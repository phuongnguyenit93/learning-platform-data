# Registration Status and Implementation-Supported Values

Spring Cloud Commons defines the `ServiceRegistry` abstraction so applications can register, deregister, and change the status of a service instance. However, **status is not a universal enum with identical meaning across every registry**. Eureka, Consul, and Zookeeper store status according to their own models; Kubernetes lets the platform control whether a Pod enters Service endpoints rather than having the application mutate its registration status directly.

Therefore, when calling the shared API or Actuator endpoint, do not assume every implementation accepts `UP`, `DOWN`, and `OUT_OF_SERVICE`. You need to know which implementation is running, which values it supports, how it stores status, and which component uses that status to filter instances.

This lesson belongs to the `ServiceRegistry` chapter of the `SPRING_CLOUD_CORE` module. It focuses on the `ServiceRegistry` contract, the status management endpoint, differences among Eureka, Consul, Zookeeper, and Kubernetes, and how to verify status in operations.

## 1. ServiceRegistry Is an Abstraction, Not a Universal State Machine

Spring Cloud Commons provides interfaces so applications do not depend directly on a single registry provider:

- **Registration:** represents the information of a registered instance. This is a marker interface in the shared abstraction; the concrete implementation provides data such as service ID, host, port, URI, metadata, and security mode.
- **ServiceRegistry:** provides operations to register, deregister, close the registry, and read/write the status of a `Registration`.
- **DiscoveryClient:** allows an application to query lists of services and instances without calling Eureka, Consul, or Zookeeper proprietary APIs.
- **ServiceInstance:** describes an instance returned by discovery to consumers.

`ServiceRegistry` has these primary operations:

| Operation | Purpose |
| --- | --- |
| register(registration) | Registers the instance with the registry |
| deregister(registration) | Deregisters the instance |
| setStatus(registration, status) | Requests the implementation to update status |
| getStatus(registration) | Reads status in the form provided by the implementation |
| close() | Closes or releases registry client resources if needed |

The status parameter in the shared contract is a string. Spring Cloud does not enforce a standard enum requiring every registry to support the same set of values. Commons documentation instructs applications to consult the value list in the documentation of the implementation in use.

That means:
- The same string can be interpreted differently between two registries.
- An implementation may support only two administrative statuses.
- An implementation may store status as metadata and rely on LoadBalancer to filter it.
- An implementation may not allow the application to control registration status.
- The value returned by GET may be a string, object, or custom structure depending on the implementation.

## 2. Distinguishing Registration Status, Health Status, and Process State

A service has several related yet distinct states:

| Concept | Question answered | Example |
| --- | --- | --- |
| Process state | Is the JVM/container still running? | Running, stopped |
| Application health | Are the application and dependencies operating properly? | UP, DOWN, OUT_OF_SERVICE |
| Registration status | What state does the registry consider the instance to be in? | UP or OUT_OF_SERVICE per implementation |
| Discovery visibility | Do consumers receive the instance from discovery/load balancer? | Present in list or filtered out |
| Readiness | Is the instance ready to accept new traffic? | Kubernetes Ready/NotReady |

A JVM can still be running while its registration has been set to `OUT_OF_SERVICE` to pull it out of traffic. An instance can remain registered while Consul's health check is `critical`. A Pod can remain running while its readiness probe fails, causing Kubernetes to remove the Pod from the `EndpointSlice` backing the Service.

Do not treat a single status value as complete proof of all remaining states.

## 3. The Actuator Service Registry Endpoint

Spring Cloud Commons provides an Actuator endpoint with ID `serviceregistry`. With Spring Boot's default management base path, the URLs are typically:

~~~text
GET  /actuator/serviceregistry
POST /actuator/serviceregistry
~~~

The endpoint relies on a `Registration` bean in the Spring `ApplicationContext`. GET calls `getStatus()` on the corresponding `ServiceRegistry`. POST accepts JSON containing a `status` field and forwards that value to the implementation to update.

Example taking an instance out of traffic:

~~~bash
curl -X POST http://localhost:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

Example requesting the instance return to active service:

~~~bash
curl -X POST http://localhost:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"UP"}'
~~~

Both examples apply only to implementations that support the corresponding values. Do not send the same value across all environments merely because the endpoint URL looks identical.

If a separate management port or base path is configured, the URL changes. Check Actuator links and runtime configuration.

### 3.1. Enabling Exposure and Securing the Endpoint

Example exposing the endpoint over HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - serviceregistry
~~~

