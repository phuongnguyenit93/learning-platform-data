# session.timeout.ms and Heartbeat

In a Kafka consumer group, heartbeats let the coordinator know which consumers are still connected and participating in the group. The **session.timeout.ms** parameter defines how long the coordinator waits for a valid heartbeat before considering a consumer's session lost. When the session expires, the coordinator can initiate a rebalance and redistribute partitions among active consumers.

In a Spring Kafka application, these parameters directly affect how quickly disconnected consumers are detected, sensitivity to brief disruptions, and rebalance frequency. Setting them too low can cause a healthy consumer to be evicted from the group during temporary network or JVM slowdowns. Setting them too high makes the system take longer to detect a genuinely dead consumer. Understand heartbeats, session timeouts, and the **max.poll.interval.ms** processing limit before changing them.

## 1. How Do Heartbeats Work in a Consumer Group?

The consumer group coordinator tracks group members. A consumer sends periodic heartbeats to signal that it is still participating in the group. The coordinator receives heartbeats and maintains member state while the session remains valid.

High-level flow:

~~~text
Consumer A                  Group Coordinator
    |                              |
    |------ JoinGroup ------------>|
    |<----- SyncGroup --------------|
    |                              |
    |------ Heartbeat ------------>|
    |<----- Heartbeat response -----|
    |                              |
    |------ Heartbeat ------------>|
    |<----- Heartbeat response -----|
    |                              |
    |  (connection lost / stopped) |
    |                              |
    |       session timeout        |
    |                              |
    |<------ rebalance ------------|
    |                              |
~~~

After joining the group and receiving an assignment, the consumer continues sending periodic heartbeats. If the coordinator receives no heartbeat within the session timeout, it can mark the member as having left the group. Partitions owned by that member are redistributed according to the rebalance protocol.

A heartbeat is a signal of group membership health, not proof that business logic is processing records successfully. A consumer may send steady heartbeats while its listener processes slowly, downstream hangs, or backlog grows. Therefore, monitor both heartbeat/rebalance metrics and consumer lag plus record processing times.

## 2. What Is session.timeout.ms?

**session.timeout.ms** is the maximum duration the coordinator waits for a heartbeat from a consumer before considering that consumer inactive in the group. When the timeout expires, the coordinator can evict the member and trigger a rebalance.

This parameter creates a trade-off:

- Smaller values detect dead consumers faster and reduce how long partitions are held by an inactive member.
- Larger values give consumers more room to survive transient network glitches, JVM pauses, or brief system load spikes.
- Values that are too small can cause false positives: the consumer is alive, but its heartbeat reaches the coordinator late.
- Values that are too large delay failure detection and throughput recovery after a consumer truly dies.

Under the classic consumer group protocol, the client sends its session.timeout.ms value when joining the group. The broker bounds this value using configurations such as **group.min.session.timeout.ms** and **group.max.session.timeout.ms**. If a client sets a value outside the broker's bounds, joining the group can fail.

Do not pick a timeout merely out of a desire to "rebalance as fast as possible". Measure network latency, JVM pause durations, CPU load, coordinator health, and recovery SLAs to choose a threshold with a safe margin.

## 3. heartbeat.interval.ms Controls the Heartbeat Cadence

Under the classic consumer group protocol, **heartbeat.interval.ms** determines how frequently the consumer sends heartbeats to the coordinator. Heartbeats are typically sent more frequently than the session timeout so failures have opportunities to be handled before the session expires.

A common rule of thumb is:

~~~text
heartbeat.interval.ms <= session.timeout.ms / 3
~~~

For example, if session.timeout.ms is 15 seconds, you can start testing with heartbeat.interval.ms around 5 seconds. This is a common starting point, not a mandatory formula for every workload. Consider network latency, coordinator load, number of consumers in the group, and failure-detection requirements.

Heartbeats that are too frequent increase coordination requests and broker/coordinator load, especially with many consumers. Heartbeats that are too infrequent give the consumer fewer chances to prove liveness before session timeout.

