# Load Testing During Mass Startup and Cluster-Wide Recovery

## 1. Why Measure These Two Scenarios?

A microservice system may operate smoothly with all instances running yet run into trouble when many instances start up at once or when an entire registry cluster just recovered. During those moments, multiple components generate work simultaneously:

- Applications initialize their Spring contexts, connect to databases, populate caches, and warm up.
- Many clients register services, send heartbeats, and fetch the registry simultaneously.
- The registry updates state, replicates data, and runs health checks.
- Consumers refresh discovery caches and start sending requests to the new instances.
- The Kubernetes scheduler, kubelet, EndpointSlice controller, and API Server process Pod/Service changes.
- DNS, gateways, service meshes, message brokers, and databases receive extra connections or retries.

If you only measure business endpoint throughput in steady state, operations teams will miss **startup storms** and **recovery storms**. Both scenarios can overload the registry, API Server, or dependencies even when overall business request volume is not yet high.

The goal of testing is to determine how many instances can start concurrently, how long it takes them to become ready, the peak load the registry/control plane must absorb, and how long it takes the entire cluster to return to SLO after an incident.

## 2. Distinguishing Startup Storms and Recovery Storms

| Scenario | What Happens Concurrently? | Primary Risk |
|---|---|---|
| Cluster-wide cold start | All applications and registry clients initialize from a cold state | CPU/GC, DNS, database connections, registrations, and registry fetches spike abruptly |
| Large scale-out | Many new replicas are created within a short window | Registration bursts, health check bursts, image pulls, and warm-up compete for resources |
| Registry restart | Eureka/Consul server or part of the control plane restarts | Client reconnects, retries, full registry fetches, leader election, and replication |
| Network partition recovery | Nodes and clients reconnect after a network outage | Bursting heartbeats/fetches, catalog reconciliation, and divergent cache data |
| Node/pool recovery | Many Pods get rescheduled after a node failure or maintenance | Scheduler, image registry, API Server, CNI, DNS, and dependencies all hit by load |
| Dependency recovery | External database/broker/API comes back online | Retry queues and connection pools of many services resume activity together |

Startup storms typically begin from a deployment or scaling action. Recovery storms can happen after an incident without any new deployment. Measure each type separately to locate the exact bottleneck.

## 3. Quantities to Measure

Do not record only CPU and request counts. A thorough benchmark needs timestamps, peak loads, latencies, errors, and registry convergence levels.

### 3.1. Instance Lifecycle Milestones

| Milestone | Definition |
|---|---|
| `t0` | Timestamp when the create or start instance command is issued |
| `t_process` | Process/JVM begins running |
| `t_server` | Web server binds port and begins listening |
| `t_registered` | Registry accepts registration or platform creates endpoint |
| `t_ready` | Application readiness flips to allow traffic |
| `t_visible` | Consumer polls discovery and sees an eligible instance |
| `t_first_ok` | First business request to the instance succeeds |
| `t_failure_recovery_start` | Timestamp when recovery begins after incident resolution or end of fault injection |
| `t_slo` | Timestamp when key metrics (latency, error rate, throughput) return to defined SLOs |

From these milestones you can compute:

- **Startup duration:** `t_ready - t0`.
- **Registration duration:** `t_registered - t0`.
- **Discovery propagation delay:** `t_visible - t_registered`.
- **Time to first successful request:** `t_first_ok - t0`.
- **Recovery time:** `t_slo - t_failure_recovery_start`, measured from when recovery begins after an incident until traffic stays within SLO across a confirmation window.

Not every registry has an identical `registered` event. With Kubernetes, you can use when the Pod/Service is created and EndpointSlice marks the endpoint ready. With Eureka/Consul, use client and server logs/metrics to pinpoint registration acceptance, then verify from the consumer.

### 3.2. Load and Quality Metrics

