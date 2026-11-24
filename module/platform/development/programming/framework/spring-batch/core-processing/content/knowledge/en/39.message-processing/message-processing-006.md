# Message Keys and Correlation

In a message-processing system combined with Spring Batch, a single message often carries several different identifiers. One identifier selects a partition or queue, another uniquely identifies the message, a business key represents the entity being processed, and a correlation ID links multiple messages belonging to the same workflow. These values may coincide in a simple design, but they solve different problems.

Properly distinguishing message keys and correlation helps a system route messages stably, preserve order when needed, prevent duplicate processing, trace a business workflow across multiple services, and link messages to a Spring Batch `JobExecution`. Using one ID for everything can mispartition data, break traceability, or cause duplicates when the broker redelivers messages.

## 1. Types of Identifiers in Message Processing

A message can carry the following identifier fields:

| Identifier | Purpose | Example |
|---|---|---|
| Message ID | Identifies a specific message | `msg-8f21` |
| Message key | Routes, partitions, or groups messages per broker semantics | `customer-1042` |
| Business key | Identifies a business entity | `customerId`, `orderId` |
| Idempotency key | Identifies an operation to prevent repeated execution | `payment-command-9001` |
| Correlation ID | Links multiple messages belonging to the same workflow/request | `corr-import-2026-11-15` |
| Causation ID | Indicates which message caused the current message | `msg-8f21` |
| Batch ID | Identifies a data batch or import run | `batch-customer-20261115` |
| JobExecution ID | Identifies one execution of a job in Spring Batch | ID issued by `JobRepository` |

These concepts can be represented in message headers, payloads, broker metadata, or inbox/outbox tables. Document the system contract explicitly: which fields are required, who generates them, uniqueness scope, and retention duration.

## 2. What Is a Message Key?

A message key is a value attached to a message that helps the broker or application decide how to route, partition, group, or process the message. Its exact meaning depends on the middleware.

For example, in Apache Kafka, a record key is typically used by the partitioner to choose a partition. Records with the same key are usually sent to the same partition under the partitioning strategy, allowing Kafka to preserve their ordering within that partition. A key is not necessarily unique per message; many distinct records can share the same key.

In a JMS system, the concept of a message key does not carry Kafka-style partition semantics. An application may use a message property for routing or lookup, whereas `JMSMessageID` and `JMSCorrelationID` are headers with dedicated meanings.

Therefore, do not apply Kafka key rules to every broker. Treat the key as part of a specific middleware contract and document clearly how the broker uses it.

## 3. What Is a Correlation ID?

A correlation ID is an identifier used to link related messages within the same request, business transaction, or distributed workflow. A correlation ID is typically generated at the start of the flow and propagated across downstream services or subsequent messages.

For example, a file import emits multiple messages per customer:

~~~text
Import request
  correlationId = corr-20261115-01
       |
       +--> Customer message 1
       |      messageId = msg-001
       |      customerId = C-001
       |
       +--> Customer message 2
       |      messageId = msg-002
       |      customerId = C-002
       |
       +--> Customer message 3
              messageId = msg-003
              customerId = C-003
~~~

Each message has its own message ID, yet they share the same correlation ID because they belong to one import run. This allows logs, traces, audits, and processing results to be grouped by workflow.

A correlation ID is not necessarily a message's unique key or partitioning key. It can have very high cardinality, representing a single request, file, or workflow. Using a correlation ID as a Kafka key sends all messages for that workflow into one partition; this can help ordering, or create a hot partition if a workflow has high message volume.

## 4. Distinguishing Message Key, Message ID, and Correlation ID

Identifiers are commonly used together:

~~~text
Message:
  messageId       = msg-001
  key             = customer-C001
  correlationId   = corr-import-01
  causationId     = msg-import-start
  businessKey     = C-001
  idempotencyKey  = import-01-C001
~~~

| Question | Appropriate Field |
|---|---|
| Which specific message is this? | Message ID |
| Which value should the broker route/partition by? | Message key per broker semantics |
| Which workflow does the message belong to? | Correlation ID |
| Which message produced this message? | Causation ID |
| Which business entity is affected? | Business key |
| Has this operation already been executed? | Idempotency key |

