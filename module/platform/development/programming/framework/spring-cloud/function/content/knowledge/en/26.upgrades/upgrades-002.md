# Comparing APIs, Configuration Properties, and Default Behavior Changes

## 1. A Successful Upgrade Does Not Mean Behavior Remains Identical

Suppose a Spring Cloud Function application has an order-classification bean:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> new OrderClassified(
            order.orderId(),
            order.totalInCents() >= 100_000L
                    ? "PRIORITY" : "STANDARD");
}
```

Before the upgrade, the application receives JSON over HTTP or Kafka, converts the data into `OrderCreated`, invokes `classifyOrder`, and sends the result. After upgrading the libraries, the application still **compiles** and even **starts up cleanly**, yet it may change how the default bean is selected, binding names, converted payload types, polling intervals, retries, or error-message handling.

Thus, verifying an upgrade is not merely asking "does the old API still compile?", but comparing three dimensions:

1. **API:** do classes, interfaces, methods, annotations, generic types, and invocation contracts remain compatible?
2. **Configuration:** have property names, namespaces, value types, scopes, precedence order, or binder-supported properties changed?
3. **Default behavior:** when a property is omitted, which function does the application actually pick, which destination/group does it read, how does it serialize payloads, how many times does it retry, and how does it handle failures?

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_FUNCTION** module. The focus is keeping `Supplier`, `Function`, `Consumer`, and `FunctionCatalog` reusable across HTTP, Spring Cloud Stream, or serverless while upgrading external adapters, dependencies, and configuration in a controlled way.

**Expected outcome:** you will know how to build a before–after comparison table, avoid misattributing a deployment-configuration change as a "Function breaking change," write regression tests with realistic payloads, and establish a recovery plan if runtime behavior no longer meets the contract.

## 2. Pinpoint the Exact Version Pair Before Comparing

Every claim that "previously the default was X, now it is Y" must state **the starting point, ending point, and context**. A change in Spring Cloud Function 5.1 can differ from a change in Boot 4 or the Kafka binder. Do not use documentation from a current version to infer the behavior of an application still on the 3.x line.

Example generation comparison as of **November 24, 2026**:

| Axis | Assumed baseline | Illustrative target | Verification source |
| --- | --- | --- | --- |
| Spring Boot | 3.5.x | 4.2.0 | Boot migration guide and system requirements |
| Spring Cloud BOM | 2025.0.x | 2026.0.0 | Spring Cloud/Boot matrix, release train notes |
| Spring Cloud Function | 4.3.x | 5.1.0 | Function release notes and dependency graph |
| Spring Cloud Stream | Branch managed by BOM 2025.0.x | 5.1.0 | Stream and binder release notes |
| Java target/runtime | Current application values | Selected and tested values | Build tool, image/serverless runtime |
| HTTP/Kafka/Rabbit/AWS adapter | Specific dependencies | Versions managed by BOM | Adapter docs and integration tests |

Spring Cloud **2026.0.0** was released on **November 20, 2026**, based on Boot **4.2.0**, including Function **5.1.0** and Stream **5.1.0**. This is a **sourced illustrative milestone**, not a claim that every application must move to those versions immediately.

Sources: [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/) and [Spring Cloud release compatibility](https://spring.io/projects/spring-cloud/).

### Do Not Conflate Four Types of Changes

| Category | Example | How to detect |
| --- | --- | --- |
| **Source compatibility** | Method/annotation removed or signature changed | Compiler errors, API docs |
| **Binary compatibility** | `NoSuchMethodError` due to version-skewed modules | Dependency graph and startup/integration tests |
| **Configuration compatibility** | Property no longer binds or changed namespace | Metadata, startup logs, config experiments |
| **Behavioral compatibility** | Wrong function selected, different retries, messages sent to another group | Contract/golden tests and observability |

An API marked **deprecated** is not necessarily removed in the current release. Conversely, a property that is still syntactically accepted is not guaranteed to take effect in that adapter/binder.

## 3. Build a Three-Column Comparison Table Before Changing Anything

Start with a table answering three mandatory questions: **what does the old version do?**, **what does the new documentation state?**, **which test proves the required behavior is preserved?**

| Component | Baseline state to capture | Post-upgrade criteria |
| --- | --- | --- |
| Function bean | Bean name and generic signature | Catalog resolves the exact bean |
| Definition | Runtime value of `spring.cloud.function.definition` | Correct function/composition; no accidental fallback reliance |
| HTTP endpoint | Path, method, content type, status, and headers | Contract unchanged outside approved changes |
| Stream bindings | Input/output names, aliases | Bindings exist and connect to the right destinations |
| Kafka/Rabbit | Group, offset/queue, codec | No unexpected drops/duplicates; schema intact |
| Source/Supplier | Poll frequency, messages per poll | No extra emissions or missed items |
| Error path | `maxAttempts`, backoff, DLQ/DLT | Transient and permanent errors follow the right recovery path |
| Reactive | When subscribed, `onError`, ordering | One error does not terminate the stream against contract |
| Serverless | Handler, env vars, runtime, event shape | Invokes cleanly with sample production events |
| Security | Input routing, SpEL, payload size, deserialization | No new unsafe execution or DoS vectors introduced |

**Evidence rule:** label every finding with one of these statuses:

- **CONFIRMED:** release notes or API docs explicitly state the change in that exact version.
- **OBSERVED:** verified by running tests on the baseline/target.
- **ASSUMPTION:** no evidence yet; must be verified before deployment.

Do not write a "migration cheat sheet" guessing renamed properties simply because an old command failed. Distinguish between a **wrong property**, a **valid property attached to the wrong binding**, and a **valid property ignored by that adapter**.

## 4. Pre-Upgrade API Inventory: Do Not Just Grep Version Numbers

For a project using Spring Cloud Function, inventory at least:

- `Supplier<T>`, `Function<I,O>`, and `Consumer<T>` beans and exposed bean names.
- All call sites of `FunctionCatalog.lookup(...)` or direct interactions with `FunctionInvocationWrapper`.
- Composition, routing, `MessageRoutingCallback`, and custom converters.
- `Message<T>`, generic types, headers, and reactive `Flux`/`Mono`.
- `@PollableBean`, `StreamBridge`, `PollableMessageSource`, and custom binding APIs.
- HTTP, Stream Kafka/Rabbit, and AWS Lambda adapters if present.
- Legacy modules/annotations or **deprecated** libraries.
- SDKs, auto-configurations, or bytecode transformations relying on internal APIs.

### Commands Used Only for Inventory, Not Conclusions

```bash
# Maven: get resolved versions and dependency paths
mvn help:effective-pom
mvn dependency:tree

