# Testing Algorithm Correctness, Fairness, and Overhead

When writing a custom load-balancing algorithm for **Spring Cloud LoadBalancer**, seeing requests reach a replica is not enough to conclude the algorithm is right. An algorithm can pass manual checks yet still pick filtered-out instances, skew distribution over time, cause thread contention, allocate too many objects, or spike selection latency when thousands of `ServiceInstance` entries exist.

This lesson belongs to the **Customizing LoadBalancer** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The goal is building a repeatable test suite for **correctness**, **fairness**, and **algorithmic cost (overhead)** in service-to-service communication. The examples connect to service IDs, `ServiceInstanceListSupplier`, discovery/health/zone policies, RestClient, WebClient, and OpenFeign; performance measurement cleanly separates instance-selection cost from total HTTP duration.

## 1. Three Questions That Must Be Tested Independently

| Dimension | Key question | Verification criteria |
|---|---|---|
| **Correctness** | Did it pick a valid instance, right service ID, and right policy? | Never picks outside candidate set; handles empty lists; respects metadata/request context |
| **Fairness** | Does each instance's selection share match the declared strategy? | Round Robin balanced over a stable list; Random/Weighted matches expected probability distribution |
| **Cost** | Does picking an instance consume excessive CPU, memory, allocations, or lock contention? | Complexity, p95/p99 selection time, throughput, allocations, and contention under high concurrency |

An algorithm can be **correct and fair yet slow**, or **fast and correct yet unfair**, or pass all three in unit tests yet degrade under discovery, retries, caching, and HTTP transport in production.

For example, a picker that "always takes the first element" is `O(1)` and never picks outside the candidate set; yet with 3 equally weighted healthy replicas, it routes 100% of requests to one backend. Conversely, an algorithm scanning and sorting the entire candidate list on every request may pick valid targets yet incur `O(n log n)` unnecessary work.

### Three Test Layers to Separate

~~~mermaid
flowchart TB
    A["Layer 1: Pure picker unit tests"] --> B["Layer 2: ReactorLoadBalancer and supplier tests"]
    B --> C["Layer 3: HTTP integration / chaos / performance"]
    A --> D["Deterministic correctness + fairness"]
    B --> E["Request context, discovery, filters, no-instance"]
    C --> F["Real instances, retries, p99 latency, overhead"]
~~~

Each layer answers different questions. A unit test of `choose()` does not prove WebClient carries the LoadBalancer filter; an HTTP load test does not prove the picker is free of race conditions on a single-instance list.

## 2. Target Selection Model in Spring Cloud

Spring Cloud LoadBalancer uses `ReactiveLoadBalancer`/`ReactorServiceInstanceLoadBalancer` and a `ServiceInstanceListSupplier` candidate source. For service ID `inventory-service`, the conceptual chain is:

~~~mermaid
flowchart LR
    A["Caller: service ID"] --> B["ServiceInstanceListSupplier"]
    D["DiscoveryClient"] --> B
    B --> C["Cache / health / zone / hint policy"]
    C --> E["Candidate snapshot"]
    E --> F["Custom ReactorServiceInstanceLoadBalancer"]
    F --> G["One ServiceInstance or EmptyResponse"]
    G --> H["HTTP client transport"]
~~~

Key decisions:

- **Candidate source**: discovery may return new/stale instances, multiple instances across zones, or an empty list.
- **Policy filtering**: health, hints, zone, version, sticky preference, or request-aware suppliers can modify the candidate set prior to selection.
- **Picker**: Round Robin, Random, Weighted, least-active, hash/affinity, or custom policy.
- **HTTP integration**: RestClient, WebClient, and OpenFeign select instances when configured with Spring Cloud LoadBalancer integration.
- **Retries**: one *logical request* can select an instance multiple times; `choose` call counts differ from requests received by backends.

Tests must record the **candidate list at the exact moment of selection**, not merely the initial list registered in discovery. If a zone filter removes one replica, it must not be counted in the denominator when evaluating picker fairness.

## 3. Write the "Correctness Contract" Before Writing Assertions

For example, a Round Robin picker for `inventory-service` has this contract:

1. If the list is empty, return "no instance"; never try accessing index 0.
2. If the list has one element, always return that instance.
3. If the list has N elements, return only an element present in the received candidate list.
4. If the supplier applies zone/hint/health filters, never re-select an excluded instance.
5. Over a **stable list snapshot**, across `k × N` consecutive selections, each candidate is selected `k` times (regardless of starting position).
6. Across multiple threads, no race causes out-of-bounds indices or picks outside the snapshot.
7. Never make network calls or block the event loop inside pure selection logic.
8. When no instance exists, never fabricate a `DefaultResponse` wrapping null.
9. Never reuse prior request state to leak tenant, hint, or zone onto the next request.
10. When input conditions change, **safety** invariants still hold; "strict alternation" may no longer apply.

If the algorithm is Random/Weighted/Sticky, replace item 5 with its matching contract. A weighted algorithm is **not supposed to be fair** under raw equal-count checks like Round Robin when weights differ; fairness here means matching target weight proportions.

### Minimum Test Case Matrix

| Input | Behavior to verify | Common failure |
|---|---|---|
| No instance | `EmptyResponse` or empty Optional | `IndexOutOfBoundsException`/divide by zero |
| One instance | Always returns that sole instance | Returning null or corrupting state |
| Two/three instances | Selected instance belongs to valid set | Returning an out-of-set instance |
| Mutable/changing list | No crash, never uses old size for index | `IndexOutOfBoundsException` |
| Weight 0/negative/malformed | Clear policy: reject/fallback | Negative probability/NaN/overflow |
| Zone has no candidates | Fallback matches policy | Unauthorized cross-zone selection violating contract |
| Hint, version, tenant | Picks only policy-compliant candidates | Old request context leakage |
| Supplier returns error | Propagate/fallback per contract | Swallowing errors into fake success |
| High concurrency | Preserves safety without severe hotspots | Race conditions and contention |
| Retries | Can switch instances if policy requires | Infinite loop on broken backend |

## 4. Separate the Pure Selection Algorithm from Spring Adapters

A useful technique is placing selection logic in a small class **free of HTTP, Spring context, or Reactor**. Unit tests can then verify the algorithm independently and deterministically.

Example `RoundRobinPicker`:

~~~java
package com.example.loadbalancer;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.cloud.client.ServiceInstance;

public final class RoundRobinPicker {

    private final AtomicLong sequence = new AtomicLong();

    public Optional<ServiceInstance> pick(
            List<ServiceInstance> candidates) {

        if (candidates == null || candidates.isEmpty()) {
            return Optional.empty();
        }

        long ticket = sequence.getAndIncrement();

        // Valid even when AtomicLong wraps.
        int index = (int) Long.remainderUnsigned(
                ticket,
                candidates.size()
        );

        return Optional.of(candidates.get(index));
    }
}
~~~

### Design Notes

- `AtomicLong` gives threads distinct tickets without locking the whole method.
- `Long.remainderUnsigned` treats tickets as unsigned integers, preventing negative indices if the counter wraps past `Long.MAX_VALUE`.
- `Optional.empty()` signals no candidates.
- The algorithm returns **an existing instance from the input list**, creating no new `ServiceInstance` objects.
- Over a **stable** list, the `i`-th selection gets index `i mod N`, selecting every element once per N turns.
- If the list changes size or order, "strict per-replica alternation" is not guaranteed across snapshots; the safety property *selected ∈ current candidates* must still hold.
- The code assumes `candidates` is a **read-only list snapshot** for the duration of the call. If a supplier provides a concurrently mutated list, snapshot at the publisher/supplier boundary; avoid unconditional `List.copyOf` on every selection if aiming to evaluate `O(1)` overhead.

