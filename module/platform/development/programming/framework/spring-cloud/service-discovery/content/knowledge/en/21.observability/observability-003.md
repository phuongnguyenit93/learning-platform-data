# Tracking Instance Counts and Registration Churn by Service

In a microservices system, a service can have multiple instances, and that count changes continuously due to deployments, scaling, health checks, restarts, or network incidents. Looking at a registry dashboard at a single point in time is not enough to tell whether the system is stable or constantly adding, removing, and changing instance statuses.

You need to track two groups of data simultaneously:

- **Current instance counts:** how many instances are registered, and how many are healthy, warning, critical, or out of service.
- **Registration churn:** over a given period, how many registrations, deregistrations, status transitions, registration failures, or sync losses occurred.

These two groups answer different questions. A gauge shows the current snapshot; a counter shows how many events have occurred. A service can always have 5 instances while continuously replacing old instances with new ones. If you only watch the gauge, this churn remains invisible.

This article explains how to design metrics by service and status, leverage built-in Eureka and Consul metrics, add instrumentation with Micrometer, query Prometheus, build dashboards, and alert on registration churn.

## 1. Distinguishing Registered, Healthy, and Eligible

Before counting instances, define which set you are counting. A registry may still hold an instance's registration even though its health check has failed. A consumer may also apply additional filters to select only a subset of instances.

| Concept | Meaning | Example |
|---|---|---|
| Registered instances | Instances still having an entry in the registry/catalog | 5 |
| Healthy instances | Instances whose health status meets requirements | 4 |
| Eligible instances | Instances remaining after consumer/load balancer filters | 3 |
| Reachable instances | Instances the consumer can actually reach over the network path | Potentially only 2 |

For example, `inventory-service` has 5 registrations:

- 3 instances are `UP` or `passing`.
- 1 instance is `warning`.
- 1 instance is `critical`.
- The consumer only picks `UP`/`passing` instances and only selects its local zone, leaving perhaps only 2 candidates.

Do not name a single metric `service_instance_count` and use it for all four meanings. Metric names and labels must clearly reflect the exact instance set being measured.

### 1.1. Counting by Service and Status

A useful snapshot looks like:

| Service | UP / passing | Warning | Critical / DOWN | Total Registered |
|---|---:|---:|---:|---:|
| inventory-service | 3 | 1 | 1 | 5 |
| order-service | 4 | 0 | 0 | 4 |
| payment-service | 2 | 0 | 1 | 3 |

Total registrations may exceed healthy instances. If only the total is displayed, operators might assume the service has sufficient capacity even though many instances are no longer receiving traffic.

Different registries use different statuses:

- Eureka typically uses `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, and `UNKNOWN`.
- Consul health checks use `passing`, `warning`, and `critical`.
- An application can normalize these statuses into `healthy`, `degraded`, `unhealthy`, and `unknown` for cross-registry dashboards, while preserving the raw status for diagnostics.

## 2. Gauges and Counters Serve Different Purposes

Prometheus clearly distinguishes metrics reflecting current state from metrics accumulating events.

**Gauge** values can go up or down. Use a gauge to represent the number of currently registered instances at scrape time:

~~~text
service_registry_instances{
  registry="eureka",
  service="inventory-service",
  status="UP"
} 3
~~~

**Counter** values only increase over a process lifetime, resetting only on process restart. Use a counter to count registration events:

~~~text
service_registry_registration_events_total{
  registry="eureka",
  service="inventory-service",
  action="register",
  result="success"
} 42
~~~

An example:

- At 10:00 there are 5 instances.
- Over the next 10 minutes, one instance is deregistered and one new instance registers.
- At 10:10 there are still 5 instances.

The gauge remains 5. The register counter increases by 1 and the deregister counter increases by 1. Both metrics are needed to understand churn.

Rules:

- Current counts, instances by status, latest successful scrape timestamp: gauge.
- Total registrations, deregistrations, status transitions, and registration errors: counter.
- Duration of register/deregister operations or snapshot sync duration: histogram or summary.
- Do not use `rate()` on gauges. Use `rate()` or `increase()` on counters.

## 3. Recommended Metric Set

You can standardize a set of metrics independent of the registry backend. The examples below are custom metric names defined by the application team or an exporter; not all of them are automatically created by Spring Cloud.

| Metric | Type | Primary Labels | Meaning |
|---|---|---|---|
| `service_registry_instances` | Gauge | registry, service, status, datacenter | Current registration count by status |
| `service_registry_registration_events_total` | Counter | registry, service, action, result, reason | Number of register, deregister, or status-change events |
| `service_registry_registration_duration_seconds` | Histogram | registry, operation, result | Duration of register/deregister operations |
| `service_registry_last_snapshot_timestamp_seconds` | Gauge | registry, datacenter | Unix timestamp of the last successful snapshot read |
| `service_registry_snapshot_duration_seconds` | Gauge or Histogram | registry, datacenter | Time taken to fetch and aggregate the snapshot |
| `service_registry_snapshot_errors_total` | Counter | registry, datacenter, reason | Number of times the collector failed to fetch a snapshot |

### 3.1. Choosing Bounded Labels

Useful labels:

- `registry`: eureka, consul, zookeeper, or kubernetes.
- `service`: service ID/name.
- `status`: raw status or normalized status.
- `datacenter` or `cluster`: registry scope.
- `action`: register, deregister, status_change.
- `result`: success or failure.
- `reason`: a finite set of reasons such as startup, graceful_shutdown, health_transition, lease_expired, operator.

Avoid putting unbounded or continuously changing values into labels:

- Instance ID, pod UID, or container ID.
- IP address, dynamic hostname, or request ID.
- User ID, trace ID, or exception message.
- Timestamps or log contents.

Every label combination creates a separate time series. Adding instance ID and IP for every instance to every metric causes cardinality to explode during scaling or deployments. Use logs, an event store, or the registry API to investigate individual instances; keep metrics at the service and status level.

## 4. Data Sources for Counting Instances

No single source answers every question. Choose based on your goal:

| Source | What It Counts | Limitations |
|---|---|---|
| Registry API / Catalog API | Existing registrations | May not show detailed health status |
| Health API | Registrations along with checks and status | Requires aggregating multiple checks by policy |
| Eureka server metrics | Gauges by application and instance status | Must be enabled; not an event history |
| Consul agent telemetry | Activity and performance of agent/API/catalog | Not a current instance count gauge per service |
| Consumer DiscoveryClient | Instance set actually seen by the consumer | May differ from registry due to cache and filters |
| LoadBalancer supplier | Instance set after LoadBalancer filters | Reflects only that specific consumer's view |

Operational dashboards should separate registry-side metrics from consumer-side metrics. If the registry reports 5 `UP` instances while a consumer only sees 3, investigate cache, datacenter, ACLs, filters, zones, or synchronization lag.

## 5. Tracking Instance Counts with Eureka

Eureka receives registration metadata and heartbeats from each instance. The server holds registry state; when a heartbeat is not renewed under the lease mechanism, the instance can be evicted from the registry according to configured policies and intervals.

Spring Cloud Netflix includes a Micrometer feature named `EurekaInstanceMonitor`. This feature listens to Eureka registration events and creates/updates gauges in `MeterRegistry`.

To enable it:

~~~yaml
eureka:
  server:
    metrics:
      enabled: true
~~~

This feature is disabled by default according to current Spring Cloud Netflix documentation.

The default gauge has the Micrometer name `eureka.server.instances` and two tags:

- `application`: application/service name.
- `status`: instance status such as `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, or `UNKNOWN`.

When exported to Prometheus, the metric name may be normalized according to registry naming conventions, for example to `eureka_server_instances`. The name shown at the Actuator metrics endpoint and the normalized name in Prometheus may differ.

Additional tags can be added via a custom `EurekaInstanceTagsProvider` implementation. Only add tags with bounded value sets, such as region or environment.

### 5.1. What Does the Eureka Gauge Show?

Example metric output after scraping:

~~~text
eureka_server_instances{
  application="INVENTORY-SERVICE",
  status="UP"
} 3

eureka_server_instances{
  application="INVENTORY-SERVICE",
  status="OUT_OF_SERVICE"
} 1
~~~

You can query total instances by application and status:

~~~promql
sum by (application, status) (eureka_server_instances)
~~~

Count only `UP` instances:

~~~promql
sum by (application) (
  eureka_server_instances{status="UP"}
)
~~~

This is a gauge of instance counts by status. It helps visualize snapshots and count trends, but does not tell you how many new registrations or deregistrations occurred in the recent period.

### 5.2. Tracking Eureka Churn

If you need registration/deregistration counts over time, add event instrumentation. You can record events in a server-side listener or registry processing layer to reflect changes actually accepted by Eureka.

Distinguish:

- Register: a new registration is created or accepted.
- Renew/heartbeat: an instance renews its lease; this is not a new registration.
- Status change: an instance's status changes, e.g., `UP` to `OUT_OF_SERVICE`.
- Cancel/deregister: a registration is cancelled.
- Expiration: a registration is evicted due to lease expiration.

Do not count every heartbeat as a register event. An instance sends periodic heartbeats very frequently; counting heartbeats as churn would make charts reflect heartbeat cadence rather than instance lifecycle.

To count events accurately, instrument at the server-side event source. A counter placed on the provider only shows that the client attempted to call register or deregister; it can miss abrupt crashes or lose events if the process terminates before the next scrape.

## 6. Tracking Instance Counts with Consul

Consul separates Catalog and Health:

- Catalog stores service registrations, nodes, addresses, ports, tags, and metadata.
- Health API returns registrations along with associated checks, indicating whether an instance is `passing`, `warning`, or `critical`.

To count total registrations for a service, you can query:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/service/inventory-service
~~~

Each element is a service registration in the catalog. Count the elements to get the current registration count for the datacenter, namespace, and partition targeted by the query.

To read health:

~~~bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
~~~

To retrieve only nodes where all health checks are passing:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing"
~~~

When building gauges by status, the collector can classify check results using a consistent policy:

- At least one critical check: instance is classified as `critical`.
- No critical checks, but at least one warning check: instance is classified as `warning`.
- All relevant checks passing: instance is classified as `passing`.

Document clearly whether the collector includes node-level checks alongside service-level checks. The Health API can return checks at both scopes; if you only read the service's HTTP check and ignore node checks, the healthy count may look higher than Consul's actual view.

### 6.1. Consul Agent Telemetry Is Not an Instance Inventory

The Consul agent exposes metrics related to Catalog and API operations:

- `consul.catalog.register` and `consul.catalog.deregister` measure catalog operation duration, published as summaries.
- `consul.client.api.catalog_register` counts register requests received by the agent.
- `consul.client.api.catalog_deregister` counts deregister requests received by the agent.
- `consul.catalog.service.query` counts catalog service queries.
- `consul.catalog.service.not_found` counts service queries that returned not found.

These metrics are useful for monitoring Consul load, errors, and performance. They are not gauges of currently existing instances per service. In particular, the number of API requests does not necessarily equal the number of registrations that actually changed, because a request may update an existing entry, be retried, or fail.

To get instance count gauges by service and health state, take snapshots from the Catalog/Health API or use a dedicated exporter. To capture churn history, collect events from the registry source or instrument register/deregister operations with explicit outcomes.

### 6.2. Scraping Consul Agent Metrics

Consul can export telemetry in Prometheus format via the agent endpoint. Example scrape configuration:

~~~yaml
scrape_configs:
  - job_name: consul-agent
    metrics_path: /v1/agent/metrics
    params:
      format: ["prometheus"]
    static_configs:
      - targets:
          - consul-agent-1:8500
          - consul-agent-2:8500
~~~

Consul uses this path and query parameter instead of the default `/metrics` endpoint. Secure the agent endpoint, configure ACLs/TLS for the environment, and verify telemetry retention matches your Consul version.

## 7. Building a Snapshot Exporter for Current Counts

If the registry does not provide per-service gauges, you can build a periodically running collector:

1. Obtain the list of services to monitor.
2. Query the Catalog or Health API.
3. Aggregate registration counts by service and status.
4. Update the gauges.
5. Update the successful snapshot timestamp.
6. If the query fails, increment the error counter and retain the previous successful timestamp to alert on stale data.

Example output:

~~~text
service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="passing",
  datacenter="dc1"
} 3

service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="warning",
  datacenter="dc1"
} 1

service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="critical",
  datacenter="dc1"
} 1

service_registry_last_snapshot_timestamp_seconds{
  registry="consul",
  datacenter="dc1"
} 1795500000
~~~

The timestamp is the Unix time of the last successful snapshot. You can compute staleness in PromQL:

~~~promql
time() - service_registry_last_snapshot_timestamp_seconds
~~~

If the collector cannot query the registry, do not reset all gauges to 0. A value of 0 means a successful snapshot found zero instances; an inability to fetch data must be represented via an error counter or snapshot age. Resetting to 0 on query failure would mislead dashboards into showing that the service lost all instances.

### 7.1. Polling Collectors Can Miss Rapid Churn

Suppose the collector reads a snapshot every 30 seconds. An instance registers and deregisters between two scrapes. Both snapshots may show 5 instances; the gauge never reflects that transient instance.

Snapshots report state at read time, not an event log. If you need to capture every change:

- Use event listeners on the registry server if supported by the backend.
- Use watch/blocking queries to detect changes, then re-read the snapshot.
- Instrument register/deregister at the point where the operation is performed.
- Record events to durable logs or an event store if exact auditing is required.

A watch or blocking query typically signals that data changed rather than providing a historical log of every individual operation. If multiple changes occur between two reads, the collector still needs to diff snapshots or read from a durable event log.

## 8. Instrumentation with Micrometer

Spring Boot Actuator provides Micrometer and auto-configures `MeterRegistry` when the corresponding registry dependency is on the classpath. For Prometheus, add dependencies matching your project's Spring Boot/Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Expose the required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
~~~

The Prometheus endpoint is `/actuator/prometheus`. This endpoint is not exposed by default in all configurations; expose it explicitly and protect it with network policies or Spring Security.

### 8.1. Instance Count Gauge

Example component tracking counts by service and status:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.stereotype.Component;

@Component
public class RegistryInstanceMetrics {

    private final MeterRegistry meterRegistry;

    private final ConcurrentMap<String, AtomicInteger> counts =
            new ConcurrentHashMap<>();

    public RegistryInstanceMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void setCount(
            String registry,
            String service,
            String status,
            int count
    ) {
        String key = registry + "|" + service + "|" + status;

        AtomicInteger value = counts.computeIfAbsent(key, ignored -> {
            AtomicInteger holder = new AtomicInteger();

            Gauge.builder(
                    "service.registry.instances",
                    holder,
                    AtomicInteger::get
            )
            .tag("registry", registry)
            .tag("service", service)
            .tag("status", status)
            .register(meterRegistry);

            return holder;
        });

        value.set(count);
    }
}
~~~

The collector calls `setCount` after each successful snapshot. The `AtomicInteger` instance is retained in the map so the gauge's backing object stays alive; never create a gauge over a temporary object that can be garbage-collected.

This example illustrates a simple collector. In production, handle disappearing service/status entries, status normalization rules, and synchronization when multiple collectors update concurrently.

### 8.2. Counter for Register and Deregister

Events can be recorded where the application or registry server confirms the operation:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.stereotype.Component;

@Component
public class RegistryEventMetrics {

    private final MeterRegistry meterRegistry;

    public RegistryEventMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void record(
            String registry,
            String service,
            String action,
            String result,
            String reason
    ) {
        Counter.builder("service.registry.registration.events")
                .tag("registry", registry)
                .tag("service", service)
                .tag("action", action)
                .tag("result", result)
                .tag("reason", reason)
                .register(meterRegistry)
                .increment();
    }
}
~~~

Label values should come from an enum or bounded set, for example:

- action: `register`, `deregister`, `status_change`.
- result: `success`, `failure`.
- reason: `startup`, `graceful_shutdown`, `health_transition`, `lease_expired`, `operator`.

Increment the counter after the operation result is known. If you want to track both attempts and final outcomes, use separate metrics for attempts and success/failure; do not merge two meanings into the same counter.

Do not record heartbeat renewals in the registration counter. If you need to observe heartbeats, create dedicated metrics for renew requests, renew failures, or lease expirations.

