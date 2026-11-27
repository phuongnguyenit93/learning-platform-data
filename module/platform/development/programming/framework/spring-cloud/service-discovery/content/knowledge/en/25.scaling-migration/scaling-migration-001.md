# When You Need a Custom DiscoveryClient

Spring Cloud provides `DiscoveryClient` as a common interface for applications to look up instances by service ID. Eureka, Consul, and several other systems already have corresponding implementations. Therefore, before writing a new `DiscoveryClient`, it is necessary to identify which exact part of service discovery does not meet your requirements: the instance data source, how services are registered, or how the LoadBalancer selects instances.

A custom `DiscoveryClient` is appropriate when an application needs to read from a proprietary catalog, an internal platform without a Spring Cloud adapter, or a service ID and metadata mapping rule that existing implementations do not support. If you only need to change the instance selection strategy, Spring Cloud LoadBalancer's `ServiceInstanceListSupplier` is usually a more suitable extension point. If you need to register or deregister services, consider a separate `ServiceRegistry`.

## 1. What Does DiscoveryClient Do?

DiscoveryClient belongs to Spring Cloud Commons. It decouples consumer code from the specific APIs of Eureka, Consul, or other providers.

A consumer only needs to know the service ID:

    List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

The application does not need to know whether the registry stores data in Eureka, Consul, or a proprietary catalog. The DiscoveryClient implementation is responsible for calling the data source, converting the result into `ServiceInstance` objects, and returning them to the consumer.

Basic flow:

    Consumer
       |
       | getInstances("inventory-service")
       v
    DiscoveryClient
       |
       | look up by service ID
       v
    Registry / Catalog / Directory
       |
       | list of host, port, scheme, metadata
       v
    List<ServiceInstance>
       |
       v
    Spring Cloud LoadBalancer
       |
       v
    Select an instance to call

DiscoveryClient is only a lookup layer. It does not send HTTP requests to target services itself and does not decide the load balancing algorithm.

## 2. The DiscoveryClient Contract

The blocking DiscoveryClient interface currently has these main methods:

    public interface DiscoveryClient extends Ordered {

        String description();

        List<ServiceInstance> getInstances(String serviceId);

        List<String> getServices();

        default void probe() {
            getServices();
        }

        default int getOrder() {
            return 0;
        }
    }

Meaning:

| Method | Responsibility |
|---|---|
| description() | Returns a human-readable description of the implementation, used in the health indicator |
| getInstances(serviceId) | Returns the known instances of a service ID |
| getServices() | Returns the service IDs known to the discovery source |
| probe() | Checks whether the implementation can still communicate with the data source |
| getOrder() | Determines the order of the implementation when multiple DiscoveryClients exist |

DiscoveryClient extends Ordered. The default value of `getOrder()` is 0. A custom implementation can override it to set an appropriate order.

Some rules to follow:

- Do not return null from `getInstances()` or `getServices()`; when there is no data, return an empty list.
- Keep service IDs consistent with how consumers call them; only normalize uppercase/lowercase if system conventions explicitly specify it.
- Return the correct host, port, scheme, and metadata so LoadBalancer can construct a valid URI.
- Distinguish between a service having no instances and a connection error to the catalog.
- Do not silently turn backend errors into an empty list; doing so makes it hard for consumers to distinguish between having no instances and a failing registry.
- Set finite timeouts for queries to the data source.

## 3. ServiceInstance Is the Standard Output Data

Each instance is represented by `ServiceInstance`. The information typically needed includes:

- instanceId: unique identifier of the instance if provided by the provider.
- serviceId: logical name of the service.
- host: reachable hostname or IP.
- port: port that the consumer will call.
- isSecure: whether the connection uses HTTPS or HTTP.
- uri: URI of the instance.
- metadata: additional key-value pairs.
- scheme: custom scheme if the implementation needs to provide one.

