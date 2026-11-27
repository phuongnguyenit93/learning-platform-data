# Supported Statuses and Conversion Limits Across Registries

In Spring Cloud Service Discovery, an instance carries more than address information such as host and port. The registry also needs to represent whether the instance is active, ready to receive requests, temporarily paused from receiving traffic, or gone. These statuses affect how consumers see and select instances.

Spring Cloud Commons provides the `ServiceRegistry` abstraction with register, deregister, and status-update operations. However, this abstraction does not define a standard set of statuses that works identically across every registry. Eureka, Consul, and other implementations each have their own status models, health checks, and transition rules.

Therefore, when designing service discovery, separate the application's **desired operational status** from the **technical status** supported by the registry. When migrating from Eureka to Consul or vice versa, map by meaning and actual behavior rather than merely copying status strings.

## 1. What Does Instance Status Mean?

A service ID can have multiple instances. Each instance has its own lifecycle: starting up, registering, becoming ready for traffic, pausing, failing, and terminating. The registry needs to store enough information for consumers to determine which instances can be used.

Statuses commonly referenced in operations:

| Conceptual status | Meaning in the lifecycle |
|---|---|
| STARTING | Process is starting up and should not receive business requests yet |
| UP / HEALTHY | Instance is running and eligible for selection |
| OUT_OF_SERVICE / DRAINING | Instance still exists but should stop receiving new requests |
| DOWN / UNHEALTHY | Instance fails serving criteria |
| UNKNOWN | Status has not been determined or insufficient data exists |

These are conceptual descriptions. Not every registry supports all of these values, and their names may also differ.

Distinguish three concepts:

- **Registration:** the record indicating that a service instance exists and which endpoint it provides.
- **Availability status:** the status published by the registry or integration for the instance.
- **Health check result:** the outcome of a specific check, such as an HTTP probe succeeding or failing.

A registration can exist in the registry while a health check reports failure. Conversely, a process may be healthy yet not yet registered. Do not collapse all three concepts into a single boolean flag.

## 2. The Status Contract of ServiceRegistry

In Spring Cloud Commons, `ServiceRegistry` is the registration-side abstraction. The general contract includes the operations:

~~~java
void register(R registration);

void deregister(R registration);

void setStatus(R registration, String status);

Object getStatus(R registration);
~~~

`R` is the implementation's specific registration type. Registration holds the instance information required by the corresponding registry.

Meaning of the operations:

| Method | Role | Notes |
|---|---|---|
| `register(registration)` | Registers the instance | Creates or publishes the registration according to the backend |
| `deregister(registration)` | Deregisters the instance | Removes the record or asks the backend to stop advertising the instance |
| `setStatus(registration, status)` | Requests a status update | Status string is interpreted by the implementation |
| `getStatus(registration)` | Reads current status | Returns `Object`, not a universal portable enum |

This contract unifies how the application calls the API, without guaranteeing identical status semantics across backends.

### 2.1. Limits of String and Object Types

Two details in the API are critical:

- The `status` input is a `String`. Spring Cloud Commons does not enforce a common enum required for every implementation.
- The `getStatus()` result is an `Object`. Its actual type and interpretation depend on the registry.

Consequently, application code should not assume every registry interprets `UP`, `DOWN`, or `OUT_OF_SERVICE` identically. Casting the result to a Eureka-specific enum when the application might run against Consul introduces backend coupling and can cause runtime errors.

Before calling `setStatus()`, inspect the documentation and implementation of the exact Spring Cloud version in use. Some operations may have limited support or backend-specific behavior.

## 3. Eureka Statuses

Eureka uses its own instance status model. Common values in `InstanceInfo.InstanceStatus` include:

| Eureka status | General meaning |
|---|---|
| `UP` | Instance is active and considered ready to serve |
| `DOWN` | Instance is marked inactive |
| `STARTING` | Instance is in the startup phase |
| `OUT_OF_SERVICE` | Instance is temporarily not serving traffic |
| `UNKNOWN` | Status is undetermined |

