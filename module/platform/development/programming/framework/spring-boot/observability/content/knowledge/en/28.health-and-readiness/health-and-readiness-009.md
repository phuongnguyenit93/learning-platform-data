# Health Group

In the **Health and readiness** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a Health group allows Spring Boot Actuator to gather health indicators into separate health views tailored to operational purposes. Instead of having only one aggregated result from `/actuator/health`, an application can expose groups such as `readiness`, `liveness`, `critical-dependencies`, or `external-services`. Each group checks only the components relevant to the decision the caller needs to make.

Health groups are especially important when deploying applications on Kubernetes or similar orchestration platforms. Liveness answers whether the process needs to be restarted; readiness answers whether the instance is ready to receive traffic. These two questions are different, so you should not put every dependency into both groups. A temporarily unavailable database may cause readiness to fail, but usually does not mean the process needs a restart.

This lesson explains how to create and configure health groups, select contributors, handle status and HTTP mapping, secure health details, test statuses, and integrate with deployment probes.

## 1. Learning objectives

After this lesson, you will be able to:
1. Explain Health groups and their role in Actuator.
2. Distinguish an aggregated health group from an individual `HealthIndicator`.
3. Configure readiness/liveness groups and dedicated business groups.
4. Select contributors using include/exclude and understand group membership.
5. Customize status aggregation and HTTP status mapping.
6. Design liveness to be independent of non-essential external services.
7. Design readiness to accurately reflect traffic-receiving capability.
8. Protect health details with `show-details` and authorization.
9. Test group endpoints with healthy, degraded, and down dependencies.
10. Troubleshoot probe failures and avoid cascading restarts/traffic removal.

## 2. What is a Health group?

A `HealthIndicator` or `HealthContributor` reports the status of a component. A health group is a named set of contributors evaluated and aggregated by Actuator into a separate result.

Examples:
- `readiness`: state of readiness to receive requests.
- `liveness`: state of whether the process should continue running.
- `critical-dependencies`: dependencies essential to the request path.
- `external-services`: external services to monitor that do not necessarily dictate readiness.
- `startup`: state indicating completion of required initialization steps.

A single contributor can appear in multiple groups. For example, a database may belong to `readiness` if all requests need the database, yet it should not automatically belong to `liveness`.

A health group does not create a new health check per member. It organizes and aggregates results from existing `HealthContributor`s.

## 3. Default endpoint and named groups

Default aggregated endpoint:

~~~http
GET /actuator/health
~~~

When health probes are enabled, Spring Boot can provide groups dedicated to liveness and readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

The corresponding endpoints typically take the form:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Custom named groups can be defined via configuration:

~~~yaml
management:
  endpoint:
    health:
      group:
        critical:
          include: db,redis
        external:
          include: search,partnerApi
~~~

They can then be accessed at:

~~~http
GET /actuator/health/critical
GET /actuator/health/external
~~~

Group names must be stable and must not collide with endpoint/contributor names. The actual configuration requires matching registered contributors. If a name in `include` does not exist or is misspelled, the group may not behave as expected; check startup/configuration logs.

## 4. Include and exclude contributors

Groups are typically configured using `include` and `exclude`.

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
        external:
          include: search,partnerApi
          exclude: diskSpace
~~~

`include` specifies which contributors are included in the group. `exclude` removes contributors from the group by contributor name. Verify exact bean/indicator names and canonical names used by Actuator in the application.

A few notes:
- Do not assume every contributor automatically belongs to every custom group.
- Verify group membership via health details responses in authorized environments.
- When using a custom `HealthContributor`, give the bean a clear and stable name.
- Avoid creating too many groups just to duplicate the same list of indicators.
- Each group should serve a concrete operational decision.

## 5. Liveness and readiness serve different purposes

| Group | Question | Suitable components |
| --- | --- | --- |
| Liveness | Is the process alive and able to continue running? | `livenessState` and internal signals showing an unrecoverable process. |
| Readiness | Can the instance accept new traffic? | `readinessState`, database, or mandatory dependencies per architecture. |
| Critical dependencies | Are core dependencies operating? | Database, cache, essential broker. |
| External services | Are external services responding? | Search, partner API, payment provider. |

