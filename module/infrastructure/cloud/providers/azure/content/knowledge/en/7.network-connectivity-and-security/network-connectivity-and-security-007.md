# Protecting Web Applications with Web Application Firewall

A web application may already be deployed inside a VNet, have its ports restricted with a Network Security Group (NSG), and enforce HTTPS—yet it still faces malicious HTTP requests: SQL injection attempts, cross-site scripting (XSS), probing of sensitive paths, or abnormal automated traffic. These behaviors happen at the application layer, where a rule opening TCP port 443 cannot tell a legitimate request apart from one carrying an attack payload.

**Web Application Firewall (WAF)** is an HTTP/HTTPS traffic inspection layer placed in front of a web application or API. Azure offers WAF integrated with **Azure Application Gateway** and **Azure Front Door**. WAF inspects HTTP request characteristics against a policy, applies managed or custom rule sets, and logs events for operations, investigation, and tuning.

This lesson belongs to the **Network Connectivity and Security** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module introduces Azure—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, data, deployment, monitoring, security, and cost control. In an Azure application architecture, WAF adds a **Layer 7** defense layer alongside VNets, NSGs, identity management, monitoring, and application-level security controls.

After this lesson, you will be able to:

- Explain what WAF controls and what limitations WAF cannot solve on its own.
- Choose between Azure Application Gateway WAF and Azure Front Door WAF based on architecture.
- Distinguish **managed rules**, **custom rules**, **Detection**, and **Prevention**.
- Design WAF policies, policy association scopes, rules, exclusions, and monitoring.
- Reduce false positives without disabling the entire protection layer.
- Build a rollout roadmap from testing to production, inspect logs, and trace incidents.
- Protect direct access paths to the origin to prevent bypassing the WAF.

## 1. Where Does WAF Operate?

WAF is a reverse-proxy security control positioned inline on web traffic paths. It receives requests, evaluates them against a policy, and forwards valid requests to backend servers (origins/backends). Blocked requests are not forwarded along the normal path.

~~~text
   Users / Browsers / API Clients
                  |
               HTTPS
                  |
      +-----------v------------+
      | Azure Front Door WAF   |
      | or Application Gateway |
      | WAF                    |
      +-----------+------------+
                  |
        Inspect HTTP request
        - managed rules
        - custom rules
        - policy action/mode
                  |
          +-------+-------+
          |               |
     Valid Request  Blocked Request
          |               |
          v               v
     Web/API Backend  Log + Response
          |
     Databases /
     Internal Services
~~~

### What Can WAF Inspect?

Depending on the product, policy, request type, and inspection limits, WAF can evaluate the HTTP method, URL, query string, headers, cookies, client IP address, and supported request body payloads. Managed rules detect common application exploit patterns; custom rules enforce organization-specific conditions.

For example, consider an endpoint **/products?search=...** used to search products. A request containing a SQL-injection-like pattern in the **search** parameter can be logged or blocked by a managed rule. However, WAF does not execute your application's authorization logic: it cannot tell whether a user is allowed to view someone else's order if the request looks syntactically valid.

### What WAF Does Not Replace

| Tool / Mechanism | Primary Scope | Why You Still Need It Alongside WAF |
|---|---|---|
| **NSG** | Allow/deny L3/L4 network connections by IP, port, and protocol | Restricts network flows to subnets/NICs; does not inspect full HTTP payloads |
| **Azure DDoS Protection** | Defends against network-layer DDoS attacks | WAF does not replace L3/L4 DDoS mitigation |
| **Azure Firewall** | Centralized network traffic control across many protocols | Scope and policy differ from an HTTP-specialized WAF |
| **Microsoft Entra ID / auth** | Verifies identity and issues tokens | WAF does not determine per-user business permissions |
| **API authorization** | Decides who can read/modify which record | Prevents cross-account or cross-tenant access flaws that generic rules cannot spot |
| **Secure coding, SAST/DAST** | Prevents and finds vulnerabilities at the source | WAF is only a risk-mitigation layer; root vulnerabilities must still be fixed |
| **Backup, DR, monitoring** | Recovery, detection, and investigation | WAF does not guarantee data recoverability or continuous app uptime |

WAF primarily evaluates **HTTP/HTTPS**. Never use WAF to protect an arbitrary TCP port, SSH service, database protocol, or general east-west traffic inside a VNet.