A new message ID may be generated each time a producer resends the same business command. Thus, a message ID is not always enough to prevent duplicates. An idempotency key must stay stable across retries of the same business operation.

## 5. Kafka Record Keys and Partitioning

In Kafka, a producer can send a record with a key and value:

~~~java
ProducerRecord<String, CustomerEvent> record =
        new ProducerRecord<>(
                "customer-events",
                customerEvent.customerId(),
                customerEvent);

kafkaTemplate.send(record);
~~~

With `customerId` as the key, records for the same customer are typically routed to the same partition as long as the partitioner and partition count do not change in a way that alters the mapping. This helps consumers process events for the same customer in order within a partition.

A Kafka key does not guarantee global ordering across partitions. If two customers land in two different partitions, no cross-stream ordering is guaranteed between them.

Changing the partition count can map keys to different partitions in the future depending on the partitioner. Therefore, if the application depends on long-term key-based ordering, plan for partition expansion and migration strategies.

Do not automatically use a correlation ID as the key. Choose the key according to the entity or aggregate whose events must be processed sequentially. Examples:

- Customer events: `customerId`.
- Order lifecycle: `orderId`.
- Account ledger: `accountId`.
- File import progress: `batchId` only if the entire batch requires the same partition and throughput allows it.

## 6. JMS Message IDs and JMSCorrelationID

In JMS, the provider typically assigns `JMSMessageID` to identify a sent message. `JMSCorrelationID` links a message to another message or a request/reply exchange.

A request/reply pattern can work like this:

~~~text
Requester
   |
   | Request
   | JMSMessageID = ID-REQ-01
   v
Request Queue
   |
   v
Worker
   |
   | Reply
   | JMSCorrelationID = ID-REQ-01
   v
Reply Queue
   |
   v
Requester matches reply to request
~~~

In this pattern, the reply sets its correlation ID to the request's message ID so the requester can match the right response. Some systems use an application-generated correlation ID instead of `JMSMessageID`; what matters is that both sides agree on the contract.

`JMSCorrelationID` is neither the reply's message ID nor a business key. It correlates the reply with the request. In multi-step workflows, an application correlation ID can be preserved across many messages while each message retains its own `JMSMessageID`.

## 7. Correlation in Spring Messaging

Spring Messaging represents a message with a payload and headers. Applications can pass a correlation ID as a header:

~~~java
Message<CustomerEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlationId", correlationId)
        .setHeader("messageKey", event.customerId())
        .setHeader("causationId", sourceMessageId)
        .build();
~~~

Header names in the example are application-defined. Broker adapters may map certain headers to native broker properties, but never assume custom headers pass through a broker automatically without configuration. Check the header mapping of your adapter and message converter.

Constants can prevent typos:

~~~java
public final class MessageHeaders {
    public static final String CORRELATION_ID = "correlationId";
    public static final String MESSAGE_KEY = "messageKey";
    public static final String CAUSATION_ID = "causationId";

    private MessageHeaders() {
    }
}
~~~

In larger applications, use an envelope or metadata object with an explicit schema rather than letting each producer invent header names independently.

## 8. Propagating Correlation IDs Across Workflows

A correlation ID should be created at the start of the flow if the incoming request lacks a trustworthy ID. Each service receiving a message must preserve the correlation ID when producing subsequent messages.

~~~text
API request
   |
   v
Order Service
   | correlationId = corr-123
   v
OrderCreated event
   |
   v
Inventory Service
   | correlationId = corr-123
   v
InventoryReserved event
   |
   v
Billing Service
   | correlationId = corr-123
   v
PaymentRequested event
~~~

If a service spawns an independent child workflow, it can create a new correlation ID while keeping the parent correlation ID in a separate header. Do not overwrite the parent workflow's correlation ID if you need to trace relationships between workflows.

Correlation IDs should propagate through:

- Message headers or envelopes.
- Log contexts.
- Distributed tracing contexts.
- Audit records.
- `JobParameters`/`ExecutionContext` when a message launches a batch.
- Outbox/inbox records if persisted durably.

