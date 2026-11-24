# Testing Message Readers and Writers

In Spring Batch, message readers and message writers enable a step to receive data from a message broker or send results to a destination such as a JMS queue or topic. Unlike files or databases, a message is an independent unit of exchange that can be acknowledged, redelivered, duplicated, or expired according to broker policy. Therefore, testing message readers and writers must verify both payload conversion and delivery/transaction semantics.

For JMS, Spring Batch provides `JmsItemReader<T>` and `JmsItemWriter<T>`. The reader receives messages via `JmsTemplate` and converts payloads into items; the writer converts each item into a message and sends it to a destination. You can unit test both components independently by mocking `JmsTemplate`, then add integration tests against a real broker to verify acknowledgement, rollback, redelivery, headers, and destination behavior.

## 1. Message Processing in Spring Batch

A message-oriented step typically looks like:

```text
JMS Queue / Topic
       |
       v
  JmsItemReader
       |
       v
  ItemProcessor
       |
       v
  JmsItemWriter
       |
       v
Output Queue / Topic
```

The reader and writer are invoked chunk by chunk just like other item components. For example, a step reads 100 messages, processes 100 payloads, and sends outputs within one chunk. However, message brokers have their own delivery mechanics; a step database transaction rolling back does not automatically guarantee received messages are redelivered or sent messages are revoked.

When designing tests, separate these questions:

- Does the reader receive the right messages from the right destination?
- Does the message converter produce the right Java items?
- When no messages remain, does the reader return `null` per the `ItemReader` contract?
- Does the writer send every item to the right destination with the right payload/headers?
- If a chunk fails, are received messages redelivered and sent messages rolled back?
- Can retries/restarts produce duplicate messages?
- How does the broker handle poison messages, delivery limits, and dead-letter queues?

## 2. JmsItemReader and JmsItemWriter

Two components commonly used in Spring Batch JMS:

| Component | Responsibility |
|---|---|
| `JmsItemReader<T>` | Receives messages from a destination via `JmsTemplate`, converts messages to items, and returns them one by one. |
| `JmsItemWriter<T>` | Converts items into JMS messages and sends them to a destination via `JmsTemplate`. |
| `JmsTemplate` | Provides JMS send/receive APIs and uses `MessageConverter` when calling `convert...` methods. |
| `MessageConverter` | Converts Java payloads to JMS messages and vice versa. |
| JMS `ConnectionFactory` | Creates connections/sessions to the broker. |
| JMS Transaction Manager | Manages local JMS transactions and session commit/rollback. |

`JmsItemReader` is typically configured with `JmsTemplate`, a destination name, and an item type. `JmsItemWriter` likewise accepts `JmsTemplate` and a target destination. Exact APIs may vary across Spring Batch/Spring Framework versions; use the `jakarta.jms` package in Spring Framework 6/Spring Batch 5, and check the corresponding API if the application runs an older `javax.jms` generation.

## 3. Configuring a Message Reader

Example of a queue holding customer payloads converted into `CustomerMessage`:

```java
@Bean
@StepScope
JmsItemReader<CustomerMessage> customerMessageReader(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['inputDestination']}") String destination) {

    JmsItemReader<CustomerMessage> reader = new JmsItemReader<>();
    reader.setName("customerMessageReader");
    reader.setJmsTemplate(jmsTemplate);
    reader.setDestinationName(destination);
    reader.setItemType(CustomerMessage.class);
    return reader;
}
```

In this example, `@StepScope` lets the destination be chosen via `JobParameters`. Destinations must be validated against application configuration; never accept an arbitrary destination from a message or untrusted input.

The reader uses `JmsTemplate` to receive messages. When the message converter runs, the payload is converted to `CustomerMessage`. If a message cannot be converted or the payload has the wrong type, the reader may throw an exception; never turn conversion errors into `null` because `null` in `ItemReader` signals end of input.

## 4. Configuring a Message Writer

The writer sends each item to a destination:

```java
@Bean
@StepScope
JmsItemWriter<CustomerMessage> customerMessageWriter(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['outputDestination']}") String destination) {

    JmsItemWriter<CustomerMessage> writer = new JmsItemWriter<>();
    writer.setJmsTemplate(jmsTemplate);
    writer.setDestinationName(destination);
    return writer;
}
```

Within a chunk, the writer sends each item as a message. If one send fails mid-chunk, the actual outcome depends on the active JMS session/transaction. Never assume messages sent before the error vanish automatically when Spring Batch rolls back the database transaction.

If outputs require a correlation ID, event type, or batch ID, use a custom `MessageConverter`, `MessagePostProcessor`, or dedicated writer adapter to attach appropriate headers/properties. Tests should verify this metadata as part of the integration contract.

## 5. Configuring MessageConverter

JMS messages come in forms such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. `MessageConverter` decides how Java payloads convert to messages and back.

For `String` payloads or types supported by `SimpleMessageConverter`, a simple configuration may suffice. For JSON DTOs, you can use a Jackson-based converter:

```java
@Bean
MappingJackson2MessageConverter customerMessageConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}

@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory,
                        MessageConverter customerMessageConverter) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(customerMessageConverter);
    return template;
}
```

JSON converters can use a type ID to determine the Java type upon receipt. Restrict allowed types and never trust arbitrary type metadata supplied by senders. In multi-service systems, explicit schemas/versions and a discriminator allowlist are usually safer and easier to govern than allowing deserialization of arbitrary classes.

## 6. Unit Testing the Reader with a Mock JmsTemplate

Reader unit tests should verify:

- The reader uses the right destination.
- Payloads are returned in receive order.
- The reader returns `null` when `JmsTemplate` has no more messages.
- The reader does not return items of the wrong type.
- Broker/converter exceptions propagate per contract.

Example using Mockito with `String` payloads:

```java
@ExtendWith(MockitoExtension.class)
class JmsItemReaderTest {

    @Mock
    private JmsTemplate jmsTemplate;

    private JmsItemReader<String> reader;

    @BeforeEach
    void setUp() {
        reader = new JmsItemReader<>();
        reader.setName("testJmsReader");
        reader.setJmsTemplate(jmsTemplate);
        reader.setDestinationName("customer.input");
        reader.setItemType(String.class);
        reader.afterPropertiesSet();
        reader.open(new ExecutionContext());
    }

    @AfterEach
    void tearDown() {
        reader.close();
    }

    @Test
    void readsMessagesUntilNoMessageIsAvailable() throws Exception {
        when(jmsTemplate.receiveAndConvert("customer.input"))
                .thenReturn("C001", "C002", null);

        assertThat(reader.read()).isEqualTo("C001");
        assertThat(reader.read()).isEqualTo("C002");
        assertThat(reader.read()).isNull();

        verify(jmsTemplate, times(3))
                .receiveAndConvert("customer.input");
    }
}
```

This example assumes the `JmsItemReader` version in use calls the `receiveAndConvert(String destinationName)` overload. If your implementation/version calls an overload accepting `Destination`, mock that exact overload. Unit tests should reflect the real API in your project dependencies.

`open()` and `close()` are invoked to respect the reader's `ItemStream` lifecycle. Avoid calling `read()` on an unopened stream reader when the contract requires `open(ExecutionContext)` first.

## 7. Testing Reader Returning Null and End of Input

With a finite queue or a batch with a clear termination signal, the reader can return `null` when no messages remain. Tests must verify `null` appears only at the defined end condition.

An ordinary JMS queue has no natural EOF. If `JmsTemplate.receiveAndConvert(...)` returns `null` due to a timeout or a currently empty queue, `JmsItemReader` may return `null` to Spring Batch. The framework treats this as end of input and the step may complete. Messages arriving later will not automatically restart the step.

Therefore, before using `JmsItemReader` on a queue, choose one of these models:

- A batch with a known expected message or record count.
- A final sentinel/end-marker message per contract.
- Batch/manifest metadata determining when all messages have been received.
- Draining the queue within a finite time window where timeout counts as business completion.
- Using a message-driven consumer or integration flow suited to continuous streams instead of a finite batch step.

Do not test "temporarily empty queue" as "batch complete" unless that is an agreed business rule.

## 8. Testing the Message Converter Separately

Do not test readers/writers only with `String`s when production uses JSON DTOs. Test the converter independently to verify message formatting.

Example checking conversion of a DTO to a JSON `TextMessage` and back:

```java
@Test
void convertsCustomerPayloadToAndFromTextMessage() throws Exception {
    CustomerMessage input = new CustomerMessage("C001", "Nguyen An");

    Message message = converter.toMessage(input, session);
    assertThat(message).isInstanceOf(TextMessage.class);

    CustomerMessage restored = (CustomerMessage) converter.fromMessage(message);
    assertThat(restored.customerId()).isEqualTo("C001");
    assertThat(restored.name()).isEqualTo("Nguyen An");
}
```

This is an illustrative contract test; how `Session`/messages are created in unit tests depends on the JMS provider and converter. For converters requiring a real broker/session, integration tests are more appropriate.

Cases to test:

- Valid payloads matching the schema.
- Missing required fields.
- Malformed JSON or unsupported types.
- Unicode characters and encoding.
- Headers/type IDs/correlation IDs.
- Old and new schema versions.
- Oversized payloads or payloads exceeding configured limits.

## 9. Unit Testing the Writer with a Mock JmsTemplate

Writer unit tests verify every item is sent to the right destination and send failures propagate.

```java
@ExtendWith(MockitoExtension.class)
class JmsItemWriterTest {

    @Mock
    private JmsTemplate jmsTemplate;

    private JmsItemWriter<String> writer;

    @BeforeEach
    void setUp() {
        writer = new JmsItemWriter<>();
        writer.setJmsTemplate(jmsTemplate);
        writer.setDestinationName("customer.output");
        writer.afterPropertiesSet();
    }

    @Test
    void sendsEveryItemToConfiguredDestination() throws Exception {
        writer.write(new Chunk<>(List.of("C001", "C002", "C003")));

        verify(jmsTemplate).convertAndSend("customer.output", "C001");
        verify(jmsTemplate).convertAndSend("customer.output", "C002");
        verify(jmsTemplate).convertAndSend("customer.output", "C003");
        verifyNoMoreInteractions(jmsTemplate);
    }

    @Test
    void propagatesSendFailure() {
        doThrow(new JmsException("broker unavailable"))
                .when(jmsTemplate)
                .convertAndSend("customer.output", "C001");

        assertThatThrownBy(() -> writer.write(
                new Chunk<>(List.of("C001"))))
                .isInstanceOf(JmsException.class);
    }
}
```

This example assumes the writer calls `convertAndSend(String destinationName, Object message)`. If your version or implementation uses a `Destination` object or an overload with `MessagePostProcessor`, verify the actual method invoked.

Mock tests verify the calls are constructed accurately; they do not prove the broker accepted, persisted, or delivered messages. Those require integration tests.

## 10. Testing Empty Chunks and Writer Failures

Test the writer with an empty chunk according to your version's contract. No dummy messages should be sent when a chunk has no items.

Another critical test is a failure occurring after the writer has sent part of a chunk:

```text
Chunk: A, B, C
  send A -> success
  send B -> success
  send C -> exception
```

Unit tests can verify the exception propagates and prior calls occurred. However, mocks cannot verify whether the broker rolls back A/B. That depends on session transactions and transaction managers.

Do not write an assertion claiming "the writer threw an exception so no messages were sent" unless a transaction actually spans sending and you verified the broker supports those semantics. When sending per message with an auto-ack/non-transacted session, messages sent before the failure may already exist at the destination.

