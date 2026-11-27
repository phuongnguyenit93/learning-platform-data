# Designing observable flows

In the **Flow Design** chapter of the **SPRING_INTEGRATION_CORE** module, a flow needs to expose both the message path and the outcome of each execution. When a customer asks "where is my order?", the operations team must be able to trace from the entry point, through transformers, filters, routers, and endpoints, to the final outcome or where it is waiting.

This lesson uses Message, MessageChannel, and Java DSL as the foundation; gateways, aggregators, error handling, and tests are placed within the same observability problem. The goal is to design diagnostic information right when designing the flow, so runtime system behavior can be explained.

## 1. Outcomes to achieve

After this lesson, you will be able to:

- Assign stable channel and endpoint names to link diagrams, logs, metrics, and traces.
- Maintain business identifiers across transformations, branching, and message reprocessing.
- Explicitly define the points of intake, completion, rejection, and failure.
- Choose appropriate measurement points for synchronous and asynchronous processing.
- Design resource-bounded observation branches.
- Verify that enabling observability preserves business outcomes accurately.

Consider an order intake flow: validate data, normalize the order ID, then call the processing step. Invalid data goes to the rejection branch; technical errors need their own diagnostic path. With only a single line saying "order received", you cannot tell whether the order completed, was rejected, or is still sitting in a queue.

## 2. Start from what needs to be explained

Before adding tooling, identify the operational questions.

| Question | Evidence to collect |
| --- | --- |
| How many requests does the system receive? | Intake counts at a defined boundary |
| How many requests reach a final outcome? | Business outcomes at terminal endpoints |
| Where is a specific order right now? | Business key, correlation ID, and processing checkpoints |
| Where is the flow slow? | Wait times, processing durations, and end-to-end duration |
| At which branch did a request disappear? | Traces of routing, rejection, timeout, or recovery decisions |
| Is the observation branch overloading? | Buffer capacity, dropped event count, and telemetry export errors |

Four kinds of telemetry complement one another:

| Telemetry type | Role in the order flow | Limitations to understand |
| --- | --- | --- |
| Log | Describes an event with specific lookup keys | Hard to aggregate when written only as free-form text |
| Metric | Detects shifts in traffic, errors, latency, and backlog | Unsuitable for storing individual order IDs |
| Trace | Links steps of an execution across boundaries | Depends on context propagation and sampling policy |
| Topology | Shows existing components and connections | Does not prove a specific order traversed every link |

A dashboard showing rising errors detects an incident. A trace or correlation ID narrows down an execution. Logs at the relevant endpoint explain the business decision. A good design lets you traverse these three levels without grepping through all logs.

## 3. Draw success, rejection, and error paths together

~~~mermaid
flowchart LR
    A["Caller or gateway"] --> B["ordersInput"]
    B --> C["ordersValidate: filter"]
    C -->|valid| D["ordersNormalize: transformer"]
    C -->|invalid| R["ordersRejected"]
    R --> S["ordersRecordRejected"]
    D --> E["ordersNormalized"]
    E --> F["ordersProcess"]
    F --> G["processed"]
    F -. "synchronous exception" .-> A
    E -. "optional tap" .-> T["ordersTelemetry: bounded queue"]
    T --> U["telemetry consumer"]
~~~

This diagram corresponds to the synchronous example in Section 6. When switching the input to a queue and using a poller, errors thrown in the processing task must be observed through that task's error mechanism.

### 3.1. Name meaningfully

Use channel names that express data state: `ordersInput`, `ordersNormalized`, `ordersRejected`. Use endpoint IDs that express responsibility: `ordersValidate`, `ordersNormalize`, `ordersProcess`.

In Java DSL, set the ID via the endpoint configurer:

~~~java
.filter(Order.class, ObservableOrderFlowApplication::valid,
        endpoint -> endpoint
                .id("ordersValidate")
                .discardChannel("ordersRejected"))
~~~

Channel bean names and endpoint IDs are two different identifiers. Some supporting components or DSL-generated handlers have derived names; when building dashboards, inspect the actual names exposed by the registry and graph.

Names used on dashboards must stay stable across deployments. Renaming an endpoint can split old and new metric series apart, even though the business logic stayed the same.

### 3.2. Mark execution boundaries on the diagram

With `DirectChannel`, the handler is invoked on the sending thread. With `QueueChannel`, the send operation can finish once the message is placed in the queue; a consumer still has to pull and process it. In-memory queues also provide no durability across process shutdowns. These characteristics are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

