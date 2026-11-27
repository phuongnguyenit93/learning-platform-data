# Checking Support for Each Discovery and HTTP Client Implementation

A Spring Cloud application may run fine on a standard JVM yet fail to start after enabling Spring AOT, GraalVM Native Image, or JVM checkpoint/restore. The cause usually lies in a specific implementation: discovery client, registry client, HTTP transport, connection pool, proxy, runtime reflection, or open resources.

Therefore, do not evaluate "does Spring Cloud support AOT" as a blanket conclusion applicable to every starter. You must check each implementation actually present on the classpath and each HTTP client Spring Boot selects at runtime.

This lesson belongs to the **AOT and checkpoint** chapter of the **SPRING_CLOUD_CORE** module. The content distinguishes Spring AOT, Native Image, and CRaC; builds a support matrix by discovery implementation and HTTP client; highlights key configuration conditions; and establishes a testing workflow to confirm the application can build, start, discover, make HTTP calls, checkpoint, and restore in the target environment.

## 1. Three Concepts That Must Not Be Equated

### 1.1. Spring AOT

Spring AOT analyzes the application at build time and generates code/metadata to optimize how the ApplicationContext is created. This process needs advance knowledge of part of the bean structure, configuration conditions, proxies, reflection, resources, and service clients.

AOT can generate optimized code for the JVM or act as a mandatory step when building a GraalVM Native Image. An application that runs on the JVM with AOT-generated code provides higher confidence, but does not replace building and running a real native executable.

### 1.2. GraalVM Native Image

Native Image compiles the application and dependencies into an executable under a closed-world model. Classes, methods, resources, or proxies loaded only dynamically at runtime may not exist in the image if the build cannot discover them.

Common limitations include:
- Reflection or proxies without declared runtime hints.
- Resources inside JARs not included in the image.
- Configuration altering the bean graph at runtime when the bean graph was locked at build time.
- Service IDs or clients created dynamically that AOT cannot infer.
- Libraries using dynamic class loading or serialization without appropriate hints.

### 1.3. JVM Checkpoint/Restore with CRaC

CRaC captures the state of a running JVM and restores that state later. Unlike Native Image, CRaC does not compile the application into a native executable; it saves a memory snapshot and prepared process state.

CRaC is particularly sensitive to operating system and external resources:
- Open sockets.
- HTTP connection pools and database pools.
- File handles.
- Threads waiting on I/O.
- Cached DNS or IP addresses.
- Expiring tokens, credentials, and sessions.
- Registrations, heartbeats, or leases in a service registry.
- Schedulers with tasks coming due while the JVM is checkpointed.

Spring Framework integrates CRaC through bean lifecycles. Before checkpoint, `Lifecycle`/`SmartLifecycle` beans are stopped to release resources; after restore, they are restarted. Libraries without Spring integration may need an adapter implementing `org.crac.Resource` (written as org.crac.Resource in prose below).

### 1.4. Comparison Table

| Criterion | Spring AOT | GraalVM Native Image | CRaC |
| --- | --- | --- | --- |
| Processing time | Build time | Build time and native compilation | While the JVM is running |
| Artifact | AOT code/metadata | Native executable | JVM snapshot |
| Reflection/resources | Needs hints when not inferred | Needs hints/resource configuration | Present in JVM state, but OS resources must be handled |
| Bean graph | Some decisions fixed at build time | Closed-world, requires deterministic structure | Preserves already-created bean state |
| Sockets and pools | Not the focus | Created when the process runs | Must be closed before and reopened after restore if not retainable |
| Refresh scope | Unsupported in Spring Cloud AOT mode | Unsupported | Can be refreshed on restart via Spring Cloud Context |
| Goal | Optimize context initialization | Reduce footprint and startup | Reduce startup/warm-up time via snapshot |

Do not use AOT test results to conclude CRaC is safe. An implementation may have complete runtime hints yet still hold non-restorable sockets. Conversely, an HTTP client may handle sockets cleanly on restore yet lack reflection hints for Native Image.

## 2. Discovery Implementation Support Matrix

Official documentation does not publish a uniform AOT/Native Image/CRaC matrix for all discovery providers. The table below only marks support when an implementation's documentation explicitly states it; cases without a specific statement must be tested on your target BOM and runtime.

