# Defining Recovery Criteria and Validating with Fault Injection Experiments

Service discovery can return an instance list that is structurally valid yet stale relative to actual runtime state. A provider may have stopped while the registry or a consumer cache still holds its address; conversely, a new provider may already be ready while consumers have not yet seen the new registration. Therefore, testing service discovery should not merely confirm the registry is up or an endpoint returns HTTP 200. You must measure failure detection time, registry and consumer convergence times, stale data exposure, recovery capability, and the rate at which healthy instances get falsely evicted.

Fault injection experiments create controlled scenarios such as stopping a provider, blocking connectivity to the registry, slowing down health checks, or restarting a node. Observing the results verifies whether your defined recovery criteria hold under realistic conditions.

This article builds a measurement framework, experiment planning methodology, fault matrices for Eureka, Consul, and ZooKeeper, evidence-collection practices, and guidance on turning results into operational decisions.

## 1. What Must Service Discovery Recovery Achieve?

A discovery flow involves multiple independent states:

1. Whether the provider process is running or stopped.
2. Whether the business endpoint is genuinely ready to accept requests.
3. Whether the registry has recorded the updated state.
4. Whether the discovery client has updated its local list.
5. Whether the consumer's LoadBalancer or cache still selects the old instance.
6. Whether the consumer can successfully call another healthy instance.

A sound recovery design brings all of these layers back to a consistent state within agreed time bounds. A registry showing an instance UP is insufficient to prove consumers can call it; likewise, the registry removing a failed instance does not guarantee every consumer has stopped using stale caches.

~~~mermaid
flowchart LR
    P["Actual provider"]
    R["Registry / agent"]
    D["Discovery client cache"]
    L["LoadBalancer"]
    Q["Consumer request"]
    P -->|"Register / health"| R
    R -->|"Fetch / watch / query"| D
    D --> L
    L --> Q
    Q --> P
~~~

During fault injection, observe all four: the provider, the registry, consumer caches, and request outcomes. Looking at only one component fails to capture end-to-end recovery time.

## 2. Distinguishing Detection, Convergence, and Service Restoration

Define these timestamps:

- **t0:** timestamp when fault injection begins.
- **tdetect:** timestamp when the discovery system first detects the fault.
- **tregistry:** timestamp when the registry reflects the new state.
- **tconsumer:** timestamp when the consumer stops picking the faulty instance and sees the updated list.
- **trecovered:** timestamp when the consumer successfully calls a healthy instance per business criteria.

From these, measure:

\[
T_{detect} = t_{detect} - t_0
\]

\[
T_{registry} = t_{registry} - t_0
\]

\[
T_{converge} = t_{consumer} - t_{registry}
\]

\[
T_{remove} = t_{consumer} - t_0
\]

\[
T_{restore} = t_{recovered} - t_0
\]

These metrics answer distinct questions:

| Metric | Question |
|---|---|
| Detection time | How long does it take the registry or health checker to detect the faulty instance? |
| Registry convergence | How long does it take the registry to reflect the new state? |
| Consumer convergence | How long does it take consumers to stop picking the faulty instance? |
| Removal time | How long until the faulty address disappears from instance selection? |
| Service restore time | How long until business requests succeed again? |

For example, a Consul agent detects a failing health check after 15 seconds, the catalog updates almost immediately afterward, yet consumers cache the old list for another 20 seconds. Detection time may look good, while removal time stays long due to caching. If other healthy instances remain, requests may recover before the faulty instance vanishes from every cache; hence you must measure both request success and discovery state.

## 3. Setting Verifiable SLIs and SLOs

An SLI is a measurable indicator; an SLO is an agreed quality target. Never apply one blanket target to all services. Payment APIs, low-traffic internal services, and development environments carry different requirements.

A useful set of SLIs:

| SLI | How to measure | Meaning |
|---|---|---|
| Stale selection rate | Requests sent to confirmed-faulty instances / total requests | Blast radius of stale registry data |
| Healthy instance availability | Fraction of time healthy instances remain selectable | Avoids mistakenly evicting good instances |
| Detection latency | tdetect - t0 | Speed of fault detection |
| Registry update latency | tregistry - t0 | Time for registry to reflect new state |
| Consumer convergence latency | tconsumer - tregistry | Time for consumers to adopt updated registry state |
| Removal latency | tconsumer - t0 | Total time from fault onset until consumers stop picking the faulty instance |
| Service restore latency | trecovered - t0 | Time until requests recover |
| Registration recovery | Time until a new instance appears and gets used by consumers | Recovery capability after restart/scale |
| Registry request error rate | Errors in register, heartbeat, fetch, query, or watch | Health of the control plane |
| False eviction rate | Rate at which healthy instances are marked unhealthy or evicted | Stability of health mechanisms |

Illustrative SLOs for a service with at least two replicas:

- After one replica stops abruptly, consumers stop picking that replica within at most 60 seconds at p95.
- Requests succeed again within at most 30 seconds provided a healthy replica remains and no other dependency fails.
- Rate of requests routed to a confirmed-faulty instance after convergence stays below 0.1% within the measurement window.
- Zero healthy instances are falsely evicted during connectivity-loss experiments shorter than the defined tolerance threshold.
- New instances become visible to consumers within at most 90 seconds after passing readiness and registering successfully.

These are sample numbers illustrating how to formulate SLOs, not defaults guaranteed by Spring Cloud or any registry. Choose bounds based on lease/session timeouts, health-check intervals, fetch/watch behavior, cache TTLs, network latency, and business requirements.

### Setting Stale Data Thresholds

Stale data can be measured by time or by request volume:

- **Stale window:** interval from when the provider actually fails until consumers finally stop picking it.
- **Stale request count:** number of requests routed to the faulty instance during the stale window.
- **Stale request ratio:** stale requests divided by total requests in the same window.

If a faulty instance receives only one request per minute, stale request count may stay low even with a long stale window. On high-traffic services, even a short stale window can produce many failed requests. Monitor both duration and request ratio.

### Defining Recovery Criteria for New Instances

Do not count a new instance as recovered merely because the process started or its znode/registry record appeared. Mark recovered only when:

1. The provider passes required readiness checks.
2. The registry holds the registration with accurate host, port, and metadata.
3. Target discovery clients observe the instance.
4. LoadBalancer can select the instance.
5. A safe verification request to the instance returns a valid response.

## 4. Bounding Data Loss and Registry State

In service discovery, dynamic registrations can usually be rebuilt from surviving providers. Consequently, registry RPO is not identical to a business database's RPO.

Instead of asking only "how much data was lost," specify:

- How many valid registrations are lost after a registry restart?
- How quickly can surviving providers re-register?
- How many stale registrations linger after instances have stopped?
- Are metadata, service IDs, instance IDs, and health states restored accurately?
- Do consumers observe consistent state once caches refresh?

For ephemeral registrations, state can be reconstructed from running providers and new sessions. For static configuration or administrator-managed registry configs, verify persistence and restoration from configuration sources. Never lump dynamic registrations and persistent config data into a single RPO metric.

## 5. Preparing a Fault Injection Experiment

A sound experiment defines a clear hypothesis, scope, pass/fail criteria, and rollback procedure.

### Defining the Hypothesis

Example:

"If one provider is killed abruptly, health/lease/session mechanisms will remove the instance from consumer selection within at most 60 seconds; consumers will shift traffic to the remaining healthy replica without exceeding the defined request error-rate threshold."

The hypothesis must state clearly:

- Where and when the fault is injected.
- Which component is expected to detect the fault.
- Which consumers are used for measurement.
- Expected state in the registry and along the request path.
- Time and error-rate bounds.

### Establishing a Baseline

