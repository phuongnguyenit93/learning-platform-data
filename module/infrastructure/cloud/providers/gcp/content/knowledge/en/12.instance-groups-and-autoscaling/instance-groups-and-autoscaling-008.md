# Combining Managed Instance Groups with Cloud Load Balancing

A retail website runs its HTTP backend on **Compute Engine**. During off-peak hours, two VMs are enough; during promotional campaigns, request rates jump severalfold, a VM can become overloaded, or a zone can experience an outage. Manually spinning up additional VMs forces operators to track instance IPs, monitor health, balance traffic, and tear down machines once demand drops.

**Managed Instance Groups (MIGs)** and **Cloud Load Balancing** solve two complementary halves of this problem: the MIG **maintains and scales a templated fleet of VMs**, while the load balancer **receives traffic and routes it to eligible backends**. Paired properly, the system can scale with demand, replace failed machines, perform rolling updates, and span multiple zones. However, never treat these two services as an "automatic zero-downtime guarantee": the application still needs accurate health endpoints, durable externalized state, safe rollout practices, proper networking/IAM, and user-facing quality monitoring.

This lesson belongs to the **Instance Groups and Autoscaling** chapter of the **CLOUD_PROVIDERS_GCP** module. This architecture connects directly to project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, Cloud Storage, and Cloud SQL. Through deployment scenarios, learners select load balancers, secure backends, automate releases, manage reliability, and evaluate cost trade-offs.

## 1. Objectives and architecture map

After this lesson, you can:

1. Distinguish the responsibilities of **instance templates**, **MIGs**, **autoscalers**, **backend services**, **health checks**, and **load balancer frontends**.
2. Choose between a **zonal MIG** and a **regional MIG**, while understanding how they differ from cross-region load balancing.
3. Configure **named ports**, attach a MIG as a backend for an Application Load Balancer, and configure health checks.
4. Explain the relationship between **CPU autoscaling**, **load balancing serving capacity**, and min/max replica bounds.
5. Design secure backend access using VPC firewalls, TLS, service accounts, and related policies.
6. Coordinate version updates, connection draining, autohealing, and troubleshooting without conflating architectural layers.

### 1.1. Request flow from client to VM

~~~mermaid
flowchart TB
    U["Client / browser"] --> FE["Frontend: IP, HTTPS, forwarding rule"]
    FE --> PROXY["Target HTTPS proxy"]
    PROXY --> MAP["URL map: host/path routing"]
    MAP --> BS["Backend service: retail-web-backend"]
    BS --> HC["Health check"]
    BS --> MIG["Managed Instance Group"]
    MIG --> VM1["VM A: web :8080"]
    MIG --> VM2["VM B: web :8080"]
    MIG --> VM3["VM C: web :8080"]
    TEMPLATE["Instance template"] -. "Provisions uniform VMs" .-> MIG
    AUTO["Autoscaler"] -. "Adjusts VM count" .-> MIG
    HC -. "Probes backend" .-> VM1
    HC -.-> VM2
    HC -.-> VM3
~~~

The diagram shows the logical architecture of an **Application Load Balancer**; Network Load Balancer variants use a different data plane and component set. Notably, the backend service uses its health check to determine which instances are eligible to receive traffic. **MIG autohealing** may use a separate health check to decide when to replace a VM, so never assume every health-check failure deletes a machine.

### 1.2. Who is responsible for what?

| Component | Responsibility | What it does NOT do automatically |
| --- | --- | --- |
| **Instance template** | Declares machine type, image, disks, network, metadata, and service account for new VMs. | Does not launch VMs without a MIG or instance-creation call. |
| **MIG** | Manages VM count and configuration from a template; updates/repairs instances per policy. | Does not provide public IP addresses, TLS, or URL routing. |
| **Autoscaler** | Computes target VM count from load signals and configured bounds. | Does not make an app stateless or grant instant capacity. |
| **Backend service** | Attaches instance groups/NEGs and configures traffic policies, health checks, and serving capacity. | Does not replace instance templates or fix code on VMs. |
| **Health check** | Probes backend readiness by protocol, port, and path. | Does not validate every business flow or database query. |
| **Load balancer frontend** | Accepts traffic on an IP and port; for Application LBs, coordinates proxies, TLS, and URL maps. | Does not grant IAM or database privileges to the application. |
| **VPC firewall** | Controls which packets may reach backend instances. | Does not alter routing or endpoint health. |

This pattern uses a **MIG as an instance-group backend**. This differs from **zonal network endpoint groups (NEGs)** targeting IP:port pairs; do not mix both backend models without clarifying ownership and compatibility.

## 2. Managed Instance Group fundamentals

### 2.1. Instance templates as the source for new VMs

A MIG provisions VMs from an **instance template**: machine type, boot image, disks, labels, network interfaces, service account, startup script, and declared attributes. When shipping a new version, create a **new template** and update the MIG rather than SSHing into individual VMs.

A VM inside a MIG should be designed to be **replaceable**. If you patch code directly on a VM without updating the template/image, VM replacement or scale-out will lose those changes. Likewise, user files or sessions stored solely on local boot disks are not durable shared state across the fleet.

Backend apps can persist critical data in **Cloud SQL**, objects in **Cloud Storage**, secrets in **Secret Manager**, and metrics/logs in their respective managed services. The runtime service account should hold only the minimum permissions needed on each resource.

### 2.2. Zonal MIG vs. regional MIG

| Criterion | Zonal MIG | Regional MIG |
| --- | --- | --- |
| Scope | One zone. | One region, distributing VMs across selected zones. |
| Availability | Cannot survive a full-zone outage on its own. | Keeps backends running in other zones if capacity and policies allow. |
| Setup | Simpler for labs or restartable workloads. | Requires choosing distribution zones, capacity headroom, and multi-zone behavior. |
| Autoscaling | Adjusts total VM count in the group. | Adjusts total VM count and distributes across zones per group policy. |
| Best suited for | Dev/test, batch jobs, or workloads accepting zone disruption. | Production backends reducing single-zone failure risk. |

**A regional MIG does not span multiple regions.** To survive a full region outage, deploy separate regional MIGs across multiple regions and use a load balancer capable of multi-region routing, alongside multi-region data design and failover policies.

