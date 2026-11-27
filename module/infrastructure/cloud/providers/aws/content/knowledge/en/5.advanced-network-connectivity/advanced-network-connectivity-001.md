# VPC Peering and Non-Transitive Routing Limitations

In AWS, an application can be separated into multiple **Virtual Private Clouds (VPCs)** to isolate development environments, production, data systems, and shared services. When an application in VPC A must call a private API or access a database in VPC B, the two VPCs can be connected using **VPC Peering**. This technology establishes a traffic exchange path using the IP addresses of the two VPCs without traversing the public internet.

However, VPC Peering has a particularly important design limitation: **it does not support transitive routing (non-transitive routing)**. If VPC A peers with B and A also peers with C, B **cannot** use A as a transit network to communicate with C. Misunderstanding this easily leads to incorrect route tables, non-working deployments, and multi-VPC architectures that are difficult to scale.

This lesson belongs to the **Advanced Network Connectivity** chapter of the **CLOUD_PROVIDERS_AWS** module. This knowledge is applied when designing networks for EC2, ECS/EKS, Lambda in VPC, RDS, storage, and integration services across accounts/Regions; selecting connectivity options, configuring security, monitoring, resilience, and controlling costs.

> **Principle to remember:** VPC Peering is a **one-VPC-to-one-VPC pair** connection. Route tables, Security Groups, NACLs, and DNS must be configured appropriately on both sides. A middle VPC cannot be turned into a transitive router between peering connections.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain VPC Peering, same/cross-account and Region conditions, and IPv4/IPv6 support.
2. Read an A–B–C diagram and demonstrate why B cannot reach C through A.
3. Build **bidirectional** route tables for a peered VPC pair without confusing `local`, `pcx-...`, Internet Gateway, NAT Gateway, or Transit Gateway routes.
4. Identify limitations regarding overlapping CIDRs, DNS, Security Group references, edge-to-edge routing, and quotas.
5. Describe the workflow for requesting, accepting, activating peering, and granting actual traffic permissions.
6. Use **read-only** AWS Console and AWS CLI operations to inspect connectivity, route tables, Security Groups, NACLs, and VPC Flow Logs.
7. Choose between VPC Peering, AWS Transit Gateway, AWS Cloud WAN, and AWS PrivateLink based on actual requirements.
8. Evaluate impacts on security, availability, scalability, and data transfer costs.

## 2. VPC Peering Concepts

A **VPC Peering connection** is a networking connection between **two VPCs** that enables resources in them to exchange data using private IPv4 or IPv6 addresses. Connections can be created between:

- Two VPCs in the same AWS account, same Region.
- Two VPCs in different AWS accounts, same Region.
- Two VPCs in the same AWS account, different Regions.
- Two VPCs in different AWS accounts, different Regions.

For example, a company has a VPC running Java/Spring Boot APIs in an application account and a VPC containing private data services in a data account. When IP CIDRs do not overlap and both accounts are granted permissions to configure the connection, route tables, and appropriate network policies, the application can connect to the database's private endpoint. Peering provides **routing capability**; it does not automatically grant login permissions to the database or AWS APIs.

### 2.1. Peering is an IP-layer Network Connection, Not "Merging VPCs"

After peering, the two VPCs remain independent with respect to:

- Account ownership, IAM boundaries, and organizational SCPs.
- Subnets, route tables, Security Groups, NACLs, and DNS of each VPC.
- CIDR ranges, DNS settings, deployed resources, and their lifecycles.
- Application policies, database authentication, TLS, secrets, and service authorization.

Peering does not create a new VPC, does not merge CIDRs, does not synchronize routes, and does not create a VPN gateway or router appliance that requires operation. Traffic stays within the AWS network infrastructure; inter-Region peering travels over the AWS backbone and is encrypted in transit between Regions. For sensitive data, applications should still use TLS and dedicated authentication.

### 2.2. Prerequisites Before Creating Peering

| Prerequisite | Meaning |
|---|---|
| **Non-overlapping CIDRs** | Two VPCs cannot be peered directly if any of their IPv4 or IPv6 ranges overlap; this includes primary/secondary CIDRs |
| Both ends are valid VPCs | Accurate VPC ID, account ID, and Region |
| Operation permissions | Principal is allowed to create/accept peering; for cross-account, the receiving side must accept |
| Bidirectional routes required | Creating peering alone does not make traffic flow |
| Network access rules | SG/NACL and application firewalls must allow the required traffic flows |
| DNS | If hostnames are used, DNS resolution must be handled independently of opening IP routes |
| Quotas and data transfer | Check peering/route table quotas and data transfer costs by AZ/Region |

**CIDR example:** VPC A is `10.10.0.0/16` and VPC B is `10.20.0.0/16`, so the two ranges do not overlap. If B has CIDR `10.10.128.0/17`, it falls within A's range, so peering cannot be created even if you only intend to use a non-overlapping subnet. Having separate IPv6 CIDRs on both VPCs also **does not allow bypassing** an IPv4 overlap.

## 3. Core Problem: A Peers with B, A Peers with C, but B Cannot Reach C

