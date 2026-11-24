# AsyncAcks and Out-of-Order Commits

In Spring Kafka, a listener can process records asynchronously by offloading work to an executor or a background service. When multiple records run concurrently, completion order often differs from the order Kafka delivered them. For example, a consumer receives offsets 100, 101, and 102, yet work for offset 102 finishes before offset 100. If the application commits offset 103 as soon as record 102 finishes, Kafka may skip 100 and 101 after a consumer failure.

`asyncAcks` is a Spring Kafka mechanism allowing acknowledgments for records returned in a single poll to arrive in any order. The container defers committing until acknowledgments for all records from that poll arrive, and only then commits offsets in safe order. While acknowledgments are still missing, the consumer is paused so it does not fetch more records from the managed partitions.

This mechanism supports asynchronous processing, but it does not by itself create exactly-once semantics, does not execute work in parallel on its own, and does not replace idempotency. The application must still acknowledge only after business effects are durably persisted, handle worker errors, and tolerate redelivery after incidents.

## 1. Why Can Out-of-Order Commits Drop Records?

Kafka stores committed offsets per partition and consumer group. The committed offset indicates the next position the consumer group will read. Once record offset 102 is finished, committing offset 103 tells the consumer group that all records before position 103 in that partition are confirmed.

Suppose a poll returns three records from the same partition:

| Offset | Processing Duration | Completion Order |
|---:|---:|---:|
| 100 | 900 ms | 3 |
| 101 | 300 ms | 2 |
| 102 | 100 ms | 1 |

If each worker commits offsets on completion, record 102 can make the application commit offset 103 before 100 and 101 finish. If the process stops right after that, the next read starts from 103; the two unfinished records may be skipped.

~~~text
Kafka poll:       100       101       102
                   |         |         |
Worker:          slow     medium     fast
                   |         |         |
Completed:         3         2         1
                   |         |         |
Wrong commit:                         103
                   |
            Process crashes
                   |
         100 and 101 skipped
~~~

The issue is not Kafka reordering records itself. Kafka still delivers records in offset order within a partition. Out-of-order completion arises at the application layer when multiple tasks run concurrently and finish at different speeds.

### 1.1. Committing an Offset Means Committing the Next Position

When record offset 100 is acknowledged successfully, the committed offset is normally 101. When record 102 is acknowledged, the committed offset is 103. Because committed offsets denote the next position to read, committing a higher offset implicitly confirms all lower offsets in the same partition.

Offsets across partitions are independent. Committing offset 103 on partition 0 does not mean records on partition 1 are finished. Still, a single poll can contain records from multiple partitions; the container must track acknowledgments and offsets per partition.

### 1.2. Why Does Parallel Processing Trigger This?

A listener might submit each record to a thread pool:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void listen(OrderCreated event) {
    executor.execute(() -> billingService.process(event));
}
~~~

The listener method returns immediately after enqueueing the task. If the container uses automatic record-style acknowledgments, it can treat the listener as finished while business work is still running. If commits happen directly in completion callbacks without preserving offset order, a fast record can push the offset past a slower record.

Do not treat submitting work to an executor as successful business processing. Acknowledgment timing must tie to durable completion of the work, not merely to the thread pool accepting the task.

## 2. How Does AsyncAcks Solve This Problem?

`asyncAcks` was added by Spring Kafka starting in the 2.8 release line. When enabled, the application can acknowledge records belonging to the same poll in any completion order. The container tracks missing acknowledgments and delays committing until all required acknowledgments from the prior poll have been received.

Example with offsets 100, 101, and 102:

1. The listener receives the records and dispatches three tasks to a worker pool.
2. The worker processing offset 102 finishes first and calls acknowledge.
3. The worker processing offset 101 finishes and acknowledges.
4. The container still does not commit past offset 100 because that record's acknowledgment is missing.
5. Offset 100 completes and is acknowledged.
6. Once all acknowledgments for the poll arrive, the container can safely commit the offset to the next position after the partition's last record.

~~~text
Poll returns:      100       101       102
                    |         |         |
Completed:          3         2         1
                    |         |         |
Ack arrives:       100?      101       102
                    |         |         |
Container holds acks until all arrive
                    |
Ack for offset 100 arrives
                    |
Safe next offset committed: 103
~~~

The key point is that the container manages commit ordering even when acknowledgments arrive out of order. The application does not have to compute the highest contiguous offset and commit manually inside every callback.

### 2.1. The Consumer Is Paused While Waiting for Acknowledgments

While acknowledgments from the prior poll are still missing, the container pauses the consumer so it does not keep feeding new records into the listener. This prevents an unbounded asynchronous work backlog and keeps clean boundaries between polls waiting to finish.

