# Synchronous and Asynchronous Commits

A Kafka consumer must commit offsets to record the consumer group's reading progress. When committing, the application records the next position to read for each partition. The Kafka client provides two ways to send commit requests: **synchronous commit** using commitSync and **asynchronous commit** using commitAsync.

Synchronous commit waits for the broker to return a result before continuing. Asynchronous commit sends the request and continues work, with the result delivered later via a callback. The two approaches have different characteristics in terms of latency, error observability, and failure handling.

In Spring Kafka, the listener container manages commit timing according to AckMode. The syncCommits property determines whether the container uses commitSync or commitAsync when sending commit requests. You must clearly distinguish commit timing from commit execution: AckMode and syncCommits solve two different problems.

This lesson belongs to the **Offsets and Commits** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to choose between synchronous and asynchronous commits, configuring Spring Kafka, handling commit errors, and ensuring consumers can recover safely.

## Learning Outcomes

After this lesson, you can:

- Explain that the committed offset is the next position to read for a partition.
- Distinguish between commitSync and commitAsync.
- Understand the impact of commit latency, timeouts, and rebalance errors.
- Configure syncCommits in the Spring Kafka listener container.
- Observe asynchronous commit results via a commit callback.
- Avoid retrying old commits in a way that rolls back newer committed progress.
- Distinguish AckMode, syncCommits, and asyncAcks.
- Choose a commit strategy based on latency, throughput, and recovery requirements.
- Test offset commits and failure scenarios in a controlled manner.

## 1. What Does an Offset Commit Save?

Kafka stores records by partition. Each record in a partition has an increasing offset. The consumer reads records and commits offsets to record the group's progress.

The committed offset is the **next offset the consumer wants to read**, not the offset of the last processed record.

Example of a consumer processing records:

| Partition | Last Processed Record | Committed Offset |
|---|---:|---:|
| orders.created-0 | 41 | 42 |
| orders.created-1 | 18 | 19 |
| orders.created-2 | 105 | 106 |

Each partition has its own offset. A single commit request can include multiple partitions at once, but there is no single global offset representing the entire topic.

If the application processes record offset 41 and then commits 42, when the consumer group restarts and resumes from the committed offset, Kafka delivers records starting from position 42 based on the data still retained.

This also explains the risks of committing at the wrong time:

- Committing after successful processing: records may be redelivered if the commit has not completed, creating the possibility of duplicate processing.
- Committing before processing finishes: if the application stops after committing, records may be skipped when the group resumes reading.
- Never committing: the group may resume from an old offset after a restart or rebalance and re-read already processed records.

Therefore, commits must align with actual processing progress. Synchronous or asynchronous commit only changes how the commit request is sent; neither determines on its own whether a record has been safely processed.

## 2. Synchronous Commit with commitSync

commitSync sends an offset commit request and waits for the broker to return a result. The calling thread continues only after the commit completes, encounters an unrecoverable error, or exceeds the configured timeout.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Consumer thread
    participant Broker as Kafka broker
    App->>App: Process record
    App->>Broker: commitSync(offsets)
    Broker-->>App: Commit response
    App->>App: Continue polling
~~~

Characteristics of commitSync:

- The caller knows whether the commit request succeeded or failed before continuing.
- Commit errors can be handled directly in the calling flow.
- The Kafka client can retry transient recoverable errors within the timeout limit.
- Waiting for the commit increases the time between polls.
- If the commit fails because the consumer no longer belongs to a valid generation after a rebalance, the application cannot consider the offset successfully saved.

commitSync is generally easier to understand and operate when you need to know the commit outcome at execution time. In exchange, waiting for the broker can increase consumer latency.

In the Kafka client, there are commitSync overloads that accept a timeout. If no explicit timeout is passed, the client uses the configured default API timeout. Choose a timeout appropriate for cluster response times and the consumer's poll limits.

## 3. Asynchronous Commit with commitAsync

