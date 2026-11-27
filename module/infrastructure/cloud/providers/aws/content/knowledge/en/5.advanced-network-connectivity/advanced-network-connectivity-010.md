# Reachability Analyzer and Routing Troubleshooting in AWS

## Learning Objectives

After this lesson, learners will be able to:

- Explain how **Amazon VPC Reachability Analyzer** evaluates network connectivity based on configuration and the limits of that analysis.
- Read a **network insights path**, **network insights analysis**, `NetworkPathFound` verdict, path components, and failure explanations.
- Pinpoint the right route table, security group, network ACL, gateway, or endpoint when an application fails to communicate across subnets, VPCs, or corporate networks.
- Distinguish **routing and packet filtering** issues from DNS, TLS, IAM, stopped applications, or unresponsive databases.
- Execute an investigation workflow using AWS Console, AWS CLI, VPC Flow Logs, and live workload testing, while applying fixes under the principle of minimal change.
- Propose monitoring, resilience verification, and cost management practices for multi-Availability Zone (AZ), multi-account, or hybrid AWS networks.

**Context:** This lesson belongs to the **Advanced Network Connectivity** chapter of the **CLOUD_PROVIDERS_AWS** module. AWS provides multiple network infrastructure layers: Regions/AZs, VPCs/subnets, route tables, Internet/NAT gateways, VPC peering, Transit Gateways, endpoints, and on-premises connections. When applications running on EC2, ECS, EKS, or Lambda need to access RDS, S3, DynamoDB, or integration services, a single misconfigured route or security group can disrupt the system. Reachability Analyzer helps isolate issues based on **AWS network configuration** before needing to probe and measure live traffic.

## 1. Distinguishing Three Questions When Investigating Lost Connectivity

A `connection timed out` message can stem from many causes. Separate it into three questions:

1. **Does the domain name resolve to a valid destination?** Which IP did the DNS client obtain, is it private/public, IPv4/IPv6, and does it match the current endpoint?
2. **Does the network configuration allow packets from source to destination?** Do route tables point properly, are gateways attached, and do security groups and NACLs permit the traffic? This is what **Reachability Analyzer** helps analyze.
3. **Is the destination actually serving requests?** Is the TCP listener open, is an OS firewall blocking it, are TLS/HTTP correct, and do IAM/application authentication permit access?

~~~mermaid
flowchart TD
    A[Application reports connection failure] --> B{Does DNS name resolve?}
    B -->|No| C[Check DNS / Resolver / private hosted zone]
    B -->|Yes| D{Does AWS network allow the path?}
    D -->|No| E[Route table / gateway / SG / NACL / endpoint]
    D -->|Yes per config| F[Live testing: TCP / TLS / application]
    F --> G[Listener / OS firewall / IAM / DB / app / timeout]
~~~

Example of an EC2 instance in a private subnet accessing RDS by hostname:

- If DNS returns the wrong address: troubleshoot name resolution or the endpoint.
- If a route is missing along the path or a security group blocks TCP 5432: troubleshoot networking.
- If the network path is allowed yet PostgreSQL rejects login: inspect database authentication and users; adding routes or opening ports will not fix this error.

**Principle:** "DNS responds", "Reachability Analyzer finds a path", and "the application request succeeds" are **three distinct conclusions**.

## 2. What Is Reachability Analyzer?

**Amazon VPC Reachability Analyzer** is an AWS connectivity configuration analysis capability. You specify a **source**, **destination**, and traffic attributes like protocol/port; the service analyzes supported network components to determine whether a valid path exists under the configuration. Results help identify which layer is blocking traffic.

Reachability Analyzer **does not send probe packets from the application to the destination**. It is a **static configuration-based analysis**, making it useful even when an endpoint is not yet running an application or carrying live traffic, provided the resources and configurations are supported for analysis.

### Key Terms to Know

| Concept | Meaning | What to remember |
| --- | --- | --- |
| **Network insights path** | Declaration of hypothetical source → destination, protocol, port, and path parameters | Can be saved and re-analyzed repeatedly |
| **Network insights analysis** | A single Reachability Analyzer run against a created path | Reflects configuration at the time of analysis |
| **Source / Destination** | Resources or endpoints supported by the tool, e.g., EC2 instances/network interfaces | Supported resource types and IP/port options vary by context |
| **`NetworkPathFound`** | Verdict on whether a valid path exists under the modeled configuration | Does not prove the application works |
| **Forward path components** | Resources/hops analyzed along the path from source to destination | Useful for understanding routes and intermediate components |
| **Return path components** | Return-path components if the analysis type supports and returns them | Not guaranteed to appear in every analysis |
| **Explanations** | Reasons why the requested path cannot be traversed, or related details | Inspect resource IDs and details to fix the exact spot |
| **Reachability** | Ability to reach the destination under modeled network rules | Does not confirm DNS, TLS, IAM, or listening processes |

### What the Tool Can and Cannot Do

| Reachability Analyzer is useful for | Do not treat it as proof that |
| --- | --- |
| Checking path configuration from a supported source to destination | Packets have actually traversed the live network |
| Detecting route tables or network filters blocking a path | The server is listening on the port and responding healthily |
| Inspecting modeled intermediate network components | DNS always points to the destination the application actually uses |
| Comparing results before/after a network change | TLS handshakes, IAM, DB permissions, or app logic are right |
| Checking certain paths across VPC peering, Transit Gateway, gateways, and endpoints within supported scope | Every external non-AWS appliance or tunnel is fully modeled |

