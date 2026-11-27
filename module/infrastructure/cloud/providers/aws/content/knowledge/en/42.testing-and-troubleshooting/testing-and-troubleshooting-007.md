# Diagnosing DNS, Routing, Security Groups, and VPC Connectivity

An application in Amazon VPC may fail to connect to a database, internal API, AWS service, or on-premises host even when the EC2 instance is in the `running` state. The root cause usually sits at one link in the packet path: DNS returns the wrong address, the route table picks the wrong target, a Security Group omits the required port, a Network ACL blocks return packets, a VPC endpoint lacks configuration, or the application is not listening on the expected address/port.

Effective troubleshooting starts from a concrete connection. Identify source, destination, protocol, port, initiation direction, and failure time. Then inspect name resolution, IP addressing, routing paths, network filtering layers, and the destination application in order. This narrows down the cause without opening broad network access or changing multiple settings simultaneously.

In AWS, tools such as Reachability Analyzer, VPC Flow Logs, Route 53 VPC Resolver query logs, EC2 status checks, and CloudWatch provide distinct perspectives. No single tool completely replaces testing from the workload itself. This lesson guides you on combining them to troubleshoot with evidence and safely restore connectivity.

## Learning Objectives

After this lesson, learners will be able to:

- Describe the path of a connection from source workload to destination workload in a VPC.
- Distinguish DNS errors, routing errors, Security Group errors, Network ACL errors, and application errors.
- Inspect Route 53 VPC Resolver, private hosted zones, DHCP option sets, and hybrid DNS.
- Read route tables, longest prefix match, and routes to Internet Gateways, NAT Gateways, and VPC endpoints.
- Analyze stateful Security Groups and stateless Network ACLs, including ephemeral ports.
- Diagnose connectivity across VPC peering, Transit Gateway, VPN, and Direct Connect.
- Use Reachability Analyzer to identify path blockers.
- Use VPC Flow Logs and Resolver query logs to verify actual behavior.
- Use Linux, Windows, and AWS CLI commands to gather evidence.
- Build troubleshooting workflows, runbooks, and production checklists.

## 1. VPC Connectivity Diagnostic Model

A TCP request to a service in a VPC typically traverses these logical steps:

1. The application determines the destination hostname or IP address.
2. If using a hostname, the OS queries the DNS resolver and receives one or more IP addresses.
3. The OS selects the destination IP, source IP, and local route.
4. Packets traverse the subnet route table and network components such as NAT Gateway, Internet Gateway, VPC peering, Transit Gateway, or VPC endpoints.
5. Network ACLs inspect traffic at subnet boundaries.
6. Security Groups attached to network interfaces inspect inbound/outbound resource traffic.
7. The destination OS receives the packet; host firewalls and the application process handle it further.
8. Return packets travel back to the source via corresponding routes and filtering layers.

~~~mermaid
flowchart TD
    A["Application: hostname + port"] --> B["DNS resolution"]
    B --> C["Destination IP address"]
    C --> D["Route table / network path"]
    D --> E["Network ACL at subnet"]
    E --> F["Security Group at ENI"]
    F --> G["OS firewall / service listener"]
    G --> H["Response traffic"]
    H --> I["Return route + NACL + state tracking"]
    I --> J["Application receives response"]
~~~

Paths vary by topology. For example, traffic to S3 via a gateway endpoint bypasses the NAT Gateway; traffic to an interface endpoint goes to the endpoint ENI's private IP; traffic to another VPC may traverse peering or Transit Gateway.

### 1.1. Gathering Information Before Changing Anything

For every incident, record:

| Detail | Example |
|---|---|
| Source | EC2 instance ID, ENI ID, subnet, and VPC ID |
| Destination | Hostname, IP, ENI, or endpoint ID |
| Protocol/port | TCP 443, TCP 5432, UDP 53 |
| Direction | Client-initiated outbound or server-initiated inbound |
| Address family | IPv4 or IPv6 |
| Expected path | Local VPC, IGW, NAT, peering, TGW, VPN, or endpoint |
| Symptom | NXDOMAIN, timeout, connection refused, TLS error, HTTP 403/5xx |
| Time window | Start time of failures and testing timestamps |
| Recent changes | Routes, SGs, NACLs, DNS, deployments, endpoints, or application releases |

A `connection timed out` message usually indicates the client received no response in time; it does not prove a Security Group is at fault. `connection refused` typically indicates traffic reached the host, yet no listener accepts that port or the host actively rejected it. `NXDOMAIN` is a DNS response indicating the name does not exist in the queried resolver scope. Distinguishing symptoms guides which layer to inspect.

## 2. Diagnosing DNS in a VPC

DNS translates hostnames into IP addresses. If DNS is wrong, subsequent route and Security Group checks may target the wrong destination.

Amazon VPC includes Route 53 VPC Resolver, formerly called Route 53 Resolver. The resolver is built into the VPC and handles queries for public DNS names, AWS-provided internal names, and Route 53 private hosted zones.

Common resolver addresses:

- IPv4: primary VPC IPv4 CIDR base plus 2, e.g., VPC `10.20.0.0/16` has resolver `10.20.0.2`.
- Link-local IPv4: `169.254.169.253`.
- IPv6: `fd00:ec2::253`.

### 2.1. Two VPC DNS Attributes

Two attributes to check:

| Attribute | Role |
|---|---|
| `enableDnsSupport` | Enables DNS resolution in the VPC via the Amazon-provided DNS server. |
| `enableDnsHostnames` | Assigns public DNS hostnames to instances with public IPs/EIPs and supports corresponding private DNS use cases. |

For private hosted zones and private DNS on interface VPC endpoints, both attributes must be enabled. If either is disabled, Route 53 VPC Resolver may fail to resolve Amazon-provided private DNS hostnames.

Check with the AWS CLI:

~~~bash
aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsSupport

aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsHostnames
~~~

Never toggle DNS attributes experimentally in production. Identify beforehand which workloads depend on custom DNS, private hosted zones, or private endpoints.