commitAsync sends a commit request without waiting immediately for the broker's response at the call site. The consumer can continue working; the commit outcome is reported later via a callback.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Consumer thread
    participant Broker as Kafka broker
    App->>App: Process record
    App->>Broker: commitAsync(offsets, callback)
    App->>App: Continue work
    Broker-->>App: Commit response
    App->>App: Callback success or failure
~~~

Characteristics of commitAsync:

- The call returns faster because it does not wait for the commit response.
- Commit errors are reported through the callback.
- The Kafka consumer does not automatically retry commitAsync in the same way as commitSync; arbitrary retries can cause offset ordering issues.
- The application must observe the callback and have an appropriate policy when a commit fails.
- An unacknowledged commit may still be in flight while the consumer continues polling.

Asynchronous commit is useful when you want to reduce blocking time at the commit step and are prepared to manage callback outcomes. It requires a clear understanding of commit ordering, errors, and consumer shutdown.

## 4. Comparing commitSync and commitAsync

| Criterion | commitSync | commitAsync |
|---|---|---|
| Waits for broker response | Yes | Does not wait at the call site |
| Latency on consumer thread | May be higher due to waiting for response | Lower at the call site |
| Error visibility | Directly via return or exception | Via callback |
| Retry | Client handles retries for transient errors within timeout limits | Does not auto-retry via the same mechanism as commitSync |
| Ordering risk | Caller waits for the current commit before continuing | Must avoid retrying an old offset after newer progress has been committed |
| Operational complexity | Usually simpler | Requires callbacks, metrics, and error policies |
| Best suited for | Needing explicit commit confirmation, prioritizing simplicity and observability | Needing to reduce commit wait time with ability to manage callbacks |

There is no single optimal choice for every application. Start with synchronous commits unless you have evidence that commit wait time is a bottleneck. Switch to asynchronous commits only after measuring latency and establishing observability for commit failures.

## 5. Configuring Commits in Spring Kafka

The Spring Kafka listener container manages offset commits. The syncCommits property determines whether the container uses commitSync or commitAsync.

In ContainerProperties, syncCommits defaults to true. Therefore, the container normally performs synchronous commits.

Example listener container configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    var containerProperties = factory.getContainerProperties();
    containerProperties.setAckMode(ContainerProperties.AckMode.BATCH);
    containerProperties.setSyncCommits(true);
    containerProperties.setSyncCommitTimeout(Duration.ofSeconds(10));

    return factory;
}
~~~

In the example, the listener container processes with AckMode.BATCH and commits synchronously with the specified timeout. Types, ConsumerFactory, and bean names should be adjusted to fit the application. The timeout API may vary depending on the Spring Kafka version in use; check your project's dependency version.

To switch to asynchronous commits:

~~~java
containerProperties.setSyncCommits(false);
~~~

When syncCommits=false, the container uses commitAsync. You can configure a callback to observe commit outcomes.

## 6. Monitoring Asynchronous Commits with a Callback

The Kafka consumer API lets you pass an OffsetCommitCallback to commitAsync. Spring Kafka provides ContainerProperties to configure the callback used when the container commits asynchronously.

Example:

~~~java
containerProperties.setSyncCommits(false);
containerProperties.setCommitCallback((offsets, exception) -> {
    if (exception != null) {
        log.error(
                "Kafka offset commit failed, offsets={}",
                offsets,
                exception
        );
        return;
    }

    log.debug("Kafka offset commit completed: {}", offsets);
});
~~~

The callback receives:

- offsets: a map of TopicPartition to OffsetAndMetadata requested for commit.
- exception: the error if the commit failed; null if the commit succeeded.

The callback is an appropriate place to log, increment error counters, or emit monitoring signals. Do not perform database queries, synchronous HTTP calls, or heavy processing inside the callback, as it can impact the consumer thread.

At a minimum, track:

- Successful commit count.
- Failed commit count.
- Exception type and cause.
- Elapsed time from sending the commit to receiving the callback, if measured by the application.
- Involved partition and offset for investigation.

Do not use offsets or group IDs as unbounded-cardinality metric labels. Per-partition details belong in logs or traces; metrics should use labels with bounded value sets.

