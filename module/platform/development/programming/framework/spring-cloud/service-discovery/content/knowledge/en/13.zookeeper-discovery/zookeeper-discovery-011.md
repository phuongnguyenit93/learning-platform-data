# Limits of Using ZooKeeper for Discovery and Scope of Dependency Management

Apache ZooKeeper was designed as a distributed coordination service. It provides a znode data tree, sessions, ephemeral nodes, watches, and consensus mechanisms so processes can coordinate with one another. Spring Cloud Zookeeper uses Apache Curator to build service registration, discovery, and client-side load balancing on top of those primitives.

This integration is useful when a system already operates ZooKeeper for coordination or needs to share a lightweight discovery platform. However, ZooKeeper is not a specialized service registry with built-in health checks, routing, and business dependency management. Development teams must understand the limits of sessions, watches, quorum, data size, and how Spring Cloud extends those primitives.

This lesson focuses on two scopes: the limits of ZooKeeper when used as a service discovery platform and the scope of the **Spring Cloud Zookeeper Dependencies** feature. Distinguish this runtime feature from Maven or Gradle dependencies: it declares which services an application intends to call, rather than managing JAR libraries or remote service lifecycles.

## 1. What was ZooKeeper designed for?

ZooKeeper is a coordination service for distributed applications. It provides a tree-structured namespace where each znode can hold small amounts of data and child znodes. Applications use primitives such as create, delete, exists, get data, set data, and get children to build higher-level capabilities.

Key characteristics:

- Data is organized by path, such as `/services/inventory-service/instance-a`.
- Each znode can hold a small payload along with version and metadata.
- Clients connect to a server in the ensemble, send requests and heartbeats, and receive watch events.
- The ensemble is replicated; a majority of servers must stay active for the ZooKeeper service to keep serving.
- ZooKeeper suits read-heavy workloads and small coordination data rather than storing large business datasets.

Spring Cloud Zookeeper does not turn ZooKeeper into a full-featured service discovery database. It uses the Curator Service Discovery Extension to store instance info and expose APIs compatible with Spring Cloud.

~~~mermaid
flowchart TD
    APP["Spring Boot service"] --> SCZ["Spring Cloud Zookeeper"]
    SCZ --> CUR["Apache Curator"]
    CUR --> ZK[("ZooKeeper ensemble")]
    ZK --> ZNODE["Znode registration tree"]
    CON["Consumer"] --> DC["DiscoveryClient"]
    DC --> SCZ
    DC --> LB["Spring Cloud LoadBalancer"]
    LB --> HTTP["HTTP client"]
    HTTP --> PROVIDER["Provider instance"]
~~~

## 2. Service discovery is built on znodes and sessions

When registering a service, Spring Cloud Zookeeper publishes metadata such as service name, instance ID, host, port, and additional attributes. The default discovery root path is `/services`; service names and instances are represented in the znode tree per Curator/Spring Cloud Zookeeper conventions.

Illustrative example:

~~~text
/services
  /inventory-service
    /inventory-a
      { host: "10.0.1.11", port: 8081, ... }
    /inventory-b
      { host: "10.0.1.12", port: 8081, ... }
  /order-service
    /order-a
      { host: "10.0.2.21", port: 8082, ... }
~~~

This is a conceptual diagram to visualize services and instances. Actual payload structures and znode naming are governed by Curator recipes and Spring Cloud Zookeeper configuration.

Discovery information can be read through `DiscoveryClient`:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
~~~

Spring Cloud Zookeeper also integrates with Spring Cloud LoadBalancer. When using the discovery starter, `ZookeeperServiceInstanceListSupplier` is configured to supply the instance list to the load balancer. Consumers can call by logical service name instead of storing hardcoded IPs and ports.

### 2.1. The starter is not a ZooKeeper server

The `spring-cloud-starter-zookeeper-discovery` dependency adds client-side libraries and enables auto-configuration. It does not install or start a ZooKeeper ensemble for the system.

You must deploy ZooKeeper servers separately, configure connections, and ensure applications can reach the ensemble. If ZooKeeper runs outside `localhost:2181`, configure:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
~~~

The host list must match the ensemble topology. Each environment should manage connect strings, authentication, and ACLs via secure deployment configuration.

## 3. First limit: registration is tied to the session

