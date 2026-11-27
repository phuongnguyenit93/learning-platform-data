# VCN CIDR Design and Overlap Prevention

A Virtual Cloud Network (VCN) can work fine on its own yet run into issues as soon as it connects to a data center, another VCN, or a partner network. The cause is often that both sides use the same IP range, such as both choosing 10.0.0.0/16. When that happens, the routing system cannot look at the destination address alone to know which network the server the sender actually wants to reach is located in.

In Oracle Cloud Infrastructure (OCI), CIDR design is the foundation for VCNs, subnets, hybrid connectivity, and many Compute, storage, and database services. A good design must simultaneously meet current address requirements, scalability, environment separation, and future connectivity. Compartments and IAM help manage permissions; they do not create uniqueness for network addresses.

This lesson guides IPv4 planning for VCNs, overlap checking, and choosing how to handle conflicts when detected. The addresses in the examples are hypothetical data for learning; verify against the actual address pool before deployment.

## 1. Learning Objectives

After this lesson, you will be able to:

- Read a CIDR and determine the address range it covers.
- Estimate subnet sizes from required IPs and growth rates.
- Allocate addresses by organization, environment, region, VCN, and subnet.
- Detect overlaps even when two CIDRs are written differently.
- Explain why route tables, NSGs, IAM, or compartments do not automatically resolve address collisions.
- Build a pre-check workflow before creating a VCN, adding a CIDR, or opening network connectivity.

## 2. CIDRs Describe a Set of Addresses

### 2.1. Meaning of the Prefix

IPv4 has 32 bits. A CIDR is written as a network address and a prefix length, for example **10.64.4.0/22**:

- The first 22 bits identify the network portion.
- The remaining 10 bits represent the addresses within the range.
- The total number of addresses is 2^(32 - 22) = 1,024.

The longer the prefix, the smaller the range. Therefore, /24 contains fewer addresses than /22.

| Sample CIDR | Total addresses | First address | Last address |
| --- | ---: | --- | --- |
| 10.64.0.0/16 | 65,536 | 10.64.0.0 | 10.64.255.255 |
| 10.64.0.0/20 | 4,096 | 10.64.0.0 | 10.64.15.255 |
| 10.64.4.0/22 | 1,024 | 10.64.4.0 | 10.64.7.255 |
| 10.64.8.0/23 | 512 | 10.64.8.0 | 10.64.9.255 |
| 10.64.10.0/24 | 256 | 10.64.10.0 | 10.64.10.255 |
| 10.64.10.0/26 | 64 | 10.64.10.0 | 10.64.10.63 |
| 10.64.10.64/27 | 32 | 10.64.10.64 | 10.64.10.95 |

The total number of addresses in a range differs from the number of addresses assignable to resources. In an OCI IPv4 subnet, the first two addresses and the last address are reserved. For example, subnet 10.64.10.0/24 has 256 addresses, of which .0, .1, and .255 are reserved; 253 addresses remain assignable.

A service may use multiple addresses for a single logical component. The number of available IPs remaining after deployment will depend on primary IPs, secondary IPs, and endpoints created by the service.

### 2.2. Network Addresses Must Align on Boundaries

For /22, the subnet mask is 255.255.252.0. Within 10.64.x.x, the third octet of the network address must start at a multiple of 4:

~~~text
10.64.0.0/22  -> 10.64.0.0 to 10.64.3.255
10.64.4.0/22  -> 10.64.4.0 to 10.64.7.255
10.64.8.0/22  -> 10.64.8.0 to 10.64.11.255
~~~

Writing 10.64.5.0/22 has non-zero host bits, so it is not a canonical network address representation. When normalized by the mask, it belongs to the 10.64.4.0/22 network. Input validation tools may reject non-canonical notation; do not rely on the tool fixing it automatically.

A common mistake is seeing the number 5 and assuming the range starts at 10.64.5.0, thereby overlooking that it overlaps with subnet 10.64.4.0/24.

### 2.3. Distinguishing VCN CIDR and Subnet CIDR