Spring Cloud has `DefaultServiceInstance` to convert data from a proprietary catalog into the standard object:

    new DefaultServiceInstance(
        instanceId,
        serviceId,
        host,
        port,
        secure,
        metadata
    );

Do not put unroutable information into `ServiceInstance`. For example, `localhost` inside a container can cause a consumer to mistakenly call itself. The returned host and port must fit the consumer's network.

Metadata should contain small, stable attributes such as zone, version, role, or protocol. Do not put secrets, tokens, or business data into metadata.

## 4. When Should You Write a Custom DiscoveryClient?

The following scenarios usually have clear technical reasons.

### 4.1. Having a Proprietary Catalog Source Without an Integration

An organization may use an internal platform to store services, instances, addresses, deployment regions, and statuses. If there is no Spring Cloud DiscoveryClient adapter for that platform, a custom implementation can call the catalog's REST API, SDK, or database view and convert the results into `ServiceInstance`.

Example data sources:

- Internal service directory.
- Deployment platform control plane.
- Multi-region or multi-account catalog.
- Centrally managed service mapping system.
- An in-house discovery API developed by the organization.

This case fits best when the catalog is the authoritative data source and has a stable API contract.

### 4.2. Needing Custom Service ID or Metadata Mapping Conventions

A platform may name services by namespace, tenant, region, or version. A custom DiscoveryClient can translate the application's logical name into the catalog's lookup key, and then map the results back to the standard service ID.

For example, the consumer calls:

    inventory-service

The internal catalog stores:

    prod/asia-southeast1/commerce/inventory

The adapter can perform the mapping between these two names. Make sure the mapping rules are clear, tested, and do not produce duplicate instances when data comes from multiple sources.

If filtering only relies on metadata already present in `ServiceInstance`, it can be handled in LoadBalancer instead of modifying DiscoveryClient.

### 4.3. Needing to Integrate a Specialized Protocol or API

If the catalog uses a proprietary protocol, request signing, workload authentication, or response format not directly compatible with Eureka/Consul, a custom client can act as an adapter.

The adapter should isolate protocol details inside a separate gateway/service. DiscoveryClient should only be responsible for converting catalog results into the Spring Cloud model.

Do not scatter request signing, retry, JSON parsing, or token management logic across consumers.

### 4.4. Needing to Merge Data from Multiple Sources with Custom Rules

A system may be migrating from Eureka to Consul, or have different registries per region. If requirements for merging, deduplication, source prioritization, or metadata normalization are more complex than existing configuration capabilities, a custom adapter layer can be useful.

However, first check `CompositeDiscoveryClient` and Spring Cloud's ordering capabilities. If you only need multiple implementations to coexist, there is no need to write another composite client.

When merging multiple sources, clearly define:

- Priority rules if the same instance appears in two sources.
- How to identify duplicate records.
- Which source is the source of truth when metadata differs.
- How to handle one source failing while the other source remains operational.
- How to avoid returning both old and new endpoints simultaneously during migration.

## 5. When Do You Not Need a Custom DiscoveryClient?

| Need | Appropriate Approach |
|---|---|
| Using Eureka | Add Spring Cloud Netflix Eureka Client and configure the server |
| Using Consul | Add Spring Cloud Consul Discovery and configure the agent/catalog |
| Fixed endpoint list, rarely changes | Use SimpleDiscoveryClient |
| Only want round-robin, weighted, or zone preference | Configure Spring Cloud LoadBalancer |
| Only want to filter instances by metadata | Use ServiceInstanceListSupplier or LoadBalancer configuration |
| Only need to register/deregister services | See ServiceRegistry and Registration |
| Want multiple DiscoveryClients to coexist | See CompositeDiscoveryClient and ordering |
| Only want to switch endpoints by profile | Use Spring Boot Profiles and corresponding configuration |

`SimpleDiscoveryClient` is used when there is no suitable Service-Registry-backed DiscoveryClient on the classpath. The instance list is declared using properties:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-a:8080
                  - uri: http://inventory-b:8080