The consumer still continues its container-managed poll/heartbeat lifecycle to maintain group membership. Pausing here means temporarily halting new record delivery for processing, not closing the consumer or leaving the group.

Operational consequences:

- The slowest worker in a poll can keep the consumer paused longer than other workers.
- Adding more workers does not necessarily raise throughput if one slow record holds the whole poll batch from completing.
- Poll batch size affects how many tasks can run concurrently and how long the consumer remains paused.
- Monitor the age of missing acknowledgments, worker processing times, and consumer lag.

`asyncAcks` permits out-of-order completion while preserving safe commit boundaries. It does not remove the cost of a slow task.

## 3. Requirements for Using AsyncAcks

To use this mechanism, the listener must use manual acknowledgment and the container must enable asynchronous acknowledgments. Example configuration on a listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL);
    factory.getContainerProperties().setAsyncAcks(true);

    return factory;
}
~~~

Listener using this factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {
    // Offload work to worker and acknowledge on completion.
}
~~~

Bean names, key/value types, serializers, and consumer settings must match the actual application. `setAsyncAcks(true)` is an API in Spring Kafka versions supporting this feature; verify against your dependency version.

### 3.1. Manual Acknowledgment

`AckMode.MANUAL` lets the listener explicitly call `acknowledge()` after work completes. Combined with `asyncAcks`, acknowledgments can arrive from worker threads in actual completion order.

`AckMode.MANUAL_IMMEDIATE` commits immediately if acknowledge is called on the consumer thread. If acknowledge is called from another thread, the commit request is routed back to run on the consumer thread; do not assume it always commits instantaneously the moment a worker calls the method.

For asynchronous work, understand which thread calls ack and the semantics of the ack mode. Never build logic assuming the broker already committed the offset the instant a callback invokes `acknowledge()`.

### 3.2. Important Limitations

- `asyncAcks` is designed for record listeners; batch listeners are not supported under this feature's semantics.
- When `asyncAcks` is enabled, do not use `nack()`. Negative acknowledgment is incompatible with out-of-order acknowledgment management.
- The listener must use proper manual acknowledgment; simply enabling the property without calling ack at the right time leaves the container waiting indefinitely for missing acknowledgments.
- A poll must receive all required acknowledgments before the container resumes delivering new records under this mechanism.
- `asyncAcks` does not run records on a thread pool by itself. The application must manage its own executor and task lifecycle to process in parallel.

If you need a batch listener or `nack` logic to retry part of a batch, choose a different design tailored to your listener type and error handling instead of enabling `asyncAcks`.

## 4. Example of Asynchronous Processing with Acknowledgment

A common pattern is receiving the record on the consumer thread, submitting work to an executor, and acknowledging once the business service finishes:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    CompletableFuture
            .runAsync(
                    () -> billingService.processIdempotently(record.value()),
                    workerExecutor)
            .whenComplete((ignored, error) -> {
                if (error == null) {
                    acknowledgment.acknowledge();
                }
                else {
                    asyncFailureHandler.handle(record, error, acknowledgment);
                }
            });
}
~~~

This is an illustrative structure. `workerExecutor` must be an executor with bounded threads and queue; `billingService` must commit durable business changes before the future succeeds. `asyncFailureHandler` is an application-designed component for handling asynchronous failures.

Do not use an unbounded executor. If task arrival exceeds processing speed, the queue can grow without bound, consuming heap and stretching completion times. With `asyncAcks`, the consumer pauses while waiting for a poll's acknowledgments, yet a single poll can still spawn many concurrent tasks.

### 4.1. Acknowledge After Work Is Durable

For example, if a worker updates a database, the sequence should be:

1. Start the database transaction.
2. Check or insert the event ID into an inbox table.
3. Apply business updates if the event has not yet been processed.
4. Commit the database transaction.
5. Only after the commit succeeds, call `acknowledge()`.

If the database commits successfully yet the application dies before the offset is committed, Kafka may redeliver the record. The inbox/idempotency key prevents duplicate business updates.

Do not ack immediately after calling `CompletableFuture.runAsync()`. That only confirms the task was submitted to the executor; the task may fail, the process may stop, or the executor may reject the task.

### 4.2. Managing Task Rejection

If the executor rejects a task because its queue is full or it is shutting down, the listener must not treat the record as processed. Handle rejection right on the receive path and route the record to a controlled retry/recovery mechanism. Never ack a record just to unblock the consumer.

With a bounded-queue executor, choose an observable rejection policy. Policies that silently drop tasks lose work while Kafka offsets may be acknowledged if the application acks at the wrong moment.