### 8.3. Measuring Operation Duration

You can use a `Timer`/`DistributionSummary` or Histogram to track the duration of register/deregister operations. Example:

~~~java
import io.micrometer.core.instrument.Timer;

Timer.Sample sample = Timer.start(meterRegistry);

try {
    registryClient.register(instance);
    sample.stop(Timer.builder("service.registry.registration.duration")
            .tag("registry", "consul")
            .tag("operation", "register")
            .tag("result", "success")
            .register(meterRegistry));
} catch (RuntimeException ex) {
    sample.stop(Timer.builder("service.registry.registration.duration")
            .tag("registry", "consul")
            .tag("operation", "register")
            .tag("result", "failure")
            .register(meterRegistry));
    throw ex;
}
~~~

Place this instrumentation in the adapter performing the registry operation. If instrumentation is placed in an outer caller layer, the timer may include retries, queuing, or network delays; be clear whether the measured latency represents client call duration or registry commit duration.

## 9. Prometheus Scrape Configuration

Example Prometheus scrape configuration for Spring Boot applications:

~~~yaml
scrape_configs:
  - job_name: spring-services
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service-1:8080
          - inventory-service-1:8080
          - payment-service-1:8080
~~~

In dynamic environments, use Kubernetes service discovery, Consul service discovery, or file-based service discovery instead of a static list. Each target should be scraped independently to distinguish metrics from individual processes.

Do not scrape a shared gateway endpoint when your goal is to count per-instance application metrics. A gateway may only expose its own metrics and hide backend instances.

## 10. PromQL for Counts and Churn

The following queries assume the custom metrics are exported under the corresponding Prometheus names. Micrometer normalizes dots to underscores when exporting; verify the actual metric names at `/actuator/prometheus`.

### 10.1. Instance Count by Service and Status

~~~promql
sum by (service, status) (
  service_registry_instances
)
~~~

### 10.2. Healthy Instance Count by Service

If using raw Eureka statuses:

~~~promql
sum by (service) (
  service_registry_instances{status="UP"}
)
~~~

If using raw Consul statuses:

~~~promql
sum by (service) (
  service_registry_instances{status="passing"}
)
~~~

If normalized to `health_state`:

~~~promql
sum by (service) (
  service_registry_instances{health_state="healthy"}
)
~~~

Use one consistent status convention within a single dashboard. Never add `UP` and `passing` together directly if metrics are unnormalized or the `registry` label is not separated.

### 10.3. Register and Deregister Counts over 15 Minutes

~~~promql
sum by (service, action) (
  increase(
    service_registry_registration_events_total{
      action=~"register|deregister",
      result="success"
    }[15m]
  )
)
~~~

### 10.4. Registration Churn Rate

~~~promql
sum by (service) (
  rate(
    service_registry_registration_events_total{
      action=~"register|deregister",
      result="success"
    }[5m]
  )
)
~~~

This yields the per-second event rate. To get the total event count over a time window, use `increase()`.

### 10.5. Registration Failures

~~~promql
sum by (service, operation) (
  increase(
    service_registry_registration_failures_total[5m]
  )
)
~~~

### 10.6. Snapshot Age

~~~promql
time() - service_registry_last_snapshot_timestamp_seconds
~~~

If this value increases continuously, the collector is failing to update snapshots. Distinguish this scenario from an instance gauge equal to 0.

## 11. Dashboard Design

A service discovery monitoring dashboard should include the following panels:

| Panel | Visualization Type | Question Answered |
|---|---|---|
| Current instances by service/status | Stacked bar or stacked area | How many `UP`, `warning`, and `critical` instances does each service have? |
| Register/deregister over time | Time series | Is there a deployment, scaling event, or abnormal churn? |
| Status transitions | Time series | Are instances flapping between `UP` and `DOWN`? |
| Registration failures | Time series | Is the registry rejecting or failing to accept operations? |
| Registration latency | Histogram/quantile | Are registration operations unusually slow? |
| Snapshot age | Stat/time series | Is the collector successfully reading the registry? |
| Healthy vs desired capacity | Gauge/bar | Is the healthy instance count below demand? |

