# Route 53 Hosted Zones and DNS Record Management

When a user opens `https://www.example.com`, the application does not receive that domain name directly: first, the **DNS (Domain Name System)** must answer which IP address or target name the domain points to. On AWS, **Amazon Route 53** provides authoritative DNS (*authoritative DNS*), domain registration, endpoint health checking, and mechanisms to select DNS answers according to routing policies. At the heart of DNS management is the **hosted zone**: a collection of records for a domain and the subdomains for which the zone has authority.

This lesson belongs to the **DNS and Content Delivery** chapter of the **CLOUD_PROVIDERS_AWS** module. By mastering hosted zones and DNS records, learners can point a domain to an Application Load Balancer for a Java/Spring Boot application on EC2/ECS/EKS, serve a static website through CloudFront and S3, assign internal names for services inside a VPC, integrate Route 53 with IAM/ACM, design failover and monitoring, and control the number of hosted zones, queries, and related charges.

> **Principle:** Creating a record in Route 53 is not enough for the Internet to use that record. For a **public hosted zone**, the domain must be **delegated** to the correct authoritative name servers; for a **private hosted zone**, the VPC/Resolver must be configured to see the zone. DNS selects the target to connect to; DNS **does not automatically open ports, grant permissions, or guarantee that the application is healthy**.

## 1. Learning Outcomes

After this lesson, learners will be able to:

1. Distinguish between **registrar**, **domain registration**, **public/private hosted zone**, authoritative name server, and **recursive resolver**.
2. Explain `NS`, `SOA`, `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `CAA`, and Route 53 **alias** records.
3. Create a proper name server change/delegation plan when migrating DNS to Route 53; understand why multiple zones with the same name do not mean all of them are being used by the Internet.
4. Design records pointing a domain to an ALB, CloudFront, or an application endpoint; choose **alias** instead of `CNAME` at the zone apex.
5. Explain TTL, caching, negative caching, `PENDING → INSYNC` changes, and low-disruption DNS rollout practices.
6. Describe private hosted zones, VPC association, split-view DNS, and Route 53 Resolver requirements.
7. Read/inspect hosted zones and record sets via the Console, AWS CLI, and `dig`/`nslookup`; understand change batch structure.
8. Distinguish routing policies, health checks, IAM, DNSSEC, and DNS costs to make sound operational decisions.

## 2. How Does DNS Work Before an Application Receives a Request?

DNS typically consists of the following roles:

| Component | Function |
|---|---|
| **Stub resolver** on the user's machine | Queries the DNS resolver configured in the OS/browser |
| **Recursive resolver** | Looks up and caches results, such as an ISP/corporate resolver or Route 53 Resolver inside a VPC |
| **Root/TLD name servers** | Directs to the domain's authoritative name servers based on delegation |
| **Authoritative name servers** | Answers records according to zone configuration; Route 53 serves this role for a properly delegated public hosted zone |
| **Client and backend** | Only after DNS resolution does the client open an HTTPS/TCP connection to the target; the load balancer/CDN handles the subsequent request |

~~~mermaid
sequenceDiagram
    participant U as User's Browser
    participant R as Recursive DNS resolver
    participant P as Root / TLD and delegation
    participant Z as Route 53 authoritative DNS
    participant E as CloudFront / ALB / Endpoint
    U->>R: Query A/AAAA www.example.com
    alt Cache valid
        R-->>U: Cached record
    else Cache miss
        R->>P: Find name servers for example.com
        P-->>R: NS delegation
        R->>Z: Query record www.example.com
        Z-->>R: A/AAAA/CNAME per configuration
        R-->>U: Result and TTL
    end
    U->>E: HTTPS connection per DNS answer
    E-->>U: HTTP response
~~~

The diagram simplifies the actual process: a recursive resolver may cache NS records, follow multiple CNAMEs, use EDNS Client Subnet, and apply other policies. The key point is that **Route 53 answers DNS**, while **CloudFront**, **ALB**, **EC2**, or the application receives the HTTP/TCP traffic.

### 2.1. Java Application Example

A Spring Boot service running on ECS behind an ALB has an AWS-assigned DNS name such as `my-api-123.ap-southeast-1.elb.amazonaws.com`. The product team wants customers to access `api.example.com`. They create a Route 53 record `api.example.com` as an **alias A** record pointing to the ALB; after DNS is resolved, the client connects to the ALB over HTTPS, and the ALB selects an ECS target based on target group health checks.

Route 53 does not receive the `/orders` REST request, does not read JWTs, and does not automatically attach a Security Group to the ALB. Those responsibilities belong to the application/load balancer/IAM/network layers respectively.

## 3. Domain Registration, Hosted Zone, and DNS Delegation

Three concepts are often lumped together as "buying a domain on Route 53," but they are three distinct parts.

- **Domain registration:** records the right to use `example.com` through a registrar and registry/TLD, renewed periodically. A domain can be registered with Route 53 or another registrar.
- **Hosted zone:** a collection of DNS records managed by Route 53 for `example.com` or a subdomain. A zone has a **hosted zone ID** like `Z...`; creating a zone can incur charges even when no one queries it.
- **Delegation:** the parent DNS zone/registrar points to the **name servers** of the hosted zone responsible for answering.

Creating an `example.com` public hosted zone usually auto-generates **NS** and **SOA** records. Route 53 provides a set of four name servers. For a registered domain to work through this zone, the registrar/TLD must be configured to use **the exact four NS** of **the exact zone**. Owning a zone whose name matches the domain **does not automatically change NS at the registrar**.

### 3.1. Distinguishing Two Sets of NS

Suppose Route 53 assigns illustrative name servers:

~~~text
ns-100.awsdns-10.com.
ns-200.awsdns-20.net.
ns-300.awsdns-30.org.
ns-400.awsdns-40.co.uk.
~~~

These are **illustrative names only**, not a list you can use to configure a real domain.

There are two places to check:

1. **NS record inside the hosted zone**: Route 53 creates this to publish the zone's authoritative NS.
2. **Domain delegation at the parent/TLD via the registrar**: tells recursive resolvers which name servers to query when resolving `example.com`.

If the NS set at the registrar still points to the old DNS provider, the Internet continues using that provider's records. You can create `api.example.com` in Route 53 all day and external Internet users will still not see it.

### 3.2. What If There Are Multiple Hosted Zones with the Same Name?

AWS allows creating multiple public hosted zones named `example.com`, each with its **own hosted zone ID and NS set**. The domain is only delegated to the NS actually configured at the parent. Route 53 **does not automatically merge** records from zones with the same name.

This is an easy mistake to make when dev/staging/production environments or IaC create a new zone and then update records in the wrong zone ID. Always verify the **hosted zone ID**, **record sets**, and **currently delegated NS** before making production changes.

## 4. Public Hosted Zone vs. Private Hosted Zone

| Attribute | **Public hosted zone** | **Private hosted zone (PHZ)** |
|---|---|---|
| Lookup audience | Internet via authoritative DNS delegation | Resolver for associated VPCs and eligible integrated DNS paths |
| Scope | Public domains and subdomains | Private DNS namespace for internal systems |
| Needs NS at registrar? | **Yes** for Internet domain queries to reach the right zone | **No** for a VPC to resolve the PHZ internally; requires VPC association |
| VPC association | Not required | Yes; cross-account requires an association authorization mechanism |
| DNS records | Websites, email, domain validation, public APIs | Internal service names, private ALB, appropriate RDS endpoint aliases |
| Application permissions | DNS does not replace TLS/SG/IAM | DNS does not replace routes/VPC security/auth |
| DNSSEC signing | Supported by Route 53 per public zone conditions | **Direct signing on a PHZ is not supported** |
| Primary use cases | `www.example.com`, `api.example.com` for customers | `db.internal.example.com`, `service.corp.example.com` for workloads |

### 4.1. A Public Hosted Zone Does Not Mean the Backend Must Be Public

A public zone can contain records for a **CloudFront distribution**, an internet-facing ALB, or other endpoints. Creating a public record `api.example.com` pointing to a private IP does not make that IP reachable from the Internet, because VPC routing/security still blocks it by design. Publishing DNS records can also expose unnecessary naming/metadata; avoid putting sensitive resource names in a public zone.

### 4.2. Private Hosted Zones Require VPC DNS Settings

To use a PHZ with associated VPCs, ensure the VPC attributes are set:

~~~text
enableDnsSupport   = true
enableDnsHostnames = true
~~~

Inside the VPC, **Route 53 Resolver / AmazonProvidedDNS** resolves records in the associated PHZ. Records existing in a PHZ **are not automatically shared with every peered VPC or VPC connected via Transit Gateway**. If you want VPC B to also use VPC A's internal names, you must design a PHZ association for B or an appropriate forwarding/Resolver setup, along with actual network connectivity to the private endpoint.

For hosts in an on-premises network over VPN/Direct Connect, resolving private hostnames may require **Route 53 Resolver inbound endpoints** and DNS forwarding rules; a physical/VPN network connection alone does not automatically let on-prem DNS know about private records.

### 4.3. Split-View / Split-Horizon DNS

An organization can use **two hosted zones with the same name** `example.com`:

- Public zone: `api.example.com` → public ALB/CloudFront.
- Private zone: `api.example.com` → internal ALB/private IP for workloads inside the VPC.

~~~mermaid
flowchart TD
    D["Query api.example.com"]
    D --> I{"Where is the resolver?"}
    I -->|"Internet"| P["Public hosted zone"]
    I -->|"VPC with PHZ association"| Q["Private hosted zone"]
    P --> W["CloudFront / Public ALB"]
    Q --> V["Internal ALB / private endpoint"]
~~~

A very common pitfall: when a queried name **matches** an associated private hosted zone, but that zone **does not have the corresponding record**, Route 53 Resolver **does not automatically fall back** to the public zone of the same name; it may return a name/record-not-found response. Therefore, if sharing a public/private namespace, you must actively manage the records needed in each view, or separate namespaces clearly to avoid conflicts.

## 5. What Does a DNS Record Set Contain?

A resource record set in Route 53 includes basic attributes such as:

- **Name:** FQDN, e.g., `api.example.com.` (the trailing dot indicates the root; many tools accept with or without the dot).
- **Type:** record type such as `A`, `AAAA`, `CNAME`, `MX`.
- **TTL:** time (in seconds) a recursive resolver may cache the record; alias records to AWS resources use the target's TTL.
- **Value/ResourceRecords or AliasTarget:** IP, hostname, DNS data structure, or alias target.
- **Routing policy:** simple, weighted, latency, failover, etc., optionally adding `SetIdentifier`, weight, region, health check.

An `example.com` hosted zone might contain the records below (IPs are in **documentation-only** ranges, not real server IPs):

| Name | Type | Illustrative Value | Purpose |
|---|---|---|---|
| `example.com.` | `A` alias | ALB or CloudFront target | Root domain (zone apex) |
| `www.example.com.` | `CNAME` | `example.com.` | Standard DNS alias for a subdomain |
| `api.example.com.` | `A` | `192.0.2.10` | IPv4 for API when using static IP |
| `api.example.com.` | `AAAA` | `2001:db8::10` | IPv6, if endpoint supports it |
| `example.com.` | `MX` | `10 mail.example.com.` | Mail server and priority |
| `example.com.` | `TXT` | `"v=spf1 include:_spf.example.net -all"` | TXT for illustrative SPF policy |
| `_acme-challenge.example.com.` | `TXT` | Illustrative validation token | Proving domain ownership |
| `example.com.` | `CAA` | `0 issue "amazon.com"` | Specifies CAs allowed to issue certs per CAA policy |

**Do not use example values to configure production systems.** Records for email, SPF/DMARC/DKIM, domain validation, and TLS must be taken **verbatim** from the authoritative provider. An `MX` record will not make email work if the SMTP/mail provider is not properly configured.

### 5.1. Common Record Types

| Type | Meaning | Notes |
|---|---|---|
| **A** | Name → IPv4 | Can hold multiple values; with alias, resolved by Route 53 to the appropriate target |
| **AAAA** | Name → IPv6 | Enable only when endpoint/network path supports IPv6 |
| **CNAME** | One name → another canonical name | **Do not place CNAME at zone apex**; cannot coexist with many other record types at the same name per DNS rules |
| **MX** | Routes mail to a mail exchanger | Includes priority; destination mail server must resolve validly in DNS |
| **TXT** | Text strings for domain verification, SPF, DKIM, etc. | Has quoting/chunking rules; follow each service's instructions |
| **NS** | Identifies authoritative name servers for a domain/subdomain | Critical for delegation |
| **SOA** | Authority info and negative caching parameters | Created by Route 53 by default; do not edit without understanding |
| **CAA** | Permits/restricts certificate authorities | Can affect TLS certificate issuance/renewal |
| **SRV** | Identifies service host/port | Has priority/weight/port/target format |
| **PTR** | Reverse resolution IP → name | Depends on reverse DNS type and prefix/IP ownership |

Route 53 also supports other record types depending on the API, such as `DS`, `HTTPS`, `SVCB`. Do not assume every record type is valid in every hosted zone/routing policy; check documentation and tool versions before using.

### 5.2. Multiple Records with the Same Name/Type

For **simple routing**, you can place multiple `A` IPs in **one record set**. Route 53 can return multiple addresses; the resolver/client selects an IP according to its own behavior. This is **not health-aware load balancing**. When you want weights/health checking, create record sets with the same Name/Type but different `SetIdentifier` values under a supported policy and configure appropriate health checks.

## 6. Alias, CNAME, and the Zone Apex

**Route 53 alias** is a Route 53-specific extension that lets a record point to certain AWS resources and other records. When a recursive resolver queries `A` or `AAAA` for the alias name, Route 53 returns the **corresponding target address** without exposing a standard DNS CNAME alias record.

| Criterion | **CNAME** | **Route 53 alias A/AAAA** |
|---|---|---|
| Standard DNS specification | Yes | Route 53-specific feature |
| Usable at `example.com` (apex) | **No** | **Yes** when target is supported |
| Target | Canonical domain name | Compatible AWS resource or eligible Route 53 record |
| TTL | Configured by you | When aliasing an AWS resource, uses the resource's TTL; when aliasing another record, uses the target's TTL |
| When target IP changes | Resolver continues resolving CNAME/target | Route 53 automatically returns updated IPs from supported targets |
| Client DNS query | Can see CNAME | Sees A/AAAA answer, does not see alias attribute |
| Query cost | Per DNS query pricing | Aliases to **AWS resources** typically incur no Route 53 DNS query charges per AWS pricing rules |

### 6.1. Root Domain Requires Alias Instead of CNAME

Do not create `CNAME example.com → d123.cloudfront.net` at the apex because the apex requires NS/SOA and per DNS rules cannot be a CNAME. A common configuration:

~~~text
example.com.      A (Alias)  -> CloudFront distribution
www.example.com.  A (Alias)  -> CloudFront distribution
api.example.com.  A (Alias)  -> Application Load Balancer
~~~

Aliasing to CloudFront/ALB requires the **DNSName and HostedZoneId of the AWS target itself** (different from your domain's Route 53 hosted zone ID). When creating via the Console, supported target values are usually suggested; in IaC/CLI, you must retrieve the target's actual attributes. For ALB/NLB, you can get `CanonicalHostedZoneId` from `describe-load-balancers`.

### 6.2. S3 and CloudFront

Route 53 can alias to an S3 **website endpoint** under static website hosting conditions, but an S3 website endpoint does not natively provide HTTPS with a custom domain. Modern website architectures typically use **CloudFront** as the CDN/HTTPS endpoint, with an S3 bucket as origin and **Origin Access Control (OAC)** when keeping the bucket private. You need to configure:

1. A CloudFront distribution and the appropriate Alternate Domain Name (CNAME).
2. An AWS Certificate Manager TLS certificate matching the hostname (certificates used for CloudFront must be in **us-east-1**).
3. An `A` alias record (and `AAAA` if using IPv6) from the domain to CloudFront.
4. Correct bucket policy/OAC and origin access; do not make the bucket public just to make DNS work.

**A DNS alias does not automatically provision a certificate.** The record may resolve successfully, but the browser will still report a TLS hostname mismatch if the certificate or CloudFront/ALB configuration is incorrect.

### 6.3. Evaluate Target Health

Alias records for some targets like ELB have an **Evaluate Target Health** option; Route 53 can factor in target health as supported by the target service when selecting DNS answers. Not every alias target type supports this feature (for example, CloudFront has its own limitations). Health evaluation **does not replace** ALB target group health checks, application readiness, or an end-to-end failover strategy.

## 7. Creating a Public Hosted Zone and Delegating a Domain

A production workflow needs to separate **setting up DNS records** from **transferring authoritative control**.

### 7.1. Preparation Phase

1. Inventory the domain and all subdomains in use: website, API, email, domain validation, DMARC/DKIM/SPF, service discovery.
2. Record Name/Type/TTL/Values/health rules from the current DNS provider.
3. Identify the AWS account owning the Route 53 public hosted zone; use least-privilege IAM permissions.
4. Create the **public** hosted zone for `example.com` in Route 53.
5. Create all required records and cross-check against the old configuration; verify sensitive records such as MX/TXT/CAA.
6. Note the **four NS** belonging to the exact hosted zone ID.
7. Plan the NS cutover at the registrar, monitoring window, and rollback procedure.

### 7.2. Updating the Registrar

When ready, change the domain registration's authoritative nameservers to the four name servers of the new hosted zone. If the domain is registered at another registrar, do this in that registrar's UI; if registered in Route 53, do it under **Registered domains**, not merely by editing the NS record inside the hosted zone.

**Important:** Recursive resolvers that cached the old NS delegation may keep querying the old DNS provider until their cache expires. Keep the old hosted zone and records consistent during an appropriate transition window—do not delete them immediately. Only clean up old resources after confirming the Internet actually uses the new NS and services are healthy.

### 7.3. Delegating a Separate Subdomain

Suppose an application team manages `apps.example.com` in its own hosted zone (possibly in another account), while the platform team owns the parent zone `example.com`.

- Create the public hosted zone `apps.example.com` and obtain the **child zone's** NS set.
- In the **parent zone `example.com`**, create an **NS record for `apps.example.com`** pointing to the child zone's name servers.
- Create records such as `api.apps.example.com` in the child zone and verify resolution from the Internet.

~~~mermaid
flowchart TD
    T["TLD .com"] --> P["NS delegation example.com"]
    P --> Z["Public hosted zone example.com"]
    Z --> S["NS delegation apps.example.com"]
    S --> C["Public hosted zone apps.example.com"]
    C --> A["api.apps.example.com → ALB"]
~~~

Simply creating the child zone and forgetting the NS delegation in the parent zone is not enough. Standard recursive resolvers will not find the path to the child zone's records.

## 8. TTL, DNS Caching, and Record Changes

**TTL (Time to Live)** specifies how many seconds a recursive resolver may keep a DNS answer in cache, starting from when it fetched the answer. TTL **does not guarantee** every client worldwide sees a change the moment you click Save.

For example, if you change `api.example.com` from `192.0.2.10` to `192.0.2.20` at 10:00:

- A resolver that cached the old record at 09:59 with a TTL of 3600 may return the old IP for nearly another hour.
- A resolver with an empty or expired cache may receive the new record sooner.
- Client OS, JVM, application libraries, or proxies may maintain their own caches per their policies.

### 8.1. Short or Long TTL?

| Illustrative TTL | When to use? | Trade-offs |
|---:|---|---|
| 60 seconds | Frequent backend changes or preparing for cutover | More DNS lookups, shorter caching |
| 300 seconds | APIs/websites needing moderate flexibility | Balance between caching and agility |
| 3600 seconds | Stable endpoints | Fewer repeated lookups, but DNS-based rollout/failover is slower |
| 86400 seconds | Very stable records safe to cache long-term | Changes/rollbacks take a long time |

These values are **examples**, not fixed rules. Negative TTL (negative caching) for non-existent answers relates to the SOA record and resolver behavior. A newly created hostname may still fail to resolve on a resolver because it cached an earlier `NXDOMAIN` result.

### 8.2. Low-Disruption DNS Change Procedure

1. **Several old TTLs ahead of time**: lower the current record's TTL and verify resolvers have had time to cache the new TTL value.
2. Prepare the new backend, health checks, TLS certificate, and firewall before cutover.
3. Update the record via Console/IaC/change batch; save evidence of the old record and the rollback plan.
4. Wait for **Route 53 change status = INSYNC** on the authoritative name servers.
5. Test both authoritative NS and recursive resolvers from different vantage points; expect an overlapping cache window.
6. Keep the old backend running for an appropriate period and monitor HTTP 5xx, latency, and DNS query failures.
7. Once stable, consider raising the TTL again to reduce queries and improve caching.

**`INSYNC` does not mean all recursive resolvers have dropped the old record.** It only means the change has propagated to the hosted zone's authoritative name servers. Resolver/client caches remain bound by TTL and implementation behavior.

## 9. Route 53 Routing Policies and Health Checks

When multiple endpoints serve the same hostname, Route 53 can apply a **routing policy** to select the appropriate DNS answer.

| Policy | Concept | Example Use Case |
|---|---|---|
| **Simple** | Returns configured record/alias simply | A single ALB for `api.example.com` |
| **Weighted** | Distributes answers by weight | Gradually shifting 10% → 50% → 100% of queries to a new version |
| **Latency** | Prefers the AWS Region endpoint with optimal estimated latency for the resolver/client location | Multi-Region applications |
| **Failover** | Primary/secondary based on health | DR site receives queries when primary is considered unhealthy |
| **Geolocation** | Answers based on country/geographic region | Region-specific content/compliance |
| **Geoproximity** | Answers based on resource location and bias | Tuning service areas across multiple locations |
| **Multivalue answer** | Returns multiple IPs/endpoints with optional health checking | Simple backends; does not replace a load balancer |
| **IP-based** | Answers based on identified client/resolver CIDR | Routing by source IP group, for supported hosted zone types |

Some policies/features differ in support between **public** and **private** hosted zones. For example, **IP-based routing is not among the supported routing policies for PHZs** per AWS documentation; check applicability rather than assuming every policy works in every zone.

### 9.1. Weighted DNS Does Not Equal Exact Application Request Percentage

If you create two weighted records with the same Name/Type and weights 90 and 10, Route 53 aims for a **percentage of DNS responses** by weight (when health conditions permit), not directly splitting 90% of HTTP requests. One recursive resolver can cache a single answer and serve thousands of users; actual request counts do not necessarily match record weight ratios.

For precise per-request rollout control, consider strategies at the ALB/API gateway, deployment/canary, or application layer.

### 9.2. Failover with Health Checks

A failover setup typically includes:

- A `PRIMARY` record for the main endpoint and its corresponding health check/target health.
- A `SECONDARY` record for the standby endpoint.
- DNS policy to return secondary when primary is unhealthy per Route 53 logic.

Health checks must inspect the **actual endpoint**. When creating a health check by hostname, do not arbitrarily use the DNS hostname controlled by the failover record itself as the check URL, because you could check the wrong backend. Use endpoint/region-specific hostnames such as `primary-health.example.com` and `secondary-health.example.com`.

Route 53 health checks from outside a VPC **cannot by default reach private IPs**. For private backends, use an appropriate mechanism such as a **CloudWatch alarm-based health check** or safely designed monitoring/endpoints. DNS failover is also subject to TTL/caching; never promise "instant cutover" when a backend fails.

### 9.3. DNS Does Not Replace a Load Balancer or CDN

Route 53 directs clients to an endpoint, while ALB balances requests across a target group and CloudFront caches content at the edge. For a Java/Spring Boot system, the typical path is:

~~~text
client → Route 53 DNS → CloudFront (optional) → ALB → ECS/EC2 → RDS
~~~

For multi-AZ resilience, ALB and Auto Scaling handle it at the zone/AZ layer. For full Region failover, weighted/latency/failover DNS or other global traffic services are one part of the solution, alongside database replication, data, IAM, and DR testing.

## 10. Using the AWS Management Console

### 10.1. Creating a Hosted Zone

1. Sign in to the AWS Console using IAM Identity Center/role in the right account.
2. Open **Route 53 → Hosted zones → Create hosted zone**.
3. Enter the **Domain name**, e.g., `example.com`.
4. Choose **Public hosted zone** or **Private hosted zone**.
5. If private, associate the authoritative VPC and Region; verify VPC DNS attributes.
6. Create the zone and record the **hosted zone ID**, NS set (public), and SOA.
7. For a public zone, prepare DNS records before changing registrar name servers.

Route 53 authoritative hosted zones are **global** resources; you do not create a separate public hosted zone per Region for the same domain. For VPCs/ALBs, you must be aware of the **target resource's** Region; private zone associations specify the VPC ID and Region.

### 10.2. Creating a Record

Inside the hosted zone, choose **Create record** and specify:

1. Record name, e.g., `api` in zone `example.com` (creates `api.example.com`).
2. Type `A` or `AAAA`, depending on IPv4/IPv6 endpoint support.
3. **Alias**: enable when pointing to a supported AWS resource; select the right target.
4. **Routing policy**: simple for basic cases, or weighted/failover/... when required by the design.
5. For non-alias records, enter TTL and resource values; for alias records, target TTL rules apply.
6. Verify the right zone/account, target URL/IP, and health settings, then save.

Do not modify the default NS/SOA of a public zone or create wildcard `*.example.com` records without understanding their impact. Wildcards have different matching rules from specific hostnames and do not automatically provide certificates for every name.

## 11. AWS CLI: Safely Reading Hosted Zones and Record Sets

The commands in this section are **read-only**, using AWS CLI v2 with an assumed `dev` profile granted permissions by an administrator. For Route 53 APIs managing hosted zones/records, **`--region` is not required** as it is for EC2/VPC; this is a global DNS management API group. Still verify the exact account/role before reading or making changes.

### 11.1. Identifying Identity/Account

~~~bash
aws --version
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Do not use the root account for routine DNS operations. When multiple accounts each have a zone named `example.com`, `sts get-caller-identity` helps catch being in the wrong account before touching production.

### 11.2. Listing Hosted Zones

~~~bash
aws route53 list-hosted-zones \
  --profile dev \
  --query 'HostedZones[].{Id:Id,Name:Name,Private:Config.PrivateZone,Records:ResourceRecordSetCount}' \
  --output table

aws route53 list-hosted-zones-by-name \
  --dns-name example.com \
  --profile dev \
  --output json
~~~

`list-hosted-zones-by-name` does not necessarily return only **one** `example.com` zone; the API returns a list ordered alphabetically starting from the specified name, which may include matching or different zone names and pagination. Filter by the **exact Name and hosted zone ID** before drawing conclusions.

### 11.3. Inspecting a Hosted Zone

~~~bash
aws route53 get-hosted-zone \
  --id Z012345EXAMPLE \
  --profile dev \
  --output json
~~~

A public zone result may include `DelegationSet.NameServers`; a private zone may list associated VPCs. `Z012345EXAMPLE` is a placeholder: use the account's **real hosted zone ID**. When a private zone has special/cross-account associations, you may also need the list-zones-by-VPC API or network admin verification for a complete picture.

### 11.4. Reading Record Sets

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --profile dev \
  --query 'ResourceRecordSets[].{Name:Name,Type:Type,TTL:TTL,Alias:AliasTarget.DNSName,Values:ResourceRecords[].Value}' \
  --output json
~~~

`TTL` may be absent on alias records; `AliasTarget` may be absent on standard records. For zones with many records, the CLI handles pagination; **do not pass `--no-paginate`** and assume you have read the entire zone. The API returns records ordered by name and type, with markers to continue.

### 11.5. Testing Public DNS Answers

~~~bash
# Only for PUBLIC hosted zones: simulates authoritative DNS answer.
aws route53 test-dns-answer \
  --hosted-zone-id Z012345EXAMPLE \
  --record-name www.example.com \
  --record-type A \
  --profile dev \
  --output json
~~~

`TestDNSAnswer` supports **public hosted zones**, not private zones. It checks what Route 53 **would answer** for a given query, without proving that the registrar has delegated to the zone or that everyone's recursive cache has updated.

From a machine with `dig`:

~~~bash
# Query through the configured recursive resolver
dig A www.example.com
dig AAAA www.example.com
dig NS example.com

# Query a real authoritative name server of the hosted zone directly
dig @ns-real-authoritative.example A www.example.com
~~~

The last line uses a **placeholder**; replace it with a name server from `get-hosted-zone`, such as `ns-xxxx.awsdns-yy.com` from the real zone. On Windows you can use:

~~~powershell
nslookup -type=A www.example.com
nslookup -type=NS example.com
~~~

Distinguish between results from querying an **authoritative NS** and a **recursive resolver**. If Route 53 returns the new record but users still see the old one, check delegation, TTL/caching, or DNS views.

## 12. AWS CLI: Structure of a Change Batch

Route 53 uses the `ChangeResourceRecordSets` API with a list of changes in a batch:

- `CREATE`: creates a new record set; fails if a record set with the same identifier already exists.
- `UPSERT`: creates if missing, or replaces an existing record set.
- `DELETE`: deletes a record set matching the exact values/attributes required by the API; read current state first to avoid accidental deletion.

A batch is **validated upfront and applied all-or-nothing** by Route 53 for that batch; it is not an atomic transaction across ALB/CloudFront creation or external non-DNS systems.

### 12.1. Illustrative JSON Example for an A Record

Suppose you already have the `example.com` hosted zone with ID `Z012345EXAMPLE` and want to create `api.example.com`. Prepare `change-a.json` **before** running the change operation:

~~~json
{
  "Comment": "Illustration: update api.example.com for approved lab",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.example.com.",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          { "Value": "192.0.2.10" }
        ]
      }
    }
  ]
}
~~~

**The address `192.0.2.10` is a documentation IP, not a real backend.** This example illustrates structure and must not be used verbatim in production.

The command below **actually modifies DNS** when run with valid file/zone/credentials; execute only after approval and confirming that `UPSERT` does not overwrite a critical record:

~~~bash
aws route53 change-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --change-batch file://change-a.json \
  --profile dev
~~~

The response includes `ChangeInfo.Id` and `Status`, usually starting as `PENDING`. Check status:

~~~bash
aws route53 get-change \
  --id /change/C012345EXAMPLE \
  --profile dev \
  --output json
~~~

Replace `/change/C012345EXAMPLE` with the **actual ChangeInfo.Id**. Once `INSYNC`, the change has reached the authoritative name servers; client caches may still hold unexpired TTLs.

### 12.2. Illustrative Alias Structure to an ALB

An alias record replaces `TTL` and `ResourceRecords` with `AliasTarget`:

~~~json
{
  "Name": "api.example.com.",
  "Type": "A",
  "AliasTarget": {
    "HostedZoneId": "ELB_CANONICAL_HOSTED_ZONE_ID",
    "DNSName": "my-alb-123.ap-southeast-1.elb.amazonaws.com.",
    "EvaluateTargetHealth": true
  }
}
~~~

This is a **`ResourceRecordSet` inside a ChangeBatch**, not the entire request. `HostedZoneId` inside `AliasTarget` is the **ALB's canonical zone ID**, distinct from `Z012345EXAMPLE` managing `example.com`. Do not guess IDs by Region or copy an example ID; retrieve it from the real load balancer description and AWS documentation.

### 12.3. Guardrails for Production DNS Changes

- Verify the correct AWS account, zone ID, record Name/Type, policy, target, and TTL.
- Read and export current records for rollback readiness; watch for weighted/latency records with `SetIdentifier`.
- With `UPSERT`, verify all values in the record set; do not assume "adding one value" preserves existing values.
- With `DELETE`, supply the exact matching attributes of the existing record; re-read before deleting.
- Scope IAM permissions by hosted zone, record names/types/actions where appropriate; review IaC changes.
- Wait for `INSYNC` and test DNS queries; continue monitoring the application and recursive caches.
- Never put sensitive data in TXT records or comments/commit logs.

## 13. Private Hosted Zones and Route 53 Resolver in AWS VPC

### 13.1. An Internal Example

A Spring Boot application in VPC App needs to call a gRPC API through an internal ALB in VPC Shared. The team can place `grpc.internal.example.com` in a private hosted zone `internal.example.com`, associating the PHZ with VPC App and VPC Shared using appropriate permissions. Workloads querying through Route 53 Resolver in the associated VPCs will receive the private DNS answer.

**DNS does not create an IP network route.** If VPC App lacks an actual network path to the internal ALB in VPC Shared (VPC peering, Transit Gateway, PrivateLink, or another valid model), the hostname may still resolve while the TCP connection still fails.

### 13.2. Cross-Account PHZ Association

When the PHZ lives in a DNS account and the VPC lives in an application account, a typical workflow is:

1. The account owning the PHZ creates an **association authorization** for the other account's VPC ID and Region.
2. A principal in the account owning the VPC calls the API to **associate the VPC with the hosted zone**, with appropriate permissions.
3. After association succeeds, unnecessary authorizations can be deleted.
4. Verify VPC DNS attributes and resolution from a resource inside the VPC.
5. Codify the association workflow in IaC/runbooks to avoid configuration drift.

AWS also offers newer DNS sharing management mechanisms and considerations with Route 53 Profiles/Resolver; the steps above describe **traditional direct association**. Do not assume that merely being in the same AWS Organization makes a PHZ automatically visible in all VPCs.

### 13.3. Resolver Inbound/Outbound Endpoints

Route 53 Resolver can support hybrid DNS:

- **Inbound Resolver endpoint:** on-premises DNS servers send queries into the VPC/AWS environment over appropriate networking/DNS forwarding to resolve private names.
- **Outbound Resolver endpoint + forwarding rule:** the VPC Resolver forwards specified domains back to on-premises DNS servers.
- **Resolver rules/associations:** determine which VPCs use which forwarding rules.

Endpoints create network interfaces and require Security Groups, subnets/AZs, routes, and separate charges. Create them only when there is a clear hybrid DNS requirement; systems using names within a single VPC are simpler with PHZ association.

### 13.4. Split-View and NXDOMAIN Errors

For example, the public zone has `www.example.com`, while a private zone of the same name `example.com` **does not** have a `www` record. If an EC2 instance in an associated VPC queries `www.example.com`, it may receive **NXDOMAIN** instead of the public record. This is a common mistake: operators assume "if missing in private, it falls back to public," whereas Resolver selects the matched private namespace.

The fix is to define all required records in the private view, or create the PHZ only for a narrower namespace like `corp.example.com` when the architecture allows. Also check resolver rule precedence and hosted zones with overlapping namespaces.

## 14. Security: IAM, TLS, and DNSSEC

### 14.1. IAM and DNS Changes

DNS changes can redirect traffic to production systems or disrupt email. Administrators do not need `AdministratorAccess`. Roles can be scoped:

| Task | Commonly Related IAM Actions |
|---|---|
| List hosted zones | `route53:ListHostedZones`, `route53:ListHostedZonesByName` |
| View hosted zone and records | `route53:GetHostedZone`, `route53:ListResourceRecordSets` |
| Create/edit/delete records | `route53:ChangeResourceRecordSets` on allowed hosted zones |
| Check record change progress | `route53:GetChange` |
| Create hosted zone | `route53:CreateHostedZone` |
| Associate VPC and PHZ | `route53:AssociateVPCWithHostedZone`, authorization APIs, and related VPC permissions |
| DNSSEC key signing | Appropriate Route 53 DNSSEC and AWS KMS actions |

You can use IAM condition keys such as `route53:ChangeResourceRecordSetsNormalizedRecordNames`, `route53:ChangeResourceRecordSetsRecordTypes`, and `route53:ChangeResourceRecordSetsActions` to restrict a role to updating only specific names/types/actions within a hosted zone. Combine with MFA, IAM Identity Center, approvals, and IaC change reviews. Do not grant permission to create/modify NS delegations to developers who do not manage the domain.

### 14.2. DNS and HTTPS Are Two Separate Problems

A DNS record may point to the right ALB while HTTPS still fails if:

- The ACM certificate does not include the hostname requested by the client.
- The ALB HTTPS listener uses the wrong cert or lacks TLS configuration.
- CloudFront lacks the corresponding alternate domain name/certificate.
- The target group is unhealthy, a Security Group/NACL blocks the port, or the backend has not started.
- The browser/Java client validates TLS/SNI and the server returns a cert for a different domain.

Troubleshoot layer by layer: **DNS resolution → TCP/TLS → load balancer → application**. Do not disable TLS verification to "fix DNS."

### 14.3. DNSSEC

**DNS Security Extensions (DNSSEC)** allow validating resolvers to verify DNS signatures, mitigating certain types of DNS data spoofing/tampering. Route 53 supports **DNSSEC signing for public hosted zones**, and does not support enabling signing directly on private hosted zones.

High-level process:

1. Verify DNSSEC prerequisites, name servers, and rollback plan.
2. Create/register a **KSK** backed by an asymmetric AWS KMS key per AWS requirements, and enable signing on the hosted zone.
3. Retrieve the **DS record** from Route 53.
4. Add the DS record to the appropriate **parent zone/registrar** to establish the chain of trust.
5. Monitor DNSSEC errors via CloudWatch and verify query resolution.

**Do not enable DNSSEC and add DS records casually in production:** if the DS at the parent is wrong or key/signing fails, validating resolvers may fail to return records and the entire domain can go down. AWS recommends CloudWatch alarms such as `DNSSECInternalFailure` and `DNSSECKeySigningKeysNeedingAction`. DNSSEC does not encrypt DNS traffic and does not protect HTTP without TLS.

## 15. Monitoring, Resilience, and Cost

### 15.1. Monitoring

- **CloudTrail:** logs control-plane actions such as `ChangeResourceRecordSets`, `CreateHostedZone`, or configuration changes when properly configured; aids actor and timestamp auditing.
- **Route 53 query logging:** logs DNS queries per public hosted zone capabilities or Resolver query logging for VPCs, with separate log destinations; evaluate cost and sensitive data in domain names.
- **Route 53 health checks:** monitor public endpoints, health checking options, or CloudWatch alarms; use only with compatible routing policies.
- **CloudWatch metrics/alarms:** health check status, DNSSEC, and feature metrics; correlate with application HTTP 5xx/latency at ALB/CloudFront.
- **Reachability/Application logs:** DNS may be correct while TCP/HTTP still fails; logs are needed across layers.

### 15.2. Costs to Budget For

Route 53 charges **monthly hosted zone fees** and **DNS query fees** per its pricing policy, in addition to domain registration/renewal. Features like health checks, Resolver endpoints/query logging, and certain traffic policies can incur separate charges.

| Item | Cost Driver Example |
|---|---|
| Public/private hosted zone | Number of existing hosted zones, even if not yet delegated |
| Standard/advanced DNS queries | Query volume and routing policy type |
| Alias record to AWS resource | Certain alias queries are free in Route 53 per pricing rules |
| Health checks | Number of checks, interval/feature settings |
| Route 53 Resolver endpoints | Endpoint hours and query counts per pricing schedule |
| Domain registration | Annual renewal, independent of hosted zones |
| ALB/CloudFront/S3/EC2 | Downstream services receiving requests bill separately by usage |

Do not assume "a new record costs nothing": query volume, hosted zone count, health checks, and target services all affect total cost. Check current pricing for your Region/features at [Amazon Route 53 Pricing](https://aws.amazon.com/route53/pricing/) before finalizing a design.

### 15.3. DR and DNS Boundaries

DNS failover can direct **new connections** to another endpoint, but it does not transfer database state. To recover a Java application across Regions, you need data backup/replication, IAM roles, secrets, container images, network routes, ALB target health, TLS certificates, and DR testing. DNS is only one component of failover.

## 16. Common Issues and Diagnostic Order

| Symptom | Common Cause | Check/Resolution |
|---|---|---|
| Record exists in Route 53 but Internet does not resolve | Registrar/parent has not delegated to that zone's NS | `dig NS`, compare NS at registrar, zone ID, and delegation chain |
| Two hosted zones with same name; queries return old record | Editing the undelegated zone by mistake | Compare each zone ID, NS set, and parent delegation |
| `NXDOMAIN` right after creating a new record | Negative cache or record not yet on authoritative NS | Query authoritative NS, check SOA/negative TTL and `GetChange` status |
| `INSYNC` yet users still hit old IP | Recursive/browser/JVM/proxy DNS cache still holds TTL | Test from multiple resolvers; keep old backend running long enough |
| `api.example.com` returns unexpected CNAME | Different alias/CNAME/policy record, DNS view, or resolver cache | Use `dig A/AAAA/CNAME`, inspect record set/type/target |
| Cannot create CNAME at apex `example.com` | DNS prohibits CNAME at zone apex | Use Route 53 alias A/AAAA to a supported target |
| Alias to ALB fails on creation | Wrong `AliasTarget.HostedZoneId` or DNSName/Region | Retrieve CanonicalHostedZoneId from the real ELB target |
| DNS resolves to right IP but HTTPS cert errors | ACM/CloudFront/ALB hostname & TLS certificate mismatch | Inspect certificate, listener, alternate domain names |
| Private DNS works only in VPC A | VPC B lacks PHZ association or proper DNS attributes | Check VPC association, `enableDnsSupport`/`enableDnsHostnames` |
| Peered VPC cannot resolve PHZ names | Peering does not automatically share PHZs | Associate PHZ with the other VPC or use Resolver forwarding |
| PHZ shares public zone name, missing some records | Split-view does not fall back to public for a matched private zone | Create needed records in private view or separate namespaces |
| Failover does not switch in time | Misconfigured health check, endpoint not yet unhealthy, client caches hold TTL | Check `GetHealthCheckStatus`, routing policy, and client TTL |
| Weighted 10% but HTTP traffic is not 10% | DNS weights affect answers; resolver caching/client behavior skews requests | Measure queries vs. HTTP separately; use L7 rollout for exact request ratios |
| DNS changes unexpectedly after deploy | IaC/automation/manual overwrite of records | Inspect CloudTrail, change sets, and pipeline history |
| DNSSEC causes `SERVFAIL` at validating resolvers | Wrong DS/KSK or broken chain of trust/signing | Check DNSSEC/CloudWatch and rollback runbook |
| Deleted hosted zone and domain broke | Deleted zone before moving delegation or lost records | Restore per NS/record plan and perform appropriate registrar actions |

### 16.1. Four-Layer Procedure

1. **DNS name:** what hostname/type is the client querying, and in public or private view?
2. **Delegation/authoritative:** which NS does the parent point to, is the zone ID right, and does the record exist on the authoritative server?
3. **Cache and policy:** are TTL, negative caching, weighted/failover health, or `GetChange` affecting results?
4. **Application target:** does the IP/ALB/CloudFront have network path, TLS, health, authentication, and backend readiness?

This approach prevents editing Security Groups when the root cause is at the registrar, or editing DNS records when the application is returning HTTP 500.

## 17. Read-Only Lab: Comparing Records and Delegation

### 17.1. Prerequisites

Have a learning AWS account, AWS CLI v2 profile `dev` with permissions to view hosted zones/records, and a readable public hosted zone. No need to register a new domain or touch production. If you do not have a zone yet, use `example.com` to analyze the structure.

### 17.2. Step A — Identify the Account

~~~bash
aws sts get-caller-identity --profile dev --output json
aws route53 list-hosted-zones-by-name \
  --dns-name example.com \
  --profile dev \
  --output json
~~~

Note the account ID, zone ID, and `Config.PrivateZone`. If there is no zone, do not create one just for sample data; analyze the illustrative JSON instead.

### 17.3. Step B — Read NS/SOA and Application Records

~~~bash
aws route53 get-hosted-zone \
  --id Z012345EXAMPLE \
  --profile dev

aws route53 list-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --profile dev \
  --output json
~~~

Replace the placeholder zone ID with your assigned ID. Find `NS`, `SOA`, `A`, `AAAA`, `CNAME`, `MX`, `TXT`. For alias records, inspect `AliasTarget`; for standard records, inspect `TTL` and `ResourceRecords`.

### 17.4. Step C — Compare Route 53 with a Recursive Resolver

If the zone is **public** and delegated, compare:

~~~bash
# Query through the default DNS resolver
dig NS example.com
dig A api.example.com

# Test Route 53's direct answer for the assigned zone
aws route53 test-dns-answer \
  --hosted-zone-id Z012345EXAMPLE \
  --record-name api.example.com \
  --record-type A \
  --profile dev
~~~

Answer: Do the NS records at the parent match the zone's delegation set? If `TestDNSAnswer` returns data while `dig` does not, would you check delegation or cache first?

### 17.5. Step D — Choose the Right Record

| Requirement | Recommended DNS Design | Notes |
|---|---|---|
| Root `example.com` to CloudFront | `A` alias, and `AAAA` alias if using IPv6 | Requires valid alternate domain/certificate |
| `api.example.com` to ALB | `A` alias, `AAAA` depending on IPv6 | AliasTarget uses the ALB's canonical hosted zone ID |
| `www.example.com` to root | Valid CNAME or alias | Do not place CNAME at apex |
| Send email for `example.com` | `MX` + required `TXT` records | Get real config from email provider |
| Internal name `db.internal.example.com` | PHZ and VPC association | DNS only resolves; RDS credentials/SG still required |
| Gradual v1/v2 rollout | Weighted records | DNS weight does not guarantee exact HTTP request ratio |
| Two-Region failover routing | Failover records/health | Requires data DR and TTL/cache strategy |

### 17.6. Step E — Design a DNS Cutover Plan

Suppose you want to switch `api.example.com` to a new ALB at 10:00 on deployment day:

1. Check the authoritative zone, NS delegation, and current record TTL.
2. Schedule lowering the TTL **early enough**—do not wait until cutover time.
3. Prepare ALB/ACM/target health and run HTTPS tests against a test endpoint.
4. Execute the change batch via IaC/approved workflow.
5. Wait for `INSYNC`, test authoritative/recursive resolvers, and monitor HTTP success rate.
6. Keep the old backend running long enough for client caches; keep a rollback record and runbook ready in case of errors.

## 18. Self-Check Questions

1. Why does creating a public hosted zone with the same name as a registered domain still not make users see new records?
2. What purpose do the four name servers assigned by Route 53 for a zone serve? Where do they sit in delegation?
3. Does a private hosted zone require setting NS at the registrar for EC2 instances in the same VPC to resolve it?
4. Which VPC DNS attributes must be enabled when using a private hosted zone?
5. If private and public hosted zones share the same name, and the private zone matches the query but lacks the record, does the resolver automatically fall back to public?
6. Why can't `CNAME` be placed at `example.com`, whereas an `A` alias can?
7. What two target fields does an alias record to an ALB require? Why is the target HostedZoneId different from the domain's zone ID?
8. Can you infer an exact HTTP request ratio from a 90/10 weighted DNS setup?
9. Distinguish `PENDING/INSYNC` from recursive resolver TTL.
10. Why doesn't a health check guarantee all users switch to the secondary within a few seconds?
11. Which AWS CLI command lists a zone's record sets? Which command returns the status of a change batch?
12. Can `TestDNSAnswer` be used to directly test a private hosted zone?
13. What systems besides a website can `MX`/`TXT` records affect?
14. When a domain resolves to the right ALB but the browser reports a certificate error, what should you check?
15. Why does DNSSEC signing for a public zone require a DS record at the parent/registrar?
16. Which charges still apply even when nobody has queried a public hosted zone yet?

### Answer Guidance

Demonstrated competence means knowing to inspect in order—**registrar/delegation → hosted zone/record → TTL/cache/routing policy → endpoint/TLS/application**—choosing the right record type, not confusing the DNS control plane with application traffic, and having a change, monitoring, and rollback plan.

## 19. Official Documentation

1. [What is Amazon Route 53?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Welcome.html) — DNS, domain registration, health checking.
2. [Working with public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-working-with.html) — Creating and managing public hosted zones.
3. [Considerations when working with public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zone-public-considerations.html) — NS/SOA and zones with duplicate names.
4. [Working with private hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-private.html) — VPC association and private DNS.
5. [Considerations for private hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zone-private-considerations.html) — Split-view DNS and no-fallback behavior.
6. [Choosing between alias and non-alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html) — Alias, CNAME, and apex.
7. [DNS record types](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/ResourceRecordTypes.html) — A/AAAA/CNAME/MX/TXT/CAA and other types.
8. [Choosing a routing policy](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html) — Simple, weighted, latency, failover, and other policies.
9. [How Route 53 chooses records when health checking is configured](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — Health-based routing caveats.
10. [AWS CLI route53 list-resource-record-sets](https://docs.aws.amazon.com/cli/latest/reference/route53/list-resource-record-sets.html) — Reading record sets and pagination.
11. [AWS CLI route53 change-resource-record-sets](https://docs.aws.amazon.com/cli/latest/reference/route53/change-resource-record-sets.html) — Change batches and record mutations.
12. [Route 53 GetChange API](https://docs.aws.amazon.com/Route53/latest/APIReference/API_GetChange.html) — `PENDING` and `INSYNC`.
13. [Route 53 TestDNSAnswer API](https://docs.aws.amazon.com/Route53/latest/APIReference/API_TestDNSAnswer.html) — Testing public DNS answers.
14. [DNSSEC signing in Route 53](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-configuring-dnssec.html) — KSK/DS and operational notes.
15. [Route 53 pricing and billing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Route53Pricing.html) — Hosted zone/query/health costs.
16. [Amazon VPC DNS concepts](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html) — Resolver, VPC DNS attributes, and private names.

> **Key Takeaway:** A **hosted zone** stores records, **NS delegation** determines which zone is authoritative, **TTL/caching** governs when changes take effect, and **routing policy** selects the DNS answer. For AWS applications, verify DNS alongside ALB/CloudFront/VPC, TLS, IAM, health monitoring, DR, and cost before promoting records to production.
