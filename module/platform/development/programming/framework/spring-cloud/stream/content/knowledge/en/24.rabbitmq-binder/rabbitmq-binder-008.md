# TTL, Queue Expiration, Length Limits, and Overflow

RabbitMQ provides multiple mechanisms to bound queue lifecycle and capacity. Message TTL determines how long a message is allowed to wait in a queue. Queue expiration determines how long an unused queue remains before the broker deletes it. Queue length limits bound the number of messages or total body size in the backlog. When a limit is reached, the overflow policy decides whether the broker drops older messages or rejects new ones.

The Spring Cloud Stream RabbitMQ Binder provides properties to declare these limits when provisioning queues. Distinguish binder properties from RabbitMQ-managed policies, as both can affect a queue. Choosing the right limits helps control backlog, prevent keeping stale messages, reduce the risk of running out of memory/disk, and clearly define how publishers learn when a queue stops accepting data.

## 1. Distinguishing Message TTL and Queue Expiration

RabbitMQ uses the term TTL for two different objects:

| Mechanism | RabbitMQ argument/policy | Meaning |
|---|---|---|
| Per-queue message TTL | `x-message-ttl` / `message-ttl` | Limits how long a message is retained in the queue |
| Per-message TTL | `expiration` in AMQP message properties | Sets an individual expiration for a specific message |
| Queue expiration | `x-expires` / `expires` | Deletes a queue after a period of inactivity |

Message TTL does not delete the queue. Queue expiration is likewise not the lifetime of individual messages. For example, a queue can exist for many days while keeping messages for at most five minutes; or a temporary queue can be deleted after one hour with no consumers even if no message TTL is set.

With the RabbitMQ Binder, the key consumer properties are:

- `ttl`: how long messages are retained in the queue when the binder declares the queue, in milliseconds. The binder uses this setting to set queue-level message TTL (`x-message-ttl`).
- `expires`: how long a queue remains unused before the broker automatically deletes it, in milliseconds (`x-expires`).

For example: `ttl: 300000` means messages have a 5-minute lifetime in the queue. `expires: 3600000` means the queue can be deleted after one hour of being unused per RabbitMQ's definition. The two properties are not interchangeable.

## 2. Per-Queue Message TTL

Message TTL suits data that remains meaningful only within a certain time window. Examples:

- Delivery status updates useful only for 10 minutes.
- Data refresh requests that can be skipped if delayed too long.
- Transient device status events that do not need processing after a defined cutoff.
- Messages in a fast-processing queue that should not accumulate into stale backlogs.

Declaring TTL for an input binding's queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              ttl: 300000
~~~

Rabbit binder extension properties reside under `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`. The `ttl` value is in milliseconds; for example, `300000` equals 5 minutes. The queue provisioned by the binder for that destination/group applies this limit to messages waiting in the queue.

RabbitMQ guarantees that messages whose TTL has expired will not be delivered to consumers. The broker attempts to remove expired messages at or shortly after expiration. With classic queues, expired messages are typically removed when they reach the head of the queue; therefore, expired messages may still appear in queue statistics while blocked behind unexpired messages. Do not use TTL as a millisecond-accurate timer to trigger scheduled work.

If the queue has a dead-letter exchange (DLX), expired messages can be dead-lettered per broker configuration. Without an appropriate DLX, expired messages are discarded. Clearly decide whether expired data can be dropped or must be routed to an investigation/reconciliation flow.

## 3. Per-Message TTL

In addition to queue-wide TTL, RabbitMQ supports per-message expiration. Publishers set the AMQP `expiration` property as a numeric string in milliseconds. When both queue TTL and per-message TTL are present, RabbitMQ applies the shorter expiration.

Example with Spring AMQP `RabbitTemplate`:

~~~java
rabbitTemplate.convertAndSend(
    "orders.exchange",
    "orders.created",
    event,
    message -> {
        message.getMessageProperties().setExpiration("60000");
        return message;
    }
);
~~~

In this example, the message has an individual TTL of 60 seconds. This uses the Spring AMQP API directly to illustrate setting the AMQP message property. If your application sends via the Spring Cloud Stream Rabbit binder, check header mapping or message converter/producer customization mechanisms in your version before assuming an arbitrary header maps to `expiration`.

Per-message TTL is useful when messages in the same queue have different lifetimes. However, with classic queues, an expired message sitting behind an unexpired message may not be evicted immediately; it will not be delivered to consumers, yet may continue consuming resources until the broker can remove it.

