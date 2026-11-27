# Supported Function Composition and Binding Names of Composed Topologies

The Kafka Streams binder lets you assemble a topology from multiple Java function beans without writing an extra glue function just to wire one function's output into the next function's input. This mechanism uses **function composition** expressions in the `spring.cloud.function.definition` property. The `|` symbol chains functions in execution order; the binder creates a single processor topology and generates binding names from the names of the composed beans.

For example, two functions `normalize` and `enrich` can be declared independently and then activated with the definition `normalize|enrich`. The binder connects `normalize`'s `KStream` output into `enrich`'s input. The input and output bindings are named after the composed function: `normalizeenrich-in-0` and `normalizeenrich-out-0`.

Understanding which function types are supported, composition constraints, and binding naming rules ensures destinations, Serdes, and Kafka Streams properties attach to the right topology ports.

## 1. Composition in the Kafka Streams Binder

The Kafka Streams binder uses the functional programming model with Java types such as `Function`, `Consumer`, `BiFunction`, and curried functions to represent input/output `KStream`, `KTable`, or `GlobalKTable`.

Each function bean typically performs a single, independently readable processing step:

- Normalizing data or validating conditions.
- Enriching events by joining with a reference table.
- Computing, aggregating, or transforming data structures.
- Writing results to a topic or ending the topology with a `Consumer`.

Composition chains these steps into a linear processing pipeline. Each function remains a separate Spring bean, while the binder treats the composed expression as one processor function to build the topology.

~~~mermaid
flowchart LR
    A[(Topic orders)] --> B[Binding normalizeenrich-in-0]
    B --> C[normalize: KStream]
    C --> D[enrich: KStream]
    D --> E[Binding normalizeenrich-out-0]
    E --> F[(Topic enriched-orders)]
~~~

In the diagram, `normalize` and `enrich` are composed into a single topology. Intermediate outputs between the two functions do not create separate topics or output bindings. Only the chain's entry input and final output become bindings—unless the final function is a `Consumer` or returns multiple `KStream`s via branching.

## 2. Declaring Separate Function Beans

Suppose the system receives order events, validates amounts, and builds summaries for downstream consumers:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<KStream<String, Order>, KStream<String, Order>>
            normalize() {
        return orders -> orders
                .filter((key, order) -> order.total().signum() >= 0);
    }

    @Bean
    public Function<KStream<String, Order>, KStream<String, OrderSummary>>
            summarize() {
        return orders -> orders.mapValues(order ->
                new OrderSummary(order.id(), order.total()));
    }

    public record Order(String id, BigDecimal total) {
    }

    public record OrderSummary(String orderId, BigDecimal total) {
    }
}
~~~

Each `@Bean` method takes its method name as its bean name. Thus, the two functions in this example are named `normalize` and `summarize`. The binder uses these exact names in function definitions and generated binding names.

The `normalize` function accepts and returns `KStream<String, Order>`. The `summarize` function accepts `KStream<String, Order>` and returns `KStream<String, OrderSummary>`. Because the first step's output type matches the next step's input type, the two functions can be composed.

Activating composition:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize"
    stream:
      bindings:
        normalizesummarize-in-0:
          destination: orders
        normalizesummarize-out-0:
          destination: order-summaries
~~~

The binder constructs a topology from `normalize` followed by `summarize`. Default binding names:

- `normalizesummarize-in-0`: input of the composed function.
- `normalizesummarize-out-0`: final output of the composed function.

There are no `normalize-out-0` or `summarize-in-0` bindings for the internal link. If you want to write an intermediate result to a topic, express that write in the Kafka Streams DSL or design a separate processor topology.

## 3. Distinguishing | and ;

These two characters carry distinct meanings in `spring.cloud.function.definition`:

| Syntax | Meaning | Result |
|---|---|---|
| `normalize|summarize` | Composes functions into a single chain. | One linear topology with input/output bindings for the composed function. |
| `normalize;summarize` | Activates two independent functions. | Two separate processors/topologies, each with its own bindings. |
| `normalize|summarize;archive` | Composes the first two functions and activates `archive` separately. | One composed topology and one independent topology. |

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize;archive"
~~~

In this configuration, `normalize` and `summarize` form one composed topology; `archive` is another processor. The semicolon does not connect `summarize`'s output to `archive`.