If the endpoint list is known in advance and rarely changes, this approach is usually simpler than building a custom adapter.

## 6. Distinguishing DiscoveryClient, ServiceRegistry, and LoadBalancer

Three abstractions solve three different problems:

| Abstraction | Question | API or Extension Point |
|---|---|---|
| DiscoveryClient | What instances of the service exist? | getInstances(), getServices() |
| ServiceRegistry | How to register, update, or deregister an instance? | register(), deregister(), status |
| ServiceInstanceListSupplier / LoadBalancer | Which instance to choose for the current request? | Supplier and ReactorLoadBalancer |

DiscoveryClient is a read interface. Implementing DiscoveryClient does not automatically provide the ability to register the application's instance into the catalog.

Spring Cloud Commons provides `ServiceRegistry` and `Registration` for the registration side. If a custom platform needs both read and write, design the two responsibilities separately and ensure the register/deregister lifecycle is managed properly.

If you only need to change how LoadBalancer chooses instances, start with `ServiceInstanceListSupplier`. Do not put round-robin, sticky session, or retry policies into DiscoveryClient because they belong to the instance selection and service invocation layer.

## 7. Architecture Design of a Custom DiscoveryClient

The implementation should be split into three parts:

    Consumer / LoadBalancer
             |
             v
    Custom DiscoveryClient
             |
             v
    Directory Gateway
             |
             | HTTP / SDK / database
             v
    Internal Service Catalog

**Custom DiscoveryClient** fulfills the Spring Cloud contract, validates input, and transforms data.

**Directory Gateway** calls the catalog's API or SDK. This component is responsible for timeouts, authentication, retries, and translating technical errors into meaningful exceptions.

**Internal Service Catalog** is the authoritative data source, managing instances and metadata.

This separation makes it easy to unit test DiscoveryClient without starting a real catalog. The gateway can also be replaced with a mock implementation in integration tests.

## 8. Blocking DiscoveryClient Implementation Example

Suppose an organization has a `DirectoryGateway` to query the internal catalog:

    public interface DirectoryGateway {

        List<DirectoryInstance> findInstances(String serviceId);

        List<String> listServiceIds();

        void ping();
    }

    public record DirectoryInstance(
            String instanceId,
            String host,
            int port,
            boolean secure,
            Map<String, String> metadata
    ) {
    }

Implementation:

    import java.util.List;
    import java.util.Map;

    import org.springframework.cloud.client.DefaultServiceInstance;
    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.stereotype.Component;
    import org.springframework.util.StringUtils;

    @Component
    public class DirectoryDiscoveryClient implements DiscoveryClient {

        private final DirectoryGateway gateway;

        public DirectoryDiscoveryClient(DirectoryGateway gateway) {
            this.gateway = gateway;
        }

        @Override
        public String description() {
            return "Internal Directory Discovery Client";
        }

        @Override
        public List<ServiceInstance> getInstances(String serviceId) {
            if (!StringUtils.hasText(serviceId)) {
                return List.of();
            }

            return gateway.findInstances(serviceId)
                    .stream()
                    .<ServiceInstance>map(instance -> new DefaultServiceInstance(
                            instance.instanceId(),
                            serviceId,
                            instance.host(),
                            instance.port(),
                            instance.secure(),
                            instance.metadata() == null
                                    ? Map.of()
                                    : Map.copyOf(instance.metadata())
                    ))
                    .toList();
        }

        @Override
        public List<String> getServices() {
            return gateway.listServiceIds()
                    .stream()
                    .distinct()
                    .sorted()
                    .toList();
        }

        @Override
        public void probe() {
            gateway.ping();
        }

        @Override
        public int getOrder() {
            return 20;
        }
    }

The example uses Java 17 or later. `DirectoryGateway` is an application abstraction; an implementation calling the real catalog with appropriate timeouts is required.