A central characteristic of the Curator Service Discovery model is that registrations typically use **ephemeral znodes**. An ephemeral node exists while the session that created it remains valid; when the session expires, ZooKeeper deletes ephemeral nodes belonging to that session.

This cleans up registrations when a process genuinely loses its session without requiring a separate cleanup job. Yet it also introduces behaviors that must be understood clearly:

- Losing a TCP connection briefly does not mean the session has expired.
- If the client reconnects before the session timeout, the session can continue and ephemeral registrations remain intact.
- If the session expires, registrations are deleted on the ZooKeeper side.
- When the client receives notice of session expiration, the old session cannot keep using deleted ephemeral nodes. Curator or the integration must establish a new session and re-register the instance; the application should verify this recovery process.
- In the interval between session expiry and re-registration, consumers may not see the instance.

Example of a container hitting a network partition:

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant Z as ZooKeeper
    participant C as Consumer

    P->>Z: Register ephemeral znode
    Z-->>C: Instance appears
    Note over P,Z: Network partition
    P--xZ: Heartbeat interrupted
    Note over P,Z: Session timeout expires
    Z-->>C: Ephemeral znode deleted
    P->>Z: Reconnect with new session
    P->>Z: Register again
    Z-->>C: Instance appears again
~~~

Do not treat a few seconds of lost connectivity as proof that an instance was removed from the registry. Session state and session timeout determine when ephemeral nodes are cleaned up.

### 3.1. Session liveness is not application readiness

An ephemeral node reflects ZooKeeper session lifecycle, without directly proving that business APIs are healthy.

A process can:

- Maintain its ZooKeeper connection and keep its session alive normally.
- Still retain its ephemeral registration in the znode tree.
- Yet have a failed database or message broker, preventing APIs from handling requests.

Conversely, an application may temporarily lose its ZooKeeper connection while still processing in-flight requests. Discovery and health must be treated as two distinct signals.

If readiness must be reflected, design dedicated health checks and update instance status according to policy. Do not use session liveness as an HTTP health probe replacement for Actuator.

## 4. Second limit: health status is less complete than a dedicated registry

ZooKeeper provides primitives for storing data and notifying on changes; ZooKeeper itself does not actively poll a provider's HTTP endpoints to verify readiness. Nor does the Curator Service Discovery recipe offer a full state model like Eureka.

Spring Cloud Zookeeper adds support for instance status via metadata. For example, `OUT_OF_SERVICE` status is stored in the payload, and `ZookeeperServiceInstanceListSupplier` filters out instances whose status is not `UP`. If the status field is empty, the implementation treats the instance as `UP` for backward compatibility.

Key points to keep in mind:

- This behavior is coordinated by Spring Cloud Zookeeper and LoadBalancer, not a native ZooKeeper health state.
- `OUT_OF_SERVICE` can be used to stop including an instance in load-balancing lists.
- Changing status does not automatically finish in-flight requests; graceful shutdown and connection draining must still be handled separately.
- Do not assume every Actuator health status is automatically translated into znode status.
- If databases, brokers, or dependencies must be checked, the application must design appropriate health indicators and status-update mechanisms.

Initial status and instance details can be configured via `spring.cloud.zookeeper.discovery.*` properties. Example:

~~~yaml
spring:
  cloud:
    zookeeper:
      discovery:
        register: true
        initial-status: UP
        root: /services
        instance-host: 10.0.1.11
        instance-port: 8081
~~~

Property names and values must match the project's Spring Cloud Zookeeper version. `instance-host` must be an address reachable by consumers, not necessarily loopback or a container-only internal address.

### 4.1. Using OUT_OF_SERVICE during maintenance

Spring Cloud Zookeeper provides an Actuator endpoint for ServiceRegistry to change instance status. Example using HTTPie:

~~~bash
http POST http://localhost:8081/service-registry status=OUT_OF_SERVICE
~~~

`ZookeeperServiceInstanceListSupplier` excludes instances whose status is not `UP` from the list used for load balancing. After updating, verify consumers have received the new data before stopping the process.

A drain flow should include:

1. Transition the instance to `OUT_OF_SERVICE`.
2. Wait for discovery/load balancers on consumers to update.
3. Stop accepting new requests at the application or ingress, if any.
4. Complete in-flight requests.
5. Stop the application and allow the session to close or the registration to deregister.

