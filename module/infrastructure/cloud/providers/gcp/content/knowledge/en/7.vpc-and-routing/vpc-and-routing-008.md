# Private Google Access and Accessing Google APIs

An application running on a **Compute Engine** VM needs to read objects in **Cloud Storage**, send logs to **Cloud Logging**, or call the **Secret Manager API**. To reduce the attack surface, the operations team does not assign an external IP address (*external IP*) to the VM. A question arises: how can the VM still call Google APIs over HTTPS while the VPC network is tightly controlled?

**Private Google Access (PGA)** solves an important piece of this problem: it allows eligible resources in a VPC subnet, typically VMs with only internal IPv4 addresses, to connect to supported Google APIs and services. PGA is configured on the **subnet** and must work alongside **DNS**, **routes**, egress policies, and application access permissions. Enabling PGA does not replace authentication, IAM, or all other types of private connectivity to Google Cloud services.

This lesson belongs to the **VPC and Routing** chapter of the **CLOUD_PROVIDERS_GCP** module. Its content supports infrastructure design from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment examples, learners can select API access options, protect resources, automate configurations, and evaluate reliability and cost impacts.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of Private Google Access when a VM lacks an external IPv4 address.
2. Distinguish PGA from Cloud NAT, Private Service Connect, and Private Services Access.
3. Choose between accessing default Google API domains, `private.googleapis.com`, and `restricted.googleapis.com`.
4. Describe the packet path from a VM through DNS, routes, and firewalls to a Google API.
5. Enable PGA on a subnet, inspect DNS/routes, and verify connectivity using read commands or controlled configuration steps.
6. Diagnose common errors involving routing, domain names, IAM, OAuth scopes, and VPC Service Controls.

## 2. What Does Private Google Access Actually Do?

### 2.1. Context: A VM with Only an Internal IP

Example of a VM's network interface:

~~~text
Project: retail-prod
VPC:     retail-vpc
Subnet:  app-subnet (asia-southeast1)
VM:      api-worker-01
Internal IP: 10.20.10.15
External IPv4: none
~~~

The application on the VM calls `https://storage.googleapis.com` or an API via `*.googleapis.com`. Having no external IP does not mean the VM is completely blocked from talking to Google services. If **PGA is enabled on the subnet**, and the path and access conditions are valid, the VM can send requests to supported Google APIs without owning an external IPv4 address or using Cloud NAT solely for those APIs.

In this context, distinguish carefully:

- **Traffic source:** the VM in the subnet; PGA is a subnet setting rather than an IP address attached individually to the VM.
- **Destination:** Google APIs and services within the supported scope, not arbitrary Internet websites.
- **Connectivity:** requires DNS to resolve the service name, a valid route to the destination, and a path not blocked by egress policies.
- **Authorization:** the target Google service still checks identity, tokens, IAM, and API conditions.

PGA applies primarily to **IPv4** connectivity in scenarios supported by Google Cloud documentation. When designing for IPv6, hybrid, or serverless platforms, consult the specific connectivity guide for that environment; do not assume toggling a flag on one subnet automatically resolves every connectivity pattern.

### 2.2. At What Level Is the Feature Enabled?

Private Google Access is a property of a **regional VPC subnet**. If a VPC has three subnets, enabling PGA only on `app-subnet` does not enable it on the remaining subnets.

| Component | What PGA changes | What PGA does not do |
| --- | --- | --- |
| **Subnet** | Allows eligible VMs in the subnet to reach supported Google APIs using internal IPs via PGA mechanisms. | Does not automatically create subnets, VMs, or service accounts. |
| **VM** | VMs without external IPv4 can call Google APIs when the network is configured properly. | Does not automatically grant IAM roles or OAuth tokens. |
| **VPC route** | Proper routes to API destinations forward packets via supported next hops. | PGA does not automatically create arbitrary custom routes. |
| **DNS** | Can be paired with custom DNS settings to use private/restricted endpoints. | Enabling PGA alone does not rewrite every domain to `restricted.googleapis.com`. |
| **Firewall / policy** | Must allow appropriate traffic for connections to succeed. | PGA does not bypass egress denies, org policies, or VPC Service Controls. |
| **Cost** | May reduce the need for NAT solely to reach supported APIs. | Does not eliminate all service, data transfer, or related infrastructure charges. |

