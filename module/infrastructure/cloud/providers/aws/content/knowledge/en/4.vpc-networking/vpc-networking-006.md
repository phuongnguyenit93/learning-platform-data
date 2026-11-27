# Network ACLs and Stateless Rules

> **Chapter:** VPC Networking  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore AWS infrastructure, IAM, VPC, and application services to design secure, observable, resilient, and cost-controlled systems.

In Amazon Virtual Private Cloud (VPC), network connectivity is governed by multiple layers: IP addresses, subnets, route tables, Internet Gateways/NAT Gateways, **Network Access Control Lists (Network ACLs or NACLs)**, and **Security Groups**. A NACL is a traffic control layer **at the subnet boundary**. The most critical detail: **NACLs are stateless**, so every inbound or outbound packet is evaluated independently, even when it belongs to an already-established TCP connection.

This lesson explains how NACLs evaluate rules, why both request and response directions must be opened, and how to combine NACLs with Security Groups in a secure AWS architecture. All IP ranges and resources in the examples are hypothetical.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Describe how a NACL associates with subnets and how it differs from a Security Group.
2. Read rule fields: **rule number**, protocol, port range, CIDR, Allow/Deny, and inbound/outbound direction.
3. Explain **first-match** and **implicit deny** in NACL rule evaluation.
4. Identify the correct destination ports for request and response packets, especially **ephemeral ports**.
5. Design minimal rule sets for web, application, and database subnets; diagnose causes of broken connectivity.
6. Use the AWS Console/CLI, VPC Flow Logs, and path analysis tools to reconcile configuration with observed behavior.

## 2. What Is a Network ACL?

A **Network ACL** is a set of rules that allows or denies **inbound** and **outbound** traffic for one or more VPC subnets. A NACL inspects traffic crossing the subnet boundary based on packet attributes such as protocol, IP, and port. NACLs do not perform routing: for a packet to reach its destination, the network still requires valid routes and connectivity components.

Relationship among VPC, subnets, NACLs, and Security Groups:

~~~mermaid
flowchart TB
    Client["Client / external network"] --> Route["Routing via IGW, NAT, TGW... depending on path"]
    Route --> NACL_IN["NACL inbound at subnet boundary"]
    NACL_IN --> SG_IN["Security Group at ENI/instance"]
    SG_IN --> APP["EC2 / service in subnet"]
    APP --> SG_OUT["Security Group outbound"]
    SG_OUT --> NACL_OUT["NACL outbound at subnet boundary"]
    NACL_OUT --> Route
~~~

*This diagram illustrates the two filtering layers logically; actual packet paths depend on service type and destination. It does not imply that all internal AWS traffic traverses NACLs identically.*

### 2.1. Scope of Association

- **Each subnet must be associated with exactly one NACL** at a time.
- **One NACL can be associated with multiple subnets** in the same VPC.
- When creating a subnet, if no custom NACL is attached, it associates with the VPC's **default NACL**.
- A NACL controls traffic **entering or leaving a subnet**; it does not filter traffic exchanged between two resources **within the same subnet** as boundary-crossing traffic.
- NACLs support both IPv4 and IPv6 traffic, though separate rules must be configured for IPv4/IPv6 CIDRs.

When an application spans multiple Availability Zones (AZs), each AZ has its own subnets. A NACL attaches to a **subnet**, not directly to an AZ or EC2 instance. Two subnets in different AZs can share a NACL; however, editing a shared NACL immediately affects every associated subnet.

### 2.2. What Does Stateless Mean?

A **stateful** filter tracks connection state and automatically permits matching return flows. **NACLs do not remember connections**, so:

- **Client → server** packets are evaluated against inbound or outbound rules at the subnet boundary.
- **Server → client** packets are evaluated **from scratch** in the opposite direction.
- An inbound Allow **does not** automatically grant an outbound Allow for return packets.
- If a return packet does not match an Allow rule in the outbound direction, the connection can fail even though the request packet entered successfully.