Exposure only makes the endpoint reachable over the web; it does not replace authentication, authorization, or network policies.

This endpoint changes instance status in the discovery system. If unauthorized callers can POST to it, they could take a service out of traffic or put an unhealthy instance back into consideration. Therefore:
- Expose it only on the required management network.
- Protect it with Spring Security or an equivalent administrative control.
- Grant status-write permissions only to authorized operator groups.
- Log audits including instance, old/new value, caller, and timestamp.
- Never expose management endpoints to the public Internet.
- Verify results in the registry and consumers after calling it.

### 3.2. GET Response Is Not Necessarily a Simple String

Commons describes GET as reading the `Registration`'s status, but the exact data structure is decided by the implementation. Some implementations return a status string; others may return additional information such as an overridden status. Do not write administrative clients assuming a uniform response schema if your applications support multiple registries.

## 4. Auto-registration and Registration Lifecycle

In many integrations, a Spring Boot application automatically registers its instance at startup. Auto-registration is typically enabled by default when a compatible discovery implementation is present on the classpath.

Auto-registration can be disabled with:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Or configured on `@EnableDiscoveryClient` with `autoRegister=false` when Java configuration control is needed. Commons documentation also describes two events:
- `InstancePreRegisteredEvent`: published before the instance is registered.
- `InstanceRegisteredEvent`: published after registration completes.

Neither event is published when auto-registration is disabled via `spring.cloud.service-registry.auto-registration.enabled`.

Disabling auto-registration does not mean every registry supports the same manual registration mechanism. Check the specific implementation. Notably, Spring Cloud Kubernetes leaves Service/Endpoint management to Kubernetes; Commons' two auto-registration disable settings do not have the same effect in that implementation.

## 5. Eureka: UP, DOWN, OUT_OF_SERVICE, and UNKNOWN

Eureka has its own instance status model. Spring Cloud Commons documentation lists the values supported via the Service Registry endpoint as:

| Value | Operational meaning |
| --- | --- |
| UP | Instance is considered ready to serve |
| DOWN | Instance is not operating normally |
| OUT_OF_SERVICE | Instance remains registered but is taken out of traffic |
| UNKNOWN | Status cannot be determined |

Eureka also has internal states in its `InstanceInfo` model and may have initialization states such as `STARTING` depending on version/lifecycle timing. When using the common endpoint, rely on the list supported by Spring Cloud Netflix documentation for your running version; do not assume every native state is identically supported across all APIs.

### 5.1. OUT_OF_SERVICE Differs from Deregister

`OUT_OF_SERVICE` removes the instance from traffic while keeping its registration in Eureka. This is useful for blue/green deployments, maintenance, or draining an instance before stopping the process.

Deregister deletes the registration from the registry. The two operations differ:

| Action | Registration still exists? | Intent |
| --- | --- | --- |
| setStatus(OUT_OF_SERVICE) | Yes | Temporarily pull instance out of traffic |
| setStatus(UP) | Yes | Return instance to active serving state |
| deregister() | Registration removed after processing | End instance registration |

If a deployment rollback might be needed, keeping the instance in `OUT_OF_SERVICE` can make restoring traffic easier than deleting the registration completely. However, wait for the status to propagate to the registry and client caches before shutting down the instance.

### 5.2. Eureka Health Checks Are Not Enabled Automatically via Actuator

By default, Eureka uses heartbeats to determine whether a client is alive. Unless Eureka health check integration is enabled, Spring Cloud Discovery Client does not propagate Spring Boot Actuator's current health status to Eureka; after successful registration, Eureka may continue advertising the instance as `UP`.

You can enable it:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Spring Cloud Netflix documentation notes this property should be placed in `application.yml`. Placing it in `bootstrap.yml` can cause side effects, such as registering the instance with `UNKNOWN` status.

If custom rules are needed to map health to Eureka status, implement `HealthCheckHandler` per the Eureka API supported by your version.

Eureka also has initial status configuration via `eureka.instance.initial-status` (default `UP`). That sets the value at registration creation, unlike runtime status changes via `ServiceRegistry.setStatus()`. On the consumer side, `eureka.client.filter-only-up-instances` defaults to enabled so only `UP` instances are returned in certain query flows. Check effective values of both properties when an instance appears in the registry yet is not selected by LoadBalancer.

### 5.3. Status Override and Heartbeats