### 2.3. Visualizing the Request Path

~~~mermaid
flowchart LR
    VM["VM with internal IPv4 only"] --> DNS["DNS resolution: API hostname"]
    DNS --> IP["Google APIs destination IP"]
    VM --> ROUTE["VPC routes and egress policies"]
    IP --> ROUTE
    ROUTE --> API["Google API endpoint"]
    SA["Service account / token"] -. "Authentication" .-> API
    IAM["IAM / access controls"] -. "Authorization" .-> API
~~~

This diagram is a logical model. DNS resolves the name into a destination address; the VM then sends packets along the selected route. **DNS does not open the network, routes do not grant permissions, and IAM does not establish TCP connections.** Thus a `403 PERMISSION_DENIED` error is fundamentally different from `Could not resolve host` or `Connection timed out`.

## 3. Distinguishing PGA from Other Access Mechanisms

Names containing *private* often cause confusion, especially when a system simultaneously uses Cloud SQL, GKE, and Cloud Run.

| Mechanism | Primary need | Scope and characteristics |
| --- | --- | --- |
| **Private Google Access** | VMs without external IPv4 calling supported Google APIs/services. | Enabled on a subnet; works alongside DNS, routes, and network policies. |
| **Cloud NAT** | Workloads without external IPv4 connecting outbound to the Internet or certain external targets via NAT. | Translates source addresses for supported outbound connections; does not initiate inbound connections or replace IAM. |
| **Private Service Connect (PSC) for Google APIs** | Accessing Google APIs through an internal endpoint provisioned inside the VPC. | Creates dedicated endpoints, DNS, and policies; configuration resources and mechanics differ from traditional PGA. |
| **Private Services Access** | Private connectivity to Google-managed services supporting this mechanism, such as certain **Cloud SQL private IP** setups. | Uses service networking/peering and allocated IP ranges; not simply turning on PGA to call an API. |
| **VPC Service Controls** | Reduces risk of data exfiltration outside a protected boundary for supported services. | Restricts API access via service perimeters and rules; not a NAT or routing product. |
| **VPN / Interconnect** | Connects an on-premises network to a VPC. | Requires dedicated routing and DNS design; does not automatically let on-premises hosts call all Google APIs. |

**Example distinguishing two Cloud SQL paths:**

1. A program calls the **Cloud SQL Admin API** to inspect instance configuration: this is accessing a Google API; PGA can be part of the network solution.
2. A program opens a **data connection to a Cloud SQL database via private IP**: you must configure the corresponding private connectivity mechanism, routing, and database permissions; merely enabling PGA on the subnet is not enough to connect.

Similarly, Cloud Run is a serverless service with its own networking model. A Cloud Run service calling a Google API over its default egress path does not mean you enable PGA on a VM subnet for it. If configured to route traffic through a VPC (e.g., Direct VPC egress or a connector under supported models), evaluate paths, DNS, and permissions specifically for that setup.

## 4. Three Google API Domain and Endpoint Options

### 4.1. Accessing Default API Domains

A workload can call `storage.googleapis.com`, `secretmanager.googleapis.com`, `logging.googleapis.com`, etc. Default DNS may return shared Google API IP addresses. For VMs without external IPv4, **Private Google Access** and an appropriate route allow supported APIs to receive that traffic.

In a common setup, the VPC has a default `0.0.0.0/0` route via the **default internet gateway**. When PGA is enabled on the subnet, traffic from VMs without external IPv4 to supported Google APIs can use this matching route. The next-hop name "internet gateway" **does not prove** traffic travels over the public Internet; it is a Google Cloud logical next hop. Actual reachability still depends on destination addresses, PGA, and network rules.

For environments requiring tighter control over Google API destinations, review the two VIPs Google provides for private/restricted access.

### 4.2. `private.googleapis.com`

`private.googleapis.com` uses a dedicated set of IPv4 VIPs:

~~~text
199.36.153.8/30
199.36.153.8
199.36.153.9
199.36.153.10
199.36.153.11
~~~

When the network's DNS is configured to point eligible Google API hostnames to these VIPs, clients connect to addresses designated for private Google API access. This option fits cases needing access to supported Google APIs and services, including APIs not supported by VPC Service Controls.