Allow filtering by registry, service, environment, cluster, and datacenter. Across multiple regions, compare total instances with per-region instance counts to detect distribution skew.

A dashboard showing only a total-instance panel makes it hard to spot scenarios such as:

- Total count stays constant while instances are continuously replaced.
- Total registrations are high while healthy count is low.
- The collector cannot read the registry and is displaying a stale snapshot.
- Consumers see fewer instances than the registry holds.
- One datacenter loses registrations while other datacenters remain normal.

## 12. Alerting Should Focus on Meaningful Behavior

Not every registration or deregistration is an incident. Rolling deployments generate normal churn. Alerts should factor in service criticality, desired capacity, duration, and rate of change.

### 12.1. No Healthy Instances Remaining

~~~yaml
groups:
  - name: service-discovery
    rules:
      - alert: ServiceHasNoHealthyInstances
        expr: |
          sum by (service) (
            service_registry_instances{status=~"UP|passing"}
          ) == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.service }} has no healthy instances"
~~~

The gauge metric needs to emit `0` for known services even when no instances exist. If the time series disappears completely, the expression above may return no series; in that case, use `absent()` or a recording rule backed by a known service inventory.

### 12.2. High Churn Spike

~~~yaml
- alert: ServiceRegistrationChurnHigh
  expr: |
    sum by (service) (
      increase(
        service_registry_registration_events_total{
          action=~"register|deregister"
        }[10m]
      )
    ) > 20
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Service {{ $labels.service }} has high registration churn"
~~~

The threshold of 20 is only an example. Set baselines according to service scale and deployment schedule. A service with hundreds of instances has a different normal churn level than a service with two instances.

### 12.3. Rising Registration Failures

~~~yaml
- alert: ServiceRegistrationFailures
  expr: |
    sum by (service) (
      increase(
        service_registry_registration_events_total{result="failure"}[5m]
      )
    ) > 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Registration errors detected for service {{ $labels.service }}"
~~~

### 12.4. Stale Snapshot

~~~yaml
- alert: ServiceRegistrySnapshotStale
  expr: |
    time() - service_registry_last_snapshot_timestamp_seconds > 120
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Registry snapshot is stale"
~~~

Set the threshold based on polling interval and timeout settings. If the collector runs every 30 seconds, a 120-second threshold can reasonably catch sustained failures, though it should be tuned per environment.

## 13. Registration Churn and Common Causes

Churn is the phenomenon of instances repeatedly appearing, disappearing, or changing status over a period of time. Low churn is normal during deployments or scaling. Sustained high churn can increase registry load, cache refreshes, DNS updates, and load balancer re-selections.

| Symptom | Possible Cause | Data to Cross-Check |
|---|---|---|
| Periodic rise in register/deregister | Rolling deployment, autoscaling, or restart loop | Deployment events, pod restarts, desired replicas |
| Instances flap UP/DOWN repeatedly | Flaky health checks, overly short timeouts | Health check latency, dependency health, logs |
| Instances disappear after network interruption | Lease/session expiration | Heartbeats, session events, network errors |
| Registration failures | ACLs, auth, wrong service name, or registry unavailable | Registry logs, ACL metrics, client errors |
| High registry count but low UP | Many registrations exist but fail health checks | Eureka status or Consul checks |
| Consumer sees fewer instances than registry | Stale cache, filters, zone, datacenter, or namespace | `DiscoveryClient` and LoadBalancer supplier |
| Only one datacenter lacks instances | Replication, federation, or region configuration | Datacenter/region metrics and registry state |

### 13.1. Distinguishing Real Churn from Heartbeats

Eureka uses heartbeats to renew leases. Increased heartbeat traffic does not mean increased registration churn. If heartbeat metrics rise while instance counts stay steady, that may simply be normal client activity.

Consul uses health checks and agent telemetry. A check transitioning from `passing` to `critical` and back to `passing` is a status transition, not necessarily a deregistration followed by re-registration.

Separate three event types:

1. **Registration lifecycle:** creation or removal of a registration.
2. **Health/status transition:** the instance still exists, but its status changes.
3. **Liveness/heartbeat:** the client or agent renews a lease/session or runs periodic checks.

