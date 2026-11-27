# Protecting Egress Flows and Accessing Services via Endpoints

In a VPC, **egress** is traffic initiated by resources inside the network toward destinations outside the subnet or VPC. Destinations can be the Internet, on-premises networks, other VPCs, or AWS services such as Amazon S3, AWS Secrets Manager, and Amazon CloudWatch. Good egress design answers two questions: which paths is traffic allowed to take, and which exact destinations are workloads permitted to reach?

VPC endpoints allow workloads to call supported AWS services over the AWS private network without traversing an Internet Gateway or NAT Gateway. Combining endpoints with route tables, security groups, endpoint policies, IAM, and logging lets operations teams reduce attack surface and enforce clearer access boundaries.

## Learning Objectives

After this lesson, you can:

- Describe the path of an egress connection and distinguish the roles of route tables, security groups, network ACLs, NAT Gateways, and firewalls.
- Choose the appropriate egress mechanism for IPv4, IPv6, and environments requiring centralized inspection.
- Distinguish Gateway endpoints, Interface endpoints, and AWS PrivateLink.
- Design endpoint access controls using security groups, endpoint policies, IAM policies, and resource policies.
- Troubleshoot DNS, routing, permissions, and logs when a workload cannot reach a service.

## 1. Understanding Egress Traffic Paths

An outbound connection typically originates at the ENI of an EC2 instance, ECS task, EKS pod, or another resource in a subnet. AWS evaluates control layers along the path, then the route table selects the next hop. Depending on the architecture, the next hop can be a NAT Gateway, Internet Gateway, egress-only Internet Gateway, VPC endpoint, Transit Gateway, or firewall endpoint.

For example, an EC2 instance in a private subnet calls a public Internet API:

1. The application opens a TCP connection to the destination address, typically on port 443.
2. The ENI's security group checks outbound rules. Because security groups are stateful, return traffic for that connection is automatically allowed.
3. The subnet's Network ACL checks outbound traffic. Because Network ACLs are stateless, matching rules are required for both outbound and return directions.
4. The subnet's route table selects the most specific matching route. The IPv4 default route is typically `0.0.0.0/0` pointing to a NAT Gateway.
5. The NAT Gateway translates the private IPv4 source address to the NAT Gateway's public address to connect to the Internet.
6. Return packets arrive back at the NAT Gateway, are mapped back to the workload's address and port, and enter the subnet.

Actual paths can be more complex when centralized firewalls, proxies, Transit Gateway, or multiple VPCs are involved. During design, trace every hop and ensure symmetric forward and return paths as required by stateful inspection devices.

### Control Layers and Responsibilities

| Component | Control Scope | Primary Role |
|---|---|---|
| Route table | Subnet | Selects the next hop for destination addresses; does not authenticate identities or inspect app payloads |
| Security group | ENI or supported resource | Stateful inbound/outbound filtering by protocol, port, and source/destination |
| Network ACL | Subnet | Stateless filtering by IP, protocol, and port; must allow both forward and return directions |
| NAT Gateway | IPv4 path | Lets private resources initiate outbound connections via address translation; not an application-filtering firewall |
| VPC endpoint | Connections to supported services | Routes traffic to services over the AWS private network |
| AWS Network Firewall | Locations routed through the firewall | Inspects and filters network traffic via stateless/stateful rules |
| Route 53 Resolver DNS Firewall | DNS queries via Resolver | Allows or blocks domain queries per rule groups |
| IAM and resource policies | AWS identities and resources | Determines which APIs/actions a principal can perform |

No single component replaces all the others. Route tables choose paths; security groups and network ACLs filter IP traffic; IAM controls actions on AWS services.

## 2. Common Ways to Provide Egress

### 2.1. Public Subnet via an Internet Gateway

An IPv4 resource in a public subnet can reach the Internet directly when all of these conditions hold:

- The subnet's route table has a `0.0.0.0/0` route to an Internet Gateway attached to the VPC.
- The resource has a public IPv4 address or an associated Elastic IP.
- Security groups, network ACLs, and OS configuration permit the connection.

The label "public subnet" only reflects that the route table has a route to an Internet Gateway. An EC2 instance without a public IPv4 address still does not automatically have a direct IPv4 path to the Internet.

Placing resources directly in a public subnet is usually appropriate for components that must accept inbound Internet connections, such as public load balancers. For application servers, workers, and databases, private subnets are generally the safer choice.