Do not put a database or remote API into liveness merely because it is business-critical. If a dependency outage causes liveness to fail, the platform can continuously restart all replicas without fixing the external cause.

Readiness can depend on the database if the request path cannot function when the database is unavailable. However, consider degraded modes, caching, queueing, and replica counts. If all instances fail readiness together during a database outage, the service will be completely pulled from traffic; that may be the right decision or may worsen the incident depending on the architecture.

## 6. Automatically adding readiness/liveness state

Spring Boot provides application availability states and corresponding health indicators when probes are enabled.

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

`livenessState` reflects the application's liveness state; `readinessState` reflects its readiness state. Spring Boot and the application lifecycle can transition these states during startup/shutdown.

Applications can also control availability states when needed:

~~~java
@Component
class WarmupRunner implements ApplicationRunner {

    private final ApplicationAvailability availability;

    WarmupRunner(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        // Perform necessary warm-up before marking ready.
        // Spring Boot manages the availability lifecycle; only change state
        // manually when the application genuinely owns that decision.
    }
}
~~~

This snippet illustrates accessing `ApplicationAvailability`. In practice, use `AvailabilityChangeEvent.publish(...)` with `ReadinessState.ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC` when the application needs explicit readiness control; do not change state solely on transient dependency failures.

## 7. Custom HealthIndicator inside a group

You can write a `HealthIndicator` for a specific dependency:

~~~java
@Component("partnerApi")
class PartnerApiHealthIndicator implements HealthIndicator {

    private final PartnerClient client;

