# AWS Shield and DDoS Mitigation Architecture

A web service can be securely designed and still become unavailable if an attacker exhausts bandwidth, connection state, HTTP processing capacity, or downstream resources. A Distributed Denial of Service (DDoS) attack is a coordinated attack from multiple sources designed to disrupt service for legitimate users. An effective anti-DDoS architecture combines edge traffic absorption, anomaly detection, application-layer request filtering, origin protection, bounded scaling, and incident response procedures.

AWS Shield is a managed DDoS protection service. **Shield Standard** is enabled automatically for AWS customers at no additional charge; **Shield Advanced** is a paid subscription adding enhanced monitoring, detection, mitigation, AWS WAF integration, Shield Response Team support, and cost protection benefits. Shield is one layer in the architecture. Route 53, CloudFront, Global Accelerator, AWS WAF, load balancers, VPC origins, security groups, auto scaling, and observability determine whether an application stays available in practice.

This lesson belongs to the **Network and Application Security** chapter of the **CLOUD_PROVIDERS_AWS** module. It focuses on choosing architectures suited for websites, APIs, and TCP/UDP applications; configuring protection on the right resources; distinguishing L3/L4/L7 protection layers; building health checks, alerts, and runbooks; controlling costs; and validating resilience.

> **Principle:** There is no single Shield toggle that protects every resource in an account. Shield Advanced monitors/protects only explicitly specified resources or those covered by an AWS Firewall Manager policy. Traffic must flow through the right entry points, origins must be protected against bypass, and rules must be tested to avoid blocking legitimate users.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain DDoS and distinguish volumetric, protocol, and application-layer attacks.
2. Recognize common L3, L4, and L7 attack vectors.
3. Compare AWS Shield Standard and Shield Advanced.
4. Identify resource types supported by Shield Advanced and protection scopes.
5. Explain the roles of Route 53, CloudFront, Global Accelerator, AWS WAF, and Elastic Load Balancing.
6. Design DDoS-resilient architectures for web applications, APIs, and TCP/UDP workloads.
7. Protect origins from direct access when CloudFront is the public entry point.
8. Use AWS WAF rate-based rules and the Anti-DDoS Managed Rule Group.
9. Understand the 2026 transition from Layer 7 Auto Mitigation to the Anti-DDoS Managed Rule Group.
10. Configure Route 53 health checks to support Shield Advanced health-based detection.
11. Describe the role, eligibility requirements, and contact process for the Shield Response Team (SRT).
12. Monitor DDoS events with Shield metrics, CloudWatch, WAF logs, and EventBridge.
13. Build runbooks for detection, containment, mitigation, and recovery.
14. Evaluate costs, DDoS cost protection, and service limits.
15. Practice protecting resources in an AWS sandbox and checking for false positives.

## 2. What Is DDoS and How Does It Impact Applications?

DDoS is an attack originating from multiple distributed sources. Sources may be botnets, compromised hosts, proxies, or automated traffic generators. The objective is to prevent a resource or dependency from serving legitimate requests.

A DDoS attack can cause:

- Exhaustion of network bandwidth or packet-processing capacity.
- Exhaustion of connection tables, sockets, threads, or workers.
- Elevated CPU, memory, database connections, and queue depth.
- Increased latency, HTTP 5xx errors, timeouts, and error rates.
- Unexpected costs from data transfer, request processing, or autoscaling.
- Disruption of dependent services such as DNS, authentication, payments, APIs, and databases.

DDoS does not have to take a server completely offline. As soon as response times exceed SLOs or critical requests time out, user experience and revenue are already impacted.

### 2.1. Three Attack Groups by OSI Layer

| Group | Layer | Target | Examples |
|---|---|---|---|
| Volumetric/network | L3 | Saturate bandwidth or packet-processing capacity | UDP flood, ICMP flood, reflection/amplification |
| Protocol/transport | L4 | Exhaust connection state or exploit protocols | TCP SYN flood, connection flood |
| Application | L7 | Exhaust HTTP/API or backend processing capacity | HTTP request flood, login/search/API abuse |

### 2.2. Volumetric and Reflection/Amplification Attacks

Attackers generate high packet volumes or abuse third-party servers to amplify traffic toward the victim. In reflection/amplification, an attacker spoofs the victim's source IP in small requests; responding services send much larger replies to the victim. The victim receives massive traffic without directly communicating with the attacker.

Defense requires large traffic absorption capacity and upstream/edge filtering. Simply increasing instance sizes or Auto Scaling inside a VPC generally cannot resolve bandwidth saturation before traffic reaches the origin.

### 2.3. Protocol Attacks

A TCP SYN flood sends many SYN packets and leaves half-open handshakes, exhausting connection state tables at the endpoint or intermediate devices. A connection flood differs in that many connections may complete the handshake and hold resources open for long periods. Some vectors exploit protocol quirks, packet fragmentation, or state tracking.

Edge layers such as CloudFront, Route 53, and Global Accelerator provide built-in mitigation mechanisms; AWS Shield provides detection/mitigation across supported resources and network layers. Security groups and NACLs control traffic, but they do not replace upstream DDoS mitigation systems.

### 2.4. Application-Layer Attacks

An HTTP request flood can send syntactically valid requests that are expensive to process—such as search, login, report generation, database queries, or uncacheable APIs. Attack traffic may be distributed across many IPs and mimic legitimate user agents and request patterns.

Limiting requests solely by IP can fall short if attackers use botnets or NAT/shared IPs. Combine rate-based rules, managed rule groups, tokens/challenges, authentication, caching, per-user/API-key quotas, backend concurrency limits, and capacity planning. Protect the most expensive endpoints before requests reach the database.

## 3. AWS Shield Standard and Shield Advanced

### 3.1. Shield Standard

Shield Standard is automatically enabled for all AWS customers at no extra cost. It protects against common network- and transport-layer (L3/L4) DDoS attacks, including SYN/UDP floods, reflection attacks, and common vectors.

Services such as Route 53, CloudFront, and Global Accelerator benefit from AWS's distributed edge/network mitigation infrastructure. Placing entry points at the edge allows traffic to be absorbed and filtered closer to sources before reaching a Region.

Shield Standard requires no subscription or manual enablement. However, Standard does not automatically configure AWS WAF rules, application-specific rate limits, origin restrictions, health checks, or application runbooks.

### 3.2. Shield Advanced

Shield Advanced is a paid subscription for internet-facing applications needing enhanced protection, visibility, and response capabilities. Key capabilities include:

- Always-on flow-based monitoring and DDoS event detection for protected resources.
- Enhanced visibility, metrics, and attack/event reports.
- Enhanced mitigation for L3/L4 and L7 support via AWS WAF.
- Integration with AWS WAF Web ACLs, rules, and managed rule groups.
- Health-based detection using Route 53 health checks.
- Protection groups to group resources and evaluate events at the group level.
- Shield Response Team (SRT) assistance for investigation/mitigation under eligible support plans.
- Proactive engagement when a health check associated with a protected resource turns unhealthy during a detected event.
- DDoS cost protection via service credits subject to program terms.

