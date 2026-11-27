# Building Functions with Plain Java and Platform Adapters

A serverless function does not necessarily have to be written with a specific framework. At the application level, a function can simply be a Java class that receives input data, invokes business logic, and returns a result. When deployed to AWS Lambda, Azure Functions, Google Cloud Functions, or another platform, an adapter layer converts the platform's trigger format and context into a contract that the plain Java core understands.

This organization separates two concerns: **business logic** decides what the application does; the **platform adapter** decides which protocol HTTP data, messages, or events are received and responded to. The Java core can be tested with ordinary unit tests, while the adapter only needs to verify the mapping of input, output, errors, identity, and trigger metadata.

## 1. What Does a Java Function Actually Need?

At a simple level, a function has three parts:

1. **Input contract:** input data and necessary metadata such as request ID, tenant, correlation ID, or processing deadline.
2. **Business logic:** validating business rules, reading/writing data, and determining the outcome.
3. **Output contract:** a structured success result or error so that the adapter can convert it into an HTTP response, message acknowledgement, or event result.

For example, an order creation function can receive `PlaceOrderRequest`, validate the line items, and return `PlaceOrderResult`. The business core does not need to know whether the request came from API Gateway, an Azure HTTP trigger, or a queue consumer.

```text
HTTP / Queue / Event
        |
        v
Platform adapter
  - deserialize input
  - read identity and metadata
  - map platform context
        |
        v
Plain Java function / use case
  - validate business rules
  - call repository and services
  - return result or domain error
        |
        v
Platform adapter
  - map result/error
  - HTTP response or ACK/retry
```

The adapter is not the place to hold all business logic. If a function has multiple triggers, multiple endpoints, or multiple platforms, keeping the business core independent reduces duplication and ensures infrastructure changes have minimal impact on the domain.

## 2. Designing the Core with Plain Java

Plain Java here means the business layer depends only on the JDK and interfaces defined by the application. It does not need to import annotations, request classes, or cloud-provider-specific SDKs. Ordinary records, classes, interfaces, and exceptions can be used.

An in-process synchronous transformation can be represented with `java.util.function.Function<PlaceOrderRequest, PlaceOrderResult>` or a method reference like `useCase::execute`. This is merely a Java functional interface; it does not automatically create a deployment entry point, trigger, retry, or FaaS scaling mechanism. The runtime still needs an adapter or framework to know how to invoke the application.

Example contract for an order creation request:

```java
import java.util.List;

public record PlaceOrderRequest(
        String customerId,
        List<OrderLineRequest> items,
        String idempotencyKey
) {}

public record OrderLineRequest(
        String productId,
        int quantity
) {}

public record PlaceOrderResult(
        String orderId,
        String status
) {}
```

The types above are the application's contract. Do not put `APIGatewayProxyRequestEvent`, `HttpRequestMessage`, `CloudEvent`, or SDK classes into business DTOs unless necessary. The adapter can convert platform types into these DTOs.

`record` has been available since Java 16. If the target runtime uses Java 11 or lower, represent the contract with ordinary classes having constructors, getters, and equivalent immutability rules. Always choose syntax according to the JDK supported by the deployment platform.

Next, define interfaces for the dependencies that the use case needs:

```java
import java.util.Optional;

public interface OrderRepository {
    Optional<PlaceOrderResult> findByIdempotencyKey(
            String customerId,
            String idempotencyKey
    );

    void save(String customerId, PlaceOrderRequest request,
              PlaceOrderResult result);
}

public interface OrderIdGenerator {
    String nextId();
}
```

The use case handles business rules and uses the interfaces above instead of instantiating database clients itself or reading environment variables:

```java
import java.util.Objects;

public final class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final OrderIdGenerator ids;

    public PlaceOrderUseCase(OrderRepository orders,
                             OrderIdGenerator ids) {
        this.orders = Objects.requireNonNull(orders);
        this.ids = Objects.requireNonNull(ids);
    }

    public PlaceOrderResult execute(PlaceOrderRequest request) {
        validate(request);

        var previous = orders.findByIdempotencyKey(
                request.customerId(), request.idempotencyKey());
        if (previous.isPresent()) {
            return previous.get();
        }

        var result = new PlaceOrderResult(ids.nextId(), "PLACED");
        orders.save(request.customerId(), request, result);
        return result;
    }

    private void validate(PlaceOrderRequest request) {
        if (request == null || request.customerId() == null
                || request.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }
        if (request.idempotencyKey() == null
                || request.idempotencyKey().isBlank()) {
            throw new InvalidOrderException("idempotencyKey is required");
        }
        if (request.items() == null || request.items().isEmpty()) {
            throw new InvalidOrderException("at least one item is required");
        }
        for (var item : request.items()) {
            if (item == null || item.productId() == null
                    || item.productId().isBlank() || item.quantity() <= 0) {
                throw new InvalidOrderException("invalid order item");
            }
        }
    }
}
```

`InvalidOrderException` is an application-defined exception. In a real system, looking up the idempotency key and saving the order must be protected by a unique constraint or a transaction/conditional write; the abbreviated code above only illustrates the call flow and does not guarantee safety when two invocations run concurrently. If the key already exists with a different request hash, the use case should return a conflict instead of blindly returning the previous result.

A minimal exception can be declared as follows:

```java
public final class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

This core has no knowledge of which cloud the function runs on. `execute` can be called from a unit test, an HTTP adapter, a message handler, or a locally running Java application.

## 3. Distinguishing the Function Handler from the Platform Adapter

On many platforms, the deployer must provide an entry point following an interface or convention recognized by the runtime. That entry point is the adapter. The runtime calls the adapter, the adapter reads the trigger envelope, and calls the Java core.

| Trigger type | Data received by the adapter | What the adapter typically must do |
| --- | --- | --- |
| HTTP | Method, path, headers, query, body, identity | Validate protocol, parse body, map status/headers/body |
| Queue/message | Message ID, body, receive count, visibility/ack metadata | Parse message, invoke handler, ACK or allow retry per protocol |
| Event bus | Event envelope, source, type, time, data | Validate schema/source, map event, and prevent duplicates |
| Scheduler | Trigger time, schedule metadata | Determine scheduled interval, avoid duplicate runs, and handle delay |

An HTTP adapter needs to care about status codes and response headers. A queue adapter needs to understand ACK, batching, and retry. An event adapter needs to check `eventId`, `source`, `type`, and schema. Do not use the same error-return mechanism for every trigger: HTTP can return 4xx/5xx, whereas a queue usually needs to throw an error or return a partial batch failure so the event source redelivers the message.

## 4. A Provider-Independent HTTP Adapter

Before wiring a specific SDK, you can create an internal adapter layer with a small contract:

```java
public record FunctionRequest<T>(
        T body,
        String requestId,
        String correlationId,
        String tenantId
) {}

public record FunctionResponse<T>(
        int statusCode,
        T body,
        String correlationId
) {}

public final class PlaceOrderFunction {
    private final PlaceOrderUseCase useCase;

    public PlaceOrderFunction(PlaceOrderUseCase useCase) {
        this.useCase = useCase;
    }