### 3.1. Spring Boot Configuration Example

Under the classic group protocol, you can configure the consumer in Spring Boot as follows:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[session.timeout.ms]": 15000
        "[heartbeat.interval.ms]": 5000
        "[max.poll.interval.ms]": 300000
~~~

The values above are only examples illustrating the relationship among the three parameters. Verify that the broker allows a 15-second session timeout and tune according to Kafka version, infrastructure, and processing characteristics. Do not copy this configuration verbatim to production without measuring processing durations and behavior under network disruptions.

You can declare them via ConsumerFactory if the application configures consumer properties manually:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 15_000);
props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 5_000);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);

DefaultKafkaConsumerFactory<String, OrderEvent> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props, keyDeserializer, valueDeserializer);
~~~

If Spring Boot already creates ConsumerFactory from property configuration, avoid creating a second factory just to set timeouts unless specifically required. Keeping consumer configuration centralized ensures consistent behavior across instances and simplifies operations.

## 4. Distinguishing Session Timeout from max.poll.interval.ms

This is the most critical point when troubleshooting consumer rebalances. **session.timeout.ms** and **max.poll.interval.ms** guard two different conditions:

| Parameter | What Does It Monitor? | When the Limit Is Exceeded |
|---|---|---|
| session.timeout.ms | How long the coordinator receives no valid heartbeat | The member may be considered expired and evicted from the group |
| max.poll.interval.ms | Maximum time between two application poll() calls | The consumer is considered no longer making progress in the poll loop; the group may rebalance |

Heartbeats prove the consumer still maintains group connectivity. poll() proves the application continues fetching and making progress on data. The two are related but not identical.

The Kafka consumer client can maintain heartbeats on a background thread while the application processes records returned by the previous poll. Thus, a slow listener can still send heartbeats normally while exceeding max.poll.interval.ms. In that case, the consumer is considered overdue for polling and can lose its assignment.

Conversely, if the network to the coordinator drops or the consumer process freezes, heartbeats fail to reach the coordinator and the session timeout can expire even before max.poll.interval.ms is exceeded.

### 4.1. Slow Processing Example

Suppose a consumer polls 100 records and the listener takes an average of 4 seconds per record. Batch processing time can be roughly 400 seconds, excluding overhead and outlier slow records. If max.poll.interval.ms is only 300,000 ms (5 minutes), the consumer risks exceeding the poll interval even though the heartbeat thread remains healthy.

Remediation approaches:

- Reduce max.poll.records to bound the processing time per batch.
- Optimize listener logic and downstream calls.
- Increase max.poll.interval.ms if SLAs and design genuinely permit longer processing times.
- Move long-running work to a controlled worker architecture, acknowledging only after work is durably stored or safely handed off.

Never raise session.timeout.ms to fix a max.poll.interval.ms violation. The two parameters address different causes.

## 5. Heartbeats and Listener Lifecycle in Spring Kafka

Spring Kafka runs listener containers to manage Kafka consumers, poll, invoke listeners, commit offsets, and coordinate rebalances. Each consumer in the container joins the group and sends heartbeats per the Kafka client's mechanism.

For a per-record listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

The listener is normally invoked on the container's processing thread. If the method takes a long time, evaluate the total processing time of all records returned in one poll against max.poll.interval.ms. A heartbeat thread does not turn a stalled listener into a consumer making normal progress.

With a batch listener, total batch processing time can be much larger than single-record processing time. Choose max.poll.records, concurrency, and poll interval based on high-percentile processing times, not averages alone.

### 5.1. Container Concurrency and Consumer Count

Spring Kafka allows setting concurrency on a listener container:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Concurrency creates multiple consumers in the same group from a single listener container application. Each consumer has its own heartbeat lifecycle and assignment. If active consumers exceed partitions, some consumers will receive no partition assignments and will not increase throughput.

When increasing concurrency, evaluate:

- Partition count of subscribed topics.
- CPU, memory, and downstream capacity.
- Total consumers across all application instances.
- Heartbeat and group coordination load.
- Rebalance duration during deployments or autoscaling.

Raising concurrency is not a direct fix for session timeouts. If the root cause is coordinator/network issues or JVM pauses, adding consumers can increase load on the group coordinator and brokers.

## 6. What Happens When Heartbeats Are Lost?

Common reasons heartbeats fail to reach the coordinator on time include:

- The consumer process crashes or the container is killed.
- The host or pod loses network connectivity to the broker.
- The coordinator broker is overloaded, restarting, or unable to serve requests.
- Long JVM stop-the-world pauses or severe CPU throttling.
- DNS, TLS, authentication, or network routing issues.
- The consumer is blocked or stalled during client initialization/shutdown.
- Heartbeat/session timeout settings are too tight for real-world conditions.

When the coordinator determines a session has expired, the member can be removed from the group. Remaining consumers receive a rebalance notification and may have to revoke and reacquire partitions. During a rebalance, some processing may pause temporarily. Uncommitted records may be redelivered, so business consumers must be idempotent.

A rebalance does not necessarily mean data loss. However, continuous rebalances can cut throughput, raise lag, and increase duplicate processing. Identify the root cause before raising timeouts or changing assignment strategies.

## 7. Static Membership and group.instance.id

Kafka supports static membership via **group.instance.id**. A consumer with a stable member identity can leave and return within the active session window without necessarily triggering an immediate rebalance as dynamic membership does. This is useful during rolling restarts or for pods with stable identities.

Static membership changes how member departure is detected:

- When an instance restarts quickly with the same identity, it can reclaim its member slot and reduce unnecessary rebalances.
- If the instance is genuinely gone for a long time, the coordinator still waits for the session to expire before releasing its assignment.
- group.instance.id must be unique within a group. Two consumers using the same identity can cause fencing or membership errors.
- If using Spring Kafka concurrency, each consumer needs a unique identity; check how your Spring Kafka version appends suffixes for child consumers.

Static membership does not replace heartbeats and does not allow a consumer to stop polling indefinitely. It mainly changes how the coordinator handles a member with a stable identity when it leaves and rejoins.

## 8. Classic Protocol vs. the New Consumer Group Protocol

The parameters session.timeout.ms and heartbeat.interval.ms are configured on the client in the classic consumer group protocol. Kafka also has the new consumer group protocol, selected via group.protocol=consumer in supporting client/broker versions.

When using the new protocol:

- Certain heartbeat and session timeout settings are managed by the broker rather than the client.
- Client-side heartbeat.interval.ms and session.timeout.ms are no longer where cadence and timeouts are controlled the way the classic protocol uses them.
- Broker configurations such as group.consumer.heartbeat.interval.ms and group.consumer.session.timeout.ms govern the corresponding values.
- Verify broker, Kafka client, and Spring Kafka compatibility before switching protocols.

Do not mix classic protocol guidance with the new consumer protocol. If your application uses the classic protocol, configure both parameters on the client as shown earlier. If group.protocol=consumer is enabled, consult the documentation for your deployed Kafka version and tune on the broker per the new protocol's mechanics.

## 9. Choosing Timeouts by Workload and Environment

No single timeout pair fits every application. A consumer processing lightweight events on a local network can use a shorter session timeout than one running across inter-region networks or environments with longer JVM pauses.

When choosing values:

1. Measure heartbeat response times and network latency to the coordinator.
2. Measure JVM pauses, CPU throttling, and OS scheduler starvation.
3. Determine the dead-consumer detection time acceptable to the business.
4. Check the broker's group.min.session.timeout.ms and group.max.session.timeout.ms bounds under the classic protocol.
5. Set the heartbeat interval sufficiently smaller than the session timeout per protocol recommendations.
6. Verify max.poll.interval.ms independently against batch processing times.
7. Test consumer restarts, broker restarts, and network interruptions in staging.

