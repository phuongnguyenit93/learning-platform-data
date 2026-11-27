# Running Multiple Replicas, Building Dashboards, and Writing a Recovery Report

## Practice Objectives

A Spring Cloud CircuitBreaker application typically runs multiple replicas to serve traffic and increase availability. Each replica is a separate process, so a Resilience4j CircuitBreaker keeps its state and sliding window in each JVM's memory by default. Pod A can be `OPEN` while pods B and C remain `CLOSED`. If you only look at an aggregated dashboard without preserving pod labels, operations teams can misjudge the scope of an incident.

This hands-on practice sets up a multi-replica environment for `order-service`, injects controlled faults on one replica, observes per-pod breaker state, builds a dashboard, and documents the recovery process. The goal is to prove the path from dependency failure to the `OPEN` decision, fallback behavior, `HALF_OPEN` probe attempts, and steady state after recovery.

After completing this practice, you can:

- Deploy multiple replicas of a Spring Cloud application with circuit breakers.
- Explain why each replica has its own breaker state and sliding window.
- Inject controlled faults on one replica to compare against the remaining replicas.
- Collect metrics from each pod using Actuator, Micrometer, and Prometheus.
- Build a dashboard showing state, failure rate, slow call rate, rejected calls, and fallbacks.
- Distinguish per-pod breaker state from the overall health of the dependent service.
- Trace a full `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED` cycle.
- Write a recovery report backed by metrics, timestamps, and follow-up actions.

## 1. Practice Environment Architecture

Use two applications:

- **order-service:** calls `inventory-service` through a gateway protected by Spring Cloud CircuitBreaker and Resilience4j.
- **inventory-service:** provides an inventory lookup API and supports fault injection enabled only in the practice environment.

Deploy three replicas of `order-service` and at least two replicas of `inventory-service`. A Kubernetes Service routes requests to the inventory pods. Each order pod maintains its own in-process `CircuitBreakerRegistry`.

    Client
      |
      v
    order-service (Kubernetes Service)
      |
      +----------------+----------------+
      |                |                |
      v                v                v
    order-0          order-1          order-2
    breaker-local    breaker-local    breaker-local
      |                |                |
      +----------------+----------------+
                       |
                       v
             inventory-service (Service)
                       |
                +------+------+
                |             |
                v             v
             inventory-0  inventory-1

Each order pod can end up in a different state:

| Replica | Example breaker state | Meaning |
| --- | --- | --- |
| order-0 | OPEN | Calls from this replica hit enough errors to cross the threshold. |
| order-1 | CLOSED | Calls from this replica are still succeeding. |
| order-2 | CLOSED | Calls from this replica are still succeeding. |

An `OPEN` state on `order-0` does not automatically open the breakers in `order-1` or `order-2`. Nor does the Kubernetes Service automatically remove `order-0` from receiving requests just because that pod's outbound breaker is `OPEN`. The circuit breaker protects outbound calls from `order-service` to `inventory-service`; readiness of `order-service` is a separate decision.

## 2. Prepare CircuitBreaker and Metric Configuration

Use a stable breaker ID, such as `inventory-read`. Each replica creates a breaker with the same name while holding separate state inside its own JVM.

Example `application.yml` for the lab environment:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 6
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 2
            automaticTransitionFromOpenToHalfOpenEnabled: true

Small values make state transitions quick to observe during practice. Do not copy this configuration verbatim to production without evaluating traffic volume, SLOs, and `inventory-service` characteristics.

Actuator and Prometheus configuration:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,metrics,prometheus
      endpoint:
        health:
          show-details: never
      metrics:
        tags:
          application: order-service

Required dependencies depending on Spring Boot version and integration setup:

- Spring Boot Actuator.
- Micrometer registry for Prometheus.
- Resilience4j Micrometer integration if the current starter does not auto-configure the binder.
- Spring Cloud CircuitBreaker Resilience4j starter matching your project's release train.