    public FunctionResponse<PlaceOrderResult> handle(
            FunctionRequest<PlaceOrderRequest> request
    ) {
        var result = useCase.execute(request.body());
        return new FunctionResponse<>(201, result,
                request.correlationId());
    }
}
```

The `PlaceOrderFunction` class is the application's entry point, yet it is still not tied to any cloud provider. The platform adapter will construct `FunctionRequest`, invoke `handle`, and convert `FunctionResponse` into the runtime's response type.

In this example, tenant and customer identity must be obtained from the authenticated identity, not trusted from fields self-reported by the client. In the abbreviated code, authentication is assumed to have been performed before invoking the function.

## 5. AWS Lambda Adapter with RequestHandler

The AWS Lambda Java runtime provides the `RequestHandler<I, O>` interface. The runtime deserializes the payload into type `I`, invokes `handleRequest`, and serializes the return value into the output. This is a straightforward way to process a structured JSON event.

```java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public final class PlaceOrderLambdaHandler
        implements RequestHandler<PlaceOrderRequest, PlaceOrderResult> {

    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @Override
    public PlaceOrderResult handleRequest(
            PlaceOrderRequest input,
            Context context
    ) {
        // Request ID is useful for logging and tracing.
        String requestId = context.getAwsRequestId();
        context.getLogger().log("Handling place order: " + requestId);
        return useCase.execute(input);
    }
}
```

The example above illustrates a direct Lambda invocation with JSON structured to match `PlaceOrderRequest`. `Context` provides invocation metadata such as request ID, function name, memory limit, and remaining time. Do not pass `Context` into the domain model; if a deadline or correlation ID is needed, map the required values into an internal object.

If Lambda is invoked through API Gateway, the input is usually an event envelope containing method, path, headers, body, and request context. In that case, the handler needs to use the corresponding event type (for example, an API Gateway HTTP API event) or an adapter/framework that supports the gateway to parse the body and build the HTTP response. `RequestHandler<PlaceOrderRequest, PlaceOrderResult>` does not automatically turn into an HTTP API handler.

With SQS or streams, an event may contain multiple records in a single invocation. The adapter must handle batch, ACK, and partial batch response semantics according to the event source mapping. Never assume one invocation always corresponds to one message.

## 6. Azure Functions Adapter with Java Annotations

Azure Functions Java uses annotations to declare the function name and trigger bindings. The runtime invokes the annotated method; the method receives Azure request/context types and returns a response according to the binding.

Example HTTP trigger using a string body so the adapter explicitly deserializes it:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import java.util.Optional;

public final class PlaceOrderAzureFunction {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @FunctionName("placeOrder")
    public HttpResponseMessage run(
            @HttpTrigger(name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION)
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context
    ) throws Exception {
        String rawBody = request.getBody().orElse("");
        PlaceOrderRequest input = JSON.readValue(
                rawBody, PlaceOrderRequest.class);

        PlaceOrderResult result = useCase.execute(input);
        context.getLogger().info(
                "Place order invocation: " + context.getInvocationId());

        return request.createResponseBuilder(HttpStatus.CREATED)
                .header("Content-Type", "application/json")
                .body(JSON.writeValueAsString(result))
                .build();
    }
}
```

This is an example illustrating how to connect an Azure HTTP trigger to the Java core. You need to declare the Azure Functions Java library dependency, the annotation processor/packaging plugin according to the guide for the runtime version in use, and configure appropriate authorization. `AuthorizationLevel.FUNCTION` is a protection level using a function key; production APIs typically require user/application authentication and explicit business authorization. Do not log function keys or tokens.

Azure also has triggers for queues, timers, Event Hubs, and other services. Each binding has its own data types and retry behavior; write adapters appropriate to the trigger instead of trying to turn everything into a fake HTTP request.

## 7. Google Cloud Functions Framework Adapter for HTTP

Functions Framework for Java defines the `HttpFunction` interface. The runtime calls the `service` method with request and response abstractions. The adapter reads the request, parses the body, invokes the core, and writes the response.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.IOException;

public final class PlaceOrderGoogleFunction implements HttpFunction {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws IOException {
        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            response.setStatusCode(405);
            response.getWriter().write("Method not allowed");
            return;
        }

        PlaceOrderRequest input = JSON.readValue(
                request.getReader(), PlaceOrderRequest.class);
        PlaceOrderResult result = useCase.execute(input);

        response.setStatusCode(201);
        response.setContentType("application/json");
        JSON.writeValue(response.getWriter(), result);
    }
}
```

This class illustrates the HTTP adapter of Functions Framework. When running locally, the framework can start the function using the configured entry point; when deployed, the target environment provides the runtime and target configuration. Authentication, authorization, request size limits, and error mapping must still be designed according to the deployment service.

Google also supports functions that receive CloudEvents via the corresponding interface. In the event adapter, read the event ID, source, type, and data; then map them to an internal command/event. Do not assume a CloudEvent has the same schema as an HTTP request.

Example of a CloudEvents adapter that only reads the envelope and forwards the payload to an internal handler:

```java
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;

