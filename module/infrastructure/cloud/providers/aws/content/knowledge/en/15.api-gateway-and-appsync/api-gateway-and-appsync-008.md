# Private APIs, VPC Links, and Backends Inside a VPC

A Java/Spring Boot application running on Amazon ECS or EC2 commonly sits behind an **internal Application Load Balancer (ALB)** in private subnets. The engineering team wants **Amazon API Gateway** to handle authentication, routing, throttling, metrics, and versioning without assigning a public IP to the backend. Another system wants **the API endpoint itself to be reachable only from internal networks**. These two requirements sound similar, yet they rely on **two distinct mechanisms** in AWS:

- **Private API:** Restricts **how clients reach API Gateway**. In API Gateway, the **`PRIVATE`** endpoint type is currently supported only on **REST API**; clients connect through an **Interface VPC Endpoint for `execute-api`**.
- **Private integration via VPC Link:** Connects **API Gateway to an HTTP/HTTPS backend inside a VPC**. An API using a VPC Link can still have a **public client-facing endpoint** unless you also configure a private endpoint or separate access controls.
- **AWS AppSync Private API:** Exposes a private **GraphQL/Realtime API** via an **AppSync Interface VPC Endpoint**; you do not use an API Gateway VPC Link to reach a GraphQL endpoint.

This lesson belongs to the **API Gateway and AppSync** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects with Regions/AZs, IAM, VPCs, Route 53, ECS/EC2, Lambda, RDS, CloudWatch, content delivery, resilience, and cost control. The ultimate goal is designing a **client → API → backend** path that is sound at both the network and authorization layers, highly available, and observable when failures happen.

> **First takeaway:** **Private API** defines *who can enter API Gateway and over which network path*; **VPC Link** defines *how API Gateway reaches a backend inside a VPC*. They are independent and **can be combined** within the same REST API.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Private REST API**, **REST/HTTP API private integration**, **VPC Link V1/V2**, **AWS AppSync Private API**, and **AWS PrivateLink**.
2. Explain the flow: client → `execute-api` Interface Endpoint → Private REST API → integration → backend.
3. State the requirements for API Gateway to connect to an **ALB, NLB, or AWS Cloud Map** via VPC Link V2 and understand per-API-type limitations.
4. Design private subnets, Security Groups, routing, NACLs, DNS, and TLS for VPC Links and ECS/EC2 backends.
5. Configure **API resource policies** using `aws:SourceVpce`/`aws:SourceVpc`, VPC endpoint policies, and method authorization.
6. Explain VPC Link V2 **immutable subnets/SGs**, `PENDING`/`AVAILABLE`/`INACTIVE` states, and the 60-day inactivity lifecycle.
7. Diagnose **stage path prefix** issues, `Host`/SNI/TLS mismatches, target group health, IAM permissions, endpoint Private DNS caveats, and cross-account connectivity.
8. Distinguish **AppSync data-plane** `appsync-api` endpoints from **control-plane** `appsync` endpoints, and understand visibility immutability after creation.
9. Inspect configurations via the AWS Console/CLI in a **read-only** manner, separating network troubleshooting from application bugs.
10. Evaluate security risks, latency, Multi-AZ resilience, rollout downtime, and total cost across API Gateway, PrivateLink, and ALB.

## 2. Three Common Architectures

### 2.1. Public API, Private Backend

Suppose Internet users call `https://api.example.com/orders`, while the Spring Boot backend has no Internet-facing load balancer:

~~~mermaid
flowchart LR
    I["Internet client"] --> A["API Gateway HTTP API or REST Regional"]
    A --> V["VPC Link V2"]
    subgraph VPC["Customer VPC"]
      V --> L["Internal ALB / NLB"]
      L --> S["ECS/EC2: Spring Boot"]
      S --> R["RDS private"]
    end
~~~

**Characteristics:** The API endpoint is reachable from the Internet subject to configured authorization. VPC Link only keeps the **API Gateway → ALB/NLB/backend** segment private—it does not make the client-facing API private.

### 2.2. Private REST API for Internal Clients Only

An EC2 instance in a VPC or an on-premises client over VPN/Direct Connect calls the API, backed by a Lambda integration:

~~~mermaid
flowchart LR
    C["EC2/ECS/on-prem client with VPC route"] --> E["Interface VPCE: execute-api"]
    E --> A["API Gateway REST API, EndpointType PRIVATE"]
    A --> L["Lambda integration"]
    L --> D["S3 / RDS / DynamoDB per VpcConfig"]
~~~

**Characteristics:** Clients must traverse an **Interface Endpoint** and satisfy the resource policy. You do not need a VPC Link simply because the API endpoint is `PRIVATE` or the backend is Lambda—API Gateway provides native Lambda integration. If Lambda itself needs to reach a private RDS database, **Lambda `VpcConfig`** handles that hop.

### 2.3. Private REST API + Private HTTP Backend

Combine both mechanisms when **both clients and the backend** require private paths:

~~~mermaid
flowchart LR
    C["Internal client"] --> E["execute-api Interface Endpoint"]
    E --> R["API Gateway PRIVATE REST API"]
    R --> V["VPC Link V2"]
    subgraph VPC["Backend VPC"]
      V --> ALB["Internal ALB"]
      ALB --> ECS["ECS/EC2 Spring Boot"]
      ECS --> DB["Private database"]
    end
~~~

**Characteristics:** Ingress is governed by endpoint and resource policies, while backend egress goes through VPC Link. Each side has its **own IAM, routing, SGs, DNS, and cost drivers**.

## 3. Decision Matrix: What Is Actually Private?

| Component / question | Private REST API | API with VPC Link | AppSync Private API |
|---|---|---|---|
| Which segment is isolated? | **Client → API Gateway** | **API Gateway → VPC backend** | **Client → AppSync GraphQL/Realtime** |
| API type | **REST** | **REST or HTTP**; WebSocket has separate constraints | **AWS AppSync GraphQL** |
| Must client be in VPC/VPN/DX? | Must reach **`execute-api` VPCE** | **Not necessarily**; frontend can be public | Must reach **`appsync-api` VPCE** |
| Core resources | Interface VPCE, API resource policy | VPC Link V2, subnets, SGs, ALB/NLB/Cloud Map | AppSync private visibility, Interface VPCE |
| Is VPC Link mandatory? | No | Yes for private HTTP/HTTPS integrations | No |
| Automatically secures backend? | No | Does not replace SGs/auth/TLS | No; still depends on data sources |
| IAM/authorization | Method auth + resource/endpoint policies | Frontend authorizer + separate backend auth | GraphQL auth + endpoint policy |
| Where data lives | Any supported integration target | Backend inside private VPC topology | AppSync data sources and supported AWS services |

**Common mistake:** Seeing the phrase "private integration" and assuming the entire API is private. An HTTP API calling a private ALB via VPC Link still exposes a **Regional public invoke endpoint** unless you restrict clients separately.

## 4. Private REST API: `execute-api` Interface Endpoint

### 4.1. What Is the `PRIVATE` Endpoint Type?

API Gateway REST APIs offer three endpoint types: **Regional**, **edge-optimized**, and **Private**. A Private REST API prevents normal direct Internet invocation; clients connect through an **Interface VPC Endpoint** (AWS PrivateLink) for the service:

~~~text
com.amazonaws.ap-southeast-1.execute-api
~~~

The example above uses the Singapore Region. The VPCE provisions network interfaces with private IPs in your chosen subnets. The VPC endpoint Security Group must allow **inbound TCP 443** from clients, and VPC / Route 53 Resolver must resolve the API hostname to the endpoint when Private DNS is enabled.

