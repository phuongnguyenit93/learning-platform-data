# OPEN Duration Elapsed Without Any Probe Calls

In Resilience4j, a Circuit Breaker does not automatically send a request to the dependent service simply because the OPEN duration has expired. **waitDurationInOpenState** defines how long the breaker stays in the OPEN state before it can transition to HALF_OPEN. An actual call from the application is what gets permitted as a probe to check whether the dependency has recovered.

This is a common reason why operations teams see that the OPEN duration has elapsed yet observe no probe requests. The **automaticTransitionFromOpenToHalfOpenEnabled** property only controls automatic state transition via a scheduler; it does not generate health check requests. Accurate diagnosis requires distinguishing when the wait duration expires, when the state transitions to HALF_OPEN, and when a real request is actually permitted to reach the dependency.

## 1. OPEN Duration Expiring Does Not Mean a Probe Has Occurred

The Circuit Breaker state machine has three primary operational states:

- **CLOSED:** calls are permitted and outcomes are recorded in the sliding window.
- **OPEN:** new calls are rejected immediately without executing the supplier calling the dependency.
- **HALF_OPEN:** only a limited number of calls are permitted to pass through to test recovery.

When the failure rate or slow-call rate exceeds the threshold, the breaker transitions from CLOSED to OPEN. While OPEN, new requests are rejected. After **waitDurationInOpenState** expires, the breaker can transition to HALF_OPEN according to the configured mechanism.

However, the Circuit Breaker does not fabricate an HTTP request, call a health check endpoint, or send a message to the dependency. A probe is an actual business call sent by the application through the same Circuit Breaker once the breaker permits it. If there are no new requests, there are no probes to observe.

| Milestone | Meaning | Is Dependency Called? |
|---|---|---|
| Just transitioned to OPEN | Breaker begins rejecting new calls | No |
| Wait duration not yet expired | Still inside protection period | No |
| Wait duration expired, auto-transition disabled | May still show OPEN until the next call arrives | Not yet |
| Wait duration expired, auto-transition enabled | State can transition to HALF_OPEN via scheduler | Not yet, if there are no requests |
| New request permitted in HALF_OPEN | An actual probe is executed | Yes |
| Sufficient probe outcomes collected | Breaker decides CLOSED or OPEN per configuration | Probes were sent |

Therefore, the first diagnostic question is not merely "how long has it been?", but "since that time, has any request passed through the exact Circuit Breaker instance?".

## 2. Default Mechanism: Transition to HALF_OPEN on the Next Call

Resilience4j's **automaticTransitionFromOpenToHalfOpenEnabled** property typically defaults to **false**. When automatic transition is disabled, no background thread switches the state the moment the wait duration ends. The breaker transitions from OPEN to HALF_OPEN when a new call arrives after the wait duration has elapsed.

Example configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: false
        permittedNumberOfCallsInHalfOpenState: 3
~~~

With the configuration above:

1. The Circuit Breaker transitions to OPEN and starts the 15-second wait period.
2. During those 15 seconds, new calls are rejected.
3. After 15 seconds, the state may still be reported as OPEN if no subsequent request has arrived.
4. The next request passing through the factory with ID **inventory** triggers the elapsed-time check and may be permitted in HALF_OPEN.
5. Up to three probe calls are permitted per configuration.
6. The probe outcomes determine whether the breaker closes or re-opens.

In low-traffic systems, the OPEN state can persist longer than the configured duration on dashboards. That is not necessarily a timer bug; there may simply have been no calls to trigger the transition under the default mechanism.

## 3. Enabling automaticTransitionFromOpenToHalfOpenEnabled

If you want the state to transition to HALF_OPEN automatically after the OPEN duration expires even without incoming requests, enable **automaticTransitionFromOpenToHalfOpenEnabled**:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 3
~~~

When this property is enabled, Resilience4j uses a scheduler mechanism to transition the state from OPEN to HALF_OPEN once the wait duration expires. This avoids waiting for a new request just to perform the state transition.

However, understand the limitation clearly: the scheduler only changes the state. It does not call **inventoryClient**, send HTTP requests, or check endpoints on its own. If no requests pass through the Circuit Breaker after the state becomes HALF_OPEN, the breaker still has no probe outcomes to evaluate recovery.

| Configuration | Behavior After Wait Duration Expires | Requirement for a Probe |
|---|---|---|
| **automaticTransitionFromOpenToHalfOpenEnabled: false** | Transitions state when the next call arrives | A new request must pass through the breaker |
| **automaticTransitionFromOpenToHalfOpenEnabled: true** | Scheduler transitions state to HALF_OPEN | A new request must still arrive to be permitted |

