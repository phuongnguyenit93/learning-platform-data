# Security Groups and Stateful Rules

> **Chapter:** VPC Networking  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Regions/Availability Zones (AZs), IAM, VPC, compute, storage, databases, integration, and serverless; practice designing secure, monitored, resilient, and cost-controlled applications.

## Learning Objectives

After completing this lesson, you will be able to:

1. Explain where Security Groups (SGs) protect traffic in Amazon VPC and distinguish them from route tables, Network ACLs (NACLs), IAM, and AWS WAF.
2. Read and design **inbound rules** and **outbound rules** by protocol, port, CIDR block, prefix list, or referenced Security Group.
3. Explain **stateful** behavior: return traffic for an allowed connection passes back through the Security Group without needing a separate rule for the reverse direction.
4. Distinguish a VPC's default Security Group from newly created Security Groups; understand **allow-only**, **implicit deny**, and how multiple Security Groups combine.
5. Design network segmentation for a multi-tier **Internet → ALB → EC2/app → RDS** architecture deployable across multiple AZs.
6. Diagnose connection failures, inspect configurations using the AWS CLI, and use VPC Flow Logs and observability tools when needed.
7. Apply least privilege to both inbound and outbound flows, while recognizing the impact of network configuration on availability and cost.

## 1. What Is a Security Group?

A **Security Group** is an AWS network traffic control mechanism attached to **network interfaces** (typically Elastic Network Interfaces — ENIs) of supported resources inside a VPC. A Security Group consists of rules allowing **inbound** and **outbound** traffic.

Imagine an application running on EC2:

- The website needs to accept HTTPS on TCP port **443**.
- The backend needs to talk to a PostgreSQL database on TCP port **5432**.
- The database should accept connections only from the backend, never directly from the Internet.

Security Groups express those requirements as network rules. A rule can state: "Allow TCP/5432 **from network interfaces attached to the backend Security Group** to the database," rather than opening the database port to all IP addresses.

A Security Group is a network-layer protection. It **does not replace** application user authentication, IAM authorization, TLS encryption, OS patching, data protection, or VPC routing design.

### 1.1. Where Do Security Groups Sit in the Network Model?

~~~mermaid
flowchart LR
    C["Client / external system"] --> RT["Network path via route table and connectivity components"]
    RT --> NACL["NACL at subnet boundary"]
    NACL --> ENI["ENI with attached Security Group"]
    ENI --> APP["Application on EC2 / supported resource"]
~~~

This diagram is a conceptual model of control layers, not an exact packet-processing order across every architecture. What matters is:

- **Route table** determines whether packets have a valid network path.
- **NACL** evaluates traffic at the subnet level using allow/deny rules.
- **Security Group** controls traffic for attached interfaces/resources using allow-only rules.
- **The application or OS** must still actually listen on that port, be properly configured, and handle valid requests.

**Conclusion:** If a route does not exist, a Security Group Allow rule will not establish connectivity. Conversely, if a route exists but the Security Group does not allow it, traffic is blocked at the Security Group layer.

### 1.2. Scope of a Security Group

A Security Group is created inside a **VPC**. When creating resources such as EC2, RDS, or an Application Load Balancer (ALB), you attach appropriate Security Groups to the corresponding network interfaces or resources within the scope and conditions supported by the service.

An ENI can have **multiple Security Groups**. **Allow** rules from all Security Groups attached to the same interface are evaluated cumulatively. For example, if SG-A allows inbound 443 from the Internet and SG-B allows inbound 22 from an admin network, both flows can be permitted on an interface attached to both SG-A and SG-B, provided other control layers allow them.

There is no concept of "Security Group A takes precedence over Security Group B" by attachment order. **You cannot attach a Security Group containing Deny rules to override Allow rules from another Security Group**, because standard Security Groups only support allow rules.

## 2. Components of a Security Group Rule

A Security Group typically has two sets of rules:

| Type | What It Controls | Example |
| --- | --- | --- |
| **Inbound rule** | Traffic **entering** the interface/resource. | Allow TCP/443 from the Internet to the ALB. |
| **Outbound rule** | Traffic **leaving** the interface/resource. | Allow the app to call the database on TCP/5432. |

Common fields in each rule:

| Field | Meaning | Example |
| --- | --- | --- |
| **Direction** | Inbound or outbound. | Inbound |
| **Protocol** | TCP, UDP, ICMP/ICMPv6, or supported protocol type. | TCP |
| **Port / port range** | Port or port range, when the protocol uses ports. | 443; 8080; 5432 |
| **Source / destination** | Source for inbound, destination for outbound. | 203.0.113.0/24; another Security Group |
| **Description** | Explanation of why access is granted. | HTTPS from visitors |
| **Rule ID** | Identifier of a rule for viewing, auditing, and management. | sgr-… |

Common source/destination types:

- **IPv4 CIDR:** e.g., **10.0.0.0/16** for an internal network or **0.0.0.0/0** for all IPv4 addresses.
- **IPv6 CIDR:** e.g., **::/0** for all IPv6 addresses; manage IPv6 separately if the VPC/resources use IPv6.
- **Security Group ID:** references network interfaces attached to the specified group where supported by the networking model.
- **Managed prefix list:** a managed list of CIDRs where supported by services; helpful for managing multiple address ranges.