Private REST APIs support TLS 1.2 and dualstack IP addressing per current documentation. That describes the **private API endpoint**, not a guarantee that every downstream backend behind an integration only speaks TLS 1.2.

### 4.2. One VPCE Can Serve Multiple Private REST APIs

You do not need a separate interface endpoint per REST API. One `execute-api` VPC endpoint can serve **multiple authorized private APIs** in the matching account/Region, provided:

1. The VPC endpoint is healthy and its Security Group permits traffic.
2. Each API's resource policy permits the **VPC/VPCE**.
3. The endpoint policy allows the target API, method, and principal.
4. Method authorization (such as `AWS_IAM`) permits the caller.
5. DNS or private custom domain associations match the invoked URL.

A working network path **does not** automatically mean every API authorizes every caller.

### 4.3. On-Premises Calling a Private API

Data-center clients can reach the VPCE over **AWS Direct Connect or VPN** with appropriate private routing and DNS. On-premises clients **must still route through the Interface VPCE** to invoke a Private REST API—having a VPN into the VPC does not give the API a standalone private IP outside the endpoint.

For DNS resolution from on-premises, you may need a Route 53 Resolver inbound endpoint or forwarding rules depending on your DNS design. VPN/DX routes must reach the endpoint ENI private IPs, and SGs/NACLs must permit HTTPS.

## 5. Resource Policies, Endpoint Policies, and Method Authorization

Protect a Private REST API across multiple layers:

| Layer | Configuration | What it decides |
|---|---|---|
| **Client network** | VPC route/DNS to Interface VPCE, VPCE SG TCP 443 | Can packets reach the VPCE? |
| **VPC endpoint policy** | Policy attached to `execute-api` VPCE | Which APIs, principals, and actions may traverse the endpoint? |
| **REST API resource policy** | `aws:SourceVpce`, `aws:SourceVpc`, principal | Which endpoints or VPCs may invoke this API? |
| **Method authorization** | `AWS_IAM`, Cognito/Lambda authorizer, etc. | Which user or workload may invoke this method? |
| **Backend security** | VPC Link SG, ALB listener, JWT/service auth | Will the backend accept the request forwarded by API Gateway? |

### 5.1. Resource Policy Scoped to a Specific VPC Endpoint

**Illustrative** example—replace `vpce-0123456789abcdef0` with a real VPCE ID:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PermitInvocationSubjectToVpceRestriction",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*"
    },
    {
      "Sid": "DenyRequestsFromOtherEndpoints",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*",
      "Condition": {
        "StringNotEquals": {
          "aws:SourceVpce": "vpce-0123456789abcdef0"
        }
      }
    }
  ]
}
~~~

**Meaning:** The resource policy permits traffic only via **one specific VPCE**, explicitly denying all other sources. However, `Principal: "*"` does not authenticate individual users. On sensitive methods, also enable **`AWS_IAM` or an authorizer**, pairing endpoint policies with least privilege.

In API Gateway, `execute-api:/*` is a **shorthand ARN syntax** inside an API resource policy; API Gateway expands it to the current API's ARN upon saving. In caller IAM policies or VPC endpoint policies, you normally write the full ARN:

~~~text
arn:aws:execute-api:ap-southeast-1:111122223333:abc123def4/prod/GET/orders
~~~

Substitute the real account, API ID, stage, method, and path. Avoid granting wildcards across all APIs in production client identity policies unless necessary.

### 5.2. `SourceVpce`, `SourceVpc`, and Original Source IP

- `aws:SourceVpce` restricts the **VPC endpoint ID** carrying the request.
- `aws:SourceVpc` restricts the **source VPC**.
- `aws:VpcSourceIp` is the condition key for checking the **caller's original private IP** traversing an interface endpoint; `aws:SourceIp` may not reflect the original client IP because the VPCE can rewrite source IPs.

Never copy Internet-API `IpAddress aws:SourceIp` rules onto a private API without checking private IP and dualstack semantics. In multi-account/multi-VPC architectures, prefer explicit endpoint/VPC IDs and manage their lifecycle carefully.

### 5.3. Endpoint Policies Do Not Replace Resource Policies

A VPC endpoint policy might allow only `GET` on one API. That narrows the network pipe, yet the **API resource policy** must still permit invocation from that source, and IAM-protected methods still require valid credentials.

Important nuance: VPC endpoint policies evaluate principals based on **SigV4/SigV4a signed requests** versus unsigned requests; with bearer tokens or JWTs, the endpoint may not see an IAM principal as expected. If you intend to restrict IAM principals at the endpoint policy level, use `AWS_IAM` and test request signing.

### 5.4. Example Endpoint Policy Scoped to One API

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": [
        "arn:aws:execute-api:ap-southeast-1:111122223333:abc123def4/prod/GET/*"
      ]
    }
  ]
}
~~~

This policy only illustrates resource scoping on a VPCE; it **does not replace** the API's resource policy or method authorization. With private custom domains, you also configure domain-name access associations and domain resource policies per current documentation.

## 6. Private REST APIs and DNS: Invoking from Inside a VPC

### 6.1. Private DNS Enabled

When the `execute-api` VPCE enables **Private DNS**, clients inside the VPC can call the familiar invoke URL:

~~~text
https://abc123def4.execute-api.ap-southeast-1.amazonaws.com/prod/orders
~~~

and the private resolver routes traffic to the **private VPCE**. If the method uses `AWS_IAM`, requests **must be signed with SigV4**. Plain `curl` without signing only works for test APIs configured with another authorization type.

**DNS warning:** Enabling Private DNS on `execute-api` can cause **default `execute-api` URLs of public APIs** to resolve to the private VPCE from inside that VPC, breaking calls to those public APIs. Mitigate this by calling public APIs via custom domains, or by disabling Private DNS and creating Route 53 Private Hosted Zone records for specific private APIs.

### 6.2. Private DNS Disabled or Endpoint-Specific URLs

You can invoke a Private REST API without enabling Private DNS via:

- The VPCE DNS hostname paired with a `Host` or `x-apigw-api-id` header so API Gateway knows which API to invoke.
- The endpoint-specific URL generated after **associating the VPC endpoint with the private API**, of the form:

~~~text
https://abc123def4-vpce0123456789abcdef0.execute-api.ap-southeast-1.amazonaws.com/prod/orders
~~~

This shows the URL pattern; use the exact hostname provided by API Gateway. Associating the VPCE creates a Route 53 alias so clients do not need to supply a custom `Host` header manually.

### 6.3. Testing Layer by Layer

From an authorized EC2 instance inside the VPC:

~~~bash
# Read-only: verify DNS resolution without sending a business request.
nslookup abc123def4.execute-api.ap-southeast-1.amazonaws.com

# If the test method permits access without AWS_IAM,
# this GET sends a real request and may incur charges.
curl -i --connect-timeout 5 \
  https://abc123def4.execute-api.ap-southeast-1.amazonaws.com/prod/health
~~~

If the method requires `AWS_IAM`, sign requests with SigV4 via an AWS SDK or signing HTTP client; an HTTP `403` from an unsigned `curl` **does not mean** networking is broken. For on-premises clients, verify DNS and routing to the VPCE IPs and Security Groups first.

## 7. VPC Link: How API Gateway Reaches Private Backends

A **VPC Link** is an API Gateway-managed resource enabling **private integrations** to resources inside a VPC. It is neither a client-facing API endpoint nor a NAT Gateway. VPC Link V2 creates ENIs in selected subnets with configured security groups and forwards traffic to integration targets.

### 7.1. VPC Link V1 vs. V2