Note: this is an **illustrative algorithm for testing**, not a recommendation to replace Spring Cloud's standard `RoundRobinLoadBalancer`. The standard implementation has its own logic/callbacks and edge-case handling (e.g., single-instance suppliers) that custom adapters must weigh in production.

## 5. Correctness Unit Tests: Empty, Single Instance, Multiple Instances

Build test fixtures using `DefaultServiceInstance`:

~~~java
package com.example.loadbalancer;

import java.util.List;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;

public final class Fixtures {

    private Fixtures() {}

    public static List<ServiceInstance> threeInstances() {
        return List.of(
                new DefaultServiceInstance(
                        "A", "inventory-service", "127.0.0.1", 8081, false),
                new DefaultServiceInstance(
                        "B", "inventory-service", "127.0.0.1", 8082, false),
                new DefaultServiceInstance(
                        "C", "inventory-service", "127.0.0.1", 8083, false)
        );
    }
}
~~~

JUnit Jupiter tests:

~~~java
package com.example.loadbalancer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;

class RoundRobinPickerTest {

    @Test
    void emptyListNeverSelectsAnInstance() {
        RoundRobinPicker picker = new RoundRobinPicker();

        assertTrue(picker.pick(List.of()).isEmpty());
    }

    @Test
    void aSingleCandidateIsAlwaysSelected() {
        RoundRobinPicker picker = new RoundRobinPicker();
        ServiceInstance only = Fixtures.threeInstances().get(0);

        for (int i = 0; i < 100; i++) {
            assertEquals(only, picker.pick(List.of(only)).orElseThrow());
        }
    }

    @Test
    void oneCompleteCycleChoosesEveryCandidate() {
        RoundRobinPicker picker = new RoundRobinPicker();
        List<ServiceInstance> instances = Fixtures.threeInstances();

        for (int i = 0; i < 3; i++) {
            assertEquals(instances.get(i),
                    picker.pick(instances).orElseThrow());
        }
    }
}
~~~

This test is **deterministic** because `RoundRobinPicker` starts its ticket at 0. For Spring's `RoundRobinLoadBalancer` which uses an initial seed or different cursor behavior, never assert the first element is always A: instead verify *all N candidates appear within N selections*.

### Testing Safety Properties Under List Changes

~~~java
@Test
void neverChoosesOutsideTheCurrentSnapshot() {
    RoundRobinPicker picker = new RoundRobinPicker();
    List<ServiceInstance> all = Fixtures.threeInstances();

    List<List<ServiceInstance>> snapshots = List.of(
            all,
            all.subList(0, 2),
            List.of(all.get(2)),
            List.of(),
            List.of(all.get(1), all.get(2))
    );

    for (int round = 0; round < 500; round++) {
        for (List<ServiceInstance> current : snapshots) {
            var selected = picker.pick(current);

            if (current.isEmpty()) {
                assertTrue(selected.isEmpty());
            } else {
                assertTrue(selected.isPresent());
                assertTrue(current.contains(selected.orElseThrow()));
            }
        }
    }
}
~~~

This test does not require every replica to be chosen equally across changing snapshots. **Fairness must be evaluated over candidate sets with consistent eligibility**, not lumped together across heterogeneous windows.

## 6. Deterministic Fairness Unit Test for Round Robin

Over N fixed instances, an ideal Round Robin satisfies:

\[
|c_i-c_j|\leq1 \quad \text{for all }i,j
\]

after `K` completed sequential or concurrent selections, assuming a single shared counter and one ticket per selection.

Example for 3 instances, 12,000 selections:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

@Test
void equalCandidatesHaveExactlyEqualCountAcrossFullCycles() {
    RoundRobinPicker picker = new RoundRobinPicker();
    var instances = Fixtures.threeInstances();

    Map<String, Integer> counts = new HashMap<>();

    for (int i = 0; i < 12_000; i++) {
        String id = picker.pick(instances)
                .orElseThrow()
                .getInstanceId();

        counts.merge(id, 1, Integer::sum);
    }

    assertEquals(4_000, counts.get("A"));
    assertEquals(4_000, counts.get("B"));
    assertEquals(4_000, counts.get("C"));
}
~~~

This is a **valid test for the picker on stable input**, not a promise that successful HTTP responses from three backends will be equal: retries, timeouts, connection reuse, and uneven backend load can make responses/latency differ even when selections are perfectly balanced.

When `K` is not divisible by `N`, assert `max(counts)-min(counts)≤1` rather than exact equality. When testing Spring's built-in implementation, allow for an unknown initial seed.

## 7. Concurrency Testing: Safety Before Fairness

In production, many threads or reactive subscriptions call the picker concurrently. An implementation like this is **unsafe**:

~~~java
// Anti-pattern: non-atomic increment.
private long position = 0;

int next = (int) (position++ % candidates.size());
~~~

Two threads can read the same ticket, dropping a turn and skewing distribution. Switching to `AtomicLong` or another concurrency primitive fixes the counter race, though you must still test candidate lists, callbacks, and per-request state.

Test with 16 workers:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;
import org.junit.jupiter.api.Test;

@Test
void concurrentCallsKeepPerInstanceCountsBalanced()
        throws Exception {

    RoundRobinPicker picker = new RoundRobinPicker();
    var instances = Fixtures.threeInstances();

    int workers = 16;
    int loopsPerWorker = 600; // 9600 calls, divisible by 3.
    ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    ExecutorService executor =
            Executors.newFixedThreadPool(workers);

    try {
        List<Future<?>> futures = new ArrayList<>();

        for (int worker = 0; worker < workers; worker++) {
            futures.add(executor.submit(() -> {
                for (int i = 0; i < loopsPerWorker; i++) {
                    String id = picker.pick(instances)
                            .orElseThrow()
                            .getInstanceId();

                    counts.computeIfAbsent(
                            id, key -> new LongAdder()
                    ).increment();
                }
            }));
        }

        for (Future<?> future : futures) {
            future.get(10, TimeUnit.SECONDS);
        }
    } finally {
        executor.shutdownNow();
    }

    assertEquals(3_200L, counts.get("A").sum());
    assertEquals(3_200L, counts.get("B").sum());
    assertEquals(3_200L, counts.get("C").sum());
}
~~~

This is a correctness/concurrency test, **not a throughput benchmark**. The timeout in `future.get(...)` only prevents the test from hanging forever; never treat 10 seconds as an algorithm latency SLO. For hard-to-reproduce races, run varied interleavings or dedicated concurrency stress harnesses in a separate pipeline.

Another pitfall is **calling `choose` twice for the same request**, rather than a race inside the picker. When multiple layers retry, selection counts and backend-received request counts diverge; before concluding "a ticket was lost," confirm whether you are observing selections or HTTP attempts.

## 8. Property-Based Testing and Adversarial Inputs

Unit tests with 3 instances are just a start. Custom algorithms must be tested across varied list sizes, metadata sets, and candidate orderings.

Useful properties:

- **Safety**: `selected == empty` when `candidates.isEmpty()`; otherwise `selected ∈ candidates`.
- **Identity**: `selected.getServiceId()` must match the service ID guaranteed by the supplier; if the algorithm accepts unfiltered lists directly, validate or establish a contract with the supplier.
- **No input mutation**: selection never alters order, size, or metadata of a shared candidate list.
- **Single output per call**: one chooser invocation emits a single `Response<ServiceInstance>`.
- **Determinism with seed**: a Random algorithm with an injected RNG and fixed seed must reproduce identical sequences for identical inputs in unit tests.
- **Constrained eligibility**: if a request allows only zone A, never return zone B unless fallback is explicitly specified.
- **Bounded complexity**: never loop infinitely when total weight is 0 or metadata is malformed.
- **Overflow safety**: counters, total weights, and indices remain valid after massive operation counts or boundary values.

