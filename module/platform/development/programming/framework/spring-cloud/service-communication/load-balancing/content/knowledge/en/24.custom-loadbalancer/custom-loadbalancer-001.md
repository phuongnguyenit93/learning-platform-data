# Criteria for Choosing Built-in Configuration vs. Writing a Custom Component

In **Spring Cloud LoadBalancer**, the need for "smarter routing" does not automatically mean writing a custom LoadBalancer algorithm from scratch. Many requirements such as **round-robin, random selection, zone preference, weighting, hints, sticky sessions, or health checks** are already available as built-in algorithms or `ServiceInstanceListSupplier` implementations. Only when a **mandatory constraint** cannot be satisfied by these components does writing custom code become the right choice.

This lesson in the **Customizing LoadBalancer** chapter raises a practical question: *when should you only configure properties, when should you compose built-in suppliers, when should you write a candidate-filtering supplier, and when do you genuinely need a custom `ServiceInstance` selection algorithm?*

The goal is not to create as many custom classes as possible, but to choose a solution that **matches the routing contract, is easy to test, is observable, and has a rollback path**. The examples use `order-service` calling `catalog-service` by service ID via `RestClient` or `WebClient`.

## 1. Before Choosing a Solution: Express Requirements as Testable Rules

Compare these two requirements:

> *"When possible, prefer an instance in the same zone to reduce latency."*

and:

> *"Data belonging to region A must never be sent to an instance outside region A, even when no instance remains in region A."*

Both sentences mention geographic locality, yet they have **opposite fallback contracts**:

| Criterion | Soft preference | Hard constraint |
|---|---|---|
| No instance in the same region/zone | Can use an instance from another zone | Must return no candidates or a controlled error |
| Goal | Latency, locality, lower cross-zone cost | Security policy, data partitioning, residency |
| Suitable component | Built-in `ZonePreferenceServiceInstanceListSupplier` | Custom strict/allowlist filter, paired with backend enforcement |
| Is enabling a preset enough? | Usually yes, if the fallback semantics fit | **No** if the preset falls back to the full list |
| Most important test | Prefers correctly when enough instances exist | **Never** selects a prohibited instance when candidates are missing |

**The first step is always specifying the behavior when no valid candidate exists**, and only then choosing properties or writing code.

Example of a clear requirement:

~~~text
serviceId: catalog-service
policy: prefer-same-zone
preferredZone: zone-a
onNoPreferredInstance: fall back to all discovered instances
onNoInstanceAtAll: return no-server error
routingSignal: ServiceInstance.metadata["zone"]
~~~

A strict requirement can be written as:

~~~text
serviceId: payment-service
policy: require-region
allowedRegion: region-a
onNoAllowedInstance: fail closed; do not choose another region
routingSignal: trusted ServiceInstance.metadata["region"]
securityBoundary: backend/authorization must independently enforce region
~~~

LoadBalancer configuration is a **client-side** optimization/routing mechanism; it does not replace access control or data policies **on the server side**.

## 2. Four Levels of Customization, from Least Code to Most Code

You can choose a solution in increasing order of control and maintenance cost:

~~~mermaid
flowchart TD
    A["Clearly state requirements and fallback behavior"]
    B{"Does a preset match the<br/>policy semantics completely?"}
    C["Level 1: properties / built-in configuration"]
    D{"Is composing built-in<br/>suppliers enough?"}
    E["Level 2: configure a supplier chain"]
    F{"Only need to change the<br/>eligible instance set?"}
    G["Level 3: write custom supplier / filter"]
    H["Level 4: write custom ReactorServiceInstanceLoadBalancer"]
    I["Test correctness, failure, latency, rollback"]
    A --> B
    B -->|"Yes"| C --> I
    B -->|"No"| D
    D -->|"Yes"| E --> I
    D -->|"No"| F
    F -->|"Yes"| G --> I
    F -->|"No; need a new selection algorithm"| H --> I
~~~