| Characteristic | **VPC Link V1 (legacy)** | **VPC Link V2 (recommended)** |
|---|---|---|
| CLI/API management | `aws apigateway create-vpc-link` | `aws apigatewayv2 create-vpc-link` |
| REST private integration | Supports **NLB** | Supports **ALB and NLB** |
| HTTP API private integration | Do not use legacy V1 | **ALB, NLB, and AWS Cloud Map** |
| How configured | Target NLB | **Subnet IDs + Security Group IDs** |
| Network path | V1 NLB-based VPC Link | V2 API Gateway-managed ENIs in VPC |
| New deployments | Avoid V1 when V2 fits | Prefer V2 and verify Regional availability |

**Important update vs. older docs:** REST API is **no longer limited to NLB-only** private integrations. **REST VPC Link V2** now supports targeting an **ALB directly**, eliminating the need to place an NLB in front of an ALB. However, **REST private integrations do not support AWS Cloud Map targets**; Cloud Map is exclusive to HTTP API private integrations.

### 7.2. V2 Operational Constraints

- VPC Link V2, the target load balancer or Cloud Map service, and the API must belong to the **same AWS account** per current private integration rules.
- **Subnets and security groups on a VPC Link V2 are immutable**: once created, they cannot be edited in place. To change them, create a new VPC Link V2 and update integrations.
- VPC Link V2 transitions from `PENDING` to `AVAILABLE` once ENIs are provisioned. Wait until `AVAILABLE` before deploying or testing traffic.
- If there is **no traffic for 60 days**, the link can transition to `INACTIVE` and API Gateway deletes its ENIs. When traffic resumes, requests fail briefly while API Gateway re-provisions ENIs (taking a few minutes). Monitor and document this in runbooks for low-traffic environments.
- One VPC Link can be reused across multiple private integrations; you do not need a separate link per route if security boundaries and traffic profiles align.

## 8. HTTP API Private Integration with ALB / NLB / Cloud Map

HTTP APIs fit well when you need straightforward routing/proxying, JWT/IAM authorization, and lower per-request cost than REST APIs for equivalent features. While HTTP API **lacks REST's `PRIVATE` endpoint type**, it can still use **VPC Link V2** to reach private backends.

### 8.1. Using an Internal ALB

A popular setup for Spring Boot on ECS:

~~~mermaid
flowchart LR
    C["Web/mobile client"] --> G["API Gateway HTTP API"]
    G --> V["VPC Link V2"]
    V --> A["Internal ALB: HTTPS listener"]
    A --> T["ECS service: orders-api :8080"]
    T --> D["RDS private"]
~~~

ALB fits when you need host/path HTTP routing, health checks, HTTPS listeners, target groups, and microservices routing. API Gateway **does not make ALB targets healthy automatically**. An unhealthy target group causes API Gateway errors even when the VPC Link status is `AVAILABLE`.

### 8.2. Using an NLB

NLB fits when backends use TCP/TLS listeners, specific throughput/connection semantics, or an existing NLB architecture. Because API Gateway still performs an **HTTP API integration**, configure the listener and protocol properly—having an NLB TCP listener does not mean API Gateway can proxy arbitrary custom binary protocols.

### 8.3. Using AWS Cloud Map

An HTTP API private integration can target an **AWS Cloud Map service ARN**; API Gateway calls `DiscoverInstances` to retrieve registered private IPs/ports and routes traffic to healthy instances.

- Cloud Map records must include appropriate IP and port attributes.
- For ECS service discovery, configure **SRV records** per documentation or use ECS Service Connect appropriately.
- Never apply this pattern to REST private integrations, because REST **does not support Cloud Map targets**.
- Health checks in Cloud Map and the application must still be carefully maintained.

### 8.4. Stage Prefix Forwarded to the Backend

HTTP API private integrations can forward the URL's **stage segment** to the backend. For example, a client calls:

~~~text
GET /test/orders/123
~~~

while the Spring Boot backend only exposes `/orders/123`. Without mapping, the backend receives `/test/orders/123` and returns `404`.

Fix this with a **parameter mapping** overwriting the integration request path to:

~~~text
$request.path
~~~

Verify mappings when creating routes/integrations and test across `dev`/`test`/`prod` stages. Never alter Spring Boot's base path just to work around a mapping or DNS/SG issue.

### 8.5. HTTPS from API Gateway to the Backend

Private integrations default to **HTTP** unless HTTPS is configured. On HTTP API, configure integration **`tlsConfig`** (with secure server name) targeting an HTTPS listener. The backend TLS certificate must match the SNI/hostname when verified. **HTTPS between clients and API Gateway does not automatically encrypt API Gateway → backend traffic.**

## 9. REST API Private Integration with VPC Link V2

REST API offers resource/method models, request validation, API keys/usage plans, mapping templates, and the **`PRIVATE` endpoint type**. For private integrations to HTTP backends:

- Create a **VPC Link V2** via the `apigatewayv2` API/CLI.
- Create the **REST method integration** via `apigateway put-integration` or the Console, choosing **`VPC_LINK`** and specifying the VPC Link V2 ID.
- With **V2**, the integration target can be an **ALB or NLB ARN**, while `uri` specifies the integration host/URL (affecting the `Host` header and TLS verification).
- With **legacy V1**, the integration target is an **NLB** under the older model.
- **REST does not support Cloud Map private integration targets.**
- After updating a REST integration, resource policy, or method, **redeploy the REST API to its stage** for the new deployment to take effect.

### 9.1. Console Workflow

1. Create or select a REST API in the right account and Region.
2. Create a **VPC Link V2** across at least two subnets where possible, with a Security Group permitted to reach the load balancer.
3. Wait until the VPC Link reaches `AVAILABLE`.
4. Create a method (e.g., `GET /orders`) with integration type **VPC Link**, choosing the target ALB or NLB.
5. Configure HTTP/HTTPS, integration path, TLS hostname, and method authorization.
6. If the API itself must be private-only, configure **REST endpoint type `PRIVATE`** with an `execute-api` VPCE and resource policy.
7. Deploy/redeploy to stage `prod`, then test the URL, CloudWatch logs, and ALB target health.

### 9.2. When Do You Need Both VPC Link and an `execute-api` VPCE?

| Scenario | Need `execute-api` Interface VPCE? | Need VPC Link? |
|---|---|---|
| Internet client → HTTP API → internal ALB | **No** | **Yes** |
| Private EC2 → Private REST API → Lambda | **Yes** | **No** |
| Private EC2 → Private REST API → internal ALB | **Yes** | **Yes** |
| Private EC2 → Regional REST API → Lambda | No for Regional endpoint (needs appropriate egress) | No |
| ECS in VPC → AppSync Private GraphQL | Uses `appsync-api` endpoint, not `execute-api` | **No** |

The "Need" columns apply to the **exact scenario described**. Applications may use VPNs or other integrations; never infer from the table that VPC Link is the only way API Gateway calls any AWS backend.

## 10. VPC Link V2: Subnets, Security Groups, and Network Path to ALB

### 10.1. Path from Link ENIs to Targets

Example topology:

| Component | Placement | Network policy |
|---|---|---|
| VPC Link V2 | Private subnets in AZ-a / AZ-b | Link ENIs use **SG-VPC-LINK** |
| Internal ALB | Private subnets in target AZs | ALB SG permits **inbound TCP 443** from SG-VPC-LINK |
| ECS/EC2 targets | Private subnets | Target SG permits **inbound TCP 8080** from ALB SG |
| RDS | Private database subnets | DB SG permits **inbound TCP 5432** from target SG |

Visualization:

~~~text
API Gateway
  → VPC Link ENI (SG-VPC-LINK, outbound 443)
  → Internal ALB listener :443 (ALB SG inbound from SG-VPC-LINK)
  → Spring Boot target :8080 (target SG inbound from ALB SG)
  → RDS :5432 (DB SG inbound from target SG)
~~~

Security Groups are **stateful**, so return traffic for allowed connections passes automatically. Network ACLs are **stateless**, requiring explicit outbound/return rules including ephemeral ports when strict NACLs are used. Route tables must permit traffic to private endpoints. Never open the ALB SG inbound to `0.0.0.0/0` just because API Gateway cannot reach the ALB.

### 10.2. Critical Checks

1. VPC Link subnets have **enough free IP addresses** for managed ENIs and do not block VPC link traffic.
2. The ALB sits in a supported account/VPC topology, using the exact listener ARN / ALB ARN required.
3. The VPC Link SG allows outbound traffic to the ALB, and the ALB SG allows inbound traffic from the VPC Link SG.
4. ALB listeners and target groups are healthy; target SGs permit traffic and the app listens on the expected port.
5. When using HTTPS, the backend certificate and host/SNI verification match.
6. When using HTTP API with Cloud Map, targets register valid IPs, ports, and health statuses per docs.
7. Across VPCs, route tables, NACLs, peering, Transit Gateway, or PrivateLink must have **valid forward and return paths**.

### 10.3. Same-Account vs. Cross-Account Backends

AWS documentation requires the direct private integration resources—the API, VPC Link, and target **load balancer or Cloud Map service**—to live in the **same AWS account**. If your business backend resides in another account, place a **target ALB/NLB in the API account** and bridge to the backend account via AWS PrivateLink, VPC peering, or Transit Gateway as appropriate.

Never supply a load balancer ARN from account B directly as a VPC Link integration target in account A when unsupported. Having a **Transit Gateway route** does not bypass control-plane same-account restrictions.

## 11. API Gateway IAM, JWT, Resource Policies, and Backend Authentication

### 11.1. Client-Side Authentication

Keeping a private backend free of public IPs **does not secure the API** if a public API exposes `ANY /admin/*` to everyone. Choose per API type:

- **REST API:** `AWS_IAM`, Cognito User Pool authorizer, Lambda authorizer, etc.
- **HTTP API:** JWT authorizer (OIDC/Cognito), Lambda authorizer, or `AWS_IAM`.
- **Private REST API:** Add a **resource policy restricting VPCE/VPC** plus a VPCE policy.

When a method uses `AWS_IAM`, the caller's IAM role needs `execute-api:Invoke` on the exact `execute-api` ARN and must sign requests with SigV4. Even with JWT authorization, backends often need to verify application-level claims and roles for business authorization.

### 11.2. API Gateway → Backend Is Not Automatic IAM Identity Propagation

VPC Link provides **network connectivity**, not automatic forwarding of business JWTs or assuming IAM roles to call private HTTP servers. To ensure the backend trusts only API Gateway:

- Restrict network ingress via **SG-VPC-LINK → ALB SG**, never exposing the ALB publicly.
- Use **TLS** on the integration when required and validate hostnames/certificates.
- Forward identity headers in a controlled manner; backends must never trust a client-supplied `X-User-Id` header if callers could spoof it.
- For sensitive operations, add service-to-service authentication, authorizers, or signed identity assertions.
- If the ALB listener or backend performs its own OIDC/auth, ensure redirects, header propagation, and timeouts work seamlessly through API Gateway.

### 11.3. Policies Can Block at Multiple Layers

A `403` can originate from:
- The VPCE policy.
- The API Gateway resource policy (`aws:SourceVpce`/`aws:SourceVpc`).
- Method IAM/JWT/Lambda authorizers.
- Backend application authorization when proxied.
- WAF or guardrails depending on API type and config.

Read **API Gateway access logs**, execution logs where supported, CloudTrail changes, ALB access logs, and application logs to isolate the exact layer. Never fix `403`s by changing IAM policies to wildcards.

## 12. DNS, HTTP Request Paths, `Host` Headers, and TLS

### 12.1. Both DNS Directions Must Work

- **Client → Private API:** The VPC resolver must resolve the `execute-api` hostname (or private custom domain) to the **VPCE IP**.
- **API Gateway → backend via VPC Link:** The integration must target the right ALB/NLB/Cloud Map resource. ALB listener rules can match on **`Host`/path**, so a mismatched host or path causes `404` even when TCP connects cleanly.

With a private custom domain like `api.internal.example.com`, configure the TLS certificate, DNS record/association, and API mapping properly. Never assume a Route 53 Private Hosted Zone automatically allows every VPCE to access a private custom domain—you still need domain-name access associations and resource policies per API Gateway rules.

### 12.2. HTTPS on Both Hops

~~~text
Client --HTTPS--> API Gateway --HTTP or HTTPS per integration--> Internal ALB --> Backend
~~~

If policy mandates end-to-end encryption, configure **HTTPS on the integration** as well as the client-facing API Gateway endpoint. On HTTP API, set `tlsConfig` with the secure server name; on REST VPC Link V2, specify the HTTPS host in `--uri` per AWS docs.

Never disable certificate or hostname verification (`insecureSkipVerification`) to work around production connection errors. Fix the ACM certificate, SNI, TLS listener, and DNS `Host` header instead.

### 12.3. CORS Does Not Replace Authorization

If browser clients call a public API, configure **CORS** with exact allowed origins, methods, and headers. CORS is browser-enforced and does not protect private backends from scripts or `curl`. Even on an intranet private API, CORS may still be needed if a web app runs on another origin; handle preflight and authorization properly.

### 12.4. URL Path Rewriting

- On HTTP private integrations, the **stage path prefix** can be forwarded to the backend. Use `$request.path` parameter mapping when needed.
- On REST private integrations, check integration request paths, mapping templates, and stage behavior; never assume the backend always sees the exact raw URL the user typed.
- Test trailing slashes `/`, path parameters, query strings, HTTP methods, and `Host` headers against ALB listener rules.

## 13. AppSync Private APIs: A Different GraphQL Solution from API Gateway VPC Link

**AWS AppSync** provides GraphQL APIs and real-time subscriptions. AppSync supports **Private GraphQL APIs** invoked from a VPC over **AWS PrivateLink**—this is separate from API Gateway `PRIVATE` REST APIs, and you do not use an API Gateway VPC Link to send GraphQL traffic to AppSync.

### 13.1. Two AppSync Interface Endpoint Services

| Endpoint service in `ap-southeast-1` | Role |
|---|---|
| `com.amazonaws.ap-southeast-1.appsync-api` | **Data plane:** GraphQL queries, mutations, subscriptions, and Realtime endpoints |
| `com.amazonaws.ap-southeast-1.appsync` | **Control plane:** Managing GraphQL APIs, schemas, and data sources via CLI/SDK |

If workloads only need to **call the GraphQL API**, `appsync-api` is the required endpoint. Do not create only the `appsync` control-plane endpoint and expect GraphQL queries to traverse it.

### 13.2. Private Visibility Must Be Chosen at Creation Time

For an AWS AppSync GraphQL API, `visibility` is `GLOBAL` or `PRIVATE`; **Private API visibility must be set when creating the API** and **cannot be toggled between public and private after creation** per AWS documentation. Decide access scope before provisioning, or plan a migration to a new API if requirements change.

The VPC interface endpoint for an AppSync Private API must reside in the **same account and Region as the API**, per current AppSync guidance. That VPC must configure inbound port 443 on the SG, Private DNS, and IAM/endpoint policies if restricting callers.