An illustrative set of values for the classic protocol might be:

| Parameter | Example Value | Meaning |
|---|---:|---|
| session.timeout.ms | 15,000 ms | Coordinator detects expired member session after ~15 seconds without a valid heartbeat |
| heartbeat.interval.ms | 5,000 ms | Consumer sends heartbeats roughly every 5 seconds |
| max.poll.interval.ms | 300,000 ms | Application must keep polling within the 5-minute limit |

This is not a universal production template. Consumers with long batch processing times may need a higher max.poll.interval.ms; fast-recovery requirements may need a lower session timeout if infrastructure supports it. Brokers can also reject session timeouts outside permitted bounds.

## 10. Metrics for Monitoring Heartbeats and Rebalances

To know whether consumers maintain stable membership, monitor metrics from the Kafka consumer client and Spring Kafka listener container.

Useful metrics (exact names and tags depend on Kafka client version):

| Metric | Meaning | Warning Sign |
|---|---|---|
| heartbeat-rate | Heartbeat rate | Unusual drop or stop while the consumer is expected to be active |
| heartbeat-total | Total heartbeats | Check heartbeat activity over a time window |
| heartbeat-response-time-max | Maximum heartbeat response time | Increases may indicate a slow coordinator or network |
| last-heartbeat-seconds-ago | Seconds since last heartbeat | Unexpectedly rising values warrant investigation |
| rebalance-rate / rebalance-total | Rate and total count of rebalances | Continuous increases may indicate group instability |
| rebalance-latency-avg / rebalance-latency-max | Time to complete rebalances | Prolonged rebalances reduce useful processing time |
| assigned-partitions | Number of partitions assigned to the consumer | Check assignment balance and idle consumers |
| records-lag-max | Maximum record lag | Detects consumers falling behind producers |
| poll-idle-ratio-avg | Fraction of time the consumer is idle rather than processing | Helps tell if the consumer is idle or constantly busy |

Do not alert only when heartbeat-rate reaches 0. A consumer can still send heartbeats while processing records far too slowly. Combine heartbeat metrics with rebalance rate, lag, poll interval, listener duration, and downstream errors.

Dashboards should distinguish group, client, topic, and partition with stable tags. Avoid using dynamic member IDs or client IDs as unbounded labels if they create high cardinality on every deployment.

## 11. Troubleshooting Common Failures

### 11.1. Consumer Repeatedly Evicted from the Group

Check:

1. Do consumer logs show session timeout or heartbeat failure messages?
2. Did heartbeat-response-time-max and last-heartbeat-seconds-ago spike before the rebalance?
3. Did the coordinator broker restart, overload, or lose connectivity?
4. Did the JVM experience long GC pauses, CPU throttling, or container resource starvation?
5. Is session.timeout.ms within broker bounds and given enough safety margin?
6. Are many consumers starting/stopping simultaneously due to autoscaling or health checks?

If heartbeats are not reaching the coordinator, focus on network, broker, JVM, and timeouts. Simply increasing max.poll.interval.ms will not fix missed heartbeats.

### 11.2. Heartbeats Healthy Yet Rebalancing Due to Slow Processing

If heartbeat metrics are normal yet the consumer keeps leaving the group, inspect max.poll.interval.ms. Measure p95/p99 poll-batch processing duration, records per poll, downstream latency, and blocking code paths.

Lower max.poll.records, optimize the listener, or raise the poll interval in a controlled way. If the listener executes asynchronous work, ensure records are never acked before work is durably persisted or safely handed off.

### 11.3. Rebalances Spike After Deployments

Rolling deployments can cause consumers to leave and rejoin the group. If all instances restart simultaneously, the group can undergo multiple rebalance waves and lag rises. Check:

- Rollout strategy and how many instances restart concurrently.
- Graceful shutdown of listener containers.
- Static membership if the application has suitable stable identities.
- Startup duration, broker connection time, and assignment completion.
- Partition count and consumer count in the group.

