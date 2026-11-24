# Transaction Timeout

In Kafka, **transaction timeout** is the limit enforced by the transaction coordinator so a transaction cannot remain open forever when a producer stops making progress. If a transaction stays active too long without receiving appropriate state updates, the broker can proactively **abort** it. This is especially important for Spring Kafka applications running consume–transform–produce flows: the listener consumes a record, writes outputs, and enlists the source offset into the same Kafka transaction.

Timeouts cut both ways. Too low a limit causes valid transactions to abort when listeners run slowly, brokers lag, or networks blip. Too high a limit leaves abandoned transactions open longer, blocking `read_committed` consumers from reading stable data, slowing recovery, and masking application bugs.

Understanding transaction timeouts requires distinguishing **producer transaction timeout**, **broker-permitted maximum**, **network/producer call timeouts**, **Spring transaction timeout**, and consumer **`max.poll.interval.ms`**. These limits do not substitute for one another.

## 1. What Is a Kafka Transaction Used For?

Kafka transactions group multiple Kafka writes and, in the right model, **commit consumer offsets** into a single Kafka-level atomic unit.

Suppose a service receives `OrderPlaced` from topic `orders` and emits `OrderValidated` to topic `validated-orders`:

~~~text
orders (input)
      |
      v
@KafkaListener
      |
      +-- Process OrderPlaced
      |
      +-- KafkaTemplate.send("validated-orders", result)
      |
      +-- Container enlists consumed offsets into transaction
      |
      v
Commit Kafka transaction
      |
      +-- Success: output visible to read_committed,
      |            input offset recorded
      |
      +-- Abort: transactional output excluded from data
                 visible to read_committed,
                 input offset not committed with transaction
~~~

If the transaction aborts, the consumer can re-read the source record from the previous committed offset. Thus, input consumption progress and Kafka outputs stay synchronized at the transaction boundary.

**Limitation:** Kafka transactions do not automatically include databases, REST APIs, emails, or external payment systems in one atomic unit. Those side effects require idempotency, outbox/inbox, or dedicated coordination workflows.

## 2. What Is transaction.timeout.ms?

Kafka producers have the **transaction.timeout.ms** property. It specifies the maximum time the transaction coordinator waits for transaction status updates from a producer before it may proactively abort an open transaction.

Example:

~~~properties
transaction.timeout.ms=120000
~~~

`120000` ms equals 2 minutes. This is a **Kafka producer** parameter used by the broker's transaction coordinator; it is not an HTTP client or `@KafkaListener` timeout.

By default in many Apache Kafka versions, `transaction.timeout.ms` is **60000 ms (60 seconds)**. In operations, check your Kafka client version and effective configuration because applications or platforms may override defaults.

The transaction coordinator tracks transaction state, including producer identity, epoch, transaction state, and participating partitions. If a transaction does not complete within the coordinator's allowed window, the broker can abort it to release state and unblock stable reads.

Do not think of `transaction.timeout.ms` as an exact stopwatch starting the moment a listener begins and ending when business code finishes. Kafka manages transactions via protocol state updates from the producer; wall-clock time measured inside an app also includes polling, listener logic, producer requests, commits, and external delays.

## 3. How Does the Broker Cap Transaction Timeouts?

Kafka brokers have **transaction.max.timeout.ms**: the maximum timeout value a broker accepts from a transactional producer.

Example:

~~~properties
# Broker configuration, illustrative only
transaction.max.timeout.ms=900000
~~~

In many Apache Kafka distributions, the default limit is **900000 ms (15 minutes)**. Real cluster values may differ, especially on managed Kafka services.

If a producer requests a `transaction.timeout.ms` exceeding the broker's `transaction.max.timeout.ms`, **transactional producer initialization** can fail rather than the broker silently allowing longer transactions. Fix the producer configuration or adjust the cluster limit through governance processes.

Do not raise the broker limit just because one listener is currently slow. First inspect processing time, transaction scope, dependencies, and ways to break up work.

### 3.1. Comparing two settings

| Configuration | Location | Purpose |
|---|---|---|
| `transaction.timeout.ms` | Kafka producer | Sets the transaction timeout requested by the producer |
| `transaction.max.timeout.ms` | Kafka broker | Upper bound permitted by the broker |
| `transactional.id` | Kafka producer | Identifies a transactional producer for coordinator epoch and fencing |
| `isolation.level=read_committed` | Kafka consumer | Reads only committed transactional data and eligible non-transactional data |

