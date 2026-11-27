# Zonal and regional managed instance groups

Suppose a Java application runs on a single Compute Engine virtual machine. When user traffic grows, the machine can become overloaded; if the VM fails or the zone experiences an outage, the website stops serving requests. Manually creating a few more VMs increases processing capacity, but the operations team then has to manually synchronize software versions, replace failed machines, and update each VM individually. **Managed instance groups (MIGs)** solve this problem by managing multiple virtual machines as a single group with uniform configuration, count, and lifecycle.

In Google Cloud, a MIG can be deployed in **a single zone (zonal MIG)** or **multiple zones within the same region (regional MIG)**. This distinction directly impacts fault tolerance, capacity distribution, quotas, costs, and load balancing design. This is the core focus of this lesson in the **Instance Groups and Autoscaling** chapter of the **CLOUD_PROVIDERS_GCP** module: selecting Google Cloud services, securing resources with IAM/VPC, deploying applications, automating releases, and monitoring reliability and cost.

After this lesson, you can:

- Distinguish between **zonal MIGs**, **regional MIGs**, and **unmanaged instance groups**.
- Create and use **instance templates**, understanding immutability and the lifecycle of managed instances.
- Choose the right zone count, target distribution shape, and distribution policy.
- Distinguish between **autoscaling**, **autohealing**, **load balancing**, and **rolling updates**.
- Create MIGs using the Console or `gcloud`, and observe actual VM counts and provisioning errors.
- Design a Java service capable of surviving a zone failure, handling traffic spikes, and controlling costs.

## 1. What is a MIG?

A **managed instance group** is a Compute Engine resource that manages a collection of VMs based on a shared configuration, typically an **instance template**. A MIG can proactively create VMs, replace failed VMs, adjust instance counts when an autoscaler is enabled, and update configurations via rolling updates.

~~~mermaid
flowchart TD
    A["Instance template: OS, machine type, network, startup"] --> B["Managed instance group"]
    B --> C["VM instance 1"]
    B --> D["VM instance 2"]
    B --> E["VM instance 3"]
    F["Autoscaler: load and min/max"] --> B
    G["Autohealing: application health check"] --> B
    H["Updater: template v2 / rolling update"] --> B
    I["Load Balancer"] --> C
    I --> D
    I --> E
~~~

### Core concepts

| Concept | Meaning | Example |
|---|---|---|
| **Instance template** | VM blueprint: machine type, boot disk, image, NIC, service account, startup script | `java-api-template-v1` |
| **MIG manager** | Resource that orchestrates VMs according to configuration, target size, and policies | `orders-api-mig` |
| **Target size** | Number of VMs the group aims to maintain without an autoscaler, or the count decided by the autoscaler | 6 |
| **Managed instance** | A VM managed by a MIG; names typically include a generated suffix | `orders-api-x7k2` |
| **Autoscaler** | Adjusts VM count based on CPU, load-balancing capacity, metrics, or schedule | Min 3, max 12 |
| **Autohealing** | Detects unhealthy VMs via health checks and replaces them per policy | HTTP `/healthz` fails to return success |
| **Updater** | Applies VM changes based on templates/versions and allowed disruption | Rolling update v1 → v2 |
| **Load balancer** | Distributes requests to healthy instances in the group | External Application Load Balancer |

**A MIG is not a load balancer.** A MIG manages VMs; a load balancer receives and distributes traffic to the VMs that the MIG supplies as a backend. **Nor does a MIG enable every mechanism by default**: autoscaling, application-based autohealing, and load balancing must be configured explicitly to work as expected.

### MIG vs. unmanaged instance group

| Characteristic | Managed instance group | Unmanaged instance group |
|---|---|---|
| Create multiple VMs from one blueprint | Yes | Manage VMs individually |
| Autoscaling via MIG autoscaler | Supported when configured for compatible workloads | Not managed by MIG autoscaling |
| Self-healing VMs via health checks | Can enable autohealing | No built-in MIG autohealing mechanism |
| Rolling updates from instance template | Supported | Must coordinate VM replacement separately |
| Arbitrary heterogeneous VMs | Constrained by group configuration, with supported exceptions | More flexible |
| Best suited for | Relatively uniform, replaceable VM fleets | Heterogeneous VM sets grouped for administration or as a backend |

MIGs are best suited for **stateless** workloads such as web frontends and API workers; **stateful MIG** features also exist for workloads that must preserve certain resources/state, though they carry significant limitations for autoscaling and rolling update management. Placing a database inside a MIG should never be assumed to automatically provide replication, backups, or data-tier high availability.

## 2. Zones and regions: the foundation of design decisions

A **region** is a geographical area provided by Google Cloud, typically containing multiple **zones**. A zone is a deployment domain with infrastructure isolated to the extent designed by the service; even within the same region, do not assume every zone has the same availability of machine types, GPUs, or quotas.

~~~text
Region: us-central1
├── Zone: us-central1-a
│   ├── VM A1
│   └── VM A2
├── Zone: us-central1-b
│   ├── VM B1
│   └── VM B2
└── Zone: us-central1-c
    ├── VM C1
    └── VM C2
~~~