When reviewing a diagram, mark where threads change, where durable writes occur, where external services are called, and where additional messages are created. Those points determine how measurements are interpreted and how requests are traced.

## 4. Distinguish types of identifiers

| Identifier | Meaning | Usage |
| --- | --- | --- |
| `MessageHeaders.ID` | Technical identifier of a Message | Correlate a specific message instance |
| `businessCorrelationId` | Application-defined header for a business request | Link processing milestones across steps |
| `orderId` | Order key in the business domain | Query order status |
| Integration-pattern `correlationId` | May serve grouping, e.g. splitter/aggregator | Keep the semantics of the active pattern |
| Trace ID, span ID | Execution identifiers managed by tracing infrastructure | Navigate between related spans and logs |
| `attempt` if defined by app | Processing attempt number for the same request | Distinguish retries from new requests |

Never use a Message's ID as the sole key for an entire order lifecycle. A step creating a new Message can assign a new ID; retries or resends from external systems can also create different Messages for the same business operation.

In this lesson, `businessCorrelationId` is a custom header name. It is not an automatic Spring Integration header and does not automatically become trace context. Choosing a distinct name also prevents accidentally overwriting the `correlationId` header used by a splitter or aggregator.

At the intake boundary:

1. Validate externally supplied correlation IDs against length and character rules.
2. Generate a new value if none was supplied externally.
3. Attach the value to the Message and preserve it across internal steps that need linking.
4. When crossing adapters or brokers, define header mapping explicitly.
5. For retry requests, keep the business key and record attempt number per the retry contract.

Example constructing a Message in Java, assuming `ordersInput` is an injected channel:

~~~java
var message = org.springframework.messaging.support.MessageBuilder
        .withPayload(new ObservableOrderFlowApplication.Order(
                "ord-101", "APAC", 2))
        .setHeader("businessCorrelationId", "checkout-101")
        .build();

ordersInput.send(message);
~~~

A header present only in current memory does not guarantee transmission over HTTP, Kafka, or JMS. Inspect header mappers, wire formats, and trust rules at each boundary.

## 5. Define event contracts and metric labels

### 5.1. Every event must have clear semantics

Proposed contract for the order flow:

| Event | When emitted? | Permitted conclusion |
| --- | --- | --- |
| `received` | Message enters the inbound observation point | Reached that boundary |
| `normalized` | Passed the normalization step | Normalized data is ready for the next step |
| `processed` | Illustrative processing step finished | Completed the scope defined by the example |
| `rejected` | Filter rejected per data rules | Intentionally rejected |
| `failed` | Processing step hit a technical error | This processing attempt failed |
| `retry_scheduled` | Recovery actually scheduled a retry | Another attempt will follow per policy |
| `expired` | Configured wait deadline elapsed | Waiting ceased under that contract |

Do not emit `processed` right after enqueueing if business work still runs downstream. For database writes, decide whether success means "handler returned" or "transaction committed". For external service calls, distinguish "request sent" from "confirmation received".

Example field-structured log:

~~~text
event=processed flow=orders endpoint=ordersProcess
orderId=ORD-101 correlationId=checkout-101
~~~

In a real application, a JSON encoder can store each field separately. The snippet above only shows the required fields without assuming a specific log collector.

### 5.2. Keep label cardinality bounded

A metric with tags `flow`, `outcome`, and `region` having 4, 3, and 5 values respectively can produce `4 × 3 × 5 = 60` combinations, before multiplying by instances and backend auxiliary series.

Adding `orderId` with one million values multiplies series per order. Keep order IDs in logs or controlled trace attributes, while using finite value sets for metrics.

| Field | Log / trace | Metric tag |
| --- | --- | --- |
| Fixed flow, endpoint | Appropriate | Appropriate |
| Outcome from a defined set | Appropriate | Appropriate |
| Region from a finite catalog | Appropriate | Appropriate when breakdown is needed |
| Order ID, correlation ID | Use when permitted | Avoid |
| Partner exception message text | Must filter and bound | Avoid |
| `errorCategory` like `timeout`, `validation` | Appropriate | Appropriate if finite catalog |

Never build tags from `exception.getMessage()`, full URLs, or payloads. For errors, map to controlled categories: `dependency_timeout`, `dependency_unavailable`, `unexpected`.

