# Consumer Rebalancing Continuously or Slow to Commit Offsets

A Spring Cloud Stream application can start up normally yet have its Kafka consumer repeatedly receive and lose partitions, see consumer lag grow even when CPU is low, or log offset commit failures. This class of incident easily causes duplicate message processing, unstable throughput, higher latency, and confusion between consumer group errors and business logic errors.

This lesson walks through diagnosing **Kafka consumers using the regular Kafka Binder** in Spring Cloud Stream: identifying real rebalances, separating processing time from commit time, reading Kafka client logs and metrics, checking `max.poll.interval.ms`, heartbeat/session timeouts, group membership, acknowledgements, retries, networking, and the broker coordinator. The final sections highlight differences from the Kafka Streams Binder, RabbitMQ/Pulsar, and how to run regression tests. Do not change the group ID, reset offsets, or disable acknowledgements just to make a lag chart look prettier.

## 1. Identify the Exact Symptom Before Adjusting Configuration

Common signals:

- Repeated logs of `Revoking previously assigned partitions`, `partitions revoked`, `partitions assigned`, or `Successfully joined group` despite no deployment or major traffic change.
- Consumer group repeatedly cycling between stable and rebalancing states; member IDs and partition assignments changing frequently.
- Logs of `CommitFailedException`, `RebalanceInProgressException`, or `Offset commit failed`.
- Committed offset not advancing as expected while the handler still logs processed messages.
- Kafka consumer lag rising and throughput dropping; already-processed messages may be replayed after restarts or rebalances.
- Broker responding slowly to heartbeats/commits, request timeouts, or application restarts triggered by OOM, liveness probes, or rolling deploys.

**Not every rebalance is an error.** Rebalancing is normal when members join or leave a group, topic partitions change, or the group coordinator moves. The problem is rebalances repeating at abnormal frequency, impacting SLOs, or dragging on too long.

## 2. Three Phenomena Easily Confused

| Phenomenon | Prominent Signs | What to Measure |
|---|---|---|
| **Rebalance storm** | Repeated revoke/join/assign cycles, changing generations/members | Rebalance rate, last-rebalance time, member count, pod restarts |
| **Slow commit requests** | Rising `commit-latency-avg/max`, commit timeouts, or coordinator errors | Client commit latency, request/network latency, coordinator health |
| **Committed offset advances slowly** | `CURRENT-OFFSET` stays flat or inches up; not necessarily slow Kafka commits | Ack mode, completed record count, ack timing, retries/batches |

Consumer lag is normally computed from the log end offset and the group's committed offset. While processing a batch before committing, lag can appear high even though the app has already fetched many records. Conversely, the committed offset can advance faster than business completion if the app acks too early or enables inappropriate auto-commits. Therefore, compare **consumer position, committed offset, end offset, and business processing completion** before concluding the root cause.

## 3. How Kafka Consumer Groups and Rebalancing Work

Inside a consumer group, Kafka assigns partitions to the active consumer members. Each partition is normally processed by only one consumer in the same group at a time. Whenever membership changes, Kafka must update assignments.

Components to distinguish:

- **`group.id`**: group name; in Spring Cloud Stream this usually comes from `spring.cloud.stream.bindings.<binding>.group`.
- **Group coordinator**: the broker managing membership and offset commits for the consumer group.
- **Member/instance**: a consumer participating in the group; a single Spring Boot instance can create multiple Kafka consumers when `concurrency` is greater than 1.
- **Assignment**: the list of partitions assigned to a consumer.
- **Heartbeat**: signal telling the coordinator that a member is still alive.
- **Poll loop**: `poll()` calls fetching records; when a listener processes too slowly, the next poll is delayed.
- **Offset commit**: persists group progress; the committed offset is normally **the next position to read**, not the last processed offset.

For example, after successfully processing the record at offset 41, the committed value is typically 42. Do not misdiagnose an off-by-one offset in `kafka-consumer-groups.sh` output.

## 4. Gather Evidence in the First 10 Minutes

Before tweaking parameters, gather:

1. Incident start time, application/binder/Kafka client versions, and most recent deployment changes.
2. Kafka cluster name, topic, group ID, binding name, partition count, pod count, and `consumer.concurrency`.
3. Revoke/assign, heartbeat, coordinator, commit, and exception logs aligned on the same timeline.
4. CPU, GC pauses, heap, thread dumps, function execution duration, and dependency latency.
5. Consumer group lag and member assignments before and after rebalances.
6. Commit latency/rate, rebalance rate, and poll interval metrics from the Kafka client.
7. Container restarts, HPA scaling events, graceful shutdowns, and readiness/liveness probe timings.

Do not change the group ID, delete topics, reset offsets, or run consumer-group-mutating commands during evidence collection. Those actions can erase the root cause or trigger mass message replays.

## 5. Inspect the Group with Kafka Tools

Example commands on a host with the Kafka CLI and broker access:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service
~~~

Typical fields in the output:

~~~text
GROUP         TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-service orders.events  0          12500           12800           300
order-service orders.events  1          12480           12600           120
~~~

Inspect members:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service --members --verbose
~~~

If your CLI version supports it, check overall state:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service --state
~~~

Interpretation:

- `CURRENT-OFFSET`: the group's committed offset on that partition; not necessarily the record currently being processed.
- `LOG-END-OFFSET`: the log end offset as seen by the tool; can be affected by isolation level and transaction state.
- `LAG`: offset difference; grows when production outpaces the group's offset progression.
- `MEMBER-ID`/`CLIENT-ID`/`HOST`: helps spot a pod/consumer repeatedly joining and leaving the group.

Take multiple snapshots 30–60 seconds apart to separate steadily growing lag from normal fluctuation. If the group keeps changing members without pod restarts, focus on poll/heartbeat/network. If members churn in lockstep with pod restarts, investigate process crashes and health probes first.

## 6. Read Logs by Cause Category

| Log / Symptom | First Hypothesis | Verification Step |
|---|---|---|
| `max.poll.interval.ms` exceeded | Handler/retry/batch blocks poll too long | Measure poll-to-poll gap, `max.poll.records`, and processing time |
| `session timeout`, heartbeat failure | Coordinator does not receive heartbeats in time | Check GC pauses, network, coordinator, and session config |
| `CommitFailedException` | Consumer is no longer a valid member / generation changed | Look for a rebalance right before commit; check poll interval |
| `RebalanceInProgressException` | Rebalance in progress during commit | Trace poll/rejoin and check rebalance frequency |
| `NotCoordinator` or `CoordinatorNotAvailable` | Coordinator moving / broker hard to reach | Check broker health, metadata, network, and client retries |
| `FencedInstanceIdException` | Multiple consumers share the same static `group.instance.id` | Ensure unique IDs per consumer instance |
| Partition revoke/assign right at deploy time | Rolling deployment or autoscaling | Check rollout policy, readiness, and graceful termination |
| Offset stays flat with no commit error | Ack has not fired or batch is unfinished | Check ack mode, handler completion, and manual acknowledgement |

Do not conclude the broker is slow from a single `CommitFailedException` line. Often a commit error is a **consequence** of a rebalance: the member was evicted or an older generation lost permission to commit.

## 7. Common Cause: Exceeding max.poll.interval.ms

`max.poll.interval.ms` caps the maximum interval between two `poll()` calls in a consumer group. The modern Kafka client default is usually **300,000 ms (5 minutes)**. If the message-processing thread takes too long and fails to return to `poll()` in time, Kafka treats the consumer as stalled.

Typical sequence:

~~~text
poll() returns up to N records
    |
    v
Listener handles records (DB/HTTP/retries)
    |
    +-- processing and backoff exceed max.poll.interval.ms
    |
    v
Consumer loses valid membership / group assignment changes
    |
    v
Commit attempted with stale generation -> failure
    |
    v
Partitions reassigned, records may be replayed
~~~

For example, a poll returns up to 500 records, each taking an average of 800 ms sequentially. Total processing can reach ~400 seconds, **exceeding 300 seconds**, before counting retries and network overhead. The consumer loses membership before committing. That is a problem of **doing too much work between polls**, which cannot be cured by simply adding brokers.

Priorities:

1. Measure duration of each handler, including dependencies, serialization, and retries.
2. Lower `max.poll.records` to cap the work per poll.
3. Break down or optimize batching, reduce blocking I/O, and set timeouts on dependencies.
4. Check batch mode and error handlers; huge batches can stretch a single processing cycle.
5. Increase `max.poll.interval.ms` only after measuring and with clear justification, since too large a value delays detection of a hung consumer.

Do not assume `max.poll.records` limits how many records Kafka fetches from the broker in a single network fetch; it limits how many records a single `poll()` call returns to the application.

## 8. Configuring Spring Cloud Stream for Oversized Polls

Example using the **regular Kafka Binder** with bean `Consumer<Message<OrderEvent>> handleOrder`:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: order-service
          consumer:
            concurrency: 3
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              ack-mode: BATCH
              configuration:
                max.poll.records: 100
                max.poll.interval.ms: 300000
~~~

This configuration illustrates a **100 records/poll cap** and an explicit `ack-mode: BATCH` choice for clarity. It is **not a universal recommendation**: if your application uses `RECORD`, `MANUAL`, or transactions, do not switch ack modes without understanding redelivery and duplicate requirements.

Kafka client properties live under `spring.cloud.stream.kafka.bindings.<binding>.consumer.configuration`; generic Spring Cloud Stream properties like `concurrency` live under `spring.cloud.stream.bindings.<binding>.consumer`; `ack-mode` sits under the Kafka binder's consumer branch. If the binding was aliased via `spring.cloud.stream.function.bindings`, use the exact **effective binding name** in both branches.

Benchmark with large messages, peak load, and retries—not just tiny records in a local environment.

## 9. Another Cause: Session Timeout and Heartbeats

`session.timeout.ms` is how long the coordinator waits for heartbeats before considering a member dead. It is distinct from `max.poll.interval.ms`:

| Property | What Does It Guard? | When Exceeded |
|---|---|---|
| `max.poll.interval.ms` | Consumer poll/processing progress | Member can lose partition ownership even while heartbeats continue |
| `session.timeout.ms` | Member liveness via heartbeats | Coordinator evicts the member for missing heartbeats |
| `heartbeat.interval.ms` | Heartbeat cadence in the classic protocol | Too infrequent or slow network can trigger timeouts |

Causes of missed heartbeats include:

- Long JVM stop-the-world GC pauses, CPU throttling, or resource exhaustion.
- Unstable network to the group coordinator, or slow/failing DNS/TLS/SASL.
- Overloaded coordinator broker, failover in progress, or issues on internal `__consumer_offsets` partitions.
- Container kills/restarts, rolling deployments, node drains, or overly sensitive liveness probes.

**Important for newer Kafka versions:** consumers can use `group.protocol=classic` or `group.protocol=consumer`. With **classic**, client parameters `heartbeat.interval.ms` and `session.timeout.ms` apply; heartbeats must stay smaller than the session timeout, and many guides recommend no more than about one-third. With the **consumer protocol**, heartbeat intervals and session timeouts are broker-controlled via `group.consumer.heartbeat.interval.ms` and `group.consumer.session.timeout.ms`; do not set classic client properties expecting them to take effect.

Do not multiply timeouts several-fold before identifying the cause; overly long timeouts delay real failover. If failures happen only during network drops or long GC pauses, fix the underlying infrastructure condition first.

## 10. Why Can a Single Pod Trigger Continuous Rebalances?

On Kubernetes, a consumer member can be repeatedly created and destroyed because:

- A liveness probe checks consumer lag or a remote dependency; when Kafka slows down, the probe restarts the pod and triggers a rebalance loop.
- `terminationGracePeriodSeconds` is too short; the Kafka consumer cannot close and leave the group gracefully during a rolling update.
- A deployment rollout creates too many new pods at once, constantly shifting member count.
- HPA scales up and down near a threshold without a stabilization window.
- Memory limit is too low (JVM `OOMKilled`), or CPU limits cause GC or scheduling stalls.
- Readiness/liveness probes fail to distinguish a temporarily unavailable broker from a genuinely hung process.

Operational inspection commands:

~~~bash
kubectl get pods -n orders -o wide
kubectl describe pod <pod-name> -n orders
kubectl get events -n orders --sort-by=.lastTimestamp
kubectl rollout status deployment/order-service -n orders
~~~

These commands are read-only observations; adjust namespace and deployment names for your environment. Correlate timestamps of pod restarts, rollouts, and HPA events with `partitions revoked` entries in the logs.

If rebalances correlate with deployments, fix rollout strategy and graceful shutdown before tuning `max.poll.interval.ms` or `session.timeout.ms`.

## 11. Group ID, Consumer Count, and Partition Assignment

In Spring Cloud Stream, `spring.cloud.stream.bindings.handleOrder-in-0.group` defines the consumer group for the binding. The actual number of members can exceed the pod count because each pod can spin up multiple consumer containers:

~~~text
Total consumer instances ~ pods × concurrency
Effective parallelism <= topic partition count
~~~

For example, 5 pods with `concurrency=4` create roughly 20 consumers in the same group. If the topic has only 12 partitions, some consumers will have no partitions to work on. This **does not automatically cause a rebalance storm**, but it increases join/leave churn during deploys or autoscaling.

Common mistakes:

- Two **unrelated services** accidentally share the same group ID and topic, competing for partitions instead of each service receiving all messages.
- The app changes group ID across deploys due to an environment variable or profile, creating a brand-new group with separate offsets.
- Different instances run with mismatched settings (topic subscriptions, partition assignors, group protocols), causing unstable joins/rebalances.
- Assigning duplicate `group.instance.id` values across multiple consumer instances, causing fencing.
- Using the binder's static partition assignment with `auto-rebalance-enabled=false` without aligning `instanceCount`/`instanceIndex` across all instances.

Never change the group ID just to "reset" rebalance behavior. That can cause the application to re-read or skip data depending on existing offsets and `auto.offset.reset`.

## 12. Static Membership and Cooperative Rebalancing

Two mechanisms can reduce group churn in suitable environments:

- **Static membership** via `group.instance.id`: helps Kafka recognize the same consumer instance across brief restarts. The ID must be **unique and stable per Kafka consumer**, not merely per pod if a pod runs with concurrency greater than 1. Duplicate IDs trigger fencing; long timeouts can also delay failover to another instance.
- **Cooperative assignment** in the classic group protocol, such as `CooperativeStickyAssignor`: can avoid revoking every partition during membership changes. Check client/broker compatibility and roll out assignor switches cleanly in a coordinated fashion. Never mix incompatible assignor configurations across members.

With `group.protocol=consumer`, assignment and heartbeats follow broker-driven rules; do not blindly apply classic-protocol advice about swapping `partition.assignment.strategy`.

These are optimizations to stabilize membership after fixing crashes, timeouts, slow handlers, and restart loops—not a first-line band-aid to hide failures.

## 13. Offset Commit: Distinguish Processed, Acknowledged, and Committed

In Spring Kafka's message listener container, when `enable.auto.commit=false`, `AckMode` determines **when the container commits offsets**:

| Ack Mode | Commit Timing Under General Semantics | Trade-offs |
|---|---|---|
| `RECORD` | After the listener finishes processing each record | More frequent commits, smaller redelivery window |
| `BATCH` | After processing all records returned from a poll | Fewer commits; committed offset jumps in batches |
| `TIME` | Based on `ackTime` interval after poll records complete | Committed offset may pause briefly between ticks |
| `COUNT` | Once accumulated processed records reach `ackCount` | Commit cadence depends on message rate |
| `COUNT_TIME` | Whichever threshold (count or time) arrives first | Balances commit frequency and delay |
| `MANUAL` | Application calls `acknowledge()`, then commits using BATCH-like semantics | Risk of forgetting ack or acking too early |
| `MANUAL_IMMEDIATE` | Commits immediately when `acknowledge()` is called on the listener thread | Higher commit cost; requires attention to threads/callbacks |

These are listener container semantics when transactions are not in use. The Spring Cloud Stream Kafka Binder may apply different defaults depending on version and configuration, especially between record mode and batch mode; **verify the effective ack mode** at runtime rather than inferring it solely from Kafka client defaults.