A system with 6 VMs distributed 2-2-2 has a significantly different risk profile from 6 VMs all placed in `us-central1-a`. If zone A becomes unavailable, VMs in B and C can continue serving. However, the application, load balancer, database, and all dependent services must also be designed for fault tolerance for end-to-end availability to improve.

## 3. Zonal MIGs and regional MIGs

| Criterion | **Zonal MIG** | **Regional MIG** |
|---|---|---|
| VM placement | Single zone | Multiple selected zones within the same region |
| Zone fault tolerance | Cannot automatically maintain service if the entire zone goes down | VMs in remaining healthy zones can continue serving |
| Orchestration level | Single zone, predictable placement | Distributed according to target distribution shape |
| Quota/capacity | Dependent on a single specific zone | Can leverage multiple zones, depending on distribution policy |
| Core MIG features | Templates, autohealing, autoscaling, updates | Corresponding features plus zonal distribution options |
| Default VM limit | 1,000 VMs | 2,000 VMs |
| Common use cases | Dev, zone-bound batch jobs, workloads requiring locality | Production web/API workloads requiring single-zone fault tolerance |

The VM limits listed above are **Google Cloud's published default limits**, which may vary by configuration and limit-increase policies; they do not mean your project quota already permits creating that many VMs.

### When to choose a zonal MIG

- Dev/test environments aiming to reduce complexity and accepting single-zone outage risk.
- Batch workers that only need to run in one zone because their data resides in that same zone.
- Strict control over VM placement or machine types available in only one zone.
- Teams learning MIG fundamentals before building multi-zone architectures.

### When to choose a regional MIG

- Customer-facing websites and APIs needing reduced blast radius when a single zone fails.
- Distributing Compute Engine load across zones within the same region.
- Improving the likelihood of finding available resources or utilizing eligible reservations.
- When ready to configure external/internal load balancers, health checks, and stateless applications.

**A regional MIG is not a multi-region MIG.** It only deploys within **a single region**. If the entire region becomes unavailable, a single regional MIG cannot keep the service running in another region. To survive a regional outage, you typically need separate deployments across multiple regions and an appropriate traffic distribution/failover model.

### Selecting zones when creating a regional MIG

For a regional MIG, you can specify the allowed zones at group creation time; if omitted, Google Cloud typically selects three zones by default. **You cannot change the selected list of zones by directly editing an existing regional MIG after creation**; you must plan ahead or rebuild/migrate to a new group if you want different zones.

Do not look only at zone names: verify machine type support, persistent disks, and GPUs/reservations if used; the subnet configuration must belong to the matching region, and you cannot arbitrarily change a MIG's network/subnet after it is created.

## 4. How does a regional MIG distribute VMs?

A regional MIG has a **target distribution shape** that dictates how zones are chosen when creating or deleting VMs. Do not equate "regional" with "always split evenly."

| Shape | How zones are selected | Best suited for |
|---|---|---|
| **EVEN** (default) | Tries to keep target instance counts across zones within a difference of at most 1 | API/web serving requiring even distribution and HA |
| **BALANCED** | Aims for relatively even distribution while prioritizing zones with available capacity | Serving/batch needing better resilience against capacity exhaustion |
| **ANY** | Picks zones based on available resources and reservation utilization without prioritizing even balance | Batch workloads with lower zonal HA requirements |
| **ANY_SINGLE_ZONE** | Places all VMs in a single selected zone | Workloads needing low inter-VM latency/locality, accepting zone risk |

**Example with 6 VMs across 3 zones:** `EVEN` targets 2-2-2; `BALANCED` may produce 3-2-1 when resources are constrained and adjust as conditions change; `ANY` may skew further; `ANY_SINGLE_ZONE` places all VMs in one zone. These are illustrative distribution examples, not a guarantee that the system will maintain those exact ratios at every moment.

Key nuances to understand:

- `EVEN` maintains the distribution target but **does not guarantee all 6 VMs are RUNNING** if one zone lacks capacity; you may see uncreated VMs in the constrained zone.
- `BALANCED` can place more VMs into zones with spare resources, which helps during localized quota/capacity shortages.
- `ANY` and `ANY_SINGLE_ZONE` **do not guarantee** the application stays up if the largest or chosen zone fails.
- When using `BALANCED` or `ANY_SINGLE_ZONE`, **proactive instance redistribution** must be disabled per Google Cloud requirements; check support for autoscaling, canary updates, and instance flexibility for each shape.
- **Instance flexibility** allows specifying fallback machine types in priority order where supported, such as `e2-standard-4` or `n2-standard-4`, but it is not supported with the `EVEN` shape.

### Proactive instance redistribution

In a regional MIG, **proactive redistribution** (enabled by default where applicable) actively works to bring the group back to its desired cross-zone distribution. This can cause the MIG to create and delete instances during rebalancing.

If an application runs long-lived tasks or holds VM-bound state, overly aggressive movement can cause disruption. Consider disabling redistribution where the use case and shape allow, while weighing the risk of uneven distribution. **Redistribution is not autoscaling**: one mechanism changes VM placement/balance across zones, while the other changes the **total number** of VMs.

