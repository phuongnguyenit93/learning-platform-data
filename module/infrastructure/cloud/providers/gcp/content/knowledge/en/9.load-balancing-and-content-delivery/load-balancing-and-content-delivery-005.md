# URL Maps and Host/Path-Based Routing

## Learning Objectives

After this lesson, learners will be able to:

1. Explain what a **URL map** is, where it sits in an **Application Load Balancer**, and how it routes HTTP(S) traffic by **hostname** and **URL path**.
2. Distinguish **URL map default**, **host rule**, **path matcher**, **path rule**, **route rule**, **backend service**, and **backend bucket**.
3. Accurately predict destinations when handling exact paths, trailing path wildcards, multiple hosts, default backends, and prioritized routes.
4. Configure a sample URL map using **gcloud** to separate a website, APIs, and static content; and know how to test before and after deployment.
5. Recognize limitations by load balancer type, differences between **routing**, **redirect**, and **rewrite**, as well as security, reliability, observability, and cost considerations.

## 1. Why Do We Need Host and Path Routing?

An online store may want to use a single public HTTPS address while serving multiple components:

- **https://shop.example.com/**: storefront website.
- **https://api.shop.example.com/v1/orders**: Java/Spring API version 1.
- **https://api.shop.example.com/v2/orders**: API version 2.
- **https://static.shop.example.com/images/logo.png**: images and static content.

If each component had its own IP address, certificate, and entry point, managing DNS, TLS, firewalls, releases, and monitoring would become much more complex. An **Application Load Balancer** operates at Layer 7 and can receive HTTP(S) requests and forward them to the right backend based on **Host** and **path**.

In the **CLOUD_PROVIDERS_GCP** module, learners choose services across Compute Engine, GKE, Cloud Run, storage, and databases while securing resources, automating releases, and monitoring reliability and costs. URL maps are a key component for placing multiple workloads behind a shared HTTP(S) entry point and controlling request paths.

A **URL map** is a configuration resource defining a set of HTTP(S) routing rules to **backend services** or **backend buckets**. It can be used by Application Load Balancers and certain other products such as Cloud Service Mesh. This lesson focuses on **Application Load Balancer**; specific details and capabilities differ across global, regional, external, internal, and classic modes.

## 2. Where Does the URL Map Sit in the Load Balancing Architecture?

~~~mermaid
flowchart LR
    U["Browser / API client"] --> DNS["DNS: domain → frontend IP"]
    DNS --> FR["Forwarding rule<br/>IP, port, protocol"]
    FR --> TP["Target HTTP(S) proxy<br/>TLS for HTTPS"]
    TP --> UM["URL map<br/>hostRules + pathMatchers"]
    UM --> BS1["Backend service<br/>web"]
    UM --> BS2["Backend service<br/>Java API"]
    UM --> BB["Backend bucket<br/>static assets"]
    BS1 --> W["MIG / NEG"]
    BS2 --> A["VM / GKE / Cloud Run<br/>via supported backend type"]
    BB --> CS["Cloud Storage"]
~~~

Different components handle different responsibilities:

| Component | Primary Role | Decides Host/Path? |
|---|---|---|
| **Cloud DNS or DNS provider** | Resolves domain name to frontend IP | Does not select backends by URL path |
| **Forwarding rule** | Receives traffic at IP and port; points to target proxy | Does not inspect path |
| **Target HTTP(S) proxy** | Handles HTTP, and TLS when using HTTPS; links to URL map | Uses URL map to decide routing |
| **URL map** | Reads host/path and applies rules/fallbacks to select destination | **Yes** |
| **Backend service** | Distributes requests to instance groups or network endpoints, with health/capacity configs | Not where URL map host/path rules are declared |
| **Backend bucket** | Routes traffic to a supported Cloud Storage bucket | Can receive traffic via URL map |

**Note:** creating a URL map does not automatically create an IP, DNS record, HTTPS certificate, backend, or frontend. A URL map only takes effect for live requests when a **target HTTP(S) proxy** serving traffic actively references it.

### Does a URL Map Support Every Load Balancer Type?

No. URL maps apply to compatible Layer 7 HTTP(S) products, notably **Application Load Balancers**. A Layer 4 **passthrough Network Load Balancer** does not use a URL map to read **/api** or **/images**. If the requirement is pure TCP/UDP routing, select the load balancer family matching the protocol and architecture.

| Application Load Balancer Type | URL Map Type | Remarks |
|---|---|---|
| **Global external** | **Global** | External managed; rich advanced traffic management capabilities |
| **Classic external** | **Global** | Supports host/path rules; some advanced features are not supported |
| **Regional external** | **Regional** | URL map resource is scoped to a region |
| **Cross-region internal** | **Global** | Internal managed, serving internal traffic across regions by design |
| **Regional internal** | **Regional** | Internal managed within a single region |

Whether a **URL map is global or regional** must be compatible with the load balancer's target proxy and backend resources. You cannot arbitrarily attach a global URL map to a regional proxy.

## 3. Internal Structure of a URL Map

A URL map has this logical structure:

~~~text
URL map: shop-map
|
|-- defaultService: web-main
|
|-- hostRules:
|   |-- api.shop.example.com    → pathMatcher: api-paths
|   |-- static.shop.example.com → pathMatcher: static-paths
|
|-- pathMatchers:
|   |-- api-paths
|   |   |-- /v1      → api-v1
|   |   |-- /v1/*    → api-v1
|   |   |-- /v2      → api-v2
|   |   |-- /v2/*    → api-v2
|   |   '-- defaultService: api-default
|   |
|   '-- static-paths
|       '-- defaultBackendBucket: static-assets
~~~

This is a **conceptual diagram**, not directly applicable YAML. The backends in the example must already be created and configured.

### 3.1. URL Map Default

**defaultService** or **defaultBackendBucket** at the **URL map level** is the fallback destination when **no host rule matches** the incoming hostname. The simplest URL map has only a default and needs no host rules or path matchers.

For example, a request to **https://unknown.shop.example.com/v1/orders** matches neither host rule in the diagram, so it goes to **web-main**, even though the path **/v1/orders** looks like an API path. **Host is evaluated before path.**

### 3.2. Host Rule

A **host rule** binds **one or more hostnames** to exactly **one path matcher**. Multiple host rules can share a path matcher, but one hostname must not point to conflicting host rules within the same URL map.

Examples:

| Host from HTTP Request | Selected Path Matcher |
|---|---|
| api.shop.example.com | **api-paths** |
| static.shop.example.com | **static-paths** |
| shop.example.com | No dedicated host rule → **URL map default** |

Hostnames can be exact FQDNs or wildcard patterns supported by the product, such as **\*.example.com**. Do not use IPv4/IPv6 IP addresses as names in host rules. Understand that wildcards match hostname labels; they are not arbitrary regular expressions for any string.

### 3.3. Path Matcher

A **path matcher** is the set of routing rules scoped to the host(s) it serves. Each matcher has its **own default**, used when the host matched but the path matched no specific rule.

For example, a request to **https://api.shop.example.com/health**:

1. Host **api.shop.example.com** matches **api-paths**.
2. There is no path rule for **/health**.
3. It falls back to **api-default** in the path matcher.

This request **does not fall back** to **web-main** at the URL map level.

### 3.4. Path Rules and Route Rules

| Property | Basic **pathRules** | Advanced **routeRules** |
|---|---|---|
| Goal | Simple path-based destination selection | Complex conditions and actions |
| Matching | Exact path or prefix with trailing wildcard per supported syntax | Exact/prefix/regex, headers/query params, and supported conditions |
| Precedence | Matches exact path first, then wildcard with the longest prefix | Evaluated by **priority**: lower numbers have higher priority |
| Destination | A backend service/bucket or eligible action | Can pick a service, redirect, or `routeAction` such as weighted backends |
| When to choose? | API v1/v2, assets, basic web | Canary releases, traffic splitting, header-based routing, rewrites, or advanced redirects |

Within **a single path matcher**, declare either **pathRules or routeRules** according to supported structure; do not arbitrarily mix both inside the same matcher. Not every load balancer mode supports every `routeRules` field.

## 4. Request Evaluation Order: Host → Path → Backend

~~~mermaid
flowchart TD
    R["HTTP(S) request arrives at proxy"] --> H{"Hostname matches hostRule?"}
    H -->|No| G["URL map default"]
    H -->|Yes| PM["Select pathMatcher attached to hostRule"]
    PM --> P{"Path/routing condition matches?"}
    P -->|Yes| D["Rule's backend or action"]
    P -->|No| F["Path matcher default"]
    G --> B["Forward / redirect per config"]
    D --> B
    F --> B
~~~

**Evaluation order matters:** the system does not scan all path rules first before checking the host. Once a host matches, only the rules belonging to the path matcher linked to that host decide the destination.

### 4.1. Exact Path and Wildcard Are Not Equivalent

Two fundamental patterns:

- `/api`: matches only the exact path **/api**.
- `/api/*`: matches paths starting with **/api/** and anything after, but **does not match /api**.

That is why configurations serving both **/v1** and **/v1/orders** commonly need **two path patterns**: **/v1** and **/v1/\***.

| Request Path | **/v1** | **/v1/\*** | Result if both point to api-v1 |
|---|---|---|---|
| /v1 | Yes | No | **api-v1** |
| /v1/ | No | Yes | **api-v1** |
| /v1/orders | No | Yes | **api-v1** |
| /v1/orders/123 | No | Yes | **api-v1** |
| /v1beta/orders | No | No | **matcher default** |
| /V1/orders | No (case-sensitive rules) | No (case-sensitive rules) | **matcher default** |

**Basic path rule:** a wildcard in a path rule must follow supported syntax (such as trailing **/\***), not **/v\*1** or arbitrary regex. If multiple wildcards match, the longer prefix wins—for example, **/api/admin/\*** takes precedence over **/api/\***.

### 4.2. Example Routing Outcomes by Host and Path

Assume the URL map from Section 3 is deployed:

| Request | Expected Destination | Reason |
|---|---|---|
| **shop.example.com/** | **web-main** | No dedicated host rule → URL map default |
| **api.shop.example.com/v1/orders** | **api-v1** | Host matches api-paths; prefix /v1/* |
| **api.shop.example.com/v1** | **api-v1** | Exact /v1 |
| **api.shop.example.com/v2/orders** | **api-v2** | Prefix /v2/* |
| **api.shop.example.com/health** | **api-default** | Host matched but path did not |
| **static.shop.example.com/images/a.png** | **static-assets** | Static path matcher has default backend bucket |
| **unknown.shop.example.com/v2/orders** | **web-main** | Unmatched host skips API pathRules |

Selecting a backend does not mean the backend is healthy or the API actually returns **200 OK**. The URL map determines the route; backend services, health checks, firewalls, and the application also determine the final outcome.

### 4.3. Hostname, Port, Query String, and TLS

In **https://api.shop.example.com:443/v1/orders?state=pending**:

- **Hostname:** `api.shop.example.com`, used for host matching.
- **Path:** `/v1/orders`, used for basic `pathRules`.
- **Query:** `state=pending`; basic `pathRules` cannot branch by query values. **`routeRules`** can match query parameters in supported modes.
- **TLS/SNI:** certificates and HTTPS connections must work properly at the target HTTPS proxy. The URL map **does not issue or validate** certificates for hostnames.

If a client sends an unexpected hostname not permitted by TLS or the application, enforce separate controls; host routing does not replace user authentication or blocking malicious `Host` headers at the application layer.

## 5. Hands-On: Building a URL Map for a Storefront

This lab uses a **global external Application Load Balancer** with a global URL map. All names below are examples; replace the project ID, backend names, and domains with actual pre-created resources.

### 5.1. Preparing Backends and Permissions

Suppose project **shop-prod-001** already has:

| Resource | Type | Role |
|---|---|---|
| **web-main** | Global backend service | Homepage and fallback |
| **api-default** | Global backend service | API fallback, health, or controlled error responses |
| **api-v1** | Global backend service | Java app version 1 |
| **api-v2** | Global backend service | Java app version 2 |
| **static-assets** | Global backend bucket | Cloud Storage static assets if supported by LB type |
| **shop-map** | Global URL map to create | HTTP(S) routing |

Backend services can use appropriate instance groups or NEGs—for example, a **serverless NEG** to Cloud Run when supported by the architecture and load balancer type. **Creating backend services or buckets is a separate task.** A URL map points to existing resources; it does not deploy Java containers, create VMs, or upload files to Cloud Storage.

The operator needs appropriate Compute Load Balancing permissions (including permissions on URL maps and **use** permissions on referenced backend resources). If cross-project service referencing is used, handle IAM in the backend's project as well. Test in a dedicated project first; avoid unreviewed changes in production.

### 5.2. Inspecting Current State Before Making Changes

~~~bash
gcloud config get-value project

gcloud compute backend-services list \
  --project=shop-prod-001 --global

gcloud compute backend-buckets list \
  --project=shop-prod-001

gcloud compute url-maps list \
  --project=shop-prod-001
~~~

Carefully verify **backend types**, **load balancing schemes**, exact names, and global/regional scope. If editing an existing URL map, **export and review** it before importing or running CLI updates.

### 5.3. Creating the URL Map with a Default Backend

~~~bash
gcloud compute url-maps create shop-map \
  --project=shop-prod-001 \
  --default-service=web-main \
  --global

gcloud compute url-maps describe shop-map \
  --project=shop-prod-001 \
  --global
~~~

In this state, the URL map only has default **web-main**. Every hostname and path goes to `web-main`. This is useful for verifying fallback before adding branching rules.

### 5.4. Creating a Path Matcher for the API

~~~bash
gcloud compute url-maps add-path-matcher shop-map \
  --project=shop-prod-001 \
  --global \
  --path-matcher-name=api-paths \
  --default-service=api-default \
  --path-rules="/v1=api-v1,/v1/*=api-v1,/v2=api-v2,/v2/*=api-v2" \
  --new-hosts=api.shop.example.com
~~~

This command creates a **path matcher** named **api-paths** with default **api-default** and 4 patterns, while **--new-hosts** creates a host rule mapping **api.shop.example.com** to that matcher. The CLI requires a matcher to be referenced by a host rule, so creating both together avoids an orphaned matcher.

### 5.5. Adding a Host Rule If the API Has a Second Hostname

Suppose the business also wants **api-alt.shop.example.com** to use the same path rules. Once **api-paths** already exists:

~~~bash
gcloud compute url-maps add-host-rule shop-map \
  --project=shop-prod-001 \
  --global \
  --hosts=api-alt.shop.example.com \
  --path-matcher-name=api-paths
~~~

This adds **another** host rule referencing the existing matcher. Both **api.shop.example.com** and **api-alt.shop.example.com** use **api-paths**; unmatched hosts still use the URL map default **web-main**. If the lab only uses one API hostname, skip Section 5.5.

### 5.6. Adding a Path Matcher for Static Content

~~~bash
gcloud compute url-maps add-path-matcher shop-map \
  --project=shop-prod-001 \
  --global \
  --path-matcher-name=static-paths \
  --default-backend-bucket=static-assets \
  --new-hosts=static.shop.example.com
~~~

This simultaneously creates **static-paths** and the host rule for **static.shop.example.com**. All requests to this host go to the backend bucket unless another rule is added. The backend bucket serves compatible Cloud Storage content and can use **Cloud CDN** when enabled/configured. A URL map does not automatically enable caching or grant object read permissions.

### 5.7. Reviewing the Configuration

~~~bash
gcloud compute url-maps describe shop-map \
  --project=shop-prod-001 \
  --global \
  --format="yaml(name,defaultService,hostRules,pathMatchers)"
~~~

Check both host rules, matching path matcher names, API/static defaults, and all four path rules. Record the output before attaching to a target proxy.

### 5.8. Attaching the URL Map to the Frontend (Related Knowledge)

The target HTTP(S) proxy references the URL map; the forwarding rule points to the proxy. If the proxy already exists, changing its URL map is a separate, traffic-impacting change:

~~~bash
# Read which URL map the HTTPS proxy currently uses
gcloud compute target-https-proxies describe shop-https-proxy \
  --project=shop-prod-001 \
  --global \
  --format="yaml(name,urlMap)"
~~~

Only switch the proxy's URL map after full review and approval following your organization's release process. A new URL map **will not receive live traffic** even after creation succeeded if no proxy references it yet.

## 6. Configuring URL Maps with YAML and Testing Paths

For complex maps or CI/CD-managed setups, YAML export/import makes reviewing diffs easier. The logical example below is an **illustrative** global URL map configuration; **PROJECT_ID** and backend names must be replaced with real resources.

~~~yaml
kind: compute#urlMap
name: shop-map
defaultService: projects/PROJECT_ID/global/backendServices/web-main

hostRules:
  - hosts:
      - api.shop.example.com
    pathMatcher: api-paths
  - hosts:
      - static.shop.example.com
    pathMatcher: static-paths

pathMatchers:
  - name: api-paths
    defaultService: projects/PROJECT_ID/global/backendServices/api-default
    pathRules:
      - paths: ["/v1", "/v1/*"]
        service: projects/PROJECT_ID/global/backendServices/api-v1
      - paths: ["/v2", "/v2/*"]
        service: projects/PROJECT_ID/global/backendServices/api-v2

  - name: static-paths
    defaultService: projects/PROJECT_ID/global/backendBuckets/static-assets
~~~

**Explanation:** two host rules reference two separate matchers; each matcher contains only path rules relevant to its host. **web-main** is the default for the entire URL map; **api-default** and **static-assets** are the defaults for the two matchers.

When exporting an existing configuration, editing the exported file preserves fields omitted from this simplified example. Do not import a stripped-down example directly onto a production URL map, as it could overwrite other settings.

### 6.1. Building a Test Matrix Before Release

| Host | Path | Expected Backend |
|---|---|---|
| shop.example.com | / | web-main |
| api.shop.example.com | /v1 | api-v1 |
| api.shop.example.com | /v1/orders | api-v1 |
| api.shop.example.com | /v2/orders | api-v2 |
| api.shop.example.com | /v1beta | api-default |
| api.shop.example.com | /health | api-default |
| static.shop.example.com | /images/logo.png | static-assets |
| unexpected.shop.example.com | /v1/orders | web-main |

The test suite intentionally includes **negative cases**: **/v1beta** must not mistakenly route to v1, and unknown hostnames must not automatically enter the API.