Changing status alone does not guarantee every consumer refreshes instantaneously. Test cache behavior and propagation delay for your exact version.

## 5. Third limit: watches are not a durable event stream

ZooKeeper supports watches on znodes so clients receive notifications when data changes. Watches are very helpful to avoid constant polling, but standard watches are **one-time triggers**: after firing, the client must register a new watch to receive subsequent changes.

Therefore:

- A watch event only signals that data changed; the client must re-read the updated state.
- There is a gap between receiving an event and registering the next watch.
- A znode may change multiple times during that gap; clients must not treat watches as an audit log of every modification.
- While disconnected, a client receives no watch events.
- Clients must handle session events and re-read state after connectivity is restored.

Starting in ZooKeeper 3.6, persistent recursive watches are supported, but verify whether your server, client, and integration libraries use that capability. Do not assume Spring Cloud Zookeeper Dependency Watcher turns ZooKeeper into a message bus.

### 5.1. Using watches safely

Upon receiving a change notification, the general handling flow is:

1. Re-read the current data of the service or dependency.
2. Update the internal cache from the fresh snapshot.
3. Re-register the watch if using standard watches.
4. When receiving session disconnected, switch the application to a safe-mode policy.
5. After reconnecting or establishing a new session, resynchronize state rather than relying solely on received events.

If ordered processing of every business event without loss is required, use a message broker or proper event log. ZooKeeper watches are primarily state-change signals.

## 6. Fourth limit: quorum and ensemble availability

ZooKeeper runs as an ensemble of multiple servers. Servers maintain replicated state using consensus. The ensemble requires a majority of servers to remain active to keep serving updates.

Example with a three-server ensemble:

| Active servers | Quorum present? | Impact |
|---|---|---|
| 3/3 | Yes | Normal operation |
| 2/3 | Yes | Service can still be maintained |
| 1/3 | No | Cannot proceed with updates requiring quorum |

If quorum is lost, providers cannot register new instances, update status, or deregister as expected. Consumers may temporarily retain previously read data, though that data may be stale.

Do not treat ZooKeeper as a registry writable on every node during network partitions. Design applications to tolerate:

- Transient connection errors.
- Disconnected and expired sessions.
- Registrations being deleted and recreated.
- Inability to update the registry when the ensemble loses quorum.
- Consumers observing stale snapshots during resynchronization.

If discovery is mandatory for service startup, explicitly define policy when ZooKeeper is unavailable: fail startup, perform bounded retries, or run with controlled fallback configuration.

## 7. Fifth limit: workload and data scale

ZooKeeper is optimized for small coordination data and read-dominant workloads. It keeps critical state in memory while maintaining transaction logs and snapshots. Znode data should generally stay small, from a few bytes to a few kilobytes.

This affects how it is used as a registry:

- Store only metadata necessary to locate instances.
- Never store business payloads, large configuration files, or request history in registration znodes.
- Avoid high-frequency continuous status updates.
- Avoid creating/deleting znodes per request or per user session.
- Limit unnecessary watches and client connections.
- Monitor heap, latency, connection counts, watch counts, and transaction processing times.

Every provider registration, deregistration, or metadata update generates write operations. In systems with large instance counts and high churn, the registry puts extra pressure on both the ensemble and clients.

No single fixed instance threshold applies to every system. Capacity depends on ensemble configuration, hardware, client count, znode sizes, change frequency, and query patterns.

## 8. Sixth limit: client-side discovery does not replace routing

Spring Cloud Zookeeper supplies `DiscoveryClient` and integrates with Spring Cloud LoadBalancer. Consumers query instances and pick endpoints on the client side.

It does not provide a centralized L7 proxy that every request passes through. Applications still need a load-balanced HTTP client, such as OpenFeign, `RestTemplate`, or `WebClient`.

Example calling a service by logical name:

~~~java
@LoadBalanced
@Bean
RestTemplate restTemplate() {
    return new RestTemplate();
}
~~~

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

The load balancer can select an instance from the list supplied by `ZookeeperServiceInstanceListSupplier`. Yet consumers must still handle timeouts, connection failures, retries, and circuit breakers. Finding an endpoint in ZooKeeper does not guarantee that endpoint will respond successfully.

