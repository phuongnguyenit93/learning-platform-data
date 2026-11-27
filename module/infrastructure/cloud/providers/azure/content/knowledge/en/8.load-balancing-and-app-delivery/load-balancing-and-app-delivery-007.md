# DNS Routing with Azure Traffic Manager

## 1. Context and Objectives

In the Microsoft Azure ecosystem, a web application can be deployed simultaneously across multiple regions to serve users in different areas and remain available when one deployment location fails. For example, a company might run one instance in Southeast Asia and another in East Asia. Both have public endpoints, yet users only need to remember one domain name: **app.example.com**.

The question is: when users access the shared domain name, how does the system pick the right destination, detect unhealthy endpoints, and change name resolution results when needed?

**Azure Traffic Manager** solves this problem at the **DNS** layer. Traffic Manager answers DNS queries according to the chosen routing method and endpoint monitoring status. After receiving the DNS answer, the user's device connects **directly to the application endpoint**.

After this lesson, you will be able to:

1. Explain the difference between DNS routing and traffic-forwarding proxies/load balancers.
2. Identify profiles, endpoints, routing methods, health probes, and DNS TTL.
3. Choose the right routing method for priority failover, proportional split, latency, or geographic region.
4. Configure a Traffic Manager profile using the Azure Portal and Azure CLI.
5. Connect a custom domain, design HTTPS, and verify DNS resolution.
6. Test failover, understand DNS caching limits, and troubleshoot common incidents.
7. Integrate Traffic Manager with Azure compute, networking, monitoring, security, and cost control.

## 2. Traffic Manager Operates at the DNS Layer

Traffic Manager **does not receive and forward individual HTTP requests** like a reverse proxy. It operates as follows:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant R as Recursive DNS resolver
    participant T as Azure Traffic Manager DNS
    participant A as Endpoint A
    participant B as Endpoint B
    U->>R: Ask for IP of app.example.com
    R->>T: Query Traffic Manager domain name
    T-->>R: Answer per routing method and health
    R-->>U: Return DNS answer cached per TTL
    U->>A: Connect directly via HTTPS to selected endpoint
    Note over U,A: Traffic Manager is not in the HTTP data path
    T->>A: Health probe per configuration
    T->>B: Health probe per configuration
~~~

A typical flow:

1. The user enters **https://app.example.com**.
2. The organization's DNS record points this name to **tm-prod-app.trafficmanager.net**.
3. The recursive DNS resolver queries Traffic Manager's DNS system.
4. Traffic Manager evaluates the routing method, enabled endpoints, and monitoring status to choose a DNS answer.
5. The resolver caches the answer per TTL rules and returns it to the client.
6. The browser connects directly over the Internet to the resolved endpoint, such as an Azure App Service.
7. When an endpoint fails, Traffic Manager can alter **subsequent DNS answers** per policy.

Key takeaway: Traffic Manager controls **which address DNS returns**; it does not migrate already-open TCP/HTTPS sessions and does not decrypt application traffic.

### 2.1. Benefits of Operating at the DNS Layer

- Supports endpoints across multiple regions, multiple Azure subscriptions, or even outside Azure as long as they have suitable public addresses.
- Adds no extra proxy hop in the application data path.
- Manages failover priorities and several traffic-distribution policies from a single centralized configuration.
- Works with many DNS-reachable application types, provided endpoints and monitoring protocols are compatible.

### 2.2. Limitations to Keep in Mind

- Switchover speed is affected by **DNS TTL, recursive resolver caching, and client caching**.
- Already-connected sessions are not immediately moved by Traffic Manager to another endpoint.
- Does not provide TLS termination, WAF, cookie handling, session affinity, or HTTP path routing.
- Does not turn a service with only a private VNet IP into a public endpoint.
- Does not replace data synchronization, multi-region deployment, or resilient application design.

Therefore, Traffic Manager fits **DNS-level destination steering**, while a truly fault-tolerant multi-region application still needs a data layer, session handling, and independent regional operation.

## 3. Distinguishing Traffic Manager from Other Load-Balancing Services

Azure provides multiple application delivery options. Pick the right service based on the problem to solve:

| Service | Primary layer and function | Typical use case |
|---|---|---|
| **Azure Traffic Manager** | DNS-based routing to public endpoints | Selecting regions/endpoints by priority, weight, geography, or expected latency |
| **Azure Front Door** | Global HTTP/HTTPS application delivery operating as an edge reverse proxy | Web app acceleration, TLS termination, WAF, and L7 routing |
| **Azure Application Gateway** | L7 application load balancer at Azure regional scope, optional WAF | Host/path routing and HTTP/HTTPS load balancing for workloads |
| **Azure Load Balancer** | L4 TCP/UDP connection balancing in supported models | Distributing traffic to VMs or backend services at L4 |

