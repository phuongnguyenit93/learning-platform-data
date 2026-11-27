# Frontend, Backend Service, and Health Check

An application may run across multiple Compute Engine VMs, multiple GKE Pods, or multiple Cloud Run revisions. Users only need to visit a single domain such as `shop.example.com`, while the system must decide **where to receive requests, which service to route them to, and which backend is healthy enough to handle them**. Google Cloud Load Balancing separates these responsibilities into independently manageable components: **frontend**, **backend service**, and **health check**.

This lesson belongs to the **Load Balancing and Content Delivery** chapter in the `CLOUD_PROVIDERS_GCP` module. By combining knowledge of organization/projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, databases, and release automation, you can deploy systems securely, monitor reliability, and control costs. This lesson focuses on **HTTP(S) Application Load Balancers**, particularly the *global external Application Load Balancer* using the `EXTERNAL_MANAGED` model; key differences for regional, internal, and Network Load Balancers are explained separately to prevent misapplication.

## Learning Objectives

After this lesson, you will be able to:

1. Describe the path of an HTTP(S) request from DNS to frontend, URL map, backend service, and backend.
2. Distinguish **forwarding rule**, **target HTTP(S) proxy**, **TLS certificate**, **URL map**, **backend service**, **backend group**, and **health check**.
3. Explain the role of health checks and why a running backend might still fail to serve traffic.
4. Identify backend types such as managed instance group, zonal NEG, serverless NEG, and backend bucket.
5. Design host/path-based routing and understand routing policy limits when backends are unhealthy.
6. Practice `gcloud` commands to create/inspect components of a global external Application Load Balancer for a VM instance group.
7. Distinguish health check configuration for VM/GKE from the **Cloud Run serverless NEG exception**.
8. Analyze 502/503 errors, TLS, firewalls, routing, capacity, logging, and costs.

## 1. Big Picture of an Application Load Balancer

Consider an e-commerce system with a web interface and an API, placed in project `commerce-prod`:

~~~mermaid
flowchart LR
    U["User<br/>https://shop.example.com"]
    DNS["Cloud DNS or other DNS<br/>shop.example.com → LB IP"]
    FR["Frontend: forwarding rule<br/>Public IP + TCP 443"]
    PROXY["Target HTTPS proxy<br/>TLS certificate"]
    MAP["URL map<br/>/api/* → API<br/>/* → Web"]
    WEB["Backend service: web"]
    API["Backend service: api"]
    HW["Health check: web"]
    HA["Health check: api"]
    BW["Instance group: Web VMs"]
    BA["Zonal NEG or MIG: API"]
    U --> DNS --> FR --> PROXY --> MAP
    MAP --> WEB --> BW
    MAP --> API --> BA
    HW -. "Monitors" .-> BW
    HA -. "Monitors" .-> BA
~~~

**The path above applies to an Application Load Balancer example with standard VM/NEG backends.** If a backend is a **serverless NEG** pointing to Cloud Run, the backend service **must not have a health check attached**. If using a **backend bucket** to serve Cloud Storage objects, that is a different backend resource type from a backend service.

A request can go through these steps:

1. DNS returns the public IP of the load balancer.
2. **Forwarding rule** receives connections to the configured IP/protocol/port and points to the **target HTTPS proxy**.
3. **Target proxy** completes the TLS handshake using the domain's certificate and processes the HTTP request.
4. **URL map** evaluates host/path or supported routing rules to select a backend service or backend bucket.
5. **Backend service** picks an eligible backend according to configuration, health signals, and capacity.
6. The backend processes the request; the response is returned to the client through the load balancer's proxy mechanism.

Key takeaway: **the frontend determines where clients connect**, **the URL map selects which service receives the request**, and **the backend service determines how to distribute across the backend group**. Health checks provide serving-readiness signals for backend types that support them.

## 2. Frontend: IP, Port, Forwarding Rule, and Target Proxy

The **frontend** is the surface users see when sending traffic to the load balancer. Depending on the load balancer type, configuration typically includes an IP address, protocol, port, and the component accepting/delegating connections.

### 2.1. Forwarding Rule

A **forwarding rule** binds an **IP address + protocol + port** to a target. For an Application Load Balancer, the target is typically a **target HTTP proxy** or **target HTTPS proxy**.

Example:

~~~text
Name: shop-https-rule
Scope: global
IP: a global IPv4 address (can be pre-reserved)
Protocol: TCP
Port: 443
Target: shop-https-proxy
~~~

With a global external Application Load Balancer, the forwarding rule can use a global public IP in an appropriate network tier. **DNS does not replace a forwarding rule**: DNS only resolves domain names to an IP; the forwarding rule specifies the port/target handling requests arriving at that IP.

Do not confuse `--ports=443` on the forwarding rule with the application port on the backend (such as `8080`). These are **two separate connections** in the proxy model.

### 2.2. Target HTTP(S) Proxy

A **target HTTP proxy** receives HTTP; a **target HTTPS proxy** handles HTTPS connections and TLS certificates per product capabilities. The proxy references a **URL map** to decide routing.

In the HTTPS model:

- The TLS certificate must match the domain name and be in an active/usable state.
- Clients connect to the HTTPS proxy at the frontend.
- The proxy can forward to backends over HTTP or HTTPS depending on the **backend service protocol**; enabling HTTPS at the frontend **does not automatically turn** backend communication into HTTPS.
- Configure an HTTP → HTTPS redirect explicitly if you want to enforce TLS. Redirects are a **separate rule** (typically via an HTTP frontend's URL map), not an automatic side effect of creating an HTTPS proxy.

### 2.3. Example: Two Frontends Serving the Same Website

| Frontend | Components | Desired Behavior |
| --- | --- | --- |
| `http://shop.example.com:80` | Forwarding rule 80 → target HTTP proxy → redirect URL map | Returns redirect to HTTPS |
| `https://shop.example.com:443` | Forwarding rule 443 → target HTTPS proxy → backend URL map | Serves the application over TLS |

Components can share the same public IP when permitted by the forwarding rule type and IP/port/protocol combination. **Do not expose plain HTTP 80** simply because an HTTPS frontend exists; intentionally design a redirect or omit port 80.

## 3. URL Map: Deciding Which Application Receives a Request

One frontend can serve multiple paths or multiple hostnames. The **URL map** inspects supported HTTP attributes to select a **backend service**, **backend bucket**, or perform an action such as a redirect.

Examples:

| Request | Routing Rule | Destination |
| --- | --- | --- |
| `https://shop.example.com/` | Default route | Backend service `web-backend` |
| `https://shop.example.com/api/orders` | Path prefix `/api/*` | Backend service `orders-api-backend` |
| `https://static.example.com/logo.svg` | Host `static.example.com` | Backend bucket or backend service serving static content |
| `http://shop.example.com/checkout` | HTTP redirect URL map | HTTPS frontend |

### 3.1. URL Maps Do Not Check Backend Health

The URL map answers: **which route does this request belong to?** The backend service answers: **which backend can handle the routed request?** If the `/api/*` route points to the API backend service and every endpoint in that group is unhealthy, the URL map **does not automatically fall back to the web backend**.

~~~mermaid
flowchart TD
    R["HTTP request /api/orders"] --> M["URL map selects orders-api-backend"]
    M --> S{"Does backend service have an eligible backend?"}
    S -->|Yes| B["Distribute request to appropriate backend"]
    S -->|No| E["Request may fail; inspect LB errors"]
~~~

To achieve fallback, retry, traffic splitting, or failover behavior, you must **configure features explicitly supported by the load balancer and backend type**, and test them. Never infer fallback merely from the existence of two backend services.

### 3.2. Available Routing Mechanisms

Depending on the Application Load Balancer type and deployment mode, routing can be based on:

- Hostname/host rules.
- URL path or path prefix.
- Headers, query parameters, and advanced route rules where supported.
- Redirects, rewrites, or weighted traffic splitting per corresponding features.

For example, during a release, a team might split a percentage of traffic to a canary version if supported by the load balancer and backend; request percentage **does not equal** unique user percentage and must be monitored as a rollout decision.

## 4. Backend Service: Distribution Policy to Backends

A **backend service** is the central configuration governing how the load balancer connects to backends. A backend service can be **global or regional** depending on the load balancer type; its configuration must match the forwarding rule, load balancing scheme, and backend types.

Key fields typically include:

| Attribute | Role | What to Check |
| --- | --- | --- |
| **Protocol** | Protocol the proxy uses toward backends (HTTP, HTTPS, HTTP/2, or supported type) | Does the backend actually serve that protocol? |
| **Backends** | Attached instance groups or network endpoint groups (NEGs) | Right group, zone/region, endpoint count? |
| **Health check** | Probes VM/endpoint backends as supported | Path, port, response, and firewalls match? |
| **Balancing mode** | How capacity is interpreted via utilization/rate/connection depending on backend & LB type | Compatible with backend type? |
| **Timeout** | Backend request processing timeout per supported mechanism | Could long-running APIs time out? |
| **Session affinity** | Hint to keep a client on the same backend per supported policy | Is stateful session needed, or should it be stateless? |
| **Connection draining** | Grants active connections a grace window when removing a backend | Tuned for rollouts/scale-downs? |
| **Logging** | Observes connections, errors, latency | Enabled and sampled appropriately for cost? |
| **Cloud CDN/Cloud Armor** | Caching or traffic security policies on supported configs | Compatible with backend type and deployment scope? |

Not every attribute applies to every backend. **Serverless NEGs** do not support health check configuration and do not use standard balancing modes like `UTILIZATION`/`RATE`/`CONNECTION` to distribute traffic the way VM backends do.

### 4.1. What Resources Can Be Backends?

| Backend | Example | Backend Service Health Check |
| --- | --- | --- |
| **Managed instance group (MIG)** | Auto-scaling Compute Engine VM group | Typically uses VM health check |
| **Unmanaged instance group** | Manually operated VM group | Typically uses VM health check |
| **Zonal NEG with VM IP:port endpoints** | `GCE_VM_IP_PORT`, commonly used with compatible containers/workloads | Endpoint/port health check supported |
| **Serverless NEG** | Cloud Run, certain other serverless services | **Attaching health checks is NOT supported** |
| **Backend bucket** | Cloud Storage bucket used as static content backend | Not a backend service and has no VM health check |

With GKE, an Ingress or Gateway API controller can create/manage backend services and health checks. Manually editing controller-managed resources can be overwritten when the controller reconciles; configure via the appropriate Kubernetes/GKE mechanism instead.

### 4.2. Named Ports for Instance Groups

For a **proxy load balancer** using an instance group backend, the `backend service` typically references a **named port**, such as `http`, and the instance group maps that name to the actual port number.

~~~text
Frontend forwarding rule: TCP 443
  → HTTPS proxy
  → URL map
  → backend service: port-name=http
  → instance group: http=8080
  → VM backend: TCP 8080
~~~

A named port is **not** the frontend port. If the backend service has `--port-name=http` but the instance group lacks the `http:8080` mapping, the proxy may not know the correct application port.

**Named ports do not apply identically to every NEG.** For `GCE_VM_IP_PORT`, the port is part of each endpoint; for serverless NEGs, endpoints represent the serverless service rather than a VM port.

### 4.3. A Backend Service Is Not the VM or Cloud Run Service Itself

Creating a backend service does not mean servers are running. You must still **attach a backend group**, configure application listeners, firewall rules, health checks if supported, and ensure the application runs on the right endpoint.

Conversely, a VM returning HTTP 200 from inside the VPC does not guarantee the load balancer sees it as healthy; health checks could still fail due to DNS/routing/firewall/port mismatches or timeouts.

## 5. Health Check: Detecting Which Backends Are Eligible for Traffic

**Health checks** are periodic probes from Google Cloud systems to backends to determine responsiveness. A health check can use HTTP, HTTPS, TCP, SSL, HTTP/2, or gRPC depending on the supported load balancer/backend type. For an HTTP backend on VMs, an HTTP probe is a straightforward choice.

~~~mermaid
sequenceDiagram
    participant HC as Google Cloud health checker
    participant VM as Backend VM :8080
    participant LB as Backend service
    HC->>VM: GET /healthz
    VM-->>HC: HTTP 200 OK
    HC->>LB: Backend healthy after threshold met
    Note over VM: App stops or becomes unready
    HC->>VM: GET /healthz
    VM--xHC: Timeout or non-200 HTTP status
    HC->>LB: Backend unhealthy after failure threshold
~~~

Health checks commonly configure:

- **Protocol:** HTTP/TCP/HTTPS/gRPC; must match how the backend responds.
- **Port:** probe port; can be a fixed port or another supported selection mechanism.
- **Request path:** for HTTP(S), e.g., `/healthz`.
- **Check interval:** spacing between probes from each checker.
- **Timeout:** how long to wait for a single probe result.
- **Healthy threshold:** consecutive successful probes required before marking healthy.
- **Unhealthy threshold:** consecutive failed probes required before marking unhealthy.

### 5.1. Designing the `/healthz` Endpoint for Its True Purpose

Example VM web app response:

~~~http
GET /healthz HTTP/1.1
Host: shop.example.com

HTTP/1.1 200 OK
Content-Type: text/plain

ok
~~~

Standard HTTP probes expect **status 200**; redirects to login, 401/403/404 errors, or 5xx codes can cause probes to fail. If the application redirects all HTTP to HTTPS, consider an HTTPS health check or an appropriate HTTP probe endpoint so probes are not unexpectedly redirected.

A health endpoint should:

1. Respond quickly and reliably once the backend is genuinely ready to handle requests.
2. Not require user tokens or login for probes, while protecting it via probe source firewall rules and proper scoping.
3. Not execute heavy database queries on **every** health check.
4. Reflect critical dependencies if the application cannot serve without them.
5. Avoid causing all backends to be marked unhealthy simultaneously if a non-critical auxiliary service has a transient hiccup.

**Readiness differs from liveness:** readiness indicates whether an instance is ready to accept requests; liveness indicates whether a process needs restarting. Load balancer health checks primarily govern **traffic distribution** decisions. MIG autohealing and Kubernetes probes may require different targets, timeouts, and thresholds.

### 5.2. A Health Check Is Not an End-to-End Business Transaction

A backend returning 200 on `/healthz` does not prove the `/api/orders` route works properly. The probe might only test the HTTP process while the database fails on a separate API. Therefore, combine health checks with:

- **Synthetic HTTP tests** for critical business flows.
- `5xx`, latency, and request count metrics.
- Application tracing and logs.
- Alerts on saturation, queue depth, database connections, and resource usage.
- Defined SLOs, error budgets, and incident runbooks.

### 5.3. Exception: Cloud Run via Serverless NEG

For a **serverless NEG** connecting Cloud Run to an Application Load Balancer, Google Cloud **does not support health checks** on the backend service. You **do not configure** an HTTP health check for this backend service; monitoring Cloud Run runtime health, application errors, and service telemetry must be handled through Cloud Run's own mechanisms. Some models support **outlier detection** to reduce sending new requests to an erroring serverless backend, but that is **not a traditional HTTP health check**.

If a Cloud Run tutorial shows a "Create backend service" step, do not add `--health-checks` just because a Compute Engine example did.

## 6. Health Checks Depend on Firewalls and Network Paths

For VMs or zonal NEGs behind a global external Application Load Balancer, backends must allow Google Cloud health check probes and appropriate proxy traffic. **Never open ingress `0.0.0.0/0` to the application port just to fix a health check failure.**

Per Cloud Load Balancing documentation, relevant IPv4 source ranges for a **global external Application Load Balancer** with VM/zonal NEG backends include:

~~~text
35.191.0.0/16
130.211.0.0/22
~~~

Which ranges to allow depends on the **LB type**, backend type, IPv4/IPv6, proxy architecture, and other firewall rules. For health checks on certain managed global external Application Load Balancers, documentation notes `35.191.0.0/16` as the IPv4 probe source; `130.211.0.0/22` remains relevant for GFE proxy traffic to VM/zonal NEGs and other configurations. Always cross-check the **exact LB type table** when creating firewalls to allow the right source ranges and backend ports.

**Regional external Application Load Balancer** uses Envoy proxies and additionally requires a **proxy-only subnet** for backends to receive proxy traffic; firewalls typically must permit both health check source ranges and the corresponding proxy-only subnet. Never copy a global load balancer's firewall setup verbatim onto a regional load balancer.

### 6.1. A Common Cause of Unhealthy Status

A VM has an app listening on `127.0.0.1:8080`, while the health checker connects to the VM's internal NIC IP. Because the app only binds to loopback, probes cannot reach it. Bind the app to the right interface IP—such as `0.0.0.0:8080` if appropriate for the design—while restricting sources with firewalls.

Other common causes include wrong ports, non-existent URL paths, HTTP redirect/HTTPS mismatches, overly short timeouts, backends still booting, empty instance groups, or firewall rules targeting the wrong network tag.

## 7. Practical Configuration Mapping Steps

When designing application ingress, use this table to avoid mixing up responsibilities:

| Question | Component to Decide |
| --- | --- |
| At which IP and port does the website receive traffic? | Forwarding rule / frontend |
| Using HTTPS—where does the certificate live? | Target HTTPS proxy + TLS certificate |
| Where do `/api/*` and `/*` go? | URL map |
| Send to which MIG or NEG, using what protocol/port? | Backend service + backend attachment |
| Is the backend healthy enough to receive requests? | Health check, **if supported by backend type** |
| Which users are allowed to call private APIs? | IAM / app / authentication, not just the LB |
| Mitigate malicious requests, application DDoS? | Cloud Armor/WAF on supported configurations |
| Cache static objects near users? | Cloud CDN / backend bucket or supported backend service |
| Observe 5xx, latency, and request distribution? | Cloud Monitoring/Logging + app metrics |
| Reduce cost and scale appropriately? | LB pricing, backend autoscaling, CDN/caching, budgets |

### 7.1. Deciding Global vs. Regional

Not every Application Load Balancer has the same scope:

- **Global external Application Load Balancer**: global public frontend (per supported mode) using Google's global infrastructure; suited for websites serving multiple regions.
- **Regional external Application Load Balancer**: regional frontend/Envoy proxy with a **proxy-only subnet** and backends/routing within the region's supported scope.
- **Internal Application Load Balancer**: frontend using an internal address for internal traffic or connected networks per supported architecture.
- **Network Load Balancer**: serves TCP/UDP or proxy networking with different semantics; never force the HTTP path-routing URL map model onto a passthrough network LB.

Choose the LB type based on **client sources, backend scope, protocol, routing features, security requirements, availability, and cost**.

## 8. Hands-On gcloud: Global External Application Load Balancer with VM Backend

This lab illustrates frontend → URL map → backend service → health check. Assume you already have:

- Project `PROJECT_ID` with Compute Engine API enabled, appropriate billing, and required network/compute IAM admin permissions.
- A **managed instance group** named `web-mig` in zone `asia-southeast1-b` inside VPC `commerce-vpc`.
- VMs in the group serving HTTP on port `8080` and returning `200 OK` at `/healthz`.
- VMs carrying network tag `lb-backend` (or adjust firewall targets to match your actual service accounts/tags).
- Active backends in the group, matching the network and deployment scope.

**Commands creating LBs, reserving IPs, and running VMs can incur costs.** Run only in an authorized lab project. Example names do not automatically create the MIG/VPC/VMs: if they do not exist yet, create them following Compute Engine labs first.

### Step 1: Inspect Configuration and Set Named Port on the Instance Group

~~~bash
gcloud auth list
gcloud config set project PROJECT_ID

gcloud compute instance-groups managed describe web-mig \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID

# Map named port http → 8080 for VMs in the MIG
gcloud compute instance-groups managed set-named-ports web-mig \
  --zone=asia-southeast1-b \
  --named-ports=http:8080 \
  --project=PROJECT_ID
~~~

The named port is used when the proxy backend service connects to the instance group. It does not replace having the application actually listen on port 8080.

### Step 2: Create an HTTP Health Check

~~~bash
gcloud compute health-checks create http shop-hc \
  --port=8080 \
  --request-path=/healthz \
  --check-interval=10s \
  --timeout=5s \
  --healthy-threshold=2 \
  --unhealthy-threshold=2 \
  --project=PROJECT_ID
~~~

Meaning: probe HTTP port 8080, path `/healthz`. Two consecutive successful or failed probes (per health checker evaluation) transition health state. These are illustrative values and should not be used blindly in every production environment.

### Step 3: Allow Health Checker/Proxy Sources to Backend VMs

~~~bash
gcloud compute firewall-rules create allow-shop-lb-backend \
  --network=commerce-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=lb-backend \
  --project=PROJECT_ID
~~~

This is an **illustrative configuration for a global external Application Load Balancer with VM backends**, and must be reviewed against the exact LB type and any active hierarchical/network firewall policies. Never allow overly broad sources and never modify production security policies just to pass a lab.

### Step 4: Create the Backend Service and Attach the Instance Group

~~~bash
gcloud compute backend-services create shop-web-backend \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP \
  --port-name=http \
  --health-checks=shop-hc \
  --project=PROJECT_ID

gcloud compute backend-services add-backend shop-web-backend \
  --global \
  --instance-group=web-mig \
  --instance-group-zone=asia-southeast1-b \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.8 \
  --project=PROJECT_ID
~~~

The backend service references the health check, uses HTTP protocol, and uses named port `http`. The `add-backend` command attaches the MIG in the specified zone. The balancing mode and utilization flags in this example apply to supported instance groups; **do not pass these flags for a serverless NEG**.

### Step 5: Create the URL Map

~~~bash
gcloud compute url-maps create shop-url-map \
  --default-service=shop-web-backend \
  --global \
  --project=PROJECT_ID
~~~

The URL map has default service `shop-web-backend`. In real architectures, you can add host/path matchers to route `/api/*` to a separate API backend service. This lab uses one default backend to make verifying the request path straightforward.

### Step 6: Create the HTTP Target Proxy and Frontend

To keep the lab simple, the initial step uses **HTTP port 80**. Production deployments should use HTTPS with valid certificates and either configure redirects or omit plain HTTP depending on policy.

~~~bash
# Reserve a global IPv4 address for the frontend
gcloud compute addresses create shop-lb-ip \
  --global \
  --ip-version=IPV4 \
  --network-tier=PREMIUM \
  --project=PROJECT_ID

# Create HTTP target proxy referencing the URL map
gcloud compute target-http-proxies create shop-http-proxy \
  --url-map=shop-url-map \
  --global \
  --project=PROJECT_ID

# Forwarding rule listening on HTTP 80
gcloud compute forwarding-rules create shop-http-rule \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address=shop-lb-ip \
  --target-http-proxy=shop-http-proxy \
  --ports=80 \
  --project=PROJECT_ID
~~~

**These commands create billable resources**; run only in an authorized lab. Never use plain HTTP as a public frontend for sensitive data or production credentials.

### Step 7: Inspect Each Component

~~~bash
# Frontend / public IP
gcloud compute addresses describe shop-lb-ip \
  --global --project=PROJECT_ID

gcloud compute forwarding-rules describe shop-http-rule \
  --global --project=PROJECT_ID

# URL map, backend service, and health check
gcloud compute target-http-proxies describe shop-http-proxy \
  --global --project=PROJECT_ID

gcloud compute url-maps describe shop-url-map \
  --global --project=PROJECT_ID

gcloud compute backend-services describe shop-web-backend \
  --global --project=PROJECT_ID

gcloud compute backend-services get-health shop-web-backend \
  --global --project=PROJECT_ID

gcloud compute health-checks describe shop-hc \
  --global --project=PROJECT_ID
~~~

`get-health` shows backend health status from the backend service's perspective. Results may take some time to populate right after creation or configuration updates.

Once backends are healthy, retrieve the IP from `addresses describe` and test:

~~~bash
curl -i http://LOAD_BALANCER_IP/
~~~

Use the **actual IP address** in place of `LOAD_BALANCER_IP`. If the application checks the `Host` header, pass the expected hostname per configuration. An HTTP response from the load balancer confirms the frontend path works, though routing and backend behavior still need verification.

### Step 8: Transitioning to HTTPS for Production

Once you have a domain name and valid TLS certificates:

1. Provision a Google-managed certificate or an appropriate Certificate Manager / Compute SSL certificate option.
2. Create a **target HTTPS proxy** pointing to the URL map and referencing the certificate.
3. Create a **port 443 forwarding rule** pointing to the HTTPS proxy, optionally sharing the same IP if IP/port/protocol rules permit.
4. Point the hostname's DNS record to the frontend IP; complete certificate validation/activation.
5. If HTTP → HTTPS redirect is needed, configure a separate **HTTP redirect URL map** and attach it via a port 80 target HTTP proxy.
6. Test TLS handshake, hostname, redirects, routing, and backend health after release.

**Frontend HTTPS differs from backend protocol.** If end-to-end TLS is required, explicitly choose HTTPS/HTTP2 for the backend where supported and configure appropriate certificates/connections.

## 9. Health Checks with GKE: Controllers Can Manage Them for You

In GKE, Ingress/Gateway controllers can create or reconcile backend services, health checks, URL maps, and load balancing resources from Kubernetes manifests. For instance, an `Ingress` pointing to a Kubernetes `Service` can generate the corresponding Google Cloud components.

Specifically when using container-native load balancing, GKE can use a **zonal NEG** with **Pod IP:port** endpoints instead of node instance groups.

~~~mermaid
flowchart LR
    IN["GKE Ingress / Gateway"]
    LB["Application Load Balancer"]
    BS["Backend service"]
    NEG["Zonal NEG: Pod IP:port"]
    P1["Pod 1"]
    P2["Pod 2"]
    HC["Health check"]
    IN -. "Controller manages" .-> LB
    LB --> BS --> NEG
    NEG --> P1
    NEG --> P2
    HC -. "Probes" .-> NEG
~~~

### 9.1. Distinguishing Three Health Layers

| Component | Example | Decision |
| --- | --- | --- |
| **Kubernetes readiness probe** | Pod initialized and ready to serve | Should the Pod be included in the Kubernetes Service endpoints? |
| **Kubernetes liveness probe** | Process wedged and needs restart? | Should kubelet restart the container? |
| **Google Cloud LB health check** | Backend endpoint answers LB probe? | Should the LB send traffic to that backend? |

They are related but **not identical**. Setting a liveness probe too aggressively can trigger restart loops; setting an LB health check too aggressively can drain traffic from the entire group while pods are starting up.

Configuring health checks in GKE may involve `BackendConfig`, `HealthCheckPolicy`, or controller behavior depending on the Ingress/Gateway type and version/features. When GKE manages LB resources, edit the **source Kubernetes configuration** rather than hand-editing the health check in the Google Cloud Console.

## 10. Health Checks with Cloud Run: An Exception to Remember

An Application Load Balancer can route to Cloud Run through a **serverless NEG**. However, a backend service with a serverless NEG **must not have a health check configured**.

~~~mermaid
flowchart LR
    C["HTTPS Client"]
    F["Frontend + TLS + URL map"]
    B["Backend service"]
    S["Serverless NEG"]
    R["Cloud Run service"]
    C --> F --> B --> S --> R
~~~

Key checks:

- The Cloud Run service is deployed in the right region and handling requests properly.
- The NEG links to the right Cloud Run service; the backend service uses only options supported by serverless NEGs.
- Cloud Run ingress settings and authentication align with the frontend load balancer model.
- Inspect error metrics, latency, Cloud Run request logs, runtime startup/liveness probes, and Cloud Load Balancing request logs.
- When error rates climb, consider features such as outlier detection if supported by the LB/NEG type; **never add a VM HTTP health check**.

When the backend is Cloud Run, never assume "missing health check resource" means a misconfiguration: it is a design characteristic of **serverless NEG backends**.

## 11. Health Checks, Balancing Modes, and Load Capacity

A backend marked **healthy** only indicates it satisfies probe criteria. Backends can still become overloaded under heavy traffic, which is why **backend services** include distribution and capacity controls.

Factors to coordinate:

- **Balancing mode:** e.g., utilization, rate, or connection depending on backend/LB type.
- **Capacity scaler:** caps the fraction of backend capacity used when supported by the backend type.
- **Autoscaling:** MIG/GKE/Cloud Run independently scale instances/pods based on their own metrics and policies.
- **Connection draining:** helps minimize disruption when removing backends or scaling down.
- **Timeout:** neither too short for legitimate requests nor too long so as to mask failures.
- **Session affinity:** enable only when justified; does not automatically turn a stateful service into a highly available system.

~~~mermaid
flowchart TD
    A["Backend healthy per health check"] --> B{"Still has capacity for requests?"}
    B -->|Yes| C["Receive traffic per balancing policy"]
    B -->|No| D["Need more capacity, traffic limiting, or overload handling"]
    C --> E["Latency, 5xx, and saturation metrics"]
    D --> E
    E --> F["Tune autoscaling, policies, or architecture"]
~~~

**Do not substitute an autoscaler for health checks.** A large VM group can still be completely unhealthy if ports/firewalls are wrong; conversely, a healthy group can still suffer terrible latency under overload.

## 12. Common Troubleshooting Scenarios

| Symptom | Possible Cause | Priority Check |
| --- | --- | --- |
| Domain unreachable | DNS not pointing to frontend IP, propagation, or certificate issue | DNS records, forwarding rule, IP address, TLS certificate |
| Frontend accepts TCP but HTTPS fails | Cert inactive/hostname mismatch, wrong target proxy | TLS handshake, certificate, proxy's URL map |
| Requests to `/api/*` hit web backend | Missing/misconfigured host/path matcher in URL map | URL map, route precedence, and default backend |
| Backend service reports unhealthy | `/healthz` returns non-200, wrong port, timeout, firewall | `get-health`, app logs, probe path, tags |
| VM `curl localhost` works, LB fails | App binds loopback only, firewall blocks probes | Listener `0.0.0.0`, NIC IP, LB source firewall |
| `502` or `503` | Backend unavailable, connection reset, timeout, protocol mismatch, etc. | LB request logs, status details, health, backend logs |
| Created backend service but receives no requests | Backend not attached or not wired to URL map/proxy/forwarding rule | Verify every link in the chain |
| No health check appears for Cloud Run | Using serverless NEG, which does not support health checks | Check serverless NEG and metrics/runtime logs |
| GKE pod healthy but LB unhealthy | Mismatch between readiness, LB check, NEG port/firewall | Ingress/Gateway controller, NEG endpoints, backend health |
| Only regional LB fails to reach backend | Missing proxy-only subnet or corresponding ingress firewall | Regional Envoy source ranges and routes/firewalls |
| Errors right after deploying new version | Instances not ready, health check too eager, or shutdown too abrupt | Startup/readiness, rolling updates, draining |
| Traffic rises but throughput plateaus | Capacity/scaling policy, backend saturation, quotas | CPU/latency/rate metrics, autoscaling, backend service config |

### 12.1. Request-Path Troubleshooting Workflow

~~~mermaid
flowchart TD
    A["Client sees error"] --> B{"DNS returns right frontend IP?"}
    B -->|No| C["Fix DNS / IP record"]
    B -->|Yes| D{"Forwarding rule and target proxy valid?"}
    D -->|No| E["Check listener, TLS, target proxy"]
    D -->|Yes| F{"URL map points to right backend?"}
    F -->|No| G["Check host/path/default routing"]
    F -->|Yes| H{"Is backend type serverless NEG?"}
    H -->|Yes| I["Check Cloud Run ingress, logs, latency, NEG"]
    H -->|No| J{"Is LB backend healthy?"}
    J -->|No| K["Check port, path, firewall, and health checker"]
    J -->|Yes| L["Check capacity, timeouts, 5xx, and application"]
~~~

**Note:** Some HTTP statuses are returned by the application itself; some errors are generated by the load balancer. For 502/503 errors, distinguish them via logging/status details rather than guessing from the status code alone.

### 12.2. When Should You Inspect Firewalls?

If the backend is a Compute Engine instance group or GKE zonal NEG, probes and proxy traffic must reach the application port. Check:

1. Backend VPC and subnet.
2. Target network tags or service account on the firewall rule.
3. Exact source ranges for the LB type.
4. Exact protocol and backend port.
5. Organization/folder/network-level firewall policies if present.
6. Process actually listening on the required IP/port.

For **serverless NEGs**, similar VM health check firewall rules do not apply. For **regional Envoy-based LBs**, traffic from the proxy-only subnet must be permitted to the corresponding backends.

## 13. Logging, Monitoring, and SLOs

A well-operated load balancer requires visibility on both frontend and backend. Signals to track:

| Signal | Question |
| --- | --- |
| **Request count / rate** | Which hostname/path is experiencing a traffic spike? |
| **Response code class 2xx/4xx/5xx** | Are errors coming from clients, the proxy, or backends? |
| **Backend latency** | Is processing time at the backend increasing? |
| **Total latency** | How is end-user experience affected? |
| **Backend health** | How many VM/NEG endpoints are healthy? |
| **Timeouts/connection errors** | Are connections to backends resetting or stalling? |
| **Backend capacity** | Are there enough instances/pods to absorb traffic? |
| **TLS failures/certificate status** | Is the HTTPS frontend validly configured? |
| **Cloud Armor events** | Is traffic being blocked by security policies? |
| **Cloud CDN cache metrics** | Are hit/miss ratios and static content latency reasonable? |

Cloud Logging captures request logs per the load balancer's configuration capabilities. Health checks and backend metrics come from separate telemetry sources; not every detail appears in a single log record.

An example SLO for a web API: **99.9% successful requests** over a measurement window based on a precise definition of success and exclusions. To measure accurately, clearly define the denominator, which status codes count as errors, and where telemetry is sourced. An SLO is different from "all backends healthy": backends can pass health checks yet still return business logic errors.

### 13.1. Reading Error Reports Methodically

When encountering `502`/`503`:

1. Record the timestamp, hostname, path, and request ID/trace ID if available.
2. Verify the frontend certificate, URL map, and target backend service.
3. Read `get-health` (if health checks are supported) and healthy-status metrics.
4. Correlate load balancer request logs with VM/GKE/Cloud Run logs.
5. Check firewalls, protocols, ports, timeouts, connection draining, and capacity.
6. Identify the root cause and roll back or scale as needed; re-verify the SLO.

Never write access tokens, private keys, or customer data into diagnostic logs.

## 14. Security and IAM Around Components

A load balancer handles receiving, routing, and distributing traffic; it does not automatically supply every security layer. Proper design includes:

- **HTTPS and TLS certificates** for client-facing frontends.
- **Cloud Armor** when supported by the LB and backend to mitigate certain classes of malicious traffic.
- **Firewalls** restricting paths from health checkers/proxies to VMs/NEGs.
- **IAM** restricting who can create forwarding rules, edit URL maps, attach backend services, alter health checks, or manage certificates.
- **Application authentication/authorization** for APIs requiring user/service identity.
- **Secret Manager/runtime identity** for backend apps, never embedding service account keys in frontend configs.
- **Cloud Audit Logs** to track infrastructure configuration changes within supported scope.

### 14.1. Changing a URL Map Is Also a Security Change

If someone changes `/admin/*` to another public backend or alters a host rule, traffic can be routed to the wrong service. Permissions to update URL maps, target proxies, certificates, backend services, and forwarding rules must be governed as production infrastructure changes.

### 14.2. A Load Balancer Does Not Automatically Make Private Backends "Safe"

A backend VM might still have an external IP or an overly broad ingress firewall. Clients could then reach it directly, **bypassing** the load balancer and Cloud Armor. Consider removing unnecessary external IPs, tightening firewalls, and verifying direct access paths per architecture.

For Cloud Run, inspect ingress settings and mechanisms preventing direct access to the `run.app` URL if traffic is required to traverse the load balancer. Configurations must align with Cloud Run and load balancer capabilities; never assume adding a serverless NEG automatically blocks all other entry paths.

## 15. Deployment Scenario: Web on MIG, API on Cloud Run, Assets on Cloud Storage

Atlas Corp operates a system:

- `shop.example.com` serves the web frontend from a managed instance group.
- `shop.example.com/api/*` runs on Cloud Run.
- `static.example.com/*` serves images and JavaScript files from Cloud Storage.

Design layout:

~~~mermaid
flowchart TD
    CLIENT["Internet client"] --> FE["HTTPS frontend<br/>IP + certificate + target proxy"]
    FE --> UM["URL map"]
    UM -->|shop.example.com /*| WEB["Backend service web"]
    WEB --> MIG["MIG Web VMs"]
    H["Health check /healthz"] -.-> MIG
    UM -->|shop.example.com /api/*| API["Backend service api"]
    API --> NEG["Serverless NEG → Cloud Run"]
    UM -->|static.example.com| BUCKET["Backend bucket → Cloud Storage"]
    CDN["Cloud CDN (if configured)"] -. "Supported caching" .-> BUCKET
~~~

**Three targets with three different health mechanisms:**

1. **Web MIG:** backend service has an HTTP health check; only VMs meeting criteria receive traffic.
2. **Cloud Run:** backend service attaches a serverless NEG, **has no health check**; relies on Cloud Run metrics and application monitoring.
3. **Cloud Storage backend bucket:** static content delivery path via backend bucket, **no VM HTTP health check attached**.

For static content, **Cloud CDN** can be enabled per supported configuration to cache near users, reduce backend requests, or improve latency. However, Cloud CDN does not solve private-content caching automatically: cache keys, `Cache-Control`, invalidation, and data security must be designed to match requirements.

### 15.1. Ensuring Zero-Downtime Releases

When rolling out a new web version:

1. Provision/start new instances in the MIG and wait for the app to become ready.
2. Let health checks confirm backends are healthy before receiving traffic.
3. Distribute requests through the backend service per policy.
4. Remove old instances with appropriate connection draining/rolling updates.
5. Monitor errors/latency before and after rollout; roll back if thresholds are exceeded.

For Cloud Run, revision/traffic splitting occurs through Cloud Run mechanisms, optionally combined with LB-side routing where appropriate. Never copy VM health check thresholds directly onto a serverless NEG.

## 16. Cost and Choosing the Right Configuration

An Application Load Balancer can incur costs from forwarding rules, data processing, egress, and related backend components per actual pricing. Adding Cloud CDN, Cloud Armor, Cloud Logging, instance groups/VMs, or backend services also adds their respective charges.

| Decision | Cost / Effort Impact |
| --- | --- |
| Global vs. regional load balancer | Different scopes, proxy infrastructure, and supported pricing models |
| Multiple frontends / forwarding rules | Increases configuration count and associated charges |
| Backend VMs and MIG autoscaling | VM/CPU/RAM/disk/network billed by usage |
| Cloud Run backend | Serverless service billed per Cloud Run pricing and related settings |
| CDN | Adds cache/egress fees but can reduce requests hitting backends |
| Overly verbose logging | Increases log volume and storage/query costs |
| Overly frequent health checks | Increases probe traffic and backend load; pick sensible intervals |

There is no single flat price formula for every load balancer. Consult **Cloud Load Balancing pricing**, backend pricing pages, the Google Cloud Pricing Calculator, and set **Cloud Billing budgets** for lab projects. Budgets alert—they do not shut down a load balancer automatically.

### 16.1. What Needs Cleanup When Finishing the Lab?

If the lab created the resources in Section 8, inspect and clean up in dependency order:

1. Verify the exact lab project, URL map, proxy, forwarding rule, backend service, and MIG.
2. Detach/delete the lab forwarding rule and target proxy/URL map once no consumers remain.
3. Remove backend attachments and delete the lab backend service/health check after confirming they are not shared.
4. Delete the MIG/VMs or test sources if authorized; check for lingering disks, images, and IPs.
5. Release any separately reserved public IP addresses no longer needed.
6. Re-check billing after reporting delays.

**Never delete a backend service or health check shared by a production load balancer.** This cleanup list is an inventory guide, not an automated script.

## 17. Self-Check Exercises

**Q1.** A user calls `https://shop.example.com/api/orders`. Which component decides to route `/api/*` to the API backend: the forwarding rule or the URL map?

*Hint:* **URL map**. The forwarding rule defines the IP/port and target proxy for incoming connections.

**Q2.** The frontend serves HTTPS on port 443, while VMs run HTTP on port 8080. Is this valid?

*Hint:* It can be valid. The target HTTPS proxy terminates the client connection; the backend service/proxy opens connections to backends using the configured protocol/port. For TLS to backends, configure the corresponding backend protocol.

**Q3.** Why does a VM return `200` to `curl http://127.0.0.1:8080/healthz`, yet the backend service still reports unhealthy?

*Hint:* The app might only bind loopback, firewalls might block probe sources, named port might mismatch, path/timeout might differ, or the instance group might not be attached properly.

**Q4.** A backend service points to Cloud Run via a serverless NEG. Should you create an HTTP health check and attach it to that backend service?

*Hint:* No. Google Cloud does not support health checks for serverless NEG backends.

**Q5.** When all VMs in the API backend are unhealthy, does the URL map automatically send `/api/*` to the web backend?

*Hint:* Not by default. The URL map selects backend services by routing rules; fallback/failover must be configured using explicitly supported features.

**Q6.** For a global external Application Load Balancer with VM backends, you open ingress `0.0.0.0/0` to the backend port so health checks pass. Is this appropriate?

*Hint:* No. Identify the exact health checker/GFE source ranges from documentation and restrict firewalls to the required port/backends.

**Q7.** A GKE team uses an Ingress controller that creates a Google Cloud health check. After editing it directly in the Console, the configuration reverts. Why?

*Hint:* The controller reconciles resources it manages. Edit the Kubernetes/GKE source configuration via the appropriate Ingress/Gateway mechanism.

**Q8.** A Cloud Run service has high request errors, and there is no health check resource in its backend service. Is the load balancer missing a component?

*Hint:* No, if the backend is a serverless NEG. Inspect Cloud Run ingress, request logs, revisions, latency, and metrics alongside LB configuration.

**Q9.** A forwarding rule listens on port 80, the target HTTP proxy references a URL map, and the URL map has a default service. Why do requests still fail?

*Hint:* Missing backend group, wrong named port, unhealthy health checks, firewall block, protocol mismatch, timeout, or app not running. Check the entire chain.

**Q10.** When choosing global vs. regional load balancing, what extra requirement must be checked for a regional external Application Load Balancer?

*Hint:* Regional Envoy proxies typically require a proxy-only subnet and firewall rules allowing traffic from the proxy-only subnet to backends, in addition to health check sources and regional constraints.

## 18. Key Takeaways Checklist

- [ ] Identify the exact load balancer type: global/regional, external/internal, Application/Network.
- [ ] Frontend has matching IP/port/protocol/forwarding rule.
- [ ] Target proxy references the right URL map and valid TLS certificate if using HTTPS.
- [ ] URL map has an intended default backend and expected host/path rules.
- [ ] Backend service uses the right protocol, backend group, and ports; named ports match the instance group.
- [ ] Health check uses the right protocol/path/port/thresholds if supported by the backend type.
- [ ] **Do not attach health checks to serverless NEGs.**
- [ ] Firewalls permit health checker/proxy sources on the right port; regional LBs have a proxy-only subnet when required.
- [ ] Monitor health, 5xx, latency, and capacity; distinguish app readiness from LB health checks.
- [ ] Review HTTPS, IAM, Cloud Armor, Cloud CDN, and direct backend exposure.
- [ ] Have a budget, owner, rollback plan, and cleanup plan for test environments.

**Three crucial questions when deploying a new application:** *Which frontend do clients connect to? Which backend service does the URL map select? How is that backend verified to be healthy and sufficiently provisioned?* Answering these three questions clearly makes Compute Engine/GKE/Cloud Run deployments far more reliable and surfaces failures earlier.

## Official References

- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Forwarding rules overview](https://cloud.google.com/load-balancing/docs/forwarding-rule-concepts)
- [Target proxies overview](https://cloud.google.com/load-balancing/docs/target-proxies)
- [URL maps overview](https://cloud.google.com/load-balancing/docs/url-map-concepts)
- [Backend services overview](https://cloud.google.com/load-balancing/docs/backend-service)
- [Health checks overview](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Firewall rules for load balancing](https://cloud.google.com/load-balancing/docs/firewall-rules)
- [Serverless NEGs](https://cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
- [Global external Application Load Balancer with VM instance groups](https://cloud.google.com/load-balancing/docs/https/setup-global-ext-https-compute)
- [Cloud Load Balancing pricing](https://cloud.google.com/load-balancing/pricing)