## 4. Queue Expiration: Deleting Unused Queues

The Rabbit binder's `expires` property specifies how long a queue may remain unused before RabbitMQ automatically deletes it:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        replies-in-0:
          destination: rpc.replies
          group: temporary-client
      rabbit:
        bindings:
          replies-in-0:
            consumer:
              expires: 3600000
~~~

In this example, the queue can expire after one hour of non-use. RabbitMQ defines a queue as in use when it has active consumers; redeclaring the queue or calling `basic.get` also refreshes the usage timestamp. The `x-expires` value must be a positive integer, not 0.

Queue expiration is useful for temporary queues, such as RPC reply queues or queues created for short-lived consumers. It is usually inappropriate for long-lived business queues that must persist to retain messages while applications are stopped.

When a queue expires, the broker deletes the queue along with any remaining messages inside it. Do not treat queue expiration as an archival mechanism. If messages must be kept for audit or later processing, use a durable destination, DLQ, or dedicated storage.

## 5. Limiting Message Count with maxLength

`maxLength` sets a limit on the number of messages in a queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-length: 10000
~~~

When the queue reaches the 10,000-message limit, RabbitMQ applies the overflow behavior to decide which messages are dropped or which publishes are rejected. This is a broker backlog limit, not a limit on the total number of messages an application receives over its lifetime.

For classic queues, the length limit counts only ready messages (waiting to be delivered). Messages already delivered to consumers but not yet acknowledged (unacknowledged) do not count toward the limit. Quorum queues also count delayed messages, including delayed retries and messages awaiting at-least-once dead-lettering according to quorum queue semantics.

Therefore, `max-length: 10000` does not mean the total number of messages in flight across the entire pipeline—including messages currently being processed by consumers—is always under 10,000. Monitor `messages_ready` and `messages_unacknowledged` separately.

## 6. Limiting Size with maxLengthBytes

`maxLengthBytes` limits the total body size of messages in the queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        image-jobs-in-0:
          destination: image.jobs
          group: image-worker
      rabbit:
        bindings:
          image-jobs-in-0:
            consumer:
              max-length-bytes: 104857600
~~~

The value `104857600` equals 100 MiB. RabbitMQ sums message body lengths; message properties and protocol overhead are not counted toward this body-size limit. This is a backlog size limit, not a size limit on a single message.

You can configure `maxLength` and `maxLengthBytes` together. When either limit is reached, overflow behavior takes effect. Example:

~~~yaml
max-length: 10000
max-length-bytes: 104857600
~~~

The queue is bounded by whichever limit—message count or total bytes—is hit first. When message sizes vary widely, a byte limit often controls storage usage better than a count limit alone.

## 7. Choosing Overflow Behavior

RabbitMQ supports strategies for handling when a queue length limit is reached. The Rabbit binder currently provides the `overflowBehavior` property, with common values:

| Value | Behavior | Consequence |
|---|---|---|
| `drop-head` | Drops the oldest message at the head of the queue to make room for new messages | Old messages may be lost from the processing flow; if a DLX exists, dead-lettering depends on broker config |
| `reject-publish` | Rejects newly published messages when the queue is full | Publishers can receive `basic.nack` if publisher confirms are enabled and must handle send failures |

Example selecting rejection of new messages:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-length: 10000
              overflow-behavior: reject-publish
~~~

`drop-head` fits latest-state data where older updates can be discarded when backlog grows too large. Do not use this strategy for payment commands, balance changes, or events requiring complete processing unless a recovery mechanism exists.

`reject-publish` creates backpressure on the publisher. The publisher must observe publisher confirms/nacks and perform controlled retries or route failures to another workflow. Do not assume the boolean return value from an application-level send call accurately reflects every queue overflow scenario; configure and test the binder's publisher confirm/error mechanisms.

RabbitMQ also has a `reject-publish-dlx` variant in some broker versions, where rejected publishes are dead-lettered. However, the Rabbit binder's `overflowBehavior` property currently documents `drop-head` and `reject-publish`; do not set `reject-publish-dlx` in binder config if your binder version does not support that value. If advanced behavior is needed, manage the queue via RabbitMQ policies and verify broker compatibility.

## 8. Combining TTL, expires, and Queue Limits

