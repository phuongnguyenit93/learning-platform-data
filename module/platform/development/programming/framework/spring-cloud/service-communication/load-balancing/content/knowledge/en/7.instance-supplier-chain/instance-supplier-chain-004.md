# How Decorator Order Affects the Output List

Spring Cloud LoadBalancer does not have to take the raw instance list straight from a service registry and pick randomly or with Round Robin. Before selecting a target, the framework can pass the list through multiple **ServiceInstanceListSupplier** layers: fetching instances from discovery, caching, health checking, preferring a zone, applying hints, handling sticky sessions, or avoiding a recently failed instance on retry. These additional layers are commonly called **decorators**.

A decorator takes another supplier as its **delegate**, reads the list returned by that delegate, and produces an output list according to its rules. Therefore, **decorator order can change the instance set, element ordering, refresh timing, and even whether request context continues propagating to inner layers**.

This lesson examines the difference between **builder declaration order**, **execution layer order**, and **list transformation order**. The goal is to design the right instance supplier chain for Spring Cloud LoadBalancer when using RestClient, WebClient, or OpenFeign—especially when combining caching, health checks, and request-based routing.

## 1. ServiceInstanceListSupplier and the Decorator Model

LoadBalancer needs a list of **ServiceInstance** objects for a service ID. Instances may come from `DiscoveryClient`, `ReactiveDiscoveryClient`, or a custom source. `ServiceInstanceListSupplier` supplies this input to the target-selection algorithm.

The two key methods on the interface are:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Points to remember:

- Each emission of the `Flux` is **one list of instances**. Each `ServiceInstance` is not emitted as an individual `Flux` item.
- The `Request`-accepting method lets a decorator act on hints, sticky sessions, retries, or other contextual metadata.
- A decorator can filter elements, reorder them, apply weights, alter emission frequency, or return cached results.
- **RoundRobinLoadBalancer** or **RandomLoadBalancer** picks from the final list; the selection algorithm itself cannot restore instances already removed by an earlier decorator.

Example chain:

~~~mermaid
flowchart LR
    A["Discovery supplier"] --> B["Caching decorator"]
    B --> C["ZonePreference decorator"]
    C --> D["HintBased decorator"]
    D --> E["RoundRobin LoadBalancer"]
~~~

Each arrow represents list data flowing from an inner delegate out to an outer decorator. With the configuration above, one selection pass reads as: **discovery → cache → zone preference → hint filter → instance selection algorithm**.

## 2. Builder Order and Processing Order Read Differently in Code

Spring Cloud provides a builder to assemble a chain:

~~~java
ServiceInstanceListSupplier supplier =
        ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
~~~

Builder calls are written from the source outward toward outer decorators. Once constructed, the delegate relationship tree looks like:

~~~text
HintBasedServiceInstanceListSupplier
  └── ZonePreferenceServiceInstanceListSupplier
        └── CachingServiceInstanceListSupplier
              └── DiscoveryClientServiceInstanceListSupplier
~~~

From LoadBalancer's perspective, calling the outermost supplier flows inward along **Hint → Zone → Cache → Discovery** to retrieve data. As the data flows back out, transformations happen in the order **Discovery → Cache → Zone → Hint**.

This is a common source of confusion: the code places **withZonePreference()** before **withHints()**, yet Hint is the outermost decorator and **operates on the list already processed by Zone**.

We can model this with functions:

- **D()**: returns the list from discovery.
- **C(L)**: uses a cache to serve list L.
- **Z(L)**: prefers instances belonging to the configured zone.
- **H(L, r)**: filters by the hint in request r or the default hint.

The chain above corresponds to:

\[
L_{\text{final}}(r) = H(Z(C(D())),r)
\]

Swapping the two decorators to:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withHints()
        .withZonePreference()
        .build(context);
~~~

yields:

\[
L_{\text{final}}(r) = Z(H(C(D()),r))
\]

You must not assume these two expressions are equivalent. They only yield the same output under specific data conditions.

## 3. Decorator Types and Their Effects on the List