Assume all three VPCs are in the same Region `ap-southeast-1`:

| VPC | IPv4 CIDR | Function |
|---|---|---|
| **A – Shared Services** | `10.10.0.0/16` | Shared APIs or services |
| **B – Application** | `10.20.0.0/16` | Backend application |
| **C – Data** | `10.30.0.0/16` | Data systems |

There are two peering connections:

- `pcx-ab`: A ↔ B.
- `pcx-ac`: A ↔ C.

~~~mermaid
flowchart TD
    B["VPC B • Application<br/>10.20.0.0/16"]
    A["VPC A • Shared Services<br/>10.10.0.0/16"]
    C["VPC C • Data<br/>10.30.0.0/16"]
    B <-->|"pcx-ab: direct"| A
    A <-->|"pcx-ac: direct"| C
    B -.-|"NO direct peering<br/>B → A → C is not supported"| C
~~~

**Valid paths:** An EC2 instance in B can call a private service in A via `pcx-ab` if routes, Security Groups, NACLs, firewalls, and the application are all properly configured. An EC2 instance in C can also call A via `pcx-ac`.

**Invalid path:** An EC2 instance in B wants to connect to the private IP of an RDS instance in C along the path `B → pcx-ab → A → pcx-ac → C`. **AWS does not forward traffic from one peering connection to another peering connection.** Adding a route to C's CIDR in B's route table with the target `pcx-ab` does not create transitive routing.

### 3.1. Why Can't Transitive Routing Be Enabled Using Static Routes?

In traditional networking, if router A knows routes to B and C, A can forward traffic between the two networks. However, **VPC Peering is not a router between VPCs**. Peering only allows traffic from one VPC to **the direct partner VPC of that connection**. The A↔B relationship is independent of A↔C; AWS does not treat A as a "transit network" for B↔C traffic.

The following actions **do not resolve** this limitation:

1. Adding a default route `0.0.0.0/0` in B pointing to `pcx-ab` to reach C.
2. Adding a route for `10.30.0.0/16` on B with target `pcx-ab` even though A is not the endpoint of C's CIDR.
3. Opening all ports in A's Security Group alone.
4. Enabling IP forwarding on an EC2 instance in A to simulate a router bridging two peering connections.
5. Adding a C→B route in C's route table while still lacking a direct B–C peering connection.

Even if the control plane accepts a certain route configuration, **the data plane does not support transitive routing across peering**. The proper fix is to have a **dedicated B–C peering** if point-to-point connectivity is needed, or use a tool designed for transitive routing such as **AWS Transit Gateway** or **AWS Cloud WAN**.

### 3.2. Adding a Direct B–C Peering

For all three VPCs to communicate with one another, you can additionally create:

- `pcx-bc`: B ↔ C.
- Routes in the required subnets in B to `10.30.0.0/16` via `pcx-bc`.
- Return routes in C to `10.20.0.0/16` via `pcx-bc`.
- Security Groups, NACLs, and application permissions for the exact communication flows.

~~~mermaid
flowchart TD
    A["VPC A"]
    B["VPC B"]
    C["VPC C"]
    A <-->|"pcx-ab"| B
    A <-->|"pcx-ac"| C
    B <-->|"pcx-bc"| C
~~~

**Now** B↔C has a direct peering path. B–C connectivity does not need to go through A. This is a **full mesh** model for three VPCs.

### 3.3. Scaling Formula

If there are `n` VPCs and every VPC must peer directly with every other VPC, the number of peering connections is:

\[
P = \frac{n(n-1)}{2}
\]

| Number of VPCs | Full mesh peering count | Notes |
|---:|---:|---|
| 2 | 1 | Very simple |
| 3 | 3 | A–B, A–C, B–C |
| 5 | 10 | More routes and SGs |
| 10 | 45 | Increased operational burden |
| 20 | 190 | Need to re-evaluate connectivity architecture |

Each VPC in a full mesh has `n − 1` connections; the total number of connections grows as `O(n²)`. AWS enforces quotas on peering connections per VPC and route entries per route table. Therefore, with tens or hundreds of VPCs, you should typically evaluate **Transit Gateway** or **Cloud WAN** instead of maintaining a full mesh.

## 4. Route Tables: Configuring Conditions for Two VPCs to Communicate

**A VPC Peering connection in the `active` state still does not guarantee traffic can flow.** The route tables associated with the source and destination subnets must contain routes to the other side's CIDR, including **both the forward path and the return path**.

### 4.1. Case A ↔ B

Given A `10.10.0.0/16`, B `10.20.0.0/16`, and illustrative peering ID `pcx-ab`. Route tables of the subnets needing to communicate:

| Subnet route table | Destination | Target |
|---|---|---|
| Subnet in A | `10.10.0.0/16` | `local` |
| Subnet in A | `10.20.0.0/16` | `pcx-ab` |
| Subnet in B | `10.20.0.0/16` | `local` |
| Subnet in B | `10.10.0.0/16` | `pcx-ab` |

The **`local` route** is added by AWS for the VPC scope to handle internal traffic. The route to the peer must point to the **VPC peering connection ID**, not to an EC2 instance, Internet Gateway, NAT Gateway, or VPC ID.

