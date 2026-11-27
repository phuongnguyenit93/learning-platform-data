# Auto-registration and Application Lifecycle

In a Spring Cloud application, the service registry needs to know each instance's address so clients can find and call the service. Spring Cloud Commons standardizes this operation via `ServiceRegistry` and `Registration`, and provides an **auto-registration** mechanism so providers register the application instance during startup and deregister it when the application stops.

Auto-registration links the lifecycle of the `ApplicationContext` with the lifecycle of a service instance in the registry. Once the web server has initialized and obtained an actual port, the discovery implementation typically builds the registration info and sends it to the registry. When the context closes, the implementation typically deregisters the instance. Exact timing and execution details depend on the provider, yet the shared abstractions help applications understand the core steps and extend behavior when needed.

This lesson belongs to the **ServiceRegistry** chapter of the **SPRING_CLOUD_CORE** module, focusing on Spring Cloud Commons, service discovery, service registration, Spring Boot lifecycle, instance status management, and testing startup and shutdown behavior.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the roles of `ServiceRegistry`, `Registration`, and `AutoServiceRegistration`.
2. Distinguish automatic registration from manual registration.
3. Describe the timing of registration in a Spring Boot application lifecycle.
4. Understand the two events `InstancePreRegisteredEvent` and `InstanceRegisteredEvent`.
5. Configure enabling/disabling auto-registration and understand related properties.
6. Explain management service registration when the management port is separate.
7. Describe the deregistration process when the context closes.
8. Distinguish instance status from registration and deregistration.
9. Use the `/serviceregistry` endpoint to read or update status according to provider capabilities.
10. Test startup, registration, shutdown, registry errors, and multi-replica behavior.

## 2. Components of Service Registration

### 2.1. `ServiceRegistry`

`ServiceRegistry` is the abstraction for interacting with the registry. Typical methods include:

- `register(registration)`: registers an instance.
- `deregister(registration)`: deregisters an instance.
- `setStatus(registration, status)`: updates status if supported by the provider.
- `getStatus(registration)`: reads the status returned by the provider.
- `close()`: closes registry client resources when required by the implementation.

The interface resides in package:

~~~java
org.springframework.cloud.client.serviceregistry.ServiceRegistry
~~~

`ServiceRegistry` is a shared contract; each provider supplies its own implementation. For example:

| Provider | Registration type | Registry implementation |
| --- | --- | --- |
| Eureka | `EurekaRegistration` | `EurekaServiceRegistry` |
| Consul | `ConsulRegistration` | `ConsulServiceRegistry` |
| ZooKeeper | `ZookeeperRegistration` | `ZookeeperServiceRegistry` |

When calling the generic API, pass the exact registration type required by the provider implementation. You cannot take an arbitrary `Registration` and assume every registry understands the same metadata or updates status the same way.

### 2.2. `Registration`

`Registration` is a marker interface extending `ServiceInstance`. It describes the instance to be placed into the registry, typically including:

- Service ID or logical name.
- Instance ID if used by the provider.
- Host and port.
- URI or security scheme.
- Metadata such as zone, version, region, or routing information.

Conceptual example:

~~~text
serviceId: orders-service
instanceId: orders-service-7f9c
host: orders-7f9c.internal
port: 8080
scheme: http
metadata:
  zone: ap-southeast-1a
  version: v2
~~~

This is illustrative data. How a provider constructs `Registration`, selects network addresses, and represents metadata can vary.

### 2.3. `AutoServiceRegistration`

`AutoServiceRegistration` describes the ability to automatically register an instance according to the application's lifecycle. A provider typically supplies an implementation combined with `ServiceRegistry` to automatically register and deregister the instance.

Applications use this abstraction to receive automatic behavior; you do not need to call `register()` manually on every startup if the provider already configures auto-registration.

### 2.4. Role of DiscoveryClient

Distinguish the two directions:

