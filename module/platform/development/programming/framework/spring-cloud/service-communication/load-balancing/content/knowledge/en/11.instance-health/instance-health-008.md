# Avoiding Overload from Too Many Callers Performing Health Checks

A service running multiple replicas is often called by many other applications. In Spring Cloud LoadBalancer, each caller application can have its own `ServiceInstanceListSupplier` and actively probe the health of target instances. As the number of callers grows, the volume of health-check requests (*health-check probes*) can grow as well, even before business traffic increases proportionally.

The issue here is not merely how many resources one probe consumes. The issue is **many independent callers simultaneously checking the same set of replicas**, potentially at the same frequency or even at the same exact moment. Without careful design, the very routing mechanism meant to avoid unhealthy instances generates extra load, drives up timeouts, and makes system recovery harder.

This lesson belongs to the **Instance Health** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module's goal is to master client-side load balancing by service ID, discovery, health checks, and routing policies; while practicing with `RestClient`, `WebClient`, OpenFeign, retries/timeouts, and error observability. This lesson focuses on how to **keep health checks useful without letting health-check traffic become a source of overload**.

After this lesson, you will be able to:

- Explain why health checks performed in each caller risk amplifying request volume.
- Estimate probe load from caller count, instance count, and check interval.
- Distinguish Spring Cloud LoadBalancer health checks from registry and deployment-platform checks.
- Choose a primary health-checking mechanism that reduces duplicate probing.
- Configure check intervals, endpoints, and supplier chains according to your Spring Cloud version's capabilities.
- Evaluate traffic spikes, cascading health-check failures, and their impact on retries/timeouts.
- Design measurements to verify results before and after optimization.

## 1. How Do Client-Side Health Checks Work?

Suppose `order-service` calls `inventory-service` using the logical address:

~~~http
GET http://inventory-service/api/items/42
~~~

Spring Cloud LoadBalancer selects a `ServiceInstance` from the list provided by `ServiceInstanceListSupplier`. When client-side health checking is configured, an appropriate supplier, such as `HealthCheckServiceInstanceListSupplier`, can probe each replica's health endpoint and provide only instances satisfying the policy.

For example, with three replicas:

~~~text
inventory-service
  ├─ inv-a: 10.0.1.11:8080
  ├─ inv-b: 10.0.1.12:8080
  └─ inv-c: 10.0.1.13:8080
~~~

One caller can hit the health endpoint of all three replicas:

~~~mermaid
flowchart LR
    A["order-service caller"] --> LB["ServiceInstanceListSupplier"]
    LB --> HA["GET inv-a /actuator/health"]
    LB --> HB["GET inv-b /actuator/health"]
    LB --> HC["GET inv-c /actuator/health"]
    HA --> F["Healthy instance list"]
    HB --> F
    HC --> F
    F --> L["Spring Cloud LoadBalancer"]
    L --> R["Business request to selected instance"]
~~~

Probes help detect instances whose endpoint is unresponsive or reporting an unacceptable status. However, with client-side health checks, **each caller process can run its own checks**, rather than sharing a single centralized check result. When `order-service` has 200 replicas, you cannot assume all 200 replicas share just one probe cycle.

Also distinguish:

- **Service instance lookup**: fetching the host/port list from discovery.
- **Health check**: evaluating whether instances in the list are healthy enough to be candidates.
- **Load balancing**: picking an instance from the candidate set.
- **Business HTTP request**: executing actual work on the chosen instance.

Reading discovery data faster does not automatically reduce health probe counts. Conversely, probing health more frequently does not make the registry reflect changes faster if the discovery source itself propagates changes slowly.

## 2. Load Amplification as Caller Count Grows

Suppose there are:

- `C` caller processes, each with a health-check supplier for the same service.
- `I` target instances probed by each caller.
- `T` seconds between check cycles.
- Each cycle probes each instance once, excluding retries or refresh-triggered probes.

