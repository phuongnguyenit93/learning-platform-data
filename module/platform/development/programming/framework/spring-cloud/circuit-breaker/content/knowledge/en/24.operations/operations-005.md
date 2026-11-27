# Runbook for Forcing OPEN, Resetting, and Returning to Automatic Mode Safely

During operations, teams sometimes need to proactively prevent an application from continuing to call a failing dependency. For example, Inventory may be overloaded, a partner system may be timing out continuously, or a deployment may cause Payment to return widespread errors. A Circuit Breaker can transition to OPEN automatically based on failure rate and slow-call rate, but in certain incident scenarios, operators must force the circuit open immediately to shed load.

Once the root cause is resolved, the team needs to return the Circuit Breaker to automatic operation in a controlled manner. Forcing OPEN, transitioning back to standard timed OPEN, resetting to CLOSED, and observing HALF_OPEN each have different effects on traffic, state, and statistical history.

This lesson covers operational procedures with Resilience4j in a Spring Cloud CircuitBreaker application: distinguishing OPEN from FORCED_OPEN, executing administrative operations through the registry, securing control endpoints, logging audits, recovering through HALF_OPEN, and handling multi-replica deployments.

## 1. When Is Manual State Intervention Needed?

Normally, the Circuit Breaker manages its own state machine:

~~~text
                 errors or slow calls exceed threshold
          +------------------------------------------+
          |                                          v
       CLOSED ------------------------------------> OPEN
          ^                                          |
          |                                          | waitDuration expires
          |                                          v
          +---------------- success ------------- HALF_OPEN
                                                     |
                                                     | errors exceed threshold
                                                     +------> OPEN
~~~

In CLOSED, calls are permitted and outcomes are recorded in the sliding window. Once enough samples accumulate and the failure rate or slow-call rate reaches the threshold, the circuit transitions to OPEN. After waitDurationInOpenState, the circuit transitions to HALF_OPEN to probe recovery. If probe calls meet recovery criteria, the circuit returns to CLOSED; otherwise, it goes back to OPEN.

Manual intervention may be needed when:

- A dependency is causing cascading failures and must stop receiving new requests immediately.
- Operations wants to isolate a dependency while rolling back or remediating an incident.
- Planned maintenance requires stopping calls to a dependency.
- A dependency must remain isolated from traffic until the owning team confirms readiness.
- The automatic Circuit Breaker has not accumulated enough samples to trip yet, while external operational signals confirm the dependency is unsafe.

Do not force OPEN over a single isolated alert. Before intervening, identify the dependency, blast radius, fallback behavior, replica count, and the owner responsible for recovery.

## 2. Distinguishing OPEN, FORCED_OPEN, and reset

Resilience4j provides distinct operational states. Three actions often confused are transitioning to OPEN, forcing FORCED_OPEN, and resetting.

| Action | Outcome | Post-Action Behavior |
| --- | --- | --- |
| Transition to OPEN | Circuit enters standard OPEN state | The OPEN wait duration applies; afterward it can transition to HALF_OPEN as configured |
| Force FORCED_OPEN | Circuit is held in a call-rejecting state | Does not automatically transition to HALF_OPEN merely because waitDuration elapsed; requires an administrative action to leave forced-open state |
| reset() | Returns instance to CLOSED and clears instance state/statistics | Calls are permitted immediately under CLOSED rules; no preceding HALF_OPEN probe phase occurs |

Key takeaways:

- OPEN is part of the automatic state machine. It has a wait timer and can transition to HALF_OPEN.
- FORCED_OPEN is a forced-open state meant to keep a dependency isolated. It is the right choice when calls must be blocked until a deliberate operational decision is made.
- reset() is not merely "clearing errors." It returns the Circuit Breaker to its initial state and resets instance metrics. This operation can erase history that operators rely on to analyze an incident.
- Returning the circuit to CLOSED immediately can send a heavy wave of traffic back to an unrecovered dependency. For cautious recovery, leave FORCED_OPEN by transitioning to standard OPEN so HALF_OPEN probing occurs.