Eureka can maintain a server-side overridden status. This matters operationally:
- If an instance is placed in `OUT_OF_SERVICE` from the server side, normal `UP` heartbeats do not necessarily bring it back to `UP` immediately.
- Use the proper status/reset-override operations provided by the Eureka implementation.
- Check both status and overridden status when investigating discrepancies between local state and server state.
- Do not treat a single local log line as proof that all Eureka peers/clients already see the new status.

### 5.4. Verifying Eureka

After calling POST:
1. Read status via the application's Actuator endpoint.
2. Check `InstanceInfo` on Eureka Server.
3. Check that Eureka clients have received the update.
4. Check instance filtering settings, such as filtering only `UP` instances.
5. Send requests through Spring Cloud LoadBalancer to verify the instance is excluded or restored.

Do not check only Actuator's HTTP response. A successful response does not prove discovery caches across all consumers updated immediately.

## 6. Consul: UP and OUT_OF_SERVICE via Maintenance Mode

Spring Cloud Consul uses Consul's HTTP API for service registration and discovery. Service registrations can carry host, port, ID, name, tags, and metadata. Consul typically creates an HTTP health check polling the Actuator health endpoint; if the health check fails, the service instance is marked `critical`.

For `ConsulServiceRegistry`'s `setStatus` operation, the supported administrative values are:

| Value | Behavior |
| --- | --- |
| UP | Disables service maintenance mode |
| OUT_OF_SERVICE | Enables service maintenance mode |

The Consul implementation uses maintenance mode to pull a service instance out of traffic selection. Do not send `DOWN` or `UNKNOWN` via the `ServiceRegistry` endpoint expecting Consul to handle them like Eureka; those values are not in the set supported by the implementation for this operation.

### 6.1. Maintenance Mode Differs from Critical Health Checks

Consul has multiple status mechanisms:
- Maintenance mode is a state toggled by an operator/agent to mark a service under maintenance.
- HTTP health checks reflect endpoint probe results.
- TTL checks receive periodic heartbeats from the application.
- Consul check states include `passing`, `warning`, and `critical`.

A failing health check can make a service `critical` even when maintenance mode is off. Conversely, a service can be placed in maintenance to stop receiving traffic even while its health endpoint still returns `UP`.

Therefore, do not use `getStatus` from `ServiceRegistry` as an aggregate substitute for all Consul health checks. Check the Consul health API/UI and Actuator health separately.

### 6.2. TTL Application Status

With TTL heartbeats, Spring Cloud Consul can derive status from the Actuator health endpoint. If no health endpoint exists or the app is not an Actuator app, the integration may assume the application is healthy by default. You can disable using Actuator health for TTL checks or supply a custom `ApplicationStatusProvider` per version documentation.

Example TTL configuration:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        heartbeat:
          enabled: true
          ttl: 10s
          use-actuator-health: true
~~~

If using a custom health group, configure `actuator-health-group` accordingly. Ensure TTL interval, heartbeat interval, and Consul check settings align to prevent delayed heartbeats from triggering `critical` status.

### 6.3. Workflow to Pull a Consul Instance Out of Traffic

1. Identify the exact instance ID.
2. Set the instance to `OUT_OF_SERVICE` via `ServiceRegistry`.
3. Verify maintenance mode in Consul.
4. Wait for consumers/load balancers to drop the instance from eligible targets.
5. Drain in-flight requests/messages.
6. Stop or deploy the instance.
7. When ready, set it back to `UP`.
8. Verify maintenance mode is off and health checks are `passing`.

Do not delete the registration if the goal is only temporarily pulling the instance for maintenance.

## 7. Zookeeper: Status in Metadata and Filtering in LoadBalancer

Spring Cloud Zookeeper also implements `ServiceRegistry`. Because Curator Service Discovery lacks built-in Eureka-style `OUT_OF_SERVICE` behavior, Spring Cloud Zookeeper stores status in the service instance's metadata.

Documentation describes the behavior:
- Instances with status `UP` are considered active.
- Instances with a status other than `UP` and non-null are filtered out of Spring Cloud LoadBalancer's list by `ZookeeperServiceInstanceListSupplier`.
- If the status field is empty, the implementation treats it as `UP` for backward compatibility.
- You can POST `OUT_OF_SERVICE` to the Service Registry Actuator endpoint to remove the instance from LoadBalancer's active list.

Example:

~~~bash
curl -X POST http://localhost:8081/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

The exact path depends on management port/base path and endpoint version.

### 7.1. Status in Metadata Is Not a Native Curator State