You must select the **correct route table associated with the subnet** running the resource. A VPC can have multiple route tables, and each subnet uses one route table (explicitly associated or inheriting the main route table). Adding a route to the main route table has no effect if the subnet actually uses a different custom route table.

### 4.2. Case A ↔ B and A ↔ C

So that B can call A, and C can call A:

| Route table | Destination | Target |
|---|---|---|
| A | `10.20.0.0/16` | `pcx-ab` |
| A | `10.30.0.0/16` | `pcx-ac` |
| B | `10.10.0.0/16` | `pcx-ab` |
| C | `10.10.0.0/16` | `pcx-ac` |

The local routes always exist but are omitted from this table for clarity. These routes **do not create a B→C path**. A has routes to B and C for **traffic originating from A's resources** and return traffic to applications in A. It does not become a transitive router for traffic from B to C.

### 4.3. Choosing a Narrower Route CIDR

It is not mandatory to add a route to the entire peer VPC. If an application only needs to connect to data subnet `10.30.10.0/24`, you can create a narrower route `10.30.10.0/24 → pcx-ac` in the corresponding subnet of A. In some scenarios, you can route to a single host IP `/32`. AWS uses the **longest prefix match** rule to select the most specific route.

Restricting via route tables helps reduce the scope of reachable routes, but **route tables do not replace security policies**: Security Groups, NACLs, and application authentication still must be configured properly.

### 4.4. `pending-acceptance` Connections and `blackhole` Routes

AWS allows defining a route pointing to a peering connection that is still in `pending-acceptance`, but the route may be in the **`blackhole`** state (not yet active) until the peering is accepted and becomes `active`. If the connection is deleted or invalidated, routes pointing to it also cannot establish valid data flow. Always check **both the connection's `Status.Code` and the route's `State`**.

## 5. Lifecycle of Creating and Activating Peering

The actual connection setup workflow consists of multiple independent steps:

1. **Plan IP addressing:** verify that primary/secondary IPv4 and IPv6 CIDRs of both VPCs do not overlap.
2. **Identify both ends:** account, Region, and VPC ID of the requester and accepter.
3. **Requester creates the peering request:** via Console or API `CreateVpcPeeringConnection`.
4. **Accepter accepts:** the owner of the receiving VPC must run `AcceptVpcPeeringConnection` for the connection to transition to `active`. Within the same account, the operator can perform both roles if authorized.
5. **Update route tables of the subnets needing communication:** in both VPCs.
6. **Configure SG/NACL/DNS:** according to access flows and domain name requirements.
7. **Verify actual communication and observability:** cross-check routes, flow logs, and applications.
8. **Save changes in IaC/runbooks:** manage lifecycle, permissions, costs, and cleanup if no longer used.

A `pending-acceptance` request can **expire after 7 days** if not accepted. When peering across two Regions, the requester creates the request in the source VPC's Region and the accepter receives/accepts it in the destination VPC's Region. Peering Name tags are account/Region-scoped metadata and should not be assumed to synchronize automatically across sides.

### 5.1. Operations via AWS Management Console

Go to **VPC Console → Peering connections → Create peering connection**. Select the requester VPC, the accepter's account and Region, and then select the accepter VPC. After creating the request, in the accepter's account/Region select **Actions → Accept request**. Next, open **VPC → Route tables** on each side, identify the route table by subnet association, and add a route to the peer's CIDR with the peering connection as the target.

To configure connectivity in a production environment, the team responsible for each account must approve the application flow, SG/NACL changes, and record test results. **Do not accept requests from unfamiliar accounts**; creating peering only opens routing capability, which can be the first step toward unintended access.

### 5.2. AWS CLI Examples of Mutating Operations

The commands below **illustrate administrative syntax** and will modify AWS configuration if executed with real IDs/credentials. Only run them in a lab where you have modification permissions, pre-planned VPCs/CIDRs, and appropriate approval processes.

~~~bash
# Requester side: create a connection request between VPCs in the same Region
aws ec2 create-vpc-peering-connection \
  --vpc-id vpc-REQUESTER \
  --peer-vpc-id vpc-ACCEPTER \
  --region ap-southeast-1

# Accepter side: accept the connection ID after verification
aws ec2 accept-vpc-peering-connection \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1

# Route in the requester VPC's subnet to the peer CIDR
aws ec2 create-route \
  --route-table-id rtb-REQUESTER \
  --destination-cidr-block 10.20.0.0/16 \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1

# Return route must be created on the accepter side
aws ec2 create-route \
  --route-table-id rtb-ACCEPTER \
  --destination-cidr-block 10.10.0.0/16 \
  --vpc-peering-connection-id pcx-EXAMPLE \
  --region ap-southeast-1
~~~

IDs containing `REQUESTER`, `ACCEPTER`, and `EXAMPLE` are placeholders and **cannot be used verbatim**. For cross-account peering, the accept and route commands on the accepter side are executed using an IAM principal of that account; for inter-Region peering, `--region` must be set appropriately for each side. Do not run `create-route` redundantly when a route already exists; check first and choose the appropriate modification API if needed.

