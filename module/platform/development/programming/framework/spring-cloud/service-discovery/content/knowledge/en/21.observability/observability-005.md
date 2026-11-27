# Tracking Heartbeats, Health Checks, and Stale Data

In Spring Cloud Service Discovery, a registry helps consumers locate instances by service ID. However, an entry in the registry does not by itself prove an instance is still running or capable of serving requests. An instance may have stopped while its entry remains; an instance may have recovered while consumers still hold a stale cache; or heartbeats may keep arriving regularly while the business endpoint is already failing.

For reliable discovery observability, track three signals separately: heartbeats/leases, health check results, and registry/cache data freshness. This article explains how to read those signals in Eureka and Consul, measure update latency, build alerts, and investigate stale registrations.

## 1. Distinguishing Heartbeats, Health Checks, and Registry Freshness

These three concepts answer different questions:

| Signal | Question | Typical Mechanism |
|---|---|---|
| Heartbeat / lease renewal | Is the registry still receiving signals from the instance? | Eureka client sends heartbeats; Consul TTL check receives heartbeats |
| Health check | Does the instance meet configured health criteria? | Consul Agent calls HTTP/TCP/script checks; Actuator health indicator |
| Registry freshness | How recently updated is the data consumers are seeing? | Registry response cache, client fetch cache, LoadBalancer cache |

For example, the JVM may still send heartbeats to Eureka even though the database connection is lost and the application is no longer ready to serve requests. In that case, heartbeats look healthy while health is actually degraded.

Conversely, the application may have recovered and its health endpoint returns `UP`, yet the Consul Agent has not executed its next check or the consumer has not refreshed its cache. The registry/client can still show the old status for some time.

Therefore, never use a single signal to conclude a service is healthy. Combine heartbeats, health checks, registration state, update timestamps, and actual call success from consumers.

## 2. Heartbeats and Leases in Eureka

Eureka Client registers an instance with Eureka Server and then sends periodic heartbeats to renew its lease. Common default values:

| Property | Typical Default | Role |
|---|---:|---|
| eureka.instance.lease-renewal-interval-in-seconds | 30 seconds | Interval at which the client sends heartbeats |
| eureka.instance.lease-expiration-duration-in-seconds | 90 seconds | Time the server waits for a heartbeat before expiring the lease |
| eureka.client.registry-fetch-interval-seconds | 30 seconds | Interval at which the client fetches the registry |
| eureka.server.response-cache-update-interval-ms | 30000 ms | Interval at which the server updates its response cache |

Actual values depend on the application's version and configuration. When investigating, check the effective configuration on both client and server rather than reading only the YAML file in the repository.

Example client configuration:

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90
      client:
        registry-fetch-interval-seconds: 30

Heartbeats indicate that the server is still receiving signals from the client. They do not replace the application's health check. If you want Spring Boot health status reflected into Eureka, you can enable health check integration:

    eureka:
      client:
        healthcheck:
          enabled: true

Set this property in `application.yml` or the corresponding application configuration so health status is initialized alongside `ApplicationContext`. Exact behavior depends on the Spring Cloud Netflix version and the `HealthCheckHandler` in use.

## 3. Self-Preservation Affects Stale Data Detection

Eureka includes a self-preservation mechanism to avoid mass-evicting instances when the server receives fewer heartbeats than expected. Missing heartbeats can mean many instances truly died, or they can result from a network partition, high load, or the server temporarily failing to receive heartbeats.

When self-preservation activates, Eureka pauses eviction. Consequently, stopped instances can remain in the registry longer than the expected lease expiration window.

Related properties:

    eureka:
      server:
        enable-self-preservation: true
        renewal-percent-threshold: 0.85
        expected-client-renewal-interval-seconds: 30

Do not treat an instance still present in Eureka as proof that it is alive while the server is in self-preservation mode. Monitor the self-preservation state, received vs. expected heartbeats, and eviction logs.

Do not disable self-preservation just to make dashboards remove instances faster. In production, this mechanism protects the registry during widespread network disruptions. If you experiment with changing the heartbeat interval, synchronize `expected-client-renewal-interval-seconds` on the server and measure the impact before deploying.

## 4. Health Checks in Consul