Shield Advanced does not automatically protect every resource in an account. You must explicitly add resources to Shield Advanced or apply a policy via AWS Firewall Manager. When an architecture places CloudFront in front of an ELB and the ELB accepts traffic only from CloudFront, AWS recommends enabling Shield Advanced protection only on CloudFront rather than paying to protect both resources.

### 3.3. Quick Comparison

| Capability | Shield Standard | Shield Advanced |
|---|---|---|
| Automatically available | Yes | Requires subscription |
| Separate Shield fee | No | Yes, plus usage charges |
| Common L3/L4 DDoS | Yes | Yes, enhanced |
| Advanced event visibility | Basic via integrated services | Yes |
| Health-based detection | No | Yes |
| Protection groups | No | Yes |
| AWS WAF integration | Use WAF separately per pricing | Includes specific WAF fee benefits for protected resources |
| Anti-DDoS Managed Rule Group | Usable via AWS WAF per applicable pricing | Included under subscription/request allowance |
| SRT support | No | Yes, with Business or Enterprise Support |
| Proactive SRT engagement | No | Yes, requires health checks and setup |
| DDoS cost protection | No | Yes, subject to terms/eligibility |

### 3.4. Resource Types Supported by Shield Advanced

Shield Advanced supports enhanced protection for the following resource types:

- Amazon CloudFront distributions.
- Amazon Route 53 hosted zones.
- AWS Global Accelerator standard accelerators.
- Amazon EC2 Elastic IP addresses; EC2 instances are protected via EIP association.
- Application Load Balancers.
- Classic Load Balancers.
- Network Load Balancers via association with EC2 Elastic IP addresses.

Not every AWS resource can be added directly to Shield Advanced. For instance, Gateway Load Balancers and Global Accelerator custom routing accelerators are not on the protected resource list. NAT Gateways handle outbound traffic; Shield Advanced focuses on inbound DDoS protection.

Current Shield Advanced documentation specifies IPv4 support and does not support IPv6 for resource protections. When designing dual-stack architectures, verify protection coverage for each service and do not assume Shield Advanced covers IPv6. Protected resource limits per resource type/account should also be checked in Service Quotas.
By default, you can protect up to 1,000 resources per resource type in an AWS account; if you need more, submit a quota increase request via Service Quotas.



## 4. Role of Each Service in Anti-DDoS Architecture

No single service solves every attack layer. Architectures should place the right function at each point:

| Service | Role in DDoS Resiliency | Primary Layer/Impact |
|---|---|---|
| Amazon Route 53 | Authoritative DNS, health checks, routing/failover | DNS/application availability |
| Amazon CloudFront | Global edge entry, caching, traffic absorption, TLS termination | L3/L4 edge + L7 cache/origin shielding |
| AWS Global Accelerator | Static anycast IPs, global edge entry, routing to healthy endpoints | L3/L4/global routing |
| AWS Shield Standard | Automatic common DDoS mitigation | L3/L4 |
| AWS Shield Advanced | Enhanced detection/mitigation, visibility, SRT, and cost protection | L3/L4/L7 integration |
| AWS WAF | Inspect HTTP(S), managed rules, rate-based rules, labels, challenge/block | L7 |
| Elastic Load Balancing | Distribute traffic across targets/AZs, health-based routing | Availability/capacity |
| Auto Scaling / ECS / EKS scaling | Add capacity within configured limits | Backend resilience |
| AWS Network Firewall / Security Groups / NACLs | Restrict allowed network paths and protocols | Network access control |
| CloudWatch / CloudTrail / EventBridge | Metrics, audit, alerts, and automation | Detection/response |

### 4.1. Route 53

Route 53 provides authoritative DNS and can use health checks to support routing/failover. DNS query floods are mitigated by AWS's distributed DNS infrastructure and protections. Health checks should reflect actual application health—such as endpoint health, response codes, latency, or composite checks backed by CloudWatch alarms.

Avoid creating health checks that only verify whether a TCP port is open if the application can still fail at the business layer. Shield Advanced health-based detection uses health check status to tune detection sensitivity; the health check must relate directly to the protected resource.

### 4.2. CloudFront

CloudFront serves content from edge locations, caches objects, and maintains connections to origins. Cache hits keep requests out of the VPC/database, reducing origin load during traffic surges. TLS termination at the edge, combined with Shield mitigation, helps filter vectors before they reach the origin.

For dynamic content, design cache policies carefully: cache static assets aggressively, cache API responses when safe, and avoid caching responses containing private data. Caching does not replace authorization; never cache per-user data unless the cache key includes all required isolating factors.

### 4.3. Global Accelerator

Global Accelerator provides static anycast IPs and routes traffic over the AWS global network to appropriate endpoints. It is valuable for TCP/UDP or applications needing static IPs, fast failover, and routing to healthy regional endpoints. For web content, CloudFront is generally the better edge/caching choice; Global Accelerator adds value for non-HTTP workloads or network-level routing requirements.

### 4.4. AWS WAF

AWS WAF is the L7 request control layer. A Web ACL can contain:

- Managed rule groups to detect common exploits, bots, and DDoS request patterns.
- Rate-based rules to limit request rates by IP or supported aggregation keys.
- IP sets, geo match, and header/path/method filters.
- Label matching to handle requests tagged by prior rules.
- CAPTCHA/Challenge actions for suitable client/browser flows.
- Logging and sampled requests to analyze false positives.

WAF does not absorb upstream volumetric attacks like edge DDoS mitigation. WAF inspects HTTP(S) requests after traffic reaches the resource associated with the Web ACL. Position CloudFront or ALB/API Gateway properly and protect origins so attackers cannot bypass WAF.

## 5. Reference Architecture for Web Applications

A common resilient web architecture places Route 53 and CloudFront at the edge, uses AWS WAF to inspect requests, and forwards from CloudFront to origins in a private VPC. Shield Standard provides automatic protection; Shield Advanced protects explicitly registered resources and adds visibility/response.

~~~mermaid
flowchart LR
    U["Users / Internet"] --> DNS["Route 53<br/>DNS + health checks"]
    DNS --> CF["CloudFront<br/>Edge cache + TLS"]
    CF --> WAF["AWS WAF Web ACL<br/>Associated with CloudFront"]
    WAF --> ORIGIN["CloudFront VPC origin"]
    ORIGIN --> ALB["Private ALB"]
    ALB --> APP["ECS / EKS / EC2 targets"]
    APP --> DB["RDS / ElastiCache"]
    SHIELD["Shield Standard / Advanced"] -.-> DNS
    SHIELD -.-> CF
    SHIELD -.-> ALB
    CW["CloudWatch / WAF logs / EventBridge"] -.-> SHIELD
