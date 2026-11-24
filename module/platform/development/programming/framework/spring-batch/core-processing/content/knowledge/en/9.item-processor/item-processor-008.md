# Do not let a processor perform side effects that are hard to retry in Spring Batch

`ItemProcessor` sits between the reader and the writer in chunk-oriented processing. Its main task is to receive an input item, validate or transform it, and return a result for the writer to write. Because the processor is called during chunk processing, its design directly affects the job's retry, rollback, and restart capabilities.

A retry-friendly processor should perform a transformation that can be repeated without causing additional external effects. If a processor sends email, debits money, calls an API that creates data, writes a file, or emits a message, reprocessing can create duplicate side effects. **Do not put side effects that are hard to undo or hard to repeat safely in `process()`**. Keep the processor focused on producing results and move durable write operations to a place with a suitable transaction or deduplication mechanism.

## 1. The role of ItemProcessor

In chunk processing, Spring Batch reads items, passes each item through the processor if one is configured, and then hands the remaining outputs to the writer:

```text
ItemReader
    |
    v
Input item
    |
    v
ItemProcessor
    |
    +---- returns an object -> put into the output chunk
    |
    +---- returns null   -> filter the item out of the output
    |
    v
ItemWriter
    |
    v
Commit chunk transaction
```

The basic interface:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

The processor receives an item of type `I` and returns an item of type `O`. The two types can be the same if it only normalizes or updates data, or different if it converts from source data to a command/DTO for the next step.

Tasks suited to a processor include:

- Normalizing strings, dates, or business codes.
- Computing values based on the input data.
- Mapping a source entity to a DTO or command.
- Checking business conditions and returning a classified result.
- Filtering items that do not need processing by returning `null`, when that is a valid business rule.

The processor can throw an exception if an item cannot be processed. The Step will apply the configured transaction and fault-tolerance policy to decide whether to retry, skip, or fail.

## 2. What is a side effect?

A side effect is an observable change outside a function's return value. In a processor, the following actions are side effects:

- Sending email or SMS.
- Calling a `POST`, `PUT`, or `PATCH` API to create or update data in another system.
- Debiting money, creating a payment transaction, or placing an order in an external service.
- Sending a message to Kafka, RabbitMQ, or another queue.
- Writing a file, uploading an object, or updating a database that does not participate in the chunk's transaction.
- Updating a shared cache, a static variable, a global counter, or the state of an external service.
- Calling an operation that is billed or creates a new resource each time it is called.

Not every I/O operation is a side effect. A query that only reads reference data can be appropriate in a processor, but the result needs to be stable if the same item is processed again. For example, looking up the current exchange rate twice may give different results; if that result affects the amount written out, it should be tied to a clear point in time or data version.

The point to care about is whether the effect is rolled back together with the chunk, and whether a repeated execution can be recognized. Calling an external system usually does not participate in Spring Batch's database transaction, so a chunk rollback cannot undo that call on its own.

## 3. Why can the processor be called again?

A batch job does not guarantee that each `process()` call happens exactly once over the whole business lifecycle. Processing can be retried when there is an error, a chunk rollback, or a job restart. The exact behavior depends on the step configuration, fault tolerance, and when the error occurs.

Situations that can lead to reprocessing include:

- A chunk fails and is rolled back; some of the chunk's items may have to be processed again.
- An error in the writer prevents the chunk from committing; the step may retry the chunk according to the configured policy.
- The job fails and is then restarted from a committed checkpoint; items that were not committed can appear again.
- A test or operational action re-runs the same unit of work under an appropriate configuration.
- With a fault-tolerant step, the `processorNonTransactional()` configuration can require the processor to be called again when an item is reprocessed after a rollback.

Spring Batch has a mechanism for buffering/caching processor results in some fault-tolerant processing paths to avoid recomputation on rollback. However, you should not rely on that internal cache as an exactly-once guarantee. The cache does not replace durability across a restart or deduplication capability in an external system; configuration and execution circumstances can also cause the processor to be called again.

For example, a processor that calls a payment service:

```text
Read Order-42
    |
    v
Processor calls payment API -> payment succeeds
    |
    v
Writer writes the result -> database error
    |
    v
Chunk rollback
    |
    v
Item is reprocessed
    |
    v
Processor calls payment API again
```

If the API has no idempotency key, the order may be charged twice. A database transaction rollback cannot undo a payment that has already completed in the payment system.

