# Secure Web Proxy and Outbound Web Access Control

A Java application running on Compute Engine needs to download libraries from the Internet; a CI/CD pipeline must connect to a source repository; a data analytics team calls a partner API. If every workload can send HTTP/HTTPS requests to any arbitrary website, the organization struggles to detect malware phoning home, curb data exfiltration, and determine which service is calling unauthorized endpoints.

**Secure Web Proxy (SWP)** is a Google Cloud-managed web proxy service that centralizes control over **outbound (egress) HTTP/HTTPS traffic**. Rather than relying solely on IP-based firewalls, administrators can enforce policies over traffic sources, destinations, and request attributes within the capabilities of the chosen deployment mode. SWP accepts requests, evaluates policies, opens a new outbound connection to the destination when permitted, and writes logs for investigation.

This lesson belongs to the **Network Security and Access** chapter of the **CLOUD_PROVIDERS_GCP** module. It connects with project design, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, databases, release automation, and reliability/cost monitoring. The goal is knowing when to pick SWP, how to configure it, and how to ensure workloads cannot take alternate network paths to bypass the proxy.

After this lesson, you will be able to:

- Explain outbound traffic flow and where Secure Web Proxy sits.
- Distinguish **explicit proxy**, **next-hop routing**, and **Private Service Connect**.
- Design gateway security policies with source identities, destination criteria, and **default deny**.
- Understand HTTPS visibility limits and the purpose of **TLS inspection**.
- Create sample policies, rules, and gateways via Google Cloud Console or `gcloud`.
- Test the proxy with `curl`, read Cloud Logging, and prevent bypasses.
- Estimate costs, manage changes, and troubleshoot common errors.

## 1. Where Does Secure Web Proxy Sit in the Network Flow?

In the **explicit proxy** model, applications are configured to route requests through the proxy address. The proxy receives connections, evaluates policies, and initiates a new connection to the external website or API if the request is allowed.

~~~mermaid
flowchart LR
    A["Compute Engine / workload in VPC"] --> B["Regional Secure Web Proxy"]
    B --> C{"Security policy"}
    C -- "ALLOW" --> D["Internet egress via managed network"]
    D --> E["External website / API"]
    C -- "DENY" --> F["Denied + transaction log"]
    B --> G["Cloud Logging / Monitoring"]
~~~

For example, an application sends a request to `https://api.vendor.example`. Only if the policy permits the source and destination within observable attributes does the proxy forward it. If blocked, the request never reaches the destination API. SWP enforces policies on **traffic that actually traverses the proxy**.

| Component | Responsibility | Limitation |
|---|---|---|
| **VPC, routes, firewalls** | Control paths and connections at the network layer | Does not parse HTTP URL paths on its own |
| **Cloud NAT** | Provides Internet egress for private IPs via NAT | Not a domain/HTTP filter per workload identity |
| **Secure Web Proxy** | Inspects HTTP/HTTPS egress per policy | Does not govern arbitrary protocols or unblocked bypass paths |
| **Cloud DNS** | Resolves domain names | Does not block HTTP requests to a domain by itself |
| **Cloud Armor** | Primarily protects **inbound** app traffic via supported load balancers | Does not replace SWP for egress |
| **IAM and service accounts** | Defines identity and Google Cloud API permissions | Does not restrict arbitrary websites on the Internet |
| **VPC Service Controls** | Restricts access/data movement for supported Google Cloud services | Does not replace an external web filtering proxy |

Cloud Armor typically blocks client traffic **entering** an API, whereas SWP governs requests **leaving** the API toward the Internet. Both layers can be used together.

## 2. When Do You Need SWP?

| Requirement | How SWP helps | Complementary components |
|---|---|---|
| Backend may only call approved partner APIs | Destination and source allowlists | Service accounts, DNS, and networking |
| Record domains/websites accessed by VMs | Transaction logs | Logging and log-viewer permissions |
| Block connections to unapproved domains | Default deny plus explicit rules | Firewalls/routes blocking direct egress |
| Differentiate workload groups | Match by service account or secure tag where supported | IAM and tag governance |
| Inspect paths/headers inside HTTPS | TLS inspection | Certificate Authority Service and trust store |
| Reuse a central proxy across multiple VPCs | Private Service Connect or supported modes | Host project / PSC design |
| Cap outbound request rate to the Internet | Service rate-limiting policies where supported | Quotas and in-app rate controls |

