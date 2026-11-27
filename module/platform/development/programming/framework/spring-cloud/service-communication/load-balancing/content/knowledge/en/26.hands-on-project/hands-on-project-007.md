# Practicing Zone Preference, Weighting, and Hints

When an application calls `http://inventory-service`, **Spring Cloud LoadBalancer** picks a `ServiceInstance` from the discovery list. By default, Round Robin distributes selections relatively evenly across instances. In real-world systems, we frequently need three additional policies:

- **Zone preference:** a caller in zone `hcm` wants to prefer replicas in the same zone to reduce network latency and cost.
- **Weighting:** a replica with more resources should receive a larger share of requests than a smaller replica.
- **Hints:** individual calls can designate a preferred group of replicas, such as `blue` and `green` during a rollout.

This **Hands-On Project** builds a lab from scratch to observe each policy independently and then compose them in a deliberate order. The lab applies to the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module: calling by **service ID**, selecting instances via discovery and `ServiceInstanceListSupplier`, and testing fallbacks, timeouts, retries, and observability. The main section uses **WebClient** because it makes passing hints via request headers and observing reactive pipelines straightforward; the end of the lesson explains how to use the same policies from `RestClient` and OpenFeign.

> **Scope:** this is a local lab using `SimpleDiscoveryClient` and static metadata. The distribution numbers are **expectations**, not executed benchmark results. Never rely on default hint or zone preference to enforce authorization, data residency, or security isolation.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Run one caller and four `inventory-service` replicas with `zone`, `weight`, and `hint` metadata.
2. Construct a `ServiceInstanceListSupplier` in `zone`, `weighted`, `hint`, or `combined` mode.
3. Distinguish between **the eligible instance set after filtering** and **the single-instance selection algorithm** (e.g., Round Robin).
4. Use `spring.cloud.loadbalancer.zone` and `ZonePreferenceServiceInstanceListSupplier` for zone preference.
5. Use `WeightedServiceInstanceListSupplier` to apply weights from the `weight` metadata key.
6. Use `HintBasedServiceInstanceListSupplier` and the `X-SC-LB-Hint` header to prefer a replica group per request.
7. Observe how all three policies compose, including fallbacks when no instance matches a zone or hint.
8. Collect hit counts, compare against expected distribution shares, test failures, and establish safety guardrails for production.

### Distinguishing the Three Goals

| Policy | Input | What Does It Do? | What Does It Not Guarantee? |
|---|---|---|---|
| Zone preference | Caller zone and instance `zone` metadata | Prefers instances in the same zone | Does not strictly reject cross-zone calls when no match exists |
| Weight | `weight` metadata or `WeightFunction` | Biases selection frequency by weight | Does not automatically inspect live CPU/queues or real-time capacity |
| Hint | Request header `X-SC-LB-Hint` or hint property, `hint` metadata | Prefers instances with matching hint | Not a hard partition or security mechanism |

These three policies are implemented primarily via **supplier decorators**, without necessarily writing a custom `ReactorServiceInstanceLoadBalancer`. `RoundRobinLoadBalancer` can still pick one item from the list produced by the supplier.

## 2. Lab Architecture

~~~mermaid
flowchart TB
    U["PowerShell or HTTP client"] --> C["caller :8080 (WebClient)"]
    C --> L["Spring Cloud LoadBalancer / inventory-service"]
    M["SimpleDiscoveryClient: zone, weight, hint metadata"] --> L
    L --> A["inventory HCM blue A :8081 (weight 3)"]
    L --> B["inventory HCM blue B :8082 (weight 1)"]
    L --> D["inventory HCM green C :8083 (weight 2)"]
    L --> E["inventory HN blue D :8084 (weight 4)"]
~~~

We use zone names `hcm` and `hn` for illustration; they are strictly **metadata strings** in the lab and do not mean the processes actually run in different data centers.

| Instance ID | URI | `zone` | `hint` | `weight` |
|---|---|---|---|---:|
| `hcm-blue-a` | `http://localhost:8081` | `hcm` | `blue` | 3 |
| `hcm-blue-b` | `http://localhost:8082` | `hcm` | `blue` | 1 |
| `hcm-green-c` | `http://localhost:8083` | `hcm` | `green` | 2 |
| `hn-blue-d` | `http://localhost:8084` | `hn` | `blue` | 4 |

Place the caller in zone `hcm`:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: hcm
~~~

Scenarios to observe:

- **Zone:** only A/B/C remain eligible when `hcm` replicas exist; D in `hn` is not preferred.
- **Weight:** without filtering, target distribution by weight for A:B:C:D is `3:1:2:4`.
- **Hint = blue:** prefers A/B/D because of `hint: blue` metadata.
- **Hint = green:** prefers C.
- **Combined (zone → hint → weight):** with hint `blue`, ends up preferring A/B in a `3:1` target ratio; hint `green` leaves only C.
- **Unknown hint:** when no instance matches, the default hint supplier **returns the list supplied by its delegate**, rather than returning an empty list by default.

The combined outcomes are a property of **the supplier order configured in this lesson**. Changing the order can change the selected candidate set.

## 3. Tools and Dependencies

Required setup:

- JDK compatible with your chosen Spring Boot version, Maven, and PowerShell or an equivalent terminal.
- A simple Spring Boot **backend** project (Spring Web).
- A Spring Boot **caller** project (Spring WebFlux, Spring Cloud LoadBalancer, optional Actuator).
- No Eureka/Consul/Kubernetes needed for the lab because `SimpleDiscoveryClient` uses a static list.

Choose Spring Boot and Spring Cloud **from a compatible release train**. For example, Spring Cloud docs list Spring Cloud `2025.0.x` alongside Spring Boot `3.5.x`, and `2025.1.x` alongside Spring Boot `4.0.x` and compatible `4.1.x` versions. Never mix BOMs from two generations. For this lesson, use a verified compatible pair or generate from Spring Initializr with compatible dependencies. Some Boot 4 Web starters changed names relative to Boot 3; avoid copying POMs across generations without checking.

Caller dependencies using compatible Spring Boot/Cloud BOMs:

~~~xml
<dependencies>
    <!-- Reactive HTTP client and caller REST endpoint. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <!-- Client-side discovery / ServiceInstance LoadBalancer. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Metrics and health observation; optional in small labs. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The backend project needs the Web starter matching your Spring Boot generation and `spring-boot-starter-test` if writing tests. When using Maven, configure the Spring Cloud BOM in `dependencyManagement` per Spring Initializr guidelines:

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

`spring-cloud.version` must be set to a Boot-compatible version, not left as an unresolved placeholder. The lab supplies only the necessary file snippets; learners can place them into two standalone Maven projects rather than creating a multi-module build.

### Suggested Source Layout