Enabling automatic transition is appropriate when you need state transitions independent of traffic. Do not enable it expecting the system to actively ping the dependency. If an operational requirement calls for proactive health checks, design a dedicated health checker with timeouts, concurrency limits, and safety policies; do not confuse it with probes granted by the Circuit Breaker to application requests.

## 4. permittedNumberOfCallsInHalfOpenState Only Caps Permitted Probes

In HALF_OPEN, **permittedNumberOfCallsInHalfOpenState** determines how many calls are permitted to execute to evaluate the dependency. Example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        waitDurationInOpenState: 10s
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 2
        failureRateThreshold: 50
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
~~~

When the state transitions to HALF_OPEN, at most two calls are permitted as probes under this policy. If there is no traffic, the actual number of probes remains 0. If only one request arrives, only one probe executes; the breaker must receive enough outcomes according to the mechanism and configuration of the version in use before deciding the next state.

Do not set the probe count too high, because the purpose of HALF_OPEN is to test recovery without sending a sudden burst of load to the dependency. Do not set it too low either if a single outcome is easily skewed by transient network noise. Choose the count based on traffic, stability, and the dependent service's load capacity.

If requests are retried, pay attention to coordination order. Retry wrapping outside the Circuit Breaker can send each attempt through the breaker and consume multiple probe slots. Circuit Breaker wrapping outside Retry may grant a single permission for the entire logical operation while Retry performs multiple internal attempts. Account for actual requests reaching the dependency, not just logical business requests.

## 5. Check Whether Requests Pass Through the Right Circuit Breaker ID

Another common cause is that the application is sending traffic, but requests are not passing through the instance the team is watching. For example, code calls:

~~~java
return circuitBreakerFactory.create("inventory-read").run(
    () -> inventoryClient.getStock(sku),
    error -> Stock.unavailable(sku)
);
~~~

While the Resilience4j configuration declares:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Here, the code uses ID **inventory-read**, while properties configure instance **inventory**. The team may be checking metrics for **inventory** while actual requests use **inventory-read**. Keep names consistent across the factory, instance configuration, logs, and dashboards.

With Spring Cloud Gateway, also check the name in the filter:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
~~~

The **args.name** value is the filter's Circuit Breaker ID. The route ID is **inventory-route**, not the instance name. If dashboards monitor **inventory-read** while the Gateway uses **inventory**, the two breakers have different scopes.

Check the following:

- The name in **CircuitBreakerFactory.create(id)** or filter **args.name**.
- The instance name under **resilience4j.circuitbreaker.instances**.
- The name appearing in metrics and events.
- The route or service actually invoked by incoming requests.
- Whether requests are handled by a cache, another filter, or a fallback before reaching the Circuit Breaker.

## 6. Considerations When Running Multiple Replicas or Pods

Resilience4j Circuit Breaker normally stores state in process memory. Each JVM or pod has its own registry and state. Having the same name **inventory** across six pods does not mean there is a single cluster-wide state machine.

Example:

| Pod | Local State | Time OPEN |
|---|---|---|
| app-1 | OPEN | 10:00:00 |
| app-2 | CLOSED | Not opened |
| app-3 | OPEN | 10:00:04 |
| app-4 | CLOSED | Not opened |

When **app-1**'s wait duration ends, the next request might be routed by the load balancer to **app-2**. Pod **app-2** is CLOSED, so the call executes normally; it is not a probe for **app-1**. Conversely, a request may land on **app-1** and become a probe if that pod's state is ready for HALF_OPEN.

This makes cluster-wide aggregate dashboards misleading. Some pods may be OPEN while others stay CLOSED, and probe counts vary with per-pod traffic. Inspect metrics per instance/pod and logs containing process identifiers.

Do not assume Resilience4j Circuit Breaker synchronizes state across pods automatically. If a cluster-wide shared breaker is required, you need a dedicated distributed design or a shared-layer admission control mechanism. Weigh latency, availability, and the risk of a distributed state store failing before choosing that approach.

## 7. Other Reasons Why No Probes Appear

Beyond lack of traffic, check these scenarios:

| Cause | Symptom | How to Verify |
|---|---|---|
| Requests never reach the protected service or route | No incoming gateway/service logs | Check route predicates, ingress, auth, and traffic |
| Requests go through a different Circuit Breaker ID | Watched instance metrics never change | Cross-check factory ID, filter name, and properties |
| Traffic is cached or served by an earlier fallback layer | Caller gets responses, but dependency receives no requests | Trace filter ordering and client logs |
| Local state differs on another pod | Per-pod metrics differ | Split dashboard views by pod/instance |
| Circuit Breaker is set to FORCED_OPEN | Requests are always rejected even after wait duration expires | Check administrative actions or state configuration |
| HALF_OPEN probe slots are already exhausted | Some probes ran, then subsequent requests were rejected | Check permitted count and each probe's outcome |
| Probes are running very slowly | HALF_OPEN does not yet have enough outcomes | Check timeouts, latency, and in-flight requests |
| Configuration failed to bind | State transitions do not match expected values | Check startup logs, active profile, and property names |