## 5. Instance templates: VM blueprints

To create a MIG, you need an **instance template** defining the VM configuration. For example:

~~~text
Instance template: java-api-v1
├── machine type: e2-medium
├── boot disk: Debian Linux (or custom image)
├── network/subnet: app-vpc / app-subnet
├── service account: java-api-runtime@...
├── tags/labels: java-api, environment=dev
├── metadata/startup-script: start application and health endpoint
└── image/version: verified artifact
~~~

A template can be **global** or **regional**, depending on how it is created. For a zonal MIG, use a compatible template; for a regional MIG, the template must be valid in every zone the group intends to use or paired with compatible distribution features. Templates are **immutable**: to change the boot image, startup script, or machine type, create a new template and roll out the new version to the MIG.

### Ensuring VMs boot identically

- Use pinned-version images/container artifacts; avoid relying on `latest` tags that change silently.
- Make startup scripts idempotent, ensure they log properly, and ensure startup failures are reflected through health checks.
- Never place secrets inside images, startup scripts, or instance metadata; use Secret Manager and workload identity where appropriate.
- Each VM needs a **least-privilege** service account for Cloud Storage, Pub/Sub, Logging, or the actual APIs it calls.
- Store user session data in a database, object storage, or shared cache rather than on a replaceable boot disk.
- Configure shutdown/graceful termination and handle stop signals in the application before rolling updates or scale-in events.

**Never store the sole copy of live data on stateless VMs.** Autohealing or rolling updates can delete and recreate VMs; temporary disks, processes, and in-memory state are lost. Stateful MIGs allow preserving certain stateful resources, but they do not replace database backup/replication design.

## 6. How to create zonal and regional MIGs in the Console

Prerequisites: a project with billing and the Compute Engine API enabled, a valid instance template, CPU/disk/IP quotas, a VPC/subnet, and IAM permissions. If the template attaches a service account, the creator also needs permission to use that service account.

1. Open **Compute Engine → Instance groups → Create instance group**.
2. Choose **New managed instance group** (stateless for typical web/API workloads).
3. Select or create an instance template; enter the MIG name and target number of VMs.
4. For a **zonal MIG**, select **Single zone**, the region, and a specific zone.
5. For a **regional MIG**, select **Multiple zones**, the region, and the zones to use; choose the target distribution shape (typically starting with **Even** for HA APIs).
6. Review **autoscaling**, **autohealing**, **instance lifecycle**, rolling update, and instance naming settings.
7. Click **Create**, wait for the operation to finish, and inspect the managed instances list and VM status per zone.

Note: the Console UI may enable autoscaling by default for stateless groups; if a lab requires a fixed size, check the autoscaling mode rather than assuming it stays at the initial `target size`. Creating VMs will incur charges.

## 7. gcloud hands-on: creating an instance template and both MIG types

The following examples are **operational samples** for a lab project; do not run them in production without reviewing quotas, permissions, and costs. Replace the Project ID, VPC, subnet, zone, and script file path with real resources. Create **only one of the two** MIGs depending on your goal; running both independent examples creates more VMs and incurs higher charges.

### 7.1. Create an instance template

A demo web VM needs an application responding to HTTP/health checks. Suppose your working directory contains the following `startup.sh` file:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Lab sample requires Internet egress or an internal mirror to install packages.
apt-get update
apt-get install -y nginx
echo "Hello from a managed VM" >/var/www/html/index.html
echo "ok" >/var/www/html/healthz
systemctl enable --now nginx
~~~

Create the shared template for the VMs:

~~~bash
PROJECT_ID="my-mig-lab-project"
REGION="us-central1"
ZONE="us-central1-a"
VPC="app-vpc"
SUBNET="app-subnet"
TEMPLATE="web-template-v1"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

# app-vpc and app-subnet must exist beforehand and match REGION.
# --no-address omits public IPs on VMs; appropriate NAT/egress is needed
# if the startup script downloads packages from the Internet.
gcloud compute instance-templates create "$TEMPLATE" \
  --machine-type=e2-medium \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --network="$VPC" \
  --subnet="$SUBNET" \
  --no-address \
  --tags=mig-web \
  --metadata-from-file=startup-script=./startup.sh

gcloud compute instance-templates describe "$TEMPLATE"
~~~

**Lab note:** the script installs Nginx from Debian repositories. If VMs have no external IP and no Cloud NAT or egress path, the startup script will fail to download packages. In production, use a **custom image or pre-built artifact** to shorten VM boot time, avoid external repository dependencies, and enable reproducible deployments.

### 7.2. Create a zonal MIG

~~~bash
ZONAL_MIG="web-zonal-mig"

gcloud compute instance-groups managed create "$ZONAL_MIG" \
  --zone="$ZONE" \
  --template="$TEMPLATE" \
  --size=3 \
  --base-instance-name=web-zonal

gcloud compute instance-groups managed describe "$ZONAL_MIG" \
  --zone="$ZONE"

gcloud compute instance-groups managed list-instances "$ZONAL_MIG" \
  --zone="$ZONE"
~~~