### 13.3. AppSync Private DNS Has the Same Caveat as API Gateway

Enabling Private DNS on an `appsync-api` Interface Endpoint can prevent VPC clients from **reaching public AppSync APIs via their default AppSync-generated URLs**, because DNS resolves to the private API endpoint instead. Per AWS guidance, configure **custom domains** for public AppSync APIs that must remain reachable from that VPC.

The AppSync Console Query Editor **does not automatically tunnel into your VPC** just because you are logged into the AWS Console. Your browser needs network connectivity to the private endpoint (such as Client VPN or Direct Connect) to query a private API.

### 13.4. AppSync Does Not Automatically Reach Arbitrary Private HTTP Backends

AppSync resolvers invoke Lambda, DynamoDB, or supported data sources via AppSync's native integrations. If a Lambda resolver needs to query RDS or an internal ALB, **that Lambda function needs its own `VpcConfig`, SGs, and routes** for that backend. Do not look for an API Gateway VPC Link inside AppSync; the two services use different integration models.

**Choose AppSync** when your API fits a GraphQL schema with typed resolvers, queries/mutations/subscriptions, and integrated data sources. **Choose API Gateway** when you need REST/HTTP endpoint routing, proxying, and API Gateway policies/authorizers.

## 14. AWS Console: Setup Workflows for Both Sides

### 14.1. Creating a Private REST API (Private Ingress)

1. Sign in to the target AWS account and Region and choose **API Gateway → REST API → Build**.
2. Select endpoint type **Private** and configure appropriate security options.
3. Create an **Interface VPC Endpoint for `execute-api`** in the caller VPC, selecting private subnets and an SG permitting inbound TCP 443.
4. Attach a REST API **resource policy** restricting `aws:SourceVpce` or `aws:SourceVpc`; never rely solely on the VPCE SG.
5. Configure a **VPC endpoint policy** and method authorization (`AWS_IAM` / authorizer).
6. Associate the VPCE with the API if you want API Gateway's endpoint-specific DNS alias; review Private DNS and its impact on public default URLs.
7. Add methods/integrations, deploy to a stage, and test from a client inside the VPC/VPN/DX.
8. Monitor CloudWatch access logs and CloudTrail changes, and never expose a domain publicly unless intentionally designed.

### 14.2. Creating an HTTP API with a Private ALB Integration

1. Prepare the ECS/EC2 backend and an **internal ALB listener with a healthy target group** in the target account.
2. Open **API Gateway → VPC links** and create a **VPC Link V2**, selecting the VPC, subnets, and SGs.
3. Wait for `AVAILABLE`; confirm the ALB SG permits inbound traffic from the VPC Link SG.
4. Create an **HTTP API → Integration → Private resource**, choosing the VPC Link and ALB listener (or NLB / Cloud Map).
5. Add routes such as `GET /orders` or `ANY /{proxy+}` per routing needs.
6. Configure `tlsConfig` for HTTPS if needed, and verify stage prefix / `$request.path` mapping.
7. Configure a JWT/IAM authorizer, CORS, throttling, metrics, and access logging.
8. Deploy to the stage, send authenticated client requests, and inspect ALB health and backend responses.

### 14.3. Choosing REST VPC Link V2 Over V1

For new REST integrations targeting ALB/NLB, choose **VPC Link V2**; NLB-only V1 is legacy. When migrating an existing REST API off V1, plan integration updates, stage redeployments, rollbacks, and Host/TLS/path checks—never delete V1 while active stages still depend on it.

## 15. Read-Only AWS CLI: Inspecting Accounts, APIs, VPC Links, and Endpoints

All commands in this section are **read-only**. They assume AWS CLI v2 with profile `dev` and Region `ap-southeast-1`. Replace placeholders (`abc123def4`, `vpc-EXAMPLE`, `vpce-EXAMPLE`, and ARNs) with real authorized values. Note that even read-only CLI calls can incur minor API request charges per service rules.

### 15.1. Caller Identity and REST APIs

~~~bash
aws sts get-caller-identity --profile dev --output json

aws apigateway get-rest-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'items[].{Id:id,Name:name,Endpoint:endpointConfiguration.types,VPCEs:endpointConfiguration.vpcEndpointIds}' \
  --output table

aws apigateway get-rest-api \
  --rest-api-id abc123def4 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Check whether `endpointConfiguration.types` is `PRIVATE` and whether the resource policy restricts VPCE/VPC sources. If the API is `REGIONAL` or `EDGE`, integrating with an ALB via VPC Link **does not change its endpoint type to `PRIVATE`**.

### 15.2. HTTP APIs and Integrations

~~~bash
aws apigatewayv2 get-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:ApiId,Name:Name,Protocol:ProtocolType,Endpoint:ApiEndpoint}' \
  --output table

aws apigatewayv2 get-integrations \
  --api-id HTTP_API_ID \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws apigatewayv2 get-routes \
  --api-id HTTP_API_ID \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Look for integrations with `ConnectionType = VPC_LINK`, `ConnectionId`, `IntegrationType = HTTP_PROXY`, and `IntegrationUri` pointing to the ALB/NLB listener ARN or Cloud Map service ARN. `HTTP_API_ID` is a placeholder; never create APIs without authorization.

### 15.3. VPC Links V2 vs. Legacy V1

~~~bash
# VPC links V2: use apigatewayv2 CLI
aws apigatewayv2 get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:VpcLinkId,Name:Name,Status:VpcLinkStatus,Subnets:SubnetIds,SGs:SecurityGroupIds}' \
  --output json

# Legacy REST VPC links V1: use apigateway CLI
aws apigateway get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

These two commands query different API namespaces—**do not assume a VPC Link V2 vanished** just because V1 `apigateway get-vpc-links` returns empty.

### 15.4. Interface Endpoints in the VPC

~~~bash
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,PrivateDns:PrivateDnsEnabled,State:State,SubnetIds:SubnetIds,SG:Groups[].GroupId}' \
  --output json
~~~

Look for service names:

~~~text
com.amazonaws.ap-southeast-1.execute-api  # Private REST API ingress
com.amazonaws.ap-southeast-1.appsync-api  # AppSync Private GraphQL data plane
com.amazonaws.ap-southeast-1.appsync      # AppSync management control plane
~~~

If there is no `execute-api` endpoint in the caller's VPC, Private REST API clients have no ingress path under this model. If the VPCE exists but its SG blocks inbound TCP 443 from callers, connections time out.

### 15.5. ALB/NLB and Target Health

~~~bash
aws elbv2 describe-load-balancers \
  --profile dev \
  --region ap-southeast-1 \
  --query 'LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,Type:Type,Arn:LoadBalancerArn,Vpc:VpcId,Dns:DNSName}' \
  --output json

aws elbv2 describe-listeners \
  --load-balancer-arn ALB_OR_NLB_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws elbv2 describe-target-health \
  --target-group-arn TARGET_GROUP_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

**A VPC Link showing `AVAILABLE` is not enough:** ALB/NLB target groups must have healthy targets, `Host`/path rules must match, and the app must listen on the target port. Never disable health checks just to "make networking pass."

### 15.6. AppSync APIs

~~~bash
aws appsync list-graphql-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'graphqlApis[].{Name:name,Id:apiId,Visibility:visibility,Urls:uris}' \
  --output json
~~~

`visibility` reports `PRIVATE` or `GLOBAL` in API metadata. Verify matching account/Region and `appsync-api` VPC endpoints before expecting private GraphQL calls to succeed.

## 16. Configuring VPC Link V2 via CLI: Mutating Examples Only