Before injecting faults:

1. Confirm all target instances are healthy.
2. Record service IDs, instance IDs, hosts, ports, metadata, and registry status.
3. Record the instance count observed by each consumer.
4. Send low-load verification requests to confirm normal call paths.
5. Capture baseline latency, error rate, registry QPS, and health-check latency.
6. Synchronize clocks across the test runner, providers, registry, and consumers.

You cannot measure stale windows accurately if clocks drift significantly across components. Use synchronized timestamps or a single experiment controller recording t0.

### Isolating Scope

Run fault injection in staging or a dedicated namespace, using service IDs and data that do not affect unrelated workloads. Define upfront:

- Which instances or nodes are permitted targets.
- Which resources must never be stopped.
- Automatic abort thresholds for the experiment.
- Who owns recovery/rollback.
- How to verify all fault rules have been removed.

Never inject multiple fault types concurrently on your first measurement run. Start with a single fault, isolate causality, and only then test combined faults.

## 6. Fault Injection Experiment Matrix

The following matrix serves as a framework for choosing experiments. Each row requires expected results, timeouts, and concrete evidence definitions before execution.

| Experiment | How to inject the fault | What to observe |
|---|---|---|
| Provider crash | Force-kill one instance | Health/lease/session detection, registry eviction, consumer failover to another replica |
| Graceful shutdown | Stop provider via standard lifecycle | Proactive deregistration, request draining, no prolonged stale window |
| Provider isolated from registry | Block provider-agent/registry traffic while keeping API running | Whether registration expires and whether provider re-registers after reconnect |
| Consumer isolated from registry | Block consumer-registry traffic while keeping providers running | How stale cache behaves, whether requests continue, refresh after reconnect |
| Registry node/agent restart | Restart one node or agent in staging | Quorum/leader, registrations, reconnects, caches, and convergence time |
| Network latency/loss | Inject bounded delay or packet loss | False eviction, retry bursts, latency, and session stability |
| Failing health endpoint | Return 500 or time out on health endpoint | Instance status flips at threshold and recovers once endpoint turns healthy |
| Rolling deployment | Replace instances in batches | Whether any zero-available-instance gap occurs |
| Duplicate instance ID | Start two providers sharing an ID in test | How registry resolves collision; which instance is overwritten or rejected |
| Invalid metadata | Register with missing or wrong version/zone | Whether consumer filters exclude the instance properly and emit alerts |

## 7. Eureka-Specific Experiments

Eureka Client sends periodic heartbeats/renewals while consumers fetch the registry on intervals. Experiments should verify both server-side eviction and client-side fetch/cache lag.

### Abrupt Provider Stop

Procedure:

1. Run at least two instances under the same service ID.
2. Confirm both are UP in Eureka and visible to consumers.
3. Send continuous low-load requests and log which instance is selected.
4. Force-kill one provider so graceful deregistration does not run.
5. Record when lease renewals stop and when Eureka evicts the instance.
6. Monitor consumer registry fetches and when requests stop hitting the killed instance.
7. Verify requests continue succeeding via the remaining instance.

Settings that typically shape outcomes:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    registry-fetch-interval-seconds: 30
~~~

These values are illustrative only. Eureka Server includes self-preservation to avoid mass evictions when renewal rates drop abnormally. During experiments, always log self-preservation state and eviction logs; never assume lease expiration guarantees immediate removal under all conditions.

### Consumer Loses Connectivity to Eureka

Block connectivity from one consumer to Eureka while keeping providers and other consumers running. Observe:

- Whether the consumer continues serving from its local registry cache or rejects requests.
- Whether the cached list turns stale if a provider stops while the consumer is disconnected.
- After network recovery, how long the consumer takes to fetch a fresh snapshot.
- Whether retries burst when many clients reconnect simultaneously.

Define expected outcomes against actual client settings and request policies. Do not assume all Eureka client versions handle caches and connection faults identically.