| Supplier type | Primary effect | Request-dependent? | Ordering notes |
| --- | --- | --- | --- |
| DiscoveryClientServiceInstanceListSupplier | Fetches list from blocking discovery | Usually no | Source at the start of the chain |
| CachingServiceInstanceListSupplier | Caches list by service ID | Should not depend on Request | Place right after discovery source |
| HealthCheckServiceInstanceListSupplier | Maintains list of instances passing health checks | Should not depend on Request | Place right after discovery source, usually instead of plain caching |
| ZonePreferenceServiceInstanceListSupplier | Prefers instances in the same zone | Usually uses zone configuration | Falls back when no same-zone instances exist |
| HintBasedServiceInstanceListSupplier | Filters by hint metadata | Can read hint from Request | Place outside cache/health to preserve request context |
| SameInstancePreferenceServiceInstanceListSupplier | Prefers previously selected instance | Depends on prior selection/context | Affects candidate ordering or preference |
| RequestBasedStickySessionServiceInstanceListSupplier | Prefers instance ID in cookie | Yes | Only works when adapter forwards sufficient request context |
| RetryAwareServiceInstanceListSupplier | Avoids previously tried instance on retry, if alternatives exist | Yes | Must see retry context; cannot invent additional instances |
| WeightedServiceInstanceListSupplier | Adjusts selection weight distribution | Usually metadata/weight function | Can affect distribution after other filters run |

This table describes each class's purpose, not a guarantee that every decorator strictly returns a subset. For example, a weighted supplier changes instance representation/distribution rather than simply filtering instances out.

**General rule:** decorators responsible for **fetching and stabilizing the list from the source** belong close to discovery; decorators responsible for **request-based filtering or preference** belong on the outside, close to LoadBalancer.

## 4. Why Can Two Filters Fail to Commute?

If both filters purely computed set intersection, order would not change the final set. However, many Spring Cloud decorators have a **fallback** mechanism: when no matching instance is found, they return the entire input list rather than an empty list.

In Spring Cloud LoadBalancer:

- **ZonePreferenceServiceInstanceListSupplier** prefers instances whose `zone` metadata matches the client's zone. If no same-zone instance exists or no zone is configured, it returns the delegate's list.
- **HintBasedServiceInstanceListSupplier** filters instances whose `hint` metadata matches the request/configured hint. If no matching hint exists, it returns the delegate's list.

This fallback condition is precisely why the order of Zone and Hint can change the outcome.

### 4.1. Input Data

Suppose the registry provides exactly two instances:

| Instance | Zone | Hint | Health |
| --- | --- | --- | --- |
| A | zone-a | red | UP |
| B | zone-b | blue | UP |

The request asks for hint **blue**, while the client is configured to prefer **zone-a**.

Initial discovery list:

~~~text
D = [A(zone-a,red), B(zone-b,blue)]
~~~

### 4.2. Case 1: Zone First, Hint Second

Builder:

~~~java
.withDiscoveryClient()
.withCaching()
.withZonePreference()
.withHints()
~~~

Step-by-step transformation:

| Step | Processor | List |
| --- | --- | --- |
| 0 | Discovery | [A, B] |
| 1 | Cache | [A, B] |
| 2 | ZonePreference(zone-a) | [A] |
| 3 | HintBased(blue) | No blue in [A], falls back to [A] |
| **Final** | LoadBalancer receives | **[A]** |

The `blue` hint can no longer find B because Zone already removed B from the list passed to Hint. Hint's fallback policy can only fall back to **[A]**; it cannot recover B from the registry.

### 4.3. Case 2: Hint First, Zone Second

Builder:

~~~java
.withDiscoveryClient()
.withCaching()
.withHints()
.withZonePreference()
~~~

Step-by-step transformation:

| Step | Processor | List |
| --- | --- | --- |
| 0 | Discovery | [A, B] |
| 1 | Cache | [A, B] |
| 2 | HintBased(blue) | [B] |
| 3 | ZonePreference(zone-a) | No zone-a in [B], falls back to [B] |
| **Final** | LoadBalancer receives | **[B]** |

The result is **B**, completely opposite to Case 1. Both choices are valid according to decorator fallback behavior, yet they express two **different business/operational priorities**:

- Zone first then Hint: **zone takes priority**; hint is only selected within the remaining zone.
- Hint first then Zone: **hint takes priority**; zone is only selected within the hint-matched group.

