# Diagnosing TLS, Health Probe, and HTTP Gateway Failures

> **Chapter:** Load Balancing and Application Delivery  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control the cost of an application architecture on Azure.

## Learning Objectives

After this lesson, you will be able to:

1. Trace the path of an HTTPS request through **Azure Application Gateway** and pinpoint where failures can occur.
2. Distinguish TLS failures on the **client → gateway** connection from TLS failures on the **gateway → backend** connection.
3. Explain how **health probes** classify backends as `Healthy`, `Unhealthy`, or `Unknown`, and why a running app can still be marked unhealthy.
4. Analyze HTTP `502`, `503`, `504`, certificate errors, redirects, WAF blocks, and common DNS/network issues.
5. Use the Azure portal, Azure CLI, `curl`, `openssl`, and Azure Monitor to isolate root causes with evidence.
6. Follow a safe remediation workflow with post-change verification and monitoring.

## 1. Which Layers Does an HTTPS Request Pass Through?

Suppose an organization deploys an API site on Azure:

- Users visit `https://api.contoso.example/orders`.
- **Azure Application Gateway** receives HTTPS on a public frontend IP.
- **Listener** listens on port 443 and selects the site by hostname.
- **Request routing rule** directs the request to a backend pool.
- The backend pool contains two VMs or application endpoints on a private network.
- Backend HTTP settings specify HTTP/HTTPS protocol, port, timeout, hostname, and probe.
- Health probes check backends; the gateway routes only to backends evaluated as available per configuration.

~~~mermaid
flowchart LR
    C["Client\nBrowser / curl"]
    F["Frontend IP :443"]
    L["HTTPS listener\nCert + host name"]
    R["Routing rule\nURL path / host"]
    H["Backend settings\nHTTP(S), port, host"]
    P["Health probe\nHealthy?"]
    B["Backend pool\nAPI 10.20.2.4 / 10.20.2.5"]
    DB["Database / dependencies"]
    C -->|"TLS #1"| F --> L --> R --> H
    H -->|"TLS #2 if HTTPS backend"| B --> DB
    P -.->|"Evaluates endpoint"| B
    P -.->|"Influences backend selection"| R
~~~

This is a logical diagram: health probes run independently of user requests. Individual requests do not wait for a probe cycle to finish.

### Two TLS Connections in the End-to-End HTTPS Model

When both frontend and backend use HTTPS, **Application Gateway terminates client TLS and establishes a separate TLS connection to the backend**. This is not a single unbroken TCP/TLS stream straight from the browser to the backend server.

| Connection | Certificate-presenting endpoint | Validated name | Commonly observed errors |
| --- | --- | --- | --- |
| **Client → Gateway** | Certificate bound to the HTTPS listener | Domain users visit, e.g., `api.contoso.example` | Browser certificate warnings, TLS handshake failure; request may never reach the HTTP gateway |
| **Gateway → Backend** | Certificate presented by the backend server | Hostname/SNI matching backend settings and probe | Gateway fails to establish HTTPS, backend `Unhealthy`, potentially returning `502` |

If the backend uses **HTTP**, TLS applies only on the frontend; traffic from gateway to backend is not TLS-encrypted on that leg. Choosing HTTP vs. HTTPS backends must match security requirements and internal architecture.

### Differences Among Three Easily Confused Azure Services

| Component | Primary layer | Role of health checks / TLS | Scenarios |
| --- | --- | --- | --- |
| **Azure Application Gateway** | L7 HTTP/HTTPS | HTTPS listeners, TLS termination, backend HTTPS, probes per HTTP settings | Regional websites/APIs, path-based routing, WAF |
| **Azure Front Door** | L7 at global edge | Client-side TLS and origin connections, origin health probes; config names and logs differ from Application Gateway | Multi-region apps, CDN/edge routing, WAF |
| **Azure Load Balancer** | L4 TCP/UDP | Does not terminate application TLS; probes check endpoints per supported types | TCP/UDP connection balancing, no URL-path HTTP routing |

This lesson uses **Application Gateway** as the primary example. When troubleshooting Front Door or Load Balancer, keep the layered mindset while checking the health probes, certificates, and telemetry **of that specific product**.

## 2. Classifying Failures from the First Signal

Users often report "HTTPS is broken" or "the gateway is down," yet symptoms can mean very different things.

| Symptom | Layer to check first | Preliminary explanation |
| --- | --- | --- |
| Browser shows `ERR_CERT_AUTHORITY_INVALID` | Frontend TLS | Certificate is not trusted by the client |
| `ERR_CERT_COMMON_NAME_INVALID` or domain mismatch | Frontend TLS | Certificate does not cover the hostname |
| `curl` reports TLS handshake failure | TLS/ciphers/version, SNI, network path | Not yet clear whether frontend or backend until connection point is checked |
| HTTP `502 Bad Gateway` | Gateway ↔ backend, backend health, backend TLS | Gateway received no valid upstream response or has no usable backend depending on cause/product |
| HTTP `503 Service Unavailable` | Backend availability, quota, or origin/service | Potentially no healthy backends, overloaded service, or another product on the path |
| HTTP `504 Gateway Timeout` | Gateway/origin timeout | Upstream did not respond before deadline; separate request timeout from probe timeout |
| HTTP `401/403` | Authentication, authorization, WAF, or probe | Request likely reached the app/WAF; not automatically a TLS failure |
| HTTP `301/302` | Backend redirect or routing rule | Could be normal behavior or a redirect loop |
| Some URLs work, others fail | Path-based rules, backend pools, app endpoints | Different paths may map to different backends/settings |
| Backend `Unhealthy` yet direct VM calls work | Probe path, hostname, TLS/SNI, source, routing | Probe requests can differ from manual test requests |
| Backend `Unknown` | Gateway state / probe path / telemetry | Inspect details; do not assume the app is dead |

