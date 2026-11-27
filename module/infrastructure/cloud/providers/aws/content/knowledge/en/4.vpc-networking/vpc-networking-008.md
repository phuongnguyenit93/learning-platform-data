# DNS in a VPC and DHCP Options

## Learning Objectives

After completing this lesson, you will be able to:

- Explain how EC2 instances, containers, and other workloads **resolve domain names** in an Amazon VPC; distinguish DNS resolution from actual network connectivity.
- Describe **AmazonProvidedDNS / Route 53 VPC Resolver**, special VPC DNS addresses, and the two attributes **enableDnsSupport** and **enableDnsHostnames**.
- Understand how a **DHCP option set** delivers DNS configuration, domain suffixes, NTP, and other parameters to instances; safely create, associate, swap, and verify option sets.
- Choose among **AWS default DNS**, **custom DNS servers**, **Route 53 private hosted zones**, and **Resolver inbound/outbound endpoints** for each scenario.
- Systematically diagnose DNS failures using the AWS CLI, OS tools, Route 53 Resolver query logs, and knowledge of VPCs, security groups, routes, and IAM.
- Evaluate the impact of DNS on secure applications, availability across multiple Availability Zones, monitoring, and cost.

This lesson belongs to the **VPC Networking** chapter of the **CLOUD_PROVIDERS_AWS** module. Across the AWS ecosystem—whether applications run on EC2, ECS, EKS, or Lambda and call S3, RDS, DynamoDB, or SQS—proper DNS resolution is routinely required for successful service connectivity. DNS supports address flexibility and recovery, but DNS **does not replace** network design, authorization, encryption, or backups.

## 1. What Role Does DNS Play in a VPC?

**Domain Name System (DNS)** translates human-friendly names into records needed for connectivity. For example, an application needs to reach `api.internal.example.com`; DNS may return the private IP address of an internal service. Only after receiving the IP address does the application open a TCP/UDP or HTTPS connection over the appropriate network path.

| Record | Common Purpose | Illustrative Example |
| --- | --- | --- |
| **A** | Domain name → IPv4 | `api.internal.example.com → 10.20.5.24` |
| **AAAA** | Domain name → IPv6 | `api.internal.example.com → 2001:db8::24` |
| **CNAME** | Alias from one name to another | `web.example.com → app.example.net` |
| **TXT** | Text data; commonly used for domain verification, SPF, etc. | `_verify.example.com` |
| **MX** | Mail server receiving email for a domain | `example.com` |
| **PTR** | Reverse IP → name mapping in reverse DNS | Corresponding reverse DNS record |

Certain features such as **Route 53 alias records** are Route 53–level capabilities rather than standalone standard DNS record types.

Three concepts appear along the query path:

1. **Stub resolver / DNS client:** component in the OS or application library that sends domain name queries.
2. **Recursive resolver:** server that receives queries and looks up/caches results. Inside a VPC, AWS provides **Route 53 VPC Resolver**.
3. **Authoritative DNS:** the source owning records for a DNS zone, such as a Route 53 hosted zone or enterprise DNS.

~~~mermaid
flowchart LR
    A[Application: api.internal.example.com] --> B[DNS client on EC2 / container]
    B --> C[Recursive DNS resolver]
    C --> D{Matching record / cache?}
    D -->|Yes| E[Return A / AAAA / CNAME...]
    D -->|Lookup needed| F[Authoritative DNS source]
    F --> E
    E --> G[Application opens connection to target IP]
~~~

**DNS success does not guarantee connection success.** A name can resolve accurately to a private IP while requests still time out due to route tables, security groups, NACLs, firewalls, endpoints, ports, or an unlistening application. Conversely, EC2 may reach an IP directly yet fail by hostname due to a broken DNS client/resolver.

## 2. AmazonProvidedDNS / Route 53 VPC Resolver

When you create a VPC, AWS provides **Route 53 VPC Resolver** (older common name: **Route 53 Resolver**, also called the **Amazon DNS server**). This is the built-in DNS resolver for resources in the VPC; you normally do not need to deploy your own DNS servers just to resolve EC2 names, AWS services, or public Internet names.

Addresses commonly used to reach the VPC Resolver:

| Address | Meaning |
| --- | --- |
| **Primary VPC IPv4 CIDR + 2** | For example, in VPC `10.20.0.0/16` the resolver is at `10.20.0.2`; derived from the VPC's **primary IPv4 CIDR** |
| **169.254.169.253** | Link-local IPv4 address reserved for AWS DNS |
| **fd00:ec2::253** | IPv6 address for AWS DNS in IPv6-capable contexts |

These addresses are different ways to reach the same VPC resolution capability, **not three independent self-managed DNS servers**. The `VPC+2` IPv4 address is scoped to that VPC; do not treat it as a public DNS server for Internet or on-premises hosts to query directly.

Example for VPC `10.20.0.0/16`:

~~~text
VPC CIDR:                    10.20.0.0/16
AmazonProvidedDNS:           10.20.0.2
Link-local DNS address:      169.254.169.253
IPv6 DNS address:            fd00:ec2::253
Example EC2 private IPv4:    10.20.10.34
~~~