SWP focuses on **HTTP/HTTPS web egress**. It is not a VPN/Interconnect, does not replace a public load balancer for external customers, and does not proxy arbitrary TCP/UDP protocols.

## 3. Three Modes to Route Traffic to the Proxy

### 3.1. Explicit Proxy

The application or OS configures the proxy address: e.g., `--proxy` in `curl`, `HTTP_PROXY`/`HTTPS_PROXY` environment variables, or JVM proxy settings.

~~~text
Application → SWP IP:port in VPC → Policy → Internet
~~~

This model is easy to test per client, yet a program that ignores proxy settings can bypass it if the network still permits direct connections.

### 3.2. Next-Hop Mode

With **next-hop**, routes steer traffic from workloads toward the gateway per supported capabilities, reducing the need to reconfigure each app. Design carefully around route types, destinations, and internal traffic so you don't break intra-VPC connectivity. An explicit gateway does not become next-hop merely by changing proxy addresses in applications.

### 3.3. Private Service Connect (PSC)

SWP can be published via **Private Service Connect** so other VPCs connect to a central proxy. PSC provides private connectivity between authorized networks, but does not open all websites automatically; SWP policies still decide whether requests are forwarded.

| Mode | Request sender | Best suited for | What to verify |
|---|---|---|---|
| Explicit | App configures proxy address | VMs and workloads whose settings can be edited | Proxy settings, firewalls, no-proxy |
| Next-hop | Routes direct traffic to gateway | Many sources hard to configure individually | Route priority, internal paths, limits |
| PSC | Consumer VPC uses a private endpoint | Multi-VPC, centralized networking | Endpoint/service attachment, DNS, IAM |

SWP is **regional**. Choose regions based on workload location, networking needs, latency, and availability. Current documentation also specifies that gateways in a **Shared VPC** must be deployed in the **host project**, not a service project; coordinate with the network administration team.

## 4. Resource Architecture: Gateway, Policy, and Network

~~~text
Project: platform-egress
├── VPC: prod-network
│   ├── PRIVATE subnet: egress-subnet (region A)
│   └── Proxy-only subnet: REGIONAL_MANAGED_PROXY (region A)
├── Gateway security policy: outbound-policy
│   ├── Rule 10: allow approved sources and destinations
│   ├── Rule 20: allow required dependency repositories
│   └── Default: DENY
├── Secure Web Proxy gateway: outbound-proxy
│   ├── Internal IP and frontend ports
│   └── Attached outbound-policy
└── Managed Cloud NAT / Cloud Logging
~~~

| Resource | Role | Common misconfigurations |
|---|---|---|
| **Gateway** | Receives requests at IP/port and enforces policy | Clients use the wrong IP or gateway is not yet ready |
| **Gateway security policy** | Holds standard web egress rules | Not attached to gateway, or overridden by an authorization policy |
| **Rule** | Priority, `basicProfile`, `sessionMatcher`, optional `applicationMatcher` | Matching HTTPS as if it were plain HTTP |
| **PRIVATE subnet** | Subnet referenced when creating the gateway | Accidentally selecting the proxy-only subnet |
| **Proxy-only subnet** | `REGIONAL_MANAGED_PROXY` supplying IPs for Envoy proxy pool | Missing or overlapping CIDR |
| **Cloud NAT** | Provides public IP identity for outbound proxy traffic | Confusing VM IPs with public egress IPs |
| **Certificate Manager** | Supplies frontend certificates when clients talk TLS to the proxy | Confusing with the CA used to decrypt HTTPS to target websites |
| **Certificate Authority Service** | Issues CA certs for TLS inspection | Clients don't trust the CA or apps enforce certificate pinning |

When deploying SWP, you need **both a regular PRIVATE subnet and a proxy-only subnet** in the target region. The proxy-only subnet must not be passed as `gateway.subnetwork`. SWP can automatically provision **Cloud NAT** with dynamic egress IPs; if a partner requires allowlisting fixed public IPs, follow the corresponding advanced Cloud NAT setup guide.

## 5. Policy: Default Deny and Rule Priority

For a **gateway security policy** handling standard web traffic:

- `priority`: lower numbers evaluate first.
- `enabled`: toggles rule enforcement.
- `basicProfile`: `ALLOW` or `DENY`.
- `sessionMatcher`: session, source, and destination criteria supported by the mode.
- `applicationMatcher`: detailed HTTP criteria when traffic type and TLS inspection permit.
- `tlsInspectionEnabled`: enables HTTPS decryption for the rule once CA/policy configuration is in place.