## 6. Java DSL example: observing a synchronous flow

The example uses Java 17 or later, Spring Integration 6.x or later, and Spring Boot managing compatible dependencies. Required dependencies:

- `spring-boot-starter-integration` for Spring Integration and Java DSL.
- `spring-boot-starter-actuator` for Boot-configured metric infrastructure.
- `spring-boot-starter-web` if accessing Actuator over HTTP.

Place these dependencies in a Boot project with a compatible parent or BOM; do not mix versions manually. This application receives messages over channels and has no REST controller yet. Processing is simulated in memory to highlight observability signals.

~~~java
package example.integration;

import java.util.Locale;
import java.util.Set;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;
import org.springframework.messaging.Message;

@SpringBootApplication
@EnableIntegration
public class ObservableOrderFlowApplication {

    private static final Logger LOG =
            LoggerFactory.getLogger("orders.flow");

    public static void main(String[] args) {
        SpringApplication.run(ObservableOrderFlowApplication.class, args);
    }

    public record Order(String orderId, String region, int quantity) {
    }

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    DirectChannel ordersNormalized() {
        return new DirectChannel();
    }

    @Bean
    DirectChannel ordersRejected() {
        return new DirectChannel();
    }

    @Bean
    OrderTelemetry orderTelemetry(MeterRegistry registry) {
        return new OrderTelemetry(registry);
    }

    @Bean
    IntegrationFlow ordersFlow(OrderTelemetry telemetry) {
        return IntegrationFlow.from("ordersInput")
                .log(LoggingHandler.Level.INFO, "orders.flow",
                        message -> summary("received", message))
                .filter(Order.class, ObservableOrderFlowApplication::valid,
                        endpoint -> endpoint
                                .id("ordersValidate")
                                .discardChannel("ordersRejected"))
                .transform(Order.class,
                        order -> new Order(
                                order.orderId().toUpperCase(Locale.ROOT),
                                order.region(),
                                order.quantity()),
                        endpoint -> endpoint.id("ordersNormalize"))
                .channel("ordersNormalized")
                .log(LoggingHandler.Level.INFO, "orders.flow",
                        message -> summary("normalized", message))
                .handle(Order.class, (order, headers) -> {
                    try {
                        telemetry.processing.record(() -> {
                            // Simulate an error to practice observability.
                            if (order.orderId().startsWith("FAIL-")) {
                                throw new IllegalStateException(
                                        "Simulated processing failure");
                            }
                            // Replace with actual processing logic in the application.
                        });
                    }
                    catch (RuntimeException failure) {
                        telemetry.failed.increment();
                        LOG.error(
                                "event=failed flow=orders endpoint=ordersProcess "
                                        + "orderId={} correlationId={} errorType={}",
                                safe(order.orderId()),
                                safe(headers.get("businessCorrelationId")),
                                failure.getClass().getSimpleName());
                        throw failure;
                    }

                    telemetry.processed.increment();
                    LOG.info(
                            "event=processed flow=orders endpoint=ordersProcess "
                                    + "orderId={} correlationId={}",
                            safe(order.orderId()),
                            safe(headers.get("businessCorrelationId")));
                    return null;
                }, endpoint -> endpoint.id("ordersProcess"))
                .get();
    }

    @Bean
    IntegrationFlow ordersRejectedFlow(OrderTelemetry telemetry) {
        return IntegrationFlow.from("ordersRejected")
                .handle(Order.class, (order, headers) -> {
                    telemetry.rejected.increment();
                    LOG.info(
                            "event=rejected flow=orders "
                                    + "endpoint=ordersRecordRejected "
                                    + "reason=invalid_order "
                                    + "orderId={} correlationId={}",
                            safe(order.orderId()),
                            safe(headers.get("businessCorrelationId")));
                    return null;
                }, endpoint -> endpoint.id("ordersRecordRejected"))
                .get();
    }

    static boolean valid(Order order) {
        return order.orderId() != null
                && order.orderId().matches("[A-Za-z0-9-]{1,40}")
                && order.region() != null
                && Set.of("APAC", "EU", "US").contains(order.region())
                && order.quantity() > 0;
    }

    static String summary(String event, Message<?> message) {
        Object orderId = message.getPayload() instanceof Order order
                ? order.orderId() : null;
        return "event=" + event
                + " flow=orders"
                + " messageId=" + message.getHeaders().getId()
                + " orderId=" + safe(orderId)
                + " correlationId="
                + safe(message.getHeaders().get("businessCorrelationId"));
    }

