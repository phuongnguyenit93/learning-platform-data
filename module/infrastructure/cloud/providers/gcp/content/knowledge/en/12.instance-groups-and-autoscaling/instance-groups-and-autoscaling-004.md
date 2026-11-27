# Autohealing and health check design for MIGs

> **Chapter:** Instance Groups and Autoscaling  
> **Module:** CLOUD_PROVIDERS_GCP

A Java application running on Compute Engine can encounter a situation where **the VM is still RUNNING, yet the application has hung**: the process stops accepting connections, thread pools are wedged, or the service stops returning valid responses. If you only monitor VM status, the operations team may fail to detect the outage in time. With a **Managed Instance Group (MIG)**, Google Cloud can use an **application-based health check** to evaluate each VM and **automatically recreate unhealthy VMs**, returning the group to its desired size and configuration. This mechanism is called **autohealing**.

In the **CLOUD_PROVIDERS_GCP** module, learners study Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases—learning through deployment scenarios how to select services, secure resources, automate releases, and track reliability alongside cost. This lesson in the **Instance Groups and Autoscaling** chapter focuses on designing reliable health checks, configuring autohealing policies, monitoring repairs, and preventing recreate loops that degrade availability.

After this lesson, you can:

1. Distinguish between **MIG repair**, **application-based autohealing**, **autoscaling**, **rolling updates**, and **load balancer health checking**.
2. Choose a health endpoint that reflects failures requiring **VM replacement**, without confusing it with readiness for **receiving traffic**.
3. Design `check interval`, `timeout`, `healthy/unhealthy thresholds`, and **initial delay** based on measured startup duration.
4. Configure Google Cloud health checks, firewall rules, and autohealing policies for zonal or regional MIGs.
5. Interpret `HEALTHY`, `UNHEALTHY`, `TIMEOUT`, `UNKNOWN` states and instance current actions.
6. Analyze scenarios involving misconfigured health checks, unready apps, failing external dependencies, overload, and excessive VM repairs.
7. Design a runbook incorporating observability, validation, rollback, and balancing cost against SLOs.

## 1. Managed Instance Groups and the role of autohealing

A **Managed Instance Group (MIG)** is a group of VMs managed by Compute Engine according to an **instance template** and group settings such as target size, distribution, update policy, autoscaler, or autohealing policy. A MIG can be **zonal** (in a single zone) or **regional** (distributed across multiple zones in a region per configuration).

A MIG provides two distinct mechanisms:

- **Repair of VMs with infrastructure failures or unexpected stops**: the MIG works to maintain its target size by recreating failed or missing VMs. This baseline mechanism **does not require an application health check**.
- **Application-based autohealing**: the administrator attaches a **health check** to the MIG. If the application on a VM is evaluated as unhealthy per policy, the MIG can **recreate** that VM. This is an application-layer recovery signal, not merely a hypervisor-layer signal.

~~~mermaid
flowchart LR
  T["Instance template\nImage / startup / service account"] --> MIG["Managed Instance Group\nTarget size = 3"]
  MIG --> VM1["VM-1\nHealthy"]
  MIG --> VM2["VM-2\nHealthy"]
  MIG --> VM3["VM-3\nApp hung"]
  HC["Application health check"] -. "Probes each VM" .-> VM1
  HC -. "Probes each VM" .-> VM2
  HC -. "Probes each VM" .-> VM3
  HC --> RULE{"VM-3 Unhealthy\nafter initial delay?"}
  RULE -- "Yes" --> REPAIR["MIG repair / recreate VM-3"]
  REPAIR --> MIG
~~~

### 1.1. What "recreate" really means

When autohealing repairs an unhealthy VM, the MIG typically **deletes and recreates the instance** using the MIG-managed configuration. This is **not** a "restart Java application" button, nor does it guarantee preserving local VM state.

Consequences:

- Processes and in-memory sessions disappear.
- Local SSD/ephemeral data and unsaved manual edits can be lost.
- Disks, IPs, metadata, and state that must survive can only rely on **stateful MIG/preserved state** policies or appropriate external storage services, within product limits.
- The new VM must execute its startup script, fetch configuration, register with services, and pass health checks.
- If the defect lives in the **instance template** or a new release, the replacement VM can hit the **exact same error** and enter another replacement cycle.

**Design principle:** Workloads suited for autohealing should be **replaceable at the VM level** without losing data or corrupting transactions; place durable state in Cloud SQL, Cloud Storage, Memorystore, or appropriately designed data stores. If a workload maintains VM-local state, understand the capabilities and limits of **stateful MIGs** before enabling repairs.

### 1.2. Zonal vs. regional MIG

| Scope | Capability | Limitation |
| --- | --- | --- |
| **Zonal MIG** | Repairs instances within one zone; easy for labs, lower complexity | Cannot keep operating if the **entire zone** becomes unavailable |
| **Regional MIG** | Can distribute instances across multiple zones in a region, reducing single-zone failure risk | Does not replace multi-region architecture; still depends on regional services and capacity |
| **MIG + Load Balancer** | Provides a stable frontend and routes traffic away from unhealthy backends | Backend service/health check/firewall rules must be accurate; LB does not store app state |
| **MIG + Autoscaler** | Scales VM count according to load | Adding VMs does not fix bugs or hung processes; bounded by quotas and startup time |

A regional MIG is a key building block for **high availability**, yet minimum VM count, distribution, LB backends, databases, and application fault tolerance determine the end result. A regional MIG with only one instance provides no meaningful redundancy.

## 2. Distinguishing autohealing, autoscaling, load balancing, and rolling updates

This is one of the most common areas of confusion when designing a self-healing system.

| Mechanism | Primary decision | Effect on VMs | Goal |
| --- | --- | --- | --- |
| **Autoscaling** | Should capacity be added/removed based on CPU, LB serving capacity, metrics, or schedule? | Changes the MIG's **target size** | Match capacity to load and cost |
| **Load balancer health check** | Should this backend **receive new requests**? | Usually removes unhealthy backends from traffic, **does not recreate VMs** | Protect user experience quickly |
| **MIG application health check + autohealing** | Is this VM broken enough to **require replacement**? | MIG actively recreates unhealthy VMs | Restore application health/capacity |
| **Baseline MIG repair** | Did the VM suffer an infrastructure failure or unexpected stop/loss? | Recreates VMs to maintain target size | Keep the group intact |
| **Rolling update** | Should a new template/version be rolled out across VMs? | Replaces or updates VMs per update policy | Controlled release rollout |

**Google Cloud recommends separating health checks for load balancing and autohealing.** A load balancer needs fast decisions so it **stops sending requests** to an unready instance. Autohealing takes a heavy action: **recreating a VM**. Thus, the autohealing signal should be **conservative, stable, and fail only when replacing the VM actually helps**.

~~~mermaid
flowchart TD
  USER["Client request"] --> LB["Cloud Load Balancer"]
  LBC["LB health check\nReadiness: fast and sensitive"] --> LB
  LB --> VM1["VM-1 serving"]
  LB --> VM2["VM-2 temporarily drained from traffic"]
  AHC["MIG autohealing health check\nLiveness: conservative"] --> MIG["MIG controller"]
  MIG --> VM1
  MIG --> VM2
  VM2 -. "If error persists without recovery" .-> MIG
  MIG -. "Recreates when needed" .-> VM2
~~~

### 2.1. Example of why the two checks differ

Suppose a Java VM can respond to HTTP requests while its Cloud SQL connection pool is still initializing.

- **Readiness for Load Balancer:** returns **503** until it can process transactions, allowing the LB to route requests to other VMs.
- **Liveness for autohealing:** continues returning **200** while the Java process, HTTP server, and core background workers remain alive. A few seconds of Cloud SQL hiccups do not mean the VM needs to be destroyed and recreated.
- If event loops/thread pools deadlock, the server stops answering probes, or the process crashes persistently, **liveness fails**, and the MIG recreates the VM after thresholds are met.
- When a new VM boots, **initial delay** gives the application time to finish startup before failed checks trigger recreation.