Consul Agent manages health checks attached to services. For HTTP checks, the agent actively calls the endpoint on the declared interval. A typical Spring Cloud Consul configuration using Actuator:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s
            health-check-timeout: 3s
            query-passing: true

Consul HTTP checks typically interpret response codes as follows:

| HTTP Response | Consul Status |
|---|---|
| 2xx | passing |
| 429 | warning |
| Other codes, connection error, or timeout | critical |

Consul Agent executes requests from the agent's own network location. An endpoint may work when called from the host machine yet fail when the agent resides in a different container or subnet. Always test from the Consul Agent's exact network namespace.

Setting `query-passing=true` instructs Spring Cloud Consul to retrieve only instances with passing checks when querying health services. If disabled, discovery results may include non-passing statuses depending on the API and query mode.

## 5. TTL Checks and Active Heartbeats in Consul

Besides HTTP/TCP/script checks, Consul supports TTL checks. With TTL, the application or integration component actively sends heartbeats to the Consul Agent to renew check status.

Spring Cloud Consul can enable TTL heartbeats:

    spring:
      cloud:
        consul:
          discovery:
            heartbeat:
              enabled: true
              ttl: 30s

With a TTL check, the application must update its status on time. If the agent does not receive a heartbeat before the TTL expires, the check transitions to `critical`. TTL is not the same as HTTP `health-check-timeout`:

- `TTL` is the deadline Consul waits for the next heartbeat.
- `health-check-timeout` is the maximum wait time for a single HTTP check call.
- `health-check-interval` is the interval between active endpoint calls by the agent.

Choose a TTL with sufficient headroom over the heartbeat interval, accounting for scheduler delays, JVM pauses, and network jitter. If the TTL is too short, a single GC pause or slow network packet can flip a healthy instance to `critical`.

A TTL heartbeat only confirms that the component sending heartbeats can still talk to the agent. If heartbeats are sent by a scheduler independent of request handling, they can keep arriving even when the business API is broken. To verify serving capability, you need health checks that accurately reflect dependencies and application state.

## 6. Spring Boot Health Indicators and Readiness

Spring Boot Actuator aggregates `HealthIndicator` beans to compute health status. Some indicators check datasources, disk space, or integrated dependencies; applications can also add custom indicators.

Common endpoints:

    /actuator/health
    /actuator/health/liveness
    /actuator/health/readiness

Liveness indicates whether the process can keep running or needs a restart. Readiness indicates whether the application should accept new traffic. These two signals should not be conflated:

- A temporary database outage may mark readiness `DOWN` if the database is essential for requests.
- Liveness typically should not depend on all external services, avoiding cascading restarts when a dependency has an outage.
- During a planned drain, readiness can transition to `REFUSING_TRAFFIC` while liveness remains `CORRECT`.

Health endpoints must be lightweight and have bounded timeouts. Never invoke a chain of downstream services or run heavy queries on every Consul Agent check; doing so adds extra load and can turn the health check itself into an outage trigger.

Keep `show-details` appropriately restricted and never expose connection strings, secrets, or sensitive details to public networks.

## 7. Stale Records and Forms of Stale Data

Stale data does not only mean a dead instance lingering in the registry. It takes several distinct forms:

| Form of Stale Data | Example | Common Causes |
|---|---|---|
| Stale registration | Instance stopped, but record remains | Shutdown without deregistration, lease not yet expired, self-preservation |
| Stale health status | Application recovered, but check stays critical | Next check hasn't run yet, agent error, or endpoint still blocked |
| Stale client cache | Registry updated, but consumer still sees old instances | Registry fetch interval or client cache |
| Stale load-balancer cache | Discovery client has fresh data, but requests still pick old instances | LoadBalancer cache/list supplier |
| Orphan catalog record | Catalog still lists service, but source agent/workload is gone | Node died, agent out of sync, deregistration failed |
| Duplicate registration | One service has both old and new instance IDs | Changed instance ID, overlapping deployments, or missing deregistration |

Determine which layer holds the stale data before deleting a record. If you only delete from the Catalog while an agent or orchestrator still owns the registration, the service may reappear. If the registry is already accurate while the consumer cache has not refreshed, deleting registrations again will not fix the root cause.

