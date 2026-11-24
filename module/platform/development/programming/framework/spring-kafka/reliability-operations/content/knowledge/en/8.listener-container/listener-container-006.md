# Consumer thread naming

In Spring Kafka, consumer thread naming is the practice of giving recognizable names to threads running Kafka consumers and listener containers. Thread names appear in thread dumps, logs, tracing, and JVM monitoring tools. When an application runs multiple listeners, concurrent consumers, or multiple replicas, clear thread names help identify which thread is polling Kafka, which thread is processing records, and which thread is waiting on resources.

A thread name is JVM diagnostic metadata. It does not determine which group a consumer belongs to, does not select partitions, and does not replace the Kafka client ID. To read production telemetry accurately, distinguish container name, consumer group ID, client ID, and thread name.

## 1. Which thread runs the consumer?

Kafka consumers are not thread-safe. A `KafkaConsumer` must be used sequentially by its managing thread, especially for operations such as poll, subscribe, commit, and close. The Spring Kafka listener container manages the consumer lifecycle and the thread executing the poll loop.

With a standard listener container, the processing flow looks roughly like this:

~~~text
Spring application
       |
       v
KafkaListenerEndpointRegistry
       |
       v
Listener container
       |
       v
Consumer task / consumer thread
       |
       +---- KafkaConsumer.poll()
       |
       +---- receive records from broker
       |
       +---- invoke listener
       |
       +---- manage acknowledgement / commit
       |
       +---- continue polling
~~~

In typical synchronous listener setups, the listener is invoked on the consumer's execution thread. When the application offloads work to a separate executor, calls async APIs, or uses another processing model, additional application- or framework-managed threads may appear. Those threads follow their own naming rules and are not necessarily consumer threads.

Types of threads that may appear in a Spring Kafka application:

| Thread type | Responsibility | Typical naming source |
|---|---|---|
| Consumer thread | Polls Kafka, manages consumer, and invokes listener synchronously | Listener container executor or consumer thread renaming configuration |
| Application worker thread | Processes work offloaded to a separate executor | `ThreadFactory` or prefix of the application-configured executor |
| Scheduler thread | Runs periodic jobs, health checks, or internal tasks | Scheduler configured for the container or application |
| Web request thread | Handles HTTP requests if the application has a web layer | Web server and web server executor |

Do not assume every thread with `kafka` in its name is a consumer thread. Cross-check names against containers, client IDs, stack traces, and application logs.

## 2. Default listener container thread names

Spring Kafka creates a consumer task for each consumer managed by a listener container. When no custom executor is configured, the container uses its default executor. Default thread names are usually constructed from the bean/container name and a suffix to distinguish consumers or child containers.

For a single listener, the name might look roughly like:

~~~text
ordersListener-C-1
~~~

For containers with concurrency greater than one, child containers may include an additional index in the name, for example:

~~~text
ordersListener-0-C-1
ordersListener-1-C-1
ordersListener-2-C-1
~~~

These are illustrative examples of common naming shapes, not a guaranteed format across all Spring Kafka versions. Suffixes and numbering depend on container type, bean name, executor, and framework version.

The container-linked portion helps identify which listener is running. The suffix helps distinguish consumer tasks. When changing executors or enabling thread renaming, actual names may differ from the examples above.

### Naming listeners clearly

For annotation-declared listeners, setting a meaningful `id` helps identify the endpoint/container in Spring:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

In the example:

- `id` identifies the listener endpoint/container in Spring Kafka.
- `groupId` specifies the consumer group the listener joins.
- `clientIdPrefix` sets the Kafka client ID prefix for the consumer; Kafka client ID is used in Kafka-side metrics and logs.
- Thread name is managed by the container/executor and may use the container name as part of its prefix.

The three attributes `id`, `groupId`, and `clientIdPrefix` serve different purposes. Setting `id = ordersListener` does not mean group ID or client ID automatically share that value in all configurations. Declare group ID and client ID explicitly when clear observability is needed.