This is the defining difference when comparing NACLs with Security Groups.

## 3. How Do Security Groups and Network ACLs Differ?

| Criterion | Network ACL | Security Group |
| --- | --- | --- |
| Scope | Subnet | Network interface (ENI), typically attached to EC2 or service network resources |
| Mechanism | **Stateless** | **Stateful** for tracked return traffic |
| Rules | Supports **Allow** and **Deny** | **Allow** rules only, no Deny rules |
| Order | Evaluated by **ascending rule number**, stopping at the first match | No numeric rule priority order |
| If no allow rule matches | Default deny via the `*` rule | Unmatched traffic is implicitly denied |
| Return flows | Must have explicit matching rules in **both directions** | Return traffic for tracked connections is normally allowed automatically |
| Source/destination selection | IPv4/IPv6 CIDRs per supported rule fields | CIDRs, prefix lists, and Security Group references in supported contexts |
| Common usage | Coarse subnet-boundary control, blocking specific network ranges | Fine-grained access filtering close to applications and between tiers |

**Example:** An application server's Security Group has inbound `TCP 443` from a client address; for a tracked TCP connection, the server can send responses without opening the corresponding ephemeral port in SG outbound. For the NACL on the server's subnet, you need **inbound for port 443** and **outbound for the client's ephemeral destination port**.

Do not use NACLs as a replacement for Security Groups. Both can be applied together, serving different roles: Security Groups provide fine-grained per-resource control, while NACLs add a subnet-level guardrail including **explicit Deny** by network range.

## 4. Structure of a NACL Rule

A NACL has **two independent lists**: inbound rules and outbound rules. Each rule includes these fields:

| Field | Example | Meaning |
| --- | --- | --- |
| **Rule number** | `100`, `110` | Priority order; **lower numbers are evaluated first** |
| **Type/Protocol** | HTTPS (TCP), HTTP (TCP), Custom TCP, UDP, ICMP | Protocol type to filter |
| **Port range** | `443` or `1024–65535` | **Destination** port of TCP/UDP packets in the evaluated direction |
| **Source** (inbound) | `203.0.113.0/24` | **Source** CIDR of packets entering the subnet |
| **Destination** (outbound) | `0.0.0.0/0` | **Destination** CIDR of packets leaving the subnet |
| **Allow / Deny** | `ALLOW` or `DENY` | Permit or block packets matching the rule |
| **IPv4 / IPv6 CIDR** | `10.20.0.0/16`, `2001:db8::/32` | Select one address family per rule; add separate rules for the other family |

For TCP/UDP, pay close attention to interpreting **port as the packet's destination port**. TCP/UDP packets also carry a source port, but NACL port-range rules evaluate **destination port**; hence TCP responses typically require opening the **initiator's** ephemeral port range in the reverse direction.

### 4.1. Rule Numbers and First-Match Evaluation

AWS evaluates NACL rules in **ascending rule number** order, independently per direction. The **first rule matching** protocol, CIDR, and port determines Allow/Deny; higher-numbered rules are not evaluated for that packet.

Example inbound table for a web subnet:

| Rule | Protocol | Source | Destination Port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `203.0.113.0/24` | 443 | **DENY** |
| 110 | TCP | `0.0.0.0/0` | 443 | **ALLOW** |
| * | All traffic | `0.0.0.0/0` | All | **DENY** |

Results:

- Client `203.0.113.25` accesses HTTPS: **Deny**, because rule 100 matches before rule 110.
- Client `198.51.100.15` accesses HTTPS: rule 100 does not match; rule 110 **Allows**.
- Client `198.51.100.15` accesses port 22: matches neither 100 nor 110; hits rule `*` and is **Denied**.

Ranges `203.0.113.0/24` and `198.51.100.0/24` are **documentation examples**, not real customer IPs. AWS imposes limits on entry counts and rule numbers; administrators commonly space numbers apart (100, 110, 120...) to leave room for insertions.