Do not generate a new correlation ID at each step when the goal is tracking the same workflow. If separate trace spans are needed, use the tracing system's trace/span IDs while keeping the business correlation ID intact.

## 9. Causation ID and Parent-Child Relationships

A correlation ID tells you which messages belong to the same workflow; a causation ID tells you which message produced the current message.

Example:

~~~text
Message A: OrderCreated
  messageId = A
  correlationId = ORDER-FLOW-1

Message B: InventoryReserved
  messageId = B
  correlationId = ORDER-FLOW-1
  causationId = A

Message C: PaymentRequested
  messageId = C
  correlationId = ORDER-FLOW-1
  causationId = B
~~~

Correlation IDs let you query the entire workflow. Causation IDs reconstruct the causal chain. The two fields complement each other during failure analysis or auditing.

If a message is produced from multiple input messages (such as an aggregator), a single causation ID may not suffice. You can store a list of parent message IDs in metadata or a relationship table, with appropriate size and retention limits.

## 10. Combining Messages with Spring Batch Jobs

A message can instruct Spring Batch to process a file, a customer range, or a data batch. When a consumer receives the message, the application can translate message metadata into `JobParameters`.

Example:

~~~java
@Service
public class ImportJobLauncher {

    private final JobLauncher jobLauncher;
    private final Job customerImportJob;

    public ImportJobLauncher(
            JobLauncher jobLauncher,
            Job customerImportJob) {
        this.jobLauncher = jobLauncher;
        this.customerImportJob = customerImportJob;
    }

    public JobExecution launch(ImportRequest request) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", request.batchId(), true)
                .addString("inputUri", request.inputUri(), true)
                .addString("correlationId", request.correlationId(), false)
                .toJobParameters();

        return jobLauncher.run(customerImportJob, parameters);
    }
}
~~~

This example uses `batchId` and `inputUri` as identifying parameters, and `correlationId` as non-identifying metadata. The choice of identifying vs. non-identifying parameters must match `JobInstance` semantics.

If the same batch is resent, using the same identifying parameters makes Spring Batch locate the corresponding `JobInstance` and apply restart/already-complete rules. If each message is an independent import request, you need a distinct business batch ID or a suitable identifying request ID.

Do not make `correlationId` an identifying parameter merely because it is present on the message. One correlation ID can group multiple messages or multiple batches; using it as identity could cause separate jobs to collide on the same `JobInstance`.

## 11. JobParameters and JobInstance Identity

Spring Batch distinguishes `JobInstance` by job name and identifying `JobParameters`. A `JobExecution` is one execution attempt of a `JobInstance`. One `JobInstance` can have multiple `JobExecution`s if a prior run failed and was restarted.

This matters for message redelivery:

- If a message represents the same batch operation, identifying parameters must remain stable across redeliveries.
- If a message represents a new request, a new identity is required.
- A correlation ID merely links a workflow; it is not necessarily the batch identity.
- A message ID may change when a producer resends, so it is not always an idempotency key.

Example:

~~~text
Message delivery 1:
  messageId = msg-A
  batchId = BATCH-900
  correlationId = FLOW-1

Message delivery 2 (redelivery):
  messageId = msg-A or provider-specific redelivery identity
  batchId = BATCH-900
  correlationId = FLOW-1

Spring Batch:
  JobInstance = customerImportJob + batchId + inputUri
  JobExecution 1 = FAILED
  JobExecution 2 = RESTARTED
~~~

Do not add a random timestamp to identifying parameters when retrying the same message, because that creates a new `JobInstance` instead of restarting the previous instance.

## 12. Idempotency Keys and Preventing Duplicate Message Processing

Message brokers can redeliver messages, especially when a consumer finishes processing without acknowledging or loses connection before the broker records the acknowledgement. Therefore, applications must assume the same message can arrive multiple times.

An idempotency key represents a business operation that stays stable across redeliveries. Example:

~~~text
messageId       = msg-7781
businessKey     = order-900
idempotencyKey  = capture-payment-order-900
correlationId   = checkout-flow-900
~~~

