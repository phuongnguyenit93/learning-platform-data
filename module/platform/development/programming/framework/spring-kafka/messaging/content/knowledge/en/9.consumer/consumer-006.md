# Poll Loop and Data Fetching Cycle

A Kafka consumer receives data by actively calling `poll()` to retrieve records stored by the broker. The continuous loop of calling poll is called the **poll loop**. Each poll can return a set of records from multiple partitions assigned to the consumer; the consumer processes that batch of records and then continues polling to receive new data.

In a Spring Kafka application, you normally do not write your own `while` loop calling `KafkaConsumer.poll()` in a service. Spring Kafka's listener container manages the consumer, the poll loop, invoking the `@KafkaListener` method, offset coordination, and the consumer lifecycle. Understanding the poll cycle is still crucial because it determines how much data is received per iteration, how long a consumer can spend processing a batch, how the group detects slow consumers, and how parallel processing scales.

## 1. Consumers actively pull data

Kafka producers send records to brokers, while consumers actively request data from brokers. Brokers do not call back into the application to push individual messages. A consumer uses `poll(Duration)` to receive data and maintain active participation in the consumer group.

A single poll can return:

- Multiple records belonging to the same partition.
- Records from multiple partitions assigned to the consumer.
- An empty set if no matching data is available within the wait window.

Therefore, one `poll()` call is not equivalent to receiving a single message. It is a cycle that returns whatever batch of records the client can currently deliver given fetch settings, maximum record limits, and available data.

## 2. Steps in the poll loop

A poll loop at the Kafka client level can be illustrated as follows:

```text
KafkaConsumer thread
       |
       v
   poll(timeout)
       |
       v
 Check group, metadata,
 fetch required data
       |
       v
 Return ConsumerRecords
       |
       v
 Process records
       |
       v
 Commit offset per policy
       |
       +----------> next poll()
```

This is a conceptual model. The Kafka client may send fetch requests asynchronously, receive data, and buffer it before the application calls the next poll. Polling also participates in consumer group coordination and updates processing progress. Heartbeat details depend on the group protocol and Kafka client version; do not treat the poll timeout as the heartbeat interval.

Pure Java example to see the loop:

```java
import java.time.Duration;
import java.util.Collections;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class BasicPollLoop {

    public void consume(KafkaConsumer<String, String> consumer) {
        consumer.subscribe(Collections.singletonList("orders.events"));

        try {
            while (true) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    System.out.printf(
                            "topic=%s partition=%d offset=%d key=%s value=%s%n",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            record.key(),
                            record.value());
                }
            }
        }
        finally {
            consumer.close();
        }
    }
}
```

This example only illustrates the Kafka client's poll mechanism. Production code must handle controlled shutdown, exceptions, offset commits, rebalances, and security configuration. Never use the same `KafkaConsumer` concurrently from multiple threads; a Kafka consumer is not thread-safe and must be owned by a single thread driving the poll loop.

## 3. Fetch cycle between consumer and broker

`poll()` is the API called by the application, whereas **fetch** is the protocol the client uses to request brokers to send data from partitions. The two concepts are related but not identical.

The fetch cycle can proceed as follows:

1. The consumer knows its assigned partitions and the offsets to read next.
2. The Kafka client sends fetch requests to the leader brokers for the corresponding partitions.
3. Brokers return available record batches, or wait within configured limits if there is not enough data yet.
4. The client receives and buffers the data.
5. `poll()` returns records from the fetched data and continues triggering data fetching as needed.

The client can fetch from multiple brokers and multiple partitions. A poll may return data already sitting in the buffer; conversely, a poll may return no records if no suitable data is available or the wait timeout expires.

## 4. Configurations affecting poll and fetch

Kafka provides several properties controlling how much data is received and fetch timing. Understand each property accurately because they affect throughput, latency, memory, and consumer group stability.

