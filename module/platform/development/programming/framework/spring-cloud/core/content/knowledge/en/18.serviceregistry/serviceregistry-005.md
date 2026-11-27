# Enabling and Disabling Auto-registration via Properties or Annotations

> **Chapter:** ServiceRegistry  
> **Module:** SPRING_CLOUD_CORE

In a Spring Cloud system, an application may need to look up other services without registering its own instance in the service registry. For example, a batch worker that only calls internal services, an application running in an integration test, or a temporary instance that must not appear in the traffic-serving endpoint list.

Spring Cloud Commons provides application-level **auto-registration** controls. It can be disabled via the property `spring.cloud.service-registry.auto-registration.enabled=false` or by placing `@EnableDiscoveryClient(autoRegister = false)` on the application configuration. Both options affect the Spring Cloud-integrated auto-registration workflow; they must be distinguished from registry lookup capabilities and manual registration operations.

This lesson explains how to choose the configuration approach, how to verify startup and shutdown behavior, and scenarios requiring registration control in the **SPRING_CLOUD_CORE** module.

## 1. Discovery and Registration Are Two Different Directions

Service discovery typically involves two needs:

- **Discovery:** the application finds instances of other services by service ID.
- **Registration:** the application publishes its own instance so other clients can find it.

An application may need discovery without needing registration. For example, `report-worker` can look up `catalog-service` and `pricing-service` without exposing HTTP endpoints for other services to call. In that case, disabling auto-registration does not mean disabling discovery.

| Capability | Meaning | Disabled by auto-registration=false? |
| --- | --- | --- |
| Auto-registering the application's own instance | Sends host, port, and metadata to the registry at startup | Yes, for the Spring Cloud-managed auto-registration flow |
| Looking up other services | Fetches instances by service ID via DiscoveryClient | No |
| Selecting an instance for requests | Load balancing over the instance list | No |
| Manual registration via ServiceRegistry | Code explicitly invokes the registration API | Not implicitly |
| Health checks and instance status | Provider or platform updates status | Not automatically disabled solely by this property |

Therefore, before disabling registration, determine whether the application needs to be discoverable by other services or only acts as a client.

## 2. How Does Auto-registration Work in Spring Cloud?

Spring Cloud Commons defines shared abstractions such as `ServiceRegistry`, `Registration`, and `AutoServiceRegistration`. Discovery providers like Eureka or Consul provide implementations tailored to their registries.

Conceptually, the auto-registration process follows these steps:

1. The application initializes the `ApplicationContext`.
2. The discovery provider builds registration info for the current instance, such as service ID, host, port, and metadata.
3. The provider's auto-registration mechanism performs registration according to the application lifecycle.
4. The registry stores the instance so other clients can discover it.
5. When the application stops, the provider can deregister the instance or update status according to the integrated lifecycle.

~~~mermaid
flowchart TB
    A["Spring Boot application starts"]
    A --> B["Discovery provider is configured"]
    B --> C{"Auto-registration enabled?"}
    C -->|Yes| D["Create Registration for instance"]
    D --> E["ServiceRegistry.register()"]
    E --> F["Instance appears in registry"]
    C -->|No| G["Skip auto-registration step"]
    G --> H["Application can still use DiscoveryClient"]
    F --> I["Application runs"]
    H --> I
    I --> J["Shutdown"]
    J --> K["Provider handles lifecycle/deregister if registered"]
~~~

The diagram illustrates the general flow. Details of registration creation, health checks, heartbeats, deregistration, and status depend on the discovery provider and version in use.

### 2.1. ServiceRegistry Is Not the Same as AutoServiceRegistration

`ServiceRegistry` is the abstraction for registry operations, typically covering registration, deregistration, and reading/updating registration status. `AutoServiceRegistration` is the integration mechanism that lets the provider perform registration automatically following the application lifecycle.

Separating these two concepts clarifies the effect of the disable flag:

- Disabling auto-registration prevents Spring Cloud's automatic registration flow.
- The `ServiceRegistry` bean or API may still exist.
- Code that explicitly calls the registration API can still register an instance if the provider permits it.
- `DiscoveryClient` can still function to read instances of other services.

Do not treat the auto-registration disable property as a security or registry authorization control. If an application must never be allowed to register under any circumstances, enforce permissions at the registry and ensure no unintended manual registration code path exists.

