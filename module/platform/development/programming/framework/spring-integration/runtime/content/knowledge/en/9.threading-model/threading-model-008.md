# Race Conditions When Multiple Consumers Process the Same Channel

In Spring Integration, having multiple consumers subscribed to the same channel can increase parallel processing capacity. It also creates race conditions when concurrent executions read and write shared state, update the same business entity, or complete out of the expected order.

Before fixing a bug, determine how the channel distributes messages. `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and `PublishSubscribeChannel` behave differently. In particular, multiple consumers listening to a channel does not always mean each consumer receives a copy of every message.

## 1. Distinguishing Message Distribution Models

| Channel | Distribution behavior | Implication with multiple consumers |
| --- | --- | --- |
| `DirectChannel` | Subscribable, synchronous, point-to-point | The dispatcher selects one subscriber per send. With multiple subscribers, the default strategy typically distributes round-robin. The handler runs on the message-sending thread. |
| `ExecutorChannel` | Subscribable, asynchronous, point-to-point | Selects one subscriber like `DirectChannel`, then hands work off to an executor. Multiple messages can be processed concurrently by worker threads. |
| `QueueChannel` | Pollable, stores messages in a queue | Multiple pollers or consumers pull messages from one queue. Each successful `receive` removes one item from the queue for one consumer to process. |
| `PublishSubscribeChannel` | Subscribable, broadcast | Every subscriber receives the message. With an executor, subscribers can run in parallel. This is intentional fan-out, not a group of competing consumers pulling one message. |

With `DirectChannel`, invoking the handler synchronously only means the handler runs on the thread calling `send`. If multiple threads send messages concurrently, the same handler can still be invoked simultaneously on multiple threads. `DirectChannel` does not automatically make a handler with shared state safe for concurrent execution.

With `QueueChannel`, multiple pollers can compete to pull items from the same queue. An item already taken by one `receive` will not simultaneously be taken by another poller. However, if the handler fails after receiving the message, whether the message is restored depends on the channel type, `MessageStore`, and transaction configuration. Never assume every processing error automatically returns the message to the queue.

`PublishSubscribeChannel` has completely different semantics: every subscriber is invoked. If two subscribers mutate the same mutable payload, they can overwrite each other's changes. If the goal is load-sharing so each message is handled by only one worker, use a point-to-point model or an appropriate queue.

## 2. Common Race Conditions

| Scenario | Cause | Symptom |
| --- | --- | --- |
| Lost update | Two consumers read the same value, compute new values, and overwrite each other | Counter or inventory count is lower than actual |
| Out-of-order update | Two messages for the same order or account are processed in parallel | Final state reflects stale data written after newer data |
| Shared mutable payload | Multiple processing branches hold references to the same mutable object | Fields change unpredictably; logs across branches are inconsistent |
| Duplicate business side effects | Retry or redelivery re-runs the handler after partial side effects already completed | Sending notifications twice, double-charging, or creating duplicate records |
| Correlation state contention | Multiple messages update the same message group in an aggregator simultaneously | Group is not released on time or aggregated output is unexpected |

### Lost Update Example

The following code is still unsafe even though it uses `ConcurrentHashMap`:

```java
private final ConcurrentMap<String, Integer> reserved = new ConcurrentHashMap<>();

void reserve(String sku) {
    int current = reserved.getOrDefault(sku, 0);
    reserved.put(sku, current + 1);
}
```

`getOrDefault` and `put` are two separate operations. Suppose two consumers both read `5`; both compute `6`, and then both write `6`. One reservation was lost.

If this is strictly an in-memory counter and per-SKU addition is the entire operation to protect, you can use a key-level atomic operation:

```java
void reserve(String sku) {
    reserved.merge(sku, 1, Integer::sum);
}
```

`merge` turns updating a single key into an atomic operation inside `ConcurrentHashMap`. This does not replace database transactions, does not protect state across multiple application instances, and does not enforce business rules such as stock limits on its own.

For critical business data, let the database enforce update conditions in a single atomic statement, for example:

```sql
UPDATE inventory
SET reserved = reserved + :quantity
WHERE sku = :sku
  AND reserved + :quantity <= available;
