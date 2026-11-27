# Migrating from Fixed Addresses or SimpleDiscoveryClient to a Registry

When a microservice calls another service using a fixed IP and port, every time the provider changes address or scales replicas up or down, consumers may need configuration edits and redeployment. `SimpleDiscoveryClient` lets you place static URIs in configuration and look them up through the `DiscoveryClient` abstraction, but the instance list is still maintained by humans; it cannot automatically detect new replicas or recognize stopped instances.

Moving to a registry like Eureka, Consul, or ZooKeeper lets providers register instances under a service name while consumers look up instances by logical name. If consumers already use `DiscoveryClient` and Spring Cloud LoadBalancer, most service-calling code can remain unchanged; the main changes lie in the discovery provider, registry configuration, advertised addresses, and health check operations.

This lesson belongs to the `Scaling and Migration` chapter in the `SPRING_CLOUD_SERVICE_DISCOVERY` module. The module helps learners understand service-name instance lookup via `DiscoveryClient`, `ServiceRegistry`, Eureka, or Consul, along with registration lifecycles, health checks, load balancing, security, and resolving registry drift. This guide walks through migrating from fixed URLs or `SimpleDiscoveryClient` to a dynamic registry in stages, with verification and rollback.

## 1. Three Common Ways to Locate Services

Before migrating, identify which approach each application currently uses. All three approaches below may coexist within one system.

| Calling Style | Example | Who Manages the Address List? | Main Limitation |
|---|---|---|---|
| Hard-coded address | `http://10.0.1.21:8080` in code | Developers or separate config files. | Addresses are tightly coupled to the environment; changing IP/port requires updating consumers. |
| `SimpleDiscoveryClient` | `http://inventory-service` with static URIs in YAML | Operators declare each URI in configuration. | Has the discovery abstraction, but does not auto-register, monitor, or update instances. |
| Registry-backed discovery | `http://inventory-service` with Eureka/Consul | Providers register; the registry tracks state; consumers query. | Requires operating the registry, security, health checks, and handling caching/propagation delay. |

The goal of migration is not merely replacing IPs with names. The goal is shifting responsibility for maintaining instance lists from scattered config files to a controlled registration and discovery lifecycle.

## 2. Why Are Fixed Addresses Hard to Scale?

Suppose `order-service` calls `inventory-service` at `http://10.0.1.21:8080`.

- When inventory moves hosts, the old address becomes invalid.
- When scaling from one to three replicas, consumers do not know the new addresses.
- When a replica stops, consumers may still keep sending requests to the old address.
- Each environment—dev, test, staging, and production—needs a distinct set of addresses.
- Multiple consumers must be updated simultaneously, creating deployment coupling across services.
- Internal addresses may be hard-coded in source, Docker images, or manifests, making topology changes hard to control.

Example legacy configuration:

```yaml
clients:
  inventory:
    base-url: http://10.0.1.21:8080
```

Consumer reading the URL directly:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://10.0.1.21:8080")
        .build();
```

This code has no awareness of a registry. It always calls one exact configured address with no instance selection step.

## 3. What Does SimpleDiscoveryClient Solve, and What Does It Not?

`SimpleDiscoveryClient` is a `DiscoveryClient` implementation in Spring Cloud Commons. When no registry-backed `DiscoveryClient` is on the classpath, Spring Cloud can use this implementation and read instances from static configuration under the `spring.cloud.discovery.client.simple.instances` prefix.

Example:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
            pricing-service:
              - uri: http://10.0.2.31:8090
```