### 5.3. States to Distinguish

| State | Operational Meaning |
|---|---|
| `initiating-request` | AWS is initiating the request |
| `pending-acceptance` | Waiting for the receiving VPC owner to accept |
| `active` | Peering is active; still requires valid routes/security |
| `failed` | Connection could not be created, e.g., CIDR overlap |
| `rejected` | Accepter rejected the request |
| `expired` | Request was not accepted before the expiration period |
| `deleted` | Connection was deleted/is no longer valid |

Do not rely solely on the `active` state to conclude that an application has network reachability. That conclusion requires bidirectional routes, SG/NACL rules, and testing with the exact protocol/port.

## 6. CIDR Limitation: No Overlap Allowed Between Two Directly Peered VPCs

AWS rejects peering between two VPCs when their corresponding IPv4 or IPv6 CIDRs **overlap**. This rule applies to all CIDRs attached to a VPC, including secondary CIDRs.

### 6.1. Examples

| VPC Pair | CIDRs | Can peer directly? | Explanation |
|---|---|---|---|
| A and B | A: `10.10.0.0/16`; B: `10.20.0.0/16` | Yes, if other conditions are met | No overlap |
| A and D | A: `10.10.0.0/16`; D: `10.10.128.0/17` | No | D is within A's CIDR |
| A and E | A primary: `10.10.0.0/16`, secondary: `172.20.0.0/16`; E: `172.20.8.0/21` | No | Overlaps with A's secondary CIDR |
| A and F | IPv4 does not overlap; IPv6 overlaps on both sides | No | IPv6 overlap is still a restriction |

If B and C have the same CIDR but **do not peer directly with each other**, A can still have two connections A–B and A–C if A's CIDR does not overlap with either side. This is a complex situation: A's routes must be specific enough to select the right peer, and there is no unicast reverse path forwarding guarantee that return packets go to the right place. Avoid this design for new systems if possible; allocate non-overlapping CIDRs across the entire connectivity domain to reduce risk.

### 6.2. Handling Existing Overlapping Networks

Do not try to route around this via a third VPC using peering. Options depending on requirements include:

- **Re-IP CIDRs or build a new VPC:** a clean network architecture solution when full layer 3 connectivity is required and services can be migrated.
- **AWS PrivateLink:** publish a target service for VPCs to consume via an interface endpoint; often suitable when only a specific API/service is needed and networks overlap.
- **Supported NAT/routing models via other solutions:** when address translation is genuinely needed at network scale, design and test carefully via Transit Gateway or supported network appliances; avoid assuming peering handles NAT/transit automatically.

PrivateLink is not a bidirectional full mesh connection between all addresses in two VPCs; it provides **service-level** access. You must evaluate interface endpoints, load balancers, DNS, authentication permissions, and separate costs.

## 7. Edge-to-Edge Routing Limitations

**Edge-to-edge routing** is the attempt to use a peered VPC as a transit path to another gateway or network connection.

AWS does not support the following flows **over VPC peering**:

| Intended flow | Can VPC peering be used transitively? |
|---|---|
| VPC B accesses the internet through an Internet Gateway in VPC A | **No** |
| VPC B uses VPC A's NAT Gateway/NAT device to access the internet | **No** |
| VPC B uses VPC A's VPN to reach on-premises | **No** |
| VPC B reaches on-premises via VPC A's Direct Connect/Virtual Private Gateway | **No** |
| VPC B uses an S3 gateway endpoint in VPC A | **No** |
| VPC B reaches VPC C via `pcx-ab` then `pcx-ac` | **No** |

For example, a company has a "network hub" VPC A with a NAT Gateway to control internet egress. Simply peering B with A and setting `0.0.0.0/0 → pcx-ab` in B **cannot** use A's NAT Gateway as an internet exit for B. Centralized egress networks must use a supported transit architecture (for example, Transit Gateway combined with an inspection/egress VPC) and properly configured route tables, NAT, firewalls, and resilience.

Note the distinction: the NAT Gateway service has certain mechanisms for traffic going *from a NAT in its VPC to a peer* that AWS supports in specific cases. That **does not allow clients from a peer VPC to use the other VPC's NAT as an internet gateway**.

## 8. Security: Existing Routes Do Not Mean Ports Are Open

An application connection flow from VPC B to VPC A simultaneously requires:

1. **Peering `active`** and bidirectional routes between the required subnets.
2. **Security Groups** attached to the client/server allowing egress/inbound for the right protocol/port.
3. **Network ACLs** on both subnets not blocking outbound and return traffic.
4. Host firewall, load balancer listener, application, and database actually listening on the port.
5. Proper DNS, TLS, and application authentication if hostnames/HTTPS/database users are used.

### 8.1. Stateful Security Groups

Suppose a Java client in B `10.20.1.10` needs to call a private API in A `10.10.10.20:443`:

- Client B SG: outbound TCP 443 to the API's IP/CIDR or peer SG if supported.
- Server A SG: inbound TCP 443 from B's IP/CIDR or B's SG if supported.
- SGs are **stateful**, so return traffic for a valid connection is normally allowed without needing a separate rule for ephemeral return ports.

