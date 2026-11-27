# DiscoveryClientHealthIndicator and DiscoveryCompositeHealthContributor

This lesson belongs to the **Observability** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Commons integrates service discovery with Spring Boot Actuator using health indicators. `DiscoveryClientHealthIndicator` checks the usability of the current blocking `DiscoveryClient`; `DiscoveryCompositeHealthContributor` groups registered `DiscoveryHealthIndicator`s into a single health contributor group so Actuator can display both the aggregated status and each provider's status.

The two components have different scopes. The individual indicator performs a check against the DiscoveryClient and produces `UP`, `DOWN`, or `UNKNOWN`. The composite contributor only organizes multiple indicators into a result tree; it does not query the registry itself on behalf of child indicators. Therefore, when reading `/actuator/health`, you must inspect both the aggregated status and the details of each component.

An important behavior of the current implementation is that `DiscoveryClientHealthIndicator` waits for `InstanceRegisteredEvent` to mark discovery as initialized. Before that event, health returns `UNKNOWN`. After initialization, the indicator calls `getServices()` by default; if the call does not throw an exception, the status is `UP`, even when the service list is empty. This lesson explains the limits of this check, how to reduce query overhead, enable/disable configurations, and how to test in real environments.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the role of `DiscoveryClientHealthIndicator` in Spring Cloud Commons.
2. Distinguish an individual health indicator from `DiscoveryCompositeHealthContributor`.
3. Describe the auto-configuration conditions that create the blocking discovery health indicator.
4. Explain why the initial status may be `UNKNOWN`.
5. Distinguish `getServices()` and `probe()` when checking discovery.
6. Configure `use-services-query` to adjust health check cost.
7. Configure description and understand its impact on aggregated health results.
8. Enable/disable the indicator and composite contributor independently.
9. Read the Actuator `/actuator/health` result tree.
10. Distinguish discovery health from application health, readiness, liveness, and service registration.
11. Recognize limitations when using multiple discovery providers or reactive discovery.
12. Design tests for UNKNOWN, UP, DOWN, composite states, and properties.
13. Diagnose situations where health is UP yet a target service ID has no instances to call.
14. Establish appropriate operational policies to avoid health checks placing unnecessary load on the registry.

## 2. Role of DiscoveryClientHealthIndicator

### 2.1. DiscoveryClient Provides Service Lookup

`DiscoveryClient` is the blocking abstraction of Spring Cloud Commons. It allows an application to query known service IDs and retrieve instance lists by service ID:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

Implementations can connect to Eureka, Consul, Zookeeper, or another discovery source. Applications rely on a shared contract rather than provider-specific APIs.

However, having a `DiscoveryClient` bean in the ApplicationContext does not prove the registry is reachable. The bean can exist while DNS, networking, credentials, or the registry server fail. `DiscoveryClientHealthIndicator` adds a health check by invoking the discovery API when Actuator collects health.

### 2.2. What Does the Individual Indicator Check?

`DiscoveryClientHealthIndicator` relies on the active `DiscoveryClient` implementation. Once discovery is marked initialized, the indicator invokes one of two operations:

- `getServices()` if `use-services-query=true`.
- `probe()` if `use-services-query=false`.

If the operation completes without throwing an exception, the indicator returns status `UP`. If an exception occurs, the indicator returns `DOWN` and attaches the error to the health result. If the indicator has not yet received the initialization signal, it returns `UNKNOWN`.

This means the indicator primarily checks whether the discovery API can be called. It does not automatically verify a specific service ID, a minimum instance count, or HTTP reachability to individual instances.

### 2.3. Processing Flow

~~~mermaid
flowchart TD
    A["Actuator requests health"] --> B{"Discovery initialized?"}
    B -->|No| C["UNKNOWN: Discovery Client not initialized"]
    B -->|Yes| D{"use-services-query"}
    D -->|true| E["Call DiscoveryClient.getServices()"]
    D -->|false| F["Call DiscoveryClient.probe()"]
    E --> G{"Call threw exception?"}
    F --> G
    G -->|No| H["UP"]
    G -->|Yes| I["DOWN + error detail"]
~~~

The indicator does not retry indefinitely when a provider fails. Timeouts, retries, and connection behavior depend on the DiscoveryClient implementation and underlying client configuration.

## 3. Conditions for Creating the Health Indicator

