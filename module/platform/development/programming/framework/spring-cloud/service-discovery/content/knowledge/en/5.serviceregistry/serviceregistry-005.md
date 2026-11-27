# Pre- and Post-Registration Events for Service Instances

## 1. Why Monitor Registration Events?

In Spring Cloud Service Discovery, an application typically registers its own instance with a registry at startup. The registry may be Eureka, Consul, or another discovery system. Registration information usually includes service ID, host, port, status, and metadata such as application version.

The registration process is an important milestone in the application lifecycle. Before sending information to the registry, the system may need to log details, validate instance data, or initialize metrics. After registration completes, the application can record status, emit monitoring signals, or trigger an auxiliary task.

Spring Cloud Commons provides application events to observe these two moments:

- **InstancePreRegisteredEvent:** published before the auto-registration mechanism registers the instance.
- **InstanceRegisteredEvent:** published after the auto-registration mechanism's registration operation completes.

These events allow other components in the application to react to the registration lifecycle without embedding monitoring logic directly into Eureka or Consul configuration classes.

## 2. How Does Instance Registration Work in Spring Cloud?

Spring Cloud defines common abstractions for working with a registry:

- **Registration:** describes an instance to be registered, typically providing service ID, host, port, URI, and metadata.
- **ServiceRegistry:** provides registration management operations such as register, deregister, getStatus, and setStatus.
- **DiscoveryClient:** provides a way to look up service IDs and their corresponding instance lists.

Each discovery provider implements these abstractions. For example, Eureka provides an implementation integrated with Eureka Client; Consul provides an implementation that communicates with a Consul agent/server.

With the auto-registration mechanism, Spring Cloud initializes the Registration data and then executes the general sequence:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot Application
    participant Auto as Auto Service Registration
    participant Event as Application Event Publisher
    participant Registry as ServiceRegistry
    participant Backend as Eureka / Consul
    App->>Auto: Application starts
    Auto->>Event: InstancePreRegisteredEvent
    Auto->>Registry: register(Registration)
    Registry->>Backend: Send instance information
    Backend-->>Registry: Operation result
    Registry-->>Auto: Complete register call
    Auto->>Event: InstanceRegisteredEvent
~~~

The diagram illustrates the typical auto-registration flow. Execution details and configuration may vary across implementations and Spring Cloud versions.

## 3. Differences Between the Two Events

| Event | Timing | Observable Data | Common Purpose |
|---|---|---|---|
| **InstancePreRegisteredEvent** | Immediately before auto-registration invokes the register operation | Registration being prepared for registration | Log instance details, inspect metadata, mark start milestone |
| **InstanceRegisteredEvent** | After auto-registration finishes the register call | Configuration or configuration object associated with registration | Record outcomes, metrics, audits, or trigger auxiliary tasks |

The two events mark two distinct points in time. Receiving InstancePreRegisteredEvent does not mean the registry has received the instance. InstanceRegisteredEvent indicates that the registration step of the auto-registration flow has finished running; it is not a guarantee that every node in a cluster has synchronized or that every client can see the instance immediately.

### 3.1. InstancePreRegisteredEvent

This event is published before Spring Cloud calls ServiceRegistry.register(...) inside the auto-registration flow. Listeners can read details of the instance about to be registered, such as service ID, host, port, and metadata.

Some applications use this milestone to:

- Log the instance configuration before publishing it.
- Verify that the service ID or metadata has been prepared.
- Record a metric marking the start of registration.
- Capture application version details for auditing.

The event is not an API replacement for Registration configuration. If you need to change host, port, service ID, or metadata, configure the corresponding registration object before auto-registration runs.

### 3.2. InstanceRegisteredEvent

This event is published after the registration operation in the auto-registration flow completes. Listeners can use it to:

- Log that the application has executed the registration step.
- Increment metrics or emit an internal signal for monitoring systems.
- Record the configuration that was used.
- Trigger an auxiliary task outside the core registration flow.

Do not treat this event as an application health check. Successful registration only confirms that the registration communication step completed according to the implementation; it does not prove that all business endpoints are healthy or that all peers have received the registry replica.

## 4. Listening to Events with Spring ApplicationEvent

Spring allows listening to application events using the @EventListener annotation. Both Spring Cloud Commons events reside in the org.springframework.cloud.client.serviceregistry.event package.