Verify that `/actuator/prometheus` actually exports circuit breaker metrics. Metric names and tags are standardized by Resilience4j/Micrometer version; inspect the exported output before writing dashboard queries.

Metrics typically observed include:

- Breaker state by name and state.
- Call counts by outcome: successful, failed, ignored, or not permitted.
- Failure rate and slow call rate.
- Rejected call counts while the breaker is `OPEN`.
- Call duration and `inventory-service` latency.
- Fallback counts by reason.
- State transition counts, if the application publishes events as custom counters.

## 3. Deploy Multiple Replicas

Example Kubernetes Deployment for `order-service`:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: order-service
      template:
        metadata:
          labels:
            app: order-service
          annotations:
            prometheus.io/scrape: "true"
            prometheus.io/path: "/actuator/prometheus"
            prometheus.io/port: "8080"
        spec:
          containers:
            - name: order-service
              image: example/order-service:lab
              ports:
                - name: http
                  containerPort: 8080
              env:
                - name: SPRING_PROFILES_ACTIVE
                  value: lab
              readinessProbe:
                httpGet:
                  path: /actuator/health/readiness
                  port: http
                initialDelaySeconds: 10
                periodSeconds: 5

Service for `order-service`:

    apiVersion: v1
    kind: Service
    metadata:
      name: order-service
    spec:
      selector:
        app: order-service
      ports:
        - name: http
          port: 8080
          targetPort: http

`inventory-service` should also be deployed with multiple replicas and a stable Service DNS name:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: inventory-service
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: inventory-service
      template:
        metadata:
          labels:
            app: inventory-service
        spec:
          containers:
            - name: inventory-service
              image: example/inventory-service:lab
              ports:
                - name: http
                  containerPort: 8080

    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: inventory-service
    spec:
      selector:
        app: inventory-service
      ports:
        - name: http
          port: 8080
          targetPort: http

These manifests are illustrative templates; replace images, namespaces, resource limits, secrets, and probes to fit your environment. Do not hardcode fixed container names or settings that prevent replica scaling. Every pod must have identifying labels so Prometheus and logs can distinguish metric sources.

Deploy and verify:

    kubectl apply -f inventory-deployment.yml
    kubectl apply -f order-deployment.yml
    kubectl get pods -l app=order-service -o wide
    kubectl get pods -l app=inventory-service -o wide
    kubectl get endpoints inventory-service

You should see three order pods in the `Ready` state and at least two available inventory endpoints. If replica counts or readiness are not met, resolve them before generating fault traffic.

## 4. Inject Controlled Faults on a Single Replica

To observe different breaker states across pods, cause one order replica to receive intentional errors while the remaining replicas call inventory normally.

A practical approach is adding fault injection active only under the `lab` profile:

- Requests from `order-service` carrying header `X-Lab-Fault: always-fail` receive HTTP 503 from the lab `inventory-service`.
- Requests without that header are processed normally.
- Use this header only in the lab namespace; never enable or trust it in production.
- The gateway forwards the header from test requests to inventory calls only under the `lab` profile.

Example on the `inventory-service` side:

    @GetMapping("/inventory/{sku}")
    public InventoryResponse find(
            @PathVariable String sku,
            @RequestHeader(
                value = "X-Lab-Fault",
                required = false
            ) String faultMode) {

        if ("always-fail".equals(faultMode)) {
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Lab fault injection"
            );
        }

        return inventoryRepository.find(sku);
    }

On the `order-service` side, you can propagate the header in a Feign request interceptor or WebClient filter dedicated to the `lab` profile. Never allow external clients to arbitrarily enable fault injection in real environments.

To send requests directly to each order pod, list pod names:

    kubectl get pods -l app=order-service

Then open a port-forward to a specific pod:

    kubectl port-forward pod/<order-pod-name> 18080:8080