| Group | Metrics to Collect |
|---|---|
| Application | Startup duration, time-to-ready, CPU, memory, GC pauses, thread counts, connection pools, queue depth |
| Discovery client | Register/renew/fetch counts, request latency, retry counts, timeouts, cache refresh duration, visible instance count |
| Registry server | Request rate, p50/p95/p99 latency, 4xx/5xx, CPU, heap, GC, thread pool, connection counts, queue/backlog |
| Health check | Checks/s, pass/warning/critical, check duration, timeouts, and state transitions |
| Kubernetes control plane | API request rate/latency, 429/5xx, inflight requests, watch reconnect/relist, EndpointSlice update delay, etcd latency |
| Infrastructure | DNS latency/errors, network throughput, conntrack, packet loss, disk I/O, node pressure, and image pull duration |
| Business traffic | Request rate, p50/p95/p99, error rate, timeouts, retries, saturation, and requests sent to unready instances |
| Recovery | Time to registry healthy, time to all instances visible, time to SLO, stale instance count, and remaining retry backlog |

Always record metrics over short time windows fine enough to reveal load spikes. A 5-minute average can hide a 5-second burst.

## 4. Estimating Load Before Running Tests

The formulas below help estimate baseline load. They do not replace peak load measurement because clients can synchronize when they send requests.

Suppose:

- `N`: number of instances being started.
- `S`: window over which instances are staggered to start.
- `H`: heartbeat/renewal interval.
- `C`: number of consumers performing registry fetches.
- `F`: registry fetch interval of one consumer.
- `Q`: number of health checks per instance per second.

Approximate average load:

\[
R_{register} \approx \frac{N}{S}
\]

\[
R_{heartbeat} \approx \frac{N}{H}
\]

\[
R_{fetch} \approx \frac{C}{F}
\]

\[
R_{health} \approx N \times Q
\]

Illustrative example: 900 instances staggered over 90 seconds corresponds to roughly 10 registrations per second. If 900 instances start within the first few seconds, peak load can be far higher than the 10/second average. If every client retries in lockstep after timing out, actual load increases further.

### 4.1. Why Averages Are Not Enough

Suppose 1,000 clients share the same 30-second fetch interval and start at the exact same moment. The theoretical average is roughly 33 fetches/second, yet if timers are created nearly in phase, many requests can hit the server in the same short window. You must inspect histograms at one-second or finer resolution to detect this phenomenon.

Intervals and defaults must come from the running version and configuration. For instance, current Spring Cloud Netflix documentation publishes `eureka.client.registry-fetch-interval-seconds` defaulting to 30 seconds; Eureka clients also use periodic heartbeats. Never extrapolate real load solely from defaults because client counts, retries, full fetches, peer replication, and registry size all matter.

### 4.2. Retry Load Can Amplify Bursts

If `N` clients time out together and retry after a fixed delay, the next retry wave creates another burst. Use exponential backoff with jitter to spread out retry attempts:

\[
delay_k = U\left(0,\; \min(delay_{max}, delay_{base} \times 2^k)\right)
\]

Where `U(0,x)` is a random value between 0 and `x`. Combine retry limits, timeouts, retry budgets, and circuit breakers at the service call layer. Do not retry infinitely or retry all 4xx errors.

## 5. Designing Repeatable Tests

### 5.1. Preparing the Environment

The test environment must match production closely on factors affecting results:

- Same registry type, node count, replication/peer topology, and health check configuration.
- Equivalent instance count, registry size, service count, and consumer count to target scale.
- Equivalent CPU/memory limits, JVM heap, garbage collector, network, and storage.
- Same deployment approach, DNS, gateway, service mesh, database, and message broker.
- Same versions of Spring Boot, Spring Cloud, Eureka/Consul/Kubernetes, and client libraries.
- Synchronized clocks across load generators, applications, and registry for comparing timestamps.

Do not use an empty registry if production has thousands of services/instances. Registry size affects fetch payloads, serialization, memory, and cache refresh duration.

### 5.2. Separating Control Plane and Data Plane Load

Run at least two measurement tracks:

1. **Control plane load:** registration, heartbeats, fetches, health checks, Kubernetes API watch/list, leader election, and replication.
2. **Data plane load:** business requests through the gateway, Kubernetes Service, or Spring Cloud LoadBalancer.

