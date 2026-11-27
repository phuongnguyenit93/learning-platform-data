# Multi-AZ VPC Design for Production Applications

> **Chapter:** VPC Networking  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; practice designing secure, observable, resilient, and cost-controlled systems.

A production application cannot treat "having two servers" as sufficient redundancy. If both servers reside in the same Availability Zone (AZ), share a single egress path, or depend on a single database without failover, a single infrastructure failure can bring down the entire service. **Multi-AZ VPC design** structures networks and resources so a localized fault does not eliminate every path serving the application.

This lesson uses an e-commerce application within one AWS Region deployed across **two independent AZs**. All CIDRs, resource names, instance counts, and the Region are illustrative. In real deployments, verify available AZs in your account, data requirements, service capabilities, quotas, performance, and current pricing.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why multiple AZs are needed, the failure scope a multi-AZ design addresses, and the limits of a single Region.
2. Partition a VPC into public, private application, and private database subnets **per AZ** with scalable CIDR allocations.
3. Design route tables, Internet Gateways (IGWs), NAT Gateways, and VPC endpoints to avoid unnecessary network dependencies.
4. Coordinate Application Load Balancers (ALBs), Auto Scaling, Security Groups, and RDS Multi-AZ to sustain service during an AZ outage.
5. Set availability targets, serving capacity, and RTO/RPO; plan observability, recovery drills, and cost control.
6. Read an Infrastructure as Code network configuration and inspect a design using read-only AWS CLI commands.

## 2. Understanding "Multi-AZ" Properly

An **AWS Region** is a geographic area; each Region contains multiple **Availability Zones** engineered for isolated power, networking, and physical infrastructure while interconnected over low-latency links. A **subnet resides entirely within one AZ**, whereas a **VPC spans a Region**. Therefore, an application spanning two AZs must provision dedicated subnets in each AZ.

| Scope | Example Resources | Fault-Tolerance Implication |
| --- | --- | --- |
| **AZ** | EC2 instances, EBS volumes, subnets, zonal NAT Gateways | An AZ outage can disrupt resources located in that AZ |
| **Region** | VPCs, many Region-scoped managed services | AZs can be combined, yet the Region remains a larger fault domain |
| **Global / Edge** | Route 53, CloudFront | Assists routing/delivery; does not automatically make origins or databases multi-Region |

**Multi-AZ does not mean Multi-Region.** Two AZs mitigate localized failures at one site; Region-wide incidents, shared software bugs, bad IAM changes, accidental data deletion, or third-party outages still require separate strategies.

### 2.1. Start with Business Objectives

Before picking EC2 types or subnet sizes, clarify:

- **RTO (Recovery Time Objective):** target duration to restore functionality after an outage.
- **RPO (Recovery Point Objective):** target acceptable data loss expressed in time.
- **SLO:** measurable service target, such as successful request ratio and latency over a time window.
- **Load during AZ loss:** how many requests must the surviving AZ absorb, and for how long?
- **Operability:** can the team observe failures, recover, roll back, and run periodic drills?

You cannot infer actual RTO, RPO, or availability percentages solely from checking a "Multi-AZ" box. They depend on service settings, network paths, surviving capacity, and application recovery time.

## 3. Reference Architecture for a Production Application

Suppose a system has a web UI, API, order data, and product images. Proposed architecture:

~~~mermaid
flowchart TB
    U["Users"] --> DNS["Route 53 / domain name"]
    DNS -.->|"DNS resolution"| U
    U --> EDGE["CloudFront + WAF (as needed)"]
    EDGE --> ALB["Application Load Balancer - Internet facing"]

    subgraph VPC["VPC 10.40.0.0/16 - single AWS Region"]
        ALB
        subgraph A["Availability Zone A"]
            PA["Public subnet A: ALB nodes + NAT-A"]
            AA["Private app subnet A: EC2/ECS app"]
            DA["Private DB subnet A: RDS primary (initial)"]
        end
        subgraph B["Availability Zone B"]
            PB["Public subnet B: ALB nodes + NAT-B"]
            AB["Private app subnet B: EC2/ECS app"]
            DB["Private DB subnet B: RDS standby (initial)"]
        end
        ALB --> AA
        ALB --> AB
        AA --> RDS["RDS Multi-AZ Endpoint"]
        AB --> RDS
        RDS --> DA
        DA -.->|"Data replication"| DB
        AA -.->|"Egress in AZ A"| PA
        AB -.->|"Egress in AZ B"| PB
    end
    EDGE -.->|"Images and static assets"| S3["Amazon S3 Standard - Region"]
    AA -.->|"AWS APIs via endpoints (where applicable)"| AWS["Regional AWS services"]
    AB -.->|"AWS APIs via endpoints (where applicable)"| AWS
~~~

