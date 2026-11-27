# Securing Management Endpoints and Configuration Change Permissions

Circuit Breakers can be observed and intervened upon during operations: on-call engineers can view state, inspect metrics, force a circuit into `FORCED_OPEN` to stop calling a dependency, or reset a circuit once an incident has been resolved. These actions directly affect production traffic. If management endpoints are left public or granted overly broad permissions, unauthorized actors could disrupt service, reopen traffic before a dependency has recovered, or alter protection thresholds in ways that leave the system vulnerable to cascading failures.

With Spring Cloud CircuitBreaker and Resilience4j, separate three permissions: **observation**, **runtime state control**, and **policy configuration changes**. Each permission has its own scope, approval workflow, and auditing model. Actuator is well-suited for exposing selected health and metrics data; state or policy mutations should go through an internal administrative interface with clear authentication, authorization, and auditing.

## Distinguishing Observation, Control, and Configuration Endpoints

| Category | Example Actions | Risk | Recommended Permission |
|---|---|---|---|
| Observation | Read health, metrics, Circuit Breaker state | Exposing internal details or dependency status | `circuitbreaker.read` or read-only operations role |
| Runtime control | Force `FORCED_OPEN`, reset circuit | Immediately halting or reopening traffic | `circuitbreaker.write` with audit and change reason |
| Policy change | Modify failure threshold, sliding window, timeout, probe count | Alters protection behavior across many requests or replicas | Configuration management permission, review, and rollout workflow |

Do not collapse all three categories into a single endpoint accepting arbitrary JSON. Someone who only needs to view dashboards should not have permission to reset circuits; someone authorized to force-open a dependency during an incident does not necessarily need permission to alter system-wide base configuration.

## Expose Only Necessary Actuator Endpoints

Spring Boot Actuator provides operational endpoints such as `health`, `metrics`, and `prometheus`. Expose only the endpoints needed by your observability platform. Do not expose all management endpoints on public networks, especially endpoints that can reveal configuration, environment variables, bean graphs, or internal metadata.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

`show-details: when-authorized` restricts detailed health information to users with an appropriate role. Liveness/readiness health endpoints may need to be reachable by the orchestration platform; permit only the exact probe paths required. `metrics` and `prometheus` endpoints should normally stay on the internal observability network or require read authorization, since meter names and tags can reveal dependency names, topology, or system state.

If using a separate `management.server.port`, configure security on the management port and restrict it with network policies/firewalls. Separating ports does not create security by itself; if that port remains reachable from the Internet or user networks, endpoints still require authentication and authorization.

## Authentication and Authorization with Spring Security