Property test pseudocode example:

~~~text
repeat for lists with size from 0 to 1_000:
    snapshot = immutableCopy(generatedInstances)
    response = picker.pick(snapshot)

    if snapshot is empty:
        assert response is empty
    else:
        assert response is present
        assert snapshot contains response.instance

    assert snapshot remains unchanged
~~~

You can use jqwik or QuickTheories for generated inputs; there is no need to force a property-testing framework just to run basic examples. If generators run in CI, log seeds and failing inputs so failures are reproducible.


## 9. Wiring the Pure Picker into ReactorServiceInstanceLoadBalancer

For a Spring Cloud app to use the tested picker, write an adapter implementing `ReactorServiceInstanceLoadBalancer.choose(Request)`. The adapter is responsible for calling **`ServiceInstanceListSupplier.get(request)`** instead of reading IPs from YAML directly, wrapping results in `DefaultResponse` or `EmptyResponse`, and notifying callbacks when required by the supplier.

~~~java
package com.example.loadbalancer;

import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.client.loadbalancer.Response;
import org.springframework.cloud.loadbalancer.core.ReactorServiceInstanceLoadBalancer;
import org.springframework.cloud.loadbalancer.core.SelectedInstanceCallback;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Mono;

public final class TestedRoundRobinLoadBalancer
        implements ReactorServiceInstanceLoadBalancer {

    private final ObjectProvider<ServiceInstanceListSupplier> provider;
    private final RoundRobinPicker picker = new RoundRobinPicker();

    public TestedRoundRobinLoadBalancer(
            ObjectProvider<ServiceInstanceListSupplier> provider) {
        this.provider = provider;
    }

    @Override
    public Mono<Response<ServiceInstance>> choose(Request request) {
        return Mono.defer(() -> {
            ServiceInstanceListSupplier supplier =
                    provider.getIfAvailable();

            if (supplier == null) {
                return Mono.just(new EmptyResponse());
            }

            return supplier.get(request)
                    .next()
                    .map(candidates -> chooseFrom(supplier, candidates))
                    .defaultIfEmpty(new EmptyResponse());
        });
    }

    private Response<ServiceInstance> chooseFrom(
            ServiceInstanceListSupplier supplier,
            List<ServiceInstance> candidates) {

        var selected = picker.pick(candidates);

        if (selected.isEmpty()) {
            return new EmptyResponse();
        }

        ServiceInstance instance = selected.orElseThrow();

        if (supplier instanceof SelectedInstanceCallback callback) {
            callback.selectedServiceInstance(instance);
        }

        return new DefaultResponse(instance);
    }
}
~~~

**Things to test in the adapter:**

- `Mono.defer(...)` fetches the supplier upon subscription rather than capturing state when the publisher is built.
- `get(request)` preserves `Request` context for hint/zone/retry-aware suppliers; calling `get()` drops request data policies rely on.
- `.next()` takes one snapshot from `Flux<List<ServiceInstance>>`. If the Flux emits nothing, return `EmptyResponse` rather than an ambiguous empty Mono.
- An empty list also returns `EmptyResponse`; never invoke the selection callback.
- If `supplier` implements `SelectedInstanceCallback`, invoke the callback only on successful selection.
- Supplier errors propagate; never turn a severe registry failure into a fake server response.
- `RoundRobinPicker` holds one counter per **adapter instance**. Spring Cloud creates child contexts per service ID; never use a static counter that accidentally shares cursors across service IDs without reason.

This adapter illustrates correctness of a Round Robin picker. In production, account for semantics of your exact Spring Cloud version, health/discovery fallbacks, callbacks, and source supplier thread safety. Never write a custom picker when Spring's built-in implementation satisfies your requirements.

## 10. Registering the Algorithm for Only One Service ID

Using `@LoadBalancerClient`:

~~~java
package com.example.order;

import com.example.loadbalancer.InventoryLbConfiguration;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLbConfiguration.class
)
public class LoadBalancerRoutingConfiguration {
}
~~~

Configuration for the LoadBalancer child context:

~~~java
package com.example.loadbalancer;

import org.springframework.beans.factory.annotation.Bean;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.core.env.Environment;

public class InventoryLbConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> testedLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId =
                environment.getProperty(
                        LoadBalancerClientFactory.PROPERTY_NAME
                );

        return new TestedRoundRobinLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId,
                        ServiceInstanceListSupplier.class
                )
        );
    }
}
~~~

Place `InventoryLbConfiguration` **outside the application's component scan scope**, or omit annotations that would scan it as global config. This is critical in Spring Cloud: `@LoadBalancerClient` configuration must apply strictly to the target service ID. `ReactorLoadBalancer<ServiceInstance>` beans accidentally placed in the parent context can affect other services.

In this example, one bean with `@LoadBalancerClient` targets `inventory-service` alone. `payment-service` continues using default Round Robin or its own dedicated config.

### Do Not Test with Physical URIs When Testing LoadBalancer

~~~java
// Logical URI: LoadBalancer can select a ServiceInstance.
inventoryRestClient.get()
        .uri("http://inventory-service/api/items/123");

// Physical URI: no longer tests service-id-based selection.
ordinaryRestClient.get()
        .uri("http://localhost:8081/api/items/123");
~~~

With WebClient, test the proper `@LoadBalanced` builder or `ReactorLoadBalancerExchangeFilterFunction`. With OpenFeign, `@FeignClient(name="inventory-service")` must omit a static `url` and have proper LoadBalancer integration configured. If Feign has a fixed URL, calls bypass client-side LoadBalancer and algorithm tests are meaningless.

## 11. Testing the Reactive Adapter: Supplier, EmptyResponse, and Callback

Once the pure algorithm is verified, test **integration** with `ServiceInstanceListSupplier`. Spring Cloud provides `ServiceInstanceListSuppliers.toProvider(...)` to wrap static instance lists in tests without starting a service registry.

Test example with Reactor Test:

~~~java
package com.example.loadbalancer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultRequest;
import org.springframework.cloud.loadbalancer.support.ServiceInstanceListSuppliers;
import reactor.test.StepVerifier;

class TestedRoundRobinLoadBalancerTest {

    @Test
    void choosesOnlyInstancesFromSupplier() {
        ServiceInstance a = new DefaultServiceInstance(
                "A", "inventory-service", "127.0.0.1", 8081, false);
        ServiceInstance b = new DefaultServiceInstance(
                "B", "inventory-service", "127.0.0.1", 8082, false);

        var provider = ServiceInstanceListSuppliers.toProvider(
                "inventory-service", a, b
        );
        var loadBalancer =
                new TestedRoundRobinLoadBalancer(provider);

        StepVerifier
                .create(loadBalancer.choose(new DefaultRequest<>()))
                .assertNext(response -> {
                    assertTrue(response.hasServer());
                    assertEquals("A",
                            response.getServer().getInstanceId());
                })
                .verifyComplete();
    }

    @Test
    void emptySupplierProducesNoServer() {
        var provider = ServiceInstanceListSuppliers.toProvider(
                "inventory-service"
        );
        var loadBalancer =
                new TestedRoundRobinLoadBalancer(provider);

        StepVerifier
                .create(loadBalancer.choose(new DefaultRequest<>()))
                .assertNext(response ->
                        assertFalse(response.hasServer()))
                .verifyComplete();
    }
}
~~~

`DefaultRequest` and `StepVerifier` come from their respective test dependencies. Use Spring Boot test or `reactor-test` matching your module's release train. If testing an implementation with a random seed, never assert A is picked first; the snippet above asserts A because the illustrative `RoundRobinPicker` initializes its ticket at 0.

Additional adapter tests to write:

1. Supplier emits an updated list on a second subscription: adapter reads the new list.
2. Supplier emits an empty list: `hasServer() == false`.
3. Supplier returns `Flux.empty()`: also produces no instance.
4. Supplier emits an exception: behavior is well-defined with no fake success response.
5. Supplier inspects `Request` hints/zones: verify the adapter calls `get(request)` without dropping context.
6. Supplier implements `SelectedInstanceCallback`: callback fires exactly once on successful selection and zero times when empty.
7. Two service IDs with two child contexts: verify each algorithm applies strictly to its scope.
8. If custom contracts track per-instance metadata/state, verify callbacks/state never leak across services.

You do not need full HTTP integration inside this unit test. The adapter layer tests only the contract between picker, reactive supplier, and response wrapper.

## 12. Fairness: Define It by **Selections** Before Measuring HTTP

Suppose three replicas A/B/C have equal weights and are always eligible:

- **Round Robin**: after K selections on a fixed list, counts across replicas differ by at most 1.
- **Uniform Random**: each selection has probability `p_i = 1/3`; exact 1/3 splits are not guaranteed in short windows.
- **Weighted Random**: with weights 3:1:1, target probabilities are 60%, 20%, and 20%.
- **Sticky/affinity**: the same session/user pins to one replica; per-session fairness **differs** from per-request fairness.
- **Least-active/concurrency-aware**: prefers instances with fewer in-flight requests; counts may skew intentionally to protect latency.
- **Zone preference**: when requests originate in zone A, global imbalance across zones is intentional.

First, pick the **unit of measurement**:

| Unit | Question | Why it can differ |
|---|---|---|
| LoadBalancer selections | How many times did the picker choose A/B/C? | Closest measure of algorithm fairness |
| HTTP attempts | How many times did HTTP transport actually send? | Retries create extra attempts; connect failures |
| Completed HTTP responses | How many success/error responses returned? | Slower replicas hold more in-flight requests |
| Successful requests/sec | How much throughput did each replica serve? | Differing capacity/CPU/DB/backend queues |
| In-flight requests | How many calls are concurrently active on an instance? | Varying service times |
| Bytes/CPU time | How much resource load did each backend bear? | Differing payloads/costs per request |

**Fairness in selection counts does not guarantee fairness in CPU or latency.** If each request to A takes 5 ms while B takes 500 ms, Round Robin still divides selections equally, yet B accumulates in-flight requests and high p99 latency.

## 13. Probabilistic Fairness of Random

For N independent selections over a fixed list of n instances, uniform random has:

\[
p_i=\frac{1}{n},\qquad E[C_i]=Np_i
\]

and when selections are independent:

\[
\mathrm{Var}(C_i)=Np_i(1-p_i),\quad
\sigma_i=\sqrt{Np_i(1-p_i)}.
\]

For example, 3 instances and 9,000 selections:

\[
E[C_i]=3000,\quad
\sigma_i=\sqrt{9000\times\frac13\times\frac23}
\approx44.72.
\]

Consequently, counts such as `A=2954, B=3022, C=3024` are completely normal. Never write a test expecting "exactly 3,000 hits per instance" for Random, and never conclude an algorithm is broken just because two consecutive calls hit A.

### Non-Flaky Random Testing

Use two layers:

**Deterministic layer:** Inject a fixed-seed RNG, confirming that identical seeds and identically ordered lists reproduce the exact sequence with all indices in `[0, n)`. This catches logic bugs and aids debugging.

**Statistical layer:** Run a large enough sample, count selections, and compare against expectations using a precomputed tolerance. Never pick an arbitrary threshold or test distribution on a 20-request sample.

Example picker with RNG injection:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.IntUnaryOperator;
import org.springframework.cloud.client.ServiceInstance;

public final class RandomPicker {

    private final IntUnaryOperator nextIndex;

    public RandomPicker(IntUnaryOperator nextIndex) {
        this.nextIndex = nextIndex;
    }

    public static RandomPicker production() {
        return new RandomPicker(bound ->
                ThreadLocalRandom.current().nextInt(bound));
    }

    public Optional<ServiceInstance> pick(
            List<ServiceInstance> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return Optional.empty();
        }

        int index = nextIndex.applyAsInt(candidates.size());

        if (index < 0 || index >= candidates.size()) {
            throw new IllegalStateException("RNG index out of bounds");
        }

        return Optional.of(candidates.get(index));
    }
}
~~~

In a unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Random;

@Test
void fixedSeedMakesRandomSelectionReproducible() {
    var instances = Fixtures.threeInstances();

    RandomPicker p1 =
            new RandomPicker(new Random(2026)::nextInt);
    RandomPicker p2 =
            new RandomPicker(new Random(2026)::nextInt);

    for (int i = 0; i < 500; i++) {
        assertEquals(
                p1.pick(instances).orElseThrow().getInstanceId(),
                p2.pick(instances).orElseThrow().getInstanceId()
        );
    }
}
~~~

For the production picker using `ThreadLocalRandom`, distribution tests should be **statistical tests with controlled false-failure rates** or run as non-blocking quality/performance gates rather than flaking every pull request.

### Statistical Thresholds Instead of Arbitrary Numbers

If `\hat p_i = C_i/N` and each selection is an independent Bernoulli trial for instance i, Hoeffding's inequality gives:

\[
P(|\hat p_i-p_i|\ge\varepsilon)
\le 2e^{-2N\varepsilon^2}.
\]

For n instances, a simple union bound bounds the probability that any share exceeds the tolerance:

\[
P(\exists i:|\hat p_i-p_i|\ge\varepsilon)
\le 2n e^{-2N\varepsilon^2}.
\]

For example, with N = 10,000, n = 3, and `\varepsilon = 0.03` (3 percentage points), this upper bound is tiny under **i.i.d. assumptions with fixed p_i**. This provides a principled threshold for **uniform random on a stable snapshot**, though it does not apply directly to sticky sessions, adaptive least-request, or shifting lists.

A failing random test can indicate an RNG bug, biased input, pre-selection filter, or measurement error. Never tweak the algorithm solely because a single small sample looked skewed.

## 14. Weighted Fairness: Target Proportions Differ from Equal Splits

Suppose target weights are:

| Instance | Weight | Target share |
|---|---:|---:|
| A | 3 | 60% |
| B | 1 | 20% |
| C | 1 | 20% |

Ideal probabilities:

\[
p_i=\frac{w_i}{\sum_j w_j},\qquad E_i=Np_i.
\]

If N=10,000, expectations are A=6,000, B=2,000, and C=2,000. A test expecting 3,333 per backend here has the **wrong contract**.

Spring Cloud provides `WeightedServiceInstanceListSupplier` and `WeightFunction` to resolve instance weights; by default it reads the `weight` metadata key per documentation. When writing custom algorithms, decide **whether weights are interpreted by the supplier or by the chooser** to avoid "double weighting."

Two common strategies:

- **Weighted sampling via cumulative table**: sum weights and draw a number in `[0, total)`; linear scanning per selection costs `O(n)`, while binary search over prefix sums gives `O(log n)` if precomputed.
- **Weighted supplier**: transforms candidate lists/ratios at the supplier layer. Round Robin/Random downstream sees the output set; do not infer ratios solely from raw metadata.

### Tests for Invalid Weights

| Input | What to verify |
|---|---|
| All weights > 0 | Target distribution and membership |
| One weight = 0 | Excluded or fallback? Contract must define |
| Negative weight | Reject or handle via safe rule |
| Huge weight | Sum does not overflow; never creates massive replica lists |
| Missing metadata | Default weight per policy, e.g., 1 with built-in supplier |
| Metadata parse failure | Fallback or fail fast with safe logging |
| Weights change at runtime | Consistent snapshot/alias table updates |
| One instance disappears | Adjust total weight and candidate set as new snapshot arrives |

