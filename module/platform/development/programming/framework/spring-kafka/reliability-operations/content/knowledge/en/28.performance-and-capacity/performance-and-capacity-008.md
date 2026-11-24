# CPU, Heap, and Network

The performance of a Spring Kafka application does not depend solely on consumer count or partition count. A consumer can read data very quickly yet fail to keep up because CPU is saturated; it can process short records yet pause frequently due to garbage collection; or it can have ample CPU and heap while network throughput, latency, or broker connectivity becomes the bottleneck.

**CPU, heap, and network** are the three resource groups that must be observed together when planning capacity for producers, consumers, and listener containers. Each group impacts different parts of the pipeline:

    Producer application
       |
       +--> serialize / compress / batch
       |          |
       |          +--> CPU
       |          +--> heap / buffer.memory
       |
       +--> network send --------------------+
                                              |
                                           Kafka brokers
                                              |
    Consumer application                      |
       |                                      |
       +<-- network fetch <-------------------+
       |
       +--> deserialize / listener / business logic
       |          |
       |          +--> CPU
       |          +--> heap / object allocation
       |          +--> GC pauses
       |
       +--> offset commit / downstream I/O

When any of the three resources runs low, throughput can drop, latency and consumer lag can rise, retries increase, or pods get OOMKilled. Increasing concurrency or replicas without identifying the bottleneck can simply consume more resources and push pressure onto brokers or downstream systems.

This lesson belongs to the **Performance and Capacity** chapter of Spring Kafka Reliability Operations. Its goal is to recognize the symptoms of CPU, heap, and network bottlenecks, understand how Kafka/Spring Kafka configurations affect them, calculate capacity on a sound basis, and choose safe operational actions.

## 1. Distinguishing Throughput from Resource Utilization

These concepts are related, yet none can substitute for another:

| Metric | Question Answered |
|---|---|
| Throughput | How many records/bytes per second is the system processing? |
| Latency | How long does a record or request take? |
| CPU utilization | What fraction of allocated CPU capacity is currently busy? |
| Heap usage | How many objects is the JVM currently holding in the heap? |
| Allocation rate | How fast is the application allocating objects? |
| GC pause | How long does the JVM pause application threads to collect garbage? |
| Network throughput | How many bytes per second is the application sending/receiving? |
| Network latency | How long does a request/response take to traverse the network? |
| Consumer lag | How far behind the log end offset is the consumer group, according to how it is measured? |

A service at 25% CPU does not necessarily have 3x remaining capacity. A single thread may already be saturating one core while other cores sit idle. A service with 40% free heap is not necessarily safe either if the allocation rate is very high and GC runs continuously.

Read resource metrics alongside records/sec, bytes/sec, listener duration, error rates, commit progress, and oldest record age. Capacity is meaningful only when tied to a specific load level and a specific SLO.

## 2. Where Is CPU Used in the Kafka Pipeline?

Producer-side CPU is typically spent on:

- Payload serialization and validation.
- Compression of record batches.
- TLS encryption/decryption.
- Partition selection and key hashing.
- Batch construction, buffering, and retry bookkeeping.
- Callbacks, logging, metrics, and tracing.
- Business logic prior to publishing.

Consumer-side CPU is typically spent on:

- Fetch response processing and decompression.
- Deserialization, schema conversion, and validation.
- Listener business logic.
- Object mapping, JSON parsing, and allocation.
- TLS/network processing.
- Offset/transaction bookkeeping.
- Logging, tracing, metrics, and error handling.

If the listener calls a database or HTTP API and waits on I/O, the consumer thread may use little CPU while waiting. Therefore, low CPU does not prove a consumer is idle or has spare throughput.

## 3. A Single CPU Core Can Be the Bottleneck Despite Low Pod CPU

Suppose a pod is allocated 8 vCPUs. One consumer thread processes sequentially and consumes nearly an entire core; the remaining threads mostly wait on I/O.

    Pod capacity: 8 vCPU
    Consumer thread A: 100% of 1 core
    Other cores: mostly idle

    Container CPU total: ~12.5% of 8 vCPU

The dashboard may show only 12.5% CPU, yet the throughput of the partition owned by thread A has already hit the single-threaded sequential processing ceiling.

What to observe:

- Per-thread CPU or thread dumps/JFR.
- Consumer concurrency and assigned partitions.
- Processing duration per listener.
- Hot partition/key distribution.
- Container CPU throttling.
- Overall pod and node CPU usage.

Raising pod CPU requests/limits may not speed up a single-threaded code path. You need to optimize the code, shard partitions/workloads, or add valid parallelism.

## 4. CPU Requests, CPU Limits, and Throttling in Kubernetes

In Kubernetes:

- **CPU request** helps the scheduler place pods on nodes and serves as the basis for certain CPU share calculations.
- **CPU limit** caps how much CPU a container can consume via cgroup enforcement.
- When hitting the limit, the container can be throttled even if the node has spare CPU.
- Prolonged CPU throttling can slow down listener processing, GC threads, and monitoring tasks.

Example:

~~~yaml
resources:
  requests:
    cpu: "1"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "2Gi"
~~~

This is an example configuration, not a default recommendation. Choose requests/limits from load tests and production observations.

Important metrics:

- Container CPU usage.
- CPU throttled periods.
- CPU throttled time.
- Node CPU pressure.
- JVM process CPU.
- Listener processing p95/p99.

If pod CPU usage looks low while throttling is high, inspect cgroup limits and how metrics are aggregated. Do not conclude CPU is sufficient from a single aggregate utilization figure.

## 5. CPU Throttling Affects Polls and Consumer Groups

When a consumer is throttled, threads can slow down at multiple stages:

    CPU limit reached
          |
          v
    Consumer/listener thread receives less CPU
          |
          +--> slow deserialization
          +--> slow listener processing
          +--> delayed callback/commit handling
          +--> next poll delayed
          |
          v
    Consumer lag increases
          |
          v
    May approach max.poll.interval.ms

If the interval between polls exceeds `max.poll.interval.ms`, the consumer group can change membership and rebalance per protocol. This moves partitions across members and can cause uncommitted records to be redelivered.