### 6.2. URL Map Configuration Tests

For **global external** or **classic Application Load Balancers**, `gcloud` supports **URL map validate** to check configuration syntax and declared **tests** without **updating the live URL map**.

Example `tests` section inside an exported YAML file, after replacing **PROJECT_ID**:

~~~yaml
tests:
  - description: API v1 exact path
    host: api.shop.example.com
    path: /v1
    service: projects/PROJECT_ID/global/backendServices/api-v1

  - description: API v1 nested path
    host: api.shop.example.com
    path: /v1/orders
    service: projects/PROJECT_ID/global/backendServices/api-v1

  - description: API unknown path uses matcher default
    host: api.shop.example.com
    path: /v1beta
    service: projects/PROJECT_ID/global/backendServices/api-default

  - description: Unknown host uses URL map default
    host: unexpected.shop.example.com
    path: /v2/orders
    service: projects/PROJECT_ID/global/backendServices/web-main
~~~

Tests belong inside the **same complete URL map YAML file**, not a standalone YAML file containing only **tests**. Validation requires appropriate IAM permissions and valid referenced backend resources.

~~~bash
# Export existing configuration for review
gcloud compute url-maps export shop-map \
  --project=shop-prod-001 \
  --global \
  --destination=shop-map.yaml

# Edit shop-map.yaml: route rules + tests, preserving required fields
# Static check without creating/updating the URL map
gcloud compute url-maps validate \
  --project=shop-prod-001 \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --source=shop-map.yaml
~~~

**Limitation:** per Google Cloud documentation, **gcloud compute url-maps validate** **does not support regional external Application Load Balancers or internal Application Load Balancers**. For unsupported types, review via API/Console, validate configs, and run live tests in a staging/test environment using appropriate tools. Never mark "validated" if that LB type's tooling does not support it.