**Private VIPs do not replace API authorization:** the service account still needs valid tokens, roles, and permissions; requests can still be rejected if a service perimeter or service policy forbids them.

### 4.3. `restricted.googleapis.com`

`restricted.googleapis.com` uses a dedicated set of IPv4 VIPs:

~~~text
199.36.153.4/30
199.36.153.4
199.36.153.5
199.36.153.6
199.36.153.7
~~~

The **restricted** endpoint is for APIs/services supported by **VPC Service Controls**. It helps align Google API paths with data boundaries, but does not expose the exact same set of APIs as `private.googleapis.com`. For an unsupported API, pointing its hostname to the restricted endpoint can cause requests to fail.

VPC Service Controls must still be **configured with a service perimeter** to enforce data access boundaries. Merely using `restricted.googleapis.com` addresses does not create a perimeter, grant IAM, or prevent every data exfiltration vector.

### 4.4. Endpoint Comparison Table

| Criterion | Default hostname | `private.googleapis.com` | `restricted.googleapis.com` |
| --- | --- | --- | --- |
| How it is used | Client calls standard API hostname. | DNS directs matching API hostnames to private VIPs. | DNS directs VPC-SC-supported API hostnames to restricted VIPs. |
| Example VIP range | Determined by API DNS. | `199.36.153.8/30` | `199.36.153.4/30` |
| Goal | Call supported APIs with proper PGA/route setup. | Steer Google API traffic through dedicated private endpoints. | Restrict API group to VPC Service Controls supported scope. |
| API compatibility | Depends on service and connection method. | Broader set of APIs than restricted, per current docs. | Only services listed as supported by Google. |
| IAM and authentication | Still required. | Still required. | Still required. |
| Auto-configures service perimeter? | No. | No. | No. |

Never force every Google-owned hostname onto one endpoint just because the domain name looks similar. Domains like `*.pkg.dev`, `gcr.io`, Google Workspace services, and specialized endpoints may require additional configuration or fall outside the expected support scope. Check documentation for the exact service, API, and domain name your application actually calls.

## 5. How DNS and Routes Coordinate with PGA

### 5.1. Name Resolution Is a Separate Step

Suppose an application sends a request:

~~~text
GET https://storage.googleapis.com/...
~~~

The DNS resolver looks up the IP address of `storage.googleapis.com`. If the organization creates a **Cloud DNS private zone** for `googleapis.com.`, it can provide a wildcard record so matching hostnames CNAME to `private.googleapis.com.` or `restricted.googleapis.com.`, whose A records hold the VIP addresses.

~~~text
storage.googleapis.com.
    -> CNAME private.googleapis.com.
private.googleapis.com.
    -> A 199.36.153.8
    -> A 199.36.153.9
    -> A 199.36.153.10
    -> A 199.36.153.11
~~~

**Wildcards do not necessarily cover every name:** for instance, a `*.googleapis.com.` record does not match the apex `googleapis.com.` itself or domains without the `.googleapis.com` suffix. If a zone or DNS policy already exists for that domain, design modifications and check for conflicts rather than creating duplicate zones.

When using Shared VPC, verify that the zone is attached to the **actual VPC network** used by workloads, even when that network lives in the host project. Do not assume placing a Cloud DNS private zone in an application project automatically makes it visible to all VMs using the shared network.

### 5.2. Selecting Routes to the VIP

Once DNS returns an address in `199.36.153.8/30`, the VPC must have a matching path for that range. A common design uses a route whose destination is the VIP range and next hop is the **default internet gateway**:

~~~text
Destination: 199.36.153.8/30
Next hop:    default internet gateway
VPC:         retail-vpc
~~~

If the VPC still retains a valid default `0.0.0.0/0` route via the default internet gateway, that route can serve VIP connectivity. In networks that removed the default route to restrict egress, create a specific route to the VIPs. A prefix-specific route also makes VIP routing more explicit.

Google Cloud selects routes per VPC routing rules, including path validity and destination specificity; **priority does not completely override prefix matching rules**. In particular, if custom routes, policy-based routes, or hybrid networks exist, verify no other path unintentionally hijacks routing.

### 5.3. Egress and DNS Policies