If caching an alias table or prefix sums to save `O(n)` per pick, remember to **invalidate** when instances or weights change. Benchmarks using only fixed lists will miss table-rebuild overhead.

## 15. Measuring Fairness When Discovery, Zones, and Health Change

A very common evaluation mistake: summing selections of A/B/C over an hour and blaming the algorithm for "picking B too rarely" even though B was eligible for only 10 minutes.

With uniform random and candidate set `C_t` at selection t, valid probabilities vary over time:

\[
p_i(t)=
\begin{cases}
1/|C_t| & i\in C_t\\
0 & i\notin C_t
\end{cases}
\]

Expected selections for i:

\[
E_i=\sum_{t=1}^{N}p_i(t).
\]

With weighted random, replace `1/|C_t|` with i's weight divided by the sum of weights of candidates **eligible at time t**. Never divide an hour's selections equally when the instance list changed.

Record:

- `serviceId`, `instanceId`, snapshot version, and timestamp;
- Candidate set **after** zone/hint/health filtering;
- Request context affecting eligibility, while avoiding logging sensitive tenant/user IDs;
- Active weight/affinity rules;
- Retry attempts, no-instance events, and fallback paths;
- Name of the active algorithm/load-balancer policy.

**If the policy is sticky preference**, global per-request fairness is not the sole objective. A tenant generating 80% of traffic may legitimately drive 80% of selections to its pinned instance. Evaluate distribution **by key/session** or keys assigned per replica, while also monitoring traffic hotspots.

## 16. Supplementary Fairness Metrics and Their Limits

You can use these metrics, provided you state the target distribution upfront:

**Absolute share deviation:**

\[
\Delta_i=|\hat p_i-p_i|.
\]

Easy to explain: if target is 20% and observed is 24%, the deviation is **4 percentage points**.

**Relative error:**

\[
R_i=\frac{|\hat p_i-p_i|}{p_i},\quad p_i>0.
\]

Useful when comparing deviation on low-weight replicas against high-weight replicas; never use when target probability is 0.

**Jain's fairness index for equivalent instances:**

\[
J=\frac{(\sum_i c_i)^2}{n\sum_i c_i^2},\quad
\frac1n\le J\le1.
\]

`J=1` when all counts are equal. However, a high Jain index **does not prove** requests hit the right instances, and Jain on raw counts has the **wrong target** for Weighted 3:1:1.

To evaluate target weights, use normalized ratios `r_i=C_i/E_i` for `E_i>0`, then compute Jain over `r_i`. This approaches 1 when observed shares closely match expectations, though it requires large sample sizes and special care for instances with tiny expected counts.

**Chi-square goodness-of-fit**:

\[
\chi^2=\sum_{i=1}^{n}\frac{(O_i-E_i)^2}{E_i}.
\]

Valid only when probabilistic and independence assumptions hold and expected counts meet the test's minimum criteria. Never apply chi-square directly to "prove" deterministic Round Robin or stateful adaptive load balancing.

**Fairness takeaway:** always start with **algorithm contract + measurement unit + observation window + eligible candidate set**. No single fairness number replaces those four inputs.


## 17. Algorithmic Cost: Complexity Models

Cost must be evaluated in terms of **candidate count n**, **request rate Q**, metadata access patterns, and concurrency. Not every "pick one element" algorithm is `O(1)`.

| Strategy / operation | Per-selection cost (model) | State / preparation | Operational risk |
|---|---|---|---|
| Round Robin on existing list | `O(1)` | `O(1)` counter | Atomic contention under very high concurrency |
| Uniform Random on existing list | `O(1)` | `O(1)` | No short-window fairness guarantee |
| Weighted Random scanning cumulative weights each call | `O(n)` | `O(1)` if no table cached | CPU scales linearly with candidates |
| Weighted Random + prefix sum + binary search | `O(log n)` | `O(n)` memory, `O(n)` rebuild | Must rebuild when instances/weights change |
| Weighted Random + alias method | `O(1)` | `O(n)` setup/memory | Expensive rebuilds; hard to cache dynamic data |
| Least-active scanning active request counts | `O(n)` | `O(n)` counters | Stale telemetry/races; CPU-heavy scans |
| Power of two choices | Roughly `O(1)` when inspecting a few candidates | `O(n)` or telemetry-dependent | Approximate least-active; state updates |
| Consistent hashing (sorted ring) | `O(log(vn))` lookup | `O(vn)` ring with v virtual nodes per instance; costly build/sort | Hash skew, memory, rebalancing |
| Filtering zone/hint/health from list | Typically `O(n)` | Depends on supplier/cache | Easily misattributed to chooser cost |
| Copying or sorting list before every pick | `O(n)` or `O(n log n)` | Fresh allocation per request | Negates `O(1)` chooser advantage |

`O(1)` describes **asymptotic complexity in n**, not zero real-world latency or thread-count independence. Even Round Robin with `AtomicLong` can suffer cache-line contention when hundreds of threads hammer the same cursor.

### Example Cost Calculation by Request Volume

If a chooser scans 1,000 candidates per selection at 10,000 calls/sec, it inspects roughly 10 million elements/sec—**before** filtering, allocations, and networking. An `O(1)` chooser eliminates that scan, yet if each HTTP call takes 50 ms across only three instances, the end-to-end impact may be negligible.

More importantly, if a supplier creates `new ArrayList<>(instances)` or re-sorts the list on every selection, benchmarking `picker.pick(...)` alone misses the largest cost. Separate clearly:

\[
T_{\text{selection path}} =
T_{\text{supplier}} +
T_{\text{filter}} +
T_{\text{algorithm}} +
T_{\text{reactive/adaptation}}.
\]

And total HTTP call latency:

\[
T_{\text{end-to-end}} =
T_{\text{queue/pool}} +
T_{\text{selection path}} +
T_{\text{connect/TLS}} +
T_{\text{backend}} +
T_{\text{response}} +
T_{\text{retry/backoff}}.
\]

Stages may overlap depending on pipeline/transport; these equations are a **decomposition model** for measurement and comparison, not an exact formula for every HTTP call.

## 18. Microbenchmarking the Algorithm Properly with JMH

Never wrap selections in a hand-rolled `System.nanoTime()` loop and draw conclusions from a few microseconds: JIT optimizations, dead-code elimination, GC, OS scheduling, and CPU frequency scaling skew results. **JMH** is the right tool for Java microbenchmarks.

Example JMH skeleton using the picker from section 4:

~~~java
package com.example.loadbalancer.benchmark;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import com.example.loadbalancer.RoundRobinPicker;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(2)
@Threads(8)
public class RoundRobinPickerBenchmark {

    @Param({"1", "10", "100", "1000"})
    public int instanceCount;

    private List<ServiceInstance> instances;
    private RoundRobinPicker picker;

    @Setup(Level.Trial)
    public void setup() {
        var list = new ArrayList<ServiceInstance>();

        for (int i = 0; i < instanceCount; i++) {
            list.add(new DefaultServiceInstance(
                    "inst-" + i,
                    "inventory-service",
                    "127.0.0.1",
                    10000 + i,
                    false
            ));
        }

        instances = List.copyOf(list);
        picker = new RoundRobinPicker();
    }

    @Benchmark
    public void pick(Blackhole blackhole) {
        blackhole.consume(
                picker.pick(instances).orElseThrow()
        );
    }
}
~~~

Running this benchmark requires `jmh-core` and `jmh-generator-annprocess` in a dedicated profile/build target. **Never put microbenchmarks in the per-commit unit-test suite**, as results are environment-sensitive and slow down CI. The code above is a benchmark template, not measured results for this module.

### Designing Unbiased Benchmarks

