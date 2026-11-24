# Testing Transactions

Kafka transactions group multiple Kafka write operations into a single commit or abort unit. In Spring Kafka, transactions can be used when a producer sends a batch of records, or when a listener reads an input record, processes it, sends output, and commits offsets within the same transaction. Testing transactions must prove that **consumers see only committed data, data from aborted transactions is hidden from `read_committed`, and input offsets advance alongside outputs when using a transactional listener**.

Merely checking that a listener was called or that `KafkaTemplate.send()` did not throw an exception is not enough. Transactions are a coordinated behavior across the producer, broker transaction coordinator, consumer isolation level, and listener container. Tests must observe post-commit/post-abort state from an appropriately configured consumer.

## 1. Objectives of Testing Transactions

A transaction test should answer these questions:

- Can the producer open a transaction, send records, and commit successfully?
- When a transaction aborts, does a `read_committed` consumer skip the records from that transaction?
- Are multiple output records committed/aborted together?
- With a transactional listener, do outputs and input offsets commit together?
- Does a listener throwing an exception roll back the transaction and retry the record according to policy?
- Is a producer fenced when its transactional ID is used by another producer?
- Does the consumer behave properly while a transaction is open or incomplete?

The EOS scope here is Kafka state. If a listener updates a database or makes HTTP calls, those side effects live outside the Kafka transaction and must be tested separately with inbox/outbox or idempotency.

## 2. Distinguishing Producer Transactions and Transactional Listeners

Spring Kafka supports two main testing scenarios:

| Scenario | Usage | What to Verify |
| --- | --- | --- |
| Producer-only transaction | `KafkaTemplate.executeInTransaction(...)` | Outputs inside the callback commit or abort together |
| Transactional listener container | Attach `KafkaTransactionManager` to the listener container | Outputs and input offsets commit/abort together |

Producer-only transactions fit when the application needs to publish a group of records atomically without an associated consumer offset. Transactional listeners fit consume-process-produce flows: the container starts a transaction before invoking the listener, `KafkaTemplate` sharing the same producer factory participates in the transaction, and then the container sends input offsets into the transaction.

Both scenarios can share a test broker, but require different assertions. A producer-only test does not prove consumer offsets commit atomically. Only listener container tests verify the relationship between outputs and input offsets.

## 3. Configuring a Transaction-Capable Test Broker

Transaction tests require a Kafka broker that supports transactions. With a single-node test broker, the transaction state topic must have a replication factor and min ISR matching the broker count. Example `@EmbeddedKafka`:

```java
import org.springframework.kafka.test.context.EmbeddedKafka;

@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.input", "orders.output"},
        brokerProperties = {
                "transaction.state.log.replication.factor=1",
                "transaction.state.log.min.isr=1"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaTransactionIntegrationTest {
}
```

With a single-node broker, setting replication factor and min ISR to 1 is solely for testing. This configuration does not represent the durability of a multi-broker production cluster. When using Testcontainers, verify that the Kafka image and broker properties support transactions as in the target environment.

Ensure test topics are created before tests run with a fixed partition count. Do not rely on automatic topic creation because default partition counts can alter partition assignments or offset assertions.

## 4. Configuring Spring Kafka Transactions in Tests

A transactional producer factory requires a `transactionIdPrefix`. The prefix must be unique across concurrently active producer factories. Spring Boot configuration example:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: test-orders-${random.uuid}-
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

`transaction-id-prefix` instructs Spring Boot to configure a transactional producer factory and transaction manager in auto-configuration. In tests running multiple contexts or multiple producer factories concurrently, assign distinct prefixes to avoid unintended `ProducerFencedException` errors.

If configuring in Java manually, wire the components to the same producer factory:

```java
@Bean
ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    var factory = new DefaultKafkaProducerFactory<String, String>(props);
    factory.setTransactionIdPrefix("test-orders-" + UUID.randomUUID() + "-");
    return factory;
}

@Bean
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

The transactional listener container factory must be wired with the transaction manager:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
transactionalListenerFactory(
        ConsumerFactory<String, String> consumerFactory,
        KafkaTransactionManager<String, String> transactionManager) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
```

