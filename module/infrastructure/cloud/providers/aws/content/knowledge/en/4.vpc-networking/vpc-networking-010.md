# Gateway Endpoints and Interface Endpoints

> **Chapter:** VPC Networking  
> **Module:** CLOUD_PROVIDERS_AWS — explore Region/AZ infrastructure, IAM, VPC, and compute, storage, database, integration, and serverless services to design secure, observable, resilient, and cost-controlled applications.

## Learning Objectives

In an Amazon VPC, an EC2 instance or application in a private subnet often needs to call APIs of Amazon S3, DynamoDB, Systems Manager, Secrets Manager, CloudWatch, or other services. If all of that traffic goes through a NAT Gateway and the Internet, the architecture can incur unnecessary cost, depend needlessly on egress paths, and become harder to scope by service. **VPC endpoints** provide a private connection path to supported services, enabling access designs aligned with private networking and security policies.

After completing this lesson, you will be able to:

1. Explain what **gateway endpoints** and **interface endpoints** are, and how each forwards traffic from a VPC.
2. Choose the right endpoint type for S3, DynamoDB, and services supporting AWS PrivateLink.
3. Distinguish the roles of **route tables**, **DNS**, **ENIs**, **security groups**, **IAM policies**, **endpoint policies**, and **resource policies**.
4. Create and test endpoints using the AWS Console or AWS CLI in a sandbox; explain how to clean up resources and where costs arise.
5. Diagnose common errors: timeouts, DNS returning unexpected addresses, `AccessDenied`, wrong Region, misconfigured route tables or security groups.
6. Build a multi-AZ design and explain VPC endpoint limitations when accessed from other VPCs or on-premises networks.

## 1. What Problem Do VPC Endpoints Solve?

Suppose an application runs in a **private subnet** with no public IPv4 and no default route to the Internet. The application still needs to download images from S3, read parameters from AWS Systems Manager, and call internal AWS APIs. There are two common connectivity approaches:

- Configure an **egress path via a NAT Gateway** and use standard public AWS DNS/API endpoints.
- Create a **VPC endpoint** for the supported service to connect privately from inside the VPC or connected networks.

A VPC endpoint is a networking component; it **does not grant IAM permissions**, **does not encrypt data on behalf of the application**, **does not block all other Internet traffic**, and **does not guarantee every AWS service has an endpoint**. API authorization is still evaluated through IAM/resource policies and other constraints.

### 1.1. Two Common Traffic Paths

~~~mermaid
flowchart TD
    A[Application in private subnet] --> B{Target destination}
    B -->|S3 or DynamoDB via gateway endpoint| C[Route table: AWS-managed prefix list]
    C --> D[Gateway VPC endpoint]
    D --> E[S3 / DynamoDB]
    B -->|Service supporting AWS PrivateLink| F[Service DNS: endpoint private IP]
    F --> G[Interface VPC endpoint: ENI + security group]
    G --> H[AWS service / endpoint service]
    B -->|Destination outside endpoint scope| I[NAT Gateway / appropriate egress if configured]
    I --> J[Internet or public service endpoint]
~~~

**Key idea:** gateway endpoints rely primarily on **routes in a route table**; interface endpoints rely primarily on **ENI private IP addresses**, typically discovered by applications via **DNS**. Both are configured within a single Region and must be compatible with the specific service.

### 1.2. Distinguishing Endpoint Types

AWS offers additional endpoint types for other purposes (such as **Gateway Load Balancer endpoints** for traffic inspection architectures). This lesson compares only the two types commonly used to access services:

| Criterion | Gateway Endpoint | Interface Endpoint |
|---|---|---|
| Mechanism | Route to the service via **route table** and AWS-managed prefix list | **Elastic Network Interface (ENI)** with a private IP in a subnet |
| Typical services | **Amazon S3, Amazon DynamoDB** | Many AWS services such as Systems Manager, Secrets Manager, CloudWatch Logs; partner or custom endpoint services; S3 also offers an interface option |
| Placement configuration | VPC + route tables to use it | VPC + subnets in supported AZs + security groups |
| Changes DNS resolution? | **Does not require** changing service DNS to a private IP | Typically enables **private DNS**; or uses endpoint-specific DNS names |
| Security group attached to endpoint | No | Yes, attached to the ENI |
| Access via peering, Transit Gateway, VPN, Direct Connect | Cannot use another VPC's gateway endpoint across these links | Possible, if service, routing, DNS, and policies allow |
| Endpoint fees | No charge to create/use a gateway endpoint | Typically billed **hourly per AZ** and **per GB of data processed** |
| Permission controls | Endpoint policy; IAM and resource policies also apply | IAM/resource policies; endpoint policy if supported by the service |
| Common use case | EC2/Lambda in a VPC accessing S3/DynamoDB in the same Region | Workloads in a VPC calling AWS APIs from private subnets without traversing NAT |

