# Transforming, Filtering, and Enriching Data in a Processing Chain

A message arriving in an application is often not yet in a shape suitable for every consumer to use immediately. The data might carry field names from a partner system, contain whitespace, use internal status codes, or lack reference information. A well-structured processing chain normalizes the data, drops or quarantines ineligible records, and enriches the record with required information before emitting the output event.

Spring Cloud Stream integrates Spring Cloud Function's functional model to compose processing steps by bean name. Each Function owns a clear responsibility; the output of the preceding step becomes the input of the next step. For continuous data streams, you can use a reactive function accepting and returning `Flux<T>` to transform, filter, and call enrichment services while preserving backpressure.

In the imperative model, `Function<T, R>` is invoked per event. With a reactive function `Function<Flux<T>, Flux<R>>`, the framework passes a reference to the data stream into the function to assemble the pipeline; Reactor operators then process each element as the stream is consumed. Therefore, do not write a reactive function as if the framework will invoke the method once per record.

## 1. Viewing the processing chain as steps with data type contracts

Suppose the system receives orders from a partner. The incoming payload may use partner-specific field names and formats. The application needs to:

1. Normalize the order ID, customer ID, monetary amount, and currency.
2. Filter out records that do not meet business criteria.
3. Look up the customer's name and segment to enrich the data.
4. Emit the normalized event to a destination for downstream consumers.

~~~text
orders.raw
    |
    v
+--------------------+
| normalizeOrder     |
| Normalize data     |
+--------------------+
    |
    v
+--------------------+
| filterValidOrder   |
| Filter valid rows  |
+--------------------+
    |
    v
+--------------------+
| enrichOrder        |
| Enrich information |
+--------------------+
    |
    v
orders.enriched
~~~

Each step should have explicit input and output types:

| Step | Input | Output | Responsibility |
|---|---|---|---|
| `normalizeOrder` | `RawOrder` | `NormalizedOrder` | Normalize data representation |
| `filterValidOrder` | `NormalizedOrder` | `NormalizedOrder` | Retain only qualifying records |
| `enrichOrder` | `NormalizedOrder` | `EnrichedOrder` | Add data from a reference source |

Data type contracts help catch function composition errors at startup or compile time. If the first step returns `NormalizedOrder`, the next step must accept that exact type. Individual functions should not read from the broker or look up destinations themselves; transport belongs to bindings and binders, while functions focus on data processing.

## 2. Distinguishing transformation, filtering, and enrichment

These three operations often appear together but serve different purposes.

| Operation | Question | Example |
|---|---|---|
| Transform | How should the data representation change? | Trim order IDs, uppercase currency codes |
| Filter | Should the record proceed further? | Drop orders with non-positive totals or missing order IDs |
| Enrich | What additional data do consumers need? | Look up customer name or customer segment |

Avoid packing format conversion, rule checking, and multiple API calls into a single large function. Splitting them into steps lets you test each responsibility independently, modify one step with minimal impact on others, and pinpoint exactly where failures occur.

Filtering also requires an explicit policy. Dropping an invalid record may suit telemetry or optional data. For orders, payments, or financial records, rejected records usually need to be recorded or sent to quarantine for investigation. Never silently discard important data merely because you used a `filter` operator.

## 3. Defining data types for each stage

Avoid reusing a single DTO across all stages when the meaning of the data changes. Creating dedicated types distinguishes raw partner data from normalized data and the final event.

~~~java
import java.math.BigDecimal;

public record RawOrder(
    String externalOrderNumber,
    String customerCode,
    BigDecimal amount,
    String currencyCode
) {}

public record NormalizedOrder(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}

public record CustomerInfo(
    String customerId,
    String displayName,
    String segment
) {}

public record EnrichedOrder(
    String orderId,
    String customerId,
    String customerName,
    String customerSegment,
    BigDecimal total,
    String currency
) {}
~~~

`RawOrder` reflects the structure received from the source. `NormalizedOrder` uses uniform field names and formats inside the pipeline. `EnrichedOrder` contains the attributes needed by consumers, including looked-up customer details.

In real applications, these records may live in separate packages. Treat types between functions as the internal contract of the pipeline; events emitted to the broker must still be designed according to the service's public contract.

## 4. Transforming data with a Function