Do not raise `max.poll.interval.ms` to mask prolonged CPU starvation. Inspect CPU limits, processing times, `max.poll.records`, and listener deadlines.

## 6. What Does the JVM Heap Contain?

The heap is the JVM memory region used to allocate most Java objects. In Spring Kafka, the heap may contain:

- `ConsumerRecord` instances and deserialized payloads.
- `ProducerRecord` instances and application-layer serialized buffers.
- Strings, byte arrays, JSON trees, and DTOs.
- Batches/lists of records returned from poll.
- Objects inside listeners and downstream clients.
- Retry/recovery metadata.
- Caches, application state, and queues.
- Objects created by the Kafka client, Spring, Micrometer, and tracing.

The heap is not the container's entire memory footprint. The process also uses:

- Metaspace for class metadata.
- Thread stacks.
- Direct/off-heap buffers.
- Native libraries.
- TLS/native networking buffers.
- Code cache and JVM internal structures.
- Memory allocator overhead.

Therefore, setting `-Xmx` equal to the container memory limit can cause the process to be OOMKilled even before the heap reaches max.

## 7. Heap, RSS, and Container Memory Differ

| Memory | Meaning |
|---|---|
| Java heap used | Objects currently live/allocated in the heap |
| Java heap committed | Heap memory the JVM has committed/reserved for use |
| Java heap max (`-Xmx`) | Maximum heap limit |
| Metaspace | Class metadata |
| Thread stack | Stack per thread |
| Direct memory | Off-heap buffers, such as `ByteBuffer` |
| Native memory | JVM, TLS, libraries, allocator |
| RSS | Resident memory currently in RAM |
| Container memory usage | Container memory accounted by cgroups |

Example:

    Container memory limit = 2 GiB
    Java heap max          = 1.2 GiB
    Metaspace + stacks     = 250 MiB
    Direct/native          = 300 MiB
    Other overhead         = 150 MiB

    Total potential ~= 1.9 GiB

These numbers are illustrative. As thread count rises, stack memory rises; when producers/consumers use many direct buffers, off-heap usage can rise. When setting `-Xmx`, leave headroom for non-heap memory.

## 8. Choosing Xms and Xmx

Example JVM flags:

~~~text
-Xms512m
-Xmx1536m
-XX:MaxDirectMemorySize=256m
~~~

- `-Xms`: initial heap.
- `-Xmx`: maximum heap.
- `MaxDirectMemorySize`: caps JVM-managed direct buffer memory according to the corresponding configuration.

Do not treat these values as a formula for every pod. Account for container limits, thread counts, metaspace, native memory, TLS, Kafka client buffers, and GC.

In modern container-aware JVMs, the JVM can detect container memory limits and choose heap ergonomics based on memory percentages. However, if the application sets `-Xmx` explicitly, that value can override automatic selection.

Verify the actual flags at runtime, not just by reading the Dockerfile or Helm values.

## 9. Heap Grows Due to High Allocation Rates

A consumer processing JSON can allocate many temporary objects:

    byte[] Kafka payload
       |
       v
    JSON parser nodes
       |
       v
    DTO graph
       |
       v
    Validation / mapping objects
       |
       v
    Business result
       |
       v
    Temporary objects become garbage

Even when each record retains little long-lived data, a high allocation rate can trigger frequent GC. For example, 10,000 records/second, each creating 20 KB of temporary objects:

    Allocation rate = 10,000 * 20 KB
                    = 200 MB/s

This is an illustrative calculation. Actual object allocation may be higher or lower depending on payloads, parsers, and JVM optimizations.

Observe allocation rate and GC pauses, not just heap used after GC. If post-GC heap is stable while allocation rate is very high, the application may still burn significant CPU on GC.

## 10. Heap Leaks vs. Heap Pressure

**Heap pressure:** heap usage rises while processing high load and drops after GC. This can be normal behavior.

**Memory leak:** objects no longer needed remain referenced, causing the post-GC live set to climb steadily over time.

Signs of a leak:

- Heap after GC climbs steadily across multiple cycles.
- Old generation occupancy never returns to baseline.
- OOM occurs even without corresponding traffic growth.
- Heap dumps show collections/caches/queues retaining large objects.
- The dominator tree shows a few roots retaining many payloads/records.

Common leak sources:

- Caches without eviction.
- Maps retaining `eventId`/`ConsumerRecord` indefinitely.
- Listeners holding references in static collections.
- Unreleased `CompletableFuture` instances or callbacks.
- Unbounded async queues.
- Long-lived retry state or tracing baggage.

Do not increase `-Xmx` as the sole fix if the live set keeps rising. A larger heap only delays OOM.

## 11. Unbounded Queues Are a Capacity Risk

A dangerous pattern:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);

@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    executor.submit(() -> orderService.process(event));
}
~~~

A fixed thread pool created via `newFixedThreadPool` uses an unbounded queue by default. If the producer sends faster than workers process, the queue holding event objects grows indefinitely.

Consequences:

- Heap grows continuously.
- GC pressure rises.
- Latency from poll to processing increases.
- The process can OOM.
- The listener may ack/commit records before async tasks finish if the container treats method return as success.

Use bounded queues, in-flight limits, backpressure, and proper acknowledgment after durable processing. Do not try to solve this by expanding heap indefinitely.

## 12. How Does max.poll.records Affect the Heap?

`max.poll.records` caps the maximum number of records returned by a single `poll()` to the application. A large value can make the consumer hold many `ConsumerRecord` objects and payloads at once, especially when the listener processes the entire batch sequentially.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 200
~~~

If records average 100 KB, 200 records represent about 20 MB of raw payload, excluding object overhead, deserialized graphs, batch collections, and other buffers.

You cannot calculate heap solely from payload bytes. A JSON DTO can consume many times more objects than the raw input byte size.

Lowering `max.poll.records` can reduce peak heap and processing time per poll, though it can increase poll overhead and lower throughput. Load test with real record size distributions, including the largest valid records.

## 13. fetch.max.bytes and max.partition.fetch.bytes

The Kafka consumer has fetch settings limiting how much data the broker returns:

- `fetch.max.bytes`: maximum bytes for a single fetch response per client config.
- `max.partition.fetch.bytes`: maximum bytes per partition in a fetch.
- `fetch.min.bytes`: minimum bytes the broker tries to accumulate before returning a response.
- `fetch.max.wait.ms`: time the broker can wait to satisfy `fetch.min.bytes`.

These settings affect network usage, batching, and memory buffers. They do not replace `max.poll.records`, as a fetch may be buffered before the application receives records via poll.

Kafka can return a first batch larger than the per-partition fetch limit so the consumer can make progress when the first batch is oversized. Therefore, do not treat byte fetch limits as absolute hard memory caps.

When tuning, consider record batch sizes, partition counts, concurrent fetches, and heap headroom.

## 14. Producer buffer.memory and max.block.ms

The Kafka producer holds records in buffers before sending them to brokers. Related settings:

- `buffer.memory`: total memory the producer allocates for buffering record batches per client config.
- `max.block.ms`: maximum time calls such as `send()` can block waiting for metadata or buffer allocation.
- `batch.size`: target batch size per partition.
- `linger.ms`: time the producer waits for more records to fill a batch.
- `compression.type`: record batch compression codec.

When brokers are unavailable or the producer sends faster than it can transmit, the buffer can fill up. `send()` may block up to `max.block.ms` under certain conditions and then throw an exception.

Example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 67108864
        batch.size: 32768
        linger.ms: 5
        max.block.ms: 10000
        compression.type: lz4
~~~

Values are illustrative. `buffer.memory` is not the producer JVM's total memory; there are also payload objects, serialization buffers, compression buffers, and native/direct allocations.

If you increase `buffer.memory`, the producer can absorb longer bursts, yet it also consumes more memory before backpressure appears. Set limits and monitor buffer availability/wait time.

## 15. Compression Is a CPU-vs.-Network Trade-off

Compression reduces bytes transmitted/stored on Kafka, yet requires CPU to compress and decompress.

| Codec | General Characteristics | When to Consider |
|---|---|---|
| none | Zero compression CPU cost | Small payloads or CPU is the bottleneck |
| gzip | Usually strong compression ratio, higher CPU cost | Network/storage matters more than CPU |
| snappy | Fast compression/decompression, moderate ratio | High-throughput workloads |
| lz4 | Often favors speed with low overhead | Balancing CPU and network |
| zstd | Good compression ratio with configurable levels | When needing tunable CPU/byte trade-off |

Results depend on payloads. Repetitive-field JSON compresses much better than already-compressed payloads or random data.

The producer sets the codec via `compression.type`. Consumers typically decompress batches automatically using codec metadata; no separate codec setting is needed to decompress normal records.

Benchmark with real payloads, measuring CPU, network bytes/sec, broker disk throughput, and end-to-end latency. Do not pick a codec based solely on compression ratio on a single sample file.

## 16. TLS Has CPU and Latency Costs

When Kafka uses TLS, clients must perform encryption/decryption and handshakes. Overhead rises with:

- TLS version and cipher suite.
- Record batch sizes.
- Connection churn.
- Node CPU capability.
- Session resumption and connection reuse.
- Network RTT and packet size.

Restart loops can cause TLS handshakes to spike as pods continually recreate connections. This is another reason to avoid restarting on transient broker disconnects.

Do not disable TLS to improve production throughput if the cluster requires encryption. Measure CPU/network and configure connection lifecycles properly.

## 17. Network Throughput: Byte Rate Matters More Than Record Rate

Two topics both running 10,000 records/second can produce vastly different network loads:

    Topic A: 10,000 * 1 KB  = 10 MB/s
    Topic B: 10,000 * 100 KB = 1,000 MB/s

Record rate alone does not reflect network capacity. Measure:

- Producer bytes sent/sec.
- Consumer bytes received/sec.
- Broker bytes in/out.
- Network interface throughput.
- Retransmissions, packet drops, and errors.
- RTT to brokers.
- Connection count and connection churn.
- TLS handshake rate.

Normalize units: bits/s differs from bytes/s; MB differs from MiB. When sizing capacity, include protocol overhead, headers, replication traffic, and compression.

## 18. Broker Replication Multiplies Network Traffic Beyond Producer Input

Producers send records to partition leaders, and Kafka replication then ships data to followers according to the replication factor and ISR policy.

If producer input is 100 MB/s and the replication factor is 3, total internal broker traffic can substantially exceed 100 MB/s; the exact figure depends on topology, rack placement, batching, protocol, and traffic direction.

Do not compare producer egress to broker NIC throughput expecting them to match. Brokers also handle replication, consumer fetches, inter-broker communication, controller/metadata traffic, and traffic from other consumer groups.

When broker networks saturate, raising consumer concurrency can increase fetch traffic without improving useful throughput.

## 19. Network Latency and Consumer Placement

Consumers placed far from the cluster can experience higher RTT. With synchronous operations like `commitSync`, network latency can directly increase how long the consumer thread waits.

For fetches, Kafka clients typically keep requests outstanding and poll behavior can overlap some work; however, RTT, packet loss, and bandwidth still affect throughput.

Consider:

- Placing consumers close to the Kafka cluster in network topology.
- Using stable routing and proper DNS.
- Avoiding unnecessary cross-region traffic.
- Measuring RTT per broker rather than pinging a single VIP.
- Checking TLS handshakes and connection reuse.
- Evaluating inter-region data transfer costs.

Do not conclude the network is healthy merely because ping is low. Kafka traffic is also affected by TLS, broker request queues, packet retransmissions, and server processing.

## 20. Bandwidth-Delay Product and In-Flight Requests

On high-RTT network paths, achieving high throughput requires enough data/requests in flight to fill the bandwidth-delay product.

    Bandwidth-delay product = Bandwidth * RTT

Example for a 1 Gbit/s link with 40 ms RTT:

    1 Gbit/s * 0.04 s = 40 Mbit
    ~= 5 MB of data in flight

If clients/brokers allow very little outstanding data, throughput can fall below link capacity. Kafka fetch/request batching and socket buffers play a role, yet you should not blindly enlarge every buffer.

