# Reducing getServices Overhead in Health Checks with probe

Spring Cloud provides a health indicator for `DiscoveryClient` so that Actuator reflects the status of the service discovery component. The traditional check may call `getServices()` and retrieve the list of all service names in the registry. When the registry is large, this operation can consume time, allocate objects, and generate repeated load every time the health endpoint is polled.

If the goal is merely to confirm that the discovery client can still communicate with the registry, listing every service name is unnecessary. Spring Cloud Commons provides the `probe()` method on `DiscoveryClient` so the health indicator can perform a lighter-weight check. You can select this mode by configuring `use-services-query=false`, though you must understand how `probe()` is implemented by the discovery client in use: the default implementation may delegate back to `getServices()`, so changing the property alone does not guarantee reduced overhead.

This article explains how the health indicator works, when to use `probe`, how to implement a lightweight check, how to observe effectiveness, and what boundaries to preserve in your design.

## 1. Why Can getServices() Become Significant Overhead?

`DiscoveryClient` has two commonly used operations that serve different purposes:

- `getInstances(serviceId)` retrieves the instances of a specific service so consumers can route requests.
- `getServices()` lists the service names known to the registry.

A health check only wants to verify that the discovery connection is working, yet `getServices()` may have to fetch or aggregate the entire service list. Depending on the implementation, this operation may involve:

1. Calling the registry API or reading data from the client cache.
2. Fetching the list of registered applications/services.
3. Converting the response into a collection of service names.
4. Aggregating data from multiple discovery clients when using `CompositeDiscoveryClient`.
5. Allocating objects and processing data before returning to the health indicator.

For registries with many services, namespaces, or application groups, the list can be large. If the health endpoint is called continuously by orchestrators, monitoring systems, and dashboards, this cost repeats frequently.

For example, if a probe is called every 5 seconds across 20 application instances, a health indicator can be triggered hundreds of times per minute. If each call lists all service names over the network, the health check itself can put considerable load on the registry.

Not every implementation incurs such overhead. Some clients already cache the service list, or `getServices()` simply reads local memory. Measure latency, backend call counts, and allocations of the actual implementation before concluding this is a bottleneck.

## 2. What Does the DiscoveryClient Health Indicator Check?

Spring Cloud Commons integrates `DiscoveryClient` with Spring Boot Actuator. `DiscoveryClientHealthIndicator` participates in health aggregation to indicate whether the discovery client is functioning according to the check it performs.

In services-query mode, the health indicator calls `getServices()` and may include the service list in health details. This is useful when you need to verify that the client can read the service list, though it does more work than a simple connectivity check.

In probe mode, the health indicator calls the `probe()` method of `DiscoveryClient`. The intent is to give implementations an extension point to perform a cheaper check without listing all services.

Be clear on the distinction:

| Check | Question Answered | Scope |
|---|---|---|
| getServices() | Can the client retrieve the list of service names? | Queries or aggregates the service list |
| probe() | Can the discovery client perform its liveness/operability check? | Defined by the implementation |
| getInstances(serviceId) | Does the registry return instances for a specific service? | One service |
| Business health | Can the application process business operations? | Application and business dependencies |

`probe` does not implicitly check every service, every instance, or the application's database. It only checks whatever the implementation designed `probe` to check.

## 3. Switching the Health Indicator to Probe Mode

In Spring Cloud Commons, you can configure the health indicator not to use the services query:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

When this property is `false`, `DiscoveryClientHealthIndicator` uses `DiscoveryClient.probe()` instead of fetching the list via `getServices()`.

The default value of `use-services-query` is `true` in current Spring Cloud Commons releases. Therefore, if the property is omitted, the health indicator uses `getServices()`. The default value of `include-description` is `false`; enable it only when you want to include the implementation description in the health result.

You can keep the health indicator description if needed:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
          include-description: true
~~~