The VCN CIDR defines the address space the VCN uses. A subnet CIDR is a subset within that space.

Example:

~~~text
VCN: 10.64.0.0/20
  Edge subnet: 10.64.0.0/24
  App subnet:  10.64.4.0/22
  Data subnet: 10.64.8.0/23
~~~

Each subnet must reside entirely within a matching VCN CIDR, and subnets within a VCN must not overlap each other. If a VCN has multiple IPv4 blocks, check each block individually rather than merging them into an imaginary contiguous range.

Subnet 10.64.16.0/24 does not reside within VCN 10.64.0.0/20, because this VCN ends at 10.64.15.255.

## 3. Defining the Scope That Must Be Unique

### 3.1. Do Not Check Only Within a Single VCN

Uniqueness must be considered across the entire network scope expected to connect or exchange traffic:

- VCNs within the same tenancy or across tenancies.
- Regions used for production, disaster recovery, or expansion.
- Data centers and offices connected via Site-to-Site VPN or FastConnect.
- Partner networks, acquired companies, and other clouds.
- Address ranges of user VPNs, container platforms, and virtual networks inside hosts.

A pod or service range that is not advertised directly can still cause conflicts on machines that have a route to that range. Therefore, clearly document which ranges are routed across networks, which exist only locally, and what address translation mechanisms sit in between.

Two isolated environments can technically use the same CIDR. However, if they must connect later, the initial effort saved can turn into an address renumbering project. Dedicated ranges should be assigned to environments that may need to interconnect.

### 3.2. Choosing Private Address Space

RFC 1918 private IPv4 ranges include:

| Range | Address span |
| --- | --- |
| 10.0.0.0/8 | 10.0.0.0 to 10.255.255.255 |
| 172.16.0.0/12 | 172.16.0.0 to 172.31.255.255 |
| 192.168.0.0/16 | 192.168.0.0 to 192.168.255.255 |

"Private" means these addresses are not publicly routed on the Internet; it does not mean other organizations will not use the same range.

Not every address starting with 172 is a private address. For example, 172.32.0.0 does not belong to 172.16.0.0/12.

Similarly, 100.64.0.0/10 is shared address space, not an RFC 1918 range. Do not treat it as a "spare private address pool" without evaluating carrier environments, VPNs, containers, and related service requirements.

Choosing a CIDR for an internal network is also not a reason to arbitrarily pick someone else's public IP range.

### 3.3. Compartments, IAM, and Environment Names Do Not Separate Addresses

The following constructs have different roles:

| Component | Primary role in the problem |
| --- | --- |
| Compartment | Resource organization and governance |
| IAM policy | Defines who has permission to perform actions |
| VCN and subnet | Defines the network and address range |
| Route table | Determines the path of traffic |
| NSG, security list | Allows or restricts traffic according to rules |
| Address registry / IPAM | Manages allocations and prevents duplicate assignment |

Placing VCN-A and VCN-B in two different compartments does not make two 10.64.0.0/20 blocks non-overlapping. Naming a network "private" also does not create an isolation mechanism in place of routes and security rules.

## 4. Sizing from Actual IP Demand

### 4.1. Component-by-Component Inventory

Do not choose a subnet based solely on the number of currently running VMs. Build an IP budget for:

- Compute VNICs and secondary private IPs.
- Nodes and pods if the container platform's networking model consumes IPs from the subnet.
- Load balancers, private endpoints, and service-managed network resources.
- Database configurations that use multiple addresses or require dedicated subnets.
- Resources existing concurrently during rolling updates, blue-green deployments, or incident recovery.
- Expected growth over the operational cycle.

For Oracle database services, check the network requirements of the exact service and configuration chosen. Do not use a single fixed IP count for every Database, RAC, or Exadata deployment pattern.

### 4.2. Estimation Formula

You can start with this model:

~~~text
Peak demand = Fixed IPs
              + sum(peak resource count per group × IPs per resource)

IP budget = ceil(Peak demand × (1 + buffer ratio))
~~~

Then select a subnet whose assignable IP count is greater than or equal to the budget, while meeting the requirements of each service.