Support for individual resource types, protocols, and multi-account architectures can evolve. Before relying on results for specialized designs like GWLB, firewall appliances, Direct Connect, or Internet paths, consult **supported resources / limitations** in current AWS documentation. If a segment is not modeled by the tool, supplement with live tests and logs from the relevant appliances.

### Why Specify the Exact Port and Direction?

A path from **EC2-A → EC2-B TCP/443** may be valid, whereas **EC2-A → EC2-B TCP/5432** may fail due to security groups. Directions **A → B** and **B → A** are also two different checks when evaluating connection initiation. Therefore:

- Select the **exact source** (instance/ENI/supported object), **exact destination**, protocol, and **destination port**.
- When destination IPs change after failover, verify the active entity/IP at the time of investigation.
- Run separate analyses for critical application flows; never infer all ports are open just because one path returned `NetworkPathFound=true`.

## 3. AWS Routing Model to Master Before Reading Results

A packet from EC2-A to EC2-B may traverse the following components:

~~~mermaid
flowchart LR
    A[EC2-A / ENI] --> SG1[Source security group]
    SG1 --> NA[Subnet A Network ACL]
    NA --> RT[Subnet A Route table]
    RT --> GW{Destination / next hop}
    GW --> NB[Subnet B Network ACL]
    NB --> SG2[Destination security group]
    SG2 --> B[EC2-B / ENI]
~~~

This diagram is a **logical investigation model**, not the exact packet-processing order of every AWS component. Within the same VPC, routes may use `local`; across peering, Transit Gateway, Internet Gateway, NAT Gateway, or endpoints, the component chain differs.

### 3.1. CIDRs, Subnets, and Route Tables

A **CIDR** defines an address range, e.g., VPC `10.20.0.0/16`, subnet `10.20.1.0/24`. Each subnet uses **an explicitly associated route table**, or falls back to the VPC's **main route table** if no explicit association exists.

A route table consists of **destinations** and **targets** (next hops). Example:

| Destination | Target | Interpretation |
| --- | --- | --- |
| `10.20.0.0/16` | `local` | Packets to addresses within the VPC via default internal routing |
| `0.0.0.0/0` | `igw-...` | Default IPv4 route to Internet Gateway when properly designed |
| `0.0.0.0/0` | `nat-...` | Default IPv4 route out to NAT Gateway, typically for private subnets |
| `10.30.0.0/16` | `pcx-...` | Route to another VPC via VPC peering |
| `10.40.0.0/16` | `tgw-...` | Route to networks attached to Transit Gateway |
| `pl-...` | `vpce-...` | Prefix-list route to the matching gateway endpoint for supported services |

For IPv6, routes and destinations use `::/0` and IPv6 CIDRs; select an appropriate IPv6-capable target such as an Internet Gateway or egress-only Internet Gateway as required. You cannot infer IPv6 works from the `0.0.0.0/0` route alone.

**Longest-prefix match:** Generally, the route matching the **most specific** prefix for the destination IP takes precedence. However, when static routes, propagated routes, or overlapping prefix lists coexist, AWS applies specific precedence rules; inspect actual route tables and documentation for those cases.

### 3.2. Security Groups and Network ACLs

| Attribute | Security group (SG) | Network ACL (NACL) |
| --- | --- | --- |
| Where attached | Elastic network interface / resource with corresponding ENI | Subnet |
| Statefulness | **Stateful** | **Stateless** |
| Rules | Allow-based inbound/outbound; no standard Deny rules | Allow/Deny evaluated by rule number |
| Return traffic | Response traffic for an allowed connection is normally permitted automatically | Requires rules for **both forward and return directions** |
| Matching criteria | Protocol, port, CIDR, or eligible SG reference | Protocol, port, CIDR, rule number order |
| Easy pitfalls | Source SG is not a literal IP, and SG references have support conditions | Forgetting ephemeral ports for return traffic |

Example: EC2-A in subnet `10.20.1.0/24` calls EC2-B in `10.20.2.0/24` over TCP/443.

- A's SG needs **egress** allowing the connection to B per configuration.
- B's SG needs **ingress TCP/443** from A or its source SG when SG referencing is supported.
- Subnet A and B NACLs must permit both outbound and return traffic; because NACLs are stateless, the client's **ephemeral ports** must be accounted for based on OS/flow.
- Both subnets' routes must reach each other; same-VPC subnets normally use the `local` route, though custom routes through an appliance may exist in specialized architectures.

Never add `0.0.0.0/0` across all SGs as a "quick fix". An AccessDenied/blocking verdict should lead to **the minimal rule matching the real flow**, while IAM/API limits and OS firewalls must still be reviewed independently.

## 4. Common Routing Errors by Connectivity Type

### 4.1. Same VPC, Different Subnets or Different AZs

In a standard VPC, the `local` route enables subnets to reach each other across the VPC CIDR. However, communication is still constrained by SGs/NACLs, instance firewalls, and listeners.

Common causes:

- Destination SG lacks the required TCP port or source SG egress is too restrictive.
- NACL denies either the outbound or return traffic.
- Destination is not on the expected IP/ENI, or the app is not bound to the required address.
- The `local` route was overridden in a middlebox/inspection architecture and the appliance fails to forward properly.
- IP addresses changed due to ENI replacement, autoscaling, or failover.

### 4.2. Public Subnets and Internet Gateway