Using **the exact same database-dependent check** for both LB and autohealing means a brief Cloud SQL outage can cause **every VM to be recreated simultaneously**, worsening the incident and wasting money.

### 2.2. Autohealing does not fix every failure

| Scenario | Can autohealing help? | What else is needed? |
| --- | --- | --- |
| Java process crashes and does not recover | Usually yes, if probes detect it | Lower MTTR, reliable startup scripts |
| Deadlock causes app to stop answering health endpoint | Potentially yes | Design probes that reflect process hang |
| VM stops unexpectedly | Handled by baseline MIG repair | IAM, auditing, restricting out-of-band VM edits |
| Sudden traffic spike while VMs remain healthy | Does not add capacity | Autoscaling and workload optimization |
| Shared Cloud SQL/VPC/DNS outage | Recreating VMs usually **does not help** | Dependency HA/DR, timeouts, retries, circuit breakers |
| Buggy new release affecting every VM | Usually **does not help** | Version/template rollback, canary, rollout controls |
| Entire zone/region unavailable | Cannot resolve alone | Regional/multi-region HA architecture |
| Memory leak recurring every few hours | Recreation may ease symptoms | Fix the leak, track metrics, rate-limit repairs |
| DB record mid-processing on a VM | Recreation can cause loss or duplicate processing | Idempotency, queue acks, persistent state |

## 3. Designing a good health check endpoint

A **health check** is the criteria Google Cloud probes apply to each backend VM: protocol, port, request path, check interval, timeout, and healthy/unhealthy thresholds. Health checks for MIGs should clearly distinguish **liveness** from **readiness**.

### 3.1. Liveness vs. readiness vs. startup

| Signal type | Question | Appropriate decision |
| --- | --- | --- |
| **Liveness** | Is the process/application still functioning meaningfully? | Signal for **autohealing** |
| **Readiness** | Can the VM **accept new requests right now**? | Signal for **load balancing** |
| **Startup/initialization** | Has the application finished booting? | Sizing **initial delay** and startup logic |
| **Business health/SLO** | Are users completing transactions? | Monitoring, alerting, SRE review, rollback |
| **Dependency health** | Are DB, cache, queue, and Google APIs working? | Readiness or telemetry; fail liveness only when justified |

**Never use a bare HTTP 200 on "/" as your sole health definition.** A homepage may return 200 while internal workers are dead; conversely, an endpoint querying every external dependency can fail during a shared outage that VM recreation cannot fix.

### 3.2. Principles for an autohealing endpoint

1. **Lightweight, fast, and deterministic:** avoid heavy DB queries, disk scans, external service calls, or long resource locks.
2. **Side-effect free:** health checks must never INSERT, DELETE, or enqueue messages.
3. **Reflects failures fixable by recreation:** such as hung processes, unresponsive listeners, or unrecoverable local instance state.
4. **Exposes no secrets:** never print tokens, internal configs, or user info in responses.
5. **Network-reachable on the VM:** bind the app to the proper network interface IP (or `0.0.0.0`) on the probe port; never listen solely on `127.0.0.1`.
6. **Returns accurate status codes:** HTTP success per health check config when healthy; 5xx or no response when genuinely unhealthy.
7. **Separate observability:** log state transitions; avoid logging every individual probe if it risks flooding Cloud Logging.
8. **Respect graceful shutdown/idempotency:** recreation must not corrupt transactions or duplicate work.

### 3.3. Example endpoint contract for a Java application

Suppose a Java Spring Boot application runs in the instance template, listening on port **8080**, exposing two endpoints:

~~~text
GET http://<VM_INTERNAL_IP>:8080/internal/health/live
  - 200: HTTP server and core components are alive
  - 503/timeout: process or local components are unrecoverable

GET http://<VM_INTERNAL_IP>:8080/internal/health/ready
  - 200: application is ready to accept business requests
  - 503: warming up, draining, or critical dependencies unready
~~~

You can use **Spring Boot Actuator liveness/readiness probes** once the dependency is added and the respective health groups are enabled for your framework version. Do not assume an arbitrary Java app already exposes these paths: implement them, test manually, and define return conditions explicitly.

Illustrative pseudo-controller (**not complete production code**):

~~~java
// Illustrates endpoint contract; requires real Spring wiring and dependencies.
@GetMapping("/internal/health/live")
ResponseEntity<String> liveness() {
    // Do not query DB or external services in liveness.
    return ResponseEntity.ok("live");
}

@GetMapping("/internal/health/ready")
ResponseEntity<String> readiness() {
    return applicationAcceptsNewTraffic()
        ? ResponseEntity.ok("ready")
        : ResponseEntity.status(503).body("not ready");
}
~~~

This example only verifies that web request threads can respond. If the application runs background workers requiring deadlock detection, design a reliable **local progress** signal; do not turn the endpoint into a fan-out check across all dependencies that adds load or causes cascading failures.

**Warning:** An endpoint unconditionally returning 200 can mask a process still serving HTTP whose core business logic has stalled. An endpoint failing over brief DB hiccups is overly sensitive. Match the signal to the workload and test safely with fault injection.

### 3.4. Protocols and ports

Google Cloud supports **non-legacy health checks** including HTTP, HTTPS, TCP, and SSL/TLS under corresponding conditions, in both global and regional scopes.

- For **HTTP**, commonly probes `GET /internal/health/live` on port 8080, expecting a configured success status code.
- For **HTTPS**, requires TLS handshake and certificate/SNI setup if applicable; check product limits and probe reachability.
- For **TCP**, verifies only that a TCP handshake succeeds; insufficient to confirm application logic health.
- For non-HTTP services, consider a local health adapter reflecting application state without disrupting business traffic.
- Documentation distinguishes **modern health checks** from legacy `http-health-checks`/`https-health-checks`. Use modern health checks for new deployments unless compatibility dictates otherwise.

Never bind the health endpoint solely to loopback `127.0.0.1`, as external probes from Google infrastructure cannot reach the guest OS loopback interface.

## 4. Configuring check timing and recovery thresholds

These parameters balance **fast failure detection** against **avoiding false repairs**:

| Parameter | Meaning | Example for autohealing |
| --- | --- | --- |
| `check-interval` | Frequency of probes sent to an instance | `30s` |
| `timeout` | Maximum wait for a single probe response | `10s` |
| `healthy-threshold` | Consecutive successful probes to transition to healthy | `2` |
| `unhealthy-threshold` | Consecutive failed probes to transition to unhealthy | `3` |
| `initial-delay` | VM startup window during which MIG ignores initial failures | `300s` for an app taking ~4 minutes to boot |

These values are **learning samples**, not universal defaults for every app. Google recommends conservative autohealing health checks: `unhealthy-threshold` **greater than 1** (commonly **3 or more**), and `timeout` generous enough for normal response latency while never exceeding `check-interval`.

### 4.1. Understanding initial delay accurately

**Initial delay** is the time the MIG gives a new VM to finish booting, running its startup script, and initializing the application. Key details:

- Allowed range is **0 to 3600 seconds**.
- Per documentation, the **Console** may default to **300 seconds**, whereas the **API/CLI if omitted** may default to **0 seconds**. **Always specify it explicitly.**
- The timer starts when the VM's `currentAction` in the MIG transitions to **`VERIFYING`**, not simply when the operator clicks Create.
- During this window, the MIG **ignores failed health check results**, preventing premature recreation during warm-up.
- **If probes report healthy before initial delay expires**, the MIG treats initialization as complete and may end the grace window early.
- This is **not** a fixed pause that forces waiting the full 300 seconds before routing traffic. The LB uses its own readiness health check to control traffic delivery.