**Security Groups do not filter by domain names, URL paths, or HTTP payloads.** If you need access control by web path, application authentication mechanisms or layers like AWS WAF/ALB are more appropriate.

### 2.1. Example: Reading Three Rules

| SG | Direction | Protocol/Port | Source or Destination | Meaning |
| --- | --- | --- | --- | --- |
| **alb-sg** | Inbound | TCP/443 | 0.0.0.0/0 | ALB accepts HTTPS from any IPv4 address. |
| **app-sg** | Inbound | TCP/8080 | **alb-sg** | Only interfaces belonging to alb-sg may initiate connections to the app on port 8080. |
| **db-sg** | Inbound | TCP/5432 | **app-sg** | PostgreSQL database accepts connections from the app, not from arbitrary sources in the VPC. |

The three inbound rules above are not enough to prove the application works. You must also inspect **outbound rules on the initiating side**, routes, NACLs, and listener/port configurations on each service.

## 3. What Does Stateful Mean?

**Stateful** means the Security Group tracks connection state. When a request is allowed by a rule in the initiating direction, the **corresponding return traffic** is permitted back through the Security Group without requiring a separate rule for the reverse direction.

### 3.1. Inbound HTTPS Example

Suppose a client with IP **203.0.113.10** connects to web server **10.0.2.20** over HTTPS:

| Step | Direction | Illustrative Port Pair | SG Check |
| --- | --- | --- | --- |
| 1 | Client → Server | 203.0.113.10:**51524** → 10.0.2.20:**443** | Server's inbound rule must Allow TCP/443 from the appropriate source. |
| 2 | Server → Client | 10.0.2.20:**443** → 203.0.113.10:**51524** | Return traffic for the permitted connection is handled **statefully** by the SG. |

Port **51524** is an illustrative **ephemeral port** used by the client; in practice this value varies by OS and connection.

~~~mermaid
sequenceDiagram
    participant C as Client 203.0.113.10
    participant S as Server SG
    participant W as Web server TCP/443
    C->>S: TCP source 51524 → destination 443
    Note over S: Check inbound Allow TCP/443
    S->>W: Forward permitted packet
    W-->>S: Response source 443 → destination 51524
    Note over S: Allow response based on connection state
    S-->>C: Return HTTPS response
~~~

**Key point:** You do not need to add an outbound rule "allow TCP/51524" just for the server to reply to an already-allowed inbound HTTPS connection. Outbound rules are still evaluated separately when **the server initiates a new outbound connection**.

### 3.2. Outbound HTTPS from EC2 Example

An EC2 instance needs to call a service API on TCP/443:

1. The EC2 instance's outbound rules allow new connections to the target endpoint on TCP/443.
2. The EC2 instance initiates the connection.
3. Response packets from the external endpoint enter the EC2 instance via stateful tracking without needing an inbound rule for the ephemeral port.

This means **an SG with empty inbound rules can still receive responses to permitted outbound connections**. Empty inbound rules do not mean the host receives zero packets; they prevent new unpermitted inbound flows.

### 3.3. Stateful Does Not Mean "Allow All Directions"

Common incorrect conclusions:

- "Having inbound 443 lets the server automatically initiate new outbound Internet connections on 443." → **False.** New connections initiated by the server are evaluated against outbound rules.
- "Having outbound 5432 from the app lets the database automatically accept connections on 5432." → **False.** The database side still needs an appropriate inbound rule.
- "Once a connection succeeded earlier, all packets from that IP are permanently allowed." → **False.** SGs evaluate traffic belonging to tracked connections/flows, not unlimited access for an IP.
- "SGs alone are enough; NACLs don't matter." → **False.** NACLs are stateless and require inspecting both directions if restrictive rules exist.

### 3.4. Connection Tracking and Practical Caveats

AWS uses connection tracking for Security Groups, with behaviors and exceptions depending on protocol, traffic type, and resource type. Some traffic flows are **untracked** under very broad allow configurations; do not treat SGs as a full TCP session-inspecting application firewall.

In some cases, **modifying a rule does not immediately drop all active connections** because connection tracking state can persist until timeout or closure; certain untracked flows may behave differently. When handling security incidents, verify actual behavior, actively terminate sessions or change paths if necessary, and consult AWS *Security group connection tracking* documentation.

**Remember:** Stateful behavior mainly eliminates extra rules for **return traffic**. It does not replace restricting new connections, application session management, or application-layer firewalls.

## 4. Default Rules, Implicit Deny, and Multiple Security Groups

### 4.1. Newly Created Security Groups

For a Security Group you newly create in a VPC, the initial configuration is typically:

- **Inbound:** no rules allowing new inbound traffic.
- **Outbound:** a default rule allowing all IPv4 outbound traffic; if IPv6 is enabled within scope, a corresponding IPv6 outbound rule may exist.

Always **inspect the actual configuration** before drawing conclusions, as operators, templates, or IaC tools may alter rules upon creation.