Send requests to the forwarded pod. For the target pod, include the fault injection header; for the other pods, send normal requests. Repeat port-forwarding per pod to keep clear which replica receives each request.

Example:

    curl -H "X-Lab-Fault: always-fail"       http://localhost:18080/api/inventory/SKU-42

    curl http://localhost:18080/api/inventory/SKU-42

If the gateway uses a different header or endpoint, adapt to your lab API. The critical requirement is that requests are sent directly to an identified order pod and faults apply only to downstream calls from that pod.

## 5. Trigger OPEN on One Pod and Compare Other Pods

With the lab config of `minimumNumberOfCalls` 6 and `failureRateThreshold` 50, send enough failing calls to `order-0` to cross the threshold. Account for the actual sample count recorded by the breaker; do not assume one failing request always equals one sample if retries or other wrappers are active.

Steps:

1. Port-forward to `order-0`.
2. Send consecutive requests with the fault injection header.
3. Read metrics or events from `order-0` after each batch of requests.
4. Confirm the failure rate reaches the threshold once enough samples exist and the breaker transitions to `OPEN`.
5. Keep sending requests to `order-0`; confirm the breaker fails fast and the fallback executes.
6. Port-forward to `order-1` and `order-2`.
7. Send requests without the fault header; confirm these two pods still call inventory and their breakers remain `CLOSED`.

Expected results:

| Pod | Requests sent to pod | Breaker state | Behavior |
| --- | --- | --- | --- |
| order-0 | With fault header, enough failure samples | OPEN | Subsequent calls are rejected before calling inventory. |
| order-1 | Without fault header | CLOSED | Inventory calls succeed. |
| order-2 | Without fault header | CLOSED | Inventory calls succeed. |

If all three pods go `OPEN`, check whether fault injection is being applied to all requests, whether requests are actually going through the shared Service instead of per-pod port-forwarding, and whether metrics are being aggregated without pod labels.

When accessed through the normal `order-service` Service, requests can be load-balanced to any replica. If one pod is `OPEN`, only requests routed to that pod may receive fallbacks while requests hitting `CLOSED` pods still succeed. This is a crucial aspect of multi-replica behavior that dashboards must surface.

## 6. Verify Each Replica Has Its Own Sliding Window

Resilience4j CircuitBreaker maintains its state machine and sliding window in process memory by default. There is no automatic state synchronization across JVMs merely because they share the same breaker name.

This means:

- `order-0` may record six errors and open its breaker.
- `order-1` may record only two successes and stay `CLOSED`.
- `order-2` may have received no requests yet; its breaker may not have enough samples to evaluate.
- Restarting `order-0` creates a new process whose in-memory breaker starts fresh per configuration, typically `CLOSED`.

Do not conclude that `inventory-service` has recovered merely because a newly restarted order pod has a `CLOSED` breaker. A fresh `CLOSED` state only means the new breaker lacks enough failure history to open; verify actual requests and dependency health.

Distributing traffic across multiple replicas also changes how fast samples accumulate. If each pod receives only a fraction of traffic, a breaker may take longer to reach `minimumNumberOfCalls`. When choosing `minimumNumberOfCalls`, size it for per-replica traffic, not just total deployment traffic.

Do not attempt to share breaker state via Redis or a database as a default pattern. A Resilience4j breaker is an in-process mechanism; if centralized control is required, design a dedicated control plane and carefully evaluate its consistency, latency, and failure modes.

## 7. Collect Metrics Separately for Each Pod

Prometheus must scrape each `order-service` pod rather than scraping a load-balanced Kubernetes Service. Scraping through a Service can hit a different pod on each scrape, causing pod labels to stop reflecting individual sources reliably.