State-transition APIs are Resilience4j-specific. If the application uses only the Spring Cloud CircuitBreaker abstraction, that abstraction does not necessarily expose state-management operations. When manual control is needed, use the Resilience4j registry managing the exact instance used by business calls.

## 3. Preparing the Registry and Instance Names

Each Circuit Breaker is managed in the registry by name. The name used in operational actions must match the name used in configuration and business calls.

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
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      payment:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

A service may invoke the Circuit Breaker via the Spring Cloud factory:

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getInventory(sku),
    error -> InventoryResponse.unavailable(sku)
);
~~~

The name inventory is the identifier used in configuration. If an administrative action targets inventoryService while business calls use inventory, the operator may modify the wrong instance or fail to find it.

With Resilience4j Spring Boot integration, you can inject CircuitBreakerRegistry to look up an instance:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");
~~~

Do not create a second registry solely for administrative endpoints. That registry could hold a different instance than the one protecting live requests. Ensure the factory, Spring configuration, and operations layer share the application-managed registry.

If the project uses only the Spring Cloud CircuitBreaker starter, verify the auto-configuration and registry bean in your exact version. Do not cast internal factory implementations or depend on private provider classes to manipulate state.

## 4. State-Transition APIs to Know

Resilience4j CircuitBreaker provides state-management operations on each instance:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");

// Transition to standard OPEN, with recovery wait timer.
circuitBreaker.transitionToOpenState();

// Force open and hold call-rejection state.
circuitBreaker.transitionToForcedOpenState();

// Return instance to CLOSED and reset state/statistics.
circuitBreaker.reset();
~~~

Operational meaning:

- transitionToOpenState() puts the circuit into standard OPEN. After the configured wait duration, the automatic mechanism can allow HALF_OPEN.
- transitionToForcedOpenState() keeps the circuit held in forced-open state, for instance during maintenance or incident investigation.
- reset() intentionally returns the instance to CLOSED and restarts statistics. It is not equivalent to waiting for HALF_OPEN probing.

Resilience4j also offers transitions to other specialized states depending on the version. Expose only the operations your operational workflow actually requires. Before implementing, check the API of the Resilience4j version managed by your project's dependency management.

Do not use reset() as a way to "check whether the dependency is healthy yet." Resetting immediately permits new requests and can wipe out data needed for incident analysis. Use health checks, synthetic probes, or the HALF_OPEN workflow to evaluate recovery.

## 5. Building an Operations Layer with an Allowlist

Administrative endpoints must not allow callers to pass arbitrary Circuit Breaker names. Use an allowlist to restrict controllable instances and return a clear error if the name does not exist.

Example operations service class:

~~~java
package com.example.operations;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

import java.util.Set;

@Service
public class CircuitBreakerOperations {

    private static final Set<String> MANAGED_INSTANCES =
        Set.of("inventory", "payment");

    private final CircuitBreakerRegistry registry;

    public CircuitBreakerOperations(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    private CircuitBreaker requireManaged(String name) {
        if (!MANAGED_INSTANCES.contains(name)) {
            throw new IllegalArgumentException(
                "Circuit Breaker is not managed by this operations API"
            );
        }

        return registry.find(name)
            .orElseThrow(() -> new IllegalArgumentException(
                "Circuit Breaker instance does not exist: " + name
            ));
    }

    public CircuitBreaker.State forceOpen(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.transitionToForcedOpenState();
        return circuitBreaker.getState();
    }

    public CircuitBreaker.State openWithRecoveryTimer(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.transitionToOpenState();
        return circuitBreaker.getState();
    }

    public CircuitBreaker.State resumeAutomaticProbing(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);

        // Leave FORCED_OPEN via standard OPEN.
        // The Circuit Breaker will wait waitDuration, then enter HALF_OPEN automatically.
        circuitBreaker.transitionToOpenState();

        return circuitBreaker.getState();
    }

