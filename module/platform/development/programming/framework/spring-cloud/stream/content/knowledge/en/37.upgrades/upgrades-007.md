# Checking Reactive Kafka Binder Support Status and Alternatives

The **Reactive Kafka Binder** was a Spring Cloud Stream component connecting functions using `Flux`/`Mono` to Apache Kafka through **Reactor Kafka**. It used reactive APIs on both message receiving and publishing sides, enabling backpressure across the reactive chain. However, the support status of this component has changed, and it should no longer be treated as the default choice for new projects.

**Conclusion based on official documentation cross-checked on November 24, 2026:** Spring Cloud Stream marked `spring-cloud-stream-binder-kafka-reactive` as **deprecated as of version 4.3.0**, scheduled for **removal in a future release**. The **Spring Cloud Stream 5.1.0** documentation still notes its status as deprecated/planned for removal, and does **not** state that all versions have already removed it. Spring announced on **May 20, 2025** that Reactor Kafka will be discontinued going forward, with 1.3 as its final minor release; the **Spring Cloud 2026.0.0 GA release announcement on November 20, 2026** continues to note the deprecation of the Reactive Kafka Binder.

Therefore, for existing applications, you should inspect the active versions and APIs, identify requirements for backpressure, offsets, and retry/DLQ, and then select a maintained solution. **The path guided by Spring Cloud Stream** is the regular Kafka binder combined with reactive types where appropriate, though the application must explicitly design advanced reactive aspects itself. If the goal is stateful processing with joins/windows/state stores, consider the Kafka Streams binder; if fine-grained Kafka consumer/ack control is needed, consider Spring for Apache Kafka.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_STREAM** module. The goal is to make evidence-based migration decisions rather than merely deleting a dependency or dropping the word `reactive` from the binder name.

## 1. Why evaluate support status?

Older documentation once introduced the Reactive Kafka Binder as the way to achieve end-to-end reactive processing on Kafka. Some current pages still retain that historical description and `KafkaReceiver`/`KafkaSender` examples. However, the notice at the top of current Spring Cloud Stream pages states that the component is deprecated.

You must distinguish:

| Term | Meaning |
|---|---|
| Supported | Within the support scope of a version line and its corresponding support policy |
| Deprecated | Should not build new work on the API; maintainers have a replacement/removal direction |
| Maintenance discontinued | No continued long-term development; fixes may only appear within an announced support window |
| Removed | Code/capability has actually been stripped from a specific release |
| Artifact exists on Maven Central | Only proves a release was published; does **not** prove it is currently recommended or supported |

**Do not infer "already removed" solely from the word deprecated; nor infer "still safe" because Maven can still download an old JAR.** For production projects, tie decisions to exact releases and your organization's support policies.

## 2. Official timeline

| Milestone | Event | Impact |
|---|---|---|
| Before Spring Cloud Stream 4.3 | Dedicated reactive binder based on Reactor Kafka existed | May be encountered in legacy applications |
| May 20, 2025 | Spring announced Reactor Kafka maintenance would be discontinued in the future; 1.3 is the last minor | Prepare to move off this dependency for new designs |
| Spring Cloud Stream 4.3.0 | Reactive Kafka Binder deprecated | Plan migration |
| November 20, 2026 | Spring Cloud 2026.0.0 GA; Spring Cloud Stream 5.1.0 and deprecation note | Recommended to continue migrating |
| November 24, 2026 | Spring Cloud Stream 5.1.0 docs still state "deprecated and will be completely removed in a future release" | Do not claim it is completely removed in 5.1.0 |

Example guide pages may not have been completely rewritten after a deprecation notice. Prioritize current notices and release announcements over leftover "recommended" phrasing in older feature descriptions.

## 3. Distinguishing commonly confused libraries