# Gradle: inspect runtimeClasspath and version selection reasons
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency spring-cloud-function-context

# Identify JDK/build tool
java -version
mvn -version
./gradlew --version
```

These are **reference commands for the learner's environment**. Dependency graph results must come from the exact artifact packaged for production, not only a test module. Running these commands is not required to follow this lesson.

## 5. FunctionCatalog and Java Beans: Two Different Invocation Paths

Consider:

```java
@Bean
Function<String, String> normalize() {
    return String::trim;
}
```

There are two ways to retrieve the function:

```java
// Original bean managed by the Spring ApplicationContext.
Function<String, String> original =
        applicationContext.getBean("normalize", Function.class);

// Function looked up through Spring Cloud Function.
Function<?, ?> fromCatalog = catalog.lookup("normalize");
```

**Do not assume both objects are identical.** Spring Cloud Function documentation notes that functions retrieved via `FunctionCatalog` may be **wrapped/instrumented**, adding behaviors such as invocation normalization, composition, and type conversion. Grabbing the raw bean directly is not guaranteed to pass through those wrappers.

### 5.1. Valid API, Yet Return Types Can Mislead Test Code

A risky migration snippet:

```java
// Easy to be overconfident about runtime types when wrappers/conversion are involved.
@SuppressWarnings("unchecked")
Function<String, String> fn =
        (Function<String, String>) catalog.lookup("normalize");
```

Generic casts in Java undergo type erasure; they do not prove the actual runtime payload is `String`. If `lookup` returns a wrapper handling `Message<?>`, or an adapter supplies data with another content type, test the actual invocation path and object types.

Choose tests according to the **contract being protected**:

1. Test the `normalize` bean directly to verify business logic `" x " → "x"`.
2. Test `FunctionCatalog` lookup to verify name resolution and invocation.
3. Test the HTTP or Stream adapter to verify message conversion and headers.

### 5.2. Unit-Test Pure Logic First

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class NormalizeBusinessTest {

    @Test
    void trimsText() {
        Function<String, String> fn = String::trim;
        assertEquals("ORD-101", fn.apply(" ORD-101 "));
    }
}
```

This is a pure business test with no Boot or broker dependency. It does not replace `FunctionCatalog` integration tests after an upgrade.

## 6. Definition and Bean Autodiscovery: Make Them Explicit

Spring Cloud Function documentation describes **single-function fallback**: when the catalog contains only one eligible functional bean, a lookup without specifying a name may still locate that function. With Spring Cloud Stream, an application with only one functional bean may be auto-bound.

This is **conditional** behavior, not a good contract to rely on long term.

For example, initially the application only has:

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

After upgrading, a starter or another bean happens to register an extra functional bean. Now "there is only one function" no longer holds. The application may fail to pick a definition or wire the wrong integration.

**Defensive configuration:**

```yaml
spring:
  cloud:
    function:
      definition: uppercase
```

If the application requires lookup **strictly by name**, Spring Cloud Function provides the property:

```yaml
spring:
  cloud:
    function:
      single-function-fallback-enabled: false
```

Do not treat this property as a default change introduced in 5.1; it is a **configuration tool** to lock down the behavior the application expects. Always test it on your target version.

### 6.1. Filtering Out Beans You Do Not Want Registered

Spring Cloud Function may detect functional beans that the application did not intend to expose. The documentation supports:

```properties
spring.cloud.function.ineligible-definitions=internalNormalizer,debugFunction
```

Use this when truly needed, though setting **`definition` explicitly** is still better. Whenever you change dependencies or starters, audit the beans registered in `FunctionCatalog` to avoid accidentally exposing an internal-only function over HTTP or FaaS adapters.

### 6.2. Before–After Checklist

| Item to compare | Before upgrade | After upgrade |
| --- | --- | --- |
| Total `Supplier/Function/Consumer` beans | Record exact count | Re-record; verify no unexpected beans |
| `spring.cloud.function.definition` | Present/absent, exact value | Explicit, matching business intent |
| Single-function fallback | Was it relied upon? | Decide whether to disable or cover with tests |
| Bean eligibility | Which beans enter the catalog? | No internal beans unintentionally exposed |
| Lookup name | Which name in `catalog.lookup(...)`? | Stable name, no collisions |

## 7. Composition, Multiple Definitions, and Binding Name Contracts

Two important separators:

- `|` composes multiple functions into **one pipeline**.
- `;` selects **multiple independent definitions** so Spring Cloud Stream binds them separately.

```yaml
# One pipeline: normalize runs before classify.
spring.cloud.function.definition: normalize|classify
```

```yaml
# Two separate definitions; no cross-binder ordering between them.
spring.cloud.function.definition: classify;audit
```

A common real-world upgrade bug is **not an API change**, but a property accidentally dropped in a new profile. The application silently falls back from an explicit pipeline to autodiscovery, resulting in different wiring.

### 7.1. Function Signatures Determine Binding Counts

| Definition | Input binding | Output binding |
| --- | --- | --- |
| `uppercase` | `uppercase-in-0` | `uppercase-out-0` |
| `normalize|classify` | `normalize|classify-in-0` | `normalize|classify-out-0` |
| `audit` as `Consumer<T>` | `audit-in-0` | No default output |
| `supply` as `Supplier<T>` | No default input | `supply-out-0` |
| `classify;audit` | Each definition gets its own `-in-0` | Only value-returning definitions get an output |

Names like `-in-0`/`-out-0` are logical port names, **not** broker destinations. Renaming a bean changes its implicit binding name; without an explicit destination, messages can drift to a default destination derived from the new binding name.

### 7.2. Aliases Do Not Change Function Semantics

```yaml
spring:
  cloud:
    function:
      definition: normalize|classify
    stream:
      function:
        bindings:
          "normalize|classify-in-0": ordersInput
          "normalize|classify-out-0": ordersOutput
      bindings:
        ordersInput:
          destination: orders.created
          group: classify-workers
        ordersOutput:
          destination: orders.classified
```

Once aliased, **actual binding properties** live under `ordersInput`/`ordersOutput`. A common migration mistake leaves `spring.cloud.stream.bindings.normalize|classify-in-0.destination` in an old profile while adding the alias in a new profile, fragmenting the configuration.

**Do not assume** Spring Cloud Function changed its naming rules in a given version without reading the release notes. Inspecting binding logs and runtime destinations provides stronger evidence.

## 8. Comparing Routing APIs and Routing Properties

`RoutingFunction` is part of Spring Cloud Function, typically cataloged under `functionRouter`. Depending on the scenario, it can choose the target function via properties, message headers, or a `MessageRoutingCallback`.

