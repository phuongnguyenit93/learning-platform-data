# Warm-up, Cooldown, and Time-to-Ready for New Instances

## Lesson objectives

When a machine group or compute cluster scales out automatically, a new instance cannot serve traffic the moment the cloud provider reports it as running. The machine still needs to boot the operating system, complete bootstrap, fetch configuration and secrets, start the application, load required data, establish dependency connections, and pass health checks. For Java applications, JIT compilation and cache warming can also keep initial performance below steady state.

Warm-up and cooldown help the autoscaling system account for this delay. Misconfiguration can cause the autoscaler to underestimate or overestimate capacity, continuously launch extra instances, scale in prematurely, or route traffic to unready instances.

After this lesson, you will be able to:

- Distinguish launch, boot, bootstrap, application startup, and readiness times.
- Explain warm-up at the instance, application, and autoscaling controller layers.
- Distinguish cooldown from startup delay and stabilization windows.
- Design health checks, readiness gates, and traffic ramp-up.
- Measure time-to-ready for new machines using metrics and events.
- Choose warm-up and cooldown settings based on workload and scaling policy.
- Troubleshoot slow instance startups, failing health checks, and scaling oscillation.

## 1. Why cannot a new machine serve load immediately?

In the cloud, a VM launch or node-add command only initiates the resource lifecycle. The provider must allocate compute, attach networking and storage, and power on the machine; afterward, the guest OS and workload execute their own initialization steps.

An instance can be in a running state while the application is not yet ready to process requests. For example:

- Cloud-init or startup scripts are still installing packages and fetching configuration.
- Security, monitoring, or logging agents have not finished registering.
- The application is running schema migrations, loading models, or reading initialization data.
- A JVM is loading classes, JIT-compiling, and building connection pools.
- Caches are cold, making initial requests slower than normal.
- The load balancer has not yet marked the target healthy.
- Network routes, DNS, or service discovery have not propagated yet.

If the autoscaler counts the instance toward active capacity immediately upon VM creation, the system may assume capacity is sufficient while the new machine cannot handle requests. If traffic arrives too early, users experience timeouts and errors. If the autoscaler fails to account for time-to-ready, it may keep scaling out while newly launched machines are still booting, resulting in over-provisioning later.

## 2. Distinguishing lifecycle timing milestones

Measure each phase separately rather than lumping everything under a generic "startup time."

| Milestone | Meaning | Events to use |
|---|---|---|
| Provisioning | Provider allocates instance, NICs, volumes, and metadata | Create/launch request and instance state |
| OS boot | Firmware, kernel, and operating system start | Boot timestamp, cloud-init start |
| Bootstrap | Install agents, fetch config, secrets, certificates, and packages | Bootstrap start/end |
| Application startup | Application process starts, loads classes and config | Process start, application startup event |
| Dependency ready | Database pools, message brokers, DNS, or caches are ready | Connection pool initialized, dependency probes |
| Readiness | Instance is eligible to receive traffic | Readiness check passes |
| Traffic warm-up | Instance gradually ramps processing capability once receiving traffic | Request rate, latency, and error rate |
| Steady state | Performance and metrics reach normal operational baseline | SLOs, throughput, and resource baseline |

**Time to launch** usually measures only from the instance creation request until the cloud reports the machine is running.

**Time to ready** measures from creation start until the machine passes serving readiness criteria.

**Time to first successful request** measures until the first business request completes successfully.

These three metrics can differ substantially. For service autoscaling, time to ready and time to reach stable throughput matter far more than the running machine state.

~~~mermaid
flowchart LR
    A["Create instance"] --> B["Provisioning"]
    B --> C["OS boot"]
    C --> D["Bootstrap"]
    D --> E["Application startup"]
    E --> F["Dependency checks"]
    F --> G["Readiness passed"]
    G --> H["Receive traffic"]
    H --> I["Traffic warm-up"]
    I --> J["Steady state"]
~~~

## 3. What is warm-up?

Warm-up is the period a workload or instance needs to reach stable operational performance after startup or after beginning to receive traffic.

The term is used across several layers:

1. **Infrastructure warm-up:** the VM or node finishes booting and bootstrapping.
2. **Application warm-up:** the application finishes startup, class loading, pool initialization, and data preparation.
3. **Runtime warm-up:** the JVM, JIT compiler, caches, and runtime components reach steady performance.
4. **Autoscaling instance warm-up:** the period during which the autoscaling controller temporarily excludes a new instance's metrics from representing steady-state capacity, per platform rules.
5. **Traffic warm-up:** gradually increasing request volume sent to a new instance instead of sending full load immediately.

These intervals can overlap, yet they are not synonymous. An instance may pass readiness while still needing extra time to warm caches or JIT-compile code. Conversely, an instance may finish runtime warm-up before the load balancer adds it to the target group.

### 3.1. Warm-up is not a constant

Warm-up duration depends on:

- Instance type, CPU generation, storage, and networking.
- OS image, packages, agents, and startup scripts.
- Application size, dependencies, and data loaded at startup.
- JVM version, heap size, garbage collector, and JIT compilation level.
- Health of databases, brokers, registries, and secret services.
- Concurrent load, number of instances launching simultaneously, and API rate limits.
- Availability Zone, image caching, and underlying infrastructure state at launch time.

Therefore, do not pick a default warm-up number once and leave it forever. Measure across representative instance groups and releases, inspecting the p50, p95, and p99 distributions.

### 3.2. Example timeline

Suppose a web service takes the following times during a scale-out:

| Phase | Illustrative duration | Status |
|---|---:|---|
| Provision and OS boot | 35 seconds | VM booting |
| Bootstrap and agents | 25 seconds | Not receiving traffic |
| Application startup | 20 seconds | Process starting |
| Dependency/readiness | 10 seconds | Verifying serving conditions |
| Runtime/traffic warm-up | 30 seconds | Receiving controlled traffic |
| Total to steady state | 120 seconds | New capacity reaches expected level |

This is only an illustrative example, not a standard cloud timing. If the autoscaling controller uses 120 seconds for instance warm-up, verify which event starts the timer and which metrics are excluded during that window.

## 4. Application warm-up: what must finish

An application should have a startup sequence that clearly defines mandatory prerequisites before accepting requests.

Common tasks:

- Read and validate configuration.
- Retrieve secrets/certificates via the instance's assigned identity.
- Initialize thread pools and concurrency limits.
- Establish connection pools to databases or message brokers.
- Load required metadata, schemas, models, or lookup tables.
- Initialize background caches or precompute essential data.
- Register with service discovery and telemetry.
- Verify application compatibility with dependencies.
- Open the readiness endpoint once mandatory steps succeed.

Not every task has to block readiness. For example, loading secondary analytics data or warming non-essential caches can run in the background if the app serves safely on cache misses. Conversely, if requests require a mandatory ML model or schema, readiness should wait until that resource is ready.

### 4.1. Avoiding overly long startup scripts

Startup scripts should be minimal, repeatable, and time-bounded:

- Use pre-baked images to minimize package installation at boot.
- Pull artifacts using explicit versions or immutable digests.
- Avoid downloading unpinned dependencies from the public Internet on every scale-out.
- Use retries with backoff and an overall timeout cap.
- Log step-by-step so bootstrap failures are distinct from application failures.
- Never embed secrets in images or write them to logs.
- Ensure re-running the script does not duplicate configuration or resources.

If startup relies on package repositories or container registries, measure download times and handle slowdowns. A large scale-out can cause dozens of instances to pull artifacts simultaneously, saturating the very dependency they need to become ready.

### 4.2. JVM and JIT warm-up

For Java, the JVM may need time to:

- Load classes and initialize frameworks.
- JIT-compile hot methods.
- Populate connection pools and caches.
- Complete initial GC cycles.
- Accumulate execution profiles to optimize hot code paths.

If readiness opens immediately after the Spring context or `main` method finishes, the instance may still exhibit high latency on initial requests. Use a warm-up endpoint or synthetic requests to exercise critical code paths before taking live traffic.

Warm-up requests must be safe, produce zero business side effects, avoid writing dummy data to production, and never overload dependencies. If write paths must be exercised, use isolated test data or transactions designed to roll back.

Do not replay full production workloads just to warm up a single instance. Select a small, representative request set with strict concurrency caps and timeouts.

## 5. Readiness, liveness, and startup health checks

Different health checks serve different roles. Using the wrong probe can trigger restart loops or route traffic to unready machines.

