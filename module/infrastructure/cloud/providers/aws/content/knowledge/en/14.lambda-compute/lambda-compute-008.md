# Connecting Lambda to VPCs and Private Services

In AWS, a **Lambda function** can receive events from API Gateway, EventBridge, or SQS and process data without server management. However, when business logic must query a **private Amazon RDS database**, call **Amazon ElastiCache**, or mount **Amazon EFS**, the function needs a network path to resources inside an **Amazon Virtual Private Cloud (VPC)**. That differs from reaching S3 or DynamoDB via public AWS service endpoints, and differs even more from how a client inside a VPC invokes the **Lambda Invoke API**.

Picking a few subnets and hitting Save without understanding routing, security groups, and VPC endpoints leads to database connection timeouts, unreachable Secrets Manager secrets, or broken outbound calls to external APIs. This lesson builds a network and security model to avoid those pitfalls.

This lesson belongs to the **Lambda Compute** chapter of **CLOUD_PROVIDERS_AWS**, connecting Regions/AZs, IAM, VPC, EC2, RDS, EFS, S3, integration networking, and serverless. The goal is to design Lambda functions with private connectivity, least privilege, observability, resilience, and cost control.

> **Key idea:** Lambda **does not physically move inside your subnet** when attached to a VPC. It still runs on Lambda-managed infrastructure and uses a **Hyperplane Elastic Network Interface (ENI)** to reach private resources in your VPC. Attaching a VPC governs **outbound traffic from your code**; it does not turn Lambda into a server with a private IP that clients connect to directly.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish **Lambda-managed VPC**, **customer VPC**, and **Hyperplane ENI**.
2. Choose private subnets across multiple Availability Zones, route tables, security groups, and NACLs for Lambda.
3. Explain why a **public subnet does not automatically grant Internet access** to Lambda and when a NAT Gateway is required.
4. Choose **Gateway VPC Endpoints** for S3/DynamoDB and **Interface Endpoints (AWS PrivateLink)** for AWS APIs like Secrets Manager, STS, or the Lambda Invoke API.
5. Distinguish **Lambda calling VPC resources** from **a VPC client invoking Lambda**.
6. Design Lambda → RDS/RDS Proxy, ElastiCache, or EFS integrations accounting for scaling, authentication, and connection pooling.
7. Scope IAM execution roles with ENI permissions and service permissions while avoiding overly broad code-level privileges.
8. Inspect configurations via Console/CLI, verify endpoints/routes/SGs, and troubleshoot timeouts, DNS errors, and `AccessDenied`.
9. Use Java AWS SDK v2 to access private services without hardcoding credentials.
10. Account for IPv6, concurrency, multi-AZ availability, and NAT/PrivateLink/RDS Proxy costs.

## 2. The Right Mental Model: Lambda Stays on Lambda-Managed Infrastructure

In Lambda's standard execution model, AWS runs execution environments inside a **Lambda-managed VPC** invisible to customers. If a function needs to talk to a private database inside your VPC, you configure **`VpcConfig`** with subnet IDs and security group IDs from your **customer VPC**.

Lambda creates and manages **Hyperplane ENIs** for each unique subnet and security group combination so traffic from the function enters private VPC address space. This is a **managed network attachment**, not a dedicated EC2 network interface manually attached per container.

~~~mermaid
flowchart LR
    T["API Gateway / EventBridge / SQS event"] --> L["AWS Lambda execution environment<br/>(Lambda-managed VPC)"]
    L --> H["Lambda Hyperplane ENI"]
    subgraph V["Customer VPC · 10.20.0.0/16"]
      S["Private subnets<br/>AZ-a, AZ-b"]
      DB["RDS / RDS Proxy<br/>private endpoint"]
      EC["ElastiCache / private API"]
      EFS["EFS mount targets"]
      EP["S3 Gateway / Interface VPC endpoints"]
      NAT["NAT Gateway<br/>when IPv4 Internet is needed"]
      H --> S
      S --> DB
      S --> EC
      S --> EFS
      S --> EP
      S --> NAT
    end
~~~

### 2.1. Four Essential Facts

- **The function can still be invoked from outside the VPC** via authorized triggers; VPC attachment does not block API Gateway, EventBridge, or SQS from triggering it.
- **The function has no direct TCP/HTTP listener on its Hyperplane ENI** for external systems to hit like an EC2 server.
- **Outbound traffic initiated by your code to private resources** follows the route tables, SGs/NACLs, and DNS of those subnets and targets.
- **Do not attach a VPC unless needed:** a function only calling public S3/DynamoDB via AWS APIs works cleanly without VPC attachment. Adding a VPC unnecessarily complicates networking and can add NAT/endpoint costs.

### 2.2. Separating Layers During Failures

| Layer | Question to answer | Example |
|---|---|---|
| **Invoke** | Is the caller permitted to trigger the function? | API Gateway, SQS event source mapping, `lambda:InvokeFunction` |
| **VPC network** | Does an IP/DNS path exist from function to backend? | Subnet routes, Hyperplane ENI, SG, VPC endpoints |
| **AWS IAM** | Does the execution role have permission to call the AWS API? | `secretsmanager:GetSecretValue`, `s3:GetObject` |
| **Application** | Is the backend listening with valid TLS/auth? | RDS port 5432, JDBC credentials, TLS certificates |
| **Operations** | Are connections exhausted or timeouts exceeded? | Lambda concurrency, RDS `max_connections`, NAT capacity |

To troubleshoot quickly, pinpoint **which layer failed** instead of blindly adding a `0.0.0.0/0` rule or IAM `*`.

## 3. Hyperplane ENIs: Operation, Sharing, and Lifecycle

When attaching a Lambda function to a **subnet ID + security group ID combination** not yet used by Lambda, AWS creates a Hyperplane ENI. Functions in the **same account** sharing the exact same network combination can reuse that ENI rather than allocating a new ENI per function or invocation.

According to current AWS documentation, a Hyperplane ENI supports roughly **65,000 connections/ports**; Lambda can scale out additional ENIs automatically when connection demand exceeds an existing ENI. This is **not** a 65,000 Lambda concurrency limit or a guarantee that your database can handle 65,000 SQL connections.

### 3.1. Initial VPC Setup Can Show `Pending`

- When a new function needs a Hyperplane ENI that is not ready yet, it can stay in **`Pending`** while the ENI provisions.
- A brand-new function cannot be invoked until it reaches **`Active`**.
- When modifying VPC config on an existing function, older versions may remain invocable while certain updates/publishes are temporarily blocked.
- ENI creation can take a few minutes; **this is one-time provisioning**, not a per-invocation Java cold start bug.

### 3.2. Idle Functions Can Transition to `Inactive`

Per AWS documentation, if a function goes unused for **14 days**, Lambda may reclaim idle Hyperplane ENIs and mark the function `Inactive`. The next first invocation may fail while Lambda transitions through `Pending` to recreate network resources. Systems must never depend on **permanent ENI existence**.

When removing VPC config or deleting a function, ENI cleanup takes time; deleting the execution role too early can leave orphaned ENIs. Never manually delete Lambda-managed ENIs or ENIs still shared by other functions/versions.

### 3.3. Optimizing Subnet/SG Combinations

Creating a separate SG per function solely for naming multiplies network combinations. Reuse SGs when **security boundaries and traffic rules match**; conversely, never lump unrelated functions into one SG if that grants excess permissions. Balance security segmentation, ENI reuse, and operations at the application level.

## 4. Choosing VPCs, Subnets, and Availability Zones

### 4.1. A Two-AZ Architecture

Example:

