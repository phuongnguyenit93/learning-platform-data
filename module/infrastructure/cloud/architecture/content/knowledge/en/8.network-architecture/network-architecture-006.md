# Designing Public DNS, Internal DNS, and Hybrid Name Resolution

## 1. Why Is DNS a Cloud Architecture Decision?

**Domain Name System (DNS)** resolves domain names into records usable by applications and infrastructure, such as IPv4/IPv6 addresses, mail servers, or domain verification metadata. In a cloud system, DNS determines which public entry point users reach, how internal workloads discover private services, and whether systems in traditional data centers can resolve cloud resource names.

DNS directly affects business experience: users unable to resolve a name cannot reach the application even when every server is healthy; a service resolving the wrong address may connect over the public Internet instead of a private path, increasing latency, cost, and security risk. Across multiple environments, networks, and providers, a minor mistake in a zone or forwarding rule can sever an entire dependency chain.

In the **CLOUD_ARCHITECTURE** module, DNS design connects closely with networking, compute, data, and deployment choices. A sound design must balance **reliability, security, scalability, cost, and operations**, while remaining verifiable under the Well-Architected mindset. This lesson focuses on three areas: **public DNS**, **private DNS inside internal networks**, and **hybrid name resolution between on-premises and cloud**.

After this lesson, you will be able to:

- Explain the roles of authoritative DNS, recursive resolvers, zones, delegation, TTLs, and caching.
- Design domain names and records for public applications, private services, and hybrid networks.
- Distinguish private DNS zones, split-horizon DNS, conditional forwarding, and DNS resolver endpoints.
- Diagram and explain DNS query paths from the Internet, corporate networks, and cloud workloads.
- Specify network requirements, access controls, redundancy, logging, and DNS failure modes.
- Verify designs with lookup commands from each source location rather than merely inspecting zone configs.

## 2. DNS Components to Distinguish

A typical DNS query traverses distinct roles:

| Component | Role | Example |
| --- | --- | --- |
| **Stub resolver** | OS/library component receiving requests from apps and forwarding them to configured DNS resolvers | Resolver on a laptop or application server |
| **Recursive resolver** | Finds answers on the client's behalf; may query authoritative servers, use cache, or forward to another resolver | Corporate DNS, cloud-provided DNS |
| **Authoritative name server** | Answers for records within the zones it authoritatively manages | Authoritative DNS for **example.com** |
| **DNS zone** | Authoritative data scope holding records and administrative metadata | Public zone **example.com**, private zone **cloud.example.com** |
| **Delegation** | Parent zone designates authoritative name servers for a child zone via NS records; may require glue records | Delegating **shop.example.com** to a unit's dedicated DNS |
| **Forwarder** | Resolver receiving queries and forwarding some or all of them to another resolver | Office DNS forwarding **cloud.example.com** to a cloud resolver |
| **Cache / TTL** | Caches lookup results for a permitted duration to cut latency and load | Resolver caches an A record for up to 300 seconds |

**Authoritative servers** and **recursive resolvers** are not the same role. An authoritative server answers for the zone data it owns, whereas a recursive resolver performs lookups for clients. One DNS software package can perform both functions, yet designs must keep their responsibility boundaries and access policies distinct.

### 2.1. How Does Internet Name Resolution Work?

~~~mermaid
sequenceDiagram
    participant U as Browser / OS
    participant R as Recursive resolver
    participant Root as Root DNS
    participant TLD as .com DNS
    participant Auth as Authoritative example.com
    U->>R: booking.example.com A?
    alt No valid cached entry
        R->>Root: Ask for .com path
        Root-->>R: NS for .com
        R->>TLD: Ask for example.com path
        TLD-->>R: NS for example.com
        R->>Auth: booking.example.com A?
        Auth-->>R: Relevant A / CNAME record
    else Cache still valid
        Note over R: Use cached result
    end
    R-->>U: Result + remaining TTL
~~~

This diagram shows the conceptual flow. In practice, resolvers may already have NS, CNAME, or answer records cached; queries may ask for AAAA, HTTPS, or other record types. Not every request travels all the way to root and TLD servers.

### 2.2. Common Record Types

| Record | Purpose | Things to watch out for |
| --- | --- | --- |
| **A / AAAA** | Maps a name to IPv4 / IPv6 | Returned address must be routable from the client's location |
| **CNAME** | Aliases one name to another name | No other record data may coexist at a CNAME name; a standard zone apex cannot use CNAME |
| **NS / SOA** | Designates name servers, admin metadata, and zone parameters | NS records at delegation boundaries must match reality |
| **MX** | Identifies mail servers for a domain | Target names must resolve properly |
| **TXT** | Stores text data such as domain verification and email policies | Never store secrets; public DNS TXT records are readable by anyone |
| **CAA** | Restricts allowed Certificate Authorities via DNS policy | Check before automating certificate issuance/renewal |
| **SRV** | Publishes certain services with target and port | Useful only when clients follow SRV conventions |
| **PTR** | Reverse lookup from IP to name | Managed in reverse zones; depends on IP range owner |
| **DS / DNSKEY / RRSIG** | DNSSEC components authenticating origin and integrity of DNS data | Requires coordinated keys and delegation; DNSSEC does not encrypt DNS queries |

Some providers support **ALIAS, ANAME, or CNAME flattening** to point a zone apex at a service with a dynamic DNS name. That is a platform feature, **not a standard CNAME record at the zone apex**. When choosing a solution, verify how the target DNS service handles records and health-based routing.

### 2.3. TTL Is a Cache Policy, Not a Precise Cutover Clock

**Time To Live (TTL)** states how long a DNS response may be cached per resolver policy. With a 300-second TTL, changing a record does not mean every client sees the new IP after exactly 5 minutes: some resolvers cached earlier, apps hold persistent connections longer, local OS caches behave independently, or resolvers apply custom policies. **NXDOMAIN** (non-existent domain) responses can also be negatively cached based on the zone's SOA parameters.

Low TTLs usually surface changes sooner, at the cost of higher query counts, fees, and DNS dependency when caches expire. High TTLs reduce load but lengthen cutover windows. Choose TTLs based on **change frequency, cutover targets, resolution path reliability, client behavior, and cost**; rehearse live changes before baking them into runbooks.

## 3. Starting from Requirements and Namespace Planning

Before creating zones, the architecture team must know who queries DNS, which network they sit in, which names need resolution, and whether expected answers are public or private addresses.