| Discovery Implementation | Spring AOT / Native Image | Conditions or Limitations | CRaC / Checkpoint |
| --- | --- | --- | --- |
| Eureka Client | Supported | Disable spring.cloud.refresh.enabled; do not use random server port | Must verify re-registration, heartbeat, registry cache, and HTTP transport after restore |
| Eureka Server | Not yet supported | Netflix documentation explicitly states AOT/native is unsupported | No separate commitment; do not infer from Eureka Client |
| Spring Cloud Kubernetes Discovery | Not yet supported per current docs | Docs state Spring Boot AOT transformations or native images are not yet supported | No dedicated CRaC matrix; check Kubernetes client, watches, and API connections |
| Spring Cloud Consul Discovery | No dedicated AOT statement in current reference | Check Consul client, health checks, TLS, and runtime hints per version | Check Consul sessions, health checks, connections, and re-registration |
| Spring Cloud Zookeeper Discovery | No dedicated AOT statement in current reference | Check client library, serialization, watchers, and runtime dependencies | Check ZooKeeper sessions, connections, and watchers after restore |
| SimpleDiscoveryClient | No implementation-specific support statement | Instance source is properties; check binding and service IDs at build/runtime | No registry session, but check configuration and client caches after restore |
| Spring Cloud LoadBalancer | Supported since 4.0.0 | Must explicitly declare LoadBalancerClient service IDs | Check child contexts, suppliers, caches, and discovery delegates after restore |
| Spring Cloud Config Client | Supported since 4.0.0 | Config source must be reachable during AOT build; disable refresh scope; do not use legacy config-first bootstrap | Check Config Server/backend connectivity and config reloading after restore |

**No stated support does not mean confirmed unsupported.** It means official documentation provides no commitment an application can rely on. Treat that implementation as unverified until tests succeed on your exact release train.

### 2.1. Eureka Client

Spring Cloud Netflix confirms Eureka Client supports Spring AOT transformations and Native Image when refresh mode is disabled:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Additionally, random ports are not supported in AOT/Native Image due to the closed-world assumption. For applications registering with Eureka, predictable host and port values must be determined at build/deploy time.

Do not confuse this condition with Eureka Server. Current documentation explicitly states Eureka Server does not support Spring AOT transformations or Native Image.

When running CRaC, verify separately:
- Does Eureka client close HTTP connections before checkpoint?
- After restore, does the client re-register or continue renewals properly?
- Is instance metadata still valid for the new host, port, and network interface?
- Does the registry still hold an old registration while the process was paused?
- Is the client cache refreshed at the right time?

Eureka Client's AOT support is not a guarantee that all checkpoint/restore scenarios are handled.

### 2.2. Spring Cloud Kubernetes Discovery

Current Spring Cloud Kubernetes documentation explicitly states the project does not yet support Spring Boot AOT transformations or Native Image. Do not put the Kubernetes Discovery starter into a production native image merely because a basic Spring Boot application compiled successfully.

If the goal is deploying a native Spring Boot app on Kubernetes, evaluate whether Spring Cloud Kubernetes is truly needed. Kubernetes already provides service discovery via Service DNS, EndpointSlice, and platform APIs. A Spring Boot application can use standard DNS/service addresses without adding Spring Cloud Kubernetes' discovery implementation.

If the application must use Spring Cloud Kubernetes Discovery:
- Check the support status of your specific release before enabling AOT/native.
- Separate discovery tests from native image tests to isolate failing dependencies.
- Check whether Fabric8 Kubernetes Client or Kubernetes Java Client is selected by the starter.
- Check service account, namespace, RBAC, and API endpoint.
- Do not assume client watches or informers can be restored from a CRaC snapshot without reopening connections.

### 2.3. Consul and Zookeeper

No dedicated AOT/Native Image support statement was found in the current reference documentation for these two discovery providers. Therefore, verify on your exact version:

- Runtime hints for reflection, serialization, and resources.
- Does the client load classes or providers dynamically?
- Are TLS, truststore, credential, and namespace configurations resolved at build time?
- Are watchers/listeners re-registered after context restart?
- Are connections/sessions closed and recreated after CRaC restore?
- Are health checks and registrations updated after the instance recovers?

Spring Cloud Config Client has its own AOT documentation and can connect to backends such as Config Server, Consul, Zookeeper, or Vault. That does not automatically prove Consul Discovery or Zookeeper Discovery have the same level of AOT support.

### 2.4. SimpleDiscoveryClient

SimpleDiscoveryClient retrieves instances from configuration instead of connecting to a registry server. Thus, it reduces the number of external components that need testing.

Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8080
              - uri: http://catalog-b.internal:8080
~~~

With AOT, ensure property sources and service lists are loaded according to configuration known at build time/runtime. With CRaC, there is no registry session to restore, but HTTP clients, DNS caches, and LoadBalancer caches still need verification.

Do not use SimpleDiscoveryClient to replace a dynamic registry if the application needs self-registration, heartbeats, or instance updates as replicas appear and disappear.

## 3. Explicit Service ID Declaration for LoadBalancer

Spring Cloud LoadBalancer supports AOT and Native Image starting from version 4.0.0. An essential condition is explicitly declaring the service IDs the application will load-balance.

You can use an annotation:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(name = "catalog-service")
public class CatalogLoadBalancerConfiguration {
}
~~~

Or declare via properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - catalog-service
          - inventory-service
          - pricing-service
~~~

Example with multiple clients:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClients;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClients({
        @LoadBalancerClient(name = "catalog-service"),
        @LoadBalancerClient(name = "inventory-service"),
        @LoadBalancerClient(name = "pricing-service")
})
public class ServiceLoadBalancerClients {
}
~~~