> **Common mistake:** Putting `ALLOW 443 0.0.0.0/0` at rule 100 followed by `DENY 443 203.0.113.0/24` at rule 110 **fails to block** that IP range because requests match rule 100 first.

### 4.2. The `*` Rule and When No Allow Matches

At the bottom of both inbound and outbound tables, the console displays rule **`*`** with action **DENY**, applied when no preceding rule matches. This is the NACL's built-in **implicit deny**; this catch-all rule cannot be deleted.

Do not confuse the default `*` rule with a rule using the wildcard CIDR `0.0.0.0/0`. CIDR `0.0.0.0/0` denotes all IPv4 addresses, but the outcome still depends on protocol, port, rule order, and rule action.

### 4.3. Default NACL vs. Custom NACL

| Attribute | Default NACL on New VPC Creation | Newly Created Custom NACL |
| --- | --- | --- |
| Inbound | Defaults to an Allow rule for all IPv4 traffic; may include an IPv6 rule if VPC has IPv6 | Initially has **no Allow rules** |
| Outbound | Defaults to an Allow rule for all IPv4 traffic; may include an IPv6 rule if VPC has IPv6 | Initially has **no Allow rules** |
| Bottom of list | `*` rule Denies if no prior rule matched | `*` rule Denies if no prior rule matched |
| Consequence | Default NACL is permissive; tighten access with Security Groups and other layers | Attaching to a subnet before adding rules can block all traffic crossing the subnet boundary |

The default NACL is **an editable resource**: if an administrator modified its rules, its actual behavior may differ from the initial defaults. Always inspect the active rules rather than assuming behavior from the name "default."

## 5. TCP Flows: Why Ephemeral Ports Matter

When a client opens an HTTPS connection, it picks a **temporary source port** (ephemeral port), while the server listens on **destination port 443**. The server sends responses back to that ephemeral port.

Example:

~~~text
Client 198.51.100.15:51842            Web server 10.20.1.20:443
           |                                       |
           | ---- TCP SYN: 51842 -> 443 ---------> |  (request)
           | <--- TCP SYN-ACK: 443 -> 51842 ------ |  (response)
           | ---- TCP ACK: 51842 -> 443 ---------> |  (ack)
           |                                       |
~~~

If the server is in a public subnet, the first packet entering **into the subnet** has destination port 443; the SYN-ACK leaving **out of the subnet** has destination port 51842.

Because NACLs are **stateless**, a minimal illustrative configuration for this connection requires:

| Server Subnet NACL Direction | External CIDR | TCP Destination Port | Purpose |
| --- | --- | --- | --- |
| Inbound | `198.51.100.15/32` | `443` | Allow client HTTPS access |
| Outbound | `198.51.100.15/32` | `51842` | Allow response to client's ephemeral port |

In practice, the server cannot predict port 51842 for every client, so the outbound rule must cover the **ephemeral port range** that may appear—for instance `1024–65535` when supporting diverse clients. This is an illustrative broad range; operating systems, NATs, proxies, load balancers, and applications may use **different ephemeral ranges**. Verify the behavior of the initiating side to pick the proper range.

### 5.1. The Server Can Also Be the Initiator

Suppose an application in a private subnet calls an external HTTPS API:

~~~text
App 10.20.11.20:49152  -- TCP 49152 -> 443 -->  API 198.51.100.20:443
App 10.20.11.20:49152  <-- TCP 443 -> 49152 --  API 198.51.100.20:443
~~~

For the private subnet's NACL:

- **Outbound:** must Allow destination port **443** to authorized external targets.
- **Inbound:** must Allow destination ports in the **ephemeral range** used by the app.
- If going through a **NAT Gateway**, also inspect routing, the NACL on the subnet hosting the NAT Gateway, and post-NAT addresses/ports. Editing only the app's NACL does not guarantee end-to-end success.