### 2.3. MIG VM lifecycle management

Common lifecycle actions:

- **Scale out:** provisions additional VMs from the template to meet target size.
- **Scale in:** removes instances as demand falls, governed by autoscaler rules and scale-in protection/controls.
- **Autohealing:** probes VM health and recreates unhealthy VMs when enabled.
- **Rolling update:** transitions batches of VMs to a new template/version within availability and surge limits.
- **Recreate/repair:** replaces failed VMs or instances drifting from desired state.

MIGs **cannot recover data stored solely in VM RAM** or keep open connections alive across VM replacement. Backends must implement graceful shutdown, timeouts, retries, and external state persistence.

### 2.4. Named ports: the bridge between instance group and backend service

Suppose every VM in the MIG runs a web server on TCP port `8080`. At the group level, configure:

~~~text
Managed instance group: retail-web-mig
Named port:             http:8080

Backend service:
  protocol: HTTP
  portName: http
~~~

For proxy/Application LB backend services using named ports, the name `http` tells the backend service which **serving port** to target on each VM. If the group declares `http:8080` while the web server listens on `9090`, traffic or health checks will fail depending on config.

**A named port is not a firewall rule, does not start a service, and does not open a port to the Internet.** It is simply a name-to-port mapping used by supported load balancer types. For passthrough Network Load Balancers, port and backend targeting work differently.

## 3. Choosing the right Cloud Load Balancing option for a MIG

### 3.1. Application Load Balancer or Network Load Balancer?

Google Cloud offers multiple load balancers. When serving HTTP/HTTPS web apps with custom domains, TLS certificates, and host/path routing, an **Application Load Balancer** is the standard choice. When balancing raw TCP/UDP transport traffic or preserving packet headers, evaluate the corresponding **Network Load Balancer** options.

| Requirement | Option to evaluate | Architectural notes |
| --- | --- | --- |
| Public HTTPS website with host/path routing | Global external Application Load Balancer. | Frontend/proxy/URL map, backend service, and health checks. |
| Internal-only HTTP(S) services | Internal Application Load Balancer. | VPC, regional/cross-regional scope, proxy-only subnet per type, and network permissions. |
| Public HTTP(S) restricted to a single region | Regional external Application Load Balancer. | Uses regional resources and a required proxy-only subnet. |
| Raw TCP without URL routing | Suitable proxy or passthrough Network Load Balancer. | Protocols, frontends, and instance-group/NEG backend modes differ. |
| Multiple regions behind one public hostname | Supported global external LB with multi-region backends. | Each region needs matching capacity, data consistency, and SLOs. |

**Not all load balancer types support the same health checks, scopes, SSL termination, autoscaling signals, session affinity, or distribution algorithms.** For the example commands below, we standardize on a **global external Application Load Balancer** with a MIG backend to avoid mixing incompatible flags.

### 3.2. One MIG serving multiple purposes

A MIG provides VMs to backend services. An architecture can point multiple backend services or load balancers at one group where supported, but assess:

- Which ports actually accept traffic? Do named ports align per backend?
- Do health checks verify the right app and scope?
- Which signal drives autoscaling, and how does combined traffic behave?
- Could one application overload VMs shared with another application?

When applications have distinct lifecycles, permissions, SLAs, or scaling profiles, **separate MIGs** simplify operations and prevent capacity contention.

### 3.3. Backend service vs. instance group

A backend service can attach eligible instance groups across zones or regions supported by that load balancer. **The backend service governs traffic distribution and health evaluation**, while each MIG manages its own VMs.

A global external Application Load Balancer can route to backends in multiple regions; that does not turn a regional MIG into a multi-region group. Keeping boundaries clear makes redundancy models easier to test.

## 4. Preparing backends before attaching a load balancer

### 4.1. Application pattern and health endpoints

Suppose the web app listens on all interfaces (`0.0.0.0`) on port `8080`, exposing two endpoints:

~~~text
GET /healthz  -> HTTP 200 when instance is ready for traffic
GET /livez    -> HTTP 200 when core process/VM remains alive
~~~

**Readiness** (`/healthz`) typically serves the load balancer backend service: if an instance has not connected to essential dependencies, withhold new requests. **Liveness** (`/livez`) should be less sensitive so MIG autohealing does not destroy a VM over brief external dependency blips.

Example:

~~~text
VM booting:
  /livez   = 200 if core process is up
  /healthz = 503 while loading config/caches

VM serving normally:
  /livez   = 200
  /healthz = 200

VM unable to accept new traffic:
  /healthz = 503
  /livez   = may still return 200
~~~

Exact criteria depend on application architecture. Never let a health check run heavy operations, write to databases, or cause side effects; load balancer probe volume scales up with VM count.

### 4.2. Linux application bootstrap example

In a lab, a startup script can spin up a simple HTTP server. The snippet below is **strictly for learning**; production workloads should use tested golden images, proper service management, and CI/CD pipelines:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y python3
mkdir -p /opt/retail-web

cat >/opt/retail-web/server.py <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/livez"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            payload = f"Retail demo on {socket.gethostname()}\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
PY

cat >/etc/systemd/system/retail-web.service <<'UNIT'
[Unit]
Description=Retail web demo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/retail-web/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now retail-web.service
~~~

Without an appropriate egress path, `apt-get update` will fail. For VMs without external IPs, configure Private Google Access or Cloud NAT/approved egress for the required package sources; PGA alone does not grant access to arbitrary Internet repositories. For production, pre-bake dependencies into images so VMs boot fast with fewer external runtime dependencies.

### 4.3. Preparing VPC infrastructure and permissions

Before running VM creation commands:

1. Project and VPC/subnet exist in the target region/zone.
2. The deployer holds sufficient IAM roles in the proper scope to create templates, MIGs, health checks, backend services, URL maps, and firewalls.
3. A dedicated VM runtime service account has least-privilege access to Cloud SQL, Cloud Storage, or Secret Manager as needed.
4. Backends have valid egress paths to fetch packages/images and reach Google APIs; external IPs are not mandatory.
5. Firewall rules allow required health checker/proxy traffic to the app port.
6. Budgets, monitoring, lab cleanup plans, and quotas are verified.

Every resource-creation command can **incur charges**. Use an authorized sandbox project and double-check commands before executing.