Spring Cloud Commons auto-configures health indicators when matching conditions are met. For the blocking indicator, the main conditions include:

- Spring Boot Actuator health API is on the classpath.
- A `DiscoveryClient` bean exists in the ApplicationContext.
- Discovery is enabled.
- Blocking discovery client is enabled.
- The discovery health indicator's own property is not disabled.

In the current auto-configuration, the `DiscoveryClientHealthIndicator` bean is created in the discovery/load-balancer configuration. The composite bean is created when at least one bean implementing `DiscoveryHealthIndicator` exists and the composite property remains enabled.

| Component | Key Conditions |
| --- | --- |
| `DiscoveryClientHealthIndicator` | Actuator health class, DiscoveryClient bean, discovery enabled, blocking discovery enabled, and health-indicator enabled. |
| `DiscoveryCompositeHealthContributor` | `DiscoveryHealthIndicator` bean present and composite-indicator enabled. |
| Reactive discovery health contributor | Matching `ReactiveDiscoveryClient`/`ReactiveDiscoveryHealthIndicator`, reactive discovery, and reactive Actuator support. |

Adding `spring-boot-starter-actuator` alone does not guarantee the discovery indicator will appear. The application also needs a discovery provider or a suitable DiscoveryClient implementation.

## 4. Initialization Lifecycle and the UNKNOWN State

### 4.1. The Indicator Listens for InstanceRegisteredEvent

The current implementation of `DiscoveryClientHealthIndicator` implements `ApplicationListener<InstanceRegisteredEvent<?>>`. Upon receiving `InstanceRegisteredEvent`, the indicator marks discovery as initialized.

Before that point, the health result generally looks like:

~~~json
{
  "status": "UNKNOWN",
  "description": "Discovery Client not initialized"
}
~~~

This state means discovery initialization has not yet been confirmed complete. It does not necessarily mean the registry is broken.

### 4.2. Why Does the Event Matter?

With service registry auto-registration, Spring Cloud typically publishes two events:
- `InstancePreRegisteredEvent` before registering the instance.
- `InstanceRegisteredEvent` after registering the instance.

`DiscoveryClientHealthIndicator` uses the second event as the initialization signal. Only afterward do subsequent health checks perform the query/probe.

If the application disables auto-registration, the provider does not publish the corresponding event, or the application uses a manual registration lifecycle that does not emit this event, the indicator may remain in the `UNKNOWN` state in the current implementation. Check the lifecycle of your provider and release train instead of assuming this is a registry connection failure.

Configuration to disable auto-registration:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

If you need to disable auto-registration while still wanting the health indicator to reflect discovery, determine how your provider emits the initialization signal in a manual workflow. Do not fake the event in production just to force the status to UP when the registry is not ready.

### 4.3. UNKNOWN Is Different from DOWN

| Status | Meaning |
| --- | --- |
| `UNKNOWN` | The indicator has not confirmed discovery initialization or cannot determine status. |
| `UP` | The query/probe completed without throwing an exception. |
| `DOWN` | The query/probe threw an exception and the indicator recorded the error. |

Do not convert every `UNKNOWN` case into `DOWN` with a blanket monitoring rule. Distinguish startup phases, auto-registration settings, and actual errors when calling the registry.

## 5. getServices() and probe()

### 5.1. Service List Query Mode

Default:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: true
~~~

The indicator calls `DiscoveryClient.getServices()`. On success, the list of service IDs is added to health details under the `services` key.

Example result:

~~~json
{
  "status": "UP",
  "details": {
    "services": [
      "inventory-service",
      "pricing-service",
      "orders-service"
    ]
  }
}
~~~

The list can become very large in environments with many teams or services. If the health endpoint is polled continuously by orchestrators and monitoring tools, querying all service IDs can put significant load on the registry.

### 5.2. An Empty List Can Still Return UP

The indicator does not require the returned list to contain at least one element. If `getServices()` returns an empty list without throwing an exception, the implementation still sets status `UP`.

Therefore:

- `UP` proves the discovery API operation completed according to the indicator's contract.
- `UP` does not prove the service ID your application needs to call exists.
- `UP` does not prove that service has healthy instances.
- `UP` does not prove your application can make HTTP calls to instances successfully.

If business logic needs to verify a critical dependency, create a dedicated health check that checks that service ID or probes the dependency with an appropriate timeout. Avoid turning the generic health indicator into a check of every dependency on every health request.

