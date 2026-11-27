# TLS Termination, Listeners, and Backend Pools

An application accessed via `https://shop.example.com` might run across multiple virtual machines, App Service instances, or a group of backend services. Users only see a single HTTPS domain name, yet the system must answer three questions simultaneously: **where is the TLS connection handled, under what conditions are HTTP requests accepted, and which backend receives each request?**

In Azure, **Application Gateway** is a typical choice for **Layer 7 (HTTP/HTTPS)** load balancing. The three concepts **TLS termination**, **listeners**, and **backend pools**—together with **request routing rules**, **backend settings**, and **health probes**—form a complete processing pipeline. Understanding how they fit together helps you configure domains, certificates, routing, security, and availability accurately.

This lesson belongs to the **Load Balancing and Application Delivery** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data, then applies those concepts to deploying, monitoring, securing, and controlling the cost of application architectures. The content below focuses on Azure Application Gateway while pointing out differences from Azure Load Balancer and Azure Front Door where needed.

## 1. Lesson Objectives

After completing this lesson, you will be able to:

1. Explain **TLS termination** and the difference between frontend TLS and backend TLS.
2. Describe the components of an **HTTP/HTTPS listener**: frontend IP, port, protocol, hostname, and certificate.
3. Organize a **backend pool** containing IPs/FQDNs or targets supported by Application Gateway.
4. Wire **listener → request routing rule → backend pool + backend settings**.
5. Design **health probes** so traffic is only directed to backends eligible to receive it.
6. Choose between HTTPS→HTTP and HTTPS→HTTPS models based on security requirements.
7. Troubleshoot real-world failures: invalid certificates, hostname mismatches, Unhealthy backends, HTTP 502, and redirect loops.
8. Verify configurations using Azure Portal and Azure CLI prior to sign-off.

## 2. Placing Application Gateway in the Azure Load-Balancing Landscape

Several Azure services perform "traffic distribution," but at different layers:

| Service | Key characteristics | Best-fit scenarios |
|---|---|---|
| **Azure Load Balancer** | **Layer 4** TCP/UDP load balancing operating on IP and port. | TCP/UDP services, internal or public network load balancing. |
| **Azure Application Gateway** | **Layer 7** reverse proxy and load balancer understanding HTTP/HTTPS; supports TLS termination, host/path routing, health probes, and WAF by SKU. | Web/API applications within a regional Azure architecture. |
| **Azure Front Door** | Application delivery at the global edge, with TLS, routing, and security features per tier. | Multi-region public applications, optimizing global access and regional failover. |

**Azure Load Balancer does not perform TLS termination at the HTTP layer.** When using Load Balancer, TLS is normally decrypted by the application or a downstream proxy. Application Gateway can decrypt HTTPS to inspect hostnames, paths, and headers and apply Layer 7 rules. Azure Front Door also handles TLS, but operates at a different network position and global delivery scope than Application Gateway.

In this lesson, examples use **Application Gateway v2** (`Standard_v2` or `WAF_v2` depending on needs). Specific options vary by SKU, region, and version; verify currently supported features before deploying to production.

## 3. End-to-End Flow from Browser to Backend

Every HTTP(S) request passes through multiple configuration objects:

```text
                     DNS: shop.example.com
                               |
                         HTTPS :443
                               v
                      +-----------------+
Internet / Client --->| Frontend IP     |
                      | Application     |
                      | Gateway         |
                      +--------+--------+
                               |
                       HTTPS Listener
                 host=shop.example.com
                 protocol=HTTPS, port=443
                 TLS certificate: shop.example.com
                               |
                    Request routing rule
                  (Basic or path-based)
                               |
                      +--------+--------+
                      |                 |
               Backend pool        Backend settings
              [web-01, web-02]     HTTP/HTTPS, port,
                                  host, timeout, affinity,
                                  custom health probe
                      |                 |
                      +--------+--------+
                               |
                 Select healthy endpoints only
                       /              \
                      v                v
                   web-01            web-02
                10.20.1.10         10.20.1.11
```

The flow in the diagram comprises these logical steps:

1. The client resolves DNS and opens a TCP/TLS connection to the gateway's **frontend IP**.
2. The **HTTPS listener** accepts the connection matching protocol, port, and hostname.
3. The gateway performs a **TLS handshake** with the client using the certificate configured on the listener.
4. The gateway evaluates the **request routing rule** to choose a backend pool and backend settings, or redirect to another URL.
5. **Health probes** determine which backends are ready.
6. The gateway sends the request to a healthy backend over HTTP or HTTPS per backend settings.
7. The backend returns a response through the gateway, which forwards it back to the client over the frontend connection.

