# commitRetries

In Spring Kafka, **commitRetries** is a listener container setting that specifies how many times the container retries a synchronous offset commit operation when it encounters a retriable commit error. This parameter helps consumers withstand transient failures while sending offsets to Kafka, such as when the coordinator or connection is transitioning state.

`commitRetries` belongs to the step of persisting consumer group progress. It does not retry record-processing logic, does not resend output records, and does not control how many times the listener is re-invoked. When record processing succeeds yet the offset commit has not been persisted, the record may be re-read after a restart or rebalance. Therefore, commit retries improve the odds of completing the commit operation, while the application still needs idempotent side effects to withstand replays.

## 1. Where Does Offset Commit Fit in the Consumer Lifecycle?

A Kafka consumer reads records from partitions and advances through subsequent offsets. The application needs to commit offsets so Kafka stores the consumer group's progress. When the consumer restarts or a partition is assigned to another member, the group can resume from the stored committed offset.

With a Spring Kafka listener container, the simplified lifecycle is typically:

~~~
Consumer poll()
      |
      v
Listener processes record or batch
      |
      v
Container determines offsets to commit per AckMode
      |
      v
Send offset commit to Kafka
      |
      +---- Success: group records progress
      |
      +---- Retriable error: container retries commit
      |
      +---- Non-retriable error: handle per error and group state
      |
      v
Continue poll()
~~~

The committed offset is normally the next offset to read. If the listener processed the record at offset 41 and committed offset 42, the group's next read starts from 42.

Offset commits are stored in Kafka's consumer group management mechanism via the coordinator and the internal **__consumer_offsets** topic. A successful commit indicates the broker recorded group progress per protocol. It does not by itself prove that every side effect outside Kafka completed exactly once.

## 2. What Does commitRetries Do?

In Spring Kafka, **ContainerProperties** exposes the **commitRetries** property. When the listener container performs a synchronous commit and encounters **RetriableCommitFailedException**, the container can retry the commit operation up to the configured count.

Example:

~~~java
factory.getContainerProperties().setCommitRetries(5);
~~~

A value of 5 means the container is allowed to retry up to five times after the initial commit attempt for error types supported by this mechanism. The total number of attempts can include the initial attempt plus the retries. The default is commonly 3; verify the API and default in your running Spring Kafka version.

Key points to remember:

- `commitRetries` is used for synchronous commits.
- The setting takes effect only when **syncCommits=true**.
- This mechanism targets retriable commit errors, typically **RetriableCommitFailedException**.
- Non-retriable errors, authorization errors, or errors caused by the consumer no longer being a valid group member do not become recoverable merely by increasing `commitRetries`.
- This parameter does not control producer retries, listener retries, or retry topics.

With the Spring Kafka listener container, synchronous commit is the default in many configurations. If the application switches to asynchronous commits, `commitRetries` does not apply to `commitAsync` calls.

## 3. Distinguishing commitRetries from Other Retry Mechanisms

Retry configuration names in Kafka ecosystems sound similar, yet they handle different stages.

| Mechanism | Target Being Retried | Purpose |
|---|---|---|
| Kafka producer retries | Producer record send requests | Overcome transient send failures within delivery limits |
| Spring Kafka listener retry / error handler | Record processing where the listener threw an error | Retry business processing or recover failed records |
| Non-blocking retry topic | Record routed to a retry topic | Defer the next attempt and let the main consumer proceed |
| `commitRetries` | Synchronous offset commit operation of the consumer container | Retry persisting group progress when commit hits a retriable error |
| Application-written retry | A code-controlled business operation | Recover a workflow under custom policy |

For instance, a listener reads a record successfully, calls the database, and then the container commits the offset. If the commit hits a retriable error, `commitRetries` can retry the commit operation. It does not re-invoke the listener merely because the commit needed a retry.

Conversely, if the listener throws an exception before finishing processing, the container enters its rollback/error-handler mechanism. That is record-processing retry, not `commitRetries`.

Do not use `commitRetries` to mask a stalled listener, a database timeout, or a malformed data record. Identify whether the failure occurred at the processing step or at the offset-persistence step.

## 4. Synchronous Commits vs. Asynchronous Commits

Spring Kafka lets the container use synchronous or asynchronous commits through the **syncCommits** property.

