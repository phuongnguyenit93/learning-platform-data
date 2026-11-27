# Observing Stale Caches and Change Detection Delay

In microservices systems, an instance may already be removed from the service registry or a new replica may already be registered, yet **callers keep selecting the old instance set for some period of time**. The cause can lie in discovery caches, `CachingServiceInstanceListSupplier`, health-check cycles, or control-plane synchronization speed. This phenomenon is called a **stale instance list** — the client's candidate list does not yet reflect the source's new state.

This lesson belongs to the **Hands-On Project** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will build a live lab to **mutate topology while the caller is running**, observe it via `@LoadBalanced RestClient`, measure from the moment the source changes until LoadBalancer sees the new list, and distinguish **stale cache**, **dead instance**, **connection pool**, and **retry/timeout** issues. The conclusions apply equally to `WebClient` and OpenFeign when using Spring Cloud LoadBalancer.

> **Experimental goal:** instead of merely saying "the TTL is 6 seconds," actually measure **when the source switched from A+B to A** while **the cache still shows A+B**, log `source-change`/`cache-refresh` timestamps, and explain why observed delay does not necessarily equal the exact TTL.

## 1. Capabilities Gained After This Lab

After completing the lab, you should be able to prove:

1. **The instance-list source** and **the LoadBalancer cache** are two independent state layers.
2. When the source removes replica B, **a stale cache can keep returning B** until the cache entry expires or is invalidated.
3. **TTL is measured from cache write time**, not from the moment an instance changes state.
4. **Cache expiration** and **observing the new list** are two distinct events; a read after expiration creates the opportunity to refresh.
5. You can measure **detection delay** using timestamps, revisions, and source-read counters rather than guessing from a single request.
6. In real systems, **discovery propagation, LB caching, health checks, retries, and network transport** introduce distinct delays and behaviors.
7. You can build a test matrix verifying **a removed instance is no longer selected after convergence**, without hard-coding an unmeasured exact millisecond bound for all systems.

### Expected Deliverables

| Component | Role |
|---|---|
| `catalog-backend` running two replicas | Returns replica ID A/B |
| `caller-service` | Calls logical URI `http://catalog-service` |
| `TopologyState` | `ServiceInstance` source mutable at runtime |
| `MutableTopologySupplier` | Returns source snapshots and increments source reads |
| `CachingServiceInstanceListSupplier` | Holds candidate list for the TTL duration |
| `/__lab/source` | Inspects current source (without reading cache) |
| `/__lab/candidates` | Inspects the list LoadBalancer sees (may trigger cache refresh) |
| `/__lab/mode` | Switches source between `BOTH`, `A_ONLY`, `B_ONLY`, `NONE` |
| `/demo/whoami` | Performs real HTTP calls to the selected instance |

This is an **internal localhost lab**. The `/__lab/*` endpoints mutate routing and expose topology state; **never expose them to public production**.

## 2. Three Different Clocks of Change

Suppose at `t0` the caller cached `[A, B]`. At `t1` the control plane publishes only `[A]`. Distinguish:

- **Source update time:** `t_source` — when the source actually changed.
- **Cache eligibility time:** `t_expire` — when the cache entry becomes eligible for expiration per TTL.
- **Observed convergence time:** `t_detect` — the first observation seeing the new snapshot after refresh.

~~~mermaid
sequenceDiagram
    participant T as TopologyState
    participant S as MutableTopologySupplier
    participant C as LB cache (TTL=6s)
    participant LB as LoadBalancer
    participant A as catalog-a
    participant B as catalog-b

    LB->>C: Select instance (t0)
    C->>S: Cache miss, fetch snapshot
    S->>T: Read source [A, B]
    T-->>S: revision=1, [A, B]
    S-->>C: [A, B]
    C-->>LB: [A, B]
    Note over C: Write cache, start TTL clock
    T->>T: t1: switch source to [A], revision=2
    LB->>C: New request before cache expires
    C-->>LB: Stale [A, B]
    LB->>B: May pick B even though source dropped B
    Note over C: t_expire: TTL expired
    LB->>C: Request/read snapshot after t_expire
    C->>S: Cache miss, fetch new source
    S->>T: Read source [A]
    S-->>C: [A]
    C-->>LB: [A]
    LB->>A: Pick A
    Note over LB: t_detect: first observation of [A]
~~~

With a 6-second cache TTL, if the source changes 1 second after the cache entry was written, the remaining stale window may be **around 5 seconds** — though real measurements are affected by polling timing, scheduling, other cache layers, and request arrival times. Do not treat 6 seconds as a fixed latency guarantee.

**Lab observation formulas:**

~~~text
detectionDelayMs = firstObservedNewCandidateListAtMs
                   - sourceChangedAtMs

staleWindowMs     = max(0, cacheExpireAtMs - sourceChangedAtMs)

measurementError  ≈ pollInterval + scheduling/network overhead
~~~

This expresses timing relationships, not a hard Spring Cloud SLA. `t_expire` is computed from **cache write time**, not from `t_source`. If no request arrives after expiration, **there is no reason to expect an immediate background refresh**.

## 3. Instance Caching Differs from Response Caching and Connection Pools

