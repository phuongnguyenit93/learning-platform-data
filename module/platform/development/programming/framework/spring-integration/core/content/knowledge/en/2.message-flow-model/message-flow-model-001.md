# Pipes and filters

## 1. Lesson objectives

In the **Message flow model** chapter of the **SPRING_INTEGRATION_CORE** module, Pipes and Filters is the foundation for reading and designing a message flow: data passes through steps with clear responsibilities, and the connections between steps are represented by channels.

After this lesson, you can:

- Distinguish between a pipe, a processing step, a message, and an endpoint in a Spring Integration flow.
- Refactor a method handling multiple responsibilities into Java DSL steps with explicit input and output contracts.
- Explain processing order, the path of discarded messages, and the error path.
- Choose where synchronous execution or message buffering is needed.
- Observe results and identify cases that need testing before expanding the flow.

## 2. The problem: an order needs to go through multiple steps

Suppose a partner sends an order in the form:

~~~text
 ord-101 | 125000 | vnd
~~~

The application needs to trim leading and trailing whitespace, convert the data into a Java object, accept only positive amounts in VND currency, and then produce an acceptance receipt.

One implementation approach is to put everything into `processOrder(String raw)`. As requirements grow, this method can end up parsing data, checking business rules, writing to a database, calling services, and sending notifications all at once. Every small change has to go through a large orchestration block; reusing just the parsing step or pinpointing the failure point also becomes harder.

Pipes and Filters splits work into independent steps and connects them with message channels. Each step receives data through an input, performs its own responsibility, and passes the result through an output. This structure is described in [Enterprise Integration Patterns — Pipes and Filters](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html).

For the problem above, we choose:

~~~mermaid
flowchart LR
    I["ordersInput<br/>String"] --> N["Trim whitespace"]
    N --> P["Parse into OrderCommand"]
    P --> F{"Positive amount<br/>and currency = VND?"}
    F -- "Pass" --> H["Create OrderReceipt"]
    H --> O["acceptedOrders"]
    F -- "Fail" --> D["rejectedOrders"]
    P -. "Invalid format" .-> E["Exception to sender<br/>in synchronous example"]
~~~

The arrows represent logical paths. To know which thread a message runs on, whether it waits, or whether it is persisted, you must examine the channel type and endpoint configuration.

## 3. Mapping the pattern to Spring Integration

| Concept | Role in the flow | Commonly used component |
| --- | --- | --- |
| Message | Carries data and processing context | `Message<T>` with payload and headers |
| Pipe | Connects the output of one step to the input of another | `MessageChannel` |
| Processing step | Performs a single responsibility on the message | Transformer, filter, service activator |
| Endpoint | Connects processing logic with message reception and lifecycle | Endpoint registered in the Spring context |
| Entry/exit point | Connects the caller or external system to the flow | Gateway, channel adapter, or direct send/receive |
| Flow definition | Declares components and the relationships between them | `IntegrationFlow` in Java DSL |

### 3.1. "Filter" in the pattern name is broader than `MessageFilter`

In **Pipes and Filters**, a filter is a general term for a processing step. That step might transform data or invoke business logic.

In Spring Integration, **Message Filter** is a specific pattern: it evaluates a condition to decide whether a message proceeds or not. Therefore, a pipeline implementing Pipes and Filters may contain multiple transformers without any `.filter()` call.

When discussing design, use "processing step" for the broad meaning and "message filter" for the step that decides acceptance or rejection. This naming avoids the misconception that every step in a pipeline must return a `boolean`.

### 3.2. Java DSL describes the structure, messages trigger execution