## 3. Approach 1: Disabling via Configuration Properties

The most common approach is declaring the shared Spring Cloud Commons property in `application.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Full property name:

~~~text
spring.cloud.service-registry.auto-registration.enabled
~~~

When set to `false`, Spring Cloud does not execute the automatic registration flow controlled by the auto-registration configuration. The application can still initialize the discovery client and query the registry if the provider is configured for discovery.

### 3.1. Profile-Based Configuration

You can disable registration in local and test environments while keeping production behavior as needed:

`application.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

`application-test.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Under the `test` profile, profile-specific properties override the base value according to Spring Boot configuration rules. Check the active profile and effective value in `Environment` to avoid tests accidentally registering instances into a shared registry.

A batch or worker application can set the property to `false` in its own deployment profile if it does not need to advertise endpoints to other clients.

### 3.2. Configuring via Environment Variables or JVM Arguments

The property can be supplied from the deployment environment:

~~~bash
SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
~~~

Or via a JVM system property:

~~~bash
-Dspring.cloud.service-registry.auto-registration.enabled=false
~~~

This is useful when the same artifact is deployed across multiple environments with different registration policies. Avoid declaring conflicting values in YAML, environment variables, and JVM arguments without verifying which source takes precedence.

### 3.3. Why Are Properties a Good Choice for Deployment?

Properties fit well when controlling registration per environment without modifying source code:

- Can be placed in Config Data or managed configuration sources.
- Can be overridden by profiles, environment variables, or JVM arguments.
- Easy to audit in deployment configurations.
- Does not force applications to add annotations solely to toggle an operational flag.

For deployment-wide policies, external configuration is generally easier to manage. Ensure the value is supplied before auto-configuration creates the registration mechanism; do not assume modifying a property in a file at runtime will dynamically toggle lifecycle registration.

## 4. Approach 2: Disabling via Annotation

If you want to express the policy directly in application configuration, you can use the `autoRegister` attribute of `@EnableDiscoveryClient`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient(autoRegister = false)
public class ReportWorkerApplication {
}
~~~

`autoRegister = false` instructs the application not to automatically register its instance through the auto-registration mechanism activated by this annotation.

This approach works well when the decision is a fixed part of the application's architecture—for example, a worker that is always client-only and should never be advertised as a service endpoint.

### 4.1. Is the Annotation Required to Enable Discovery?

In many modern Spring Cloud setups, the discovery client is auto-configured whenever a matching provider dependency is present; applications do not necessarily need `@EnableDiscoveryClient` just to turn on discovery.

Still, the annotation retains the `autoRegister` attribute to express registration choices in configurations that support it. If a project already uses the annotation, you can set `autoRegister = false`. If you only need environment-based control, the shared configuration property is usually clearer.

Do not add the annotation to every application out of habit without checking how auto-configuration behaves in your release train.

### 4.2. Do Not Confuse This Annotation with Disabling Discovery

For instance, `@EnableDiscoveryClient(autoRegister = false)` still expresses the intent to use a discovery client while not registering the application itself. It differs from disabling the discovery client or removing the provider dependency.

If the application needs to look up `catalog-service`, verify that `DiscoveryClient` is still created and can retrieve the instance list after disabling auto-registration.

## 5. Choosing Between Properties and Annotations

Both approaches express the same goal but suit different management scenarios.

| Criterion | Property `enabled: false` | Annotation `autoRegister = false` |
| --- | --- | --- |
| Scope of control | Application/deployment configuration | Java configuration with annotation |
| Changing by profile | Convenient | Requires code config or import changes |
| Changing by environment | Supports env/JVM/config server | Inconvenient if policy varies across environments |
| Intent visibility in source | Lower | Explicit on configuration class |
| Best suited for | Environment-driven operational policy | Applications that never auto-register |
| Requires version verification | Yes | Yes, especially when using the annotation |

You can use the shared property as the default choice for deployments. Use the annotation when you want the policy tied to the application type and consistent across environments.

If using both, keep their values consistent and verify behavior with an integration test. Avoid setting the property to enable registration while the annotation requests no auto-registration, as the outcome may depend on the version and how auto-configuration is imported.

## 6. Disabling Auto-registration Does Not Disable Registry Lookup

This is the most important point to verify thoroughly after making the change.

A client-only application may still need:

- `DiscoveryClient.getInstances(serviceId)` to find instances.
- `DiscoveryClient.getServices()` to inspect known service IDs.
- Spring Cloud LoadBalancer to pick an instance.
- An `@LoadBalanced` HTTP client to make calls by service ID.

For example, a worker looking up the catalog:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    public CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
~~~

When auto-registration is disabled, the lookup code above can still work if the discovery provider and registry connection are properly configured. `report-worker` does not need to register itself in order to query `catalog-service`.

### 6.1. Do Not Misuse Discovery-Disabling Properties

Other properties can affect the discovery client or provider. For instance, disabling discovery completely can prevent the application from querying the registry at all; that is a different goal from merely not advertising its own instance.

With Eureka, the provider-specific property `eureka.client.register-with-eureka=false` controls whether the Eureka client registers itself. If it still needs to fetch registry entries, you must separately inspect `eureka.client.fetch-registry` and related settings. These are provider-specific configurations and do not universally replace Spring Cloud Commons' shared property across all registries.

Do not copy Eureka properties to Consul or another provider. Each implementation has its own namespace and semantics.

## 7. Manual Registration Remains a Separate Path

Disabling auto-registration is not a security-level "ban on registering." The application can still access the `ServiceRegistry` bean and invoke registration operations explicitly if code is written to do so.

Scenarios that may require manual registration:

- An application managing multiple logical instances.
- Registering only after completing a special initialization step.
- Registering a secondary endpoint only when a feature is enabled.
- Controlling deregistration timing directly during maintenance workflows.

When managing registration manually, the application takes responsibility for the entire lifecycle: constructing valid registration data, handling errors, preventing duplicates, deregistering on shutdown, and updating status when needed.

Do not use manual registration just to bypass the auto-registration property. If the goal is ensuring the application never appears in the registry, audit internal code, listeners, and other integrations that might perform registration.

## 8. What Happens to Previously Registered Instances?

`spring.cloud.service-registry.auto-registration.enabled=false` primarily governs auto-registration behavior during application configuration initialization. Changing the value to `false` while the JVM is running should not be treated as a command to deregister an instance that was already registered earlier.

If an instance already exists in the registry, determine how to remove it:

- Use a lifecycle/deregister API supported by the provider.
- Use registry administrative operations.
- Stop the instance via graceful shutdown so the provider handles deregistration if supported by the integration.
- Check lease/TTL/heartbeat settings to know when the registry automatically evicts disconnected instances.

Do not assume every provider deregisters immediately or shares the same shutdown semantics. Some registries rely on leases/TTLs, some have health statuses, and the time it takes for an instance to disappear from discovery results can depend on configuration.

### 8.1. When Converting a Service to Client-Only

If an application previously registered itself but no longer needs to be discoverable:

1. Identify existing instances in the registry.
2. Choose how to deregister or wait out provider lifecycle/leases per policy.
3. Disable auto-registration for subsequent startups.
4. Verify no manual registration code or listeners remain.
5. Confirm the discovery client still works if the application calls other services.
6. Verify other clients no longer depend on this application's endpoints.

Simply flipping the flag while leaving an old registration behind can cause other clients to keep sending traffic to an endpoint that is no longer serving.

## 9. Impact on Startup, Shutdown, and Health

Not registering automatically avoids advertising an unnecessary instance, but it does not replace other operational practices.

### 9.1. Startup

When auto-registration is enabled, the provider usually registers the instance through its integrated lifecycle. When disabled, that step is skipped. Other application startup steps—such as bean creation, opening an HTTP server, or connecting to the registry for discovery—can still take place.

If the application starts an HTTP server without registering, endpoints may still be reachable via direct addresses or an external load balancer. Disabling registration only affects the integrated registry; it does not automatically shut down network listeners.

### 9.2. Shutdown

If no registration was created by auto-registration, the provider has no corresponding instance to deregister through that path. However, other beans still need to stop and resources must close properly following the lifecycle.

If the application still registers manually, shutdown must deregister that registration. Do not rely on the auto-registration lifecycle to clean up a registration created by custom code unless that code is wired into the same lifecycle.

### 9.3. Health and Readiness

Disabling auto-registration does not disable health endpoints or readiness state. A registry health indicator, if present, can still check connectivity to the registry or dependencies. Application readiness must still reflect its ability to accept work according to deployment requirements.

A worker that does not register as a service may still need Kubernetes health/readiness probes. That is a workload management mechanism independent of Spring Cloud's service registry.

## 10. Testing Disabled Auto-registration

Good tests should verify two things at the same time:

1. The application does not send an instance registration request on startup.
2. The discovery client can still look up other services if required by the application.

### 10.1. Testing Configuration

For integration tests, pass the disable property in the test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.service-registry.auto-registration.enabled=false"
})
class AutoRegistrationPropertyTest {

    @Autowired
    Environment environment;

    @Test
    void autoRegistrationIsDisabled() {
        assertThat(environment.getProperty(
                "spring.cloud.service-registry.auto-registration.enabled",
                Boolean.class,
                true)).isFalse();
    }
}
~~~

This only verifies that the property is loaded. It does not prove the provider refrained from sending a registration request; behavioral integration testing is needed.

### 10.2. Behavioral Testing with a Fake Registry

You can use a mock server or fake provider to record incoming requests. When the context starts:

- Confirm no register request is sent for the application's instance.
- Confirm no heartbeat/lease renewal requests are sent for a registration created by this application.
- If discovery is still required, invoke the instance lookup API and confirm fetch/query requests are still sent.
- Close the context and verify no deregister request is sent for a registration that was never created.

How you observe requests depends on the protocol of Eureka, Consul, or the registry in use. Avoid asserting on a hardcoded HTTP endpoint when tests swap providers.

### 10.3. Test Matrix

| Auto-registration | Discovery query | Expected outcome |
| --- | --- | --- |
| Enabled | Enabled | Application instance is registered; can look up other services |
| Disabled | Enabled | Does not auto-register instance; can still look up other services |
| Enabled | Disabled or unconfigured | Registration depends on provider; do not assume queries work |
| Disabled | Disabled | Neither auto-registers nor performs discovery queries |
| Disabled | Enabled, with manual register | Automatic flow is off, yet manual code can still register |

This matrix helps catch confusion between registration and discovery directions, as well as between auto-registration and manual registration.

## 11. Common Mistakes and How to Avoid Them

1. **Disabling auto-registration and assuming discovery is also disabled:** verify the `DiscoveryClient` bean and registry query capability separately.
2. **Using provider-specific properties across every registry:** shared properties and provider-specific properties have different scopes.
3. **Assuming `false` automatically deregisters old instances:** inspect the registry and deregister via lifecycle/provider mechanisms.
4. **Adding the annotation while manual register code remains:** audit all other registration paths in the application.
5. **Using the annotation when policy must vary by profile:** consider configuration properties for environment-based management.
6. **Conflicting settings between annotation and property:** maintain one consistent policy and verify release train behavior.
7. **Skipping auto-configuration verification:** confirm that provider and auto-registration beans are actually created or omitted as intended.
8. **Assuming the HTTP server stops when not registering:** listeners may still run and accept direct traffic.
9. **Forgetting worker readiness:** workloads still need health/readiness probes even when absent from the registry.
10. **Testing only `Environment` properties:** add tests observing actual register/query requests on the provider side.

## 12. Selection and Implementation Workflow

When you want to disable auto-registration in a Spring Cloud application:

1. Determine whether the application needs to be discoverable by other services or only needs to call other services.
2. Inspect the active discovery provider and auto-registration mechanism.
3. Choose `spring.cloud.service-registry.auto-registration.enabled=false` if policy depends on the environment.
4. Choose `@EnableDiscoveryClient(autoRegister = false)` if policy is a fixed application decision and supported by your version.
5. Avoid configuring conflicting directions across annotations and properties.
6. Check provider-specific settings if using Eureka, Consul, or another registry.
7. Look for manual registration calls and listeners that might register the instance.
8. If an instance was already registered, execute deregistration or handle leases according to the provider.
9. Test that no register request is sent while discovery queries still work if needed.
10. Verify health, readiness, HTTP listeners, and shutdown still match the application's role.

**Key takeaway:** The property `spring.cloud.service-registry.auto-registration.enabled=false` and the annotation `@EnableDiscoveryClient(autoRegister = false)` control the application's automatic instance registration flow. They do not implicitly disable `DiscoveryClient`, LoadBalancer, or all manual registration operations. Evaluate instance publishing, service lookup, and registration lifecycle management separately to configure `ServiceRegistry` safely in **SPRING_CLOUD_CORE**.