## 8. Tracking Data Freshness Across Layers

A discovery flow passes through multiple update layers:

    Service instance
       |
       | heartbeat / health check
       v
    Consul Agent or Eureka Server
       |
       | catalog / registry update
       v
    Registry response cache
       |
       | client fetch / discovery query
       v
    DiscoveryClient cache
       |
       | supplier/cache refresh
       v
    Spring Cloud LoadBalancer
       |
       v
    Consumer request

Each layer can hold old data for some period. To measure freshness, record key timestamps:

- Time the instance started and registered.
- Time of the most recent successful heartbeat.
- Time of the most recent health check and returned status.
- Time the registry recorded the new status.
- Time the consumer first observed the change.
- Time the last request was sent to a failed instance.

You can define derived metrics:

- Heartbeat age: current time minus most recent successful heartbeat timestamp.
- Health-check age: current time minus most recent check timestamp.
- Registry propagation delay: time consumer observed the change minus time registry recorded the change.
- Stale selection count: number of requests routed to instances confirmed to be out of service.
- Orphan registration age: duration an entry without a valid owner/agent remains present.

These indicators help distinguish slow incident detection from slow propagation.

## 9. Metrics to Track

Metrics can be divided into four groups:

| Group | Suggested Metrics | Meaning |
|---|---|---|
| Heartbeat/lease | Heartbeat success, heartbeat failure, heartbeat age, lease expiry | Is the client still maintaining its registration? |
| Health | Check status by passing/warning/critical, check duration, check failure count | Does the instance meet health criteria? |
| Discovery | Lookup count, lookup error, lookup latency, returned instance count | Are consumer registry lookups succeeding? |
| Freshness/routing | Registry propagation delay, cache age, requests to stale instances | Is the data fresh enough for routing? |

Specific metric names depend on your exporter and version. The names in the table represent concepts to instrument, not default metric names guaranteed to exist in every Spring Cloud version.

With Micrometer, you can create custom metrics for lookup counts and errors:

    import io.micrometer.core.instrument.MeterRegistry;
    import org.springframework.stereotype.Component;

    @Component
    public class DiscoveryMetrics {

        private final MeterRegistry registry;

        public DiscoveryMetrics(MeterRegistry registry) {
            this.registry = registry;
        }

        public void recordLookup(String provider, String serviceId) {
            registry.counter(
                    "discovery.lookup",
                    "provider", provider,
                    "service", serviceId
            ).increment();
        }

        public void recordLookupFailure(String provider, String serviceId) {
            registry.counter(
                    "discovery.lookup.failure",
                    "provider", provider,
                    "service", serviceId
            ).increment();
        }

        public void recordLookupLatency(
                String provider,
                String serviceId,
                Runnable lookup) {
            registry.timer(
                    "discovery.lookup.duration",
                    "provider", provider,
                    "service", serviceId
            ).record(lookup);
        }
    }

This is an example of instrumenting at the call layer; integrate it into real code paths and avoid recording a metric only on invocation without capturing the outcome. You can add a `Timer` for health-check duration and a `Gauge` for instance counts by service/status.

Do not place high-cardinality values such as instance ID, IP, request ID, or user ID into metric labels if their cardinality can grow unbounded. Those granular details belong in structured logs or trace attributes. Keep labels to bounded sets such as `provider`, `service`, `status`, and `environment`.

## 10. Logs and Traces for Investigating Stale Registrations

Metrics tell you there is a problem and its scope; logs and traces help uncover the root cause.

Logs should include fields such as:

- `provider`: `eureka` or `consul`.
- `service_id` and `instance_id`.
- `node` or `datacenter` if supported by the provider.
- `operation`: `register`, `heartbeat`, `health_check`, `lookup`, `status_change`, or `deregister`.
- `status_before` and `status_after`.
- Published `endpoint`/`host`/`port`, after stripping sensitive data.
- `duration_ms`, `result`, and `error_type`.
- `timestamp` and `trace`/`correlation ID` if the operation occurs within a management request.

Example structured log:

    {
      "event": "discovery_health_check",
      "provider": "consul",
      "service_id": "inventory-service",
      "instance_id": "inventory-1",
      "status": "critical",
      "duration_ms": 3000,
      "reason": "timeout"
    }