**These commands create or modify real AWS resources**; run them only after review/approval in an authorized lab account. Never use literal placeholders in production.

### 16.1. Create a VPC Link V2

~~~bash
# MUTATING: creates managed ENIs/network capacity and may incur charges.
aws apigatewayv2 create-vpc-link \
  --name orders-private-vpc-link \
  --subnet-ids subnet-EXAMPLE-A subnet-EXAMPLE-B \
  --security-group-ids sg-EXAMPLE-VPCLINK \
  --profile dev \
  --region ap-southeast-1
~~~

Once the API returns `VpcLinkId`, poll `get-vpc-link`/`get-vpc-links` until status is `AVAILABLE`. Never pass subnet IDs from different VPCs; pick subnets in the right AZs/routes and an SG inside that same VPC.

### 16.2. HTTP API Integration to an ALB Listener

~~~bash
# MUTATING: creates an integration, without routes or deployments yet.
aws apigatewayv2 create-integration \
  --api-id HTTP_API_ID \
  --integration-type HTTP_PROXY \
  --integration-method GET \
  --connection-type VPC_LINK \
  --connection-id VPC_LINK_V2_ID \
  --integration-uri arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/orders-internal/EXAMPLE_ALB_ID/EXAMPLE_LISTENER_ID \
  --payload-format-version 1.0 \
  --profile dev \
  --region ap-southeast-1
~~~

For HTTP API, `IntegrationUri` with ALB/NLB is the **listener ARN**, not a target group or DNS name. To serve traffic, you still need a route, authorizer, stage/deployment (depending on auto-deploy), access logs, and testing. For HTTPS integrations, configure `tlsConfig` with the real secure server name.

### 16.3. REST API Integration to an ALB via VPC Link V2

~~~bash
# MUTATING: updates a REST API method integration.
aws apigateway put-integration \
  --rest-api-id REST_API_ID \
  --resource-id RESOURCE_ID \
  --http-method GET \
  --type HTTP_PROXY \
  --integration-http-method GET \
  --connection-type VPC_LINK \
  --connection-id VPC_LINK_V2_ID \
  --integration-target arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:loadbalancer/app/orders-internal/EXAMPLE_ALB_ID \
  --uri https://orders.internal.example.com:443/orders \
  --profile dev \
  --region ap-southeast-1
~~~

For REST V2, `--integration-target` is the **load balancer ARN**, while `--uri` supplies the integration hostname and path (controlling the `Host` header and TLS verification). Ensure the ALB listener certificate matches that hostname, and redeploy the REST API stage for changes to take effect. This snippet does not create resources, methods, authorizers, or stage deployments.

### 16.4. What Not to Do

Never run `create-vpc-link` just to test a `get-vpc-links` lookup. Never delete an old VPC Link V1 while REST integrations still depend on it. Avoid creating a fresh VPC Link V2 on every CI deployment when an existing link can be reused—extra links waste ENIs, management overhead, and money. When V2 subnets or SGs must change, roll out a new link cleanly and cut integrations over instead of attempting unsupported in-place edits.

## 17. Spring Boot Backend: Health Checks and HTTP Flow

Suppose a microservice exposes:

~~~java
package com.example.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    @GetMapping("/{orderId}")
    public ResponseEntity<String> findOrder(@PathVariable String orderId) {
        // Learning example: does not query a database or verify ownership yet.
        return ResponseEntity.ok("order=" + orderId);
    }
}
~~~

A `GET /orders/42` request can follow:

~~~text
Client HTTPS
  → API Gateway route GET /orders/{orderId}
  → VPC Link V2
  → ALB listener :443 (Host/path rules)
  → ECS task :8080
  → Spring Boot GET /orders/42
~~~

If stage `test` remains in the forwarded path, the backend can receive `/test/orders/42` → `404`. Configure HTTP API parameter mapping to strip it. If Spring Boot binds only to `localhost:8080` instead of the container network interface, ALB health checks fail even when the container appears alive internally.

### 17.1. Health Checks and Readiness

- Point ALB target group health checks at a safe readiness endpoint such as `/actuator/health/readiness` when Spring Boot Actuator is configured.
- Ensure health check path, expected status code, port, and SG match, or targets stay `unhealthy`.
- API Gateway returns `5xx` when integration targets are unhealthy, time out, or cannot be reached; the app itself can also return `500` on unhandled exceptions.
- Backends should not trust requests solely based on Security Groups; enforce business authorization and claim checks where appropriate.

### 17.2. Timeouts, Keep-Alive, and Idempotency

API Gateway and ALBs enforce integration and idle timeouts depending on API type, Region, and settings. For long-running work (such as multi-minute Java report exports), do not hold synchronous HTTP calls open through API Gateway past timeout limits; instead:

1. `POST /jobs` enqueues a job in SQS or Step Functions.
2. Backend returns `202 Accepted` with a job ID.
3. Client polls status or receives a callback/WebSocket/event notification upon completion.
4. Store outputs in S3 and serve via tightly scoped, short-lived presigned URLs.

Client and integration retries can resend requests; implement **idempotency keys**, database transaction boundaries, and duplicate handling on state-changing `POST` endpoints.

## 18. Observability: API Gateway, VPC Link, ALB, and Application Logs

### 18.1. Telemetry Layers

| Layer | Observation sources | Key signals to watch |
|---|---|---|
| API Gateway | Access logs, metrics, tracing where supported | `Count`, `4XXError`, `5XXError`, `Latency`, `IntegrationLatency` |
| VPC Link V2 | Status API/Console; ENI / Flow Logs | `PENDING`/`AVAILABLE`/`INACTIVE`, network rejects/connection errors |
| VPC network | VPC Flow Logs, Reachability Analyzer where appropriate | IP/port, `ACCEPT`/`REJECT`, routes/SGs/NACLs |
| ALB/NLB | Target health, access logs, CloudWatch | `HealthyHostCount`, `TargetResponseTime`, `5xx`, TCP errors |
| Spring Boot | Actuator/Micrometer/structured logs | HTTP status, DB latency, correlation ID, exceptions |
| IAM/control-plane | CloudTrail | Who modified APIs, resource policies, VPC Links, SGs, or targets? |

A `504 Gateway Timeout` alone does not tell you whether the delay occurred in API Gateway, VPC Link, the ALB, or the backend. Correlate **request IDs**, timestamps, routes/paths, statuses, integration latency, ALB trace headers, and application logs.

### 18.2. Security Logging

- Never log raw `Authorization` bearer/JWT tokens or API keys in access logs.
- Mask request bodies, credentials, PII, and secrets.
- Restrict CloudWatch log retention and read permissions.
- CloudTrail audits control-plane changes and does not replace application access logs.
- Configure metrics/alarms for VPC Link `INACTIVE` states and backend target health on low-traffic environments.

## 19. Symptom-Based Troubleshooting