### 2.2. Private Subnet IPv4 Egress via a NAT Gateway

A public NAT Gateway is typically placed in a public subnet. The public subnet's route table must have a route to the Internet Gateway; the private subnet's route table points the IPv4 default route to the NAT Gateway.

~~~text
Private subnet
  EC2 / ECS task
       |
  Route 0.0.0.0/0
       |
  Public NAT Gateway
       |
  Internet Gateway
       |
    Internet
~~~

A NAT Gateway allows workloads in private subnets to initiate outbound connections. External hosts cannot initiate new connections to the workload through the NAT Gateway simply by knowing the NAT Gateway's public address.

A NAT Gateway **is not an application-layer destination filter**. It does not provide domain allowlist policies or HTTP content inspection like an application-aware proxy or firewall. If requirements restrict workloads to calling only specific services, combine NAT with security groups, AWS Network Firewall, proxies, and application-layer policies where appropriate.

In multi-Availability Zone environments, deploy a NAT Gateway in each AZ and have private subnets prefer the NAT Gateway in the same AZ. This reduces single-AZ dependency and avoids unnecessary cross-AZ traffic. Routing to a NAT Gateway in another AZ allows workloads to keep working if a local NAT Gateway fails, but the path and cross-AZ data transfer charges must be accounted for.

### 2.3. Private Subnet IPv6 Egress via an Egress-Only Internet Gateway

IPv6 does not use NAT Gateways the way IPv4 typically does. If workloads have global IPv6 addresses and only need to initiate outbound connections to the Internet, use an egress-only Internet Gateway.

The route table includes a `::/0` route pointing to the egress-only Internet Gateway. This component allows outbound IPv6 connections and return traffic for internally initiated connections while blocking new inbound IPv6 connections initiated from the Internet into the VPC.

Security groups and network ACLs must still be configured properly. An egress-only Internet Gateway does not replace those control layers.

### 2.4. Centralized Egress Through a Firewall or Proxy

Organizations can route outbound traffic through AWS Network Firewall or a centralized proxy to enforce shared policies, logging, and traffic inspection. Architectures often use Transit Gateway or route tables designed to steer workload traffic through the firewall before reaching a NAT Gateway or private destination.

~~~mermaid
flowchart LR
    A["Workload in private subnet"] --> B["Route table"]
    B --> C["Firewall endpoint"]
    C --> D{"Destination allowed?"}
    D -->|Yes| E["NAT Gateway or private route"]
    D -->|No| F["Block and log"]
    E --> G["Internet or destination network"]
~~~

When deploying, verify:

- Every outbound route requiring inspection actually traverses the firewall.
- Return paths return to the same stateful device, avoiding asymmetric routing.
- Firewall endpoints are deployed and routed properly across all AZs needing protection.
- Policies permit DNS, OS updates, AWS services, and required application dependencies.
- Logs are delivered to appropriate storage and monitoring targets.

Route 53 Resolver DNS Firewall can block queries to disallowed domains when workloads use Route 53 Resolver. It does not replace a network firewall: applications can still connect directly by IP address or use another DNS resolver if the architecture does not block those paths.

## 3. Layered Egress Controls

An effective egress policy typically combines these layers:

**Security groups:** Restrict outbound traffic by protocol, port, and destination. For applications needing only HTTPS to an endpoint in the same VPC, allow TCP 443 to the security group attached to the Interface endpoint. Security-group-referencing rules avoid maintaining lists of endpoint ENI IP addresses.

**Network ACLs:** Provide an additional filtering boundary at the subnet level. Because NACLs are stateless, allow the service port outbound and appropriate ephemeral ports inbound for return traffic, and consider the reverse direction as well. Network ACLs do not understand IAM identities or API names.

**Route tables:** Direct traffic to endpoints, NAT, firewalls, or connected networks. More specific routes take precedence over default routes. Route tables cannot themselves block a request by domain name or API action.

**AWS Network Firewall or proxy:** Enforce network policies and deeper inspection when security requirements demand filtering by protocol, domain, or flow attributes. Verify actual visibility against the TLS and application protocols in use.

**DNS Firewall:** Restrict which domains workloads can resolve via Route 53 Resolver. Control alternative DNS paths if consistent policy enforcement is required.

**IAM and resource policies:** Restrict which APIs/actions a principal may invoke on AWS services. For example, an EC2 instance may have a network path to S3 while its IAM role is permitted to read only one specific bucket.

