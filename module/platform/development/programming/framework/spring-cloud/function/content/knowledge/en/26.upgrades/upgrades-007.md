# Mapping Legacy Documentation to the Current Cloud Generation

## 1. Why Is Old Documentation Still Accurate Yet No Longer Suitable for New Projects?

A development team has been maintaining a Spring Cloud Stream application for years. The code contains annotations such as `@EnableBinding`, `@Input`, `@Output`, and `@StreamListener`; a `Processor` interface defines input/output channels; tests use `MessageCollector`. The documentation accompanying the app was written for an older release train and still accurately explains how that system behaves.

When upgrading Spring Boot and Spring Cloud, the team searches for a newer guide. They see examples using `@Bean Function<T,R>`, `spring.cloud.function.definition`, binding names like `processOrder-in-0`, and `InputDestination`/`OutputDestination`. The team concludes the old docs are wrong and deletes all legacy code. Yet that approach easily drops critical details such as destinations, consumer groups, headers, retries, binders, and schemas.

**Old documentation is not automatically wrong just because it is old.** It may be completely accurate for the version that system is running. Trouble arises when you grab examples from one framework generation, mix them with dependencies from another generation, and expect identical APIs, configurations, and behaviors.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_FUNCTION** module. The module focuses on developing reusable business logic with `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, composition, and message conversion independent of calling protocols. When comparing documentation, therefore, distinguish what belongs to the **stable business contract**, what belongs to the **framework API**, and what belongs to the **adapter/binder/runtime**.

After this lesson, you will know how to identify exact documentation versions, read release trains and compatibility matrices, recognize legacy annotation models, migrate to the functional model, verify configurations, bindings, error handling, and test binders, and plan evidence-based upgrades instead of mechanically copying the newest snippet.

## 2. Four Questions to Answer Before Reading Any Documentation Page

When you find a Spring Cloud Function or Spring Cloud Stream example, do not start by copying code. Determine:

1. **Which version does the page document?** Is it 3.2.10, 5.0.x, 5.1.0, or a SNAPSHOT?
2. **Which release train and Spring Boot version manage the dependencies?** Individual module versions do not replace the compatibility matrix.
3. **Which programming model does the example use?** Annotation/channel model, functional beans, Spring Integration, or reactive functions?
4. **Which layer does the example address?** Business functions, `FunctionCatalog`, Stream binders, HTTP/serverless adapters, or cloud provider runtimes?

An example can be syntactically valid yet wrong for your project if even one of these four factors differs.

### 2.1. Spotting Versions in URLs and Banners

| Clue | Interpretation | How to use |
| --- | --- | --- |
| `/docs/3.2.10/reference/...` | Version-pinned documentation | Use to understand 3.2.10 baseline behavior |
| `/reference/5.0/...` | Documentation for the 5.0 branch | Pick when target dependencies belong to this branch |
| `/reference/` without version | Usually the site's default/current branch redirect | Check the banner, release notes, and displayed version |
| `5.1-SNAPSHOT` or `5.1.0-M1` | Development/milestone build | Do not treat as GA documentation if your project uses GA |
| Release blog | Summary of changes in a release | Use to spot topics requiring deep reading in reference/release notes |
| Javadoc | API signatures and deprecation status per artifact | Use to verify a specific class or method |

**Do not look only at the version number in a heading.** A SNAPSHOT page may show newer content than GA that can still change before release. Conversely, an unversioned reference URL may redirect to a different stable branch than the newest module in a newly announced release train.

### 2.2. An Important Source-Precedence Rule

Prioritize sources in this order:

1. Version-matched release train compatibility matrix and release notes.
2. Version-matched module reference documentation.
3. Javadoc/API docs of the resolved artifact.
4. Official migration guides and issues/changelogs.
5. Technical blogs or community posts.
6. Q&A threads, forum snippets, and unversioned examples.

Lower-tier sources remain useful for clues, yet should never serve as sole evidence for migration decisions.

## 3. Current Generation at the Time of Comparison

As of **November 24, 2026**, Spring Cloud **2026.0.0** was announced GA on **November 20, 2026**. This release train builds on Spring Boot **4.2.0**; the release train reference lists Spring Cloud Function **5.1.0** and Spring Cloud Stream **5.1.0**.

| Component | Current milestone used in this lesson | Role |
| --- | --- | --- |
| Spring Boot | 4.2.0 | Application platform and auto-configuration |
| Spring Cloud release train | 2026.0.0 | Coordinated compatible versions of Spring Cloud projects |
| Spring Cloud Function | 5.1.0 | Functional model, `FunctionCatalog`, conversion, and adapters |
| Spring Cloud Stream | 5.1.0 | Bindings, binders, messaging, and test binder |
| Java runtime | Chosen per Boot, adapters, and cloud provider | JVM executing the application |
| Kafka/Rabbit binder | Artifacts managed by the release train | Connects to specific middleware |

This is a **reference milestone at the time of writing**, not a recommendation that every system must upgrade immediately. If your app runs on a still-supported release train, choose its matching compatible branch rather than bumping individual modules to their highest numbers.

Official sources:
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Train Reference — 2026.0.0](https://docs.spring.io/spring-cloud-release/reference/index.html)

### 3.1. Release Train Version Differs from Module Version

`2026.0.0` is the **release train** version. `5.1.0` is the individual project version for Function and Stream. Spring Boot `4.2.0` is the Boot platform version. These three numbers are not interchangeable.

Illustrative Maven BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream</artifactId>
    </dependency>
</dependencies>
```

Gradle example using `platform`:

```kotlin
dependencies {
    implementation(
        platform("org.springframework.cloud:spring-cloud-dependencies:2026.0.0")
    )
    implementation("org.springframework.cloud:spring-cloud-function-context")
    implementation("org.springframework.cloud:spring-cloud-stream")
}
```

Do not specify separate versions on individual modules when managed by the BOM unless you have a verified reason and confirmed compatibility. Overriding one module can skew Function context, Stream binders, adapters, and other Spring dependencies.

### 3.2. Inspect Resolved Dependencies, Not Only the POM

```bash
# Maven
./mvnw help:effective-pom
./mvnw dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-cloud-function-context

java -version
./mvnw -version
./gradlew --version
```

These commands are instructions for your own project; capture results from the exact module/artifact being deployed. A version written in a parent POM does not prove it is the version packaged in the final JAR.

## 4. Migration History: From Channel/Annotation Model to the Functional Model

Spring Cloud Stream began with a message-channel and annotation model. Users defined interfaces with `@Input`/`@Output`, enabled binding with `@EnableBinding`, and handled messages with `@StreamListener` or Spring Integration annotations.

Spring Cloud Function introduced Java's `Supplier`, `Function`, and `Consumer` functional interfaces as a programming model usable across execution contexts. Spring Cloud Stream integrated the functional model starting in **2.1**. Stream **3.x** docs recommended functional implementations and marked the native annotation-based model (`@EnableBinding`/`@StreamListener`) deprecated.

| Stage | Docs/code markers | How to interpret |
| --- | --- | --- |
| Stream 1.x/2.0 and older docs | `@EnableBinding`, `@Input`, `@Output`, `@StreamListener` | Channel/annotation model was the standard pattern |
| Stream 2.1 | Integrated functional beans from Spring Cloud Function | Teams can begin adopting `Supplier`/`Function`/`Consumer` |
| Stream 3.x | Functional model recommended; native annotation model deprecated | Plan migration rather than expanding legacy code |
| Stream 3.x onward | Reactive support moved to Function's native Reactor support; `spring-cloud-stream-reactive` discontinued | Use `Flux`/`Mono` in functional signatures |
| Stream 3.x | Legacy test support binder/`MessageCollector` progressively replaced by Integration Test Binder | Migrate tests to `InputDestination`/`OutputDestination` |
| Stream 5.1.0 in train 2026.0.0 | Functional model and binders continue under the new release train | Use version-matched reference; do not copy 2.x configs |

**Careful:** "deprecated" does not mean "deleted in every version." Stream 3.2.10 docs clearly mark the annotation model deprecated, whereas later references may still mention some annotation/Integration configs as legacy or compatibility options. Verify which APIs actually exist in your target artifact before planning removals.

### 4.1. Three Statuses Not to Conflate

- **Deprecated:** should not be used in new code; may still run.
- **Discontinued/not distributed:** module is no longer released the old way; a replacement mechanism may exist.
- **Removed:** API/artifact no longer exists in the target version.

One release-note line saying "deprecated" does not prove an artifact vanished. Nor does a discontinued module necessarily follow the exact same migration path as a deprecated annotation.

## 5. Comparing the Legacy Model: `@EnableBinding` and `@StreamListener`

A common legacy example:

```java
@EnableBinding(Processor.class)
public class LegacyOrderHandler {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public OrderClassified classify(OrderCreated order) {
        return new OrderClassified(
                order.orderId(),
                order.totalInCents() >= 100_000L
                        ? "PRIORITY" : "STANDARD");
    }
}
```

This illustrates the legacy `Processor` interface pattern. It expresses three things:

1. `@EnableBinding` activates binding interfaces.
2. `Processor.INPUT` and `Processor.OUTPUT` are explicit channel names.
3. `@StreamListener` binds the method to the input channel; `@SendTo` targets the output channel.

When reading legacy docs, never overlook destination/group, content type, retry, and binder configurations. Those remain essential operational details that must carry over into the new configuration.

### 5.1. Corresponding Functional Model

Modern code:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> new OrderClassified(
            order.orderId(),
            order.totalInCents() >= 100_000L
                    ? "PRIORITY" : "STANDARD");
}
```

Configuration:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

| Legacy model | Functional model | What to preserve |
| --- | --- | --- |
| `@EnableBinding(Processor.class)` | Functional bean + Stream auto-configuration | Binder and topology |
| `Processor.INPUT` | `classifyOrder-in-0` | Input destination/group |
| `Processor.OUTPUT` | `classifyOrder-out-0` | Output destination |
| `@StreamListener` method | `Function<I,O>` | Business rules, validation, and exception semantics |
| `@SendTo` | Return value of `Function` | Output mapping |
| Interface channel names | Binding naming convention/aliases | Configuration keys and profiles |

This is a **conceptual** mapping, not mechanical annotation replacement. Additional legacy handler behaviors—header mapping, partitioning, conditional dispatch, or overloaded methods—must be migrated explicitly and tested.

## 6. Legacy `Source`/`Sink` vs. Current `Supplier`/`Consumer`

In legacy Stream docs, source and sink apps typically used the `Source` and `Sink` interfaces and channel constants.

Legacy pattern:

```java
@EnableBinding(Source.class)
public class LegacyOrderSource {

    @Bean
    @InboundChannelAdapter(
        value = Source.OUTPUT,
        poller = @Poller(fixedDelay = "1000"))
    public MessageSource<String> source() {
        return () -> new GenericMessage<>("order-created");
    }
}
```

The functional model typically uses `Supplier<T>`:

```java
@Bean
Supplier<String> orderSource() {
    return () -> "order-created";
}
```

Stream configuration:

```yaml
spring:
  cloud:
    function:
      definition: orderSource
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
```

A legacy consumer used a channel listener; the new model uses:

```java
@Bean
Consumer<OrderCreated> auditOrder() {
    return order -> auditService.record(order);
}
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