For example, if the requirement is "users in a region should receive the healthiest application endpoint per DNS policy," Traffic Manager may fit. If the requirement is "inspect HTTP paths and send **/api** and **/images** to different backends," you need an L7 service like Front Door or Application Gateway.

They can be combined: Traffic Manager can point to endpoints backed by Application Gateway or application services. Still, each added layer must have a clear role to avoid routing paths that are hard to monitor.

## 4. Core Configuration Components

### 4.1. Traffic Manager Profile

The **Profile** is the resource managing the routing method, DNS name, endpoint monitoring, and endpoint list. When creating a profile, you pick a unique DNS name under the **trafficmanager.net** domain.

Example:

- Profile name: **tm-prod-app**.
- DNS name: **tm-prod-app.trafficmanager.net**.
- Routing method: **Priority**.
- DNS TTL: **60 seconds**.
- Monitor: **HTTPS**, port **443**, path **/health**.

The DNS name above is illustrative only; the prefix must be unused across the service.

### 4.2. Endpoint

An endpoint is a target that Traffic Manager can return in DNS answers. A profile can contain multiple endpoints with individual enabled/disabled states and parameters depending on the routing method.

### 4.3. Routing Method

The routing method governs how Traffic Manager picks one or more endpoints for a DNS query. Common methods include **Priority, Weighted, Performance, Geographic, MultiValue**, and **Subnet**.

### 4.4. Health Monitoring

Traffic Manager actively probes endpoints using HTTP, HTTPS, or TCP to detect unavailable targets. Probe-observed health affects endpoint selection in subsequent queries.

### 4.5. DNS TTL

**Time to Live (TTL)** is the duration a DNS answer may remain cached per DNS standards. A short TTL gives resolvers a chance to re-query sooner, but does not make failover instantaneous.

## 5. Endpoint Types

| Endpoint type | Description | Example |
|---|---|---|
| **Azure endpoint** | Public Azure resource of a type supported by Traffic Manager | A supported Azure App Service or Public IP resource |
| **External endpoint** | Public FQDN or IP address of a service outside Azure or an endpoint not declared as an Azure endpoint | Application in a datacenter or another cloud provider |
| **Nested endpoint** | Another Traffic Manager profile used as an endpoint inside the current profile | Global profile selecting regional or fallback profiles |

An **Azure endpoint** is typically referenced by the supported resource's ID; an **external endpoint** has a public DNS name or public IP target. When using external endpoints with the **Performance** method, declare an appropriate **endpoint location** so the algorithm has a basis for evaluation.

Endpoints must actually be reachable over the required network and answer the configured health probe. **Traffic Manager is not used to return Private Endpoint private IPs or provide access to an internal-only VNet app.** For private access, use corresponding private DNS/networking solutions.

### 5.1. Endpoint Status vs. Monitor Status

- **Endpoint status** reflects whether the endpoint is enabled to participate in routing.
- **Monitor status** reflects the health status observed by service monitoring.

An endpoint can be enabled in configuration yet marked unhealthy by monitoring. Conversely, an intentionally disabled endpoint will not be selected for traffic even if the backend app is still running.

## 6. Six DNS Routing Methods

### 6.1. Priority — Primary and Standby Failover

The **Priority** method chooses the healthy endpoint with the highest priority order. **Smaller priority numbers mean higher precedence.**

Example:

| Endpoint | Priority | Meaning |
|---|---:|---|
| App in Southeast Asia | 1 | Primary |
| App in East Asia | 2 | Standby |

Under normal conditions, DNS steers traffic to the Priority 1 endpoint. When that endpoint is evaluated as unhealthy, Traffic Manager can return the Priority 2 endpoint.

Fits when data or cost requires an **active-passive** architecture and the business wants explicit control over which region is primary. However, the standby region must be fully operational rather than an empty endpoint.

### 6.2. Weighted — Proportional Distribution by Weight

The **Weighted** method selects endpoints based on configured weights.

Example:

| Endpoint | Weight | Expected relative share |
|---|---:|---|
| App version A | 80 | Approximately 80% of DNS decisions under matching conditions |
| App version B | 20 | Approximately 20% of DNS decisions under matching conditions |

**Do not interpret this table as exactly 80% and 20% of HTTP requests.** One recursive resolver can cache answers for many clients, and users send varying numbers of requests. Weights influence DNS selection, whereas actual request counts depend on caching, client count, session length, and application traffic.

Fits proportional DNS distribution or gradual traffic migration. For canary releases requiring exact per-request or per-user control, an L7 solution may be needed.

### 6.3. Performance — Selecting Lower Expected Network Latency

Traffic Manager uses network latency data between regions and endpoints to pick an appropriate target for the location inferred from the DNS query. This method aims to improve user experience for multi-region applications.