If a producer retry generates a new message ID for the same payment capture operation, the idempotency key must stay the same. Consumers can use a unique constraint on the idempotency key to ensure the operation applies only once.

Example inbox table:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    message_id VARCHAR(200),
    correlation_id VARCHAR(200),
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

Within the same database transaction, the consumer records the inbox key and updates business data. If the key already exists, the message is recognized as already processed and can be acknowledged without repeating side effects.

Persist the processed marker only along with the business side effect in the same transaction. If the marker commits first while the business update fails, the message may be treated as processed even though data was never updated. If the business update commits first while the marker fails, redelivery can repeat side effects. Inbox and business updates should share the same transaction when in the same database.

## 13. A Message Key Does Not Replace an Idempotency Key

A Kafka key is normally used to partition records. It does not guarantee a message is delivered only once and is not necessarily unique per operation.

For example, all events for customer `C-001` may share the same Kafka key:

~~~text
key=C-001, value=CustomerCreated
key=C-001, value=CustomerAddressChanged
key=C-001, value=CustomerStatusChanged
~~~

The three records share the same key yet represent three distinct operations. Using the key as an idempotency key would cause the consumer to wrongly drop valid events after the first one.

Conversely, two messages with different keys can still represent the same business operation if the producer generates unstable keys. Idempotency requires a dedicated operation identifier with clear generation and retention rules.

## 14. Inbox Pattern for Consumers

The inbox pattern records received/processed messages to detect redeliveries and support audits. A typical flow:

~~~text
Broker message
     |
     v
Consumer
     |
     v
Begin database transaction
     |
     +--> Insert inbox idempotency key
     |
     +--> Apply business update
     |
     +--> Store correlation/causation metadata
     |
     v
Commit
     |
     v
Acknowledge broker message
~~~

If inserting the inbox key violates a unique constraint, the consumer knows the operation was handled previously. Clarify marker statuses: `RECEIVED`, `PROCESSING`, `COMPLETED`, or `FAILED`. A `RECEIVED` marker does not mean the business operation has completed.

For long-running processing in Spring Batch, the consumer can create a durable batch request record and then launch the job. The request table needs a unique key per batch operation so redeliveries do not launch an unintended independent batch.

Do not keep a database transaction open across an entire long-running job merely to wrap broker acknowledgement. Instead, record the request and launch state in a short transaction, then let the job manage its own chunk transactions.

## 15. Outbox Pattern When Emitting Messages from Batch

If Spring Batch updates a database and then publishes events directly to a broker, the dual-write problem can occur:

- The database commit succeeds, but publishing fails.
- Publishing succeeds, but the database transaction rolls back.

The outbox pattern writes events into an outbox table in the same transaction as business updates. A separate publisher reads the outbox and sends messages to the broker:

~~~text
Spring Batch chunk transaction
     |
     +--> Update business table
     |
     +--> Insert outbox event
     |
     v
   Commit

Outbox publisher
     |
     v
   Broker
~~~

An outbox record should store message ID, message key, correlation ID, causation ID, event type, payload, and creation timestamp. The publisher needs idempotency/retries because it may resend an event if it crashes after broker acceptance but before updating the outbox marker.

Consumers still need inbox/idempotency because outbox typically provides at-least-once publication, not automatic end-to-end exactly-once across all side effects.

## 16. Correlation ID and Distributed Tracing

A business correlation ID helps group logs and audits by workflow. Distributed tracing uses trace IDs and span IDs to represent timing relationships across operations.

The two concepts are related but not identical:

- A correlation ID can persist long-term across a business workflow and appear in databases, messages, and reports.
- A trace ID typically represents an observational trace and may change when a new trace starts or across sampling boundaries.
- A span ID identifies one operation within a trace.
- Baggage/context propagation carries metadata across service boundaries per tracing standards.

Do not replace trace IDs with business correlation IDs or vice versa. Both can be logged together:

~~~text
timestamp=...
service=customer-import
correlationId=FLOW-2026-001
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
jobExecutionId=142
batchId=BATCH-900
~~~

When receiving messages, configure instrumentation or adapters to continue trace context per W3C Trace Context/OpenTelemetry standards. Propagating a custom correlation ID alone does not automatically create a complete distributed trace.