When an application runs multiple independent Kafka Streams processors, each processor needs its own application ID. Configure an application ID per function when running multiple processors so consumer groups, state stores, and scaling remain cleanly isolated. Never use a binding name in place of an application ID.

## 4. Supported Composable Function Types

The Kafka Streams binder supports constrained composition to build linear topologies:

| First Component | Next Component | Supported | Notes |
|---|---|---|---|
| `Function` | One or more `Function`s | Yes | Output of the preceding step must match input of the next step. |
| `Function` | `Consumer` | Yes | `Consumer` must be the final step; the topology has no output binding. |
| `BiFunction` | One or more `Function`s | Yes | `BiFunction` must come first in the chain. |
| `BiFunction` | `Consumer` | Yes | `Consumer` terminates the chain. |
| `BiFunction` | `BiFunction` | No | Cannot chain another `BiFunction` within the same definition. |
| `Consumer` | Any function | No | `Consumer` cannot be first because it produces no output for the next step. |
| `BiConsumer` | Any function | No | `BiConsumer` is not supported in composition. |
| Function returning `KStream[]` | Next function | No | A function returning a branching array can only be the final step. |

The combinations above define the Kafka Streams binder's supported scope. Do not extrapolate general Spring Cloud Function composition rules to arbitrary `Supplier`, `BiConsumer`, or custom signatures in the Kafka Streams binder.

### Function Chained with Function

This is the simplest case. The subsequent function accepts the exact type returned by the preceding function:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>>
        validateOrder() {
    return stream -> stream.filter(
            (key, order) -> order.total().signum() > 0);
}

@Bean
public Function<KStream<String, Order>, KStream<String, EnrichedOrder>>
        enrichOrder() {
    return stream -> stream.mapValues(order ->
            new EnrichedOrder(order.id(), order.total(), "STANDARD"));
}
~~~

Definition:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|enrichOrder"
~~~

`validateOrder`'s `KStream<String, Order>` output becomes `enrichOrder`'s input. If types are incompatible, the composition cannot be built properly.

### Function Ending with Consumer

A topology can transform data and write directly to a target system inside a `Consumer`:

~~~java
import java.util.function.Consumer;

@Bean
public Function<KStream<String, Order>, KStream<String, OrderSummary>>
        summarizeOrder() {
    return stream -> stream.mapValues(order ->
            new OrderSummary(order.id(), order.total()));
}

@Bean
public Consumer<KStream<String, OrderSummary>> storeSummary(
        SummaryRepository repository) {
    return stream -> stream.foreach((key, summary) ->
            repository.save(summary));
}
~~~

Definition:

~~~yaml
spring:
  cloud:
    function:
      definition: "summarizeOrder|storeSummary"
~~~

`storeSummary` is the final component. The composed function gets default input binding `summarizeOrderstoreSummary-in-0` and no output binding because `Consumer` returns no `KStream`. Writing data inside `foreach` is an application side effect; account for idempotency and retry/reprocessing impact.

## 5. Composing Functions Starting with BiFunction

When a topology has two input sources, the first function can be a `BiFunction`. For example, joining an order stream with a customer table:

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;

@Bean
public BiFunction<KStream<String, Order>,
        KTable<String, Customer>,
        KStream<String, EnrichedOrder>> enrichFromCustomer() {
    return (orders, customers) -> orders.leftJoin(
            customers,
            (order, customer) -> new EnrichedOrder(
                    order.id(),
                    order.total(),
                    customer == null ? "UNKNOWN" : customer.segment()
            )
    );
}

@Bean
public Function<KStream<String, EnrichedOrder>,
        KStream<String, OrderView>> toOrderView() {
    return enriched -> enriched.mapValues(order ->
            new OrderView(order.id(), order.segment()));
}
~~~

Declaration:

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichFromCustomer|toOrderView"
~~~

`BiFunction` must be the first function in the chain. Subsequent components must be `Function` or `Consumer`, never another `BiFunction`.

The two inputs are indexed in parameter order:

- First parameter `KStream<String, Order>` creates input binding `enrichFromCustomertoOrderView-in-0`.
- Second parameter `KTable<String, Customer>` creates input binding `enrichFromCustomertoOrderView-in-1`.
- The final output creates binding `enrichFromCustomertoOrderView-out-0`.