~~~

Principles:

1. **Single public entry point:** direct users through Route 53 and CloudFront instead of exposing multiple public origins.
2. **Cache before the origin:** static content and cacheable responses should be served from the edge.
3. **Web ACL on the right resource:** associate the Web ACL with the CloudFront distribution to inspect requests before they reach the origin.
4. **Keep origins non-public unless required:** CloudFront VPC origins let CloudFront reach ALBs/NLBs/EC2 instances in private subnets.
5. **Origin access for S3:** use Origin Access Control (OAC) so only the CloudFront distribution can read private S3 origins.
6. **Bounded backend scaling:** set Auto Scaling/ECS/EKS capacity limits and database connection limits aligned with budgets and load tests.
7. **Health checks and failover:** check application health, not merely instance status.
8. **Observe from edge to database:** monitor CloudFront, WAF, ALB, application, queue, and database metrics.

### 5.1. Protecting Origins from Direct Access

If attackers learn an ALB DNS name or public EC2 address, they can send requests directly to the origin and bypass CloudFront/WAF. Mitigations:

- Prefer CloudFront VPC origins to keep ALB/NLB/EC2 origins in private subnets and restrict origin access to CloudFront.
- For S3 origins, use OAC and a bucket policy allowing only the intended distribution.
- If not yet using VPC origins, restrict ALB security groups to the CloudFront origin-facing managed prefix list or an appropriate origin access mechanism; verify both IPv4/IPv6 and health check paths.
- A custom origin header can act as an additional verification layer, but secret headers do not replace network restrictions and must be rotated.
- Never allow origin DNS/endpoints to become a public bypass path.

CloudFront VPC origins are AWS's recommended solution for VPC origins; they support ALBs, NLBs, and EC2 instances in private subnets without requiring public internet access on the origin. For S3, OAC remains the recommended managed solution.

### 5.2. Web ACLs and Rate-Based Rules

Rate-based rules count requests over an AWS WAF–supported evaluation window and apply an action when rates exceed the threshold. You can aggregate by source IP, forwarded IP, or supported custom keys. Use scope-down statements to apply rules only to sensitive paths such as `/login`, `/search`, or `/api/report`.

Example design-level policies:

| Endpoint | Suggested Controls | Rationale |
|---|---|---|
| `/login` | IP rate limit + application account-level throttling | Mitigate brute force and login floods |
| `/search` | Rate limit + caching + query complexity limit | Prevent DB-intensive queries |
| `/api/report` | Authentication + per-tenant quota + queue | Keep expensive requests from exhausting workers |
| Static assets | CloudFront cache + WAF baseline | Reduce origin requests |
| Admin endpoints | Strong authentication, allowlists where appropriate, rate limits | Shrink attack surface |

Rate-based rules are a near-real-time mitigation layer evaluated per WAF mechanics; do not treat them as exact quotas for billing or business rate limiting. For per-user/tenant/API-key quotas, enforce limits separately in the application or API Gateway.

### 5.3. Avoiding Cache Poisoning and False Positives

- Cache only appropriate responses; audit query strings, cookies, and headers in cache keys.
- Never cache responses containing PII/private data without proper cache isolation.
- Use WAF Count mode to observe new rules before switching to Block.
- Inspect sampled requests and WAF logs before raising sensitivity.
- Create narrow exceptions by verified URI/headers/client behavior.
- Track rates of legitimate traffic receiving Challenge/CAPTCHA and monitor conversion/error rates.

## 6. Architectures for API, TCP, and UDP Workloads

### 6.1. API Workloads

With API Gateway, AppSync, or public ALBs, combine WAF Web ACLs, authentication, per-client quotas, caching, backend concurrency limits, and queues. Shield Advanced protects only supported resource types; do not assume every API endpoint/service can be added directly to Shield Advanced. AWS WAF can protect a wider set of resource types than Shield Advanced.

An API pattern:

~~~mermaid
flowchart TD
    CLIENT["Mobile / Web / Partner"] --> EDGE["Route 53 / CloudFront"]
    EDGE --> WAF["AWS WAF Web ACL"]
    WAF --> API["API Gateway / ALB"]
    API --> AUTH["JWT / Cognito / IAM auth"]
    AUTH --> LIMIT["Tenant quota + concurrency limit"]
    LIMIT --> QUEUE["SQS / EventBridge"]
    QUEUE --> WORKER["Lambda / ECS workers"]
    WORKER --> DATA["DynamoDB / RDS"]
    OBS["CloudWatch / WAF logs"] -.-> WAF
    SH["Shield"] -.-> EDGE
~~~

For expensive APIs, fail fast with `429 Too Many Requests` when quotas are exceeded, queue long-running work, and apply idempotency so retries do not create duplicate side effects. Do not let a request flood turn directly into a database connection flood.

### 6.2. TCP/UDP Workloads

Game servers, DNS, voice/video signaling, or custom protocols may require Network Load Balancers, Elastic IPs, or Global Accelerator. Enable Shield protection on supported resource types and verify the association path.

- Use Global Accelerator when static anycast IPs, health-based endpoint routing, and global ingress are required.
- Use NLB for high-performance TCP/UDP load balancing; Shield Advanced protection for NLB relies on EIP associations per resource support.
- Use security groups/NACLs to restrict protocols/ports and appropriate source ranges.
- Configure connection timeouts, idle timeouts, retry/backoff, and per-client connection limits.
- Monitor packets/bytes, new connections, active flows, rejected connections, and application health.

For UDP, the application protocol should validate legitimate requests and limit response amplification. Never send large responses to small unauthenticated requests if the protocol could be abused as a reflector.

## 7. Layer 7 DDoS Protection and the Anti-DDoS Managed Rule Group

HTTP request floods can send valid-looking requests that put heavy pressure on applications. AWS WAF addresses this layer with Web ACLs, rate-based rules, managed rule groups, and tokens/challenges. Shield Advanced provides enhanced integration and visibility for protected resources.

### 7.1. Key Change in 2026

Effective **March 26, 2026**, the AWS WAF Anti-DDoS Managed Rule Group (Anti-DDoS AMR) became the default solution for HTTP request flood protection and replaced Layer 7 Auto Mitigation (L7AM) in new deployment guidance.

- Existing Shield Advanced customers can continue using legacy L7AM for existing or new accounts.
- New Shield Advanced customers are recommended to use the Anti-DDoS Managed Rule Group.
- If new customers need access to legacy L7AM, they must contact AWS Support.
- Anti-DDoS AMR can detect/mitigate within seconds per AWS documentation, whereas legacy L7AM could take several minutes depending on the event.
- Do not copy old L7AM guidance into new architectures without checking update dates and service availability.