## 7. Why Should You Not Retry commitAsync Arbitrarily?

A major concern with asynchronous commits is progress ordering.

Suppose the consumer sends a commit for offset 20 and then sends a commit for offset 30. The failure callback for commit 20 might be invoked while commit 30 has already been sent and its result has not yet arrived. If the callback schedules a retry task for offset 20 that runs later—after commit 30 has already succeeded—the stale retry request could roll the group back to offset 20 if the broker accepts it.

This causes the consumer to re-read more records than necessary and can repeat business side effects.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant B as Broker
    C->>B: commitAsync(offset=20)
    C->>B: commitAsync(offset=30)
    B-->>C: callback offset=20 reports error
    C->>C: Schedule retry task for offset 20
    B-->>C: callback offset=30 succeeds
    C->>B: Retry task resends offset=20
    B-->>C: Retry offset=20 succeeds
    Note over C: Stale commit may roll back progress
~~~

The Kafka consumer typically invokes callbacks in the order the asynchronous commit requests were sent. However, a callback might schedule a retry task onto another executor or queue; that task could execute after a newer commit has succeeded. Thus, any manual retry logic must still check the latest progress and avoid resending older offsets.

Safety principles:

- Never blindly retry an old offset after a newer commit has occurred.
- If retrying is necessary, ensure the retried offset is not lower than the latest progress the consumer has safely processed.
- Consider using commitSync at boundaries that require firm confirmation, such as before shutdown or in flows requiring strict ordering.
- Prefer the commit mechanism managed by the Spring Kafka container rather than calling commit from multiple places yourself.
- Log commit failures and evaluate the likelihood of record redelivery after a restart/rebalance.

In most Spring Kafka applications, there is no need to build a custom commitAsync retry loop. Use the container's mechanism and callback to observe failures, and design idempotency to tolerate redelivery when an offset has not been committed.

## 8. AckMode and syncCommits Are Two Separate Settings

AckMode determines **when** the container decides to commit offsets. syncCommits determines **how** the commit is executed.

Examples:

| Configuration | Meaning |
|---|---|
| AckMode.RECORD + syncCommits=true | After each record listener succeeds, the container commits synchronously per RECORD policy. |
| AckMode.BATCH + syncCommits=true | After all records in a poll are processed successfully, the container commits synchronously. |
| AckMode.BATCH + syncCommits=false | After all records in a poll are processed successfully, the container sends an asynchronous commit. |
| AckMode.MANUAL + syncCommits=false | The listener explicitly acknowledges; the container commits asynchronously per manual mode semantics. |

Changing syncCommits from true to false does not alter the processing boundary confirmed by AckMode. It only changes how commit requests are sent to the broker.

Also distinguish commitAsync from Spring Kafka's asyncAcks property. asyncAcks allows acknowledgments for records within the same poll to arrive out of order, with the container deferring commits until required acknowledgments are complete. That is a different feature; it does not simply mean the container uses Kafka commitAsync.

## 9. Impact of Commits on the Poll Loop and Rebalances

The consumer must continue polling within an appropriate interval to maintain group membership. When using commitSync, the time spent waiting for the commit is part of the time during which the consumer has not called the next poll.

If the broker responds slowly, commitSync can increase the time between two polls. If the total processing and commit time exceeds max.poll.interval.ms, the consumer may be considered no longer making progress and the group may rebalance.

CommitAsync reduces blocking time at the call site, but it does not eliminate other poll loop risks. The listener must still process records within reasonable bounds, and the commit callback should remain lightweight.

When a rebalance occurs:

- Partitions may be revoked from the current consumer.
- Committing offsets after a partition has been revoked or when the generation is no longer valid may fail.
- Uncommitted records may be assigned to a new consumer member.
- The application needs idempotency to reprocess safely.

Do not use commitAsync merely to mask a listener that takes too long to process. Measure record processing time, commit latency, poll interval, and rebalance frequency before changing configuration.

## 10. Committing on Shutdown and Before Leaving the Group

