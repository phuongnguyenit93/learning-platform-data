# stopImmediate

In Spring Kafka, the listener container manages the consumer lifecycle: polling records, invoking the listener, handling acknowledgments, and committing offsets. When the application asks the container to stop, the system must decide whether to process all records already fetched in the current poll or stop immediately after the record currently being processed. The **stopImmediate** property controls this stop boundary.

By default, the container typically finishes remaining records from the current poll result before stopping. When `stopImmediate` is enabled, the container stops after finishing the current record. This helps shorten stop time during new version deployments, maintenance, or scaling down consumers. In return, remaining records in the poll not yet processed by the listener may be redelivered when the consumer group resumes.

`stopImmediate` does not cancel an in-flight listener invocation mid-call, does not roll back side effects already executed, and does not replace offset commit policies. To stop safely, understand the stop point, `AckMode`, how listeners handle records, and application shutdown time.

## 1. What does stopImmediate solve?

A Kafka consumer fetches records via `poll()`. One poll can return multiple records from one or more partitions. For a record listener, Spring Kafka calls the listener sequentially for each record in the poll result. When a stop is requested, the container must decide how many more records to process before exiting the loop.

- **stopImmediate=false:** the container processes remaining records in the current poll result before stopping, per default behavior.
- **stopImmediate=true:** the container stops after the currently processing record finishes; subsequent records in the current poll result are not dispatched to the listener in that container lifecycle.

Example where a poll returns five records:

    Poll returns:  A  B  C  D  E
    Listener currently processing: C
    stop() requested

    stopImmediate=false:
        Finish C -> process D -> process E -> stop

    stopImmediate=true:
        Finish C -> stop
        D and E were not processed by the listener in this run

This setting controls when the container stops dispatching records to the listener. It is not a thread-cancellation command and does not make an in-flight record disappear. If the listener is calling a database or HTTP service, the container must wait for that call to return or throw an exception before finishing the current record.

## 2. Stop boundary and record lifecycle

A record typically goes through these steps:

1. Consumer polls records from the broker.
2. Container delivers a record to the listener.
3. Listener executes business processing.
4. Listener completes normally or throws an exception.
5. Container applies the corresponding error handler and acknowledgment/commit policy.
6. Container checks running state and proceeds to the next record or stops.

When `stopImmediate` is enabled, the stop boundary sits after the current record. This means the container does not proactively interrupt between statements inside the listener. If the listener has started processing record C, the listener must finish or fail according to its own logic.

Example:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
    auditService.recordProcessed(event.eventId());
}
~~~

If the container receives a stop command while `consume()` is running, `stopImmediate` does not erase the `auditService` call or stop the thread between those two lines. The container waits for the listener to return, then stops before calling the listener for the next record.

If `process()` committed to the database but `auditService` failed, the record may be considered failed depending on the exception and error handler. When the record is redelivered, `process()` may run again. Listeners should have idempotency for side effects to avoid applying business updates twice.

## 3. Configuring stopImmediate on a listener container

The direct approach is configuring the factory's `ContainerProperties` before creating containers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setStopImmediate(true);
    properties.setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Listeners can select the factory using the `containerFactory` attribute:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Setting `stopImmediate` on `ContainerProperties` makes containers created from that factory share the same policy. If you only want it for one listener, configure a dedicated factory or customize that container in the way supported by your project's Spring Kafka version.

Do not set the property after a container is already running and assume it immediately changes the stop boundary of an in-progress poll. Configure it before startup and verify behavior in an integration environment.

### 3.1. Configuring shutdown timeout

`stopImmediate` controls how many more records are dispatched after a stop request. `shutdownTimeout` controls how long the container waits for stopping to finish during shutdown. The two properties solve different problems.

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setStopImmediate(true);
properties.setShutdownTimeout(15_000L);
~~~

The shutdown timeout value is in milliseconds in this API. Choose the timeout based on the maximum time the listener needs to finish one record, plus offset commit and consumer close time. Too short a timeout can cause the process to be terminated while the listener is still processing; too long a timeout can drag out rollouts or shutdowns.

Coordinate container timeout with Spring Boot graceful shutdown duration, deployment platform termination grace period, and dependency timeouts. If the orchestrator forces process termination before the container finishes, the listener can be cut off even with `stopImmediate` enabled.

## 4. Stopping a container via KafkaListenerEndpointRegistry

For listeners declared with `@KafkaListener`, Spring Kafka registers containers in `KafkaListenerEndpointRegistry`. The application can look up a container by ID and request a stop.

~~~java
@Component
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

The ID passed to `getListenerContainer()` must match the `id` on `@KafkaListener`. If no explicit ID is set, Spring Kafka may generate a default ID; using an explicit ID makes operational control easier to manage.

