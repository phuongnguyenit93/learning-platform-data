# Circuit Breaker Health Indicators and Their Impact on Readiness

A Circuit Breaker provides a signal about dependency health: the breaker may be CLOSED, OPEN, or HALF_OPEN. Spring Boot Actuator can expose this information through the health endpoint so operations teams and deployment platforms can observe service protection status. However, tying Circuit Breaker state into readiness directly affects whether an instance receives traffic. If an optional dependency fails and shifts the entire instance to NOT_READY, the application can remove itself from the load balancer even while still able to serve most requests.

In the SPRING_CLOUD_CIRCUIT_BREAKER module, this lesson explains how to enable the Resilience4j health indicator, read breaker status via Actuator, organize health groups, and decide whether to include breakers in readiness. The focus is distinguishing diagnostic health from traffic-routing readiness and process-vitality liveness.

## 1. Distinguishing Liveness, Readiness, and Aggregate Health

Three concepts are commonly used in Spring Boot Actuator and deployment platforms:

| Concept | Question | Typical Action Attached |
|---|---|---|
| Liveness | Is the process still running and able to continue? | On prolonged failure, the platform may restart the container |
| Readiness | Is the instance ready to accept new requests? | On failure, the platform temporarily stops sending traffic to the instance |
| Aggregate health | What status are monitored components reporting? | Used for diagnostics, dashboards, alerting, and operational checks |

Liveness should not depend directly on an external service such as Catalog, Payment, or Redis. If a dependency suffers an outage and liveness goes DOWN across every instance, Kubernetes can repeatedly restart healthy instances. Restarting does not fix an external dependency and further reduces serving capacity.

Readiness serves a different goal: deciding whether an instance can receive traffic. An application can remain READY even when an optional dependency is OPEN, provided it has a fallback or can still serve core functionality. Conversely, if a dependency is mandatory and no requests relying on it can complete, removing the instance from the load balancer may be appropriate.

Aggregate health can display Circuit Breaker status so operators see which dependency is degrading. You do not need to turn every DOWN status in aggregate health into a readiness failure.

## 2. Enabling the Resilience4j Health Indicator

For Actuator to publish Circuit Breaker status, the application needs Spring Boot Actuator and a Resilience4j integration compatible with the Spring Boot/Spring Cloud versions in use. Let the Spring Cloud BOM manage Spring Cloud versions; avoid manually mixing incompatible Resilience4j artifacts.

Configuration example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  health:
    circuitbreakers:
      enabled: true

resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
~~~

`management.health.circuitbreakers.enabled` enables the Circuit Breaker health indicator group in Actuator. `registerHealthIndicator` enables registering health information for the configured instance. The name `catalog-read` is the Circuit Breaker ID and must match the ID the application uses when creating the breaker.

If the application has many breakers, enable health indicators selectively for instances that need monitoring. Avoid registering excessive unnecessary details if a very large number of dynamic breakers are created; the health endpoint should keep its payload readable and stable.

Health endpoints can typically be inspected at:

~~~text
GET /actuator/health
GET /actuator/health/circuitBreakers
~~~

Exact component paths and contributor names can vary across starter versions and configurations. Inspect the actual aggregate health endpoint response to confirm exposed component names. If the component is missing, check Actuator dependencies, Resilience4j integration, the enable and `registerHealthIndicator` properties, and exposure settings.

## 3. Understanding Circuit Breaker Health Statuses

The health indicator maps Circuit Breaker state to a Spring Boot health status. With common Resilience4j integrations, CLOSED is reported as UP, OPEN as DOWN, and HALF_OPEN may be reported as UNKNOWN. Confirm the exact mapping and how the health aggregator combines statuses on your specific version.

| Circuit Breaker | Protection Meaning | Typical Health | Interpretation |
|---|---|---|---|
| CLOSED | Permits calls and records outcomes | UP | Dependency calls are permitted; does not guarantee every request succeeds |
| OPEN | Rejects new calls during wait period | DOWN | Dependency is isolated by the breaker due to errors or slow calls exceeding threshold |
| HALF_OPEN | Permits limited probe calls | UNKNOWN or intermediate status depending on integration | Breaker is evaluating recovery capability |

Health UP does not replace failure rate or latency metrics. A CLOSED breaker can still have an error rate below the opening threshold; some requests may still fail. Likewise, an OPEN breaker indicates the policy is blocking new calls, not necessarily that the entire application has stopped serving.

