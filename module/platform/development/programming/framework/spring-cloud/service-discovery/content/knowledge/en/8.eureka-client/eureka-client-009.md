# When It Is Safe to Use `EurekaClient` in the Spring Lifecycle

## 1. Why Does Timing Matter When Calling EurekaClient?

`EurekaClient` is the Netflix Eureka client, configured and managed by Spring Cloud across the application lifecycle. It maintains connectivity with Eureka Server, registers the instance, sends heartbeats, and fetches the registry into a local cache. Therefore, the moment a Spring bean can have `EurekaClient` injected does not mean the registry already holds complete data for lookups.

A common mistake is calling `eurekaClient.getApplication(...)` directly inside a service's constructor or `@PostConstruct`. At that point, Spring may still be creating other beans, Eureka Client may not have completed its first registry fetch yet, or dependent services may not have finished registering. The outcome can be an empty list, a missing service, or unnecessary startup failures.

To use it safely, distinguish three milestones:

1. **Bean injected:** Spring has provided a reference to `EurekaClient`.
2. **Application context refreshed:** singleton beans have been instantiated and configured; however, startup tasks and registry updates may still be underway.
3. **Application ready to serve:** Spring Boot publishes `ApplicationReadyEvent` after context refresh and after `ApplicationRunner`/`CommandLineRunner` beans complete. This is usually the appropriate point to run discovery logic that depends on a started application.

Even `ApplicationReadyEvent` does not guarantee every instance in the cluster is already present in the registry. Eureka involves caching, heartbeats, fetch intervals, and replication; data may not have converged yet. Critical logic must still check results, apply bounded timeouts/retries, and handle cases where a service is not yet available.

## 2. How Does Spring Manage `EurekaClient`?

When you add the Spring Cloud Netflix Eureka Client starter, auto-configuration creates the required beans, including the Eureka Client and discovery adapters. The application should inject the `EurekaClient` interface via Spring-managed constructor or field injection; never instantiate a new client with `new` in business code.

```java
@Service
public class InventoryLookup {

    private final EurekaClient eurekaClient;

    public InventoryLookup(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }
}
```

Constructor injection here only accepts and stores the reference. That is the proper way to declare the dependency. What you must avoid is running network or discovery logic directly inside the constructor:

```java
// Avoid: calling the registry while the bean is still being constructed.
public InventoryLookup(EurekaClient eurekaClient) {
    this.eurekaClient = eurekaClient;
    Application app = eurekaClient.getApplication("PAYMENT-SERVICE");
}
```

Bean construction is not a signal that Eureka Client has fetched the registry or that the application has finished starting up. Keep constructors lightweight—only assign dependencies and initialize simple internal state.

## 3. Evaluating Spring Lifecycle Milestones

| Lifecycle Milestone | Can Inject `EurekaClient`? | Should Query the Registry? | Reason |
|---|---|---|---|
| Bean constructor | Yes, if bean is Spring-managed | No | Other dependencies and startup tasks may not be ready |
| `@PostConstruct` | Yes | Usually no | Only guarantees the current bean is initialized; context and registry may not be ready |
| `InitializingBean.afterPropertiesSet()` | Yes | Usually no | Still inside the bean initialization phase |
| `ContextRefreshedEvent` | Yes | Not yet reliable | Context is refreshed, but runners and application readiness may not be complete |
| `ApplicationRunner` / `CommandLineRunner` | Yes | Possible, but must handle unready cache | Runs after context refresh and before `ApplicationReadyEvent` |
| `ApplicationReadyEvent` | Yes | Usually appropriate | Spring Boot signals startup and runners are complete |
| Request handling after application is ready | Yes | Yes | Can query on demand, though data can still be stale or changing |
| Shutdown phase | Bean reference may still exist | Avoid starting new discovery work | Client/context may be closing and networking may no longer be available |

`ApplicationReadyEvent` is the right milestone for logic that needs to wait until application startup completes, though it is not a promise that the registry already contains every service. If an operation requires another service to be present, check the result and decide whether the application should wait with a timeout, run in degraded mode, or report not-ready status.

## 4. Why Is `@PostConstruct` Often Too Early?

`@PostConstruct` executes after the current bean's dependencies are injected, yet before the entire Spring Boot startup sequence finishes. Several factors make Eureka lookups unreliable at this stage:

- Eureka Client may still be initializing schedulers for heartbeats and registry fetches.
- The initial registry fetch may not have finished or may have no data yet.
- The target service the application wants to look up may not have registered yet, or updates may not have replicated to the server the client connects to.
- Other dependent beans may not have finished initializing or transitioned to a ready state.
- If a failed lookup throws an exception from `@PostConstruct`, the entire Spring context can fail to start even when that discovery check is not mandatory.

Example to avoid:

```java
@Component
public class StartupProbe {

    private final EurekaClient eurekaClient;

    public StartupProbe(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @PostConstruct
    public void init() {
        // Registry cache may not exist yet or the service may not have registered.
        Application application = eurekaClient.getApplication("PAYMENT-SERVICE");
        // Do not assume application is always non-null here.
    }
}
```

If you only need to validate local configuration, doing so during initialization is fine. However, looking up remote services or deciding business flow based on the registry should happen after the application is ready, with handling for missing instances.

## 5. Using `ApplicationReadyEvent` for Post-Startup Logic

Spring Boot emits `ApplicationReadyEvent` once the application has completed startup, including runners. You can use this event to perform an initial discovery check:

```java
import com.netflix.discovery.EurekaClient;
import com.netflix.discovery.shared.Application;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryStartupListener {

    private final EurekaClient eurekaClient;

    public DiscoveryStartupListener(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        Application application = eurekaClient.getApplication("PAYMENT-SERVICE");

        if (application == null || application.getInstances().isEmpty()) {
            // Registry has no instances yet: record it and let an appropriate
            // retry/health mechanism handle it rather than assuming the service exists.
            return;
        }

        application.getInstances().forEach(instance ->
                System.out.println(instance.getHostName() + ":" + instance.getPort()));
    }
}
```

The example uses `getApplication` to read an application from the data Eureka Client currently holds. Application names are typically stored in uppercase, such as `PAYMENT-SERVICE`; use the actual app name present in the registry. The `return` only illustrates handling when no instance is found; real systems should emit logs/metrics and define a clear retry or degraded-mode policy.

Do not turn the event listener into an infinite wait loop. If the application must wait for a critical service before accepting traffic, use a bounded readiness gate, retry with backoff, and expose observable status. If the service is only needed for an optional feature, let the application start and handle errors when that feature is invoked.

## 6. `ApplicationReadyEvent` Does Not Mean the Registry Has Converged

Eureka Client typically maintains a local cache. Methods such as `getApplication(...)` and `getApplications()` read the data the client currently holds; they should not be interpreted as synchronous queries guaranteed to return the latest cluster-wide state on every call.

Reasons a service may still be absent even after `ApplicationReadyEvent`:

1. The target service has not started or registered with Eureka Server yet.
2. The consumer's Eureka Client has not completed its registry fetch or is waiting for the next fetch interval.
3. Registry changes have not replicated to the peer the consumer is connected to.
4. The target service has an ineligible status or is not published under the app name the consumer queries.
5. Network, DNS, or Eureka Server issues caused the registry refresh to fail.

Therefore, do not treat `ApplicationReadyEvent` as sole proof that a specific remote service is ready. It describes the startup state of the current application, not the state of the entire microservice system.

### 6.1. Bounded Retries When a Service Is a Mandatory Dependency

If `payment-service` must locate `inventory-service` before serving traffic, you can build a dedicated readiness check step. Recommended rules:

- Configure a maximum wait deadline aligned with your startup SLO.
- Retry with pauses or exponential backoff; avoid hammering the registry continuously.
- Log and emit metrics for attempt counts, wait duration, and outcomes.
- When the deadline expires, decide explicitly whether to fail startup or enter a degraded state.
- Do not block startup threads indefinitely; ensure shutdown can still complete cleanly.

Example single-check helper:

```java
private boolean hasInventoryInstance() {
    Application application = eurekaClient.getApplication("INVENTORY-SERVICE");
    return application != null && !application.getInstances().isEmpty();
}
```

The method above only inspects the current cache. Retries should be orchestrated by a separate readiness/startup component with a time limit, rather than an unbounded loop inside a constructor or `@PostConstruct`.

## 7. When to Call EurekaClient in Requests or Background Tasks

Once the application is ready, you can use `EurekaClient` in business services if you genuinely need Eureka-specific data. Keep in mind, however, that registry data is dynamic:

- An instance can stop immediately after being returned.
- The cache may not reflect the latest registration or deregistration yet.
- A network partition can temporarily leave the registry stale.
- `InstanceInfo` does not prove the endpoint can still serve requests successfully at call time.

Consequently, do not look up an instance once at startup and cache its address forever. If you need to call a service by name, prefer Spring Cloud LoadBalancer with the `DiscoveryClient` abstraction to fetch instances and pick a target per request. This keeps service-calling logic less coupled to Eureka.

If you need Eureka-specific APIs such as `getApplication`, `getApplications`, VIP lookups, or reading `InstanceInfo`, isolate code depending on `EurekaClient` inside a dedicated adapter or service. Handle `null`, empty lists, and connection errors; never assume the registry always has data.

## 8. Safety During Shutdown

Spring Cloud manages the `EurekaClient` lifecycle. When the application context closes normally, the client is cleaned up and can send a deregistration request to Eureka Server. Do not create or close a separate Eureka Client inside a business bean, and do not manually call `shutdown()` on a Spring-managed bean.