## 3. How does concurrency affect thread count?

`ConcurrentMessageListenerContainer` can create multiple child `KafkaMessageListenerContainer` instances. Each child manages one `KafkaConsumer` and one consumer task. Therefore, increasing concurrency usually increases the listener's consumer thread count.

Factory configuration example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

With concurrency 3, the container manages three consumer tasks for this listener. If the application runs two replicas and each replica has concurrency 3, the group can have six consumer members in total for that listener.

Thread count does not equal partition count. If a topic has two partitions, at most two consumers in the same group can own partitions of that topic in steady-state assignment; the remaining consumers have no partitions to read. If the topic has ten partitions and six consumers, some consumers may receive multiple partitions.

In Spring Boot, you can configure default concurrency for listener containers:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

This value applies to listener containers configured via auto-configuration, unless a listener or factory has its own concurrency configuration. Check the effective configuration of each listener when an application has multiple factories.

When inspecting thread dumps, combine thread names with assigned partition counts and client IDs. Do not merely count threads and conclude that the system has that many consumers actively processing records.

## 4. Distinguishing thread name, listener ID, group ID, and client ID

These identifiers often appear together in logs, yet they are not interchangeable:

| Identifier | Example | Purpose |
|---|---|---|
| Listener ID | `ordersListener` | Identifies endpoint/container in Spring Kafka |
| Consumer group ID | `orders-service` | Identifies consumer group sharing assignments and offsets |
| Kafka client ID | `orders-consumer-0` | Identifies client in Kafka metrics and logs |
| Thread name | `ordersListener-0-C-1` | Identifies execution thread in JVM and thread dumps |
| Application instance ID | `orders-pod-2` | Identifies application replica or instance |

One group can have many client IDs. One client runs on one consumer thread at a time. When a listener uses concurrency, each child consumer can get a distinct client ID built from a prefix and suffix.

Example setting `clientIdPrefix`:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

The Kafka client may append a suffix to distinguish consumers created from the same prefix in a concurrent container. Actual client ID names depend on how Spring Kafka creates consumers and `client.id` configuration.

`client.id` is useful when viewing JMX metrics or broker logs, whereas thread name is useful when inspecting JVM thread dumps. When the two can be correlated, finding the consumer causing lag or blocking becomes much faster.

## 5. Customizing thread names with a consumer task executor

Container properties allow configuring the executor that runs consumer tasks. A simple approach is using `SimpleAsyncTaskExecutor` with a custom thread name prefix:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var consumerExecutor =
            new SimpleAsyncTaskExecutor("orders-consumer-");
    factory.getContainerProperties()
            .setConsumerTaskExecutor(consumerExecutor);

    return factory;
}
~~~

With prefix `orders-consumer-`, threads created by the executor are named `orders-consumer-1`, `orders-consumer-2`, and continue incrementing via the executor's counter. Exact names also depend on the executor and task-creation lifecycle.

A dedicated executor is useful when:

- The application has multiple listeners and threads need to be distinguished by business stream.
- Thread dumps should immediately show which listener is running.
- You want consistent executor and prefix management rather than relying on defaults.
- You need to apply limits or observe executors per listener group.

### Using ThreadPoolTaskExecutor

You can use `ThreadPoolTaskExecutor` when you want pool and lifecycle control:

~~~java
@Bean
ThreadPoolTaskExecutor ordersConsumerExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("orders-consumer-");
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(3);
    executor.setQueueCapacity(0);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    executor.initialize();
    return executor;
}
~~~

Attach the executor to the factory:

~~~java
factory.getContainerProperties()
        .setConsumerTaskExecutor(ordersConsumerExecutor);
~~~

A consumer task is long-lived because it executes the poll loop until the container stops. Therefore, the pool needs enough threads for every consumer task launched on that executor. If the pool has only two threads while the factory creates concurrency 4, some containers may lack threads to run or have to wait on resources depending on executor policy.