**Default deny** is the safest starting point: requests not matching an explicit allow rule cannot reach external websites.

| Priority | Workload | Approved destination | Decision |
|---:|---|---|---|
| 10 | Build pipeline | Listed registries, source repos, and dependencies | Allow |
| 20 | Payment service | Payment partner API | Allow |
| 30 | Reporting app | Contractual data ingestion endpoint | Allow |
| Default | All other sources/destinations | Unapproved | Deny |

This is a **logical requirement matrix**, not directly runnable rules. Map identities, domains, traffic types, and mode-specific match capabilities accordingly.

### Gateway Security Policy, Authorization Policy, and Rate Limiting

SWP also supports **authorization policies** for identity verification, frontend mutual TLS, or authorization extensions. For standard web traffic, **authorization policies and gateway security policies are mutually exclusive primary models on the same gateway**: attaching an authorization policy causes existing gateway security rules to be ignored. Service rate-limiting policies can also be added where supported.

For **AI agent / Agent Gateway** traffic, Google Cloud provides dedicated authorization and extension mechanisms; this lesson focuses on standard web traffic.

## 6. HTTPS and Visibility Limitations

HTTPS requests encrypt HTTP contents, including URL paths and headers. The proxy cannot read them from IP/port alone; matching capabilities also depend on explicit vs. next-hop mode.

| Traffic | What can the proxy inspect? | Notes |
|---|---|---|
| Unencrypted HTTP | Host and HTTP attributes per mode | Host rules work directly for illustration |
| HTTPS without TLS inspection | Session/source info and visible TLS attributes per mode | Cannot read URL paths or HTTP headers |
| HTTPS with TLS inspection | Decrypted HTTP contents within supported scope | Uses `sessionMatcher` and `applicationMatcher` plus CA/trust |

**Key limitation of explicit proxy:** per current SWP docs, for **HTTPS without TLS inspection**, hostname matching at session/application level is constrained. Do not take a `host() == 'partner.example'` rule tested on HTTP and assume it filters HTTPS identically in explicit mode. In **next-hop** mode, SWP can evaluate TLS SNI per supported capabilities, though SNI never contains the URL path.

### How Does TLS Inspection Work?

~~~text
Client -- TLS session 1 --> Secure Web Proxy
              Decrypt, evaluate policy on HTTP
Proxy  -- TLS session 2 --> Target Server/API
~~~

The proxy acts as a trusted intermediary using **Certificate Authority Service** to mint short-lived certificates for accessed domains. Clients must trust that CA chain. To use `applicationMatcher` on HTTPS, create a `tlsInspectionPolicy`, CA pool, service agent permissions, attach the policy, and set `tlsInspectionEnabled` on the applicable rules.

Constraints to weigh:

1. Clients that do not trust the root CA will fail the HTTPS handshake.
2. Applications using **certificate pinning** or mutual TLS may break; define reviewed exceptions.
3. Sensitive data inside requests must be inspected/logged strictly under privacy policies.
4. Avoid decrypting every arbitrary Internet site when you only need to inspect a few target APIs.
5. **Frontend certificates** for client-to-proxy HTTPS differ from the **TLS inspection CA** used toward target websites.

## 7. Preparing VPC, APIs, and Permissions

Before creating an **explicit proxy** for practice, ensure you have a billing-enabled test project, a Linux VM or workload able to reach the proxy, suitable VPC and subnets, permissions to configure networking/security policies, and a test website for verification.

Essential APIs typically include **Compute Engine, Network Services, Network Security**; plus **Certificate Manager** for frontend certificates and **CA Service** for TLS inspection if used. Roles such as `roles/compute.networkAdmin` may be needed for administration; add scoped certificate/CA roles as required.

### Creating Two Subnets in a Test VPC

~~~bash
PROJECT_ID="my-egress-project"
REGION="us-central1"
VPC="egress-lab-vpc"
FRONTEND_SUBNET="swp-frontend"
PROXY_SUBNET="swp-proxy-only"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  networkservices.googleapis.com \
  networksecurity.googleapis.com \
  certificatemanager.googleapis.com

gcloud compute networks create "$VPC" --subnet-mode=custom

# Regular subnet: the gateway references this subnet directly.
gcloud compute networks subnets create "$FRONTEND_SUBNET" \
  --network="$VPC" --region="$REGION" \
  --range="10.60.0.0/24" --purpose=PRIVATE