Expected outcome: the group attempts to create 3 VMs in `us-central1-a`. Once all VMs are provisioned and the script finishes, HTTP is reachable within the appropriate network when permitted by firewall rules. If the entire zone experiences an outage, the MIG **does not automatically move a zonal MIG's VMs to another zone**.

### 7.3. Create a regional MIG

~~~bash
REGIONAL_MIG="web-regional-mig"
ZONES="us-central1-a,us-central1-b,us-central1-c"

gcloud compute instance-groups managed create "$REGIONAL_MIG" \
  --region="$REGION" \
  --zones="$ZONES" \
  --template="$TEMPLATE" \
  --size=6 \
  --target-distribution-shape=even

gcloud compute instance-groups managed describe "$REGIONAL_MIG" \
  --region="$REGION"

gcloud compute instance-groups managed list-instances "$REGIONAL_MIG" \
  --region="$REGION"
~~~

With `EVEN`, size 6, and three zones, the target is typically **2 VMs per zone**. This is a **total of 6 VMs across the regional MIG**, not 6 VMs per zone. If a quota or capacity shortage occurs in one zone, inspect managed instance statuses and operation errors—never assume the group is ready merely because the create command succeeded.

> **Access note:** for VMs without external IPs, serving Internet traffic requires an appropriate load balancer and matching firewall rules. Creating a MIG does not automatically create DNS records, TLS certificates, or an external Application Load Balancer.

## 8. Autoscaling: adjusting total VM count based on load

An **autoscaler** changes the **target size** of a MIG based on supported signals such as CPU utilization, load-balancing serving capacity, Cloud Monitoring metrics, or schedules. For a regional MIG, min/max counts represent the **total number of VMs in the group**, not per-zone limits.

Suppose a web API sees elevated average CPU during peak hours. The team configures:

- **Minimum replicas:** 6 — maintains baseline capacity distributed across three zones.
- **Maximum replicas:** 18 — caps scaling in line with quotas and budget.
- **CPU target:** 0.65 (65%) — the autoscaler aims to keep CPU utilization near the target, not as a hard cap.
- **Initialization period:** 180 seconds — gives the application time to start up before scaling signals are evaluated.

~~~bash
gcloud compute instance-groups managed set-autoscaling "$REGIONAL_MIG" \
  --region="$REGION" \
  --min-num-replicas=6 \
  --max-num-replicas=18 \
  --target-cpu-utilization=0.65 \
  --cool-down-period=180
~~~

In this CLI command, `--cool-down-period` is the historical flag name for the autoscaler's **initialization period**, not a window during which the system "locks" all scale-in/scale-out actions. Measure actual startup time to pick this value rather than guessing. Google Cloud also provides stabilization, scale-in controls, and predictive autoscaling to reduce disruptive scaling behavior.

### Autoscaling is not strictly linear

If one healthy VM can handle roughly 100 requests/second, that **does not** prove six VMs will reliably handle 600 requests/second. Throughput also depends on request types, database load, contention, garbage collection, networking, and request queues. A 65% CPU target is a scaling signal, not a direct formula converting QPS into VM counts.

Additionally:

- Adding VMs takes time to create disks, boot the OS, run startup scripts, warm up the JVM, and pass health checks.
- Scale-out can fail if **CPU, disk, or IP quotas**, subnet IP space, or zonal capacity are exhausted.
- Scale-in can terminate VMs actively serving requests if the application lacks connection draining/graceful shutdown.
- When the database is the bottleneck, adding VMs does not necessarily increase throughput; it can overwhelm the database faster.
- If traffic has predictable scheduled peaks, consider **scaling schedules** or pre-warming capacity ahead of peak hours.
- MIG autoscaling has **limitations** with stateful configurations; do not apply stateless autoscaling assumptions to stateful MIGs without reviewing those constraints.

**Distinction:** autoscaling changes the **VM count**; autohealing replaces **unhealthy VMs** to maintain the group; rolling updates change the **configuration version**. These mechanisms can occur simultaneously and must be monitored separately.

## 9. Autohealing: replacing unhealthy VMs

A MIG can be configured with **application-based autohealing**. An appropriate HTTP/HTTPS/TCP health check evaluates application health; when a VM remains persistently unhealthy, the MIG can **repair it by recreating** that VM.

~~~text
MIG VM is created from template
      ↓
OS boots, startup script runs, Java application becomes ready
      ↓
Health check probes /healthz
  ├── HEALTHY   → VM is kept
  └── UNHEALTHY → MIG replaces VM per autohealing policy
      ↓
New VM is created from template and checked again
~~~

### Autohealing health checks differ from load balancing health checks

| Health check | Goal | Sensitivity |
|---|---|---|
| **Load balancer health check** | Determine whether a backend should receive traffic right now | Can probe rapidly and strictly |
| **MIG autohealing health check** | Determine whether a VM should be replaced | Should generally be more conservative to avoid recreate loops |

**Using the exact same health check for both can cause adverse effects** if thresholds are too aggressive or the application takes time to boot. For example, if a backend needs 120 seconds for JVM startup, having the load balancer temporarily withhold traffic makes sense, whereas autohealing recreating the VM after 15 seconds prevents the application from ever completing startup.

### Creating an HTTP health check

