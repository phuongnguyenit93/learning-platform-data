# Troubleshooting Stuck Consumers in Spring Kafka

A stuck consumer is a condition where a consumer group stops making expected progress through records. Typical symptoms include growing consumer lag, stalled offsets, missing listener processing logs, a partition stalled for a long time, or continuous consumer rebalances. However, growing lag does not always mean a consumer is hung: a topic may receive records faster than processing capacity, consumers may not be assigned partitions yet, or a listener may be retrying a failing record.

To resolve it properly, determine what state the consumer is in: lacking partition assignments, not polling Kafka, polling while the listener is blocked, retrying, processing without committing offsets, or simply having no new records. Restarting the consumer before collecting evidence can destroy diagnostic clues and trigger redeliveries.

## 1. Understanding types of stuck consumers

There is no single root cause for a "stalled consumer." Classify by symptom:

| Symptom | What may be happening |
|---|---|
| Consumer has no partition assignments | Wrong group ID, subscription, unstable rebalances, topic lacks partitions, or concurrency exceeds partition count |
| Container stopped | Listener has auto-start disabled, was stopped via registry, or application has not finished startup |
| Container paused | Pause was intentionally requested or never resumed |
| Consumer polls but listener never finishes | Business code blocked, deadlocked, HTTP/DB call missing timeouts, or processing too slowly |
| Offsets not advancing while listener runs | Record retrying, listener spending a long time on one record, manual ack not called, or commits failing |
| Consumer continuously rebalancing | Poll interval/heartbeat breached, flaky network, instance restarts, or membership churn |
| No listener logs yet consumer errors occur | Deserialization, authentication, authorization, or failure before listener method invocation |
| Lag is 0 and no new records exist | Consumer may simply be idle normally, not stuck |

First identify `group.id`, topic, partition, offset, and the last time progress occurred. Never jump to conclusions from a single log line or one lag check.

## 2. Distinguishing idle, lagging, and stuck consumers

These three states are distinct:

- **Idle:** consumer is active and has no new records to process.
- **Lagging:** new records are written faster than the consumer processes them; lag grows or stays elevated.
- **Stuck:** consumer makes no progress despite remaining records to process, or the container/consumer is not operating as configured.

Example:

| Log end offset | Consumer committed offset | Lag | Interpretation |
|---:|---:|---:|---|
| 100 | 100 | 0 | Caught up; if no new records arrive, normal idle state |
| 150 | 140 | 10 | 10 records remaining; check processing speed |
| 500 | 140 | 360 | Large lag; check throughput and consumer health |
| 500 | 140 (unchanged long) | 360 | Potentially stuck, retrying a record, or not committing |
| 500 (unchanged) | 500 | 0 | No new data; not stuck |

Lag is the distance between log end offset and committed offset per partition. Rising lag shows the consumer is falling behind, though you should compare incoming publish rate and processing rate before declaring a failure.

One partition having high lag while others stay normal may point to skewed key distribution, one very slow record, or a single blocked consumer thread. Inspect lag per partition rather than looking only at total group lag.

## 3. General diagnostic workflow

Follow this order to preserve evidence:

1. Identify affected group ID, topic, listener ID, instance, and partitions.
2. Check group state, members, partition assignments, current offsets, log end offsets, and lag.
3. Check whether the container is running, paused, or stopped.
4. Cross-check producer, consumer, retry handler, DLT, and rebalance logs.
5. Capture thread dumps while the symptom is occurring.
6. Check HTTP/database/cache/locks that the listener is waiting on.
7. Check `max.poll.interval.ms`, `session.timeout.ms`, `max.poll.records`, AckMode, and error handler.
8. Choose an appropriate recovery action; restart only after capturing needed state.

If multiple instances are affected together, prioritize checking brokers, networking, authentication, and shared downstream dependencies. If only one instance or one partition is affected, focus on threads, assignments, key distribution, and specific records.

## 4. Inspecting consumer groups with Kafka CLI

Use `kafka-consumer-groups` to check per-partition progress:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service
```

Output typically includes columns:

- `TOPIC`, `PARTITION`: data location.
- `CURRENT-OFFSET`: offset committed by the consumer group.
- `LOG-END-OFFSET`: end offset of the partition per broker metadata.
- `LAG`: gap remaining from committed offset.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID`: member holding the partition, if any.