You can use pod annotations, `ServiceMonitor`, or Prometheus Kubernetes service discovery configuration. Example conceptual scrape config using pod annotations:

    scrape_configs:
      - job_name: order-service-pods
        kubernetes_sd_configs:
          - role: pod
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_label_app]
            action: keep
            regex: order-service
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
            action: keep
            regex: "true"
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
            action: replace
            target_label: __metrics_path__
            regex: (.+)
          - source_labels: [__meta_kubernetes_pod_ip, __meta_kubernetes_pod_annotation_prometheus_io_port]
            separator: ";"
            action: replace
            target_label: __address__
            regex: (.+);(\d+)
            replacement: $1:$2
          - source_labels: [__meta_kubernetes_pod_name]
            target_label: pod
          - source_labels: [__meta_kubernetes_namespace]
            target_label: namespace

This is a template configuration; the rule combines pod IP with the port annotation to build `__address__`. In a real cluster, add your platform's standard namespace, TLS, authentication, and relabel rules. If using Prometheus Operator, prefer `ServiceMonitor`/`PodMonitor` for clear scrape and label configuration.

After scraping, verify each time series has stable `pod` or `instance` labels. Inspect metrics from individual pods by querying the Actuator endpoint directly when needed.

Do not expose Actuator publicly just for Prometheus scraping. Use an internal network, authentication, or a dedicated management port appropriate for your platform.

## 8. Build a Per-Replica Dashboard

The dashboard should include filters for namespace, application, pod, and breaker name. Suggested panels:

| Panel | Data | Question answered |
| --- | --- | --- |
| State per pod | State gauge for each breaker | Which pods are `CLOSED`, `OPEN`, or `HALF_OPEN`? |
| Failure rate | Failure rate by pod and breaker | Which pods are recording high error rates? |
| Slow call rate | Slow call rate | Is the dependency slowing down before failing outright? |
| Calls by outcome | Rate of successful, failed, ignored | How are traffic and outcomes changing? |
| Not permitted | Counter of calls rejected by breaker | How many requests are failing fast? |
| Fallback | Counter by reason and pod | Which replicas are serving fallbacks to users? |
| State transitions | From/to counter by pod | How often are breakers opening and recovering? |
| Latency | p50/p95/p99 of dependency calls | Did latency drop after the breaker opened? |

Illustrative PromQL for the number of pods currently `OPEN`:

    sum by (namespace, pod, name) (
      resilience4j_circuitbreaker_state{state="open"} == 1
    )

Call rate by outcome, if the registry exports timer counts with a `kind` tag:

    sum by (pod, name, kind) (
      rate(resilience4j_circuitbreaker_calls_seconds_count[5m])
    )

Rejected calls over 5 minutes:

    sum by (pod, name) (
      increase(resilience4j_circuitbreaker_not_permitted_calls_total[5m])
    )

Metric names and labels must be verified against the Prometheus endpoint of the running version. Prometheus can normalize Micrometer dot-separated names into underscores and counter/timer suffixes. If actual metrics differ, adjust queries to match scraped data; do not create blank panels and assume the breaker is not emitting metrics.

If the application does not yet export transition counters, register an `onStateTransition` listener and increment a custom counter keyed by `from`, `to`, and `name`. Keep tag cardinality bounded; never use request ID or SKU as tags.

## 9. Distinguish Per-Pod Dashboards from Service-Wide Dashboards

A dashboard showing only aggregated state can hide a situation where one pod is `OPEN` and two pods are `CLOSED`. Maintain both views:

**Per-pod view**

- Each breaker's state on each pod.
- Failure rate, slow call rate, and not-permitted counts per pod.
- State transition counts and time spent `OPEN` per pod.
- Fallbacks and latency from that pod.

**Service-wide view**

- How many pods are currently `OPEN`.
- Overall request success rate and fallback rate.
- Total rejected calls.
- Aggregate latency and `inventory-service` health.
- Ready pod count and selectable inventory endpoint count.

When aggregating state gauges, use aggregations that match the question. For example, total `OPEN` pods is the sum of `OPEN` gauges equal to 1. Never sum `CLOSED`/`OPEN`/`HALF_OPEN` state values as if they were event counters.