**Do not swap pollers blindly.** For `Supplier`, verify whether it is imperative or reactive, its poll interval, messages per poll, whether the source is finite or infinite, and replica count. A `Supplier` returning `Flux<T>` has a different lifecycle from one returning a single item; finite reactive sources require checking polling mechanisms such as the `@PollableBean` marker where appropriate.

## 7. Functional Model: `FunctionCatalog` Standardizes Invocation

Spring Cloud Function registers eligible `Supplier`, `Function`, and `Consumer` beans in `FunctionCatalog`. Looking up via the catalog returns a framework-instrumented/wrapped function supporting features like type conversion and composition.

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Autowired
FunctionCatalog catalog;

void invoke() {
    Function<?, ?> function = catalog.lookup("uppercase");
}
```

Fetching the bean straight from `ApplicationContext` is not guaranteed to match looking it up through `FunctionCatalog`, because the raw bean lacks the framework's wrapper/conversion behavior.

### 7.1. `definition` Is Integration Configuration

```yaml
spring:
  cloud:
    function:
      definition: uppercase
```

If only one function exists, the framework can locate it via fallback even without a name. Still, documentation recommends setting `spring.cloud.function.definition` explicitly when integrating with frameworks like Spring Cloud Stream.

To enforce exact name-only lookups:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
      single-function-fallback-enabled: false
```

This reduces accidental reliance on having only one functional bean in the application context.

### 7.2. Ineligible Definitions

Dependencies might contribute Java functional beans that are not meant to be exposed as functions. Exclude bean names via:

```properties
spring.cloud.function.ineligible-definitions=internalFunction,debugFunction
```

Use this to govern catalog eligibility, not as a substitute for authentication/authorization on adapters.

## 8. New Binding Names Differ from Legacy Channel Names

In the functional model, Spring Cloud Stream derives binding names from the function name and index:

- Input: `<functionName>-in-<index>`.
- Output: `<functionName>-out-<index>`.

For example, `uppercase` gets:

```text
uppercase-in-0
uppercase-out-0
```

Destination is the broker resource; binding name is the configuration port inside the app. Do not confuse the two.

### 8.1. Aliases to Preserve Configuration Keys

You can map implicit binding names to explicit names:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      function:
        bindings:
          uppercase-in-0: textInput
          uppercase-out-0: textOutput
      bindings:
        textInput:
          destination: text.raw
          group: text-workers
        textOutput:
          destination: text.uppercase
```

Once aliased, subsequent binding properties reference `textInput`/`textOutput`. Aliases do not alter bean names, destinations, or event types.

Stream docs note that aliases add a layer of indirection. When longer descriptive keys are unnecessary, implicit names are often easier to trace.

### 8.2. Binding Names for Compositions

If `definition` is:

```yaml
spring:
  cloud:
    function:
      definition: normalize|classifyOrder
```

the logical bindings include the composition:

```text
normalize|classifyOrder-in-0
normalize|classifyOrder-out-0
```

Changing the composition to `validate|normalize|classifyOrder` alters the implicit binding names. Aliases can keep downstream property names stable, yet you must update the alias key to the new implicit name.

## 9. Modern Composition and How to Read Old Examples

Spring Cloud Function supports declarative composition using `|` or commas:

```yaml
spring:
  cloud:
    function:
      definition: normalize|classifyOrder
```

Output from `normalize` feeds `classifyOrder`. Types must align between steps.

Semicolons in Stream configs select multiple independent definitions:

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder;auditOrder
```

Both functions are bound independently; `;` does not wire the first function's output into the second function's input.

| Symbol | Meaning |
| --- | --- |
| `|` | Composition/pipeline |
| `,` | Alternative supported composition syntax |
| `;` | Multiple independent definitions in supported Stream contexts |

Some legacy docs describe pipelines using channels/`@SendTo`; when converting to composition, verify whether a broker boundary is still required. `FunctionCatalog` composition does not create topics, queues, transactions, or durable checkpoints.

## 10. Reactive: Old Module Discontinued, Reactor API Lives in Function

Older docs reference the `spring-cloud-stream-reactive` dependency. Release train 2020.0.x and Stream 3.x docs note that this module was discontinued as of Stream 3.0; reactive support is provided directly via Spring Cloud Function/Reactor.

Functional reactive pattern:

```java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
```

Do not add `spring-cloud-stream-reactive` just to use `Flux` in function signatures when the current version already supports reactive functions natively.

### 10.1. Reactive Does Not Mean "Imperative Handler with More Threads"

- Imperative `Function<T,R>` typically executes per message with handler semantics.
- Reactive `Function<Flux<T>,Flux<R>>` builds a pipeline over a publisher.
- `Supplier<Flux<T>>` may be invoked once to establish a long-lived stream.
- Finite reactive suppliers may need explicit polling; `@PollableBean` marks this case in current Function docs.

Do not mechanically apply imperative handler retry/DLQ assumptions to reactive streams. Stream docs explain that reactive function error/retry handling relies on Reactor operators, whereas imperative message-handler retry templates carry different semantics.

### 10.2. A Common Upgrade Mistake

A team changes from:

```java
Function<String, String>
```

to:

```java
Function<Flux<String>, Flux<String>>
```