| Configuration | Role |
| --- | --- |
| `max.poll.records` | Limits the maximum number of records the application receives in one `poll()` |
| `max.poll.interval.ms` | Maximum time between two poll calls before the consumer is considered stalled and may leave the group |
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate before returning a fetch response |
| `fetch.max.wait.ms` | Maximum time the broker waits to reach `fetch.min.bytes` before returning a response |
| `max.partition.fetch.bytes` | Limit on fetched data per partition in a single request |
| `fetch.max.bytes` | Limit on total fetch response data the client requests in one request |
| `poll(Duration)` | Maximum time the poll API waits for data before returning; not a limit on record processing time |
| `session.timeout.ms` | Time the broker waits for a valid heartbeat before considering a consumer inactive in the classic group protocol |
| `heartbeat.interval.ms` | Heartbeat interval in the classic group protocol; typically smaller than session timeout |

Some of the properties above may have different handling or bounds between the classic consumer group protocol and the new consumer group protocol. Check the documentation for the Kafka client version you are using.

### `max.poll.records`

`max.poll.records` caps the number of records returned to the application in a single poll. For example, setting it to 100 means one poll will not return more than 100 records. This property does not directly cap the bytes fetched from the broker; the Kafka client may fetch and buffer more data and hand it out across subsequent poll calls.

Lowering this value can shorten each processing turn, helping the consumer call poll more frequently. However, too low a value can increase overhead and reduce throughput. Increasing it can improve batch processing efficiency, but increases the time to process a poll and the number of records held in memory.

### `max.poll.interval.ms`

This is the time limit between two poll calls. If the application receives a batch and takes too long processing it before calling the next poll, the consumer may be treated as making no progress and the group may trigger a rebalance.

For example, if `max.poll.interval.ms` is 300,000 ms (5 minutes), the total time to process records in one poll plus any auxiliary work before the next poll must fit within this limit with reasonable headroom.

Do not confuse `max.poll.interval.ms` with `poll(Duration)`. A poll may wait at most one second to retrieve data, yet processing the resulting batch may take several minutes. `poll(Duration)` does not limit that processing time.

### `fetch.min.bytes` and `fetch.max.wait.ms`

These two properties govern how the broker batches data before returning a fetch response. A higher `fetch.min.bytes` lets the broker wait for more data to accumulate, improving batch efficiency at the cost of potentially higher latency. `fetch.max.wait.ms` caps that wait duration.

For applications requiring fast response times, small `fetch.min.bytes` and low fetch wait values are common. For high-volume streams, batch accumulation can be increased if additional latency is acceptable.

### Fetch byte limits

`max.partition.fetch.bytes` limits data fetched per partition, while `fetch.max.bytes` limits total data in a fetch response. These values must be large enough for the largest record batch a producer can write. Kafka makes an exception for the first batch of a partition in certain cases so the consumer can still make progress; therefore, these limits should not be viewed as an absolute barrier blocking every larger batch.

## 5. Spring Kafka listener container manages the poll loop

With Spring Kafka, the listener container creates and manages `KafkaConsumer`. The container runs the poll loop, retrieves records, and invokes the listener method declared by the application.

Example:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        System.out.printf("order event: key=%s value=%s%n",
                record.key(), record.value());
    }
}
```

The application does not need to call `poll()` itself. The listener container handles that and invokes `onMessage` when records arrive. In a standard listener, processing runs on the container-managed consumer thread. When the listener completes, the container continues the poll cycle and processes offsets according to the acknowledgment configuration.

`spring.kafka.consumer.*` properties are used to construct the consumer; listener container configuration lives under `spring.kafka.listener.*` and the properties of `ConcurrentKafkaListenerContainerFactory`/`ContainerProperties`. Do not confuse Kafka client settings with container settings: `max.poll.records` belongs to the consumer client, whereas `pollTimeout` is the wait duration passed to the poll call made by the container.

## 6. Configuring poll and fetch in Spring Boot

Consumer settings can be placed in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 52428800
    listener:
      concurrency: 3
```

In the example:

- Each poll returns at most 100 records.
- The consumer must poll again within 5 minutes.
- The broker may wait up to 500 ms to gather fetch data if the minimum 1 byte is not yet available.
- Per-partition and total fetch response limits are set to illustrative values.
- The listener container is configured with concurrency of three.

The values above are not an optimal parameter set for every application. Start from actual traffic, record size, processing time, and partition count. Spring Boot lets you set Kafka client properties that lack dedicated fields under `consumer.properties`; bracket syntax preserves property names containing dots.

`enable-auto-commit: false` aligns with how the Spring Kafka listener container manages offset commits. In Spring Kafka, if unspecified, the framework typically sets auto-commit to false; declaring it explicitly in the example shows intent. Actual committing still depends on the container's `AckMode`.

## 7. Polling, processing records, and committing offsets

Polling and retrieving records does not mean the records have been processed successfully. The consumer must define when read progress is committed.

In Spring Kafka, the listener container manages acknowledgments and commits according to `AckMode`. With the common default `BATCH`, offsets are committed after all records returned by a poll have been processed. Other modes such as `RECORD`, `MANUAL`, and `MANUAL_IMMEDIATE` let you tune confirmation timing as needed.

Example processing flow:

```text
poll() returns 50 records
       |
       v
listener processes record/batch
       |
       +-- success per AckMode ---> commit offset
       |
       +-- error -----------------> error handler / retry policy
                                      |
                                      v
                               decide retry, seek,
                               recover, or DLT
       |
       v
next poll()
```

If an application commits offsets before completing business tasks, a subsequent error may prevent the record from being re-read. Conversely, if processing finishes but the process stops before committing, the record may be redelivered. Therefore, consumers typically require idempotent processing or appropriate deduplication mechanisms.

Do not commit offsets just because poll returned data. Understand the `AckMode`, error handler, and retry policy used in your listener container.

## 8. Record listeners and batch listeners

One poll can return multiple records. Spring Kafka supports two primary listener styles:

- **Record listener:** the container invokes the method for each record. Business code handles one event at a time, even though poll may return multiple records.
- **Batch listener:** the container passes the set of records from a poll into a single listener invocation. Business code can process them as a batch.

Example batch listener:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-batch-projection",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessages(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            // Convert and process records in the batch.
        }
    }
}
```

The `batchKafkaListenerContainerFactory` must be configured with `setBatchListener(true)` and an appropriate consumer factory. If using a default record listener, you cannot simply change the parameter type to `List` and expect the container to switch to batch mode automatically.

Batch listeners can reduce method invocation overhead and leverage batch database inserts/updates. In return, processing time for the entire batch must stay within the poll interval limit, and error logic must determine which records succeeded or failed according to the container's policy.

## 9. Processing time and the risk of exceeding max.poll.interval.ms

Suppose `max.poll.records=100` and each record takes an average of 100 ms to process sequentially. The nominal processing time for the batch is:

```text
100 records x 100 ms = 10,000 ms = 10 seconds
```

If there are slow database queries, external HTTP calls, or synchronous retries, actual duration can be much higher. When total time between two polls exceeds `max.poll.interval.ms`, the consumer may leave the group and its partitions are reassigned to another consumer.

To reduce the risk:

1. Measure actual processing time at high percentiles, not just the average.
2. Choose `max.poll.records` to match per-record and batch processing times.
3. Increase `max.poll.interval.ms` when business work legitimately takes longer, while keeping bounds and monitoring in place.
4. Use efficient batch operations when they reduce per-record time.
5. Avoid unbounded waits on external services inside a listener.
6. Use pause/resume or controlled backpressure when downstream is temporarily unresponsive.

Do not simply increase `max.poll.interval.ms` to hide a hung consumer. You need I/O timeouts, processing time observability, and a recovery strategy.

## 10. Concurrency and partition count

In Spring Kafka, a listener container's `concurrency` determines how many child consumer threads/containers are created for the listener. Each consumer has its own poll loop and is assigned partitions by the Kafka group coordinator.

Example topic with six partitions:

```text
Topic: orders.events (6 partitions)