*This diagram depicts logical relationships, not every packet hop. The ALB is a logical resource using subnets in both AZs; RDS primary/standby illustrates a **Multi-AZ DB instance with one standby**. Not every TLS, IAM, route, NAT, Security Group, or cache detail is shown.*

Core request flow:

1. Users resolve DNS and connect over HTTPS. CloudFront/WAF is an optional layer useful for caching, lower delivery latency, or edge filtering.
2. The ALB spans at least two subnets in two AZs, checks target health, and distributes requests to targets in private app subnets.
3. Business logic runs on EC2 or ECS services/Auto Scaling with instances or tasks in both AZs.
4. The app connects to the RDS Multi-AZ endpoint; RDS manages primary/standby roles and failover per the chosen configuration.
5. Images/static assets live in S3 Standard; calls to other AWS services can use appropriate VPC endpoints to minimize NAT egress.
6. CloudWatch logs, metrics, and alarms surface health across every layer rather than checking EC2 status alone.

In environments without CloudFront, users can connect directly to the ALB over HTTPS and DNS; adjust routing, certificates, and edge protections accordingly.

## 4. Per-AZ IP and Subnet Plan

### 4.1. Partitioning CIDRs by Function

Use IPv4 VPC `10.40.0.0/16` as an example. Using `/24` subnets keeps the illustration readable; production systems must size for ENI counts, pod IPs, growth plans, network interconnects, and avoid CIDR overlaps with on-premises or peered VPCs.

| AZ | Subnet | CIDR | Hosted Components |
| --- | --- | --- | --- |
| A | `public-a` | `10.40.0.0/24` | Public ALB ENIs, NAT-A |
| B | `public-b` | `10.40.1.0/24` | Public ALB ENIs, NAT-B |
| A | `app-private-a` | `10.40.10.0/24` | EC2/ECS application |
| B | `app-private-b` | `10.40.11.0/24` | EC2/ECS application |
| A | `db-private-a` | `10.40.20.0/24` | RDS subnet group |
| B | `db-private-b` | `10.40.21.0/24` | RDS subnet group |

AWS reserves **5 IPv4 addresses per subnet**; a `/24` subnet has 256 total addresses and at most 251 usable IPv4 addresses before other constraints. Never size solely by EC2 instance count: ALB, ECS `awsvpc`, EKS, NAT, RDS, and interface VPC endpoints also consume IPs/ENIs.

**Subnet separation is not an automatic security control.** Calling a subnet "private" does not protect resources if routes, public IPs, or access policies are misconfigured. Public/private roles must be enforced via **routing** and reachability controls.

### 4.2. When Do You Need Three AZs?

Two AZs are the common minimum for tolerating a single-AZ failure, and several AWS services require at least two AZs. Three AZs add flexibility during load balancing, maintenance, or outages, while increasing complexity across subnets, NAT paths, data transfer fees, and capacity math.

With three AZs, provision **a complete set of subnets in AZ C**: do not add EC2 instances in AZ C while omitting ALB subnets, database subnets, and local egress paths. For specific services, verify minimum/maximum supported AZs and service data models.

### 4.3. AZ Names vs. AZ IDs

Names like `ap-southeast-1a` can map to different physical data centers across different AWS accounts. When comparing exact physical alignment across accounts, check the **AZ ID** (e.g., `apse1-az1`). Within a single account, use the AZ names returned by APIs; never assume "AZ a" maps to the same physical facility in every account.

## 5. Route Tables, Internet Gateways, and Bidirectional Paths

A VPC includes a `local` route for the VPC CIDR so subnets in the VPC can route to one another unless custom routing overrides it. Whether packets are permitted still depends on Security Groups, Network ACLs, listeners, the OS, and other security layers.

### 5.1. Public Subnets

A public subnet typically associates with a route table containing:

| Destination | Target | Meaning |
| --- | --- | --- |
| `10.40.0.0/16` | `local` | Intra-VPC path |
| `0.0.0.0/0` | `igw-prod` | IPv4 Internet ingress/egress via Internet Gateway |

For an EC2 instance to communicate directly with the Internet via an IGW, it also needs a **public IPv4 or Elastic IP** and matching SG/NACL rules. Never place application servers or databases in public subnets merely to simplify deployment.

For an internet-facing ALB, AWS requires subnets in **at least two AZs**. The ALB accepts traffic at the public tier and forwards to targets in private subnets; targets do not need public IPs.

### 5.2. Private Application Subnets

Applications in private subnets have no direct default route to an Internet Gateway. When outbound **IPv4 Internet connections** are required, you can use zonal NAT Gateways in public subnets.

| Route Table | Destination | Target |
| --- | --- | --- |
| `rt-app-a` | `10.40.0.0/16` | `local` |
| `rt-app-a` | `0.0.0.0/0` | `nat-a` in AZ A |
| `rt-app-b` | `10.40.0.0/16` | `local` |
| `rt-app-b` | `0.0.0.0/0` | `nat-b` in AZ B |