An EC2 instance said to "have a public IPv4" can still fail to accept connections from the Internet if:

- The subnet lacks an appropriate route to the **Internet Gateway (IGW)**;
- Its SG does not allow ingress on the target port;
- A NACL or OS firewall blocks it;
- The instance lacked a valid public IP/Elastic IP at the time of access;
- The application is not listening or DNS points to a stale IP.

The `0.0.0.0/0 → igw-...` route is just one network condition. A route alone does not turn a private IP into an Internet-reachable IP.

### 4.3. Private Subnets and NAT Gateway

A private instance needing to **initiate IPv4 connections to the Internet** typically has:

- A `0.0.0.0/0 → NAT Gateway` route in the private subnet's route table;
- A public NAT Gateway in a valid public subnet with an Elastic IP and route to IGW;
- Valid SGs/NACLs and return paths.

**A NAT Gateway is not an ingress port for the Internet to initiate connections to private instances.** For AWS services, consider **VPC endpoints** instead of Internet egress where supported by the service and use case; for example, gateway endpoints for S3/DynamoDB or interface endpoints for many AWS services.

### 4.4. VPC Peering

Peering connects **two VPCs** via supported mechanisms, but does not automatically populate complete routes. You need:

1. The peering connection in the `active` state.
2. A route **from the source subnet** to the destination CIDR via peering.
3. A **return route** from the destination subnet back to the source CIDR.
4. SGs/NACLs in both VPCs permitting the flow.
5. Non-overlapping CIDRs as required by VPC peering.

**Peering does not support transitive routing:** VPC A peering with B and B peering with C does not let A automatically reach C through B. Use an appropriate connectivity model if you need a multi-network hub.

### 4.5. Transit Gateway (TGW)

TGW acts as a hub connecting multiple VPCs and supported networks. Failures can arise at **two route layers**:

- The **VPC subnet route table** pointing to TGW for the destination CIDR.
- The **TGW route table** having the right association/propagation or static route to the target attachment.
- The remote VPC also having return routes from its subnets back to TGW when needed.

An attachment showing `available` does not prove the TGW route table selects that attachment. With multiple TGW route tables, verify **which attachment is associated with which table** and which routes are propagated. Blackhole routes, overlapping CIDRs, or missing return paths can all break flows.

### 4.6. Hybrid Connectivity: VPN/Direct Connect

VPC-to-on-premises connectivity additionally requires:

- VPC/TGW routes to internal corporate networks;
- Proper gateway/attachment/VPN or Direct Connect configuration;
- On-premises routes/BGP and firewall policies in **both directions**;
- Hybrid DNS if connecting by hostname;
- Checking MTU/MSS and external network appliances when symptoms show small packets passing while large packets fail.

Reachability Analyzer can evaluate **supported AWS segments**, but **does not fully inspect routers/firewalls inside your data center**. Once AWS segments are verified, test live traffic and inspect external network appliance logs.

## 5. Using Reachability Analyzer in the AWS Console

> **Preparation:** Have an authorized account and Region; know the exact VPC, source, destination, protocol, and service port. Labs should use lab EC2/ENIs; Reachability Analyzer may incur per-analysis charges. Never modify production infrastructure just to test without impact assessment.

### Step 1 — Choose the Flow to Inspect

Example:

- **Source:** EC2 `app-a`, private IP `10.20.1.10`, in AZ A.
- **Destination:** EC2 `api-b`, private IP `10.20.2.20`, in AZ B.
- **Flow:** TCP port **8080**.
- **Expectation:** A can call the API on B, while B does not necessarily initiate new connections to A.

Define the flow clearly before opening the Console. If the application uses DNS, verify which resource DNS resolved to at the time of failure; avoid analyzing one instance while the application actually calls a different load balancer.

### Step 2 — Create a Network Insights Path

In **VPC Console → Reachability Analyzer → Create and analyze path** (screen labels may vary slightly across UI updates):

1. Choose **source** from supported resource types, such as an EC2 instance or its ENI.
2. Choose **destination**, such as the API's EC2 instance or ENI.
3. Choose **protocol TCP** and **destination port 8080**.
4. If supported by the UI, configure source/destination IPs or other parameters to match the exact requirement.
5. Add a searchable name/tag like `lab-app-to-api-8080`, then create the path and run the analysis.

### Step 3 — Read the Results

Once the analysis completes, read **both the verdict and the explanations**:

| Result | Interpretation | Next action |
| --- | --- | --- |
| `NetworkPathFound = true` | A valid network path exists under the modeled config | If the app still fails, test from OS/runtime and check DNS, listener, OS firewall, TLS, IAM |
| `NetworkPathFound = false` | No path found under the specified conditions | Open Explanations and inspect the blocking component |
| `Status = failed` or analysis error | The analysis itself failed or is unsupported in that context | Check status message, IAM permissions, source/destination, quotas, and supported resources |
| Analysis running | No verdict yet | Wait for completion in Console; do not read a transient state as final proof |

Hypothetical example when no path is found: the tool flags a missing **inbound security group rule** for TCP/8080 on the destination ENI. The right fix is verifying and adding a **TCP/8080 rule from the exact source SG** (when SG referencing is supported) or minimal source CIDR, then re-analyzing.

### Step 4 — Live Testing and Recording Evidence

A re-analysis returning `NetworkPathFound=true` is a good sign, yet live testing is still required:

- From EC2-A: `curl -v --connect-timeout 5 http://10.20.2.20:8080/health` (if the application actually supports HTTP).
- On EC2-B: inspect listening processes/ports with OS tools like `ss -lnt`, then check service logs.
- Correlate timestamps, VPC Flow Logs, CloudWatch metrics, and recent deployments.
- Briefly record **before/after**, resource IDs, modified rules, live test results, and the owner.

## 6. Hands-On with AWS CLI

AWS CLI lets you save path definitions, re-run controlled checks, and embed outputs in runbooks. IDs below are **examples only**; do not run them verbatim in production.

### 6.1. Verify Identity and Region

~~~bash
aws sts get-caller-identity --profile lab
aws configure get region --profile lab
~~~

The account/role needs minimal IAM permissions for Reachability Analyzer APIs and read access to related resource metadata; modifying routes or SGs is a separate permission granted only when needed.

### 6.2. Create a Network Insights Path Between Two ENIs

~~~bash
aws ec2 create-network-insights-path \
  --source eni-0123456789abcdef0 \
  --destination eni-0fedcba9876543210 \
  --protocol tcp \
  --destination-port 8080 \
  --region ap-southeast-1 \
  --profile lab
~~~

Use actual **ENIs supported by Reachability Analyzer** as source and destination; investigations can also use EC2 instance IDs or other resource types where supported by the API. Creation output includes `NetworkInsightsPathId` formatted as `nip-...`.

### 6.3. Start the Analysis

~~~bash
aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

This returns an analysis ID formatted as `nia-...`. Only after the analysis completes should you read `NetworkPathFound`, `Explanations`, and path components.

### 6.4. Read the Results

~~~bash
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

To view a summary only:

~~~bash
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-0123456789abcdef0 \
  --query 'NetworkInsightsAnalyses[0].{Status:Status,PathFound:NetworkPathFound,Explanations:Explanations}' \
  --region ap-southeast-1 \
  --profile lab
~~~

**How to read it:** `Status` reflects analysis progress; `NetworkPathFound` indicates whether a path exists per configuration. If no path exists, expand `Explanations` and match the resource ID against the actual VPC, subnet, route table, SG, NACL, gateway, or attachment.

### 6.5. Inspect Route Tables and Security Groups to Confirm

~~~bash
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

**Pitfall:** If filtering route tables by `association.subnet-id` returns empty, the subnet may be **inheriting the VPC's main route table**; never conclude the subnet has no routes. Inspect subnet associations and the VPC's main route table. For NACLs, inspect the NACL associated with the **subnet**, not just an arbitrary NACL in the VPC.

### 6.6. Clean Up Test Resources

If lab policy permits, finish by deleting **test analyses/paths** once no longer needed for reporting. Save minimal evidence before cleanup. Avoid deleting paths/analyses belonging to other teams' operational workflows. Analysis fees and logs may already have been incurred even if the path resource is later deleted.

## 7. Diagnostic Table by Network Component

| Component | Common mistakes | Priority checks |
| --- | --- | --- |
| **Subnet route table** | Wrong table association, missing route, wrong target, `blackhole` route | Destination CIDR, longest-prefix, route state, next hop |
| **Security group** | Missing destination ingress port, overly strict source egress, mismatched CIDR/SG reference | Which ENI holds which SG, TCP/UDP, port, source/dest |
| **Network ACL** | Higher-priority Deny rule, missing return ephemeral ports | Rule numbers, inbound/outbound, CIDR, ephemeral range |
| **Internet Gateway** | Not attached or subnet lacks route; instance lacks public IP | IGW attachment, `0.0.0.0/0` route, public IP, and SG |
| **NAT Gateway** | Wrong route, NAT not available, public NAT in subnet lacking IGW | Private route, NAT subnet, and return path; NAT only allows outbound-initiated flows |
| **VPC peering** | Peering not active, route missing on one side, overlapping CIDRs | Peering state, route tables in both VPCs |
| **Transit Gateway** | Missing/wrong attachment association, missing propagation, static/blackhole route | TGW route table, attachment state, bidirectional VPC routes |
| **VPC endpoint** | Wrong endpoint type, route/prefix list, endpoint SG, or private DNS | Gateway endpoint vs. interface endpoint; matching DNS and SGs/routes |
| **VPN/Direct Connect** | Missing routes/BGP, external firewall, dropped tunnel | TGW/VGW + tunnel/link state + on-premises devices |
| **Load Balancer** | Wrong SG/listener/target group/health check | Check client→LB and LB→targets flows separately |
| **DNS** | Wrong IP/zone, private zone not associated, stale cache | `dig`/`nslookup`, Route 53 Resolver and endpoints |
| **OS / application** | Port not listening, host firewall, wrong TLS or auth | `ss`, `curl`, logs, metrics, DB/auth |

**Note:** Not every item in this table is fully inspected by Reachability Analyzer. This table represents the **end-to-end investigation scope**, within which Reachability Analyzer is a key tool for the AWS network portion.

## 8. Example A: Two EC2 Instances in the Same VPC Cannot Call an API

### Topology

- VPC `10.20.0.0/16` in one Region.
- EC2-A in subnet `10.20.1.0/24`, SG `sg-client`.
- EC2-B in subnet `10.20.2.0/24`, SG `sg-api`.
- App A calls `http://10.20.2.20:8080/health`.

