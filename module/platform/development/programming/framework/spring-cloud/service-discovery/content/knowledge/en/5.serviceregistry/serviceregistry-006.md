# Using the Right Registration Type for Eureka, Consul, and Zookeeper

Spring Cloud provides `ServiceRegistry<R extends Registration>` to standardize the operations for registering, deregistering, and managing the status of a service instance. However, type `R` is not simply the generic `Registration`. Each registry integration usually provides a specialized registration class carrying provider-specific data and rules.

For common integrations, the corresponding types are `EurekaRegistration` for Eureka, `ConsulRegistration` for Consul, and `ZookeeperRegistration` for Zookeeper. When calling `ServiceRegistry`, you must pair the right implementation with its matching registration type. Mixing these types can cause Java compilation to reject the code; forcing a cast or using raw types can turn the mistake into a hard-to-diagnose runtime failure.

This lesson belongs to the `ServiceRegistry` chapter in the `SPRING_CLOUD_SERVICE_DISCOVERY` module. The module helps learners understand instance discovery by service ID via `DiscoveryClient`, `ServiceRegistry`, Eureka or Consul, along with the registration lifecycle, health checks, load balancing, security, and registry inconsistency handling. This lesson focuses on the generic type parameter of `ServiceRegistry` and how to choose the right registration class when working with Eureka, Consul, and Zookeeper.

## 1. What Is Registration?

In Service Discovery, a service can run multiple instances. Each instance needs to publish information so consumers can find and connect to it, typically including:

- Service ID: the logical name of the service, for example `order-service`.
- Instance ID: an identifier for a specific running replica according to the registry's rules.
- Host and port: the address consumers can reach.
- URI or protocol: information used to build the corresponding HTTP/HTTPS address.
- Metadata: supplementary data such as zone, version, or deployment group.
- Status or health information according to the registry's model.

In Spring Cloud Commons, `Registration` is the abstraction representing an instance used in the registration workflow. It extends `ServiceInstance`, thus carrying general address and metadata information:

```java
package org.springframework.cloud.client.serviceregistry;

import org.springframework.cloud.client.ServiceInstance;

public interface Registration extends ServiceInstance {
}
```

`Registration` is a common interface, not a concrete class for applications to instantiate arbitrarily. Registry integrations can provide their own implementations to hold the extra data required by their registries.

For example, for the very same `order-service` instance, a registration may need to wrap a Eureka `InstanceInfo` object, a Consul service definition, or a Zookeeper service node record. These details are not interchangeable merely because they all describe a service instance.

## 2. The Generic Contract of ServiceRegistry

The core contract in Spring Cloud Commons has the form:

```java
package org.springframework.cloud.client.serviceregistry;

public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void setStatus(R registration, Object status);

    Object getStatus(R registration);
}
```

The type parameter `R extends Registration` means each `ServiceRegistry` operates on a specific registration type, and that type must implement `Registration`.

| Member | Meaning |
|---|---|
| `R` | The registration type managed by the implementation. |
| `register(R registration)` | Publishes the instance described by the registration. |
| `deregister(R registration)` | Removes the corresponding registration from the registry. |
| `setStatus(R registration, Object status)` | Sets the status according to the model supported by the implementation. |
| `getStatus(R registration)` | Reads the status as represented by the implementation. |

The key point is that the parameter of `register` and `deregister` has type `R`, not just any object implementing `Registration`. Generics bind the registry to its exact registration class at compile time.

## 3. Registration Types by Registry

Common registry integrations provide the following type pairs:

| Registry | Registration type | ServiceRegistry implementation | Common package |
|---|---|---|---|
| Eureka | `EurekaRegistration` | `EurekaServiceRegistry` | `org.springframework.cloud.netflix.eureka.serviceregistry` |
| Consul | `ConsulRegistration` | `ConsulServiceRegistry` | `org.springframework.cloud.consul.serviceregistry` |
| Zookeeper | `ZookeeperRegistration` | `ZookeeperServiceRegistry` | `org.springframework.cloud.zookeeper.serviceregistry` |

At the type level, these pairs relate as follows:

```java
ServiceRegistry<EurekaRegistration> eurekaRegistry;
ServiceRegistry<ConsulRegistration> consulRegistry;
ServiceRegistry<ZookeeperRegistration> zookeeperRegistry;
```

Each registration class satisfies the `Registration` contract, while each registry implementation accepts its own specialized type. When reading the source code or API documentation of a specific Spring Cloud version, check the implementation's declaration to confirm exact packages and generic types for the release train your project uses.

### 3.1. EurekaRegistration

