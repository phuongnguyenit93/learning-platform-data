# Reducing Cold Starts for Java Applications on Cloud Run

An order API written in **Java/Spring Boot** is deployed on **Cloud Run**. During the day the system handles hundreds of requests per minute; overnight there is almost no traffic. The first request after an idle period sometimes takes several seconds, whereas subsequent requests are typically much faster. The development team wants to reduce this latency without keeping too many idle instances alive or letting costs spiral out of control.

This is the **cold start** problem: Cloud Run must provision a new container instance before that instance can serve requests. For Java, that time also includes JVM and framework startup. A sound solution must distinguish **infrastructure provisioning, JVM startup, application initialization, and request processing**, then optimize using real measurements.

This lesson belongs to the **Cloud Run** chapter of the `CLOUD_PROVIDERS_GCP` module: choosing Google Cloud services, managing projects/IAM/VPCs, deploying from Artifact Registry, connecting Cloud SQL/Cloud Storage, automating releases, and monitoring reliability and cost. The content focuses on **reducing cold starts for Java services on Cloud Run**, without confusing them with warm-request latency or downstream dependency failures.

## 1. Learning Objectives

After this lesson, you can:

1. Identify cold start phases and distinguish **cold start**, **first-request latency**, and **warm-request latency**.
2. Choose **minimum instances**, **startup CPU boost**, **concurrency**, and CPU/memory configurations based on SLOs and budgets.
3. Reduce initialization overhead in the **JVM**, Spring Boot, dependency injection, connection pools, and container images.
4. Design a **startup probe** so traffic does not arrive too early while avoiding prolonged startup from unnecessary work.
5. Run controlled experiments, inspect metrics/logs, and analyze p95/p99 latency and cost per request.
6. Apply safe rollout/rollback strategies and troubleshoot common symptoms.

## 2. Where Do Cold Starts Actually Happen?

### 2.1. Typical Phases

~~~mermaid
flowchart LR
    R["Request arrives"] --> S["Cloud Run needs a new instance"]
    S --> C["Prepare image / container"]
    C --> J["Start JVM"]
    J --> F["Initialize framework / beans"]
    F --> D["Initialize minimal dependencies"]
    D --> L["App ready on PORT"]
    L --> H["Handle request"]
~~~

Each phase carries a different source of latency:

| Phase | Symptoms | Optimization direction |
| --- | --- | --- |
| Instance and container provisioning | Latency incurred when scaling from 0 or scaling out. | Minimum instances, concurrency tuning, startup CPU boost. |
| JVM startup | Slow Java process boot, initial class loading/JIT. | Appropriate JDK, trim classpath, CDS/AOT/native where beneficial, benchmarked JVM flags. |
| Application initialization | Spring instantiating many beans, classpath scanning, running migrations, or calling remote services. | Remove unused autoconfiguration, move heavy work out of startup. |
| Dependency connections | Waiting on Cloud SQL, Secret Manager, DNS, or external APIs. | Tune timeouts, connection pools, IAM/networking, and initialization order. |
| First request | First endpoint call triggers lazy beans, JIT, DB queries, or cache population. | Selective preloading, optimize request handler, measure first call separately. |

**Cold starts do not happen on every request.** Once initialized, an instance can serve multiple requests up to its configured concurrency. Cloud Run may still create additional instances even when warm instances exist if traffic rises or existing instances run out of capacity.

### 2.2. Three Measurements Not to Conflate

- **Startup duration:** time from when the Java process starts until the app is ready. This is only one piece of end-to-end cold start.
- **Cold-request latency:** client-observed latency when a request triggers a new instance, including routing/queueing, startup, and request execution.
- **Warm-request latency:** latency when served by an already-ready instance; normally used as the business-logic baseline.

Illustrative example:

| Measurement | P50 | P95 | Interpretation |
| --- | ---: | ---: | --- |
| Request on warm instance | 85 ms | 180 ms | Baseline business performance. |
| Request needing a new instance | 1,900 ms | 3,700 ms | Includes startup and instance wait time. |
| JVM time to ApplicationReady | 1,150 ms | 1,600 ms | Excludes full Cloud Run startup overhead. |

These are **hypothetical numbers**, not official Cloud Run or Java benchmarks. A handful of `curl` calls cannot reliably estimate p95.

## 3. Cloud Run-Layer Solutions

### 3.1. Minimum Instances: Keeping Capacity Ready