## 5. Error Handling in Asynchronous Workers

A critical distinction is that exceptions occurring on a worker thread after the listener has returned do not automatically pass through the listener container's error handler. The container only observes exceptions thrown inside the listener/container thread it manages.

Therefore, if a worker fails:

- Do not acknowledge the record as though work succeeded.
- Do not assume the listener container's error handler will automatically catch exceptions from a thread pool.
- Route errors to an observable failure handler with bounded retries.
- Acknowledge only after processing succeeds or after the record has been durably transferred to a recovery flow such as a DLT.
- If both business processing and recovery fail, raise alerts and stop/recover the consumer per clear policy; do not leave acknowledgments hanging indefinitely.

### 5.1. Acknowledge Only After Successful Recovery

One design pattern is having the failure handler retry transient errors a bounded number of times. If processing still fails, it publishes the record to a DLT and calls acknowledge only after the DLT publish result is confirmed successful.

~~~text
Worker processes record
       |
       +---- Success -------> Ack
       |
       +---- Failure
                 |
                 v
          Bounded retries
                 |
          +------+------+
          |             |
       Success   Retries exhausted
          |             |
          v             v
         Ack       Publish DLT
                        |
                 +------+------+
                 |             |
              Success       Failure
                 |             |
                 v             v
                Ack      Do not ack; alert
                         and recover per runbook
~~~

This is an application logic flow, not an automatic setup provided by `asyncAcks`. Publishing to the DLT must await proper confirmation; if the DLT broker rejects the record, do not ack the source and lose replayability.

### 5.2. Missing Acknowledgments Can Keep the Consumer Paused

If a worker fails and the failure handler never completes or fails to ack after recovery, the container keeps waiting for the missing acknowledgment. Because the consumer is paused until the prior poll is fully acknowledged, new records may stop being delivered to the listener.

This behavior protects commit order, yet without timeouts and alerts it can look like a hung consumer. Log event ID, topic, partition, offset, processing start time, retry count, and recovery status.

Never arbitrarily ack a record just to unpause the consumer. Before acking, require proof that business effects completed or the record was safely persisted into a recovery channel.

## 6. Example of Out-of-Order Completion Within a Poll

Suppose a poll returns:

| Partition | Offset | Task |
|---|---:|---|
| orders-0 | 40 | Create invoice, takes 800 ms |
| orders-0 | 41 | Update status, takes 200 ms |
| orders-0 | 42 | Write audit, takes 100 ms |
| orders-1 | 15 | Sync data, takes 300 ms |

Completion order might be offset 42, offset 41, partition 1 offset 15, and finally offset 40. The container must manage acknowledgments independently per partition and must not commit past the missing offset in partition 0.

Once offset 40 is finally acknowledged and every record in the poll is confirmed, committed offsets can advance to 43 for partition 0 and 16 for partition 1. There is no global ordering between offset 43 and 16 because they belong to two different partitions.

This shows:

- Kafka preserves record ordering within each partition, not business processing order across partitions.
- AsyncAcks protects offset commit ordering, not worker completion order.
- If business logic requires ordering per aggregate, events for that aggregate must share a key/partition and must not run side effects concurrently in a way that breaks business order.

## 7. AsyncAcks and Throughput Limits

`asyncAcks` lets records within a single poll run concurrently, yet the container waits for all acknowledgments before fetching records in the next poll. Therefore, throughput depends on:

- Number of records returned per poll.
- Number of workers genuinely running in parallel.
- Processing duration of the slowest record in the poll.
- Capacity of databases and downstream services.
- Number of consumer members and assigned partitions.

A poll of 100 records with a 20-thread executor can process at most roughly 20 tasks simultaneously, depending on workload. However, if one task takes 30 seconds, the consumer still must wait for that acknowledgment before advancing to a new poll. Increasing `max.poll.records` can increase tasks per poll and potential parallelism, but also increases in-flight work and pause duration when a slow record occurs.

### 7.1. Choosing max.poll.records

`max.poll.records` caps how many records are returned in one poll. When using AsyncAcks, treat it as the cap on how many acknowledgments must finish before the consumer can advance.

Large batches:

- Can keep the executor busy and reduce poll overhead.
- Can spawn many concurrent tasks.
- Can let one slow record stall the whole poll longer.
- Can increase how many records get redelivered after a crash before commit.

Small batches:

- Bound concurrent tasks and pending work scope.
- Can let the consumer resume polling sooner when tasks finish quickly.
- Can lower throughput if poll and commit overhead takes a large share.