## 2. Choosing Azure Application Gateway WAF or Azure Front Door WAF?

Azure offers two primary WAF deployment models tailored to different architectural needs.

| Criterion | Application Gateway WAF | Azure Front Door WAF |
|---|---|---|
| Placement | Regional Layer 7 reverse proxy in an Azure region | Global edge reverse proxy / entry point |
| Common architecture | Applications in a VNet, regional backends, host/path routing | Global websites or APIs, multi-region, needing edge routing/acceleration |
| Related resources | WAF-capable Application Gateway SKU, backend pool, listener, routing rule | Front Door profile/endpoint, origin group, route, domain, and security policy |
| Rule sets | WAF policy with supported managed rules and custom rules | WAF policy with features per Front Door SKU/tier |
| Scope of application | Can attach policy at gateway and supported scopes like listener/path | Attaches WAF policy to domains/paths via security policy configuration |
| Key considerations | VNet, dedicated subnet, backend health, TLS, path to backend | Origin security, bypass prevention, custom domains, routing, and tier-based features |

**Application Gateway WAF_v2** typically fits when protecting a regional Azure application, reaching backends inside a VNet, and managing ingress alongside network topology. Example: an HR portal deployed in one region with VM backends or private endpoints to web services depending on connectivity support.

**Azure Front Door WAF** fits when serving users across multiple geographies who need a global public entry point, routing across origins, and edge protection. Example: a SaaS application with origins in Southeast Asia and Europe. Features such as managed rule sets and bot protection depend on **tier/SKU** and service version; check feature availability before finalizing designs. For Front Door Standard/Premium, never copy guidance written for legacy Front Door (classic) verbatim.

In some architectures, Front Door sits in front of Application Gateway. In that setup, define clearly **which layer enforces WAF**, the network boundaries, and the purpose of each policy to avoid overlapping rules that are hard to operate. Having two WAF layers does not automatically increase security if the origin remains directly reachable or policies conflict.

### Platform Selection Process

1. **User locations:** one internal region or the global Internet?
2. **Backend locations:** inside a VNet, App Service, multi-region, or hybrid?
3. **Availability and routing needs:** regional distribution only, or global origin failover/routing?
4. **Security requirements:** which managed rules, bot protection, rate limiting, logging, and customization are needed?
5. **Cost and operations:** gateway/edge service fees, request volume, data transfer, logs, redundancy, and staffing.
6. **Product limits:** SKU, region, rule set availability, and feature support must be verified for the target environment.

## 3. Components of a WAF Policy

A **WAF policy** bundles security settings so they can be managed independently from most of the gateway or Front Door configuration. Key components:

| Component | Meaning | Decisions Required |
|---|---|---|
| Policy mode | Detection or Prevention | Observe only or block based on evaluation results |
| Managed rule sets | Provider-maintained rule collections | Choose supported rule set and version |
| Custom rules | User-defined rules with conditions and priorities | Block/allow/policy actions by IP, URL, rate, etc. |
| Rule exclusions | Controlled exclusion of specific request parts from managed rule inspection | Reduce false positives with documented evidence |
| Request body/file limits | Settings and limits for inspecting request bodies and uploads | Ensure compatibility with APIs and file uploads |
| Policy association | Scope where policy applies | All traffic or only specific hostnames/routes/listeners |
| Diagnostics | Logs, metrics, alerts | Detect attacks and user impact |

A policy that is not associated with the right traffic entry point will not protect the application even if the policy itself succeeded in provisioning. Always verify the full **client → gateway/Front Door → backend** path and policy association scope.

### Detection vs. Prevention

| Mode | Typical Behavior | When to Use |
|---|---|---|
| **Detection** | Logs requests matching rules without blocking them solely for managed-rule detection | Observation and false-positive tuning phase |
| **Prevention** | Enforces blocking actions per policy/rules | After testing and when ready to protect production |

**Important:** Do not interpret Detection mode as disabling all custom rules in every scenario or product version. The behavior of **custom rule actions**, managed rules, and policy mode can vary across WAF platforms. During testing, verify actual logs and HTTP responses for your exact product and policy.