public final class OrderCreatedCloudEventFunction
        implements CloudEventsFunction {
    private final OrderCreatedHandler handler =
            ApplicationFactory.createOrderCreatedHandler();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"com.example.orders.order-created.v1".equals(event.getType())) {
            throw new IllegalArgumentException("unsupported event type");
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("event data is required");
        }

        String json = new String(
                event.getData().toBytes(), StandardCharsets.UTF_8);
        OrderCreatedMessage message =
                JsonSupport.mapper().readValue(json, OrderCreatedMessage.class);

        // Envelope ID is a stable delivery identifier for the event.
        OrderCreatedMessage normalized = new OrderCreatedMessage(
                event.getId(), message.orderId(), message.customerId(),
                event.getSource().toString(), message.schemaVersion());
        handler.handle(normalized);
    }
}
```

`JsonSupport` is the application's Jackson configuration helper in the example. When deploying, validate the schema/version and allowed event source, handle cases where `data` has a different media type or encoding, and ensure the handler is idempotent because events can be redelivered.

## 8. Adapters for Messages and Events

A queue consumer usually does not return a business response to the producer. The important outcome is whether the message has been processed and ACKed. For example, an internal handler can receive a normalized message:

```java
public record OrderCreatedMessage(
        String eventId,
        String orderId,
        String customerId,
        String source,
        int schemaVersion
) {}

public interface OrderCreatedHandler {
    void handle(OrderCreatedMessage message);
}
```

The queue adapter deserializes the message, validates schema/version, invokes the handler, and decides ACK/retry according to the protocol. If processing succeeds, the adapter acknowledges the message. On transient errors, it can throw an exception or mark the record as failed so the event source redelivers it. On unrecoverable data errors, it must route to a DLQ or error-handling flow according to policy.

Example handler using idempotency by event ID:

```java
public interface ProcessedEventRepository {
    boolean markProcessedIfAbsent(String eventId);
}

public final class OrderCreatedEventHandler
        implements OrderCreatedHandler {
    private final ProcessedEventRepository processedEvents;
    private final CustomerNotificationService notifications;

    public OrderCreatedEventHandler(
            ProcessedEventRepository processedEvents,
            CustomerNotificationService notifications
    ) {
        this.processedEvents = processedEvents;
        this.notifications = notifications;
    }

    @Override
    public void handle(OrderCreatedMessage message) {
        if (!processedEvents.markProcessedIfAbsent(message.eventId())) {
            return;
        }
        notifications.sendOrderConfirmation(message.orderId());
    }
}
```

This snippet only sketches the idea; in a real system, marking an event as processed and producing a side effect must be coordinated atomically or via an outbox/inbox. If you mark first and then sending the notification fails, retries will be skipped and the notification will be lost. If you send first and then marking fails, duplicate notifications may be sent. Use transactions/outbox, downstream idempotency, or sufficiently granular processing states.

With batch triggers, the adapter must return the exact list of failed records if the platform supports partial batch responses. If one record fails and the adapter throws an error for the whole batch, already-succeeded records may be redelivered and need to be idempotent.

## 9. Platform Context: Take Only What the Application Actually Needs

Runtimes often provide different contexts. Useful pieces of information include:

- Request/invocation ID for correlating logs and traces.
- Deadline or remaining time to bound downstream calls.
- Function name, version, region, or deployment metadata for diagnostics.
- Authenticated identity/claims if reliably provided by the trigger and gateway.
- Correlation ID, traceparent, or event ID for linking steps.
- Cancellation/interruption signal if supported by the runtime or library.

Do not pass the provider's entire context object into business services. Create a small internal context type containing only the necessary data:

```java
import java.time.Duration;