This is the **per-AZ egress** pattern: apps in AZ A route through NAT-A, and apps in AZ B route through NAT-B. If both AZs shared NAT-A and AZ A failed, apps in AZ B might stay running yet lose Internet egress. Per-AZ NAT increases cost, while eliminating cross-AZ dependency and avoiding cross-AZ transfer hop charges.

A NAT Gateway does not allow the Internet to initiate direct connections into private instances. It serves connections initiated from the private network. For public inbound access, use an ALB, reverse proxy, or explicit ingress architecture.

**Note:** AWS offers multiple NAT deployment types/modes depending on time and Region. When applying a per-AZ NAT pattern, verify the NAT type, availability scope, quotas, and routing behavior. Do not assume all NAT options share identical failure domains.

### 5.3. Private Database Subnets

For databases that need no outbound Internet access, their dedicated route table may need only `local` and any required internal/endpoint routes. **Do not add a `0.0.0.0/0` route to NAT** for DB subnets without a clear, justified requirement.

Databases still need reachability from the application tier across the VPC, restricted by Security Groups and database authentication. Setting `PubliclyAccessible=false` on RDS is an important control, alongside auditing DB subnet groups and network policies.

### 5.4. VPC Endpoints to Reduce Unnecessary Egress

Applications may need S3, DynamoDB, Secrets Manager, Systems Manager, ECR, CloudWatch Logs, or other AWS services.

| Endpoint | General Mechanism | When to Consider |
| --- | --- | --- |
| **Gateway endpoint** | Supports S3/DynamoDB via route tables and service prefix lists | Avoid Internet/NAT for supported same-Region service flows |
| **Interface endpoint** | Places dedicated ENIs/IPs in selected subnets via AWS PrivateLink | Access compatible service APIs inside private networks |

Gateway endpoints for S3/DynamoDB do not share the same pricing model as interface endpoints; interface endpoints typically incur per-AZ hourly charges and data-processing fees. Gateway endpoints handle only specific services, routes, and conditions—they **do not replace all NAT traffic**.

For interface endpoints, select subnets across multiple AZs for AZ fault tolerance, configure DNS/SGs/endpoint policies appropriately, and test application flows. For services needing multiple endpoints such as ECR, account for image pulls, S3 object fetches, and logging flows together.

## 6. Load Balancing and Application Tier per AZ

### 6.1. Application Load Balancer

ALB is a Layer 7 load balancer. In this architecture:

- HTTPS `443` listener uses an ACM certificate matching the domain name.
- ALB is enabled across two public subnets in two AZs.
- Target group points to the app listening on `HTTP 8080` or `HTTPS` per design, with health checks on an endpoint such as `/health/ready`.
- EC2 instances/ECS tasks are distributed across app subnets A and B.
- ALB forwards requests only to targets considered healthy by service health check rules.

**Application health checks** should reflect actual readiness to serve requests: has startup finished, are critical dependencies reachable, or is the instance draining? If health checks are too heavy or depend on non-critical external services, a minor downstream glitch can mark every target unhealthy. Separate liveness and readiness checks where the platform supports them.

Cross-zone load balancing on an ALB distributes traffic across targets in all enabled AZs per service settings. Understand that **a healthy ALB does not mean the entire application is healthy**; a target group can have zero healthy instances if app code or the database fails.

### 6.2. Auto Scaling and Capacity Allocation

Suppose the app runs in an **EC2 Auto Scaling Group (ASG)** across `app-private-a` and `app-private-b`, with a minimum of four instances normally. The ASG replaces unhealthy instances and balances across AZs subject to capacity availability and configuration.

Suppose load testing shows each instance safely handles up to 120 requests/second before hitting performance limits. Targeting **70%** peak utilization gives an effective capacity of **84 requests/second/instance**. For peak traffic of 200 requests/second:

~~~text
Capacity required when one AZ goes down = 200 req/s
Target capacity per instance = 120 × 70% = 84 req/s
Surviving instances required = ceil(200 / 84) = 3
~~~

With two AZs balanced evenly, you may need **at least three instances per AZ** (six total) so that after losing one AZ, the three surviving instances handle peak load *under test assumptions*. This figure is illustrative; real capacity can be constrained by CPU, memory, DB connections, concurrency, queues, and instance boot time.

Do not rely solely on the ASG scaling out **after an AZ has already failed**: provisioning new instances, booting, pulling images, registering targets, and passing health checks all take time. To meet strict SLOs, maintain **pre-provisioned headroom**, while checking EC2 quotas, capacity reservations, or diversified instance types if needed.

### 6.3. Other Compute Services

