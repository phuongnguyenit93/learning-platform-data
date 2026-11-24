# Returning Asynchronous Results with Spring-Supported Types

In a STOMP application, a method annotated with `@MessageMapping` receives a message from a client and can return a payload. If processing requires calling an external service, querying data, or performing time-consuming work, the method can return an asynchronous type recognized by Spring Messaging. Spring waits for the result to complete before converting the payload into a message sent to the broker.

The key point is that the return type must conform to the contract supported by the Spring Messaging version in use. For STOMP annotated controllers, Spring documentation lists `ListenableFuture`, `CompletableFuture`, and `CompletionStage`. Since Spring Framework 6.0, support for `ListenableFuture` has been deprecated in favor of `CompletableFuture`. Therefore, new code should prefer `CompletableFuture` or expose the `CompletionStage` abstraction.

## 1. Processing Flow

A synchronous method must finish its work before returning a payload. With an asynchronous type, the method creates or obtains a future/stage, returns that object to Spring, and the work finishes at a later time.

1. The client sends a STOMP `SEND` to an application destination, such as `/app/quotes.lookup`.
2. Spring routes the message to the `@MessageMapping("/quotes.lookup")` method.
3. The method returns `CompletionStage<QuoteResult>` without blocking for the work to complete.
4. When the stage completes successfully, Spring extracts the payload, converts it using a `MessageConverter`, and sends the message over `brokerChannel`.
5. The broker delivers the message to clients subscribed to the output destination.

```mermaid
flowchart LR
    A["Client sends SEND /app/quotes.lookup"] --> B["clientInboundChannel"]
    B --> C["@MessageMapping"]
    C --> D["CompletionStage processing"]
    D -->|"Completed"| E["MessageConverter"]
    E --> F["brokerChannel"]
    F --> G["Client subscribed to /topic/quotes"]
```

The return value is still the payload of a STOMP message. The client does not receive an HTTP response, nor is the SEND connection blocked until the work completes. Clients should subscribe to the output destination before sending the request.

## 2. Supported Return Types

| Return Type | Usage | Notes |
|---|---|---|
| `CompletableFuture<T>` | Suitable for new code that creates and composes async tasks | JDK type; provides chaining methods such as `thenApply`, `thenCompose`, and error handling |
| `CompletionStage<T>` | Suitable when exposing an async contract without tying callers to a concrete implementation | Spring adapts the stage to `CompletableFuture` for further handling |
| `ListenableFuture<T>` | Primarily for maintaining legacy integrations | Spring type deprecated since Framework 6.0; prefer migrating to `CompletableFuture` |

Do not assume that every type with “Future” in its name is supported. The STOMP annotated controllers documentation explicitly specifies the types in the table above. Return types from other mechanisms, such as Spring MVC's `DeferredResult` or `Callable`, have their own contracts. Likewise, do not assume WebFlux reactive return types apply to STOMP controllers by default.

If a service or client library already returns `CompletionStage<T>`, you can return that stage directly or compose it using `CompletionStage` operators. Avoid wrapping one stage inside another; use `thenCompose` when the next step also returns a stage.

## 3. Example with Spring Framework and Java 17+

The following example receives a quote lookup request, executes the work on a dedicated executor, and broadcasts the result to `/topic/quotes`. Prices in the example are illustrative data.

### STOMP and Executor Configuration

`WebSocketConfig.java`:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Bean("stompTaskExecutor")
    public ThreadPoolTaskExecutor stompTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("stomp-work-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        return executor;
    }
}
```

The executor has a bounded number of threads and queue capacity to limit concurrent work. These numbers are illustrative only; applications must tune them based on processing time, resources, and real load.

### Data Transfer DTOs

Place each public record in its own file:

`QuoteRequest.java`:

```java
public record QuoteRequest(String symbol) {}
```

`QuoteResult.java`:

```java
public record QuoteResult(
        String symbol,
        BigDecimal price,
        Instant quotedAt
) {}
```

`ErrorMessage.java`:

```java
public record ErrorMessage(String code, String message) {}
```

### Service Returning CompletionStage

`QuoteService.java`:

```java
@Service
public class QuoteService {