# Proxy-only subnet: used by the Envoy proxy pool.
gcloud compute networks subnets create "$PROXY_SUBNET" \
  --network="$VPC" --region="$REGION" \
  --range="10.61.0.0/23" \
  --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE
~~~

These commands are **illustrative only**; never run them verbatim in production. Pick non-overlapping CIDRs, restrict permissions, and note that resources can incur charges. With Shared VPC, use the host project/VPC provided by the platform team rather than creating shadow networks to bypass rules.

## 8. Creating a Policy, Rule, and Gateway with gcloud

These examples use YAML files as **learning templates**. Substitute real `PROJECT_ID`, `REGION`, and IP values. Here we configure only an **unencrypted HTTP** rule; this example does not represent a production HTTPS filter.

### Step 1. Create the Gateway Security Policy

~~~yaml
# policy.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy
description: Test egress policy
~~~

~~~bash
gcloud network-security gateway-security-policies import outbound-policy \
  --source=policy.yaml \
  --location="$REGION"
~~~

### Step 2. Add an HTTP Rule

~~~yaml
# allow-http.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy/rules/allow-http-wikipedia
description: Allow plain HTTP to the test website
enabled: true
priority: 10
basicProfile: ALLOW
sessionMatcher: host() == 'www.wikipedia.org'
~~~

~~~bash
gcloud network-security gateway-security-policies rules import allow-http-wikipedia \
  --source=allow-http.yaml \
  --location="$REGION" \
  --gateway-security-policy=outbound-policy
~~~

**Do not assume HTTPS is also opened:** filtering HTTPS by hostname/path in explicit mode requires checking TLS inspection and supported attributes. Never add `ALLOW all` merely to work around a blocked website error in production.

### Step 3. Create the Gateway

~~~yaml
# gateway.yaml
name: projects/PROJECT_ID/locations/REGION/gateways/outbound-proxy
type: SECURE_WEB_GATEWAY
addresses: ["10.60.0.10"]
ports: [443]
gatewaySecurityPolicy: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy
network: projects/PROJECT_ID/global/networks/egress-lab-vpc
subnetwork: projects/PROJECT_ID/regions/REGION/subnetworks/swp-frontend
routingMode: EXPLICIT_ROUTING_MODE
~~~

~~~bash
gcloud network-services gateways import outbound-proxy \
  --source=gateway.yaml \
  --location="$REGION"
~~~

`10.60.0.10` is an illustrative subnet IP; in real deployments pick a free IP or let the service allocate one. SWP currently supports up to **five frontend ports**, and this list cannot be edited after gateway creation. If clients sit in another region, you can set `allowGlobalAccess` **at gateway creation time** where supported.

### Step 4. Read Back Policy and Gateway

~~~bash
gcloud network-security gateway-security-policies describe outbound-policy \
  --location="$REGION"

gcloud network-security gateway-security-policies rules list \
  --gateway-security-policy=outbound-policy \
  --location="$REGION"

gcloud network-services gateways describe outbound-proxy \
  --location="$REGION"
~~~

Exact flags may vary by Cloud CLI version; check `gcloud network-security ... --help` and `gcloud network-services ... --help`. Creating gateways/policies can incur charges.

### Step 5. Test from a Linux VM

~~~bash
PROXY_IP="10.60.0.10"

# Host permitted by the HTTP rule.
curl -v --proxy "http://$PROXY_IP:443" \
  "http://www.wikipedia.org/"

# Host absent from allowlist, expected to be denied.
curl -v --proxy "http://$PROXY_IP:443" \
  "http://example.org/"
~~~

A `200` response or `301/302` redirect from the allowed site shows the request traversed the proxy to the destination; exact status codes depend on the live site. If `curl` prints status `000`, it is usually a connectivity/TLS/DNS failure rather than proof of a DENY rule.

**Two different TLS relationships:** this example uses `http://` for the client-to-proxy connection. If clients connect via `https://` to the proxy, a frontend certificate is required. This differs from SWP **decrypting HTTPS between the client and target website** via TLS inspection.

## 9. Configuring Java Workloads to Use an Explicit Proxy

In Java, proxy handling depends on the HTTP library used. Some standard Java networking APIs honor these system properties:

~~~bash
java \
  -Dhttp.proxyHost=10.60.0.10 \
  -Dhttp.proxyPort=443 \
  -Dhttps.proxyHost=10.60.0.10 \
  -Dhttps.proxyPort=443 \
  -jar app.jar