and keeps assuming the binder retries each failing message individually. This is a programming-model shift, not merely a generic-type swap. You must verify `onError`, `retryWhen`, resubscription, side effects, and ordering.

## 11. Content-Type and Conversion: Do Not Carry Legacy Headers into New Defaults

Spring Cloud Function uses `MessageConverter` for `Message` inputs and `ConversionService` for non-`Message` data when type conversion is required. The target type normally comes from the function signature; `contentType` guides converter selection.

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> classify(order);
}
```

Binding configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          content-type: application/json
        classifyOrder-out-0:
          content-type: application/json
```

### 11.1. Legacy Docs May Mention `original-content-type`

Historically in Stream, an `original-content-type` header was used in legacy conversion steps. Stream 3.x docs record that references to this header were removed after being deprecated in 2.0.

Do not add that header merely because it appears in an old snippet. Inspect actual `contentType`, binding properties, native codecs, and converters in your target version.

### 11.2. `@StreamMessageConverter`

Stream 3.x docs marked `@StreamMessageConverter` deprecated because the functional model and current message conversion no longer require that legacy configuration approach in standard scenarios. If a project uses this annotation, inspect the active converters and migrate to version-appropriate `MessageConverter` beans/extension points as needed.

### 11.3. Verify Wire Data Types

Do not check only that a Java DTO instantiates. Save fixtures for raw bytes/JSON, content types, headers, unknown fields, nullability, large numbers, enums, and Unicode. A native Kafka deserializer may run before Function conversion; `content-type: application/json` does not configure Kafka serializers/deserializers on its own.

## 12. Dynamic Destinations: From `BinderAwareChannelResolver` to `sendto.destination`

Legacy Stream docs used `BinderAwareChannelResolver` for sending to dynamic destinations. Stream 3.x marked this resolver deprecated for the function-based model and recommends the `spring.cloud.stream.sendto.destination` header/property in suitable cases.

Example function returning a `Message` with a dynamic destination:

```java
@Bean
Function<OrderCreated, Message<OrderClassified>> routeOrder() {
    return order -> MessageBuilder
            .withPayload(classify(order))
            .setHeader("spring.cloud.stream.sendto.destination",
                    destinationFor(order))
            .build();
}
```

This illustrates the pattern; verify dynamic-destination mechanics and your project's specific binder. Never let external inputs specify arbitrary destinations; enforce a server-controlled allowlist or mapping.

Dynamic destinations can auto-create new topics/queues and affect broker ACLs, retention, and costs. Never treat them as a substitute for owned topology design.

## 13. Error Handling: Old and New Docs May Discuss Different Layers

Spring Cloud Stream provides error handling at the framework/binder level. When an imperative function throws, the binder can retry according to consumer properties and route to a DLQ/DLT if supported and configured.

Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        classifyOrder-in-0:
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

Current docs state `maxAttempts` defaults to 3 for imperative message handlers. A reactive function is not a message handler with the same semantics; errors inside `Flux` must be handled using Reactor operators and matching stream policies.

### 13.1. Custom `ErrorMessage` Handlers Can Override Defaults

Configuring a `Consumer<ErrorMessage>` as a custom error handler can supersede default/binder error handlers; in that case, do not assume DLQ still runs automatically as it did without a custom handler. Read the error-handling section for your exact binder.

### 13.2. Retries Do Not Guarantee Exactly-Once Processing

A message may be reprocessed after an error, crash, or redelivery. If a function writes to the DB and then throws, retries can repeat side effects. Use stable event IDs, idempotency keys, transactional outboxes, and deduplication.

Never copy a retry config from Kafka to RabbitMQ or a cloud event source without verifying binder/provider capabilities.

## 14. Test Binder: Legacy `MessageCollector` vs. `InputDestination`/`OutputDestination`

Legacy docs may use:

```java
@Autowired
MessageCollector messageCollector;
```

and the `spring-cloud-stream-test-support` dependency. Stream 3.2.10 docs note the old test-support binder was deprecated in favor of the new Integration Test Binder.

The modern test pattern typically uses `InputDestination` and `OutputDestination`:

```java
@SpringBootTest
class UppercaseStreamTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void transformsMessage() {
        input.send(new GenericMessage<>("hello".getBytes()));

        Message<byte[]> result = output.receive();

        assertThat(new String(result.getPayload()))
                .isEqualTo("HELLO");
    }

    @SpringBootApplication
    @Import(TestChannelBinderConfiguration.class)
    static class TestApplication {

        @Bean
        Function<String, String> uppercase() {
            return String::toUpperCase;
        }
    }
}
```

This is an illustrative structure; pull exact imports, test binder dependencies, and context config from your target version's reference. With multiple bindings, pass explicit destination/binding names to `send()`/`receive()`.

### 14.1. The Test Binder Does Not Replace a Real Broker

The Integration Test Binder is great for testing function wiring, binding names, and in-JVM conversions. It does **not** prove:

- Kafka partitions, offsets, or consumer groups.
- Rabbit exchanges, queues, or acks.
- Native serializers/deserializers.
- Broker ACLs, TLS, or retry/DLQ topology.
- Real message retention and redelivery.

Add broker integration tests (such as Testcontainers) for semantics the test binder does not simulate.

## 15. The Binder Abstraction Still Matters in the New Generation

A common misconception when reading old docs is thinking the functional model removed Binders. In reality, Spring Cloud Stream still relies on the Binder abstraction to connect apps to middleware such as Kafka or RabbitMQ.

