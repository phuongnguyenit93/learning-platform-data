# Limits of Exactly-Once When Calling Services or Producing Side Effects Outside Kafka

Kafka transactions and exactly-once semantics (EOS) enable an application to read records from Kafka, process them, and write result records back to Kafka within a consistent transaction. However, this guarantee has a clear boundary: Kafka can commit output records together with consumer offsets in a Kafka transaction, but it cannot automatically roll back an HTTP call, an independent database transaction, a sent email, or a written file.

This is a critical boundary when building Spring Cloud Stream applications. A function may run inside a Kafka transaction and then call a payment service or update a database. If the Kafka transaction rolls back after the external side effect has already completed, the input message can be redelivered and the service-calling code will run again. To avoid duplicate side effects, the application must coordinate with external systems using idempotency, inbox/outbox, sagas, or an appropriate reconciliation mechanism.

## 1. What does Kafka exactly-once guarantee?

With the consume-process-produce model, a Kafka transaction can combine two actions:

1. Writing output records to one or more Kafka topics.
2. Recording offsets of the processed input records in the same transaction.

Both actions commit or abort together. If the transaction commits, downstream consumers using `read_committed` isolation can read the committed output records and input offsets are updated. If the transaction aborts, uncommitted output records are not visible to `read_committed` consumers and input offsets do not advance as a successful transaction.

Example of a processor receiving `OrderCreated` and emitting `OrderAccepted`:

~~~text
Kafka input topic
      |
      v
Consumer reads record
      |
      v
Process inside listener transaction
      |
      +----> Write output record to Kafka transaction
      |
      +----> Write input offset to same transaction
      |
      v
Commit transaction
      |
      +----> Output record is published
      +----> Input offset is updated
~~~

The key point to understand properly is that EOS protects the observable Kafka outcome of the read-process-write cycle. It does not mean the handler function is only ever invoked once in every situation. When a transaction rolls back, the input record can be read and processed again. Therefore, processing code can still execute multiple times; Kafka outputs from aborted transactions are simply withheld from `read_committed` consumers.

Kafka transactions do not cover systems that do not participate in that transaction. HTTP APIs, standalone databases, SMTP, object storage, filesystems, or other message brokers do not automatically become part of a Kafka transaction.

## 2. Enabling the transactional binder in Spring Cloud Stream

The Kafka Binder can enable transactions by setting a non-empty `transaction-id-prefix`:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-processor-instance-1-
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
~~~

The value `orders-processor-instance-1-` is only an example. Each running instance of the application must have a unique transaction ID prefix; in containerized environments, use a stable value that differs per instance/pod. If two instances share the same prefix, producers can fence each other and cause transactions to fail.

In a processor application, the consumer starts the transaction. Records sent from the consumer thread via a producer belonging to the same transactional producer factory can join that transaction. When the listener completes normally, the container sends the offset into the transaction and commits. If the listener throws an exception, the transaction rolls back.

Example function processing and emitting output:

~~~java
@Bean
Consumer<OrderCreated> processOrder(StreamBridge streamBridge) {
    return event -> {
        OrderAccepted accepted =
            new OrderAccepted(event.eventId(), event.orderId());

        boolean sent = streamBridge.send("processOrder-out-0", accepted);
        if (!sent) {
            throw new IllegalStateException("Output binding rejected the event");
        }
    };
}
~~~

When binder transactions are properly enabled and the `StreamBridge` call executes on the consumer thread, sending output can join the consumer-initiated Kafka transaction. If multiple binders or different producer factories exist, verify that the bindings use the intended binder and transaction manager.

Per-binding producer properties are ignored when the transactional binder uses the shared producer factory; producer configuration for the transactional binder lives under `spring.cloud.stream.kafka.binder.transaction.producer`. Check the documentation for your Spring Cloud Stream version before copying normal producer properties to a transactional binder.

## 3. Downstream consumers need to read committed records

Downstream consumers need `isolation.level=read_committed` if they should only see records from committed transactions:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

The binding name in the example is `processOrder-in-0`; actual configuration must be placed on the consumer binding that needs to read transactional output. With `read_uncommitted`, a consumer can see records from uncommitted or aborted transactions. When building a processor chain relying on EOS, configure proper isolation on downstream consumers.

`read_committed` does not turn a database or HTTP API into a Kafka transactional resource. It only controls which Kafka records are exposed for reading.

## 4. Why can external non-Kafka service calls be repeated?

Suppose a consumer reads `PaymentRequested`, calls a payment API, and then commits the Kafka transaction. There is a failure window:

~~~text
1. Kafka delivers PaymentRequested
2. Listener starts Kafka transaction
3. Application calls payment API
4. Payment service charges funds successfully
5. Application fails before Kafka transaction commits
6. Kafka transaction rolls back
7. Input offset is not committed
8. Kafka redelivers PaymentRequested
9. Listener calls payment API again
~~~