~~~

This is a **client configuration sample**; not all Java libraries honor these properties. Apache HttpClient, OkHttp, gRPC, or specialized SDKs may require library-specific proxy settings. For HTTPS, rules and trust must be designed as in Sections 6 and 8; with only the illustrative HTTP rule, HTTPS requests may be denied.

In environments supporting proxy environment variables:

~~~bash
export HTTP_PROXY="http://10.60.0.10:443"
export HTTPS_PROXY="http://10.60.0.10:443"

# Bypass proxy only for approved internal destinations.
export NO_PROXY="localhost,127.0.0.1,metadata.google.internal"
~~~

`NO_PROXY` is a **client-side** exception list. Overly broad settings like `*` or external domains allow clients to skip the proxy whenever direct network paths exist. Different runtimes parse `NO_PROXY` differently; test with the exact application and HTTP library in use.

On GKE, setting proxy env vars on a Pod only affects components that read them. Image pulls, kubelet, or control-plane flows may take separate paths and must be verified independently. On Cloud Run, use VPC connectivity such as **Direct VPC egress** where appropriate so the app can reach the proxy, alongside configuring the HTTP client; VPC connectivity **does not automatically force** all HTTP requests through SWP.

## 10. Preventing Bypass: Proxy Settings Must Pair with Network Controls

**Setting proxy variables in an app alone does not create a hard security boundary.** If workloads have external IPs, Cloud NAT, or direct Internet routes, any program ignoring proxy settings can still send requests directly out.

Necessary controls:

1. **Restrict direct egress** via VPC design, firewalls, and routes, keeping paths open only to the gateway and approved internal services.
2. **Audit exceptions:** DNS, metadata server, token services, Google APIs, or platform services may need dedicated paths; avoid blind blocks that break workload startup.
3. **Test both paths:** send proxied requests to verify allow/deny behavior, and attempt direct non-proxied connections to confirm unauthorized bypasses fail.
4. **Separate identity and governance:** workloads must not freely edit service accounts, secure tags, or security rules to acquire broader egress access.
5. **Verify multi-VPC/PSC:** every real source must route to the intended production proxy and policy, not accidentally into a test gateway.
6. **Avoid breaking releases:** test Git, registries, package managers, Cloud DNS, and operational tools before flipping to default deny.

Even when the proxy permits connecting to a partner domain, the target API still requires authentication and authorization. **Permitting egress does not mean permitting reading or modifying external data.**

## 11. Enabling TLS Inspection When Granular HTTPS Filtering Is Required

Suppose a system may only access `https://partner.example/reports` while blocking `https://partner.example/upload`. Both paths sit inside TLS-encrypted HTTP payloads; domain/session-level filtering cannot tell them apart. **TLS inspection** is needed so `applicationMatcher` can operate within supported scope.

General workflow:

~~~text
Identify sources and domains authorized for decryption
  → Provision CA pool and CA in Certificate Authority Service
  → Grant service agent permission to use CA pool
  → Create regional tlsInspectionPolicy
  → Link to gateway security policy
  → Create sessionMatcher + applicationMatcher
  → Set tlsInspectionEnabled: true on rules requiring decryption
  → Distribute CA trust to clients
  → Test TLS, certificate pinning, and exceptions
~~~

Illustrative **rule syntax example**—cannot be imported standalone without first preparing the CA and inspection policy:

~~~yaml
# inspection-rule.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy/rules/allow-partner-reports
description: Allow a reviewed HTTPS path only
enabled: true
priority: 20
basicProfile: ALLOW
sessionMatcher: host() == 'partner.example'
applicationMatcher: request.path.startsWith('/reports')
tlsInspectionEnabled: true
~~~

Note that `host()` and session conditions must be compatible with **explicit/next-hop mode** and request traits. Never apply this example blindly to all HTTPS traffic without checking host-matching behavior in current documentation. For clients using certificate pinning, mutual TLS, or specially regulated data, establish reviewed exceptions before enforcing.

TLS inspection adds CA Service cost, handshake latency, and trust-chain management. CA administration requires least privilege, key management, rotation, and revocation procedures. Never log decrypted HTTPS payloads without explicit justification and data-handling authorization.

## 12. Operating Alongside Compute Engine, GKE, Cloud Run, and CI/CD