The Zookeeper implementation leverages its flexible payload to store metadata status. Therefore:
- Status is metadata understood by Spring Cloud Zookeeper.
- Do not assume every Curator client or external application filters by this field.
- Spring Cloud LoadBalancer uses `ZookeeperServiceInstanceListSupplier` to filter non-`UP` instances.
- Consumers reading Zookeeper data directly or using another discovery client may need their own filtering rules.

The implementation can store a status string in metadata; however, the documented recommended values for traffic control are `UP` and `OUT_OF_SERVICE`. If using other strings, verify precisely whether all consumers and suppliers share the same rule.

### 7.2. Backward Compatibility When Metadata Has No Status

Older registrations may lack the status field. `ZookeeperServiceInstanceListSupplier` treats `null`/empty values as `UP` so legacy instances do not vanish from the list. This is backward-compatibility behavior, not a recommendation to skip status checks.

When migrating systems, inspect metadata on existing registrations and filtering behavior before enforcing new status policies.

## 8. Kubernetes: Platform Controls Registration

In Kubernetes, Services and EndpointSlices are managed by the Kubernetes control plane based on Pods, label selectors, readiness, and controllers. Applications do not register Pods into an external registry the way Eureka or Consul does.

Spring Cloud Kubernetes states clearly:
- Service registration is controlled by the Kubernetes platform.
- `spring.cloud.service-registry.auto-registration.enabled` does not alter this mechanism.
- `EnableDiscoveryClient(autoRegister=false)` also does not have the same effect as with other registry clients.

Therefore, do not use the `ServiceRegistry` Actuator endpoint as a generic way to call `setStatus` on Kubernetes.

### 8.1. Readiness Controls Traffic Reception

Kubernetes readiness probes determine whether a container/Pod is ready to receive traffic. When a Pod is not Ready, the endpoint controller can remove that Pod from the `EndpointSlice` serving the Service.

Example:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

To remove an instance from traffic in Kubernetes, you can:
- Transition the readiness probe to `NotReady` via controlled application state.
- Use a `preStop` hook and `terminationGracePeriodSeconds` for draining.
- Adjust Deployment rollouts/replicas.
- Manage Service selectors or EndpointSlices through the control plane when justified.

Do not try to change Pod readiness merely via a status string in Spring Cloud Commons' `ServiceRegistry`.

### 8.2. Health and Readiness Are Not the Same

An application can be alive yet not ready to accept requests. Kubernetes separates liveness, readiness, and startup probes. Configure appropriate health groups so:
- Liveness reflects whether the process needs restarting.
- Readiness reflects whether it can accept traffic.
- Startup probes protect slow-starting apps from premature liveness checks.

Do not fail liveness (`DOWN`) just to drain traffic; liveness failures can cause container restarts.

## 9. SimpleDiscoveryClient Is Not a Dynamic ServiceRegistry

If no `ServiceRegistry`-backed `DiscoveryClient` is on the classpath, Spring Cloud Commons can use `SimpleDiscoveryClient` with instances declared via properties. Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8080
              - uri: http://catalog-b.internal:8080
~~~

`SimpleDiscoveryClient` reads the instance list from configuration. It is not equivalent to a registry server supporting runtime `setStatus`/`deregister` operations. To change the list, modify the property source and apply the appropriate configuration refresh mechanism, or use an implementation supporting dynamic registration.

Do not expect the `serviceregistry` endpoint to work merely because `SimpleDiscoveryClient` is present.

## 10. Status Comparison Table by Implementation

| Implementation | Supported/documented admin values | How stored or applied | What consumers must note |
| --- | --- | --- | --- |
| Eureka | UP, DOWN, OUT_OF_SERVICE, UNKNOWN per Commons endpoint docs; native model may have other states per version | InstanceInfo/status and Eureka server-side override status | Eureka health check does not propagate automatically unless enabled; clients cache lists |
| Consul | UP, OUT_OF_SERVICE | UP disables maintenance; OUT_OF_SERVICE enables maintenance | Health checks passing/warning/critical are a separate mechanism |
| Zookeeper | UP, OUT_OF_SERVICE are the documented control values | Stored as status in metadata | LoadBalancer filters non-UP status; empty status is treated as UP |
| Kubernetes | No shared ServiceRegistry status operation for apps to control registration | Kubernetes control plane, Pod readiness, and EndpointSlice | Use readiness, rollouts, and draining |
| SimpleDiscoveryClient | No dynamic registry status mutation | Instance list from Environment properties | Update config or pick a dynamic registry |