Kafka cannot undo the charge performed in step 4. If the payment API does not support idempotency, the second call can charge again even though the Kafka output from the first attempt was aborted.

Another common scenario: the application sends an HTTP request, the external service succeeds, but the response is lost or times out. The application cannot be sure whether the operation succeeded. Retrying with a fresh request can duplicate the side effect. Not retrying can drop the operation if the request never actually arrived.

This is the ambiguous outcome problem between two independent systems. Kafka transactions cannot solve it because the HTTP service does not participate in the same transaction.

## 5. Failure windows when writing to a database

Suppose a consumer reads a Kafka event and then updates a database:

| Failure Timing | Possible Outcome |
|---|---|
| Before DB commit | DB rolls back; Kafka may redeliver the event |
| After DB commit but before Kafka offset commit | DB has already changed; Kafka redelivers the event and risks applying the change again |
| Kafka offset commits before DB commit | Application may lose the DB side effect if the process crashes before DB commit |
| DB commit succeeds but Kafka commit response is lost | Application may not know whether Kafka committed; requires duplicate-safe handling |

Commit ordering can reduce certain risks, but it does not create an atomic transaction across two systems. If the DB commits first, crashing before Kafka offset commit leads to redelivery. If the Kafka offset commits first, crashing before DB commit can lose the DB update. Only a distributed transaction protocol supported by both systems can coordinate an atomic commit; many real-world systems do not support or prefer not to operate 2PC.

Spring transaction synchronization or coordinating multiple transaction managers can control commit ordering, but it does not turn two independent transaction managers into a distributed transaction capable of atomic rollback if the process or network fails between commits.

## 6. Idempotency: repeating the same request produces no extra side effects

Idempotency is the property where executing the same operation multiple times with the same identifier does not alter the final outcome after the first execution. For example, processing `eventId` `evt-1001` a second time does not create another charge or another loyalty-point credit.

For external services, use a stable idempotency key derived from the event ID or business operation ID:

~~~java
paymentClient.charge(
    new ChargeRequest(orderId, amount),
    event.eventId()
);
~~~

An HTTP client can send `eventId` in the `Idempotency-Key` header:

~~~http
POST /payments
Idempotency-Key: evt-1001
Content-Type: application/json
~~~

The payment service must store the key and processing result atomically with the payment action. When receiving the same key again, it returns the stored result instead of creating a new charge. If the same key arrives with a different payload, the service should reject it to catch key-reuse bugs.

Principles:

- Use a stable `eventId` or `operationId` across all retries.
- Do not generate a new UUID on each service call retry.
- The same key must represent the same operation and the same meaningful payload.
- The receiving service must retain the key, status, and result long enough to cover the retry/replay window.
- If the external service does not support idempotency, use reconciliation or a saga rather than assuming retries are safe.

Idempotency does not stop requests from being sent multiple times; it ensures repeated deliveries yield the same business outcome.

## 7. Inbox pattern for consumers writing to a database

The inbox pattern records that an event has been processed within the same database transaction as the business mutation. The inbox table has a unique constraint on the event ID:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

The consumer opens a DB transaction, tries to insert the event ID first, and executes the side effect only if that insert succeeds:

~~~java
@Transactional
public void apply(OrderPaid event) {
    boolean firstDelivery =
        inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return; // Event was already applied in a previous delivery
    }

    orderRepository.markPaid(event.orderId(), event.amount());
}
~~~

`insertIfAbsent` must be enforced by a database unique constraint; do not merely run `SELECT` followed by `INSERT` as two separate statements because two concurrent consumers could both pass the check. Use `INSERT ... ON CONFLICT DO NOTHING` or the database's equivalent statement.

If updating the order fails, the DB transaction rolls back both the inbox row and the business mutation. When Kafka redelivers the event, the consumer can retry. If the DB commits successfully but the Kafka offset has not committed, the event is redelivered; next time `insertIfAbsent` returns `false` and the consumer skips the already completed side effect. When the listener exits normally, the offset can advance.

This pattern achieves idempotent processing at the database even though the Kafka offset and DB do not share one transaction. It does not make the callback run only once; it guarantees repeated executions do not apply the DB side effect again.

## 8. Outbox pattern for databases and emitted events

Another problem arises when an application both updates a DB and emits a Kafka event. If the DB commits successfully but the Kafka publish fails, DB state and events diverge. If Kafka publishes first and the DB then rolls back, downstream consumers may receive an event for a change that does not exist.

The outbox pattern resolves dual-writes by storing the business change and the event record to emit in the same DB transaction:

~~~text
DB transaction
   |
   +--> UPDATE orders
   |
   +--> INSERT outbox_event
   |
   +--> COMMIT

Outbox relay
   |
   +--> Read unsent records
   |
   +--> Publish to Kafka
   |
   +--> Mark as sent