Different route types can be configured from a listener depending on supported rules. One backend pool can also be referenced by multiple routing rules. The components must align properly; creating a backend pool alone does not send traffic to the application.

## 4. What Is TLS Termination?

**TLS (Transport Layer Security)** provides an encrypted channel and server authentication for network connections, commonly used with HTTPS. When a browser visits `https://shop.example.com`, it validates the TLS certificate and establishes an encrypted connection to the HTTPS endpoint.

**TLS termination at Application Gateway** means the gateway **terminates the client's TLS connection**. The gateway can then decrypt HTTP content to route requests, inspect headers, or apply WAF rules (if enabled).

```text
Client                  Application Gateway               Backend
  |     TLS session A           |                           |
  |============================>|                           |
  |  HTTPS encrypted            |  Decrypted HTTP request   |
  |                             |---------- HTTP ---------->|  (option 1)
  |                             |                           |
  |                             |==== TLS session B =======>|  (option 2)
  |                             |    HTTPS to backend       |
```

Key point: **TLS session A and TLS session B are two separate connections.** In the HTTPS→HTTPS model, the gateway decrypts the request at the frontend and then initiates a new TLS connection to the backend. This is commonly referred to as **end-to-end TLS** in Application Gateway documentation, though it is not a single unbroken TLS session from client to backend.

### HTTPS at the Frontend, HTTP at the Backend

- Browser ↔ Application Gateway: **HTTPS**, encrypted.
- Application Gateway ↔ backend: **HTTP**, unencrypted at the TLS layer.
- Simpler to configure and may suit certain lab environments or controlled trust boundaries.

Risk: traffic **behind the gateway is no longer protected by TLS**. Use this only if permitted by your security model, network zoning, and organizational policies.

### HTTPS at the Frontend, HTTPS at the Backend

- Browser ↔ Application Gateway: **HTTPS**, gateway presents the frontend certificate.
- Application Gateway ↔ backend: **HTTPS**, gateway acts as a TLS client and validates the backend per configuration.
- Suitable when data must remain encrypted on both hops or when required by security policy.

Backend HTTPS configuration requires attention to the **backend certificate**, validated hostname, trust chain, SNI, and TLS port reachability. The client-facing listener certificate **does not automatically** become the backend certificate. The backend must have its own appropriate server certificate.

### TLS Termination vs. TLS Passthrough

- **Termination:** the gateway decrypts and understands HTTP to apply Layer 7 routing and WAF.
- **Passthrough:** an intermediary forwards encrypted TLS traffic without decrypting HTTP.

Because Application Gateway is a Layer 7 reverse proxy, its model relies on **TLS termination**. If true TCP-layer TLS passthrough is required, evaluate another appropriate service/architecture rather than expecting an Application Gateway HTTPS listener to forward raw TLS sessions untouched.

## 5. Frontend TLS Certificates

An HTTPS listener needs a certificate for the domain serving users, such as `shop.example.com`.

Items to verify:

| Factor | Requirement |
|---|---|
| **Subject/SAN** | Certificate covers the exact hostname clients access. |
| **Validity** | Not expired and already past its valid-from date. |
| **Trust chain** | Includes the proper CA chain so browsers can validate it. |
| **Private key** | Usable by the gateway via a supported certificate import method. |
| **TLS policy** | TLS version and cipher suites meet security and client compatibility requirements. |
| **Renewal** | Rotation process, expiration monitoring, and post-renewal verification exist. |

In Application Gateway, frontend certificates can typically be supplied as a **PFX/PKCS#12** file containing the private key, or referenced from a certificate/secret managed in **Azure Key Vault** using a mechanism supported by the SKU. When integrating with Key Vault, the gateway needs a **managed identity**, proper permissions to read the secret/certificate, and network reachability to the vault per configuration.

Never place PFX passwords, private keys, client secrets, or certificate files containing private keys into repositories, logs, or learning examples. For production, manage certificate lifecycles centrally, apply least-privilege permissions, and monitor Key Vault access failures.

### SNI and Multiple Domain Names

**Server Name Indication (SNI)** is a TLS extension allowing clients to indicate the target hostname during the handshake. The gateway can select the matching certificate/listener when multiple domains share a single frontend IP and port.

Example:

| Hostname | HTTPS listener | Frontend certificate |
|---|---|---|
| `shop.example.com` | `listener-shop-https` | Certificate covering `shop.example.com` |
| `admin.example.com` | `listener-admin-https` | Certificate covering `admin.example.com` |
| `api.example.com` | `listener-api-https` | Certificate covering `api.example.com` |

You can use SAN or wildcard certificates if they satisfy domain scope and key management policies. A wildcard certificate does not cover arbitrary subdomain levels. For example, `*.example.com` typically covers `shop.example.com`, but does not automatically cover `api.eu.example.com`.