| Question | Why it matters |
| --- | --- |
| Are users on the Internet, offices, data centers, or inside a VPC/VNet? | Drives authoritative sources, resolvers, network routing, and paths |
| Which names must be public and which are strictly internal? | Determines public/private zones and publishing policies |
| Are there on-premises networks, multiple cloud accounts, multiple VPCs/VNets, or multiple providers? | Drives forwarding, zone associations/visibility, and inter-network connectivity |
| Do suffixes or names collide with legacy DNS, Active Directory, or partner systems? | Prevents broken split-horizon, authority conflicts, and forwarding loops |
| Do resources change IPs during scaling, redeploys, or failover? | Favors stable targets, dynamic records, or DNS automation |
| What are SLOs/RTO/RPO, lookup latency, and tolerance for on-prem↔cloud link loss? | Determines resolver/endpoint counts, redundancy, TTLs, and failure handling |
| Who administers zones, update permissions, certificates, and logging? | Defines ownership, auditing, change management, and security |

A measurable requirements table:

| ID | Sample requirement | Verification method |
| --- | --- | --- |
| DNS-01 | Internet clients resolve **booking.example.com** to the app's public entry point | Query from outside the corporate network and verify against authoritative config |
| DNS-02 | Internal cloud machines resolve **api.cloud.example.com** to an allowed private network IP | Query from workloads in networks associated with the private zone |
| DNS-03 | Office clients resolve private cloud names over the private link while network and resolvers are healthy | Query via on-prem resolver; verify traffic path and returned IP |
| DNS-04 | Cloud workloads resolve **erp.office.example.com** via the authorized on-prem resolver | Query from cloud, verify matching rule and traffic toward office DNS |
| DNS-05 | When one private DNS endpoint stops responding, queries still succeed via remaining endpoints within approved recovery target | Run failover tests and measure success rate/latency |

Exact quantitative thresholds for latency, success rate, and recovery time must be confirmed by business/SRE owners rather than copied from generic defaults.

### 3.1. Planning Namespaces by Ownership and Usage Scope

An illustrative scheme uses domain **example.com** (a documentation-reserved domain) and three branches:

| Namespace | Visibility | Owner | Examples |
| --- | --- | --- | --- |
| **example.com** | Public DNS | Domain/platform admin team | **booking.example.com**, **www.example.com** |
| **cloud.example.com** | Private DNS within authorized cloud networks | Platform/cloud team | **api.cloud.example.com**, **db.cloud.example.com** |
| **office.example.com** | Internal corporate DNS | Network/on-prem team | **erp.office.example.com**, **ldap.office.example.com** |

Private namespaces anchored under an owned domain establish clear boundaries and avoid inventing unmanaged internal suffixes. **Private namespaces do not have to be publicly delegated:** internal resolvers can be configured directly to know private authoritative sources. However, ensure external resolvers never accidentally rely on private records or leak sensitive internal names.

**Avoid letting independent teams share one suffix without explicit rules.** If a company uses the same **app.example.com** in both public and private zones, split-horizon must be actively governed; records may return different values depending on the resolver and network.

## 4. Designing Public DNS

**Public DNS** answers names meant to be resolved from the Internet, such as websites, public APIs, email, and domain/certificate validation records. Public authoritative zones are typically hosted on DNS services offering high availability, change control, and globally distributed points of presence.

~~~mermaid
flowchart LR
    Browser["Internet client"] --> Rec["Client's recursive DNS"]
    Rec --> Auth["Public authoritative zone: example.com"]
    Auth -->|"A/AAAA or alias for booking.example.com"| Rec
    Browser -->|"HTTPS to resolved address"| Edge["WAF / CDN / public load balancer"]
    Edge --> App["Cloud application"]
~~~

DNS **only directs clients to a target address/name**; it does not replace HTTPS, certificate validation, WAF, firewalls, load balancing, or access control. Records pointing to a service must match a routable target and valid TLS certificates for the application name.

### 4.1. Public Record Design Decisions

- **Websites and APIs:** Use A/AAAA for stable public IPs or platform-supported alias records pointing to CDNs/load balancers. Avoid hardcoding ephemeral instance or container IPs.
- **Subdomains:** Use CNAME to policy-approved targets when not at the apex. Monitor target DNS and avoid overly long CNAME chains.
- **Apex example.com:** Never place a standard CNAME alongside SOA/NS at the same owner name; if the target service lacks static IPs, consider ALIAS/flattening as supported by the DNS provider.
- **Email and verification:** Manage MX, SPF/DKIM/DMARC via appropriate records, TXT, and CAA as needed; restrict write permissions since mistakes can break systems unrelated to the app.
- **Multi-region services:** Use latency/weighted/geolocation/failover routing or global load balancing per chosen product. Check health-check behavior and caching traits before treating it as DR.

### 4.2. Public DNS Failover Must Coordinate with Application Health

Suppose **booking.example.com** points to entry points in region A and region B. A DNS service with health-based failover can return B when A is unhealthy, yet:

1. Health checks must test a representative signal; an open TCP port alone does not prove the app can process bookings.
2. Resolvers and clients may hold old addresses until caches expire; apps may also keep existing connections open.
3. Data and transactions must be engineered so B actually serves validly upon cutover. DNS does not replicate databases.
4. Drill region-loss scenarios and measure real recovery time against agreed RTO/RPO.

Public DNS can enable **DNSSEC** to authenticate response origin and integrity via the parent-zone chain of trust; key rollovers and DS record updates must be coordinated carefully so validating resolvers do not return SERVFAIL. DNSSEC **does not encrypt** queries and does not replace HTTPS.

## 5. Designing Internal DNS and Private Zones

**Private DNS** answers names meant exclusively for authorized networks: databases, internal APIs, service discovery, private cloud service endpoints, and admin systems. Private DNS zones are typically associated with one or more virtual networks, accounts, or projects per provider mechanics.

~~~mermaid
flowchart LR
    VM["App in VPC/VNet"] --> Resolver["Cloud recursive resolver"]
    Resolver --> Zone["Private zone: cloud.example.com"]
    Zone --> Resolver
    Resolver --> VM
    VM -->|"Connects to 10.42.20.15"| API["Private API, no public IP"]
~~~

In this example, **api.cloud.example.com** returns **10.42.20.15** only when workloads use a resolver permitted to see the zone and have valid network paths. This is an illustrative private address. Not every Internet client can query private zones, and having a private A record **does not mean the network permits traffic**.

### 5.1. Authoritative Sources and Zone Visibility

- Identify where **cloud.example.com** is managed and which networks are associated. If a workload sits in another VPC/VNet, establish proper associations, peering, or resolution mechanisms; network reachability to an IP does not automatically grant DNS zone visibility.
- For cloud services with **private endpoints**, check how the provider handles private DNS names, CNAMEs, or private-zone records. Target the exact hostname clients actually call; do not assume every endpoint has a static IP.
- Across **dev/staging/prod**, consider distinct suffixes or separate association permissions to prevent accidental record overwrites—for example, **api.prod.cloud.example.com** and **api.dev.cloud.example.com** with clear zone/association rules.
- In Kubernetes, cluster DNS (typically serving **service.namespace.svc.cluster.local**) is a separate service-discovery layer from VPC/VNet private DNS. Do not assume cluster service names automatically resolve from all on-prem networks or the Internet.

