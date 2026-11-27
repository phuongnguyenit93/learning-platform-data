# Cloud Armor with Load Balancers at the Edge

A Java API serves customers via `api.example.com`, running on Cloud Run or GKE and exposed through an External Application Load Balancer. During peak hours, the system receives a surge of anomalous HTTP requests to `/login`; some carry SQL injection payloads, while others originate from networks with a history of abuse. If all that traffic passes straight to the application, CPU, connection pools, databases, and autoscaling costs can suffer before the team even identifies the root cause.

**Google Cloud Armor** applies traffic protection rules on Google's infrastructure before requests reach load-balanced backends. Combining Cloud Armor with **Cloud Load Balancing** creates an edge control layer for web applications: receiving requests via a managed frontend, selecting backends via routing, evaluating security policies, and forwarding only eligible requests to services. Cloud Armor supports filtering by IP, country, HTTP attributes, WAF rules, and rate limiting; specific capabilities depend on policy type, load balancer, and service tier.

This lesson belongs to the **Load Balancing and Content Delivery** chapter of the **CLOUD_PROVIDERS_GCP** module. Cloud Armor builds on project organization, IAM, and VPCs, extending into operational scenarios across Compute Engine, GKE, Cloud Run, Cloud Storage, release automation, reliability observability, and cost control.

After this lesson, you will be able to:

- Explain where Cloud Armor sits in the path of an HTTP(S) request through a load balancer.
- Distinguish **backend security policy**, **edge security policy**, and **network edge security policy**.
- Design rules with priorities, default allow/deny, preview mode, WAF, and rate limiting.
- Attach policies to the right backend service or backend bucket, accounting for Cloud CDN caching effects.
- Deploy policies via Console, `gcloud`, and Infrastructure as Code.
- Block direct backend bypass paths, inspect logs, and test changes before enforcing.
- Identify protection boundaries, costs, and common configuration mistakes.

## 1. Why Does Cloud Armor Commonly Pair with a Load Balancer?

An External Application Load Balancer is a Layer 7 HTTP(S) load balancer. The frontend accepts traffic at an IP/port, handles TLS per configuration, the URL map selects a backend service or backend bucket, and proxy infrastructure forwards requests to the appropriate backend. Cloud Armor applies a security policy to the **protected target** along that path, filtering requests before they consume application resources.

~~~mermaid
flowchart LR
    A["Internet Client"] --> B["Cloud DNS / Frontend IP + TLS"]
    B --> C["External Application Load Balancer"]
    C --> D["URL map → Backend service"]
    D --> E["Cloud Armor security policy"]
    E -- "Allow" --> F["Cloud Run / GKE / Compute Engine"]
    E -- "Deny / Rate-limit" --> G["HTTP 403 / 429 / other action"]
    F --> H["Database / Storage / dependencies"]
~~~

This is a **conceptual diagram** omitting Cloud CDN. Actual evaluation placement and order vary by load balancer type, edge/backend policy, CDN, and IAP. One frontend can route to multiple backend services; **policies must be attached to the exact backend resources receiving requests**, not merely configured on a frontend IP or DNS.

| Component | Role | What It Cannot Solve Alone |
|---|---|---|
| **Cloud DNS** | Points domain name to frontend IP | Does not filter HTTP or block SQL injection |
| **External Application Load Balancer** | Handles HTTP(S), TLS, routing, and backend distribution | Does not replace full custom WAF rulesets |
| **Cloud Armor** | Evaluates requests against security policies, filters/rate-limits on Google infrastructure | Does not patch application bugs or replace authentication |
| **Cloud CDN** | Caches eligible content and offloads origin | Does not enforce access rules for private data |
| **VPC firewall / ingress control** | Restricts network paths to backends | Does not inspect full HTTP payloads like a WAF |
| **IAM / IAP / app auth** | Verifies identity and authorization | Does not replace edge traffic flood mitigation |

The architectural benefit is shedding unwanted requests before they hit backends, protecting availability and centralizing shared rules. However, **Cloud Armor only inspects traffic traversing the paths and resources where the policy actually applies**. If users can reach a backend endpoint directly without going through the load balancer, they bypass this policy layer.

## 2. Choosing the Right Cloud Armor Security Policy Type

The phrase "at the edge" can be misleading because Cloud Armor has multiple policy types. Choose based on **frontend type**, **attachment point**, and **supported attributes**.