## 8. Consul-Specific Experiments

Consul typically uses agents to accept registrations and execute health checks. Distinguish application failures from agent failures and agent-to-server communication faults.

### Health Check Failure

1. Register a provider with a lightweight health check endpoint.
2. Confirm the agent reports the check as passing.
3. Make the endpoint return errors or hang.
4. Record the first failed probe timestamp and when the catalog transitions status.
5. Query the health API filtering strictly for passing instances.
6. Check whether consumers query only passing instances or still receive warning/critical ones.
7. Restore the endpoint and measure time until the instance returns to passing.

Example catalog health check:

~~~bash
curl "http://consul-agent:8500/v1/health/service/catalog-service?passing=true"
~~~

In ACL/TLS-enabled environments, use HTTPS and valid tokens. This command merely illustrates querying; never expose unauthenticated APIs in production.

### Agent Loses Connectivity to Server

Block communication between a Consul client agent and Consul servers for a controlled period while keeping the local HTTP API reachable if required by the scenario. Monitor:

- Does the agent API still respond?
- Do local health checks continue running?
- What state does the server catalog show?
- How quickly does the agent resynchronize after connectivity returns?
- Do consumers querying a different agent observe a different state?

A responding local agent does not mean the whole cluster has received the updated state. Compare results from the affected agent, another agent, and the server/catalog according to your deployment topology.

## 9. ZooKeeper-Specific Experiments

ZooKeeper binds ephemeral znodes to sessions. Temporary TCP loss does not automatically delete a node; deletion occurs when the session expires. Experiments must therefore separate successful reconnects from session expiration.

### Disconnect Shorter Than Session Timeout

1. Register a service using an ephemeral znode.
2. Record session state and ephemeral owner.
3. Block client connectivity to the ensemble for less than the effective session timeout.
4. Observe that the znode persists while the session stays valid.
5. Restore networking and confirm the client reconnects using the existing session if possible.
6. Verify registrations and watches remain intact or recover cleanly.

### Disconnect Exceeding Session Timeout

1. Re-establish a healthy-session baseline.
2. Block client connectivity longer than the negotiated session timeout.
3. Confirm the server marks the session expired.
4. Confirm the session's ephemeral znode is deleted.
5. Restore networking.
6. Confirm the client creates a new session and re-registers its znode.
7. Measure how long consumers take to observe the instance back in service.

Never treat connection timeout as the session expiration boundary. The server negotiates session timeout within the ensemble's configured bounds; observe the effective negotiated value before choosing fault injection duration.

### Registry Quorum Loss

In a staging cluster with multiple ZooKeeper servers, stop one node and verify clients continue operating while quorum holds. Afterward, simulate quorum loss in an isolated environment to confirm clients report errors, sessions/watches recover, and no false conclusion is drawn that all providers are dead.

Never run quorum-loss experiments on an ensemble serving shared workloads. The objective is understanding behavior when the control plane cannot commit mutations, not disrupting live systems.

## 10. Fault Injection Tools

Pick tools matching the layer where you want to inject faults:

| Tool/method | Faults simulated | Appropriate scope |
|---|---|---|
| Docker Compose stop/kill/restart | Provider or agent shutdown | Local integration/staging |
| Toxiproxy | Latency, timeouts, resets, bandwidth caps between endpoints | Testing client-registry or consumer-provider |
| Linux network emulation (`tc netem`) | Delay, jitter, packet loss, corruption | Isolated network namespace or test node |
| Kubernetes pod delete/scale | Pod restarts or replica disappearance | Staging namespace |
| Chaos Mesh/Litmus | Network partitions, pod failures, controlled experiment stress | Controlled Kubernetes staging |
| HTTP mock server | Health endpoint returning 500s, slowness, or malformed bodies | Automated application tests |