Choose the value from p95/p99 processing time distributions, worker-pool capacity, and downstream capacity. Do not base it solely on averages.

### 7.2. Bounded Executors and Backpressure

The executor should have bounded threads and a bounded queue. When the queue nears capacity, the system should apply backpressure or fail cleanly rather than accepting tasks indefinitely.

Options:

- Lower `max.poll.records` to reduce how many tasks are emitted per poll.
- Reduce worker count if downstreams are overloaded.
- Scale downstream capacity when it is the true bottleneck.
- Bound processing timeouts and retry counts.
- Add consumers/partitions when more parallelism is needed and data can be partitioned safely.

Do not use `CallerRunsPolicy` thoughtlessly if it forces the consumer thread to run long tasks inside callbacks and distorts poll timing. Every rejection policy must be evaluated in terms of which thread executes the task.

## 8. AsyncAcks Is Not Exactly-Once

AsyncAcks protects offset commit order for records in a poll. It does not create an atomic transaction between Kafka and a database, nor does it prevent a record from being redelivered after a crash.

Possible scenarios:

| Failure Timing | Consequence |
|---|---|
| Worker has not finished, not yet acked | Record may be redelivered |
| Database committed, worker not yet acked | Record may be redelivered; business logic must be idempotent |
| Worker acked, container not yet committed offset | Record may be redelivered if process/broker fails before commit |
| All acks arrived and offset committed | Consumer group resumes from the next committed offset |
| Worker acked before database committed | Risk of losing business effects if the database fails afterward |

For consumers updating a database, use an inbox table or unique event ID in the same transaction as the business update. For external API calls, use an idempotency key if the target API supports it. Otherwise, maintain processing state and reconciliation to handle ambiguous timeout outcomes.

## 9. AsyncAcks and Business Ordering

Kafka preserves record order within a partition, yet when an application processes asynchronously, business effects can finish out of order.

For example, a partition contains:

1. `OrderCreated`
2. `OrderPaid`
3. `OrderShipped`

If three workers run concurrently, `OrderShipped` might finish before `OrderCreated`. AsyncAcks only protects offset commits; it does not automatically ensure event side effects finish in order.

If business logic requires sequential order per aggregate:

- Process records with the same key within a partition sequentially.
- Or shard work by key into sequential lanes.
- Or check aggregate version/sequence in the database before applying changes.
- Enforce idempotency and reject or defer out-of-order events per business rules.

Run in parallel only independent events or steps that tolerate out-of-order completion.

## 10. Observability for Acknowledgments and Commits

When using AsyncAcks, consumer lag alone is not enough to find a stuck acknowledgment. Record these milestones:

- Timestamp when the record was received by the listener.
- Timestamp when the task was enqueued and started running.
- Timestamp when the business effect committed.
- Timestamp when acknowledgment was invoked.
- Retry or DLT publish outcomes if any.
- Topic, partition, offset, event ID, and consumer group.

Recommended metrics:

| Metric | Meaning |
|---|---|
| Async task in-flight count | Number of tasks currently executing |
| Worker queue depth | Number of tasks waiting in the executor |
| Worker processing duration | Worker execution time |
| Oldest unacknowledged age | Age of the oldest missing acknowledgment |
| Acknowledgement completion rate | Rate of tasks completing and acking |
| Consumer pause duration | Time consumer spends paused waiting for acks |
| Consumer lag / oldest record age | Backlog and data staleness |
| Retry/recovery/DLT rate | Failure and recovery health |
| Commit latency/failure | Offset commit outcomes |

Do not attach event ID, offset, or message key as high-cardinality metric tags. Record them in structured logs to investigate specific records.

### 10.1. Essential Alerts

Configure alerts when:

- An incomplete acknowledgment exceeds expected processing time.
- Consumer pause lasts abnormally long.
- Worker queue depth climbs continuously.
- Processing rate drops below incoming rate and lag grows.
- Retries or DLT volume spike sharply.
- Offset commits fail.
- Worker exceptions rise after a deployment.

Thresholds should reflect SLAs and real processing-time distributions. A 5-second task may be normal for one job type yet an incident for a real-time pipeline.

## 11. Runbook When Consumer Pauses Due to Missing Acks

### 11.1. Consumer Receives No New Records

1. Check container status and consumer pause state.
2. Find records dispatched without a matching acknowledgment.
3. Search logs by topic, partition, offset, and event ID.
4. Inspect worker queue, thread pool, database connections, and downstream latency.
5. Determine whether the task is running, hung, rejected, or failed.
6. If the task failed, check the failure handler and retry/DLT state.
7. Acknowledge only after business work completes or recovery durably persists the record.
8. Confirm the consumer resumes polling and lag begins dropping.