| Mechanism | Data Held | How Does Instance Change Affect It? |
|---|---|---|
| Registry/discovery state | Registered instances and metadata | Original source of change |
| Discovery client's local cache | Snapshot/registrations held by discovery adapter | Can delay new source reaching callers |
| `CachingServiceInstanceListSupplier` | `List<ServiceInstance>` per service ID | Can keep allowing removed instances to be chosen |
| HTTP connection pool | Sockets/HTTP connections to chosen host:port | Does not decide the candidate list |
| Application response cache | API DTOs/responses | Can skip remote calls altogether; unrelated to candidate list |
| Health-check supplier | Probe results and healthy instance set | Has its own refresh cycle; does not verify identity |

**Disabling HTTP keep-alive does not make LoadBalancer's cache fresher.** Removing an instance from a registry does not immediately close all open sockets either. Health checks detecting dead backends differ from detecting records removed from the source.

In the baseline lab, to measure one mechanism cleanly, we **leave the health-check supplier off**, **disable retries**, and **use no external discovery/registry**. There is only `TopologyState → MutableTopologySupplier → CachingServiceInstanceListSupplier → LoadBalancer`.

## 4. Architecture Diagram and Test Endpoints

~~~mermaid
flowchart LR
    P["POST /__lab/mode"] --> S["TopologyState: [A,B] or [A]"]
    S --> D["MutableTopologySupplier (sourceReads++)"]
    D --> C["CachingServiceInstanceListSupplier: TTL"]
    C --> LB["RoundRobinLoadBalancer"]
    Q["GET /demo/whoami"] --> RC["RestClient @LoadBalanced"]
    RC --> LB
    LB --> A["catalog-a:18081"]
    LB --> B["catalog-b:18082"]
    O["GET /__lab/source"] --> S
    I["GET /__lab/candidates"] --> C
~~~

| Application | Port | Endpoint |
|---|---:|---|
| Backend A | 18081 | `GET /api/whoami` |
| Backend B | 18082 | `GET /api/whoami` |
| Caller | 18090 | `GET /demo/whoami` |
| Caller lab control plane | 18090 | `GET /__lab/source`, `POST /__lab/mode` |
| Caller cache debug | 18090 | `GET /__lab/candidates` |

In the lab, mutating `TopologyState` simulates **synchronous, immediate** registry changes. Thus observed delay comes primarily from the LB cache. When swapping in Eureka/Kubernetes/Consul, real refresh/propagation mechanisms add further delay, though **you must not assume they simply add linearly in all cases**.

## 5. Preparing the Environment

Assume two separate Spring Boot projects, `catalog-backend` and `caller-service`, using Java 17+ and **compatible Spring Boot/Spring Cloud BOMs per release train**. The Java snippets use records, switch expressions, Spring Framework 6.1+ `RestClient`, and matching Spring Cloud LoadBalancer APIs.