`transactional.id` is not a timeout, yet it is central to transaction state and producer fencing. Never share the same `transactional.id` concurrently across independent producers.

## 4. Transaction Lifecycle and Timeout Points

A transactional producer steps through:

~~~text
initTransactions()
      |
      v
beginTransaction()
      |
      +-- send() records to output partitions
      |
      +-- sendOffsetsToTransaction() if processing consumer input
      |
      v
commitTransaction()
      |
      +-- Commit succeeds
      |
      +-- Timeout / broker abort / fencing / other error
                |
                v
        Handle transaction state,
        rollback/recovery per framework
~~~

If a producer begins a transaction and fails to commit or abort within the coordinator's window, the broker can abort the transaction. This can happen even while the Java process stays alive—for instance, if a thread blocks on a database lock or an untimed HTTP request.

### 4.1. A transactional producer is not a database session

Kafka does not automatically roll back database changes when a Kafka transaction aborts. For example, a listener updates an `orders` table and then the Kafka transaction times out:

~~~text
Database update: COMMITTED
Kafka transaction: ABORTED
Input offset in Kafka transaction: NOT COMMITTED
      |
      v
Input record is re-read
      |
      v
Database update may run again
~~~

This is why Kafka transactions do not replace **idempotent consumer** or **transactional outbox** designs when non-Kafka resources are involved.

## 5. Configuring Transaction Timeouts in Spring Boot

A Spring Boot app can enable Kafka transactions with a transaction ID prefix and pass producer properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    producer:
      transaction-id-prefix: orders-tx-
      properties:
        transaction.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Meaning:

- **transaction-id-prefix** tells the producer factory to create transactional producers with distinct `transactional.id` values.
- **transaction.timeout.ms** requests a 2-minute transaction timeout for the Kafka producer.
- **enable-auto-commit=false** lets the listener container manage offsets rather than the Kafka consumer auto-committing periodically.
- **read_committed** is for consumers needing to hide uncommitted or aborted transactional outputs.

Prefixes must be **unique across concurrently running application instances** when using Spring Kafka's transactional producer pooling. For example, include an instance ID, pod name, or stable deployment identifier per platform policy. If two instances accidentally share a `transactional.id`, they can fence each other.

Spring Boot properties and automatic creation of `KafkaTransactionManager` may vary across versions. Verify your version, actual producer factory, and the transaction manager wired to the listener container.

### 5.1. Configuring in Java

When creating `DefaultKafkaProducerFactory` manually:

~~~java
@Bean
ProducerFactory<String, String> producerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> config =
        new HashMap<>(kafkaProperties.buildProducerProperties());

    config.put(
        ProducerConfig.TRANSACTION_TIMEOUT_CONFIG,
        120_000
    );

    DefaultKafkaProducerFactory<String, String> factory =
        new DefaultKafkaProducerFactory<>(config);

    factory.setTransactionIdPrefix("orders-service-instance-1-tx-");
    return factory;
}
~~~

This snippet illustrates setting the producer property; `buildProducerProperties` signatures and SSL bundle parameters may change across Spring Boot versions. If Boot already auto-configures `ProducerFactory` and `KafkaTransactionManager`, redefining those beans manually is unnecessary.

## 6. Transactions in KafkaTemplate

With a producer factory configured with a transaction ID prefix, `KafkaTemplate` can execute a group of sends in a transaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishTwoEvents(String orderId) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                "orders-validated",
                orderId,
                "VALIDATED"
            );
            operations.send(
                "orders-audit",
                orderId,
                "VALIDATED"
            );
            return null;
        });
    }
}
~~~

In this example, both sends join a Kafka transaction managed by `KafkaTemplate`. If the transaction commits, `read_committed` consumers see the committed outputs. If it aborts, that transaction's outputs remain hidden from `read_committed` consumers.

An issue arises if code inside `executeInTransaction` runs non-Kafka work for too long, such as calling an HTTP API with no timeout. The transaction stays open while awaiting HTTP and risks coordinator abort.