## 11. Testing Destinations and Routing

Destinations are part of the contract. Unit tests should verify:

- The reader consumes from the right queue/topic.
- The writer publishes to the right queue/topic.
- `JobParameters` or configuration profiles pick the right destination.
- No accidental cross-routing across dev/test/prod environments.
- Message-type routing never sends payloads to the wrong destination.

If using `Destination` objects instead of destination names, verify the exact object passed to `JmsTemplate`. For dynamic destinations, allowlist permitted names and test invalid inputs.

Never share a fixed queue name across parallel tests. Use run-suffixed destinations or dedicated brokers per test so messages from other tests do not bleed in.

## 12. Integration Tests with a Real Broker

Mock unit tests fail to simulate:

- JMS sessions and acknowledgement modes.
- Message persistence.
- Delivery counts and redelivery.
- Selectors and destination semantics.
- Transaction commits/rollbacks.
- Dead-letter queues and expiration.
- Actual provider serialization.

Therefore, for production message readers/writers, write integration tests with a broker of the same type or compatible with production. You can run an ephemeral in-test broker via an embedded broker when supported by the provider, or a dedicated test container.

A basic integration test:

1. Start the test broker and connection factory.
2. Create dedicated queues for the test.
3. Send several messages with known payloads/headers.
4. Open `JmsItemReader` and read items.
5. Verify ordering, content, and end condition.
6. Write items through `JmsItemWriter`.
7. Receive output messages using a test consumer.
8. Verify payloads, destinations, and metadata.
9. Clean up queues/broker after the test.

Test brokers must shut down in `@AfterEach`/`@AfterAll` or Testcontainers lifecycles so threads, ports, and resources do not leak across tests.

## 13. End-to-End Send/Receive Testing

An end-to-end test can send messages to an input queue, run a step, and inspect the output queue:

```text
Test producer
     |
     v
input.queue
     |
     v
Spring Batch Job
  JmsItemReader
  ItemProcessor
  JmsItemWriter
     |
     v
output.queue
     |
     v
Test consumer assertions
```

Tests should verify:

- `JobExecution` and `StepExecution` finish in the expected status.
- `readCount`, `writeCount`, `filterCount`, and `skipCount` match inputs.
- Output queue receives all expected messages.
- Payloads preserve key data after conversion.
- Headers such as correlation ID, event type, and batch ID are preserved or generated accurately.
- Input queue retains or removes messages per the chosen acknowledgement/transaction policy.
- No leftover messages remain from earlier tests.

## 14. JMS Acknowledgement and Transactions

This is the most crucial part when testing readers. JMS has its own acknowledgement modes and transactions. Default `JmsTemplate` often uses `AUTO_ACKNOWLEDGE` when no managed JMS transaction is active. With synchronous receives, messages can be acknowledged immediately upon successful receipt.

If `JmsItemReader` receives a message and Spring Batch later rolls back the chunk due to a processor/writer failure, already auto-acknowledged messages may not be redelivered. A database rollback does not automatically return messages to the queue.

If message receipt must commit alongside the chunk, configure proper JMS transactions and use a transaction manager governing the JMS session for the step. When JMS is the only resource, `JmsTransactionManager` can manage local JMS transactions. When a step writes to a database while receiving/sending JMS, a single local transaction manager does not make both atomic automatically; use XA/JTA if supported, or outbox/inbox plus idempotency.

Tests must simulate failures after receiving and verify actual broker behavior under real configuration. Never infer acknowledgement behavior solely from seeing step status `FAILED`.

## 15. Testing Rollback and Redelivery

A transaction test should verify both commit and rollback cases:

**Commit:**

1. Send messages to the input queue.
2. Run the step with the appropriate JMS transaction manager.
3. Let the chunk complete.
4. Verify messages are consumed/acknowledged as designed.

**Rollback:**

1. Send messages to the input queue.
2. Make the processor or writer throw an exception before commit.
3. Verify the JMS session rolls back.
4. Receive the message again using a test consumer.
5. Check redelivery flags/counts per broker.

