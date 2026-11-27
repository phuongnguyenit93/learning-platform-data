# Regions, Availability Zones, and Edge Infrastructure

> **Chapter:** AWS Overview  
> **Module Scope:** `CLOUD_PROVIDERS_AWS` — explore AWS infrastructure to select services and design and deploy secure, observable, resilient, and cost-controlled applications.

When deploying an application on AWS, the first question is not only "should we use EC2 or Lambda?" but also **where will resources be placed, which parts need redundancy, and which network path will users take?** The three foundational concepts that answer that question are **Region**, **Availability Zone (AZ)**, and **edge infrastructure**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between Regions, AZs, data centers, edge locations, and extended locations such as Local Zones.
2. Explain resource scope by Region/AZ and its implications for VPCs, subnets, servers, and storage.
3. Choose a Region based on latency, data residency, service availability, recovery requirements, and cost.
4. Design Multi-AZ applications to reduce impact when an AZ fails; know when to consider multiple Regions.
5. Identify the roles of CloudFront, Route 53, and Global Accelerator along the path of a request from users to the application.

## 2. Mental Map: Layers of AWS Infrastructure

One way to visualize the system is moving from broad to narrow geographic scope:

~~~text
AWS Global Infrastructure
├── AWS Region (e.g., ap-southeast-1, Singapore)
│   ├── Availability Zone A
│   │   └── One or more independent data centers
│   ├── Availability Zone B
│   │   └── One or more independent data centers
│   └── Availability Zone C
│       └── One or more independent data centers
├── Other Regions (different geographic and fault scopes)
└── Global Edge Network
    ├── Points of Presence / edge locations
    ├── Regional edge caches (CloudFront)
    └── Network endpoints for delivery and routing services
~~~

This diagram illustrates **conceptual relationships**, not a physical wiring diagram. An edge location is not an AZ inside a Region; the edge network operates globally and connects to **origin** systems in a Region or elsewhere.

| Unit | Nature | Primary problem addressed | Example |
| --- | --- | --- | --- |
| **Region** | Geographic area consisting of multiple independent AZs | Data location, deployment scope, regional fault isolation | `ap-southeast-1` (Singapore) |
| **Availability Zone** | One or more data centers with separate power, networking, and physical facilities within a Region | Availability when a single facility location fails | `ap-southeast-1a` as an AZ name in an account |
| **Edge location / PoP** | Point of presence belonging to the global edge network | Bringing content and connectivity closer to users | Endpoint serving CloudFront requests |
| **Regional edge cache** | Larger caching tier between CloudFront PoPs and the origin for eligible flows | Increasing cache content reuse | Caching less frequently accessed objects |
| **Local Zone / Wavelength Zone / Outposts** | Ways to extend AWS infrastructure to locations with specialized requirements | Ultra-low latency, 5G, or on-premises customer deployment | Analyzed in Section 6 |

**Key takeaway:** Regions and AZs help you choose where to operate and design fault tolerance; edge infrastructure improves the path to users. They solve different parts of the architecture.

## 3. AWS Regions: Choosing a Deployment Area

### 3.1. What Is a Region?

An **AWS Region** is a distinct geographic area where AWS provides infrastructure and services. Each Region consists of multiple AZs designed to be isolated from one another and connected via high-bandwidth, low-latency private networking. Each Region has an identifier code, for example:

- `ap-southeast-1`: Asia Pacific (Singapore).
- `ap-southeast-3`: Asia Pacific (Jakarta).
- `ap-northeast-1`: Asia Pacific (Tokyo).
- `eu-west-1`: Europe (Ireland).

When creating a **regional** resource, the deployer selects that resource's Region. Most services do not automatically replicate resources to other Regions simply because all Regions belong to AWS. For example, an RDS database in Singapore does not automatically have a replica in Tokyo; to enable recovery in Tokyo, you must design the corresponding replication, backups, failover procedures, and access permissions.

Some services have a **global** interface or scope (such as IAM, Route 53, CloudFront), whereas many other resources are bound to a Region or AZ. Therefore, you should not assume all data and functionality of an application reside in a single Region solely based on an EC2 configuration.