## 5. Hands-on: creating a MIG and attaching a global external Application Load Balancer

This section uses **Bash** and placeholder names. `create`, `set-*`, `add-*`, and `update` commands are **write operations** on Google Cloud. Do not run them verbatim in production without checking permissions, naming conventions, network topology, and CLI version specifics.

### 5.1. Illustrative variables

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
ZONE="asia-southeast1-a"
NETWORK="retail-vpc"
SUBNET="web-subnet"
TEMPLATE="retail-web-v1"
MIG="retail-web-mig-a"
HC="retail-web-health"
BACKEND="retail-web-backend"
~~~

In real environments, manage these values in IaC/CI configuration and never hardcode secrets in startup metadata. Project, region, and subnet must align; with Shared VPC, many network/IAM operations target the **host project**.

### 5.2. Create the instance template

Assume you saved the script from Section 4.2 as `bootstrap.sh` on your admin machine. This is a **deployer-prepared file**, not automatically provided by the lesson.

~~~bash
gcloud compute instance-templates create "$TEMPLATE" \
  --project="$PROJECT_ID" \
  --machine-type=e2-medium \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --no-address \
  --tags=allow-retail-web \
  --metadata-from-file=startup-script=bootstrap.sh
~~~

This example picks Debian and omits external IPv4 addresses on backends. If the app accesses Cloud SQL or Cloud Storage, attach a **dedicated service account** with appropriate OAuth scopes rather than granting overly broad default service account permissions.

**An instance template is a blueprint for creating new VMs.** To change the script, image, or network config, create a new template (`retail-web-v2`) and roll it out to the MIG rather than expecting old templates to update running VMs.

### 5.3. Create a zonal MIG

~~~bash
gcloud compute instance-groups managed create "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --template="$TEMPLATE" \
  --base-instance-name=retail-web \
  --size=2

# Define the named port referenced by the backend service.
gcloud compute instance-groups managed set-named-ports "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --named-ports=http:8080

# View configuration and managed instances (read-only).
gcloud compute instance-groups managed describe "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

gcloud compute instance-groups managed list-instances "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"
~~~

A MIG with target size 2 does not prove **two VMs are Ready**. VMs may still be booting, hitting startup script errors, blocked by quotas, or waiting on capacity. Inspect instance logs and verify the app actually listens on port 8080.

### 5.4. Create the health check

~~~bash
# WRITE: health check for the global backend service.
gcloud compute health-checks create http "$HC" \
  --project="$PROJECT_ID" \
  --global \
  --port=8080 \
  --request-path=/healthz

# READ-ONLY: inspect configuration.
gcloud compute health-checks describe "$HC" \
  --project="$PROJECT_ID" \
  --global
~~~

The load balancer probes VM backends using this health check. Set the exact **protocol/path/port**, startup tolerance, and timeout/check interval. `/healthz` must not require user login, yet should never expose secrets or sensitive internal state.

### 5.5. Open firewall rules for health checks and backend traffic

For a **global external Application Load Balancer** using Google Front Ends (GFEs), Google Cloud documentation specifies the required source ranges for health checkers/backend traffic:

~~~text
35.191.0.0/16
130.211.0.0/22
~~~

An illustrative rule scoped by port and network tag:

~~~bash
gcloud compute firewall-rules create allow-retail-lb-to-web \
  --project="$PROJECT_ID" \
  --network="$NETWORK" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=allow-retail-web
~~~

**Do not copy those two ranges blindly for every load balancer.** For Envoy-based regional/cross-regional internal or external Application Load Balancers, the **proxy-only subnet** and matching health-checker ranges must be allowed. With Shared VPC, firewall policies live in the host VPC/network. Also check hierarchical firewall policies and guest OS firewalls.

Never open `0.0.0.0/0` to backend ports just to turn health checks green. In proxy-based models, backends usually need neither external IPs nor direct Internet exposure.

### 5.6. Create the backend service and attach the MIG

~~~bash
# WRITE: backend service for global external Application Load Balancer.
gcloud compute backend-services create "$BACKEND" \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP \
  --port-name=http \
  --health-checks="$HC"

# WRITE: attach the zonal MIG to the backend service.
gcloud compute backend-services add-backend "$BACKEND" \
  --project="$PROJECT_ID" \
  --global \
  --instance-group="$MIG" \
  --instance-group-zone="$ZONE" \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.80

# READ-ONLY: inspect backend service configuration.
gcloud compute backend-services describe "$BACKEND" \
  --project="$PROJECT_ID" \
  --global
~~~

Here, `--port-name=http` binds to named port `http:8080` on the MIG. `UTILIZATION` and `maxUtilization` guide how the load balancer models backend capacity; they **do not enable autoscaling automatically**. To autoscale, configure an autoscaler on the MIG separately.

If attaching a **regional MIG**, reference the backend with **region** scope and only on compatible backend services/load balancers. If using a regional backend service, do not pass `--global` as shown above.

### 5.7. Create an HTTP frontend for testing

These commands create an **unencrypted HTTP frontend** purely to demonstrate the flow. **Never use plain HTTP for login, sessions, or production customer data**; in real deployments, use an **HTTPS proxy with valid certificates**, a port-443 forwarding rule, and proper DNS.

~~~bash
gcloud compute url-maps create retail-web-map \
  --project="$PROJECT_ID" \
  --default-service="$BACKEND"

gcloud compute target-http-proxies create retail-web-http-proxy \
  --project="$PROJECT_ID" \
  --url-map=retail-web-map

gcloud compute forwarding-rules create retail-web-http-rule \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --target-http-proxy=retail-web-http-proxy \
  --ports=80

# READ-ONLY: inspect the assigned frontend IP.
gcloud compute forwarding-rules describe retail-web-http-rule \
  --project="$PROJECT_ID" \
  --global \
  --format="yaml(name,IPAddress,IPProtocol,portRange)"
~~~

A global frontend may use an ephemeral IP in a lab; in production, reserve static IPs and manage DNS deliberately. Test `http://<FRONTEND_IP>/` externally only **after** healthy backends appear. If errors occur, avoid tearing down the whole stack—debug layer by layer per the troubleshooting section.

### 5.8. Verify backend health