Redelivery property names can vary across JMS providers. JMS defines the `JMSRedelivered` flag; some brokers also provide delivery counts as extended properties. Portable tests should check `JMSRedelivered` when possible and check provider-specific counts only in broker-specific tests.

## 16. Distinguishing JMS Transactions from Database Transactions

A chunk may need to update a database and send messages. There are three scenarios:

| Configuration | Risk |
|---|---|
| Database transaction with non-transacted JMS send | Database rollback does not revoke already-sent messages. |
| Local JMS transaction with separate database transaction | JMS rollback does not roll back the database and vice versa. |
| XA/JTA transaction spanning both resources | Can coordinate atomic commit/rollback if broker, database, and transaction manager are configured properly; increases operational complexity. |

For many systems, a transactional outbox is a simpler option: the batch writes data and outbox records in the same database transaction; a separate publisher sends messages post-commit. Consumers use idempotency/inbox to guard against duplicates.

Integration tests should exercise failure windows: database commits while send has not occurred; send succeeds while metadata has not committed; process crashes between the two steps. Mock tests cannot prove atomicity across two systems.

## 17. Testing JmsItemWriter on Duplicate Sends

Spring Batch can retry chunks or restart jobs after failures. If a message was accepted by the broker before the step recorded success, retries may resend the same item.

Example:

```text
Chunk sends event E-100
  broker accepts E-100
  process dies before chunk metadata commits

Restart/retry
  chunk runs again
  writer sends E-100 again
```

This is duplicate delivery/duplicate publication. JMS delivery guarantees do not automatically ensure applications see only one execution across every failure window.

Tests should use stable event IDs and verify:

- The writer can send the same event multiple times on retry.
- Consumers deduplicate by event ID or idempotency key.
- Consumer side effects apply strictly once per business rules.
- Audits can identify redelivered/duplicate messages.

Never generate a new event ID on each retry. IDs must be generated upfront or deterministically from business keys so attempts identify the same event.

## 18. Testing Poison Messages and Dead-Letter Queues

A poison message is a message that always triggers processing failures, such as invalid schema payloads, missing required fields, or unparseable data. If the broker keeps redelivering, one message can cause workers to fail repeatedly.

Tests must verify:

- Which exceptions trigger message rollback/redelivery.
- How the broker or application bounds delivery counts.
- Once the delivery limit is exceeded, whether the message moves to a dead-letter queue (DLQ) or is dropped.
- Whether payload, original destination, delivery count, and exception context are preserved.
- Whether the message can be replayed after fixing data or code.

DLQ policies depend on the broker. Some brokers use dedicated address/queue configurations; others use dead-letter strategies and delivery counts. Never assume identical DLQ names or properties across ActiveMQ Artemis, ActiveMQ Classic, IBM MQ, RabbitMQ JMS client, or other brokers.

## 19. Testing Message Headers and Correlation

Messages typically carry metadata beyond the payload:

- `JMSMessageID` generated by the provider.
- `JMSCorrelationID` linking request/response or event chains.
- `JMSType` if used by the application.
- `JMSReplyTo` for request/reply flows.
- Custom properties such as `eventType`, `schemaVersion`, `batchId`, and `tenantId`.

Writer tests should verify headers/properties are attached accurately. Reader tests should verify converters or adapters preserve required metadata in item wrappers.

Example wrapper:

```java
public record InboundMessage<T>(
        T payload,
        String correlationId,
        String eventType,
        String batchId) {
}
```

If using plain `JmsItemReader<T>` returning payloads, some metadata may not populate the object. When business logic needs headers, use a custom converter/reader returning a wrapper or a custom `ItemReader` receiving `Message` and mapping both payload and headers.

Do not rely on `JMSMessageID` as the sole idempotency key if the broker may assign a new ID when a message is republished. A stable business event ID is usually better suited.