~~~text
routing-lab/
  backend/
    pom.xml
    src/main/java/com/example/lab/backend/
      BackendApplication.java
      ReplicaController.java

  caller/
    pom.xml
    src/main/java/com/example/lab/caller/
      CallerApplication.java
      RoutingClientConfiguration.java
      RoutingController.java
    src/main/java/com/example/lab/lb/
      InventoryLoadBalancerConfiguration.java
    src/main/resources/
      application.yml
~~~

**Important:** `InventoryLoadBalancerConfiguration` sits in package `com.example.lab.lb` **outside the component scan** of `com.example.lab.caller`. This prevents per-service configuration from being pulled into the parent `ApplicationContext` and accidentally applying to other service IDs.

## 4. Building the Inventory Backend from a Single Artifact

Each replica runs the same backend artifact with different ports and `lab.*` properties. The backend simply echoes illustrative metadata so we know which instance was called.

`BackendApplication.java`:

~~~java
package com.example.lab.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

`ReplicaController.java`:

~~~java
package com.example.lab.backend;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReplicaController {

    private final Environment environment;

    public ReplicaController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public InstanceView whoami(
            @RequestHeader(
                    name = "X-SC-LB-Hint",
                    required = false
            ) String receivedHint) {

        return new InstanceView(
                environment.getRequiredProperty("lab.instance-id"),
                environment.getProperty("lab.zone", "unknown"),
                environment.getProperty("lab.hint", "unknown"),
                environment.getProperty("lab.weight", "1"),
                receivedHint,
                environment.getProperty("server.port", "unknown")
        );
    }

    public record InstanceView(
            String instanceId,
            String zone,
            String hint,
            String weight,
            String receivedHint,
            String port
    ) {}
}
~~~

**Do not confuse the two metadata sources:** the backend's `lab.zone`/`lab.hint`/`lab.weight` properties are **for echoing only**. Spring Cloud LoadBalancer on the caller actually reads `zone`/`hint`/`weight` metadata from `ServiceInstance.getMetadata()` supplied by `SimpleDiscoveryClient`. If the two sources diverge, you might see the backend echo "hcm" while the supplier selects it under "hn". Always inspect the instance registration source, not just the demo response.

### Running the Four Backends

Build the artifact:

~~~powershell
cd routing-lab/backend
mvn -q -DskipTests package
~~~

Open **four separate terminals** and run one command in each (replace the JAR path with your actual artifact):

~~~powershell
# Terminal 1
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8081 --lab.instance-id=hcm-blue-a --lab.zone=hcm --lab.hint=blue --lab.weight=3
~~~

~~~powershell
# Terminal 2
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8082 --lab.instance-id=hcm-blue-b --lab.zone=hcm --lab.hint=blue --lab.weight=1
~~~

~~~powershell
# Terminal 3
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8083 --lab.instance-id=hcm-green-c --lab.zone=hcm --lab.hint=green --lab.weight=2
~~~

~~~powershell
# Terminal 4
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8084 --lab.instance-id=hn-blue-d --lab.zone=hn --lab.hint=blue --lab.weight=4
~~~

If Maven produces a differently named JAR, match your project's `artifactId`/`version`. Never run all four commands sequentially in the same foreground terminal because the first process blocks the prompt.

Verify each instance directly:

~~~powershell
8081..8084 | ForEach-Object {
    Invoke-RestMethod "http://localhost:$_/whoami"
}
~~~

Expect to see all four instance IDs, their zone/hint/weight values, and their ports. `receivedHint` is `null` since you have not sent the header yet.

## 5. Declaring Four ServiceInstances in the Caller

In `caller/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: routing-caller

  cloud:
    loadbalancer:
      zone: hcm
      hint-header-name: X-SC-LB-Hint
      retry:
        enabled: false   # Lab: keep a single HTTP attempt for easy counting.
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - instance-id: hcm-blue-a
                uri: http://localhost:8081
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "3"
              - instance-id: hcm-blue-b
                uri: http://localhost:8082
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "1"
              - instance-id: hcm-green-c
                uri: http://localhost:8083
                metadata:
                  zone: hcm
                  hint: green
                  weight: "2"
              - instance-id: hn-blue-d
                uri: http://localhost:8084
                metadata:
                  zone: hn
                  hint: blue
                  weight: "4"

lab:
  routing:
    mode: zone

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

**How to read this:**

- `inventory-service` is the single **service ID** with four `ServiceInstance` entries.
- `instance-id` identifies instances for logs/tests; `uri` specifies the physical host:port.
- `metadata.zone` is compared by `ZonePreferenceServiceInstanceListSupplier` against client zone `hcm`.
- `metadata.hint` is used by `HintBasedServiceInstanceListSupplier` to filter by request hint.
- `metadata.weight` is parsed by `WeightedServiceInstanceListSupplier` as an integer by default; if missing, weight 1 is used.
- `lab.routing.mode` is a **custom property defined for this lab** to pick the supplier policy; it is not a built-in Spring Cloud setting.
- `retry.enabled: false` disables Spring Cloud LoadBalancer's retry mechanism for simpler analysis. Any other HTTP client/gateway layer with retries enabled must be checked separately.

`SimpleDiscoveryClient` reads the list from properties and does not update automatically when a backend process stops. Thus, the fault-simulation section near the end distinguishes "address still in discovery" from "instance actually healthy."

## 6. Why Not Pick Zone, Weight, or Hint Directly in the Controller?

An anti-pattern:

~~~java
// Illustrates the WRONG approach: bypasses discovery/LoadBalancer.
String url = hint.equals("blue")
        ? "http://localhost:8081/whoami"
        : "http://localhost:8083/whoami";
~~~

This couples business code to raw IPs/ports, lacks consistent health/zone/weight policies, and bypasses discovery.

The proper lab path:

~~~text
RoutingController
    -> WebClient calls http://inventory-service/whoami
    -> @LoadBalanced WebClient.Builder
    -> Spring Cloud LoadBalancer
    -> ServiceInstanceListSupplier:
         discovery -> zone/hint/weight
    -> RoundRobinLoadBalancer selects one candidate
    -> HTTP to physical URI
~~~

**Zone preference and hint are candidate-list filters/preferencers**; the weighted supplier adjusts selection odds from that list. They are not three separate HTTP calls or three separate retry loops.


## 7. Creating Per-Service-ID LoadBalancer Configuration

In the caller, declare `@LoadBalancerClient` to configure suppliers **exclusively for `inventory-service`**.

`CallerApplication.java`:

~~~java
package com.example.lab.caller;

import com.example.lab.lb.InventoryLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

`InventoryLoadBalancerConfiguration.java` (in package `com.example.lab.lb`, **outside** component scan):

~~~java
package com.example.lab.lb;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "zone"
    )
    ServiceInstanceListSupplier zoneSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withZonePreference()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "weighted"
    )
    ServiceInstanceListSupplier weightedSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withWeighted()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "hint"
    )
    ServiceInstanceListSupplier hintSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHints()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "combined"
    )
    ServiceInstanceListSupplier combinedSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withZonePreference()
                .withHints()
                .withWeighted()
                .build(context);
    }
}
~~~

This registers **one supplier bean per mode**: `@ConditionalOnProperty` ensures only the method whose `havingValue` matches `lab.routing.mode` is registered. Since the lab always sets `mode`, `matchIfMissing` is unnecessary.

Architectural notes:

- `.withDiscoveryClient()` retrieves the list from discovery; in a lab without an external registry, `SimpleDiscoveryClient` supplies the static instances.
- `.withZonePreference()` uses the caller zone and instance `zone` metadata.
- `.withHints()` filters by the request/property hint and `hint` metadata.
- `.withWeighted()` transforms the list by weight before the selector picks an item.
- No custom `ReactorLoadBalancer<ServiceInstance>` is defined because we keep the default `RoundRobinLoadBalancer`.
- If using `withCaching()` in production, place it **right after retrieval**, ahead of request-filtering suppliers. Never inadvertently cache the output after hint/zone filtering, since requests A and B may carry different hints.
- Do not annotate `InventoryLoadBalancerConfiguration` with `@Configuration` or `@Component` inside a component-scanned package. If scanned as a global bean, it can affect other service IDs.
- Supplier builder methods require APIs matching your release train; if upgrading Spring Cloud, run integration tests for every mode.

### Supplier Chain Diagram in Combined Mode

~~~mermaid
flowchart LR
    D["Discovery"] --> Z["ZonePreference"]
    Z --> H["HintBased"]
    H --> W["Weighted"]
    W --> RR["RoundRobinLoadBalancer"]
    RR --> I["ServiceInstance"]
~~~

When `zone=hcm` and header `hint=blue`:

~~~text
Discovery:
  A(hcm,blue,w3)
  B(hcm,blue,w1)
  C(hcm,green,w2)
  D(hn, blue,w4)

Zone preference:
  A, B, C

Hint blue:
  A, B

Weighted:
  Logical list in 3:1 ratio between A and B

Round Robin:
  Selects one entry from the list provided by the supplier

HTTP:
  Calls A :8081 or B :8082
~~~

**Order is part of the contract.** If hint ran before zone, a hint matching only instances in another zone could produce a different candidate set. In this lesson's chain, zone runs first, then hint, and finally weighting applies across the remaining candidates.

### Why Does the Example Leave Caching Off?

We have four static instances and want to see each policy's effect cleanly. Therefore, the builders omit `withCaching()`. This is a **lesson simplification**, not a production performance recommendation. With real discovery, Spring Cloud recommends caching unless the discovery client already caches; a production configuration might look like:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .withWeighted()
        .build(context);
~~~

With `HealthCheckServiceInstanceListSupplier`, pay attention to caching/replay behavior and the specific ordering described in the docs. Avoid stacking multiple independent caching/health layers without understanding when the instance list refreshes.

## 8. Creating the @LoadBalanced WebClient

`RoutingClientConfiguration.java`:

~~~java
package com.example.lab.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class RoutingClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

`@LoadBalanced` attaches Spring Cloud LoadBalancer to the builder. In `http://inventory-service`, the hostname is the **service ID**, and `/whoami` is the backend endpoint. Calling `http://localhost:8081` directly **bypasses service ID selection** and will not exercise the configured suppliers.