| Piece | Role |
| --- | --- |
| Function bean | Data processing logic |
| `FunctionCatalog` | Lookup/wrapper/composition/conversion |
| Stream binding | Function input/output ports |
| Binder | Adapter to middleware |
| Destination | Topic/queue/exchange |
| Consumer group | Consumer identity and distribution semantics |
| Broker | Infrastructure storing/delivering messages |

The functional model cuts coupling to channel APIs and makes business logic more portable. It does not turn Kafka and RabbitMQ into identical brokers; binder-specific configs, retries, DLQs, partitions, and native codecs still differ.

## 16. Notable Changes Recorded in Generation 2026.0.0

The Spring Cloud 2026.0.0 release announcement lists several notable changes:

| Project | Announced item | Meaning when comparing docs |
| --- | --- | --- |
| Spring Cloud Function | Fix CVE-2026-59439 for unbounded JSON collections | Verify security patch and payload bounds |
| Spring Cloud Function | Fix CVE-2026-59440 for arbitrary class loading | Verify dynamic MIME `type` and allowlist |
| Spring Cloud Function | Deprecation of RSocket module | If using this adapter/module, plan replacement |
| Spring Cloud Function | Deprecation of gRPC module | Audit gRPC dependencies and adapters |
| Spring Cloud Stream | Fix CVE-2026-59441 for subpackage deserialization | Audit deserializers and trust policies |
| Spring Cloud Stream | Deprecation of reactive Kafka Binder | Separate the binder artifact from reactive Function APIs |
| Spring Cloud Stream | Deprecation of Schema Registry component | Review your app's schema/registry strategy |
| Spring Cloud Bus | Integrated into Spring Cloud Stream; artifact coordinates unchanged | Read release notes before altering coordinates |

**Do not conclude the reactive Function API is deprecated just because the reactive Kafka Binder was deprecated.** One is a programming model using Reactor; the other is a specific binder artifact. Likewise, deprecating the RSocket/gRPC modules does not remove `Function<T,R>` or `FunctionCatalog`.

These are release-train highlights, not an exhaustive list of every change. Read module-specific issues and release notes whenever your app uses those features.

## 17. Step-by-Step Process for Mapping a Legacy Documentation Snippet

Suppose you find a legacy snippet:

```java
@EnableBinding(Processor.class)
public class LegacyHandler {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String transform(String input) {
        return input.toUpperCase();
    }
}
```

Walk through these steps:

### Step 1 — Identify the Documentation Version

Record the Spring Cloud Stream/Spring Cloud train version the example targets. If unstated, inspect dependencies or APIs in the snippet to trace authoritative sources without guessing a version.

### Step 2 — Extract the Business Logic

What does the method do? What are its inputs/outputs? Are there side effects, validations, headers, transactions, or error paths?

Here the business logic is `String -> uppercase String`.

### Step 3 — Identify the Adapter

The snippet uses the Spring Cloud Stream channel model, not core Spring Cloud Function APIs.

### Step 4 — Check Migration Status

Consult Stream 3.x docs on annotation-model deprecation and current functional-model docs. Separate deprecated from removed.

### Step 5 — Move Business Logic into a Function Bean

```java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
```

### Step 6 — Write Definition and Bindings

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: text.raw
          group: text-workers
        uppercase-out-0:
          destination: text.uppercase