Do not rely on a service ID that only appears in a URI string constructed dynamically at runtime. AOT needs to know which client contexts need to be configured.

### 3.1. Why Are Explicit Service IDs Needed?

Spring Cloud LoadBalancer creates a separate child ApplicationContext for each service ID. By default, these contexts are lazily initialized on the first request. In AOT, the list of service IDs must be determined in advance so context processing can generate the corresponding metadata.

Therefore, check:
- Is the service ID list complete?
- Does the logical URI match the declared service ID spelling?
- Is any service ID generated from a dynamic property unknown at build time?
- Are custom ServiceInstanceListSuppliers registered in the right context?
- Are per-service-ID configurations discovered during AOT?

### 3.2. Do Not Create LoadBalancer Configurations from Runtime-Only Data

Do not depend on reading a list of services from a database after the native image is built to create child contexts. If the number of services can change, choose a design compatible with the closed-world assumption or move the variable part into runtime data that does not alter the bean graph.

## 4. Spring Cloud OpenFeign and AOT Conditions

Spring Cloud OpenFeign supports Spring AOT transformations and Native Image, provided these conditions are met:

- spring.cloud.refresh.enabled=false.
- Do not enable spring.cloud.openfeign.client.refresh-enabled=true.
- Do not enable spring.cloud.openfeign.lazy-attributes-resolution=true.

Example:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
    openfeign:
      client:
        refresh-enabled: false
      lazy-attributes-resolution: false
~~~

These are conditions related to AOT/native. Do not enable refresh simply because the application wants to change a Feign client URL at runtime.

### 4.1. Feign Client URL and Service ID

With load balancing, the Feign client uses a service name:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
public interface CatalogClient {

    @GetMapping("/api/catalog")
    CatalogResponse getCatalog();
}
~~~

The name catalog-service must correspond to a service ID known to discovery and LoadBalancer.

If a fixed URL is declared in FeignClient, the client can call that endpoint directly without load balancing. OpenFeign documentation also describes overriding the URL via a system property if the URL is declared via properties right from build time. Do not assume every URL value can be freely changed after the native image has been built.

### 4.2. Lazy Attribute Resolution

Lazy attribute resolution can be useful in certain tests or environments that need to defer resolving annotation attributes. However, AOT/native requires a deterministic structure at build time.

If the application uses Spring Cloud Contract or test contexts requiring lazy resolution, separate test and production configurations. Do not enable lazy resolution in a native runtime when OpenFeign's AOT conditions require it to be disabled.

## 5. Spring Cloud Config Client in AOT/Native

Spring Cloud Config Client supports AOT transformations and Native Image starting from version 4.0.0. However, there are several critical conditions:

1. Do not use legacy config-first bootstrap with spring.config.use-legacy-processing=true.
2. Disable refresh scope with spring.cloud.refresh.enabled=false.
3. The remote configuration data source Config Client connects to must be reachable during the AOT build.
4. Properties affecting bean creation must be consistent between build time and runtime.
5. Account for time spent calling Config Server/backend when the native application starts up.

Example:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
    config:
      uri: https://config.internal
~~~

If Config Server requires TLS or authentication, the AOT build environment must also have the appropriate network route and credentials. Do not embed production secrets into the image or build logs; use secure secret injection for the build process.

### 5.1. Config Client Connecting to Consul or Zookeeper

Config Client documentation lists Consul and Zookeeper as configuration sources that can be used. When AOT processes the context, that data source must be reachable to resolve configuration.

This means:
- Separately test builds when Config Server/backend is temporarily unreachable.
- Identify which properties must be supplied at build time.
- Keep properties affecting the bean graph consistent at runtime.
- Do not treat a successful Consul backend configuration as proof that Consul Discovery native image is supported.

## 6. Spring HTTP Client Matrix

Spring Boot has multiple HTTP abstractions. AOT/Native Image support of a Spring abstraction does not mean all underlying implementations share the same capabilities. Both the client API and the selected HTTP transport must be checked.

### 6.1. RestTemplate and RestClient

Spring Boot auto-detects the HTTP client used with RestTemplate and RestClient based on the classpath. The current priority order in Boot 4.1 documentation is:

| Order | Request Factory / HTTP Client |
| --- | --- |
| 1 | Apache HttpClient |
| 2 | Jetty HttpClient |
| 3 | Reactor Netty HttpClient |
| 4 | JDK java.net.http.HttpClient |
| 5 | Simple JDK HttpURLConnection |

If multiple implementations are present, the highest-priority client is chosen unless the application configures a specific factory.

Example forcing the JDK client:

~~~yaml
spring:
  http:
    clients:
      imperative:
        factory: jdk
~~~

Example forcing Jetty:

~~~yaml
spring:
  http:
    clients:
      imperative:
        factory: jetty
~~~

### 6.2. WebClient

Spring Boot auto-detects the ClientHttpConnector for WebClient based on the classpath:

| Order | Reactive HTTP Client |
| --- | --- |
| 1 | Reactor Netty |
| 2 | Jetty RS client |
| 3 | Apache HttpClient |
| 4 | JDK HttpClient |

Example forcing the Jetty connector:

~~~yaml
spring:
  http:
    clients:
      reactive:
        connector: jetty
~~~

If the implementation is not pinned, adding or removing a dependency can cause Spring Boot to choose a different transport. This can change behavior around connection pools, TLS, cookies, proxies, and lifecycles.

### 6.3. AOT and CRaC Evaluation Matrix by HTTP Client

| API / Transport | Spring Boot Configuration Support | AOT/Native | CRaC/Checkpoint |
| --- | --- | --- | --- |
| RestTemplate | Yes | Usable with application AOT if request factory and dependencies have appropriate hints; no blanket guarantee for every factory | Must check lifecycle of underlying connection pool |
| RestClient | Yes | Usable with application AOT if request factory and dependencies have appropriate hints | Must close/rebuild HTTP transport resources if needed |
| WebClient + Reactor Netty | Yes | Test native image with exact Reactor Netty version and resource hints | Check event loop, connection pool, sockets, and DNS after restore |
| WebClient + Jetty | Yes | Test native image with Jetty RS client and dependency runtime hints | Check Jetty HttpClient and connection pool lifecycle |
| Apache HttpClient | Yes | Test exact major version, reflection/resource hints, and TLS provider | Close/reopen connection manager and pool |
| JDK HttpClient | Yes | Test on target JDK and native-image toolchain | Check sockets/executor and recreating client after restore |
| HttpURLConnection | Yes | Test behavior in target native image | Do not assume connection state survives across checkpoint |

Spring Boot documentation describes transport options and how they are selected, but does not guarantee that every version of Apache, Jetty, Reactor Netty, or the JDK client carries identical CRaC certification. Do not infer CRaC support from the fact that Spring Boot can auto-configure that client.

### 6.4. Verify the Transport Actually Selected

Do not look only at dependency declarations. Verify the implementation at runtime via:
- The ClientHttpConnector bean injected into WebClient.
- The request factory used by RestClient/RestTemplate.
- The dependency tree of HTTP transports.
- Startup logs or the debug condition report.
- An integration test calling an endpoint through the exact client bean.

If the application needs reproducibility across developer machines, CI, and production, configure the factory explicitly rather than relying on classpath priority order.

## 7. Spring Cloud LoadBalancer with Each HTTP API

Spring Cloud LoadBalancer provides these integrations:
- BlockingLoadBalancerClient for RestTemplate and RestClient.
- ReactorLoadBalancerExchangeFilterFunction for WebClient.
- Spring Cloud OpenFeign uses LoadBalancer's blocking mode.
- Starting from Spring Cloud LoadBalancer 5.0.0, there is integration with Spring HTTP Service Clients auto-configuration.

For AOT/native, in addition to choosing the right HTTP API, service IDs must be explicitly declared as in the previous section. For CRaC, both LoadBalancer's child contexts and the underlying transport must be checked.

### 7.1. Load-Balanced RestClient

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

The example above illustrates a builder annotated with LoadBalanced; in a real application, use the auto-configured builder or configurer appropriate for your Spring Boot version to preserve configured customizers and request factories.

### 7.2. Load-Balanced WebClient

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveCatalogHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

When using a service ID in the URI, LoadBalancer resolves the logical URI into an instance address. AOT still needs to know the service IDs being used; CRaC needs to verify connector resources and LoadBalancer suppliers after restore.

### 7.3. HTTP Service Clients

Spring Cloud LoadBalancer 5.0.0 and later integrates with Spring HTTP Service Clients auto-configuration. For a group with an empty baseUrl or the lb scheme, LoadBalancer can configure the base URL by service ID from the group name.

For AOT, explicitly declare the group and client interfaces at build time. For CRaC, check the underlying RestClient or WebClient group configurer and transport lifecycle.

## 8. Refresh Scope Has Special Limitations in AOT/Native

Spring Cloud Context does not support Context Refresh for Spring AOT transformations and Native Image. When using AOT/native, set:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

This applies to Spring Cloud Context's refresh scope mechanism. Do not try to enable RefreshScope to mutate the bean graph after the native image has been built.

Distinguish between:
- spring.cloud.refresh.enabled: enables/disables refresh scope and context refresh features.
- spring.cloud.openfeign.client.refresh-enabled: enables refresh for Feign clients.
- spring.cloud.refresh.on-restart.enabled: controls refresh when the JVM restarts after checkpoint/restore.
- spring.cloud.loadbalancer.eager-load.clients: declares service IDs for LoadBalancer; not a refresh flag.

### 8.1. Refresh Scope on Restart for CRaC

Spring Cloud Context provides RefreshScopeLifecycle to trigger Context Refresh when the JVM restarts after CRaC restore. Refreshing can rebind configuration properties and refresh RefreshScope beans.

You can disable this behavior with:

~~~yaml
spring:
  cloud:
    refresh:
      on-restart:
        enabled: false
~~~

This is behavior for the restart/checkpoint lifecycle; it does not make refresh scope compatible with AOT/native image. The two modes must be configured and tested separately.

### 8.2. RefreshScopeHealthIndicator

Spring Cloud provides RefreshScopeHealthIndicator to monitor errors when rebinding or reinitializing beans after context refresh. If a bean cannot be reinitialized, the health indicator can transition to DOWN and display the associated exception.

In a CRaC environment, observe health after restore before allowing the instance to receive traffic. Do not check only that the process restarted; confirm refreshable beans are ready.

## 9. CRaC and the Discovery Client Lifecycle

A discovery client typically holds several long-lived resources:
- HTTP clients connecting to the registry.
- Scheduled heartbeats or health updates.
- Registry caches.
- Watchers or long-polling connections.
- Authentication tokens.
- Expiring sessions or leases.

When the JVM is checkpointed for a long time, these resources may no longer be valid upon restore. For example:
- The registry has expired the instance's lease.
- Tokens have expired.
- Sockets were closed by a firewall.
- DNS has changed.
- The instance is restored on a different host or network namespace.
- The registry has accepted a new registration from another instance using the same identity.

### 9.1. Cycle to Test

~~~mermaid
flowchart TD
    A["Start application"] --> B["Connect discovery and HTTP client"]
    B --> C["Register service / fetch instance list"]
    C --> D["Warm up common flows"]
    D --> E["Before checkpoint: stop beans and close resources"]
    E --> F["CRaC saves JVM snapshot"]
    F --> G["Restore JVM"]
    G --> H["After restore: reopen HTTP client and session"]
    H --> I["Refresh/rebind config if needed"]
    I --> J["Register or renew discovery"]
    J --> K["Health/readiness confirms"]
    K --> L["Allow receiving traffic"]
~~~

Do not allow the instance to accept traffic immediately when JVM restore completes if the discovery session or connection pool is not yet ready.

### 9.2. Spring Lifecycle and org.crac.Resource

For Spring-managed beans, prefer implementing Lifecycle or SmartLifecycle if the resource can stop and start along with the context lifecycle.

For libraries without Spring integration, you can implement org.crac.Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public class ExternalTransportResource implements Resource {

    private final ExternalTransportFactory factory;
    private ExternalTransport transport;

    public ExternalTransportResource(ExternalTransportFactory factory) {
        this.factory = factory;
        this.transport = factory.open();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        transport.close();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        transport = factory.open();
    }
}
~~~

ExternalTransport and ExternalTransportFactory are application-defined abstractions for managing a transport that can be closed and recreated. Do not use a closed instance after restore.

If the transport is managed by Spring Boot or a library that already has CRaC integration, do not register a duplicate adapter. Two lifecycle handlers closing/opening the same resource can cause errors or create unexpected connections.

### 9.3. Eureka After Restore

For Eureka Client, verify:
- The HTTP client is operational again.
- Heartbeats are sent to Eureka Server.
- Registration has the host/port matching the restored environment.
- Instance ID does not conflict with another process.
- Client registry cache has been updated.
- LoadBalancer does not select stale addresses.

If Eureka client is refreshed or re-registered on context restart, monitor the window while the instance is unregistered and when it becomes registered again. Verify behavior on your exact Eureka version and configuration.

### 9.4. Consul and Zookeeper After Restore

For Consul, check sessions, registrations, health checks, ACL tokens, and HTTP connections after restore.

For Zookeeper, check session timeouts, connection state, watcher registrations, and re-registration of ephemeral nodes if the application uses that node type.

The steps above are an operational checklist to confirm via integration tests; not every provider automatically handles all of this state.

### 9.5. Kubernetes Discovery After Restore

If the application uses Kubernetes API watches or informers:
- Verify the watch connection is reopened.
- Verify the resource version is still valid.
- If the watch closed, the client may need to re-list and establish a new watch.
- Check service account token rotation.
- Check DNS caches and EndpointSlice updates.
- Check the network namespace/Pod IP after restore.

Spring Cloud Kubernetes AOT/native documentation currently states no support, but that does not automatically answer CRaC capability. CRaC must be evaluated separately with the actual client and version.

## 10. CRaC and the HTTP Client Lifecycle

HTTP clients typically hold connection pools, sockets, event loops, and executors. Before checkpoint, ensure:
- In-flight requests have completed or been cancelled cleanly.
- No sockets remain that CRaC cannot checkpoint.
- Connection pools are closed or released.
- Event loop threads are not hung.
- After restore, the client can open new connections.
- TLS/sessions/credentials are updated if expired.
- DNS is re-resolved when needed.

### 10.1. Reactor Netty

For WebClient using Reactor Netty, check:
- ConnectionProvider and pool lifecycle.
- LoopResources/event loop.
- Open sockets.
- Idle connections or connections actively processing requests.
- DNS resolver cache.
- SSL context and certificate rotation.