Switching straight to Prevention on systems with complex requests (JSON APIs, uploads, payment callbacks) risks disrupting legitimate users. Recommended workflow: gather a baseline in Detection mode, inspect logs, tune exclusions, test in a controlled manner, and then enable Prevention with a rollback plan.

## 4. Managed Rules: Protecting Against Common Attack Patterns

Managed rules are protection rulesets maintained by the provider. On Azure Application Gateway, common rulesets derive from the **OWASP Core Rule Set (CRS)** and Microsoft-provided rulesets depending on platform/version. On Azure Front Door, supported rulesets depend on the SKU and service tier. Never assume rule names, versions, rule IDs, or update behavior are identical across the two products.

Risk categories WAF helps detect include:

- **SQL injection (SQLi):** patterns attempting to inject SQL expressions into URLs, queries, or bodies.
- **Cross-site scripting (XSS):** payloads resembling dangerous script markup in requests.
- **Local/remote file inclusion and path traversal:** patterns trying to read or reference unintended files.
- **Protocol anomalies:** malformed requests, invalid headers, or evasion techniques.
- **Command injection and other application exploits:** depending on the specific ruleset and request parser.
- **Bot-related patterns:** only when the policy/SKU supports appropriate bot protection.

### Anomaly Scoring Mechanism

Many managed rulesets use **anomaly scoring**: a single request can match one or more rules, each match adds points, and the final action depends on thresholds and policy settings. Never assume every rule entry in a log means the request was rejected.

Illustrative example:

~~~text
Request: GET /search?q=...
  |
  +-- Managed rule A: matched, anomaly signal recorded
  +-- Managed rule B: matched, additional signal recorded
  |
  +-- Policy evaluation outcome
        |
        +-- Detection: log evaluation results
        |
        +-- Prevention: block if blocking conditions are met
~~~

When investigating, inspect the **action**, **rule ID**, **message**, **transaction/request correlation**, and policy context rather than just counting matched rule log lines.

### Updating Managed Rules

New ruleset versions improve detection coverage but can also change behavior for valid traffic. To upgrade safely: verify support, test in staging, compare block/false-positive counts, schedule the rollout, and keep a rollback plan. Avoid blindly auto-upgrading rulesets without testing critical flows.

## 5. Custom Rules: Enforcing Organization-Specific Requirements

**Custom rules** are rules you define for specific conditions, such as:

- Restricting access to an admin area to approved corporate IPs.
- Blocking an IP range flagged as malicious by the security team.
- Applying rate limiting on endpoints prone to abuse where supported by the platform.
- Adding controls based on URI, header, method, or other match variables.

A custom rule typically has a **priority**, matching conditions, and an action. Available actions vary by platform—commonly including **Allow** or **Block**, and potentially **Log**, **Redirect**, challenge, or rate limiting on specific SKUs/configurations. Always check the options available for your exact policy before designing around them.

### Example Rule Protecting an Admin Path

Suppose the admin interface lives at **/admin** and only staff coming from corporate egress IPs should reach it. You can design a custom rule condition such as:

~~~text
If the request path starts with /admin
and the client IP address is not in the approved egress range
then Block.
~~~

This is a **logical description**, not a finished product configuration. You must verify URL/path matching semantics, normalization, trusted client IP headers/extraction, and rule evaluation order in your WAF platform. In reality, an administrator may connect over VPN or Zero Trust Access with changing IPs; never rely on an IP allowlist as the sole authentication control. The application must still enforce sign-in and admin role checks.

### Example Rate Limiting

A public API **/api/search** is receiving excessive requests from a bot. If your WAF platform/tier supports rate limiting, apply thresholds per supported client or key to curb abuse. Do not set overly tight per-IP thresholds if many legitimate users share a corporate NAT or proxy; tune limits using observed telemetry, latency, and business goals.

WAF rate limiting does not replace API backend quotas/rate limits, since user identities, API keys, and subscription tiers are typically known accurately only by the application.

### Order and Impact of Custom Rules

Higher-priority rules can evaluate before lower-priority rules; certain **Allow** actions may bypass subsequent inspection steps depending on product behavior. Consequently, an overly broad Allow rule can inadvertently create a wide exemption that neutralizes managed rules for that traffic. Favor narrow conditions, peer review, and testing with both suspicious and valid requests.

## 6. Reference Architecture: WAF for an Azure Application