The resolver can resolve:

- **Default EC2 DNS names** subject to VPC capabilities and DNS attributes.
- **Records in Route 53 private hosted zones** properly associated with the VPC.
- **Public domain names** via recursive lookup.
- **Other internal domain names** when configured with Resolver rules/forwarding or matching resolution settings.

**IPv6-only case:** Do not mechanically assume every instance receives DNS identically to standard IPv4. AWS has dedicated DHCP/link-local DNS mechanisms for IPv6-only subnets; inspect the actual resolver inside the OS.

### How Does AmazonProvidedDNS Differ from a Route 53 Public Hosted Zone?

| Component | Responsibility |
| --- | --- |
| **Route 53 VPC Resolver** | Receives DNS queries from VPC workloads; answers from VPC metadata, private hosted zones, cache, or recursive lookups |
| **Route 53 public hosted zone** | Stores authoritative records for public domains |
| **Route 53 private hosted zone** | Stores internal DNS records, resolved only within associated VPCs or via supported Resolver connectivity |
| **Route 53 Resolver inbound/outbound endpoint** | Bridges DNS query flows between a VPC and networks/DNS outside the VPC |
| **DHCP option set** | Tells hosts which DNS servers/domain and network parameters to use; **does not store** application A/CNAME records |

Using a Route 53 public hosted zone does not create private connectivity; using a private hosted zone does not connect networks between two VPCs. DNS and routing must be designed in parallel.

## 3. Two Key DNS Attributes of a VPC

Amazon VPC has two DNS-affecting attributes that are independent of the DHCP option set.

| Attribute | Primary Function | When to Care |
| --- | --- | --- |
| **enableDnsSupport** | Enables resolution via AWS-provided DNS for the VPC | Whenever using AmazonProvidedDNS/Route 53 VPC Resolver |
| **enableDnsHostnames** | Controls whether the VPC assigns public DNS hostnames to EC2 instances with public IPv4s under eligible conditions; also required alongside DNS support for certain internal DNS features | EC2 public DNS hostnames; Route 53 private hosted zones; private DNS for interface VPC endpoints |

**Rule to remember:** To use custom names from **Route 53 private hosted zones** and **private DNS on interface VPC endpoints**, **both** `enableDnsSupport=true` and `enableDnsHostnames=true` must be enabled.

VPC defaults can vary depending on how the VPC was created. For example, `enableDnsSupport` is typically enabled by default; `enableDnsHostnames` is typically disabled in custom-created VPCs and enabled in the default VPC. Always check the actual value rather than guessing.

Inspect via AWS CLI, replacing the VPC ID and Region with real values:

~~~bash
aws ec2 describe-vpc-attribute --vpc-id vpc-0123456789abcdef0 --attribute enableDnsSupport --region ap-southeast-1

aws ec2 describe-vpc-attribute --vpc-id vpc-0123456789abcdef0 --attribute enableDnsHostnames --region ap-southeast-1
~~~

The response structure looks like this (abbreviated):

~~~json
{
  "VpcId": "vpc-0123456789abcdef0",
  "EnableDnsSupport": { "Value": true }
}
~~~

To modify them, navigate to **VPC console → Your VPCs → select VPC → Actions → Edit VPC settings**, review, and enable the required attributes. In live systems, plan DNS changes carefully, prepare a rollback path, and monitor dependent applications.

### Example: Private DNS for Internal Services

Suppose private hosted zone `internal.example.com` is associated with VPC `vpc-app` and contains:

~~~text
api.internal.example.com.   A   10.20.10.24
db.internal.example.com.    CNAME   database-cluster.internal.example.net.
~~~

EC2 instances in the VPC using the VPC Resolver can query these names. However:

- The `api` record is useful only if its IP stays updated across the application lifecycle; for dynamic services, prefer DNS pointing to an internal ALB/NLB or appropriate resource rather than hardcoding private IPs.
- The `db` record must point to an actually resolvable DNS name; depending on the design, use the endpoint hostname provided by RDS/Aurora.
- Hosts outside the VPC cannot automatically resolve private hosted zones merely because a VPN or VPC peering exists. Zone associations and/or Resolver endpoints must be configured.

## 4. What Is a DHCP Option Set?

**DHCP (Dynamic Host Configuration Protocol)** delivers network parameters to hosts, such as leased IP addresses and DNS settings. In AWS, a **DHCP option set** is a network configuration attached to a VPC that controls values provided by the DHCP server to instances.

In a typical VPC:

~~~mermaid
sequenceDiagram
    participant I as EC2 instance / OS
    participant D as Amazon DHCP server
    participant R as DNS server
    I->>D: Request/renew DHCP lease
    D-->>I: IP & network parameters, DNS, domain, ...
    I->>R: DNS query to configured nameserver
    R-->>I: DNS answer
~~~