Some design decisions in the example:

- An empty service ID returns an empty list because there is no valid lookup key.
- Instances are converted into `DefaultServiceInstance`.
- Null metadata is converted into an empty map.
- `getServices()` deduplicates and sorts service IDs for deterministic results.
- `probe()` calls a lightweight operation instead of loading the entire service list.
- `getOrder()` returns 20 to declare the implementation's order when coexisting with other clients.

In a real application, verify that host and port are valid, whether the instance is marked healthy, whether metadata conforms to the schema, and whether the URI is reachable from the consumer. If the catalog returns an error, the gateway should throw an appropriate exception so connection errors can be observed.

## 9. How to Register the Implementation in the Spring Context

For a standalone application, you can declare the implementation using `@Component` as shown above or create a bean in a `@Configuration` class. Component scanning must cover the package containing the implementation.

For a library or starter reused across multiple applications, package it as auto-configuration:

    @AutoConfiguration
    @ConditionalOnClass(DiscoveryClient.class)
    @ConditionalOnProperty(
        prefix = "acme.discovery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    public class AcmeDiscoveryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(DirectoryDiscoveryClient.class)
        DirectoryDiscoveryClient acmeDiscoveryClient(DirectoryGateway gateway) {
            return new DirectoryDiscoveryClient(gateway);
        }
    }

Register the auto-configuration class in the file:

    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

File contents:

    com.example.discovery.AcmeDiscoveryAutoConfiguration

Package and class names in the example should be replaced with the actual names of your library.

The two bean registration methods are mutually exclusive alternatives. If using `@Component` as in the blocking example, let component scan create the bean and do not redeclare that bean in auto-configuration. If packaging a starter, remove `@Component` and let auto-configuration create the bean. The `@ConditionalOnMissingBean(DirectoryDiscoveryClient.class)` condition only prevents creating duplicate beans of this custom implementation; it still allows `EurekaDiscoveryClient` or `ConsulDiscoveryClient` to coexist.

The bean condition is scoped to the custom implementation type to avoid creating two beans of the same type. Do not mechanically use `@ConditionalOnMissingBean(DiscoveryClient.class)` if the goal is to allow the custom client to coexist with Eureka or Consul. Spring Cloud can combine multiple DiscoveryClients; enforcing a single bean can break that coordination capability.

In the Spring Cloud ecosystem, the extension mechanism via `@EnableDiscoveryClient` also has metadata in `META-INF/spring.factories` under the key `org.springframework.cloud.client.discovery.EnableDiscoveryClient`. That is Spring Cloud's discovery configuration registration mechanism, whereas `AutoConfiguration.imports` is Spring Boot 3's mechanism for finding auto-configuration. When releasing a starter, follow the right integration path and the Spring Boot/Spring Cloud versions supported by the library.

`@EnableDiscoveryClient` is no longer mandatory in typical Spring Boot applications if a discovery implementation is already on the classpath and properly configured.

## 10. Handling Multiple DiscoveryClients and Precedence Order

An application can have multiple implementations, such as Eureka and an internal catalog. `DiscoveryClient` extends `Ordered` to declare precedence.

For example:

    @Override
    public int getOrder() {
        return 20;
    }

You can configure the order of built-in Spring Cloud implementations using provider-specific properties, such as `eureka.client.order` or `spring.cloud.consul.discovery.order`.

By Spring `Ordered` convention, a lower order value has higher precedence. Choose values intentionally and verify the actual client order in the application context, especially when multiple providers are enabled together.

When multiple sources exist, clearly define what ordering means:

- Which source takes priority during lookup.
- Whether to fall back to the next source when the first source has no instances.
- Whether instances from multiple sources are merged.
- Whether a query error from one source breaks the entire result.
- How instances with duplicate IDs are handled.

Do not just change the order number and assume data will merge properly. Write integration tests with two sources containing overlapping data, distinct data, and scenarios where one source fails.