### 5.2. Split-Horizon DNS: One Name, Multiple Answers

**Split-horizon** (also called split-view or split-brain DNS in some literature) means the DNS answer for the same name varies by client location or resolver used.

| Query origin | Queried name | Example result |
| --- | --- | --- |
| Internet | **portal.example.com** | Public IP of CDN/WAF |
| Internal network | **portal.example.com** | Private IP of internal load balancer |
| Internet | **db.cloud.example.com** | Private zone data is not publicly exposed |
| Associated VPC/VNet | **db.cloud.example.com** | Private IP of database or private endpoint |

Split-horizon helps when corporate users must reach the same hostname over a private link while keeping certificates aligned with that name. However, it creates an obligation to keep required records synced across views. **A private zone sharing the same name/suffix as a public zone can shadow public records:** when a private resolver searches the private zone and a record is missing, it may return NXDOMAIN instead of falling back to the public zone. Exact behavior varies by resolver and cloud service, so test rather than assuming fallback always happens.

If sharing the exact hostname is unnecessary, separating namespaces cleanly—such as **public booking.example.com** and **private api.cloud.example.com**—is usually easier to operate.

### 5.3. Private DNS Is Not a Firewall

Withholding names from public DNS reduces service discoverability, yet **does not replace** network segmentation, ACLs/security groups, IAM, service authentication, TLS, or data controls. Any party knowing the IP or name can still attempt connections if routes and policies allow. Private DNS design and network security policies must be verified together.

## 6. Hybrid Name Resolution: Bidirectional Between On-Premises and Cloud

**Hybrid DNS** solves how on-premises and cloud clients resolve each other's names across private interconnects such as site-to-site VPN or dedicated private links. The core task is deciding **which recursive resolver is authorized to query which authoritative source** and establishing connectivity to permitted resolvers.

Two primary query directions:

1. **On-premises → Cloud:** Office clients need to look up **api.cloud.example.com** in the cloud private zone. On-prem DNS forwards queries matching that suffix to the **cloud inbound resolver endpoint**; the cloud resolver queries the private zone and returns the private address.
2. **Cloud → On-premises:** Cloud workloads need to look up **erp.office.example.com**. The cloud resolver uses a **conditional forwarding rule** to send queries to on-prem DNS via the **cloud outbound resolver endpoint** or equivalent mechanism.

~~~mermaid
flowchart LR
    subgraph Office["On-premises network"]
      Client["Office client"]
      OnDNS["Internal DNS / recursive resolver"]
      ERP["ERP: 10.10.20.15"]
      Client --> OnDNS
    end
    subgraph Link["Routed VPN / private interconnect"]
      Tunnel["Private network link"]
    end
    subgraph Cloud["Cloud VPC/VNet"]
      In["Inbound DNS resolver endpoint"]
      CloudDNS["Cloud recursive resolver + private zone cloud.example.com"]
      Out["Outbound DNS resolver endpoint"]
      Workload["Cloud application"]
      API["Private API: 10.42.20.15"]
      Workload --> CloudDNS
      In --> CloudDNS
      CloudDNS --> Out
    end
    OnDNS -->|"cloud.example.com"| Tunnel
    Tunnel --> In
    Out -->|"office.example.com"| Tunnel
    Tunnel --> OnDNS
    CloudDNS -.-> API
    OnDNS -.-> ERP
~~~

This diagram illustrates the **logical query path**, not DNS response return paths or actual application data connections. Even after a name resolves properly, clients still need routes, firewalls/security groups, TLS, and permissions to reach the API or ERP IP.

### 6.1. What Does a Cloud Inbound Endpoint Do?

An inbound endpoint provides private IP addresses to which on-prem DNS servers are allowed to send queries into the cloud resolver service. It is **not a public authoritative DNS server**, should not be exposed directly to the Internet, and does not create VPC/VNet network routes by itself. Ensure on-prem source IPs route to the endpoint and are permitted to send DNS over the appropriate protocol.

### 6.2. What Does a Cloud Outbound Endpoint Do?

An outbound endpoint is the path the cloud resolver service uses to send queries from the cloud to DNS servers outside its scope, such as corporate internal DNS. It requires a **suffix-based forwarding rule**, on-prem DNS target IPs, and rule association with the relevant networks. Some providers use different names or policy models; the logical goal remains forwarding the right query to the authoritative source.

### 6.3. How Does Conditional Forwarding Differ from Delegation?

- **Conditional forwarding:** A recursive resolver forwards queries for a specific suffix to designated target resolvers/forwarders. Ideal for cloud-managed private zones, especially when only an inbound resolver IP exists without directly exposed authoritative NS servers.
- **Delegation:** A parent authoritative zone publishes NS records for a child zone. Suited when a child zone has authoritative servers directly reachable by resolvers. Never confuse a **recursive inbound resolver IP** with an **authoritative name server** meant for delegation.
- **DNS peering / sharing:** Some platforms support sharing private zones across networks/accounts/projects or DNS peering policies. Capabilities and limits depend on the provider and differ from raw network peering.

In hybrid networks, conditional forwarding is often the pragmatic choice to bridge cloud private zones and corporate DNS; still weigh zone governance, access control, caching, availability, and endpoint types.

## 7. End-to-End Example: Three Namespaces and Three Resolution Paths

Suppose the enterprise uses:

| Component | Illustrative value | Scope |
| --- | --- | --- |
| Public domain | **example.com** | Public authoritative DNS |
| Public app | **booking.example.com** → public entrypoint | Internet |
| Private cloud zone | **cloud.example.com** | Associated cloud VPCs/VNets |
| Private API | **api.cloud.example.com** → **10.42.20.15** | Authorized cloud and on-prem clients |
| Cloud inbound DNS endpoints | **10.42.1.10**, **10.42.2.10** | Two distinct subnets/fault zones where supported |
| Private on-prem zone | **office.example.com** | Corporate DNS |
| On-prem ERP | **erp.office.example.com** → **10.10.20.15** | Authorized on-prem and cloud workloads |
| On-prem DNS | **10.10.0.53**, **10.11.0.53** | Two resolvers across distinct fault zones |
| Hybrid link | Routed VPN or private link | 10.10.0.0/16 ↔ 10.42.0.0/16 (illustrative) |