Measure bytes/sec and RTT first. If the link is not saturated, enlarging socket buffers may not help. If request queues or broker processing are the bottleneck, bandwidth-delay product is not the root cause.

## 21. Connection Counts and Broker Fan-Out

A consumer group has many consumers, and each consumer may maintain connections to multiple brokers/leaders/coordinators as needed. As replicas and concurrency grow, client connections can multiply.

Example:

    30 pods * concurrency 4 = 120 consumers

Each consumer can interact with brokers serving partitions and the coordinator. Do not treat 120 as the exact TCP connection count since Kafka clients manage connections per node/client; however, it shows that more members/clients increase connection and request load.

When scaling:

- Check connection counts on brokers.
- Monitor request rates and network throughput.
- Avoid rolling out all pods simultaneously.
- Use jitter/backoff on reconnects.
- Cap replicas by partition and downstream capacity.
- Check file descriptors and ephemeral ports on hosts.

More connections do not automatically create throughput if partition counts and dependencies do not scale accordingly.

## 22. Concurrency Affects CPU, Heap, and Network Simultaneously

Spring Kafka `concurrency` spawns child consumers in a concurrent listener container:

~~~java
factory.setConcurrency(4);
~~~

Increasing concurrency can:

- Increase the number of listener threads running business logic in parallel.
- Increase active fetch requests and buffers.
- Increase object allocation and heap pressure.
- Increase network connections/request activity.
- Increase CPU for deserialization/processing.
- Increase group membership and rebalance overhead.

However, the number of assigned consumers in a group is bounded by eligible partitions. If concurrency exceeds partition capacity, extra consumers create no additional useful parallel processing.

Verify concurrency increases through measured throughput gains while SLOs remain met, not simply because CPU utilization looks low.

## 23. Partition Skew Creates Uneven Bottlenecks

A topic with 24 partitions does not guarantee equal load per partition. If key distribution is skewed, one partition may receive 60% of traffic.

    P0: 60% records
    P1-P23: split the remaining 40%

The consumer owning P0 may run hot on CPU and build large lag while other consumers sit idle.

Check:

- Records/bytes in per partition.
- Consumer lag per partition.
- Processing duration per partition if available.
- Key distribution and partitioner.
- Hot business keys.
- Number of assigned consumers.

Adding replicas will not solve a hot partition if key ordering forces all records for that key into the same partition. You may need to change the partition key or business design while preserving ordering semantics.

## 24. Batch Size and Linger Affect Throughput

Producer `batch.size` and `linger.ms` work together to accumulate records per partition before sending.

- Larger batches can improve network/compression efficiency.
- Higher linger gives more batching opportunities, yet adds send latency.
- Many partitions spread traffic out, making each partition's batch harder to fill.
- Overly large batches increase memory and can cause network bursts.
- Overly small batches increase request overhead.

Example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536
        linger.ms: 10
        compression.type: lz4
~~~

This is a starting point for benchmarking, not a universal standard. `batch.size` is a per-partition batch target; the producer can send smaller batches when linger expires or buffer pressure occurs.

Measure records/batch, bytes/batch, request rate, compression CPU, and end-to-end latency.

## 25. Consumer Fetch Batching and Heap Headroom

Consumer fetches can bundle bytes from multiple partitions into one response. Fetch settings affect both network efficiency and bufferable data volume.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 100
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 200
~~~

Understand that:

- `fetch.min.bytes` helps the broker accumulate data before returning a fetch, trading off latency.
- `fetch.max.wait.ms` bounds how long the broker waits to meet `fetch.min.bytes`.
- `fetch.max.bytes` caps total fetch response per client config, with an exception to guarantee progress on the first batch.
- `max.partition.fetch.bytes` applies a per-partition cap with the first-batch exception.
- `max.poll.records` caps the number of records returned to the application, not total bytes.

Size fetches based on record size distribution, partition count, and heap. Setting large fetches with a small `-Xmx` creates heap pressure; setting fetches too small raises request overhead.

## 26. Record Size and Payload Design

Large records impact simultaneously:

- Heap via byte arrays and DTO graphs.
- CPU via serialization/deserialization/compression.
- Network bandwidth and request latency.
- Broker memory/disk and replication.
- GC via large allocations.
- Max request/record size constraints.

If an event carries files/images or hundreds of KB of repetitive data, consider storing large payloads in object storage/databases and sending only a reference plus necessary metadata via Kafka.

When changing schemas/payloads:

1. Measure p50/p95/p99 record sizes.
2. Check max message/request sizes on producer, broker, and consumer.
3. Measure bytes/sec and compression ratio.
4. Measure heap allocation per record.
5. Evaluate compatibility and retention.
6. Do not log full large payloads in listeners.

Record size limits should rest on contracts and capacity, not merely default values.

## 27. Direct Memory and Kafka Network Buffers

The Kafka Java client and networking stack can use `ByteBuffer`/direct memory. Direct buffers live outside the Java heap, so heap graphs can look normal even while container memory climbs.

Monitor:

- Direct buffer pool count/used/capacity via JVM `BufferPoolMXBean`.
- `MaxDirectMemorySize` if configured.
- Native memory tracking when enabled.
- Container RSS and memory working set.
- Connection counts and socket buffers.

Do not raise direct memory indefinitely to cure `OutOfMemoryError: Direct buffer memory`. Inspect what holds buffers, allocation rates, client counts, and consumer/producer lifecycles.

Direct memory and kernel socket buffers are separate regions; do not add or compare them without understanding metric sources.

## 28. Thread Count and Stack Memory

Increasing Spring Kafka concurrency also increases consumer threads. In addition, the application has web threads, schedulers, producer callbacks, database pools, async executors, and tracing/exporter workers.

Every Java thread allocates native stack memory. If thread count grows too high, the process can consume substantial off-heap memory and fail to create new threads.

Check:

- JVM thread count.
- Thread states.
- `-Xss` and stack memory budgets.
- Executor queue depth.
- Database connection pool size.
- Group-wide Kafka concurrency.
- Thread churn from repeatedly creating executors.

