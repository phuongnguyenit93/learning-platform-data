# AWS Network Firewall and VPC Traffic Filtering

## Learning Objectives

After this lesson, you can:

- Explain the role of AWS Network Firewall in Amazon VPC network security architectures.
- Distinguish between firewall, firewall policy, rule group, firewall endpoint, and VPC endpoint association.
- Compare Classic policies with Next Generation policies and select the appropriate model.
- Explain stateless, stateful, firewall engine, and IPS engine processing flows.
- Author filtering rules by IP address, port, protocol, connection state, SNI, and HTTP host.
- Design route tables to steer traffic through the firewall while maintaining symmetric forward and return paths.
- Choose distributed, centralized, or combined deployment models in multi-VPC environments.
- Design TLS inspection, logging, monitoring, and cost controls.
- Combine Network Firewall with Security Groups, Network ACLs, Route 53 Resolver DNS Firewall, AWS WAF, Transit Gateway, Cloud WAN, and AWS Firewall Manager.
- Run test deployments, verify outcomes, troubleshoot routing issues, and operate the firewall in production.

## 1. The Problem: Controlling Traffic Between VPCs and the Internet

An application running in a VPC typically exchanges data with many destinations: Internet users, partner APIs, AWS services, on-premises servers, and workloads in other VPCs. Security groups control connections at the network interface level, while Network ACLs filter packets at subnet boundaries. When an organization requires deeper inspection by protocol, domain, intrusion signatures, or application content, those two layers alone may fall short.

For example, a company wants to:

- Allow production servers to access only approved external domains.
- Block connections to malicious IP addresses, ports, or domains.
- Detect and prevent certain application-layer attack patterns.
- Inspect TLS traffic per security policy.
- Log allowed or blocked traffic for incident investigation.
- Enforce a consistent baseline across multiple VPCs and AWS accounts.

AWS Network Firewall is a managed network firewall service for Amazon VPC. It provides per-Availability Zone firewall endpoints and applies firewall policies to inspect traffic routed through those endpoints. Stateful inspection uses a Suricata-compatible engine, enabling flow tracking and detection across many application-layer protocols.

Network Firewall does not automatically see all VPC traffic. You must configure route tables to send the right traffic flows through the firewall endpoints. If routes bypass the endpoint, the policy cannot inspect that traffic.

Within the AWS ecosystem, Network Firewall works alongside:

- **Amazon VPC** to define subnets, route tables, and traffic paths.
- **Security Groups and Network ACLs** to control access at the network interface and subnet levels.
- **AWS Transit Gateway or AWS Cloud WAN** to centralize traffic across multiple VPCs.
- **Amazon Route 53 Resolver DNS Firewall** to protect DNS query paths.
- **AWS WAF** to inspect HTTP requests at application termination points such as CloudFront, Application Load Balancer, and API Gateway.
- **AWS Firewall Manager** to manage policies across multiple accounts in AWS Organizations.
- **Amazon CloudWatch, Amazon S3, and Amazon Data Firehose** to collect, store, and stream logs.

## 2. Where Does Network Firewall Protect?

Network Firewall operates on network paths routed through a firewall endpoint. It can inspect traffic across multiple layers:

| Layer | Data Available for Filtering |
|---|---|
| L3 - Network | IPv4/IPv6, source and destination addresses |
| L4 - Transport | TCP, UDP, ICMP, ports, and flow state |
| L7 - Application | Protocol detection, TLS SNI, HTTP host/headers, and supported application attributes |
| TLS inspection | Decrypts TLS traffic within configured scope, inspects payload, then re-encrypts |

The stateful engine can identify application protocols even when applications run on non-standard ports. For example, TLS may run on a port other than 443 and HTTP may run on a port other than 80. Detection capability depends on protocol parsers, flow context, and supported traffic types.

Network Firewall protects traffic passing through its endpoints. A subnet is not automatically protected merely because a firewall exists in the VPC. Inspect route tables for source subnets, destination subnets, and intermediate components to confirm the actual traffic path.

### Network Firewall and Other Control Layers

| Service | Primary Scope | Example |
|---|---|---|
| Security Groups | Stateful access control attached to ENIs | Allow app servers to receive TCP/443 only from the ALB |
| Network ACLs | Stateless packet filtering at subnets | Block a known CIDR at the subnet boundary |
| AWS Network Firewall | Stateful network inspection on traffic routed through endpoints | Filter domains, protocols, and intrusion signatures |
| Route 53 Resolver DNS Firewall | Filter DNS queries via Route 53 Resolver | Block resolution of malicious domains |
| AWS WAF | HTTP/HTTPS request inspection at web endpoints | Block SQL injection, bots, or anomalous requests |
| AWS Shield | Protection against DDoS attacks | Protect public-facing services |

Network Firewall does not replace security groups. Security groups remain the resource-level control even when a traffic flow does not traverse a firewall endpoint.

AWS WAF also serves a distinct goal. WAF understands HTTP request structure and enforces rules at the web application layer. Network Firewall inspects traffic at the network and transport layers and can add stateful application protocol inspection. A public web architecture may use both WAF and Network Firewall.

## 3. Components of AWS Network Firewall

A deployment typically includes four main components:

| Component | Role |
|---|---|
| Firewall | Links an inspection policy to a VPC or Transit Gateway attachment and defines AZs with endpoints |
| Firewall policy | Defines rule groups, evaluation order, and default behavior |
| Rule group | Reusable collection of rules |
| Firewall endpoint | Traffic processing point inside a subnet and Availability Zone |

A firewall uses one firewall policy at a time. A policy can be shared across multiple firewalls. Rule groups can be referenced by multiple policies and shared via AWS Resource Access Manager when appropriate.

For a VPC-attached firewall, each Availability Zone needs a dedicated firewall subnet to host the endpoint. An endpoint protects other subnets in the VPC, but it does not protect the subnet in which the endpoint itself resides. Do not place workloads or application resources inside the firewall subnet.

Each endpoint subnet requires at least one available IP address. When creating a firewall, select one subnet per AZ where you want to deploy an endpoint; additional VPCs using VPC endpoint associations can only place endpoints in AZs that already have an endpoint in the primary VPC.

Beyond primary endpoints, VPC endpoint associations can create additional endpoints to extend protection coverage to other VPCs or add endpoints within a VPC. These endpoints share the parent firewall's policy and configuration.

~~~mermaid
flowchart TD
    A["Workload subnet"] --> B["Route table"]
    B --> C["Firewall endpoint in AZ"]
    C --> D["Firewall policy"]
    D --> E["Rule groups"]
    E --> F["Allow / Drop / Reject / Alert"]
    F --> G["Next network hop"]
    H["CloudWatch / S3 / Firehose"] <-->|"Logs"| D
~~~

## 4. Two Firewall Policy Types: Classic and Next Generation

AWS Network Firewall currently offers two firewall policy types. A firewall attaches only one policy type at a time.

| Criterion | Classic Policy | Next Generation Policy |
|---|---|---|
| Status | Fully supported | Recommended by AWS for new firewalls |
| Inspection engines | Stateless engine and stateful engine | Firewall engine and IPS engine |
| Rule groups | Stateless and stateful | Firewall and IPS |
| Access control default | Depends on stateless/stateful default actions | Firewall engine Drop by default |
| IPS default | Stateful engine uses action order or strict order | IPS engine Pass by default |
| Rule ordering | Stateless by priority; stateful by Action Order or Strict Order | Firewall section by priority; IPS section by action order |
| Stateless rule groups | Yes | No |
| Embedded rules | Depends on Classic configuration | Supported in each section |
| Use case | Maintaining existing deployments | New baselines, separating access control and threat prevention |

