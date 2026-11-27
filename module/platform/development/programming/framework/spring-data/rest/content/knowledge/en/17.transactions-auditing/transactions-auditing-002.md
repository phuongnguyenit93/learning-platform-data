# Why After* Events Do Not Mean a Transaction Has Committed in Spring Data REST

## Objectives

Spring Data REST publishes events such as `AfterCreateEvent`, `AfterSaveEvent`, `AfterDeleteEvent`, and `AfterLinkSaveEvent` when the REST exporter processes an entity or association. The word “After” indicates that an exporter processing step has finished. It is **not the name of a transaction phase** and does not by itself guarantee that the database transaction has committed.

To understand precisely when a listener runs, separate three concepts:

1. **Repository operation:** the `save()`, `delete()`, or association operation call has returned.
2. **Spring application event:** the exporter publishes the event, and listeners are invoked synchronously on the publishing thread by default.
3. **Transaction completion:** the transaction manager actually commits or rolls back the transaction enclosing the operation.

When a repository opens its own transaction and there is no outer transaction, the repository call may commit before the exporter publishes the After* event. However, if the repository participates in an existing transaction, the After* event can still be published while that transaction is still open and later rolled back. Therefore, you cannot treat the After* prefix as an “already committed” guarantee.

## 1. Spring Data REST Before* and After* events

The REST exporter publishes eight repository events while processing entities:

| Before operation | After operation | Meaning |
| --- | --- | --- |
| `BeforeCreateEvent` | `AfterCreateEvent` | Creating a new entity |
| `BeforeSaveEvent` | `AfterSaveEvent` | Saving/updating an entity |
| `BeforeLinkSaveEvent` | `AfterLinkSaveEvent` | Linking or updating an association link |
| `BeforeDeleteEvent` | `AfterDeleteEvent` | Deleting an entity from the repository |

These events are published by the Spring Data REST REST exporter. You can listen to them using `ApplicationListener`, `AbstractRepositoryEventListener`, or an annotated handler with `@RepositoryEventHandler`.

The words “Before” and “After” describe the order relative to the repository operation executed by the exporter. They are not equivalent to Spring transaction synchronization phases such as `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`.

## 2. Execution order in the REST exporter

Consider an item update request:

~~~http
PUT /api/orders/42
Content-Type: application/json
~~~

In the current source of `RepositoryEntityController`, the update flow is implemented in this general order:

~~~java
publishEvent(new BeforeSaveEvent(domainObject));

Object saved = invoker.invokeSave(domainObject);

publishEvent(new AfterSaveEvent(saved));
~~~

The item deletion flow is similar:

~~~java
publishEvent(new BeforeDeleteEvent(entity));

invoker.invokeDeleteById(id);

publishEvent(new AfterDeleteEvent(entity));
~~~

You can visualize this as:

~~~text
REST request
    |
    v
Before* event
    |
    v
RepositoryInvoker calls save/delete
    |
    v
Repository method returns
    |
    v
After* event
    |
    v
Exporter completes response
~~~

The key point is that the exporter publishes After* after the repository call returns. The exporter does not turn the event into a transaction callback and does not guarantee that every transaction enclosing that call has ended.

With Spring Data JPA, CRUD methods on `SimpleJpaRepository` are usually annotated with `@Transactional`. Without an outer transaction, the repository call can open and complete its own transaction before returning to the exporter. In that common case, After* may be published after the repository transaction commits.

However, if the repository call joins an existing transaction, the repository does not commit the outer transaction itself. Returning from the method only means the method's work is done; the outer transaction can still commit or roll back afterward. That is why After* is not a commit guarantee independent of the actual transaction boundary.

## 3. Two transaction scenarios for the same AfterSaveEvent

### Scenario A: the repository owns the transaction

Suppose the request passes through the REST exporter with no outer transaction:

~~~text
REST exporter
    |
    | invokeSave()
    v
Repository transaction begins
    |
    | INSERT / UPDATE
    v
Repository method finishes
    |
    | Transaction manager commits
    v
invokeSave() returns
    |
    | publish AfterSaveEvent
    v
Listener runs
~~~

In this scenario, the repository transaction has typically committed by the time the exporter publishes AfterSaveEvent. If the listener writes logs or sends notifications, that work happens after the repository transaction.

However, that is a consequence of the active transaction boundary, not a guarantee implied by the name AfterSaveEvent. A different repository implementation or transaction configuration can have a different boundary.

### Scenario B: an outer transaction exists

Suppose a transaction wraps the request or repository call:

~~~text
Outer transaction begins
    |
    v