~~~mermaid
flowchart TD
    S["Source [A(zone-a,red), B(zone-b,blue)]"]
    S --> Z["Zone(zone-a) => [A]"]
    Z --> H1["Hint(blue) no match => fallback [A]"]
    S --> H2["Hint(blue) => [B]"]
    H2 --> Z2["Zone(zone-a) no match => fallback [B]"]
    H1 --> A["Result A"]
    Z2 --> B["Result B"]
~~~

The example above assumes the list and metadata do not change during evaluation. In real environments, cache/health and discovery may update asynchronously, so compare chains against the same snapshot.

## 5. HealthCheck and ZonePreference Ordering Can Be Even Riskier

**HealthCheckServiceInstanceListSupplier** periodically checks instances and normally returns healthy ones. According to Spring Cloud LoadBalancer 5.0.4 documentation, when no instance passes health checks, the supplier can fall back to the **entire list of instances received from its delegate**. Consequently, a filter placed before health checking alters both the health-check scope and the fallback list.

Suppose:

| Instance | Zone | Actual status |
| --- | --- | --- |
| A | zone-a | DOWN |
| B | zone-b | UP |

The client prefers `zone-a`. In this example, assume the health-check cycle has fully updated:

**Recommended order: Health → Zone**

~~~text
Discovery:       [A, B]
HealthCheck:     [B]          // only B is healthy
ZonePreference:  [B]          // no zone-a, fallback [B]
Result:          [B]
~~~

**Risky order: Zone → Health**

~~~text
Discovery:       [A, B]
ZonePreference:  [A]          // A is in zone-a
HealthCheck:     [A]          // A is DOWN, none healthy;
                               // falls back to input [A] under this policy
Result:          [A]
~~~

The wrong order can cause LoadBalancer to **prefer an instance that is DOWN** because the health supplier was fed a list already narrowed down to same-zone instances. This illustrates how delegate-list fallback can violate operational expectations if decorators are ordered carelessly.

**Version note:** older Spring Cloud releases or documentation may describe different behavior when zero healthy instances remain. Before deploying safety rules to production, check your exact version and test the scenario where every instance in the list is unhealthy.

In the recommended setup, HealthCheck sits **immediately after discovery, before any other filters** so it observes the full baseline list.

## 6. Cache Must Sit Close to the Discovery Source

A sound ordering with caching is:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Diagram:

~~~text
Discovery → Caching → ZonePreference → HintBased → LoadBalancer
~~~

**Why?** `CachingServiceInstanceListSupplier` is designed to cache the instance list by **service ID**. It does not use hint headers, per-user cookies, or retry attempts as cache keys.

With this ordering, the same discovery list can be shared across many requests while each request still applies hints, zones, or other filters on the outside:

| Request | Shared cached list | Post-cache filter |
| --- | --- | --- |
| Hint=blue | [A, B, C] | Select instances with hint=blue from [A, B, C] |
| Hint=red | [A, B, C] | Select instances with hint=red from [A, B, C] |
| No hint | [A, B, C] | Use default hint or return input list |

The cache shares the **underlying data source**, not the filtering decision of a specific request.

### 6.1. Placing Cache After a Request-Based Filter

A questionable configuration:

~~~java
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHints()
        .withCaching()
        .withZonePreference()
        .build(context);
~~~

The decorator hierarchy becomes:

~~~text
ZonePreference
  └── Caching
        └── HintBased
              └── Discovery
~~~

When the cache sits outside Hint, the cache's fetch path invokes **delegate.get()** and caches by service ID. It is not designed to forward each user's individual `Request` down into Hint. As a result, the inner Hint supplier **may not receive the request header**, falling back to the default hint or no filtering while the resulting list is cached and reused across requests.

Do not mechanically assume "the first blue request makes every subsequent request blue forever" for the current cache implementation: exact behavior depends on how `delegate.get()` handles default hints and how other layers are customized. What is certain is that **caching must not sit outside a filter whose output depends on Request**; doing so can drop request context and cache an output unsuitable for other requests.

With a custom cache decorator, if it caches the list **after per-request filtering** using only the service ID as the key, the risk is even clearer: later requests can receive a list filtered for an earlier request. Distinguish this bug from Spring Cloud's built-in cache behavior.

### 6.2. Caching Cannot Fix Stale Discovery Data

Even a properly placed cache introduces update lag. If an instance deregisters, the cached list can retain that instance until the TTL expires. This is a property of stale data (**stale discovery**), not a filter ordering bug.