For the reactive composite discovery client, Spring Cloud describes the behavior more explicitly:

- By default, instances are taken from the fastest client that returns a non-empty list.
- `spring.cloud.discovery.reactive.order-enforced=true` requires querying in order; lower-priority clients are only queried when preceding clients have no instances.
- In `order-enforced` mode, a slow high-priority client can delay the result and errors may be propagated instead of falling back.
- `spring.cloud.discovery.reactive.combine-instances=true` allows combining instances from reactive clients; an error from one client is logged without blocking results from other clients.
- If both `combine-instances` and `order-enforced` are enabled, clients are queried in the configured order.

These properties apply to the reactive composite; do not assume the same behavior for the blocking composite without checking the version in use.

## 11. Do You Need to Implement ReactiveDiscoveryClient?

Spring Cloud has two discovery contracts:

- `DiscoveryClient`: blocking API, returns `List`.
- `ReactiveDiscoveryClient`: reactive API, returns `Flux` and uses reactive probe.

If the application uses WebFlux or needs completely non-blocking lookups, consider `ReactiveDiscoveryClient`. The reactive interface has equivalent operations such as `getInstances(serviceId)`, `getServices()`, and `reactiveProbe()`.

A reactive adapter should use an HTTP client or SDK with a reactive API. Do not call a blocking SDK directly on the Reactor event loop.

If only a blocking SDK is available, you can isolate blocking operations on an appropriate scheduler like `boundedElastic`, but you need timeouts and concurrency limits. This is a transitional solution; under high load, a truly reactive adapter is usually easier to control.

It is not mandatory to implement both blocking and reactive clients if the application only uses one model. If providing both, ensure they return the same service IDs, addresses, metadata, and health rules.

## 12. Integrating with Spring Cloud LoadBalancer

After DiscoveryClient returns `ServiceInstance`, Spring Cloud LoadBalancer can use that list to select an instance for a request.

Example with `RestTemplate`:

    @Configuration
    public class ClientConfiguration {

        @Bean
        @LoadBalanced
        RestTemplate restTemplate() {
            return new RestTemplate();
        }
    }

Calling a service by service ID:

    restTemplate.getForObject(
            "http://inventory-service/api/items/42",
            Item.class
    );

LoadBalancer uses DiscoveryClient to retrieve the instance list and applies the instance selection algorithm. If the custom client returns the wrong host, port, or scheme, the request will fail even if the catalog query succeeded.

If the requirement is only filtering by zone, version, metadata, weight, sticky session, or additional health checks, inspect `ServiceInstanceListSupplier`. This is the layer dedicated to processing the instance list before LoadBalancer selects an instance.

For example, filtering instances by version metadata can be done in the supplier. DiscoveryClient still returns the complete list matching the catalog; instance selection policies remain in the LoadBalancer layer.

## 13. Performance, Timeouts, and Caching

DiscoveryClient can be called frequently as LoadBalancer refreshes its instance list. Therefore, do not let every `getInstances()` call trigger an unbounded query to the catalog.

Some guidelines:

- Set finite connect timeouts and response timeouts for `DirectoryGateway`.
- Limit the number of concurrent requests to the catalog.
- Use a TTL-based cache if the data source is slow and topology does not change per request.
- Have a refresh/invalidation policy when registrations change.
- Do not cache errors indefinitely or turn backend failures into empty results.
- Use retries with backoff and jitter; avoid thundering-herd retries when the catalog is failing.
- Monitor cache age and propagation delay to know how stale consumer data is.
- Paginate or filter on the catalog side if `getServices()` can return a very large list.
- Do not load the entire registry just to check one service if the provider offers a lightweight probe API.

The default DiscoveryClient `probe()` method calls `getServices()`. In systems with many services, loading the entire list just for a health check can waste resources. A custom client should override `probe()` to perform a lightweight connectivity check if the backend supports it.