**Referencing a peer VPC's Security Group:** AWS supports SG references if the two peered VPCs are in the **same Region**, even across different accounts (using the account ID alongside the SG ID where applicable). You cannot reference a peer VPC's SG in a **different Region**; use IP CIDRs and manage address changes instead.

Do not open `0.0.0.0/0` inbound just to "test if it works" for a private connection; doing so can expose more scope than intended if resources have other reachability paths.

### 8.2. Stateless Network ACLs

NACLs apply at the subnet boundary and are **stateless**. In addition to inbound/outbound rules for the service port, you must allow the return direction over the ephemeral port range appropriate for the OS/client. For example, when a client opens a TCP connection to a server on port 443, the response has source port 443 and destination set to the client's ephemeral port. If the NACL blocks the return direction, SYN packets may pass but the handshake will still fail.

NACLs differ from SGs in that they have allow/deny rules evaluated in rule-number order. When troubleshooting, inspect **all four inbound/outbound directions across both subnets**, not just the server's inbound rule.

### 8.3. IAM and the Application Layer

An IAM policy granting permission to **create/accept/modify peering** is control-plane authorization; IAM is not an IP firewall for all traffic over peering. Application permissions are still determined by SGs, NACLs, host firewalls, and authentication/authorization at the destination service. For example, successfully connecting VPCs does not grant access to RDS tables if database credentials are missing or the DB security group has not opened the appropriate port.

In multi-account environments, the **least privilege** principle should apply to both networking administrators and workloads. Dual-party approval should be required for changes that create routes across account boundaries.

## 9. DNS When Using VPC Peering

Enabling IP connectivity does not automatically resolve all hostnames in the peer.

### 9.1. Peering DNS Resolution Option

By default, the **public IPv4 DNS hostname** of an EC2 instance in a peer may resolve to the instance's public IPv4 address. When the DNS resolution option is enabled on the peering connection and VPC DNS conditions are met, the public IPv4 DNS hostname of an EC2 instance in the peer can resolve to its **private IPv4 address** when queried from the partner VPC.

Note that:

- The peering connection must be in the `active` state.
- Both VPCs must satisfy the `enableDnsSupport` and `enableDnsHostnames` settings.
- Requester/accepter DNS resolution options are managed on each respective side.
- The DNS resolution option does not automatically grant access to all private hosted zones in the peer.

### 9.2. Private Hosted Zones and DNS Servers

A **Route 53 private hosted zone (PHZ)** is not automatically shared just because two VPCs are peered. If an application in B needs to resolve `db.internal.example` belonging to a PHZ configured privately in A, you need an approach such as associating the PHZ with VPC B (including the appropriate cross-account workflow), Route 53 Resolver endpoints/rules, or another DNS design.

You cannot directly query the **Amazon-provided DNS server of a peer VPC** by sending DNS traffic across peering to ask the peer's resolver to process it. Therefore, distinguish three things:

1. Is A↔B IP connectivity working?
2. Does the hostname resolve to the **correct private IP**?
3. After resolution, are SG/NACL/application ports open?

When `curl https://service.internal` fails while calling the private IP directly succeeds, the investigation typically points to DNS/TLS hostname issues rather than route tables. Calling the IP directly is an appropriate diagnostic step; for TLS certificates, the exact hostname/SNI may still be required.

## 10. Inter-Region Peering, IPv6, Quotas, and Costs

### 10.1. Cross-Region

VPC Peering supports inter-Region connectivity without requiring an Internet Gateway, VPN, or Direct Connect to carry traffic between two VPCs. Inter-Region traffic travels over the AWS backbone and is encrypted by AWS in transit. Even so, latency between geographic regions can still affect synchronous applications, database replication, and timeouts. Application design must also ensure appropriate retries, idempotency, and failover strategies.

With inter-Region peering, peering management and routing operations must be performed in **each side's respective Region**. Security Group references to a peer in another Region are not supported. DNS resolution options across Regions must be configured appropriately if EC2 hostnames need to return private IPs.

### 10.2. IPv6

Peering can carry IPv6 if both VPCs have non-overlapping IPv6 CIDRs, resources/subnets are configured with IPv6, and route tables on both sides have IPv6 routes to the peering connection. Security Groups/NACLs must allow the corresponding IPv6 flows. Do not assume that opening IPv4 CIDRs automatically opens IPv6.

### 10.3. Quotas

Each VPC has a quota for active/pending peering connections, and route tables have entry quotas. According to AWS documentation, the default quota for active peering connections per VPC is currently **50**, which can be requested to be increased within AWS-supported limits; specific quotas also depend on account/Region and are subject to updates. Before deciding on a full mesh, check **Service Quotas** and calculate route counts per subnet rather than assuming quotas will suffice.

### 10.4. Costs

AWS does not charge a separate fee for **creating a peering connection**. Costs arise primarily from data transfer over peering:

- Data transfer over peering within the **same Availability Zone** is free under AWS service terms, even across different accounts.
- Traffic **across different AZs** within a Region may incur transfer charges according to the relevant pricing schedule.
- **Inter-Region peering** incurs inter-Region data transfer charges.
- Source/destination resources such as EC2, RDS, load balancers, CloudWatch, and other services have their own charges.