public record InvocationMetadata(
        String invocationId,
        String correlationId,
        String tenantId,
        Duration remainingTime
) {}
```

The adapter reads metadata from the platform context, verifies its origin, and constructs `InvocationMetadata`. `tenantId` must come from an authenticated identity/claim or a trusted mapping, never arbitrarily from a client-sent header. If the platform does not provide a deadline, the adapter can use a configured application timeout and leave a safety buffer.

When calling an HTTP client, database, or SDK, use the remaining time to set a timeout smaller than the function deadline. If the function has 800 ms left, do not start a downstream call that could wait 10 seconds. Not every runtime allows cleanly cancelling dependent work when an invocation ends; therefore, side effects still need idempotency.

## 10. Dependency Initialization and Runtime Lifecycle

A serverless runtime may reuse an execution environment across multiple invocations, though this is not guaranteed. Some objects can be created once at runtime startup and reused; other objects should be created per invocation.

| Resource type | Typically appropriate management approach |
| --- | --- |
| JSON mapper, validator, immutable config | Reuse if thread-safe |
| Thread-safe HTTP client/SDK client | Reuse across invocations when supported by the library and runtime |
| Connection pool | Use a small pool with health checks/timeouts and cap total concurrency |
| Request DTO, mutable state, security context | Create per invocation |
| Transaction, connection, stream, temporary file | Open and close within the scope of the operation; clean up properly |
| Business data needing to survive across invocations | Store in a database/object storage/workflow state |

A factory can be used to construct use cases and dependencies:

```java
public final class ApplicationFactory {
    private ApplicationFactory() {}

    public static PlaceOrderUseCase createPlaceOrderUseCase() {
        OrderRepository repository = createOrderRepository();
        OrderIdGenerator ids = new UuidOrderIdGenerator();
        return new PlaceOrderUseCase(repository, ids);
    }

    private static OrderRepository createOrderRepository() {
        // Create repository based on configuration and appropriate shared client.
        throw new UnsupportedOperationException("configure persistence adapter");
    }
}
```

The factory here serves as a placeholder illustrating the composition root. In a real application, you can use constructor injection with a DI framework, a hand-written factory, or a dependency injection mechanism supported by the platform. Do not open a new database connection per request if a safe pool/client can be used; nor keep a transaction or request state in a shared field.

Shared fields must be concurrency-safe. The runtime may process multiple requests concurrently depending on the platform and configuration. Avoid storing `currentUser`, the request body, or per-invocation mutable variables in `static` or shared instance fields.

## 11. Error Mapping and Trigger Semantics

The Java core should classify errors by business meaning and retryability. The adapter decides how to represent errors according to the protocol:

| Error from core | HTTP adapter | Queue/event adapter |
| --- | --- | --- |
| Invalid input | `400 Bad Request` | Usually non-retryable error; route to DLQ/quarantine per policy |
| Unauthenticated/insufficient permissions | `401`/`403` | Reject processing; check permission config and avoid infinite retries |
| Business resource does not exist | `404` or business code per contract | May be a non-retryable data error |
| Idempotency/state conflict | `409 Conflict` | May skip already-processed duplicate or escalate for investigation if unexpected conflict |
| Transient downstream failure | `502`/`503`/`504` depending on API | Bounded retries with backoff |
| Unexpected error | `500 Internal Server Error` | Retry per policy, then DLQ/alert |

Do not return stack traces, SQL, internal hostnames, or secrets to the client. Log details server-side with request ID and correlation ID. With HTTP, a 500 response can cause the client to retry; if the operation already produced side effects before failing, idempotency is needed. With queues, throwing an exception usually causes the message to be retried according to the event source policy; exact behavior depends on the platform.

Do not catch every exception and return an empty success result. Doing so causes the runtime to ACK the message or report the request as successful even though the business work did not complete. Distinguish between retryable errors, non-retryable errors, and idempotently already-processed results.

## 12. Testing the Core and Adapters

Separating the core and adapters makes it possible to split the testing strategy:

### Unit Tests for Plain Java

Unit tests invoke the use case directly, replacing the repository with a fake or mock. There is no need to start a cloud runtime or spin up an HTTP server.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseTest {
    @Test
    void createsOrderWhenRequestIsValid() {
        OrderRepository repository = new InMemoryOrderRepository();
        OrderIdGenerator ids = () -> "order-100";
        var useCase = new PlaceOrderUseCase(repository, ids);

        var request = new PlaceOrderRequest(
                "customer-1",
                java.util.List.of(new OrderLineRequest("book-1", 2)),
                "checkout-100");

        var result = useCase.execute(request);

        assertEquals("order-100", result.orderId());
        assertEquals("PLACED", result.status());
    }
}
```