Property names and behavior depend on the Spring Cloud Commons version in use. Check your project's dependency management/BOM and verify that the property binds in that version. If your project uses an older release train that does not support this configuration, upgrade compatibly or build an appropriate custom health indicator; do not assume an unrecognized property will take effect on its own.

This configuration only changes how the health indicator performs its check. It does not change how consumers look up instances, does not alter service registration, and does not replace each provider's own health check.

## 4. Key Point: The Default probe May Still Call getServices()

`DiscoveryClient` defines a `probe()` method whose default implementation may call `getServices()`. This keeps older implementations compatible with the check behavior, but it also means:

**Setting `use-services-query=false` does not automatically make the check cheaper if the `DiscoveryClient` in use does not override `probe()`.**

Flow to understand:

~~~mermaid
flowchart TD
    A["Actuator health request"] --> B["DiscoveryClientHealthIndicator"]
    B --> C{"use-services-query"}
    C -->|"true"| D["getServices()"]
    C -->|"false"| E["probe()"]
    E --> F{"Does implementation override probe()?"}
    F -->|"No"| D
    F -->|"Yes"| G["Lightweight check provided by client"]
    D --> H["Health result"]
    G --> H
~~~

Before enabling probe mode, identify which implementation is actually being injected:

- Eureka `DiscoveryClient`.
- Consul `DiscoveryClient`.
- ZooKeeper `DiscoveryClient`.
- `SimpleDiscoveryClient`.
- `CompositeDiscoveryClient` or a custom discovery client.

Do not assume from the registry name that `probe` is already optimized. Inspect the source code or documentation for the exact version, or measure whether `probe` still invokes `getServices()`. If the injected bean is `CompositeDiscoveryClient` and the composite does not override `probe()`, the default `probe()` will call `getServices()` on the composite; as a result, lists from the delegates may still be aggregated.

### Examples of Built-in Client Behavior

In current Spring Cloud Netflix source code, `EurekaDiscoveryClient` implements `getServices()` but does not override `probe()`. Consequently, when the health indicator calls `probe()`, the interface's default implementation still calls `getServices()`; the property `use-services-query=false` alone does not eliminate this enumeration operation for that Eureka client.

By contrast, `ConsulDiscoveryClient` in Spring Cloud Consul overrides `probe()` and calls an operation to retrieve Consul's leader status. This is a lighter-weight check than listing all services. This behavior depends on library version; verify against the source of your deployed release train before relying on this conclusion.

## 5. Designing a Lightweight and Meaningful probe

A good probe must satisfy three criteria:

1. Check the actual capability you care about, typically whether the client can still communicate with the registry or discovery backend.
2. Have low overhead and bounded response time.
3. Fail with an error when the check genuinely fails, never returning a false success.

Example of the override in a custom `DiscoveryClient`:

~~~java
@Override
public void probe() {
    registryHealthProbe.checkConnectivity();
}
~~~

`registryHealthProbe` is an application-defined abstraction, not a built-in Spring Cloud API. It can invoke a lightweight operation supported by the registry client, such as checking connection state or performing a small metadata read request. If the operation fails, the method must throw an exception so the health indicator records an unhealthy status.

An illustrative application interface:

~~~java
public interface RegistryHealthProbe {
    void checkConnectivity();
}
~~~

The implementation must avoid calling `getServices()` inside `checkConnectivity()` if the goal is to eliminate service-listing overhead. Never create a probe that simply returns normally without checking anything, as that would cause the health indicator to stay `UP` even when the registry is unreachable.

If the registry client already maintains reliable connection state, the probe can inspect that state. If that state only reflects TCP connectivity while registry requests could still fail due to authentication or permissions, consider a lightweight read operation with a timeout to verify the required access path as well.

## 6. Distinguishing Connectivity Probes from Specific Service Checks

A probe at the `DiscoveryClient` level typically checks the operability of the discovery backend; it does not prove that a specific service has healthy instances.

For example:

- A successful Eureka probe indicates that the discovery client completed its designed check against Eureka.
- It does not prove that `inventory-service` has instances.
- Nor does it prove that each instance of `inventory-service` returns HTTP 200.
- It does not prove that the provider's database or business service is healthy.

If you need to check a specific service, you can call `getInstances(serviceId)` or use a dedicated health check for that service. However, avoid placing the list or all instances of every service inside the general probe if doing so recreates the original overhead.

One way to separate layers:

| Component | Should Check | Example |
|---|---|---|
| Discovery client | Connectivity/ability to read discovery metadata | Lightweight probe |
| Service required by application | Whether suitable instances exist | `getInstances` for a specific `serviceId` |
| Provider instance | Whether it can accept and process requests | HTTP readiness/health endpoint |
| Consumer application | Whether it has enough dependencies to receive requests | Readiness group |

Do not turn a consumer's health check into a chain of business calls across all downstream services. That can cause a health-check storm and propagate a single dependency failure into mass application restarts.

## 7. Custom DiscoveryClient Example

The following snippet illustrates the idea of a self-managed discovery client. Query and registration methods are simplified to focus on `probe`:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class InventoryRegistryDiscoveryClient implements DiscoveryClient {

    private final RegistryApi registryApi;
    private final RegistryHealthProbe healthProbe;

    public InventoryRegistryDiscoveryClient(
            RegistryApi registryApi,
            RegistryHealthProbe healthProbe) {
        this.registryApi = registryApi;
        this.healthProbe = healthProbe;
    }

    @Override
    public String description() {
        return "Inventory registry discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return registryApi.findInstances(serviceId);
    }

    @Override
    public List<String> getServices() {
        return registryApi.listServiceNames();
    }

    @Override
    public void probe() {
        healthProbe.checkConnectivity();
    }
}
~~~

`RegistryApi` and `RegistryHealthProbe` are illustrative application-defined interfaces. In a real system, you do not need to write your own `DiscoveryClient` if the Eureka, Consul, or ZooKeeper starter already provides a suitable implementation. Only create a custom adapter when you have a specific requirement and understand how Spring selects the `DiscoveryClient` bean.

The probe must have a timeout. If the registry check request can hang for a long time, the Actuator endpoint can slow down as well. Set a timeout shorter than the orchestrator's health check time budget, yet long enough to tolerate normal network latency.

## 8. When Using Multiple DiscoveryClients

An application may have multiple `DiscoveryClient` instances, for example one client for a primary registry and another for secondary discovery. Spring Cloud can aggregate them through `CompositeDiscoveryClient`.

In this case, determine which `DiscoveryClient` bean is actually injected into `DiscoveryClientHealthIndicator`. Auto-configuration may create `CompositeDiscoveryClient` as the primary bean. `CompositeDiscoveryClient` aggregates the service list from its delegates; if the composite does not override `probe()`, the interface's default method calls `getServices()` on the composite and still performs that aggregation.

Having a delegate override `probe()` does not mean the composite automatically calls the delegate's `probe()`. To avoid listing services, either the composite needs an appropriate `probe` implementation or the application must configure the right `DiscoveryClient` bean for the health indicator to use. Check the source of your exact release train and measure actual invocations.

Points to check:

- The ordering of each `DiscoveryClient`.
- Whether `CompositeDiscoveryClient` is being used instead of a single implementation.
- Whether `probe` is overridden on the delegates or only on the composite.
- Whether a failing secondary discovery backend should mark composite health `DOWN`.
- Whether the application genuinely needs every registry to serve requests or only a primary one.

Do not merge registry statuses in a way that causes an unused registry to make the application lose readiness. If multiple backends are all mandatory, composite health should reflect those mandatory conditions. If a secondary backend only supports an optional feature, surface its status separately rather than marking the entire application `DOWN`.

### Consul Has Its Own Health Indicator