### 4.1. Synchronous Commits

When **syncCommits=true**, the container uses **Consumer.commitSync()** to send offsets and wait for the result. If the commit completes, the container knows the operation succeeded per Kafka's response. If the commit fails with a retriable error supported by Spring Kafka, the container can retry according to `commitRetries`.

Advantages:

- The container receives the commit result within the control flow.
- Easy to know when the commit completed before continuing the processing cycle.
- Can retry certain transient commit errors via `commitRetries`.

In return, the consumer thread must wait for the commit to finish. If the coordinator or broker responds slowly, cycle duration can rise. Monitor commit latency and set sensible timeouts.

### 4.2. Asynchronous Commits

When **syncCommits=false**, the container uses **Consumer.commitAsync()**. The call does not wait for the broker to finish committing; results are delivered through a callback if configured.

The advantage is reduced blocking on the consumer thread. However, the application does not receive a synchronous outcome before continuing. The Kafka client does not auto-retry `commitAsync` the same way as `commitSync`, partly because re-sending an older commit after a newer commit can move the group's offset backward.

In this mode, **commitRetries has no effect**. The application should monitor the callback, log errors, and rely on subsequent commits to record newer offsets. Do not manually re-send an older offset map after the consumer has moved on to process and commit newer progress.

### 4.3. Comparison Table

| Criterion | `syncCommits=true` | `syncCommits=false` |
|---|---|---|
| Primary API | `commitSync` | `commitAsync` |
| Waits for broker result | Yes | Does not wait in the call |
| Callback | Not the primary result mechanism | Can receive results via commit callback |
| `commitRetries` | Applies to supported retriable errors | Does not apply |
| Latency impact | Can increase consumer-thread wait time | Less waiting in the calling loop |
| Manual retry risk | Container controls synchronous commit retries | Manually retrying an old commit can overwrite newer progress |

Choosing synchronous or asynchronous depends on commit latency requirements, result visibility, and recovery behavior. Do not switch to async solely to lower a latency metric without a plan to handle callback failures.

## 5. Configuring commitRetries in Spring Kafka

`commitRetries` can be configured on the **ContainerProperties** of a listener container factory. Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setSyncCommits(true);
    properties.setCommitRetries(5);
    properties.setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

In this example, the container uses synchronous commits, allows up to five commit retries under the supported mechanism, and commits offsets per batch after the listener finishes processing records from the poll.

You can configure the timeout for synchronous commits with **syncCommitTimeout**:

~~~java
properties.setSyncCommitTimeout(Duration.ofSeconds(10));
~~~

Parameter types and setter APIs can differ across Spring Kafka versions. Check the Javadoc for your exact version. Each commit's timeout and the retry count together determine how long the container may wait before concluding a commit has failed.

When using Spring Boot, consumer properties such as **default.api.timeout.ms** can affect the Kafka client's default timeout. When configuring an explicit timeout on `ContainerProperties`, verify which value takes effect.

### 5.1. Basic Consumer Configuration

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        default.api.timeout.ms: 10000
~~~

The Spring Kafka listener container normally manages offset commits in place of consumer auto-commit. Keeping auto-commit off lets the container control commit timing across AckMode, retries, and transactions. If auto-commit is enabled manually, do not assume `commitRetries` controls the auto-commits executed by the Kafka client.

## 6. AckMode Determines When Commits Occur

`commitRetries` only gets a chance to act when the container executes a synchronous commit. `AckMode` decides when and what range of offsets the container commits.

| AckMode | Typical Commit Timing | Impact on Commits |
|---|---|---|
| RECORD | After each record listener finishes successfully | Can generate more commits |
| BATCH | After all records in a poll finish successfully | Commits a batch of offsets after the poll |
| TIME | When configured time elapses and offsets are pending | Time-based commits |
| COUNT | When configured record count is reached | Count-based commits |
| COUNT_TIME | When either count or time condition is met | Commits on whichever threshold hits |
| MANUAL | When listener acknowledges; container commits on the matching cycle | Listener explicitly reports processed records |
| MANUAL_IMMEDIATE | Commits immediately when acknowledge is called on consumer thread | Can commit earlier than MANUAL |