The normalization step should perform deterministic transformations without depending on external state. For instance, trim leading and trailing whitespace, standardize currency codes, and preserve exact monetary values using `BigDecimal`.

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class OrderPipelineFunctions {

    @Bean
    Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeOrder() {
        return rawOrders -> rawOrders.map(raw -> new NormalizedOrder(
                trimToNull(raw.externalOrderNumber()),
                trimToNull(raw.customerCode()),
                raw.amount(),
                normalizeCurrency(raw.currencyCode())
            ));
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private static String normalizeCurrency(String value) {
        if (value == null) {
            return null;
        }

        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

This Function only changes representation. It does not decide whether an order is valid. Separating validation/filtering into the next step gives business rules explicit names and makes them independently testable.

Do not arbitrarily alter data semantics during normalization. For example, if a partner sends amounts in cents, convert according to the agreed contract; you cannot assume multiplying or dividing by 100 based solely on a field name. For currencies, follow currency rules for units and decimal precision.

## 5. Filtering out non-qualifying records

In reactive streams, you can use `Flux.filter` to emit only elements satisfying a predicate. Add the following bean method inside the `OrderPipelineFunctions` class declared earlier:

~~~java
// Method placed inside OrderPipelineFunctions
@Bean
Function<Flux<NormalizedOrder>, Flux<NormalizedOrder>> filterValidOrder() {
    return orders -> orders.filter(order ->
        order.orderId() != null
            && !order.orderId().isBlank()
            && order.customerId() != null
            && !order.customerId().isBlank()
            && order.total() != null
            && order.total().signum() > 0
            && order.currency() != null
            && order.currency().matches("[A-Z]{3}")
    );
}
~~~

The predicate above illustrates minimal criteria: present order ID, customer ID, positive total, and an uppercase three-letter currency code. Actual rules must follow your system's business logic and schema.

`filter` removes non-qualifying elements from the stream. It does not automatically create a DLQ, persist error records, or raise alerts. If rejected data needs investigation, record metrics or route invalid records to a dedicated quarantine flow. Avoid logging entire payloads if they contain sensitive data.

Also distinguish structural validation from business filtering:

- Validation determines whether a payload conforms to expected structure and data types.
- Business filtering determines whether a record should continue through the pipeline.
- Technical errors such as lookup timeouts are not filter conditions; they belong to error handling.

Do not use `filter` to swallow exceptions. If a check cannot complete because a dependency failed, the pipeline must surface that error so it can be retried or recovered.

## 6. Enriching data from a reference source

Enrichment often requires calling another service or data store—for example, retrieving a customer's name and segment from a Customer Directory.

For a reactive pipeline, define an adapter returning `Mono<CustomerInfo>`:

~~~java
import reactor.core.publisher.Mono;

public interface CustomerDirectory {
    Mono<CustomerInfo> findById(String customerId);
}
~~~

The enrichment Function receives the stream of normalized orders, looks up the customer, and produces the output type:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class EnrichmentFunctions {

    @Bean
    Function<Flux<NormalizedOrder>, Flux<EnrichedOrder>> enrichOrder(
            CustomerDirectory directory) {

        return orders -> orders.concatMap(order ->
            directory.findById(order.customerId())
                .map(customer -> new EnrichedOrder(
                    order.orderId(),
                    order.customerId(),
                    customer.displayName(),
                    customer.segment(),
                    order.total(),
                    order.currency()
                ))
        );
    }
}
~~~

This example assumes `findById` returns `Mono.empty()` if the customer is not found. In that case, the corresponding element produces no output in `concatMap`. If business rules require retaining the order even when customer lookup misses, represent the unenriched state explicitly in an output type rather than silently dropping the element.

Never call `.block()` inside a reactive function to wait for an API response. `block()` occupies a processing thread and defeats the benefits of a reactive pipeline. Use a reactive client and combine results with `map`, `flatMap`, `concatMap`, or another suitable operator.

### Choosing operators by ordering and concurrency requirements

| Operator | Behavior | When to use |
|---|---|---|
| `map` | Synchronously transforms one element to one element | Pure data normalization |
| `filter` | Keeps elements matching a predicate | Simple conditional filtering |
| `concatMap` | Turns each element into a publisher, processing sequentially and preserving order | Lookups that must preserve input order |
| `flatMap` | Subscribes to inner publishers concurrently; output order may vary | Prioritizing throughput when order is not required |
| `flatMapSequential` | Allows concurrent processing while emitting results in source order | Needing concurrency while preserving output order |

`concatMap` is straightforward and preserves order, but it can cap throughput if each lookup is slow. When bounded concurrency is needed while still preserving output order, use `flatMapSequential(mapper, concurrency)`. Increase concurrency only after checking the lookup service's limits and system capacity.

## 7. Composing Functions into a pipeline

The three functions have compatible types:

- `normalizeOrder`: `Flux<RawOrder>` to `Flux<NormalizedOrder>`.
- `filterValidOrder`: `Flux<NormalizedOrder>` to `Flux<NormalizedOrder>`.
- `enrichOrder`: `Flux<NormalizedOrder>` to `Flux<EnrichedOrder>`.

Declare the composition in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|filterValidOrder|enrichOrder"

    stream:
      bindings:
        "normalizeOrder|filterValidOrder|enrichOrder-in-0":
          destination: orders.raw
          group: order-enrichment
          content-type: application/json

        "normalizeOrder|filterValidOrder|enrichOrder-out-0":
          destination: orders.enriched
          content-type: application/json
~~~

The `|` symbol instructs Spring Cloud Function to compose the beans in order. Incoming messages flow through `normalizeOrder`, normalized results flow through `filterValidOrder`, and remaining items are enriched by `enrichOrder`.

The default binding names of the composite function are derived from the composition expression:

- `normalizeOrder|filterValidOrder|enrichOrder-in-0` is the input binding.
- `normalizeOrder|filterValidOrder|enrichOrder-out-0` is the output binding.

Because the binding name contains `|`, wrap the key in double quotes so YAML preserves the exact name. If you prefer shorter and more stable binding names, you can use `spring.cloud.stream.function.bindings` to map generated binding names to custom names; in that case, use the mapped names in the `bindings` section.

Composition works properly only when each step's output type is compatible with the next step's input type. If you replace `filterValidOrder` with a function returning a different type, update the subsequent step or insert a corresponding mapper.

## 8. How does data flow through the pipeline?

Suppose the broker delivers three records:

~~~json
[
  {
    "externalOrderNumber": " ord-100 ",
    "customerCode": " cus-10 ",
    "amount": 150000,
    "currencyCode": "vnd"
  },
  {
    "externalOrderNumber": " ",
    "customerCode": "cus-11",
    "amount": 200000,
    "currencyCode": "VND"
  },
  {
    "externalOrderNumber": "ord-102",
    "customerCode": "cus-12",
    "amount": 85000,
    "currencyCode": "VND"
  }
]
~~~

After the normalize step, the data looks like:

| orderId | customerId | total | currency |
|---|---|---:|---|
| ord-100 | cus-10 | 150000 | VND |
| null | cus-11 | 200000 | VND |
| ord-102 | cus-12 | 85000 | VND |

The filter step drops the second record because orderId is invalid. The remaining two records proceed to the enrich step. If Customer Directory returns details for both customers, the output could be:

~~~json
{
  "orderId": "ord-100",
  "customerId": "cus-10",
  "customerName": "Nguyen An",
  "customerSegment": "STANDARD",
  "total": 150000,
  "currency": "VND"
}
~~~

~~~json
{
  "orderId": "ord-102",
  "customerId": "cus-12",
  "customerName": "Tran Binh",
  "customerSegment": "PREMIUM",
  "total": 85000,
  "currency": "VND"
}
~~~

If Customer Directory cannot find a customer, the behavior depends on the chosen policy: drop the item, emit an event indicating missing enrichment, or route to a handling flow. Do not let this behavior depend accidentally on whether the adapter returns `null`, `Mono.empty()`, or an exception.

## 9. Error handling in each step

Errors can occur at any step:

| Step | Example | Handling approach |
|---|---|---|
| Normalize | Malformed payload structure, unconvertible types | Validation and quarantine |
| Filter | Business criteria not met | Intentional discard or emit rejected record |
| Enrich | API timeout, rate limit, customer not found | Distinguish transient failures from not-found |
| Publish | Broker rejection or connection loss | Retry per binder, preserve replay capability |

In a reactive pipeline, an exception thrown inside an operator typically becomes an error signal on the publisher. If unhandled, the error signal propagates to the framework and binding error handling. You can use `onErrorResume` when a defined fallback exists, but never convert every error to `Mono.empty()` because doing so disguises technical failures as missing data.

Example distinguishing not-found from service errors:

~~~java
import reactor.core.publisher.Mono;

return directory.findById(order.customerId())
    .map(customer -> new EnrichedOrder(
        order.orderId(),
        order.customerId(),
        customer.displayName(),
        customer.segment(),
        order.total(),
        order.currency()
    ))
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(order.customerId())
    ));
~~~

Here, `Mono.empty()` is converted into an explicitly named business exception. The application can catch `CustomerNotFoundException` specifically to quarantine or emit a rejected event, while timeouts still follow transient-error retry policies.

Retries need bounds, backoff, and exception classification. In a reactive pipeline, retrying an inner publisher can avoid re-running earlier elements; retrying the entire Flux may cause some elements to be reprocessed. Place retries at the right boundary and ensure steps with side effects are idempotent.

## 10. Ensuring ordering, backpressure, and resource limits

A pipeline can receive messages faster than customer lookups or broker writes can complete. Reactive Streams uses backpressure to signal demand between publishers and subscribers, but backpressure only works when participating components do not introduce unbounded queues or block threads.

Key principles:

- Keep pure transformations inside `map`; do not call blocking APIs inside it.
- Choose `concatMap` when ordering must be preserved and sequential execution is acceptable.
- Use bounded concurrency when lookups are independent and the downstream dependency permits it.
- Bound timeouts and concurrent requests to external APIs.
- Monitor queue depth, lag, processing latency, and error counts per step.
- Do not increase concurrency just to reduce lag if downstream is already overloaded.
- Ensure consumers are idempotent when retries or redeliveries can replay data.

Ordering within a reactive pipeline generally corresponds to processing order within that subscription. When a broker has multiple partitions or multiple instances, there is no global order across all messages. If events for the same order must preserve ordering, the producer and binder must use an appropriate key/partition, and the pipeline must not reorder those events.

## 11. Preserving metadata when creating a new payload

When a Function receives `Message<T>` and builds a new payload, decide which headers must be preserved. If it only receives payload `T`, the function has no direct access to message metadata.

Example with a synchronous function:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public interface CustomerDirectorySync {
    CustomerInfo findRequired(String customerId);
}

@Configuration
public class SyncEnrichmentFunctions {

    @Bean
    Function<Message<NormalizedOrder>, Message<EnrichedOrder>> enrichWithHeaders(
            CustomerDirectorySync directory) {

        return input -> {
            NormalizedOrder order = input.getPayload();
            CustomerInfo customer = directory.findRequired(order.customerId());

            EnrichedOrder result = new EnrichedOrder(
                order.orderId(),
                order.customerId(),
                customer.displayName(),
                customer.segment(),
                order.total(),
                order.currency()
            );

            return MessageBuilder.withPayload(result)
                .copyHeaders(input.getHeaders())
                .setHeader("eventType", "OrderEnriched")
                .build();
        };
    }
}
~~~

Place the `CustomerDirectorySync` interface and the `SyncEnrichmentFunctions` class in two separate Java files because both are top-level `public` types. This synchronous example illustrates header preservation; in the reactive pipeline above, prefer an adapter returning `Mono<CustomerInfo>` so processing threads are not blocked.

This is a separate imperative example, not the reactive `Flux` function from the earlier pipeline. `copyHeaders` preserves incoming metadata; you can then overwrite headers that take on new meaning. Only copy headers permitted to cross service boundaries, avoiding leaking credentials or internal metadata to other consumers.

If the output event is a new business event, generate a new event ID, preserve the workflow correlation ID, and set the causation ID to the message that directly triggered the event. Do not use Spring's internal message ID as a business event ID.

## 12. Testing individual steps and the full composition

Splitting functions makes it easy to test each step with unit tests. For the example pipeline, key test cases include:

| Test case | Expected verification |
|---|---|
| Normalize ID with whitespace | Output ID is trimmed |
| Normalize lowercase currency | Output currency is uppercase per Locale.ROOT |
| Filter missing order ID | Record does not proceed |
| Filter zero or negative total | Record is dropped per policy |
| Enrich customer found | Output includes name and segment |
| Enrich customer not found | Handled per missing-customer policy |
| Enrich timeout | Error is classified, not turned into empty |
| End-to-end composition | Output follows step order and binding setup |

Example unit test for the normalize and filter functions:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

class OrderPipelineFunctionsTest {

    private final OrderPipelineFunctions functions =
        new OrderPipelineFunctions();

    @Test
    void normalizesCurrencyAndIdentifiers() {
        RawOrder raw = new RawOrder(
            " ord-100 ",
            " cus-10 ",
            new BigDecimal("150000"),
            "vnd"
        );

        NormalizedOrder result =
            functions.normalizeOrder().apply(Flux.just(raw)).blockFirst();

        assertEquals("ord-100", result.orderId());
        assertEquals("cus-10", result.customerId());
        assertEquals("VND", result.currency());
    }

    @Test
    void filtersOrdersWithoutAnIdentifier() {
        NormalizedOrder valid = new NormalizedOrder(
            "ord-100", "cus-10", new BigDecimal("100"), "VND"
        );
        NormalizedOrder invalid = new NormalizedOrder(
            null, "cus-11", new BigDecimal("200"), "VND"
        );

        List<NormalizedOrder> result = functions.filterValidOrder()
            .apply(Flux.just(valid, invalid))
            .collectList()
            .block();

        assertEquals(List.of(valid), result);
    }
}
~~~

The test example uses `.block()` in tests to await results; do not use this in production functions. For `enrichOrder`, use a fake CustomerDirectory returning `Mono.just(...)`, `Mono.empty()`, or `Mono.error(...)` to test the three cases: found, not found, and technical failure.

Spring Cloud Stream's Test Binder verifies input bindings, output bindings, and payloads through composition without needing a real broker. Integration tests with Kafka, RabbitMQ, or Pulsar are still needed to verify serialization, partitioning, header mapping, retries, redelivery, and real broker behavior.

## 13. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Function does too much | Hard to test and modify | Separate normalize, filter, and enrich |
| Incompatible output/input types | Composition fails to build a valid pipeline | Define DTOs for each stage |
| Calling blocking APIs inside Flux | Ties up threads, degrades throughput | Use a reactive client or isolate blocking work |
| Filter drops important data without recording | Loss of auditability | Emit metrics, quarantine, or rejected events |
| Using empty to mask timeout errors | Pipeline can silently lose data | Preserve error signals and classify exceptions |
| flatMap with unbounded concurrency | Overloads dependent services | Set explicit concurrency and timeouts |
| Failing to preserve order when business requires it | Downstream state can become inconsistent | Use concatMap or flatMapSequential appropriately |
| Retrying whole pipeline with side effects | Already-executed steps may repeat | Place retries at the right boundary and design idempotently |

## 14. Practice sequence and completion criteria

Implement the exercise with the order stream:

1. Create `RawOrder`, `NormalizedOrder`, and `EnrichedOrder`.
2. Write `normalizeOrder` to standardize order ID, customer ID, and currency.
3. Write `filterValidOrder` to drop records failing criteria.
4. Write `enrichOrder` to look up Customer Directory with a reactive client.
5. Compose the three functions via `spring.cloud.function.definition`.
6. Map the composite bindings to `orders.raw` and `orders.enriched`.
7. Send valid data, invalid data, and data with a nonexistent customer.
8. Observe outputs, metrics, and error handling.
9. Test different concurrency levels and confirm output ordering.
10. Write unit tests, Test Binder tests, and integration tests with a broker.

You have completed this lesson when you can explain the data types at each step, how to configure composition binding names, how to filter records, how to enrich using external services, and how to handle errors without confusing technical failures with empty data.

## 15. Official References

- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — Supplier, Function, Consumer, and reactive function models.
- [Spring Cloud Function — Function composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-composition) — composing multiple functions in sequence.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — default binding names and custom binding mapping.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — integrating functions with bindings and binders.
- [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html) — multi-element stream processing.
- [Project Reactor — Error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — error signals and recovery strategies.
- [Reactive Streams](https://www.reactive-streams.org/) — backpressure and asynchronous stream processing specification.