REST exporter
    |
    | BeforeSaveEvent
    v
Repository save joins outer transaction
    |
    | SQL runs in open transaction
    v
Repository method returns
    |
    | AfterSaveEvent is published
    v
Listener runs
    |
    v
Outer transaction continues
    |
    +---- COMMIT
    |
    +---- ROLLBACK
~~~

Here, AfterSaveEvent is published before the outer transaction finishes. The listener may have already run, yet the data can still be rolled back afterward.

For example, a request might execute inside a test transaction or an outer transaction interceptor. The repository joins the current transaction; the After* event is published while that transaction is still open. If the transaction is marked rollback-only, the database will not persist the changes even though the listener received the event.

Therefore, the question to ask is not merely “what is the event named?”, but “who owns the transaction and where does that transaction end?”.

## 4. Spring events run synchronously by default

Spring Data REST events are specialized Spring application events. By default, Spring application event listeners run synchronously: the publisher calls `publishEvent(...)`, and listeners are invoked on the same thread before the publish call returns.

This means:

- When Before* is published, default handlers run before the exporter invokes the repository operation.
- When After* is published, default handlers run after the repository invocation returns.
- Unhandled exceptions in a synchronous listener propagate back to the publisher.
- A synchronous listener neither creates a new transaction nor waits for a transaction to commit.
- If an event is handed off to another thread or across an asynchronous boundary, ordering and transaction context must be evaluated separately.

Synchronous only describes how the listener is invoked; it says nothing about which phase the transaction is in.

## 5. Why an After* listener can run while data still rolls back

Suppose a handler records an event in memory or sends a message immediately upon receiving AfterSaveEvent:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderEventHandler {

    private final NotificationService notificationService;

    public OrderEventHandler(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        notificationService.notifyUpdated(order.getId());
    }
}
~~~

If AfterSaveEvent is published while an outer transaction is still open, the notification can be sent successfully before the transaction ends. Afterward, the transaction rolls back due to an error in another step.

Result:

- The recipient has already received an “Order updated” notification.
- The database did not persist the Order change.
- The external system and the database are out of sync.

The same situation occurs when a handler sends an email, calls a webhook, publishes a message to a broker, or evicts a cache directly inside After*.

If After* is published after a repository-owned transaction has committed, rolling back that transaction can no longer occur. Even then, the handler itself can still fail after commit, or another outer transaction might not yet be complete. Hence, you should not use After* as a mechanism to guarantee ordering between the database and external systems.

## 6. Use @TransactionalEventListener when you need a transaction phase

Spring Framework provides `@TransactionalEventListener` to bind a listener to the transaction lifecycle. The default phase is `AFTER_COMMIT`.

The phases are:

| Phase | When the listener runs | Use case |
| --- | --- | --- |
| `BEFORE_COMMIT` | Right before the transaction commits | Validate or prepare data within the current transaction |
| `AFTER_COMMIT` | Only after a successful commit | Send notifications, update caches/indexes after data has committed |
| `AFTER_ROLLBACK` | After the transaction rolls back | Compensating actions or alerts when an operation fails |
| `AFTER_COMPLETION` | After the transaction ends, whether commit or rollback | Clean up resources or perform tasks needing completion notification |

Example:

~~~java
@Component
public class OrderCommittedListener {

    private final NotificationService notificationService;

    public OrderCommittedListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChangedEvent event) {
        notificationService.notifyUpdated(event.orderId());
    }
}
~~~

The listener above runs only after the transaction in which the event was published commits successfully.

**Crucial requirement:** the event must be published while a transaction is active so that Spring can register the listener with that transaction. Without a transaction, `@TransactionalEventListener` does not invoke the listener by default. You can enable `fallbackExecution = true`, but when there is no transaction, the listener runs via fallback instead of waiting for a nonexistent commit.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderChangedEvent event) {
    // If there is no transaction, the method is still invoked via fallback.
}
~~~

Do not use fallbackExecution as a way to create a commit guarantee. When there is no transaction, there is no commit phase to wait for.

## 7. An important limitation when listening directly to Spring Data REST After* events

You can write:

~~~java
@Component
public class RepositoryAfterSaveListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onAfterSave(AfterSaveEvent event) {
        // Process after commit if the event is published inside a transaction.
    }
}
~~~

However, you must not assume this listener will always run when Spring Data REST publishes AfterSaveEvent.

If the repository invocation has already completed its transaction before the exporter publishes AfterSaveEvent, there may no longer be an active transaction at publish time. In that case, the transactional listener is not registered by default and will not run.

