# Curried Functions for Topologies with More Than Two Inputs

The Spring Cloud Stream Kafka Streams binder lets a single function process multiple incoming Kafka streams. For two inputs, you can use **BiFunction**. When a topology requires three or more inputs, the curried function model represents each input as a nested **Function** layer: the function receives the first stream and returns a function awaiting the second stream; that next function awaits the following stream until all inputs are received and the final topology is produced.

Currying preserves a clean function signature when the number of input bindings exceeds two. The Kafka Streams binder maps each parameter in order to **functionName-in-0**, **-in-1**, **-in-2**... bindings and maps the final return value to the output binding. The parameter order in the function signature is therefore part of the configuration contract.

This lesson explains how to write curried functions for three or more `KStream`s, how to name bindings and configure Serdes, how to combine streams via `merge` or `join`, and considerations around keys, partitioning, state, testing, and deployment.

## Learning Objectives

After this lesson, you will be able to:

- Explain currying and why it is used when a topology has more than two inputs.
- Distinguish `BiFunction` for two inputs from nested `Function`s for three or more inputs.
- Write a curried function signature accepting three `KStream`s and returning one `KStream`.
- Map parameter order accurately to the `-in-0`, `-in-1`, and `-in-2` input bindings.
- Configure destinations and Serdes for each input/output binding.
- Distinguish merging streams from joining events by key and time.
- Understand the impact of partitioning, ordering, state stores, and application IDs.
- Test topology logic independently and verify binder wiring.

## 1. Why Do Topologies Need Multiple Inputs?

An event-processing application often aggregates data from multiple topics. For instance, an e-commerce system might receive:

- **orders**: order creation or update events.
- **payments**: payment events.
- **shipments**: shipping events.

A topology might merge all three streams to build a unified event log, or join them to compute a complete order status. Each topic serves as an independent input to the function.

The Kafka Streams binder maps input bindings to `KStream`, `KTable`, or corresponding Kafka Streams input types. When there are more than two inputs, the function signature must represent each source explicitly.

### Two Inputs: BiFunction

With exactly two inputs, you can use `BiFunction`:

~~~java
@Bean
BiFunction<
        KStream<String, String>,
        KStream<String, String>,
        KStream<String, String>> mergeTwoSources() {

    return (orders, payments) ->
        orders.merge(payments);
}
~~~

`BiFunction<T1, T2, R>` accepts two independent parameters and returns one result. This type does not extend directly to three or more parameters.

### Three Inputs: Nested Functions

Currying expresses a three-input function as a chain of single-parameter functions:

~~~java
Function<A, Function<B, Function<C, R>>>
~~~

Read it step by step:

1. The outermost function takes a value of type `A`.
2. The returned function takes a value of type `B`.
3. The next function takes a value of type `C`.
4. Once all three inputs are supplied, the final function produces a result of type `R`.

With Kafka Streams, replace `A`, `B`, `C` with concrete `KStream` types.

~~~mermaid
flowchart LR
    A["Function receiving KStream 0"] --> B["Function receiving KStream 1"]
    B --> C["Function receiving KStream 2"]
    C --> D["Build topology and return output KStream"]
~~~

Currying is a way to represent multiple parameters of a single function. It is not chaining multiple function beans via function composition like **functionA|functionB**.

## 2. Curried Signature for Three KStreams

Example of three topics sharing `String` key and value types:

~~~java
Function<
    KStream<String, String>,
    Function<
        KStream<String, String>,
        Function<
            KStream<String, String>,
            KStream<String, String>
        >
    >
>
~~~

Reading the signature from left to right:

- Input 0: `KStream<String, String>`.
- Input 1: `KStream<String, String>`.
- Input 2: `KStream<String, String>`.
- Output: `KStream<String, String>`.

This can be declared in Spring configuration:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MultiInputTopology {

    @Bean
    Function<
            KStream<String, String>,
            Function<
                    KStream<String, String>,
                    Function<
                            KStream<String, String>,
                            KStream<String, String>>>> combineEvents() {

        return orders -> payments -> shipments ->
            orders
                .mapValues(value -> "ORDER|" + value)
                .merge(payments.mapValues(value -> "PAYMENT|" + value))
                .merge(shipments.mapValues(value -> "SHIPMENT|" + value));
    }
}
~~~