A company deploys an e-commerce web app consisting of frontend, API, and database tiers in Azure. Requirements: public HTTPS, protection against common HTTP attack patterns, admin page protection, logging for investigations, and no direct client access to the backend API.

~~~text
                    Internet
                       |
                DNS: shop.example
                       |
            +----------v-----------+
            | Front Door WAF       |
            | or App Gateway WAF   |
            +----------+-----------+
                       |
                 HTTPS to origin
                       |
          +------------v-------------+
          | Web frontend / API       |
          | AuthN / AuthZ / logging  |
          +------------+-------------+
                       |
                 Internal Data
             (not directly public)
~~~

In this model, WAF protects the **inbound HTTP path**. Other controls must still be implemented:

1. Backends verify identity and permissions for each API/resource.
2. Configure TLS for client → WAF and, when needed, WAF → origin; manage certificate lifecycles.
3. Restrict direct access to the origin via network controls and appropriate request source verification.
4. Apply NSGs, private networking, and least privilege wherever possible.
5. Send WAF/access logs to monitoring tools and alert on blocks, errors, and latency.
6. Monitor health probes/backend health to avoid confusing app outages with WAF blocks.

### Critical Issue: Origin Bypass

If a public website sits behind Front Door WAF yet the underlying App Service or public load balancer still accepts direct Internet requests, attackers can bypass the WAF by targeting the origin address directly instead of the protected hostname.

For Front Door, apply origin access controls appropriate to the backend type—such as **Private Link where supported**, source network restrictions, and **verifying the Front Door instance identity** per product documentation. Allowing only a shared edge network IP range does not guarantee requests came specifically through your Front Door profile. Never trust an unverified header from the Internet without locking down direct origin access.

For Application Gateway, place backends in a private network or restrict inbound rules so only authorized ingress components can connect, matching the real topology.

## 7. Creating a WAF Policy in the Azure Portal

The following example uses **Application Gateway WAF_v2**. If choosing Front Door, design principles are similar, though portal menus, associations, and rule options differ.

### Step 1: Prepare

- Have an authorized subscription and resource group.
- Have permissions to create/edit WAF policies and associate them with the gateway.
- Have a WAF-capable Application Gateway; if not yet deployed, practice only design or an unassociated policy to avoid unintended gateway infrastructure costs.
- Know the hostnames, API paths, access rules to protect, upload sizes, and special application flows.

### Step 2: Create the Policy