    PartnerApiHealthIndicator(PartnerClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.ping();
            return Health.up()
                    .withDetail("dependency", "partner-api")
                    .build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "partner-api")
                    .withDetail("error", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

The bean name `partnerApi` can be used in group `include` configuration. Do not put exception messages, URLs, credentials, or response bodies into details.

Health checks should:
- Have short, clearly bounded timeouts.
- Perform lightweight operations; do not run heavy queries or full scans.
- Produce no side effects.
- Avoid calling numerous downstream dependencies too frequently.
- Classify UP, DOWN, or another status appropriately per policy.
- Avoid creating cascading load when a dependency is experiencing issues.

If a health check shares a connection pool with business traffic, avoid adding noticeable load when the system is already saturated. You can use a lightweight ping or cached health signal depending on freshness needs.

## 8. Status aggregation and HTTP status mapping

A health group aggregates statuses from its members. Spring Boot has a default status aggregator, though applications can customize severity order or HTTP mapping.

~~~yaml
management:
  endpoint:
    health:
      status:
        order: DOWN,OUT_OF_SERVICE,UNKNOWN,UP
        http-mapping:
          down: 503
          out-of-service: 503
      group:
        readiness:
          status:
            order: DOWN,OUT_OF_SERVICE,UNKNOWN,UP
~~~

Status severity and HTTP response code are related yet distinct concepts:
- The status aggregator picks the aggregated status from contributors.
- The HTTP mapper converts that status into a response code.

For example, readiness DOWN is usually mapped to HTTP 503 so the platform removes the instance from traffic. Do not change status order arbitrarily because it can alter aggregated outcomes. Verify the actual group endpoint response after configuring.

A custom status such as `DEGRADED` needs explicit definition and mapping if used by the application. Otherwise, the platform may treat the status as UNKNOWN or HTTP 200 depending on mapping, causing unexpected probe behavior.

## 9. Health details and security

Health endpoints can return details about databases, brokers, dependency names, hosts, or system state. Configure visibility level:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Common options depending on version include `never`, `when-authorized`, and `always`. In production, avoid `always` if the endpoint can be reached by untrusted callers.

Distinguish between:
- Minimal health status for probes.
- Component status so operators know which component is DOWN.
- Details that may contain internal info requiring an authorized role.

Spring Security can restrict permissions to read details and management endpoints. Network policies should also block public access if the management interface is not meant for the internet.

Do not return passwords, connection strings, tokens, full exception messages, or raw responses from dependencies in Health details. Only return filtered categories/error types.

## 10. Health groups and deployment probes

Kubernetes can use readiness/liveness endpoints as HTTP probes. Conceptual configuration example:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

These parameters are illustrative. Port/path must match the server or management server configuration. If Actuator runs on a separate management port, probes must target that port.

A failing readiness probe marks the instance unready once the control plane updates endpoints. A failing liveness probe can restart the container. Therefore, the two probes should not share the same group out of convenience.

If an app starts slowly, use a startup probe to give the process enough initialization time before liveness begins. Do not use liveness to check slow dependencies or temporarily unavailable remote services.

## 11. Group-specific endpoints and exposure

Custom health groups can have dedicated endpoints, yet web exposure and security must still be considered. With default health endpoint exposure, groups are usually accessible under `/actuator/health/{group}` once created.

Do not expose all Actuator endpoints just so probes can call a health group. Expose only health and configure appropriate details. Check the management base path, port, address, and security matchers.

If a custom group needs a different HTTP status from aggregate health, configure group-specific status mapping as supported by your version and test the response. Do not assume group configuration automatically alters global health status.

## 12. Metrics and logs complementing health groups

A health group is a status snapshot at the moment it is called; it does not replace historical metrics or alerting.

Combine:
- Health group: can the instance receive traffic?
- Metrics: how are dependency error rate, latency, pool saturation, and request volume changing?
- Logs: what specific error caused the health indicator to fail?
- Traces: which request/dependency path is slow or failing?

Do not create metric tags from raw health details or dependency error messages. If you need to count health check failures, use counters with finite tags such as dependency name and outcome.

~~~java
log.atWarn()
        .addKeyValue("event.name", "health.check.failed")
        .addKeyValue("dependency", "partner-api")
        .addKeyValue("outcome", "down")
        .log("Dependency health check failed");
~~~

Logs should only record necessary categories. Do not log full exceptions or response bodies if they might contain sensitive data.

## 13. Testing Health groups

Use Spring Boot tests to verify group membership, status aggregation, and HTTP mapping. Mock dependencies to control state:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ReadinessHealthGroupTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    PartnerClient partnerClient;

    @Test
    void readinessDoesNotDependOnOptionalPartner() throws Exception {
        when(partnerClient.ping()).thenThrow(new RuntimeException());

        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

This test assumes `partnerApi` is not in the readiness group. In newer Spring Boot versions, the mock annotation may shift to `@MockitoBean`; use the test API matching your project's version.

Required tests:
1. All contributors UP -> group UP.
2. Mandatory contributor DOWN -> group DOWN.
3. Optional contributor DOWN does not fail readiness if excluded from the group.
4. `exclude` properly removes a contributor.
5. Custom statuses have accurate HTTP mapping.
6. Health details are hidden from anonymous callers.
7. Readiness/liveness endpoints exist when probes are enabled.
8. Startup state does not report ready before necessary warm-up.
9. Indicator timeouts do not hang health requests indefinitely.

Do not use `Thread.sleep` to wait for health transitions if you can control availability state or mock lifecycle events directly.

## 14. Troubleshooting

| Symptom | Possible cause | Investigation step |
| --- | --- | --- |
| `/actuator/health/readiness` returns 404 | Probes not enabled or group endpoint not created. | Check `management.endpoint.health.probes.enabled` and version. |
| Custom group returns UNKNOWN | `include` points to non-existent contributor or unmapped status. | Check bean names and response components. |
| Readiness DOWN even though API still works | Group includes optional dependency or check is too strict. | Review group membership and degraded mode. |
| Liveness DOWN during database outage | Database mistakenly added to liveness group. | Use only process/lifecycle health for liveness. |
| Probe fails with 404/503 | Incorrect path, port, HTTP mapping, or exposure. | Check probe config and actual response. |
| Health details not shown | `show-details` policy requires authorization. | Check caller roles and security configuration. |
| Health requests create high load | Indicator runs heavy queries or calls many remote services. | Use timeouts, lightweight pings, or cached state. |
| One contributor fails the group | Status aggregation prioritizes that contributor's severity. | Identify the member and status order. |
| All replicas removed from service | Readiness depends on an outaged shared dependency. | Review readiness policy, capacity, and degraded mode. |
| Startup probe/liveness restart loop | Startup incomplete yet liveness already started. | Configure startup probe and startup lifecycle properly. |

## 15. Runbook: readiness group reports DOWN

1. Call `/actuator/health/readiness` from a network context similar to the platform probe.
2. Confirm the HTTP status and health status in the response.
3. If details are hidden, query using an authorized operator identity.
4. Identify which contributor caused the group to go DOWN.
5. Inspect group `include`/`exclude` and corresponding bean names.
6. Correlate dependency latency/error metrics and logs.
7. Check health indicator timeouts and probe-induced load.
8. Determine whether that dependency is genuinely mandatory for the request path.
9. If optional, fix group membership through a tested change; do not mask errors by forcing status UP.
10. Check the number of remaining ready replicas and service capacity.
11. After the dependency recovers, verify readiness transitions back to UP.
12. Document the root cause and update health policy/runbooks if needed.

## 16. Self-check exercises

### Exercise 1 — Database outage

The database is unavailable for 2 minutes. Should the database be placed in both readiness and liveness?

**Answer:** Usually do not put it in liveness. Readiness can include the database if every request requires the DB; liveness should focus on process/lifecycle to avoid restart loops from external outages.

### Exercise 2 — Optional dependency

The search service is temporarily failing, but the application has a fallback cache. Should the search indicator fail readiness?

**Answer:** Not necessarily. If the service still fulfills requests in degraded mode, search can belong to a separate `external` group; readiness should reflect actual ability to receive traffic.

### Exercise 3 — Custom group UNKNOWN

The `critical` group returns UNKNOWN. What should be checked?

**Answer:** Check contributor names in `include`/`exclude`, registered `HealthContributor` beans, and status aggregation/mapping.

### Exercise 4 — Readiness DOWN and HTTP 200

Group status is DOWN yet the HTTP response is 200. What could be wrong?

**Answer:** HTTP status mapping has not mapped DOWN to 503 or custom group mapping differs. Check status order and `http-mapping` for the group.

### Exercise 5 — Liveness restart loop

Pods restart continuously when the partner API is unavailable. What is the common cause?

**Answer:** An external dependency was placed in the liveness group. Liveness failures cause the orchestrator to restart the process even though the process is not broken.

### Exercise 6 — Probe causing overload

Each readiness check runs a heavy reporting query and is called every few seconds. How do you fix it?

**Answer:** Replace it with a lightweight check with a timeout, cached health state, or signals from the client/pool. Health probes should not add load when the system is already overloaded.

## 17. Implementation checklist

- [ ] Each Health group has a specific operational purpose.
- [ ] Readiness and liveness are designed separately.
- [ ] Liveness does not depend on non-essential remote dependencies.
- [ ] Readiness only includes dependencies genuinely required to accept traffic.
- [ ] Custom group `include`/`exclude` use exact contributor names.
- [ ] Custom `HealthIndicator`s have timeouts, are lightweight, and have no side effects.
- [ ] Status aggregation and HTTP status mapping are tested.
- [ ] Health details are protected via `show-details` and authorization.
- [ ] Probe port/path match the management/application server.
- [ ] A startup probe is used if warm-up duration is long.
- [ ] Metrics/logs supplement health status without creating high cardinality.
- [ ] No secrets, connection strings, or raw exception messages are returned in details.
- [ ] Integration tests cover healthy, degraded, down, and timeout cases.
- [ ] A runbook exists to identify which contributor caused readiness failure.
- [ ] A capacity/degraded-mode plan exists for shared dependency outages.
- [ ] Health groups are reviewed whenever dependencies are added or request paths change.

**Key takeaways:** A Health group gathers `HealthContributor`s around a specific operational decision. Readiness decides whether an instance accepts traffic; liveness decides whether the process needs restarting. Select members via `include`/`exclude`, use lightweight health checks with timeouts, protect details, and test status/HTTP mapping. Combine health groups with metrics, logs, and traces to understand root causes rather than staring at a single UP/DOWN state.
