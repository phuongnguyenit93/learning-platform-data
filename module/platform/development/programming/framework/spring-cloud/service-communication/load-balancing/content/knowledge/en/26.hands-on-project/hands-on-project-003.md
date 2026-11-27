# Comparing Round-Robin and Random Over a Sufficiently Large Request Set

In Spring Cloud LoadBalancer, both **RoundRobinLoadBalancer** and **RandomLoadBalancer** select a **ServiceInstance** from the provided list of replicas. The difference does not lie in how the HTTP request is constructed, but in the **replica selection rule**. With too few requests, an observer might think random is "biased" or round-robin is "uneven" if they accidentally count responses by completion order, enable retries, mutate the instance list, or use multiple callers. Therefore, we need a hands-on exercise with **a sufficiently large request set, clear controlled conditions, and appropriate statistical methods**.

This lesson belongs to the **Hands-On Project** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will set up **three Inventory Service instances**, one **Order Caller** using **@LoadBalanced RestClient**, retrieve the instance list via **SimpleDiscoveryClient**, run round-robin and random sequentially, send **6,000–30,000 HTTP requests**, collect distributions, measure deviation and latency, and examine scenarios when concurrency/retry/health change.

Key learning outcomes after completing this lab:

1. Independently configure **RoundRobinLoadBalancer** and **RandomLoadBalancer** for the same service ID.
2. Distinguish between **ServiceInstance selection**, **HTTP attempt**, **successful response**, and **response completion order**.
3. Use count tables, shares, relative gap, **Jain's fairness index**, and **chi-square** to interpret the data.
4. Understand why a large N makes observing random more reliable, yet **does not force random to split strictly evenly**.
5. Understand how **discovery, health, cache, zone, retry, timeout, connection pool**, and concurrency affect results.
6. Be able to repeat measurements and write **conditional** conclusions rather than claiming one algorithm is "always faster" from a single run.

> **Scope of this lesson:** The Java/Gradle/YAML snippets are lab templates for learners to implement in their own practice repository. The Knowledge worker only writes this Markdown document, does not create source files, and does not run Gradle/tests. Choose a compatible Spring Boot and Spring Cloud release train according to your environment's BOM; do not arbitrarily mix Spring Boot 3.x/4.x versions with Spring Cloud.

## 1. Research Question and Hypotheses

Suppose **inventory-service** has three identical replicas:

| Instance | Host:port | API | Assumed Capacity |
| --- | --- | --- | --- |
| inventory-a | 127.0.0.1:8091 | GET /whoami | Equal |
| inventory-b | 127.0.0.1:8092 | GET /whoami | Equal |
| inventory-c | 127.0.0.1:8093 | GET /whoami | Equal |

The caller sends:

~~~http
GET http://inventory-service/whoami
~~~

All three replicas return JSON containing **instanceId** so we know which one **actually received the request**:

~~~json
{"instanceId":"inventory-b"}
~~~

We formulate two hypotheses to observe:

| Algorithm | Hypothesis for Large N, Fixed List, No Retry |
| --- | --- |
| **Round Robin** | Cycles through positions in the list; **selection** counts per instance are nearly equal (differing by at most 1 for a sequential selection stream on an unchanged list) |
| **Random** | Each selection is independently close to uniform over the same list; counts per instance **fluctuate randomly**, with shares approaching 1/3 as N grows |

Do not replace the hypothesis with "round-robin always has lower latency." When backends differ in performance, network/HTTP pools behave differently, and the environment is under load, latency depends on many factors beyond the selection algorithm.

### 1.1. "Even" Has Two Meanings

**Even by hit count**: A/B/C are selected roughly 1/3 of the time.

**Even by actual load**: CPU, processing time, in-flight request count, bytes transferred, database queries, and queue depth across A/B/C are roughly equal.

Round-robin can achieve **evenness by hit count** without necessarily achieving **evenness by load**. If A takes 200 ms while B takes only 20 ms, the number of concurrent in-flight requests on A can be much higher even though hit counts are equal. This first lesson compares **request-count distribution** first, then examines latency and confounding factors.

## 2. Lab Architecture

~~~mermaid
flowchart LR
    T["Lab Runner"] --> O["Order Caller :8080"]
    O --> LB["Spring Cloud LoadBalancer"]
    D["SimpleDiscoveryClient\ninventory-service → A,B,C"] --> LB
    LB --> A["Inventory A :8091"]
    LB --> B["Inventory B :8092"]
    LB --> C["Inventory C :8093"]
    A --> M["JSON instanceId"]
    B --> M
    C --> M
    M --> O
    O --> R["Aggregate counts, shares,\nlatency, errors"]
~~~

We run both modes **on the same topology**:

~~~text
Experiment 1:
  algorithm = round-robin
  fixed service instance list = [A, B, C]
  N = 6000

Experiment 2:
  algorithm = random
  fixed service instance list = [A, B, C]
  N = 6000
~~~

### 2.1. Variables That Must Remain Fixed

| Control Variable | Configuration |
| --- | --- |
| Service ID | inventory-service |
| Instance list | A/B/C, kept unchanged during a run |
| API and response | GET /whoami, identical JSON schema |
| Algorithm | Only toggle **round-robin** ↔ **random** |
| HTTP client | Same RestClient/request factory |
| Retry | Disabled so **one logical request = one HTTP attempt** |
| Health filter/zone/hint | Do not add policies that alter the A/B/C list in the baseline phase |
| N | Equal across both modes, e.g., 6,000 |
| Concurrency | Initially **sequential, single caller** |
| Warm-up | Fixed count excluded from N |
| Backend errors | Expected 0 in baseline phase |
| Timeout | Same configuration, large enough to avoid hanging indefinitely |

**Why does this matter?** If Round Robin runs with two instances while Random runs with three, the comparison is no longer about the algorithm. If retries are enabled on one arm, you are comparing **two retry + LoadBalancer policies**, not just two selectors.

### 2.2. Scope of a Single LoadBalancer

Spring Cloud LoadBalancer creates a **child ApplicationContext per service ID**. A `RoundRobinLoadBalancer` for `inventory-service` maintains its selection state only inside **that caller process/context**. When running **multiple caller pods**, each pod has its own counter/cycle; they **do not automatically synchronize a cluster-wide selection index**.

Therefore, the statement "6,000 requests split 2,000–2,000–2,000" only holds under the model of **one active round-robin selector, a fixed three-element list, no retries, and counting sequential selections**. Do not generalize this to arbitrary distributed traffic models.

## 3. Probability Model and Expectations

Let:

- \(N\): total number of **valid** selections or attempts to analyze.
- \(k\): number of `ServiceInstance` entries with equal selection chance.
- \(n_i\): number of hits assigned to instance \(i\), with \(\sum_{i=1}^{k}n_i=N\).
- \(p_i=n_i/N\): observed share of instance \(i\).
- \(E=N/k\): expected count per instance under a uniform selection policy.

### 3.1. Ideal Round-Robin

For a cyclic selection sequence over a **constant set of k instances**, the count per instance after N selections can only be:

\[
n_i\in\left\{\left\lfloor\frac{N}{k}\right\rfloor,\left\lceil\frac{N}{k}\right\rceil\right\}
\]

If **N is divisible by k**, every instance receives exactly \(N/k\) selections. If not divisible, the maximum count difference is **1 selection**, though which instance gets the extra hit depends on the starting position of the counter.

Example with 3 instances:

~~~text
N = 12
A B C | A B C | A B C | A B C
=> A=4, B=4, C=4

N = 11
A B C | A B C | A B C | A B
=> A=4, B=4, C=3
~~~

Spring may start at a position other than A due to seed/initial state and prior requests; we compare **counts**, rather than asserting "the first request is always A."

### 3.2. Uniform Random Selection

When each random selection assigns probability \(1/k\) to each instance, the count for one instance is a binomial random variable (a marginal of the multinomial distribution):

\[
\operatorname{E}[n_i]=\frac{N}{k},\qquad
\operatorname{Var}(n_i)=N\frac{1}{k}\left(1-\frac{1}{k}\right)
\]

\[
\sigma_i=\sqrt{N\frac{1}{k}\left(1-\frac{1}{k}\right)}
\]

For \(N=6000,k=3\):

~~~text
Expected per instance: 6000 / 3 = 2000
Standard deviation:    sqrt(6000*(1/3)*(2/3)) ≈ 36.5 hits
Approx. ±2σ interval:  2000 ± 73 hits (approximate)
~~~

