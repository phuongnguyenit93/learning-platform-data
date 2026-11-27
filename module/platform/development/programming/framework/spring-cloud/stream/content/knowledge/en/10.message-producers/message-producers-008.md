# Handling Empty Sources and Errors During Data Retrieval

In Spring Cloud Stream, a producer can be invoked periodically to fetch data from an API, database, filesystem, or external service. Not every invocation has new data. The source can also become temporarily unreachable, return invalid data, or suffer from configuration errors.

A solid `Supplier` design must clearly distinguish three cases: no new data, valid data available, and unable to fetch data due to an error. Having no data is usually a normal outcome of a poll cycle; source errors must be observed, classified, and handled under a retry or recovery policy. If you conflate these two cases, the application can silently swallow incidents or emit business-meaningless events.

## 1. Understanding the Lifecycle of a Supplier Source

Spring Cloud Stream supports the `Supplier`, `Function`, and `Consumer` functional model. A `Supplier` is a source with no input binding; the framework invokes the `Supplier` via a poller and forwards its return value to the output binding.

~~~text
Poller
  |
  | calls Supplier.get()
  v
Supplier reads data source
  |
  +---- No new data ------------> Emit no message
  |
  +---- Valid data -------------> Build payload/message
  |                                  |
  |                                  v
  |                              Output binding
  |                                  |
  |                                  v
  |                               Binder
  |                                  |
  |                                  v
  |                               Broker
  |
  +---- Source error -----------> Error handling / retry / alert
~~~

For example, a `Supplier` may check a partner API every few seconds for new order statuses. Sometimes the API returns an order, sometimes there are no changes, and sometimes the API times out. These three outcomes must be handled differently.

A synchronous `Supplier` normally returns one value per call. When there is no message to emit, the `Supplier` can return `null`; the poller will not produce an output message for that call. If the application's internal source returns `Optional<T>`, you can use `Optional` to represent the lookup result and convert empty to `null` at the `Supplier` boundary.

Do not emit an empty object merely as a placeholder for no data. An empty payload is still a message and can mislead consumers into thinking a business event occurred.

## 2. Distinguishing No Data from an Empty-Result Event

Having no new data and emitting an event reporting an empty result carry different meanings.

| Scenario | Meaning | Action |
|---|---|---|
| No new records in this poll | Source currently has nothing to emit | Do not emit a message |
| Business query completed with 0 results | An operation finished and its outcome is empty | Emit an explicit event if consumers need to know the outcome |
| Source timeout or lost connection | Cannot tell whether the source has data | Report error, retry, or open circuit |
| Source returned malformed schema | Data exists but cannot be safely interpreted | Quarantine record, log error, and alert |
| Source returned an already-emitted record | Data may be redelivered | Use event IDs and idempotency to deduplicate |

For example, a `Supplier` checks for orders needing synchronization. If there are no new orders, it does not need to emit an `OrderCreated` event with a blank `orderId`. If a search report finishes and finds zero orders, the system can emit `SearchCompleted` with `resultCount` equal to `0`, because that is a meaningful business outcome.

Do not interchange `null`, empty lists, empty strings, and exceptions arbitrarily. Define what each case means right at the source-reading adapter.

## 3. Writing a Supplier When the Source Has No Data

Suppose a client returns `Optional<OrderSnapshot>` when checking the source:

Here are three separate Java files placed side by side to illustrate the contract between the client and data types:

~~~java
import java.util.Optional;

public interface OrderSourceClient {
    Optional<OrderSnapshot> fetchNext();
}

public record OrderSnapshot(
    String orderId,
    String customerId,
    long total
) {}

public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {}
~~~

The `Supplier` turns present results into events and emits nothing for empty results:

~~~java
import java.util.Optional;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderSourceConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderSourceClient client) {
        return () -> client.fetchNext()
            .map(snapshot -> new OrderCreated(
                snapshot.orderId(),
                snapshot.customerId(),
                snapshot.total()
            ))
            .orElse(null);
    }
}
~~~

If the client has no data, an empty `Optional` becomes `null`. The poller emits no message for that invocation. When data exists, the `Supplier` creates an `OrderCreated` payload and the default output binding is named `orderSource-out-0`.

`Optional` is the client's internal return type in this example. Do not assume `Supplier<Optional<OrderCreated>>` will automatically skip `Optional.empty()`; with that signature, `Optional` could become the message payload depending on conversion settings. Explicitly translate an empty result into non-emission at the `Supplier`.

Do not use fake defaults like `orderId = "UNKNOWN"`, `total = 0`, or an empty event to mask an empty source. If `0` is valid business data, it must be distinguishable from the absence of a record.

## 4. Configuring the Poller and Output Binding