### 5.3. Switching to probe()

To avoid fetching the entire service list:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

The indicator will call `DiscoveryClient.probe()` and omit the service list from details.

`DiscoveryClient` provides a default implementation of `probe()` by calling `getServices()`. Providers may override this method to perform a lighter check. Thus, setting `use-services-query=false` only ensures the indicator calls `probe()`; actual load reduction depends on the provider implementation.

### 5.4. Comparing the Two Modes

| Criterion | getServices() | probe() |
| --- | --- | --- |
| Goal | Query all known service IDs. | Check whether the client can perform a discovery operation. |
| Health detail | Includes the `services` list. | No service list generated by the indicator. |
| Cost | Can be high when the registry has many services. | Can be lower if the provider overrides probe with a lighter operation. |
| Commons Default | Used when `use-services-query=true`. | Used when the property is false. |
| Limitation | An empty list can still return UP. | Default probe still calls getServices; not automatically lighter. |
## 6. Description and Health Details

### 6.1. include-description

`DiscoveryClient` has a `description()` method to provide an implementation description. The property `spring.cloud.discovery.client.health-indicator.include-description` defaults to `false`. When set to `true`, the indicator reads `client.description()` and attaches the description to the health status; the description may appear in the aggregated health output.

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          include-description: true
          use-services-query: true
~~~

Descriptions help distinguish implementations in multi-provider environments. Do not include internal endpoints, sensitive hostnames, or credentials in the description string.

### 6.2. Services Detail

When using `getServices()`, the indicator adds the service ID list to details. This is useful diagnostic data, but it can reveal internal topology. Control who can read health endpoint details.

### 6.3. Hiding Details Does Not Mean Disabling the Indicator

Spring Boot lets you control the level of detail exposed via Actuator:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Common values are `never`, `when-authorized`, and `always`. This setting controls what content is displayed; it does not stop health indicators from executing their checks.

If the goal is to reduce registry query load, configure `use-services-query` or disable the indicator. If the goal is to restrict users from viewing topology, adjust show-details/show-components and security.

## 7. What Is DiscoveryCompositeHealthContributor?

### 7.1. Composite Contributor Aggregates Indicators

`DiscoveryCompositeHealthContributor` is an adapter that turns a collection of `DiscoveryHealthIndicator` beans into a Spring Boot Actuator `CompositeHealthContributor`.

It does not call `DiscoveryClient.getServices()` on behalf of each indicator and does not connect to the registry itself. Each child indicator performs its own check; the composite contributor provides a named structure so Actuator displays each result.

For example, the ApplicationContext contains:
- Generic indicator `DiscoveryClientHealthIndicator`.
- Provider-specific indicator for provider A.
- Provider-specific indicator for provider B.

The composite contributor groups them under one health group.

~~~mermaid
flowchart TD
    ACT["Actuator HealthEndpoint"] --> ROOT["DiscoveryCompositeHealthContributor"]
    ROOT --> GENERIC["DiscoveryClientHealthIndicator"]
    ROOT --> PROVIDER_A["Provider A DiscoveryHealthIndicator"]
    ROOT --> PROVIDER_B["Provider B DiscoveryHealthIndicator"]
    GENERIC --> CLIENT["Blocking DiscoveryClient"]
    PROVIDER_A --> REG_A["Registry A health check"]
    PROVIDER_B --> REG_B["Registry B health check"]
~~~

### 7.2. Composite Is Not CompositeDiscoveryClient

Two similarly named concepts have different functions:

| Component | Role |
| --- | --- |
| `DiscoveryCompositeHealthContributor` | Groups multiple `DiscoveryHealthIndicator`s into a health contributor tree. |
| `CompositeDiscoveryClient` | Combines multiple `DiscoveryClient` implementations to perform discovery operations. |

Composite health is used to observe the state of discovery indicators. Composite discovery client is used to query discovery sources. An application may have one, both, or neither, depending on providers and configuration.

### 7.3. Conditions for Creating the Composite

The composite contributor is auto-configured when:
1. At least one bean implementing `DiscoveryHealthIndicator` exists.
2. `spring.cloud.discovery.client.composite-indicator.enabled` is not disabled.
3. The corresponding discovery auto-configuration is enabled.

If there are no child indicators, the composite has no data to aggregate and the composite bean is not created under current conditions.

## 8. Reading /actuator/health Results

