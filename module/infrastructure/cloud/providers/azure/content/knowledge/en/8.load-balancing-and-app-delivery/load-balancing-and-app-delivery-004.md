# HTTP Routing with Azure Application Gateway

An application can consist of multiple components serving users together: a web frontend, an API, an admin portal, and a static content service. Exposing each component to the Internet via a separate address forces operations teams to manage multiple entry points, certificates, security rules, and monitoring configurations. **Azure Application Gateway** lets you place a single HTTP/HTTPS entry point in front and forward requests to the right backend based on **hostname**, **URL path**, and configured rules.

Application Gateway is Microsoft Azure's **Layer 7 (application-layer)** load balancer. It can inspect relevant details inside an HTTP request, terminate TLS sessions at the gateway, distribute requests across healthy backends, and—when using WAF—apply web application firewall rules. Using it effectively requires understanding how listeners, request routing rules, URL path maps, backend pools, backend settings, and health probes work together.

This lesson belongs to the **Load Balancing and Application Delivery** chapter of the Azure learning path: from subscriptions and resource groups to virtual networks, compute services, data, monitoring, security, and cost management.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish Application Gateway from Azure Load Balancer and Azure Front Door.
2. Describe the flow of an HTTP/HTTPS request through Application Gateway.
3. Explain listeners, backend pools, backend settings, health probes, and routing rules.
4. Design hostname-based and URL-path-based routing, including default routes.
5. Understand how TLS, WAF, DNS, private networking, and availability fit together.
6. Perform a sample configuration in the Azure portal and verify it with Azure CLI and curl.
7. Diagnose 502 errors, 403 errors, misrouted backends, and unhealthy backends.

## 1. What Problem Does Application Gateway Solve?

Suppose an e-commerce system has:

- Customer storefront at **shop.example.com**.
- Order-processing API at **shop.example.com/api/**.
- Admin portal at **admin.example.com**.
- Multiple web and API instances to avoid depending on a single server.

The team wants users to access HTTPS through a single entry point, yet have requests routed to the right service. Application Gateway enables this routing:

| Client request | Matching logic | Target backend |
|---|---|---|
| https://shop.example.com/ | Host shop + default route | Web server pool |
| https://shop.example.com/products/15 | Host shop + default route | Web server pool |
| https://shop.example.com/api/orders | Host shop + path /api/* | API pool |
| https://admin.example.com/ | Host admin | Admin app pool |

That is the key difference from load balancing based solely on IP and port: Application Gateway can route based on **HTTP Host** and **URL path** information, then choose an eligible backend from the pool.

### Comparing Traffic Distribution Services

| Service | Protocol layer and scope | Suitable example |
|---|---|---|
| **Azure Load Balancer** | Layer 4, TCP/UDP, load balancing by IP/port | Balancing TCP connections to VMs or internal services |
| **Azure Application Gateway** | Layer 7, HTTP/HTTPS, regional and VNet-integrated gateway | Routing `/api/*`, multiple hostnames, frontend TLS and WAF |
| **Azure Front Door** | Layer 7, global entry point at Microsoft's edge network | Multi-region apps, global origin selection, and delivery acceleration |

Services can be combined. For example, Front Door handles global users and forwards traffic to regional Application Gateways. The choice depends on architecture, geographic scope, security requirements, features, and cost; Application Gateway does not automatically replace every role of Load Balancer or Front Door.

## 2. How a Request Is Processed

Logical flow:

~~~text
Client: https://shop.example.com/api/orders
                   |
                   v
DNS: shop.example.com -> Application Gateway Public IP
                   |
                   v
Frontend IP + port 443
                   |
                   v
HTTPS listener (hostname + certificate)
                   |
                   v
Request routing rule (priority)
                   |
                   v
URL path map: /api/*  -> API backend pool
              default -> Web backend pool
                   |
                   v
Backend settings (HTTP/HTTPS, port, host, timeout, ...)
                   |
                   v
Health probe -> select only healthy backends
                   |
                   v
API backend: 10.44.2.10:8080
~~~

For gateways with WAF enabled, the request is also inspected against the WAF policy applied at the appropriate scope. WAF can log or block the request before it reaches the backend, depending on the rules, mode, and policy in use.

Key points to remember:

- **DNS** helps clients locate the frontend IP or name; it does not choose between web and API backends.
- **Listener** defines which requests the gateway accepts, such as HTTPS on port 443 for a specific hostname.
- **Routing rule** binds a listener to a routing or redirection action.
- **Path map** selects a backend by URL path when the rule is path-based.
- **Backend settings** define how the gateway communicates with the backend.
- **Health probe** determines which backends are eligible to receive traffic.

Application Gateway is a **reverse proxy**: the client establishes a connection to the gateway, and the gateway opens a separate connection to the chosen backend. Therefore, you must verify both the client → gateway path and the gateway → backend path.

## 3. Core Configuration Components

### 3.1. Frontend IP and Frontend Port

The **Frontend IP** is the address clients use to reach the gateway. Depending on supported SKUs and deployment models, the gateway can use a public frontend, a private frontend, or both per architecture. A public frontend is typically attached to an Azure **Public IP**; a private frontend takes an IP from the gateway's subnet.

The **Frontend port** is the port opened on the gateway, commonly 80 for HTTP or 443 for HTTPS. Creating a frontend IP/port is not enough to serve traffic: you also need a listener and a rule bound to a backend.

### 3.2. Listener

An **HTTP listener** defines how the gateway receives incoming requests:

- Protocol: HTTP or HTTPS.
- Frontend IP and port.
- Applicable hostname or set of hostnames, when configuring a multi-site listener.
- TLS certificate if the listener uses HTTPS.

Two common models:

- **Basic listener:** accepts requests on the configured frontend/port without restricting to a specific hostname as in multi-site listeners.
- **Multi-site listener:** matches hostnames such as **shop.example.com** or **admin.example.com**, ideal when one gateway serves multiple sites; wildcard hostname options depend on feature support and configuration rules.

For multi-hostname HTTPS, you need matching certificates and proper SNI/hostname configuration per listener type. If the hostname does not match, the gateway may not select the listener you expect.

### 3.3. Backend Pool

A **Backend pool** is a collection of endpoints that can receive requests, such as:

- Private IPs of VMs or VM Scale Sets.
- IP addresses or FQDNs of services running in the VNet or a validly connected network.
- FQDNs of a PaaS service such as Azure App Service when supported by the architecture.

A pool can contain multiple backends for load balancing. Creating a pool does not mean every endpoint receives traffic; the gateway uses health probe results to pick backends deemed healthy.

Example:

~~~text
pool-web
  - 10.44.1.10
  - 10.44.1.11

pool-api
  - 10.44.2.10
  - 10.44.2.11
~~~

Backends can be declared by FQDN when IPs may change; the gateway must resolve DNS accurately and have a network route to the specified endpoint.

### 3.4. Backend HTTP Settings

**Backend settings** (referred to as *HTTP settings* in some UIs or APIs) specify how the gateway connects to the backend:

| Property | Role |
|---|---|
| Protocol | HTTP or HTTPS between the gateway and the backend |
| Port | Port the backend listens on, such as 8080 or 443 |
| Host name | Host header sent to the backend; may need overriding per backend |
| Request timeout | Duration the gateway waits for a response per configuration |
| Cookie-based affinity | Option to maintain session affinity when required by the app |
| Connection draining | Supports waiting for active connections during backend changes per service capabilities |
| Custom probe | Associates a dedicated health probe configuration for the backend |
| Path override | Option to alter the backend path; test thoroughly when used |

Distinguish **backend pool** (which machines/services to send to) from **backend settings** (which protocol, host, and port to use when communicating).

For example, an API backend serves HTTP at **10.44.2.10:8080**. The pool specifies the IP; the settings must specify HTTP port 8080. If settings specify HTTPS port 443 while the API does not serve TLS there, both health probes and live requests will fail.

### 3.5. Health Probe

A **Health probe** is a periodic check sent by the gateway to backends to determine whether an endpoint can serve traffic. Default and custom probes exist. For real workloads, custom probes are usually more valuable because you control:

- HTTP/HTTPS protocol.
- Hostname and port matching the backend.
- Path, such as **/healthz** or **/api/health**.
- Check interval, timeout, unhealthy threshold, and response acceptance criteria per feature capabilities.