View detailed members and assignments on supported Kafka versions:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Option names and output formats can differ across Kafka versions/distributions. Use the CLI shipped with the running cluster.

Read results per partition:

- `CURRENT-OFFSET` static while `LOG-END-OFFSET` climbs: consumer is not keeping up or not committing.
- No members/assignments: check group state, listener startup, subscriptions, and join-group errors.
- Only one partition has high lag: check the consumer owning that partition, key skew, and the record currently being processed.
- Lag is 0: check whether log end offset continues increasing before calling it stuck.

Never use `--reset-offsets` as a first diagnostic step. Resetting offsets can skip or reprocess records; do it only with a business plan, approval, and reconciliation method.

## 5. Checking ListenerContainer in Spring Kafka

For listeners declared with `@KafkaListener`, use `KafkaListenerEndpointRegistry` to inspect the container:

```java
@Service
public class ListenerDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(ListenerDiagnostics.class);

    private final KafkaListenerEndpointRegistry registry;

    public ListenerDiagnostics(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void inspect(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener not found: " + listenerId);
        }

        log.info(
                "listener={} running={} pauseRequested={} paused={}",
                listenerId,
                container.isRunning(),
                container.isPauseRequested(),
                container.isContainerPaused());
    }
}
```

`isRunning()` reports the container's lifecycle state, not proof that the listener is actively processing records. `isPauseRequested()` indicates a pause has been requested; `isContainerPaused()` reflects the container's actual paused state. On concurrent containers, paused state must be understood across child consumers.

If `getListenerContainer()` returns null, check the annotation ID and when the endpoint is registered. Containers created directly as beans may not live in the registry; inspect the corresponding bean/container according to how the app declares it.

Never expose diagnostic APIs on public endpoints without authentication and authorization. Return only needed metadata, never consumer configs containing credentials.

## 6. Checking if the listener is blocked in business code

This is a common root cause: the Kafka consumer received a record, but the listener method cannot finish because it is waiting on a dependency.

Common scenarios:

- HTTP call lacking a connect timeout or read timeout.
- Database query waiting on a lock or exhausted connection pool.
- Synchronous call to an overloaded service.
- Unbounded `Future.get()`.
- `CountDownLatch.await()` or semaphore without a timeout.
- Deadlock from threads acquiring locks in inconsistent order.
- Runaway CPU loop or oversized payload processing.
- Slow file/network writes or stalled filesystem.