| Policy Type | Where Attached? | Primary Use Case | Scope and Notes |
|---|---|---|---|
| **Backend security policy** (`CLOUD_ARMOR`) | Backend service | WAF, HTTP/IP conditions, rate limiting to protect apps | Supports many Application Load Balancers and some proxy Network Load Balancers; features depend on frontend |
| **Edge security policy** (`CLOUD_ARMOR_EDGE`) | Backend service or backend bucket of supported frontends | Filters requests before Cloud CDN cache, protecting cache hits too | Used with global external or classic Application Load Balancers; narrower attribute set than backend policies |
| **Regional backend security policy** | Regional backend service | Apps using regional external or regional internal Application Load Balancers | Created/attached per region; do not assume all global features apply identically |
| **Network edge security policy** (`CLOUD_ARMOR_NETWORK`) | Supported network-level resources | Network edge defense for passthrough Network Load Balancers, protocol forwarding, or VM external IPs | Operates at network layer; not an HTTP WAF in the same way |

**In this lesson**, the main focus is **global external Application Load Balancer** with backend security policies, plus edge security policies when Cloud CDN is present. Cloud Armor supports other load balancer types as well, but always consult the feature compatibility matrix for your exact frontend and security policy type before using them.

### Which Policies Can a Backend Service Attach?

- A global external Application Load Balancer backend service can use a **backend policy**, an **edge policy**, or both per supported features.
- If a backend service is referenced by multiple URL maps/routes, requests reaching that service are governed by the policy attached to it.
- **Backend buckets** (e.g., Cloud Storage served via load balancer/Cloud CDN) support **edge security policies only**, not standard backend security policies.
- A backend service accepts **at most one policy of each type** attached directly at the service level; to enforce more checks, add rules inside the policy or evaluate supported hierarchical policies.
- With **GKE Ingress**, controller reconciliation can overwrite manual edits on backend services. Use the controller's declarative resource, such as `BackendConfig` for GKE Ingress, to avoid drift.

**Do not equate every Cloud Armor policy with a WAF:** network edge policies and edge policies do not support the full HTTP/WAF content inspection language of backend policies.

## 3. Cloud Armor and Cloud CDN: Where Are Cache Hits Protected?

When a backend service enables Cloud CDN, static content can be served from Google's caches. **Backend security policies** apply to requests routed to the backend after a cache lookup—such as cache misses or uncached requests. To inspect requests served directly from cache as well, use an **edge security policy** on supported frontends.

~~~mermaid
flowchart TD
    A["HTTP(S) Client"] --> B["Global / Classic Application LB"]
    B --> C{"Edge security policy"}
    C -- "Deny" --> X["Denied at the edge"]
    C -- "Allow" --> D{"Cloud CDN cache"}
    D -- "Hit" --> E["Serve cached content"]
    D -- "Miss or bypass" --> F{"Backend security policy"}
    F -- "Deny" --> X
    F -- "Allow" --> G["Backend service / origin"]
    G --> H["Response / cache if eligible"]
~~~

Key points to remember:

1. **Edge policies filter before the cache**, so they can block requests even when content is already cached.
2. **Backend policies protect the path to the origin**; with Cloud CDN, do not assume a backend policy inspects every cache hit.
3. **Backend buckets attach only edge policies.** If dynamic apps need rich WAF logic, design an appropriate backend service and policy.
4. **Caching is not a protection mechanism for sensitive data.** Carefully audit `Cache-Control`, cookies, authorization, and cross-client data exposure risks.

For example, if a site caches `/assets/app.js` in Cloud CDN while `/api/orders` is dynamic, you can enforce basic IP filtering across all requests in an edge policy, and detailed WAF/rate limiting on the API backend service. If the URL map routes `/api/orders` to another backend, attach the policy **to that API backend service**.

## 4. Structure of a Security Policy

A security policy contains **rules**. Each rule has:

- **Priority:** an integer; the **smaller** the number, the **earlier** it is evaluated.
- **Match:** condition such as IP/CIDR, region, path, headers, or WAF expression, depending on policy type.
- **Action:** `allow`, `deny-403`, `deny-404`, `deny-502`, `throttle`, `rate-based-ban`, or other supported actions.
- **Preview:** logs what the rule would match without enforcing its blocking action yet.
- **Description:** operational purpose and justification for review.

Standard rules use unique priorities from `0` to `2147483646`. Every policy has a **default rule** at `2147483647`, evaluated when no earlier rule matches. The default rule can be `allow` or `deny` by design.