~~~bash
HC="mig-app-health"

gcloud compute health-checks create http "$HC" \
  --port=80 \
  --request-path=/healthz

gcloud compute health-checks describe "$HC"
~~~

For the MIG, go to **Compute Engine → Instance groups → MIG name → Edit → Instance lifecycle and autohealing**, select the health check, and configure an appropriate **Initial delay** (e.g., 180 seconds after verifying boot duration). Enable autohealing only after verifying the endpoint and firewall rules. Autohealing policies can also be configured via API/IaC; the older `gcloud beta ... set-autohealing` command emits a deprecation warning in the CLI, so avoid using it as the default example.

**Key lesson:** health checks should test **the application's own ability to serve**. However, avoid making the check overly dependent on an external service or a globally failing database, as doing so can trigger continuous VM recreation loops across the entire group when the fault is not on the VMs.

### Initial delay and firewall rules

The initial delay gives a VM time to finish booting before failed health checks trigger repairs. Ensure:

- The VM startup script and application actually listen on the probed port and path.
- Firewall rules allow the **health-check probe IP ranges** corresponding to the load balancer/health check type.
- The initial delay covers image pulls, Java warmup, non-blocking migrations, and cache loading.
- The failure threshold is reasonable to avoid resetting VMs over transient network jitter.

Do not enable autohealing across production before verifying that the health check works cleanly on a test group first.

## 10. Combining a regional MIG with a load balancer

A **regional MIG** manages VMs across zones; an **Application Load Balancer** receives client requests, selects an eligible backend, and forwards traffic to healthy VMs. For a stateless Java web/API tier, the typical architecture is:

~~~mermaid
flowchart TD
    A["Users / Cloud DNS"] --> B["External Application Load Balancer"]
    B --> C["Backend service"]
    C --> D["Regional MIG: us-central1"]
    D --> E["Zone a: VM1, VM2"]
    D --> F["Zone b: VM3, VM4"]
    D --> G["Zone c: VM5, VM6"]
    E --> H["Shared Database or Storage"]
    F --> H
    G --> H
~~~

Architectural deployment steps:

1. Configure the startup script/image so every VM is ready to serve the same API version.
2. Configure the service port and MIG **named port** if required by the backend service type, such as `http:80`.
3. Create the backend service and load balancer health check; attach the MIG as a backend.
4. Create the URL map, frontend, TLS certificate, and forwarding rule for the chosen load balancer type.
5. Allow only required proxy/health check sources to reach VMs via firewall rules; omit direct public IPs on VMs unless required.
6. Point Cloud DNS to the load balancer's frontend IP.
7. Test normal traffic, single-VM failure, and the impact of a zone outage in a controlled drill.

Example of setting a named port:

~~~bash
gcloud compute instance-groups managed set-named-ports "$REGIONAL_MIG" \
  --region="$REGION" \
  --named-ports=http:80
~~~

This command **does not create a load balancer**. Backend services, health checks, firewall rules, and certificates must be configured separately. If Cloud Armor is used, it protects requests **passing through the backend service where the policy is attached**; it does not protect direct access paths bypassing the load balancer.

### Designing for single-zone failure tolerance

Suppose a regional MIG has 6 VMs split evenly 2-2-2, and one VM sustains 100 RPS under load testing in specific conditions. If zone A fails, 4 VMs remain in zones B and C, providing roughly 400 RPS of reference capacity. If live demand at that moment is 500 RPS, the application **can still become overloaded** even though the regional MIG remains operational.

Therefore, plan for **overprovisioning** or spare capacity:

- Set the minimum VM count high enough for the remaining zones to carry critical load if one zone goes down.
- Ensure databases, load balancers, and caches are not single points of failure.
- Account for regional/zonal CPU quotas and instance capacity when the autoscaler attempts to replace lost VMs.
- Design API request idempotency, bounded retries, circuit breakers, and graceful shutdown.

**A regional MIG does not guarantee zero recovery time.** Health checks, VM provisioning, warmup, and cache population take time; service continuity depends on remaining capacity.

## 11. Rolling updates: controlled rollout of new versions

A MIG runs template `web-template-v1`. When the team releases Java application v2, create a **new instance template** rather than manually editing individual VMs.

~~~text
Template v1 → Running MIG
      ↓
Build v2 image/release + template v2
      ↓
Verify rollout policy and quotas
      ↓
Incrementally replace some v1 VMs with v2 VMs
      ↓
Health checks OK → proceed to next batch
      ↓
All VMs across zones updated
~~~

Key options:

| Parameter | Meaning | Consequence |
|---|---|---|
| `maxSurge` | Number of extra VMs above target size allowed during update | Speeds up rollout, but requires extra quota and incurs cost |
| `maxUnavailable` | Number of VMs allowed to be unavailable during update | Lower values reduce disruption, but slow down the rollout |
| `minimalAction` | Minimum disruption level applied to VMs | May refresh, restart, or replace depending on what changed |
| `replacementMethod` | Strategy for creating replacement VMs | May generate new VM names or recreate while preserving names where supported |
| `proactive / opportunistic` | Proactively update all VMs or update only when triggered/recreated | Affects rollout timing and risk exposure |