### 8.1. Points to Keep Stable

| Mechanism | Config/API signal | Testing implication |
| --- | --- | --- |
| Static definition | `spring.cloud.function.definition=classifyOrder` | Picks a fixed target function |
| Routing function | `spring.cloud.function.definition=functionRouter` | Enables routing function when using a suitable adapter |
| Routing expression | `spring.cloud.function.routing-expression` | Rule determining target function |
| Header routing | Header `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` | Suitable only when the adapter supports it and messages are discrete units |
| Callback | `MessageRoutingCallback` bean | Can override header/property routing decisions |
| Unroutable handling | `DefaultMessageRoutingHandler` | Controls error or fallback when no route matches |

Per Spring Cloud Function documentation, routing precedence in the imperative model follows **callback → header → application property**. If a callback bean is introduced after an upgrade, the same message may route to a different function even if the YAML property did not change.

**Reactive note:** With `Function<Flux<T>, Flux<R>>`, per-message header routing does not carry the same semantics as the imperative model. When routing an entire stream, use application properties or an appropriate mechanism; do not assume message headers are evaluated per element.

### 8.2. Security Considerations Cannot Be Ignored

Routing expressions may use SpEL. Whenever external callers can influence routing headers or properties, validate inputs and access controls. Although Spring Cloud Function applies restricted evaluation for expressions originating from message headers, **do not** treat that as permission to expose arbitrary beans or expressions to users.

Recommendations:

- Only allow approved function definitions.
- Do not trust function names sent by HTTP callers if the route triggers sensitive side effects.
- Do not unintentionally expose Actuator or mutation endpoints.
- After upgrading, test malformed payloads/headers, invalid expressions, nonexistent routes, and authorization boundaries.
- Track security advisories and prioritize patch releases.

In the **2026.0.0** announcement, Spring Cloud Function published security fixes related to JSON collection limits and class loading. Accordingly, regression tests should cover payload sizes, nesting/types, and untrusted inputs—not just happy paths.

## 9. HTTP Adapter: Same Function, Endpoint Contract Must Be Captured

`spring-cloud-function-web` can expose functions over HTTP when the right dependencies and web stack are present. However, a `Function<T,R>` bean **does not guarantee** that HTTP paths, status codes, or body encodings stay unchanged across upgrades.

Simple example:

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

When the web adapter is properly configured, an HTTP request carrying `"hello"` can be passed into the function. Exact URL paths, HTTP methods, and content conversions must be verified **on the target adapter version and application config**.

### HTTP Contract Checklist

| Item | Baseline to record | Post-upgrade check |
| --- | --- | --- |
| URL and method | Path, verb | No unintended changes |
| Request headers | `Content-Type`, `Accept`, correlation | Converters recognize them properly |
| Response | Status, headers, JSON/text body | Downstream contracts remain intact |
| Validation errors | HTTP status and error body | Does not suddenly return 500 for bad input |
| Routing | Headers, callback, expression | No unauthorized routes exposed |
| Security | Authentication/authorization, CORS | Protections are not weakened |
| Resource limits | Max payload size, timeout | No risky large-payload vectors |

### Example HTTP-Level Check

```bash
# Example only when the adapter exposes the /uppercase endpoint.
curl -i -X POST http://localhost:8080/uppercase \
  -H "Content-Type: text/plain" \
  --data "hello"
```

Tests must assert **body, status, and headers** against the baseline first, then rerun after upgrading. Never write a test that only calls `uppercase.apply("hello")` and assume the HTTP adapter was tested.

## 10. Spring Cloud Stream Configuration: Which Property Belongs to Which Layer?

An essential lesson is distinguishing namespaces:

| Namespace | Configuration target | Example |
| --- | --- | --- |
| `spring.cloud.function.*` | Function selection, routing, catalog-related config | `spring.cloud.function.definition` |
| `spring.cloud.stream.bindings.<binding>.*` | Common binding config | `destination`, `group`, `content-type` |
| `spring.cloud.stream.bindings.<binding>.consumer.*` | Common consumer | `maxAttempts`, `concurrency`, `useNativeDecoding` |
| `spring.cloud.stream.bindings.<binding>.producer.*` | Common producer | `useNativeEncoding`, partition settings |
| `spring.cloud.stream.function.bindings.*` | Implicit binding name alias | `uppercase-in-0: inputName` |
| `spring.cloud.stream.kafka.bindings.<binding>.*` | Kafka binder-specific config | `consumer.enableDlq`, `consumer.ackMode` |
| `spring.cloud.stream.rabbit.bindings.<binding>.*` | Rabbit binder-specific config | `consumer.autoBindDlq` |
| `spring.integration.poller.*` | Default polling settings | `fixed-delay`, `max-messages-per-poll` |

**Example of a misplaced property:**

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          # Do not place Kafka-specific enableDlq here:
          # consumer:
          #   enableDlq: true
```

**Example of the correct Kafka namespace:**

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: process-workers
          consumer:
            maxAttempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.errors
```

`maxAttempts` belongs to the common consumer properties, whereas `enableDlq` is specific to the Kafka binder. A property appearing in YAML without a matching binding target **does not mean** the runtime applied it.

## 11. Risky Checkpoints: Default Destination, Group, and Offset

Spring Cloud Stream defines several helpful defaults that can still surprise teams:

- If `destination` is omitted, the logical binding name may be used as the destination.
- If `group` is omitted, a consumer typically belongs to an **anonymous group** per binder rules.
- The common default `contentType` is documented by Spring Cloud Stream as `application/json`; this still interacts with the wire format and native codecs if enabled.

### 11.1. Renaming a Bean Can Make a Consumer Read the Wrong Topic

Originally:

```java
@Bean
Consumer<OrderCreated> auditOrder() { /* ... */ }
```

```yaml
spring:
  cloud:
    function:
      definition: auditOrder
    stream:
      bindings:
        auditOrder-in-0:
          destination: orders.created
          group: audit-workers
```

If you rename the bean to `recordOrder` without updating `definition` and the binding name, wiring breaks. If `destination` was omitted and the framework defaulted it to the binding name, the application may read a different destination without failing Java compilation.

**Recommendation:** in brokered environments, explicitly declare `definition`, `destination`, and `group` for every consumer requiring stable identity and progress tracking.

### 11.2. Consumer Group Is More Than a Label

In Kafka, the group controls offset tracking; in RabbitMQ, the group usually determines the receiving queue. Changing the group during an upgrade can cause:

- Kafka to apply initial offset rules for a nonexistent group; `startOffset`, retention, and topic partitions must be checked.
- RabbitMQ to create a new group queue with different topology and backlog than the old queue.
- Accidental dual groups causing **two groups to execute the same side effects**, creating duplicate processing.

Therefore, changing `group` is an **operational/data-semantics change**, not merely cosmetic renaming.

### 11.3. Do Not Treat Documented Defaults as Absolute Guarantees

In the Kafka binder, `startOffset` rules for named vs. anonymous groups are documented, yet actual behavior also depends on **committed offsets, `resetOffsets`, retention, and Kafka client configuration**. Before releasing, use an integration environment to prove whether a new group replays history or reads only new records as designed.

## 12. API/Conversion: POJO, Message<T>, Headers, and Native Codecs

Three common signatures:

```java
Function<OrderCreated, OrderClassified>

Function<Message<OrderCreated>, Message<OrderClassified>>

Function<Flux<OrderCreated>, Flux<OrderClassified>>
```

They differ in contract:

| Signature | What to test during upgrades |
| --- | --- |
| `Function<T,R>` | JSON/bytes → `T`, business rules, `R` → output wire format |
| `Function<Message<T>,Message<R>>` | All of the above + headers/correlation/type |
| `Function<Flux<T>,Flux<R>>` | Reactive lifecycle, subscription, `onError`, backpressure, and consecutive messages |

### 12.1. Content-Type Does Not Replace Schema

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          content-type: application/json
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

This is **format metadata**; Java generic types and converters determine how concrete objects are instantiated. If `OrderCreated` renames a field or changes a type, older JSON payloads may fail to parse or map incorrectly even though `content-type` is unchanged.

Tests should use realistic production-like payloads (with sensitive data redacted), including missing fields, `null`, large numbers, Unicode, unexpected content types, and unfamiliar headers.

### 12.2. Native Conversion Follows a Different Path

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            useNativeDecoding: true
        processOrder-out-0:
          producer:
            useNativeEncoding: true
```

When using binder-native decoding/encoding, the corresponding Kafka serializer/deserializer or codec must be properly configured. `content-type: application/json` **does not automatically substitute** for an incompatible Kafka `StringDeserializer`/`JsonDeserializer`.

**Distinguish failure points:**

- Native deserializer fails **before** the function is invoked.
- Framework type conversion fails at the message → Java boundary.
- Business rules fail **inside** the function.
- Output serializer fails **after** the function returns a result.

Retry/DLQ must be designed for where errors actually occur; a `try/catch` inside the function cannot catch conversion errors happening outside it.

### 12.3. Header Mapping Differs Across Adapters

`Message<OrderCreated>` may carry `correlationId`, but Kafka headers, Rabbit message properties, HTTP headers, and Lambda event metadata do not map 1:1. After an upgrade:

1. Test what Java type an incoming header has inside the bean.
2. Test that output only forwards intended headers.
3. Check the output `contentType` when the payload type changes.
4. Avoid blindly copying all transport-specific incoming headers.

## 13. Polling Suppliers and Batch Data: Defaults Can Easily Trigger Incidents

In Spring Cloud Stream, an imperative `Supplier<T>` is typically polled by default with **`fixedDelay = 1000 ms`** and **`maxMessagesPerPoll = 1`** per current documentation. Record the actual baseline values; do not infer them from local console timestamps.

```java
@Bean
Supplier<String> heartbeat() {
    return () -> "alive";
}
```

If a source always returns `"alive"`, it can emit indefinitely. Changes in packaging, bean registration, or deployment replicas can multiply producers without modifying this code.

### 13.1. Lock Down Polling Cadence Explicitly

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      max-messages-per-poll: 1
```

Or configure a dedicated poller per output binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        heartbeat-out-0:
          destination: system.heartbeat
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 1
```

`fixed-delay` is measured in milliseconds in the default configuration. Runtime tests must still account for execution duration and scheduling; a 5-second delay does not mean the broker receives records on exact 5-second wall-clock boundaries.

### 13.2. Reactive Suppliers Differ from Imperative Suppliers

A standard `Supplier<Flux<T>>` provides a Publisher, typically obtained/subscribed once to emit over the stream's lifetime. For a **finite reactive source that must be polled periodically**, use `@PollableBean`:

```java
import java.util.function.Supplier;
import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean(splittable = true)
public Supplier<Flux<String>> batchSource() {
    return () -> Flux.just("A", "B", "C");
}
```

The `@PollableBean` annotation marks a pollable source; `splittable=true` allows the framework to split elements into separate messages. `splittable` is documented as defaulting to `true`; switching it to `false` can markedly change the output contract. A `Supplier<List<T>>` and a `Supplier<Flux<T>>` do not carry identical semantics.

**Specifically:** `maxMessagesPerPoll=1` does not automatically truncate a `Flux` after its first element. When upgrading, test **poll count** and **emitted message count** separately.

## 14. Imperative and Reactive: Error/Retry Defaults Are Not Equivalent

Compare:

```java
// One invocation per message in the imperative model.
Function<OrderCreated, OrderClassified> classify

// Sets up a pipeline handling many elements.
Function<Flux<OrderCreated>, Flux<OrderClassified>> classifyReactive
```

With an imperative handler, the framework/binder can observe exceptions per message and apply `consumer.maxAttempts`/error handlers accordingly. With a reactive function, the function is typically called to **assemble the Flux**, and errors later propagate via `onError`; do not assume imperative retry/DLQ works identically per item.

### 14.1. Regression Tests Must Verify Stream Continuity After an Error

Risky example:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderClassified>> classifyReactive() {
    return orders -> orders.map(order -> {
        if (order.orderId() == null) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return new OrderClassified(order.orderId(), "STANDARD");
    });
}
```

If one bad element causes the stream to emit `onError` and terminate, subsequent valid messages may not be processed as expected. Test:

- Valid messages before a failing message.
- A failing message with `orderId=null`.
- Valid messages **after** the failure.
- Restart/resubscribe, retries, and deduplication.
- Broker acknowledgement/offsets if the pipeline interacts with a Stream binder.

Do not blindly apply `retryWhen` to the entire Publisher: resubscribing can replay earlier side effects.

### 14.2. Relation to the 2026.0.0 Upgrade

The **2026.0.0** release train announcement mentions **deprecating the reactive Kafka binder**. This does **not** mean every `Function<Flux<T>,Flux<R>>` is removed. Distinguish:

- The **reactive programming model** of Spring Cloud Function/Reactor.
- The **reactive Kafka binder artifact** in Spring Cloud Stream.
- The **conventional Kafka binder** wired to a reactive functional bean.

Seeing the shared word "reactive" is not enough to conclude both APIs share the same lifecycle or replacement path.

