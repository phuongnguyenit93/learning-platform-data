# Pausing an Entire Listener Container

Spring Kafka allows you to pause record consumption for a listener container without stopping the container entirely or closing the Kafka consumer. When `pause()` is called, the container instructs the consumers it manages to temporarily stop receiving records from their assigned partitions. The container continues polling to maintain its membership in the consumer group; when `resume()` is called, record consumption resumes.

Pausing an entire container is useful when downstream is overloaded, the application needs to perform maintenance on a dependency, the system needs to throttle processing speed, or a group of listeners must be temporarily paused during an operational state change. For a listener with concurrency, pausing the container endpoint applies to all child consumers of that endpoint.

## 1. How does pausing a container differ from stopping a container?

`pause()` and `stop()` serve different purposes:

| Behavior | `pause()` | `stop()` |
| --- | --- | --- |
| Receiving new records | Temporarily stops receiving records | No consumer polls because the container has stopped |
| Kafka consumer | Retained and continues polling | Consumer is closed when the stop process completes |
| Consumer group membership | Consumer stays active in the group | Consumer leaves the group; partitions may be reassigned |
| Resuming processing | Call `resume()` | Call `start()` to restart the container |
| Purpose | Temporary throttling/backpressure | Stopping the listener lifecycle |

Pausing is not an offset commit operation. Offsets still follow the configured `AckMode`, acknowledgements, and transactions. If a record has been processed but not yet committed, a subsequent failure or shutdown can still cause the record to be redelivered.

## 2. Pausing a listener container using KafkaListenerEndpointRegistry

For listeners declared with `@KafkaListener`, Spring Kafka registers the endpoint in `KafkaListenerEndpointRegistry`. You can retrieve the container by `id` and call `pause()` or `resume()`.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.created",
            groupId = "orders-projection")
    public void onMessage(String payload) {
        // Process event.
    }
}
```

Controlling the container by ID:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener container 'orders-listener' was not found");
        }

        container.pause();
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener container 'orders-listener' was not found");
        }

        container.resume();
    }
}
```

The `id` in `@KafkaListener` is the endpoint identifier used to look up the container. It differs from `groupId`: the group ID identifies the consumer group on Kafka, whereas the listener ID identifies the container within the Spring application.

## 3. Pausing all listener containers managed by the registry

When you need to temporarily pause all listener endpoints declared with `@KafkaListener`, iterate through `registry.getListenerContainers()` and call `pause()` on each container:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class AllListenersControlService {

    private final KafkaListenerEndpointRegistry registry;

    public AllListenersControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseAll() {
        registry.getListenerContainers()
                .forEach(MessageListenerContainer::pause);
    }

    public void resumeAll() {
        registry.getListenerContainers()
                .forEach(MessageListenerContainer::resume);
    }
}
```

`getListenerContainers()` returns the containers managed by the registry. If the application creates and manages containers manually outside the registry, you must keep references to those containers and pause/resume them separately. Limit the control scope to the exact listeners the operational action needs to affect; do not assume a registry includes every manually created container.

If an endpoint uses `concurrency = "3"`, the registry returns the corresponding endpoint container; it is a `ConcurrentMessageListenerContainer` managing three child containers. Calling `pause()` on the parent container requests the child consumers to pause without needing to iterate through each thread manually.

## 4. Pause operates asynchronously on the consumer thread

The `pause()` and `resume()` methods are designed to be callable from application threads. The call submits a control request; the actual pause/resume operation on the Kafka consumer executes on the container's consumer thread.

Therefore, immediately after calling `pause()`, you should not assume the consumer is already in the paused state. Two states must be distinguished:

| API | Meaning |
| --- | --- |
| `isPauseRequested()` | The container has received a pause request |
| `isConsumerPaused()` | The consumer has actually transitioned to the paused state |

Example of checking status:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

container.pause();

boolean requested = container.isPauseRequested();
boolean paused = container.isConsumerPaused();
```