### Example Evaluation Order

| Priority | Condition | Action | Purpose |
|---:|---|---|---|
| 100 | IP in verified blocklist | `deny-403` | Block abusive sources |
| 500 | Selected SQL injection WAF rule | `deny-403` (initially Preview) | Detect suspicious payloads |
| 900 | Requests to `/login` exceeding per-IP threshold | `throttle` | Slow down brute-force attempts |
| 2000 | IP in corporate range, if explicit precedence needed | `allow` | Allow per business requirements |
| 2147483647 | All unmatched traffic | `allow` or `deny` | Default behavior |

**Note:** a low-priority-number `allow` rule stops evaluation early and skips higher-numbered WAF/deny rules. Therefore, never place a broad "allowlist" ahead of all other controls without evaluating the consequences. When a WAF rule is in **Preview**, evaluation continues through subsequent rules to produce the live enforced outcome.

Choosing a strategy:

**Default allow** suits public websites with a broad legitimate audience: block known bad patterns, throttle, and monitor false positives. **Default deny** suits apps open only to known sources (such as a partner-only portal), placing exact allowlists at higher precedence (lower priority numbers) than default deny. Never apply default deny to a public API without validating all real client IP ranges.

## 5. WAF: Detecting Attack Patterns in Requests

Cloud Armor's **Web Application Firewall (WAF)** supports **preconfigured WAF rules** built on widely used signature sets for web application risk categories (such as SQL injection and cross-site scripting). From an implementation standpoint, a rule can use an expression like:

~~~text
evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})
~~~

This example selects an SQL injection signature set and sensitivity level. Signature set names, versions, and sensitivity levels must be verified against current documentation before production rollout. Applications passing special characters or complex JSON parameters can trigger false positives.

Alongside preconfigured WAF rules, **custom rules** can evaluate expressions using supported attributes:

~~~text
# Illustrative Cloud Armor CEL expressions:
request.path.startsWith('/admin')

origin.region_code == 'VN'

inIpRange(origin.ip, '203.0.113.0/24')

request.path.startsWith('/login') &&
request.method == 'POST'
~~~

Each expression is an **independent example**, not a complete policy. The IP comes from documentation range `203.0.113.0/24`; region code `VN` is illustrative only. **Geo-blocking** can disrupt VPN users, traveling customers, or proxied browsers; it is not an identity control.

### Tuning WAF Properly

1. Enable new rules in **Preview** mode while maintaining adequate logging.
2. Exercise legitimate traffic from browsers, mobile apps, webhooks, and internal clients; in test environments, also run controlled test payloads.
3. Review matched rules/subsignatures, URLs, request paths, clients, and false-positive rates.
4. Tune sensitivity levels, specific signature exclusions (`opt-out`), or approved match conditions.
5. Once results meet expectations, disable Preview to enforce on schedule and continue monitoring.

Cloud Armor **does not inspect the entire request body in every scenario**. WAF inspection has body-size limits (configurable within supported bounds, e.g., 8–64 KiB depending on mechanism) and content-type parsing rules; body bytes beyond the limit may go uninspected. For WebSockets, Cloud Armor evaluates the initial HTTP upgrade request, not every subsequent WebSocket frame.

A WAF reduces risk—it **does not replace** input validation, parameterized queries, output encoding, authentication, authorization, patching, and in-app rate limiting.

## 6. Rate Limiting: Mitigating Request Floods and API Abuse

Cloud Armor supports rate-limiting actions:

| Mechanism | How It Works | When to Use |
|---|---|---|
| **Throttle** | If requests exceed the threshold in a time window, excess requests receive `exceed-action` | Login endpoints, public APIs, traffic bursts |
| **Rate-based ban** | Temporarily bans a client for a configured duration after hitting thresholds/rules | Persistent offenders or sustained attacks |

Thresholds are tracked by a **key**, such as client IP, HTTP header/cookie, or other supported attributes. Rate limiting in Cloud Armor is enforced per attached backend service; sharing the same policy across two backends **does not mean** they share a single combined counter across both services.

### Design Example for `/login`

A public app has a login endpoint vulnerable to credential stuffing. Operations sets an experimental threshold of **100 requests per 60 seconds per IP**, returning HTTP 429 when exceeded.

This is an **illustrative threshold**, not a universal recommendation. Users behind shared NATs, schools, or corporate offices share one IP and can suffer collateral blocks; conversely, botnets distributed across many IPs can evade per-IP caps. Measure legitimate traffic, IP distribution, login frequency, and false positives before enforcing.

