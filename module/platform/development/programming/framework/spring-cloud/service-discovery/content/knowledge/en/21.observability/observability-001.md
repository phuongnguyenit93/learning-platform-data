# DiscoveryClientHealthIndicator and Composite Discovery Health

## 1. Why Does Service Discovery Need Health Checks?

An application may still respond to HTTP requests and process some traffic while being unable to query the registry. For example, Eureka Server may be temporarily unreachable, the Kubernetes API may reject requests due to missing RBAC permissions, or the discovery client may encounter an error when reading the service list. If monitoring only checks the process and web server, it may conclude the application is completely healthy even though service discovery is degraded.

Spring Cloud Commons provides **DiscoveryClientHealthIndicator** to integrate the status of `DiscoveryClient` into Spring Boot Actuator's health system. This health indicator helps observe the application's ability to invoke the discovery API.

In the Spring Cloud Service Discovery module, health should be viewed across multiple layers:

- Whether the application is still running and serving HTTP traffic.
- Whether `DiscoveryClient` can query registry information.
- Whether specific discovery providers such as Eureka, Consul, or Kubernetes are operating properly.
- Whether the services required by business logic have suitable instances available.
- Whether the discovered instances are actually healthy and processing requests successfully.

These questions are related, but they cannot replace one another. `DiscoveryClientHealthIndicator` primarily checks the `DiscoveryClient` layer; it does not automatically send business requests to every instance to verify the health of each service.

## 2. What Does DiscoveryClientHealthIndicator Check?

`DiscoveryClient` is Spring Cloud's abstraction for retrieving the list of services and their corresponding instances. Common operations include:

- **getServices():** retrieves the list of service IDs currently known to the client.
- **getInstances(serviceId):** retrieves the list of instances for a given service ID.
- **description():** describes the discovery implementation currently in use.

Under the common default configuration, `DiscoveryClientHealthIndicator` calls `getServices()` to retrieve the service list and uses this result as the check. If the operation completes normally, the indicator reports `UP` and may attach the service list; if the query throws an exception, the indicator reports `DOWN` along with error information. In some newer versions, you can set `use-services-query=false` to replace the service-list query with `DiscoveryClient.probe()`, a lighter-weight check. The exact meaning of `probe` depends on the implementation; consult the provider documentation if you need to verify a direct connection to the registry.

This indicates that the check operation through `DiscoveryClient` completed at that point in time; it does not necessarily prove a fresh network round-trip to the registry occurred. For instance, Eureka Client typically reads the service list from its local registry cache. Therefore, an `UP` health status can coexist with Eureka Server being temporarily unreachable, as long as the client still returns cached data. With other providers, `getServices` or `probe` may perform checks differently.

This result does not mean:

- All required service IDs exist in the registry.
- Every instance in the list has an `UP` status.
- Every instance is reachable over the network.
- The business endpoints of those instances respond properly.
- The registry is instantaneously synchronized across all nodes or clients.

An empty service list is not necessarily a connection error. In a newly started environment, an empty namespace, or a system with no registered services, `DiscoveryClient` can still query successfully. If business logic requires a specific service to exist, a separate check must be added for that service.

In some release trains, the indicator also tracks whether `DiscoveryClient` has been initialized. Before the client completes its initialization phase or publishes the corresponding registration event, the health status may be `UNKNOWN` with a description stating the client is not yet initialized. Be sure to distinguish this initialization state from `DOWN` caused by a failed provider query.

## 3. How Is the Health Indicator Exposed in Actuator?

Spring Boot Actuator provides health endpoints and an aggregation mechanism for health contributors. When the required dependencies are present and auto-configuration is enabled, Spring Cloud can register a health indicator for `DiscoveryClient`.

A common configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized

spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

Meaning:

| Property | Effect |
|---|---|
| spring.cloud.discovery.client.health-indicator.enabled | Enables or disables the discovery health indicator provided by Spring Cloud |
| spring.cloud.discovery.client.health-indicator.include-description | Allows including the `DiscoveryClient` description in health details |
| spring.cloud.discovery.client.health-indicator.use-services-query | Uses `getServices()` for the check; if `false`, uses the lighter-weight `probe()` in supported versions |
| spring.cloud.discovery.client.composite-indicator.enabled | Enables or disables the composite discovery health contributor |
| spring.cloud.discovery.enabled | Enables discovery health indicators configured by Spring Cloud |
| management.endpoint.health.show-details | Controls when the health response displays details |
| management.endpoints.web.exposure.include | Determines which Actuator endpoints are exposed over HTTP |

In common current configurations, both the health indicator and composite indicator are enabled by default; `include-description` typically defaults to `false`, and `use-services-query` defaults to `true`. The `use-services-query` property is not present in all older release trains. Refer to the documentation for the Spring Cloud version you are using if the application does not recognize a property or if you want to change its behavior.

For registries with a very large number of services, you can reduce the cost of each health check by using `probe` instead of fetching the entire list:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Only use this option when the `DiscoveryClient` implementation supports an appropriate `probe`. A lighter-weight probe does not provide the service list in health details; its goal is to verify client operability at a lower cost.

Disabling the health indicator does not disable service discovery. The application can still use `DiscoveryClient` to look up services; only the corresponding health contributor stops participating in the health endpoint.

### 3.1. Querying the Health Endpoint

When the health endpoint is exposed and accessible, you can call:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

The response has the general structure:

~~~json
{
  "status": "UP",
  "components": {
    "discoveryComposite": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

This is an illustrative example. Component names, detail structures, and whether a composite component is present depend on the health beans registered in the application. Inspect the actual names in the response rather than assuming every version uses a fixed key.

If the configuration only allows authenticated users to view details, unauthorized requests may only receive the aggregated status. This is intentional security behavior.

## 4. Distinguishing Discovery Health from Service Instance Health

One common misconception is treating `DiscoveryClientHealthIndicator` as a check on all discovered services. The two types of checks serve different purposes:

| Check | Scope | Example Result |
|---|---|---|
| DiscoveryClientHealthIndicator | Ability to query the discovery client | Able to retrieve the service list from the registry |
| Required service check | One or more service IDs chosen by business logic | `payment-service` has at least one instance |
| Instance health | A health endpoint or mechanism on the target instance | Instance responds successfully to a health check |
| Business health | Ability to complete a business flow | Able to generate a quote or confirm an order |

For example, `DiscoveryClient` successfully returns the service list, so discovery health is `UP`. However, `payment-service` has not been deployed yet, so `getInstances(payment-service)` returns an empty list. These two results do not contradict each other: the registry is queryable, while the business service is missing instances.

Conversely, the registry may be temporarily unreachable while the application continues processing requests using cached data or without needing to call other services. Transitioning the entire application to `DOWN` should be based on actual dependency impact rather than being inferred automatically from a single discovery failure.

## 5. Composite Health When Multiple DiscoveryClients Exist

An application may have multiple `DiscoveryClient` implementations on its classpath, such as Eureka alongside another provider, or a primary client and a fallback client. Providers can supply beans implementing `DiscoveryHealthIndicator`; Spring Cloud Commons can group these beans into `DiscoveryCompositeHealthContributor` to observe the health status of each provider.

When using composite health:

- The composite health contributor is based on the beans implementing `DiscoveryHealthIndicator` registered in the context.
- `DiscoveryClientHealthIndicator` is the general health indicator based on the currently selected `DiscoveryClient`.
- Individual provider results may appear as nested sub-details.
- An aggregated status is produced from the component statuses according to health aggregation rules.
- A failing provider can degrade the aggregated status, depending on how the composite indicator and status aggregator are configured.

You can disable the composite contributor separately via `spring.cloud.discovery.client.composite-indicator.enabled=false`. This property does not disable the general `DiscoveryClientHealthIndicator`; the two mechanisms have separate control properties. The composite contributor collects registered `DiscoveryHealthIndicator` beans; depending on the version and providers, this set of beans may include the general indicator and provider-supplied indicators. `DiscoveryClientHealthIndicator` is the general indicator based on the currently selected `DiscoveryClient`.

Do not confuse **CompositeDiscoveryClient** with the composite health indicator. `CompositeDiscoveryClient` is an abstraction that combines or coordinates lookups across multiple `DiscoveryClient` instances. The composite health indicator aggregates the health status of discovery components. An application can have one mechanism without necessarily configuring the other the same way.

### 5.1. When Is Composite Health Needed?

Composite health is useful when:

- The application genuinely uses multiple discovery providers.
- The operations team needs to know which specific provider is failing.
- A primary provider and a fallback provider serve distinct roles that need independent observation.
- You need to detect when one provider cannot be queried even though another provider is still working.

If there is only a single `DiscoveryClient`, a single health indicator is usually sufficient. Avoid adding multiple providers just to produce a complex health response.

### 5.2. Lookup Order Is Not Health Order

When multiple `DiscoveryClient` instances exist, lookup priority order and health status are two separate concerns. One provider may be prioritized for `getInstances`, while another provider is still checked and reports an error in the composite health.

Therefore, when composite health reports `DOWN`, inspect each component's details and determine which provider affects actual request paths. Do not conclude the application cannot discover services based solely on the aggregated status if another provider can still fulfill lookups.

## 6. Spring Boot Status Aggregation Rules

Spring Boot Actuator collects statuses from `HealthIndicator` and `HealthContributor` beans, then aggregates them into the status of the endpoint or health group.

Common statuses:

| Status | Meaning |
|---|---|
| UP | The evaluated component is operating normally |
| DOWN | The component encountered a critical error according to the indicator |
| OUT_OF_SERVICE | The component is temporarily out of service |
| UNKNOWN | The status cannot be determined |

The aggregated status depends on `StatusAggregator` and the status priority order. Under the common default configuration, `DOWN` and `OUT_OF_SERVICE` are considered unhealthy statuses and can cause the health endpoint to return HTTP 503; `UP` typically returns HTTP 200. If the application customizes status ordering or HTTP mappings, the result may differ.

Example status order configuration:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: down,out-of-service,unknown,up
~~~

Do not change the order just to make dashboards show green. The status must accurately reflect the impact on serving capability. If a non-essential secondary provider fails, you may need a separate health group or an appropriate aggregation policy rather than marking the entire application down.

## 7. Which Health Group Should Discovery Belong To?

Actuator can publish overall health as well as separate health groups such as `readiness` or `liveness`. Do not automatically include every health indicator in every group.

Example readiness group configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,requiredServices
~~~

`requiredServices` is the bean name of the custom `HealthIndicator` shown in the next section. When adding an auto-configured indicator to a group, confirm its actual ID in the Actuator response of the running version before declaring it under `include`.

Only include discovery in `readiness` when the ability to query the registry is a mandatory condition for the instance to receive requests. For example, requests to this service always need to look up another service in real time with no cache or safe fallback.

If the application can continue serving using cached data, or if some requests do not require discovery, letting a registry disruption mark the Pod as `NotReady` can remove too much capacity. In that case, observe discovery in overall health or a separate group, while keeping `readiness` focused strictly on conditions truly needed to receive traffic.

Do not put discovery network checks into `liveness` just to trigger automatic restarts when the registry fails. If Eureka or the Kubernetes API suffers a widespread outage, all applications could restart simultaneously and worsen the incident. Liveness should focus on whether the process itself can recover, whereas readiness reflects the ability to serve traffic.

## 8. Customizing Required Service Checks

If business logic requires certain services to have at least one instance, write a custom `HealthIndicator`. The following example checks two required service IDs:

~~~java
import java.util.Map;
import java.util.LinkedHashMap;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component("requiredServices")
public class RequiredServicesHealthIndicator implements HealthIndicator {

    private final DiscoveryClient discoveryClient;

    public RequiredServicesHealthIndicator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @Override
    public Health health() {
        Map<String, Integer> instanceCounts = new LinkedHashMap<>();
        instanceCounts.put("payment-service",
                discoveryClient.getInstances("payment-service").size());
        instanceCounts.put("inventory-service",
                discoveryClient.getInstances("inventory-service").size());

        boolean allAvailable = instanceCounts.values()
                .stream()
                .allMatch(count -> count > 0);

        if (allAvailable) {
            return Health.up()
                    .withDetail("instanceCounts", instanceCounts)
                    .build();
        }

        return Health.down()
                .withDetail("instanceCounts", instanceCounts)
                .withDetail("reason", "A required service has no discovered instance")
                .build();
    }
}
~~~

This example checks for the presence of instances in discovery results without calling each instance's endpoint. If `getInstances` throws an exception, Actuator captures the failure from the indicator; if the list is empty, the indicator explicitly returns `DOWN` because the service is marked as required.

Avoid hardcoding the list of required services in code if each environment has different dependencies. You can externalize service IDs into configuration, while validating the configuration at startup.

If you need to verify that instances can actually serve requests, design a dedicated health check with timeouts, concurrency limits, and result caching. Calling the health endpoint of every instance on each Actuator scrape can generate heavy load and slow down the health endpoint.

## 9. Avoiding Heavy Health Checks and Circular Dependencies

Health endpoints may be called frequently by Kubernetes, load balancers, monitoring systems, and operators. If each health call triggers multiple network queries, the health check itself can become a new source of load.

Principles to apply:

- Use lightweight operations such as checking whether `DiscoveryClient` can query the registry.
- Avoid deeply scanning every service and every instance on every scrape unless necessary.
- Set explicit timeouts for any operation that may make network calls.
- Avoid long retries within the health request path.
- If deep checks are needed, run them periodically in the background and have the health endpoint only read the latest result.
- Distinguish transient errors from persistent failures to prevent constant `UP`/`DOWN` flapping.
- Do not let a health endpoint depend circularly on the very service being checked.

Example of a dangerous circular dependency: service A's health check calls service B, while service B's health check calls service A. When both start up, the two health checks can wait on each other or generate retry storms. Health indicators should check dependencies minimally and with strict bounds.

## 10. Observation and Diagnostics

When `DiscoveryClientHealthIndicator` reports `DOWN`, check in the following order:

1. Read the health response details and the exception from the discovery component.
2. Identify the actual provider: Eureka, Consul, Kubernetes, or another implementation.
3. Verify connectivity to the registry or Kubernetes API from inside the application's runtime environment.
4. Check DNS, ports, TLS, authentication, and authorization.
5. Inspect provider client logs and the timestamp of the most recent fetch/watch.
6. If composite health contains multiple components, identify which component is `DOWN` and whether that provider is on the actual lookup path.
7. If discovery health is `UP` but a required service lacks instances, check the corresponding service ID, namespace, registration, and selectors.
8. If instances exist but requests fail, check host, port, network policies, health endpoints, and load balancing.

| Symptom | Possible Cause | Diagnostic Direction |
|---|---|---|
| Discovery health `DOWN` | Provider query error or exception from `DiscoveryClient` | Check exception, registry endpoint, network, and permissions |
| Discovery health `UP` but service list empty | Registry has no services yet or namespace/filter is incorrect | Check registration, namespace, and provider |
| Discovery health `UP` but required service has no instances | Wrong service ID or instance not yet registered | Check `getInstances(serviceId)`, service name, and registry |
| Composite health `DOWN` while one provider still works | Another provider in the composite is failing | Read each component's status and lookup order |
| Health endpoint slow | Indicator runs heavy queries or blocks on network | Measure latency, timeouts, and call counts |
| Pod `NotReady` when registry fails | Discovery is included in the readiness group | Review readiness policy and fallback capability |
| Application restarts repeatedly when registry fails | Liveness depends on discovery | Decouple liveness from registry availability |

## 11. Testing Health Indicators

Test both healthy and failure scenarios for the provider:

1. When `DiscoveryClient` queries successfully, verify the health component has the expected status.
2. When `getServices` returns an empty list without an exception, verify the application interprets the empty state properly.
3. When the provider throws an exception, verify the indicator reports an error without leaking sensitive information.
4. When multiple `DiscoveryClient` instances exist, verify each component is accurately represented in composite health.
5. When one provider fails while another remains operational, verify the overall status aligns with operational policy.
6. Verify that the `readiness` and `liveness` health groups do not accidentally include the wrong contributors.
7. Measure health endpoint latency when monitoring scrapes at the expected frequency.
8. Check the response when callers lack permission to view health details.

You can mock `DiscoveryClient` in unit tests to simulate service lists, empty instance lists, and exceptions. For integration tests, use a test provider or isolated test environment to verify auto-configuration and actual bean names.

## 12. Common Design Mistakes

### 12.1. Treating DiscoveryClient UP as Every Service Being Healthy

The indicator only checks the ability to query discovery according to the implementation. To verify a specific service ID, check its instances separately; to verify business processing capability, implement health checks at the appropriate layer.

### 12.2. Treating an Empty Service List as a Connection Error

An empty registry can be a valid state. Distinguish a successful query returning no data from a query failing due to network or permission issues.

### 12.3. Including Discovery in Liveness

A registry failure does not mean the Spring Boot process needs to restart. Liveness depending on discovery can trigger a restart storm during a widespread outage.

### 12.4. Including Every Provider in Readiness

If an application has a fallback provider or does not use every provider for every request, a failing secondary provider should not necessarily remove the Pod from traffic. Readiness must reflect actual serving requirements.

### 12.5. Health Checks Scanning All Instances

Calling the health endpoint of every instance on each scrape can create heavy load and circular dependencies. Use shallow checks for aggregated health; design separate deep checks with scheduled execution, timeouts, and load limits.

### 12.6. Exposing Health Details to Everyone

Health responses can reveal provider names, service IDs, exceptions, hostnames, or internal topology. Restrict `show-details` and protect endpoints with access controls.

## 13. Configuration and Operations Workflow

1. Identify the actual `DiscoveryClient` provider and Spring Cloud version.
2. Verify whether the auto-configured health indicator is enabled.
3. Configure `include-description` and an appropriate detail exposure policy.
4. Query Actuator health to record the actual component names and statuses.
5. If multiple providers exist, inspect composite health and distinguish it from lookup order.
6. Determine which service IDs are truly mandatory for application requests.
7. Create custom business health indicators only when you need to check specific service IDs or instances.
8. Decide whether discovery belongs in the `readiness` group; avoid placing it in `liveness`.
9. Configure timeouts and load limits for any checks that make network calls.
10. Test scenarios involving provider failure, empty registry, missing instances, multiple providers, and frequent health endpoint polling.

## 14. References

- [Spring Cloud Commons - Common Abstractions and Health Indicators](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons - Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)

Refer to the documentation for your project's release train; health indicator properties and behavior may vary across versions.

## 15. Summary

`DiscoveryClientHealthIndicator` exposes the ability to run a check via `DiscoveryClient` to Spring Boot Actuator. With providers that maintain a local registry cache such as Eureka, an `UP` health status does not necessarily prove the registry server is reachable at that exact moment. Nor does the indicator confirm that all required services exist or that all instances are healthy. An empty service list can be valid if the query succeeded and the registry currently holds no entries.

When an application has multiple `DiscoveryClient` implementations, composite health can show the state of each provider as well as the overall status. Distinguish composite health from `CompositeDiscoveryClient`, which is used for lookups. Spring Boot further aggregates `HealthContributor` beans according to `StatusAggregator` and configured health groups. Only include discovery in `readiness` when the registry is strictly required to serve requests; never use registry failures as a `liveness` condition. For checks targeting specific services, create custom indicators with timeouts and load limits, and protect health details from unauthorized callers.