Right after `pause()`, `requested` may be `true` while `paused` is still `false`. Administrative applications should wait for the actual consumer state or monitor container events instead of returning a "pause completed" message as soon as the command is issued.

## 5. How does the container handle records already in the poll?

A Kafka consumer can return multiple records in a single `poll()`. When a container receives a pause request while processing records from the current poll, the default behavior is to finish processing the already-fetched records and then pause before the next poll.

```text
poll() returns: R1, R2, R3, R4
                 |
                 v
            Process R1
                 |
           pause() is called
                 |
                 v
            Process R2
                 |
                 v
            Process R3
                 |
                 v
            Process R4
                 |
                 v
          Consumer pauses
                 |
                 v
        No new records received
```

This avoids abandoning an already-polled batch of records, but it means pausing does not necessarily stop the listener immediately. If the previous poll returned many records or each record takes a long time to process, the time between requesting a pause and the consumer actually pausing can be significant.

## 6. Using pauseImmediate when an earlier stop is needed

Spring Kafka supports `pauseImmediate` on container properties. When enabled, the container pauses after processing the current record instead of continuing to process all remaining records from the previous poll.

```java
factory.getContainerProperties().setPauseImmediate(true);
```

This setting is useful when the application needs to react quickly to backpressure and does not want to process all remaining records from the current poll. For a record listener, the container can hold the records that have not yet been passed to the listener to deliver them after resuming. For a batch listener, the listener invocation receives the entire batch as a single unit; it cannot stop mid-method in a batch invocation as if each record were a separate call.

`pauseImmediate` does not cancel in-progress work and does not roll back side effects that have already occurred. If the listener is currently processing a record, the container must wait for a safe point in that execution before pausing. Test this behavior with your actual listener type and AckMode.

## 7. Resuming and continuing record consumption

Call `resume()` to instruct the container to resume receiving records from its assigned partitions:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isPauseRequested()) {
    container.resume();
}
```

`resume()` is also a request applied on the consumer thread. Once the consumer has resumed, the next poll can return records waiting on Kafka. If the listener has concurrency, resuming the parent container applies to the corresponding child consumers.

Resuming does not guarantee that the backlog will be processed immediately. The resumption rate depends on partition assignment, poll interval, listener processing time, consumer lag, and downstream capacity.

## 8. Pausing the entire container when downstream is overloaded

A common scenario is that a listener reads from Kafka faster than the database can write. If it keeps receiving records, the application can accumulate pending work, exhaust the connection pool, or grow heap usage.

You can pause the container when downstream metrics exceed a threshold:

```text
Database pool usage / queue depth / latency
                 |
                 v
        Exceeds HIGH threshold
                 |
                 v
        pauseAllListeners()
                 |
                 v
       Downstream recovers
                 |
                 v
        Drops below LOW
                 |
                 v
       resumeAllListeners()