When using Kafka transactions, offsets are typically sent into the transaction and committed with the transaction; do not interpret commit frequency the same way as a non-transactional container.

## 14. Why Does the Committed Offset "Stand Still" While the Handler Is Running?

That can be completely expected in scenarios such as:

- `BATCH`: the consumer fetched a large batch and has not finished the final record of the poll yet.
- `TIME` or `COUNT`: the commit threshold has not been reached yet.
- `MANUAL`: business logic ran, but the callback never invoked `acknowledge()`.
- An async worker is still running, so the listener has not marked completion.
- Retry/backoff is holding a record; the container cannot advance the offset past that failing record.
- Kafka Streams is holding state/transactions or waiting for its own commit interval.

Distinguish each step:

~~~text
Fetched / delivered records
        |
        v
Business processing completed?
        |
        +-- no -> slow handler, dependency, retry, poison message
        |
        v
Acknowledgement reached?
        |
        +-- no -> ACK mode, missing manual ack, async completion
        |
        v
Offset commit attempted?
        |
        +-- no -> threshold/transaction timing, container lifecycle
        |
        v
Commit request sent and accepted by coordinator?
        |
        +-- no -> rebalance, coordinator/network, request timeout
        |
        v
Committed offset advances
~~~

Never force the committed offset forward by acking before data is durably persisted: doing so risks losing business updates if the process crashes.

## 15. Manual Acknowledgement: Verify the Right Header and Thread

When `MANUAL` or `MANUAL_IMMEDIATE` is enabled on a Kafka binding, the `Message` carries `KafkaHeaders.ACKNOWLEDGMENT`. Illustrative consumer:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> handleOrder(OrderService orderService) {
    return message -> {
        // Complete the durable business operation before acknowledging.
        orderService.saveIdempotently(message.getPayload());

        Acknowledgment ack = message.getHeaders().get(
            KafkaHeaders.ACKNOWLEDGMENT, Acknowledgment.class);
        if (ack == null) {
            throw new IllegalStateException(
                "Kafka acknowledgment header is missing");
        }
        ack.acknowledge();
    };
}
~~~

With binding `handleOrder-in-0`, configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: order-service
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              ack-mode: MANUAL
~~~

Keep in mind:

- `MANUAL` does not mean an immediate commit request; the container applies BATCH-style commit timing after acknowledgement.
- `MANUAL_IMMEDIATE` has immediate-commit semantics when acknowledged on the listener thread; calling it from another thread can behave differently depending on container configuration and version.
- Do not assume `acknowledge()` returning means the broker synchronously finished committing in every mode.
- If you hand work off to an async worker and ack before the worker persists the result, a crash can make the message disappear from the consumer group's perspective before business work finished.
- Missing an ack on an early return or exception branch can stall the committed offset or create gaps.
- With Spring Kafka's `asyncAcks`, out-of-order acks can temporarily pause the container until gaps close. It is not a free throughput boost.

Do not switch `MANUAL` to `RECORD` just to hide a forgotten acknowledgement; first verify that changing the policy does not violate system semantics.

## 16. Sync vs Async Commits and Coordinator Latency

A Kafka consumer has two fundamental ways to persist offsets:

- `commitSync()`: blocks waiting for the coordinator response or timeout; can stall the poll thread and amplify slowdowns when the broker or network is unstable.
- `commitAsync()`: issues commits asynchronously; requires callbacks/logging to observe failures and introduces risks around callback ordering and shutdown.

In Spring Kafka's listener container, `syncCommits` controls which mechanism is used and typically defaults to `true`. You can customize the listener container via Spring Kafka/Spring Cloud Stream hooks when a change is truly warranted. Do not switch to async commits purely for lower p99 without testing restarts, rebalances, and redelivery behavior.

To determine whether commits are genuinely slow:

1. Check Kafka client metrics `commit-latency-avg` and `commit-latency-max`.
2. Compare `commit-rate` and `commit-total` against your expected ack mode and message rate.
3. Look for `CoordinatorNotAvailable`, timeouts, `NotCoordinator`, and network reconnects.
4. Check the coordinator broker, disk/network health, throttling, `__consumer_offsets`, and broker restarts.
5. Separate time **waiting for commit conditions** from time spent on the **commit request** after it is sent.