### 8.1. Configuring Actuator

The application needs the Actuator dependency and an appropriate discovery provider. The health endpoint is typically accessed via:

~~~text
GET /actuator/health
~~~

To show components and details during local testing, configure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

In production, replace `always` with `when-authorized` or restrict access using Spring Security and a management network.

### 8.2. Example Response with Composite

Illustrative response when both the generic indicator and a provider-specific indicator exist:

~~~json
{
  "status": "UP",
  "components": {
    "discoveryComposite": {
      "status": "UP",
      "components": {
        "discoveryClient": {
          "status": "UP",
          "details": {
            "services": [
              "inventory-service",
              "pricing-service"
            ]
          }
        },
        "registryProvider": {
          "status": "UP",
          "details": {
            "description": "Provider-specific discovery health"
          }
        }
      }
    }
  }
}
~~~

Exact child names depend on the registered beans and implementations. `discoveryClient` is the name provided by the current `DiscoveryClientHealthIndicator`; provider-specific indicators may use their own names.

### 8.3. Composite Status and Child Status

The composite displays the status of each child contributor along with the aggregated status. Spring Boot uses a status aggregation strategy to compute the overall status. For custom statuses, configure the ordering or provide an appropriate StatusAggregator.

Example severity order configuration:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: down,out-of-service,unknown,up
~~~

Do not assume the aggregated status is always UP just because one child returns UP. Inspect each child and the application's status aggregation order.

### 8.4. HTTP Status Code Does Not Replace JSON Status

Under Spring Boot's default mapping:
- `DOWN` and `OUT_OF_SERVICE` typically map to HTTP 503.
- `UP` and `UNKNOWN` have no special error mapping, so they typically return HTTP 200.

Therefore, monitoring systems should read the `status` field in the response rather than relying solely on HTTP 200. If the application configures custom HTTP status mappings, re-verify behavior after changes.

## 9. Independent Enable/Disable Configuration

The related properties have distinct scopes:

| Property | Target | Default per Commons config metadata |
| --- | --- | --- |
| `spring.cloud.discovery.client.health-indicator.enabled` | Enable/disable the generic blocking DiscoveryClientHealthIndicator. | `true` |
| `spring.cloud.discovery.client.health-indicator.include-description` | Whether to include DiscoveryClient description in health. | `false` |
| `spring.cloud.discovery.client.health-indicator.use-services-query` | Choose between getServices or probe. | `true` |
| `spring.cloud.discovery.client.composite-indicator.enabled` | Enable/disable DiscoveryCompositeHealthContributor. | `true` |
| `spring.cloud.discovery.enabled` | Enable/disable discovery overall and related auto-configurations. | `true` |
| `spring.cloud.discovery.blocking.enabled` | Enable/disable blocking discovery client. | `true` |
| `spring.cloud.discovery.reactive.enabled` | Enable/disable reactive discovery client. | `true` |

### 9.1. Disabling the Generic Health Indicator

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
~~~

This prevents auto-configuration from creating `DiscoveryClientHealthIndicator`. Other provider-specific `DiscoveryHealthIndicator`s may still exist. If they exist and the composite remains enabled, the composite can still be created from the remaining indicators.

### 9.2. Disabling the Composite Contributor

~~~yaml
spring:
  cloud:
    discovery:
      client:
        composite-indicator:
          enabled: false
~~~

Child indicators may still be created and appear as standalone health components. Only the aggregated discovery group is disabled.

### 9.3. Omitting Description Only

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          include-description: false
~~~

The indicator still runs. This setting only omits the DiscoveryClient description from the health result.

### 9.4. Switching to probe

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

The indicator remains active but uses `probe()`. Load reduction depends on the provider implementation.

### 9.5. Disabling All Discovery

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

This is a broad-scope switch. It affects discovery auto-configurations, not just the health indicator. Do not use this property if your goal is only to hide health details or reduce query cost.

### 9.6. Disabling Blocking Discovery Only

~~~yaml
spring:
  cloud:
    discovery:
      blocking:
        enabled: false
~~~

The blocking health indicator depends on the blocking DiscoveryClient and corresponding auto-configuration conditions, so it may not be created. Reactive discovery may remain enabled if supported by the provider and reactive stack.

## 10. Blocking and Reactive Health Contributors

This lesson focuses on `DiscoveryClientHealthIndicator` and `DiscoveryCompositeHealthContributor` for blocking discovery.