Example of a small application tier:

- Normally 30 instances.
- During scaling and rolling deployments, at most 80 instances exist concurrently.
- Each instance uses 2 private IPs.
- An additional 20 IPs for other components in the same subnet.
- An additional 25% buffer.

~~~text
Peak demand = 80 × 2 + 20 = 180 IPs
IP budget = ceil(180 × 1.25) = 225 IPs

/25: 128 total addresses, 125 assignable addresses -> insufficient
/24: 256 total addresses, 253 assignable addresses -> sufficient under assumptions
~~~

This conclusion is only valid if all assumptions already cover service requirements and concurrency levels. If 80 instances is the steady-state count and blue-green requires 80 additional machines, recalculate.

For a regional subnet, the budget must sum resources across all availability domains using that subnet. If the peak count is already the system-wide total, do not multiply it again by the number of availability domains.

### 4.3. Balancing Headroom and Efficient Utilization

A subnet that is too small causes difficulties when scaling or replacing resources. A subnet that is too large consumes part of the address pool that other environments might need.

Unused private addresses do not by themselves incur Compute or public IP charges. However, wasteful allocation can cause operational costs later: renumbering, adding NAT devices, or reorganizing hybrid connectivity.

A practical approach is to size for a specific growth horizon, keep contiguous reserve blocks, and review when the architecture changes.

## 5. Tiered Allocation and Explicit Reserve Blocks

### 5.1. From Organizational Pool to VCN

Suppose the network team has confirmed that 10.64.0.0/12 can be dedicated to the organization's cloud infrastructure. This range covers 10.64.0.0 to 10.79.255.255.

A plan can be structured as follows:

| Purpose | Reservation block in IPAM | Initial VCN CIDR created |
| --- | --- | --- |
| Production, primary region | 10.64.0.0/16 | 10.64.0.0/20 |
| Staging | 10.65.0.0/16 | 10.65.0.0/20 |
| Development | 10.66.0.0/16 | 10.66.0.0/20 |
| Unallocated | 10.67.0.0/16 | Not yet created |
| Production, DR region | 10.68.0.0/16 | 10.68.0.0/20 |

**A reservation block in IPAM is not the same as a CIDR configured on a VCN.** In this example, the production VCN initially has only 10.64.0.0/20. The remainder of 10.64.0.0/16 is held by the network team for expansion planning.

If the entire 10.64.0.0/16 is configured on the current VCN, do not treat 10.64.16.0/20 as a free range to assign to a VCN that needs to connect to it. That sub-range is already inside the current VCN's CIDR, even if no subnet uses it yet.

Splitting by /16 and /20 here is an address-organization example, not a mandatory rule for every system. A small system can use smaller blocks after calculating demand and checking applicable OCI limits.

### 5.2. Subnetting the Production VCN

Consider VCN **10.64.0.0/20**, from 10.64.0.0 to 10.64.15.255:

| Role | CIDR | Address span | Assignable IPs in IPv4 subnet |
| --- | --- | --- | ---: |
| Edge, such as load balancer | 10.64.0.0/24 | 10.64.0.0–10.64.0.255 | 253 |
| Application | 10.64.4.0/22 | 10.64.4.0–10.64.7.255 | 1,021 |
| Data | 10.64.8.0/23 | 10.64.8.0–10.64.9.255 | 509 |
| Private service endpoints | 10.64.10.0/24 | 10.64.10.0–10.64.10.255 | 253 |
| Operations tooling | 10.64.11.0/24 | 10.64.11.0–10.64.11.255 | 253 |

The application tier in this example assumes a larger budget than the small example in the previous section: needing around 700 IPs at peak, so /24 is insufficient and /22 provides headroom matching that assumption.

Parts without subnets created yet:

~~~text
10.64.1.0/24  : reserve near the edge tier
10.64.2.0/23  : reserve for additional needs
10.64.12.0/22 : reserve for a new application tier or cluster
~~~

All of these ranges fall within the /20 and do not overlap.