| Error / symptom | Likely cause category | Where to check |
|---|---|---|
| Private REST API `403` | Resource policy omits VPCE/VPC, VPCE policy, or bad IAM auth | Check `aws:SourceVpce`, VPCE policy, method auth, SigV4 |
| Public HTTP API still reaches private backend | Expected behavior of a **private integration** | To make the frontend private, redesign with Private REST API |
| Private API DNS returns public IP | Misconfigured Private DNS, Resolver, or VPCE association | VPC DNS settings, VPCE `PrivateDnsEnabled`, hostname |
| VPC client cannot call public `execute-api` URL | Private DNS enabled on `execute-api` VPCE hijacked DNS resolution | Use public custom domains or a split-horizon private DNS strategy |
| VPCE TCP 443 timeout | Endpoint SG, subnet/NACL, route, or DNS | Inbound SG from client, VPCE ENI IP/routes |
| V1 `get-vpc-links` does not list V2 link | Wrong CLI namespace | Run `apigatewayv2 get-vpc-links` |
| VPC Link V2 stuck `PENDING` | ENIs provisioning, subnet IP exhaustion, or permissions | Link status, subnet free IPs, VPC SGs |
| VPC Link V2 `INACTIVE` | 60 days with no traffic | Wait for re-provisioning, monitor status; plan for first-request recovery |
| API Gateway integration `502` | TLS `Host` mismatch, ALB reset, misconfigured integration | Integration URI, secure server name, ALB listeners/certs/logs |
| API Gateway integration `504` | Backend timeout, SG/route/NACL block, slow ALB response | `IntegrationLatency`, Flow Logs, ALB target health, backend timeouts |
| Spring Boot returns `404` on private integration | `/test` stage prefix or wrong path mapping | HTTP API `$request.path` mapping, ALB path rules |
| ALB targets unhealthy | Wrong target SG, port, readiness path, or TLS | Target group status, target SG inbound, health endpoint |
| NLB/ALB `5xx` while VPC Link is `AVAILABLE` | Link is up, backend is failing | ALB/NLB metrics, target logs, application logs |
| REST VPC Link V2 fails with Cloud Map | REST does not support Cloud Map targets | Use ALB/NLB or switch to HTTP API |
| Cannot edit VPC Link V2 subnets/SGs | V2 is immutable | Create a new link and swap integrations |
| VPC Link target in another AWS account | Same-account restriction | Place LB in API account + cross-account PrivateLink/TGW/peering |
| HTTP API backend HTTPS cert mismatch | `tlsConfig`/SNI/certificate mismatch | TLS hostname, listener, ACM/trust chain |
| On-prem calls to Private API fail | Missing routes or DNS to VPCE | VPN/DX routes, Resolver inbound endpoint, VPCE SG |
| AppSync private queries fail to reach endpoint | Missing `appsync-api` data-plane VPCE | AppSync visibility, VPCE service name, Private DNS |
| Public AppSync API unreachable from VPC | `appsync-api` Private DNS overrides default API hostname | Use custom domain for public AppSync or separate DNS design |
| Costs rise even though backend has no public IP | VPCE, VPC Link, ALB, CloudWatch, and egress incur independent charges | Cost Explorer, idle resources, request volume |

### 19.1. Seven-Step Investigation Sequence

1. **Identify API type/endpoint:** REST `PRIVATE`, REST `REGIONAL`, or HTTP API? AppSync `PRIVATE` or `GLOBAL`?
2. **Isolate the failing hop:** client → VPCE/API Gateway, API Gateway → VPC Link → ALB, or AppSync → resolver/Lambda?
3. **Check DNS and TLS:** Correct hostname? Is VPCE Private DNS enabled and affecting public URLs?
4. **Check authorization:** Do the API resource policy, VPCE policy, and method IAM/JWT auth match the caller?
5. **Check the VPC Link:** V1 or V2? `AVAILABLE` or `INACTIVE`? Right subnets and SGs?
6. **Check the backend:** Listener target ARN, SGs, NACLs, target health, path mapping, TLS, and app readiness.
7. **Correlate logs and metrics:** API Gateway access/integration logs, ALB target/Flow Logs, CloudTrail, and Spring Boot logs.

Never solve a `403` resource policy failure by opening the ALB SG, and never solve a `504` backend timeout by granting IAM administrator permissions.

## 20. Availability, Security, and Cost

### 20.1. Multi-AZ Resilience

- Select subnets across **multiple AZs** for VPC Link V2 whenever possible to avoid single-AZ dependencies.
- Provision ALB/NLB listeners and healthy targets across multiple AZs; run ECS tasks with multiple replicas and proper health checks.
- Place `execute-api`/`appsync-api` Interface VPC Endpoint ENIs in all AZs where clients run, with proper SGs and DNS.
- For HTTP/REST APIs, configure retries/idempotency, circuit breakers, and backend DB connection pools aligned with SLOs.
- For multi-Region backends, build dedicated DR, Route 53/custom domain failover, data replication, and testing—a VPC Link does not span Regions.

### 20.2. Separate Cost Drivers

| Item | Why costs accrue |
|---|---|
| API Gateway REST/HTTP | Requests, payload/data transfer, caching/features if enabled |
| Interface VPC Endpoint | Hourly endpoint charges per AZ plus data processing |
| VPC Link | Per link type/features and current API Gateway / VPC networking pricing |
| ALB/NLB | Load balancer hours, LCU/NLCU, processed bytes |
| ECS/EC2 backend | Task/instance CPU, RAM, and storage |
| CloudWatch Logs / tracing | Ingestion, retention, metrics, and trace spans |
| Route 53 / ACM / private DNS | Hosted zones/queries and certificate services where applicable |
| Inter-AZ / cross-account networking | Data transfer plus PrivateLink/TGW/NAT depending on topology |

A **public API + VPC Link** is often cheaper and simpler than "Private REST API + interface endpoint + VPC Link" when a private client-facing endpoint is unnecessary. Conversely, internal workloads with strict data-perimeter mandates justify the extra cost and complexity to restrict access strictly to VPCEs. Evaluate total networking, security, and operational TCO rather than per-request pricing alone.

### 20.3. Practical Security Rules

1. Apply least-privilege IAM roles and authorizers; never allow `execute-api:Invoke` to all principals unless another approved auth layer enforces access.
2. On Private REST APIs, pair **resource policies (`aws:SourceVpce`/`aws:SourceVpc`)** with VPCE policies and SGs, verifying explicit denies.
3. On private integrations, enforce **VPC Link SG → ALB SG** and end-to-end TLS where required.
4. Never make databases or internal ALBs public just to get API Gateway working.
5. Protect DNS, Route 53 zones, ACM certificates, and domain-name access associations.
6. Scrub tokens and PII from logs, alert on `5xx`/latency spikes, and audit every change.
7. Use IaC with change approvals, replacing immutable VPC Link V2s cleanly when subnets or SGs change rather than attempting unsupported edits.

## 21. Read-Only Lab: Identifying Architecture and Root Causes

### 21.1. Scenario

A Spring Boot application on ECS in private subnets sits behind an internal ALB. Internet clients must reach `api.example.com` without accessing the ALB directly. Simultaneously, an internal admin app requires a private endpoint accessible only to employees over VPN.

Sketch both paths:

- **Customer path:** Public **HTTP API + VPC Link V2 → internal ALB → ECS**, protected by a JWT/IAM authorizer and security controls.
- **Internal path:** **Private REST API → `execute-api` VPCE → VPC Link V2 → internal ALB → ECS** when using a private HTTP backend, or native Lambda integration if the admin backend runs on Lambda.

Do not create real APIs or VPC Links during this read-only lab so you incur no charges.

### 21.2. Part A — Inspect API Types

~~~bash
aws sts get-caller-identity --profile dev

aws apigateway get-rest-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'items[].{Id:id,Name:name,Endpoint:endpointConfiguration.types}' \
  --output table

aws apigatewayv2 get-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:ApiId,Name:Name,Type:ProtocolType}' \
  --output table
~~~

Record API IDs, REST/HTTP types, and endpoint types. If a REST endpoint type is not `PRIVATE`, does adding a VPC Link make the API private? **No.**

### 21.3. Part B — Inspect VPC Links and Endpoints