Example: users in Southeast Asia are typically directed to a favorable region based on network latency data, while users elsewhere may receive a different endpoint.

Notes:

- This is an **estimate based on network latency tables**, not a live RTT measurement for every HTTP request.
- Client location may be inferred from the recursive resolver; **EDNS Client Subnet** can improve accuracy where supported.
- Network configs, DNS resolvers, VPNs, or varying Internet paths can make choices differ from a user's physical location.
- External endpoints require an appropriate region location setting.

If the goal is improving multi-country experience, measure directly from user networks and consider CDNs, edge services, or L7 services where needed.

### 6.4. Geographic — Distributing by Mapped Geographic Region

**Geographic** maps users by country, state/province, or geographic region supported by the service to specific endpoints.

Example:

| Geographic group in design | Assigned endpoint |
|---|---|
| Market group in Asia | App Asia |
| Market group in Europe | App Europe |

Fits market segmentation or region-specific experiences. However, **DNS-based routing is not an absolute guarantee of a user's physical location or where data is stored**.

Important note: Geographic strictly honors region mappings. If the endpoint assigned to a region fails, Traffic Manager does not automatically fail traffic over to another region's endpoint as an organization might assume. If failover within the same geography is required, consider nested profiles and test the exact behavior.

### 6.5. MultiValue — Returning Multiple Addresses

**MultiValue** can return multiple healthy endpoints in a single DNS response when endpoints and configuration meet the method's requirements. Use cases typically involve external endpoints with valid IPv4/IPv6 addresses rather than hostname-only targets.

The application or client receives a set of addresses and handles selection/connection retries itself. This differs from Weighted, which steers DNS selection by weight.

Before using MultiValue, carefully check endpoint object limits and DNS client behavior, as not all profiles or backends fit.

### 6.6. Subnet — Mapping by Source IP Range

The **Subnet** method maps client IP ranges identified from DNS queries to corresponding endpoints. For example, an organization may want requests originating from certain ISP or partner network IP ranges to prefer a dedicated endpoint.

Things to keep in mind:

- The DNS server may see the recursive resolver's address or client subnet info passed via EDNS Client Subnet.
- A client using an intermediate DNS resolver may be classified differently from its direct HTTP source IP.
- This is not a user authentication mechanism, firewall, or IP-based content protection control.

**Summary of method selection:** choose **Priority** for primary–standby, **Weighted** for DNS ratios, **Performance** for expected lower-latency destinations, **Geographic** for regional mapping, **MultiValue** for multiple valid IPs, and **Subnet** for source IP-range mapping.

## 7. Two-Region Design: Example for an App Deployed in Asia

Suppose an e-commerce app has two independent deployments:

- **Endpoint A:** `app-sea.example.net`, hosted in Southeast Asia.
- **Endpoint B:** `app-ea.example.net`, hosted in East Asia.
- **Customer domain:** `app.example.com`.
- **Traffic Manager profile:** `tm-prod-app.trafficmanager.net`.

The **example.com** and **example.net** domains here are illustrative documentation names; during hands-on work, use real domains or endpoints you administer.

~~~mermaid
flowchart TD
    U[Customer opens app.example.com] --> DNS[Recursive DNS]
    DNS --> TM[Traffic Manager: tm-prod-app.trafficmanager.net]
    TM -->|Priority 1, healthy| A[App Southeast Asia]
    TM -->|Priority 2 when A unhealthy| B[App East Asia]
    U -->|Direct HTTPS per DNS answer| A
    U -.->|HTTPS after DNS failover| B
    A --> DA[(Region A data)]
    B --> DB[(Region B data)]
    DA <-.->|Data sync per architecture| DB
~~~

The diagram depicts two access flows at different times; it does not imply Traffic Manager replicates sessions or databases.

**Prerequisites for failover to be useful:**

1. Both Endpoints A and B can serve the required public hostname.
2. Both are authorized for production traffic and run compatible versions.
3. Data is replicated/recovered per application design with defined RPO/RTO.
4. Health endpoints detect failures that prevent an app instance from serving validly.
5. Custom domain and valid TLS certificates exist at both endpoints.
6. The app avoids storing sessions solely in one instance/region's memory or has a sound recovery strategy.
7. Operators measure actual cutover behavior including DNS caching and active sessions.

If a standby app exists without ready data, DNS switching to region B will still cause user errors.

## 8. How Do Health Probes Work?

Traffic Manager periodically checks endpoints using the configured protocol. Typical settings to choose:

| Setting | Function | Example |
|---|---|---|
| **Protocol** | Connection type used for probing | HTTPS |
| **Port** | Application port | 443 |
| **Path** | HTTP/HTTPS path expected to respond successfully | /health |
| **Probing interval** | Time between checks | Per supported mode and feature |
| **Timeout** | Probe response wait limit | Per configured value |
| **Tolerated failures** | Number of consecutive failed checks before marking unhealthy | Per sensitivity policy |
| **Expected status codes** | Accepted HTTP status codes when supported/configured | E.g., HTTP 200 |