You can configure the health indicator not to call `getServices()` and instead use `probe()`:

    spring:
      cloud:
        discovery:
          client:
            health-indicator:
              use-services-query: false

When configured this way, `DiscoveryClientHealthIndicator` uses `probe()` to check reachability. The health indicator should not turn into a full-registry query running too frequently.

## 14. Securing the Catalog Source

A custom client usually calls an internal API or SDK, so security must be handled in the gateway layer:

- Use TLS and verify certificates.
- Provision credentials via workload identity or a secret manager.
- Restrict catalog read permissions by namespace or service group.
- Do not log access tokens, passwords, or URLs containing credentials.
- Limit metadata returned to consumers.
- Enforce access checks when multiple tenants or regions exist.
- Use timeouts and response size limits to prevent abnormal responses from exhausting memory.
- Do not trust hosts, ports, or URIs returned by an unauthenticated data source.

`DiscoveryClient.getInstances(serviceId)` does not accept an arbitrary request context object. If the catalog needs tenant context or per-user permissions, design clearly how context is passed in the application. Do not rely on `ThreadLocal` in reactive calls or asynchronous processing because context may not follow the thread as expected.

If access rights vary by caller, consider whether the generic DiscoveryClient is the right abstraction or if consumers need an explicit API that takes a request context.

## 15. Testing a Custom DiscoveryClient

Testing should be divided into multiple layers.

**Unit tests for data mapping**

- Valid service ID returns the expected instances.
- Non-existent service returns an empty list.
- Metadata is preserved.
- HTTPS maps to `secure=true`.
- Host and port are mapped accurately.
- Instance IDs are neither duplicated nor lost.
- `getServices()` returns no duplicates.
- `probe()` calls the gateway's lightweight operation.

Example:

    @Test
    void mapsDirectoryInstanceToServiceInstance() {
        DirectoryInstance record = new DirectoryInstance(
                "inventory-1",
                "inventory.internal",
                8443,
                true,
                Map.of("zone", "zone-a")
        );

        when(gateway.findInstances("inventory-service"))
                .thenReturn(List.of(record));

        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        assertThat(instances).hasSize(1);
        assertThat(instances.get(0).getServiceId())
                .isEqualTo("inventory-service");
        assertThat(instances.get(0).getUri().toString())
                .isEqualTo("https://inventory.internal:8443");
        assertThat(instances.get(0).getMetadata())
                .containsEntry("zone", "zone-a");
    }

The example uses JUnit, Mockito, and AssertJ; create the mock gateway and initialize `discoveryClient` in test setup.

**Integration tests**

- Verify the bean is created properly in the Spring `ApplicationContext`.
- Verify the custom client is included in `CompositeDiscoveryClient`.
- Verify ordering when Eureka or Consul is also present.
- Verify LoadBalancer can select an instance.
- Verify backend timeouts, authentication failures, and error responses.
- Verify cache refresh when instances register or deregister.

**Contract tests**

If the catalog has a proprietary API, write tests to validate schema, metadata, service IDs, health status, and advertised addresses. When the provider changes its API, contract tests help catch failures before reaching production.

## 16. Migrating from Eureka/Consul to a Proprietary Catalog

A custom DiscoveryClient can support incremental migration without modifying every consumer at once.

A reference process:

1. Define the current contract: service ID, instance ID, host, port, scheme, metadata, and status.
2. Write an adapter that reads the new catalog and converts results into `ServiceInstance`.
3. Run the adapter in a test environment alongside the existing implementation.
4. Compare discovery results from both sources per service.
5. Check for duplicate records, unroutable endpoints, and missing metadata.
6. Verify LoadBalancer, health checks, caching, and behavior when the new catalog fails.
7. Switch a group of consumers or a profile to the new source.
8. Monitor lookup latency, service call errors, and propagation delay.
9. Expand cutover group by group.
10. Keep a clear rollback path until data and registrations stabilize.