1. Open [Azure Portal](https://portal.azure.com) and search for **Web Application Firewall policies** or the Application Gateway WAF policy section.
2. Select **Create**, specifying subscription, resource group, location, and policy name such as **wafp-shop-prod**.
3. Choose the policy type for **Application Gateway** and select a supported managed ruleset/version.
4. Set **Detection** mode for the initial observation phase.
5. Verify request body inspection, upload limits, and other settings matching your application profile.
6. Create the policy, then reopen it to verify saved values.

### Step 3: Associate the Policy

Associate the policy with the Application Gateway or supported listener/path scopes matching your ingress topology and product inheritance rules. After association, confirm the gateway uses the new policy and is not overridden by a policy at another scope.

### Step 4: Add a Custom Rule

For instance, create a rule blocking access to **/admin** from unapproved sources. In the Portal, open custom rules, provide a clear name, assign priority, add conditions, and select **Block**. Align conditions with how your application handles URL encoding, proxies, and client IP extraction.

In production, before enabling Block, verify that corporate IPs or automated system identities still connect cleanly—including health probes, ops tools, and emergency procedures.

### Step 5: Transition to Prevention in a Controlled Way

After reviewing logs in Detection mode, test sign-in, checkout, search, uploads, and API callbacks. Resolve false positives following Section 10. Switch to **Prevention** only with test evidence, an active monitoring window, and a rollback plan.

**Note:** Portal UI and managed ruleset catalogs change across products and SKUs. These steps explain configuration intent; exact menu labels may differ in your current Portal version.

## 8. Inspecting Policies and Related Resources with Azure CLI

Azure CLI lets you list and inspect policies. Command groups for **Application Gateway WAF policy** differ from Front Door commands; avoid mixing syntax between the two platforms.

First confirm your account and subscription:

~~~bash
az login
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

To list existing Application Gateway WAF policies in a resource group:

~~~bash
az network application-gateway waf-policy list \
  --resource-group <RESOURCE_GROUP> \
  --output table
~~~

View details of a created policy:

~~~bash
az network application-gateway waf-policy show \
  --resource-group <RESOURCE_GROUP> \
  --name <WAF_POLICY_NAME> \
  --output json
~~~

Inspect fields such as policy settings, managed rules, custom rules, ID, and association scopes if returned by your CLI version. Some association links reside inside the Application Gateway/listener configuration, so inspect the attached gateway as well.

View the Application Gateway and its overall configuration:

~~~bash
az network application-gateway show \
  --resource-group <RESOURCE_GROUP> \
  --name <APPLICATION_GATEWAY_NAME> \
  --output json
~~~

For Front Door Standard/Premium, inspecting WAF policies requires the **Front Door WAF** and security policy association command groups; do not use Application Gateway commands for Front Door. Before automating rule creation or edits, run `az ... --help` to confirm flags for your installed Azure CLI version. Do not treat **show/list** commands as proof that requests are protected; you still must verify associations, send test traffic, and inspect logs.

## 9. Logging, Metrics, and Investigating WAF Events

A WAF policy remains effective over time only when operations teams know what is being blocked, whether valid traffic is affected, and how attack sources evolve.

### Data Types to Monitor

| Data | Operational Meaning |
|---|---|
| WAF firewall logs | Rule ID, action, URI, client IP, match reason, and correlation/transaction ID per service |
| Access logs | HTTP status, latency, hostname, backend, and request context |
| Metrics | Request counts, blocked counts, gateway/origin errors, health, and latency |
| Application logs | Business errors, trace IDs, user journeys, and backend processing status |
| Azure Activity Log | Management-plane changes to policies or gateways |

To collect logs for analysis, configure **Diagnostic settings** on the Application Gateway or Front Door resource, select the appropriate categories, and route them to a **Log Analytics workspace** or approved destination. In Log Analytics, table names depend on whether you choose **resource-specific** mode or **AzureDiagnostics** mode and on the service type.

### Kusto Query Language (KQL) Examples

For Application Gateway when logs route to the resource-specific **AGWFirewallLogs** table, you can start with:

~~~kusto
AGWFirewallLogs
| where TimeGenerated > ago(1h)
| summarize Requests = count() by Action, RuleId
| order by Requests desc
~~~

To inspect recent individual events:

~~~kusto
AGWFirewallLogs
| where TimeGenerated > ago(30m)
| order by TimeGenerated desc
| take 30
~~~

If the workspace uses **AzureDiagnostics**, a starter query is:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1h)
| where Category == "ApplicationGatewayFirewallLog"
| order by TimeGenerated desc
| take 30
~~~

For **Azure Front Door Standard/Premium**, logs use different table/category names. When using resource-specific tables with ingested data, explore events with:

~~~kusto
FrontDoorWebApplicationFirewallLog
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 30
~~~

These are sample queries, **not a guarantee** that every workspace has these exact tables populated. Confirm exact table names, columns, and categories from Diagnostic settings and current service schemas. If a query reports a missing table, check whether diagnostics are enabled, which destination is configured, and whether recent events exist.

### Correlating Logs During an Incident

When users report rejected requests, capture:

1. Timestamp with timezone, hostname, and URL path (excluding secrets or sensitive payloads).
2. HTTP status code and correlation/transaction ID if available.
3. WAF action, rule ID, policy ID, and the request element that matched (storing only the minimum necessary).
4. Access logs and backend health to distinguish a **WAF block** from an **origin 403/500/502**.
5. Recent changes in policies, managed rules, app deployments, and traffic patterns.

Never paste access tokens, passwords, session cookies, or PII-bearing payloads into public tickets. WAF logs can capture URLs, query strings, or sensitive artifacts; enforce log access RBAC, retention, and masking per data governance policies.

## 10. Handling False Positives While Preserving Protection

A **false positive** is a legitimate request flagged by WAF as malicious. For example, a content management system allows editors to save HTML snippets; a managed rule may treat script-like markup as XSS. Blocking everything could break legitimate administrative workflows.

Safe handling workflow:

1. **Verify impact:** collect the path, representative valid request, user journey, action, and rule ID.
2. **Investigate root cause:** compare the matched rule against actual input and how the application handles/escapes that content.
3. **Assess risk:** does that raw content truly need to be sent, or should the app use a safer format?
4. **Pick a narrow exclusion:** exclude only the specific parameter name, header, cookie, or location supported by the product; scope it to the specific rule or rule group whenever possible.
5. **Keep other controls intact:** maintain authentication, authorization, and input validation/encoding inside the app.
6. **Test:** confirm legitimate requests succeed while malicious variants are still caught.
7. **Track:** record the ticket, approver, justification, and review date for the exclusion.

**Avoid doing this:** disabling the entire managed ruleset because of one failing endpoint; creating a custom Allow rule for all requests to `/api`; leaving all of production in Detection mode indefinitely; or disabling request body inspection without understanding the risk.

### Example of a Reasonable Exclusion

Endpoint **POST /content/save** includes field **articleHtml** storing HTML from a controlled editor. Logs show a specific managed rule consistently matches that field on valid requests. Once the app team confirms inputs are controlled and outputs are properly sanitized/encoded, consider an exclusion scoped to **that specific field and the false-positive rule**, rather than disabling all checks on the endpoint.

Exclusion capabilities, per-rule-ID scoping, selector matching, and evaluation order differ between Application Gateway and Front Door. Only configure exclusions supported in the exact way needed by your active policy/tier.

## 11. Optimizing Request Body, Uploads, and APIs

A modern site often handles image uploads, document uploads, large JSON APIs, webhooks, and multi-field bodies. Configure WAF inspection to match real limits and traffic patterns.

- **Request body inspection:** enable according to protection needs, while verifying behavior on oversized requests or unsupported content types.
- **File uploads:** review size limits, dedicated upload endpoints, malware scanning for file contents, and secure storage; WAF is not an antivirus scanner.
- **JSON/XML/form data:** understand which body, query, header, and field locations managed/custom rules inspect.
- **Compression/encoding:** verify parser capabilities for your service version; avoid assuming WAF inspects every byte of every payload.
- **Webhooks:** remember payment/partner webhooks have unique payloads, signatures, and retry rules; WAF policy does not replace webhook signature verification.
- **Streaming/WebSocket:** confirm gateway/Front Door support and which traffic portions WAF can actually inspect.

Byte limits, upload caps, and oversized-request behavior vary by platform, tier, and setting. Never copy a default limit from outdated docs into a new system; verify current specifications before going to production.

## 12. Production WAF Rollout Roadmap

Enforcing WAF is a network and security change that can affect live users. Plan clear milestones:

| Phase | Activities | Exit Criteria |
|---|---|---|
| **Design** | Select ingress, identify origins, inventory hostnames/paths, define logging | Architecture, SKU, cost, and policy approved |
| **Preparation** | Enable TLS, create policy, configure managed rules, restrict admin RBAC | Traffic routes through WAF; origin is not left exposed |
| **Observation** | Use Detection where appropriate, enable diagnostics, capture request/error baselines | Logs flowing; representative valid traffic captured |
| **Tuning** | Analyze false positives, apply narrow exclusions, test applications | Critical user flows unaffected |
| **Controlled Enforcement** | Switch to Prevention in a change window, monitor alerts closely | No unexpected spike in business errors; expected WAF blocks |
| **Operations** | Review rulesets, incidents, exceptions, certificates, and costs | Named owners, review cadence, and incident runbook in place |

During rollout, prepare a concrete rollback procedure: who is authorized to change the policy, where approvals live, how to revert to a tested configuration, how to confirm traffic recovery, and how to avoid exposing the origin directly during remediation.

### Key Metrics to Track

- Blocked requests over time, by rule ID and endpoint.
- HTTP 4xx/5xx error rates, especially before and after policy changes.
- Verified false-positive rate and resolution time.
- p95/p99 latency, backend health, and traffic shifts.
- Traffic by client IP/geography at the granularity needed for investigation.
- Log ingestion volume, retention, and WAF/gateway/edge costs.

Do not optimize by aiming for **as many blocked requests as possible**. High blocks may reflect real attacks, overly sensitive tuning, or application bugs. The goal is reducing risk while preserving legitimate user experience.

## 13. Common WAF Troubleshooting