In the Kafka Streams binder, parameter types `KStream`, `KTable`, or `GlobalKTable` determine binding types. Parameter order is part of the topology contract; changing order can wire destinations or Serdes to the wrong source.

## 6. Using Curried Functions for Multiple Inputs

When a topology needs more than two inputs, the binder supports **curried** functions. Instead of a function taking three or more parameters, the method returns nested functions. Each partial application adds one input binding.

Example joining orders with customer and product tables:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.GlobalKTable;
import org.apache.kafka.streams.kstream.KStream;

@Bean
public Function<KStream<String, Order>,
        Function<GlobalKTable<String, Customer>,
                Function<GlobalKTable<String, Product>,
                        KStream<String, EnrichedOrder>>>> enrichOrder() {

    return orders -> customers -> products ->
            orders.join(
                    customers,
                    (orderKey, order) -> order.customerId(),
                    (order, customer) -> new OrderWithCustomer(order, customer)
            ).join(
                    products,
                    (key, value) -> value.order().productId(),
                    (value, product) -> new EnrichedOrder(
                            value.order(), value.customer(), product)
            );
}
~~~

Single-function definition:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
~~~

The binder creates three input bindings in order:

| Binding | Input Type | Example Destination |
|---|---|---|
| `enrichOrder-in-0` | `KStream<String, Order>` | `orders` |
| `enrichOrder-in-1` | `GlobalKTable<String, Customer>` | `customers` |
| `enrichOrder-in-2` | `GlobalKTable<String, Product>` | `products` |
| `enrichOrder-out-0` | `KStream<String, EnrichedOrder>` | `enriched-orders` |

You can compose an initial curried function with a subsequent `Function`:

~~~java
@Bean
public Function<KStream<String, EnrichedOrder>,
        KStream<String, OrderView>> toOrderView() {
    return stream -> stream.mapValues(EnrichedOrder::toView);
}
~~~

Definition:

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichOrder|toOrderView"
~~~

In this case, the default binding names for the composed function are:

- `enrichOrdertoOrderView-in-0`
- `enrichOrdertoOrderView-in-1`
- `enrichOrdertoOrderView-in-2`
- `enrichOrdertoOrderView-out-0`

Curried functions enable multiple input bindings without needing a custom `BiFunction` variant for every arity. However, too many inputs make Java signatures hard to read and topologies hard to operate. If a processor needs many independent sources, consider splitting topologies or placing reference data into an appropriate state store.

## 7. Output-to-Input Type Compatibility Rules

Composition chains functions by data type. The preceding function's output type must match the input type accepted by the next function. The binder does not automatically convert every Kafka Streams structure to force two functions to be compatible.

| Preceding Step Output | Next Step Input | Result |
|---|---|---|
| `KStream<K, V>` | `KStream<K, V>` | Composes directly if generic types match. |
| `KTable<K, V>` | `KTable<K, V>` | Composes directly. |
| `KStream<K, V>` | `KTable<K, V>` | Not directly compatible. |
| `KTable<K, V>` | `KStream<K, V>` | Not directly compatible if the next function declares `KStream`. |
| `KTable<K, V>` | `KTable<K, V>` | Composable; the next function must accept `KTable`. |

### When KTable Is the Output

The Kafka Streams binder allows `KTable` as the final output binding. However, when a `KTable` is an intermediate output in a composition, the next function must accept a `KTable`.

Valid example:

~~~java
@Bean
public Function<KStream<String, String>, KTable<String, String>>
        toTable() {
    return KStream::toTable;
}

@Bean
public Function<KTable<String, String>, KStream<String, String>>
        toStream() {
    return KTable::toStream;
}
~~~

Definition:

~~~yaml
spring:
  cloud:
    function:
      definition: "toTable|toStream"
~~~

`toStream` accepts `KTable` because `toTable`'s output is `KTable`. Changing `toStream`'s signature to `Function<KStream<...>, ...>` makes the chain incompatible. Converting between table and stream must be expressed explicitly via Kafka Streams APIs such as `toStream()` or `toTable()`.

## 8. Limitations When Composing Functions

The Kafka Streams binder supports minimal composition for linear topologies. Key constraints:

1. A `Function` can compose with one or more `Function`s.
2. A `Function` can terminate with a `Consumer`.
3. A `BiFunction` can only appear first; subsequent elements are `Function` or `Consumer`.
4. Never chain a second `BiFunction` after the first `BiFunction`.
5. Never compose `BiConsumer`.
6. Never start a chain with `Consumer`.
7. A function returning `KStream[]` for branching can only appear at the end of the chain.
8. `KStream`/`KTable` types between adjacent steps must match.
9. Never compose a function using the regular Kafka message-channel binder with a function using the Kafka Streams binder in the same chain. An application can run both processor types independently, but composition must stay within the same binder model.

### Branching and KStream[]

Kafka Streams supports splitting one stream into multiple branches. A function can return a `KStream[]` array; the binder creates one output binding per array element.

Branching function example:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>[]>
        branchOrders() {
    return input -> {
        KStream<String, Order> highValue =
                input.filter((key, order) -> order.total().intValue() >= 1000);
        KStream<String, Order> regular =
                input.filter((key, order) -> order.total().intValue() < 1000);

        @SuppressWarnings("unchecked")
        KStream<String, Order>[] branches = new KStream[] {
                highValue, regular
        };
        return branches;
    };
}
~~~

Default output bindings:

- `branchOrders-out-0`
- `branchOrders-out-1`

If the branching function is the final function in a composition chain, binding names are formed from the composed function name plus the output suffixes. You cannot chain another function after a step returning `KStream[]` within the same composition; apply follow-up operations inside each branch or design a separate topology.

## 9. Default Binding Names of Single Functions

Before understanding composed binding names, know the rules for a standalone function:

| Function Type | Default Input Bindings | Default Output Bindings |
|---|---|---|
| `Consumer<KStream<...>>` | `<bean>-in-0` | None |
| `Function<KStream<...>, KStream<...>>` | `<bean>-in-0` | `<bean>-out-0` |
| `BiFunction<KStream<...>, KTable<...>, KStream<...>>` | `<bean>-in-0`, `<bean>-in-1` | `<bean>-out-0` |
| Three-input curried `Function` | `<bean>-in-0`, `-in-1`, `-in-2` | `<bean>-out-0` |
| Function returning `KStream[]` | `<bean>-in-0` | `<bean>-out-0`, `-out-1`, ... |

Binding names are built from the function bean name and input/output indices. They are logical names in Spring Cloud Stream used to configure destinations, groups, Serdes, and binding properties.

If `destination` is not configured, the binder may use the binding name as the default topic name or require the corresponding topic to already exist depending on permissions and provisioning settings. In production, configure `destination` explicitly to avoid accidentally creating topics named after bindings.

## 10. Binding Naming Rules for Composed Topologies

With function composition, the binder concatenates function bean names in the exact order listed in the definition to form the composed function name. Then it appends input/output suffixes and indices.

Example:

~~~text
spring.cloud.function.definition=foo|bar

Composed function name: foobar
Input binding:          foobar-in-0
Output binding:         foobar-out-0
~~~

Three-step example:

~~~text
spring.cloud.function.definition=decode|validate|enrich

Composed function name: decodevalidateenrich
Input binding:          decodevalidateenrich-in-0
Output binding:         decodevalidateenrich-out-0
~~~

If the first function is curried with two inputs:

~~~text
spring.cloud.function.definition=curriedFoo|bar

Composed function name: curriedFoobar
Input binding 0:        curriedFoobar-in-0
Input binding 1:        curriedFoobar-in-1
Output binding:         curriedFoobar-out-0
~~~

If the final function is a `Consumer`:

~~~text
spring.cloud.function.definition=normalize|persist

Input binding:  normalizepersist-in-0
Output binding: none
~~~

A binding name is not a topic name, consumer group, or application ID. It is a topology port name used by Spring Cloud Stream to apply configuration. `destination` specifies the actual Kafka topic to which the binding connects.

## 11. Setting Destinations for Composition Bindings

Example composing `normalize|enrich` into one topology:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      bindings:
        normalizeenrich-in-0:
          destination: orders
        normalizeenrich-out-0:
          destination: enriched-orders
~~~

`normalizeenrich-in-0` reads from `orders`; `normalizeenrich-out-0` writes final results to `enriched-orders`.

Do not configure a destination for an intermediate binding such as `normalize-out-0`, because that binding does not exist in the composed topology. Using the wrong name means properties will not apply to your intended topology.

