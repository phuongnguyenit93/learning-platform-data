# Separating Runtime Handlers from Business Services

In Spring Integration, a **message handler** is the bridge between messaging infrastructure and application logic. A message travels through a channel, is received by a consumer endpoint, and is passed to a handler for execution. If a handler manages headers, retries, threads, and error channels while also containing business rules and database operations, small runtime changes easily force business changes, making testing and error handling hard to control.

The goal of this lesson is to organize two clear layers of responsibility:

- **Runtime handler (integration adapter):** understands Spring Integration, receives and transforms messages, reads necessary metadata, invokes the service, builds the return result, and lets infrastructure orchestrate errors.
- **Application/domain service:** executes the use case, enforces business invariants, and manages transactions and business state; it can be called from REST, batch jobs, schedulers, or message flows without depending on Spring Integration APIs.

This is a design principle for the **Spring Integration runtime**, where message flows are orchestrated across channels, endpoints, consumers, pollers, and executors. Layer separation allows changing topology, transaction boundaries, retries, or error handling while keeping a consistent business service.

## 1. Boundary Between Runtime and Business Logic

~~~mermaid
flowchart LR
    A["Gateway / Inbound Adapter"] --> B["MessageChannel"]
    B --> C["Consumer endpoint"]
    C --> D["Runtime handler"]
    D --> E["Application service"]
    E --> F["Domain / Repository"]
    D -. "result" .-> C
    C -. "reply" .-> G["Reply channel / Gateway"]
    C -. "errors when runtime configured" .-> H["Error flow"]
~~~

A <code>ServiceActivator</code> is a consumer endpoint that binds a handler to a channel. The handler is invoked by Spring Integration whenever the endpoint receives a message. The service behind the handler does not need to know whether the message arrived from HTTP, Kafka, an in-memory queue, or a poller.

| Concern | Runtime Handler / Integration Configuration | Business Service |
|---|---|---|
| Communication | <code>Message</code>, payload, headers, channel, reply | Application commands/DTOs and domain types |
| Transformation | Normalize payload, validate required headers, map to command | Enforce business rules and invariants |
| Orchestration | Subscribers, pollers, executors, routing, timeouts | Execute use case, coordinate domain/repositories |
| Reliability | Retry advice, error flows, dead-letter/recovery policy | Safely re-executable operations, deduplication by business key |
| Transactions | Configure transaction start points on pollers/adapters if needed | <code>@Transactional</code> wrapping business data changes |
| Observability | Correlation/tracing headers, endpoint/channel metrics | Logs and metrics for business outcomes |
| Lifecycle | Start/stop endpoints, flows, consumers, and executors | Service is independent of whether the flow is running or stopped |

**Dependency rule:** the handler calls the service; the service never calls back into <code>MessageChannel</code>, never reads <code>MessageHeaders</code>, and knows nothing about <code>IntegrationFlowContext</code>. When a use case genuinely needs to emit a business event, the service can publish a domain event or call an application-defined port; an outer adapter translates that event into a message.

## 2. Signs a Handler Has Too Many Responsibilities

Example of a hard-to-maintain handler:

~~~java
@ServiceActivator(inputChannel = "placeOrder.input")
public void handle(Message<PlaceOrderRequest> message) {
    // Code illustrating a design to avoid:
    // reading headers + manual retries + querying/saving database + sending another message
    // + evaluating discount rules + swallowing exceptions.
}
~~~

In this model, testing discount rules forces you to construct a <code>Message</code> and Spring Integration wiring; every retry may save the order twice; catching and merely logging an exception tricks the endpoint into thinking processing succeeded. Switching <code>DirectChannel</code> to <code>ExecutorChannel</code> can alter error and transaction behavior without the handler code giving any hint of it.

Instead, keep the handler thin, though **not dogmatically**: it is still allowed to validate required headers, normalize formats, and classify infrastructure errors. Rules such as "quantity must be positive," "orders must not be duplicated," or "customer is eligible to place an order" belong in the business service.

## 3. Complete Example: Gateway → Channel → Handler → Service

Suppose the application receives order creation commands scoped by <code>tenantId</code>. A gateway provides a synchronous Java API, the handler maps the message to a command, and the service handles the transaction. The code snippets below form a concise Spring Integration 6.x and Spring Framework 6.x example; persistence implementation is abstracted behind an <code>OrderStore</code> port.