### 6.3. Importing Once Approved

~~~bash
# Example impactful operation; perform only after review and rollback prep
gcloud compute url-maps import shop-map \
  --project=shop-prod-001 \
  --global \
  --source=shop-map.yaml
~~~

**Import can replace the existing URL map configuration.** Before importing, diff against the live export, verify backends, retain the backup export for rollback, and confirm the LB type. After importing, test real requests rather than relying solely on exit code 0.

### 6.4. Live Testing Against the Frontend

Once the URL map is active on the proxy and DNS/TLS are configured:

~~~bash
curl -i https://api.shop.example.com/v1/orders
curl -i https://api.shop.example.com/v2/orders
curl -i https://api.shop.example.com/v1beta
curl -I https://static.shop.example.com/images/logo.png
~~~

If DNS has not yet cut over to the new frontend but you know **LB_IP**, test hostname and TLS/SNI using **--resolve**:

~~~bash
curl --resolve api.shop.example.com:443:LB_IP \
  -i https://api.shop.example.com/v1/orders
~~~

Replace **LB_IP** with the real frontend IP and use a valid certificate for the hostname. This overrides DNS resolution locally in **curl** without changing user DNS or bypassing TLS verification.

To confirm exactly which backend handled a request, temporarily inspect version marker headers in a test environment or correlate Cloud Logging/Cloud Monitoring across the load balancer and backends. Never expose sensitive debug headers in production.

## 7. Advanced: `routeRules` and Conditions Beyond Path

When requirements are simply **/v1 → API v1** and **/v2 → API v2**, **pathRules** suffice. When you need decisions based on request headers, query parameters, traffic weights, redirects, or rewrites, supported Application Load Balancer modes can use **routeRules**.

### 7.1. Lower Priority Numbers Are Evaluated First

With `routeRules`, smaller **priority** numbers are evaluated earlier. Example:

| Priority | Match Condition | Backend |
|---:|---|---|
| 10 | Header **x-canary: true** and prefix **/api/** | api-canary |
| 100 | Prefix **/api/** | api-stable |
| Default | Does not match any routeRules | web-default |

A request with **x-canary: true** and path **/api/orders** matches both rules, so **priority 10** wins first. Requests missing the canary header fall through to rule 100.

Inside a **routeRule**, entries in **matchRules** are combined with **OR** logic between entries; multiple conditions inside the same **matchRule** are combined with **AND** logic. To require both path and header simultaneously, place them inside the **same matchRule**.

~~~yaml
# Illustrative snippet in pathMatchers[].routeRules for supported LBs
routeRules:
  - priority: 10
    matchRules:
      - prefixMatch: /api/
        headerMatches:
          - headerName: x-canary
            exactMatch: "true"
    service: projects/PROJECT_ID/global/backendServices/api-canary

  - priority: 100
    matchRules:
      - prefixMatch: /api/
    service: projects/PROJECT_ID/global/backendServices/api-stable
~~~

**Prerequisite:** choose whether a path matcher uses **routeRules**, and do not place **pathRules** in the same matcher simultaneously. Verify field support for the LB type before importing.

### 7.2. Query Parameter Routing

Suppose only requests containing **?preview=true** should go to the preview backend, while all others go to stable. Basic **pathRules** cannot handle this logic. **queryParameterMatches** inside **routeRules** enables this on supported LB modes.

Supported match types include exact, prefix, regex, and others depending on the product. **Regex** must follow **RE2** syntax, not arbitrary PCRE syntax. **Classic Application Load Balancer** does not support regular expression routing like the managed modes noted in documentation.

### 7.3. Weighted Backend Services for Rollouts

A `routeRule` can split traffic between two backend services by weight:

~~~yaml
# Illustrative snippet for /api/ route rule on supported LBs
routeRules:
  - priority: 20
    matchRules:
      - prefixMatch: /api/
    routeAction:
      weightedBackendServices:
        - backendService: projects/PROJECT_ID/global/backendServices/api-stable
          weight: 95
        - backendService: projects/PROJECT_ID/global/backendServices/api-canary
          weight: 5
~~~

A **95/5** split is a statistical target distribution, **not a guarantee of exactly 95 stable requests and 5 canary requests out of every 100 requests**. Health state, session affinity, backend config, and caching can skew observed counts. Measure error rates, latency, request counts, and business metrics before increasing canary weight.

## 8. Routing, Redirect, and Rewrite: Three Easily Confused Behaviors

| Behavior | URL Seen by User | Request Handling | Example |
|---|---|---|---|
| **Route** | Unchanged | Selects appropriate backend | **/v2/orders → api-v2** |
| **Redirect** | Client receives **HTTP 3xx + Location** and typically sends a new request | Redirected on client side | **http://... → https://...**, or **/old → /new** |
| **Rewrite** | Usually keeps the URL requested by client | LB modifies host/path when **forwarding to backend** | **/public/v1/orders → /orders** at backend |

### 8.1. Redirect Differs from Backend Routing