## 17. Correlation When Aggregating Multiple Messages

A workflow can emit multiple child messages and wait for their results. A correlation ID groups messages belonging to the same set:

~~~text
Batch request corr=B-01
   |
   +--> Part 1 completed corr=B-01
   |
   +--> Part 2 completed corr=B-01
   |
   +--> Part 3 completed corr=B-01
              |
              v
        Aggregator
              |
              v
        Batch completed
~~~

An aggregator may also need an expected count, sequence number, or partition ID to know when all results have arrived. A correlation ID alone is insufficient to determine workflow completion without count or completion-marker metadata.

In Spring Integration, a correlation strategy, release strategy, and message group store can group messages. Configure group timeouts, expiry, and a persistent `MessageGroupStore` if groups must survive restarts. The correlation key must be produced consistently across messages.

Do not reuse one correlation ID across multiple independent workflows if an aggregator relies on it to group messages, or messages may mix into the same group.

## 18. Sequence Numbers and Ordering Within a Correlation

If messages in the same workflow must be processed in order, they can carry a sequence number:

~~~json
{
  "messageId": "msg-002",
  "correlationId": "FLOW-01",
  "sequence": 2,
  "eventType": "CustomerAddressChanged",
  "payload": {
    "customerId": "C-001"
  }
}
~~~

Sequences help consumers detect missing, duplicate, or out-of-order messages. However, a sequence is meaningful only if the producer defines counting scope, gap handling, and reset/versioning rules.

Kafka ordering is guaranteed only within a partition. If records with the same aggregate key go to the same partition, partition append order can support sequential processing. Consumers must still handle retries, rebalances, and idempotent side effects.

Do not infer ordering from timestamps alone. Clocks across producers can drift, and multiple messages can share the same timestamp.

## 19. Correlation and Message Redelivery

When a broker redelivers a message, the correlation ID normally stays the same because the message still belongs to the same workflow. The message ID may stay the same or change depending on the producer/provider and how the application reconstructs messages. The idempotency key must stay stable for the same operation.

A consumer should log:

- Message ID or provider delivery metadata.
- Correlation ID.
- Idempotency key.
- Delivery attempt/redelivery indicator if supplied by the broker.
- Business key.
- Batch ID and `JobExecution` ID if the message launches a batch.

If redelivery creates an unintended new `JobExecution`, inspect identifying `JobParameters` and the inbox table. Never generate a new timestamp as `JobInstance` identity on every re-receipt of the same request.

## 20. Combining Correlation with Partitioning in Spring Batch

A correlation ID can be stored in `JobParameters` or `ExecutionContext` to track steps and partitions of a batch. For example, the job receives `batchId` and `correlationId`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", request.batchId(), true)
        .addString("correlationId", request.correlationId(), false)
        .toJobParameters();
~~~

When the partitioner creates worker contexts, it can copy the correlation ID into each partition:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("partitionName", partitionName);
context.putString("correlationId", correlationId);
context.putLong("minId", minId);
context.putLong("maxId", maxId);
~~~

The worker step can use the correlation ID in logs or audits:

~~~java
@Bean
@StepScope
ItemProcessor<Customer, CustomerResult> customerProcessor(
        @Value("#{stepExecutionContext['correlationId']}") String correlationId,
        CustomerService customerService) {

    return customer -> customerService.process(customer, correlationId);
}
~~~

The correlation ID here serves traceability. Do not use it in place of a partition key or business key when their semantics differ.

## 21. Batch ID and Correlation ID

A batch ID and correlation ID may be identical in a simple system, but should be distinguished:

- Batch ID identifies a dataset or import run.
- Correlation ID links messages/operations across a distributed workflow.

One workflow can contain multiple batches:

~~~text
Correlation FLOW-77
   |
   +--> Batch CUSTOMER-01
   |
   +--> Batch ORDER-01
   |
   +--> Batch INVOICE-01
~~~

Conversely, one batch may be processed by multiple `JobExecution`s or partitions while still belonging to the same batch ID. A correlation ID can tie the batch launch request to completion events and downstream notifications.