A `Supplier` is triggered by a poller. Example configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource

    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
          content-type: application/json

  integration:
    poller:
      fixed-delay: 2000
      initial-delay: 1000
~~~

In this example:

- `orderSource` is the activated `Supplier` bean name.
- `orderSource-out-0` is the output binding created by the framework from the bean name.
- `orders.created` is the destination on the broker.
- `content-type` declares the payload content type.
- `fixed-delay` sets the wait interval between polls using Spring Integration configuration.
- `initial-delay` sets the wait time before the first poll.

Tune the polling cadence to API limits, data update rate, and broker processing capacity. Polling too fast when the source is usually empty creates unnecessary load. Polling too slowly increases latency in detecting new data.

Set source-call timeouts smaller than or aligned with the polling cadence and maximum processing time. If one call hangs for too long, the poller can be tied up and new data is detected late. Do not use infinite loops or `Thread.sleep` inside the `Supplier` to manage cadence yourself; use the poller or an appropriate scheduling mechanism.

If the application runs multiple instances, every instance may call the source concurrently. For sources that do not support parallel reads, use work distribution, leases, locks, or partitioning to avoid multiple instances grabbing the same record unintentionally.

## 5. Classifying Errors During Data Retrieval

Not every source error shares the same recovery path. Before adding retries, classify errors:

| Error Category | Example | Handling Strategy |
|---|---|---|
| Transient | Timeout, connection reset, overloaded broker/API | Bounded retries with backoff |
| Rate limited | HTTP 429 or throttling notice | Honor `Retry-After` if present, reduce cadence |
| Service unavailable | HTTP 5xx, database failover | Bounded retries, circuit breaker, and alert |
| Configuration/authentication | Bad credentials, missing permissions, wrong URL | Stop tight retries, raise operational alert |
| Invalid data | Missing required field, wrong type, incompatible schema | Quarantine data, log error, and investigate |
| Programming error | Unexpected null, mapping bug, violated invariant | Let error surface, fix code, and test |

A timeout does not mean the source has no data. If you catch the exception and return `null`, the application treats the outage as an empty poll and may never notice that the source has stopped working.

Do not catch every `Exception` and only log at `DEBUG` level. Classify errors intentionally. Transient errors can be retried; configuration or invalid-data errors must be alerted on and routed to a separate workflow.

## 6. Letting Source Errors Flow into Error Handling

An example `Supplier` that allows client errors to propagate outward:

~~~java
// ExternalSourceConfiguration.java
import java.util.Optional;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExternalSourceConfiguration {

    public interface ExternalOrderClient {
        Optional<ExternalOrderResponse> fetchNext();
    }

    @Bean
    Supplier<ExternalOrder> externalOrderSource(
            ExternalOrderClient client) {

        return () -> client.fetchNext()
            .map(this::toEvent)
            .orElse(null);
    }

    private ExternalOrder toEvent(ExternalOrderResponse response) {
        if (response.orderId() == null || response.orderId().isBlank()) {
            throw new IllegalArgumentException(
                "External order is missing orderId"
            );
        }

        return new ExternalOrder(
            response.orderId(),
            response.total()
        );
    }

    public record ExternalOrderResponse(String orderId, long total) {}
    public record ExternalOrder(String orderId, long total) {}
}
~~~

`ExternalOrderClient` must be supplied as a separate bean—for example, an adapter calling a REST API or querying a database. The `Supplier` configuration is only responsible for turning the adapter's result into a payload and letting errors propagate to error handling.

When the client throws an exception, the `Supplier` must not turn it into an empty result. The exception enters the poller/Spring Integration error-handling mechanism. How retries, error routing, and notifications behave depends on the poller type, error channel, error handler, and application configuration.

In real applications, define semantically clear exceptions such as `TransientSourceException` and `PermanentSourceException`. Transient exceptions can be retried; permanent errors should enter alerting or quarantine flows. Avoid retrying unrecoverable data errors infinitely.

If you catch an exception to add context, preserve the original cause:

~~~java
try {
    return client.fetchNext()
        .map(this::toEvent)
        .orElse(null);
} catch (SourceTimeoutException ex) {
    throw new TransientSourceException(
        "Could not fetch the next order from partner API",
        ex
    );
}
~~~

Only catch exception types you know how to handle. If you cannot recover inside the `Supplier`, let the exception propagate to error handling so the system can observe it and decide the next step.

## 7. Retry, Backoff, and Circuit Breakers

Retries suit errors likely to self-recover. Policies should include bounded attempts, increasing wait intervals, and jitter so multiple instances do not hammer the source in lockstep.

Illustrative retry schedule:

| Attempt | Relative Time |
|---|---|
| Initial attempt | 0 seconds |
| Retry 1 | After 1 second |
| Retry 2 | After 2 seconds |
| Retry 3 | After 4 seconds |
| After limit | Record error and transition to recovery state |