**Reasoning tip:** Identify *who initiates the connection?* → write `sourceIP:sourcePort → destinationIP:destinationPort` → flip it to trace the return packet → apply inbound/outbound NACL rules at **every subnet the packets traverse**.

### 5.2. UDP and ICMP Cases

**UDP** also requires evaluating both directions even without a TCP handshake. A DNS query may go to port 53 and receive a response on the client's ephemeral port. Do not open only UDP 53 in both directions assuming responses always go to port 53.

**ICMP/ICMPv6** uses type/code instead of TCP/UDP ports; network control, diagnostic, and MTU discovery messages may need dedicated rules as required. Especially with IPv6, carelessly blocking ICMPv6 can break network operation. Do not assume a TCP/UDP rule permits ICMP.

## 6. Example 1: Exposing HTTPS from a Web Subnet

**Scenario:** A web server at `10.20.1.20` sits in subnet `10.20.1.0/24` with an Internet path and a Security Group allowing HTTPS only from accepted clients. NACL goal: allow HTTPS and responses without granting SSH administrative access.

The NACL attached to the server subnet can start with this IPv4 rule set:

**Inbound:**

| Rule | Protocol | Source | Destination Port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `0.0.0.0/0` | `443` | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

**Outbound:**

| Rule | Protocol | Destination | Destination Port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `0.0.0.0/0` | `1024–65535` | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

Explanation:

- Client sends packet to port **443** → inbound rule 100 matches.
- Server returns packet to client's **ephemeral** port → outbound rule 100 matches.
- SSH port 22 request from the Internet → no inbound Allow, Denied.
- If the server also initiates calls to AWS APIs, update services, DNS, or log shipping, this rule set is **incomplete**: add rules for server-initiated connections and their return packets. Security Groups, Internet paths, NAT, route tables, and listeners must also be right.

**Limitation of this example:** outbound ephemeral `0.0.0.0/0` is a broad rule illustrating connectivity with arbitrary clients; it is not a blanket recommendation to copy verbatim into every system. Narrow CIDRs to client networks where feasible, or use an ALB/WAF architecture and appropriate protection layers.

## 7. Example 2: Two-Tier Application Behind an ALB

**Problem:** Clients access an HTTPS application via an Application Load Balancer (ALB), and the ALB forwards HTTP or app TCP traffic to EC2 targets on port 8080. Assume:

- ALB subnet: `10.20.1.0/24`, public.
- App subnet: `10.20.11.0/24`, private.
- ALB listens on `TCP 443` from the Internet; app targets listen on `TCP 8080`.
- These CIDRs illustrate **a single pair of subnets**; in a multi-AZ deployment, expand the design and verify every subnet pair across which the ALB and targets communicate.

~~~mermaid
sequenceDiagram
    participant C as Internet Client
    participant L as ALB (public subnet)
    participant A as App (private subnet)
    C->>L: TCP client_ephemeral → 443
    L-->>C: TCP 443 → client_ephemeral
    L->>A: TCP alb_ephemeral → 8080
    A-->>L: TCP 8080 → alb_ephemeral
~~~

The two connections `Client ↔ ALB` and `ALB ↔ App` are **two separate TCP flows**. NACLs must permit both forward and return directions at **both subnet boundaries**.

### 7.1. ALB Subnet NACL

| Direction | Protocol | Source / Destination | Destination Port | Flow Served |
| --- | --- | --- | --- | --- |
| Inbound | TCP | Source `0.0.0.0/0` | `443` | Client → ALB |
| Outbound | TCP | Destination `0.0.0.0/0` | `1024–65535` | ALB → client's ephemeral port |
| Outbound | TCP | Destination `10.20.11.0/24` | `8080` | ALB → App |
| Inbound | TCP | Source `10.20.11.0/24` | `1024–65535` | App → ALB's ephemeral port |

### 7.2. App Subnet NACL

| Direction | Protocol | Source / Destination | Destination Port | Flow Served |
| --- | --- | --- | --- | --- |
| Inbound | TCP | Source `10.20.1.0/24` | `8080` | ALB → App |
| Outbound | TCP | Destination `10.20.1.0/24` | `1024–65535` | App → ALB's ephemeral port |