When health reports UNKNOWN, do not assume the dependency is healthy or broken. Check detailed breaker state, metrics, and logs. Actuator's overall status may use a status aggregator ordering DOWN, OUT_OF_SERVICE, UNKNOWN, and UP; this ordering affects health group results.

## 4. A Health Indicator Does Not Automatically Control Readiness

Enabling the health indicator only exposes breaker status in the health endpoint. It does not automatically make readiness depend on the breaker. Readiness is affected only when the health contributor is included in the readiness group or custom logic uses breaker state to decide readiness.

Spring Boot can enable health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

When probes are enabled, the application exposes readiness and liveness groups, typically at:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

You can check readiness status without adding Circuit Breakers to the group. Readiness then reflects the traffic-readiness conditions defined by Spring Boot and the application itself.

If you want to include Circuit Breakers in readiness, configure the health group, for example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,circuitBreakers
~~~

The contributor name `circuitBreakers` is a common name for the composite health contributor from the Resilience4j integration. Confirm it via the `/actuator/health` response before putting it into group configuration. If the name differs in your version, substitute the actual component ID. Never guess names in production because the health group might fail to initialize or omit the intended contributor.

## 5. When Should a Breaker Be Included in Readiness?

Include a Circuit Breaker in readiness only when that dependency's state truly determines whether the instance can serve requests. Consider dependency criticality, fallback availability, and the proportion of impacted requests.

| Scenario | Include in Readiness? | Reason |
|---|---|---|
| Catalog only provides supplementary images or descriptions; usable cache exists | Usually no | The application still serves core content |
| Recommendation is an optional feature | Usually no | Recommendations can be omitted when the breaker is OPEN |
| Payment authorization is mandatory for checkout endpoints with no alternative | Worth considering | The instance cannot complete this critical function |
| A critical dependency fails but only impacts one group of endpoints | Usually avoid marking the entire instance NOT_READY | Route or handle errors at the endpoint/feature level |
| Every request requires a mandatory datastore and cannot be served if disconnected | May be appropriate | The instance genuinely cannot handle useful requests |
| Breaker is HALF_OPEN probing recovery | Do not automatically remove the whole instance just for an intermediate state | Probe calls may succeed and the instance can still serve other requests |

An application often has multiple dependencies. If a single OPEN breaker makes readiness DOWN, the load balancer may pull all instances out of service because instances typically share the same dependency. As a result, READY instance count drops to 0 even though instances are alive and capable of serving features independent of the failing service.

This is a pitfall to avoid when designing readiness. For optional dependencies, keep breakers in aggregate health or a separate diagnostic health group while letting readiness reflect overall serving capability.

## 6. Creating a Dedicated Health Group for Dependencies

If you need an endpoint reflecting dependency status without affecting readiness, create a dedicated health group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        dependencies:
          include: circuitBreakers
~~~

After confirming the right component ID, the group endpoint can be accessed at:

~~~text
GET /actuator/health/dependencies
~~~

This group lets dashboards or monitoring systems inspect breaker states without directly altering readiness probe routing decisions.

You can organize multiple groups by purpose:

- `readiness`: whether the application can accept requests.
- `liveness`: whether the process can keep running or needs restarting.
- `dependencies`: status of dependencies and breakers for diagnostics.
- aggregate `health`: contributor information exposed for operations.

You do not need to put every health contributor into every group. Choose the right signal for the right decision.

## 7. Consequences When Readiness Transitions to NOT_READY

When the readiness endpoint returns an unhealthy status, the deployment platform typically stops routing new traffic to that instance. In Kubernetes, a failing readiness probe marks the Pod unready in EndpointSlice/Service routing. The container is not necessarily restarted; restarts are normally tied to liveness probe failures.

If an optional dependency's Circuit Breaker is wired into readiness, a downstream incident can trigger a cascade:

1. A shared dependency starts returning errors.
2. Circuit Breakers on application instances transition to OPEN.
3. The health indicator reports DOWN.
4. The readiness group containing that contributor turns DOWN.
5. Kubernetes removes the Pods from traffic-receiving endpoints.
6. READY Pod count drops, potentially down to 0.
7. New requests never reach the application even though many features could still operate.

Therefore, do not treat readiness as a mirror of aggregate health. Readiness must reflect an instance's ability to accept traffic according to the application's operational contract.

## 8. Liveness Must Not Depend on Circuit Breakers

Do not place dependency health indicators into the liveness group. If Catalog Service or Payment Service fails, restarting the caller application does not fix that external service. Repeated restarts also wipe local caches, force connection pool warm-up, and add load to struggling dependencies.