Because SGs are **allow-only**, any new flow not matched by an allow rule is **implicitly denied**. Security Groups do not have explicit **Deny** rules or numeric rule ordering like NACLs.

### 4.2. Default Security Group of a VPC

Every VPC has a **default Security Group**. Its initial configuration usually includes:

- Inbound allowing traffic from **interfaces attached to that same default Security Group** (self-reference).
- Outbound allowing all traffic per the existing default rules.

Note that "default" **does not** mean optimal for production. If many resources share the default SG, its self-referencing inbound rule can let them communicate directly across the network even when the application does not require it.

**Recommendation:** Create role-specific SGs such as **alb-sg**, **app-sg**, and **db-sg**, keeping only the rules needed for each role. Audit uses of the default SG and tighten them per environment policy.

### 4.3. Multiple Security Groups Merge Cumulative Allows

Suppose an EC2 instance has two SGs:

- SG-A: inbound TCP/443 from **0.0.0.0/0**.
- SG-B: inbound TCP/22 from **10.10.0.0/16**.

With both attached, the EC2 instance can accept **both HTTPS 443 from the Internet** and **SSH 22 from the admin network**, provided other layers do not block them.

If you detach SG-A, Internet sources lose inbound 443 access granted by SG-A; however, another SG might still allow 443. You cannot attach a "block-all" SG to negate SG-A's permissions. To tighten access, modify or remove the overly broad Allow rule or SG.

### 4.4. Inbound and Outbound Rules Are Independent for New Connections

Practical phrasing during reviews:

- **Inbound:** "Who is allowed to **initiate** connections to this resource, on which protocol/port?"
- **Outbound:** "Where is this resource allowed to **initiate** connections, on which protocol/port?"

For a **client → server** flow, typically both **client outbound** and **server inbound** must allow the new flow. The return direction is handled by stateful SGs, while still needing to satisfy other network layers along the path.

## 5. Security Group Referencing: Granting Access by Network Role

A Security Group can reference **another Security Group's ID** instead of a static list of IP addresses, within the networking scopes and referencing rules supported by AWS.

For example:

- **app-sg** inbound TCP/8080 **source = alb-sg**.
- **db-sg** inbound TCP/5432 **source = app-sg**.

When a new EC2 instance is launched with **app-sg**, it automatically becomes an eligible source for **db-sg** without manually adding the instance's private IP to the rule.

### 5.1. What Happens When Referencing an SG?

When an inbound rule specifies **source = app-sg**, it allows traffic from interfaces attached to **app-sg**, per AWS mechanics within supported connectivity scopes. It does **not** "copy" all of app-sg's rules into db-sg.

**SG references are not transitive:**

- **alb-sg → app-sg** lets the ALB initiate connections to the app per configured rules.
- **app-sg → db-sg** lets the app initiate connections to the DB per configured rules.
- These two rules **do not** grant the ALB direct access to the DB.

Additionally, an inbound rule on the target SG **does not automatically create** an outbound rule on the source SG; if the source SG restricts outbound traffic, add the corresponding outbound rule.

### 5.2. Self-Reference

If an SG allows inbound TCP/9000 from **itself**, network interfaces using that SG can initiate TCP/9000 connections to each other under supported network conditions. This is useful for certain clusters requiring internal communication, though it also widens access among nodes sharing that SG.

Distinguish clearly:

- **Self-reference**: allows flows only from ENIs bearing the same SG.
- **Internal CIDR**: allows every address in the specified CIDR range, including resources without that SG if network routing permits.

### 5.3. Referencing Limitations

Do not assume Security Group referencing works across **every** VPC peering, Transit Gateway, cross-account, or NAT/proxy intermediary pattern. Support depends on **rule type, VPC relationship, and connectivity mechanism**. When traffic passes through a middlebox or forwarding mechanism that alters observed source identity, verify whether SG referencing still applies or whether tightly scoped CIDRs are needed.

For complex routing, check the *Security group referencing* documentation and test actual paths before approving the design.

## 6. Reference Design: Internet → ALB → Application → RDS

Suppose an ordering system uses:

- **Application Load Balancer (ALB)** receiving HTTPS from clients.
- **EC2** running an API on TCP/8080 in private subnets.
- **Amazon RDS for PostgreSQL** accepting TCP/5432 in database subnets.
- Application components placed across **multiple AZs** to support high availability when required by the architecture.

~~~mermaid
flowchart TB
    U["Internet / users"] -->|"TCP 443"| ALB["ALB — alb-sg"]
    subgraph VPC["Amazon VPC"]
      subgraph AZA["Availability Zone A"]
        A["EC2 App A — app-sg, TCP 8080"]
      end
      subgraph AZB["Availability Zone B"]
        B["EC2 App B — app-sg, TCP 8080"]
      end
      DB[("Amazon RDS PostgreSQL — db-sg, TCP 5432")]
      ALB -->|"TCP 8080"| A
      ALB -->|"TCP 8080"| B
      A -->|"TCP 5432"| DB
      B -->|"TCP 5432"| DB
    end
~~~