This table describes common Spring Cloud integration behaviors, not a global enum list. BOM versions, discovery modules, servers, and clients can all affect specific behavior.

## 11. Manual Registration and Auto-registration

If an application needs to control registration timing itself, auto-registration can be disabled in implementations that support it:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Then code can call `ServiceRegistry.register()` or `deregister()` with a concrete `Registration`. Because the generic `Registration` type depends on the implementation, code should be written against the injected concrete registry bean.

General helper example:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public class RegistrationStatusOperations<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final R registration;

    public RegistrationStatusOperations(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public Object currentStatus() {
        return serviceRegistry.getStatus(registration);
    }

    public void changeStatus(String status) {
        serviceRegistry.setStatus(registration, status);
    }

    public void register() {
        serviceRegistry.register(registration);
    }

    public void deregister() {
        serviceRegistry.deregister(registration);
    }
}
~~~

This helper illustrates a registry bean and `Registration` of the same type. Do not use raw types to mix `EurekaRegistration` with `ConsulServiceRegistry` or `ZookeeperRegistration` with another registry.

If you only need to observe the auto-registration lifecycle, use `InstancePreRegisteredEvent` and `InstanceRegisteredEvent` instead of building a parallel registration flow. Avoid double-registering an instance via both auto-registration and manual registration.

## 12. Testing Correct Status in Both Registry and Consumer

A test that only verifies `setStatus` does not throw an exception is insufficient. Verify that status is stored, discovery returns the expected data, and the load balancer filters the instance as intended.

### 12.1. Unit Testing Control Code

You can mock `ServiceRegistry` to confirm the application passes the expected status string to the implementation:

~~~java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

@ExtendWith(MockitoExtension.class)
class RegistrationStatusOperationsTest {

    interface TestRegistration extends Registration {
    }

    @Mock
    ServiceRegistry<TestRegistration> serviceRegistry;

    @Mock
    TestRegistration registration;

    @Test
    void requestsOutOfServiceForDrain() {
        RegistrationStatusOperations<TestRegistration> operations =
                new RegistrationStatusOperations<>(serviceRegistry, registration);

        operations.changeStatus("OUT_OF_SERVICE");

        verify(serviceRegistry).setStatus(registration, "OUT_OF_SERVICE");
    }
}
~~~

This unit test checks application code. It does not prove the registry server accepted the update or consumers filtered out the instance.

### 12.2. Integration Tests per Implementation

| Implementation | Required tests |
| --- | --- |
| Eureka | Set OUT_OF_SERVICE, read InstanceInfo/server state, confirm clients do not select that instance; set UP and recheck |
| Consul | Enable maintenance, check Consul health/service state; disable maintenance and verify recovery |
| Zookeeper | Update metadata status, verify ZookeeperServiceInstanceListSupplier filters non-UP and handles empty metadata |
| Kubernetes | Transition Pod readiness to NotReady, confirm EndpointSlice/Service stops routing traffic to that Pod |
| SimpleDiscoveryClient | Update instance list config and verify discovery reads the new list once applied |

Run integration tests against the exact registry server version and Spring Cloud BOM used in production. Do not test solely with a generic mock and conclude all implementations behave identically.

### 12.3. Post-Operation Verification

After changing status, verify:
1. The Actuator endpoint accepted the request.
2. `ServiceRegistry.getStatus` returns the expected status.
3. The registry server recorded the status or metadata.
4. `DiscoveryClient` returns instances per implementation rules.
5. `LoadBalancer` selects or excludes the instance as desired.
6. Real requests stop arriving at the drained instance.
7. Upon recovery, the instance is Ready/UP and accepts traffic again.

## 13. Operating Drains, Maintenance, and Rollbacks

A drain workflow typically includes:

1. Identify the exact instance ID, avoiding accidental changes across the whole service.
2. Record current health, traffic, and in-flight requests/messages.
3. Set status to `OUT_OF_SERVICE` if supported by the implementation.
4. Wait for the registry and clients/load balancers to refresh.
5. Stop accepting new work and drain active requests/messages.
6. Confirm no new traffic reaches the instance.
7. Perform maintenance or deploy the new version.
8. Check health/readiness and dependencies.
9. Return the instance to `UP` or `Ready`.
10. Confirm consumers see the instance again.