| Level | What changes? | When to choose? | Main cost |
|---|---|---|---|
| **1. Property/preset** | Select a configuration or policy provided by Spring Cloud | Metadata-based weighting, same-instance, zone, or hint with acceptable fallback | Lowest; requires understanding exact semantics |
| **2. Built-in supplier chain** | Compose discovery, cache, health, zone, hint, and weight in order | Need to combine multiple policies without altering core behavior | Chain ordering, caching, request context |
| **3. Custom supplier** | Filter, sort, or transform the candidate list | Need allowlist/fail-closed behavior or custom filtering criteria | Policy logic, metadata reliability, refresh |
| **4. Custom LoadBalancer algorithm** | Decide how to pick one instance from the candidate set in a new way | Least-connections, multi-factor scoring, complex dynamic-state affinity | Concurrency, performance, state, fairness, fallback, observability |

**Design principle:** prefer the smallest extension point that satisfies the requirement. If you only need to filter out invalid candidates, a new `ServiceInstanceListSupplier` is usually far less complex than replacing the entire `ReactorServiceInstanceLoadBalancer`.

## 3. Built-in Spring Cloud Components to Choose From

Spring Cloud LoadBalancer provides several familiar components; you should separate the **selection algorithm** from the **candidate source and filters**.

| Need | Built-in component | What to verify |
|---|---|---|
| Distribute turns across instances | `RoundRobinLoadBalancer` (common default) | Does not guarantee instances have equal latency or capacity |
| Pick a random instance | `RandomLoadBalancer` | Not weighted or least-loaded |
| Distribute by weight | `WeightedServiceInstanceListSupplier` | `weight` metadata defaults to 1 if omitted |
| Prefer the same zone | `ZonePreferenceServiceInstanceListSupplier` | When no match exists, returns the full list |
| Hint-routing | `HintBasedServiceInstanceListSupplier` | When no hint or no match exists, usually returns the full list |
| Prefer the previously used instance | `SameInstancePreferenceServiceInstanceListSupplier` | It is a preference; not a strict affinity guarantee |
| Sticky by request cookie | `RequestBasedStickySessionServiceInstanceListSupplier` | Support depends on request context/integration; verify WebClient and specific conditions |
| Periodic health checks | `HealthCheckServiceInstanceListSupplier` | When no healthy instance exists, defaults to falling back to the source list |
| Cache the instance list | `CachingServiceInstanceListSupplier` | TTL and discovery client caching can make data stale |
| Receive instances from discovery | `DiscoveryClientServiceInstanceListSupplier` or reactive variant | Only reflects source data subject to discovery intervals/delays |

In addition, some versions include other suppliers/presets such as subsetting, API versioning, or retry awareness. **Do not assume every option exists in every Spring Cloud version.** Check the documentation and configuration metadata for your exact release train.

### What LoadBalancer Does Not Do on Its Own

- Does not open TCP/TLS connections or manage the HTTP connection pool.
- Does not enforce overall business timeouts or enable a circuit breaker.
- Does not guarantee a `POST` request body is replayable on retry.
- Does not enforce security policies on downstream servers.
- Does not turn `weight` or `zone` metadata into real-time load or health measurements.

These concerns may require `RestClient`, `WebClient`, OpenFeign, separate retry/timeout policies, resilience mechanisms, and dedicated authorization.

## 4. Decision Matrix for Whether to Write Custom Code

Before writing a custom class, evaluate the requirement along seven axes:

| Criterion | Favors built-in configuration | Favors a custom component |
|---|---|---|
| **Correct semantics** | Preset has expected fallback and priority order | Must fail-closed, follow ordered fallback, or handle exceptions |
| **Input data** | Zone/hint/weight exist in standardized metadata | Requires dynamic data such as queue depth, EWMA latency, tenant policy |
| **Per-request behavior** | Fixed policy per service ID/zone or supported hint | Must inspect trusted context, tenant, API version, or quota |
| **Determinism** | Round-robin/random/weight meets the requirement | Needs specialized state-based selection or scoring |
| **Operational risk** | Preset fallback failure is acceptable | Misrouting can violate policy or cause cascading outages |
| **Measurability & testability** | Built-in metrics/logs and stable behavior | Needs new observability and unit/property/chaos tests |
| **Long-term cost** | Uses public APIs with minimal upgrade churn | Must maintain custom code and release train compatibility |

A useful rule of thumb: **put "disallowed" conditions ahead of optimization conditions**. If picking the wrong instance could leak data or cause invalid transactions, prioritize correctness and fail-closed behavior over performance.