### 11.2. Worker Queue Grows Continuously

1. Compare dispatch rate with completion rate.
2. Check worker count and CPU utilization.
3. Check whether downstream databases/APIs are slow or throttling concurrency.
4. Reduce poll batch size or dispatch rate.
5. Adjust the worker pool after identifying the bottleneck.
6. Monitor the oldest acknowledgment age until it returns to normal.

### 11.3. Records Redelivered After Restart

1. Identify the group's latest committed offset.
2. Identify which records completed business work yet were not committed.
3. Check inbox/idempotency keys to prevent duplicate side effects.
4. Reconcile external operations outside the database if the target API returned ambiguous outcomes.
5. Confirm records reprocess and ack/commit advance in proper order.

## 12. Testing AsyncAcks

Tests must verify completion ordering, offset commits, and business side effects together.

An integration test scenario:

1. Create a test topic with at least one partition and publish multiple consecutive offsets.
2. Configure a record listener with manual ack and AsyncAcks.
3. Make the first record process slower than subsequent records.
4. Have workers finish and ack in reverse order.
5. Confirm the consumer does not commit past the unacknowledged record.
6. Let the slowest record ack and confirm the commit advances once the poll is fully acknowledged.
7. Restart the consumer before all acks arrive and confirm uncommitted records can be redelivered.
8. Confirm idempotency prevents duplicate business effects.
9. Force a worker failure and verify the failure handler does not ack erroneously.
10. Make DLT/recovery unavailable and verify the source record is not acked and lost.

Have separate tests for executor rejection, worker timeouts, shutdown while tasks are running, and commit failures. A test verifying only that `acknowledge()` was called is insufficient; inspect actual offsets and business outcomes.

## 13. Common Design Mistakes

**Acking immediately after enqueue:** The task may not have run yet or may be rejected. Ack only after business outcomes are durable.

**Manually committing the highest offset from a worker:** Can commit past a missing offset in the same partition. Let the container manage acknowledgments with AsyncAcks.

**Enabling AsyncAcks without manual ack:** The container does not receive completion signals at the right point. Choose the matching ack mode and listener signature.

**Swallowing exceptions inside workers:** The listener container cannot see asynchronous errors. Forward errors to a failure handler with clear retry/recovery.

**Leaving an ack hanging indefinitely:** The consumer can stay paused and stop receiving new records. Set up timeouts, alerts, and recovery procedures.

**Assuming AsyncAcks preserves side-effect order:** It only manages offset commits; business ordering must be protected at the processing layer.

**Using an unbounded executor:** The queue can grow without limit and exhaust heap. Bound threads, queues, and dispatch rate.

**Using nack alongside AsyncAcks:** The two mechanisms are incompatible. Choose one suitable retry model.

## 14. Implementation Checklist

### Container Configuration

- [ ] Spring Kafka version supports AsyncAcks.
- [ ] Listener uses the appropriate record mode.
- [ ] Ack mode is set to MANUAL or MANUAL_IMMEDIATE per required semantics.
- [ ] AsyncAcks is enabled on the exact listener container.
- [ ] `nack` is not used while AsyncAcks is enabled.
- [ ] Kafka consumer auto-commit is disabled when the container manages acknowledgments.

### Asynchronous Processing

- [ ] Executor has bounded threads and queue.
- [ ] Tasks ack only after business work completes durably.
- [ ] Executor rejections and worker exceptions are handled explicitly.
- [ ] Failure handler has bounded retries and recovery/DLT.
- [ ] Recovery acks only after the record has been durably stored.
- [ ] Timeouts and alerts exist for missing acknowledgments.

### Reliability and Operations

- [ ] Consumer is idempotent when records are redelivered.
- [ ] Business ordering per key is protected if required.
- [ ] Metrics exist for in-flight tasks, queue, processing time, pause, and lag.
- [ ] Crash-before-commit and duplicate-delivery tests have been run.
- [ ] Worker failures, DLT failures, and graceful shutdown have been tested.
- [ ] Runbook documents how to resolve consumer pauses caused by missing acks.

## Conclusion

AsyncAcks allows records within the same poll to be acknowledged in any completion order while Spring Kafka defers committing until all required acknowledgments arrive. This enables parallel processing without committing past unfinished records. In return, the consumer pauses while acks are missing, slow workers can hold back an entire poll, and errors on asynchronous threads must be handled separately by the application. Use manual acknowledgment, bounded executors, idempotency, and controlled recovery; monitor missing-ack age, pause duration, worker queues, and committed offsets to operate safely.