Consumers can query through the common abstraction:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
```

This is a step forward from hard-coding URLs in code: consumers only know the service ID and can use Spring Cloud LoadBalancer to pick a URI from the list. However, the URIs are still static data. When replicas change, operators must update configuration and redeploy or refresh configuration via a separate mechanism.

### 3.1. SimpleDiscoveryClient Is Not a Registry Server

`SimpleDiscoveryClient` does not provide a centralized server for providers to register with. It does not auto-detect new processes, receives no heartbeats from providers, and has no mechanism to remove stopped instances. It returns the list declared in configuration.

Therefore:

- You can use `SimpleDiscoveryClient` in local development, testing, or small, stable topologies.
- You can use it as an intermediate step to remove physical addresses in favor of service IDs in consumer code before deploying a registry.
- Do not treat a static URI list as proof that instances are healthy.
- You must manually update configuration if addresses or replica counts change.

### 3.2. SimpleDiscoveryClient and DiscoveryClient Are Two Different Concepts

`DiscoveryClient` is the abstraction; `SimpleDiscoveryClient`, `EurekaDiscoveryClient`, and `ConsulDiscoveryClient` are concrete implementations. Thus, if code already depends on `DiscoveryClient`, switching from Simple to Eureka/Consul usually does not require rewriting lookup logic.

What changes is the implementation configured in the application context and the data source it queries. Inspect the actual beans, especially when an application has multiple discovery integrations or `CompositeDiscoveryClient` aggregating multiple sources.

When multiple discovery implementations share the classpath, do not assume every client combines lists in the same way. Clients are ordered (`Ordered`); in the reactive composite, the default may return the fastest non-empty result, whereas `spring.cloud.discovery.reactive.combine-instances=true` combines results from clients. `spring.cloud.discovery.reactive.order-enforced=true` can be used to query in configured order. Therefore, when switching sources, explicitly verify which implementation is active, its order, and its combine mode; do not let old static URIs continue appearing unexpectedly.

## 4. Migrate from Hard-Coded URLs to Service IDs First

If consumers currently call IP/port directly, decouple URLs from code and switch to service IDs first. During this phase, `SimpleDiscoveryClient` can hold the static list.

Example configuration:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
```