### 2.2. Testing from an EC2 Instance

Linux:

~~~bash
cat /etc/resolv.conf

getent hosts api.internal.example.com

dig api.internal.example.com A

dig api.internal.example.com AAAA

dig @10.20.0.2 api.internal.example.com A
~~~

Windows PowerShell:

~~~powershell
Get-DnsClientServerAddress

Resolve-DnsName api.internal.example.com -Type A

Resolve-DnsName api.internal.example.com -Type AAAA
~~~

How to interpret results:

| Result | What to Inspect |
|---|---|
| `NOERROR` with answer | Name resolved; verify the returned IP matches the intended environment/endpoint. |
| `NXDOMAIN` | Resolver could not find the name in the queried namespace; check spelling, hosted zones, and records. |
| `SERVFAIL` | Resolver failed to complete the query; check forwarding rules, upstream DNS, DNS Firewall, or DNSSEC. |
| Timeout | Client received no DNS response; check resolver address, custom DNS, DHCP options, and path to custom DNS servers. |
| `A` works yet `AAAA` fails | Workload may prefer IPv6 and fail even when IPv4 works; inspect IPv6 routes and endpoints. |
| Stale IP | Likely due to TTL/caching at resolver, OS, JVM, or app layers; inspect TTL and cache layers. |

Do not rely solely on pinging a hostname to conclude DNS failed. Ping may be blocked by ICMP filters while DNS and TCP still work. Use `dig`, `Resolve-DnsName`, or `getent` to test DNS independently.

### 2.3. Private Hosted Zones

A private hosted zone resolves only within associated VPCs or VPCs linked via appropriate DNS mechanisms. Verify:

- Does the hosted zone domain name match the queried hostname?
- Is the workload's VPC associated with the private hosted zone?
- Do A, AAAA, CNAME, or alias records point to the right target?
- Is another private hosted zone in the same namespace shadowing public records?
- Is a Resolver rule forwarding that domain to another DNS server?
- Does the DHCP option set point to a custom DNS resolver?

A private hosted zone can return `NXDOMAIN` for a name that has a public DNS record if the private namespace takes precedence yet lacks an internal record. This commonly explains why applications inside a VPC resolve names differently from external laptops.

### 2.4. Hybrid DNS with On-Premises

When a VPC needs to resolve data-center domains, or on-premises hosts need to resolve names in a private hosted zone, use Route 53 VPC Resolver endpoints:

| Endpoint | Query Direction |
|---|---|
| Inbound Resolver endpoint | On-premises DNS resolvers or other VPCs send queries into AWS to resolve private hosted zones. |
| Outbound Resolver endpoint | VPC Resolver sends queries from AWS to on-premises DNS resolvers per forwarding rules. |

Typical outbound flow:

1. Create an outbound endpoint in a VPC with network reachability to on-premises DNS servers.
2. Endpoint Security Group allows outbound TCP/UDP 53 to target resolvers.
3. Create a forwarding rule for the domain, e.g., `corp.example.com`.
4. Associate the rule with required VPCs.
5. Verify routes over VPN or Direct Connect and firewalls at both ends.

Typical inbound flow:

1. Create an inbound endpoint with IPs across multiple Availability Zones per availability requirements.
2. Security Group allows inbound TCP/UDP 53 from on-premises DNS resolvers.
3. Configure on-premises DNS servers to forward private domains to the inbound endpoint IPs.
4. Verify routes, NACLs, and firewalls between both networks.

Do not forward queries from on-premises directly to the VPC CIDR + 2 address. AWS recommends using an inbound Resolver endpoint for queries originating outside the VPC.

### 2.5. DNS Query Logging and DNS Firewall

VPC Resolver query logging records DNS queries and response codes such as `NOERROR`, `NXDOMAIN`, or `SERVFAIL`. Logs can be delivered to CloudWatch Logs, S3, or Firehose.

Note: Resolver caches answers according to TTL. Query logs record unique queries processed by Resolver; responses served from cache may not emit new log records.

To block domains, use Route 53 Resolver DNS Firewall. Security Groups and Network ACLs cannot filter DNS traffic to/from `AmazonProvidedDNS`. DNS Firewall is the domain control layer for queries traversing VPC Resolver.

## 3. Reading and Inspecting Route Tables

Route tables determine the next hop for traffic based on destination IP. Each subnet is associated with one route table; without an explicit association, a subnet uses the VPC's main route table.

Each route has a destination and a target. Examples:

| Destination | Target | Meaning |
|---|---|---|
| `10.20.0.0/16` | `local` | Intra-VPC traffic |
| `0.0.0.0/0` | `igw-...` | IPv4 Internet route via Internet Gateway |
| `0.0.0.0/0` | `nat-...` | IPv4 outbound route from private subnet via NAT Gateway |
| `pl-...` | `vpce-...` | Route to S3/DynamoDB gateway endpoint via prefix list |
| `10.30.0.0/16` | `pcx-...` | Route to VPC peering |
| `10.40.0.0/16` | `tgw-...` | Route to Transit Gateway |
| `192.168.0.0/16` | `vgw-...` | Route to Virtual Private Gateway/VPN |

### 3.1. Longest Prefix Match

When multiple routes match a destination, the VPC selects the most specific route (longest prefix match). Example:

| Route | Target |
|---|---|
| `0.0.0.0/0` | NAT Gateway |
| `10.30.0.0/16` | VPC peering |
| `10.30.5.0/24` | Transit Gateway |

Traffic to `10.30.5.10` matches all three routes yet picks `10.30.5.0/24` because it has the most specific prefix. A specific route pointing to the wrong target can misroute traffic even when the default route is correct.

When routes share identical prefixes, route priority also considers route type: static routes take precedence over prefix-list routes, followed by propagated routes. When in doubt, inspect the actual route table and route states rather than checking only the default route.

### 3.2. Public Subnets and Internet Gateways

For an EC2 instance to access the Internet over IPv4 via an Internet Gateway, all of the following are required:

- An Internet Gateway is attached to the VPC.
- The subnet's route table has an appropriate route, typically `0.0.0.0/0 → igw-...`.
- The EC2 instance has a public IPv4 address or Elastic IP.
- Security Groups and NACLs permit the traffic.
- The destination application or external firewall permits the connection.

Having a route to an IGW does not automatically assign a public IP to an instance. An EC2 instance with only a private IP cannot directly communicate over IPv4 Internet via an IGW.

IPv6 uses a separate path. Workloads need an IPv6 CIDR and IPv6 address, plus a `::/0` route to the IGW for bidirectional Internet connectivity.

### 3.3. Private Subnets and NAT Gateways

Private subnets can initiate outbound IPv4 Internet connections through a NAT Gateway:

- The NAT Gateway resides in a public subnet.
- The NAT Gateway is `Available` and has an Elastic IP (for public NAT Gateways).
- The NAT's public subnet has a route to the IGW.
- The private subnet's route table has `0.0.0.0/0 → nat-...`.
- Security Groups/NACLs allow outbound connections and return traffic.

A NAT Gateway lets private workloads initiate outbound connections; it does not provide arbitrary inbound access from the Internet to private instances.

In multi-AZ architectures, consider deploying a NAT Gateway per AZ to reduce cross-AZ dependencies and improve fault tolerance. Routing to a NAT Gateway in another AZ incurs cross-AZ data transfer and depends on that AZ.

For IPv6 outbound-only access, use an Egress-only Internet Gateway and a `::/0` route; an IPv4 NAT Gateway does not replace this IPv6 mechanism.

### 3.4. VPC Endpoints

When workloads access AWS services, VPC endpoints avoid traversing the Internet or NAT:

| Endpoint | Properties to Check |
|---|---|
| Gateway endpoint | Uses route tables and prefix lists; commonly used for Amazon S3 and DynamoDB. |
| Interface endpoint | Provisions endpoint network interfaces in subnets; the endpoint's Security Group controls inbound traffic to the ENI. |

For interface endpoints:

- The VPC must have `enableDnsSupport` and `enableDnsHostnames` enabled if using private DNS.
- The endpoint's private DNS name must be enabled if applications call standard service hostnames.
- The endpoint Security Group must allow inbound TCP 443 from workload clients.
- The endpoint policy must allow required actions/resources.
- Target service IAM policies and resource policies still apply.

For gateway endpoints, check route table associations and endpoint policies. Gateway endpoints do not have endpoint ENIs to attach Security Groups to.

### 3.5. Inspecting Route Tables with the AWS CLI

~~~bash
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# Inspect every route table in the VPC, including the main route table
aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0

aws ec2 describe-route-tables \
  --route-table-ids rtb-0123456789abcdef0
~~~

Fields to inspect:

- `Associations`: which subnets use the route table.
- `Routes`: destination, target, and `State`.
- `Origin`: whether the route was user-created or propagated.
- `State`: whether the route is `active` or `blackhole`.
- `GatewayId`, `NatGatewayId`, `VpcPeeringConnectionId`, `TransitGatewayId`: exact next hop.

A `blackhole` route cannot forward traffic. Check whether the target was deleted, the attachment dropped, or propagation was disabled.

## 4. Security Groups: Stateful Firewalls at the Network Interface

A Security Group is a virtual firewall attached to a resource's network interface. Security Groups support allow rules only; traffic not matching an allow rule is denied.

Security Groups are stateful. Once a connection is permitted, return traffic for that connection is automatically allowed even without a symmetric outbound/inbound rule.

### 4.1. Checking the Right Interface and Port

An EC2 instance can have multiple ENIs and multiple Security Groups. Do not judge by instance name alone; inspect the actual ENI carrying the traffic.

~~~bash
aws ec2 describe-network-interfaces \
  --network-interface-ids eni-0123456789abcdef0

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0
~~~

Example web application running on TCP 443 and connecting to PostgreSQL on TCP 5432:

| Resource | Inbound Rule | Outbound Rule |
|---|---|---|
| ALB SG | TCP 443 from allowed client CIDR | App TCP port to App SG |
| App SG | App TCP port from ALB SG | TCP 5432 to DB SG |
| DB SG | TCP 5432 from App SG | Return traffic allowed by stateful SG |

This pattern restricts sources to the calling tier's Security Group. Avoid opening database ports to `0.0.0.0/0` or the entire VPC if only the app tier needs access.

### 4.2. Checking Common Security Group Errors

- Inbound rule opens the wrong port, protocol, or source CIDR.
- Rule specifies a public IP while actual traffic uses private IPs.
- Security Group is attached to a different ENI than the one serving traffic.
- Outbound rules are restricted and block clients from initiating connections.
- Invalid Security Group reference in an inter-VPC topology.
- Source workload changed SGs while referencing rules were not updated.
- Traffic traverses a middlebox/NAT, changing the source IP from expectations.

Security Group referencing lets you use an SG as a source/destination in supported topologies. For inbound rules, referenced SGs can reside in the same VPC, a peered VPC, or a VPC connected via Transit Gateway. For outbound rules, referencing covers the same VPC or a peered VPC. However, not all middlebox paths preserve SG reference semantics. When traffic between two instances traverses a middlebox appliance, SG referencing may not permit traffic as expected; inspect private IPs or source/destination CIDRs instead.

### 4.3. Traffic Not Filtered by Security Groups

Security Groups do not filter traffic to/from certain foundational services, including `AmazonProvidedDNS`, DHCP, instance metadata, ECS task metadata, Windows license activation, Amazon Time Sync Service, and certain reserved router addresses. To filter DNS queries via `AmazonProvidedDNS`, use Route 53 Resolver DNS Firewall.

## 5. Network ACLs: Stateless Firewalls at the Subnet

Network ACLs (NACLs) apply at the subnet level and have separate inbound and outbound rules. Unlike Security Groups, NACLs are stateless: AWS does not automatically allow return traffic just because the initial request was allowed.

NACLs support both allow and deny rules. Rules are evaluated in ascending rule-number order; the first matching rule decides allow or deny.