The function receives the three streams in order, normalizes values with an event-type prefix, and merges them into one output stream. This is a simple merge example; in production applications, prefer a shared schema such as `EventEnvelope` rather than string concatenation when processing structured data.

The nested lambdas are evaluated when the binder constructs the topology. They do not mean the application waits for a message from the first topic before invoking the function for the second topic. Kafka Streams builds the topology from all stream sources, and the runtime then processes records across the declared branches.

## 3. Mapping Input Bindings by Parameter Order

Suppose the function bean is named `combineEvents`. The Kafka Streams binder creates bindings based on the function name:

| Parameter Position in Function | Binding | Example Destination |
|---:|---|---|
| First parameter | `combineEvents-in-0` | `orders` |
| Second parameter | `combineEvents-in-1` | `payments` |
| Third parameter | `combineEvents-in-2` | `shipments` |
| Function return value | `combineEvents-out-0` | `unified-events` |

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
~~~

Binding names must match the function name and input/output indices exactly. If you change the parameter order in the signature without updating the corresponding destinations, data can flow into the wrong branch even though the application starts successfully.

### Why Is Order a Contract?

Suppose the signature changes from:

~~~java
Function<A, Function<B, Function<C, R>>>
~~~

to:

~~~java
Function<B, Function<A, Function<C, R>>>
~~~

Input 0 and input 1 swap positions. The binder still maps bindings strictly by index; it does not infer which topic carries which business meaning. Consequently, changing input order breaks the configuration contract and must be reviewed alongside YAML, tests, and deployment configuration.

## 4. Configuring Serdes per Binding

Kafka Streams uses Serdes (serializer/deserializer) to convert keys and values between Kafka byte arrays and the topology's Java types. For the `KStream<String, String>` example, you can configure `String` Serdes for each input and output.

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
      kafka:
        streams:
          bindings:
            combineEvents-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Serde configuration lives under the Kafka Streams binder namespace, not solely under generic bindings. Each input may require its own Serde if data types differ. Outputs require Serdes matching the key/value types emitted by the topology.

### Serdes Differ from contentType

Spring Cloud Stream's `contentType` supports message conversion in the message-based model. The Kafka Streams binder works directly with Kafka Streams types and Serdes. Do not assume setting `contentType: application/json` automatically replaces all Serde configuration in a topology.

For records or business objects, choose a properly typed JSON Serde, a schema-based Serde, or a custom Serde. Test both serialization and deserialization on each binding. If topics have distinct schemas, do not share one Serde simply because they all carry JSON.

## 5. Merging Three Streams into One

`KStream.merge()` combines two streams of the same key/value types into one stream. You can chain multiple calls to merge three or more inputs.

~~~java
KStream<String, String> allEvents =
    orders
        .mapValues(value -> "ORDER|" + value)
        .merge(payments.mapValues(value -> "PAYMENT|" + value))
        .merge(shipments.mapValues(value -> "SHIPMENT|" + value));
~~~

Characteristics of `merge`:

- Does not combine two records into a single record.
- Does not wait for records with the same key or timestamp.
- Does not guarantee global ordering by time.
- Preserves each individual record from all sources in the same output stream.
- Can share a common key for downstream partitioning by business key.

If you need to identify the origin, add the event type to the payload or header before merging. For structured data, use an envelope containing `eventType`, `eventId`, `occurredAt`, and `payload` fields.

Envelope example:

~~~java
public record EventEnvelope(
    String eventId,
    String eventType,
    String aggregateId,
    Instant occurredAt,
    String payload
) {}
~~~

Source streams can be mapped into the same envelope type prior to merging. The output then has a unified schema and downstream consumers do not need to guess the source topic.

## 6. Joining Multiple Inputs by Key