**Minimum instances** sets the minimum floor of instances Cloud Run keeps warm within supported configuration ranges. For low-traffic services, setting a floor above 0 lowers the probability a request waits for a cold start from zero.

~~~text
min instances = 0:
  no traffic → may scale to 0 → next request incurs cold start

min instances = 1:
  one instance kept warm → light requests can be served right away
~~~

Key points to remember:

- **Does not guarantee eliminating all cold starts.** Scaling out past minimum instances, rolling out new revisions, instance replacement, or infrastructure events can still launch cold instances.
- **Incurs instance maintenance cost.** Billing depends on CPU allocation/billing settings and current pricing.
- Cloud Run defines minimums at the **service** level and, in supported setups, at the **revision** level; during traffic splits or when retaining old revisions, check scope so you do not keep unintended warm capacity running.
- Choosing 1, 2, or more instances must be grounded in **baseline traffic, region, reliability, and SLOs**, not a one-size-fits-all magic number.

Example write command on **an existing service**:

~~~bash
# WRITE: updates service-level minimum instances per supported CLI.
# Check "gcloud run services update --help" before running.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --min=1
~~~

In some guides or CLI versions, the **revision-level** flag has a similar name (`--min-instances`); do not mix the two without confirming whether they target **service** or **revision** scope. To compare against baseline within budget, you can revert to 0 under an approved change process.

### 3.2. Startup CPU Boost: Extra CPU During Initialization

Cloud Run supports **startup CPU boost** on eligible configurations: granting additional CPU resources during container startup and a short post-startup window defined by the service. This often helps JVM/Spring Boot apps that need heavy CPU to load classes, instantiate beans, and initialize the runtime.

~~~bash
# WRITE: enable startup CPU boost on an existing service.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu-boost
~~~

Startup CPU boost **does not make a slow Cloud SQL connection faster** if the bottleneck is a network timeout, nor does it turn an I/O-heavy app into a CPU-bound workload. CPU boost can incur **extra charges** during the boost window; check pricing and compare cost per completed request.

### 3.3. Concurrency Decides When Another Instance Is Needed

**Container concurrency** caps how many requests can be routed simultaneously to a single instance. Raising concurrency appropriately lets warm instances absorb more requests, reducing scale-out pressure and cold starts—provided the Java app handles concurrency safely.

~~~bash
# WRITE: example setting up to 40 concurrent requests/instance.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --concurrency=40
~~~

| Concurrency | Suitable scenarios | Risks |
| --- | --- | --- |
| Low | CPU-intensive requests, non-thread-safe code, load isolation needed. | Needs more instances sooner; can raise cold starts/cost. |
| Medium | Java API with DB/API I/O, benchmarked thread pools and memory. | Must size thread/DB connection pools and request queues. |
| High | I/O-bound workloads with efficient concurrency and ample CPU/RAM. | p95/p99 rises from contention, GC, blocking, or database limits. |

Do not blindly apply `--concurrency=80` as a default optimization trick. If one request saturates CPU or DB connections, high concurrency can slow the system down even while reducing cold starts. **Autoscaling, concurrency, and max instances work together** and must be load-tested as a unit.

### 3.4. CPU/Memory and CPU Allocation

Cloud Run lets you choose vCPU count, memory, and CPU allocation mode per service capabilities. Two trade-offs:

1. **Too little CPU:** slow JVM bootstrap/JIT, app misses startup deadlines, or latency climbs.
2. **Too much CPU:** startup may speed up, yet cost climbs—especially at low traffic.

With **request-based CPU allocation**, CPU outside active request processing can be throttled per service model. With **instance-based CPU allocation**, CPU stays allocated throughout the instance lifecycle under a different pricing model. Choose instance-based when the app genuinely needs out-of-request background work; **do not enable it thinking it eliminates cold starts by itself**.

Example resource update for benchmarking:

~~~bash
# WRITE: hypothetical config; verify supported limits and cost.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu=1 \
  --memory=1Gi
~~~

**Capping `max instances` does not cure cold starts.** It helps bound budgets and downstream connections, yet setting it too low when traffic surges forces requests to queue or fail. Conversely, raising max arbitrarily can exhaust Cloud SQL's connection pool.

## 4. Optimize Java and the JVM Before Changing Architecture

### 4.1. Choose the Right JDK and Avoid Heavy Startup

For traditional Java services:

- Use a **supported LTS JDK/JRE** and up-to-date base image matching bytecode and runtime architecture.
- Remove unused dependencies, trim the classpath, and drop unnecessary startup plugins.
- Avoid creating huge thread pools, parsing massive configs, loading large datasets, or making synchronous remote API calls inside static initializers or constructors.
- Never run heavy database migrations every time a new instance boots. Use a dedicated migration job/pipeline with proper locking and rollback procedures.
- Keep startup deterministic; log an `application ready` milestone to spot which release regressed startup time.

Before shrinking startup time, **identify whether the bottleneck is CPU, I/O, or a dependency**. Tuning JVM flags does little if Spring Boot is blocked waiting on a 10-second database connection timeout.

### 4.2. JVM Flags: Benchmark, Never Copy Blindly

The flags below are **benchmarking candidates**, not the "best" config for every Java workload:

~~~bash
# Example environment variable for a JVM honoring cgroup memory limits.
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65"

# Another experiment to reduce initial JIT optimization overhead:
JAVA_TOOL_OPTIONS="-XX:TieredStopAtLevel=1 -XX:MaxRAMPercentage=65"
~~~

`-XX:TieredStopAtLevel=1` can lower initial JIT overhead yet **reduces peak throughput** for long-lived applications. `MaxRAMPercentage` only scales relative JVM heap sizing; containers also need memory for metaspace, thread stacks, native buffers, and JIT code cache. Packing heap too tightly against the container limit can trigger OOMs, worsening latency and cold starts.

Mechanisms like **Class Data Sharing (CDS/AppCDS)** or Java **AOT optimizations** can reduce class-loading and initialization costs when packaged properly with the matching JDK/image. Measure on real artifacts and keep archives synchronized across updates rather than treating them as a substitute for trimming dependencies.

### 4.3. Java Native Image

With **GraalVM Native Image** or framework-supported native/AOT tooling, the app compiles ahead-of-time into a native executable. Across many workloads, this cuts startup time and memory footprint dramatically.

Trade-offs to weigh:

| Potential benefit | Costs/risks to measure |
| --- | --- |
| JVM bootstrap and class loading reduced or eliminated by native runtime. | Complex build pipelines, long build times, and high build-time RAM usage. |
| Serves requests much sooner during scale-out. | Reflection, proxies, JNI, serialization, and resource loading need explicit metadata/support. |
| Lower memory footprint in certain apps. | Peak throughput/latency differs from JVM JIT; benchmark under real traffic. |

**Do not assume native is always faster** for Java services with long-running requests, heavy compute algorithms, or poorly supported libraries. Base the decision on startup p95, warm throughput, binary size, CI build time, debuggability, and operational cost.

## 5. Optimizing Spring Boot in the Right Places

Spring Boot startup overhead often comes from autoconfiguration, classpath scanning, dependency injection, ORMs, and connection pools. Targeted fixes here usually beat random JVM flag tweaks:

1. **Measure initialization by phase** using Spring Boot startup metrics/logs, JVM runtime uptime, and tracing.
2. Drop unneeded starters (for example, do not pull in a database/ORM stack if the service does not use JPA).
3. Narrow component scanning to required packages instead of scanning unrelated modules/plugins.
4. Defer rarely used initialization, while **never blindly pushing failures into the first request**.
5. Minimize synchronous remote calls inside `@PostConstruct` or bean initialization; configure explicit timeouts on caches and connection pools.
6. Test **Spring AOT / native support** if the service mostly handles short requests and startup is a major bottleneck.

### 5.1. Logging Spring Boot's Ready Milestone

In a typical Spring Boot project with standard dependencies:

~~~java
import java.lang.management.ManagementFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupLogger {
    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        long uptimeMs = ManagementFactory.getRuntimeMXBean().getUptime();
        System.out.println("application_ready_jvm_uptime_ms=" + uptimeMs);
    }
}
~~~

This metric measures **how long the JVM ran until `ApplicationReadyEvent`**; it **excludes Cloud Run container/image provisioning time**. Logging timestamps, revisions, and instance identifiers via supported logging tools helps compare releases.

### 5.2. Spring Lazy Initialization: Use Only After Testing

~~~properties
# Controlled experiment only; do not enable blindly for production.
spring.main.lazy-initialization=true

# Spring Boot listens on the PORT provided by Cloud Run.
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