Common configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Current Spring Cloud LoadBalancer defaults to caching with a 35-second TTL and capacity of 256. If `DiscoveryClient` already caches (for example, Eureka), consider disabling LoadBalancer's cache to avoid double caching that prolongs propagation delay.

## 7. HealthCheck Is a Dynamic State Source, Not Just a Synchronous Filter

`HealthCheckServiceInstanceListSupplier` has a periodic check schedule and retains the latest results via a Reactor `Flux` replay mechanism. Thus, it is not merely a pure synchronous filter over a `List` per HTTP request.

Factors affecting its output:

1. **Delegate source:** which instances are fed into health probing.
2. **Latest probe cycle:** health may have changed since the previous poll.
3. **Zero-healthy-instances policy:** may fall back depending on version behavior.
4. **Emission pattern:** the supplier may emit intermediate lists during probing rather than always waiting for every instance to finish.
5. **Source refresh:** when discovery changes, refetching may be needed if the delegate does not push updates continuously.

Current documentation mentions:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 25s
        refetch-instances: true
        refetch-instances-interval: 25s
        update-results-list: false
~~~

This is an **illustrative configuration**, not a mandatory set of values. When `update-results-list=false`, the health supplier aggregates the alive list before emitting to avoid publishing multiple intermediate states within one cycle; verify against your exact version.

Spring Cloud recommends placing **HealthCheckServiceInstanceListSupplier immediately after discovery**. Do not automatically wrap `CachingServiceInstanceListSupplier` around it: the health supplier already replays results, and two caching/retention layers can make refresh behavior harder to reason about.

Example configuration for reactive discovery:

~~~java
class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

For blocking discovery, the builder provides **withBlockingDiscoveryClient()** and **withBlockingHealthChecks()**. Do not mix reactive and blocking arbitrarily without considering the HTTP client/provider in use.

LoadBalancer-level health checks are typically useful with `SimpleDiscoveryClient` or sources that do not report health. With a registry that already tracks health reliably, re-probing every instance from each client may be redundant and add unnecessary load.

## 8. Request-Based Filters Must See the Right Request

Not every decorator only reads a `List`. Several require **Request** to compute their result:

- Hints can be passed via the `X-SC-LB-Hint` header or default hint configuration.
- Request-based sticky sessions can read a cookie containing an instance ID.
- Retry-aware suppliers can read the instance selected in the prior attempt.
- A custom decorator can read tenant, API version, or traffic classification data.

In Spring Cloud Commons, decorators extending `DelegatingServiceInstanceListSupplier` typically have two call paths: **get()** and **get(Request)**. If an outer layer calls `delegate.get()` instead of `delegate.get(request)`, context can be lost before reaching inner layers.

Since Spring Cloud LoadBalancer 4.1.0, the property:

~~~yaml
spring:
  cloud:
    loadbalancer:
      call-get-with-request-on-delegates: true
~~~

was introduced to support forwarding `Request` to delegates for applicable layers, and defaults to `true` in current versions. There are **exceptions** for `CachingServiceInstanceListSupplier` and `HealthCheckServiceInstanceListSupplier`. That is why these two belong close to the discovery source, **before** request-dependent filters.

When writing a custom decorator, do not override only `get()` and accidentally drop `Request`. Determine:

1. Does this decorator need `Request`?
2. Does it call `delegate.get()` or `delegate.get(request)`?
3. Does it retain/pin the list across multiple requests?
4. If no request context is present, does it return the original list, apply a default, or fail?
5. Across different HTTP adapters, does `Request` carry all the fields it needs to read?

Correct ordering only helps when **Request is actually populated by the HTTP client**. For instance, if an adapter does not forward the hint header to the `HintBased` supplier in your version, reordering decorators alone will not fix the missing header.

## 9. Sticky Sessions, Retries, and Priority Order

### 9.1. Sticky Sessions

**RequestBasedStickySessionServiceInstanceListSupplier** attempts to prefer the instance ID specified in a request cookie. When combined with zone or hints, the sticky decorator's position decides **which list it applies preference over**.

Example:

~~~text
Discovery: [A, B, C]
Zone:     [A, B]
Hint:     [B]
Sticky:   prefers instance pointed to by cookie, if still in [B]
~~~