## 4. Example of a processor with a side effect that is hard to retry

The following code illustrates a risky design:

```java
public class ChargeOrderProcessor
        implements ItemProcessor<Order, PaymentReceipt> {

    private final PaymentClient paymentClient;

    public ChargeOrderProcessor(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    @Override
    public PaymentReceipt process(Order order) {
        // Side effect: each call may create a new charge.
        return paymentClient.charge(order.getId(), order.getTotal());
    }
}
```

The problem is that `process()` both decides the output data and performs the payment transaction. If the same order is processed again, the API may create an additional charge. The processor is also hard to test independently because every call depends on the payment service and may change real data.

Similar ways of writing it are also risky:

```java
@Override
public Notification process(Order order) {
    emailClient.sendReceipt(order);       // send email immediately
    messageBroker.publish(order);         // publish message immediately
    auditRepository.save(new Audit(...)); // write to a DB outside the transaction
    return toNotification(order);
}
```

When an operation in the chunk fails, effects that already happened in external systems may remain intact. A subsequent retry or restart can repeat them.

## 5. Designing the processor as a repeatable transformation

A processor should focus on computing and mapping data. With the same input and the same reference data/version, the result should be stable and create no external changes.

For example, instead of charging directly in the processor, create a command that describes the payment request:

```java
public record PaymentCommand(
    String eventId,
    String orderId,
    BigDecimal amount
) {}

public class PaymentCommandProcessor
        implements ItemProcessor<Order, PaymentCommand> {

    @Override
    public PaymentCommand process(Order order) {
        if (order.isCancelled()) {
            return null; // filter according to a business rule
        }

        String eventId = "payment:v1:" + order.getId();
        return new PaymentCommand(
            eventId,
            order.getId(),
            order.getTotal()
        );
    }
}
```

The processor only creates an object that describes the work. `eventId` is created from a stable business identifier and the operation version; it will be used as a deduplication key at the write step or in the consumer. If an order can validly be paid multiple times, the key needs to include additionally a payment-attempt identifier or request code so that two different transactions are not merged by mistake.

A repeatable transformation also needs to avoid depending on uncontrolled changing state. If the processor needs exchange-rate information, a policy, or a price list, pass the version/point in time to use through the input or `JobParameters`, or read a consistent snapshot. Do not call a service that changes over time and then assume a retry will receive exactly the same result as the first attempt.

## 6. Moving write operations into ItemWriter

`ItemWriter` is the component responsible for writing a group of the chunk's outputs. Writes to a database that participate in the same transaction as the step can be committed or rolled back together with the chunk if the correct transaction manager and the same transactional resource are used.

For example, a writer that saves a payment request to an outbox table:

```java
@Bean
ItemWriter<PaymentCommand> paymentOutboxWriter(
        PaymentOutboxRepository outboxRepository) {
    return chunk -> {
        List<PaymentOutboxEvent> events = chunk.getItems().stream()
            .map(command -> new PaymentOutboxEvent(
                command.eventId(),
                command.orderId(),
                command.amount(),
                "PENDING"
            ))
            .toList();

        outboxRepository.saveAll(events);
    };
}
```

In a real configuration, `PaymentOutboxEvent` and the repository are the application's own models. The outbox table needs a unique constraint on `event_id` so that one logical request is not created as multiple rows. If the writer can be called again, the write approach should use insert-if-absent/upsert or handle duplicate keys according to a defined rule, rather than letting a repeated write create an additional event.

The writer can also be called again on chunk rollback or retry. Therefore, moving a side effect from the processor to the writer does not automatically produce exactly-once. The benefit of the writer is that it is a clear chunk-write boundary and can participate in a transaction; safety still requires an appropriate transaction and idempotency.

## 7. Transactional outbox for effects on external systems

If a job needs to send a message, call an API, or create a transaction in another service, a common pattern is the **transactional outbox**. Instead of performing the side effect right in the processor, the job writes an event record to the outbox in the same transaction as the related business data.

General flow:

```text
ItemReader
    |
    v
ItemProcessor
  creates PaymentCommand (no charge)
    |
    v
ItemWriter
  writes business data + outbox event
    |
    v
One local database transaction commits
    |
    v
Outbox dispatcher reads PENDING events
    |
    v
Calls payment API / publishes message
    |
    v
Marks the event as sent
```