## 14. Data Freshness and Drift Between Registry and Consumers

Registry snapshots, discovery caches, and LoadBalancer caches can update at different times. Therefore, dashboards should indicate both the metric source and the snapshot timestamp.

For example:

- Eureka Server has 5 `UP` instances.
- The consumer's Eureka Client fetched the registry before the most recent deregistration, so it still sees 5.
- The LoadBalancer cache still holds the list of 5 instances.
- A subsequent request may still select the recently removed endpoint.

To investigate, collect counts from three perspectives:

| Perspective | Metric or Check |
|---|---|
| Registry server | Number of registrations and statuses in the registry |
| DiscoveryClient | Instance list received by the consumer |
| LoadBalancer | Candidate list after supplier/filters |

Do not compare two snapshots taken at different times without recording timestamps. With Consul, keep datacenter, namespace, partition, and filters consistent across queries. With Eureka, inspect peer replication status and client fetch intervals if counts diverge between server and consumer.

## 15. Security and Metric Access Control

Metrics can reveal internal service names, topology, datacenters, deployment state, and instance counts. Ensure that:

- Only Prometheus or monitoring agents can access metrics endpoints.
- Actuator `metrics`/`prometheus` endpoints are never exposed to the public Internet.
- Consul agent metrics and APIs are protected with appropriate network policies, ACLs, and TLS.
- Tokens, secrets, sensitive hostnames, or personal data are never placed in labels.
- Dashboard access is restricted by role.
- Registration metrics are never treated as proof of service identity authentication.

If metrics are scraped from the registry server, the exporter should have read-only permissions as needed. Never use a token with registration-write permissions solely to collect metrics.

## 16. Step-by-Step Implementation Workflow

1. Choose the source of truth for registrations: Eureka server, Consul Catalog/Health API, or another registry.
2. Clearly define registered, healthy, eligible, and reachable counts.
3. Enable built-in backend metrics where appropriate, such as the Eureka instance gauge.
4. Add a snapshot collector if per-service/status counts are needed and not provided by the backend.
5. Instrument register, deregister, status changes, and failures at the event source.
6. Do not count heartbeats as registration events.
7. Export metrics via Micrometer/Prometheus or a telemetry exporter.
8. Build dashboards segmented by service, status, datacenter, and registry.
9. Configure alerts for zero healthy instances, high churn, registration failures, and stale snapshots.
10. Test deployment, scaling, graceful shutdown, abrupt crash, health failure, and registry outage scenarios.
11. Cross-check registry server metrics against consumer `DiscoveryClient` and LoadBalancer views.
12. Evaluate cardinality and retention before expanding label sets.

## 17. Key Takeaways

- Current registration count is a gauge; register/deregister counts are counters.
- Registered, healthy, eligible, and reachable are four distinct sets.
- Eureka provides the `eureka.server.instances` gauge by application/status; it requires `eureka.server.metrics.enabled=true` and is disabled by default.
- Consul provides metrics for catalog operations and API requests; they do not replace per-service inventory gauges.
- Consul Catalog counts registrations; the Health API provides checks and instance health states.
- To get counts by service/status, use registry snapshots or an exporter; to get a complete history of all changes, collect events at the source.
- Never count heartbeats as registrations; nor is a status transition a deregistration.
- Keep label cardinality low; avoid instance IDs, IPs, trace IDs, and exception messages.
- Track snapshot timestamps to distinguish services with zero instances from a collector failing to read the registry.
- Compare registry, `DiscoveryClient`, and LoadBalancer views to pinpoint causes of count drift.

Tracking instance counts alongside registration churn helps distinguish capacity shortages, health degradation, and churn caused by deployments or network issues. When gauges reflect well-sourced snapshots and counters capture real events, dashboards can show how many instances a service has, what their status is, and why those numbers are changing.

## References

- [Spring Cloud Netflix — Eureka Server Metrics](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Consul — Agent Telemetry Metrics](https://developer.hashicorp.com/consul/docs/reference/agent/telemetry)
- [Consul — Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul — Health HTTP API](https://developer.hashicorp.com/consul/api-docs/health)
- [Spring Boot — Actuator Metrics and Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/)