**Step 1 — define use case data and contract without messaging dependencies:**

~~~java
public record PlaceOrderRequest(String orderId, int quantity) {}
public record PlaceOrderCommand(String tenantId, String orderId, int quantity) {}
public record OrderReceipt(String orderId, String status) {}

public interface OrderStore {
    // Real implementation must guarantee uniqueness by tenantId + orderId
    OrderReceipt createIfAbsent(PlaceOrderCommand command);
}
~~~

**Step 2 — service holds business rules and transactions:**

~~~java
@Service
public class PlaceOrderService {
    private final OrderStore orderStore;

    public PlaceOrderService(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @Transactional
    public OrderReceipt place(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }
        return orderStore.createIfAbsent(command);
    }
}
~~~

<code>OrderStore.createIfAbsent</code> illustrates an operation that can safely handle message redelivery: the application must enforce uniqueness via persistence constraints/transactions, not merely an in-memory variable. <code>@Transactional</code> takes effect when the service is invoked through a Spring proxy, such as from a handler in a separate bean.

**Step 3 — handler performs conversion and delegation:**

~~~java
@Component
public class PlaceOrderRuntimeHandler {
    private final PlaceOrderService service;

    public PlaceOrderRuntimeHandler(PlaceOrderService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "placeOrder.input")
    public OrderReceipt handle(Message<PlaceOrderRequest> message) {
        String tenantId = message.getHeaders().get("tenantId", String.class);
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenantId");
        }

        PlaceOrderRequest request = message.getPayload();
        PlaceOrderCommand command = new PlaceOrderCommand(
            tenantId, request.orderId(), request.quantity()
        );
        return service.place(command);
    }
}
~~~

The handler does not touch <code>EntityManager</code>, does not evaluate business rules, does not call <code>Thread.sleep()</code> to retry, and does not swallow exceptions. The returned <code>OrderReceipt</code> becomes the payload of the reply produced by Spring Integration under request–reply mechanics.

**Step 4 — wiring channel and gateway:**

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderIntegrationConfig {
    @Bean(name = "placeOrder.input")
    MessageChannel placeOrderInput() {
        return new DirectChannel();
    }
}

@MessagingGateway(defaultRequestChannel = "placeOrder.input")
public interface OrderGateway {
    OrderReceipt place(
        PlaceOrderRequest request,
        @Header("tenantId") String tenantId
    );
}
~~~

Common imports: <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>MessagingGateway</code>, <code>IntegrationComponentScan</code>; <code>org.springframework.integration.config.EnableIntegration</code>; <code>org.springframework.integration.channel.DirectChannel</code>; <code>org.springframework.messaging.Message</code>, <code>MessageChannel</code>; <code>org.springframework.messaging.handler.annotation.Header</code>. With Java 17+, the <code>record</code> types in the example can live in separate files.

When calling <code>orderGateway.place(new PlaceOrderRequest("O-42", 2), "T-A")</code>, the gateway builds a message with the payload and <code>tenantId</code> header, sends it through <code>DirectChannel</code>, the endpoint calls the handler, and the handler maps it to <code>PlaceOrderCommand</code> and receives the result from the service. The gateway awaits the reply and returns <code>OrderReceipt</code> to the caller. Reply/timeout settings must be revisited when moving to asynchronous execution.

An equivalent alternative is defining the consumer with Java DSL:

~~~java
@Bean
IntegrationFlow placeOrderFlow(PlaceOrderRuntimeHandler handler) {
    return IntegrationFlow.from("placeOrder.input")
        .handle(handler, "handle")
        .get();
}
~~~

**Choose only one endpoint registration style for the same handler.** When using <code>IntegrationFlow</code> above, remove <code>@ServiceActivator</code> from the <code>handle</code> method; keeping both can register multiple consumers listening on the same channel and lead to unpredictable processing behavior.

## 4. Threading and Transactions: Why Does This Boundary Matter?

Changing channel types can change the execution thread, yet it should not change the API of <code>PlaceOrderService</code>.