**Distinguish the two roles:** the DHCP option set tells the host **where to send DNS queries**; the DNS resolver answers **which address corresponds to a name**. Editing a DHCP option set does not create new records in Route 53 and does not automatically expose private hosted zones from another network.

### Important Fields

| Option | Meaning | Scenario |
| --- | --- | --- |
| **domain-name-servers** | List of DNS resolvers used by instances | `AmazonProvidedDNS` or internal/enterprise DNS IPs |
| **domain-name** | Domain name/suffix provided to the DHCP client | Using `corp.example.com` as a search suffix for short-name lookups |
| **ntp-servers** | Time synchronization servers | Aligning with enterprise time sync policies |
| **netbios-name-servers** | NetBIOS/WINS servers, primarily legacy Windows environments | Applications relying on NetBIOS name resolution |
| **netbios-node-type** | How Windows NetBIOS resolves names | Windows networks requiring NetBIOS |
| **ipv6-address-preferred-lease-time** | Preferred lifetime for IPv6 addresses assigned via DHCPv6 | Tuning DHCPv6 renewal frequency for workloads |

AWS provides a **default DHCP option set** per Region; by default, the DNS server is typically **AmazonProvidedDNS**. Custom DHCP option sets are used when custom DNS servers, domain suffixes, or additional policies are needed. One option set can be attached to multiple VPCs, but **each VPC has only one DHCP option set at a time**.

### Crucial Operational Rules

1. **A DHCP option set is immutable once created:** to change values, create a **new option set** and associate it with the VPC.
2. **Attaching a new option set does not require rebooting/relaunching all EC2 instances:** instances typically pick up changes upon DHCP lease renewal, which can take several hours or be renewed manually per OS.
3. **Changing the option set affects the entire VPC**, across all subnets/AZs. You cannot use option sets to assign a distinct DNS server per subnet as a standalone VPC DHCP setting.
4. **Do not arbitrarily test "No DHCP option set":** DHCP-supplied DNS may be disabled or behave differently depending on EC2 platform type; on some Nitro instances, link-local DNS may still be configured by default. Verify OS and actual instance behavior.
5. **Do not confuse with `enableDnsSupport` and `enableDnsHostnames`:** these are VPC attributes, not keys inside a DHCP option set.

### Can You Mix AmazonProvidedDNS and Custom DNS?

AWS allows declaring certain combinations of DNS servers in an option set, but **mixing `AmazonProvidedDNS` with custom DNS servers can produce unpredictable behavior** because clients fail over among nameservers unpredictably. Listed DNS servers do not necessarily know the same zones.

**Deployment recommendations:**

- For predominantly AWS workloads, prefer pointing clients to **AmazonProvidedDNS** and adding **Resolver forwarding rules** for specific domains as needed.
- If the enterprise mandates custom DNS, configure the custom DNS servers to resolve or **conditionally forward** required AWS/private domains via a supported Resolver architecture.
- Mix multiple resolvers only when you thoroughly understand client behavior, failover mechanics, split-horizon DNS, and have tested it.

## 5. Choosing a DNS Pattern by Problem

| Requirement | Starting Configuration to Evaluate | Rationale |
| --- | --- | --- |
| EC2/ECS/Lambda in one VPC calling AWS services and Internet | AmazonProvidedDNS with required VPC attributes enabled | Low operational overhead; resolves VPC and public names |
| Internal name `api.internal.example.com` | Route 53 private hosted zone + VPC association | Manage internal DNS records natively in AWS |
| EC2 needs to resolve `corp.example.com` managed by on-prem DNS | VPC Resolver outbound endpoint + forwarding rule | Forwards only that domain to enterprise DNS |
| Office hosts need to resolve names in an AWS private hosted zone | VPC Resolver inbound endpoint + on-prem conditional forwarder | Provides a supported query target over private connectivity |
| App requires Active Directory / enterprise DNS | DHCP option set pointing to custom DNS, plus conditional forwarding for AWS names | Preserves domain services and distributed namespace management |
| Need to audit DNS queries per VPC | Route 53 VPC Resolver query logging | Captures query source, queried name, and response for troubleshooting |
| Need to filter malicious domains through VPC Resolver | Route 53 Resolver DNS Firewall | Enforces domain rules and tracks alerts/blocks |

Not every scenario needs inbound/outbound endpoints. Those endpoints carry dedicated networking, security, and cost considerations. A simple system using AmazonProvidedDNS and private hosted zones may be sufficient.

## 6. Hands-On: Reading and Changing DHCP Option Sets

> **Lab environment:** Use a dedicated authorized test VPC. The IDs `vpc-0123456789abcdef0`, `dopt-0123456789abcdef0`, `10.20.x.x` addresses, and `example.com` domain below are illustrative; substitute real values. Never change a production VPC's option set without evaluating DNS dependencies across the entire VPC.

### Step 1 — Check Which DHCP Option Set the VPC Uses

~~~bash
aws ec2 describe-vpcs \
  --vpc-ids vpc-0123456789abcdef0 \
  --query 'Vpcs[0].{VpcId:VpcId,Cidr:CidrBlock,DhcpOptionsId:DhcpOptionsId}' \
  --region ap-southeast-1