    public CircuitBreaker.State resetToClosed(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.reset();
        return circuitBreaker.getState();
    }
}
~~~

The resumeAutomaticProbing method deliberately transitions to standard OPEN instead of resetting straight to CLOSED. This lets the Circuit Breaker apply waitDurationInOpenState and then run HALF_OPEN probes as configured.

The allowlist should be maintained alongside the list of dependencies operations is permitted to control. If this list varies by configuration, load it from controlled configuration and validate it at application startup. Never use arbitrary user-supplied names to create new instances in the registry.

## 6. Designing Internal Control Endpoints

A dedicated endpoint can be provided for operations, but it must be protected by authentication and authorization. The example below illustrates controller structure; real systems must configure Spring Security, administrative networking, and auditing to organizational standards.

~~~java
package com.example.operations;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/internal/operations/circuit-breakers")
public class CircuitBreakerOperationsController {

    private final CircuitBreakerOperations operations;

    public CircuitBreakerOperationsController(
            CircuitBreakerOperations operations) {
        this.operations = operations;
    }

    @PostMapping("/{name}/force-open")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:operate')")
    public ResponseEntity<Map<String, String>> forceOpen(
            @PathVariable String name) {
        CircuitBreaker.State state = operations.forceOpen(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }

    @PostMapping("/{name}/resume-probing")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:operate')")
    public ResponseEntity<Map<String, String>> resumeProbing(
            @PathVariable String name) {
        CircuitBreaker.State state =
            operations.resumeAutomaticProbing(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }

    @PostMapping("/{name}/reset")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:reset')")
    public ResponseEntity<Map<String, String>> reset(
            @PathVariable String name) {
        CircuitBreaker.State state = operations.resetToClosed(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }
}
~~~

These endpoints must only be reachable from an administrative network or internal control plane. Scopes circuitbreaker:operate and circuitbreaker:reset are example authorities; map them from your actual identity provider and Spring Security policy.

Separate reset permissions from force-open/resume permissions because reset can send traffic back to a dependency immediately and clears metrics. For critical systems, reset may require higher privileges or approval through a change management workflow.

Never expose this endpoint on an unauthenticated public route. Never use GET to mutate state because GET can be invoked by crawlers, caches, or monitoring tools.

## 7. Auditing Every Operation

Every manual state change requires an audit trail so operators can later see who performed it, why, and on which instance.

Audit records should include:

- Circuit Breaker instance name.
- State before the operation and state after the operation.
- Action type: force-open, resume-probing, or reset.
- Actor and authentication source.
- Timestamp of the operation.
- Reason, incident ID, or change ticket.
- Target replica/pod receiving the command.
- Operation outcome and any error.

Do not write access tokens or secrets to the audit log. You can require a request DTO with reason and incidentId, for example:

~~~java
public record CircuitBreakerOperationRequest(
    String reason,
    String incidentId
) {
}
~~~

The controller should validate that reason is non-empty and record the audit entry before or immediately after executing the operation per the chosen workflow. If auditing is mandatory, do not report success when the action cannot be recorded. Define clearly how to handle temporary audit store unavailability.

Operations should be safely repeatable (idempotent) at the business level. Resending force-open for an instance already in FORCED_OPEN must not produce unexpected side effects. Before returning the response, read the current state to confirm the post-action state.

## 8. Procedure for Forcing OPEN During an Incident

When calls to a dependency must be stopped immediately, use the following procedure:

1. Identify the exact dependency and Circuit Breaker instance.
2. Confirm the incident via metrics, logs, tracing, health checks, or notification from the dependency-owning team.
3. Verify whether the fallback can serve requests and assess business impact.
4. Determine the replica scope to control.
5. Record the incident ID, reason, and responsible owner.
6. Invoke the force-open operation.
7. Re-read the state and confirm it is FORCED_OPEN.
8. Monitor rejected call counts, fallbacks, latency, and dependency load.
9. Record the next review time and recovery owner.

Example administrative request (sent only from an authenticated internal environment):

~~~bash
curl -X POST \
  -H "Authorization: Bearer <operations-access-token>" \
  "https://order-admin.internal/internal/operations/circuit-breakers/inventory/force-open"
~~~

The token in the example is a placeholder only. Never put real tokens into shell history, documentation, or logs. If the endpoint requires a request body containing reason and incidentId, supply those fields per the application's API contract.

After forcing open, new calls through that instance are rejected. Monitor fallbacks to ensure the application does not shift the failure to another dependency or return incorrect business data. Requests already permitted before the circuit was forced open may still be running; forcing open does not automatically cancel in-flight calls.

## 9. Returning to Automatic Mode via OPEN and HALF_OPEN

Once the dependency has been remediated, the cautious recovery path is moving the Circuit Breaker from FORCED_OPEN back to standard OPEN. When waitDurationInOpenState expires, the state machine can automatically transition to HALF_OPEN.

Procedure:

1. Confirm the root cause of the incident has been resolved.
2. Check dependency health and service readiness.
3. Call transitionToOpenState() to leave FORCED_OPEN.
4. Confirm the state is standard OPEN.
5. Wait for waitDurationInOpenState.
6. Watch as the Circuit Breaker transitions to HALF_OPEN.
7. Observe probe counts, success outcomes, errors, and slow-call rate.
8. If probes succeed under configured conditions, the Circuit Breaker automatically transitions to CLOSED.
9. If probes fail or exceed slow-call thresholds, the Circuit Breaker returns to OPEN.
10. Close the incident only once state and metrics stabilize.

Example configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: true
        failureRateThreshold: 50
        slowCallRateThreshold: 50
~~~

In HALF_OPEN, probe count is bounded. Do not send extra manual test traffic outside the probe budget without evaluating total load. Let the Circuit Breaker decide based on the probes it permits.

If the caller runs across multiple replicas, each local Circuit Breaker may have its own timer and HALF_OPEN transition moment. Observe each replica rather than concluding the entire system has recovered just because one instance transitioned to CLOSED.

## 10. When to Use reset()?

reset() returns the Circuit Breaker to CLOSED and resets the instance's state and statistics. After a reset, new calls can be permitted immediately and the sliding window starts accumulating fresh data.

Use reset only for a clear reason, such as:

- Clearing state and statistical history after a test exercise in a test environment.
- An operational decision to restore traffic to a dependency immediately, after confirming the dependency is healthy and accepting that HALF_OPEN will be skipped.
- Restoring an instance after configuration or operating conditions changed under a controlled procedure.

Do not reset just to make an OPEN state disappear from a dashboard. Doing so does not fix the root cause and can send requests back into a failing dependency.

Example operation:

~~~java
CircuitBreaker inventory =
    circuitBreakerRegistry.circuitBreaker("inventory");

inventory.reset();

if (inventory.getState() != CircuitBreaker.State.CLOSED) {
    throw new IllegalStateException(
        "Inventory Circuit Breaker did not return to CLOSED"
    );
}
~~~

After a reset, record explicitly in the audit log that metrics and statistical windows were cleared. Dashboards may show sample counts dropping back to zero; that is an effect of reset, not proof the dependency is healthy.

If the goal is probed recovery, use transitionToOpenState() after FORCED_OPEN to wait for HALF_OPEN instead of calling reset.

## 11. Reading State and Metrics Before and After Operations

The operations layer should expose state inspection so operators can verify before and after making changes.

Example:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.find("inventory")
        .orElseThrow();

CircuitBreaker.State state = circuitBreaker.getState();
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

int bufferedCalls = metrics.getNumberOfBufferedCalls();
int failedCalls = metrics.getNumberOfFailedCalls();
float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();
~~~

The following details can be shown in dashboards or admin pages:

| Field | Purpose |
| --- | --- |
| Instance name | Identifies the controlled dependency |
| State | CLOSED, OPEN, HALF_OPEN, or FORCED_OPEN |
| Buffered calls | Current sample count in the sliding window |
| Failed calls | Failed call count in the window |
| Failure rate | Current failure rate |
| Slow-call rate | Current slow-call rate |
| Not permitted calls | Rejected call count |
| Last operation | Most recent administrative action |
| Operator/reason | Actor and reason |

Some metrics may return a sentinel value when there are not enough samples yet to evaluate, such as an undefined failure rate. Administrative UIs should represent insufficient data clearly instead of displaying it as a confirmed 0% rate.

Actuator and Resilience4j metrics endpoints are primarily for observation. Do not assume a metrics endpoint can be used to force state unless your integration version provides an official state-writing API. Use a dedicated operations layer with controlled access.

## 12. Managing Multiple Replicas and Multiple Instances

Resilience4j Circuit Breakers normally hold local state per application process. If Order runs four replicas, each replica has its own registry and Circuit Breaker instance.

~~~text
                Operations control plane
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Pod A        Pod B        Pod C
          inventory    inventory    inventory
          FORCED_OPEN  CLOSED       FORCED_OPEN
             |           |           |
             +-----------+-----------+
                         |
                         v
                  Inventory service
~~~

If only one pod is forced open, the LoadBalancer can still route requests to other pods that remain CLOSED. Thus, acting on one replica does not isolate the dependency system-wide.

When all replicas must be controlled:

- Use a control plane or automation capable of dispatching commands to every replica.
- Collect state confirmation from each pod.
- Define clearly what policy new replicas created during the incident will receive.
- Monitor state after scale-out, restarts, or rolling deployments.
- Do not assume state is shared across pods merely because they use the same instance name.

An alternative operational approach is changing routing or configuration at the gateway/control plane to stop traffic to the dependency system-wide. That has a different scope than changing local Circuit Breaker state. Choose the control layer suited to your objective and document the exact blast radius.

## 13. Configuration, State, and Application Lifecycle

Circuit Breaker configuration and current runtime state are two separate concepts:

- YAML or Java configuration defines thresholds, windows, wait durations, and probe counts.
- The registry manages instances.
- Each instance holds runtime state and metrics.
- Force-open or reset actions affect instance state.
- Restarting the application normally recreates the registry and instances from startup configuration.

Accordingly, do not treat editing application.yml as a state reset action. Conversely, calling reset does not alter the current configuration's failureRateThreshold or slidingWindowSize.

During a rolling restart, new instances may start in CLOSED while older replicas remain FORCED_OPEN. If isolation must persist across restarts, store a durable policy in the control plane or deployment configuration and reapply it to new replicas. Do not rely on in-memory pod state to store long-lived operational decisions.

When maintenance mode must persist, manage that state in an auditable, time-bounded coordination source. At startup, the application can read the approved operational policy and apply the corresponding state.

## 14. Recovery and Rollback Plan

Every force-open operation should be paired with a recovery plan before execution.

| Phase | Condition to Confirm | Action |
| --- | --- | --- |
| Before force-open | Dependency has an incident, fallback ready, exact instance and replicas identified | Record incident, owner, and scope |
| After force-open | State is FORCED_OPEN, new requests blocked | Monitor fallbacks, rejections, and dependency load |
| Before resume | Root cause resolved, health and latency stabilizing | Prepare transition back to standard OPEN |
| HALF_OPEN | Probes within budget and outcomes observable | Let the state machine decide automatically |
| After CLOSED | Failure rate and latency stable, no error rebound | Confirm recovery and close incident |
| If probes fail | Dependency remains unstable | Let circuit return to OPEN, continue investigating, keep fallback |

If the wrong instance is reset or the circuit is returned to CLOSED too early, you can immediately force-open again and log an additional audit entry. However, do not rely on compensating actions in place of verification discipline. Check instance name, state, and replica scope before every action.

## 15. Testing the Procedure in Staging

Before using administrative endpoints in production, exercise the full lifecycle in staging:

1. Create a Circuit Breaker named inventory and send successful requests to confirm CLOSED.
2. Inject controlled failures so the Circuit Breaker automatically transitions to OPEN.
3. Wait for automatic transition to HALF_OPEN and observe probe outcomes.
4. Call the force-open endpoint while the instance is CLOSED to confirm FORCED_OPEN state.
5. Send business requests and confirm new requests are rejected or routed to fallback.
6. Wait longer than waitDurationInOpenState and confirm FORCED_OPEN persists.
7. Call resume-probing to transition back to standard OPEN.
8. Wait for HALF_OPEN and send configured probes.
9. Confirm successes return the circuit to CLOSED; inject failures to confirm it returns to OPEN.
10. Test reset in a separate scenario and confirm CLOSED state along with refreshed metrics.
11. Verify access control: callers without operations scopes receive 403.
12. Verify audit entries contain instance name, action, actor, reason, and timestamp.
13. Repeat across multiple replicas and verify every pod receives the command.
14. Restart a pod while a maintenance policy is active and verify the decision is reapplied if required by architecture.

Do not run arbitrary reset or force-open operations in production merely to test endpoints. Validate behavior in staging and maintain a rollback plan.

## 16. Common Operational Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Forced OPEN yet dependency still receives requests | Only one replica was controlled, or in-flight calls were permitted earlier | Check every replica and in-flight calls |
| Circuit transitions to HALF_OPEN even though isolation was desired | Used standard OPEN instead of FORCED_OPEN | Use transitionToForcedOpenState() when forced isolation is needed |
| Circuit stays FORCED_OPEN after wait duration | Expected behavior of forced-open state | Invoke controlled resume operation |
| Sudden traffic spike right after reset | Reset returned instance to CLOSED immediately | Use standard OPEN then HALF_OPEN when gradual recovery is needed |
| Dashboard loses history after reset | Reset cleared instance metrics/sliding window | Log audit and export pre-action metrics if needed for investigation |
| Endpoint cannot find instance | Wrong name or operations registry differs from business registry | Align names and share the same registry |
| Restart reverts circuit back to CLOSED | State lives only in instance memory | Store maintenance policy in control plane and apply at startup |
| Some pods CLOSED, some pods FORCED_OPEN | Command was sent to only a subset of replicas | Orchestrate command cluster-wide and verify each pod |
| Unauthorized user can control state | Endpoint lacks authentication or authorization | Enable Spring Security, restrict scopes, and enforce admin networking |
| Unclear who performed reset | Missing audit log or incident reference | Require logging actor, reason, timestamp, and action |

## 17. Safe Operational Principles

- Use standard OPEN when you want the state machine to wait and probe recovery automatically.
- Use FORCED_OPEN when a dependency must remain isolated until a further operational decision.
- Use reset only when you accept returning the instance to CLOSED immediately and clearing statistical history.
- Never treat reset as a health check or a way to clear alerts.
- Use the exact registry and instance name used by business calls.
- Restrict controllable instances with an allowlist.
- Protect administrative endpoints with authentication, authorization, and internal networking.
- Audit every action, including actor, reason, incident, and before/after state.
- Monitor in-flight calls, fallbacks, and rejections after forcing open.
- Manage state across all replicas; never assume Circuit Breaker state is shared cluster-wide.
- Have a resume, HALF_OPEN, rollback plan, and named owner before forcing open.
- Verify APIs and semantics against the exact Resilience4j version running.

Forcing OPEN, resetting, and returning to automatic mode are operational actions with direct traffic impact. FORCED_OPEN keeps a dependency isolated; transitioning back to standard OPEN lets the Circuit Breaker wait and then probe via HALF_OPEN; reset returns the instance to CLOSED immediately and refreshes statistics. By using the right registry, protecting administrative permissions, logging audits, and controlling every replica, operations teams can respond decisively to incidents while keeping recovery verifiable.

## References

- [Resilience4j CircuitBreaker — State transitions and configuration](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j CircuitBreaker API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreaker.html)
- [Resilience4j CircuitBreakerRegistry API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreakerRegistry.html)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