    static String safe(Object value) {
        if (value == null) {
            return "-";
        }
        String text = value.toString();
        return text.matches("[A-Za-z0-9._:-]{1,80}")
                ? text : "[redacted]";
    }

    static final class OrderTelemetry {
        final Counter processed;
        final Counter rejected;
        final Counter failed;
        final Timer processing;

        OrderTelemetry(MeterRegistry registry) {
            processed = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "processed");
            rejected = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "rejected");
            failed = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "failed");
            processing = Timer.builder("orders.flow.processing")
                    .tag("flow", "orders")
                    .description("Duration of the simulated processing step")
                    .register(registry);
        }
    }
}
~~~

Points to notice:

- `ordersValidate` has a discard channel, so rejected requests still reach an endpoint that records the outcome.
- The transformer returns a new `Order`. It does not mutate the payload in place.
- `ordersProcess` ends with `return null` because the example has a one-way contract.
- The timer wraps only the simulated processing block. Time spent in filtering, transforming, logging, and queue waiting sits outside that timer's scope.
- The `failed` counter only counts errors inside the wrapped processing block. Type-conversion failures or errors at other endpoints need their own observation points.
- `safe` restricts logged fields; this is an illustrative rule for IDs, not a replacement for an application-wide data policy.

Outcome counters express business terminations in the example. The timer inherently records a count of executions of the processing step; that count includes runs that threw exceptions, while requests dropped by the filter never reach this step. Micrometer documents timer counts and duration measurements in [Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

`processed` here means "the simulated processing block finished". When replacing it with real order persistence, move the recording point to the proper confirmation boundary, including commit or target-system acknowledgment requirements.

### 6.1. Practice data and expected results

Send three Messages with different correlation IDs:

| Payload | Expected path | Outcome |
| --- | --- | --- |
| `Order("ord-101", "APAC", 2)` | Validate → normalize → process | Order ID becomes `ORD-101`, `processed` increments |
| `Order("ord-102", "APAC", 0)` | Validate → rejected | `rejected` increments, process is not run |
| `Order("fail-103", "EU", 1)` | Validate → normalize → process | `failed` increments, exception propagates to caller |

Counters increment per **execution**, without unique-per-order counting guarantees yet. Resending the same order twice produces two recordings if there is no idempotency mechanism.

### 6.2. Putting a gateway in front of the flow

A gateway can hide the messaging API behind an interface. Choose a one-way or request-reply contract before measuring timing at the gateway; refer to [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

With the flow above, you can define a one-way interface in a package scanned by integration component scan:

~~~java
@org.springframework.integration.annotation.MessagingGateway(
        defaultRequestChannel = "ordersInput")
public interface OrderGateway {
    void submit(
            ObservableOrderFlowApplication.Order order,
            @org.springframework.messaging.handler.annotation.Header(
                    "businessCorrelationId") String correlationId);
}
~~~

When adding this interface, enable `@IntegrationComponentScan` on the appropriate configuration to register the gateway. With a synchronous flow, `submit` call duration covers work executed on the call stack. If switched to enqueueing, call duration may only reflect message handoff.

If an `OrderResult` must be returned, both the success and rejection branches must be designed to produce matching replies. A silently ending filter can make a request-reply caller wait until timeout.

## 7. Read metrics at the right boundary

### 7.1. Built-in technical metrics

When a `MeterRegistry` is present, Spring Integration supports meters for managed components. Useful names include:

| Meter | Meaning |
| --- | --- |
| `spring.integration.send` | Channel or handler timer |
| `spring.integration.receive` | Receive operation counter |
| `spring.integration.channel.queue.size` | Number of items in a `QueueChannel` |
| `spring.integration.channel.queue.remaining.capacity` | Remaining capacity |

For `spring.integration.send`, tags such as `type`, `name`, `result`, and `exception` select the component and technical outcome. Inspect the actual meters emitted before writing queries. Details are in [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html).

### 7.2. Technical outcomes vs. business outcomes

A handler receiving a message and dropping it per a filter rule can complete its send operation normally. Thus, "no exception thrown" is not enough to conclude "the order was accepted".

Similarly, a successful queue send only proves handoff into the queue succeeded under the current configuration. To know an order completed, observe the terminal endpoint or durable business state.

Maintain two viewpoints:

- Technical metrics to spot failing endpoints, congested channels, or slow dependencies.
- Business metrics to know counts of processed, rejected, expired, and intervention-needed outcomes.

### 7.3. Do not add step durations mechanically

In a synchronous chain, one endpoint can forward results to downstream endpoints before returning. Measured intervals can overlap.

For example, observed duration at the flow entry is 120 ms, of which the final handler took 90 ms. If an intermediate timer also includes those 90 ms, summing them double-counts.

For asynchronous flows, break down the target:

~~~text
End-to-end duration
  = intake duration
  + total wait time
  + time along the outcome-deciding path
  + retry or dependency wait time
~~~

With parallel branches, outcome-deciding time depends on the slowest awaited branch and the aggregation release condition. Summing CPU across all branches does not equal user-perceived latency.

Use a monotonic clock to measure durations within the same process. For message age across machines, define a transmittable timestamp, clock sync requirements, and tolerable clock skew.

## 8. Observation and tracing

Micrometer Observation models the observation lifecycle. Handlers registered with an `ObservationRegistry` can produce metrics or spans as configured. A standalone registry does not by itself supply a full trace-export pipeline; see [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

Since Spring Integration 6.0, you can choose which components are instrumented via annotation:

~~~java
@org.springframework.integration.config.EnableIntegrationManagement(
        observationPatterns = "orders*")
~~~

Add this annotation to an appropriate configuration class and supply `ObservationRegistry` along with needed handlers. Patterns match component names, so also cross-check DSL-generated handler names. Attribute details are in [EnableIntegrationManagement](https://docs.spring.io/spring-integration/api/org/springframework/integration/config/EnableIntegrationManagement.html).

Do not assume dashboards built for direct meters keep identical names and tags when switching to Observation. Inspect the application's registry after the change.

To make traces useful across a flow:

1. Verify an appropriate tracing bridge and exporter exist in the active stack.
2. Check that context propagates across real executors, pollers, and adapters.
3. Retain business correlation IDs for lookup even when traces are sampled out.
4. Restrict data attached to spans per system policy.
5. Verify parent-child links or retry links according to the library's semantics.

MDC is typically thread-bound. Setting a value on the intake thread does not guarantee a downstream processing thread sees it. If populating MDC manually, manage its lifecycle and clear context after processing to avoid tagging the next request with the wrong ID.

Do not fabricate a `traceId` by renaming a business correlation ID. The two identifier types have different lifecycles and roles.

## 9. Wire tap and the cost of observation branches

`wireTap` routes a copy of messages to a secondary branch. Synchronicity depends on the target channel; a tap to a `DirectChannel` can still make the caller wait for secondary branch processing. Refer to [Wire Tap](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-wiretap).

In Java DSL, `log()` uses a wire tap with a logging handler. Placement determines what gets recorded; a `log()` after a filter sees only messages passing the filter. See [Operator log()](https://docs.spring.io/spring-integration/reference/dsl/java-log.html).

### 9.1. Add a bounded-buffer tap

In the Section 6 application class, add the two beans below. Import `QueueChannel` and `Pollers` from Spring Integration.

~~~java
@Bean
org.springframework.integration.channel.QueueChannel ordersTelemetry() {
    return new org.springframework.integration.channel.QueueChannel(1000);
}

@Bean
IntegrationFlow ordersTelemetryFlow() {
    return IntegrationFlow.from("ordersTelemetry")
            .handle(Order.class, (order, headers) -> {
                LOG.info(
                        "event=observed flow=orders "
                                + "orderId={} correlationId={}",
                        safe(order.orderId()),
                        safe(headers.get("businessCorrelationId")));
                return null;
            }, endpoint -> endpoint
                    .id("ordersTelemetryLog")
                    .poller(org.springframework.integration.dsl.Pollers
                            .fixedDelay(100)
                            .maxMessagesPerPoll(100)))
            .get();
}
~~~

After `.channel("ordersNormalized")` in the main flow, add:

~~~java
.wireTap("ordersTelemetry", tap -> tap.timeout(0))
~~~

Setting `timeout(0)` sends to the target channel without waiting for free space. The API is documented in [WireTapSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/WireTapSpec.html) and [WireTap.setTimeout](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/interceptor/WireTap.html#setTimeout(long)).

A tap at this location records the message at the normalized channel before `ordersProcess` finishes. Thus `observed` does not mean `processed`. Across the queue boundary, log line order between the two threads can also differ from the order you read on the diagram.

### 9.2. Define overload policies explicitly

For diagnostic branches, dropping events when the buffer is full may be acceptable. For mandatory business audit evidence, design storage and acknowledgment matching durability requirements.

The tap example above does not define a custom counter for dropped events. If exact overflow numbers are needed, instrument the buffer handoff point, inspect `send` results or delivery failures, and test that behavior under the active version. Never infer dropped-event counts solely from consumer counters.

Decide upfront:

| Situation | Design decision |
| --- | --- |
| Telemetry queue full | Max wait time, drop event, or fail delivery? |
| Slow log backend | Bounded buffer, resource limits, and overload signal |
| Prolonged exporter outage | How much data to retain, how long to retry, where to track errors? |
| Application shutdown | How long to wait to flush and what loss is acceptable? |
| Observation branch errors | Error destination and mechanism to avoid error loops |

Do not treat wire tap as a deep copy of payloads. If payloads contain mutable objects, the secondary branch must avoid mutating shared objects. For large or sensitive data, construct a compact telemetry event with permitted fields before storing or exporting.

When using global interceptors or taps, exclude telemetry branches and telemetry error-handling branches from their scope. Observing the act of observing can create feedback loops and amplify load rapidly.

## 10. Observe errors according to the execution model

### 10.1. Synchronous flows

In the Section 6 example, errors in `ordersProcess` propagate back to the sender because the chain runs over `DirectChannel`. The framework can wrap errors in a `MessagingException`; inspect the cause chain when diagnosing.

Merely setting the `errorChannel` header on a Message and calling `DirectChannel.send` does not turn every exception into an error message. If a gateway should translate errors, configure that gateway's error contract. Fundamental rules are described in [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

For callers, distinguish flow-handoff errors, execution errors, and reply wait timeouts. A timeout does not prove side effects did not occur; resending must rely on an idempotency contract.

### 10.2. Asynchronous flows

When work runs inside a poller or framework-managed task, design a receiver for `ErrorMessage`. For instance, if changing `ordersInput` to a `QueueChannel`, the first consumer must have a poller and can be configured as:

~~~java
endpoint -> endpoint
        .id("ordersValidate")
        .discardChannel("ordersRejected")
        .poller(org.springframework.integration.dsl.Pollers
                .fixedDelay(100)
                .maxMessagesPerPoll(20)
                .errorChannel("ordersErrors"))
~~~

This replaces the filter's endpoint configurer in the main flow, applicable only once the input has switched to a pollable channel. Also declare the `ordersErrors` channel and a consumer for it. If error headers or adapters have custom rules, verify the actual configuration's resolution path.

The snippet below can be added to the example class to read error messages. It records errors routed to the channel without performing retries or recovery yet:

~~~java
@Bean
DirectChannel ordersErrors() {
    return new DirectChannel();
}

@Bean
IntegrationFlow ordersErrorFlow() {
    return IntegrationFlow.from("ordersErrors")
            .handle((org.springframework.messaging.MessageHandler) message -> {
                Throwable failure = (Throwable) message.getPayload();

                Message<?> failedMessage =
                        failure instanceof
                                org.springframework.messaging.MessagingException ex
                                ? ex.getFailedMessage() : null;

                Object correlationId = failedMessage == null
                        ? null
                        : failedMessage.getHeaders()
                                .get("businessCorrelationId");

                LOG.error(
                        "event=error_observed flow=orders "
                                + "correlationId={} errorType={}",
                        safe(correlationId),
                        failure.getClass().getSimpleName());
            }, endpoint -> endpoint.id("ordersErrorLog"))
            .get();
}
~~~

Business context often must be extracted from the failed Message if provided by the exception. `ErrorMessage` headers do not always match the original Message's headers. Expect cases where no failed message exists and supply alternate context from adapters or error strategies when needed.

In the polled variant, `failed` in the handler and `error_observed` in the error branch can both refer to the same failure. Only the endpoint owning the outcome should increment outcome counters; the error-logging branch should not double-increment the same counter.

Distinguish three milestones:

- **Single-attempt error:** the current execution attempt failed.
- **Recovered:** transitioned to an accepted recovery path.
- **Terminal failure:** no further processing will occur under policy.

A logged error line does not by itself confirm a rollback, dead-letter enqueue, or scheduled retry.

## 11. Message history and runtime graph

### 11.1. Message history to inspect internal paths

Can be enabled by component name:

~~~java
@org.springframework.integration.annotation.EnableMessageHistory("orders*")
~~~

Message history records tracked components into the `history` header. It helps inspect paths within the instrumented scope; configuration is presented in [Message History](https://docs.spring.io/spring-integration/reference/message-history.html).

Use intentionally: headers grow across many steps, may not propagate across adapters, and do not replace trace stores or durable logs. Never compute service time merely by subtracting timestamps of two entries without understanding which instants they mark.

### 11.2. Runtime graph to verify live wiring

Spring Integration provides `IntegrationGraphServer` to obtain a runtime model of components and links; see [Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html).

The graph is useful for checking actual names, discard branches, DSL-created intermediate channels, and post-deployment wiring. It is not a per-order execution history, nor does it prove messages were consumed.

In a Boot application with Actuator, the `integrationgraph` and `metrics` endpoints support inspecting configuration and metrics. If exposed over HTTP, configure exposure appropriately, such as in a practice environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,integrationgraph
~~~

Once traffic flows, inspect meters at `/actuator/metrics` and the graph at `/actuator/integrationgraph` under the default base path. Access also depends on the web stack, access configuration, and security. See [Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

The graph can expose component names or configuration expressions. Choose access scopes appropriate for personnel diagnosing the system.

## 12. Applying to other integration patterns

The rules below are suggested application-level observability signals, not metric names automatically generated by the framework.

| Component | What needs visibility | Risk without observability |
| --- | --- | --- |
| Transformer | Before/after types, transformation version, mapping errors | Unknown at which boundary data broke |
| Filter | Accepted count, discarded count, reason codes | Traffic vanishes without an outcome |
| Router | Normalized route key, chosen branch, fallback | Wrong or default branch grows unnoticed |
| Splitter | Parts emitted, group key, required sequence metadata | Hard to trace missing parts back to original request |
| Aggregator | Open groups, group age, releases, expiries, discards | Groups wait forever or emit incomplete results |
| Gateway | Reply contract, timeouts, errors, caller-received results | Caller times out while downstream completes |
| Outbound endpoint | Call duration, attempts, target-system acknowledgments | Confusing "sent" with "accepted" |

With splitter/aggregator, inbound and outbound message counts usually differ. For instance, an order with five lines spawns five child messages, then aggregates into one result. Dashboards must distinguish orders, child items, groups, and attempts.

With an aggregator, an "open groups" metric alone does not tell whether they are progressing normally or stuck. Combine group age, received item counts, release conditions, and expiry actions. Put specific group IDs in diagnostic logs; avoid creating metric tags for individual group IDs.

With a router, keep reason codes and route labels in a finite catalog. If route names are derived dynamically from input data, control both route count and metric series count.

## 13. Designing outcome-driven dashboards and alerts

A first dashboard should answer five things: is work arriving, is it completing, how is the error rate changing, how long does it take, and where is work piling up.

### 13.1. Calculations need well-defined denominators

For example, in a non-retrying flow where each request has one final outcome:

~~~text
Technical failure rate in a window
  = failed count
    / (processed count + rejected count + failed count)
~~~

If measuring the error rate of the post-filter processing step, the denominator can be `processed + failed`. The two calculations answer different questions; label names and meanings clearly on the dashboard.

When retries exist, clarify whether you are counting per attempt or per unique request. One order failing twice and then succeeding creates three attempts yet only one final outcome. Never label an attempt-level counter as "failed orders".

Cumulative counters depend on process age. For traffic charts, typically look at rates of increase over windows and handle resets on restart. Micrometer explains counter interpretation in [Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

### 13.2. Latency and backlog

Monitor concurrently:

- End-to-end latency per the business contract.
- Duration at critical processing steps or dependencies.
- Queued item count and capacity utilization.
- Oldest queued job age if measurable.
- Inbound rate and outbound rate.

Never average per-instance p95 values to compute an overall p95. If aggregated percentiles are needed, use histograms and appropriate backend queries; distribution collection must be configured beforehand.

For example, a queue grows from 100 to 900 items while handler duration stays nearly flat: check intake/drain rate imbalance, consumer count, executors, and poller wait times before concluding the processing algorithm slowed down.

Conversely, a small queue with high message age can point to a stuck item, priority starvation, or prolonged retries. Each symptom requires a hypothesis and corroborating evidence.

### 13.3. Actionable alerts

| Reference condition | Investigation action |
| --- | --- |
| Sustained rise in technical errors with sufficient traffic | Select failing endpoint, grab representative trace/correlation IDs |
| Job age exceeds business limit | Check consumers, backlog, and dependencies |
| Intake continues with no final outcomes for a long time | Check filters, routers, aggregator groups, stopped endpoints |
| Telemetry branch continuously drops events | Check capacity, exporter, and sampling policy |
| Unusual spike in rejection rate | Compare schemas, sending sources, and rule changes |

Thresholds must be based on service objectives and system traffic. For instance, "95% of valid orders complete within 2 seconds" is meaningful only once start point, end point, retry handling, and expiry requirements are defined.

## 14. Testing observability

Do not merely check that a log line exists. Verify that signals accurately reflect behavior and can trace a request.

| Scenario | Business check | Observability check |
| --- | --- | --- |
| Valid order | Runs expected processing step | One `processed` outcome, `correlationId` preserved |
| Invalid data | Does not call process | `rejected` recorded with finite reason code |
| Handler throws exception | Caller gets error or configured error path runs | Error recorded at right endpoint, no double-counted outcome |
| New Message created after transform | Normalized values correct | Does not rely on technical ID staying unchanged |
| Retry then succeed | Side effects match idempotency contract | Distinguishes attempts from final outcome |
| Telemetry branch stopped | Behavior matches overload policy | Buffer-full or telemetry-loss signal emitted |
| ID contains newlines or sensitive data | Validation enforces rules | Logged fields sanitized, full payload not dumped |
| Switch DirectChannel to queue | Delivery and poller work properly | Send duration not mistaken for completion duration |

For the Section 6 example, snapshot counter values before sending and compare increments after each Message. If tests share a registry or application context, never assume counters start at 0.

For asynchronous flows, wait for a concrete condition with a bounded timeout: result appears, counter increments, or Message reaches a test channel. Avoid sleeping for a fixed duration and assuming completion, as scheduling varies with load.

To test telemetry impact, compare business outcomes with the observation branch enabled vs. disabled, while simulating a slow exporter or full buffer. Check outputs, side effects, caller-visible errors, and resource bounds.

To test cardinality, send many orders with distinct IDs across the same outcome/region set. Business tag combinations must stay within the designed bound.

## 15. Diagnostic sequence for a missing request

Suppose a customer reports order `ORD-101` has no result yet.

1. Look up durable business state by order ID to see whether an outcome is already confirmed.
2. Find intake logs and extract the business correlation ID.
3. Cross-check milestones for normalization, routing, rejection, processing, retry, or expiry.
4. If traces exist, inspect the last executed segment and asynchronous boundaries.
5. Check backlog, job age, pollers, executors, or aggregator groups at the stalled segment.
6. Compare the runtime graph against expected wiring.
7. Check whether the telemetry branch was sampled, failed export, or dropped events before concluding the message was lost.
8. Pick a recovery action based on business state and idempotency contracts.

Missing logs are a clue to investigate, not proof by themselves that work never ran.

## 16. Common design mistakes

| Mistake | Consequence | Adjustment |
| --- | --- | --- |
| Logging full Messages at every step | Data exposure, storage bloat, and cost | Select checkpoints and permitted fields |
| Calling successful enqueue "successful processing" | Dashboards look healthy while backlog grows | Record outcomes at the completion-owning endpoint |
| Monitoring only the success branch | Cannot explain data dropped by filters | Observe discard, fallback, and expiry paths |
| Using order ID as a metric tag | Series explode with data volume | Put order IDs in logs/traces appropriately |
| Assuming wire tap runs asynchronously | Logging branch increases caller wait time | Choose target channel and bounds explicitly |
| Summing all timers as end-to-end time | Double-counts nested intervals | Identify boundaries and nesting relationships |
| Incrementing same counter in handler and error logger | Error rate inflated | Pick one owner for outcome events |
| Using message ID as end-to-end business key | Trace breaks after new message creation | Use business keys and correlation IDs |
| Counting only exceptions | Misses rejections, timeouts, and stalled groups | Track business states |
| Unbounded buffer on observation branch | Exhausts resources and harms main flow | Bounded buffer, overflow policy, overload metrics |

An observable flow requires a consistent contract across topology, identifiers, events, and measurements. When that contract is clear, every signal helps explain a specific part of live runtime behavior.