If manually creating ConnectionProvider or LoopResources, the application must manage disposal and recreation per the appropriate lifecycle. Do not merely close the WebClient wrapper and assume all Netty resources have been released.

### 10.2. Jetty HttpClient

For Jetty, check:
- HttpClient.stop() before checkpoint.
- Connection pool and scheduler.
- Executor and threads.
- TLS context.
- Ability to start() again after restore.
- Whether active requests are drained or cancelled safely.

A stopped HTTP client must not be reused as if it were still running. Use a factory or bean lifecycle to create a fresh active state.

### 10.3. Apache HttpClient

For Apache HttpClient, check:
- Does the connection manager close sockets?
- Is the pool closed and recreated?
- Are evictor threads or idle connection monitors stopped?
- Does the DNS resolver need refreshing?
- Can the TLS socket factory and credentials be recreated?

If the application creates CloseableHttpClient manually, manage it as a resource with an explicit lifecycle. Do not assume auto-configuration knows about manually instantiated clients.

### 10.4. JDK HttpClient

For JDK HttpClient, check:
- Does the client have in-flight requests?
- Is a custom executor managed?
- Are streaming response bodies fully read or cancelled?
- After restore, can the client continue using old connections or does a new instance need to be created?

JDK HttpClient on Java 21 and later provides shutdown/close APIs. If the application uses an older JDK or another specific runtime, check that runtime's APIs and behavior instead of calling nonexistent methods.

### 10.5. Simple JDK HttpURLConnection

Simple JDK client does not provide the same connection pool model and lifecycle API as Apache/Jetty/Reactor Netty. However, in-flight requests, DNS caches, proxies, and sockets are still resources to consider.

Do not assume having no pool bean means there are no CRaC issues. Run checkpoint/restore tests both with active requests and while the client is idle.

## 11. AOT Hints for Custom Implementations

If a custom discovery provider or HTTP client uses reflection, resource loading, serialization, or JDK proxies that AOT cannot infer, declare RuntimeHints.

Example registrar:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogClientRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("catalog/client-defaults.properties");
        hints.reflection().registerType(
                CatalogWireMessage.class,
                hint -> hint.withDeclaredConstructors()
                        .withDeclaredFields()
        );
    }
}
~~~

Register the registrar:

~~~java
import org.springframework.context.annotation.ImportRuntimeHints;

@ImportRuntimeHints(CatalogClientRuntimeHints.class)
public class CatalogClientConfiguration {
}
~~~

The example illustrates resource and reflection hints for application-controlled classes. Register only the access actually required. Do not enable reflection for entire packages or the classpath just to make a native image build pass.

### 11.1. Checking Resources in a Native Image

The following files typically need verification:
- TLS certificates/truststores.
- JSON schemas or serializer metadata.
- Discovery configuration.
- HTTP client service resources.
- META-INF/services.
- Configuration files read by libraries via ClassLoader.
- Files containing templates or protocol descriptors.

A successful AOT build does not prove every resource is present in the image. Run the native executable and perform real requests to detect missing resources.

## 12. Testing AOT per Implementation

Proceed layer by layer; do not enable all discovery providers and HTTP clients at once from the start.

### 12.1. Testing AOT on the JVM

After building AOT code, you can run the application on the JVM with:

~~~bash
java -Dspring.aot.enabled=true -jar target/application.jar
~~~

Ensure the JAR already contains the AOT code generated during the build. This helps verify the optimized context without waiting for native compilation every time.

### 12.2. Testing Native Image

With Maven, enable the project's native profile and build the image according to the GraalVM plugin your project uses. After building, run the executable and verify:
- ApplicationContext initializes successfully.
- Discovery client connects to the right endpoint.
- LoadBalancer has all required service IDs.
- HTTP client creates the expected implementation.
- Requests succeed against real instances or test servers.
- TLS, serialization, and resources work.
- Health/readiness reach the desired state.

Do not test only the health endpoint. There must be at least one request going through discovery and load balancing to prove the integration actually works.

### 12.3. Using context.exit to Inspect the Startup Phase

Spring Framework supports:

~~~bash
java -Dspring.context.exit=onRefresh -jar target/application.jar
~~~

The application exits at the lifecycle phase equivalent to checkpoint-on-refresh without needing a CRaC-enabled JVM, Linux, or the CRaC dependency. This is a way to check whether any bean attempts to connect to remote services too early before lifecycle startup.

If an HTTP client or discovery implementation cannot start in this phase, consider deferring connections to an appropriate lifecycle phase instead of performing I/O directly inside constructors or PostConstruct.

### 12.4. AOT Test Matrix

| Test | Expected Result |
| --- | --- |
| AOT Build | Generates code and metadata successfully |
| JVM running with spring.aot.enabled=true | Context starts with AOT code |
| Native image build | Compiler builds executable successfully |
| Native startup | No missing classes/resources/hints |
| Discovery lookup | Service ID returns the right instances |
| LoadBalancer | Selects instances from a valid list |
| HTTP call | Request/response works over the selected transport |
| Config Client | Remote source is reachable and configuration is correct |
| Refresh scope | Disabled in AOT/native if using Spring Cloud Context |