Do not use a large queue to mask a pool lacking threads for consumer tasks. A queue only delays starting consumers; it does not increase the number of consumers that can poll concurrently. Count consumer tasks across all containers sharing the executor, not just one listener.

`SimpleAsyncTaskExecutor` creates a new thread per task rather than reusing threads like a traditional pool. `ThreadPoolTaskExecutor` manages a pool and must be configured with appropriate sizing, queue, and shutdown settings. Choose the executor based on consumer count, JVM resources, and deployment style.

## 6. Renaming consumer threads with threadNameSupplier

Some Spring Kafka versions provide `ContainerProperties` options `changeConsumerThreadName` and `threadNameSupplier`. This mechanism lets the application name consumer threads based on the Kafka `Consumer` rather than relying solely on the executor prefix.

Illustrative example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var properties = factory.getContainerProperties();
    var sequence = new AtomicInteger();
    properties.setChangeConsumerThreadName(true);
    properties.setThreadNameSupplier(
            consumer -> "orders-consumer-" + sequence.incrementAndGet());

    return factory;
}
~~~

When `changeConsumerThreadName` is enabled, the container uses the result from `threadNameSupplier` to rename the consumer thread as supported by the Spring Kafka version. The example uses a counter to generate unique names within the factory lifecycle.

These APIs depend on Spring Kafka version. If your project lacks these methods, use `consumerTaskExecutor` with a thread name prefix or check documentation for your exact version before upgrading. Do not add code relying on newer version APIs to an older project without checking the actual dependency.

Thread names should be short, easy to search, and unique within the process. Do not put tokens, passwords, payloads, or personal data in thread names. Also avoid naming threads based on current partition assignments if threads survive multiple rebalances and own different partitions over time.

## 7. Thread names and @KafkaListener configuration

The `@KafkaListener` annotation has several attributes affecting container or Kafka client identifiers:

~~~java
@KafkaListener(
        id = "paymentEventsListener",
        topics = "payment-events",
        groupId = "payment-projection",
        clientIdPrefix = "payment-projection-client",
        concurrency = "2")
public void handle(PaymentEvent event) {
    projectionService.apply(event);
}
~~~

In the example:

- `id` identifies the listener endpoint in Spring.
- `topics` specifies topic subscriptions.
- `groupId` sets the group ID for the listener.
- `clientIdPrefix` sets the Kafka client ID prefix.
- `concurrency` sets the number of consumers managed by the listener container.

`concurrency` can be configured on the annotation or on the listener container factory. If configured in both places, verify which value applies to the specific endpoint per your Spring Kafka version and container creation path. Avoid declaring conflicting values unintentionally.

If there are multiple listeners, name IDs by business function and configure separate factories when they need different executors or concurrency:

~~~java
@KafkaListener(
        id = "ordersCreatedListener",
        topics = "orders-created",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory")
public void onOrderCreated(OrderCreated event) {
    orderProjection.update(event);
}

@KafkaListener(
        id = "paymentsCapturedListener",
        topics = "payments-captured",
        groupId = "payment-projection",
        containerFactory = "paymentsListenerContainerFactory")
public void onPaymentCaptured(PaymentCaptured event) {
    paymentProjection.update(event);
}
~~~

Listener names and thread prefixes should reflect the same business context for easy correlation in logs. There is no need to cram group ID, topic, partition, and pod ID into the thread name if that information is already recorded in the log context.

## 8. Thread names in logs and thread dumps

Thread names are only useful when logs and observability tools actually display them. With Logback, the `%thread` pattern prints the thread name:

~~~xml
<encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
</encoder>
~~~

A log line may look like:

~~~text
2026-11-15 10:30:12.145 [orders-consumer-2] INFO  OrderListener - Received order event
~~~

In production, supplement logs with meaningful fields such as application instance, listener ID, group ID, topic, partition, and offset in the log message or MDC. Thread names do not replace these fields because a thread can process multiple partitions and partition ownership can change after rebalances.

Example logging inside a listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service")
public void handle(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
            "Processing event key={} topic={} partition={} offset={}",
            record.key(),
            record.topic(),
            record.partition(),
            record.offset());

    orderService.process(record.value());
}
~~~