On the Security Group side, the ALB SG can accept `TCP 443` from appropriate clients, while the App SG allows `TCP 8080` with **source = ALB SG** (where referencing is supported). Return traffic for tracked connections is handled statefully by SGs. NACLs still require the return ports shown above.

**Do not forget supporting services:** if the App also calls a database on port 5432, Redis on port 6379, DNS, secrets, or HTTPS endpoints, evaluate each of those flows separately. When the ALB sends health checks to targets, ensure health check ports and paths are allowed; if health checks use a port other than 8080, update the tables above.

### 7.3. Why Is This Example Not Yet a Complete Production Configuration?

These two tables represent only one web-and-app request chain; they omit IPv6, additional AZs, NAT, background services, databases, software updates, and monitoring. In multi-AZ designs, the ALB typically spans subnets across multiple AZs and targets can reside in multiple subnets. Enumerate **all possible source and destination subnets**, never hardcoding a single CIDR when the live application spans multiple AZs.

## 8. When the Application Connects to a Database: Applying Both Directions Again

Suppose App at `10.20.11.20` initiates a connection to PostgreSQL at `10.20.21.30:5432`:

~~~text
App 10.20.11.20:50030 -> DB 10.20.21.30:5432    (request)
DB  10.20.21.30:5432 -> App 10.20.11.20:50030    (response)
~~~

If App and DB reside in **two different subnets**, each with its own NACL, examine:

| Boundary | Direction | Remote CIDR | Destination Port | Why? |
| --- | --- | --- | --- | --- |
| App subnet | Outbound | `10.20.21.0/24` | TCP 5432 | App initiates connection to DB |
| DB subnet | Inbound | `10.20.11.0/24` | TCP 5432 | DB receives request |
| DB subnet | Outbound | `10.20.11.0/24` | App's TCP ephemeral | DB sends response |
| App subnet | Inbound | `10.20.21.0/24` | App's TCP ephemeral | App receives response |

Do not use the table above to claim that NACLs replace full database protection. For RDS and managed services, account for DB subnet groups, how the service uses ENIs, cross-AZ failover, and the database Security Group. Actual IPs can change after failover. When policies use subnet CIDRs, include all relevant standby subnets.

## 9. Common Failure States When Configuring NACLs

| Symptom | Common Cause | How to Diagnose |
| --- | --- | --- |
| Browser cannot connect to HTTPS even though EC2 is running | Inbound NACL does not Allow TCP 443, or SG/route is wrong | Check first matching inbound rule, SG, and Internet path |
| TCP sends SYN but never completes handshake | **Missing outbound ephemeral** rule for reply packets | Trace source/destination ports of SYN and SYN-ACK |
| App calling external HTTPS API times out | Missing outbound 443 or inbound ephemeral, or NAT/route error | Inspect every subnet along the request/response path |
| ALB marks target unhealthy | Missing health check port or missing ephemeral rule on one side | Cross-check listener, target group health check, SGs, and both subnet NACLs |
| IP Deny rule "has no effect" | Broad Allow sits at a **lower rule number** | Reorder rules so Deny matches first |
| Attaching custom NACL breaks the entire application | New custom NACL starts with only implicit Deny | Add all required inbound/outbound rules before associating the subnet |
| IPv4 works, IPv6 fails | Missing IPv6 rules or IPv6 path misconfigured | Inspect IPv6 CIDRs, routes, SGs, NACLs, and IPv6 support |
| Traffic between two instances in the same subnet is not blocked by NACL | NACLs filter at the **subnet boundary** | Use Security Groups and host/app controls as needed |
| Connections fail after DB failover or scale-out | New component IP/subnet or port differs from assumptions | Review standby subnets/AZs and topology changes |