```

You should use two distinct HIGH and LOW thresholds (hysteresis) to avoid continuous pausing/resuming when metrics fluctuate around a single threshold. For example, pause when the connection pool reaches 90%, and only resume when it drops below 65% and latency remains stable for a period of time.

Orchestration pseudo-code:

```java
public void onDownstreamPressure(DownstreamMetrics metrics) {
    if (metrics.poolUsage() >= 0.90 || metrics.queueDepth() >= 1_000) {
        listenerControl.pauseAll();
        return;
    }

    if (metrics.poolUsage() <= 0.65 && metrics.queueDepth() < 300) {
        listenerControl.resumeAll();
    }
}
```

This is illustrative logic. In a real application, you need debounce/stabilization time, ensure only a single component is responsible for controlling state, and have a mechanism to handle service restarts while paused.

## 9. Pausing does not stop Kafka from receiving data

Pausing a listener container only stops the consumer from fetching records to deliver to the listener. Producers and brokers continue operating; new records continue to be written to the topic if producers send them.

Therefore, during an extended pause:

- Consumer lag increases because the read offset does not advance.
- Kafka retains records according to the topic's retention and cleanup policy.
- Broker storage continues to be consumed by new data.
- Upon resuming, the consumer must process the accumulated backlog.

Pausing is consumer-side backpressure, not end-to-end flow control across the entire system. If you need to reduce event generation rates, you may need to throttle producers, limit incoming requests, or apply quotas/rate limits upstream.

## 10. Pausing and consumer group membership

While paused, Spring Kafka continues polling the consumer to maintain liveness in the group. The consumer receives no new records from paused partitions but remains in the group and retains its assignment under normal conditions.

This differs from stopping the container, closing the consumer, or letting the consumer go too long without polling. Those situations can cause the member to leave the group or be considered inactive, leading to a rebalance.

Pausing does not prevent all types of rebalances. Rebalances can still occur when topic partitions change, other members join/leave the group, subscriptions change, or infrastructure errors happen. After a rebalance, the container continues coordinating pause/resume based on its state and the new assignment; verify this behavior in the Spring Kafka version you are running.

## 11. Pausing all endpoints has broad impact: access control is required

If you expose pause/resume functionality via REST or an admin UI, it is an operation that directly affects event processing progress. Only expose the endpoint to trusted operators or orchestration systems.

An administrative API should:

- Enforce dedicated authentication and authorization for pause/resume.
- Audit the caller, timestamp, reason, and listener scope.
- Return both the requested state and the actual consumer state.
- Trigger alerts when a container remains paused longer than allowed.
- Provide a controlled resume mechanism after maintenance or when downstream recovers.
- Avoid having multiple systems control the same container without a clear state owner.

Do not automatically resume simply because the application just started if the pause state is coordinated by an external maintenance workflow. Conversely, if pausing is only a temporary in-memory state, establish a clear recovery policy after restarts because a newly started container may begin in the running state.

## 12. Container pause vs. partition pause

Pausing the entire container affects every partition managed by the consumers in that container. If only one partition is hot or downstream processes data independently per partition, you may want to pause a specific partition instead of the whole container.

| Scope | API/concept | When to use |
| --- | --- | --- |
| Entire endpoint | `MessageListenerContainer.pause()` | Temporarily stop all partitions managed by the endpoint |
| Resume entire endpoint | `MessageListenerContainer.resume()` | Allow the endpoint to receive records again |
| Single partition | `pausePartition(TopicPartition)` | Throttle a specific partition |
| Resume single partition | `resumePartition(TopicPartition)` | Reopen a specific partition |

Partition pausing comes with the additional requirement of identifying which consumer owns the partition and how to handle rebalances. If the goal is to pause the entire listener endpoint, using `pause()` is simpler and more consistent.

## 13. Monitoring pause status

Do not just record that a pause command was called. You should observe both the request and the actual state:

| Information | Purpose |
| --- | --- |
| Listener ID | Know which endpoint is paused |
| `isPauseRequested()` | Know the container has received the pause request |
| `isConsumerPaused()` | Confirm the consumer has actually paused |
| Pause duration | Detect containers paused for too long |
| Consumer lag | Measure the backlog accumulated during the pause |
| Downstream health | Determine the condition for resuming |
| Rebalance events | Detect assignment changes while paused |

Spring Kafka emits application events related to consumer pause/resume in supported versions. You can use an event listener to record state, though critical operational state should still be checked from the container and application metrics.

## 14. Testing pause/resume

Integration tests should verify that the consumer genuinely stops delivering new records and resumes after calling resume.

A scenario with Embedded Kafka:

1. Create a test topic and a listener with a fixed `id`.
2. Send a record and verify the listener receives it.
3. Call `pause()` through `KafkaListenerEndpointRegistry`.
4. Wait until `isConsumerPaused()` returns `true`.
5. Send additional records while paused.
6. Verify the listener does not receive the new records within a controlled observation window.
7. Call `resume()` and wait for the consumer to receive the backlog.
8. Verify all records are processed after resuming.

For listeners with concurrency greater than one, check the pause state of the endpoint container and ensure none of the child consumers deliver new records. Do not check only `isPauseRequested()` because the request may not have been applied yet.

You should also test:

- Calling pause while the listener is actively processing a record.
- `pauseImmediate=true` with both a record listener and a batch listener.
- Multiple pause/resume cycles and calling resume when the container is not paused.
- Container restarts or rebalances while paused.
- A backpressure controller with hysteresis that does not oscillate between pause/resume.
- Offsets/acknowledgements not being committed unintentionally.

Use `BlockingQueue`, `CountDownLatch`, or Awaitility to synchronize tests. Avoid using short `Thread.sleep` calls as proof that the consumer has paused; wait for the actual state with a timeout.

## 15. Common pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Still receives a few more records after calling pause | Pause request is applied on the consumer thread after processing already-polled records | Wait for `isConsumerPaused()`; consider `pauseImmediate` |
| `isPauseRequested()` is true but consumer is not paused yet | Consumer thread has not processed the request yet | Monitor `isConsumerPaused()` and application latency |
| Some listeners are still running | Only paused one endpoint or missed containers outside the registry | Iterate over all containers within the managed scope |
| Paused everything but backlog keeps growing | Producers/brokers continue receiving records | Throttle upstream or accept rising lag during the pause |
| Consumer triggers rebalance during a long pause | Container was stopped, poll loop stopped running, or group changed | Distinguish pause from stop and inspect poll/rebalance logs |
| Resume does not show records immediately | Consumer has not applied resume yet or partition has no new records | Wait for resumed state, check assignment and lag |
| Continuous pause/resume | Backpressure threshold fluctuates around a single value | Use HIGH/LOW thresholds, debounce, and stabilization periods |
| Container restarts and receives records despite previous pause | Pause state is runtime state, not durable configuration | Persist orchestration state externally if recovery after restart is needed |

## 16. Operations checklist

- [ ] Each `@KafkaListener` requiring control has a stable `id`.
- [ ] Identify the exact container scope to pause; do not confuse `id` with `groupId`.
- [ ] Use `KafkaListenerEndpointRegistry` for annotation-managed endpoints.
- [ ] Use `pause()`/`resume()` instead of `stop()`/`start()` for temporary throttling.
- [ ] Distinguish between `isPauseRequested()` and `isConsumerPaused()`.
- [ ] Understand that already-polled records may continue to be processed before pausing completes.
- [ ] Enable `pauseImmediate` only after testing its semantics with record/batch listeners.
- [ ] Monitor consumer lag and pause duration.
- [ ] Use HIGH/LOW thresholds to prevent state oscillation.
- [ ] Enforce admin permissions, auditing, and a resume policy.
- [ ] Maintain integration tests with realistic concurrency.

## 17. Conclusion

Pausing an entire listener container lets you temporarily stop receiving records from the partitions managed by an endpoint while keeping the consumer active in its group and continuing to poll. Use `KafkaListenerEndpointRegistry` to retrieve a container by listener ID or iterate over `getListenerContainers()` to pause/resume all registry-managed endpoints. With `ConcurrentMessageListenerContainer`, a pause request on the parent container applies to its child consumers.

Pause/resume commands are thread-safe requests executed on the consumer thread; distinguish `isPauseRequested()` from `isConsumerPaused()`. By default, the container finishes processing records from the current poll before pausing; `pauseImmediate` lets record listeners stop after the current record. Pausing does not commit offsets, stop producers, or prevent backlog growth on the broker. Use it as a monitored backpressure mechanism combined with metrics, hysteresis thresholds, access controls, and testing for safe resumption.

## References

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — KafkaListenerEndpointRegistry API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html)
- [Spring for Apache Kafka — MessageListenerContainer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/MessageListenerContainer.html)
- [Apache Kafka — KafkaConsumer pause/resume](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
