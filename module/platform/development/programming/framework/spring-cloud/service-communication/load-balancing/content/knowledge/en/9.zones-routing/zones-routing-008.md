# Same-Instance Preference and Caller State Scope

In Spring Cloud LoadBalancer, a **caller** may send thousands of HTTP requests to the same service ID such as `inventory-service`. With Round Robin, each target selection typically moves to the next replica in the list; with Random, the selector picks a replica randomly. Sometimes, however, we want the caller to **prefer the replica selected on the previous turn** instead of rotating across every turn.

Spring Cloud supports this mechanism through `SameInstancePreferenceServiceInstanceListSupplier`. The key word here is **preference**: the supplier prioritizes the previously selected instance **if that instance is still within the eligible candidate set**, not a guarantee that every user or every request will always go to the same machine.

The most important point of this lesson is **state scope**. The most recent selection is kept in a LoadBalancer supplier object on the caller side, usually belonging to the dedicated context of the **target service ID** and a single **caller application process**. It is not a user session, is not automatically synchronized across caller replicas, and is not persisted across application restarts.

## 1. Problem: The Caller Wants to Prefer a Familiar Instance

Suppose a system has:

- `checkout-service`: service calling APIs during checkout processing.
- `inventory-service`: stock-checking service, running three replicas A, B, and C.
- `payment-service`: payment collection service, running two replicas D and E.

The caller uses logical addresses:

~~~text
http://inventory-service/api/stock/SKU-42
http://payment-service/api/authorize
~~~

Discovery provides the `ServiceInstance` list for each service ID. When Same-instance preference is disabled, the default algorithm is usually Round Robin, cycling through replicas on consecutive requests. When previous-instance preference is enabled **only for inventory**, calls to inventory tend to stay on the most recently selected replica, provided that replica still appears in the input list.

~~~mermaid
flowchart LR
    U["checkout-service<br/>caller instance 1"] --> L["Spring Cloud LoadBalancer<br/>service ID: inventory-service"]
    D["Discovery / supplier<br/>A, B, C"] --> L
    L --> P["SameInstancePreference<br/>remembers latest instance"]
    P --> A["Inventory A"]
    P -.-> B["Inventory B"]
    P -.-> C["Inventory C"]
~~~

The diagram simply shows three possible choices; **each selection** yields one instance used as the target. Goals that might make this mechanism useful include increasing the likelihood of reusing warmed data in a backend's local cache, reducing constant backend switching, or replicating the behavior of systems that used ZooKeeper's `StickyRule` policy.

However, repeatedly preferring the same backend can cause **heavily skewed** load distribution. If one caller is continuously active and the old backend remains in the list, many requests from that caller may all hit one replica. That is an intentional consequence, not a Round Robin bug.

## 2. How Does the Supplier Implement Preference?

`SameInstancePreferenceServiceInstanceListSupplier` is a **ServiceInstanceListSupplier decorator**, not an algorithm replacing `RoundRobinLoadBalancer` or `RandomLoadBalancer`. It takes an instance list from another supplier, then adjusts the list passed to the selector.

A simplified lifecycle:

1. The caller sends its first request to service ID `inventory-service`.
2. The supplier does not remember any instance yet, so it returns the candidate list such as `[A, B, C]`.
3. The LoadBalancer chooses one instance, say B.
4. The selection callback mechanism (`SelectedInstanceCallback` interface) notifies the supplier that B was selected.
5. On the next request, if B still belongs to the current list, the preference supplier prioritizes B; the selection result typically continues to be B.
6. If B is no longer provided, the supplier returns the remaining candidates for the LoadBalancer to re-select; the newly chosen instance becomes the preferred choice for subsequent turns.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant L as LoadBalancer
    participant P as SameInstancePreference supplier
    participant D as Discovery supplier
    participant B as inventory B

    C->>L: Request 1: inventory-service
    L->>P: Get candidate list
    P->>D: get instances
    D-->>P: [A, B, C]
    P-->>L: [A, B, C] (no history yet)
    L-->>P: selectedServiceInstance(B)
    L-->>C: Select B
    C->>B: HTTP request

    C->>L: Request 2: inventory-service
    L->>P: Get candidate list
    P->>D: get instances
    D-->>P: [A, B, C]
    P-->>L: Prioritize B
    L-->>C: Select B
    C->>B: HTTP request