| Check type | Question answered | Common action |
|---|---|---|
| Startup probe | Has the application finished its startup phase? | Allows extended startup without triggering liveness failures |
| Readiness probe | Can the application accept traffic right now? | Adds or keeps the target in the serving pool when passing |
| Liveness probe | Is the process still healthy and able to self-recover? | Restarts the process when an unrecoverable state is detected |

Readiness should reflect the application's ability to serve requests. It may verify mandatory dependencies, yet avoid hammering external systems on every probe. A briefly slow dependency could cause all instances to go `NotReady` simultaneously, widening the outage.

Liveness should check process or event-loop health enough to catch deadlocks or hangs. Never check external databases or third-party APIs in liveness probes, because a dependency outage would make Kubernetes restart every Pod continuously without fixing the root cause.

Startup probes protect slow-starting apps from premature liveness restarts. Readiness must still succeed before a Pod receives traffic through a Service.

### 5.1. Kubernetes probes example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api:2.1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

In this example:

- The startup probe gives the application up to roughly 180 seconds to finish initialization based on period and failure threshold.
- The readiness probe controls whether the Pod is eligible to receive traffic through the Service.
- The liveness probe detects when the process stops responding per configured criteria.

Tune these numbers to measured startup times. Health endpoints should never run heavy queries or produce side effects.

## 6. Autoscaling instance warm-up

Autoscaling needs to know how much capacity a new instance contributes and when. Right after an instance joins the group, its metrics may look unusually low because it is not yet receiving traffic. If the controller averages that low CPU into group utilization, it might assume capacity is sufficient and halt scale-out prematurely.

Instance warm-up helps the controller handle this gap. Depending on the service, the warm-up period can be used to:

- Exclude a new instance's metrics from scaling calculations during startup.
- Treat new capacity as not yet stabilized until warm-up expires.
- Adjust how additional instance counts are calculated in subsequent scaling steps.
- Prevent scale-in before a new instance contributes full metrics.

Naming and exact semantics vary by cloud provider and scaling policy type. For example, some platforms have default instance warm-up, estimated instance warm-up, or warm-up tied to lifecycle states. Read your specific service's documentation to verify how warm-up affects metric aggregation, health checks, and lifecycle transitions.

### 6.1. Choosing instance warm-up duration

A practical approach:

1. Record timestamp when instance launch is requested.
2. Record timestamp when OS boot finishes.
3. Record timestamp when bootstrap completes.
4. Record timestamp when readiness passes.
5. Record timestamp when stable throughput or latency is achieved.
6. Compute distributions from launch to readiness and from launch to steady state.
7. Pick a warm-up matching scaling goals and variance, then test scale-out and scale-in.

If warm-up is shorter than reality, the autoscaler evaluates unstable metrics. If it is too long, the autoscaler reacts sluggishly to rising demand. Consider p95/p99 timings and load ramp speed, not just averages.

Warm-up can vary by image version, instance type, region, or workload. If groups have noticeably different startup durations, consider separating launch templates, scaling groups, or policies instead of sharing a single skewed value.

## 7. What is cooldown?

Cooldown is the waiting period after a scaling action during which the controller pauses before executing or evaluating another scaling action, according to platform semantics.

The goal is to give the system time to reflect the effect of the previous change. For example, after adding 2 instances, the load balancer must update targets, traffic must rebalance, and CPU metrics need time to show the new capacity.

Cooldown helps:

- Dampen overreactions to brief metric spikes.
- Avoid consecutive scaling actions before the prior action takes full effect.
- Give the application and infrastructure time to settle after capacity shifts.

Cooldown does not make machines boot faster, does not replace readiness checks, and does not guarantee new instances are serving requests. It is purely a throttling mechanism for scaling decisions.

### 7.1. How does cooldown differ from warm-up?

| Attribute | Instance warm-up | Cooldown |
|---|---|---|
| Focus | Time a new instance needs to contribute steadily | Wait period after a scaling action |
| Start trigger | Typically tied to when the instance is added/launched; service-dependent | After a scaling action or per policy |
| Problem solved | New instance metrics do not yet represent steady state | Prevents overly rapid repeated scaling actions |
| Effect | Adjusts how new capacity/metrics are evaluated | Throttles timing of the next scaling decision |
| Does not replace | Readiness and application warm-up | Startup, health checks, or load balancer registration |

Some services use default instance warm-up and do not require separate cooldowns for target tracking; other policies use cooldowns or stabilization windows. Never apply identical settings across different scaling modes without checking semantics.