For example, to convert all HTTP requests to HTTPS, configure a **URL map redirect** returning 301/302/307/308 per service capabilities. With a global external Application Load Balancer, documentation typically requires **a partial HTTP load balancer** (forwarding rule + target HTTP proxy + redirect URL map) sharing the frontend IP with the HTTPS load balancer. A URL map pointing to an HTTPS backend **does not automatically turn** port 80 HTTP requests into redirects.

### 8.2. Rewrite Requires Care

Suppose a Java backend only exposes **/orders**, while the public API is **/v1/orders**. A URL rewrite can strip the **/v1** prefix on requests forwarded to the backend. Application logs will then record the rewritten path; account for this during diagnostics and testing.

**URL rewrite is not an HTTP redirect.** The client still sees the URL it originally called; the backend receives the modified path set by the load balancer. Rewrites must be tested against route paths, cache keys, signature validation, and application auth logic.

### 8.3. Where Does Each Feature Apply?

Support for **redirects**, **rewrites**, **header modifications**, **traffic splitting**, **retries/timeouts**, and **regex matching** differs across **classic**, **global/regional external**, and **internal Application Load Balancers**. Before using a YAML field, check the product's feature support table and API schema. Never copy an advanced config verbatim from one LB type to another simply because both have a URL map.

## 9. How Do URL Maps Relate to Cloud CDN and Content Delivery?

When serving assets via a **backend bucket** or a backend service with **Cloud CDN** enabled, the URL map decides **which backend receives the request**, while Cloud CDN decides caching and serving at the edge per configuration.

Example:

~~~text
https://static.shop.example.com/images/logo.png
        |
        v
hostRule: static.shop.example.com
        |
        v
pathMatcher: static-paths
        |
        v
backend bucket: static-assets
        |
        v
Cloud CDN (if enabled) / Cloud Storage
~~~

**Having a backend bucket does not automatically enable Cloud CDN.** Cache mode, TTL, signed URL/cookie, cache key, and invalidation settings belong to the backend bucket/service and Cloud CDN, not URL map host/path matching.

### 9.1. Caching Affects How You Measure Routing

When changing backends, cached responses may continue being served from the edge per TTL policy. Therefore distinguish:

- Whether the request **was routed by the load balancer's URL map** to the right backend/cache.
- Whether the request **actually reached the origin** or was served from cache.
- Stale content is a **cache policy or invalidation** issue, not necessarily a broken URL map.

Before rolling out asset changes, plan content-hashed filenames, TTLs, cache invalidation, and rollback policies. Combine Cloud Monitoring and logs at the appropriate layer to avoid misinterpreting why the origin shows no request logs when responses were served from cache.

## 10. Common Configuration Mistakes

| Symptom | Possible Cause | How to Diagnose |
|---|---|---|
| **/v1** hits default while **/v1/orders** works | Only declared **/v1/\*** | Add exact path **/v1** |
| **/v1beta** accidentally routes to v1 | Overly broad prefix in `routeRules` or unintended wildcard rule | Use path rules **/v1**, **/v1/\*** or tighter conditions |
| **api.shop.example.com** serves the website | Missing/wrong host rule, or proxy points to another URL map | Check `Host`, **url-maps describe**, target proxy |
| Host matches, yet unknown paths still enter API backend | Path matcher default set to `api-default` | Intended fallback by design; adjust if undesired |
| No change visible after creating URL map | Target proxy still uses old map or DNS points elsewhere | **target-https-proxies describe**, forwarding rule, DNS/IP |
| All paths go to the same backend | URL map only has default, missing host rules or matchers | Inspect **hostRules**, **pathMatchers**, **defaultService** |
| Request returns **404** | Backend/app lacks endpoint, or map routed to error backend | Use routing tests, backend headers/logs, and inspect app |
| Request returns **502/503** | No healthy endpoints, timeout, firewall/health check, or app crash | Health, backend logs, proxy logs, firewalls |
| Some paths fail | Case sensitivity, trailing slash, path prefix, query/redirect/rewrite | Test exact path, **/path/**, **/path/x**, encoded paths |
| Canary traffic differs from 95/5 | Small sample size, session affinity, caching, health, or split config | Analyze a sufficiently large sample, logs, and health |
| SSL/TLS fails despite valid rules | Certificate doesn't match hostname or DNS/SNI mismatch | TLS cert, target HTTPS proxy, frontend domain/IP |
| Old routes vanished after import | YAML import omitted fields or overwrote existing map | Diff before/after exports and perform controlled rollback |
| Cannot validate regional URL map | **validate** command has limitations by LB type | Use product-appropriate testing workflows |
| Routing is right, yet costs spike | CDN misses, egress, backend autoscaling, request surges | Billing reports, LB, CDN, and backend metrics |

### Layered Investigation Workflow

1. **DNS/IP:** does the domain point to the right frontend?
2. **TLS/Proxy:** is the HTTPS certificate valid, and does the proxy use the expected URL map?
3. **Host:** does the HTTP `Host` header match the intended `hostRule`?
4. **Path:** does the URL path match an exact rule, wildcard rule, or `routeRule` priority as expected?
5. **Fallback:** is the request hitting the URL map default or the path matcher default?
6. **Backend:** does the service/bucket exist, is it healthy, with proper IAM and network routing?
7. **Cache:** was the response served from Cloud CDN or the origin?
8. **Logs and tests:** compare the same hostname/path between the reviewed configuration and live requests.