If an outer transaction exists, the event is published inside that transaction and the listener can be registered to run after commit. Therefore, inspect the actual transaction boundary of the request and repository rather than just changing the annotation on the handler.

When business requirements strictly demand an event bound to commit, a clearer approach is to publish a domain event from inside a service method with a controlled transaction:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void updateOrder(Order order) {
        Order saved = repository.save(order);

        publisher.publishEvent(
                new OrderChangedEvent(saved.getId()));
    }
}
~~~

The event is published while the service transaction is active. The `@TransactionalEventListener(AFTER_COMMIT)` listener can register with that transaction and run only after a successful commit.

If you need to keep the default Spring Data REST API, verify whether an outer transaction wraps the request. If none exists and the business requirement needs an event tightly bound to the transaction, consider a custom controller/service endpoint so that both the transaction and the event publication point are explicitly controlled.

## 8. Writing data in an AFTER_COMMIT listener requires a new transaction

Spring Framework notes that in the `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` phases, the original transaction has already completed, yet some transactional resources may still be bound and accessible during the callback.

Consequently, if an after-commit listener calls a repository to write additional data, that operation may participate in the old transaction's resources without any subsequent commit. As a result, the new write is not committed as intended.

If a listener must write to the database after commit, open a new transaction, typically via a separate service bean:

~~~java
@Service
public class OrderAuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(Long orderId) {
        // Persist the audit record in a new transaction.
    }
}
~~~

~~~java
@Component
public class OrderCommittedListener {

    private final OrderAuditWriter auditWriter;

    public OrderCommittedListener(OrderAuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChangedEvent event) {
        auditWriter.writeAudit(event.orderId());
    }
}
~~~

Placing the new transaction method on another Spring bean ensures the call passes through the transaction proxy. Avoid calling a `REQUIRES_NEW` method within the same object because self-invocation normally bypasses the proxy and does not start a new transaction.

## 9. When do you need a transactional outbox?

`@TransactionalEventListener(AFTER_COMMIT)` guarantees the listener is invoked only after commit, but it does not make a message broker operation atomic with the database transaction. For example, the process could crash after the database commits but before the message is sent.

When high reliability is required for system integration:

1. In the business transaction, save the Order change and an Outbox record.
2. Commit both in the same database transaction.
3. A worker reads committed Outbox records.
4. The worker sends the message to the broker or webhook.
5. The worker marks the record as sent or retries according to policy.
6. The consumer handles messages idempotently because messages may be redelivered.

Illustration:

~~~text
One database transaction
   |
   +-- UPDATE orders
   |
   +-- INSERT outbox_events
   |
   v
COMMIT
   |
   v
Outbox relay
   |
   v
Message broker / webhook
~~~

If a Spring Data REST request has no outer transaction and After* is published only after the repository transaction has completed, you cannot assume an After* handler can write an Outbox record atomically with the original Order change. Move both the entity write and the outbox write into the same service transaction or a custom endpoint with an explicit transaction boundary.

Outbox is especially useful for payments, orders, inventory, notifications, and workflows where losing a message after commit causes business inconsistencies.

## 10. Distinguishing @EventListener, @Async, and @TransactionalEventListener

| Mechanism | When it runs | Waits for commit? | Transaction context |
| --- | --- | --- | --- |
| `@EventListener` | When the event is published; synchronous by default | No | Runs on the publishing thread if synchronous |
| `@Async @EventListener` | On another executor/thread | No | Does not inherit the publisher's thread-bound transaction |
| `@TransactionalEventListener` | According to the chosen phase; defaults to AFTER_COMMIT | Yes, if the event is published in a transaction | Bound to the transaction that published the event |
| `@TransactionalEventListener(fallbackExecution = true)` | According to phase when a transaction exists; runs fallback otherwise | No commit to wait for in the fallback case | No original transaction in the fallback case |

Do not add `@Async` merely to avoid slowing down the request if the listener needs transaction context. For listeners that must run after commit, use a transaction-bound event first; if background processing is needed, let the after-commit listener push work onto a queue/executor or outbox relay.

Since Spring Framework 6.1, transactional event listeners also support reactive transactions. Reactive transactions store context in the Reactor context instead of thread-local storage; events must carry the appropriate transaction context. Do not apply thread-bound imperative assumptions to reactive flows.

## 11. Testing to prove After* does not guarantee commit

The test must establish a transaction wrapping the REST exporter operation. With MockMvc running synchronously on the same test thread, you can use a test transaction to observe the event before the transaction ends.