Example of starting a rolling update on a regional MIG:

~~~bash
NEW_TEMPLATE="web-template-v2"

gcloud compute instance-groups managed rolling-action start-update \
  "$REGIONAL_MIG" \
  --region="$REGION" \
  --version="template=$NEW_TEMPLATE" \
  --type=proactive \
  --max-surge=3 \
  --max-unavailable=0
~~~

Combining `maxUnavailable=0` with `maxSurge>0` aims to preserve serving capacity during VM replacement. However, if quota or capacity is insufficient to create surge VMs, the rollout may stall. Some update types or stateful groups also impose restrictions on these options. Always **inspect managed instance statuses and errors**, rather than assuming an accepted command means deployment is complete.

Before a production rolling update:

1. Test the v2 image/template in dev or staging.
2. Verify the application supports both versions running concurrently during the transition.
3. Ensure health checks and readiness configurations are stable.
4. Validate quota for `maxSurge` in each zone.
5. Monitor HTTP 5xx rates, latency, CPU, logs, and business metrics throughout the rollout.
6. Retain the old template/image so you can initiate a **rollback** to the previous version.

With certain target distribution shapes, **two-version canary updates are not supported**; consult the documentation for your shape before planning a canary. If you roll back, the MIG must replace VMs once again; rollback is not instantaneous, and local VM data can still be lost.

## 12. IAM permissions, networking, and security

A team deploying MIGs typically needs the following permission groups:

| Task | Permissions/roles to review | Notes |
|---|---|---|
| Create templates, MIGs, resize, update | Compute Engine permissions on `instanceTemplates` and `instanceGroupManagers`, commonly included in `roles/compute.instanceAdmin.v1` | Restrict to project or resource scope |
| Use a service account on VMs | `iam.serviceAccounts.actAs`, e.g., `roles/iam.serviceAccountUser` on the specific service account | Do not grant across all service accounts |
| Use a Shared VPC subnet | Network User or equivalent permission on the assigned subnet | The MIG must be authorized to use the target network |
| Create health checks, backend services, firewalls | Required Compute/Network Admin permissions | Separate LB operators from app deployers |
| Access Artifact Registry/Secret Manager | Read roles on exact target resources for the **VM runtime identity** | Never embed tokens in startup scripts |
| View status, logs, metrics | Appropriate Viewer/Monitoring/Logging permissions | Maintain proper log retention and access controls |

**Distinguish execution identities:** the VM's service account, the identity creating the MIG, and the CI/CD deployment service account may all be **different**. A user allowed to create VMs does not automatically have permission to read application secrets, and the runtime service account should not have permissions to modify MIGs or project IAM unless required.

At the network layer:

- Omit external IPs on VMs when they do not need to accept direct external requests.
- Use firewall rules allowing only appropriate health check/proxy/load balancer sources; never open `0.0.0.0/0` as a temporary troubleshooting shortcut.
- If bootstrapping needs to download packages, configure Cloud NAT or an approved path to internal repositories/Google APIs.
- Store business data in databases or Cloud Storage; never store secrets or critical data on boot disks subject to recreation.
- Check Organization Policies and region/machine-type constraints; having IAM permission does not guarantee VM creation complies with org policies.

## 13. Operational observability and troubleshooting

For MIGs, monitor both **group state** and **application state**, because a group at its target size may still contain VMs that are not serving requests.

### Read-only inspection commands

~~~bash
# View configuration and target size.
gcloud compute instance-groups managed describe "$REGIONAL_MIG" \
  --region="$REGION"

# List VMs in each zone and their current action status.
gcloud compute instance-groups managed list-instances "$REGIONAL_MIG" \
  --region="$REGION"

# List all MIGs in the project.
gcloud compute instance-groups managed list

# View autoscaler configuration if enabled.
gcloud compute autoscalers list
~~~

For a regional MIG, the autoscaler is a regional resource; use appropriate filters/describe flags to avoid confusing zonal and regional autoscalers. You can also inspect operations and Audit Logs for VM creation failures, rolling update errors, permission issues, or configuration changes.

### Key metrics to monitor

| Metric | Condition to detect |
|---|---|
| **Target size vs. RUNNING/healthy VMs** | Group targets 6 VMs but only 4 are created |
| **VM distribution by zone** | Shape is no longer balanced as designed, or a zone is degraded |
| **Current action: creating/recreating/verifying** | VM provisioning speed and updater behavior |
| **CPU/memory, request rate** | Rising load and autoscaling demand |
| **HTTP 5xx, latency, SLO** | Application is overloaded even as VM count grows |
| **Health check status and repair count** | VMs stuck in a recreate loop due to misconfiguration |
| **Quota/stockout errors** | Autoscaler targets a higher count, but the zone is out of capacity |
| **Boot/readiness duration** | Slow instance startup degrading scale-out responsiveness |
| **VM-hours, disk, network, LB/Logging cost** | Spend exceeding forecast during autoscaling or surge updates |

MIGs can display instance distribution metrics across zones and machine types in the Console, which is especially helpful when using `BALANCED`, `ANY`, or instance flexibility. Cloud Monitoring/Logging supports building dashboards, alerts, and investigations.