~~~bash
aws apigatewayv2 get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.ap-southeast-1.execute-api \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Identify the VPC Link V2 subnets/SGs and the `execute-api` VPCE subnets/SGs. Do these two sets of ENIs perform the same job? **No:** VPC Link handles API Gateway → backend egress, whereas the `execute-api` VPCE handles client → Private REST API ingress.

### 21.4. Part C — Inspect ALB and Targets

~~~bash
aws elbv2 describe-load-balancers \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws elbv2 describe-target-health \
  --target-group-arn TARGET_GROUP_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

If the VPC Link is `AVAILABLE` while targets are `unhealthy`, should you inspect the ALB SG, target SG, listener, and readiness endpoint—or create another `execute-api` VPCE? **Inspect the backend first**, because the fault lies in the outbound integration.

### 21.5. Part D — Distinguish Three Failures

| Observed result | Priority diagnostic checks |
|---|---|
| `403` calling Private REST API from EC2 | Resource policy `SourceVpce`, VPCE policy, IAM method auth / SigV4 |
| `504` from API Gateway, ALB logs show no request | VPC Link networking, SGs/NACLs, target/Host/TLS |
| `404` from Spring Boot showing path `/test/orders/42` | HTTP API stage-prefix mapping forwarded to backend |

List **read-only** verification steps for each failure without opening `0.0.0.0/0` SGs or wildcard IAM policies.

### 21.6. Part E — AppSync

Suppose the analytics team moves the admin API to GraphQL:

1. Select **AppSync Private API at creation time**, explaining why it cannot be enabled later on an already-published API.
2. Choose the **`appsync-api` Interface Endpoint** for queries, mutations, and subscriptions.
3. Add the `appsync` management endpoint only if CLI/SDK tools inside the VPC must administer the API privately.
4. If an AppSync resolver calls Lambda to query RDS, Lambda needs its own **`VpcConfig`**; **VPC Link is not an AppSync data-source feature**.
5. Check the impact of Private DNS on public AppSync default URLs from inside the same VPC.

## 22. Self-Assessment Questions

1. Which two network segments do a Private REST API and an API Gateway private integration protect?
2. Does HTTP API have a `PRIVATE` endpoint type like REST API?
3. Can an HTTP API using a VPC Link to an internal ALB still be called from the Internet?
4. What is the service name of the `execute-api` Interface VPC Endpoint in the Singapore Region?
5. Does a Private REST API need a VPC Link if its integration only invokes Lambda?
6. What does the API resource policy condition `aws:SourceVpce` restrict?
7. Why does a VPCE policy not replace a method's IAM or JWT authorizer?
8. Why can enabling Private DNS on `execute-api` break calls to public `execute-api` URLs from inside the VPC?
9. How do VPC Link V1 and V2 differ in purpose, CLI namespace, and supported targets?
10. Does REST API VPC Link V2 still require placing an NLB in front of an ALB?
11. HTTP API private integrations support Cloud Map, but does REST API support Cloud Map targets?
12. Why should the ALB SG allow inbound TCP 443 from the VPC Link SG rather than `0.0.0.0/0`?
13. When a VPC Link V2 transitions to `INACTIVE` after 60 days without traffic, what happens to its ENIs?
14. Can you edit subnets and SGs on a VPC Link V2 in place?
15. How can an HTTP API stage named `test` cause a backend to receive an unexpected path?
16. What must be configured for API Gateway → backend traffic to use HTTPS?
17. Why must a backend `404` and a Private API `403` be diagnosed differently?
18. Does private AppSync GraphQL traffic use the `appsync` or `appsync-api` endpoint service?
19. Can you change an AppSync API from `GLOBAL` to `PRIVATE` after creation?
20. When an AppSync resolver invokes a Lambda that queries RDS, does it need a VPC Link or Lambda `VpcConfig`?
21. Why must cross-account ALB/VPC Link private integrations still satisfy the same-account constraint for the direct target?
22. What charges still accrue even when the backend has no public IP?

### Answer Key Outline

- **Private REST API:** Private ingress via `execute-api` VPCE, resource policy, endpoint policy, and authorizers.
- **VPC Link V2:** Private outbound integration to **ALB/NLB (REST or HTTP)** or **Cloud Map (HTTP)** using ENIs in your VPC; V2 links are immutable and can become `INACTIVE` after 60 idle days.
- **AppSync Private API:** GraphQL/Realtime via `appsync-api` VPCE, with visibility chosen at creation time; distinct from API Gateway VPC Link.
- **Operations:** Separate DNS, authentication, networking, TLS, backend target health, stage path mapping, request logs, and cost.

## 23. Official AWS Documentation

1. [Private REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-apis.html) — `PRIVATE` endpoint and Interface VPCE.
2. [Create a private API](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-api-create.html) — Resource policies, VPCE associations, deployment.
3. [Invoke a private API](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-api-test-invoke-url.html) — DNS, invocation, and private custom domains.
4. [API Gateway resource policy examples](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-resource-policies-examples.html) — `SourceVpc`, `SourceVpce`, `VpcSourceIp`.
5. [VPC endpoint policies for private APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-vpc-endpoint-policies.html) — Endpoint access controls.
6. [Private integrations for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/private-integration.html) — VPC Link V2 to ALB/NLB and legacy V1.
7. [Set up VPC links V2](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-vpc-links-v2.html) — Creation, subnet/SG immutability, `INACTIVE` after 60 days.
8. [Create REST private integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-private-integration.html) — REST `put-integration` and `integration-target`.
9. [HTTP API private integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html) — ALB/NLB/Cloud Map, path mapping.
10. [HTTP API to ECS private integration tutorial](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-private-integration.html) — Complete ALB/ECS walkthrough.
11. [Deploy REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-deploy-api.html) — Deployments, stages, update propagation.
12. [AWS CLI apigatewayv2 create-vpc-link](https://docs.aws.amazon.com/cli/latest/reference/apigatewayv2/create-vpc-link.html) — Create V2 command.
13. [AWS CLI apigatewayv2 create-integration](https://docs.aws.amazon.com/cli/latest/reference/apigatewayv2/create-integration.html) — Create HTTP integration command.
14. [AWS CLI apigateway put-integration](https://docs.aws.amazon.com/cli/latest/reference/apigateway/put-integration.html) — REST integration.
15. [AWS AppSync Private APIs](https://docs.aws.amazon.com/appsync/latest/devguide/using-private-apis.html) — GraphQL/Realtime, AppSync endpoints, and visibility.
16. [AppSync GraphqlApi API](https://docs.aws.amazon.com/appsync/latest/APIReference/API_GraphqlApi.html) — `GLOBAL`/`PRIVATE` visibility.
17. [API Gateway Private API and integration best practices whitepaper](https://docs.aws.amazon.com/whitepapers/latest/best-practices-api-gateway-private-apis-integration/best-practices-api-gateway-private-apis-integration.html) — Architecture, security, and operations.
18. [VPC Interface endpoints through AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html) — Interface endpoints, SGs, Private DNS.
19. [Security groups for VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — Stateful network policy.
20. [ALB target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — Health status.
21. [API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) — Requests and features.
22. [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/) — VPCE endpoint-hours and data processing.
23. [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/) — ALB/NLB charges.

> **Final takeaway:** To build secure APIs, draw **two separate arrows**: **client → API** and **API → backend**. To keep the *frontend* private, use **Private REST API + `execute-api` VPCE** (or AppSync Private API for GraphQL). To keep the *backend* private, use **VPC Link V2 + private ALB/NLB/Cloud Map per API type**. When you need both, combine the mechanisms cleanly and verify IAM/resource policies, SGs, DNS, TLS, stage paths, target health, logs, and costs before releasing.
