# Multiple Inputs or Outputs with Supported Function Types

A Spring Cloud Stream function typically has one input and one output: Function<T, R> receives one message, processes it, and returns a result. In real event-driven systems, a processing step may need data from multiple streams, or need to emit results to multiple independent streams. Spring Cloud Stream supports reactive function signatures with multiple inputs or outputs using Reactor tuples containing Flux streams.

The key is distinguishing the number of message ports from ordinary Java method parameters. A multi-input function is represented by a single tuple parameter containing the input streams; a multi-output function returns a tuple containing the output streams. Spring Cloud Stream creates a separate binding for each port using suffixes in-0, in-1, out-0, out-1, and so on. From there, each binding can connect to the appropriate destination and consumer group.

## 1. Basic function types

Spring Cloud Stream uses Spring Cloud Function's functional model. The three basic types are:

| Function type | Simple signature | Default bindings |
|---|---|---|
| Supplier | Supplier<T> | functionName-out-0 |
| Function | Function<T, R> | functionName-in-0, functionName-out-0 |
| Consumer | Consumer<T> | functionName-in-0 |

For per-message processing, these types can use ordinary Java payloads. For continuous streams or when multiple ports are needed, use reactive types:

- Supplier<Flux<T>> emits a stream of messages.
- Function<Flux<T>, Flux<R>> transforms an input stream into an output stream.
- Consumer<Flux<T>> receives and processes a stream.

When multiple inputs or outputs are needed in one reactive function, use Reactor tuples such as Tuple2 or Tuple3. Each tuple element corresponds to one binding port. The examples below use Tuple2 to illustrate the mapping. This is how the reactive model represents multiple ports; do not declare a Java method with multiple separate parameters and expect Spring Cloud Stream to automatically create bindings for each parameter.

## 2. Multiple inputs: combining two streams

Suppose the order creation service emits OrderCreated events, while the customer service emits CustomerProfile snapshot data. A processing step needs to combine order details with customer profiles to produce EnrichedOrder.

Define the data types:

~~~java
record OrderCreated(String orderId, String customerId, long totalMinorUnits) {}

record CustomerProfile(String customerId, String displayName, String tier) {}

record EnrichedOrder(
        String orderId,
        String customerId,
        String customerName,
        String customerTier,
        long totalMinorUnits) {}
~~~

Declare a Function taking one tuple parameter where each element is a Flux:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

@Configuration
class OrderEnrichmentFunctions {

    @Bean
    Function<Tuple2<Flux<OrderCreated>, Flux<CustomerProfile>>,
             Flux<EnrichedOrder>> enrichOrders() {
        return inputs -> Flux.zip(
                inputs.getT1(),
                inputs.getT2(),
                (order, customer) -> new EnrichedOrder(
                        order.orderId(),
                        order.customerId(),
                        customer.displayName(),
                        customer.tier(),
                        order.totalMinorUnits()));
    }
}
~~~

Tuple2 holds the two input streams. getT1() accesses the first stream, and getT2() accesses the second stream. Flux.zip pairs one element from the first stream with one element from the second stream to produce a result. The function returns a single Flux<EnrichedOrder>, so there is only one output binding.

Configure the two input bindings and one output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrders-in-1:
          destination: customers.profile-snapshots
          group: order-enrichment
          content-type: application/json
        enrichOrders-out-0:
          destination: orders.enriched
          content-type: application/json
~~~

In the configuration above:

- enrichOrders-in-0 receives messages from orders.created.
- enrichOrders-in-1 receives messages from customers.profile-snapshots.
- enrichOrders-out-0 emits results to orders.enriched.

Binding names are derived from the bean name and port index. Destinations are stream names on the broker. Each input binding declares a group; this example uses the same name order-enrichment for both input streams. The binder maps the group to the corresponding consumer group, queue, or subscription per destination.

## 3. Choosing a combination operator matching data semantics

Flux.zip pairs elements by emission order: the first element of stream A goes with the first element of stream B, the second with the second, and so on. It works when both streams have a one-to-one relationship and are produced in the same order.