If committed offsets jump every 5 seconds while `commit-latency-avg` stays low, that is usually a policy/threshold effect rather than slow broker commits.

## 17. Retries, DLQ, and Slow Handlers

In Spring Cloud Stream, retries can run in the binder or via the listener container/error handler. Each retry attempt can keep a partition/consumer busy. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              enable-dlq: true
~~~

These numbers are examples only. When a downstream dependency stays degraded, total up processing time, HTTP timeouts, retry count, and backoff. A poison message retried dozens of times or endlessly requeued can heavily impact poll intervals and committed offsets.

Solutions:

- Separate **transient errors** from **permanent errors**; never infinitely retry schema or business-rule failures.
- Set timeouts on dependencies and bound retries/backoff.
- Use DLQ/recovery for records that fail after the allowed attempts; monitor DLQs and support controlled replays.
- For long retries, use an appropriate `DefaultErrorHandler`/container strategy rather than blocking the listener thread unchecked. Spring Kafka supports pause/resume polling in certain handlers to keep the consumer alive.
- With `batch-mode`, verify batch retry semantics specifically; do not assume binder `max-attempts` behaves identically to record mode.
- When adjusting policies, preserve idempotency because a record may be processed multiple times after revocations, commit failures, or restarts.

Never enable `enable.auto.commit=true` to "escape rebalances" when your logic requires at-least-once guarantees. Auto-commit does not guarantee business work completed, and it does not cure underlying poll or heartbeat problems.

## 18. When the Broker or Coordinator Is the Bottleneck

If handlers are fast, polls are steady, and pods are stable, yet commit latency or heartbeat latency climbs, investigate:

- Coordinator broker restarting, re-electing leaders, or overloaded.
- Broker request queue depth, CPU, disk I/O, and `__consumer_offsets` replication and ISR.
- Network jitter, packet loss, slow TLS handshakes, or slow DNS lookups.
- Unstable Kafka client metadata; firewalls, load balancers, or NAT idle timeouts.
- ACL/SASL/token refresh causing authentication errors or connection churn.
- Consumer group with too many members causing expensive rebalances.
- Incompatible Kafka broker/client versions or group protocols after an upgrade.

Correlate metrics across **both client and broker** on the exact same timestamp. Raising client timeouts while the broker continuously moves coordinators only delays incident detection. Coordinate with Kafka operators using broker metrics you are authorized to inspect.

## 19. Essential Dashboard Metrics

| Metric / Signal | How to Interpret | Notes |
|---|---|---|
| `rebalance-total` / `rebalance-rate-per-hour` | Frequency of rebalances | Correlate with deploys/HPA |
| `rebalance-latency-avg/max` | Time taken to complete rebalances | Exact metric names depend on version/client |
| `heartbeat-rate` | Whether heartbeats are sent steadily | Usage differs by group protocol |
| `heartbeat-response-time-max` | Is the coordinator slow replying to heartbeats? | Compare with request/network errors |
| `last-poll-seconds-ago` | How long since the last poll | View alongside `max.poll.interval.ms` |
| `time-between-poll-max` | Longest gap between polls | Spots blocking handlers or retries |
| `commit-latency-avg/max` | Commit request round-trip duration | Distinguish from waiting for acks |
| `commit-rate` / `commit-total` | Commit frequency | Does not necessarily equal message rate |
| `assigned-partitions` | Currently held partitions | Sudden drops can indicate a rebalance |
| Consumer lag per partition | Backlog by group | Combine with throughput and completion |
| GC pauses / CPU throttling / pod restarts | Is the runtime losing poll/heartbeat capability? | Plot on the same timeline |
| Processing p95/p99 / retries / DLQ | Is internal work too slow? | Break down by dependency |

Kafka clients expose many metrics over JMX; Spring Boot Actuator/Micrometer can expose a subset depending on dependencies and configuration. Meter names translated from JMX to Micrometer may differ. Do not assume dashboards automatically collect every metric until instrumentation is configured.