When the application stops, the listener container needs to finish processing and save appropriate progress before the consumer closes. Spring Kafka manages the container lifecycle and can perform commits based on configuration, processing state, and how the container is stopped.

With synchronous commits, the commit result can be awaited before completing the close step. With asynchronous commits, you must understand the callback and when the consumer closes; do not assume callbacks will be treated as blocking operations before shutdown completes in every scenario.

Operational principles:

- Stop accepting new work in a controlled manner.
- Give active listeners time to finish within the shutdown timeout.
- Do not commit offsets for records that have not been processed successfully.
- Ensure uncommitted records can be redelivered after a restart.
- Monitor commit errors during the shutdown phase.
- Design idempotent handlers to tolerate redelivery.

If the application processes asynchronously outside the listener, manage in-flight work before the container stops. Committing offsets before work finishes can forfeit the opportunity for records to be redelivered when the process stops.

## 11. Offset Commits and Exactly-Once

Neither commitSync nor commitAsync creates exactly-once semantics for the entire business operation on its own.

For example, a consumer reads OrderCreatedEvent, updates a database, and then commits the offset. If the database commit succeeds but the Kafka offset commit fails, the record may be redelivered. The consumer will need to recognize the already processed event so it does not update the database again.

Conversely, if the offset is committed before the database completes and the application stops, the record may not be redelivered even though the business effect is incomplete.

To reduce risk:

- Use a stable eventId for each event.
- Store an inbox/deduplication key in the same database transaction as the business change.
- Ensure business operations are idempotent.
- For consume-transform-produce flows, consider Kafka transactions and committing offsets within the transaction.
- For database and Kafka coordination, consider outbox/inbox because Kafka transactions do not automatically cover database transactions.

Kafka transactions can coordinate writing output records and input offsets within a single Kafka transaction. This is a different scope from standard commitSync/commitAsync. When using transactions, check the commit or abort of the transaction rather than inferring from an individual offset commit callback.

## 12. Choosing Sync vs. Async by Scenario

| Scenario | Direction to Consider | Reason |
|---|---|---|
| New application without bottleneck metrics yet | Sync commit | Clear behavior, easy to diagnose. |
| Flow needs to know the commit succeeded before proceeding | Sync commit | Caller waits for the result. |
| Measured commit latency is a bottleneck | Evaluate async commit | Reduces wait time at the commit call. |
| System has clear metrics/callbacks and redelivery policy | Async commit can be used | Provides failure observability and operational control. |
| Side effects are hard to make idempotent | Prioritize redesigning safe replay first | No commit mode eliminates the window between processing and committing. |
| Listener frequently exceeds poll interval | Optimize processing and batching first | Async commit does not fix a processing bottleneck. |

Measure throughput, commit latency, consumer lag, rebalances, and commit errors under representative load. Only switch to async if the measured benefit outweighs the added operational complexity.

## 13. Testing Synchronous and Asynchronous Commits

Tests should verify the group's saved offsets, not just check that the listener method finished.

Test categories:

| Test | What to Verify |
|---|---|
| Configuration test | syncCommits has the expected value and AckMode is correct. |
| Sync commit integration test | After processing, the group's offset is updated to the expected position. |
| Async commit callback test | Callback receives success or exception depending on the scenario. |
| Multi-partition test | Offsets are committed independently per TopicPartition. |
| Rebalance test | Commits after a partition is revoked are handled properly. |
| Failure test | Commit errors do not cause the application to falsely record progress. |
| Shutdown test | Container stops gracefully and uncommitted records can be redelivered. |
| Idempotency test | Redelivery does not duplicate side effects. |

You can use AdminClient to read committed group offsets via the listConsumerGroupOffsets API. Example of checking offsets after processing:

~~~java
Map<TopicPartition, OffsetAndMetadata> committed =
        adminClient.listConsumerGroupOffsets("orders-fulfillment")
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS);

OffsetAndMetadata position = committed.get(
        new TopicPartition("orders.created", 0)
);