### 8.1. Designing the Health Endpoint

The **/health** endpoint should return a short, stable response representing the app's ability to accept new requests.

Meaningful examples:

- HTTP 200: application is ready for traffic per monitoring criteria.
- HTTP 503: application should not accept new traffic due to missing critical dependencies.

A regular HTML page always returning HTTP 200 can trick Traffic Manager into keeping an endpoint marked healthy even when payments or data reads are broken. Conversely, checking too many non-essential auxiliary services can cause unwanted failovers over minor glitches.

Distinguish:

- **Liveness:** the process is still running.
- **Readiness:** the deployment is eligible to accept real traffic.
- **Synthetic business check:** a deep check simulating critical business workflows.

Traffic Manager can only judge based on the configured probe type and criteria. The application team is responsible for designing an appropriate path and check logic.

### 8.2. HTTPS Probes and Certificates

When using HTTPS, endpoints must have TLS and host/certificates aligned with the architecture. Using an HTTPS probe does not mean Traffic Manager becomes the TLS termination point for end users.

Verify the hostname and HTTP Host header used by health probes, especially when backends host multiple domains on one endpoint. Some monitoring configs allow custom headers; confirm capabilities and values supported by your profile.

### 8.3. Monitoring States

The UI may display endpoints as **Online, Degraded, Disabled, CheckingEndpoint, Stopped**, or other relevant states depending on the situation.

Do not draw conclusions solely from the profile status. Inspect **endpoint status**, **monitor status**, probe path, response codes, and application logs. If every endpoint goes unhealthy, understand routing behavior and app design in that scenario; Traffic Manager cannot create a healthy application purely by changing DNS.

## 9. DNS TTL and Failover Time Limits

This is the most critical part when assessing recovery capability.

Suppose a profile has a **60-second** TTL. When endpoint A breaks, Traffic Manager needs time for probes to detect the failure, update state, and serve new DNS answers. Even then, some recursive DNS resolvers or applications may keep using A's cached address.

Conceptual timeline:

~~~text
t0: Endpoint A stops serving
    |
    +-- Health probes detect A is unhealthy
    |
    +-- Traffic Manager starts returning endpoint B for new DNS queries
    |
    +-- Recursive resolver / client caches expire and re-query
    |
    +-- New client connections gradually shift to B
~~~

**A 60-second TTL does not guarantee all users switch to B in exactly 60 seconds.** TTL is only one piece. Other factors include:

- Probe interval, timeout, and tolerated failure count.
- Caches inside DNS resolvers, operating systems, apps, or DNS libraries.
- Whether resolvers honor or override TTLs.
- Already-open TCP, TLS, WebSocket, or keep-alive sessions.
- Whether a client performs a fresh DNS lookup on reconnect.

Lower TTLs generally shorten cache lifetimes per design, but can raise DNS query volume and cost. Higher TTLs reduce query frequency while slowing endpoint transitions.

**Application RTO must be measured with real failover tests**, not calculated purely from TTL. Traffic Manager does not guarantee instant failover for all clients.

## 10. Preparation Before Creating a Traffic Manager Profile

Before configuring, ensure:

1. **At least two working public endpoints** if the goal is testing failover; each must answer HTTPS or the monitored protocol.
2. **Azure permissions** to create profiles and endpoints in the target resource group/subscription.
3. **Chosen routing method** matching requirements: standby priority, proportional split, or destination optimization.
4. **Consistent readiness/health path** tested directly on each endpoint.
5. **Verified domain name** owned by your organization with permission to edit DNS records.
6. **TLS and custom hosts configured** on every backend serving the shared hostname.
7. **Logging and alerting prepared** for the app, DNS routing, and endpoint health.
8. **Cost estimate** covering profiles, endpoints/monitoring, and DNS query volume.

When applications handle personal data or face data-residency mandates, evaluate backend regions, data storage/replication locations, and per-service policies. Choosing Geographic routing alone does not enforce legal data-residency requirements.

## 11. Creating a Profile via the Azure Portal

The example below uses **Priority** for a primary/standby deployment.

1. In the **Azure Portal**, search for **Traffic Manager profiles** and create a new profile.
2. Enter a profile name, e.g., **tm-prod-app**; choose subscription and resource group.
3. Set routing method to **Priority**.
4. Create the profile. Note the assigned DNS name under **trafficmanager.net**.
5. Open **Configuration** and set the desired DNS TTL, e.g., **60 seconds**.
6. Under endpoint monitoring, choose **HTTPS**, **Port 443**, **Path /health**, plus appropriate probe/expected-response settings.
7. Open **Endpoints** and add endpoint A with **Priority 1**.
8. Add endpoint B with **Priority 2**.
9. Confirm endpoints are enabled, targets are accurate, and monitoring transitions to an expected state.
10. Query **tm-prod-app.trafficmanager.net** to verify DNS answers before attaching the production domain.