| Technology/artifact | Role | During upgrade |
|---|---|---|
| `spring-cloud-stream-binder-kafka-reactive` | Binder using Reactor Kafka | **Deprecated since 4.3.0** |
| `reactor-kafka` | `KafkaReceiver`, `KafkaSender`, `ReceiverOffset` library | Announced by Spring to be discontinued in the future |
| `spring-cloud-stream-binder-kafka` | Regular message-channel Kafka binder | Primary replacement path for Spring Cloud Stream |
| `spring-cloud-stream-binder-kafka-streams` | Kafka Streams DSL integration, KStream/KTable | For stateful topologies, not a one-to-one replacement |
| `spring-kafka` | `@KafkaListener`, `KafkaTemplate`, listener container | Deep ack/commit/retry control |
| `reactor-core` | `Flux`, `Mono` APIs and operators | **Not** synonymous with Reactor Kafka; still widely used |
| `spring-cloud-stream-reactive` | Older-generation reactive module | Discontinued since Spring Cloud Stream 3.0; a **different** artifact |

Historically there were two independent changes: the old `spring-cloud-stream-reactive` module was replaced by the functional programming model starting in 3.0; the Reactor Kafka-based Reactive Kafka Binder was deprecated starting in 4.3.0. Do not merge the two events into one.

## 4. What did the Reactive Kafka Binder provide?

The old reactive binder used Reactor Kafka's `KafkaReceiver` and `KafkaSender`. It tied Kafka into the Reactive Streams demand/backpressure model.

~~~text
Reactive Kafka Binder (legacy)
Kafka broker
   |
   v
KafkaReceiver -> Flux -> Reactor operators -> KafkaSender
                  |             |
               demand        reactive flow
                  |             |
                  +-- backpressure --+
   |
   v
Kafka broker output
~~~

Business functions could look simple:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Flux;

@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return input -> input.map(String::toUpperCase);
}
~~~

This exact signature **can** be used with the regular Kafka binder. However, merely using `Flux` in a function is not enough to guarantee full backpressure mechanics through the Kafka client.

## 5. How does the regular Kafka binder with Flux differ?

~~~text
Regular Kafka Binder + Flux:
Kafka -> Spring Kafka listener -> message channel -> Flux pipeline
                                                -> output channel -> producer
           Poll/dispatch and broker boundaries are not
           end-to-end reactive Reactor Kafka receiver/sender.
~~~

What is preserved:

- The `Supplier`, `Function`, `Consumer` functional model.
- Reactor operators such as `map`, `filter`, `flatMap`.
- Binding names, destinations, groups, and typical broker configuration.
- Spring Cloud Stream test binder for verifying business transformations.

What must **not** be assumed automatically equivalent:

- Backpressure flowing across Kafka receiver → function → Kafka sender.
- `ReceiverOffset` and Reactor Kafka's offset commit mechanics.
- `reactiveAutoCommit` and `reactiveAtmostOnce` from the old binder.
- Listener/binder retries and DLQs behaving identically for reactive functions and imperative functions.
- In-flight message bounds, thread scheduling, and completion ordering.

Re-design these points whenever correctness or performance depends on them.

## 6. Inventorying dependencies and versions

Record these details before editing code:

~~~text
Spring Boot                 <actual version>
Spring Cloud train          <actual version>
Spring Cloud Stream         <actual version>
Reactive Kafka Binder       <actual version, if present>
Reactor Kafka               <actual version, if present>
Reactor BOM                 <actual version>
Spring Kafka                <actual version>
Kafka client / broker       <actual versions>
JDK                         <actual version>
~~~

Commands to inspect a Maven project:

~~~bash
mvn dependency:tree

mvn dependency:tree \
  -Dincludes=org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive

mvn dependency:tree \
  -Dincludes=io.projectreactor.kafka:reactor-kafka
~~~

For Gradle projects, inspect the runtime dependency graph via:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands are guides for learners to inventory their own projects; do not infer real versions from these examples. Inspect both direct and transitive dependencies. A JAR cached locally in Maven may still build offline even if the target version no longer includes corresponding dependency management.

## 7. Checking code for legacy API usage

Search in code and configuration for:

~~~text
spring-cloud-stream-binder-kafka-reactive
reactor-kafka
KafkaReceiver
KafkaSender
ReceiverOffset
ReceiverOptionsCustomizer
SenderOptionsCustomizer
reactiveAutoCommit
reactiveAtmostOnce
KafkaHeaders.ACKNOWLEDGMENT
Function<Flux<...>, Flux<...>>
Consumer<Flux<...>>
~~~

Classification:

| Signal | Meaning |
|---|---|
| Reactive binder dependency or `KafkaReceiver` | Depends on the deprecated foundation |
| Plain `Flux`/`Mono` | **Insufficient** alone to prove the reactive binder is in use |
| `ReceiverOffset` | Commit logic depends on Reactor Kafka |
| `reactiveAutoCommit` | Uses specific batch/commit processing semantics |
| `reactiveAtmostOnce` | May commit before processing |
| `ReceiverOptionsCustomizer` | Customized receiver on the old API |
| `KafkaStreams`/KStream/KTable | This is Kafka Streams, not Reactor Kafka |

Specifically, do not overlook shared library classes importing `ReceiverOffset`, even if the main function looks like ordinary Spring Cloud Stream code.

## 8. Asking questions based on business needs

Before choosing a replacement, determine:

1. Are we only mapping/filtering events, or do we need joins/windows/aggregations?
2. Is multi-hour/multi-day stateful processing with changelogs and restore required?
3. Do we truly need Kafka-level reactive backpressure, or just `Flux` syntax?
4. When processing succeeds, at what exact moment is the offset committed?
5. Can duplicate events be handled safely after a crash?
6. Do we need per-message retry/DLT, or a pipeline-wide error strategy?
7. Is per-key/partition ordering required?
8. What are steady load, bursts, latency, and RAM limits?
9. Are WebClient/reactive databases used for asynchronous processing?
10. Do operations and real-broker integration support the new stack?

Do not choose Kafka Streams just because its name contains "Streams". It is a different topology API from `Flux`. Also do not adopt Reactor Kafka directly as a "replacement" when Reactor Kafka itself is on a maintenance-discontinuation path.

## 9. Alternatives comparison table

| Option | Use when | What to verify |
|---|---|---|
| **A. Regular Kafka Binder + imperative Function/Consumer** | Per-event transform, validation, persistence, retry/DLT | Post-processing ack, idempotency, lag |
| **B. Regular Kafka Binder + Flux/Mono Function** | Useful Reactor operators exist and business pipeline should be kept | Error strategy, in-flight bounds, ack boundary |
| **C. Kafka Streams Binder** | KStream/KTable, window, join, aggregate, state stores | Serdes, app ID, internal topic/state migration |
| **D. Spring for Apache Kafka** | Deep control over consumer container, ack/rebalance/batch | Manual ack, error handler, exact configuration |

**A** is the natural initial candidate for most imperative event processing. **B** reduces code rewrites when many Reactor transformations exist, but cannot claim to be a fully reactive broker stack. **C** and **D** address specialized needs. Choose by correctness and SLOs, not just fewest lines of code.

## 10. Option A: swap dependency, keep the functional model

Maven with the regular Kafka binder:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
~~~

Do not re-add `spring-cloud-stream-binder-kafka-reactive` merely to preserve old APIs. Use the Spring Cloud BOM compatible with Spring Boot; do not manually pin conflicting versions.

Example function handling one event at a time:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderCreated(String eventId, String orderId) {}

    public record OrderValidated(
        String eventId,
        String orderId,
        boolean valid
    ) {}

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(
            event.eventId(),
            event.orderId(),
            event.orderId() != null && !event.orderId().isBlank()
        );
    }
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator-v2
          content-type: application/json
          consumer:
            max-attempts: 3

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
~~~

`max-attempts` is a generic retry property for imperative consumer message handlers per binder policy. If logic includes database side effects, deduplication and retry requirements must be designed in detail rather than just returning a DTO.

## 11. Option B: keeping Flux inside the regular Kafka binder

Spring Cloud Function supports `Function<Flux<T>, Flux<R>>` with the regular binder:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class ReactiveTransformFunctions {

    @Bean
    Function<Flux<String>, Flux<String>> uppercase() {
        return input -> input
            .filter(value -> !value.isBlank())
            .map(String::toUpperCase);
    }
}
~~~

Input/output configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

    stream:
      bindings:
        uppercase-in-0:
          destination: text.input
          group: uppercase-v2

        uppercase-out-0:
          destination: text.output

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
~~~

Operational warnings:

- The reactive pipeline runs at the function layer, not `KafkaReceiver`/`KafkaSender` across the broker.
- There is no automatic Kafka demand/backpressure equivalent to the old binder.
- Internal buffers and concurrency must be bounded; measure heap, p99, and lag.
- If an operator throws an unhandled exception, the pipeline can terminate.
- Generic binder retry/DLQ for imperative message handlers does not automatically become per-element retry.
- Do not treat a function returning a Publisher as confirmation that outputs or side effects have committed.

If only simple `map`/`filter` operations are used, an imperative Function is usually easier to verify for retries and acks.

## 12. Error handling in reactive functions differs from imperative functions

In an imperative function, Spring Cloud Stream invokes the handler per message, allowing the binder to wrap each invocation with retry/error handling.

In a reactive function, the framework typically invokes the function once to wire publishers together; many messages then flow through the same pipeline. Therefore `maxAttempts`, retry templates, and DLT behavior from imperative handlers do not apply by default in the same way.

~~~text
Imperative:
message1 -> function invocation -> success/exception
message2 -> function invocation -> success/exception

Reactive:
publisher -> function builds pipeline -> subscriber
                   N messages share the pipeline
~~~

Pitfalls to avoid:

- `retryWhen` at the end of the whole stream can resubscribe beyond the scope of a single record.
- `onErrorResume(error -> Mono.empty())` can turn failed records into silently dropped records.
- `onErrorContinue` is not an observable, recoverable, or auditable DLQ strategy.
- Parallel `flatMap` can alter completion order.
- Unbounded buffers can fill heap instead of propagating backpressure to the broker.

If per-message error handling is needed, choose a solution supporting per-message ack/retry/DLT, or build a thoroughly controlled Reactor error path and test under broker/downstream failures.

## 13. Reactive Consumer and subscription

With `Consumer<Flux<T>>`, the return type is void, so in some cases the framework has no resulting Publisher to subscribe to automatically. This example **does not activate** the pipeline:

~~~java
@Bean
Consumer<Flux<String>> brokenConsumer() {
    return input -> input
        .map(String::toUpperCase)
        .doOnNext(System.out::println);
}
~~~

If using an explicit reactive Consumer, active subscription is required:

~~~java
@Bean
Consumer<Flux<String>> loggingConsumer() {
    return input -> input
        .map(String::toUpperCase)
        .doOnNext(System.out::println)
        .subscribe();
}
~~~

However, `subscribe()` alone **does not** define ack, retry, resource disposal, and shutdown. You must manage lifecycle and error handlers. Spring Cloud Stream also describes using `Function<Flux<T>, Mono<Void>>` in some cases so the framework sees a resulting Publisher; for business logic requiring ack after each database commit, an imperative Consumer is usually clearer.

## 14. Option C: Kafka Streams binder

If requirements call for joins, windows, aggregations, KTables, or stateful topologies, evaluate the Kafka Streams binder:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

API example:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, String>, KStream<String, String>>
        normalizeOrders() {
    return stream -> stream.mapValues(
        value -> value == null ? null : value.trim()
    );
}
~~~

This is not a 1:1 replacement for `Function<Flux,Flux>`. When adopting Kafka Streams, you need:

- A stable `application.id`.
- Group/task assignment and partition topology.
- Key/value Serdes and schema evolution.
- State stores, RocksDB, and changelog/repartition topics if stateful.
- Window grace/retention periods and post-restart restore capability.
- A state upgrade/reset plan if changing topology or application ID.

Choose Kafka Streams for stateful stream-time processing capabilities, not simply because the name contains "Streams".

## 15. Option D: Spring for Apache Kafka

If deep control over listener containers/offsets/acks is required, use Spring Kafka directly:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection-v2"
    )
    public void receive(
            String payload,
            Acknowledgment acknowledgment) {

        processor.processAndCommit(payload);
        acknowledgment.acknowledge();
    }
}
~~~

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BROKERS:localhost:9092}
    listener:
      ack-mode: manual
    consumer:
      auto-offset-reset: earliest
~~~

This assumes `OrderProcessor.processAndCommit` is a business method returning only after committing durable side effects. `Acknowledgment` requires the listener container in manual ack mode. Configure `DefaultErrorHandler`, DLT, and backoff if needed; never swallow exceptions and still ack.

The tradeoff is coupling code more directly to Spring Kafka, in exchange for controlling mechanisms that migration needs to verify. If using asynchronous WebClient/Mono, never ack before the Mono completes successfully.