~~~bash
# READ-ONLY: check backend health on the global backend service.
gcloud compute backend-services get-health "$BACKEND" \
  --project="$PROJECT_ID" \
  --global
~~~

It takes time for VMs to boot, health checkers to complete probes, and status to stabilize. If backends stay unhealthy, verify the app listens on `0.0.0.0:8080`, firewalls, named ports, and health check paths before adding more VMs.

## 6. Expanding to a multi-zone regional MIG for production

A single zonal MIG cannot survive a zone outage. For production availability, create a **regional MIG** distributing VMs across multiple zones in one region.

~~~mermaid
flowchart TD
    LB["Global external Application Load Balancer"] --> BS["Backend service"]
    BS --> RM["Regional MIG: asia-southeast1"]
    RM --> A["Zone A: 2 VMs"]
    RM --> B["Zone B: 2 VMs"]
    RM --> C["Zone C: 2 VMs"]
    DB["Cloud SQL / durable store"] --> APP["Shared application state"]
    A -.-> APP
    B -.-> APP
    C -.-> APP
~~~

### 6.1. Example of creating a regional MIG

~~~bash
# WRITE: deploy across multiple zones in the same region.
gcloud compute instance-groups managed create retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1 \
  --zones=asia-southeast1-a,asia-southeast1-b,asia-southeast1-c \
  --template=retail-web-v1 \
  --base-instance-name=retail-web \
  --size=6

gcloud compute instance-groups managed set-named-ports retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1 \
  --named-ports=http:8080

# READ-ONLY: inspect VM distribution across the group.
gcloud compute instance-groups managed list-instances retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1
~~~

This example is an **alternative** to the zonal MIG created earlier, not meant to run simultaneously with conflicting instance names. Before migrating a backend from zonal to regional, validate zones, quotas, IPs/subnets, and distribution policies. Listed zones must belong to the chosen region and support the machine type.

### 6.2. Attaching a regional MIG to a backend service

A **compatible** backend service can reference a regional MIG:

~~~bash
# WRITE: use only when attaching the regional MIG in place of another backend
# or when the backend service topology supports adding it.
gcloud compute backend-services add-backend retail-web-backend \
  --project=retail-lab \
  --global \
  --instance-group=retail-web-regional \
  --instance-group-region=asia-southeast1 \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.80
~~~

Never attach two instance groups containing the **same underlying VMs** or unsupported overlapping backend configurations. When shifting traffic from an old group to a new one, plan a controlled **migration/rollout** using backend weights or capacity scalers as supported by your load balancer type.

### 6.3. A regional MIG is not a multi-region strategy

To survive an **entire region** outage, add backends in another region and evaluate:

- How the global load balancer routes across backends in those regions.
- Whether Cloud SQL/Cloud Storage data and dependencies are available in the secondary region.
- Whether IAM, VPC egress, firewalls, TLS, quotas, and secrets are provisioned there.
- Added latency and data transfer costs when routing clients to a farther region.
- Tested failover and failback procedures.

Spreading VMs across zones will never protect a database running on a single instance or in a single region.

## 7. Autoscaling: from CPU to load balancing utilization

### 7.1. What does the autoscaler change?

The **MIG autoscaler** monitors configured signals, computes a **recommended size**, and adjusts the group's instance count within **min/max replicas**. Autoscalers can use CPU utilization, load balancing serving capacity, Cloud Monitoring metrics, or schedules depending on MIG type and feature support.

For example, a system needing two VMs off-peak and eight at peak:

~~~text
Min replicas: 2
Max replicas: 8

10:00 -> 2 VMs
12:00 -> 5 VMs (load increases)
13:00 -> 8 VMs (if cap reached)
16:00 -> 3 VMs (load drops, after stabilization)
~~~

This illustrates the concept only. **Scale-out is not instant**: VMs must be created, boot images, run startup scripts, start the app, and pass health checks before receiving traffic. **Scale-in uses stabilization/cooldown mechanisms** to prevent flapping; exact details depend on settings and product rules.

### 7.2. CPU-based autoscaling

For CPU-bound backends, set a CPU target:

~~~bash
# WRITE: configure autoscaler with min 2, max 8 VMs, 60% CPU target.
gcloud compute instance-groups managed set-autoscaling retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --min-num-replicas=2 \
  --max-num-replicas=8 \
  --target-cpu-utilization=0.60
~~~

Target `0.60` guides VM CPU utilization per autoscaler logic—it is **not a guarantee every VM stays below 60% CPU at all times**. If the app is bottlenecked on networking, disk I/O, database connections, or external APIs, CPU can stay low even as latency spikes. In that case, CPU alone is a poor scaling signal.

### 7.3. HTTP load balancing serving capacity autoscaling

When a MIG backs a supported HTTP(S) Application Load Balancer, the autoscaler can use **load balancing utilization**: scaling VM counts based on consumption of the backend's **serving capacity**.

~~~bash
# WRITE: ALTERNATIVE option to CPU autoscaling in the lab.
# Requires a valid backend service and configured serving capacity.
gcloud compute instance-groups managed set-autoscaling retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --min-num-replicas=2 \
  --max-num-replicas=8 \
  --target-load-balancing-utilization=0.70
~~~

In this model:

- The **backend service** must configure capacity and balancing mode compatible with the LB type.
- The **autoscaler** tracks utilization against LB serving capacity; `0.70` targets 70% of that modeled capacity, **not 70% CPU**.
- LB capacity calculations depend on balancing mode, backend settings (`UTILIZATION`, `RATE`, request caps, etc.), and LB type—never assume one universal formula across all backends.
- A MIG can combine multiple signals where supported, and the autoscaler takes the highest capacity requirement; never run separate `set-autoscaling` commands with different flags assuming they automatically merge additively.

Pick targets by measuring request rate, latency, resource utilization, and VM counts together. Setting the target too high risks overloading VMs before scale-out completes; setting it too low wastes money on idle capacity.

### 7.4. Distinguishing autoscaler target from backend max utilization

Suppose:

~~~text
Backend service:
  balancingMode: UTILIZATION
  maxUtilization: 0.80

MIG autoscaler:
  targetLoadBalancingUtilization: 0.70
  minNumReplicas: 2
  maxNumReplicas: 8
~~~