Prefer intermediate proxies or dedicated network namespaces so only target connections are affected. When using node-level network emulation, confirm the exact interface and cleanup rules; a rule applied to a shared interface can disrupt unrelated workloads outside the experiment.

### Example: Stopping a Provider in Docker Compose

~~~bash
docker compose stop inventory-service
~~~

This simulates a controlled graceful stop. To test crashes that bypass shutdown hooks, use a forced kill in a test environment and document it as a distinct scenario. After each fault injection, confirm actual container state and stop timestamp.

### Example: Inspecting Endpoints in Kubernetes

~~~bash
kubectl get pods -n discovery-staging
kubectl get endpointslices -n discovery-staging
kubectl describe pod <pod-name> -n discovery-staging
~~~

These commands gather Pod and EndpointSlice state. During tests, compare them against Eureka/Consul/ZooKeeper records and the instance list observed by consumers.

## 11. Cross-Checking State Across Layers

In every experiment, gather evidence from at least four vantage points:

| Vantage point | Evidence |
|---|---|
| Provider | Process/container/pod state, readiness, health endpoint, start/stop logs |
| Registry | Instance record, status, health check, lease/session, registration timestamp |
| Consumer | `DiscoveryClient` list, LoadBalancer selection, cache age, reconnect/fetch/watch logs |
| Request path | Per-instance request counts, success/error rates, latency, timeouts |

If the registry has already removed an instance while consumers still call it, the issue lies in propagation or consumer caching. If the registry still holds an instance after the provider died, inspect detection/lease/session/health policies. If both registry and consumers see a new instance yet requests fail, inspect advertised host/port, networking, TLS, and readiness.

Never rely solely on a UI dashboard as ground truth. Dashboards may refresh slowly or read from a separate cache. Record timestamps and instance IDs to correlate the exact same record across layers.

## 12. Recording Experiment Results

Every test run should produce a standardized record:

~~~yaml
experiment:
  id: provider-crash-001
  environment: discovery-staging
  service: inventory-service
  fault: abrupt-provider-stop
  target_instance: inventory-02
  started_at: "2026-11-24T10:00:00Z"
  expected:
    max_detection_seconds: 30
    max_consumer_removal_seconds: 60
    max_service_restore_seconds: 30
    max_false_evictions: 0
  observed:
    detection_seconds: 24
    consumer_removal_seconds: 47
    service_restore_seconds: 3
    stale_requests: 2
    false_evictions: 0
  result: PASS
~~~

Numbers in this YAML only illustrate result formatting, not real measurements or default SLOs. In real experiments, pull timestamps from synchronized logs/metrics; never enter rough estimates to mark a PASS.

Also record:

- Spring Boot, Spring Cloud, and registry versions.
- Effective lease/session/health/fetch/cache configurations.
- Active instance and consumer counts at run time.
- Background request load.
- Exact fault rule and cleanup timestamp.
- Links to relevant logs, dashboards, or traces.
- Deviations from the hypothesis and confirmed root causes.

## 13. PASS/FAIL Criteria

An experiment passes only when every critical criterion is measured and within configured bounds. Example:

| Criterion | PASS when | FAIL when |
|---|---|---|
| Detection | Registry/agent detects fault within limit | Fault goes undetected or is detected too late |
| Consumer convergence | Consumers stop picking faulty instance on time | Cache keeps selecting faulty instance past deadline |
| Healthy availability | Healthy instances remain retained | Healthy instances are falsely evicted beyond budget |
| Service restore | Requests shift to healthy instances on time | Requests keep failing despite healthy replicas remaining |
| Re-registration | New instance registers and gets selected on time | Registration fails to return or metadata is wrong |
| Recovery stability | No continuous register/evict cycle after recovery | Flapping or retry storm persists |
| Cleanup | Fault rules removed and baseline restored | Fault rules or test artifacts left behind |

If data needed to compute a metric is missing, the verdict must be **INCONCLUSIVE**, never marked PASS. For instance, if you failed to capture when the provider actually died, you cannot compute detection latency accurately.