| Abstraction | Responsibility |
| --- | --- |
| `DiscoveryClient` / `ReactiveDiscoveryClient` | Reads service and instance lists from discovery |
| `ServiceRegistry` | Writes, deletes, and updates registration status |
| `Registration` | Describes the registered instance |
| `AutoServiceRegistration` | Binds registration operations to the application lifecycle |

An application can use `DiscoveryClient` to find other services without registering itself. Conversely, a component can register an instance without necessarily using discovery to call downstream services.

## 3. When Does Auto-registration Run?

### 3.1. Provider Is on the Classpath

When a compatible discovery provider dependency is on the runtime classpath, Spring Boot auto-configuration can create the corresponding discovery and service registry beans.

For example, an application using Eureka can add the Eureka Client starter; an application using Consul can add the Consul Discovery starter. Spring Cloud Commons defines the shared contract, while the starter/provider is responsible for configuring connectivity and registration.

`@EnableDiscoveryClient` is no longer mandatory in current Spring Cloud versions when a compatible implementation is already on the classpath. The annotation still exists and can be used to adjust behavior, such as `autoRegister=false`. Check your project's release train when working with older versions.

### 3.2. Instance Address Must Be Determined

Registration needs an address reachable by other clients. This information can be derived from:

- `spring.application.name`.
- Web server port.
- Hostname or network address chosen by the provider.
- Secure port or scheme configuration.
- Provider-specific metadata and properties.

Do not assume the registered address is always `localhost`. In containers, VMs, or Kubernetes, the address advertised by the registry must be reachable from the consumer's network.

### 3.3. Common Flow with Web Applications

A common implementation based on `AbstractAutoServiceRegistration` listens for `WebServerInitializedEvent`. Once the embedded web server finishes initializing, the event provides the actual port; the implementation then starts registration.

~~~mermaid
sequenceDiagram
    participant Boot as Spring Boot
    participant Web as Embedded Web Server
    participant Auto as AutoServiceRegistration
    participant Registry as ServiceRegistry
    participant Store as Remote Registry

    Boot->>Web: Initialize web server
    Web-->>Auto: WebServerInitializedEvent
    Auto->>Auto: Check auto-registration
    Auto->>Auto: Build Registration with actual port
    Auto->>Registry: register(Registration)
    Registry->>Store: Write instance
    Store-->>Registry: Registration result
    Registry-->>Auto: Complete
~~~

Not every provider must use this exact base class or the same event. This is a common flow in implementations using `AbstractAutoServiceRegistration`; a provider may have its own initialization mechanism, especially for non-web applications or registries that do not depend on a web server.

### 3.4. Why Wait for the Web Server to Initialize?

If registration happens before the web server has an actual port, the application might publish the wrong port, especially when using `server.port=0` to let the operating system assign a dynamic port.

Waiting for `WebServerInitializedEvent` lets the implementation capture the port bound by the server. For applications without a web server, the provider must have its own strategy to determine the address and registration timing; do not assume the web-event flow applies to all application types.

## 4. Auto-registration Sequence and Lifecycle Hooks

In implementations based on `AbstractAutoServiceRegistration`, the startup process typically follows these steps:

1. Receive `WebServerInitializedEvent` from the application's web server.
2. Store the actual port and call `start()`.
3. Check whether the provider has registration enabled.
4. Check running state to prevent duplicate registration.
5. Publish `InstancePreRegisteredEvent`.
6. Execute `RegistrationLifecycle` hooks before registration.
7. Call `ServiceRegistry.register()` for the main instance.
8. Execute hooks after registering the main instance.
9. If the management server uses a separate port and registration is allowed, register the management instance as well.
10. Publish `InstanceRegisteredEvent`.
11. Mark auto-registration as running.