**Backend – Gradle:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Caller – Gradle:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    // Enables Caffeine-backed LoadBalancer cache in the lab.
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-cloud-starter-loadbalancer` supplies Spring Cloud LoadBalancer; Caffeine on the classpath enables the matching cache implementation. This lesson's TTL config uses **`spring.cloud.loadbalancer.cache.ttl`**, omitting `spring.cloud.loadbalancer.cache.caffeine.spec` so a custom spec does not override general settings.

**Do not guess a hard-coded Spring Cloud version**; import the Spring Cloud BOM matching your Spring Boot version.

## 6. Backend A/B: Endpoint Returning Instance ID

In the backend project, create `lab.backend.BackendApplication`:

~~~java
package lab.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

Create `lab.backend.InstanceController`:

~~~java
package lab.backend;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InstanceController {

    private final String instanceId;

    InstanceController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "unknown");
    }

    @GetMapping("/api/whoami")
    Map<String, Object> whoami() {
        return Map.of(
            "instanceId", instanceId,
            "serverTimeMs", System.currentTimeMillis()
        );
    }
}
~~~

After building the backend into `catalog-backend.jar` using your project's build, run it in **two separate terminals**:

~~~bash
java -jar catalog-backend.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-backend.jar --server.port=18082 --instance.id=catalog-b
~~~

Test directly:

~~~bash
curl -s http://127.0.0.1:18081/api/whoami
curl -s http://127.0.0.1:18082/api/whoami
~~~

Expect `catalog-a` and `catalog-b` respectively. Do not stop a backend yet; the **source-change** experiment observes stale caching while both backends stay alive so you do not confuse it with connection refused.

## 7. Caller: Storing a Runtime-Mutable Topology Snapshot

In the caller project, create `lab.caller.TopologyState`. The initial source is `[A, B]`, with an incrementing revision on mode switches and a `sourceReads` counter tracking when the supplier actually fetches a new snapshot.

~~~java
package lab.caller;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.stereotype.Component;

@Component
public final class TopologyState {

    public enum Mode { BOTH, A_ONLY, B_ONLY, NONE }

    public record Snapshot(
        long revision,
        Mode mode,
        long changedAtMs,
        List<ServiceInstance> instances
    ) {}

    private static final String SERVICE_ID = "catalog-service";

    private final AtomicReference<Snapshot> current =
        new AtomicReference<>(new Snapshot(
            1,
            Mode.BOTH,
            System.currentTimeMillis(),
            instancesFor(Mode.BOTH)
        ));

    private final AtomicLong sourceReads = new AtomicLong();

    public Snapshot current() {
        return current.get();
    }

    // Called only by the supplier; increments counter on source read.
    public Snapshot readForSupplier() {
        sourceReads.incrementAndGet();
        return current.get();
    }

    public long sourceReadCount() {
        return sourceReads.get();
    }

    public synchronized Snapshot switchTo(Mode mode) {
        Snapshot previous = current.get();

        Snapshot next = new Snapshot(
            previous.revision() + 1,
            mode,
            System.currentTimeMillis(),
            instancesFor(mode)
        );

        current.set(next);
        return next;
    }

    private static List<ServiceInstance> instancesFor(Mode mode) {
        ServiceInstance a = new DefaultServiceInstance(
            "catalog-a", SERVICE_ID, "127.0.0.1", 18081, false
        );

        ServiceInstance b = new DefaultServiceInstance(
            "catalog-b", SERVICE_ID, "127.0.0.1", 18082, false
        );

        return switch (mode) {
            case BOTH -> List.of(a, b);
            case A_ONLY -> List.of(a);
            case B_ONLY -> List.of(b);
            case NONE -> List.of();
        };
    }
}
~~~

Design notes:

- `AtomicReference<Snapshot>` ensures a single read observes a consistent revision, mode, timestamp, and list.
- `List.of(...)` prevents arbitrary mutation of the collection once published.
- `current()` **observes the source without incrementing the counter**.
- `readForSupplier()` increments `sourceReads`; cache hits normally **do not** invoke this method.
- `changedAtMs` uses wall clock to display timestamps; for precise internal duration measurements, use a monotonic clock (`System.nanoTime()`) rather than subtracting clocks across two machines.
- Switching to `A_ONLY` and back to `BOTH` increments the revision even though the list returns to its prior state.

`DefaultServiceInstance` is sample data; the lab does not connect to a real discovery server. Never treat these measurements as sync-latency numbers for production Eureka/Consul/Kubernetes.

## 8. Custom Source Supplier: Fetching the Current Snapshot per Read

Place `lab.caller.MutableTopologySupplier` alongside `TopologyState`:

~~~java
package lab.caller;

import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

import reactor.core.publisher.Flux;

public final class MutableTopologySupplier
        implements ServiceInstanceListSupplier {

    private final TopologyState state;

    public MutableTopologySupplier(TopologyState state) {
        this.state = state;
    }

    @Override
    public String getServiceId() {
        return "catalog-service";
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return Flux.defer(() ->
            Flux.just(state.readForSupplier().instances())
        );
    }
}
~~~

Here `Flux.defer(...)` ensures each new subscription reads the latest snapshot. Without caching, after switching modes, subsequent supplier calls see the new list on the very next read.

**Do not return `Flux.empty()` in `NONE` mode.** A valid empty list is `Flux.just(List.of())`; that differs from "a publisher that emits no snapshot at all." Furthermore, some cache implementations/versions may not treat an empty list as a normal cache hit; watch `sourceReads` during the `NONE` experiment rather than assuming identical behavior to `[A, B]`.

## 9. Wrapping the Source Supplier with the LoadBalancer Cache

Create `lab.lb.CatalogLoadBalancerConfig` **in a package outside the default component scan** of `lab.caller.CallerApplication`.

~~~java
package lab.lb;

import lab.caller.MutableTopologySupplier;
import lab.caller.TopologyState;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.loadbalancer.cache.LoadBalancerCacheManager;
import org.springframework.cloud.loadbalancer.core.CachingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogLoadBalancerConfig {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            TopologyState topology,
            LoadBalancerCacheManager cacheManager,
            @Value("${lab.use-cache:true}") boolean useCache) {

        ServiceInstanceListSupplier source =
            new MutableTopologySupplier(topology);

        return useCache
            ? new CachingServiceInstanceListSupplier(
                source, cacheManager)
            : source;
    }
}
~~~

**This is the toggle between the two experiments**:

- `lab.use-cache=true`: path `MutableTopologySupplier → CachingServiceInstanceListSupplier → LoadBalancer`.
- `lab.use-cache=false`: LoadBalancer uses the source directly, without this cache decorator.

Keep `spring.cloud.loadbalancer.cache.enabled=true` in both lab runs so `LoadBalancerCacheManager` stays auto-configured and injectable. **Do not set `cache.enabled=false` while still injecting the manager unconditionally**, as some versions/configurations will not create the bean.

`CachingServiceInstanceListSupplier` wraps a delegate and a `CacheManager`; it sits **right after source retrieval**, ahead of other filters. This is the order recommended by Spring Cloud.

> In this lab there is only one chain for `catalog-service`. Do not add another caching supplier on the same source or enable `HealthCheckServiceInstanceListSupplier` simultaneously so TTL measurements do not mix with health scheduling. In real projects, verify exact APIs/autoconfiguration against your release train.

## 10. Binding Configuration per Service ID

Caller entry point `lab.caller.CallerApplication`:

~~~java
package lab.caller;

import lab.lb.CatalogLoadBalancerConfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLoadBalancerConfig.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

`CatalogLoadBalancerConfig` should sit outside `lab.caller` component scan so the supplier bean applies only inside `catalog-service`'s **LoadBalancer child context**, rather than accidentally registering as a global supplier.

### Caller's application.yml

~~~yaml
server:
  port: 18090

spring:
  application:
    name: caller-service
  cloud:
    loadbalancer:
      retry:
        enabled: false
      cache:
        enabled: true
        ttl: 6s
        capacity: 256

lab:
  use-cache: true
~~~

**Key semantics**:

- `cache.ttl: 6s` is the TTL measured **from cache entry write time**. This short value is intentional for easy observation, not a production recommendation.
- `capacity` is **initial capacity** per LoadBalancer config, not a hard ceiling on entries.
- Do not set `spring.cloud.loadbalancer.cache.caffeine.spec`; setting a custom Caffeine spec can override shared `ttl` and `capacity` settings.
- `retry.enabled=false` prevents confusing one logical call with multiple HTTP attempts while measuring caching.
- This config keeps health checks off so probe intervals are not confused with cache expiration.

## 11. RestClient Using Service ID Instead of Physical Ports

Create `lab.caller.CatalogClientConfig`:

~~~java
package lab.caller;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(1000);
        requestFactory.setReadTimeout(2000);

        return RestClient.builder().requestFactory(requestFactory);
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder) {

        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Using `@LoadBalanced` on the builder routes HTTP requests through Spring Cloud LoadBalancer. The request factory only provides lab I/O timeouts; it **does not govern instance cache lifetime**.

The client calls `http://catalog-service/api/whoami`, while LoadBalancer chooses a physical endpoint from the snapshot, such as `127.0.0.1:18081`. Creating a standalone `RestClient.create("http://catalog-service")` **does not automatically activate Spring's LoadBalancer**.