With the chain **Discovery → Cache → Zone → Hint → Sticky**, sticky cannot pick A if Hint already narrowed the list to B. If sticky needs higher priority than hint/zone, reconsider decorator order and **fallback contracts** rather than just toggling a flag.

Request-based sticky sessions should not replace proper session storage or distributed state. If the instance named in the cookie dies, requests must still be able to route to another instance.

### 9.2. Retry-Aware

**RetryAwareServiceInstanceListSupplier** can exclude the most recently selected instance from the retry candidate list when alternatives exist. The goal is to avoid immediately retrying the same replica that just failed.

~~~text
After Zone and Hint: [B, C]
Previous call:       B
Retry-aware:         [C]      // if policy to avoid B applies
LoadBalancer:        selects C
~~~

If earlier filters left only B, retry-aware cannot conjure C. Fallback behavior when no alternative remains depends on the current implementation/policy; never promise that every retry switches instances.

In some configurations, Spring Cloud automatically wraps the supplier with `RetryAwareServiceInstanceListSupplier` when retry is enabled. Inspect both **the application-configured supplier chain** and **wrappers added by auto-configuration** to know the actual runtime order.

Retry only concerns **re-selecting an instance**; it does not make side-effecting `POST`/`PATCH` calls idempotent. For order creation, payments, or inventory updates, idempotency keys and bounded retry/timeout settings are still required.

## 10. Example Builders with Explicit Priorities

### 10.1. Caching Before Filters

When you want to cache the discovery list, prefer zone first, and then prefer hint:

~~~java
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

Meaning of the output: prefer **same-zone** instances from the cached discovery list; then choose **hint** within the remaining list.

If hint should take precedence over zone, swap the last two calls:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withHints()
        .withZonePreference()
        .build(context);
~~~

Meaning of the output: prefer instances **by hint** first; zone only filters within the remaining set, falling back according to `ZonePreference` rules.

### 10.2. HealthCheck Instead of Cache

When using the health-check scheduler:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Place HealthCheck right after Discovery; generally **do not combine with withCaching()** because the health supplier already replays results. If using blocking HTTP/discovery, choose the corresponding blocking builder methods.

### 10.3. Binding Configuration to the Right Service ID

A supplier configuration can be applied exclusively to `inventory-service`:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

`InventoryLoadBalancerConfiguration` in the example is not annotated with `@Configuration`. Spring Cloud recommends that configuration classes passed to `@LoadBalancerClient` **not be picked up by component scanning as global configuration**: either omit `@Configuration` or place them outside the scan scope. If scanned globally, a supplier meant for one service can unintentionally affect other services.

### 10.4. Configuring Zone, Hint, and Cache

Example `application.yml`:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      hint:
        default: blue
      cache:
        enabled: true
        ttl: 35s
~~~

**ZonePreference** compares the client's zone against the instance's `zone` metadata key. **HintBased** compares the hint against the instance's `hint` metadata key. If YAML defines these properties while the registry lacks matching metadata, the filter can fall back to the delegate's list.

With the `HintBased` supplier, the default request header **X-SC-LB-Hint** can override the configured hint when the HTTP adapter forwards that context. Verify actual behavior for your HTTP client, release train, and header propagation setup.

## 11. Distinguishing Instance Membership, Element Order, and Emission Timing

Saying "the output list changed" does not only mean more or fewer instances:

| Type of change | Example | Consequence |
| --- | --- | --- |
| Membership | [A, B, C] becomes [B] | Only B remains a candidate |
| Element order | [A, B] becomes [B, A] | Can change selection under index-sensitive algorithms/policies |
| Weight/representation | A has weight 3, B has weight 1 | Effective selection frequency differs |
| Data freshness | Cache holds [A, B] even though B stopped | Requests sent to a failed instance |
| Request context | Hint `blue` not passed into supplier | Traffic group not filtered properly |
| Emission timing | Health publisher emits multiple snapshots | Different requests may observe different lists |

**WeightedServiceInstanceListSupplier** uses `weight` metadata or a `WeightFunction` to adjust instance selection distribution. Therefore, proper evaluation must look at **selection frequency across many requests**, not merely the count of unique instances in the list.

With a custom sorting decorator, element order can directly impact index-based selection algorithms. Still, do not judge Round Robin distribution from a single list snapshot: current counter position, concurrent requests, caching, and instance state all play a role.