Spring Cloud Commons also has reactive abstractions:
- `ReactiveDiscoveryClient`.
- `ReactiveDiscoveryHealthIndicator`.
- `ReactiveDiscoveryCompositeHealthContributor`.

Reactive contributors fit reactive health infrastructure and providers with reactive discovery support. Do not assume the blocking indicator automatically checks the reactive client or vice versa.

The `spring.cloud.discovery.client.composite-indicator.enabled` property is used in the corresponding composite discovery configuration; verify both blocking and reactive contributors in the ApplicationContext if the application enables both stacks.
## 11. Distinguishing Discovery Health from Readiness and Liveness

### 11.1. Discovery Health Is Not Readiness

Discovery health answers the question: can the application call the discovery API according to the current check?

Readiness answers the question: should the instance start receiving new traffic?

An application may have discovery API UP while a specific dependency service has zero instances. Conversely, the discovery registry may temporarily lose connectivity while the application continues serving in-flight requests or using a cached list of recent instances.

If service discovery is a mandatory requirement to receive new traffic, consider placing the discovery component into the readiness group. Example:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,discoveryComposite
~~~

Component names must match the actual health contributor IDs in the application. Check the `/actuator/health` response before putting this into deployment probes.

### 11.2. Avoid Using Discovery as Default Liveness

Liveness should reflect whether the process is stuck or unable to continue running. If an external registry temporarily loses connectivity and liveness flips to DOWN, the orchestrator could restart instances en masse even though the fault lies in the registry infrastructure.

Readiness is usually the more appropriate place if losing discovery prevents the instance from serving new requests. The choice depends on architecture and ability to serve using cache/fallback.

### 11.3. Comparison Table

| Mechanism | Question |
| --- | --- |
| DiscoveryClientHealthIndicator | Can the discovery client perform getServices/probe after initialization? |
| DiscoveryCompositeHealthContributor | What is the aggregated status of child discovery health indicators? |
| Liveness | Is the process healthy enough to keep running? |
| Readiness | Is the instance ready to accept new traffic? |
| Business dependency check | Does a specific dependency meet business requirements? |

## 12. Health Check Cost and Frequency

### 12.1. Frequent Polling Can Generate Load

Orchestrators, load balancers, and monitoring platforms may call the health endpoint at short intervals. If every call runs `getServices()` against a large registry, total query volume can increase substantially.

Estimate load using a simple formula:

~~~text
Total health checks per minute
= number of application instances × 60 / check interval (seconds)
~~~

For example, 120 instances with a 10-second interval:

~~~text
120 × 60 / 10 = 720 checks per minute
~~~

If each check triggers querying a large service list, consider `probe()`, provider-side caching, or adjusting monitoring frequency.

### 12.2. Reducing Returned Data

`use-services-query=false` eliminates the step of fetching the service list and its corresponding detail. However, it does not guarantee the provider does not query the list internally inside `probe()`.

Read the provider implementation or observe metrics to determine whether probe is genuinely lighter.

### 12.3. Bounding Timeouts

Health indicators need to return within the timeframe expected by Actuator, orchestrators, and monitoring tools. Timeouts must be configured appropriately on the discovery provider/client. If timeouts are too long, health requests can drag out and cause checks to overlap.

Do not increase timeouts indefinitely to mask registry errors. Set a deadline aligned with the probe interval and the health endpoint's total response budget.

## 13. Multiple Discovery Providers in the Same Application

### 13.1. Multiple DiscoveryClients

Spring Cloud Commons allows multiple DiscoveryClient implementations to coexist. Clients can be combined via `CompositeDiscoveryClient` and ordered accordingly.

The generic health indicator receives a DiscoveryClient from the ApplicationContext via active wiring rules. If the context has multiple candidates, verify the primary or composite client that the indicator actually uses.

### 13.2. Multiple DiscoveryHealthIndicators

The composite health contributor collects all `DiscoveryHealthIndicator` beans. This enables providers to publish dedicated health checks alongside the generic indicator.

Example:
- Generic discovery client check.
- Provider A health check.
- Provider B health check.

If provider A is DOWN while the generic client is UP, the composite still shows both results so operations teams know which layer failed. Aggregated status is computed by Spring Boot's StatusAggregator.

### 13.3. Do Not Confuse Composite Discovery and Composite Health