Domain names map to listeners via hostname configuration, DNS, and TLS certificates. If a client uses a name not covered by the certificate, the browser can throw a **hostname mismatch** error right during the TLS handshake.

## 6. Listener: The Entry Gate for Requests

A **Listener** declares **which traffic the gateway listens for**. In Application Gateway, a listener typically binds these properties:

- **Frontend IP configuration:** public or private frontend per architecture.
- **Frontend port:** e.g., `80` for HTTP or `443` for HTTPS.
- **Protocol:** HTTP or HTTPS.
- **Hostname(s):** target domain name(s) when using a host-based listener.
- **TLS certificate:** required for HTTPS listeners.
- **Additional TLS settings:** such as SSL profiles or client authentication features if used and supported by the SKU.

A listener does not specify the complete handling destination on its own. You need a **request routing rule** linking the listener to a backend pool and backend settings, or to a redirect configuration.

### Basic Listener vs. Multi-Site Listener

| Type | Request matching principle | Use case |
|---|---|---|
| **Basic** | Accepts requests based on configured frontend IP, port, and protocol without distinguishing hosts like multi-site. | Single website or simple endpoint. |
| **Multi-site** | Identifies requests using hostname(s) in addition to frontend IP, port, and protocol. | Multiple websites/APIs sharing a gateway with distinct hosts. |

With multi-site listeners, the hostname sent in the HTTP Host header and the hostname used for TLS/SNI must be configured consistently with the certificate. Mismatches can cause listener selection, certificate, or routing failures.

Example with two websites sharing one public IP:

```text
https://shop.example.com:443  ──> listener-shop  ──> pool-shop
https://admin.example.com:443 ──> listener-admin ──> pool-admin
```

Hostname-based separation avoids provisioning separate IPs/ports per website. However, an admin endpoint may still need internal-only access, strong authentication, or additional security controls; naming the host `admin` does not protect the application from unauthorized access.

### Choosing Public or Private Frontend

- **Public frontend IP:** for applications serving clients over the Internet. Requires matching DNS and security policies.
- **Private frontend IP:** for applications accessed only over private networks, such as VNet peering, VPN, or ExpressRoute where paths and DNS permit.
- Some configurations support multiple frontends as needed. Check SKU limits and listener/port conflict rules before creating.

**Do not confuse the frontend IP with backend addresses.** The frontend is the address clients connect to; the backend pool holds the endpoints receiving requests after gateway routing.

## 7. Backend Pool: The Set of Application Targets

A **Backend pool** is a set of destinations that can receive requests forwarded by the gateway. Supported target types can include:

- Private IPs of VMs/NICs or servers in a connected VNet.
- FQDNs of applications/backends that the gateway can resolve and reach.
- Feature-integrated targets such as VM Scale Sets or App Service, depending on creation method and SKU.

Example `pool-shop` containing:

| Backend | Address | Application | Notes |
|---|---|---|---|
| `web-01` | `10.20.1.10` | Shop API instance 1 | Private IP |
| `web-02` | `10.20.1.11` | Shop API instance 2 | Private IP |
| `web-03` | `10.20.1.12` | Shop API instance 3 | Private IP |

The pool describes **members**, not the full details of how the gateway opens connections. To connect to backends, the gateway needs **backend settings** (formerly often called HTTP settings) specifying protocol, port, and HTTP/TLS behavior.

**Note:** a backend whose DNS name changes IPs must be resolvable by the gateway through supported mechanisms. Plan DNS and real backend monitoring; placing an FQDN in a pool does not guarantee network reachability or a running application.

### A Backend Pool Is Not End-User DNS

Clients use `shop.example.com` to locate the gateway **frontend**. They do not need to know `10.20.1.10` or the internal pool membership. The gateway selects healthy backends based on configuration and health probes.

### Can Backends Reside in Another Network?

Yes, depending on the scenario and supported target type, as long as the gateway has **network reachability** to the backend via routing, peering, VPN/ExpressRoute, or appropriate networking. If an FQDN resolves to an unreachable address, an NSG blocks traffic, or DNS fails to resolve, the pool has members yet cannot serve traffic.

Do not populate pools with overlapping address ranges or endpoints behind a firewall lacking return routes. Security and routing must be designed bidirectionally.

## 8. Backend Settings: How Does the Gateway Connect to Backends?

Backend settings define the details of the **hop behind the gateway**.