AZ names like `ap-southeast-1a` can map to different physical AZs across accounts; use the **AZ ID** when you need to match the same physical AZ. Check the latest **Amazon VPC/EC2 Pricing** before finalizing budgets. Govern based on actual data: GB transferred, traffic direction, number of VPC pairs, Region, placement, and growth plans.

## 11. Peering, Transit Gateway, Cloud WAN, or PrivateLink?

| Criterion | VPC Peering | AWS Transit Gateway | AWS Cloud WAN | AWS PrivateLink |
|---|---|---|---|---|
| Concept | Direct connection between two VPCs | Central transit hub between multiple VPCs and connected networks | Global network management via policies and segments | Publish/consume private services via endpoints |
| Transitive routing | **No** | **Yes**, when attachments/route tables permit | Yes, by segment/policy design | Not full network routing |
| Best suited for | Few VPCs, stable connection pairs | Many VPCs, hub-and-spoke, hybrid networking | Large-scale multi-Region, multi-account networks | Controlled access to a specific service/endpoint |
| Overlapping CIDRs | Not allowed for directly peered pairs | Must resolve/design around overlap for routing between attachments | Requires appropriate address planning and policies | Can serve service-access use cases when networks overlap |
| Operations | Manage each pair + routes on both sides | Manage attachments, TGW route tables, and VPC routes | Manage core network, policies, segments | Manage endpoints/services, DNS, and application authorization |
| Cost | Data transfer; no connection creation fee | Attachment-hour, data processing, transfer per pricing | Core network/attachment/data fees per pricing | Endpoint-hour and data processing per service |

### 11.1. When to Choose Peering?

- You have two or a small number of VPCs with non-overlapping CIDRs needing bidirectional private IP exchange.
- No third VPC is needed as transit.
- You want explicit management of each connection and route in small numbers.
- Cross-account or inter-Region direct connectivity needs to be simple, with administrative access on both ends.

### 11.2. When to Choose Transit Gateway?

- Many VPCs need to communicate with each other or reach on-premises networks in a hub model.
- You need controlled **transitive routing** using TGW route tables, propagation, and associations.
- You want to reduce point-to-point connections and apply network segmentation and security inspection at appropriate points.

However, **attaching every VPC to a Transit Gateway does not mean every VPC is automatically allowed to see each other**. Reachability is still governed by VPC route tables, TGW route tables, SGs/NACLs, policies, and other configurations. Attachments carry their own costs and quotas.

### 11.3. When to Choose Cloud WAN or PrivateLink?

**AWS Cloud WAN** is suitable when managing large networks across Regions/accounts with network policies, segmentation, and centralized governance. **AWS PrivateLink** is suitable when a provider only needs to grant consumers access to a specific service via a private endpoint without opening general IP connectivity between two VPCs; it fits many service-sharing models across account boundaries, even when CIDR ranges overlap.

If B only needs to call one API in C, **PrivateLink** may make more sense for narrow access. If B needs to communicate with dozens of subnets/resources in C and many other VPCs, **Transit Gateway/Cloud WAN** may be more appropriate.

## 12. Read-Only Lab: Observing Peering and Checking the A↔B Path

### 12.1. Prerequisites

- An AWS account/lab with at least one VPC; if no peering exists, you can use a hypothetical model and analyze sample output.
- AWS CLI v2 configured with an SSO/role profile having read permissions `ec2:DescribeVpcs`, `ec2:DescribeVpcPeeringConnections`, `ec2:DescribeRouteTables`, `ec2:DescribeSecurityGroups`, and `ec2:DescribeNetworkAcls` as needed.
- Example Region: `ap-southeast-1`. If using a different Region, replace it with the target VPC's Region.
- The lab **does not create, accept, or delete peering or modify routes/SGs/NACLs**; it only queries metadata.

### 12.2. Step A – Confirm Identity and VPC CIDRs

~~~bash
# Ensure you are using the right account/role
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

# List VPC IDs, primary/secondary IPv4, and IPv6 associations
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,PrimaryIpv4:CidrBlock,AllIpv4:CidrBlockAssociationSet[].CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock}' \
  --output json
~~~

Record the VPC ID, CIDR, owner account, and exact Region; compare the CIDR ranges. If the output is empty, there may be no VPC in that Region or the account may be incorrect; if you get `AccessDenied`, check the granted permissions.

### 12.3. Step B – List Peering Connections

~~~bash
aws ec2 describe-vpc-peering-connections \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcPeeringConnections[].{PeeringId:VpcPeeringConnectionId,Status:Status.Code,Requester:RequesterVpcInfo.VpcId,RequesterOwner:RequesterVpcInfo.OwnerId,RequesterRegion:RequesterVpcInfo.Region,Accepter:AccepterVpcInfo.VpcId,AccepterOwner:AccepterVpcInfo.OwnerId,AccepterRegion:AccepterVpcInfo.Region}' \
  --output table
~~~