1. **Sufficient warmup** so the JIT compiler can optimize hot paths.
2. **Fork** fresh JVMs to avoid state warmed by prior tests.
3. **Vary parameter n** across 1, 10, 100, 1000 (add 10,000 if production sets grow that large).
4. **Concurrency**: measure single-threaded and 8/32 threads; lock/atomic algorithms behave differently under contention.
5. **Snapshots**: benchmark on immutable lists matching production inputs; never construct lists inside `pick` when isolating the algorithm.
6. **Consume results** via `Blackhole` so the optimizer cannot eliminate the computation.
7. **Track memory allocations**: measure allocations/op, GC rate, and temporary objects if building lookup tables.
8. **Check variance**: inspect multiple forks and distributions, not just a single mean.
9. **Stabilize the environment**: CPU cores, frequency scaling, JVM/GC, JDK, cgroup quotas, memory, and thermal throttling.
10. **Measure tail latency** if p99 selection matters; average time does not substitute for p99.

You can add `Mode.Throughput` and `Mode.SampleTime` benchmarks via dedicated JMH fixtures. For weighted selection, state explicitly whether table preparation is included in the benchmark; under frequent topology churn, rebuild cost can exceed selection cost.

### Avoid Misleading Pre-Initialized Benchmarks

A benchmark measuring only `pick(candidates)` may report stellar `O(1)` latency, while real WebClient calls still traverse Reactor, `ServiceInstanceListSupplier`, health filtering, and the connector. Therefore add a second benchmark for **supplier → reactive choose → response**, plus an end-to-end HTTP test. Never extrapolate microbenchmark gains into proportional total API speedups.

## 19. Benchmarking Cost-Shifting Scenarios

Do not test only `n=3`, equal weights, and zero concurrency. A controlled experiment matrix:

| Control variable | Suggested values | What to observe |
|---|---|---|
| Instance count | 1, 10, 100, 1000 | Scaling with n |
| Threads/subscriptions | 1, 8, 32 | Atomic contention and thread safety |
| Topology churn frequency | Static; every 1s; every 100ms | Rebuild/cache invalidation cost |
| Weight skew | Equal; 10:1 skew; zero/invalid | Weighted picker handling |
| Zone/hint filtering | Unfiltered; filtered down to 1/10 instances | Filter cost and fairness on reduced set |
| Caching | Separate cache hit/miss runs | Discovery/selection overhead |
| Retries | Off; single budgeted retry | Actual `choose` invocations |
| Backend latency | 1ms, 50ms, 500ms | Selection overhead vs. network/backend |
| Response payload | Small and large | Codec/network cost may dwarf picker cost |
| Service ID count | 1 vs. many client contexts | Memory and init overhead of child contexts |

When comparing benchmarks, hold backend count, request rate, concurrency, and retry config constant. If one algorithm has different fallback/affinity behavior than the baseline, it changes the request mix and backend latency; HTTP p99 alone no longer isolates selection overhead.

### Separate Cold Path from Warm Path

Spring Cloud LoadBalancer creates per-service child contexts **lazily** by default. The first call can include context initialization, initial discovery fetch, and connection pool warmup. Never compare that first call against the millionth call of another algorithm.

Measure separately:

- **Cold start / first selection**: time from first request to first selection, potentially including child context init.
- **Warm steady-state**: using stabilized suppliers/caches.
- **Topology update**: changing instances/weights/metadata and measuring update latency and cost.
- **Recovery**: re-adding a replica after health checks; measure lag from update until it receives traffic again.

If eager-load contexts are enabled, comparisons must account for shifting initialization cost to startup rather than pretending it vanished.

## 20. Integration Testing: Two/Three Backends and Real Service IDs

To verify the algorithm through an HTTP client, build a lab:

~~~text
caller :8080
  |
  | GET http://inventory-service/whoami
  v
Spring Cloud LoadBalancer + custom algorithm
  |
  +--- inventory A :8081
  +--- inventory B :8082
  +--- inventory C :8083
~~~

`application.yml` in the caller using `SimpleDiscoveryClient`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083
~~~

In `inventory-service`, have each replica return its listening port:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoami() {
        return Map.of(
                "instance",
                environment.getProperty("server.port", "unknown")
        );
    }
}
~~~

Run the same service on ports 8081–8083 and verify each backend directly before testing routing. The caller exposes `GET /proxy/whoami` using `@LoadBalanced RestClient.Builder`, `@LoadBalanced WebClient.Builder`, or `@FeignClient(name="inventory-service")`. Implement the proxy endpoint separately in the lab.

PowerShell example:

~~~powershell
1..60 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/proxy/whoami"
}
~~~

With custom Round Robin and a **stable** instance set, 60 selections can split evenly 20/20/20. However, if HTTP timeouts/retries, proxy errors, or other requests share `inventory-service`, **60 successful responses do not necessarily equal 60 selections**. To verify the algorithm, instrument at the selection lifecycle and cross-check backend access logs.

### Testing Scope Isolation

Add a `payment-service` client using the default policy. Call it and confirm inventory's custom algorithm is **not** mistakenly applied. This catches `@LoadBalancerClient` configurations accidentally placed inside component scanning and registered globally.

### Testing All Three HTTP Clients

| Client | Service-ID configuration | What to verify |
|---|---|---|
| RestClient | `@LoadBalanced RestClient.Builder` | URI host is `inventory-service`; call reaches a replica |
| WebClient | `@LoadBalanced WebClient.Builder` or Reactor LoadBalancer filter | Mono subscribed; selection by service ID |
| OpenFeign | `@FeignClient(name="inventory-service")` without static URL | Spring Cloud LoadBalancer integrated; method hits right replica |

With WebClient, **never call `block()` on an event-loop thread** to test inside a reactive application. Use `StepVerifier`/`WebTestClient` or framework-managed subscriptions.

## 21. Testing Failures, Health, Zones, Retries, and Circuit Breakers

Picker fairness cannot be measured in isolation from candidate policies. Failure-testing scenarios should distinguish at least:

### 21.1. One Dead Replica

~~~text
A :8081  healthy
B :8082  stopped
C :8083  healthy
~~~

If the supplier still includes B (e.g., static `SimpleDiscoveryClient`), the custom selector **may validly pick B given its input**, causing a connect error. That does not prove the chooser is broken. Test both cases:

1. **Without health filtering:** B stays in candidates, causing connect failures and bounded retries; count selections/attempts.
2. **With health filtering:** once the health supplier marks B unhealthy, candidates omit B; the picker stops selecting B.

With `HealthCheckServiceInstanceListSupplier`, separate update/caching intervals apply; test the transition window rather than expecting instant removal.

### 21.2. Zone/Hint/Affinity

If policy permits only zone HCM, create candidates with HCM/Hanoi zone metadata. Send requests with matching request context/hints and verify **supplier output** first, then **selection output**.

Note that some zone-preference/hint suppliers **fall back to the full list** when zero candidates match the filter; tests must follow **the real contract of the configured supplier**, never assuming every hint is a hard filter.

For sticky sessions, test two properties:

- Same affinity key and stable candidate set: selection adheres to sticky policy.
- Sticky instance disappears or is excluded: policy executes defined fallback/rebalance without picking an absent instance.

### 21.3. Retries and Instance Switching

When a retry-aware supplier is enabled, retried requests can receive a list **preferring to avoid the previous instance**. Never require every retry to switch replicas in all situations: when only one valid instance remains or policy allows re-selection, the same replica may be picked again.

Also test:

- Retries stay bounded during network failures/503s.
- Side-effecting POST/PUT calls retry only when idempotency is guaranteed.
- Overall timeout covers all attempts and backoffs.
- Metrics distinguish logical requests, selections, and HTTP attempts.
- When a circuit breaker is OPEN, requests may be blocked **before** LoadBalancer selects an instance; fairness counts then do not rise with client calls.

### 21.4. Empty Candidate Set