## 16. Legacy ReceiverOffset is not equal to new Acknowledgment

The legacy Reactive Kafka Binder since 4.0.2 documented the `KafkaHeaders.ACKNOWLEDGMENT` header as holding a Reactor Kafka `ReceiverOffset`. In the regular Kafka binder with manual ack, the counterpart is `org.springframework.kafka.support.Acknowledgment`.

| Aspect | Legacy reactive binder | Regular binder |
|---|---|---|
| Consumer foundation | Reactor Kafka `KafkaReceiver` | Spring Kafka listener container |
| Ack object | `ReceiverOffset` | `Acknowledgment` |
| Reactive auto-commit options | `reactiveAutoCommit`, `reactiveAtmostOnce` | No direct mapping |
| Error handling | Reactor pipeline and dedicated options | Imperative listener/binder error handler or Reactor per function |
| Commit point | Per `ReceiverOffset`/legacy options | Per listener ack mode and error handling |

Do not just fix imports while leaving logic untouched. The same header name can carry different objects and semantics. Define precisely what "successfully processed" means relative to offset commit timing.

## 17. Two legacy reactive commit options to audit

Per legacy documentation:

- `reactiveAtmostOnce=true`: commits before processing the record, accepting the risk of record loss on errors.
- `reactiveAutoCommit=true`: processes according to Reactor Kafka auto-commit batch semantics, potentially using `Flux<Flux<ConsumerRecord<...>>>` and native deserializers.
- Documentation notes that `reactiveAutoCommit` in 4.0.2 had an inaccurate implementation close to at-most-once; behavior changed in later versions.
- In these auto-commit modes, the manual acknowledgment header may not be present.

Audit the actual option values in YAML and test these cases:

1. Consumer crashes before processing.
2. Database commit succeeds, but offset has not committed yet.
3. Offset committed, but side effects are not yet durable.
4. Broker output returns an error.
5. Poison record inside a batch.
6. Retries occurring after a rebalance.

Switching binders can reduce data loss or introduce extra duplicates depending on the new commit boundary. This is a semantic change, not an API rename.

## 18. Retries and DLT when migrating to the imperative binder

Example generic retry combined with Kafka DLT:

~~~yaml
spring:
  cloud:
    function:
      definition: storeOrder

    stream:
      bindings:
        storeOrder-in-0:
          destination: orders.created
          group: order-projection-v2
          consumer:
            max-attempts: 3

      kafka:
        bindings:
          storeOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
~~~

This example assumes required topics/ACLs/Serdes are configured, and `storeOrder` is an imperative message handler. Test deserialization failures, business failures, and DLT publish failures separately because they follow different handling paths.

If keeping a reactive function, do not assume `max-attempts` above automatically retries each element. Reactor `retryWhen`/error operators must sit at the appropriate layer, ensuring records are neither silently dropped nor retried infinitely.

## 19. Controlling in-flight work and backpressure after migration

When removing the reactive Kafka client, control load across multiple layers:

| Boundary | Parameters/mechanisms | Measurements |
|---|---|---|
| Kafka → consumer | Partitions, concurrency, `max.poll.records` | Lag per partition, poll latency |
| Consumer → business | Bounded queue, executor, semaphore | In-flight count, queue depth, rejections |
| Business → DB/API | Connection pool, timeouts, rate limits | p95/p99, wait time, errors |
| Function → producer | Batching, acks, buffer memory | Send latency, error rate |
| Downstream overload | Pause/resume consumer, backoff | Lag, recovery, rebalances |

Avoid running `flatMap` with concurrency higher than downstream resources can handle. An unbounded `onBackpressureBuffer` merely moves backlog from Kafka into JVM heap rather than providing end-to-end backpressure.

If records must stay ordered by `orderId`, verify partition keys and execution order when using concurrency or parallel Reactor operators.

## 20. Migration should follow four phases

### Phase A — Inventory

1. Record Spring Boot, Cloud, Stream, Reactor Kafka, and broker versions.
2. Identify both direct and transitive dependencies.
3. Locate `ReceiverOffset`/customizers/reactive commit flags.
4. List input/output topics, groups, schemas, keys, and headers.
5. Document legacy behavior: when ack/commit occurs, retry/DLT, ordering, throughput.