Therefore, **keep transaction scopes as small as possible**. Perform pure CPU prep or slow queries before opening the transaction whenever they do not need to sit inside the transaction boundary. When external side effects must coordinate, design an outbox/inbox or suitable recovery protocol.

## 7. Container Transactions in Spring Kafka

When a listener container has a Kafka transaction manager configured, the container manages a Kafka transaction around record or batch processing. It can enlist consumed offsets into the same transaction as listener outputs.

Conceptual setup:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> transactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

This snippet is illustrative; the transaction manager's generic types should match the `ProducerFactory` used for outputs. Check setter APIs and Boot auto-wiring against your actual Spring Kafka version.

With a transactional container:

1. Container polls records.
2. Container opens a Kafka transaction for the processing unit.
3. Listener processes and emits Kafka outputs via a compatible template.
4. Container enlists processed offsets into the transaction.
5. Producer commits the transaction.
6. On commit, outputs and offsets are recorded together; on abort, transactional outputs and offsets do not commit.

Timeouts can occur if the listener or commit operation stalls too long. Tuning `transaction.timeout.ms` is only part of the picture; measure listener duration, producer requests, and transaction commits together.

## 8. Transaction Timeout Differs from Spring @Transactional Timeout

In Spring applications, you may encounter multiple "transaction timeout" concepts:

~~~java
@Transactional(timeout = 30)
public void updateOrder(...) {
    // ...
}
~~~

The **timeout=30** attribute belongs to Spring's transaction abstraction; actual behavior depends on the **PlatformTransactionManager** and its managed resource. With database transaction managers, the timeout can affect resource operations per implementation.

It is **not automatically equivalent** to the Kafka producer property `transaction.timeout.ms`. Never assume adding `@Transactional(timeout=30)` causes the broker to abort a Kafka transaction at exactly 30 seconds.

Likewise, Kafka `transaction.timeout.ms` does not bound individual SQL statements or HTTP calls. If an HTTP client hangs, the broker may abort the transaction while the thread still sits blocked in HTTP.

### 8.1. Comparing easily confused timeouts

| Timeout | Component | What it bounds |
|---|---|---|
| `transaction.timeout.ms` | Kafka transactional producer/coordinator | Transaction coordinator may abort overdue open transactions |
| `transaction.max.timeout.ms` | Kafka broker | Maximum transaction timeout accepted by broker |
| `@Transactional(timeout=...)` | Spring transaction abstraction | Timeout enforced by the respective transaction manager |
| `max.poll.interval.ms` | Kafka consumer | Maximum interval between valid polls before group considers consumer stalled |
| `delivery.timeout.ms` | Kafka producer | Maximum time to deliver a producer record across retries/delivery |
| `request.timeout.ms` | Kafka client | Time waiting for a single request response |
| `max.block.ms` | Kafka producer | Blocking limit in certain producer APIs awaiting metadata or buffers |
| HTTP connect/read timeout | HTTP client | Bounds establishing connections and awaiting dependency responses |
| Database statement/lock timeout | Database/driver | Bounds SQL execution and lock waits per DB engine |

No single timeout covers every layer. Production designs must align dependency timeouts and processing budgets with intended open-transaction durations.

## 9. Transaction Timeout Example in Consume–Transform–Produce

Suppose:

- `transaction.timeout.ms`: 60 seconds.
- Listener reads `OrderPlaced`.
- Listener calls a pricing service taking 75 seconds.
- Listener then sends `OrderPriced` and the container tries to commit the Kafka transaction.

High-level sequence:

~~~text
t=0s   Container starts Kafka transaction
       |
t=1s   Listener starts calling pricing service
       |
t=60s  Transaction coordinator may determine
       |      transaction exceeded deadline
       |      and proactively abort
       |
t=76s  Listener completes, sends output/commit
       |
       v
       Transaction no longer in expected
       committable state
       |
       v
       Exception -> rollback/error handling
       |
       v
       Input offset not committed
       with Kafka transaction
~~~

The `t=60` mark is a conceptual illustration, not a guarantee that the broker aborts at millisecond 60,000 from listener entry. The transaction coordinator enforces timeouts according to broker protocol and scheduling.

Once the transaction has aborted, Kafka outputs from that transaction stay hidden from `read_committed` consumers. The input record can be redelivered. If the pricing service already produced a side effect, it may be invoked again.