Service rules, AZ support, IP address types, DNS options, and pricing can change. Before deploying, verify the actual **service name** and **endpoint type** in your target Region.

## 2. Gateway Endpoints: Private Routing to S3 and DynamoDB

### 2.1. Route Table–Based Operation

A **gateway VPC endpoint** is created in a VPC and associated with one or more **route tables**. AWS adds a route for an **AWS-managed prefix list** containing the target service's Regional IP ranges, with the endpoint ID as target.

~~~mermaid
flowchart LR
    A[EC2 in private subnet] --> B[Subnet route table]
    B -->|Destination: pl-... S3 prefix list| C[Target: vpce-... Gateway endpoint]
    C --> D[Amazon S3 in same Region]
    B -->|0.0.0.0/0 if present| E[NAT Gateway / Internet egress]
~~~

Example route table entries:

| Destination | Target | Role |
|---|---|---|
| `10.20.0.0/16` | `local` | Intra-VPC communication |
| `pl-xxxxxxxx` | `vpce-xxxxxxxx` | Path to S3 via gateway endpoint |
| `0.0.0.0/0` | `nat-xxxxxxxx` | Other Internet egress path, if architecture requires |

A **prefix list** is an AWS-managed set of CIDRs for a service. The S3 IP address returned by DNS may still be a public service IP, but because the destination matches the prefix list route, traffic routes through the gateway endpoint, **requiring neither a public IP on EC2 nor a NAT Gateway** for that connection.

The gateway endpoint route appears only in route tables **associated with the endpoint**. If an app's subnet uses an unassociated route table, traffic continues via NAT (if present) or fails. Also verify whether higher-priority routes alter the path.

### 2.2. Scope Limitations

- Gateway endpoints serve **S3 and DynamoDB**, using Regional service names such as `com.amazonaws.ap-southeast-1.s3` or `com.amazonaws.ap-southeast-1.dynamodb`.
- **The VPC containing the gateway endpoint** is the direct access boundary. You cannot use that endpoint over VPC peering, Transit Gateway, Site-to-Site VPN, or Direct Connect from another VPC or network.
- Gateway endpoints operate **within the same Region** by design. For S3 buckets in another Region, inspect alternative paths and access methods; do not assume every S3 request uses the gateway endpoint.
- Gateway endpoints **do not create ENIs** and **have no directly attached security groups**. EC2 security groups, network ACLs, and service policies still apply.
- Gateway endpoint availability is managed by AWS; you do not choose per-AZ ENIs as with interface endpoints.

### 2.3. Endpoint Policy for S3

When creating a gateway endpoint, you can leave the **default endpoint policy** (allowing broad access at the endpoint layer) or attach a **custom endpoint policy** to restrict actions/resources traversing the endpoint.