Resilience4j also provides administrative states such as **FORCED_OPEN**, **DISABLED**, or **METRICS_ONLY**. If the breaker was manually transitioned to FORCED_OPEN, do not expect the normal OPEN timer to move it to HALF_OPEN automatically. Identify who or what changed the state and restore it through the appropriate administrative procedure.

If HALF_OPEN has probes that never complete, check HTTP client timeouts, TimeLimiter, Bulkhead, and executor resources. The state cannot evaluate outcomes while probe calls remain hanging.

## 8. Observe State Transitions and Probe Counts

Do not rely solely on a single OPEN or HALF_OPEN log line. Track both state transitions and the actual number of calls reaching the dependency.

You can register an event listener on the Resilience4j Circuit Breaker to record state transitions:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerObservationConfiguration {

    @Bean
    ApplicationRunner observeInventoryBreaker(
            CircuitBreakerRegistry registry) {
        return args -> {
            var breaker = registry.circuitBreaker("inventory");

            breaker.getEventPublisher()
                .onStateTransition(event ->
                    log.info(
                        "Circuit Breaker inventory: {}",
                        event.getStateTransition()
                    )
                )
                .onCallNotPermitted(event ->
                    log.warn("Circuit Breaker inventory rejected call")
                )
                .onSuccess(event ->
                    log.debug("Inventory probe/call succeeded")
                )
                .onError(event ->
                    log.warn("Inventory probe/call failed", event.getThrowable())
                );
        };
    }
}
~~~

This example illustrates observing events on the Resilience4j registry when the registry is provided by the starter in use. Verify the exact bean and API against your project's dependency versions.

Combine these signals:

- Current state of each Circuit Breaker instance.
- Timestamps of transitions to OPEN and HALF_OPEN.
- Number of calls permitted in HALF_OPEN.
- Number of rejected calls (not permitted).
- Number of requests actually sent by the HTTP client or received by the dependency.
- Latency and outcome of each probe.
- Pod/instance handling the request.

If Actuator or Micrometer is enabled, use the corresponding endpoints and metrics to inspect state alongside call counts. Expose administrative endpoints only according to your environment's security policy; never publicly expose endpoints that mutate state.

## 9. Check Configuration and Behavior via a Diagnostic Procedure

When the OPEN duration expires without seeing probes, execute these steps in order:

1. **Identify the instance:** get the exact Circuit Breaker ID from code or Gateway filter.
2. **Verify configuration:** check **waitDurationInOpenState**, **automaticTransitionFromOpenToHalfOpenEnabled**, and **permittedNumberOfCallsInHalfOpenState** for that exact instance.
3. **Inspect state per pod:** determine which pods are OPEN, HALF_OPEN, or CLOSED.
4. **Compare timestamps:** confirm when OPEN started and the actual elapsed wait time, not merely deployment time or when you looked at the dashboard.
5. **Check traffic:** confirm new requests passed through the right route/service after the wait duration expired.
6. **Check filters and caches:** confirm requests are not handled by another layer before the Circuit Breaker.
7. **Check probe permits:** verify how many probes were permitted and whether any probe is currently in-flight.
8. **Check administrative state:** rule out FORCED_OPEN or an administrative mechanism holding the state.
9. **Check outcomes:** see whether the dependency returns success, error, or timeout; cross-check with thresholds and exception policies.
10. **Verify metrics:** distinguish state transitions from requests actually dispatched to the dependency.

If **automaticTransitionFromOpenToHalfOpenEnabled** is **false** and there is no traffic after the wait duration, not seeing HALF_OPEN yet can be expected behavior. If it is **true** and the state is already HALF_OPEN without HTTP requests appearing, check traffic and request routing; the scheduler does not generate requests.

## 10. Controlled Testing for Missing Probes

You can write an integration test with a short OPEN duration to verify both modes. Do not use long wait times in tests or rely on production traffic.

### Case A: Automatic Transition Disabled

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 500ms
        automaticTransitionFromOpenToHalfOpenEnabled: false
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trigger enough errors to transition the breaker to OPEN. Wait past 500 ms without sending a new request. The state may still report OPEN. Send a subsequent request through the exact same instance; at that point the breaker checks elapsed time and permits the HALF_OPEN flow.

### Case B: Automatic Transition Enabled

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 500ms
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trigger enough errors to open the circuit, then wait past 500 ms. The state can transition to HALF_OPEN automatically even with no requests. However, the dependency call count remains 0 until the test sends a request through the breaker.