The best fix is usually shortening transaction open time, adding dependency timeouts, and designing idempotency—not immediately raising `transaction.timeout.ms` to a huge number.

## 10. Which Exceptions Can Signal a Transaction Timeout?

There is no single exception for every transaction expiration case. Depending on timing, Kafka client version, and producer state, applications may see `KafkaException`, `TimeoutException`, `InvalidTxnStateException`, producer fencing, or Spring transaction framework exceptions.

Categories to distinguish:

### 10.1. Producer request timeout

Producers can time out while sending records, fetching metadata, adding partitions to a transaction, or committing. A request timeout alone does not prove the broker aborted the transaction. Inspect producer state and root exceptions.

### 10.2. Coordinator already aborted the transaction

If the transaction coordinator proactively aborted due to timeout, the producer can no longer commit that transaction. Errors typically surface when the producer keeps sending/committing or when the framework finalizes the transaction.

### 10.3. Producer fencing

When another producer uses the same `transactional.id` with a new epoch, the older producer can be **fenced**. `ProducerFencedException` or producer-epoch errors mean the current instance no longer owns that transactional identity.

This is not a simple timeout you can retry on the same fenced producer. Close/discard the old producer and verify `transactional.id` uniqueness, instance lifecycles, and restarts.

### 10.4. Spring transaction completion failure

The listener body may finish cleanly while errors appear only during the container's Kafka transaction commit phase. Stack traces then point to Spring Kafka's listener container and transaction manager rather than the earlier slow business code.

Investigate with a timeline covering transaction start, listener latency, Kafka sends, commit, and root-cause exceptions. Avoid blindly increasing listener retries based solely on the outer wrapper exception.

## 11. Timeouts, Retries, and Producer State

Crucial point: after a transaction error, not every producer state can be safely reused.

Depending on error type, the Kafka client may require:

- Aborting the active transaction if still valid and abortable.
- Closing the transactional producer due to fatal or fencing errors.
- Initializing a new producer with an appropriate transaction identity/epoch.
- Letting Spring Kafka's transaction manager/container manage rollback and redelivery.

Never write a catch-all loop like:

~~~java
while (true) {
    try {
        producer.commitTransaction();
        break;
    } catch (Exception ex) {
        // Wrong: retry every exception infinitely on old producer
    }
}
~~~

This code can pin a producer in a permanently broken state, delay recovery, and obscure root causes. A transaction already aborted by the broker or a fenced producer cannot be "rescued" by retrying commits endlessly.

Classify errors per the Kafka client contract, record transaction state, and let the container/transaction manager manage lifecycles per version.

## 12. Impact on read_committed Consumers and LSO

With **isolation.level=read_committed**, consumers must not observe outputs of uncommitted or aborted transactions. Kafka uses the **Last Stable Offset (LSO)** to cap the readable portion of a log under this isolation level.

If a partition holds an open transaction, subsequent records behind that transaction's boundary remain invisible to `read_committed` consumers even as the log end offset climbs.

~~~text
Partition log:
offset 100  committed data
offset 101  transaction T begins (open)
offset 102  record of T
offset 103  subsequent record
offset 104  subsequent record

LSO ----> read_committed readable boundary
LEO ----------------------------> end of log
~~~

This diagram shows conceptual impact; Kafka stores transaction markers and enforces LSO at the protocol level rather than necessarily storing a visible business record called "begin".

If transaction T stalls for a long time, `read_committed` consumers can stop advancing on that partition. Once T commits or aborts, LSO advances and consumers resume reading stabilized data.

An overly large transaction timeout lets an abandoned transaction hold back LSO longer, adding latency downstream. Too small a timeout increases unnecessary aborts. Tuning must therefore balance **producer reliability** and **`read_committed` consumption latency**.

## 13. Misleading Lag During Long Open Transactions

A lag dashboard often computes:

~~~text
consumer_group_lag = log_end_offset - committed_offset
~~~

For `read_committed` consumers, data near the log end may be unreadable because LSO has not advanced. Rising lag in that case does not necessarily mean the consumer is slow.

Example:

- Producers continuously write records.
- One transaction stays open on a partition for a long time.
- LEO grows while LSO is pinned by the open transaction.
- `read_committed` consumers cannot read records past LSO.
- Lag computed against LEO climbs.