Cloud Armor absorbs request pressure at the edge. Applications still need per-account lockouts/cooldowns, session protection, credential-stuffing defenses, fraud monitoring, and business quota limits, since IP-based controls alone are insufficient.

## 7. Prerequisites for Deploying a Policy to a Load Balancer

For the hands-on lab, assume the following already exist:

- A working **global external Application Load Balancer** with an HTTPS frontend.
- A URL map routing `api.example.com` to a **backend service** named `api-backend`.
- The backend service serving Cloud Run via a serverless NEG, or VMs/GKE via a supported backend type.
- Compute Engine API enabled, active billing, and appropriate operator permissions.
- Sample access logs and an owner team ready to roll back if rules impact valid traffic.

**You do not need to create an extra load balancer just to use Cloud Armor** if the current architecture already uses a supported frontend/backend. Conversely, creating a Cloud Armor policy alone will not protect a direct Cloud Run URL: traffic must route through the load balancer with bypass paths closed.

### Required IAM Permissions

Managing security policies and attaching policies to backend services are two distinct operations:

| Task | Reference Permissions / Roles |
|---|---|
| Create/edit/delete policies and rules | `roles/compute.securityAdmin` or custom role with appropriate `compute.securityPolicies.*` |
| Attach policy to backend service | Permission to use policy and update backend service, often in `roles/compute.networkAdmin` depending on scope |
| View load balancer logs | Appropriate Cloud Logging/Monitoring read permissions |
| Modify backend, URL map, or frontend configs | Corresponding load balancing admin roles, separated from WAF editing where feasible |

Assign IAM via Google Groups and dedicated CI/CD service accounts. Watch out for IAM inheritance from Organization/Folder levels, as removing a local project binding may not revoke effective access if a broader parent binding exists.

## 8. Creating a Backend Security Policy and Rules with gcloud

The commands below are **educational examples** using placeholder names; executing them in a real project can incur charges or affect production traffic. Run only after verifying the project, backend service, blast radius, and IAM permissions.

~~~bash
PROJECT_ID="demo-security-project"
POLICY="api-armor-policy"
BACKEND="api-backend"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

# 1. Create a global backend security policy.
gcloud compute security-policies create "$POLICY" \
  --type=CLOUD_ARMOR \
  --description="Protect API backend"

# 2. Example blocking an illustrative IP range, initially in Preview mode.
gcloud compute security-policies rules create 100 \
  --security-policy="$POLICY" \
  --src-ip-ranges="203.0.113.0/24" \
  --action=deny-403 \
  --description="Example denylist in preview" \
  --preview

# 3. Add SQL injection WAF rule with initial sensitivity.
gcloud compute security-policies rules create 500 \
  --security-policy="$POLICY" \
  --expression="evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})" \
  --action=deny-403 \
  --description="SQLi detection in preview" \
  --preview

# 4. Attach the policy to the right global backend service.
gcloud compute backend-services update "$BACKEND" \
  --global \
  --security-policy="$POLICY"

# 5. Re-read configuration.
gcloud compute security-policies describe "$POLICY"
gcloud compute security-policies rules list --security-policy="$POLICY"
gcloud compute backend-services describe "$BACKEND" --global
~~~

`rules create` fails if a rule already exists at that priority. Before modifying production, inspect which policy and backend service are currently active; the backend may already attach an existing policy that should be updated rather than replaced.

**Preview applies only to rules marked Preview.** Other enforced rules and the policy remain active; the default rule and other deny rules continue blocking matching traffic. Inspect the entire policy and logs rather than assuming "enabling Preview" on one rule disables all blocking.

### Adding Rate Limiting for the API

An independent example applying an illustrative threshold to `/login` requests on the backend service:

~~~bash
gcloud compute security-policies rules create 900 \
  --security-policy="$POLICY" \
  --expression="request.path.startsWith('/login')" \
  --action=throttle \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 \
  --conform-action=allow \
  --exceed-action=deny-429 \
  --enforce-on-key=IP \
  --description="Preview login rate limit" \
  --preview
~~~

Priority ordering directly matters: if a request is already blocked by rule 100, it never reaches rule 900. If an `allow` rule at 200 matches and terminates evaluation, the throttle rule at 900 may not apply to that request. Monitor both enforced and preview decisions in logs to verify impact.

### Disabling Preview After Evaluation