| Component | Illustrative value |
|---|---|
| VPC | `vpc-app`, CIDR `10.20.0.0/16` |
| Private subnet A | `10.20.10.0/24` in `ap-southeast-1a` |
| Private subnet B | `10.20.20.0/24` in `ap-southeast-1b` |
| Lambda SG | `sg-lambda-orders`, scoped egress |
| RDS/Proxy SG | `sg-db-orders`, inbound TCP 5432 from Lambda SG |
| S3 Gateway Endpoint | Attached to both private subnet route tables |
| Secrets Manager Interface Endpoint | ENIs + SG for TCP 443 and Private DNS |
| NAT Gateway | Optional, when IPv4 Internet access is needed beyond endpoints |

IDs and CIDRs are examples. In production, select **at least two private subnets in different AZs** where target services/Regions/architectures support it, ensuring sufficient IPv4 address space, routes, NACLs, and target service availability across those AZs.

### 4.2. `SubnetIds` Must Belong to the Same VPC

A single Lambda `VpcConfig` references subnets and security groups from **one VPC**. You cannot mix one subnet from VPC A and one from VPC B in the same `VpcConfig`. If a backend sits in VPC B, establish inter-VPC connectivity (peering, Transit Gateway, or PrivateLink) or use VPC sharing.

### 4.3. Route Tables Belong to Subnets, Not Lambda Code

Traffic to private CIDRs **inside the same VPC** uses the built-in `local` route. Routes leaving the VPC are configured on the route tables associated with the selected subnets:

| Destination | Target | Effect |
|---|---|---|
| `10.20.0.0/16` | `local` | Communicates with resources inside the VPC |
| `0.0.0.0/0` | `nat-...` | IPv4 Internet egress from private subnets when required |
| S3 prefix list | `vpce-...` (Gateway type) | Reaches S3 through the gateway endpoint |
| `::/0` | Egress-only Internet Gateway | IPv6 outbound in matching dual-stack setups |
| Peer CIDR | `pcx-...` or TGW attachment | Connects to resources in other VPCs per routing design |

If a subnet uses a **custom route table**, editing the main route table has no effect on that subnet. Always inspect subnet-to-route-table associations and both **outbound and return paths**.

### 4.4. Availability by AZ

Lambda places network capacity across the attached subnets. Selecting subnets across multiple AZs avoids single-AZ dependency, yet if both subnets route through a single NAT Gateway in AZ-a, or the database itself is single-AZ, a single point of failure remains. Design the whole chain — **Lambda → network egress → endpoints → database** — rather than just giving Lambda two AZs.

## 5. Security Groups, NACLs, and DNS

### 5.1. Stateful Security Groups

For Lambda to call a private RDS PostgreSQL/Proxy endpoint on TCP 5432:

- **Lambda SG:** allow **egress TCP 5432** to the RDS/Proxy SG or approved CIDR.
- **RDS/Proxy SG:** allow **inbound TCP 5432** from the **Lambda SG** (within the same VPC or supported peered SG references).
- Security groups are **stateful**: return traffic for an established connection is automatically allowed.

Never open inbound `0.0.0.0/0` on the Lambda SG just so AWS API Gateway or SQS can invoke the function. Invocations do not open direct TCP connections to your Hyperplane ENI.

### 5.2. Illustrative SG Table

| Security Group | Inbound | Outbound |
|---|---|---|
| `sg-lambda-orders` | No inbound rules needed to call RDS | TCP 5432 to `sg-db-orders`; TCP 443 to endpoint SG |
| `sg-db-orders` | TCP 5432 from `sg-lambda-orders` | As needed by DB/Proxy; avoid wide-open egress |
| `sg-vpce-secrets` | TCP 443 from `sg-lambda-orders` | Stateful responses per SG; verify policies |

If an interface endpoint (Secrets Manager, STS, etc.) restricts inbound to another CIDR, Lambda calls time out even when the IAM role is correct.

### 5.3. Stateless Network ACLs and Ephemeral Ports

NACLs apply at the subnet level and are **stateless**; restrictive NACLs must explicitly permit return traffic on **ephemeral ports** in both inbound and outbound directions. Lambda networking troubleshooting docs specifically note that Hyperplane ENIs use source ports **1024–65535** for TCP/UDP traffic; overly narrow NACLs cause intermittent failures.

Never use NACLs as a substitute for Security Groups. In most architectures, SGs act as the primary source/destination control while NACLs provide coarse subnet guardrails if policy demands them.

### 5.4. DNS Inside a VPC

Lambda code typically connects by hostname such as `orders-proxy.proxy-abc.ap-southeast-1.rds.amazonaws.com` or `secretsmanager.ap-southeast-1.amazonaws.com`. Verify:

1. VPC DNS attributes `enableDnsSupport` and `enableDnsHostnames`.
2. Route 53 Resolver, private hosted zones, and forwarding rules.
3. Private DNS enabled on interface endpoints.
4. Resolved IPs are reachable through route tables, SGs, and NACLs.
5. TLS hostname verification matches the real hostname, especially with RDS Proxy/databases.

`UnknownHostException` points to DNS; `SocketTimeoutException` points to network/service reachability; `AccessDeniedException` from the AWS SDK points to IAM or resource policies.

## 6. Does Attaching a VPC Cut Off Internet Access?

**Yes, unless egress is designed.** By default, functions without a customer VPC reach public AWS service APIs and the Internet from the Lambda-managed environment. Once attached to a customer VPC, **outbound traffic initiated by your code** traverses that VPC's networking; reaching the Internet requires an explicit path.

### 6.1. A Public Subnet Does Not Give Lambda Internet Access

Many teams attach Lambda to a subnet with `0.0.0.0/0 → Internet Gateway` expecting outbound HTTPS to work. However, **Lambda does not receive a public IPv4 address just because a subnet is public**. An Internet Gateway does not forward outbound IPv4 traffic from a private-IP ENI without NAT or a public IP.

AWS recommends placing Lambda in **private subnets** and using a **NAT Gateway** in a public subnet if IPv4 Internet egress is needed.

~~~mermaid
flowchart LR
    L["VPC-connected Lambda"] --> R["Private subnet route table"]
    R --> NAT["0.0.0.0/0 → NAT Gateway"]
    NAT --> IGW["Public subnet → Internet Gateway"]
    IGW --> EXT["External HTTPS API / Internet"]
    R --> S3["S3 Gateway Endpoint"]
    R --> SM["Secrets Manager Interface Endpoint"]
~~~

### 6.2. Sample Route Tables for NAT Gateway

| Location | Destination | Target |
|---|---|---|
| Private subnet | VPC CIDR | `local` |
| Private subnet | `0.0.0.0/0` | `nat-123...` |
| Public subnet hosting NAT | VPC CIDR | `local` |
| Public subnet hosting NAT | `0.0.0.0/0` | `igw-123...` |

A public NAT Gateway requires proper configuration, typically with an **Elastic IP**. For multi-AZ HA, consider **one NAT Gateway per AZ** with private route tables pointing to the AZ-local NAT to prevent single-AZ failures and cross-AZ data transfer charges. NAT incurs hourly and data-processing fees.

### 6.3. Outbound IPv6 from Dual-Stack Subnets

Lambda supports **outbound IPv6** when `Ipv6AllowedForDualStack=true` and **all** subnets in `VpcConfig` are **dual-stack** (both IPv4 and IPv6 CIDRs). AWS **does not support outbound IPv6 on IPv6-only subnets** in this Lambda VPC setup.

For IPv6 Internet egress without direct inbound connectivity, use an **egress-only Internet Gateway** and a `::/0` route where supported. IPv4-only external endpoints still require NAT; enabling IPv6 **does not replace** `0.0.0.0/0` and NAT.

## 7. VPC Endpoints: Calling AWS APIs Without Internet Egress