## 14. Stopping Experiments and Restoring Baseline

Define abort triggers before running:

- Error rate breaches safety threshold.
- False eviction rate of healthy instances spikes abnormally.
- Registry loses quorum or fails to serve out-of-scope services.
- Retries or request queues grow continuously.
- Fault impacts an unintended namespace, node, or service ID.
- Experiment duration exceeds time limit.

Cleanup procedure:

1. Remove toxic proxies, network rules, or chaos experiments.
2. Restart any stopped providers, agents, or nodes.
3. Confirm registry quorum/leader and API health.
4. Confirm all expected instances are healthy with accurate registrations.
5. Confirm consumer caches converged and requests succeed.
6. Verify no stray test processes, containers, or fault rules remain.
7. Archive results and document deviations before running the next experiment.

Restoring infrastructure does not automatically mean discovery has recovered. Conclude only when consumers actually select healthy instances and verification requests meet criteria.

## 15. Turning Results into Improvements

If the stale window exceeds your SLO, do not blindly slash every interval. First pinpoint which stage consumed the time:

- Slow detection: inspect health-check intervals, timeouts, lease/session expirations, and probing capacity.
- Slow registry update: inspect server load, self-preservation, agent sync, quorum, or catalog processing.
- Slow consumer update: inspect fetch intervals, blocking queries/watches, reconnects, and local caches.
- Slow request restoration: inspect LoadBalancer caching, retries, timeouts, circuit breakers, and healthy replica count.
- False evictions: inspect overly aggressive health endpoints, unsuitable dependency checks, JVM pauses, network jitter, and session timeouts.
- Registration fails to return: inspect client reconnects, re-registration, duplicate IDs, ACLs, metadata, and advertised addresses.

Every configuration change needs a new hypothesis and a re-run of the same experiment to compare before and after. Preserve baselines so optimizing one metric does not silently degrade another—such as shrinking the stale window at the cost of higher false evictions.

## 16. Minimum Experiment Suite to Maintain

A recurring verification suite for service discovery should cover:

1. Provider graceful shutdown and abrupt crash.
2. Provider losing connectivity to registry/agent.
3. Consumer losing connectivity to registry while still calling providers.
4. Health endpoint timing out and recovering.
5. Registry node/agent restart.
6. Rolling deployment or scale up/down.
7. Bounded network latency/packet loss.
8. ZooKeeper session expiration and re-registration.
9. Eureka lease/eviction and consumer fetch convergence.
10. Consul health states, catalog queries, and agent reconnects.

Not every environment needs to execute the full suite on every deploy. Tier them: automated pipeline tests for single faults and contracts; periodic staging runs for network/registry failures; scheduled game days for quorum loss or multi-node outages.

## 17. Principles for Setting Recovery Criteria

- Measure detection, registry convergence, consumer convergence, and service restoration separately.
- Set explicit thresholds for stale windows, stale request ratios, and false evictions.
- Count a new instance as recovered only when readiness, registration, discovery, and live requests all pass.
- Distinguish rebuildable dynamic registrations from persistent registry configuration.
- Run single faults before testing combined failures.
- Gather evidence across provider, registry, consumer, and request path.
- Align criteria with Eureka, Consul, or ZooKeeper semantics.
- Document versions, active configs, timestamps, and experiment scope.
- Mark runs INCONCLUSIVE whenever measurement data is missing.
- Remove all fault rules and verify the full discovery pipeline before finishing.

A valuable recovery criterion states clearly what service users will experience, within what timeframe, and which evidence proves the outcome. Fault injection turns assumptions about heartbeats, health checks, caches, watches, and sessions into concrete measurements. Measuring from provider to registry, registry to consumer, and down to the final request empowers operations teams to locate true bottlenecks and strengthen resilience without sacrificing the stability of healthy instances.