If you need to drain an instance from traffic gracefully, transition the instance status to `OUT_OF_SERVICE` before closing the context, wait for consumers to refresh their registries and finish in-flight requests, and then let Spring shut down the application:

```java
applicationInfoManager.setInstanceStatus(InstanceInfo.InstanceStatus.OUT_OF_SERVICE);
```

This operation uses Eureka's `ApplicationInfoManager` to change the local status and send an update via the client mechanism. Design explicit drain times, timeouts, and handling when Eureka Server is unreachable. Transitioning status does not replace the application shutdown procedure.

Avoid starting new discovery tasks inside `@PreDestroy` or after the context has begun closing. At that stage, components may already be stopping, schedulers may be cancelled, and network connections may no longer be available. If your shutdown sequence needs to update status, coordinate it before closing the context using an explicit lifecycle/shutdown coordinator; then let Spring handle closing Eureka Client and deregistration.

## 9. Practices to Avoid

| Practice | Risk | Better Approach |
|---|---|---|
| Calling `getApplication()` in a constructor | Bean is created before startup completes | Keep constructors to storing dependencies; query after readiness |
| Calling the registry in `@PostConstruct` | Registry cache or target service may not be ready | Use `ApplicationReadyEvent` and validate results |
| Assuming `ApplicationReadyEvent` guarantees the latest registry | Event only means the current application finished startup | Handle caching, replication lag, and bounded retries |
| Infinite wait loop for a service at startup | Can hang startup and block shutdown | Use timeouts, backoff, and a readiness policy |
| Caching host/port retrieved at startup indefinitely | Instances can change or leave the registry | Look up/select instances per request via LoadBalancer |
| Instantiating `EurekaClient` with `new` | Creates a client outside Spring's lifecycle and schedulers | Inject the `EurekaClient` bean provided by auto-configuration |
| Calling `shutdown()` manually on a Spring bean | Can close the client while other beans still need it | Let Spring manage the lifecycle and context closure |
| Calling discovery in `@PreDestroy` | Client or network may already be shutting down | Coordinate status updates before context shutdown begins |

## 10. Usage Timing Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Spring as Spring ApplicationContext
    participant Bean as Business Bean
    participant Eureka as EurekaClient
    participant Server as Eureka Server

    Spring->>Bean: Create bean and constructor injection
    Note over Bean: Only store EurekaClient reference
    Spring->>Bean: @PostConstruct
    Note over Bean: Do not query registry at this stage
    Spring->>Eureka: Initialize client and background tasks
    Eureka->>Server: Register / heartbeat / fetch registry
    Spring->>Spring: Refresh context and run runners
    Spring-->>Bean: ApplicationReadyEvent
    Bean->>Eureka: getApplication / getApplications
    Eureka-->>Bean: Current cached data (may be empty/stale)
    Note over Bean: Check result; bounded retry if needed
    Spring->>Spring: Shutdown begins
    Note over Eureka,Server: Spring manages client shutdown and deregistration
```

The diagram shows the conceptual sequence. Eureka Client may register and fetch the registry via background tasks during startup; exact timing depends on version and configuration. `ApplicationReadyEvent` is a safer milestone for application logic, though it does not eliminate the asynchronous nature of the registry.

## 11. Checklist Before Using EurekaClient

Before adding logic that depends on `EurekaClient`, verify:

1. The bean is injected from Spring auto-configuration, not instantiated manually.
2. Constructors and `@PostConstruct` do not call the registry or wait on remote services.
3. Discovery logic runs after `ApplicationReadyEvent` or inside requests/tasks managed after readiness.
4. `getApplication`/`getApplications` results may be null, empty, or stale; code handles those cases.
5. For mandatory dependencies, the readiness policy defines timeouts, retry/backoff, and clear failure states.
6. Instance addresses fetched at startup are never held as immutable endpoints.
7. Prefer `DiscoveryClient` and Spring Cloud LoadBalancer for general discovery/load-balancing needs; use `EurekaClient` only when Eureka-specific APIs are required.
8. Let Spring manage shutdown and deregistration; coordinate draining or `OUT_OF_SERVICE` before closing the context.

## 12. Conclusion

`EurekaClient` can be injected as soon as Spring constructs beans, but registry lookups should be deferred until the application finishes starting up—typically from `ApplicationReadyEvent` or in post-readiness execution paths. Avoid calling discovery inside constructors or `@PostConstruct` because the registry cache, dependent services, and application lifecycle may not be ready.

Even after `ApplicationReadyEvent`, the registry may still be converging. Always validate returned data, apply bounded retries when needed, and handle temporarily unavailable services. During shutdown, let Spring manage Eureka Client; if you need to drain traffic, update instance status before closing the context.