Exact details also depend on record listener vs. batch listener, calling acknowledge on the consumer thread vs. another thread, the error handler, and the Spring Kafka version.

Example with RECORD:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Example with BATCH:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

If RECORD produces more commits than BATCH, commit-error occurrences can scale with commit count. However, BATCH widens the offset range committed after a poll; when a batch fails, more records may have to be re-read. Choose AckMode based on delivery semantics and processing boundaries, then tune `commitRetries` from observed commit behavior.

## 7. Which Errors Can commitRetries Handle?

Not every error during a commit can be solved by retrying the same operation.

### 7.1. RetriableCommitFailedException

This is the error type Spring Kafka uses to identify certain retriable commit failures. For example, it may relate to transient issues during offset committing or coordinator state transitions that the Kafka client flags as retriable.

In synchronous commit mode, the container can retry up to the configured count. If the commit succeeds on a subsequent attempt, the group records the offset and the container resumes normal operation.

### 7.2. CommitFailedException Due to Lost Membership

If the consumer is no longer a valid group member or the generation has changed, the commit may be rejected. An old commit from a consumer that lost partition ownership should not be forced through via endless retries.

Causes can include rebalances, overly slow consumer processing, expired sessions, or revoked partitions. The right response is letting the consumer complete the protocol rejoin/assignment flow, establish valid offsets, and accept replay if offsets were not committed.

### 7.3. AuthorizationException

If the principal lacks permission to commit offsets or the related operation is denied, retrying with unchanged credentials and ACLs will keep failing. Access permissions or security configuration must be fixed.

### 7.4. Timeouts or Connection Errors

Timeouts can appear when the coordinator or broker responds slowly, or when an acknowledgment is lost. Sometimes the broker persisted the commit while the client missed the response. Hence, the outcome of a timed-out commit can be ambiguous.

When the container retries the same offset, committing the exact same offset does not fundamentally move the group backward. However, if the application manually retries an old offset after a newer commit succeeded, it can regress group progress. Letting the container manage retries inside the proper commit flow avoids unsafe commit ordering.

### 7.5. Error Classification

| Error Category | Example | Does commitRetries Solve It? | Action |
|---|---|---|---|
| Retriable commit failure | `RetriableCommitFailedException` | Yes, when `syncCommits` is enabled and the error type is supported | Let container retry within bounds |
| Lost membership/generation | `CommitFailedException` from rebalance or invalid consumer | Do not rely on retrying the old commit | Rejoin group, handle replay, and inspect poll/rebalance |
| Authorization | `GroupAuthorizationException` or matching auth error | No | Fix ACLs/principal |
| Configuration error | Invalid client or group configuration | No | Fix configuration |
| Connection/timeout error | Coordinator unavailable, timeout | Only if surfaced as a supported retriable error | Check broker/network; assess uncertain commit outcome |
| Async commit failure | Error in `commitAsync` callback | No | Monitor callback and let newer commits advance in order |

Exact exception names depend on the Kafka client and Spring Kafka versions. Inspect the root exception and consumer logs instead of assuming every error containing the word "commit" belongs to the retriable class.

## 8. commitRetries and Wait Time

Increasing `commitRetries` can improve the chance of riding out a transient error, yet it can also keep the consumer thread waiting longer if each commit takes substantial time.

Total wait time depends on:

- The timeout of each synchronous commit attempt.
- The number of additional retry attempts.
- Actual broker/coordinator response latency.
- Kafka client API timeouts.
- Other processing and commit time within the same poll cycle.

Rough upper-bound estimate when each commit approaches timeout:

~~~
T_commit_budget ≈ (1 + commitRetries) × syncCommitTimeout
~~~

This is a conservative estimate, not an exact time guarantee. Some retries may return faster than timeout; internal Kafka client timeout and retry layers can also shift actual durations.

For example, suppose `syncCommitTimeout` is 10 seconds and `commitRetries` is 3. If all four attempts near timeout, the consumer could spend roughly 40 seconds committing. If that time falls inside the poll cycle, it can push the consumer closer to `max.poll.interval.ms`.

Do not increase `commitRetries` while ignoring the poll budget. Evaluate commit latency alongside listener processing time, retry/backoff, and `max.poll.interval.ms`. If slow commits persist, investigate the coordinator, brokers, network, and cluster health.