| Environment | How it connects to proxy | What to test |
|---|---|---|
| **Compute Engine** | App proxy settings or supported next-hop routes | Firewalls, subnets, source identity, proxied/unproxied requests |
| **GKE** | Pod proxy settings or architectural network routing | Container runtime, DNS, image pulls, control-plane traffic |
| **Cloud Run** | VPC path to gateway + HTTP client config in service | Direct VPC egress/connector, egress mode, IAM, connectivity |
| **Build/CI/CD** | Workload network and appropriate proxy settings | Source repos, Maven/Gradle, artifact registries, token APIs |

**Compute Engine:** start with a lab VM to test easily using `curl`. In production, use per-app service accounts rather than sharing one high-privilege egress identity across all VMs.

**GKE:** controlling HTTP from Pods does not guarantee cluster control-plane traffic takes the same route. With tight policies, test rollouts, image pulls, DNS resolution, and Google API calls when new nodes spin up.

**Cloud Run:** having a VPC connector or Direct VPC egress does not automatically send HTTP requests through the proxy. Verify your HTTP library; `all-traffic` vs. `private-ranges-only` egress modes affect routing depending on architecture.

**CI/CD:** source control, package managers, and backing CDN domains rarely live under a single hostname. Observe real traffic in a lab to build an accurate allowlist rather than opening wide Internet wildcards in production.

## 13. Administrative Permissions and Change Control

Creating gateways, editing security policies, and managing certificates/CAs are sensitive operations. Never grant all those privileges to developers merely so their apps can call external APIs.

| Organizational role | Responsibility | Appropriate permissions |
|---|---|---|
| **Platform/network admin** | VPC, subnets, gateways, PSC, next-hop | Network administration in project/host project |
| **Security team** | Approve allowlists, TLS inspection, source identities | Controlled policy-edit permissions with audit trails |
| **Application owner** | Request domains, paths, and ports needed | Read access, submitting requests/pull requests |
| **CI/CD service account** | Apply IaC after review | Scoped strictly to modifying approved SWP resources |
| **SRE/auditor** | Inspect metrics, logs, and investigate incidents | Appropriate Cloud Logging/Monitoring viewer roles |

Per Google Cloud docs, `roles/compute.networkAdmin` is used across many SWP setup steps; `roles/certificatemanager.editor` or equivalent may be needed for frontend certificates. TLS inspection also requires dedicated permissions for CA Service and the Network Security service agent. Inspect **effective permissions**—including Folder/Organization inheritance—rather than granting `Owner` to clear errors.

A production change lifecycle:

~~~text
Application team requests new domain/URL
  → Security reviews justification, data sensitivity, and scope
  → Edit policy in source code / PR
  → Review match expression + priority + plan
  → Test with both allowed and denied requests
  → Apply to production via CI/CD identity
  → Monitor transaction logs and business metrics
  → Revoke expired exceptions
~~~

If a new rule breaks application connectivity, rollback should revert the policy to the last tested version while investigating root cause via logs. Never delete the entire SWP just to fix one bad rule. With TLS inspection, rollback must also account for certificate/trust distribution and app exceptions.

## 14. Cloud Logging, Monitoring, and Policy Verification

SWP emits **proxy transaction logs** and Cloud Audit Logs. Audit Logs show who modified gateways/policies; transaction logs record requests traversing the proxy, sources, destinations, policy outcomes, and latency.

In **Logs Explorer**, query proxy transactions:

~~~text
logName="projects/PROJECT_ID/logs/networkservices.googleapis.com%2Fgateway_requests"
resource.type="networkservices.googleapis.com/Gateway"
~~~

Find denied requests per documented log format:

~~~text
logName="projects/PROJECT_ID/logs/networkservices.googleapis.com%2Fgateway_requests"
jsonPayload.policy_evaluation_results.policy_action="DENY"
~~~

Exact field names can vary by gateway type, policy, and log schema. If no entries appear, check the project owning the gateway, Cloud Logging permissions, query time range, and sample log entries. For some older policy formats, results may appear under `enforcedGatewaySecurityPolicy`.

| Signal | What to investigate |
|---|---|
| Surge in denied requests | Recent policy edit, new workload, or anomalous activity |
| Requests to unfamiliar domains | New dependency, misconfiguration, or potential compromise |
| HTTP 403 from proxy | Policy deny; inspect match/action |
| Connection failures or `curl` code `000` | Routing, firewall, TLS, DNS, or gateway readiness |
| Rising latency | Proxy capacity, TLS inspection, target Internet host, or network |
| Rising request/response bytes | Large downloads, unusual exfiltration, cost risk |
| Low proxy logs despite high Internet egress | Possible bypass path or traffic skipping the gateway |