We can estimate the **system-wide average probe rate**:

\[
R_{\text{probe}} \approx \frac{C \times I}{T}
\]

This is an estimation model for capacity planning, not a guarantee that an implementation always sends exactly one request per instance every cycle. How the supplier refreshes its list, initialization timing, repeated-check settings, and error-handling behavior can all shift actual load.

### Medium-Scale Example

Suppose there are 240 callers, each seeing 8 instances, with a 10-second health check interval:

\[
R_{\text{probe}} \approx \frac{240 \times 8}{10}=192
\]

Roughly **192 probes/second** are generated across the instance set, excluding health checks from ingress, registry, Kubernetes, or monitoring.

If the interval is increased to 60 seconds in an environment where that is acceptable:

\[
R_{\text{probe}} \approx \frac{240 \times 8}{60}=32
\]

Average probe rate drops from roughly 192 to 32 requests/second—an **approximately 6x reduction**. However, detection time for a failed instance via this polling mechanism may become longer. Thus increasing the interval is not the only answer: choose a reliable health source and understand fault tolerance during the transition window.

### Larger Scales

| Caller count | Instances probed/caller | Interval | Estimated probes/second |
|---:|---:|---:|---:|
| 20 | 4 | 30 seconds | 2.7 |
| 100 | 10 | 30 seconds | 33.3 |
| 240 | 8 | 10 seconds | 192 |
| 240 | 8 | 60 seconds | 32 |
| 1,000 | 20 | 10 seconds | 2,000 |

With multiple target services, sum the estimated load across each caller–service ID pair. On a single target instance, the average probe rate from 240 callers with a 10-second interval is roughly `240/10 = 24` requests/second, assuming every caller checks that instance.

These figures exclude spikes caused by retries, list changes, other health checkers, or schedule synchronization across callers.

## 3. Average Load Differs from Burst Spikes

The calculation above averages over time. It does not reveal whether probes arrive evenly spaced or bunched in bursts.

For example, a deployment starts 200 callers almost simultaneously. If all begin their first health check cycle right after the same `initial-delay`, many callers can hit the same instance within a very short window:

~~~mermaid
sequenceDiagram
    participant A as Caller A
    participant B as Caller B
    participant C as Caller C
    participant I as Inventory instance
    Note over A,C: Many callers start in the same rollout
    A->>I: GET /actuator/health
    B->>I: GET /actuator/health
    C->>I: GET /actuator/health
    I-->>A: 200
    I-->>B: 200
    I-->>C: 200
~~~

At the scale of hundreds of callers, even a simple endpoint can suffer noticeable connection spikes. When a health endpoint invokes expensive dependencies, the effect is amplified: probes from many callers can hit the database, message broker, or authentication system simultaneously.

**Key distinction:** increasing the interval lowers the *average rate*, but does not by itself guarantee avoiding synchronized probe bursts.

To reduce synchronization:

- Avoid starting all callers or refreshing all health checkers at the exact same instant when possible.
- If custom scheduling is needed, consider jitter to stagger probe timing.
- Cap concurrent probes at the probing or receiving side where the system supports it.
- Do not assume Spring Cloud LoadBalancer includes a built-in jitter toggle in every version; use only mechanisms your actual version and implementation provide.
- Measure requests/second at fine enough granularity to spot spikes, rather than looking only at 1-minute averages.

## 4. Distinguishing Sources of Health Information

Not every “is the instance healthy?” decision needs to be re-checked by every caller. A system may already hold health information across several layers:

| Layer | Who executes | Primary goal | Keep in mind |
|---|---|---|---|
| **Liveness probe** | Operational platform, e.g., Kubernetes | Decide when to restart a container | Not synonymous with readiness to take traffic. |
| **Readiness probe** | Operational platform | Decide whether an instance belongs in the traffic-serving endpoint set | Can be reflected in instance lists via discovery adapters. |
| **Registry health/status** | Eureka, Consul, or equivalent | Register and publish service status | Freshness depends on heartbeats, leases, watches, or refreshes. |
| **LoadBalancer health-check supplier** | Each caller application using this supplier | Add instance availability checks before selection | Risks multiplying probes by caller count. |
| **Timeout/circuit breaker** | Caller on business requests | Bound wait times and react to real call errors | Does not fully replace health or discovery. |

Each layer has a distinct purpose. For instance, Kubernetes readiness can remove a Pod from traffic endpoints. If the caller's discovery client already receives a list containing only ready endpoints, adding another round of HTTP health checks from every caller may offer little extra value while creating many redundant requests.

Conversely, if the registry only knows an instance is “registered” without guaranteeing its application endpoint works, an additional health-check mechanism may be worthwhile.

**The first design question is not “what interval should we set?” but “where do we already have a reliable health signal?”**

## 5. Choose One Primary Check Mechanism, Avoid Needless Duplication

No single approach fits every system. Consider typical cases.

### Case A: Kubernetes and Discovery Already Supply Only Ready Endpoints

If the client uses a discovery adapter that returns a readiness-filtered endpoint list and the list updates fast enough, a sound choice is to let the platform handle readiness and **avoid enabling an extra per-caller health-check supplier** unless a clear need is established.

Benefit: avoids multiplying HTTP probes from every caller. Trade-off: selection quality relies on readiness signals, discovery update speed, and operational policies.

### Case B: Eureka or Consul Already Tracks Health

When the registry performs checks or receives appropriate status updates and supplies available instances, you can rely on that signal as the primary source. Verify that the registry actually filters or marks status in a way the application's discovery client understands.

Do not assume “using Eureka” means every application fault is detected instantaneously. Heartbeats, lease expiration, and registry refreshes still incur lag. Depending on failure detection requirements, you may still need timeouts, controlled retries, or a narrower-scoped health checker.

### Case C: Discovery Only Supplies Addresses with No Reliable Health Signal

In some environments using static lists or discovery without availability checks, a caller-side health-check supplier can reduce choosing dead instances. In that case:

1. Limit the check interval to what meets failure-detection goals.
2. Use a lightweight, unambiguous, easily reachable health endpoint.
3. Account for the number of callers running probes.
4. Measure error rates from stale instances before and after enabling the mechanism.
5. Test behavior when the healthy list becomes empty.

A caller-side supplier **is not a system-wide shared health checker**. To truly curb probe volume at large scale, moving checks to a shared source such as the registry or platform may be necessary, when suitable.

## 6. Configuring HealthCheckServiceInstanceListSupplier

Once client-side health checking is deemed necessary, you can build a supplier chain using `HealthCheckServiceInstanceListSupplier` through Spring Cloud LoadBalancer's builder.