The example below logs details before and after registration:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.serviceregistry.event.InstancePreRegisteredEvent;
import org.springframework.cloud.client.serviceregistry.event.InstanceRegisteredEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RegistrationLifecycleListener {

    private static final Logger log =
            LoggerFactory.getLogger(RegistrationLifecycleListener.class);

    @EventListener
    public void beforeRegistration(InstancePreRegisteredEvent event) {
        ServiceInstance instance = event.getRegistration();

        log.info(
                "Preparing registration: serviceId={}, host={}, port={}",
                instance.getServiceId(),
                instance.getHost(),
                instance.getPort()
        );
    }

    @EventListener
    public void afterRegistration(InstanceRegisteredEvent event) {
        Object config = event.getConfig();

        log.info(
                "Registration step completed; configType={}",
                config == null ? "none" : config.getClass().getName()
        );
    }
}
~~~

The first listener retrieves details from the registration attached to the event. The second listener logs the configuration type supplied by the event; avoid casting to a Eureka- or Consul-specific class if the application needs to remain registry-provider agnostic.

Getters and data type details belong to the Spring Cloud Commons API of the version in use. When upgrading the Spring Cloud release train, verify the corresponding API if listener code depends on specific details.

### 4.1. Listening with ApplicationListener

If you prefer implementing an interface instead of @EventListener, you can create a dedicated listener for each event:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.cloud.client.serviceregistry.event.InstancePreRegisteredEvent;
import org.springframework.stereotype.Component;

@Component
public class BeforeRegistrationListener
        implements ApplicationListener<InstancePreRegisteredEvent> {

    @Override
    public void onApplicationEvent(InstancePreRegisteredEvent event) {
        String serviceId = event.getRegistration().getServiceId();
        // Log or record metrics before registration.
    }
}
~~~

@EventListener is convenient when one component listens to multiple event types. ApplicationListener is useful when you want to declare the event type explicitly in the interface signature or configure the listener through Spring's corresponding mechanism.

## 5. Instance Version Metadata

Registration events and version metadata are two related yet distinct concepts:

- Events describe **when** the auto-registration flow is taking place.
- Metadata describes **what information** the instance publishes to the registry.

For example, an application can publish its version and build number in Eureka metadata:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      version: 2.4.1
      build: 2026.11.24
~~~

This metadata helps operators or other clients distinguish which version each running instance serves. Key names and values are defined by application convention; Eureka does not treat version as an upgrade strategy or automatically route traffic by version merely because metadata exists.

A pre-registration listener can read metadata to log or validate it. A post-registration listener can record the published version in metrics or audits. If you need to modify metadata, do so in the instance configuration before the registration is created; do not assume an event listener can mutate a shared registration.

## 6. Combining Events with ServiceRegistry

