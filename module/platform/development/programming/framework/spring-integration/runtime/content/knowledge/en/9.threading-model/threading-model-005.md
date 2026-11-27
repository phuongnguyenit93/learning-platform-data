# Thread Context, MDC, and Propagation

In Spring Integration, a message can pass through multiple channels and endpoints, yet not every step runs on the same thread. When a flow transitions from `DirectChannel` to `ExecutorChannel`, from a producer to a poller, or through another executor, data bound to the current thread—such as MDC, `ThreadLocal`, security context, or request context—may no longer be present in the next step.

Message headers travel with the message; thread context travels with the thread. This is an important distinction when connecting logs, traces, and business metadata across asynchronous boundaries. For reliable propagation, determine which data belongs to the message and which belongs to the thread, then choose the appropriate propagation mechanism for each.

## 1. What Is Thread Context?

Thread context is state stored in association with the currently executing thread. In Java, many frameworks use `ThreadLocal` to hold this state without passing parameters through every method.

Common examples:

| Context | Purpose | Typical mechanism |
|---|---|---|
| SLF4J MDC | Attach correlation ID, tenant ID, or request details to logs | `MDC` backed by thread-local state |
| Spring Security | Hold the request's `SecurityContext` and principal | `SecurityContextHolder` defaults to a thread-local strategy |
| Spring transactions | Hold the active transaction/resources on the current thread | Thread-bound transaction synchronization and resource binding |
| Locale/request context | Hold locale or request metadata during synchronous processing | `LocaleContextHolder`, `RequestContextHolder` |
| Tracing context | Link the current span to logs and downstream calls | Micrometer Tracing/OpenTelemetry context and propagation |

Thread-locals make synchronous code convenient, but they do not automatically become message data. When a task runs on another worker thread, the worker has its own thread-locals. Java does not automatically copy all context from the sending thread to the receiving thread.

Do not treat all thread contexts as the same kind of data. A business correlation ID can live in a message header; MDC is a way to expose certain values in logs; a transaction is resource-management state; security context represents identity and authorities. They have different lifecycle and security requirements.

## 2. Thread Boundaries in Spring Integration

The channel type and how an endpoint is triggered determine where the thread changes.

| Component | Typical thread behavior | Impact on context |
|---|---|---|
| `DirectChannel` | Invokes subscriber on the message-sending thread | Current MDC and ThreadLocal values are usually still visible during synchronous calls |
| `ExecutorChannel` | Hands processing off to a `TaskExecutor` | Different worker thread; context requires explicit propagation |
| `QueueChannel` | Producer enqueues, polling consumer receives later | Consumer runs on the poller thread; producer context does not travel through the queue automatically |
| `PublishSubscribeChannel` without executor | Subscribers typically run synchronously on the sending thread | Context remains in the same call path, depending on subscribers |
| `PublishSubscribeChannel` with executor | Subscribers are dispatched asynchronously | Each worker needs context propagation |
| Polling endpoint | Poller receives messages on scheduler thread or poller executor | Context from the thread that sent to the queue is not automatically present on the poller |

Illustrative diagram:

~~~mermaid
flowchart LR
    A[HTTP request thread<br/>MDC + SecurityContext] --> B[DirectChannel]
    B --> C[Transformer]
    C --> D[ExecutorChannel]
    D --> E[Worker thread<br/>new context]
    E --> F[Service Activator]
    F --> G[Remote service]
~~~

From A to C, code normally runs on the same thread. When the message crosses `ExecutorChannel`, the task executes on worker thread E. Message headers still follow the message if preserved, but thread A's MDC, `SecurityContextHolder`, or `LocaleContextHolder` do not automatically appear on E.

`QueueChannel` creates a similar boundary across time: the producer puts the message into the queue and finishes; a poller retrieves the message later. Message headers can be preserved in the queue, while the producer's thread context has already ended or been reused for another request.

Using a channel does not imply asynchronous execution. `DirectChannel` is typically synchronous; `ExecutorChannel` actively moves processing to an executor. Likewise, endpoints inside the same `IntegrationFlow` do not automatically share one thread. Inspect the actual channels, pollers, executors, and adapters between two steps.

## 3. Message Headers and MDC Have Different Roles