~~~mermaid
sequenceDiagram
  participant M as MIG controller
  participant V as New VM
  participant H as Autohealing probe
  M->>V: Create VM from template
  V-->>M: RUNNING
  M->>V: currentAction = VERIFYING
  Note over M: Start initial delay
  H->>V: GET /internal/health/live
  V-->>H: Timeout while app is booting
  H-->>M: Unhealthy
  Note over M: Ignore failure during initial delay
  H->>V: Retry probe after startup
  V-->>H: HTTP 200
  H-->>M: HEALTHY
  M-->>V: currentAction = NONE
~~~

### 4.2. Estimating detection time without mistaking it for an SLA

With a 30s interval and unhealthy threshold of 3, three consecutive failures span **at least two interval cycles** plus probe/timeout duration and scheduling jitter; never promise "exactly 90 seconds." Health checks run across distributed probers and involve observation/control latency.

Approximate timing budget:

~~~text
T_detect  ≈ time across consecutive probes + timeout/observation delay
T_repair  ≈ detection + MIG queue + recreate VM + boot + app warmup
T_restore ≈ repair + LB readiness + client retry / connection recovery
~~~

To minimize user impact, let the **load balancer drain/reroute traffic first** before autohealing recreates the VM. Never lower `unhealthy-threshold` to 1 chasing an "ultra-low RTO" if it triggers false positives and unnecessary VM churn.

### 4.3. Measure warmup time instead of guessing

1. Sample multiple VM creations from the same template in the target zone and machine type.
2. Record timestamps from the `instances.insert` operation to the first healthy probe result.
3. Capture **p95/p99** or real worst-case timing including image pulls, startup scripts, config loading, and app initialization.
4. Pick an `initial-delay` comfortably above the measured stable duration, with safety margin.
5. Whenever a new version slows boot time, adjust based on new measurements before rolling out.

For example, if p95 startup ≈ 160s and p99 ≈ 220s, `initial-delay=300s` can be sensible in a lab. However, if an app hangs immediately at startup and **never turns healthy**, the MIG waits out this entire window before acting; an overly long initial delay slows recovery of genuinely broken VMs.

### 4.4. Stabilization limits and monitoring startup delay

Per published Google Cloud documentation, after configuring a health check, **it can take up to ~10 minutes** before autohealing begins monitoring instances in the MIG. Seeing a new VM in `UNKNOWN` or `UNHEALTHY` during initial verification **does not immediately prove misconfiguration**.

MIGs also enforce stability guardrails when multiple VMs fail simultaneously:

- At any given time, a MIG tries to repair at most **30% of the VMs per zone**, **rounded up**.
- If a zonal MIG has only one VM, or a regional MIG has one VM in a zone, that single VM can still be repaired.
- If an instance keeps failing across repeated repairs, the MIG applies exponential backoff between attempts, up to **roughly 60 minutes**.
- When a majority of instances appear unhealthy, the MIG may pause further repairs to avoid wiping out remaining capacity simultaneously.

**Do not treat the 30% concurrent repair limit as an application SLO.** It is a MIG-layer safety cap; if 60% of VMs fail from a shared bad config, the group can still lose enough capacity to drop traffic.

## 5. Lab deployment layout

We assume an **existing instance template** running a web app listening on HTTP port **8080** at `/internal/health/live`. This walkthrough attaches a health check to a **zonal MIG in a lab project**. Do not attach policies to production MIGs before verifying firewall rules and health endpoints.

| Resource | Example value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Zone | `asia-southeast1-a` |
| Region | `asia-southeast1` |
| VPC | `lab-vpc` |
| Subnet | `lab-subnet` |
| Instance template with app | `web-v1-template` |
| MIG | `web-autoheal-mig` |
| Network tag on template/VMs | `autoheal-web` |
| Global health check | `web-autoheal-hc` |
| VPC firewall rule | `allow-web-autoheal-probes` |
| HTTP liveness endpoint | `/internal/health/live` |
| Port | `8080` |
| Health check interval / timeout | `30s` / `10s` |
| Healthy / unhealthy thresholds | `2` / `3` |
| MIG initial delay | `300s` |

**Lab prerequisites:**

- Compute Engine API enabled; billing and quotas approved for VMs, disks, networking, and health checks.
- Least-privilege IAM permissions to create health checks, update MIGs, and manage firewall rules/templates.
- `web-v1-template` **genuinely installs and starts the application**; its startup script or image is complete and verified on a standalone VM if needed.
- VPC/subnet and network tag exist; IP/CIDR ranges do not conflict with organization policies.
- A designated owner monitoring the test and **an approved lab window** so production is unaffected.
- A rollback plan if the health check is misconfigured; logging and compute costs are accepted.

**Permission scope:** `compute.healthChecks.create`, `compute.healthChecks.use`, `compute.instanceGroupManagers.update`, and relevant firewall/network permissions are examples to verify. Common roles include `roles/compute.networkAdmin`, `roles/compute.securityAdmin`, and `roles/compute.instanceAdmin.v1` depending on task; never grant project-wide `Owner` as a "quick fix" for IAM errors.

### 5.1. Why does the lab assume the template already contains the app?

An instance template specifying only a blank Debian image **does not magically include** an HTTP server on port 8080. Creating a MIG from a blank template and enabling autohealing causes every probe to time out and triggers endless VM recreation, testing the wrong thing.

Two ways to prepare:

1. Use a **golden image** bundling the application and a reliable startup service.
2. Use a **startup script** in the instance template to install and launch the app from a pinned artifact/version; private VMs need Private Google Access, Cloud NAT, or an internal mirror to fetch dependencies.

Once deployed, **test the endpoint on a single VM from that template first** before wiring the health check to autohealing.

### 5.2. Testing the application from inside a VM

From a test VM in the same VPC/subnet with reachability to the app, run:

~~~bash
# Read-only commands, run from guest OS or an authorized host reaching the VM IP
curl --connect-timeout 3 --max-time 10 \
  -i http://127.0.0.1:8080/internal/health/live

# If network probes hit the internal IP, test that exact IP directly:
curl --connect-timeout 3 --max-time 10 \
  -i http://VM_INTERNAL_IP:8080/internal/health/live

# Check Linux service/listener
ss -lntp | grep ':8080'
~~~

**Expected result:** HTTP 200 on the **internal IP**, not just `127.0.0.1`. If the app runs locally yet refuses connections on the network interface IP, Google health checks will fail.

## 6. Creating a health check for autohealing

### 6.1. Console