When a function in a private subnet calls AWS services, **VPC endpoints** can replace NAT where supported by the service, Region, and network path. Two primary types exist:

- **Gateway Endpoint:** supports **Amazon S3** and **DynamoDB**; attaches to route tables with no hourly endpoint charge for standard Gateway endpoints.
- **Interface Endpoint (AWS PrivateLink):** provisions ENIs inside subnets for services like Secrets Manager, STS, ECR, SQS, Lambda APIs, and CloudWatch Logs where supported; uses SGs, Private DNS, endpoint policies, and bills per hour and GB processed.

### 7.1. Endpoint Selection Table

| Function code needs to call | Endpoint in `ap-southeast-1` | Type |
|---|---|---|
| `S3 GetObject/PutObject` | `com.amazonaws.ap-southeast-1.s3` | Gateway |
| `DynamoDB GetItem/PutItem` | `com.amazonaws.ap-southeast-1.dynamodb` | Gateway |
| `SecretsManager GetSecretValue` | `com.amazonaws.ap-southeast-1.secretsmanager` | Interface |
| `STS AssumeRole` (if code explicitly calls it) | `com.amazonaws.ap-southeast-1.sts` | Interface |
| `SQS SendMessage/ReceiveMessage` from code | `com.amazonaws.ap-southeast-1.sqs` | Interface |
| `SSM GetParameter` | `com.amazonaws.ap-southeast-1.ssm` | Interface |
| `KMS Encrypt/Decrypt` from code | `com.amazonaws.ap-southeast-1.kms` | Interface |
| `Lambda Invoke API` from code/client | `com.amazonaws.ap-southeast-1.lambda` | Interface |
| `CloudWatch Logs API` from code | `com.amazonaws.ap-southeast-1.logs` | Interface |

**This table illustrates Singapore Region names**; verify exact service names, availability, and real network paths before provisioning. Endpoints never grant IAM permissions by themselves. S3/DynamoDB Gateway endpoints serve **same-Region** service traffic per Gateway endpoint rules, not automatic cross-Region access.

### 7.2. S3 Gateway Endpoint

In VPC Console → Endpoints, pick the S3 **Gateway** service, target VPC, and private route tables. AWS adds an S3 prefix-list route. Same-Region S3 calls from Lambda then traverse the endpoint without needing NAT.

Verify:

1. Endpoint matches the VPC and Region.
2. Private subnet route tables include the prefix list → `vpce-...` route.
3. Endpoint policy and S3 bucket policy allow the IAM principal, actions, and keys.
4. DNS and SDK Region match.
5. Never confuse an endpoint policy with IAM `s3:GetObject` permissions.

### 7.3. Interface Endpoints

Example Secrets Manager interface endpoint:

- Create endpoint for `com.amazonaws.ap-southeast-1.secretsmanager`.
- Select **private subnets** across the required AZs for availability.
- Attach an endpoint SG allowing **inbound TCP 443** from the Lambda SG.
- Enable **Private DNS** so the AWS SDK resolves the default service hostname to private endpoint IPs.
- Grant `secretsmanager:GetSecretValue` on the exact secret ARN plus `kms:Decrypt` if needed.
- Review endpoint policies, DNS, routes, SGs, AZ coverage, and cost.

### 7.4. Avoid Assuming Lambda Logs/SQS Triggers Need Endpoints for Code

The **Lambda service** ships standard runtime logs to CloudWatch Logs and polls SQS event source mappings on the control/service plane — distinct from **AWS SDK calls emitted by your function code**. If your code explicitly calls `SQS SendMessage` or `CloudWatchLogs PutLogEvents`, it needs a network path; however, you do not need SQS or Logs VPC endpoints solely for Lambda to receive SQS triggers or emit standard runtime logs.

Similarly, receiving events from EventBridge or API Gateway requires no inbound TCP path into your ENI. VPC networking primarily governs **connections opened by your function code**.

## 8. Lambda Calling RDS in a Private Subnet

### 8.1. Direct Connection to RDS

Suppose `orders-api` connects to PostgreSQL RDS at private endpoint `orders-db.abc.ap-southeast-1.rds.amazonaws.com:5432`.

Requirements:

1. Lambda `VpcConfig` selects subnets with routes to the DB endpoint.
2. Lambda SG allows outbound TCP 5432 to the DB SG.
3. DB SG allows inbound TCP 5432 from the Lambda SG.
4. Database is `available` and its DNS hostname resolves properly.
5. Valid JDBC URL, TLS CA/hostname verification, and username/password or IAM DB auth.
6. Execution role permits fetching the secret if stored in Secrets Manager.
7. If fetching secrets via SDK from a private subnet without NAT, attach a **Secrets Manager interface endpoint**.

**Never mark RDS publicly accessible** just so Lambda in the same VPC can reach it. Enabling public access widens attack surface without fixing VPC routing.

### 8.2. Why Can Lambda Concurrency Exhaust DB Connections?

One Lambda execution environment can reuse a TCP/JDBC connection across sequential invocations **within that environment**. When concurrent invocations surge, Lambda spins up many execution environments. If each holds 5 JDBC connections across 300 environments, the fleet opens around **1,500 DB connections**, overwhelming a small DB's `max_connections`.

Never assume Lambda execution environments share one global connection pool. Pools live **inside a single environment**, never across concurrent environments.

### 8.3. Amazon RDS Proxy

**RDS Proxy** provides managed connection pooling for supported RDS/Aurora engines. Lambda connects to the proxy endpoint while the proxy maintains and multiplexes backend DB connections, helping handle bursty concurrency, connection overhead, and failover transitions.

~~~mermaid
flowchart LR
    L["Many Lambda execution environments"] --> P["RDS Proxy endpoint<br/>private DNS/TCP 5432"]
    P --> DB["RDS/Aurora DB"]
    SM["Secrets Manager / IAM auth"] --> P
~~~

RDS Proxy **does not remove all connection limits**. Long-lived transactions or session-state features cause pinning, reducing pooling efficiency. Monitor `ClientConnections`, `DatabaseConnections`, `DatabaseConnectionsBorrowLatency`, DB CPU/connections, and timeouts.

### 8.4. Security Groups When Using RDS Proxy

Example:

| Source | Destination | Rule |
|---|---|---|
| Lambda SG | RDS Proxy SG | Egress TCP 5432 |
| RDS Proxy SG | Lambda SG | Inbound TCP 5432 |
| RDS Proxy SG | RDS DB SG | Egress TCP 5432 |
| RDS DB SG | RDS Proxy SG | Inbound TCP 5432 |

Separate direct DB access from proxy access so Lambda connects exclusively through the proxy. Avoid opening DB ingress to the entire VPC CIDR when only one workload needs access.

### 8.5. Secrets and IAM Database Authentication

- **Secrets Manager** stores and rotates DB passwords; never hardcode plaintext passwords in Lambda environment variables.
- Grant `secretsmanager:GetSecretValue` on the approved secret ARN in the execution role, plus `kms:Decrypt` for customer-managed KMS keys.
- Consider **IAM database authentication** where supported by the engine/proxy to avoid passwords in code; requires `rds-db:connect` on the exact DB resource ARN and short-lived signed auth tokens.
- When using Secrets Manager credentials, cache with a bounded TTL and handle rotation so you do not call the secret API on every single request or connection init.

RDS Proxy carries its own charges and is not free. For small databases with low concurrency, compare direct connections vs. proxy across connection count, latency, complexity, and cost.

## 9. Connecting to ElastiCache, EFS, and Private HTTP APIs

### 9.1. Amazon ElastiCache

ElastiCache for Valkey / Redis OSS / Memcached typically exposes private endpoints inside a VPC. Lambda connects via TCP to the cluster/reader endpoint:

- Redis/Valkey defaults to `6379` (or configured port); Memcached uses `11211`.
- Ensure inbound SG rules from the Lambda SG on that port, proper routes, and DNS.
- Account for TLS, AUTH/ACL, Redis client pooling, and Lambda concurrency.
- Cache is an **optimization**, never the sole source of truth where durability matters.

Do not provision NAT just to reach ElastiCache inside the same VPC; `local` routing and SGs are sufficient.

### 9.2. Amazon EFS

Lambda can mount **Amazon EFS** for shared filesystem access:

- Function must have a **VPC configuration**.
- EFS file system needs **mount targets** in the AZs used by Lambda (or supported topology); AWS recommends a mount target in each connected AZ.
- An **EFS access point** defines the root path and POSIX identity.
- Local mount path in Lambda must begin with `/mnt/`.
- Mount target SG must allow **inbound TCP 2049 (NFS)** from the Lambda SG.
- Execution role needs `elasticfilesystem:ClientMount` (and `ClientWrite` if writing), aligned with any EFS resource policy.

~~~yaml
# Conceptual CloudFormation snippet for Lambda VPC + EFS
VpcConfig:
  SubnetIds:
    - subnet-PRIVATE-A
    - subnet-PRIVATE-B
  SecurityGroupIds:
    - sg-LAMBDA
FileSystemConfigs:
  - Arn: arn:aws:elasticfilesystem:ap-southeast-1:111122223333:access-point/fsap-EXAMPLE
    LocalMountPath: /mnt/shared
~~~

This is an **illustrative snippet**, not a complete template or usable ARNs/IDs. EFS incurs storage/throughput charges and requires permission management and file locking when concurrent invocations write.

### 9.3. Calling Private HTTP APIs Inside a VPC

A Lambda function can call an **internal Application Load Balancer** or services on ECS/EC2 via private DNS names (Route 53 private hosted zones, internal ALB DNS). Check:

1. Lambda subnets route to the private ALB ENIs / target VPC.
2. Internal ALB SG allows inbound TCP 443 from the Lambda SG.
3. Listener/target groups are healthy and SGs/NACLs between ALB and ECS/EC2 permit traffic.
4. TLS hostname verification and service authN/authZ match.
5. Across VPCs, verify matching VPC peering, Transit Gateway, or PrivateLink connectivity.

**VPC Peering is non-transitive:** Lambda in VPC A cannot reach VPC C via peering links A–B and B–C. You need a direct link or a transit service.

## 10. Inbound Private Invocation Is a Separate Problem

“Can an EC2 instance inside a VPC invoke Lambda without going over the Internet?” is a completely different question from “Can Lambda reach private RDS?”

### 10.1. Client in a VPC Calling the Lambda Invoke API

Provision an **Interface VPC Endpoint** for the Lambda service:

~~~text
com.amazonaws.ap-southeast-1.lambda
~~~

With Private DNS enabled, an EC2/ECS workload in the VPC can call `lambda:InvokeFunction` via the AWS SDK over AWS PrivateLink **without NAT or public Internet** when properly configured. Requirements:

- Interface endpoint in the VPC with SG allowing inbound 443 from clients.
- Proper VPC DNS settings and Private DNS enabled.
- Caller IAM policy plus resource-based permissions if cross-account or required.
- Optional endpoint policy scoping principals, functions, and actions.

**This VPC endpoint does not connect your Lambda function to RDS.** It is an entry point to the **Lambda API** for callers sitting inside a VPC.

~~~mermaid
flowchart LR
    C["EC2/ECS client in VPC"] --> EP["Lambda interface endpoint<br/>PrivateLink"]
    EP --> API["Lambda Invoke API"]
    API --> F["Lambda execution environment"]
    F --> HE["Hyperplane ENI if function attached to VPC"]
    HE --> DB["Private database"]
~~~

### 10.2. Lambda Is Not a Private TCP Server

You cannot grab a Hyperplane ENI's private IP and open raw TCP requests straight to your handler like an EC2 instance. Valid invocation paths include:

- `InvokeFunction` via the Lambda API and IAM.
- API Gateway (REST/HTTP APIs or private REST APIs per config).
- ALB Lambda target groups (ALB invokes Lambda through service integration, not TCP to the Hyperplane ENI).
- EventBridge, SQS, SNS, S3 notifications, and event source mappings.
- Lambda Function URLs where appropriate; **IAM auth does not turn a Function URL into a private VPC endpoint**.

If an API frontend must stay strictly reachable from a private network, design an **API Gateway private API / PrivateLink** or an appropriate integration/auth model; never confuse outbound `VpcConfig` with inbound network isolation.

## 11. IAM Execution Role for VPC Lambda

Lambda needs permission to create and manage Hyperplane ENIs inside your customer VPC. AWS provides the managed policy **`AWSLambdaVPCAccessExecutionRole`**, covering EC2 ENI actions and basic CloudWatch Logs.

### 11.1. Related EC2 Actions

Per AWS documentation, the ENI permissions are:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VpcNetworkInterfaceManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Not all of these actions can be scoped by ENI ARN like standard IAM resources. `AWSLambdaVPCAccessExecutionRole` is convenient in labs, with one caveat: EC2 permissions on the **execution role** can also **be called by your function code via the EC2 API**. Do not treat that managed policy as having zero impact on attack surface.

AWS notes that ENI permissions are needed for Lambda to **create/manage attachments**, not during every individual invocation; teams sometimes evaluate removing or constraining them under runbooks, though you must account for **VPC config changes, scaling, ENI recreation, and cleanup**. Never strip permissions and delete the role before ENIs are cleaned up.

### 11.2. IAM Role Trust Policy

A Lambda execution role trusts the Lambda service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLambdaService",
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This **trust policy** lets the Lambda service assume the role; application permissions live in separate statements, such as `secretsmanager:GetSecretValue` on one secret ARN or `s3:GetObject` on one prefix.

### 11.3. Restricting EC2 APIs from Function Code

AWS documents using the **`lambda:SourceFunctionArn`** IAM condition key to **deny EC2 ENI management APIs when called by function code**, while the Lambda control plane can still create ENIs because service-level calls do not carry that condition key. Sample policy (**must be tested before deploying**):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEniApiCallsFromFunctionCode",
      "Effect": "Deny",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses"
      ],
      "Resource": "*",
      "Condition": {
        "ArnEquals": {
          "lambda:SourceFunctionArn": "arn:aws:lambda:ap-southeast-1:111122223333:function:orders-api"
        }
      }
    }
  ]
}
~~~

`lambda:SourceFunctionArn` uses the **unqualified function ARN** (no version or alias suffix). Before applying, verify the function's business logic legitimately needs no EC2 APIs, and avoid attaching a broad deny to a shared role in ways that break other functions.

### 11.4. Constraining Which VPCs a Function Can Attach To

IAM supports Lambda condition keys `lambda:VpcIds`, `lambda:SubnetIds`, and `lambda:SecurityGroupIds` to restrict deployers on `lambda:CreateFunction` and `lambda:UpdateFunctionConfiguration` to approved VPCs, subnets, and SGs. These are **control-plane guardrails**, not route tables or security group rules.

## 12. IAM for Private Services and Secrets Manager