Java DSL creates an `IntegrationFlow` as a Spring bean. When the context initializes, the framework registers the corresponding channels and endpoints; calls such as `.transform()` and `.handle()` declare the steps of the flow. See [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

Therefore, the configuration snippet:

~~~java
IntegrationFlow.from("ordersInput")
        .transform(String.class, String::strip)
        .transform(String.class, OrderFlowDemo::parseOrder)
        .get();
~~~

does not parse an order immediately when the `@Bean` method is invoked. The two transformations execute when a message enters `ordersInput`.

Between adjacent endpoints, the DSL can create internal channels. Thus, not seeing `.channel(...)` between two DSL lines does not mean the two steps have lost message-passing semantics. Configuration and naming rules are covered in [Spring Integration — Message Channels in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

The short snippet above only illustrates how steps are declared. The complete example below includes an output channel to receive the final result.

## 4. Designing contracts before writing the flow

Splitting a large method into multiple lambdas is not enough. The output of a preceding step must satisfy the input contract of the following step.

For the order problem, we define:

| Step | Input payload | Payload on the success path | Behavior when unable to proceed |
| --- | --- | --- | --- |
| Trim whitespace | `String` | `String` after `strip()` | Wrong input type is a contract violation |
| Parse | String with three fields separated by `|` | `OrderCommand` | Malformed structure, empty order ID, or unparseable amount throws an exception |
| Business validation | `OrderCommand` | Keeps the accepted message unchanged | Non-positive amount or currency other than VND is sent to `rejectedOrders` |
| Create receipt | Valid `OrderCommand` | `OrderReceipt` | An exception in this step is treated as a processing error |
| Collect result | `OrderReceipt` | Held in `acceptedOrders` for consumption | Output requires an appropriate receiver |

Here, "parseable amount" and "accepted amount" are two distinct conditions:

- `abc` cannot be parsed into a `BigDecimal`: malformed data.
- `-500` can be parsed, but does not meet the acceptance policy: the message is rejected by business rules.

This classification decision belongs to application design. Another system might route both cases to a manual review channel; what matters is that the contract states the behavior clearly.

## 5. Complete Java DSL example

The example uses Java with `record` support, along with compatible Spring Context and Spring Integration Core libraries managed by the project. No broker or database connection is required.

Place the following source code in `OrderFlowDemo.java`. In the example:

- `ordersInput` is a `DirectChannel`.
- Intermediate steps in the flow use direct connections created by the DSL.
- `acceptedOrders` and `rejectedOrders` are in-memory queues, each with a capacity of 10 messages.
- `main()` acts as the sender and actively reads results from the two queues.

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderFlowDemo {

    public record OrderCommand(
            String orderId,
            BigDecimal amount,
            String currency) {
    }

    public record OrderReceipt(
            String orderId,
            BigDecimal amount,
            String currency,
            String status) {
    }

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel rejectedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersInput")
                .transform(String.class, String::strip)
                .transform(String.class, OrderFlowDemo::parseOrder)
                .filter(
                        OrderCommand.class,
                        order -> order.amount().signum() > 0
                                && "VND".equals(order.currency()),
                        endpoint -> endpoint.discardChannel("rejectedOrders"))
                .handle(
                        OrderCommand.class,
                        (order, headers) -> new OrderReceipt(
                                order.orderId(),
                                order.amount(),
                                order.currency(),
                                "ACCEPTED"))
                .channel("acceptedOrders")
                .get();
    }

    public static OrderCommand parseOrder(String raw) {
        String[] fields = raw.split("\\|", -1);

        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Expected orderId|amount|currency");
        }

        String orderId = fields[0].strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be empty");
        }

        BigDecimal amount = new BigDecimal(fields[1].strip());
        String currency = fields[2].strip().toUpperCase(Locale.ROOT);

        return new OrderCommand(orderId, amount, currency);
    }

    private static void send(
            MessageChannel input, String payload, String traceId) {
        boolean sent = input.send(
                MessageBuilder.withPayload(payload)
                        .setHeader("traceId", traceId)
                        .build(),
                1_000);

        if (!sent) {
            throw new IllegalStateException("Input channel did not accept message");
        }
    }

    private static Message<?> receiveRequired(PollableChannel channel) {
        Message<?> message = channel.receive(1_000);
        if (message == null) {
            throw new IllegalStateException("Expected an output message");
        }
        return message;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowDemo.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);
            PollableChannel accepted =
                    context.getBean("acceptedOrders", PollableChannel.class);
            PollableChannel rejected =
                    context.getBean("rejectedOrders", PollableChannel.class);

            send(input, " ord-101 | 125000 | vnd ", "trace-001");
            Message<?> success = receiveRequired(accepted);
            System.out.println("ACCEPTED: " + success.getPayload());
            System.out.println(
                    "TRACE: " + success.getHeaders().get("traceId"));

            send(input, "ord-102|-500|VND", "trace-002");
            Message<?> discarded = receiveRequired(rejected);
            System.out.println("REJECTED: " + discarded.getPayload());

            try {
                send(input, "ord-103|abc|VND", "trace-003");
            }
            catch (MessagingException exception) {
                System.out.println("ERROR: unable to parse data");
            }
        }
    }
}
~~~