concurrency = 1  -> 1 consumer handles 6 partitions
concurrency = 3  -> 3 consumers, typically around 2 partitions per consumer
concurrency = 6  -> up to 6 consumers with assigned partitions
concurrency = 8  -> 2 consumers may have no partitions assigned
```

This illustrates a balanced distribution; actual results depend on the assignor, the total number of consumers in the group, and other members. Within the same consumer group, a partition is assigned to only one consumer at a time. Therefore, setting concurrency higher than the partition count does not allow a single partition to be processed in parallel by multiple consumers.

Increasing concurrency can boost throughput when there are enough partitions and sufficient downstream capacity. It also increases consumer connections, threads, and load on brokers/databases. Choose concurrency based on partition count, throughput targets, and available resources.

## 11. Pause, resume, and backpressure

When a downstream database or service is overloaded, a consumer may need to temporarily stop receiving records from certain partitions. The Kafka client supports `pause()` and `resume()` per partition. The Spring Kafka listener container exposes corresponding APIs to coordinate the consumer on the container thread.

Pausing does not mean closing the consumer or leaving the group. The container can still continue polling to maintain group membership and process unpaused partitions. Once downstream is ready, the container resumes to continue fetching records.

Pause/resume is useful for implementing backpressure, but avoid pausing so long that poll limits are breached or consumers fall too far behind. Monitor consumer lag and pause duration, and clearly define resume conditions.

## 12. Monitoring the poll loop in operations

To know whether consumers are fetching and processing data steadily, monitor both the Kafka client and the application:

| Metric | Meaning |
| --- | --- |
| Consumer lag per partition | Distance between committed offset and log end offset |
| Records consumed rate | Number of records processed by the consumer per unit of time |
| Bytes consumed rate | Volume of data read from Kafka |
| Fetch latency | Response time of fetch requests |
| Fetch size / records per request | Amount of data brokers return to the consumer |
| Processing time | Time the listener spends processing a record or batch |
| Poll interval | Actual interval between poll calls |
| Rebalance count/time | Frequency and duration of consumer group partition reassignments |

Continuously growing consumer lag may stem from higher producer load, slow consumer processing, insufficient fetching, or downstream bottlenecks. Compare lag against processing rate and poll duration to locate the root cause.

## 13. Common issues

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Listener receives many records and takes long to finish | High `max.poll.records` or slow per-record processing | Measure processing time and tune batch size |
| Consumer rebalances frequently | Batch processing exceeds `max.poll.interval.ms`, connection failures, or group membership changes | Check poll interval, I/O timeouts, heartbeat/session, and rebalance logs |
| Consumer lag grows continuously | Processing rate is slower than producer rate | Optimize processing, increase concurrency if partitions and resources allow |
| Poll frequently returns empty batches | Low topic traffic, fetch wait settings, or wrong subscription/assignment | Verify topic, assignment, and fetch settings |
| High latency with low throughput | `fetch.min.bytes` or `fetch.max.wait.ms` too high for low load | Lower batch accumulation wait if latency is prioritized |
| Consumer loses data after error | Committing offsets before processing completes or improper error handling | Inspect `AckMode`, commits, and recovery strategy |
| Consumer memory grows | Oversized batch/fetch or holding records too long in the app | Reduce batch/fetch size, avoid retaining unnecessary payloads |

## 14. Conclusion

The poll loop is the central cycle of a Kafka consumer: the consumer calls `poll()`, receives a set of records from fetched data, processes them, and continues polling. Fetching is the protocol activity between client and broker; properties such as `fetch.min.bytes`, `fetch.max.wait.ms`, and byte limits control how data is accumulated and returned. `max.poll.records` limits records per poll, while `max.poll.interval.ms` limits the time between polls.

In Spring Kafka, the listener container manages the poll loop and invokes `@KafkaListener`. For a stable consumer, balance batch size, processing time, offset commits, concurrency, and partition count while monitoring consumer lag, poll intervals, and rebalances. Understanding this cycle properly lets you tune throughput and latency while keeping the consumer group stable.

## References

- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