### Configuring Multiple Inputs

For `curriedFoo|bar`, each input must have its own destination:

~~~yaml
spring:
  cloud:
    function:
      definition: "curriedFoo|bar"
    stream:
      bindings:
        curriedFoobar-in-0:
          destination: orders
        curriedFoobar-in-1:
          destination: customers
        curriedFoobar-out-0:
          destination: enriched-orders
~~~

The first and second inputs map in parameter order of the curried function. Inspect the bean signature before assigning destinations, especially when one source is a `KTable` or `GlobalKTable`.

## 12. Renaming Default Bindings with Aliases

Long concatenated binding names can become hard to read when topologies compose many functions. Spring Cloud Stream lets you map a default name to a friendlier alias via:

~~~text
spring.cloud.stream.function.bindings.<default-binding-name>
~~~

Example renaming bindings of `normalize|enrich`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      function:
        bindings:
          normalizeenrich-in-0: orders-input
          normalizeenrich-out-0: orders-output
      bindings:
        orders-input:
          destination: orders
        orders-output:
          destination: enriched-orders
~~~

After mapping:

- `normalizeenrich-in-0` is referenced via the alias `orders-input`.
- `normalizeenrich-out-0` is referenced via the alias `orders-output`.
- Binding-level properties such as `destination` must be placed under the new alias.

When configuring additional group, consumer, or extended Kafka Streams properties, use the corresponding alias once renamed. Do not continue placing properties under the old default name expecting them to apply to the alias.

### Aliases for Multi-Input Topologies

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichOrder|toOrderView"
    stream:
      function:
        bindings:
          enrichOrdertoOrderView-in-0: orders-source
          enrichOrdertoOrderView-in-1: customers-table
          enrichOrdertoOrderView-in-2: products-table
          enrichOrdertoOrderView-out-0: order-views
      bindings:
        orders-source:
          destination: orders
        customers-table:
          destination: customers
        products-table:
          destination: products
        order-views:
          destination: order-views
~~~

Aliases clarify the role of each source. Binding types are still determined by the `KStream`, `KTable`, or `GlobalKTable` types in the function signature; aliases only rename the configuration port.

## 13. Binding Names and Kafka Streams Extended Properties

The Kafka Streams binder supports extended per-binding properties, such as Serdes, state store materialization, timestamp extractors, or event types. Once a binding is aliased, use the alias for extended properties too.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      function:
        bindings:
          normalizeenrich-in-0: orders-input
          normalizeenrich-out-0: orders-output
      bindings:
        orders-input:
          destination: orders
        orders-output:
          destination: enriched-orders
      kafka:
        streams:
          bindings:
            orders-input:
              consumer:
                value-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

This example shows where Serde configuration goes when using an alias. Actual Serdes must match the topic's keys/values and the data types processed by the topology. If you do not alias the binding, use the default binding name `normalizeenrich-in-0` under the Kafka Streams namespace.

Do not confuse:

- `spring.cloud.stream.bindings.<name>` — general binding configuration such as `destination`.
- `spring.cloud.stream.kafka.streams.bindings.<name>` — Kafka Streams binder-specific extended configuration.
- `spring.cloud.stream.function.bindings.<default-binding-name>` — mapping from default binding name to alias.

## 14. Distinguishing Binding Names and Application IDs

Kafka Streams uses `application.id` to identify a processor application, its consumer group, and associated state. A binding name only identifies an input/output port in Spring Cloud Stream.

| Concept | Example | Purpose |
|---|---|---|
| Function bean name | `normalize` | Identifies the function bean in Spring. |
| Function definition | `normalize|enrich` | Declares composition and execution order. |
| Composed function name | `normalizeenrich` | Composed function name derived by the binder. |
| Binding name | `normalizeenrich-in-0` | Input port used to configure destination and consumer properties. |
| Destination | `orders` | Source or target Kafka topic. |
| Application ID | `order-enrichment-v1` | Identifies the Kafka Streams application and consumer group. |

With multiple independent Kafka Streams processors in the same application, set a separate application ID for each processor in the binder configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            functions:
              archive:
                application-id: order-archive-v1
              audit:
                application-id: order-audit-v1
~~~