Since Spring Kafka 3.2, use `setKafkaAwareTransactionManager(...)`; the legacy `setTransactionManager(...)` API is deprecated. `KafkaTemplate` uses the same `ProducerFactory` as the transaction manager so sends inside the listener join the active transaction.

## 5. Testing Producer Transaction Commit

`KafkaTemplate.executeInTransaction(...)` opens a local transaction for the callback. If the callback completes normally, the transaction commits; if the callback throws an exception, the transaction aborts and the exception propagates to the caller.

Example sending two records inside one transaction:

```java
@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void commitsAllRecordsInTransaction() {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.output", "order-1", "created");
        operations.send("orders.output", "order-2", "confirmed");
        return null;
    });

    List<String> values = readCommittedValues("orders.output", 2);

    assertThat(values).containsExactlyInAnyOrder("created", "confirmed");
}
```

`readCommittedValues` is a custom test helper that consumes records using a `read_committed` consumer with a timeout. This example only illustrates transaction boundaries; in real tests, use a dedicated topic per test or clean up topic/group state so you do not read records from earlier runs.

If the callback returns normally while an async send fails, `KafkaTemplate` handles the send result within the transaction. For assertions, wait until the transaction callback finishes and then read from the test consumer; do not treat the `send()` call site as proof of commit.

## 6. Testing Producer Transaction Abort

When the callback throws an exception, the transaction must abort. A `read_committed` consumer must not return records sent inside an aborted transaction:

```java
@Test
void abortedTransactionIsInvisibleToReadCommittedConsumer() {
    assertThatThrownBy(() -> kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.output", "order-3", "must-abort");
        throw new IllegalStateException("force rollback");
    })).isInstanceOf(IllegalStateException.class);

    List<String> values = readCommittedValues("orders.output", 1);

    assertThat(values).doesNotContain("must-abort");
}
```

The helper needs a finite timeout and a dedicated topic for the test. In a test asserting the absence of records, poll for a bounded duration after the transaction aborts; do not wait indefinitely because the expected result is no message.

A `read_uncommitted` consumer can see records from aborted transactions. Therefore, when verifying that data is not exposed to downstream EOS applications, the test consumer must set `isolation.level=read_committed`.

## 7. Creating a Test Consumer with `read_committed`

When using `KafkaTestUtils.consumerProps(...)`, explicitly override the isolation level:

```java
Map<String, Object> consumerProps = KafkaTestUtils.consumerProps(
        "transaction-test-group",
        "false",
        embeddedKafkaBroker);
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

try (Consumer<String, String> consumer = new KafkaConsumer<>(consumerProps)) {
    consumer.subscribe(List.of("orders.output"));
    // Poll with a timeout and inspect records.
}
```

This example requires importing `KafkaTestUtils`, `EmbeddedKafkaBroker`, `KafkaConsumer`, `Consumer`, and appropriate serializer/deserializer configurations. An independent test consumer should have its own group ID, `enable.auto.commit=false`, and `auto.offset.reset=earliest` if reading from the beginning of the topic.

Wait for consumer assignment before relying on `poll()`. With a fresh single-partition test topic, you can poll until assignment appears and then continue. Do not assume `subscribe()` means partitions are assigned instantaneously.

## 8. Testing Transactional Listener Commit

With a transactional listener, the container starts a transaction before calling the listener. The listener sends outputs using a `KafkaTemplate` sharing the same producer factory. When the listener completes, the container adds input offsets to the transaction and commits.

Example listener:

```java
@Component
public class OrderTransactionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderTransactionListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            id = "order-transaction-listener",
            topics = "orders.input",
            groupId = "order-transaction-test",
            containerFactory = "transactionalListenerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        kafkaTemplate.send(
                "orders.output",
                record.key(),
                "processed:" + record.value());
    }
}
```

The integration test should:

1. Send a record to `orders.input`.
2. Wait for the listener to process and the transaction to commit.
3. Consume `orders.output` using a `read_committed` consumer.
4. Assert the output has the right key/value.
5. Verify the `order-transaction-test` group offset advanced past the input offset.