Next Generation policies are the preferred choice for new deployments. Classic policies remain suitable when operating legacy setups or requiring compatibility with existing rule groups. You cannot attach both Classic and Next Generation policies to the same firewall simultaneously.

Next Generation policies require the firewall to run in source-preserving mode. You cannot attach this policy type to a firewall running in proxy mode or no-source-preservation mode.

### 4.1 Next Generation Policy

A Next Generation policy splits processing into two engines:

1. **Firewall engine:** access control. This engine is Drop by default; connections are accepted only when passing required hooks and rules.
2. **IPS engine:** intrusion inspection using Suricata-compatible rules. This engine is Pass by default and blocks or rejects traffic matching drop/reject rules.

Processing flow:

~~~mermaid
flowchart TD
    A["Incoming packet / connection"] --> B["Firewall engine"]
    B --> C{"Accepted by firewall rules?"}
    C -->|No| D["Firewall default action"]
    C -->|Yes| E{"Bypass IPS?"}
    E -->|Yes| F["Forward to destination"]
    E -->|No| G["IPS engine"]
    G --> H{"Threat rule matches?"}
    H -->|Drop / Reject| I["Block or reject"]
    H -->|No match / Pass| F
~~~

The Firewall section contains rule groups or embedded rules for access control. Each entry in the section has a priority; lower numbers are evaluated first. The IPS section contains IPS rule groups or embedded rules. The IPS engine uses action order: pass, drop, reject, then alert.

You can enable **Monitor mode** to observe policy behavior before switching to **Enforce mode**. In monitor mode, operators assess which connections would be affected and tune allow rules before enforcing real traffic blocks.

Next Generation policies can integrate AWS managed rule groups and Active Threat Defense. Managed rule groups supplement threat signatures maintained by AWS or partners. Review descriptions, update sources, capacity, and impact before adding them to production.

### 4.2 Classic Policy

A Classic policy uses two engines sequentially:

1. The stateless engine inspects each packet first.
2. The stateful engine inspects packets in flow context if stateless rules or the default action forward packets to the stateful engine.

The stateless engine suits simple rules based on IP, protocol, port, and packet attributes. The stateful engine uses Suricata-compatible rules to track flows, detect protocols, and inspect application attributes.

In Classic policies, stateful rule evaluation has two modes:

- **Strict order:** rules are evaluated in the exact order you define; the first matching rule determines the outcome.
- **Action order:** the engine groups rules by action—typically pass first, then drop, reject, and alert. Because pass can evaluate before drop, the order written in the file is not necessarily the execution order.

Strict order provides clearer control over precedence. When using Strict order, design stateful default actions intentionally so unmatched traffic is neither silently passed nor silently dropped without logging.

### 4.3 Choosing a Policy Type

- Choose Next Generation for new firewalls unless compatibility constraints prevent it.
- Keep Classic if existing policies are already tested and switching requires a separate migration plan.
- You cannot switch policy types simply by changing one config field. The two policy types use distinct resource types, rule groups, and APIs.
- During migration, build the new policy, verify rule coverage, test in a non-production environment, then switch the firewall to the new policy under a change plan.

## 5. Rule Groups and Authoring Rules

A rule group is a set of traffic matching conditions and actions to execute. Rule groups can be reused across multiple firewall policies.

### 5.1 Rule Groups in Classic Policies

Classic policies support:

- **Stateless rule groups:** filter packets by headers and network attributes.
- **Stateful rule groups:** filter flows using standard stateful rules, domain lists, or Suricata-compatible rule strings.

Stateless actions typically include Pass, Drop, Forward to stateful rule groups, and custom actions. The stateless engine lacks full flow context. When application protocol detection, detailed logging, or reject actions are needed, use the stateful engine.

### 5.2 Rule Groups in Next Generation Policies

Next Generation policies support:

- **Firewall rule groups:** define access control using the visual rule builder, text rule builder, or domain lists.
- **IPS rule groups:** define threat detection/prevention using Suricata-compatible rule strings.
- **Embedded rules:** write rules directly inside a policy section without creating a separate rule group resource.

Referenced rule groups work best when reusing and sharing across policies. Embedded rules suit rules relevant to only a single policy that do not need separate fixed capacity management.

### 5.3 Stateful Suricata Rules

A Suricata rule typically has the structure:

~~~text
action protocol source source_port direction destination destination_port (options)
~~~

A sample rule blocking TLS to a malicious domain based on SNI:

~~~text
drop tls $HOME_NET any -> $EXTERNAL_NET any (ssl_state:client_hello; tls.sni; content:"malware.example"; startswith; nocase; endswith; msg:"Block prohibited TLS domain"; flow:to_server; sid:2001001; rev:1;)
~~~

Meaning:

- **drop:** blocks traffic matching the rule.
- **tls:** applies to the TLS protocol.
- **$HOME_NET:** internal network defined in the policy.
- **$EXTERNAL_NET:** external network.
- **tls.sni:** inspects the Server Name Indication in the TLS Client Hello.
- **content:** domain string to detect.
- **flow:to_server:** restricts direction from client to server.
- **sid:** unique rule ID within the rule set context.
- **rev:** rule revision.

This is an illustrative example. Verify AWS Network Firewall–supported Suricata syntax, rule ordering, and behavior on live traffic before use.

### 5.4 Domain List Rules

A domain list rule group can define an allow list or deny list. Common target types include:

| Target Type | Domain Source | Conditions |
|---|---|---|
| `TLS_SNI` | Domain name in TLS Client Hello | Client must send observable SNI |
| `HTTP_HOST` | Host in HTTP request | For encrypted HTTPS, TLS inspection is required to read HTTP host |
| `AWS_ROUTE_53_RESOLVED_DOMAIN` | Domain resolved by Route 53 Resolver | Traffic must traverse supported DNS Resolver paths with proper validation setup |

Domain names can be exact names or wildcards per domain list syntax. For example, `.example.com` can match `example.com` and its subdomains. Test both the apex domain and subdomains to verify match scope.

Domain lists based on SNI/HTTP host do not mean Network Firewall reads the full TLS payload. Without TLS inspection enabled, the firewall can still see SNI in the Client Hello, while application payloads inside TLS remain encrypted.

### 5.5 Rule Evaluation and Default Actions

A policy must answer three questions:

1. Which rule is evaluated first?
2. When no rule matches, how is traffic handled?
3. Must allowed traffic continue through the IPS engine?

With Next Generation policies, the firewall engine defaults to Drop. You must author rules for permitted connections. The IPS engine evaluates threat rules after the firewall engine accepts, unless a rule specifies bypassing IPS inspection.

With Classic policies, the stateless default action can be Forward to stateful rule groups, Pass, or Drop. Stateful default actions apply to packets matching no stateful rules in Strict order. Never leave defaults ambiguous, or traffic may pass without intended inspection.

## 6. Network Variables and HOME_NET Scope

Suricata uses variables such as **HOME_NET** and **EXTERNAL_NET** to keep rules readable.