Note each `VpcPeeringConnectionId`, `Status.Code`, requester/accepter VPC IDs, owners, and Regions. If you see `pending-acceptance`, review your organization's permission/approval workflow; do not accept requests from unknown accounts. For inter-Region peering, check the appropriate management location and Region metadata on both ends.

### 12.4. Step C – Read Route Tables by VPC/Subnet

Replace `vpc-EXAMPLE-A` with a VPC ID you are authorized to view:

~~~bash
aws ec2 describe-route-tables \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'RouteTables[].{TableId:RouteTableId,Associations:Associations[].SubnetId,Routes:Routes[].{Ipv4:DestinationCidrBlock,Ipv6:DestinationIpv6CidrBlock,Target:VpcPeeringConnectionId,State:State}}' \
  --output json
~~~

Find routes with `VpcPeeringConnectionId = pcx-...` and compare them against the peer VPC's CIDR. Identify which route table the application's subnet uses; if there is no explicit association, it uses the **main route table**. Check the opposite side in the peer account/Region to confirm the return route exists.

### 12.5. Step D – Check Security Groups and NACLs

~~~bash
aws ec2 describe-security-groups \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'SecurityGroups[].{Id:GroupId,Name:GroupName,Inbound:IpPermissions,Outbound:IpPermissionsEgress}' \
  --output json

aws ec2 describe-network-acls \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-EXAMPLE-A \
  --query 'NetworkAcls[].{Id:NetworkAclId,Entries:Entries,Associations:Associations}' \
  --output json
~~~

Verify service ports, valid source CIDRs or SGs, and outbound/return directions. Do not open all ports just because ping fails: ICMP can be blocked while HTTPS 443 still works.

### 12.6. Step E – Cross-Check Console and Architecture

In the VPC Console, inspect **Peering connections**, **Route tables**, **Security Groups**, and target resources. Draw an accurate diagram of the actual connected pairs. Answer:

1. Is there a direct peering connection from B to C?
2. If not, why does the route `B → pcx-ba → A → pcx-ac → C` not work?
3. Which route tables are attached to the source subnet and destination subnet?
4. What does a `blackhole` route indicate?
5. Are any SG/NACL rules blocking the desired protocol/port?
6. If a DNS hostname resolves to the wrong IP, which attributes would you check?

Only when you have operational permissions and the lab environment permits it should you perform an advanced exercise creating A–B peering, accepting it, and configuring bidirectional routes. For shared/production accounts, review and prepare a rollback plan before making changes.

## 13. Troubleshooting: Finding the Exact Cause of Connection Failures

A Java program in B calling a service in A over HTTPS may time out even though peering is `active`. Diagnose in order:

| Symptom | Check first |
|---|---|
| Peering not found | Correct account/Region? Requester/accepter VPC IDs? |
| `pending-acceptance` or `expired` | Did the receiving side accept before expiration? |
| Peering `failed` | Do IPv4/IPv6 CIDRs overlap? |
| Peering `active` but unreachable | Route table of the **exact subnet** on both ends; correct `pcx-...` target? |
| Route `blackhole` | Is peering not yet active, deleted, or no longer valid? |
| TCP timeout despite having routes | SG inbound/outbound, NACL forward/return directions, host firewall, port/listener |
| DNS hostname returns public IP | Are the DNS resolution option and VPC DNS attributes enabled? |
| Private hostname does not resolve | PHZ association, Route 53 Resolver rules/endpoints |
| B↔A works, A↔C works, B↔C fails | **This is non-transitive peering**; requires direct B–C peering or a transit model |
| Traffic misrouted between two peers | Overlapping peer CIDRs, route specificity/longest-prefix-match, missing proper return route |
| Fails only cross-Region or under load | Check latency, MTU/PMTUD, application throughput, data transfer, DNS, and timeouts |

### 13.1. Using Observability in the Right Places

- **VPC Flow Logs:** records IP traffic metadata at the ENI/subnet/VPC level as configured; helps inspect `ACCEPT`/`REJECT`, IP/port/protocol, though `ACCEPT` does not guarantee the application processed the request successfully.
- **Reachability Analyzer:** analyzes reachability paths and networking components that may block connections; used to detect wrong routes, SG/NACL issues, and path limitations supported by the tool.
- **CloudWatch metrics/logs and application logs:** help inspect TCP timeouts, database connection pools, DNS errors, and retries.
- **CloudTrail:** useful for investigating who created/accepted peering or modified routes or SGs/NACLs in the control plane when those events are logged.
- **VPC IP Address Manager (IPAM):** assists with planning, allocating, and tracking CIDRs to minimize overlap in multi-VPC architectures.

Do not conclude a flow is secure just because it runs over private peering; application-layer encryption, proper IAM/credentials, and database security measures are still required.

## 14. Architecture Scenario: Multi-VPC Java/Spring Boot Application

An enterprise designs three domains:

- **VPC App (B):** hosts ECS services running Java/Spring Boot, sending requests to shared APIs.
- **VPC Shared (A):** hosts an authentication proxy and several internal APIs.
- **VPC Data (C):** hosts private RDS/Aurora and data administration services.