assertThat(position).isNotNull();
assertThat(position.offset()).isEqualTo(expectedNextOffset);
~~~

Tests must ensure the consumer has finished processing and committing before reading offsets. Use Awaitility or a synchronization condition with an explicit timeout; avoid fixed Thread.sleep.

To test commitAsync callback failures, use unit tests for callback logic or a controlled broker/network fault test. Do not rely on randomly stopping brokers in a test suite, as failures may not reproduce reliably.

## 14. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming commitAsync succeeded as soon as the method returns | Consumer may proceed even though the broker has not confirmed the offset | Observe callbacks and understand pending state. |
| Retrying an old commit after a newer commit has been sent | Risk of rolling offsets backward | Never retry blindly; ensure retried offsets are not older than safe progress. |
| Enabling auto-commit alongside container-managed commits | Progress may be committed outside the expected AckMode | Keep enable.auto.commit=false. |
| Using async to hide a slow listener | Consumer can still exceed max.poll.interval.ms | Optimize the poll loop and processing time. |
| Ignoring callback exceptions | Commit failures go unobserved | Log/record metrics and monitor commit failures. |
| Committing before processing completes | Records may be skipped after a restart | Only acknowledge safely processed progress. |
| Assuming sync commit guarantees exactly-once | Database side effects can still repeat if offset commit fails | Use idempotency or inbox/outbox. |
| Confusing asyncAcks with commitAsync | Configuration and behavior are misunderstood | Distinguish acknowledgment order from how commit requests are sent. |

## 15. Comprehensive Exercise: Comparing Sync and Async Commits

Build a consumer for the topic orders.created with group orders-fulfillment.

Requirements:

1. Configure AckMode.BATCH and enable.auto.commit=false.
2. Run with syncCommits=true and record poll processing time along with commit latency.
3. Read committed offsets using AdminClient after processing multiple records.
4. Switch syncCommits=false and configure a commit callback.
5. Record callback successes and create a metric for commit failures.
6. Simulate a broker error or rebalance in a test environment to verify commit failures.
7. Verify the consumer does not retry an old offset after advancing to a newer offset.
8. Stop the consumer mid-processing to verify redelivery of uncommitted records.
9. Run tests with multiple partitions and verify offsets are saved separately per partition.
10. Compare throughput, commit latency, lag, and error rate between the two configurations.
11. Add idempotency via eventId to safely handle redelivered records.
12. Document the rationale for choosing sync or async based on measured results.

The exercise is complete when you demonstrate how to read committed offsets, observe asynchronous callbacks, analyze commit errors, and explain why a commit strategy does not replace idempotency.

## 16. Learning Sequence and Completion Criteria

| Stage | Core Content | Self-Check Criteria |
|---|---|---|
| 1. Offset model | Next offset and partitions | Correctly calculate the commit offset after the last record. |
| 2. Sync commit | commitSync and timeout | Explain why the caller waits for the result. |
| 3. Async commit | commitAsync and callback | Monitor commit outcomes and errors. |
| 4. Spring Kafka | syncCommits, commitCallback | Configure properly in the listener container. |
| 5. Ordering | Multiple async commits | Avoid retrying old commits that roll back progress. |
| 6. Poll/rebalance | Commit latency and membership | Understand the impact on poll interval and partition assignment. |
| 7. Reliability | Idempotency and transactions | Do not confuse offset commits with business exactly-once. |
| 8. Testing | AdminClient, EmbeddedKafka/Testcontainers | Verify committed offsets and failure paths. |
| 9. Operations | Metrics, logs, shutdown | Monitor commit latency and errors in operations. |

The lesson is complete when you can accurately explain the difference between commitSync and commitAsync, configure syncCommits in Spring Kafka, monitor asynchronous commit failures, and choose a strategy based on metrics.

Synchronous commits prioritize knowing the result before continuing; asynchronous commits reduce wait time at the call site but require careful callback observation and progress ordering. Whichever approach you choose, offsets should reflect only safely completed work, while business effects require idempotency or an appropriate transaction mechanism.