The 10.64.12.0/22 block is not adjacent to the app subnet 10.64.4.0/22, because the data and endpoint subnets sit in between. It can serve a new subnet, but it is not evidence that the existing app subnet can be expanded in place into a /21.

In fact, expanding 10.64.4.0/22 into its enclosing /21 block would involve 10.64.0.0/21, which already contains the edge subnet. This is why both CIDR boundaries and already-allocated ranges must be checked before planning an in-place expansion.

~~~mermaid
flowchart TD
    A["Organization pool: 10.64.0.0/12"] --> B["Production reservation: 10.64.0.0/16"]
    A --> C["Staging reservation: 10.65.0.0/16"]
    A --> D["DR reservation: 10.68.0.0/16"]
    B --> E["Production VCN: 10.64.0.0/20"]
    E --> F["Edge: 10.64.0.0/24"]
    E --> G["App: 10.64.4.0/22"]
    E --> H["Data: 10.64.8.0/23"]
    E --> I["Endpoint: 10.64.10.0/24"]
    E --> J["Operations: 10.64.11.0/24"]
    E --> K["Reserve ranges recorded in IPAM"]
~~~

The diagram illustrates address allocation relationships, not traffic paths or route configurations.

### 5.3. CIDR and Availability

A VCN is regional in scope. OCI has regional subnets and availability-domain-specific subnets; regional subnets allow the same subnet to serve resources across multiple availability domains in the region when supported by the service.

There is no need to create a separate IP range for each availability domain just because their names differ. Subnet division decisions should be based on architecture, service requirements, and operational policies.

Conversely, a disaster recovery (DR) region should have a separate range when there is a possibility of connecting to the primary region. Reusing the production CIDR for the DR region can cause conflicts during drills, data replication, or failback, when both environments need to operate simultaneously.

A sensible CIDR facilitates high-availability deployment; it does not guarantee HA on its own if the entire application or database remains concentrated at a single point of failure.

## 6. Checking Overlaps Properly

### 6.1. Definition

Two ranges overlap when their intersection contains at least one address.

If each CIDR is represented as an interval from the first address to the last address:

~~~text
A = [A_start, A_end]
B = [B_start, B_end]

overlap(A, B) =
    (A_start <= B_end) AND (B_start <= A_end)
~~~

For IPv4, addresses can be converted into unsigned integers:

~~~text
Value of a.b.c.d =
    a × 256^3 + b × 256^2 + c × 256 + d

Block size = 2^(32 - prefix)
Block start = floor(IP value / block size) × block size
Block end = block start + block size - 1
~~~

When implementing the check, use a reliable network address library, validate IPv4 syntax and prefix length, and require canonical network addresses as input. Do not compare strings lexicographically, because string order is not numeric IP order.

### 6.2. Easily Confused Cases

| Range A | Range B | Overlap? | Explanation |
| --- | --- | --- | --- |
| 10.64.0.0/16 | 10.64.8.0/24 | Yes | B lies inside A |
| 10.64.4.0/22 | 10.64.6.0/24 | Yes | /22 covers third octet from 4 to 7 |
| 10.64.4.0/22 | 10.64.8.0/23 | No | A ends at 10.64.7.255 |
| 10.64.0.0/24 | 10.64.0.0/24 | Yes | Two identical address sets |
| 10.64.255.0/24 | 10.65.0.0/24 | No | Two adjacent ranges with no intersection |
| 172.16.0.0/12 | 172.31.8.0/24 | Yes | 172.31.x.x still belongs to this /12 |

In particular, do not just look for identical CIDR strings. String equality checks miss the case where a larger range encloses a smaller range.

### 6.3. Distinguishing Containment from Conflict

In a tree-structured address registry, a subnet residing inside a VCN is a valid relationship; it is not an error to eliminate.

Separate rules must be applied:

1. A subnet must lie entirely within an appropriate parent VCN CIDR.
2. Sibling subnets must not intersect each other.
3. VCN CIDRs must be checked against peer VCNs and external networks intended to interconnect.
4. A reservation block may contain its own child allocations.
5. A block already assigned to another team or environment must not be reassigned simply because no active resources are seen using it yet.