Choosing which field forms `JobInstance` identity must reflect the batch's restart semantics. Do not use `correlationId` if one correlation can encompass multiple independent runs.

## 22. Designing a Message Envelope

A standard envelope helps producers and consumers use identifiers consistently:

~~~json
{
  "metadata": {
    "messageId": "msg-001",
    "messageKey": "customer-C001",
    "correlationId": "corr-import-01",
    "causationId": "msg-import-start",
    "idempotencyKey": "import-01-C001",
    "batchId": "batch-20261115",
    "schemaVersion": 1,
    "createdAt": "2026-11-15T10:00:00Z",
    "producer": "customer-import-service"
  },
  "payload": {
    "customerId": "C-001",
    "fullName": "An Nguyen"
  }
}
~~~

An envelope should specify contract version, nullability rules, maximum ID lengths, and propagation rules. Avoid letting arbitrary payloads overwrite validated metadata.

If the middleware has native keys/headers, adapters can map `messageKey` to the native field. `correlationId` and `idempotencyKey` can live in headers or the envelope depending on broker capabilities and storage requirements. Test round-trips through serializers/deserializers to verify no headers are dropped.

## 23. ID Generation Rules

Each ID should be generated by the component that owns its semantics:

- Producer generates the message ID per message.
- Workflow initiator generates the correlation ID for the workflow.
- Producer/command handler generates a stable idempotency key for the business operation.
- Domain entity owns the business key.
- Batch orchestration generates the batch ID for the data batch.
- Spring Batch `JobRepository` issues the `JobExecution` ID.

UUID/ULID can fit distributed IDs, though format alone does not define uniqueness scope or retention. For business keys, prefer stable domain keys. For idempotency keys, avoid generating a new random value on every retry of the same command.

Do not embed sensitive data such as email addresses, account numbers, or tokens inside a correlation ID. IDs commonly appear in logs, metrics, traces, and broker metadata, so treat them as broadly observable data.

## 24. Security and Privacy

Correlation IDs and message keys are frequently written to logs and monitoring systems. They should never contain secrets or direct personal data.

Guidelines:

- Never use access tokens, session tokens, or credentials as message keys or correlation IDs.
- Avoid putting PII in IDs when opaque identifiers can be used.
- Bound key/header lengths to prevent oversized or rejected messages.
- Validate externally supplied correlation IDs if they influence routing or queries.
- Never trust a client-supplied correlation ID to grant data access permissions.
- Restrict read permissions on inbox/outbox tables and message audits.
- Maintain retention policies for message metadata and trace data.

A correlation ID is a tracing tool, not proof of identity or authorization to access a workflow.

## 25. Testing Message Keys and Correlation

Test the contract across multiple layers:

### Unit Tests

- Message builders preserve the right message key and correlation headers.
- Correlation IDs propagate from requests to subsequent events.
- Causation IDs reference the right source message.
- Idempotency keys remain stable when retrying the same command.
- Business keys are not confused with message IDs.

### Broker Integration Tests

- Kafka records with keys land in expected partitions under test configuration.
- Records with the same key preserve ordering within a partition.
- `JMSCorrelationID` is preserved accurately in request/reply.
- Custom headers serialize/deserialize cleanly through adapters.
- Redeliveries retain metadata per contract.

### Spring Batch Integration Tests

- Messages launch jobs with stable identifying parameters.
- Redeliveries do not create unintended `JobInstance`s.
- Correlation IDs appear in step and partition logs/audits.
- Restarting the same batch preserves batch ID and input identity.
- Job completion events preserve the original correlation ID.
- Inbox/outbox do not produce duplicate side effects.

Do not test only in-memory `Message` objects. Run integration tests with a real broker or suitable embedded/test container to verify native header mappings and delivery semantics.

## 26. Example Consumer Launching a Batch from a Message

A listener can translate a message payload into `JobParameters`:

~~~java
@Component
public class ImportRequestListener {

    private final ImportJobLauncher launcher;
    private final InboxService inboxService;

    public ImportRequestListener(
            ImportJobLauncher launcher,
            InboxService inboxService) {
        this.launcher = launcher;
        this.inboxService = inboxService;
    }