### 5.1. Example: Why Requests Succeed Yet Responses Are Dropped

An external client opens a TCP connection to a web server in a subnet:

- The request has destination port 443.
- The client chooses a source ephemeral port, e.g., 49152.
- The server's response has source port 443 and destination port 49152.

If the inbound NACL allows port 443 yet the outbound NACL blocks responses to the client's ephemeral port, the connection can time out even though stateful Security Groups allowed the response.

Ephemeral port ranges depend on the initiating OS or device. For example, many Linux kernels use `32768–61000`; modern Windows Server versions typically use `49152–65535`; NAT Gateways and certain AWS services use other ranges. Identify the actual traffic sources and select the needed range rather than blindly copying a generic port range.

### 5.2. NACL Checklist

- Check the NACLs associated with both source and destination subnets.
- Check both inbound and outbound rules.
- Check whether a lower-numbered rule denies traffic before an allow rule.
- Check protocol, port, and source/destination CIDRs.
- Check IPv4 and IPv6 separately; IPv4 rules do not apply to IPv6.
- Check ephemeral ports for return traffic.
- Check NACLs on both subnets when traffic crosses two different subnets.

NACLs do not filter traffic to/from `AmazonProvidedDNS`, DHCP, and certain other foundational services. Use DNS Firewall for domain filtering on `AmazonProvidedDNS`.

## 6. Connectivity Across VPCs, Subnets, and On-Premises Networks

### 6.1. VPC Peering

When using VPC peering, verify:

- The peering connection is `active`.
- The CIDRs of the two VPCs do not overlap.
- Route tables on both sides route to the peer VPC CIDR via the peering connection.
- Security Groups allow the source/destination and port.
- NACLs in both subnets allow both requests and responses.
- DNS resolution options are enabled if resolving names across peering.

VPC peering is non-transitive. If VPC-A peers with VPC-B and VPC-B peers with VPC-C, traffic does not automatically flow from A to C through B. You need a topology such as Transit Gateway or an appropriate network appliance design.

### 6.2. Transit Gateway

With Transit Gateway, inspect multiple layers:

1. VPC/VPN/DX attachments are `available`.
2. Subnet route tables route to the TGW.
3. The TGW route table is associated with the correct attachment.
4. Routes are propagated or static routes exist.
5. The TGW route table has a path to the destination attachment.
6. The destination subnet's route table has a return path.
7. SGs/NACLs at the destination resource allow the traffic.

An attachment is associated with a TGW route table, whereas propagation populates attachment routes into route tables. Do not confuse association with propagation.

### 6.3. Site-to-Site VPN and Direct Connect

When connecting to on-premises:

- Check VPN tunnel state or Direct Connect virtual interface status.
- Check BGP sessions and route advertisements if using dynamic routing.
- Verify on-premises firewalls allow the CIDRs/ports.
- Check routes back to AWS on the on-premises side.
- Check routes to on-premises in the VPC/TGW.
- Verify CIDRs do not overlap or get shadowed by summary routes.
- Check MTU/MSS when symptoms occur only with large payloads or TLS handshakes.

A one-way path is not enough. Both requests and responses require valid routes.

## 7. Reachability Analyzer: Finding Blockers in Network Configuration

VPC Reachability Analyzer is a static configuration analysis tool. You specify a source, destination, protocol, and port; the tool models the virtual network path, returning hop-by-hop details when reachable or identifying the component blocking the path.

Reachability Analyzer can identify issues in:

- Route tables.
- Security Groups.
- Network ACLs.
- VPC peering or Transit Gateway.
- NAT Gateways, Internet Gateways, and supported network components.
- Load balancers, VPC endpoints, and attachments within supported topologies.

### 7.1. When to Use It

Example: an app EC2 instance in a private subnet cannot reach a database ENI on TCP 5432.

1. Select the app ENI as the source.
2. Select the database ENI as the destination.
3. Choose TCP and destination port 5432.
4. Run the analysis.
5. Read the path components and explanation codes.
6. Fix the specific route/SG/NACL identified.
7. Re-run the analysis and test from the workload.

Reachability Analyzer performs static configuration analysis and does not send real packets through applications. A `reachable` path does not prove the database process is running, DNS resolves properly, the OS firewall permits traffic, TLS is valid, or the application accepts requests.

The tool supports specific resource types and topologies. Source and destination must be in the same Region and within the same VPC or VPCs connected via supported peering/TGW. For unsupported components or complex paths, combine Flow Logs and runtime testing.

## 8. VPC Flow Logs: Observing Actual Traffic

VPC Flow Logs capture metadata about IP traffic going to and from a VPC, subnet, or network interface. Logs can be published to CloudWatch Logs, S3, or Firehose.

Flow Logs help:

- Confirm whether traffic reaches an ENI.
- Distinguish accepted vs. rejected traffic at the network layer.
- Identify source/destination IPs, ports, and protocols.
- Analyze request/response directionality.
- Diagnose overly restrictive Security Groups or NACLs.

Illustrative record:

~~~text
2 123456789012 eni-0123456789abcdef0 10.20.1.15 10.20.3.25 49152 5432 6 12 840 1763652000 1763652060 REJECT OK
~~~

Fields in order represent version, account, interface ID, source/destination addresses, source/destination ports, protocol, packets, bytes, start/end times, action, and log status.

- `ACCEPT`: traffic was permitted by network controls.
- `REJECT`: traffic was denied, e.g., by a Security Group or NACL, or packets arrived after connection closure.
- `OK`: logging proceeded normally.
- `NODATA`: no traffic during the aggregation interval.
- `SKIPDATA`: some records were skipped during the interval.

### 8.1. Limitations of Flow Logs

Flow Logs do not capture packet payloads, do not show HTTP status codes returned by applications, and do not prove a service listener is running. Traffic to/from the Amazon DNS server (`AmazonProvidedDNS`/VPC Resolver), DHCP, instance metadata, and certain foundational addresses is not logged. Therefore, an absence of Flow Log records for a DNS query to VPC Resolver does not mean the client sent no query.