If a validation tool flags every parent–child pair as an error, it will generate many false positives. If the tool ignores all containment pairs, it may miss a new VCN being placed inside another VCN's CIDR.

### 6.4. Checking Summary Routes Too

Suppose the on-premises team only uses a few subnets in 10.0.0.0/8 but advertises the entire 10.0.0.0/8 toward the cloud. A new VCN 10.64.0.0/20 may not collide with the actually assigned subnets, yet it still falls inside that summary route.

Two questions must be clarified:

- Have any addresses actually been assigned in duplicate?
- Where will summary routes, specific routes, and advertisement policies send traffic?

A more specific route may take precedence under the routing rules of the relevant component, but that should not be used in place of a clear address plan. Agree on range ownership and advertisement methods before putting connectivity into operation.

In particular, do not advertise an entire large reservation block just because it appears in IPAM. Reserve pools for address management and the set of prefixes permitted for advertisement are two pieces of information that must be managed separately.

## 7. CIDR Does Not Determine Public vs. Private Subnets

A subnet using RFC 1918 addresses can still be designed to serve resources with Internet connectivity. Public/private behavior in OCI relates to subnet configuration, whether public IP assignment is allowed, and routing architecture.

In the typical model:

- Resources that need to receive traffic from the Internet via a public IP must have a public IP configured, an appropriate path through an Internet Gateway, and permissive security rules.
- Resources in a private subnet can reach the Internet outbound via a NAT Gateway according to configured routes, without becoming a target for unsolicited inbound Internet connections.
- A Service Gateway serves access to supported OCI services per the corresponding network design; it is not a general Internet forwarding gateway.
- Routes via a DRG serve connectivity to associated networks when routes on each side are configured appropriately.

For example, naming the app subnet 10.64.4.0/22 does not automatically make it private. Likewise, separating app and database into two subnets does not automatically block all traffic between them. NSGs or security lists and the necessary security policies must still be applied.

When using subnet names like "edge", "app", and "data" in a CIDR plan, treat them as design intent that must be realized through network configuration.

## 8. Why Peering, DRG, and Firewalls Cannot Fix Overlapping IPs

Suppose there are two VCNs:

~~~text
Application VCN: 10.20.0.0/16
  App host: 10.20.1.10

Data VCN: 10.20.0.0/16
  Database host: 10.20.1.10
~~~

If the application needs to call 10.20.1.10, the destination address does not carry the information "the database host in the Data VCN". This can even be the app host's own address or an address belonging to the local network from the sender's perspective.

Adding a rule allowing TCP 1521 on an NSG does not change the meaning of the destination address. Adding a route or connecting via a DRG also does not turn two identical address sets into two unique ones.

Certain connection types have constraints on CIDRs and route advertisements. Therefore, check the conditions of the exact peering or DRG model you intend to use, rather than assuming that creating a connection lets all VCNs communicate.

The following measures do not address the root cause:

| Measure | Why it is insufficient |
| --- | --- |
| Renaming the VCN or subnet | Names do not change source/destination addresses in packets |
| Moving resources to another compartment | Compartments are not an address translation mechanism |
| Opening additional ports on an NSG | Firewalls permit packets but do not disambiguate the destination |
| Creating a new DNS record pointing to the same IP | The new name still resolves to the conflicting address |
| Adding a specific route for the overlapping address | May select one path, but cannot create two identities for the same destination IP |
| Adding a standard OCI NAT Gateway | Outbound Internet function is not an arbitrary NAT solution between private networks |

DNS can assist with migrating to new addresses, but only works when the name resolves to a network destination that the caller can route to properly.

## 9. Handling Existing Overlaps

### 9.1. Prioritize Fixing Before Workloads Exist

If it is still in the design phase, change the CIDR directly in the plan. If a test VCN was recently created with no resources that need to be kept, evaluate recreating it with an officially assigned CIDR.

The cost of fixing at this stage is usually much lower than when IPs already appear in application configs, allowlists, DNS, database connections, and monitoring tools.