Simply raising consumer concurrency will not solve this: the bottleneck is an unresolved transaction, not processing thread count.

When investigating, examine producer transaction metrics, open-transaction durations, broker coordinator health, consumer isolation levels, and exact exporter lag definitions.

## 14. Transaction Timeout vs max.poll.interval.ms

These two settings are often confused:

**transaction.timeout.ms** belongs to the Kafka producer/coordinator. It bounds how long a transaction stays open per broker rules.

**max.poll.interval.ms** belongs to the Kafka consumer. It bounds how long a consumer may go without calling `poll()` again before the group considers it dead.

A slow listener can violate **both**, with distinct consequences:

~~~text
Listener processes long
      |
      +--> transaction timeout
      |         |
      |         v
      |      Broker aborts transaction,
      |      transactional output and offsets
      |      do not commit as expected
      |
      +--> max.poll.interval.ms exceeded
                |
                v
             Consumer loses group progress,
             rebalance, partitions may be revoked
~~~

If the consumer already lost partition ownership, sending offsets into a transaction or committing under an old generation triggers other errors. Measure each timeout axis separately to find which trips first.

### 14.1. Poll and transaction time budget

Suppose a listener executes these steps:

| Step | p99 duration |
|---|---:|
| Deserialization/mapping | 0.2 seconds |
| Database read | 1.5 seconds |
| External API | 8 seconds |
| Business compute | 0.5 seconds |
| Kafka sends and transactional flush | 2 seconds |
| Commit transaction | 1 second |
| GC/network headroom | 3 seconds |
| **Approximate total** | **16.2 seconds** |

With a 10-second transaction timeout, the budget fails p99. Still, do not blindly pick 60 seconds just because the sum is 16.2 seconds: also weigh batch sizes, retry paths, SLOs, and coordinator behavior.

If a listener processes an entire poll batch, multiply per-record time by realistic record counts and concurrency to estimate worst cases. Often the right fix is shrinking work inside the transaction rather than inflating timeouts.

## 15. How to Choose Sensible Timeouts

Design approach:

1. Define the **transaction boundary**: before which operation it opens and when it closes.
2. Measure p50/p95/p99 and worst-case durations of listener logic plus Kafka sends/commits.
3. Set timeouts on databases, HTTP clients, and every dependency.
4. Sum the multi-step time that can hold a transaction open.
5. Pick `transaction.timeout.ms` with reasonable headroom over real transaction duration, yet short enough for brokers to abort abandoned transactions promptly.
6. Verify the value does not exceed broker `transaction.max.timeout.ms`.
7. Evaluate `max.poll.interval.ms` and batch sizes independently.
8. Run fault-injection tests to observe rollback/recovery on timeout.

### 15.1. Choosing between 30, 60, or 180 seconds

Suppose most transactions finish in 2 seconds and p99 is around 6 seconds, yet an external endpoint occasionally hangs for 90 seconds.

Raising the timeout to 180 seconds to "accommodate" that endpoint is not mandatory. Instead, you can:

- Set a bounded HTTP timeout, e.g., aligned with a 5–10 second SLO.
- Move slow processing into a separate workflow.
- Open the Kafka transaction after the long prep step if semantics permit.
- Use an outbox when coordinating database and Kafka writes.
- Retry transient errors outside an open transaction.

Raise transaction timeouts only when valid transactions genuinely require longer durations and downstream tolerates open transactions holding back LSO.

## 16. Why Avoid Keeping Transactions Open Across Long External Calls?

Suppose a listener opens a Kafka transaction and calls a Payment API that responds after 70 seconds or hangs.

During that window:

- The Kafka transaction stays open even though logic is incomplete.
- The broker may abort due to transaction timeout.
- The consumer thread stays blocked on the HTTP call.
- If the payment executed yet the response was lost, API state is uncertain.
- The input record may redeliver and call payment again.

This is a **transaction scope + side effect** issue, not just a timeout property.

Alternative design:

- Use a stable idempotency key on the Payment API.
- Use an outbox to persist business state and event intent in one database transaction.
- Use a dedicated worker to publish outbox rows to Kafka.
- Keep external waits outside Kafka transactions where business consistency allows.
- Track uncertain states and reconcile instead of retrying payment commands as fresh charges.

