# Extending Registration with ServiceRegistry When Truly Needed

Spring Cloud normally auto-registers an application instance with the service registry when the application starts. In most systems, one registration per instance is sufficient: it holds the `serviceId`, `instanceId`, address, port, and metadata for consumers to find and call the service.

There are cases where a single process genuinely provides multiple distinct logical endpoints, such as HTTP and gRPC on two ports, or needs to advertise a separate endpoint for a subset of consumers. In those situations, you may need to add registrations through `ServiceRegistry`. However, adding a record does not make an endpoint materialize, open a port, or create a network route. Each registration must represent a meaningful endpoint with a clear lifecycle and reachable address.

This guide explains the role of `ServiceRegistry`, how to decide when to extend registration, how to manage multiple records without duplicating auto-registration, and how to verify behavior on Eureka, Consul, or ZooKeeper.

## 1. Where Does ServiceRegistry Fit in Service Discovery?

Spring Cloud Commons provides abstractions for providers to register services and consumers to discover instances:

| Component | Role | Primary Actions |
|---|---|---|
| Registration | Marker interface for registry-specific registration objects | serviceId, host, port, secure, metadata |
| ServiceRegistry | Abstraction to manage registrations | register, deregister, getStatus, setStatus |
| DiscoveryClient | Abstraction for consumers to query the registry | getServices, getInstances |
| AutoServiceRegistration | Coordinates automatic registration during application lifecycle | Registers default instance on application startup |
| ServiceInstance | Instance data received by the consumer | URI, host, port, metadata |

`ServiceRegistry` is a Spring Cloud Commons SPI. It is neither an independent registry server nor an API for consumers to locate instances. Specific registry implementations perform write operations against Eureka, Consul, ZooKeeper, or the corresponding system.

The API is generic because each registry has its own `Registration` type:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    <T> T getStatus(R registration);

    void setStatus(R registration, String status);

    void close();
}
~~~

This is the general shape of the SPI; inspect the source matching your release train when writing integration code. Do not cast a Eureka registration to a Consul registration or use raw types to bypass type checking.

The SPI only standardizes basic operations; it does not promise that every implementation allows a single bean/client to manage arbitrarily many independent serviceIds. Some integrations bind `ServiceRegistry` to one application instance or one default registration. Before designing multiple records in the same process, check the specific implementation of your starter and version. If the adapter only supports one application instance, you may need a separate client/context, a separate service/process, or a gateway; multi-registration capability cannot be inferred solely from the generic API.

`getStatus()` and `setStatus()` also do not share a portable value set across all registries. `getStatus()` uses a generic return type and status semantics depend on the implementation. Do not pass arbitrary `UP`/`DOWN` strings if the adapter expects a specific enum or state.