`merge` works when you want to keep all events intact. If you need to combine related records into one output record, use `join`. `join` carries different semantics than `merge`.

### Stream-Stream Joins

Joining two `KStream`s typically requires:
- Matching keys across both streams.
- A window defining the time interval in which records can be matched.
- Serdes for keys and intermediate values.
- Compatible partitioning between both sources.

Illustrative example with two streams:

~~~java
KStream<String, OrderEvent> orders = ...;
KStream<String, PaymentEvent> payments = ...;

KStream<String, OrderWithPayment> paidOrders =
    orders.join(
        payments,
        OrderWithPayment::new,
        JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(5))
    );
~~~

This example uses the windowed stream-stream join API. Specific overloads may also require `StreamJoined` to specify Serdes, depending on the Kafka Streams version. For production topologies, explicitly configure Serdes for keys, values, and join results.

To combine three sources, you can join two sources first and then join the intermediate result with the third source. The curried signature still receives each input stream individually; the function body builds the join steps.

~~~java
return orders -> payments -> shipments ->
    orders
        .join(
            payments,
            OrderWithPayment::new,
            JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(5))
        )
        .join(
            shipments,
            OrderPaymentWithShipment::new,
            JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(10))
        );
~~~

This is a topology outline illustrating how joins are chained. Actual input/output types, API overloads, windows, and Serdes must be adapted to your real domain model. Records with the same key will not join unless they fall within the configured window.

### KStream-KTable and KStream-GlobalKTable

If one source represents current state, it can be modeled as a `KTable`. For instance, an order stream enriched with a customer profile table. A `KStream`-`KTable` join looks up the table value by key; it does not have the same window semantics as a stream-stream join.

With mixed input types, a curried signature can nest the corresponding Kafka Streams types if supported by the binder. Keep explicit generic types on every parameter to avoid raw types or unsafe casts.

## 7. Heterogeneous Inputs: Each Source Has Its Own Type

Currying does not require all inputs to share the same type. The signature can declare distinct stream types:

~~~java
Function<
    KStream<String, OrderEvent>,
    Function<
        KStream<String, PaymentEvent>,
        Function<
            KStream<String, ShipmentEvent>,
            KStream<String, EventEnvelope>
        >
    >
>
~~~

In this example, the three inputs have different value types and the output uses a common envelope. The function body converts each event type into the envelope before merging, or joins them by business key.

Serde configuration must match each binding:
- `combineEvents-in-0`: `OrderEvent` Serde.
- `combineEvents-in-1`: `PaymentEvent` Serde.
- `combineEvents-in-2`: `ShipmentEvent` Serde.
- `combineEvents-out-0`: `EventEnvelope` Serde.

Do not declare `KStream<String, Object>` for every input just to bypass typing. Explicit types catch schema mismatches early and minimize runtime casts. If JSON Serdes are needed, declare specific types or configure safe type mappings.

## 8. Partitioning and Co-Partitioning for Joins

Kafka Streams parallelizes work via tasks tied to partitions. For stream-stream joins, records sharing the same key must reach the same task to be matched accurately. Therefore, the two joined sources must be co-partitioned—having the same partition count and the same partitioning rule for corresponding keys—or the topology must perform the necessary repartitioning.

Checklist:
- Matching key types and serialization formats.
- Matching partitioners or compatible key-partitioning strategies.
- Aligned partition counts across joined topics.
- Whether a repartition step is introduced after key-changing operations.
- Throughput and network overhead of repartitioning.

`merge` does not require co-partitioning like stream-stream joins because it does not match records by key. However, output partitioning still affects ordering and downstream parallelism.

If a topology alters keys using `selectKey`, subsequent joins may require repartitioning to ensure records with the same key land on the same task. Verify the topology description and internal repartition topics during testing.

## 9. Processing Order and Multi-Source Semantics

Kafka guarantees ordering within a single partition, not global ordering across partitions or topics. When merging three streams, records are processed according to Kafka Streams' polling/task scheduling; you cannot assume every event from `orders` arrives before `payments` or `shipments`.