Flow Logs are aggregated over intervals and can arrive with delay. Some records may be skipped; inspect `log-status` and delivery status. When DNS evidence is required, enable Resolver query logging.

### 8.2. Reading Flow Logs to Determine Failure Direction

Examples:

- `ACCEPT` from app ENI to DB ENI on TCP 5432 with no response: check the DB listener, host firewall, return route, outbound/inbound NACLs, and database logs.
- `REJECT` from app to DB: check SGs/NACLs for the exact source/destination/port.
- Request `ACCEPT` yet response `REJECT`: typically inspect stateless NACLs and ephemeral ports on the return path.
- No records on the destination ENI: check routes, source ENI, endpoints/attachments, and Flow Log scope.

Flow Logs record traffic at the network layer; an `ACCEPT` record does not mean the application processed the request successfully.

## 9. Comparing Observability Tools

| Tool | Question Answered | Key Limitation |
|---|---|---|
| `dig`, `nslookup`, `Resolve-DnsName` | What IP does the hostname resolve to? | Reflects only the resolver and cache at test time |
| Route 53 Resolver query logs | What queries did VPC Resolver receive and what response codes did it return? | Cache hits may not generate new log records |
| Reachability Analyzer | Does network configuration permit the virtual path? | Static analysis; sends no packets to applications |
| VPC Flow Logs | What traffic was accepted/rejected at an ENI/subnet/VPC? | No payloads; omits `AmazonProvidedDNS` traffic |
| Network Access Analyzer | Does network access violate intent/security posture? | Access-path analysis, not a runtime probe |
| `nc`, `curl`, `Test-NetConnection` | Can the real workload establish TCP/TLS/HTTP connections? | Tests only the path and service at execution time |
| CloudTrail | Who modified routes, SGs, NACLs, or endpoints and when? | Records API activity, not packet traces |

A strong workflow uses Reachability Analyzer to flag suspicious configuration, Flow Logs to observe traffic, and runtime tests to confirm actual behavior.

## 10. Testing Directly from the Workload

### 10.1. Linux

Inspect interfaces and addresses:

~~~bash
ip addr

ip route

ip route get 10.20.3.25
~~~

`ip route get` shows which route the source machine's kernel selects. It does not display the entire VPC route table or TGW route table.

Test TCP:

~~~bash
nc -vz -w 5 db.internal.example.com 5432

curl -v --connect-timeout 5 https://api.internal.example.com/health

openssl s_client \
  -connect api.internal.example.com:443 \
  -servername api.internal.example.com
~~~

Interpreting output:

- DNS resolves yet `nc` times out: check routes, SGs, NACLs, firewalls, and return path.
- `nc` reports `connection refused`: TCP reached the host, yet nothing is listening on that port or the host rejected it.
- TCP connects yet TLS fails: check certificates, SNI, trust store, TLS versions, and system clock.
- TLS succeeds yet HTTP returns 403/5xx: the network path works; inspect authorization, load balancers, WAF, or the application.

### 10.2. Windows PowerShell

~~~powershell
Resolve-DnsName db.internal.example.com

Test-NetConnection db.internal.example.com -Port 5432 -InformationLevel Detailed

tracert db.internal.example.com
~~~

`Test-NetConnection` displays the remote address, source interface, and TCP test outcome. `tracert` may hide intermediate hops because ICMP/TTL-expired traffic can be filtered; never conclude routing is broken solely from `*` lines.

### 10.3. Testing IPv4 and IPv6 Separately

If DNS returns both `A` and `AAAA`, applications may prefer IPv6 or try both. Working IPv4 routing does not guarantee working IPv6 routing.

~~~bash
dig api.example.com A

dig api.example.com AAAA

curl -4 -v https://api.example.com/health

curl -6 -v https://api.example.com/health
~~~

If only IPv6 fails, check IPv6 CIDRs, addresses attached to ENIs, `::/0` routes, Egress-only IGWs, IPv6 SG/NACL rules, and endpoint support.

## 11. Layer-by-Layer Troubleshooting Workflow

Follow this sequence for a failing connection:

1. **Identify the symptom:** DNS error, timeout, refused, TLS error, or HTTP error.
2. **Check DNS:** resolve `A`/`AAAA`, compare the IP against the expected endpoint, and review query logs if available.
3. **Check IP path:** identify source ENI/subnet, destination ENI/IP, route table associations, and longest prefix match.
4. **Check bidirectional routes:** are both forward and return routes valid?
5. **Check Security Groups:** right ENI, right source/destination, protocol, and port.
6. **Check NACLs:** both inbound/outbound and ephemeral ports on both subnets.
7. **Check middleboxes/endpoints:** NAT state, IGW attachment, TGW attachments/route tables, endpoint ENIs/endpoint policies.
8. **Check runtime:** TCP connect, TLS handshake, service listener, OS firewall, and application logs.
9. **Correlate telemetry:** Reachability Analyzer, Flow Logs, Resolver query logs, CloudTrail, and CloudWatch.
10. **Fix one evidence-backed cause:** re-run the exact test, compare before/after, and document the change.

Never open all inbound/outbound traffic to `0.0.0.0/0` or `::/0` just to see if it works. If a temporary test rule is needed, restrict source, port, and duration, log a change ticket, and roll back immediately after verification.

## 12. Common Failure Scenarios

### 12.1. EC2 Cannot Resolve Private Hostnames

Symptom: `dig app.internal.example.com` returns `NXDOMAIN` or `SERVFAIL`.

Check:

- `enableDnsSupport=true` and `enableDnsHostnames=true`.
- Private hosted zone is associated with the right VPC.
- Record name and target are correct.
- DHCP options do not point to an unexpected custom DNS resolver.
- A Resolver forwarding rule does not match a more specific domain.
- DNS Firewall is not blocking the query.
- Response codes recorded in query logs.

If custom DNS sits on-premises, check outbound Resolver endpoints, TCP/UDP 53 security groups, VPN/DX routes, and upstream DNS servers.

### 12.2. App Server Cannot Connect to Database on TCP 5432