Moreover, if the registered address is not routable from the consumer, discovery may return a syntactically valid URI while requests still fail. Always verify host, port, and network policies from the consumer's actual environment.

## 9. Scope of Spring Cloud Zookeeper Dependencies

The name **Zookeeper Dependencies** in Spring Cloud refers to runtime services an application declares as dependencies to invoke via Feign, `RestTemplate`, or WebFlux. These are not Maven/Gradle JAR dependencies.

For instance, `order-service` needs to call `inventory-service` and `pricing-service`. The application can declare aliases and paths for those services in configuration:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      dependencies:
        inventory:
          path: /services/inventory-service
          loadBalancerType: ROUND_ROBIN
          version: v1
          contentTypeTemplate: application/vnd.inventory.$version+json
          required: true
        pricing:
          path: /services/pricing-service
          loadBalancerType: RANDOM
          required: false
~~~

In this example:

- `inventory` and `pricing` are aliases used by the application in URLs and service clients.
- `path` is the path where the service is registered in ZooKeeper.
- `loadBalancerType` declares the instance selection strategy.
- `version` and `contentTypeTemplate` support generating versioned Content-Type headers when the corresponding header feature is enabled.
- `required` determines how startup behaves if the dependency is not yet found when the application starts.

### 9.1. Alias and path serve different roles

Spring Cloud LoadBalancer expects an application ID in URLs. It does not accept a complex ZooKeeper path as a service ID. Therefore, Spring Cloud Zookeeper uses aliases to map to actual paths.

Example client calling an alias:

~~~java
@FeignClient("inventory")
public interface InventoryClient {

    @GetMapping("/items")
    List<ItemResponse> getItems();
}
~~~

The alias `inventory` is the identifier used on the Spring Cloud side. The path `/services/inventory-service` indicates where to find the registration in ZooKeeper.

Do not embed full znode paths into service IDs or logical service URLs. Keep aliases stable and configure paths in one place.

### 9.2. Scope of loadBalancerType

Spring Cloud Zookeeper Dependencies supports the documented options:

| Value | Behavior |
|---|---|
| `STICKY` | Once chosen, continues preferring the same instance |
| `RANDOM` | Selects an instance randomly |
| `ROUND_ROBIN` | Alternates across instances in round-robin order |

This is a client-side instance selection policy. It does not create server-side routing, does not guarantee perfectly even load distribution, and does not replace health checks.

### 9.3. required and startup presence checks

`required: true` means the dependency must be found when the application starts. If a required dependency cannot be located in ZooKeeper, the Spring context may fail to initialize.

`required: false` allows the application to start and logs a warning when the dependency is absent.

| Configuration | When dependency does not exist at startup |
|---|---|
| `required: true` | Startup fails |
| `required: false` | Application continues running and logs a WARN |

This is a startup presence check. It does not prove the dependency will remain healthy afterward and does not validate every request. If dependencies appear or vanish after startup, use watchers and appropriate runtime handling policies.

## 10. How far does Dependency Watcher manage state?

Spring Cloud Zookeeper provides Dependency Watcher to register listeners that monitor dependency state changes. Listeners can receive `CONNECTED` or `DISCONNECTED` events:

~~~java
public interface DependencyWatcherListener {

    void stateChanged(
            String dependencyName,
            DependencyState newState
    );
}
~~~

The application registers an implementation as a Spring bean. When a dependency changes state, the application can:

- Log events and emit metrics.
- Pause a processing flow that depends on that service.
- Report state to a monitoring component.
- Resume work once the dependency reconnects.

Dependency Watcher is not a workflow engine. It does not repair failing services, restart pods, recover databases, or guarantee in-flight requests finish.

The Dependencies feature can be disabled with `spring.cloud.zookeeper.dependency.enabled`. This property controls runtime dependencies; it is separate from `spring.cloud.zookeeper.discovery.enabled`, which controls the discovery client.

### 10.1. Presence Checker

Presence Checker helps make startup decisions based on the dependency list:

- A `required` dependency that is missing causes startup to fail under the default implementation.
- An optional dependency that is missing emits a WARN log.
- You can replace the default verifier with a `DependencyPresenceOnStartupVerifier` bean if a custom policy is needed.