~~~mermaid
flowchart LR
    subgraph VPC["VPC 10.20.0.0/16"]
      subgraph AZA["AZ A"]
        A[EC2-A / 10.20.1.10 / SG client]
      end
      subgraph AZB["AZ B"]
        B[EC2-B / 10.20.2.20 / SG API]
      end
      A -->|TCP 8080| B
    end
~~~

**Symptom:** `curl` from A times out. In Reachability Analyzer, the path from ENI-A to ENI-B for TCP/8080 returns **no path found**, with explanations pointing to the destination SG.

**Diagnosis:**

1. Confirm subnets use route tables with `10.20.0.0/16 → local`.
2. Confirm SG A permits appropriate egress.
3. Inspect SG B: if only TCP/443 is open, TCP/8080 is blocked.
4. Add inbound TCP/8080 restricted to SG A (if referencing is supported) or the appropriate source IP range.
5. Re-analyze; once the path is found, run a live `curl` test.
6. If `curl` still times out, check whether the app on EC2-B is listening on TCP/8080, check local firewalls, IP binding, and logs.

**Lesson:** An SG is a filter, not a route table. An existing `local` route does not prove application ports are open.

## 9. Example B: VPC Peering Is Active, Yet Communication Fails

### Topology

- **VPC A**: CIDR `10.10.0.0/16`, source EC2 `10.10.1.10`.
- **VPC B**: CIDR `10.30.0.0/16`, destination EC2 `10.30.2.20`.
- Peering `pcx-demo` is `active`.
- Goal: A calls B on TCP/443.

~~~mermaid
flowchart LR
    A[EC2-A / 10.10.1.10] --> RA[Subnet A route table]
    RA --> PCX[VPC peering]
    PCX --> RB[Subnet B route table]
    RB --> B[EC2-B / 10.30.2.20]
~~~

**Example state:** A's route table has `10.30.0.0/16 → pcx-demo`, but B lacks `10.10.0.0/16 → pcx-demo`. An exchange cannot complete due to the missing return path; inspect both directions using RA findings and route configs.

**Remediation:**

1. Verify VPC A/B CIDRs are compatible, peering is active, and which route tables each subnet uses.
2. Check **routes in both VPCs** to the partner's CIDR.
3. Verify SG B allows TCP/443 from the source, and SG A allows matching egress.
4. Check NACLs on both sides and return paths.
5. Evaluate with Reachability Analyzer within peering's supported scope, then run live connectivity tests and record results.

**Lesson:** Active peering is only a connectivity relationship between VPCs; **bidirectional routes and network filters** determine whether application traffic completes. With stateful SGs, return traffic does not need an extra inbound rule on the initiator's SG, but stateless NACLs must still account for the return direction.

## 10. Example C: Private Instance Accessing AWS Services or the Internet

### Scenario

An API in a private subnet needs to fetch data from an AWS service over HTTPS; operations sees connection failures or timeouts.

**Do not immediately spin up a NAT Gateway:** first identify **the target service and access method**.

- If accessing **S3/DynamoDB** via a supported endpoint: consider a **gateway VPC endpoint** with matching route tables.
- If calling an AWS service API with an **interface VPC endpoint**: consider endpoint ENIs, security groups, and proper private DNS.
- If general IPv4 Internet access is needed: evaluate a **public NAT Gateway** for private subnets and IGW egress.
- If IPv6: evaluate IPv6 routes and an egress-only IGW/appropriate egress path—do not extrapolate from IPv4.

### Workflow

1. Confirm whether DNS resolves the service name to a private endpoint or a public IP.
2. Check the source subnet's actual route table: gateway endpoint route/prefix list vs. default route via NAT.
3. Verify private DNS on the **interface endpoint** and the endpoint ENI's SG if used.
4. Use Reachability Analyzer if the endpoint pair and architecture are supported; do not force the tool onto unsupported resource types.
5. Test live HTTPS and actual IAM permissions; AWS APIs can still return **`AccessDenied`** even when networking is completely healthy.

**Lesson:** Network errors reaching an endpoint and IAM permission errors are two independent layers. Changing routes will never fix `AccessDenied` from S3/KMS once requests already reach the service.

## 11. Complementary Tools: Picking the Right Kind of Evidence

Reachability Analyzer should sit inside a broader diagnostic toolkit, not stand alone.

| Tool | Primary evidence | Limitations to remember |
| --- | --- | --- |
| **Reachability Analyzer** | Path existence/absence per supported AWS network config and explanations | Not a packet probe; does not verify listeners/TLS/IAM |
| **VPC Flow Logs** | Traffic metadata at ENI, subnet, or VPC level; ACCEPT/REJECT per log config | Has delivery delay, no payload, not exhaustive; ACCEPT does not mean app success |
| **CloudWatch Logs/Metrics** | Application logs, traffic metrics, error rates, latency, timeouts | Requires log collection/retention setup and timestamp alignment |
| **Route 53 Resolver query logging** | DNS queries handled/logged by the Resolver | Caching and logging scope affect recorded entries |
| **VPC Traffic Mirroring** | Packet copies in supported cases for deep inspection | Resource-intensive; requires setup, storage, and data protection |
| **AWS Network Manager / Route Analyzer** | Analyzes certain hub/routing paths within supported service scope | Distinct from Reachability Analyzer; select based on actual TGW/Cloud WAN tech |
| **VPC Network Access Analyzer** | Checks network access paths against user-defined control scopes/rules | Intended for access-boundary compliance auditing, not live app probes |
| **`curl`, `nc`, `dig`, `traceroute`, `ss`** | Verifies DNS, TCP/TLS, listeners, or path behavior from the OS | Output depends on ICMP/UDP/TCP, firewalls, endpoints, and OS permissions |
| **AWS CloudTrail** | Who modified routes, SGs, NACLs, endpoints; control-plane APIs | Not packet payload logging; requires proper event lookup setup |

