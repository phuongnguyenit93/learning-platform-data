# Function, Consumer, BiFunction, and Multi-Input Functions

The Spring Cloud Stream Kafka Streams binder lets you write topologies using familiar Java functional interfaces instead of manually creating and managing listeners for each topic. The bean's signature tells the binder how many inputs the topology needs, whether it produces outputs, and whether each binding should be represented as a `KStream`, `KTable`, or `GlobalKTable`.

The three most common types are `Function`, `Consumer`, and `BiFunction`. `Function` accepts one input and returns a result; `Consumer` accepts an input without creating an output binding; `BiFunction` accepts two inputs and returns a result. When a topology needs three or more inputs, nested `Function` types (currying) can be used. For two inputs with no output, use `BiConsumer`.

Crucially, these functions operate on Kafka Streams abstractions such as `KStream` and `KTable`, not on individual Spring `Message` objects. The binder creates the bindings and connects topics; the function body describes how data is joined, filtered, transformed, or consumed.

## 1. The Kafka Streams Binder and the Functional Model

The Kafka Streams binder is a dedicated binder for the Kafka Streams DSL. It creates and manages the Kafka Streams runtime, attaches input/output topics to the topology, and maps function signatures to bindings.

Applications typically require the Kafka Streams binder dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

In the functional model:

- A `Consumer` bean receives data to process or record, declaring no output binding.
- A `Function` bean receives data and returns a `KStream` or `KTable` as output.
- A `BiFunction` bean receives two input bindings, commonly used to join a stream with a table or two streams.
- Nested `Function` beans can declare multiple input bindings in parameter order.

The binder uses the bean name as the base for generating binding names. For example, a bean named `process` gets input binding `process-in-0` and output binding `process-out-0`. With two inputs, the default bindings are `process-in-0` and `process-in-1`.

This model differs from consumers/functions in the standard Kafka message-channel binder. The Kafka Streams binder passes `KStream`, `KTable`, or `GlobalKTable` objects into the topology so the application builds continuous processing; it does not invoke the function once per `Message` like the message-channel model.

## 2. KStream, KTable, and GlobalKTable in Function Signatures

Before choosing a function type, choose the right abstraction for each input:

| Type | Meaning | Common Role |
|---|---|---|
| `KStream<K, V>` | Key/value event stream; each record is an independent event | Order events, clicks, payments, state transitions |
| `KTable<K, V>` | State table updated by key from a changelog topic | Customer table, configuration, latest state by ID |
| `GlobalKTable<K, V>` | Full copy of a table distributed to every Kafka Streams instance | Shared lookup data, appropriately sized reference tables |

`KStream` fits when every event matters and must be processed in stream order. `KTable` represents the current state per key; newer records update the key's value, while tombstones can delete keys from the table. `GlobalKTable` also represents a state table, but the entire dataset is replicated to every application instance.

`KStream` can serve as an input or output. `KTable` and `GlobalKTable` are typically bound as inputs; when emitting state, an application can convert a `KTable` to a `KStream` via `toStream` or return a `KTable` from a `Function` as supported by the binder.

The choice of input type shapes processing semantics. For example, if the customer topic is a changelog and only each customer's latest information is needed, `KTable` is a better fit than `KStream`. If every customer address change must be processed as a historical event, `KStream` may be more appropriate.

## 3. Consumer: One Input, No Output

`Consumer` fits topologies that only consume a stream and perform terminal operations such as auditing, recording metrics, calling a controlled API, or writing to an external system via the Processor API.

Example of a `Consumer` receiving order events and writing an audit log:

~~~java
import java.util.function.Consumer;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(
        String orderId,
        String status,
        long totalMinorUnits) {}

@Configuration
class OrderAuditTopology {

    @Bean
    Consumer<KStream<String, OrderEvent>> auditOrders() {
        return orders -> orders.foreach((key, event) -> {
            System.out.printf(
                    "orderKey=%s orderId=%s status=%s total=%d%n",
                    key,
                    event.orderId(),
                    event.status(),
                    event.totalMinorUnits());
        });
    }
}
~~~