Example endpoint policy **allowing read access only to a single lab bucket** `aws-lab-dev-data-example`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTrainingBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::aws-lab-dev-data-example"
    },
    {
      "Sid": "ReadTrainingObjects",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-dev-data-example/*"
    }
  ]
}
~~~

**`Principal: "*"` in an endpoint policy does not grant public read access to the bucket.** An endpoint policy only filters requests **passing through that endpoint**; IAM policies, bucket policies, and other authorization layers must still allow access. If a user has another network path to S3, the endpoint policy **does not restrict paths outside the endpoint**.

Key points to remember:

- `s3:ListBucket` applies to the **bucket** ARN, whereas `s3:GetObject` applies to **object** ARNs.
- Endpoint policies apply only to traffic passing through the endpoint, not account-wide.
- To require a bucket to accept requests only via an approved endpoint, consider `aws:SourceVpce` in the **bucket policy**, but first evaluate impacts on the AWS Console, automation, and AWS services accessing the bucket on behalf of users.

## 3. Interface Endpoints: Private IP Connectivity via AWS PrivateLink

### 3.1. ENIs Created in Subnets

An **Interface VPC endpoint** uses **AWS PrivateLink**. When creating an interface endpoint, you select one or more subnets in the VPC—typically **at most one subnet per AZ** for that endpoint. AWS creates an **endpoint ENI** in each chosen subnet and assigns **private IPs** per supported configuration.

~~~mermaid
flowchart TB
    A[App in private subnet AZ-a] --> D[Service DNS]
    B[App in private subnet AZ-b] --> D
    D --> E[Private DNS returns endpoint ENI IP]
    E --> F[Endpoint ENI in AZ-a]
    E --> G[Endpoint ENI in AZ-b]
    F --> H[AWS PrivateLink]
    G --> H
    H --> I[Service: Systems Manager / Secrets Manager / other]
~~~

Unlike gateway endpoints, interface endpoints **do not need a special prefix-list → vpce route**. Clients connect to the **endpoint ENI's private IP**, and standard VPC routing delivers packets to that IP provided routing, security groups, and NACLs permit it.

### 3.2. Private DNS Is Crucial for Application Experience

Suppose you create an interface endpoint for `com.amazonaws.ap-southeast-1.ssm`. When **private DNS is supported and enabled**, querying the standard API name:

~~~text
ssm.ap-southeast-1.amazonaws.com
~~~

from an eligible DNS resolution environment inside the VPC returns the **private IP of the endpoint ENI**. Applications and the AWS CLI can normally keep using the default service hostname without code changes.

If private DNS is disabled (or unsupported by the service), you generally must use the **VPC endpoint's specific DNS name** from `describe-vpc-endpoints` and specify the endpoint URL where needed. **Do not construct URLs manually** because DNS name formats vary by service, Region, and endpoint.

Conditions and limits to verify:

1. The VPC must have appropriate DNS settings enabled, typically **DNS resolution** (`enableDnsSupport`) and **DNS hostnames** (`enableDnsHostnames`).
2. The service must support private DNS for that endpoint.
3. If using custom DNS servers or calling from on-premises, design **DNS forwarding / Route 53 Resolver** so service queries resolve properly.
4. Enabling private DNS inside a VPC **does not automatically alter DNS on hosts in external networks**.
5. Some services have specific guidance on endpoint domain names, IPv4/IPv6, and connectivity options. Check the specific endpoint in the Console or service docs.

### 3.3. Security Groups and NACLs on Interface Endpoints

An interface endpoint has **security groups** attached to its endpoint ENIs. For a typical HTTPS API:

- **Endpoint security group:** allow **inbound TCP 443** from security groups or CIDRs of authorized workloads.
- **Workload security group:** allow **outbound TCP 443** to the endpoint.
- **Network ACL:** when using restrictive ACLs, allow bidirectional traffic and matching return ports.
- **Subnet IPs:** ensure enough free addresses for AWS to provision the ENIs; endpoint ENIs have a lifecycle and must be monitored.
- **IAM and endpoint policies:** still govern API operations; TCP reachability does not mean `GetSecretValue` or other API calls are authorized.

**Example:** a Lambda function running inside a VPC with security group `sg-app` calls Secrets Manager via an interface endpoint; the endpoint's security group `sg-vpce` should allow inbound 443 from `sg-app` rather than opening `0.0.0.0/0` unnecessarily.

### 3.4. Accessing from Other Networks

An interface endpoint **can** be reached from another VPC via peering/Transit Gateway or from on-premises via VPN/Direct Connect if network connectivity, return routes, DNS, security groups, policies, and service support all align. This makes interface endpoints valuable for centralized connectivity hubs or private data center access.

Example:

~~~mermaid
flowchart LR
    A[On-premises application] --> B[VPN / Direct Connect]
    B --> C[VPC hosting endpoint]
    C --> D[Interface endpoint ENI]
    D --> E[AWS PrivateLink]
    E --> F[Supported service]
~~~

Private connectivity over VPN/Direct Connect **does not automatically ensure working DNS**. Service hostnames must resolve to the endpoint's private IP, or clients must use the appropriate endpoint-specific DNS name.

**AWS PrivateLink** also supports the **endpoint service** model: a service provider publishes its own service (typically behind a Network Load Balancer) so consumers can create **interface endpoints** in their own VPCs. That model supports allowed principals and connection acceptance workflows. It is distinct from interface endpoints targeting AWS-managed service APIs.

## 4. Choosing Between Gateway Endpoints and Interface Endpoints

### 4.1. Decision Matrix

| Need | Recommended Option | Rationale |
|---|---|---|
| EC2 in VPC downloading objects from S3 in same Region | **S3 gateway endpoint** | No endpoint fee; simple route table integration |
| VPC app reading/writing DynamoDB in same Region | **DynamoDB gateway endpoint** | Uses prefix list routing for the service |
| Private EC2 calling AWS Systems Manager APIs | **SSM interface endpoint** | Service supports PrivateLink and avoids NAT for this API |
| Lambda in VPC calling Secrets Manager | **Secrets Manager interface endpoint** | API connects via endpoint private IP |
| VPC app sending logs to CloudWatch Logs | **CloudWatch Logs interface endpoint** | Reduces NAT reliance for Logs APIs |
| On-premises network needing private IP access to S3 | **Evaluate S3 interface endpoint** | Gateway endpoints cannot be used from on-premises |
| Another VPC needing an AWS service endpoint over private links | **Interface endpoint + matching routing/DNS** | Gateway endpoints do not work across external VPC links |
| App needing general web browsing or arbitrary public APIs | **NAT / controlled egress** | VPC endpoints do not replace general Internet connectivity |

**Do not pick an interface endpoint solely because it sounds "more private."** For S3/DynamoDB within the same VPC and Region, gateway endpoints are usually simpler and more cost-effective. For services supporting only interface endpoints or cross-network access, interface endpoints are the right choice.

### 4.2. Special Case: S3 Supports Both Endpoint Types

S3 supports both **gateway endpoints** and **interface endpoints**. Practical designs typically follow:

- **In-VPC workloads:** use an **S3 gateway endpoint** when only same-Region S3 access from inside the VPC is needed.
- **On-premises clients:** use an **S3 interface endpoint** with private networking and properly configured DNS.
- **Hybrid environments:** AWS offers DNS options so on-premises clients use the interface endpoint while in-VPC workloads continue using the gateway endpoint; options like **private DNS only for inbound Resolver endpoint** have specific prerequisites, including gateway endpoint configuration. Review official S3 documentation before applying.

Avoid creating both types for the same VPC by default without mapping traffic flows and costs first.

## 5. Security: Endpoint Policies, IAM Policies, and Resource Policies

### 5.1. Three Distinct Control Layers

~~~mermaid
flowchart TD
    A[Principal: EC2 role / Lambda role / user] --> B[IAM policy: permitted to call API?]
    B --> C[VPC endpoint: does request traverse endpoint?]
    C --> D[Endpoint policy: is this request allowed?]
    D --> E[Resource policy if applicable: bucket/secret/other]
    E --> F[Service evaluates remaining authorization checks]
    F --> G[Allow or Deny]
~~~

This diagram is a **mental checklist**, not an exact representation of every internal IAM evaluation step. AWS evaluates multiple policy layers including **explicit deny**, permissions boundaries, session policies, SCPs, and service-specific rules.

| Layer | What Does It Control? | What If a Matching `Allow` Is Missing? |
|---|---|---|
| **Identity-based IAM policy** | Whether the principal is permitted to invoke the action on the resource | Typically denied |
| **Endpoint policy** | Which requests may pass through the endpoint | Denied at the endpoint layer if disallowed by policy |
| **Resource-based policy** | Which principals/conditions the resource accepts | May be denied depending on permission model and resource type |
| **SCP / permissions boundary / session policy** | Upper bounds on effective permissions for the principal/session | Can be denied even if an IAM policy grants `Allow` |

**Endpoint policies do not replace IAM policies.** The default endpoint policy typically allows all traffic at the **endpoint layer**, without granting service-level permissions on its own.

**Not every interface endpoint supports endpoint policies.** Verify capabilities for the specific endpoint service; some endpoints use fixed default policies or separate access controls.

### 5.2. Restricting an S3 Bucket by VPC Endpoint

When you need to enforce that S3 requests arrive through a specific endpoint, a bucket policy can use the **global condition key** `aws:SourceVpce`. The example below is strictly to **illustrate the mechanism**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRequestsOutsideApprovedEndpoint",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::aws-lab-dev-data-example",
        "arn:aws:s3:::aws-lab-dev-data-example/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:SourceVpce": "vpce-0123456789abcdef0"
        }
      }
    }
  ]
}
~~~

In this illustrative policy, any request not originating from the approved endpoint matches `Deny`. **Never copy this policy verbatim onto shared or production buckets**: the AWS Console typically does not traverse your VPC endpoint, and AWS service workflows, emergency admin access, and automation could be locked out. If you actually enforce it, design conditional exceptions, recovery procedures, and test every legitimate access path beforehand.

Distinguish clearly:

- `aws:SourceVpce`: ID of the VPC endpoint used by the request.
- `aws:SourceVpc`: source VPC in supported contexts.
- `aws:VpcSourceIp`: private source IP inside the VPC when available; do not rely on it alone to identify a VPC uniquely since CIDRs can overlap across VPCs.
- **Public source IPs** and **ENI private IPs** do not behave identically across policies for every endpoint type.

### 5.3. VPC Endpoints Do Not Eliminate All Egress Needs

- If a route table still has `0.0.0.0/0` via NAT and an app calls other destinations, that traffic still traverses NAT.
- If an API is called via a domain/Region not matching the endpoint or without private DNS enabled properly, requests may take another path or fail.
- Endpoints only alter the network path for **configured services and scopes**; they do not replace firewalls, monitoring, IAM, or data governance.
- TLS/HTTPS and certificate verification remain mandatory per service requirements; private connectivity does not mean skipping TLS checks.

## 6. Cost, Performance, and Availability

### 6.1. Cost Comparison

| Component | Endpoint Cost | Other Costs That May Still Apply |
|---|---|---|
| **S3/DynamoDB gateway endpoint** | No hourly or data-processing endpoint charges | Request, storage, read/write, data transfer, and underlying service fees |
| **Interface endpoint** | Typically hourly per AZ and per GB processed | Cross-AZ transfer, DNS/Resolver if configured, target service fees, logs, and related components |
| **NAT Gateway** | Hourly NAT and per-GB processing charges | Data transfer and related network fees |
| **VPC Flow Logs / CloudWatch Logs** | Per service resource/log pricing | Ingestion, storage, queries, and retention if enabled |

Do not quote a single fixed price across all Regions. When estimating, use the **AWS Pricing Calculator** and current pricing tables:

~~~text
Estimated monthly interface endpoint cost
≈ (AZs with endpoint × active hours × hourly rate/AZ)
  + (GB processed via endpoint × rate/GB)
  + associated networking, service, or logging fees if applicable
~~~

Placing endpoints in **two AZs** for higher availability increases hourly charges but reduces single-AZ outage risk. Placing an endpoint in only one AZ forces clients in other AZs to cross AZ boundaries, adding latency/fees and dependency on the AZ hosting the ENI.

### 6.2. Multi-AZ Design

- **Gateway endpoints:** associate all **route tables** of private subnets needing S3/DynamoDB access; audit route tables whenever adding new subnets.
- **Interface endpoints:** select subnets across **the AZs to be served**, aligned with AZs supported by the endpoint service and fault-tolerance goals.
- **Security groups:** allow workload groups from all participating AZs, not just a single test subnet.
- **DNS:** verify clients resolve to the expected endpoint ENIs, including after AZ or VPC layout changes.
- **Monitoring:** use endpoint state, DNS checks, Flow Logs, CloudTrail, and service metrics where available to verify real behavior.
- **Resilience:** multiple ENIs alone do not make an app fault-tolerant; SDK retries, timeouts, circuit breakers, and service dependencies must also be designed.

## 7. Sandbox Hands-On: Create, Verify, and Clean Up Endpoints

> **Prerequisites:** operate only in an authorized AWS account/sandbox, in the proper Region and VPC. This lab can provision a **billable interface endpoint** (hourly + per-GB); check pricing and clean up right after the session. You do not need to run commands if studying theory only. Replace all IDs below with real sandbox IDs; never run against production.

Illustrative variables used in this section:

| Variable | Meaning |
|---|---|
| `REGION=ap-southeast-1` | Practice Region |
| `VPC_ID` | VPC containing private subnets |
| `ROUTE_TABLE_ID` | Route table of the private subnet needing S3 access |
| `SUBNET_A`, `SUBNET_B` | Two subnets in two distinct AZs with sufficient free IPs |
| `ENDPOINT_SG` | Security group for the interface endpoint |
| `APP_SG` | Security group of the EC2/Lambda workload calling the endpoint |
| `BUCKET` | Test S3 bucket in the same Region you are permitted to access |

### 7.1. Step 1 — Verify Identity, VPC, Region, and Supported Services

Using AWS CLI v2 in a Bash terminal:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1
VPC_ID=vpc-0123456789abcdef0
ROUTE_TABLE_ID=rtb-0123456789abcdef0
SUBNET_A=subnet-0123456789abcdef0
SUBNET_B=subnet-0123456789abcdef1
ENDPOINT_SG=sg-0123456789abcdef0
APP_SG=sg-0123456789abcdef1

aws sts get-caller-identity --profile "$AWS_PROFILE"

aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --region "$REGION"
aws ec2 describe-route-tables --route-table-ids "$ROUTE_TABLE_ID" --region "$REGION"
aws ec2 describe-subnets --subnet-ids "$SUBNET_A" "$SUBNET_B" --region "$REGION"

aws ec2 describe-vpc-endpoint-services \
  --service-names "com.amazonaws.$REGION.s3" "com.amazonaws.$REGION.ssm" \
  --region "$REGION"
~~~

All **IDs above are hypothetical examples**; replace them with assigned sandbox resources. If you do not have an `aws-lab-dev` profile, follow your organization's login instructions or use CloudShell with your signed-in identity and omit `export AWS_PROFILE=...`.

Verify:

1. STS `Account` and `Arn` match your practice account.
2. VPC, route table, and subnets belong to the target Region; subnets sit in the intended AZs.
3. `com.amazonaws.<region>.s3` supports creating a **gateway endpoint**; `com.amazonaws.<region>.ssm` supports creating an **interface endpoint** in the target AZs.
4. Interface endpoints require compatible private DNS and VPC DNS enabled.
5. Your current role has permissions for EC2 VPC endpoints; if not, stick to read/simulation steps rather than escalating privileges.

### 7.2. Step 2 — Create an S3 Gateway Endpoint

~~~bash
GW_EP_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" \
  --vpc-endpoint-type Gateway \
  --service-name "com.amazonaws.$REGION.s3" \
  --route-table-ids "$ROUTE_TABLE_ID" \
  --region "$REGION" \
  --query 'VpcEndpoint.VpcEndpointId' \
  --output text)

echo "$GW_EP_ID"

aws ec2 describe-route-tables \
  --route-table-ids "$ROUTE_TABLE_ID" \
  --region "$REGION" \
  --query 'RouteTables[].Routes[]' \
  --output table
~~~

Expected result: the route table gains a route to the **S3 prefix list** targeting the **gateway endpoint ID**. If your app spans multiple private subnets across multiple route tables, associate every route table that needs the endpoint.

At creation time, the default endpoint policy typically permits service traffic through the endpoint; apply a custom policy once exact required permissions are understood. Endpoint policies do not replace IAM or bucket policies.

### 7.3. Step 3 — Prepare the Security Group for the Interface Endpoint

For an SSM interface endpoint, allow the endpoint ENI to receive HTTPS from workloads. If `ENDPOINT_SG` is a security group **you are authorized to edit** and lacks the rule:

~~~bash
aws ec2 authorize-security-group-ingress \
  --group-id "$ENDPOINT_SG" \
  --protocol tcp \
  --port 443 \
  --source-group "$APP_SG" \
  --region "$REGION"
~~~

If the rule already exists, the API may return `InvalidPermission.Duplicate`; no need to add it again. Ensure the workload security group permits **egress TCP 443** and network ACLs allow return traffic. Do not open inbound 443 to the entire Internet if only in-VPC workloads need the endpoint.

### 7.4. Step 4 — Create the SSM Interface Endpoint Across Two AZs

~~~bash
IF_EP_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" \
  --vpc-endpoint-type Interface \
  --service-name "com.amazonaws.$REGION.ssm" \
  --subnet-ids "$SUBNET_A" "$SUBNET_B" \
  --security-group-ids "$ENDPOINT_SG" \
  --private-dns-enabled \
  --region "$REGION" \
  --query 'VpcEndpoint.VpcEndpointId' \
  --output text)

echo "$IF_EP_ID"

aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids "$GW_EP_ID" "$IF_EP_ID" \
  --region "$REGION" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Type:VpcEndpointType,State:State,Service:ServiceName}' \
  --output table
~~~

Wait until the endpoint reaches **`available`** before testing. For interface endpoints, inspect **DNS entries**, **subnet IDs**, **network interface IDs**, and **security groups** in the Console or `describe-vpc-endpoints` output.

**Systems Manager note:** the `ssm` endpoint serves SSM APIs, whereas a private EC2 instance using full **Session Manager / SSM Agent** capabilities may also require endpoints such as `ssmmessages` and `ec2messages` (depending on Region, agent version, and features), along with appropriate IAM permissions. Never assume a single `ssm` interface endpoint covers every EC2 management workflow.

### 7.5. Step 5 — Test from a Workload in a Private Subnet

Run tests from an **EC2 private instance** or VPC-attached runtime; running from a laptop outside the VPC does not validate traffic traversing the endpoint. Ensure the workload has an **IAM role** with least-privilege permissions for test APIs.

**Test interface endpoint DNS:**

~~~bash
nslookup ssm.ap-southeast-1.amazonaws.com
~~~

When private DNS works, queries from an eligible in-VPC resolver typically return **private IPs** of the endpoint ENIs. Cross-check those addresses against the interface endpoint's ENIs; **correct DNS is necessary, but does not prove API authorization**.

**Test SSM API (if the role has `ssm:DescribeInstanceInformation`):**

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --max-results 5
~~~

**Test S3 gateway endpoint (if authorized to access the bucket):**

~~~bash
BUCKET=aws-lab-dev-data-example

aws s3api head-bucket \
  --bucket "$BUCKET" \
  --region ap-southeast-1
~~~

The bucket must **exist in the matching Region** and IAM/bucket/endpoint policies must permit access. A `403 AccessDenied` does not necessarily indicate a network failure; separate **connectivity/TLS/DNS** errors from **IAM/S3 authorization** errors first.

To verify traffic reaches the right endpoint, combine DNS checks, route tables, endpoint ENIs, VPC Flow Logs if enabled, and API request logs where supported by the service. **VPC Flow Logs** reflect network flow metadata, not the payload of individual API calls.

### 7.6. Step 6 — Delete Resources to Stop Incurring Charges

Once the lab finishes, delete only the endpoints **you created** and are authorized to clean up:

~~~bash
aws ec2 delete-vpc-endpoints \
  --vpc-endpoint-ids "$GW_EP_ID" "$IF_EP_ID" \
  --region "$REGION"
~~~

Verify the endpoints transition to deleting and disappear from the list. AWS removes the associated gateway endpoint routes and interface endpoint ENIs as part of endpoint deletion. If you created a dedicated security group for the lab, delete it once no endpoint references it; if you added a rule to a shared security group, follow your team's process to remove only the rule you added.

**Warning:** shell variables `GW_EP_ID` and `IF_EP_ID` live only in your current terminal session. Record lab endpoint IDs in your technical notes so you can locate/delete them even if the terminal closes; verify `Account`/`Region` before deleting anything.

## 8. Symptom-Based Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Private EC2 cannot reach S3 despite a gateway endpoint | Subnet route table not associated with endpoint; bucket in different Region; IAM/bucket policy restriction | Trace subnet → route table → prefix list target → bucket Region and permissions |
| EC2 calling SSM/Secrets Manager times out | Endpoint ENI not `available`, endpoint SG blocks inbound 443, NACL or DNS/routing error | `describe-vpc-endpoints`, check ENIs, SGs, routes, DNS, and Flow Logs |
| API endpoint hostname still resolves to public IP | Private DNS not enabled/supported; wrong VPC DNS settings; custom DNS server not forwarding | Check endpoint private DNS, `enableDnsSupport`, `enableDnsHostnames`, and resolvers |
| API returns `AccessDenied` despite HTTPS connectivity | Blocked by IAM, endpoint policy, resource policy, SCP, boundary, or session policy | Confirm principal via STS; inspect policies and CloudTrail |
| Cannot create interface endpoint in a subnet | AZ unsupported by service; subnet out of IPs; quota or endpoint config error | Inspect error message, service details, subnet/AZ, and quotas |
| Host in another VPC cannot use S3 gateway endpoint | Gateway endpoints are unreachable across peering/TGW/VPN | Provision an endpoint in the target VPC or design an interface endpoint where appropriate |
| On-premises access to interface endpoint fails | Missing route, DNS forwarding, SG, or return path | Inspect VPN/DX/TGW, endpoint DNS name, subnets, and bidirectional flow |
| Interface endpoint exists, yet NAT costs remain high | Part of traffic still hits public endpoints/other services; DNS points elsewhere; NAT serves other destinations | Cross-check DNS, flow logs, active endpoint services, and Cost Explorer |
| S3 bucket rejects Console access after adding `SourceVpce` policy | Console does not arrive via the required VPC endpoint | Review bucket policy and designed administrative access paths |
| Endpoint policy allows reads, yet the app still fails | Identity policy lacks permission, bucket policy denies, KMS key policy, or another condition | Inspect `s3:GetObject`, object ARN, KMS, and all policy layers |

### 8.1. Ordered Verification Workflow

1. **Account/Region:** confirm the exact environment you are operating in.
2. **Service and endpoint type:** is that endpoint type supported in the Region/AZ?
3. **Endpoint state:** is the endpoint `available`?
4. **Network path:** for gateway endpoints inspect **route table/prefix list**; for interface endpoints inspect **DNS → ENI private IP → security group/NACL/routing**.
5. **TLS and API:** does HTTPS reach the service? If so, is the error `AccessDenied` or a business/application error?
6. **Authorization:** review IAM, endpoint policy, resource policy, SCP/boundary/session policy, and service-specific policies.
7. **Cost and cleanup:** verify endpoints, ENIs, and supporting resources remaining after the lab.

## 9. Architecture Design Exercise

**Scenario:** An order-processing system uses:

- **API/Lambda** in two private subnets across two AZs.
- **DynamoDB** storing order state.
- **S3** storing invoices and export files.
- **Secrets Manager** storing sensitive config for components using secrets.
- **CloudWatch Logs** collecting logs.
- No arbitrary Internet access for workloads, while maintaining observability and cost control.

**Design** the required endpoints and specify route tables, subnets/AZs, security groups, IAM, and endpoint/resource policies.

A reference design:

| Need | Endpoint | Placement | Accompanying Controls |
|---|---|---|---|
| Read/write S3 in same Region | S3 gateway | Associate route tables of both private subnets | Least-privilege IAM role, bucket policy, endpoint policy if needed |
| Access DynamoDB | DynamoDB gateway | Associate route tables of both private subnets | IAM policy scoped to tables and actions |
| Access Secrets Manager | `secretsmanager` interface | Create endpoint ENIs in served AZs, private DNS | SG inbound 443 from app, IAM/KMS if applicable |
| Send CloudWatch Logs from components calling Logs API | `logs` interface | One or more AZs per SLO, private DNS | SG, IAM Logs permissions, retention/cost |
| Auth, additional service calls | Evaluate other endpoints like STS/KMS/SSM only when genuinely needed | Follow API flows and per-service documentation | Do not add endpoints just to "check off a list" |

**Trade-off analysis:**

- The two gateway endpoints carry no separate endpoint fees, making them ideal for same-Region S3/DynamoDB.
- Each additional interface endpoint increases hourly and data-processing fees; provision only for APIs genuinely needed.
- Two AZs reduce single-AZ dependency, but application-level retries and resilience are still required.
- If the app has other egress paths, adding a VPC endpoint does not automatically force all AWS API traffic through it; policies and DNS configs must align.
- To monitor costs, tag supporting resources, enable Billing/Cost Explorer reporting per permissions, set Budget alerts, and delete unused resources.
- Before declaring "no NAT needed," list **all dependencies**: container registries, image pulls, package mirrors, telemetry, authentication, non-AWS APIs, and supporting features; additional endpoints or controlled egress may still be necessary depending on the system.

## 10. Misconceptions to Avoid

**"A gateway endpoint is a gateway VM inside the subnet."** False. It is an AWS-managed route target; there is no endpoint ENI or security group specific to a gateway endpoint.

**"Having an interface endpoint automatically uses the standard service hostname."** Only when endpoint/service DNS is configured properly. Otherwise, you need the endpoint-specific DNS name and appropriate routing.

**"Creating an endpoint allows all APIs."** False. IAM policies and other constraints still govern authorization, and endpoint policies act as an additional control layer where supported.

**"S3 must always use an interface endpoint for private access."** False. Gateway endpoints are the common, no-endpoint-fee choice for same-Region S3 access from in-VPC workloads.

**"A gateway endpoint in VPC A can be shared with VPC B over peering."** False. Gateway endpoints cannot be accessed across peering; provision a dedicated endpoint in VPC B or adjust the design.

**"Interface endpoints have no cost because they avoid NAT."** False. Interface endpoints typically incur per-AZ hourly charges and per-GB data-processing charges.

**"Having an endpoint in one AZ guarantees multi-AZ fault tolerance."** False. That creates a dependency on the AZ hosting the endpoint ENI; select AZs and recovery plans aligned with target availability.

## 11. Knowledge Self-Check

1. Why does an S3 gateway endpoint require route table association, whereas an interface endpoint typically relies on private DNS and security groups?
2. When an EC2 instance has no public IP and its route table has no NAT, under what conditions can it still read S3 via a gateway endpoint?
3. Why can `aws:SourceVpce` in a bucket policy block AWS Console access to the bucket?
4. In a two-AZ architecture, what must be considered when provisioning an interface endpoint ENI in only one AZ?
5. When an interface endpoint is `available` yet APIs return `AccessDenied`, which policies should be audited?
6. When should you choose an S3 interface endpoint instead of a gateway endpoint?
7. Can an endpoint policy replace an IAM role policy to grant `secretsmanager:GetSecretValue` to Lambda?
8. If a service has no VPC endpoint support and requires Internet access, what kind of network path does the application need? Why does a NAT Gateway not necessarily replace dedicated endpoints?
9. If a project uses CloudWatch Logs and several other AWS services, how should you estimate private communication costs before creating every endpoint?

**Completion criteria:** you can accurately trace the **packet path**, choose endpoints by service and network scope, identify API authorization policies, test in a sandbox, and clean up resources to prevent unnecessary costs.

## Official AWS Documentation for Reference

- [Access an AWS service using an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html)
- [Gateway endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html)
- [Gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html)
- [Gateway endpoints for DynamoDB](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-ddb.html)
- [AWS PrivateLink concepts](https://docs.aws.amazon.com/vpc/latest/privatelink/concepts.html)
- [Interface endpoint DNS names](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html)
- [VPC endpoint policies](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-access.html)
- [Amazon S3 interface endpoints](https://docs.aws.amazon.com/AmazonS3/latest/userguide/privatelink-interface-endpoints.html)
- [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/)
- [AWS IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)

> **Hands-on note:** IDs, bucket names, CLI commands, and JSON examples in this lesson are for explanation only. Verify current AWS service support, Regions/AZs, IAM permissions, DNS behavior, pricing, and resource cleanup procedures before changing configurations in a real account.