### VPC Flow Logs: What Do `ACCEPT` and `REJECT` Mean?

Suppose Flow Logs for the source ENI record TCP/8080 with action `REJECT`: this signals checking SGs/NACLs. If `ACCEPT`, packets likely passed the logged control layer, yet **it does not prove the TCP handshake completed**, that the service received the request, or that it returned HTTP 200.

An important step is filtering logs accurately:

- **ENI/subnet/VPC**, source, destination, port, protocol;
- failure time window and timezone;
- network interfaces of **actual underlying resources**, especially behind load balancers, NATs, or endpoints;
- Flow Logs configuration, record format, and `log-status` field if present.

When NAT or load balancers are involved, observed IPs/ports at different hop points change due to address translation or proxying. Do not expect every log to appear on one source ENI with the same original 5-tuple.

### Distinguishing Network Paths from Endpoint Health

Suppose Reachability Analyzer reports client → ALB is reachable. This **does not prove** the ALB has a valid listener or that its target group has healthy targets. Separately inspect:

1. Client → ALB on the actual port;
2. ALB → target on the configured port;
3. health checks, target status, and response codes;
4. TLS certificates/listener rules and application logs.

You can run a separate network analysis for the LB → target leg when resources and path types are supported by Reachability Analyzer.

## 12. Ordered Diagnostic Workflow: Avoid Guessing

### Step 1 — Define the Requirement and Connection Direction

Write down a one-line summary:

~~~text
Source:      EC2 app-a / eni-A / 10.20.1.10 / VPC-A / subnet-A
Destination: EC2 api-b / eni-B / 10.20.2.20 / VPC-A / subnet-B
Flow:        TCP 8080, app-a initiates connection
Error:       Connection timed out after 5 seconds
Timestamp:   Actual observed date/time and Region
~~~

If load balancers, NATs, or dynamic DNS are involved, record the **hostname**, the resolved IP at failure time, and intermediate resources.

### Step 2 — Inspect Source/Destination Configuration

- Which VPC/subnet/SG do the EC2 instances/ENIs belong to?
- Which CIDR/IPv4/IPv6 does the destination IP belong to?
- Is the source subnet's route table an explicit table or the main route table?
- Do SG ingress/egress and NACLs have matching rules?
- What states are the gateways/attachments/endpoints in?

### Step 3 — Use Reachability Analyzer to Isolate the Bottleneck

Create a path with the exact protocol/port and run an analysis. If no path is found, read **Explanations + resource IDs**, and verify against route tables/SGs/NACLs/attachments. Never blindly add `0.0.0.0/0` or `::/0` just to make a route look valid.

### Step 4 — Apply the Minimal Change

Examples:

- Missing return route from VPC B: add only the source CIDR via existing peering/TGW after approval.
- Destination SG missing TCP/443 from app SG: add that exact rule instead of opening to the whole Internet.
- NACL missing ephemeral return ports: adjust rules to match OS/client and exact CIDR limits.
- TGW missing association/propagation: adjust the **exact** TGW route table/attachment per diagram.
- Route to NAT in `blackhole`: restore the target/egress path and inspect NAT health before altering routes.

Changing network controls in production must account for side effects on other flows, especially route tables/SGs shared across multiple workloads.

### Step 5 — Verify After the Change

1. Re-run **Reachability Analyzer** with the same source/destination/protocol/port.
2. Run **live TCP/HTTP tests** from the workload.
3. Confirm **application behavior** and latency/error metrics recover.
4. Verify unauthorized flows remain blocked; do not accidentally widen access.
5. Record evidence, change ID, timestamp, root cause, and rollback plan.

### Step 6 — If Analysis Reports Reachable Yet the App Still Fails

Check in order:

- DNS cache/returning a different IP than analyzed;
- process not listening, host firewall, or container networking;
- load balancer listeners/target groups/health checks;
- TLS SNI/certificates, proxies, HTTP host headers;
- database connection limits, authentication, or IAM;
- latency/throttling, DNS TTLs, packet size/MTU, resource saturation;
- intermittent time-based failures, since Reachability Analyzer only inspects **configuration at the moment of analysis**.

### Reference Decision Tree

~~~mermaid
flowchart TD
  A[Connection fails] --> B[Check DNS and destination IP]
  B --> C[Select source, destination, protocol, port]
  C --> D[Run Reachability Analyzer]
  D --> E{NetworkPathFound?}
  E -->|No| F[Explanations: route / SG / NACL / GW / endpoint]
  F --> G[Fix exact config + re-analyze]
  E -->|Yes| H[Test TCP / TLS / app from real source]
  G --> H
  H --> I{Does live request succeed?}
  I -->|No| J[Flow Logs / OS / LB / TLS / IAM / app]
  I -->|Yes| K[Record evidence and monitor]
~~~

## 13. Multi-AZ, Multi-Account, and Resilience Mindset

### Multiple Availability Zones

If an application runs services in AZ A and AZ B, verify critical flows from **both AZs**, such as:

- App task AZ A → RDS endpoint;
- App task AZ B → RDS endpoint;
- ALB subnets AZ A/B → targets AZ A/B;
- Workloads in each AZ → respective NAT gateway or VPC endpoint.