Do not mechanically set consumer concurrency equal to vCPU count. I/O-bound workloads may warrant more threads than CPUs, yet must still stay bounded by heap, connections, and downstream capacity.

## 29. GC Pauses and Throughput

The garbage collector affects latency and CPU. Under high heap pressure, GC can run frequently or pause for long intervals.

Signs:

- Rising p95/p99 GC pauses.
- High allocation rates.
- Rising old generation occupancy.
- Throughput dips coinciding with GC cycles.
- Listener duration spikes aligned with GC events.
- High container memory even when post-GC heap used is modest.

Use GC logs and JVM metrics to analyze. On modern Java, G1 is a common default; do not switch collectors based on a single high pause.

Optimize allocations before tuning the collector:

- Avoid parsing the same payload multiple times.
- Avoid creating unnecessary intermediate objects.
- Bound batches/queues.
- Do not retain `ConsumerRecord`/payloads longer than needed.
- Use efficient serializers/deserializers.
- Inspect cache and collection retention.

GC tuning cannot compensate for unbounded queues or memory leaks.

## 30. Optimizing Deserialization and Serialization

Serialization/deserialization can be a CPU hotspot, especially with large JSON payloads or complex schema conversions.

Options:

- Jackson JSON with appropriate configuration.
- Avro/Protobuf/Schema Registry if schema contracts and ecosystem fit.
- Avoid serializing the same object repeatedly.
- Limit CPU-heavy custom validation on the consumer hot path.
- Practice explicit schema evolution.
- Measure allocations and CPU using JFR/profilers.

Do not choose a binary format merely expecting it to always beat JSON. Payloads, schemas, libraries, compression, and business logic determine actual results.

Ensure deserializers handle schema errors explicitly; infinitely retrying a poison record burns CPU without making the record valid.

## 31. Logging, Tracing, and Metrics Also Consume CPU/Heap/Network

Observability carries real cost:

- Structured logs allocate objects/strings and perform I/O.
- Trace spans allocate metadata, sampling state, and exporter queues.
- Metrics update counters/timers and retain time series.
- Exporters ship telemetry over the network.
- High-cardinality labels increase memory and backend costs.

At high throughput, logging a line for every record can become a bottleneck. Sampling 100% of traces can generate massive span volumes. Metric labels using `eventId`/`offset` can cause cardinality explosions.

Recommendations:

- Log INFO for lifecycle/major events, DEBUG per record only during bounded investigations.
- Use low-cardinality metrics.
- Apply an appropriate sampling policy.
- Bound exporter queues and batches.
- Monitor dropped telemetry and exporter failures.
- Never let an exporter outage block the listener business path indefinitely.

Observability must suffice for diagnostics without consuming the majority of pipeline capacity.

## 32. Calculating CPU Capacity

A simple estimate for CPU cost:

    CPU cores required
      ~= records_per_second * CPU_seconds_per_record

For example, benchmarks show each record uses an average of 2 ms of CPU:

    Input rate = 5,000 records/s
    CPU per record = 0.002 CPU-seconds

    CPU demand = 5,000 * 0.002
               = 10 CPU cores

This is actual CPU time, not elapsed processing duration. If a listener waits 50 ms on a database while using only 2 ms of CPU, do not multiply 50 ms by records/sec to size CPU cores.

Leave headroom for:

- GC and JVM runtime.
- Poll/fetch/commit.
- TLS and compression.
- Logging/metrics/tracing.
- Traffic bursts.
- Node contention and CPU throttling.

If the workload has high p99 CPU cost or variable record sizes, sizing purely on averages is unsafe.

## 33. Calculating Network Capacity

An estimate:

    Network bytes/s
      ~= records/s * average serialized bytes/record

Example:

    8,000 records/s * 12 KB
      = 96,000 KB/s
      ~= 96 MB/s (decimal)

Then adjust for compression ratio, protocol overhead, replication, consumer groups, and traffic direction.

Distinguish between:

- Producer client egress.
- Broker ingress.
- Inter-broker replication.
- Broker egress to consumers.
- Consumer client ingress.
- Other telemetry/network traffic.

If a topic has three consumer groups, brokers may need to serve data to all three groups. Network egress does not equal producer ingress alone.

## 34. Calculating Heap Capacity

Heap sizing is harder than CPU/network because it depends on concurrently live objects.

An approximate model:

    Live heap
      ~= in-flight records * average retained object size
         + application cache
         + framework/client objects
         + queue contents

Example:

    4 consumer threads
    max.poll.records = 200 per consumer
    in-flight record count upper estimate = 800
    retained object graph = 80 KB/record

    Record objects ~= 64 MB

This covers only estimated record graphs, excluding transient deserialization allocations, producer buffers, caches, thread stacks, native memory, and other objects. Listeners may retain extra references that enlarge the live set.

For sizing:

1. Measure object graph size with a profiler/heap analysis.
2. Measure peak in-flight records.
3. Measure allocation rate and GC.
4. Inspect queue/cache retention.
5. Leave headroom for bursts and native memory.
6. Test with valid p99/max payloads.

Never take `max.poll.records * average payload bytes` and treat that as required `-Xmx`.

## 35. Balancing CPU, Heap, and Network

Optimizing one resource can increase pressure on another:

| Change | Potential Benefit | Cost/Risk |
|---|---|---|
| Stronger compression | Reduces network bytes | Increases CPU |
| Larger batches | Reduces request overhead | Increases heap and latency |
| Higher concurrency | Increases parallelism | Increases threads, heap, connections |
| Higher `max.poll.records` | Reduces poll overhead | Increases in-flight memory and poll work |
| Larger producer buffer | Sustains longer bursts | Increases memory before backpressure |
| Higher tracing sample rate | More diagnostic data | Increases CPU/heap/network/storage |
| More replicas | Increases consumer capacity when partitions allow | Increases broker connections and downstream load |
| Higher `-Xmx` | Adds heap headroom | May enlarge GC working set and hit container limits |

Every change should carry a clear hypothesis: which bottleneck decreases, which resources may rise, and which metrics confirm the outcome.

## 36. Consumer Group Capacity Example

Suppose:

- Topic has 24 partitions.
- 6 pods.
- Each pod has `concurrency=4`, totaling 24 consumers.
- Each consumer processes an average of 250 records/s.
- CPU cost is 1.5 ms/record.
- Average deserialized payload retains 40 KB during processing.

Theoretical capacity:

    Max record rate = 24 * 250
                    = 6,000 records/s

CPU demand:

    6,000 * 0.0015 CPU-seconds
      = 9 CPU cores

In-flight record estimate if each consumer handles a poll of 100 records:

    24 * 100 * 40 KB
      = 96 MB record graph estimate

These numbers exclude skew, GC, batch/queue overhead, broker capacity, network, retries, and downstream systems. If partition skew slows one consumer down, group throughput can fall well below 6,000 records/s.

This is a capacity model to guide load testing, not a production throughput guarantee.

## 37. Backpressure When CPU or Heap Nears Exhaustion

When a listener pulls faster than downstream capacity or the JVM nears memory exhaustion, do not keep polling and pushing work into unbounded queues.

Mechanisms:

- Cap `max.poll.records`.
- Bounded async executor queues.
- Cap in-flight requests.
- Rate limiters at downstream call sites.
- Spring Kafka container pause/resume by watermark.
- Lower concurrency if resource pressure is severe.
- Throttle producer input upstream when feasible.

Container pause must use Spring Kafka's API while honoring poll/heartbeat semantics. Never pause by arbitrarily blocking the consumer thread.

When resuming, enforce downstream limits and monitor backlog draining; do not let all consumers unleash a sudden burst simultaneously.

## 38. Distinguishing CPU Bottlenecks from I/O Waits

Signs of a CPU bottleneck:

- High CPU usage/throttling.
- Threads continuously `RUNNABLE`.
- Processing time rises alongside CPU.
- Profiles show hot serializers, compression, JSON parsing, or business computation.

Signs of an I/O bottleneck:

- Low CPU while threads sit in `WAITING`/`TIMED_WAITING` or socket reads.
- High database/HTTP latency.
- Exhausted connection pools.
- Rising network RTT/packet loss.
- High listener duration alongside low CPU time.

A listener with 500 ms elapsed duration does not mean 500 ms of CPU usage. Use JFR/profilers or thread diagnostics to separate CPU time from wait time.

If I/O is the bottleneck, raising CPU requests may not improve throughput; optimize timeouts, connection pools, downstream capacity, or bounded-concurrency async designs.

## 39. Using Java Flight Recorder to Investigate CPU and Allocation

Java Flight Recorder (JFR) helps inspect:

- Hot methods and CPU samples.
- Allocation samples.
- GC pauses.
- Thread park/block events.
- Socket I/O and file I/O.
- Lock contention.
- Thread lifecycles.

Start a recording via the JVM mechanism suited to your environment:

~~~bash
jcmd <pid> JFR.start name=kafka-capacity settings=profile duration=120s filename=/tmp/kafka-capacity.jfr
~~~

This command is an example for environments with `jcmd` and appropriate attach permissions. In production containers, ensure the file path has sufficient space, permissions, and retention controls. Do not run heavy profiling continuously without evaluating overhead.

JFR helps pinpoint CPU/GC/thread bottlenecks; it does not replace broker metrics, consumer lag, and network diagnostics.

## 40. Heap Dumps and Native Memory Tracking

When suspecting a heap leak, capture a heap dump in a controlled environment:

~~~bash
jcmd <pid> GC.heap_dump /tmp/kafka-heap.hprof
~~~

Heap dumps can contain payloads, event data, and sensitive information in memory. Protect files, restrict access, and delete them per retention policy.

Native Memory Tracking (NMT) helps investigate off-heap memory if the JVM starts with the appropriate flag:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Then run `jcmd <pid> VM.native_memory summary` if supported by the JVM. NMT adds overhead and does not capture every native allocation outside the JVM.

Do not take a heap dump on every slight memory bump. First check GC, heap after GC, RSS, direct buffers, and container memory.

## 41. Network Diagnostics

When suspecting a network bottleneck, distinguish among:

- DNS resolution failures.
- TCP connection refused/reset.
- TLS handshake failures.
- Packet loss/retransmissions.
- Rising RTT.
- Bandwidth saturation.
- Slow broker request processing.
- Network policies/firewalls blocking endpoints.

Environment tools may include `ss`, `netstat`, `tcpdump`, `curl` against appropriate endpoints, or Kubernetes/cloud network telemetry. Available tools depend on container images and operational permissions.

Successful ping does not prove Kafka ports/TLS/advertised listeners work. Check the exact hostname and port the client receives from broker metadata.

Do not capture production packets containing sensitive payloads without proper authorization and policy compliance.

## 42. Kafka Client Metrics to Watch

Kafka producers/consumers expose many client metrics. Names and groups may change across versions; verify actual metrics at runtime.

Useful metric groups:

| Group | Example Metrics | Purpose |
|---|---|---|
| Producer throughput | `outgoing-byte-rate`, `record-send-rate` | Send rate |
| Producer batch | `batch-size-avg`, `records-per-request-avg` | Batching efficiency |
| Producer buffer | `buffer-available-bytes`, `bufferpool-wait-time` | Buffer pressure |
| Producer request | `request-latency-avg/max` | Broker response latency |
| Consumer throughput | `bytes-consumed-rate`, `records-consumed-rate` | Read rate |
| Consumer fetch | `fetch-latency-avg/max`, `fetch-rate` | Fetch performance |
| Consumer lag | `records-lag-max` | Client/partition lag metric |
| Coordinator | `commit-latency-avg/max`, `commit-rate` | Offset commits |
| Connection | connection count/creation metrics if supported by client version | Connection churn |

Kafka client metric names are typically exposed via JMX/Micrometer binders, and exporters may alter hyphens or units. Never copy alert queries from another version without verification.

## 43. JVM and Container Metrics

Monitor at minimum:

- Heap used/committed/max.
- Old generation occupancy.
- Allocation rate.
- GC pause count/time.
- Thread count and deadlock detection.
- Direct buffer pool usage.
- Process RSS.
- Container memory working set/limit.
- CPU usage and throttling.
- Restart/OOMKilled count.