`stop()` requests the container to stop. When `stopImmediate=true`, the container applies the stop boundary after the current record. Do not call `stop()` from the listener thread itself if that operation makes the control flow wait on itself. For control requests from an administrative endpoint or another service, execute on an appropriate thread and protect the endpoint with application authentication and authorization.

You can use the lifecycle callback when you need to know the container has stopped:

~~~java
container.stop(() -> {
    log.info("Orders listener has stopped");
});
~~~

The callback indicates container stopping has completed per the lifecycle contract. It does not prove all non-Kafka business work has finished if the listener spawned asynchronous work and returned early.

## 5. Impact on offsets and acknowledgments

`stopImmediate` does not itself decide which offsets are committed. Offset commits depend on `AckMode`, transactions, which records the listener finished, and when the container processes acknowledgments.

Example with `AckMode.RECORD`:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setStopImmediate(true);
~~~

When the listener completes record C successfully, the container can commit that record's offset according to the configured commit mode. Unprocessed records D and E are not acknowledged as successful merely because they were polled. When the consumer group restarts, uncommitted records can be redelivered.

With `AckMode.BATCH`, the container commits per poll batch after the batch is successfully processed. If you want to stop mid-poll while maintaining accurate offset progress, check how your Spring Kafka version and listener type handle commits for already-processed records. Do not assume enabling `stopImmediate` automatically turns every `BATCH` mode into `RECORD`.

Points to remember:

- Successfully processed but uncommitted records may be redelivered.
- Records not yet processed by the listener are not considered complete just because the consumer polled them.
- Committing offsets before durable side effects can lose work.
- Completing side effects without committing offsets can create duplicates on redelivery.
- Manual acknowledgment must be called after business processing succeeds.

For listeners writing to a database, a common pattern is writing business changes and an `eventId` marker in the same database transaction, then letting the container commit offsets. If the process stops between the database commit and offset commit, redelivery sees the already-processed `eventId` and can skip duplicate side effects.

## 6. stopImmediate with record listeners and batch listeners

### 6.1. Record listener

A record listener receives each `ConsumerRecord` or corresponding payload. The container controls invoking the listener for each record in the poll result. This is the easiest case to reason about: when `stopImmediate=true`, the container finishes the current record and stops before invoking the listener for the next record.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

If a poll returns multiple records, the container may process only part of the poll result when stop is requested. Unprocessed records are read again from the committed offset once the consumer group resumes.

### 6.2. Batch listener

A batch listener receives a list of records in a single call:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    orderService.processBatch(records);
}
~~~

With a batch listener, the application receives the entire batch in one invocation. Do not assume the container can stop between statements inside `processBatch()` or cancel part of the work inside the method. `stopImmediate` is a container stop policy; it is not an API to cancel an active batch callback.

If you need per-record stopping, consider using a record listener. If you must use a batch listener, design batch processing to control progress, transactions, and per-record errors using your batch listener APIs. Verify actual behavior with your application's Spring Kafka version.

### 6.3. Listeners offloading work to an executor

A common design mistake is a listener launching background work and returning immediately:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

The container may treat the listener as finished immediately after submitting the task. If offsets are committed afterward, the record may be acknowledged while background work has not yet finished. `stopImmediate` only waits for the listener method to return; it does not automatically wait for tasks submitted by the application to an executor.

If processing asynchronously, coordinate acknowledgments with task completion. You can use async acknowledgments supported in your Spring Kafka version, or keep the listener invocation open until the future completes. Do not commit offsets merely because a task was queued.

## 7. stopImmediate is not pauseImmediate

Spring Kafka provides pause and stop mechanisms for different purposes.

| Mechanism | Purpose | Behavior |
|---|---|---|
| `stopImmediate` | Stop container early | Stops after the current record completes |
| `stopImmediate=false` | Stop at default poll boundary | Processes remaining records in poll before stopping |
| `pause` | Temporarily stop fetching more records | Container stays alive and can continue after resume |
| `pauseImmediate` | Control pause timing | Can pause after the current record instead of waiting for the full poll |
| `shutdown` | Terminate application/container | Performs lifecycle stop and closes resources |

Pause fits when temporary throttling is needed or waiting for a dependent service to recover without leaving the consumer group the way stopping a container does. Stop fits when taking a consumer out of service, deploying a new version, or shutting down the application.

`stopImmediate` does not replace `pauseImmediate`. A stopped container must be started again via lifecycle to resume consuming; a paused container can resume without recreating the entire lifecycle.

## 8. Impact on ordering and duplicates