    @JmsListener(destination = "customer-import-requests")
    public void receive(
            ImportRequest request,
            @Header(name = "correlationId", required = false)
            String correlationId,
            @Header(name = "idempotencyKey")
            String idempotencyKey) throws Exception {

        inboxService.executeOnce(idempotencyKey, () ->
                launcher.launch(request.withCorrelationId(correlationId)));
    }
}
~~~

This is an illustrative skeleton; how JMS headers are bound, acknowledgement mode, transactions, and exception handling must match listener container configuration. If the listener acknowledges the message before the batch request is durably saved, the request can be lost if the application crashes. If the listener holds a transaction open too long while the job runs, it may tie up broker/database resources unnecessarily.

A common design writes the request to an inbox table in a short transaction, commits, and then acknowledges the message. A separate dispatcher launches the job for unlaunched requests. Request states must allow recovery if the process stops between saving the request and calling `JobLauncher`.

## 27. Tracking Batch Status via Correlation

A job can emit events when it starts, completes, or fails. Each event preserves the correlation ID and batch ID:

~~~json
{
  "eventType": "BatchCompleted",
  "messageId": "msg-complete-01",
  "correlationId": "corr-import-01",
  "causationId": "msg-import-request-01",
  "batchId": "batch-20261115",
  "jobExecutionId": 142,
  "status": "COMPLETED",
  "processedCount": 25000
}
~~~

Downstream systems can tie completion events back to the initial request and intermediate events. If the job restarts, the `JobExecution` ID may change, while the batch ID/correlation ID stay the same if it belongs to the same workflow.

Never emit `BatchCompleted` before data has genuinely committed and all required outputs are ready. If publishing events within the same database transaction, use an outbox to avoid dual writes. If events are emitted in a post-commit listener, handle the case where publishing fails after the job has already completed.

## 28. Common Mistakes

**Using a message key as a message ID:** many valid messages can share the same key, especially when the key drives Kafka partitioning. Never use keys for deduplication unless semantics guarantee per-operation uniqueness.

**Using a correlation ID as an idempotency key:** one workflow can contain many distinct operations. Use a dedicated idempotency key per operation.

**Generating a new correlation ID in every service:** messages from the same workflow become fragmented across logs and audits. Propagate the initial ID or explicitly record parent correlation.

**Using a correlation ID as a Kafka key without considering partition load:** a large workflow can funnel into one partition. Choose keys by the aggregate requiring ordering.

**Using a message ID as JobInstance identity:** redelivery can produce unstable identity depending on the producer. Choose identifying `JobParameters` based on the batch operation.

**Adding a new timestamp to identifying parameters on retry:** creates a new `JobInstance` instead of restarting the previous `JobInstance`.

**Dropping correlation headers across message converters:** traces break when adapters fail to map custom headers. Test round-trips with the broker.

**Acknowledging before a request is durably stored:** messages can be lost if the consumer crashes. Use inbox/request records and recovery.

**Treating broker delivery as exactly-once:** redelivery can still happen. Use inboxes, unique constraints, and idempotent side effects.

**Writing to an outbox without deduplicating at the publisher/consumer:** a publisher crash after sending can resend events. Consumers still need idempotency.

**Putting PII or secrets in correlation IDs:** metadata appears widely in logs/traces. Use opaque IDs.

**Using correlation for authorization:** correlation IDs do not authenticate callers or prove permission to access a workflow.

## Conclusion

Message keys, message IDs, business keys, idempotency keys, and correlation IDs solve different problems. Keys can drive partitioning/routing per broker semantics; message IDs identify individual messages; business keys identify entities; idempotency keys prevent repeated operations; correlation IDs link messages in the same workflow; causation IDs record causal lineage. When combining messaging with Spring Batch, choose identifying `JobParameters` according to the batch operation and restart semantics, propagate correlation IDs through headers/`ExecutionContext`/logs, and use inbox/outbox to handle redeliveries and dual writes. Test header mapping against real brokers, key-based ordering, `JobInstance` restarts, and duplicate deliveries so identifiers remain consistent from request receipt through batch completion.