Kafka transactions cannot roll back a payment that already succeeded on an external system.

## 17. Behavior on Transaction Timeout and Rollback

With transactional listener containers, exceptions in the listener or during commit can cause transactions to abort/roll back. After rollback, the framework must decide how to redeliver input records.

Spring Kafka provides **DefaultAfterRollbackProcessor** for post-rollback handling. It can seek affected partitions/records per policy and support bounded recovery attempts.

Conceptual example:

~~~text
Consumer receives record at offset 220
       |
       v
Kafka transaction opens
       |
       v
Listener sends transactional output
       |
       v
Transaction timeout/commit fails
       |
       v
Transaction aborts or fails to commit
       |
       v
Offset 221 not committed with transaction
       |
       v
Record 220 may be redelivered
~~~

When recovery sends failing records to a DLT, verify whether DLT publishing and recovered offset commits share an appropriate recovery transaction. APIs such as `commitRecovered` or `AfterRollbackProcessor`'s `kafkaTemplate` have configuration- and version-dependent semantics.

Do not attach a non-transactional `DefaultErrorHandler` assuming it is the sole controller for transactional container rollbacks.

## 18. Retries Cannot Rescue an Already Timed-Out Transaction

Two distinct kinds of retries exist:

1. **Retrying an operation inside a still-valid transaction**: the Kafka client can retry producer requests per protocol and delivery timeout.
2. **Retrying entire record processing after transaction abort**: Spring Kafka's container/rollback processor can redeliver the input for a fresh attempt in a new transaction.

Once a Kafka transaction has aborted, you cannot simply call `commitTransaction` again on the old transaction to turn it into a commit. Let the framework close/recover producer state per contract and rerun work in a new transaction when safe.

Important: retrying the entire listener can repeat database/HTTP side effects that succeeded earlier. Therefore, transaction timeouts make event IDs and idempotency even more critical.

## 19. Producer Fencing and Transaction ID Uniqueness

Kafka uses **transactional.id** and producer epochs to guard against zombie producers—for example, an old producer thinking it still owns a transaction after a new instance took over.

If two service instances accidentally share a `transactional.id`:

~~~text
Instance A: transactional.id=orders-tx-0
        |
        v
Transaction open

Instance B: transactional.id=orders-tx-0
        |
        v
Initialize new producer with same identity
        |
        v
Old producer may be fenced
~~~

When `ProducerFencedException` appears, investigate:

- Is `transaction-id-prefix` unique across instances?
- Did a rolling update run two pods sharing the same prefix concurrently?
- Is a producer pool reusing identities improperly?
- Was an old instance still alive when a new instance started?

Fencing differs from transaction timeouts, though both can surface around restarts or slow commits. Never raise timeouts to solve `transactional.id` collisions.

## 20. Transaction Timeout and read_uncommitted

Consumers using `isolation.level=read_uncommitted` can see records belonging to aborted transactions, because they do not filter by commit markers like `read_committed` does.

Therefore, if Kafka outputs rely on transactions to keep uncommitted work hidden downstream, downstream consumers need **read_committed**. Leaving them on `read_uncommitted` lets them read records from transactions that eventually abort and trigger unwanted side effects.

A system using Kafka EOS on producers without `read_committed` downstream fails to deliver expected semantics.

Check consumer properties across **every downstream group needing this guarantee**, not just the first producer.

## 21. Transaction Timeouts in Unstable Clusters

Broker failovers, coordinator migrations, and network partitions can slow down or fail transaction requests. When transactions run close to their timeout, such delays raise abort rates.

To diagnose:

- Inspect coordinator errors, transaction markers, and broker logs.
- Check leader/ISR health on output partitions and the internal transaction state topic.
- Measure producer request latency, retry rates, and delivery timeouts.
- Correlate timestamps with broker restarts or network disconnects.
- Check producer transaction timeouts and broker maximums.
- Compare abort counts before and after infrastructure changes.

Kafka uses internal topics for transaction state and consumer offsets; cluster operations must maintain their replication, ISR, and availability. Weak coordinator infrastructure can affect many transactional producers even when business listeners run fast.

Never rely solely on raising `transaction.timeout.ms` to paper over prolonged broker/controller/coordinator outages.