Initially, App B only called APIs in A, and Data C also called APIs in A. The two peering connections B–A and C–A were sufficient for **those direct flows**. Later, a developer added a feature for App B to access the DB in C via private IP; the request failed even though A could communicate with both sides.

The reason is that B **cannot go through A** to reach C. Possible solutions:

1. **If B only needs to access a single service in C:** consider PrivateLink or an API exposed through A where **the application receives the request and initiates its own call to service C** (two separate application connections B→A and A→C, not IP packet forwarding through A). Security, auth, latency, and cost must be evaluated.
2. **If B and C need direct bidirectional IP connectivity at small scale:** add B–C peering and bidirectional routes, with port-specific SGs/NACLs.
3. **If there will be dozens of VPCs and hybrid connectivity in the future:** design Transit Gateway/Cloud WAN with routing domains, segmentation, inspection, and proper CIDR and cost planning.

**Distinguishing the network layer from the application layer:** VPC A can run an API proxy that receives a request from B, and then the proxy application initiates a **new request** to C. This is application-layer logic; it does not enable forwarding arbitrary TCP/IP packets from B through A to C. Using a proxy is only appropriate if the architecture and application policy intentionally call for it.

## 15. Self-Assessment Questions

1. If A peers with B and B peers with C, can A send packets to C through B? Why?
2. Three VPCs A, B, C need pairwise connectivity using Peering: how many connections and basic bidirectional routes are required?
3. A peering connection is `active`, but the peer side is missing a return route. What error typically occurs?
4. VPC A and B have different primary IPv4 CIDRs, but their secondary IPv4 CIDRs overlap. Can they peer directly?
5. Why does opening inbound Security Group port 443 not fix the non-transitive routing limitation?
6. Can a client in VPC B use VPC A's NAT Gateway over peering to access the internet?
7. Can inter-Region VPC peering reference a peer's Security Group in another Region?
8. VPC B needs to resolve private hostnames from a Route 53 private hosted zone in A. Is peering alone enough?
9. In what cases is PrivateLink more suitable than Peering?
10. In an environment with 10 VPCs connected in a full mesh, how many peering connections are there?
11. If flow logs on both ends record `ACCEPT` but the application still fails, which additional layers should be checked?
12. Why is it necessary to monitor cross-AZ/cross-Region data transfer, even though creating peering incurs no fee?

### Guiding Answers

- **Non-transitive:** there is no default transit or configuration to enable transit over peering; a direct peering or TGW/Cloud WAN architecture is required.
- **Bidirectional routes:** both the source subnet and destination subnet must have routes to the peer CIDR via the exact `pcx-...`; evaluate SGs/NACLs, DNS, and applications independently.
- **CIDR overlap:** direct peering is not possible if any IPv4/IPv6 ranges overlap between the VPC pair.
- **Scaling:** a full mesh of `n` VPCs requires `n(n-1)/2` connections; 10 VPCs require 45 connections.
- **Service selection:** Peering directly connects a small number of VPCs; Transit Gateway/Cloud WAN serves transit networks; PrivateLink serves access to a specific service.

## 16. Official AWS Documentation

1. [What is VPC Peering?](https://docs.aws.amazon.com/vpc/latest/peering/what-is-vpc-peering.html) — Concepts, account/Region scope, and traffic.
2. [How VPC peering connections work](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-basics.html) — Non-transitive peering, CIDR overlap, edge-to-edge routing, and other limitations.
3. [Create a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/create-vpc-peering-connection.html) — Requester and accepter.
4. [Accept or reject a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/accept-vpc-peering-connection.html) — Approval and safety with partner accounts.
5. [Update your route tables](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-routing.html) — Bidirectional routes, `blackhole`, and `pcx-...` targets.
6. [VPC Peering common configurations](https://docs.aws.amazon.com/vpc/latest/peering/peering-configurations-full-access.html) — Star/full mesh diagrams.
7. [Peering configurations with specific routes](https://docs.aws.amazon.com/vpc/latest/peering/peering-configurations-partial-access.html) — Longest prefix match and overlapping peer CIDR considerations.
8. [Reference peer security groups](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-security-groups.html) — Regional limits on SG references.
9. [Enable DNS resolution for peering](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-dns.html) — DNS hostnames when peering.
10. [Troubleshoot a VPC peering connection](https://docs.aws.amazon.com/vpc/latest/peering/troubleshoot-vpc-peering-connections.html) — Routes, SGs/NACLs, and Reachability Analyzer.
11. [VPC Peering quotas](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-connection-quotas.html) — Connection limits.
12. [AWS: Network connectivity between VPCs and Regions](https://docs.aws.amazon.com/prescriptive-guidance/latest/secure-outbound-network-traffic/vpc-region-communication.html) — Comparing Peering and Transit Gateway.

> **Remember:** **A–B and A–C do not imply B–C.** VPC Peering only carries traffic between two VPCs **that are directly peered**. Before deployment, verify non-overlapping CIDRs, active request status, bidirectional routes, SGs/NACLs/DNS, IAM policies, and security requirements. If the design requires transit between multiple networks, use a service that supports transitive routing rather than trying to add static routes to peering.