When adding endpoints, choose **Azure endpoint** for supported Azure resources or **External endpoint** when targeting a public FQDN. Examples like **app-sea.example.net** in this guide are illustrative only; replace them with real targets when testing.

Never point production DNS to the profile before verifying health probes, TLS, network paths, and rollback plans.

## 12. Implementation with Azure CLI

Azure CLI provides commands for managing Traffic Manager. The example below demonstrates using **externalEndpoints** pointing to two live public hostnames. Run in an authorized test environment and replace all placeholders.

### 12.1. Sign In and Create Resource Group

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-traffic-lab \
  --location southeastasia
~~~

Traffic Manager is a global DNS routing service; the resource group location stores resource management metadata rather than dictating where all DNS queries are served.

### 12.2. Create Traffic Manager Profile

~~~bash
az network traffic-manager profile create \
  --resource-group rg-traffic-lab \
  --name tm-prod-app \
  --routing-method Priority \
  --unique-dns-name tm-prod-app \
  --ttl 60 \
  --protocol HTTPS \
  --port 443 \
  --path /health
~~~

The prefix **tm-prod-app** must be a unique available DNS name on Azure Traffic Manager. In a real lab, pick your own unique prefix to avoid colliding with someone else's profile.

### 12.3. Create Two External Endpoints

~~~bash
az network traffic-manager endpoint create \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --name app-primary \
  --type externalEndpoints \
  --target app-sea.example.net \
  --priority 1

az network traffic-manager endpoint create \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --name app-secondary \
  --type externalEndpoints \
  --target app-ea.example.net \
  --priority 2
~~~

If backends are supported Azure resources, use **azureEndpoints** with the target resource ID parameter instead of declaring hostnames as external endpoints. When using Performance routing with external endpoints, supply a supported location for routing.

### 12.4. Inspect Profile and Endpoints

~~~bash
az network traffic-manager profile show \
  --resource-group rg-traffic-lab \
  --name tm-prod-app \
  --output json

az network traffic-manager endpoint list \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --output table
~~~

Inspect DNS name, routing method, TTL, protocol/port/path, endpoint priorities, targets, endpoint status, and monitor status. If endpoints do not evaluate as Online, check the app/health URL, DNS, and firewalls before moving toward production.

**Note:** `example.net` has no live endpoints in this sample lab. Profile/endpoint creation commands only serve practical testing once replaced with real public hostnames running live apps.

## 13. Using a Custom Domain with Traffic Manager

Suppose your organization owns **example.com** and wants everyone to access:

**https://app.example.com**

Sample DNS configuration at your DNS provider:

~~~dns
app.example.com.  CNAME  tm-prod-app.trafficmanager.net.
~~~

After the change, resolution can flow as:

~~~text
app.example.com
    |
    +-- CNAME --> tm-prod-app.trafficmanager.net
                      |
                      +-- Traffic Manager returns selected target endpoint
                            |
                            +-- DNS resolver continues resolving to IP if needed
~~~

### 13.1. Root Domains and Subdomains

For subdomains like **app.example.com**, a CNAME is usually straightforward. At an **apex/root domain** like **example.com**, many DNS systems disallow standard CNAMEs because of conflicts with other records. When pointing an apex domain, check your DNS provider's **alias/ANAME/ALIAS** capability. Azure DNS supports alias records in supported scenarios.

Do not assume every DNS provider supports the same alias mechanism.

### 13.2. HTTPS and TLS Certificates

Traffic Manager only steers DNS; browsers still open TLS connections to **the selected endpoint**. Because users type **app.example.com**, backends must be configured to serve that hostname with valid TLS certificates.

Checklist:

1. Custom domain is bound/accepted on every backend.
2. TLS certificate is valid for the access name and renewed on time.
3. Backends handle the HTTP Host header and SNI properly.
4. No redirect loop exists between default hostnames and the custom domain.
5. Both primary and secondary serve the same application routes and health probes.

If endpoint A has a certificate for `app.example.com` while endpoint B only has a certificate for the service's default name, DNS failover to B will trigger TLS errors even though B shows Online under probe checks.

## 14. Testing DNS and Simulating Failover

### 14.1. Querying DNS

On a machine with DNS tools:

~~~bash
nslookup app.example.com

dig app.example.com CNAME
dig app.example.com A
dig tm-prod-app.trafficmanager.net
~~~

In Windows PowerShell:

~~~powershell
Resolve-DnsName app.example.com
Resolve-DnsName tm-prod-app.trafficmanager.net
~~~

What to verify:

- Does the CNAME point to the right Traffic Manager profile?
- Does the profile return the expected endpoint?
- Is a DNS resolver still caching an earlier result?
- Does the returned IP/FQDN match the real backend?

Never use results from **one machine and one query** to conclude all users reach the same endpoint. Recursive resolvers, geography, routing methods, and caches can produce different answers.

### 14.2. Testing Priority Failover

In a sandbox, a procedure might look like:

1. Configure A with Priority 1 and B with Priority 2; both must work.
2. Verify DNS selects A while A is healthy.
3. Induce a controlled fault on **A's health path** or make A fail readiness, strictly in a test environment.
4. Watch A's monitor status turn unhealthy per configured thresholds.
5. Issue fresh DNS queries to confirm answers switch to B.
6. Observe clients still using cached results and measure recovery time.
7. Restore A, verify Online status, and confirm Priority routing returns to primary once eligible again.
8. Record timestamps from when A failed to detection, DNS switch, and real user access to B.

In production, follow formal drill procedures and avoid breaking live apps without an approved plan.

### 14.3. Distinguishing Key Timestamps

- **Detection:** time for probes to confirm an endpoint is unhealthy.
- **DNS answer change:** moment Traffic Manager begins returning the alternate endpoint for eligible queries.
- **Resolver/client switch:** moment caches expire or refresh.
- **Application recovery:** moment users can complete business tasks on endpoint B.

These timestamps can be separated by noticeable gaps. Measure RTO by real end-user application experience and document your measurement method.

## 15. Weighted Routing for Canary or Gradual Migration

Suppose an organization prepares to shift an app from **v1** to **v2**:

1. Deploy v2 independently and verify its endpoint/health.
2. Configure Weighted routing across both endpoints, biasing weight toward v1.
3. Monitor error rates, latency, and app metrics—not just DNS query counts.
4. Increase v2's weight gradually as criteria pass.
5. Keep the ability to roll weight back to v1 if errors climb.

Steps like **90/10 → 70/30 → 50/50 → 0/100** express relative targets for DNS decisions, not exact guarantees of HTTP request or user percentages. Caching and long-lived sessions can skew actual ratios significantly.

If traffic must be split by user ID, cookie, header, or request path, use an application/L7 layer or dedicated release mechanism instead of relying on Traffic Manager Weighted routing.

## 16. Geographic Routing and Data Requirements

An organization with customers across regions may want to map European users to a European app and Asian users to an Asian app.

Geographic routing is part of user experience design or DNS steering, yet **does not by itself prove data compliance**. Data-residency requirements must examine:

- Where each endpoint stores its data.
- Whether databases, backups, replicas, and logs cross into other regions.
- Where downstream APIs, queues, and global services process data.
- Whether clients use DNS resolvers/VPNs causing inferred location to differ from actual location.
- Whether traffic is permitted to fail over to another region if the local endpoint fails.

If rules forbid shifting users to another region, build redundancy **within the allowed region**, potentially using nested profiles under suitable conditions. If cross-region failover is permitted, obtain explicit legal and operational sign-off.

## 17. Nested Profiles for Multi-Tier Routing Policies

One Traffic Manager profile can reference another profile via a **nested endpoint**, enabling layered routing policies.

Example:

~~~mermaid
flowchart TD
    ROOT[Global profile: Geographic] --> ASIA[Asia profile: Priority]
    ROOT --> EU[Europe profile: Performance]
    ASIA --> A1[App Asia primary]
    ASIA --> A2[App Asia secondary]
    EU --> E1[App Europe region 1]
    EU --> E2[App Europe region 2]
~~~

This design groups users by geography in the outer profile, then applies Priority/Performance inside each region to pick the right endpoint.

Trade-offs include extra profiles, health configurations, DNS behavior, and operational overhead. Verify:

- How the parent profile determines availability of a nested endpoint.
- Whether failover scope complies with data rules.
- TTL and caching interactions at every layer.
- Actual access paths when one or more endpoints fail.
- Nesting limits and Traffic Manager features at design time.

Do not assume nested profiles automatically solve every regional failover or data-redundancy scenario.

## 18. Securing the Traffic Manager Model

Because Traffic Manager handles only DNS, place security controls at other layers:

**DNS and administrative permissions:**

- Grant only necessary Azure RBAC permissions to create/edit profiles and endpoints.
- Audit changes to profiles, DNS zones, and custom domains.
- Protect admin accounts with Microsoft Entra ID, MFA/PIM where appropriate.
- Keep domain/DNS administration tightly controlled.

**Endpoints and applications:**

- Configure HTTPS on every backend; do not rely on Traffic Manager to encrypt traffic.
- Use WAF or appropriate application services when HTTP protection is needed.
- Configure firewalls/WAF so Traffic Manager health probes are handled properly; if restricting sources, use published Azure probe IPs or service tags kept up to date per current guidance.
- Protect origins from unauthorized access per app design; DNS routing does not hide backend addresses.
- Enforce application authentication/authorization at the proper layer.