To check offsets, use `AdminClient.listConsumerGroupOffsets(...)` or a consumer in the same group reading committed offsets. The committed offset is normally the next position to read, i.e., the processed record's offset plus one when processing one record sequentially.

Do not call `acknowledge()` manually in a transactional listener just to force offset commits. The container transaction manages offsets; let exceptions escape the listener when wanting a rollback.

## 9. Testing Transactional Listener Rollback and Redelivery

An important test is having the listener send an output and then throw an exception. The output from the failed attempt must be aborted; the input record is retried; only the successful attempt produces committed output.

You can build a test listener with an attempt counter:

```java
@Component
public class FailingOnceTransactionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final AtomicInteger attempts = new AtomicInteger();

    public FailingOnceTransactionListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.retry-input",
            groupId = "transaction-retry-test",
            containerFactory = "transactionalListenerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        int attempt = attempts.incrementAndGet();
        kafkaTemplate.send("orders.retry-output", record.key(), "attempt-" + attempt);

        if (attempt == 1) {
            throw new IllegalStateException("fail first delivery");
        }
    }
}
```

`DefaultAfterRollbackProcessor` coordinates seeking and redelivering the record after rollback according to configuration. Tests can configure a short backoff and suitable retry limit. After the second processing attempt succeeds, a `read_committed` consumer on the output should see only `attempt-2`; `attempt-1` belonged to an aborted transaction and is never exposed.

This is a simple illustrative example. In real tests, use a test-specific listener bean or `@MockitoBean`/bean replacement mechanism matching your Spring version. Avoid sharing an `AtomicInteger` across multiple tests or partitions unintentionally.

## 10. Testing Input Offsets and Outputs Committing Together

To prove EOS for a transactional listener, verify both sides of the transaction:

| Listener Outcome | `read_committed` Output | Input Offset |
| --- | --- | --- |
| Listener succeeds | Output appears | Offset advances |
| Listener sends output then throws exception | Output from failed attempt does not appear | Offset does not advance due to transaction abort |
| Subsequent retry succeeds | Output from successful commit appears | Offset advances in that same transaction |

If checking only outputs, tests may miss offset bugs. If checking only offsets, tests may miss missing outputs. Observe both using the corresponding consumer group and output consumer.

When reading committed offsets with `AdminClient`, wait for the container to finish the transaction and use Awaitility to wait for the offset to reach the expected value. Do not read immediately after the listener method starts or after the producer sends output before the transaction commits.

## 11. Testing Transaction Timeout and Producer Fencing

Transaction timeout occurs when a transaction stays open longer than `transaction.timeout.ms` or the broker enforces its corresponding limit. The producer may receive an error on commit or the next operation. Timeout tests should use small values on a dedicated test broker and test producer; do not change production timeouts just to make tests fast.

Producer fencing happens when a new producer initializes with the same `transactional.id` and a newer epoch invalidates the older producer. Fencing can be tested with two transactional producers sharing the same ID:

1. Initialize producer A with a fixed transactional ID and call `initTransactions()`.
2. Initialize producer B with the same transactional ID.
3. Perform another transaction operation on producer A.
4. Verify producer A is fenced and cannot commit the old transaction.

This test requires careful producer lifecycle management and should run only in an isolated test environment. Never let two parallel tests share the same transactional ID, as that causes random fencing.

## 12. Testing Multiple Producers and Multiple Instances

In Spring applications, `transactionIdPrefix` must be unique across concurrently running instances. Configuration tests should verify:

- Each application context/instance receives a distinct prefix.
- Producer factories within the same instance generate distinct transactional ID suffixes for cached producers.
- Two instances do not accidentally fence each other.
- When intentionally configured with duplicate prefixes, tests/diagnostics can detect `ProducerFencedException`.

Do not use a single global fixed prefix across all test classes if tests run in parallel. Generate prefixes with UUIDs or per-test-run namespaces.

## 13. Testing Transactions with Batch Listeners