~~~

The diagram shows the conceptual flow, not synchronous callback methods in identical order across every transport. The core point: **the supplier is updated from the instance selection result**, not from a successful HTTP response.

That entails an easily overlooked limitation: instance B might return HTTP 500 or time out while still remaining in discovery's list. Without appropriate health filtering or retries, the preference mechanism may keep prioritizing B. **Same-instance preference does not evaluate backend health itself.**

## 3. Scope of Memory: Per Service ID and Per Caller

Spring Cloud LoadBalancer typically creates a separate context per service ID through `LoadBalancerClientFactory`. Inside this context reside the corresponding selector and supplier beans. When preference is enabled for inventory, the supplier holds the *most recently selected instance* state for inventory on the caller side.

Example of a `checkout-service` process calling two services:

~~~text
checkout-service process #1
|
+-- LoadBalancer context: inventory-service
|   +-- SameInstancePreferenceServiceInstanceListSupplier
|   +-- previously selected: inventory-B
|
+-- LoadBalancer context: payment-service
    +-- separate supplier
    +-- separate policy (e.g., Round Robin)
~~~

Selecting `inventory-B` never automatically alters the selection for `payment-service`: the two service IDs have separate contexts and instance sets.

At the same time, a `RestClient` and a `WebClient` calling the same **service ID** from the same caller process can share the LoadBalancer context/supplier if they share the same configuration and `LoadBalancerClientFactory`. Preference state is therefore **not bound per HTTP client object**, per controller, or per Java thread. It is bound to the **supplier instance** managed in that LoadBalancer context.

To visualize the boundaries:

| Scope | Shares "Previously Selected Instance" by Default? | Explanation |
|---|---|---|
| Two sequential requests to the same service ID, same caller process/context | Tends to yes | Same supplier retains the latest choice |
| Two controllers in the same caller calling the same service ID | Possibly yes | If going through the same LoadBalancer client context |
| One RestClient and one WebClient in the same caller calling the same service ID | Possibly yes | If sharing LoadBalancer infrastructure/context |
| Two different service IDs, same caller process | No | Each service ID usually has its own context |
| Two replicas of `checkout-service` | No | Each JVM/container has its own supplier and memory |
| Two users passing through one caller process | No per-user state | Latest selection belongs to the caller, not the session |
| Caller restart/redeploy | Not persisted | In-memory state is recreated |
| Two clusters or two regions | Not automatically synchronized | No consensus/distributed persistence for this preference |

This is the biggest difference compared to cookie-based **session affinity**. Same-instance preference is a preference based on the *caller's latest selection*, not user identity.

## 4. When Multiple Caller Replicas Exist: Each Remembers Its Own Result

Suppose `checkout-service` is scaled to three Pods:

~~~mermaid
flowchart LR
    G["Gateway"] --> C1["Checkout Pod 1<br/>prefers inventory A"]
    G --> C2["Checkout Pod 2<br/>prefers inventory C"]
    G --> C3["Checkout Pod 3<br/>prefers inventory A"]

    C1 --> A["Inventory A"]
    C2 --> C["Inventory C"]
    C3 --> A
~~~

Each caller Pod has its own context and supplier. Pod 1 may remember A, Pod 2 remembers C, and Pod 3 also remembers A. There is no shared state store reporting which Pod chose which instance.

Consequently:

- A user sending a first request through Checkout Pod 1 may indirectly call Inventory A.
- The next request from the **same user** routed by the gateway through Checkout Pod 2 may indirectly call Inventory C.
- If all three callers happen to prefer Inventory A, A can become hot while B or C receive little traffic.

Do not interpret Same-instance preference as a `userId -> inventory instance` guarantee. Nor should you assume a large number of callers will automatically distribute evenly; initial distribution and preference lifetime can create prolonged skew.

If you need **affinity per user session**, use a mechanism with an explicit identity key such as request-based sticky sessions or consistent-hashing routing designed for the business case. If you need durable transaction or session state, use a shared data/session store rather than relying on the backend machine never changing.

## 5. Initializing or Changing the Preferred Instance

Several events change the preference state:

| Situation | Observable Outcome |
|---|---|
| Never selected an instance yet | Supplier has no prior choice; selector uses initial candidate set |
| Selected instance is still in the list | Supplier prioritizes that instance |
| Selected instance is removed from eligible set | Selector must re-select from remaining set; new choice becomes preferred |
| Discovery or cache has not yet reflected lost instance | Failed instance may still be prioritized |
| Caller restarts | Selection history is cleared |
| Service ID changes | Switches to a different context, with that service's state |
| Many concurrent requests before any history exists | Requests may choose different instances before state is updated |
| Old instance returns after caller already picked another | No guarantee of switching back to old instance; preference tracks latest selection |

A single list change does not necessarily make the supplier forget the old instance immediately. What practically matters is the **effective candidate list for that selection turn** after discovery, cache, health checks, zone filtering, or other suppliers.

In a system with many concurrent requests, selection callback ordering can interleave. Hence this is a **best-effort** policy, not a hard lock or a mechanism serializing all requests to one backend.

## 6. Enabling via Built-in Configuration

Spring Cloud provides the `same-instance-preference` preset. If you want to configure this policy application-wide, you can use:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: same-instance-preference
~~~

This preset selects the preference-enabled `ServiceInstanceListSupplier` configuration instead of the default supplier for affected LoadBalancer clients. Because it is global configuration, assess the impact on every service ID in the caller.

In versions supporting per-client overrides under the `spring.cloud.loadbalancer.clients.<serviceId>` namespace, you can attach the preset to one service:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          configurations: same-instance-preference
~~~

`inventory-service` must exactly match the service ID the caller uses. This approach depends on the per-client binding/configuration mechanism in your Spring Cloud version; check the configuration reference for your release train if the preset does not take effect. To precisely define the supplier chain or combine multiple policies, the safe and controllable option is `@LoadBalancerClient` paired with dedicated per-service-ID Java configuration.

There is no guaranteed standard property of the form `spring.cloud.loadbalancer.same-instance-preference.enabled: true` to directly replace the two approaches above. Use the proper preset or register the appropriate supplier.

## 7. Java Configuration Dedicated to inventory-service

Suppose the main application is in package `com.example.checkout`. We place the LoadBalancer configuration class in a package **outside** the main application's component-scan scope, such as `com.example.lbconfig`, to prevent beans in the client context from being registered by mistake into the application-wide context.

In the startup class:

~~~java
package com.example.checkout;

import com.example.lbconfig.InventoryPreferenceConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryPreferenceConfiguration.class
)
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

In `com.example.lbconfig.InventoryPreferenceConfiguration`:

~~~java
package com.example.lbconfig;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryPreferenceConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withSameInstancePreference()
                .build(context);
    }
}
~~~

Explanation:

- `withDiscoveryClient()` supplies the instance list from configured discovery.
- `withCaching()` is an optional cache layer placed right after the discovery source. When using DiscoveryClient's own cache or a health-check supplier that maintains its own cache, consider omitting duplicate caching.
- `withSameInstancePreference()` places the preference decorator over the source list so the LoadBalancer uses the prioritized result.
- `@LoadBalancerClient(name = "inventory-service")` scopes this configuration to the inventory service ID in the caller application.

In specific release trains, the sample code may need imports or builder chains matching the supported API. Spring Cloud shows direct examples with `withDiscoveryClient().withSameInstancePreference().build(context)`; `withCaching()` is added here to illustrate proper cache placement per supplier-chain guidance.

**Do not let this configuration class be component-scanned as global configuration.** If it is registered into the main context, the policy can affect unintended service IDs. You can leave the class without `@Configuration` as in the example, or keep an annotated class in a package outside the scan scope and reference it solely via `@LoadBalancerClient`.

Important note on chain order: preference should operate on **the candidate list already satisfying routing constraints**. For example, if you want to prioritize zone first and then maintain the instance, a configuration can use:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withSameInstancePreference()
        .build(context);
~~~

With that, an instance excluded after the zone-preference step will not keep being selected merely because it was selected last time. Verify wrapper ordering and each supplier's fallback rules rather than assuming preference implicitly understands zones or versions.

## 8. Experimenting with SimpleDiscoveryClient and RestClient

To try this locally right away, you can run three inventory instances running the same code on three ports 8081, 8082, and 8083; the caller runs on port 8080.