~~~

Example schema:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

The service writes the order and outbox entry in the same transaction:

~~~java
@Transactional
public void confirmOrder(Order order) {
    orderRepository.save(order);
    outboxRepository.insert(
        OutboxEvent.from(order.eventId(), order.id(), "OrderConfirmed", order)
    );
}
~~~

A relay or CDC connector reads the outbox and publishes to Kafka. If the relay publishes successfully but crashes before marking `published_at`, it may publish the same event again. Therefore, the outbox guarantees not losing the intent to publish when the DB commits, while the relay still typically exhibits at-least-once semantics. Consumers need idempotency/inbox keyed by `eventId`.

The outbox does not automatically create exactly-once between the DB and Kafka; it turns a dual-write into one DB transaction plus a publish pipeline that can be retried and deduplicated.

## 9. Calling HTTP APIs: idempotency, timeouts, and reconciliation

When a consumer calls an external service, design around an operation ID:

1. Determine `eventId` or generate `operationId` once and persist it durably.
2. Send `operationId` as the idempotency key on every retry.
3. Have the external service store the key and outcome atomically with its side effect.
4. On timeout, retry with the same key or query status by key.
5. If the outcome remains unclear, transition to a pending/reconciliation state instead of issuing a new request with a different key.

Pseudo-code example:

~~~java
public PaymentResult charge(OrderCreated event) {
    String operationId = event.eventId();

    try {
        return paymentClient.charge(
            event.orderId(),
            event.total(),
            operationId
        );
    }
    catch (SocketTimeoutException timeout) {
        return paymentClient.findByIdempotencyKey(operationId)
            .orElseThrow(() -> new PaymentOutcomeUnknownException(operationId));
    }
}
~~~

Not every service supports idempotency keys or status lookups. If a provider lacks these capabilities, the application may need to persist operation state, cap retries, require manual reconciliation, or use a compensating workflow. You cannot guarantee exactly-once for an API merely by wrapping an HTTP call inside a Kafka transaction.

## 10. Sagas and compensating actions

When a business workflow spans multiple independent services, you can use a saga: each step commits locally in its own service; if a later step fails, the system triggers a compensating action to bring the business state back to an acceptable condition.

Order placement example:

| Step | Side Effect | Possible Compensating Action |
|---|---|---|
| Reserve inventory | Decrement available stock | Release inventory |
| Capture payment | Create charge | Refund payment |
| Create shipment | Schedule delivery request | Cancel shipment if still permitted |

A saga does not roll back external service history like a shared DB transaction. It initiates a new business workflow to compensate for side effects that already occurred. Saga steps also require idempotency because commands/events can be redelivered.

For payments, a refund is a new transaction with its own operation ID linked to the original charge. Do not delete records or pretend the original charge never happened.

## 11. Non-database side effects

Other side effects also need idempotency or reconciliation strategies:

| Side Effect | Risk on Retry | How to Reduce Duplication |
|---|---|---|
| Sending email/SMS | Recipient receives multiple identical copies | Provider supports idempotency; store notification ID and send status; reconcile status |
| Writing files/object storage | Creates multiple objects or overwrites data | Use stable object keys derived from `eventId`, conditional writes, and checksums |
| Provisioning cloud accounts/resources | Creates duplicate resources for the same purpose | Use client tokens/idempotency tokens and look up by operation ID |
| Granting permissions or sending device commands | Applies command multiple times or flips state | Use command IDs, versions, and idempotent operations; persist results |
| Sending webhooks | Receiver processes the same event multiple times | Send event ID, require receiver deduplication, and retry with backoff |

If an operation cannot be made idempotent and has no outcome lookup API, consider manual confirmation or reconciliation workflows. Some side effects, such as an email already accepted by SMTP, cannot be recalled by a Kafka rollback.

## 12. Why isn't transaction synchronization a distributed atomic commit?

Spring for Apache Kafka supports synchronizing a Kafka transaction with another transaction manager. For instance, a DB transaction may commit first, followed by the Kafka transaction committing; or the application may order them differently.

Commit-order synchronization helps, yet still leaves gaps:

- DB commits successfully, process dies before Kafka commits: DB is mutated, while Kafka may redeliver the event.
- Kafka commits successfully before DB commit: if the DB commit fails, Kafka output has already been published.
- Second transaction manager fails to commit after the first already committed: an exception cannot roll back the previously committed transaction.

Therefore, do not describe using two transaction managers or nested `@Transactional` as an exactly-once guarantee across a DB and Kafka. If both systems genuinely support the same distributed transaction protocol and your organization accepts the operational cost, 2PC/XA can be evaluated for that specific case. For most event-driven applications, inbox/outbox and idempotency are easier to operate and recover.

## 13. Retries in the transactional binder