Without `spring-cloud-starter-loadbalancer` or `@LoadBalanced`, you may see an `UnknownHostException` for hostname `inventory-service`.

## 9. Caller Controller: Forwarding Only Allowlisted Hints

`RoutingController.java`:

~~~java
package com.example.lab.caller;

import java.time.Duration;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class RoutingController {

    private static final Set<String> DEMO_HINTS =
            Set.of("blue", "green", "unknown");

    private final WebClient inventory;

    public RoutingController(
            @Qualifier("inventoryWebClient") WebClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/route")
    public Mono<InstanceView> route(
            @RequestParam(required = false) String hint) {

        if (hint != null && !DEMO_HINTS.contains(hint)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported lab hint"
            ));
        }

        return inventory.get()
                .uri("/whoami")
                .headers(headers -> {
                    if (hint != null) {
                        headers.set("X-SC-LB-Hint", hint);
                    }
                })
                .retrieve()
                .bodyToMono(InstanceView.class)
                .timeout(Duration.ofSeconds(2));
    }

    public record InstanceView(
            String instanceId,
            String zone,
            String hint,
            String weight,
            String receivedHint,
            String port
    ) {}
}
~~~

Key points:

- `hint` is a query parameter on the **caller demo API**, which the caller explicitly attaches as the `X-SC-LB-Hint` header on the outbound HTTP request to inventory. Do not confuse the two data layers.
- `null` means the caller **sends no hint header**. The lab also sets no default hint in properties.
- `blue` and `green` are valid values. `unknown` is **intentionally allowlisted to test fallback**, not a production rollout value.
- `DEMO_HINTS` is purely a lab allowlist. Production must derive hints from trusted routing policy decisions (feature flags, rollout allocations, authenticated permissions), never copying untrusted Internet headers blindly.
- `.timeout(Duration.ofSeconds(2))` bounds this reactive publisher. It does not mean backend execution stops when the client times out.
- The backend echoing the header lets us confirm transmission, yet **merely seeing the header at the backend does not prove** LoadBalancer filtered correctly; verify `instanceId` in the response.

### Where Does the Supplier Read the Hint Header?

Spring Cloud's `HintBasedServiceInstanceListSupplier` checks for a hint in the `Request` context; on the `WebClient`-backed LoadBalancer path, client request headers can be passed into `RequestDataContext`. When `X-SC-LB-Hint` is present, the supplier matches it against the `hint` metadata of each `ServiceInstance`.

If no header is present, the supplier can fall back to property hints such as:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint:
        default: blue
~~~

Beyond `default`, Spring Cloud also supports per-service-ID hints via `spring.cloud.loadbalancer.hint.[SERVICE_ID]`. However, **do not add a default to the basic lab** if your goal is observing that "no hint" returns the full list.

The default header name is `X-SC-LB-Hint`; it can be changed via `spring.cloud.loadbalancer.hint-header-name`. If changed, keep `WebClient` and tests in sync.

## 10. Building and Running the Caller

In another terminal:

~~~powershell
cd routing-lab/caller
mvn -q -DskipTests package
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone
~~~

Use your project's actual JAR name if different. The caller runs on port 8080; if occupied, change `server.port` and update the test URLs accordingly.

First verification call:

~~~powershell
Invoke-RestMethod "http://localhost:8080/route"
~~~

Example response (illustrative only):

~~~json
{
  "instanceId": "hcm-blue-b",
  "zone": "hcm",
  "hint": "blue",
  "weight": "1",
  "receivedHint": null,
  "port": "8082"
}
~~~