Design alerts around **combinations**: abnormal rebalance spikes + rising lag + falling throughput, or poll intervals approaching limits + high handler p99. A single rebalance during a rolling deployment should not automatically page as a critical outage.

## 20. Branch-Based Troubleshooting Runbook

### Branch A — Poll Is Too Slow

1. Measure `time-between-poll-max` and p99 handler duration.
2. Check records per poll, batch mode, retries, and external I/O.
3. Try reducing `max.poll.records` in a test environment.
4. If slowed by a dependency, add timeouts/circuit breakers, adjust batching, or scale dependency capacity.
5. Increase `max.poll.interval.ms` only with a clear latency budget and after testing failover.

### Branch B — Heartbeat/Session Failures

1. Check `session timeout`, heartbeat errors, and coordinator errors.
2. Identify the active `group.protocol`: `classic` or `consumer`.
3. Cross-check GC pauses, CPU throttling, pod restarts, and network telemetry.
4. Inspect broker coordinator/metadata health and network incidents.
5. Adjust session/heartbeat timeouts only on the right side (client vs broker) per protocol and cluster policy.

### Branch C — Committed Offset Not Advancing

1. Verify whether the handler actually **completed business processing** or merely received the record.
2. Check the effective `ack-mode` and `enable.auto.commit`.
3. For `MANUAL`, verify every success path invokes ack properly.
4. Compare commit metrics against `BATCH`/`COUNT`/`TIME` policies.
5. If commit requests are genuinely slow, inspect coordinator/network/broker; if commits fail after rebalances, fix membership stability.

### Branch D — Rebalances Coincide with Deploys

1. Overlay deployment/HPA/pod-restart timelines against Kafka group membership changes.
2. Fix startup readiness, graceful shutdown, and resource limits.
3. Reduce scale churn and configure stabilization windows.
4. Once stable, consider static membership or cooperative assignment suited to the protocol.
5. Re-test rolling deployments under realistic load.

## 21. Regression Testing Against a Real Broker

Test Binder in Spring Cloud Stream is great for function logic, but it **does not simulate the Kafka group coordinator, heartbeats, poll intervals, rebalances, or real offset commits**. Use Embedded Kafka or Testcontainers/Kafka clusters to verify these scenarios:

| Scenario | Test Action | What to Verify |
|---|---|---|
| Slow handler | Stretch batch processing close to `max.poll.interval.ms` | Membership stays intact or drops as expected in real time |
| Poll size | Compare `max.poll.records` 500 vs 100 | Poll gap, throughput, and lag |
| Manual ack | Intentionally skip an ack branch in a test | Offset does not advance erroneously; missing ack caught |
| Consumer restart | Kill an instance after DB write but before commit | Redelivery happens and business logic is idempotent |
| Rolling deploy | Add/remove consumer members | Rebalance completes and assignments stabilize |
| Network/coordinator outage | Briefly interrupt broker/coordinator in test | Client recovers and commits resume cleanly |
| Retry/poison record | Send a permanently failing record | DLQ/recovery does not stall the group indefinitely |
| Commit latency | Inject controlled network delay | Commit metrics alert while consumer meets SLO |
| Kafka Streams | Stop/start an instance restoring state | Rebalance/task movement, state restore, and lag |

For fault-injection tests, enforce finite timeouts, isolated topics/groups, cleanup, and environments separated from production. When testing real consumers, verify Test Binder auto-configuration does not replace the Kafka Binder.

## 22. Anti-Patterns to Avoid

**Raising `max.poll.interval.ms` to hours as soon as rebalances appear.** This can mask a wedged listener and leave the group waiting far too long before reassigning partitions from a stalled consumer.

**Raising `session.timeout.ms` without checking the group protocol.** Under the `consumer` protocol, timeouts and heartbeats are broker-driven; classic client configs will not behave as expected.

**Changing the group ID or resetting offsets to zero out lag.** That alters reading progress and can skip or replay records. Perform data manipulations only under an approved data-handling procedure.

**Acking before persisting data.** Business progress is lost if the process crashes even though Kafka shows the group committed.