Never log ACL tokens, passwords, URIs containing credentials, or health details holding sensitive data.

Tracing is helpful when correlating a failed request with the selected instance. Add the selected `service ID`, `instance ID`, and `endpoint` to span attributes in a controlled way. Periodic heartbeats do not necessarily need their own traces; if observation is needed, instrument management operations or client calls separately and avoid generating a trace for every high-frequency heartbeat.

## 11. Discovery Observability Dashboards

An operational dashboard should answer four questions:

1. How many instances are registered per service?
2. How many instances are `passing`, `warning`, `critical`, or `OUT_OF_SERVICE`?
3. When did the latest heartbeat and health check occur?
4. What instance list is the consumer receiving, and where are actual requests being sent?

Panels can be arranged as follows:

| Panel | Content | Signals to Watch |
|---|---|---|
| Instance inventory | Instance count by service and status | Sudden drop in passing instances |
| Heartbeat age | Age of most recent heartbeat/lease | Age exceeding expected lease threshold |
| Health check | Status and response duration | Sustained critical or rising check duration |
| Registry freshness | Update timestamps of registry and consumer cache | Rising propagation delay |
| Discovery lookup | Error rate and latency | Rising lookup errors or empty lists |
| Routing | Requests per instance and connection errors | Consumers still calling stale instances |

Dashboards should allow filtering by environment, provider, service ID, and datacenter. Never mix dev/test/prod data in the same panel without clear environment labels.

## 12. Building Meaningful Alerts

Alerts should reflect service impact rather than firing on a single delayed heartbeat.

Example policies:

- High heartbeat age: alert when heartbeat age exceeds a significant fraction of lease expiration across multiple evaluation windows.
- Sustained critical: alert when a check stays critical longer than the service's normal recovery time.
- Insufficient healthy instances: alert when passing instances drop below the service's minimum capacity.
- Discovery lookup failures: alert when error rate or latency exceeds SLO.
- Stale routing: alert when requests keep hitting instances already confirmed as critical or deregistered.
- Orphan records: alert when registrations lack an active agent/workload owner for an extended duration.

For Eureka, when self-preservation is active, alert separately on that mode and compare received vs. expected heartbeats. Avoid alerting solely on expired leases to trigger deletion if the server is actively preserving the registry.

For Consul, monitor how long checks stay critical and configure `DeregisterCriticalServiceAfter` if you want prolonged failed services cleaned up automatically. That critical timeout is how long the registration is retained before deregistration; it is not the timeout of a single HTTP health check.

## 13. Investigating Failed Instances Still Appearing in Discovery

When consumers report still receiving instances that are no longer running, investigate in order:

1. Identify the exact instance: extract `service ID`, `instance ID`, `host`, `port`, `node`, and `datacenter` from consumer results.
2. Check the registry: inspect its current state in Eureka or Consul, update timestamp, and health check.
3. Check heartbeats: determine the latest heartbeat and whether the lease is still valid or expired.
4. Check self-preservation: for Eureka, verify whether the server has paused eviction.
5. Check the agent: for Consul, compare `/v1/agent/services` and `/v1/agent/checks` against the Catalog.
6. Check the client cache: invoke discovery from the consumer and compare against the registry server.
7. Check LoadBalancer: identify which cache or supplier still holds the instance.
8. Check the network path: call the published host/port directly from the consumer to distinguish a stale registry from a broken route.
9. Identify the owner: check which application, Consul Agent, config file, or orchestrator can still re-register the instance.
10. Clean up records only after confirmation: deregister at the true owning source and monitor to ensure the record does not reappear.

With Consul, you can use these read APIs:

    GET /v1/agent/services
    GET /v1/agent/checks
    GET /v1/catalog/service/inventory-service
    GET /v1/health/service/inventory-service?passing

Comparing the local agent with the catalog reveals whether the registration still exists on the agent or only in the catalog. If the agent still owns the registration, deleting directly from the catalog may cause the agent to re-sync and recreate the entry.

## 14. Investigating Recovered Instances Still Excluded

The reverse scenario also happens frequently: an application is healthy again, yet consumers do not see the instance.

Check:

- Does the health endpoint already return HTTP 2xx or `UP`?
- Has the Consul Agent run its next check yet?
- If using TTL, has the application sent a passing heartbeat to the agent?
- Is the service in maintenance mode or `OUT_OF_SERVICE`?
- Has the Eureka client sent its updated heartbeat/health status?
- Has the consumer fetched the updated registry yet?
- Is `query-passing` filtering out the instance because another check is still `warning`/`critical`?
- Has the LoadBalancer cache refreshed yet?

Do not restore traffic solely because the process is running. Verify readiness, registry status, and real requests before returning the instance to the pool.

## 15. Distinguishing Stale Data from Unfiltered Health Queries

Some cases look like stale data when the real cause is a query that does not filter for healthy instances.

In Spring Cloud Consul, `query-passing` defaults to `false`. When disabled, results may include service instances with `warning` or `critical` health checks depending on the query mode. If the application should only use passing instances, enable `query-passing` and check the Health API endpoint used by the provider.

In Eureka, clients maintain a local registry cache. Instances can remain in cache until the next fetch cycle. Additionally, self-preservation can make the server retain expired leases during network incidents. Separate server registry state from client cache state.

Therefore, whenever you see a failing instance, inspect both check statuses and how the query is performed. Never conclude a registry is stale from an unfiltered list alone.

## 16. Hands-On Lab: Observing Heartbeats and Stale Data

You can run a controlled experiment with two `inventory-service` instances:

1. Start Eureka or Consul and register two instances.
2. Record each `service ID`, `instance ID`, published address, and registration timestamp.
3. Observe successful heartbeats or TTL renewals.
4. Call the health endpoint and record response times.
5. Gracefully stop one instance; observe deregistration and how long it takes for the consumer to stop seeing it.
6. Restart the instance, then abruptly cut its network to simulate lost heartbeats.
7. Watch lease expiration or the Consul check transitioning to `critical`.
8. Compare registry state with the consumer's `DiscoveryClient` output.
9. Measure the time from when the registry changes until LoadBalancer stops selecting the instance.
10. Restore the network and observe how long it takes the instance to return to `passing`/`UP`.
11. Test `query-passing=false` and `true` in Consul to observe the difference in returned lists.
12. With Eureka, observe self-preservation in an isolated test environment and do not apply that test configuration to production.

Record timestamps for each event to compute heartbeat age, health-check age, and propagation delay. Repeat the test under load and during GC pauses to understand realistic jitter.

## 17. Operational Principles

- Track heartbeats and health checks as two separate signals.
- Measure registry and cache freshness on the consumer side.
- Keep health endpoints lightweight with bounded timeouts that accurately reflect readiness.
- With Consul, consider `query-passing` if consumers must only receive passing instances.
- With Eureka, monitor self-preservation and never disable it merely for faster eviction.
- Size TTLs and leases with headroom for network jitter and JVM pauses.
- Use graceful shutdown to deregister on planned stops; rely on health/lease timeouts as a fallback for unexpected failures.
- Never delete from the catalog before identifying which agent or orchestrator owns the registration.
- Bound metric label cardinality; keep granular instance IDs in logs/traces.
- Protect Actuator, Consul API, and Eureka management endpoints with authentication, ACLs, and network policies.
- Base alerts on impact and sustained duration; avoid reacting to a single delayed check.

## 18. Conclusion

Heartbeats indicate that an instance still maintains contact with the registry; health checks indicate whether the instance meets health criteria; registry freshness indicates how up to date the consumer's view is. Eureka uses heartbeats/leases and self-preservation; Consul uses active checks or TTL heartbeats and can filter results with `query-passing`.

To detect stale data, monitor the latest heartbeat timestamp, health check status and age, registry update time, consumer cache state, and actual requests. When handling stale registrations, identify the right data layer and owning source before deregistering. Combining metrics, structured logs, traces, and disconnect testing helps distinguish genuinely failing instances from discovery data that is simply lagging behind.

## References

- [Spring Cloud Netflix — Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka — Server Self-Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Spring Cloud Consul — Service Discovery and Health Checks](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [HashiCorp Consul — Health API](https://developer.hashicorp.com/consul/api-docs/health)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Micrometer — Metrics](https://docs.micrometer.io/micrometer/reference/index.html)