~~~

Record the current **DhcpOptionsId** so you can roll back if testing fails.

### Step 2 — Inspect the Configured Options

~~~bash
aws ec2 describe-dhcp-options \
  --dhcp-options-ids dopt-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Inspect `domain-name`, `domain-name-servers`, `ntp-servers`, and other fields. If using the default configuration, the DNS server entry may be `AmazonProvidedDNS`. Do not assume custom DNS IPs are required for a valid setup.

### Step 3 — Create a New Option Set with Internal DNS (When Needed for a Lab)

Suppose operations manages DNS servers `10.20.10.10` and `10.20.20.10` placed in different AZs; execute this only if those two DNS servers **already exist and are reachable** from clients:

~~~bash
aws ec2 create-dhcp-options \
  --dhcp-configurations \
    Key=domain-name,Values=corp.example.com \
    Key=domain-name-servers,Values=10.20.10.10,10.20.20.10 \
  --region ap-southeast-1
~~~

This returns the new DHCP option set ID. Note: **without valid DNS servers at those example addresses, this configuration will break name resolution** for clients receiving it. If focusing on default DNS, simply inspect the existing option set instead of running mutating commands.

### Step 4 — Associate with the Test VPC

~~~bash
aws ec2 associate-dhcp-options \
  --dhcp-options-id dopt-0newexample12345 \
  --vpc-id vpc-0123456789abcdef0 \
  --region ap-southeast-1
~~~

The ID `dopt-0newexample12345` is a placeholder, **not** a valid ID to run literally. After associating, re-read the VPC and option set, then check the DNS client inside EC2. In practice, changing the DHCP option set affects all instances in the VPC once they renew their DHCP lease. Depending on the OS, you can manually renew the lease to test immediately, weighing impact on active connections.

### Step 5 — Restore the Previous Option Set After the Lab

Re-associate the **DhcpOptionsId saved from Step 1** to roll back. Once no VPC uses the test option set, delete it following your lab resource cleanup procedures. You cannot delete a DHCP option set currently associated with a VPC.

## 7. Checking DNS Inside EC2: Linux and Windows

After inspecting AWS state, verify **what configuration the OS is actually using**. Fresh DHCP leases and OS caches/`systemd-resolved` can produce results different from expected settings.

### Linux

~~~bash
# Check active nameserver config; resolv.conf may be managed by systemd-resolved
cat /etc/resolv.conf

# On systems using systemd-resolved
resolvectl status

# Test domain name using default OS DNS client
getent hosts api.internal.example.com

# Query AmazonProvidedDNS directly
dig @169.254.169.253 api.internal.example.com A

# Compare with internal DNS if configured and reachable
dig @10.20.10.10 api.internal.example.com A
~~~

**Note:** `dig @...` tests a specific DNS server; results may differ from queries sent through the OS's default resolver. `/etc/resolv.conf` sometimes points only to a local stub such as `127.0.0.53`; check `resolvectl status` to see the real upstream servers. In container environments, DNS queries may pass through a runtime/cluster DNS proxy before reaching the VPC Resolver.

### Windows PowerShell

~~~powershell
Get-DnsClientServerAddress
ipconfig /all
Resolve-DnsName -Name api.internal.example.com
Resolve-DnsName -Name api.internal.example.com -Server 169.254.169.253
~~~

Compare results from the default resolver and AmazonProvidedDNS. If a Windows host is domain-joined to Active Directory, also inspect the DNS client domain suffix and domain controller DNS servers, as internal lookups often follow domain-specific rules.

### Interpreting DNS Outputs

| Signal | Possible Meaning | Next Step |
| --- | --- | --- |
| Expected A/AAAA returned | DNS answered successfully | Check TCP/HTTP, routes, security groups, TLS, and target service if the app still fails |
| **NXDOMAIN** | Resolver reports the name does not exist in the answering scope | Check zone/record, FQDN, VPC association, split-horizon, and forwarding rules |
| **SERVFAIL** | Resolver could not complete the query | Check upstream DNS, forwarders, DNSSEC/timeout errors, and logs |
| **Timeout** | No response received in time | Check DNS IP, routing, SG/NACL for custom DNS, DNS service, endpoints, and hybrid links |
| **Wrong / stale IP returned** | Record/target differs from expectation, cached, or forwarded to another zone | Check authoritative source, TTL, OS/resolver caches, and zone selection rules |
| **Intermittent failures** | Inconsistent upstream DNS or uneven node/AZ/DNS configs | Test per server, across multiple instances, across AZs, and under high load |

Avoid relying solely on `ping`: DNS may resolve properly while ICMP is blocked. For HTTPS services, test with `curl` or an application-level tool once name and address are confirmed.

## 8. DNS for Hybrid Environments: Inbound and Outbound Resolvers

An enterprise may simultaneously run:

- A VPC running AWS applications with zone `aws.corp.example.com`;
- An office/on-premises network with its own authoritative DNS for `corp.example.com`;
- Private network connectivity via **Site-to-Site VPN** or **Direct Connect**.