If you need to read concurrently from multiple registries, use `CompositeDiscoveryClient` when its behavior meets requirements. If dual-write registration is needed, handle it separately in `ServiceRegistry`/lifecycle. Do not assume that adding a DiscoveryClient will automatically register instances into both registries.

During migration, determine which source is the source of truth for each service. If both registries return the same instance with different addresses, consumers might call an old endpoint or receive duplicate records.

## 17. Common Pitfalls When Building a Custom Implementation

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Consumer does not see the custom client | Bean was not component-scanned or auto-configuration was not loaded | Check package, bean conditions, and AutoConfiguration.imports |
| Two DiscoveryClients return duplicate instances | Both Eureka/Consul and custom client are used by composite | Define source rules, deduplicate, or enable providers selectively by profile |
| getInstances() returns an empty list despite catalog having data | Wrong service ID, namespace, or filter | Check ID mapping and query the catalog directly |
| Consumer calls wrong host or port | Incorrect ServiceInstance mapping | Check host, port, scheme, and network reachability from consumer |
| Health indicator is slow | Default probe loads all of getServices() | Override lightweight probe() and set use-services-query=false |
| WebFlux is blocked | Calling a blocking SDK on the event loop | Use a reactive client or isolate blocking calls on a scheduler |
| Catalog errors are interpreted as no instances | Exceptions are caught and return List.of() | Distinguish empty results from backend failures |
| LoadBalancer keeps choosing old instances | Cache or refresh has not updated | Check ServiceInstanceListSupplier and cache TTL |
| Auto-configuration creates client twice | Duplicate bean registration configuration | Check bean conditions and bean names |
| Can read instances but cannot register local service | Only DiscoveryClient was implemented | Add ServiceRegistry/Registration if write-side lifecycle is needed |

## 18. Decision Checklist Before Writing Code

Before creating a new class, answer the following questions:

1. Is the instance data source Eureka, Consul, or a provider that already has a Spring Cloud starter?
2. Can `SimpleDiscoveryClient` suffice if the endpoint list is stable?
3. Is the problem in the data source or only in how LoadBalancer selects instances?
4. Do you need custom service ID, metadata, or namespace mapping?
5. Do you need to read from multiple registries or simply switch providers?
6. Do you need to register/deregister the local service or only perform lookups?
7. Does the application use a blocking or reactive API?
8. Does the catalog have clear timeout, authentication, pagination, and cache policies?
9. Do you have contract tests and a rollback procedure?
10. Can this be solved with existing configuration instead of adding a new abstraction?

If the answers indicate that the data source is already supported and the requirement is only instance selection, customize LoadBalancer. If writing registrations is needed, look at `ServiceRegistry`. Only build a `DiscoveryClient` when you truly need a new discovery read adapter.

## 19. Conclusion

A custom `DiscoveryClient` is appropriate when Spring Cloud lacks an adapter for an organization's catalog source, requires custom service ID or metadata mapping conventions, or needs to integrate a specialized discovery API. The implementation must adhere to the `getInstances()`, `getServices()`, `description()`, and `probe()` contracts and return `ServiceInstance` objects with accurate routable addresses.

Before writing one, clearly distinguish `DiscoveryClient` from `ServiceRegistry` and `ServiceInstanceListSupplier`. Use built-in implementations when possible, `SimpleDiscoveryClient` for static lists, LoadBalancer suppliers for instance selection policies, and `ServiceRegistry` for registration lifecycles. If building a custom client, ensure it has timeouts, caching, security, health probes, contract tests, and a clear migration plan.

## References

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Commons — ServiceInstance API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java)
- [Spring Cloud Commons — DefaultServiceInstance](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/DefaultServiceInstance.java)
- [Spring Cloud LoadBalancer — Client-Side Load Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud LoadBalancer — Getting Started Guide](https://spring.io/guides/gs/spring-cloud-loadbalancer/)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