API example:

~~~http
GET /healthz HTTP/1.1
Host: api.internal.example.com
~~~

If the API returns a response matching the probe criteria, the endpoint is marked healthy. If the probe fails, the gateway can stop sending requests to that backend. A health endpoint should reflect readiness to serve primary requests without running heavy operations or mutating data.

**A mismatched Host header, path, certificate, or port can make a probe report unhealthy even when the application is running.** This is one of the most common causes of 502 errors.

### 3.6. Request Routing Rule

A **Request routing rule** connects a listener to a backend or routing action. Two main types:

1. **Basic rule:** the listener forwards requests to a single backend pool using selected backend settings.
2. **Path-based rule:** the listener uses a **URL path map** to select backend pools/settings based on URL path, with a default route for non-matching paths.

With Application Gateway v2, set explicit **priorities** on request routing rules. A rule with a smaller priority number takes higher precedence when match conditions compete. Inside a path map, path rule order must also be planned carefully when patterns overlap.

## 4. Hostname-Based Routing (Multi-Site)

One Application Gateway can host multiple websites on the same frontend and port.

Example:

| Client-sent Host | Listener | Rule | Backend |
|---|---|---|---|
| shop.example.com | listener-shop-https | rule-shop, priority 100 | pool-web or path map |
| admin.example.com | listener-admin-https | rule-admin, priority 200 | pool-admin |

To configure:

1. DNS for both hostnames must point to the appropriate frontend.
2. Create an HTTPS listener for each hostname and attach a valid certificate.
3. Create backend pools/settings for each application.
4. Create rules linking each listener to a backend or URL path map.
5. Verify Host headers, SNI, backend health, and live requests.

In a browser, a user visits **https://admin.example.com**. The gateway accepts the TLS connection, matches the listener for this hostname, and forwards traffic to **pool-admin** provided the rule and backend are in a healthy state.

If both hostnames point to the Public IP but you only created a listener for **shop.example.com**, do not assume **admin.example.com** will work automatically. DNS only solves finding the frontend.

## 5. URL Path-Based Routing

Path-based routing lets you split features of the same domain across separate backends.

Suppose the listener for **shop.example.com** uses:

| Path pattern | Backend pool | Backend settings |
|---|---|---|
| `/api/*` | pool-api | settings-api |
| `/assets/*` | pool-static | settings-static |
| Default | pool-web | settings-web |

When accessed:

- **/api/orders** → pool-api.
- **/assets/logo.svg** → pool-static.
- **/products/15** → pool-web via the default route.

### Understanding Path Maps

A URL path map consists of **path rules** and a **default backend**. The gateway matches the URL path against supported patterns and picks the corresponding backend. Overlapping patterns can produce unintended matches if ordering and specificity are not designed properly.

For instance, if both exist:

~~~text
/api/admin/*
/api/*
~~~

Place the more specific pattern `/api/admin/*` before the broader `/api/*` in the path map and test with live requests. Otherwise, admin requests may end up routed to the general API backend.

The default route matters greatly. If no path rule matches, the request follows the URL path map's default backend; do not assume the gateway will automatically return 404. If you want 404 returned for a set of paths, design the backend or handling logic to do so.

### Is the Path Preserved or Changed?

**Path-based routing does not automatically strip path prefixes.** For example, **/api/orders** is normally still sent to the backend with that matching path unless you configure an appropriate override/rewrite. If the backend API only serves **/orders**, handle the **/api** prefix via appropriate gateway configuration or update the application.

Application Gateway also supports **URL rewrite** and **redirect** capabilities. Rewrite modifies request/response attributes under supported conditions; redirect returns a redirect response to the client, such as HTTP to HTTPS. These are distinct behaviors and must be tested separately.

### Combining Host + Path Routing Together

They can be combined:

~~~text
HTTPS listener: shop.example.com
  rule-shop, priority 100
    /api/*       -> pool-api
    /assets/*    -> pool-static
    default      -> pool-web

HTTPS listener: admin.example.com
  rule-admin, priority 200
    default      -> pool-admin
~~~

The goal is clear organization of entry points and backends. An overly broad rule can accept unwanted requests; an overly narrow rule can miss required URLs. Maintain a test suite for every hostname, path, redirect, and non-matching case.

## 6. HTTPS: Terminate TLS at the Gateway or Encrypt to the Backend?

Application Gateway can accept HTTPS from clients and manage connections to backends according to backend settings.

### TLS Termination at the Frontend

The client establishes HTTPS with the gateway. The gateway decrypts traffic to perform Layer 7 routing and apply relevant features. It then connects to the backend using the configured protocol:

~~~text
Client --HTTPS--> Application Gateway --HTTP--> Backend
~~~

This model is simple when backends sit inside a network trusted by policy, but the gateway → backend leg uses HTTP and is **not encrypted with TLS**. Evaluate data security requirements before choosing it.

### End-to-End TLS

The gateway still terminates the client-side TLS session to process the request, then establishes **a separate HTTPS session** to the backend:

~~~text
Client --HTTPS--> Application Gateway --HTTPS--> Backend
       TLS #1                          TLS #2
~~~

With HTTPS backends, ensure:

- The backend actually listens on the configured HTTPS port.
- The backend certificate is valid (not expired), matches the expected hostname, and has a verifiable trust chain.
- If using an internal CA or self-signed cert, configure the trusted root certificate per gateway capabilities and requirements.
- Host header and Server Name Indication (**SNI**) match the backend.
- Health probes also use compatible protocol, host, and path settings.

For example, suppose a backend is an Azure App Service whose HTTPS endpoint expects a Host header matching a custom domain. If the gateway sends a private IP or mismatched hostname as the Host header, the backend may return errors, probes may fail, or certificate validation may fail. Keep backend FQDN, hostname override, and certificates aligned.

### Certificates and Lifecycle

Frontend certificates are attached to HTTPS listeners. Certificates can be managed directly or integrated with Azure Key Vault where supported by features/SKU, subject to identity and access permission requirements. Operations teams must track expiration dates, renewal plans, and verify configurations after certificate rotation.

If HTTP → HTTPS redirection is required, create a matching listener/rule or redirect configuration. Adding an HTTPS listener does not automatically create a redirect from port 80.

## 7. Web Application Firewall (WAF)

**Application Gateway WAF_v2** adds a web application firewall for supported deployment models. WAF inspects HTTP(S) requests against rule sets and a WAF policy to mitigate risks from common web attacks.

Two common modes:

- **Detection:** evaluates and logs requests matching rules, useful for observation and tuning.
- **Prevention:** can block requests deemed to violate the policy.

WAF does not replace fixing application flaws, authentication, authorization, secret management, or database security. Valid requests must still be authenticated by the backend. A WAF-blocked request may return **403** right at the gateway, distinct from **502** caused by an unhealthy backend.

When enabling WAF on a live application, test valid paths, payloads, and integrations to prevent false positives. Review WAF logs, rule IDs, request IDs, and applied policies before adding exclusions or tuning rules. Never disable the entire WAF just because one endpoint hits an error.

## 8. Networking, Subnets, DNS, and Backend Reachability

Application Gateway is deployed inside an **Azure Virtual Network** and requires a dedicated subnet for the gateway per service requirements.

### Dedicated Subnet

In an example layout:

~~~text
VNet: vnet-sales          10.44.0.0/16
  snet-appgw              10.44.0.0/24
  snet-web                10.44.1.0/24
  snet-api                10.44.2.0/24
~~~

Subnet **snet-appgw** is dedicated to Application Gateway and must not host regular VMs or application resources. For v2, a **/24** subnet is commonly recommended for scaling headroom, though minimum sizes depend on SKU and design. When creating or resizing subnets, check current documentation and expected instance counts.

Do not apply NSGs or UDRs that block infrastructure/control-plane traffic required by Application Gateway. If you place NSGs, route tables, or firewalls in the path, follow Application Gateway's specific requirements for management traffic and backend traffic.

### Connectivity Path to Backends