**The first question to answer:** did the failure happen **before an HTTP response was received**, or did the gateway return an HTTP status code? Browser certificate errors usually happen before HTTP; a `502` is an HTTP response showing traffic progressed farther down the pipeline.

### Five-Point Isolation Sequence

1. **DNS and network path:** does the user's domain resolve to the right gateway frontend?
2. **Frontend listener/TLS:** does the listener have the right host, port, certificate, and TLS policy?
3. **Routing:** which backend pool and settings do the URL path, host, and rules select?
4. **Backend health:** does the gateway actually see the backend as Healthy or Unhealthy, and why?
5. **Backend and dependencies:** is the server listening on the right port, returning valid HTTP, presenting the right cert, and reaching its database/dependencies?

Multiple issues can occur at once. To avoid fixing the wrong thing, always run a check that proves which layer failed.

## 3. How Does TLS Work at the Frontend?

### 3.1. Role of Certificates and the TLS Handshake

When a client visits `https://api.contoso.example`, the browser connects to the gateway on port 443 and sends TLS metadata, typically including **Server Name Indication (SNI)** to specify the requested hostname. The gateway picks the matching certificate/listener per configuration.

The client then validates:

- Whether the certificate was issued for `api.contoso.example` or lists it in **Subject Alternative Name (SAN)**.
- Whether the certificate is within its validity window and chains to a CA trusted by the client.
- Whether the TLS protocol/cipher is mutually supported and not blocked by policy.
- Any additional app/client security checks depending on environment.

**SAN** is the first field to inspect when checking hostname match; never rely merely on a `.pfx` filename or certificate label in the Azure portal.

### 3.2. Common Frontend TLS Errors

| Cause | Symptom | How to verify |
| --- | --- | --- |
| Expired or not-yet-valid certificate | Browser shows validity/certificate error | Check `Not Before`, `Not After`, and system clock |
| SAN does not match FQDN | Hostname mismatch | Compare accessed hostname against SAN entries |
| Incomplete CA chain or untrusted private CA | Client reports authority/chain error | Inspect server-sent chain and client trust store |
| Listener bound to wrong certificate | One hostname fails while another works | Inspect multi-site listeners, hostnames, bindings, and SNI |
| TLS policy too restrictive for clients | Handshake failure, no HTTP response | Check TLS versions/ciphers on both sides with a compliant TLS client |
| DNS points to wrong frontend | Another system's certificate is returned | `nslookup`/`dig`, public IP, listener |
| Key Vault rotation issue | Frontend breaks after cert change | Check version/secret, managed identity, permissions, and gateway state |

For Application Gateway HTTPS listeners, certificates are typically configured from a PFX or Key Vault integration depending on SKU capabilities. The certificate must include a valid private key usable by the gateway. A `.cer` file containing only the public certificate **cannot replace** the PFX needed for listener TLS termination.

### 3.3. Distinguishing SNI from HTTP Host

Both relate to domain names, yet occur at **two different stages**:

- **TLS SNI:** domain name sent by the client during the handshake so the server picks the right certificate/TLS context.
- **HTTP Host header:** domain name inside the HTTP request after TLS is established, used by the gateway or backend for virtual-host routing.

A client can send one SNI and a different HTTP Host; depending on gateway, listeners, and routing rules, the request can land on the wrong site or get rejected. Backends may also rely on a Host header different from the public name.

**Therefore:** "A valid certificate" does not prove routing is right; "the right Host header" does not prove the backend HTTPS handshake works.

## 4. TLS from Application Gateway to Backends

### 4.1. Why Does Backend HTTPS Frequently Cause 502s?

Example:

- Users call `https://api.contoso.example`.
- The HTTPS listener uses a public cert with SAN `api.contoso.example` — completely valid.
- The routing rule forwards to backend `api.internal.contoso.example:443`.
- The backend certificate has SAN `api.internal.contoso.example`.
- Backend settings instead send/expect hostname `10.20.2.4` or `api.contoso.example`.

The gateway fails to validate the backend certificate because **the hostname mismatches the certificate**, or because the CA chain is untrusted. HTTPS health probes fail for the exact same reason.

Backend TLS steps involved:

1. Does the gateway have a network route to the backend IP and port?
2. Does the backend accept the TLS protocol/ciphers offered by the gateway?
3. Does the backend connection's hostname/SNI match the backend certificate?
4. Is the certificate valid and its CA chain trusted by the gateway per configuration?
5. After TLS succeeds, does the backend accept the HTTP Host/path sent by the gateway?

**Never fix a backend certificate error by changing the frontend listener certificate** unless it truly is the same certificate and you verified the root cause.

### 4.2. Backend Settings and Hostname Override

In Azure Application Gateway, backend settings can specify:

- Protocol: `HTTP` or `HTTPS`.
- Port: e.g., `80` or `443`.
- Backend hostname: configured explicitly, taken from backend address, or overridden depending on scenario.
- Trusted root certificates when backends use a private CA and the SKU/config requires them.
- Request timeout and custom health probe.

For HTTPS backends, **the hostname used for certificate validation and SNI must align consistently with the backend cert**. For virtual-host apps, the Host header must also match the site the server hosts.

Conceptual configuration example:

~~~text
Frontend:       https://api.contoso.example:443
Listener cert:  SAN = api.contoso.example