### 7.2. How the Anti-DDoS Managed Rule Group Works

The AWS managed rule group named `AWSManagedRulesAntiDDoSRuleSet`, provided by vendor `AWS`, consumes 50 WCUs. The rule group detects requests participating in or likely participating in a DDoS event, attaches labels, and applies soft/hard mitigations.

- **Soft mitigation:** issues a silent browser Challenge to requests capable of handling a challenge interstitial. This suits browser GET requests marked as challengeable.
- **Hard mitigation:** blocks requests with sufficiently high suspicion levels.
- Sensitivity for challenge and block actions can be tuned across low/medium/high suspicion levels.
- The rule group attaches labels so downstream rules in the Web ACL can apply custom actions.
- The rule group may attach labels to both legitimate and attack traffic while a resource is experiencing an event; understand label semantics before adding extra blocking rules.

Common labels:

| Label | Meaning |
|---|---|
| `awswaf:managed:aws:anti-ddos:event-detected` | Resource is experiencing a DDoS event against baseline; label may appear on all requests to the resource during the event |
| `awswaf:managed:aws:anti-ddos:ddos-request` | Request comes from a source suspected of participating in the event |
| `...:low-suspicion-ddos-request` | Request has low/probable suspicion level |
| `...:medium-suspicion-ddos-request` | Request has higher suspicion level |
| `...:high-suspicion-ddos-request` | Request has very high suspicion level |
| `...:challengeable-request` | URI/request can process a Challenge action per rule group criteria |

Do not block all requests simply because the `event-detected` label is present: that label can be attached to legitimate traffic while a resource is under attack. Use labels indicating suspected DDoS requests, confidence levels, token status, and challengeability according to rule order and application goals.

### 7.3. Deploying Anti-DDoS AMR

General workflow:

1. Create or select an AWS WAF Web ACL v2 for CloudFront or a supported resource.
2. Identify resources to protect and associate the Web ACL.
3. Add the AWS managed rule group `AWSManagedRulesAntiDDoSRuleSet` with vendor `AWS`.
4. Review sensitivity, challenge behavior, rule action overrides, and priority ordering.
5. Verify which URIs support Challenge; exclude URIs unable to handle browser challenges such as machine-to-machine APIs, webhooks, or incompatible endpoints.
6. Enable WAF logging and CloudWatch metrics; monitor labels, sampled requests, and legitimate traffic.
7. Use Count/override behavior during testing if impact evaluation is needed; switch to Block/Challenge only after verification.
8. Run load/attack simulations in authorized environments and in compliance with AWS testing policies.

The rule group can apply Challenge to browser-compatible requests and Block to high-suspicion requests. API clients incapable of executing browser challenges may be disrupted if scoping is wrong. Use scope-down statements to restrict URIs/traffic, and inspect labels before authoring custom label-match rules.

### 7.4. Shield Advanced L7 and WAF Rate-Based Rules

Even when using Anti-DDoS AMR, applications still need business-specific controls:

- Source-IP rate limits for public endpoints that do not require identity.
- Per-user, tenant, API key, or JWT subject quotas in the application/API layer.
- Authentication before running expensive operations.
- Caching and request coalescing for read-heavy endpoints.
- Queues, concurrency caps, and circuit breakers for backends.
- Challenge/CAPTCHA for flows with compatible browser sessions.
- Narrow allowlists for verified partners/webhooks; never hardcode broad allowlists.

Rate-based rules and managed rule groups are defensive layers; they do not replace business quotas, fraud controls, or authorization.

### 7.5. WAF Costs and Limits

A Shield Advanced subscription includes access to the Layer 7 Anti-DDoS managed rule group and an allowance of up to 50 billion WAF requests per month per payer ID. Requests exceeding the allowance are billed at prevailing rates. Fees for managed rules and WAF features outside the included scope may still apply.

Shield Advanced covers certain standard AWS WAF charges for protected resources, including Web ACL, rule, and request fees up to the default 1,500 WCUs/default body size within the allowance. Bot Control, Fraud Control, Web ACLs above 1,500 WCUs, and body inspection beyond default sizes can still incur extra charges. Check pricing before enabling additional managed rule groups or add-on features.

## 8. Health-Based Detection, Proactive Engagement, and the Shield Response Team

### 8.1. Route 53 Health Checks for Shield Advanced

Shield Advanced can use Route 53 health checks to understand application health and improve detection sensitivity. Health checks can be associated with protected resources, except Route 53 hosted zones. When an application is unhealthy, Shield Advanced can detect events faster and at lower thresholds; when healthy, it requires stronger evidence before declaring an event.

A good health check should:

- Report healthy only when the application operates within defined SLO thresholds.
- Report unhealthy only when users are genuinely impacted.
- Inspect endpoints/responses/latency tied to the resource.
- Optionally combine CloudWatch metrics, application health, and dependency checks.
- Avoid false unhealthy states caused by a non-critical dependency failure.
- Remain maintained for as long as the protected resource requires health-based detection.

Shield Advanced does not manage health checks for you. The health check must be healthy at association time; do not delete a health check in use by Shield Advanced. Health-based detection improves accuracy for L3/L4 resources such as NLB, EIP, and Global Accelerator standard accelerators as well as L7 resources like CloudFront/ALB.

### 8.2. Proactive Engagement

Proactive engagement allows the SRT to reach out proactively when Shield Advanced detects an event and a Route 53 health check associated with the protected resource turns unhealthy. Health checks, contact details, and required permissions/authorizations must be configured before an incident occurs.

Proactive engagement does not mean AWS automatically contacts every Shield Standard customer. It is a conditional Shield Advanced capability; keep escalation contacts accurate and ensure someone is on call to answer phone/email outreach.

### 8.3. Shield Response Team (SRT)

The SRT consists of security engineers specializing in DDoS mitigation. They can:

- Analyze AWS WAF logs to identify attack patterns.
- Assist in creating/tuning WAF rules with customer approval during an engagement.
- Build custom network mitigations for infrastructure-layer attacks.
- Coordinate network traffic engineering to increase mitigation capacity or adjust traffic paths.
- Provide architectural recommendations when design changes are needed.

To engage the SRT, the account requires Shield Advanced and AWS Business Support or Enterprise Support. Do not assume a Shield Advanced subscription automatically includes every AWS Support tier. During an incident, open a support case under AWS Shield with severity matching your support plan; provide protected resource ARNs, symptoms, user impact, timestamps, and traffic details.

### 8.4. Protection Groups

Shield Advanced protection groups let you group protected resources to evaluate events and mitigations collectively—for example, grouping CloudFront distributions, ALBs, and EIPs belonging to one application or environment. Membership criteria can automatically add new matching resources to the group.

Protection groups aid group-level visibility and analysis; they do not automatically convert unprotected resources into protected ones. You must still declare resource protection or apply a Firewall Manager policy.