When Spring Cloud Consul is enabled, an application may have both `DiscoveryClientHealthIndicator` and `ConsulHealthIndicator` at the same time. These two indicators have different configurations. By default, `ConsulHealthIndicator` may read leader status and the service list; to omit the service-list query, configure:

~~~yaml
spring:
  cloud:
    consul:
      health-indicator:
        include-services-query: false
~~~

This property only controls `ConsulHealthIndicator`. It does not replace `spring.cloud.discovery.client.health-indicator.use-services-query` and does not configure `DiscoveryClient.probe()`. When investigating the health endpoint, check which contributor is taking the time so you pick the right property.

## 9. Separating Discovery Health from Liveness and Readiness

Actuator health may be consumed by many systems: dashboards, Prometheus, load balancers, Kubernetes probes, or deployment platforms. Not every health indicator should control restarts or remove instances from traffic.

- **Liveness** answers whether the process is still alive and can continue running.
- **Readiness** answers whether the application is ready to accept new requests.
- **Discovery health** reflects the status of the discovery client according to the configured probe.
- **Business health** reflects dependencies and the ability to perform business operations.

If the registry temporarily loses connectivity while the application can still process incoming requests, liveness does not necessarily need to go `DOWN`. Repeated restarts during a registry outage can increase load and prolong the incident.

If the application needs discovery to locate downstream services for every request, losing discovery may warrant marking readiness `DOWN`. If service addresses are already cached and the application can continue serving safely, the readiness policy may differ. The decision must be based on actual runtime behavior, not solely on the health indicator's name.

When using Spring Boot Actuator readiness groups, inspect the actual contributor names at the health endpoint and configure the group as needed. Never assume discovery health always belongs in readiness or liveness.

## 10. Tracking Overhead Before and After Enabling probe

To know whether the change is effective, measure under the same set of conditions before and after.

Metrics to observe:

| Metric | Before Optimization | After Optimization |
|---|---|---|
| `getServices()` call count | Counted on every health check | Expected to drop or disappear from probe |
| `probe()` call count | Possibly unused | Increases at the health check interval |
| Health indicator latency | Measure p50/p95/p99 | Compare under the same load |
| Requests to registry | Count service-listing requests | Verify whether probe makes lightweight requests |
| CPU and allocations | Measure when service list is large | Check reduction |
| Error rate | Errors from `getServices()` | Errors from the new probe |

Do not attach every service name as a metric label if the number of services is large or changes frequently; doing so creates high-cardinality metrics. You can log the total service count or expose a dedicated gauge when observation is needed.

The probe should also be rate-limited to the health check interval. Do not call `probe` on every business request. If many replicas probe at the exact same time, consider jitter or a short-lived status cache to avoid load spikes on the registry.

## 11. Testing to Ensure getServices() Is No Longer Called

A simple test can confirm that the health indicator follows `probe` instead of the services query. Create a fake `DiscoveryClient` with counters:

~~~java
import java.util.List;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class CountingDiscoveryClient implements DiscoveryClient {

    private final AtomicInteger servicesCalls = new AtomicInteger();
    private final AtomicInteger probeCalls = new AtomicInteger();

    @Override
    public String description() {
        return "Counting discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return Collections.emptyList();
    }

    @Override
    public List<String> getServices() {
        servicesCalls.incrementAndGet();
        throw new UnsupportedOperationException("getServices must not be used by this probe test");
    }

    @Override
    public void probe() {
        probeCalls.incrementAndGet();
    }

    public int servicesCalls() {
        return servicesCalls.get();
    }

    public int probeCalls() {
        return probeCalls.get();
    }
}
~~~

An integration test should initialize the health indicator with `use-services-query=false`, drive the indicator through an instance registration event so it leaves its initial `UNKNOWN` state, then call `health()` and verify that `probeCalls` increases while `servicesCalls` remains `0`. If testing a real registry implementation, add an integration test or measure backend requests to confirm `probe` does not indirectly invoke the service-listing API.