~~~mermaid
flowchart TD
    A[WebServerInitializedEvent] --> B{Auto-registration enabled?}
    B -->|No| X[Do not register]
    B -->|Yes| C{Already running?}
    C -->|Yes| Y[Skip duplicate registration]
    C -->|No| D[InstancePreRegisteredEvent]
    D --> E[RegistrationLifecycle before]
    E --> F[ServiceRegistry.register]
    F --> G[RegistrationLifecycle after]
    G --> H{Separate management port?}
    H -->|Yes and enabled| I[Register management instance]
    H -->|No| J[Complete]
    I --> J
    J --> K[InstanceRegisteredEvent]
    K --> L[Mark running]
~~~

This order describes the current base implementation. A specific provider may add steps, alter conditions, or handle management registration in its own way. When depending on lifecycle details, verify the implementation and documentation for the exact version in use.

### 4.1. `InstancePreRegisteredEvent`

This event is published before the main registration call. Listeners can use it to:

- Log the start of registration.
- Attach additional metadata if the registration object allows it.
- Validate deployment preconditions.
- Create a correlation ID for operational logs.

Do not use a listener to perform a second registration for the same instance; doing so can create duplicate registrations or leave registry state inconsistent.

### 4.2. `InstanceRegisteredEvent`

This event is published after auto-registration completes in the corresponding implementation flow. Listeners can:

- Record that the instance has been registered.
- Emit a metric or audit event.
- Trigger a post-registration dependency check.
- Notify an internal component.

The event indicates that the registration step has been executed in the lifecycle. It does not prove every consumer already sees the instance immediately, because the registry may have synchronization delays or caches.

### 4.3. Registering Listeners

Example using `@EventListener`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.cloud.client.discovery.event.InstancePreRegisteredEvent;
import org.springframework.cloud.client.discovery.event.InstanceRegisteredEvent;

@Component
public class RegistrationEventLogger {

    @EventListener
    public void beforeRegistration(InstancePreRegisteredEvent event) {
        // Record when registration starts.
    }

    @EventListener
    public void afterRegistration(InstanceRegisteredEvent<?> event) {
        // Record that registration completed according to the provider.
    }
}
~~~

This example focuses on listener placement. Avoid making another synchronous registry call from a listener without a specific purpose. For operations that may fail or require retries, design a dedicated service with timeouts, idempotency, and error observability.

### 4.4. `RegistrationLifecycle` Hooks

Spring Cloud Commons provides the `RegistrationLifecycle` extension point to run logic before and after local service registration and deregistration. Common hooks include:

| Hook | Timing |
| --- | --- |
| `postProcessBeforeStartRegister(registration)` | Before registering the instance |
| `postProcessAfterStartRegister(registration)` | After registering the instance |
| `postProcessBeforeStopRegister(registration)` | Before deregistering |
| `postProcessAfterStopRegister(registration)` | After deregistering |

There is a similar set of hooks in `RegistrationManagementLifecycle` for management registration.

These hooks are useful when the provider or application needs to add metadata, record audits, or coordinate tasks before/after a registry operation. They do not replace `ServiceRegistry`; write/delete operations are still performed by the registry implementation.

## 5. Enabling and Disabling Auto-registration

### 5.1. Defaults

According to current Spring Cloud Commons configuration properties:

| Property | Default | Meaning |
| --- | --- | --- |
| `spring.cloud.service-registry.auto-registration.enabled` | `true` | Enable/disable auto-registration |
| `spring.cloud.service-registry.auto-registration.fail-fast` | `false` | Whether to fail startup if no `AutoServiceRegistration` is present |
| `spring.cloud.service-registry.auto-registration.register-management` | `true` | Allow registering the management service when applicable |

These defaults describe Commons configuration. A provider may still have its own properties affecting registration, such as toggling the client, selecting ports, or controlling registration by environment.

### 5.2. Disabling via application.yml

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

This configuration prevents the common auto-registration mechanism from running. The application can still use `DiscoveryClient` to read instances of other services if the discovery client is enabled and supported by the provider.

Disabling auto-registration does not mean disabling all of discovery. If you want to disable discovery completely, that is a separate property, such as `spring.cloud.discovery.enabled=false`.

