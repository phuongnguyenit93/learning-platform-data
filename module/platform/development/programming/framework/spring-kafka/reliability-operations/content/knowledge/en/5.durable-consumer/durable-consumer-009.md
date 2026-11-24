# fetch.min.bytes and fetch.max.wait.ms

## 1. Role in Consumer Data Fetching

A Kafka consumer does not fetch each record in a separate request. The consumer sends a Fetch request to the broker holding the leaders of assigned partitions, and the broker returns available records from the log. The consumer can fetch data in batches, buffer it locally, and deliver it to the application via poll calls.

The two configurations **fetch.min.bytes** and **fetch.max.wait.ms** determine how long the broker should wait to accumulate enough data before answering a Fetch request:

- **fetch.min.bytes** is the minimum amount of data the consumer wants the broker to return in a Fetch response.
- **fetch.max.wait.ms** is the maximum time the broker is allowed to wait when available data has not yet reached that minimum.

The goal of both settings is balancing latency against batching efficiency. If the consumer receives a response immediately as soon as a tiny amount of data arrives, the application can process new events faster but must issue many small Fetch requests. If the consumer asks the broker to accumulate more data, request counts can drop and batches grow larger, though some records must wait longer before being returned.

In Spring Kafka, these are Kafka consumer properties. They apply to consumers created by ConsumerFactory and used by the listener container.

## 2. How Does fetch.min.bytes Work?

**fetch.min.bytes** sets the minimum byte threshold the broker tries to accumulate before answering a Fetch request. The Kafka consumer default is 1 byte.

For example, a consumer sets fetch.min.bytes to 65,536 bytes (64 KiB). When the broker receives a Fetch request:

1. The broker checks available data for the partitions in the request.
2. If available data meets the threshold, the broker can respond immediately.
3. If not enough yet, the broker holds the request while waiting for new data.
4. Once accumulated data reaches the threshold, the broker responds.
5. If the threshold is still unmet when fetch.max.wait.ms expires, the broker returns whatever data is available, even if total bytes are below fetch.min.bytes.

This threshold is measured in bytes of the broker's fetch response payload for the request, not record count and not a per-message threshold. One large record can fill most of the response; many small records can add up to meet the threshold.

### 2.1. Impact of Low and High Values

| Configuration | Typical Behavior | Trade-off |
|---|---|---|
| fetch.min.bytes = 1 | Broker can return data as soon as any is ready | Low latency, but can produce many small responses |
| fetch.min.bytes = 16 KiB | Broker gets a chance to batch moderately | Balanced for moderate-traffic workloads |
| fetch.min.bytes = 64 KiB or higher | Broker waits to accumulate more bytes before responding | Larger batches, fewer requests under sufficient load; events may wait longer |
| fetch.min.bytes too large for traffic | Threshold is rarely met before wait timeout | Fetch requests routinely wait until max wait, adding latency without meaningfully improving batching |

Values in the table are illustrative. A consumer reading a low-traffic topic may never accumulate 64 KiB within a short window. Conversely, a consumer reading many high-throughput partitions may hit that threshold very quickly.

### 2.2. Units and Scope

Kafka accepts fetch.min.bytes in bytes. When configuring directly via the Kafka client, the value is an integer:

~~~java
props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
~~~

When configuring via Spring Boot, you can use a DataSize such as 64KB. Check your Spring Boot version's property binding behavior if the application uses custom configuration.

The setting applies per Kafka consumer. When Spring Kafka creates multiple consumers via concurrency or multiple listener containers, each consumer maintains its own Fetch requests and buffers. Total fetch traffic to brokers therefore also depends on consumer count, assigned partitions, and partition placement across brokers.

## 3. How Does fetch.max.wait.ms Work?

**fetch.max.wait.ms** sets the maximum time the broker waits to satisfy fetch.min.bytes when insufficient data is available. The Kafka consumer default is 500 milliseconds.

Suppose a consumer configures:

- fetch.min.bytes = 65,536
- fetch.max.wait.ms = 200