If the business data and the outbox are written in the same database transaction, both commit or roll back together. After the commit, a separate dispatcher reads the outbox and sends the request out. If the dispatcher stops between sending and marking as sent, the event can be sent again; therefore the receiving system still needs idempotency by `eventId`.

The outbox helps avoid losing a request between the moment of committing the data and the moment of publishing. It generally provides an at-least-once delivery model, not a guarantee that a message reaches the consumer exactly once. The consumer or target API needs to store an idempotency key to detect duplicate deliveries.

For example, the consumer can store processed `eventId`s in a table with a unique constraint. When it receives the same event again, the consumer recognizes that the event has already been applied and returns an appropriate result without performing the side effect again.

## 8. Idempotency when a side effect cannot be avoided

An operation is idempotent if performing it multiple times with the same request identifier still produces the same business result as performing it once. Idempotency is an important layer of protection when the system must retry or reprocess.

Commonly used approaches:

- Send a stable `Idempotency-Key` to the target API, for example `payment:v1:ORDER-42`.
- Create a unique constraint on the business key or event ID in the target database.
- Use upsert instead of a blind insert when the write operation can be repeated.
- Store the event's processing state and check the state before applying the effect.
- Use a transaction ID created by the source system and propagate it across retries.

Do not use a new UUID generated on each `process()` call as the idempotency key. If a retry generates a different UUID, the target system will treat them as two independent requests. The key must be created from a stable identifier of the business unit or persisted durably before performing the side effect.

Idempotency also needs a defined scope. An order can have multiple valid payments; a key based only on `orderId` could block a new transaction as well. Combine the order ID with a payment attempt ID or operation version according to the business model.

## 9. Should a read-only service be called in the processor?

A processor sometimes needs to look up data to compute a result. For example, fetching customer information, classification rules, or limits. Read-only operations can be appropriate, but you still need to consider repeatability and stability.

A read API call may return a different result on a retry if the data changes between the two points in time. This is not a direct side effect, but it can cause the same item to produce different results. If correctness requires the same snapshot, you should:

- Pass the point in time or data version to use into the job.
- Read reference data from an immutable snapshot.
- Store the looked-up value in the input or in a suitable durable store.
- Use a cache with a clear scope and expiration when acceptable.
- Handle timeout errors with limited retry, and do not arbitrarily convert errors into empty results.

Do not call a service that has side effects under the name of a “lookup” or “validate” function. Make the service's contract clear: read-only, state-changing, billed, or able to create new resources.

## 10. Listeners are not an exactly-once mechanism

Spring Batch has listeners such as `ItemProcessListener`, `ChunkListener`, and `StepExecutionListener` to observe the processing lifecycle. They are suited to logging, metrics, tracing, or recording diagnostic information. However, a listener callback does not by itself guarantee that an external operation is performed exactly once.

For example, sending email in `afterProcess()` still risks sending it again if the item is reprocessed. Sending a message in `afterChunk()` can avoid some cases before the commit, but the process can still stop after the database commits and before the message is sent; if the callback is executed again in another situation, duplicates can also arise. Sending email in `afterStep()` can have a similar problem when the step completes but the application stops before it finishes recording or sending.

Use listeners for observation and controlled lifecycle hooks. For business effects that must not be lost, record the durable intent in a transaction (such as an outbox), and then dispatch it with a component that has retry and idempotency.

## 11. Distinguishing processor, writer, and business service

A clear way to organize things is to have the processor produce a result or command, the writer store the result/intent, and a dedicated service communicate with external systems using a durable mechanism.

| Component | Suitable responsibility | What to avoid |
| --- | --- | --- |
| `ItemReader` | Fetch items from the source and maintain recoverable read state. | Consuming data that cannot be re-read without a suitable checkpoint. |
| `ItemProcessor` | Validate, compute, normalize, map, and filter. | Sending email, charging, publishing, or writing external resources outside the transaction. |
| `ItemWriter` | Write the chunk's output within a transaction or via an idempotent operation. | Assuming the writer is called only once. |
| Outbox dispatcher | Send the stored events and update the dispatch state. | Sending without idempotency or without persisting progress. |
| Consumer/target API | Apply the business effect with a deduplication key. | Treating each received request as a completely new operation. |

This separation makes it possible to test the processor with simple input/output, test the writer with a transaction test, and test the dispatcher separately for retry, timeout, and duplicate delivery.

