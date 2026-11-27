# Routing by Host, Path, Header, and Weight

> **Chapter:** Load Balancing and Scaling  
> **Module:** CLOUD_PROVIDERS_AWS — exploring Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; practicing how to select services, design, and deploy secure, monitored, resilient, and cost-controlled applications.

## Learning Objectives

As an application grows from a single web server into multiple services such as a frontend, API, dashboard, and worker, simply distributing requests evenly across servers is no longer enough. You also need to decide **which request goes to which service**, which version receives experimental traffic, and how to handle deployments or unhealthy target pools.

AWS's **Application Load Balancer (ALB)** is a **Layer 7** load balancer capable of processing HTTP/HTTPS, evaluating **listener rules** based on hostname, URL path, HTTP headers, and other attributes, and forwarding requests to one or more **target groups**. Within a forward action, **weights** allow gradually splitting traffic between a stable version and a new version.

After this lesson, you will be able to:

1. Explain the relationship between **ALB, listener, listener rule, condition, action, target group, and target**.
2. Design routing by **host**, **path**, and **HTTP header**, as well as combine multiple conditions within a single rule.
3. Understand **priority**, the **default rule**, **AND/OR** matching logic, and wildcard/regex limits according to service capabilities.
4. Configure **weighted target groups** for canary or blue/green deployments; distinguish traffic routing from **Auto Scaling**.
5. Diagnose misrouted requests, 404/403/5xx errors, unhealthy targets, TLS/Host mismatches, altered headers, or unexpected weight distributions.
6. Use the AWS CLI to **inspect configurations** and test rules in a sandbox, including verification and resource cleanup steps.
7. Propose security, monitoring, rollback, multi-AZ, and cost-optimization measures.

## 1. The Big Picture: From DNS to the Application

A domain name like `api.example.com` can have DNS configured to point to an ALB. The ALB accepts connections on a **listener** (e.g., HTTPS:443), evaluates rules, and forwards requests to the matching target group. Each target group can contain multiple EC2 instances, IP addresses, or Lambda functions depending on target type and service support.