### Extending the Same Measurements to WebClient and OpenFeign

Once the `RestClient` lab converges properly, you can test **the same service ID and the same caching supplier** through `WebClient` or OpenFeign. Both are **optional** and unnecessary during the initial `RestClient` measurement.

`WebClient` requires `spring-boot-starter-webflux` and `@LoadBalanced WebClient.Builder`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfig {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

When multiple `WebClient.Builder` beans exist, qualify the `@LoadBalanced` builder with `@Qualifier`. The caller can invoke `catalogWebClient.get().uri("/api/whoami").retrieve().bodyToMono(String.class)` and await completion in an appropriate test; never call `block()` on a WebFlux event loop.

OpenFeign requires `spring-cloud-starter-openfeign`, `@EnableFeignClients`, and compatible LoadBalancer integration:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/api/whoami")
    String whoami();
}
~~~

When clients truly call service ID `catalog-service` inside the same caller, they share the same candidate list provided by the supplier context. However, **retries, HTTP transport, timeouts, and subscription timing differ**; disable retries and inspect `candidateIds` before comparing live HTTP responses. If Feign sets a static `url` or `WebClient` lacks `@LoadBalanced`, tests will bypass LoadBalancer.

## 12. Endpoints for Observing Source, Cache, and Real HTTP

Create `lab.caller.LabController` to inspect all three layers: current source, supplier list seen by LoadBalancer, and HTTP responses from target instances.

~~~java
package lab.caller;

import java.time.Duration;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class LabController {

    private final TopologyState topology;
    private final LoadBalancerClientFactory factory;
    private final RestClient client;

    LabController(TopologyState topology,
                  LoadBalancerClientFactory factory,
                  RestClient catalogRestClient) {
        this.topology = topology;
        this.factory = factory;
        this.client = catalogRestClient;
    }

    record SourceView(long observedAtMs, long revision,
        String mode, long changedAtMs,
        List<String> sourceIds, long sourceReads) {}

    record CandidateView(long observedAtMs, long sourceRevision,
        List<String> sourceIds, List<String> candidateIds,
        long sourceReads) {}

    record InstanceReply(String instanceId, long serverTimeMs) {}

    private static List<String> ids(List<ServiceInstance> instances) {
        return instances.stream()
            .map(ServiceInstance::getInstanceId).toList();
    }

    private SourceView view(TopologyState.Snapshot snapshot) {
        return new SourceView(
            System.currentTimeMillis(),
            snapshot.revision(),
            snapshot.mode().name(),
            snapshot.changedAtMs(),
            ids(snapshot.instances()),
            topology.sourceReadCount()
        );
    }

    @GetMapping("/__lab/source")
    SourceView source() {
        return view(topology.current());
    }

    @PostMapping("/__lab/mode")
    SourceView change(@RequestParam TopologyState.Mode mode) {
        return view(topology.switchTo(mode));
    }

    @GetMapping("/__lab/candidates")
    CandidateView candidates() {
        ServiceInstanceListSupplier supplier = factory.getInstance(
            "catalog-service", ServiceInstanceListSupplier.class);

        if (supplier == null) {
            throw new IllegalStateException("Missing catalog supplier");
        }

        List<ServiceInstance> visible = supplier.get()
            .next().block(Duration.ofSeconds(2));

        if (visible == null) {
            visible = List.of();
        }

        TopologyState.Snapshot snapshot = topology.current();

        return new CandidateView(
            System.currentTimeMillis(), snapshot.revision(),
            ids(snapshot.instances()), ids(visible),
            topology.sourceReadCount()
        );
    }

    @GetMapping("/demo/whoami")
    InstanceReply whoami() {
        return client.get()
            .uri("/api/whoami")
            .retrieve()
            .body(InstanceReply.class);
    }
}
~~~

How to interpret:

- `GET /__lab/source` inspects `TopologyState.current()` **without reading or warming the cache**.
- `POST /__lab/mode?mode=A_ONLY` mutates the source immediately without **automatically invalidating the cache**.
- `GET /__lab/candidates` reads the supplier in the service ID's child context, triggering a cache hit or miss.
- `GET /demo/whoami` executes an HTTP request through `@LoadBalanced RestClient`.

**Critical measurement caveat:** `GET /__lab/candidates` itself can trigger a refresh if the cache has expired. It is an active supplier read, not a purely passive cache peek. `block()` here is strictly for a Spring MVC blocking controller; do not copy this pattern onto a WebFlux event loop.

The `/__lab/*` endpoints have no authentication because this is a localhost-only lab; never deploy them to production.

## 13. Warming the Cache and Observing Source Reads

Keep both backends running, then start the caller:

~~~bash
java -jar caller-service.jar --server.port=18090
~~~

Read the source first:

~~~bash
curl -s http://127.0.0.1:18090/__lab/source
~~~

**Illustrative** response (not live measured data):

~~~json
{
  "observedAtMs": 1000000,
  "revision": 1,
  "mode": "BOTH",
  "changedAtMs": 999900,
  "sourceIds": ["catalog-a", "catalog-b"],
  "sourceReads": 0
}
~~~

Warm the cache entry:

~~~bash
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

Expected after the first cache miss:

~~~json
{
  "observedAtMs": 1000100,
  "sourceRevision": 1,
  "sourceIds": ["catalog-a", "catalog-b"],
  "candidateIds": ["catalog-a", "catalog-b"],
  "sourceReads": 1
}
~~~

Call `/__lab/candidates` again within the 6-second TTL. On a cache hit, `sourceReads` stays unchanged. Then observe real HTTP calls:

~~~bash
curl -s http://127.0.0.1:18090/demo/whoami
curl -s http://127.0.0.1:18090/demo/whoami
curl -s http://127.0.0.1:18090/demo/whoami
~~~

With Round Robin and healthy A/B, both IDs appear, yet **one response from A does not prove the cache dropped B**. Inspect `candidateIds` to see the active candidate set.

## 14. Experiment A: Source Drops B While Cache Still Holds A+B

**Setup:** both backends remain up; cache is warm with `[A,B]`; switch the source before the TTL expires.

~~~bash
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=A_ONLY"
curl -s http://127.0.0.1:18090/__lab/source
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

Before the cache expires, you can observe:

~~~text
SOURCE sourceIds    = [catalog-a]
CACHE candidateIds  = [catalog-a, catalog-b]
SOURCE revision     = 2
SOURCE readCount    = 1 (not refetched yet)
~~~

**This is proof of a stale list.** If LoadBalancer picks B during this window, backend B still returns 200 because we intentionally left B running. A successful request does not prove the candidate list is fresh.

Once the entry expires, a call to `/__lab/candidates` triggers a cache miss and loads the current source:

~~~text
SOURCE sourceIds    = [catalog-a]
CACHE candidateIds  = [catalog-a]
SOURCE readCount    = 2 (assuming one sequential refetch)
~~~

Do not demand the counter equal exactly 2 in every setup, as background traffic or multiple contexts could differ.

| Milestone | Source | Candidate List | Source Reads | Meaning |
|---|---|---|---|---|
| Warm | A+B | A+B | 1 | Cache populated |
| Switch source | A | A+B | 1 | Cache is stale |
| Early poll | A | A+B | 1 | Cache hit |
| Poll after expiry | A | A | 2 | Cache miss and refresh |
| Next poll | A | A | 2 | Fresh cache hit |

If A appears immediately after switching the source, the cache was probably **near TTL expiration** beforehand. Restart the caller, warm the cache, and switch the source sooner to reproduce cleanly.

## 15. PowerShell: Measuring Detection Delay via Polling

The following script measures using timestamps generated by the caller itself. For repeatable results under stable conditions, restart the caller to reset topology to `BOTH` with an empty cache before each run.

~~~powershell
$base = "http://127.0.0.1:18090"

$warm = Invoke-RestMethod "$base/__lab/candidates"
Write-Host "Warm candidates:" ($warm.candidateIds -join ",")

$change = Invoke-RestMethod -Method Post -Uri "$base/__lab/mode?mode=A_ONLY"
$changedAt = [long]$change.changedAtMs

$firstSeenAt = $null
for ($i = 0; $i -lt 80; $i++) {
    $view = Invoke-RestMethod "$base/__lab/candidates"
    $ids = @($view.candidateIds)
    $elapsed = [long]$view.observedAtMs - $changedAt

    Write-Host ("+{0} ms | reads={1} | cache={2}" -f $elapsed, $view.sourceReads, ($ids -join ","))

    if ($ids.Count -eq 1 -and $ids[0] -eq "catalog-a") {
        $firstSeenAt = [long]$view.observedAtMs
        break
    }

    Start-Sleep -Milliseconds 250
}

if ($null -eq $firstSeenAt) {
    throw "Cache did not converge within the polling budget"
}

Write-Host "Detection delay (ms):" ($firstSeenAt - $changedAt)
~~~

**Interpreting results properly:**