By default, `HOME_NET` is often derived from the CIDR of the VPC hosting the firewall. In a centralized inspection architecture, traffic can arrive from many spoke VPCs. If `HOME_NET` contains only the inspection VPC CIDR, rules may fail to recognize traffic originating from spokes.

For example, an organization has:

- Inspection VPC: **10.0.0.0/16**
- Production VPC: **10.10.0.0/16**
- Development VPC: **10.20.0.0/16**

To inspect traffic for both spoke VPCs, configure policy variables so `HOME_NET` includes all protected CIDRs. Define variables at the policy level when sharing across rule groups; avoid overriding `HOME_NET` individually inside each rule group, as that leads to inconsistent behavior.

For east-west inspection, clearly define which source and destination networks are internal. A rule written for egress traffic may fail to match properly if flow direction or `HOME_NET` is misconfigured.

## 7. Route Tables Determine Whether Traffic Traverses the Firewall

After creating a firewall, you must insert the firewall endpoint into the traffic path. Network Firewall does not automatically alter VPC route tables to force all traffic through its endpoints.

Suppose a workload subnet currently has routes:

| Destination | Current Target |
|---|---|
| **10.0.0.0/16** | local |
| **0.0.0.0/0** | Internet Gateway |

To inspect egress traffic, the workload subnet's route table must send Internet-bound traffic to the firewall endpoint. The firewall subnet's route table then forwards traffic to the Internet Gateway or NAT gateway depending on architecture.

For inbound inspection via an Internet Gateway, you must also update the Internet Gateway's edge-associated route table so traffic entering the workload subnet passes through the firewall endpoint. If you only edit the outbound path, inbound traffic can bypass the firewall.

### 7.1 Egress Flow via Internet Gateway

~~~mermaid
flowchart LR
    A["EC2 in workload subnet"] --> B["Workload route table"]
    B --> C["Firewall endpoint"]
    C --> D["Firewall subnet route table"]
    D --> E["Internet Gateway"]
    E --> F["Internet"]
    F --> E
    E --> G["IGW edge route table"]
    G --> C
    C --> H["Workload subnet"]
~~~

Logical steps:

1. Workload route table sends **0.0.0.0/0** to the firewall endpoint in the same AZ.
2. The firewall endpoint applies the policy.
3. The firewall subnet route table forwards allowed traffic to the Internet Gateway.
4. For return traffic, the Internet Gateway's route table sends traffic back to the firewall endpoint.
5. The firewall endpoint forwards return traffic to the workload subnet.

If using a NAT Gateway for private subnets, place the firewall in the path before NAT per the appropriate egress design so the firewall sees original private source addresses. Inspect route tables for workload subnets, firewall subnets, NAT subnets, and the Internet Gateway.

### 7.2 Inbound Inspection

For traffic from the Internet into a public subnet:

1. The Internet Gateway receives traffic.
2. The Internet Gateway's edge-associated route table routes destination traffic to the firewall endpoint.
3. The firewall inspects and allows or blocks.
4. The firewall subnet route table routes traffic to the workload subnet.
5. Response traffic returns through the firewall endpoint before exiting via the Internet Gateway.

Do not inspect only the workload subnet route table. Inbound routing typically requires the Internet Gateway's edge-associated route table.

### 7.3 Inter-Subnet and East-West Traffic

To inspect traffic between subnets, route inter-subnet traffic through the firewall endpoint. Inspect source subnet, destination subnet, and return-path route tables. Intra-subnet traffic does not traverse the firewall endpoint via standard route tables.

VPC peering traffic is also not automatically routed through firewall endpoints. When inspection between VPCs is required, design through Transit Gateway or a routing model supporting service insertion rather than assuming VPC peering traverses the firewall.

## 8. Symmetric Routing and Availability Zones

Because AWS Network Firewall uses stateful inspection, it must observe both requests and responses for the same flow. Requests and responses must traverse the same firewall endpoint. If outbound traffic passes through an endpoint in AZ-A while return traffic passes through an endpoint in AZ-B, the stateful engine may lack complete flow context to inspect accurately.

This is asymmetric routing.

Key principles:

- Deploy a firewall endpoint in every AZ containing workloads to protect.
- Route workloads in an AZ to the matching endpoint in the same AZ.
- Ensure both forward and return paths traverse the same endpoint.
- Avoid route designs that allow response traffic to bypass the firewall.
- When using Transit Gateway with an inspection VPC, enable appliance mode on the inspection VPC attachment.
- When using a native Transit Gateway Network Firewall attachment, AWS manages appliance mode automatically for that model.

Each endpoint deploys per AZ and scales independently. Maximum bandwidth is 100 Gbps for traffic traversing a firewall's endpoints in a single AZ; multiple endpoint associations in that AZ share that limit. Check quotas and actual load during capacity design.

### 8.1 Verifying Symmetric Routing

You can use:

- VPC Reachability Analyzer to verify intended paths.
- Network Firewall flow logs to correlate both directions of traffic.
- Temporary alert rules to confirm the stateful engine sees established flows.
- The CloudWatch metric **StreamExceptionPolicyPackets** to monitor stream exceptions.
- VPC Flow Logs to inspect ENI and subnet traffic.

If flow logs show only request traffic with no responses, responses may be bypassing the firewall or being blocked by security groups/Network ACLs.

## 9. Deployment Architectures: Distributed, Centralized, and Combined

AWS Network Firewall supports multiple deployment models. Choose based on VPC count, account count, traffic volume, isolation needs, routing, and cost.

### 9.1 Distributed Deployment

Each VPC needing inspection has its own firewall and either its own policy or a reused policy.

Best suited for environments with few VPCs, workloads with distinct security requirements, or avoiding Transit Gateway processing costs.

Advantages:

- Traffic is inspected close to workloads.
- Routing is straightforward within a single VPC.
- Blast radius can be isolated per application or account.
- No need to funnel all traffic through a central hub.

Trade-offs:

- More firewall endpoints and hourly charges.
- Policies must be managed across multiple VPCs.
- Rule synchronization and logging grow more complex as VPC count increases.

### 9.2 Centralized Inspection VPC with Transit Gateway

An inspection VPC hosts Network Firewall endpoints. Multiple spoke VPCs connect to Transit Gateway. Transit Gateway route tables steer inspected traffic through the inspection VPC.

~~~mermaid
flowchart TD
    A["Spoke VPC A"] --> T["Transit Gateway"]
    B["Spoke VPC B"] --> T
    C["Spoke VPC C"] --> T
    T --> I["Inspection VPC"]
    I --> F["Network Firewall endpoints"]
    F --> T
    T --> E["Egress VPC"]
    E --> N["NAT Gateway"]
    N --> G["Internet Gateway"]
    G --> X["Internet"]
~~~

This model fits organizations needing a centralized control point for east-west and north-south traffic.

When using Transit Gateway with an inspection VPC:

- Enable appliance mode on the inspection VPC attachment to keep forward and return flows in the same AZ.
- Use Transit Gateway route tables to separate spoke, inspection, and egress paths.
- Route workload subnets via TGW.
- Route traffic from TGW to the inspection endpoint in the same AZ.
- Verify return routes to spokes and routes out to the Internet.
- Account for Transit Gateway data processing and cross-AZ traffic costs.

### 9.3 Native Transit Gateway Attachment