Never loosen IAM or global firewalls just because you see a 404: it may simply be a routing or application endpoint issue. Nor should you conclude a URL map is wrong purely from a response code when certificates or backend health are actually broken.

## 11. Security, Reliability, and Release Automation

### 11.1. Securing Multiple Hosts on One Frontend

- **TLS certificates** must cover all served hostnames; verify whether wildcard certs cover actual domain scopes.
- **Host rules** only decide routing; they do not provide **authentication** or **authorization** for data. Protect APIs using application auth, IAM, IAP/Cloud Armor, or compatible features scoped properly.
- Choose a safe **default backend** for unknown hosts—such as a backend returning a controlled **404**—to avoid accidentally exposing unintended content.
- If routing on client-controlled headers or query params, never treat them as proof of special privileges without proper authentication.
- Review **backend IAM** when using Cloud Run service accounts, cross-project backends, or private services. A valid URL map does not automatically grant access across all resources.

### 11.2. Reliability

A good URL map has clear fallbacks, but fallback **does not automatically fail over to a different healthy API** if a backend crashes. Each backend service needs health checks, capacity, autoscaling, and timeouts suited to its backend type.

For an order API, design health endpoints that avoid excessive dependencies on external systems so they aren't overly fragile, yet still reflect real serving readiness. When rolling out v2, use test environments, canary releases, 4xx/5xx monitoring, percentile latency, and SLO checks before shifting 100% of traffic to v2.

### 11.3. CI/CD and Infrastructure as Code

Recommended flow:

~~~mermaid
flowchart LR
    D["URL map change<br/>in Git / IaC"] --> R["Review + structural check"]
    R --> V["Validate/tests if supported by LB"]
    V --> S["Deploy to staging"]
    S --> P["Host/path + backend smoke tests"]
    P --> A["Production approval"]
    A --> M["Controlled apply / import"]
    M --> O["Metrics, logs, rollback"]
~~~

If using **Terraform**, manage the URL map, proxy, and backends within appropriate state boundaries. Avoid mixing manual Console edits with Terraform applies without reconciling drift, as old IaC runs can overwrite live changes.

**Rollback:** keep a known-good exported configuration, keep the previous backend running during the observation window, and know the exact command or pipeline to restore the URL map. Rolling back routing does not automatically revert data written by the new backend; consider API/schema compatibility during canaries.

### 11.4. Cost

Consider costs for the **Application Load Balancer**, data processed, egress, Cloud CDN/cache egress, backend compute, Cloud Storage/backend buckets, and logging. Host/path routing does not make two backends a single free resource.

Optimization can come from reducing origin requests via caching, right-sizing backends, and sensible path routing. Always balance cost against latency, hit rates, security, and reliability. Track billing by project, labels, service, and actual workloads.

## 12. Design Scenario: E-Commerce on GCP

**Minh Phat** Corp wants to serve a web frontend, Java APIs v1/v2, and product images behind an external Application Load Balancer. The system consists of:

- **web-main** on a managed instance group or appropriate backend.
- **api-v1** and **api-v2** on Cloud Run via **serverless NEGs** or corresponding backend services per design.
- **static-assets** as a Cloud Storage backend bucket with optional Cloud CDN.
- **Cloud SQL** as the API database, never receiving requests directly from the URL map.

### 12.1. Routing Plan

| Host/Path | Backend | Owner |
|---|---|---|
| shop.example.com/* | web-main | Frontend team |
| api.shop.example.com/v1 and /v1/* | api-v1 | Java API team |
| api.shop.example.com/v2 and /v2/* | api-v2 | Java API team |
| api.shop.example.com/other | api-default | Java API team |
| static.shop.example.com/* | static-assets | Content team |
| Host not in allowlist | Safe error/default backend | Platform team |

In real projects, decide the default for unknown hostnames based on security policy. For instance, **web-main** works for learning routing, while multi-tenant or sensitive environments can replace it with an **unknown-host** backend returning a controlled error.

### 12.2. Test Plan

1. **Unit routing tests:** cover all exact paths, wildcards, hosts, and defaults; verify **/v1beta** does not enter v1.
2. **Integration:** call the live frontend or use **curl --resolve** to verify proxy, TLS, and backends.
3. **Security:** test unexpected `Host` headers, path traversal/canonicalization, token-protected endpoints, and internal admin paths not meant to be public.
4. **Performance:** measure per-backend latency, Cloud CDN hit rate, throughput, and 5xx under load.
5. **Resilience:** test unhealthy backends and rolling back v2 to v1 via the release mechanism.
6. **Cost:** monitor egress, CDN, compute, and logging costs before and after changes.

### 12.3. Example Rollout Mistake

An engineer changes the **api.shop.example.com** host rule to point to path matcher **web-paths**, leaving v1/v2 `pathRules` inside **api-paths**. As a result, API calls return web pages or 404s, even though both API backends are completely healthy.