If heap is steady while RSS climbs, inspect direct/native memory, thread stacks, and the allocator. If RSS is steady while heap after GC climbs, inspect retained objects/leaks.

Use aligned timestamps to correlate resource spikes with Kafka lag and processing latency. Otherwise, mismatched scrape intervals can lead to misattribution.

## 44. Layers of a Capacity Dashboard

A dashboard for Spring Kafka workers should include:

**Workload**

- Input records/sec and bytes/sec.
- Processed records/sec.
- Consumer lag and oldest record age.
- Partition distribution/hot partitions.
- Retry/DLT rates.

**Application performance**

- Listener duration p50/p95/p99.
- Serialization/deserialization duration if available.
- Database/HTTP latency.
- In-flight request count.
- Executor queue depth.

**JVM/resources**

- CPU usage/throttling.
- Heap used/after GC.
- Allocation rate.
- GC pause p95/p99.
- Direct memory/RSS.
- Thread count.

**Kafka/network**

- Producer send/fetch rates.
- Request latency/errors.
- Buffer pool waits.
- Bytes in/out.
- Reconnect/disconnect counts.
- Commit latency/failures.
- Rebalance count.

A good dashboard answers: is input rising, is the consumer keeping up, which resource is hitting limits, and is the bottleneck in the application or in brokers/downstream.

## 45. Alerting on Symptoms and SLOs

Do not page solely because CPU exceeded 80% for one minute. High CPU can represent healthy workload scaling if throughput rises proportionally and latency stays within SLOs.

Useful alerts combine signals:

- High CPU/throttling **and** rising listener latency.
- Continuously rising post-GC heap **and** container memory near limit.
- Rising GC pauses **and** degrading poll cadence/lag.
- Rising producer buffer wait **and** rising send errors/latency.
- Network throughput near link capacity **and** rising request latency.
- Consumer lag/oldest age breaching SLO despite spare resource headroom.

Use warning/critical tiers with hold durations, baselines, and proper scopes. A single-pod alert differs from a consumer-group-wide alert.

## 46. Evidence-Based Tuning Order

A tuning workflow:

1. Define SLOs: throughput, freshness, latency, error rate.
2. Measure a baseline under representative load.
3. Identify bottlenecks using CPU, heap/GC, network, and downstream metrics.
4. Change one configuration group at a time.
5. Re-run the exact same workload/payload distribution to compare.
6. Measure throughput, p95/p99, GC, bytes/sec, lag, and error rate.
7. Verify duplicate/rebalance/offset behavior.
8. Keep changes only when gains are measurable and reliability does not degrade.

Do not change concurrency, `max.poll.records`, fetch sizes, `-Xmx`, and producer batch size all at once and lose track of which change caused the outcome.

## 47. Diagnostic Example: High CPU, Rising Lag

Symptoms:

- Pod CPU near limit.
- High CPU throttling.
- Rising listener p95.
- Rising consumer lag.
- Heap and GC relatively stable.

Possibilities:

- CPU-heavy JSON parsing/compression.
- Heavy business computation.
- Increased concurrency with unchanged CPU limits.
- Increased TLS or tracing overhead.

Investigation:

1. Capture a JFR CPU profile.
2. Check which threads consume CPU.
3. Compare processing duration against CPU time.
4. Inspect records/sec and payload sizes.
5. Check CPU throttling.
6. Benchmark serializers/compression.
7. Optimize hot methods or raise CPU capacity in a controlled way.
8. Verify lag drops without overloading downstream.

## 48. Diagnostic Example: Rising Heap and OOMKilled

Symptoms:

- Container memory climbing steadily.
- Post-GC heap rising.
- Frequent GC pauses.
- Pod OOMKilled.
- Consumer lag rising after restarts.

Possibilities:

- Unbounded async queues.
- Listeners caching payloads.
- `max.poll.records` too large relative to payload size.
- In-flight tasks not being released.
- Batch or retry state retaining objects.
- Application memory leak.

Investigation:

1. Compare heap used against RSS.
2. Inspect heap after GC.
3. Capture a heap dump in a safe environment if needed.
4. Analyze dominators/retained objects.
5. Inspect queue depth, cache sizes, and in-flight tasks.
6. Inspect direct buffers and thread counts.
7. Bound queues/batches and fix reference retention.
8. Run a soak test long enough to confirm live set stability.

Only raise `-Xmx` when evidence shows the workload needs more heap and container limits have headroom. Never use `-Xmx` to mask a leak.

## 49. Diagnostic Example: Low CPU Yet Slow Consumer

Symptoms:

- 20% CPU.
- Stable heap.
- High listener duration.
- Rising consumer lag.
- Thread dumps show many threads waiting on sockets/connection pools.

Possibilities:

- Slow database/API.
- Exhausted connection pool.
- High network RTT.
- Rate limiter waiting for permits.
- External locks or future waits.

Investigation:

1. Read thread dumps.
2. Inspect dependency latency and pool saturation.
3. Compare wall-clock duration against CPU time.
4. Check network RTT/retransmissions.
5. Inspect retries/backoff and circuit breakers.
6. Bound timeouts/in-flight concurrency.
7. Increase consumer concurrency only if dependencies have spare capacity.

Low CPU is not a sufficient reason to add replicas; it may further overload downstream systems.

## 50. Diagnostic Example: Producer Buffer Waits and Send Timeouts

Symptoms:

- Rising `bufferpool-wait-time`.
- Dropping `buffer-available-bytes`.
- `send()` blocking near `max.block.ms`.
- Rising delivery timeouts/errors.
- Broker/network throughput failing to keep up with input.

Possibilities:

- Brokers unavailable or high request latency.
- Producer send rate exceeds network/broker capacity.
- Slow compression/serialization.
- Ineffective batch/partition distribution.
- Broker throttling/quotas.

Remediation:

1. Confirm broker and network health.
2. Inspect request latency and outgoing bytes.
3. Review `buffer.memory`, batch size, and linger.
4. Inspect partition leader distribution.
5. Check compression CPU cost.
6. Throttle input or apply outbox/backpressure when needed.
7. Do not raise `buffer.memory` indefinitely.
8. Handle send future failures explicitly and preserve stable event IDs.