This diagram illustrates the **logical flow**: RDS Multi-AZ, subnets, route tables, interfaces, and actual failover mechanisms must be configured separately. You cannot infer Multi-AZ or resilience solely from placing two instances in two AZs.

### 6.1. Minimum Rule Matrix for Core Flows

| Security Group | Direction | Protocol/Port | Source/Destination | Purpose |
| --- | --- | --- | --- | --- |
| **alb-sg** | Inbound | TCP/443 | 0.0.0.0/0 | Accept HTTPS from IPv4 clients. |
| **alb-sg** | Outbound | TCP/8080 | **app-sg** | ALB initiates connections to targets and performs health checks on the app port when configured that way. |
| **app-sg** | Inbound | TCP/8080 | **alb-sg** | Only the ALB can access the application endpoint on port 8080. |
| **app-sg** | Outbound | TCP/5432 | **db-sg** | Application initiates connections to PostgreSQL. |
| **db-sg** | Inbound | TCP/5432 | **app-sg** | Only authorized app instances can connect to the database. |

**Additional rules as needed:** If the application also calls AWS APIs, S3/STS endpoints, image registries, monitoring systems, DNS, Secrets Manager, or external services, design the corresponding outbound flows and connectivity paths (VPC endpoints, NAT, or other paths). The table above intentionally covers only **the two business flows ALB → app and app → DB**; it is not a complete ruleset for every workload.

If the ALB uses IPv6 and the site expects IPv6 clients, add appropriate IPv6 rules such as **::/0** for the public HTTPS port. The rule **0.0.0.0/0** covers only IPv4.

### 6.2. Tracing a Successful Request

1. Client initiates an HTTPS/443 connection to the ALB. **alb-sg inbound 443** permits the request.
2. ALB initiates a separate connection to the target EC2 on TCP/8080. **alb-sg outbound 8080** and **app-sg inbound 8080** permit it.
3. App needs order data and initiates a connection to RDS TCP/5432. **app-sg outbound 5432** and **db-sg inbound 5432** permit it.
4. RDS returns the result; SGs along the permitted connection path allow the response **statefully**.
5. App returns the response to the ALB, and the ALB returns the HTTPS response to the client over their respective connections.

Prerequisites: the ALB must have a properly configured listener, target group, and health check; EC2 must listen on port 8080; RDS must be running and accepting valid connections; routes/NACLs/DNS/credentials must all align.

### 6.3. Why Not Use a Single SG for the Entire System?

If the ALB, app, and RDS share one overly broad SG, it becomes very hard to prove who is authorized to reach the database. Splitting SGs by **role** ensures that scaling app instances in an Auto Scaling Group does not force constant IP updates in the RDS SG.

Role-based design also simplifies change review: operations teams can immediately see which database tier would be affected by adding a TCP/5432 rule.

### 6.4. Restricting Administrative Ports

Avoid opening inbound TCP/22 or TCP/3389 from **0.0.0.0/0** on production hosts. When administrative access is needed, consider **AWS Systems Manager Session Manager** with appropriate IAM, endpoints, and configuration, or controlled admin access over a corporate network/VPN.

Note: Session Manager only works when the instance/agent, IAM role, connectivity to SSM services, and related prerequisites are configured properly. Simply deleting the SSH rule does not make Session Manager usable automatically.

## 7. How Do Security Groups and Network ACLs Differ?

**Security Groups and NACLs are complementary network control layers** with distinct behaviors:

| Criterion | Security Group | Network ACL (NACL) |
| --- | --- | --- |
| Scope | Supported network interfaces / resources. | Subnets. |
| Rule types | **Allow** only; unmatched flows are implicitly denied. | **Allow** and **Deny**. |
| Statefulness | **Stateful** for tracked flows. | **Stateless**. |
| Rule order | No numeric evaluation order; all Allow rules are merged. | Evaluated by **rule number**, ascending, stopping at the first match. |
| Return direction | Corresponding responses for allowed connections pass without a reverse rule. | Must have explicit matching rules for **both directions** of traffic. |
| Attachment | Attached to interfaces/resources; one interface can have multiple SGs. | Each subnet is associated with one NACL at a time. |
| Source/destination | IPv4/IPv6 CIDRs, SG references, prefix lists per rule/support. | Primarily IPv4/IPv6 CIDRs, protocols, and port ranges. |
| Typical use | Role-based access across ALB/app/DB tiers. | Additional filtering layer at subnet boundaries. |

### 7.1. Example: Inbound HTTPS with a Stateless NACL

A website receives TCP/443 from a client using source port **51524**:

- **Inbound NACL** on the server's subnet must allow requests to destination port **443**.
- **Outbound NACL** on the server's subnet must allow responses to the client's **ephemeral port 51524**, within the designed source/destination scope.
- If a client-side subnet's NACL is also in the same routing environment, matching rules must be evaluated on that side too.

Never conclude that "because SGs are stateful, NACLs will automatically let responses through." **NACLs do not track connection state.** Ephemeral port ranges vary by OS, client, and service; avoid memorizing a single range for all systems without verifying the environment.

### 7.2. Default NACL vs. Custom NACL