With **ECS**, place tasks across multi-AZ subnets and configure deployment settings, load balancers, and health checks properly. With **EKS**, distribute nodes/pods, configure topology spread constraints, PodDisruptionBudgets, and assess AZ-loss impact. With VPC-attached **Lambda**, Lambda manages compute scaling, yet subnets/ENIs and egress paths to downstream services must still be properly configured. Do not assume selecting multiple subnets automatically solves concurrency quotas or database bottlenecks.

## 7. Data and Stateful Services Must Survive AZ Failures

Stateless application tiers are straightforward to replicate; databases, login sessions, caches, and storage require careful design.

### 7.1. RDS Multi-AZ Does Not Equal Read Replica

With an **RDS Multi-AZ DB instance deployment**, AWS maintains a **primary** and a **synchronous standby** in a different AZ. Applications connect to the DB endpoint; when failover conditions occur, RDS promotes the standby. Applications must handle dropped connections, DNS/connection pool refreshes, retries, and in-flight transactions during switchover.

A **Read Replica** primarily serves read scaling and specific replication/recovery scenarios depending on setup; it is not automatically equivalent to Multi-AZ failover above. An RDS Multi-AZ **DB cluster** has its own topology and behavior (including readable DB instances), so verify the exact deployment type before designing.

For RDS, a **DB subnet group** generally requires subnets in **at least two AZs**. Never create a DB subnet only in AZ A and expect a standby to appear automatically in AZ B. Verify database engine, deployment option, scaling behavior, and backup/restore requirements.

### 7.2. Other Data Resources

| Component | Scope / Option | What to Verify |
| --- | --- | --- |
| **EBS** | Volume bound to a single AZ | Live volumes cannot move across AZs; require snapshots/backups and restore procedures |
| **S3 Standard** | Region-wide object storage with AWS-managed multi-AZ durability | S3 Standard differs from One Zone classes; check data protection policies and access controls |
| **EFS Regional** | File system replicated across AZs, with mount targets in matching AZs | Mount target reachability, SG/NFS rules, and transfer costs |
| **ElastiCache** | Multi-AZ/failover options vary by engine and mode | Verify replication groups, cluster mode, endpoints, and client reconnect logic |
| **DynamoDB** | Managed service with Regional availability | Consistency model, throughput limits, and multi-Region recovery needs |
| **SQS** | Regionally managed queues | Retries, dead-letter queues, deduplication, and workflow durability |

Never store critical business state solely in one EC2 instance's memory or local disk without a recovery strategy. For user sessions, use tokens or an appropriate managed session store; application code should implement **idempotency** so retries never create duplicate orders or payments.

### 7.3. During Database Failover

An order-write request may hit a network error or dropped connection right as RDS switches primary. Never blindly retry every write: if you do not know whether the transaction committed, retrying can duplicate records. Use **idempotency keys**, bounded retries, exponential backoff, transaction state checks, and error monitoring.

Multi-AZ improves infrastructure fault tolerance but does not protect against **accidental data deletion, bad migrations, faulty SQL**, or Regional disasters. Maintain backups, point-in-time recovery (where supported), schema change controls, and recovery drills.

## 8. Network Authorization and Production Security

Design around **deny by default and least privilege** at every layer:

| Object | Suggested Inbound | Outbound to Review |
| --- | --- | --- |
| **ALB Security Group** | HTTPS `443` from clients/CloudFront per architecture | App SG on app port `8080`, health checks per config |
| **App Security Group** | `8080` from ALB SG | DB SG `5432`, VPC endpoints, required services |
| **DB Security Group** | `5432` only from App SG | Scoped to actual DB/service needs, not wide open by default |
| **VPC endpoint SG** (interface) | HTTPS from App SG/appropriate CIDRs | Return traffic via connection tracking |

Security Groups are **stateful**, so you do not open reverse ephemeral ports for return traffic of tracked flows as with NACLs. NACLs are **stateless** and attach to subnets; if using custom NACLs, permit both inbound and outbound directions including service ports and the initiator's ephemeral ports. Lower rule numbers evaluate first; a Deny before an Allow can block legitimate flows.

Additional controls:

- Attach **IAM roles** to workloads; avoid storing long-lived access keys in images, source code, or unprotected environment variables.
- Store secrets in **AWS Secrets Manager** or an appropriate secrets solution with encryption and access controls.
- Enforce TLS at public boundaries; consider encrypting ALB → app and app → DB connections as required.
- Administer instances via **AWS Systems Manager Session Manager** where appropriate instead of opening public SSH/RDP; provision SSM endpoints/NAT, agent, and IAM roles.
- Enable S3 Block Public Access appropriately; for CloudFront with private S3 origins, use **Origin Access Control (OAC)** where applicable.
- Deploy AWS WAF for HTTP(S) at CloudFront/ALB and monitor anomalous traffic; WAF does not replace application-level authentication/authorization.
- Isolate dev, staging, and production via separate accounts/VPCs/permissions; restrict permissions to edit route tables, Security Groups, NACLs, and deployment pipelines.