## 9. Enabling Shield Advanced and Managing Protections

### 9.1. Preparing Before Subscribing

Before enabling Shield Advanced, identify:

- Business-critical applications, RTO/RPO, and availability SLOs.
- Public entry points: Route 53, CloudFront, Global Accelerator, ALB/NLB, EIPs.
- Account/Region ownership and resource ARNs.
- Existing Web ACLs, WAF capacity units (WCUs), managed rules, and request volume.
- Route 53 health checks and escalation contacts.
- Personnel authorized to manage Shield, WAF, Firewall Manager, and AWS Support.
- Budget, 1-year subscription commitment, and usage-based data transfer out.

Shield Advanced is an annual commitment. Review pricing, billing owner/payer ID, and support plan before subscribing. Subscribing does not automatically protect resources; after subscribing, you must still add protected resources.

### 9.2. Adding Resources to Shield Advanced

General Console workflow:

1. Open the AWS WAF & Shield Console.
2. Subscribe to Shield Advanced and confirm the terms/billing commitment.
3. Open **AWS Shield → Protected resources**.
4. Choose **Add resources to protect**.
5. Select Region and resource type; global resources such as CloudFront/Route 53 are selected in their global scope.
6. Load resources and select the resources to protect.
7. For application-layer resources, associate an AWS WAF Web ACL.
8. Configure Route 53 health checks if using health-based detection/proactive engagement.
9. Verify protection status, metrics, notifications, and contact details.
10. Document owner, change ticket, resource ARN, and review date.

Shield Advanced protection applies only to selected resources or those managed by a Firewall Manager policy. Whenever replacing origins, distributions, EIPs, or load balancers, re-verify protection coverage.

### 9.3. Managing Multiple Accounts with AWS Firewall Manager

AWS Firewall Manager centrally manages Shield Advanced protections and AWS WAF policies across AWS Organizations. Security administrators can create policies scoped by OU/account/resource, applying them to existing and newly created resources per policy settings.

Governance design should:

- Designate a clear delegated administrator and security account.
- Classify production, development, and sandbox accounts.
- Create policies for supported resource types/Regions.
- Define Web ACL baselines, managed rule groups, and an exception workflow.
- Route policy compliance findings to Security Hub/SNS or equivalent workflows.
- Track newly created unprotected resources and post-IaC drift.

A Firewall Manager policy does not replace application owner reviews. A Web ACL baseline may require scope-downs/exceptions for webhooks, API clients, or specialized endpoints.

### 9.4. AWS Shield Network Security Director (Preview)

As of November 20, 2026, AWS Shield network security director is described in the AWS FAQ as a preview capability that analyzes topology and network security configurations to surface issues such as overly permissive access and certain DDoS/web threat risks. Analysis must be triggered manually; the preview currently does not support continuous analysis/automated monitoring. It is a network security visibility/remediation tool and does not replace Shield Standard/Advanced DDoS protection or AWS WAF.

## 10. Monitoring, Metrics, and Auditing

DDoS response requires simultaneous visibility across edge, network, load balancer, application, and backend layers. Watching only EC2 CPU can miss attacks being absorbed at the edge or attacks exhausting database connections.

### 10.1. Metrics to Monitor

| Layer | Metrics / Signals | Meaning |
|---|---|---|
| Shield Advanced | DDoS detected, attack bits/packets/requests per second, event status | Identify affected resource and event type |
| CloudFront | Requests, bytes downloaded, 4xx/5xx, origin latency, cache hit ratio | Distinguish traffic spikes, origin failures, and cache behavior |
| AWS WAF | Allowed/Blocked/Counted/Challenge requests, rule labels, sampled requests | Identify request patterns and false positives |
| Route 53 | Health check status, DNS query patterns, failover events | Track user-facing health and DNS behavior |
| ALB/NLB | `RequestCount`, target response time, target 5xx, active/rejected connections | Monitor ingress and target saturation |
| Application | Request rate, latency percentiles, queue depth, worker concurrency, auth failures | Separate legitimate flash crowds from abusive traffic |
| Database/cache | Connections, CPU, latency, throttles, cache hit/miss | Pinpoint backend bottlenecks |
| Billing | Data transfer out, WAF requests, autoscaling and service usage | Detect cost anomalies |

Exact metric names vary by resource type. Use the Shield console, CloudWatch metrics, and service-specific dashboards to choose the right namespaces/dimensions.

### 10.2. Alerts and Event Routing

Create CloudWatch alarms for:

- Shield DDoS event detected on a protected resource.
- Route 53 health check transitioning to unhealthy.
- Sudden spikes in WAF Blocked/Challenge/Counted requests.
- Increases in CloudFront/ALB 5xx errors and origin latency.
- Application error rates, queue age, or database connections breaching SLOs.
- Unexpected increases in data transfer out or usage costs.

Route alarms to SNS/on-call systems or EventBridge incident workflows. Alerts should include resource ARN, Region, event timestamp, dashboard link, runbook, and responsible owner. Never create an alarm based solely on request count without baseline and health context.

### 10.3. WAF Logging and Request Analysis

WAF logs help identify:

- URIs, HTTP methods, headers, and request characteristics.
- Which rules matched and Allow/Block/Count/Challenge actions.
- Labels attached by managed rule groups.
- Source IPs and forwarded IPs when properly configured.
- Request patterns over time and by resource.

Protect WAF logs as security data: restrict access, enforce retention, redact/avoid logging sensitive headers/cookies, and avoid storing credentials/tokens. Do not log full request bodies unnecessarily.

### 10.4. CloudTrail and Auditing Protection Changes

Use CloudTrail to trace who:

- Created, deleted, or updated Shield protections.
- Modified AWS WAF Web ACLs/rules/associations.
- Modified Route 53 health checks or DNS records.
- Updated CloudFront distributions/origins.
- Modified security groups, NACLs, ALBs/NLBs, and Firewall Manager policies.
- Changed contacts/permissions for SRT or security automation.

Use a multi-Region/organization CloudTrail trail and centralized S3 archive per audit requirements. Link protection changes to change tickets/IaC deployments to separate approved changes from anomalous ones.

## 11. Costs and DDoS Cost Protection

### 11.1. Shield Standard

Shield Standard is enabled automatically with no separate Shield fee. Accompanying services such as CloudFront, Route 53, WAF, ELB, or data transfer still carry their own usage pricing.

### 11.2. Shield Advanced

Per AWS pricing checked on November 20, 2026:

- The subscription fee is **3,000 USD/month for the payer account** when the payer account or at least one linked account subscribes and the payer owns the linked accounts/resources per billing terms.
- Requires a **1-year** subscription commitment; subscriptions auto-renew annually unless canceled within the proper notice window.
- Usage-based fees apply for data transfer out from protected resources such as CloudFront, ELB, EC2, and Global Accelerator.
- The subscription includes certain standard AWS WAF fees for protected resources: Web ACL, rule, and request fees up to the default 1,500 WCUs/default body size within the allowance.
- Allowance of up to 50 billion AWS WAF requests per payer ID per calendar month; excess requests are billed per the pricing table. Requests identified by Shield Advanced as DDoS do not count toward this allowance.
- Bot Control, Fraud Control, WAF Web ACLs over 1,500 WCUs, body inspection above default size, and certain managed-rule fees may still be billed separately.

Per-GB/Region/resource rates and traffic-dependent charges can change. Always use AWS Shield Pricing and the AWS Pricing Calculator to estimate costs before subscribing.

### 11.3. DDoS Cost Protection

Shield Advanced provides cost protection for certain usage spikes caused by DDoS attacks, such as data transfer out fees on protected resources. The benefit is issued as Shield Advanced service credits, not a guarantee to refund all incurred costs or automatically offset an entire bill.

DDoS cost protection depends on eligibility terms, protected resource status, the 1-year subscription commitment, the credit request process, and incident evidence. Preserve CloudTrail, Shield event reports, CloudWatch metrics, WAF logs, billing data, and the incident timeline to support claims.

### 11.4. Controlling Costs and Avoiding Overprovisioning

- Cache more at CloudFront to reduce origin requests/data processing.
- Select protected resources deliberately; if an ALB only receives traffic from CloudFront, consider protecting CloudFront per pricing guidance.
- Use WAF scope-down statements to limit traffic evaluated by managed rule groups where appropriate.
- Monitor WAF requests, WCUs, Bot/Fraud features, and data transfer out.
- Use Auto Scaling with min/max bounds, concurrency limits, and budget alarms.
- Never scale databases unboundedly to absorb invalid traffic.
- Factor cost protection into your risk model, but never use it as an excuse to skip capacity/caching design.

## 12. DDoS Detection and Response Runbook

Runbooks should be written and rehearsed before an incident. When anomalous traffic is detected, the goal is to maintain availability for legitimate users, identify the attacked layer, limit blast radius, and preserve evidence for post-incident review.

### 12.1. Detect and Confirm Impact

1. Identify the protected resource, account, Region, and event start time.
2. Check Shield Advanced event details/metrics if the resource is protected.
3. Compare CloudFront, WAF, ALB/NLB, application, and database metrics against baselines.
4. Check Route 53 health checks and user-facing synthetic monitoring.
5. Distinguish legitimate traffic spikes (flash crowds, campaigns, launches) from attack patterns.
6. Identify endpoints, URIs, source IPs/ASNs, user agents, token status, request rates, and backend cost.

Do not rely solely on total request count. A legitimate flash crowd can raise request counts with a high cache hit ratio, whereas an attack can target one DB-heavy URI and cause high latency even at lower total request counts.

### 12.2. Contain and Mitigate

Depending on the attack layer:

- **L3/L4:** rely on Shield/edge mitigation; verify resource protection, Global Accelerator/CloudFront/Route 53 paths, security groups/NACLs, and health.
- **L7 HTTP flood:** inspect WAF labels/logs, Anti-DDoS AMR, rate-based rules, scope-down statements, Challenge/Block sensitivity, and caching.
- **Origin overload:** increase caching, restrict direct origin access, reduce concurrency, queue work, engage circuit breakers, and temporarily shed expensive non-critical endpoints per the incident plan.
- **Backend bottleneck:** check connection pools, database throttling, queue age, and worker saturation; do not scale capacity without bounds.
- **False positives:** switch problematic rules to Count or lower sensitivity carefully; create narrow exceptions rather than opening broad allowlists.

If using Shield Advanced, contact the SRT per your support plan when an event impacts availability. Provide resource ARNs, event timestamps, user impact, metrics, WAF logs, and mitigations already attempted.

### 12.3. Communicate and Preserve Evidence

- Activate the incident commander and on-call owners.
- Update service status, impact scope, workarounds, and next update time.
- Preserve Shield event reports, WAF logs, CloudFront/ALB metrics, application logs, CloudTrail events, and billing evidence.
- Document rule/policy changes, approvers, timestamps, and outcomes.
- Never delete logs or disable audit logging during incident handling.

### 12.4. Recover and Learn

1. Gradually relax temporary mitigations once traffic stabilizes.
2. Verify legitimate users can complete critical workflows.
3. Confirm origins/backends have returned to baseline with no remaining queue backlog.
4. Check cache behavior, WAF false positives, and health checks.
5. Evaluate data transfer, WAF usage, autoscaling, and cost anomalies.
6. Write a post-incident review covering timeline, root cause, control gaps, decision points, and action owners.
7. Update runbooks, architecture diagrams, WAF rules, capacity plans, and escalation contacts.

## 13. Hands-On Labs in an AWS Sandbox

The labs below use learner-managed sandbox resources. Never generate DDoS traffic against public systems, third-party endpoints, or production resources. If simulating attack traffic, comply with the AWS DDoS simulation testing policy and use only AWS-authorized methods/providers.

### 13.1. Lab A — Building the Web Entry Path

1. Create a CloudFront distribution in front of a test application.
2. Create a Route 53 hosted zone/record if using a sandbox domain.
3. Associate an AWS WAF Web ACL with CloudFront.
4. Configure the origin as a private S3 bucket using OAC or an ALB inside a VPC.
5. If using an ALB, try a CloudFront VPC origin to keep the origin in private subnets.
6. Verify requests traverse CloudFront and the origin is unreachable directly from the Internet.
7. Check cache hit ratio and origin request count.

### 13.2. Lab B — AWS WAF Rate-Based Rule

1. Create a sandbox Web ACL and associate it with a test CloudFront distribution or ALB.
2. Create a rate-based rule for a test path such as `/login-test`.
3. Set the action to Count first to observe.
4. Send normal traffic from a test client within allowed limits.
5. Inspect WAF metrics, sampled requests, and logs.
6. Switch the action to Block/Challenge after verifying false positives.
7. Send requests to another path to confirm scope-down applies only to the target endpoint.

### 13.3. Lab C — Anti-DDoS Managed Rule Group

1. Confirm the account/Region/resource supports the AWS WAF managed rule group.
2. Add `AWSManagedRulesAntiDDoSRuleSet` to the sandbox Web ACL.
3. Review WCU usage and managed rule configuration.
4. Inspect labels recorded in WAF logs/metrics.
5. Verify which URIs are challengeable; exclude webhooks/API clients that do not support browser challenges.
6. Observe Count/Challenge/Block actions and test legitimate traffic.
7. Record request volume and pricing implications.

Do not attempt to generate an attack flood to trigger the rule group. Use sample logs/test cases or AWS-approved simulations per policy.

### 13.4. Lab D — Shield Advanced Protection and Health Checks