- `changedAtMs` is the timestamp when the source changed.
- `observedAtMs` is the timestamp when the server built the observation response.
- A 250 ms poll makes the detected timestamp **greater than or equal to** the true convergence moment.
- The first poll after expiration may itself be what triggers the cache refresh.
- TTL counts from **cache write**, not from `changedAtMs`.
- `detectionDelayMs` can be smaller than TTL because the cache already had some age before the source changed.

The values below are solely to illustrate the reasoning:

| TTL | Cache Age at Source Change | Approx. Remaining Stale Window |
|---|---:|---:|
| 6 s | 0.8 s | 5.2 s |
| 6 s | 3.5 s | 2.5 s |
| 6 s | 5.8 s | 0.2 s |

Real measurements also include sampling delay, scheduling, and overhead; never report illustrative numbers as benchmark output.

## 16. Experiment B: Comparing Cached vs. Uncached Modes

Stop the caller, **keep both backends running**, and run without the `CachingServiceInstanceListSupplier` wrapper:

~~~bash
java -jar caller-service.jar --server.port=18090 --lab.use-cache=false
~~~

Test:

~~~bash
curl -s http://127.0.0.1:18090/__lab/candidates
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=A_ONLY"
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

In this mode, the supplier pulls snapshots directly from `TopologyState`, so the next read immediately sees `[A]`, aside from scheduling/HTTP/polling overhead. `sourceReads` increments with every supplier call.

To test a 30-second TTL, stop the caller and run:

~~~bash
java -jar caller-service.jar --server.port=18090 --lab.use-cache=true --spring.cloud.loadbalancer.cache.ttl=30s
~~~

Do not try to alter a running process's TTL from another terminal command. Comparative runs should **restart the caller for a clean cache** and warm it at matching relative times.

| Mode | Source Reads | Time to See New Snapshot |
|---|---|---|
| `lab.use-cache=false` | Increments on every supplier read | Next source read |
| Cache TTL 6s | Fewer while entry stays valid | After entry expiry and new access |
| Cache TTL 30s | Longer cache hit window | Can stay stale longer |
| External discovery also caches | Multiple layers coexist | Measure each layer separately |

**Important:** `spring.cloud.loadbalancer.cache.enabled` stays `true` so the cache manager bean exists; `lab.use-cache=false` only skips **the lab's cache decorator**. If you set `cache.enabled=false` while unconditionally injecting `LoadBalancerCacheManager`, some versions/configurations fail to create the bean and the application fails to start.

## 17. Experiment C: Adding a New Instance and Switching Candidate Sets

Once the cached snapshot converges to `A_ONLY`, switch the source back to `BOTH`:

~~~bash
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=BOTH"
~~~

Before the `[A]` cache entry expires, the candidate list can still hold only A even though the source has A+B. That is **new-instance discovery lag**, which often slows down load redistribution during scale-out.

| Source Change | Stale List Potentially Returned | Consequence |
|---|---|---|
| `BOTH` → `A_ONLY` | A+B | B can still be chosen |
| `A_ONLY` → `BOTH` | A | B is not utilized yet |
| `A_ONLY` → `B_ONLY` | A | Traffic shift to B is delayed |
| `BOTH` → `NONE` | A+B | May keep picking removed instances |
| `NONE` → `BOTH` | May see source sooner than expected | Empty-list caching depends on implementation |

**`NONE` experiment:** the source supplier emits `Flux.just(List.of())`, though do not assume an empty list caches identically to a non-empty snapshot. In some versions, cache lookups treat an empty list as a miss. Watch `sourceReads` and record actual observed behavior.

## 18. Experiment D: Stopping a Backend While Cache Still Holds B

This scenario is closer to production and easy to misread if you look only at HTTP errors.

1. Restart the caller and warm the `[A,B]` cache.
2. Switch the source to `A_ONLY` while the cache is still valid.
3. **Stop backend B** on port 18082.
4. Call `/demo/whoami` repeatedly while `/__lab/candidates` still shows `[A,B]`.
5. Wait for TTL expiration, inspect the candidate list, and call again.

While the cache still holds B:

- LoadBalancer picks A → HTTP 200, everything looks normal.
- LoadBalancer picks B → may throw `ConnectException`, connection refused, or an I/O error depending on transport.
- If a connection pool held an open socket to B, requests may hit reset/disconnect after B stopped.
- After the cache refreshes to `[A]`, **new requests through LoadBalancer** stop picking B unless another policy intervenes.

**Never treat connection refused as proof that backend B sent HTTP 503**. It is a connection error before any HTTP response from B exists. Likewise, never treat a single successful request to A as proof that the cache has converged.

In the lab, `spring.cloud.loadbalancer.retry.enabled=false` keeps single calls from hiding extra attempts. Production may retry safe GETs with bounded budgets and updated lists, yet retries **do not fix** a stale snapshot before cache miss/refresh.

## 19. Capturing the Right Timeline to Analyze Delay

An observation table should include:

| Field | Question Answered |
|---|---|
| `sourceRevision` | How many times did the source change? |
| `changedAtMs` | When did the source change? |
| `sourceIds` | What is the authoritative source list? |
| `candidateIds` | Which candidates is LoadBalancer actually using? |
| `sourceReads` | How many times did the supplier read the source? |
| `observedAtMs` | When was this observation recorded? |
| `cache.ttl` / `lab.use-cache` | Is caching on, and what is the TTL? |
| `pollIntervalMs` | What is the sampling uncertainty? |
| HTTP selected instance, status, cause | Where did the real request go, and did a network error occur? |
| Discovery/client/transport version | Which implementation details affect semantics? |