### 7.2. Cooldown example

Suppose a machine group scales out by 2 instances after CPU crosses a threshold. Over the next 90 seconds, CPU remains high because the new instances are not yet taking full traffic. If the policy immediately adds 4 more machines, the group will end up over-provisioned once traffic balances.

Cooldowns or stabilization windows can suppress repeated actions during that window. However, if load climbs very rapidly and SLOs require immediate capacity, an overly long wait causes capacity shortages. Test both rapid load spikes and load drops.

## 8. Stabilization windows and scaling policies

Beyond warm-up and cooldown, many systems offer stabilization windows to evaluate metrics over a rolling period.

- **Target tracking:** attempts to hold a metric near a target, such as average CPU or requests per instance.
- **Step scaling:** applies different increments/decrements depending on how far the metric breaches the threshold.
- **Simple scaling:** executes a single scaling action and enforces a policy cooldown.
- **Scheduled scaling:** adjusts capacity on a known calendar schedule.
- **Predictive scaling:** forecasts demand and pre-provisions capacity before load rises.
- **Kubernetes HPA:** adjusts replica counts based on metrics, offering `behavior` and stabilization windows to dampen oscillation.
- **Cluster/node autoscaler:** adds nodes when Pods cannot be scheduled and removes nodes when workloads can be safely consolidated.

Each policy has distinct semantics. For example, a simple scaling cooldown does not behave identically to a Kubernetes HPA stabilization window or a VM group's default instance warm-up.

### 8.1. HPA example with stabilization window

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

This example allows rapid scale-up while capping growth rate via policy, and retains 300 seconds of metric history when deciding to scale down. This is an illustrative configuration; HPA requires accurate resource requests to calculate CPU utilization. If new Pods are not yet ready, examine controller behavior, the metrics pipeline, and node capacity as well.

Stabilization windows reduce flapping, but they do not eliminate node provisioning time. If the cluster takes 2 minutes to spin up a node, HPA may create Pods right away while those Pods stay `Pending` until the new node is ready.

## 9. Load balancers and traffic warm-up

Once a new instance passes readiness, it can register with the load balancer. However, sending full traffic immediately can overwhelm cold caches or fresh connection pools.

Control techniques:

- Register targets only after readiness passes.
- Use slow-start or weighted traffic if the load balancer supports it.
- Gradually ramp up the new instance's weight in stages.
- Cap initial concurrency or request rates.
- Warm caches using safe, bounded synthetic requests.
- Monitor latency, errors, and saturation before increasing traffic further.

Not every load balancer supports slow-start. If unsupported, applications can use readiness gates, queues, rate limiting, or other traffic-shaping mechanisms.

### 9.1. Target health and draining

Target lifecycles typically include states such as registering, initial, healthy, unhealthy, and draining. Exact names vary by product.

During scale-in, stop routing new requests to the target, wait for in-flight requests to finish, and close connections per policy. This process is commonly called connection draining or deregistration delay.

Warm-up handles instances entering the group; draining handles instances leaving the group. Both affect user experience and must be tested.

## 10. Lifecycle hooks and warm pools

Some machine group services provide lifecycle hooks to pause an instance in a wait state before completing launch or termination. This lets automation run extra bootstrap tasks, register configurations, or perform cleanup before the lifecycle advances.

Example steps during a launch hook:

1. Instance is created and enters a wait state.
2. Bootstrap agent fetches configurations and secrets.
3. Application starts and runs self-checks.
4. Automation signals lifecycle action completion.
5. Instance proceeds into the group and can take traffic per health policy.

Lifecycle hooks need timeouts, retries, and failure-handling callbacks. If a hook hangs, instances stay stuck waiting and the group never reaches desired capacity.

A **warm pool** is a set of pre-initialized (partially or fully) instances kept ready to shorten scale-out time. Instances may sit in stopped, hibernated, or running states depending on platform and configuration. When needed, the group pulls an instance from the pool and completes only the remaining steps.

Warm pools are helpful when:

- Startup times are long and hard to shrink.
- Load can spike faster than fresh machine provisioning.
- Applications have heavy bootstrap overhead.
- Capacity must be staged ahead of peak hours or events.