**Note:** a private subnet does not mean "unhackable." If an application is compromised, attackers can attempt calls to internal services, metadata, or resources allowed by the IAM role. Restrict network paths, IAM, data access, and application behavior together.

## 9. Blast Radius Failure Analysis

Production design must determine not only *how many AZs exist*, but **what breaks when a single component fails**.

| Incident | Expected Architectural Behavior | What Must Be Verified |
| --- | --- | --- |
| Single EC2 instance fails | ALB deregisters target; ASG replaces instance | Health checks, remaining targets, replacement startup time |
| **AZ A lost** | AZ B apps and NAT-B keep running; ALB routes to healthy targets | Sufficient remaining capacity, AZ B uses NAT-B, no hidden AZ A single dependencies |
| NAT-A fails | App A egress impacted; App B uses NAT-B | Each private route table points to its own AZ's NAT |
| RDS primary in AZ A fails | RDS Multi-AZ fails over to standby in AZ B per service behavior | Connection retries, transaction handling, post-failover latency and connectivity |
| One ALB target unhealthy | ALB shifts traffic to healthy targets | Readiness endpoint, health check thresholds, ECS/ASG replacement |
| Bad release deployed to both AZs | **Both AZs can break simultaneously** | Rolling/canary deployments, rollback, release testing, feature flags |
| Data deleted or bad migration | Multi-AZ replicates faulty changes too | Backups, PITR, and data restoration procedures |
| **Entire Region unavailable** | Single-Region architecture stops serving | Multi-Region DR if required by business, clear RTO/RPO |

### 9.1. Running an AZ-Loss Drill

1. Before testing, define SLOs, abort criteria, owners, customer impact, and rollback steps.
2. Verify infrastructure has targets in both AZs, autoscaling groups, and Multi-AZ database configuration active.
3. Simulate losing one AZ/target group using approved methods in a **test environment**, measuring detection time, traffic shift duration, and error counts.
4. Observe ALB target health, ASG activity, RDS events, DB connection counts, p95/p99 latency, and error rates.
5. Verify egress from the surviving AZ, health checks, queue consumers, and background jobs.
6. Restore configuration, verify load balancing returns to normal, and document any gaps against RTO/SLO.

Never disrupt production directly to "prove Multi-AZ" without an approved test procedure and strict blast-radius limits.

## 10. Observability, Alerting, and Operations

### 10.1. Key Signals to Watch

| Layer | Monitored Signals |
| --- | --- |
| **ALB** | `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime`, `HealthyHostCount` |
| **EC2/ASG** | CPU, memory via CloudWatch Agent if configured, instance status, ASG activity, in-service count |
| **RDS** | CPU, connections, free storage, storage latency, RDS events, failover and replication status |
| **NAT Gateway** | Active connections, bytes processed, packet drops/port allocation errors per service metrics |
| **VPC Flow Logs** | Metadata for ACCEPT/REJECT flows within the chosen capture scope |
| **Application** | Throughput, error rate, p95/p99 latency, retries, queue lag, transaction failures, idempotency conflicts |
| **Cost** | NAT hours/data processing, load balancers, EC2, RDS Multi-AZ, data transfer, VPC endpoints |

Do not treat `HealthyHostCount > 0` as proof the system is safe: when only one healthy target remains, requests still succeed while all redundancy is gone. Set alarms against the **minimum target count needed for fault tolerance** and serving capacity.

### 10.2. Logging and Tracing

- Use **CloudTrail** for critical control-plane changes such as route tables, subnet associations, Security Groups, and IAM; logged event types depend on trail/event data store settings.
- Enable **VPC Flow Logs** within the scope needed for investigation and optimize storage/retention; `REJECT` records alone do not identify the exact blocking rule.
- Enable **ALB access logs** per audit and request analysis needs; account for cost and sensitive data.
- Centralize application logs, correlation/request IDs, and distributed tracing to isolate root causes across ALB, app, DB, and queues.
- Use **VPC Reachability Analyzer** to validate network path configs between supported endpoints; corroborate analysis results with real tests.

## 11. Cost Control in Multi-AZ Deployments

High availability has a cost. Calculate **whole-system cost**, rather than simply doubling EC2 counts:

| Component | Cost Driver | How to Evaluate |
| --- | --- | --- |
| **Multi-AZ Compute** | Redundant instances/tasks running continuously | Size capacity for AZ loss, load, and SLO; optimize instance types and autoscaling |
| **RDS Multi-AZ** | Standby compute and storage/I/O depending on deployment option | Compare exact pricing by engine, instance size, and deployment model |
| **Per-AZ NAT Gateway** | Hourly and data-processing fees; multiplied by NAT count | Measure real egress; use VPC endpoints where justified |
| **Cross-AZ data transfer** | Traffic crossing AZ boundaries per source/destination and service | Map flows, check current pricing; avoid unnecessary cross-AZ hops |
| **ALB** | Hourly uptime and Load Balancer Capacity Units (LCUs) per pricing model | Measure request rate, connections, rule evaluations, and bytes processed |
| **Interface endpoints** | Per-AZ hourly fees and bytes processed | Provision only needed endpoints across required AZs |
| **Logs, metrics, backups** | Storage, ingestion, queries, retention | Set retention, storage tiers, cost alarms, and budgets |