## 9. Relationship with max.poll.interval.ms and Rebalances

The consumer must continue calling `poll()` within `max.poll.interval.ms`. When record processing or commit waits take too long, the consumer may miss its poll deadline and be considered stalled.

A scenario:

~~~
poll() receives batch
      |
      v
Listener processes successfully
      |
      v
Container commits offset synchronously
      |
      v
Commit hits retriable error
      |
      v
Container retries commit
      |
      v
Total processing + commit time too long
      |
      v
Consumer exceeds max.poll.interval.ms
      |
      v
Group rebalance / partition revoked
~~~

If `commitRetries` stretches the commit cycle, it can contribute to a rebalance. In that case, retrying commits more times does not necessarily improve overall reliability. Measure:

- Listener/batch processing duration.
- Commit latency and commit retry count.
- Time between consecutive polls.
- Rebalance count and group leave reasons.
- Coordinator/broker response times.

If processing time is already close to `max.poll.interval.ms`, reduce work per poll, optimize dependencies, or tune timeouts with evidence. Do not simply raise `commitRetries` trying to power through an unstable cluster.

## 10. commitRetries in Transactional Listeners

When the listener container uses a Kafka transaction manager, input offsets can be sent into the same Kafka transaction as output records. In that setup, the container does not simply call `consumer.commitSync()` on offsets like a non-transactional flow.

Transactional flow:

1. Container begins a Kafka transaction.
2. Listener processes the record and sends output via `KafkaTemplate`.
3. Container sends processed offsets into the transaction.
4. Producer commits the transaction.
5. Kafka commits output records and offsets atomically within the transaction.

If committing the transaction fails, handling falls under the transaction protocol, producer state, and Spring Kafka's rollback/error handling. **commitRetries is not a transaction-commit retry mechanism** and should not be used to infer retry counts for Kafka transactions.

Distinguishing the cases:

| Execution Mode | How Offsets Are Persisted | Role of commitRetries |
|---|---|---|
| Non-transactional listener, sync commit | `Consumer.commitSync()` | Can retry supported retriable commit failures |
| Transactional listener with `KafkaTransactionManager` | Offsets sent into producer transaction | Does not govern Kafka transaction commit/retries |
| Container using async commit | `Consumer.commitAsync()` | Does not apply |

If the transaction aborts, offsets are not committed alongside outputs. Input records may be reprocessed; side effects outside Kafka still need idempotency or separate resource coordination.

## 11. Observing Commits and Detecting Issues

A good consumer dashboard separates processing time from commit time. Looking only at consumer lag makes it hard to tell a slow listener apart from a slow coordinator commit.

Useful signals:

| Signal | Meaning |
|---|---|
| Commit latency | Duration of synchronous commits or callback response time |
| Commit failure count | Number of failed commit operations |
| Retriable commit failure count | Frequency of retriable commit errors |
| Commit retry attempts | How often the container had to retry |
| Commit callback error | Failed asynchronous commit outcome |
| Committed offset progress | Whether the group's offset keeps advancing |
| Consumer lag | Gap between log end and committed offset |
| Rebalance count/duration | Whether slow commits or slow polls trigger constant group churn |
| Coordinator/network errors | Whether Kafka or connectivity issues are occurring |

Metric names depend on the Kafka client, Spring Kafka, Micrometer, and exporter. Do not assume every version exports a dedicated metric for `commitRetries`; if exact retry counts are needed, use appropriate logs/observations or container-layer instrumentation without altering commit behavior.

### 11.1. Useful Commit Logs

Logs should record:

- Consumer group ID.
- Relevant topic and partition.
- Offset being committed.
- Root exception type.
- Retry attempt count if observable.
- Commit duration and final outcome.
- Consumer ID/client ID to correlate with a specific member.

Avoid logging payloads or credentials. Offset and topic are usually enough to trace a record in operations environments with proper access controls.

### 11.2. Using the CLI to Verify Progress

You can inspect committed offsets and lag with:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service
~~~

If commit retries rise while committed offsets keep advancing, errors may be transient and the container is recovering. If offsets stall, check group state, member assignment, recent commit errors, and listener processing. If the group has no members, determine whether consumers stopped or are restarting.