## 15. Retry, Error Handlers, and DLQ: Watch Per-Binder Defaults

Spring Cloud Stream provides common consumer retry properties:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processors
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

Binding Properties documentation states `maxAttempts` defaults to **3**, **including the initial attempt**. Set it to `1` to disable that retry mechanism. These defaults **must be checked against your exact version and handler type**, and do not imply DLQ is enabled.

### 15.1. Kafka DLQ Is Binder-Specific

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.errors
```

A Kafka DLT is a separate topic. Without a declared `group`, the Kafka binder DLQ mechanism has limitations for anonymous consumers. The DLT producer serializer must match the payload and native mode.

### 15.2. RabbitMQ DLQ Differs from Kafka DLT

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

RabbitMQ uses exchanges/queues, ack/nack/requeue, and DLX. Do not copy Kafka config directly to the Rabbit binder; behavioral equivalence must be **tested**, not inferred by property name mapping.

### 15.3. Custom Error Handlers Alter the Recovery Path

Spring Cloud Stream supports:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          error-handler-definition: recordError
```

In the error-handling documentation, a **custom `ErrorMessage` handler** is described as mutually exclusive with default/binder-specific error handlers. Once enabled, do not assume DLQ still runs just because `enableDlq` is set. This is an example of **configuration-driven behavior change**, not evidence that an upgrade suddenly deleted DLQ support.

**Minimum test matrix:**

| Case | Expectation to prove |
| --- | --- |
| Valid message | Processed cleanly, appropriate commit/ack progress |
| Transient error | Bounded retries with backoff |
| Permanent error | No infinite retry; proper recovery/quarantine |
| Custom error handler | Messages are not silently lost by swallowing exceptions |
| DLT/DLQ write failure | Alerting and clear recovery path exist |
| Crash after DB commit before ack | No duplicate side effects |

## 16. Announced Changes in Release Train 2026.0.0

This section separates **confirmed release events** from **behaviors requiring testing**.

According to the [Spring Cloud 2026.0.0 release announcement on November 20, 2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/):

| Area | What was announced | Impact on upgrade plan |
| --- | --- | --- |
| Spring Cloud Function | **Deprecated RSocket module** | Inventory if using Function RSocket; plan replacement rather than assuming immediate removal |
| Spring Cloud Function | **Deprecated gRPC module** | Inventory adapters and test gRPC if used by the app |
| Spring Cloud Stream | **Deprecated reactive Kafka binder** | Separate the binder artifact from using `Flux` inside functions |
| Spring Cloud Stream | **Deprecated Schema Registry component** | Check schema/serialization ecosystem and support roadmap |
| Spring Cloud Bus | Integrated into Spring Cloud Stream; **artifact coordinates unchanged** | Check dependency resolution; do not rewrite coordinates prematurely |
| Spring Cloud Function | Security fixes for JSON Collection limits and class loading controls | Test untrusted inputs and payload limits |
| Spring Cloud Stream | Security fix for deserialization subpackages | Audit deserialization trust rules and security patches |

**Deprecated ≠ removed.** Do not delete a dependency or rewrite an endpoint merely because release notes say deprecated. Check whether the artifact still functions, its support window, the recommended migration target, how much of it you use, and your migration timeline.

Conversely, a **security fix** may tighten acceptance criteria for untrusted data. A regression test failing because a payload exceeds a new limit is not necessarily a bug where you "turn off protection"; adjust the contract and enforce size/validity controls.

### Practical Impact Matrix

| What the application uses | Action required |
| --- | --- |
| Only `Function<String,String>` over HTTP | Focus on `FunctionCatalog`/web adapter and input/route security |
| `Function<T,R>` via standard Kafka binder | Focus on bindings, conversion, offset/group, and DLT |
| `Function<Flux<T>,Flux<R>>` via Kafka binder | Test reactive lifecycle and binder separately; do not assume the API itself is deprecated |
| Separate reactive Kafka binder artifact | Review deprecation and replacement/support roadmap |
| Function gRPC/RSocket adapters | Review deprecation of those specific modules |
| Stream Schema Registry | Verify schema compatibility and component roadmap |
| Spring Cloud Bus | Inspect classpath/release train even though coordinates are unchanged |

## 17. Legacy APIs: Do Not Confuse "Recommended" with "Removed"

Spring Cloud Stream historically used channel-interface annotations for message handlers and `@StreamListener`. Since Stream 3.x, documentation recommends the **functional programming model** with `Supplier`, `Function`, and `Consumer`. However, one model being recommended **is not proof** that the older model has been removed in every current version.

A sensible migration path when a legacy project uses annotation-based sources/sinks:

1. Record input/output destinations, groups, content types, and native codecs.
2. Identify equivalent `Function<I,O>`, `Consumer<T>`, or `Supplier<T>` handlers.
3. Decouple business logic from annotations and broker APIs.
4. Replace implicit/explicit channel names with `<function>-in-0` / `-out-0` or intentional aliases.
5. Compare message schemas, headers, retries, groups, and offsets/requeues.
6. Remove legacy binding code only after integration tests pass against a real broker.

**Do not assume** `@Bean Function` guarantees 100% parity with a legacy handler regarding thread affinity, concurrency, headers, or acknowledgements. Those parameters live outside the business function.

## 18. Property Migration: Build a Mapping Table, Do Not Bulk-Edit by Intuition

Build a table from **baseline documentation** and **target documentation**, paired with observed runtime values.

| Business intent | Current key/property to locate | What to verify |
| --- | --- | --- |
| Function selection | `spring.cloud.function.definition` | Bean names, definition count, composition |
| Routing condition | `spring.cloud.function.routing-expression` | Callback/header/property precedence, security |
| Binding alias | `spring.cloud.stream.function.bindings.*` | Implicit → explicit mapping |
| Destination | `spring.cloud.stream.bindings.*.destination` | Actual topic/exchange |
| Consumer group | `spring.cloud.stream.bindings.*.group` | Offset/queue identity |
| Content type | `spring.cloud.stream.bindings.*.content-type` | Converter/codec and headers |
| Input concurrency | `spring.cloud.stream.bindings.*.consumer.concurrency` | Ordering, scaling, and broker behavior |
| Retry count | `spring.cloud.stream.bindings.*.consumer.maxAttempts` | Total attempts (including initial) |
| Kafka DLT | `spring.cloud.stream.kafka.bindings.*.consumer.enableDlq` | Group, DLT, serializer |
| Rabbit DLQ | `spring.cloud.stream.rabbit.bindings.*.consumer.autoBindDlq` | DLX/queue topology |
| Default poller | `spring.integration.poller.fixed-delay` | Supplier cadence |
| Binding poller | `spring.cloud.stream.bindings.*.producer.poller.fixed-delay` | Correct output binding |
| Native codec | `consumer.useNativeDecoding` / `producer.useNativeEncoding` | Compatible serializer/deserializer |