This is an example of exponential backoff; real values must reflect timeouts, service limits, and data urgency.

A circuit breaker pauses calls to the source when the failure rate crosses a threshold. After a cooldown period, it lets a few probe requests through to check whether the service has recovered. This prevents fleets of instances from continuously overloading a struggling source.

Do not retry every error. Bad credentials, missing permissions, invalid URLs, or undecodable payloads are rarely fixed by calling again immediately. For HTTP 429, respect the wait time provided by the partner if available. For timeouts, consider that the partner may already have processed the request even if the response was lost; read operations should be safe to repeat, while write operations need an idempotency key.

Do not place unbounded retries inside the `Supplier` without a time limit. The poller needs to keep running, and the system needs a way to alert when a source stops supplying data.

## 8. No Data Is Not an Error and Should Not Spam Warning Logs

A polled source can be empty most of the time. That is normal if the source only emits when new data arrives.

Track separate metrics:

- Total poll count.
- Empty poll count.
- Mean and high-percentile duration of a source read.
- Successful read count.
- Error counts by category: timeout, throttling, authentication, invalid data.
- Retry counts and open circuit breaker state.
- Age of the oldest unprocessed record.
- Successful publishes and publish failure counts.

Do not log `WARN` every time the source is empty. Use metrics or `DEBUG` logs for normal empty states. Trigger alerts when there has been no data for abnormally long compared to the source's normal rhythm, when backlog grows, when the source errors continuously, or when a circuit breaker stays open too long.

If a source normally produces data on a schedule, track the timestamp of the latest record and the lag from `occurredAt` to publish time. That helps distinguish a genuinely quiet source from a stalled pipeline.

## 9. Protecting Data When Reading Sources and Emitting Messages

Source data may contain sensitive information or large payloads. Before emitting:

- Validate required fields and bound payload size.
- Strip internal fields or secrets that do not belong in the event contract.
- Normalize timestamps, time zones, monetary amounts, and enums.
- Never log full responses or tokens.
- Bound timeouts and concurrent calls.
- Manage credentials via a secret manager or environment variables.
- Validate schemas before sending to avoid emitting unconsumable messages.

If source data is invalid, retain enough diagnostic details—such as source, record key, receipt time, and validation failure reason. You do not necessarily need to store the full invalid payload if it contains sensitive data. Store a masked copy or a reference ID pointing to an access-controlled quarantine store.

## 10. Distinguishing Source Read Errors from Broker Send Errors

Emitting an event has two independent legs:

1. Reading data from the source.
2. Sending the message through the output binding to the broker.

Errors in the first leg happen before a valid payload exists. Errors in the second leg happen after the application has the data and is transporting the message. These two error classes need separate metrics, logs, and recovery workflows.

| Leg | Error Example | How to Investigate |
|---|---|---|
| Source read | API timeout, database unavailable | Check connectivity, timeouts, credentials, rate limits |
| Mapping/validation | Schema mismatch, missing field | Inspect input data and mapper |
| Broker send | Broker unreachable, authorization failed | Check binder, destination, permissions, and broker health |
| Send confirmation | Connection lost while awaiting result | Determine whether the message may have been received; use stable IDs to deduplicate |

Do not use a consumer DLQ to handle every source read error. Before data has been retrieved, there is no valid event to send to a dead-letter destination. You can record source errors in an operational store or a dedicated error topic if a diagnostic payload contract is defined; do not emit a fake business event just to push an error into a DLQ.

When a send API returns success, understand the exact confirmation level the binder provides. A message being accepted into an application channel does not always mean the broker has durably persisted it. If stronger guarantees are needed, configure binder-appropriate producer acknowledgments/confirmations and monitor publish results.

## 11. Preventing Data Loss with Stateful Sources

If a `Supplier` reads a record and marks it processed before the broker receives the message, a failure during publish can lose the event. If publish succeeds yet the application fails to record completion, the next poll can re-emit the event. This is the boundary between the data source and the broker.

For critical data, use a claim/lease model or a transactional outbox:

~~~text
Data Source / Outbox
       |
       v
Claim a record with a lease
       |
       v
Build event with stable eventId
       |
       v
Publish via binder
       |
       +---- Confirmed per broker policy
       |              |
       |              v
       |         Mark as sent
       |
       +---- Error or unknown outcome
                      |
                      v
              Hold/release lease
              and retry under control
~~~

An outbox writes business changes and events to emit in the same database transaction. A relay reads unsent records, publishes them, and marks them sent using an appropriate confirmation mechanism. If the relay stops after publishing but before updating status, the event may be re-emitted. Therefore, the event ID must be stable and consumers must be idempotent.