AWS Network Firewall supports native attachments with Transit Gateway. When creating a firewall attached directly to Transit Gateway, AWS provisions and manages the underlying internal VPC infrastructure, endpoints, and attachments. Appliance mode is enabled automatically to maintain symmetric routing.

This is the centralized model to evaluate first for new Transit Gateway designs. It supports east-west inspection and centralized internet egress when paired with an egress VPC containing a NAT Gateway and Internet Gateway.

Benefits:

- Eliminates customer-managed inspection VPC infrastructure.
- Appliance mode is managed automatically.
- Supports allocating Network Firewall costs to traffic-originating accounts via corresponding Transit Gateway features.
- Simplifies certain route configurations compared to a traditional inspection VPC.

Review specific requirements before choosing native attachments. Use cases such as centralized ingress inspection, certain endpoint ENI metrics/logs, or specialized routing requirements may better fit a customer-managed inspection VPC.

### 9.4 AWS Cloud WAN

If an organization already uses AWS Cloud WAN as its global network backbone, service insertion can steer traffic through an inspection VPC hosting Network Firewall. This model suits multi-Region network segmentation and global routing policies.

### 9.5 Combined Deployment

You can combine a centralized firewall for inter-VPC traffic with distributed firewalls for specialized workloads. For example, most workloads traverse the inspection hub, while one high-throughput or uniquely regulated application uses a firewall endpoint in its own VPC.

Do not assume centralized is always cheaper. Compare endpoint counts, Transit Gateway charges, cross-AZ traffic, processed data volume, and operational complexity.

## 10. Traffic That Does Not Traverse Network Firewall

Certain traffic is not automatically visible to Network Firewall:

| Traffic | Reason | Additional Control |
|---|---|---|
| DNS queries to the VPC .2 Resolver (`AmazonProvidedDNS`) | DNS Resolver uses a dedicated path and does not traverse firewall endpoints | Route 53 Resolver DNS Firewall |
| Traffic between two resources in the same subnet | Local intra-subnet routing bypasses endpoints | Security Groups |
| Traffic over VPC peering | Peering routes are not automatically inserted through firewall endpoints | Security Groups or redesign via Transit Gateway |
| Traffic via AWS Global Accelerator | Global edge paths do not rely on VPC route tables in a way the firewall can intercept | AWS WAF, Security Groups, and endpoint controls |
| Traffic with routes bypassing the endpoint | Firewall is not on the data path | Fix route tables and verify paths |

DNS is a critical point. Network Firewall can inspect SNI or HTTP host in a connection after DNS resolution, but it cannot see queries sent to `AmazonProvidedDNS` at the VPC `.2` address. That creates a separate egress channel vulnerable to DNS tunneling or domain generation algorithms.

Deploy Route 53 Resolver DNS Firewall on VPCs requiring DNS query control. Combine DNS Firewall with Network Firewall to protect both the DNS resolution path and the connection data path.

## 11. Domain Filtering and Route 53 Resolved IP Validation

Domain filtering can rely on SNI in TLS Client Hello or HTTP host in HTTP requests. Without TLS inspection, the firewall can still read SNI, but cannot read HTTP payloads encrypted inside TLS.

Route 53 Resolved IP validation verifies a connection's destination address against IPs resolved by Route 53 Resolver for that domain. This adds confidence to domain-based filtering, especially when a client claims a domain that differs from the IP actually returned by the resolver.

A domain-based control should consider:

- Whether clients send SNI.
- Whether applications use QUIC/HTTP3 over UDP.
- Whether proxies or custom DNS resolvers are used.
- Whether domains sit behind CDNs with frequently changing IPs.
- Whether DNS queries pass through Route 53 Resolver to provide resolved IP context.
- Whether TLS inspection is needed to inspect HTTP host or URLs.

A domain allow list does not automatically govern every way an application reaches a service. Combine it with IP/port/protocol controls, DNS Firewall, and egress architecture.

## 12. TLS Inspection

TLS inspection enables Network Firewall to terminate TLS connections from clients, decrypt traffic in scope, apply stateful rules to the decrypted payload, and re-encrypt before sending to the server.

General flow:

~~~mermaid
flowchart LR
    A["TLS client"] --> B["Network Firewall"]
    B --> C["Decrypt using inspection configuration"]
    C --> D["Stateful / IPS rules inspect payload"]
    D --> E["Re-encrypt"]
    E --> F["Destination server"]
~~~

To enable TLS inspection:

1. Prepare certificates in AWS Certificate Manager.
2. Create a TLS inspection configuration.
3. Define inbound or outbound scope by protocol, source/destination IP, and port.
4. For outbound inspection, prepare a CA certificate so the firewall can mint certificates for destination servers.
5. Install the corresponding trust chain on client workloads so clients trust firewall-issued certificates.
6. For inbound inspection, prepare server certificates for protected domains.
7. Attach the TLS inspection configuration to a new firewall policy.
8. Test certificate validation, application compatibility, latency, and logging.

A TLS inspection configuration must be created before attaching to a new policy. AWS allows replacing an already-attached TLS inspection configuration with another configuration; you cannot add a configuration to an existing firewall policy that lacks one.

### 12.1 Known Limitations

- Supports TLS 1.1, 1.2, and 1.3 subject to compatibility conditions.
- TLS 1.0 and older SSL versions are not supported.
- StartTLS decryption is not supported.
- TLS over UDP such as QUIC is not supported by TLS inspection.
- Encrypted Client Hello (ECH) or missing SNI can cause connection resets.
- SNI in Client Hello must match the server certificate.
- WebSocket over HTTP/2 is not supported; WebSocket over HTTP/1.1 is supported.
- If TLS already terminated at an Application Load Balancer before the firewall, a firewall behind the ALB cannot decrypt the original TLS terminated at the ALB.
- Enabling TLS inspection can reset active flows within scope.
- TLS handshakes and certificate revocation checks can increase initial latency.

When the firewall decrypts traffic, the stateful engine can apply rules to inner payloads such as HTTP headers. For traffic within TLS inspection scope, TLS keywords other than `TLS.SNI` cannot be used for matching as they would on encrypted traffic; `TLS.SNI` can still be inspected. Network Firewall supports decrypted payload inspection for HTTP/2.

Do not decrypt all traffic by default. Define clear inspection goals, exclude sensitive or incompatible workloads, assess privacy requirements, and benchmark performance before expanding scope.

## 13. Logging: Alert, Flow, and TLS

Network Firewall supports three log types:

| Log Type | When Emitted | Used For |
|---|---|---|
| Alert | When a rule with an alert-generating action or a pass rule with an alert modifier matches | Near-real-time monitoring, investigating rule matches |
| Flow | When a flow ends or hits idle timeout | Analyzing volume, packet counts, duration, and bidirectional traffic |
| TLS | When TLS inspection is enabled and a TLS event occurs | Investigating SNI mismatches, certificate validation, and revocation |

Alert logs are usually the primary tool for monitoring ongoing events. Flow logs are not real-time; if a connection remains open, having no flow log yet is normal behavior.

Alert logs and flow logs can share a flow ID for correlation. Alert logs include `alert.action` and `verdict.action` fields. `alert.action` describes the alert rule's action, while `verdict.action` reflects the final verdict applied to traffic. When checking whether traffic was actually blocked, inspect the final verdict.