| Property | Example | Effect |
|---|---|---|
| **Protocol** | HTTP or HTTPS | Chooses whether to initiate a TLS session to the backend. |
| **Port** | `80`, `8080`, `443`, `8443` | Port the backend service actually listens on. |
| **Request timeout** | Appropriate number of seconds | Sets how long the gateway waits for a response per configuration. |
| **Cookie-based affinity** | Enabled/Disabled | Can pin a client session's requests to the same backend in supported models. |
| **Host name** | `shop.internal.example` | Sets the Host header/name sent to the backend, important for virtual hosts and TLS. |
| **Trusted root CA / validation** | Configured trusted CA | Lets the gateway validate HTTPS backend certificates. |
| **Custom probe** | `probe-shop` | Links the matching health check to the pool and backend settings. |

Example where frontend is `HTTPS :443` while the application runs `HTTP :8080`:

```text
Client  -- HTTPS/443 -->  Application Gateway  -- HTTP/8080 -->  web-01, web-02
```

If the backend runs HTTPS on 8443:

```text
Client  -- HTTPS/443 -->  Application Gateway  -- HTTPS/8443 -->  web-01, web-02
```

The frontend port **does not have to equal** the backend port. Nor do backend settings permit traffic on their own if NSGs/firewalls block the port or the app is not listening.

### Backend TLS and Hostnames

When using an **HTTPS backend**, verify:

1. The backend presents an **unexpired server certificate**.
2. Certificate SAN/CN matches the **hostname Application Gateway uses to connect and validate**.
3. The trust chain is trusted; if using a private CA, configure the appropriate trusted root certificate per service requirements.
4. The gateway can resolve the hostname and reach the right IP and port over the network.
5. The health probe uses matching host and protocol settings so it does not produce false healthy or false negative results.

For example, suppose a backend is an App Service with default hostname `store-prod.azurewebsites.net`, while the listener accepts `shop.example.com`. If App Service has not been configured with a custom domain/certificate for `shop.example.com`, having the gateway forward the frontend hostname to the backend can break TLS/host matching. You may need to pick the host name from the backend target or set an explicit matching backend hostname, then verify the application still generates URLs and cookies correctly.

If the app relies on the **original Host header**, overriding Host to satisfy the backend can affect redirects, cookies, or internal app routing. Design **frontend hostname, backend hostname, and forwarded headers** holistically instead of tweaking one field blindly just to "make 502 go away."

## 9. Request Routing Rules: Pairing Listeners with Backends

The listener accepts requests, while the **request routing rule** decides how to process them.

Two common routing types:

- **Basic rule:** uses a backend pool and backend settings to handle requests matching the listener with one logical target.
- **Path-based rule:** chooses backends via a URL path map, such as `/api/*` to the API pool and `/images/*` to the static pool.

Example for hostname `shop.example.com`:

| Listener | URL condition | Backend pool | Backend settings |
|---|---|---|---|
| `listener-shop-https` | `/api/*` | `pool-api` | HTTPS port 8443 |
| `listener-shop-https` | `/images/*` | `pool-images` | HTTP port 8080 |
| `listener-shop-https` | Remaining paths | `pool-web` | HTTPS port 443 |

In Application Gateway, this logically represents **one path-based routing rule** with a URL path map; it does not mean creating three conflicting basic rules on the same listener. In v2, request routing rules have priority ordering to avoid ambiguous matches when multiple configurations overlap.

### Redirecting HTTP to HTTPS

To redirect users visiting `http://shop.example.com` to HTTPS:

1. Create an HTTP listener on port 80 for the target hostname.
2. Create an HTTPS listener on port 443 with a valid certificate.
3. Create a **redirect configuration** from the HTTP listener to the HTTPS listener or appropriate target.
4. Attach the redirect to the HTTP listener's routing rule.
5. Choose the right redirect status code, typically permanent redirect once configuration is confirmed stable.

The port 80 HTTP listener **does not** need to point directly to a backend pool if its sole job is redirecting. The TLS handshake only occurs when the client connects via HTTPS to the port 443 listener.

Do not rely solely on redirects to claim all traffic is encrypted. Protect the HTTPS listener, apply an appropriate TLS policy, and consider HSTS once the application/domain is ready.

## 10. Health Probes: Is the Backend Truly Ready?

A **Health probe** is a periodic check sent by the gateway to backends. Only endpoints deemed **healthy** are eligible to receive requests under the gateway's load-balancing mechanism.

Probes can specify:

- **Protocol:** HTTP or HTTPS.
- **Port:** from backend settings or supported probe settings.
- **Host header:** the application/virtual host name expected by the backend.
- **Path:** e.g., `/healthz` or `/ready`.
- **Interval, timeout, and unhealthy threshold:** frequency, wait limit, and evaluation threshold.
- **Status code match:** by default typically accepts HTTP 200–399; ranges can be configured as needed.

