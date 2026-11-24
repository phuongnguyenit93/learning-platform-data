# PauseImmediate

When a Kafka consumer processes data faster than a downstream database, HTTP API, or executor can accept it, the system needs **backpressure** to prevent overloading downstream. Spring Kafka allows calling **pause()** on the listener container to temporarily stop delivering new records to the listener without stopping and restarting the entire consumer.

**pauseImmediate** is a property of **ContainerProperties**, added in Spring Kafka 2.9. It changes **when a pause request takes effect for a record listener**:

- **pauseImmediate=false (default):** the container continues processing all remaining records from the previous poll, and then pauses.
- **pauseImmediate=true:** the container applies the pause after the **currently processing record** finishes; remaining records from the poll are retained in memory and delivered to the listener upon resume.

Immediate **does not mean interrupting the currently running method**. Pause does not automatically acknowledge records, does not lose Kafka data, and does not replace retries. This lesson belongs to the **Pause and Backpressure** chapter of **Spring Kafka Reliability Operations**, focusing on processing boundaries, offsets, control APIs, memory, concurrency, and operations.

## 1. Why pause the listener container?

Suppose the orders consumer has three pods, each running with concurrency=4. In total, there are 12 consumer threads capable of calling the database concurrently. When the database connection pool saturates, every call becomes slower and may time out.

If processing continues unrestricted:

- New listener invocations create more requests against an already overloaded pool.
- Timeouts trigger retries, potentially increasing total request volume.
- Async executor queues swell if the listener merely submits tasks and returns.
- Memory, thread pools, and CPU can be over-utilized.
- Consumer lag rises because the rate of completing business processing drops.
- Rebalances can occur if the listener does not return to poll within `max.poll.interval.ms`.

**Pause** reduces the rate of dispatching additional work, giving downstream time to recover. However, producers can still write to Kafka. Thus, lag can continue growing while paused; monitor retention and post-resume catch-up capacity.

### 1.1 Pause vs. stop

| API | Meaning | Consequence |
|---|---|---|
| container.pause() | Requests temporarily halting consumption | Container keeps running and can poll to maintain consumer group membership |
| container.resume() | Requests resuming consumption | Records continue being delivered upon resume |
| container.stop() | Ends lifecycle | Consumer closes, partitions may be reassigned |
| KafkaConsumer.pause(partitions) | Low-level API on a single consumer | Must respect consumer thread ownership |

For temporary backpressure, using container.pause()/resume() is usually better suited than stop/restart. Do not call KafkaConsumer.pause() directly from an HTTP controller or another scheduler thread.

## 2. Why can default pause react slowly?

KafkaConsumer.poll() can return **multiple records**. With a record listener, Spring Kafka invokes the listener individually for the records in the poll result.

Suppose a poll returned A, B, C, D, E. The container has finished A and B, and is currently processing C. Another thread detects downstream overload and calls pause().

When pauseImmediate=false, the sequence may be:

~~~text
poll -> [A, B, C, D, E]
handle(A) -> done
handle(B) -> done
handle(C) -> running
pause() requested
handle(C) -> done
handle(D) -> done
handle(E) -> done
consumer paused
~~~

The pause request only takes effect after the container finishes processing all records from that poll. If the poll is large and the listener is slow, the latency from request to paused can be long.

### 2.1 pauseImmediate=true

When set to true, the sequence becomes:

~~~text
poll -> [A, B, C, D, E]
handle(A) -> done
handle(B) -> done
handle(C) -> running
pause() requested
handle(C) -> done
consumer paused
D, E retained in memory

... downstream recovers ...

resume()
handle(D) -> done
handle(E) -> done
~~~

D and E are retained to continue after resume. PauseImmediate reduces the number of listener invocations started after a pause request, without altering the contents of records already polled.

### 2.2 Does not cancel the current record

If handle(C) is waiting on a 40-second HTTP call, pauseImmediate=true still cannot cut off C mid-execution. The container must wait for the current invocation to complete or be handled by the proper exception mechanism.

This means:

- Pause latency depends on the remaining execution time of the current record.
- Finite timeouts must be configured for database/HTTP calls.
- Do not use pause to mask a hung listener.
- If the listener does not return to poll in time, `max.poll.interval.ms` can still be exceeded.
- With async work, pause does not automatically cancel already-submitted tasks.

## 3. Configuration in ConcurrentKafkaListenerContainerFactory