**This table is a comparison checklist, not a claim that these keys were renamed in 2026.0.0.** Many keys remain active in current documentation. A proper migration marks "RENAME" only if docs or metadata confirm a property actually changed; otherwise classify as "RETAIN", "SEMANTIC REVIEW", "DEPRECATED", or "REMOVED".

### Sample Evidence Table

| Property | Baseline | Target | Classification | Evidence |
| --- | --- | --- | --- | --- |
| `spring.cloud.function.definition` | `classifyOrder` | `classifyOrder` | RETAIN | Startup + function lookup test |
| `processOrder-in-0.consumer.maxAttempts` | 3 | 3 | RETAIN / VERIFY | Binding metadata and retry test |
| `consumer.group` | `audit-workers` | `audit-workers` | RETAIN, data-critical | Kafka offset/Rabbit queue test |
| Custom project key | Unknown | Unknown | UNKNOWN | Locate metadata, owner, and logs |

Do not put unverified assumptions into a list of "confirmed breaking changes."

## 19. Creating a Java Example Suitable as a Regression Fixture

The fixture below keeps business logic in plain Java while including a header-aware branch for testing adapters:

```java
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class UpgradeFixtureApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeFixtureApplication.class, args);
    }

    public record OrderCreated(
            String eventId,
            String orderId,
            long totalInCents) {}

    public record OrderClassified(
            String eventId,
            String orderId,
            String priority) {}

    @Bean
    Function<OrderCreated, OrderClassified> classifyOrder() {
        return order -> {
            if (order.orderId() == null || order.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId required");
            }

            return new OrderClassified(
                    order.eventId(),
                    order.orderId(),
                    order.totalInCents() >= 100_000L
                            ? "PRIORITY" : "STANDARD");
        };
    }

    @Bean
    Function<Message<OrderCreated>,
             Message<OrderClassified>> classifyWithHeaders() {

        return input -> {
            OrderCreated order = input.getPayload();

            var output = new OrderClassified(
                    order.eventId(),
                    order.orderId(),
                    order.totalInCents() >= 100_000L
                            ? "PRIORITY" : "STANDARD");

            var builder = MessageBuilder.withPayload(output)
                    .setHeader("processedBy", "upgrade-fixture");

            Object correlationId =
                    input.getHeaders().get("correlationId");

            if (correlationId != null) {
                builder.setHeader("correlationId", correlationId);
            }

            return builder.build();
        };
    }

    @Bean
    Consumer<OrderClassified> auditOrder() {
        return value -> System.out.printf(
                "AUDIT %s %s %s%n",
                value.eventId(),
                value.orderId(),
                value.priority());
    }
}
```

**Note:** to test a single pipeline, pick a **specific definition**. Do not let all three beans bind simultaneously without reason, because `classifyOrder` and `classifyWithHeaders` could read the same destination with different processing behavior.

### Fixture Payload

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "totalInCents": 150000
}
```

Expected output:

```json
{
  "eventId": "evt-101",
  "orderId": "ORD-101",
  "priority": "PRIORITY"
}
```

Keep sample events fixed as contract fixtures; do not modify them at the same time as upgrading dependencies so comparisons remain meaningful.

## 20. Sample Stream Configurations for Before–After Comparison

Example selecting **one function** that accepts a POJO and emits a POJO:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder

    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: classify-workers
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000

        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

This YAML does not select Kafka or RabbitMQ on its own if multiple unconfigured binders exist in the project; dependencies and binder connections must be specified. In brokered tests, supply ports/URLs/credentials via the test environment rather than hardcoding secrets in lessons.

### When Testing Multiple Independent Definitions

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder;auditOrder

    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: classify-workers
          content-type: application/json

        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json

        auditOrder-in-0:
          destination: orders.classified
          group: audit-workers
          content-type: application/json
```

`;` selects two independent definitions; `auditOrder` receives `classifyOrder`'s output **only because they share the destination**. If you rename `orders.classified` on one binding, they will not auto-connect.

### When Testing a Composed Pipeline

Suppose you have two type-compatible beans `normalizeOrder` and `classifyOrder`:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|classifyOrder
    stream:
      bindings:
        "normalizeOrder|classifyOrder-in-0":
          destination: orders.created
          group: classify-workers
          content-type: application/json
        "normalizeOrder|classifyOrder-out-0":
          destination: orders.classified
          content-type: application/json
```

This is an **alternative configuration**, requiring a `normalizeOrder` bean returning `OrderCreated` to run. Do not merge all three sample configs into one profile expecting them to run as three sequential stages.

## 21. Layered API and Behavior Testing

### 21.1. Business Unit Tests

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BusinessContractTest {

    @Test
    void mapsPriorityTheSameWay() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyOrder();

        var output = function.apply(
                new UpgradeFixtureApplication.OrderCreated(
                        "evt-101", "ORD-101", 150_000L));

        assertEquals("PRIORITY", output.priority());
        assertEquals("ORD-101", output.orderId());
    }

    @Test
    void rejectsInvalidOrder() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyOrder();

        assertThrows(IllegalArgumentException.class, () ->
                function.apply(
                        new UpgradeFixtureApplication.OrderCreated(
                                "evt-102", " ", 10L)));
    }
}
```

These tests target the business bean directly and **do not test adapters**. Keep them so you know when failures originate from business logic rather than framework migration.