These addresses and records are **for design practice only**. In real deployments, select IPs, routing, zone associations, and subnets from your network plan rather than copying these values into production.

### 7.1. Internet Client Queries booking.example.com

~~~text
Internet client
  -> external recursive resolver
  -> public authoritative zone example.com
  -> record for booking.example.com
  -> public entrypoint IP / hostname
  -> client connects over HTTPS via Internet
~~~

There is no reason to route this query through corporate internal DNS. The cloud platform can sit behind a CDN/WAF/load balancer; public DNS must never leak internal admin or database addresses.

### 7.2. Office Client Queries api.cloud.example.com

~~~text
Office laptop
  -> on-prem recursive DNS 10.10.0.53
  -> rule for cloud.example.com
  -> private link to cloud inbound DNS 10.42.1.10 or 10.42.2.10
  -> private zone cloud.example.com
  -> A 10.42.20.15
  -> answer returns to laptop
  -> laptop connects to private API per policy and route
~~~

The office resolver does not need to know every cloud record; it only needs to know **where to forward queries matching suffix cloud.example.com**. When the API changes IP under controlled change management, the cloud team updates the private zone rather than rewriting office DNS configurations.

### 7.3. Cloud Workload Queries erp.office.example.com

~~~text
Cloud workload
  -> cloud resolver
  -> rule for office.example.com
  -> outbound DNS endpoint over VPN/private link
  -> on-prem DNS 10.10.0.53 or 10.11.0.53
  -> authoritative data for office.example.com
  -> A 10.10.20.15
  -> answer returns to workload
  -> workload connects to ERP per policy and route
~~~

**Both directions require distinct configurations:** on-prem forwarding to cloud inbound, and cloud forwarding to on-prem targets via outbound. Configuring only one direction will let one side succeed while reverse calls fail.

## 8. Authority, Forwarding Rules, and Avoiding Loops

Hybrid DNS failures rarely stem from missing records; they more often come from **two resolvers disagreeing on who is authoritative for a suffix**. If both office and cloud forward queries for the same domain to each other, queries loop until limits trip and return SERVFAIL. If a resolver believes it owns an authoritative zone that lacks a record, it returns NXDOMAIN without asking elsewhere.

### 8.1. Authority and Forwarding Ownership Matrix

| Suffix | Authoritative source | What office DNS does | What cloud DNS does |
| --- | --- | --- | --- |
| **example.com** (public) | Public authoritative DNS | Resolves publicly per default policy | Resolves publicly per default policy |
| **cloud.example.com** (private) | Cloud private zone | **Forwards** to cloud inbound endpoint | Looks up in associated private zone |
| **office.example.com** (private) | On-prem DNS | Answers from internal zone | **Forwards** via cloud outbound endpoint to on-prem DNS |
| Names outside above suffixes | Corresponding authoritative source | Follows existing recursive DNS policy | Follows existing recursive DNS policy |

Here, **cloud.example.com** and **office.example.com** are separate branches so neither team has to co-manage a shared zone. If an organization uses a deeper domain tree (such as parent/child with multiple private subzones), verify longest-suffix rule precedence, delegation, and authoritative NXDOMAIN behavior on each resolver.

### 8.2. Error-Prone Scenarios

| Scenario | What can happen | Prevention |
| --- | --- | --- |
| On-prem forwards all **example.com** to cloud, while cloud forwards all **example.com** to on-prem | Forwarding loop or broken public record resolution | Forward **only suffixes owned by the other side**, using specific rules |
| Cloud hosts private zone **example.com** missing **booking.example.com** | Private zone shadows public zone, potentially returning NXDOMAIN | Separate internal suffixes or maintain complete split-horizon, testing missing records |
| Two DNS servers claim authority for the same private zone with divergent data | Clients see inconsistent answers | Designate one authoritative source or owned sync/delegation |
| Forwarder falls back to public DNS when private endpoint fails | Private queries leak to external DNS or return unwanted results | Consider **forward only** for private zones and dedicated redundancy |
| Rules configured for only one direction | On-prem→cloud works while cloud→on-prem fails | Verify both directions independently in a test matrix |
| Putting resolver endpoint IP in NS when endpoint only accepts recursive queries | Delegation fails to work as expected | Distinguish recursive inbound endpoints from authoritative NS |

With many VPCs/VNets or multiple clouds, design a **suffix ownership and forwarding-direction table** before creating rules in bulk. A suffix may split into branches, but never allow two conflicting paths without clear ownership.

### 8.3. Should DNS Forwarding Fall Back to the Internet?

For **private names**, policies that forward strictly to authorized resolvers are usually safer. If the private path fails, return a clear error and fire alerts rather than silently querying public DNS—which lacks the record anyway and could leak internal names.

For **public names**, resolvers still need normal Internet resolution or an approved forwarder. Balancing reliability against query leakage is a policy decision that should be documented in corporate DNS standards.

## 9. Conditional Forwarding Configuration Examples

### 9.1. BIND9 On-Premises

If office DNS uses BIND9 as its recursive resolver, an illustrative config for the cloud suffix might look like:

~~~conf
// On on-prem recursive DNS (illustrative, not a complete configuration).
zone "cloud.example.com" IN {
    type forward;
    forward only;
    forwarders {
        10.42.1.10;  // Cloud inbound resolver, fault zone A
        10.42.2.10;  // Cloud inbound resolver, fault zone B
    };
};
~~~

Meaning: when clients query names under **cloud.example.com**, BIND sends queries to the two configured endpoints per BIND's server-selection policy. **forward only** prevents falling back to iterative public resolution if forwarders fail to respond. Both IPs must be real provisioned endpoints with proper network connectivity and ACLs; these are not public DNS addresses.

If on-prem DNS also hosts the authoritative **office.example.com** zone, the zone config can live on the same service or on a separate authoritative server:

~~~conf
// On internal authoritative DNS (functional illustration only).
zone "office.example.com" IN {
    type primary;
    file "/etc/bind/zones/office.example.com.zone";
};
~~~

In real deployments, zone types, zone-file read permissions, recursion restrictions, views, ACLs, DNSSEC validation, and reload behavior must be verified on the exact BIND version in use. **Never expose a recursive resolver to the entire Internet**, as it can be abused for DNS amplification/reflection attacks and leak internal namespaces.

### 9.2. Cloud Forwarding to On-Premises

With managed cloud DNS, logical configuration can be expressed as:

~~~text
Query source:
  Workloads in VPC/VNet associated with the DNS ruleset

Rule:
  Suffix: office.example.com
  Action: FORWARD
  Egress path: outbound DNS resolver endpoint
  Target DNS servers:
    - 10.10.0.53
    - 10.11.0.53