Allowing a route does not mean packets pass the firewall. If the organization enforces default-deny egress, allow required destinations and protocols per design—typically **TCP 443** to API endpoints and DNS traffic to the active resolver. Rules may reside in VPC firewalls, hierarchical firewall policies, or other control layers; do not open broad Internet ranges if only Google APIs are needed.

Under strict policies, traffic to Google APIs can be monitored using a combination of VPC Flow Logs (if enabled and within supported scope), Cloud DNS logging, service Cloud Audit Logs, and application telemetry. Never assume a single log source captures all application requests completely.

## 6. Hands-On: Configuring PGA on Compute Engine

The following example assumes a **project**, VPC, and subnet already exist. Values `retail-prod`, `retail-vpc`, `app-subnet`, and `asia-southeast1` are samples only. Commands containing `update` or `create` modify real resources; run them only in an authorized environment after assessing impact on active workloads.

### 6.1. Inspecting the Existing Subnet

~~~bash
PROJECT_ID="retail-prod"
NETWORK="retail-vpc"
SUBNET="app-subnet"
REGION="asia-southeast1"

# Read subnet configuration without modifying resources.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,network,region,ipCidrRange,privateIpGoogleAccess)"
~~~

The `privateIpGoogleAccess` field reflects the on/off state of the feature on the IPv4 subnet. When using Shared VPC, administrators must query and update the subnet in the **host project**, not mistakenly in a workload service project.

### 6.2. Enabling Private Google Access

~~~bash
# Mutates configuration of an existing subnet.
gcloud compute networks subnets update "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --enable-private-ip-google-access

# Read back and verify status after the change.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(privateIpGoogleAccess)"
~~~

Expected output is `True` or the CLI's equivalent representation. This operation does not add external IPs to VMs, create Cloud NAT, or grant roles to service accounts.

### 6.3. Inspecting Routes Before Changing DNS

~~~bash
# View route structure and next hops in the project.
gcloud compute routes list \
  --project="$PROJECT_ID" \
  --format="table(name,network.basename(),destRange,priority,nextHopGateway)"
~~~

For a VPC using a default route via the default internet gateway, verify that route against active egress policies. If the organization deleted the default route and chose to access via `private.googleapis.com`, you may need to create a route specifically to the VIPs:

~~~bash
# Write operation: use only if architecture confirms a dedicated route is needed.
gcloud compute routes create googleapis-private-vip \
  --project="$PROJECT_ID" \
  --network="$NETWORK" \
  --destination-range="199.36.153.8/30" \
  --next-hop-gateway="default-internet-gateway" \
  --priority=800
~~~

If the organization uses `restricted.googleapis.com`, the corresponding destination range is `199.36.153.4/30`. Route configuration must be compatible with policies, existing routes, and the actually selected endpoint; do not add both ranges just to "be safer."

### 6.4. Illustrative DNS Configuration for Private VIPs

If you want API hostnames under `*.googleapis.com` to use private VIPs, one option is creating a **Cloud DNS private zone** on the appropriate VPC:

~~~bash
# Bash example: ONLY run when no conflicting zone/policy exists.
gcloud dns managed-zones create private-googleapis-zone \
  --project="$PROJECT_ID" \
  --dns-name="googleapis.com." \
  --description="Private resolution for Google APIs" \
  --visibility="private" \
  --networks="$NETWORK"

# A records for target private.googleapis.com.
gcloud dns record-sets create private.googleapis.com. \
  --project="$PROJECT_ID" \
  --zone="private-googleapis-zone" \
  --type="A" \
  --ttl=300 \
  --rrdatas="199.36.153.8,199.36.153.9,199.36.153.10,199.36.153.11"

# Redirect matching subdomains to private VIPs.
gcloud dns record-sets create '*.googleapis.com.' \
  --project="$PROJECT_ID" \
  --zone="private-googleapis-zone" \
  --type="CNAME" \
  --ttl=300 \
  --rrdatas="private.googleapis.com."
~~~

The example above illustrates configuring **from scratch** in an authorized environment. If the VPC already has a `googleapis.com.` private DNS zone, update the existing zone via your change process. If the **restricted** endpoint is needed, change the target record to `restricted.googleapis.com.` and the A records to `199.36.153.4` through `199.36.153.7`, while confirming every API used by the application is supported.