## 13. Testing CRaC Checkpoint/Restore

### 13.1. Environment Requirements

Spring Framework currently requires:
- A JVM with checkpoint/restore support.
- A Linux environment for actual checkpointing per current documentation.
- org.crac:crac version 1.4.0 or later.
- JVM flags such as -XX:CRaCCheckpointTo=PATH or -XX:CRaCRestoreFrom=PATH.

Example dependency:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version>1.5.0</version>
</dependency>
~~~

Use the version supported by your project's runtime and Spring Framework version. Do not arbitrarily pin the newest CRaC version if the platform's dependency management specifies another version.

### 13.2. Creating a Checkpoint

Start the application with a CRaC-enabled JDK:

~~~bash
java -XX:CRaCCheckpointTo=./crac-image -jar target/application.jar
~~~

Warm up the application with a representative workload, then create a checkpoint:

~~~bash
jcmd application.jar JDK.checkpoint
~~~

Restore from the snapshot:

~~~bash
java -XX:CRaCRestoreFrom=./crac-image
~~~

Runtime syntax and capabilities may vary across vendors. Check the documentation of your CRaC JDK and Linux/CRIU permissions in the real environment.

### 13.3. Checks After Restore

After restore:
1. Check that ApplicationContext is active.
2. Confirm HTTP connection pools have reopened.
3. Confirm discovery sessions/heartbeats resumed or re-registered.
4. Check that service instances have the right addresses.
5. Check that LoadBalancer suppliers/caches received valid data.
6. Send business requests through the HTTP client.
7. Check database/broker dependencies.
8. Confirm readiness before accepting traffic.
9. Check logs for socket, executor, or thread errors.
10. Measure time from restore to first successful request.

### 13.4. Fixed Rate Schedulers After Restore

With @Scheduled(fixedRate = 5000), executions missed while the JVM was checkpointed may run upon restore. If you do not want a burst of executions right after restore, consider fixedDelay or a cron expression.

Do not allow heartbeat, polling, or cleanup tasks to burst after restore and overload the registry, broker, or database.

### 13.5. Protecting Snapshots

A CRaC snapshot contains JVM memory. Any data the application has read may reside in the snapshot, including:
- Secrets and access tokens.
- Database credentials.
- HTTP Authorization headers.
- TLS sessions or key material.
- Configuration properties.
- Customer data or request payloads still in the heap.

Therefore:
- Store snapshots on storage with access controls.
- Encrypt snapshots at rest/in transit if policy requires.
- Do not place snapshots containing secrets in public artifacts.
- Restrict read and write permissions on snapshots.
- Do not restore production snapshots into environments with different access privileges without evaluating credentials.
- Establish a deletion process when snapshots expire.

## 14. Process to Verify Implementations Before Production Selection

### 14.1. Discovery Implementation

| Question | Evidence to Collect |
| --- | --- |
| Which implementation is created? | Dependency tree and ApplicationContext beans |
| Is there AOT/native support? | Reference guide for the exact version |
| Does it require explicit service IDs? | AOT config and list of LoadBalancer clients |
| Does it connect remotely at build time? | Build logs and config sources |
| Does it have heartbeats/watches/sessions? | Provider logs and metrics |
| Does it reconnect after restore? | CRaC integration test |
| Is the instance re-registered? | Registry records and instance ID |
| Does the cache become stale? | Discovery list before/after restore |

### 14.2. HTTP Client Implementation

| Question | Evidence to Collect |
| --- | --- |
| Which request factory/connector does Spring select? | Runtime beans and dependency tree |
| Does the native image have enough hints? | Native build and runtime smoke test |
| Are there dynamic resources or reflection? | RuntimeHints and resource inspection |
| Is the pool closed? | Checkpoint logs and resource callbacks |
| Is there a fresh client after restore? | Integration test and real requests |
| Are DNS/TLS refreshed? | Endpoint call results after restore |
| Are retries/timeouts altered? | Client metrics and request traces |

### 14.3. Running Tests by Combination

Example combinations to test:

| Discovery | HTTP Client | AOT/Native | CRaC |
| --- | --- | --- | --- |
| Eureka Client | RestClient + JDK | Check Eureka and LoadBalancer conditions | Check registration and client recreation |
| Eureka Client | WebClient + Reactor Netty | Check service IDs and native hints | Check event loop and pool |
| SimpleDiscoveryClient | RestTemplate | Check property binding and service IDs | Check request factory |
| Consul Discovery | RestClient + Apache | No dedicated AOT commitment; test target version | Check session, registration, and pool |
| Zookeeper Discovery | WebClient + Jetty | No dedicated AOT commitment; test target version | Check session, watchers, and client |
| Kubernetes Discovery | RestClient | Current docs state AOT/native unsupported | Check API watch and token lifecycle |