Illustrative example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryEventTransactionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository repository;

    @Autowired
    AfterSaveProbe afterSaveProbe;

    @Test
    @Transactional
    void afterSaveEventCanRunBeforeOuterTransactionCompletes()
            throws Exception {

        Order order = repository.save(new Order("PO-42"));

        mockMvc.perform(put("/api/orders/{id}", order.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "orderNumber": "PO-42-UPDATED"
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        assertThat(afterSaveProbe.wasCalled()).isTrue();

        // The test transaction is still open here.
        // If the test flags for rollback, changes in the request participating
        // in this transaction can also be rolled back.
        TestTransaction.flagForRollback();
        TestTransaction.end();

        Order persisted = repository.findById(order.getId()).orElseThrow();
        assertThat(persisted.getOrderNumber()).isEqualTo("PO-42");
    }
}
~~~

The example assumes MockMvc executes the request on the same thread and the repository joins the open test transaction. If the request runs through a real server, another thread, or a different transaction manager, the test boundary will differ; you must design integration tests suited to the actual architecture.

You can verify that a transactional listener runs only after commit:

~~~java
@Test
@Transactional
void transactionalListenerWaitsForCommit() throws Exception {
    mockMvc.perform(put("/api/orders/{id}", 42)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "orderNumber": "PO-42-UPDATED" }
                """))
        .andExpect(status().is2xxSuccessful());

    assertThat(afterCommitProbe.wasCalled()).isFalse();

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertThat(afterCommitProbe.wasCalled()).isTrue();
}
~~~

Additionally, test these cases separately:

- No outer transaction: verify when the repository transaction ends.
- Outer transaction that commits: After* can run before commit, while the transactional listener runs after commit.
- Outer transaction that rolls back: a synchronous After* handler may have already run, while an AFTER_COMMIT listener does not run.
- No transaction: a transactional listener does not run by default.
- With `fallbackExecution = true`: the listener is called even without a transaction, but there is no commit guarantee.
- Post-commit listener writing to the database: verify that the `REQUIRES_NEW` transaction actually commits.

## 12. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| AfterSaveEvent ran, but data rolled back | Event was published inside an open outer transaction | Use a transaction-bound listener when post-commit processing is required |
| Notification was sent, but the entity was not saved | Side effect ran in a synchronous After* handler before the outer transaction ended | Move the notification to AFTER_COMMIT or an outbox |
| @TransactionalEventListener does not run | Event was published outside any transaction | Publish the event inside a service transaction or explicitly review fallbackExecution |
| fallbackExecution=true causes listener to run immediately | No transaction existed to bind a phase | Do not treat fallback as AFTER_COMMIT |
| AFTER_COMMIT listener writes to DB, but data is missing | Old transaction resources remain bound without another commit | Call a service that opens a REQUIRES_NEW transaction |
| Handler runs on another thread and sees no transaction | Asynchronous listener does not inherit thread-bound context | Separate async work from the transactional portion |
| After* exception does not roll back committed changes | Repository-owned transaction may have completed before the event was published | Do not use an After* exception as a rollback mechanism |
| Test proves event ran, not that it committed | Only asserted listener invocation without checking transaction outcome | Test both commit and rollback with transaction tests |

## 13. Rules for choosing a mechanism

| Goal | Mechanism |
| --- | --- |
| Normalize or validate an entity before the exporter saves | Before* event |
| Run logic after the repository invocation returns | After* event |
| Run only when the transaction commits successfully | `@TransactionalEventListener(AFTER_COMMIT)` with an event published inside a transaction |
| React when a transaction rolls back | `@TransactionalEventListener(AFTER_ROLLBACK)` |
| Run logic before commit | `@TransactionalEventListener(BEFORE_COMMIT)` |
| Reliably deliver messages after database changes | Transactional outbox |
| Apply the same rules across REST, jobs, and services | Shared service/domain layer |

Determine the transaction boundary before choosing a listener. The After* name indicates which step the repository/exporter passed through; only the transaction manager determines whether the transaction committed or rolled back.

## References

- [Spring Data REST 5.1.2 — Events](https://docs.spring.io/spring-data/rest/reference/events.html): list of the eight events, annotated handlers, ApplicationListener, and Spring's synchronous event default.
- [Spring Data REST — RepositoryEntityController source](https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryEntityController.java): source showing the exporter publishing Before*, invoking RepositoryInvoker, and then publishing After*.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases, fallbackExecution, and reactive transactions.
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): AFTER_COMMIT default, behavior without a transaction, and notes on accessing transactional resources after completion.
- [Spring Framework API — TransactionPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): definitions of BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION.
- [Spring Data JPA — SimpleJpaRepository source](https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java): example of CRUD methods marked transactional.