A single passing path does not guarantee **every AZ, ENI, and target** is configured properly. NACLs can differ per subnet; route tables can differ; services may only fail upon failing over to another AZ.

**Failover:** Reachability Analyzer validates paths against static configurations—it does not simulate real outages/failovers. To validate RTO/RPO and resilience, conduct controlled drills combining health checks, applications, DNS, database replication/backups, and standby services.

### Multi-Account, Multi-VPC

In AWS Organizations environments, a single flow may cross route tables and TGW/VPC attachments owned by multiple accounts. Visibility and multi-account analysis permissions/support depend on configurations and enabled features; organize network governance accounts, information sharing, and appropriate IAM roles.

Checklist:

- Maintain non-overlapping CIDR plans and VPC/account/Region mapping tables.
- Document **owners** for every route table, TGW table, SG, endpoint, and firewall.
- Explicitly trace **return paths**, not just the forward leg.
- Verify cross-account analysis support for actual resource types; where insufficient, rely on flow logs and testing from each side.

### Consistency and Infrastructure Changes

Many outages stem from configuration drift: one environment has the right rule while another lacks it. Manage routes, SGs, endpoints, TGW attachments, and VPCs using **Infrastructure as Code (CloudFormation, CDK, or equivalent tools)**, review changes, and integrate routing analysis into testing stages.

For high-impact network routes, explicitly document **assumptions, tests, metrics, and rollback** in pull/change requests. Reachability Analyzer provides valuable pre-flight evidence, though live rollout testing remains essential.

## 14. Security, Cost, and Observability

### Security

- **Least privilege:** investigators' IAM roles should have only necessary read/analysis permissions; permissions to edit SGs/routes should be scoped by role and change process.
- **Defense in depth:** valid routes do not replace SGs/NACLs; permissive SGs do not replace host firewalls/TLS; working DNS does not replace authentication/authorization.
- **Private networking:** prefer private endpoints/internal paths for sensitive workloads where feasible; avoid opening public ports just to run a test.
- **Secure logging:** VPC Flow Logs, CloudWatch, CloudTrail, and connectivity docs can contain IPs, hostnames, and infrastructure details; apply retention, encryption, and read access controls.
- **Minimize change risk:** modify only the exact rules, routes, CIDRs, and ports needed; verify **disallowed** paths remain blocked afterward.

### Cost

- Reachability Analyzer may incur **per-analysis** charges. Avoid running repeated analyses on identical paths without a new verification goal.
- VPC Flow Logs, CloudWatch Logs/S3, and data retention carry separate charges.
- NAT Gateways, Transit Gateways, endpoints, cross-AZ/cross-Region data transfer, and hybrid links can represent significant network spend.
- Use **AWS Pricing Calculator, AWS Cost Explorer, and AWS Budgets** to estimate under active Regions/configurations, and tag by application, environment, and owner.

A `0.0.0.0/0` route through a NAT Gateway can hairpin inter-service traffic and cost more than an appropriate private endpoint/path. Still, choose endpoints based on **service type, security requirements, and actual traffic**, not a single isolated fee.

### Post-Fix Monitoring

Useful indicators:

- connection success rate, TCP connect time, HTTP 5xx, and application errors;
- ALB/NLB target health, and states of gateways/attachments/tunnels;
- VPC Flow Logs `ACCEPT`/`REJECT` traffic and shifting error patterns;
- DNS/endpoint latency and connection timeouts across AZs;
- route/SG change timestamps via CloudTrail and change logs;
- NAT/TGW/endpoint/logging costs by application or environment.

## 15. Common Misconceptions

| Incorrect statement | Accurate understanding |
| --- | --- |
| "Reachability Analyzer pings machines from AWS." | It is static configuration analysis and sends no live probe packets. |
| "Path found means HTTPS will return 200." | You must still check listeners, TLS, DNS, IAM, and the application. |
| "Active peering means two VPCs automatically talk to each other." | Bidirectional routes, SGs/NACLs, return paths, and non-overlapping CIDRs are still required. |
| "A VPC route table having `0.0.0.0/0` means Internet works." | Valid targets, public IPs/network paths, SGs/NACLs, and running services are also needed. |
| "A private subnet calling AWS APIs always needs NAT." | Gateway/interface VPC endpoints can be used where appropriate. |
| "Security groups are stateless so inbound ephemeral ports must be opened for responses." | SGs are stateful; stateless **NACLs** are what require return port rules. |
| "VPC Flow Logs ACCEPT proves the application succeeded." | It is only a signal at the logged network layer, proving neither TLS/HTTP nor app logic. |
| "If one AZ has a working path, Multi-AZ definitely works." | Verify every subnet/ENI/route and rehearse failovers. |
| "Just open `0.0.0.0/0` everywhere to find the bug." | That creates security exposure and obscures root causes; analyze flow by flow instead. |
| "All on-premises devices are modeled inside Reachability Analyzer." | Verify support boundaries and supplement with tests/logs from non-AWS networks. |

## 16. Checklist Before Declaring an Incident Resolved