This is an approximate normal-distribution reference interval for **a single count**, not a guarantee that all instances fall inside it simultaneously. Random selection can produce larger deviations, and a single skewed run **does not prove the algorithm is buggy**.

### 3.3. Why Is a Sufficiently Large N Needed?

The typical absolute deviation of random grows roughly as \(\sqrt{N}\), whereas the **relative** deviation shrinks roughly as \(1/\sqrt{N}\).

| N | E for k=3 | Approx. Standard Deviation | One σ as % of E |
| ---: | ---: | ---: | ---: |
| 30 | 10 | 2.58 | 25.8% |
| 300 | 100 | 8.16 | 8.16% |
| 3,000 | 1,000 | 25.82 | 2.58% |
| 6,000 | 2,000 | 36.51 | 1.83% |
| 30,000 | 10,000 | 81.65 | 0.82% |

That is why a screenshot with **9 requests** and an A/B/C split of 5/2/2 cannot evaluate the fairness of random. With thousands of requests, we inspect the **distribution** and repeat across multiple runs instead of demanding "random must split strictly evenly."

## 4. Metrics to Record

Do not stop at a request-count chart; compute:

| Metric | Formula / Definition | Interpretation |
| --- | --- | --- |
| Count | \(n_i\) | Number of successful responses returned by instance i in the baseline phase |
| Share | \(100n_i/N\) (%) | Request share |
| Max-min gap | \(\max(n_i)-\min(n_i)\) | Spread of counts |
| Relative gap | \((\max n_i-\min n_i)/(N/k)\) | Spread relative to expectation |
| Jain fairness | \((\sum n_i)^2/(k\sum n_i^2)\) | Close to 1 when counts are balanced |
| Pearson chi-square | \(\sum(n_i-E)^2/E\) | Deviation from expected distribution |
| Error rate | errors / total requests | Are errors distorting the observed counts? |
| P50/P95/P99 | Response time percentiles | End-to-end performance, not purely the algorithm |
| Throughput | Successful requests / elapsed seconds | Combined result of client, network, and backend |

**Note:** Jain's index, chi-square, and shares on the same run are not three independent hypothesis tests. They all summarize a single count vector. Chi-square is only a **statistical measure** under an i.i.d. uniform random selection model; do not use it to "grade correctness" of round-robin, which is deterministic.

### 4.1. Consistent Definition of N

In the **baseline phase**, all requests succeed and retries are disabled, so:

~~~text
N logical calls = N selections = N HTTP attempts = N successful responses
~~~

When timeouts or 503s occur, this equation **no longer holds**:

~~~text
N logical calls
    <= N HTTP attempts (if retries happen)
    != N backend successes (if errors happen)
    may != N observed responses (if the client drops responses)
~~~

Do not use **counts from successful responses** as proof that selections were evenly split when an instance is dead. To measure **true selection fairness** under failure, instrument at the LoadBalancer lifecycle or HTTP attempt level rather than relying solely on backend JSON responses.

## 5. Lab Project Structure and Dependencies

Suggested layout of the two Spring Boot applications:

~~~text
loadbalancer-lab/
├─ settings.gradle
├─ inventory/
│  └─ src/main/java/lab/inventory/InventoryApplication.java
└─ caller/
   ├─ src/main/java/lab/caller/CallerApplication.java
   ├─ src/main/java/lab/caller/ExperimentController.java
   ├─ src/main/java/lab/caller/InstanceResponse.java
   ├─ src/main/java/lab/lb/InventoryLoadBalancerConfiguration.java
   └─ src/main/resources/application.yml
~~~

**This is an exercise diagram, not files created by this document.** Separate the packages so **`InventoryLoadBalancerConfiguration` sits outside the component scan of `CallerApplication`** (section 8 explains why).

Example dependencies (individual versions omitted because they are managed via compatible Spring Boot and Spring Cloud BOMs):

~~~gradle
// inventory/build.gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}

// caller/build.gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Spring Boot 3.2+ includes **RestClient**. Do not add Eureka/Consul in this phase: **SimpleDiscoveryClient** reads a fixed instance list from properties, eliminating noise from registry updates. If using Spring Boot 4.x, check web starter artifact names against the BOM and Spring Boot migration notes.

### 5.1. Why Not Run the Test Directly in Production?

6,000–30,000 back-to-back requests can:

- Saturate connection pools or spike CPU/network.
- Distort metrics and error budgets of real services.
- Increase registry/gateway/cloud egress costs.
- Trigger side-effectful endpoints.

Run in **local or an isolated test environment** with read-only GETs. Never use ordering/payment endpoints as a distribution benchmark.

## 6. Creating the Inventory Service Returning Its Replica Identifier

Each Inventory instance uses **the same application** while receiving distinct **server.port** and **lab.instance-id** values. For example:

~~~java
package lab.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class InventoryApplication {

    private final String instanceId;

    public InventoryApplication(Environment environment) {
        this.instanceId = environment.getRequiredProperty("lab.instance-id");
    }

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }

    @GetMapping(
            path = "/whoami",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public InstanceReply whoAmI() {
        return new InstanceReply(instanceId);
    }

    public record InstanceReply(String instanceId) {}
}
~~~

Response from A:

~~~json
{"instanceId":"inventory-a"}
~~~

Response from B:

~~~json
{"instanceId":"inventory-b"}
~~~

### 6.1. Why Must the ID Come from the Backend?

In the baseline phase, the caller receives the response from **the instance that actually processed the HTTP request**, rather than assuming the chosen instance from an index in `[A, B, C]`. If a request hit A while the body claimed B, measurements would be invalid; therefore each backend is started with a fixed instance ID and verified directly on its physical port.

Do not use a **client**-generated header as the sole proof of which backend received a request. You can additionally include **`X-Instance-Id` from the server itself** to cross-check, though the response body suffices in a lab when the mock server is trustworthy.

### 6.2. No Side Effects on /whoami

The GET endpoint does not write to a database, publish messages, or mutate inventory. That way, when learners run 30,000 calls, the experiment does not alter state and does not have to deal with idempotency.

## 7. Configuring the Caller and SimpleDiscoveryClient

Define **caller/src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-caller
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
              - uri: http://127.0.0.1:8093
    loadbalancer:
      retry:
        enabled: false

lab:
  algorithm: round-robin
~~~

Prerequisites:

- Caller has **spring-cloud-starter-loadbalancer**.
- No other registry-backed `DiscoveryClient` is on the classpath altering the instance source.
- All three Inventory processes are listening on their assigned ports.
- Backend URIs are fixed to eliminate discovery registration/TTL effects during the comparison phase.
- Same HTTP scheme; this lesson uses **HTTP on localhost** solely to measure algorithms, not as a production security configuration.

**Important distinction:** the host **inventory-service** in the logical URL is a **service ID**, not a DNS host to be resolved by the operating system. Spring Cloud LoadBalancer selects a `ServiceInstance` and builds the physical URI to `127.0.0.1:8091/8092/8093`.

### 7.1. Directly Verifying All Three Backends Before Using LoadBalancer

In Windows PowerShell:

~~~powershell
(Invoke-RestMethod http://127.0.0.1:8091/whoami).instanceId
(Invoke-RestMethod http://127.0.0.1:8092/whoami).instanceId
(Invoke-RestMethod http://127.0.0.1:8093/whoami).instanceId
~~~

Expected output:

~~~text
inventory-a
inventory-b
inventory-c
~~~

If A/B/C return the wrong IDs, **stop the experiment here**. Never analyze fairness from unreliable backend labels.

## 8. Switching RoundRobinLoadBalancer and RandomLoadBalancer via Property

Spring Cloud uses **RoundRobinLoadBalancer** by default; we still declare both algorithms explicitly so the experiment can toggle via **lab.algorithm**.

Define class **lab.lb.InventoryLoadBalancerConfiguration**:

~~~java
package lab.lb;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.RoundRobinLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// Do not place @Configuration in a package scanned by CallerApplication.
// This class is registered as a dedicated configuration for @LoadBalancerClient.
public class InventoryLoadBalancerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "lab",
            name = "algorithm",
            havingValue = "round-robin",
            matchIfMissing = true)
    ReactorLoadBalancer<ServiceInstance> roundRobinLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);
        return new RoundRobinLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab",
            name = "algorithm",
            havingValue = "random")
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