A CompositeDiscoveryClient can select or combine service instance results. DiscoveryCompositeHealthContributor only aggregates health. The two components do not share the same responsibility and do not replace each other.

## 14. Testing DiscoveryClientHealthIndicator

### 14.1. States to Test

An indicator test suite should verify:

1. Before receiving the initialization event, status is UNKNOWN.
2. After the initialization event, when getServices returns a list, status is UP.
3. When getServices returns an empty list without exception, status is still UP.
4. When getServices throws an exception, status is DOWN.
5. With use-services-query=false, probe is called instead of the indicator calling getServices directly.
6. include-description controls the description.
7. Services detail only appears in getServices mode.

These cases reflect the indicator's logic and help avoid the misconception that it checks for the existence of a specific service.

### 14.2. Testing in ApplicationContext

Use a Spring Boot test context with Actuator and a DiscoveryClient test double. You can build a test provider to:
- Return a fixed list of services.
- Return an empty list.
- Throw an exception when getServices/probe is called.
- Publish `InstanceRegisteredEvent` after the test fixture completes its initialization step.

Tests should verify that the `DiscoveryClientHealthIndicator` bean is actually auto-configured when matching conditions and properties hold.

### 14.3. Testing the Composite Contributor

Register two differently named `DiscoveryHealthIndicator` beans, one returning UP and one returning DOWN. Call HealthEndpoint and verify:
- The composite contributor is created when the property is enabled.
- Both child contributors are present.
- Each child preserves its individual status.
- Root/composite status follows StatusAggregator.
- When the composite property is disabled, child indicators can still appear individually.

Do not merely assert that the composite bean exists. Inspect the health endpoint output to verify that names and the contributor tree are assembled properly.

### 14.4. Testing Properties

| Property | Enable/Disable Test |
| --- | --- |
| `health-indicator.enabled` | Generic indicator present/absent in context. |
| `composite-indicator.enabled` | Composite contributor present/absent when child indicators exist. |
| `include-description` | Description appears/omitted in health output. |
| `use-services-query` | getServices/probe branch called properly. |
| `spring.cloud.discovery.enabled` | Overall discovery auto-configuration enabled or excluded. |
| `spring.cloud.discovery.blocking.enabled` | Whether the blocking indicator is configured. |

## 15. Testing via the HTTP Health Endpoint

### 15.1. Calling the Endpoint

~~~bash
curl --request GET \
  http://localhost:8080/actuator/health
~~~

To inspect details during local testing, you can configure:

~~~yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

In production environments, only grant permission to view details to appropriate principals.

### 15.2. Assertions Should Rely on Status and Components

An HTTP test should verify:
- HTTP status code according to configured mappings.
- Root health status.
- Presence or absence of the discovery composite component.
- Status of each child.
- Services detail when use-services-query is enabled.
- Description when include-description is enabled.

Do not assert only HTTP 200. UNKNOWN can also map to HTTP 200 under Spring Boot's default status mapping.

## 16. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Discovery component does not appear. | Missing Actuator, DiscoveryClient bean, blocking discovery, or property disabled. | Check dependencies, beans, and conditions. |
| Status is always UNKNOWN. | Indicator has not received InstanceRegisteredEvent or registration lifecycle does not emit the event. | Check auto-registration/provider lifecycle and active version. |
| Status is UP yet no services exist. | getServices returns an empty list without exception. | Check service registration, namespace, and service ID; UP does not verify list items exist. |
| Status is DOWN. | getServices/probe threw an exception. | Check registry endpoint, DNS, network, credentials, TLS, and timeout. |
| Probe mode still consumes heavy resources. | Provider does not override probe and default probe still calls getServices. | Check provider implementation or metrics. |
| Composite does not appear. | No DiscoveryHealthIndicator bean exists or composite property is disabled. | Check child indicators and composite-indicator.enabled. |
| Composite is UP even though one provider is UNKNOWN. | StatusAggregator or another contributor determines aggregated status by severity order. | Check child statuses and status.order configuration. |
| Only generic indicator appears. | Provider does not supply its own DiscoveryHealthIndicator or provider health auto-config did not run. | Check provider integration and health indicator beans. |
| Disabled health-indicator yet discovery component still appears. | Provider-specific indicator is still registered or composite contains another indicator. | Inspect contributor beans; disable composite if you need to remove the group. |
| Disabled composite yet child health still appears. | Child indicators are still registered independently by Spring Boot. | This is expected behavior; the composite flag only disables the composite contributor. |
| Health endpoint returns 200 despite UNKNOWN status. | Spring Boot's default HTTP mapping does not map UNKNOWN to 503. | Read the status field in JSON and configure mapping if policy requires it. |
| Health endpoint is slow. | getServices queries a large list or provider timeout is high. | Consider probe, timeout, probe interval, and provider-specific optimizations. |
| Liveness causes pods to restart on registry failure. | Discovery health was attached to the liveness group. | Move it to readiness if discovery only affects accepting new traffic. |
| Health details not visible over HTTP. | show-details/show-components or security policy hides details. | Configure Actuator according to environment and access permissions. |
| Reactive discovery exists but no blocking indicator. | Application only enables reactive DiscoveryClient. | Check ReactiveDiscoveryHealthIndicator and reactive composite contributor separately. |