You can set pauseImmediate directly on ContainerProperties:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        CommonErrorHandler errorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(errorHandler);
    factory.setConcurrency(3);
    factory.setBatchListener(false);

    factory.getContainerProperties().setPauseImmediate(true);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Record listener using the factory:

~~~java
@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-projection",
        topics = "orders",
        groupId = "orders-projection-prod",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderEvent event) {
        service.apply(event);
    }
}
~~~

OrderEvent, OrderService, and errorHandler are assumed to already exist in the application; the example requires appropriate imports, serializer/deserializer, and consumer properties.

**setPauseImmediate(true) only configures behavior when a pause is requested.** It does not cause the listener container to start in a paused state.

### 3.1 Version and scope

- The property was introduced in Spring Kafka **2.9**.
- The default value is **false**.
- It is described for **record listeners**.
- To configure it reliably on a custom factory, use factory.getContainerProperties().setPauseImmediate(true).
- Do not assume a YAML property with a similar name exists in every Spring Boot version.
- If multiple container factories exist, configure the exact factory of the listener you want to throttle.

### 3.2 Batch listeners differ from record listeners

A batch listener receives multiple records in **a single method call**:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "ordersBatchFactory"
)
public void handleBatch(List<OrderEvent> events) {
    service.processBatch(events);
}
~~~

PauseImmediate does not automatically split an ongoing processBatch() call at element N. To achieve mid-batch backpressure, you must design batch processing, sizing, acknowledgment, and partial retries separately.

Do not use a feature meant for record listeners as a promise that "a batch listener will stop immediately in the middle of the List."

## 4. Calling pause() and resume() via registry

With `@KafkaListener`, you can look up the container by listener ID via KafkaListenerEndpointRegistry.

~~~java
@Service
public class OrderConsumptionControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumptionControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        MessageListenerContainer container = container();
        if (!container.isPauseRequested()) {
            container.pause();
        }
    }

    public void resume() {
        MessageListenerContainer container = container();
        if (container.isPauseRequested()) {
            container.resume();
        }
    }

    public boolean pauseRequested() {
        return container().isPauseRequested();
    }

    public boolean consumerPaused() {
        return container().isConsumerPaused();
    }

    private MessageListenerContainer container() {
        MessageListenerContainer result =
            registry.getListenerContainer("orders-projection");

        if (result == null) {
            throw new IllegalStateException(
                "orders-projection container not found"
            );
        }
        return result;
    }
}
~~~

If the container is not managed by the `@KafkaListener` registry and is instead a directly declared bean, you can inject that bean rather than looking it up via the registry.

### 4.1 Pause requested vs. actual pause

**isPauseRequested()** indicates a pause has been requested. **isConsumerPaused()** indicates the underlying Kafka consumers are actually in the paused state, with appropriate aggregation for concurrent containers.

A completely valid state:

~~~text
pauseRequested = true
consumerPaused = false
~~~

At this moment, the current record may still be running or one child may not have applied the pause yet. Admin APIs should not return "all consumers paused" immediately after calling pause() without verifying actual state.

### 4.2 Do not control KafkaConsumer directly from another thread

KafkaConsumer is not thread-safe for most operations. The container API allows requesting pause/resume from a service or scheduler and letting Spring Kafka apply it within the consumer lifecycle.

Do not grab the Consumer object from a listener callback and call consumer.pause() on an HTTP request thread. Doing so can race with polling and assignment state.

## 5. Polling still matters while paused

When the container is paused, Spring Kafka can still issue appropriate polls to maintain group membership. That differs from completely blocking the consumer thread with a very long Thread.sleep().

### 5.1 pollTimeoutWhilePaused

Some Spring Kafka versions support the pollTimeoutWhilePaused property to adjust the poll timeout while in the paused state.

~~~java
factory.getContainerProperties()
       .setPollTimeoutWhilePaused(Duration.ofMillis(100));
~~~

Modern Spring Kafka documentation notes the default is typically **100 ms**. The timeout should be greater than 0 to avoid a tight CPU-burning loop while the consumer is paused.

| Configuration | Controls |
|---|---|
| pauseImmediate | Boundary for applying pause while a record listener processes a poll |
| pollTimeoutWhilePaused | Poll timeout when the container is paused |
| max.poll.records | Maximum records a consumer receives in a single poll |
| max.poll.interval.ms | Maximum time limit between polls before risking assignment loss |

Lowering the poll timeout does not make the current listener finish faster. Nor does pauseImmediate make a hung HTTP call time out on its own.

### 5.2 Consumer group membership