The `auditOrders` bean has one `KStream` parameter, so the binder creates one default input binding `auditOrders-in-0`. Because the function type is `Consumer`, the binder creates no output binding.

Input topic configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrders
    stream:
      bindings:
        auditOrders-in-0:
          destination: orders.events
~~~

`Consumer` has no return value. If you need to transform records and write them to another topic, use `Function`. If you need two input bindings without any output binding, use `BiConsumer`.

Do not perform non-idempotent side effects casually inside `foreach`. Kafka Streams may reprocess records during restarts or task recovery. If the terminal operation calls an external service, an idempotency key or a suitable durable write mechanism is required.

## 4. Function: One Input, One or More Outputs

`Function` fits when a topology receives a `KStream` and returns a `KStream` or `KTable`. The binder creates an input binding and an output binding.

Example filtering order events with a valid total amount:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ValidOrderTopology {

    @Bean
    Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
    validOrders() {
        return orders -> orders
                .filter((key, event) -> event.totalMinorUnits() > 0);
    }
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: validOrders
    stream:
      bindings:
        validOrders-in-0:
          destination: orders.received
        validOrders-out-0:
          destination: orders.valid
~~~

The binder reads records from `orders.received` into a `KStream`, applies the topology, and writes the remaining records to `orders.valid`. Records failing the filter predicate do not appear on the output stream.

A `Function` can also return a `KTable`. When the output is a `KTable`, the binder uses its corresponding stream representation to write results to a topic. If a downstream function receives this output in a composition chain, the downstream input signature must accept a `KTable`; do not assume every output is a `KStream`.

### Function with Multiple Outputs

Kafka Streams supports branching. A `Function` can return a `KStream` array so the binder creates multiple output bindings:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>[]>
routeOrders() {
    return orders -> {
        KStream<String, OrderEvent>[] branches = orders.branch(
                (key, event) -> "PAID".equals(event.status()),
                (key, event) -> "CANCELLED".equals(event.status()));
        return branches;
    };
}
~~~

With two branches, the binder creates `routeOrders-out-0` and `routeOrders-out-1`. Configure the two corresponding destinations:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.events
        routeOrders-out-0:
          destination: orders.paid
        routeOrders-out-1:
          destination: orders.cancelled
~~~

Each output binding receives one branch in the exact array order. The `branch` API with two predicates routes each record only to the first matching branch; records matching no predicate do not appear on any output. Ensure the number of configured destinations matches the number of `KStream` elements returned by the topology.

## 5. BiFunction: Two Inputs, One Output

When a topology needs to combine data from two topics, `BiFunction` is the direct choice. The first parameter maps to the first input binding, and the second parameter maps to the second input binding.

A common case is joining an event stream with a reference table. For instance, the `clicks` topic holds click counts per user, while `user-regions` is a changelog updating each user's region. The goal is to attach the region to each click event:

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Joined;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.KeyValue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record RegionTotal(String region, long clicks) {}

@Configuration
class RegionClickTopology {

    @Bean
    BiFunction<KStream<String, Long>, KTable<String, String>,
            KStream<String, RegionTotal>> clicksByRegion() {

        return (clicks, regions) -> clicks
                .leftJoin(
                        regions,
                        (count, region) -> new RegionTotal(
                                region == null ? "UNKNOWN" : region,
                                count),
                        Joined.with(
                                Serdes.String(),
                                Serdes.Long(),
                                Serdes.String()))
                .map((userId, regionTotal) ->
                        KeyValue.pair(regionTotal.region(), regionTotal));
    }
}
~~~

`BiFunction` creates two input bindings: `clicksByRegion-in-0` for the `KStream` and `clicksByRegion-in-1` for the `KTable`. The resulting `KStream` creates output binding `clicksByRegion-out-0`.

Destination declarations:

~~~yaml
spring:
  cloud:
    function:
      definition: clicksByRegion
    stream:
      bindings:
        clicksByRegion-in-0:
          destination: user.clicks
        clicksByRegion-in-1:
          destination: user.regions
        clicksByRegion-out-0:
          destination: clicks.by-region
~~~

A `KStream`-`KTable` join looks up the current table value by the stream's key. For partitioned `KStream` and `KTable` inputs, both sides usually must be co-partitioned: the same key must be routed consistently to the same partition so the join works accurately. Align keys, partition counts, and partitioning strategies across both topics.

`leftJoin` retains clicks even when no matching region exists yet; in that case, the example assigns `UNKNOWN`. Use `join` instead of `leftJoin` if you only want records with matching keys on both sides.

## 6. Two Inputs with No Output: BiConsumer

If a topology needs two input bindings but only performs terminal operations, use `BiConsumer`:

~~~java
import java.util.function.BiConsumer;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RegionAuditTopology {

    @Bean
    BiConsumer<KStream<String, Long>, KTable<String, String>>
    auditClickAndRegionState() {
        return (clicks, regions) -> {
            clicks.foreach((userId, count) ->
                    System.out.printf("user=%s clicks=%d%n", userId, count));

            regions.toStream().foreach((userId, region) ->
                    System.out.printf("user=%s region=%s%n", userId, region));
        };
    }
}
~~~

The binder creates `auditClickAndRegionState-in-0` and `auditClickAndRegionState-in-1` with no output binding. This topology has two independent inputs; the two `foreach` calls do not automatically establish a join relationship between the stream and the table.

If you need to combine data and emit results, use `BiFunction`. If you only need to observe both inputs, `BiConsumer` expresses that intent cleanly in its signature.

## 7. Multi-Input Functions Using Currying

Java provides `BiFunction` for two parameters. For three or more inputs, the Kafka Streams binder supports nested functions, also known as curried functions. Each inner `Function` accepts one additional input; the innermost `Function` returns the resulting topology.

For example, suppose we need to combine:

- An orders `KStream`.
- A customers `GlobalKTable`.
- A products `GlobalKTable`.

The output is an order stream enriched with customer and product details:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.GlobalKTable;
import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Order(Long customerId, Long productId, int quantity) {}

record Customer(String name) {}

record Product(String name, long priceMinorUnits) {}

record CustomerOrder(Order order, Customer customer) {}

record EnrichedOrder(
        String customerName,
        String productName,
        int quantity,
        long totalMinorUnits) {}

@Configuration
class EnrichOrderTopology {

    @Bean
    Function<KStream<Long, Order>,
            Function<GlobalKTable<Long, Customer>,
                    Function<GlobalKTable<Long, Product>,
                            KStream<Long, EnrichedOrder>>>> enrichOrders() {

        return orders -> customers -> products ->
                orders.join(
                        customers,
                        (orderId, order) -> order.customerId(),
                        (order, customer) ->
                                new CustomerOrder(order, customer))
                .join(
                        products,
                        (orderId, customerOrder) ->
                                customerOrder.order().productId(),
                        (customerOrder, product) ->
                                new EnrichedOrder(
                                        customerOrder.customer().name(),
                                        product.name(),
                                        customerOrder.order().quantity(),
                                        product.priceMinorUnits()
                                                * customerOrder.order().quantity()));
    }
}
~~~

The function signature is read from the outside in:

1. The first `Function` receives `KStream<Long, Order>` and returns another `Function`.
2. The second `Function` receives `GlobalKTable<Long, Customer>` and returns the next `Function`.
3. The third `Function` receives `GlobalKTable<Long, Product>` and returns `KStream<Long, EnrichedOrder>`.

The binder creates three input bindings in parameter order: `enrichOrders-in-0`, `enrichOrders-in-1`, and `enrichOrders-in-2`. The final result creates `enrichOrders-out-0`.

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders
        enrichOrders-in-1:
          destination: customers
        enrichOrders-in-2:
          destination: products
        enrichOrders-out-0:
          destination: orders.enriched
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: order-enrichment-v1
~~~

In this example, `orders` is an event stream, while `customers` and `products` are lookup tables replicated as `GlobalKTable`s. Using `GlobalKTable` allows looking up by a key derived from the order record without requiring those two table topics to share the same partitioning as `orders`. In exchange, the entire tables are replicated to every instance, so evaluate data size and network/storage costs.

If an application runs multiple Kafka Streams processors within the same process, each processor needs an appropriate, distinct application ID. For a single processor, you can configure `applicationId` at the binder level or use the application name according to your version's guide. Do not share one application ID across independent topologies unless they are intentionally meant to share state and consumer groups.

## 8. Adding More Inputs: When Should You Stop?

Currying makes multiple inputs possible, but increasing binding counts makes topologies harder to reason about:

| Input Count | Typical Function Type | Possible Output Count |
|---:|---|---:|
| 1 | `Consumer` | 0 |
| 2 | `BiConsumer` | 0 |
| 1 | `Function` | 1 or more |
| 2 | `BiFunction` | 1 or more |
| 3 or more | Curried `Function` | 0 or more, depending on the final type |

Do not stuff every topic into a single function just because the binder supports it. When inputs proliferate, consider splitting topologies by responsibility: one processor normalizes reference data, another performs enrichment, and a subsequent processor computes business logic.

Splitting reduces coupling across schemas, partitioning, update rates, and deployment lifecycles of data sources. It also makes step-by-step testing and per-input lag monitoring much easier.

## 9. Binding Naming and Function Activation

Default binding names are derived from the bean name and parameter positions. For a bean named `process` (or `enrichOrders` in the three-input case):

| Bean Signature | Default Inputs | Default Outputs |
|---|---|---|
| `Consumer<KStream<...>> process` | `process-in-0` | None |
| `Function<KStream<...>, KStream<...>> process` | `process-in-0` | `process-out-0` |
| `BiFunction<KStream<...>, KTable<...>, KStream<...>> process` | `process-in-0`, `process-in-1` | `process-out-0` |
| Three-input curried `Function` `enrichOrders` | `enrichOrders-in-0`, `in-1`, `in-2` | `enrichOrders-out-0` |
| `Function` returning a two-branch `KStream[]` | `process-in-0` | `process-out-0`, `process-out-1` |

If an application declares multiple `Function`/`Consumer` beans, explicitly activate the ones to run:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrders;validOrders;enrichOrders
~~~

Definitions are separated by semicolons when running multiple independent processors in the same application. For linear function composition, a pipe character chains functions in order, for example:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders|validOrders
~~~

Composition only works when the output type of the preceding step matches the input type of the following step. A `Function` can compose with another `Function` or end with a `Consumer`. A `BiFunction` must come first in the composition chain; subsequent steps are `Function` or `Consumer`. You cannot chain another `BiFunction` after a `BiFunction`, cannot start a chain with a `Consumer`, and cannot place a `KStream[]` output in the middle of a chain.

If a function outputs a `KTable`, the next function must accept a `KTable`. The binder does not automatically convert a `KTable` into a `KStream` just because the next bean expects a `KStream`; if a type conversion is needed, use `toStream` explicitly.

## 10. Configuring Serdes per Input Binding

Kafka Streams needs to know how to convert keys and values between bytes and Java types. The binder can infer Serdes from function signatures and available Serde beans. Common types like `String`, `Long`, `Integer`, `UUID`, and `byte[]` have built-in Serdes; business domain types usually need JSON Serdes or custom Serdes.

With multiple inputs, do not assume all bindings share the same Serde. For instance, `orders` has `Order` values, `customers` has `Customer` values, and `products` has `Product` values. Each binding may need its own configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichOrders-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
~~~

This example specifies the `Long` key Serde for all three inputs. Value Serdes can be inferred from generic types or configured individually with `valueSerde` as needed. For Avro/Protobuf or a schema registry, configure dedicated serializers/deserializers matching each topic's contract.

The Kafka Streams binder uses native deserialization for inputs by default. If you want Spring Cloud Stream's message conversion instead, disable native decoding on each corresponding input binding; do not assume configuring one input changes the others.

If a Serde mismatches actual data, errors can occur before `Function` logic runs. Check key/value types in the signature, Serde beans, binding configurations, and producer schemas.

## 11. KStream-KTable Joins and Partitioning Requirements

When using `BiFunction` to join a `KStream` with a `KTable`, keys on both sides must be compatible. For partitioned joins, Kafka Streams requires both sources to be co-partitioned so records with the same key can be processed on the same task.

Verify:

- Both topics have compatible partition counts.
- Identical keys are serialized in the same format.
- Both use the same partitioning strategy or hash rule.
- If rekeying is needed, use `selectKey` or `map` before the join and account for repartitioning.
- Do not increase partition counts on only one side without re-evaluating the topology.

`GlobalKTable` has different semantics: the entire table is replicated to every instance. A `KStream` can use a key selector to look up any key in the `GlobalKTable`, without needing co-partitioning like a `KTable`. However, large tables can increase memory, network, and recovery costs.

## 12. Testing Function Signatures and Topologies

Tests should verify both how the binder constructs bindings and the processing results:

1. Single-input `Consumer`: send records and verify the terminal action executes with no output binding.
2. Single-input `Function`: send valid/invalid records and verify outputs.
3. `BiFunction`: send stream records alongside table data and verify joins match by key.
4. Curried function: send data to all input bindings in the right order.
5. `KTable`: update the same key multiple times and verify the latest value is used.
6. `GlobalKTable`: look up data whose key lives on a different partition from the `KStream` and verify results.
7. Branching: verify the number of output bindings matches the number of returned `KStream` branches.
8. Serdes: test keys/values on each input binding, including schema-invalid payloads.
9. Composition: verify the output type of each step matches the input type of the next step.

`TopologyTestDriver` can test Kafka Streams topology logic without a broker for pure transformations. However, integration tests with a real Kafka broker are still needed to verify that the binder creates the proper bindings, application IDs, Serdes, partition assignments, and state stores in practice.

## 13. Common Mistakes When Using Multiple Inputs

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Only one topic is consumed | Only one parameter declared, or `Function` used instead of `BiFunction` | Check the bean signature and input binding count |
| Binding `in-1` or `in-2` not found | Curried `Function` lacks enough nested `Function` layers | Check nested types and binding names |
| Join produces no results | Keys differ, `KTable` lacks data yet, or inputs are not co-partitioned | Check keys, Serdes, partitions, and update timing |
| `GlobalKTable` data updates slowly | The table must be replicated to every instance | Monitor restore/replication and consider `KTable` if appropriate |
| Consumer receives wrong value type | Serde inference mismatch or missing binding configuration | Declare the proper `valueSerde` per input |
| Output binding exists but emits no records | Function filters everything out or returns an empty topology | Check predicates, joins, and input data |
| Output binding count mismatch | `KStream[]` array has a different branch count than configured | Check actual branch count and how unmatched records are handled |
| Function composition fails to start | Incompatible input/output types or `BiFunction` placed mid-chain | Review composition rules and generic signatures |
| Processors unintentionally share state | Duplicate application ID across independent topologies | Assign distinct application IDs per processor |

## 14. Function Design Checklist

- Determine how many inputs and outputs the topology requires.
- Choose `Consumer` when taking one stream and emitting no output.
- Choose `Function` when one input produces one or more outputs.
- Choose `BiFunction` for two inputs with output; `BiConsumer` for two inputs without output.
- Use curried `Function` for three or more inputs.
- Pick `KStream`, `KTable`, or `GlobalKTable` according to topic semantics.
- Configure destinations for each `in-0`, `in-1`, `in-2`, and `out-0` binding.
- Explicitly activate beans via `function.definition` when the application defines multiple processors.
- Configure appropriate Serdes for keys and values on each input.
- Evaluate co-partitioning for `KStream`-`KTable` joins and replication cost for `GlobalKTable`.
- Set an appropriate application ID, avoiding sharing across independent processors.
- Test both topology logic and real bindings against Kafka.

The Kafka Streams binder infers topology structure from function types: `Consumer` for one input with no output, `Function` for one input with output, `BiFunction` for two inputs with output, and curried `Function` for additional inputs. Choosing `KStream`, `KTable`, or `GlobalKTable` defines the data semantics the function receives; parameter names and nesting order determine the corresponding input bindings. With well-designed signatures, bindings, Serdes, and partitioning, an application can combine multiple topics into a clear topology while keeping testing and operations manageable.

## References

- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/overview.html)