When `stopImmediate` stops after record C in a poll, records D and E may be redelivered when the consumer group starts again. This is normal at-least-once behavior if offsets were not committed past them.

Example:

    Partition orders-0
    Offset:     20    21    22    23    24
    Record:      A     B     C     D     E

    Container processes A, B, C
    stopImmediate=true
    Container stops after C

If offset 23 was committed, the next run starts from D. If offset was committed only up to 22, the consumer may re-read C, then D and E. If offset was mistakenly committed to 25, D and E could be skipped. Therefore, check `AckMode` and commit boundaries when testing mid-poll stops.

Duplicates commonly arise when a listener finishes side effects but the offset is not committed. To handle safely:

- Use a stable `eventId` in payload or headers.
- Persist a processed marker in the same transaction as business updates.
- Use unique constraints or conditional upserts.
- Keep external service calls idempotent using an idempotency key.
- Avoid generating a new `eventId` when a record is retried or re-driven.

Regarding key-based ordering, Kafka preserves order within a partition, though redelivery can cause a previously processed record to appear again. Idempotency and aggregate versioning help avoid repeated effects or overwriting with stale state.

## 9. Impact on rebalances and rolling deployments

When a container stops, the consumer leaves the group or closes, and partitions can be assigned to other consumers. `stopImmediate` reduces how many records the old instance continues processing after receiving a stop command. This helps in rolling deployments because new instances can take over processing sooner.

However, do not stop all instances simultaneously if the system needs to maintain processing capacity. In a rolling deployment:

1. Pick an instance to stop.
2. Request its listener container to stop.
3. Wait for the current record to finish and the container to report stopped.
4. Let the group rebalance and remaining instances take over partitions.
5. Start the new version.
6. Monitor lag, errors, and duplicate rate after rollout.

If there are multiple concurrent child containers, stopping a `ConcurrentMessageListenerContainer` controls child containers via lifecycle. Check the status of all containers and active consumer counts before proceeding with the rollout.

`stopImmediate` reduces time spent draining the current poll, but does not eliminate processing time for the running record, offset commits, closing network clients, or rebalances. Measure actual times rather than treating it as an instant-shutdown guarantee.

## 10. Combining stopImmediate with error handlers

If a listener throws an exception, the error handler can retry the record, recover, or route it to a DLT. `stopImmediate` governs container stop lifecycle, whereas the error handler governs record failures. The two mechanisms can interact at stop time.

Example record listener with error handler:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

If the container is stopping while the error handler is retrying, completion timing depends on how the container handles the current record and the retry/backoff settings. Do not assume `stopImmediate` skips the error handler or aborts an active retry cycle.

With long retry backoffs, stopping can be prolonged by the current record's handling policy. Weigh retry counts, backoff durations, DLT, and allowed shutdown time. If a failing record cannot recover immediately, routing to DLT may be better than keeping the container in prolonged retries, while ensuring DLT publishing succeeds before treating the original record as recovered.

## 11. Controlling in-flight listener duration

`stopImmediate` is clearly effective only when the listener completes within a bounded time. If the listener calls a service without a timeout, stopping can wait indefinitely or until the container's shutdown timeout expires.

Measures to apply:

- Set connect and read timeouts on HTTP clients.
- Set query and transaction timeouts on databases.
- Bound retry duration inside the listener.
- Never wait on futures indefinitely with unbounded `join()` or `get()`.
- Monitor p50, p95, and p99 record processing times.
- Set shutdown timeout large enough to finish valid work.
- Align deployment platform termination grace period with container stop duration.

Example waiting on a future with a timeout:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    try {
        orderService.processAsync(event)
                .get(20, TimeUnit.SECONDS);
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted while processing order", exception);
    }
    catch (ExecutionException | TimeoutException exception) {
        throw new IllegalStateException("Order processing failed", exception);
    }
}
~~~

This example keeps the listener invocation open until the future completes or times out. On timeout, the application still must account for the possibility that the background task keeps running and creates side effects after the listener fails. Use cancellation if the service supports it, and keep business operations idempotent.

## 12. Scenarios where stopImmediate should be enabled

| Scenario | Benefit | What to control |
|---|---|---|
| Rolling deployment | Old instance stops early after current record | New instance and group must take over partitions |
| Listener maintenance | Reduces extra records processed after stop request | Offsets of unprocessed records must remain safe |
| Application shutdown | Reduces time draining already-polled records | Current listener must have reasonable timeouts |
| Consumer config changes | Stops old loop faster before recreating container | Control rebalances and duplicates |
| Admin-triggered stop | Faster response when halting a consumer | Secure control endpoint and monitor lifecycle |