Do not only test that the endpoint returns `UP`. A probe implementation that always succeeds will pass that test without checking connectivity at all. Add a test where the registry probe fails to confirm the health indicator transitions its status accordingly.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Set `use-services-query=false` but latency did not drop | Default `probe()` still calls `getServices()` | Inspect implementation and override `probe` if possible |
| Health indicator always `UP` even when registry disconnects | `probe` performs no actual check | Use a backend check with timeout and error reporting |
| Health endpoint slow when registry is large | `getServices()` fetches the entire list | Measure backend calls; switch to a lightweight probe if applicable |
| Probe fails while registry is still serving | Probe depends on an unnecessary endpoint or permission | Choose an operation representing what the app actually needs |
| Composite client still incurs overhead | Composite inherits default `probe` and calls aggregated `getServices()` | Check primary bean and override `probe` on the composite |
| Readiness `DOWN` causes repeated restarts | Discovery health misused as liveness | Separate liveness, readiness, and discovery status |
| Metric cardinality grows | Dynamic service names attached as labels | Use aggregated metrics, logs, or bounded grouping |
| Probe causes high load similar to old query | Probe still lists services or is called too frequently | Measure call counts and backend cost; add appropriate timeout/jitter |

## 13. Safe Rollout Procedure

Proceed in order:

1. Record the Spring Boot and Spring Cloud release train versions in use.
2. Confirm that the Spring Cloud Commons version supports the `use-services-query` property.
3. Identify the actual `DiscoveryClient` implementation being injected.
4. Check whether current `probe()` is overridden or still calls `getServices()`.
5. Measure latency, backend call counts, and service list size in the current mode.
6. Configure `use-services-query=false` in a staging/test environment.
7. If default `probe` still calls `getServices()`, implement or select an implementation with a lightweight and meaningful probe.
8. Test both healthy registry and failing registry scenarios.
9. Compare p95/p99 latency, backend requests, CPU, and allocations.
10. Inspect Actuator health, readiness, and liveness to ensure traffic policies were not unintentionally altered.
11. Roll out incrementally by instance group and monitor errors before expanding.

If you cannot override the `DiscoveryClient` from the library in use, consider a custom health indicator or an officially supported adapter. Never create two health indicators checking the same backend without controlling ordering and status aggregation, as Actuator might still run the old `getServices()` check.

## 14. Completion Checklist

Before considering the optimization complete, verify:

1. You have clearly identified which health indicator is calling `getServices()`.
2. The property `use-services-query=false` binds properly in your Spring Cloud Commons version.
3. `DiscoveryClient.probe()` performs a genuinely lightweight check.
4. `probe` does not indirectly call `getServices()`.
5. `probe` has a timeout and reports an error when the discovery backend is unreachable.
6. Business health and liveness are not conflated with discovery connectivity.
7. The health endpoint does not enumerate service names unnecessarily.
8. `CompositeDiscoveryClient` and each delegate have been verified.
9. Call counts, latency, and resource usage were measured before and after the change.
10. Both passing and failing probe cases have been tested.

The core takeaway is: **`getServices()` returns the service list, whereas `probe()` should verify discovery client operability at low cost.** Setting `use-services-query=false` only switches the health indicator to call `probe`; to actually reduce load, the `probe` implementation must avoid enumerating all services while still verifying the required condition.

## 15. References

- Spring Cloud Commons — Common Abstractions and DiscoveryClientHealthIndicator: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons — Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- DiscoveryClient interface — description of default `probe()` and override capability: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java
- EurekaDiscoveryClient — example implementation that does not override `probe()` in current source: https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaDiscoveryClient.java
- ConsulDiscoveryClient — example implementation overriding `probe()` to check leader: https://github.com/spring-cloud/spring-cloud-consul/blob/main/spring-cloud-consul-discovery/src/main/java/org/springframework/cloud/consul/discovery/ConsulDiscoveryClient.java