This is the scope of presence checking. It does not manage transitive dependencies—such as `order-service` needing `inventory-service`, which in turn needs `database-service`—and automatically orchestrate startup order across the whole graph.

Applications still need their own timeouts, retries, circuit breakers, fallbacks, and startup policies.

## 11. Runtime dependencies are not build dependencies

Distinguish the two uses of the word dependency:

| Concept | Example | Managed by |
|---|---|---|
| Build dependency | `spring-cloud-starter-zookeeper-discovery`, Curator, ZooKeeper Java client | Maven/Gradle and Spring Cloud BOM |
| Runtime dependency | `order-service` calls `inventory-service` via alias `inventory` | `spring.cloud.zookeeper.dependencies` |
| Startup-required dependency | `required: true` for a service needed at application startup | Spring Cloud Zookeeper Presence Checker |
| Runtime dependency state | `CONNECTED` or `DISCONNECTED` | Spring Cloud Zookeeper Dependency Watcher |

`spring.cloud.zookeeper.dependencies` does not download JARs, declare `groupId`/`artifactId`, check library versions, or manage transitive library dependencies. It describes services registered in ZooKeeper that the application wants to call.

## 12. Dependency scope does not replace API contracts

Declaring a dependency alias, path, version, or Content-Type template does not automatically guarantee API compatibility between two services.

Development teams must still manage:

- Request and response contracts.
- Schemas and serialization.
- Backward compatibility across API versions.
- Authentication and authorization.
- Timeouts, retries, and idempotency.
- Circuit breakers, fallbacks, and load shedding.
- Rollout and rollback policies.

`version` in Zookeeper Dependencies configuration can be used to construct headers like `Content-Type`; it does not verify that the provider actually implements that version. If the provider registers incorrect metadata or lacks support for the requested contract, requests can still fail.

Default configured `headers` must also be reviewed for security. Never store bearer tokens or long-lived secrets in broadly shared configuration files. Use an appropriate secret management mechanism for credentials.

## 13. Dependency scope is not distributed configuration

Spring Cloud Zookeeper also includes a separate distributed configuration module. Discovery and Config both use ZooKeeper but serve different goals:

- `spring-cloud-starter-zookeeper-discovery`: service registration and discovery.
- `spring-cloud-starter-zookeeper-config`: reading application configuration from a config namespace.
- `spring.cloud.zookeeper.dependencies`: declaring runtime services an application wants to call.

Do not add Zookeeper Config if the application only uses service discovery. Conversely, adding Config does not register providers or create a DiscoveryClient.

With Spring Cloud Zookeeper Config, configuration is loaded into the Spring Environment via the version's bootstrap/config data mechanism. Current documentation describes configuration being read at startup and reloadable via the refresh endpoint; automatic watching of the config namespace is not described as implemented in that flow. Verify documentation for your exact release train before relying on instant config updates.

## 14. Build dependencies and starter scope

For discovery, the common starter is:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

If the application needs an HTTP server, add the corresponding web starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Manage the Spring Cloud version with a BOM compatible with Spring Boot:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Avoid adding arbitrary Curator or ZooKeeper client versions manually when the starter already manages versions. Spring Cloud Zookeeper uses Curator underneath; verify compatibility across the Spring Cloud release train, Spring Boot, Curator, and ZooKeeper server before overriding transitive dependencies.

If distributed configuration is needed, add `spring-cloud-starter-zookeeper-config` separately. Do not pull in an umbrella starter or unnecessary dependencies just to enable discovery.

## 15. Security and access control

ZooKeeper uses ACLs on individual znodes to control who can read, write, create, or delete nodes. ACLs are not automatically inherited by child znodes. Therefore, setting an ACL on the root path does not mean every registration beneath it is protected as intended.

Pay attention to:

- Restrict read and write permissions per service or namespace.
- Allow only authorized workloads to create registrations and change status.
- Protect client credentials and connection strings.
- Never store secrets in service metadata.
- Restrict network access to ZooKeeper client ports.
- Verify ACLs on both parent nodes and created child nodes.
- Use TLS/authentication per infrastructure and deployment version requirements.

If a client can write into another service's registration path, it can advertise bogus endpoints or tamper with discovery data. Registry write permissions should be treated as permissions affecting internal traffic routing.