Certain Google API domains, artifact registries, or other endpoints require separate DNS records and support verification. Do not treat this wildcard as a catch-all solution for every Google Cloud service.

### 6.5. Verifying on a VM Without an External IP

On a VM inside the PGA-enabled subnet, test in order:

~~~bash
# See which IP the API hostname resolves to.
nslookup storage.googleapis.com

# Test HTTPS connectivity to the endpoint.
curl -I --connect-timeout 5 --max-time 15 \
  https://storage.googleapis.com/
~~~

If using private VIPs, DNS records should resolve to `199.36.153.8`–`199.36.153.11` via CNAME or an equivalent mechanism. If the endpoint returns `400`, `401`, or `403` over HTTPS, treat that as a sign that **DNS, TCP, and TLS are working well enough to receive an HTTP response**; it does not prove the caller has permission to access the resource. To verify business logic, make a real authenticated API call using a valid identity and verify specific IAM permissions.

If the network uses `restricted.googleapis.com`, DNS results should reflect `199.36.153.4`–`199.36.153.7`. With default DNS, IPs are not required to fall inside those two VIP ranges; verification must match the chosen connectivity approach.

## 7. IAM, Tokens, and VPC Service Controls: Mandatory Layers

### 7.1. PGA Does Not Replace Authentication

A VM application should typically use a **workload-bound service account** and **Application Default Credentials (ADC)**, avoiding embedding long-lived JSON keys in code or images.

Logical flow:

~~~mermaid
sequenceDiagram
    participant A as App on VM
    participant M as Metadata service / credentials
    participant G as Google API
    A->>M: Fetch token for workload identity
    M-->>A: Appropriate token
    A->>G: HTTPS request + token
    G->>G: Verify token, IAM, and policies
    G-->>A: Result or 401/403 error
~~~

For example, a VM reading an object in Cloud Storage must have **object read permission** under an appropriate IAM policy. Reaching `storage.googleapis.com` only solves the network layer. On Compute Engine VMs, **OAuth access scopes** can also restrict API requests alongside IAM; when troubleshooting, inspect both scopes and the actual runtime identity.

### 7.2. Restricted VIPs and Perimeters

In systems holding sensitive data, security teams may combine `restricted.googleapis.com` with **VPC Service Controls** to govern access to supported services by service perimeter. Evaluate:

1. Which projects and resources belong inside the perimeter.
2. Which APIs are supported by VPC Service Controls and included in the protected service list.
3. Valid ingress/egress access paths into/out of the perimeter, including CI/CD, workloads, and administrators.
4. Whether DNS, routes, and egress policies steer traffic accurately to the chosen endpoint.
5. Logging and processes for handling denied access events.

Never use restricted VIPs as a substitute for least-privilege IAM or other data-loss controls. A misconfigured DNS setup can break auxiliary services from calling APIs even before perimeter rules are evaluated.

### 7.3. Things to Remember for GKE and Cloud Run

- **GKE private nodes** are typically VMs/nodes without external IPs; when nodes or workloads call Google APIs over the corresponding network path, verify PGA, DNS, routes, and cluster conditions. Workload authentication should use GKE-supported identity mechanisms such as Workload Identity Federation for GKE where appropriate.
- **GKE cluster control planes** have their own networking, authentication, and API access mechanisms; do not assume PGA on the node subnet automatically opens all connections to the control plane.
- **Cloud Run** has a default egress path and optional VPC routing. Only evaluate PGA and routes for traffic actually traversing the workload's VPC; verify Direct VPC egress/connector details, route settings, and IAM.
- **Cloud SQL** involves both the Admin API and database protocol connections. Using PGA to call the Admin API does not replace Cloud SQL private IP, connection permissions, database credentials, firewalls, or choosing Cloud SQL Auth Proxy/connectors.

## 8. Practical Design for a Sales System

Suppose a team operates an ordering system on Compute Engine and Cloud Run; order data resides in Cloud SQL, product images in Cloud Storage, and some asynchronous processing runs on GKE. The organization mandates **no external IPv4 on order-processing VMs** and access strictly to necessary APIs.

### 8.1. Requirements and Approaches