~~~mermaid
flowchart TD
    U[Client / Browser] --> DNS[DNS: api.example.com]
    DNS --> LB[Application Load Balancer]
    LB --> L[HTTPS listener :443]
    L --> R{Listener rules by priority}
    R -->|Host api.example.com, Path /v1/*| TG1[Target group: api-v1]
    R -->|Host shop.example.com, Path /images/*| TG2[Target group: image-service]
    R -->|Header X-Release: beta| TG3[Target group: api-beta]
    R -->|No rule matches| DEF[Default action]
    TG1 --> A1[EC2 / ECS / IP targets]
    TG2 --> A2[EC2 / ECS / IP targets]
    TG3 --> A3[EC2 / ECS / IP targets]
~~~

**VPC/AZ and ALB:** ALB attaches to subnets in enabled Availability Zones. Backends behind it can be operated with **EC2 Auto Scaling**, **Amazon ECS**, or other platforms, using health checks so ALB determines which targets can receive traffic. Routing rules neither create more EC2 instances nor guarantee recovery on their own.

### 1.1. Components and Responsibilities

| Component | What Is It? | Question It Answers |
|---|---|---|
| **ALB** | Layer 7 load balancer receiving HTTP/HTTPS | Where does client traffic enter? |
| **Listener** | Port and protocol accepting connections, with a default action | Port 80 or 443? Is there a TLS certificate? |
| **Listener rule** | Conditions, priority order, and action | Which rule does this request match? |
| **Condition** | Host/path/header/query/method/IP, etc. | Does this request need special routing? |
| **Action** | Forward, redirect, fixed response; optionally auth depending on context | How is the request forwarded or answered? |
| **Target group** | Pool of targets and health checks | Which service or version receives the request? |
| **Target** | EC2 instance, IP, or Lambda per target type | Which specific workload processes the request? |
| **Health check** | Target status probe | Is the target healthy enough to receive requests? |

Logical configuration example:

~~~text
Listener HTTPS :443
  priority 10 -> Host admin.example.com                -> tg-admin
  priority 20 -> Host api.example.com + Header beta    -> tg-api-beta
  priority 30 -> Host api.example.com + Path /v1/*     -> tg-api-v1
  priority 40 -> Host api.example.com + Path /v2/*     -> tg-api-v2
  default     -> fixed-response 404
~~~

**Lower priority numbers are evaluated earlier.** Once a listener rule matches and its action executes, ALB stops evaluating lower-priority rules. Therefore, rule ordering is part of application design.

### 1.2. Why Focus on ALB?

AWS also provides **Network Load Balancer (NLB)** and **Gateway Load Balancer (GWLB)**, but **routing by host, URL path, and HTTP headers is ALB's core strength**. NLB primarily serves Layer 4 scenarios and uses a different rule/action model; do not mechanically apply the ALB guidance in this lesson to NLB.

## 2. How ALB Evaluates Listener Rules

### 2.1. Priority Order and Default Action

Every listener always has a **default rule**. Each non-default rule has a unique **priority** within that listener and is evaluated in ascending numeric order; the default rule is evaluated last and has no conditions.

~~~mermaid
flowchart TD
    A[Request arrives at HTTPS listener :443] --> B{Priority 10 matches?}
    B -->|Yes| X[Execute rule 10 action]
    B -->|No| C{Priority 20 matches?}
    C -->|Yes| Y[Execute rule 20 action]
    C -->|No| D{Priority 30 matches?}
    D -->|Yes| Z[Execute rule 30 action]
    D -->|No| E[Default action]
~~~

Safe practices:

- **Specific first, general later:** `Host=api.example.com` + `Header=X-Release:beta` should precede a rule matching only `Host=api.example.com`.
- **Priority is not weight:** priorities 10/20 determine **condition evaluation order**, whereas weights 90/10 determine **request distribution across target groups** inside a single forward action.
- **The default rule has no conditions:** you can configure a fixed-response 404 for undeclared hosts/paths, or intentionally route to a fallback target group.
- With overlapping rule conditions, **the first matching rule** wins. There is no "stacking" of routing effects across multiple matched rules.

### 2.2. Combining AND Conditions and OR Values

ALB supports common condition types: `host-header`, `path-pattern`, `http-header`, `http-request-method`, `query-string`, and `source-ip`.

- Multiple **conditions** of different types within the same rule are combined with **AND** logic: the request must satisfy **every condition**.
- When a single condition lists multiple **values** to match, matching any one value is sufficient (**OR**).
- With multiple `http-header` or `query-string` conditions in one rule, each condition must still be satisfied.
- AWS enforces **quotas** on conditions, match evaluations, and wildcards per rule. Check current quotas before building complex patterns.

Example:

~~~text
Condition A: host-header ∈ { api.example.com, service.example.com }
Condition B: path-pattern ∈ { /v1/*, /legacy/* }
Condition C: X-Channel ∈ { partner, internal }

Rule matches when:
    (host = api.example.com OR service.example.com)
AND (path matches /v1/* OR /legacy/*)
AND (header X-Channel = partner OR internal)
~~~

This reduces duplicate rules, though you should avoid packing too many conditions together if operators can no longer clearly trace request flows and access rules.

### 2.3. Listener Rule Actions

A rule typically ends with one terminating action:

| Action | Effect | Scenario |
|---|---|---|
| **forward** | Sends requests to one or more target groups | Service split, canary/blue-green |
| **redirect** | Returns HTTP 301/302 to a different URL | Redirecting HTTP to HTTPS, domain changes |
| **fixed-response** | ALB returns a configured status/body directly | 404 for unmatched paths, 403 for blocked routes |
| **authenticate-cognito** / **authenticate-oidc** | Authenticates via ALB-supported integration before the final action | Apps requiring login at the ingress tier |

On supported listeners, a rule can include an **authentication action** before a `forward` action; a valid terminating action is still required per ALB rules. AWS also supports **host header rewrite and URL rewrite transforms** on eligible listener rules: these are explicit features—do not assume standard path routing strips or alters the path automatically.

## 3. Host-Based Routing: One ALB, Multiple Domains

### 3.1. Host Matching Principles

**Host-based routing** selects a target group based on the **HTTP Host header**, for example:

~~~text
shop.example.com   -> tg-web-shop
api.example.com    -> tg-api
admin.example.com  -> tg-admin
~~~

With HTTPS, the client completes the TLS handshake, ALB picks the right certificate using TLS/SNI settings, and then evaluates HTTP requests against listener rules. **A Host header used for routing is not equivalent to a TLS certificate or user identity.** Clients can send arbitrary Host headers in many situations, so never treat Host conditions as authentication or authorization.

### 3.2. JSON Condition Example

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": [
        "api.example.com",
        "service.example.com"
      ]
    }
  }
]
~~~

For value matching, ALB supports wildcards such as `*` and `?` per documented rules. For instance, `*.example.com` matches subdomains like `api.example.com`, **not necessarily the apex domain** `example.com`. Hostname matching is case-insensitive.

Some current ALB rule features also support **regular expression matching** for host/path/header via `RegexValues`. Regex brings additional syntax and quota constraints; use it only when standard value/pattern matching is insufficient, and test with sample requests.

### 3.3. Design Choices

E-commerce system example:

| Host | Target group | Service |
|---|---|---|
| `shop.example.com` | `tg-web` | Buyer frontend |
| `api.example.com` | `tg-api` | Backend API |
| `seller.example.com` | `tg-seller` | Seller portal |
| `admin.example.com` | `tg-admin` | Internal administration |

Even on the same ALB, **the admin portal still needs identity and network controls**. A Host rule for `admin.example.com` does not prevent strangers from crafting an HTTP request with that header. Apply AWS WAF, ALB authentication, application security controls, and internal network design as needed.

## 4. Path-Based Routing: Splitting Services by URL

### 4.1. The `path-pattern` Condition

Path-based routing inspects the **URL path**, excluding the query string. For example:

~~~text
https://app.example.com/api/orders/123  -> tg-api
https://app.example.com/static/logo.svg -> tg-static
https://app.example.com/admin/users     -> tg-admin
https://app.example.com/                -> tg-web
~~~

Example condition:

~~~json
[
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": [
        "/api/*",
        "/v2/*"
      ]
    }
  }
]
~~~

Patterns are evaluated against the request path after ALB normalization. **Path matching is case-sensitive** per published AWS rules; query strings are excluded from `path-pattern` matching. If you need to match `?region=us`, use a separate `query-string` condition.

### 4.2. Path Forwarding Does Not Rewrite URLs by Default

Suppose a rule matches `/api/*` and the request is:

~~~text
GET https://app.example.com/api/orders/123?include=items
~~~

If you only configure a `path-pattern` condition with a `forward` action, the backend normally receives **`/api/orders/123`**; ALB **does not strip `/api`** merely because it matched. If the backend only exposes `/orders/123`, you must:

1. Teach the backend to accept the `/api` prefix; or
2. Configure a **URL rewrite transform** when supported by the listener/service, with tested patterns and replacements; or
3. Use another ingress/reverse proxy tier responsible for rewriting.

Avoid inferring rewrite behavior from the action name. Altering paths can affect request signatures, cache keys, authorization, and logs/tracing.

### 4.3. Avoiding Shadowed Rules

Suppose you have two rules:

~~~text
priority 10: path /api/* -> tg-api-default
priority 20: path /api/internal/* -> tg-api-internal
~~~

Every `/api/internal/users` request matches priority 10 first and **never reaches rule 20**. Reverse the order:

~~~text
priority 10: path /api/internal/* -> tg-api-internal
priority 20: path /api/*          -> tg-api-default
~~~

This is one of the most common mistakes in systems with many microservices or legacy routes. Map out priority order and run a sample request suite before applying new rules.

## 5. HTTP Header Routing: Splitting Traffic by Request Metadata

### 5.1. How `http-header` Conditions Work

ALB can match an HTTP header by name and value. For example, a client sends:

~~~http
GET /checkout HTTP/1.1
Host: shop.example.com
X-Release: canary
~~~

A rule with `Host=shop.example.com`, `Path=/checkout*`, and `X-Release=canary` can route that request to a new target group.

Example condition:

~~~json
[
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

Header names and values match according to ALB's case-insensitive rules. Header names, values, wildcards, and regex have limits; certain security settings like `routing.http.drop_invalid_header_fields.enabled` can cause ALB to drop invalid headers.

### 5.2. Combining Host + Path + Header

Full condition example:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["shop.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/checkout*"]
    }
  },
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

This rule matches only when **host, path, and header** all align. Without the header, requests fall through to a lower-priority rule pointing to the stable target group or the defined default action.

### 5.3. Client-Sent Headers Are Not Proof of Identity

Setting `X-Release: canary` with `curl` is trivial, so:

- Use header routing for **canary testing, test-channel selection, or client-capability routing** when the system accepts that header source.
- **Never use self-declared client headers to authenticate** customers, select tenants, grant admin privileges, or enforce data-access policies.
- If a trusted proxy/edge component injects the header, ensure clients cannot supply or spoof that same header to bypass rules.
- For sensitive access, rely on **IAM/OIDC/Cognito, application authorization, AWS WAF**, and proper backend controls.

Header conditions do not block direct access to backends over other network paths. Place targets in subnets/security groups configured to accept only authorized traffic paths.

## 6. Weighted Target Groups: Splitting Traffic by Ratio

### 6.1. Where Do Weights Apply?

Within a **`forward` action** targeting multiple target groups, ALB can split traffic using a **weight** per group. Weights are integers within AWS-defined bounds (typically **0–999** per group), and the theoretical share for a group with positive weight is:

~~~text
Traffic share of group i
≈ weight_i / sum of weights across configured groups
~~~

Example:

| Target group | Weight | Expected Share |
|---|---:|---:|
| `tg-stable` | 90 | 90% |
| `tg-canary` | 10 | 10% |
| Total | 100 | 100% |

Observed ratios may not hit exactly 90/10 in a short window due to statistical variance, request counts, stickiness, client errors, and workload behavior. Weight **is not target count**: a target group with 5 EC2 instances does not automatically receive 5x the traffic of a group with 1 EC2 instance.

### 6.2. `ForwardConfig` Example

~~~json
[
  {
    "Type": "forward",
    "ForwardConfig": {
      "TargetGroups": [
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-stable/1111111111111111",
          "Weight": 90
        },
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-canary/2222222222222222",
          "Weight": 10
        }
      ],
      "TargetGroupStickinessConfig": {
        "Enabled": false
      }
    }
  }
]
~~~

All ARNs above are **illustrative placeholders**. Within a single forward action, AWS supports multiple target groups up to service limits; use groups compatible with the listener and consider each group's internal distribution algorithm.

**Separate two levels of distribution:**

1. **Across target groups:** driven by the weights configured in the forward action.
2. **Across targets within the same target group:** driven by the target group's algorithm/settings and target health states.

A single rule can use `host-header`/`path-pattern` to select an application while using weighted forwarding to split traffic between two versions of that application.

### 6.3. Critical Rule: Weight Is Not Failover

**ALB does not automatically shift weight to another target group when a weighted target group is empty or completely unhealthy.** Therefore, if `tg-canary` has weight 10 and all of its targets fail health checks, never assume 100% of traffic will automatically divert to `tg-stable`.

Operational design practices:

- Configure **health checks** for every target group.
- Monitor `HealthyHostCount`, `UnHealthyHostCount`, HTTP 5xx, and latency.
- Maintain the ability to **roll back canary weight to 0** or revert the rule to stable when alarm thresholds trigger.
- Combine with deployment automation / Auto Scaling to replace unhealthy targets.
- Test rollback procedures in a sandbox instead of treating health checks as a complete failover plan.

Inside a single target group there may be fail-open behavior or service-level health thresholds; do not extrapolate from that to assume **weighted group routing provides automatic inter-group failover**.

### 6.4. Target Group Stickiness

If a client must stay pinned to the same **target group** across requests, enable `TargetGroupStickinessConfig` with an appropriate duration. ALB then uses a service cookie to preserve group selection so users do not bounce back and forth between stable and canary versions.

Distinguish:

- **Target-group stickiness:** pins a client to a **group** within a weighted forward action.
- **Target stickiness:** pins a client to **a single target** inside a target group via separate target-group attributes.

Stickiness can skew observed traffic away from configured weights and causes issues for clients that do not store cookies or for stateless APIs. If an application requires session state, prefer storing sessions outside EC2 (such as Redis/DynamoDB where appropriate) to avoid node affinity; enable stickiness only with clear justification.

## 7. Canary, Blue/Green, and Phased Rollouts

### 7.1. Canary Rollout Using Weights

Suppose the same API endpoint has two versions:

- **Stable:** `tg-api-v1` running the proven version.
- **Canary:** `tg-api-v2` running the new version.

Example rollout strategy:

| Stage | Stable | Canary | Criteria to Proceed |
|---|---:|---:|---|
| Smoke check | 100 | 0 | Canary deployed, health checks and smoke tests pass |
| Small canary | 99 | 1 | Error rate/latency steady, sufficient request sample |
| Expanded canary | 90 | 10 | 5xx, p95/p99, and business metrics healthy |
| Gradual shift | 50 | 50 | No regressions, system has adequate capacity |
| Complete | 0 | 100 | Criteria met; retain rollback capability during watch window |

**These percentages are an illustrative plan.** Do not raise weights on a fixed timer before collecting enough requests to detect rare errors. At low traffic, 1% may yield too few requests to draw conclusions.

~~~mermaid
flowchart LR
    U[Clients] --> ALB[ALB listener rule]
    ALB -->|90% expected| ST[Stable target group]
    ALB -->|10% expected| CA[Canary target group]
    ST --> VM1[API v1 targets]
    CA --> VM2[API v2 targets]
    MON[CloudWatch / logs / traces / business KPIs] -. Monitor .-> ST
    MON -. Monitor .-> CA
    MON --> R{SLOs met?}
    R -->|Yes| INC[Increase canary weight]
    R -->|No| RB[Set canary weight 0 / rollback]
~~~

### 7.2. Blue/Green Deployment

Blue/green maintains two ready environments/target groups. Once green is verified, you can flip traffic with a single forward rule update or ramp weights gradually. The advantage is keeping the blue environment as an immediate rollback path.

Watch out for:

- Backend database/schema migrations must be **bidirectionally compatible** during the transition window; rolling back code cannot undo a breaking schema change.
- Do not treat weight 0 as having **deleted** the old version; targets/compute and associated resources still exist and incur cost.
- If sessions must persist, apply sticky/group consistency or externalize state per application design.
- Routing rules are only part of deployment; you still need health checks, autoscaling, smoke tests, metrics, and rollback.

### 7.3. When to Use Headers Instead of Weights?

**Header routing** works well for testing a new version with an explicit QA group or test-harness requests:

~~~text
Host api.example.com + Header X-Release: canary -> tg-api-v2
Host api.example.com (no header)                -> tg-api-v1
~~~

**Weighted routing** works well for sampling a percentage of general traffic. Both can be combined:

1. High-priority rule for testers sending the header, routing **100% of testers** to canary.
2. Lower-priority rule splitting remaining traffic **99/1** between stable and canary.
3. Default rule handling remaining hosts/paths.

Control priority ordering carefully so testers are not captured first by the general rule. Client-sent headers **are not suitable as security controls**; testers accessing real data must still authenticate at the application layer.

## 8. Designing Verifiable Routing Rules

### 8.1. Complete Architecture Example

An e-commerce system runs three services across two AZs:

- `shop.example.com`: frontend.
- `api.example.com`: stable and canary APIs.
- `admin.example.com`: admin dashboard with independent authentication.

Proposed rule ordering:

| Priority | Condition | Action | Rationale |
|---:|---|---|---|
| 10 | Host `api.example.com` + Header `X-Release: canary` | Forward `tg-api-canary` | Explicit tester/canary routing |
| 20 | Host `api.example.com` + Path `/v2/*` | Forward `tg-api-v2` | Path-based v2 API service |
| 30 | Host `api.example.com` + Path `/v1/*` | Forward 90% `tg-api-stable` + 10% `tg-api-canary` | Small-percentage canary |
| 40 | Host `shop.example.com` + Path `/static/*` | Forward `tg-static` | Static assets |
| 50 | Host `shop.example.com` | Forward `tg-web` | Remaining frontend traffic |
| 60 | Host `admin.example.com` | Authenticate then forward `tg-admin` | Dashboard |
| Default | Unconditional | Fixed response 404 | Reject undeclared hosts/paths |

**This example is not a complete ACL.** You still need valid TLS certificates for all hostnames, security groups, IAM, AWS WAF, and backend authorization. Depending on architecture, CloudFront + S3 may replace a dedicated EC2 target group for static files.

### 8.2. Expected Request Test Matrix

| Request | First Matching Rule | Result |
|---|---|---|
| `Host=api.example.com`, `Path=/v1/orders`, `X-Release=canary` | 10 | `tg-api-canary` |
| `Host=api.example.com`, `Path=/v2/orders`, no header | 20 | `tg-api-v2` |
| `Host=api.example.com`, `Path=/v1/orders`, no header | 30 | Split stable/canary by weight |
| `Host=shop.example.com`, `Path=/static/logo.svg` | 40 | `tg-static` |
| `Host=shop.example.com`, `Path=/cart` | 50 | `tg-web` |
| `Host=admin.example.com`, `Path=/settings` | 60 | Authenticate then route to `tg-admin` |
| `Host=unknown.example.com`, `Path=/anything` | Default | 404 from ALB |

If you also need to route `/v1` **without a trailing slash**, add an appropriate pattern; `/v1/*` does not necessarily match bare `/v1` variants. Test exact path normalization and patterns against your real application.

### 8.3. Distinguishing Routing from URL Rewrite

Routing selects a target group; rewriting alters the host/path before sending to the backend when explicitly configured. For the same request `/api/v1/orders`:

- **Pure routing:** the backend receives `/api/v1/orders`.
- **URL rewrite:** can be configured to transform it to `/v1/orders` via a supported rule transform.

Whenever adding transforms, update test suites to verify headers, paths, HTTP status codes from backends, and logs. Do not enable rewrites simply because backend teams have not agreed on path conventions.

## 9. Lab 1 — Inspecting ALB Configuration with AWS CLI

**This section is read-only**, suitable even if you do not have modify permissions. You need AWS CLI v2, a valid profile, and `elasticloadbalancing:DescribeLoadBalancers`, `DescribeListeners`, `DescribeRules`, `DescribeTargetGroups`, and `DescribeTargetHealth` permissions.

### 9.1. Verify Account and Region

Example using Bash/Linux or AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws configure list --profile "$AWS_PROFILE"
~~~

If using **AWS CloudShell** inside a Console session without an `aws-lab-dev` profile, omit `export AWS_PROFILE` and `--profile` as needed. Confirm the actual account and role before proceeding.

### 9.2. List ALBs and Listeners

~~~bash
REGION=ap-southeast-1

aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --query 'LoadBalancers[].{Name:LoadBalancerName,Type:Type,DNS:DNSName,State:State.Code}' \
  --output table
~~~

Pick an ALB **you are authorized to inspect**, then retrieve its listeners:

~~~bash
ALB_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:loadbalancer/app/aws-lab-alb/0123456789abcdef"

aws elbv2 describe-listeners \
  --load-balancer-arn "$ALB_ARN" \
  --region "$REGION" \
  --query 'Listeners[].{Listener:ListenerArn,Protocol:Protocol,Port:Port}' \
  --output table
~~~

These ARNs are **dummy placeholders** and must be replaced with real sandbox ARNs. A `LoadBalancerNotFound` error typically indicates the wrong ARN, Region, account, or a non-existent resource.

### 9.3. Read Listener Rule Ordering

~~~bash
LISTENER_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/aws-lab-alb/0123456789abcdef/abcdef0123456789"

aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --region "$REGION" \
  --output json
~~~

Note down in order:

1. `Priority`: non-default rules are evaluated from smallest number to largest.
2. `Conditions`: `Field`, `Values`, or `HostHeaderConfig`/`PathPatternConfig`/`HttpHeaderConfig`.
3. `Actions`: `Type`, `TargetGroupArn`, or `ForwardConfig.TargetGroups` and `Weight`.
4. `IsDefault`: fallback rule when no other rule matches.

**Exercise:** From the returned configuration, construct three hypothetical requests: (a) matching host but wrong path; (b) matching host + path without the header; (c) matching all three. Identify the first rule and target group each request hits.

### 9.4. Inspect Target Groups and Health

~~~bash
aws elbv2 describe-target-groups \
  --load-balancer-arn "$ALB_ARN" \
  --region "$REGION" \
  --query 'TargetGroups[].{Name:TargetGroupName,Arn:TargetGroupArn,Protocol:Protocol,Port:Port,Type:TargetType}' \
  --output table
~~~

For a specific target group:

~~~bash
TG_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-stable/1111111111111111"

aws elbv2 describe-target-health \
  --target-group-arn "$TG_ARN" \
  --region "$REGION" \
  --query 'TargetHealthDescriptions[].{Id:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}' \
  --output table
~~~

If targets are not healthy yet, do not route live rollout traffic to that target group. Check **health check path/port/status matcher**, security groups, and connectivity from ALB to targets.

## 10. Lab 2 — Creating Host/Path/Header and Weighted Rules in a Sandbox

> **This is a mutating extension.** Apply it only on **an ALB and target groups dedicated to your lab**, with proper permissions, verified account/Region, and a cleanup plan. ALB, EC2/ECS backends, logs, data transfer, and related components can incur charges. This section is optional if you only have read access.

### 10.1. Prerequisites

Your sandbox needs:

- An ALB attached to at least two suitable AZs with a dedicated lab HTTPS or HTTP listener.
- `tg-stable` and `tg-canary` with healthy targets; backends returning **version-tagged responses** (e.g., JSON `{"version":"stable"}` or `{"version":"canary"}`) so you can verify where requests land.
- Planned listener priorities **currently unused**; verify via `describe-rules`.
- Security groups permitting traffic from your test client to ALB and from ALB to backends within the sandbox.
- `elasticloadbalancing:CreateRule`, `ModifyRule`, `DeleteRule`, and necessary read permissions.

**Never create rules on a production listener** or a listener owned by someone else. Each subsection below shows example JSON; **replace dummy ARNs with real ARNs** before executing.

### 10.2. Create a Header-Based Rule for Testers

Create `conditions-canary.json`:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["api.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/v1/*"]
    }
  },
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

Create `actions-canary.json`:

~~~json
[
  {
    "Type": "forward",
    "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-canary/2222222222222222"
  }
]
~~~

Create priority 10 rule **only when priority 10 is unused on your sandbox listener**:

~~~bash
RULE_CANARY_ARN=$(aws elbv2 create-rule \
  --listener-arn "$LISTENER_ARN" \
  --priority 10 \
  --conditions file://conditions-canary.json \
  --actions file://actions-canary.json \
  --region "$REGION" \
  --query 'Rules[0].RuleArn' \
  --output text)

echo "$RULE_CANARY_ARN"
~~~

This rule matches only when host, path, and header all match. If a tester omits `X-Release: canary`, the request skips this rule and falls through to the next rule or default action.

### 10.3. Create a Weighted Rule for All Other API v1 Requests

Create `conditions-v1.json`:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["api.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/v1/*"]
    }
  }
]
~~~

Create `actions-v1-weighted.json`:

~~~json
[
  {
    "Type": "forward",
    "ForwardConfig": {
      "TargetGroups": [
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-stable/1111111111111111",
          "Weight": 90
        },
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-canary/2222222222222222",
          "Weight": 10
        }
      ],
      "TargetGroupStickinessConfig": {
        "Enabled": false
      }
    }
  }
]
~~~

Create priority 20 weighted rule:

~~~bash
RULE_WEIGHTED_ARN=$(aws elbv2 create-rule \
  --listener-arn "$LISTENER_ARN" \
  --priority 20 \
  --conditions file://conditions-v1.json \
  --actions file://actions-v1-weighted.json \
  --region "$REGION" \
  --query 'Rules[0].RuleArn' \
  --output text)

echo "$RULE_WEIGHTED_ARN"
~~~

Check:

- Priorities 10 and 20 are valid and non-colliding.
- The header rule precedes the weighted rule.
- The weighted rule specifies both target group ARNs and 90/10 weights.
- Target groups have healthy targets in configured AZs.
- Backends handle `/v1/...`, since no URL rewrite is configured in this example.

### 10.4. Test Routing with `curl`

Assuming `api.example.com` resolves to the lab ALB with a valid TLS certificate:

~~~bash
curl -i https://api.example.com/v1/status

curl -i \
  -H "X-Release: canary" \
  https://api.example.com/v1/status
~~~

With the header, responses should come from canary (due to priority 10). Without the header, requests hit **weighted rule priority 20**, so send many requests and inspect responses/metrics to evaluate the 90/10 split.

If you do not have custom DNS yet, you can test a lab-managed **HTTP listener** using the ALB's DNS name with a `Host` header; for **HTTPS**, verify TLS SNI/certificate/hostname compatibility. Never use `curl -k` as a permanent habit to bypass certificate validation; TLS must be validated against real hostnames before production.

To identify which backend served each response, include a test header or JSON field such as `X-App-Version: stable` / `canary` in test backends. Version tags are for observability only, not security.

### 10.5. Verify Configuration After Creation

~~~bash
aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --region "$REGION" \
  --query 'Rules[].{Priority:Priority,RuleArn:RuleArn,Conditions:Conditions,Actions:Actions}' \
  --output json
~~~

If priorities 10/20 are missing or the JSON differs from expectations, investigate AWS CLI errors, ARNs, account, and permissions before sending more requests. Pay attention to target group health and the default rule to avoid shadowed paths.

### 10.6. Clean Up Rules After the Lab

Delete only **the exact rule ARNs you created**:

~~~bash
aws elbv2 delete-rule \
  --rule-arn "$RULE_CANARY_ARN" \
  --region "$REGION"

aws elbv2 delete-rule \
  --rule-arn "$RULE_WEIGHTED_ARN" \
  --region "$REGION"
~~~

**Do not run these commands if the ARN variables are empty or point to someone else's rules.** Save ARNs in your lab notes before closing your terminal; if rule creation failed partway, check which rules actually exist before cleaning up. If you also provisioned dedicated ALBs, target groups, EC2 instances, ECS services, or certificates for the lab, clean them up per approved procedure and check EBS, public IPv4, logs, and data transfer charges.

## 11. Monitoring Rollouts and Resilience

### 11.1. Key Metrics

| Layer | Suggested Metrics | Interpretation |
|---|---|---|
| **ALB listener/target group** | `RequestCount`, `RequestCountPerTarget` | Volume and distribution across pools |
| **Target health** | `HealthyHostCount`, `UnHealthyHostCount` | Do canary/stable have enough targets to serve traffic? |
| **HTTP errors** | `HTTPCode_Target_5XX_Count`, `HTTPCode_ELB_5XX_Count` | Distinguish backend errors from load balancer errors |
| **Latency** | `TargetResponseTime` and app p95/p99 | Detect regressions in the new version |
| **Availability** | Target health, health-check failures, connection errors | Alert when a target group loses readiness |
| **Application** | Business conversions, transaction failures, timeouts, retry rates | Direct user-impact indicators |
| **Cost** | ALB usage, LCU, backend compute, cross-AZ transfer, logs | Evaluate cost per SLO-compliant request |

CloudWatch offers `LoadBalancer` and `TargetGroup` dimensions for many ALB metrics. Filter by exact dimensions when comparing stable vs. canary. Some signals are **target group metrics**, whereas application logs/traces are needed to diagnose detailed errors.

### 11.2. Example Rollback Criteria

Suppose canary receives 10% of traffic for 20 minutes. The organization defines:

- Canary `HealthyHostCount=0` during the check window: **halt rollout, set weight to 0**.
- Canary error rate exceeds baseline by a predefined threshold: evaluate rollback based on statistical significance and user impact.
- Canary p95 latency breaches SLO: hold or reduce weight; inspect CPU, DB, connection pools, and GC.
- Data corruption or incompatible changes detected: execute application/data recovery procedures; lowering weight alone does not revert already-written data.

**Do not copy a fixed error threshold blindly** across every service. Low-traffic endpoints need larger sample windows; payment flows require stricter critical error signals and tighter guardrails.

### 11.3. What Does Auto Scaling Do in This Model?

**Auto Scaling** adds/removes EC2 instances based on demand or scaling policies; **weighted routing** adjusts the share of requests sent to each target group. Both mechanisms should work together:

~~~text
Weighted routing:
  tg-stable 90% | tg-canary 10%
  -> governs request share per group.

Auto Scaling:
  tg-stable attached to stable ASG
  tg-canary attached to canary ASG
  -> governs how many instances serve inside each group.
~~~

If you shift 50% of traffic to canary when it only has one small target, raising the weight can overload it. Before every rollout step, verify **canary capacity**, autoscaling warm-up, health checks, and shared database/dependency headroom.

### 11.4. Multi-AZ and Failure Modes

- Enable ALB in appropriate AZs; target groups should have healthy targets across multiple AZs when high availability is required.
- Health checks only confirm the probed endpoint responds properly; they do not verify every business function.
- A shared dependency such as RDS, Redis, or an external API can still be a **single point of failure** even if target groups span two AZs.
- Test target loss, single-AZ capacity shortages, canary failures, and rollbacks.
- When a rule forwards solely to an empty or completely unhealthy target group, **do not expect weights to fail over automatically** to the remaining group.

## 12. Security and Limitations of Layer 7 Routing

### 12.1. TLS, Host Headers, and `X-Forwarded-For`

ALB can terminate TLS using ACM certificates or supported certificate stores. Ensure:

1. Valid certificates exist for every application domain.
2. HTTPS listeners and TLS policies meet security standards.
3. HTTP redirects to HTTPS when TLS is mandatory.
4. Backends safely consume proxy-added headers like `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Port`.
5. Never blindly trust client-sent headers to determine identity, client IP, or access rights; configure trusted proxies and parse IP chains per application standards.

### 12.2. WAF and Authorization

**AWS WAF** can attach to ALB per service support, enabling request filtering, rate-based rules, and pre-application protections. Still:

- **Routing rules** do not replace WAF, IAM, or application authorization.
- Host/path/header conditions only pick a route; they never bypass backend authentication.
- Admin dashboards require strong identity checks; if stricter privacy is required, consider an **internal ALB** or tighter network controls.
- Combine ALB-level authentication (OIDC/Cognito) when appropriate with role-based enforcement inside the application.

### 12.3. Routing Does Not Guarantee Tenant Isolation

Suppose a frontend sends `X-Tenant-ID: company-A`. Even if ALB routes based on this header to app A, a client can spoof `company-B`. **Tenant isolation requires verifiable identity, resource-level authorization**, and backend data-access enforcement. Never use routing headers as a customer-data security boundary.

## 13. Cost and Quotas When Using Many Rules and Target Groups

### 13.1. Cost

ALB is typically billed by **running hours** plus **Load Balancer Capacity Units (LCU)** consumption under current AWS pricing. Backend EC2/ECS/Lambda compute, data transfer, CloudWatch logs, WAF, DNS, and other services have separate pricing.

| Component | Can Generate Charges | Cost Control |
|---|---|---|
| ALB | ALB uptime hours and LCU usage | Delete unused lab ALBs; measure load and estimate pricing |
| Target compute | EC2/ECS/Lambda or other backends | Auto Scaling, right-sizing, appropriate schedules |
| Logs/metrics | S3 log storage, CloudWatch metrics/logs, tracing | Sensible retention and sampling rates |
| Security | WAF/web ACL rules, request inspection, related services | Enable only needed rules; monitor usage |
| Networking | Data transfer/cross-AZ, NAT, or related components | Design VPC/AZ layout and monitor traffic |

**Never assume weighted routing is free just because adding a rule is cheap**: running an extra backend pool adds compute, EBS, IP, monitoring, and operational costs. Conversely, creating target groups alone does not incur separate hourly per-target-group fees.

### 13.2. Quotas

AWS limits resources such as rules per ALB, target groups, listeners, and conditions/match evaluations per rule. Hitting a quota causes AWS CLI calls to return corresponding limit errors.

Principles:

- Never create a new rule per user or per request; group traffic predictably.
- Establish priority conventions, such as allocating numeric ranges per service to avoid collisions.
- Keep rules clear and auditable; remove rules from retired versions.
- Check **Service Quotas** and current AWS docs before scaling to large rule counts.

## 14. Common Pitfalls

| Symptom | Common Cause | Where to Check |
|---|---|---|
| `/api/internal/*` requests hit the general backend | `/api/*` rule has a higher-precedence (lower) priority | Place specific rules before general rules |
| Right Host, yet ALB returns 404 | No path rule matched; fell into fixed-response default | `describe-rules`; inspect actual Host and path |
| Header routing fails to match | Header name/value differs; proxy strips/alters header; wrong priority | Inspect raw requests, ALB config, and edge proxies |
| Client spoofs canary header | Relying on untrusted headers for access control | Move authorization to identity/backend; lock down edge |
| Weighted 90/10 does not look exact over 20 requests | Small sample size, stickiness, and uneven traffic | Widen observation window; check request counts per target group |
| Canary is unhealthy yet ALB still returns errors | Weighted target groups do not auto-failover | Roll back weight; inspect health and capacity |
| HTTPS fails despite valid Host rule | SNI/certificate or DNS mismatch | Check certificates, TLS listener, and actual domain |
| Backend returns 404 even though ALB picked the right target | Backend does not recognize `/api` prefix | Verify original path and any configured URL rewrite |
| Target health reports unhealthy | Wrong health check path/status/port; SG blocks traffic | `describe-target-health`, network and application logs |
| Cannot create new rule | Duplicate priority, wrong ARN, invalid condition/quota | Check `create-rule` error, quotas, and existing rules |
| Latency spikes after raising canary weight | Canary lacks capacity or shared dependency overloaded | ASG/ECS capacity, CPU, DB, connection pools, traces |
| Stable target group is healthy yet some requests fail | Unhealthy canary group still receives weighted share | Check weights per group, health, and 5xx metrics |
| Data fails to revert on app rollback | Breaking schema/data migration | Use backward-compatible migrations and backup/restore |
| High bill after testing finishes | Lab ALB/EC2/EBS/logging left running | Audit Cost Explorer and resources by Region/tag |

### 14.1. Short Diagnostic Checklist

~~~text
1. Right account, Region, ALB, listener, hostname?
2. Does TLS/DNS/client traffic actually reach the intended ALB?
3. Which rule priority matches first?
4. Do host/path/header conditions match post-proxy/normalization?
5. Are forward/redirect/fixed-response actions and weights right?
6. Does the target group have healthy targets and enough capacity?
7. Is the failure in ALB, backend, IAM/network, WAF, or an app dependency?
8. Are rollback and post-lab resource cleanup in place?
~~~

## 15. Real-World Scenario and Evaluation Exercises

### 15.1. Problem Statement

An online learning platform on AWS has:

- `learn.example.com`: student frontend.
- `api.example.com`: content and progress API.
- `teacher.example.com`: instructor portal.
- An upcoming **API v2** release not yet ready for 100% of traffic.
- API v1 and v2 running on two EC2 Auto Scaling groups across two AZs; business state stored outside EC2.
- Requirements to control p99 latency, 5xx errors, cost, and recovery if the new version fails.

Design the listener rules and deployment workflow.

**One reference solution:**

| Rule | Priority | Conditions | Action |
|---|---:|---|---|
| Canary test | 10 | `Host=api.example.com` + `X-Release=canary` | 100% to `tg-api-v2` |
| Public API | 20 | `Host=api.example.com` + `Path=/v1/*` | Stable 95%, canary 5% |
| Teacher portal | 30 | `Host=teacher.example.com` | Appropriate auth + `tg-teacher` |
| Student frontend | 40 | `Host=learn.example.com` | `tg-frontend` |
| Default | - | Unmatched | 404 |

Alongside listener rules, include:

- Valid ALB HTTPS certificates and DNS records.
- Least-privilege security groups and IAM roles.
- Target group health checks, per-version Auto Scaling, and instance replacement.
- Dashboards per target group/version; criteria to advance, pause, or roll back.
- Compatible database migrations while both versions run concurrently.
- AWS WAF/application authorization; canary header used strictly for version selection.
- Cost Explorer/AWS Budgets for ALB and backends, plus a test-environment teardown plan.

### 15.2. Review Questions

1. Why should `Host=api.example.com` not precede `Host=api.example.com` + `X-Release=canary`?
2. If a request matches the host but path `/v1` does not match `/v1/*`, what does ALB do?
3. Do priorities 10/20 interact with weights 90/10?
4. For a rule with both Host and Header conditions, which conditions must pass for the rule to match?
5. If canary has weight 10 but the canary target group is empty or unhealthy, does ALB automatically shift that 10% to stable?
6. Can a browser-sent header replace authentication for the teacher portal?
7. When increasing canary from 5% to 50%, what capacity and SLO metrics must be checked first?
8. If the backend receives `/api/users` while only defining route `/users`, where is the mismatch?
9. Can you declare success if the first 10 requests hit stable and 1 hits canary?
10. How do you ensure fast code rollback while handling database schema migrations?
11. How do ALB routing and EC2 Auto Scaling solve two different problems?
12. When using one ALB for multiple subdomains, do you need matching TLS certificates and DNS for each hostname?

### 15.3. Suggested Answers

1. The broader rule would match first, preventing the header rule from ever being evaluated.
2. ALB evaluates subsequent rules and falls through to the default action if none match.
3. Priority controls **which rule is evaluated first**; weight controls **traffic proportions across target groups within a single action**.
4. Both Host and Header must match, because rules combine conditions with AND logic.
5. No; weighted routing does not automatically fail over between target groups like that.
6. No; clients can forge headers, so authorization must rely on verified identity and permissions.
7. Healthy targets, request count, error rate, `TargetResponseTime`/p95/p99, DB capacity, and business metrics.
8. Path routing does not strip prefixes automatically; the backend must support the prefix or a URL rewrite transform must be configured.
9. No; the sample size is far too small to judge distribution or quality.
10. Use backward-compatible schemas, phased migrations, backups/restores, and a recovery plan.
11. Routing selects **the request's destination**, whereas Auto Scaling adjusts **the number of serving targets**.
12. Yes; domain ownership, DNS, and certificates/SNI must be verified for HTTPS paths.

## 16. Lesson Completion Checklist

Before promoting routing configurations to a shared environment:

- [ ] Diagrammed the ALB, listeners, rule priorities, target groups, and AZs.
- [ ] Tested Host/Path/Header conditions with both matching and non-matching sample requests.
- [ ] Ordered specific rules before general rules with no priority collisions.
- [ ] Verified path forwarding matches backend expectations; tested transforms if rewriting URLs.
- [ ] Verified hostnames, DNS, TLS certificates/SNI, and HTTP→HTTPS redirects.
- [ ] Ensured client-sent headers are never used in place of authentication/authorization.
- [ ] Verified both target groups in weighted forwards have accurate ARNs, weights, and healthy targets.
- [ ] Built dashboards comparing stable vs. canary on error rate, latency, and business metrics.
- [ ] Defined rollback criteria without relying on weighted target-group auto-failover.
- [ ] Confirmed canary capacity and Auto Scaling configuration match projected load.
- [ ] Evaluated multi-AZ redundancy, durable storage, and database compatibility.
- [ ] Aligned IAM permissions, security groups, and AWS WAF with traffic flows.
- [ ] Budgeted ALB/LCU, backend, and log costs; documented lab cleanup instructions.

**Expected outcome:** learners can classify requests by Host/Path/Header, predict the first matching listener rule, explain weighted forwarding, and design data-driven rollouts. With that foundation, they can deploy safely, monitor errors, recover from canary failures, and prevent test resources from generating uncontrolled costs.

## Official AWS Documentation

- [Application Load Balancer listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-rules.html)
- [Condition types for listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/rule-condition-types.html)
- [Action types for listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/rule-action-types.html)
- [Add a listener rule](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/add-rule.html)
- [Target groups for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html)
- [Health checks for ALB target groups](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [AWS CLI elbv2 create-rule](https://docs.aws.amazon.com/cli/latest/reference/elbv2/create-rule.html)
- [Monitor Application Load Balancers using CloudWatch](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [Elastic Load Balancing quotas](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-limits.html)
- [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)
- [EC2 Auto Scaling documentation](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)

> **Usage note:** The domain `example.com`, account ARN `111122223333`, target groups, and paths in this lesson are training examples. AWS may update quotas, syntax, and rule/transform capabilities by Region and service version. Before modifying production listeners, consult current AWS documentation, test in a sandbox, and prepare an approved rollback plan.