| Symptom | Possible Causes | How to Check |
|---|---|---|
| WAF policy created successfully, but no logs or blocks appear | Policy not associated with ingress path, traffic bypasses WAF, or diagnostics disabled | Verify association, DNS/routing, requests hitting WAF, and log destination |
| Users see 403 after enabling Prevention | Blocked by managed/custom rule, or origin app returns 403 itself | Compare WAF firewall logs with access/origin logs via correlation ID |
| A JSON API or file upload is blocked | False positive, body inspection, or request size limit | Find rule ID, inspect valid payload, apply narrow exclusion |
| In Detection mode yet requests are still blocked | Custom rule action, block at another layer, or platform-specific behavior | Check actual action, rule scope, NSG/origin, and policy mode |
| WAF logs missing from KQL queries | Diagnostic settings not sending logs, wrong table/category, or no traffic yet | Check Log Analytics destination and matching table schema |
| Backend returns 502/504 | Origin connection failure, health probe, TLS, DNS, or firewall issue | Check backend health, origin access logs, and network path |
| Clients still reach origin bypassing WAF hostname | Public origin not locked down | Configure origin access restrictions / Private Link and verify source |
| Allow rule lets malicious requests through | Rule priority or action skips remaining checks | Narrow conditions, review rule order, and retest |
| Many new blocks appear after ruleset upgrade | Updated ruleset changed match behavior | Compare pre/post logs, review rule IDs, roll back per procedure |
| Website slows down after WAF changes | Added inspection overhead, routing change, or backend bottleneck | Monitor latency at edge/gateway and origin; check load and capacity |

When recovering from a production incident, do not immediately disable the entire WAF. Identify the offending policy, rule, or scope, consider a narrow temporary adjustment under approved change control, and record every change.

## 14. Hands-On Exercise: Safely Designing and Testing WAF

You can complete most of this exercise as a design and Portal walkthrough without provisioning billable Application Gateway or Front Door instances. If you have a sandbox and proper permissions, apply the configuration only to an application **you own or are authorized to test**.

### Scenario

The application **shop.lab.example** has three areas:

- **/**: public shopping website.
- **/api/search**: product search with JSON/query requests and relatively high traffic.
- **/admin**: administrative portal requiring login, used only from approved source networks.

The engineering team wants to start in Detection mode to gauge managed rule accuracy, then move to Prevention. All inbound application traffic must pass through WAF; the backend must not accept direct Internet connections.

### Part A: Design the WAF Policy

Complete the table:

| Component | Recommended Configuration | Rationale |
|---|---|---|
| Ingress | App Gateway WAF_v2 or Front Door per topology | Positions WAF inline in front of origin |
| Managed rules | Supported and tested ruleset | Protects against common web risk categories |
| Initial mode | Detection | Observe false positives safely |
| Post-rollout mode | Prevention | Enforce blocking policy |
| /admin | Custom rule blocking unapproved sources, combined with Entra ID/roles | Reduces attack surface without replacing auth |
| /api/search | Rate limit per platform support and observed baselines | Curbs abuse without blocking users behind shared NAT |
| Logging | WAF/access diagnostics to Log Analytics | Investigate by action/rule/URI |
| Origin | Restrict direct paths to backend | Prevent WAF bypass |
| Exclusions | Added only after proving false positives | Preserves protection effectiveness |

### Part B: If You Have an Azure Lab Environment

1. Choose a dedicated lab subscription and resource group; verify gateway/Front Door, log, public IP, and related costs before deploying.
2. Deploy a test web app or use an approved test backend.
3. Create a policy matching the platform and attach it to the ingress handling your lab hostname.
4. Enable managed rules and Detection mode; configure Diagnostic settings to an authorized workspace.
5. Send several valid requests to home, search, and sign-in pages; record status, latency, and logs.
6. If authorized to test in an isolated environment, send a **harmless** request containing a script-like string in the search parameter:

~~~bash
curl -i "https://shop.lab.example/api/search?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
~~~

7. Check whether a rule match is logged. **Not every ruleset will necessarily match this sample request**, and the request could also fail due to the app or another setting; do not infer results solely from HTTP status.
8. Correlate WAF logs by timestamp, URI, rule ID, and action. Only after understanding false positives and having a rollback plan should you test Prevention mode.
9. Resend valid requests to confirm normal business flows remain intact.
10. Clean up or revert lab resources per plan—including WAF policy, gateway/Front Door, origin, public IPs, and diagnostics—if no longer needed.