In return, warm pools incur storage, compute, licensing, and image maintenance costs. Apply patches, rotate credentials, and verify configuration before placing pooled machines into service. Never let warm pool instances hold secrets or tokens longer than policy allows.

## 11. Measuring warm-up and cooldown

You cannot pick effective warm-up or cooldown settings without telemetry. Emit events and metrics for every lifecycle milestone.

Recommended metrics:

| Metric | Definition |
|---|---|
| `instance_launch_duration_seconds` | Time from launch request to instance running state |
| `instance_boot_duration_seconds` | Time from boot start to OS ready |
| `instance_bootstrap_duration_seconds` | Time to complete bootstrap |
| `application_startup_duration_seconds` | Time from process start to application startup complete |
| `instance_time_to_ready_seconds` | Time from launch to readiness pass |
| `instance_time_to_steady_state_seconds` | Time from launch until stable throughput/latency criteria are met |
| `autoscaling_action_count` | Count of scale-up/scale-down actions by policy |
| `pending_instance_count` | Number of instances provisioning or warming up |
| `healthy_target_count` | Number of targets marked healthy by the load balancer |
| `capacity_ready_ratio` | Ready capacity divided by target capacity |
| `scale_in_drain_duration_seconds` | Time from drain start until instance termination |

Attach stable metadata such as launch template version, image ID, instance type, region/AZ, application version, and environment. Avoid using high-cardinality labels like instance ID on every metric if the system spins up thousands of ephemeral instances; keep instance IDs in logs/events and aggregate metrics by resource group.

### 11.1. Defining steady state

Passing readiness does not necessarily mean performance has stabilized. Define steady state by workload, for example:

- p95/p99 latency within SLO.
- Error rate below a defined threshold.
- Throughput reaching expected minimum levels.
- CPU and memory free of abnormal spikes.
- Connection pools and caches in operational state.
- No continuously growing backlog.

For batch workers, steady state may be defined by message processing rate and queue depth. For APIs, it may rely on request rate, latency, and error rates. Do not apply a single generic criterion to every workload.

### 11.2. Measuring with event timestamps

One approach is having the application or bootstrap agent emit events:

- `instance.launch.requested`
- `instance.os.ready`
- `instance.bootstrap.completed`
- `application.startup.completed`
- `application.readiness.passed`
- `application.steady_state.reached`

A collector computes durations between events. Clock synchronization across hosts and control planes is essential; clock skew can produce negative or distorted durations. Prefer timestamps from a single authoritative source or monotonic clocks for intra-process intervals.

## 12. Choosing warm-up and cooldown by workload

| Workload type | Characteristics | Configuration guidance |
|---|---|---|
| Stateless web/API | Relatively fast startup, requires stable latency | Base warm-up on p95/p99 time-to-ready plus traffic warm-up; cooldown just long enough for metrics to reflect capacity |
| Large Java service | Class loading, JIT, and cache warm-up can be slow | Separate application readiness from runtime warm-up; consider synthetic warm-up and warm pools |
| Batch worker | Can pull messages once broker connection and consumer are ready | Readiness after consumer is ready; warm-up aligned to stable processing throughput |
| GPU/model serving | Model loading and GPU memory allocation can be slow | Pre-load models/caches before serving traffic; use warm pools or predictive scaling if needed |
| Stateful service | Needs data sync, quorum, or volume attachment | Use lifecycle-aware orchestration; never admit node to serving pool until data state is safe |
| Kubernetes node | New VM must register as a node, init CNI/CSI, and schedule Pods | Measure node-ready and Pod-ready separately; include scheduling and image pull times |

Warm-up should be long enough to avoid counting capacity prematurely, yet not so long that the autoscaler reacts slowly to fresh demand. Cooldowns or stabilization windows should reflect how long a prior action takes to show up in metrics and SLOs.

For ultra-fast bursts, simply increasing warm-up or cooldown is not enough. Maintain minimum baseline capacity, or use scheduled/predictive scaling, warm pools, or queue buffering so capacity exists before load arrives.

## 13. End-to-end scale-out flow example

Suppose CPU or requests-per-instance exceeds target:

1. The scaling policy detects load above target across the evaluation window.
2. The machine group requests additional instances.
3. Instances boot the OS and execute bootstrap scripts.
4. Agents register with monitoring and pull configuration and secrets.
5. The application starts and connects to databases and caches.
6. Startup checks finish; readiness passes.
7. The load balancer marks the target healthy and admits it to traffic.
8. Traffic ramps up gradually if slow-start or weighted routing is enabled.
9. Instance metrics enter capacity evaluation once instance warm-up expires per autoscaler semantics.
10. The autoscaler re-evaluates load and decides whether further scaling is needed.