With a transactional batch listener, one transaction wraps each batch processing cycle. If the listener throws an exception, the batch transaction rolls back; batch offsets are not committed in that transaction.

Tests should verify:

- The batch receives the right number of records and partitions/offsets.
- When the entire batch succeeds, outputs and offsets commit.
- When one record causes the listener to throw an exception, outputs sent during the batch transaction are aborted.
- `AfterRollbackProcessor` handles retries according to configured batch semantics.
- Side effects outside Kafka are not assumed to roll back with the Kafka transaction.

Do not test a batch listener as multiple independent record listeners. Transaction and retry boundaries differ; use a fixed batch size and test with a small batch.

## 14. Testing Recovery/DLT After Rollback

Transactional listeners normally use `AfterRollbackProcessor` rather than mechanically applying a non-transactional listener's `DefaultErrorHandler`. Once retries are exhausted, the record can be recovered and published to a DLT.

If DLT publishing and the input offset must commit atomically, configure transactional after-rollback recovery, such as `commitRecovered=true` with a transactional `KafkaTemplate` appropriate for your Spring Kafka version. Tests should verify:

- The failed record eventually appears on the DLT.
- A `read_committed` DLT consumer reads the record after the recovery transaction commits.
- The input offset advances after successful recovery.
- If DLT publishing fails, the input offset is not committed as if recovery succeeded.
- DLT headers preserve the topic, partition, offset, and required exception metadata.

If DLT publishing runs outside the transaction or uses a different producer factory, do not assume it is atomic with the input offset. Inspect the actual recoverer configuration.

## 15. Do Not Combine Non-Blocking Retry with Container Transactions

`@RetryableTopic` forwards records to retry topics to perform non-blocking retries. This mechanism does not support listener container transactions.

Therefore, transaction tests must pick a compatible model:

- Transactional listener: test rollback/retry via `AfterRollbackProcessor`.
- Non-blocking retry: test main/retry/DLT topology with a listener not running container transactions.

Do not configure `@RetryableTopic` on a transactional listener and expect input offsets, retry topics, and business outputs to participate in a single Kafka transaction.

## 16. Transactions Do Not Roll Back Databases: Testing External Boundaries

Kafka transactions cover only Kafka records and consumer offsets sent into the transaction. They do not automatically roll back databases, HTTP requests, emails, or file writes.

An integration test can simulate:

1. Listener updates the database successfully.
2. Listener sends a Kafka output.
3. The Kafka transaction aborts.
4. The input record is redelivered.
5. The database update is invoked again.

If the database update is not idempotent, business state can be duplicated even while Kafka EOS works properly. Tests should prove that inbox/event IDs prevent duplicate side effects or that an outbox keeps business changes and events in the same database transaction.

Do not write an assertion claiming "the listener is invoked only once" as proof of EOS. Listeners can be invoked multiple times; what must be proven is the committed Kafka state and accurate final business side effects.

## 17. Synchronizing Async Tests and Avoiding Flakiness

Kafka transactions and listener containers run asynchronously. Principles for stable tests:

- Await the producer's `CompletableFuture` with a timeout when confirming send completion.
- Use Awaitility, `CountDownLatch`, or `BlockingQueue` to wait for listeners and committed offsets.
- Wait for consumer assignment before polling data.
- Use dedicated topics and group IDs per test or test class.
- Use dedicated transactional ID prefixes, especially when tests run in parallel.
- Set `auto.offset.reset=earliest` for test consumers reading records from the start.
- Use `read_committed` for assertions on committed outputs.
- Do not use fixed `Thread.sleep` as proof that a transaction committed/aborted.
- Close consumers, producers, and containers after tests.

When an assertion times out, log topic, partition, offset, group ID, transaction outcome, and listener assignment for diagnosis.

## 18. Embedded Kafka or Testcontainers for Transaction Tests?

| Criterion | Embedded Kafka | Testcontainers |
| --- | --- | --- |
| Startup | Fast and integrates directly with Spring Kafka test | Starts a container, depends on Docker |
| Transactions | Can test producer transactions and listener transactions | Can test transactions on a specific broker image/version |
| Broker configuration | Must set transaction state replication matching the test broker | Can configure close to the deployment environment |
| Purpose | Frequent transaction integration tests | Compatibility tests, broker configs, and production-like environments |