- [ ] Identified exact source, destination, protocol, destination port, and failure timestamp.
- [ ] Confirmed which IP DNS resolved to at failure time; avoided analyzing the wrong endpoint.
- [ ] Inspected the right route table for every subnet, including the **main table** when no explicit association exists.
- [ ] Verified SG inbound/egress per ENI and bidirectional NACLs.
- [ ] For peering/TGW/hybrid: verified routes and states on **both sides**; avoided CIDR collisions and blackholes.
- [ ] For Internet/NAT/VPC endpoints: verified targets, public/private addressing, endpoint types, and DNS.
- [ ] Ran Reachability Analyzer with valid parameters and understood `NetworkPathFound` and `Explanations`.
- [ ] Matched blocked components against real configs without overly broadening network permissions.
- [ ] Tested live TCP/TLS/application connectivity from the actual fault origin, not just static analysis.
- [ ] Confirmed via logs/metrics that errors dropped and unauthorized paths remain blocked.
- [ ] Verified multi-AZ operation and post-failover behavior if the system requires HA.
- [ ] Documented changes, resource IDs, root cause, tests, rollback plan, and cost impact.

## 17. Exercises and Self-Check Questions

### Exercise 1: Diagnosing a Missing SG Rule

**Prompt:** EC2 instances in two subnets of the same VPC cannot communicate over TCP/8443. The `local` route exists, source SG allows egress, and destination SG allows only TCP/443. Do the following:

1. Create a path from the source ENI to the destination ENI with TCP/8443.
2. Explain why the analyzer may return `NetworkPathFound=false`.
3. Propose the minimal ingress rule for the destination SG; predict what changes if you switch the path port to 443.
4. After updating, re-run the analysis and test live TCP/8443; list reasons the connection could still fail even once a path is found.

**Expectation:** Distinguish SG rules from routes, use exact destination ports, and understand static analysis limits.

### Exercise 2: VPC Peering Has a Forward Path but Lacks a Return Path

**Prompt:** VPC A has CIDR `10.1.0.0/16` and VPC B has `10.2.0.0/16`; peering is active. Route A → B exists, while B → A does not. Draw the forward/return paths, list the route tables to fix, and note remaining SG/NACL checks. Compare an A→B path check against an actual end-to-end application connection.

**Expectation:** Recognize routes must align on both sides alongside filters and application settings.

### Exercise 3: Multi-VPC Enterprise Architecture

**Prompt:** Application VPCs across multiple accounts connect to a single TGW, with an on-premises network connected over VPN. A service in VPC A must call a service in VPC C on TCP/443. Design a runbook covering:

- table of VPC CIDRs, subnet route tables, and attachments;
- TGW route table associations/propagations;
- principles for checking return paths and firewalls;
- where Reachability Analyzer helps locate blocks;
- complementary tools where on-premises segments lie outside analyzer scope;
- post-completion metrics/logs and alerts.

### Self-Check Questions

**1. Reachability Analyzer reports reachable, yet the TCP handshake times out. What is the next step?**  
Test live connectivity from the exact ENI/host, verify DNS IP, listener, host firewall, load balancer, runtime state, return path, and Flow Logs; never infer the application works from static analysis alone.

**2. SG permits inbound 5432, yet a NACL blocks return ephemeral ports. Will a TCP connection complete?**  
Likely not. Stateful SGs and stateless NACLs behave differently; both return paths and response ports must be accounted for.

**3. Why can't a private subnet be reached directly from the Internet merely because a NAT Gateway exists?**  
Standard NAT Gateways allow outbound flows initiated from the private side, not new inbound connections initiated from the Internet to private instances.

**4. With TGW, is checking only the VPC route table enough?**  
No. You must also inspect TGW route tables, associations, propagations/static routes, attachment states, and return paths.

**5. A route change yesterday broke all of AZ B while AZ A stayed healthy. What should be checked first?**  
Compare route table associations, SGs/NACLs/endpoints, and resources across AZs; run matching network insights paths from both AZs, then perform live tests.

## 18. Conclusion

Reachability Analyzer answers a critical question: **"Given the current AWS network configuration and specified flow, does a valid path exist from source to destination?"** When combined with inspecting route tables, security groups, NACLs, gateways, peering, and TGW, it sharply reduces the time spent isolating connectivity failures.

A solid workflow is **define the live flow → verify DNS and addressing → analyze the path → read blocking points → make the minimal change → test TCP/TLS/app → monitor and document**. When designing AWS systems that are secure, resilient, and cost-controlled, look simultaneously across Regions/AZs, IAM, VPCs, compute, storage/databases, endpoints, logging, and budgets. Configuration-level reachability is just one layer of overall system quality.

### AWS Documentation to Consult During Implementation

- **Amazon VPC Reachability Analyzer User Guide**: concepts of Network Insights Path, analysis, explanations, supported resources, and limitations. <https://docs.aws.amazon.com/vpc/latest/reachability/>
- **Amazon VPC User Guide**: Route tables, security groups, network ACLs, Internet Gateway, NAT Gateway, VPC endpoints, VPC peering. <https://docs.aws.amazon.com/vpc/latest/userguide/>
- **AWS CLI Command Reference — EC2**: `create-network-insights-path`, `start-network-insights-analysis`, `describe-network-insights-analyses`. <https://docs.aws.amazon.com/cli/latest/reference/ec2/>
- **Amazon VPC Flow Logs**: data scope, filters, and meaning of `ACCEPT`/`REJECT`. <https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html>
- **AWS Transit Gateway documentation**: attachments, route tables, associations, propagations, and static routes. <https://docs.aws.amazon.com/vpc/latest/tgw/>

Supported features, limits, permission policies, and pricing may vary by service, account, and Region; always verify current AWS documentation before applying changes to production environments.