~~~mermaid
sequenceDiagram
    participant AS as Autoscaler
    participant VM as Instance
    participant APP as Application
    participant LB as Load Balancer
    participant MON as Monitoring
    AS->>VM: Launch instance
    VM->>VM: OS boot and bootstrap
    VM->>APP: Start application
    APP->>APP: Connect dependencies and warm up
    APP->>LB: Readiness passed
    LB->>LB: Register target and health check
    LB->>APP: Traffic ramp-up
    VM->>MON: Publish metrics
    MON->>AS: Capacity metrics after warm-up
    AS->>AS: Re-evaluate scaling
~~~

In practice, some steps run in parallel. For instance, monitoring agents may start ahead of the application, and target registration can trigger as soon as readiness passes. This diagram highlights key control checkpoints without mandating a strict universal sequence.

## 14. Scale-in: draining, cooldown, and workload protection

Scale-in carries different risks than scale-out. An instance leaving the group may be handling requests, messages, or jobs. Terminating it abruptly can drop requests, trigger duplicate message processing, or leave writes incomplete.

Safe scale-in workflow:

1. Autoscaler selects a candidate instance for removal per policy.
2. Mark the instance as ineligible for new work.
3. Load balancer transitions the target to draining or deregisters it.
4. Application stops accepting new requests/messages.
5. Wait for active requests, transactions, or jobs to finish within limits.
6. Close connection pools, flush data, and persist state.
7. Lifecycle hooks/termination handlers complete.
8. Instance is terminated.
9. Monitoring verifies post-scale-in capacity and error rates.

For queue workers, stop polling first, complete or return in-flight messages per broker semantics, and only then exit the process. For HTTP services, implement graceful shutdown and a drain window long enough for legitimate requests.

Cooldown after scale-in helps prevent flapping when metrics oscillate, though it never replaces graceful shutdown. You still need termination grace periods, deregistration delays, and proper shutdown handlers.

## 15. Common failure scenarios

| Symptom | Possible causes | Investigation and remediation |
|---|---|---|
| VM running but target unhealthy | Application not started, wrong port, or security group blocking health checks | Check bootstrap logs, listeners, routes, and health check paths |
| Instance takes traffic then latency spikes | Readiness opened too early, cold caches, or un-warmed JIT | Separate readiness from steady state; use traffic ramp-up and synthetic warm-up |
| Autoscaler scales out continuously | New instance metrics look low, bad warm-up config, or load outpaces provisioning | Check instance warm-up semantics, capacity-ready ratio, and load ramp speed |
| Sluggish scale-out | Overly long cooldown/stabilization, quotas, or launch failures | Inspect policies, quotas, lifecycle hooks, and provisioning events |
| Instances stuck in Pending/Wait | Lifecycle hook never completed or automation failed | Check timeouts, retries, permissions, and completion callbacks |
| New instances not counted as capacity | Still unhealthy or warm-up period active per policy | Inspect health states and metric aggregation rules |
| Scale-in breaks requests | Missing draining or overly short grace period | Enable graceful shutdown and verify longest valid request duration |
| New machines show unusually low CPU | Not receiving traffic yet or metrics not stabilized | Correlate healthy targets, request counts, and warm-up state |
| New node ready yet Pods stay Pending | CNI/CSI issues, image pulls, taints, or resource limits | Check node conditions, scheduler events, and container runtime |

When debugging, pinpoint which exact layer is slow: cloud provisioning, OS boot, bootstrap, application startup, readiness, load balancer, or autoscaler policy. Never inflate cooldowns to hide a bootstrap or health check bug.

## 16. Testing workflow for warm-up and cooldown

Before going to production, test scale-out, scale-in, and failure scenarios.

### 16.1. Preparation

- Choose a representative workload and define SLOs.
- Record baseline startup time and steady-state throughput.
- Enable events for every instance lifecycle stage.
- Ensure CPU, memory, request, latency, and health metrics are all collected.
- Set cost caps and maximum instance limits for the test run.

### 16.2. Testing scale-out