When you need to interact with the registry proactively, Spring Cloud provides ServiceRegistry. The following illustrative example shows the generic API:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
public class RegistryOperations<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public RegistryOperations(ServiceRegistry<R> serviceRegistry) {
        this.serviceRegistry = serviceRegistry;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

This is a generic example of the abstraction; type R must be the concrete Registration type used by the registry implementation. How a RegistryOperations object is created and injected depends on the implementation and application configuration. In many Spring Cloud applications, auto-registration already performs registration at startup, so avoid calling manual register additionally without a clear reason.

One point to note: InstancePreRegisteredEvent and InstanceRegisteredEvent are tied to Spring Cloud's auto-registration flow. If the application directly invokes ServiceRegistry.register(...) elsewhere, do not assume these two events will automatically be published for that manual call. If events are needed for a self-managed workflow, the application must explicitly define and publish an appropriate domain event.

## 7. Startup Ordering and Listener Impact

Spring application events are processed synchronously on the publishing thread by default, unless the application configures an asynchronous mechanism. Consequently, a listener performing long-running work can prolong startup or delay the auto-registration process.

Some implementation principles:

- Keep listeners brief: log, increment counters, or hand off a lightweight message to another processing system.
- Avoid calling external services with long timeouts directly inside a pre-registration listener.
- Do not perform data migrations or heavy work before the registry is updated.
- If asynchronous processing is needed, configure the executor and error-handling policy explicitly; ensure tasks do not depend on the listener finishing synchronously.
- Design post-registration tasks to be idempotent if executed repeatedly without unintended side effects.

If a listener throws an exception in a synchronous flow, the exception can affect startup or registration depending on where the event is published and how the implementation handles errors. Catch and handle recoverable errors inside the listener; do not swallow critical configuration errors that the system must surface.

## 8. What Events Do Not Guarantee

When designing event-driven logic, separate in-process application signals from the state of the entire discovery system:

| Claim | Can It Be Concluded? | Explanation |
|---|---|---|
| Receiving InstancePreRegisteredEvent means the instance is already in the registry | No | The event is published before the registration operation |
| Receiving InstanceRegisteredEvent means the auto-registration flow finished the register call | Yes, within the implementation's auto-registration flow | It is the milestone after the register operation in that flow |
| All Eureka peers already have the instance right when the post-registration event arrives | No | Replication between peers can have latency |
| All Eureka Clients already see the instance | No | Clients may use a registry cache and refresh periodically |
| The instance has passed business health checks | No | Discovery registration does not replace health checks |
| The version code in metadata automatically controls routing | No | Version-based routing requires explicit policies in clients or gateways |

In particular, do not use InstanceRegisteredEvent as the sole signal to put an application into traffic-serving readiness. Combine health indicators, readiness probes, and checks on essential application dependencies.

## 9. Testing and Observing the Registration Lifecycle

You can verify event behavior by starting the application in a test environment and observing logs:

1. Enable logging in the pre-registration listener.
2. Start the application with a reachable registry endpoint.
3. Confirm the InstancePreRegisteredEvent log appears before the post-registration log.
4. Check the registry for the instance with the expected service ID, host, port, and version metadata.
5. Confirm the post-registration listener was invoked.
6. Try starting when the registry is unreachable to observe errors and implementation retry behavior.
7. Start multiple instances with different version metadata to confirm the registry displays each instance accurately.

At a minimum, record the following fields in logs or metrics:

| Field | Purpose |
|---|---|
| Service ID | Identifies the service name |
| Instance ID or host/port | Distinguishes individual instances |
| Version/build metadata | Identifies the published version |
| Event type | Distinguishes pre- and post-registration milestones |
| Timestamp | Measures elapsed time from preparation to registration completion |
| Result or exception | Aids investigation of registration failures |

Avoid putting sensitive data into metadata or registration logs. Metadata is typically visible to many clients permitted to query the registry; publish only information needed for discovery and operations.

## 10. Example New-Version Rollout Flow

Suppose payment-service is running two instances of version 2.4.0. The deployment team introduces one instance of 2.5.0 into the system:

1. The new instance starts up and prepares a registration with metadata version: 2.5.0.
2. InstancePreRegisteredEvent is published; the listener logs the service ID and version about to be advertised.
3. Auto-registration invokes ServiceRegistry.register(...).
4. Once the registration operation finishes, InstanceRegisteredEvent is published; the listener records a metric for the new instance.
5. The registry updates and clients gradually receive the new instance via the provider's mechanism.
6. Load balancers or gateways apply configured routing policies to direct traffic to appropriate instances.

The post-registration event is only one milestone in the rollout process. Rolling update, canary, or blue-green strategies must be managed by the deployment platform, gateway, or dedicated routing policies. ServiceRegistry events do not shift traffic or replace old instances on their own.

~~~mermaid
flowchart TD
    START[New-version instance starts] --> META[Prepare Registration and version metadata]
    META --> PRE[InstancePreRegisteredEvent]
    PRE --> REG[ServiceRegistry.register]
    REG --> POST[InstanceRegisteredEvent]
    POST --> SYNC[Registry and clients update gradually]
    SYNC --> ROUTE[Routing policy selects instance]
~~~

## 11. Summary

Spring Cloud Commons provides InstancePreRegisteredEvent and InstanceRegisteredEvent to observe before and after the auto-registration step of a service instance. The pre-registration event is suited for recording information about to be published; the post-registration event is suited for logging, recording metrics, or triggering auxiliary work after the registration operation.

Metadata such as version and build represent data published by the application, whereas events represent lifecycle milestones. InstanceRegisteredEvent does not guarantee all peers or clients see the instance yet, nor does it replace health checks or routing policies. Keep listeners concise, avoid blocking startup threads, and test behavior against the exact implementation, Spring Cloud version, and registry used by the application.