If business logic requires per-aggregate ordering:
- Use the same aggregate key so related events route to the same partition where appropriate.
- Include a sequence number or aggregate version in the payload.
- Validate versions before updating state.
- Size join windows based on real-world source latency.
- Handle late arrivals and missing events.

Do not rely on timestamps for strict ordering if producers have skewed clocks or backfill historical records. Define which timestamp serves as the source of truth and how late-arriving data is handled.

## 10. Choosing an Application ID and Managing State

The Kafka Streams application ID identifies the processing application, its internal consumer group, and associated resources such as state stores and changelogs. Instances of the same application must share the same application ID to coordinate processing; independent environments or applications require distinct IDs.

Binder configuration example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: event-consolidator
~~~

When a topology only merges streams without stateful operators, the application may create no business state stores. When using joins, aggregations, windows, or materialized tables, Kafka Streams creates state stores and changelog topics for state recovery.

Key reminders:
- Keep the application ID stable across restarts of the same application.
- Use distinct application IDs for integration tests or isolated environments.
- Do not change the application ID merely to "refresh" a topology without evaluating data reprocessing.
- When resetting input offsets, account for state stores and changelogs simultaneously.
- Do not delete internal topics manually without a recovery procedure.

## 11. Complete Configuration for a Three-Input Topology

Example combining function, bindings, and Serdes for three `String` topics:

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
      kafka:
        streams:
          binder:
            applicationId: event-consolidator
          bindings:
            combineEvents-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Paired with the function bean from Section 2, this configuration sets up three input bindings and one output binding. Before running, verify:
- All three input topics exist and contain data compatible with `String` Serde.
- The output topic has an appropriate partition configuration.
- The application ID does not collide with another independent application.
- Broker credentials and ACLs permit reading inputs, writing outputs, and managing required internal topics.
- Additional Kafka Streams settings such as replication factor for internal topics match the production environment.

## 12. Testing Curried Topologies

Test two layers separately: topology logic and Spring Cloud Stream binder wiring.

### Unit Testing with TopologyTestDriver

`TopologyTestDriver` tests a Kafka Streams topology without a running broker. Create the corresponding input topics and assert outputs:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Produced;

StreamsBuilder builder = new StreamsBuilder();

KStream<String, String> orders =
    builder.stream("orders", Consumed.with(Serdes.String(), Serdes.String()));
KStream<String, String> payments =
    builder.stream("payments", Consumed.with(Serdes.String(), Serdes.String()));
KStream<String, String> shipments =
    builder.stream("shipments", Consumed.with(Serdes.String(), Serdes.String()));

KStream<String, String> output =
    combineEvents.apply(orders).apply(payments).apply(shipments);

output.to("unified-events", Produced.with(Serdes.String(), Serdes.String()));

Topology topology = builder.build();
~~~

In an actual test, instantiate `TopologyTestDriver` with `Properties` containing mock `application.id` and `bootstrap.servers`, then create a `TestInputTopic` for each source and a `TestOutputTopic` for the output. Pipe records into all three inputs and verify:
- The output receives all expected records.
- Prefixes or event types accurately reflect their sources.
- Keys are preserved as expected.
- No records are mismatched due to swapped parameter order.

The snippet above assumes `combineEvents` is retrieved from the Spring context or instantiated directly in the test. When using the binder, `TopologyTestDriver` tests do not replace verifying actual binding names and Serde configurations.

### Integration Testing with Kafka

Use a test Kafka broker or Testcontainers to verify:
- The right `function.definition` is selected.
- `-in-0`, `-in-1`, and `-in-2` bindings map to the intended topics.
- The output binding writes to the intended destination.
- Serdes match real payloads.
- Application ID and consumer groups behave properly.
- Rebalances and restarts restore the topology and state as expected.

The Test Binder can help check Spring Cloud Stream wiring to some degree, but it does not fully simulate partition assignment, broker protocol, state restoration, or the Kafka Streams runtime. Those behaviors require integration tests against real Kafka.