### 5.3. Disabling via `@EnableDiscoveryClient`

You can use:

~~~java
@EnableDiscoveryClient(autoRegister = false)
@SpringBootApplication
public class OrdersApplication {
}
~~~

In current versions, the annotation is not required just to activate discovery when a provider is already on the classpath. However, `autoRegister=false` remains an explicit way to express disabling this behavior in annotation configuration.

Prefer a single, clear, consistent configuration source. Avoid setting conflicting values between annotations and properties that make operational intent hard to determine.

### 5.4. When Should Auto-registration Be Disabled?

Some valid scenarios:

- The application only reads discovery data and does not want to register itself.
- Registration is controlled by an external deployment process.
- An administrative process shares discovery dependencies but is not a service endpoint.
- Integration tests need manual control over registration.
- A service should only enter the registry after completing a custom warm-up or readiness step.

When disabling auto-registration, there must be another way for the instance to appear in the registry if consumers still need to find it. Do not disable registration and expect the registry to know the application's address automatically.

## 6. `fail-fast` and Startup Error Handling

The property:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        fail-fast: true
~~~

controls behavior when no `AutoServiceRegistration` is present according to the Commons configuration properties description. The default value is `false`.

Distinguish the following cases:

- **Missing AutoServiceRegistration bean:** the application may not have an auto-registration mechanism configured.
- **Bean exists but registry is unreachable:** the provider makes the network call and handles errors according to its implementation, timeouts, and policy.
- **Registry accepts the request but rejects registration:** possibly due to credentials, service ID, metadata, or policy.
- **Registration succeeds but clients do not see the instance yet:** possibly due to sync latency, caching, or querying the wrong namespace.

Do not interpret `fail-fast` as a universal guarantee that every registry network error will be handled identically. To fail startup when a specific provider cannot register, inspect that provider's error policy and write an integration test with an unavailable registry.

### 6.1. Deciding Whether to Fail Startup or Keep Running

| Context | Potentially suitable policy |
| --- | --- |
| Service must be discoverable immediately upon running | Consider failing startup when registration fails |
| Background job not receiving traffic via discovery | May allow startup with a warning |
| Registry temporarily loses connectivity | Bounded retries, backoff, and appropriate readiness |
| Invalid credentials or invalid service ID | Usually needs a clear error rather than infinite retries |
| Local tests without a registry | Use SimpleDiscoveryClient or disable auto-registration per test goal |

Do not let a service report readiness `UP` if the architecture requires it to be registered before receiving traffic while registration has not succeeded.

## 7. Registering the Management Service

### 7.1. Separate Management Port

Spring Boot can run management endpoints on a separate port via `management.server.port`. When the management port differs from the application port, some providers can register an additional management instance so operational tools can find management endpoints.

Example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
~~~

In Spring Cloud's base implementation, `spring.cloud.service-registry.auto-registration.register-management` defaults to `true`. Management registration is only performed when a separate management port is configured and the provider supports creating a management registration.

### 7.2. Disabling Management Registration

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        register-management: false
~~~

This is useful if management endpoints should only be reachable over a private network and must not appear in the general service registry.

Disabling management registration does not disable Actuator itself. It only affects publishing the management endpoint as a separate registration according to provider support.

### 7.3. Why Separate the Management Address?

If the management port is registered as a separate instance, consumers can distinguish service endpoints from management endpoints. However, publishing the management port also expands the discovery surface. Register the management service only when you have a valid use case and access policy; protect Actuator with authentication, authorization, and network restrictions.

## 8. Deregistration on Application Shutdown

### 8.1. Shutdown Lifecycle

In implementations using `AbstractAutoServiceRegistration`, the destruction method is bound to `@PreDestroy`. When Spring closes the context, the implementation calls `stop()` to deregister.

Common flow:

1. `ApplicationContext` begins closing.
2. `AbstractAutoServiceRegistration.destroy()` calls `stop()`.
3. Verify the instance is marked running and registration is still enabled.
4. Run `postProcessBeforeStopRegister` hooks.
5. Call `ServiceRegistry.deregister()` for the main instance.
6. Run `postProcessAfterStopRegister` hooks.
7. If a management service was registered, deregister it as well.
8. Close the registry client if required by the implementation.

~~~mermaid
sequenceDiagram
    participant Context as ApplicationContext
    participant Auto as AutoServiceRegistration
    participant Registry as ServiceRegistry
    participant Store as Remote Registry

    Context->>Auto: @PreDestroy / destroy()
    Auto->>Auto: stop()
    Auto->>Auto: RegistrationLifecycle before stop
    Auto->>Registry: deregister(Registration)
    Registry->>Store: Remove or mark instance
    Store-->>Registry: Result
    Auto->>Auto: RegistrationLifecycle after stop
    Auto->>Registry: deregister management (if any)
    Auto->>Registry: close()
~~~

This is the base implementation flow, not a promise that every provider uses the exact same internal order. Providers may use leases, heartbeats, or other cleanup mechanisms.

### 8.2. Graceful Shutdown and Deregistration

Deregister makes the registry stop advertising the instance according to provider semantics. It does not by itself guarantee that all in-flight requests have completed.

In production, coordinate the following steps:

1. Transition the instance to stop accepting new traffic or set readiness `DOWN`.
2. Give the load balancer/router time to stop selecting the instance.
3. Drain in-flight requests.
4. Close the `ApplicationContext`.
5. Let the provider deregister the instance.
6. Verify the registry has updated.

If the process is forcibly killed, loses power, or the container is terminated before callbacks run, deregistration may not execute. The registry needs TTLs, leases, heartbeats, or expiration mechanisms to clean up stale instances. Detection time depends on the provider and configuration.

### 8.3. Deregister Does Not Mean Deleting History

Some registries retain instance history, status, or events after it is no longer active. `deregister()` usually stops the instance from being advertised as an active registration, while retention and audit history depend on the provider.

Do not assume data has completely vanished from registry storage just because `deregister()` returned.

## 9. Instance Status and the ServiceRegistry Actuator Endpoint

### 9.1. Status Differs from Registration

An instance can be registered yet marked `OUT_OF_SERVICE` or `DOWN`. This status can stop the instance from being selected while keeping its registration intact for maintenance or investigation.

| Operation | Meaning |
| --- | --- |
| `register()` | Creates or publishes a registration |
| `setStatus()` | Changes the registration's status if supported by the provider |
| `deregister()` | Removes the registration |
| Heartbeat/lease | Maintains presence according to the provider mechanism |

Do not use status updates as a universal substitute for deregister. How LoadBalancer or the registry handles status depends on the provider.

### 9.2. The `/serviceregistry` Endpoint

Spring Cloud Commons provides the `/serviceregistry` Actuator endpoint if a `Registration` bean exists and the endpoint is configured/exposed.

- `GET /actuator/serviceregistry`: reads the current registration status.
- `POST /actuator/serviceregistry`: updates the status with JSON containing a `status` field.

Example:

~~~http
POST /actuator/serviceregistry
Content-Type: application/json

{
  "status": "OUT_OF_SERVICE"
}
~~~