### 21.2. Header Tests

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class MessageContractTest {

    @Test
    void keepsCorrelationId() {
        var app = new UpgradeFixtureApplication();
        var function = app.classifyWithHeaders();

        var request = MessageBuilder.withPayload(
                new UpgradeFixtureApplication.OrderCreated(
                        "evt-101", "ORD-101", 150_000L))
                .setHeader("correlationId", "trace-789")
                .build();

        var response = function.apply(request);

        assertEquals("trace-789",
                response.getHeaders().get("correlationId"));
        assertEquals("upgrade-fixture",
                response.getHeaders().get("processedBy"));
        assertEquals("PRIORITY",
                response.getPayload().priority());
    }
}
```

After the Java test passes, integration tests must confirm headers still traverse HTTP/Kafka/Rabbit/AWS as contracted. Never treat a `MessageBuilder` unit test as proof of binder header mapping.

### 21.3. FunctionCatalog Integration Tests

With a real application context, test:

- The catalog contains the exact function names meant to be exposed.
- `catalog.lookup("classifyOrder")` locates the function.
- Composition `normalizeOrder|classifyOrder` resolves cleanly when both beans exist.
- When `single-function-fallback-enabled=false` is set, looking up a wrong name does not silently return the sole bean.
- No debug or internal function beans are unintentionally exposed.

Use `@SpringBootTest` or a suitable Spring context test. Since the catalog may return wrappers, verify using actual data and contracts; do not assert that the wrapper and raw bean share the same class.

### 21.4. Stream Test Binder and Real Brokers

Spring Cloud Stream's test binder verifies selection, binding naming, and framework conversion. Afterward, verify against real Kafka/RabbitMQ or Testcontainers for:

- Topic/queue and group identity.
- Payload bytes, content type, and headers.
- Retries, backoff, and DLQ/DLT when the handler throws.
- Redelivery after restart and idempotency.
- Native serializers/deserializers.
- Offsets/acks and ordering across partitions/concurrency.

**Contract tests should be version-independent**: the same fixtures, same expected semantics, and same suite run on baseline and target. When results diverge, classify the change before modifying the test.

## 22. Golden Tests: Repeatable Before–After Comparisons

A golden test stores **fixed inputs** and **approved outputs/behaviors**, rather than snapshotting entire logs with changing timestamps.

| Test | Input | Observation to store | Risk detected |
| --- | --- | --- | --- |
| Lookup | Bean name `classifyOrder` | Catalog resolves exact name | Changed fallback/eligibility |
| HTTP | JSON `evt-101` | Status, body, headers | Changed routing/conversion |
| Kafka | JSON record + key/headers | Output schema, partition behavior | Changed native codec/group |
| RabbitMQ | Sample AMQP message | Receiving queue, DLQ on error | Changed topology/ack |
| Supplier | 2 poll cycles | Invocation count and message count | Changed cadence/splitting |
| Reactive | 2 valid + 1 error + 1 valid | Stream stays alive or stops | `onError` kills stream |
| Routing | Valid header, unknown header | Routed properly or rejected | Wrong function/security |
| Retry | Transient exception twice then success | Total attempts/backoff | Unexpected retry behavior |
| DLQ | Poison message | Failed payload is quarantined | Silent drop |
| Serverless | Real event source | Handler, output, error shape | Changed adapter/runtime |

### Setting Thresholds and Pass Criteria

- **Qualitative:** destinations, function names, schemas, groups, and error routes must be **exact matches**.
- **Quantitative:** latency, throughput, and startup time may vary within approved tolerances.
- **Security:** inputs rejected by new security limits must be analyzed; never loosen tests to accept unsafe data.
- **Determinism:** do not assert cross-partition ordering in Kafka or across consumer groups when the architecture makes no cross-group ordering guarantee.

Golden tests require sanitized data and should be stored alongside schema versions and expected contracts.

## 23. Monitoring Effective Configuration: Did the Property Actually "Bind"?

A property appearing in a YAML file is **not enough** to conclude the framework applied it.

Common causes:

- Running a different profile from the file you edited.
- Environment variables overriding values in `application.yml`.
- Binder name differing from config name (`kafka` vs. a custom named binder instance).
- Binding aliased while the property remains under the implicit name.
- Consumer property placed under producer (or vice versa).
- Property belonging to a binder namespace not present on the classpath.
- Property deprecated/removed and no longer read by the binder.
- Container artifact running an older build.

### How to Verify

1. Inspect effective build dependencies.
2. Review startup logs for `FunctionCatalog`, bindings, and binders.
3. Check actuator configuration/bindings if enabled and **properly secured**.
4. Use integration tests to send messages to the **real destination**.
5. Inspect actual topics/queues, consumer groups/queue depths, and DLQs.
6. Write tests asserting critical behavior rather than merely checking that a YAML file contains a line.

`/actuator/env`, `/actuator/configprops`, or management endpoints can leak sensitive data. Never expose them publicly on the Internet or print raw credentials in test logs.

### Configuration Source Checklist

```text
application.yml
    ↓
application-<profile>.yml
    ↓
environment variables / command-line args / config server
    ↓
Spring Environment (effective value)
    ↓
configuration binding to target object
    ↓
Function/Stream/binder runtime behavior
```

This diagram is a high-level view; exact property-source precedence is governed by Spring Boot and may include additional sources like config server, test properties, and system properties. Do not use this diagram in place of the official precedence table for your target Boot version.

## 24. Comparing AWS Lambda and Serverless Environments

A function reused in serverless adds extra layers to check: **adapter handler**, **Java runtime**, **event source**, and **how environment variables are passed**.

For example, the Spring Cloud Function AWS adapter commonly uses the handler:

```text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
```

A dotted Spring property can map to an environment variable via Spring Boot's relaxed binding rules. The AWS adapter documentation gives the example:

```text
spring.cloud.function.definition
    -> spring_cloud_function_definition
```

Test the actual value the runtime receives. Do not assume hyphens, dots, or camelCase in every property name are interpreted identically across all platforms and Boot conditions.

### FaaS Test Scenarios

- Single function selected via an explicit env var.
- Multiple function beans with `definition` or policy-based routing.
- JSON events or schema-accurate SQS/Kinesis/API Gateway events.
- Parse/validation errors and event-source retries/partial batch failures.
- Timeout, cold start, memory, and Java runtime selection.
- Secrets/permissions and log masking.
- Artifact layout/handler class after upgrading adapter dependencies.

**Do not copy Kafka retry and DLT rules onto AWS Lambda merely because both use `Function<T,R>`**. Ack/retry semantics for SQS/Kinesis/API Gateway are governed by the platform and event source integration.

## 25. Deployment, Canary, and Rollback Decision Checklist

### Pre-Upgrade

- [ ] Identify baseline/target versions: Boot, Cloud BOM, Function, Stream, binders, Java runtime.
- [ ] Save current dependency graph output and artifact/image digests.
- [ ] Record all function names, compositions, routing, and message schemas.
- [ ] Record explicit `definition`, destinations, groups, and Supplier cadences.
- [ ] Record retry/DLQ settings, content types, native codecs, header mappings, and default assumptions.
- [ ] Review official release notes, deprecations, and security advisories.
- [ ] Prepare representative test data for valid, invalid, and edge-case payloads.

### On Staging

- [ ] Unit tests and `FunctionCatalog` lookup/composition tests pass.
- [ ] HTTP/Stream/Lambda adapter contract tests pass for everything in scope.
- [ ] No ignored properties or miswired destinations.
- [ ] Retries/DLQ/acks and redelivery verified against a real broker.
- [ ] Reactive streams continue or stop per designed policy.
- [ ] Backward/forward schema compatibility confirmed.
- [ ] Resource usage, startup latency, and error rates within thresholds.
- [ ] Security changes preserved, not disabled just to "pass tests."

### During Release

- [ ] Roll out canary groups and monitor error rate, lag, queue depth, and DLT/DLQ.
- [ ] Automated thresholds or on-call owner authorized to halt rollout.
- [ ] Ability to restore the previous artifact by digest, not a mutable tag.
- [ ] Rollback does not break DB/event schemas emitted during the canary window.
- [ ] Two consumer versions do not unintentionally use **different groups**.
- [ ] Plan exists to handle messages already emitted by the target version during testing.

### How to Classify Test Outcomes

| Test result | Action |
| --- | --- |
| API does not compile | Identify changed method/annotation and migration path |
| API compiles but contract differs | Compare property/adapter behavior and decide whether to accept or fix |
| Property silently ignored | Verify namespace, key spelling, and target metadata |
| Behavior changed due to security fix | Do not disable protections; update the contract |
| Error path changed and drops data | Halt rollout, fix recovery, and retest |
| Only performance changed | Measure thresholds, check tuning, do not mask functional bugs |
| All quality gates pass | Monitored canary, then expand rollout percentage |

Rolling back a JAR or image **cannot unsend** already-published messages or undo applied data migrations. When both producers and consumers are upgrading, ensure event schemas remain compatible during overlap.

## 26. Hands-On Exercises

### Exercise 1: Classify a Change

You rename bean `classifyOrder` to `classify` while keeping:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
```