This is Eureka's vocabulary, not a standard status list defined by Spring Cloud Commons.

Eureka Client registers the instance with Eureka Server and maintains registration via heartbeats/leases. Status can be updated from the client side and propagated to the registry via Eureka's mechanism. Health indicators and status propagation can affect the status Eureka advertises.

### 3.1. Using OUT_OF_SERVICE to Drain an Instance

A common scenario is deploying a new version or maintaining an instance. The instance still needs to stay alive briefly to finish in-flight requests, yet must not accept new requests.

With Eureka, `OUT_OF_SERVICE` is commonly used to indicate that an instance is temporarily out of service. Consumers and discovery components need appropriate status-filtering rules so they do not select that instance for new requests.

Illustrative drain flow:

1. Transition the instance to a state that rejects or avoids new traffic.
2. Update status to `OUT_OF_SERVICE` in Eureka.
3. Consumers receive updated registry data on their refresh interval.
4. Load balancers stop picking the instance once updated data takes effect.
5. In-flight requests complete.
6. The instance is deregistered and stopped.

Changing status does not automatically terminate existing HTTP connections. Graceful shutdown and connection draining must still be configured separately in the application, HTTP server, or deployment infrastructure.

### 3.2. Status May Be Affected by Health Integration

If the application uses health integration to synchronize Spring Boot health with Eureka, status may be influenced by health indicators or lifecycle events. A manual update may not stick if another health/status mechanism continues writing status updates.

Therefore, clarify which source holds final authority:

- Application explicitly calling status updates?
- Spring Boot health indicators?
- Eureka Client lifecycle?
- Configuration or deployment automation?

Avoid having multiple mechanisms update status concurrently without a clear precedence order.

## 4. Consul Statuses and Health

Consul represents service health through health checks attached to registrations. Common health check statuses are:

| Consul check status | Meaning |
|---|---|
| `passing` | Check succeeded |
| `warning` | Check raised a warning |
| `critical` | Check failed critically |

A service also has a service-level **maintenance mode**. When placed into maintenance, Consul can exclude it from standard query results depending on the API and query parameters. Maintenance is an operational Consul mechanism and should not be treated as an ordinary health check result.

### 4.1. Health Is Derived from Checks

A service can have multiple attached checks, such as:

- An HTTP check calling the application's health endpoint.
- A TCP check verifying that the port accepts connections.
- A TTL check updated by an external process.
- Other checks managed by the agent or deployment environment.

Service health in health queries is aggregated from relevant checks according to Consul's rules. If a critical check transitions to `critical`, the service may no longer appear in queries filtering only for healthy instances.

Consequently, Consul is under no obligation to interpret every status string passed via `ServiceRegistry.setStatus()` identically to Eureka. Consul's health checks and maintenance mode have their own semantics.

### 4.2. OUT_OF_SERVICE and Maintenance

Some versions of Spring Cloud Consul integrate the `OUT_OF_SERVICE` status with Consul's service maintenance mechanism. Exact handling must be verified for the implementation version in use.

Do not infer that Eureka values such as `STARTING`, `DOWN`, or `UNKNOWN` all map one-to-one into Consul. If those states must be distinguished, the application must define its own mapping, potentially using health checks, maintenance mode, or metadata depending on the goal.

## 5. Why Statuses Do Not Convert One-to-One Across Registries

Eureka and Consul solve the same service discovery problem, yet their status management models differ:

- Eureka uses an instance status enum published alongside the registration.
- Consul aggregates health check results and offers service maintenance mode.
- One registry may represent status at the instance level; another may represent check-level results aggregated at the service level.
- How consumers filter instances also depends on the query API and discovery client configuration.

The table below suggests semantic mappings rather than automatic conversions guaranteed by Spring Cloud Commons:

| Operational status | Suggested Eureka | Suggested Consul | Limitations |
|---|---|---|---|
| Starting up | `STARTING` | Not marked passing until readiness is reached | Consul has no equivalent STARTING enum in health checks |
| Ready for traffic | `UP` | Required checks are all `passing` | Requires configuring checks and querying healthy instances |
| Temporarily paused from traffic | `OUT_OF_SERVICE` | Maintenance mode | Depends on how Spring Cloud Consul implements maintenance |
| Unhealthy | `DOWN` | Check turns `critical` | `DOWN` is not a Consul health check status name |
| Undetermined | `UNKNOWN` | No check yet or check status inconclusive | No direct equivalent conversion |

Do not map Consul's `warning` to `UP` by default. A warning might still permit traffic under one policy while requiring alerts or exclusion under another. The decision depends on check severity and business requirements.

Similarly, Eureka's `DOWN` is not automatically equivalent to every Consul `critical` case. Inspect why the health check failed, instance exclusion policies, and how consumers query instances.

## 6. Common Status Transitions

Status should reflect the instance lifecycle. A simple domain model might use internal states:

- `STARTING`: process is initializing.
- `ACCEPTING_TRAFFIC`: application is ready to receive requests.
- `DRAINING`: stop accepting new requests; finish in-flight requests.
- `FAILED`: application no longer meets serving criteria.
- `STOPPED`: instance has stopped and registration should be removed.

This is an application-defined model, not a Spring Cloud enum. Adapters for Eureka or Consul translate these internal states into vocabulary supported by the backend.

### 6.1. STARTING to ACCEPTING_TRAFFIC

An instance should only be advertised as ready after:

1. The application context has initialized.
2. Configuration and mandatory dependencies are ready.
3. The server is listening on the advertised endpoint.
4. Readiness checks pass.
5. The registry/discovery integration has registered a valid endpoint.

Registering before readiness allows consumers to discover the instance while requests still fail during startup.

### 6.2. ACCEPTING_TRAFFIC to DRAINING

During deployment or maintenance:

1. Transition the instance to a state that stops receiving new requests.
2. Propagate the change to the registry per the backend's mechanism.
3. Wait for the new status to reach consumers and load balancers.
4. Complete in-flight requests within graceful shutdown limits.
5. Deregister the instance.

Wait times should account for refresh intervals, caches, maximum request duration, and connection draining. You cannot assume all consumers observe the new status immediately after `setStatus()` returns.

### 6.3. FAILED to Recovery

When an instance recovers:

1. Confirm the root cause of the failure has been resolved.
2. Verify readiness and mandatory dependencies.
3. Restore health checks to passing.
4. Clear maintenance mode or update status per the backend.
5. Confirm consumers see the instance as healthy again.
6. Monitor live requests before concluding the instance is serving reliably.

Do not flip an instance to UP solely because the process restarted. The process may be alive while the database, message broker, or critical dependencies are not yet ready.

### 6.4. Stopping an Instance

`deregister()` and `setStatus()` are two distinct operations:

- `setStatus()` alters the status of an existing registration, if supported by the implementation.
- `deregister()` requests removal of the registration or stops advertising the instance.

Setting status to `DOWN` does not necessarily remove the record. Conversely, deregister is not a health status. After a registration is removed, calling `getStatus()` on that registration may no longer be meaningful or may depend on implementation behavior.

## 7. Example Design for a Status-Mapping Layer

Avoid scattering Eureka or Consul status strings directly across business code. Express operational intent with an internal enum and centralize mapping inside an adapter.

Example internal model:

~~~java
public enum ServiceAvailability {
    STARTING,
    ACCEPTING_TRAFFIC,
    DRAINING,
    FAILED,
    STOPPED
}
~~~

An adapter interface might define:

~~~java
public interface RegistryStatusPublisher {

    void publishAvailability(
        ServiceAvailability availability
    );
}
~~~