Pause differs from stop because the consumer can continue polling without receiving data records from paused partitions, helping maintain group membership. However, if the current record takes so long to process that polling cannot continue, the consumer can still rebalance.

Do not claim that pause 100% guarantees no rebalances under all infrastructure failures.

## 6. Remaining records are held in memory

When pauseImmediate=true, remaining records from the prior poll are retained in container memory. This is how Spring Kafka resumes delivering data after resume without requiring the application to republish records.

For example, a consumer polls 200 records, processes 61 records, and then pauses. The remainder can be held in memory until resume.

### 6.1 Impact on memory budget

Suppose concurrency=4, max.poll.records=500. Each child can retain its own subset of records. The total number of retained records depends on:

- Number of child consumers.
- Number of records returned from the polls.
- Number of records already processed before pause.
- Size of keys, values, headers, and object graphs.
- Runtime allocation, GC, and deserializers.

Do not treat `max.poll.records` as a byte limit. A poll of 100 large payloads can require more memory than a poll of 500 small payloads.

### 6.2 Lowering max.poll.records

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
~~~

Reducing records per poll can reduce the number of buffered records when pausing. However, it can also alter throughput. Measure your real workload; do not set `max.poll.records` extremely small solely to chase a particular pause latency.

### 6.3 Memory buffer is not durable

If the pod dies while D/E are retained, process memory is lost. A new consumer will re-read from the committed offset per Kafka log and retention.

Some previously succeeded records may also be redelivered if their offsets had not committed in time. Therefore, the listener and downstream side effects still need idempotency.

## 7. Offset commits and acknowledgment

PauseImmediate does not automatically mark polled records as successful. It is not an offset commit mechanism.

### 7.1 AckMode.RECORD

With a record listener and AckMode.RECORD, the container typically commits offsets after each successfully processed record according to the corresponding commit policy.

~~~text
A processed
B processed
C processed
PAUSED
D retained, not processed
E retained, not processed
~~~

D/E are not considered business successes just because they sit in the buffer. Because they have not been processed, application logic must not commit offsets past them.

### 7.2 AckMode.BATCH

A record listener can also use AckMode.BATCH. When pause cuts mid-poll, the commit timing of already-processed records must be evaluated against your Spring Kafka version and container semantics.

Do not assume pause always commits offsets immediately after record C. If the commit has not completed, A/B/C may be redelivered after a restart.

### 7.3 Manual acknowledgment

With AckMode.MANUAL or MANUAL_IMMEDIATE, acknowledge only after side effects truly complete:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "manualOrdersFactory"
)
public void handle(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    service.apply(record.value());
    acknowledgment.acknowledge();
}
~~~

The factory must configure the appropriate AckMode. Do not place acknowledge inside a finally block: a business failure must not automatically turn into a successful record.

### 7.4 asyncAcks is a separate mechanism

Spring Kafka has `asyncAcks` for out-of-order manual acknowledgments in supporting versions; the container may pause when needing to wait for missing acknowledgments.

`asyncAcks` solves **offset acknowledgment sequencing**, whereas `pauseImmediate` decides **the boundary for delivering new records after a pause request**. If using both together, distinguish the cause of pauses and avoid resuming at the wrong time.

## 8. Concurrency and multiple child consumers

The parent ConcurrentMessageListenerContainer creates multiple child KafkaMessageListenerContainer instances. Each child manages its own KafkaConsumer and consumer thread.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer"]
    P --> A["Child 0 / consumer 0"]
    P --> B["Child 1 / consumer 1"]
    P --> C["Child 2 / consumer 2"]
    A --> LA["Record listener"]
    B --> LB["Record listener"]
    C --> LC["Record listener"]
~~~

When the parent receives a pause request, the children apply it at their own processing boundaries. With pauseImmediate=true, each child waits for its current record to finish.

For example:

- Child 0 has 20 ms left on its current record.
- Child 1 has 500 ms left.
- Child 2 has 3 seconds left.

The parent can only be considered fully paused after the corresponding child consumers have applied the pause. Do not assume all three stop at the exact same instant.

### 8.1 Account for the entire deployment

Three pods with concurrency=4 create up to 12 consumer members participating in the group. Each member has its own poll buffer. When designing memory/backpressure budgets, account for total instance count, concurrency, `max.poll.records`, and record sizes.

### 8.2 Pause does not fix uneven load distribution

One partition can contain more records than another. Pausing the parent affects all corresponding children, including a child processing healthy partitions. If you need to throttle a single partition or tenant, consider partition-level pause APIs in supporting Spring Kafka versions, while verifying their specific semantics; do not assume pauseImmediate applies identically to every partition-control flow.