Dependencies needed for the caller (versions managed by compatible Spring Boot parent and Spring Cloud BOM):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Declare the static instance list in the caller's `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: checkout-service
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

In the inventory service, create an endpoint to reveal which instance handled the request:

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

    @GetMapping("/instance")
    public Map<String, String> instance() {
        return Map.of(
                "serviceId", "inventory-service",
                "instance", "inventory:" +
                        environment.getProperty("server.port", "8081")
        );
    }
}
~~~

Launch the inventory Spring Boot app as three separate processes, overriding `--server.port=8081`, `--server.port=8082`, and `--server.port=8083` respectively. The `/instance` endpoint should return a distinct instance field for each port.

On the caller, declare a builder integrated with Spring Cloud LoadBalancer:

~~~java
package com.example.checkout;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Controller creating RestClient by service ID:

~~~java
package com.example.checkout;

import java.util.Map;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class InventoryProxyController {

    private final RestClient restClient;

    public InventoryProxyController(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @GetMapping("/proxy/instance")
    public Map<String, String> proxy() {
        return restClient.get()
                .uri("/instance")
                .retrieve()
                .body(new org.springframework.core.ParameterizedTypeReference<>() {});
    }
}
~~~

This code illustrates RestClient and instance selection in action. Do not access `http://localhost:8081` directly from the caller, as that bypasses the LoadBalancer and fails to verify preference.

## 9. Observing Multiple Requests and Possible Outcomes

Run the applications and call the caller **sequentially**:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/instance").instance
}
~~~

Example output:

~~~text
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
~~~

This is an **illustrative result**, not a claim that port 8082 is always picked. Initially the LoadBalancer may choose 8081, 8082, or 8083. With the preference supplier active and a stable candidate list, subsequent calls typically continue using the first selected instance.

What to observe:

- **Preference not enabled:** with default Round Robin, ports typically alternate across multiple requests.
- **Preference enabled:** once an instance is selected, subsequent sequential calls tend to return to the same instance.
- **Concurrent requests:** multiple instances may be observed at startup or when the list changes; preference is not a mechanism that serializes requests.
- **Restarting the caller:** a new preferred instance is chosen again; by coincidence it may match the pre-restart instance.
- **Restarting a target instance while keeping static URIs:** the address is not removed from SimpleDiscoveryClient; stopping the process does not automatically trigger safe fallback.

Measure both the logical service ID and the actual instance ID, since looking only at `http://inventory-service` does not reveal which backend handled the request.

## 10. Verifying Scope with Two Caller Replicas

You can run two checkout processes from the same application, one on port 8080 and one on port 8090. Each process connects to the same inventory list while managing its own preference state.

~~~text
checkout-service :8080   -> may prefer inventory:8081
checkout-service :8090   -> may prefer inventory:8083
~~~

Call both callers sequentially:

~~~powershell
Write-Host "Caller 8080"
1..8 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/instance").instance
}

Write-Host "Caller 8090"
1..8 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8090/proxy/instance").instance
}
~~~

If both callers happen to pick `inventory:8081`, that is still a valid outcome; **it is not proof that state is shared**. To prove the boundary, restart caller 8090 alone and observe its latest selection reset; caller 8080 can continue preferring its previous instance.

Each caller replica has a LoadBalancer context inside its own JVM. Putting an API gateway in front does not make those two contexts share state. Therefore, when requests from the same user pass through different caller replicas, the chosen backend can also differ.

## 11. Verifying Failover Properly

An easy-to-misinterpret test is stopping Inventory 8082 and expecting every request to switch immediately to 8081. With a static list in `SimpleDiscoveryClient`, however, instance 8082 **is still returned**. The preference supplier may keep treating it as a candidate and calls will fail.

To verify the case where the old instance is no longer available, you need a **genuinely changing list source**:

1. Use Eureka/Consul/Kubernetes discovery or a test `ServiceInstanceListSupplier` capable of removing instances.
2. Ensure the stopped instance is no longer in the candidate list **that preference actually sees**, accounting for registry and cache latency.
3. When the next request arrives, the supplier no longer finds the old preferred instance and returns the remaining set.
4. The LoadBalancer selects a new instance, and preference updates to that instance.
5. When the old instance returns, do not expect the policy to automatically switch back to it; the new instance has become the latest choice.