NAT Gateways can become expensive when pulling container images, shipping telemetry, or downloading dependencies from the Internet. If workloads in private subnets call ECR/S3/CloudWatch, evaluate required endpoints. Still, **never assume endpoints are always cheaper than NAT**: compare hourly fees, AZ counts, bytes processed, and actual traffic.

**Trade-off comparison example:** sharing one NAT-A across two AZs reduces NAT Gateway count but ties AZ B's egress to AZ A and can incur cross-AZ transfer; two per-AZ NATs increase fixed hourly fees while improving fault isolation. Base the decision on business impact of losing egress, not lowest sticker price alone.

## 12. Representing the Network with Infrastructure as Code

Infrastructure as Code (IaC) reproduces subnets, routes, NATs, and permission boundaries consistently. The Terraform snippet below defines a **minimal IPv4 network foundation** across two AZs with one zonal NAT Gateway per AZ. It is an **illustrative skeleton**—it does not yet create ALB/ASG/RDS/Security Groups or operational policies and will incur charges if applied.

AZ names must come from your actual account and Region; pick two distinct available AZs. The example provisions two database subnets with internal-only routing and adds an S3 gateway endpoint to private route tables.

~~~hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "ap-southeast-1"
}

variable "az_names" {
  type        = list(string)
  description = "Two distinct available AZs in the same account/Region"

  validation {
    condition     = length(var.az_names) == 2 && length(distinct(var.az_names)) == 2
    error_message = "Select exactly two distinct AZs."
  }
}

locals {
  zones = {
    a = {
      az          = var.az_names[0]
      public_cidr = "10.40.0.0/24"
      app_cidr    = "10.40.10.0/24"
      db_cidr     = "10.40.20.0/24"
    }
    b = {
      az          = var.az_names[1]
      public_cidr = "10.40.1.0/24"
      app_cidr    = "10.40.11.0/24"
      db_cidr     = "10.40.21.0/24"
    }
  }
}

resource "aws_vpc" "prod" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "prod-vpc" }
}

resource "aws_internet_gateway" "prod" {
  vpc_id = aws_vpc.prod.id
  tags   = { Name = "prod-igw" }
}

resource "aws_subnet" "public" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.prod.id
  availability_zone       = each.value.az
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false
  tags = { Name = format("prod-public-%s", each.key) }
}

resource "aws_subnet" "app" {
  for_each          = local.zones
  vpc_id            = aws_vpc.prod.id
  availability_zone = each.value.az
  cidr_block        = each.value.app_cidr
  tags = { Name = format("prod-app-%s", each.key) }
}

resource "aws_subnet" "db" {
  for_each          = local.zones
  vpc_id            = aws_vpc.prod.id
  availability_zone = each.value.az
  cidr_block        = each.value.db_cidr
  tags = { Name = format("prod-db-%s", each.key) }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.prod.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.prod.id
  }
  tags = { Name = "prod-public-routes" }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  for_each = local.zones
  domain   = "vpc"
}

resource "aws_nat_gateway" "zonal" {
  for_each      = local.zones
  subnet_id     = aws_subnet.public[each.key].id
  allocation_id = aws_eip.nat[each.key].id
  depends_on    = [aws_internet_gateway.prod]
  tags = { Name = format("prod-nat-%s", each.key) }
}

resource "aws_route_table" "app" {
  for_each = local.zones
  vpc_id   = aws_vpc.prod.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.zonal[each.key].id
  }
  tags = { Name = format("prod-app-routes-%s", each.key) }
}

resource "aws_route_table_association" "app" {
  for_each       = aws_subnet.app
  subnet_id      = each.value.id
  route_table_id = aws_route_table.app[each.key].id
}

resource "aws_route_table" "db" {
  vpc_id = aws_vpc.prod.id
  tags   = { Name = "prod-db-routes-local-only" }
}

resource "aws_route_table_association" "db" {
  for_each       = aws_subnet.db
  subnet_id      = each.value.id
  route_table_id = aws_route_table.db.id
}

data "aws_region" "current" {}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.prod.id
  vpc_endpoint_type = "Gateway"
  service_name      = format("com.amazonaws.%s.s3", data.aws_region.current.name)
  route_table_ids   = concat(
    [for rt in values(aws_route_table.app) : rt.id],
    [aws_route_table.db.id]
  )
}
~~~

**Key things to read in the code:**