A simple `Supplier` poller does not create an atomic transaction between a data source and a broker. When you need to advance a cursor, mark source records after publishing, or coordinate multiple steps, use a stateful relay, an outbox, or a dedicated connector. Never mark a source record complete simply because the `Supplier` returned a payload.

For external APIs with cursors or pagination tokens, advance the cursor only after the corresponding data has been durably stored or published under a recoverable workflow. Otherwise, a failure between fetching a page and saving the cursor can drop data.

## 12. Handling Invalid Data and Quarantining Records

A source may return a record missing required fields or violating the schema. Do not ignore it silently, nor retry an unfixably invalid record forever.

A handling workflow can include:

1. Identify the record key, source, and retrieval timestamp.
2. Validate the payload before creating an event.
3. If valid, map it to the event contract.
4. If invalid, record the reason and move the record into a controlled quarantine store.
5. Raise an alert or create a ticket based on severity.
6. After fixing the data or mapper, allow reprocessing with a stable event ID if an event had already been generated.

Quarantine stores invalid input data for investigation. It differs from a DLQ: a DLQ typically holds messages already delivered by the broker to a consumer that the consumer failed to process; quarantine can hold raw source data that never became a valid message.

## 13. Testing Empty Sources, Errors, and Recovery

Testing a `Supplier` must verify both non-emission outcomes and error paths:

| Scenario | Expected Result |
|---|---|
| Client returns `Optional.empty()` | `Supplier` returns `null`, no output message |
| Client returns a valid record | `Supplier` builds the expected event |
| Client temporarily times out | Error is classified and enters retry/error handling |
| Client returns authentication error | No tight retries; operational alert raised |
| Payload missing required field | Validation fails and data is quarantined |
| Broker unavailable | Publish failure is recorded; source data can recover |
| Relay restarts after publish | May re-emit the same event ID; consumer deduplicates |
| Multiple instances polling concurrently | Do not claim the same record when exclusive access is required |

Unit test example for the `Supplier`:

~~~java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class OrderSourceConfigurationTest {

    @Test
    void emitsNothingWhenSourceIsEmpty() {
        OrderSourceClient client = () -> Optional.empty();
        OrderSourceConfiguration configuration =
            new OrderSourceConfiguration();

        Supplier<OrderCreated> supplier = configuration.orderSource(client);

        assertNull(supplier.get());
    }

    @Test
    void mapsAvailableRecordToEvent() {
        OrderSourceClient client = () -> Optional.of(
            new OrderSnapshot("ord-100", "cus-200", 50000)
        );
        OrderSourceConfiguration configuration =
            new OrderSourceConfiguration();

        Supplier<OrderCreated> supplier = configuration.orderSource(client);

        OrderCreated event = supplier.get();
        assertEquals("ord-100", event.orderId());
        assertEquals(50000, event.total());
    }
}
~~~

Add exception tests to confirm errors are not turned into `null`. The Test Binder can verify that an empty `Supplier` emits no messages and a populated `Supplier` emits the expected payload. Integration tests with a real broker must verify publish failures, retries, producer confirmations, and replay after restarts.

The Test Binder does not fully simulate partner API timeouts, rate limits, source leases, or broker acknowledgments. Those behaviors must be tested using fake servers, test databases, or real brokers in integration tests.

## 14. Practice Sequence and Completion Criteria

Practice with an external order source:

1. Create a client with a `fetchNext` method returning `Optional<OrderSnapshot>`.
2. Write a `Supplier` converting valid records into `OrderCreated`.
3. When the source is empty, return `null` and verify no output message is produced.
4. Configure the poller and output binding in `application.yml`.
5. Simulate timeouts, throttling, authentication errors, and invalid payloads.
6. Classify transient vs. permanent errors; add bounded retries and alerts.
7. Track empty poll counts, read duration, errors, and backlog.
8. Simulate broker disconnection after the source already returned data.
9. Design a claim/lease or outbox approach so no data is lost when publishing fails.
10. Start multiple instances and verify no unintended duplicate reads occur.

You have completed the exercise when you can explain why having no data is not an error, how a `Supplier` avoids emitting messages on an empty source, how to classify source read errors, how to apply retry/backoff, and how to preserve data across the publish boundary. Both normal and error states should be observable in logs, metrics, and integration tests.

## 15. Official References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — function, binding, and binder architecture.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — `Supplier`, `Function`, and `Consumer`.
- [Spring Cloud Stream — Configuration options](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — binding and producer configuration.
- [Spring Integration — Endpoint and Poller Configuration](https://docs.spring.io/spring-integration/reference/endpoint.html) — pollers, fixed delay, and polling endpoints.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html) — error channels and exception handling.
- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — error handling in stream applications.
- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — emitting messages from non-function components.