## 9. Automatic throttling with hysteresis

A backpressure policy should have a **high watermark** to pause and a **low watermark** to resume, rather than a single threshold that causes oscillation.

Example:

~~~text
downstream pending >= 800 : pause
downstream pending <= 300 : resume
300 < pending < 800     : keep current state
~~~

Illustrative controller:

~~~java
public interface DownstreamLoad {
    long pendingTasks();
}
~~~

~~~java
@Component
public class OrdersBackpressureController {

    private final KafkaListenerEndpointRegistry registry;
    private final DownstreamLoad load;

    public OrdersBackpressureController(
            KafkaListenerEndpointRegistry registry,
            DownstreamLoad load) {
        this.registry = registry;
        this.load = load;
    }

    @Scheduled(fixedDelay = 2_000)
    public void regulate() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-projection");

        if (container == null || !container.isRunning()) {
            return;
        }

        long pending = load.pendingTasks();

        if (pending >= 800 && !container.isPauseRequested()) {
            container.pause();
        }
        else if (pending <= 300 && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

For `@Scheduled` to run, enable scheduling in Spring configuration, e.g., `@EnableScheduling`. The numbers 800/300 are illustrative only and must be calibrated to downstream queue capacity/latency.

### 9.1 Choosing the right metric

If the listener calls the database synchronously, pendingTasks in an executor may not reflect load because there is no executor. You can use:

- Connection pool waiters.
- Database query p95/p99 latency.
- HTTP 429/503 rates.
- Circuit breaker open/half-open state.
- In-flight request count or queue depth.
- CPU throttling, heap pressure.
- Bounded worker pool backlog.

Rising consumer lag **does not by itself prove a need to pause**. Pausing can increase lag further; the goal is protecting downstream.

### 9.2 Do not let an auto-controller resume a manual pause

If an operator pauses for maintenance and the auto-controller sees pendingTasks=0, an automatic resume call can violate intent.

In production, manage pause reasons: MAINTENANCE, DOWNSTREAM_OVERLOAD, MANUAL_OPERATOR. Resume only when all pause reasons have been resolved. The simple code example above assumes a single policy owner.

## 10. Pause does not fix an unbounded async queue

Anti-pattern:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    executor.submit(() -> service.apply(event));
}
~~~

The listener returns immediately while the task is still running. The container can continue polling and committing offsets before the task actually completes, depending on AckMode. If the pod dies, incomplete tasks can be lost even though the offset advanced.

pauseImmediate only stops **new listener invocations**, without automatically draining the queue or guaranteeing side effects complete.

If using async processing, you must design:

- A bounded executor queue.
- Backpressure on queue occupancy.
- Acknowledgments tied to actual completion.
- Idempotency and per-key ordering.
- Graceful shutdown and task recovery.

Do not treat pause as a substitute for a durable job queue if the business requires processing durability across crashes.

## 11. Observability: pause requested vs. pause effective

Spring Kafka provides **ConsumerPausedEvent** and **ConsumerResumedEvent** when the container/consumer changes state accordingly.

~~~java
@Component
public class KafkaPauseEvents {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Paused partitions={}", event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Resumed partitions={}", event.getPartitions());
    }
}
~~~

Events can pertain to child containers and partition assignments. For troubleshooting, attach listener ID, client ID, and topic-partition to logs where possible.

### 11.1 Suggested metrics

| Metric | Purpose |
|---|---|
| pause_requested_total | Number of pause requests |
| resume_requested_total | Number of resume requests |
| pause_request_to_effective_ms | Latency to apply pause |
| pause_duration_seconds | Time spent paused |
| listener_processing_duration | p95/p99 record latency |
| consumer_lag | Kafka backlog |
| committed_offset_progression | Whether consumer advances after resume |
| rebalance_count | Whether abnormal rebalances occurred |
| downstream_pool_waiters | Connection pressure |
| downstream_error_rate | Whether the dependency has recovered |

These are suggested names for instrumentation, not all automatically present in default Micrometer.

### 11.2 Alerts

Alert when:

- Pause duration is too long.
- Consumer lag exceeds SLA or retention budget.
- isPauseRequested=true for a long time while isConsumerPaused=false.
- After resume, offsets still do not advance while waiting records exist.
- Downstream still fails yet the controller resumes repeatedly.
- Other retry consumers continue overloading downstream while the main listener is paused.

## 12. Combining PauseImmediate with an error handler