These two numbers serve **different purposes**:

- `maxUtilization` is a **backend service capacity/load-distribution parameter**.
- `targetLoadBalancingUtilization` is the **autoscaler's target** when evaluating serving capacity usage.

They are not simply two stacked CPU thresholds. Monitor metrics from both the backend service and autoscaler and validate with load tests.

### 7.5. Min/max, stabilization, and startup duration

In production, an autoscaler also needs:

1. **Min replicas** sufficient for baseline load, rolling update headroom, and surviving an unhealthy VM.
2. **Max replicas** aligned with quotas, budget, and downstream limits such as Cloud SQL connection pools.
3. **Initialization period** matching real VM readiness duration so startup metrics do not skew decisions.
4. **Scale-in stabilization and controls** to avoid prematurely terminating VMs handling long-lived requests.
5. **Capacity headroom** for traffic bursts before new VMs warm up.
6. **Load testing** measuring req/s, p95/p99 latency, and errors across fleet sizes.

Autoscaling cannot cure deadlocks, memory leaks, or an exhausted database connection pool. Adding VMs can even overwhelm a strained database faster.

### 7.6. Inspecting the autoscaler

~~~bash
# READ-ONLY: inspect autoscalers.
gcloud compute autoscalers list --project=retail-lab

# READ-ONLY: MIG configuration and target size.
gcloud compute instance-groups managed describe retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(targetSize,autoscaler,status)"

gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

Returned CLI fields can vary across API versions, especially recommended size details. Inspect raw output with `--format=yaml` before writing scripts coupled to specific fields.

## 8. Two types of health checks: load balancing vs. autohealing

### 8.1. Do not confuse "withhold traffic" with "replace VM"

Suppose a VM is warming up an internal cache:

- It may not be ready for HTTP traffic yet (`/healthz = 503`).
- Yet its process and guest OS are completely healthy (`/livez = 200`).

The load balancer should **stop sending new requests** when `/healthz` fails. MIG autohealing does not necessarily need to recreate the VM right away, especially during transient dependency glitches. Both mechanisms serve distinct goals.

| Mechanism | Primary attachment | Decision |
| --- | --- | --- |
| **LB health check** | Attached to the backend service. | Should this backend instance receive traffic? |
| **MIG autohealing health check** | Attached to the MIG autohealing policy. | Should this VM be repaired/recreated? |

You may share one health check if criteria align, though most systems benefit from **separating readiness and liveness**, tuning thresholds and initial delays to prevent unnecessary VM churn.

### 8.2. Example autohealing configuration

~~~bash
# WRITE: lightweight health check for MIG VM evaluation.
gcloud compute health-checks create http retail-web-repair-hc \
  --project=retail-lab \
  --global \
  --port=8080 \
  --request-path=/livez

# WRITE: attach health check directly to the MIG.
gcloud compute instance-groups managed set-autohealing retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --health-check=retail-web-repair-hc \
  --initial-delay=300
~~~

`--initial-delay=300` only illustrates an **initial startup grace window**; measure real boot times and adjust accordingly. A VM whose startup script takes 8 minutes will be flagged unhealthy prematurely if the delay is too short.

### 8.3. Health check design pitfalls

- Health endpoint unconditionally returns 200 even when core workers die: LB keeps routing traffic to broken backends.
- Health endpoint runs heavy database queries: every VM turns unhealthy together when the DB slows down.
- Health endpoint requires login or tokens that Google health checkers never send.
- Application binds only to `127.0.0.1:8080`, making it unreachable to network probes.
- Firewall blocks health checker ranges even though `curl localhost:8080/healthz` succeeds inside the VM.
- Overly sensitive autohealing triggers constant VM recreation, further shrinking capacity.

**Always verify from both inside the guest OS and the backend service perspective.** Testing localhost proves only that a process opened a port locally, not that Google probes can reach the VPC interface.

## 9. Rolling updates, connection draining, and safe deployments

### 9.1. Versioned image/template updates

Application code changes should follow:

~~~mermaid
flowchart LR
    BUILD["CI builds image/artifact"] --> TMP["Instance template v2"]
    TMP --> PLAN["Review rollout policy"]
    PLAN --> MIG["MIG rolling update"]
    MIG --> BOOT["New VMs boot"]
    BOOT --> H["Health checks pass"]
    H --> LB["Load balancer routes traffic"]
    LB --> OBS["Monitor latency/errors"]
    OBS --> DEC{"Meets SLO?"}
    DEC -- "No" --> RB["Version rollback"]
    DEC -- "Yes" --> DONE["Complete rollout"]
~~~

A new instance template **does not immediately replace old VMs**. The MIG needs an explicit version update or rollout trigger via API/CLI/IaC. Operators must control replacement pace, surge VMs, and allowable unavailability per wave.

### 9.2. Controlled rolling update example

Suppose template `retail-web-v2` is built, tested, and registered:

~~~bash
# WRITE: start rolling update; run only after reviewing template v2.
gcloud compute instance-groups managed rolling-action start-update retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --version=template=retail-web-v2 \
  --max-surge=1 \
  --max-unavailable=0

# READ-ONLY: monitor instance replacement progress.
gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

`max-surge` and `max-unavailable` aim to replace a few VMs at a time while preserving capacity. Verify quota headroom and compatibility with zonal/regional MIG constraints. **Never promise zero downtime solely from `max-unavailable=0`**: in-flight requests, load balancer health lag, and application state can still cause errors.

### 9.3. Connection draining

When a VM is removed from a backend during scale-in or a rolling update, active requests may still be in progress. Backend service **connection draining** gives the backend a grace period to finish existing connections/requests as supported by the product.

~~~bash
# WRITE: example setting a 60-second draining timeout on the backend service.
gcloud compute backend-services update retail-web-backend \
  --project=retail-lab \
  --global \
  --connection-draining-timeout=60s
~~~

The application should also handle stop signals, stop accepting new work, and finish or cleanly abort in-flight work. If a request can run for 5 minutes while draining timeout is 60 seconds, connections can still be severed. Size the timeout around protocols, workload duration, cost, and backend characteristics.

For long background jobs or queue workers, do not rely solely on HTTP load balancer connection draining; use checkpoints, idempotency, and safe job re-delivery.