### 8.1. Why Read PROPERTY_NAME from the Child Context?

Spring Cloud LoadBalancer creates a **dedicated child ApplicationContext per service ID**. The value of **LoadBalancerClientFactory.PROPERTY_NAME** indicates which service the current context serves. Calling **factory.getLazyProvider(serviceId, ServiceInstanceListSupplier.class)** fetches the supplier for that specific service ID rather than mixing lists across services.

**RandomLoadBalancer** and **RoundRobinLoadBalancer** implement the same **ServiceInstance** selection contract, so we swap only the algorithm. This is the extension point documented by Spring Cloud.

### 8.2. Do Not Component-Scan Child Configuration Globally

Spring Cloud documentation warns that a class passed to **@LoadBalancerClient(configuration=...)** should **not be annotated with @Configuration**, or must reside outside the main application's component-scan scope. This example intentionally places the class in **lab.lb**, outside `CallerApplication`'s **lab.caller** package.

If the LoadBalancer configuration class for Inventory is accidentally scanned into the **parent ApplicationContext**, the custom bean can apply outside its intended scope, distorting both experiment results and other services.

### 8.3. Invalid Property Values

Values should only be:

~~~text
lab.algorithm=round-robin
lab.algorithm=random
~~~

If you mistype **lab.algorithm=randam**, neither `@ConditionalOnProperty` matches, and another default bean may be auto-configured. **Do not treat the property name echoed in the response as proof that the algorithm was selected**; use tests/logs of the bean type and distribution data to confirm.

## 9. Bootstrapping CallerApplication with @LoadBalanced RestClient

~~~java
package lab.caller;

import lab.lb.InventoryLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

**When applying in real projects:** If Spring Boot already provides a `RestClient.Builder` configured with observations, TLS, interceptors, and codecs, use the appropriate **RestClientBuilderConfigurer** so you do not lose that setup. Configure transport **connect/read timeouts**; the snippet above stays minimal so learners clearly see the LoadBalancer path.

With `RestClient`, **@LoadBalanced** marks the builder so Spring Cloud adds `ServiceInstance` selection integration. Simply using `RestClient.builder().baseUrl("http://inventory-service").build()` in an application without the LoadBalancer interceptor **will not** automatically treat `inventory-service` as a service ID.

### 9.1. Tracing a Single Request's Path

~~~text
Controller -> RestClient GET /whoami
    |
    v
Logical URI: http://inventory-service/whoami
    |
    v
BlockingLoadBalancerClient uses ReactorServiceInstanceLoadBalancer
    |
    v
Retrieves [A,B,C] from SimpleDiscoveryClient
    |
    v
RoundRobin or Random selects an instance
    |
    v
HTTP request to physical IP:port
    |
    v
Backend returns JSON instanceId
~~~

**"Reactor" in `ReactorLoadBalancer` does not turn `RestClient` into a reactive HTTP client.** Spring Cloud can use the reactive selection abstraction within a **blocking** HTTP path. The HTTP transport executed by `RestClient`/request factory remains synchronous.

## 10. Writing an Endpoint to Run N Requests and Compute Statistics

We create an internal endpoint **GET /lab/run?n=6000&warmup=30**. It:

1. Sends a fixed number of warm-up calls to avoid comparing uneven cold-connection effects.
2. Sends N HTTP calls **sequentially** using the `@LoadBalanced` `RestClient`.
3. Reads **instanceId from the response** to increment counters.
4. Counts errors separately rather than silently ignoring them.
5. Measures elapsed time with **System.nanoTime()** and computes percentiles.
6. Computes Jain's fairness and chi-square over **successful responses**, along with warnings if errors occurred.

Example **lab.caller.ExperimentController** (Java 17+):

~~~java
package lab.caller;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/lab")
public class ExperimentController {

    private static final Set<String> KNOWN = Set.of(
            "inventory-a", "inventory-b", "inventory-c");

    private final RestClient inventory;
    private final String algorithm;

    public ExperimentController(
            RestClient inventoryRestClient,
            Environment environment) {
        this.inventory = inventoryRestClient;
        this.algorithm = environment.getProperty(
                "lab.algorithm", "round-robin");
    }

    @GetMapping("/run")
    public RunReport run(
            @RequestParam(defaultValue = "6000") int n,
            @RequestParam(defaultValue = "30") int warmup) {

        if (n < 300 || n > 30_000 || warmup < 0 || warmup > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "n must be 300..30000 and warmup 0..100");
        }

        // Warm-up is excluded from N. If backends are not ready,
        // fail before starting measurement.
        for (int i = 0; i < warmup; i++) {
            InstanceReply reply = callInventory();
            requireKnownInstance(reply);
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("inventory-a", 0);
        counts.put("inventory-b", 0);
        counts.put("inventory-c", 0);

        Map<String, Integer> errorsByType = new TreeMap<>();
        List<Long> successLatenciesNanos = new ArrayList<>(n);
        int failed = 0;
        long wallStart = System.nanoTime();

        for (int i = 0; i < n; i++) {
            long oneStart = System.nanoTime();
            try {
                InstanceReply reply = callInventory();
                requireKnownInstance(reply);

                counts.merge(reply.instanceId(), 1, Integer::sum);
                successLatenciesNanos.add(
                        System.nanoTime() - oneStart);
            } catch (RuntimeException exception) {
                failed++;
                errorsByType.merge(
                        exception.getClass().getSimpleName(),
                        1, Integer::sum);
            }
        }

        double elapsedSeconds =
                (System.nanoTime() - wallStart) / 1_000_000_000.0;
        int succeeded = n - failed;
        double sumSquares = 0;
        int minimum = Integer.MAX_VALUE;
        int maximum = 0;

        for (int count : counts.values()) {
            sumSquares += (double) count * count;
            minimum = Math.min(minimum, count);
            maximum = Math.max(maximum, count);
        }

        double expected = succeeded / (double) counts.size();
        double chiSquare = 0;
        if (expected > 0) {
            for (int count : counts.values()) {
                double deviation = count - expected;
                chiSquare += deviation * deviation / expected;
            }
        }

        double jain = sumSquares > 0
                ? (double) succeeded * succeeded /
                        (counts.size() * sumSquares)
                : 0.0;
        double relativeGapPercent = expected > 0
                ? (maximum - minimum) / expected * 100.0
                : 0.0;

        successLatenciesNanos.sort(Long::compareTo);

        return new RunReport(
                algorithm, n, warmup, succeeded, failed,
                counts, errorsByType,
                jain, chiSquare, relativeGapPercent,
                percentileMs(successLatenciesNanos, 0.50),
                percentileMs(successLatenciesNanos, 0.95),
                percentileMs(successLatenciesNanos, 0.99),
                elapsedSeconds,
                elapsedSeconds > 0
                        ? succeeded / elapsedSeconds : 0.0);
    }

    private InstanceReply callInventory() {
        return inventory.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceReply.class);
    }

    private static void requireKnownInstance(InstanceReply reply) {
        if (reply == null ||
                !KNOWN.contains(reply.instanceId())) {
            throw new IllegalStateException(
                    "Missing or unknown backend instance");
        }
    }

    private static double percentileMs(
            List<Long> sortedNanos, double fraction) {
        if (sortedNanos.isEmpty()) {
            return 0.0;
        }
        int index = (int) Math.ceil(
                sortedNanos.size() * fraction) - 1;
        index = Math.max(0, Math.min(
                index, sortedNanos.size() - 1));
        return sortedNanos.get(index) / 1_000_000.0;
    }

    public record InstanceReply(String instanceId) {}

    public record RunReport(
            String algorithm,
            int requested,
            int warmup,
            int succeeded,
            int failed,
            Map<String, Integer> counts,
            Map<String, Integer> errorsByType,
            double jainFairness,
            double chiSquare,
            double relativeGapPercent,
            double p50Ms,
            double p95Ms,
            double p99Ms,
            double elapsedSeconds,
            double throughputPerSecond) {}
}
~~~

### 10.1. Essential Points Before Using the Results