To allow a function to read only one secret and one S3 prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDbSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/db-*"
    },
    {
      "Sid": "ReadOrderConfig",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-config-example/app/*"
    }
  ]
}
~~~

This is an **illustrative least-privilege IAM policy**; substitute your real account, secret ARN, and bucket/key. With SSE-KMS/customer-managed keys, add matching key policies and `kms:Decrypt`. Granting permission to read a secret does not create network reachability to Secrets Manager; calling it from a private subnet still requires NAT or an interface endpoint.

Never write database passwords into logs, exception messages, CloudWatch Logs, HTTP responses, or stack traces. When using Secrets Manager rotation, implement TTL caching and retry logic for rotated credentials.

### 12.1. IAM Resource Policies for Invoking Lambda

Permissions for **who invokes Lambda** live separately. API Gateway, S3, or EventBridge triggers may need resource-based permissions via `lambda:AddPermission` scoped to service principal, `SourceArn`/`SourceAccount`, and trigger. Configuring the execution role alone never allows an external trigger to invoke the function.

When an EC2 client invokes via a Lambda interface endpoint, the caller still needs `lambda:InvokeFunction`; endpoint policies can add restrictions without replacing IAM.

## 13. Configuring via AWS Management Console

General workflow:

1. Open **AWS Lambda Console → Functions → select function**.
2. Go to **Configuration → VPC → Edit**.
3. Pick the VPC containing the database/private resources (or a VPC routed to them).
4. Select **at least two private subnets in different AZs** where feasible.
5. Select a security group permitting egress to the backend; add inbound rules from the Lambda SG on RDS/Proxy/ALB SGs.
6. If IPv6 outbound is needed, check **Allow IPv6 traffic for dual-stack subnets** and confirm all subnets are dual-stack.
7. Confirm the execution role has ENI permissions; add separate S3/Secrets Manager/KMS permissions as needed.
8. Provision NAT or VPC endpoints matching real traffic paths.
9. Save and monitor `State`/`LastUpdateStatus` until update completes.
10. Test with a valid request and inspect logs, DB metrics, and network errors.

**Never modify production VPC settings directly just to “test Internet access.”** Changes impact all invocations, concurrency, and connectivity; use lab environments, IaC/code reviews, and rollback plans.

## 14. Read-Only AWS CLI: Inspecting Function `VpcConfig`

Examples use AWS CLI v2, a read-only `dev` profile, Region `ap-southeast-1`, and function `orders-api`. Substitute your real environment before running.

### 14.1. Verify Account/Role

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{FunctionName:FunctionName,State:State,LastUpdate:LastUpdateStatus,Role:Role,Vpc:VpcConfig,Timeout:Timeout,MemoryMB:MemorySize}' \
  --output json
~~~

If `VpcConfig.VpcId` is empty, the function has no customer VPC attached. `State=Active` only means Lambda is ready at the platform level — it does not prove RDS or Secrets Manager connectivity works.

### 14.2. Inspect Subnets and Route Tables

~~~bash
aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Subnets[].{Subnet:SubnetId,AZ:AvailabilityZone,Cidr:CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock,AvailableIPs:AvailableIpAddressCount}' \
  --output json

aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Find the **route table associated with the exact subnets in Lambda's `VpcConfig`**. A subnet without an explicit association inherits the **main route table**. Verify routes to DB CIDRs, NAT, S3 Gateway endpoints, or TGW/peering as designed.

### 14.3. Inspect Security Groups and Endpoints

~~~bash
aws ec2 describe-security-groups \
  --group-ids sg-LAMBDA sg-DB \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,State:State,PrivateDns:PrivateDnsEnabled,RouteTables:RouteTableIds}' \
  --output json
~~~

IDs `vpc-EXAMPLE`, `sg-LAMBDA`, and `sg-DB` are **placeholders**; commands fail unless replaced. Interface Endpoints use ENIs and SGs; Gateway Endpoints use route table associations. Never assume an endpoint is missing just because `RouteTables` is empty on an **Interface** endpoint.

### 14.4. Inspect Hyperplane ENIs When Permitted

~~~bash
aws ec2 describe-network-interfaces \
  --filters Name=interface-type,Values=lambda \
  --profile dev \
  --region ap-southeast-1 \
  --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,Subnet:SubnetId,Vpc:VpcId,Type:InterfaceType,Status:Status,Description:Description}' \
  --output table
~~~

Lambda-managed ENIs carry distinct metadata and interface types. You might lack permissions or see propagation lag; never delete an ENI just because its description mentions “Lambda.” Hyperplane ENIs can be shared across functions/versions in the account.

## 15. Modifying Configuration via CLI and IaC

The examples below **modify AWS resources** if executed with valid credentials and IDs. Use only in authorized environments with change approval.

### 15.1. VPC Config File for CLI

Create `vpc-config.json` with real IDs:

~~~json
{
  "SubnetIds": [
    "subnet-EXAMPLE-PRIVATE-A",
    "subnet-EXAMPLE-PRIVATE-B"
  ],
  "SecurityGroupIds": [
    "sg-EXAMPLE-LAMBDA"
  ],
  "Ipv6AllowedForDualStack": false
}
~~~

Apply:

~~~bash
# MODIFIES FUNCTION CONFIGURATION - do not run in production without approval.
aws lambda update-function-configuration \
  --function-name orders-api \
  --vpc-config file://vpc-config.json \
  --profile dev \
  --region ap-southeast-1
~~~

After changing `VpcConfig`, wait for completion:

~~~bash
# Waiter only polls status; does not modify the function.
aws lambda wait function-updated \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{State:State,LastUpdateStatus:LastUpdateStatus,Reason:LastUpdateStatusReason,Vpc:VpcConfig}' \
  --output json
~~~

Replace placeholder subnet and SG IDs before running. In PowerShell, passing `file://vpc-config.json` avoids inline shell JSON quoting headaches.

### 15.2. AWS SAM Template Example

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: 'Example Lambda with VPC access (illustrative)'
Parameters:
  PrivateSubnetA:
    Type: AWS::EC2::Subnet::Id
  PrivateSubnetB:
    Type: AWS::EC2::Subnet::Id
  LambdaSecurityGroup:
    Type: AWS::EC2::SecurityGroup::Id
Resources:
  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: orders-api-example
      Runtime: java21
      Handler: com.example.OrdersHandler::handleRequest
      CodeUri: target/orders-lambda.jar
      MemorySize: 512
      Timeout: 15
      VpcConfig:
        SubnetIds:
          - !Ref PrivateSubnetA
          - !Ref PrivateSubnetB
        SecurityGroupIds:
          - !Ref LambdaSecurityGroup
        Ipv6AllowedForDualStack: false
      Policies:
        - AWSLambdaVPCAccessExecutionRole
~~~

This is an **illustrative template**, without databases, secrets, or bundled source code, and is not production-ready as written. `Policies: AWSLambdaVPCAccessExecutionRole` grants ENI permissions but **does not grant Secrets Manager or S3 business permissions**. Add least-privilege roles/policies, network endpoints, logs, alarms, build artifacts, CI/CD, and IAM security checks.

## 16. Java 21 Lambda Connecting to RDS Proxy and Secrets Manager

The example below illustrates a **private DB flow** in code. Assumptions:

- Lambda has `VpcConfig` and an SG permitting TCP 5432 to the RDS Proxy private endpoint.
- Secrets Manager holds JSON with `username` and `password` keys.
- The execution role grants `secretsmanager:GetSecretValue` on that secret and matching KMS permissions.
- Lambda reaches Secrets Manager via an interface endpoint or NAT.
- The PostgreSQL endpoint uses TLS with a properly configured CA/trust store.

### 16.1. Java Handler

~~~java
package com.example;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Map;

public class OrdersDbHealthHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    private static final ObjectMapper JSON = new ObjectMapper();

    // Reuse the SDK client across invocations in the same execution environment.
    private static final SecretsManagerClient SECRETS =
            SecretsManagerClient.builder()
                    .region(Region.of(System.getenv("AWS_REGION")))
                    .build();

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event, Context context) {

        try {
            String secretId = requiredEnv("DB_SECRET_ARN");
            String proxyHost = requiredEnv("DB_PROXY_HOST");
            String database = requiredEnv("DB_NAME");

            String rawSecret = SECRETS.getSecretValue(
                    GetSecretValueRequest.builder()
                            .secretId(secretId)
                            .build())
                    .secretString();
            JsonNode creds = JSON.readTree(rawSecret);

            // With RDS Proxy, use the proxy's exact DNS hostname.
            // verify-full requires valid CA trust and hostname verification.
            String jdbcUrl = "jdbc:postgresql://" + proxyHost
                    + ":5432/" + database
                    + "?sslmode=verify-full&connectTimeout=3&socketTimeout=5";

            try (Connection conn = DriverManager.getConnection(
                            jdbcUrl,
                            creds.path("username").asText(),
                            creds.path("password").asText());
                 PreparedStatement statement = conn.prepareStatement("SELECT 1");
                 ResultSet result = statement.executeQuery()) {

                boolean ok = result.next() && result.getInt(1) == 1;
                return Map.of("status", ok ? "ok" : "unhealthy");
            }
        } catch (Exception e) {
            // Never log secrets, JDBC URLs with sensitive parameters, or SQL payloads.
            context.getLogger().log(
                    "Database health check failed: "
                    + e.getClass().getSimpleName());
            throw new IllegalStateException("Database unavailable");
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing configuration: " + key);
        }
        return value;
    }
}
~~~

Key Maven/Gradle dependencies include `aws-lambda-java-core`, `software.amazon.awssdk:secretsmanager`, the PostgreSQL JDBC driver, and `jackson-databind` (versions managed via BOM/lockfile). This is a **learning example**, not a production repository. Ensure your packaged artifact fits the Lambda Java runtime and configures certificate trust properly.

### 16.2. Why Must This Code Be Improved Before Production?

- **Cache Secrets Manager** using a TTL/rotation strategy instead of calling the API on every invocation; consider the AWS Parameters and Secrets Lambda Extension or supported caching libraries.
- Reuse **DB connections** properly or pair with RDS Proxy / IAM DB auth. Opening and closing a connection per call above is for clarity, not optimal performance.
- Set **Lambda timeout** safely above expected network timeouts and enforce bounded timeouts, circuit breakers, and retries.
- Use prepared statements for all SQL handling request input; `SELECT 1` takes none.
- Cap Lambda concurrency so the database and proxy are not overwhelmed.
- Run schema migrations in a dedicated pipeline step, never running DDL inside every handler invocation.

### 16.3. Common Code Errors

If `SecretsManagerClient` throws connection timeouts, inspect the endpoint/NAT and port 443 SG. If it throws `AccessDeniedException`, inspect the IAM secret ARN and KMS key policy. If JDBC times out, inspect port 5432 SGs, DNS/routes, and Proxy/DB health. If JDBC fails authentication, inspect secret rotation or IAM DB auth — **never add IAM wildcards** to fix a database password issue.

## 17. Triggers, Concurrency, and Backend Impact

### 17.1. Event Sources Do Not Hit Your Lambda ENI Like an Inbound Server

| Trigger | Core mechanism | VPC consideration |
|---|---|---|
| API Gateway | API Gateway invokes Lambda | `VpcConfig` governs **outbound code calls**, not API Gateway TCP into your ENI |
| EventBridge rule | EventBridge calls Lambda via integration permissions | No inbound SG needed on Lambda |
| S3 event notification | S3 service invokes Lambda | Only code calling S3 needs an endpoint/NAT from the customer VPC |
| SQS event source mapping | Lambda service polls SQS and invokes | Only code calling `SendMessage` needs an SQS network path |
| ALB Lambda target | ALB uses service integration to invoke Lambda | Not a direct TCP connection to the Hyperplane ENI |
| EC2/ECS calling `InvokeFunction` | AWS Lambda API | Can use a Lambda interface endpoint inside the caller's VPC |

### 17.2. Rapid Concurrency Scaling

Lambda spins up execution environments rapidly under bursty event loads. A small database or ElastiCache cluster may not keep up. Design:

- **Reserved concurrency** on the function to cap concurrent invocations when needed.
- RDS Proxy or proper SQL pooling.
- SQS queues and batch/window tuning to absorb bursts.
- Retries/backoff with jitter to avoid retry storms, plus dead-letter/redrive policies.
- **Idempotency** so retries never produce duplicate writes.
- Monitor `ConcurrentExecutions`, `Throttles`, `Duration`, DB connections, and downstream latency.

Reserved concurrency shields the DB from spikes, yet setting it too low increases throttling and queue lag. Tune against SLOs and real measurements.

### 17.3. Cold Starts vs. Hyperplane ENI Provisioning

Do not confuse a **cold start** (initializing the Java runtime and app) with **initial Hyperplane ENI creation** when attaching a VPC. Hyperplane ENIs are reused across invocations, while Java initialization still depends on memory/CPU, dependencies, TLS connections, SDK clients, and DB bootstrapping. Use CloudWatch `Init Duration`, distributed tracing/metrics, and load tests to isolate causes.

## 18. Monitoring, Security, and Incident Response

### 18.1. CloudWatch and Lambda Logs

Monitor:

- Lambda metrics: `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions`, and `IteratorAge` (where applicable).
- `State`/`LastUpdateStatus` during VPC updates or `Inactive`/`Pending` transitions.
- Application logs containing correlation/request IDs, HTTP/JDBC status, and per-dependency latency — **never printing secrets**.
- RDS/Proxy metrics: client/backend connections, borrow latency, DB CPU, and active connections.
- NAT Gateway metrics/costs and Interface Endpoint metrics/flow logs where relevant.
- X-Ray/OpenTelemetry tracing to separate network time from application processing time.

### 18.2. VPC Flow Logs, Reachability Analyzer, and CloudTrail

- **VPC Flow Logs:** inspect IP/port/protocol and `ACCEPT`/`REJECT` records on ENIs/subnets/VPCs; note `ACCEPT` only proves packets passed, not that the backend returned HTTP/SQL success.
- **Reachability Analyzer:** traces network paths and identifies blocking components between supported sources and destinations.
- **CloudTrail:** audits who called `UpdateFunctionConfiguration`, altered IAM roles, SGs, route tables, or created endpoints. CloudTrail does not replace application tracing.
- **IAM Access Analyzer / AWS Config / Security Hub:** evaluates overly broad permissions, public exposure, and organizational compliance.

### 18.3. Guardrails

- Restrict who can attach functions to VPCs/subnets/SGs using IAM condition keys.
- Scope execution roles strictly to required secrets and keys; never use `AdministratorAccess`.
- Keep endpoint policies, bucket policies, and SGs tightly scoped.
- Encrypt secrets and environment variables with KMS; enforce TLS for DBs and APIs.
- Never store plaintext secrets in env vars, logs, or tracing span attributes.
- Maintain IaC/approvals and rollback procedures if a VPC update breaks connectivity.

## 19. Troubleshooting: Common Issues

| Symptom | Common root cause | First check |
|---|---|---|
| New function stays `Pending` after VPC attach | Hyperplane ENI provisioning, missing EC2 permissions, or subnet out of IPs | `StateReason`/`LastUpdateStatusReason`, execution role, subnet available IPs |
| Function becomes `Inactive` after long idle period | Hyperplane ENI reclaimed after 14 days idle | Check `State`; allow reinitialization before retrying |
| `ENILimitReachedException` | VPC/ENI quota or interface management limits | Check ENI/service quotas and request adjustments if needed |
| Lambda calling RDS times out | SG egress/inbound 5432, routes, DNS, or Proxy/DB health | Lambda and DB/Proxy SGs, subnet route associations |
| Lambda calling Secrets Manager times out | Missing NAT/Secrets Manager endpoint, wrong endpoint SG or DNS | VPC endpoint or NAT, Private DNS, TCP 443 |
| `SecretsManager AccessDenied` | IAM role, secret policy, or KMS deny | Execution role, secret ARN, KMS key policy |
| AWS SDK calling S3 from VPC times out | Missing Gateway endpoint/NAT or broken route | Route table S3 prefix list, policies, Region |
| Attached Lambda to public subnet yet no Internet | No public IP on Hyperplane ENI | Move to private subnet + NAT for IPv4 |
| IPv6 outbound fails | Not all subnets are dual-stack, IPv6 disabled, or missing `::/0` egress | `Ipv6AllowedForDualStack`, subnet IPv6 CIDRs, routes/SGs |
| API Gateway cannot invoke Lambda | Bad invoke permission or integration | Lambda resource policy, API Gateway logs; **never** open inbound on Lambda SG |
| EC2 cannot call `InvokeFunction` privately | Missing Lambda interface endpoint, DNS, SG, or IAM | `com.amazonaws.region.lambda`, endpoint SG 443, caller IAM |
| Function `running` yet SQL auth fails | Wrong/rotated secret, JDBC TLS, or DB user | RDS Proxy/DB auth, secret version, TLS |
| RDS hits `max_connections` | Lambda concurrency or connection pool too wide | `ConcurrentExecutions`, RDS/Proxy metrics |
| NACL causes intermittent TCP failures | Return ephemeral ports blocked | Permit TCP/UDP `1024–65535` per AWS guidance |
| Interface endpoint DNS returns public IP | Private DNS / VPC DNS attributes disabled or wrong forwarding | Endpoint settings and Route 53 Resolver |
| VPC B cannot reach VPC C via VPC A | Peering is non-transitive | Direct peering, Transit Gateway, or PrivateLink |
| S3/SQS trigger stops firing | Broken event source mapping or resource permission | Trigger config/IAM — do not confuse with Lambda VPC egress |
| Function times out calling external API | Missing NAT/Internet egress or remote timeout | `0.0.0.0/0` → NAT, NAT SG/NACL, remote DNS |
| High NAT bill despite only calling S3 | S3 traffic routing through NAT instead of Gateway endpoint | Endpoints/route tables and AWS billing |

### 19.1. 7-Step Diagnostic Workflow

1. Confirm the exact **AWS account, Region, function ARN, and `VpcConfig`**.
2. Check **`State`/`LastUpdateStatus`** to distinguish provisioning from an `Active` function.
3. Write down the exact **destination hostname/IP, TCP port, and AWS API service**.
4. Verify DNS resolution and the route tables of the **exact Lambda subnets**.
5. Inspect SG egress/inbound rules and NACLs (including ephemeral return ports).
6. Inspect IAM execution role, resource policies, KMS key policies, and endpoint policies independently.
7. Cross-check CloudWatch Logs, Flow Logs, and DB/Proxy metrics, then retest with an approved minimal test case.

**Never adopt “open all ports and grant admin to test”** as a standard workflow. When isolating root causes, use read-only CLI inspection and rollback-ready lab changes.

## 20. Cost and Resilient Architecture

### 20.1. Separating Cost Components

| Component | Common charges |
|---|---|
| Lambda compute | Invocations, duration, and enabled features |
| Hyperplane ENI | Not managed or billed as a separate EC2 instance; look at VPC network charges |
| NAT Gateway | Hourly charge plus data processed; cross-AZ transfer if crossing AZs |
| Interface VPC Endpoint | Endpoint-hours per AZ plus data processing |
| Gateway Endpoint (S3/DynamoDB) | No hourly or data-processing fee for standard Gateway endpoints |
| RDS / RDS Proxy | DB compute/storage/I/O and proxy charges |
| EFS | Storage/throughput and related fees |
| CloudWatch/X-Ray/CloudTrail | Log ingestion, retention, traces, and audit trails |
| Data transfer | Per AZ/Region/Internet/service path depending on topology |

A function without NAT that only calls **S3 and Secrets Manager** can use an S3 Gateway Endpoint and a Secrets Manager Interface Endpoint instead of running a NAT Gateway purely for those two flows. Still, Interface Endpoints carry hourly/data charges, so compare total cost against traffic volume, AZ count, endpoint count, and SLOs.

### 20.2. High Availability

- Use at least two private subnets/AZs where appropriate.
- If using NAT for steady IPv4 egress, deploy NAT per AZ with AZ-local route tables for HA.
- Place Interface Endpoint ENIs in the same AZs with matching SGs and Private DNS.
- Use Multi-AZ RDS where needed; pair with RDS Proxy for connection management and smoother failovers.
- Bound concurrency, timeouts, and retries to what DB/Redis/HTTP backends can sustain.
- Never mistake VPC attachment for a disaster recovery plan; implement backups, replication, and cross-Region failover if required.

### 20.3. When Should You Attach a VPC?

| Workload | `VpcConfig` needed? | Why |
|---|---|---|
| Process S3 events and write DynamoDB | **Not required** | Can call AWS service APIs from the Lambda-managed environment |
| Query a private RDS endpoint | **Usually yes** | Needs private network path to DB |
| Call a private ElastiCache cluster | **Needs private path** | Cache private IPs and SGs |
| Mount EFS | **Yes** | Connects to EFS mount targets inside VPC |
| Call external public REST API | **Not required** | Attaching a VPC would force adding NAT/IPv6 egress |
| EC2 invokes Lambda via PrivateLink | **Does not require VPC on Lambda** | The Lambda interface endpoint sits in the **caller's VPC** |
| Call services across VPCs via PrivateLink | **Design-dependent** | Lambda connects to an endpoint inside its attached VPC |

## 21. Read-Only Practice Exercise: Analyzing a Lambda VPC Architecture

### 21.1. Prerequisites

- AWS CLI v2 and a `dev` profile with read access to Lambda, EC2, IAM, and related resources.
- If read access is available, inspect a lab function and VPC; otherwise analyze the diagrams, tables, and JSON examples.
- **Do not create NAT Gateways or endpoints, alter SGs, change `VpcConfig`, or invoke production functions** in this baseline lab.
- All IDs in commands are placeholders; substitute authorized lab resources if running live.

### 21.2. Part A — Identify the Network Attachment

~~~bash
aws sts get-caller-identity --profile dev

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Name:FunctionName,State:State,Vpc:VpcConfig,Role:Role}' \
  --output json
~~~

Record the VPC ID, subnet IDs, SG IDs, and `Ipv6AllowedForDualStack`. If `VpcConfig` is empty, explain how (or whether) the function could reach private RDS (for example, if another supported network resource feature is configured).

### 21.3. Part B — Inspect Routes and Security Groups

~~~bash
aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-security-groups \
  --group-ids sg-LAMBDA sg-DB \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Questions: Does Lambda have a local route to private RDS? Does the DB SG open the right port from the Lambda SG? If SQL times out while Secrets Manager succeeds, what should you inspect first?

### 21.4. Part C — Inspect Endpoints

~~~bash
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Classify Gateway Endpoints vs. Interface Endpoints. For S3: is the endpoint attached to the right route tables? For Secrets Manager: does the endpoint SG allow inbound 443 and is Private DNS enabled?

### 21.5. Part D — Decide Whether NAT Is Needed

Suppose the function calls only:

1. Private RDS PostgreSQL in the same VPC.
2. Secrets Manager via an interface endpoint.
3. Same-Region S3 via a gateway endpoint.

Question: Is a NAT Gateway needed **solely for these three flows**? **No**, provided all service, endpoint, network, SG, and IAM settings are complete. If the function later calls an external payment API with only a public IPv4 endpoint, you must add egress (e.g., NAT Gateway) or redesign the integration.

### 21.6. Part E — Distinguish Trigger Plane vs. Data Plane

An SQS queue triggers Lambda, and Lambda writes to RDS. If the SQS VPC endpoint is removed while the Lambda service continues polling the queue, can the trigger still fire? Under standard Lambda-managed event source mapping, **yes**; verify trigger IAM/config. However, if **function code** itself calls SQS from a private subnet, it needs a network path to SQS.

### 21.7. Part F — Build a Runbook Table

Create a checklist table:

| Component | Verified? | Owner | Risk |
|---|---|---|---|
| Lambda `VpcConfig` and status | ... | App team | ENI pending/inactive |
| Private subnet AZs/routes | ... | Network | Single AZ / NAT |
| Lambda SG → RDS Proxy SG | ... | Network/DBA | JDBC timeout |
| Secrets Manager endpoint | ... | Platform | Cannot retrieve credentials |
| IAM/KMS/bucket policies | ... | Security | `AccessDenied` |
| DB connections and concurrency | ... | App/DBA | DB exhaustion |
| CloudWatch/Flow Logs/alarms | ... | SRE | Blind to failures |
| Backups/rollback | ... | App/DBA | Data loss / outage |

## 22. Architecture Scenario and Self-Check Questions

### 22.1. Scenario: Order Processing API

An API Gateway route invokes a Java Lambda. Lambda queries private PostgreSQL RDS and writes invoice objects to S3. The app requires TLS to the DB, managed secrets, and zero public Internet access.

Sound design:

1. Attach Lambda to two private subnets in distinct AZs in the same VPC as RDS Proxy.
2. Allow Lambda SG egress 5432 to Proxy; allow Proxy SG inbound 5432 from Lambda.
3. Deploy a Secrets Manager Interface Endpoint with SG inbound 443 from Lambda; grant `GetSecretValue`/KMS on the role.
4. Attach an S3 Gateway Endpoint to the private route tables; grant `PutObject` on the exact bucket prefix.
5. Use RDS Proxy for connection pooling and Lambda reserved concurrency to protect the DB.
6. Let API Gateway invoke Lambda via integration permissions; **never open inbound rules on the Lambda SG**.
7. Enable CloudWatch/X-Ray/CloudTrail alongside backup and rollback runbooks.

### 22.2. Self-Check Questions

1. Does attaching Lambda to a customer VPC mean execution environments run directly inside that subnet?
2. Is a separate Hyperplane ENI created for every single invocation?
3. Why can a newly VPC-attached function stay in `Pending`?
4. What can happen after 14 days of a function sitting idle?
5. Does Lambda gain Internet access merely by choosing a public subnet?
6. How do Gateway VPC Endpoints and Interface Endpoints differ?
7. To call Secrets Manager from a private subnet without NAT, what is needed besides IAM permissions?
8. Must same-Region S3 calls from a VPC-attached Lambda always traverse NAT?
9. Why does the Lambda SG not need inbound rules to receive triggers from API Gateway?
10. How do RDS Proxy SG inbound and Lambda SG outbound differ on TCP 5432?
11. With restrictive NACLs, which ephemeral port range does AWS highlight for Lambda VPC traffic?
12. Which endpoint type does an EC2 instance inside a VPC need to call the Lambda Invoke API without Internet?
13. How do Lambda `VpcConfig` and the `com.amazonaws.region.lambda` endpoint differ in purpose?
14. Which EC2 APIs does `AWSLambdaVPCAccessExecutionRole` allow, and why review its security impact?
15. In what scenario can `lambda:SourceFunctionArn` be used?
16. Why can direct RDS run out of connections when Lambda concurrency surges?
17. Can Lambda mount EFS without a VPC connection?
18. For IPv6 outbound, what condition applies to **all subnets**?
19. Why might a function report `State=Active` yet still see JDBC timeouts?
20. If an application only processes S3/SQS/DynamoDB events via AWS APIs, is VPC attachment always needed?

### Directional Answers

- **Hyperplane ENI:** bridges Lambda-managed execution environments into your customer VPC; it is not an inbound private server.
- **Networking:** private subnets + route tables + SGs/NACLs + DNS; use NAT for IPv4 Internet and VPC endpoints for AWS APIs.
- **RDS:** align directional SGs, Secrets Manager / IAM DB auth, and RDS Proxy when connection pooling is needed.
- **Invoke:** VPC clients calling Lambda via a Lambda interface endpoint is distinct from outbound `VpcConfig`.
- **Operations:** least-privilege IAM, AZ alignment, ENI status awareness, concurrency caps, logs, metrics, and full network cost tracking.

## 23. Official AWS References

1. [Giving Lambda functions access to resources in an Amazon VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html) — Customer VPC, Hyperplane ENIs, IAM, and IPv6.
2. [Enable internet access for VPC-connected Lambda functions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html) — Private subnets, NAT Gateway, Internet egress.
3. [Troubleshoot networking issues in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting-networking.html) — NACL ephemeral ports, VPC endpoints, and timeout errors.
4. [Connecting inbound interface VPC endpoints for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-endpoints.html) — Private invoke via the Lambda API.
5. [AWS Lambda with Amazon RDS](https://docs.aws.amazon.com/lambda/latest/dg/services-rds.html) — Direct RDS connections and RDS Proxy.
6. [Automatically connecting Lambda functions and RDS DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/lambda-rds-connect.html) — VPC, SGs, and RDS auto-connect.
7. [RDS Proxy connection management](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html) — Pooling, limits, and failover.
8. [RDS Proxy network prerequisites](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-network-prereqs.html) — VPC, subnets, AZs, and SGs.
9. [Lambda with EFS file systems](https://docs.aws.amazon.com/lambda/latest/dg/configuration-filesystem-efs.html) — Access points, mount targets, NFS/2049.
10. [Access AWS services through VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html) — PrivateLink interface endpoints and Private DNS.
11. [S3 Gateway VPC Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html) — Route tables, endpoint policies, and limits.
12. [DynamoDB Gateway Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-ddb.html) — Private DynamoDB access.
13. [Using source function ARN for IAM access control](https://docs.aws.amazon.com/lambda/latest/dg/permissions-source-function-arn.html) — `lambda:SourceFunctionArn`.
14. [Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html) — Role trust, permissions, and least privilege.
15. [Lambda permissions and resource-based policies](https://docs.aws.amazon.com/lambda/latest/dg/access-control-resource-based.html) — Invoke authorization.
16. [AWS CLI get-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/get-function-configuration.html) — Reading `VpcConfig`, state, and execution role.
17. [AWS CLI update-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-configuration.html) — Updating subnets/SGs/IPv6.
18. [Using AWS SAM with Lambda VPC](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html) — IaC `VpcConfig`.
19. [Amazon VPC security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — Stateful rules.
20. [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — Network diagnostics.
21. [Lambda pricing](https://aws.amazon.com/lambda/pricing/) — Requests, duration, and feature pricing.
22. [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/) — Interface endpoint-hours and data processing.
23. [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) — NAT Gateway, IPv4, and data transfer.

> **Takeaway:** Lambda attaches to a VPC **so outbound code can reach private resources**. Plan subnets/AZs, Hyperplane ENIs, route tables, SGs/NACLs, DNS, NAT/PrivateLink, IAM, and backend capacity together. **VPC attachment does not create an inbound TCP server**; private callers invoking Lambda must go through supported integrations or the Lambda API. Only when networking, identity, application behavior, reliability, and billing are designed together is a serverless architecture truly secure and resilient.