    private final Executor executor;

    public QuoteService(
            @Qualifier("stompTaskExecutor") Executor executor
    ) {
        this.executor = executor;
    }

    public CompletionStage<QuoteResult> findQuote(QuoteRequest request) {
        return CompletableFuture.supplyAsync(() -> {
            if (request == null
                    || request.symbol() == null
                    || request.symbol().isBlank()) {
                throw new IllegalArgumentException("symbol is required");
            }

            String symbol = request.symbol()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            // Hardcoded sample data for illustration; replace with real service/repository calls.
            return new QuoteResult(
                    symbol,
                    new BigDecimal("123.45"),
                    Instant.now()
            );
        }, executor);
    }
}
```

`supplyAsync` submits the task to the executor and returns a `CompletableFuture` immediately. That value can be returned directly because `CompletableFuture` implements `CompletionStage`. In a real application, the task body can call a repository or an external client.

### STOMP Controller

`QuoteController.java`:

```java
@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("/quotes.lookup")
    @SendTo("/topic/quotes")
    public CompletionStage<QuoteResult> lookup(QuoteRequest request) {
        return quoteService.findQuote(request);
    }

    @MessageExceptionHandler
    @SendToUser("/queue/errors")
    public ErrorMessage handleFailure(Exception exception) {
        // Do not send stack traces or internal details to the client.
        return new ErrorMessage(
                "PROCESSING_FAILED",
                "Unable to process the quote request."
        );
    }
}
```

With the configuration above:

- Clients send a JSON payload to `/app/quotes.lookup`.
- Clients subscribe to `/topic/quotes` to receive the result.
- Processing failures are converted into a private payload sent to the user via `/queue/errors`.
- `@SendTo` broadcasts the result to the specified destination. If the annotation is omitted, Spring uses the default destination according to STOMP annotated controller rules.
- Use `@SendToUser` for data meant only for the sender; avoid publishing private data to a shared topic.

## 4. Composing Asynchronous Tasks

When a service already returns a stage, do not spawn an extra thread just to wrap it. You can transform the result with `thenApply`:

```java
public CompletionStage<QuoteResult> findQuote(String symbol) {
    return marketClient.fetchQuote(symbol)
            .thenApply(this::toQuoteResult);
}
```

If the next step also returns a stage, use `thenCompose` to flatten the async chain:

```java
public CompletionStage<QuoteResult> findQuote(String accountId) {
    return accountService.find(accountId)
            .thenCompose(account ->
                    marketClient.fetchQuote(account.symbol()))
            .thenApply(this::toQuoteResult);
}
```

The two examples above assume the corresponding data types and client methods already exist. `thenApply` transforms an available result; `thenCompose` chains another step that returns a stage. Do not call `get()` or `join()` directly inside the controller to wait for the result, as doing so blocks the message-handling thread and defeats the purpose of returning asynchronously.

## 5. Choosing an Executor Properly

When calling `CompletableFuture.supplyAsync(task)` without passing an executor, Java uses the common ForkJoinPool. This may suit some short CPU tasks, but it should not be used by default for blocking work such as JDBC, synchronous HTTP calls, or file I/O.

- For blocking work, use an executor with bounded threads and queue capacity; set timeouts on underlying calls.
- For CPU-bound work, size the pool based on core count and processing time; avoid creating a thread per message.
- When a continuation must run asynchronously on a chosen pool, use the `thenApplyAsync(fn, executor)` or `thenComposeAsync(fn, executor)` forms.
- `thenApply` does not create a new thread on its own; the continuation usually runs on the thread that completed the previous stage or the thread registering the continuation if the stage is already complete.
- Monitor queue wait time, processing duration, active task count, and task rejections. A full queue should be handled as overload rather than switching to an unbounded queue.

Returning a `CompletableFuture` does not automatically turn a blocking call into a non-blocking one. If the inner task makes a synchronous JDBC call, an executor thread remains occupied until the query finishes. The benefit is that the thread receiving STOMP messages remains free to handle other messages.

## 6. Error Handling and Timeouts

A stage can complete normally or exceptionally. You can handle errors in the service with `exceptionally` or `handle` if you want to turn an error into a business result. If you let the error propagate, Spring Messaging routes the asynchronous completion error through the message handler's exception-handling mechanism; `@MessageExceptionHandler` or `@ControllerAdvice` can produce an appropriate error payload.

Distinguish two cases:

- **Business errors:** such as an invalid request code or a missing record. Return a stable error code and a message safe to display to the client.
- **Infrastructure errors:** such as timeouts, unresponsive external services, or executor task rejections. Log with a correlation ID, return a generic message to the client, and keep technical details on the server.

You can set a time limit on a future, for example using `orTimeout` on `CompletableFuture` in Java 17. A timeout on the future only completes the future with an error; it does not guarantee cancellation of a JDBC query or an HTTP request already sent to an external system. To actually stop the underlying work, the underlying client must support timeouts or cancellation.

## 7. Destinations, Security, and Request Correlation

`@SendTo("/topic/quotes")` sends results to a topic that multiple subscribers can receive together. This is appropriate for public data or shared events. For sender-private data, use `@SendToUser` or private routing with access control checks.

STOMP does not automatically establish an application-level request-response relationship just because a controller returns a future. When a client sends multiple concurrent requests, results may complete in a different order than they were sent. If results must be matched to requests, include a `requestId` or correlation ID in both request and response. Never use a shared mutable field in the controller to store the “current request”.

Always verify access permissions and validate input data before executing work. Never include exception messages, SQL, tokens, account data, or stack traces in payloads sent to clients.

## 8. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `future.join()` or `get()` inside `@MessageMapping` | The message-receiving thread blocks; processing becomes synchronous again | Return the future/stage directly |
| Using `supplyAsync` without an executor for blocking tasks | Tasks contend over the common pool and load is hard to control | Pass a bounded executor |
| Using `ListenableFuture` in new code | Relies on an API deprecated since Spring 6.0 | Choose `CompletableFuture` or `CompletionStage` |
| Assuming every `Future<T>` is supported | The handler may not accept that return type | Check the list documented for your exact version |
| Using `@SendTo` for private data | Every subscriber on the topic can receive the data | Use user destinations and check permissions |
| Omitting a correlation ID under concurrent requests | Client struggles to correlate responses with requests | Pass an ID via payload or headers |
| Omitting timeouts and executor bounds | Hung tasks or overload exhausts resources | Configure timeouts, bounded queues, and monitor rejections |

## 9. How to Test

When testing an asynchronous STOMP endpoint, verify the following behaviors:

1. The client subscribes to the output destination before sending the request.
2. The controller method returns the stage without calling `get()` or `join()`.
3. When the stage completes normally, the client receives the properly serialized payload at the `@SendTo` destination.
4. When the stage completes exceptionally, the exception handler produces an error payload matching the defined contract.
5. Send multiple concurrent requests and confirm correlation IDs still match results accurately.
6. Simulate slow tasks and a full executor to verify timeouts, logging, and overload behavior.
7. Verify private messages reach only the intended user and are not broadcast on a shared topic.

## 10. Version Compatibility Notes

Spring Framework documentation for STOMP annotated controllers lists `ListenableFuture`, `CompletableFuture`, and `CompletionStage` as supported asynchronous return types. Spring Framework 6.1 Javadoc describes `CompletableFutureReturnValueHandler` as supporting both `CompletableFuture` and `CompletionStage`; the `ListenableFuture` API has been marked deprecated since 6.0.

When upgrading Spring Boot or overriding dependencies, check the actual version of the `spring-messaging` artifact resolved by Gradle. Do not rely solely on versions mentioned in older docs or online examples. Spring Framework's contract and the Java types compiled by your project must match the same version.

## References

- [Spring Framework — Annotated Controllers (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework 6.1 — AsyncHandlerMethodReturnValueHandler](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/invocation/AsyncHandlerMethodReturnValueHandler.html)
- [Spring Framework 6.1 — CompletableFutureReturnValueHandler](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/invocation/CompletableFutureReturnValueHandler.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