A single queue can combine multiple limits:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              ttl: 300000
              expires: 86400000
              max-length: 10000
              max-length-bytes: 104857600
              overflow-behavior: reject-publish
~~~

Meaning:

- Messages are retained in the queue for at most 5 minutes if undelivered.
- The queue may be deleted after 24 hours of non-use.
- Backlog is capped at 10,000 messages or 100 MiB of bodies.
- When limits are reached, the broker rejects new publishes rather than dropping older messages.

Do not set a short `expires` on a business queue just to clean up old messages. Deleting the queue wipes out both the queue and its backlog. If you want messages to expire while the queue remains, use message TTL. If you want a temporary queue to vanish when no consumers remain, use queue expiration.

## 9. Dedicated Limits for DLQs

A DLQ is also a queue and can accumulate failed messages. The Rabbit binder provides dedicated properties to control DLQ lifecycle and capacity:

- `dlqTtl`: message TTL applied to the DLQ.
- `dlqExpires`: duration a DLQ remains unused before deletion.
- `dlqMaxLength`: maximum number of messages in the DLQ.
- `dlqMaxLengthBytes`: maximum total body size in the DLQ.
- `dlqOverflowBehavior`: overflow handling strategy for the DLQ.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-worker
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              dlq-ttl: 604800000
              dlq-expires: 2592000000
              dlq-max-length: 5000
              dlq-max-length-bytes: 52428800
              dlq-overflow-behavior: reject-publish
~~~

In this example, messages in the DLQ have a 7-day TTL; the DLQ queue can expire after 30 days of non-use; and the DLQ is bounded to 5,000 messages or 50 MiB. These limits should align with investigation windows and replay procedures. If the DLQ is deleted or overflows with `drop-head`, failed messages can be lost before they are handled.

`auto-bind-dlq` tells the binder to create the DLQ and link the dead-letter exchange. `republish-to-dlq` makes the binder republish failed messages with additional diagnostic headers such as exception message and stack trace. That covers consumer errors after retries; messages expiring by TTL or overflow can follow broker-level dead-letter behavior if the queue has a DLX. Distinguish consumer-reject dead-lettering from TTL/overflow dead-lettering.

## 10. Binder Properties vs. RabbitMQ Policies

The Rabbit binder can declare queue arguments when auto-provisioning queues. RabbitMQ also supports policies for centrally managing properties such as message TTL, queue expiration, max-length, max-length-bytes, and overflow.

Two common management approaches:

| Approach | When appropriate |
|---|---|
| Rabbit binder properties | The application owns queue provisioning and settings should travel with the binding |
| RabbitMQ policies | Operations manages limits centrally and needs to adjust policies without re-releasing apps |

If a queue already exists with arguments differing from what the binder tries to declare, RabbitMQ may reject the redeclaration with `PRECONDITION_FAILED` due to an incompatible queue declaration. Before changing TTL, expires, max-length, or queue type, inspect existing arguments and choose one consistent configuration source. Do not delete a production queue just to resolve a config conflict without assessing backlog and a data migration plan.

Policies allow changing certain limits dynamically without deleting the queue. However, check the precedence rules among client-provided arguments, user policies, and operator policies for your RabbitMQ version. Confirm effective values in the Management UI or via `rabbitmqctl list_queues` after applying changes.

## 11. Choosing Limits Based on Business Characteristics

No single set of TTL/length values fits every queue. Determine:

- How long does a message remain valuable?
- What is the maximum backlog the system can process before data becomes stale?
- What are the average and maximum sizes of a single message?
- When the queue is full, is dropping old messages or rejecting new publishes less damaging?
- Is there a DLQ and replay process to recover rejected/expired messages?
- How long can consumers remain offline while the queue must still be preserved?

Examples:

| Queue type | Business-driven TTL guidance | Overflow typically considered |
|---|---|---|
| Latest sensor state | Short; older readings quickly lose value | `drop-head` if dropping old state is acceptable |
| Payment commands | Do not set arbitrary TTL; business rules govern deadlines | `reject-publish` so publishers learn the queue is full |
| Thumbnail generation jobs | Moderate TTL matching processing deadline | `reject-publish` or bounded DLQ |
| Temporary reply queue | Queue `expires` to clean up when clients disappear | Do not use as storage |
| Investigation DLQ | Long enough TTL for operations and replay | `reject-publish` to avoid silently dropping failed messages |