- **RunReport.counts** counts backends in **successful responses**, not directly LoadBalancer's `choose()` counter. Only when `failed=0`, retries are off, and all bodies are valid can you infer one successful request equals one selection.
- **p50/p95/p99** measure only **successful** requests, excluding latencies of failed attempts. Always inspect **failed/errorsByType** before comparing latencies.
- **relativeGapPercent** uses \(N_{\text{success}}/3\) as denominator; when errors occur, this metric reflects **success distribution**, not true instance-selection probability.
- Warm-up requests affect the Round Robin counter position, connection pools, and JIT; **they must not be added to N**, though the warm-up count of each run should be recorded.
- **elapsedSeconds** is the total time to send N **sequential** requests. Throughput in this run is bounded by network + backend + JSON decode + caller thread, not LoadBalancer's peak capacity.
- **jainFairness=1** reflects equal counts; it does not guarantee equal latency, CPU, or availability.

### 10.2. This Is an Experiment Endpoint, Not a Public API

A request to **/lab/run?n=30000** can hold a server thread for a long time and fire thousands of outbound HTTP requests. **Enable it only in isolated environments**; if it must remain in a test cluster, enforce authentication, timeouts, and rate limits, and never let end users invoke it arbitrarily.

With Spring MVC, a synchronous method running a large N holds a request thread. In real projects you might use a separate CLI runner, but this section intentionally uses an HTTP endpoint for convenience and immediate JSON output.

## 11. Running the A/B Experiment with the Same Procedure

First complete **settings.gradle** to declare the two subprojects:

~~~gradle
rootProject.name = "loadbalancer-lab"
include("inventory", "caller")
~~~

Plugin versions and the Spring Cloud BOM must be configured in the project's **build.gradle** according to your chosen version pair. The snippets in section 5 only illustrate dependencies; they are not runnable build scripts without plugins/repositories/BOM declarations.

### 11.1. Starting the Three Backends in Three Different Terminals

In Windows PowerShell, from the root folder of the lab project:

~~~powershell
# Terminal 1
.\gradlew.bat :inventory:bootRun --args="--server.port=8091 --lab.instance-id=inventory-a"

# Terminal 2
.\gradlew.bat :inventory:bootRun --args="--server.port=8092 --lab.instance-id=inventory-b"

# Terminal 3
.\gradlew.bat :inventory:bootRun --args="--server.port=8093 --lab.instance-id=inventory-c"
~~~

Each command is a **long-running process**; do not run all three sequentially in one terminal and expect them to stay up concurrently. After all three are ready, check `/whoami` on each port as in section 7.1.

### 11.2. Running the Caller with Round-Robin

Terminal 4:

~~~powershell
.\gradlew.bat :caller:bootRun --args="--lab.algorithm=round-robin"
~~~

Terminal 5:

~~~powershell
$rr = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
$rr | ConvertTo-Json -Depth 5
~~~

Save the JSON response to your experiment report. Verify **failed=0**, every instance has a positive count, and the sum of counts equals 6000.

### 11.3. Running the Caller with Random

**Stop the round-robin caller** first. Keep the same three Inventory backends and dataset, then start a fresh caller:

~~~powershell
.\gradlew.bat :caller:bootRun --args="--lab.algorithm=random"
~~~

Execute:

~~~powershell
$random = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
$random | ConvertTo-Json -Depth 5
~~~

Do not change the instance list, server response logic, or HTTP engine between the two runs. **Restart the caller** to guarantee the algorithm and child ApplicationContext are recreated with the new property; do not merely edit `application.yml` while the process is running.

### 11.4. Pre-Conclusion Verification Checks

~~~text
[ ] All three backends return the right ID and HTTP 200.
[ ] Caller was restarted with the intended algorithm.
[ ] Total requested = 6000, failed = 0.
[ ] Sum of counts A+B+C = succeeded.
[ ] Warm-up was identical across both modes.
[ ] No other traffic called inventory-service during measurement.
[ ] LB retry/Feign retry/gateway retry are all off.
[ ] No zone/health/hint/weighted filter altered the candidate set.
[ ] Did not confuse response completion order with selection order.
~~~

If **failed > 0**, do not adjust counts by "evenly splitting errors" across instances; investigate the errors first or rerun once all backends are stable.

## 12. Reading the Results: Round-Robin Nearly Exact, Random Fluctuates

A **hypothetical illustrative example** for N=6000, k=3, zero errors:

| Algorithm | inventory-a | inventory-b | inventory-c | Total |
| --- | ---: | ---: | ---: | ---: |
| Round Robin | 2,000 | 2,000 | 2,000 | 6,000 |
| Random, run 1 | 1,987 | 2,050 | 1,963 | 6,000 |
| Random, run 2 | 2,034 | 1,981 | 1,985 | 6,000 |

The random rows here are **illustrative figures**, not actual project run output. In practice, learners must use counts from their live endpoint; never force results to match this table.

### 12.1. Converting Counts to Shares

For Random run 1:

| Instance | Count | Share |
| --- | ---: | ---: |
| A | 1,987 | 33.12% |
| B | 2,050 | 34.17% |
| C | 1,963 | 32.72% |
| **Total** | **6,000** | **100%** |

The ideal share is **33.33%**, but random is expected to fluctuate around that figure. This is natural statistical variation of random draws, not necessarily a sign that an instance is faulty.

### 12.2. Computing Max-Min Gap and Relative Gap

Example from Random run 1:

\[
\operatorname{gap}=2050-1963=87
\]

\[
\operatorname{relativeGap}=\frac{87}{2000}\times100\%=4.35\%
\]

Round Robin has **gap=0** when N=6000 is divisible by 3 and the instance set is stable. When N is not divisible by 3, the maximum gap is 1 selection in a simple round-robin sequence.

### 12.3. Jain's Fairness Index

\[
J=\frac{(\sum_{i=1}^{k}n_i)^2}
{k\sum_{i=1}^{k}n_i^2}
\]

Assuming non-negative counts and at least one hit:

- \(J=1\) if all counts are equal.
- \(J\) is less than 1 when the distribution is skewed.
- With k instances and all hits going to a single instance, \(J=1/k\).

Applied to Random run 1:

\[
J=
\frac{6000^2}{3(1987^2+2050^2+1963^2)}
\approx0.99966
\]

A value close to 1 indicates **near-balanced request counts**. It says nothing directly about CPU or backend latency, since individual requests can consume wildly different amounts of resources.

### 12.4. Pearson Chi-Square

Under the uniform distribution hypothesis, \(E=6000/3=2000\):

\[
\chi^2=\sum_{i=1}^{3}\frac{(n_i-E)^2}{E}
=\frac{(-13)^2+50^2+(-37)^2}{2000}=2.019
\]

With k=3 and an i.i.d. random selection model, degrees of freedom \(k-1=2\), the standard 95% chi-square critical value is **approximately 5.991**. The result 2.019 **does not show strong evidence against a uniform distribution** at the 5% significance level under that model.

However:

1. If one random run yields chi-square > 5.991, that **can happen purely by chance** roughly 5% of the time when the null hypothesis is true; do not declare the algorithm broken from a single run.
2. If Round Robin yields chi-square=0 when N is divisible by k, that is a consequence **of a deterministic algorithm**, not "better randomness."
3. Chi-square is only inferentially valid when the experiment matches the model assumptions: equal probabilities, fixed instance list, sufficiently independent events, and large enough expected counts.
4. If one instance errors out and returns no JSON, success counts suffer from **selection bias**. In that case, measure **selection counts** or HTTP attempts separately.

## 13. Repeating Multiple Runs Instead of Relying on One Snapshot

For a reliable comparison, run **at least 10 runs** per algorithm under the same N and conditions; you can increase to 30 runs to observe run-to-run variance.

PowerShell example calling the running endpoint:

~~~powershell
$rows = @()
1..10 | ForEach-Object {
    $r = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
    $rows += [PSCustomObject]@{
        run       = $_
        algorithm = $r.algorithm
        a         = $r.counts.'inventory-a'
        b         = $r.counts.'inventory-b'
        c         = $r.counts.'inventory-c'
        errors    = $r.failed
        jain      = $r.jainFairness
        chiSquare = $r.chiSquare
        p95Ms     = $r.p95Ms
    }
}
$rows | Format-Table -AutoSize
~~~

If you need to save results **in your own practice project**, you can use `Export-Csv` on the learner's machine; **the documentation worker does not generate CSVs or experiment output files**.

### 13.1. How to Interpret Multiple Runs