| Runtime Configuration | Core Behavior | Impacts to Check |
|---|---|---|
| <code>DirectChannel</code> | Handler runs on the sender's thread; typically synchronous | Exceptions usually propagate to the sender; gateway sees the result as soon as the handler finishes |
| <code>ExecutorChannel</code> | Hands message off to a <code>TaskExecutor</code> | Handler runs on another thread; caller's transaction/thread context does not propagate automatically; a request–reply gateway may still have to wait for the reply |
| <code>QueueChannel</code> + poller | Messages enter a queue; poller fetches and invokes the handler | Must configure poller, capacity, backpressure, commit timing, and behavior when the poller stops |
| <code>PublishSubscribeChannel</code> | Broadcasts to multiple subscribers | Do not use as a single-item work distributor; each subscriber can produce its own side effects |

With <code>DirectChannel</code>, the same thread may run from gateway through handler and service. However, **same thread does not mean every operation is automatically inside the same transaction**: actual boundaries depend on where <code>@Transactional</code> is placed and on the transaction manager. With <code>ExecutorChannel</code> or a poller, a transaction opened on the sending thread will not automatically wrap the receiving service. A transaction on the service can still start on the worker thread if the call goes through a Spring proxy.

When a poller reads messages from a transactional source, you may need transaction advice on the poller/endpoint. Database transactions and external broker acknowledgments do not automatically form a single atomic transaction; flows needing reliable delivery may require inbox/outbox patterns, idempotency keys, or compensating mechanisms.

Do not embed decisions like "which executor to run on," "how often to poll," or "when to stop/start the flow" inside the service. Those decisions belong in channel, consumer endpoint, poller, and <code>IntegrationFlow</code> configuration.

## 5. Retries, Errors, and Idempotency

When processing a message fails, the design must distinguish **business errors that should not be retried** from **transient errors that can be retried**.

1. The service throws meaningful exceptions per use case rules (e.g., invalid order, duplicate key, datastore access error). Never catch every exception and return "success."
2. The runtime configures bounded retries at the consumer endpoint, such as via <code>RequestHandlerRetryAdvice</code>, with backoff and a policy retrying only recoverable errors.
3. Once attempts are exhausted, the endpoint/adapter executes recovery, routes to an error flow, dead-letter queue, or logs/alerts according to the system's delivery guarantees.
4. The service ensures side effects are safe upon re-execution: unique constraints, idempotency keys, processing states, or transactional outbox when needed.

In a synchronous flow over <code>DirectChannel</code>, unhandled exceptions usually propagate back to the sender, possibly wrapped in a Spring Messaging exception. With an asynchronous consumer or poller, errors can be turned into an <code>ErrorMessage</code> on the corresponding <code>errorChannel</code> **if an error-handling path is configured**. Never assume every exception automatically lands on an error channel. <code>errorChannel</code>, retry advice, and ACK/redelivery behavior must be verified specifically for the endpoint/adapter in use.

For instance, a sender may resend the same "create O-42" command. <code>MessageHeaders.ID</code> can differ on each send; it is a message identifier, not a stable business key. Use <code>tenantId + orderId</code> or an explicit <code>idempotencyKey</code> contract to block duplicate writes. If retries re-run email sending or payment API calls, design external side effects accordingly.

### Correlation and Observability

A flow may pass through routers, aggregators, or request–reply steps. The handler should read headers needed for mapping and observability, while preserving or propagating correlation metadata when constructing new messages. The <code>correlationId</code> header correlates processing steps or traces according to the flow's contract; do not treat it as a business key or assume it is always present.

At the runtime layer, track throughput, handler latency, retry counts, queue depth, thread pool saturation, error message counts, and reply wait times. At the business layer, track orders created/rejected and business reasons. Log correlation IDs rather than dumping full payloads that may contain sensitive data.

## 6. IntegrationFlow Lifecycle Is Independent of the Service

Spring Integration manages endpoint lifecycles (such as <code>SmartLifecycle</code>) and can register dynamic flows via <code>IntegrationFlowContext</code>. When toggling processing for a data source, act on the flow registration or consumer endpoint—do not put flag variables and message-receiving loops inside <code>PlaceOrderService</code>.