1. Open [Google Cloud Console → Health checks](https://console.cloud.google.com/compute/healthChecks).
2. Click **Create health check** and name it `web-autoheal-hc`.
3. Select **Global** scope for this example (regional health checks are also supported when appropriate for the architecture).
4. Set protocol **HTTP**, port **8080**, and request path **`/internal/health/live`**.
5. Set `check interval=30s`, `timeout=10s`, `healthy threshold=2`, `unhealthy threshold=3`.
6. Review and create the health check. **Do not attach it to a MIG yet** until firewall rules and probe paths are verified.

**Global vs. regional scope:** Regional health checks can reduce cross-region dependencies and support data-residency boundaries; global checks are convenient when MIGs across regions share one health check. Choose based on architecture and regional support, not simply because "global" sounds "more available."

### 6.2. Google Cloud CLI

The following command creates a **global HTTP health check** for autohealing. This **modifies infrastructure**—run only in an authorized lab:

~~~bash
gcloud compute health-checks create http web-autoheal-hc \
  --port=8080 \
  --request-path=/internal/health/live \
  --check-interval=30s \
  --timeout=10s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3 \
  --global \
  --project=LAB_PROJECT_ID
~~~

Read back to verify (read-only):

~~~bash
gcloud compute health-checks describe web-autoheal-hc \
  --global \
  --format="yaml(name,type,checkIntervalSec,timeoutSec,healthyThreshold,unhealthyThreshold,httpHealthCheck)" \
  --project=LAB_PROJECT_ID
~~~

**Meaning:** Creating this resource does not repair any VMs yet. Only after a **MIG** references it in an autohealing policy configured with a repair action can results trigger instance recreation.

### 6.3. Firewall rules allowing health check probes to reach VMs

Google Cloud autohealing documentation specifies the IPv4 probe source ranges:

~~~text
130.211.0.0/22
35.191.0.0/16
~~~

Allow **only port 8080** from these ranges to the MIG's VMs. In our custom lab VPC, use a **network tag** to restrict scope:

~~~bash
gcloud compute firewall-rules create allow-web-autoheal-probes \
  --network=lab-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=130.211.0.0/22,35.191.0.0/16 \
  --target-tags=autoheal-web \
  --enable-logging \
  --project=LAB_PROJECT_ID
~~~

This rule takes effect immediately and may interact with existing firewall policies. **Include the `autoheal-web` tag in the instance template** before creating the MIG; without the tag, the rule **will not apply** to the VMs.

If your VPC uses hierarchical or network firewall policies, check whether higher-priority deny rules block probes. For IPv6 health checks or load balancer types with distinct probe sources/paths, check [health check probe sources](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts) for your backend type instead of blindly copying these two IPv4 CIDRs.

**IP range pitfall:** `35.235.240.0/20` is for **IAP TCP forwarding**, **not** the two IPv4 health check probe ranges above. Allowing only the IAP range leaves health checkers unable to reach your VMs.

Inspect the rule:

~~~bash
gcloud compute firewall-rules describe allow-web-autoheal-probes \
  --format="yaml(network,direction,allowed,sourceRanges,targetTags,priority)" \
  --project=LAB_PROJECT_ID
~~~

### 6.4. Why allow probes before enabling repair?

If a firewall blocks probes, even healthy VMs actively serving traffic report `TIMEOUT`/`UNHEALTHY`. Enabling autohealing immediately causes the MIG to **delete and recreate healthy VMs**, which also hit `TIMEOUT` in an endless loop. Before modifying production policies, verify probe paths, firewall logs, and listening ports/addresses.

### 6.5. Handling authenticated health endpoints

MIG health checks do not act like end users carrying arbitrary JWT or IAM tokens. Avoid requiring login flows, redirecting to auth pages, or checking session cookies on probe endpoints.

A sound design is a **liveness endpoint containing no sensitive data**, returning simple status codes and restricted via firewall exclusively to Google probe ranges. If mTLS/TLS or zero-trust policies are mandatory, verify protocol compatibility for your health check type and design a compliant adapter—never open a port to the public Internet just to make probes pass.

### 6.6. Sharing limits for health checks

Per current documentation, **one health check can be applied to at most 50 MIGs**. If your organization manages more, create multiple health checks; generally separate them by workload type, port/protocol, and sensitivity. Do not reuse one shared health check across APIs and workers with different bootstrap durations or liveness criteria.

## 7. Attaching the autohealing policy to a Managed Instance Group

### 7.1. Safe approach: observe before enabling repair

If a MIG is already serving traffic, never attach a new health check and enable immediate VM replacement in one step. A lower-risk rollout flow:

1. Test the endpoint on a standalone VM with the same image/config.
2. Verify firewall probe ranges, port, and network tag.
3. Create a dedicated health check for autohealing.
4. **Attach the health check in monitor-only mode without repairs** using `--action-on-vm-failed-health-check=do-nothing`.
5. Observe `HEALTH_STATE` across all VMs over an adequate window, including peak load and rolling updates if applicable.
6. Eliminate false positives by tuning intervals, timeouts, and initial delay.
7. Only once signals are stable, enable `repair` for workloads safe to recreate.

**Key distinction:** Setting `do-nothing` stops repairs **triggered by the application health check**. Baseline repairs for **failed VMs** and group lifecycle controls still depend on `defaultActionOnFailure`/lifecycle policies. Do not treat `do-nothing` as disabling all MIG management.

### 7.2. Creating a new zonal MIG in observe-first mode

Example using the **app-ready instance template** `web-v1-template`, network tag `autoheal-web`, and HTTP listener on 8080:

~~~bash
# CREATES RESOURCES: run in an approved LAB project
gcloud compute instance-groups managed create web-autoheal-mig \
  --base-instance-name=web-autoheal \
  --template=web-v1-template \
  --size=3 \
  --zone=asia-southeast1-a \
  --health-check=web-autoheal-hc \
  --initial-delay=300 \
  --action-on-vm-failed-health-check=do-nothing \
  --project=LAB_PROJECT_ID
~~~

**Why not enable repair immediately?** Because initially you have not confirmed that the health check accurately reflects app health across every instance. This mode still reports health states for verification.

If `web-v1-template` is a **regional template** instead of global, use the appropriate resource URL per CLI documentation; the example above assumes a global template. VMs inherit VPC/subnet settings from the template; MIG commands do not rewire VM networking.

After confirming accurate health states across several cycles and load testing, enable autohealing:

~~~bash
# UPDATES POLICY: may trigger VM RECREATION when unhealthy
gcloud compute instance-groups managed update web-autoheal-mig \
  --zone=asia-southeast1-a \
  --action-on-vm-failed-health-check=repair \
  --project=LAB_PROJECT_ID
~~~

**Never enable `repair` in production** without maintenance/change approval, monitoring, and a rollback plan. A faulty health check can replace multiple VMs, disrupt sessions, and degrade application capacity.

### 7.3. Applying to an existing MIG

If a MIG already exists without a health check, attach the health check and initial delay with repairs disabled first:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --health-check=web-autoheal-hc \
  --initial-delay=300 \
  --action-on-vm-failed-health-check=do-nothing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

After sufficient observation and approval:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=repair \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

For a **regional MIG**, replace `--zone=ZONE` with `--region=REGION` and verify health check scope. A regional health check can also be referenced by its regional resource path when needed—never assume every MIG must use a global health check.

### 7.4. Configuring in the Console

1. Open [Compute Engine → Instance groups](https://console.cloud.google.com/compute/instanceGroups/list).
2. Select the target MIG and confirm **project**, **zone/region**, instance template, and VM count.
3. Click **Edit** → expand **Instance lifecycle and autohealing**.
4. Select the created **Health check**; enter `Initial delay` based on bootstrap measurements.
5. Under **On failed health check**, select **No action** initially to observe.
6. Save and monitor VM statuses and health checks.
7. Once verified, switch the action to repair per change-management procedures.

Exact button labels in the Console may change over time. Always verify the health check target port/path and action behavior before clicking Save.

### 7.5. One policy per MIG

A MIG supports **one autohealing policy** pointing to **one health check**. You may attach separate health checks for load balancers/backend services, but you cannot stack multiple autohealing policies onto a single MIG to probe DB, cache, queue, and HTTP separately.

If an application has multiple subsystems, design a health endpoint that aggregates **only the local signals required** for deciding VM recreation, while exposing granular metrics on separate dashboards.

## 8. Reading states, actions, and repair indicators

### 8.1. Read-only commands

~~~bash
# MIG details and autohealing policy
gcloud compute instance-groups managed describe web-autoheal-mig \
  --zone=asia-southeast1-a \
  --format="yaml(name,targetSize,autoHealingPolicies,instanceLifecyclePolicy,status)" \
  --project=LAB_PROJECT_ID

# Each instance and its current health state
gcloud compute instance-groups managed list-instances web-autoheal-mig \
  --zone=asia-southeast1-a \
  --project=LAB_PROJECT_ID

# List MIGs in the project
gcloud compute instance-groups managed list \
  --project=LAB_PROJECT_ID

# Health check parameters
gcloud compute health-checks describe web-autoheal-hc \
  --global \
  --project=LAB_PROJECT_ID

# View recorded repair operations (filtered by operation type)
gcloud compute operations list \
  --filter='operationType~compute.instances.repair.*' \
  --project=LAB_PROJECT_ID
~~~

For regional MIGs, pass `--region=REGION` to describe/list-instances. Repair operations record historical actions, not necessarily root application causes; correlate with service logs and metrics to understand why a health check failed.

### 8.2. `HEALTH_STATE` values

| State | Meaning documented by Google Cloud | How to handle |
| --- | --- | --- |
| `HEALTHY` | VM is reachable and health endpoint meets health check criteria | Confirm readiness, SLOs, and workload metrics are also healthy |
| `UNHEALTHY` | VM is likely reachable, but response fails criteria | Check HTTP status/path, app logs, local dependencies |
| `TIMEOUT` | Cannot connect or endpoint fails to answer before timeout | Check firewall, listener, port, VPC, CPU/threads |
| `UNKNOWN` | Health checking system has not yet determined VM status | Wait for monitoring startup; check config or signal loss |
| `DRAINING` | VM is draining and not accepting new connections per process | Inspect MIG/LB operations; do not assume app crash immediately |

New VMs may appear `UNHEALTHY` **before being verified healthy**; interpret that state alongside `initial-delay` and `currentAction`. When `UNKNOWN`, the MIG **does not repair immediately**, avoiding misguided replacements while signals are not yet established.

### 8.3. Current actions and MIG stability

A VM in a MIG can transition through:

~~~text
CREATING -> VERIFYING -> NONE
                          |
                          +-- Health becomes UNHEALTHY/TIMEOUT
                          v
                       RECREATING
                          |
                          +-- New VM: CREATING -> VERIFYING -> NONE
~~~

This is a **conceptual diagram**, not an exhaustive list of all API states/actions in every scenario.

- `CREATING`: MIG is creating the instance.
- `VERIFYING`: VM is running; MIG is verifying health/initialization.
- `NONE`: no active MIG lifecycle operation on that VM.
- Failure-triggered recreations appear in **current action**, operations, and audit logs.

At the group level, `status.isStable` exists. This flag **does not simply mean "every health check returns 200"**: a MIG undergoing autoscaling, redistribution, or rolling updates will also report unstable. Inspect **target size, current actions, health states, template versions, and backend health** together.

### 8.4. Health state change logs and investigation records

Compute Engine can emit **health state change logs** by default whenever an instance's health state transitions. Use Logs Explorer to:

1. Filter by project, group/instance name, and incident timeframe.
2. Correlate timestamps: startup, health state transitions, MIG repair operations, and when the app began serving.
3. Determine whether failures started right after changing templates, firewalls, IAM/service accounts, or health check settings.
4. Compare recreation counts against HTTP 5xx rates, p95/p99 latency, and remaining LB traffic capacity.
5. Alert on **repair rate**, **unhealthy instances**, and **MIG not stable**, not just VM CPU.

Logs can incur Cloud Logging charges beyond free tiers depending on retention and volume. Avoid logging full probe payloads or application secrets.

## 9. Safe validation workflow before enabling production repair

A health check can **look valid** in the Console yet trigger false positives under real traffic. Split validation into three layers.

### 9.1. Static configuration check

- Correct **project/VPC**, subnet/region/zone, and instance template network tags.
- Listener actually running on the declared port and path.
- VPC ingress firewall allows **both IPv4 probe ranges** to the intended target.
- No hierarchical firewall policy blocking probes.
- Health endpoint returns expected status (no login prompts, redirects, or 404s).
- Health check global/regional scope matches architecture.
- Initial delay exceeds real bootstrap time with safety margin.
- Autohealing and load balancing health checks are separated if differing sensitivities are needed.
- MIG has enough instances/zones to maintain service during repairs.

### 9.2. Observing in `do-nothing` mode

~~~text
Step 1: Attach health check + action=do-nothing
     ↓
Step 2: Inspect HEALTH_STATE for all VMs
     ↓
Step 3: Run test traffic (separate readiness/LB)
     ↓
Step 4: Inspect logs as new VMs boot / app starts
     ↓
Step 5: Explain every TIMEOUT/UNHEALTHY event
     ↓
Step 6: If false positives occur -> fix endpoint/thresholds/firewall
     ↓
Step 7: Sufficient evidence -> approve action=repair
~~~

Enable repair only after health signals prove trustworthy. For large fleets, validate on a **canary MIG/lab group** before applying the policy across production.

### 9.3. Controlled fault injection in the lab

**Execute only on test MIGs with clear ownership. Never inject faults into production.**

| Test case | Expected behavior | What to observe |
| --- | --- | --- |
| App returns 200 on internal IP | VM evaluated as healthy | HEALTH_STATE, time to healthy |
| App returns 503 during initial boot | Not prematurely recreated during initial delay | `currentAction=VERIFYING`, timing |
| Stop app service on **one lab VM** | Recreated after thresholds if repair is enabled | Operations, instance ID, startup logs |
| Force endpoint to return 503 for a few seconds | Not recreated before unhealthy threshold is reached | Probe logs, threshold |
| Block probes via rule in isolated lab | Shows `TIMEOUT` and risk of false recreation | Firewall logs, repair rate |
| External dependency fails while liveness stays 200 | No mass recreation if app can self-recover | LB readiness, app errors, dependency SLO |
| New template boots slower | Is initial delay still sufficient? | p95 startup, recreation count |
| One VM repairs under high load | Does LB retain enough healthy backends? | Error rate, backend capacity |

**Do not block firewall probes across all running VMs** just to prove autohealing works. That induces cascading repairs and does not reflect real application failures.

### 9.4. Properly simulating a service failure

If your lab VM runs a Linux service named `demo-java.service` inside the MIG, you can simulate a failure **on one lab VM you own** after recording its instance name:

~~~bash
# Run inside the chosen lab VM, only with approved fault-testing permission:
sudo systemctl stop demo-java.service
~~~

This is an **intentional disruption command**. When autohealing is enabled, the MIG may recreate the VM rather than waiting for you to restart the service. If you need to recover manually before the MIG acts, you may run `sudo systemctl start demo-java.service` within the test window, though recovery before repair thresholds trigger is not guaranteed. Observe instance states and logs rather than guessing exact timings.

Do not use `gcloud compute instances stop VM_NAME` to simulate an **application health failure**: directly stopping a MIG-managed VM triggers **failed-VM repair**, testing a completely different mechanism.

## 10. Special scenarios and trade-offs

### 10.1. Whole group turns unhealthy due to a Cloud SQL outage

Suppose every Java VM calls Cloud SQL. If the liveness endpoint runs `SELECT 1` against the DB and fails when DB connectivity drops, the entire MIG turns unhealthy simultaneously. Mass recreation causes:

- Loss of active in-flight sessions.
- Connection storms as all VMs boot and reconnect at once.
- Slower DB recovery.
- An endless repair loop across the whole group even though the root fault isn't on the VMs.

**Better design:** Liveness checks local recoverability; LB readiness reflects ability to serve requests, while dependency monitoring alerts separately. If the app cannot serve due to a DB outage, **remediate the DB and use fallbacks**—don't destroy VMs by default.

### 10.2. High CPU / brief stop-the-world GC pauses

Under heavy load, a Java VM may respond several seconds slower due to GC pauses, CPU throttling, disk I/O, or saturated thread pools. With a 1s timeout and unhealthy threshold of 1, the MIG may misread transient slowness as permanent failure.

Evidence-based tuning:

- Measure p99 response time of the health endpoint under peak load.
- Set `timeout` safely above p99, while **never exceeding `check-interval`**.
- Set `unhealthy-threshold` to at least 3, per Google's guidance.
- Ensure the health endpoint **is not queued behind heavy business requests**.
- Address capacity shortages via CPU/autoscaler/Cloud Monitoring; reserve autohealing for unrecoverable instances.

### 10.3. Initial delay too short and recreate loops

An app takes 4 minutes to pull images, register, and warm caches, yet `initial-delay=60s`. Probes receive 503, the MIG declares it unhealthy, and recreates the VM. No VM ever lives long enough to turn ready.

Remediation:

1. Temporarily switch **health check action to `do-nothing`** if a repair loop is occurring.
2. Inspect startup logs, listening ports, HTTP status codes, and actual boot duration.
3. Adjust `initial-delay` and optimize the startup script if needed.
4. Launch a canary VM from the updated template to verify stability.
5. Re-enable repair only after the endpoint consistently turns healthy within measured bounds.

### 10.4. Initial delay too long

An 1800s window can mask a VM that **never finishes booting** for 30 minutes. While this reduces false positives, it greatly delays detection and recovery of real failures.

Balance this: size the delay from the workload's startup time distribution, and **never** crank it up to 3600s just to "stop seeing errors" when the true cause is a firewall rule or wrong port.

### 10.5. Bad template and "repair storms"

A new template ships a broken startup script or buggy app version uniformly across all VMs. Autohealing merely replaces broken VMs with more VMs running the exact same broken template; you must **roll back the template/version** per release policy. When many instances fail, the 30%/zone repair cap and backoff limit blast radius, **but cannot fix a broken template**.

Investigation steps:

- Compare template/version on unhealthy VMs vs. healthy VMs.
- Correlate release timestamps, image digests, and startup script diffs.
- Temporarily pause health-check repairs if needed to preserve logs for analysis.
- Roll back the release or fix startup config via the **MIG-managed workflow**.
- Avoid manually patching individual VMs outside the MIG as a permanent fix.

### 10.6. Interaction between repair and update policies

MIGs track template/version changes, and during repairs can either **retain each instance's original configuration** or **apply the newer target configuration**, depending on **force update on repair** and update policy. Per current CLI documentation, **update on repair is off by default**; forcing updates to the current template during repairs requires explicit opt-in and risk evaluation.

Never use autohealing as an uncontrolled "rolling deploy" mechanism. Rollouts belong under update policies, canaries, `maxSurge`/`maxUnavailable`, and proper LB/application health checks.

### 10.7. Stateful MIGs, storage, and transactions

If VMs store data on boot/local disks without state preservation, recreation loses data. With **stateful MIGs**, preserved disks/IPs can be configured within feature limits, yet the application must still handle:

- In-flight transactions, idempotency, and duplicate messages.
- Disk attachment and filesystem recovery time.
- Application locks and instance identity changes.
- DB/storage RTO/RPO, quotas, and dependencies.
- Zonal outages rendering zonal disks unavailable.

**Autohealing only promises best-effort VM recreation**—it does not provide backups, transaction recovery, or data consistency.

### 10.8. Liveness returns HTTP 200 while the real app is broken

A process can keep answering 200 on its health endpoint while all queue workers are deadlocked. To prevent false-healthy states:

- Emit a **local progress** signal from critical workers (e.g., updating an in-memory heartbeat timestamp).
- Fail liveness if the heartbeat stalls beyond a reasonable threshold.
- Never fail liveness simply because an external queue is empty/full or an external service blips.
- Emit detailed logs and metrics so operators distinguish local hangs from dependency outages.

A good health check **precisely defines when recreation is required**, rather than being "a GET route that always returns OK."

## 11. Symptom-based troubleshooting

| Symptom | Possible causes | Verification and remediation |
| --- | --- | --- |
| VM RUNNING, yet `TIMEOUT` | Firewall blocking probes, no listener, bound to loopback, wrong port, network policy | Test IP/port from another VM; check firewall probe ranges and logs |
| `UNHEALTHY` while app serves traffic | Liveness path returning 404/302/401/500; health check expects another status | Check actual HTTP response, health check port/path config |
| All VMs turn unhealthy right after policy attach | Shared firewall, missing template tag, missing health endpoint, DB dependency failure | Switch to `do-nothing`; fix shared root cause before re-enabling repair |
| New VMs continuously recreated during startup | Initial delay too short or broken startup script | Measure boot time; tune delay or fix template |
| `UNKNOWN` longer than expected | Monitoring newly enabled, lost health signal, or unusual permissions/config | Check elapsed time, health check config, and MIG status |
| VM unhealthy, yet not repaired | `do-nothing` mode, inside initial delay, 30% cap, backoff, or operation errors | Check autohealing policy, `currentAction`, and operations |
| Continuous repairs bring no improvement | Fault in template, config, release version, or shared dependency | Roll back and fix root cause rather than treating symptoms |
| LB reports backend unhealthy while MIG shows HEALTHY | LB readiness is stricter than autohealing liveness | May be intentional design; verify SLAs and metrics |
| MIG HEALTHY, yet users see 5xx | Overly simplistic health check, DB error, LB config, or networking | Inspect request metrics, traces, and dependencies |
| After rollout, group shows `isStable=false` | Update, autoscaling, creation, or repair still in progress | Inspect MIG `currentAction`, `targetSize`, and versions |
| Only one zone repairs repeatedly | Zonal issue, capacity shortage, divergent template/network | Inspect distribution, quotas, and underlying operations |
| Health check logs missing | Logging disabled, missing IAM, or ingestion delay | Check Logging config and health state change logs |
| Port opened only to IAP; health check always times out | IAP range differs from Google probe ranges | Allow `130.211.0.0/22` and `35.191.0.0/16` on probe port |
| Private VMs fail to download artifacts during repair | Missing Cloud NAT, Private Google Access/PSC, or IAM | Test startup dependencies from a standalone VM using same template |
| Repairs cause state loss | Sessions or files stored non-durably | Move state off VMs or design a stateful MIG |

**Short diagnostic workflow:**

~~~mermaid
flowchart TD
  S["MIG has unhealthy VMs"] --> A{"Is action=repair enabled?"}
  A -- "No" --> M["Observe, fix health endpoint/config"]
  A -- "Yes" --> P{"Inside initial delay?"}
  P -- "Yes" --> W["Wait for boot/health, measure timing"]
  P -- "No" --> H{"UNHEALTHY or TIMEOUT?"}
  H -- "TIMEOUT" --> NET["Check firewall, IP, listener, port, timeout"]
  H -- "UNHEALTHY" --> APP["Check HTTP response, app logs, dependencies"]
  NET --> R{"Same failure across all VMs?"}
  APP --> R
  R -- "Yes" --> SYS["Check release, VPC, DB, shared config;\navoid repair storm"]
  R -- "No" --> ONE["Inspect individual instance: memory, GC, disk"]
  SYS --> FIX["Apply controlled config fix or rollback"]
  ONE --> FIX
~~~

## 12. Safely disabling or adjusting autohealing

When a new health check triggers a recreate loop, **do not manually delete VMs** or reflexively shrink `targetSize`. Identify the root cause and take the least disruptive action.

### 12.1. Temporarily pause health-check repairs

~~~bash
# Policy change: pause application-based autohealing repairs
# while retaining the health check for observation (within approved scope)
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=do-nothing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

After fixing and re-observing, re-enable:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=repair \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

If you want autohealing to follow the MIG's default failure action, `default-action` can be used per current policy. **Do not confuse** `--action-on-vm-failed-health-check` with `--default-action-on-vm-failure`: they can be controlled independently.

### 12.2. Removing the health check from the autohealing policy

When removing a health check from a MIG under approved change control:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --clear-autohealing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

**Impact:** This removes the health check from the autohealing policy, stopping application health evaluation through that config. Never run this in production without adequate alternative monitoring.

### 12.3. Do not disable baseline MIG repair without reason

Google Cloud also provides `--default-action-on-vm-failure` to govern repairs when VMs fail unexpectedly. Setting it to `do-nothing` stops the MIG from automatically repairing infrastructure-failed VMs and, depending on `onFailedHealthCheck`, can also affect autohealing. This is a specialized option for controlled maintenance/workloads, not a default rollback for a buggy health endpoint.

## 13. Operational observability, SLOs, and cost

A sound autohealing strategy tracks **why** VMs were replaced, **how long users were impacted**, and **how much costs increased**.

### 13.1. Essential metrics and dashboards

| Signal | Purpose |
| --- | --- |
| VM count by health state | Track healthy vs. unhealthy share of capacity |
| Repair rate / duration | Spot repair storms and broken templates |
| Time from create to healthy | Tune `initial-delay` and catch startup regressions |
| `targetSize` vs. running instances | Verify capacity stability |
| `status.isStable` and current actions | Distinguish scaling, updating, verifying, and repairing |
| LB backend health and HTTP 5xx | Measure direct user impact |
| Request latency p95/p99 | Spot CPU/GC/IO issues and post-repair slowdowns |
| Autoscaler metrics | Separate capacity shortages from dead VMs |
| Cloud Logging/audit/Compute operations | Trace root causes and configuration changes |
| VM restarts/recreations by version | Detect repeatedly failing releases |
| Startup script / artifact retrieval failures | Diagnose new VMs failing to boot healthy |

Example alerts:

- Multiple instances entering `UNHEALTHY/TIMEOUT` consecutively within a few minutes.
- Repair operation rate exceeding normal baselines.
- Healthy LB backend ratio falling below SLO minimums.
- Boot-to-HEALTHY time increasing after a release.
- MIG remaining unstable unusually long with operation errors.
- Simultaneous repairs across multiple VMs paired with rising error rates.
- Region/zone lacking capacity to recreate instances.

### 13.2. Correlating logs with release events

When a repair loop appears, build a timeline:

| Time | Event | Evidence |
| --- | --- | --- |
| T0 | New image/template released | Deployment logs, version |
| T1 | VM created or updated | Compute operation |
| T2 | App starts and binds port | Guest OS logs |
| T3 | Health check changes state | Health state change logs |
| T4 | MIG triggers repair | Repair operation |
| T5 | New VM turns HEALTHY or fails again | `list-instances`, LB health |
| T6 | User-facing errors or normal traffic | HTTP metrics/traces |

The goal is determining **whether failures began before or after the release**, and whether the **app genuinely crashed** or the **health-check configuration is wrong**.

### 13.3. Cost control

Autohealing and logging have cost implications:

- Newly booted VMs re-download dependencies and generate network/disk/API operations.
- Replaced VMs produce operation logs, startup logs, and monitoring volume.
- Combined with an autoscaler, concurrent repairs and scale-outs can cause VM counts to fluctuate, raising Compute Engine bills.
- For stateful instances with slow boot/restore times, total downtime may exceed application-level recovery.
- Emitting health state change logs incurs Cloud Logging charges past free tiers depending on plan.

Optimizing cost **does not mean disabling autohealing** to save on logs. Instead, eliminate false-positive repairs, speed up startup, maintain clean templates, and set log retention/levels aligned with SRE, security, and financial needs.

## 14. Enterprise scenario: Java order API on a MIG

### 14.1. Context

A company operates an order system consisting of:

- A three-zone **Regional MIG** within one region.
- **Java Spring Boot** on VMs built from an instance template.
- An **External Application Load Balancer** serving HTTPS APIs.
- **Cloud SQL** storing order data.
- **Pub/Sub** for event processing.
- **Cloud Monitoring/Logging** tracking SLOs and errors.
- An **Autoscaler** scaling VM counts as traffic fluctuates.

During a promotion, one VM hits a worker thread deadlock while the other two keep running. The load balancer must stop routing requests to the failing VM quickly, while the MIG replaces it to restore full capacity.

~~~mermaid
flowchart TD
  CLIENT["Customers"] --> LB["External Application Load Balancer"]
  LB --> AZ1["VM Zone A healthy"]
  LB --> AZ2["VM Zone B unhealthy"]
  LB --> AZ3["VM Zone C healthy"]
  LBHC["LB readiness probe\nfast"] -. "Temporarily drain from traffic" .-> AZ2
  MIG["Regional MIG\nAutohealing liveness probe"] -. "Recreate after threshold" .-> AZ2
  AZ1 --> SQL["Cloud SQL"]
  AZ3 --> SQL
  AZ1 --> PUB["Pub/Sub"]
  AZ3 --> PUB
  MIG -. "Recreate from template" .-> NEW["VM Zone B replacement"]
~~~

### 14.2. Two selected health endpoints

| Endpoint | Criteria | Policy |
| --- | --- | --- |
| `/internal/health/ready` | App is ready for new requests; required dependencies within bounds | Faster LB check; temporarily removes backend from traffic |
| `/internal/health/live` | Process responds; core local workers alive | Conservative MIG check; replaces only on sustained failure |
| `/metrics` or other telemetry | HTTP errors, GC, worker lag, DB timeouts | Monitoring/alerting; do not wire every error into autohealing |

If Cloud SQL suffers a brief outage, readiness can fail to protect users while liveness remains healthy to avoid hammering the DB with VM restarts. If a Java process genuinely deadlocks and stops answering, autohealing replaces that VM.

### 14.3. Hypothetical incident analysis

| Indicator | Interpretation | Action |
| --- | --- | --- |
| One VM `TIMEOUT`, others healthy | Local VM/port/OS failure | Inspect logs; let autohealing repair if thresholds met |
| All VMs `UNHEALTHY` after release | Shared config/template defect | Halt repair storm; roll back release |
| LB unhealthy, MIG HEALTHY | Readiness stricter than liveness | Inspect dependencies, autoscaler, and LB capacity |
| VMs stuck in `VERIFYING` | Startup incomplete; image/config too slow | Inspect startup timeline; tune delay and template |
| App returns 5xx while health endpoints stay healthy | Endpoint misses business failure | Add metrics and refine health contract |
| Many VMs repaired simultaneously when DB goes down | Liveness improperly coupled to DB | Fix health contract; reduce coupling |

### 14.4. Measuring real outcomes

Do not declare success simply because "the MIG recreated a VM." Prove that:

- Users see fewer 5xx errors and timeouts when one VM hangs.
- Remaining backends carry sufficient capacity.
- Replacement VMs from the template **genuinely become ready**.
- Repairs do not cause duplicate orders or messages.
- Time-to-healthy stays within approved error budgets/SLOs.
- Shared dependency or release bugs do not trigger wasteful mass recreations.

## 15. Guided hands-on exercise

**Prerequisites:** Use an authorized lab project and an instance template running a real HTTP endpoint. If resource creation is restricted, complete the design and reasoning parts using hypothetical tables and answers.

### Part A — Design

1. Define the workload, mean/p95/p99 startup times, peak load, and plausible failure modes.
2. Specify the `/internal/health/live` and `/internal/health/ready` contracts, detailing HTTP 200/503 conditions.
3. Choose and justify `check-interval`, `timeout`, `healthy-threshold`, and `unhealthy-threshold`.
4. Choose `initial-delay` comfortably above p99 startup time within the 0–3600s range.
5. Plan firewall rules for probe source ranges and target network tags.
6. Choose zonal vs. regional MIG and minimum VMs to survive a single instance/zone failure.
7. Confirm stateless vs. stateful boundaries so critical data is not stored where recreation wipes it.

### Part B — Observe before repairing

1. Verify the health endpoint and firewall rules.
2. Create the health check.
3. Attach it to the MIG with `--action-on-vm-failed-health-check=do-nothing`.
4. Watch `list-instances` and logs over several cycles.
5. Run legitimate load or test traffic in the lab; confirm zero false positives.
6. Once approved, enable `repair`.

### Part C — Inject a single-instance fault in the lab

1. Record a healthy lab VM's name and `HEALTH_STATE`.
2. Stop the **application service on that lab VM**—do not run a Compute Engine VM stop command.
3. Track when `HEALTH_STATE` changes, when the MIG starts repair, and when a replacement VM appears.
4. Confirm the replacement VM uses the expected template and transitions to `HEALTHY`.
5. Confirm application recovery through the LB with no critical data loss.
6. Clean up the lab and stop/delete owned resources per policy.

### Part D — Results report

| Metric | What to record |
| --- | --- |
| VM creation → first healthy probe | Measured from logs/operations |
| Initial delay and rationale | Measured startup + headroom |
| Thresholds/interval/timeout | Applied configuration |
| Probe ports/source CIDRs | Firewall and access model |
| App failure → unhealthy | Observed duration |
| Unhealthy → repair operation | Observed duration |
| Repair → replacement HEALTHY | Observed duration |
| User-facing errors during test | HTTP errors/latency, if any |
| Data loss/duplicate processing | Evidence of idempotency |
| Incurred costs | VM boots/logs/network, if any |
| Open issues | Remediation and owner |

**Pass criteria:** Learners must do more than run commands—they must explain why liveness was chosen, why initial delay is required, why firewalls restrict to probe ranges, and why MIG healthy status alone does not guarantee application SLOs.

## 16. Thought exercises with answers

### Exercise 1 — DB-dependent liveness

Three VMs share Cloud SQL. Each VM's health endpoint runs `SELECT 1`. A 2-minute Cloud SQL hiccup causes all three checks to fail. Should you set `unhealthy-threshold=1` to recreate all three VMs immediately?

**Hint:** No. That is a **shared dependency failure**; recreating VMs will not heal the DB. Separate readiness, liveness, and DB monitoring, and apply timeouts, retries, and circuit breakers.

### Exercise 2 — Estimating timing

Suppose `check interval=30s`, `unhealthy threshold=3`, `timeout=10s`, and the VM is past `initial-delay`. After a sustained failure, will autohealing always begin at exactly 90s?

**Hint:** No. Timing depends on probe schedules, consecutive results, timeout/aggregation delays, and the MIG controller—plus queuing, repair, and startup. Budget an **approximate range**, measure via logs, and never promise exact timing.

### Exercise 3 — Boot cycle

A VM takes 240s to boot. `initial-delay=60s`, and the health check returns failures until the app is ready. The MIG keeps recreating VMs. How do you fix this?

**Hint:** Measure p95/p99 startup times, raise `initial-delay` based on data, confirm the endpoint/port and template work properly, and observe in `do-nothing` mode before enabling repair.

### Exercise 4 — Conflicting signals

The load balancer health check marks VM-A UNHEALTHY, yet MIG autohealing reports HEALTHY. Is this definitely misconfigured?

**Hint:** No. LB readiness may check whether the VM can accept new requests, while MIG liveness checks for local faults requiring replacement. Still, verify that this split is intentional and enough serving capacity remains.

### Exercise 5 — Repair limit

A zonal MIG has 10 VMs, and four turn unhealthy at once. Under the 30%/zone cap, how many VMs will the MIG attempt to repair concurrently at most?

**Hint:** 30% × 10 = **3 VMs** (rounded up per rule; equals 3), not necessarily all four immediately. For a regional MIG with 3 VMs per zone, at most roughly one VM per zone at a time in that example.

### Exercise 6 — Probe network path

A VM runs a web server on port 8080 bound only to `127.0.0.1`. `curl localhost:8080` returns 200. Can the MIG health check report healthy?

**Hint:** No, if Google probes target the internal IP where nothing is listening. Fix the listener binding and check firewall rules rather than tweaking thresholds.

### Exercise 7 — Why stopping a VM does not test application health checks

An operator runs `gcloud compute instances stop VM_NAME` and sees the MIG recreate the VM. Does that prove application autohealing works?

**Hint:** No. Baseline MIG repair for unexpectedly stopped/failed VMs operates **without** an application health check. To test autohealing, simulate a service failure inside a lab VM and watch health states and repair operations.

## 17. Production checklist for MIG autohealing

- [ ] Distinguished baseline MIG repair from application-based autohealing.
- [ ] Decided between zonal and regional MIG, minimum VM counts, and LB architecture.
- [ ] Instance template bundles apps, agents, and startup scripts capable of clean bootstrap.
- [ ] Critical data/sessions do not rely on ephemeral VMs or use an appropriate stateful policy.
- [ ] Autohealing health endpoint reflects **local failures fixable by recreation**.
- [ ] LB readiness health check separated if faster sensitivity is needed.
- [ ] Health check configured conservatively: failure threshold > 1, sensible timeout/interval.
- [ ] Initial delay sized from p95/p99 startup measurements and set explicitly.
- [ ] VPC firewall allows probe source ranges and ports to the proper target tag without over-exposing.
- [ ] No authentication or redirects causing Google probes to fail.
- [ ] Rolled out health check in `do-nothing` mode and observed long enough first.
- [ ] Dashboards, logs, and alerts cover health states, repair rate, and HTTP errors.
- [ ] Autoscaler, rolling updates, and repair policies do not conflict.
- [ ] Tested single-instance failure and verified traffic handling during repair.
- [ ] Rollback plan exists for health check/action changes and repair storms.
- [ ] IAM, quotas, disks, logging, networking, and costs budgeted.
- [ ] Runbook distinguishes single-VM failure, bad template, and shared dependency outage.

## 18. Official Google Cloud references

The following resources provide current documentation for MIG autohealing, application health checks, and lifecycle management. When deploying in production, verify current UI/CLI syntax alongside IAM, regional, and protocol requirements:

- [Set up an application-based health check and autohealing](https://docs.cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs) — creating checks, firewalls, initial delay, policies, health states, and repair rules.
- [About repairing VMs for high availability](https://docs.cloud.google.com/compute/docs/instance-groups/about-repair) — distinguishing failed-VM repair from application-based autohealing.
- [Instance groups overview](https://docs.cloud.google.com/compute/docs/instance-groups) — zonal/regional MIGs, autoscaling, load balancing, and health checking.
- [Monitor managed instance health state changes](https://docs.cloud.google.com/compute/docs/instance-groups/monitoring-managed-instance-health-state-changes) — health state change logs and measuring startup duration.
- [View information about MIGs and instances](https://docs.cloud.google.com/compute/docs/instance-groups/getting-info-about-migs) — `list-instances`, `currentAction`, `isStable`, and policies.
- [Turn off repairs in a MIG](https://docs.cloud.google.com/compute/docs/instance-groups/turn-off-vm-repairs-in-mig) — `default-action-on-vm-failure` and `action-on-vm-failed-health-check`.
- [Apply configuration updates during repairs](https://docs.cloud.google.com/compute/docs/instance-groups/update-on-repair) — retaining or updating templates/configs on repair.
- [Health checks overview](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts) — protocols, probe sources, and differences by load balancer/backend type.
- [Firewall rules for Cloud Load Balancing](https://docs.cloud.google.com/load-balancing/docs/firewall-rules) — probe and backend paths by LB type.
- [gcloud compute health-checks create http](https://docs.cloud.google.com/sdk/gcloud/reference/compute/health-checks/create/http) — HTTP health check syntax.
- [gcloud compute instance-groups managed create](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed/create) — creating MIGs and autohealing policies.
- [gcloud compute instance-groups managed update](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed/update) — updating health checks, actions, and initial delay.
- [Autoscaling managed instance groups](https://docs.cloud.google.com/compute/docs/autoscaler) — how autoscaling differs from autohealing.
- [High availability architecture on Google Cloud](https://docs.cloud.google.com/architecture/framework/reliability) — designing SLOs, HA, redundancy, and recovery.

**Key takeaway:** Autohealing is only effective when the **health check accurately measures failures fixable by recreating the VM**. Separate **load balancer readiness** from **MIG liveness**, base **initial delay** on real startup measurements, configure **accurate firewall rules and probe ranges**, observe in **`do-nothing`** mode first, and enable repair under controlled change management. Self-healing VMs do not replace database HA, stateless design, release rollbacks, or SLO monitoring.