Do not use zip to simulate a business-key join if the two streams emit independently. For example, an order does not necessarily correspond to the next customer profile message in the profile stream. The two streams can have different rates, orderings, and element counts. In that situation, zip can mismatch data or wait indefinitely if one side stops emitting elements.

Choose the processing approach based on requirements:

| Requirement | Approach |
|---|---|
| Two streams emit matching elements in the same order | Flux.zip |
| Each order message needs to look up the latest profile by customerId | Query a service/cache or data store by key |
| Two event streams must be joined by key and time window | Use a stateful processor with window/join such as Kafka Streams or a dedicated streaming engine |
| Emit results whenever either stream changes, using the latest value from each stream | Consider combineLatest after clearly defining semantics |

For instance, combineLatest emits a result whenever either side emits a new element after both sides have emitted at least one element. It combines the latest element from each side rather than performing one-to-one pairing. Choose the operator based on business rules and test with streams running at different speeds.

## 4. Multiple outputs: branching one stream

A Function can accept one input stream and emit results to multiple output bindings. For example, high-value orders are routed to a manual review stream, while remaining orders go to the normal processing stream.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

record ManualReviewRequested(String orderId, long totalMinorUnits) {}

@Configuration
class OrderRoutingFunctions {

    @Bean
    Function<Flux<OrderCreated>,
             Tuple2<Flux<OrderCreated>, Flux<ManualReviewRequested>>> routeOrders() {
        return orders -> {
            Flux<OrderCreated> shared = orders.publish().autoConnect(2);

            Flux<OrderCreated> normalOrders =
                    shared.filter(order -> order.totalMinorUnits() < 100_000_000);

            Flux<ManualReviewRequested> reviewOrders =
                    shared.filter(order -> order.totalMinorUnits() >= 100_000_000)
                            .map(order -> new ManualReviewRequested(
                                    order.orderId(),
                                    order.totalMinorUnits()));

            return Tuples.of(normalOrders, reviewOrders);
        };
    }
}
~~~

Because the function returns Tuple2, there are two output bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.created
          group: order-router
        routeOrders-out-0:
          destination: orders.normal
        routeOrders-out-1:
          destination: orders.manual-review
~~~

routeOrders-out-0 receives normal orders; routeOrders-out-1 receives manual review requests. Output indices correspond to the element positions in the tuple: getT1() is output 0, getT2() is output 1.

The example uses publish().autoConnect(2) to share the upstream across both branches instead of creating two independent subscriptions to the source. The subscriber count must match the number of consumed branches. If the number of outputs changes or a branch is optional, adjust the sharing strategy and test subscription lifecycles so streams do not remain unconnected or subscribe to the source multiple times.

## 5. A function with multiple inputs and multiple outputs

You can combine both tuple forms in the same signature: an input tuple holding multiple Flux streams and an output tuple holding multiple Flux streams. For example, a system receives orders and a product catalog, then emits enriched orders alongside a stream of invalid-data warnings.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

record ProductInfo(String productId, String category) {}

record OrderLine(String orderId, String productId, int quantity) {}

record OrderWithCategory(
        String orderId,
        String productId,
        String category,
        int quantity) {}

record EnrichmentWarning(String orderId, String reason) {}

@Configuration
class MultiPortFunctions {

    @Bean
    Function<Tuple2<Flux<OrderLine>, Flux<ProductInfo>>,
             Tuple2<Flux<OrderWithCategory>, Flux<EnrichmentWarning>>>
    enrichAndReport() {
        return inputs -> {
            Flux<Tuple2<OrderLine, ProductInfo>> sharedPairs =
                    Flux.zip(inputs.getT1(), inputs.getT2())
                            .publish()
                            .autoConnect(2);

            Flux<OrderWithCategory> enriched = sharedPairs
                    .filter(pair -> pair.getT1().productId() != null)
                    .map(pair -> new OrderWithCategory(
                            pair.getT1().orderId(),
                            pair.getT1().productId(),
                            pair.getT2().category(),
                            pair.getT1().quantity()));

            Flux<EnrichmentWarning> warnings = sharedPairs
                    .filter(pair -> pair.getT1().productId() == null)
                    .map(pair -> new EnrichmentWarning(
                            pair.getT1().orderId(),
                            "Missing product identifier"));

            return Tuples.of(enriched, warnings);
        };
    }
}
~~~