## 22. Monitoring: Which Metrics to Track?

A solid dashboard for transactional producers goes beyond send rates and consumer lag. It must show whether transactions complete within expected windows.

| Signal | Operational meaning |
|---|---|
| Transaction duration p50/p95/p99 | How long transactions actually stay open |
| Transaction commit rate | Transactions completing successfully |
| Transaction abort rate | Transactions aborted |
| Transaction start/commit error rate | Failing broker/coordinator or producers |
| Producer fencing/errors | ID collisions, epoch, or lifecycle issues |
| Producer request latency/retries | Whether Kafka I/O stretches transactions |
| Listener processing latency | Whether business logic or dependencies run slow |
| `max.poll.interval` and rebalances | Whether consumers sustain poll cadence |
| `read_committed` consumer lag | Whether downstream is blocked by LSO |
| LSO/HW/LEO if exposed by infra | Gap caused by open transactions vs replication |
| External dependency timeout rate | Whether HTTP/DB calls extend transactions |

Exact metric names and export paths via Micrometer, Kafka client JMX, or exporters vary by version. Some metrics require application-side measurement, such as elapsed time from begin to commit/abort.

Alert not only on realized transaction timeouts, but also on transaction durations trending toward limits, rising abort rates, climbing `read_committed` lag, and unexpected producer fencing.

## 23. Logs and Tracing for Transaction Timeouts

Useful logs support reconstructing a timeline:

- Application instance, `transactional.id`, or matching prefix.
- Consumer group, source topic, partition, and offset.
- Listener start/finish timestamps.
- Transaction begin and commit/abort timestamps if available.
- Database/HTTP dependency durations.
- Kafka send timestamps and producer future results.
- Root exception class, nested causes, and transaction manager exceptions.
- Configured transaction timeout and broker maximum if accessible.
- Stable correlation ID / event ID.

Do not log full sensitive payloads or credentials. In tracing, separate Kafka transaction spans from HTTP/database spans to identify which dependency consumes open-transaction time.

A commit exception at the end of a listener may originate from a stall dozens of seconds earlier. Timelines pinpoint root causes much better than the final stack trace alone.

## 24. Testing Transaction Timeouts

Tests must cover both valid transactions and timed-out/aborted transactions.

### 24.1. Short successful transaction

Produce an input record, let the listener send transactional output, and commit. Verify:

- Output becomes visible to `read_committed` consumers.
- Source offset commits with the container transaction.
- No duplicate side effects occur under normal conditions.

### 24.2. Slow listener exceeding transaction timeout

In a controlled test environment, configure a short timeout and insert a processing step exceeding the threshold. Verify the transaction does not commit, downstream `read_committed` sees no aborted output, and input redelivers per rollback policy.

Avoid using excessively long sleeps as a production test; real timings are also shaped by coordinator cycles and other timeouts.

### 24.3. Transaction ID collision

Start two transactional producers with the same identity in a test environment. Observe fencing and confirm the app does not infinitely retry on the fenced producer.

### 24.4. Broker coordinator unavailable

Simulate connection/coordinator failures via test harnesses. Verify error classification, transaction abort/recovery, and metric alerts.

### 24.5. External side effect succeeds then Kafka aborts

This is the single most critical test for services with databases/APIs:

1. Execute the side effect with an event ID.
2. Force the Kafka transaction to abort.
3. Redeliver the input.
4. Verify the side effect does not happen twice.

### 24.6. read_committed held back by open transaction

Open a transaction in a test cluster and write subsequent records to the same partition. Observe the difference between `read_committed` and `read_uncommitted` while the transaction remains open; verify consumers read stabilized data once committed/aborted.

## 25. Runbook for Transaction Timeout Errors

### Step 1: Identify which layer timed out

Inspect the root exception and surrounding logs. Confirm whether it is a Kafka producer/coordinator transaction timeout, request timeout, `@Transactional` database timeout, or `max.poll.interval.ms`.

### Step 2: Identify producer and transaction scope

Locate `transactional.id`, application instance, listener/container factory, and producer factory. Trace where the transaction begins, where it ends, and whether long dependency calls sit inside.

### Step 3: Check configurations