Do not enable static membership mechanically. If IDs are not unique or an instance stays down long, retaining membership can prolong how long assignments are held.

### 11.4. Slow Heartbeat Responses

Check network latency to the coordinator broker, broker request queues, CPU/disk pressure, and topology changes. If multiple consumer groups are affected simultaneously, the issue is likely on the broker or shared network infrastructure. If only one application is affected, inspect its pod resources, DNS, TLS, and client configuration.

## 12. Runbook When a Consumer Loses Heartbeats

When an alert signals heartbeat failures or unusual rebalance spikes:

1. Identify the affected group, consumer instances, topics, and partitions.
2. Inspect logs to distinguish session timeout from max.poll.interval.ms.
3. Correlate heartbeat response time, last heartbeat age, rebalance latency, and consumer lag.
4. Check coordinator broker health, network, DNS, TLS, and JVM/container resources.
5. If caused by a slow listener, measure batch and downstream durations; tune poll interval or batch size accordingly.
6. If caused by infrastructure, restore network/broker or compute resources before changing timeouts.
7. After the group stabilizes, monitor lag until caught up and check for duplicate delivery in business state.
8. Document the root cause and update alerts/runbooks if current thresholds cause false positives.

During an incident, do not repeatedly restart all consumers to "retry". Doing so can trigger extra rebalances, increase coordinator load, and worsen lag.

## 13. Testing Heartbeats and Session Timeouts

Tests should simulate both connectivity failures and processing-progress failures:

- Terminate a consumer process abruptly and measure how long it takes for partitions to be reassigned.
- Block network traffic between the consumer and coordinator broker in a test environment.
- Induce controlled JVM pauses or CPU throttling to observe heartbeat behavior.
- Make a listener process longer than max.poll.interval.ms to distinguish poll timeout from session timeout.
- Restart the broker hosting the coordinator and observe group recovery.
- Perform a rolling restart of consumers with and without static membership to compare rebalances.
- Verify uncommitted records are redelivered without creating duplicate business effects.

Record the time from failure onset to coordinator detection, to rebalance completion, and to consumer group backlog catch-up. These three intervals are distinct and all can impact recovery SLAs.

## 14. Production Configuration Checklist

### Heartbeats and Sessions

- [ ] Identified whether consumers use the classic or new consumer group protocol.
- [ ] Under the classic protocol, session.timeout.ms is within broker bounds.
- [ ] heartbeat.interval.ms is configured appropriately relative to session timeout.
- [ ] Timeouts have safety margins based on network latency, JVM pauses, and real load.
- [ ] Session timeout is not used as a workaround for max.poll.interval.ms violations.

### Listener and Poll

- [ ] Poll batch processing duration stays within max.poll.interval.ms.
- [ ] max.poll.records fits processing duration and downstream capacity.
- [ ] Consumers do not ack before business side effects are durable.
- [ ] Consumers are idempotent to tolerate record redelivery.
- [ ] Concurrency matches partition count and application resources.

### Observability and Recovery

- [ ] Dashboards cover heartbeats, heartbeat responses, rebalances, and consumer lag.
- [ ] Logs distinguish session timeout from poll interval timeout.
- [ ] Alerts exist for abnormal rebalances and lag exceeding SLA.
- [ ] Runbooks define how to check coordinator, network, and JVM health.
- [ ] Consumer crashes, network interruptions, and rolling restarts have been rehearsed.

## Conclusion

session.timeout.ms sets how long the coordinator waits for heartbeats before considering a consumer's session lost; heartbeat.interval.ms controls the heartbeat cadence under the classic group protocol. These two parameters detect disconnected members, while max.poll.interval.ms governs whether the application continues polling and making processing progress. In Spring Kafka, configure them according to protocol version, broker bounds, listener processing duration, and infrastructure conditions. Monitoring heartbeats, rebalances, lag, and processing times together helps separate connectivity failures from slow consumers, cut unnecessary rebalances, and recover groups in a controlled manner.