For suffix cloud.example.com:
  Answer from private zone cloud.example.com associated with network

Other public names:
  Use approved recursive/default resolver path
~~~

The snippet above is a **policy description**, not Terraform or CLI commands portable across every cloud. Syntax for creating forwarding rules, associating rulesets with networks, and configuring outbound endpoints differs by provider.

### 9.3. Using IaC and Change Management

In real projects, manage zones, records, associations, forwarding rules, firewall rules, and resolver endpoints via **Infrastructure as Code** whenever supported. Changes require peer review for impact, ownership, and verification steps:

1. Provision private connectivity and permitted resolver endpoints.
2. Query the endpoint directly from the source network to test reachability.
3. Add suffix-specific conditional forwarding rules.
4. Test using the client's default resolver rather than specifying endpoints manually.
5. Verify public queries and unrelated suffixes remain unaffected.
6. Monitor logs/metrics and update runbooks.

Avoid modifying dozens of zones and rules simultaneously before proving one complete resolution path end-to-end. For changes touching authoritative zones, account for TTLs and negative caching before cutting over.

## 10. Network Conditions Required for Hybrid DNS to Actually Work

A valid DNS record does not guarantee clients can reach it. Hybrid DNS requires **bidirectional networking**, **resolvers permitted to answer**, and **application reachability after resolution**.

| Component | Checks required |
| --- | --- |
| **Private link** | VPN/private interconnect is up, with routes to resolver subnet IPs and return routes |
| **Firewall/ACL** | Allow only approved DNS servers to send queries over UDP **and TCP** port 53 to target endpoints |
| **Network security group** | Inbound endpoints accept traffic only from trusted on-prem DNS CIDRs/IPs; outbound permitted to on-prem DNS |
| **DNS server policy** | Allow-query, allow-recursion, views, ACLs, and forwarders do not reject valid clients/resolvers |
| **Redundancy** | At least two resolver/endpoint IPs across appropriate fault domains where supported; no single shared box |
| **NAT and source IP** | Confirm which source IP target DNS sees behind VPN/NAT; ACLs must match actual source IPs |
| **MTU and EDNS(0)** | Large responses may truncate/fragment; DNS must succeed when falling back to TCP |
| **Dual-stack resolution** | If IPv6 is enabled, check AAAA records, IPv6 routing, firewalls, and resolver/endpoint IPv6 support |
| **Application target** | Returned IP has routes and access rules on the application port, e.g., HTTPS 443 |

**Why is TCP port 53 required?** Standard DNS lookups use UDP, yet TCP is used when responses truncate, for certain DNS transactions, and when clients/resolvers explicitly choose TCP. A system allowing only UDP 53 may work for small records yet fail mysteriously on large responses or DNSSEC-signed payloads. Not every DNS timeout means a record is missing.

### 10.1. Separate the DNS Query Path from the Application Data Path

For instance, an office laptop resolves **api.cloud.example.com** to **10.42.20.15** via the inbound DNS endpoint. Next, the laptop needs HTTPS connectivity to **10.42.20.15**. Reachability to the resolver IP (10.42.1.10) **does not guarantee** routes or firewall rules exist to the application IP (10.42.20.15).

Verify both paths:

~~~text
DNS control path:
  On-prem DNS -> VPN/private link -> cloud inbound resolver -> private zone

Application data path:
  On-prem client -> VPN/private link -> private API load balancer / service
~~~

The same model applies in the cloud → on-prem direction. Distinguishing the two paths isolates real faults: if resolution succeeds while the app times out, the issue lies in routes, firewalls, TLS, or the service itself rather than DNS.

### 10.2. Multi-Network or Multi-Account Designs

If applications span multiple VPCs/VNets, verify which networks see private zones and forwarding rules. Depending on the provider, you may need zone associations, rule sharing, DNS peering, or centralized resolvers. Never assume **network peering automatically implies DNS zone sharing**; those are usually separate capabilities.

Centralized resolvers cut duplicate endpoints and rules, yet create a **shared dependency** requiring HA, access governance, and throughput headroom. Distributed resolvers boost autonomy while raising cost, configuration count, and inconsistency risk. Choose based on network count, ownership, latency, availability, and governance capability.

## 11. Reliability, TTL, and Failover Handling

DNS sits in the serving critical path. If DNS dependencies break, many workflows fail even while compute and databases remain healthy. DNS recovery targets and monitoring must therefore tie directly to business journeys.

### 11.1. Designing Around Fault Domains

- **Public DNS:** Select authoritative DNS with multi-POP resilience and proper change controls; if using multiple providers, address zone sync, DNSSEC, delegation, and single-provider outage behavior.
- **On-prem DNS:** Deploy redundant resolvers/authoritative servers across suitable fault zones rather than sharing a single VM, power feed, or circuit when impact is high.
- **Cloud resolver endpoints:** Where supported, place multiple endpoint IPs across different subnets/zones; monitor quotas and reachability.
- **Hybrid connectivity:** A single VPN or dedicated circuit can be a single point of failure for both DNS and app traffic. A second link adds real resilience when justified by recovery targets.
- **Client resolvers:** Verify DNS server ordering and OS/runtime retry behavior; listing two resolvers does not guarantee every client fails over immediately to the second server.

### 11.2. Do Not Rely on TTL as Your Only HA Mechanism

Low TTLs shorten how long stale records persist, yet cannot fix dead authoritative/resolver servers, timeouts, long-lived open connections, or unsynced data. For public region failover, pair health checks, global load balancing, and application DR. For private DNS, engineer endpoint HA, forwarding redundancy, and resilient network paths.

Overly low TTLs strain resolvers and inflate query fees. Overly high TTLs delay traffic shifts. Account for **negative caching** as well when adding new records where systems previously returned NXDOMAIN.

### 11.3. Setting Targets by Business Criticality

Illustrative example:

| Flow | Impact on failure | Reliability measures to evaluate |
| --- | --- | --- |
| Customers visiting public site | Lost access, revenue impact | HA public DNS, external synthetic monitoring, health-based routing if needed |
| Cloud app connecting to private DB | Critical transaction failures | Stable private zone/endpoints, DB-compatible failover, in-workload probes |
| Cloud querying on-prem ERP | Delayed or halted synchronization | Redundant on-prem DNS, backup VPN, queues, or graceful error handling if business allows |
| Office accessing private cloud API | Internal staff blocked from operations | HA inbound DNS endpoints, redundant conditional forwarders, HA app paths |

RTO/RPO is not decided by DNS alone; DNS is one factor affecting overall system RTO. Measure recovery time **end-to-end**, not merely record propagation time.

## 12. Security and DNS Lifecycle Governance

### 12.1. Public DNS