Retries can still cause listener code to execute again. With the transactional Kafka Binder, an exception in the listener rolls back the transaction; the input record can be redelivered. Retries must be configured according to the container's after-rollback mechanism.

Kafka Binder documentation notes that standard binder retry and dead-lettering mechanisms do not behave the same way as in non-transactional mode. When the transactional binder is enabled, retries are coordinated post-rollback by `DefaultAfterRollbackProcessor`; dead-letter publication is also performed during post-rollback handling. Check retryable exceptions, attempt counts, backoff, and DLQ configuration for your Spring Cloud Stream version.

Do not infinitely retry an unrecoverable business error. For permanent data errors, route to an error/DLQ stream after a configured number of attempts and preserve the event ID for investigation. Whether using container-level or application-level retries, side effects outside Kafka must still be idempotent.

## 14. Reference architecture patterns

### Kafka-to-Kafka processor

- Use the transactional binder.
- Consumer and output bindings use the same transactional producer factory/binder.
- Producer sends occur on the consumer thread to join the transaction.
- Downstream consumers use `read_committed`.
- Avoid calling external side effects without idempotency/recovery.

### Kafka-to-database consumer

- Use a DB transaction for both the inbox row and business changes.
- Unique `eventId` guards against redelivery.
- Allow the listener to complete/commit offset only after the DB transaction has committed.
- Test crashing after DB commit but before Kafka offset commit.

### Database-to-Kafka publisher

- Write business changes and the outbox row in the same DB transaction.
- Relay/CDC publishes outbox entries to Kafka.
- Mark send status and handle potential duplicate publishes.
- Downstream consumers use inbox/idempotency.

### Kafka-to-external-service workflow

- Use `eventId`/`operationId` as the idempotency key.
- Persist operation state for retries and reconciliation.
- For multi-step workflows, use a saga and compensating actions.
- Do not rely on Kafka transactions to roll back external services.

## 15. Testing failure windows

Ordinary unit tests are insufficient to prove safe behavior when a process crashes between two systems. Test potential failure points:

- Call external service successfully, then intentionally force the Kafka transaction to roll back; verify redelivery does not create a second side effect.
- External service completes but client times out; verify retrying with the same idempotency key returns the previous outcome.
- DB commits successfully, process dies before Kafka offset commit; verify the inbox prevents duplicate updates on redelivery.
- DB transaction rolls back; verify both the inbox row and business changes roll back together.
- Outbox relay publishes successfully then dies before marking published; verify downstream consumers deduplicate the event.
- Kafka output is sent but the transaction aborts; verify `read_committed` consumers do not see the aborted output.
- Run a `read_uncommitted` consumer in a test environment to observe the difference when reading transactional output.
- Run two instances concurrently; verify distinct `transactionIdPrefix` values and no mutual fencing.
- Exhaust retries; verify the record reaches the configured error/DLQ flow and can be investigated.
- Fail mid-saga; verify compensating actions have their own operation IDs and handle retries safely.

Integration tests should use a real Kafka broker or equivalent test environment with transaction support. For DB/external APIs, use fault injection or mocks that simulate timeouts after server-side commit to test ambiguous outcomes.

## 16. Exactly-once design checklist

- [ ] Clarified whether the exactly-once scope is Kafka-to-Kafka or involves external systems.
- [ ] Kafka transactions commit output records together with input offsets.
- [ ] Each application instance has a unique `transactionIdPrefix`.
- [ ] Downstream consumers use `read_committed` when only committed outputs should be read.
- [ ] Does not assume callbacks execute only once; safe repeat handling is designed.
- [ ] Every HTTP call uses a stable idempotency key or reconciliation workflow.
- [ ] DB consumers write inbox/unique event IDs in the same transaction as business mutations.
- [ ] DB-to-Kafka publishers use an outbox or recoverable dual-write pattern.
- [ ] Non-rollbackable side effects have sagas/compensation where appropriate.
- [ ] Commit ordering is understood when coordinating multiple transaction managers.
- [ ] Retries and DLQ align with the transactional binder.
- [ ] Crash windows, timeouts, redelivery, and replays have been tested.

Kafka EOS is a strong guarantee for reading, processing, and writing across Kafka topics when offsets and outputs share a transaction. It does not make an HTTP service call, an independent database update, or an email part of the Kafka transaction. Assume processing code can run again, use idempotency keys and inbox tables to protect side effects, use an outbox for database-to-Kafka dual-writes, and use sagas when a multi-service workflow requires compensation.

## References

- [Spring Cloud Stream 5.1 — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/5.1/kafka/kafka-binder/transactional.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Blog — Apache Kafka's Exactly-Once Semantics in Spring Cloud Stream Kafka Applications](https://spring.io/blog/2023/10/16/apache-kafkas-exactly-once-semantics-in-spring-cloud-stream-kafka/)