**Distinguishing "REJECT" from root cause:** A VPC Flow Logs record showing `REJECT` indicates traffic was denied at the observed network layer, but it **does not directly identify which exact NACL rule caused it**; Security Groups and other conditions can also cause rejections. Correlate logs with the network path model and active configurations at the time of failure.

## 10. Designing NACLs Safely

In multi-tier systems, design from **required business flows**:

1. **Diagram subnets and AZs.** List public, app, database, NAT Gateway, and any other involved subnets.
2. **Build a connectivity matrix:** source, destination, protocol, service port, initiator, and return path.
3. **For each subnet boundary:** write inbound rules for requests and outbound rules for responses; then add the reverse flow if hosts inside the subnet also initiate outbound connections.
4. **Narrow CIDRs** where possible. Use subnet or managed network sources/destinations instead of `0.0.0.0/0` when requirements allow.
5. **Place explicit Deny rules before broad Allow rules** when blocking specific sources. Leave gaps between rule numbers so new rules can be inserted without excessive renumbering.
6. **Maintain separate Security Group controls** on resources. NACLs do not support SG references, whereas SGs can filter by source SG in supported contexts.
7. **Check both IPv4 and IPv6**, non-TCP protocols, health checks, and supporting backend services.
8. **Prepare a rollback path** before modifying a shared NACL. Editing a NACL can immediately affect multiple subnets; test in an isolated subnet or staging environment first.
9. **Monitor and validate:** use Flow Logs, Reachability Analyzer where appropriate, real source testing, and post-change monitoring.

### 10.1. Cost and Availability

A NACL is not a compute or storage service requiring servers; however, network designs involving **NAT Gateways, VPC endpoints, cross-AZ data transfer**, load balancers, and monitoring solutions incur charges. An overly strict NACL that breaks health checks, supporting services, or failover directly impacts **availability**. Evaluate performance, recovery, and cost alongside security goals.

### 10.2. What NACLs Cannot Do

- NACLs **do not manage IAM identities**, application roles, S3 permissions, or SQL-level database authorization.
- NACLs **do not control routing** and do not provide Internet, NAT, or PrivateLink connectivity on their own.
- NACLs **are not HTTP payload firewalls** and do not replace AWS WAF or DDoS protection mechanisms.
- NACLs **cannot block all flows to special AWS addresses**; traffic paths such as AmazonProvidedDNS/Route 53 Resolver, instance metadata, or infrastructure mechanisms follow separate rules. Do not rely on NACLs alone to enforce full policies for those paths.
- NACLs cannot filter by domain name, IAM principal, or Security Group ID.

## 11. Read-Only Practice with AWS CLI

The commands below are for **inspection**, not modifying configuration. They require configured AWS CLI credentials and permissions to view EC2/VPC information. Replace illustrative Region and IDs with real resources.

### 11.1. List NACLs in a Region

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --query "NetworkAcls[].{Id:NetworkAclId,Default:IsDefault,Vpc:VpcId}" \
  --output table
~~~

### 11.2. View the NACL Associated with a Specific Subnet

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --query "NetworkAcls[].{Id:NetworkAclId,Associations:Associations[].SubnetId}" \
  --output json
~~~

`subnet-0123456789abcdef0` is an illustrative ID; if this subnet does not exist in your account, the output may be an empty array.

### 11.3. Inspect Rules and Ordering

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --network-acl-ids acl-0123456789abcdef0 \
  --query "NetworkAcls[].Entries[].{No:RuleNumber,Out:Egress,Protocol:Protocol,Action:RuleAction,CIDR:CidrBlock,IPv6:Ipv6CidrBlock,Ports:PortRange}" \
  --output json
~~~

Interpret the output as follows:

- `Egress=false` means **inbound**; `Egress=true` means **outbound**.
- `RuleNumber` determines evaluation order within each direction.
- `RuleAction` is typically `allow` or `deny`.
- `CidrBlock` or `Ipv6CidrBlock` indicates the rule's address family.
- `PortRange` appears for protocols using port ranges; do not assume every rule has this field.