### 9.4. Blue/green and canary

For major changes, teams can maintain:

- A **Blue MIG** running the stable version.
- A **Green MIG** running the new version and passing smoke/health checks.
- **Backend services or URL traffic splitting** per load balancer capabilities to shift traffic gradually.

During a canary, track errors and latency separately for the new version; avoid blended metrics when traffic share is tiny or request mixes differ. Weighted traffic splitting, capacity scalers, and session affinity depend on load balancer type—verify support before choosing a rollout pattern.

## 10. Production scenario: multi-zone retail website

### 10.1. Business requirements

Suppose `shop.example.com` serves shoppers:

- Public HTTPS frontend with web backends on Compute Engine.
- Off-peak load of a few hundred requests/minute, spiking sharply during campaigns.
- Must survive single-VM failures and minimize risk during a zone outage.
- Order data stored in **Cloud SQL**; product images in **Cloud Storage**.
- DevOps deploys releases through CI/CD with zero manual SSH edits on VMs.
- Must monitor latency, error rates, and VM/load balancer costs.

### 10.2. Proposed architecture

| Component | Illustrative choice | Rationale |
| --- | --- | --- |
| Frontend | Global external Application Load Balancer (HTTPS). | TLS termination, single domain, URL routing, multi-zone backends. |
| VM fleet | Regional MIG in `asia-southeast1` across at least two zones. | Reduces single-zone dependency. |
| Instance template | Tested application image, `e2-*` or load-test-verified machine type. | Uniform, fast-booting VMs. |
| Named port | `http:8080`. | Routes backend service to the exact app port. |
| Backend health | `/healthz` on HTTP 8080. | Directs requests only to ready instances. |
| MIG autohealing | `/livez` with tuned initial delay. | Replaces genuinely broken VMs without overreacting. |
| Autoscaler | Min capacity for baseline, max bounded by quota/cost, benchmarked CPU/LB signals. | Balances cost and latency. |
| Data tier | Cloud SQL/Storage/Secret Manager; never treat boot disks as sole storage. | VMs stay disposable with zero data loss. |
| Networking | Backends without external IPs where unneeded, minimal egress, LB-scoped firewalls. | Minimizes attack surface. |
| Observability | Backend health, requests/5xx, p95/p99, autoscaler/MIG, Cloud SQL bottlenecks. | Pinpoints root causes and tracks SLOs. |

### 10.3. Request path

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant L as HTTPS Load Balancer
    participant B as Backend service
    participant V as VM in regional MIG
    participant D as Cloud SQL
    C->>L: GET /products/42
    L->>B: URL map selects web backend
    B->>B: Pick healthy VM by capacity
    B->>V: HTTP to named port
    V->>D: Query data via identity/DB auth
    D-->>V: Result
    V-->>C: HTTP response via load balancer
~~~

This sequence omits many network, TLS, and IAM steps. VMs need **database connectivity, authentication, and SQL privileges**, not just a healthy load balancer. If Cloud SQL is saturated, scaling out the MIG with more VMs can worsen database connection pressure.

### 10.4. Rehearsing three failure modes

**VM crash:** an instance stops answering `/healthz`. The load balancer stops routing to it per health criteria; MIG autohealing replaces the VM on matching liveness failures. Measure replacement time and verify remaining VM capacity.

**Single zone unavailable:** the regional MIG keeps VMs serving in other zones if capacity and distribution were sized properly. Inspect failed requests, dependencies, and how the MIG restores distribution afterward.

**Sudden traffic surge:** the autoscaler needs time to provision VMs; measure p95/p99 latency during warm-up and watch max replicas and quotas. If DB connection pools saturate, adding VMs alone will not solve the bottleneck.

## 11. Security, IAM, and operational responsibilities

### 11.1. Separation of identities

Never reuse one broad service account for both CI/CD and VM runtime:

| Principal | Responsibility | Required permissions |
| --- | --- | --- |
| **CI/CD deployer** | Create templates, update MIGs and backend configs per pipeline. | Roles scoped strictly to target infra resources plus service account actAs where needed. |
| **VM runtime service account** | Call Cloud Storage, Cloud SQL Admin APIs, or Secret Manager for the app. | Least-privilege permissions on exact resources; separate DB user privileges. |
| **SRE/on-call** | Inspect logs, health, metrics, and investigate instances. | Viewer/monitoring/logging roles and audited maintenance permissions. |
| **Network/security team** | Manage firewalls, certificates, Cloud Armor/policies. | Dedicated roles and change approval for sensitive policies. |

Data access is not automatically secured merely because the app sits behind an HTTPS load balancer. **Frontend TLS encrypts client–LB traffic**, while LB-to-backend traffic follows separate protocols and network policies; enable backend encryption options if required.

### 11.2. Cloud Armor, IAP, and Cloud CDN

Depending on Application Load Balancer type:

- **Cloud Armor** helps protect apps from malicious traffic and enforce edge access policies.
- **Identity-Aware Proxy (IAP)** fits internal applications requiring user authentication, subject to topology and compatibility.
- **Cloud CDN** speeds up cacheable images/assets, though cache policies must avoid caching personal data or shopping carts.

Do not assume every feature can be enabled simultaneously on the same backend service; check compatibility for your exact load balancer type, protocol, and product tier.

### 11.3. State and sessions

A scalable architecture should **avoid storing sessions solely in VM RAM**. When subsequent requests land on another VM or a VM gets replaced, local sessions vanish.

Alternatives include server-verified tokens/sessions, a shared external session store, or fully stateless designs. Load balancer **session affinity** helps in specific cases, yet it never guarantees a user stays pinned to one VM across failures, rollouts, or scaling events. Never substitute session affinity for durable state design.

## 12. Monitoring: healthy VMs aren't enough—users must succeed

### 12.1. Signals to track

| Layer | Signals | Question |
| --- | --- | --- |
| Frontend LB | Requests, HTTP 4xx/5xx, TLS errors, latency. | Can users reach the site? |
| Backend service | Healthy/unhealthy instance counts, request distribution, backend latency. | Which backend is failing? |
| MIG | Target size, actual size, recreations, rolling update state. | Are enough ready VMs running per policy? |
| Autoscaler | Recommended/current capacity, CPU/LB signals, min/max saturation. | Is scaling capped or reacting too slowly? |
| VM | CPU, memory, disk I/O, startup logs, process health. | Are guest resources bottlenecked? |
| Dependencies | Cloud SQL connections/latency, Cloud Storage errors, cache saturation. | Is the bottleneck outside the VMs? |
| Business | Checkout success rate, p95/p99 latency, payment errors. | Are end-to-end SLOs met? |