## 17. Operational Principles

1. **Understand what UP really means.** UP only confirms getServices/probe completed without exception per the indicator's contract.
2. **Handle UNKNOWN according to lifecycle.** Check InstanceRegisteredEvent and auto-registration before concluding the registry failed.
3. **Choose query mode intentionally.** Use probe if the provider has a lightweight implementation and you do not need the service list.
4. **Do not assume probe is always cheap.** Default probe may call getServices.
5. **Separate indicator and composite.** Disabling one indicator does not mean disabling all provider health indicators.
6. **Observe child statuses.** Composite status can hide details if you only look at the root.
7. **Do not use health to verify every service.** Critical dependencies need dedicated health checks with clear timeouts and semantics.
8. **Distinguish readiness and liveness.** A registry outage should not automatically trigger a restart loop.
9. **Protect health details.** Service lists and provider descriptions can expose internal topology.
10. **Set reasonable timeouts.** Health requests must finish before orchestrator/monitoring deadlines.
11. **Monitor overhead.** Measure indicator duration, probe counts, and registry load.
12. **Verify against your release train.** Auto-configuration conditions and reactive counterparts may vary by Spring Cloud/Spring Boot version.

## 18. Completion Checklist

- [ ] Can explain what DiscoveryClientHealthIndicator checks.
- [ ] Can distinguish an individual indicator from DiscoveryCompositeHealthContributor.
- [ ] Can distinguish DiscoveryCompositeHealthContributor from CompositeDiscoveryClient.
- [ ] Know the auto-configuration conditions for the blocking indicator.
- [ ] Can explain the UNKNOWN state before the initialization event.
- [ ] Understand the role of InstanceRegisteredEvent.
- [ ] Know that a successful getServices call can return UP even with an empty list.
- [ ] Can distinguish use-services-query=true and false.
- [ ] Understand that default probe may still call getServices.
- [ ] Can configure include-description and understand default false.
- [ ] Can configure health-indicator.enabled.
- [ ] Can configure composite-indicator.enabled.
- [ ] Can distinguish disabling the indicator, disabling the composite, and disabling all discovery.
- [ ] Can read the component tree in /actuator/health.
- [ ] Understand status aggregation and HTTP status mapping.
- [ ] Can distinguish discovery health from readiness and liveness.
- [ ] Recognize reactive health contributors as a separate branch.
- [ ] Have tests for UNKNOWN, UP, DOWN, empty service list, and probe.
- [ ] Have tests for composite child statuses and enable/disable properties.
- [ ] Protect health details and monitor health polling overhead.

**Official documentation to cross-check for your project version:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClientHealthIndicator, DiscoveryCompositeHealthContributor, and enable/disable properties.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): defaults for health-indicator, composite-indicator, include-description, and use-services-query.
- [DiscoveryClientHealthIndicator source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/health/DiscoveryClientHealthIndicator.java): initialization event, getServices/probe, and status.
- [CommonsClientAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java): conditions for creating the blocking health indicator and composite contributor.
- [ReactiveCommonsClientAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ReactiveCommonsClientAutoConfiguration.java): reactive discovery health contributor.
- [Spring Boot Actuator – Health Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): show-details, show-components, status aggregation, and HTTP mapping.

A health indicator is a bounded operational signal. Inspect actual responses, child contributors, and provider behavior in test environments; then choose a readiness/liveness policy aligned with your application's ability to serve when the registry experiences issues.