When reading thread dumps using `jstack`, Java Flight Recorder, or APM tools, check:

- Thread name to identify the listener/executor.
- Stack trace to see whether the thread is in `KafkaConsumer.poll()`, listener code, serialization, a database call, or waiting on a lock.
- Thread state such as `RUNNABLE`, `WAITING`, or `BLOCKED`.
- Duration in that state and frequency across multiple dumps.
- Thread count compared to expected concurrency and replicas.

A thread inside `KafkaConsumer.poll()` is not necessarily hung; it may simply be waiting normally for records. A consumer thread frequently inside database calls or lock contention can slow polling and trigger rebalances if configured limits are exceeded.

## 9. MDC and context when offloading work to another thread

MDC is commonly used to attach correlation IDs, request IDs, or business context to logs. MDC is typically `ThreadLocal`-based, so MDC values on a consumer thread do not automatically appear in another worker thread.

If the listener processes synchronously, MDC set on the consumer thread persists for the processing scope if cleared properly. If the listener offloads work to an executor, pass context explicitly:

~~~java
Map<String, String> context = MDC.getCopyOfContextMap();

workerExecutor.execute(() -> {
    try {
        if (context != null) {
            MDC.setContextMap(context);
        }
        processAsync(event);
    }
    finally {
        MDC.clear();
    }
});
~~~

This is an example of manual MDC propagation. You can use `TaskDecorator` or framework context propagation mechanisms to standardize copying and restoring context. Always clear context after the task finishes because thread pools reuse threads; otherwise, logs of a subsequent event could carry the previous event's correlation ID.

Do not confuse renaming threads with propagating context. A thread name is an execution thread label; MDC is log data attached to a thread at a point in time. Renaming a thread does not automatically put group ID, event ID, or trace ID into MDC.

## 10. Thread naming with multiple applications and replicas

A Kafka cluster can be read by many applications, each with many replicas and each replica with many consumers. If all use generic thread names like `kafka-consumer-1`, centralized logs struggle to identify which application a thread belongs to.

Use a convention with just enough components:

~~~text
<service>-<listener>-consumer-<index>
~~~

Example:

~~~text
orders-created-consumer-1
orders-created-consumer-2
payments-captured-consumer-1
payments-captured-consumer-2
~~~

If logs and APM already include `service.name`, `instance.id`, `client.id`, and `group.id`, thread names do not need to contain all of those fields. Keeping names short makes thread dumps easier to read and avoids overly long names.

When running multiple replicas:

- Use an application instance ID to identify pods or processes in logs and metrics.
- Use a stable group ID for replicas that should share load.
- Use distinct client ID prefixes per listener or consumer group when per-listener metric tracking is needed.
- Use distinct thread name prefixes for each listener's executor.
- Do not assign a different group ID per replica if the goal is for replicas to share the same assignment.

Thread names do not need to be globally unique across the cluster since threads exist within a single JVM. However, the name combined with service and instance ID in logs must suffice to pinpoint the event source.

## 11. Notes on executors and thread lifecycle

Consumer threads run long-lived loops. Hence, configuring an executor for listener containers differs from an executor for short-lived tasks:

- The pool needs enough threads for the number of running consumer tasks.
- A large queue does not increase the number of consumers that can poll concurrently.
- If the pool is shut down before containers, consumer tasks may fail to start or continue.
- During application shutdown, containers should stop first or follow the Spring-managed lifecycle so consumers can close properly.
- Do not arbitrarily rename threads from inside the listener without a clear reason; doing so can make thread names stop reflecting the container.