If you only generate HTTP requests to applications without observing the registry/control plane, the test fails to measure registration pressure. Conversely, firing requests only at registry endpoints does not represent business traffic.

### 5.3. Defining Target Load Levels

At a minimum, determine:

- Current instance count and maximum instance count.
- Number of instances that can start in one minute and in one second in the worst-case scenario.
- Consumer count and fetch/refresh intervals.
- Health checks per instance and check intervals.
- Registry size, average metadata, and churn rate.
- Normal business request rates and peaks during rollouts.
- Maximum acceptable recovery time.

Document assumptions before running. Never tweak parameters mid-run without recording them, as doing so invalidates comparisons.

## 6. Core Test Scenarios

### 6.1. Steady-State Cluster Baseline

1. Start all services using the normal procedure.
2. Wait for the registry and traffic to stabilize.
3. Generate baseline business traffic for a sufficiently long period.
4. Record CPU, memory, GC, registry request rate, health checks, p95/p99, and error rate.

The baseline serves as the reference point for every subsequent scenario. If the system is unstable at baseline, do not run startup storms yet.

### 6.2. Mass Simultaneous Startup of All Instances

1. Stop or scale down to a predefined test state.
2. Keep the registry running to isolate client-induced load.
3. Issue commands to start `N` instances within a very short window.
4. Monitor registrations, heartbeats, fetches, health checks, and time-to-ready.
5. Verify consumers see all instances and requests only reach ready instances.
6. Repeat with varying values of `N` and startup windows.

Do not record only when the first instance becomes ready. Record p50/p95/p99 of `t_ready`, when the last instance becomes ready, and the percentage of instances that failed to register.

### 6.3. Staged Scale-Out Waves

Test controlled replica increases, such as 10%, 25%, 50%, and 100% of target scale. Wait for stabilization between waves or explicitly note if deliberately overlapping waves.

The goal is to find the threshold where:

- Registry latency starts climbing rapidly.
- Registration retries or timeouts appear.
- Service database/connection pools saturate.
- Time from registration to consumer visibility exceeds target.
- Business traffic error rate breaches SLO.

### 6.4. Restarting the Registry While Clients Are Running

Follow the topology and failover procedures of each registry:

- Restart one registry node in an HA cluster while keeping peer nodes up.
- In a dedicated test environment, restart nodes sequentially and verify quorum/leader/peer recovery.
- Observe client reconnects, retries, registry re-fetches, and retention of stale caches during disconnects.
- Check after registry recovery: does data converge, do new instances appear, and are old instances retained too long?

Never restart the entire registry simultaneously in production to generate test load. To test full-cluster loss, use an isolated environment with equivalent data and topology.

### 6.5. Simulating a Network Partition and Recovery

1. Controlled-block network paths between a group of clients and the registry, or between peers.
2. Maintain business traffic within safe bounds to observe behavior while the registry is disconnected.
3. Record retries, timeouts, stale caches, health states, and visible instance counts.
4. Restore network connectivity.
5. Measure time for heartbeats/fetches/replication to normalize and time for the registry to converge.
6. Verify requests do not pile onto a subset of instances due to divergent discovery views.

This scenario is especially important for Eureka self-preservation and Consul catalog replication. The registry may preserve old records to avoid falsely evicting instances during a network outage; consumers must still time out quickly and handle unresponsive instances.

### 6.6. Node Failure and Mass Rescheduling

In Kubernetes, simulate a node drain or node loss in a test cluster. Observe the scheduler, image pulls, Pod startups, readiness probes, EndpointSlice updates, API Server, and etcd. Also monitor image registry and CNI load because they can prolong startup even when the discovery client is not the bottleneck.

### 6.7. Dependency Recovery After an Outage

Temporarily slow down or sever the database/broker in a test environment, then restore it. Check whether connection pools reopen simultaneously, whether retry queues dump backlogs, and whether readiness transitions appropriately. A healthy registry does not mean business dependencies have recovered.

## 7. Load Generation and Metric Collection Tools

### 7.1. Generating Business Request Load with k6