| Expectation | Round Robin | Random |
| --- | --- | --- |
| Count per instance across 6,000 requests | Near 2,000 if pool/list are fixed and calls succeed | Fluctuates around 2,000 |
| Variance across runs | Negligible in counts (excluding topology changes/errors) | Varies naturally |
| Chi-square with fixed list and N divisible by k | Can be 0 | Usually >0, fluctuates |
| Mean share across many runs | Near 33.33% | Approaches 33.33% |
| P95/P99 latency | Depends on backend/network/pool | Depends on backend/network/pool |

**Do not cherry-pick a random run that happens to hit 2000–2000–2000 and claim random behaves like Round Robin by rule.** A single lucky near-even outcome does not turn a stochastic algorithm into a cyclic one.

### 13.2. Should You Restart the Caller Every Time?

**To switch algorithms:** yes, in this lab workflow so the property and child context are reliably recreated.

**To repeat the same algorithm:** you can call `/lab/run` repeatedly within the same process, though subsequent runs use a warmed connection pool/JIT/context; that is good for comparing **steady-state**, and unsuitable if measuring **first-call cold start**.

If studying cold-start latency, each run should start with a fresh JVM/process and record startup separately. If studying instance-selection fairness, restarting between every run is unnecessary.

## 14. Comparing Across Different Values of N

An experimental table should cover:

| N | Instance Count k | Round Robin Expectation | Random Expectation |
| ---: | ---: | --- | --- |
| 30 | 3 | 10/10/10 (if stable) | Can deviate substantially |
| 300 | 3 | 100/100/100 | Noticeable fluctuation |
| 3,000 | 3 | 1000/1000/1000 | Shares typically closer to 1/3 |
| 6,000 | 3 | 2000/2000/2000 | Counts still differ by dozens |
| 30,000 | 3 | 10000/10000/10000 | Relative deviation typically lower |

Run every value of N for both algorithms. Record:

- counts and individual shares;
- gap, relative gap, Jain, chi-square;
- error rate;
- P50/P95/P99;
- total elapsed time.

### 14.1. How Should the Convergence Curve Be Interpreted?

If you plot:

~~~text
X-axis: N = 30, 300, 3000, 6000, 30000
Y-axis: relative gap (%) or |share_i - 1/k|
Each color: one algorithm
~~~

then the random curve generally tends to **decrease in proportional deviation** as N grows, though it does not have to drop at **every consecutive step**. An N=6,000 run can still show a larger relative gap than an N=3,000 run purely due to random noise.

With Round Robin, when N is divisible by k, the count-gap curve can sit at 0. If it remains high, investigate **failures, retries, changing lists, and shared caller traffic** before blaming the selector code.

## 15. Concurrency: Selections May Be Even While Completion Order Is Not Alternating

In the baseline phase, we called **sequentially**. Next, spawn **16 or 64 concurrent workers** to observe the difference between **selection order** and **completion order**.

~~~text
Selection time (Round Robin):
  request-1  -> A
  request-2  -> B
  request-3  -> C
  request-4  -> A
  request-5  -> B
  request-6  -> C

Completion time (due to varying latency):
  request-3  <- C
  request-2  <- B
  request-6  <- C
  request-1  <- A
  request-5  <- B
  request-4  <- A
~~~

**Round Robin enforces a rule over selection order according to selector state**, not **responses returning in A→B→C order**. Concurrency, HTTP connection pooling, TCP scheduling, backend latency, and OS thread scheduling reorder completions.

### 15.1. Designing a Reproducible Concurrent Test

Instead of blasting HTTP calls externally and guessing their arrival order, in a test project use:

- An `ExecutorService` with a configured fixed thread pool.
- A `CountDownLatch` or `CyclicBarrier` so workers start nearly simultaneously.
- `ConcurrentHashMap`/`LongAdder` to count responses per instance.
- `AtomicInteger` to count failed attempts.
- **`CompletionService` or `CompletableFuture.allOf`** to wait for all tasks.
- An overall timeout so the test does not hang if a backend dies.

After the run, assert **total counts + errors = N logical calls**. Never write to a plain `HashMap` from multiple threads without synchronization. If you simply call `/lab/run` from section 10, **each endpoint call still runs sequentially**; sending concurrent requests to that endpoint creates **multiple overlapping runs**, not one cleanly defined run.

### 15.2. Why Can Skew Still Appear Under Concurrency?

If the same `RoundRobinLoadBalancer` uses an atomic position and all 3 instances remain stable, **final total selections** still stay nearly balanced. However:

- Some requests time out and produce no response to count.
- Retries add attempts so selection counts diverge from logical call counts.
- Multiple callers maintain separate counters.
- Suppliers might return lists with different orderings or contents.
- A request gets cancelled between `choose` and sending HTTP.
- One slow server accumulates higher **in-flight concurrency** even when assigned counts are nearly equal.

Thus, under concurrency you should inspect **LoadBalancer selection metrics + HTTP attempt metrics + backend success counts**, not just a list of JSON responses.

## 16. Failure Experiment: Stopping One Inventory Instance Mid-Run

After a successful baseline, keep static discovery configured with A/B/C, but **stop the `inventory-b` process on port 8092**.

~~~text
SimpleDiscoveryClient: [A, B, C]
A: UP
B: DOWN, port 8092 no longer has a listener
C: UP
~~~

### 16.1. With Retries Disabled

In this phase:

- Round Robin may still **pick B** every few calls because the supplier list still includes B.
- Calls hitting B may throw **connection refused**, yielding no `instanceId` JSON.
- The caller records B under **errors**, not successful response counts.
- Remaining responses may come from A/C.

**Hypothetical** distribution example, N=6000:

| Metric | A | B | C | Total |
| --- | ---: | ---: | ---: | ---: |
| Times selected (if observed at LB) | 2000 | 2000 | 2000 | 6000 |
| Successful responses with `instanceId` | 2000 | 0 | 2000 | 4000 |
| Failed attempts connecting to B | 0 | 2000 | 0 | 2000 |

If you only look at JSON counts of successful responses, you will see **A/C balanced 50/50** and B=0. That result does not prove LoadBalancer noticed B is dead, because **selection can still be split evenly across all three instances**.

### 16.2. What If You Add HealthCheckServiceInstanceListSupplier?

If the supplier is designed with health checks and B is dropped from the candidate set after polling, the list can become:

~~~text
[A, C]
~~~

Round Robin will then alternate between A/C instead of A/B/C. However, eviction depends on **poll interval, initial delay, health endpoint, caching, discovery consistency, and supplier ordering**. Do not assume a single HTTP connection refused immediately makes Spring Cloud LoadBalancer drop the instance.

Once the list only contains A/C, the expectation for a new N=6000 run (after the snapshot settles) is approximately:

~~~text
Round Robin: A=3000, C=3000
Random:      A≈3000, C≈3000, with fluctuations
~~~

**This is a different experiment**: k changed from 3 to 2. Do not compare a k=2 run's chi-square against a k=3 expected table without adjusting.

### 16.3. Do Not Use Round-Robin as a Substitute for Health Checks

Plain Round Robin **is not a dead-backend detector**. It only picks from **the list it is given**. If the list still contains B, the algorithm can still select B; properly removing B requires an appropriately designed discovery/health supplier or retry/failure policy.

## 17. Enabling Retries: Counting Logical Calls, Attempts, and Backend Successes Separately

After understanding the failure case, try a **bounded** retry configuration (in a test environment only) to see how retries affect distribution.

Illustrative policy example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

**Do not assume** this YAML snippet alone enables retries for every client/release train: blocking `RestTemplate` may require Spring Retry on the classpath; `RestClient`, `WebClient`, and Feign have their own integration paths. Always verify actual retries using backend request counts and logs.

### 17.1. Example of How Retries Change the Counts

~~~text
Logical request #42:

Attempt 1: LB picks B -> connection refused
Attempt 2: LB picks C -> HTTP 200

Logical calls         = 1
LoadBalancer attempts = 2 (if each retry re-selects)
Backend HTTP receives = 1 on C (B may receive no HTTP request because connect failed)
Success responses     = 1 on C
~~~

Therefore:

~~~text
One logical call can lead to multiple LB selections.
One selection may not lead to an HTTP request received by a backend.
A backend may process a request while the caller times out before receiving the response.
~~~

If you compare N=6000 logical calls with retries enabled directly against an expected **2000/instance for selections**, you are using the wrong denominator. You need to:

1. Count **logical calls** at the caller.
2. Count **HTTP attempts** at the client/transport layer.
3. Record the **selected instance** of each attempt via LoadBalancer lifecycle or corresponding instrumentation.
4. Count **requests actually received by the server** and **successful responses**.
5. Compare ratios of each data type against its matching denominator.

### 17.2. Retries Might Not Pick a Different Instance

Even when the policy is retry-on-next-service-instance:

- If only one instance exists, there is no alternative.
- The supplier might return an altered list between attempts.
- The retry context might not propagate properly in a given HTTP integration.
- A fallback/zone preference might keep only the previous candidate.

Therefore, tests must record **the instance selected on attempt 1 and attempt 2**, rather than asserting "retry guarantees failover."

### 17.3. Failures with Side Effects

The baseline phase uses safe GET requests. If expanding to `POST /reservations`, **a client timeout does not prove the backend failed to commit**; retrying can duplicate transactions. You need an **idempotency key** and server-side deduplication. Never use stateful business POST endpoints as input for a simple distribution benchmark.

## 18. Changing Instance Lists: No Longer Assuming a Cycle Over a Fixed Set

In real environments, `ServiceInstanceListSupplier` can update the list due to:

- Scale-out or scale-in.
- Registry marking an instance DOWN/UP.
- Health check re-evaluation.
- Zone/hint filters producing a different subset.
- Cache TTL expiration fetching a fresh discovery snapshot.
- Canary/metadata/weight rollouts.

Example:

~~~text
Requests 1..3000: supplier = [A, B, C]
Requests 3001..6000: supplier = [A, C, D, E]
~~~

We cannot divide N=6000 by a single fixed k to predict full-run counts. A sounder analysis:

1. **Timestamp every discovery/supplier snapshot**.
2. Split the run into **epochs** where the candidate list is relatively stable.
3. Compute expectations separately for each epoch.
4. Sum each instance's expected hits across the epochs where it was actually eligible.

For instance, A/C appear in both epochs, B only in epoch 1, and D/E only in epoch 2. A/C having higher counts than B/D/E happens **not because the algorithm is biased**, but because **their eligible durations differed**.

### 18.1. Zone Preference Can Change Effective k

Suppose the Caller is in `zone-a`, and the supplier prefers `[A, B]` and only falls back to `[C]` when no same-zone instances remain. Even though the registry holds 3 replicas, the **eligible** set for each selection may only be 2.

Do not conclude Random is broken because C gets 0 requests. First inspect:

~~~text
Discovery list      = [A, B, C]
Filtered list       = [A, B]
Selected instances  = A or B
~~~

Every fairness formula in this lesson must be computed **over the actual policy's candidate set**, not all running processes.

### 18.2. Weighted Selection Is a Different Problem

If weights for A/B/C are 5/3/2 respectively, the true expectation is no longer 1/3 per instance. Use:

\[
p_A=0.5,\quad p_B=0.3,\quad p_C=0.2
\]

and expected counts are \(N p_i\). Do not apply an equal-split Round Robin/Random test to a pipeline with **WeightedServiceInstanceListSupplier** or another weighted policy without adjusting expectations.

The goal of the current lab is to **distinguish selection algorithms over an equal-weight list**, not to benchmark weighted load balancing.

## 19. Hit-Count Fairness Does Not Guarantee Better Latency

Suppose all three backends each receive roughly 2000 requests:

| Instance | Assumed Average Processing Time |
| --- | ---: |
| A | 15 ms |
| B | 150 ms |
| C | 20 ms |

Round Robin still splits hit counts nearly 1/3 each, yet B is much slower; overall P95 can suffer heavily because roughly 1/3 of requests hit B.

Random also selects B roughly 1/3 of the time in expectation, and will produce random bursts to B. An algorithm aware of **latency, outstanding requests, CPU, weight, or health** may yield a better load distribution. However, that is a **different custom policy**, not proof that Round Robin/Random are inherently bad.

### 19.1. Do Not Evaluate Using Only Total Elapsed Time of a Sequential Test

For N sequential calls:

\[
T_{\text{total}} \approx \sum_{i=1}^{N}T_i
\]

Throughput near \(N/T_{\text{total}}\) depends heavily on **network RTT and backend response time**. A few microseconds' difference in the selection algorithm is completely masked by HTTP.

To measure **the algorithm's own overhead**, you must benchmark `choose()` directly with the same `ServiceInstanceListSupplier`, without creating HTTP sockets, accounting for JVM warm-up/JMH. However, this lesson's goal is **real HTTP distribution**, not microbenchmarking `choose()`.

### 19.2. P95/P99 Can Be Affected by the Connection Pool

Even when `/whoami` is tiny:

- Cold connections incur DNS/TCP/TLS overhead.
- Keep-alive reuse lowers latency for later requests.
- Pool acquisition queues can grow under higher concurrency.
- HTTP/2 multiplexing changes the relationship between connections and requests.
- GC, JIT, OS scheduling, and server-side thread pools affect elapsed time.

Thus, when reporting that Random had a higher P95 than Round Robin in one run, specify **HTTP engine, pool config, concurrent load, warm-up, and error rate**. Never turn a single-run gap into a universal conclusion about the algorithm.

## 20. Automated Testing: Functional Verification and Statistics Are Different Tasks

A test can verify **the code works correctly** without forcing Random to produce exact 1/3 counts. Split into three tiers:

| Tier | Goal | How to Verify |
| --- | --- | --- |
| Algorithm/supplier unit test | Round Robin and Random pick within valid candidates | Fixed `ServiceInstanceListSupplier`, call `choose()` |
| HTTP integration test | Service ID URI is rewritten to real instances | MockWebServer/WireMock, recorded requests |
| Performance/statistical experiment | Distribution at large N, P95/P99, and variance | Repeat multiple runs, report counts/CI/metrics |

**Never use a single random statistical threshold as a hard CI assertion.** If random is truly implemented properly, a short sample can still deviate significantly by chance and make the test flaky.

### 20.1. A Baseline Acceptance Test Suite

| Test | Setup | Assertion |
| --- | --- | --- |
| Service ID lookup | A/B/C all running | No DNS lookup of `inventory-service` as a physical host; backends receive requests |
| Round Robin 600 calls | 3 fixed instances, retry off | Successful counts equal 200/200/200 with no other traffic |
| Round Robin 601 calls | Same controlled list/context | Counts look like 201/200/200, without requiring a specific instance to get the extra |
| Random 600 calls | 3 fixed instances, retry off | Total counts=600, every `instanceId` belongs to the valid set |
| Random large N | 6,000+ requests, repeated runs | Report distribution, do not hard-assert exact equality |
| No instance | Empty supplier | Zero HTTP backend requests; caller gets no-instance error |
| One instance down | B stopped yet still in list | Failures are recorded, not swallowed |
| Retry enabled | Explicit attempt limit | Backend attempt count and logical successes measured separately |
| Concurrency | Fixed worker count | Total successes+errors=N, thread-safe counters |
| Zone/hint filter | Candidate set narrowed to A/B | Do not expect C to receive 1/3 |

### 20.2. Why Can a 600-Call Round Robin Test Assert Exact Counts?

With **one selector state**, a supplier always returning `[A,B,C]` in the same order, retries off, no external requests, and all 600 responses succeeding, the selection cycle completes exactly 200 full rounds. **The critical condition is that the selection count equals 600.**

If a 30-call warm-up precedes the test, since 30 is divisible by 3, counts during measurement remain balanced. Even with a 1-call warm-up or a different starting counter position, **counts remain equal** whenever N is divisible by 3. Only the **A/B/C order of the first three requests** may differ.

### 20.3. Do Not Write a Random Test That Asserts the Wrong Hypothesis

Example of an assertion prone to flakiness:

~~~java
assertEquals(200, counts.get("inventory-a")); // Wrong for Random.
assertEquals(200, counts.get("inventory-b"));
assertEquals(200, counts.get("inventory-c"));
~~~

A correct random implementation has a very low probability of hitting **exact equality** after N requests. How to verify functionally:

~~~java
// controller injected in an integration test with three running backends.
ExperimentController.RunReport report = controller.run(600, 30);

assertEquals(0, report.failed());
assertEquals(600, report.succeeded());
assertEquals(600, report.counts().values()
        .stream().mapToInt(Integer::intValue).sum());
~~~