If one pod is `OPEN` while two pods are `CLOSED`, the service can still serve a portion of requests. However, the load balancer in front of `order-service` may keep routing traffic to the `OPEN` pod. Measure client-side fallback and error rates to understand the real user impact.

Do not automatically mark an order pod `NotReady` merely because an outbound breaker is `OPEN`. Doing so can pull the pod out of traffic and overload the remaining pods, triggering a cascading failure. Only tie dependency status to readiness when there is an explicit availability design and its consequences have been evaluated.

## 10. Trace a Recovery Cycle

With `waitDurationInOpenState: 10s` and `automaticTransitionFromOpenToHalfOpenEnabled: true`, the breaker can automatically transition from `OPEN` to `HALF_OPEN` after the wait duration. In `HALF_OPEN`, up to two probe calls are allowed under the lab configuration.

Recovery workflow:

1. Record the timestamp when `order-0` transitions to `OPEN`.
2. Verify subsequent requests fail fast; downstream inventory receives no new attempts from that breaker.
3. Remove fault injection so `inventory-service` returns successful responses.
4. Wait for the breaker to transition to `HALF_OPEN`.
5. Send the permitted number of probe calls and observe the outcomes.
6. If probe calls succeed per policy, the breaker transitions to `CLOSED`.
7. If probe calls fail or exceed slow thresholds, the breaker can return to `OPEN`.
8. Record when it left `OPEN`, the `HALF_OPEN` probe results, and when it returned to `CLOSED`.

If automatic transition is disabled, the breaker may transition to `HALF_OPEN` only when a new call arrives after the wait duration elapses. In that case, observed `OPEN` duration can exceed the configured duration. Document the actual configuration in the report.

A single transition to `CLOSED` does not prove every inventory instance is healthy. Probe calls still route through service discovery/load balancing and may hit different instances. To verify individual inventory instances, inspect instance IDs or metrics on `inventory-service`.

## 11. Analyzing Cases Where Replicas Have Different States

Use an observation table during practice:

| Order pod | State | Failure rate | Not permitted | Fallback | Explanation |
| --- | --- | --- | --- | --- | --- |
| order-0 | OPEN | 80% | 25 | 25 | Fault injection pushed failure samples past threshold. |
| order-1 | CLOSED | 0% | 0 | 0 | Received only successful calls. |
| order-2 | CLOSED | 0% | 0 | 0 | Received only successful calls. |

Numbers are illustrative. When capturing real data, record both sample count and scrape timestamp to avoid comparing rates from a tiny window against a full window.

If `order-1` or `order-2` also open, check:

- Were failing requests sent through the shared Service instead of port-forwarding to a specific pod?
- Is the gateway adding the fault header to every request?
- Is the inventory backend returning errors to all clients?
- Is the breaker ID shared across multiple operations within the same pod?
- Are metrics scraped through the Service, stripping pod labels?
- Did retries generate more failing attempts than expected?
- Is exception configuration counting business errors as failures?

If `order-0` stays `CLOSED` despite sending errors, check `minimumNumberOfCalls`, how many requests actually passed through the breaker, whether the exception is recorded, and whether the breaker name in metrics matches. Never lower thresholds just to force `OPEN`; first verify the breaker's input signals.

## 12. Writing a Recovery Report