Typically, a VPC's **default NACL** contains rules allowing all inbound and outbound traffic; a newly created **custom NACL** denies flows until appropriate rules are added. Always read the actual rules since they may have been customized.

Which NACL applies to a subnet is a **subnet association** property, not an instance-level SG assignment. If an EC2 instance cannot communicate across a subnet, inspect both layers.

## 8. Security Groups Do Not Replace Routing or Other Network Services

### 8.1. Route Tables, Internet Gateways, and NAT

An EC2 instance in a subnet with no route to the Internet cannot directly access the Internet merely because its SG outbound allows `0.0.0.0/0`.

For example:

- A **public subnet** has a route to an Internet Gateway, along with appropriate public addressing and connectivity conditions.
- A **private subnet** can use a NAT Gateway for outbound IPv4 Internet flows or VPC endpoints to reach AWS services without traversing the public Internet.
- Neither an **Internet Gateway** nor a **NAT Gateway** bypasses SGs: network permissions on interfaces/resources must still allow the traffic.

Note endpoint differences:

- **Gateway endpoints** (e.g., S3/DynamoDB where supported) operate via route table entries; they do not attach SGs directly like interface endpoints.
- **Interface endpoints** are deployed via ENIs inside the VPC and have Security Groups that must allow traffic from clients.

For complete access control to AWS services, you may also need **endpoint policies**, IAM/resource policies, and service-specific conditions.

### 8.2. IAM, TLS, and Application Firewalls

Security Groups inspect only network/transport attributes as supported. They do not know whether an API caller is authorized to view an order.

- **IAM** governs AWS API actions by identity and permissions.
- **TLS** encrypts traffic and supports endpoint authentication when properly configured.
- **AWS WAF** adds web request filtering rules for supported resource types.
- **Application authorization** determines which data an end user may read or modify.
- **OS firewalls** inside EC2 (if configured) add host-level filtering independent of SGs.

An HTTPS request allowed by an SG can still receive **401**, **403**, or certificate errors from the application. Those errors do not automatically mean the SG is wrong.

### 8.3. Compute Services Beyond EC2

Not every AWS service uses Security Groups identically. For example, EC2/ENIs, RDS, ALBs, interface VPC endpoints, and workloads attached to a VPC via ENIs can use SGs per service documentation. For Lambda, configuring an SG only applies in the context of the function's **VPC connectivity**; do not assume that SG directly opens or closes permission to call the Lambda invoke endpoint.

When designing ECS, EKS, or serverless architectures, know which resources actually attach ENIs/SGs and each service's specific traffic behavior. Workload API permissions remain governed by IAM and related policies.

## 9. Secure Deployment Practices

### 9.1. Restrict Inbound to Truly Necessary Sources

| Need | Appropriate Rule | Avoid |
| --- | --- | --- |
| Public website | TCP/443 from expected Internet sources to the ALB's SG. | Opening database ports publicly just for testing convenience. |
| App behind ALB | TCP/app port from the ALB's SG. | Inbound `0.0.0.0/0` to app EC2 instances in private subnets. |
| Database | TCP/DB port from authorized workload SGs. | TCP/5432 or 3306 from all IPv4/IPv6 addresses. |
| EC2 administration | Prefer managed admin channels; if SSH is required, restrict to admin IPs/networks. | Public SSH/RDP with unrestricted source ranges. |
| Intra-cluster communication | SG self-reference or tightly scoped target group reference. | Opening the entire VPC CIDR to every service unnecessarily. |

Even if a server has no public IP, overly broad inbound rules create risks from inside the VPC, connected networks over VPN/peering/Transit Gateway, or compromised workloads.

### 9.2. Tighten Outbound with Control

An "Allow all" outbound rule is convenient for demos but permits unintended outbound connectivity. When aiming for least-privilege egress:

1. List genuinely required destinations: databases, HTTPS APIs, S3 endpoints, patching/monitoring services, DNS, and supporting components.
2. Specify destinations using **SG references**, **prefix lists**, or properly maintained CIDRs.
3. Ensure routing, NACLs, endpoint policies, and IAM are compatible.
4. Test application functionality, health checks, instance reboots, dependency updates, and recovery scenarios before applying to production.

**Note:** External service IP addresses can change. Hardcoding a SaaS endpoint's static IP into an SG often breaks connectivity later when the provider rotates IPs. Choose an egress management solution suited to your domain/range requirements.

### 9.3. Separate Environments and Governance Responsibilities

- Use separate SGs for **development**, **staging**, and **production** per account/VPC model.
- Manage rules with Infrastructure as Code (IaC) and controlled change reviews where appropriate.
- Set clear names, **descriptions**, and tags; document business justification in rule descriptions.
- Restrict who holds **ec2:AuthorizeSecurityGroupIngress**, **ec2:AuthorizeSecurityGroupEgress**, or SG modification permissions; audit changes via CloudTrail.
- Periodically review unused SGs, obsolete rules, and SGs attached to unexpected resources.
- Audit IPv4 and IPv6 independently, especially in dual-stack VPCs or ALBs.

### 9.4. Stateful Behavior Does Not Eliminate Monitoring Needs