### Quick Elimination Questions

- Only need to change `timeout` or retry? This is **not** a default reason to write a custom LoadBalancer algorithm.
- Only need standard health filtering? Try the built-in supplier, but understand its fallback when no healthy instances remain.
- Only need to adjust traffic ratios via metadata? Try the weighted supplier.
- Need to strictly avoid a region? Soft zone preference may not be enough; a strict filter is needed.
- Need selection based on continuously updated latency scores and load? You may need both a custom selection algorithm **and a metrics collection pipeline**; writing only an instance selector class is not enough.

## 5. Level 1: Properties and Built-in Configurations

Several preset configurations are provided by Spring Cloud LoadBalancer via `spring.cloud.loadbalancer.configurations`. For example, selecting weighted:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: weighted
~~~

In a metadata-based model, instances can be declared as:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  weight: "5"
              - uri: http://127.0.0.1:8082
                metadata:
                  weight: "1"
~~~

`WeightedServiceInstanceListSupplier` looks up `weight` in metadata by default and assumes a weight of 1 when omitted. Actual traffic distribution also depends on the selection algorithm, request count, concurrency, caching, and other filters. **There is no guarantee of "exactly 5/6 of requests" going to the first instance**.

To try zone preference, in versions that support the preset:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: zone-preference
      zone: zone-a
~~~

If `catalog-service` has instances with metadata `zone=zone-a` and `zone=zone-b`, the supplier prefers the `zone-a` subset when it is non-empty. **When no instance exists in `zone-a`, the supplier returns the entire source set** — that is a soft preference.

Other presets are documented such as `health-check` or `same-instance-preference`. For each preset, check your version and do not combine values into a single-valued property expecting it to automatically compose multiple policies.

### When Should You Stop at Level 1?

Stop at a preset when:

1. Behavior is correct including **missing metadata or no remaining candidates**.
2. No custom trusted per-request signal needs to be read.
3. The policy can be verified purely by testing instance data and sample requests.
4. Metrics/observability are sufficient to inspect distribution, errors, and latencies.
5. Rollback is possible through configuration changes without code changes.

**Do not choose a preset just because the policy name sounds like your requirement.** Read both the fallback condition and how it uses metadata.

## 6. Level 2: Composing a Built-in Supplier Chain per Service ID

If you need discovery + cache + zone/hint, you can declare a **configuration class** containing existing suppliers without writing a new algorithm.