## 12. Pure Java Practice: Proving Two Filters Do Not Commute

You do not need to boot Eureka or WebClient to understand the principle. The Java 17+ example below models the **fallback rules** of `ZonePreference` and `HintBased` with two functions:

~~~java
import java.util.List;

public class DecoratorOrderDemo {

    record Instance(String id, String zone, String hint) {
    }

    static List<Instance> preferZone(
            List<Instance> input, String preferredZone) {
        List<Instance> matching = input.stream()
                .filter(i -> preferredZone.equals(i.zone()))
                .toList();
        return matching.isEmpty() ? input : matching;
    }

    static List<Instance> preferHint(
            List<Instance> input, String requestedHint) {
        List<Instance> matching = input.stream()
                .filter(i -> requestedHint.equals(i.hint()))
                .toList();
        return matching.isEmpty() ? input : matching;
    }

    public static void main(String[] args) {
        List<Instance> discovered = List.of(
                new Instance("A", "zone-a", "red"),
                new Instance("B", "zone-b", "blue"));

        List<Instance> zoneThenHint =
                preferHint(preferZone(discovered, "zone-a"), "blue");

        List<Instance> hintThenZone =
                preferZone(preferHint(discovered, "blue"), "zone-a");

        System.out.println("Zone -> Hint: " +
                zoneThenHint.stream().map(Instance::id).toList());
        System.out.println("Hint -> Zone: " +
                hintThenZone.stream().map(Instance::id).toList());
    }
}
~~~

Expected output:

~~~text
Zone -> Hint: [A]
Hint -> Zone: [B]
~~~

This is an **intentional simulation**, not code calling the two Spring Cloud classes directly. Its advantage is isolating **list transformation order** from cache timing, health-check schedules, registry access, and HTTP client state.

After understanding this example, test the real supplier chain inside a Spring application.

## 13. Testing a Real Supplier Chain

### 13.1. Preparing Fixed Test Data

Prepare three or four `ServiceInstance` entries with explicit metadata:

| Instance | zone | hint | Simulated health status |
| --- | --- | --- | --- |
| A | zone-a | red | UP |
| B | zone-b | blue | UP |
| C | zone-a | blue | DOWN |
| D | zone-b | red | UP |

You can use a stub supplier in unit tests returning `Flux.just(List.of(A, B, C, D))`. For health checks, use a mock endpoint or HTTP client to control probe results rather than relying on live instances changing unpredictably.

### 13.2. Test Scenario Matrix

| Scenario | Action | What to verify |
| --- | --- | --- |
| Zone before Hint | Set `zone-a`, request hint `blue` | Lists after Zone and after Hint follow exact order |
| Hint before Zone | Swap the two decorators | Final list may differ |
| No matching zone | Pick nonexistent zone | `ZonePreference` falls back to delegate list |
| No matching hint | Send nonexistent hint | `HintBased` falls back to delegate list |
| Cache before Hint | Send two requests with different hints | Both share discovery cache yet filter by their own hint |
| Cache outside Hint | Temporarily misconfigure in test | Check whether `Request` reaches Hint and if list gets pinned |
| Health before Zone | A DOWN, B UP | Only healthy instances enter Zone once probes stabilize |
| Zone before Health | Swap the two decorators | Observe fallback result and compare with current version |
| Retry-aware | Retry after instance B fails | If alternatives exist, verify B is avoided |
| Discovery update | Add or remove an instance | Verify cache TTL / health refresh takes effect as expected |

### 13.3. Do Not Judge Health from a Single Read

`HealthCheckServiceInstanceListSupplier` uses a scheduler and publisher; a single subscription may catch an unstabilized state or an intermediate snapshot. During tests, wait proactively for the expected test condition, configure `update-results-list` if needed, and timestamp each snapshot.

**`Flux<List<ServiceInstance>>` can emit multiple lists over time**. Do not call `collectList()` on a continuous stream expecting it to complete on its own. For unit tests over a controlled snapshot, `next()` or `take(1)` with an appropriate timeout works; for health tests, wait for a snapshot satisfying the expected condition.

## 14. Observability and Diagnostics

When an HTTP request lands on the wrong instance, inspect the supplier chain layer by layer:

~~~text
Discovery:
  [A, B, C, D]
Cache / Health:
  [A, B, D]
Zone:
  [A]