## 20. Testing Queue and Topic Semantics

Queues and topics have different semantics:

- Queues typically distribute each message to one consumer among competing consumers.
- Publish-subscribe topics deliver messages to subscribers per subscription semantics; durable subscriptions have their own lifecycle.
- Selectors filter messages by headers/properties.
- Durable subscriptions can retain messages while subscribers are offline per broker configuration.

Tests must verify the right destination type. When using topics, verify durable/non-durable subscriptions, client IDs, and subscription names per broker. When using selectors, send both matching and non-matching messages to confirm exact item selection.

Never share topic subscriptions across parallel tests without isolation. Tests can steal each other's messages and become flaky.

## 21. Testing Message Ordering

JMS queues generally preserve send/receive order under provider conditions, yet concurrency, message priority, redelivery, multiple producers, and competing consumers can cause observed order to differ from simple test assumptions.

When business order matters:

- Use a single producer/consumer path with deterministic ordering.
- Attach sequence numbers or aggregate versions to payloads.
- Assert order by business key/version rather than relying solely on `JMSMessageID`.
- Test redelivery and multiple consumers under production-like configuration.
- Consider partitioning by aggregate key so events for the same aggregate run sequentially.

Never write tests demanding global ordering in multi-consumer setups if the system does not guarantee it.

## 22. Testing Message Expiration and Delivery Delay

Messages may carry time-to-live (TTL), delivery delays, or timestamps. Tests should verify:

- Messages expiring before the reader receives them are dropped or moved to a DLQ per policy.
- Delayed messages not yet due for delivery are not mistaken for EOF when the reader uses timeouts.
- Whether the job may terminate early on a temporarily empty queue or must wait for a batch completion signal.
- Clocks in tests are controlled to avoid flaky wall-clock dependencies.

When testing TTL, pick durations long enough for integration tests or configure appropriate clocks/waits. Avoid tests relying on long sleeps; prefer polling with deadlines and explicit conditions.

## 23. Testing Message Conversion Errors

A payload can reach the broker cleanly yet fail conversion into an item. Tests should send invalid schemas or content types to verify:

- The reader throws a meaningful exception.
- The job applies the expected skip/retry/fail policy.
- Whether the message is acknowledged or redelivered per transaction/ack mode.
- Poison messages route to a DLQ after the appropriate number of attempts.
- Raw payloads and metadata suffice for investigation.

Never catch all conversion exceptions and return `null`. That makes Spring Batch treat payload errors as EOF and end the step as if the queue ran out of data.

## 24. Testing Steps with @SpringBatchTest