The function name in `functions.<function-name>.applicationId` is the activated function bean/processor name. Double-check the exact function name when configuring multiple processors. Never set an application ID to a binding name such as `normalizeenrich-in-0`; the two concepts have different lifecycles and meanings.

## 15. Composition and Multiple Independent Processors in One Application

An application can declare multiple function beans and specify which processors to activate in the definition. Example:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>>
        normalize() {
    return stream -> stream.filter(
            (key, order) -> order.total().signum() >= 0);
}

@Bean
public Function<KStream<String, Order>, KStream<String, OrderSummary>>
        summarize() {
    return stream -> stream.mapValues(
            order -> new OrderSummary(order.id(), order.total()));
}

@Bean
public Consumer<KStream<String, AuditEvent>> audit(
        AuditRepository auditRepository) {
    return stream -> stream.foreach((key, event) ->
            auditRepository.store(event));
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize;audit"
    stream:
      bindings:
        normalizesummarize-in-0:
          destination: orders
        normalizesummarize-out-0:
          destination: order-summaries
        audit-in-0:
          destination: audit-events
~~~

In this example:

- `normalize|summarize` is a composed topology with an input and an output.
- `audit` is a separate topology with only an input.
- `audit` does not receive intermediate output from `summarize`.

If you need to audit the exact events produced by `summarize`, either append `audit` to the composition or emit a separate stream using the Kafka Streams DSL. Do not use `;` expecting the binder to wire two processors together.

## 16. When to Compose Functions vs. Split Topologies

Composition fits linear processing steps that share the same lifecycle and belong in one topology. Splitting into multiple processors fits branches with different deployment, application ID, state, scaling, or permission requirements.

| Criterion | Composed via `|` | Independent Processors via `;` |
|---|---|---|
| Topology | Single linear chain | Multiple separate topologies |
| Bindings | One input/output set for the composed function | Each function has its own bindings |
| Intermediate outputs | No automatic intermediate bindings | Can connect via topics if configured |
| Lifecycle | Steps share the same processor | Each processor can be managed independently |
| Application ID | One processor identity for the composed topology | Needs per-processor identification |
| Best suited for | Normalize → enrich → transform | Independent audit, projection, and archival |

Avoid overly long compositions merely to reduce bean counts or configuration lines. A linear chain with too many steps still becomes difficult to test, modify, and observe. Draw boundaries according to business domains and operational requirements.

## 17. Testing Function Composition and Binding Names

Testing should verify both data logic and topology configuration:

1. Unit test each function bean independently to validate transformation logic.
2. Test composition in the exact function order.
3. Verify output/input types at every connection point.
4. Check the number and names of bindings created by the binder.
5. Verify each binding points to the expected destination.
6. Verify aliases and extended Kafka Streams properties attach to the intended bindings.
7. With multiple processors, confirm each processor gets its expected application ID.

### Example Processing Flow Check

For composition `normalize|summarize`, construct input records:

| Key | Order | Expected Outcome |
|---|---|---|
| `o-1` | total = 120 | Retained and converted to `OrderSummary`. |
| `o-2` | total = -5 | Filtered out in `normalize`. |
| `o-3` | total = 0 | Retained when condition is `signum() >= 0`. |

The topology test should assert:

- Output contains only records passing `normalize`.
- Output values are `OrderSummary` instances built by `summarize`.
- Keys are preserved or modified accurately per step logic.
- No intermediate output binding exists for the first function.

### Checking Binding Names

You can inspect generated bindings via the Actuator bindings endpoint when enabled. For the composed function `normalize|summarize`, you should see the input and output bindings of the composed topology—do not expect separate bindings for each individual component function.

For curried compositions, verify all input bindings matching the parameter stages. When the final function is a `Consumer`, expect no output binding. When the final function returns `KStream[]`, verify the output binding count equals the returned stream count.

### Test Matrix

| Scenario | Setup | Expected Verification |
|---|---|---|
| Function + Function | `normalize|summarize` | Single composed topology, one input and one output. |
| Function + Consumer | `summarize|persist` | One input, no output binding. |
| BiFunction first | `joinOrders|toView` | Two input bindings in parameter order and one output. |
| Curried function | Three inputs in the first function | Three input bindings numbered 0, 1, 2. |
| Intermediate KTable | `toTable|toStream` | Next function accepts `KTable`. |
| Mismatched link types | Output is `KStream` but next expects `KTable` | Type compatibility error caught when building composition. |
| Consumer first | `consume|transform` | Definition is unsupported. |
| BiConsumer in chain | `joinAndConsume|transform` | Composition is unsupported. |
| Second BiFunction | `joinA|joinB` | Composition is unsupported. |
| Mid-chain branching | Function returns `KStream[]` then another function | Unsupported. |
| Terminal branching | Final function returns `KStream[]` | Output binding count matches stream count. |
| Aliased bindings | Rename `normalizeenrich-in-0` to `orders-input` | Destination and extended properties use the new alias. |
| Multiple processors | `normalize|summarize;audit` | One composed topology and one independent audit topology. |
| Application ID | Two processors configured with separate IDs | No unintended shared application ID. |

## 18. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Function in definition not found | Name in `spring.cloud.function.definition` does not match bean name. | Check the `@Bean` method name or component name. |
| Functions run as separate topologies instead of composing | Used `;` instead of `|`. | Use `|` for composition; use `;` only to activate independent processors. |
| Binding `foo-in-0` not found | Composed functions generate a concatenated name from bean names. | Use the composed function's binding name, e.g., `foobar-in-0`. |
| Destination not applied | Configured under a component function name or old alias. | Place properties under the actual post-composition/alias binding name. |
| Two inputs are swapped | Destinations assigned out of `BiFunction`/curried parameter order. | Match Java signature order with `in-0`, `in-1`, ... suffixes. |
| Composition type error | Preceding output does not match next input. | Align generic types or convert `KStream`/`KTable` explicitly. |
| `BiFunction` fails to compose | `BiFunction` is not first or another `BiFunction` follows. | Put one `BiFunction` at the start, followed only by `Function`/`Consumer`. |
| `Consumer` creates no output binding | Composition ends with a `Consumer`. | Expected behavior; `Consumer` returns no `KStream`. |
| Cannot chain after branching | Intermediate function returns `KStream[]`. | Make branching the final step or redesign the topology. |
| Extended Serde not applied | Binding was aliased but property still uses default name. | Use the alias for Kafka Streams binding properties. |
| Multiple processors share an application ID | Per-processor IDs were not configured. | Configure `functions.<function-name>.applicationId` per function. |
| Expected independent processor to receive another's output | Used `;` thinking it links pipelines. | Use topics as boundaries and configure output/input destinations accordingly. |

When investigating issues, check in order: bean names, function definition, function types, input/output types at each link, generated binding names, aliases, destinations, and application IDs. This separates composition issues from topic provisioning or Kafka Streams runtime errors.

## 19. Pre-Deployment Checklist

- [ ] Names in `function.definition` match bean names exactly.
- [ ] `|` is used for composition and `;` for independent processors.
- [ ] The first and subsequent functions use types supported by the Kafka Streams binder.
- [ ] If `BiFunction` is used, it appears first in the chain.
- [ ] If `Consumer` is used, it is the final component.
- [ ] `BiConsumer` is not composed and chains do not start with `Consumer`.
- [ ] Each step's output type matches the next step's input type.
- [ ] Functions returning an intermediate `KTable` are followed by a function accepting `KTable`.
- [ ] Branching `KStream[]` appears only as the final step.
- [ ] Binding names are derived from the composed function name and input/output indices.
- [ ] Destinations are configured under the actual active binding names.
- [ ] If aliases are used, all binding-level and extended properties reference the aliases.
- [ ] Application IDs are kept distinct from function names and binding names.
- [ ] Independent processors in the same application have appropriate application IDs.
- [ ] Integration tests confirm the actual topology, bindings, and destinations.

The Kafka Streams binder supports constrained composition for linear topologies: `Function` can chain into `Function` and end with `Consumer`; `BiFunction` must come first; curried functions enable multiple inputs. The `|` operator composes functions into a single processor, while `;` activates multiple independent processors. The binder constructs binding names from the concatenated function names—for instance, `foo|bar` yields `foobar-in-0` and `foobar-out-0`; if renamed via aliases, all binding configurations must use the new aliases. Understanding data types, composition limits, and binding naming ensures topologies wire cleanly and Kafka Streams properties attach to the intended inputs and outputs.

## References

- [Spring Cloud Stream 5.0.4 — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream 5.0.4 — Ancillaries to the Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/ancillaries-to-the-programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