The Eureka integration uses `EurekaRegistration` to represent registration data bound to the Eureka client. These types belong to the package:

```java
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaRegistration;
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaServiceRegistry;
```

`EurekaServiceRegistry` manages `EurekaRegistration`. This registration is tied to Eureka client internals, such as instance metadata and Eureka's application status management. Never try to create a Eureka registration by taking a Consul or Zookeeper registration and casting it.

Example declaring a component that depends on the exact Eureka types:

```java
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaRegistration;
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class EurekaRegistryOperations {

    private final EurekaServiceRegistry serviceRegistry;
    private final EurekaRegistration registration;

    public EurekaRegistryOperations(
            EurekaServiceRegistry serviceRegistry,
            EurekaRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

This example illustrates the dependency types; whether the registration and registry beans exist depends on the starter, configuration, and application lifecycle. In a typical Eureka setup, Spring Cloud can register and deregister the instance automatically. Do not call `register` again arbitrarily when auto-registration already manages the lifecycle, as that can trigger duplicate operations or corrupt state.

### 3.2. ConsulRegistration

The Consul integration uses `ConsulRegistration`, residing in the package:

```java
import org.springframework.cloud.consul.serviceregistry.ConsulRegistration;
import org.springframework.cloud.consul.serviceregistry.ConsulServiceRegistry;
```

`ConsulServiceRegistry` works with `ConsulRegistration`. This registration is tied to the service information published to Consul, such as service name, service ID, address, port, tags, and metadata according to the integration configuration.

Example of a component operating with the exact Consul types:

```java
import org.springframework.cloud.consul.serviceregistry.ConsulRegistration;
import org.springframework.cloud.consul.serviceregistry.ConsulServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class ConsulRegistryOperations {

    private final ConsulServiceRegistry serviceRegistry;
    private final ConsulRegistration registration;

    public ConsulRegistryOperations(
            ConsulServiceRegistry serviceRegistry,
            ConsulRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

Consul can use agents and health checks to update service status. The registration structure and how service records are built depend on the Consul integration configuration. Do not assume that all metadata fields or statuses share the same representation as Eureka.

### 3.3. ZookeeperRegistration

The Zookeeper integration uses `ZookeeperRegistration`, residing in the package:

```java
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperRegistration;
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperServiceRegistry;
```

`ZookeeperServiceRegistry` works with `ZookeeperRegistration`. This registration holds the data needed to register a service instance in the Zookeeper data tree, typically tied to the service instance and node creation rules under Spring Cloud Zookeeper's discovery mechanism.

Example:

```java
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperRegistration;
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class ZookeeperRegistryOperations {

    private final ZookeeperServiceRegistry serviceRegistry;
    private final ZookeeperRegistration registration;

    public ZookeeperRegistryOperations(
            ZookeeperServiceRegistry serviceRegistry,
            ZookeeperRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

Zookeeper typically represents service discovery using nodes in a data tree and can use session-bound ephemeral nodes to reflect client lifecycles. Node path details, payloads, and lifecycle rules are determined by the integration. Therefore, `ZookeeperRegistration` cannot be replaced by `EurekaRegistration` or `ConsulRegistration`.

## 4. Why Not Use ServiceRegistry<Registration> for Every Registry?

A common mistake is declaring a generic variable like this:

```java
ServiceRegistry<Registration> registry;
```

And then assigning a concrete implementation:

```java
EurekaServiceRegistry eurekaServiceRegistry = ...;

// Invalid due to generic invariance:
ServiceRegistry<Registration> registry = eurekaServiceRegistry;
```

The reason is that generics in Java are *invariant*. Even though `EurekaRegistration` is a subtype of `Registration`, `ServiceRegistry<EurekaRegistration>` is not a subtype of `ServiceRegistry<Registration>`.

If Java allowed that assignment, the following code could pass a registration from another registry into Eureka:

```java
// Suppose the invalid assignment above were allowed:
registry.register(consulRegistration);
```

The Eureka registry cannot handle a `ConsulRegistration` simply because both implement `Registration`. Generic invariance prevents this mistake at compile time.

### 4.1. Do Not Work Around It with Raw Types

Raw types bypass generic type checking:

```java
@SuppressWarnings("rawtypes")
ServiceRegistry registry = eurekaServiceRegistry;

// The compiler no longer verifies the registration type at the call site.
registry.register(consulRegistration);
```

The code may compile with warnings, but the implementation can fail when casting internally or processing the registration. Do not use a raw `ServiceRegistry` to dodge generic type errors.

### 4.2. Do Not Cast Another Registry's Registration

The following example is wrong:

```java
Registration registration = consulRegistration;
EurekaRegistration eurekaRegistration = (EurekaRegistration) registration;
```

Casting only changes how the compiler views the reference; it does not transform a Consul object into a Eureka object. Because the two classes do not share an inheritance relationship, the cast fails at runtime with a `ClassCastException`.

## 5. How to Write Reusable Functions While Staying Type-Safe

If you want to reuse logic that calls `ServiceRegistry`, preserve the generic type `R` across the method. For example:

```java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public final class RegistryActions {

    private RegistryActions() {
    }

    public static <R extends Registration> void register(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        serviceRegistry.register(registration);
    }

    public static <R extends Registration> void deregister(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        serviceRegistry.deregister(registration);
    }
}
```

The compiler infers `R` from the pair of arguments. Valid calls look like:

```java
RegistryActions.register(eurekaServiceRegistry, eurekaRegistration);
RegistryActions.register(consulServiceRegistry, consulRegistration);
RegistryActions.register(zookeeperServiceRegistry, zookeeperRegistration);
```

Each call preserves the matching type pair. Mismatched pairs are rejected at compile time:

```java
// Invalid: the Eureka registry does not accept ConsulRegistration.
RegistryActions.register(eurekaServiceRegistry, consulRegistration);
```

Generic methods allow reusing common operations without erasing concrete type information. There is no need to widen every registration to `Registration` and cast back later.

## 6. When Multiple Registries Coexist in One Application

An application may depend on multiple registries due to a migration, legacy system integration, or region segmentation. In such cases, clearly distinguish the corresponding beans and registrations.

You can inject by generic type:

```java
public class MultiRegistryCoordinator {

    private final ServiceRegistry<EurekaRegistration> eurekaRegistry;
    private final ServiceRegistry<ConsulRegistration> consulRegistry;

    public MultiRegistryCoordinator(
            ServiceRegistry<EurekaRegistration> eurekaRegistry,
            ServiceRegistry<ConsulRegistration> consulRegistry) {
        this.eurekaRegistry = eurekaRegistry;
        this.consulRegistry = consulRegistry;
    }
}
```

Spring can use generic type information when resolving dependencies. If the application defines multiple beans with the same generic type or custom wrappers, use `@Qualifier` with the actual bean name from configuration to avoid ambiguity. Do not invent qualifier names from examples if the project has not declared those beans.

If you need to hold a heterogeneous collection of registries, `ServiceRegistry<?>` can store references for inspecting metadata or forwarding to read-only logic. However, a wildcard does not allow passing an arbitrary `Registration` into `register`, because the compiler does not know the concrete registration type that registry accepts. For write operations, keep the generic type `R` and its matching registration paired within the same abstraction.

## 7. Auto-Registration and Manual Operations

In standard Spring Cloud applications, registry starters typically integrate service registration into the Spring Boot lifecycle. When the application starts, the integration creates a registration and registers it; when the application stops, the integration deregisters it or lets the registry's lease/health mechanism handle cleanup per configuration.

Therefore, before calling `register` or `deregister` manually, determine:

1. Is auto-registration enabled?
2. Which component owns the registration lifecycle?
3. Which bean produced the registration object, and does it match the running instance?
4. Are you accidentally creating duplicate registrations or canceling registration before graceful shutdown finishes?
5. Does the registry implementation support status operations in the way the application expects?

Manual operations can be useful in administrative tools or custom lifecycle flows. However, if Spring Cloud already manages registration, leave ownership in a single place to avoid competing register/deregister calls.

## 8. Differences in Status and Health Across Registries

`ServiceRegistry` exposes `setStatus` and `getStatus` at the abstraction level, yet the status parameter is `Object`. This indicates that the common contract does not enforce a single enum or identical status set across all providers.

| Registry | What to check |
|---|---|
| Eureka | Status types accepted by the Eureka integration and the relationship among instance status, heartbeats, health, and self-preservation. |
| Consul | How service status is reflected by health checks, check statuses, tags, and the catalog; do not assume a status object carries the same meaning as in Eureka. |
| Zookeeper | How the registration exists in the data tree, session/ephemeral nodes, and how the implementation behaves with status methods. |

Do not assume calling `setStatus(registration, "DOWN")` produces the same effect across all three registries. One implementation may require its own enum or object, while another may rely primarily on health checks or node lifecycles. Check the API for your exact starter version and test actual runtime behavior.

Also distinguish between:

- **Registration:** the record showing how an instance is advertised.
- **Health check:** a check verifying whether an endpoint or process meets health criteria.
- **Heartbeat/lease:** a signal indicating that a client is still alive or renewing the record's lease.
- **Readiness:** whether the instance is ready to accept business traffic.
- **Load balancing:** selecting one instance among those deemed eligible.

These concepts work together, yet are not identical. Having a record in the registry does not prove the endpoint is healthy; a healthy status does not automatically guarantee requests will connect successfully either.

## 9. Checking Dependencies and Imports

When a registration class cannot be found or injected, inspect the registry integration dependencies. Each starter supplies its own packages and beans:

| Integration | Typical starter dependency | Types to recognize |
|---|---|---|
| Eureka | `spring-cloud-starter-netflix-eureka-client` | `EurekaRegistration`, `EurekaServiceRegistry` |
| Consul | `spring-cloud-starter-consul-discovery` | `ConsulRegistration`, `ConsulServiceRegistry` |
| Zookeeper | `spring-cloud-starter-zookeeper-discovery` | `ZookeeperRegistration`, `ZookeeperServiceRegistry` |

Artifact names and configuration details may change across release trains. Use a Spring Cloud BOM compatible with your project's Spring Boot version and avoid mixing starter versions manually. If an application uses only one registry, do not add dependencies for the other two registries merely to access their registration classes.

When troubleshooting compilation errors, check:

- Do imports point to the exact integration package?
- Does the registry variable declare the matching generic type?
- Does the registration object have the same type as the generic parameter?
- Is the starter on the classpath with a compatible version?
- Are the registration/service registry beans created by auto-configuration?
- Are multiple beans of the same type causing Spring dependency resolution to fail?

## 10. Common Errors and How to Fix Them

### `ServiceRegistry<Registration>` rejects a concrete implementation

The cause is generic invariance. Declare `ServiceRegistry<EurekaRegistration>`, `ServiceRegistry<ConsulRegistration>`, or `ServiceRegistry<ZookeeperRegistration>` matching the implementation.

### `register` receives the wrong registration class

Match the implementation's generic parameter with the passed object. Never use a cast to turn one registry's registration into another registry's registration.

### Spring reports no registration bean found

Check the starter, auto-configuration, discovery enablement conditions, and how auto-registration is enabled/disabled. Some beans exist only when the corresponding registry configuration is active.

### Spring reports multiple matching beans

Check whether multiple registry starters were added simultaneously. Use generic types to disambiguate when Spring supports it; if still ambiguous, use `@Qualifier` with the actual bean name or inject the specific implementation appropriate for the design.

### Instance appears twice or is deregistered at the wrong time

Check whether auto-registration and manual code are both acting on a registration. Choose a single owner for the lifecycle and ensure the registration object matches the current instance.

### Status does not change as expected

Inspect the status type, integration semantics, and health checks. Do not assume strings like `UP` or `DOWN` are accepted uniformly. Observe the data in the registry and discovery results after the operation.

## 11. Checklist for Choosing the Right Registration Type

| Question | Correct condition |
|---|---|
| Which registry is the application using? | Identify the actual starter and integration. |
| What generic type does the registry implementation use? | Read the implementation's `ServiceRegistry<R>` declaration. |
| Which class is the registration object? | Must exactly match the `R` of that registry. |
| Are raw types or unchecked casts being used? | Remove them and preserve concrete generic types. |
| Are there multiple registry beans? | Use generic-aware injection or `@Qualifier` when needed. |
| Who owns the registration lifecycle? | Decide between auto-registration or custom code; avoid duplicate operations. |
| Do statuses share identical semantics? | Verify types and behavior specific to each integration. |
| Are starters compatible? | Verify Spring Boot, Spring Cloud release train, and BOM alignment. |

## Conclusion

`Registration` is the common abstraction, whereas `EurekaRegistration`, `ConsulRegistration`, and `ZookeeperRegistration` are specialized types for their respective registry integrations. The implementations `EurekaServiceRegistry`, `ConsulServiceRegistry`, and `ZookeeperServiceRegistry` bind `ServiceRegistry<R>` to their matching registration classes. Because Java generics are invariant, `ServiceRegistry<EurekaRegistration>` cannot be used as `ServiceRegistry<Registration>`.

Keep the registry and registration paired consistently from dependency declarations through constructor injection and `register`/`deregister` calls. When reusing logic, use generic methods `<R extends Registration>` to preserve type relationships. At the same time, clarify each provider's auto-registration behavior, lifecycle ownership, and status semantics. This practice catches type mismatches at compile time, eliminates unsafe casts, and keeps the Service Discovery lifecycle consistent.