1. Proceed only with an approved sandbox account and subscription; review commitments/costs first.
2. Add a sandbox CloudFront distribution or ALB to Shield Advanced protected resources.
3. Create a Route 53 health check reflecting application health.
4. Associate the health check with the protection and confirm it is healthy.
5. Inspect Shield metrics/event visibility and configure notifications.
6. Review how to enable proactive engagement/contact details if eligible.
7. Clean up resource protections after the lab per subscription/resource policy; do not cancel subscriptions outside contract windows.

### 13.5. Lab E — Origin Protection

1. Create a private S3 bucket or private ALB origin.
2. For S3, use OAC and a bucket policy allowing only the CloudFront distribution.
3. For a VPC origin, place the ALB/NLB/EC2 in private subnets and configure a CloudFront VPC origin.
4. Attempt to access the origin directly from the Internet; requests must not succeed over a public path.
5. Verify CloudFront still serves the application.
6. Audit security groups, bucket policies, and CloudFront origin settings.

### 13.6. Lab F — Monitoring and Incident Drill

1. Create a CloudWatch dashboard covering CloudFront, WAF, ALB, and application metrics.
2. Create alarms for WAF blocked requests, origin 5xx errors, and unhealthy health checks.
3. Route alarms to an SNS/EventBridge test workflow.
4. Send valid test traffic to establish a baseline and observe metrics.
5. Run a tabletop exercise: simulate an HTTP flood against the search endpoint.
6. Walk through detect, contain, communicate, and recover steps per the runbook.
7. Document gaps in dashboards, alerts, contact lists, and escalation processes.

## 14. Pre-Production DDoS Resiliency Review Checklist

### Architecture and Entry Points

- [ ] Are all public entry points, origins, DNS records, and EIPs inventoried?
- [ ] Do Route 53/CloudFront/Global Accelerator match protocols and traffic patterns?
- [ ] Is static/dynamic content cached under safe policies?
- [ ] Are origins protected from direct access/bypass?
- [ ] Are CloudFront VPC origins or S3 OAC used where appropriate?
- [ ] Does the backend enforce Auto Scaling, concurrency limits, queues, and circuit breakers?
- [ ] Are multi-AZ/failover and dependency health checks in place?

### Shield and WAF Coverage

- [ ] Is it understood that Shield Standard is automatic and covers only common L3/L4 attacks?
- [ ] Has Shield Advanced necessity been evaluated against business impact/risk/cost?
- [ ] Are all resources needing Shield Advanced explicitly protected or covered by a Firewall Manager policy?
- [ ] Have resource type/IPv4 support/association paths been verified?
- [ ] Are WAF Web ACLs attached to the right CloudFront/ALB/API resources?
- [ ] Has the Anti-DDoS Managed Rule Group been evaluated under current service availability?
- [ ] Have rate-based rules undergone scope-down, threshold, and false-positive reviews?
- [ ] Are Challenge-incompatible API clients/webhooks handled separately?

### Health, Monitoring, and Response

- [ ] Do Route 53 health checks reflect application health and remain maintained?
- [ ] Are proactive engagement/contact details configured if used?
- [ ] Are SRT eligibility and Business/Enterprise Support confirmed?
- [ ] Are CloudWatch dashboards and alarms active from edge to database?
- [ ] Are WAF logs/Shield events/CloudTrail retained with controlled access?
- [ ] Are an incident commander, on-call contacts, and runbook established?
- [ ] Have DDoS tabletop and recovery drills been conducted?

### Cost and Governance

- [ ] Have the Shield Advanced 1-year subscription and DTO usage fees been estimated?
- [ ] Have the 50B WAF request allowance, WCUs, and non-standard WAF charges been checked?
- [ ] Are DDoS cost protection eligibility and credit processes understood?
- [ ] Do Firewall Manager policies cover account/resource lifecycles?
- [ ] Are owners, an exception process, and a protection coverage review schedule defined?

## 15. Self-Assessment Questions

1. How does DDoS differ from DoS?
2. How do volumetric, protocol, and application-layer attacks differ?
3. How does a UDP reflection/amplification attack work?
4. What type of resource does a TCP SYN flood exhaust?
5. Why can an HTTP request flood cause damage even when requests are syntactically valid?
6. Does AWS Shield Standard require manual enablement or carry a separate Shield fee?
7. Which layers does Shield Standard protect?
8. What capabilities does Shield Advanced add?
9. Which resource types can Shield Advanced protect?
10. Does Shield Advanced automatically protect every resource in an account?
11. Why must IPv4/IPv6 support be checked?
12. How does Route 53 improve DDoS resiliency?
13. Through which mechanisms does CloudFront offload origins?
14. For which use cases is Global Accelerator better suited than CloudFront?
15. At which layer does AWS WAF operate and what does a Web ACL do?
16. Why does WAF not replace upstream DDoS mitigation?
17. Why must origins be protected from direct access when using CloudFront?
18. Which origin types do CloudFront VPC origins support?
19. Which origin type is OAC used to protect?
20. How does a rate-based rule differ from a per-user/tenant business quota?
21. Why should Count be used before Block?
22. On what date did the Anti-DDoS Managed Rule Group become the default solution?
23. What is the name of the AWS Anti-DDoS managed rule group and how many WCUs does it use?
24. How do soft mitigation and hard mitigation differ?
25. Why should you not block all requests carrying the `event-detected` label?
26. When can a browser Challenge cause false positives?
27. What does health-based detection use Route 53 health checks for?
28. Which health check condition is required for SRT proactive engagement?
29. Which AWS Support plans are required for SRT?
30. Which activities can the SRT assist with during a DDoS incident?
31. Do protection groups automatically protect new resources?
32. How does AWS Firewall Manager support DDoS governance?
33. In what form does Shield Advanced provide cost protection?
34. Which components make up Shield Advanced pricing?
35. Which metrics should be monitored across CloudFront/WAF/ALB/backend?
36. Which detect, contain, communicate, and recover steps belong in a DDoS runbook?

### Answer Guide

- **Attack layers:** L3 saturates networks; L4 exploits protocol/connection state; L7 exhausts applications/backends via request floods.
- **Shield Standard:** automatic, no separate Shield fee, focuses on common L3/L4.
- **Shield Advanced:** paid subscription, explicit protected resources, enhanced visibility/mitigation, WAF integration, health-based detection, SRT, and conditional cost credits.
- **Architecture:** Route 53/CloudFront/Global Accelerator at entry; WAF at L7; private/restricted origins; caching, bounded scaling, and queues to ease backend pressure.
- **2026 L7:** Anti-DDoS Managed Rule Group became the default deployment path on March 26, 2026; legacy L7AM remains available for existing customers.
- **Response:** health checks, metrics, WAF logs, CloudTrail, SRT, and runbooks enable controlled response.
- **Cost:** 1-year commitment, monthly subscription, data transfer out usage, WAF request/WCU allowances, and credit eligibility must all be evaluated.