Measuring listener duration helps identify slow-processing records:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    long startedAt = System.nanoTime();
    OrderCreated event = record.value();

    try {
        if (event == null) {
            // Tombstone: handle according to compacted topic semantics.
            log.info(
                    "kafka.consume.tombstone topic={} partition={} offset={}",
                    record.topic(), record.partition(), record.offset());
            return;
        }

        orderService.process(event);
    }
    catch (RuntimeException exception) {
        log.error(
                "kafka.consume.failed topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset(), exception);
        throw exception;
    }
    finally {
        long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
        log.debug(
                "kafka.consume.finished topic={} partition={} offset={} durationMs={}",
                record.topic(), record.partition(), record.offset(), durationMs);
    }
}
```

The `finished` log only appears when the method returns. If the thread blocks indefinitely, this log never prints; capture a thread dump to see where the stack is waiting. In real applications, you can also log the event ID if present and safe to log.

Set explicit timeouts on HTTP clients, JDBC queries, lock acquisition, and all I/O operations. Timeouts must fit both the record-processing SLA and the `max.poll.interval.ms` budget.

## 7. Capturing thread dumps when consumers stall

Thread dumps provide critical evidence of what listener threads are doing. Capture them while the issue is occurring, ideally multiple dumps spaced a few seconds apart to separate progressing threads from wedged ones.

On JVMs supporting `jcmd`:

```bash
jcmd <PID> Thread.print
```

Or:

```bash
jstack <PID>
```

Locate listener/container threads and inspect the stack traces:

| Common stack trace | Possibility to check |
|---|---|
| `SocketInputStream.read` or HTTP client socket read | Unresponsive downstream, missing read timeout |
| JDBC driver / connection pool wait | Slow query, DB lock, or exhausted pool |
| `LockSupport.park`, `Object.wait`, `ReentrantLock` | Waiting on lock/condition or deadlock |
| Same business method repeated across dumps | Infinite loop or CPU-bound work |
| GC/safepoint or long thread pauses | Heap pressure, allocation rate, or stop-the-world pauses |
| Kafka consumer poll/fetch/coordinator code | Check brokers, networking, group coordination, and client state |

Do not judge solely from thread names. Read full stack traces and correlate with logs, metrics, thread states, CPU, and heap. Thread dumps can contain sensitive data in stack frames/arguments; store them in restricted locations.

## 8. Distinguishing max.poll.interval.ms and session.timeout.ms

These two timeouts solve different problems:

| Property | Meaning | Symptom when breached |
|---|---|---|
| `max.poll.interval.ms` | Maximum time allowed between `poll()` calls while in an active group | Consumer processes one poll too slowly, misses polling in time, and may leave group/rebalance |
| `session.timeout.ms` | Time broker waits for a valid heartbeat before considering the consumer disconnected | Consumer fails to heartbeat due to process/network/GC or client failure |
| `heartbeat.interval.ms` | Interval at which client sends heartbeats in the classic group protocol | Must be tuned alongside session timeout and network stability |

`max.poll.interval.ms` is not a timeout for individual SQL statements or HTTP requests. It is the ceiling between poll calls. If a listener spends too long processing a batch before the next poll, the consumer can breach this limit even while the process is healthy.

`session.timeout.ms` governs heartbeats and disconnected-member detection. Raising session timeout does not fix business code that blocks while still heartbeating; raising max poll interval does not fix broker/network issues breaking heartbeats.

Identify which exact timeout appears in logs and metrics before modifying settings.

## 9. Tuning max.poll.records and max.poll.interval.ms

`max.poll.records` caps the maximum records returned in a single poll. When a listener processes sequentially, larger batches extend the total processing time before the next poll.

Example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.records]": 50
        "[max.poll.interval.ms]": 300000
```

These are illustrative values only; do not copy them to production without measuring real processing durations.

Configuration selection process:

1. Measure p95/p99 processing duration for a single record.
2. Measure total duration of the largest batch the listener actually receives.
3. Account for retries, DB/HTTP timeouts, GC pauses, and pre-next-poll work.
4. Choose `max.poll.records` so a batch fits inside your processing budget.
5. Set `max.poll.interval.ms` above expected processing time with a sensible safety margin.
6. Monitor rebalances and lag after deployment.

Lowering `max.poll.records` shortens per-batch processing time, though it may slightly lower throughput due to more frequent polls. Raising `max.poll.interval.ms` delays detection of truly hung consumers; never use it to mask a dependency without timeouts.

If individual records inherently take a very long time, redesign the task, break work into smaller steps, or offload long-running work to a separate workflow. If offloading to another thread, ensure acknowledgment semantics, partition ordering, and lifecycle prevent committing offsets before work completes.

## 10. Checking concurrency and partition assignments

Spring Kafka can run multiple child consumers via the listener container's `concurrency` setting. However, useful consumers in a group are bounded by the number of assigned partitions.

Example with a 4-partition topic:

| Concurrency | Consumers able to receive partitions | Interpretation |
|---:|---|---|
| 1 | One consumer receives all 4 | Single processing thread |
| 2 | Each consumer receives roughly 2 partitions | Parallelism can scale |
| 4 | Each consumer receives one partition | Maximum consumer parallelism for this topic |
| 8 | Only 4 consumers get partitions; the rest stay idle | Raising concurrency alone does not increase throughput |

If a consumer holds no partitions, it is not automatically stuck. Check assignments and partition counts first. When concurrency exceeds partition count, surplus consumers simply receive no records.

When subscribing to multiple topics, overall assignment depends on partitions across all topics and the assignor strategy. Never judge solely from a single topic's partition count.

## 11. Checking pause, stop, and autoStartup

A consumer can stop receiving records due to intentional lifecycle actions:

- `autoStartup=false` prevents the listener from starting automatically on context initialization.
- An admin service called `stop()`.
- `pause()` was invoked for backpressure, with no path calling `resume()`.
- The listener container was stopped during deployment/shutdown.
- A dynamic listener was not registered yet, or registered with a different ID/topic.

Check `isRunning()`, `isPauseRequested()`, and `isContainerPaused()` via the registry. Cross-check audit or admin logs to see what changed the state.

If the consumer was paused due to downstream overload, fix the dependency first and resume per procedure. Do not keep resuming while the target system is still overloaded, as that generates more failures and retries.

Pausing keeps the consumer in the group via the container's pause mechanism; stopping closes the consumer and can trigger a rebalance. Pick the right operation for your operational goal.

## 12. Checking retries and error handlers

A failing record can stall offset progress while the consumer retries:

- `DefaultErrorHandler` can perform blocking retries according to its `BackOff`.
- Extended retries keep the listener container spending time on the same record.
- Large backoffs must be configured compatibly with the poll interval.
- Once retries exhaust, a recoverer can send the record to a DLT or perform other recovery actions.

For long backoffs, Spring Kafka offers `ContainerPausingBackOffHandler` to pause the container while waiting and continue polling safely. Verify exact APIs and configuration against your Spring Kafka version.

If a poison-pill record fails repeatedly, check whether the exception is retryable. Data/validation errors rarely heal on retry; classify exceptions and route to recovery/DLT by policy rather than retrying forever.

Never let a listener catch an exception and return normally if you want the error handler to retry. Exceptions must propagate back to the container properly.

## 13. Checking non-blocking retries and retry topics

With `@RetryableTopic`, Spring Kafka routes failing records to retry topics for later handling. Consumers on the main topic can move on to subsequent records; failed events wait on retry topics for the configured delay.

If operators watch only the main topic, they might mistake this for lost records or a stuck consumer. Inspect:

- Corresponding retry topics and delay intervals.
- Consumer groups reading the retry topics.
- Retry attempt and exception headers.
- The DLT once attempts exhaust.
- `KafkaBackoffException` or errors related to retry scheduling.

Non-blocking retries change relative processing order across events. If business logic requires strict per-key ordering, evaluate the impact of retry topics and how consumers handle out-of-order delayed events.

## 14. Checking deserialization errors before the listener

If a payload fails deserialization, the `@KafkaListener` method may never be invoked. Thus, seeing no logs at the start of the listener does not mean Kafka failed to deliver records.

Common causes:

- Producer and consumer using incompatible schemas/serializers.
- Malformed JSON types or missing required fields.
- Invalid or untrusted type headers.
- Incompatible Avro/Protobuf schemas.
- Corrupted or oversized payloads.

In Spring Kafka, `ErrorHandlingDeserializer` forwards deserialization errors into the container's error-handling/recovery pipeline. Inspect deserializer configs, consumer client logs, and the error handler. When using a DLT, verify the recoverer can handle records whose values were never deserialized into objects.

Never retry a malformed payload forever without a schema or data fix. Preserve raw bytes safely per policy, log source metadata, and route to the DLT for investigation.

## 15. Checking commits and acknowledgments

Offsets stalling even though the listener logs completion can stem from commit strategy issues:

- `AckMode.MANUAL` without calling `Acknowledgment.acknowledge()`.
- `AckMode.MANUAL_IMMEDIATE` used, but acknowledgment invoked from an unsupported thread/condition.
- Commit request failing due to a rebalance or broker error.
- Transaction aborting so offsets are not committed as expected.
- With `asyncAcks`, out-of-order acknowledgments causing the container to pause delivering new records until missing offsets are acknowledged.