Depending on design, `HealthCheckServiceInstanceListSupplier` can be used to exclude unhealthy instances before reaching the preference step. This mechanism must be configured in the proper order; setting `health-check.interval` in YAML does not automatically enable the health supplier. Additionally, some discovery clients already include health filtering and caching, so avoid wrapping unnecessary redundant cache layers.

Results to log: when the instance disappeared from the supplier, which instance was previously preferred, error count before switching, newly selected instance, and recovery latency. These metrics distinguish **instance health detection failures** from **instance selection errors**.

## 12. Preference Does Not Replace Request-Based Sticky Sessions

Spring Cloud has another feature named `RequestBasedStickySessionServiceInstanceListSupplier`. It prioritizes an instance ID read from a cookie in the request, unlike Same-instance preference which relies on the caller's previous selection.

| Property | Same-Instance Preference | Request-Based Sticky Session |
|---|---|---|
| Key used to prioritize | Supplier's most recently selected instance | Instance ID in request cookie |
| Where context lives | Supplier memory in the caller's LoadBalancer context | Cookie attached to each corresponding request/client flow |
| Distinguish two users through the same caller | No | Possible, if cookies are propagated properly |
| Two caller replicas | Maintain separate selection histories | Can preserve continuity if cookie arrives properly and instance remains eligible |
| When preferred instance disappears | Falls back using current list | Falls back using current list |
| Primary goal | Minimize backend switching for a caller | Route related requests to the same backend |

According to Spring Cloud Commons documentation, request-based sticky sessions can use:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: request-based-sticky-session
      sticky-session:
        add-service-instance-cookie: true
      instance-id-cookie-name: sc-lb-instance-id
~~~

Automatic cookie addition and request context support depend on the HTTP integration; Spring Cloud documentation notes direct support for the WebClient path in this section. Do not assume RestClient or all Feign setups share identical cookie-handling behavior.

Neither mechanism is a **promise** that requests will stay on one instance indefinitely. If a backend is removed, fallback is necessary. If the application depends on session/state stored in a single backend's memory, design shared session storage or recovery when a backend dies.

## 13. Interaction with Retries, Timeouts, and Multi-Layer Load Balancing

Same-instance preference belongs to the **target selection** layer. It does not configure connect timeouts, read timeouts, retry counts, circuit breakers, or transaction idempotency.

When a request encounters an error:

- The instance-selection callback may already have recorded the instance before knowing whether the HTTP request succeeded or failed.
- If the failing instance remains in the list, preference may continue selecting the failing instance.
- If retries are enabled and you want to avoid the recently failed instance, inspect the retry policy and the corresponding `RetryAwareServiceInstanceListSupplier`. Policies that avoid previous instances can interact with preference; verify actual behavior in your active version.
- The HTTP client still needs connect/read/response timeouts so it does not wait forever when a target is unresponsive.
- POST or state-changing operations require idempotency keys/duplicate-prevention design before retrying.

Furthermore, if the caller selects a VIP or Kubernetes Service address rather than directly targeting a Pod/instance, Same-instance preference only stabilizes the **logical address seen by the LoadBalancer**. Infrastructure behind the VIP can still distribute connections to different backends. Do not rely on preference to infer the final Pod when the system has two layers of load balancing.

An example:

~~~text
Caller process
  -> SameInstancePreferenceServiceInstanceListSupplier
  -> ServiceInstance = http://inventory.internal (VIP)
  -> Infrastructure load balancer
  -> May route to backend A or backend B
~~~

If only one VIP exists in the list, preference cannot distinguish the backends behind it. Selection looks stable in Spring Cloud, yet actual HTTP requests can still be spread by infrastructure.

## 14. Load Skew Risks and Solution Selection Criteria

Same-instance preference can be helpful when backends maintain local caches and callers benefit from repeatedly calling a familiar replica. Before adopting it, however, answer these questions:

- **Caller replica count vs. backend count:** one caller can push nearly all its load onto one backend; if there are very few callers and many backends, several backend replicas may receive almost no traffic.
- **Backend homogeneity:** if instances have different capacities, preference does not factor in weights or CPU.
- **Caller lifetime:** long-lived processes hold preferences for a long time; after a rolling restart, the caller → backend mapping can redistribute abruptly.
- **Backend churn:** do health checks and discovery refreshes remove failed instances quickly enough?
- **Multiple regions/zones:** is the preferred instance still valid under the current zone policy?
- **Session data:** does critical state reside exclusively in backend RAM? If so, preference is insufficient for correctness.