Spring Cloud Commons also includes the `/serviceregistry` actuator endpoint to read or modify the status of the current `Registration` bean. This endpoint is not a tool for creating multiple registrations. Valid status values depend on the registry; for instance, Eureka supports `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. Only expose this endpoint on a secured management interface.

Consumers generally do not call `ServiceRegistry.register()`. Consumers use `DiscoveryClient.getInstances(serviceId)` or Spring Cloud LoadBalancer to obtain instances. The provider or a lifecycle component is responsible for registering and deregistering.

## 2. By Default, One Instance Usually Needs Only One Registration

Suppose `inventory-service` runs one replica on host `10.20.1.11`, listening for HTTP on port `8080`. The registration might contain:

~~~yaml
serviceId: inventory-service
instanceId: inventory-node-a
host: 10.20.1.11
port: 8080
secure: false
metadata:
  app.version: "2.4.0"
  routing.zone: "zone-a"
~~~

Consumers look up `inventory-service` and receive a `ServiceInstance`. When the service has three replicas, each replica registers its own instance with the same `serviceId` but a distinct `instanceId`.

~~~mermaid
flowchart TD
    R["Registry: inventory-service"]
    R --> A["inventory-node-a<br/>10.20.1.11:8080"]
    R --> B["inventory-node-b<br/>10.20.1.12:8080"]
    R --> C["inventory-node-c<br/>10.20.1.13:8080"]
    D["Consumer / LoadBalancer"] --> R
    D --> A
    D --> B
    D --> C
~~~

This is the standard horizontal scaling model. There is no need to call `ServiceRegistry` manually per consumer or per request. The starter's auto-registration mechanism already registers the application instance.

If you only need to add version, zone, weight, or a few routing attributes, add metadata to the existing registration. Do not create another registration solely to store a metadata value.

## 3. When Are Multiple Registrations Truly Needed?

Only extend registrations when multiple logical endpoints require independent discovery.

| Need | Appropriate Representation | Why |
|---|---|---|
| Multiple replicas of the same API | Same serviceId, distinct instanceId per replica | LoadBalancer chooses among equivalent replicas |
| One process offering HTTP and gRPC on different ports | Two logical serviceIds, e.g., inventory-http and inventory-grpc | Consumers need to pick the right protocol and port |
| Business API and management endpoint | Register only the business API; management uses a separate admin channel | Prevents consumers from accidentally calling actuator |
| Same endpoint with version/zone/canary | One registration with metadata | Metadata describes attributes of the same endpoint |
| Internal and public endpoints with different trust boundaries | Separate serviceId/registry scope or gateway | Consumers must not receive addresses from the wrong network |
| One process with two independent endpoints having distinct traffic policies | Separate registration per endpoint | Enables independent rollout, health checks, and authorization |
| Multiple networks for one logical endpoint | Prefer DNS/gateway or network-scoped discovery | An advertised address may not be reachable from every caller |

For example, `inventory-service` exposes an HTTP API on port `8080` and gRPC on port `9090`. If both protocols have separate consumers and health checks, you can register:

- `inventory-http` → `host:8080`
- `inventory-grpc` → `host:9090`

Do not register both ports under the same `serviceId` if consumers lack a mechanism to distinguish protocols. If LoadBalancer receives both HTTP and gRPC instances in the same list, it may pick the wrong port and cause hard-to-diagnose errors.

A single process can hold multiple registrations, provided each registration has a unique `instanceId` within the registry's rules and accurately describes its endpoint.

## 4. When Should You Not Extend Registration?

The following cases usually do not warrant adding extra records:

- Only wanting to add metadata such as version, zone, canary, or weight.
- Wanting to register each replica twice to increase reliability.
- Wanting to register one record per consumer.
- Wanting to advertise individual URL paths or controller methods.
- Wanting to expose the Actuator port in the business service list.
- Wanting to add a record on every retry or reconnect.
- Wanting to fix a network issue by creating another registration with the same unreachable address.

Registration only stores routing info and metadata. It does not open firewalls, create Docker port mappings, provision DNS, configure TLS, or make a Pod IP reachable from outside the cluster.

If the current endpoint is already accurate, update metadata or address configuration. If two endpoints have different protocols or lifecycles, consider separate `serviceId` values.

## 5. Distinguishing serviceId and instanceId

These two fields solve two different problems:

- **serviceId** is the logical name that consumers look up.
- **instanceId** distinguishes a specific registration within a service.

Example:

| serviceId | instanceId | Endpoint |
|---|---|---|
| inventory-http | inventory-http-node-a | 10.20.1.11:8080 |
| inventory-http | inventory-http-node-b | 10.20.1.12:8080 |
| inventory-grpc | inventory-grpc-node-a | 10.20.1.11:9090 |

If two registrations in the same process share the same `instanceId` while the registry requires unique IDs, the later registration may overwrite or conflict with the earlier record. Choose stable IDs that are unique per `serviceId` and endpoint.

Do not generate a new random `instanceId` on every retry. If a `register` call times out after the server already wrote the record, retrying with a new ID creates duplicate registrations. Use a deterministic ID derived from `serviceId`, hostname/pod identity, and port, or another stable identifier.

## 6. ServiceRegistry and Auto-Registration

Spring Cloud starters typically integrate `AutoServiceRegistration` to register the default application instance during startup lifecycle. This removes the need for applications to call `register()` manually in every project.

When adding an extra registration, clarify:

1. Which endpoint does auto-registration currently register?
2. Which endpoint does the additional registration represent?
3. Who owns the lifecycle of the additional record?
4. On shutdown, which component calls `deregister`?
5. On reconnect or session loss, how is the record recreated?
6. Is there any risk of both mechanisms registering the same endpoint?

If you only need to add a second endpoint, usually keep auto-registration for the primary endpoint and manage the additional registration separately. Do not disable auto-registration application-wide if you still need the default registration.

The common property used to control auto-registration is:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

If you need to disable auto-registration to manage the default registration yourself, the configuration can be:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Only use this configuration when a manual lifecycle fully replaces the default registration and has been tested for deregistration, reconnection, health, and readiness. If only adding a secondary endpoint, normally keep auto-registration for the primary endpoint.

If the application manages all registrations manually, you may need to disable auto-registration using the property supported in your Spring Cloud version. Verify the exact configuration of your release train and starter; do not assume all versions or registries share the same lifecycle.

Another option supported by Spring Cloud Commons is `@EnableDiscoveryClient(autoRegister=false)`. There is no need to use both the annotation and the property when one clearly expresses the application's configuration.

Do not keep auto-registration enabled while also calling `register()` manually for the same `serviceId`/`instanceId` without an idempotent design. That can create races, inconsistent metadata updates, or erroneous deregistration of records on shutdown.

## 7. Extending with ServiceRegistry Safely

`ServiceRegistry` has the generic type `R extends Registration`. When injecting the registry, use the exact registration type provided by the implementation. Do not cast an arbitrary `Registration` into a Eureka- or Consul-specific registration.

A shared wrapper can hold `register`/`deregister` operations while a registry adapter factory creates the concrete registration:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public final class AdditionalRegistrationPublisher<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public AdditionalRegistrationPublisher(ServiceRegistry<R> serviceRegistry) {
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

This is a generic coordinator class; `R` must be the `Registration` type matching the injected `ServiceRegistry`. It does not construct a `EurekaRegistration` or `ConsulRegistration` by itself. Use factories, builders, or integration APIs supported by the starter to construct the registration object.

Do not instantiate registrations by guessing internal starter implementation classes. Those implementations may depend on clients, configuration, health checks, metadata, or instance info prepared by auto-configuration.

Do not call `serviceRegistry.close()` from an additional registration's handle. `close()` belongs to the lifecycle of the registry/client and can affect the default registration or other handles sharing the same bean. Let the component owning `ServiceRegistry` or the starter's Spring lifecycle close the client at the right time.

Some `AutoServiceRegistration` implementations call `ServiceRegistry.close()` on stop. If an additional handle shares the registry bean, its phase/order must ensure the handle finishes deregistering before auto-registration closes the registry client. Verify this ordering against your actual implementation and version.

## 8. Managing the Lifecycle of Additional Registrations

A registration should only appear once the endpoint is ready to accept connections. On shutdown, remove the registration before the endpoint stops serving so consumers have time to update their lists.

General lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> EndpointReady: Server bound and port determined
    EndpointReady --> Registered: ServiceRegistry.register()
    Registered --> Serving: Readiness UP
    Serving --> Draining: Shutdown begins
    Draining --> Deregistered: ServiceRegistry.deregister()
    Deregistered --> Stopped: Server closes
    Registered --> Retry: Transient register error
    Retry --> Registered: Backoff and retry succeed
    Stopped --> [*]
~~~

A lifecycle manager can use `SmartLifecycle` to tie `register`/`deregister` operations to the `ApplicationContext` lifecycle:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
import org.springframework.context.SmartLifecycle;

import java.util.function.Supplier;

public final class AdditionalRegistrationLifecycle<R extends Registration>
        implements SmartLifecycle {

    private final ServiceRegistry<R> serviceRegistry;
    private final Supplier<R> registrationFactory;

    private R registration;
    private volatile boolean running;

    public AdditionalRegistrationLifecycle(
            ServiceRegistry<R> serviceRegistry,
            Supplier<R> registrationFactory) {
        this.serviceRegistry = serviceRegistry;
        this.registrationFactory = registrationFactory;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }

        R candidate = registrationFactory.get();
        serviceRegistry.register(candidate);

        this.registration = candidate;
        this.running = true;
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }

        serviceRegistry.deregister(registration);
        running = false;
        registration = null;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

This is an illustrative skeleton. In a real application, ensure `registrationFactory` only creates the record after the endpoint has its exact host/port. If the port is dynamically allocated, do not create `Registration` prematurely while the port is still unknown.

Configure appropriate lifecycle phase and ordering so `deregister` runs before the endpoint shuts down. If `deregister` fails, log the error and apply a retry/cleanup policy; do not falsely mark success. When `start` fails, do not set `running=true`.

With multiple registrations, manage each handle independently. If a secondary endpoint fails to start, clearly decide whether the application can continue serving the primary endpoint or whether the entire application must report readiness `DOWN`.

## 9. Preventing Duplicate or Overwritten Additional Registrations

When adding registrations, identify the registry's unique key. Typically pay attention to `serviceId`, `instanceId`, node ID, or provider-specific service ID.

Example internal management table:

| Logical endpoint | serviceId | instanceId | Host | Port |
|---|---|---|---|---:|
| HTTP API | inventory-http | inventory-http-node-a | 10.20.1.11 | 8080 |
| gRPC API | inventory-grpc | inventory-grpc-node-a | 10.20.1.11 | 9090 |

Invariants to maintain:

- One endpoint never has two registrations created by both auto and manual mechanisms.
- Retries reuse the same `instanceId` for the same endpoint.
- Two different endpoints do not share an `instanceId` if the registry requires uniqueness.
- Deregister the exact registration created, not just by generic `serviceId`.
- Never deregister another replica's record.
- After a restart, old records must be cleaned up via lease/session expiration or deregistration.

Especially when managing multiple registrations in one process, do not keep a single `registration` field and overwrite it each time a new endpoint is created. Use a map keyed by logical endpoint or a list of clearly identified handles.

## 10. Metadata Can Solve Needs Without Adding Registrations

If endpoints share the same protocol, host, and port, differing only in version or zone, metadata is usually the right choice.

Eureka example:

~~~yaml
eureka:
  instance:
    metadata-map:
      app.version: "2.4.0"
      routing.zone: "zone-a"
      routing.canary: "false"
~~~

Consul example:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          app.version: "2.4.0"
          routing.zone: "zone-a"
          routing.canary: "false"
~~~

Property names and mapping behavior depend on the starter version. In Consul, tags and metadata are two distinct concepts; do not assume tags automatically populate the `ServiceInstance` metadata map.

Metadata does not cause LoadBalancer to filter instances automatically. If consumers need to select by zone or version, you must configure and test a corresponding `ServiceInstanceListSupplier` or policy. If no consumer reads the metadata, adding it merely increases payload size without affecting routing.

## 11. Differences When Using Eureka

Eureka `ServiceRegistry` operates on registrations following the Eureka instance model. Starter auto-registration typically creates a registration for the application instance based on Eureka client configuration.

Be cautious: Eureka's `ServiceRegistry` is typically tied to the current application's `EurekaRegistration`/`ApplicationInfoManager`. Do not assume simply constructing multiple arbitrary registration objects will cause one Eureka client to advertise multiple independent applications/serviceIds. Check how the implementation in your exact version builds `ApplicationInfoManager` and instance info; if it only models a single application instance, use a separate application/client or an appropriate endpoint/gateway architecture.

When an additional endpoint is needed:

- Decide whether the endpoint should be a separate application/`serviceId`.
- Use a distinct and stable instance ID.
- Verify advertised host/port are reachable from consumers.
- Do not mix the management port into the API `serviceId` if consumers might pick it by mistake.
- Verify auto-registration and custom registration do not overwrite the same record.
- On deregister, verify the exact instance is removed from the Eureka registry.

If only metadata is needed, prefer configuring the metadata map on the existing Eureka instance. If HTTP and gRPC require different ports, consider two logical serviceIds and corresponding client adapters.

Eureka heartbeat/lease applies to its registered instance. Do not assume adding a custom registration automatically receives the same heartbeat/lifecycle as the default registration unless the adapter manages it. Check how the starter renews leases and statuses for additional registrations.

## 12. Differences When Using Consul

A Consul registration normally contains service name, service ID, address, port, tags, metadata, and health checks. Service ID usually distinguishes a specific registration on an agent/node.

The Consul agent API can manage multiple service registrations with different service IDs on the same node. Even so, the specific Spring Cloud adapter and auto-registration lifecycle still govern how records are created/deregistered; verify the service ID, the owning agent, and cleanup permissions.

When adding a registration:

- Create a distinct service ID for each logical endpoint.
- Choose an address/port reachable by consumers.
- Configure a health check tailored to that exact endpoint.
- Do not use the same check URL for HTTP and gRPC if protocols differ.
- Identify which agent owns the registration and which component deregisters it.
- Verify `passing`/`critical` status via the Health API and records in the Catalog.

Example of two endpoints:

~~~json
{
  "service": {
    "name": "inventory-http",
    "id": "inventory-http-node-a",
    "address": "10.20.1.11",
    "port": 8080,
    "checks": [
      {
        "http": "http://10.20.1.11:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

~~~json
{
  "service": {
    "name": "inventory-grpc",
    "id": "inventory-grpc-node-a",
    "address": "10.20.1.11",
    "port": 9090,
    "checks": [
      {
        "grpc": "10.20.1.11:9090",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

These are illustrative Consul agent registration payloads; gRPC check syntax, TLS, and optional fields must be checked against your running Consul version. A passing check only proves the agent can reach the check endpoint. Consumers must still be able to reach the service address and port.

## 13. Differences When Using ZooKeeper

Spring Cloud Zookeeper or Curator Service Discovery typically stores instance info in znodes. Registrations can be tied to ephemeral nodes and a ZooKeeper session.

The ability to register multiple endpoints depends on how the library constructs service paths and payloads. The generic SPI does not generate distinct paths automatically; you must use different service names/paths and instance identities, and verify whether the client/session can manage those nodes concurrently.

If one process exposes two logical endpoints, the registration payload or path must distinguish service name and instance identity. Do not write two endpoints to the same znode path and overwrite each other's payloads.

When creating an additional registration:

- Use a separate path/service name per logical endpoint.
- Give each endpoint a clear instance identity.
- Identify which session owns the ephemeral node.
- When a session becomes `LOST`, recreate registrations for each endpoint.
- On shutdown, remove the exact node or close the session per client lifecycle.
- Consumers must watch/resync the right paths.

Do not create persistent znodes in place of ephemeral registrations without a cleanup mechanism. Persistent nodes can survive process crashes and cause consumers to receive stale endpoints.

If using Spring Cloud Zookeeper auto-registration, inspect how the library constructs service instances and manages lifecycle. Avoid enabling auto-registration while also manually creating a znode at the same path for the default endpoint.

## 14. Managing Health and Readiness Separately Per Endpoint

If a process serves multiple endpoints, a single health check may not accurately reflect each endpoint.

For example:
- HTTP API is up, but the gRPC server has not bound yet.
- gRPC is healthy, but the HTTP server is failing.
- The management endpoint is up, while the business API cannot accept requests.
- Registry connection is lost, though the current endpoint can still serve via cached discovery.

Scope health checks per logical endpoint. With two independent registrations, each registration can have its own check. If an endpoint is mandatory for the application to serve, overall readiness must reflect that condition.

Do not register an endpoint before its server binds or before its health check can run. Do not let a health check inspect only one port and mark both registrations as passing.

On shutdown:
1. Lower readiness for the stopping endpoint.
2. Stop accepting new requests or begin draining.
3. Deregister the corresponding endpoint.
4. Wait for consumers to refresh discovery within allowed limits.
5. Close the server and resources.
6. Verify the old record has been removed or transitioned per registry mechanics.

## 15. Testing Additional Registrations

Test both registration data and lifecycle behavior.

| Test | Expectation |
|---|---|
| Initial registration | Registry holds the exact serviceId/instanceId/host/port |
| Repeated registration with same ID | No duplicate record created; idempotent behavior per adapter |
| Two endpoints in one process | Both registrations do not overwrite each other |
| Metadata mapping | Consumers receive the right keys and values |
| Invalid host/port | Contract test catches invalid endpoints |
| Health check failure | Corresponding endpoint transitions to critical/not-ready |
| Deregister one endpoint | Remaining endpoint stays registered |
| Full process shutdown | All registrations owned by the process are removed |
| Reconnect/session LOST | Registrations are restored with appropriate identities |
| Consumer lookup | Separate serviceId returns only the matching protocol/endpoint |

Unit tests can mock `ServiceRegistry` to verify register/deregister call counts and lifecycle ordering. Integration tests require a real registry or testcontainer to verify records and metadata when read back via `DiscoveryClient`.

Do not only assert that a mock registry received one `register` call. Verify that the advertised endpoint is reachable from the consumer network and that deregistration does not accidentally remove another registration.

For example, simple tests for a lifecycle manager can verify:
- calling `start` twice only registers once;
- calling `stop` twice only deregisters once;
- failed `register` does not set `running` to `true`;
- deregistering endpoint A does not affect endpoint B.

## 16. Observing Registrations and Detecting Stale Records

When extending registrations, record counts increase intentionally. However, leftover records caused by retries or failed shutdowns must be detected.

Metrics to monitor:

| Metric/log | Meaning |
|---|---|
| registration_count by serviceId | Number of currently advertised instances |
| registration_attempt_total | Number of registration attempts |
| registration_failure_total | Number of failed registrations |
| deregistration_total | Number of deregistrations |
| duplicate_instance_id | Identity conflicts |
| registration_age | Age of an existing record |
| health_status by endpoint | Status of each logical endpoint |
| discovery_lookup_result | Whether consumers receive the expected endpoints |

Do not use unbounded `instanceId` or `hostname` values as metric labels if they cause high cardinality. Use structured logs and aggregate metrics by `serviceId`/endpoint type.

When detecting stale records:
1. Identify the process or agent owning the record.
2. Cross-check `instanceId`, `host`, `port`, and last update timestamp.
3. Confirm the record no longer has a live endpoint.
4. Use the registry's official deregistration API or cleanup mechanism.
5. Verify consumers have evicted the stale record from caches.

Do not bulk-delete records solely by service name. Healthy replicas with the same `serviceId` may still be running.

## 17. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| An endpoint appears twice | Auto-registration and manual registration both active | Only one lifecycle may own each record |
| HTTP consumer picks gRPC port by mistake | Two protocols share the same serviceId and LoadBalancer list | Split logical serviceId or filter explicitly |
| New registration overwrites old registration | Reusing the same instanceId/service ID | Assign distinct identities per endpoint |
| Dashboard shows record but port is closed | Registered before server bound or wrong port mapping | Only register after endpoint is ready |
| Record persists after shutdown | Failed to deregister or session has not expired | Ensure lifecycle cleanup and proper lease/session config |
| Added metadata but routing did not change | LoadBalancer does not read metadata | Configure supplier/policy and test |
| Consumer receives unreachable internal address | Advertised address is for the wrong network | Advertise an appropriate endpoint/gateway |
| Consul check passing but consumers fail | Agent check URL differs from service address | Test both network paths separately |
| ZooKeeper retains stale znode | Persistent node or stale session/cache | Check ephemeral nodes/session/watchers |
| One failing registration makes entire app DOWN | Aggregated readiness fails to distinguish required endpoints | Design health policy around serving capability |

## 18. Safe Registration Extension Process

Before writing code, clarify:

1. Does the additional endpoint truly differ from the existing endpoint in protocol, port, network, or lifecycle?
2. Can this be solved using metadata or a gateway instead?
3. What distinct `serviceId` do consumers need?
4. How will each registration get a unique `instanceId`?
5. Which registration is managed by auto-registration?
6. Which registration is managed by a custom lifecycle?
7. At what point after server bind is the registration created?
8. Which address and protocol does the endpoint's health check use?
9. On shutdown, how is registration deregistered before the server stops?
10. On retry/reconnect, how are duplicate records avoided?
11. Do consumers filter by the right `serviceId` and metadata?
12. Are there integration tests verifying lookups and network reachability?

Implement step by step:
- Define `serviceId` and metadata schema.
- Create the registration via the appropriate integration API.
- Attach register/deregister lifecycle handling.
- Test idempotency and cleanup.
- Verify consumer lookup and endpoint reachability.
- Monitor record counts, health, and errors before broad rollout.

## 19. Completion Checklist

Before deploying additional registrations to production, confirm:

1. There is a clear justification for every additional registration.
2. No new record is created solely to duplicate metadata or scale replicas.
3. `serviceId` properly distinguishes logical endpoints and protocols.
4. `instanceId` is unique and stable across retries.
5. Host/port is an endpoint reachable by consumers.
6. Registration is created only after the endpoint has bound.
7. Auto-registration and manual registration never own the same record.
8. Every registration has an appropriate health check.
9. Deregistration runs before the endpoint stops.
10. Retries do not create duplicate records.
11. Consumers query only the matching `serviceId`.
12. Metadata follows a schema and contains no secrets.
13. Integration tests verify actual records and `ServiceInstance` objects.
14. Metrics/logs exist to detect duplicate or stale registrations.

The core takeaway is: **ServiceRegistry lets you manage registrations at an abstraction level, but it is not a license to create arbitrary extra records.** Only extend when an independent logical endpoint requires separate discovery; keep identity, metadata, health checks, and lifecycle consistent so consumers always receive the right address.

## 20. References

- Spring Cloud Commons — Common Abstractions, ServiceRegistry and auto-registration: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons — ServiceRegistry source: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/ServiceRegistry.java
- Spring Cloud Commons — AbstractAutoServiceRegistration lifecycle: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.java