### 13.1 Log Destinations

Each log type can be sent to one destination:

| Destination | Best For |
|---|---|
| CloudWatch Logs | Fast analysis, Logs Insights, alarms, and operations |
| Amazon S3 | Long-term retention, Athena, auditing, and large-scale analysis |
| Amazon Data Firehose | Streaming to SIEM or external analytics systems |

Network Firewall configures one destination per log type. If you need copies of the same log type in multiple places, send to CloudWatch Logs and use subscription filters or another pipeline to forward.

For S3, logs are batched into files exported roughly every 5 minutes. A single file may contain multiple flows. When enabling monitoring dashboards backed by Athena, the log bucket must be in the same Region as the firewall and prefixes should not start with a leading slash.

Separate alert logs and flow logs into distinct log groups or S3 prefixes for easier querying. Protect logs with encryption, bucket policies, retention, and role-based access control.

## 14. CloudWatch Metrics and Alarms

Network Firewall publishes metrics in Amazon CloudWatch. Key operational metrics include:

| Metric | Meaning |
|---|---|
| `ReceivedPackets` | Packets received by the firewall |
| `PassedPackets` | Packets allowed |
| `DroppedPackets` | Packets dropped |
| `RejectedPackets` | Packets rejected |
| `Bytes` | Data volume processed |
| `Packets` | Packet volume by direction or engine |
| `StreamExceptionPolicyPackets` | Count of times the stream exception policy applied |

Metric names and dimensions vary by policy type, engine, traffic direction, and inspection settings. Check the CloudWatch metric catalog in the target Region before creating alarms.

Alarms to consider:

- Sudden spikes in `DroppedPackets` compared to baseline.
- Unusual increases in `RejectedPackets`.
- `StreamExceptionPolicyPackets` rising alongside application errors.
- `ReceivedPackets` approaching expected throughput limits.
- High-severity signatures appearing frequently in Alert logs.
- TLS logs showing spikes in SNI mismatches or certificate revocation failures.
- Unhealthy endpoint or firewall status.

Do not alert solely on total dropped packets. A deny-by-default policy naturally produces high drop counts by design. Correlate metrics with rule identity, severity, traffic source, and recent changes.

## 15. AWS Firewall Manager and Multi-Account Governance

AWS Firewall Manager centrally governs security policies across AWS Organizations. For Network Firewall, security teams can define account or OU scopes, deploy policies, and track compliance.

An operating model can include:

- A security account managing baselines and policies.
- A network account owning Transit Gateway, inspection VPCs, or native attachments.
- Application accounts hosting spoke VPCs and workloads.
- A logging account centralizing log storage.
- AWS RAM sharing Transit Gateways or rule groups as needed.

When using centralized inspection, define responsibilities clearly:

| Role | Responsibility |
|---|---|
| Network platform | Transit Gateway, route tables, firewall endpoints, and connectivity |
| Security engineering | Firewall policies, rule groups, threat signatures, and exceptions |
| Application team | Tags, workload requirements, testing, and allowlist requests |
| SOC / Incident response | Monitoring alerts, investigation, and incident response |
| FinOps | Tracking endpoint, data processing, logging, and cross-AZ costs |

AWS Firewall Manager can enforce policies across organizational scopes. Verify service-linked role permissions, delegated administrator account, supported Regions, and member account deployment status.

## 16. Deployment Procedure for a New Firewall

A deployment can follow these steps:

1. Identify traffic to inspect: egress, ingress, east-west, or combined.
2. Choose distributed, centralized, or combined architecture.
3. Choose policy type: Next Generation for new firewalls or Classic for existing systems.
4. Provision dedicated firewall subnets in each AZ.
5. Create firewall rule groups and IPS rule groups.
6. Create the firewall policy with default actions, mode, stream exception handling, and `HOME_NET`.
7. Create the firewall and attach the policy.
8. Retrieve the firewall endpoint ID per AZ.
9. Update route tables to steer traffic through endpoints.
10. Ensure symmetric request/response routing.
11. Enable alert/flow/TLS logging as required.
12. Verify CloudWatch metrics and configure alarms.
13. Test allow, drop, reject, domain filtering, and failure scenarios.
14. Expand gradually to production after validating behavior.

### 16.1 Creating a Next Generation Firewall Rule Group

Example creating a firewall rule group allowing TLS to domains under `example.com`. This illustrates Next Generation firewall engine syntax; test and tailor to actual policy.

Save the rule string to **firewall-rules.json**:

~~~json
{
  "RulesSource": {
    "RulesString": "accept:hook tcp:all $HOME_NET any -> $EXTERNAL_NET any (tcp.session:setup,established; app-layer-protocol:unknown|tls; sid:1;)\naccept:hook tcp:all $EXTERNAL_NET any -> $HOME_NET any (tcp.session:setup,established; app-layer-protocol:unknown|tls; sid:2;)\naccept:flow tls:<client_hello $HOME_NET any -> $EXTERNAL_NET any (tls.sni; dotprefix; content:\".example.com\"; endswith; nocase; sid:3;)\n"
  }
}
~~~

Create the rule group:

~~~bash
aws network-firewall create-rule-group \
  --rule-group-name allow-example-https \
  --type FIREWALL \
  --capacity 100 \
  --firewall-rule-group file://firewall-rules.json \
  --region ap-southeast-1
~~~

IPS rule groups can use Suricata-compatible rule strings. Example blocking a hypothetical SNI:

~~~json
{
  "RulesSource": {
    "RulesString": "drop tls $HOME_NET any -> $EXTERNAL_NET any (ssl_state:client_hello; tls.sni; content:\"bad.example\"; startswith; nocase; endswith; msg:\"Block prohibited SNI\"; sid:2001; rev:1;)\n"
  }
}
~~~

Save the JSON above as **ips-rules.json** before running the command to create the IPS rule group.

Create the IPS rule group:

~~~bash
aws network-firewall create-rule-group \
  --rule-group-name block-known-bad-sni \
  --type IPS \
  --capacity 100 \
  --ips-rule-group file://ips-rules.json \
  --region ap-southeast-1
~~~

Capacity is fixed when a rule group is created. Leave headroom for future rules. A rule group that hits its capacity cannot accept additional rules beyond that limit.

### 16.2 Creating a Next Generation Firewall Policy

Once rule groups are ACTIVE, collect each rule group's ARN and include it in the policy definition.

Example **policy.json**:

~~~json
{
  "FirewallRuleGroupEntries": [
    {
      "Priority": 1,
      "ResourceArn": "arn:aws:network-firewall:ap-southeast-1:111122223333:firewall-rulegroup/allow-example-https"
    }
  ],
  "IpsRuleGroupEntries": [
    {
      "ResourceArn": "arn:aws:network-firewall:ap-southeast-1:111122223333:ips-rulegroup/block-known-bad-sni"
    }
  ],
  "PolicyMode": "ENFORCE",
  "FirewallDefaultAction": "DROP"
}
~~~

Create the policy:

~~~bash
aws network-firewall create-firewall-policy-v2 \
  --firewall-policy-v2-name production-egress-policy \
  --firewall-policy-v2 file://policy.json \
  --region ap-southeast-1
~~~

Replace account IDs and ARNs with actual values. In Next Generation policies, the Firewall section uses priority; the IPS section has no priority and uses the IPS engine's action order.