Lazy initialization makes the app report "ready" sooner, **yet the first beans are instantiated when the first request touches them**—which may merely shift cold-start latency onto that first request. Do not enable this if the app needs fail-fast config/DB validation at startup or has strict first-request SLOs. Measure both `ApplicationReady` **and** first-request latency on every critical endpoint.

### 5.3. Connection Pools and Caches

Suppose each instance creates a 20-connection DB pool and Cloud Run can scale up to 30 instances: theoretically that can open **600 connections** if every pool saturates. That is a capacity calculation, not a guarantee all 600 open immediately at startup.

Keep pools small, reuse connections per instance, and stay within Cloud SQL limits. Avoid eagerly filling entire pools or loading gigabyte caches **on the startup path** when requests do not immediately need them. If an essential dependency must be verified, prefer a lightweight status check with a strict timeout over blocking indefinitely.

## 6. Container Image and Readiness

### 6.1. Targeted Image Optimization

Oversized images packed with unused dependencies can add distribution/startup work, though platform-level optimizations in Cloud Run mean **image size does not always scale linearly with startup latency**.

Best practices:

- Use **multi-stage builds**, copying only the JRE/native binary and runtime artifacts into the final image.
- Use trusted base images, pinned by digest at release time; patch vulnerabilities regularly.
- Keep layers stable to maximize build cache hits, and exclude build tools/secrets from the runtime image.
- Declare the entrypoint directly, avoiding wrapper shell scripts running unneeded commands before the JVM.
- Never run `apt-get`, Maven downloads, or package fetches at **container startup**.

### 6.2. Listen Properly on `PORT`

Cloud Run injects `PORT` into the ingress container; the app must listen on **`0.0.0.0`** at that port, not only `127.0.0.1`.