Control over domain ownership, NS/DS changes, zones, and records can affect the entire enterprise. Enforce:

- Protect registrar and DNS provider accounts with MFA, least privilege, change approval, and audit logs.
- Separate permissions to update app records from permissions to alter delegation, NS, DNSSEC keys, and domain-wide settings.
- Evaluate DNSSEC and controlled key rotation if used; inconsistent DS records cause validating resolvers to fail.
- Govern CAA, certificate issuance/renewal workflows, and domain verification records; never place live tokens/secrets in public TXT records.
- Protect DNS automation pipelines: scope permissions per zone/record where supported, enforce change control, and run tests.

### 12.2. Internal and Hybrid DNS

- Restrict recursive DNS and inbound endpoints strictly to authorized clients/DNS servers. **Never run an open resolver.**
- Forward only required suffixes; avoid leaking internal namespace names to public resolvers.
- Keep internal DNS traffic on protected private networks; standard DNS over UDP/TCP 53 **does not encrypt payloads**. If DNS-layer encryption is required, evaluate DoT/DoH or supported equivalents on both ends; VPNs protect site-to-site transit but do not replace all endpoint policies.
- Prevent unauthorized record edits, retain audit trails, and monitor anomalies; limit who can modify zones and resolver rules.
- Authenticate applications and enforce TLS for service connections, because **private DNS is neither authentication nor authorization**.
- Weigh privacy of DNS query logs: queried names can expose internal services, accounts, or access patterns; apply suitable retention and access controls.

Common threats include **DNS spoofing/cache poisoning**, misconfigurations redirecting to unintended targets, **DNS tunneling** for data exfiltration, DDoS or resolver abuse, and unauthorized record tampering. Defenses must align with real threat models rather than flipping on DNSSEC and assuming total security.

### 12.3. Record Ownership and Governance

| Role | Responsibility |
| --- | --- |
| Domain owner / registrar admin | Controls root domains, delegation, and sensitive registrar actions |
| Public DNS owner | Manages public zones, DNSSEC, record checks, and customer-facing changes |
| Cloud platform team | Manages private zones, associations, resolver endpoints, and forwarding rules |
| Network / on-prem team | Manages internal DNS, VPN/routing, and firewalls for hybrid DNS |
| Application owner | Defines hostnames, targets, TTL expectations, and monitors app impact |
| Security / SRE | Audits permissions, DNS logging, SLOs, alerts, and incident drills |

Each zone needs one approved source of change; avoid manual edits in multiple consoles without reconciliation. When decommissioning a service, clean up associated records, permissions, and rules on schedule to avoid dangling DNS or pointing to stale targets.

## 13. Mapping the Model to Cloud Providers

Services differ in naming and limits. This table is strictly a **conceptual map** to select components; prior to implementation, consult current provider documentation on regions, quotas, DNS forwarding, network associations, and security features.

| Need | AWS | Microsoft Azure | Google Cloud |
| --- | --- | --- | --- |
| Public DNS | Route 53 public hosted zone | Azure DNS public zone | Cloud DNS public zone |
| Internal DNS | Route 53 private hosted zone associated with target VPCs | Azure Private DNS zone linked to VNet | Cloud DNS private zone authorized for network |
| On-prem → cloud private DNS queries | Route 53 Resolver inbound endpoint | Azure DNS Private Resolver inbound endpoint | Cloud DNS inbound forwarding via server policy and network config |
| Cloud → on-prem DNS queries | Route 53 Resolver outbound endpoint + forwarding rule | Azure DNS Private Resolver outbound endpoint + DNS forwarding ruleset | Cloud DNS forwarding zones / outbound server policy per requirements and product limits |
| Hybrid network link | VPN / Direct Connect | VPN Gateway / ExpressRoute | Cloud VPN / Cloud Interconnect |

These options are not 1:1 equivalents. Sharing private zones across accounts/projects, spoke resolver behavior, and overlapping-name handling all differ. In multi-cloud architectures, explicitly document **which service is authoritative for which suffix**, which endpoint types receive queries, and where forwarding rules must reside.

Self-managing BIND/Unbound can fit specialized control needs or legacy integration, yet leaves HA, patching, backups, monitoring, capacity planning, and security on your team. Managed DNS reduces operational toil in exchange for service feature limits, costs, and integration boundaries.

## 14. Testing Properly from Every Query Location

DNS answers vary by network, resolver, view, and cache state. Testing one lookup from an admin's laptop **does not prove** Internet clients, office machines, and cloud workloads all resolve properly. Build a test matrix specifying source, actual resolver, queried name, record type, expected answer, and application connectivity.

### 14.1. Expected Results Matrix

| Location / resolver | **booking.example.com** | **api.cloud.example.com** | **erp.office.example.com** |
| --- | --- | --- | --- |
| Internet / public recursive resolver | **Public** IP or alias | Must not receive private-zone records from public DNS | Must not receive private-zone records from public DNS |
| Authorized VPC/VNet / cloud resolver | Public entrypoint per policy | **10.42.20.15**, if zone is linked and record exists | **10.10.20.15** via forwarding rule to on-prem |
| Office network / on-prem recursive resolver | Public entrypoint per policy | **10.42.20.15** via forward to cloud inbound endpoint | **10.10.20.15** from on-prem authoritative DNS |
| **Unauthorized** VPC/VNet without private zone | Public entrypoint per policy | Must not assume private zone resolves | Resolves only if explicitly designed and authorized |

Responses for private names from unauthorized networks may be NXDOMAIN, NODATA, REFUSED, or timeouts depending on resolver design; the key criterion is **zero private data leaked via unauthorized paths**, without breaking public DNS.

### 14.2. Verification Commands with dig

The commands below are examples to run **from an authorized query location** after replacing sample domains/IPs with real lab values. **example.com** and sample IPs in this lesson do not represent live Internet records.

From an authorized office machine:

~~~bash
# Test default path: machine -> on-prem recursive DNS -> cloud inbound
dig @10.10.0.53 api.cloud.example.com A +time=2 +tries=1

# Query cloud inbound DNS directly to isolate on-prem forwarder issues
dig @10.42.1.10 api.cloud.example.com A +time=2 +tries=1

# Test TCP fallback on an authorized endpoint
dig +tcp @10.42.1.10 api.cloud.example.com A

# Check on-prem name at defined authoritative/recursive source
dig @10.10.0.53 erp.office.example.com A
~~~

From a cloud workload using configured default DNS:

~~~bash
# Test cloud rule -> outbound endpoint -> on-prem DNS
dig erp.office.example.com A +time=2 +tries=1

# Test cloud private zone inside the running network
dig api.cloud.example.com A +time=2 +tries=1

# Verify the app still resolves a public name
dig booking.example.com A
~~~