Actual responses may pick A or C depending on the Round Robin cursor. What to verify in `zone` mode is that **D (`hn`) is not selected while A/B/C are available** and discovery/supplier loaded the right metadata.

When switching modes, **stop and restart the caller** with `zone`, `weighted`, `hint`, or `combined`. Do not assume mutating `lab.routing.mode` via a custom endpoint will rebuild the `ServiceInstanceListSupplier` bean. With `@ConditionalOnProperty` as structured here, selection happens **at `ApplicationContext` startup**.

## 11. Test A: Enabling Zone Preference Only

Start the caller:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone
~~~

Send 12 requests without hints:

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route" |
        Select-Object instanceId,zone,port
}
~~~

**Eligibility expectations:**

~~~text
Eligible after ZonePreference(hcm): A, B, C
D in hn: not selected while A/B/C remain in the list

With Round Robin and a stable list:
A, B, C, A, B, C ... (starting offset may vary)
~~~

The first response does not have to be A: the Round Robin implementation may start at a different offset. Across exactly 12 selections over 3 stable candidates, each candidate can be picked 4 times.

### When the Zone Has No Matching Instances

Try starting the caller with an override:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone --spring.cloud.loadbalancer.zone=unknown-zone
~~~

`ZonePreferenceServiceInstanceListSupplier` **does not fail closed** when zero instances exist in the requested zone: it **returns the entire delegate list**. Consequently, all of A/B/C/D can be picked. This is an **availability-first fallback** of the implementation, not a regional data-isolation enforcement mechanism.

If business compliance requires running strictly in `hcm` for residency, **never use default `ZonePreference` as the sole control**. Implement a tested hard-filter supplier or policy that intentionally fails when no match exists.

### Real-World Zone Scenarios

In multi-AZ infrastructure, zone preference reduces cross-AZ traffic and latency. However, zone metadata must mirror real topology, each zone needs sufficient capacity, and cross-zone fallback must be approved. `localhost` in this lab validates routing logic only—it cannot measure inter-zone latency.

## 12. Test B: Enabling Weighting

Stop the zone-mode caller and restart:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=weighted
~~~

In this mode, there is **no `withZonePreference()` and no `withHints()`**: A/B/C/D are all eligible. `WeightedServiceInstanceListSupplier` reads `weight` metadata and provides a weighted list to Round Robin.

Target weighted distribution:

\[
p_i = \frac{w_i}{\sum_j w_j}
\]

With `w_A=3, w_B=1, w_C=2, w_D=4`, totaling 10:

| Instance | Weight | Target Share | Expected in 1,000 Selections |
|---|---:|---:|---:|
| A | 3 | 30% | 300 |
| B | 1 | 10% | 100 |
| C | 2 | 20% | 200 |
| D | 4 | 40% | 400 |

These are metadata targets, **not executed run logs**. Over sufficiently large samples and a stable list, hit counts should match how the weighted supplier materializes weights; exact counts in a short window may vary slightly.

A common misconception: **a weight of 3 does not mean one HTTP request is sent three times**. It changes the relative selection frequency, without duplicating business requests or adjusting timeouts.

### Checking with PowerShell

~~~powershell
$selected = 1..1000 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/route").instanceId
}

$selected | Group-Object | Sort-Object Name |
    Select-Object Name,Count,
        @{Name="Percent"; Expression={
            [math]::Round(100.0 * $_.Count / $selected.Count, 1)
        }}
~~~

Compare the `Percent` column against the 30%/10%/20%/40% targets, **without treating one short run as proof of exact probabilities**. If weights are ignored and distribution hovers near 25% per instance across multiple independent samples, inspect `weight` metadata and confirm `weighted` mode—not `zone` or plain Round Robin—is running.

### Weight Must Not Be Used as an Instance Off-Switch

If `weight` is missing, `WeightedServiceInstanceListSupplier` defaults to 1. Invalid or non-positive values may fall back to the default weight depending on implementation; never set `weight: "0"` assuming a replica is guaranteed to receive zero traffic. To drain an instance, use discovery deregistration, health filtering, or an explicit contract-backed policy.

A 4:1 weight ratio does not prove the larger replica actually has 4× capacity. Before production use, measure per-instance CPU, memory, queues, p99 latency, and error rates, and set weights from capacity data and observation.

## 13. Test C: Enabling Per-Request Hints

Stop the caller and run:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=hint
~~~

Here the supplier filters strictly by `hint`, with **no** zone preference and **no** weights.

### Hint blue

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=blue" |
        Select-Object instanceId,zone,hint,receivedHint
}
~~~

Expected candidate set: **A/B/D**, since all three carry `hint: blue`; **C** does not match. With Round Robin and a stable snapshot, A/B/D should receive nearly equal counts.

### Hint green

~~~powershell
1..6 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=green" |
        Select-Object instanceId,zone,hint
}
~~~

Expected candidate set: **only C**, so 100% of requests route to C as long as it remains in discovery and healthy.

### No Hint

~~~powershell
Invoke-RestMethod "http://localhost:8080/route"
~~~

When neither a hint header nor a hint property is present, the default supplier **does not filter** by `hint` metadata. All four replicas A/B/C/D are eligible.

### Unmatched Hint

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=unknown"
}
~~~

No replica has `hint: unknown` metadata. By default behavior of `HintBasedServiceInstanceListSupplier`, if the filtered list is empty, it returns **the full delegate list** rather than an `EmptyResponse`. Therefore, a request carrying an unknown hint **can still succeed against A/B/C/D**.

**Safety implication:** default hinting is a *preference*, not an authorization boundary, tenancy boundary, or hard version pin. For rollouts where v2 traffic **must never** reach v1, write a custom strict filter or API routing/auth layer with fail-closed behavior instead of relying on the default hint supplier.

### Header Crossing the Network vs. Header Affecting Selection

`receivedHint` on the backend confirms the header arrived; however, seeing `receivedHint: "blue"` from C would signal a misconfiguration if `hint` mode were filtering properly. Always inspect **both the instance ID** and the echoed header.

In real systems, hints must come from trusted policy decisions. Never let external users pick legacy versions or sensitive zones by forging raw headers.

## 14. Test D: Composing zone → hint → weight

Restart the caller:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=combined
~~~

With zone `hcm`, the supplier chain is:

~~~text
Discovery:       A, B, C, D
Zone preference: A, B, C
Hint:            filters by hint if any match is found
Weight:          adjusts ratios within the remaining list
Round Robin:     selects an instance
~~~

### D1. Hint = blue

~~~powershell
$selected = 1..400 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/route?hint=blue").instanceId
}

$selected | Group-Object | Sort-Object Name |
    Select-Object Name,Count,
        @{Name="Percent"; Expression={
            [math]::Round(100.0 * $_.Count / $selected.Count, 1)
        }}
~~~