- What is the producer's effective `transaction.timeout.ms`?
- What is the broker's `transaction.max.timeout.ms`?
- Are `transactional.id` prefixes unique across instances?
- Do downstream consumers use `read_committed`?
- Do `max.poll.interval.ms` and dependency timeouts fit?

### Step 4: Identify the cause of long durations

Measure p99 listener duration, HTTP/database timeouts, Kafka send/commit latencies, broker health, and GC pauses. If the listener processes large batches, inspect record counts and sequential work inside the transaction.

### Step 5: Classify recovery actions

- If caused by a transient dependency stall: shrink scope and retry the record in a new transaction per policy.
- If the producer was fenced: recover producer lifecycle and fix `transactional.id` uniqueness.
- If the broker aborted due to expiration: never try to re-commit the old transaction.
- If non-Kafka side effects ran: reconcile state and verify idempotency before replaying.

### Step 6: Recover and verify

After changes, monitor commit/abort rates, transaction durations, listener throughput, `read_committed` lag, rebalances, and duplicate side effects. Confirm input offsets and Kafka outputs advance cleanly together.

## 26. Common Design Mistakes

| Mistake | Risk | Remediation |
|---|---|---|
| Raising `transaction.timeout.ms` to fix everything | Masks slow listeners, keeps open transactions and LSO stalled longer | Measure transaction scope, dependencies, and coordinator |
| Setting producer timeout above broker max | Transactional producer init may be rejected | Check `transaction.max.timeout.ms` |
| Confusing `@Transactional` timeout with Kafka producer timeout | Expected bounds do not apply | Configure separately per manager and Kafka producer |
| Holding transactions open across untimed HTTP calls | Broker aborts while request still runs | Set timeouts, shrink scope, use idempotency/outbox |
| Retrying `commitTransaction` infinitely on aborted transactions | Unrecoverable and keeps broken producer pinned | Retry whole unit in a fresh transaction if safe |
| Sharing `transactional.id` across two instances | Producer fencing | Unique prefix per instance/lifecycle |
| Leaving downstream on `read_uncommitted` | May observe outputs from aborted transactions | Use `read_committed` where transactional visibility matters |
| Treating high consumer lag as slow consumer | LSO may be pinned by an open transaction | Check LSO and transaction state |
| Retrying listeners without protecting DB/HTTP side effects | Business duplicates | Inbox/outbox/idempotency keys |
| Inspecting only the final commit exception | Misses the earlier slow listener cause | Capture timelines and measure dependency latencies |
| Ignoring `max.poll.interval.ms` | Can trigger both transaction timeout and rebalance | Budget poll intervals separately |
| Confusing producer send retries with transaction retries | Retrying at wrong scope or after fatal errors | Distinguish producer requests from transaction lifecycles |

## 27. Pre-Production Checklist for Kafka Transactions

1. Is `transaction.timeout.ms` explicitly configured for transactional producers?
2. Does the value fit within broker `transaction.max.timeout.ms`?
3. Are `transactional.id` prefixes unique across application instances and producer pools?
4. Are exact transaction start/end boundaries documented?
5. Do listeners execute long HTTP/database calls inside transactions?
6. Do all dependencies have finite timeouts and sensible retry policies?
7. Do p95/p99 transaction durations leave sufficient margin below the timeout?
8. Was `max.poll.interval.ms` evaluated independently of `transaction.timeout.ms`?
9. Do output consumers use `isolation.level=read_committed` where required?
10. Are transaction durations, aborts, commit failures, fencing, and LSO/lag monitored?
11. If a transaction aborts after non-Kafka side effects, is idempotency or reconciliation in place?
12. Do transactional listeners have an appropriate rollback/recovery processor?
13. Are transaction timeouts, restarts, coordinator outages, and duplicates tested?
14. Do separate runbooks exist for fencing, request timeouts, and broker aborts?
15. Were outbox/inbox patterns considered when consistency spans beyond Kafka?

**Conclusion:** Transaction timeout is not just a millisecond number in producer properties. It is the broker's mechanism to clean up stalled transactions, directly impacting Spring Kafka's ability to commit outputs/offsets and `read_committed` consumer latency. Sustainable usage keeps transaction scopes short, bounds dependencies with timeouts, separates timeout layers, isolates `transactional.id` values, measures transaction durations, and enforces idempotency on all side effects outside Kafka.