A useful check path should respond quickly and reflect instance readiness. For example, `/ready` can check essential components required to accept traffic, but should not run heavy load-inducing queries or mutate data on every probe.

### Default Probe vs. Custom Probe

The default probe may check the root path `/` based on backend settings. If an application expects a specific hostname or returns `401/403/404` on `/`, the gateway may mark the backend **unhealthy** even though the app works on other endpoints.

The usual solution is creating a **custom probe** pointing to a health endpoint with expected responses, paired with the right host and protocol. Do not simply widen status code matching to accept 500 errors; doing so can keep broken backends marked healthy.

### Example

```http
GET /healthz HTTP/1.1
Host: shop.internal.example
```

Expected response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

ok
```

This is a logical example. In a real system, the endpoint should align with how the app publishes status, network security controls, and gateway probe behavior.

### How Do Unhealthy Backends Impact Traffic?

If a pool only has Unhealthy backends left, the gateway may have no eligible endpoints to handle requests; clients may receive **502 Bad Gateway** in those cases. However, 502s can also stem from TLS handshakes, timeouts, or communication errors, so check **Backend health** and logs before drawing conclusions.

## 11. Designing Multi-Hostname and Multi-Backend Applications

Suppose a system includes:

- Public website: `shop.example.com`.
- Public API: `api.example.com`.
- Internal admin site: `admin.corp.example`.
- Web backend with two App Services or VMs.
- API backend with three instances.
- Admin site accessible only from the corporate network.

Configuration plan:

| Component | Website | API | Admin |
|---|---|---|---|
| Client hostname | `shop.example.com` | `api.example.com` | `admin.corp.example` |
| Frontend | Public IP | Public IP | Private IP if supported by architecture/SKU, plus internal DNS |
| HTTPS listener | `lis-shop` | `lis-api` | `lis-admin` |
| TLS certificate | Covers shop | Covers API | Covers admin |
| Routing | Basic or path map | API rule | Admin rule |
| Backend pool | `pool-shop` | `pool-api` | `pool-admin` |
| Backend protocol | HTTPS | HTTPS | HTTPS |
| Health probe | `/healthz` | `/ready` | `/healthz` |

This is a **design table**, not an automatically applied configuration. Using public and private frontends simultaneously, listeners on the same port, and separate hostnames must respect SKU limits and real routing rules. Admin resources must still enforce access controls and authentication policies; a private IP only addresses network reachability scope.

### VNet/Subnet and Network Security

Application Gateway deploys into a **dedicated subnet for Application Gateway**. When sizing the subnet, account for autoscaling and the IP count instances may consume; a larger subnet—such as `/24` for architectures with significant scaling needs—generally leaves safer headroom than a small one. Check SKU/region documentation for exact limits and sizing rules.

Backends can sit in another subnet/VNet if routing permits. Configure NSGs, UDRs, Azure Firewall, and DNS properly, avoiding blocking required probe or data paths. Never deploy arbitrary application VMs inside the gateway's dedicated subnet.

## 12. WAF, Security, and HTTP Headers

**WAF_v2** adds a Web Application Firewall to inspect HTTP/HTTPS requests against policies. TLS termination lets the gateway/WAF inspect requests after decryption.

Protection layers serve different purposes:

- **TLS:** encrypts traffic and verifies server identity via certificates.
- **WAF:** detects/blocks certain Layer 7 malicious requests using rules and policies.
- **NSG/Firewall:** restricts network paths and ports.
- **Authentication/authorization:** verifies whether users or workloads are allowed to invoke functionality.
- **Application validation:** validates input data, sessions, CSRF, and business rules.

WAF does not replace user permission checks or secure source code. When testing WAF, watch for false positives and manage logs/exclusions carefully.

### Forwarded Headers and Client Addresses

Because the gateway is a reverse proxy, backends may see connections coming from the gateway rather than the client's direct IP. Application Gateway appends forwarded headers such as `X-Forwarded-For`, `X-Forwarded-Proto`, and others per service capabilities.

Applications can use these headers for logging or generating accurate URLs, but **must configure a trusted proxy list** and handle headers securely. Never blindly trust a header supplied directly by a client reaching the app through another path.

### Scheme-Induced Redirect Loops

For instance, a client uses HTTPS to the gateway, and the gateway uses HTTP to the backend. If the app only sees the internal HTTP connection and continuously redirects to HTTPS, users hit an infinite redirect loop.

How to analyze:

1. Verify the frontend is actually HTTPS.
2. Inspect backend settings and the application's redirect policy.
3. Check how the app handles `X-Forwarded-Proto`/scheme and trusted proxies.
4. Align reverse proxy and application configurations consistently instead of turning off HTTPS.

## 13. Deployment Workflow via Azure Portal

The steps below illustrate Application Gateway receiving `https://shop.example.com` and distributing traffic to web backends.