```

### Step 7 — Preserve Operational Behavior

Carry over destinations, groups, content types, partitioning, retries, DLQs, consumer concurrency, headers, and security—not merely the Java method.

### Step 8 — Test on the Target Artifact

Run catalog lookups, test binder checks, real broker tests, and deployment-like tests. Compare before–after behavior using identical fixtures.

## 18. Mapping Table: Legacy APIs/Config to Current Concepts

| Legacy pattern | Current/functional concept | Migration note |
| --- | --- | --- |
| `@EnableBinding(Source.class)` | `Supplier<T>` | Preserve poller/emission rate |
| `@EnableBinding(Sink.class)` | `Consumer<T>` | Preserve group, retries, and side effects |
| `@EnableBinding(Processor.class)` | `Function<I,O>` | Preserve input/output destinations |
| `@Input`/`@Output` | Implicit binding names or aliases | Verify exact binding names |
| `@StreamListener` | Functional bean + `spring.cloud.function.definition` | Migrate logic and header/error semantics |
| `@SendTo` | `Function` return value or explicit output | Verify output mapping |
| `@InboundChannelAdapter` | `Supplier<T>` + matching poller | Check cadence and batching |
| `spring-cloud-stream-reactive` | Reactor types in functional beans | Do not add the old module to new code |
| `MessageCollector` | Test Binder + `InputDestination`/`OutputDestination` | Update test dependencies |
| `@StreamMessageConverter` | `MessageConverter` bean / current converters | Replace only when custom conversion is required |
| `original-content-type` | Current `contentType`/converters | Legacy header was removed |
| `BinderAwareChannelResolver` | `spring.cloud.stream.sendto.destination` where appropriate | Restrict dynamic destinations |
| Legacy `@StreamRetryTemplate` examples | Current consumer retry/binder config and error handling | Check target version and binder |

This table is a conceptual map, not an automated refactoring script. A legacy handler may combine multiple concerns; separate them before migrating.

## 19. Separating Framework Changes from Cloud Provider Changes

Spring Cloud Function keeps business logic reusable across HTTP, streams, and serverless. Cloud providers still govern their own runtimes, triggers, identities, retries, scaling, and event envelopes.

| Question | Spring Cloud Function/Stream | Cloud provider |
| --- | --- | --- |
| Which function runs? | `FunctionCatalog`, `definition`, routing | Handler config/env vars if used by adapter |
| JSON to DTO conversion? | `MessageConverter`/`ConversionService` | May wrap payload in a provider event envelope first |
| Sending/receiving events? | Bindings/Binders | Kafka, Rabbit, SQS, EventBridge, Pub/Sub, Azure triggers, etc. |
| Retries? | Framework/binder when handler & binder support it | Event source mapping/host/platform policy |
| Scaling? | Consumer concurrency/replicas | Lambda concurrency, Functions host scaling, Cloud Run |
| Identity? | Security/application context | IAM, RBAC, service accounts |
| Packaging? | Adapters/build plugins | JAR/ZIP/container/Functions packages |
| Timeouts/memory? | Some application settings | Runtime/provider limits |

Never take a Stream binder `maxAttempts` snippet and assume SQS, Azure Queue, or Pub/Sub enforce identical retry semantics. Adapters bridge the contract; providers still control key runtime behaviors.

## 20. Adapter and Runtime Docs Also Have Their Own Lifecycles

For example, a Java function can deploy to AWS Lambda via `spring-cloud-function-adapter-aws` and `FunctionInvoker`. Azure uses its own adapter and Azure Java Worker annotations/DI. GCP uses its own adapter and Functions Framework.

When reading older docs, verify:

- Is the adapter artifact still published in the target BOM?
- Is the handler FQN still accurate?
- Does the cloud provider runtime still support that Java version?
- Does the build plugin produce the required artifact layout?
- Have trigger event schemas changed?
- Do IAM/RBAC and secret injection remain intact?
- Do retry/ack/partial-batch behaviors match expectations?

Compiling a Java class does not prove the provider can load it. Test the **final packaged artifact** with a local emulator/Functions Framework or a suitable staging environment.

## 21. Managing Project Documentation: Build a Provenance Table

Every key example should carry minimal provenance:

| Field | Example |
| --- | --- |
| Document title | Spring Cloud Stream — Functional Binding Names |
| Version | 5.1.x |
| URL | Official reference URL |
| Retrieved/reviewed date | November 24, 2026 |
| Project artifact | `spring-cloud-stream` |
| Release train | `2026.0.0` |
| Boot baseline | `4.2.0` |
| Usage | Binding names for `classifyOrder` |
| Migration status | Current / Deprecated / Removed / Unknown |
| Owner | Orders Platform team |
| Last verification | CI integration test run |

An unversioned snippet becomes technical debt. When the framework upgrades, the team won't know which branch the snippet came from or why a property exists.

### 21.1. Record Confidence Levels Explicitly

Tag each finding with one label:

- **CONFIRMED:** verified in version-matched release notes or Javadoc.
- **DOCUMENTED:** described in reference docs, not yet tested in the app.
- **OBSERVED:** executed and verified on the target artifact.
- **ASSUMED:** no evidence yet; never use as release justification.

An old blog post might be CONFIRMED for Stream 2.0 yet UNKNOWN for Stream 5.1.0.

## 22. Testing Migrations with Shared Fixtures

Keep business fixtures identical between baseline and target. At minimum:

| Test | What to prove |
| --- | --- |
| `FunctionCatalog` lookup | Function names still resolve |
| Composition | Step order and type compatibility |
| Binding creation | Input/output binding names match |
| Destination/group | Broker topology preserves contract |
| JSON conversion | Content type and target DTO match |
| Header mapping | Required metadata neither lost nor leaked |
| Supplier polling | Cadence, batching, and finite/reactive semantics match |
| Retry/DLQ | Transient/permanent failures take expected paths |
| Schema compatibility | New consumers read old events; old consumers read new events if required |
| Native codecs | Kafka/Rabbit serializers/deserializers behave properly |
| Test binder | Wiring and framework behavior match |
| Broker integration | Offsets, partitions, queues, acks, and replays match |
| Cloud adapters | Handlers, event envelopes, and permissions match |
| Rollback | Old artifact still handles emitted data |

### 22.1. Distinguish Unit, Binder, and Broker Tests

- **Unit test:** tests pure business functions.
- **`FunctionCatalog` test:** tests lookup, wrappers, and composition.
- **Test binder:** tests Stream bindings/conversions inside the JVM.
- **Broker integration test:** tests real Kafka/Rabbit semantics.
- **Cloud deployment test:** tests provider event sources, IAM, packaging, and retries.

No single testing layer replaces the others.

## 23. Case Study: Upgrading a Legacy Service to a New Release Train

Suppose baseline has:

- Spring Boot 2.x/3.x per project.
- Spring Cloud Stream 2.x or 3.2.x.
- `@EnableBinding(Processor.class)`.
- `@StreamListener(Processor.INPUT)`.
- `MessageCollector` in tests.
- Kafka destination `orders.created`, group `order-classifiers`.

Target moves to Spring Cloud 2026.0.0 / Boot 4.2.0 / Function 5.1.0 / Stream 5.1.0.

### Phase A — Inventory

Record:
- Java handlers and all annotations.
- Input/output channel names.
- Topics, groups, partitions, consumer concurrency.
- Content types and serializers.
- Retries, DLT, offsets/acks.
- Event schemas and consumer versions.
- Test binder and broker tests.

### Phase B — Extract Business Logic

Move logic into a function bean:

```java
@Bean
Function<OrderCreated, OrderClassified> classifyOrder() {
    return order -> classify(order);
}
```

Preserve existing DTO/event contracts before evolving schemas. Set `definition` explicitly.

### Phase C — Functional Bindings

```yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
          consumer:
            maxAttempts: 3
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
```

Compare binder-specific settings like Kafka DLT, partitioning, native decoding, and ack modes. Do not assume common properties cover every broker feature.

### Phase D — Update Tests

Migrate tests from `MessageCollector` to the test binder's `InputDestination`/`OutputDestination`, while keeping real broker integration tests separate.

### Phase E — Upgrade Dependencies via BOM

- Select the Spring Cloud release train compatible with Boot 4.2.0.
- Import BOM `2026.0.0`.
- Remove unnecessary version overrides.
- Inspect the dependency tree.
- Review deprecations, removals, and security advisories.

### Phase F — Canary

- Deploy new consumers or new producers first according to schema compatibility.
- Monitor lag, DLT, conversion errors, retries, and duplicate events.
- Keep artifact and schema rollback paths ready.
- Delete legacy binding code only after all consumers have migrated and historical data remains readable.

## 24. Release Train 2026.0.0 Changes to Record in Internal Docs

Beyond API bumps, the 2026.0.0 release notes highlight module-organization shifts:

1. **Spring Cloud Bus was integrated into Spring Cloud Stream.** Release notes state Bus artifact coordinates remain unchanged. Do not rewrite dependency coordinates merely because the project merged.
2. **Function gRPC and RSocket modules were marked deprecated.** If your app uses those adapters, inventory them and plan dedicated migration paths.
3. **Reactive Kafka Binder was deprecated.** This does not remove Reactor or reactive functional signatures.
4. **Stream's Schema Registry component was deprecated.** Check whether your app uses this component or an external registry/custom serializer.
5. **Security fixes** in Function/Stream are part of the release; verify matching patches and advisories.

These points were published in the release announcement. For production systems, read full module release notes and security advisories before making replacement decisions.

## 25. Common Mistakes When Comparing Documentation

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Copied `@EnableBinding` from old guide, yet API no longer fits | Doc targets deprecated annotation model | Move to functional beans per target version |
| Used `@StreamListener` in new code | Mixed up Stream 2.x/3.x docs | Check deprecations and use functional model |
| `MessageCollector` missing | Old test-support binder deprecated | Use Integration Test Binder and destinations |
| `spring-cloud-stream-reactive` missing | Module discontinued since Stream 3.0 | Use Reactor types in function signatures |
| Wrong binding name | Confused channel interfaces with implicit binding names | Compute `<function>-in/out-index` and check aliases |
| Destination changed with function name | Coupled binding to destination | Name destinations after the domain |
| `original-content-type` has no effect | Legacy header removed | Use current `contentType` mechanisms |
| `@StreamMessageConverter` incompatible | Legacy converter API deprecated | Check current `MessageConverter` extensions |
| `BinderAwareChannelResolver` no longer recommended | Legacy dynamic send path | Check `spring.cloud.stream.sendto.destination` |
| Reactive handler retries differently | Imperative vs. reactive error semantics differ | Use Reactor operators and test stream lifecycle |
| Boot/Cloud BOM incompatible | Mixed versions independently | Follow release train compatibility matrix |
| Snapshot docs differ from GA artifact | Read wrong doc branch | Use version-matched docs |
| Test binder passes, Kafka fails | Test binder doesn't simulate broker | Run broker integration tests |
| Cloud runtime won't load JAR | Packaging/handler layout differs | Test final artifact on target runtime |
| Deprecated misread as removed | Didn't check API/Javadoc | Verify presence in resolved artifact |
| Schema Registry component deprecation misread as dropping all registries | Confused integration module with external registries | Read exact scope in release notes |
| Reactive Kafka Binder deprecation misread as dropping `Flux` | Confused binder artifact with programming model | Separate binder artifact from Reactor API |

## 26. Checklist for Evaluating an Old Documentation Page

Before applying an example:

- [ ] Record the page URL and version.
- [ ] Record the matching release train and Spring Boot version.
- [ ] Identify the programming model: annotation, functional, Spring Integration, or reactive.
- [ ] Identify the exact artifact, binder, and adapter used.
- [ ] Check whether classes/methods/properties are deprecated or removed.
- [ ] Cross-check migration guides and release notes.
- [ ] Separate business logic from transport/handlers.
- [ ] Verify binding names, destinations, groups, and headers.
- [ ] Verify content types, converters, and native codecs.
- [ ] Verify retries, DLQs, acks, pollers, and concurrency.
- [ ] Update test binder and broker integration tests.
- [ ] Run identical fixtures on baseline and target.
- [ ] Record provenance and verification results for the snippet.
- [ ] Do not remove legacy APIs before contract tests pass.
- [ ] Prepare rollback plans for artifacts, schemas, and emitted messages.

## 27. Hands-On Exercises

### Exercise 1: Reading the Right Version

You find an `@EnableBinding(Processor.class)` example in Spring Cloud Stream 2.0 and a functional binding-names page for Stream 5.x. List what must be established before comparing the two snippets. Why can't you claim the 2.0 page is wrong?

### Exercise 2: Converting `@StreamListener` to `Function`

Given:

```java
@EnableBinding(Processor.class)
class LegacyHandler {
    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String uppercase(String value) {
        return value.toUpperCase();
    }
}
```

Convert it to `Function<String,String>`, configuring `definition`, input/output bindings, destinations, and group. List behaviors beyond output body that must be tested.

### Exercise 3: `Source`/`Sink` to `Supplier`/`Consumer`

A legacy app uses `Source.OUTPUT` and `Sink.INPUT`. Write the equivalent functional beans and explain how to verify pollers, groups, and replica counts after upgrading.

### Exercise 4: Distinguishing Deprecated from Removed

Stream 3.2.10 docs mark `@StreamListener` deprecated, while later docs still mention some legacy/annotation setups. Propose how to verify whether the class exists in your target version and decide whether to keep using it.

### Exercise 5: Test Binder Migration

A test using `MessageCollector` no longer compiles after upgrading. Describe how to replace it with `InputDestination`/`OutputDestination`, and list real broker tests that must remain.

### Exercise 6: Legacy Reactive Module

An app depends on `spring-cloud-stream-reactive` and has a `Flux`-based handler. Migrate it to a Reactor functional signature, explain `Supplier<Flux<T>>` and `@PollableBean`, and design tests for the error/retry lifecycle.

### Exercise 7: Current Release Train

As of November 24, 2026, inspect release train `2026.0.0` and identify Boot, Function, and Stream versions. Why must `2026.0.0` never be put into individual artifact version properties?

### Exercise 8: Separating Binder from Reactive API

A system uses the reactive Kafka Binder and `Function<Flux<Order>,Flux<Result>>`. Release notes mark the binder deprecated. Which part needs a migration evaluation? Which part must not be assumed removed?

### Exercise 9: Legacy Properties and Content Types

A configuration uses the `original-content-type` header and a custom `@StreamMessageConverter`. Determine their historical status and plan `contentType`/`MessageConverter` testing on the target version.

### Exercise 10: Writing Provenance for Snippets

Create a record template for critical examples capturing version, release train, artifact, URL, review date, migration status, and test evidence. Explain how CI can flag snippets relying on deprecated APIs.

### Self-Assessment Questions

1. How does the Spring Cloud release train version differ from the Spring Cloud Function version?
2. Why check versions in both the URL and page banner of documentation?
3. Starting in which version did Spring Cloud Stream integrate the functional model?
4. What status do `@EnableBinding`/`@StreamListener` carry in Stream 3.x docs?
5. How does deprecated differ from discontinued and removed?
6. Why shouldn't you delete every annotation just because a new doc uses `Function`?
7. How does `FunctionCatalog.lookup` differ from fetching a bean directly from `ApplicationContext`?
8. By what rule are functional-model binding names generated?
9. Does a binding alias change the destination?
10. Why is `spring-cloud-stream-reactive` no longer needed for the modern reactive function model?
11. How do imperative and reactive error handling differ?
12. Why doesn't the test binder replace real broker integration tests?
13. What mechanism replaces `MessageCollector`?
14. Should `original-content-type` be copied from legacy docs?
15. What role does the Binder abstraction still play in the functional model?
16. Which Boot version does release train `2026.0.0` build upon?
17. Does deprecating the reactive Kafka Binder mean Reactor APIs are removed?
18. How do you distinguish a framework change from a cloud provider change?
19. Which operational details must be preserved when migrating from the annotation model to the functional model?
20. Why keep provenance metadata for code snippets and internal docs?

## 28. Summary

Mapping legacy documentation to the current cloud generation requires keeping context intact:

- **Old docs can still be accurate for old versions.** Record version, release train, and artifact before applying anything.
- **The functional model has been recommended by Spring Cloud Stream since 3.x.** Native annotations like `@EnableBinding`/`@StreamListener` are deprecated; never claim legacy APIs are removed without checking the target artifact.
- **Spring Cloud Function standardizes invocation via `FunctionCatalog`.** `Supplier`, `Function`, `Consumer`, composition, and conversion keep business logic reusable.
- **Binding names, destinations, and event contracts are distinct layers.** Switching programming models never authorizes changing topics, groups, schemas, or headers implicitly.
- **Reactive support is built around Reactor types.** `spring-cloud-stream-reactive` was discontinued; imperative retries and reactive stream error handling differ fundamentally.
- **Test binders and broker tests have different scopes.** `InputDestination`/`OutputDestination` check in-JVM wiring; Kafka/Rabbit integration tests check real broker semantics.
- **Release train `2026.0.0`** serves as the current milestone in this lesson, based on Boot `4.2.0` with Function/Stream `5.1.0`; track per-module deprecations and security fixes carefully.

A sound workflow is **identify source/version → check release train → classify legacy APIs → separate business logic from transport → migrate functions and bindings → preserve event contracts → update tests → verify on real brokers/runtimes → canary and roll back safely**.

Never copy an old or new snippet blindly without understanding its scope. Preserve proven business rules and contracts while migrating each framework layer using docs from the matching release train—so `Supplier`, `Function`, and `Consumer` logic continues working across HTTP, events, and serverless without dragging along outdated binder, runtime, or cloud-provider assumptions.

### References

- [Spring Cloud 2026.0.0 — Release announcement, November 20, 2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Train Reference — Version 2026.0.0, Boot compatibility, and project versions](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Function — Current Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/)
- [Spring Cloud Function 5.0 — Programming Model](https://docs.spring.io/spring-cloud-function/reference/5.0/spring-cloud-function/programming-model.html)
- [Spring Cloud Function 3.2.10 — Historical Reference](https://docs.spring.io/spring-cloud-function/docs/3.2.10/reference/html/spring-cloud-function.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binder Abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-abstraction.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream 3.2.10 — Historical Reference and Deprecations](https://docs.spring.io/spring-cloud-stream/docs/3.2.10/reference/html/spring-cloud-stream.html)
- [Spring Cloud Stream 3.0.x — Legacy annotation-based support](https://docs.spring.io/spring-cloud-stream/docs/3.0.x/reference/html/spring-cloud-stream.html)
- [Spring Cloud Stream — Testing and Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Function — AWS adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Function — Azure adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html)
- [CloudEvents Specification 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