**Requirement 1:** EC2 instances in the VPC need to query `db.corp.example.com`, managed by on-premises DNS.

**Requirement 2:** On-premises hosts need to query `api.aws.corp.example.com`, managed by a Route 53 private hosted zone.

~~~mermaid
flowchart TB
    subgraph AWS["AWS Region / VPC"]
      App[EC2 / ECS / Lambda] --> RV[Route 53 VPC Resolver]
      RV --> PHZ[Private hosted zone: aws.corp.example.com]
      RV --> Rule[Forwarding rule: corp.example.com]
      Rule --> OE[Resolver outbound endpoint]
      IE[Resolver inbound endpoint] --> RV
    end
    subgraph OnPrem["Enterprise Network"]
      Client[On-premises client] --> DN[Enterprise DNS]
      DNS[Authoritative DNS: corp.example.com] --- DN
    end
    OE -->|Queries to enterprise DNS| DN
    DN -->|Forward aws.corp.example.com| IE
~~~

The diagram depicts only **logical DNS flows**; in production you also need private network connectivity, bidirectional routes, and security groups on the endpoints.

### Outbound: AWS Querying External Network DNS

1. Create a **Route 53 VPC Resolver outbound endpoint** in an appropriate VPC, typically with endpoint IPs spanning at least two AZs.
2. Allow the endpoint to reach target DNS servers on the DNS ports used (typically **UDP/TCP 53**) over a valid network path.
3. Create a **Resolver forwarding rule** for the specific domain, e.g., `corp.example.com`, targeting the destination DNS IPs.
4. **Associate the rule** with VPCs whose workloads need it.
5. Keep EC2 instances using **AmazonProvidedDNS** where appropriate: VPC Resolver forwards queries for that domain per the rule, avoiding changing every instance's DHCP option set to on-premises IPs.

### Inbound: External Networks Querying AWS DNS

1. Create a **Resolver inbound endpoint**, choosing subnets/IPs, AZ distribution, and security groups.
2. Configure on-premises DNS with a **conditional forwarder** for `aws.corp.example.com` pointing to the **inbound endpoint IPs**.
3. Ensure the VPC hosting the inbound endpoint is associated with the right private hosted zones or has required resolver rules.
4. Verify VPN/Direct Connect connectivity, routes, NACLs, SGs, and forwarders on both sides.

**Important:** Never forward directly from on-premises DNS or another VPC's DNS to the **VPC CIDR + 2** address (e.g., `10.20.0.2`); that is not supported across network boundaries. Use a **Resolver inbound endpoint** for inbound queries into a VPC.

### Avoiding DNS Forwarding Loops

Incorrect setup: VPC Resolver forwards `corp.example.com` to on-premises DNS; on-premises DNS forwards `corp.example.com` right back into the VPC Resolver. Queries loop until timeout or SERVFAIL.

The fix is cleanly separating **which DNS is authoritative for each zone** and writing **one-way conditional forwarding rules** per namespace slice, for example:

- `corp.example.com`: on-premises authoritative;
- `aws.corp.example.com`: Route 53 private hosted zone authoritative;
- VPC forwards `corp.example.com` to on-premises while resolving `aws.corp.example.com` locally per specificity/rule precedence;
- On-premises forwards only `aws.corp.example.com` to the inbound endpoint.

When multiple private hosted zones and Resolver rules overlap or nest domains, verify **precedence and domain-specificity rules** in current AWS documentation; never guess evaluation order from rule names.

## 9. Custom DHCP DNS and Active Directory

Certain Windows/Active Directory workloads require domain controllers or centralized DNS servers rather than AmazonProvidedDNS alone.

**Sample design:**

1. EC2 instances in the VPC receive DNS servers `10.20.10.10` and `10.20.20.10` via a DHCP option set.
2. Those two DNS servers resolve the organization's domain, e.g., `ad.corp.example.com`.
3. For AWS private hosted zones, custom DNS servers use conditional forwarding to a supported Route 53 Resolver path (e.g., an inbound endpoint if crossing VPC boundaries).
4. Ensure DNS servers are available across multiple AZs, health-monitored, and resilient if one server becomes unreachable.

**Do not confuse DNS with domain join:** Supplying a domain suffix in DHCP does not join AD, create SRV records, or grant resource permissions. AD join requires proper DNS, network connectivity, time sync, identity, and dedicated policies.

If using AWS Managed Microsoft AD or other Active Directory integrations, follow DNS forwarding and DHCP option set guidance specific to **that directory type**. Avoid generic configurations without testing SRV/Kerberos records.

## 10. DNS and Multi-AZ Availability Design

A VPC spans a Region and can hold subnets in multiple Availability Zones. The built-in VPC Resolver is managed by AWS, yet **the DNS path used by your application** can still have points of failure:

| Component | Risk | Mitigation |
| --- | --- | --- |
| AmazonProvidedDNS | Link-local/DNS throughput limits or misconfigured VPC settings | Optimize caching, measure query rates, enable proper DNS attributes |
| Custom DNS on a single EC2 | Instance or AZ failure | Run multiple DNS servers across AZs, monitor, test failover |
| Resolver endpoint | Single endpoint IP/ENI or network path failure | Provision endpoint with multiple IPs across AZs, valid SGs and routes |
| Forwarding rule | Domain mismatch or pointing to wrong upstream | Verify namespaces, rule precedence, monitor errors |
| Private hosted zone | VPC not associated or stale/wrong record | Manage DNS via IaC, review changes, validate from target VPCs |
| DNS client/cache | Stale results until TTL expiry; inconsistent caching | Choose TTLs suited to failover needs; establish cache verification steps |
| Hostname-dependent app | DNS succeeds, yet destination is down | Health checks, autoscaling, ALB/NLB, DB failover, and proper retries |

AWS enforces rate limits on shared link-local services per instance, including DNS, IMDS, and NTP. An application issuing an uncached DNS lookup on every single request can throttle itself. Use connection pooling and sensible DNS caching while ensuring caches do not block endpoint switching during failover.

**TTL (time to live)** governs how long clients may reuse cached records, but it does not guarantee every client switches to a new IP at an exact instant. Application failover design must also address timeouts, retries, connection pools, circuit breakers, health checks, and database state. DNS does not solve data RPO/RTO.

## 11. Security: DNS Is Helpful, Not a Firewall

DNS contributes to secure network operations:

- **Private hosted zones** limit internal name resolution scope, though they do not encrypt data or authorize service access.
- **IAM** restricts who can alter VPC settings, DHCP option sets, Resolver rules, hosted zones, and query logging. Workloads still need appropriate IAM roles to call AWS APIs.
- **AWS Route 53 Resolver DNS Firewall** inspects/filters domains queried through VPC Resolver, but does not inspect arbitrary application protocols or replace security groups/AWS WAF.
- **Route 53 Resolver query logging** aids auditing of DNS queries, sources, responses, and firewall events; logs can expose sensitive internal hostnames, so restrict access and set retention policies.
- **TLS/HTTPS** protects connections to destinations; DNS results do not replace certificate validation, authentication, or authorization.

**Note on security groups/NACLs:** AWS does not let you filter traffic **to/from the Amazon DNS server** with security groups or network ACLs in the usual way. However, when using **custom DNS servers** or **Resolver endpoints** that place ENIs in subnets, routes, security groups, and NACLs matter greatly. Avoid thinking that opening UDP 53 in an EC2 security group always fixes AmazonProvidedDNS errors.

### Commonly Overlooked Costs

- VPC Resolver is included for basic VPC queries; add-on features such as **Resolver inbound/outbound endpoints**, **DNS Firewall**, and **query logging/log destinations** incur separate charges.
- Endpoints typically need multiple IPs/ENIs for high availability; billing depends on endpoint configuration and query volume per pricing schedules.
- Self-managed DNS servers on EC2 also carry instance, EBS, security patching, operations, and monitoring costs.
- Hybrid DNS queries add connectivity, data transfer, and network management costs.
- For Route 53 hosted zones and billable query types, check current service pricing tables.

Validate using the **AWS Pricing Calculator**, **AWS Cost Explorer**, and **AWS Budgets**; tag resources to separate lab, dev, and production environments. Never pick a custom DNS server just from EC2 hourly pricing while ignoring operational labor.

## 12. Common DNS Troubleshooting Table

| Symptom | Likely Cause | Ordered Investigation |
| --- | --- | --- |
| Host resolves Internet names but cannot see private hosted zone records | VPC DNS attributes, zone not associated, or host uses custom DNS without proper forwarding | Check VPC attributes → DHCP DNS → VPC association/records → custom forwarders |
| `dig @169.254.169.253` succeeds, yet the app reports NXDOMAIN | OS/container queries a different DNS server or uses search suffixes/cache | Inspect `resolvectl`/DNS policies; query exact FQDN against each nameserver |
| After changing DHCP option set, some EC2 instances still use old DNS | DHCP lease not renewed or OS manages DNS statically | Check OS config, perform controlled lease renewal, verify across AZs |
| On-premises DNS cannot resolve private hosted zone names | Missing inbound endpoint, wrong forward rule, or missing network path | Test inbound endpoint DNS IPs over VPN/DX, UDP/TCP port 53, zone association |
| EC2 cannot resolve AD/internal corporate domain | Wrong DNS server selected; missing outbound rule/endpoint; corporate DNS unresponsive | Compare queries against AmazonProvidedDNS vs. custom servers; trace forwarding flow |
| Name resolves to right IP, yet HTTPS times out | Routes, SG, NACL, endpoint, application, or firewall | Test TCP/HTTPS to IP/FQDN; inspect Flow Logs and service logs |
| Intermittent SERVFAIL responses | Unstable upstream DNS, forwarding loop, unhealthy endpoint, overload, or quota | Inspect resolver query logs, test each server, verify retries/TTL and topology |
| Private DNS on an interface endpoint fails | VPC DNS attributes, endpoint private DNS setting, SG/NACL | Check `enableDnsSupport`, `enableDnsHostnames`, endpoint state, and DNS |
| DNS updated to new IP, yet clients still hit old target | Cache TTL, connection pooling, application pinning IPs | Check actual TTL, OS/runtime caches, connection reuse |
| Custom DNS works in only one AZ | Single point of failure in DNS server/routing/endpoint IP | Test from each AZ against each nameserver; measure recovery time |