Backend pool:   10.20.2.4, 10.20.2.5
Backend HTTPS:  port = 443
Backend host:   api.internal.contoso.example
Backend cert:   SAN = api.internal.contoso.example
Health probe:   HTTPS /ready, host = api.internal.contoso.example
~~~

If the pool lists private IPs while the certificate is issued to an FQDN, do not leave TLS verification using the raw IP. Configure backend host and probe settings properly to prevent mismatches.

### 4.3. Public CAs vs. Internal CAs

If the backend certificate is signed by a **public CA trusted by the gateway**, Application Gateway v2 validates it via the service's trusted CA store. If the backend uses a **Private CA**, configuring the proper trusted root certificate in backend settings may be required.

When inspecting certificate chains:

- Confirm the **leaf** certificate has a matching SAN and is unexpired.
- Check that required **intermediate CAs** are presented properly.
- Identify where the **root CA** must be trusted (frontend clients differ from gateway backends).
- Verify the backend actually serves the new cert after rotation.
- Never disable certificate validation in production just to "make requests go through."

### 4.4. TLS Policy Is Not Health Policy

**TLS policy** governs protocols/ciphers and connection security strength. **Health probes** govern whether a backend endpoint is considered available. A backend can fail probes because:

- TLS fails due to cert/hostname mismatch.
- TLS succeeds, yet the probe URL returns HTTP `401`.
- Both TLS and HTTP work, yet the probe times out because the endpoint is too slow.

Diagnostics must inspect the exact **Unhealthy reason** and correlate it with TLS and HTTP path tests.

## 5. What Do Health Probes Check?

### 5.1. Basic Mechanics

Application Gateway continuously sends probes to backend targets per the **probe configuration** linked to backend settings. The gateway uses results to decide which backends enter load balancing.

Key attributes:

| Property | Meaning | Common misconfigurations |
| --- | --- | --- |
| **Protocol** | HTTP or HTTPS | Backend listens on HTTPS while probe sends HTTP |
| **Port** | Probed port; from backend settings or dedicated port | API runs on 8443 while probe checks 443 |
| **Host** | Hostname used in probe; affects HTTP virtual hosts and HTTPS | Default host mismatches backend virtual host/certificate |
| **Path** | Requested path such as `/healthz` | Using `/` returns 401/404 or unwanted redirects |
| **Interval** | Probe frequency | Too long delays detection; too short raises load |
| **Timeout** | Wait time per probe | Service responds slower than timeout |
| **Unhealthy threshold** | Consecutive failures before marking unhealthy | Misaligned with desired sensitivity |
| **Healthy status match** | Accepted HTTP status codes | Probe returns a code outside accepted range |
| **Body match** (if used) | Expected substring in response | Endpoint changed response body format |

For **Application Gateway**, the default HTTP match range typically accepts **200–399** for standard probes, though you should verify your exact gateway type and custom probe configuration. Do not apply this rule blindly to **Azure Load Balancer** or **Front Door**, as each has its own probe semantics.

### 5.2. Default Probe vs. Custom Probe

Application Gateway's default probe may send a **default Host header** and path `/`. For many modern apps:

- The app only responds properly when Host is `api.internal.contoso.example`.
- `/` returns `404` because the API lives under `/v1`.
- `/` redirects users to login, returning `401` or a redirect.
- The backend HTTPS certificate does not match the default hostname.
- The backend runs on a non-default port or path.

In those cases, the default probe marks the backend **Unhealthy** even though operators running `curl` against another URL see the API working.

A **custom probe** usually fits HTTPS backends and virtual-host applications better. Example:

~~~text
Probe name:     probe-api-ready
Protocol:       HTTPS
Host:           api.internal.contoso.example
Path:           /ready
Port:           443 (or inherit port from backend settings)
Interval:       30 seconds (example)
Timeout:        20 seconds (example)
Healthy codes:  200–399, or agreed range
Expected:       HTTP 200 when backend is ready to accept requests
~~~

The seconds shown are **design examples**, not guaranteed defaults across every SKU/version. Choose values based on SLOs, latency, and application behavior.

### 5.3. Distinguishing Liveness, Readiness, and Dependency Checks

A good health endpoint tells the gateway **whether the backend should accept new requests**:

- **Liveness:** is the process running? May return 200 even before the backend can serve requests.
- **Readiness:** has the backend initialized, can it accept requests, and are mandatory components ready?
- **Deep dependency check:** tests numerous dependencies. If too heavy or tied to non-essential services, a brief blip can mark every backend Unhealthy.

For example, a Node.js or Java API exposes `/ready` returning HTTP 200 once startup completes and essential dependencies are reachable. This endpoint should be **fast, stable, require no interactive login**, and expose only necessary information. Restrict access via network policies rather than requiring user login sessions for probes.

### 5.4. Probe Timeout Is Not Request Timeout

- **Probe timeout:** how long the gateway waits for a health check before counting that attempt as failed.
- **Backend request timeout:** how long the gateway waits for a user request's response from the backend.

`/ready` might respond in 100 ms while a report export endpoint takes 70 seconds and hits a 30-second backend request timeout. **The backend stays Healthy**, yet users see `502` or `504` depending on behavior/device. Do not tweak probe timeouts when the real issue is request execution time.

## 6. Causes of Unhealthy Backends

### 6.1. Wrong Network Path or Port

Application Gateway health probes originate from gateway infrastructure and must reach backend endpoints over the network. Common issues:

- Backend NSG/firewall blocks traffic from the Application Gateway subnet to the app port.
- Route tables (UDRs) or intermediate network appliances misroute traffic.
- Backend listens only on `127.0.0.1` instead of the interface the gateway reaches.
- Backend service is stopped or listening on a different port.
- DNS returns a stale IP or one unreachable from the gateway network.
- Backend pool lists the wrong address/hostname.

Inspecting the Application Gateway subnet and NSGs must follow the platform requirements for your SKU. Never delete entire NSGs or open permissions broadly just to test failures.

### 6.2. Wrong HTTP Status or Redirects

Example:

~~~text
GET /                → 404
GET /ready           → 200
GET /account         → 302 to /login
GET /api/private     → 401 without token
~~~

If the default probe hits `/`, the backend can be marked Unhealthy. The proper fix is configuring a custom probe to `/ready`, ensuring the endpoint genuinely represents serving readiness.

If a probe receives `301/302` and the matcher includes those codes, the gateway may treat the backend as Healthy **even if the redirect target is broken**. Relying on broad status codes alone is risky; a readiness endpoint should return an explicit code like `200` when ready.

### 6.3. Host Header and SNI Mismatch

Suppose a backend runs Nginx with virtual hosting:

~~~nginx
server {
    listen 443 ssl;
    server_name api.internal.contoso.example;

    ssl_certificate     /etc/nginx/certs/api-fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/api-key.pem;

    location = /ready {
        return 200 "ready\n";
        add_header Content-Type text/plain;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

This snippet is a **backend illustration**, not an instruction to edit live machines. If the probe sends `Host: 127.0.0.1` or a mismatched SNI, Nginx may serve a default server block with a different certificate or routes. Check the host in both probes and backend settings, along with how Nginx maps TLS server blocks.

### 6.4. Untrusted Backend Certificate

Backend health messages may report certificate errors such as unable to verify certificate chain or common name mismatch. When this happens:

1. Inspect the exact certificate presented by the backend.
2. Compare SANs against the hostname the gateway uses.
3. Check expiration dates and the full chain.
4. Check whether backend settings include the proper trusted root certificate when using a private CA.
5. Check whether the custom probe uses the same protocol/host/port.

Do not confuse "my laptop browser trusts the CA" with "the gateway trusts the backend CA." The two sides use different trust stores and validation contexts.

### 6.5. Application or Resource Failures

Health endpoints can return `500`, `503`, or time out when:

- The API is still booting after a deployment.
- Thread pools, CPU, memory, or connection pools are exhausted.
- A mandatory database is unreachable.
- Pods/containers/VMs crashed or are recycling.
- The probe endpoint depends on a slow third-party service.

Correlate application logs, deployment timelines, resource metrics, and Healthy/Unhealthy counts to tell whether the fault started in the backend or the gateway.

## 7. Real-World Diagnostics with Azure Portal and Azure CLI

### 7.1. Verify Subscription, Gateway, and Backend Health

The following commands are **read-only**, suitable for inspecting an authorized environment:

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Select the right authorized subscription if needed.
az account set --subscription "<SUBSCRIPTION_ID>"

# Verify target gateway and provisioning state.
az network application-gateway show \
  --resource-group rg-edge-prod \
  --name appgw-api-prod \
  --query "{name:name, location:location, provisioningState:provisioningState}" \
  --output json

# View status of each backend as evaluated by Application Gateway.
az network application-gateway show-backend-health \
  --resource-group rg-edge-prod \
  --name appgw-api-prod \
  --output json
~~~

Replace resource group and gateway names with real targets. Backend health output can list targets, status, and detailed messages. Record the exact **reason/message**, observation timestamp, and associated backend settings.

**In the portal:** open **Application Gateway → Backend health** (or the corresponding backend status view). If a pool has two backends and only one is Unhealthy, inspect that specific target first. If all turn Unhealthy right after a settings/probe change, suspect shared configuration first.

### 7.2. Cross-Check Listeners, Rules, Backend Settings, and Probes

~~~bash
# HTTPS listeners: hostnames and linked frontends.
az network application-gateway http-listener list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Routing rules: which listener maps to which backend pool/settings.
az network application-gateway rule list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Backend protocol, port, host override, and timeout.
az network application-gateway http-settings list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json

# Probe path, protocol, host, status match, and timeout.
az network application-gateway probe list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json
~~~

These commands assume an Azure CLI version supporting this command group. If parameter names differ in your version, check `az network application-gateway ... --help`. Never run `update` commands merely to inspect.

### 7.3. Inspect Listener Certificates

~~~bash
az network application-gateway ssl-cert list \
  --resource-group rg-edge-prod \
  --gateway-name appgw-api-prod \
  --output json
~~~

This lists configuration metadata; **by default it does not reveal private keys, full certificates, or all CA verification details**. Combine it with client-side TLS queries and portal listener inspection.

### 7.4. Document Configuration Relationships

A short table prevents misreading rules:

| Component | Example | What to verify |
| --- | --- | --- |
| Public FQDN | `api.contoso.example` | DNS points to the right frontend |
| Listener | `listener-api-443` | HTTPS, host, cert, port |
| Rule | `rule-api` | Rule priority, path, pool/settings |
| Backend pool | `pool-api` | Both expected backends `10.20.2.4/.5` |
| Backend settings | `https-api-443` | HTTPS, 443, host, timeout |
| Probe | `probe-api-ready` | HTTPS, `/ready`, right hostname |
| Backend health | Healthy/Unhealthy | Reason per server |

If using a URL path map, inspect the **exact path users request** and the backend settings that path selects. A gateway may have a healthy primary listener while a rule routes `/admin/*` to another broken pool.

## 8. Testing from Clients and from the Backend Network

### 8.1. Test Public DNS and HTTP/TLS

~~~bash
# Check which address public DNS returns.
nslookup api.contoso.example

# Check status and response headers, following redirects.
curl -I -v https://api.contoso.example/

# Call a real endpoint; avoid -k during standard certificate checks.
curl -v https://api.contoso.example/ready
~~~

Record hostname, resolved IP, HTTP status, certificate name, timings, and response headers. `curl -I` sends a HEAD request; if the app does not support HEAD, use `curl -v` with GET. If another gateway or CDN sits in front of Application Gateway, verify which device actually handled the request.

### 8.2. Target a Specific Frontend IP While Preserving Hostname/SNI

During DNS migrations, you may need to test a listener at one specific IP:

~~~bash
# 203.0.113.10 is a documentation IP; replace with your real frontend IP.
curl -v \
  --resolve api.contoso.example:443:203.0.113.10 \
  https://api.contoso.example/ready
~~~

`--resolve` forces the connection to the specified IP while keeping the URL hostname for SNI and HTTP Host. This is far better than `curl https://203.0.113.10` when certificates are issued for an FQDN.

If you ever use `-k`/`--insecure` for diagnosis, it proves only that the app responds **when certificate validation is skipped**; never treat it as a production fix or proof of valid TLS.

### 8.3. Inspect Backend Certificates

From an **authorized test VM with network reachability to backends**:

~~~bash
# Connect to private IP while sending SNI matching the backend cert hostname.
openssl s_client \
  -connect 10.20.2.4:443 \
  -servername api.internal.contoso.example \
  -showcerts
~~~

In the output, inspect subject/SAN, issuer, validity dates, chain, and handshake errors. Note that `openssl s_client` may print the chain without aborting the connection even when verification fails; read the verify return code or pass verification flags.

Verify hostname explicitly with an OpenSSL version that supports it:

~~~bash
openssl s_client \
  -connect 10.20.2.4:443 \
  -servername api.internal.contoso.example \
  -verify_hostname api.internal.contoso.example \
  -verify_return_error
~~~

The trust store on the VM running OpenSSL **can differ from Application Gateway's trust store**. This test helps catch errors, though it does not by itself prove the gateway trusts the backend certificate.

### 8.4. Test HTTP Path and Host Directly on Backends

~~~bash
# Use the proper TLS hostname while pinning the backend IP.
curl -v \
  --resolve api.internal.contoso.example:443:10.20.2.4 \
  https://api.internal.contoso.example/ready
~~~

What to observe:

- Does the HTTPS handshake succeed?
- Does the backend certificate SAN match the hostname?
- What status does `GET /ready` return?
- Is the response faster than the probe timeout?
- Does backend `10.20.2.5` produce the same result?

**Do not generalize from one backend to the entire pool.** If one machine is configured differently, the gateway can return intermittent errors depending on which instance handles the request.

### 8.5. Check TCP Connectivity Without OpenSSL

In Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName api.internal.contoso.example -Port 443
~~~

On Linux:

~~~bash
nc -vz api.internal.contoso.example 443
~~~

These commands check TCP reachability from the current machine; **they do not validate TLS certificates or HTTP responses**. Success from a laptop/VPN does not prove the Application Gateway subnet shares the same network path.

## 9. Interpreting HTTP 502, 503, and 504 in Context

### 9.1. 502 Bad Gateway

In applications behind Application Gateway, a 502 normally prompts checking:

- Does the backend pool have any Healthy backends?
- Do gateway-to-backend port and protocol match?
- Is the backend TLS handshake failing due to cert chain/SNI/hostname?
- Did the backend send an invalid HTTP response or reset the connection?
- Is there network reachability between gateway and backend?
- Was there a recent deployment or backend crash?

**A 502 is not always caused by certificates.** Always inspect backend health details, access logs, and change timelines.

### 9.2. 503 Service Unavailable

A 503 can be returned by the gateway/front door/origin or **by the backend application itself**. The critical step is identifying **who emitted the status code**. Fields to look for in logs typically include frontend status, backend/origin status, backend server, route, and transaction/correlation ID.

If a backend returns `503` during maintenance, the gateway may forward that code to clients even though the gateway itself is healthy. On certain products/paths, 503 also appears when no origin is available or the system is overloaded. Never rely on the status code alone to pinpoint the cause.

### 9.3. 504 Gateway Timeout

A 504 raises the question: which upstream **failed to finish the request before the deadline**?

- Did request processing run too long inside the API?
- Were app threads or database connection pools blocked?
- Is the backend settings request timeout shorter than required processing time?
- Does another intermediate device impose its own timeout?
- Are packets dropping, DNS lookups stalling, or servers unresponsive?

**Adjust timeouts only after understanding why the backend is slow.** Blindly raising timeouts hides performance bugs and leaves requests hanging longer.

### 9.4. Separating Gateway-Generated Codes from Backend-Generated Codes

Suppose logs show:

~~~text
Time:                2026-11-20 10:15:00 UTC
Client path:         GET /orders
Gateway status:      502
Backend status:      (no valid response)
Backend health:      Unhealthy
Probe error:         TLS certificate hostname mismatch
~~~

This is **simulated log data**. It supports a gateway ↔ backend fault hypothesis, unlike this scenario:

~~~text
Gateway status:      503
Backend status:      503
Backend health:      Healthy
App log:             Database connection pool exhausted
~~~

The second case points to an application or dependency error. In real telemetry, exact field names and log formats depend on resource type, SKU, and diagnostic mode.

### Quick Decision Table

| Evidence | Stronger hypothesis | Next step |
| --- | --- | --- |
| Client cannot complete TLS to gateway | Frontend cert/listener/TLS policy | Check SNI, SAN, chain, DNS |
| Client establishes HTTPS, gets 502, all backends Unhealthy | Probe/settings/backend TLS/network | Read backend health reason; test backend from valid network |
| One backend Healthy, one Unhealthy | Config or runtime drift between backends | Compare certs, ports, and app logs per target |
| Probes Healthy yet one endpoint returns 504 | Live request exceeds timeout | Inspect request timing, backend/DB |
| `/` returns 404 while `/ready` returns 200 | Wrong probe path | Configure an explicit custom probe |
| Probe returns 401 | Health endpoint requires auth | Build an unauthenticated readiness endpoint with network restrictions |
| Only one hostname fails on the same frontend IP | Multi-site listener/SNI/rule | Inspect cert and host binding for that hostname |
| Failures started only after enabling backend HTTPS | Certificate trust/SNI or HTTPS port | Compare protocol, cert, and backend settings |
| Client gets 403, WAF logs record block | WAF policy | Review rule ID and false positives; do not alter probes blindly |

## 10. Azure Monitor: Measure Instead of Guessing

### 10.1. Metrics to Cross-Check

When investigating Application Gateway, track metrics supported by your SKU:

- **Healthy host count** and **Unhealthy host count**, filterable by pool/settings.
- **Failed requests**, **Total requests**, and frontend HTTP status codes.
- **Response time / latency**, throughput, connections, and gateway capacity.
- WAF/block metrics when using a WAF SKU.
- Backend VM/container/API metrics: CPU, memory, request latency, error rate, and dependency health.

For instance, if healthy host count drops from 2 to 0 the moment a new certificate rolls out, prioritize checking backend TLS, probes, or shared changes. If Healthy stays 2 while `/reports` latency climbs, check path mappings, the API, and the database first.

Exact metric names and dimensions in the portal vary by SKU; pick the **actual metrics emitted by your resource**.

### 10.2. Diagnostic Settings and Access Logs

In the Azure portal:

1. Select the Application Gateway under investigation.
2. Open **Diagnostic settings**.
3. Enable available logs such as **Access log** and **Firewall log** if using WAF.
4. Choose a destination such as a **Log Analytics workspace**, Storage Account, or Event Hubs.
5. Choose the log table mode (resource-specific or legacy `AzureDiagnostics`) per needs and current support.
6. Verify events actually arrive; enabling logs after an outage will not backfill historical records that were never captured.

Logs may contain client IPs, URL paths, hostnames, and connection details. Enforce access controls, retention policies, and ingestion/storage budgets.

### 10.3. KQL for Resource-Specific Access Logs

When Application Gateway sends access logs to the `AGWAccessLogs` table in Log Analytics:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(2h)
| summarize Requests = count()
    by bin(TimeGenerated, 5m), Status = tostring(HttpStatus)
| order by TimeGenerated asc
~~~

This query counts requests by HTTP status in five-minute buckets. Run it inside **the workspace containing `AGWAccessLogs`**; an empty table returns no rows, and a workspace without that schema throws a missing-table error.

To spot `502`/`503`/`504` spikes:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(24h)
| where tostring(HttpStatus) in ("502", "503", "504")
| summarize Errors = count()
    by bin(TimeGenerated, 15m), Status = tostring(HttpStatus)
| order by TimeGenerated asc
~~~

When tracing a specific request, include fields for request URI, backend status, routed server, and transaction ID **if they exist in your actual schema**. Do not assume every log schema version emits identical columns.

### 10.4. When Logs Use the AzureDiagnostics Format

In workspaces using the legacy `AzureDiagnostics` table:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(2h)
| where Category == "ApplicationGatewayAccessLog"
| summarize Events = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

If the table is missing, never conclude "Application Gateway had zero errors." Diagnostic settings may be disabled, pointing to another workspace, still ingesting, or writing to **resource-specific tables**.

### 10.5. What Should an Investigation Dashboard Answer?

| Panel | Question |
| --- | --- |
| Healthy/Unhealthy backend count | Did any backend lose Healthy status right when errors started? |
| HTTP status over time | When did 502/503/504 errors spike, and which URLs are affected? |
| Request latency and timeouts | Is the backend slow or is the gateway failing to connect? |
| WAF blocks | Are 403s coming from WAF or from the backend? |
| Backend metrics/logs | Are CPU, memory, app exceptions, or database errors climbing? |
| Deployment/certificate changes | Were certs, probes, listeners, DNS, or rules changed right before errors? |

Keep timestamps in **UTC** or convert time zones explicitly with labels. Never compare a 10:15 UTC chart against a 10:15 local-time log as if they were the same instant.

## 11. Three Guided Diagnostic Case Studies

### Case A — 502 Immediately After Updating Backend Certificates

**Context:** The gateway already ran an HTTPS frontend. After the backend team replaced certificates on both VMs, customers saw `502`. In Backend health, both VMs showed `Unhealthy` with a TLS hostname message.

**Simulated details:**

~~~text
Frontend URL:         https://api.contoso.example
Backend FQDN config:  api.internal.contoso.example
New certificate SAN:  api-new.internal.contoso.example
Probe:                HTTPS /ready
Backend port:         443
~~~

**Analysis:**

1. Frontend TLS still works because clients receive HTTP `502` instead of browser certificate errors.
2. The gateway connects to the backend over HTTPS and validates hostname `api.internal.contoso.example`.
3. The new SAN covers only `api-new.internal.contoso.example`.
4. Probes and backend requests fail due to the mismatch.

**Remediation:** issue/install a backend certificate whose SAN matches the active hostname **or** update backend hostname/routing per an approved design while synchronizing DNS, SNI, Host headers, and probes. Never switch to `HTTP` just to dodge TLS validation if policy mandates end-to-end encryption.

**Verification:** check hostname with `openssl`, run `curl --resolve` against each backend, confirm Backend health returns Healthy, and confirm live requests return expected codes with zero 502s.

### Case B — API Works Normally Yet Probe Returns 401

**Context:** A backend returns `HTTP 200` for requests carrying a bearer token, yet a custom probe calling `/api/status` without a token gets `401`. Gateway marks the backend Unhealthy.

**Root cause:** health probes do not carry user login sessions and should not depend on tokens meant for normal API requests.

**Remediation:** create a dedicated `/ready` endpoint returning `200` when the service is genuinely ready, or use a gateway-supported health mechanism aligned with policy. Keep sensitive info out of the response and restrict network access appropriately. Never "fix" this by accepting `401` as Healthy, since doing so masks real readiness failures.

**Verification:** test `/ready` from an authorized network path, check Backend health, and re-test authenticated API calls.

### Case C — Gateway Healthy Yet Report Endpoint Returns 504

**Context:** Probe `GET /ready` returns `200` in 50 ms and both backends are Healthy. However, `GET /reports/monthly` takes over a minute and times out through the gateway.

**Analysis:** probes evaluate ability to accept requests, not the latency of every endpoint. The report query exceeds the request timeout in backend settings or another proxy.

**Remediation:** inspect request tracing/backend logs, database queries, connection pools, actual execution times, and timeouts across every layer. Optimize the backend, move long-running work to async processing, or tune timeouts **with justification**.

**Verification:** requests complete within agreed SLOs, timeouts drop, and backends stay Healthy.

## 12. Step-by-Step Troubleshooting Workflow

Suppose you are on call and receive an alert: "Application Gateway 502 rate increasing."

### Step 1 — Capture State and Scope Impact

Record timestamp, subscription, gateway, hostname, URL/path, affected user scope, status code, and a transaction/correlation ID if available. Never edit configurations before scoping the problem.

### Step 2 — Check DNS and Frontend TLS

From an affected client, verify DNS resolves to the right frontend; test `curl -v` with the hostname and check certificate/SAN/expiry. If TLS fails to establish, prioritize listener, DNS, TLS policy, and certificate rotation checks.

### Step 3 — Identify the Active Route

Inspect listeners, rules, URL path maps, backend pools, and backend settings. Do not guess the backend pool from the API name; verify the active rule.

### Step 4 — Inspect Backend Health

Check each target's Healthy/Unhealthy/Unknown status and record detailed messages. If all are Unhealthy, compare shared factors like probes, TLS hostnames, backend settings, and networking. If only one target fails, inspect that server's configuration/app.

### Step 5 — Test Probes and Backends from an Eligible Network

Compare probe protocol, host, path, port, timeout, and accepted status codes. From an authorized test host, verify TCP, TLS certificates, and HTTP `/ready` on **each backend**. Keep in mind the test host's network path may differ from the gateway subnet.

### Step 6 — Correlate Logs and Metrics

Find when healthy host count, request errors, and backend latency shifted. Correlate Application Gateway logs against app/dependency logs and recent deployments.

### Step 7 — Fix the Root Cause

Examples:

- Wrong SAN → issue/install matching backend cert or align hostnames.
- Probe `/` returns 404 → configure custom probe to `/ready`.
- Wrong backend port → update backend settings after verifying the real listening port.
- NSG blocks traffic → update rules scoped tightly to required sources/ports.
- Overloaded backend → fix performance/capacity root causes.
- WAF false positive → inspect rule logs before tuning narrow exclusions.

Apply changes through approved workflows. Avoid disabling HTTPS validation, opening broad firewall rules, or removing probes as a "quick recovery."

### Step 8 — Verify After Change and Document Lessons

Confirm every backend returns Healthy, representative URLs return expected status codes, TLS is valid, 502/503/504 errors drop, and SLOs stabilize. Record the change, operator, timeline, and preventive actions.

## 13. Zero-Resource Diagnostic Practice

### Scenario

An application has:

- Public FQDN: `shop.contoso.example`.
- Azure Application Gateway HTTPS listener: port 443, certificate SAN covers `shop.contoso.example`.
- Backend pool: `10.30.2.10` and `10.30.2.11`.
- Backend settings: HTTPS port 443; host `shop-api.internal.contoso.example`.
- Custom probe: HTTPS `/ready`, host `shop-api.internal.contoso.example`.
- Backend certificate SAN: `shop-api.internal.contoso.example`.
- Request timeout: 30 seconds (hypothetical).

During a new deployment, you observe the following timeline:

| UTC time | Backend .10 | Backend .11 | Client status | Notes |
| --- | --- | --- | --- | --- |
| 08:00 | Healthy | Healthy | 200 | Normal |
| 08:07 | Unhealthy | Healthy | Occasional 200 | .10 deployed new release |
| 08:10 | Unhealthy | Unhealthy | 502 rising | .11 also deployed |
| 08:12 | Unhealthy | Unhealthy | 502 | Probe `GET /ready` returns 401 on both |

**Question 1.** Is the frontend certificate the prime suspect?

*Answer:* No. Clients receive HTTP 502 and the listener already has a valid certificate. Evidence shows backend probes transitioned from Healthy to Unhealthy right after deployment.

**Question 2.** What does probe `/ready` returning 401 tell you?

*Answer:* The backend likely started requiring authentication on the health endpoint or middleware is blocking it. Verify on the backend. With a 200–399 matcher, 401 fails the probe.

**Question 3.** Should you change accepted status codes to `200–499` to make backends Healthy quickly?

*Answer:* No. Doing so treats 401/403/404 as healthy, masks the real bug, and risks routing traffic to broken backends.

**Question 4.** After fixing middleware so `/ready` returns 200 when truly ready, what should you verify?

*Answer:* Test the endpoint from an authorized network, confirm TLS remains valid, both backends return Healthy, authenticated app requests still work, 502 rates drop, and no sensitive data leaks from the health endpoint.

### KQL Practice (When Log Analytics Is Available)

If the workspace collects `AGWAccessLogs`, run:

~~~kusto
AGWAccessLogs
| where TimeGenerated >= ago(1h)
| summarize Requests = count() by HttpStatus = tostring(HttpStatus)
| order by Requests desc
~~~

Note the most frequent status code. Then compare against **Backend health** for the same timeframe; if no access log data appears, state why you must inspect diagnostic settings rather than concluding the gateway had no errors.

### TLS Misconfiguration Identification Exercise

Given three cases:

| Case | Listener certificate | Backend hostname | Backend certificate SAN | Evaluation |
| --- | --- | --- | --- | --- |
| A | `shop.contoso.example` | `shop-api.internal.contoso.example` | `shop-api.internal.contoso.example` | Names match; continue checking trust chain/port/path |
| B | `shop.contoso.example` | `shop-api.internal.contoso.example` | `new-shop-api.internal.contoso.example` | Backend mismatch; likely probe/TLS failure |
| C | `other.contoso.example` | `shop-api.internal.contoso.example` | `shop-api.internal.contoso.example` | Frontend mismatch for `shop.contoso.example` |

**Task:** identify which TLS connection has a problem in each case, and name one verification command for each.

## 14. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| "502 definitely means TLS is broken." | 502 can also come from unresponsive backends, networking, resets, or health/routing. |
| "A Healthy probe means the entire API works." | Probes check only configured criteria on a specific endpoint/path. |
| "My browser trusts the cert, so the gateway trusts the backend cert." | Frontend trust and backend trust use separate contexts. |
| "Swapping the listener cert fixes backend cert errors." | Application Gateway termination + HTTPS backend involves two distinct TLS connections. |
| "Probe 401 can be accepted as Healthy as a quick fix." | Build a proper health endpoint reflecting true readiness. |
| "TCP 443 is open, so TLS and HTTP must work." | TCP reachability does not verify certificates, SNI, or HTTP responses. |
| "Clients getting 503 means the gateway failed." | Backends can return 503 and the gateway forwards it; check logs. |
| "Raising timeouts fixes every 504." | Investigate request latency, performance, and dependencies. |
| "Front Door probes work identically to Application Gateway probes." | Each product has its own settings, behavior, metrics, and logs. |
| "No logs means zero errors." | Diagnostic settings may be off or logs may go to another workspace. |

## 15. Self-Check Questions

**Question 1.** The gateway has a valid HTTPS listener cert for `api.example.com`, yet the backend cert SAN contains only `internal-v2.example.com` while backend settings use host `internal-v1.example.com`. Which TLS connection fails?

**Answer:** TLS between gateway and backend will likely fail hostname verification. Frontend TLS can still work normally.

**Question 2.** A backend returns 200 on `/ready`, yet `/reports` frequently times out. Why does Backend health stay Healthy?

**Answer:** Health probes check only the readiness endpoint, not every processing path. Monitor real request latency and backend request timeouts.

**Question 3.** Why is `curl --resolve` usually better than calling `https://10.20.2.4` directly when diagnosing an HTTPS virtual host?

**Answer:** It keeps the proper URL hostname for TLS SNI and HTTP Host while forcing the connection to the target IP.

**Question 4.** Backend health is Unhealthy and the reason says the probe returned 404. Give two possible causes.

**Answer:** Wrong path (e.g., default `/` does not exist), or the Host header routes the request to a default/wrong virtual host lacking that endpoint.

**Question 5.** Both backends turn Unhealthy immediately after editing HTTPS settings. What do you check first?

**Answer:** Shared protocol/port, hostname/SNI, certificate/CA, custom probe, and shared network path, then inspect individual backends.

**Question 6.** If clients receive 403, does that mean probes are marking backends Unhealthy?

**Answer:** Not enough evidence. 403 can come from WAF, gateway rules, authentication, or the backend. Inspect WAF/access logs and Backend health separately.

**Question 7.** Should you run `curl -k` routinely in production monitoring because the API "still returns 200"?

**Answer:** No. `-k` skips client-side certificate verification and masks TLS faults. Use it only temporarily in controlled diagnostics, never as a fix.

## Key Takeaways

- Always identify whether a **request stopped at DNS, frontend TLS, routing, backend health, backend TLS, or the application** before changing configuration.
- Application Gateway can have **two independent TLS connections**: client → gateway and gateway → backend.
- **TLS SNI, HTTP Host, certificate SANs, and backend hostnames** must align with your architecture and routing.
- **Health probes** must check the right protocol, port, host, path, and status codes; `/ready` usually fits far better than a login-protected URL.
- **502/503/504** are signals to investigate by product and logs; a single status code alone does not identify the root cause.
- Combine **Backend health + Azure Monitor + controlled diagnostic commands** to isolate root causes, track improvements, and confirm genuine recovery.