The set after zone+hint is **A/B**. Weight A:B = 3:1. Target share is **75% A and 25% B**; C fails the hint filter and D is outside the preferred zone, so neither ID should appear when metadata and configuration work properly.

### D2. Hint = green

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=green" |
        Select-Object instanceId,zone,hint
}
~~~

The set after zone+hint contains only **C**. Weight C=2 creates no additional backends; all valid selections hit C.

### D3. No Hint Sent

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route" |
        Select-Object instanceId,zone,hint
}
~~~

Zone narrows to **A/B/C**, empty hint keeps that list, and target weights are **3:1:2**:

| Instance | Target Share Within `hcm` |
|---|---:|
| A | 50.0% |
| B | 16.7% |
| C | 33.3% |
| D | 0% while `hcm` has candidates |

### D4. Hint = unknown

~~~powershell
Invoke-RestMethod "http://localhost:8080/route?hint=unknown"
~~~

No instance in A/B/C has hint `unknown`, so `HintBasedServiceInstanceListSupplier` **falls back to its delegate list A/B/C**. Then weights 3:1:2 still apply. This prioritizes availability, **not strict matching**.

### D5. Changing the Caller Zone

Stop the caller and run:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=combined --spring.cloud.loadbalancer.zone=hn
~~~

If zone `hn` has D, the zone step narrows to **D**. With hint `blue`, D matches and is selected. With hint `green`, **no instance in `{D}` matches `green`**, yet `HintBasedServiceInstanceListSupplier` **falls back to D** (the post-zone delegate list), so requests still route to D even though D's `hint` metadata is `blue`.

Expectations table:

| Caller Zone | Request Hint | List After Zone | List After Hint (With Fallback) |
|---|---|---|---|
| hcm | blue | A, B, C | A, B |
| hcm | green | A, B, C | C |
| hcm | unknown | A, B, C | A, B, C |
| hcm | none | A, B, C | A, B, C |
| hn | blue | D | D |
| hn | green | D | D (fallback, not hard match) |
| unknown-zone | blue | A, B, C, D (zone fallback) | A, B, D |

**Lesson on ordering and fallbacks:** zone preference is a soft preference, and hint is also a soft preference. If a rule mandates "only zone X + version Y instances may serve," use a **hard** policy with explicit behavior when no candidates exist.


## 15. Scenario Matrix Summary

Before moving to fault testing, record the expected distribution table **for your chosen configuration**. This serves as a reference for acceptance tests; shares are expectations under a stable snapshot, no retries, zero errors, and the right supplier chain.

| Mode | Caller Zone | Hint | Final Eligible Candidates | Target Ratio |
|---|---|---|---|---|
| zone | hcm | none | A/B/C | Approx. 1:1:1 |
| zone | hcm | green | A/B/C | Hint has no effect in `zone` mode |
| weighted | hcm | none | A/B/C/D | 3:1:2:4 |
| weighted | hcm | blue | A/B/C/D | Hint has no effect in `weighted` mode |
| hint | hcm | blue | A/B/D | Approx. 1:1:1 |
| hint | hcm | green | C | 100% C |
| hint | hcm | unknown | A/B/C/D | Falls back to full list |
| hint | hcm | none | A/B/C/D | Unfiltered when no default hint is set |
| combined | hcm | blue | A/B | 3:1 |
| combined | hcm | green | C | 100% C |
| combined | hcm | unknown | A/B/C | Hint falls back to zone-list, then weight 3:1:2 |
| combined | hcm | none | A/B/C | 3:1:2 |
| combined | hn | blue | D | 100% D |
| combined | hn | green | D | Hint falls back within D-only set |
| combined | unknown-zone | blue | A/B/D | Zone falls back to all, then hint `blue` |

**Note:** in modes without the hint supplier, having the controller forward `X-SC-LB-Hint` to the backend does not alter routing. Likewise, `weighted` mode does not automatically consider `spring.cloud.loadbalancer.zone`. Never infer from "property is set" that "policy is active"; **the supplier chain must include the matching decorator**.

## 16. Automated Testing with PowerShell

The lab can run smoke tests without adding another test framework. Prerequisites: all four backends running, caller started in the intended mode, and no external traffic skewing the counts.

### 16.1. Sampling Functions

~~~powershell
function Get-RoutingSamples {
    param(
        [int]$Count = 100,
        [string]$Hint = ""
    )

    $url = "http://localhost:8080/route"
    if ($Hint -ne "") {
        $url += "?hint=$([uri]::EscapeDataString($Hint))"
    }

    $samples = @(
        1..$Count | ForEach-Object {
            Invoke-RestMethod -Uri $url -TimeoutSec 5
        }
    )

    return $samples
}

function Show-RoutingDistribution {
    param([object[]]$Samples)

    $total = $Samples.Count
    $Samples | Group-Object -Property instanceId |
        Sort-Object Name |
        Select-Object Name,Count,
            @{Name="Percent"; Expression={
                [math]::Round(
                    100.0 * $_.Count / $total, 2
                )
            }}
}
~~~

Usage in `combined` mode:

~~~powershell
$samples = @(Get-RoutingSamples -Count 400 -Hint blue)
Show-RoutingDistribution -Samples $samples
~~~

Then assert the **qualitative** check: only IDs A or B appear. Do not require an exact 300/100 split in a single sample when implementation and retry details may vary.

### 16.2. Assertion for Hint Green

~~~powershell
$green = @(Get-RoutingSamples -Count 30 -Hint green)

$invalid = @(
    $green | Where-Object {
        $_.instanceId -ne "hcm-green-c"
    }
)

if ($invalid.Count -gt 0) {
    throw "Combined green routing selected an unexpected instance"
}

"PASS: All green requests selected hcm-green-c"
~~~

This test applies when `combined` mode runs with `spring.cloud.loadbalancer.zone=hcm`, all backends up, and no conflicting policies. If `zone=hn`, returning D is valid under soft fallback, so that assertion would no longer apply.

### 16.3. Assertion Against Cross-Zone Calls When Local Candidates Exist

~~~powershell
$zoneResults = @(Get-RoutingSamples -Count 60)

$crossZone = @(
    $zoneResults | Where-Object {
        $_.zone -ne "hcm"
    }
)

if ($crossZone.Count -ne 0) {
    throw "Zone preference returned a cross-zone backend"
}
~~~

Run this assertion in `zone` or `combined` mode with zone `hcm`. Under `weighted` or `hint` mode, this condition **is not part of the contract**, and the test can fail even when the supplier works as designed.

### 16.4. Sample Size and False Positives

For random or weighted distributions, use sufficiently large samples. Instead of requiring exact percentages, choose acceptable tolerances and statistical rules before running.

If each request were independent with target probability `p`, expectation would be `Np` and standard deviation `sqrt(Np(1-p))`. However, `WeightedServiceInstanceListSupplier` paired with Round Robin does not necessarily behave like independent Bernoulli trials; logical list construction and snapshot changes can make the distribution more deterministic. **Do not treat a binomial test as absolute proof when the implementation does not satisfy independence assumptions.**