**Suggested diagnostic workflow:**

~~~text
1. Confirm the queried name and expected record type (A/AAAA/CNAME/SRV...).
2. Confirm the client's VPC, subnet, DNS attributes, and DHCP option set.
3. Inspect the actual DNS server configured inside the OS/container.
4. Query each DNS server directly to isolate client vs. upstream issues.
5. For private zones: verify zone/record, VPC association, and resolver rules.
6. For hybrid/custom DNS: check inbound/outbound endpoints, UDP/TCP 53,
   VPN/Direct Connect, SGs/NACLs/routes, and rule out forwarding loops.
7. If DNS answers accurately: move to TCP/TLS, IAM, and application checks.
8. Enable query logging, measure errors/latency, verify across multiple AZs;
   change configuration only after isolating the failing layer.
~~~

### Where Can You Find DNS Query Logs?

In **Route 53 VPC Resolver → Query logging**, create a logging configuration and associate it with the target VPC. Depending on your choice, logs can be delivered to **CloudWatch Logs**, **Amazon S3**, or supported delivery streams. Each record can include VPC, source IP/instance, queried name, record type, response code, and answers.

**Caveat to understand:** Resolver caches responses. When a query is served from cache, it may not generate a new query log entry. Thus, "no log entry for the second lookup" does not mean the application stopped issuing queries.

## 13. Architecture Selection Examples

### Scenario A — New Website Using Only AWS Services

**Requirements:** API on ECS/Fargate calling RDS, S3, and SQS; deployed across multiple AZs; small team wanting minimal ops.

**Recommendation:**

- Use **AmazonProvidedDNS** and enable both VPC DNS attributes when private names/private hosted zones are needed.
- Have the API use the **RDS endpoint hostname**, standard S3/SQS endpoints, and private endpoints if applicable.
- For an internal API hostname, create a **Route 53 private hosted zone** with a record pointing to an **internal ALB**.
- Monitor DNS errors and request latency; maintain IAM, SGs, backups, and budgets per requirements.

**Why:** There is no need to operate two DNS servers merely to resolve AWS service names. RDS endpoint DNS handles address updates during failover; applications should honor DNS TTLs and manage connection pools properly.

### Scenario B — EC2 Requiring Enterprise Active Directory

**Requirements:** Windows EC2 instances in a VPC must resolve `ad.corp.example.com`, Domain Controller SRV records, and several AWS private hosted zones.

**Recommendation:**

- Consider a DHCP option set pointing to dedicated domain controller DNS servers distributed across AZs/network segments per design.
- Use appropriate conditional forwarding for AWS/private names. If custom DNS sits outside the VPC, use a **Resolver inbound endpoint** to query the VPC Resolver.
- Verify VPN/DX, DNS ports, time sync, and AD prerequisites; test logins when one DNS server is stopped.

**Why:** AD requires authoritative DNS for its domain; standalone AmazonProvidedDNS cannot replace AD records.

### Scenario C — Multiple AWS Accounts and One Data Center

**Requirements:** Each team has its own VPC/account sharing an internal domain while still needing to query hostnames in the on-premises data center.

**Recommendation:**

- Design a **DNS hub / shared services VPC** with centrally managed Resolver endpoints.
- Share Resolver rules to participating VPCs using appropriate multi-account governance mechanisms (e.g., AWS Resource Access Manager where supported).
- Associate private hosted zones with the proper VPCs, defining record ownership and update workflows clearly.
- Prevent forwarding loops between the hub and on-premises DNS; control endpoint access, query logs, and costs.

**Why:** Managing DNS by namespace and shared rules reduces per-VPC duplication across dozens of VPCs, though it requires stricter change control.

## 14. Checklist for Deploying VPC DNS/DHCP

- [ ] Confirmed **Region, VPC ID, primary CIDR**, and domains requiring resolution.
- [ ] Checked `enableDnsSupport` and `enableDnsHostnames` against private hosted zone / interface endpoint requirements.
- [ ] Read **DhcpOptionsId** and actual DNS client configuration inside the OS/container.
- [ ] Chose AmazonProvidedDNS or custom DNS with clear rationale, avoiding arbitrary resolver mixing.
- [ ] For private hosted zones: valid records, accurate **VPC association**, and managed record update sources.
- [ ] For hybrid setups: tested inbound/outbound endpoints, forwarding rules, target DNS servers, routes, and UDP/TCP 53.
- [ ] For custom DNS: deployed redundantly across AZs, monitored, and tested single-DNS-server failure.
- [ ] Distinguished **DNS resolution** errors from post-resolution **TCP/TLS/SG/NACL/route/IAM** errors.
- [ ] Reviewed query logging/DNS Firewall policies, IAM permissions, log security, and TTLs.
- [ ] Prepared a rollback path when changing DHCP option sets and recorded the prior configuration ID.
- [ ] Tested failover behavior, cache TTLs, connection pooling, and real RTO impact.
- [ ] Estimated costs for Resolver endpoints, logs, and self-managed DNS servers, and configured budget alerts.