## 13. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Only two inputs are bound | Function signature lacks enough nested `Function` layers | Add a `Function` layer for each remaining input |
| Data in input 1 and 2 is swapped | Parameter order does not match binding indices | Align signature order with `-in-0`, `-in-1`, `-in-2` |
| Function is not discovered | Wrong bean name or `spring.cloud.function.definition` | Declare the function name explicitly |
| Serialization/deserialization errors | Serde does not match key/value types | Configure dedicated Serdes per binding |
| Merge produces indistinguishable records | Missing event type or envelope | Normalize to an `EventEnvelope` |
| Join misses matching records | Keys or windows do not align | Inspect keys, timestamps, and join windows |
| Join throws co-partitioning error | Incompatible partition counts or partitioners | Align partitioning or repartition |
| Output emits no records | Output binding unconfigured or topology emits nothing | Check `-out-0`, destination, and topology logic |
| Restart reprocesses data | Offsets/state were reset or application ID changed | Check committed offsets, application ID, and state |
| Unit tests pass but production fails | Unit tests did not validate binder/broker wiring | Add Kafka integration tests |
| Reordering function parameters breaks flow | Binding index is a positional contract | Version signature changes and update configuration together |

## 14. Lab Exercise: Consolidating Three Event Sources

Build a `combineEvents` topology reading three topics—`orders`, `payments`, and `shipments`:

1. Declare a function bean with three nested `Function` layers.
2. Start simply with three `KStream<String, String>` inputs.
3. Add `ORDER|`, `PAYMENT|`, and `SHIPMENT|` prefixes for each source.
4. Use `merge()` to consolidate into one output stream.
5. Configure `spring.cloud.function.definition=combineEvents`.
6. Map the three inputs to `combineEvents-in-0`, `-in-1`, and `-in-2`.
7. Map the output to `combineEvents-out-0`.
8. Configure `String` Serdes for all three inputs and the output.
9. Pick a stable application ID for the application.
10. Use `TopologyTestDriver` to pipe records into each input and verify the output.
11. Run an integration test with Kafka to verify binder wiring, destinations, and Serdes.
12. Extend the exercise by converting payloads into an `EventEnvelope`.
13. Try joining `order` and `payment` by key/window, then evaluate co-partitioning.
14. Inspect the topology description, partition assignment, and state stores if present.

Acceptance checklist:

| Item | Verification Requirement |
|---|---|
| Curried signature | Exactly one `Function` layer per input |
| Input order | Parameter order matches binding indices |
| Binding names | All `-in-0`, `-in-1`, `-in-2` are present |
| Output binding | Final output is bound to the right destination |
| Serdes | Correct key/value Serdes for each topic |
| Merge/join | Right semantics chosen for the business requirement |
| Partitioning | Join inputs are co-partitioned when required |
| Ordering | No assumption of global ordering across topics |
| Application ID | Stable and free of collisions |
| Testing | Both topology unit tests and broker integration tests exist |
| Recovery | Offsets and state are verified across restarts and resets |

## Conclusion

When a Kafka Streams topology needs more than two inputs, curried functions use nested `Function` layers to receive each `KStream` in order and return the final topology. For a function named `combineEvents`, the binder maps parameters to `combineEvents-in-0`, `-in-1`, and `-in-2`, and the return value to `combineEvents-out-0`.

Keep generic signatures explicit, synchronize binding order, configure Serdes per source, and choose `merge` or `join` based on business semantics. `merge` preserves individual records without enforcing global order; `join` requires compatible keys, windows, and partitioning. Test topology logic with `TopologyTestDriver`, then validate the binder and broker via integration tests to ensure the full multi-input topology behaves reliably.

## References

- [Spring Cloud Stream Kafka Streams Binder – Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream Kafka Streams Binder – Binding Capabilities](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding.html)
- [Apache Kafka Streams – Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Apache Kafka Streams – KStream API](https://kafka.apache.org/40/javadoc/org/apache/kafka/streams/kstream/KStream.html)
- [Apache Kafka Streams – Testing](https://kafka.apache.org/documentation/streams/developer-guide/testing.html)