The signature has two inputs and two outputs, so Spring Cloud Stream creates four bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichAndReport
    stream:
      bindings:
        enrichAndReport-in-0:
          destination: order-lines.created
          group: order-enrichment
        enrichAndReport-in-1:
          destination: products.catalog
          group: order-enrichment
        enrichAndReport-out-0:
          destination: orders.enriched
        enrichAndReport-out-1:
          destination: orders.enrichment-warnings
~~~

This example illustrates multi-port mapping only. The two streams are combined with zip, so it is appropriate only if their elements correspond by position. In the example, both outputs share a multicasted publisher to avoid subscribing independently to the two inputs. Do not use zip for catalog and order data unless they are emitted in synchronized pairs.

## 6. Supplier and Consumer with multiple ports

The examples above use Function because they have both inputs and outputs. A reactive Supplier can emit multiple outputs by returning a tuple of streams:

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
class MultiOutputSupplier {

    @Bean
    Supplier<Tuple2<Flux<String>, Flux<Long>>> systemSignals() {
        return () -> Tuples.of(
                Flux.just("started", "ready"),
                Flux.just(10L, 20L, 30L));
    }
}
~~~

A Supplier has no input binding; the returned tuple creates two output bindings systemSignals-out-0 and systemSignals-out-1. Configure an appropriate poller and emission lifecycle if the supplier produces a continuous stream. Do not use Flux.just in this example as an infinite event source; it only emits sample values and completes.

The two output bindings can be configured independently:

~~~yaml
spring:
  cloud:
    function:
      definition: systemSignals
    stream:
      bindings:
        systemSignals-out-0:
          destination: system.status
        systemSignals-out-1:
          destination: system.metrics
~~~

Consumer<T> is suitable when one input binding needs to perform a side effect and emit no result through an output binding. For processing multiple input streams, a reactive Function accepting a tuple is usually easier to control: the function combines the Flux streams with operators and returns the resulting publisher so the framework manages subscriptions and backpressure. Avoid calling subscribe() manually inside a Function without a specific reason; manual subscription puts errors and subscription lifecycle outside the framework's management. If side effects are needed, place them in appropriate operators such as doOnNext or in a separate Consumer.

## 7. Binding names and port ordering

Spring Cloud Stream numbers ports starting from 0 according to their position in the tuple:

| Position | Binding name | Meaning |
|---|---|---|
| First input | functionName-in-0 | Element getT1() |
| Second input | functionName-in-1 | Element getT2() |
| Third input | functionName-in-2 | Element getT3() |
| First output | functionName-out-0 | Element getT1() |
| Second output | functionName-out-1 | Element getT2() |
| Third output | functionName-out-2 | Element getT3() |

The bean names in the examples are enrichOrders, routeOrders, or enrichAndReport. spring.cloud.function.definition selects the bean to activate. Keys in spring.cloud.stream.bindings use the binding names; the destination property specifies the broker stream.

When changing the order of elements in a tuple, the meaning of the indexed bindings changes too. For example, if you swap Tuples.of(normalOrders, reviewOrders) to Tuples.of(reviewOrders, normalOrders) without updating configuration, data can go to the wrong destination even though the application still starts. Treat tuple ordering as part of the configuration contract and test it.

## 8. Backpressure, rates, and errors across streams

With multiple inputs, streams may emit at different rates. zip must wait for matching elements from both sides and can buffer elements from the fast stream while waiting for the slow stream. If one stream completes, the resulting zipped stream may also complete once no complete pairs remain. combineLatest has different semantics and typically emits after both sources have produced at least one value.