Expected output of the program, excluding framework startup logs:

~~~text
ACCEPTED: OrderReceipt[orderId=ord-101, amount=125000, currency=VND, status=ACCEPTED]
TRACE: trace-001
REJECTED: OrderCommand[orderId=ord-102, amount=-500, currency=VND]
ERROR: unable to parse data
~~~

`parseOrder()` uses `split("\\|", -1)` because `|` has special meaning in regular expressions. The `-1` argument preserves trailing empty fields, ensuring inputs such as `ord-104|100|` are still recognized properly as three fields and proceed to currency validation.

The example does not yet persist orders to storage. `OrderReceipt` here is the result of the demonstration step, not proof that a business transaction has been durably stored.

## 6. Reading the flow message by message

### 6.1. Valid order

For ` ord-101 | 125000 | vnd `:

1. `ordersInput` receives a message with a string payload and a `traceId` header.
2. The first transformer strips leading and trailing whitespace.
3. The second transformer parses the three fields and normalizes the currency to `VND`.
4. The filter evaluates the condition on `OrderCommand` and lets it pass.
5. The handler creates an `OrderReceipt`.
6. The resulting message is placed into `acceptedOrders`; `main()` reads it via `receive()`.

In this configuration, the flow up to placing the result into the queue runs on the thread that calls `send()`. Using a queue at the output only allows the program to retrieve results afterward; it does not automatically create a business processing worker.

### 6.2. Order rejected by business rules

For `ord-102|-500|VND`, the parsing step still produces an `OrderCommand`. The filter returns `false`, so the message goes to `rejectedOrders` and does not reach the receipt handler.

The discarded payload is `OrderCommand` because that is the payload at the moment the filter runs. If reconciliation against the original raw data is needed, you must design a way to keep the original payload or a reference to it from the start of the flow.

The `traceId` header helps correlate observations across steps to the same processing run. In the example, transformation functions return the payload and the framework handles creating the next message; avoid manually constructing a new message and accidentally dropping needed context.

### 6.3. Unparseable data

For `ord-103|abc|VND`, `new BigDecimal("abc")` fails inside the transformer. The filter has not been invoked yet, so the filter's `discardChannel` configuration does not receive this case.

That is an important distinction when diagnosing issues: **the channel receiving messages discarded by a filter does not automatically become the channel receiving all pipeline errors**.

## 7. Channels determine how steps coordinate at runtime

The same business diagram can exhibit very different execution behavior when channels are changed.

| Channel | Primary handoff mechanism | Design considerations |
| --- | --- | --- |
| `DirectChannel` | Invokes a single subscriber on the sender's thread | Directly connected steps block the sender |
| `QueueChannel` | Buffers messages for a receiver to pull | Requires a consumer to read; define capacity and timeout |
| `ExecutorChannel` | Dispatches processing through an executor | Manage thread pools, backpressure/overload, and error paths |
| `PublishSubscribeChannel` | Broadcasts to subscribers | Use when multiple receivers are needed; executor determines thread separation |

Multiple consumers reading from the same queue do not mean every consumer receives the same message. Nor should multiple subscribers on a `DirectChannel` be used as a substitute for a sequence of steps.