## 16. Design Scenario: Protecting an E-Commerce Website

An e-commerce website has a static frontend, login/search/checkout APIs, and an RDS database. Normal traffic peaks during business hours; during flash sales, requests spike sharply. The system faces HTTP flood risks against search/login endpoints, and attackers may try accessing the ALB origin directly.

### 16.1. Requirements Analysis

- The frontend must distribute quickly and withstand global traffic spikes.
- APIs must protect database-heavy endpoints and enforce per-tenant/user limits.
- Orders/payments must preserve correctness, idempotency, and avoid queue floods.
- Origins must not allow bypassing CloudFront/WAF.
- Operations need rapid detection, SRT escalation, and cost control.

### 16.2. Proposed Architecture

1. Route 53 serves DNS and application health checks.
2. CloudFront serves as the public entry point; static assets are cached at the edge.
3. An AWS WAF Web ACL associates with CloudFront, including baseline managed rules, Anti-DDoS AMR, and per-endpoint rate-based rules.
4. A CloudFront VPC origin connects to an ALB in private subnets; security groups allow only valid origin traffic.
5. The ALB distributes across ECS/EKS targets spanning multiple Availability Zones.
6. API authentication and per-user/tenant quotas run before expensive operations.
7. Search uses caching/query limits; orders/payments use idempotency and queues for asynchronous processing.
8. RDS connection pools and worker concurrency are capped; autoscaling has min/max limits.
9. Shield Standard automatically protects common L3/L4; if business impact warrants, subscribe to Shield Advanced and protect the CloudFront distribution, Route 53 hosted zone, or eligible resources.
10. Route 53 health checks reflect application health; CloudWatch alarms/WAF logs/Shield events route to on-call.

### 16.3. Decisions and Trade-Offs

| Decision | Rationale | Trade-Off to Manage |
|---|---|---|
| CloudFront as public entry | Absorbs edge traffic, caches static assets, hides origin | Cache policies and invalidations must be accurate |
| VPC origin for ALB | Origin stays private, reducing direct-origin bypass | Verify compatibility and network configuration |
| Anti-DDoS AMR + rate rules | Detects HTTP floods and limits endpoints | Challenge does not suit all API clients; test false positives |
| Application/API quotas | Limits by user/tenant, protects business operations | Requires identity and distributed rate-limit state |
| Queues + concurrency caps | Decouples request bursts from workers/databases | Queue backlogs need alarms and dead-letter handling |
| Shield Advanced | Enhanced visibility, mitigation, SRT, and cost credits | 1-year subscription, DTO usage, and WAF costs require budgeting |

### 16.4. Incident Scenario

Suppose during a flash sale, search requests surge manyfold and ALB target response times climb:

1. Check CloudFront cache hit ratio; if low, inspect cache keys and response headers.
2. Inspect WAF logs/Anti-DDoS labels to identify request patterns and endpoints.
3. Check Shield event details and Route 53 health checks.
4. Tune rate limits/scope-downs for search after confirming legitimate traffic; do not block all `event-detected` traffic.
5. Tighten caching/query limits or temporarily degrade expensive search features per the incident plan.
6. Keep the order/payment path healthy using queues and idempotency.
7. Contact the SRT if a Shield Advanced event impacts availability and the support plan is eligible.
8. Post-incident, refine cache policies, WAF sensitivity, capacity plans, and alert thresholds.

Takeaway: a sound architecture does not try to absorb every request simply by scaling the backend. It absorbs traffic at the edge, sends only necessary requests to the origin, bounds processing cost, and keeps critical business flows operational.

## 17. Official AWS Documentation

1. [How AWS Shield and Shield Advanced work](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-overview.html) — DDoS concepts, Shield Standard/Advanced, and attack classes.
2. [AWS Shield Standard overview](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-standard-summary.html) — Standard protection and edge services.
3. [AWS Shield Advanced capabilities and options](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary-capabilities.html) — Advanced features, WAF, health checks, protection groups, SRT, and cost protection.
4. [Resources protected by Shield Advanced](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary-protected-resources.html) — Resource types and explicit protection requirements.
5. [Building DDoS resilient architectures](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-resiliency.html) — Architecture patterns for web and TCP/UDP.
6. [Example Shield Advanced web architecture](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-resiliency-example-web.html) — Route 53, CloudFront, WAF, ELB, and EC2.
7. [AWS Best Practices for DDoS Resiliency](https://docs.aws.amazon.com/whitepapers/latest/aws-best-practices-ddos-resiliency/welcome.html) — Comprehensive best practices.
8. [Protecting your origin](https://docs.aws.amazon.com/whitepapers/latest/aws-best-practices-ddos-resiliency/protecting-your-origin-bp1-bp5.html) — CloudFront VPC origins and S3 OAC.
9. [AWS WAF Anti-DDoS Managed Rule Group](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-anti-ddos.html) — Rule group, labels, challenge, and block.
10. [Automating application layer DDoS mitigation](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-automatic-app-layer-response.html) — L7AM and Anti-DDoS AMR transition as of March 26, 2026.
11. [Health-based detection with Shield Advanced](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-health-checks.html) — Route 53 health checks and detection sensitivity.
12. [Shield Response Team support](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-srt-support.html) — SRT capabilities and support-plan requirements.
13. [Setting up Shield Response Team support](https://docs.aws.amazon.com/waf/latest/developerguide/authorize-srt.html) — Permissions and proactive engagement.
14. [AWS Shield Advanced pricing](https://aws.amazon.com/shield/pricing/) — Subscription, data transfer out, WAF request allowance, and pricing examples.
15. [AWS Shield FAQs](https://aws.amazon.com/shield/faqs/) — Shield capabilities, cost, and network security director preview.
16. [AWS Firewall Manager](https://docs.aws.amazon.com/waf/latest/developerguide/fms-chapter.html) — Centralized WAF and Shield policy management.
17. [AWS WAF rate-based rules](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html) — Rate-based rules and aggregation.
18. [AWS WAF scope-down statements](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-scope-down-statements.html) — Limiting evaluated traffic and controlling costs.
19. [AWS Shield DDoS testing policy](https://aws.amazon.com/security/ddos-simulation-testing/) — Rules for DDoS simulation testing on AWS.

> **Final Takeaway:** Shield Standard provides automatic L3/L4 protection; Shield Advanced adds enhanced detection, mitigation, visibility, WAF integration, SRT, and conditional cost protection. A resilient architecture places Route 53/CloudFront/Global Accelerator at entry, AWS WAF at L7, origins protected from bypass, backends equipped with caching/queues/limits, and operations equipped with health checks, metrics, alerts, and runbooks. Verify service changes, resource coverage, and pricing before production deployment.