It is not mandatory to enable `stopImmediate` for every listener. If poll batches are small and processing is fast, default behavior may be simpler. If a batch-style listener must finish an entire group of records together, evaluate batch and transaction design before enabling early stopping.

## 13. Observing stop operations

To verify `stopImmediate` produces desired behavior, record lifecycle events and record progress:

- Timestamp when the stop request was received.
- Container ID, listener ID, and consumer group.
- Record being processed when stop was requested.
- Timestamp when the current listener invocation finished.
- Last committed offset per partition.
- Number of records polled but not yet processed by the listener.
- Timestamp when the container reported stopped.
- Actual shutdown duration.
- Number of records redelivered after a new instance receives the partitions.

Logs should include topic, partition, offset, key, or `eventId`. Avoid logging sensitive payloads. Correlate producer logs, consumer logs, and business outcomes to distinguish a redelivered record from a new event.

Useful metrics include consumer lag, processing duration, rebalance count, commit latency, listener error rate, and container stop duration. If stops are fast yet consumer lag spikes or duplicate processing increases sharply, review batch size, `AckMode`, and idempotency.

## 14. Testing stopImmediate

An integration test should produce multiple records to the same partition, start consuming, and request stop while the listener is processing a known record.

Scenario:

1. Send records A, B, C, D, E to the same partition.
2. Use a record listener with a latch to hold record C during processing.
3. Wait until the listener starts processing C.
4. Call `stop()` on the container.
5. Release the latch so C completes.
6. Wait for the container to report stopped.
7. Check listener logs: with `stopImmediate=true`, D and E are not invoked in the old container lifecycle.
8. Restart the container or another consumer in the same group.
9. Verify D and E are redelivered if offsets were not committed past them.
10. Verify C's side effects are not duplicated if C is redelivered when commit had not completed.

Re-run the scenario with `stopImmediate=false` for comparison: the container processes remaining records in the poll before stopping per default behavior.

Additional cases to include:

- Current listener throws an exception while stopping.
- Error handler is executing retry/backoff.
- Listeners using `AckMode.RECORD` and `BATCH`.
- Listeners using manual acknowledgment.
- Batch listener receiving multiple records in one invocation.
- Listener offloading tasks to an executor.
- Container with concurrency greater than one.
- Application shutdown while listener calls a slow service.
- Offset commit failure or group rebalance occurring near stop time.

These tests validate stop boundaries and redelivery behavior under real configuration. Simply asserting that the container stopped is insufficient; verify offsets and business outcomes as well.

## 15. Common operational mistakes

| Misconception or practice | Consequence | Resolution |
|---|---|---|
| Thinking `stopImmediate` aborts the current listener | Can leave incomplete side effects | Design listeners with timeouts and finish current record |
| Enabling `stopImmediate` then committing entire poll | Can skip unprocessed records | Choose `AckMode` and commit offsets per completed record |
| Treating `stopImmediate` as pause | Container stops and must be started again | Use pause/resume when only temporarily halting |
| Calling stop from listener thread and waiting on itself | Risk of blocking lifecycle or deadlock | Control container from an appropriate management thread |
| Listener submits task and returns | Container may commit before task completes | Coordinate acknowledgment with task completion |
| Using batch listener expecting mid-method stop | Batch callback is not interrupted mid-statement | Use record listener or design checkpointed batches |
| Shutdown timeout too short | Process may exit before current record completes | Align container and deployment platform timeouts |
| Not checking offsets after rollout | Fails to detect lost or replayed records | Monitor commits and test restart/rebalance |
| Assuming fast stop means zero duplicates | Processed but uncommitted records can still redeliver | Make consumers idempotent by `eventId` |

## 16. Production selection guidelines

- Use `stopImmediate` when you need to stop the listener after the running record and cut down processing time for remaining poll records.
- Keep in-flight listener duration bounded; `stopImmediate` does not interrupt a running call.
- Configure `AckMode` matching side-effect and offset-commit boundaries.
- For record listeners, verify unprocessed records are not committed past.
- For batch listeners, do not assume the container can cancel part of an invocation.
- If the listener runs async tasks, acknowledge only after tasks complete durably.
- Distinguish stop, pause, `pauseImmediate`, and shutdown.
- Align `shutdownTimeout` with listener timeouts and termination grace period.
- Monitor lifecycle, commits, lag, rebalances, and redelivered records.
- Test mid-poll stops, listener errors, and shutdowns before production rollout.

`stopImmediate` lets a Spring Kafka listener container stop after the current record rather than continuing to dispatch all remaining records in the poll. Its value lies in controlling stop timing while keeping record processing boundaries clear. When properly paired with acknowledgments, offset commits, timeouts, and idempotency, applications can deploy or shut down faster while safely recovering unprocessed records.