## 12. Handling errors when the side effect has already happened

A tricky situation is when the external system has performed the operation but the application did not receive a response. For example, the payment API has charged successfully but the connection times out before returning the result. The application does not know whether the transaction succeeded.

You should not immediately send a new request with a different ID. Use the same idempotency key to query or resend the request. If the target API supports looking up status by request ID, verify before deciding to create another transaction.

For a system that does not support idempotency, you may need a reconciliation step by business code, transaction status, or a compensation process. There is no general way to roll back a side effect that has already been committed in an external system merely by rolling back Spring Batch's transaction.

## 13. Testing the processor and retry capability

A purely transformational processor is easy to test because it needs no database or external service. A test can check valid input, filtered input, and invalid input:

```java
class PaymentCommandProcessorTest {

    private final PaymentCommandProcessor processor =
        new PaymentCommandProcessor();

    @Test
    void mapsOrderToStablePaymentCommand() throws Exception {
        Order order = new Order("ORDER-42", new BigDecimal("125.00"));

        PaymentCommand first = processor.process(order);
        PaymentCommand second = processor.process(order);

        assertThat(first).isEqualTo(second);
        assertThat(first.eventId()).isEqualTo("payment:v1:ORDER-42");
        assertThat(first.amount()).isEqualByComparingTo("125.00");
    }
}
```

The test calls the processor twice with the same input to confirm that the transformation creates no external effect and gives a stable result. If the processor needs a read-only dependency, you can mock that dependency to confirm how the lookup is done; do not mock a side effect and then consider deduplication in production proven.

For the writer/outbox, you should test that:

- The output is written within an appropriate transaction.
- Two writes with the same `eventId` do not create two business events.
- A chunk rollback does not leave an outbox event without the corresponding business data.
- The dispatcher can resend after a timeout without creating a duplicate effect at the consumer.
- An event that was sent but not yet marked complete can be resent safely.

For an integration job, simulate a writer failure after the processor has run to confirm that the processor does not send side effects directly. Check restart after a chunk rollback and reconcile the number of events in the outbox with the number of committed business units.

## 14. Common mistakes

**Calling an API that creates data in `process()`:** reprocessing can create multiple resources. Create a command and store the intent in an outbox, or use an idempotent API.

**Sending email directly in the processor:** email does not roll back with the chunk transaction. Write the send request to an outbox and let a dispatcher send after the commit.

**Thinking that moving the side effect to the writer is enough:** the writer can also be called again after a rollback/retry. You need a transaction and idempotency.

**Using a new UUID for each retry:** the target system does not recognize the requests as the same operation. Create the key from a stable business identifier.

**Relying on the processor cache to guarantee once-only:** the cache is a processing detail in some fault-tolerant situations, not a durable mechanism or an exactly-once guarantee.

**Sending messages in a listener:** a listener does not by itself provide a distributed transaction or exactly-once. Use an outbox for events that need to be published reliably.

**Using reference data that changes over time:** a retry can produce a different result for the same input. Use a snapshot, a version, or a clear business point in time.

**Swallowing side-effect errors:** if the API fails but the processor still returns a successful result, the job may mark the item as processed even though the business effect has not happened. Represent the error and retry/reconcile under a clear contract.

## 15. How to design a chunk job that can retry safely

When building a job, start by determining which effects are computations and which change external state. Put validate, normalize, calculate, and map operations in the processor. Keep the input/output stable, avoid modifying shared objects, and avoid depending on data without a version.

Next, determine where data is written. Database changes that need to commit with the chunk should be done in the writer and participate in the correct transaction manager. If you need to send a message or email, or call an API after the data is saved, write an outbox event in the same transaction and then dispatch separately. If you must call the target system directly, use a stable idempotency key and the ability to look up the result after a timeout.

Finally, try the rollback, retry, skip, and restart scenarios. In particular, check the cases where the external side effect succeeded but the application lost the response, the writer fails after the processor has run, or the dispatcher stops after publishing but before marking the event complete. Monitor the number of retries, the number of pending events, duplicate keys, and reconciliation results.

A processor should focus on producing output that can be recomputed. When side effects are managed with transactions, an outbox, and idempotency at the right boundaries, a Spring Batch job can retry or restart without inadvertently repeating business effects that are hard to undo.