k6 is well-suited for generating HTTP load at a controlled arrival rate. Send requests through the exact traffic path the application will use in production; do not use registry endpoints as a proxy for business requests.

Example of ramping up request rate:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    payment_traffic: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 500,
      stages: [
        { target: 50, duration: '2m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000']
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/api/payments?limit=10`);
  check(response, {
    'response is successful': (r) => r.status === 200
  });
}
```

URLs and thresholds in the example are illustrative; replace them with read-only business endpoints carrying near-production cost and your system's SLOs. Do not use liveness/readiness endpoints as primary data-plane load. If an endpoint mutates data, use isolated test data and cleanup mechanisms. To trigger a startup storm, orchestrate instance creation separately; k6 only generates HTTP requests.

### 7.2. Orchestrating Scaling in Kubernetes

In a test cluster, you can use `kubectl scale` to trigger a replica surge:

```bash
kubectl scale deployment/payment-service --replicas=100 -n payments
kubectl rollout status deployment/payment-service -n payments --timeout=10m
```

To simulate a heavy burst, scale from a low replica count to a high count in one step. To simulate a safe rollout, configure a Deployment strategy with appropriate `maxSurge` and `maxUnavailable`. Do not use the same test to draw conclusions for both scenarios, because one creates a burst while the other rate-limits Pod replacement.

Example rollout limiting how many extra Pods are created at once:

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
```

`maxSurge: 2` allows at most two Pods above the desired replica count during rollout; `maxUnavailable: 0` requires maintaining all desired available replicas per Deployment conditions. This is an example; balance against quotas, node capacity, and application readiness duration.

### 7.3. Collecting Metrics

- Prometheus/Grafana: scrape application, registry, node, Kubernetes control plane, and dependency metrics.
- Spring Boot Actuator/Micrometer: HTTP server/client, JVM, datasource, executor, cache, and custom startup timers.
- Timestamped logs: register success/failure, heartbeat/fetch, retries, health transitions, and readiness transitions.
- Kubernetes: `kubectl get events`, Pod conditions, EndpointSlice, API Server metrics, and etcd metrics.
- Load generator: request rate, latency distribution, error rate, dropped iterations, and active VUs.

Synchronize clocks and attach `serviceId`, `instanceId`, `region`, `zone`, and `testRunId` to logs to correlate across metric sources.

## 8. Metrics and Characteristics to Observe by Registry

### 8.1. Eureka

The Eureka Client registers instances, sends heartbeats/renewals, and fetches the registry cache. When many clients start together, the server can absorb a registration burst, followed by heartbeats and registry fetches. If delta caches fail to reconcile after a disruption, clients may fall back to full registry fetches, driving higher payload and CPU costs.

Points to observe:

- Register, renew, cancel, and registry fetch requests per second.
- HTTP timeout/5xx rates and p95/p99 latency for requests to Eureka Server.
- Registry payload size, deserialization/cache refresh time, and client/server GC.
- Peer replication lag, peer request failures, and count of servers with divergent registry views.
- Heartbeat renewal rate and self-preservation status.
- Counts of `UP`, `DOWN`, `OUT_OF_SERVICE` instances and stale records.

Spring Cloud Netflix currently sets `eureka.client.registry-fetch-interval-seconds` to 30 seconds by default; Eureka communication documentation describes a 30-second default heartbeat and periodic registry cache refreshes. Actual values depend on configuration and running release. Do not lower heartbeat/fetch intervals just to make dashboards update faster. Changing intervals can raise cluster-wide load and affect lease/eviction assumptions; test only in controlled environments and evaluate both server and consumers.

Eureka self-preservation can retain instances in the registry when heartbeats drop abnormally to avoid mass-deleting records during a network partition. During tests, note this state and verify whether consumers time out quickly and retry another instance when records are stale. Do not disable self-preservation merely to make test graphs look cleaner.

### 8.2. Consul

Applications typically register services with a local Consul Agent. The agent manages services/checks and syncs state to the catalog; agents use anti-entropy to reconcile local state with the catalog. Therefore, tests must observe both agents and Consul servers.

Points to observe:

- Register/deregister/check update counts per agent.
- Agent-to-server RPCs, connection errors, and catalog sync duration.
- Leader election, Raft commit/apply latency, replication, and server CPU/memory.
- Health checks/s, check duration, timeouts, and passing/warning/critical states.
- Time from when the agent accepts registration until catalog/query consumers see it.
- Anti-entropy syncs and how often agents must reconcile local state with the catalog.

The Consul Agent API `/agent/service/register` is the path for registering a service with the local agent; the agent sends updates to servers so the global catalog stays in sync. Consul anti-entropy spaces sync intervals according to cluster scale and agents pick randomized start offsets so nodes do not synchronize simultaneously. Use agent registration rather than writing directly to the Catalog API for normal registration flows to leverage agent state and anti-entropy.

### 8.3. Kubernetes

With Kubernetes, discovery pressure can originate from applications using the Kubernetes API directly, Spring Cloud Kubernetes DiscoveryServer, or platform controllers. Clients typically pull a snapshot via `LIST` and then track changes via `WATCH` with `resourceVersion`; when a watch expires or disconnects, clients must reconnect and may need to re-list.

Points to observe:

- API request rate/latency by resource and verb (`LIST`, `WATCH`, `GET`).
- HTTP 429/5xx, `Retry-After`, inflight requests, and API Priority and Fairness.
- Watch reconnects, relists, object counts read, and response sizes.
- etcd request/commit/fsync latency, disk I/O, and leader changes.
- Scheduler pending queue, image pull duration, Pod startup, readiness, and restart counts.
- EndpointSlice update rate and time for endpoints to flip ready/not-ready.
- Number of watchers/informers and clients holding open watches.

Prefer watches/informers over polling cluster-wide `LIST` on short intervals. When receiving HTTP 429, honor `Retry-After` and apply exponential backoff. When a watch `resourceVersion` becomes invalid, clients must relist/restart watches per Kubernetes API semantics. Some API Server versions may also reject `WATCH` or unpaginated `LIST` while the watch cache is initializing and return 429; clients must retry without forming a hot loop.

Spring Cloud Kubernetes `DiscoveryClient` can monitor the catalog and update the discovery view; some modes use caching. Behavior, properties, and watcher implementations vary by version and client type, so measure the exact starter/version running rather than inferring from another release.

## 9. Mitigating Thundering Herds and Capping Peak Load

### 9.1. Stagger Startup

Instead of starting all replicas within the same second, split into waves. Each wave creates only a fraction of instances, waiting until readiness and registry stabilize to a defined threshold before proceeding. In Kubernetes, tune Deployment rolling updates (`maxSurge`, `maxUnavailable`) or use rollout orchestration.

### 9.2. Jitter for Retries and Periodic Tasks

Add jitter so clients do not send heartbeats, fetches, or retries at the exact same instant. Apply jitter at layers you control; do not assume every registry/client randomizes all timers automatically.

### 9.3. Exponential Backoff and Retry Budgets

- Increase wait duration progressively after each transient error.
- Add jitter to retry timestamps.
- Cap maximum retry attempts or total retry duration.
- Do not retry configuration, authentication, or invalid request errors as if they were network errors.
- Use circuit breakers/bulkheads for business dependencies so one failure does not generate unbounded requests.

### 9.4. Concurrency-Limited Warm-Up

If each instance warms up by calling databases or multiple other services, cap warm-up concurrency. Use a semaphore, worker pool, or bounded queue to prevent hundreds of instances from opening connection pools or running heavy queries at once.

### 9.5. Keep Readiness False During Warm-Up

Registering or binding a port does not mean being ready for traffic. Use readiness probes/health statuses so instances enter the ready endpoint set only after warm-up completes. Liveness should not depend on every external dependency, or a database outage could trigger a restart storm.

### 9.6. Rate-Limit Recovery Operations

Set concurrency limits on recovery operations like reconnects, full fetches, resyncs, and cache rebuilds if the implementation supports them. With Kubernetes, prevent controllers from continuously relisting the entire cluster when the API Server returns 429. With Eureka, do not lower fetch/heartbeat intervals across the board without measuring the server. With Consul, let anti-entropy and agent registration operate as designed.

## 10. Sample Test Matrix and Acceptance Criteria

You can use a test matrix such as:

| ID | Scenario | Action | Metrics to Measure |
|---|---|---|---|
| T0 | Baseline | Stable cluster, background traffic | Baseline latency/error/resource usage |
| T1 | Burst 25% | Start 25% of target scale in a short window | Peak register/fetch, time-to-ready |
| T2 | Burst 50% | Start half the cluster | Timeout/retry rate, registry p95/p99 |
| T3 | Burst 100% | Start the entire cluster | Time until last instance ready and all visible to consumers |
| T4 | Scale wave | Increase replicas across multiple waves | Stable throughput and peak load reduction |
| T5 | Registry node failure | Stop one registry node in an HA cluster | Client failover, stale cache, peer recovery |
| T6 | Full registry recovery | Restore registry in an isolated test cluster | Time-to-registry-healthy and time-to-SLO |
| T7 | Network partition | Sever then restore a group of connections | Retry storms, cache reconciliation, and convergence |
| T8 | Node reschedule | Drain/lose a node in Kubernetes | Scheduler/API/EndpointSlice recovery |
| T9 | Dependency recovery | Restore database/broker | Connection storms, queue drain, and readiness |

Acceptance criteria must be defined beforehand. For example:

- 100% of target instances transition to ready within the agreed maximum startup duration.
- Registration success rate hits target; no duplicate instance IDs exist.
- Consumers see new instances within the propagation SLO.
- Zero business requests reach instances whose readiness is false.
- Registry/API Server stays within defined CPU, memory, connection, and inflight request limits.
- 429/5xx and retries do not trigger an amplification loop.
- After registry/dependency recovery, traffic p95/p99 and error rates return to SLO within target recovery time.
- No stale instances remain beyond the acceptable window.

Do not apply one fixed p95 or CPU threshold across all systems. Thresholds must reflect SLOs, cluster capacity, instance count, registry size, and application recovery requirements.

## 11. PromQL Examples for Observing Load

Actual metric names depend on Spring Boot/Micrometer, exporters, registries, and versions. The following queries illustrate measuring HTTP request rates and p95:

These examples use the `service` label; if your system does not emit this label, add an appropriate common tag/relabel or substitute an existing label such as `application`. Verify actual metrics and labels in Prometheus before using queries in dashboards.

```promql
sum by (service) (
  rate(http_server_requests_seconds_count[1m])
)
```

```promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

HTTP server error ratio:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

For the Kubernetes API Server, depending on your cluster you can monitor metrics like `apiserver_request_total`, `apiserver_request_duration_seconds_bucket`, and `apiserver_current_inflight_requests`. Filter by resource, verb, code, and client where labels are available.

For Eureka/Consul, dashboards should break metrics down by request type or operation; if granular metrics are missing, add client or proxy logs/metrics to distinguish register, heartbeat, fetch, and health checks. Do not lump everything into a single `http_requests_total` line, which makes isolating load sources difficult.

### 11.1. Template for Recording Each Test Run

| Field | Value to Record |
|---|---|
| `testRunId` | Unique identifier of the test run |
| Versions | Spring Boot, Spring Cloud, registry, Kubernetes, and client |
| Scale | Service count, instance count, consumer count, and registry size |
| Trigger | Cold start, burst %, scale wave, registry restart, partition, or node failure |
| Startup window | Seconds from first instance to last instance created |
| Peak register/fetch | Requests/second and timestamp of peak |
| Registry p95/p99 | Latency per operation |
| Errors/retries | Timeouts, 429, 5xx, retry counts, and dropped iterations |
| Time-to-ready | p50/p95/p99 and timestamp when last instance became ready |
| Time-to-visible | p50/p95/p99 and timestamp when consumers saw all instances |
| Recovery time | Time from start of recovery until SLO stabilized |
| Conclusion | Pass/fail, bottlenecks, next changes to test |

Keep this template consistent across runs to compare before/after effects of changing concurrency, jitter, rollout strategy, or registry configuration.

## 12. Analyzing Results and Finding Bottlenecks

When a test fails, check milestones and metrics in order:

1. **Instances not created in time:** check scheduler, quotas, image pulls, node capacity, and startup CPU.
2. **Process running but web server slow to bind port:** check Spring bean initialization, classpath, JIT, GC, and warm-up.
3. **Server bound port but registration slow:** check DNS, networking, registry request latency, auth/TLS, connection pools, and retries.
4. **Registration succeeded but consumers do not see it:** check heartbeat/fetch intervals, registry caches, peer replication, Consul catalog sync, or Kubernetes EndpointSlice/watches.
5. **Consumers see instance but requests fail:** check readiness, health filtering, port/scheme, routing, network policies, and dependencies.
6. **Fails to recover after outage:** check retry storms, queue backlogs, stale caches, leader election, full fetches/relists, and resource limits.

Find the earliest milestone that stretches out. Optimizing at that layer is usually more effective than scaling resources across the entire system indiscriminately.

## 13. Common Testing Pitfalls

| Mistake | Why Results Are Wrong | Fix |
|---|---|---|
| Measuring only business requests | Misses registration/fetch/control-plane load | Collect registry, API Server, and client metrics |
| Recording only 5-minute averages | Hides multi-second bursts | Use histograms and shorter scrape/rollup windows |
| Empty test registry | Payloads/caches smaller than production | Pre-populate service/instance counts near target scale |
| Load generator lacks VUs/CPU | Cannot sustain target arrival rate | Monitor dropped iterations and generator capacity |
| Using readiness endpoint as main traffic | Does not represent business cost | Use test endpoints with near-production cost |
| Changing multiple timeouts/intervals per run | Cannot tell which change had impact | Vary one parameter at a time; log versions and configs |
| Fixed retries without jitter | Creates artificial bursts or amplifies outages | Test both current config and target backoff/jitter |
| Running directly in production | Can widen a real outage | Use staging/canary or bounded, approved fault injection |
| Unsynchronized clocks | Log timestamps cannot be compared | Sync NTP/chrony and attach `testRunId` |

## 14. Checklist Before Concluding Load Tests

- [ ] A stable baseline exists before testing.
- [ ] Instance count, consumer count, service count, and registry size are recorded.
- [ ] Startup window and target arrival rate are defined.
- [ ] Registration, heartbeats, fetches, health checks, and business traffic are measured separately.
- [ ] Relevant cold starts, scale waves, registry failures, partition recoveries, and node reschedules have been run.
- [ ] Collected p50/p95/p99, error rates, timeouts, retries, and resource saturation.
- [ ] Recorded `t_registered`, `t_ready`, `t_visible`, `t_first_ok`, and time-to-SLO.
- [ ] Monitored registry peers/leader/anti-entropy or Kubernetes API/etcd/EndpointSlice.
- [ ] Verified readiness prevents requests from reaching unready instances.
- [ ] Verified retries use backoff/jitter and do not trigger retry storms.
- [ ] Repeated at least once with the same configuration to verify stability.
- [ ] Documented exact configurations, versions, results, and test environment limits.

## 15. Conclusion

Load testing mass startups and cluster-wide recovery must encompass both the control plane and the data plane. Measure registrations, heartbeats, fetches, health checks, API watches/lists, and replication alongside timings from process start to ready, from registration to discovery, and from outage to traffic returning to SLO.

Wave-based startups, retries with exponential backoff and jitter, concurrency-bounded warm-ups, readiness gates, and sensible caching/watching mitigate thundering herds. Good results mean not only that every instance started, but that the registry converged, consumers saw the right healthy instances, and the entire system recovered within target time without exceeding capacity.

## References

- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix – Eureka Client and Registration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka – Self Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Consul – Agent Service HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul – Consistency and Anti-Entropy](https://developer.hashicorp.com/consul/docs/concept/consistency)
- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Kubernetes – API Concepts, List and Watch](https://kubernetes.io/docs/reference/using-api/api-concepts/)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