**Data and availability:**

- Replicate or recover data under consistency rules with defined RPO/RTO.
- Keep standby backends updated, patched, and monitored on par with primary backends.
- Test session handling, caches, uploads, and transactions when users shift endpoints.

When firewalls block health probes, Traffic Manager can mark an endpoint unhealthy even while users can still reach the app. Distinguish monitor failures from actual application outages.

## 19. Monitoring, Alerting, and Operations

A multi-endpoint system should monitor **Traffic Manager**, **backends**, and **DNS/custom domains**.

| Layer | What to monitor |
|---|---|
| Traffic Manager profile | Routing method, TTL, monitor config, endpoint changes |
| Endpoint health | Online/Degraded/Disabled states and transition times |
| DNS | Resolution results across locations, DNS query volume, cache behavior |
| Backend | HTTP error rate, latency, CPU, connection counts, dependency errors |
| TLS/domain | Certificate validity, custom hostnames, DNS records |
| Governance | Azure Activity Log, configuration change history |
| Cost | Profile/endpoint counts, DNS queries, companion service costs |

Use Azure Monitor metrics and alerts exposed by Traffic Manager alongside per-backend application monitoring. For failover verification, multi-location external synthetic probes are valuable because they measure both DNS resolution and live HTTP/HTTPS serving.

An alerting policy might require:

- Primary endpoint continuously evaluated as unhealthy.
- Zero healthy endpoints remaining for the routing method.
- Backend app error rate rising after traffic shifts.
- TLS certificates nearing expiration.
- Endpoint or custom DNS changes outside maintenance windows.

Never assume DNS query count equals HTTP request count. One resolver can serve thousands of clients from cache without sending a new query to Traffic Manager for each request.

## 20. Common Troubleshooting

### 20.1. DNS Does Not Return the Expected Profile

Check CNAME or alias records, exact profile name, DNS zone permissions, and TTL/caching. Query both the default resolver and alternate resolvers when investigating; never draw conclusions from one single query.

### 20.2. Profile Returns a Down Endpoint

Check monitor protocol, port, path, Online/Degraded state, timeout, and tolerated failures. An endpoint might still return 200 on **/health** while real business logic fails. Cached DNS answers may also still point to the old endpoint.

### 20.3. Endpoint Marked Degraded Even Though Website Opens

Check whether a firewall/WAF blocks monitoring probes, wrong URL path, HTTP status code, Host header requirements, HTTPS config, or redirect loops. Inspect health endpoint request logs to see whether probe traffic arrives at all.

### 20.4. Failover Works on a Test Machine Yet Users Still Hit Errors

DNS resolver/client caches and open connections can retain the old target. The second backend may also lack sessions, data, or TLS certificates. Inspect fresh DNS answers, live TCP/HTTPS connections, and business workflows rather than looking only at profile status.

### 20.5. HTTPS Errors After Switching Regions

Ensure **app.example.com** is configured on both backends with valid certificates on each. If endpoints use a different hostname during health monitoring, inspect differences between probes and live user access.

### 20.6. Weighted Distribution Differs from Expected Ratios

Check DNS caching, client counts behind each resolver, requests per session, observation window, and endpoint health. Weighted steers DNS decisions, not individual HTTP requests.

### 20.7. Users Receive an Endpoint from an Unexpected Region

For Performance routing, inspect recursive resolver location, EDNS Client Subnet, network latency data, and external endpoint region settings. For Geographic/Subnet, inspect mappings and how DNS query sources are detected.

### 20.8. Cannot Use Traffic Manager for Private Backends

Traffic Manager requires endpoints resolvable/reachable under supported public models. If backends only have private IPs or Private Endpoints in a VNet, design private DNS, appropriate ingress, or an L7 gateway service with required private connectivity.

## 21. Cost and Operational Risk Control

Traffic Manager costs can depend on DNS query counts, endpoint counts, and health monitoring/feature options under current pricing. Backend endpoints, bandwidth, data systems, Azure Monitor, and security services incur separate costs.

When designing, weigh:

- Overly short TTLs cause resolvers to re-query more often, increasing DNS query volume.
- Many endpoints and nested profiles raise configuration, monitoring, and cost overhead.
- The standby region needs sufficient serving capacity, since failover may shift the full load onto the remaining endpoint.
- Data replication and cross-region bandwidth can exceed the cost of DNS routing itself.
- Overly heavy health probes can place unnecessary load on backends.

Estimate with the Azure Pricing Calculator and review actual bills in Azure Cost Management after testing. Never pick a configuration just for low DNS cost if the standby system lacks capacity to serve traffic.

## 22. Lab Exercise: Primary/Secondary with Priority Routing