Liveness should focus on whether the process can keep running. If the application enters a deadlock or unrecoverable internal state, liveness can report failure so the platform restarts it. External dependency failures should be handled through Circuit Breakers, timeouts, Bulkheads, fallbacks, and operational alerts.

A configuration keeping liveness and readiness probes separate:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
        dependencies:
          include: circuitBreakers
~~~

This configuration illustrates keeping dependency status in its own group. Verify component names against the actual endpoint. If the application has another internal health contributor that belongs in readiness, add it intentionally.

## 9. Health Details and Endpoint Security

Health endpoints may contain dependency names, Circuit Breaker IDs, states, failure rates, or error information. Avoid exposing these details publicly to external users if doing so could reveal internal topology or system state.

You can restrict health details:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Depending on the Spring Boot version, `show-details` and `show-components` configuration may vary or be enforced via Spring Security. Expose only necessary endpoints and restrict access by environment. Kubernetes probes usually only need UP/DOWN status, not stack traces or exception messages.

Never place tokens, internal URLs with credentials, request payloads, or user information into health details. Errors should be categorized concisely without leaking sensitive data.

## 10. Combining Health with Metrics and Alerts

A health indicator is a snapshot at query time. It does not replace historical metrics. To understand how a breaker is behaving, monitor:

- Current state of each breaker: CLOSED, OPEN, HALF_OPEN.
- Number of state transitions over a time window.
- Failure rate and slow call rate.
- Number of calls rejected while the breaker is OPEN.
- Number of fallback activations and fallback success rate.
- Dependency p50, p95, and p99 latency.
- End-to-end request success rate and count of READY instances.

Use Actuator metrics with Micrometer and an appropriate exporter to send data to Prometheus or an existing observability system. The health endpoint supports quick inspection, while metrics enable trend analysis and alerting before outages drag on.

For example, a breaker staying OPEN for a few seconds may be normal protective behavior. If OPEN persists, fallback failures increase, and API p99 rises, an alert is warranted. Also monitor readiness across the entire deployment to detect cases where all Pods become NOT_READY due to a shared health contributor.

## 11. Readiness Testing Scenarios

Before bringing a health indicator into production readiness, test in an integration environment:

1. Dependency operating normally: breaker CLOSED, health indicator reflects healthy state.
2. Simulate dependency failure: breaker OPEN, health indicator reflects OPEN state.
3. Check readiness when breaker is OPEN for an optional dependency: instance remains READY if required by design.
4. Check readiness for a mandatory dependency: verify NOT_READY is intentional and does not unexpectedly take down all instances.
5. Recover dependency: breaker transitions HALF_OPEN then CLOSED per configuration; readiness recovers cleanly if coupled.
6. Simulate multiple instances sharing a dependency: confirm a shared incident does not inadvertently strip all deployment endpoints.
7. Check liveness: external dependency failure does not fail liveness.
8. Verify endpoints from the deployment platform's perspective: probe path, port, authentication, status codes, and timeouts must align.

Do not inspect only JSON responses. Verify actual routing behavior: which Pods remain in endpoints, how many replicas stay READY, whether requests route to other instances, and whether fallbacks sustain critical functions.

## 12. Decision Diagram for Including Circuit Breakers in Readiness

~~~mermaid
flowchart TD
    A["Circuit Breaker health indicator"] --> B{"Is the dependency mandatory to serve primary requests?"}
    B -- "No" --> C["Place in dependencies health group"]
    C --> D["Keep readiness independent"]
    B -- "Yes" --> E{"Is there a safe fallback and remaining serving capacity?"}
    E -- "Yes" --> C
    E -- "No" --> F["Consider adding to readiness"]
    F --> G{"Could impact mark every instance NOT_READY?"}
    G -- "Yes" --> H["Design readiness per feature or deployment policy"]
    G -- "No" --> I["Apply readiness with controlled scope"]
~~~

Readiness policy is an operational decision of the application, not a mandatory side effect of enabling a Circuit Breaker health indicator.

## Conclusion

The Resilience4j health indicator allows Actuator to expose Circuit Breaker state for diagnostics and monitoring. Distinguish aggregate health, readiness, and liveness: health shows component state, readiness governs whether an instance receives traffic, and liveness decides whether the process needs restarting. Include a breaker in readiness only when the dependency is genuinely mandatory with no safe fallback; keep optional dependency breakers in a dedicated health group. Monitor metrics, state transitions, and READY Pod counts alongside health checks to prevent one downstream outage from removing the entire deployment from routing.