```

The consumer checks the number of updated rows to see whether the operation succeeded or exceeded the limit. With JPA, you can use optimistic locking via a `@Version` field; when a conflict is detected, reload the data and retry the entire operation in a new transaction. Pessimistic locks fit certain high-contention flows, but require evaluating lock hold times and deadlock risk.

## 3. Choosing the Concurrency Level Deliberately

Clarify the flow's objective before adding workers:

- If sequential processing on the sending thread is required, `DirectChannel` is the simplest choice. It can still receive concurrent calls from multiple producer threads.
- If work should be handed off to worker threads, use `ExecutorChannel` and bound both the executor's pool size and queue.
- If producers must be decoupled from consumers via a queue, use `QueueChannel` and configure pollers deliberately.
- If every branch must receive the message, use `PublishSubscribeChannel`; design payloads and side effects for broadcast semantics.

Example creating an `ExecutorChannel` with a bounded pool:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("si-worker-");
    return executor;
}

@Bean
MessageChannel workChannel(ThreadPoolTaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
```

The numbers above are only examples. Size the pool based on processing time, database connection count, downstream service capacity, and application resource limits. A bounded queue keeps in-memory backlog under control; monitor both queue saturation and the executor's task rejection policy.

When multiple flows subscribe to the same `workChannel`, `ExecutorChannel`'s dispatcher picks one consumer per message. For example, two flows can subscribe as follows:

```java
@Bean
IntegrationFlow consumerA(OrderHandlerA handler) {
    return IntegrationFlow.from("workChannel")
            .handle(handler, "handle")
            .get();
}

@Bean
IntegrationFlow consumerB(OrderHandlerB handler) {
    return IntegrationFlow.from("workChannel")
            .handle(handler, "handle")
            .get();
}
```

These two flows are competing subscribers receiving messages. They do not both receive the same message like two subscribers on a `PublishSubscribeChannel`. Even so, two different messages can still be dispatched to the same consumer at overlapping times when multiple worker threads exist.

With `QueueChannel`, the poller determines when the consumer calls `receive` and how many messages are fetched per cycle. `maxMessagesPerPoll` is the maximum number of messages processed in one poll; it is not the number of consumers. To increase concurrency, configure poller count or an executor appropriate for your Spring Integration version. Java DSL configuration example:

```java
@Bean
MessageChannel workQueue() {
    return new QueueChannel(500);
}

@Bean
IntegrationFlow queueConsumer(Executor workerExecutor, OrderHandler handler) {
    return IntegrationFlow.from("workQueue",
                    endpoint -> endpoint.poller(Pollers.fixedDelay(100)
                            .taskExecutor(workerExecutor)
                            .maxMessagesPerPoll(20)))
            .handle(handler, "handle")
            .get();
}
```

When deploying multiple pollers reading the same queue, check actual poll counts, concurrent task counts, and downstream capacity. Increasing `maxMessagesPerPoll` can increase the amount of work processed per poll cycle, but by itself does not guarantee more parallel processing threads.

## 4. Protecting Business Processing Order

Message send order does not mean handler completion order. With multiple producers, sends can overlap. With `ExecutorChannel` or multiple pollers, a message taken earlier can finish after a message taken later. `QueueChannel` defaults to queue order when retrieving messages, yet parallel processing can still make completion order differ from retrieval order.

If all messages are independent, parallel processing is usually suitable. If messages affect the same business aggregate, choose a key-based ordering mechanism:

1. **Partition by business key:** route messages with the same `orderId`, `accountId`, or `customerId` into the same partition/queue and process sequentially within that partition.
2. **Lock by key:** lock only the update section that needs serialization. An in-JVM Java lock does not protect multiple instances; when running multiple instances, use shared coordination or database locking.
3. **Optimistic locking:** use a version to detect when a consumer wrote against a stale version. Retries must re-read and recompute the entire change.
4. **Order constraints in data:** store event sequence/version and reject or defer events older than the already-applied state.

Avoid locking an entire handler with `synchronized` if the handler calls slow services or accesses the network. That usually hurts throughput and only synchronizes within a single instance. Use locks only after identifying the state to protect and an appropriate lock scope.

## 5. Combining Transactions, Retries, and Idempotency

A transaction protects a group of operations within the same transaction manager; it does not automatically resolve every race condition across consumers. Wrap reads, checks, and writes that must remain consistent inside the transaction. With `DirectChannel`, the handler runs synchronously on the sending thread and can join a transaction bound to that thread if properly configured. `ExecutorChannel` moves processing to another thread; a transaction context bound to the sending thread does not automatically propagate to the worker. Open a transaction at the consumer for the consumer's data operations.

Retries can also cause a message to be processed multiple times. For example, a handler successfully calls a payment service but times out before receiving the response. A retry may call the payment service again even though the first attempt already produced a side effect. Therefore, every message with side effects needs a stable idempotency key, typically an `eventId` or unique business ID.

