# Policy When No Replicas Exist in the Preferred Zone

In a microservices system deployed across multiple **zones** (availability zones or infrastructure groups), a client generally wants to call replicas close to it first. Calling within the same zone can reduce network latency, inter-zone traffic, and data transfer costs. However, when the preferred zone has no eligible replicas left, the system must decide whether to **fall back to another zone** or **stop routing (fail closed)**.

Spring Cloud LoadBalancer supports zone preference through `ZonePreferenceServiceInstanceListSupplier`. The key point is that **this is a soft preference policy**: if no `ServiceInstance` in the same zone is found, the supplier by default **returns the entire list provided by the underlying supplier**. It does not reject requests by default simply because the preferred zone has no instances, nor does it maintain a priority order across multiple backup zones.

This lesson analyzes this rule, edge cases, and how to choose a policy suited to your system's availability, latency, cost, and data boundary requirements.

## 1. Context: Client Has a Preferred Zone, Server Has Zone Metadata

Suppose `order-service` runs in `zone-a` and calls `catalog-service`. The instance list provided by discovery consists of:

| Instance ID | Address | Metadata `zone` |
|---|---|---|
| `catalog-a1` | `10.1.1.11:8080` | `zone-a` |
| `catalog-a2` | `10.1.1.12:8080` | `zone-a` |
| `catalog-b1` | `10.2.1.21:8080` | `zone-b` |
| `catalog-c1` | `10.3.1.31:8080` | `zone-c` |

The client can declare its preferred zone with:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

`ZonePreferenceServiceInstanceListSupplier` reads the client's zone value and compares it against the **`zone`** metadata key of each `ServiceInstance`. When two same-zone instances remain, the candidate list usually contains only `catalog-a1` and `catalog-a2`; an algorithm such as round-robin then picks an instance from this list.

~~~mermaid
flowchart TD
    A["order-service in zone-a"]
    B["ServiceInstanceListSupplier<br/>catalog-service has 4 instances"]
    C{"Any zone-a<br/>instances?"}
    D["Prioritize list<br/>catalog-a1, catalog-a2"]
    E["Fall back to delegate list<br/>all instances still provided"]
    F["LoadBalancer selects one instance"]
    A --> B
    B --> C
    C -->|"Yes"| D
    C -->|"No"| E
    D --> F
    E --> F
~~~

The client's zone is the configuration criterion for the preference mechanism; the server's zone is a metadata attribute. Both must match semantically for filtering to achieve its goal.

## 2. Default Behavior When No Instance Exists in the Preferred Zone

`ZonePreferenceServiceInstanceListSupplier` receives the list from the underlying supplier (delegate), then logically processes it as follows:

1. Determine the zone configured for the LoadBalancer client.
2. Filter instances whose `zone` metadata matches the client's zone.
3. **If the matching list is non-empty**, return the matching list.
4. **If the client zone is not set or the matching list is empty**, return the entire list provided by the delegate.

This can be expressed in plain Java to understand the algorithm:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.client.ServiceInstance;

// Illustrates candidate selection logic; does not replace the framework's supplier bean.
static List<ServiceInstance> preferZone(
        List<ServiceInstance> candidates, String preferredZone) {

    if (preferredZone == null) {
        return candidates;
    }

    List<ServiceInstance> sameZone = candidates.stream()
            .filter(instance -> {
                Map<String, String> metadata = instance.getMetadata();
                String zone = metadata == null ? null : metadata.get("zone");
                return zone != null && preferredZone.equalsIgnoreCase(zone);
            })
            .toList();

    return sameZone.isEmpty() ? candidates : sameZone;
}
~~~

This is **candidate list filtering** logic, not the HTTP sending operation yet. After receiving the result, a `ReactorLoadBalancer` or corresponding selector picks a `ServiceInstance` for the HTTP client to connect to.

### Typical Cases