### 3.2. Five Criteria for Choosing a Region

| Criterion | Question to answer | How to verify |
| --- | --- | --- |
| **Latency** | Where are users and dependent systems located? | Measure actual latency from representative networks, locations, and times; test paths through a CDN if used |
| **Data residency and governance** | Is data required to be stored or processed within a specific jurisdiction? | Review regulations, contracts, backup flows, logs, replicas, and edge caches |
| **Services and features** | Are the required instance types, database engines, features, or quotas available in the Region? | Check the regional service availability and quotas page at deployment time |
| **Availability and recovery** | Must the system tolerate instance failure, AZ failure, or loss of an entire Region? | Define RTO/RPO targets and verify actual recovery capabilities |
| **Cost** | Are resource prices, Internet egress, and data transfer costs appropriate? | Estimate costs by Region with the AWS Pricing Calculator and current pricing |

**Example:** a business whose customers are primarily in Vietnam might shortlist Singapore (`ap-southeast-1`) because of relatively close geographic proximity. However, **you cannot assume this Region always has the lowest latency**: ISPs, network routes, equipment placement, supported services, and data policies all influence the final choice. Compare using actual measurements and real requirements.

### 3.3. A Region Is a Critical Recovery Boundary

A Multi-AZ design within **one Region** can tolerate the failure of a single AZ, but it is not a complete strategy against an incident that makes an entire Region unavailable. When the business requires continued operation after a Region-level outage, you must consider a backup Region along with components such as replicated data, infrastructure configuration, DNS, identity/permissions, and failover testing.

A Multi-Region strategy is usually more complex and expensive. For applications without an explicit Region-level recovery requirement, a single-Region, Multi-AZ design can be a reasonable starting point.

## 4. Availability Zones: Fault Boundaries Inside a Region

### 4.1. How Do AZs Work?

Each **Availability Zone** consists of one or more data centers with power, network connectivity, and operational facilities engineered to be independent from other AZs. AZs within the same Region are interconnected via low-latency private links, supporting architectures distributed across AZs.

For example, if an application has only one EC2 server in AZ A, losing AZ A can stop the application from serving requests. If the application has active replicas in AZ A and AZ B, a load balancer can route requests to the healthy replica when AZ A fails, **provided** the remaining capacity can handle the load and dependencies are also available.

AWS designs Regions with multiple AZs, but **the number of AZs available in your account and specific resource provisioning capacity must still be verified**. Do not assume all AZs offer the exact same instance types, quotas, or capacity levels at all times.

### 4.2. AZ Names and AZ IDs Are Not Identical

AZ names look like `ap-southeast-1a`, `ap-southeast-1b`; **AZ IDs** look like `apse1-az1`, `apse1-az2`. An AZ ID consistently identifies the same physical location across accounts. In some Regions and for older AWS accounts, the letter suffix in an AZ name may map differently between accounts.

Therefore:

- When deploying within **a single account**, you can use the AZ names returned by AWS for that account.
- When matching physical locations across **multiple accounts**, rely on the **AZ ID**; do not assume the letter "a" in two accounts always points to the same physical AZ.
- When describing an architecture, specifying "two independent AZs" matters more than hardcoding a pair of letters.

### 4.3. Resource Scope: Regional, Zonal, or Global?

Not every resource in an application shares the same level of redundancy. You need to know which services are deployed per AZ and which manage availability at the Regional level automatically.