In CI, prefer:

- Asserting **zero selections outside the eligible set** over a moderate number of calls.
- Testing the filtered list in unit/component tests.
- Checking **weight trends** with a reasonably large sample or inspecting the supplier's logical weighted list rather than hard-coding per-request order.
- Logging instance counts, mode, zone, hint, and Spring Cloud version on test failure.

## 17. Unit Testing Metadata Models and Policies

HTTP integration tests prove where requests went. Prior to that, fake `ServiceInstance` objects let you unit test the exact metadata used by policies. `DefaultServiceInstance` supports attaching metadata just like a registry:

~~~java
import org.springframework.cloud.client.DefaultServiceInstance;

DefaultServiceInstance instance = new DefaultServiceInstance(
        "hcm-blue-a",
        "inventory-service",
        "localhost",
        8081,
        false
);

instance.getMetadata().put("zone", "hcm");
instance.getMetadata().put("hint", "blue");
instance.getMetadata().put("weight", "3");
~~~

Unit/component test cases for suppliers:

1. **Zone matching:** list A/B/C/D → caller zone `hcm` yields A/B/C.
2. **Zone no match:** caller zone `unknown` → yields A/B/C/D per default fallback.
3. **Hint blue:** list A/B/C/D → A/B/D when context carries hint header `blue`.
4. **Hint unknown:** list A/B/C/D → keeps full delegate list.
5. **Combined blue:** after zone `hcm` → A/B; weighted logic reflects 3:1.
6. **Combined green:** only C remains.
7. **Weight missing:** falls back per `WeightedServiceInstanceListSupplier` defaults.
8. **Empty discovery:** zero instances → LoadBalancer returns no-instance response instead of inventing a backend.
9. **Request context:** invoke `supplier.get(request)`, not only `supplier.get()`, because the hint lives in the request.
10. **Scope:** configuration for `inventory-service` does not leak onto `payment-service`.

**Critical detail:** a test calling only `supplier.get()` cannot verify per-request hints, because `HintBasedServiceInstanceListSupplier` reads `RequestDataContext` or the matching hint context via `get(request)`. Use a real transport request context or build the exact fixture type supported by your release train, rather than passing an empty `DefaultRequest` and concluding the hint header was ignored.

Using `StepVerifier` and `ServiceInstanceListSuppliers.toProvider(...)`, you can verify reactive outputs without starting a web server. That is a unit/component test and **does not replace** end-to-end tests through `@LoadBalanced WebClient`.

## 18. Failure Scenario: One Replica Stops Running

With the caller in `combined` mode, zone `hcm`, and hint `blue`, the initial candidate set is A/B. Stop backend A on port 8081 while keeping static discovery configuration unchanged.

~~~text
Before incident:
  A :8081 (running), B :8082 (running)

After incident:
  A :8081 (stopped), B :8082 (running)

Caller's SimpleDiscoveryClient:
  STILL CONTAINS A and B in the list
~~~

At this point, the caller can still select A and hit connection refused/timeout. **Do not conclude LoadBalancer automatically shifts all traffic to B** without a mechanism to evict A from the candidate list or an appropriate retry policy.

To observe:

~~~powershell
1..12 | ForEach-Object {
    try {
        Invoke-RestMethod "http://localhost:8080/route?hint=blue"
    }
    catch {
        Write-Host ("Request failed: " + $_.Exception.Message)
    }
}
~~~

This is an intentional failure test; failure rates depend on how the weighted list generates selections, connection state, and timeouts. Restart backend A after measuring, or edit the caller's discovery list and **restart** to simulate deregistration.

### Filtering Unhealthy Instances

Spring Cloud provides `HealthCheckServiceInstanceListSupplier`. To add it in an advanced step, you need:

- A health endpoint on each backend, typically `/actuator/health` with Actuator enabled.
- A health-check supplier positioned near discovery in the chain.
- Appropriate HTTP client/health-check request factory resources.
- Clear refresh/refetch intervals; with static `SimpleDiscoveryClient`, understand when the supplier refreshes its list.

Spring Cloud docs note that the health-check supplier can **return the original list when zero instances are healthy** under its default policy. Therefore, if "never call an unhealthy instance" is a hard constraint, test and consider a dedicated fail-closed policy.

### Testing Zone Fallback When an Entire Zone Is Down

If A/B/C are all stopped, `SimpleDiscoveryClient` still lists them. `ZonePreference` for `hcm` still sees `hcm` metadata and **does not automatically fall back to D** simply because connections failed. Only when the input list **contains zero `hcm` candidates** (e.g., registry deregistration or health filtering updates) does `ZonePreferenceServiceInstanceListSupplier` fall back to other candidates.

This is the difference between:

- **No same-zone instances in the candidate list** → zone preference falls back.
- **Same-zone instances still in the candidate list, yet HTTP fails** → no automatic zone fallback; requires retry, health filtering, or discovery updates.

## 19. Changing Weights at Runtime

Suppose you want to reduce A's load from weight 3 to 1. With `SimpleDiscoveryClient` in this lesson, editing metadata in the caller's YAML **does not guarantee** runtime list updates; the reliable way to re-test is updating source config and **restarting the caller**.

In a registry-backed system, the flow typically looks like:

~~~text
Instance capacity changes
    -> update metadata in registry
    -> DiscoveryClient receives new version
    -> ServiceInstanceListSupplier/cache refreshes
    -> weighted list is recomputed
    -> subsequent selections reflect new weights
~~~

If traffic ratios do not shift immediately:

- Verify `weight` metadata was published properly to the registry.
- Check cache TTLs and refresh intervals; avoid double caching.
- Verify the active mode is actually `weighted` or `combined`.
- Ensure no zone/hint filter excluded the instance whose weight changed.
- Check sample sizes and traffic from other caller instances.
- Check whether metrics track **selections** or **HTTP completions**.
- For weight 0, do not assume it acts as a drain; perform explicit removal/deregistration or filtering.

Thus, `weight` is a metadata-driven routing policy, **not an adaptive CPU autoscaler**. If you need real-time load-based weight adjustments, build a proper control loop with reliable metrics, smoothing, bounds, and oscillation guards.

## 20. Can RestClient and OpenFeign Use the Same Policies?

Yes. `ServiceInstanceListSupplier` is configured per **service ID (`inventory-service`)**. HTTP clients integrated with Spring Cloud LoadBalancer calling that service ID share its child context.

### RestClient

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}

@Bean
RestClient restInventory(
        @LoadBalanced RestClient.Builder builder) {

    return builder.clone()
            .baseUrl("http://inventory-service")
            .build();
}
~~~

Calling with a header:

~~~java
InstanceView response = restInventory.get()
        .uri("/whoami")
        .header("X-SC-LB-Hint", "blue")
        .retrieve()
        .body(InstanceView.class);