Example Dockerfile for a **pre-built** Spring Boot JAR named `orders-api.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY orders-api.jar /app/app.jar
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example assumes `orders-api.jar` sits in the Docker build context and targets JRE 21 bytecode. Configure Maven/Gradle to emit the matching JAR name or adjust `COPY` to match the real artifact. `EXPOSE 8080` is only image metadata; Spring Boot must still bind `PORT` and Cloud Run must be configured with the matching ingress port.

### 6.3. Startup Probe: Wait Until the App Is Truly Ready

A **startup probe** lets Cloud Run verify container initialization through supported health checks. It **does not make startup faster on its own**, but prevents Cloud Run from treating a newly opened socket as "ready" before the app can actually serve requests.

Illustrative partial YAML service configuration:

~~~yaml
spec:
  template:
    spec:
      containers:
        - image: asia-southeast1-docker.pkg.dev/retail-lab/apps/orders-api:release-1
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 2
            failureThreshold: 10
~~~

This snippet **only illustrates internal structure** of a Cloud Run service configuration, not a full manifest for `kubectl apply`. Verify the exact schema/API and startup probe limits of your Cloud Run version before applying. The `/readyz` endpoint should check only minimal initialization prerequisites without running heavy queries or causing side effects on every probe. If timeouts are too tight or thresholds too sensitive, Cloud Run can repeatedly restart containers that simply needed legitimate startup time.

## 7. Practical Example: Optimizing a Java Service

Assume the image is built, tested, and pushed to **Artifact Registry**:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/apps/orders-api@sha256:<REAL_DIGEST>
~~~

`<REAL_DIGEST>` is a placeholder: replace it with the image's real SHA-256 digest when running. You may deploy by tag in a lab, whereas production should record digests in release manifests for exact rollbacks.

### 7.1. Capture Baseline Before Tuning

~~~bash
# READ-ONLY: inspect current configuration and Cloud Run service URL.
gcloud run services describe orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format=yaml

gcloud run services describe orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format="value(status.url)"
~~~

Record the revision, min instances, CPU/memory, concurrency, startup boost, image digest, and authentication settings. Omitted flags in output may reflect service schema defaults; verify supported fields rather than guessing.

### 7.2. Change One Variable at a Time

A sound experiment sequence:

1. **A — Baseline:** min instances 0, current CPU/concurrency, original image.
2. **B — Startup CPU boost:** keep everything else constant, enable boost, and measure.
3. **C — Java startup:** deploy an image with trimmed classpath/initialization; re-measure.
4. **D — Minimum instances 1:** measure impact on first-request latency and idle cost.
5. **E — Concurrency:** test 10/40/80 as appropriate under identical workload and CPU/DB bounds.

Do not conclude version D beats version A if you simultaneously changed the image, CPU, and incoming request pattern. Keep **region, load profile, auth method, upstream dependencies, and instance lifecycle observations** consistent across runs.

### 7.3. Illustrative Update Commands

~~~bash
# WRITE: apply one change at a time in a test environment.
gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --cpu-boost

gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --min=1

gcloud run services update orders-api \
  --project=retail-lab \
  --region=asia-southeast1 \
  --concurrency=40
~~~

Each command may create a new revision or modify capacity allocation per Cloud Run mechanics. These commands **do not create a new service, open public access, or grant Artifact Registry permissions**. For production, move them into reviewed IaC/CI/CD with rollback plans and Billing tracking.

## 8. Measuring Cold Starts Without Fooling Yourself

### 8.1. Collect the Right Metrics

| Signal | Source | Meaning |
| --- | --- | --- |
| Container startup latency | Cloud Run platform metrics/logs. | Time spent spinning up new instances. |
| `ApplicationReady` JVM uptime | Java application logs. | Time inside the JVM until the ready event. |
| Request latency per revision | Cloud Run request metrics, logs, and app tracing. | User-facing latency, including post-startup effects. |
| 5xx/timeouts | Cloud Run, app logs, dependency logs. | Separates readiness failures, cold starts, and dependency errors. |
| Instance count and concurrency | Cloud Monitoring/Cloud Run. | When Cloud Run scales and how many warm instances run. |
| Cloud SQL latency, connections | Cloud SQL and app metrics. | Avoids blaming the JVM for every slow query. |
| Cost/usage | Cloud Billing and Cloud Run metrics. | Evaluates latency-vs-cost trade-offs. |

To separate cold vs. warm calls, correlate logs with **revision/instance** and first-request markers in app logs. Never assume a slow request was a cold start just because it was slow—it could be DB contention, cache misses, GC pauses, or network timeouts.

### 8.2. Testing Procedure

1. Measure warm latency under steady load with sufficient sample size.
2. Use a test environment where new instances can be triggered cleanly; **never assume pausing traffic for one minute always forces Cloud Run to scale to 0**.
3. Capture multiple startup cycles, recording startup duration, first-request latency, errors, and instance counts.
4. Also test **burst traffic**: sudden load spikes can force Cloud Run to start additional cold instances even when `min=1`.
5. Compare p50/p95/p99, timeout rate, cost per 1,000 requests, and Cloud SQL limits.
6. Promote changes only when improvements hold across repeated runs within SLO and budget.

Use **k6, JMeter, Gatling**, or an approved load generator rather than sequential `curl` loops. If the service enforces IAM, grant the load generator `run.invoker` and send valid identity tokens—never open public endpoints just to benchmark.

### 8.3. A Trade-Off Calculation

Suppose (hypothetical figures):

~~~text
Option 0:
  min instances = 0
  cold request p95 = 3.0 seconds
  warm request p95 = 180 ms
  baseline cost = lower

Option 1:
  min instances = 1
  most low-traffic requests = served immediately
  warm request p95 = 180 ms
  instance maintenance cost = higher

Option 2:
  min instances = 0 + startup CPU boost + Java optimization
  cold request p95 = 1.4 seconds
  warm request p95 = 180 ms
  instance maintenance cost = none required
~~~

No single option wins universally. If an internal service runs only a few times a day and tolerates a 2-second wait, trimming app startup is usually far more economical than minimum instances. If a checkout API enforces strict latency on **every request**, keeping warm capacity may be justified, while still planning for bursts and fallback capacity.

## 9. Architecture: Cold Starts Are Not Just About Java

Example:

~~~mermaid
flowchart LR
    USER["Client"] --> RUN["Cloud Run Java API"]
    RUN --> SQL["Cloud SQL"]
    RUN --> SECRET["Secret Manager"]
    RUN --> STORE["Cloud Storage"]
    IMAGE["Artifact Registry"] -. "Image used when starting instance" .-> RUN
    MON["Cloud Monitoring/Logging"] -. "Latency, instance count, errors" .-> RUN
~~~

Points to control:

- **Cloud SQL:** avoid oversized pools per instance; set bounded timeouts and retries; never run schema migrations on every instance boot.
- **Secret Manager:** use proper identity/permissions; plan fetch timing and valid caching without logging secrets.
- **Cloud Storage:** do not download entire buckets or large datasets in constructors if the first request needs only tiny metadata.
- **Artifact Registry:** the image must exist and Cloud Run principals need pull access; image pull failures are deploy/startup errors, not JVM bottlenecks.
- **Ingress/auth:** Cloud Run IAM, TLS, LBs, and network policies decide who can call; faster startup does not replace security.

A classic anti-pattern is calling several networked services sequentially during app startup with no timeouts. If one dependency stalls, instances start slowly or crash-loop; separate dependencies into **strictly required before serving** vs. **fetched lazily on demand**.

## 10. Security and CI/CD While Optimizing

1. **Build immutable images:** record Git commit, JDK/base image version, and pushed artifact digest.
2. **Least privilege:** CI publisher holds Artifact Registry Writer on the specific repo; Cloud Run deployer and service agent hold deploy/pull permissions; runtime service account holds only needed Cloud SQL/Storage/Secret Manager roles.
3. **No secrets in Dockerfile/JARs:** use Secret Manager and least-privilege runtime identities.
4. **Change control:** benchmark startup flags in staging, review, roll out with canary/traffic splitting where supported, and watch per-revision metrics.
5. **Rollback:** record old image digests and Cloud Run config; if a new build degrades, shift traffic back to the proven revision or redeploy per runbook.
6. **Cost monitoring:** minimum instances and instance-based CPU allocation raise baseline spend; set budget alerts and track usage.

A new native/AOT image can slash cold starts yet **alter runtime behavior**. Release pipelines must add thorough tests for reflection, serialization, dependencies, and live endpoints—not just startup checks.

## 11. Troubleshooting by Symptom

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| First request slow, subsequent ones fast | Cold start/JVM init, JIT, lazy beans, or cache miss. | Cloud Run startup metrics, `ApplicationReady` logs, first-request traces. |
| Startup CPU boost barely helps | I/O bottleneck, waiting on DB/Secret Manager, dependency throttling. | Breakdown of startup phases and network timeouts. |
| `min=1` yet some requests are still slow | Scale-out, revision rollout, instance replacement, app/dependency latency. | Instance count, revision, request concurrency, logs. |
| Raising concurrency worsens p99 | CPU contention, thread/DB pool saturation, GC, or lock contention. | Load test p95/p99, CPU/memory, pool metrics. |
| Container receives no requests or port error | Java binds only localhost, wrong `PORT`/entrypoint, failing startup probe. | Container logs, `server.port`, `server.address`, probe config. |
| App boots fast yet first request is slow | Lazy initialization, JIT, or cache/connection warmup deferred to request. | Compare `ApplicationReady` with first-request trace. |
| OOM at startup | Heap/native memory exceeds container limit. | Cloud Run memory metrics, JVM heap, threads/metaspace. |
| Scaling instances chokes Cloud SQL | Each instance opens too large a pool/query load. | Cloud SQL connection limits, pool size, max instances. |
| Every deploy fails initialization | Wrong image/digest, service agent IAM, bad config/secrets, dependency down. | Revision startup logs, Artifact Registry access, health endpoints. |
| Costs jump sharply after optimization | High min instances, always-on CPU allocation, scale-out, or logging volume. | Cloud Billing, CPU/memory allocation, instance counts. |

### Short Diagnostic Workflow

1. **Pinpoint the exact revision and timestamp** of the slow request.
2. **Check whether Cloud Run spun up a new instance**; if not, focus on application/dependency latency.
3. **Inspect `ApplicationReady` logs** and startup probes; if Java starts fast, check image/platform/network layers.
4. **Separate CPU vs. I/O** via profilers/startup logs and CPU/memory/DB metrics.
5. **Inspect concurrency/scale-out**, warm pools, and downstream limits.
6. **Change one variable in staging**, measure across multiple trials, and roll back if SLOs or costs worsen.

Never fix a `403` from Cloud SQL by adding CPU, or a `PORT` binding error by keeping 10 instances warm.

## 12. Exercises

### Exercise 1 — Classifying Latency

An API has warm p95 = 120 ms, cold p95 = 2.8 seconds, and Spring reports `ApplicationReady` at 1.6 seconds. Is the 1.2-second difference guaranteed to be purely Cloud Run container provisioning? List at least three components that can contribute.

**Hint:** no. Routing/queueing, container platform startup, networking, and first-request work can all contribute; measure using traces and metrics.

### Exercise 2 — Choosing Minimum Instances

Service A receives only 20 calls/day and tolerates ~2-second cold requests. Service B is a checkout API with strict SLOs even during low-traffic hours. Should you test `min=0` or `min=1` first for each service? Which costs must you measure?

### Exercise 3 — Startup CPU Boost

One Spring Boot app takes 2.5 seconds to initialize with high CPU usage instantiating beans. Another API takes 9 seconds to start due to a Cloud SQL connection timeout. Which case will startup CPU boost likely help more, and how do you prove it?

### Exercise 4 — JVM Flags and Lazy Initialization

A team enables `-XX:TieredStopAtLevel=1` and `spring.main.lazy-initialization=true`; `ApplicationReady` drops from 1.6 to 0.8 seconds, yet the first request rises from 0.2 to 1.4 seconds. Did user experience genuinely improve? What peak throughput check is still missing?

### Exercise 5 — Concurrency and Database

Each instance has a pool of up to 15 Cloud SQL connections, and the service can scale to 40 instances. Compute the hypothetical maximum total connections. Propose ways to reduce DB exhaustion risk when raising concurrency or max instances.

**Hint:** 15 × 40 = 600 connections if all pools saturate; apply pool sizing, connection reuse, scale caps, and DB metrics.

### Exercise 6 — Controlled Benchmarking

Design three benchmark runs comparing baseline Java JIT, startup CPU boost, and a native image. Which variables must stay constant across every run? Specify measurements for startup p95, first-request p95, warm p95, 5xx rate, and cost per 1,000 requests.

### Exercise 7 — Release Control

After enabling minimum instances and deploying a new revision, traffic is split 80% to the old revision and 20% to the new revision. Why might warm instance counts and costs differ from initial estimates? Where do you inspect **service-level vs. revision-level minimum instances** and traffic splits?

## 13. Production Readiness Checklist

| Item | What to verify |
| --- | --- |
| **Cold-start baseline** | Separates startup latency, cold-request, and warm-request; sufficient p50/p95/p99 samples. |
| **Instance lifecycle** | Min instances and traffic splits configured intentionally; understands scale-out still cold-starts. |
| **CPU** | Startup CPU boost, CPU/memory, and CPU allocation benchmarked and costed. |
| **Concurrency** | Thread safety, CPU, memory, connection pools, and p99 meet SLOs. |
| **JVM** | LTS JDK, dependency footprint, JVM flags, and heap sizing verified. |
| **Framework** | Autoconfiguration, lazy beans, and startup remote calls audited. |
| **Readiness** | Binds `0.0.0.0:$PORT`; startup probe hits right endpoint with sensible timeouts. |
| **Artifacts** | Pinned image digest, reproducible builds, updated base images. |
| **Dependencies** | Cloud SQL, Storage, secrets, IAM, and networking have matching timeouts/retries. |
| **Security** | Deployer, service agent, and runtime identities separated; zero embedded secrets. |
| **Rollout** | Staging benchmarks, SLO monitors, canary/rollback, and clear ownership in place. |
| **Cost** | Monitors billed idle time/min instances, CPU, requests, transfer, and logs. |

## 14. References

Cross-check configuration limits, CLI flags, and pricing with current Google Cloud/JDK/Spring Boot documentation:

- [Cloud Run — Optimize performance](https://cloud.google.com/run/docs/tips/general)
- [Cloud Run — Minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [Cloud Run — Startup CPU boost](https://cloud.google.com/run/docs/configuring/services/startup-cpu-boost)
- [Cloud Run — Maximum concurrent requests](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run — CPU allocation/billing settings](https://cloud.google.com/run/docs/configuring/billing-settings)
- [Cloud Run — Health checks](https://cloud.google.com/run/docs/configuring/healthchecks)
- [Cloud Run — Monitoring](https://cloud.google.com/run/docs/monitoring)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Run — Container runtime contract](https://cloud.google.com/run/docs/container-contract)
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Java Class Data Sharing](https://docs.oracle.com/en/java/javase/21/vm/class-data-sharing.html)

**Takeaway:** Cloud Run cold starts combine instance provisioning, JVM startup, and application initialization. **Minimum instances** lower the odds of cold boots; **startup CPU boost** accelerates CPU-bound startups; **concurrency** governs scale-out speed; and Java/Spring/dependency optimization eliminates wasted work. No single knob eliminates all cold starts. **Measure the right phase, test one change at a time, protect first-request SLOs, and balance against cost.**