| Resource / service | Scope to remember | Design implication |
| --- | --- | --- |
| **VPC** | Bound to one Region; can contain subnets across multiple AZs | Creates one logical network for the application within the Region |
| **Subnet** | Resides completely within **one AZ**, never spanning multiple AZs | Needs a separate subnet in each AZ where you want to deploy |
| **EC2 instance** | Runs in one AZ | To survive an AZ failure, add instances/deployment groups in another AZ |
| **EBS volume** | Bound to one AZ | Volumes do not automatically move to another AZ; consider snapshots, backups, and recovery |
| **Application Load Balancer** | Configured at the Regional level and operates across enabled AZs | Specify subnets from at least two AZs; place healthy targets in multiple AZs |
| **Amazon RDS Multi-AZ** | Deploys cross-AZ redundancy depending on configuration option | Enables database failover; does not mean the application automatically tolerates all failures |
| **Amazon S3 Standard** | Regional object storage with service-managed redundancy across multiple AZs | You do not choose an AZ per object; distinguish from single-AZ storage classes like S3 One Zone-IA |
| **CloudFront / Route 53** | Services operating on global infrastructure | Do not treat them like an EC2 instance placed in a single AZ |

Important networking example: creating a VPC `10.20.0.0/16` does **not** mean creating one giant subnet spanning AZs. It can be divided into:

| Example subnet | CIDR | Location | Role |
| --- | --- | --- | --- |
| `public-a` | `10.20.0.0/24` | AZ A | Components requiring public connectivity by design |
| `public-b` | `10.20.1.0/24` | AZ B | Redundancy for the public tier |
| `app-private-a` | `10.20.10.0/24` | AZ A | Internal application servers |
| `app-private-b` | `10.20.11.0/24` | AZ B | Internal application servers |
| `db-private-a` | `10.20.20.0/24` | AZ A | Subnet for the data tier |
| `db-private-b` | `10.20.21.0/24` | AZ B | Subnet for the data tier |

This is only an example addressing scheme; a real configuration also requires route tables, security groups, network ACLs (if applicable), an Internet Gateway, NAT or VPC endpoints, and appropriate security rules. A **"public subnet"** is determined by having a route to an Internet Gateway, not merely because the subnet has "public" in its name.

## 5. Edge Infrastructure: Bringing the Experience Closer to Users

### 5.1. Edge Locations and Points of Presence

The AWS edge network consists of **Points of Presence (PoPs)** distributed across many network regions. Instead of every request traveling to an origin server in a distant Region, certain services can process, deliver, or optimize traffic paths at a location closer to the user.

An **edge location** is not a general-purpose place to run every AWS service. Nor does it replace Regions, AZs, or redundancy requirements for applications and databases at the origin.

### 5.2. Three Easily Confused Services

| Service | Primary job | Suitable scenario | What not to misunderstand |
| --- | --- | --- | --- |
| **Amazon CloudFront** | CDN serving HTTP(S) content, using caches and the edge network; can forward requests to origins | Images, CSS, JavaScript, video, web pages, some APIs | Having a CDN does **not** mean the database or the entire API runs at the edge |
| **Amazon Route 53** | Managed DNS; supports multiple routing policies and health checks | Resolving domain names, routing/redirecting targets when conditions change | DNS returns addresses to browsers; DNS itself does not transfer the website's full content |
| **AWS Global Accelerator** | Provides static anycast IP addresses and optimizes network paths to application endpoints, supporting failover when endpoints fail | TCP/UDP services, applications needing stable global connectivity | It is not a CDN that caches copies of images, HTML, or video |

**Simple CloudFront flow:**

1. A browser accesses a URL; DNS helps determine the appropriate connection target.
2. The request travels to a CloudFront PoP selected by the network based on routing conditions.
3. If the object is cacheable and a valid copy is present (*cache hit*), the PoP serves the content from cache.
4. On a *cache miss*, CloudFront checks the next cache tier when applicable or forwards the request to the **origin** (such as S3, ALB, or a web server), then returns the result to the browser.
5. Cached data can serve subsequent requests according to TTL, path, header, cookie, query string, and related policies.

**Watch out for sensitive data:** Do not configure shared caching for personalized content without controlling cache keys, access permissions, and cache policies. For ordering, payment, or account-data APIs, explicitly decide which requests may be cached and which must go to the origin.

A **Regional edge cache** in CloudFront is a larger cache layer sitting between PoPs and the origin for eligible flows. The word "regional" in this name **does not turn it into an AZ or the Region where you deploy your database**.

### 5.3. Can Logic Be Processed at the Edge?

Yes, though capabilities and limits depend on the service:

- **CloudFront Functions** are suited for lightweight HTTP-layer operations such as manipulating URLs, headers, or cache keys.
- **Lambda@Edge** supports more complex custom logic on CloudFront events, with specific constraints on runtimes, permissions, and deployment.

Only appropriate logic should be moved to the edge. Transactions requiring data consistency, database access, and core business workflows still require a clear origin architecture.

## 6. Local Zones, Wavelength Zones, and AWS Outposts

Beyond standard Regions/AZs and the CDN network, AWS offers ways to bring compute and storage closer to specialized operating locations.

| Model | Location and goal | When to consider |
| --- | --- | --- |
| **AWS Local Zones** | An extension of a Region closer to end users, providing a subset of services | Latency-sensitive applications in a metro area, real-time interactive processing |
| **AWS Wavelength** | Embeds select AWS services into telecom carriers' 5G edge infrastructure | 5G device applications with ultra-low latency requirements |
| **AWS Outposts** | AWS infrastructure installed in a customer's data center or facility | On-premises processing needed, local system integration, physical equipment placement requirements |

These are **not three other names for CloudFront**. They place compute/storage capacity near where processing is needed, whereas CloudFront primarily addresses content delivery and HTTP(S) routing. Feature availability, supported locations, connectivity back to the parent Region, and costs must be checked separately before selecting them.

## 7. Sample Design: An E-Commerce Website Serving Users in Vietnam

Suppose a system has catalog pages, product images, a shopping cart API, and orders. The team selects `ap-southeast-1` as an **illustrative** Region after evaluating latency, features, regulations, and budget; and chooses two independent AZs to deploy the application.

~~~mermaid
flowchart TB
    U["User / Browser"] -->|1. DNS lookup| DNS["Route 53"]
    DNS -.->|DNS response| U
    U -->|2. HTTPS| CF["CloudFront PoP / cache"]
    CF -->|3. Cache miss: images, static files| S3
    CF -->|3. API forwarded to origin| ALB

    subgraph R["Region ap-southeast-1"]
        S3["S3 Standard - Regional storage"]
        ALB["Application Load Balancer"]
        subgraph A["Availability Zone A"]
            AppA["App A - private subnet"]
            DBA["RDS Primary - initial state"]
        end
        subgraph B["Availability Zone B"]
            AppB["App B - private subnet"]
            DBB["RDS Standby - initial state"]
        end
        ALB --> AppA
        ALB --> AppB
        AppA --> DBA
        AppB --> DBA
        DBA -.->|Multi-AZ synchronous replication| DBB
    end
~~~

*This diagram illustrates the logical flow and an RDS Multi-AZ DB instance model with one standby; it does not depict full NAT, routing, TLS, security controls, or all RDS topologies. After failover, the Primary role may move to the other AZ.*

### 7.1. How the Components Work Together

1. **Route 53** answers DNS queries for the domain; the browser then opens an HTTPS connection to the appropriate CloudFront endpoint.
2. **CloudFront** serves cached images and static assets; cache misses go to **S3 Standard**. For API requests, policies forward traffic to the **ALB**, with caching disabled as needed for dynamic/private content.
3. **ALB** receives application requests and distributes them across healthy targets in **AZ A** and **AZ B**. The application team must deploy multiple instances or tasks across AZs and enable health checks.
4. **RDS Multi-AZ** maintains a synchronous standby in the other AZ (for a single-standby Multi-AZ DB instance); under eligible failure conditions, RDS can fail over automatically. The application still needs to handle dropped connections and implement safe retries.
5. **CloudWatch, logs, and alarms** track error rates, response times, target health, database status, and cache performance; recovery testing verifies the system meets expectations.

### 7.2. When One AZ Experiences an Outage

Suppose AZ A becomes unavailable:

- ALB stops routing traffic to unhealthy targets in AZ A and continues with targets in AZ B, provided AZ B has sufficient capacity.
- If the RDS Primary was in AZ A and Multi-AZ operates as designed, RDS promotes the standby. A **brief interruption** can occur during failover, so the application needs proper retries, timeouts, and connection management.
- CloudFront can still serve currently cached objects. This **does not guarantee** the entire API works if the origin or data is unavailable.
- Verify that remaining components—such as NAT, background services, queues, caches, secrets, routing, and capacity—do not create a single point of failure.