`@SpringBatchTest` provides Spring Batch test utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils` in matching configurations. You can run jobs/steps with real message readers/writers pointed at a test broker.

Structural example:

```java
@SpringBatchTest
@SpringBootTest
class MessageImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JmsTemplate jmsTemplate;

    @Test
    void importsMessagesFromInputQueue() throws Exception {
        jmsTemplate.convertAndSend("customer.input",
                new CustomerMessage("C001", "Nguyen An"));

        JobExecution execution = jobLauncherTestUtils.launchJob(
                new JobParametersBuilder()
                        .addString("runId", UUID.randomUUID().toString())
                        .toJobParameters());

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

This is a skeleton; the job needs an explicit termination condition for the queue, such as a known message count or end marker. If the reader terminates on queue timeout, tests must control the timeout and avoid sending messages after the reader has already received `null`.

`JobRepositoryTestUtils` helps clean up job execution metadata between tests. It does not clear messages inside the broker; tests must drain destinations or use isolated queues.

## 25. Testing Restarts of Message Steps

Restart tests must answer: are received messages from a rolled-back chunk redelivered, and are output messages sent prior to the failure resent?

A controlled test:

1. Send a message with event ID `E-001` to the input queue.
2. Run the step and intentionally make the writer fail on the first attempt.
3. Verify the database/chunk transaction rolls back.
4. Verify the input message remains or is redelivered per JMS transaction policy.
5. Restart the same `JobInstance` or retry the chunk as designed.
6. Verify event `E-001` is applied once functionally thanks to idempotency.
7. Verify the output queue contains no duplicates outside accepted semantics.

With auto-acknowledge, the message may already be consumed despite the chunk rollback. This test catches that risk. With local JMS transactions, verify receive/ack rolls back. When combining database and JMS, test failure windows between the two resources.

## 26. Test Isolation and Cleanup

Message brokers maintain state outside the test JVM. Without isolation, tests can become order-dependent or leave messages behind for subsequent tests.

Best practices:

- Use dedicated queues/topics per test class or test run.
- Drain remaining messages after each test.
- Start ephemeral brokers and shut them down cleanly per lifecycle.
- Use isolated databases/test metadata when jobs use `JobRepository`.
- Never run parallel tests against the same destination if they compete for messages.
- Use bounded timeouts so tests never hang forever.
- Log correlation IDs/test IDs to trace messages.
- Avoid long fixed `Thread.sleep` calls; use polling with deadlines.

If tests share a singleton embedded broker, reset destinations and connection state before every test. With Testcontainers, wait for broker readiness and close containers after the suite.

## 27. Testing Consumer Idempotency

Message brokers can redeliver on consumer rollbacks, dropped connections, or unconfirmed acknowledgements. Producers may also republish after timeouts with unknown outcomes. Therefore, consumers generally need idempotency.

A common pattern stores `event_id` in an inbox table with a unique constraint:

```sql
CREATE TABLE processed_message (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Consumer processes messages inside a transaction:

1. Attempt to insert `event_id` into the inbox table.
2. If the insert succeeds, apply business changes.
3. Commit both the inbox marker and business update.
4. If the event ID already exists, skip repeated side effects per rules.

Tests should send the same event twice and verify business state changes only once. If the marker and business update do not share the same transaction, a failure window remains capable of losing or duplicating work.

## 28. Testing Message Properties and Selectors

If the reader uses a message selector, test both matching and non-matching messages:

```text
eventType = 'CUSTOMER_CREATED'
tenantId = 'tenant-01'
```

Tests should verify:

- Messages matching the selector are received.
- Non-matching messages remain at the destination or reach other subscribers per broker semantics.
- Selectors use the right property types (`String`, numbers, booleans).
- Property names do not misuse reserved JMS headers.
- Messages missing properties behave as expected.

Selector syntax and behavior can depend on the JMS provider. Run integration tests with a production-compatible broker instead of mocking `JmsTemplate` alone.

## 29. Testing Connection Errors and Timeouts

The broker may be unavailable when the reader/writer opens a connection or sends/receives messages. Test:

- Connection refused or broker restarts.
- Receive timeouts.
- Send timeouts or producer flow control.
- Consumer connection loss after receive but before commit.
- Writer failure after some sends already succeeded.
- Whether reconnecting recreates consumers/sessions properly.

Retries fit only recoverable errors. Invalid payload schemas or misconfigured destinations should not retry infinitely. For connection errors, configure backoff and retry limits to avoid hanging jobs or overloading the broker.

## 30. Common Mistakes When Testing Message Readers and Writers

| Symptom | Common Cause | Fix |
|---|---|---|
| Reader returns `null` immediately | Empty queue or receive timeout; Batch treats it as EOF. | Define batch completion/end markers or use a message-driven model. |
| Step rolls back yet messages vanish | `AUTO_ACKNOWLEDGE` acknowledged on receive. | Use suitable JMS transactions and test rollback/redelivery. |
| Output messages persist after DB rollback | JMS sends did not join the database transaction. | Use XA/JTA where appropriate or transactional outbox. |
| Duplicate messages sent after retry | Send succeeded before chunk metadata committed. | Use idempotency keys and consumer deduplication. |
| Unit tests pass yet production conversion fails | Mocks bypass real converters/brokers. | Add integration tests with real message converters and brokers. |
| Tests receive messages from other tests | Shared queues/topics without cleanup. | Use isolated destinations and post-test cleanup. |
| Tests hang | Reader waits indefinitely when queue is empty. | Configure bounded timeouts or send end markers. |
| Wrong-type messages treated as EOF | Conversion errors caught and turned into `null`. | Propagate exceptions or route rejected messages. |
| Headers lost | Reader returns only payloads without mapping metadata into items. | Use wrappers/custom converters and test headers. |
| Flaky redelivery tests | Relying on provider-specific delivery counts or timing. | Check `JMSRedelivered`, use a real broker, and poll with deadlines. |
| Wrong queue/topic semantics | Using queue tests for durable topic or selector behavior. | Test the actual destination/subscription type. |
| Writer sends partial chunk | Non-transacted sends or independent session commits. | Test partial failures, JMS transactions, and idempotency. |

## 31. Building a Test Strategy Workflow

When testing message readers/writers, work through these layers:

1. **Reader unit tests:** mock `JmsTemplate`, verify destination, payload, ordering, EOF, and exceptions.
2. **Writer unit tests:** verify `convertAndSend`, destination, invocation counts, and send failures.
3. **Converter tests:** verify JSON/text/bytes, type mappings, schema versions, and headers.
4. **Broker integration tests:** real send/receive, queues/topics, selectors, message properties, and cleanup.
5. **Transaction tests:** verify ack/commit/rollback/redelivery under the JMS transaction manager.
6. **Chunk tests:** verify read/process/write counts and behavior when a chunk fails.
7. **Restart/retry tests:** verify messages are neither lost nor duplicated outside designed semantics.
8. **Failure tests:** broker unavailable, timeouts, poison messages, DLQs, and partial sends.
9. **Idempotency tests:** resend the same event ID and verify business effects apply only once.
10. **Concurrency tests:** competing consumers, ordering, and destination isolation.

Unit tests give fast feedback; integration tests prove broker semantics. Never substitute one layer for another.

## 32. Key Points to Remember

- `JmsItemReader` receives messages via `JmsTemplate`; `JmsItemWriter` sends items to a destination via `JmsTemplate`.
- `MessageConverter` decides how Java payloads convert to `TextMessage`, `BytesMessage`, or other message types.
- Unit tests can mock `JmsTemplate` to verify destinations, receive/send counts, payloads, and exceptions.
- Readers return `null` when no messages remain; Spring Batch interprets that as EOF. A temporarily empty queue does not necessarily mean the batch finished.
- JMS `AUTO_ACKNOWLEDGE` can acknowledge messages immediately upon receive; chunk rollbacks do not automatically redeliver already-acknowledged messages.
- To include receives/acks in a chunk transaction, configure an appropriate JMS transaction manager; local JMS transactions are not automatically atomic with database transactions.
- `JmsItemWriter` sends messages per item; a mid-chunk failure can leave partial sends if no transaction covers them.
- Retries/restarts can cause duplicate publications; use stable event IDs and idempotent consumers.
- Integration tests with a real broker must verify redelivery, `JMSRedelivered`, delivery counts, selectors, DLQs, expiration, and transaction behavior.
- Queues, topics, durable subscriptions, and selectors have distinct semantics; test the exact destination type.
- Test message converters independently for schemas, types, Unicode, and header/correlation metadata.
- Use isolated destinations, bounded timeouts, and cleanup so tests stay independent and never hang.
- If continuous processing is needed, consider a message-driven architecture; `ItemReader`/EOF fits finite batches with defined endpoints better.

Testing message readers and writers must go beyond verifying a payload was received or sent. Verify converters, destinations, end conditions, acknowledgements, transactions, redeliveries, duplicates, and failure windows against a production-compatible broker. Only by combining fast unit tests with integration tests covering clear transactions and idempotency can a message-based batch handle errors and restarts without silently losing or duplicating events.