Information that must follow a message across multiple channels should be placed in message headers or payload according to the business contract. MDC is only a way to attach queryable fields to logs emitted on the current thread.

Example of a producer setting a correlation ID in a message header:

~~~java
Message<Order> message = MessageBuilder.withPayload(order)
        .setHeader("correlationId", correlationId)
        .build();

ordersInputChannel.send(message);
~~~

At a downstream endpoint, read the correlation ID from the message and populate the log context for the scope of processing:

~~~java
public void handle(Message<Order> message) {
    String correlationId = message.getHeaders()
            .get("correlationId", String.class);

    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
        log.info("Processing order messageId={}",
                message.getHeaders().getId());
        orderService.process(message.getPayload());
    }
}
~~~

`MDC.putCloseable` clears the entry after the block. If using the standard MDC API, place `MDC.remove(...)` in `finally`. Never leave the previous message's correlation ID on a worker thread where the next message might accidentally log with the wrong ID.

If a transformer creates a new message, verify that required headers are preserved. With `MessageBuilder`, you can use `copyHeadersIfAbsent(...)` to retain metadata from the source message while adding new headers. Some adapters or protocols only transmit headers configured in a header mapper; do not assume every internal header crosses a broker or HTTP boundary.

Message headers are the data source linking messages and business logic. MDC is a temporary projection of selected fields into logs. Do not read from MDC to make business decisions when message headers or domain data are the source of truth.

## 4. Why Does MDC Get Lost or Leak?

MDC is typically implemented using a thread-local map. When a request starts on thread A, the application puts `correlationId` into MDC. If processing continues synchronously, subsequent logs on thread A see that value. When a task is submitted to thread B, thread B does not automatically receive A's map.

Thread pools introduce another issue: worker threads are reused. If a task sets MDC without removing it, the next task can see stale values. This bug is dangerous because logs remain syntactically valid while being tagged with the wrong request or tenant.

Unsafe example:

~~~java
public void process(Message<?> message) {
    MDC.put("correlationId", correlationId(message));
    service.process(message);
    // Without remove in finally, the worker can retain the value.
}
~~~

Safe example in synchronous processing:

~~~java
public void process(Message<?> message) {
    String correlationId = correlationId(message);
    try {
        MDC.put("correlationId", correlationId);
        service.process(message);
    }
    finally {
        MDC.remove("correlationId");
    }
}
~~~

If blocks can nest or need to preserve an earlier context, save the old map and restore it in `finally`, or use `MDC.putCloseable` when appropriate. Avoid calling `MDC.clear()` indiscriminately if framework-managed keys exist on the same thread; define clear ownership of keys.

## 5. Propagating MDC Across TaskExecutor Using TaskDecorator

Spring Framework provides `TaskDecorator` to wrap a `Runnable` before the executor runs it. This is the right place to capture context on the submitting thread and reinstall it on the worker thread.