### Troubleshooting table

| Symptom | Possible cause | First check |
|---|---|---|
| Cannot create MIG | Invalid template, missing IAM, wrong zone/region | Operation error details and Compute Engine permissions |
| MIG created with fewer VMs than target | Quota, capacity, subnet IPs, unavailable machine type | List instances, zonal quota/stockout errors |
| Regional MIG not evenly split | `BALANCED/ANY` shape, redistribution disabled, zone capacity shortage | `targetDistributionShape` and zonal distribution |
| VMs constantly recreated | Health check port/path mismatch, firewall blocking probes, slow startup | Health status, boot logs, initial delay |
| VMs RUNNING but LB returns 502/503 | Load balancer health check, firewall, named port, or app not ready | Backend health, named ports, and application status |
| Autoscaler not adding VMs | CPU below target, max replicas or quota reached | Autoscaler configuration and metrics |
| Autoscaler scales in too early | Stabilization/scale-in settings, bursty workload, missing drain | Review metric history and scaling policy |
| Rolling update stalled | Insufficient surge quota, broken new image, VMs unhealthy | Update status, VM errors, startup script logs |
| VMs lose files after update | Data stored on stateless instance boot/temp paths | Storage architecture, backups, and stateful policy |
| Sudden billing spike | High min replicas, surge VMs, disk/network/LB/Logging usage | Billing by SKU, MIG size, and policies |

A common pitfall: a team updates a startup script to run a Java API, and the script tries to pull from an Internet package registry while the VMs have no external IP and the VPC lacks Cloud NAT. VMs spin up and fail initialization; autohealing repeatedly replaces them without fixing the root cause. The fix is inspecting boot logs, egress networking, and artifact availability—**not** raising `maxReplicas`.

## 14. Costs and zonal headroom planning

A MIG does not mean "free extra machines." Total cost depends on VM compute, persistent disks, network traffic, load balancers, image builds, logging/monitoring, and dependent services. An autoscaler aligns resources with demand, yet **minimum replicas** and failover headroom still carry ongoing costs.

Estimation model:

~~~text
Monthly cost
  ≈ total VM-hours × machine type unit price
  + boot/persistent disks
  + network egress / inter-zone transfer where applicable
  + load balancing / external IPs / health-check usage where applicable
  + logging, monitoring, and supporting services
~~~

| Decision | Benefit | Cost / trade-off |
|---|---|---|
| 3-VM zonal MIG | Simple, fewer VMs | Zone outage can take down the entire service |
| 6-VM regional MIG (2-2-2) | Distributed across multiple zones | More baseline VMs required for redundancy |
| `minReplicas=6`, `maxReplicas=18` | Scales when traffic grows | Minimum cost of 6 VMs; up to 18 VMs at peak |
| `maxSurge=3` during updates | Preserves capacity during rollout | Temporarily billed for up to 3 extra VMs |
| `BALANCED` shape | Resilient when a zone lacks capacity | Uneven distribution; requires reviewing policies |
| Fast-boot optimized image | More responsive scale-out | Requires maintaining an image build/patch pipeline |

Do not blindly provision 100% extra headroom for every scenario. Use **traffic forecasts + load tests + SLOs** to calculate minimum VMs needed to survive a single-zone failure. For example, across three zones, if full critical load must be served when one zone fails, capacity in the **remaining two zones** must handle that critical load; otherwise, raise `minReplicas`, shed load, or route traffic elsewhere per business continuity plans.

Configure **Cloud Billing budgets/alerts**, track costs by project/labels, and check regional pricing for Compute Engine, disks, and load balancing. Budget alerts **do not automatically stop an autoscaler**; use `maxReplicas` and quotas to cap scale, while monitoring non-MIG cost drivers separately.

## 15. Scenario: A Java API that must stay available during a zone outage

An e-commerce company wants to run its `orders-api` service on Compute Engine. Traffic fluctuates hourly; the application accesses Cloud SQL and Cloud Storage; the company requires that a single-zone outage does not take the entire API offline.

### Option A: Zonal MIG

- 4 VMs in `us-central1-a`.
- Includes autoscaler, autohealing, and a load balancer.
- Simple to create and maintain; handles single-VM failures.
- **Risk:** if all of zone A goes down, every VM is affected; autoscaling and autohealing within the **same zone** do not eliminate that risk.

### Option B: Regional MIG

- 6 VMs distributed across `us-central1-a/b/c` with shape `EVEN`.
- Minimum 6, maximum 18 VMs based on CPU or appropriate serving capacity.
- External Application Load Balancer distributes HTTP traffic to healthy VMs.
- Autohealing replaces failed VMs; the updater rolls out new templates with surge/unavailable limits.
- Cloud SQL is configured with appropriate HA, and Cloud Storage uses the required location/consistency; the application does not store sole session state on VMs.
- Cloud Monitoring tracks HTTP SLOs, backend health, zonal distribution, and costs.

**Conclusion:** when the primary requirement is single-zone fault tolerance, a **regional MIG** is typically more appropriate than a single zonal MIG. However, choosing a region also involves user latency, data residency, data transfer costs, and machine type availability. To survive a full regional outage, the business must design **multi-region deployments**, not merely add more VMs to one regional MIG.