Create a load-balanced `WebClient.Builder`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Consumer uses only the service ID:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public Mono<Item> findItem(String id) {
        return webClient.get()
                .uri("/api/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

`Item` is an application-defined DTO. The URL `http://inventory-service` is a service ID, not a real DNS hostname. `@LoadBalanced` enables Spring Cloud LoadBalancer to resolve the service ID through the discovery client.

After this step, consumers are decoupled from physical addresses. The list is still static, but it can be swapped for registry-backed discovery without changing URLs in client code, provided the service ID stays stable.

## 5. Standardize Service Names Before Adding a Registry

Choose one logical name per service and use it consistently across providers, consumers, dashboards, manifests, and deployment documentation.

Example:

| Component | Value |
|---|---|
| Provider's `spring.application.name` | `inventory-service` |
| Service name registered in the registry | `inventory-service` |
| Service ID called by consumers | `inventory-service` |
| URL in LoadBalanced client | `http://inventory-service` |

Do not use IPs, Pod hostnames, or instance IDs as service names. A service name identifies a group; an instance ID identifies each running instance.

Before migration, check:

- Does any service use different names across environments?
- Does any consumer call an old alias name?
- Are there registry-specific overrides like `eureka.instance.appname` or `spring.cloud.consul.discovery.service-name`?
- Are there casing or hyphenation discrepancies?
- Does the service name collide with another service in the same registry/namespace?

If a service name must change, execute it as a separate compatibility change: register the new name, migrate consumers by group, observe traffic, and only then drop the old name. Never rename providers and consumers simultaneously across the entire system without a transition window or compatibility aliases.

## 6. Choose a Registry and Prepare Infrastructure

Select a registry based on your operating environment and system requirements:

| Option | When Appropriate | Preparation Required |
|---|---|---|
| Eureka | Existing Spring Cloud Netflix ecosystem needing client/server registry and health/lease integration. | Eureka Server cluster, peer configuration, TLS/auth at the appropriate layer, backup/monitoring, and client starter. |
| Consul | Need a service catalog, health checks, ACLs, and potential integration with non-JVM workloads. | Consul agents/servers, datacenter, ACL tokens, TLS, health checks, and network access. |
| Zookeeper | System already uses ZooKeeper/Curator or needs znode-based service discovery. | ZooKeeper ensemble, ACL/authentication, root path, Curator client, and registration lifecycle. |
| Kubernetes Service/DNS | Workloads run inside Kubernetes and locate services via cluster names. | Kubernetes Services, selectors, readiness, DNS, NetworkPolicies, and port mappings. |

Do not introduce another registry if the platform already provides suitable discovery. For example, applications running solely inside Kubernetes can use Service DNS directly; Spring Cloud Kubernetes `DiscoveryClient` is useful when needing Pod/`ServiceInstance` lists or Spring Cloud LoadBalancer integration.

The registry-backed examples in this guide cover Eureka, Consul, and ZooKeeper. Choose one registry as the primary source per service during the transition phase to avoid hard-to-explain discovery results.

## 7. Switch Providers to Self-Registration

Providers need the corresponding discovery starter and registry connection configuration. `spring.application.name` is the common default service name; instance ID, host, port, and metadata must be advertised accurately.

### 7.1. Provider with Eureka

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Example configuration:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
  instance:
    instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
    prefer-ip-address: true
```

`POD_UID` can be injected from the Kubernetes Downward API or deployment platform. On VMs/other containers, use a platform-provided hostname or instance ID to guarantee concurrent replicas do not collide on ID within the application name.

Example injecting Pod UID into a container:

```yaml
env:
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
```

The Eureka client typically auto-registers and renews leases per lifecycle. Do not manually call `ServiceRegistry.register()` if auto-registration is active; manual calls can create duplicate registrations or lifecycle conflicts.

### 7.2. Provider with Consul

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Example configuration:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul.internal
      port: 8500
      discovery:
        register: true
        service-name: inventory-service
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
        health-check-path: /actuator/health
        health-check-interval: 15s

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

The Consul Agent must be able to reach the registered host/port and health endpoint. If the application sits behind NAT, inside containers, or across multiple networks, the advertised address must be reachable by consumers/agents; never assume `localhost` or a container IP is always valid.

### 7.3. Provider with Zookeeper

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
```

Example configuration:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Zookeeper integration stores service instances under a root path. Configure authentication/ACLs and instance IDs suitable for your environment, then verify actual znodes, advertised host/port, and session lifecycle before migrating consumers.

These Maven examples only show the starters. Manage Spring Cloud versions via a release train BOM compatible with your Spring Boot version; do not mix Eureka, Consul, ZooKeeper, and LoadBalancer versions from different release trains.

### 7.4. Verify Provider Registered Properly

Before switching consumers, verify:

1. Service name matches the standard.
2. Each replica has a distinct instance ID.
3. Advertised host and port are reachable from consumers.
4. Health check reflects readiness to receive traffic.
5. Required metadata such as zone/version is present.
6. On graceful provider shutdown, the registration is deregistered or transitions appropriately.

Do not switch consumers just because provider logs say "registered." Inspect the registry catalog/dashboard and invoke the endpoint from the actual network path.

## 8. Switch Consumers to Registry-Backed DiscoveryClient

Once providers register reliably, add the discovery starter on the consumer side and configure the registry endpoint. If consumers already use `DiscoveryClient` or `@LoadBalanced WebClient`, most business code stays untouched.

### 8.1. Consumer with Eureka

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

If using `@LoadBalanced WebClient.Builder` and your version's dependency graph does not bring LoadBalancer onto the classpath, add the starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Configuration:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
```

`register-with-eureka` controls whether the consumer registers itself; `fetch-registry` controls whether the client downloads the registry list to discover other services. If an application only calls services and does not need to advertise itself, these two flags can be configured independently by role.

### 8.2. Consumer with Consul

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Minimal configuration:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: consul.internal
      port: 8500
      discovery:
        register: true
```

If a consumer does not need to register itself into Consul, disable registration via integration configuration while keeping discovery enabled for service lookups. Verify the exact property for your release train.

### 8.3. Consumer with Zookeeper

Consumers use the same starter and ensemble/root path as providers:

```yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: false
        root: /services/production
```

`register: false` keeps a consumer-only role if the application does not need to advertise itself. Discovery must still have ACL permissions to read the root path and instance znodes.

### 8.4. DiscoveryClient API Without Knowing the Specific Registry

Service-checking code can continue using the common abstraction:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Spring configures the implementation via starter/auto-configuration. Do not inject `EurekaClient` or Consul clients directly into business services unless provider-specific APIs are required; keeping the abstraction makes switching registries much easier.

## 9. Switching List Sources Without Changing Business URLs

If consumers call `http://inventory-service` via `@LoadBalanced WebClient.Builder`, the URL can remain identical when migrating from `SimpleDiscoveryClient` to Eureka, Consul, or ZooKeeper.

| Before Migration | After Migration |
|---|---|
| `SimpleDiscoveryClient` returns static URIs. | Eureka/Consul/ZooKeeper return registered instances. |
| `spring.cloud.discovery.client.simple.instances` holds IPs/ports. | Registry starter and registry endpoint are configured. |
| Consumer uses service ID `inventory-service`. | Consumer continues using service ID `inventory-service`. |
| Operators update static URIs. | Providers auto-register, renew, and deregister. |
| Health does not auto-update per process without a custom mechanism. | Health/lease/checks are updated by the registry integration per config. |

During the switch, remove legacy static entries from production configuration. If `SimpleDiscoveryClient` and a registry client are both configured, or `CompositeDiscoveryClient` is active, lists may be aggregated from multiple sources depending on the application context. An old static URI could continue appearing and be picked by LoadBalancer.

Do not assume adding a Eureka/Consul starter automatically disables all custom `DiscoveryClient` beans or static lists. Inspect bean composition and `getServices()`/`getInstances()` outputs after migration.

## 10. Spring Cloud LoadBalancer and Instance Selection

Registry-backed discovery only supplies the instance list. Spring Cloud LoadBalancer chooses one instance per request. You can use the default algorithm or configure policies by service ID.

WebClient example:

```java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
```

URL using service ID:

```java
webClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .retrieve();
```

When switching from a static list to a registry, verify:

- Suppliers pull instances from the right discovery client.
- LoadBalancer caches do not retain static or stale URIs.
- Health states are applied properly.
- Zone/metadata filters do not inadvertently filter out all instances.
- Retries and timeouts do not mask wrong service names or empty registries.

## 11. Advertised Addresses Must Be Reachable from Consumers

A common migration bug is that a provider registers successfully but advertises an unreachable address. For example, an application inside a container registers `127.0.0.1:8080`; consumers in other containers cannot call the provider's loopback address.

When configuring the registry, verify:

1. Which network interface does the provider bind to?
2. Which host/IP does the registry record?
3. Do consumers run in the same subnet, VPC, Kubernetes cluster, or a different network?
4. Are ports published/mapped through containers or a service mesh?
5. Do TLS certificates match the hostname advertised in the registry?

For Eureka, adjust `eureka.instance.hostname`, `eureka.instance.ip-address`, and `prefer-ip-address` depending on the environment. For Consul, verify the registered instance address, agent network, and corresponding discovery properties. Do not pick an IP merely because it is the container's IP; pick an address routable from every relevant consumer.

## 12. Phased Migration

Do not switch every provider and consumer at once. A roadmap can be split into the following phases:

### Phase 1 – Map Dependencies

- List all hard-coded internal URLs/IPs/ports.
- Separate internal endpoints from external endpoints outside service discovery.
- Record current service names, ports, protocols, health paths, and replica counts.
- Identify which consumers already use `DiscoveryClient`, `SimpleDiscoveryClient`, or `@LoadBalanced`.
- Identify network paths and addresses providers can advertise.

### Phase 2 – Standardize Service IDs

- Choose a stable logical name for every service.
- Standardize `spring.application.name` and registry-specific overrides.
- Finalize a unique instance ID strategy per replica.
- Define metadata such as zone/version if needed.
- Retain old aliases if a compatibility period is required.

### Phase 3 – Deploy the Registry

- Set up the Eureka/Consul cluster or confirm the discovery platform is ready.
- Configure networking, TLS, authentication, ACLs, and monitoring.
- Test failover, backups, and access permissions.
- Do not migrate all consumers until the registry is stable.

### Phase 4 – Migrate Providers First

- Add the discovery starter and configure the registry endpoint.
- Enable auto-registration.
- Verify service name, instance ID, host/port, and health checks.
- Scale providers to multiple replicas and confirm every instance appears distinctly.
- Test graceful shutdown and deregistration.

### Phase 5 – Canary Consumer Migration

- Pick a low-risk consumer.
- Add the registry client and keep standardized service IDs.
- Switch URLs from IPs to service IDs via LoadBalancer.
- Monitor instance counts, error rates, timeouts, latency, and cache age.
- Expand to other consumers once the canary stabilizes.

### Phase 6 – Remove Static Sources

- Remove `spring.cloud.discovery.client.simple.instances` from production profiles once unused.
- Remove legacy internal base URL properties and code building clients directly from IPs.
- Verify no custom discovery bean still returns unwanted static URIs.
- Retain static configuration only in test/local profiles if still useful.

### Phase 7 – Verify and Close Migration

- Scale providers up and down.
- Stop an instance and verify health/deregistration removes it from discovery.
- Simulate temporary registry or peer unavailability.
- Confirm consumers handle timeouts/retries and stale caches properly.
- Document rollback runbooks and registry ownership.

## 13. Before-and-After Migration Example

### Before: Fixed Address in Application Config

```yaml
clients:
  inventory:
    base-url: http://10.0.1.21:8080
```

```java
WebClient inventoryClient = WebClient.builder()
        .baseUrl(inventoryBaseUrl)
        .build();
```

### Intermediate Step: SimpleDiscoveryClient

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
```

Consumers switch to `@LoadBalanced WebClient.Builder` and call `http://inventory-service`.

### After: Eureka Registry

Provider:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
```

Consumer:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
```

Consumers still call `http://inventory-service`; the list source shifts from static YAML to the registry. Providers register each replica, the registry maintains state, and LoadBalancer picks instances from discovery results.

## 14. Controlled Rollback

Migration needs a fallback plan if the registry or client integration fails.

A rollback plan can include:

1. Keep the static URI list in a temporary profile/secret/config version during the canary phase.
2. Use a feature flag or deployment config to select a tested discovery source.
3. If the registry has an outage, switch only affected canary consumers back to a verified working static source.
4. Do not turn on both sources concurrently without knowing how `CompositeDiscoveryClient` aggregates results.
5. When reverting to static, verify the URI list contains no stopped instances and enough live replicas.
6. Log the rollback timestamp, service ID, consumer, and reason.

Static fallback is not automatically safe. If old addresses have already changed, rolling back to stale static config can worsen failures. Maintain a verified fallback list and set a sunset deadline once migration stabilizes.

## 15. Common Pitfalls During Migration

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `getInstances()` returns empty | Provider has not registered, wrong service ID, or consumer points to wrong registry. | Check service name, registry endpoint, profile, and provider logs. |
| Provider is in registry but consumer does not see it | Consumer points to wrong cluster/datacenter/namespace or cache has not refreshed. | Compare endpoints, namespaces, and most recent fetch timestamps. |
| Consumer still calls old IP | Hard-coded URL remains in code/config or static discovery source is still active. | Search all base URL configs, `SimpleDiscoveryClient`, and custom beans. |
| Duplicate records for one replica | Simple and registry sources are aggregated or provider registered twice. | Check `DiscoveryClient` beans, `CompositeDiscoveryClient`, and auto-registration. |
| Registry has instance but calls time out | Advertised host/port is unreachable from consumer. | Check routes, container port mapping, DNS, firewalls, and TLS. |
| Only one instance visible when scaling replicas | Duplicate instance IDs or failed provider registration. | Inspect per-replica IDs and registry-native records. |
| Old instance continues being selected | Registry health/lease or cache has not updated. | Check health checks, deregistration, and LoadBalancer cache. |
| Works locally but fails in production | Different profiles, service URLs, credentials, or networks. | Compare resolved config and connectivity from production runtime. |
| Consumer uses wrong service name | `spring.application.name` or overrides differ. | Standardize service IDs and inspect `getServices()`. |
| Multiple DiscoveryClients appear after adding starter | Multiple registry integrations or custom beans coexist. | Identify primary source, order, and composite output; remove redundant sources. |

## 16. Post-Migration Testing

Do not just test a single successful request. Test lifecycle behavior and topology changes:

- Start two or more provider replicas and confirm the registry lists all instances.
- Verify each instance has a distinct ID and reachable address.
- Call the consumer repeatedly through LoadBalancer and observe selected instances.
- Scale providers up and confirm consumers see new instances within the expected refresh window.
- Stop a provider and verify health/deregistration removes the instance from selection.
- Restart a provider and verify the new registration does not overwrite running replicas.
- Temporarily disconnect the registry or a peer to confirm consumers handle discovery failures and existing caches.
- Verify TLS/ACLs/tokens and least-privilege permissions.
- Confirm old static sources no longer affect production lists.

Example test using `DiscoveryClient`:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

assertThat(instances).isNotEmpty();
assertThat(instances)
        .allSatisfy(instance -> {
            assertThat(instance.getHost()).isNotBlank();
            assertThat(instance.getPort()).isPositive();
        });
```

Tests must run in a context configured with the registry and after test provider instances have registered successfully. For unit tests, mock `DiscoveryClient`; for integration tests, use a registry testcontainer or a test environment with a live registry.

## 17. Migration Completion Checklist

| Category | Question |
|---|---|
| Inventory | Have all hard-coded internal URLs/IPs been located? |
| Service ID | Do providers and consumers use the same logical name? |
| SimpleDiscoveryClient | Are static URIs still configured in production profiles? |
| Registry | Does the registry cluster/agent have health, TLS, ACLs, and monitoring? |
| Provider | Does every replica register with a unique instance ID and reachable address? |
| Health | Do health checks reflect actual readiness and endpoints? |
| Consumer | Do consumers use `DiscoveryClient`/LoadBalancer instead of physical URLs? |
| Composite sources | Are there unexpected extra discovery sources or custom static beans? |
| Network | Are advertised hosts/ports reachable from consumers? |
| Cache | Have registry client and LoadBalancer TTL/refresh intervals been evaluated? |
| Rollout | Have canary testing, scale tests, and rollback been verified? |
| Security | Are credentials kept out of public source/config and scoped to least privilege? |
| Observability | Do metrics/logs cover registrations, health, empty discovery, and request failures? |

## Conclusion

Fixed addresses bind consumers to a physical endpoint. `SimpleDiscoveryClient` brings static URI lists under the `DiscoveryClient` abstraction, enabling consumers to use service IDs and LoadBalancer while still requiring operators to maintain the list. Registries such as Eureka, Consul, or ZooKeeper shift instance list maintenance to provider registration, heartbeats/sessions/health, and consumer discovery.

A safe migration starts by removing addresses from business code, standardizing service IDs, and switching consumers to `DiscoveryClient`/LoadBalancer. Next, deploy the registry, migrate providers to register first, verify instance IDs, hosts/ports, and health, and then roll out consumers via canary. Finally, remove static sources, verify no duplicate discovery sources remain, and test scaling, shutdowns, registry outages, and rollback. If service IDs remain stable, most service-calling code can stay untouched when changing discovery sources.

## References

- [Spring Cloud Commons – DiscoveryClient and SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient abstraction and static instance configuration.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): discovery integration, suppliers, caching, and instance selection.
- [Spring Cloud Netflix Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): instance registration and Eureka client configuration.
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html): service names, instance IDs, health checks, and Consul registration.
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html): service registration, discovery, and root path configuration.