### 16.3 Creating a VPC-Attached Firewall

Once the policy is ACTIVE, create the firewall with dedicated endpoint subnets in each AZ:

~~~bash
aws network-firewall create-firewall \
  --firewall-name production-egress-firewall \
  --firewall-policy-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall-policy-v2/production-egress-policy \
  --vpc-id vpc-0123456789abcdef0 \
  --subnet-mappings SubnetId=subnet-firewall-a SubnetId=subnet-firewall-b \
  --region ap-southeast-1
~~~

Retrieve status and endpoint IDs:

~~~bash
aws network-firewall describe-firewall \
  --firewall-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall/production-egress-firewall \
  --region ap-southeast-1
~~~

In the output, inspect firewall and attachment status per Availability Zone. Update routes only after endpoints are ready.

### 16.4 Updating Route Tables

Example for egress traffic:

| Route Table | Destination | Target |
|---|---|---|
| Workload subnet AZ-A | **0.0.0.0/0** | Firewall endpoint AZ-A |
| Firewall subnet AZ-A | **0.0.0.0/0** | NAT Gateway or Internet Gateway per architecture |
| Workload subnet AZ-B | **0.0.0.0/0** | Firewall endpoint AZ-B |
| Firewall subnet AZ-B | **0.0.0.0/0** | NAT Gateway or Internet Gateway per architecture |

If inbound inspection is needed, also update the Internet Gateway's edge-associated route table so traffic destined for workload subnets traverses the firewall endpoint. Do not overlook the return path.

## 17. Enabling Logging with the AWS CLI

Create **logging.json** with log destinations. Example sending Alert logs to CloudWatch Logs and Flow logs to S3:

~~~json
{
  "LoggingConfiguration": {
    "LogDestinationConfigs": [
      {
        "LogType": "ALERT",
        "LogDestinationType": "CloudWatchLogs",
        "LogDestination": {
          "logGroup": "network-firewall-alerts"
        }
      },
      {
        "LogType": "FLOW",
        "LogDestinationType": "S3",
        "LogDestination": {
          "bucketName": "central-network-firewall-logs",
          "prefix": "production/flow"
        }
      }
    ]
  }
}
~~~

Apply the logging configuration:

~~~bash
aws network-firewall update-logging-configuration \
  --firewall-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall/production-egress-firewall \
  --logging-configuration file://logging.json \
  --region ap-southeast-1
~~~

The S3 bucket requires a bucket policy granting access to the log delivery service. If using TLS inspection, also enable the TLS log type to investigate certificate validation and SNI mismatches.

## 18. Testing and Verifying Policies

Before promoting a policy to production, test at least these scenarios:

| Test | Expected Outcome |
|---|---|
| Client accesses an allowed domain | Connection succeeds |
| Client accesses a domain on the deny list | Connection is dropped or rejected per policy |
| Client connects to a disallowed port | Firewall default action handles appropriately |
| Client accesses a domain with missing or mismatched SNI | Outcome matches rule and TLS inspection behavior |
| Response traffic returns through an endpoint in another AZ | Asymmetric routing issue is detected |
| Workload queries VPC `.2` DNS Resolver | DNS Firewall handles the query; Network Firewall does not see it |
| Open flow has not terminated yet | Alert logs may appear; flow log appears only after flow termination |
| Firewall endpoint unavailable or misrouted | Verify fail-close behavior and recovery |

Initially, run policies in monitor mode if supported by the policy type, or target a canary workload group. Review alert/flow logs before switching to enforce to reduce the risk of blocking legitimate traffic.

Do not test with a single connection and conclude the whole policy is correct. Test across protocols, ports, AZs, traffic directions, IPv4/IPv6, and applications with specialized connection behavior.

## 19. Change Management and Rule Lifecycle

Firewall policies and rule groups govern workload connectivity. A small change can disrupt many applications.

A change process should include:

1. Change request specifying traffic source, destination, port, protocol, and business justification.
2. Owner confirmation of allowlists or exceptions.
3. Review of rule syntax and priority.
4. Verification of remaining capacity.
5. Testing in a non-production account or VPC.
6. Canary run and review of output logs.
7. Phased rollout across VPC groups or AZs.
8. Monitoring of metrics and application errors.
9. Retaining the previous policy version for rollback.

In Next Generation policies, the Firewall section uses priorities, so review ordering whenever adding rules. The IPS engine uses action order, so understand pass/drop/reject/alert interactions.

In Classic policies using Strict order, the first matching rule decides the verdict. Adding a broad pass rule at the top can prevent downstream drop rules from ever evaluating. Check for rule shadowing and overlap.

## 20. AWS Network Firewall Costs

Cost components to monitor:

- Firewall endpoint hours per Availability Zone.
- Data processing by gigabytes inspected.
- TLS inspection or advanced inspection when enabled.
- Logging destinations such as CloudWatch Logs, S3, and Data Firehose.
- Transit Gateway or Cloud WAN data processing.
- Cross-AZ traffic when routing to an endpoint in another AZ.
- Athena or analytics tools when querying S3-stored logs.

Cost optimization strategies:

- Choose the number of AZs matching HA requirements and workload placement.
- Use centralized inspection when multiple VPCs share a baseline and routing model.
- Use distributed firewalls for workloads with dedicated isolation or high-throughput needs.
- Avoid cross-AZ routing whenever possible.
- Enable flow logging only where needed; alert logs are often more actionable for security events.
- Set retention and lifecycle policies on S3 logs.
- Scope TLS inspection carefully because decryption adds cost and latency.
- Factor in Transit Gateway data processing charges when comparing centralized and distributed models.

Network Firewall scales automatically with traffic. Endpoints scale independently per AZ; bandwidth limit is 100 Gbps per AZ under current quotas. When planning major traffic surges such as launches or migrations, verify capacity and quotas, and consult AWS Support if needed.

## 21. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Firewall exists but traffic is not filtered | Route tables do not point to the endpoint | Inspect source, destination, and edge route tables |
| Outbound works but inbound is uninspected | Only outbound routes were updated | Update the IGW edge-associated route table |
| Stateful rules fail to match | Asymmetric routing or incomplete flow context | Verify both directions traverse the same endpoint/AZ |
| Traffic is dropped despite a pass rule | Action order puts pass ahead or wrong default action | Check rule order and policy defaults |
| Traffic is not dropped despite a drop rule | A pass rule evaluated first in Action Order | Use Strict order or a Next Generation policy |
| Domain allow list fails | SNI/HTTP host unobservable or wrong wildcard | Check protocol, SNI, TLS inspection, and rule syntax |
| HTTPS URL rule fails to match | HTTPS payload remains encrypted | Configure TLS inspection if HTTP content inspection is needed |
| DNS queries still leave | Queries to VPC `.2` Resolver bypass Network Firewall | Deploy Route 53 Resolver DNS Firewall |
| Flow logs do not appear immediately | Connection is still open | Wait for flow termination or idle timeout |
| No Alert log for drops | Rule action does not emit alerts or logging disabled | Check alert actions, modifiers, and logging config |
| TLS connections reset | Missing SNI, certificate mismatch, or unsupported TLS | Inspect TLS logs and certificates |
| Traffic disrupts after enabling TLS inspection | Existing flows reset when new scope applies | Plan drain/reconnect and phased rollout |
| High latency in one AZ | Cross-AZ traffic or asymmetric routing | Check per-AZ routes and endpoint metrics |
| Transit Gateway traffic dropped | Appliance mode disabled on inspection VPC attachment | Enable appliance mode or use native TGW attachment |
| Endpoint creation fails | Unsupported AZ or subnet fails requirements | Verify AZ, subnet, and endpoint status |
| `DroppedPackets` spikes suddenly | Policy update, traffic spike, or misrouting | Correlate metrics, logs, change history, and route tables |