~~~

With `RestClient`, include the appropriate Spring Web and LoadBalancer dependencies, and avoid registering **two HTTP client builder beans with ambiguous names/qualifiers** if combining with `WebClient` in the same app. Hint-based filtering depends on the request context passed by the integration into `ServiceInstanceListSupplier.get(request)`; test actual behavior rather than assuming header arrival at the backend proves filtering worked.

### OpenFeign

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/whoami")
    InstanceView whoami(
            @RequestHeader("X-SC-LB-Hint") String hint);
}
~~~

With OpenFeign, add `spring-cloud-starter-openfeign`, enable `@EnableFeignClients`, and omit any static `url` to route via service ID. `@RequestHeader` forwards the hint; whether the LB supplier **receives the request-specific hint** must be verified on your actual version and transport integration. If the request context fails to carry the header to `HintBasedServiceInstanceListSupplier`, the backend still receives the header while hint filtering silently does not happen: in that case, configure an appropriate adapter/policy rather than assuming hint routing worked.

### What Is Not LoadBalancer's Responsibility?

- Authentication/authorization: a hint header does not prove a user may access a version group or zone.
- Connect/read timeouts: managed by the HTTP client/transport.
- Retry/backoff: requires independent configuration and bounds.
- Circuit breaking: decides when to stop calling a slow/failing dependency, not which hint to pick.
- Trace propagation: handled by Micrometer/OpenTelemetry instrumentation.
- Health: requires discovery/health-check suppliers to drop unhealthy instances.


## 21. Observing Selections, HTTP Attempts, and Metrics

Distinguish **one logical request**, **one instance selection**, and **one HTTP attempt**. When retries are enabled, these numbers diverge:

~~~text
1 logical request
  -> LoadBalancer selection #1: A
  -> HTTP attempt #1: connect refused
  -> retry (if enabled and budget remains)
  -> LoadBalancer selection #2: B
  -> HTTP attempt #2: HTTP 200

Logical requests: 1
Selections:       2
HTTP attempts:    2
Responses:        1
~~~

This lab sets `spring.cloud.loadbalancer.retry.enabled=false` for simplicity, yet if retries are enabled in `WebClient`, a gateway, or the HTTP transport, count each layer separately.

Spring Cloud provides `MicrometerStatsLoadBalancerLifecycle` when a `MeterRegistry` is present and stats are enabled:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Documented meters include:

| Meter | Meaning |
|---|---|
| `loadbalancer.requests.active` | Gauge of currently active requests |
| `loadbalancer.requests.success` | Timer for requests succeeding at the transport/load-balancer lifecycle level |
| `loadbalancer.requests.failed` | Timer for requests failing with an exception |
| `loadbalancer.requests.discard` | Counter when no instance could be obtained to send |

Exact names and tags depend on your Spring Cloud release train and metrics registry. These meters **do not automatically expose a "hint matched" tag**; to verify filter eligibility, use unit/component tests, scoped debug logs, or a custom `LoadBalancerLifecycle`.

Never attach raw tenant/user IDs, correlation IDs, tokens, or URIs containing dynamic SKUs as unbounded-cardinality metric labels.

Cross-check across layers:

- **Caller:** mode, zone, validated hint, logical requests, status, and latency.
- **LoadBalancer:** selection count, selected instance ID, no-instance events, selection errors.
- **Backend:** instance ID/port, received hint, status, and latency.
- **Retries:** HTTP attempt count independent of logical request count.

An HTTP 200 response does not prove **the intended routing policy ran**. For instance, `hint=unknown` fallback can still return 200 even with zero metadata matches.

## 22. When Must Zone and Hint Be Replaced by Hard Filters?

**Soft preference** fits availability-oriented goals: if no same-zone or matching-hint instance exists, calling another candidate is acceptable. That is the default behavior of the suppliers used in this lesson.

**Hard isolation** is required when:

- Data may only be processed inside a specific legal jurisdiction.
- Canary version v2 must never hit backend v1 due to incompatible contracts.
- A workload may only reach a dedicated, authorized instance pool.
- A tenant requires strict data partitioning or compliance guarantees.

In these cases, do not rely on default zone/hint suppliers. Use a supplier with **mandatory predicates** that returns empty/no-instance when nothing matches instead of falling back to the full list:

~~~text
policy = resolveTrustedPolicy(authentication, deploymentConfig)
candidates = discoverySupplier.get(request)

eligible = candidates
    .filter(instance.zone == policy.requiredZone)
    .filter(instance.version == policy.requiredVersion)
    .filter(instance.allowedForWorkload)

if eligible.isEmpty():
    return EmptyResponse

return chooseWithWeight(eligible)
~~~

This is **pseudo-code**, not a complete Java implementation. When implementing:

1. Derive required zone/version from an **authenticated** source, never trusting raw `X-SC-LB-Hint` headers supplied by Internet users.
2. Never cross zones or versions against policy when the eligible set is empty.
3. Propagate no-instance errors cleanly; never fabricate fake `ServiceInstance` entries.
4. Still enforce authentication and authorization on the backend; routing never replaces security.
5. Separately test access control, malformed metadata, empty registry responses, retries, and fallbacks.
6. Ensure `ServiceInstance.getMetadata()` comes from a trusted, managed registry rather than user-controlled request inputs.

## 23. Cost and Limits of the Supplier Chain

| Layer | Work Performed | What to Watch |
|---|---|---|
| Discovery | Fetches candidate list | Registry latency, consistency, refresh |
| Caching | Stores snapshot to avoid hammering registry | TTL, stale values, cache placement |
| Zone preference | Filters list by zone metadata | O(n) over evaluated list |
| Hint filtering | Filters by request hint | O(n), request-aware context |
| Weighted supplier | Reads weights, builds weighted logical list | Memory/CPU and weight refresh |
| Round Robin | Picks an index from the list | Typically O(1) in n |
| HTTP transport | Connect, TLS, request, response | Pool wait, timeouts, p95/p99 |

Big-O estimates represent standard models, not measured benchmarks. With four instances, filter cost is negligible relative to HTTP latency. As you scale to hundreds of instances and many caller replicas:

- Place caching after discovery retrieval if needed, avoiding accidentally caching per-request filtered results.
- Bound metric label cardinality.
- Do not generate random per-call weights if stable traffic shares are the goal.
- Do not stack multiple retry layers when a zone outage drives high load onto remaining backends.
- Measure p95/p99 latency and error rates, not just traffic percentages.
- Maintain a rollback plan to a simpler policy if distribution creates hotspots.

Weighting is not autoscaling: a high-weight replica does not automatically stay low on CPU or absorb unbounded multiples of traffic.

## 24. Troubleshooting Table