The report should describe what happened using timestamps and numbers, not just state "recovered". Use the following template for each practice or incident drill:

    # CircuitBreaker Recovery Report

    ## 1. Deployment Information
    - Date/time:
    - Environment/namespace:
    - Build/version:
    - order-service replica count:
    - inventory-service replica count:
    - Breaker id:
    - Sliding window config:
    - Failure/slow-call threshold:
    - waitDurationInOpenState:

    ## 2. Fault Scenario
    - Fault injection:
    - Affected pod(s):
    - Start time:
    - Request/attempt count:
    - HTTP status or exception:
    - Blast radius:

    ## 3. Breaker Timeline
    | Pod | Pre-fault state | Time OPEN | Time HALF_OPEN | Time CLOSED |
    | --- | --- | --- | --- | --- |
    | order-0 | | | | |
    | order-1 | | | | |
    | order-2 | | | | |

    ## 4. Impact and Metrics
    - Peak failure rate:
    - Peak slow call rate:
    - Rejected call count:
    - Fallback count:
    - p95/p99 latency:
    - Ready pod count:
    - Available inventory endpoints:

    ## 5. Recovery
    - Root cause resolved:
    - HALF_OPEN probe results:
    - Observed OPEN duration:
    - Time error rate returned to normal:
    - Evidence from dashboards/logs/traces:

    ## 6. Conclusions and Action Items
    - What worked well:
    - What fell short:
    - Configuration needing adjustment:
    - Owner:
    - Due date:
    - Dashboard or query link:

In the report, distinguish the configured `OPEN` wait duration from the observed `OPEN` duration. If the breaker only leaves `OPEN` when a new request arrives, those two values can differ. Explicitly note whether automatic transition is enabled.

Never include tokens, credentials, sensitive payloads, or personal data in the report. Use pod names, breaker names, sanitized request correlation IDs, and UTC timestamps so teams can correlate logs.

## 13. Practice Completion Criteria

The practice is complete when you have sufficient evidence for all of the following:

- Three order replicas run Ready and are scraped individually.
- Metrics are accessible per pod.
- One pod receives controlled faults and transitions to `OPEN`.
- Unaffected pods stay `CLOSED` and continue calling inventory successfully.
- Requests to the `OPEN` pod fail fast and fallbacks are observed.
- Dashboards display per-pod state, failure rate, not-permitted calls, and fallbacks.
- Fault injection is removed and `HALF_OPEN` probes succeed.
- The breaker returns to `CLOSED` after meeting recovery conditions.
- The report documents timestamps, sample counts, states, metrics, `OPEN` duration, and follow-up actions.
- Afterward, fault injection is turned off and the lab environment returns to normal.

If a criterion is not met, record the missing evidence and root cause. Do not declare recovery merely because an endpoint returned HTTP 200 once; confirm the breaker has returned to `CLOSED`, fallbacks dropped back to baseline, and replicas are behaving as expected.

## 14. Extension Exercises

After completing the primary scenario, try these variations:

1. Scale `order-service` from three to five replicas and observe how long each breaker takes to accumulate `minimumNumberOfCalls`.
2. Switch to a `TIME_BASED` sliding window and compare opening behavior when traffic fluctuates.
3. Make one inventory instance respond slowly while the other stays healthy; observe LoadBalancer, retry, and breaker behavior per logical call.
4. Restart only `order-0` while its breaker is `OPEN`; confirm the new breaker starts with fresh in-memory state and explain why this does not prove the dependency recovered.
5. Disable Prometheus scraping for one pod for a few minutes; observe dashboards and missing-data alerts.
6. Create a fallback spike while overall requests still succeed on other pods; assess the real impact on users.
7. Test a low bulkhead limit on one pod and distinguish Bulkhead rejections from `CallNotPermittedException`.
8. Disable automatic transition and verify that observed `OPEN` duration can exceed `waitDurationInOpenState`.
9. Compare the per-pod dashboard against the aggregated dashboard; identify what information is lost when pod labels are dropped.

These exercises reinforce that breaker state in a multi-replica environment is local state. Dashboards must preserve per-pod data, while recovery reports must link that state to dependency health, traffic, fallbacks, and deployment timelines.

## References

- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Resilience4j — CircuitBreaker state machine and configuration: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Micrometer metrics: https://resilience4j.readme.io/docs/micrometer
- Spring Boot Actuator — Metrics and Prometheus: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Prometheus — Kubernetes service discovery: https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config