**Illustrative** target log (not executed test data):

~~~text
warmAt=1000100 sourceRevision=1 candidates=[A,B] reads=1
changedAt=1001100 sourceRevision=2 source=[A]
observedAt=1001300 candidates=[A,B] reads=1
observedAt=1003100 candidates=[A,B] reads=1
observedAt=1006300 candidates=[A] reads=2
detectionDelayMs=5200
~~~

Concluding convergence from a single HTTP response from A is wrong: Round Robin may still hold B in the list and simply have picked A on that turn. To confirm a new candidate set, inspect `candidateIds` or equivalent LoadBalancer telemetry.

When multiple caller processes run independently, **each caller holds its own local cache**. One caller converging does not mean all callers converged. Measure delay distribution across instances/callers.

## 20. Analyzing Multiple Sources of Delay in Production

The lab uses an in-memory source, so it has zero real-registry propagation delay. With Eureka/Consul/Kubernetes or a custom control plane, the pipeline is longer:

~~~mermaid
flowchart TD
    A["Change committed in control plane"] --> B["Registry / service discovery"]
    B --> C["Discovery watch, poll, or local cache"]
    C --> D["ServiceInstanceListSupplier source"]
    D --> E["LoadBalancer cache"]
    E --> F["Health / zone / version filter"]
    F --> G["LoadBalancer selects ServiceInstance"]
    G --> H["HTTP connection / request"]
    H --> I["Backend returns response or error"]
~~~

Measure at least three timestamps: **when the registry learns of the change**, **when the discovery adapter returns the new snapshot**, and **when the LoadBalancer supplier returns the new snapshot**. If health checks are active, also measure when the health supplier removes or adds candidates.

A topology update can converge through multiple mechanisms: watches/pushes, periodic polls, TTL caches, timeouts, or explicit invalidation. **Do not sum all TTLs as an exact formula for every system**: intervals can overlap, run concurrently, or be request-triggered.

For instance, a 10-second discovery poll plus a 6-second LB cache TTL can yield nearly 16 seconds in an unlucky phase alignment, or converge much faster. Measuring only **end-to-end detection delay** is not enough to tell which layer needs tuning.

## 21. Health Checks: Fresh Source Does Not Mean Fresh Healthy Set

The baseline lab disables `HealthCheckServiceInstanceListSupplier`. If enabled in a second experiment:

- An instance may still appear in the source while health checks mark it unhealthy and avoid selecting it.
- Conversely, the source may have changed while the health supplier keeps an older snapshot until its own refetch schedule fires.
- Properties like `spring.cloud.loadbalancer.health-check.refetch-instances` and `refetch-instances-interval` govern list refresh.
- Health checks are not security checks: a rogue instance could still return HTTP 200.
- When **zero instances are healthy**, some configurations fall back to the raw input list; do not assume the candidate list is guaranteed empty.

Reference properties for a **separate health lab**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 0s
        interval: 2s
        path:
          catalog-service: /actuator/health
        refetch-instances: true
        refetch-instances-interval: 3s
~~~

Properties alone **do not add the health supplier**. You must adjust the supplier chain with `withHealthChecks()` or `withBlockingHealthChecks()` as appropriate, and expose a health endpoint (such as Spring Boot Actuator).

Spring Cloud notes that `HealthCheckServiceInstanceListSupplier` has its own caching via Reactor `replay()`, so **do not blindly stack `CachingServiceInstanceListSupplier` on top of it**. When measuring, change one layer at a time and document the exact supplier order.

## 22. Caffeine Specification Can Override TTL

For LoadBalancer caching, general properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 6s
        capacity: 256
~~~

can be overridden by a dedicated Caffeine specification, such as:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        caffeine:
          spec: expireAfterWrite=30s,maximumSize=500
~~~

When `caffeine.spec` is present, never look at `cache.ttl=6s` alone and assume 6-second expiration. A custom spec can override TTL and capacity.

Furthermore, `capacity` is **initial capacity**, not a hard cap on service IDs or sockets. Caching the instance list **is not** response caching and does not replace a connection pool.

### Double Caching

If `DiscoveryClient` already caches the list, adding LB caching creates two layers:

~~~text
Registry changes -> Discovery cache still holds [A,B]
                 -> LB cache expires and re-reads Discovery
                 -> LB cache writes stale [A,B] again
~~~

In this case, lowering LB TTL to 1 second still will not surface new replicas if **discovery has not refreshed**. Identify which layer holds stale data rather than hammering the registry unnecessarily. Spring Cloud docs recommend avoiding double caching when discovery already maintains its own cache.

## 23. Cache Expiry Is Not a Security Revocation Mechanism

There is a crucial difference between stale topology during autoscaling and stale topology after **an instance is revoked due to loss of trust**.

- **TTL expiration:** the entry becomes stale in cache; typically requires an access to fetch fresh data.
- **Explicit invalidation:** evicts cache entries upon a trusted control-plane event.
- **Registry push/watch:** the source updates quickly yet does not automatically invalidate the LB cache.
- **Network egress / certificate revocation:** blocks requests to disallowed targets even while callers still hold stale caches.