| Need | Design decision | How to verify |
| --- | --- | --- |
| VM calls Cloud Storage API | Enable PGA on the VM's subnet; configure DNS/routes matching the API endpoint. | DNS, HTTPS, and test object read with a restricted identity. |
| VM writes logs or reads Secret Manager | Confirm supported APIs/services; grant IAM to the service account. | Inspect tokens, permissions, and API responses. |
| VM calls partner Internet service | PGA does not solve this; consider Cloud NAT or a managed egress option. | Check routes, NAT, and egress rules. |
| Cloud SQL uses private IP | Design dedicated private connectivity for the database. | Check DNS/IP, connectivity path, database credentials. |
| GKE nodes without external IP | Verify subnet PGA, DNS, egress paths, and identity. | Test from node/pod matching actual access patterns. |
| Data requires a service perimeter | Evaluate restricted VIP + VPC Service Controls if APIs are supported. | Check supported service list, ingress/egress policies, and denial logs. |
| Cloud Run accesses Google APIs | Determine whether traffic uses default egress or VPC, then design networking accordingly. | Test from the runtime revision using the exact service account. |

### 8.2. Logical Architecture

~~~mermaid
flowchart TB
    subgraph V["VPC retail-vpc"]
        S["Subnet app-subnet: PGA enabled"]
        VM["Compute Engine VM: internal IP"]
        S --> VM
        DNS["Cloud DNS private zone (optional)"]
        ROUTE["Route to Google API VIP"]
        VM --> DNS
        VM --> ROUTE
    end
    ROUTE --> API["Google APIs: Storage / Logging / Secret Manager"]
    VM --> DB["Cloud SQL private IP via private connectivity"]
    VM --> NAT["Cloud NAT if other Internet access is needed"]
    IAM["Service accounts + IAM"] -. "Access permissions" .-> API
    PER["VPC Service Controls if applied"] -. "Perimeter" .-> API
~~~

Not every arrow in this diagram represents the same protocol or routing mechanism. Cloud SQL private IP, Google APIs VIPs, and Internet egress are **three distinct connectivity paths**, each with its own policies.

### 8.3. Step-by-Step Deployment Flow

1. **Inventory reality:** identify VMs, subnets/regions, VPCs, service accounts, API hostnames, and target projects.
2. **Classify egress needs:** separate supported Google APIs, partner Internet, database private IPs, and specialized endpoints.
3. **Select endpoints:** default, private VIP, or restricted VIP based on security requirements and compatible API lists.
4. **Design DNS and routes:** include Shared VPC, Cloud DNS, and existing network exceptions; avoid overlapping configurations.
5. **Enable PGA on appropriate subnets**, checking status before and after.
6. **Grant least-privilege IAM** to workloads; check VM OAuth scopes if applicable.
7. **Test from the actual environment:** DNS, TLS, authenticated API calls, database paths, and partner Internet.
8. **Observe and operate:** monitor DNS errors, timeouts, 401/403s, quotas, route drift, and firewall/policy changes.
9. **Manage via IaC and review:** standardize subnet, DNS, route, and permission configurations for reproducibility and impact assessment during changes.

Never use `curl` succeeding against one API to claim every service in the system is reachable. Each hostname may differ in DNS, API support, permissions, and VPC SC rules.

## 9. Methodical Troubleshooting

### 9.1. Error Classification Table

| Symptom | First layer to check | Likely causes | Verification step |
| --- | --- | --- | --- |
| `Could not resolve host` | DNS | Wrong private zone, resolver, CNAME, or unhandled domain. | `nslookup`/Cloud DNS config from the VM itself. |
| DNS returns unexpected IP | DNS/endpoint | Zone not applied, multiple DNS views, not switched to private/restricted VIP. | Check CNAME and A records, networks bound to the zone. |
| TCP timeout | Route/firewall/egress | PGA not enabled on subnet, wrong route, egress deny, or unsupported path. | Check `privateIpGoogleAccess`, VPC routes, firewalls/hierarchical policies. |
| TLS or hostname verification error | TLS/proxy/DNS | Using IP instead of hostname in TLS, custom proxy, or wrong certificate. | Connect via standard hostname and check proxy/trust chain. |
| HTTP `401 UNAUTHENTICATED` | Authentication | Missing token or invalid token. | Check ADC, runtime identity, and how the API is called. |
| HTTP `403 PERMISSION_DENIED` | IAM/scopes/policy | Missing role, restrictive OAuth scopes, VPC SC, or target policy denial. | Check principal, permissions, scopes, and denial logs. |
| API over restricted VIP fails | Endpoint support | API is not in the VPC Service Controls supported set. | Check supported list and choose an appropriate endpoint. |
| Partner Internet unreachable | Internet egress | PGA does not provide access to arbitrary websites outside Google APIs. | Check Cloud NAT, egress routes, and policies. |
| Cloud SQL private IP fails to connect | Private connectivity/database | Confusing Admin API with the database connection path. | Check private connectivity, IP, firewalls, database auth. |