These differences are described in [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 7.1. A synchronous pipeline does not mean the whole application is single-threaded

The main example keeps each send on the caller's thread. If multiple threads call `send()` concurrently, those executions can still run concurrently through the same beans.

Therefore, write processing steps without storing per-message mutable state in shared fields. The following pattern easily causes data mix-ups:

~~~java
// Design pattern to avoid when the same instance receives multiple messages.
private String currentOrderId;
~~~

Prefer local variables and pass data via payload or headers. In this lesson, the records only contain immutable values such as `String` and `BigDecimal`, making data sharing easier to reason about.

### 7.2. Adding a mid-flow queue requires a consumer to pull messages

If you want to buffer valid orders before the business handler step, you can add a bean:

~~~java
@Bean
public QueueChannel validatedOrders() {
    return new QueueChannel(100);
}
~~~

Then replace the `.handle(...)` section near the end of `orderFlow()` with the configuration below, keeping the preceding steps and the trailing `.channel("acceptedOrders").get()`:

~~~java
.channel("validatedOrders")
.handle(
        OrderCommand.class,
        (order, headers) -> new OrderReceipt(
                order.orderId(),
                order.amount(),
                order.currency(),
                "ACCEPTED"),
        endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofMillis(100))
                        .maxMessagesPerPoll(10)))
~~~

The replacement requires adding these imports:

~~~java
import java.time.Duration;
import org.springframework.integration.dsl.Pollers;
~~~

The poller is attached to the endpoint reading `validatedOrders`. The two queues at the end of the main example do not need a framework poller because `main()` actively calls `receive()`; by contrast, a queue in the middle of a pipeline needs an endpoint to keep pulling messages for processing.

After this change, the sender can complete once the valid order enters `validatedOrders`, while the receipt is produced on a subsequent poll. You must re-evaluate output wait timeouts and error reporting paths across the queue boundary.