## 16. When to use it and when to consider alternatives?

| Context | Assessment |
|---|---|
| System already operates ZooKeeper for coordination and team understands sessions/ACLs | Can leverage it for discovery to avoid running another platform |
| Moderate service count and churn, small registration data, mostly read operations | Fits ZooKeeper's read-dominant characteristics |
| Need integration with `DiscoveryClient` and Spring Cloud LoadBalancer | Supported via Spring Cloud Zookeeper |
| Need rich health checks, passing-only queries, multi-level status policies | Must design and test carefully; a dedicated registry may fit better |
| Very high instance create/delete rate or large watch/client counts | Must benchmark and evaluate ensemble load; consider another registry |
| System runs entirely on Kubernetes | Can use Kubernetes Service/EndpointSlice if requirements are met |
| Need service mesh, traffic policies, and network-layer observability | Consider a service mesh platform or integrated registry |

No fixed instance limit applies to every deployment. Base the decision on actual benchmarks, registration change rates, client counts, watches, metadata sizes, and ability to operate the ensemble.

## 17. Checklist before taking ZooKeeper Discovery to production

1. Determine whether ZooKeeper is an existing coordination platform or being stood up solely for discovery.
2. Deploy an ensemble with quorum and verify backups, snapshots, logs, heap, and disk.
3. Choose a session timeout suited to network conditions and recovery time.
4. Confirm providers register hosts/ports reachable from consumers.
5. Distinguish session liveness from application readiness.
6. Design health/status and draining rather than relying solely on ephemeral nodes.
7. Verify consumer refresh, watches, and behavior when sessions expire.
8. Keep znode payloads small and limit registration churn and unnecessary watches.
9. Declare only truly needed runtime dependencies; explicitly decide `required`.
10. Test Dependency Watcher and Presence Checker under service loss and reconnection scenarios.
11. Configure ACLs and authentication per path.
12. Verify Spring Cloud BOM, Curator, and ZooKeeper version compatibility.
13. Measure behavior during quorum loss, partitions, session expiry, and provider restarts.
14. Verify timeouts, retries, circuit breakers, and fallbacks on consumers.

## 18. Key takeaways

- ZooKeeper is a coordination service; Spring Cloud Zookeeper uses Curator to build registration, discovery, and LoadBalancer integration.
- Ephemeral registrations are tied to sessions. Session expiration deletes nodes, whereas brief disconnections do not immediately expire sessions.
- Session liveness does not mean the application is ready to handle business requests.
- Standard watches are one-time triggers; do not use them as a durable event log.
- Ensembles require quorum; losing a majority of servers can disrupt registration updates.
- ZooKeeper suits small coordination data and read-dominant workloads; be cautious with high churn, large payloads, and massive watch counts.
- Spring Cloud Zookeeper supports `OUT_OF_SERVICE` via metadata and the LoadBalancer supplier; this is not a full health-checking system like a dedicated registry.
- `spring.cloud.zookeeper.dependencies` declares runtime services via aliases and paths; it does not manage Maven/Gradle JARs.
- `required`, Dependency Watcher, and Presence Checker assist with presence/status checks, not replacing resilience or API contracts.
- Discovery, distributed configuration, and build dependencies are three distinct scopes; add only the starters matching your needs.

ZooKeeper can be a practical discovery platform when a system already needs coordination and the team understands operating sessions, watches, quorum, and ACLs. When using it for service discovery, keep data small, design explicit health/readiness, and limit the dependency feature to declaring and monitoring the runtime services the application actually calls.

## References

- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Service Registry and Instance Status](https://docs.spring.io/spring-cloud-zookeeper/docs/current/reference/html/)
- [Spring Cloud Zookeeper — Zookeeper Dependencies and Dependency Watcher](https://docs.spring.io/spring-cloud-zookeeper/docs/current/reference/html/)
- [Spring Cloud Zookeeper — Quick Start and Maven/Gradle setup](https://docs.spring.io/spring-cloud-zookeeper/reference/quickstart.html)
- [Apache ZooKeeper — Overview and Design Goals](https://zookeeper.apache.org/doc/current/zookeeperOver.html)
- [Apache ZooKeeper — Programmer's Guide: Sessions, Watches and ACLs](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