A processing record can throw an exception right as a pause request arrives. That does not turn the record into a success.

**DefaultErrorHandler** handles retry/recovery per policy and the container coordinates acks/offsets. PauseImmediate only controls stopping delivery of additional records when pause is requested.

Points to remember:

- Do not swallow an exception and acknowledge just so the container pauses.
- Retry/backoff may use its own pause mechanism; do not resume while backoff is still active.
- asyncAcks can keep the consumer paused due to missing acknowledgments.
- `@RetryableTopic` typically creates separate retry listener containers; pausing the main listener does not automatically pause all retry consumers.
- With a transactional listener, an exception can abort the Kafka transaction and trigger AfterRollbackProcessor; do not infer offsets from pause state alone.

### 12.1 Distinguishing pauseImmediate and stopImmediate

| Property | Trigger | Meaning |
|---|---|---|
| pauseImmediate | container.pause() | Stops delivering records after the current record, retaining the rest |
| stopImmediate | container.stop() | Stops lifecycle after the current record instead of finishing the poll, per API/version |
| pollTimeoutWhilePaused | Container paused | Poll timeout used while paused |

Do not use stopImmediate in place of pauseImmediate merely because of the similar name. Stop alters lifecycle and can trigger rebalances.

## 13. When pause reacts slowly

If pause() is called at 10:00:00 but consumerPaused only becomes true at 10:00:25:

1. Check whether runtime pauseImmediate is true or false.
2. Confirm it is a record listener rather than a batch listener.
3. Measure the latency of the current record.
4. Check `max.poll.records` and how many records were received from the prior poll.
5. Check child consumers in a concurrent container.
6. Observe ConsumerPausedEvent per child.
7. Check thread starvation, CPU throttling, or GC pauses.
8. Check error handlers, Kafka transactions, or blocked downstream calls.
9. Check `max.poll.interval.ms` and rebalance events.
10. Re-measure request-to-pause latency after adjustments.

If pauseImmediate=false and the prior poll had many records, waiting to finish the poll may be expected configured behavior rather than a Kafka bug.

If pauseImmediate=true yet the current record hangs for a long time, fix the timeout/dependency. This setting does not interrupt the method.

## 14. When resumed but the listener does not run yet

Possible causes:

- Resume is only requested; the consumer thread has not applied it yet.
- No waiting data records remain.
- The consumer does not yet have an assignment.
- The container stopped or the application is shutting down.
- Another pause reason exists.
- Error handler/backoff is waiting for a retry.
- Broker is unavailable or consumer is rebalancing.
- Metrics/logging are delayed.

Do not call resume continuously in a tight loop. Check ConsumerResumedEvent, isConsumerPaused(), assignments, consumer lag, and offset progression.

With automatic policies, use a low watermark and a healthy window instead of resuming the instant errors dip briefly.

## 15. Integration tests for PauseImmediate

Unit tests invoking listener methods directly do not verify `consumer.poll`, paused state, or retained records. Use a real Kafka broker via Testcontainers or staging.

### 15.1 Test comparing false and true

1. Create a single-partition topic.
2. Send multiple records so a single poll can receive A, B, C, D, E.
3. Have the listener use a CountDownLatch to hold record C in progress.
4. Call pause() while C has not finished.
5. With pauseImmediate=false, observe the container can process remaining records before pausing.
6. With pauseImmediate=true, release C and then wait for isConsumerPaused().
7. Verify D/E were not invoked on the listener while paused.
8. Call resume().
9. Verify D/E continue being processed.

Ensure **multiple records actually arrive in a single poll**; if each poll returns only one record, the two modes may look identical.

### 15.2 Test not interrupting the current record

- Hold C inside the listener with a latch.
- Send a pause request from another thread.
- Verify C is still running before releasing.
- After C completes, verify effective pause.
- Do not use flaky 1 ms timing assertions; use events/state and finite timeouts.

### 15.3 Test crashing while records are retained

- Poll A-E, pause after C.
- D/E are not yet processed.
- Stop the process/container before resume.
- Restart the consumer in the same group.
- Verify uncommitted records can be redelivered.
- Verify idempotency if earlier records are also redelivered.

### 15.4 Test concurrency and backpressure

- Run concurrency=3 with a topic having at least 3 partitions.
- Send pause on the parent while child records have varying latencies.
- Observe child pauses happen asynchronously, yet the parent eventually pauses.
- Exercise high/low watermarks and verify the controller does not oscillate.
- Resume and verify offset progression.
- Make one record fail to verify the error handler is not bypassed by pausing.