Example per-service configuration for `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

Register the configuration for the specific service ID:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryHealthLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

`InventoryHealthLoadBalancerConfiguration` should stay outside normal component scan or be excluded from scanning. It is referenced by `@LoadBalancerClient` for use in that service ID's LoadBalancer context. Avoid letting a supplier bean meant solely for `inventory-service` become globally applied.

Specific builder methods and check forms depend on the Spring Cloud version, discovery client, and reactive/blocking dependencies. This example illustrates the structure: **discovery source → health-check decorator → candidate set**. Do not declare multiple competing `ServiceInstanceListSupplier` beans inside the same LoadBalancer context.

## 7. Tuning Interval, Initial Delay, and Health Path

Spring Cloud LoadBalancer provides health-check configuration properties; in supporting versions, an illustrative configuration looks like:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 10s
        interval: 45s
        path:
          inventory-service: /actuator/health/readiness
~~~

Meaning:

- `initial-delay`: delays the first check cycle after the health-check supplier starts.
- `interval`: duration between check cycles according to the supplier's mechanism.
- `path.inventory-service`: dedicated health path for the target service ID, instead of using one default path for every service.

These are **illustrative values**, not an optimal setup for every system. Properties take effect only when the health-check supplier is actually created and supported by your Spring Cloud version; declaring properties alone does not automatically enable health checks across every application.

With Spring Boot Actuator, health probes can be enabled in the **target** application when the environment requires it:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Practical notes:

- `/actuator/health/readiness` must exist and be reachable from the **caller** or probing component.
- If Actuator runs on a separate management port, verify the active health-check mechanism actually targets the right host and port; changing `path` alone may not suffice.
- If the health endpoint requires authentication, account for the supplier's ability to send valid credentials; do not expose a sensitive management endpoint to the Internet just to make health checks pass.
- When using a context path or custom endpoint configuration, verify the resulting URL.
- Paths and related properties can vary across Spring Cloud release trains; verify against the docs for your deployed version before copying examples verbatim.

### Choosing Interval Based on Failure Detection Requirements

If the health checker is the sole detector of dead instances, longer intervals prolong the risk of picking failing instances. If the registry already provides a fast-updating readiness signal, polling every few seconds from every caller may bring little proportional value.

Define a **failure-detection target** first, then select intervals and supporting policies, rather than defaulting to “as fast as possible.”

## 8. Health Endpoints Must Be Cheap and Meaningful

A health endpoint can become the biggest source of load if every check runs costly queries.

For example, an overly heavy health endpoint might:

- Query the database with full-table scans or unbounded queries.
- Fan out simultaneously to multiple downstream services to “measure everyone's health.”
- Open new connections to a broker or database on every probe.
- Execute write operations to test transaction capability.
- Make HTTP calls to an external auth system on every check.
- Produce verbose logs or heavy computation unnecessarily.

When hundreds of callers probe together, these operations multiply and can trigger a **cascading failure**: health requests themselves slow down a dependency, causing health checks to fail, causing more clients to evict more instances from their candidate sets.

### Readiness Should Reflect Serving Capability

Do not go to the other extreme of a “hardcoded 200” endpoint just to stay cheap. If a dependency is genuinely essential, readiness status should reflect whether the application can safely serve requests.

The solution is **choosing efficient signals**:

- Use readiness state maintained and updated by the application across its lifecycle, rather than running expensive work on every HTTP GET.
- Use health indicators with reasonable timeouts and limit directly checked dependencies.
- If deep, costly checks are needed, consider running them separately on a schedule and publishing the latest cached state with explicit freshness requirements.
- Do not let liveness and readiness share inappropriate dependencies: a slow downstream is not automatically a reason to restart the entire process.

Health endpoints should be **side-effect-free**, return concise responses, and avoid leaking secrets. Protect endpoints with network policies or appropriate internal access controls.

## 9. Coordinating with Caching and Discovery Refreshes

A health-check supplier usually receives instance lists from discovery or another supplier. If the discovery snapshot is stale, health checks can keep probing an instance the registry has already removed.

Conversely, if a new instance has not appeared in the caller's snapshot yet, the health checker cannot probe it either.

~~~text
Registry / discovery adapter
          |
          v
ServiceInstance list at caller
          |
          v
HealthCheckServiceInstanceListSupplier
          |
          v
Instances currently considered healthy
          |
          v
LoadBalancer picks target
~~~

Do not confuse two kinds of “freshness”:

1. **Discovery freshness:** how up-to-date the instance list seen by the caller is.
2. **Health freshness:** how recently existing instances' healthy status was checked.

Raising health-check frequency does not improve discovery freshness. Raising registry refresh frequency does not guarantee endpoints are healthy.

In the supplier chain, caching and health-check decorators must be arranged per the guidance and semantics of your version; do not blindly enable both layers simply because both exist. In particular, when the discovery client already maintains a registry snapshot, adding extra caching in LoadBalancer can prolong retention of stale instances.

If health checks already exist at the registry or platform, turning off caller-side health checks can reduce load far better than merely stretching the interval.

## 10. Mass Startups, Autoscaling, and Jitter

When multiple caller replicas spin up during the same autoscale event or rolling deployment, their start times are often close together. If all initialize health-check suppliers together with the same `initial-delay`, their first probes can align in time.

Strategies to flatten peaks:

| Strategy | Benefit | Trade-off / note |
|---|---|---|
| Stagger caller rollouts | Reduces processes starting probes simultaneously | Deploy/autoscale takes slightly longer |
| Suitable initial delay | Avoids probing while context is not ready yet | Delays only the first round; does not create jitter itself |
| Jitter in custom schedulers | Spreads probe rounds out of phase | Requires an implementation or config that actually supports it |
| Concurrency limits | Prevents flooding health endpoints with connections | Queued probes can delay health status updates |
| Rely on registry health signals | Eliminates repeated HTTP checks per caller | Depends on registry freshness and reliability |
| Longer interval | Lowers average load | Can increase detection time for failed instances |

Never assume `initial-delay` acts as jitter. If every caller uses the same initial delay after a simultaneous startup, check cycles can still stay synchronized.

Additionally, avoid automatically adding retries to every individual probe just “to be sure.” When a health endpoint is overloaded, simultaneous probe retries can worsen the load spike.

## 11. Timeouts, Retries, and Failure Amplification Loops

Examine health-check traffic in relation to business HTTP traffic.

Dangerous scenario:

1. One instance slows down under overload.
2. Many callers send health probes to that instance at once.
3. Health probes also time out or return errors.
4. Callers evict that instance from their candidate sets.
5. Business traffic concentrates onto the remaining instances.
6. Remaining instances overload and start failing health checks too.

~~~mermaid
flowchart TD
    A["Instance A slows down"] --> B["Probes from many callers add latency"]
    B --> C["Some callers evict A"]
    C --> D["Traffic shifts onto B/C"]
    D --> E["B/C overload too"]
    E --> F["B/C health checks fail"]
    F --> G["Candidate set shrinks further"]
    G --> D
~~~

This is a common negative feedback loop when health policies are overly sensitive to transient fluctuations.

Mitigations include:

- Design cheap, low-dependency health endpoints with clear timeouts.
- Avoid evicting an instance on a single transient blip if the system needs anti-flapping behavior; state retention, consecutive failure thresholds, or hysteresis must be implemented per actual policy.
- Bound retries and prevent aggressive retry storms in both probe and business HTTP layers.
- Distinguish connection failures from business errors returning `4xx`; do not treat every application error as proof the whole instance is dead.
- Prioritize alerts and load observability over letting every caller react independently to noisy measurements.
- Ensure overall timeouts do not multiply unboundedly across retry layers.

Spring Cloud LoadBalancer does not automatically provide full hysteresis, circuit breakers, or retry budgets simply by adding `withHealthChecks()`. Where needed, design and configure them in the appropriate components.

## 12. When Should Caller-Side Health Checks Be Disabled?

Consider **not using a per-caller health-check supplier** when:

- The registry or platform already supplies an instance list reflecting proper readiness.
- Caller discovery updates lists fast enough relative to recovery targets.
- Re-checking every instance from hundreds of callers does not meaningfully raise success rates.
- Most load on the health endpoint comes from redundant probes.
- The system already has timeouts, controlled retries, and mechanisms reacting to real request failures.

When choosing not to enable the health-check supplier, still test actual recovery behavior. A registry that reflects true status yet updates too slowly can send many requests to dead instances. Fixes may include tuning heartbeats/readiness/registry refreshes, or adding bounded failover mechanisms.

If caller-side health checks are still needed, target **only the specific services that genuinely require them**, rather than enabling them by default for every service ID in every application.

## 13. Measuring Health Check Load by Service and Instance

Optimization cannot be evaluated by tracking total HTTP requests alone. Separate business requests from health requests.

Measurements to collect:

| Metric | Meaning |
|---|---|
| `health_probe_requests_total` | Probes sent/received over a time period |
| `health_probe_duration` | Probe response latency |
| `health_probe_failures` | Probe timeouts, connection errors, or unhealthy reports |
| `health_probe_in_flight` | Concurrent probes currently in progress |
| `supplier_candidate_count` | Number of instances provided by the supplier |
| `loadbalancer_no_instance` | Count of times no instance was available |
| HTTP `5xx`/timeouts | Actual business communication quality |
| `readiness` transitions | Frequency of instances flipping healthy/unhealthy |

These names are **illustrative metric names** for building dashboards; they do not imply Spring Cloud LoadBalancer or Micrometer automatically emits all metrics under these exact names. Use actual metrics exposed by your application's Actuator/observation setup, or add required instrumentation.

Regarding cardinality, avoid using request IDs as metric labels. Service ID and instance ID can serve as bounded labels for observability goals, provided scale and instance churn are accounted for so time-series counts do not explode.

### Forecasting Beforehand and Comparing Measurements

Suppose 240 callers, 8 instances, 10-second interval:

~~~text
Prior estimate:  240 × 8 / 10 = 192 probes/s
After changing to 60s: 240 × 8 / 60 = 32 probes/s
Target: reduce average probe load by ~83%
~~~

If measured load drops by less, health checks from the registry, Kubernetes, monitoring, or another supplier chain may still be active. If probe counts far exceed the estimate, look for retries, multiple contexts/callers, additional service IDs, or extra refresh loops.

**Do not measure probe volume alone.** Track business request success rate, failed-instance detection latency, and recovery latency when instances return at the same time.

## 14. Hands-on Verification in Local or Staging Environments

The goal of this exercise is to observe load amplification and the effect of reducing probes—not to treat sample numbers as production commitments.

### Setup

- Run two or three `inventory-service` replicas, each exposing `/actuator/health/readiness` or an equivalent health path.
- Run two or more `order-service` caller processes with `@LoadBalancerClient` and a configured health-check supplier.
- Ensure service discovery or the static instance list contains all replica hosts/ports.
- Enable logs or metrics on the health endpoint to count probes arriving at each instance.
- If also tracking business requests, use an endpoint returning `instanceId` to observe LoadBalancer target selection.

### Steps

1. Keep all instances healthy, holding caller count and replica count fixed.
2. Observe health requests over a window long enough to cover several cycles, e.g., 5 minutes.
3. Compare actual probe counts against the `C × I / T` estimate.
4. Keep target replicas fixed while increasing callers, e.g., from 2 to 4; verify whether probe load scales proportionally.
5. Keep caller count fixed and vary `interval` in staging; compare probes/second, latency, and peaks.
6. Stop one replica and measure the time from failure until the supplier stops returning it.
7. Restore the replica and measure how long it takes to rejoin the candidate set.
8. Record scenarios where the list becomes empty and how the HTTP client behaves.
9. If the platform provides reliable readiness/registry health, try turning off the caller-side health-check supplier and compare total probes alongside business error rates.

With static `SimpleDiscoveryClient`, stopping an instance **does not automatically remove it from the discovery source**. The health-check supplier can mark it unhealthy, yet its address stays in configuration. When turning off per-caller health checks, you need another mechanism to avoid picking dead hosts.

### Observation Table

| Scenario | Callers | Interval | Measured probes/second | P95 health latency | Failed business requests |
|---|---:|---|---:|---|---|
| Before optimization | 2 | 10s | Record after test | Record after test | Record after test |
| More callers | 4 | 10s | Record after test | Record after test | Record after test |
| Longer interval | 4 | 45s | Record after test | Record after test | Record after test |
| Rely on registry readiness | 4 | Per-caller check off | Record after test | N/A for LB checker | Record after test |

This table is only a data-recording template; no executed benchmark results are implied.

## 15. Remediation Workflow When Health Endpoints Are Overloaded

~~~mermaid
flowchart TD
    A["Health endpoint sees high QPS/latency"] --> B{"Where are probes coming from?"}
    B -- "Many app callers" --> C["Compute callers × instances × interval"]
    B -- "Registry / platform / monitor" --> D["Inspect each active health checker"]
    C --> E{"Does per-caller check add value?"}
    E -- No --> F["Rely on shared health signal if reliable"]
    E -- Yes --> G["Lower frequency, avoid sync, cap cost"]
    D --> H["Remove redundant duplicate checks"]
    F --> I["Re-measure load and error rate"]
    G --> I
    H --> I
    I --> J{"Are failure detection and recovery still acceptable?"}
    J -- No --> K["Adjust interval/discovery/timeout/health policy"]
    J -- Yes --> L["Keep config and monitor"]
~~~

Common configuration mistakes:

- Enabling the health-check supplier on every caller even though the registry already provides reliable readiness results.
- Setting an interval far shorter than actual failure-detection requirements.
- Starting all callers simultaneously, leading to in-phase probe bursts.
- A health endpoint running costly queries or downstream calls on every probe.
- Running both platform and per-caller health checks without accounting for combined load.
- Mistaking `initial-delay` for a jitter mechanism.
- Lacking sensible probe timeouts, leaving many connections hanging.
- Enabling aggressive retries when the health endpoint stops responding.
- Setting the wrong health path or an unreachable management port, marking healthy instances down while the app is fine.
- Treating reduced health probe volume as success without measuring impact on business error rates.

## 16. Pre-Large-Scale Deployment Checklist

| Check question | Required evidence |
|---|---|
| How many callers and target replicas exist? | Estimate `C × I / T` per service ID |
| Who is emitting health probes? | Explicit inventory: platform, registry, LB callers, monitoring |
| Is the primary health source reliable enough? | Tested readiness and discovery propagation delay |
| Is a per-caller supplier strictly necessary? | Concrete rationale and measurable benefit |
| Is the health endpoint lightweight? | No heavy downstream load per check |
| Are interval and initial delay reasonable? | Values match failure-detection goals and allowable load |
| Is schedule synchronization a risk? | Measured peak QPS and considered stagger/jitter |
| Is the supplier scoped to the right service ID? | `@LoadBalancerClient` and bean scope verified |
| Are health path and management port correct? | Reachable from callers with proper security policy |
| Are retries/timeouts and fallback clear? | No failure amplification loops or infinite retries |
| What if all instances become unhealthy? | Predictable and observable no-instance behavior |
| Measured before and after optimization? | Probe QPS, P95, error rate, detection/recovery times |

## 17. Summary

- A client-side health-check supplier can send probes from **each caller** to **multiple instances** of a target service. Average load scales roughly with `callers × instances / interval`.
- When many callers start simultaneously, probes can also **spike in bursts**; raising the interval does not automatically introduce jitter.
- Distinguish Spring Cloud LoadBalancer health checks from platform readiness/liveness and discovery registry signals.
- If the registry or platform already supplies a sufficiently reliable health signal, **avoid enabling redundant per-caller health checks**.
- When `HealthCheckServiceInstanceListSupplier` is genuinely needed, use lightweight endpoints, appropriate intervals, narrow service scoping, and evaluate failure-detection lag.
- Caching, health checks, timeouts, and retries solve different problems; poor coordination can trigger excess traffic or overload amplification loops.
- A good optimization reduces check overhead **without degrading failed-instance detection, recovery, or business request success rates**.

When considering the entire system rather than just a single caller, you can tell when to trust shared health signals, when to keep client-side health checks, and how to control probe volume so Spring Cloud LoadBalancer routes reliably without putting extra strain on target services.