Embedded Kafka fits testing Spring Kafka logic in regular suites. Testcontainers fits when verifying broker versions, KRaft/configuration, or production-like broker images. Whichever tool is used, inspect the test broker's transaction settings.

## 19. Transaction Testing Matrix

| Scenario | Producer-Only | Transactional Listener |
| --- | :---: | :---: |
| Send one record and commit | ✓ | ✓ |
| Send multiple records in one transaction | ✓ | ✓ |
| Throw exception and abort | ✓ | ✓ |
| `read_committed` hides aborted output | ✓ | ✓ |
| Input offset commits alongside output |  | ✓ |
| Listener redelivery after rollback |  | ✓ |
| `AfterRollbackProcessor` retry/recovery |  | ✓ |
| Batch transaction |  | ✓ |
| Producer fencing | ✓ | ✓ |
| DLT recovery and offsets |  | ✓ |
| Database idempotency/outbox | Tested separately at application layer | Tested separately at application layer |

## 20. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Transaction test fails to start | Test broker lacks matching transaction state replication/min ISR | Configure test broker per node count |
| Consumer still reads aborted records | Consumer uses `read_uncommitted` | Set `isolation.level=read_committed` |
| Listener sends output but offset does not advance together | Container lacks transaction manager or template uses another factory | Check `KafkaAwareTransactionManager` and shared `ProducerFactory` |
| Listener throws exception yet transaction commits | Exception was caught and not propagated to container | Let exceptions propagate to roll back |
| Test receives duplicate output | Test reads aborted records or listener retries cause non-Kafka side effects | Use `read_committed`, verify business idempotency |
| Random `ProducerFencedException` | Tests share transactional ID/prefix or run in parallel | Provide a distinct prefix per test/instance |
| Test does not see records | Consumer not assigned, wrong offset reset, or polled too early | Wait for assignment, set `earliest`, use timeouts |
| Offset assertion off by one | Committed offset is the next position to read | Compare against processed record offset plus one |
| DLT has record yet input offset has not advanced | Wrong recovery/commit policy or DLT published outside transaction | Check `AfterRollbackProcessor` and `commitRecovered` |
| Database updated twice | Database is outside the Kafka transaction | Use inbox/outbox or idempotent operations |

## 21. Pre-Release Checklist

- [ ] Test broker supports transactions and the transaction state topic is configured properly.
- [ ] Producer factory has a dedicated `transactionIdPrefix`.
- [ ] Transaction manager and `KafkaTemplate` share the same producer factory.
- [ ] Listener container is wired with `KafkaAwareTransactionManager`.
- [ ] Assertion consumers use `read_committed`.
- [ ] Producer-only commit/abort paths are tested.
- [ ] Transactional listener commit/rollback paths are tested.
- [ ] Outputs and input offsets are verified to commit together.
- [ ] `AfterRollbackProcessor` retry/recovery is tested.
- [ ] DLT publishing and offset recovery are verified if used.
- [ ] Fencing and transaction timeouts are tested according to risk.
- [ ] Batch listeners have dedicated tests if used.
- [ ] Database/external side effects have dedicated idempotency/outbox tests.
- [ ] Tests have timeouts, isolated topics/groups/prefixes, and explicit cleanup.

## 22. Conclusion

Testing transactions in Spring Kafka must prove committed state, not merely that send calls or listeners ran. For producer-only transactions, verify that outputs commit or abort together. For transactional listeners, verify that outputs and input offsets commit together while confirming rollback, redelivery, and recovery through `AfterRollbackProcessor`.

Use a transaction-capable test broker, `read_committed` consumers, dedicated transactional ID prefixes, and asynchronous waits with timeouts. Inspect both offsets and outputs to confirm atomicity. Finally, maintain clear boundaries: Kafka transactions do not encompass databases or external services; those side effects need idempotency, inbox/outbox patterns, and separate tests.

## References

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