## 16. Runbook when downstream is overloaded

1. Identify Kafka listeners calling the bottlenecked dependency.
2. Measure downstream pool waits, error rates, p95 latency, and queue depth.
3. Check concurrency, partitions, `max.poll.records`, and memory budget.
4. Confirm the listener factory has pauseImmediate=true if pausing after the current record is desired.
5. Issue pause through MessageListenerContainer, not via consumer APIs on another thread.
6. Wait for isConsumerPaused or ConsumerPausedEvent to confirm actual pause.
7. Monitor in-flight work, acks/commits, and error handlers.
8. Monitor consumer lag, Kafka retention, and catch-up capacity.
9. When downstream stabilizes, resume per low watermark and healthy window.
10. Verify listener progress, offset commits, and normal error rates.
11. If overload recurs, increase capacity or reduce upstream rate instead of pausing forever.

Backpressure protects dependencies during incidents or spikes, but cannot solve long-term problems if producer rate exceeds consumption throughput.

## 17. Misconceptions to avoid

**"pauseImmediate=true immediately interrupts the running record."** False. It waits for the current record to finish processing.

**"Just enabling pauseImmediate makes the container pause automatically."** False. A pause request must be issued.

**"container.pause() returning means it is actually paused."** False. Check isPauseRequested and isConsumerPaused.

**"The default already stops after the current record."** False. Default is false: typically waits to process all records from the prior poll.

**"Records retained in memory are a durable queue."** False. A process restart loses the buffer; Kafka log and committed offsets provide redelivery.

**"Pause automatically commits polled records."** False. Commits follow AckMode, transactions, and error handling.

**"Pause guarantees avoiding all rebalances."** No. A listener blocking poll for too long can still lose assignments.

**"Batch listeners are split right in the middle of the List."** No. The property is described for record listeners.

**"Pause makes producers stop writing to Kafka."** False. Consumer lag can still grow.

**"Pause and stopImmediate are the same thing."** False. Pause/resume differs from stop lifecycle.

**"Increasing concurrency will fix database overload."** Not necessarily; it can worsen contention.

## 18. Configuration and operational checklist

**Container**

- [ ] Spring Kafka version supports pauseImmediate.
- [ ] Listener uses record mode when stopping after the current record is needed.
- [ ] setPauseImmediate(true) is set on the right factory.
- [ ] Code actively manages pause/resume and policy ownership.
- [ ] High/low watermark thresholds exist to avoid oscillation.
- [ ] pollTimeoutWhilePaused is configured appropriately if needed.
- [ ] max.poll.records and concurrency match memory/capacity.

**Reliability**

- [ ] AckMode and error handler are explicit.
- [ ] Unprocessed retained records are not treated as acked.
- [ ] Listener is idempotent on post-crash redelivery.
- [ ] Async tasks are not acked before completion.
- [ ] Current record has a finite timeout.
- [ ] Retry-topic consumers are also factored into downstream load.

**Observability**

- [ ] Track pause requested and consumer paused separately.
- [ ] Have ConsumerPausedEvent/ConsumerResumedEvent or equivalent metrics.
- [ ] Track request-to-pause latency and pause duration.
- [ ] Track committed offsets, lag, rebalances, and memory.
- [ ] Alert when paused too long or resume makes no progress.

**Verification**

- [ ] Tested a single poll containing multiple records.
- [ ] Compared pauseImmediate false vs. true.
- [ ] Tested resume and retained records.
- [ ] Tested crash/restart while paused.
- [ ] Tested concurrency>1 and child pauses occurring at different times.
- [ ] Tested record failures, retries, and backpressure thresholds.

## 19. Official documentation

- Spring Kafka: Pausing and Resuming Listener Containers — https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html
- Spring Kafka: Listener Container Properties — https://docs.spring.io/spring-kafka/reference/kafka/container-props.html

## 20. Conclusion

**pauseImmediate** changes the pause boundary of a **record listener** in Spring Kafka. With false (default), the container typically finishes records already received from the prior poll; with true, the container pauses after the **current record**, holding remaining records in memory to deliver after resume.

This is an important tool for making backpressure react faster to downstream overload, yet it does not interrupt a running listener, does not commit offsets on its own, does not guarantee durable memory buffering, and does not replace retries/idempotency. A reliable design must use the container API from proper threads, observe pause requested separately from actual pause, account for concurrency and poll buffers, and thoroughly test pause, resume, crashes, and recovery.