**Switching to async commits without checking callbacks/errors.** It can reduce blocking while hiding commit failures or breaking assumptions during shutdown and recovery.

**Enabling auto-commit regardless of logic.** Offsets can jump ahead of business work, and it never fixes the root cause of rebalances.

**Running far more consumers than partitions.** Adds no effective parallelism while increasing churn during scaling, even if it does not directly cause a rebalance storm on its own.

**Looking only at `CommitFailedException` logs.** Ignores the preceding partition revocation and why the member lost group membership.

**Using consumer lag in Kubernetes liveness probes.** When backlogs rise, Kubernetes kills healthy pods, causing frequent rebalances and making lag worse.

**Confusing Kafka Streams and the regular Kafka Binder.** Kafka Streams has its own stream threads/tasks, state stores, restoration, and commit intervals; do not copy regular Kafka Binder container `ackMode` settings onto Kafka Streams.

## 23. Differences in Kafka Streams Binder, RabbitMQ, and Pulsar

For the **regular Kafka Binder**, `ack-mode` and the Spring Kafka listener container govern commits. For the **Kafka Streams Binder**, Kafka Streams controls the poll loop, task assignment, state stores, restoration, and commits through stream-processing semantics. Rebalances caused by task migration or state restoration can shift lag and throughput; monitor stream thread states, task assignments, restore metrics, and `application.id`. Kafka Streams `processing.guarantee` and `commit.interval.ms` mean something different from Spring Kafka listener `ackMode`.

For the **RabbitMQ Binder**, there is no Kafka-style consumer group rebalance or offset commit. Similar reliability issues are diagnosed via queue depth, unacked counts, consumer acknowledgements, prefetch, and connection/channel recovery. **Pulsar** uses subscriptions/cursors and its own broker reassignment model. Never apply Kafka's `max.poll.interval.ms` to RabbitMQ or Pulsar.

If an application uses multiple binders, confirm which binder actually owns the failing binding before editing configuration.

## 24. Checklist Before Closing the Incident

- [ ] Confirmed rebalances are abnormal rather than a normal rolling deployment.
- [ ] Identified topic, group, binding, binder, partition count, member count, and concurrency.
- [ ] Captured a unified timeline of revoke/join/assign logs, commit errors, and pod restarts.
- [ ] Compared `max.poll.interval.ms` against `time-between-poll-max` and handler duration.
- [ ] Distinguished `max.poll.interval.ms` from heartbeat/session timeouts.
- [ ] Checked `classic` vs `consumer` group protocol before adjusting heartbeat/session configs.
- [ ] Compared committed offsets, lag, business completion, and ack mode.
- [ ] Measured commit request latency to separate genuinely slow commits from infrequent commits.
- [ ] For `MANUAL` ack, verified every success path acks at the right moment.
- [ ] Verified retries/backoff/DLQ and dependency timeouts do not block polls beyond SLOs.
- [ ] Checked CPU/GC, network, broker coordinator, and deploy/HPA behavior.
- [ ] Avoided unplanned group ID changes, offset resets, or durability reductions.
- [ ] Tested restart/rebalance and verified idempotency against real Kafka.
- [ ] Set up dashboards/alerts for rebalance rate, commit latency, poll gaps, lag, and pod health.
- [ ] Collected post-fix evidence: stable membership, steady offset commits per policy, falling lag, and target throughput/latency.

**Conclusion:** When a consumer rebalances continuously, trace backward from revoke/join logs to **poll intervals, heartbeat/session timeouts, membership churn, or the coordinator**. When committed offsets advance slowly, verify **business completion → acknowledgement policy → commit request → coordinator** before concluding Kafka commits are slow. In Spring Cloud Stream, a small adjustment such as lowering `max.poll.records` or fixing manual acks can resolve the issue; however, adjust settings only after gathering measurements, keep groups/destinations intact, and re-test duplicate/redelivery semantics.

## References

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Tips, Manual Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring for Apache Kafka — Message Listener Containers and Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka — Monitoring and Consumer Group Metrics](https://kafka.apache.org/44/operations/monitoring/)
- [Spring Cloud Stream — Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/index.html)