Backends can reside in the same VNet, a peered VNet, or another validly connected network, provided the gateway can resolve and route to them under a supported architecture. For internal backends, verify:

1. Non-overlapping CIDRs across connected networks.
2. Effective routes from the gateway subnet to the backends.
3. NSGs and firewalls allow the backend port for both probe flows and request traffic.
4. Backends are listening on the expected IP/port.
5. DNS resolves to the right IP when the pool uses an FQDN.

PaaS apps do not always behave identically to VMs in a subnet. For instance, App Service has specific hostname, TLS, and private-networking requirements. When using Private Endpoints or other networking mechanisms, follow each service's supported configuration.

### Public DNS and Private DNS

Public DNS can point **shop.example.com** to the frontend Public IP. When a pool uses an internal backend FQDN, DNS from the gateway's perspective must resolve that name to a reachable address. Client → gateway DNS and gateway → backend DNS are **two independent steps**.

If the environment uses Private DNS Zones, custom DNS servers, or Azure DNS Private Resolver, verify resolution from the appropriate side. Fixing a public DNS record does not fix broken internal backend FQDN resolution.

## 9. Availability, Performance, and Limits

Application Gateway **Standard_v2** or **WAF_v2** provides capabilities such as autoscaling and availability-zone deployment in supported regions and feature combinations. When designing for production:

- Choose the SKU based on WAF, scale, and feature needs.
- Configure autoscaling/minimum instances based on load and availability targets.
- Place backends across multiple instances, zones, or clusters where appropriate.
- Configure health probes that reflect real processing capability.
- Use session affinity only when required by the app; prefer stateless application design whenever possible.
- Monitor latency, request counts, status codes, backend connections, and instance health.

The gateway is a **regional** component. It does not provide failover between two Azure regions on its own. If an application needs recovery when an entire region goes down, design global routing plus application and data replicas in another region.

Applications must tolerate failed or retried requests. Health probes help steer around broken backends, but do not replace idempotent retries, sensible timeouts, and zero-downtime deployment strategies.

## 10. Hands-On: Configuring HTTP Routing in the Azure Portal

Lab scenario: a sales application runs two web backends and two API backends. Objectives:

- Users access **https://shop.example.com** via Application Gateway.
- `/api/*` requests route to the API pool.
- All other paths route to the web pool.
- Unhealthy backends stop receiving new requests based on probe results.

The names, IPs, and domains below are **hypothetical learning examples**, not references to existing resources. Deploy only in an authorized subscription after checking budget, since Application Gateway and Public IPs incur charges.

### Step 1: Prepare the Network Environment

Prepare a VNet such as **vnet-sales (10.44.0.0/16)** with dedicated subnet **snet-appgw (10.44.0.0/24)** and web/API subnets. Deploy backends or prepare backend FQDNs/IPs reachable from the gateway subnet.

Before creating the gateway, confirm:

- Right subscription, resource group, and region.
- Gateway subnet is not shared with VMs.
- Subnet has enough IPs for instances and scale-out.
- NSGs, UDRs, and DNS satisfy Application Gateway requirements.
- Backends respond over HTTP/HTTPS and expose a health endpoint.

### Step 2: Create the Application Gateway

In the **Azure portal**, search for **Application Gateways** and select create. Choose:

1. Resource group and region.
2. SKU **Standard_v2** for application routing or **WAF_v2** if WAF is required.
3. The prepared VNet and dedicated subnet.
4. Public or private frontend per supported architecture.
5. Standard Public IP if using a public frontend and prompted by the portal.

Configure instance counts, zones, and extra options as needed. Avoid enabling every feature simply because it appears on the screen.

### Step 3: Configure Backend Pools

Create:

| Pool | Example members |
|---|---|
| **pool-web** | 10.44.1.10, 10.44.1.11 |
| **pool-api** | 10.44.2.10, 10.44.2.11 |

Hypothetical IPs must be replaced with real resource IPs or FQDNs. Never add endpoints you do not administer or without valid network reachability.

### Step 4: Configure Backend Settings and Probes

Example:

| Settings | Protocol/port | Probe | Backend |
|---|---|---|---|
| **settings-web** | HTTP / 8080 | GET /healthz | pool-web |
| **settings-api** | HTTP / 8080 | GET /healthz | pool-api |