If the broker already has 64 KiB for the request, it can respond immediately. If only 8 KiB is available, the broker may wait for more records. If data reaches 64 KiB after 70 ms, the response returns then. If after 200 ms only 20 KiB is available, the broker returns the available data when the wait deadline expires.

This means fetch.max.wait.ms is a server-side wait cap, not a fixed delay every request must wait. When enough data arrives early, responses return early.

### 3.1. Low and High Values

| Value | Behavior | When to Consider |
|---|---|---|
| 10–50 ms | Broker waits only briefly when data is below threshold | Flows requiring fast response, accepting smaller batches |
| 100–200 ms | Gives extra time to accumulate data | Moderate workloads needing a balance between latency and batching |
| 500 ms | Kafka consumer default | Baseline starting point for measurement |
| 1,000 ms or higher | Can accumulate larger batches in sparse streams | Consider only when latency budget allows and evidence shows meaningful request reduction |

Higher values can increase how long events wait at the broker during low-traffic periods. It does not automatically increase throughput; the broker can only accumulate more data if new records arrive during that window.

### 3.2. fetch.max.wait.ms Is Not Poll Timeout

These configurations are frequently confused:

- fetch.max.wait.ms is sent inside the Fetch request and governs how long the broker may wait to accumulate bytes.
- poll(Duration) is how long the KafkaConsumer application call waits to return buffered data or poll results.
- max.poll.interval.ms limits the maximum time between poll calls before the consumer may be considered inactive in the group.

A poll call can return records already sitting in the local buffer without waiting for a new broker fetch. Conversely, a fetch request can wait at the broker while the application proceeds according to the Kafka client's poll mechanics. Never increase max.poll.interval.ms simply to compensate for fetch.max.wait.ms without identifying the true cause.

## 4. How Both Settings Work Together

The two properties form a data-accumulation policy:

- fetch.min.bytes specifies the desired data size for a response.
- fetch.max.wait.ms caps how long to wait to reach that size.

You can picture the broker deciding to return a Fetch response when either condition is met:

~~~text
                    Fetch request
                          |
                          v
             Enough fetch.min.bytes yet?
                    /           \
                  Yes            No
                  |                |
                  v                v
             Send response    Keep waiting for records
                                   |
                                   v
                        fetch.max.wait.ms elapsed?
                               /          \
                             No            Yes
                              |             |
                              v             v
                          Keep           Send available
                          waiting             data
~~~

Actual wait duration depends on the rate records arrive at the broker and how partitions are distributed. Under sufficiently high traffic, the byte threshold is reached quickly. Under low or bursty traffic, the broker may often wait up to max wait.

### 4.1. Example Estimating Accumulable Data

Suppose a broker receives data for partitions fetched by a consumer at an average rate of about 1 MiB/second. In 100 ms, expected incoming data is roughly:

\[
1\ \text{MiB/s} \times 0.1\ \text{s} \approx 0.1\ \text{MiB} \approx 102\ \text{KiB}
\]

Under relatively steady load, a 64 KiB threshold can be reached before 100 ms elapses. If throughput is only around 100 KiB/second, the same 100 ms yields only ~10 KiB; the broker may wait nearly the entire timeout or return a response below threshold.

This is only an approximation. Real traffic may arrive in bursts, partitions may span multiple brokers, record sizes vary, and responses remain subject to other fetch limits.

### 4.2. Choosing a Pair of Values

Do not pick the two values independently. For example:

- High fetch.min.bytes paired with very low fetch.max.wait.ms: the broker has little time to reach the threshold, so responses routinely return below threshold.
- Low fetch.min.bytes paired with high fetch.max.wait.ms: the threshold is easily met, so max wait rarely affects active traffic; when idle, behavior also depends on how brokers handle requests.
- Moderate fetch.min.bytes paired with moderate fetch.max.wait.ms: gives the broker room to batch while bounding added latency.

When starting to tune, adjust one intentional pair, measure outcomes, and compare against baseline. Avoid raising multiple consumer limits simultaneously without knowing which change produced the effect.