From an Internet test environment:

~~~bash
# Test public recursive DNS -> authoritative public zone
dig @1.1.1.1 booking.example.com A

# Inspect public domain delegation chain (do not use for private-only zones)
dig +trace booking.example.com A
~~~

Never send sensitive production internal names to public resolvers just to test privacy; to verify private zones aren't exposed publicly, test with **approved dummy names** and inspect authoritative public zone configurations.

Key fields in **dig** output to understand:

- **status: NOERROR** means the query succeeded at the DNS protocol level; it **does not guarantee an A record exists**. If no A record exists but the name holds other record types, you get NOERROR with an empty ANSWER section (*NODATA*).
- **status: NXDOMAIN** indicates the name does not exist according to the authoritative source accepted by the resolver; check for private-zone shadowing or negative caching.
- **status: SERVFAIL** signals a processing/lookup failure; possible causes include unreachable upstream, failed DNSSEC validation, forwarding loops, or backend DNS errors.
- **status: REFUSED** typically points to ACLs, recursion limits, or query permission policies.
- **Timeout** differs from NXDOMAIN; check network routes, firewalls, DNS server availability, and source IPs.
- The **SERVER** field shows which server answered from the local host's viewpoint; it is not proof that server is the final authoritative source.
- **ANSWER / AUTHORITY / ADDITIONAL** and remaining TTL help trace the response chain, though resolvers may serve cached entries.

### 14.3. Verify Connectivity After DNS Too

If `dig` properly returns **10.42.20.15** yet the client still cannot call the API, inspect routes, ACLs/security groups, app ports, TLS certificates, SNI, and auth policies. Application tests must use the **expected hostname** to validate TLS/SNI; connecting directly to an IP can behave differently.

When validating failover, simulate an unreachable endpoint in an approved test environment and measure how quickly clients switch to the surviving endpoint. Repeat for VPN/on-prem DNS link loss if covered by reliability targets. Never verify records solely while everything is healthy.

## 15. Diagnosing DNS Incidents by Symptom

DNS failures are easily mistaken for application or network bugs. A disciplined diagnostic path follows: **which resolver did the client ask → which rule/zone did the resolver pick → what path did the query take → what did the authoritative source return → was it cached → can the app connect to the returned IP?**

| Symptom | Causes to inspect | Next verification steps |
| --- | --- | --- |
| **NXDOMAIN** for a newly created private name | Record missing in private zone, shadowed by another private zone, negative cache, wrong suffix | Query the target zone resolver directly; check zone associations, SOA/authority, and negative TTL |
| **SERVFAIL** for one suffix while public names work | Forwarding loop, unresponsive upstream, DNSSEC validation, recursive resolver error | Compare queries hop by hop; check logs, forwarding rules, and DNSSEC |
| **Timeout** querying cloud inbound endpoint | VPN/routes, UDP/TCP 53 firewall, endpoint down, unexpected ACL or source IP | Test reachability from on-prem DNS, outbound/return routes, packet/logs on both ends |
| **REFUSED** | Client or target lacks recursion/query permission | Inspect allow-recursion, allow-query, resolver policies, and network associations |
| Has **A** but no **AAAA**, or vice versa | Record type or IPv6 policy differs from expectation | Query A/AAAA explicitly; check addressing and protocol routing |
| Small queries succeed, large queries fail | Blocked TCP 53, EDNS(0), MTU, or fragmentation | Retry with `+tcp` and inspect UDP/TCP paths and response sizes |
| On-prem → cloud OK, cloud → on-prem fails | Missing outbound rule, route, or on-prem DNS rejects endpoint source IP | Query from cloud resolver; check cloud outbound and office ACLs |
| Name resolves in one VPC but fails in another | Private zone unlinked, ruleset not associated, or differing DNS peering | Compare network associations and active resolvers |
| Client holds old IP after record update | OS/runtime/recursive cache, TTL, negative caching, or stale connection | Inspect TTLs per hop and active connections; compare authoritative vs. client |
| DNS right yet HTTP times out / TLS fails | Bad route to target, security group, service health, cert/SNI mismatch | Debug data path and service; stop editing DNS once resolution is proven |
| Public names break after adding a broad private zone | Split-horizon shadowing public records | Inspect private zones sharing suffixes, missing records, and fallback behavior |

### 15.1. Reusable Investigation Playbook

1. **Capture evidence:** Timestamp, query origin, DNS server used, queried name, record type, result, TTL, and error rate.
2. **Compare vantage points:** Public, on-prem, cloud network A, cloud network B; pinpoint the boundary where answers diverge.
3. **Trace hop by hop:** Client recursive resolver → conditional forwarder → inbound/outbound endpoint → authoritative source; do not jump straight to editing zones.
4. **Verify DNS and network separately:** Check UDP/TCP 53, VPN routes, ACLs, and then application ports.
5. **Isolate caching:** Query the appropriate authoritative/source directly to separate updated data from stale caches.
6. **Remediate narrowly:** Fix rules/records/ACLs backed by evidence; retest both related public and private queries to avoid regressions.
7. **Update runbooks:** Document the failure mode, detection signals, owner, and post-change checks.

### 15.2. Monitoring and Alerting

A mature observability setup combines three layers:

- **Synthetic DNS probes:** From the Internet and representative internal networks, periodically query critical names and assert response codes, expected answers, and latency.
- **Resolver/endpoint metrics:** Track success rate, SERVFAIL, REFUSED, timeouts, latency, throughput, forwarding errors, quotas, and utilization.
- **Application symptoms:** Track connect errors, DNS resolution failures, request timeouts, and business journey SLO impact.

Do not alert solely when a DNS server fails to ping: a resolver can stay up while returning stale data or failing for a specific suffix. Apply suitable retention, access controls, and sensitive-data redaction to DNS logs.

## 16. Well-Architected Trade-Offs

DNS simultaneously influences multiple architectural goals; improving one dimension can add complexity elsewhere.

| Well-Architected perspective | Common decisions | Trade-offs to weigh |
| --- | --- | --- |
| **Operational Excellence** | Standardized naming, IaC, ownership, logs, record change workflows | Cuts manual errors but requires governance and change blast-radius control |
| **Security** | Private zones, recursion limits, public DNSSEC, source ACLs, DNS logging | Strengthens defense while adding key, permission, privacy, and policy duties |
| **Reliability** | HA resolvers, multiple endpoints, backup VPN links, health-based routing | Improves uptime while increasing cost and config surface needing drills |
| **Performance Efficiency** | Workload-local DNS, tuned TTLs/caching, centralized vs. distributed resolvers | Caching lowers latency and query volume yet risks serving stale data |
| **Cost Optimization** | Managed DNS, central resolvers, endpoint count, logs, private links | Cuts ops toil while potentially raising service fees; optimize total cost of ownership |
| **Sustainability** | Eliminate redundant DNS queries, over-provisioned setups, and idle endpoints | Resource optimization must still preserve required redundancy |