**VPC Flow Logs** capture traffic metadata within configured scopes, aiding ACCEPT/REJECT checks and path analysis; however, they do not decrypt payloads, do not capture every packet like a full packet capture tool, and depend on scope/timing/log format.

AWS **Reachability Analyzer** helps analyze reachability across configured network settings between supported endpoints. Correlate results with live application behavior, service status, and functional tests.

Enabling logs, storing them in CloudWatch Logs/S3, and analyzing them incurs costs; define log scopes and retention periods according to investigation, compliance, and budget needs.

## 10. Hands-On with AWS CLI (Read-Only)

The commands below inspect configurations; they **do not create, modify, or delete rules**. They require valid AWS CLI credentials, sufficient IAM read permissions, and replacing illustrative IDs with real IDs in an authorized environment.

### 10.1. Identify the Current Principal

~~~bash
aws sts get-caller-identity
~~~

If subsequent commands return **AccessDenied**, first verify the AWS account, Region, and active IAM role/user. IAM may restrict configuration read access.

### 10.2. Inspect a Security Group's Configuration

~~~bash
aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --region ap-southeast-1
~~~

In the output, inspect:

- **VpcId:** which VPC the SG belongs to.
- **IpPermissions:** current inbound rules.
- **IpPermissionsEgress:** current outbound rules.
- CIDR blocks/SG references in each rule and the associated protocols/ports.

Do not rely solely on SG names; verify exact IDs and VPCs to avoid mixing up environments.

### 10.3. Inspect Rules in the Newer Rule Format

~~~bash
aws ec2 describe-security-group-rules \
  --filters Name=group-id,Values=sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --output json
~~~

Each rule can include attributes such as **SecurityGroupRuleId**, **IsEgress**, **IpProtocol**, **FromPort**, **ToPort**, **CidrIpv4**, **CidrIpv6**, or **ReferencedGroupInfo**. **IsEgress = true** means outbound; **false** means inbound.

### 10.4. Find ENIs Attached to a Security Group

~~~bash
aws ec2 describe-network-interfaces \
  --filters Name=group-id,Values=sg-0123456789abcdef0 \
  --region ap-southeast-1 \
  --output json
~~~

Inspect **NetworkInterfaceId**, **SubnetId**, **PrivateIpAddress**, **Groups**, **Description**, and attachment details to see which resource interfaces the SG protects. Some managed services use AWS-created ENIs; cross-reference related resource names/IDs.

### 10.5. Inspect SGs on EC2, ALB, and RDS

~~~bash
# EC2: inspect instance, subnet, and security groups attached to the instance.
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --region ap-southeast-1 \
  --query "Reservations[].Instances[].{Id:InstanceId,Subnet:SubnetId,SG:SecurityGroups}"

# ALB: inspect scheme, VPC, and Security Groups.
aws elbv2 describe-load-balancers \
  --names example-public-alb \
  --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,VPC:VpcId,SG:SecurityGroups}"

# RDS: inspect public access and applied VPC SGs.
aws rds describe-db-instances \
  --db-instance-identifier example-orders-db \
  --region ap-southeast-1 \
  --query "DBInstances[].{Name:DBInstanceIdentifier,Public:PubliclyAccessible,SG:VpcSecurityGroups}"
~~~

An instance can have multiple ENIs, and SGs attached to each ENI must be checked along the relevant flow, so for complex incidents inspect **describe-network-interfaces** rather than only the instance-level SG list.

### 10.6. Inspect Related Network Layers

~~~bash
# Inspect NACL attached to an example subnet.
aws ec2 describe-network-acls \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1

# Inspect route table explicitly associated with the subnet (if any).
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --region ap-southeast-1
~~~

**Important:** If no **explicit** route table association is found for a subnet, it may be using the VPC's **main route table**. Check the main association instead of concluding the subnet has no routes.

### 10.7. Interpreting Output by Scenario

- If the app **cannot reach the DB** on 5432, check **app-sg outbound 5432**, **db-sg inbound 5432**, DB IP/DNS, NACLs/routes, and DB listener status.
- If the ALB reports **unhealthy** targets, inspect the health check port, app listener, **alb-sg outbound**, and **app-sg inbound**; also verify HTTP/HTTPS status codes, health check path, and application behavior.
- If an EC2 instance in a private subnet cannot reach Internet HTTPS, check **outbound SG**, routes to NAT/VPC endpoints, and other network layers. Never infer guaranteed Internet access solely from an SG Allow rule.
- If AWS APIs return **AccessDenied**, inspect IAM/resource policies; this may be an API authorization error rather than a network timeout.
- If errors appear after an SG change, verify the rule took effect, the ENI has the right SG attached, existing connection states, and changes in other network layers.

## 11. Troubleshooting with a Decision Tree

Start from the **exact flow**: source, destination, protocol, port, Region/VPC, and connection initiation direction.