The entries in this table illustrate business-driven choices rather than mandatory defaults. For financial or audit data, maintain an explicit retention policy and do not rely on queue TTL as a substitute for long-term storage.

## 12. Monitoring Queue Limits in Production

Metrics to observe:

- `messages_ready`: number of messages waiting for delivery.
- `messages_unacknowledged`: number of messages delivered but not yet acknowledged.
- `message_bytes_ready`: total body size of ready messages.
- Publish and consume rates.
- Count of publisher nacks/failed confirms when the queue overflows.
- Count of expired or dead-lettered messages.
- Age of the oldest message in the backlog.
- Count of temporary queues and expired queues.

The RabbitMQ Management UI and `rabbitmqctl list_queues` help inspect queue state. Example:

~~~bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged message_bytes_ready consumers
~~~

If `messages_ready` grows continuously, consumers may be slower than publishers or failing. If `messages_unacknowledged` grows, consumers may be holding too many deliveries or taking too long to process. Increasing `maxLength` only delays when the queue fills up; it does not fix a throughput bottleneck.

When `reject-publish` is used, enable and handle publisher confirms so the application knows whether the broker accepted or rejected a publish. When `drop-head` is used, monitor dropped/dead-lettered counts to detect data loss caused by limits.

## 13. Testing TTL, Queue Expiration, and Overflow

Do not only test that YAML starts cleanly. Test actual behavior against RabbitMQ:

1. Publish a message to a queue with a short TTL and no consumers; confirm the message expires and is not delivered.
2. Repeat with a configured DLX; confirm expired messages route to the dead-letter destination per policy.
3. Set `expires` on a temporary queue; stop the consumer, avoid redeclaring or calling `basic.get` for the configured duration; confirm the queue is deleted.
4. Create a queue with a small `max-length` and publish past the threshold; verify `drop-head` drops old messages or `reject-publish` rejects new messages.
5. Test `max-length-bytes` with messages of varying body sizes.
6. Confirm unacknowledged messages are not counted as ready messages in classic queues.
7. Test against an existing queue with different arguments and confirm deployment procedures handle `PRECONDITION_FAILED`.
8. Verify the DLQ has its own TTL, expires, and limits; confirm failed messages remain long enough for investigation.
9. Enable publisher confirms and simulate a full queue to confirm the publisher receives nacks and has retry/backpressure handling.
10. Test broker/consumer restarts and verify durable queues, persistent messages, and retention policies meet requirements.

The Test Binder can test binding configuration and function logic, but it does not fully simulate RabbitMQ TTL, queue deletion, dead-lettering, and overflow. Use a real RabbitMQ broker or Testcontainers to verify these behaviors.

## 14. Configuration Checklist

- [ ] Distinguished message TTL (`ttl`) from queue expiration (`expires`).
- [ ] Selected TTL based on how long a message retains business value.
- [ ] Understood per-message expiration and its relationship to queue TTL.
- [ ] Configured `max-length` and/or `max-length-bytes` based on processing capacity.
- [ ] Chosen the appropriate `overflow-behavior`: `drop-head` or `reject-publish`.
- [ ] If rejecting publishes, publisher confirms/nacks are observed and handled.
- [ ] Evaluated whether expired messages must be dead-lettered or can be discarded.
- [ ] Set dedicated limits for the DLQ if a DLQ is provisioned.
- [ ] Clarified whether queues are governed by binder settings or RabbitMQ policies.
- [ ] Checked existing queue arguments to avoid `PRECONDITION_FAILED`.
- [ ] Monitored ready counts, unacknowledged counts, byte backlog, and message age.
- [ ] Integration tested TTL, queue expiration, overflow, and DLQs with real RabbitMQ.

TTL, queue expiration, and queue length limits solve three different problems: stale messages can expire, temporary queues can be cleaned up when unused, and backlogs can be bounded by count or size. In the Spring Cloud Stream Rabbit binder, configure `ttl`, `expires`, `max-length`, `max-length-bytes`, and `overflow-behavior` according to broker semantics, while designing DLQs, publisher confirms, and monitoring so expiration and full-queue events become predictable and recoverable behaviors.

## References

- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl)
- [RabbitMQ — Queue Length Limit](https://www.rabbitmq.com/docs/maxlength)
- [RabbitMQ — Configurable Limits](https://www.rabbitmq.com/docs/limits)