`InMemoryOrderRepository` is a test fake. You should also add tests for invalid inputs, repeated idempotency keys, duplicate keys with different request hashes, repository failures, and concurrency. These tests verify business logic without depending on annotations or runtimes.

### Adapter Tests

Adapter tests verify:

- JSON bodies are deserialized properly and parse errors are mapped to 400.
- HTTP methods/paths/headers and response statuses/bodies match the contract.
- Identity and correlation ID are obtained from trusted sources.
- Message ID/event ID are passed intact to the handler.
- Transient errors are reported to the runtime for retry; non-retryable errors enter the appropriate handling path.
- Batch adapters report failures only for failed records when partial batch responses are supported.

### Local Integration and Cloud Tests

You can run Functions Framework or an emulator/local runtime to verify packaging, entry points, and bindings. Then use a cloud environment to test IAM permissions, timeouts, retries, concurrency, payload size, and observability. Unit tests do not prove the adapter is configured correctly in deployment; conversely, a successful deploy does not replace business logic tests.

## 13. Packaging and Entry Point Configuration

The runtime needs to know which class or function entry point to invoke, which dependencies must be included, and how to start the application. Configuration varies by platform:

- AWS Lambda Java typically packages a JAR (often a shaded/uber JAR or a ZIP containing dependencies depending on the runtime model) and configures the handler class/method according to Lambda conventions.
- Azure Functions Java uses a Maven/Gradle plugin and annotations/bindings to generate artifacts, function metadata, and host configuration.
- Google Cloud Functions Framework Java uses the framework dependency, a class implementing the appropriate interface, and a target entry point configured by the deployment environment.
- Container-based functions/runtimes can package a JAR alongside a base image and startup command; the platform invokes the function via the HTTP or event adapter exposed by the container.

Do not copy one provider's handler configuration to another provider. Check the JDK version supported by the runtime, target bytecode, dependency packaging, environment variables, memory/CPU, timeout, network access, and service permissions.

### Externalizing Configuration Outside Source Code

Move environment-specific values out to configuration:

- Table names, buckets, queues/topics, and downstream endpoints.
- Application timeouts, retry limits, and batch sizes.
- Feature flags, payload size limits, and retention.
- Log levels and tracing.

Secrets and credentials should be retrieved from a secret manager or equivalent secure mechanism, never committed to source control or written to logs. Each function should have its own identity/role with the minimum required permissions.

## 14. Java Frameworks: When Are They Needed and When Not?

Plain Java is sufficient for a small function with few dependencies, clear logic, and a simple adapter. A framework can help when you need routing, dependency injection, validation, serialization, observability, configuration, and multi-service integration.

| Implementation approach | Strengths | Considerations |
| --- | --- | --- |
| Plain Java + SDK adapter | Minimal abstraction, easy-to-understand runtime lifecycle, tight dependency control | Must organize DI, validation, error mapping, and configuration manually |
| Spring Cloud Function | Define function beans and adapters for multiple binding/runtime types | Requires understanding function catalog, binders, and startup/context cost |
| Quarkus | Geared toward startup/memory optimization and cloud/native integration | Must evaluate extensions, native compatibility, and build pipeline |
| Micronaut | Compile-time DI/AOP, which can reduce reflection/runtime overhead | Must check library compatibility and adapter configuration |
| Direct framework/provider SDK | Convenient integration with provider triggers and context | Increases coupling; changing providers may require writing a new adapter |

There is no single best framework for every function. Compare by cold start, warm latency, memory, artifact size, dependency count, JDK compatibility, build complexity, and support for the triggers you need. A framework that reduces startup time while increasing complexity or restricting libraries may not be the right choice.

## 15. Cold Start and Java Runtime Optimization

Cold start is the time it takes the platform to prepare a new execution environment before the function handles a request. For Java, initialization can include starting the JVM, class loading, initializing a DI container, reading configuration, creating SDK clients, and opening connections.