If the **entire Region** becomes unable to serve traffic, two AZs within the same Region are not enough. Recovering in a second Region requires a **Disaster Recovery (DR)** plan, replicated data, and deployment capability there.

### 7.3. RTO and RPO Help Choose Redundancy Levels

- **RTO (Recovery Time Objective):** the maximum downtime target acceptable to the business.
- **RPO (Recovery Point Objective):** the maximum acceptable data loss target measured in time.

For example, a target of "recover within minutes, lose at most a few minutes of data" is completely different from "recover within one day from a backup." Do not infer real RTO/RPO values merely from labels like **Multi-AZ** or **Multi-Region**: they must be measured through drills, specific configurations, and operational procedures.

## 8. Choosing an Architecture for the Right Type of Risk

| Practical need | Model to consider | Reason |
| --- | --- | --- |
| Personal experimentation, downtime acceptable | Single Region, possibly single AZ for some components | Simpler and lower cost, accepting lower fault tolerance |
| Application must continue when one AZ is lost | Single Region, **Multi-AZ** for critical tiers | Reduces dependence on a single physical location |
| Distant users need fast loading of images and static files | CloudFront in front of origin | Reduces distance and origin fetches for popular content |
| Global API needing static IPs and optimized TCP/UDP paths | Evaluate Global Accelerator | Optimizes connection to endpoints, not reliant on content caching |
| Must survive loss of an entire Region | **Multi-Region** DR design aligned with RTO/RPO | Recovers outside the Regional failure boundary |
| Processing near physical facilities or 5G networks | Local Zones, Wavelength, or Outposts as appropriate | Places select compute capacity at the required location |

### 8.1. Three Common Region-Level DR Patterns

1. **Backup and restore:** store backups that can be restored in another Region; operational cost is usually lower, while recovery time can be long.
2. **Pilot light / warm standby:** maintain part or most of the standby infrastructure and required data; shortens failover time at higher cost and complexity.
3. **Active-active:** multiple Regions serve traffic simultaneously; can minimize downtime but adds complexity in data, consistency, concurrent writes, orchestration, and operations.

Which model fits depends on business requirements; there is no single best choice for every application.

## 9. Security, Cost, and Operational Implications

**Security and data**

- Review IAM under least privilege, separation of public/private resources, TLS, encryption, and origin access controls.
- CloudFront is a global network: under strict data residency requirements, examine cache locations, logs, data flows, global services, and specific terms. Choosing a Region for the database **does not automatically solve all data residency issues**.
- Never expose a database directly to the Internet simply because users are distant; place public-facing services at the ingress layer and protect networks/application layers appropriately.

**Cost**

- Every EC2/task replica, standby database, and data path has a cost. **Multi-AZ** increases fault tolerance but requires an appropriate budget.
- Data transfer between AZs, between Regions, out to the Internet, and through certain intermediary services can incur different charges; verify the pricing policy of each service and path.
- CloudFront incurs traffic, request, and feature charges, while potentially reducing origin load when caching is effective. Evaluate total cost against real traffic patterns.
- If outbound access from private subnets is needed, consider per-AZ egress design and VPC endpoint options to reduce dependency/cost when appropriate.

**Monitoring and operations**

- Track ALB target health, HTTP error rates, end-to-end latency, RDS connections/alarms, cache hit ratio, and cost.
- Create intentional alarms; monitor from representative user locations to detect network issues outside AWS.
- Rehearse scenarios such as "loss of one AZ," "slow origin," "cache miss spike," "database failover," and, if required, "standby Region takeover."
- Use Infrastructure as Code to describe subnets, AZs, routing, and application configuration, making environments reproducible during recovery.

## 10. Hands-On Infrastructure Inspection Exercise (No Resources Created)