Do not delete running resources on your own to resolve a conflict. Replacement must have a plan tailored to the actual state of the workload.

### 9.2. Controlled Renumbering for Running Systems

A cutover process can include:

1. Allocate a new non-overlapping range and record it in IPAM.
2. Check the ability to add a CIDR, adjust subnets, or create new subnets/VCNs per applicable OCI features, limits, and constraints.
3. Prepare routes, NSGs, DNS, operational tools, and monitoring for the new addresses.
4. Deploy replacement resources or migrate workloads in ways supported by the service.
5. Perform bidirectional testing and dependency testing before shifting traffic.
6. Gradually shift applications to the new endpoints, monitoring errors and latency.
7. Maintain a rollback plan during the change window.
8. Reclaim old resources and addresses after confirming no dependencies remain.

Do not plan on the assumption that every subnet can be resized in place or every resource can change its private IP without disruption. Change capabilities must be verified for the exact resource type.

Adding a non-overlapping CIDR to a VCN also does not automatically change the addresses of workloads residing in the old CIDR. If traffic still uses the overlapping addresses, the conflict remains.

### 9.3. Address Translation When the Original Range Cannot Be Changed Yet

In some partner connectivity cases, changing the original range is not yet feasible. A NAT architecture via an appliance or suitable network solution can present a non-overlapping representative address range.

Conceptual example:

~~~text
Actual partner network:          10.20.0.0/16
Representative range to caller:  172.30.0.0/16
Controlled mapping:              172.30.1.10 <-> 10.20.1.10
~~~

First confirm that 172.30.0.0/16 is free across the entire relevant scope; belonging to RFC 1918 does not guarantee it is unused elsewhere.

This option requires dedicated design for SNAT/DNAT, forward and return paths, appliance HA, DNS, logging, source-address visibility, and throughput capacity. Not all applications work well when protocols exchange IP addresses inside the payload.

The NAT mechanism must be tested in the actual connection initiation direction. A design that only allows connections initiated from one side may not meet the reverse business flow.

For networks managed by the organization itself, renumbering is usually a long-term option that is easier to operate than maintaining an extra translation layer.

## 10. Managing the Plan with an Address Registry

### 10.1. Minimum Information

You can start with an IPAM system or centralized management table with these fields:

| Field | Meaning |
| --- | --- |
| Canonical CIDR | Normalized network address and prefix |
| Record type | Reservation block, VCN, subnet, or external network |
| Parent block | Identifies allocation hierarchy |
| Tenancy, compartment, region | Governance and deployment location |
| Environment and purpose | Production, development, database, endpoint... |
| Owner | Team responsible for validation and reclamation |
| Status | Proposed, reserved, in use, pending reclamation, reclaimed |
| Connectivity scope | Which networks may or will exchange traffic |
| Route advertisement | Which prefixes are allowed to be advertised, and via where |
| Review date | Time of the most recent verification |

A CIDR that is proposed but does not yet have resources created should still be reserved once allocated to a specific request. Checking only existing VCNs allows two teams to claim the same range during parallel deployments.

### 10.2. Permissions for the Address Allocation Workflow

IAM can restrict who is allowed to create or update network resources in a network compartment. However, having permission to create a VCN does not mean that person may pick an arbitrary CIDR.

The workflow should tie CIDR allocation to the person responsible for address management. If using IaC, the pipeline should receive pre-allocated ranges and run checks before applying.

A pre-deployment check can be described as follows:

~~~text
INPUT:
  Proposed VCN CIDR
  List of proposed subnet CIDRs
  List of allocations/reservations and parent-child relationships
  List of external networks and related advertised routes

CHECK:
  1. All CIDRs are valid and aligned to network boundaries.
  2. VCN lies within the block assigned to the environment.
  3. VCN does not conflict with sibling allocations and interconnected networks.
  4. Each subnet lies entirely within an appropriate VCN CIDR.
  5. Subnets do not overlap each other.
  6. Portions reserved for other purposes are not used.
  7. IP budget meets peak demand and service requirements.
  8. Summary routes do not pull traffic to the wrong network domain.