Example manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-manual",
        containerFactory = "manualAckKafkaListenerContainerFactory"
)
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
```

Acknowledge only after business processing satisfies completion criteria. Acknowledging beforehand risks never redelivering the record if side effects later fail.

Check the container factory's actual AckMode. Never apply manual-ack assumptions to a listener running `RECORD`, `BATCH`, or Kafka transactions.

## 16. Checking downstream dependencies and app resources

A consumer can stay healthy yet be throttled by downstream dependencies:

| Dependency | Symptom | What to check |
|---|---|---|
| Database | Listener waiting on queries/connections | Query plans, locks, pool active/idle counts, connection timeouts |
| HTTP service | Threads waiting on sockets or retrying constantly | Connect/read timeouts, latency, circuit breakers, rate limits |
| Cache | Timeouts or exhausted connection pools | Cluster health, pool settings, DNS/network |
| Thread pool | Growing task queue, no idle workers | Pool size, queue capacity, task duration, rejections |
| CPU/heap | High CPU, long GC pauses | Thread dumps, GC logs, allocations, heap pressure |
| File/object storage | Slow I/O or hung requests | Timeouts, retry policies, throughput, permissions |

Put finite timeouts on every external call inside a listener. Combine circuit breakers and bulkheads when downstream systems can overload. If a dependency is down, perform a controlled consumer pause or let the error handler follow its designed retry policy.

Never use an unbounded thread pool to "free up" the listener. That turns the bottleneck into an unbounded task queue and can exhaust heap memory.

## 17. Checking brokers, network, and access permissions

If multiple consumers or services are impacted simultaneously, inspect infrastructure:

- Are brokers online and controller/leaders stable?
- Do partitions have valid leaders and healthy ISR?
- Does the network show packet loss, DNS failures, or connection resets?
- Are Kafka clients reporting authentication/authorization failures?
- Do ACLs permit the current topics and consumer groups?
- Are brokers saturating request queues, disks, or network bandwidth?
- Did TLS certificates expire or trust chains change?

A consumer unable to join a group or fetch records due to ACL/auth failures logs client errors even while the listener logs nothing. Check exceptions and broker audit logs; never fix it by temporarily granting superuser rights.

If producers also cannot write or AdminClient cannot fetch metadata, the problem almost certainly lies in the cluster, network, or security layer rather than listener code.

## 18. Metrics and alerts for detecting stuck consumers

Track metrics by group, topic, partition, and instance:

- Per-partition consumer lag and lag persistence duration.
- `records-consumed-rate` and publish rate.
- Kafka consumer client `records-lag-max` if available.
- Fetch rate/latency and commit rate/latency.
- `poll-idle-ratio-avg` to see how much time between polls is spent processing.
- Assigned partition count and group member count.
- Listener processing duration p95/p99.
- Retry rate, DLT rate, and records awaiting retry.
- Rebalance count, authentication failures, and consumer errors.

Exact metric names, tags, and availability depend on the Kafka client, Spring Kafka version, and metrics backend. Verify against your runtime versions; do not assume all metrics are exported out of the box.

Alerts should combine conditions:

- Lag exceeds a threshold for a sustained duration while log end offset keeps rising.
- Committed offset stays flat while new records arrive.
- Listener processing duration breaches SLA.
- Repeated rebalances or consumers continually leaving the group.
- Consumer holds assignments but consumes zero records while lag is positive.
- Unusual spike in retry/DLT rates.

Do not alert simply because a consumer receives no records for a while if lag is 0 and the topic has no new data.

## 19. Recovering consumers safely

Once the root cause is known, choose the smallest necessary intervention:

1. **Temporary downstream overload:** reduce load, restore the dependency, then resume or let policy-driven retries proceed.
2. **Slow listener processing:** fix timeouts/logic, reduce batch size, or tune the poll budget after measuring.
3. **Poison record:** classify exceptions, route to DLT per policy, and store metadata for controlled replay.
4. **Unintended container pause/stop:** identify what triggered the lifecycle action, then resume/start the specific listener ID.
5. **Deadlocked consumer thread or unrecoverable process:** save thread dumps/logs/metrics, stop the container cleanly, fix the cause, and restart.
6. **Broker/network/auth outage:** restore the cluster, network, or credentials; avoid endlessly restarting consumers en masse.

Before stopping/restarting:

- Record group state, assignments, current offsets, log end offsets, and lag.
- Save thread dumps and relevant logs.
- Check whether the listener is midway through uncommitted side effects.
- Verify consumers are idempotent or tolerate redelivery.
- Stop containers through lifecycle APIs/callbacks so in-flight work can finish and consumers close cleanly.

Restarting can redeliver uncommitted records. Never delete consumer groups, reset offsets, or skip records merely to make lag vanish.

## 20. Post-recovery verification

After the consumer resumes, verify with live data:

- Container is running and not unintentionally paused.
- Consumer group has expected members and partition assignments.
- Current offsets advance on affected partitions.
- Lag shrinks whenever processing rate exceeds publish rate.
- No rebalance loops or recurring poll interval errors occur.
- Listener processing duration returns within SLA.
- Retry topics and DLT do not grow abnormally.
- Downstream databases/APIs are not overwhelmed by backlog replay.
- Business side effects are not duplicated unexpectedly.

Do not treat a "consumer started" log line as proof the incident is over. Close the incident only when offsets/lag, business processing, and dependencies remain normal over a suitable observation window.

## 21. Testing stuck-consumer scenarios

In test/staging environments, proactively simulate scenarios:

1. Listener processing longer than `max.poll.interval.ms` to observe rebalances and redelivery.
2. Slow or unresponsive downstream HTTP calls; verify timeouts/circuit breakers trigger.
3. Database locks or exhausted connection pools; verify metrics and thread dumps reveal the wait point.
4. Send an undeserializable poison record; verify listener/error handler/DLT handle it properly.
5. Use manual ack and intentionally omit acknowledging; observe offsets and redelivery behavior.
6. Pause and resume the container; verify assignments and record processing.
7. Raise concurrency above partition count; verify idle excess consumers are understood correctly.
8. Restart the process mid-processing; verify idempotent consumers tolerate redelivery.

Use isolated topics/groups per test and wait on conditions with bounded polling rather than fixed `Thread.sleep()` as sole proof. When simulating failures, capture logs, consumer group descriptions, and metrics for before/after comparison.

## 22. Common mistakes

**Restarting consumers immediately upon seeing lag:** erases thread state and can trigger redelivery. Collect group state, logs, and thread dumps first.

**Raising `session.timeout.ms` to fix slow listeners:** session timeout governs heartbeat failure detection; slow polling relates to `max.poll.interval.ms`.

**Setting `max.poll.interval.ms` excessively high:** hides hung threads and delays failure detection. Measure batch duration and fix dependency timeouts instead.

**Raising concurrency past partition count:** unassigned surplus consumers are not stuck. Check assignments.

**Seeing a "processed" log and assuming offsets committed:** listener completion and broker offset commit are distinct milestones.

**Retrying poison records infinitely:** corrupt data does not heal on retry; classify exceptions and route to recovery/DLT.

**Seeing no listener logs and assuming Kafka stopped delivering:** deserialization failures occur before the listener method runs.

**Unpausing without checking downstream:** consumers pull the backlog immediately and overload the dependency further.

**Resetting offsets to clear lag:** can skip or replay records. Reset only under a reconciliation plan.

**Looking only at total lag:** a single partition or consumer can be bottlenecked. Inspect lag and assignments per partition.

## 23. Production runbook checklist

- Identify exact cluster, group ID, topic, listener ID, and instance.
- Compare current offset, log end offset, and lag per partition.
- Check members, assignments, and group state.
- Check container running, pause requested, and paused states.
- Cross-check listener, retry, DLT, rebalance, and Kafka client logs.
- Capture multiple thread dumps while the issue is active.
- Check HTTP/database/thread pool/CPU/GC and dependency timeouts.
- Distinguish `max.poll.interval.ms` from `session.timeout.ms`.
- Check `max.poll.records`, concurrency, partition count, and AckMode.
- Check deserialization and error handlers when listener logs are absent.
- Record offsets/lag before stopping or restarting.
- Never reset/skip offsets without a business plan.
- Verify idempotency and redelivery tolerance.
- After recovery, verify advancing offsets, falling lag, stable rebalances, and healthy downstream services.
- Document root cause, impact window, and preventive actions.

A stuck consumer is a symptom requiring multi-layer diagnosis: group assignments, poll loop, listener threads, error handling, offset commits, downstream dependencies, and brokers. Start with per-partition lag and group state, use thread dumps to locate blocking points, inspect poll/heartbeat timeouts, and intervene in lifecycle only after capturing evidence. True recovery means offsets keep advancing and business work completes safely—not merely that the process restarted.

## References

- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka – Consumer Group Protocol](https://kafka.apache.org/documentation/#intro_consumers)
- [Spring for Apache Kafka – Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka – Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