**Prerequisites:** AWS CLI installed and credentials configured with `ec2:DescribeRegions` and `ec2:DescribeAvailabilityZones` permissions. The commands below only read infrastructure metadata; output depends on the account and Region.

**Step 1 — View Regions and opt-in status from the account:**

~~~bash
aws ec2 describe-regions --all-regions --region ap-southeast-1 --query "Regions[].{Region:RegionName,Access:OptInStatus}" --output table
~~~

**Step 2 — View AZ names, AZ IDs, and states in Singapore:**

~~~bash
aws ec2 describe-availability-zones --region ap-southeast-1 --query "AvailabilityZones[].{AZ:ZoneName,AZ_ID:ZoneId,State:State,Type:ZoneType}" --output table
~~~

**Step 3 — Interpret the results:**

- Identify the Region code rather than using the geographic name when configuring CLI/SDK/IaC.
- Note which AZs have state `available`; cross-reference `AZ` and `AZ_ID`.
- Suppose you create a subnet in the first AZ: explain why you must create a **second subnet** in a different AZ if you need to run the application in a Multi-AZ model.
- Compare AWS service availability, pricing, and network latency before deciding on a Region for a real application.

**Paper design exercise:** Starting from the `10.20.0.0/16` VPC in Section 4, sketch two private subnets across two AZs, an ALB with healthy targets in both AZs, and an RDS Multi-AZ setup. Mark every point that could cause the system to stop serving requests if AZ A fails; propose how to mitigate each point.

## 11. Common Misconceptions

| Statement | What to understand correctly |
| --- | --- |
| "Two EC2 instances in the same AZ is Multi-AZ." | Both machines still depend on the same AZ; you must deploy in **different AZs**. |
| "Having two AZs survives every AWS outage." | Multi-AZ does not automatically solve Region-wide outages, logic bugs, deleted data, or widespread misconfigurations. |
| "With S3 Standard, you must manually pick three AZs to store files." | AWS manages multi-AZ redundancy for this storage class; you do not place individual objects into a specific AZ. |
| "AZ `1a` in two accounts always maps to the same location." | In some cases name mappings differ; use **AZ ID** when matching physical locations across accounts. |
| "CloudFront makes the application run at the edge." | Caching and select edge functions run close to users; the origin and database still require separate design. |
| "Route 53 proxies every request to the backend." | Route 53 handles DNS resolution/routing; the client then connects using the DNS result. |
| "CloudFront + two AZs is enough for every DR requirement." | If targets include Region-level failure, you must add recovery design aligned with RTO/RPO. |
| "Choosing the nearest Region is always cheapest and fastest." | You must test real network latency, review pricing, check service availability, and verify data regulations. |

## 12. Summary

Keep three questions in mind before drawing an AWS architecture:

1. **Region:** Which geographic area should host the application and data to balance latency, available services, compliance, cost, and recovery needs?
2. **Availability Zone:** Do critical components have redundant replicas across independent fault locations within the Region?
3. **Edge infrastructure:** How should content, DNS, or network paths be optimized for users, and which requests still need to return to the origin?

A solid deployment choice does not stop at picking a Region name or checking a "Multi-AZ" box. You must examine **each component's fault scope**, **data paths**, and **monitoring and recovery mechanisms**, then validate them through measurement and drills.

### Official AWS Documentation for Further Reading

- [AWS Regions and Availability Zones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions-availability-zones.html) — definitions of Regions, AZs, Local Zones, and Wavelength Zones.
- [AWS Availability Zones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-availability-zones.html) and [AZ IDs](https://docs.aws.amazon.com/global-infrastructure/latest/regions/az-ids.html) — AZ codes and cross-account mapping.
- [Subnets for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html) — single-AZ subnet scope.
- [How CloudFront delivers content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HowCloudFrontWorks.html) — caching at PoPs, regional edge caches, and origins.
- [Regions and Zones for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html) — Local Zones, Wavelength, and Outposts.
- [Amazon RDS Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) — standby replicas and synchronous cross-AZ replication.
- [AWS Well-Architected: Disaster Recovery Strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html) — choosing redundancy levels by RTO/RPO.