A single failure can stem from multiple layers simultaneously. The least-effort diagnostic order is **hostname → IP → route → TCP/TLS → authentication → authorization → business logic**.

### 9.2. Read-Only Command Checklist

~~~bash
# From an admin machine with permissions on the project owning the subnet.
gcloud compute networks subnets describe app-subnet \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml(name,network,privateIpGoogleAccess)"

gcloud compute routes list \
  --project=retail-prod \
  --format="table(name,destRange,nextHopGateway,priority)"

# If a Cloud DNS private zone is configured in this project.
gcloud dns managed-zones describe private-googleapis-zone \
  --project=retail-prod

gcloud dns record-sets list \
  --project=retail-prod \
  --zone=private-googleapis-zone
~~~

Cloud DNS commands will report not-found if the environment uses default DNS or if the zone lives in another project; that is not necessarily an error. In Shared VPC, inspect the exact host project and VPC. If a project has multiple routes or subnets, confirm they actually sit on the specific VM's path.

### 9.3. Avoid Three False Conclusions

**"DNS resolved to `199.36.153.8`, so calling the API will definitely work."** Not enough. You still need routes, egress policies, PGA/supported connectivity design, and successful HTTPS.

**"HTTP 403 proves PGA is broken."** Inaccurate. HTTP 403 means the request reached an HTTP component capable of responding; inspect the error payload, identity, permissions, and VPC Service Controls.

**"Enabling Cloud NAT automatically enables PGA."** No. Cloud NAT and PGA are separate settings. A workload may use NAT for partner Internet traffic and PGA or PSC for Google APIs.

## 10. Security, Operations, and Cost

### 10.1. Multi-Layered Data Protection

A production configuration may require:

- Withholding external IPs from VMs handling sensitive data when unnecessary.
- Enabling PGA on subnets calling Google APIs, or choosing PSC endpoints/appropriate designs.
- Defining clear DNS, routes, and egress policies; restricting unnecessary egress paths.
- Using dedicated service accounts per workload, least-privilege IAM, and never embedding secret keys in code.
- Using VPC Service Controls when perimeter controls and supported services apply; testing permitted egress/ingress.
- Observing live traffic and errors, with clear ownership for subnet/firewall changes.

Private Google Access **is not a firewall and does not guarantee against data exfiltration** if applications still have other egress paths or overly broad IAM. Data protection requires coordinating identity, networking, policies, encryption, and application controls.

### 10.2. Reliability and Operability

Seemingly small changes—such as creating a new DNS private zone, deleting a default route, or applying an egress deny—can simultaneously break API calls across many VMs and GKE workloads. To reduce risk:

1. Store DNS, route, and subnet configurations in IaC when your organization uses that workflow.
2. Test in a sandbox subnet or equivalent nonproduction environment.
3. Test every actual hostname used, not just one representative endpoint.
4. Monitor API error rates, latency, quotas, and infrastructure change events.
5. Prepare a DNS/route rollback plan, ensuring you do not accidentally reopen unintended Internet egress.

Measure application SLOs from real user operations. A VM successfully calling one Google API does not prove all features involving Cloud Storage, Cloud SQL, GKE, and Cloud Run meet SLOs.

### 10.3. Cost Impact

PGA can help avoid deploying Cloud NAT **solely to reach supported Google APIs** from VMs without external IPs. Still, the final choice depends on:

- Whether third-party Internet traffic requires Cloud NAT or another mechanism.
- Target Google Cloud service charges and inter-region/link data transfer under current pricing tables.
- Cloud Logging, Cloud DNS, monitoring, audit retention, and policy management costs if applicable.
- Operational overhead of maintaining DNS, policies, routes, and specialized configurations.