**Never treat a 6-second TTL as a guarantee that "after 6 seconds no caller can ever reach B."** Multiple callers have different cache ages, in-flight requests, multiple discovery/gateway layers, and open pooled connections. For emergency revocation, enforce network/identity controls independent of local caches.

For routine scale-outs, shorter TTLs improve freshness at the cost of higher cache misses and registry load; balance according to your SLOs and traffic volume.

## 24. Test Plan and Acceptance Criteria

| Test Case | Condition | Correct Assertion |
|---|---|---|
| Warm `BOTH` | Two backends running, empty cache | Candidates A+B |
| Runtime source change | POST `mode=A_ONLY` | Source revision increments, `sourceIds=A` |
| Stale window | Switch to `A_ONLY` before TTL | Candidate list can still be A+B |
| Cache refresh | Poll after TTL | Candidate list converges to A |
| Uncached | `lab.use-cache=false` | Next read sees A |
| Long TTL | 30s instead of 6s, restart caller | Stale window can last longer |
| Scale-out | `A_ONLY`→`BOTH` | B may take time to appear |
| `NONE` | Source has no candidates | No target chosen after convergence; inspect empty caching |
| Dead backend | Cache still holds B, backend B stopped | Classify as connect error, not HTTP 503 |
| Double cache | Mock discovery has its own cache | LB refetch can still receive stale source data |
| Health supplier | Scheduled probe and refetch | Measure health convergence separately |
| Multiple callers | Two processes with separate caches | Detection delays differ |
| Open connections | Pool holds open socket to B | Socket state differs from instance-list state |

### Avoiding Flakiness in CI

Never assert convergence at **exactly 6,000 ms** via `Thread.sleep(6000)`. Instead:

1. Warm the cache with clear timestamps and revisions.
2. Switch the source well before the TTL expires.
3. Verify the new source before the new cache state.
4. Poll at a fixed interval within a bounded test deadline.
5. Assert the candidate list **eventually** reaches the desired state; log `detectionDelayMs`.
6. Do not assert Round Robin order unless specifically testing that algorithm.
7. When testing exact expiration timing, use a cache test harness with a **controllable clock/ticker** rather than relying on wall-clock timing.

In the current step we are authoring documentation only; the tests and benchmarks described here **have not been executed**.

## 25. Output Prediction Exercises

**Question A:** Cache writes `[A,B]` at t=0 with TTL 6s. Source drops B at t=4s. Caller reads supplier at t=4.2s and t=6.3s. With no other cache layers, predict the outputs.

**Hint/Answer:** t=4.2s can still return `[A,B]`; at t=6.3s the entry has exceeded its TTL and the access can refresh it to `[A]`.

**Question B:** If the cache expires while no requests arrive for 20 seconds, can we claim the cache fetched the source at second 6? **No**; expiration does not imply proactive background refresh.

**Question C:** Backend B stops, yet a retried GET succeeds on A. Has the cache converged? **Not necessarily**; inspect `candidateIds` or the actual cache contents.

**Question D:** Why does a 200 health probe not prove a new instance is visible to discovery and LoadBalancer? Because health checks, registration, and LoadBalancer's candidate list are **separate state boundaries**.

**Question E:** With `cache.ttl=6s` and `cache.caffeine.spec=expireAfterWrite=30s`, which bound governs expiration? Inspect the effective configuration; the Caffeine spec can override the general TTL.

## 26. Lab Completion Checklist

- Ran two distinct backends A/B and one caller routing by service ID.
- Caller uses `@LoadBalanced RestClient.Builder` instead of hard-coding physical ports.
- `@LoadBalancerClient` applies the custom supplier only to `catalog-service`.
- `TopologyState` source changes **without restarting**.
- `/__lab/source` does not trigger a cache refetch.
- `/__lab/candidates` reads the supplier list and can trigger cache misses.
- Tracked `sourceReads`, `revision`, and `changedAtMs`.
- Observed a window where **`sourceIds` differed from `candidateIds`**.
- Observed candidates converging after TTL expiration and a subsequent read.
- Measured detection delay with explicit polling intervals.
- Compared cached and uncached modes.
- Tested different TTLs and recorded warm-up conditions.
- Did not treat an HTTP 200 from A as proof that B was removed.
- Understood the difference between a stale list and a dead backend/connection pool.
- Isolated health/refetch/retry from baseline cache measurements.
- Did not deploy unauthenticated `/__lab/*` endpoints to public environments.

## 27. Conclusion

**Stale caching is an observable, measurable state.** Once the source shifts from `[catalog-a, catalog-b]` to `[catalog-a]`, LoadBalancer can keep receiving the old list for the remainder of the cache entry's lifetime. Only after the entry expires and an access triggers a refetch is the new candidate set observed.

**TTL counts from cache write time, not from topology change time.** Detection delay also depends on cache age when the source changed, polling intervals, discovery/health refreshes, and other cache layers. When operating `RestClient`, `WebClient`, or OpenFeign with Spring Cloud LoadBalancer, measure **source, candidate list, and HTTP results** independently, avoid unnecessary double caching, and never treat a successful retry as proof that the `ServiceInstance` list has converged.

## References

- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons configuration properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Framework RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Caffeine cache concepts: https://github.com/ben-manes/caffeine