| Symptom | Common Cause | How to Check |
|---|---|---|
| `UnknownHostException: inventory-service` | `WebClient` lacks LoadBalancer filter or starter missing | `@LoadBalanced` bean and dependencies |
| Always selects one replica | Only one candidate left after filtering or wrong mode | Mode, zone, hint, supplier chain |
| Caller in zone `hcm` yet picks D | Zone not applied, missing metadata, or zone fallback | `spring.cloud.loadbalancer.zone` and instance metadata |
| Hint `blue` yet picks C | Header never reached request context or hint supplier not active | `withHints()`, `get(request)`, integration wiring |
| Hint `unknown` still succeeds | `HintBased` falls back to delegate list | Expected behavior, not strict matching |
| Zone `unknown` picks A/B/C/D | `ZonePreference` falls back to full list | Use a hard filter if cross-zone is disallowed |
| Weighted splits nearly 25% each | Wrong mode or `weight` metadata not read | `weighted` mode and metadata source |
| Weight 0 still receives traffic | Invalid/non-positive weight may fall back to default | Use deregistration/health checks to drain |
| Combined `blue` picks D | Zone not applied or input fallback occurred | Metadata, zone, chain order |
| Backend logs `receivedHint=blue` yet routing is wrong | Header on the wire does not prove supplier received context | Inspect `RequestDataContext` and client integration |
| Edited YAML weights yet distribution unchanged | Static `SimpleDiscoveryClient`, old cache, or missing restart | Restart caller or check registry/cache refresh |
| Stopped A yet still calls A | Discovery list has not dropped A | Health/discovery, retry budget, and timeouts |
| HTTP 200 yet wrong version group | Soft hint fallback | Use strict version routing |
| Feign bypasses LoadBalancer | Static Feign `url` or missing integration | `@FeignClient(name)`/`url` |
| No metrics visible | Missing `MeterRegistry`/Actuator or no requests sent yet | Dependencies, flags, and endpoints |
| Backend request counts differ from selection counts | Retries or pre-backend connect errors | Count logical, selection, and attempt metrics separately |

Diagnostic sequence: confirm all four backends are running → inspect discovery list/metadata in the caller → confirm mode and supplier bean → verify zone/hint context → inspect weighted list → check HTTP errors/retries. Never modify Round Robin before knowing **the final candidate list**.

## 25. Advanced Exercises

**Exercise 1 — Change caller zone:** run `combined` in `hn`, send hint `green`, and explain why D is still selected.

**Exercise 2 — Change weights:** update A:B:C:D to 1:3:2:4, restart the caller, and re-measure `weighted` mode. Report shares across three sampling runs and their variance.

**Exercise 3 — Strict hint:** write a custom decorator that does not fall back to the full list when no match exists. Expect an unknown hint to produce no-instance instead of hitting an arbitrary backend.

**Exercise 4 — Dead backend:** stop A and enable a health supplier or registry with deregistration. Measure how long it takes A to disappear from the candidate list and when A is selected again after recovery.

**Exercise 5 — RestClient/OpenFeign:** reuse the same per-service supplier configuration, send hint `blue`, and verify whether the request context actually reaches the supplier in your version.

**Exercise 6 — Canary:** combine `stable`/`canary` metadata with a trusted rollout policy; explain why soft hints are insufficient when two versions have incompatible schemas.

**Exercise 7 — Two caller replicas:** run callers on 8080 and 8090 and measure counts independently. Each caller's Round Robin cursor is independent; cluster-wide traffic need not alternate globally.

**Exercise 8 — Tail latency:** simulate fast/slow backends and compare p95/p99 across `zone`, `weighted`, and `combined`. Evaluate traffic distribution alongside capacity instead of judging solely by raw request counts.

## 26. Acceptance Criteria

| Item | PASS Condition |
|---|---|
| Backend | Four ports 8081–8084 return matching `instanceId` and echoed metadata |
| Discovery | Caller sees four `ServiceInstance` entries with matching metadata |
| Zone | With `hcm` and A/B/C up, `zone` mode never selects D |
| Weight | `weighted` mode applies metadata and trends toward 3:1:2:4 |
| Hint blue | `hint` mode picks among A/B/D |
| Hint green | `hint` mode picks only C |
| Combined blue | `hcm` → A/B, target ratio 3:1 |
| Combined green | `hcm` → C |
| No hint | `hint` mode does not filter; `combined` + `hcm` keeps A/B/C |
| Unknown hint | Falls back to delegate list as expected, not mistaken for hard match |
| Unknown zone | Zone fallback to full list observed and explained |
| Backend down | Stale discovery and health/retry limits understood |
| Security | Soft zone/hint never used in place of authentication/authorization |
| Metrics | Logical requests, selections, and HTTP attempts distinguished |
| Code scope | Configuration applies exclusively to `inventory-service` |

Completing the lab does not require **exact mathematical** weighted ratios over a short window. Acceptance checks membership, proportional trends, and missing-instance behavior together.

## 27. Pre-Production Checklist

- [ ] Zone/hint/weight metadata comes from a trusted registry with clear update policies.
- [ ] Caller zone accurately reflects topology; cross-zone fallback is approved.
- [ ] Soft preference is clearly separated from hard isolation.
- [ ] Hints originate only from trusted routing decisions; user input is validated.
- [ ] Per-service `@LoadBalancerClient` config is not globally component-scanned.
- [ ] `weight=0` is never used as a replica off-switch without verifying implementation behavior.
- [ ] Cache/health suppliers are ordered properly without leaking hint context across requests.
- [ ] Tested with the actual HTTP client used in deployment (`WebClient`/`RestClient`/OpenFeign).
- [ ] Appropriate timeouts, bounded retries, circuit breakers, and idempotency are in place.
- [ ] Plans exist for zone outages, dead instances, and stale metadata.
- [ ] Metrics have bounded cardinality and never log tokens or sensitive user data.
- [ ] Load tests confirm p95/p99, error rate, and capacity do not degrade under the new policy.
- [ ] A rollback path to a simpler policy exists if distribution creates hotspots.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ZonePreferenceServiceInstanceListSupplier`, `WeightedServiceInstanceListSupplier`, `HintBasedServiceInstanceListSupplier`, and metrics.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `SimpleDiscoveryClient` and instance configuration.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): zone, hint headers, caching/retry, and statistics.
- [Spring Cloud — Project and Version Compatibility](https://spring.io/projects/spring-cloud/): selecting a release train compatible with Spring Boot.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request headers and reactive HTTP.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): calling by service ID and Feign integration.

**Conclusion:** zone, weight, and hint are three policies with **distinct purposes**, yet they compose cleanly in `ServiceInstanceListSupplier` ahead of the Round Robin selector. Zone prefers nearby instances, weight adjusts shares by capacity, and hint prefers a replica group per request. Most importantly, **default zone and hint policies are preferences with fallbacks**, not security boundaries. Validate each mode independently, verify composition order, inspect the final candidate set, review statistics, and test failure modes before deploying to production.