**Root cause:** only the path matcher **referenced by the host rule** is evaluated. Rules inside an unattached matcher have zero effect on requests to that hostname.

**How to verify:** inspect the URL map, compare `hostRules`/`pathMatchers`, run configuration tests and smoke tests. The fix is reattaching the reviewed path matcher—not granting extra IAM roles to the API.

## 13. Hands-On Exercises

### Exercise A: Predict the Backend

Given a URL map with:

- URL map default = **web-main**.
- Host **api.example.com → api-matcher**.
- **api-matcher** has path rules **/orders**, **/orders/\*** → **orders-api**; **/users/\*** → **users-api**; matcher default = **api-fallback**.
- Host **static.example.com → assets-matcher**; matcher default = **assets-bucket**.

Pick the backend for each request:

| Request | Answer |
|---|---|
| api.example.com/orders | **orders-api** |
| api.example.com/orders/123 | **orders-api** |
| api.example.com/users | **api-fallback** |
| api.example.com/users/123 | **users-api** |
| api.example.com/orders2 | **api-fallback** |
| static.example.com/logo.svg | **assets-bucket** |
| unknown.example.com/orders/123 | **web-main** |

Explain why **/users** does not match **/users/\*** and why an unmatched hostname cannot use `api-matcher`'s path rules.

### Exercise B: Design a v1 → v2 Migration

A Java v1 API serves 100% of traffic at **/api/orders**; the team wants to release experimental v2 to 5% of requests with rollback capability.

Do the following:

1. Choose **pathRules** or **routeRules** and explain why.
2. Propose how to split traffic and which metrics to monitor.
3. Identify risks when v1 and v2 write to the same Cloud SQL schema.
4. Describe approval and rollback steps if v2 spikes 5xx errors or latency.

**Solution guide:** Use **routeRules + weightedBackendServices** where supported by the load balancer. A 95/5 split is an expectation; measure over sufficient requests and monitor errors and data compatibility. Routing rollback must keep v1 compatible with data written during the canary phase.

### Exercise C: Distinguish Redirect and Rewrite

A legacy app only supports **/users**, while the public API is **/v2/users**. Meanwhile, HTTP users must be moved to HTTPS.

Distinguish:

- The behavior needing **rewrite** so the backend receives **/users** while the client still sees **/v2/users**.
- The behavior needing **redirect** so the client switches from HTTP to HTTPS via a 3xx response.
- Supporting configurations required: HTTPS certificate, target proxies, forwarding rules, and feature support for the specific load balancer type.

### Exercise D: Testing and Diagnostics

A team creates a new URL map, yet production keeps sending all requests to **web-main**.

Write a 5–8 step runbook covering: DNS and IP, which URL map the proxy references, `hostRules` and `pathMatchers`, URL map default and matcher default, `gcloud validate` if supported, `curl --resolve`, backend health, logs, and rollback.

## 14. Key Takeaways and References

**Core Principles:**

1. A **URL map** is a Layer 7 HTTP(S) routing resource: **hostname** selects a **hostRule/pathMatcher**, and **path** selects the matching `pathRule` or `routeRule`.
2. There are **two fallbacks**: the **URL map-level** default when the host does not match, and the **path matcher** default when the host matches but no path/route rule fits.
3. **/api** differs from **/api/\***. Exact paths and wildcards must be designed and tested separately.
4. **pathRules** handle simple paths; **routeRules** support priorities, advanced conditions, and weighted traffic depending on the product.
5. **Redirect** returns 3xx to the client, **rewrite** transforms the request sent to the backend, and **routing** selects the destination. Do not confuse the three.
6. **Global and regional URL maps** differ; validation commands and traffic management features vary by load balancer type.
7. A URL map does not replace **DNS, TLS, IAM, Cloud Armor, health checks, CDN policies, or monitoring**. Always test the path from frontend to real backends.

**Official Google Cloud Documentation:**

1. [URL maps overview](https://docs.cloud.google.com/load-balancing/docs/url-map-concepts) — structure, host/path order, fallbacks, `routeRules`, and limits.
2. [Use URL maps](https://docs.cloud.google.com/load-balancing/docs/url-map) — CLI setup, export/import, configuration tests, and validation.
3. [gcloud compute url-maps add-host-rule](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/add-host-rule) — host and path matcher flags.
4. [gcloud compute url-maps add-path-matcher](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/add-path-matcher) — declaring matchers, defaults, and path rules.
5. [gcloud compute url-maps validate](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/validate) — static test scope and limitations.
6. [Traffic management for global external Application Load Balancers](https://docs.cloud.google.com/load-balancing/docs/https/traffic-management-global) — `routeRules`, headers, weighted backends, rewrites, and redirects.
7. [Set up HTTP-to-HTTPS redirect for global external Application Load Balancers](https://docs.cloud.google.com/load-balancing/docs/https/setting-up-global-http-https-redirect) — redirect setup via an additional HTTP frontend.
8. [Cloud CDN overview](https://docs.cloud.google.com/cdn/docs/overview) — edge caching and supported backends.