1. `for_each = local.zones` creates subnets per AZ and uses the same `a`/`b` keys to pair each NAT with its matching-AZ route table.
2. Public route table points to the IGW; private app route tables point to their respective NATs. The DB route table has only the default local route, **no default Internet route**.
3. The S3 gateway endpoint adds S3 routes to selected route tables; this does not mean all AWS APIs traverse this endpoint.
4. `map_public_ip_on_launch = false` prevents new EC2 instances in public subnets from automatically getting public IPs; internet-facing ALBs are managed by AWS per separate configuration.
5. Terraform also requires a secure state backend, IaC execution permissions/policies, drift control, `plan` reviews, and additional ALB/ASG/RDS definitions. Never run `apply` on a production account directly from a lesson example.

To validate design logic, run `terraform fmt`, `terraform validate`, and `terraform plan` in an authorized test environment. Review the `plan` carefully since the example provisions NAT Gateways/EIPs and incurs charges.

## 13. Hands-On VPC Inspection with AWS CLI (Read-Only)

Examples use Region `ap-southeast-1` and placeholder IDs; substitute values from your account. You need AWS CLI credentials authorized for the corresponding `Describe` APIs. The commands below **do not create or delete resources**.

### 13.1. List VPCs and CIDRs

~~~bash
aws ec2 describe-vpcs \
  --region ap-southeast-1 \
  --query "Vpcs[].{VpcId:VpcId,CIDR:CidrBlock,Default:IsDefault}" \
  --output table
~~~

### 13.2. Match Subnets to AZs

~~~bash
aws ec2 describe-subnets \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "Subnets[].{Id:SubnetId,CIDR:CidrBlock,AZ:AvailabilityZone,AZ_ID:AvailabilityZoneId,FreeIPs:AvailableIpAddressCount}" \
  --output table
~~~

Verify that public/app/db subnets exist in **both AZs**; confirm non-overlapping CIDRs and sufficient free IPs for scaling and failover.

### 13.3. Inspect Route Tables by Subnet

~~~bash
aws ec2 describe-route-tables \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "RouteTables[].{Id:RouteTableId,Routes:Routes[].{Dest:DestinationCidrBlock,NAT:NatGatewayId,IGW:GatewayId},Subnets:Associations[].SubnetId}" \
  --output json
~~~

Look up the default routes of `app-private-a` and `app-private-b`. Do they point to two NATs in different AZs? Has an unintended `0.0.0.0/0` been added to the DB route table? Note: a route table **implicitly** attached via the main route table may not list a separate `SubnetId` under associations; distinguish explicit from main associations.

### 13.4. Inspect NATs by AZ

~~~bash
aws ec2 describe-nat-gateways \
  --region ap-southeast-1 \
  --filter Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "NatGateways[].{Id:NatGatewayId,Subnet:SubnetId,AZ:AvailabilityZone,State:State}" \
  --output table
~~~

If the response or CLI version omits the AZ field for your NAT type, cross-check `SubnetId` against `describe-subnets` to determine the **zonal NAT Gateway's** AZ. For other NAT types, check that type's documentation before concluding availability behavior.

### 13.5. Inspect ALB/ASG/RDS

~~~bash
aws elbv2 describe-load-balancers --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,AZs:AvailabilityZones[].ZoneName}" \
  --output json

aws autoscaling describe-auto-scaling-groups --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Desired:DesiredCapacity,Max:MaxSize,AZs:AvailabilityZones}" \
  --output json

aws rds describe-db-instances --region ap-southeast-1 \
  --query "DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,MultiAZ:MultiAZ,Public:PubliclyAccessible,PrimaryAZ:AvailabilityZone}" \
  --output table
~~~

Never rely solely on `MultiAZ=true` to declare that RTO/RPO targets are met. Inspect DB subnet groups, real topology, backups, application behavior, and failover test results.

## 14. Design and Verification Exercises

### Exercise 1 — Find Single Points of Failure

An architecture has an ALB in AZ A/B, three EC2 instances in AZ A and one EC2 instance in AZ B, while both private app subnets use NAT-A. The database is single-AZ RDS in AZ A.

**Question:** If AZ A is lost, which components stay up and why might the website still fail?

**Hint:** The ALB can continue accepting connections in AZ B and one EC2 instance in B remains running. However, capacity may be insufficient, private egress via NAT-A breaks, single-AZ RDS becomes unavailable, and endpoints may be impacted. Distribute workload/capacity intentionally, minimize cross-AZ egress dependencies, and implement database fault tolerance.

### Exercise 2 — Fill in the Routing Table

Using the CIDR layout in Section 4, complete:

| Subnet | Expected `0.0.0.0/0` Route | Should It Accept Direct Internet Requests? |
| --- | --- | --- |
| `public-a` | ? | ? |
| `public-b` | ? | ? |
| `app-private-a` | ? | ? |
| `app-private-b` | ? | ? |
| `db-private-a` | ? | ? |
| `db-private-b` | ? | ? |