Do not shut down the process immediately after calling POST. Eureka client caches, Consul health checks, Zookeeper watches, and LoadBalancer caches can all exhibit propagation lag. Verify state from the consumer perspective.

If a rollback may be necessary, keep the instance in a recoverable state during deployment. For Eureka/Consul, `OUT_OF_SERVICE` usually fits this goal better than deregister. For Kubernetes, use platform rollouts/replicas/readiness mechanisms.

## 14. Common Errors and Diagnostics

| Symptom | Possible cause | Check path |
| --- | --- | --- |
| POST returns unknown status error | Value unsupported by implementation | Read implementation docs and verify exact string |
| Actuator lacks serviceregistry | Missing Registration/ServiceRegistry bean or endpoint not exposed | Check dependencies, auto-configuration, and Actuator links |
| GET status returns unexpected value | getStatus reflects local/maintenance/metadata state | Compare against registry server API/UI |
| Eureka still sends traffic after OUT_OF_SERVICE | Client cache stale or consumer does not filter status | Check InstanceInfo, overridden status, and LoadBalancer |
| Eureka stays UP despite Actuator health DOWN | Eureka health check integration not enabled | Check `eureka.client.healthcheck.enabled` and `HealthCheckHandler` |
| Consul returns UP yet health check is critical | getStatus/maintenance does not aggregate all health checks | Check Consul checks and Actuator health separately |
| Consul rejects DOWN | ConsulServiceRegistry only supports UP and OUT_OF_SERVICE for setStatus | Use maintenance mode or fix health checks per goal |
| Legacy Zookeeper instance without status still selected | Null/empty status treated as UP for backward compatibility | Check metadata and migration policy |
| Raw Zookeeper client still sees OUT_OF_SERVICE instance | Filtering resides in ZookeeperServiceInstanceListSupplier | Check whether consumers use Spring Cloud LoadBalancer's supplier |
| Kubernetes does not react to setStatus | Registration controlled by platform | Use readiness, EndpointSlice, and rollouts |
| Disabling auto-registration has no effect on Kubernetes | Kubernetes integration does not control registration via Commons flag | Modify Pod/Service via Kubernetes API |
| Instance is UP yet receives no traffic | Health/readiness, cache, or network has not converged | Check registry, consumer cache, routing, and health |

### 14.1. Pinpointing the Failing Layer

When status does not behave as expected, check in order:
1. Which implementation is created in `ApplicationContext`?
2. Does the `ServiceRegistry` bean have the right implementation and `Registration` type?
3. Is the status value in the set supported by the implementation?
4. Does `setStatus` update the registry server or only local metadata?
5. Which status does `getStatus` return and where does it read from?
6. Does `DiscoveryClient` see the new status?
7. Does `LoadBalancer` filter instances based on that status?
8. Does the consumer have custom caches or policies?

Do not troubleshoot one implementation using assumptions from another implementation.

## 15. Design Principles

- Do not define an internal status enum and send it blindly to every `ServiceRegistry`.
- Introduce an application-level domain abstraction if meanings must be standardized, then map explicitly to each registry.
- Separate health, readiness, registration status, and process state.
- Use `OUT_OF_SERVICE` to drain when the implementation supports it and you need to preserve the registration.
- Only deregister when truly ending the registration lifecycle.
- Verify implementation-specific behavior before exposing the endpoint to operators.
- Protect the POST endpoint with authentication, authorization, and auditing.
- Verify both the registry server and consumers after status operations.
- Include status behavior in integration tests against the exact release train.
- On Kubernetes, control readiness/rollouts via platform APIs instead of simulating `ServiceRegistry` status.
- Document valid status sets in runbooks per deployment environment.

## Key Takeaways

`ServiceRegistry` provides a shared API for registering, deregistering, and reading/writing status, yet **the supported values and meaning of status are determined by the implementation**. Eureka provides `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN` per Commons docs; Consul uses `UP`/`OUT_OF_SERVICE` through maintenance mode; Zookeeper stores status in metadata and LoadBalancer filters non-`UP` values; Kubernetes lets the platform manage registration via readiness and EndpointSlices. Always verify status at the registry and behavior from consumers rather than relying solely on the Actuator endpoint response.

## References

- Spring Cloud Commons – Common Abstractions: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Netflix – Eureka Health Checks: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul – Service Discovery and Health Checks: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper – Service Registry and Instance Status: https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html
- Spring Cloud Kubernetes – Service Registry Implementation: https://docs.spring.io/spring-cloud-kubernetes/reference/service-registry.html