~~~mermaid
flowchart TD
    A["Connection fails"] --> B{"Are source/destination/protocol/port correct?"}
    B -->|"No"| B1["Verify DNS, IP, listener, port, and target"]
    B -->|"Yes"| C{"Does source allow new connections in outbound SG?"}
    C -->|"No"| C1["Fix outbound scope as required"]
    C -->|"Yes"| D{"Does destination allow inbound SG?"}
    D -->|"No"| D1["Fix inbound scope for valid sources"]
    D -->|"Yes"| E{"Do routes and NACLs allow both directions?"}
    E -->|"No"| E1["Inspect routes, subnets, NACLs, gateways/endpoints"]
    E -->|"Yes"| F["Inspect OS firewall, app, TLS, IAM, database auth, health checks, and logs"]
~~~

**The decision tree is a general diagnostic workflow.** Specialized services or networking modes may impose extra conditions. A single failure can also stem from multiple concurrent causes.

### 11.1. Scenario: TCP Timeout to RDS

**Symptom:** An EC2 instance in the VPC cannot connect to PostgreSQL on port 5432, even though the database is running.

Check in order:

1. Are you calling the right **DB endpoint**? Does the DNS endpoint resolve to the current IP, especially after failover?
2. Does the client EC2 have an outbound rule for TCP/5432 to RDS?
3. Does RDS have an inbound rule for TCP/5432 from **app-sg** or an authorized source?
4. Are both client and DB in subnets/VPCs with valid routes? Do NACLs permit both request and response directions?
5. Is the database listening, healthy, and free of connection limits or DNS/OS issues?
6. Once TCP connects but login fails, focus on **database credentials**, TLS, and DB authentication mechanisms.

Do not open 5432 to **0.0.0.0/0** as a "quick fix."

### 11.2. Scenario: EC2 Cannot Update Packages

**Symptom:** An EC2 instance in a private subnet has appropriate inbound rules yet fails to make HTTPS requests to a package repository.

Explanation: inbound SGs do not directly govern connections **initiated by the EC2 instance**. Check outbound TCP/443, DNS, NACLs, and routing through an appropriate NAT/proxy/endpoint. An EC2 instance with no public IP and no NAT/egress path cannot reach an Internet repository merely with an outbound Allow rule.

### 11.3. Scenario: ALB Receives HTTPS but Returns 502/503

Clients reaching the ALB does not guarantee the ALB can reach its targets. Cross-check:

- Which port the ALB listener and target group target.
- Whether **alb-sg outbound** permits the target/health check port.
- Whether **app-sg inbound** permits traffic from the ALB.
- Whether EC2/the app is listening on the expected port/protocol and the health check endpoint returns the expected response.
- Target registration and target health status.

502/503 errors can originate from the ALB, target, or application layers; **do not** automatically blame SGs for every error.

## 12. Common Misconceptions and Misconfigurations

| Misconception | Accurate Explanation |
| --- | --- |
| "Security Groups are stateless like NACLs." | Security Groups typically handle return flows statefully; NACLs are stateless. |
| "Opening inbound 443 requires opening outbound ephemeral ports to reply over HTTPS." | Return traffic for an SG-permitted connection is typically allowed statefully; no separate outbound rule is needed for the reply. |
| "With no inbound rules, an instance cannot receive any packets." | Return packets for allowed outbound connections can still arrive via stateful behavior. |
| "Attaching two SGs means the stricter one wins." | Allow rules are merged; SGs have no Deny rules to override Allow rules from another SG. |
| "Opening 10.0.0.0/8 is private, so it is completely safe." | Private ranges may span untrusted systems or connected networks; restrict by role. |
| "Using an SG reference means the client needs no outbound rule." | An inbound Allow on the target SG does not create an outbound Allow on the source SG. |
| "Having a route guarantees connectivity." | SGs, NACLs, gateways, listeners, and application layers can all block traffic. |
| "Security Groups can filter the URL `/admin`." | SGs do not inspect HTTP paths; use the application layer/WAF/auth appropriately. |
| "0.0.0.0/0 also allows all IPv6 traffic." | 0.0.0.0/0 covers IPv4 only; IPv6 uses IPv6 CIDRs such as `::/0` where applicable. |
| "Changing an SG immediately terminates all existing connections." | Connection tracking and exceptions mean existing session behavior must be verified. |
| "RDS is private, so opening inbound 0.0.0.0/0 is harmless." | Broadening permissions still increases risk from any connected network that can route to the DB. |

## 13. Design and Evaluation Exercises

### Exercise 1 — Evaluating Public Web Rules

An EC2 instance runs both nginx and a database, attached to one SG with inbound:

- TCP/22 from **0.0.0.0/0**.
- TCP/443 from **0.0.0.0/0**.
- TCP/5432 from **0.0.0.0/0**.

**Task:** Identify three risks and propose an improved architecture.

**Sample solution:** Public HTTPS may be valid if this is a public web endpoint with proper application-tier protection, but exposing SSH and PostgreSQL to all IPv4 addresses is high risk. Separate web and database into appropriate components/SGs, consider an ALB, place app/DB in private subnets, use role-based SG inbound rules, and use managed administrative channels instead of public SSH. Restrict outbound access and audit routes/NACLs.

### Exercise 2 — Blocked App Outbound

A system has:

- **app-sg inbound 8080 from alb-sg**.
- **db-sg inbound 5432 from app-sg**.
- **app-sg outbound allowing only TCP/443 to a specific endpoint**.

Question: Can the app open a new connection to RDS on TCP/5432?

**Answer:** No—based on the stated rules, **app-sg lacks outbound TCP/5432** to the DB. **db-sg inbound 5432** is necessary but insufficient. You must add the corresponding outbound rule and verify other network/DB prerequisites.

### Exercise 3 — Stateful Behavior and Return Traffic

An EC2 instance runs a web server receiving TCP/443 from a client with source port 51620; the EC2 instance has inbound 443 from the client IP and **no outbound rules**. Can the server reply?

**Answer:** Under standard stateful behavior, the corresponding response for the permitted inbound connection can pass back through the SG even without an explicit outbound rule. However, NACLs/routes, the listener, and remaining layers must still permit it. The server also **cannot** initiate a new outbound connection just because inbound 443 is open.

### Exercise 4 — Unstable Database Connectivity After Failover

RDS Multi-AZ fails over; the application hardcoded the old DB IP address in its configuration and suddenly times out.

**Answer:** The SG may not be the cause. Connecting to the old IP after failover fails unless you use the DNS endpoint and proper retry/reconnect logic. Check the endpoint, DNS caching configuration, application connection handling, and database health first, then cross-check SGs/NACLs/routes and logs.

## 14. Self-Check Questions

**Question 1.** At what level are Security Groups primarily applied?  
**Answer:** Attached to network interfaces/supported resources inside a VPC, not directly to subnets like NACLs.

**Question 2.** Do Security Groups support a Deny rule to override an Allow rule?  
**Answer:** No. SGs have Allow rules, and traffic not matching an Allow rule is implicitly denied.

**Question 3.** The app has outbound TCP/5432 to db-sg; the DB has inbound TCP/5432 from app-sg. Do you need to open inbound ephemeral ports on app-sg just to receive responses?  
**Answer:** Usually no. SGs are stateful for responses to permitted connections; however, NACLs must be evaluated in both directions.

**Question 4.** If an EC2 instance has two SGs attached—one allowing inbound 22 and the other allowing 443—what is the effective permission?  
**Answer:** The union of Allow rules from both SGs. There is no SG priority order that restricts another SG's permissions.

**Question 5.** Why is **db-sg inbound 5432 source = app-sg** generally more flexible than listing individual EC2 private IPs?  
**Answer:** SG referencing grants permissions by network interface role, making it seamless when workloads scale or replace instances. Ensure the connectivity/referencing mode is supported by AWS.

**Question 6.** Can `0.0.0.0/0` be used for IPv6?  
**Answer:** No. IPv6 uses its own syntax, such as `::/0`; review IPv6 rules separately.

**Question 7.** If an EC2 instance has outbound Allow to all destinations but no route to the Internet, can it access the Internet?  
**Answer:** No. SGs are only one condition; routes, gateways/NAT/endpoints, and other network settings must also align.

**Question 8.** Why do NACLs need return-direction rules even though SGs are stateful?  
**Answer:** NACLs are stateless, so they evaluate request and response directions independently.

**Question 9.** If ALB-to-app fails, which two SG rules should be checked at a minimum?  
**Answer:** **alb-sg outbound** to the app port and **app-sg inbound** from alb-sg on that port, followed by listener/target configuration, routes, NACLs, and the application itself.

**Question 10.** How do VPC Flow Logs help during investigations?  
**Answer:** They provide traffic flow metadata within configured scopes to help diagnose ACCEPT/REJECT verdicts and connection patterns; they do not replace application testing or inspecting all network layers.

## 15. Summary

Security Groups are one of the primary tools for **network segmentation and restricting connectivity** between AWS components. Four core principles to remember:

1. **Allow-only and implicit deny:** only flows matched by an appropriate rule can be initiated in that direction; multiple SGs attached to an interface combine their Allow permissions.
2. **Stateful:** return traffic for a permitted connection passes back through the SG without an independent reverse rule. **NACLs remain stateless**.
3. **Role-based design:** define groups such as ALB, app, and DB; prefer appropriate SG referencing, restrict admin/database ports, and control outbound access based on actual needs.
4. **Defense in depth:** SGs must work alongside VPC routes, NACLs, IAM, TLS, logging, cross-AZ resilience, and operational policies. Opening a port does not mean an application is secure or guaranteed to connect.

When deploying secure, monitored, and resilient systems on AWS, explicitly map out each **initiated flow** (source → destination, protocol/port), verify rules on **both ends**, confirm return traffic paths, test routes/NACLs, and monitor changes. This reduces connectivity incidents, shrinks attack surface, and avoids unnecessary troubleshooting and remediation costs.

### Official AWS References

- [Security groups for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — Security Group concepts and usage.
- [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html) — inbound/outbound, sources/destinations, SG referencing.
- [Security group connection tracking](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html) — stateful behavior and connection tracking special cases.
- [Control subnet traffic with Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — comparing the stateless subnet layer with SGs.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — collecting traffic metadata for monitoring and investigation.