Example decorator that copies only MDC:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> callerContext = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext = MDC.getCopyOfContextMap();
            try {
                if (callerContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(callerContext);
                }

                task.run();
            }
            finally {
                if (previousContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Attach the decorator to the executor:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("integration-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}

@Bean
MessageChannel asyncOrdersChannel(TaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
~~~

The decorator captures the map when the task is submitted, sets that map on the worker, and restores the worker's prior context after the task finishes. The restore step is crucial because workers are reused. This example only propagates MDC; it does not copy transactions, security context, or any other `ThreadLocal`.

If an executor receives tasks from multiple sources, only truly necessary keys should be placed in MDC. Avoid copying large payloads, tokens, or sensitive information. When handling nested tasks, clarify which context is inherited and which must be replaced.

## 6. Micrometer Context Propagation

When an application needs to propagate multiple context types, writing custom decorators for every `ThreadLocal` is error-prone. Micrometer Context Propagation provides an abstraction to capture context at submission time and restore context within the task's scope.

In Spring Framework 6.1+, you can use `ContextPropagatingTaskDecorator`:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("integration-worker-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

This decorator uses `ContextSnapshot` and `ThreadLocalAccessor` instances registered in `ContextRegistry` to capture and restore context. Micrometer Context Propagation must be on the classpath along with the corresponding accessors for the contexts you want to propagate. Simply setting the decorator does not automatically discover every custom `ThreadLocal` in the application.

For a custom application `ThreadLocal`, register an accessor describing how to get, set, and reset the value. Ensure the reset operation clears the value when the snapshot does not contain that key. Otherwise, a value from a previous task can remain on the worker.

Context propagation incurs capture and restore overhead. Enable it only on the executors and contexts that need it. With very high volumes of tiny tasks, measure overhead before applying globally.

## 7. Tracing Context Differs from MDC

MDC is primarily for logging. Distributed tracing requires more than a `traceId` string: it manages the current trace/span, parent-child relationships, sampling, and propagation across process boundaries.

In the modern Spring ecosystem, Micrometer Observation and Micrometer Tracing provide instrumentation and propagation for supported contexts. When crossing an executor, use context propagation integrated with observation/tracing so the active span continues properly. When crossing HTTP or a broker, use a standard propagator such as W3C Trace Context and configure the corresponding header mapper/protocol.

Do not invent a custom `traceId` header and treat it as complete distributed tracing. Likewise, do not use a business Correlation ID as a replacement for a Trace ID. An order may keep the same Correlation ID across many requests, whereas each processing attempt may create a distinct trace.

| Value | Scope | Used for |
|---|---|---|
| Message ID | Single message | Finding a specific message delivery |
| Correlation ID | Business operation or group of messages | Grouping child messages, replies, or steps of the same business flow |
| Trace ID | Distributed trace | Linking spans across threads and services |
| Span ID | Single operation within a trace | Identifying a processing segment and parent-child relationship |

When logging, trace/span IDs can be exposed in MDC for easier querying, but let the tracing library manage the context and lifecycle. Avoid manually setting or clearing keys owned by tracing instrumentation.

## 8. SecurityContext and Transactions Cannot Be Copied Like MDC

### SecurityContext

Spring Security stores `SecurityContext` in `SecurityContextHolder` per thread by default. When running asynchronous tasks under the caller's identity, use Spring Security's mechanisms such as `DelegatingSecurityContextAsyncTaskExecutor` or the corresponding wrapper instead of merely copying MDC.

Example:

~~~java
@Bean
AsyncTaskExecutor securedExecutor(ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
~~~

Propagating security context should follow the principle of least privilege. Do not retain a request's context longer than necessary; if a task is queued and processed later, consider carrying an authenticated user/actor identifier in the message per security policy and enforcing authorization at processing time.

### Transaction Context

Spring transactions are typically bound to the current thread and resources. When a message crosses an `ExecutorChannel` or poller executor, the sending thread's transaction does not automatically move to the worker. Never copy an `EntityManager`, JDBC connection, or transaction resource into a worker's MDC/ThreadLocal.

If the worker needs a transaction, start a new transaction on the service invoked by the worker using `@Transactional` through a Spring proxy, or configure appropriate transaction advice/poller settings. With a message broker and database, design transactions/acknowledgments according to the real capabilities of each resource. Context propagation does not merge two transactions into a single distributed transaction.

### Request and Locale Context

`RequestContextHolder` and request objects are tied to the HTTP request lifecycle. Do not hold onto `HttpServletRequest` or session objects for processing after the request completes. Pass only necessary, immutable, validated values into message headers or command objects. Locale can be propagated if business logic must format according to the user's locale, but clarify whether locale comes from the request or tenant configuration.

## 9. Propagation Across Spring Integration Channels and Adapters

For propagation to work reliably, check both sides of every boundary:

1. **Does the channel switch threads?** If so, the executor needs an appropriate decorator or context propagation.
2. **Are message headers preserved?** Transformers, filters, routers, and adapters can create new messages or filter headers.
3. **Is there a process boundary?** ThreadLocal values do not cross brokers/HTTP; serialize metadata into headers and restore context on the receiving side.
4. **Is context cleaned up?** The worker must return to a clean state after each task.

Example flow with an executor boundary:

~~~java
@Bean
IntegrationFlow orderFlow(MessageChannel asyncOrdersChannel,
                          OrderService orderService) {
    return IntegrationFlow.from("orders.input")
            .channel(asyncOrdersChannel)
            .handle(orderService, "process")
            .get();
}
~~~

If `asyncOrdersChannel` is an `ExecutorChannel`, the endpoint processing after the channel runs on a worker. The correlation ID should still be present in a message header. The executor's decorator ensures the required logging/tracing context is available on the worker while the task executes.

For broker adapters, inspect `DefaultHeaderMapper` or the corresponding header mapper to see which headers are sent and received. Do not propagate all internal headers indiscriminately: some headers contain non-serializable objects or sensitive data. Whitelist only necessary metadata, such as business correlation IDs or standard trace contexts.

## 10. Testing Context Propagation

Propagation tests should prove both conditions: the task receives the submitted context, and the worker does not retain that context after the task completes.

A test can use a single-worker executor to force two tasks to reuse the same thread:

~~~java
@Test
void propagatesMdcAndDoesNotLeakBetweenTasks() throws Exception {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(10);
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();

    try {
        MDC.put("correlationId", "request-A");
        Future<String> first = executor.submit(
                () -> MDC.get("correlationId"));
        MDC.clear();

        assertEquals("request-A", first.get());

        Future<String> second = executor.submit(
                () -> MDC.get("correlationId"));
        assertNull(second.get());
    }
    finally {
        executor.shutdown();
        MDC.clear();
    }
}
~~~

The illustrative test verifies the snapshot at submission time and confirms that the next task does not accidentally inherit the previous task's context. In real tests, use `try/finally` to clean MDC on the test thread too, specify timeouts on `Future.get(...)`, and ensure executor shutdown even when assertions fail.

Additional cases to test:

- Tasks running synchronously and asynchronously for the same message.
- An exception thrown inside the worker while MDC is still cleaned up.
- Two messages with different correlation IDs running consecutively on the same worker.
- A message passing through a transformer that creates a new message while preserving required headers.
- Context propagated across broker/HTTP via header mappers and trace propagators.
- Security context propagated with the appropriate executor wrapper without leaking the principal to the next task.
- Transactions on the worker matching expected boundaries, independent of the sending thread.

## 11. Diagnosing Lost or Corrupted Context

| Symptom | Possible cause | What to check |
|---|---|---|
| Logs after `ExecutorChannel` lack correlation ID | MDC was not propagated | Check TaskDecorator on the exact executor used by the channel |
| Logs show another request's correlation ID | Worker thread leaked MDC or decorator did not restore/clear | Check `finally`, task reuse, and context snapshot |
| Message header has ID but MDC is empty | Header exists, but nothing copies the header into MDC | Populate MDC in a handler/interceptor or use an appropriate accessor |
| Trace splits into a new root span | Trace context was not captured/propagated | Check Micrometer Observation/Tracing, executor decorator, and propagator |
| Principal is lost after async boundary | SecurityContext was not propagated | Use `DelegatingSecurityContextAsyncTaskExecutor` or equivalent mechanism |
| Worker does not join producer's transaction | Thread-bound transaction | Open a new transaction on the worker or redesign transaction boundaries |
| Old context remains after failed message | Cleanup is not inside `finally` | Restore/clear context even when an exception occurs |

When investigating, log thread name, channel/endpoint name, message ID, and Correlation ID. Compare logs before and after each thread transition point to see which boundary drops the context. Do not add global propagation before knowing which context is missing and which executor is actually being used.

## 12. Context Propagation Design Checklist

- [ ] Mark every thread-switching boundary in the IntegrationFlow.
- [ ] Store business data that must travel with the message in headers or payload.
- [ ] Use MDC strictly as logging context and always clean up/restore it.
- [ ] Attach `TaskDecorator` to the exact executor used by `ExecutorChannel` or pollers.
- [ ] Use Micrometer Context Propagation when multiple supported contexts are needed.
- [ ] Use Spring Security's dedicated mechanisms for `SecurityContext`.
- [ ] Open appropriate transactions on the worker; never attempt to copy transaction resources.
- [ ] Verify header mappers when crossing brokers or HTTP.
- [ ] Never pass tokens, request objects, or sensitive payloads solely for logging convenience.
- [ ] Test lost context, leaked context, and failing tasks on reused thread pools.

Thread context makes accessing data convenient in synchronous code, but it does not replace message metadata and does not automatically cross executors. By using message headers for business data, decorators or context propagation for thread-bound data, and explicit lifecycle cleanup, logs and traces stay accurately linked across Spring Integration's asynchronous boundaries.

## References

- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API: TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework API: ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Spring Security Reference: Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