### 21.1 Investigating Asymmetric Routing

1. Gather the flow's source IP, destination IP, port, and protocol.
2. Inspect the source subnet route table.
3. Inspect the firewall subnet route table.
4. Inspect the destination subnet or Internet Gateway route table.
5. Compare endpoint AZs for request and response paths.
6. With Transit Gateway, verify appliance mode and TGW route tables.
7. Use flow logs to check both directions of the same flow.
8. Check security groups and Network ACLs if only return traffic is missing.
9. Fix routes and retest with a fresh connection.

### 21.2 Investigating Why a Policy Fails to Block Traffic

1. Confirm traffic actually traverses the endpoint.
2. Check policy type and the section containing the rule.
3. Confirm the rule group is attached to the policy.
4. Check rule order or priority.
5. Check default actions.
6. Check `HOME_NET` and `EXTERNAL_NET`.
7. Check flow direction, protocol, and port.
8. Inspect logs for rule matches.
9. Retest with a new flow to avoid stale state.

## 22. Best Practices

### Architecture Design

- Clearly identify ingress, egress, and east-west traffic requiring inspection.
- Choose centralized or distributed based on VPC count, throughput, and isolation.
- Evaluate native Transit Gateway attachments for new centralized deployments.
- Deploy endpoints in every AZ hosting workloads.
- Maintain symmetric routing.
- Place firewall endpoints in dedicated subnets.
- Never assume all VPC traffic traverses the firewall.

### Policy and Rule Design

- Prefer Next Generation policies for new firewalls.
- Use Monitor mode before Enforce whenever feasible.
- Separate access control and IPS responsibilities.
- Set clear rule group priorities.
- Use Strict order with Classic policies.
- Manage `HOME_NET` properly for centralized inspection.
- Leave capacity headroom when creating rule groups.
- Test domain lists across SNI, HTTP host, subdomains, and real applications.
- Use managed rule groups deliberately and track updates.

### TLS Inspection and DNS

- Decrypt only traffic within required inspection scope.
- Manage certificates and trust chains via ACM.
- Test applications for TLS versions, SNI, and cipher suites.
- Account for QUIC, ECH, and StartTLS limitations.
- Use Route 53 Resolver DNS Firewall for queries to the VPC Resolver.
- Do not rely on domain allow lists as the sole control layer.

### Monitoring and Operations

- Enable Alert logs for security events requiring attention.
- Use Flow logs for post-flow traffic analysis.
- Enable TLS logs when using TLS inspection.
- Correlate alerts/flows via flow ID and final verdict.
- Monitor `DroppedPackets`, `RejectedPackets`, and `StreamExceptionPolicyPackets`.
- Archive long-term logs in S3 with lifecycle rules.
- Build baseline dashboards and alarms.
- Maintain runbooks for asymmetric routing and policy misconfigurations.

### Governance and Security

- Store policies/rules in version control with change reviews.
- Use Firewall Manager to enforce baselines across multiple accounts.
- Share rule groups via RAM when appropriate.
- Restrict permissions to modify firewalls, policies, rule groups, and route tables.
- Use KMS customer managed keys when key governance is required; never revoke access or delete keys actively protecting resources.
- Enforce an exception workflow with owners and expiration dates.
- Periodically review endpoint, data processing, TGW, and logging costs.

## 23. Limits and Quotas to Monitor

Quotas vary by Region and over time. Check Service Quotas and AWS documentation before large rollouts.

| Item | Documented Default Value |
|---|---:|
| Firewalls per account/Region | 5, adjustable via quota increase |
| Firewall policies per account/Region | 20 per policy family |
| Rule groups per account/Region | 50 per corresponding type |
| Rule groups in a Classic policy | Up to 20 stateful and 20 stateless |
| VPC endpoint associations per account/Region | 300, adjustable via quota increase |
| VPC endpoint associations per firewall/AZ | 50 |
| Stateful rule group capacity | Up to 30,000 |
| Stateless rule group capacity | Up to 30,000 |
| Stateful rules in a Classic policy | 30,000 default, adjustable via quota |
| Bandwidth through endpoints in one AZ | 100 Gbps |
| TLS inspection configurations per account/Region | 20 |
| TLS inspection configurations per policy | 1 |

Next Generation policies have separate quotas for the Firewall engine and IPS engine. Rule group capacity is fixed at creation; leave headroom for future changes. Quotas may differ between Classic and Next Generation policies.

## 24. Self-Study Exercises

1. How does AWS Network Firewall differ from Security Groups in inspection scope?
2. Why is creating a firewall in a VPC not enough for traffic to be inspected?
3. Can a firewall endpoint protect the subnet in which it resides?
4. Why is an endpoint needed in every AZ with workloads?
5. Distinguish Classic policies and Next Generation policies.
6. How do the default behaviors of the Next Generation firewall engine and IPS engine differ?
7. How can Classic stateful Action Order cause pass rules to affect drop rules?
8. Why is Strict order usually easier to control?
9. What does the stateless default action Forward to stateful mean?
10. Can rule group capacity be increased after creation?
11. Why must `HOME_NET` be configured when using centralized inspection?
12. Can a domain list based on `TLS_SNI` read encrypted HTTP payloads?
13. When is TLS inspection needed to filter HTTPS by HTTP host?
14. Why does Network Firewall not see DNS queries sent to the VPC `.2` Resolver?
15. What protection layer does Route 53 Resolver DNS Firewall add?
16. Why must requests and responses traverse the same firewall endpoint?
17. What problem does Transit Gateway appliance mode solve?
18. When should a native Transit Gateway attachment be chosen?
19. How do Alert logs and Flow logs differ in when they appear?
20. An alert log shows `alert.action=allowed` but `verdict.action=drop`. How was traffic ultimately handled?
21. Why do TLS logs not appear if TLS inspection is disabled?
22. Does TLS inspection support QUIC?
23. In what architecture can AWS WAF and Network Firewall be used together?
24. Why should you not rely solely on `DroppedPackets` to diagnose an incident?
25. When should AWS Firewall Manager be used?

### Suggested Answers