Cloud Monitoring provides metrics for `networkservices.googleapis.com/Gateway`, including request counts, bytes, and performance telemetry per configuration. Build dashboards and alerts on deny rates, latency, errors, and throughput. Because logs may contain hostnames, paths, identities, and source metadata, restrict viewer permissions and retention periods.

**SWP only logs requests it processes.** If an application skips the proxy over a direct Internet route, bypassed requests will never appear in SWP transaction logs.

## 15. Cost, Reliability, and Limitations

SWP charges typically include **gateway-hours** and **data volume processed**. Additional charges may apply for Cloud NAT, networking, Certificate Manager, CA Service, Cloud Logging, and tracing depending on design. Always check official pricing at estimation time rather than relying on numbers from old articles.

~~~text
Estimated cost
  ≈ active gateway hours × unit rate
  + GiB processed by proxy × data rate
  + network / NAT / CA / certificate / logging / trace fees if applicable
~~~

| Decision | Impact |
|---|---|
| Fewer centralized gateways | Easier management, but may increase latency and blast radius |
| Dedicated gateway per region | Optimizes latency, but increases gateway-hours and ops overhead |
| Enabling TLS inspection | Adds CA, TLS processing, and trust requirements |
| Long transaction log retention | Aids auditing, but raises storage, cost, and privacy obligations |
| Static egress IPs | Helps partners allowlist, requires IP/NAT management |

**Current limitations** to verify:

- SWP supports **IPv4**, not IPv6.
- Supports HTTP/0.9, 1.0, 1.1, and 2.0; **HTTP/3 is unsupported** per overview docs.
- Explicit proxy only governs traffic from clients actually configured to use it.
- Feature availability varies by mode, region, and release stage.
- TLS inspection carries trust, certificate compatibility, and data-policy requirements.
- In Shared VPC, gateways reside in the **host project** per current docs.

Cloud Billing budgets/alerts track spend; **budget alerts do not shut down gateways or stop traffic**. For critical systems, plan how routes/policies handle gateway unavailability without automatically opening non-compliant direct egress.

## 16. Common Issues

| Symptom | Likely cause | First thing to check |
|---|---|---|
| Cannot connect to proxy IP:port | Wrong subnet, route, firewall, region, or gateway not ready | Gateway describe, VPC routes, firewalls |
| HTTP to allowed website gets DENY | Wrong `sessionMatcher`, unattached policy, disabled rule | Rules list and transaction logs |
| HTTP works, HTTPS gets DENY | Explicit HTTPS host rule without TLS inspection behaves differently from HTTP | Mode, inspection policy, session attributes |
| `curl` throws certificate error | Frontend TLS or inspection CA not trusted by client | `curl -v` and trust store |
| Still able to reach blocked domains | Workload skipped proxy over a direct Internet route | Test without proxy, check Cloud NAT/firewalls |
| CI/CD fails to fetch dependencies | Allowlist missing required registries or backing domains | Request logs from that exact build workload |
| Partner rejects public IP | NAT egress IP missing from partner allowlist | Managed Cloud NAT / static IP |
| Latency rises during inspection | TLS handshakes, CA, app behavior, or target Internet host | Metrics/logs and CA Service |
| No proxy request logs appear | Wrong project or requests not traversing proxy | Logs Explorer and network path |
| Charges continue after stopping workloads | Gateway still exists and bills hourly | Billing by SKU and active gateways |

**Example:** a backend has `host() == 'partner.example'` in explicit mode; HTTP testing passes, yet HTTPS is blocked. Do not fix it with `ALLOW all`. Verify HTTPS matching rules for the active mode, determine whether TLS inspection or another mode is required, test from the application's actual HTTP client, and then update the policy.

## 17. Deployment Scenario Across Three Workload Groups

An e-commerce enterprise runs:

- **Payments on GKE** calling external payment APIs.
- **Catalog on Compute Engine** pulling supplier feeds.
- **CI/CD pipelines** downloading Java dependencies and container images from registries.

~~~text
                 VPC: ecommerce-prod
       Payments (GKE)     Catalog (VM)     CI/CD
                  \           |           /
                   \          |          /
                  Proxy settings / routing
                             ↓
                 Secure Web Proxy (region)
                             ↓
                       Egress policy
                /                             \
         Approved vendor APIs           Approved registries
                             ↓
                       Managed Cloud NAT
                             ↓
                           Internet