For internal management APIs, OAuth2 Resource Server with scope-based authorization works well. The following example allows health probes to read the liveness/readiness paths, requires an operations role to read remaining Actuator endpoints, and requires a dedicated scope to invoke the Circuit Breaker state-change API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/actuator/health/liveness",
                    "/actuator/health/readiness").permitAll()
                .requestMatchers("/actuator/**")
                    .hasRole("OPS")
                .requestMatchers("/internal/admin/circuit-breakers/**")
                    .hasAuthority("SCOPE_circuitbreaker.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

This is an illustrative policy for an application using JWT bearer tokens. JWT claims must map to `ROLE_OPS` for protected Actuator endpoints and the appropriate scope for the management API. If a separate snapshot-read endpoint is needed, grant `SCOPE_circuitbreaker.read` to GET routes and reserve `SCOPE_circuitbreaker.write` for state-mutating POST routes. Do not use a single broad scope like `admin` for everything when finer-grained permissions are possible.

In systems using session cookies for a browser-based admin UI, keep CSRF protection enabled for state-mutating actions. For APIs accepting only bearer tokens without relying on browser cookies, CSRF requirements may differ; decide based on the actual authentication mechanism instead of disabling CSRF globally by reflex.

## Separating Read Endpoints from State-Mutating Endpoints

Read endpoints should return DTOs containing only the fields needed for operations: Circuit Breaker name, state, sample count, failure rate, slow-call rate, and rejected call count. Do not return raw Resilience4j objects, full internal configuration, unfiltered exception messages, or authentication details.

State-mutating endpoints should use HTTP `POST` with explicitly defined actions such as `force-open` or `reset`. Never use `GET` to change state. Require a change/ticket ID and an action reason to link back to incident or change management systems.

Example controller illustrating two runtime actions:

```java
import java.security.Principal;
import java.util.Set;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/admin/circuit-breakers")
class CircuitBreakerAdminController {

    private static final Set<String> MANAGED_NAMES = Set.of("catalog", "inventory");

    private final CircuitBreakerRegistry registry;
    private final CircuitBreakerAuditService auditService;

    CircuitBreakerAdminController(
            CircuitBreakerRegistry registry,
            CircuitBreakerAuditService auditService) {
        this.registry = registry;
        this.auditService = auditService;
    }

    @PostMapping("/{name}/force-open")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker.write')")
    AdminActionResult forceOpen(
            @PathVariable String name,
            @RequestHeader("X-Change-Id") String changeId,
            @RequestHeader("X-Change-Reason") String reason,
            Principal principal) {
        CircuitBreaker breaker = requireManagedBreaker(name);
        String before = breaker.getState().name();

        auditService.recordRequested(
            principal.getName(), changeId, reason,
            name, before, "FORCE_OPEN");
        breaker.transitionToForcedOpenState();

        auditService.recordCompleted(
            principal.getName(), changeId, reason,
            name, before, breaker.getState().name(), "FORCE_OPEN");

        return new AdminActionResult(name, before,
            breaker.getState().name(), "FORCE_OPEN");
    }

    @PostMapping("/{name}/reset")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker.write')")
    AdminActionResult reset(
            @PathVariable String name,
            @RequestHeader("X-Change-Id") String changeId,
            @RequestHeader("X-Change-Reason") String reason,
            Principal principal) {
        CircuitBreaker breaker = requireManagedBreaker(name);
        String before = breaker.getState().name();

        auditService.recordRequested(
            principal.getName(), changeId, reason,
            name, before, "RESET");
        breaker.reset();

        auditService.recordCompleted(
            principal.getName(), changeId, reason,
            name, before, breaker.getState().name(), "RESET");

        return new AdminActionResult(name, before,
            breaker.getState().name(), "RESET");
    }

    private CircuitBreaker requireManagedBreaker(String name) {
        if (!MANAGED_NAMES.contains(name)) {
            throw new IllegalArgumentException("Unmanaged Circuit Breaker: " + name);
        }

        return registry.getAllCircuitBreakers().stream()
            .filter(candidate -> candidate.getName().equals(name))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Circuit Breaker not found: " + name));
    }
}

record AdminActionResult(
    String name,
    String previousState,
    String currentState,
    String action
) {}
```

`CircuitBreakerAuditService` is the application adapter that persists audit entries to durable storage; `AdminActionResult` is the DTO returned to the caller. In production code, validate that `changeId` and `reason` are non-empty, enforce length limits, validate format, and handle audit-write failures. If auditing is mandatory under organizational policy, do not report the operation as successful before the audit event has been durably written.

The two audit methods in the example separate intent and completion records: `recordRequested(...)` must durably persist intent before mutating state; `recordCompleted(...)` records the post-action state. If an operation fails between the two steps, the remaining request record alerts operations to an unconfirmed action for further investigation.

The example uses an allowlist of breaker names so callers cannot create or control arbitrary Circuit Breakers. `getAllCircuitBreakers()` is used to look up an existing instance; avoid calling `registry.circuitBreaker(name)` inside an administrative endpoint just for lookup, since that call can create a new instance if the name does not yet exist.

The registry injected into the controller must be the exact registry used by the application's backend/factory. If the controller reads a different registry, it may manipulate an instance that receives no production traffic. Verify backend wiring and share the same registry source across both the factory and the management adapter.

## Understanding the Impact of force-open and reset

`transitionToForcedOpenState()` forces the circuit into `FORCED_OPEN`; new calls are rejected until another state-transition action is taken. This is an operational measure to stop traffic to a dependency during urgent isolation. It does not fix the dependency and does not prove recovery.

`reset()` returns the Circuit Breaker to its initial state and clears runtime statistics for the instance. As a result, reset can immediately let traffic resume while the sliding window has no fresh samples yet. If the dependency is still failing, the circuit must gather enough new samples before tripping again by threshold; during that interval, the system may send additional failing requests.

Do not reset simply because a dashboard stopped alerting or because time has elapsed. Before resetting, verify the dependency with a canary or suitable health check, inspect latency and error rates, confirm connection pools and downstream components have stabilized, and reopen traffic according to plan. If you only need to exit `FORCED_OPEN`, choose the state transition appropriate for your Resilience4j version and understand its effect on metrics; do not assume every transition back to `CLOSED` is identical to `reset()`.

## A Management Operation Only Affects the Receiving Replica

Resilience4j stores Circuit Breaker state in process memory. If a management API is called through a load balancer and the request lands on replica A, the `force-open` or `reset` operation in the example affects only the instance on replica A. Replicas B and C hold separate state and do not automatically receive that change.

This must be reflected clearly in both the API and operational procedures:

- Return the instance/pod identity alongside the modified Circuit Breaker name.
- If the target is the whole deployment, the management plane must fan out to every identified replica and collect individual results; never send one request through a load balancer and treat it as a cluster-wide action.
- Watch newly started replicas or replicas scaled out during an incident; they may start with `CLOSED` Circuit Breakers.
- If cluster-wide traffic blocking is needed immediately, consider cluster-scoped gateways, service meshes, routing policies, or admission controls rather than relying on local state.
- When fanning out, bound concurrency, set per-replica timeouts, and record unresponsive replicas; avoid creating a burst of concurrent admin calls that overwhelms the control plane.

Do not assume aggregated metrics in Prometheus mean runtime state is synchronized. Observability systems can aggregate counts across replicas while each Circuit Breaker still makes independent decisions.

## Controlled Policy Configuration Changes

Properties such as `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold`, `waitDurationInOpenState`, and `permittedNumberOfCallsInHalfOpenState` are protection policies. Changing them can make the circuit open sooner, open later, permit more probes, or block traffic for longer.

For configuration declared in `application.yml`, a safe workflow is:

1. Modify configuration in the repository or managed configuration source.
2. Review new values, instance scope, traffic impact, and rollback capability.
3. Validate syntax, valid value ranges, and version compatibility before deploying.
4. Perform a controlled rollout, preferring a canary or small replica subset first.
5. Monitor state, failure rate, slow-call rate, not-permitted calls, retries, and fallbacks after the change.
6. If results worsen, roll back to a known-safe configuration version and verify replicas reapplied it.

Do not assume editing a YAML file or calling an arbitrary refresh endpoint updates the configuration of existing Circuit Breaker objects. `CircuitBreakerConfig` is applied when an instance is created; refresh and instance-recreation behavior depends on version, Spring Cloud Config mechanisms, and how the factory/registry is wired. Explicitly test reload behavior in staging. Without a verified dynamic reconfiguration mechanism, a controlled rolling restart is a more predictable way to apply new configuration.

If a product genuinely needs a runtime threshold-tuning UI, do not accept an arbitrary raw configuration object directly. Define a DTO with an allowlisted set of fields, min/max bounds, strict types, configuration version, requester, change ID, and effective duration. After validation, update the authoritative configuration source, apply the change to the intended instances/replicas via a tested mechanism, verify effective configuration, and support rollback. Modifying an in-memory object without updating a durable configuration source means changes disappear on restart and replicas can drift onto different policies.

## Configuration Change Permissions and Least Privilege

Divide operational roles according to real responsibilities:

| Role | Appropriate Permissions | Example |
|---|---|---|
| Observer | Read dashboards, health, and exposed metrics | View that `catalog` circuit is `OPEN` |
| On-call operator | Execute approved runtime actions | Force-open a circuit to isolate a dependency |
| Configuration maintainer | Propose and review policy changes | Tune failure threshold via pull request |
| Platform administrator | Manage security, management networks, and system permissions | Grant scopes, configure management ports |

Do not grant write permissions simply because a user needs to read metrics. Use short-lived tokens, multi-factor authentication at the identity provider where appropriate, mTLS for internal workloads, and network policies to restrict where management endpoints can be called from. Do not place management endpoints behind the same public host/path without protections equivalent to other sensitive APIs.

If two-person approval is required for high-risk actions such as resetting a `FORCED_OPEN` circuit or making broad threshold changes, enforce it in the control plane or change management workflow. The service endpoint should execute only authenticated, authorized commands rather than trusting a caller-supplied `approved=true` header as proof of approval.

## Audit Logs for Every Change

At minimum, an audit event should record:

- Timestamp and identity of the executing user or workload.
- Action: `FORCE_OPEN`, `RESET`, or specific configuration change.
- Circuit Breaker name, service, environment, and target replica/pod.
- State before and after the operation.
- Before/after configuration values for policy changes.
- Validated change ID, incident ID, and reason.
- Execution outcome, any error, and correlation ID of the administrative request.

Store audit logs in durable storage with restricted write access and tamper resistance per organizational requirements. Never log bearer tokens, cookies, secrets, full request bodies, or exceptions containing sensitive data. Standard application logs are useful for debugging but do not replace an access-controlled audit trail.

## Operational Procedure When Isolating a Dependency

When a dependency is causing cascading failures and on-call engineers must intervene, follow this sequence:

1. **Observe:** inspect state, failure/slow-call rates, rejected calls, and latency per replica.
2. **Determine scope:** confirm the exact dependency, Circuit Breaker name, environment, and affected replicas.
3. **Isolate:** if calls must stop immediately, execute `FORCED_OPEN` with proper authorization and change/incident ID; for cluster-wide isolation, verify outcomes on every replica or act at a shared routing layer.
4. **Investigate:** check the dependency, client timeouts, connection pools, retries, Bulkheads, and fallback sources. Force-open only blocks new calls; it does not cancel running requests.
5. **Recover:** verify dependency health via canary and live metrics; assess latency, errors, and traffic capacity.
6. **Reopen cleanly:** reset or transition state per supported procedure, starting with a narrow scope if possible and monitoring probes/traffic.
7. **Close incident:** archive audits, document changes, outcomes, and lessons learned; roll back configuration if a new policy caused side effects.

During operations, monitor fallbacks separately. An API may continue returning cached responses while the Circuit Breaker is `OPEN`; that preserves availability but does not prove the dependency has recovered. Do not use a service's HTTP 200 rate as the sole criterion for resetting a circuit.

## Common Security and Operational Mistakes

- **Exposing all of Actuator:** leaks environment variables, configuration, or internal details. Expose only needed endpoints and protect them with scopes/network policies.
- **Using one admin permission for everything:** users who only need metrics can reset circuits. Separate read, runtime write, and config change permissions.
- **Using GET to mutate state:** risks unintended actions from caches, crawlers, or prefetchers. Use authenticated, audited POST calls.
- **Accepting arbitrary Circuit Breaker names:** can create unexpected instances or target the wrong dependency. Use an allowlist and look up existing instances.
- **Resetting immediately after wait time elapses:** the dependency may still be unhealthy; resetting resumes traffic and wipes statistics. Verify health via canary and capacity checks first.
- **Calling through a load balancer and assuming cluster-wide effect:** the action hits only the receiving replica. Identify and confirm every target.
- **Assuming config refresh always updates existing instances:** configuration may only apply at instance creation. Test reload or roll out via a verified method.
- **Omitting audit logs:** makes post-incident attribution of who changed what, when, and why impossible. Write durable audits for every write action.
- **Letting fallbacks mask failing dependencies:** dashboards show only successful responses. Track fallback rates and actual data sources returned.

## Pre-Production Checklist for Management Endpoints

| Item | Condition to Verify |
|---|---|
| Network | Management endpoints reachable only from authorized networks/workloads |
| Authentication | Uses verified identities with appropriate token/certificate lifetimes |
| Authorization | Separates read, runtime control, and config change permissions |
| Exposure | Exposes only necessary Actuator endpoints |
| API design | GET for read-only; POST for state changes; allowlisted breaker names |
| Validation | Change ID, reason, and config inputs validated/bounded |
| Audit | Records actor, target, action, before/after state, and outcome |
| Replica scope | Clearly indicates local vs. deployment-wide scope |
| Recovery | Includes canary, traffic-reopening plan, and rollback |
| Observability | Tracks state, failure/slow rates, fallbacks, and not-permitted calls |

Secure management endpoints let operations teams see accurate state, take authorized actions within their scope, and trace every change. By separating observation from control, keeping configuration changes under review workflows, and accounting for per-replica local state, Circuit Breakers can be operated proactively without turning the management interface itself into a new source of outage.