When zero `ServiceInstance` entries exist, the adapter must return `EmptyResponse`/`hasServer=false` and the HTTP client surfaces the corresponding error (often 503 in some integrations). Never fabricate a dummy instance or return null and proceed to the network.


## 22. Observability: Gather the Right Data Before Drawing Conclusions

In production, you cannot set breakpoints on every `choose()`. Observe by **service ID, policy, instance, and outcome** using labels informative enough without exploding metric cardinality.

Spring Cloud LoadBalancer provides `LoadBalancerLifecycle`; when Micrometer statistics support and a `MeterRegistry` are enabled, LoadBalancer meters are registered.

Example configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Requires Spring Boot Actuator and a compatible metrics registry. Exact meter names/tags depend on the Spring Cloud release train. For example, Spring Cloud includes `loadbalancer.requests.active` for active requests; other success/failure meters/counters may be emitted by lifecycle instrumentation.

Events to distinguish:

| Event | What to know | Unit |
|---|---|---|
| Candidate snapshot | Which instances are actually eligible | List per service ID/policy |
| Selection | Which instance the chooser picked | One `choose` turn |
| No-instance | No valid candidate found | One failed selection |
| HTTP attempt | Where transport attempted to send | One attempt |
| HTTP completion | Status or transport error | Response/exception |
| Retry | How many attempts a logical call made | One retry |
| Latency | Cost of supplier, filter, picker, and network | Duration |
| In-flight | How many unfinished requests a backend holds | Gauge |
| Dynamic update | When lists/weights changed | Event/version |

### Do Not Let Metrics Degrade Performance

An ultra-fast custom picker that attaches dynamic tags per user/session/request can flood `MeterRegistry` with millions of series, making instrumentation costlier than the algorithm itself. Use:

- Controlled service IDs.
- Instance IDs or zones only if cardinality is bounded and observability policy permits.
- Bounded algorithm and operation names.
- Bounded outcome values (`selected`, `empty`, `error`) and policy versions.

Avoid raw URIs with SKUs in paths, bearer tokens, user IDs, unbounded tenant IDs, or correlation IDs as **metric labels**. Put correlation/trace IDs in **sampled logs/traces** under data-protection policies, never in histogram tags.

### Correlating Events Across Three Layers

~~~text
Controller:            logical request count
LoadBalancer:          selection count, selected instance
HTTP transport:        attempts, connect failures, timeout
Backend:               received requests, status, latency
~~~

With retries, the controller may record 1 request while LoadBalancer records 2 selections and the backend receives only 1 request (the first attempt failed pre-connect). Dividing backend responses by total caller requests to judge fairness easily leads to false conclusions.

If the application runs multiple **caller replicas**, each replica may hold its own Round Robin state. Cluster-wide totals can diverge over short windows due to different seeds and loads; that does not imply a race bug in the algorithm.

## 23. Separating Chooser Latency from Service Latency

To decide whether a custom algorithm is worth deploying, measure at two layers:

### 23.1. Algorithm Layer

Hold the candidate snapshot fixed and measure:

- Nanoseconds or microseconds per `pick`.
- CPU time and ops/second on single and multiple threads.
- Allocated bytes/op.
- GC frequency/pressure under stress tests.
- Contention on `AtomicLong`, locks, cache lines, or shared mutable maps.
- Impact of n and metadata/weight updates.

For example, Round Robin is `O(1)`, yet `AtomicLong` can become a contention point under extreme concurrency. A thread-local random picker reduces contention at the trade-off of probabilistic rather than deterministic fairness.

### 23.2. End-to-End Layer

Send real HTTP traffic and measure:

- Successful throughput (RPS).
- Error rates: 4xx, 5xx, timeouts, no-instance, connect failures.
- p50/p95/p99 latency per **logical request**.
- p95/p99 latency per **HTTP attempt**.
- Connection counts, pool waits, caller CPU/memory.
- CPU, queue depth, and in-flight counts per backend.
- Backend overload/hotspots when weights or traffic split unevenly.

If JMH shows selection dropping from 1 µs to 100 ns while API p99 remains 180 ms, do not claim the new algorithm makes the service "10x faster" for users. It reduced overhead in one tiny component; system-wide gains must be proven independently.

### 23.3. Reproducible Benchmark Report

| Field | What to record |
|---|---|
| JVM/JDK | Vendor, version, heap, GC |
| CPU and environment | Core count, cgroup quota, OS |
| Spring Cloud version | Release train/Commons/LoadBalancer |
| Candidate set | Instance count, weights, zone/hint mix |
| Algorithm | Version, config, fallback policy |
| Caching | Hit/miss, topology update cadence |
| Load | RPS, concurrency, test duration, warmup |
| Retry/timeout | Enabled or not, max attempts |
| Metrics | Instrumentation overhead enabled/disabled |
| Results | Throughput, latency distributions, CPU, allocations, errors |
| Confidence | Run count, variance, CI/benchmark host |

Never include **fabricated benchmark numbers** in reports. If a measurement was not run, state "not measured" rather than extrapolating from Big-O. Production benchmarks with small n and modest request rates often show that simpler algorithms perform just fine; Big-O is only part of the design decision.

## 24. Setting Pass/Fail Criteria So CI Is Not Flaky

A practical pipeline can organize tests into groups:

| Group | When it runs | Typical gate |
|---|---|---|
| Unit correctness | Every pull request | Never picks invalid instance; no spurious exceptions |
| Property-based correctness | Every PR or nightly | Zero membership/invariant violations; reproducible seeds |
| Concurrency stress | Nightly or dedicated CI | Zero races, deadlocks, or lost updates |
| Deterministic Round Robin fairness | Every PR | `max(count)-min(count)≤1` on stable list |
| Statistical Random fairness | Nightly/dedicated job | Deviation within statistically grounded tolerance |
| Request-aware supplier integration | Every PR | Zone/hint/health/retry policies respected |
| End-to-end multi-replica | Every PR or integration CI | Client calls by service ID; right backend responds |
| JMH microbenchmark | On algorithm changes or nightly | Regression analysis; no hard thresholds on shared machines |
| HTTP load/performance | Pre-release / performance lab | p95/p99 SLOs and error budgets satisfied |
| Fault injection/recovery | Pre-release or periodic | Failover, no-instance, topology updates, bounded retries |

### Examples of Clear Acceptance Criteria

A team might define:

- **Correctness:** 100% of valid generated inputs never select outside the candidate snapshot; no-instance returns the expected response.
- **Stable Round Robin:** 12,000 selections over 3 fixed candidates yield 4,000/4,000/4,000 counts.
- **Weighted Random:** in a large trial, shares stay within a precomputed statistical bound around targets; exact counts per run are not required.
- **Dynamic discovery:** in any snapshot omitting B, zero selections return B; fairness before/after updates is evaluated in separate windows.
- **Performance:** no significant CPU/allocation regression vs. baseline in the same test environment; API p95/p99 stays within operational SLOs.
- **Recovery:** when removing a failing replica, retry/health suppliers and the selector neither loop infinitely nor pick excluded instances.

These are **policy examples**, not fixed Spring Cloud mandates. Adjust for actual traffic, backend heterogeneity, and fairness goals.

### Test Design Mistakes to Avoid

Some anti-patterns:

~~~java
// Wrong for Random: cannot require an exact 50/50 split.
assertEquals(500, countAAfter1000RandomRequests);

// Wrong with multiple callers: RoundRobin cursor is not necessarily shared.
// Wrong with zone filter: 3 registered instances != 3 eligible instances.
// Wrong with retry: 1 business request != 1 load-balancer selection.
~~~

If a statistical test fails intermittently, do not keep bumping thresholds until it turns "green." Inspect distribution assumptions, sample sizes, confidence bounds, and sources of nondeterminism. With seeded randomness, log seeds and sample counts for reproduction.