Never conclude "PGA makes all traffic free" or "having PGA makes egress cost zero." When incorporating into real architectures, compare costs using Billing data and current pricing tables.

## 11. Practice Exercises

### Exercise 1 — Classify Solutions

Given four requirements:

1. A VM without an external IP needs to call the Secret Manager API.
2. A VM without an external IP needs to reach a third-party payment API.
3. An application needs to connect to Cloud SQL via private IP.
4. A workload inside a service perimeter needs to call a Google API supported by VPC Service Controls.

**Guided answers:** (1) evaluate PGA/PSC and IAM; (2) evaluate Internet egress such as Cloud NAT; (3) configure private connectivity to Cloud SQL; (4) evaluate restricted VIP + VPC Service Controls along with IAM. Each case requires specific routes, DNS, and service conditions.

### Exercise 2 — Read Configuration

Run the read command with the right project and region:

~~~bash
gcloud compute networks subnets describe app-subnet \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="value(privateIpGoogleAccess)"
~~~

If the result is `False`, explain why a VM without an external IPv4 in that subnet might fail to call a Google API via PGA, and what additional conditions must be checked before enabling the flag.

### Exercise 3 — Compare DNS

Two environments return:

~~~text
Environment A: storage.googleapis.com -> 199.36.153.8
Environment B: storage.googleapis.com -> 199.36.153.4
~~~

**Questions:** Which environment likely uses the private VIP, and which uses the restricted VIP? When choosing Environment B, how must you check VPC Service Controls API support and the perimeter? Why does a DNS record alone not prove a request is authorized?

### Exercise 4 — Analyze a 403 Error

`curl` to a Google API received an HTTPS response, yet the application still reports `403`. List at least four steps: check identity/token, check IAM permissions, check OAuth scopes if running on a VM, check VPC Service Controls, and inspect error details. Never grant Owner/Editor just to "make it work."

### Exercise 5 — Design a Network with Restricted Egress

A VM needs to call Cloud Storage and a partner website, while the VPC has deleted its default route. Propose routes, DNS, PGA/PSC, and Cloud NAT (if used) tailored to the two destination groups. Explain why a route to `199.36.153.8/30` does not create a valid path to the partner website's IP.

## 12. Key Takeaways and Official Documentation

| Question | Key point to remember |
| --- | --- |
| Who is PGA for? | Typical case: VMs with only internal IPv4 in a PGA-enabled subnet needing to call supported Google APIs. |
| Where is it enabled? | A **subnet** property, not an IAM role or a VM external IP. |
| What is DNS for? | Directs API hostnames to default IPs, private VIPs, or restricted VIPs. |
| What is a route for? | Carries packets to API addresses via valid next hops; firewalls/egress must still be checked. |
| How does `private.googleapis.com` differ from `restricted.googleapis.com`? | Private VIP serves a broader set of Google APIs; restricted VIP is for APIs supported by VPC Service Controls. |
| Does PGA replace Cloud NAT? | Only for accessing supported Google APIs; partner Internet is a separate egress problem. |
| Does PGA grant API permissions? | No; authentication, IAM, OAuth scopes, and service perimeters still apply. |
| Once PGA is enabled, can Cloud SQL private IP connect? | Not yet; reaching the database via private connectivity is a separate setup. |

When working with real infrastructure, consult official documentation because supported services, endpoints, DNS, and networking mechanics can evolve:

- [Private Google Access overview](https://cloud.google.com/vpc/docs/private-google-access)
- [Configure Private Google Access](https://cloud.google.com/vpc/docs/configure-private-google-access)
- [Private Service Connect for Google APIs](https://cloud.google.com/vpc/docs/private-service-connect)
- [Private services access](https://cloud.google.com/vpc/docs/private-services-access)
- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Supported products for VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/supported-products)
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview)
- [Cloud DNS overview](https://cloud.google.com/dns/docs/overview)

A successful Google API connection requires the **right subnet, right destination address, right route, right egress, and right identity**. By cleanly separating these layers, you can design VMs without external IPs that still execute Google Cloud tasks, enforce data access controls, and troubleshoot network issues methodically.