Why might the application fail to bind or bind incorrectly? Is this evidence that Spring Cloud Function changed its binding naming rules? Propose the fix and tests.

### Exercise 2: One Function Becomes Two Functions

Before upgrading, the application had a single bean `uppercase` and did not declare `definition`. After adding `reverse`, the application no longer picks the desired bean. Analyze the cause, write the explicit configuration, and explain when `single-function-fallback-enabled: false` helps.

### Exercise 3: Spot a Misplaced DLQ Configuration

Given:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          consumer:
            enableDlq: true
```

If using the Kafka binder, fix the namespace for `enableDlq` and add a `group`. Why can a misplaced property pass the build while production still ends up without a DLT?

### Exercise 4: Compare Routing

An application has a `MessageRoutingCallback`, an application property `routing-expression`, and a message header specifying a different target function. Determine precedence per Spring Cloud Function docs, then propose tests for both imperative and reactive models. Why should untrusted callers not be allowed to arbitrarily pick internal functions?

### Exercise 5: Baseline and Target Mismatch on Supplier

Before upgrading, a source emits one message every 5 seconds. After upgrading, it emits every 1 second. List possible causes involving `fixed-delay`, active profiles, replica count, `Supplier` type, and `@PollableBean` before concluding the framework changed defaults.

### Exercise 6: Switching to Native Kafka Decoding

A `Function<OrderCreated,OrderClassified>` was receiving JSON via a converter. After setting `useNativeDecoding: true`, the consumer receives `byte[]` or `String` instead of the DTO. Name the components to check and why `content-type: application/json` alone may not suffice.

### Exercise 7: Evaluate Release Train 2026.0.0

An application uses `Function<Flux<T>,Flux<R>>` with the standard Kafka binder and a Spring Cloud Function gRPC module. In release 2026.0.0, which parts were announced as deprecated? Why must you not infer that the reactive Function API was removed? Draft a migration inventory for both parts.

### Exercise 8: Write a Golden Test

Pick an order-processing flow over HTTP or Kafka and define:

- Input event JSON and headers.
- Expected output schema and status/destination.
- Error case and recovery path.
- Default assumptions to lock down in config.
- How to run the same suite against both baseline and target artifacts.

### Exercise 9: Rollback Scenario

A canary emitted events containing a new field that the old consumer version cannot understand. If you roll back the producer and Function immediately, what happens to events already sitting in the broker? Design a schema evolution and rollback plan before deploying.

### Self-Assessment Questions

1. How do API compatibility and behavioral compatibility differ?
2. Does `FunctionCatalog.lookup(...)` always return the raw bean?
3. Why should you declare `spring.cloud.function.definition` even when an app has only one function?
4. Do `|` and `;` produce the same topology?
5. Does aliasing a binding change the function's input/output order?
6. When changing a consumer group, how can Kafka offsets or RabbitMQ queues be affected?
7. Does `content-type` replace Kafka's native serializer/deserializer?
8. Does `maxAttempts` include the initial invocation?
9. Why can a custom error handler stop a DLT from running as expected?
10. Does deprecating the reactive Kafka binder mean `Flux` functions are deprecated?
11. Does deprecated mean removed?
12. How do you prove a property in YAML actually took effect?
13. Is passing a function unit test enough to prove the HTTP/Lambda adapter works?
14. Why can a security fix change payload-acceptance behavior?
15. When must you halt a rollout and roll back, and how does rollback still depend on event schemas?

## 27. Summary

Upgrading Spring Cloud Function must be treated as a **contract comparison problem**, not merely bumping dependency versions:

- **API:** check functional beans, `FunctionCatalog`, wrapper invocation, composition, routing, and adapters.
- **Configuration:** verify exact namespaces (`spring.cloud.function.*`, `spring.cloud.stream.bindings.*`, Kafka/Rabbit binder properties), aliases, pollers, content types, and native codecs.
- **Default behavior:** verify single-function fallback, destinations/groups, Supplier polling, retries, DLQ, reactive `onError`, and security limits via tests on the exact target version.
- **Release notes:** separate confirmed changes and deprecations from unverified assumptions; for Spring Cloud **2026.0.0**, pay attention to the Function gRPC/RSocket deprecations, Stream reactive Kafka binder/Schema Registry deprecations, and published security fixes.
- **Testing:** run the same golden/contract test suite on baseline and target, then verify real brokers, HTTP, and serverless runtimes.
- **Deployment:** roll out in phases, monitor closely, define rollback thresholds, and plan schema compatibility for in-flight/stored events.

Keeping `Supplier`, `Function`, and `Consumer` pure business logic lets you reuse code across HTTP, events, or serverless. Yet **every adapter carries its own operational contract**; claiming "behavior did not change" is only trustworthy with evidence at the exact adapter and system boundaries.

### References

- [Spring Cloud 2026.0.0 — Release announcement (November 20, 2026)](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud — Release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Function — Programming model, FunctionCatalog, composition, routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/)
- [Spring Cloud Function — AWS adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Kafka Binder configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