## 15. Hands-On Exercises and Self-Check Questions

### Exercise 1 — Inspecting a Running VPC Configuration

Without modifying resources:

1. Use the AWS CLI to inspect `enableDnsSupport`, `enableDnsHostnames`, and `DhcpOptionsId`.
2. Read the DNS servers from the DHCP option set and check DNS client settings on a lab EC2 instance.
3. Explain why `10.20.0.2` and `169.254.169.253` can both act as resolver addresses inside VPC `10.20.0.0/16`.
4. Compare `dig @169.254.169.253 example.com` with `dig example.com`.
5. Record which layer is an **AWS VPC setting**, which is a **DHCP option**, and which is **DNS client/OS**.

### Exercise 2 — Designing Private DNS

**Prompt:** Applications across two AZs need to reach `orders.internal.example.com`, backed by an internal ALB.

Minimum design:

- VPC attributes to enable;
- Private hosted zone and VPC association;
- Record type and target pointing to the ALB;
- DNS server configuration used by EC2/ECS clients;
- Verification steps from two subnets, including SG, route, and HTTPS checks.

**Explanation required:** Why should the ALB's DNS name be used instead of an arbitrary task/instance private IP?

### Exercise 3 — Designing Hybrid DNS

On-premises manages `corp.example.com`, while `aws.corp.example.com` lives in a Route 53 private hosted zone. EC2 instances in the VPC and office hosts need to resolve each other's names.

Draw a diagram covering:

- On-premises DNS and Route 53 VPC Resolver;
- Inbound endpoint and outbound endpoint;
- Forwarding rules and target domains;
- VPN/Direct Connect connectivity;
- Nameserver selection via DHCP option set;
- How to prevent query loops and maintain availability if one endpoint IP fails.

### Self-Check Questions

1. **Why cannot a private hosted zone in VPC A be resolved automatically from a peered VPC B?**  
   Because **DNS zone association or Resolver configuration** is separate from network peering. Peering provides packet routing paths without automatically sharing every DNS zone.

2. **Does enabling `enableDnsSupport` automatically create a DNS record for your application?**  
   No. This attribute controls whether resolution via AmazonProvidedDNS is enabled; records must be created and managed in an appropriate authoritative source.

3. **If you change the DHCP option set today, do all EC2 instances switch nameservers immediately?**  
   Do not assume so. Hosts pick up new configuration when leases update or renew; OS caches and local settings can also affect timing.

4. **Why might `dig @169.254.169.253` return the right IP while `curl https://api...` still fails?**  
   After DNS resolution, requests still depend on routes, SGs/NACLs, TCP/TLS, the application, certificates, IAM, or service policies.

5. **When is a custom DNS server needed?**  
   When there are explicit requirements like AD, enterprise DNS namespaces, or specialized resolution policies. For many straightforward AWS workloads, AmazonProvidedDNS and Resolver rules require far less operational effort.

## 16. Conclusion

In an AWS VPC, **Route 53 VPC Resolver / AmazonProvidedDNS** is the foundation for DNS resolution; the **two VPC DNS attributes** govern resolution and hostname assignment capabilities; and the **DHCP option set** directs hosts to the DNS servers and domain suffix to use. For internal names, use a **private hosted zone** with proper VPC associations. For cross-boundary VPC–on-premises resolution, add **Resolver inbound/outbound endpoints and conditional forwarding rules** alongside working network paths.

When designing secure, observable, resilient, and cost-controlled AWS applications, evaluate DNS **alongside** Region/AZ, IAM, VPC routing, security groups, database failover, logging, and budgets. A sound DNS design has clear authoritative sources, zero forwarding loops, minimal single points of failure, a rollback path, and verification from real clients.

### Official AWS Documentation

- [Understanding Amazon DNS — Amazon VPC](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html)
- [DNS attributes for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns-updating.html)
- [DHCP option set concepts](https://docs.aws.amazon.com/vpc/latest/userguide/DHCPOptionSetConcepts.html)
- [Work with DHCP option sets](https://docs.aws.amazon.com/vpc/latest/userguide/DHCPOptionSet.html)
- [What is Route 53 VPC Resolver?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver.html)
- [Resolving DNS queries between VPCs and your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-DSN-queries-to-vpc.html)
- [Resolver query logging](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-query-logs.html)
- [Route 53 Resolver DNS Firewall](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-overview.html)

Service capabilities, quotas, and pricing are subject to change; when deploying, cross-check current AWS documentation and your target Region.