~~~

The platform team manages gateways, networking, and NAT; Security audits allowlists, TLS inspection needs, and logs; application owners submit requests for new APIs. CI/CD applies reviewed policies. SREs monitor deny rates, latency, processed data, and per-gateway costs.

If Payments needs HTTPS path filtering, the team checks provider mTLS/certificate-pinning requirements before enabling TLS inspection. If a partner allowlists only a few egress IPs, static NAT IPs are configured per SWP docs. If pipelines hit multiple CDN hosts for package managers, real domains are observed in a lab to build an accurate allowlist instead of opening wildcards to the entire Internet.

## 18. Pre-Production Checklist for SWP

- [ ] Distinguished HTTP/HTTPS egress control from ingress load balancing.
- [ ] Selected explicit, next-hop, or PSC based on workload sources and network design.
- [ ] Created non-overlapping PRIVATE subnet and proxy-only subnet in a supported region.
- [ ] Prepared project/Shared VPC host project, IAM permissions, and Billing account.
- [ ] Attached policy to gateway accurately with clear source/destination/priority rules and default deny.
- [ ] Understood HTTPS host-matching limits for the chosen deployment mode.
- [ ] If using TLS inspection: configured CA pool, inspection policy, trust distribution, and exceptions.
- [ ] Configured firewalls/routes to prevent clients from bypassing the proxy directly to the Internet.
- [ ] Tested both allow and deny cases from the actual workloads and runtimes.
- [ ] Verified DNS, Google APIs, registries, IAM, and CI/CD continue functioning.
- [ ] Enabled logs, metrics, and alerts for denies, latency, bytes, and cost.
- [ ] Verified public egress IPs match partner allowlists.
- [ ] Established code review, rollback, and IaC-managed policy workflows.
- [ ] Estimated costs for gateways, data processing, NAT, CA, and logs.

**Applied exercise:** A team runs Java APIs on Compute Engine, payments on GKE, and CI/CD pipelines. Company policy allows access only to approved partner APIs and registries; all other websites must be blocked.

1. Diagram the VPC, PRIVATE subnet, proxy-only subnet, SWP gateway, NAT, and workload paths.
2. Choose explicit or next-hop mode and explain how to verify no bypass paths exist.
3. Build a table of workload identities, allowed destinations, priorities, and default decisions.
4. Draft a `policy.yaml`, an `ALLOW` rule, and a `gateway.yaml` following the Cloud SWP model.
5. Explain why an HTTP host rule is insufficient for filtering HTTPS in explicit mode.
6. If only `/reports` on an HTTPS domain may be accessed, list the TLS inspection components required.
7. Write two `curl` commands to test allow/deny, and describe how to inspect transaction logs.
8. Propose static egress IPs, metrics/alerts, and a rollback plan if a new policy blocks the build pipeline.

## Official References

- [Secure Web Proxy overview](https://cloud.google.com/secure-web-proxy/docs/overview) — modes, architecture, and limitations.
- [Initial setup steps](https://cloud.google.com/secure-web-proxy/docs/initial-setup-steps) — APIs, IAM, VPC, and proxy-only subnet.
- [Quickstart: explicit proxy](https://cloud.google.com/secure-web-proxy/docs/quickstart) — policy, rule, gateway, and testing.
- [Policies and rules](https://cloud.google.com/secure-web-proxy/docs/policies-and-rules-overview) — gateway security, authorization, rate limiting.
- [Configure gateway security rules](https://cloud.google.com/secure-web-proxy/docs/configure-rules) — CEL and HTTPS limitations.
- [Enable TLS inspection](https://cloud.google.com/secure-web-proxy/docs/enable-tls-inspection) — CA, policy, and trust.
- [TLS inspection overview](https://cloud.google.com/secure-web-proxy/docs/tls-inspection-overview) — mechanics and exceptions.
- [Use Cloud NAT for Secure Web Proxy](https://cloud.google.com/secure-web-proxy/docs/use-cloud-nat-for-swp) — public egress IPs.
- [Logs, metrics, and traces](https://cloud.google.com/secure-web-proxy/docs/monitor-logs) — monitoring operations.
- [View proxy transaction logs](https://cloud.google.com/secure-web-proxy/docs/view-proxy-transaction-logs) — log schema and queries.
- [Secure Web Proxy pricing](https://cloud.google.com/secure-web-proxy/pricing) — gateway and data processing fees.