A common pattern is recording `messageId` in an inbox table with a unique constraint, then updating business data in the same transaction:

```sql
INSERT INTO processed_message(message_id, processed_at)
VALUES (:messageId, CURRENT_TIMESTAMP);
```

If the key already exists, the consumer recognizes the message as already processed and skips the corresponding side effect. Recording in the inbox and updating business state must share the same transaction so you never end up in a "marked processed but not actually applied" state. For external services, pass an idempotency key if supported; otherwise, design reconciliation or handling for indeterminate outcomes.

Limit retry attempts, apply backoff for transient errors, and route unprocessable messages to an error flow or dead-letter channel for investigation. Never retry a permanent data error indefinitely. With `QueueChannel`, verify the exact message rollback/recovery behavior of the `MessageStore` in use; a business database transaction does not automatically ensure that pulling a message from every queue type rolls back atomically.

## 6. Considerations When Using Aggregators and Correlation

An aggregator groups multiple messages into a message group, typically based on a correlation key. Multiple messages sharing a correlation key can arrive concurrently, so the message group store, group update operations, and release conditions must match the system's concurrency level.

- Use a stable correlation key that clearly separates distinct business runs; do not group messages merely because they share a type.
- Choose an appropriate `MessageGroupStore`. When running multiple instances, the store and locking mechanism must coordinate across instances; in-memory locks within a single JVM are insufficient.
- Verify `sequenceNumber` and `sequenceSize` if split/aggregate flows rely on sequence numbers and expected message counts.
- Define handling for duplicate messages, late-arriving messages, expired groups, and groups that never satisfy release conditions.
- Ensure side effects after aggregation are also idempotent, because retries or message replays can cause the aggregated result to be processed again.

When suspecting a race in an aggregator, inspect correlation keys, group state in the store, locks in use, and logs of messages belonging to the same group. Do not look only at total message count, because two different groups can have the same item count while holding completely different states.

## 7. Diagnosing Race Conditions at Runtime

To reproduce and isolate a bug, you need visibility into which message is running on which thread and which business key it is mutating.

**Log with context.** Log `messageId`, `correlationId`, business key, endpoint name, and `Thread.currentThread().getName()`. You can enable Spring Integration message history to trace components traversed. Do not log sensitive payloads or dump all headers indiscriminately.

**Monitor queues and executors.** Observe queue depth, age of oldest message, active threads, pool size, queued tasks, rejected tasks, and handler duration. For pollers, track poll frequency, messages per cycle, and duration per poll. Continuously growing queues usually indicate consumption rate is lower than arrival rate.

**Track data conflicts.** Count optimistic locking failures, deadlocks, lock waits, unique constraint errors, retry counts, and messages entering error flows. If the same `orderId` or `accountId` appears across concurrent logs, check whether the flow needs key-based serialization.

**Capture thread state when stalled.** Thread dumps help locate `BLOCKED`, `WAITING`, or I/O-waiting threads; Java Flight Recorder can add data on contention, CPU time, and thread pool activity. Correlate those timestamps with queue depth and message logs to locate the bottleneck.

**Create controlled reproductions.** In concurrency tests, use `CountDownLatch` or `CyclicBarrier` to force two consumers to read state before writing. This exposes lost updates far more reliably than relying on `Thread.sleep`. Assert business invariants after processing many messages, including same-key cases, duplicates, and mid-flight errors. If the system requires ordering, verify ordering per key rather than assuming a single global order across the whole system.

## 8. Procedure When a Race Condition Is Found

1. Identify the actual channel and the endpoint types registered on it: subscriber, poller, aggregator, or service activator.
2. Identify the number of producer threads, consumers, executors, pollers, and application instances. Do not infer concurrency solely from bean or flow counts.
3. Pick a failing message and business key; reconstruct the timeline of reads, checks, writes, retries, and side effects for each consumer.
4. Classify the root cause: non-atomic update, out-of-order execution, mutable payload, duplicate processing, or message group contention.
5. Choose the right mechanism: atomic operations, transactions, optimistic/pessimistic locking, key partitioning, immutable payloads, or idempotency.
6. Test with multiple consumers and multiple instances if production runs distributed. Re-measure throughput, latency, queue depth, and retry rate after the fix.

A multi-consumer configuration is only safe when the data shared across consumers has explicit synchronization rules. Decide which work may run in parallel, which must be serialized by business key, and how the system recognizes that a message has already been applied. Once those three decisions are clear, choosing channels, executors, pollers, and transactions in Spring Integration becomes much easier to control.