## 25. Evaluation Framework Before Replacing Default Round Robin

Before writing and deploying a custom algorithm, answer:

**A. What problem needs solving?** For example, unequal instance weights, zone locality, sticky sessions, curbing in-flight overload, partition affinity, or high metadata-scanning costs.

**B. Is the chooser the right layer?** Many zone/health/weight problems are solved by `ServiceInstanceListSupplier` and built-in policies without writing a `ReactorServiceInstanceLoadBalancer`. If `WeightedServiceInstanceListSupplier` is already enabled, do not double-weight inside a custom picker.

**C. What stronger invariant does the new algorithm provide?** For example, stable distribution during scale-out/in, bounded load, capacity-proportional fairness, or lower p99 latency. Without a new invariant, added complexity may not pay off.

**D. What is the cost?** CPU, memory, state lifecycle management, metadata refreshes, race risks, and debugging cost. Measure under real traffic or realistic synthetic workloads.

**E. How do you roll back?** Gate the policy with per-service-ID configuration, keep Round Robin as baseline, monitor metrics/traces, and maintain a fast rollback runbook on overload.

Illustrative decision matrix:

| Requirement | Extension point to evaluate first | Core tests |
|---|---|---|
| Split equally across equivalent instances | Default Round Robin | Balanced counts, low cost |
| Random selection | `RandomLoadBalancer` | Statistical fairness, seeded tests |
| Capacity-based weighting | Weighted supplier/`WeightFunction` | Target weighted shares, weight updates |
| Zone locality | Zone preference supplier | Never misroutes cross-zone when forbidden |
| Request stickiness | Same-instance/session preference or affinity policy | Same-key consistency and fallback on lost replica |
| Health filtering | `HealthCheckServiceInstanceListSupplier` | Unhealthy removal, update lag |
| Retry on another replica | Retry-aware supplier + policy | Avoid-previous when candidates allow |
| Least-active/adaptive | Custom selector + matching telemetry | p99 latency, stale counters, concurrency |
| Consistent hashing | Custom policy with keys and ring | Churn on add/remove, hotspots, memory |

**Never turn a single fairness test into the sole optimization target.** A picker that splits requests evenly yet spikes p99 on a slow backend can be worse than a weighted/adaptive policy despite prettier raw counts.

## 26. Diagnostic Table When Tests Fail

| Symptom | Likely cause | What to check |
|---|---|---|
| Index out of bounds | Cursor used stale size or list mutated concurrently | Snapshot immutability, modulo against current size |
| Request picks filtered-out replica | Skipped `supplier.get(request)` or used raw registry list | Supplier chain, request context, eligibility tests |
| Round Robin unbalanced in unit test | Non-atomic counter or mutating list | Fixed-list tests, shared state, concurrency |
| Round Robin unbalanced at backend | Retries, no-instance, backend timeouts, multiple callers | Separate selections/attempts/completions |
| Random picks A twice in a row | Normal random behavior | Large-sample stats; never assert alternation |
| Weighted distribution wrong | Weight parser, double weighting, stale weight updates | Metadata and transformed candidate set |
| Only one instance ever picked | Health/zone/hint/sticky supplier returned one candidate | Record candidate snapshot at selection time |
| Cost scales linearly with instance count | Per-call sort/copy/weight scan | Benchmark each stage, heap allocations |
| CPU spikes with many threads | Atomic contention or `synchronized` blocks | Thread-scaled JMH, async-profiler |
| Timeouts unchanged despite fast picker | HTTP/backend latency dominates | p99 decomposition and transport metrics |
| Callback never fires | Custom adapter skipped `SelectedInstanceCallback` | Success callback and empty-path tests |
| `Mono` completes empty on empty supplier | Missing `defaultIfEmpty` | Test supplier `Flux.empty()` |
| `No servers available` despite discovery instances | Cache/health/hint supplier excluded all | Final candidate set, no-instance policy |
| Custom policy affects payment | Configuration scanned globally | `@LoadBalancerClient` child context scope |
| Feign still calls direct hostname | `@FeignClient(url=...)` or missing LB integration | Feign config and LoadBalancer starter |
| Regression only post-deploy | Different JDK/JVM, weights/topology, cold contexts | Benchmark metadata and rollout metrics |
| Flaky random test | Small sample, ungrounded threshold | Seeds/independent trials/expected shares |

## 27. Pre-Production Algorithm Testing Checklist

- [ ] Explicit contract for empty lists, single instances, multiple instances, and invalid metadata.
- [ ] Algorithm picks only from snapshots already filtered by policy.
- [ ] Never mutates shared candidate lists or stores request context in mutable singleton fields.
- [ ] Unit tests cover deterministic Round Robin, seeded random, and weight edge cases.
- [ ] Concurrency tests verify atomic state, races, infinite loops, and callbacks.
- [ ] `ServiceInstanceListSupplier.get(request)` is tested with request-specific hints/zones/retries.
- [ ] `EmptyResponse` is tested for both empty lists and non-emitting suppliers.
- [ ] Fairness metrics distinguish raw selections, HTTP attempts, responses, and backend capacity.
- [ ] Fairness target is defined: equal, weighted, sticky, zone, or least-active.
- [ ] Statistical tests use precomputed sample sizes/thresholds/confidence without spurious flakiness.
- [ ] When topology changes, fairness is computed per snapshot/window eligibility.
- [ ] Never assume Round Robin shares one cursor across all caller replicas.
- [ ] Integration tests cover RestClient/WebClient/OpenFeign with real service IDs.
- [ ] `@LoadBalancerClient` scope tests confirm policies never leak to unrelated services.
- [ ] Fault-injection tests cover a dead replica, zero instances, slow discovery, and bounded retries.
- [ ] JMH benchmarks cover n, concurrency, weight/update cadence, allocations, and GC.
- [ ] Cold path, warm path, and supplier/weight-table rebuild costs are measured separately.
- [ ] Observe end-to-end p50/p95/p99 rather than inferring HTTP speedups from microbenchmarks.
- [ ] Metric labels never contain user/session/correlation IDs or unbounded dynamic URIs.
- [ ] Baseline, rollback plan, and canary measurements exist prior to wide rollout.
- [ ] Strict performance benchmarks are not run as flaky tests on shared CI workers.
- [ ] Reports document environment, input sizes, service ID, call counts, measurement method, and error bounds.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `RoundRobinLoadBalancer`, `RandomLoadBalancer`, `ServiceInstanceListSupplier`, custom configurations, weighted/zone/sticky policies, and lifecycle/metrics.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): LoadBalancer cache, health, retry, and statistics properties.
- [Spring Cloud Commons — RoundRobinLoadBalancer source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/RoundRobinLoadBalancer.java): example of `choose(Request)`, `DefaultResponse`/`EmptyResponse`, and `SelectedInstanceCallback`.
- [Spring Cloud Commons — ServiceInstanceListSuppliers](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/support/ServiceInstanceListSuppliers.java): helpers for building static suppliers/providers in unit tests.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycles, and parameterized tests.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, testing reactive pipelines, and publisher behavior.
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): JVM benchmarking with forks, warmup, measurement, and Blackhole.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): metrics, tags, cardinality, and latency analysis.

**Conclusion:** a trustworthy custom Spring Cloud LoadBalancer must **pick validly from real candidates**, **distribute according to policy**, and **keep overhead low at expected load**. Unit/property/concurrency tests prove picker invariants; reactive adapter tests verify the contract with `ServiceInstanceListSupplier`; integration tests over RestClient/WebClient/OpenFeign verify service-ID routing; and benchmarks plus observability show whether the algorithm genuinely improves system performance. Roll out only when all three dimensions—correctness, fairness, and cost—are measured against the same explicit contract.