Several measures are commonly helpful:

1. Reduce unnecessary dependencies and avoid pulling in an entire framework when the function only needs a small handler.
2. Do not execute queries or call external services from static initializers unless necessary.
3. Create shared clients safely and defer initializing expensive resources until actually needed.
4. Choose frameworks and serialization libraries based on actual startup/memory measurements.
5. Benchmark both cold and warm invocations with memory/CPU configurations close to production.
6. Consider native images, snapshots, or provider fast-start features when beneficial and libraries are compatible.

Optimizing cold starts must not compromise correctness. A runtime may be reused, frozen, or recreated at any time; any data that must persist across invocations must be stored durably. Do not keep request-scoped state in singletons or assume shutdown hooks are always invoked.

## 16. Concurrency and Thread Safety

An execution environment may serve one or multiple concurrent invocations depending on the runtime, framework, and configuration. Even though platforms often isolate certain invocations, you should still assume shared objects can be accessed concurrently if allowed by the runtime/framework.

- Use immutable DTOs and stateless services whenever possible.
- Do not store current user data in shared fields.
- Only reuse clients documented as thread-safe.
- Use small connection pools; cap total concurrency according to database/downstream capacity.
- Set timeouts on all I/O and close resources with try-with-resources.
- Do not spawn background threads to continue work after the handler returns unless the platform guarantees that thread's lifecycle.
- For asynchronous work, enqueue tasks into a queue/workflow and let another invocation continue.

Java `static` does not mean persistent data. It only lives for the lifetime of the corresponding classloader/process and can be lost when the runtime is replaced. Likewise, do not treat a specific runtime instance as a singleton for the entire function: the platform can run multiple instances simultaneously.

## 17. Access Control and Authentication per Trigger

The adapter sits at the platform's security boundary, but business authorization must still be enforced inside the application.

- HTTP adapters verify tokens/identities from a trusted gateway or middleware, then pass the authenticated principal/tenant to the use case.
- Queue adapters verify that messages come from an authorized source via IAM/resource policies; the payload itself does not prove producer identity.
- Event adapters check `source`, `type`, schema, and signatures if required by the protocol.
- Scheduler adapters accept only schedules/metadata belonging to authorized configurations.
- Each function has permissions to read/write only the required queues, buckets, tables, or secrets.

Do not trust `tenantId`, `role`, `userId`, or permissions inside a JSON body unless verified against the authenticated identity. Do not log access tokens, secrets, presigned URLs, or full sensitive payloads.

## 18. Checklist for Building Portable Java Functions

- [ ] Application input/output contracts are independent of provider SDKs and request classes.
- [ ] Business logic resides in plain Java use cases/services and receives dependencies via constructors/interfaces.
- [ ] Adapters only perform deserialization, protocol validation, context mapping, and response/ACK mapping.
- [ ] HTTP, queue, event, and scheduler triggers have separate adapters/semantics.
- [ ] Context is converted into minimal internal metadata; the domain does not depend on provider context.
- [ ] Business errors, input errors, and infrastructure errors are classified and mapped accurately to the protocol.
- [ ] Side effects are idempotent; batches support partial failure when the trigger supports it.
- [ ] Clients/connection pools are managed according to lifecycle and thread safety.
- [ ] No business state is kept in heap/static memory or background threads after the handler returns.
- [ ] Entry point, JDK, dependency packaging, memory, timeout, and environment are configured correctly for the provider.
- [ ] IAM/identity follows least privilege; tenant and principal come from authenticated sources.
- [ ] Unit tests exist for the core, along with adapter tests and integration tests on an appropriate runtime/emulator.
- [ ] Cold start, warm latency, memory, concurrency, and cost have been measured under representative load.

Plain Java keeps business logic independent of the platform; adapters translate triggers and runtime contracts into calls that the application core understands. When this boundary is clearly designed, the same use case can be invoked from HTTP, queues, or events, tested quickly locally, and deployed across multiple runtimes without rewriting business rules. Function quality depends on contracts, lifecycle, error semantics, security, and deployment configuration, not just on the main handler method.