Symptom: `nc -vz db.internal.example.com 5432` times out.

Check in order:

- Does DNS return the DB's correct private IP?
- Does the app subnet route table route to the DB subnet CIDR via `local`?
- Does the DB ENI have the right Security Group?
- Does DB SG inbound allow TCP 5432 from the app SG?
- Does app SG outbound allow TCP 5432 to the DB if egress is restricted?
- Do NACLs on both subnets allow requests and ephemeral responses?
- Is the DB in `available` state and listening on port 5432?
- Do host firewalls and DB access rules allow the connection?

If Reachability Analyzer reports the path reachable yet `nc` still times out, inspect the listener, host firewall, database service, and actual return traffic.

### 12.3. EC2 in Private Subnet Cannot Call a Public API

Check:

- Does the private subnet route table have `0.0.0.0/0 → nat-...`?
- Is the NAT Gateway `Available` and placed in a public subnet?
- Does the NAT's public subnet have `0.0.0.0/0 → igw-...`?
- Does the NAT Gateway have an Elastic IP?
- Do NACLs/SGs allow outbound TCP 443 and return ephemeral ports?
- Does DNS resolve the public hostname properly?
- Is a proxy, firewall, or more specific route steering traffic elsewhere?

If calling only supported AWS services, consider VPC endpoints for private connectivity and reduced NAT/Internet dependence.

### 12.4. Connection Across VPC Peering Fails

Check:

- The two VPC CIDRs do not overlap.
- The peering connection is `active`.
- Source route table has a route to the peer CIDR via peering.
- Destination route table has a route back to the source CIDR.
- SGs/NACLs allow bidirectional traffic.
- Appropriate DNS resolution options are enabled if calling by hostname.

Never assume VPC peering provides transitive routing.

### 12.5. Connection to Interface VPC Endpoint Times Out

Check:

- The endpoint is `available`.
- The endpoint has a subnet/ENI in an AZ reachable by the workload.
- Private DNS is enabled and VPC DNS attributes are configured properly.
- The endpoint SG allows inbound TCP 443 from the workload.
- The workload's outbound SG allows TCP 443 to the endpoint.
- Subnet NACLs allow requests and responses.
- Endpoint policies, IAM policies, and service resource policies allow the action.

If TCP 443 connects yet the API returns `AccessDenied`, the issue lies in authorization/policies rather than the network path.

### 12.6. Connection Works by IP Yet Fails by Hostname

The issue likely lies in DNS or TLS hostname validation:

- Hostname resolves to a different IP than the one tested directly.
- A private hosted zone shadows a public record.
- `A`/`AAAA` records are inconsistent.
- The application caches DNS longer than TTL.
- The TLS certificate lacks the hostname or SNI is not sent properly.
- HTTP `Host` header or reverse proxy virtual host mismatches.

Use `curl -v` and `openssl s_client -servername` to separate DNS/TCP from TLS/SNI.

## 13. AWS CLI: Gathering Read-Only Network Configuration

These commands capture configuration before making changes:

~~~bash
# VPC DNS attributes
aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsSupport

# Route table associated with a subnet
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# Security groups attached to the workload
aws ec2 describe-network-interfaces \
  --network-interface-ids eni-0123456789abcdef0

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0

# Network ACL associated with a subnet
aws ec2 describe-network-acls \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# VPC endpoints
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0

# Flow log configuration
aws ec2 describe-flow-logs \
  --filter Name=resource-id,Values=eni-0123456789abcdef0
~~~

Use the right Region and account profile for the resources under investigation. If workloads span multiple accounts, you need read access to configurations in the relevant accounts/VPCs; lacking read permissions does not mean a resource does not exist.

## 14. Observability and Configuration Changes

Network troubleshooting requires correlating failure timestamps with configuration changes.

Monitor:

- EC2 status checks and application health.
- VPC Flow Logs on critical ENIs/subnets/VPCs.
- Route 53 VPC Resolver query logs for VPCs using private/hybrid DNS.
- Reachability Analyzer for critical paths.
- CloudTrail for changes to route tables, SGs, NACLs, VPC endpoints, peering, and TGWs.
- CloudWatch alarms for tunnel state, NAT Gateway metrics, endpoint health, and application timeouts.

VPC Flow Logs can publish to CloudWatch Logs, S3, or Firehose. For high-traffic workloads, weigh ingestion, retention, query, and archive storage costs. Resolver query logs can reveal internal hostnames and access patterns; restrict access and retention.

When deploying network changes:

1. Save pre-change state.
2. Specify exact resource IDs and rules/routes to modify.
3. Use change reviews or IaC to inspect diffs.
4. Apply small incremental changes.
5. Re-run DNS/TCP/application tests.
6. Inspect Flow Logs and metrics.
7. Roll back if symptoms worsen.
8. Document root cause and preventive measures.

## 15. Security During Troubleshooting

Quick-fix actions can inadvertently expose services or grant excessive access.

- Never open SSH/RDP/database ports to `0.0.0.0/0` or `::/0` without specific business need and approval.
- Never add an all-traffic rule just to test a single port.
- Prefer SG references or narrow workload CIDRs.
- Use NACLs as an additional subnet control layer without copying SG rules and forgetting return ports.
- Never disable DNS Firewall or security controls broadly to resolve one hostname.
- Never replace an entire subnet's default route when only one workload fails.
- Restrict permissions to modify routes, SGs, NACLs, and Resolver rules under least privilege.
- Log audits and set expirations on temporary rules.
- After testing, remove temporary rules and verify the final configuration.

## 16. Hands-On Scenario: Diagnosing App → RDS Connectivity

An EC2 application sits in private subnet `10.20.1.0/24`. The RDS database has a private address in subnet `10.20.3.0/24`. The app connects to `orders-db.internal.example.com` on TCP port 5432.

Users report timeouts after a network policy update.

### Step 1: Verify DNS

~~~bash
dig orders-db.internal.example.com A

getent hosts orders-db.internal.example.com
~~~