## 12. Testing commitRetries

Tests should focus on offset and group behavior when commits fail, not merely asserting that the property was set.

Scenarios to test in a test Kafka environment:

1. **Normal commit success:** process records, commit offsets, and confirm the group advances.
2. **Coordinator temporarily unavailable:** induce a controlled retriable commit error and observe the container retrying and recovering once the coordinator is ready.
3. **Rebalance during processing:** confirm an old commit is not forced through after losing membership; records replay from the committed offset.
4. **Authorization error:** confirm retries do not hide ACL failures and alerts fire.
5. **Async commit:** set `syncCommits=false`, confirm `commitRetries` does not participate, and verify callback observation.
6. **Transactional listener:** confirm outputs and offsets commit/abort together; do not confuse `commitRetries` with transaction retries.
7. **Poll interval:** introduce a commit delay large enough to observe its effect on poll cadence and rebalances.

Do not simulate production failures by arbitrarily shutting down brokers on a shared cluster. Use a test environment, bounded fault injection, or approved testing tools.

## 13. Choosing a commitRetries Value

There is no single optimal value for every consumer group. The value must balance tolerance for transient commit errors against how long the consumer thread can afford to wait.

Deciding factors:

- Stability of brokers and the group coordinator.
- Observed frequency of retriable commit errors.
- Synchronous timeout per commit attempt.
- `max.poll.interval.ms` and single-poll processing budget.
- `AckMode` and commit frequency.
- Impact of slow commits on lag and rebalances.
- Whether transactions or async commits are used.

If the cluster is stable and commit failures are rare, the default value is usually a sensible starting point. If increasing retries, measure post-retry recovery rate and total wait time. If most errors stem from authorization or lost membership, raising retry counts will not fix the root cause.

Do not set `commitRetries` very high hoping a consumer will always manage to commit. A consumer that lost partition ownership should not try to write stale offsets. A cluster experiencing prolonged disconnection needs alerts and infrastructure recovery, not an endlessly long commit loop.

## 14. Common Configuration Mistakes

| Practice | Consequence | Resolution |
|---|---|---|
| Setting `commitRetries` while `syncCommits=false` | Setting has no effect | Enable sync commits if this retry behavior is needed, or handle async callbacks |
| Thinking `commitRetries` retries the listener | Misunderstands how many times business logic runs | Use error handler/retry policy for the listener |
| Raising `commitRetries` for ACL issues | Failure persists and alerts are merely delayed | Fix authorization and credentials |
| Retrying an old commit after a newer commit | Can regress committed offsets | Let container manage commit order; avoid replaying stale `commitAsync` calls |
| Raising timeouts and retries without accounting for poll interval | Consumer can exceed `max.poll.interval.ms` | Budget processing + commits and monitor rebalances |
| Relying on `commitRetries` for transactional listeners | Confuses consumer `commitSync` with transaction commit | Use Spring Kafka's rollback/transaction handling |
| Committing offsets before side effects complete | Lag drops while business work can be lost | Pick an appropriate AckMode and commit point |
| Monitoring only lag | Cannot separate slow processing from slow commits | Monitor commit latency, failures, and processing latency separately |

## 15. commitRetries Operational Checklist

Before configuring or investigating commit failures, verify:

1. Is the listener container using `syncCommits` or async commits?
2. What is `commitRetries` set to, and how does your Spring Kafka version support this property?
3. Is the root exception a retriable commit error supported by the container?
4. Does each commit's timeout fit within the poll budget?
5. Does the current `AckMode` commit per record, batch, time, or manually?
6. Is the consumer still a valid group member that owns the partitions?
7. Are there coordinator, broker, network, or authorization errors?
8. Do consumer lag and committed offsets advance after retries?
9. Are side effects safe if records are re-read after a commit failure?
10. If using transactions or async commits, what is the proper recovery mechanism for that mode?

`commitRetries` is a narrow safeguard for synchronous offset commit operations in Spring Kafka. Proper configuration helps the container ride out certain transient commit errors, yet effectiveness depends on `syncCommits`, exception types, timeouts, `AckMode`, and consumer group state. When offsets stall, investigate the coordinator, rebalances, and processing duration before raising retry counts, while keeping consumers idempotent to handle redelivered records safely.