Implementations for each backend decide how to represent it:

- The Eureka adapter maps to instance statuses supported by Eureka.
- The Consul adapter updates health checks or maintenance mode appropriately.
- Another backend may not support certain states and must return an explicit unsupported outcome.

Example mapping table kept in configuration or adapter code:

~~~text
ACCEPTING_TRAFFIC -> Eureka UP
DRAINING          -> Eureka OUT_OF_SERVICE
FAILED            -> Eureka DOWN

ACCEPTING_TRAFFIC -> Consul checks passing
DRAINING          -> Consul service maintenance
FAILED            -> Consul checks critical
~~~

This is an illustrative convention. Verify the API and behavior of the exact implementation, especially for STARTING, UNKNOWN, and how Consul health checks are updated. Do not treat the table above as built-in automatic Spring Cloud configuration.

The adapter should handle unsupported cases explicitly:

- Reject the request with a meaningful error.
- Log the unsupported status.
- Emit metrics to surface failed status transitions.
- Never silently coerce unknown statuses into UP.

## 8. Limits When Migrating from Eureka to Consul

Switching backends involves more than changing dependencies and the registry address. Re-evaluate the status model, health checks, and query behavior.

### 8.1. What Can Be Preserved

Information that maps relatively directly:

- Service ID.
- Instance ID, provided a stable naming convention exists.
- Host and port reachable from consumers.
- Non-sensitive metadata such as zone, version, or deployment group.
- Operational intent such as ready for traffic or draining.

### 8.2. What Needs to Be Redesigned

Do not copy the following verbatim:

- Eureka enum statuses into Consul check statuses.
- Heartbeat/lease intervals into Consul health check intervals.
- Eureka client health reporting into how Consul Agent executes checks.
- How consumers retrieve instance lists and filter statuses.
- Maintenance/deregistration behavior.
- Cache, refresh, and convergence timing.
- Registry read/write permissions and agent/client credentials.

### 8.3. Suggested Conversion Table

| Eureka source | Consul target | Action needed |
|---|---|---|
| `UP` | Health checks `passing` | Configure checks that verify readiness |
| `OUT_OF_SERVICE` | Maintenance mode | Verify maintenance integration in the version used |
| `DOWN` | Check `critical` | Define probes that reflect serving failures |
| `STARTING` | Not passing yet | Allow checks to pass only after the application is ready |
| `UNKNOWN` | Inconclusive | Keep unready state until reliable results arrive |

During migration, test both directions: registering new instances and removing instances. A setup that only tests successful registration without testing deregistration or maintenance easily leaves stale records in the catalog.

## 9. Limits When Migrating from Consul to Eureka

The reverse direction also requires explicit policies.

| Consul source | Suggested Eureka target | Limitations |
|---|---|---|
| Checks `passing` | `UP` | Must define which set of checks determines readiness |
| Checks `warning` | `UP` or `OUT_OF_SERVICE` per policy | Eureka has no equivalent warning status |
| Checks `critical` | `DOWN` or `OUT_OF_SERVICE` per policy | Must assess failure severity and traffic impact |
| Maintenance mode | `OUT_OF_SERVICE` | Requires explicit maintenance transition |
| No check yet | `STARTING` or `UNKNOWN` per policy | Should not be assumed UP automatically |

If Consul defines multiple checks, identify which ones are mandatory. For instance, a non-critical monitoring check might warn while the API still serves traffic; mapping every warning to DOWN could evict instances unnecessarily.

Conversely, if a database check is mandatory for business processing, a passing check on a trivial HTTP endpoint may not suffice to prove the service is ready.

## 10. Constraints to Check Before Calling setStatus()

Before calling `ServiceRegistry.setStatus()`, confirm:

1. Whether the injected implementation is Eureka, Consul, or another backend.
2. Whether the registration object has the exact type required by that implementation.
3. Whether the status string is supported and whether it is case-sensitive.
4. Whether status updates are written to the registry immediately or only locally first.
5. Whether health integration might overwrite the manual status.
6. Whether consumers filter that status out of the instance list.
7. Whether LoadBalancer is serving from a stale cache.
8. Whether deregister is needed after draining, or only a status change.
9. What data type `getStatus()` returns in the current implementation.
10. Whether the backend supports the corresponding operation.

Do not infer from the shared method name that every operation shares identical semantics or completion timing across all registries.

## 11. Testing Status Transitions

Testing should verify both registry state and actual request behavior.

| Scenario | What to verify |
|---|---|
| Instance startup | Registers correct service ID, endpoint, and metadata |
| Readiness not yet met | Consumers do not select unready instances |
| Transition to drain | New requests gradually stop reaching the instance |
| In-flight requests | Active requests have enough time to finish |
| Health check fails | Registry updates status per configured threshold |
| Instance recovers | Health check passes and instance re-enters serviceable pool |
| Deregister | Registration disappears within expected timeframe |
| Registry connection lost | Consumers handle cache and refresh errors per policy |
| Eureka to Consul migration | Operational status retains intended meaning after mapping |
| Consul to Eureka migration | Warning, critical, and maintenance follow chosen rules |

Do not check only `getStatus()` immediately after `setStatus()`. Also inspect consumer-side instance query results and send test requests. The returned status value may differ from whether LoadBalancer actually selects the instance.

## 12. Observing and Troubleshooting Status Transitions

When status fails to transition as expected, check layer by layer:

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `setStatus()` throws an error | Invalid status or unsupported by implementation | Check backend vocabulary and version |
| `getStatus()` differs from value just set | Health integration or backend updated status differently | Check update sources and timing |
| Registry updated yet consumers still pick instance | Cache or refresh has not converged; status filters differ | Check instance supplier, refresh, and query semantics |
| Instance still exists after setting DOWN | Status is not deregistration | Call lifecycle deregister when registration removal is needed |
| Instance disappears too quickly | Health check or threshold too sensitive | Tune check interval, timeout, and thresholds |
| Switching registries loses status semantics | No equivalent mapping or health checks not migrated | Build explicit adapter and conversion policies |

Record service ID, instance ID, before/after status, backend, timestamp of change, and propagation outcome. Never log credentials or secrets.

## 13. Design Recommendations

- Use an internal availability model with clear operational semantics.
- Build a dedicated adapter per registry to map statuses and health.
- Use only statuses genuinely supported by the backend.
- Do not pass raw status strings interchangeably between Eureka and Consul.
- Distinguish status changes, health checks, and deregistration.
- Use readiness to determine when an instance may receive traffic.
- Use draining and graceful shutdown during deployments or maintenance.
- Verify consumer and LoadBalancer behavior after every status transition.
- Define explicit handling for unsupported, warning, and unknown statuses.
- Test transitions thoroughly before swapping registries in production.

## 14. Key Takeaways

- `ServiceRegistry` provides `register`, `deregister`, `setStatus`, and `getStatus`, yet does not standardize the full status vocabulary.
- Eureka uses instance statuses such as `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, and `UNKNOWN`.
- Consul relies on health checks with results such as `passing`, `warning`, and `critical`, alongside service-level maintenance mode.
- `OUT_OF_SERVICE` can map to maintenance in supporting Consul integrations, yet no one-to-one mapping exists for every status.
- `setStatus()` does not replace `deregister()`; health checks are not synonymous with registration either.
- Caches, refresh intervals, and health integrations can cause observed status to differ from the value just requested.
- When switching registries, rely on an operational status model and per-backend adapters.

Understanding supported statuses and conversion limits prevents Spring Cloud applications from coupling to a single registry's vocabulary. This is especially important when implementing maintenance, graceful shutdown, health checks, and migrations between Eureka and Consul.