It resolves to `10.20.3.25`, matching the DB's private subnet. If not, check the private hosted zone, VPC association, and Resolver logs before checking routing.

### Step 2: Check Routing

Both app and DB subnets reside in the same VPC. Route tables must contain the `local` route for the VPC CIDR. Inspect route table associations for both subnets and ensure no more-specific route diverts traffic to a wrong target.

### Step 3: Check Security Groups

- App SG outbound allows TCP 5432 to DB SG.
- DB SG inbound allows TCP 5432 from App SG.
- SGs are attached to the actual workload ENIs.
- DB is `available` and listening on port 5432.

### Step 4: Check NACLs

App and DB subnets use custom NACLs. Inspect inbound/outbound rules on both NACLs, especially return traffic to client ephemeral ports. If only port 5432 is allowed while the return ephemeral port range is denied, the TCP handshake cannot complete.

### Step 5: Use Reachability Analyzer

Select the app ENI as source, DB ENI as destination, TCP port 5432. If analysis flags an NACL or SG blocker, fix that exact rule. If the path is reachable, check Flow Logs and the service listener.

### Step 6: Runtime Testing

~~~bash
nc -vz -w 5 orders-db.internal.example.com 5432
~~~

Once TCP connects, use a database client to verify TLS, authentication, and database authorization. Never treat an open TCP port as proof the application can access data.

### Step 7: Confirm and Document

- Re-run DNS and TCP tests from the same EC2 instance.
- Verify Flow Logs show no remaining `REJECT` records for the relevant tuple.
- Confirm the application passes health checks.
- Document the SG/NACL/route change and rationale.
- Update the runbook to prevent recurrence.

## 17. Lab: Distinguishing DNS, Routing, and SG Issues

Objective: observe three distinct failure modes in a lab environment.

### Setup

- A VPC with two private subnets.
- An app EC2 instance in subnet A.
- A web/test server EC2 instance in subnet B listening on TCP 8080.
- Dedicated Security Groups for app and server.
- A private hosted zone with a record pointing to the server.
- VPC Flow Logs enabled on the lab ENIs or subnets.

### Experiment A: DNS Failure

1. Check the hostname using `dig` or `Resolve-DnsName`.
2. Modify the record in the lab private hosted zone or query a nonexistent hostname.
3. Observe `NXDOMAIN` and Resolver query logs.
4. Restore the record and check TTL/caching.

### Experiment B: Security Group Failure

1. Keep DNS and routing valid.
2. Remove the inbound TCP 8080 rule from app SG on the server SG.
3. Run `nc -vz server.internal.example.com 8080`.
4. Check Flow Logs for `REJECT` records on the relevant traffic.
5. Use Reachability Analyzer to identify the SG blocker.
6. Restore the narrowly scoped rule.

### Experiment C: Network ACL Failure

1. Create a custom NACL for the server subnet.
2. Allow inbound TCP 8080 yet temporarily block return traffic outbound.
3. Attempt a connection from the app and observe the timeout.
4. Inspect Flow Logs on both ENIs.
5. Add the return ephemeral port rule matching the client.
6. Confirm the TCP connection succeeds.

Perform this in a lab account and non-production subnets. Record every change so you can restore the initial state cleanly.

## 18. Common Mistakes

1. **Assuming networking works because EC2 is `running`.** Instance state does not prove DNS, routes, or application paths are valid.
2. **Checking only inbound Security Groups.** Clients also need matching outbound rules when egress is restricted.
3. **Forgetting the return path.** Forward reachability does not guarantee return packets make it back.
4. **Confusing SGs with NACLs.** SGs are stateful; NACLs are stateless and require rules in both directions.
5. **Opening app ports in NACLs while forgetting ephemeral ports.** TCP handshakes can time out on the return direction.
6. **Assuming SGs/NACLs can block `AmazonProvidedDNS`.** Queries to VPC Resolver require DNS Firewall for domain filtering.
7. **Forgetting VPC DNS attributes.** Private hosted zones and private DNS endpoints require proper DNS support/hostnames.
8. **Forwarding on-premises DNS to VPC CIDR+2.** Use a Resolver inbound endpoint per AWS guidance.
9. **Assuming an IGW route gives EC2 Internet access.** IPv4 instances also need a public IPv4/EIP and matching security rules.
10. **Configuring a NAT route in a private subnet when NAT sits in the wrong subnet.** NAT Gateways require a public subnet with a route to the IGW.
11. **Checking only forward routes.** VPC peering, TGW, VPN, and on-premises all require return routes.
12. **Assuming VPC peering supports transitive routing.** Peering does not automatically route through an intermediate VPC.
13. **Expecting Flow Logs to capture queries to `AmazonProvidedDNS`.** That traffic is excluded; use Route 53 VPC Resolver query logging.
14. **Treating Reachability Analyzer as a live packet test.** It performs static configuration analysis; workload testing is still required.
15. **Assuming Flow Logs `ACCEPT` means the app works.** `ACCEPT` means only that network controls permitted the packets.
16. **Ignoring IPv6.** `A`/`AAAA` records can lead down two different paths.
17. **Confusing network errors with application errors.** Connection refused, TLS failure, and HTTP 403 have distinct causes.
18. **Opening all traffic as a quick fix.** Reduces security and obscures the true root cause.
19. **Failing to check recent changes near failure onset.** CloudTrail and IaC diffs often reveal modified routes/SGs/NACLs.
20. **Skipping verification after rollback/fix.** Always re-run the exact test and save evidence.

## 19. Self-Check Questions

**1. What is the basic sequence to diagnose a VPC connectivity issue?**

Identify source/destination/protocol/port, check DNS, routes, SGs, NACLs, endpoints/middleboxes, return path, and the service listener.

**2. How does `enableDnsSupport` differ from `enableDnsHostnames`?**

DNS support enables resolution via the Amazon-provided DNS server; DNS hostnames controls public DNS hostname assignment and supports private DNS use cases. Private hosted zones/private endpoints usually require both enabled.

**3. Why might an application resolve a hostname differently from an external machine?**