**Application policies:** Validate inputs, restrict outbound targets, and manage timeouts/retries. Network policies do not replace application-layer data validation or authentication.

AWS WAF primarily protects web applications and APIs from inbound HTTP/S traffic targeting supported resources. Do not treat AWS WAF as a general-purpose egress filter across all protocols.

## 4. Accessing AWS Services via VPC Endpoints

A VPC endpoint establishes a connection path between a VPC and a supported service or resource. With the appropriate endpoint, workloads can access services over the AWS private network without requiring an Internet route for those requests.

Common benefits:

- Reduces reliance on NAT Gateways for traffic to supported AWS services.
- Minimizes dependency on Internet Gateways and public IP addresses.
- Enables constraining access via endpoint policies, IAM policies, and resource policies.
- Reduces the number of open egress paths and simplifies network design.

VPC endpoints do not automatically isolate the entire VPC into a purely private network. Other flows can still exit via Internet or connected network routes if route tables permit them.

### 4.1. Gateway Endpoints

Gateway endpoints are currently used for Amazon S3 and Amazon DynamoDB. When creating the endpoint, select the route tables to associate. AWS adds a route using the service's managed prefix list so traffic to the service's address ranges routes through the gateway endpoint.

Characteristics:

- Does not create ENIs in subnets.
- Does not attach security groups directly to the endpoint.
- Must be associated with route tables of subnets needing access.
- An endpoint policy can restrict actions and resources accessed through the endpoint if supported by the service.
- Gateway endpoints require neither a NAT Gateway nor an Internet Gateway for service traffic traversing the endpoint.
- Gateway endpoints are scoped to a Region and VPC; they are not a general-purpose path from on-premises networks over VPN or Direct Connect.

Example: an EC2 instance in a private subnet needs to read objects from an S3 bucket. Associating an S3 Gateway endpoint with the private subnet's route table routes S3 requests through the endpoint. The EC2 instance still needs an IAM role permitting `s3:GetObject`, and the bucket policy can further restrict principals or access conditions.

### 4.2. Interface Endpoints and AWS PrivateLink

Interface endpoints are powered by AWS PrivateLink. AWS provisions one or more elastic network interfaces (ENIs) in the subnets you select. Each ENI receives a private IP address for workloads to connect to the service.

Characteristics:

- Usable for many AWS services, partner-provided services, and organization-published endpoint services, depending on service support.
- Supports attaching security groups to endpoint ENIs.
- Supports enabling Private DNS so standard AWS service hostnames resolve to the endpoint's private IPs inside the VPC.
- Select subnets across multiple served AZs for high availability.
- Typically incurs hourly charges per endpoint/AZ and data-processing fees; check pricing by Region and service.

Example: an application in a private subnet calls AWS Secrets Manager. Create an Interface endpoint for Secrets Manager in the required AZs, enable Private DNS, and allow TCP 443 from the application security group to the endpoint security group. The application continues calling the SDK with the standard service hostname; VPC DNS resolves that hostname to the endpoint's private address when properly configured.

PrivateLink also enables a provider to publish its own service as an endpoint service. The provider typically places the service behind a Network Load Balancer or Gateway Load Balancer per supported patterns; the consumer creates an Interface endpoint in its own VPC. Both parties exchange service traffic without exposing the service to the Internet or peering the entirety of both VPCs.

### 4.3. Comparing Gateway Endpoints and Interface Endpoints

| Criterion | Gateway Endpoint | Interface Endpoint |
|---|---|---|
| Mechanism | Route table entry using a managed prefix list | ENI with private IP addresses in subnets |
| Typical services | S3, DynamoDB | Secrets Manager, CloudWatch, Systems Manager, and many other services |
| Security group | Not attached directly | Attached to endpoint ENIs |
| Private DNS | Private DNS not needed for gateway endpoint routing | Private DNS can be enabled for service hostnames |
| Key settings | Select VPC and route tables | Select VPC, subnets, security groups, and DNS options |
| Cost | No separate endpoint charge for Gateway endpoints; service and data charges still apply | Typically billed per endpoint/AZ hour and GB processed |
| Usage scope | Primarily from resources in the VPC with associated route tables | More flexible across AWS services and PrivateLink endpoint services |

Supported service lists, endpoint types, and availability vary by Region. Before deploying, verify that the service supports the desired endpoint type and review service-specific guidance.