Valid values depend on the provider. Documentation notes Eureka can use `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. Do not assume Consul, ZooKeeper, or other providers share the same semantics.

### 9.3. Exposure and Security

To access the endpoint over HTTP, you need Actuator, an endpoint implementation, proper exposure, and call permissions. Example exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,serviceregistry
~~~

An endpoint that mutates registration status is an administrative API. Restrict network access, require authentication, and enforce authorization; never expose it publicly. If Spring Security is customized, verify `SecurityFilterChain` permits write operations only for operator roles.

## 10. Manual Registration Using ServiceRegistry

Auto-registration fits standard services. Some use cases require conditional registration or a custom workflow. Spring Cloud Commons lets you call `ServiceRegistry` directly.

### 10.1. Registration Is Provider-Dependent

Each provider has a concrete registration type. For example, with ZooKeeper, provider docs illustrate creating a registration via a builder and calling the registry:

~~~java
ZookeeperRegistration registration =
        ServiceInstanceRegistration.builder()
                .defaultUriSpec()
                .address("inventory.internal")
                .port(8080)
                .name("/services/inventory-service")
                .build();

serviceRegistry.register(registration);
~~~

This snippet is an example for Spring Cloud Zookeeper; the classes and registration construction do not carry over to Eureka or Consul. Use the builder/registration type of the provider in use.

### 10.2. Disable Auto-registration When Managing Manually

If the application calls `register()` itself in a custom workflow, you typically need to disable auto-registration to avoid duplicate registrations:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Then, the application must clearly define:

- When to construct the registration.
- Under what conditions registration is permitted.
- When to retry if the registry temporarily errors.
- How to guarantee register idempotency.
- Who is responsible for deregistering.
- What happens when the process terminates abnormally.

Do not disable auto-registration and forget to implement a replacement workflow; the service will never appear in the registry.

### 10.3. Idempotency and Duplicate Registrations

Registries may handle repeated registrations in their own way, such as updating an entry with the same instance ID or creating a second entry. Do not rely on a universal assumption here.

Design with a stable instance ID across the process lifetime, apply bounded retries, and avoid creating multiple registrations for the same process. When scaling across multiple replicas, each replica must have a distinct identifier.

## 11. `SimpleDiscoveryClient` Is Not a Dynamic Service Registry

`SimpleDiscoveryClient` can read a static list of instances from configuration:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-1.internal:8080
              - uri: http://inventory-2.internal:8080
~~~

This approach fits local development, testing, or environments with static endpoints. It provides data for `DiscoveryClient` lookups, but it is not a registry server and does not register the local application with a remote registry system.

Therefore, having a `DiscoveryClient` bean does not imply having a `ServiceRegistry` or `AutoServiceRegistration` bean. Check the concrete dependencies and implementations.

## 12. Testing Auto-registration and Lifecycle

### 12.1. Unit Testing Listeners

You can test event listeners by publishing events in a test context or mocking the event publisher. The goal is to confirm that observation/audit logic does not perform duplicate registrations.

Listeners should be lightweight, avoid long network calls, and not break startup if a non-essential side task fails.

### 12.2. Integration Testing with a Real Registry

An integration test can use Testcontainers or a provider test environment:

1. Start the registry.
2. Launch the application with the provider starter and auto-registration enabled.
3. Wait for the instance to appear under the service ID.
4. Verify host, port, scheme, and metadata.
5. Call `GET /actuator/serviceregistry` if the endpoint is exposed.
6. Close the context.
7. Wait for the instance to be deregistered or transition to the provider-defined state.
8. Verify the registry no longer returns an active instance.

Do not rely solely on fixed `Thread.sleep()` calls as proof. Use polling with a timeout to wait for the registry to reach the desired state, since registries may synchronize asynchronously.

### 12.3. Testing Disabled Auto-registration

Set:

~~~properties
spring.cloud.service-registry.auto-registration.enabled=false
~~~

Verify:

- The instance is not registered automatically.
- `InstancePreRegisteredEvent` and `InstanceRegisteredEvent` are not published by auto-registration.
- The discovery client reading other services still works unless disabled separately.
- Any manual registration workflow still runs properly.

### 12.4. Testing Registry Failures

Include scenarios for:

- Registry unavailable at startup.
- Invalid credentials.
- Registry disconnects while the application is running.
- Registration rejected due to service ID or metadata.
- Registry is slow or times out.
- Process killed before deregistering.
- Instance restarts quickly and re-registers under the same service ID.
- Two replicas accidentally use the same instance ID.

Record behavior per provider and actual fail-fast/retry policy. Do not assume all providers share the same timeouts, retries, or stale-instance cleanup timing.

## 13. Operating Multiple Instances

### 13.1. Each Replica Is a Separate Registration

If a service has three replicas, the registry typically holds three separate registrations:

~~~text
orders-service
  ├── orders-7f9c -> 10.0.1.12:8080
  ├── orders-1ab3 -> 10.0.1.13:8080
  └── orders-4de8 -> 10.0.1.14:8080
~~~

Each instance needs an appropriate address and instance ID. Never share the same static instance ID across replicas if the provider requires unique IDs.

### 13.2. Rolling Deployments

During a rolling deployment, old and new instances may coexist temporarily:

1. New instance starts and registers.
2. Health/readiness meets requirements.
3. Traffic shifts to the new instance.
4. Old instance stops accepting traffic.
5. Old instance deregisters during shutdown.
6. Registry converges on the new instance list.

If registration happens too early before the service is truly ready, clients may select an instance that cannot serve requests yet. Coordinate registration with readiness, health checks, and the load balancer.

### 13.3. Stale Registrations

When a process is terminated with `kill -9` or a node loses connectivity, the deregister callback may fail to run. The registry may keep displaying the instance until TTL/lease/heartbeat expires or health checks mark the instance unhealthy.

Therefore, configure dead-instance detection intervals to match availability goals and avoid overly long TTLs that cause clients to keep calling dead addresses.

## 14. Security and Reliability

Registration metadata is often visible to many services that have discovery read permissions. Do not put secrets, tokens, passwords, or personal data into metadata.

Controls to enforce:

- TLS between applications and the registry.
- Dedicated credentials per workload.
- Least-privilege register/deregister/read permissions.
- Prevention of service ID and instance ID spoofing.
- Non-public management endpoints.
- Metadata free of secrets.
- Bounded retries with backoff.
- Timeouts on registry operations.
- Logs with correlation IDs and without credentials.
- Auditing of instance status changes.
- Verification that advertised network addresses are reachable from consumers.

When the registry is unavailable, do not retry infinitely at high frequency. A retry storm can overload the registry right when the system needs to recover.

## 15. Common Issues

| Symptom | Possible cause | Investigation path |
| --- | --- | --- |
| Service does not appear in registry | Missing provider, auto-registration disabled, or registration error | Check starter, auto-registration property, and logs |
| Instance registers wrong port | Registration built before actual port was assigned or wrong provider config | Check `WebServerInitializedEvent`, server port, and provider settings |
| Registry displays localhost | Advertised host/address unsuitable for container environment | Check hostname, network interface, and advertised address |
| Two replicas overwrite each other | Instance ID is not unique | Check how the provider generates instance IDs |
| `InstanceRegisteredEvent` never fires | Auto-registration disabled or registration incomplete | Check properties and lifecycle logs |
| Pre-register event fires but after-event does not | `register` call failed or lifecycle stopped mid-way | Check exceptions from the registry and hooks |
| Old instance persists after shutdown | Callback did not run or registry updates slowly | Check deregister, lease, heartbeat, and TTL |
| Management endpoint is not registered | No separate management port or `register-management=false` | Check management port and property |
| `/actuator/serviceregistry` returns 404 | Missing Actuator/Registration bean or not exposed | Check dependencies, auto-configuration, and exposure |
| POST status rejects value | Status invalid for provider or missing write permissions | Check provider docs and security |
| Service appears in discovery but calls fail | Registration only reflects address; instance may not be ready or network fails | Check readiness, port, health, and network |
| Startup does not fail despite registry error | `fail-fast` does not control provider errors as expected or provider allows continuation | Check implementation and integration tests |

## 16. Lifecycle-Based Troubleshooting Workflow

When an instance does not appear in the registry, check in order:

1. Confirm the provider starter is on the runtime classpath.
2. Confirm discovery and auto-registration are not disabled.
3. Check that the `AutoServiceRegistration` bean exists.
4. Check `spring.application.name`, host, port, and instance ID.
5. Confirm the web server emitted the initialization event if the provider uses that flow.
6. Check `InstancePreRegisteredEvent` and logs before `register`.
7. Inspect the registration request and registry response/errors.
8. Check `InstanceRegisteredEvent`.
9. Query the registry directly by service ID.
10. On shutdown, check deregister and TTL/lease if instances linger.

If using the `/serviceregistry` endpoint, check the registration status within the context. To verify actual stored data, query the registry provider or use its administrative API.

## 17. Hands-On Exercises

**Exercise 1 — Basic auto-registration.** Create a Spring Boot application with a discovery provider. Start the application and confirm service ID, instance ID, host, and port appear in the registry.

**Exercise 2 — Observing lifecycle events.** Create listeners for `InstancePreRegisteredEvent` and `InstanceRegisteredEvent`. Log timing, service name, and registration outcome; do not perform a second registration in the listener.

**Exercise 3 — Disabling auto-registration.** Set `spring.cloud.service-registry.auto-registration.enabled=false`. Confirm the application can still read other services via `DiscoveryClient` without registering itself.

**Exercise 4 — Management port.** Set `management.server.port` different from `server.port`. Check whether the provider registers a management instance. Then set `register-management=false` and compare.

**Exercise 5 — Deregistration.** Close the `ApplicationContext` normally. Observe stop hooks, the deregister operation, and registry state. Then forcibly kill the process and check TTL/lease behavior.

**Exercise 6 — Fail-fast.** Run the application when the provider or registry is unavailable. Compare `fail-fast=false` and `true`; pinpoint which errors belong to the Commons property and which belong to the provider.

**Exercise 7 — Service status.** Call `GET /actuator/serviceregistry`, then `POST OUT_OF_SERVICE` if supported by the provider. Verify whether LoadBalancer or the registry stops selecting the instance.

**Exercise 8 — Manual registration.** Disable auto-registration and create a registration manually using the provider API. Design retries, instance ID, deregister, and tests for duplicate registration cases.

**Exercise 9 — Rolling deployment.** Run two replicas. Bring up the new replica first, verify readiness, shift traffic, then stop the old replica. Confirm the registry always has at least one serving instance.

## 18. Key Takeaways and Reference Sources

- `ServiceRegistry` provides the register, deregister, and status update contract; `Registration` describes the instance to register.
- Auto-registration is typically enabled by default when a compatible provider is present and configuration does not disable it.
- `@EnableDiscoveryClient` is no longer required in current versions if a provider implementation is on the classpath.
- `InstancePreRegisteredEvent` is published before the `register` call; `InstanceRegisteredEvent` is published after auto-registration. Neither event is published when auto-registration is disabled via the shared property.
- Implementations using `AbstractAutoServiceRegistration` typically wait for `WebServerInitializedEvent` to obtain the actual port.
- `register-management` defaults to allowing management instance registration when a separate management port is configured and supported by the provider.
- When the context closes, common implementations call `stop()` and deregister the instance; forcibly killed processes rely on TTL/lease/heartbeat to clean up stale registrations.
- `/actuator/serviceregistry` reads or updates status according to provider support; status values are not uniform across registries.
- Disabling auto-registration does not disable the discovery read API.
- Test startup, shutdown, registry outages, multiple replicas, and stale registration cases.

Official sources to cross-check against your project's Spring Cloud/Spring Boot version:

1. [Spring Cloud Commons – Common Abstractions: ServiceRegistry and Auto-Registration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Cloud Commons Javadoc – `ServiceRegistry`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/ServiceRegistry.html)
4. [Spring Cloud Commons Javadoc – `Registration`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/Registration.html)
5. [Spring Cloud Commons Javadoc – `AbstractAutoServiceRegistration`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.html)
6. [Spring Cloud Commons Javadoc – `RegistrationLifecycle`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/RegistrationLifecycle.html)
7. [Spring Cloud Zookeeper – Service Registry](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
8. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