With `SimpleAsyncTaskExecutor`, each task may create a new thread rather than taking one from a reusable pool. This is convenient for long-running consumer tasks but still requires bounding task counts and JVM resources.

With `ThreadPoolTaskExecutor`, set core/max pool sizes to match total consumer tasks sharing the executor. If multiple listener factories share one pool, sum the concurrency of active listeners to determine required threads.

Do not attach a single small pool executor to many high-concurrency listeners. One listener can consume all worker threads and prevent another listener from starting. If resource isolation is required, create separate executors per listener group.

## 12. Monitoring consumer threads in production

Thread names are one part of observability. Combine them with consumer and container metrics to diagnose slowness or rebalances:

| Symptom | What to check |
|---|---|
| Threads do not appear after container starts | Does the executor have threads available, did the factory create the container, were there startup errors |
| Fewer threads than concurrency | Is the pool short on workers, is the queue backed up, or is the container paused |
| Consumer threads frequently BLOCKED | Lock contention in the listener or called libraries |
| Consumer threads spend long time in database/network calls | Listener is blocking; measure dependency latency and processing time per poll |
| Thread dump shows many threads with same prefix but no partitions | Concurrency may exceed partition count or listener subscription does not match |
| Thread name cannot be tied to a listener | Set clear container IDs and executor prefixes; include client ID and instance ID in logs |
| Logs show thread names changing unexpectedly | Check `threadNameSupplier`, executor, or custom thread-renaming code |

Record active consumer counts, partition assignments, consumer lag, listener processing duration, time between polls, and rebalance counts. Thread names locate threads within the JVM, but they do not replace group and partition metrics.

## 13. Common misconceptions

**Thread name is the Kafka client ID.** Incorrect. Thread name belongs to the JVM; client ID is a Kafka client property used in Kafka metrics and logs.

**Group ID determines thread name.** Incorrect. Group ID identifies the consumer group. Thread names typically come from the container bean name or executor; group ID can be used as part of a prefix only if the application explicitly configures it.

**Increasing concurrency only changes thread names.** Incorrect. It creates additional consumer tasks/members, which can change partition assignments, parallelism, connection counts, and broker load.

**One consumer-named thread always owns exactly one partition.** Incorrect. One consumer can own multiple partitions. Assignments change after rebalances.

**Renaming a thread gives the consumer a new client ID.** Incorrect. Thread name and Kafka client ID are two independent settings.

**All work triggered by a listener runs on the consumer thread.** Incorrect. If the application delegates work to an executor or async API, work can run on other threads. Observe actual threads in logs and thread dumps.

**A thread pool smaller than concurrency can be used without impact.** Incorrect. Consumer tasks are long-lived; a pool lacking workers can prevent some containers from running.

## 14. Procedure for naming listener threads

When creating a new listener, follow this sequence:

1. Set a clear listener ID reflecting the business stream.
2. Set a stable group ID for replicas that share load.
3. Set a client ID prefix if separate metrics per listener are needed.
4. Determine concurrency based on partition count and processing capacity.
5. Use default thread names if already clear enough; otherwise, configure a consumer task executor with a dedicated prefix.
6. If supported by your Spring Kafka version, consider `threadNameSupplier` for controlled consumer thread renaming.
7. Configure a log pattern with `%thread` and also log topic, partition, offset, and group ID when processing records.
8. Propagate MDC explicitly when offloading work to another executor.
9. Inspect thread dumps after startup to verify actual thread counts and names.
10. Test graceful shutdown and restart to ensure executors and containers stop in the proper lifecycle order.

Consumer thread naming helps identify execution threads in the JVM and investigate operational issues. A good convention combines an understandable container name, a clear executor prefix, a distinct client ID, and logs carrying partition metadata. Separating these identifiers allows operations teams to quickly correlate a slow thread with the listener, consumer group, and partition it is processing.