**Context:** You have two public web endpoints in a lab environment; both return HTTP 200 at **/health** and serve a page clearly identifying A vs. B.

**Prerequisites:** Azure subscription with permissions to create Traffic Manager, DNS permissions if testing a custom domain, two public backends with valid TLS, and an environment where controlled test faults can be triggered.

### Part A — Design

1. Pick a unique profile name and create an A/B endpoint table.
2. Assign Priority 1 to A, Priority 2 to B, TTL 60 seconds, and HTTPS 443 **/health** probe.
3. Define how app B handles requests when A fails; verify data, sessions, and domain.
4. Record expectations: normally A is chosen; when A is unhealthy, new DNS answers switch to B.

### Part B — Configure

1. Create the Traffic Manager profile.
2. Add both public endpoints with Priorities.
3. Verify each endpoint's monitor status.
4. Query the **trafficmanager.net** name to verify DNS resolution.
5. If hostnames and TLS are ready on both backends, point the custom domain with an appropriate CNAME.

### Part C — Induce Fault

1. Query DNS multiple times and record timestamps.
2. Confirm app A works and its health endpoint succeeds.
3. In the lab, intentionally make A's health endpoint fail the probe criteria.
4. Watch A turn unhealthy and fresh DNS queries select B.
5. From a test machine, measure how long it takes for HTTPS to actually be served by B.
6. Restore A, observe A return Online, and verify routing returns to primary per Priority configuration.
7. Record detection latency, cache duration, affected sessions, and business outcomes.

### Part D — Report

The report should include:

| Item | Information to record |
|---|---|
| Profile | DNS name, routing method, TTL |
| Endpoints | Target, priority, monitor status |
| Probe | Protocol, port, path, and evaluation criteria |
| Failover | Time A failed, A marked Degraded, DNS chose B, and users succeeded |
| DNS | Resolvers used, query outputs, and observed TTL |
| Backend | Application and data status on A/B |
| Conclusion | Observed recovery duration and main causes |

After the lab, restore the health endpoint, revert DNS records as needed, and clean up lab resources approved for deletion. Verify no DNS records remain pointing to a deleted profile.

If you only have one public endpoint, you can still practice creating a profile, health monitoring, and DNS lookups, but **you cannot claim to have tested two-endpoint failover**.

## 23. Pre-Production Checklist

- [ ] Routing method chosen for business requirements with DNS limitations understood.
- [ ] Every public endpoint is reachable on the right hostname/port with valid TLS.
- [ ] Health path reflects real serving capability rather than a dummy 200 response.
- [ ] DNS TTL, probe interval, and failure threshold align with recovery targets.
- [ ] Custom domain configured across all backends eligible to receive traffic.
- [ ] Standby backend has matching data, configuration, secrets, session strategy, and capacity.
- [ ] Tested traffic shift when an endpoint goes unhealthy and when it recovers.
- [ ] Accounted for DNS caching and measured switchover time in RTO expectations.
- [ ] Verified data, logging, and residency policies if using Geographic routing.
- [ ] Alerts configured for endpoint health, backend errors, TLS, and unexpected profile changes.
- [ ] RBAC enforced, DNS provider secured, and change history audited.
- [ ] Rollback plan, on-call owner, and DNS/endpoint troubleshooting runbooks documented.

## 24. Self-Check Questions

1. Why can't Traffic Manager directly route by HTTP path or insert a WAF?
2. A Priority profile has A at priority 1 and B at priority 2. When A turns Degraded, what answer can new DNS queries receive?
3. Why does a 60-second TTL not guarantee all users fail over within 60 seconds?
4. Does 80/20 Weighted routing guarantee an exact 80/20 split of HTTP requests? Why or why not?
5. Does Performance routing rely on live RTT measurements from each browser or on other information?
6. When a public endpoint returns 200 while the database is down, how should the health endpoint be improved?
7. When the custom domain is `app.example.com`, where must TLS certificates be provisioned?
8. Does Geographic routing automatically guarantee data-residency compliance and cross-country failover?
9. What benefits do nested profiles provide, and what configuration risks do they introduce?
10. When DNS resolves accurately yet the application is unreachable, which additional layers must you check?

## 25. Summary

**Azure Traffic Manager is a global routing tool at the DNS layer.** Profiles hold the routing method, endpoints, monitoring, and TTL; the service selects DNS answers based on policy and endpoint health. Six routing methods serve different objectives: Priority, Weighted, Performance, Geographic, MultiValue, and Subnet.

When deploying, remember that **HTTPS traffic goes directly to backends** and **DNS caching prevents instantaneous failover**. A highly available system must prepare multi-region backends, data, custom domains/TLS, health probes, access controls, and recovery testing. Traffic Manager is an orchestration component that must work alongside other Azure services to run applications safely, effectively, and cost-efficiently.