Autoscaler metrics may not appear immediately after resource creation. When analyzing incidents, check **metric ingestion lag, warm-up windows, and health transitions**. Alert on user impact rather than paging on every single VM replacement.

### 12.2. Recommended alerts

- Healthy backend count drops below minimum required capacity for a sustained window.
- 5xx error rate or p95 latency breaches SLO.
- Autoscaler hits `maxNumReplicas` while request queues keep growing.
- MIG fails to reach target size due to quotas or startup errors.
- Excessive autohealing/recreate rate within a short window.
- Cloud SQL latency or connection errors climb right after scale-out.
- VM/load balancing/logging spend trends past budget thresholds.

A single transient HTTP error during a deployment should not trigger an emergency page; evaluate error ratios, duration, blast radius, and SLO burn rates.

### 12.3. Read-only inspection commands

~~~bash
# READ-ONLY: list managed instance groups.
gcloud compute instance-groups managed list \
  --project=retail-lab

# READ-ONLY: inspect MIG configuration and instance states.
gcloud compute instance-groups managed describe retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a

gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a

# READ-ONLY: inspect backend service and health.
gcloud compute backend-services describe retail-web-backend \
  --project=retail-lab --global

gcloud compute backend-services get-health retail-web-backend \
  --project=retail-lab --global

# READ-ONLY: inspect autoscalers and health checks.
gcloud compute autoscalers list --project=retail-lab
gcloud compute health-checks list --project=retail-lab
~~~

These commands assume the illustrative resources exist. For regional deployments, use `--region` instead of `--global`/`--zone` depending on the specific API. Output will be incomplete if the caller lacks read IAM permissions.

## 13. Troubleshooting: working from the outside in

| Symptom | Likely cause | Check first |
| --- | --- | --- |
| Frontend receives no HTTP(S) traffic | Wrong DNS/forwarding rule, IP, TLS cert, or target proxy. | Forwarding rule, target proxy, URL map, DNS, and certificate. |
| LB returns `502` or `503` | Unhealthy backends, app not running, timeouts, exhausted capacity, or misrouted traffic. | Backend service `get-health`, VM logs, health checks, and network. |
| MIG has 2 VMs, yet `get-health` reports unhealthy | Startup script error, app not binding port, wrong named port, or wrong health path. | `list-instances`, port, path, and boot logs. |
| `curl localhost:8080/healthz` works, yet LB sees unhealthy | Firewall blocks health checker/proxy ranges or backend protocol/port mismatch. | VPC firewall, health check config, and named ports. |
| Autoscaler does not scale despite high latency | CPU/LB signal misses the bottleneck, autoscaler disabled, or already at max. | Autoscaler config, metrics, max replicas, DB bottleneck. |
| Newly created VMs receive no traffic | Startup incomplete, health check unhealthy, wrong network/tag. | Guest logs, readiness, health status, and firewall. |
| MIG constantly replaces VMs | Autohealing `/livez` too sensitive, initial delay too short, broken image. | Autohealing health check, repair events, startup duration. |
| Rolling update shrinks capacity | Surge/unavailable policy, missing quota, slow app startup, short draining. | Rolling update state, instance health, backend logs. |
| Post-peak scale-in causes user errors | Too-fast scale-in, local sessions, long requests cut short. | Stabilization, connection draining, session architecture. |
| Scale-out overloads Cloud SQL | Each VM opens too many DB connections or unpooled clients. | DB metrics, connection pooling, max replicas. |
| Cost stays high during low traffic | High min replicas, leftover VMs/disks, ongoing LB/logging/egress spend. | Cloud Billing, MIG target, disks, networking. |
| Health is green, yet checkout fails | Health endpoint skips critical business logic or dependencies. | Business SLIs, Cloud SQL, app logs, synthetic end-to-end tests. |

### 13.1. Six helpful investigation steps

1. **Frontend:** verify exact IP, port, TLS certificate, target proxy, and URL map.
2. **Backend service:** verify instance group attachment, global/regional scope, and named port.
3. **Health check:** verify path, port, protocol, and `get-health` output.
4. **Networking:** verify firewall rules and routes from load balancer/proxy ranges to backend IPs.
5. **VM/MIG:** inspect processes, startup scripts, instance statuses, autohealing, autoscaler, and rolling updates.
6. **Application:** correlate logs, request IDs, databases, Cloud Storage, and business completion rates.

Never tweak autoscaler settings or raise min replicas when the root cause is a wrong health-check port. Conversely, never open the entire firewall just because a backend shows unhealthy.

## 14. Reliability, capacity, and cost

### 14.1. Adding VMs does not scale throughput linearly

An app serving 100 requests/second on one VM will not necessarily serve 1,000 requests/second on 10 VMs. Reasons include:

- Database connection or query throughput limits.
- Shared cache, rate-limit, or external API bottlenecks.
- Cross-zone/inter-region data transfer adding latency and cost.
- Session affinity skewing load unevenly across VMs.
- Non-parallelizable segments of the workload.

Benchmark **useful throughput within p95/p99 latency and error limits**—never rely on CPU utilization or instance count alone.

### 14.2. Cost components

~~~text
Total cost ≈
  VM CPU/RAM by machine type and runtime
  + boot/data disks and snapshots
  + load balancer and traffic processing
  + cross-zone/egress data transfer
  + Cloud Logging/Monitoring, network services
  + data services (Cloud SQL/Storage/Cache)
  + spare/surge capacity during rollouts
~~~

This is a mental model, not an official billing formula. A MIG autoscaling from 2 to 8 VMs saves money off-peak, yet **min replicas, disks, load balancers, and supporting services still incur ongoing charges**. Track cost per request or per successful transaction rather than cost per VM alone.

### 14.3. Choosing bounds from SLOs

The following example uses hypothetical planning numbers:

| Parameter | Assumed value | Must be verified |
| --- | --- | --- |
| Latency SLO | 95% of requests under 300 ms. | Measured from client side or backend only? |
| Baseline load | 200 requests/minute. | Is min capacity sufficient? |
| Peak load | 3,000 requests/minute. | How many requests per VM at target p95? |
| VM warm-up | 2 minutes. | Covers startup script, image pull, and health probes? |
| Min/max replicas | 2/8. | Aligns with quotas, cost, fault tolerance, and DB pool? |
| Scale-out lag | Several minutes depending on stack. | Needed pre-campaign schedule or min headroom? |

Never pick `maxNumReplicas=8` just because it's a round number; justify it via load tests and downstream impact. Autoscaling optimizes **compute resources**, while SLOs require end-to-end system design.

## 15. Practice exercises

### Exercise 1 — Component responsibilities

An engineer says: "The MIG already has three VMs, so the HTTPS load balancer automatically gets a frontend and URL map." Explain why this is wrong. List the required resources from frontend to backend, and identify what the MIG owns.

**Hint:** The MIG manages VMs; frontend IP/forwarding rules, target proxies, URL maps, backend services, health checks, and firewalls belong to load balancing and VPC networking configuration.

### Exercise 2 — Named port mismatch

In a MIG, the named port is `http:8080`, the process listens on `9090`, and the health check probes `8080`. Explain why MIG VMs stay `RUNNING` yet the backend reports unhealthy. Propose a fix without widening firewall rules.

### Exercise 3 — Picking an autoscaler signal

A website queries Cloud SQL heavily; latency climbs at 200 concurrent requests while VM CPU stays at 25%. How will a 60% CPU autoscaler react? Should you scale VMs indefinitely?

**Hint:** A CPU target may not trigger scale-out; check connection pools, SQL latency, and consider load balancing or custom metrics. Adding VMs can pile on even more DB connections.

### Exercise 4 — Zonal vs. regional MIG

A webshop must survive a single-zone failure in `asia-southeast1`. Choose zonal or regional MIG and explain its limits. What else is needed beyond the MIG to keep operating if the entire region goes down?

### Exercise 5 — LB health checks and autohealing

VMs lose Cloud SQL connectivity for 20 seconds; `/healthz` returns 503 while `/livez` still returns 200. How should the load balancer and MIG autohealing respond to avoid sending failing traffic without triggering a VM replacement storm?

### Exercise 6 — Rolling update drill

A MIG has min size 2 and v1 runs smoothly. Outline the sequence to roll out v2, verify health, configure surge/unavailable, set connection draining, monitor p95/5xx, and roll back on threshold breach. Why is `max-unavailable=0` insufficient to promise zero downtime?

### Exercise 7 — Calculating serving capacity

One VM sustains roughly 150 requests/minute at the target SLO; peak load is 600 requests/minute. In simple capacity math, how many healthy VMs are needed at minimum? Why must production add headroom, single-VM failure margin, warm-up time, and Cloud SQL limits?

**Hint:** 600 / 150 = 4 healthy VMs under ideal conditions; production must account for all the operational factors listed above.

### Exercise 8 — Cutting off-peak costs

You have a tight budget yet must stay responsive during sudden traffic surges. Propose min/max replicas, an observable autoscaling signal, a pre-campaign warm-up approach, and metrics proving costs dropped without harming SLOs.

## 16. Operational checklist and official references

| Item | Requirement before production launch |
| --- | --- |
| **Backend design** | Versioned instance template, reliable startup, stateless app or durable external storage. |
| **MIG** | Zonal/regional choice matches requirements, with proper target capacity and headroom. |
| **Named ports** | Exact mapping between application listening port and backend service port name. |
| **Load balancer type** | Appropriate external/internal, Application/Network, global/regional choice. |
| **Backend service** | Group attached at matching scope, valid balancing mode/capacity, and health checks. |
| **Firewall** | Allows exact health checker/proxy ranges and ports; restricts direct exposure. |
| **TLS/DNS** | HTTPS/certificates, forwarding rules, and DNS match production frontend. |
| **Autohealing** | Appropriate health check, initial delay, and tested failure/recovery flow. |
| **Autoscaling** | Min/max backed by load tests, demand-accurate signal, safe scale-in policies. |
| **Rollout** | Immutable images/templates, rolling updates and rollback tested, connection draining set. |
| **Security** | Least-privilege IAM for deployers, runtime service accounts, and ops staff. |
| **Dependencies** | Cloud SQL, Cloud Storage, secrets, and egress have sufficient capacity and permissions. |
| **Observability** | LB 5xx, latency, backend health, MIG state, autoscaler, and business SLIs tracked. |
| **Cost** | VM/disk/LB/egress/logging spend tracked with alerts and cost-per-transaction metrics. |
| **Resilience** | Rehearsed VM loss/zone loss drills verifying data recovery and remaining capacity. |

Google Cloud documentation to verify against current versions:

- [Managed instance groups overview](https://cloud.google.com/compute/docs/instance-groups)
- [Create managed instance groups](https://cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances)
- [MIG autoscaling overview](https://cloud.google.com/compute/docs/autoscaler)
- [Autoscale based on HTTP(S) load balancing serving capacity](https://cloud.google.com/compute/docs/autoscaler/scaling-based-on-load-balancing)
- [MIG autohealing](https://cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs)
- [Rolling out updates to MIGs](https://cloud.google.com/compute/docs/instance-groups/rolling-out-updates-to-managed-instance-groups)
- [Cloud Load Balancing overview](https://cloud.google.com/load-balancing/docs/load-balancing-overview)
- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Health checks concepts](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Firewall rules for load balancing](https://cloud.google.com/load-balancing/docs/firewall-rules)
- [gcloud compute instance-groups managed](https://cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed)
- [gcloud compute backend-services](https://cloud.google.com/sdk/gcloud/reference/compute/backend-services)

**Key takeaway:** MIGs manage **VM lifecycle and fleet size**; Cloud Load Balancing manages **ingress and traffic distribution to healthy backends**; the autoscaler adjusts **capacity from load signals**. A system is truly production-ready only when all three are wired cleanly through named ports, backend services, health checks, and firewalls—backed by disciplined release processes, durable state management, and SLO monitoring.