Hint:
  [A]   (fallback: no blue left after Zone filtered)
LoadBalancer:
  picks A
~~~

Useful logging details:

- Service ID and request/trace ID.
- Decorator names and their order in the chain.
- Instance ID lists **before and after** each decorator.
- Zone, hint, previous-instance ID, and relevant request context fields.
- Timestamps of discovery/cache/health snapshots.
- Final instance selected by Round Robin or Random.

Do not log access tokens, credentials, or full cookies. If using sticky sessions, log only the relevant instance ID rather than sensitive session values.

### Diagnostic Table

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Request with hint `blue` still hits `red` instance | Hint sits below cache or adapter didn't forward `Request` | Inspect `get(Request)`, wrapper order, and header-derived hint |
| Cross-zone instance picked despite zone config | Earlier filter removed all same-zone instances; fallback triggered | Compare inputs and outputs of `ZonePreference` |
| DOWN instance appears in output | Health hasn't refreshed, fallback when none healthy, or Health misplaced | Check probe schedule and Health's delegate list |
| Changing filter order changes target | Two fallback-capable filters do not commute | Replay fixed dataset step by step |
| List stays unchanged after changing hint | Cache holds filtered list or request context lost | Check Cache position and `get(Request)` |
| Registry removed instance yet supplier still returns it | Cache TTL or discovery registry hasn't refreshed | Check cache TTL and heartbeat/deregistration |
| Retry keeps picking failed instance | No other candidates after filtering, or retry-aware lacks context | Inspect list right before retry-aware |
| Sticky session picks unexpected instance | Cookie ID no longer in post-filter list | Check instance ID and Sticky/Zone/Hint order |

If the list is already wrong coming from discovery, changing decorator order cannot fix registry data. If the discovery list is right but the output is wrong, inspect cache, health, zone, hint, and request context in turn before altering the target-selection algorithm.

## 15. Safe Chain Design Principles

1. **Have one clear instance source**: `DiscoveryClientServiceInstanceListSupplier` or a custom source.
2. **Place cache or health check close to the source**: never place request-dependent filters underneath them. Per Spring Cloud guidance, typically pick one rather than stacking both without reason.
3. **Define business priority order**: zone or hint first? Can sticky session override hint? Document this as a contract.
4. **Read fallback rules carefully**: a filter may return its input when nothing matches; "filter" does not always mean a strict constraint.
5. **Preserve Request context**: decorators needing hints/cookies/retry info must see the right request. Check `call-get-with-request-on-delegates` and adapter behavior.
6. **Do not confuse availability with filter placement**: health updates take time; being UP at selection time does not guarantee connections will succeed.
7. **Review auto-configured wrappers**: Spring Cloud may automatically wrap suppliers with retry-aware or other layers based on properties.
8. **Verify with a small data table**: trace the same snapshot through both orderings to spot differences.
9. **Measure final outputs and real errors**: track selected instances, 503s, timeouts, retry counts, and requests dropped for lacking instances.
10. **Document versions and defaults**: fallback behavior, health publisher emissions, and `Request` propagation can vary across release trains.

## 16. Conclusion

In Spring Cloud LoadBalancer, decorator order is **not a code formatting detail**. It determines which list each filter sees, whether caching strips request context, whether health checks probe the full source or only a subset, and whether fallbacks reintroduce instances that an earlier filter tried to exclude.

Start from the rule **Discovery → Cache or Health → policy filters → Request-based filters → instance selection**, then adjust business filter order intentionally and test with datasets containing non-matching cases. In particular, **Zone then Hint** can differ from **Hint then Zone** due to fallback mechanics—a concrete example of why the decorator chain does not commute.

## 17. References

- [Spring Cloud LoadBalancer - Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): builder, caching, zone preference, hints, health checks, and decorator ordering notes.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): service discovery, retry, and client-side load balancing abstractions.
- [Spring Cloud Commons Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): cache, health-check, and `call-get-with-request-on-delegates` properties.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): construction and composition order of decorators.
- [CachingServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/CachingServiceInstanceListSupplier.java): per-service ID caching behavior and delegate access.
- [ZonePreferenceServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ZonePreferenceServiceInstanceListSupplier.java): zone preference and fallback rules.
- [HintBasedServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/HintBasedServiceInstanceListSupplier.java): filtering by hint metadata and request.