| Client Zone | List from Delegate | List After ZonePreference | Meaning |
|---|---|---|---|
| `zone-a` | A1, A2, B1 | A1, A2 | Same-zone exists: keep only A1, A2 |
| `zone-a` | B1, C1 | B1, C1 | No same-zone: fall back to entire list |
| `zone-a` | B1 without `zone` metadata | B1 | No match, but delegate has an instance: still falls back |
| Client zone not configured | A1, B1, C1 | A1, B1, C1 | No zone filtering |
| `zone-a` | Empty list | Empty list | No target to select; fallback cannot create instances |

**Fallback does not guarantee a request will succeed.** It only widens the candidate set when same-zone instances are missing. Instances in other zones may still be unreachable or fail to satisfy application requirements.

## 3. When the Preferred Zone Disappears: What Changes?

Suppose `catalog-service` initially has:

~~~text
zone-a: catalog-a1, catalog-a2
zone-b: catalog-b1
zone-c: catalog-c1
~~~

During normal operation, a client in `zone-a` chooses only between A1 and A2. If A1 and A2 are deregistered and the underlying supplier has updated the list to B1 and C1:

~~~text
Before incident:
  delegate = [A1, A2, B1, C1]
  same zone = [A1, A2]
  LoadBalancer picks A1 or A2

After discovery updates:
  delegate = [B1, C1]
  same zone = []
  fallback = [B1, C1]
  LoadBalancer picks B1 or C1
~~~

This is **candidate-list fallback**, not a sequence of "try A1, then automatically switch to B1 on HTTP timeout." The policy only sees the instances still provided by the supplier and their metadata.

If the registry/cache still keeps A1 and A2 in the list even though both processes are dead, the zone filter still sees same-zone instances and **does not yet switch to B1/C1**. To handle incidents well, registration, cache TTLs, and health checks must reflect instance status.

## 4. Limitations of the Default Fallback

Several misconceptions can cause a routing policy to fall short of operational requirements.

### No Backup Zone Priority Order

When no instances remain in `zone-a`, by default B1 and C1 are returned together. `ZonePreferenceServiceInstanceListSupplier` does not automatically know that `zone-b` is closer than `zone-c` or that `zone-b` should be preferred before `zone-c`.

If you want an ordering like `zone-a → zone-b → zone-c`, you need a custom filtering policy/supplier aware of zone ordering or another explicitly configured routing solution.

### No Automatic HTTP Health Checks

Being present in the discovery list does not prove an instance can actually handle requests. Zone filtering does not imply health checks were run. The system may need health status from the service registry or `HealthCheckServiceInstanceListSupplier`, depending on how services are discovered.

### No Automatic Retry When a Request Fails

Switching zones in the candidate list differs from **retrying a failed HTTP request**. Once B1 is selected and the connection fails, whether C1 is tried next depends on the retry policy, RestClient/WebClient/OpenFeign integration, and specific configuration. Enabling zone preference does not automatically ensure retries.

### No Data Isolation or Access Control Guarantees

Soft fallback can send requests to another zone. If the application has legal, data-residency, tenant-isolation, or regional access restrictions, do not treat zone preference as a protective boundary. Controls must be enforced at the appropriate infrastructure, service, and data layers.

## 5. Configuring Zone Preference in Spring Cloud

There are two common ways to set it up: using a built-in configuration or configuring a supplier for a specific service. Both rely on the server's `zone` metadata and the desired zone on the client.

### Option 1: Enable the Built-in Configuration

With Spring Cloud LoadBalancer supporting the `zone-preference` configuration, you can enable it via properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      configurations: zone-preference
~~~

The `zone-preference` value selects the appropriate supplier configuration with zone preference. When multiple services have different requirements, consider configuring the LoadBalancer per service ID rather than applying one global policy that may not fit all.

The application needs a Spring Cloud LoadBalancer dependency compatible with the Spring Boot/Spring Cloud release train in use, along with a `ServiceInstance` source (a discovery client or static configuration).

### Option 2: Declare a Supplier for a Specific Service ID