### Phase B — Prototype

1. Swap dependencies on an isolated branch.
2. Choose the regular Kafka binder and either an imperative Function or Flux Function as needed.
3. Keep input/output contracts unchanged; avoid changing schemas and binders simultaneously.
4. Write happy-path and error-path tests with Testcontainers Kafka.
5. Measure lag, throughput, p99, heap, retries, and DLT.

### Phase C — Shadow comparison

1. Use a **different** consumer group if two apps must receive the same input.
2. Isolate shadow app outputs or run in dry-run mode to avoid duplicate side effects.
3. Record discrepancies by event ID.
4. Test restarts, rebalances, broker timeouts, and slow downstreams.
5. Determine the offset cutover point and data needing replay/backfill.

### Phase D — Cutover/rollback

1. Stop/drain the old app using a supported procedure.
2. Verify committed offsets match durable side effects.
3. Start the new app with the decided group and initial offset.
4. Monitor end-to-end success, duplicates, retries, DLT, and lag.
5. Maintain a rollback plan and event deduplication to tolerate reprocessing.

Do not run two apps in the **same consumer group** expecting both to receive every record; Kafka distributes partitions across members within that group.

## 21. Offsets and groups: transition risks

If keeping the old application's group ID, the new application can resume from existing committed offsets, though "no skipped work" only holds if old offsets accurately reflect completed side effects.

If creating a new group, `auto.offset.reset` applies only when no valid committed offset exists; `earliest` may replay history, while `latest` may miss historical events.

| Cutover | Benefit | Risk |
|---|---|---|
| Keep group | Resumes from committed offset | Old commit point may be ahead of side effects |
| New group from earliest | Re-processes history | Duplicates and repeated outputs |
| New group from latest | No replay of old data | Misses events produced before subscription |
| Two groups in parallel | Independent comparison | Must isolate sinks and doubles cost |
| Same group running concurrently | Kafka load-balances partitions | Not shadow/mirror data |

Do not reset production offsets just to "retry" without backups, data reconciliation, and a deduplication plan.

## 22. Integration testing with a real broker

In-JVM Test binder verifies function transformations, not Kafka commits/rebalances/producer acknowledgements. For migrations involving Reactor Kafka, test against a real Kafka broker.

| Scenario | Expectation |
|---|---|
| 100 valid events | 100 contract-compliant outputs/side effects |
| One poison record in the middle | Subsequent records not lost; DLT/retry behaves properly |
| Transient DB failure | Bounded retries; no premature ack |
| DB commit then JVM crash | Redelivery occurs; idempotency prevents duplicate effect |
| Broker output failure | Input not committed as successful before sink is durable |
| Rebalance under high load | No dropped offsets or endless disruption |
| Slow downstream | Bounded in-flight/buffers; measurable lag |
| Restart with old group | Resumes from real committed offset |
| Shadow group | No duplicate outputs sent to production sink |
| DLT publish failure | Tested recovery behavior, no silent drops |

Every record should carry an `eventId` to reconcile inputs, outputs, pending items, duplicates, retries, and DLT. Never test only "Spring context started".

## 23. Measuring performance before and after

Minimum metric set:

- Business events **successfully** processed per second.
- p50/p95/p99 end-to-end latency, including time spent in the broker.
- Consumer lag per partition.
- CPU, heap, GC pauses, and queue/buffer memory.
- Concurrent downstream requests / connection pool wait time.
- Retries, redeliveries, DLT, and error ratio.
- Producer send/ack latency.
- Rebalance count and recovery time.
- Cost per million valid events.

The regular binder with `Flux` may achieve strong throughput in a benchmark, yet you must still test bursts and slow downstreams to catch missing backpressure causing RAM spikes or elevated p99. Do not use low thread counts as proof of end-to-end non-blocking behavior.

## 24. Common mistakes