Set hostname, timeout, and SSL/TLS options to match the actual backend configuration. If backends use HTTPS, switch to HTTPS and verify certificates and trusted roots as needed.

Ensure **/healthz** actually exists and returns an appropriate status code. You can create separate custom probes for web and API if each app uses a different hostname/path.

### Step 5: Create the Listener

Create an HTTPS listener:

~~~text
Name: listener-shop
Frontend: public frontend
Port: 443
Hostname: shop.example.com
TLS certificate: valid certificate for shop.example.com
~~~

Also configure DNS so the hostname resolves to the real frontend. If you do not yet have a valid domain/certificate, you can demonstrate routing with HTTP in an isolated test environment, then switch to HTTPS before production use.

### Step 6: Create the URL Path Map and Rule

Logical configuration example:

~~~text
URL path map: map-shop
    /api/*  -> pool-api, settings-api
    default -> pool-web, settings-web

Request routing rule: rule-shop
    listener: listener-shop
    type: path-based
    URL path map: map-shop
    priority: 100
~~~

On the rule or path map screen, verify the backend pool/backend settings pairing for each path. If adding redirects or rewrites, document expected behavior; do not add those options just to change backends.

### Step 7: Verify Backend Health

Open **Backend health** on Application Gateway. Check every member of **pool-web** and **pool-api**:

- Healthy: probe succeeds under configured criteria.
- Unhealthy: inspect HTTP code, timeout, certificate, hostname, port, networking, or backend config.
- Unknown: check provisioning state and relevant collection/observability conditions.

Do not run end-user tests while all backends are unhealthy. Fix the root cause of probe failures first.

### Step 8: Test Routing and Edge Cases

Once DNS, listeners, rules, and backends are ready:

| Test | Expected result |
|---|---|
| GET / | Web pool returns home page |
| GET /products/15 | Web pool handles request |
| GET /api/orders | API pool handles request |
| GET /api/healthz | API pool handles request per actual backend path |
| GET /unknown | Routes to default web pool, where backend decides whether to return 404 or other content |
| Different hostname | Does not match shop routes unless a matching listener/rule exists |
| One API instance unhealthy | New requests distribute to remaining healthy instances, if any remain in the pool |

If only one backend is healthy, pool fault tolerance is limited. Also evaluate data paths, session affinity, and recovery behavior when the backend returns.

## 11. Verifying with Azure CLI and curl

The CLI commands below are **read-only** for inspecting an existing gateway. Never run commands that create gateways or alter routing on production resources just for practice.

### Select Subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az account show \
  --query "{name:name,id:id}" \
  --output table
~~~

### List and Inspect Gateways

~~~bash
az network application-gateway list \
  --resource-group "rg-sales-network" \
  --output table

az network application-gateway show \
  --resource-group "rg-sales-network" \
  --name "agw-sales-prod" \
  --query "{name:name,sku:sku.name,state:provisioningState,location:location}" \
  --output json
~~~

### View Backend Health

~~~bash
az network application-gateway show-backend-health \
  --resource-group "rg-sales-network" \
  --name "agw-sales-prod" \
  --output json
~~~

Inspect backend pools, member addresses, health status, and error details if returned by the tool. An unhealthy backend can stem from the application itself, the probe, or the network path.

### Test Host + Path Before Changing Public DNS

The example below uses curl's **--resolve** flag to send an HTTPS request to a specific gateway IP while keeping **shop.example.com** for Host/SNI:

~~~bash
curl -v \
  --resolve shop.example.com:443:<APPLICATION_GATEWAY_PUBLIC_IP> \
  https://shop.example.com/api/orders
~~~

Replace placeholders with a real Public IP and a domain/certificate you control. Since **shop.example.com** is only illustrative, do not run it verbatim against the Internet. Avoid flags that skip certificate validation in production tests.

Additional test commands:

~~~bash
curl -v https://shop.example.com/
curl -v https://shop.example.com/api/healthz
~~~

If backends expose a test endpoint returning hostname or instance name, you can verify which pool handled the request. When running repeated requests, keep in mind session affinity can influence which instance receives the call.

## 12. Observability, Logging, and Troubleshooting

Application Gateway can emit metrics, access logs, firewall logs when WAF is used, and backend health status. Sending logs/metrics to Log Analytics or another destination must be configured using Azure Monitor and appropriate diagnostic settings.

### Signals to Monitor

- Total request count and **2xx, 3xx, 4xx, 5xx** response code ratios.
- Backend health, count of healthy/unhealthy backends.
- Response times and backend latency.
- Traffic broken down by listener, rule, hostname, or backend where data is available.
- WAF block/detection logs and triggered rule IDs.
- Capacity/throughput, autoscaling, and request distribution efficiency.

### Common Troubleshooting Table

| Symptom | Possible cause | What to check |
|---|---|---|
| **502 Bad Gateway** | Unhealthy backend; bad probe; invalid backend response; TLS or connectivity failure | Open Backend health, check DNS, port, probe path, Host/SNI, certs, and NSG/UDR |
| **403 Forbidden** | WAF in Prevention mode blocked it, or backend returned 403 | Correlate access/WAF logs and response source; check rule IDs or backend auth |
| **404 Not Found** | Request hit wrong pool/path or backend returned 404 | Check path rules, default route, path received by backend, and access logs |
| **TLS/certificate error** | Frontend cert does not match hostname, expired, or backend TLS untrusted | Check listener cert, hostname, SNI, and backend trusted root |
| **Right host, wrong site** | Listener/rule priority or multi-site hostname misconfigured | Check Host header, listener hostnames, priority, and DNS |
| **`/api/*` hits web frontend** | Path map missing rule, or overlapping patterns/priorities | Inspect path rule order and default backend |
| **Only some instances fail** | Different probes, inconsistent backends, session affinity, or network issue | Check individual backend health, test instances directly, verify deployment |
| **Gateway cannot reach backend** | NSG, route, DNS, Private Endpoint, or firewall | Check gateway → backend path, effective routes, and ports |
| **Gateway works, Internet cannot reach it** | DNS, Public IP, frontend listener/port, or client network | Check public DNS, listener, IP/port, and external connectivity |
| **Rule changes not taking effect immediately** | Configuration still provisioning, DNS caching, or change outside gateway | Confirm provisioning state, compare config, test exact Host/IP |

### Distinguishing Errors by Origin

A **502** from the gateway indicates the gateway failed to communicate successfully with the backend as required. A **404** may come entirely from the backend because the path does not exist; it does not always mean the gateway misrouted. A **403** can come from WAF or the application itself. To draw conclusions, rely on logs, request IDs, backend health, and layer-by-layer testing.

Never fix issues by disabling NSGs, bypassing authentication, or turning off the entire WAF. Identify the specific rule, port, or host causing the problem and adjust it following least privilege.

## 13. Security and Governance for Production

A gateway serving multiple applications becomes a critical architectural component. When designing for production:

1. **Limit public surface:** expose only necessary listeners and hostnames; place sensitive backends on private networks when appropriate.
2. **Enforce HTTPS and manage certificates:** track cert lifecycles, restrict protocols and ciphers per service capabilities and policy.
3. **Protect traffic to backends:** consider end-to-end HTTPS, proper host/SNI settings, and CA validation.
4. **Configure WAF when needed:** use policies, review false positives and logs; do not assume WAF replaces secure application code.
5. **Enforce RBAC:** apply Azure RBAC to restrict who can modify listeners, rules, certificates, WAF policies, and backends.
6. **Controlled automation:** manage configuration via IaC such as ARM/Bicep/Terraform and review changes before deployment.
7. **Monitor actively:** enable metrics, diagnostic settings, alerts, and backend health tracking; assign operational owners.
8. **Plan redundancy:** consider multiple backends, zone redundancy, and cross-region DR plans when required.
9. **Control costs:** track SKU, uptime, capacity/autoscale, data processed, and add-on features.

A sound governance practice is assigning every listener/path map an application owner and a test suite verifying expected hostname, path, protocol, and backend. Whenever adding a new route, re-check overlapping paths to avoid breaking existing functionality.

## 14. Cost Estimation and Design Choices

Application Gateway can incur both fixed charges and usage/capacity charges depending on SKU, instance/capacity units, uptime, and billable product dimensions. Additional costs may include Public IPs, data transfer, logging/monitoring, and WAF features as applied.

Before creating a gateway for learning or production, always:

- Pick the SKU matching required features: Standard_v2 or WAF_v2 as needed.
- Estimate request volume, throughput, latency, and traffic peaks.
- Choose sensible autoscaling and minimum instance counts.
- Evaluate whether one gateway can serve multiple apps while preserving administrative and performance isolation.
- Check Azure Monitor/Log Analytics ingestion and retention costs.
- Set budgets, owner tags, and monitor Azure Cost Management.

Do not assume Application Gateway has a single flat price or is always cheaper than Front Door/Load Balancer. Check current pricing for your exact SKU, region, and architecture.

## 15. Case Study

A company runs a recruiting application:

- **jobs.example.com** displays job listings.
- **jobs.example.com/api/** serves the API.
- **admin.example.com** provides a separate admin portal.
- Web backend has two VMs, API backend has three instances, and admin backend is one HTTPS service.

Requirements: clients connect over HTTPS, API and web use separate backends, admin uses its own hostname, unhealthy backends receive no new traffic, and admin data must be protected.

Design the following:

1. Frontend IP/port and HTTPS listeners to create.
2. Backend pools and backend settings for web, API, and admin.
3. Path map for **jobs.example.com** with `/api/*` and a default route.
4. Basic rule or path-based rule for **admin.example.com**.
5. Custom probes tailored to each backend.
6. Certificates, Host/SNI, and HTTPS backend options.
7. WAF policy, DNS, network controls, and observability plan for 403/502 errors.
8. A test suite proving each Host/path reaches the right backend, including when one API instance is unhealthy.

A sound design uses two multi-site HTTPS listeners, a path-based rule for **jobs.example.com**, and a basic rule for **admin.example.com**. Backend settings/probes are separated by protocol and hostname. Only the frontend needs to be public; backend access is restricted to traffic coming from the gateway. If admin does not need to be publicly reachable by everyone, add network controls, identity checks, or a separate private entry point per policy.

## 16. Self-Check Questions

1. Why is Application Gateway classified as Layer 7, while Azure Load Balancer is typically Layer 4?
2. How does an HTTP listener differ from a backend pool and backend settings?
3. What steps does a request to **shop.example.com/api/orders** pass through before reaching the API backend?
4. What is the difference between a basic rule and a path-based rule? What does a URL path map do?
5. If both `/api/admin/*` and `/api/*` exist, what must you watch for regarding match order?
6. Why is pointing DNS to the right Public IP not enough to make a hostname work?
7. Does routing by `/api/*` automatically strip the **/api** prefix when forwarding requests to the backend?
8. Why can a backend probe show unhealthy even when the web app is still running?
9. Describe the two models—TLS termination and end-to-end TLS—when using Application Gateway.
10. When receiving a 403 error, how do you distinguish a WAF block from a backend authorization failure?
11. When receiving a 502 error, in what order should you check backend health, ports, DNS, TLS, and NSGs?
12. Why does a regional Application Gateway not automatically provide disaster recovery if an entire region fails?

## References

- Microsoft Learn — *What is Azure Application Gateway?*: https://learn.microsoft.com/azure/application-gateway/overview
- Microsoft Learn — *Request routing rules*: https://learn.microsoft.com/azure/application-gateway/request-routing-rules
- Microsoft Learn — *URL path-based routing*: https://learn.microsoft.com/azure/application-gateway/url-route-overview
- Microsoft Learn — *Backend health and health probes*: https://learn.microsoft.com/azure/application-gateway/application-gateway-probe-overview
- Microsoft Learn — *TLS termination and end-to-end TLS*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *Application Gateway WAF*: https://learn.microsoft.com/azure/web-application-firewall/ag/ag-overview
- Microsoft Learn — *Application Gateway infrastructure configuration*: https://learn.microsoft.com/azure/application-gateway/configuration-infrastructure