1. Start at minimum capacity.
2. Ramp load gradually past the scaling target.
3. Record when the autoscaler decides and issues launch requests.
4. Measure each stage up to readiness and steady state.
5. Confirm targets receive traffic only after meeting criteria.
6. Watch whether the autoscaler triggers duplicate scale-outs during warm-up.
7. Verify SLOs hold throughout capacity expansion.

### 16.3. Testing scale-in

1. Drop load from peak down to low baseline.
2. Confirm stabilization/cooldown prevents premature capacity removal.
3. Observe load balancer draining behavior.
4. Send controlled long-running requests or jobs during the drain window.
5. Confirm requests complete or retry safely.
6. Check error rates and queue backlogs after termination.

### 16.4. Fault testing

Simulate controlled failure modes:

- Slow package repositories or image registries.
- Applications failing readiness checks.
- Unavailable downstream dependencies.
- Bootstrap script timeouts.
- Unresponsive lifecycle hooks.
- One AZ or instance batch launching slowly.
- Load ramping faster than provisioning speed.

Confirm the system enforces timeouts, retries, alerts, and fallbacks. Never run fault injection in production without an approved scope and procedure.

## 17. Optimizing time-to-ready for new machines

Improvements can be applied by layer:

**Provisioning and images**

- Pick appropriate instance families and images.
- Use images pre-baked with stable packages and agents.
- Eliminate unnecessary package installations at boot.
- Prepare snapshots or warm pools when startup times are long.
- Check regional/zonal quotas and capacity availability.

**Bootstrap**

- Fetch configurations in batches and in parallel where safe.
- Pin artifacts with immutable versions or digests.
- Avoid excessive external API calls.
- Use retries with backoff, timeouts, and idempotency.
- Do not block readiness on optional background tasks.

**Application**

- Trim classpaths and unnecessary startup initialization.
- Lazy-load components not needed for initial requests.
- Size initial connection pools appropriately.
- Warm caches with a bounded set of popular keys.
- Run safe synthetic requests against critical execution paths.

**Traffic and autoscaling**

- Admit targets to traffic only after readiness passes.
- Use slow-start/weighted routing where supported.
- Set warm-up based on measured time-to-steady-state.
- Keep minimum capacity for baseline load.
- Use scheduled/predictive scaling when demand is predictable.
- Size cooldown/stabilization based on metric lag and feedback delay.

Optimizing startup never justifies skipping security or configuration validation. Never bypass certificate checks, secret validation, image integrity verification, or access controls just to shave off a few seconds.

## 18. Operational checklist

- [ ] Distinguished launch, boot, bootstrap, application startup, readiness, and steady state.
- [ ] Timestamps or events emitted for key lifecycle stages.
- [ ] Measured p50/p95/p99 time-to-ready and time-to-steady-state.
- [ ] Startup scripts implement timeouts, retries, backoff, and idempotency.
- [ ] Secrets and credentials fetched securely, never baked into images.
- [ ] Readiness opens only when the workload can safely serve requests.
- [ ] Liveness does not depend directly on every external dependency.
- [ ] Startup probes accommodate slow-starting applications.
- [ ] JVM/runtime warm-up and cold caches are accounted for.
- [ ] Load balancers route traffic only to healthy targets.
- [ ] Traffic ramp-up is configured when workloads need warm caches or pools.
- [ ] Autoscaler instance warm-up aligns with provider semantics.
- [ ] Cooldown/stabilization windows do not make autoscaling react too slowly.
- [ ] Scale-in implements draining, graceful shutdown, and termination grace periods.
- [ ] Lifecycle hooks have timeouts and failure-callback handling.
- [ ] Warm pools are patched, updated, and rotated for credentials on schedule.
- [ ] Tested scale-out, scale-in, and bootstrap failure scenarios.
- [ ] Dashboards monitor ready capacity, target health, and time-to-ready.

Warm-up, cooldown, and time-to-ready are distinct parts of the same autoscaling lifecycle. Measure from launch request to readiness and steady state, admit instances to traffic only when the app can truly serve, and tune the autoscaler to when new capacity begins contributing reliably. Cooldown and stabilization suppress rapid consecutive scaling decisions; readiness, traffic ramp-up, and graceful shutdown protect requests while the fleet changes size. Testing both scale-out and scale-in ensures the system responds accurately to load while keeping SLOs and costs within limits.