### Quick decision table

| Question | Recommendation |
|---|---|
| Test environment where zone outage is acceptable? | Start with a zonal MIG |
| Production web/API requiring single-zone fault tolerance? | Regional MIG, typically `EVEN` or `BALANCED` based on capacity |
| Batch workload prioritizing capacity/reservations over zone balance? | Regional MIG with `ANY` where suitable |
| Job requiring VMs in one zone for low inter-VM latency? | Consider `ANY_SINGLE_ZONE` and accept zone outage risk |
| Database with data that must survive VM recreation? | Design dedicated storage/HA; do not default to a stateless MIG |
| Recovery required if an entire region fails? | Multi-region architecture with multiple MIGs/backends and a failover strategy |

## 16. Design and deployment checklist

- [ ] Determined whether the workload is stateless or requires stateful configuration.
- [ ] Selected zonal or regional MIG based on single-zone fault tolerance requirements.
- [ ] For regional MIGs, selected the zone list accurately from the start.
- [ ] Target distribution shape matches capacity, availability, and workload type.
- [ ] Verified machine types, images, subnets, quotas, and reservations across target zones.
- [ ] Templates are versioned, startup scripts log properly, and secrets are never embedded in disks/metadata.
- [ ] Runtime and deployment pipeline service accounts follow least privilege.
- [ ] Autoscaler has appropriate `minReplicas`, `maxReplicas`, scaling signals, and initialization period.
- [ ] Autohealing uses a sufficiently conservative health check, initial delay, and proper firewall rules.
- [ ] Load balancer health check, named ports, and backend service are verified.
- [ ] Planned single-zone failover so **remaining capacity** covers critical traffic.
- [ ] Rolling updates have surge quota, health verification, rollback plan, and monitoring.
- [ ] Logs/metrics track target size, VM health, zone distribution, 5xx rates, latency, and cost.
- [ ] Cleanup plan in place to stop/delete lab resources and avoid unexpected charges.

**Hands-on exercise:** A team deploys a Java API on Compute Engine with an expected peak of 900 RPS across three zones in one region. Load testing shows each VM reliably handles about 150 RPS at the target CPU utilization while the database is healthy. Tasks:

1. Explain why a 6-VM zonal MIG does not meet the single-zone fault tolerance requirement.
2. Propose the **minimum VM count for a regional MIG** so that if one of the three zones goes down, the remaining two zones still handle 900 RPS under these assumptions; show your math and headroom margin.
3. Choose `EVEN` or `BALANCED` when `e2` machines occasionally face capacity shortages in one zone, and explain the trade-off.
4. Write the `gcloud` commands to create the regional MIG from a template and enable CPU autoscaling with reasonable min/max values.
5. Design the health endpoint, autohealing initial delay, and a separate load balancer health check.
6. Choose `maxSurge` and `maxUnavailable` for a v2 release, state the extra quota required, and describe the rollback approach.
7. List the dashboards/alerts and cost sources that must be monitored.
8. If the entire region goes offline, explain why a regional MIG is insufficient and what architectural additions are needed.

*Calculation hint:* with even distribution across three zones and each VM serving 150 RPS under the stated assumptions, at least 6 healthy VMs are needed **in the remaining two zones** when one zone fails. With an even 3-3-3 split, losing one zone leaves 6 VMs; thus the team might consider a baseline minimum of 9 VMs for this idealized scenario, while adding extra margin for jitter, rollouts, health checks, quotas, and database bottlenecks. Actual capacity must be validated through load testing and failure drills.

## Official references

- [Managed instance groups overview](https://cloud.google.com/compute/docs/instance-groups) — MIGs, autoscaling, autohealing, and updates.
- [Basic scenarios for creating MIGs](https://cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances) — choosing models and limits.
- [Create a zonal MIG](https://cloud.google.com/compute/docs/instance-groups/create-zonal-mig) — Console/CLI operations.
- [Create a regional MIG](https://cloud.google.com/compute/docs/instance-groups/distributing-instances-with-regional-instance-groups) — creating multi-zone groups.
- [About regional MIGs](https://cloud.google.com/compute/docs/instance-groups/regional-migs) — fault tolerance, distribution, and limitations.
- [Regional MIG target distribution shapes](https://cloud.google.com/compute/docs/instance-groups/regional-mig-distribution-shape) — EVEN/BALANCED/ANY/ANY_SINGLE_ZONE.
- [Set target distribution shape](https://cloud.google.com/compute/docs/instance-groups/regional-mig-set-target-distribution-shape) — CLI flags and redistribution constraints.
- [Set up autohealing](https://cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs) — health checks and initial delay.
- [Automatically apply configuration updates](https://cloud.google.com/compute/docs/instance-groups/rolling-out-updates-to-managed-instance-groups) — rolling updates, surge, and unavailable settings.
- [Autoscaling managed instance groups](https://cloud.google.com/compute/docs/autoscaler) — CPU/metric/schedule scaling and scale-in controls.
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) — VM, disk, and related cost components.