### Phase A: Preparation

1. Confirm subscription, resource group, region, and deployment permissions.
2. Prepare the VNet and **dedicated subnet for Application Gateway**; verify no address overlap.
3. Identify public/private frontend, DNS records, and target domain names.
4. Prepare the appropriate frontend certificate and secure key/certificate storage.
5. Identify backend pool, protocol/port, host header, and probe endpoint.
6. Choose v2 SKU and whether WAF is needed; estimate operational cost.

### Phase B: Create Gateway and Frontend

1. Open [Azure Portal](https://portal.azure.com/) → **Application gateways** → create.
2. Select region, VNet, subnet, SKU, and purpose-specific properties.
3. Configure public or private **Frontend IP** per architecture.
4. Create or select **Frontend port** 443 for HTTPS.

### Phase C: Create Backend Pool and Settings

1. Create `pool-shop` with two or more appropriate backend IPs/FQDNs.
2. Create backend settings choosing HTTPS port 443 (or the actual backend port).
3. Select appropriate hostname/backend TLS validation settings.
4. Create custom probe `/healthz` with expected host and response, then attach it to backend settings.
5. Verify routing, NSGs, and DNS allow the gateway to reach backends.

### Phase D: Create Listener, Rule, and DNS

1. Create HTTPS listener `listener-shop-https` on frontend IP:443 with hostname `shop.example.com`.
2. Attach the frontend TLS certificate.
3. Create a request routing rule linking the listener to `pool-shop` and corresponding backend settings.
4. If HTTP→HTTPS is needed, create a port 80 HTTP listener and a separate redirect configuration.
5. Create appropriate DNS records so `shop.example.com` resolves to the gateway's public IP/FQDN or private IP in internal DNS.

### Phase E: Verification

1. Open `https://shop.example.com/healthz` (if permitted from clients) or the main application URL.
2. Confirm browsers report no certificate, hostname, or CA chain errors.
3. Check **Backend health**: each endpoint is healthy and receiving requests.
4. Test URL routing, HTTP→HTTPS redirects, and API endpoints if present.
5. Temporarily remove one backend under a safe test procedure to confirm remaining backends continue serving.
6. Verify access logs, WAF logs (if used), metrics, and alerts.

Creating Application Gateway, WAF, or certificates can incur costs and requires proper permissions; changes in real environments should only run within authorized project scope.

## 14. Inspecting Current State with Azure CLI

The illustrative commands below are **read-only**, handy for inspecting a deployed environment. Substitute your real gateway and resource group names.

### Check Subscription

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### List Gateways

```bash
az network application-gateway list \
  --resource-group "rg-app-delivery" \
  --output table
```

### View Overall Configuration

```bash
az network application-gateway show \
  --name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

### View Listeners and Backend Pools

```bash
az network application-gateway http-listener list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table

az network application-gateway address-pool list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table
```

### View Backend Settings, Probes, and Rules

```bash
az network application-gateway http-settings list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json

az network application-gateway probe list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output table

az network application-gateway rule list \
  --gateway-name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

### View Backend Health

```bash
az network application-gateway show-backend-health \
  --name "agw-shop" \
  --resource-group "rg-app-delivery" \
  --output json
```

Backend health typically shows which endpoints are Healthy/Unhealthy and corresponding diagnostic details. When automating, check parameter names for your installed CLI version using `az network application-gateway --help` or `... <subcommand> --help` before building pipelines.

Read-only configuration commands **do not replace testing live requests from clients**. Also cross-check DNS, network access, and backend logs when troubleshooting errors.

## 15. Failure Scenarios and Diagnostics

| Symptom | Possible cause | Verification steps |
|---|---|---|
| Browser reports invalid certificate | Expired frontend cert, missing chain, hostname mismatch | Inspect HTTPS listener, certificate, SANs, and expiration |
| Domain A works but domain B fails | Multi-site listener host/SNI or DNS/rule misconfigured | Check hostname, listener, DNS, and rule priority |
| Client receives 502 | Backend Unhealthy, backend TLS failure, timeout, or upstream error | Check Backend health, probes, backend certs, NSGs, access logs |
| Pool has backends yet zero requests succeed | Missing routing rule/settings link, unreachable backend | Check listener→rule→pool/settings and network path |
| Probe reports Unhealthy yet direct backend access works | Probe has wrong Host/path/protocol/port, health endpoint returns out-of-range status | Create matching custom probe, inspect HTTP status |
| Gateway forwards request to backend yet app returns 404 | Wrong backend Host header or path routing | Inspect backend hostname, URL path map, and app routes |
| Infinite HTTP→HTTPS redirect loop | App does not detect real scheme, wrong proxy trust | Inspect redirects and forwarded proto |
| Backend HTTPS certificate error | Backend cert untrusted or hostname mismatch | Compare backend settings, SNI, CA chain, certificate names |
| Rising load causes slowness or errors | Under-provisioned backends, suboptimal autoscale/timeouts | Inspect latency, CPU, gateway metrics, logs, and backend health |
| WAF blocks valid requests | False positive rule or policy-violating request | Inspect WAF logs, rule IDs, and tune carefully |
| Only internal network can reach site | Private frontend, DNS/routing, or NSG restriction | Check client source and frontend design |
| App Service generates URLs with wrong hostname | Inconsistent backend host override or proxy headers | Check frontend host, backend host, cookies, redirects |

### 502 Troubleshooting Procedure

1. Record UTC timestamp, hostname, URL path, HTTP code, and correlation/transaction ID if logged.
2. Confirm DNS for the hostname resolves to the correct frontend.
3. Check that the HTTPS listener and rule point to the right pool/settings.
4. Open **Backend health** and see which endpoints are Unhealthy; read the reported reason.
5. Check the probe: protocol, port, host, path, and status code.
6. Check network connectivity between gateway and backend: NSGs, routes, DNS, firewalls, and listening ports.
7. If backends use HTTPS, verify certificate, CA chain, hostname, and TLS status.
8. Inspect gateway access logs, backend logs, and request processing times.
9. After fixing the root cause, verify health turns Healthy and re-test client requests.

Do not immediately conclude "frontend TLS is broken" upon seeing a 502. If the client completed the HTTPS handshake with the gateway and the request to the backend failed, the cause usually lies in the **backend path** or application. Conversely, a browser certificate error before any HTTP response signals you should inspect the **frontend listener/certificate**.

## 16. Monitoring, Availability, and Cost

### Monitoring

Configure Azure Monitor metrics and diagnostic settings per Application Gateway support, such as:

- **Healthy/Unhealthy host count** in each pool.
- **Total requests, failed requests, HTTP 4xx/5xx** as exposed by the service.
- **Response time/latency** and backend response outcomes.
- **WAF logs**, if deploying `WAF_v2`.
- **Access logs** showing host, path, status, and request details.
- **Certificate lifecycle** and Key Vault connectivity when using Key Vault certificate integration.

Distinguish **4xx responses legitimately rejected by the app** from **5xx errors caused by gateway or backend failures**. Not every 404 indicates an infrastructure outage.

### Availability

To improve serving resilience:

1. Maintain at least two healthy backends when the app supports horizontal scaling.
2. Spread instances across fault domains/availability zones where supported by the service and region.
3. Use health probes that reflect actual readiness.
4. Deploy the gateway with scaling and availability settings aligned to the SKU.
5. Confirm backends operate independently if one instance drops.
6. If cross-region DR is required, design a dedicated multi-region distribution architecture, such as Front Door or an appropriate DNS/traffic routing mechanism.

Application Gateway is a **regional** service; a single gateway does not turn an application into a multi-region service. Multiple backend instances also do not help if all instances share another single point of failure.

### Cost

Factors to consider include `Standard_v2`/`WAF_v2` SKU charges, capacity/autoscale units, data processed, public IPs, Azure Key Vault, backend compute, log ingestion/retention, and companion security services. Pricing varies by SKU and region, so use Azure pricing tools with estimated traffic profiles rather than inferring costs from lesson examples.

To control costs, separate gateways along sensible security/governance boundaries—avoid spinning up a dedicated gateway for every tiny app when multiple listeners/rules can safely share one, while avoiding cramming strictly isolated workloads onto a single gateway purely to save money.

## 17. Lab Exercise: From Listener to Backend Pool

**Context:** A team deploys website `shop.example.com`. Azure Application Gateway accepts HTTPS from the Internet. Two backend VMs have private IPs in the VNet:

| Parameter | Illustrative value |
|---|---|
| Frontend hostname | `shop.example.com` |
| Frontend protocol/port | HTTPS / 443 |
| Frontend certificate | Valid certificate for `shop.example.com` |
| Backend pool | `pool-shop` |
| Backend 1 | `10.20.1.10` |
| Backend 2 | `10.20.1.11` |
| Backend protocol/port | HTTPS / 8443 |
| Backend hostname | `shop.internal.example` |
| Custom probe | HTTPS `/healthz` with Host `shop.internal.example` |
| Routing | Basic rule to `pool-shop` |
| Redirect | HTTP / 80 → HTTPS / 443 |

**Tasks:**

1. Trace the request path from DNS to frontend IP, listener, routing rule, backend pool, and both backends.
2. Indicate where TLS session A ends and TLS session B begins.
3. Explain why frontend and backend certificates must be validated **independently**.
4. List the backend settings properties needed for `HTTPS :8443`.
5. Create a health probe checklist and define a Healthy response.
6. Suppose VM1 stops serving while VM2 stays healthy: predict routing behavior and how to observe it.
7. Suppose both VMs report Unhealthy even though calling the app directly works: propose an investigation order.
8. Outline monitoring for certificate expiry, Backend health, and 5xx errors.

### Reference Solution

**Processing flow:**

```text
Client / DNS
    |
    | HTTPS/TLS A :443, host shop.example.com
    v
Application Gateway
    |
    +-- HTTPS listener (cert for shop.example.com)
    |
    +-- Basic routing rule
    |
    +-- Backend pool: 10.20.1.10, 10.20.1.11
    |
    +-- Backend settings: HTTPS :8443
    |                       Host shop.internal.example
    |                       Custom probe /healthz
    |
    +==== TLS B ====> Healthy backend: shop.internal.example
```

TLS A terminates at the gateway; TLS B connects the gateway to the backend and is validated using a trusted backend certificate matching the expected hostname. The backend cannot present a certificate valid only for `api.other.example` if the gateway validates `shop.internal.example`.

**Health:** the probe should use HTTPS port 8443, Host `shop.internal.example`, path `/healthz`, and expect responses within the valid status range. An Unhealthy VM1 will not be selected for requests under the gateway's mechanism while VM2 remains healthy. If both are Unhealthy, check the probe first, then connectivity, TLS, and the application; never disable certificate validation to hide the issue.

**Acceptance:** requests to `https://shop.example.com` show no TLS errors; HTTP port 80 redirects to HTTPS; Backend health displays accurate statuses; requests through the remaining backend succeed when the other backend is stopped in testing; logs correlate requests and error causes.

## 18. Knowledge Check

**Question 1.** What does TLS termination at Application Gateway mean?

A. The gateway forwards the entire TLS session untouched without reading HTTP.  
B. The gateway terminates client TLS so it can inspect HTTP and perform Layer 7 routing.  
C. Backend certificates are no longer needed under any circumstances.

**Answer: B.** If the backend also uses HTTPS, the gateway establishes a separate TLS session to the backend.

**Question 2.** Which pair of components determines which backend and protocol/port a listener sends requests to?

**Answer:** **Request routing rule** selects the backend pool and **backend settings**. The listener only defines the incoming entry point.

**Question 3.** One gateway serves two hosts on the same frontend IP:443. What component distinguishes the websites?

**Answer:** **Multi-site listeners** with corresponding hostnames, combined with SNI and matching certificates for HTTPS.

**Question 4.** An HTTPS backend returns a certificate for `internal.example.com`, while backend settings validate `shop.example.com`. What issue can occur?

**Answer:** Hostname mismatch during backend certificate validation, causing TLS handshakes or health checks to fail. Keep hostnames and backend certificates consistent.

**Question 5.** A probe sends GET `/` and gets 401, yet the app returns 200 at `/healthz`. What should you do?

**Answer:** Configure a custom health probe using the right host/protocol/port/path, such as `/healthz`, and verify the endpoint genuinely reflects readiness.

**Question 6.** Both backends are Unhealthy. Will creating another listener fix the issue?

**Answer:** No. Check network reachability, backend settings, hostnames, certificates, probes, and the application. Listeners do not replace backend health.

**Question 7.** Does HTTPS frontend + HTTP backend mean the entire transmission path is protected by TLS?

**Answer:** No. The gateway → backend hop is unencrypted HTTP. Use an HTTPS backend if policy requires two-hop encryption.

**Question 8.** Can Azure Load Balancer read URL path `/api/*` and route by path like Application Gateway?

**Answer:** No. Azure Load Balancer operates at Layer 4 and does not perform HTTP path routing.

**Question 9.** Why do applications sometimes enter an infinite redirect loop after placing Application Gateway in front?

**Answer:** The application may assume the original request used HTTP because the gateway → backend hop is HTTP. Configure forwarded scheme/headers and trusted proxies properly, and review redirect rules.

**Question 10.** Does Application Gateway WAF replace authentication and authorization inside the application?

**Answer:** No. WAF mitigates certain Layer 7 HTTP risks; the application must still authenticate users and enforce permissions on every action.

A reliable HTTPS delivery architecture properly pairs **certificate → frontend listener → routing rule → backend pool + settings → health probe**. When troubleshooting, pinpointing whether the fault lies in **frontend TLS**, **routing**, or **backend connectivity/TLS/health** makes investigation faster and safer.