Default queues keep data in memory; if messages must survive restarts, an appropriate backing store must be chosen. Spring describes these options further in [QueueChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

## 8. Designing explicit discard and error paths

### 8.1. Filter rejection

A filter can let a message proceed, route discarded messages to a discard channel, or throw an exception depending on its configuration. If neither a discard channel is configured nor throwing on rejection is enabled, discarded messages produce no output on the main branch. See [Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

In the order example, `rejectedOrders` is used because rejected data needs to be observed. If rejections must be reported as errors, you can **replace** the current filter configuration with:

~~~java
.filter(
        OrderCommand.class,
        order -> order.amount().signum() > 0
                && "VND".equals(order.currency()),
        endpoint -> endpoint.throwExceptionOnRejection(true))
~~~

The two options represent two different acceptance contracts. Choose based on caller expectations and how the system is operated.

### 8.2. Execution exceptions

In a `DirectChannel` chain, exceptions normally propagate back to the sender along the call stack. Once processing moves to an executor task or a poller, you must look at how `ErrorMessage` instances are emitted; the framework's error handler can use the `errorChannel` header or the global `errorChannel`. See [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

In the main example, the `try/catch` around the third send observes the parsing error. After adding a mid-flow queue, an error occurring inside the poller-invoked handler is no longer on the call stack of the original send.

Simply setting an `errorChannel` header does not automatically turn every synchronous exception into an error message. When designing an error branch, identify clearly which component catches the exception and emits the `ErrorMessage`.

### 8.3. Gateways require a complete reply contract

A gateway can provide a Java interface for calling into the pipeline. If the gateway method expects a return value, you must design for success, rejection, and error cases alike.

The current example sends results to `acceptedOrders` for direct reading. Attaching a gateway to the input is not enough for the gateway to automatically receive results routed to this output queue.

For an endpoint that produces a reply, an explicit output channel takes precedence; when no output channel is configured, `replyChannel` can supply the reply destination. A handler returning `null` or `void` can also terminate processing without producing a reply. These rules are described in [Spring Integration — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

A filter that discards a message without producing a reply can cause a request–reply caller to time out. For example, an order-intake API should choose one of these contracts:

- Return a structured acceptance or rejection result.
- Report rejection as an exception according to an agreed interface.
- Accept commands strictly one-way and provide a separate mechanism to observe outcomes.

## 9. Step ordering is part of business logic

Steps have separate responsibilities, yet they can still depend on each other's outputs.

In this flow, `amount().signum() > 0` requires a `BigDecimal`; therefore, parsing must occur before validation. Moving the filter ahead of the transformer leaves the payload as a `String`, and the contract no longer matches.

Similarly, we normalize `vnd` to `VND` before checking. Checking the raw currency string with a case-sensitive comparison could reject input that is valid under the agreement.

A sensible sequence for the example is:

~~~text
Raw data
→ Parse structure and normalize
→ Check acceptance criteria
→ Perform business side effects
→ Publish result
~~~

When adding a new step, write down explicitly:

1. Which preceding step's prepared data does this step require?
2. If it fails here, which side effects have already occurred?
3. Does pre-transformation data need to be retained for investigation or reprocessing?

For example, checking the amount after deducting funds changes the consequences of the rejection branch. Just because a diagram can be reordered does not guarantee every order is valid.

## 10. Message boundaries and side effects

### 10.1. Keep data contracts clear

At the input, the example receives a three-field string. After parsing, business steps work with `OrderCommand` rather than repeatedly splitting the string.

If multiple sources send JSON, CSV, or file-based data, separate input adapters/transformers can be built and normalized to the same command type. The validation and command-handling logic then becomes reusable.

Do not cram every transformation requirement into one giant step. Split steps when two parts evolve under different rules, need reuse, or require independent observability; small operations that always belong together can remain in one function.

### 10.2. Do not use `null` to implicitly represent every outcome

A transformer is responsible for producing a valid output; returning `null` is not the way to filter messages in a Spring Integration transformer. See [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

For a rule like "do not process invalid orders further," using a filter or an explicit business result makes the policy visible to readers. Avoid situations where callers cannot distinguish between "rejected," "data not found," and "handler forgot to return a result."

### 10.3. Retries must account for side effects that already occurred

Suppose later the pipeline has two steps:

~~~text
Record payment → Send notification
~~~

If sending the notification fails and the entire pipeline is retried, the payment could be recorded a second time. When adding retries, define the retry scope and a business identifier such as `orderId` or an idempotency key.

`traceId` is primarily for tracing; a resent order may carry a new `traceId`. Therefore, deduplication keys must be based on dedicated business conventions.

Likewise, a flow chaining multiple steps does not automatically guarantee all-or-nothing commit or rollback. Transactions must be designed around the actual participating resources and the coordination mechanism in use. An executor or queue boundary is a signal to revisit assumptions about the sender thread's transaction.

## 11. When a pipeline expands into multiple branches or messages

Pipes and Filters provides a way to compose steps; real integration flows often need additional patterns from the module:

| Emerging need in the order problem | Expansion direction |
| --- | --- |
| Classify orders by region to route to the appropriate team | Router selecting the processing path |
| Notify multiple interested parties of the same event | Publish–subscribe branch |
| Process individual line items of an order | Splitter creating component messages |
| Wait for line-item results to build a combined outcome | Aggregator with correlation and completion rules |
| Wrap the flow behind a Java interface | Messaging gateway |

When one order becomes multiple messages, revisit what "done" means. Completing one line item does not mean the whole order is complete.

If a child message is discarded before aggregation while the aggregator's completion condition still waits for all original parts, the group may never complete. That is why message counts, correlation rules, and timeout policies must all be considered when expanding a pipeline.

Detailed configurations for routers, splitters, and aggregators belong to their respective dedicated lessons; here, they illustrate how the Pipes and Filters foundation continues to apply in more complex flows.

## 12. Buffering data and capacity planning

A queue provides a temporary waiting area. It only absorbs a traffic burst if the system still has capacity to drain the backlog afterward.

Suppose three steps take 2 ms, 3 ms, and 20 ms per message respectively, ignoring all other overhead:

- On a single thread executing all three steps sequentially, one pass takes about 25 ms, or roughly 40 messages/second.
- If split into stages with dedicated workers and one worker per stage, the 20 ms stage handles only about 50 messages/second. That is the ideal upper bound of that pipeline.
- If input arrives continuously at 100 messages/second in the second setup, the backlog grows by roughly 50 messages/second.
- An initially empty 500-message buffer can fill up in about 10 seconds under those assumptions.

These numbers are illustrative calculations from assumed processing times, not Spring Integration benchmarks.

When deciding to add a buffer, answer:

- How many messages and how much data can the system afford to hold in memory?
- What should the sender do when the buffer is full?
- How long can a message wait before its result becomes useless?
- Do multiple messages need concurrent processing, and does completion order matter?

A timeout on a send operation typically applies to handoff into the channel, not an end-to-end deadline covering all downstream work. Specifically, passing `1_000` to `send()` in the example does not interrupt a synchronous handler running longer than one second.

`send()` returning `true` must also be interpreted according to configuration: with a mid-flow queue, it may only prove the message entered the buffer; with a discarded branch, it does not prove the order was accepted.

## 13. Observing and testing against the flow contract

When putting the example under test, verify both expected outputs and outputs that must not appear.

| Input or scenario | What to verify |
| --- | --- |
| ` ord-101 | 125000 | vnd ` | One `OrderReceipt` in `acceptedOrders`, currency is `VND`, `traceId` preserved |
| `ord-102|-500|VND` | One `OrderCommand` in `rejectedOrders`, no acceptance receipt |
| `ord-103|100|USD` | Rejected under the currency policy |
| `ord-104|abc|VND` | Parsing error; does not pass through filter or handler |
| `ord-105|100` | Structural error due to missing field |
| `|100|VND` | Error due to empty order ID |
| `ord-106|100|` | Rejected due to empty currency under the example contract |

In the synchronous example, after `send()` returns you can call `acceptedOrders.receive(0)` and `rejectedOrders.receive(0)` for immediate verification. Use a fresh context or clean state between scenarios so messages from previous runs are not read by mistake.

In the poller variant, observing results requires a bounded wait time. Avoid concluding "no message" from a single immediate read after `send()`, because the work may not have been polled yet.

To diagnose a processing run, prioritize logging:

- Step name and `traceId` or business key.
- Payload type at key boundaries.
- Counts of succeeded, discarded, and errored messages.
- Processing latency and backlog size when queues are present.

That information answers "where did the message stop" without relying on dumping full payloads in every log entry.

## 14. Common design mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No result reaches the final handler | Filter discarded the message or an earlier step threw an error | Inspect the discard branch and error branch |
| Flow stalls after adding a queue | No matching consumer or poller is configured | Configure an endpoint to read from the queue |
| Assuming every DSL line runs on its own thread | Confusing logical structure with execution mechanism | Check channel types and executors |
| Gateway hangs until timeout | A branch produces no reply or sends output to another channel | Complete the reply contract |
| One subscriber gets messages while another does not | Using a point-to-point channel for broadcast needs | Choose an appropriate publish–subscribe setup |
| Retries cause duplicate business operations | Retry scope includes un-deduplicated side effects | Define idempotency and retry boundaries |
| Data bleeds between orders | Endpoint stores per-message state in a shared field | Use local variables and clear data contracts |
| Increasing queue capacity still leaves growing backlog | Long-term processing rate is lower than intake rate | Measure bottlenecks and adjust intake/processing capacity |

## 15. Extended practice

1. Add a step to normalize order IDs to uppercase. Keep `parseOrder()` focused solely on data structure, then determine where to place the new step so both the filter and receipt see the normalized ID.
2. Add a branch accepting foreign-currency orders for separate reconciliation. Decide when a router is needed instead of the current filter's accept/reject condition.
3. Apply the `validatedOrders` and poller variant, then trigger an error inside the handler to observe the difference between errors before and after the queue.
4. Replace the receipt-creation step with a service that performs persistence. Define an idempotency key and the behavior when the sender resubmits the same order.

For each change, write down the payload contract, success path, rejection path, and error observation strategy before modifying the Java DSL.