Due to private hosted zones, custom DHCP DNS, forwarding rules, split-horizon DNS, or caching.

**4. When do you use a Resolver inbound endpoint?**

When on-premises DNS resolvers or other networks need to send queries into AWS to resolve private hosted zones.

**5. How do Security Groups and NACLs differ?**

Security Groups attach to network interfaces/resources, support allow rules only, and are stateful. NACLs attach to subnets, support allow/deny, are stateless, and evaluate rules in numerical order.

**6. Why are ephemeral ports needed in NACLs?**

Responses to a TCP client return to a temporary destination port chosen by the client; NACLs must allow return traffic across that port range.

**7. Does an EC2 instance in a public subnet need a public IPv4 address to reach the Internet via an IGW?**

Yes; for IPv4 it needs a public IPv4 or Elastic IP, a route to the IGW, and matching security rules.

**8. Where must a NAT Gateway be placed?**

In a public subnet with a route to the Internet Gateway; private subnets route IPv4 outbound traffic to the NAT Gateway.

**9. Which route does a route table pick when multiple routes match?**

The route with the most specific prefix (longest prefix match) is typically chosen; additional priority rules apply when routes share identical prefixes.

**10. Why does VPC peering not replace Transit Gateway in multi-VPC topologies?**

Peering lacks transitive routing; Transit Gateway provides hub routing across multiple VPCs and connected networks.

**11. Does Reachability Analyzer send real packets?**

No. It is static configuration analysis to trace virtual paths and find component blockers.

**12. Do Flow Logs record packet payloads?**

No. Flow Logs record metadata such as IPs, ports, protocols, bytes, packets, and actions.

**13. What does `REJECT` in Flow Logs mean?**

Traffic was denied—for example, by an SG/NACL or packets arriving after connection closure; cross-check the tuple and configuration.

**14. Why do DNS queries not appear in VPC Flow Logs?**

Traffic to/from `AmazonProvidedDNS` is excluded from Flow Logs; use Route 53 VPC Resolver query logging.

**15. If TCP connects yet HTTP returns 403, is it still a routing error?**

Usually the network path and TCP already work; check IAM, application authorization, endpoint policies, WAF, or resource policies.

**16. When should you use a VPC endpoint instead of a NAT Gateway?**

When workloads access supported AWS services over private connectivity, reducing Internet/NAT dependency and enforcing access via endpoint policies.

## 20. Production Checklist

- [ ] Source, destination, protocol, port, direction, and IP family are documented.
- [ ] DNS `A`/`AAAA` records return the expected hostnames and environment IPs.
- [ ] VPC DNS attributes match private hosted zone/private endpoint requirements.
- [ ] Resolver rules, private hosted zone associations, and DHCP option sets are verified.
- [ ] Hybrid DNS uses Resolver inbound/outbound endpoints in the right direction.
- [ ] Subnets are associated with the intended route tables.
- [ ] Routes are active with no blackholes or unintended more-specific prefixes.
- [ ] Return routes exist across all VPC/TGW/VPN/on-premises networks.
- [ ] Public IPv4/IPv6 and IGW/NAT/Egress-only IGW are configured properly.
- [ ] VPC endpoint DNS, endpoint SGs, routes, and endpoint policies are correct.
- [ ] SGs are attached to the exact ENIs and allow only required protocols/ports/sources.
- [ ] NACLs are verified bidirectionally with appropriate ephemeral port ranges.
- [ ] Peering/TGW attachments and route table associations/propagations are correct.
- [ ] Reachability Analyzer has verified critical paths.
- [ ] VPC Flow Logs are enabled at required scopes with defined retention.
- [ ] Resolver query logs are enabled for VPCs needing DNS diagnostics.
- [ ] CloudTrail can trace network configuration changes.
- [ ] Runtime tests from real workloads verify DNS/TCP/TLS/application health checks.
- [ ] Dashboards monitor timeouts, DNS errors, `REJECT` counts, NAT/endpoint health, and tunnel states.
- [ ] Rollback runbooks and cleanup procedures exist for temporary rules.
- [ ] Periodic audits review `0.0.0.0/0`/`::/0` rules, unused routes, and obsolete SGs/NACLs.

## References

- [What is Route 53 VPC Resolver?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver.html)
- [Understanding Amazon DNS and VPC DNS attributes](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html)
- [View and update DNS attributes for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns-updating.html)
- [Resolving DNS queries between VPCs and your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-DSN-queries-to-vpc.html)
- [How Resolver endpoints forward queries from your VPC to your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-forward-vpc-to-network.html)
- [How DNS resolvers on your network forward queries to Resolver endpoints](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-forward-network-to-vpc.html)
- [Route 53 VPC Resolver query logging](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-query-logs.html)
- [Resolver DNS Firewall](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-overview.html)
- [Configure subnet route tables](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html)
- [How route priority works](https://docs.aws.amazon.com/vpc/latest/userguide/route-tables-priority.html)
- [Enable internet access for a VPC using an internet gateway](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html)
- [Example routing options](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-options.html)
- [Control traffic using security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- [Security group rules and security group referencing](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
- [Control subnet traffic with network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html)
- [Custom network ACLs and ephemeral ports](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html)
- [Logging IP traffic using VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [VPC Flow Logs record examples](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-records-examples.html)
- [VPC Flow Logs limitations](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-limitations.html)
- [Troubleshoot VPC reachability issues](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-routes-troubleshoot.html)
- [Troubleshoot reachability using Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/userguide/reachability-analyzer.html)
- [How Reachability Analyzer works](https://docs.aws.amazon.com/vpc/latest/reachability/how-reachability-analyzer-works.html)
- [Reachability Analyzer explanation codes](https://docs.aws.amazon.com/vpc/latest/reachability/explanation-codes.html)
- [Troubleshoot VPC peering connections](https://docs.aws.amazon.com/vpc/latest/peering/troubleshoot-vpc-peering-connections.html)
- [Configure an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/interface-endpoints.html)
- [Monitoring your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/monitoring.html)