Example applying zone preference only to `catalog-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogZoneLoadBalancerConfiguration.class)
class CatalogLoadBalancerRegistration {
}
~~~

With a **blocking discovery client** using RestClient/RestTemplate:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

// Do not attach @Configuration here if the class is within the main component scan scope.
// It is loaded into the child context via @LoadBalancerClient.
class CatalogZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Chain diagram:

~~~text
DiscoveryClient
    ↓
CachingServiceInstanceListSupplier
    ↓
ZonePreferenceServiceInstanceListSupplier
    ↓
RoundRobinLoadBalancer (selects one candidate)
    ↓
HTTP client calls the selected instance
~~~

**Ordering warning:** the cache should sit **right after the supplier that fetches data over the network**, before per-request or zone-filtering steps. If caching is placed after a request-dependent filter while the cache key only distinguishes by service ID, the client may mistakenly reuse a filtered list for a different request.

With reactive discovery, the builder provides `withDiscoveryClient()` for reactive sources; verify the exact API name against your Spring Cloud version and discovery client. With the health-check supplier, consider omitting the cache wrapper because it has its own replay/retention mechanism.

### Why @LoadBalancerClient Matters

Spring Cloud LoadBalancer creates a **child application context per service ID**. `@LoadBalancerClient` binds dedicated configuration to that service name, avoiding unintended policy changes across all clients in the application.

If a class intended for the child context is accidentally picked up by the main component scan into the parent context as a regular `@Configuration`, a policy bean can be applied **more broadly than intended**. The documentation recommends that classes referenced in `@LoadBalancerClient(configuration=...)` **omit `@Configuration`** or be placed outside the main component scan scope.

For multiple service IDs, you can use `@LoadBalancerClients` and separate configuration classes, rather than an uncontrolled "global" policy.

## 7. Distinguish Soft Fallback from Hard Fallback Before Reusing Suppliers

The following three cases are very easy to misunderstand:

| Built-in supplier | When condition matches | When no match exists | Suitable for |
|---|---|---|---|
| `ZonePreferenceServiceInstanceListSupplier` | Prefers instances in the same zone | Returns the full source list | Reducing cross-zone traffic when possible |
| `HintBasedServiceInstanceListSupplier` | Prefers instances with matching `hint` metadata | Returns the full list if no match | Soft hint-based routing |
| `HealthCheckServiceInstanceListSupplier` | Returns instances with matching health | By default returns source instances when none are healthy | Improving selection in non-fail-closed scenarios |

This means:

- "Prefer same-zone" is different from "forbid cross-zone."
- "Prefer instances marked `hint=canary`" is different from "only canary is allowed to handle requests."
- "Prefer healthy" is different from "if all instances are unhealthy, reject immediately."

If the requirement involves **data residency, tenant isolation, compliance, production/test environment separation**, or never calling a policy-prohibited endpoint, **do not rely on soft fallback**.

### Do Not Turn Hint Headers into an Authorization Mechanism

A hint from `X-SC-LB-Hint` or request context can be influenced by external input if not controlled at ingress. Never use an arbitrary client-supplied header to decide access to data, sensitive namespaces, or allowed regions.

Even when the caller filters properly, the backend must still enforce authorization, ownership, and corresponding residency policies. Client-side routing is not a sole security boundary.

## 8. Level 3: Writing a Custom ServiceInstanceListSupplier When Strict Filtering Is Needed

Suppose a mandatory policy states:

> "`payment-service` may only select instances with metadata `region=region-a`. When no valid replica exists, it must not fail over to another region."

That is **filtering the candidate set**, without needing to change how round-robin selects within the filtered set.

### Strict Custom Supplier Without Automatic Fallback

Java example:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

final class RequiredRegionServiceInstanceListSupplier
        implements ServiceInstanceListSupplier {

    private final ServiceInstanceListSupplier delegate;
    private final String requiredRegion;

    RequiredRegionServiceInstanceListSupplier(
            ServiceInstanceListSupplier delegate,
            String requiredRegion) {
        this.delegate = delegate;
        this.requiredRegion = requiredRegion;
    }

    @Override
    public String getServiceId() {
        return delegate.getServiceId();
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filter);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filter);
    }

    private List<ServiceInstance> filter(
            List<ServiceInstance> instances) {
        return instances.stream()
                .filter(instance ->
                        instance.getMetadata() != null
                        && requiredRegion.equals(
                                instance.getMetadata().get("region")))
                .toList();
    }
}
~~~

This pattern properly implements **fail-closed** semantics: if no instance has matching `region` metadata, the result is an **empty list**. Round-robin has no candidates to pick from; the LoadBalancer/HTTP client integration will report the corresponding "no available instance" error instead of silently switching regions.

### Registering the Custom Supplier in the Child Context

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class PaymentRegionLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier paymentSupplier(
            ConfigurableApplicationContext context) {

        ServiceInstanceListSupplier discoveryAndCache =
                ServiceInstanceListSupplier.builder()
                        .withBlockingDiscoveryClient()
                        .withCaching()
                        .build(context);

        return new RequiredRegionServiceInstanceListSupplier(
                discoveryAndCache,
                "region-a");
    }
}
~~~

The application registers this configuration using `@LoadBalancerClient(name="payment-service", configuration=PaymentRegionLoadBalancerConfiguration.class)` **instead of** the zone example in section 6. Do not declare both configuration classes as competing policies for the same service ID.

**Points to control when moving to production:**

- `"region-a"` is an example value. In practice, read it from controlled configuration and validate at startup.
- Metadata can be missing or incorrect. Under a strict policy, **missing metadata means excluded**—do not guess the region from the hostname.
- Registry data must be trustworthy and sufficiently fresh; do not blindly trust metadata self-advertised by uncontrolled workloads.
- If a request requires a different region per tenant, validate the region at a trusted boundary and pass context into `get(Request)`; do not share a single `requiredRegion` variable across all tenants.
- Do not cache a per-tenant filtered list under a cache key that only contains the service ID.
- The empty case must lead to a **clear error**, without a fallback quietly dropping the condition at another layer.

This is a **pattern illustrating policy structure**; test it against your specific dependencies and Spring Cloud version. Do not treat example code as an audited security policy.

## 9. When Is a Custom Supplier Not Enough?

A supplier operates on the **candidate set**, but does not necessarily control **which single instance is picked** from that set.

Examples:

- "From the valid list, choose the instance with the **fewest active requests**."
- "Select by a score combining p95 latency, error rate, and queue depth."
- "Use rendezvous hashing to guarantee affinity by customer key when the instance list changes."
- "Adjust selection probability based on egress cost and recent performance."

These requirements may call for a **new selection algorithm**, not merely filtering or sorting the list. Even if you sort before round-robin, round-robin will still rotate through the provided set rather than **always picking the first element**.

Custom selection typically extends `ReactorServiceInstanceLoadBalancer` or `ReactiveLoadBalancer<ServiceInstance>` accordingly, keeping the discovery and supplier layers intact where possible.

### Try Built-in RandomLoadBalancer Before Writing an Algorithm

If the goal is simply replacing round-robin with random, Spring Cloud already provides `RandomLoadBalancer`. You can swap the **instance selection** bean per service:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

class RandomCatalogLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

This class is referenced via `@LoadBalancerClient(configuration=RandomCatalogLoadBalancerConfiguration.class)` when applying specifically to `catalog-service`. There is no need to write a new random selector class.

**Do not simultaneously register two competing `ReactorLoadBalancer<ServiceInstance>` beans** in the same child context without explicit configuration; verify which bean is actually used rather than assuming startup success means the right one is active.

### If You Really Must Write a Custom Algorithm

You must define:

1. **Input:** a mutable/changing candidate list, and which `Request` context is trustworthy.
2. **State:** where counters/latency are measured, and how they are shared across threads/client instances.
3. **Selection:** formula, bounds, tie-breaking, random seed, and fairness.
4. **Empty list:** return `EmptyResponse`/no candidate, never select `null`.
5. **Concurrency:** do not block the event loop, do not hold long locks, handle snapshots consistently.
6. **Telemetry failures:** when metrics are stale or missing, how to fall back **without violating hard policies**.
7. **TTL/refresh:** avoid selecting based on instances already removed from discovery.
8. **Observability:** know why an instance was chosen without logging PII or sensitive hints.

A "least latency" algorithm that relies on the last response without smoothing or noise dampening can cause all clients to swarm whichever instance was briefly fastest, overloading it. Custom selection introduces new operational failure modes that require chaos and load testing.

## 10. Scope Policies by Service to Avoid Accidental Global Application

Suppose an application calls several services:

| Service ID | Routing contract | Viable solution |
|---|---|---|
| `catalog-service` | Prefer same zone, but cross-zone is allowed | Built-in zone preference |
| `recommendation-service` | Split load by operations-managed instance weights | Weighted supplier |
| `payment-service` | Must not fail over to another region | Custom strict region supplier |
| `analytics-service` | Controlled experiment with a least-loaded algorithm | Experimental custom selector, feature flag |

**Do not apply `payment-service`'s policy to `catalog-service`** just because both use RestClient.

Spring Cloud LoadBalancer creates a child context per service ID. Use `@LoadBalancerClients` to isolate configurations, or client-scoped properties when supported by your version.

### What Should Be Configured Globally

- HTTP transport timeouts aligned with SLOs.
- Error codes, tracing, correlation, and safe logging.
- Security rules for request context.
- Metrics and testing infrastructure.
- Safe default policy for services without custom configuration.

### What Should Be Defined per Service ID

- Zone/region policy and especially **fallback semantics**.
- Weight source and mandatory metadata requirements.
- Hints, affinity, or API version routing.
- Service-specific rules: canary allowlist, tenant placement, subsetting.
- Enablement and rollback conditions for custom selectors.

If you use `spring.cloud.loadbalancer.configurations` globally, verify its exact scope of application in your current version. When only one service needs different behavior, `@LoadBalancerClient` is usually easier to control.

## 11. Impact of Discovery, Caching, Health Checks, and Retries

A policy can be logically sound yet still pick a broken endpoint if **its input is a stale instance list**.

~~~mermaid
flowchart TD
    A["Service registry / discovery"]
    B["Instance list cache if enabled"]
    C["Health check if needed"]
    D["Zone/region/hint filtering"]
    E["RoundRobin/Random/custom selector"]
    F["HTTP transport execution"]
    G["Timeout / retry policy"]
    A --> B --> C --> D --> E --> F --> G
~~~

Notes:

- `CachingServiceInstanceListSupplier` should be placed immediately after the network-backed instance supplier, before request-dependent filters.
- If a discovery client such as Eureka already caches, adding LoadBalancer caching can cause **double caching**.
- `HealthCheckServiceInstanceListSupplier` has its own replay/caching mechanism; the documentation suggests considering **not stacking `CachingServiceInstanceListSupplier`** with it.
- When all health checks fail, the built-in health-check supplier **may fall back to the full source list**, which is not fail-closed.
- Retries may pick the same or another instance depending on integration/configuration; retries do not prove an instance is healthy or that a request body can be replayed.
- HTTP connect/response timeouts belong to the transport layer; they do not modify the `ServiceInstance` list on their own.

**A strict policy must not be bypassed by a fallback layer downstream.** Inspect the entire path from selection through HTTP execution, including retries, proxies, and any direct calls bypassing LoadBalancer.

## 12. Define Test Criteria Before Deploying Custom Components

Built-in configurations also need tests, but **custom-written components** should have multiple layers of verification:

| Test type | What it must prove | Example |
|---|---|---|
| Supplier/filter unit test | Output candidates match metadata rules | Other regions excluded, missing region excluded |
| Empty/fail-closed test | When no candidate exists, never route to forbidden targets | 0 region-a instances, 2 region-b instances → empty result |
| Algorithm unit test | Never picks outside the list, handles ties/empty | Selection only returns valid candidates |
| Distribution test | Actual ratio under load and concurrency | Weighted 5:1 trends toward the expected split |
| Chain order test | Cache sits in the right place, request context is preserved | Tenant A/B do not mix filtered lists |
| Integration test | `@LoadBalanced RestClient`/WebClient/Feign calls the right instance | Backend `/whoami` returns an explicit ID |
| Fault injection | Instance offline, stale registry, failing health probes | No crash, hard policies remain enforced |
| Soak/performance | CPU, memory, p95/p99, backlog, metrics cardinality | Custom selector overhead stays within budget |
| Rollback test | Can revert to prior policy without backend changes | Feature flag/canary config works |

### Minimum Test Matrix for a Strict-Region Policy

| Source list | Required region | Filtered list | Expected outcome |
|---|---|---|---|
| A1(region-a), A2(region-a), B1(region-b) | region-a | A1, A2 | Only selects A1/A2 |
| B1(region-b), B2(region-b) | region-a | **Empty** | No valid server; never calls B1/B2 |
| A1(region-a), X(missing metadata) | region-a | A1 | X is excluded |
| A1(region-a), A2(region-a) | region-b | **Empty** | Does not select A1/A2 |
| Empty list | region-a | **Empty** | No NPE thrown; no arbitrary selection |
| A1(region-a) but A1 is dead | region-a | A1 | May fail connection; needs separate health/discovery/timeout |

**Specifically:** the final result for case B must be **no request sent to the prohibited backend**. An HTTP 503/no-server response can be the correct behavior. Do not try to "fix 503" by enabling cross-region fallback when policy forbids it.

## 13. Hands-On Lab: Start Built-in, Then Upgrade Deliberately

### Step 1 — Create Two Zones and Observe Selection

Use `SimpleDiscoveryClient` for local testing:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
                  region: region-a
                  weight: "3"
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
                  region: region-b
                  weight: "1"
~~~

Both backends need a `GET /whoami` endpoint returning the instance ID to verify the target. `127.0.0.1` is only valid when the caller and backend share the same host/network namespace; Docker/Kubernetes require different URIs.

### Step 2 — Enable Built-in Zone Preference

Set `spring.cloud.loadbalancer.zone=zone-a` and choose the `zone-preference` preset, or use the configuration builder from section 6.

Measure:

- When a `zone-a` instance exists, the client prefers that instance.
- When only `zone-b` remains in the **updated discovery list**, the built-in supplier can fall back to `zone-b`.
- With static `SimpleDiscoveryClient`, stopping port 8081 **does not automatically remove its URI**. To test an updated list, modify the data/restart in the lab or use a dynamic supplier/registry.

### Step 3 — Upgrade the Requirement to Strict Region

Suppose business requirements change: it must pick `region-a` or return an error. Replace the child context configuration with `RequiredRegionServiceInstanceListSupplier` from section 8.

Verify that:

- No fallback path to `region-b` exists.
- Instances missing `region` metadata are excluded.
- When `region-a` has no candidates left, HTTP clients surface a **no available instance** error instead of silently choosing `region-b`.
- Retries do not fail over to a prohibited instance.

### Step 4 — Measure Overhead and Decide If a Custom Selector Is Needed

If strict filtering is all you need, **do not rush to write least-connections**. Collect metrics:

~~~text
serviceId=catalog-service
policy=strict-region
candidateCountBefore=2
candidateCountAfter=1
selectionOutcome=selected
httpOutcome=200
durationMs=42
~~~

This is an illustrative log format. Do not log token headers, cookies, user IDs, or raw URIs. If better distribution is still needed after filtering, evaluate weighted/random/round-robin before considering a brand-new selector.

## 14. Common Anti-Patterns

**1. Writing an algorithm from scratch just to get "smart load balancing."** If `WeightedServiceInstanceListSupplier` or `ZonePreferenceServiceInstanceListSupplier` already satisfies the need, writing custom code expands the test surface without proportionate value.

**2. Using zone preference as a security boundary.** It falls back to all instances when no zone match exists. A policy prohibiting cross-region routing must fail-closed and be enforced by the backend.

**3. Placing a per-tenant filter before a cache with a single shared key.** The cache can retain a list filtered for tenant A and serve it to tenant B. Only cache shared data; apply request-context filters at the appropriate layer.

**4. Combining `CachingServiceInstanceListSupplier` and `HealthCheckServiceInstanceListSupplier` without understanding their lifecycles.** This can create stale data/double caching, causing dead instances to still be picked.

**5. Sorting the list and assuming round-robin will only pick the first item.** For true min-latency or least-requests behavior, the selection algorithm itself must use scores/counters; sorting alone is usually insufficient.

**6. Selecting instances based on untrusted metadata.** A rogue instance could advertise `region=trusted` or `weight=1000` if the registry does not control metadata. Protect the source of truth and validate on the server.

**7. Performing blocking I/O inside a custom selector's `choose()`.** Querying a dashboard/DB/Redis for scores on every request can turn the LoadBalancer into a bottleneck. Prefer asynchronously updated data snapshots, nonblocking operations on reactive paths, and bounded fallbacks.

**8. Enabling blind retries when a custom policy leaves no candidates.** Under a strict policy, having no candidates is intentional; retries must not switch to a prohibited set or create infinite loops.

**9. Applying child-context configuration globally across the application.** A `@Configuration` placed in the wrong scan package can override beans for many services beyond its intended scope.

**10. Neglecting to test request-context propagation.** If a filter relies on hints/headers/tenant context but the adapter fails to pass `Request` as expected, the policy can misroute or behave inconsistently. Test real integrations with RestClient, WebClient, and Feign.

**11. Forgetting rollback.** If releasing a custom selector raises the error rate, there must be a way to revert to built-in configuration after verifying hard constraints remain intact.

## 15. Performance and Stability Considerations for Custom Solutions

A custom LoadBalancer sits on the critical path of many requests; every change can affect system-wide latency and stability.

### Computational Complexity

- Filtering a list of n instances is typically `O(n)`; with tens of instances this is rarely a major issue, though it should still be measured.
- Scoring n instances on every request can cause heavy allocations, metrics reads, and contention.
- Stateful per-instance algorithms can incur garbage collection pressure and synchronization overhead when membership changes.
- Optimizing for latency while ignoring stability and measurement confidence can cause oscillation and hotspots.

### Data Freshness

- Service registries have heartbeat/refresh intervals.
- LoadBalancer caches have TTLs; discovery clients may have their own caches.
- Health checks only probe periodically and do not guarantee the next request will succeed.
- Per-instance load/latency measurements have lag, bias, and sparse samples during low traffic.

### Tracking Changes

Monitor before and after by **service ID and policy version**:

| Metric | Meaning |
|---|---|
| Selected instance / candidate count | Whether the policy is filtering too aggressively |
| No-instance count | Whether fail-closed or missing instances occur frequently |
| Cross-zone traffic | Whether soft locality is effective |
| HTTP error/timeout rate | Whether errors truly improved or merely shifted |
| Retry attempts | Whether retries are amplifying load |
| p50/p95/p99 latency | End-to-end impact |
| Caller CPU/memory | Overhead of custom selection |
| Per-instance concurrency | Whether hotspot/fairness issues exist |
| Cache refresh/age | Whether routing data is stale |
| Policy rejected count | How many requests strict rules are blocking |

Do not log sensitive data to "explain the algorithm"; use policy codes and enum-style reasons such as `NO_ALLOWED_REGION`, `EMPTY_DISCOVERY`, or `UNHEALTHY_CANDIDATES`.

## 16. When to Upgrade from One Level to Another

| Observed situation | First choice | When to upgrade |
|---|---|---|
| Round-robin for multiple instances with equal capacity | Keep default | Only when metrics show uneven or unsuitable distribution |
| Simple 80/20 split or canary traffic | Weighted supplier/metadata | When per-request rules or complex priorities are needed |
| Prefer locality to reduce latency | Zone preference | When soft fallback violates the contract |
| Only select instances with a mandatory label | Custom strict filter supplier | When filtering alone still requires a custom selector |
| Route by trusted tenant | Request-aware supplier if sufficient | When complex stateful hashing/affinity is needed |
| Route by latency/active requests | Measure first, try built-in weights from normalized data | When dynamic selection with tests/metrics is required |
| No healthy instances | Review health-check and no-instance semantics | When fail-closed is needed instead of default fall-back-to-all |
| Backends have high timeouts | Tune timeouts, pool, retries, circuit breaker | Do not replace selector if the bottleneck is in transport |
| Stale registry | Check refresh/cache/discovery | Do not write a new selector just to mask stale source data |

The existence of an "advanced" requirement does not by itself justify custom code. Demand **evidence that built-in options are insufficient** and define the exact tests the custom code must pass.

## 17. Decision Checklist and Acceptance Criteria

Before writing or approving a custom component, ensure you can answer:

1. Is the **goal** optimizing latency/cost or enforcing a safety constraint that must never be violated?
2. Have you specified exact behavior when **no suitable instance exists**?
3. What percentage of the requirement do `weighted`, `zone-preference`, `health-check`, `same-instance-preference`, or hint presets cover?
4. Can `ServiceInstanceListSupplier.builder()` compose built-in components instead of writing new ones?
5. If not, is the problem **filtering the candidate set** or **picking an instance from the candidate set**?
6. Where does metadata such as zone, region, weight, or tenant hint come from, and is it **trustworthy**?
7. Does the policy depend on each request? If so, is request context propagated properly, and can caches leak across callers?
8. Is there a plan for fail-closed handling, empty responses, retries, timeouts, and circuit breakers?
9. Do unit/integration/chaos/load tests prove correctness, fairness, and performance?
10. Is the impact scoped to a single service ID/child context rather than the whole application?
11. Are there dashboards and non-sensitive log events to explain selections, rejections, and errors?
12. Can you roll back or disable custom behavior on regression without violating hard constraints?

**Conclusion:** In Spring Cloud LoadBalancer, follow the progression **properties/presets → compose built-in suppliers → custom filtering supplier → custom instance selection algorithm**, escalating only when requirements truly demand it. The most important distinction is not "custom code vs. no code," but rather the **contract when no candidates exist**, trustworthiness of input data, service ID boundaries, testability, and long-term operational cost. The least customized option that remains **policy-compliant, safe, and measurable** is usually the most sustainable choice.

**Official References:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons – LoadBalancer Client Configuration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#passing-your-own-spring-cloud-loadbalancer-configuration)