Do not run one huge combined test and merely report "native build failed". Break it down by provider to know whether the failure is in discovery, LoadBalancer, HTTP transport, Config Client, or custom runtime hints.

## 15. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Eureka Client fails native build | Refresh mode still enabled or random port | Disable refresh, use a deterministic port |
| Eureka Server native build fails | Implementation does not yet support AOT/native | Use JVM or another supported registry architecture |
| Kubernetes Discovery native build errors | Current docs state AOT/native unsupported | Use Kubernetes Service DNS if suitable or wait for a supported release |
| LoadBalancer cannot find client context | Service ID not explicitly declared | Use LoadBalancerClient or eager-load property |
| Feign client not created in native | Lazy attribute resolution or client refresh enabled | Disable options incompatible with AOT |
| Config Client native fails to resolve config | Config backend unreachable during build | Provide data source and required properties at build time |
| Native image missing serializer/resource | Missing runtime hints | Register minimal reflection/resource hints |
| WebClient picks a different transport than CI | Different classpath | Pin connector or inspect dependencies |
| CRaC checkpoint rejected | Sockets/files/threads still open | Stop lifecycle beans and release resources |
| Requests fail after restore | Stale connection pool or session | Recreate client/session and test reconnection |
| Old Eureka registration still persists | Lease/heartbeat and restore timing | Verify registration, instance ID, and renewal |
| Scheduler bursts after restore | Using fixedRate | Use fixedDelay/cron where appropriate |
| Snapshot restore exposes credentials | Snapshot contains heap and config | Protect storage, access, and snapshot lifecycle |

## 16. Selection and Testing Checklist

### AOT / Native Image

- [ ] Identified exact Spring Boot and Spring Cloud release trains.
- [ ] Identified the actual discovery implementation on the classpath.
- [ ] Checked AOT/native documentation for that exact implementation.
- [ ] Disabled spring.cloud.refresh.enabled if using Spring Cloud AOT/native.
- [ ] Eureka Client does not use a random server port.
- [ ] Eureka Server is not assumed to be native-compatible.
- [ ] Spring Cloud Kubernetes is not assumed to be native-compatible.
- [ ] Declared service IDs for LoadBalancer.
- [ ] Feign client refresh and lazy attribute resolution are disabled.
- [ ] Config Client has a data source reachable at build time.
- [ ] Confirmed the HTTP transport selected by Spring Boot.
- [ ] Added RuntimeHints for custom reflection/resources/proxies.
- [ ] Ran AOT JVM tests and native executable smoke tests.
- [ ] Sent requests through discovery and LoadBalancer in the native executable.

### CRaC / Checkpoint Restore

- [ ] Runtime JDK supports CRaC and runs in a supported Linux environment.
- [ ] org.crac:crac dependency is compatible with Spring Framework.
- [ ] Bean lifecycles stop and restart properly.
- [ ] HTTP pools, sockets, and executors are released before checkpoint.
- [ ] Discovery client reconnects or re-registers after restore.
- [ ] Heartbeats, leases, tokens, and watchers are verified.
- [ ] LoadBalancer cache/supplier does not use stale addresses.
- [ ] Readiness transitions to UP only after dependencies and discovery are ready.
- [ ] Scheduled tasks do not create unwanted backlogs.
- [ ] Snapshots are protected as sensitive data.
- [ ] Integration tests exist for checkpoint, restore, and real requests.

## Key Takeaways

AOT/native and CRaC are two different optimization approaches. When evaluating AOT, verify that the discovery implementation is supported, LoadBalancer service IDs are explicitly declared, HTTP clients have sufficient runtime hints, and incompatible refresh features are disabled. When evaluating CRaC, the focus is the lifecycle of sockets, connection pools, sessions, heartbeats, watchers, and schedulers. Eureka Client supports AOT/native under specific conditions; Eureka Server and Spring Cloud Kubernetes are currently unsupported; Consul/Zookeeper must be verified per version where documentation makes no commitment. Do not conclude an application is compatible merely because it builds successfully: run the native executable, perform checkpoint/restore, and send requests through the exact discovery and HTTP transport that will be used in production.

## References

- Spring Cloud Netflix – AOT and Native Image Support: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Kubernetes – AOT and Native Image Support: https://docs.spring.io/spring-cloud-kubernetes/docs/current/reference/html/#aot-and-native-image-support
- Spring Cloud Commons – LoadBalancer AOT and Native Image Support: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud OpenFeign – AOT and Native Image Support: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
- Spring Cloud Context – Application Context Services and Refresh Scope on Restart: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html
- Spring Cloud Config Client – AOT and Native Image Support: https://docs.spring.io/spring-cloud-config/reference/client.html
- Spring Boot – Calling REST Services: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework – Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework – JVM Checkpoint Restore: https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html
- Spring Boot – Checkpoint and Restore With the JVM: https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html
- CRaC – Checkpoint and Restore: https://crac.org/use/checkpoint-and-restore/