OUTPUT:
  Pass result or list of conflicting pairs with owners.
~~~

This is pseudocode describing the validation workflow, not an OCI CLI command.

### 10.3. Post-Creation Tracking

After deployment, reconcile the design against reality:

- Do the created VCN and subnet CIDRs match the allocated records?
- Do used and available IP counts support upcoming scaling waves?
- Did any service create extra private IPs or endpoints beyond expectations?
- Do advertised routes match the agreed list?
- Are any old resources retaining addresses after a migration?

VCN Flow Logs and network diagnostic tools can provide additional traffic evidence within the enabled scope. They assist investigation, but do not replace an allocation registry and overlap checks.

When needing to scale resources, evaluate IP capacity ahead of the rollout rather than waiting until instance or endpoint creation fails.

## 11. Practice: Reviewing a Plan for a Production VCN

This exercise focuses on design; it can be done on paper or in an address management system, without needing to create billable resources.

### 11.1. Inputs

Suppose the following relevant networks have been fully inventoried:

| System | CIDR |
| --- | --- |
| Existing data center | 10.0.0.0/12 |
| Partner A | 172.20.0.0/16 |
| Shared tools VCN | 10.80.0.0/16 |
| Newly allocated cloud pool | 10.64.0.0/12 |

Requirements:

- Create a production VCN in the primary region.
- Include edge, application, data, endpoint, and operations tiers.
- Plan for connectivity back to the data center.
- Reserve addresses for a DR region that may operate concurrently.
- The application tier needs a budget of around 700 IPs at peak.

### 11.2. Step 1: Validate the Proposed VCN

Choose **10.64.0.0/20**.

- Data center 10.0.0.0/12 ends at 10.15.255.255, so there is no overlap.
- Partner uses 172.20.0.0/16, so there is no overlap.
- Shared tools VCN starts at 10.80.0.0, outside the 10.64.0.0/12 pool, so it does not overlap the proposed VCN.
- The proposed VCN lies within the allocated cloud pool.

This conclusion relies on the assumption that the inventory list is complete. In practice, reserved ranges and relevant summary routes must also be included in the check.

### 11.3. Step 2: Validate the Subnets

Use the five subnets from the plan in Section 5:

~~~text
Edge:       10.64.0.0/24
App:        10.64.4.0/22
Data:       10.64.8.0/23
Endpoint:   10.64.10.0/24
Operations: 10.64.11.0/24
~~~

Verify:

1. All network addresses are aligned on boundaries.
2. All ranges lie within 10.64.0.0/20.
3. No pair of subnets intersects.
4. The app subnet has 1,021 assignable IPs, meeting the 700 IP budget under the assumptions.
5. Remaining reserve ranges are explicitly documented and not assigned to another team.
6. Public/private design and traffic controls are designed separately.

### 11.4. Step 3: Handle Two Incoming Requests

**Request A:** a team requests 10.64.6.0/24 for a new batch subnet.

Result: reject the proposed range, because it lies inside the app subnet 10.64.4.0/22. Do not treat .6 as free space simply because no instances are there yet. The network team can consider part of the reserve pool and update the plan after calculating demand.

**Request B:** a team requests 10.64.16.0/24 in the same VCN.

Result: this range does not overlap the five existing subnets, but it lies outside the VCN CIDR 10.64.0.0/20. Evaluate adding valid space to the VCN or choosing a range from existing reserves; this subnet cannot be created based solely on a "no overlap" check.

### 11.5. Step 4: Prepare DR and Hybrid Connectivity

Reserve **10.68.0.0/20** for the DR VCN per the agreed plan. Even if DR is in another region, still check it within the same interconnection scope with production and on-premises.

Before opening connectivity, agree on:

- Which prefixes are advertised from each side.
- Which subnets need to communicate with each other.
- Forward and return paths, including cases passing through firewalls or intermediate appliances.
- Security rules and DNS names for each service.
- How to test when production and DR run simultaneously.

If connectivity tests fail, inspect addresses, routes, security rules, OS configuration, and listening services in turn. Do not infer that "no overlap" means "connectivity is guaranteed to work".