| Mistake | Why it is dangerous | Fix |
|---|---|---|
| Claiming the binder was removed from all versions | Contradicts 5.1.0 deprecation wording | Record exact version and check date |
| Continuing to use it for new projects | Builds on a component with no long-term development | Use regular binder or suitable stack |
| Seeing Flux and assuming fully reactive | No end-to-end backpressure with regular binder | Measure broker boundaries and cap in-flight work |
| Mechanically swapping ReceiverOffset for Acknowledgment | Different ack timing | Redesign commit/side-effect boundary |
| Only swapping dependency and building | Misses retry, DLT, ordering, schemas | Contract tests and failure injection |
| Reactive function not retrying per record | Binder handler retry is for imperative handlers | Reactor error strategy or imperative Function |
| Consumer<Flux> never subscribing | Pipeline never processes | Manage subscription or change function signature |
| Running shadow in the same group | Two apps split partitions | Separate group, isolate outputs |
| Increasing concurrency unboundedly | Overloads downstream/heap | Cap per pool/partition |
| Picking Kafka Streams for its name | Wrong abstraction, has own state/app ID | Choose based on topology requirements |
| Raising throughput via early ack | Can lose records | Ack only at a durable success boundary |
| Having no rollback preparation | Cannot recover quickly | Clear cutover/offset/runbook |

## 25. Decision checklist

| Question | Result to record |
|---|---|
| Which exact Spring Cloud/Stream release? | Version, BOM, and changelog link |
| Is the reactive binder on the classpath? | Dependency tree |
| Is Reactor Kafka used directly? | `KafkaReceiver`/`KafkaSender`/`ReceiverOffset` |
| Support status of the target version? | Deprecated/removed/support end from official sources |
| Is real backpressure across Kafka required? | SLO and proving tests |
| Does logic have stateful windows/joins? | Whether Kafka Streams fits |
| Can an imperative per-message handler be used? | Verified retry/ack/throughput |
| Which reactive commit option is active? | Commit timing description and risks |
| Are DLQ and idempotency required? | Policy and tests |
| Are group and cutover offsets decided? | Runbook |
| Is there a shadow test with no duplicate outputs? | Separate group/destination |
| Have crash/rebalance/timeout been tested? | Integration test results |
| Is there a rollback plan? | Triggers, owners, timeline |

## 26. Practice exercise

A sample project currently uses `spring-cloud-stream-binder-kafka-reactive` with `Function<Flux<String>,Flux<String>>` reading `orders.raw`, normalizing payloads, and publishing `orders.normalized`.

1. Record the versions of the framework, Reactor Kafka, and Kafka broker.
2. Read the deprecation warning in Spring Cloud Stream 5.1.0 docs and the 2025/2026 Spring announcements.
3. Document the old version's commit/ack, retry/DLT, group, partition, headers, and serializer configuration.
4. Create a prototype using `spring-cloud-stream-binder-kafka`.
5. Keep the Flux function in the first test round, then also implement an imperative Function.
6. Run Testcontainers Kafka; verify output counts and data correctness.
7. Inject downstream failures, poison records, and crashes before/after side effects.
8. Run a shadow consumer group with isolated output.
9. Compare lag, throughput, p99, heap, retries, and DLT.
10. Choose the target approach based on correctness and SLOs; draft a cutover/rollback plan.

**Completion criteria:** accurately explain the deprecation status, distinguish the Flux API from the underlying reactive binder, select the right replacement approach, redesign ack/retry/DLT, and prove that migration loses no data and preserves committed ordering guarantees.

## 27. Official references

- [Spring Cloud Stream 5.1.0 — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html) — deprecated since 4.3.0; removal in a future release.
- [Spring Blog — Reactor Kafka Project Will Be Discontinued (May 20, 2025)](https://spring.io/blog/2025/05/20/reactor-kafka-discontinued/) — Reactor Kafka 1.3 as final minor, discontinuation roadmap for maintenance and integration.
- [Spring Cloud 2026.0.0 GA (Nov 20, 2026)](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/) — Spring Cloud Stream 5.1.0 and deprecation note.
- [Spring Cloud Stream — Reactive Kafka Binder Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html) — backpressure, `ReceiverOffset`, `reactiveAutoCommit`.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functional model, `Flux`/`Mono`, reactive Consumer, and error handling.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — generic retry/DLQ for imperative handlers.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — consumer/producer settings.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/) — KStream, KTable, and topology.
- [Spring for Apache Kafka — @KafkaListener](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html) — annotation consumer.
- [Spring for Apache Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html) — ack modes, offsets.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — scope of in-JVM test binder.