## 5. Configuration in Spring Boot and Spring Kafka

Spring Boot exposes properties for both settings under consumer. The following example sets a 64 KiB threshold and a 200 ms maximum wait:

~~~yaml
spring:
  kafka:
    consumer:
      fetch-min-size: 64KB
      fetch-max-wait: 200ms
      max-poll-records: 500
~~~

In Spring Boot, fetch-min-size binds as a data size and fetch-max-wait as a duration. These properties are passed to Kafka consumers created by the consumer factory.

If you need to set Kafka properties directly inside the properties map, declare:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 200
~~~

Use only one configuration style per property to avoid duplicates or ambiguity over which source wins. If the application uses a custom ConsumerFactory, verify it actually receives properties from Spring Boot or sets those values itself.

### 5.1. Java Configuration

For applications creating ConsumerFactory manually, use ConsumerConfig:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-fulfillment");
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );

    props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
    props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 200);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 500);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

This example illustrates only the fetch configuration portion. Production applications must add an appropriate value deserializer, trusted packages or type mapping, security, group, and environment-specific offset settings. If Spring Boot already auto-configures the consumer factory, do not create a separate factory just to change these two properties.

### 5.2. Applying to @KafkaListener

The listener container obtains consumers from ConsumerFactory. Hence, consumer factory settings apply to the listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void handle(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

If the listener container has concurrency greater than 1, each consumer running in the container uses the corresponding fetch settings. Increasing concurrency can increase parallel reading, but also increases active consumers and fetch load on brokers. fetch.min.bytes and fetch.max.wait.ms must still be evaluated in the context of total active consumers.

## 6. Related Fetch Limits

fetch.min.bytes and fetch.max.wait.ms are not the only limits governing returned data size. When tuning, understand related properties:

| Property | Scope | Effect |
|---|---|---|
| fetch.min.bytes | Consumer request | Minimum bytes the broker tries to accumulate before responding |
| fetch.max.wait.ms | Consumer request | Maximum time the broker waits to hit the minimum threshold |
| fetch.max.bytes | Consumer | Cap on total data the broker returns for one Fetch response |
| max.partition.fetch.bytes | Consumer | Cap on data returned per partition in one Fetch response |
| max.poll.records | Consumer | Maximum records the application receives from one poll |
| max.poll.interval.ms | Consumer group | Maximum time between poll calls |

Both fetch.max.bytes and max.partition.fetch.bytes can keep a response smaller than fetch.min.bytes. If the broker cannot reach the threshold before max wait, it still returns available data. Kafka also makes an exception for the first batch of a partition so consumers can make progress when a single record batch exceeds configured limits; thus size limits are not always absolute hard ceilings.

### 6.1. fetch.max.bytes

fetch.max.bytes caps the total data a broker returns in a single Fetch response. Setting the total limit too low while a consumer reads many partitions or large record batches can force the consumer to issue more requests to pull all data.

Do not raise fetch.max.bytes just because fetch.min.bytes increased. Evaluate actual batch sizes, partitions per broker, and consumer memory before adjusting.

### 6.2. max.partition.fetch.bytes

max.partition.fetch.bytes caps data returned per partition in one fetch. If a consumer has many assigned partitions, the total response can exceed the per-partition limit because it contains data from multiple partitions.

This value must be large enough for the consumer to read the largest record batch a producer can emit. Kafka allows returning the first batch above the limit so consumers do not get stuck on an unreadable batch.

### 6.3. max.poll.records

max.poll.records limits how many records one poll returns to the application. It does not directly limit how many bytes the broker fetches and does not replace fetch.min.bytes.

For example, a consumer can fetch plenty of data into its buffer, while each poll delivers at most 500 records to the listener. This affects how the application consumes and batches work, whereas fetch.min.bytes controls broker byte accumulation for responses.

### 6.4. Distinguishing Consumer Fetch from Replication Fetch

Kafka brokers also have follower replicas fetching data from leaders. Broker settings such as replica.fetch.min.bytes and replica.fetch.wait.max.ms govern inter-broker replication.

They serve a different purpose from consumer fetch.min.bytes and fetch.max.wait.ms. Changing the two consumer properties does not require changing broker replication properties. When investigating ISR or under-replicated partitions, examine replication settings separately.

## 7. Impact on Latency, Throughput, and Resources

### 7.1. Event Latency

When fetch.min.bytes is high, the consumer may have to wait for the broker to gather more records. fetch.max.wait.ms caps that added wait. Thus, both properties can increase the elapsed time from when a record is written to Kafka until the consumer receives it.

The effect is most visible on low-traffic topics or quiet partitions. On high-traffic topics, the threshold is reached quickly so wait times are usually short.

If an SLO requires events to be processed within a few hundred milliseconds, do not set max wait near the entire latency budget. Leave headroom for network, consumer scheduling, listener execution, and downstream calls.

### 7.2. Throughput and Batching Efficiency

Larger fetch thresholds let consumers receive more bytes per response. That can lower request rates, reduce network overhead, and improve batch processing efficiency.

However, larger fetches only help if the application can keep up. If the listener processes slowly, larger fetches increase buffering and processing duration, causing consumer lag to keep growing.

### 7.3. Network and Broker Load

Low fetch.min.bytes in high-throughput environments can generate many small responses. Raising the threshold moderately can reduce request rate and overhead.

Conversely, each consumer can issue Fetch requests to multiple brokers. As consumer counts grow, total requests can still be high even when each response carries more data. Measure request rates and network bytes instead of guessing from a single property.

### 7.4. Consumer Memory

Fetch responses are buffered in the client. Increasing fetch sizes can raise buffered bytes in memory, especially when consumers read many partitions across multiple brokers.

Watch heap usage, memory pressure, buffered record counts, and listener processing duration. Never raise fetch.max.bytes, max.partition.fetch.bytes, and concurrency simultaneously without estimating total memory demand.

## 8. Choosing Settings by Workload Type

No single pair of values is optimal for every consumer. Start from service goals, traffic rates, and record sizes.

| Workload Type | Illustrative Starting Point | Rationale |
|---|---|---|
| Latency-sensitive events | fetch.min.bytes = 1; fetch.max.wait.ms = 50–100 | Minimizes broker wait for batching |
| Moderate workload, steady traffic | fetch.min.bytes = 16–64 KiB; fetch.max.wait.ms = 100–200 | Gives room for moderate batching |
| High-throughput consumer | fetch.min.bytes = 64–256 KiB; fetch.max.wait.ms = 200–500 | Can cut small responses when traffic is high enough |
| Sparse topic, background processing | Low or moderate fetch.min.bytes; fetch.max.wait.ms within latency budget | Avoids waiting long for a byte threshold rarely met |
| Consumer reading many partitions | Tune by per-broker throughput and actual fetch size | Total bytes span partitions, though load may be uneven |

These values are starting points for experimentation, not universal recommendations. In particular, do not push fetch.min.bytes into megabytes chasing larger batches if per-broker throughput cannot reach that threshold within the wait timeout.

### 8.1. Low-Latency Streams

For order processing, payments, or near-real-time notifications, event latency may matter more than reducing Fetch request counts.

You can start with fetch.min.bytes at 1 and fetch.max.wait.ms around 50–100 ms. Then measure event freshness and request rate. If latency stays low yet produces excessive small responses, increase the threshold incrementally.

Do not blame fetch.max.wait.ms alone for latency. Events can also wait because the consumer is not polling, the listener is busy with a prior batch, a rebalance occurred, or downstream is slow.

### 8.2. High-Throughput Streams

For telemetry, clickstream, or high-volume data sync, the goal may be maximizing bytes consumed rate and cutting request overhead.

You can test fetch.min.bytes at 64 KiB or 128 KiB with fetch.max.wait.ms at 100–300 ms. If brokers receive steady data, the threshold hits early. Under bursty load, max wait gives the broker time to collect records in the next burst.

Also monitor max.partition.fetch.bytes and fetch.max.bytes to ensure responses can carry the desired batch sizes.

### 8.3. Low-Traffic Topics

For topics receiving only a few events per second, a 64 KiB fetch threshold may rarely be reached. Brokers will routinely respond after the wait timeout expires, inflating latency for the first event in each wave.

In this case, lowering fetch.min.bytes is usually more helpful than raising fetch.max.wait.ms. If latency requirements allow, max wait can stay moderate; if events must reach consumers quickly, reduce the wait time and confirm with end-to-end measurements.

## 9. Measuring and Observing After Changes

Do not evaluate tuning using consumer lag alone. Combine fetch telemetry, business latency, throughput, and resource metrics.

| Signal | What to Observe |
|---|---|
| Fetch size average/max | Did response size increase after raising fetch.min.bytes? |
| Fetch latency average | How long did the broker take to answer Fetch requests? |
| Fetch rate | Did Fetch requests per second decrease? |
| Records per request | How many records does each request average? |
| Bytes consumed rate | How many bytes per second does the consumer read? |
| Records consumed rate | Rate of records received by the consumer |
| Consumer lag | Is the consumer keeping pace with producer rate? |
| Event freshness | How long does an event wait from Kafka write to processing completion? |
| Consumer heap/GC | Do larger buffers and batches increase memory pressure? |
| Broker network/request metrics | Did the change reduce overhead or add broker pressure? |

Exact metric names depend on the Kafka client, JMX exporter, Micrometer, and Spring Kafka version. Verify exported metrics in your environment before setting alerts.

### 9.1. Reading Combined Signals

- Fetch size increases, fetch rate drops, bytes consumed rate holds steady or rises: batching is likely more effective.
- Fetch size stays small while fetch latency hovers near max wait: min bytes threshold is likely too high for current traffic.
- Fetch size increases yet consumer lag and event freshness worsen: larger batches may be slowing application processing or overwhelming downstream.
- Fetch rate drops while broker network bytes stay flat: responses are larger, so total bytes transferred remain similar.
- Consumer lag grows alongside low fetch rate: inspect assignments, poll loop, pause state, rebalances, and downstream before blaming fetch settings.

### 9.2. Measuring Event Freshness

To measure how long events truly spend in the pipeline, record a timestamp at the producer or in the payload/header and compare against when the consumer finishes processing. Synchronize clocks across hosts and use consistent timestamp definitions.

A consumer with 0 lag can still have high event freshness if the listener processes slowly or events sit in application buffers. Conversely, a few hundred records of lag may be acceptable under high throughput if event age stays within SLO.

## 10. Controlled Tuning Procedure

You can follow this sequence:

1. Record baseline: fetch rate, fetch size, fetch latency, bytes consumed rate, consumer lag, event freshness, heap, and broker load.
2. Pick the primary goal: lower latency, higher throughput, or lower request overhead.
3. Measure average and burst traffic per broker, not just cluster-wide totals.
4. Adjust fetch.min.bytes first or as a pair with fetch.max.wait.ms in a small step.
5. Run representative workloads across peak and off-peak periods.
6. Compare p50/p95/p99 event freshness, throughput, request rate, and resources.
7. Keep the configuration if it improves the target without regressing other SLOs; otherwise revert and test another step.
8. Document values, rationale, and outcomes so future tuning has a reliable baseline.

During testing, hold producer throughput, consumer count, partition assignment, and record sizes as constant as possible. Changing everything at once makes it hard to tell which change drove the result.

## 11. Common Configuration Mistakes and Diagnostics

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Events reach consumer slower after tuning | fetch.min.bytes too high or fetch.max.wait.ms too long | Check fetch latency, event freshness, and incoming record rate |
| Fetch responses frequently smaller than fetch.min.bytes | Insufficient data before max wait expires | Compare actual throughput against the byte threshold |
| Very high fetch request rate | Low byte threshold, many consumers, or many partitions/brokers | Check fetch rate by client and broker |
| Consumer lag grows despite large fetch sizes | Slow listener/downstream, irregular polling, or rebalances | Compare records consumed rate with processing rate |
| Heap grows after raising fetch limits | Larger fetch responses and buffers | Check fetch.max.bytes, max.partition.fetch.bytes, concurrency, and GC |
| Only some partitions lag | Uneven traffic or partition placement | Inspect per-partition lag and event age, broker leaders, and key distribution |
| Tuning does not change behavior | Properties not applied to actual ConsumerFactory or listener uses a different factory | Inspect effective configuration of each consumer |

If you suspect settings did not take effect, identify the consumer client ID and the factory that created it. An application may have multiple listener containers or multiple ConsumerFactory beans with separate configs. Editing application.yml has no effect on a custom factory if that factory does not bind those properties.

## 12. Misconceptions to Avoid

**Assuming fetch.min.bytes is a minimum record count.** It is a byte count, so record size directly affects how many records fit in a response.

**Assuming the broker must always return fetch.min.bytes.** It is a target threshold the broker tries to meet; fetch.max.wait.ms caps the wait time. When the deadline expires, the broker may return fewer bytes.

**Assuming fetch.max.wait.ms is maximum end-to-end latency.** It only caps how long the broker waits on a Fetch request when data is insufficient. Network, polling, listener work, and downstream still add latency.

**Assuming raising fetch.min.bytes always increases throughput.** Under low traffic, the broker cannot gather enough data and the consumer simply waits longer. Throughput also depends on producers, partitions, brokers, and application processing speed.

**Confusing max.poll.records with fetch size.** max.poll.records caps records returned to the application in one poll; fetch limits govern data returned by the broker.

**Confusing consumer fetch with broker replication fetch.** fetch.min.bytes and fetch.max.wait.ms are consumer properties. replica.fetch.min.bytes and replica.fetch.wait.max.ms belong to followers fetching from leaders.

**Increasing concurrency to compensate for poor fetch tuning.** More consumers can add requests and broker pressure while doing nothing to fix a slow listener or downstream.

## 13. Combined Example for an Order Consumer

Suppose Order Service writes OrderCreated events to topic orders.created. The fulfillment consumer must process events within 2 seconds. Each event averages about 1 KiB, with normal traffic around 200 records/second across brokers read by the consumer.

If the consumer sets fetch.min.bytes to 64 KiB, it takes roughly 64 records of ~1 KiB to hit the threshold in one response. At 200 records/second evenly spread, that volume could accumulate in about 320 ms if all traffic landed on one broker. In practice, partitions span multiple brokers, so each broker may see a lower rate and accumulation time will differ.

A reasonable starting point to test might be:

~~~yaml
spring:
  kafka:
    consumer:
      fetch-min-size: 16KB
      fetch-max-wait: 100ms
      max-poll-records: 200
~~~

After a trial rollout, the operations team measures:

- p95/p99 from when an event is written to Kafka until fulfillment completes.
- Average fetch size and fetch rate.
- Records consumed rate and consumer lag per partition.
- Listener processing duration and downstream fulfillment latency.
- Heap and GC as consumers receive larger batches.

If event freshness has plenty of headroom yet fetch rate is high and responses are small, test raising fetch.min.bytes to 32 KiB or 64 KiB. If p99 event freshness approaches the 2-second SLO, lower the threshold or max wait to cut accumulation time. If lag rises because the fulfillment API is slow, fix downstream first; reducing fetch wait cannot make the listener execute faster.

The numbers above are illustrative examples showing how to reason from throughput and record size. Final configuration must rely on real measurements per broker, partition, and consumer group.

## 14. Key Takeaways

fetch.min.bytes governs the minimum bytes a broker tries to accumulate for a Fetch response; fetch.max.wait.ms caps how long the broker waits to hit that threshold. Lower values favor latency, while higher values can improve batching and cut request overhead when traffic is high enough.

In Spring Kafka, configure both properties on the consumer factory used by the listener container. When tuning, evaluate fetch.max.bytes, max.partition.fetch.bytes, max.poll.records, concurrency, consumer lag, and event freshness together. Measure real workloads before and after changes to balance latency, throughput, and broker/consumer resources.