Never test attack payloads against external websites, production environments, or unauthorized systems. Use example domains and synthetic data, and never record real tokens or cookies in logs or documentation.

### Part C: Verify Design Requirements

| Scenario | Expected Outcome |
|---|---|
| Client sends valid request to homepage | Processed normally by the application |
| Request with anomalous pattern matches managed rule in Detection | WAF evaluation trail recorded; do not assume it was blocked |
| Request matches blocking rule in Prevention | Enforced according to corresponding action/policy |
| Unauthorized user accesses /admin even if request passes WAF | Rejected by application due to missing permissions |
| User hits origin directly to evade WAF | Rejected by network controls / source validation at origin |
| Valid upload API triggers false positive | Rule ID captured and narrow exclusion reviewed |
| WAF logs do not reach workspace | Runbook exists to verify diagnostics, destination, and schema |
| New policy breaks critical functionality | Accountable owner and rollback procedure ready |

### Self-Check Exercises

1. Why can an NSG opening TCP 443 not replace a WAF for inspecting HTTP requests?
2. Which scenario would lead you to choose Front Door WAF instead of Application Gateway WAF?
3. How do Detection and Prevention differ? Why should you avoid turning on Prevention immediately without prior observation?
4. How do managed rules differ from custom rules?
5. Why does a single matched-rule log line not necessarily mean the request was blocked?
6. What unintended impact could an overly broad Allow rule for **/api/** cause?
7. When Front Door WAF protects a site, why must you lock down direct access to the origin?
8. When users report a 403 error, which logs do you compare to tell whether WAF or the application caused it?
9. Why is an exclusion scoped strictly to the **articleHtml** field safer than disabling the entire ruleset?
10. Can WAF replace per-record access control in a SaaS API? Explain.

## 15. Checklist Before Using WAF in Production

- [ ] All critical public hostnames/routes pass through WAF with the proper policy association.
- [ ] Origins cannot be accessed directly outside controlled paths; TLS from client to ingress and ingress to origin is configured properly.
- [ ] Appropriate SKU/tier and supported managed ruleset selected; request body/upload limits fit the app.
- [ ] Managed rules tested against key flows; exclusions backed by evidence and narrowly scoped.
- [ ] Custom rules have clear priorities and actions; Allow rules do not unintentionally bypass other checks.
- [ ] Diagnostics are active; operations teams have access to required logs, dashboards, and alerts.
- [ ] Baseline captured for latency, HTTP errors, and block counts for pre/post-rollout comparison.
- [ ] Detection → Prevention rollout plan, rollback steps, and owner documented.
- [ ] Application still enforces authentication, authorization, input validation, output encoding, and secrets management.
- [ ] Gateway/edge, traffic, log, and retention costs reviewed with periodic governance checks scheduled.

## 16. References

- [What is Azure Web Application Firewall?](https://learn.microsoft.com/azure/web-application-firewall/overview) — overview of Azure's WAF platform.
- [Web Application Firewall on Azure Application Gateway](https://learn.microsoft.com/azure/web-application-firewall/ag/ag-overview) — WAF architecture and capabilities on Application Gateway.
- [Web Application Firewall on Azure Front Door](https://learn.microsoft.com/azure/web-application-firewall/afds/afds-overview) — edge WAF for Azure Front Door.
- [Application Gateway WAF policies](https://learn.microsoft.com/azure/web-application-firewall/ag/policy-overview) — WAF policy structure and scopes.
- [Application Gateway WAF custom rules](https://learn.microsoft.com/azure/web-application-firewall/ag/custom-waf-rules-overview) — custom rules and conditions.
- [Monitor Azure Application Gateway](https://learn.microsoft.com/azure/application-gateway/monitor-application-gateway) — metrics, logs, and diagnostic settings.
- [Azure CLI: application-gateway waf-policy](https://learn.microsoft.com/cli/azure/network/application-gateway/waf-policy) — CLI syntax to inspect and manage WAF policies.

**Conclusion:** WAF is a vital HTTP/HTTPS protection layer, but its effectiveness depends on placement, rule tuning, observability, and preventing origin bypass. Use WAF as one layer within defense-in-depth, test against representative traffic before blocking, keep exclusions minimal, and always maintain strong security inside the application itself.