## 51. Downstream Capacity Can Constrain Before CPU/Network

A consumer with spare CPU and healthy networking can still be bounded by databases/APIs.

Example:

    Kafka input = 4,000 records/s
    Listener CPU capacity = 8,000 records/s
    Network capacity = 10,000 records/s
    Database safe capacity = 1,500 transactions/s

If each record opens one DB transaction, sustainable throughput is only around 1,500 records/s or lower, depending on overhead and transaction batching.

Increasing concurrency increases concurrent requests to the database and can worsen latency. Inspect pools, lock contention, DB CPU, connection counts, and transaction latency.

End-to-end capacity is bounded by the weakest component in the pipeline, not by spare resources on the consumer pod.

## 52. Autoscaling Must Account for Partitions and Resource Limits

Lag-based autoscaling can help when load grows, yet requires guardrails:

- Do not scale consumer threads past useful partition counts without reason.
- Do not scale past downstream capacity.
- Account for startup/assignment time and rebalance cost.
- Ensure CPU/memory requests allow the scheduler to allocate resources.
- Configure cooldowns to prevent flapping scale-up/scale-down cycles.
- Account for network/broker connection budgets.
- Cap maximum replicas via operational policy.

A CPU-based HPA may fail to scale when an I/O-bound consumer has low CPU despite high lag. A lag-based scaler may over-scale when downstream is already overloaded.

Combine multiple signals: lag, oldest age, processing rate, CPU, memory, downstream saturation, and partition count.

## 53. Load Testing and Soak Testing

Load tests find capacity at a target load level; soak tests uncover issues that appear only over long durations, such as memory leaks, cache growth, or connection leaks.

A test scenario:

1. Use payload sizes near production p50/p95/p99.
2. Ramp input rates step by step.
3. Measure CPU, throttling, heap, allocation, and GC.
4. Measure producer/consumer bytes/sec and network RTT.
5. Monitor listener latency, lag, and commit rate.
6. Scale concurrency in a controlled way.
7. Simulate slow/disconnected brokers.
8. Simulate downstream latency.
9. Run soak tests long enough for live heap to stabilize.
10. Confirm pods do not OOM/restart and offsets remain accurate.
11. Record saturation points and headroom.
12. Repeat with different compression/batch/fetch configurations.

Do not use overly small or overly compressible synthetic payloads to represent production when real payloads differ substantially.

## 54. Common Tuning Mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| Watching only pod-wide CPU | Misses a saturated single thread/core | Inspect thread profiles and throttling |
| Raising concurrency indefinitely | Increases threads, connections, and rebalances | Bound by partitions/downstream |
| Setting `-Xmx` equal to container memory limit | Off-heap OOM/OOMKilled | Reserve headroom for native/stack/direct memory |
| Increasing heap to cure a leak | Only delays OOM | Find retained objects |
| Unbounded async queues | Uncontrolled heap growth | Bounded queues/backpressure |
| Raising `max.poll.records` without measuring heap | Peak in-flight memory spikes | Benchmark payload distribution |
| Maxing out fetch limits | Buffer and memory pressure | Tune by record size/partitions |
| Assuming highest compression is always best | CPU can become the bottleneck | Benchmark codecs |
| Enlarging producer buffer for broker outages | Only delays buffer exhaustion | Fix capacity/network, apply backpressure |
| Assuming low CPU means spare consumer capacity | May be blocked on I/O | Read thread states/dependency metrics |
| Assuming low ping means healthy Kafka network | Misses TLS/broker/request delays | Measure Kafka client request metrics |
| Scaling unboundedly on lag | Overloads brokers/DB | Combine partition and dependency capacity |
| Using averages only | Hides tail latency and hot partitions | Track p95/p99 and per-partition metrics |
| Logging every record at INFO | CPU/I/O/storage bottleneck | Appropriate sampling/log levels |
| 100% tracing without costing it | Exporter/heap/network overload | Sampling and bounded exporters |

## 55. Production Capacity Checklist

Before signing off on a Spring Kafka service's capacity, verify:

- Peak input records/sec and bytes/sec?
- Record size p50/p95/p99/max?
- Partition count and whether key distribution is balanced?
- Are consumer replicas × concurrency aligned?
- Actual CPU time per record?
- CPU requests/limits and throttling?
- Post-GC heap, allocation rate, and GC pauses?
- Container RSS headroom outside the heap?
- Direct memory, thread count, and stack memory?
- Do `max.poll.records`/fetch limits fit payloads?
- Have producer buffer/batch/linger/compression been benchmarked?
- Network throughput, RTT, packet loss, and broker request latency?
- Downstream capacity, pools, and concurrency limits?
- Are retries, DLT, and async queues bounded?
- Do consumer lag/oldest age meet SLOs?
- Has observability overhead been accounted for?
- Have load tests and soak tests run with production-like payloads?
- Are runbooks ready for CPU, heap, or network saturation?
- Is autoscaling bounded by partitions and downstream?
- After a broker outage, is backlog draining fast and safe enough?

## 56. Conclusion

**CPU, heap, and network are the three resource boundaries that govern Spring Kafka throughput and stability.** CPU governs serialization, compression, deserialization, and business logic; heap governs object retention, batches, queues, and GC; network governs producer sends, consumer fetches, replication, coordinator requests, and cross-region latency.

You cannot tune properly simply by raising concurrency, heap, or buffers. Measure workloads in both record rate and byte rate, separate CPU time from I/O wait, inspect post-GC heap and RSS, and monitor Kafka client metrics alongside broker/network health. Capacity must be sized around the end-to-end bottleneck, including databases/APIs and observability overhead.

A sound production configuration preserves headroom for bursts, bounds in-flight work, applies backpressure when needed, and is verified via load and soak tests. Whenever CPU, heap, or network hits a limit, identify which resource is saturated and adjust at the right layer. **The goal is sustainable throughput with latency and data reliability inside SLOs, not the highest possible resource utilization.**