**Sample answer:** public-a/public-b → IGW; app-a → NAT-A, app-b → NAT-B; the two DB subnets have no Internet default route unless strictly needed. Public requests should enter through the ALB, never directly to App/DB.

### Exercise 3 — Size Capacity for AZ Loss

Suppose peak load is **360 requests/second**, each instance safely serves **90 requests/second** at target SLO, and the system spans two AZs. Calculate how many surviving instances are required when one AZ is lost, and determine the minimum balanced configuration across the two AZs.

**Hint:** `ceil(360/90) = 4` surviving instances, so assuming even distribution and total loss of one AZ, you need at least **4 instances per AZ** (8 total), before adding headroom beyond assumptions, quotas/capacity limits, and other dependencies. If each instance hits 90 req/s in benchmark tests, add extra safety margin for traffic spikes.

### Exercise 4 — Design a Verification Test

Write a plan to test single-AZ failure without impacting production: metrics to capture before/after removing one AZ target group, ALB thresholds, instance replacement time, RDS behavior, NAT paths, p95 latency, and error rates. Define pass/fail criteria using SLOs rather than merely "the app still loads."

## 15. Common Misconceptions

| Statement | Accurate Understanding |
| --- | --- |
| "A VPC with two AZs automatically makes an app HA." | You must deploy **workloads, network paths, and data tiers** properly in both AZs. |
| "Having two EC2 instances in two AZs is enough." | Single-AZ RDS, single-AZ NAT, background services, or insufficient capacity may still break it. |
| "Private subnets don't need Internet, so routes don't matter." | Apps may need outbound access to APIs/package repositories; choose NAT or endpoints as needed. |
| "One shared NAT does not affect availability." | A zonal NAT in a failed AZ breaks egress for subnets in other AZs pointing to it. |
| "RDS Multi-AZ has zero-second interruption." | Failover can drop active connections; clients must retry/reconnect and handle transactions safely. |
| "Read Replica equals standby failover." | Read replicas serve different goals and mechanics than RDS Multi-AZ DB instance deployments. |
| "ALB health checks passing means production is always healthy." | Remaining capacity may be too small, or downstream DB/queues may be failing. |
| "Adding AZs always reduces costs." | Extra replicas, NAT paths, endpoints, cross-AZ traffic, and monitoring all carry costs. |
| "Survives Regional outage because it is Multi-AZ." | Surviving a Region outage requires multi-Region DR design and separate testing. |

## 16. Pre-Production Checklist

- [ ] Region selected for latency, data residency, service support, quotas, and cost.
- [ ] VPC CIDR does not overlap connected networks; public/app/db subnets span at least two appropriate AZs.
- [ ] ALB uses subnets across multiple AZs, with HTTPS/certificates/health checks and target groups configured properly.
- [ ] App runs instances/tasks across multiple AZs with **sufficient surviving capacity for single-AZ loss** at peak load.
- [ ] Route tables are explicit; per-AZ egress or NAT/endpoint architecture matches accepted failure domains.
- [ ] RDS/data tiers have Multi-AZ, backups, recovery, and proper retry/idempotency handling.
- [ ] SGs/NACLs allow only genuinely required flows; app and DB are not exposed publicly without reason.
- [ ] IAM roles, secrets, encryption, patching, WAF, and auditing have been reviewed.
- [ ] Logs, metrics, traces, alerts, and cost budgets have designated owners and response runbooks.
- [ ] IaC, change review, rollback, AZ-loss tests, and DR plans aligned with RTO/RPO are in place.

**Remember:** successful multi-AZ design means designing **survivable paths when one AZ stops serving**: inbound via ALB, application compute capacity, outbound via NAT/endpoints, and data tier state must all be verified together. Each component has its own fault domain; only when critical dependencies avoid piling onto a single AZ does an availability target stand on solid ground.

### Official AWS Documentation for Further Reading

- [VPCs and subnets](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html) — VPCs, subnets, AZs, and address ranges.
- [Subnet route tables](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html) — routing and subnet associations.
- [Connect your VPC to the Internet](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html) — Internet Gateways and public networking.
- [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html) — NAT egress, operational scope, and costs.
- [Gateway VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html) and [Interface VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/interface-endpoints.html) — private connectivity to AWS services.
- [Availability Zones for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html) — ALBs and multi-AZ subnets.
- [Amazon EC2 Auto Scaling availability](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-add-availability-zone.html) — distributing and replacing capacity across AZs.
- [Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) — RDS synchronous standby and failover.
- [Security groups for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) and [Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — two-layer network access control.
- [AWS Well-Architected: Planning for disaster recovery](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html) — RTO, RPO, and DR strategies.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) and [Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html) — observing and verifying network paths.