These assertions **do not prove the algorithm distributes uniformly**. Therefore, run multiple trials and separate statistical checks outside strict CI gates; or test `RandomLoadBalancer` by injecting/isolating the randomness source **when the implementation's API permits**, without altering production code just to achieve a deterministic distribution.

### 20.4. Unit Tests Do Not Replace Integration Tests

Mocking **`ReactorLoadBalancer.choose()`** directly can prove the algorithm selects an instance, but does not verify **`RestClient` has `@LoadBalanced`**, that the request URL is rewritten, or that backends actually receive requests. Conversely, a passing HTTP integration test only shows requests reached backends—not necessarily that the policy is Random rather than Round Robin.

A solid test suite includes all three:

~~~text
Algorithm config test
  -> Bean type is RoundRobinLoadBalancer or RandomLoadBalancer

HTTP integration test
  -> GET /whoami via service ID
  -> selected backend/physical URI is real

Statistical experiment
  -> distribution at large N
  -> report numbers and probability model
~~~

## 21. Observability: What to Measure When Results Surprise You?

Spring Cloud LoadBalancer supports **MicrometerStatsLoadBalancerLifecycle**; it can be enabled via:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

When a Micrometer **MeterRegistry** (e.g., via Spring Boot Actuator) and proper integration are present, Spring Cloud documentation lists these meters:

| Meter | Description |
| --- | --- |
| loadbalancer.requests.active | Gauge of active requests by instance info |
| loadbalancer.requests.success | Timer of load-balanced requests completing successfully per lifecycle |
| loadbalancer.requests.failed | Timer of requests ending with an exception |
| loadbalancer.requests.discard | Counter of requests discarded because no `ServiceInstance` could be selected |

**They do not automatically give you an exact "choose count" histogram independent of HTTP responses.** Before relying on a meter, verify the semantics of your version, available tags, and which requests are instrumented.

### 21.1. Avoiding Excessive Cardinality

Never attach to metric tags:

- Raw SKUs, order IDs, customer IDs.
- Full URLs with dynamic query parameters.
- Trace IDs, request IDs.
- Rapidly churning instance IDs or unbounded hosts/ports.

Spring Cloud LoadBalancer documentation warns about the **uri** tag in `RestTemplate` and notes **spring.cloud.loadbalancer.stats.include-path=false** to curb high-cardinality paths when needed. Use **URI templates**, service IDs, and stable operation names for aggregates.

If you need to inspect a specific instance ID, use **sampled tracing/logs** with restricted access instead of turning tens of thousands of instances into uncontrolled metric tags.

### 21.2. An Illustrative Event Trace

~~~text
trace=trace-091, logicalService=inventory-service
algorithm=round-robin, attempt=1
selected=inventory-b, physicalHost=127.0.0.1:8092
httpStatus=200, backendInstanceId=inventory-b
elapsedMs=24.8
~~~

When a timeout occurs:

~~~text
trace=trace-092, logicalService=inventory-service
algorithm=random, attempt=1
selected=inventory-c, error=read_timeout
backendResponseObserved=false
elapsedMs=1000
~~~

This is a **custom application-designed log format**, not default Spring Cloud output. The **selected** field must come from the exact request context or lifecycle, never from an instance picked by an earlier request.

## 22. Troubleshooting: Why Do the Numbers Not Match Expectations?

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| Both modes look like Round Robin | `@ConditionalOnProperty` not applied in child context or Random bean not created | Verify bean type in LB context, startup properties |
| Only one server ever receives calls | Wrong `SimpleDiscoveryClient` YAML or filter keeping one instance | Inspect supplier list |
| `UnknownHostException inventory-service` | Client lacks `@LoadBalanced` integration | Use the `@LoadBalanced` builder bean |
| RR counts are uneven | Errors/timeouts, retries, external traffic, changing list | Separate choose attempts from successes |
| First request is always B instead of A | Initial state/seed or warm-up already ran | Do not assert first hit must be A |
| Random gives 60/20/20 after 10 requests | Sample size too small | Run 6,000+ across multiple runs |
| Random skewed after 6,000 requests | Natural variance or uneven list/policy | Compute chi-square across runs, check instance list |
| Chi-square consistently very high | Weighted/zone/hint, config bug, or concentrated failures | Check eligible set and response failures |
| Random hits exact 2,000/2,000/2,000 once | Possible by chance or actually running RR | Verify bean type, repeat runs |
| RR is even yet B's CPU is high | B is slower or on different hardware | Measure CPU, in-flight, backend latency |
| P99 fluctuates wildly | JIT/GC, cold sockets, pool, scheduling | Warm-up, metrics, repeat experiment |
| Caller returns 503, backend sees no request | No instances or gateway | Check discovery and lifecycle |
| Backend A receives requests yet caller counts A=0 | Broken response body, client timeout, parser mismatch | Compare HTTP recorded requests with successes |
| Retries push total attempts > N | Policy sends multiple attempts | Disable retries in baseline, measure attempts separately |
| Response order is not A→B→C | Concurrency or heterogeneous latency | Compare selection events instead of completion order |
| Differences across two callers | RoundRobin state is per caller/context | Segment results by caller instance |
| Results change when changing N | N not divisible by k or random noise | Use floor/ceil bounds, probabilistic expectation |
| Fairness looks "skewed" after scale-out | New instances were eligible only for part of the run | Split into epochs by snapshot |

### 22.1. Ordered Debugging Checklist

~~~text
1. Are all three Inventory ports listening for HTTP?
2. Does each port return the right instanceId?
3. Does the caller use the proper @LoadBalanced RestClient.Builder?
4. Is SimpleDiscoveryClient returning [A,B,C]?
5. Did inventory-service's child context instantiate the intended algorithm bean?
6. Is any zone/health/hint/weight supplier altering the candidate set?
7. Do N logical requests equal selection counts and HTTP attempts?
8. Are failed and errorsByType equal to 0?
9. Is any other caller hitting the same service ID during the run?
10. Is your data measuring selections, backend receives, or successful responses?
~~~

Only after answering all ten should you compare **chi-square or Jain's index**. A pretty chart built on the wrong denominator leads to false conclusions.

## 23. Writing a Result Report Instead of Just Taking Screenshots

A technical report for this experiment should include at least:

**A. Run Conditions**

~~~text
Spring Boot / Spring Cloud release train:
Java version:
HTTP client / request factory:
Service ID:
Instance count and ports:
ServiceInstanceListSupplier pipeline:
Actual instantiated LB algorithm:
N (measured):
Warm-up requests:
Concurrency:
Retry policy:
Timeout:
Zone/hint/health filters:
Number of repetitions:
~~~

**B. Observed Data**