### 16.1. Centralized or Distributed Resolvers?

**Centralized resolvers** consolidate suffix management, monitoring, and on-prem integration in one place—fitting organizations with strong platform teams. However, they can increase cross-region/network dependencies, blast radius, and transfer charges if every workload routes through one hub.

**Distributed resolvers** boost autonomy and reduce cross-zone network dependencies, at the expense of more endpoints, IaC modules, permissions, update workflows, and audits. A practical middle ground keeps **consistent governance** while placing resolution points per fault/geographic domain based on load data, latency, and org structure.

### 16.2. Metrics to Include in Design

| Metric | How to measure | Significance |
| --- | --- | --- |
| Query success rate for critical names | Synthetic probes from every location, grouped by response code | Detects broken resolution or bad answers |
| Query latency p50/p95/p99 | Measured at clients/resolvers and per suffix | Flags network, forwarding, or resolver slowdowns |
| Error rates by class | Unexpected NXDOMAIN, SERVFAIL, REFUSED, timeouts | Distinguishes data, policy, and connectivity faults |
| Record propagation time | Measured before/after updates across representative recursive resolvers | Evaluates TTLs, caching, and release process |
| Recovery time on endpoint/link failure | Drilled from real clients; includes end-to-end app connectivity | Validates against business SLOs/RTO |
| DNS cost | Hosted zones, query volume, endpoints, traffic, logs, ops effort | Optimizes total cost |

Metrics and alert thresholds should align with each journey's criticality. **Never set a vague target like “DNS answers 100% of the time”** without specifying measurement locations, query types, evaluation windows, and dependency ownership.

## 17. Practice Exercise: Designing Hybrid DNS for an Ordering System

An enterprise runs a public e-commerce website, an ERP in an on-premises data center, and internal services in the cloud. Over the next six months, the company is migrating its order API to the cloud while keeping the ERP on-premises. The company has two offices, one primary VPN, and multiple VPCs/VNets; operations wants to ensure order confirmations do not halt just because one DNS endpoint or DNS server fails.

Assumptions:

- Public domain: **shop.example.com** serving Internet customers.
- Private cloud API: **orders.cloud.example.com**, never exposed to the Internet.
- Internal ERP: **erp.office.example.com**.
- On-prem DNS: two servers in two separate fault zones.
- Cloud networking: app workloads span two virtual networks; it is not yet confirmed whether private zones/rulesets are linked to both.
- Cloud↔on-prem has a private link, though link redundancy has not been approved yet.

**Tasks:**

1. Draw a diagram showing **public authoritative DNS, on-prem DNS, cloud private zone, cloud inbound/outbound endpoints, private links, and clients in all three locations**.
2. Create a table mapping **suffix → authoritative source → forwarding resolver → permitted querying networks**. Specify who owns and approves each zone.
3. Organize zones to avoid loops, suffix collisions, and internal name leaks. If using split-horizon, explain which records must stay synchronized.
4. Write bidirectional conditional forwarding policies and network rules for **UDP/TCP 53**, including real source IPs and return routes.
5. Build a **test matrix of at least 9 checks**: three names from three locations; state expected results, verification commands, unauthorized query behavior, and differences from the application data path.
6. Propose incident handling for losing **one inbound endpoint**, **one on-prem DNS server**, and **the VPN link**. State what DNS alone cannot solve, such as apps losing network routes to the ERP.
7. Select public and private TTLs for cutover scenarios; explain cache effects, negative caching, and query volume. Avoid inventing hard SLA numbers where no SLO exists.
8. Write a short **Architecture Decision Record**: choose a centralized or distributed resolver model, list rejected options, risks, costs, and review triggers.

### Evaluation Guide

A passing design keeps the public zone cleanly isolated and Internet-resolvable, supports bidirectional private namespace resolution via proper authoritative sources with zero forwarding loops, and enforces least-privilege query permissions. The test matrix must prove **resolution from real network contexts**, not just console record screenshots.

In the DR section, distinguish:

- **DNS still resolves while VPN is down:** Clients receive valid private IPs yet cannot reach on-prem/cloud apps over the broken link.
- **DNS endpoint fails while app path stays up:** Requires redundant resolver endpoints, tuned forwarding timeouts, and retries.
- **Wrong name returned due to split-horizon:** Requires fixing zones/rules and waiting out caches; adding more servers will not fix wrong data.

## 18. Pre-Production DNS Checklist

- [ ] Clients, source networks, hostnames, record types, and expected results per location are documented.
- [ ] Every public/private zone has a clear **authoritative source, owner, and change-control workflow**.
- [ ] Public, private cloud, and private on-prem namespaces are planned; any split-horizon cases are documented.
- [ ] Public domain delegation, NS/SOA, CAA, and DNSSEC (if used) are verified alongside certificate workflows.
- [ ] Private zones are linked to exact VPCs/VNets/accounts/projects; never assume network peering shares DNS automatically.
- [ ] **On-prem → cloud inbound** and **cloud → on-prem outbound** rules are defined per specific suffix.
- [ ] Zero forwarding loops, overly broad rules, or unintended public fallback behavior exist.
- [ ] Bidirectional routes, accurate source IPs, and firewall/ACL rules for **UDP and TCP 53** cover NAT and large responses.
- [ ] Redundancy covers resolvers, on-prem DNS, and hybrid links proportionate to business criticality.
- [ ] TTLs and negative caching are sized and verified for record updates, scaling, and cutovers.
- [ ] DNS query logs, audits, IAM, record-edit permissions, and recursion limits comply with policy.
- [ ] Synthetic probes from the Internet, on-prem, and each key cloud network validate answers and latency.
- [ ] Runbooks distinguish **NXDOMAIN, SERVFAIL, REFUSED, timeouts, and post-resolution app failures**.
- [ ] DNS and link failure drills align with SLO/RTO; owners and rollback plans are established.
- [ ] Zone, endpoint, query, private-link, logging, and ops staffing costs are included in the architecture review.

**Takeaway:** Public DNS governs how Internet users find the application; internal DNS gives private services an access-controlled namespace; hybrid DNS bridges both worlds through **clear authority and intentional forwarding rules**. Strong designs start from zone ownership, query paths per location, and redundancy, then prove correctness with live network, DNS, and application tests. Decisions around TTLs, security, cloud resolvers, and hybrid links must be weighed alongside Well-Architected trade-offs in reliability, performance, cost, and operations.