1. Security Groups control access at ENIs; Network Firewall inspects traffic routed through endpoints with stateful and application-protocol inspection.
2. Because route tables must steer traffic through the firewall endpoint.
3. No. A firewall endpoint does not protect the subnet containing the endpoint itself.
4. To minimize cross-AZ routing, support HA, and maintain symmetric flows.
5. Classic uses stateless/stateful engines; Next Generation separates firewall access control and IPS engines.
6. The Firewall engine defaults to Drop; the IPS engine defaults to Pass.
7. Action Order evaluates pass before drop, so a pass rule can take effect even if written later in the rule set.
8. Strict order evaluates in the exact priority order defined by administrators.
9. Packets not matching stateless rules are forwarded to the stateful engine for flow-based inspection.
10. No. Capacity is fixed at creation time.
11. Because traffic arriving from spoke VPCs may fall outside the default inspection VPC CIDR.
12. No. SNI is visible in Client Hello; HTTP payloads inside TLS remain encrypted without TLS inspection.
13. When you need to read HTTP hosts or URLs inside decrypted HTTPS traffic.
14. Because queries use the dedicated `AmazonProvidedDNS` processing path.
15. Filters DNS queries before clients establish connections.
16. The stateful engine requires bidirectional flow context to inspect application protocols.
17. Keeps requests and responses traversing the same appliance/endpoint AZ.
18. When building new centralized inspection and wanting AWS to manage attachment infrastructure.
19. Alert logs appear near real time upon rule match; Flow logs emit when a flow terminates or times out.
20. The final verdict is drop; `alert.action` only describes the alert rule's action.
21. TLS logs are emitted only for TLS inspection events.
22. No. TLS inspection does not support UDP-based QUIC.
23. WAF protects HTTP requests at ALB/CloudFront/API Gateway; Network Firewall inspects network-layer traffic along paths to workloads.
24. Because drops can be normal deny-by-default behavior; correlate with rules, flows, severity, and change history.
25. When governing security policies across multiple accounts and OUs in AWS Organizations.

## 25. Interview Questions

### What is AWS Network Firewall?

AWS Network Firewall is a managed firewall service for Amazon VPC. It deploys per-AZ firewall endpoints and uses firewall policies to inspect traffic routed through those endpoints.

### Does Network Firewall automatically filter all VPC traffic?

No. You must update route tables to send inspected flows through the firewall endpoints. Traffic that does not traverse an endpoint is not inspected by the policy.

### When should a Next Generation policy be used?

When deploying new firewalls and wanting to separate access control from IPS inspection. Next Generation policies provide a Drop-by-default firewall engine and a Pass-by-default IPS engine, cleanly separating those two responsibilities.

### Why does Network Firewall require symmetric routing?

The stateful engine tracks flows and must observe both requests and responses. If the two directions traverse different endpoints, application-layer inspection may fail to operate properly.

### Can a firewall endpoint share a subnet with workloads?

It should not. Firewall endpoints live in dedicated subnets, and an endpoint does not protect the subnet in which it is deployed.

### Does Network Firewall replace Route 53 Resolver DNS Firewall?

No. Queries to `AmazonProvidedDNS` inside a VPC follow a separate path invisible to Network Firewall. DNS Firewall protects that DNS query path.

### When is TLS inspection needed?

When policy requires inspecting HTTPS payloads after decryption, such as HTTP hosts/headers or application content. If filtering solely by SNI suffices, decrypting all TLS traffic may be unnecessary.

### Why separate Alert and Flow logs?

Alert logs support near-real-time monitoring of rule matches. Flow logs support analyzing traffic volume and connection state after flows conclude.

### When is centralized inspection used?

When multiple VPCs or accounts share a common baseline and the organization wants centralized policy management. Transit Gateway or Cloud WAN can serve as the routing hub.

### How does Network Firewall differ from AWS WAF?

Network Firewall inspects network traffic routed through endpoints. AWS WAF inspects HTTP/HTTPS requests at supported web services. The two services complement each other.

## 26. Pre-Production Checklist

### Architecture and Routing

- [ ] Ingress, egress, and east-west traffic flows are identified.
- [ ] Distributed/centralized/combined model has been reviewed.
- [ ] Firewall endpoints reside in dedicated subnets.
- [ ] Endpoints exist in all AZs requiring protection.
- [ ] Workload subnet route tables point to the right endpoints.
- [ ] Firewall subnet route tables point to the right next hops.
- [ ] Inbound paths are verified via IGW edge route tables if needed.
- [ ] Requests and responses traverse the same endpoint.
- [ ] Transit Gateway appliance mode or native attachment is configured properly.
- [ ] Bypassed traffic paths are documented with compensating controls.

### Policies and Rules

- [ ] Policy type matches requirements and compatibility.
- [ ] Default actions have been reviewed.
- [ ] Rule group priorities and evaluation order are clear.
- [ ] `HOME_NET` includes all networks requiring protection.
- [ ] Domain rules are tested against SNI, HTTP host, and subdomains.
- [ ] Rule group capacity includes room for growth.
- [ ] Managed rule groups have been evaluated for impact.
- [ ] Monitor/canary testing succeeded before enforce rollout.

### TLS and Logging

- [ ] TLS inspection scope is bounded.
- [ ] ACM certificates and trust chains are prepared.
- [ ] Applications are compatible with TLS inspection limitations.
- [ ] Alert, Flow, and TLS logs are enabled as needed.
- [ ] Log destinations have appropriate IAM/bucket policies.
- [ ] CloudWatch alarms and dashboards are configured.
- [ ] S3 retention/lifecycle and encryption are configured.

### Governance and Recovery

- [ ] Policies/rules are stored in version control.
- [ ] Exceptions have owners and approvals.
- [ ] AWS Firewall Manager is evaluated for multi-account governance.
- [ ] Runbooks exist for asymmetric routing and false positives.
- [ ] Rollback plans exist for policy and route changes.
- [ ] Quotas, throughput, and costs have been verified.
- [ ] A schedule exists to review rule groups and managed signatures.

## 27. Official References

- [What is AWS Network Firewall?](https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html)
- [Firewall components in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-components.html)
- [AWS Network Firewall firewall policy versions](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-versions.html)
- [Next Generation policies in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policies-v2.html)
- [How Network Firewall filters traffic with a Next Generation policy](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-processing-v2.html)
- [Creating a Next Generation policy](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-v2-creating.html)
- [Rule groups for Next Generation policies](https://docs.aws.amazon.com/network-firewall/latest/developerguide/rule-groups-v2.html)
- [Managing your own rule groups](https://docs.aws.amazon.com/network-firewall/latest/developerguide/rule-groups.html)
- [How AWS Network Firewall filters network traffic](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-processing.html)
- [Managing evaluation order for Suricata compatible rules](https://docs.aws.amazon.com/network-firewall/latest/developerguide/suricata-rule-evaluation-order.html)
- [Examples of stateful rules for Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/suricata-examples.html)
- [VPC route table configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-route-tables.html)
- [VPC subnet configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-subnets.html)
- [Creating a firewall in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/creating-firewall.html)
- [AWS Network Firewall no-source-preservation mode](https://docs.aws.amazon.com/network-firewall/latest/developerguide/no-source-preservation-mode.html)
- [Troubleshooting general issues](https://docs.aws.amazon.com/network-firewall/latest/developerguide/troubleshooting-general-issues.html)
- [Inspecting SSL/TLS traffic with TLS inspection configurations](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-configurations.html)
- [Considerations for TLS inspection](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-considerations.html)
- [Using SSL/TLS certificates with TLS inspection configurations](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-certificate-requirements.html)
- [Contents of a Network Firewall log](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-logging-contents.html)
- [Sending Network Firewall logs to Amazon S3](https://docs.aws.amazon.com/network-firewall/latest/developerguide/logging-s3.html)
- [AWS Network Firewall quotas](https://docs.aws.amazon.com/network-firewall/latest/developerguide/quotas.html)
- [AWS Security Services Best Practices - Network Firewall](https://aws.github.io/aws-security-services-best-practices/guides/network-firewall/)