## 5. Protecting Endpoints with Policies and Networking

A well-functioning endpoint requires both network reachability and access permissions. Verify each layer in the following order.

### 5.1. Endpoint Policies

An endpoint policy is a resource policy attached to a VPC endpoint to restrict which principals, actions, or resources may pass through the endpoint. An endpoint policy does not grant IAM permissions to callers and does not override an explicit Deny from an IAM policy or resource policy. The service must support endpoint policies for this setting to take effect.

Example S3 endpoint policy allowing reads only from the `company-artifacts` bucket:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReadObjectsFromApprovedBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-artifacts/*"
    },
    {
      "Sid": "AllowListApprovedBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::company-artifacts"
    }
  ]
}
~~~

This example restricts requests traversing the endpoint. The workload's IAM role still needs corresponding permissions, and the bucket policy can enforce additional conditions. If the workload has an alternative path to S3, the endpoint policy does not automatically govern requests taking that other path.

In multi-account environments, consider restricting principals or adding account conditions instead of relying on `Principal: "*"` when governance requires tighter bounds.

### 5.2. IAM Policies and Resource Policies

IAM policies attached to roles or users determine which actions an identity may invoke. Resource policies attached to resources, such as S3 bucket policies, determine who may access the resource and under what conditions.

For example, an application role only needs to read objects under a specific prefix. Scope `s3:GetObject` to the required prefix ARN and grant `s3:ListBucket` only when listing is genuinely needed. Avoid granting `s3:*` or permissions across all buckets merely to work around access errors.

### 5.3. Interface Endpoint Security Groups

Interface endpoints have ENIs, so the security group attached to the endpoint controls traffic entering those ENIs. For HTTPS, a typical configuration is:

- The application security group allows outbound TCP 443 to the endpoint security group.
- The endpoint security group allows inbound TCP 443 from the application security group.
- Network ACLs on both subnets allow request and return directions, including required ephemeral ports.

If the application and endpoint reside in different VPCs or connected networks, verify security group referencing support across that connectivity model; if unsupported, use appropriate CIDRs and manage changes carefully.

### 5.4. DNS and Private DNS

For Interface endpoints, enabling Private DNS lets workloads use familiar service hostnames instead of managing endpoint-specific hostnames. For this to work, the VPC must have DNS resolution and DNS hostnames enabled per service requirements.

If DNS returns public addresses instead of the endpoint's private addresses, check:

- Whether Private DNS is enabled on the endpoint.
- Whether the service and Region support Private DNS.
- Whether VPC DNS resolution and DNS hostnames are enabled.
- Whether workloads use a custom DNS resolver or stale local caches.
- Whether a private hosted zone or DNS configuration conflicts with the service hostname.

Gateway endpoints for S3/DynamoDB operate via route table routes and managed prefix lists; they do not require ENIs or Private DNS like Interface endpoints.

## 6. Designing an Access Flow

Use this workflow for each workload type:

1. **Identify destinations:** Does the workload call the Internet, AWS services, internal networks, or partner private services?
2. **Identify protocols:** Specify TCP/UDP, ports, IPv4/IPv6, hostnames, and Regions. Do not open all ports if the application only needs HTTPS.
3. **Select the path:** Use Gateway endpoints for S3/DynamoDB where suitable; Interface endpoints for PrivateLink-supported services; NAT for general IPv4 egress; egress-only Internet Gateways for IPv6 outbound; firewalls/proxies when centralized inspection is required.
4. **Restrict sources:** Allow only required workloads or security groups to reach the endpoint. Tighten overly broad outbound rules in related security groups.
5. **Restrict service permissions:** Grant minimal IAM actions and resources; add endpoint policies and resource policies when supported and needed by security requirements.
6. **Verify DNS:** Confirm hostnames resolve per design, especially for Interface endpoints with Private DNS.
7. **Enable observability:** Use VPC Flow Logs to view accepted or rejected IP flows; Network Firewall logs to investigate rule hits; Route 53 Resolver query logging for DNS queries; and CloudTrail to audit AWS API calls.
8. **Test both allowed and denied paths:** Confirm workloads reach required services while failing to reach resources or destinations outside permitted scope.
9. **Evaluate availability and cost:** Check per-AZ endpoints/NAT, cross-AZ traffic, data charges, and endpoint counts.

## 7. Implementation Examples

### 7.1. Creating an S3 Gateway Endpoint for Private Subnets

The AWS CLI example below creates an S3 Gateway endpoint in a VPC and associates it with two private subnet route tables. Replace placeholders with actual IDs in the same Region.

~~~bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.<REGION>.s3 \
  --vpc-endpoint-type Gateway \
  --route-table-ids <PRIVATE_ROUTE_TABLE_ID_1> <PRIVATE_ROUTE_TABLE_ID_2>
~~~

After creation, verify the endpoint state is `available`, route tables contain the S3 prefix list route, and workloads hold appropriate IAM permissions. To restrict buckets through the endpoint, attach a reviewed endpoint policy.

### 7.2. Creating a Secrets Manager Interface Endpoint

The example below creates an Interface endpoint for Secrets Manager, places ENIs in two subnets, and enables Private DNS:

~~~bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.<REGION>.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids <PRIVATE_SUBNET_ID_A> <PRIVATE_SUBNET_ID_B> \
  --security-group-ids <ENDPOINT_SECURITY_GROUP_ID> \
  --private-dns-enabled
~~~

The endpoint security group must permit inbound TCP 443 from workloads needing access. Workload security groups must permit matching outbound traffic. The application role needs minimal Secrets Manager actions such as `secretsmanager:GetSecretValue` on the specific secret. If the secret uses a customer managed KMS key, also verify decryption permissions in both the key policy and IAM policy.

### 7.3. Testing from the Workload

You can verify DNS resolution and TCP 443 connectivity from the application environment:

~~~bash
nslookup secretsmanager.<REGION>.amazonaws.com
curl -I https://secretsmanager.<REGION>.amazonaws.com
~~~

DNS output should match the Private DNS design. The HTTP check only tests network/HTTP reachability; it does not prove the principal is authorized to call the API. To verify permissions, invoke the API with the AWS CLI or SDK using the workload's role against an authorized secret. Never print secret values to logs or terminals while testing.

## 8. Observability and Troubleshooting

When a workload fails to call a service, classify the error before changing rules. Timeouts typically suggest network path, DNS, or firewall issues; `AccessDenied` responses typically indicate requests reached the service but lack permissions or hit a policy deny. Treat these as directional clues, not absolute conclusions.

| Symptom | Layer to Inspect | How to Verify |
|---|---|---|
| Timeout calling service | Route tables, security groups, network ACLs, firewalls | Inspect subnet routes, workload outbound, endpoint ENI inbound, and Flow Logs |
| Hostname resolves to unexpected IP | Private DNS, VPC DNS, custom resolvers | Run `nslookup` or `dig`; verify endpoint and DNS configuration |
| Interface endpoint unreachable | Endpoint state, subnets, AZs, security groups | Confirm endpoint is `available`, ENIs exist, and TCP 443 is allowed |
| S3 requests go via NAT instead of Gateway endpoint | Route tables, prefix lists, subnet associations | Confirm the route table attached to the subnet contains the S3 prefix list route |
| API returns `AccessDenied` | IAM, endpoint policy, resource policy, KMS key policy | Check principal, action, ARN, conditions, and explicit Denies |
| Only one AZ fails | Per-AZ endpoint ENIs, NAT/firewalls, route tables | Compare subnets, routes, and endpoint ENIs across AZs |
| DNS resolves but connection fails | Security groups, NACLs, routes, firewalls | Verify TCP 443 and ephemeral ports for return traffic |
| Network connects but API fails | Authentication, IAM, resource policy, request payload | Inspect CloudTrail and API error messages |

Observability sources play distinct roles:

- **VPC Flow Logs** record IP flow metadata at ENIs, subnets, or VPCs. They help locate `ACCEPT` or `REJECT` flows, though they do not include full URLs, request payloads, or IAM identities of API calls.
- **AWS Network Firewall logs** aid investigation of traffic traversing the firewall and matched rules.
- **Route 53 Resolver query logs** capture DNS queries sent to the Resolver, useful when investigating blocked domains or misresolution.
- **AWS CloudTrail** records API activity across many AWS services, identifying principals, actions, resources, and outcomes.
- **CloudWatch metrics** for NAT Gateways and network components detect traffic shifts, port allocation errors, or dropped packets. Select metrics matching the components actually deployed.

Do not open all outbound traffic just to debug an error. Change one layer at a time based on a clear hypothesis, retest, and narrow configurations once root cause is confirmed.

## 9. Common Design Mistakes

**Assuming a NAT Gateway filters domain names.** A NAT Gateway performs address translation for outbound IPv4 connections. Controlling domains or application content requires an appropriate firewall/proxy and DNS controls.

**Creating an endpoint while forgetting route tables or DNS.** Gateway endpoints must attach to the right route tables. Interface endpoints require proper DNS and security groups; merely creating an endpoint does not guarantee applications will use it.

**Assuming an endpoint policy grants access permissions.** An endpoint policy only filters requests passing through the endpoint. IAM policies, resource policies, and key policies can still deny requests.

**Opening an endpoint security group to the entire VPC.** This can let unrelated workloads access the endpoint at the network layer. Allow only the required security groups or CIDRs.

**Forgetting stateless Network ACLs.** Allowing outbound port 443 while blocking inbound ephemeral ports can prevent connections from completing.

**Using a single NAT Gateway across all AZs without assessing impact.** This creates a dependency on the NAT Gateway's AZ and can incur cross-AZ traffic. Weigh cost savings against availability requirements.

**Thinking VPC endpoints replace all egress.** Endpoints serve only supported services/resources. Internet destinations or services lacking endpoints still require separate paths governed by policy.

**Failing to inspect alternative paths.** An endpoint policy does not stop requests flowing over NAT or another network path if routes and permissions allow it. If policy mandates that all access to a service traverse the endpoint, align IAM/resource policies and egress routes to prevent bypasses.

## 10. Scenario Exercise

An order-processing system runs on EC2 in private subnets. The application must:

- Read configuration files from a specific S3 bucket.
- Fetch database credentials from Secrets Manager.
- Send notifications to a public partner API over HTTPS.
- Never allow servers to accept new inbound connections directly from the Internet.

Propose an architecture and explain your choices.

A sound approach:

1. Create an S3 Gateway endpoint and attach it to the private subnet route tables where the application runs.
2. Create a Secrets Manager Interface endpoint in the served AZs, enable Private DNS, and restrict TCP 443 from the application security group.
3. Assign an IAM role to EC2 granting read access only to objects in the required bucket/prefix and fetching only the required secret; constrain endpoint policies and bucket/secret resource policies where appropriate.
4. Route connections to the partner API through a NAT Gateway or egress firewall/proxy. If domain allowlisting, logging, or centralized inspection is required, place the firewall/proxy in the path and confirm all inspected routes traverse it.
5. Assign no public IPv4 addresses to EC2 instances and maintain no public inbound routes to instances. Security groups accept inbound traffic only from required internal components and restrict outbound per requirements.
6. Enable VPC Flow Logs, CloudTrail, and corresponding firewall/DNS logs; test both allowed and denied access paths.

When evaluating the design, explicitly verify that S3 and Secrets Manager requests traverse endpoints, partner API requests traverse controlled Internet egress, and IAM permissions remain enforced independently of network paths.

## 11. Pre-Production Operations Checklist

- [ ] Each workload has an explicit list of outbound destinations, protocols, and ports.
- [ ] Every subnet route table points to the right endpoint, NAT, firewall, or gateway.
- [ ] Gateway endpoints are associated with all required route tables.
- [ ] Interface endpoints have ENIs in served AZs and source-restricted security groups.
- [ ] Private DNS is enabled and verified by queries from workloads.
- [ ] Security groups and network ACLs allow proper request and response directions.
- [ ] IAM, endpoint policies, resource policies, and KMS key policies grant no broader permissions than required.
- [ ] Alternative egress paths cannot bypass endpoint policies.
- [ ] Firewall/DNS logging, VPC Flow Logs, and CloudTrail are configured per investigative needs.
- [ ] Allowed requests, denied requests, and single-AZ failure resilience have been tested.
- [ ] Endpoint, NAT, firewall, and cross-AZ data transfer costs have been evaluated.

## Conclusion

Secure egress design begins with knowing where workloads must connect and selecting the right path for each destination type. NAT Gateways serve general IPv4 outbound needs; egress-only Internet Gateways support IPv6 outbound; firewalls or proxies provide centralized inspection; VPC endpoints keep supported AWS service traffic on private networks. By combining network routes with security groups, network ACLs, DNS, endpoint policies, IAM, and resource policies, you control both the network path and the actions workloads are permitted to perform.