## 12. Common Mistakes and Consequences

| Design mistake | Consequence | Prevention |
| --- | --- | --- |
| Every environment chooses 10.0.0.0/16 | Difficult hybrid or cross-environment connectivity | Allocate CIDRs centrally before creating VCNs |
| Only comparing identical CIDR strings | Misses smaller ranges inside a larger range | Compare address intervals and containment relationships |
| Counting only current VMs | Runs out of IPs during scaling or rolling updates | Account for VNICs, secondary IPs, endpoints, and peak demand |
| Using the entire reservation pool as the VCN CIDR immediately | No non-overlapping space left for other VCNs | Distinguish IPAM reservations from configured CIDRs |
| Sharing the same CIDR for production and DR | Conflicts when both sides need to run concurrently | Assign separate ranges for each scope requiring interconnection |
| Assuming numerically adjacent subnets can expand in place | Expansion hits boundaries or overlaps other subnets | Check enclosing CIDR blocks and modification conditions |
| Believing IAM or NSG can fix duplicate addresses | Wastes time investigating the wrong layer | Resolve the IP plan first, then check routes and security |
| Advertising an overly broad prefix | Traffic to other ranges can be attracted along the wrong path | Manage advertised prefix lists separately from reserve pools |
| Forgetting to reclaim ranges after migration | Address registry drifts, making future allocation difficult | Verify dependencies and update lifecycle status |

## 13. Self-Check

### Question 1: Do 10.64.0.0/20 and 10.64.8.0/23 overlap?

Yes. The /20 range covers 10.64.0.0 to 10.64.15.255; the /23 lies completely inside it.

If the /23 is a subnet of the /20 VCN, this is a valid parent–child relationship. If the /23 belongs to another VCN that needs to connect to the /20 VCN, the conflict must be resolved.

### Question 2: Do 10.64.4.0/22 and 10.64.8.0/22 overlap?

No. The first range ends at 10.64.7.255, and the second starts at 10.64.8.0. They are adjacent but have no addresses in common.

### Question 3: Can a /24 be used for a budget of 260 private IPs?

No. A /24 has only 256 total addresses, and an OCI IPv4 subnet has 253 assignable addresses. A larger block must be chosen or the workload split under an appropriate architecture; do not solve it by cutting the required buffer.

### Question 4: Are two VCNs in two different regions both using 10.10.0.0/16 automatically safe?

You cannot conclude that. Different regions do not make addresses unique. If replication, peering, DRG connectivity, or shared access from on-premises is needed, evaluate and address potential overlap.

### Question 5: Does adding 10.70.0.0/20 to a VCN automatically fix workloads using an overlapping range?

No. Workloads retain their existing addresses until an appropriate change or migration occurs. The new CIDR only adds address space; relevant dependencies must be moved to eliminate the conflict in that traffic flow.

## 14. Pre-Deployment Checklist

- [ ] Address registry exists covering active networks, reserved ranges, and relevant external networks.
- [ ] CIDRs are boundary-aligned and within the pool assigned to the environment.
- [ ] Reservation blocks, VCN CIDRs, and subnet CIDRs are clearly distinguished.
- [ ] No overlaps exist outside permitted parent–child relationships.
- [ ] Peak IP demand, secondary IPs, endpoints, and parallel run phases have been calculated.
- [ ] Subnets meet the requirements of the exact Compute or database services used.
- [ ] Separate addresses exist for environments and regions that need to operate simultaneously.
- [ ] Reserve ranges exist, and it is clear whether they serve new subnets or expansion capacity.
- [ ] Advertised routes and summary routes have been reviewed with relevant network teams.
- [ ] Public/private behavior, gateways, and security rules have been appropriately designed.
- [ ] Owners, IP capacity tracking, and reclamation procedures are in place.

A CIDR plan has value when the operations team can clearly answer: who owns this range, what purpose it serves, where it can connect, how much capacity remains, and how it will expand. That is the basis for deploying OCI networking in a controlled way instead of renumbering addresses after applications already depend on them.