| Run | Algorithm | N | Success | Failed | A | B | C | Jain | Chi-square | P95 (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Round Robin | 6000 | 6000 | 0 | 2000 | 2000 | 2000 | 1.0000 | 0.000 | ... |
| 2 | Random | 6000 | 6000 | 0 | 1987 | 2050 | 1963 | 0.9997 | 2.019 | ... |
| 3 | Random | 6000 | 6000 | 0 | ... | ... | ... | ... | ... | ... |

**The figures above are illustrative only**, not executed run results. P95 is left blank because no real measurement was taken; never fabricate latency numbers for a report.

**C. Interpretation**

Example of an appropriate interpretation:

> Under a single caller, three identical instances, no retries, and an unchanged list, Round Robin splits hit counts almost strictly evenly in cyclic order. Random produces fluctuations around the 1/3 probability; as N increases, relative deviation typically shrinks. Because both used `RestClient` and the same three backends, this experiment **does not provide enough evidence** to conclude which algorithm delivers lower P99 latency in production.

**D. Limitations and Next Steps**

Explicitly state limitations: local loopback, single caller, no real registry, plain HTTP without TLS, homogeneous backends, tiny payloads, no production traffic, no topology churn. Propose separate concurrent/failure/health/weight experiments rather than mixing results from multiple configurations into one conclusion.

### 23.1. A Good Report Does Not "Clean Up" Random Data

Do not do this:

~~~text
Random A=1987, B=2050, C=1963
=> Edit table to 2000/2000/2000 so the chart looks neat.
~~~

Do this instead:

~~~text
Random observed counts: 1987/2050/1963
Expected counts:        2000/2000/2000
Absolute deviations:    -13/+50/-37
Chi-square:             2.019
Relative gap:           4.35%
~~~

The deviation itself is the **scientific signal** of a randomized algorithm; erasing it defeats the purpose of the experiment.

## 24. Extension Exercises with Hints

### 24.1. N Not Divisible by Instance Count

**Prompt:** Run 6,001 requests using Round Robin with three fixed instances, no retries, zero errors. What counts do you expect?

**Hint:** \(\lfloor6001/3\rfloor=2000\), \(\lceil6001/3\rceil=2001\). Therefore one instance receives 2,001 hits and the other two receive 2,000; **it is not guaranteed that A specifically gets 2,001**.

### 24.2. Random Distribution After 300 Requests

**Prompt:** Random gives counts A=115, B=88, C=97. Should we conclude the implementation is buggy?

**Hint:** Total=300 and expected per instance=100, but the sample is still small. Compute chi-square:

\[
\chi^2=\frac{(115-100)^2+(88-100)^2+(97-100)^2}{100}
=3.78
\]

With 2 degrees of freedom, this value is below the 5.991 threshold at the 5% level. There is not enough evidence to reject a uniform distribution at that level. Still, this is only **one check on one run**; repeat trials and ensure the instance set stays unchanged.

### 24.3. One Instance Is 10x Slower

**Prompt:** A/B/C each receive 2,000 requests, yet B averages 200 ms processing time while A/C average 20 ms.

**Hint:** Jain's index by **hit count** is still 1, while Jain's index by **resource usage** (if measured properly) can differ. Round Robin does not inspect outstanding requests or latency to avoid B. Benchmark under load and consider an appropriate weighted/adaptive policy.

### 24.4. Two Caller Pods

**Prompt:** Caller-1 sends 3,001 requests; Caller-2 sends 2,999 requests. Both pods have separate `RoundRobinLoadBalancer` state. Can we predict an exact cluster-wide 2,000 hits per instance?

**Hint:** Each pod distributes nearly evenly, yet **starting positions are not synchronized**. Cluster-wide counts can differ by a few hits, with no global A→B→C sequence. Do not expect a shared counter across two JVMs.

### 24.5. Stopping inventory-b Without Refreshing Discovery

**Prompt:** Will Round Robin still pick B?

**Hint:** Possibly yes if `SimpleDiscoveryClient` still contains B. The selector does not automatically evict an instance on a single connection error; dedicated health/discovery/retry policies are needed. Analyze **selection counts** and **success counts** separately.

### 24.6. Random and the Chi-Square Threshold

**Prompt:** Across 20 independent random runs, one run has chi-square > 5.991. Is it necessarily a bug?

**Hint:** No. At the 5% significance level, the probability of at least one false alarm across 20 independent runs is approximately:

\[
1-(1-0.05)^{20}\approx64\%
\]

If large skew persists consistently, inspect lists/weights/filters and errors, and consider statistical tests adjusted for **multiple testing**. Never use a single threshold as a standalone production alarm button.

### 24.7. Running WebClient Instead of RestClient

**Prompt:** Write a reactive version of `/lab/run` using `WebClient`.

**Hint:** Use **@LoadBalanced WebClient.Builder** and a pipeline with bounded concurrency:

~~~java
Flux.range(0, n)
        .flatMap(i -> webClient.get()
                .uri("http://inventory-service/whoami")
                .retrieve()
                .bodyToMono(InstanceReply.class),
                16);
~~~

If collecting all N responses, gather **counts with a thread-safe collector** or use `collectList()`/`groupBy()` mindful of memory; configure timeouts and error handling so the whole run does not abort silently.

**Key difference:** `flatMap` concurrency 16 changes the workload characteristics compared to sequential `RestClient`. Do not attribute P95/throughput differences between those two runs solely to Round Robin vs Random.

### 24.8. Proving the Actual Algorithm Rather Than Just the Label

**Prompt:** A learner sets `lab.algorithm=random` yet counts remain strictly 2000/2000/2000 across all ten runs.

**Hint:** That warrants investigation, though it does not prove a bug by itself. Inspect the **bean implementation** inside the child LoadBalancer context, startup logs/config, and how `@ConditionalOnProperty` is evaluated; ensure no fixed supplier/selector is overriding it. Never rely on the string echoed in `RunReport` as sufficient proof.

## 25. Lab Acceptance Checklist

- [ ] Both Inventory and Caller subprojects use a compatible Spring Boot–Spring Cloud BOM.
- [ ] Verified all three backends 8091/8092/8093 return the right `instanceId`.
- [ ] Only one `SimpleDiscoveryClient` source exists for `inventory-service` in the baseline.
- [ ] Caller uses **@LoadBalanced RestClient.Builder** with the service ID URI.
- [ ] Random and Round Robin are registered in the **child LoadBalancer context**, not accidentally picked up by parent component scan.
- [ ] Verified the actual instantiated bean matches the property, not just the algorithm label.
- [ ] Health/zone/hint/weighted filters are disabled during the baseline phase.
- [ ] Retries are disabled, and HTTP client/transport settings match between both arms.
- [ ] N is fixed, e.g., 6,000; all runs share the same warm-up count.
- [ ] Verified **requested = successes + failed**.
- [ ] With `failed=0`, total A+B+C counts equal N.
- [ ] Measured Round Robin counts, shares, max-min gap, and relative gap.
- [ ] Measured Random counts, Jain fairness, chi-square, and multi-run variance.
- [ ] Did not assert Random must split strictly equally.
- [ ] Did not assert response completion order must be A→B→C.
- [ ] Did not conclude one algorithm is faster from a single run's P95.
- [ ] Documented HTTP engine, timeouts, pooling, concurrency, and runtime environment.
- [ ] Ran additional experiments with small/medium/large N.
- [ ] Tested one dead backend, distinguishing selection counts from success counts.
- [ ] Tested retries re-selecting instances, counting attempts separately.
- [ ] Tested changing lists/health/zones and adjusted k to the eligible set.
- [ ] Wrote unit tests for algorithm configuration and real HTTP integration tests.
- [ ] Avoided side effects and never blasted thousands of requests at production.
- [ ] Produced a report with real data tables, formulas, interpretation, and limitations.
- [ ] Avoided high-cardinality metric tags such as SKUs, customer IDs, or trace IDs.

## 26. Conclusion

Under **the same stable `ServiceInstance` set, single caller, no retries, and zero errors**, the two algorithms exhibit clear properties:

- **Round Robin** advances cyclically by index, yielding nearly equal counts; when N is divisible by k, selection counts per instance are equal under a sequential selection model.
- **Random** selects probabilistically, so counts fluctuate around \(N/k\). As N grows, **proportional deviation generally shrinks**, without forcing exact equality.

However, the selection algorithm is only **one piece** of client-side load-balanced communication. Once retries, health checks, zone preferences, cache/discovery churn, concurrency, multiple caller pods, timeouts, and connection pools enter the picture, you must separate:

~~~text
logical calls
    -> ServiceInstance selections
    -> HTTP transport attempts
    -> backend received requests
    -> completed successful responses
~~~

Only when you use the right **denominator**, hold confounding variables steady, and take repeated measurements does comparing Round Robin with Random become meaningful. The lab results help learners understand algorithm behavior; optimal production choices also depend on **latency SLOs, capacity, reliability, routing policies, and observability**.

## 27. References

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): default Round Robin algorithm, Random, custom configuration, and `ServiceInstanceListSupplier`.
- [Spring Cloud LoadBalancer – Switching between the load-balancing algorithms](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#switching-between-the-load-balancing-algorithms): example of configuring `RandomLoadBalancer` via `@LoadBalancerClient`.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `SimpleDiscoveryClient` and `@LoadBalanced RestClient.Builder`.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): retry, cache, health, stats, and per-client properties.
- [Spring Cloud LoadBalancer – Statistics](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#spring-cloud-loadbalancer-statistics): `MicrometerStatsLoadBalancerLifecycle` and request meters.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, exception handling, and `ClientHttpRequestFactory`.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): `WebClient` and reactive request execution.
- [Spring Boot – REST Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient.Builder` and HTTP transport configuration in Boot.
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `SpringBootTest` and test configuration.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `Publisher` subscription, and reactive testing.
- [NIST Engineering Statistics Handbook – Chi-Square Goodness-of-Fit](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35f.htm): foundations and limitations of the chi-square test.
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): timers/counters, histograms, and percentile metrics.