The example below builds the **discovery → cache → zone preference** chain for `catalog-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogZoneSupplierConfiguration.class
)
class CatalogRoutingConfiguration {}

// Do not annotate with @Configuration if this class is within the main
// application context's component scan; it is loaded into the service's child context.
class CatalogZoneSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

When using Option 2, there is no need to also set `spring.cloud.loadbalancer.configurations: zone-preference` if you already created a dedicated chain for `catalog-service`. Check the configuration style matching your library version and ensure the dedicated configuration class is not unintentionally component-scanned as a shared bean.

Spring Cloud documentation also recommends placing the cache directly after the network-fetching instance supplier and before filtering steps, so policy-dependent results are not cached in the wrong place. If the discovery client already maintains its own cache, consider disabling the extra cache layer.

### Preparing Zone Data with SimpleDiscoveryClient

In small experiments, you can declare instances using static configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      configurations: zone-preference
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8083
                metadata:
                  zone: zone-b
~~~

The configuration above is a **standalone example**: the client has preferred zone `zone-a`, two endpoints belong to that zone, and one endpoint is in `zone-b`. In real deployments, use host/port addresses reachable by the client on its network; `127.0.0.1` is only suitable when test servers share localhost with the client.

With Eureka, some zone settings can be integrated from discovery information. With other discovery sources, explicitly setting `spring.cloud.loadbalancer.zone` helps avoid situations where the client zone is undetermined and the entire list is treated as unfiltered.

## 6. Designing Policies When No Same-Zone Replicas Exist

Not every system should use the default fallback. Choose a policy based on each service's goals.

| Policy | When Preferred Zone Has No Instances | Suitable When | Trade-offs |
|---|---|---|---|
| **Soft preference (default)** | Return all instances supplied by delegate | Service can run cross-zone; availability prioritized | Higher inter-zone latency/cost; no control over zone order |
| **Strict by zone** | Return empty list or actively reject calls | Must route strictly within allowed zone | Easy to lose availability when that zone has no instances |
| **Ordered fallback** | Try zones in a designed priority order | Nearest-first, DR zone, or specific cost requirements | Must build and verify policy correctness |
| **Allow a zone set** | Select only from approved zones; if empty, reject or fall back within set | Regional limits exist while redundancy is still needed | Must keep metadata and valid zone list synchronized |

An important rule is defining "no replicas" based on **which filtering step's output list** is evaluated. If a health check has removed failed instances, the same-zone list may be empty even though the registry still holds records in that zone. If no health check exists, a dead instance lingering in cache can prevent fallback from happening.

### Strict Policy Must Be Explicitly Implemented

If a system requires calling only instances in `zone-a`, you cannot just use the default `ZonePreferenceServiceInstanceListSupplier` and expect it to return an empty list when there is no match.

Consider a function illustrating strict filtering logic:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.client.ServiceInstance;

static List<ServiceInstance> strictZoneCandidates(
        List<ServiceInstance> candidates, String requiredZone) {

    if (requiredZone == null || requiredZone.isBlank()) {
        return List.of(); // Required zone unknown: refuse selection.
    }

    return candidates.stream()
            .filter(instance -> {
                Map<String, String> metadata = instance.getMetadata();
                String zone = metadata == null ? null : metadata.get("zone");
                return zone != null && requiredZone.equalsIgnoreCase(zone);
            })
            .toList();
}
~~~

This is core logic that can be used inside a custom `ServiceInstanceListSupplier`; **the standalone function does not register the policy with Spring Cloud LoadBalancer**. When the resulting list is empty, the target selection layer has no instance to send the request to. The status code or exception surfaced to the caller depends on the HTTP adapter and error configuration.

For regionally sensitive data, strict routing must still be combined with access controls, network policies, and storage partitioning; it does not replace access control.

### Ordered Fallback Policy

Example of a system defining zone order `zone-a → zone-b → zone-c`:

~~~text
If zone-a has candidates: select within zone-a.
If zone-a is empty:       try zone-b.
If zone-b is also empty:  try zone-c.
If all are empty:         return no candidates.
~~~

This behavior requires a custom supplier/policy. When implementing it, clearly define how missing `zone` metadata is handled, how unhealthy instances are excluded, and the difference between **fallback when the list is empty** versus **retrying in another zone after an HTTP failure**.

## 7. Combining Zone Preference with Discovery, Health Checks, and Caching

Fallback behavior is directly affected by the list provided by underlying suppliers. The component chain can be envisioned as:

~~~mermaid
flowchart TD
    A["Discovery<br/>currently known instances"]
    B["Cache if configured"]
    C["Health filtering if configured"]
    D["ZonePreferenceServiceInstanceListSupplier"]
    E["RoundRobin / selection algorithm"]
    F["RestClient / WebClient / OpenFeign"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
~~~

This is a conceptual model of **data flowing into zone preference**, not a fixed bean-ordering recipe applicable to every version and every type of health check. `HealthCheckServiceInstanceListSupplier` has its own result-retention mechanism; Spring Cloud recommends carefully checking the order and whether adding a cache is needed to avoid two unnecessary cache layers.

### Scenario A: Same-Zone Instances Disappear from the Registry

`zone-a` is no longer in the returned list. The zone preference supplier receives the list from other zones, so fallback happens as soon as the fresh data reaches this layer.

### Scenario B: Same-Zone Instance Dies but Registry Has Not Removed It

`catalog-a1` still has `zone=zone-a` metadata. The filter still prioritizes A1, even though requests may hit `connection refused` or timeouts. You need to fix registry/cache freshness or health filtering; changing only the round-robin algorithm will not solve this.

### Scenario C: No Instances Remain in the Entire Service

The delegate returns an empty list. Zone preference also returns empty. LoadBalancer-integrated HTTP clients typically report no available server via their own mechanism, such as an error response or exception; there is no valid fallback option.

## 8. Zone Fallback Differs from Retry, Timeout, and Circuit Breaker

A request can succeed at the selection stage yet fail during HTTP execution. Therefore, distinguish:

- **Zone fallback:** adjusts the candidate list before the LoadBalancer picks an instance.
- **Retry:** re-attempts a call after an error under configured conditions; may re-select an instance depending on the integration and retry policy.
- **Timeout:** limits connection or response wait time at the HTTP client.
- **Circuit breaker:** restricts continuing calls to a path/request group exhibiting high error rates according to configuration.

For example, when `catalog-a1` is still in the registry but dead, zone preference can still select A1. If retry is enabled with instance re-selection, the subsequent attempt can try A2. However, retry does not automatically switch to `zone-b` while the supplier still prioritizes `zone-a` instances.

If you need automatic "nearest zone fails → switch to backup zone," you must design error detection, refreshing/removing bad candidates, and retry/failover as a controlled workflow. For requests with side effects such as payments, idempotency must be handled to avoid duplicate business execution.

## 9. Risks of Cross-Zone Fallback

Allowing zone switching increases service continuity but can introduce operational impacts:

| Risk | Manifestation | Mitigation |
|---|---|---|
| Inter-zone latency | p95/p99 latency increases when all requests move to another zone | Monitor latency by source/target zone; set sensible timeouts |
| Network cost | Egress/inter-zone traffic rises | Measure cross-zone request count and transferred bytes |
| Backup zone overload | Surviving zone receives sudden traffic spikes | Capacity planning, autoscaling, traffic limits |
| Cross-zone connectivity errors | Firewall, DNS, TLS, or routing not yet supported | Test actual paths from clients to backup zones |
| Broken data constraints | Requests reach a zone not permitted to process them | Enforce zone allowlists, data controls, and permissions outside the LoadBalancer |
| Frequent zone flapping | Discovery/health lists fluctuate rapidly | Appropriate health/caching, stability monitoring, and consider hysteresis |

A fallback that succeeds at the connection level does not necessarily meet SLO targets or business constraints. Therefore, treat the "calling cross-zone" state as a signal that needs observability.

## 10. Observing and Troubleshooting When No Same-Zone Instance Is Found

To pinpoint the root cause, look at the **pre-filter list**, **post-filter list**, **client zone**, and **selected instance**:

| Symptom | What to Check |
|---|---|
| Client always calls cross-zone despite `zone-a` having instances | `spring.cloud.loadbalancer.zone`, instance `zone` metadata, whether the zone supplier is actually enabled |
| Preferred zone has no instances left yet no fallback happens | Cache/discovery still holds a same-zone instance; whether another filter altered the list |
| Falls back to `zone-c` even though `zone-b` is closer | Default has no priority ordering of `zone-b` before `zone-c` |
| No server found at all | Whether delegate returned empty or all instances were removed by another supplier |
| Fallback occurs yet requests still time out | Network path to other zone, HTTP client timeouts, backend resources |
| Sudden spike in inter-zone traffic | Preferred zone may have lost instances, metadata is wrong, or client zone is unconfigured |

Example of two custom log lines:

~~~text
serviceId=catalog-service preferredZone=zone-a
delegateCandidates=2 sameZoneCandidates=0 crossZoneFallback=true
selectedInstance=catalog-b1 selectedZone=zone-b
httpStatus=200 durationMs=82
~~~

This is an example of a desired log format; Spring Cloud does not necessarily emit these exact field names automatically. Integrate Micrometer/Tracing, correlation-ID logging, or suitable observability to connect instance selection decisions with HTTP outcomes.

Distinguish `sameZoneCandidates=0` due to **truly no remaining instances** from `sameZoneCandidates=0` due to **missing or incorrect `zone` metadata**. Both causes trigger the same default fallback, yet their fixes are different.

## 11. Lab Exercise to Test Fallback Policy

You can create a local experiment with three instances of `catalog-service`:

1. Run server A1 on port `8081`, A2 on `8082`, and B1 on `8083`; each server returns its instance ID at `GET /whoami`.
2. Configure `SimpleDiscoveryClient` so A1/A2 have metadata `zone=zone-a` and B1 has `zone=zone-b`.
3. Set `spring.cloud.loadbalancer.zone=zone-a` and enable `zone-preference`.
4. Send multiple requests using LoadBalancer-integrated `RestClient`, `WebClient`, or OpenFeign. While all endpoints are running, observe traffic being routed between A1 and A2.
5. Change the configured list for the next run so only B1 remains, or deregister A1/A2 via a dynamic registry. Once the data updates, verify fallback to B1.
6. Try removing the client's zone property: the candidate list will no longer be restricted to the same zone.
7. Try configuring an empty instance list: verify the client reports no available target.
8. If you want to test a strict policy, use a custom supplier that returns an empty list when `zone-a` has no match, then compare the results.

When using `SimpleDiscoveryClient`, editing the configuration file usually requires restarting the application or using an appropriate refresh mechanism; do not assume modifying `application.yml` while the process is running updates the list immediately.

### Evaluation Criteria

| Situation | Expected Result with Default ZonePreference |
|---|---|
| A1, A2 in `zone-a` and B1 in `zone-b` | Selects A1 or A2 |
| Only B1 remains in `zone-b` | Can select B1 via fallback |
| A1 is in discovery but A1 is dead | May still select A1 until the source list changes or is filtered |
| Client zone not set | Selects from all instances provided by delegate |
| Source list is empty | No instance to select |
| Only B1, C1 in two backup zones | Both B1 and C1 are candidates; B1 is not prioritized by default |

## 12. Principles to Remember

- **Default zone preference is a soft preference:** when no same-zone instances exist, it returns the full list provided by the delegate.
- **Fallback does not create instances:** if the source list is empty, the result remains empty.
- **Fallback is not equivalent to HTTP retry:** failed requests after instance selection need separate handling mechanisms.
- **Availability depends on discovery/health freshness:** a dead instance still listed in the same zone can prevent fallback from triggering.
- **No default backup zone ordering:** achieving `zone-a → zone-b → zone-c` requires configuring or implementing a custom policy.
- **Sensitive data/tenants need hard boundaries:** do not use soft zone preference as an authorization tool or data-residency guarantee.
- **Fallback needs observability:** track source/destination zones, fallback counts, error rates, latency, and network cost.

In Spring Cloud LoadBalancer, `ZonePreferenceServiceInstanceListSupplier` only changes the **candidate list** seen by the instance selection algorithm. When the preferred zone is empty, the default behavior helps the system retain a chance to call replicas in other zones; strict policies, backup ordering, retries, and HTTP quality observability must be explicitly designed according to each service's requirements.

**Reference:** [Spring Cloud Commons – Zone-Based Load-Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#zone-based-load-balancing).