~~~bash
# Apply only after verifying impact and preparing a rollback plan.
gcloud compute security-policies rules update 500 \
  --security-policy="$POLICY" \
  --no-preview
~~~

Once enforced, Cloud Armor can return `403` for WAF-matching requests. Inspect live traffic and logs right after the change. If false positives impact users, switch the rule back to Preview or add reviewed tuning/exclusions; avoid hastily deleting the entire policy.

## 9. Adding an Edge Security Policy with Cloud CDN

Suppose a website uses Cloud CDN with a backend service named `static-backend`. To filter before the cache, create a separate **edge security policy**:

~~~bash
EDGE_POLICY="public-edge-policy"
STATIC_BACKEND="static-backend"

gcloud compute security-policies create "$EDGE_POLICY" \
  --type=CLOUD_ARMOR_EDGE \
  --description="Basic filtering before CDN cache"

# Illustrative rule, not yet enforced.
gcloud compute security-policies rules create 100 \
  --security-policy="$EDGE_POLICY" \
  --src-ip-ranges="198.51.100.0/24" \
  --action=deny-403 \
  --preview

# Apply edge policy to the global load balancer's backend service.
gcloud compute backend-services update "$STATIC_BACKEND" \
  --global \
  --edge-security-policy="$EDGE_POLICY"
~~~

For a **backend bucket** serving Cloud Storage content, attach the edge policy to the backend bucket via Console/API or `backend-buckets` commands—**never run `backend-services` commands for a backend bucket**. Edge policies support only the feature subset available to edge policy types; never mechanically copy every WAF/rate-limit rule from a backend policy into an edge policy.

When a backend service has both an edge and a backend policy:

1. Requests **denied by the edge policy** are served neither from cache nor from origin.
2. Requests passing the edge policy that result in a **cache hit** are served immediately without reaching the backend policy.
3. **Cache miss/bypass** requests are evaluated by the backend policy before reaching the origin.

In systems with per-user private content, verify caching and authentication configs independently. Cloud Armor does not automatically prevent a mis-cached personalized response from leaking to other users.

## 10. Ensuring Backends Cannot Bypass Cloud Armor

Cloud Armor protects traffic **flowing through the load balancer and policy-attached backend**. If clients have another URL or IP reaching the backend directly, that protection layer is bypassed.

### Compute Engine and GKE

For VM backends, configure **VPC firewalls** so only Google-documented proxy and health check source ranges can reach the application port. If VMs still have external IPs with open application ports, attackers can hit the VMs directly without passing through the Cloud Armor-protected frontend.

For GKE, review Ingress controllers, Network Endpoint Groups, firewalls, and `BackendConfig` resources. If the workload exposes an additional Ingress, `LoadBalancer` Service, or public endpoint, audit them so all application entry paths traverse the intended control layer.

### Cloud Run and Serverless NEGs

Cloud Run services typically have a `*.run.app` URL. When fronting with an external Application Load Balancer and serverless NEG, users can bypass Cloud Armor if the direct URL still permits public access.

For services intended to accept Internet traffic exclusively through the external Application Load Balancer, consider setting ingress to:

~~~bash
# Illustrative setting for Cloud Run behind a valid external Application LB.
gcloud run services update orders-api \
  --region="asia-southeast1" \
  --ingress=internal-and-cloud-load-balancing
~~~

Depending on architecture, certain requests classified as internal may still reach the service under Cloud Run's ingress rules. Therefore, also verify `roles/run.invoker` IAM bindings, ingress settings, internal callers, and secondary endpoints. **Path restriction** and **application authentication/authorization** complement the WAF.

### Identity-Aware Proxy and Private Applications

IAP verifies **user identity**, whereas Cloud Armor evaluates **request/traffic attributes**. On a global external Application Load Balancer, Cloud Armor is evaluated before IAP per supported flow; behavior on a classic Application Load Balancer can differ. During design, check the exact evaluation order to explain 403s, login redirects, and request logs.

Cloud Armor does not replace IAM, IAP, OAuth, sessions, and business authorization. For example, a request may be valid HTTP and pass the WAF while the caller lacks permission to view an order: the application must still return 401/403 per business logic.

## 11. Managing Policies Alongside Infrastructure with Terraform

Across dev, staging, and production environments, store policies as Infrastructure as Code for review, validation, and auditable rollbacks. Minimal Terraform example declaring **only a backend security policy**:

~~~hcl
resource "google_compute_security_policy" "api" {
  name        = "api-armor-policy"
  description = "Protect the public API backend"
  type        = "CLOUD_ARMOR"

  rule {
    priority    = 500
    action      = "deny(403)"
    description = "SQLi signatures, preview first"
    preview     = true

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Default allow"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
~~~

This snippet needs a real provider, project, and CI/CD workflow; **attaching to the backend service** must be declared on the backend service resource (`security_policy` or supported attribute). Never assume a policy is protecting an app merely because Terraform created the policy resource.

A practical rule release workflow:

~~~text
Threat / incident / change request
    ↓
Pull request updating policy or rule
    ↓
Linter + review expressions, priority, expected impact
    ↓
Terraform plan (inspect policy + attachment)
    ↓
Apply in dev/staging or Preview in production
    ↓
Analyze logs / false positives / affected clients
    ↓
Approve enforcement and continue monitoring
~~~

**Managing drift:** if a GKE Ingress policy is managed by `BackendConfig`, editing the backend service directly with Terraform or `gcloud` can be overwritten by the controller. Establish a clear "source of truth" for attachments before making changes; avoid Terraform, Ingress controllers, and manual Console clicks competing over the same attribute.

## 12. Observing Cloud Armor Decisions

A sound policy needs evidence showing it is **evaluated on the right requests**. Cloud Armor uses the load balancer's logging infrastructure for per-request logging. On many backend services, **request logging may not be enabled by default**; enable logging on the target backend service and pick an appropriate sample rate.

### Enabling Logging on a Backend Service

~~~bash
gcloud compute backend-services update "$BACKEND" \
  --global \
  --enable-logging \
  --logging-sample-rate=1.0
~~~

This example uses sample rate 1.0 during tuning analysis. Under heavy traffic, weigh logging costs/volume and adjust intentionally. Log formats, field names, and support vary by load balancer type.

### Finding Blocked Requests in Logs Explorer

~~~text
resource.type="http_load_balancer"
jsonPayload.enforcedSecurityPolicy.outcome="DENY"
~~~

Or filter by:

~~~text
resource.type="http_load_balancer"
jsonPayload.statusDetails="denied_by_security_policy"
~~~

These are example filters. Results depend on LB type, sampling, timeframe, frontend project, and log schema. With cross-project frontend/backend references, logs may reside in the **project hosting the frontend/URL map**; the backend team needs appropriate log-viewer permissions.

Useful fields in request logs:

- `enforcedSecurityPolicy`: the policy and rule that actually decided the outcome when present.
- `previewSecurityPolicy`: the Preview rule that matched without blocking the request.
- Priority, action, outcome, and `statusDetails`: explain why a request was denied.
- Client IP/region, URI path, response code, latency: compare against legitimate traffic.

**Cloud Logging does not automatically capture every request** if sampling is low, backend logging is disabled, or requests bypassed the protected path. Preview rules also incur evaluation/pricing per service pricing terms, so do not leave unused Preview rules running indefinitely without an observability goal.

### Metrics and Alerts

Recommended telemetry to monitor:

| Metric | What to Look For |
|---|---|
| Denied/throttled request rate by policy/rule | Is a rule blocking too many legitimate users? |
| HTTP 403 and 429 by endpoint | Surge caused by attack, rule change, or misbehaving client? |
| Backend HTTP 5xx / error rate | Is attack traffic leaking through and hurting availability? |
| Request count by IP, region, URL | Traffic spikes or repetitive bot activity |
| Latency and backend utilization | Are load balancer, Cloud Run, or GKE overloaded? |
| Preview matches for new rules | How many requests will a staged rule affect once enforced? |
| Load balancing, Armor, and logging costs | Is attack traffic inflating the budget? |

When diagnosing WAF false positives, you can temporarily enable **verbose logging** for detailed signature match info, while weighing payload privacy risks and cost. Restrict log-read access and disable verbose logging once tuning completes.

## 13. Safe Rule Release and Rollback Process

The most common beginner mistake is turning on WAF blocking across everything without measuring legitimate traffic first, causing legitimate API requests to receive 403s.

Step-by-step workflow:

1. **Define the goal:** block specific CIDRs, mitigate HTTP floods, protect `/login`, or detect SQLi/XSS signatures?
2. **Pick the exact backend service:** trace from frontend/URL map to the route receiving live traffic; check if another policy is already attached.
3. **Choose match and priority:** evaluate overlaps across allowlists, WAF rules, rate limits, and the default rule.
4. **Enable Preview:** preserve user experience while observing how the new rule behaves.
5. **Collect representative logs:** cover mobile apps, webhooks, API clients, NAT/proxied customers, partners, and peak traffic windows.
6. **Reduce false positives:** refine expressions, tune WAF sensitivity/exclusions, or adjust rate-limit thresholds.
7. **Enforce with control:** communicate change window, owner, rollback criteria, and dashboards; start with a narrower scope if tooling allows.
8. **Observe post-release:** compare HTTP 403/429, 5xx, business metrics, latency, and support reports.
9. **Rollback:** revert the rule to Preview or the previous verified configuration, then analyze root cause. Do not delete the entire protection layer when only one rule misbehaved.

During fast-moving traffic spikes, operators may need emergency rules. Still record who changed what, why, expiration/review date, and conduct post-incident cleanup so a temporary CIDR block does not permanently lock out legitimate customers.

## 14. Limitations and Complementary Defense Layers

| Problem | How Cloud Armor Helps | What Else Is Needed |
|---|---|---|
| L7 HTTP flood through load balancer | Throttle, rate-based ban, WAF, or supported DDoS protections | Autoscaling, timeouts, circuit breakers, load testing |
| SQL injection / XSS payloads | WAF rule signatures, custom CEL | Parameterized queries, input/output validation, security testing |
| Credential stuffing | Rate limiting, bot defense depending on tier | MFA, account-level rate limits, behavioral detection, strong auth |
| Direct backend calls | Does not protect traffic bypassing LB | VM firewalls, Cloud Run ingress, closing secondary endpoints |
| Data exposure from broken API authorization | Insufficient; requests can be valid HTTP | IAM, IAP, OAuth, business authorization |
| Personal data cached improperly | Does not fix misconfigured caching | `Cache-Control`, auth-aware caching, CDN testing |
| Attacks inside open WebSocket sessions | Can inspect initial HTTP upgrade request | App-level auth and per-frame validation |
| Backend/network outage | Does not fix infrastructure failures | Multi-zone/region, health checks, failover, SLOs, and runbooks |

Cloud Armor fits **defense in depth**: one protective layer along load-balanced request paths, working alongside identity/auth, networking, application security, and backend operations.

## 15. Cost and Service Tier Selection

Evaluate costs across the entire path: frontends/forwarding rules, load balancing data processing, Cloud CDN/cache egress if enabled, Cloud Armor policies/rules/requests, Cloud Logging, and backend compute. Cloud Armor offers **Standard** and **Enterprise** tiers; pricing and features depend on usage model, policy type, subscription tier, and traffic volume. Rules running in Preview can also incur charges.

Before deploying:

- Verify features and endpoint types supported under your actual service tier.
- Consult **Cloud Armor pricing** and **Load Balancing pricing** for the relevant region/network tier instead of assuming one flat rate across all backends.
- Estimate backend service count, policy/rule count, and request volumes during normal hours and attack surges.
- Watch Cloud Logging costs when enabling high sample rates and verbose logging.
- Configure Cloud Billing budgets/alerts per project, remembering **budget alerts do not cut off traffic or cap charges automatically**.

Filtering bad traffic before backends can save CPU and autoscaling, yet Cloud Armor does not automatically reduce the total bill: policy, request evaluation, and logging fees must still be budgeted.

## 16. Real-World Scenario: E-Commerce Website and Java API

Suppose an enterprise runs:

~~~text
Cloud DNS: shop.example.com → global external Application LB
  |
  +-- /assets/* → static-backend (Cloud CDN cache)
  |                  └── Cloud Armor EDGE policy
  |
  +-- /api/* → api-backend → Cloud Run (Java)
  |             └── Cloud Armor BACKEND policy
  |
  +-- /admin/* → admin-backend → GKE
                └── Backend policy + IAP / app authentication
~~~

**Proposed Design:**

| Component | Rules / Solution | Goal |
|---|---|---|
| `static-backend` | Edge policy filtering abusive sources, Cloud CDN cache | Protect cache hits and offload origin |
| `api-backend` | SQLi/XSS WAF Preview then enforce; throttle `/login` | Protect APIs and mitigate floods |
| `admin-backend` | Appropriate IP rules, IAP, or strict auth | Minimize admin attack surface |
| Cloud Run origin | `internal-and-cloud-load-balancing` ingress if suitable | Restrict direct `run.app` calls from Internet |
| GKE origin | Ingress controller/`BackendConfig` + proper firewalls & IAM | Prevent bypasses and config overwrites |
| Platform SRE | Cloud Logging/Monitoring, alerts, and runbooks | Incident detection and rollback |
| Secure CI/CD | Terraform + peer review + scoped IAM | Auditable change governance |

**Incident scenario:** traffic to `/api/login` surges many times over; several IPs cross thresholds while SQLi payloads appear. The team inspects Preview logs, calibrates thresholds against real clients, then enforces WAF and throttle rules. If backend latency still rises, the team inspects Cloud Run autoscaling and database connection pools; Cloud Armor blocking part of the traffic does not automatically fix internal resource bottlenecks.

When legitimate users behind a shared corporate NAT IP are blocked alongside abusive traffic, consider adjusting rate-limit keys/thresholds per service capabilities, adding conditional relaxations, or requiring additional authentication. Never assume "raise the global threshold" is automatically the best answer; understand affected clients and attack exposure.

## 17. Pre-Production Cloud Armor Checklist

- [ ] Clearly identify load balancer type, backend services/backend buckets, and endpoints to protect.
- [ ] Select the right backend, edge, or network edge policy and confirm supported features.
- [ ] Audit the URL map to ensure no backend routes are left unprotected unintentionally.
- [ ] Verify lower priority numbers evaluate first; confirm default rule matches desired posture.
- [ ] Deploy new rules in Preview mode and gather representative logs.
- [ ] Tune WAF rules, rate-limit thresholds, and allowlists to minimize false positives.
- [ ] With Cloud CDN, clarify which policy applies before cache vs. only on cache misses.
- [ ] Close direct backend access paths that could bypass Cloud Armor.
- [ ] If using GKE Ingress, update the controller's declarative source config.
- [ ] Enable load balancer request logging with an appropriate sample rate.
- [ ] Dashboards track 403/429, denied requests, 5xx, latency, and backend metrics.
- [ ] Assign security rule ownership, review/rollback procedures, and change audit trails.
- [ ] Review Armor, LB, CDN, and Logging costs and configure appropriate budgets/alerts.
- [ ] Pipeline IAM has least-privilege permissions scoped to creating/updating/attaching required policies.

**Applied Exercise:** An order management app runs on Cloud Run, exposed via a global external Application Load Balancer. The static website uses Cloud CDN; the dynamic API has two routes: `/api/orders` and `/api/login`. Do the following:

1. Diagram the request path through DNS, load balancer, edge policy, cache, backend policy, and Cloud Run.
2. Design two security policies for CDN content and the API; specify attachment points, priorities, and default rules.
3. Write one WAF rule in Preview and one throttle limiting `/api/login` by IP; explain how you chose the threshold.
4. Identify a scenario where a cache hit skips the backend policy yet still passes through the edge policy.
5. Explain how to restrict clients from calling the `run.app` URL directly to bypass the load balancer.
6. Write commands to inspect policies, backend attachments, and a log filter to find blocked requests.
7. Plan enforcement/rollback if 403s spike unexpectedly for legitimate customers.
8. Propose reliability metrics and list resulting cost categories.

## Official References

- [Google Cloud Armor overview](https://cloud.google.com/armor/docs/cloud-armor-overview) — capabilities and endpoint groups.
- [Security policy overview](https://cloud.google.com/armor/docs/security-policy-overview) — policy types, priorities, and protection scope.
- [Create and manage security policies](https://cloud.google.com/armor/docs/configure-security-policies) — managing policies/rules.
- [Manage Cloud Armor security policies](https://cloud.google.com/armor/docs/manage-security-policies) — attaching policies, Preview, export, and rollback.
- [Set up preconfigured WAF rules](https://cloud.google.com/armor/docs/configure-waf) — WAF signatures, sensitivity, and body limits.
- [Configure rate limiting](https://cloud.google.com/armor/docs/configure-rate-limiting) — throttle and rate-based bans.
- [Integrate Cloud Armor with Cloud CDN, IAP, GKE and hybrid](https://cloud.google.com/armor/docs/integrating-cloud-armor) — evaluation order and ingress paths.
- [Per-request logging](https://cloud.google.com/armor/docs/request-logging) — logging conditions and filters.
- [Cloud Run ingress settings](https://cloud.google.com/run/docs/securing/ingress) — restricting direct service access.
- [Google Cloud Armor pricing](https://cloud.google.com/armor/pricing) — Standard/Enterprise tiers and pricing models.