Policy selection examples:

| Need | Approach |
|---|---|
| Distribute requests roughly evenly by count | Round Robin or a suitable load-balancing policy |
| Have caller prefer its most recently chosen instance while available | Same-instance preference |
| Give individual users affinity across caller replicas | Request-based sticky session or identifier-keyed routing |
| Reduce cross-zone calls | ZonePreference supplier, optionally combined with preference in proper order |
| Balance based on differing backend capacities | Weighted or custom strategy backed by load data |
| Keep sessions alive when a backend is replaced | Store session/state in a shared store, not via routing alone |

Most systems needing availability and load distribution should start with Round Robin and health filtering, enabling preference only when measurements show a benefit. If the goal is cache locality, compare cache hit ratio, p95/p99 latency, and load skew across replicas before and after enabling it.

## 15. Observability and Diagnostics

Looking at one backend's logs is not enough to conclude preference is working. Observe across three layers:

1. **Caller:** caller instance ID/Pod name, target service ID, request duration, HTTP status, and retry count.
2. **LoadBalancer:** candidate list after filtering, most recently selected instance, fallback counts, and instance-change events if instrumented.
3. **Backend:** actual serving instance ID, request count, cache hit rate, CPU, error rate, and response latency.

Common scenarios:

| Symptom | Causes to Check |
|---|---|
| Requests alternate among A/B/C | Preference supplier not enabled, or configuration scoped to the wrong service ID |
| Requests always hit A | Preference may be active; or only one candidate exists or caller calls A directly |
| Two callers pick two different backends | Normal because two callers maintain separate state |
| Same user switches backends | Gateway may switch caller Pods; preference is not keyed by user |
| A is dead yet still prioritized | Discovery/cache/health has not removed A from the list |
| Backend changes after caller restart | Preference history is not persistent |
| Heavy load skew after enabling policy | Expected possible outcome; check caller count, backend count, and per-caller traffic |
| Both zone and preference enabled yet unexpected selection | Check supplier order and fallback when no instances exist in zone |

For Spring Cloud LoadBalancer, Micrometer lifecycle/metrics can be enabled according to your version when a `MeterRegistry` is present. Avoid putting user IDs or raw dynamic URLs into labels, which causes high cardinality. To know the *selected instance* per request, use correlation-ID logging, custom lifecycle callbacks, or HTTP request transformers depending on client type.

### Verification Checklist

- [ ] Service ID in the URI matches `@LoadBalancerClient(name = "...")` or per-client configuration branch.
- [ ] Caller uses RestClient/WebClient/OpenFeign integrated with Spring Cloud LoadBalancer, not direct IP calls.
- [ ] Active supplier chain contains `SameInstancePreferenceServiceInstanceListSupplier`.
- [ ] Per-client configuration class is not component-scanned as global configuration.
- [ ] Verified first call selects an instance and subsequent sequential calls re-prefer that instance.
- [ ] Clearly understood state is **per service ID / per caller process**, not per user/session.
- [ ] Tested with two caller replicas without assuming shared history.
- [ ] Verified discovery/cache/health latency when a backend fails and defined fallback conditions.
- [ ] If zone/hint is present, verified supplier ordering.
- [ ] Verified retry, timeout, and idempotency requirements separately.
- [ ] Measured request count/CPU/latency per backend to catch hotspots before broad rollout.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): section *Same instance preference for LoadBalancer*, `SameInstancePreferenceServiceInstanceListSupplier`, `same-instance-preference` preset, and request-based sticky sessions.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `spring.cloud.loadbalancer` properties and per-service-ID configuration.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): discovery and retries in service-to-service communication.

**Conclusion:** Same-instance preference is a policy that **prioritizes the latest selection remembered on the caller side**. It helps a caller tend to stick with a `ServiceInstance` as long as that instance remains eligible, yet it does not mean users have durable session affinity or that multiple caller replicas share the same choice. For stable operations, combine proper discovery, health checks, retries/timeouts, load-distribution observability, and routing policy choices aligned with business requirements.