With multiple outputs, each binding can experience its own consumption rate and errors. A slow branch can build up backlog while another branch processes normally. Consider:

- Backpressure and source rate-throttling capability.
- Buffer bounds when combining streams with mismatched rates.
- Retries and DLQ per output binding.
- Behavior when one output fails to connect or that branch's consumer stops.
- Risk of a branch being subscribed multiple times when reusing the same publisher.
- Idempotency if messages may be replayed after errors.

Do not assume multiple output bindings form an atomic transaction. If sending to output 0 succeeds while output 1 fails, the system may emit only partial results. When consistency across multiple streams is required, design event IDs, an outbox, per-branch delivery state, or appropriate compensating workflows.

## 9. Testing port counts and per-branch data

The Spring Cloud Stream Test Binder can test each binding individually. For a multi-input function, send messages to the exact input binding names. For a multi-output function, read messages from each output binding to verify tuple ordering and contents.

Example testing a two-input, one-output function:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=enrichOrders",
        "spring.cloud.stream.bindings.enrichOrders-in-0.destination=orders.in",
        "spring.cloud.stream.bindings.enrichOrders-in-1.destination=customers.in",
        "spring.cloud.stream.bindings.enrichOrders-out-0.destination=orders.out"
})
class EnrichOrdersBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void combinesMessagesFromBothInputs() {
        input.send(
                MessageBuilder.withPayload(
                        new OrderCreated("ORD-1", "CUS-1", 12500)).build(),
                "enrichOrders-in-0");

        input.send(
                MessageBuilder.withPayload(
                        new CustomerProfile("CUS-1", "Lan", "GOLD")).build(),
                "enrichOrders-in-1");

        assertNotNull(output.receive(1000, "enrichOrders-out-0"));
    }
}
~~~

With zip, the test must provide an element on each input to form a pair. In real tests, also assert orderId and customerId on the result to ensure the function does not mismatch data. With multiple outputs, read from both routeOrders-out-0 and routeOrders-out-1 to verify each message enters the right branch.

The Test Binder verifies wiring at the application level but does not prove a real broker behaves identically. Integration tests with Kafka, RabbitMQ, or Pulsar should verify groups, partitions, queues/subscriptions, backpressure, retries, and scenarios where one output fails.

## 10. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Missing in-1 or out-1 configuration | A port is not connected to the right destination | Match tuple element count against configured bindings |
| Swapping tuple element order | Messages go to the wrong stream | Test each output and document port order explicitly |
| Using zip for two streams not aligned by order | Mismatched entities or indefinite waiting | Join by key/state or look up data appropriately |
| One publisher subscribed multiple times | Duplicate processing or source replay | Share upstream intentionally and test subscriptions |
| One output fails while another already sent | Partial results emitted | Use event IDs, outbox, and recovery workflows |
| Subscribing manually inside a reactive function | Loss of backpressure and error control | Return the publisher and let the framework manage subscriptions when possible |

## 11. Pre-deployment checklist

- Choose Supplier, Function, or Consumer matching the port count and processing goal.
- Use Reactor tuples for reactive functions with multiple inputs or outputs.
- Declare all bindings according to indices in-0...in-n and out-0...out-n.
- Verify tuple order matches configured destinations.
- Select stream combination operators matching data relationships; do not confuse zip with key-based joins.
- Evaluate input rates, backpressure, buffering, and the impact of one slow branch.
- Handle errors per output and never assume multi-output emission is atomic.
- Use event IDs and idempotent consumers to handle redelivery.
- Test every input, every output, and integration with a real binder/broker.

Spring Cloud Stream supports multiple inputs or outputs via reactive function types holding Reactor tuples. Each tuple element maps to an indexed binding; binding configuration connects each port to the right destination and group. By choosing the right stream combination operator, managing subscriptions, and testing each branch, applications can combine data from multiple sources or distribute results to multiple services while maintaining a clean boundary between function logic and messaging infrastructure.