After retrieving the data, build an analysis table for a request `client:52000 → app:443`. Identify the first matching inbound rule, then flip directions to find the outbound rule for the response `app:443 → client:52000`.

### 11.4. Verify Network Paths

**VPC Reachability Analyzer** helps analyze paths and configurations between compatible AWS endpoints. It can pinpoint network components likely blocking traffic in the modeled path. For real incidents, also:

- Inspect Security Groups attached to the target ENI.
- Verify route tables, Internet Gateways, NAT, transit gateways, or VPC endpoints along the path.
- Check listeners/targets and whether the application is listening on the port.
- Enable and read **VPC Flow Logs** within an appropriate scope, matching timestamps and request IPs/ports.
- Test from real sources and networks; never treat a simulation alone as proof that a system is always reachable.

## 12. Reinforcement Exercises

### Exercise 1 — Which Packet Is Allowed?

A subnet has the following IPv4 inbound rules:

| Rule | Protocol | Source CIDR | Destination Port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `10.20.0.0/16` | 22 | DENY |
| 110 | TCP | `10.20.11.0/24` | 22 | ALLOW |
| 120 | TCP | `0.0.0.0/0` | 443 | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

Determine the outcome for three requests:

1. `10.20.11.50 → server:22`.
2. `198.51.100.20 → server:443`.
3. `198.51.100.20 → server:80`.

**Sample answer:** (1) Deny because rule 100 matches **before** 110; (2) Allow at 120; (3) Deny by `*`. To allow SSH from `10.20.11.0/24` while blocking the rest of `10.20.0.0/16`, place the narrower Allow rule before the broader Deny rule (while still evaluating the risk of allowing SSH).

### Exercise 2 — Which Direction Is Missing?

A public server allows inbound TCP 443 from the Internet, yet its outbound NACL only Allows TCP 443 to the Internet. A client sends a request from port `53001`.

**Question:** Why can the TCP handshake fail? Which additional rule must be considered?

**Sample answer:** The server replies to **destination port 53001**, not port 443. Outbound rules allowing only destination port 443 will not match. An outbound rule for the client's ephemeral port range is needed, narrowed by CIDR where appropriate.

### Exercise 3 — Two-AZ Design

A system uses an ALB in **two public subnets** and EC2 instances in **two private app subnets**, all within one VPC. The backend uses port 8080; the app connects to RDS on port 5432.

Trace the request/response path when the ALB selects a target in the other AZ. Identify each NACL and its corresponding inbound/outbound table, including ephemeral response ports. Then explain what changes if RDS fails over to the subnet in the other AZ. Explain why Security Groups referencing source SGs are more convenient for managing tier-to-tier permissions while NACLs still filter by CIDR.

## 13. Key Takeaways

**Network ACL = stateless filter at the subnet boundary.** In each direction, AWS evaluates rules from lowest to highest number and applies the **first matching rule**; if no rule allows the packet, it is Denied. NACLs support both Allow and Deny, whereas Security Groups provide Allow rules with connection tracking.

To analyze a network failure accurately, do not look only at "service ports" like 443 or 5432. Diagram **both directions of every connection**, identify packet destination ports at each subnet, and remember that **return ports are typically the initiator's ephemeral ports**. Secure design requires NACLs, Security Groups, routing, monitoring, and recovery planning working together.

### Official AWS Documentation

- [Control subnet traffic with network access control lists](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — concepts, subnet-level scope, and stateless behavior.
- [Network ACL rules](https://docs.aws.amazon.com/vpc/latest/userguide/nacl-rules.html) — rule ordering, structure, and implicit deny.
- [Custom network ACL for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html) — creating, editing, and associating NACLs.
- [Compare security groups and network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Security.html) — VPC security layers.
- [Ephemeral ports](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html#nacl-ephemeral-ports) — return traffic and ephemeral port ranges.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — capturing IP traffic metadata.
- [VPC Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html) — analyzing connectivity and network paths.