In both cases, send successful probes to verify the state returns to CLOSED per policy. Send failed probes to verify the breaker transitions back to OPEN. Use assertions with timeouts or bounded polling to wait for state transitions; do not use a single long sleep and do not assert solely via logs.

## 11. Caution When Using Active Health Checks

If the business requires the system to probe a dependency even when there is no user traffic, implement a dedicated health checker instead of expecting the Circuit Breaker to ping automatically.

A health checker should have:

- A lightweight probe endpoint representative of real serving capability.
- A bounded check interval that does not create continuous load.
- Separate timeout and concurrency limits.
- Error handling, backoff, and jitter when the dependency is unhealthy.
- Clear rules determining whether health check results are allowed to open/close the Circuit Breaker or are purely for dashboards.
- A mechanism to prevent all pods from pinging the dependency simultaneously upon recovery.

Do not let a health check arbitrarily invoke the same Circuit Breaker as a privileged probe without analyzing its impact on **permittedNumberOfCallsInHalfOpenState**. A health check could consume probe slots and affect real user requests. If you want a health checker to participate in state decisions, explicitly design the coordination, load limits, and outcome semantics.

For dependencies with a dedicated health endpoint, that endpoint's status does not always mean business operations work properly. A **/health** endpoint might return OK while Catalog queries or Inventory transactions still fail. Business probes should be lightweight, safe, and sufficiently representative of the operation protected by the Circuit Breaker.

## 12. Common Mistakes

1. **Assuming waitDurationInOpenState expiry sends requests automatically.** The wait period only permits state transition; the Circuit Breaker does not generate traffic.
2. **Confusing automatic transition with active health checks.** The scheduler only transitions OPEN to HALF_OPEN; it does not call the dependency.
3. **No requests arriving after the wait period ends.** Without traffic there are no real probes.
4. **Monitoring the wrong Circuit Breaker ID.** Code, Gateway filters, and Resilience4j properties use different names.
5. **Aggregating metrics across multiple pods.** Different local states make probe counts inconsistent across replicas.
6. **Overlooking the FORCED_OPEN state.** An administratively forced-open state does not follow normal OPEN wait cycles.
7. **Setting too few probes or letting probes hang.** HALF_OPEN lacks enough completed outcomes to evaluate recovery.
8. **Retries consuming multiple probe slots.** The ordering of Retry and Circuit Breaker can make attempt counts differ from logical requests.
9. **Caches or filters returning responses before the breaker.** Callers generate traffic, yet the dependency receives no calls.
10. **Running health checks too aggressively.** Pods can create a synchronized burst of load right as the backend is recovering.

## 13. Practice Scenario

A Spring Boot application has three pods calling the Inventory service. Each pod has a Circuit Breaker instance named **inventory**, configured to stay OPEN for 15 seconds and permit two probes in HALF_OPEN.

Pod **app-1** opens its Circuit Breaker at 10:00:00. Pods **app-2** and **app-3** remain CLOSED. After 15 seconds:

- If automatic transition is off, **app-1** may still display OPEN until it receives its next request.
- If automatic transition is on, **app-1**'s scheduler transitions the state to HALF_OPEN, without sending any request.
- If no traffic reaches **app-1**, the probe count stays at 0.
- If the load balancer routes a request to **app-2**, that call passes through **app-2**'s CLOSED breaker, not as a probe for **app-1**.
- When a request arrives at **app-1**, the breaker can grant one of its two probe permits.
- If probes succeed per policy, **app-1** returns to CLOSED; if they fail, it transitions back to OPEN.

During investigation, inspect per-pod dashboards rather than a single aggregated metric. Correlate state transitions with HTTP client request counts to confirm probes actually reached the dependency.

After completing the exercise, you should be able to answer:

- When did the wait duration expire?
- Is automatic transition enabled or disabled?
- What is the state of each pod?
- Did new requests pass through the right Circuit Breaker ID?
- How many probe permits were granted and what were their outcomes?
- Did any retry, cache, or filter alter the number of requests reaching the dependency?

## Conclusion

When the OPEN duration expires without visible probes, the root cause is usually that the Circuit Breaker does not generate probe requests on its own. With **automaticTransitionFromOpenToHalfOpenEnabled: false**, the state may wait for the next call before transitioning to HALF_OPEN; when set to **true**, the scheduler only transitions the state and traffic is still required for probes to execute. Verify the exact Circuit Breaker ID, configuration, request routing, and per-pod state; check permitted probe counts, retries, timeouts, and administrative states. If proactive checking is needed when no user traffic is present, design a separate health checker with bounded load and clear coordination rules.