- **Start:** the endpoint begins receiving/polling; the service is only called when a message is delivered to the handler.
- **Stop:** the endpoint stops receiving/polling according to its endpoint type; in-flight work may need draining, timeouts, or dedicated graceful shutdown handling.
- **Remove/re-register flow:** topology and subscribers change, while the service's command contract remains intact.

Managing executor shutdown, pending queues, open transactions, and reprocessing after restarts belongs to runtime/operations. Stopping an endpoint does not automatically guarantee all in-flight messages finished or were durably persisted.

## 7. Testing by Boundary

With this separation, each layer has a natural testing scope:

| Test Level | What Should It Prove? |
|---|---|
| Service unit tests | Business rules, transactions/persistence via integration tests when needed, duplicate handling by business key |
| Handler unit tests | Reading correct headers, mapping payload → command, invoking the right service, returning results or propagating exceptions |
| Flow integration tests | Gateway sends through channels, endpoints exist, replies return to the right place, timeouts/error channels/retries behave as configured |
| Runtime tests | Switching threads/pollers, concurrent load, backpressure, stop/restart, and redelivery do not corrupt side effects |

Example handler unit test using JUnit 5 and Mockito (imports omitted):

~~~java
@Test
void handlerMapsMetadataAndDelegates() {
    PlaceOrderService service = mock(PlaceOrderService.class);
    PlaceOrderRuntimeHandler handler = new PlaceOrderRuntimeHandler(service);
    PlaceOrderRequest request = new PlaceOrderRequest("O-42", 2);
    PlaceOrderCommand command = new PlaceOrderCommand("T-A", "O-42", 2);
    OrderReceipt receipt = new OrderReceipt("O-42", "ACCEPTED");

    when(service.place(command)).thenReturn(receipt);

    Message<PlaceOrderRequest> message = MessageBuilder.withPayload(request)
        .setHeader("tenantId", "T-A")
        .build();

    assertEquals(receipt, handler.handle(message));
    verify(service).place(command);
}
~~~

This unit test does not need an <code>ApplicationContext</code> or channels. A separate integration test should invoke <code>OrderGateway</code> inside a Spring context to catch wiring issues; dedicated tests with an executor or poller are required to verify real threading, retry, and error-routing behavior.

## 8. Common Design Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Service is hard to reuse from REST or batch | Accepts <code>Message&lt;?&gt;</code> parameters or calls channels internally | Switch to pure application commands/results; let the handler convert |
| Exceptions are lost, system treats call as successful | Handler catches <code>Exception</code> and only logs it | Let errors propagate to appropriate error/retry mechanisms; recover only under explicit policy |
| Orders or payments are created twice | Retries/redeliveries, multiple subscribers, or missing data constraints | Use idempotency keys, unique constraints, and safe side-effect design |
| Gateway hangs/times out | Consumer emits no reply, poller is stopped, or executor is congested | Inspect reply channels, return values, pollers, capacity, and timeouts |
| Data does not roll back as expected | Transaction on the wrong thread, self-invoking <code>@Transactional</code> method in the same bean | Place transactions on a proxied service; inspect poller/adapter boundaries |
| Correlation is lost after message transformation | Manually creating a new message without copying required headers | Build messages preserving essential headers; verify correlation strategy |
| Flow is stopped yet tasks keep running | Work was already handed to an executor or queue before stop | Implement graceful shutdown, track in-flight tasks, and handle reprocessing safely |

## 9. Checklist Before Promoting a Flow to Runtime

- The handler depends only on integration APIs on the outside and one or a few application ports/services; the service has zero dependency on Spring Integration.
- Commands/results are explicit and validation lives at the right layer; operational headers do not leak into domain dependencies.
- Register only one consumer endpoint per handler intentionally; clearly understand unicast vs. publish–subscribe differences.
- Explicitly define synchronous/asynchronous channels, executors/pollers, reply timeouts, and transaction boundaries.
- Define retry/recovery policies for transient errors; enforce idempotency at the persistence or side-effect layer.
- Include sufficient correlation and metrics to trace messages, threads, and errors; maintain tests for the service, handler, and flow wiring.

**Desired outcome:** the runtime is responsible for *when, on which thread, through which channel, and under which error policy* a use case is invoked; the business service is responsible for *what the use case must do and which business states are valid*. This boundary lets message flows evolve without coupling business logic to how Spring Integration orchestrates the runtime.
