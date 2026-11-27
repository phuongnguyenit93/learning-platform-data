# Rollbacks, Listener Failures, and Impact on Modified Data

## Objectives

Spring Data REST publishes repository events during resource creation, updates, association changes, and deletion. Listeners can normalize entities, write audits, or trigger follow-up processing. However, a listener throwing an exception does not mean all earlier changes in the request are automatically rolled back.

To handle errors properly, determine three things:

- When the event is published relative to the repository call.
- Which database transaction is active when the listener runs.
- Whether the changes already performed are database changes, in-memory entity mutations, or side effects in external systems.

This lesson focuses on rollbacks and listener failures in Spring Data REST, especially the difference between `Before*` and `After*` events. The core rule is: a transaction only rolls back operations participating in that transaction; an exception cannot automatically undo an email already sent, an HTTP call already executed, or another transaction that has already committed.

## 1. Event flow and where failures can occur

With an exported Person repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

A create request follows this general flow:

~~~text
POST /people
      |
      v
Deserialize request body into Person
      |
      v
BeforeCreateEvent
      |
      v
repository.save(person)
      |
      v
AfterCreateEvent
      |
      v
Create HTTP response
~~~

For item updates, Spring Data REST uses the pair `BeforeSaveEvent` and `AfterSaveEvent`. For deletions, the framework publishes `BeforeDeleteEvent` and `AfterDeleteEvent`. Association changes have corresponding link-save events.

Where the exception occurs matters greatly:

- An exception in `BeforeCreateEvent` occurs before the call to save the new entity. Execution stops and the POST operation's repository save has not been invoked yet.
- An exception inside `repository.save(...)` can cause the save operation's transaction to roll back.
- An exception in `AfterCreateEvent` occurs after the repository save call returns. If the repository save ran in its own transaction and that transaction already committed, an exception in the listener cannot roll back the completed transaction.
- If an outer transaction wraps the entire request and the repository save joins that transaction, an exception in an After event can still cause the outer transaction to roll back.

Therefore, you cannot infer whether data was committed just from the event name or the HTTP status. You must inspect the application's actual transaction boundaries.

## 2. Before events: failure before the repository saves

Events such as `BeforeCreateEvent`, `BeforeSaveEvent`, and `BeforeDeleteEvent` are published before the corresponding repository operation.

Example of a handler rejecting Person creation:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getEmail() == null
                || person.getEmail().isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
    }
}
~~~

When the handler throws an exception:

1. Event publication propagates the error back to the request processing flow under the default synchronous event mechanism.
2. Spring Data REST does not proceed to repository save for that resource creation flow.
3. The entity being constructed from the request is not saved by this POST operation.
4. The request ends with an error mapped to an HTTP response by the application's exception handling.

Under default configuration, an unhandled runtime exception may become an HTTP 500. If the application has an exception resolver, `@ControllerAdvice`, or custom Spring Data REST exception mapping, the status and response body can differ. Define mappings for business errors if clients need 400, 409, or a specific status.

### 2.1. In-memory changes are not committed changes

A handler may mutate the entity before throwing an exception:

~~~java
@HandleBeforeCreate
public void beforeCreate(Person person) {
    person.setEmail(person.getEmail().trim().toLowerCase(Locale.ROOT));

    if (person.getEmail().endsWith("@blocked.example")) {
        throw new IllegalArgumentException("Email domain is not allowed");
    }
}
~~~

After the exception escapes, the in-memory entity has the normalized email, but repository save was not invoked. Unless another write operation runs, that mutation does not become database state.

Do not reuse an object from a failed request as if it held normal persistence state. Reload data from the repository when reliable state is needed.

### 2.2. Before listeners can still produce independent side effects

The fact that repository save has not happened does not mean every action inside the listener disappears. For example, a listener might:

- Write an audit record using another repository.
- Call an external service.
- Send an email or message.
- Write a file or update a cache.

If those operations use a separate transaction or do not participate in the transaction of the entity being created, they can persist even though Person creation was aborted. Consequently, do not perform irreversible side effects in a Before listener before knowing whether the main operation can commit.

## 3. Failures during repository save: the transaction can roll back

Spring Data JPA write CRUD methods typically run inside a transaction managed by the repository implementation. When the save operation encounters a runtime exception or an error at flush/commit, the corresponding transaction is rolled back.

Example:

~~~java
@Transactional
public Person createPerson(Person person) {
    return personRepository.save(person);
}
~~~

If a constraint violation or persistence error occurs in this transaction, database changes belonging to the transaction are not committed. Some errors only surface at flush or commit time, even though `save()` was called earlier.

Spring's transaction default is to roll back on `RuntimeException` and `Error`; checked exceptions do not automatically trigger rollback unless an appropriate `rollbackFor` is configured:

~~~java
@Transactional(rollbackFor = Exception.class)
public Person createPerson(Person person) throws Exception {
    // database operations that must succeed or roll back together
}
~~~

Rollback rules apply only when the exception passes through the transaction interceptor and the transaction has not yet committed. If code catches an exception and does not rethrow it, the transaction may proceed to commit unless it was already marked rollback-only or a persistence error prevents commit.

With JPA, after a persistence error, the transaction may already be marked rollback-only. Do not catch the exception and keep writing within the same transaction assuming the persistence context is still safe.

## 4. After events: listener errors can occur after commit

Example handler:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAfterCreateHandler {

    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditService.recordCreated(person.getId());
        throw new IllegalStateException("Audit processing failed");
    }
}
~~~

In the standard Spring Data REST flow, After events are published after the repository save call returns. With a JPA repository using the save method's own transaction and no outer transaction, the save transaction may have already committed before the After handler is called.

In that case, the following can happen:

1. Person is inserted and the save transaction commits successfully.
2. Spring Data REST publishes `AfterCreateEvent`.
3. The listener throws an exception.
4. The client receives an HTTP error instead of the expected creation response.
5. The Person record still exists in the database.

This is why an HTTP 500 is not proof that a POST rolled back. A client might retry the request upon seeing the error and accidentally create duplicate records.

This outcome depends on the actual transaction boundary. If a controller/service or application configuration has opened an outer transaction wrapping both repository save and event dispatch, the After listener still runs inside that transaction; an exception can cause the outer transaction to roll back. Do not assume an outer transaction wraps the request unless the application explicitly configures one.

### 4.1. After events are not transaction after-commit events

The name `AfterCreateEvent` means the event is published after the repository create/save operation in the Spring Data REST flow. It is not synonymous with the Spring transaction phase `AFTER_COMMIT`.

Two concepts must be kept separate:

- `AfterCreateEvent`: a repository lifecycle event published by Spring Data REST after the entity save call.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`: an application event listener invoked after the transaction enclosing the event publication commits successfully.

If the event is published when no transaction is active, a transactional event listener is not called by default because there is no transaction phase to bind to. Thus, do not simply rename a listener or add `@TransactionalEventListener` without verifying where the event is published and which transaction is active.

## 5. Impact table by failure point

| Failure point | Was repository save called? | Could entity data have committed? | What to check |
|---|---|---|---|
| `BeforeCreateEvent` throws | No | Not from that POST operation | Whether the listener wrote data or caused independent side effects |
| `BeforeSaveEvent` throws | Save not called for that update | Not from that save call | Whether an outer transaction or prior auxiliary operations exist |
| Inside `repository.save()` | Yes | Usually no if the transaction rolled back successfully | Runtime/checked exception, flush, commit, and rollback rules |
| `AfterCreateEvent` throws | Called and returned | May have committed if save transaction ended independently | Whether an outer transaction wraps the request |
| `AfterSaveEvent` throws | Called and returned | May have committed if save transaction ended independently | Transaction boundaries and listener side effects |
| `AfterDeleteEvent` throws | Delete executed | Record may already be deleted and committed | Recheck via repository/database |
| External API/email/message fails | Depends on timing | Database may or may not have committed | Whether the external system supports retry/idempotency |

This table describes the typical CRUD repository flow. Custom transactions in controllers/services, propagation, transaction managers, and datastore types can change the outcome. When atomicity is required, design explicit transaction boundaries rather than relying on event names.

## 6. Multiple listeners and synchronous failures

Spring application events are published synchronously by default unless the application configures an asynchronous event multicaster. Therefore, handlers usually execute on the request-handling thread.

If one listener throws an unhandled exception:

- The exception can propagate back to the event publisher and fail the request.
- Listeners scheduled after the failing listener may not execute with the default multicaster when no ErrorHandler is configured.
- Listeners that already ran earlier may have written data or triggered side effects.
- There is no automatic mechanism to undo listeners that have already executed.

If the application configures an event multicaster with an ErrorHandler or custom error handling, continuation/error-propagation behavior can differ. Inspect the actual configuration when multiple listeners depend on execution order.

Do not rely on incidental ordering among listeners to execute critical business sequences. If step B must run only after step A succeeds, invoke them from an orchestrating service with explicit transactions and error rules, or use stateful workflow/message processing.

## 7. @Transactional on a listener does not automatically wrap the whole request

Adding `@Transactional` to an event handler only creates or joins a transaction for the handler invocation according to its configured propagation. It does not retroactively pull the earlier repository save into the same transaction.

Example:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAfterCreateHandler {

    private final AuditRepository auditRepository;

    public PersonAfterCreateHandler(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional
    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditRepository.save(
            new AuditRecord("PERSON_CREATED", person.getId())
        );
    }
}
~~~

Without an outer transaction, the handler's transaction may start after the Person save transaction has already ended. When the audit insert fails, the audit transaction rolls back while the committed Person remains.

If `Propagation.REQUIRES_NEW` is used, the listener transaction is intentionally separated. It can commit independently and will not roll back with an outer transaction. This is useful for certain independent audits, but unsuitable when the requirement is for the audit and entity to succeed or fail together.

Conversely, `Propagation.REQUIRED` joins an existing transaction only if one is present; otherwise it opens a new transaction. Determine which transaction is active when the event is published.

## 8. Designing for consistent data and audits

If the business requirement is that creating an entity and writing an audit record must commit or roll back together, place both operations inside a service method with an enclosing transaction:

~~~java
@Service
public class PersonCreationService {

    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonCreationService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Person create(Person person) {
        Person saved = personRepository.save(person);

        auditRepository.save(
            new AuditRecord("PERSON_CREATED", saved.getId())
        );

        return saved;
    }
}
~~~

With the same transaction manager and the same transaction, if saving the audit record fails with a rollback-triggering error, creating the Person also rolls back. To ensure the endpoint uses this service, route the request through that service method—for instance via a custom controller or an application-orchestrated flow. Simply declaring the service does not make Spring Data REST's default POST call it automatically.

If you continue using repository event handlers, understand that a handler running before or after a repository call does not inherently create a transaction spanning both sides. Do not assume a standalone `@Transactional` on a listener guarantees atomicity between the entity and the audit.

## 9. External side effects and the transactional outbox

A database rollback cannot undo actions that have already occurred in systems outside the transaction:

- Emails already sent.
- HTTP requests that already reached another service.
- Messages already acknowledged by a broker.
- Files already written.
- Caches already updated in another system.

For example, a BeforeCreate listener sends an email and then repository save hits a constraint error. The database has no new Person, yet the email has already left the system. Similarly, an AfterCreate listener may successfully deliver a webhook before another step causes an outer transaction to roll back.

For integrations requiring high reliability, a transactional outbox is a common choice:

1. Within the same transaction that creates the entity, write an outbox record describing the event to publish.
2. Commit the entity and outbox record together.
3. A worker reads unprocessed outbox records and delivers messages/webhooks.
4. After successful delivery, the worker marks the record processed.
5. If the worker fails, retry according to policy; consumers must process idempotently to avoid duplicate effects.

Simple structural example:

~~~java
@Transactional
public Person create(Person person) {
    Person saved = personRepository.save(person);

    outboxRepository.save(
        OutboxMessage.personCreated(saved.getId())
    );

    return saved;
}
~~~

If the transaction rolls back, neither the Person nor the outbox record is committed. If the transaction commits, the worker can continue publishing the message even if the application stops right afterward.

An outbox does not by itself guarantee exactly-once delivery. A worker may deliver successfully and crash before marking the record processed, so consumers and senders need idempotency keys or suitable deduplication mechanisms.

## 10. Error handling and returning HTTP responses

Do not swallow exceptions in a listener just to keep requests always returning success:

~~~java
@HandleAfterCreate
public void afterCreate(Person person) {
    try {
        notificationService.send(person);
    } catch (Exception ex) {
        log.error("Notification failed", ex);
        // Do not silently treat an important side effect as succeeded.
    }
}
~~~

If the notification is an auxiliary task that can be retried, record the failure state and offload it to a worker/outbox. If the notification is mandatory for the business operation to be considered successful, place it in a workflow with explicit state and compensation; do not rely on throwing an exception from an After listener to roll back a committed insert.

For business errors before saving, use meaningful exceptions and map them to appropriate responses. Example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidPersonException.class)
    ResponseEntity<ProblemDetail> handleInvalidPerson(
            InvalidPersonException ex) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        problem.setDetail(ex.getMessage());

        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

This is an example application controller advice; applicability and response format must be verified when used alongside Spring Data REST. Not every listener exception should return 400. Classify validation errors, conflicts, system errors, and integration errors according to your API contract.

## 11. Testing rollbacks and remaining data after failures

You should write integration tests against an appropriate database and verify repository state after the request. Two critical cases are Before listener failures and After listener failures.

Example verifying BeforeCreate failure:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonCreateRollbackTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PersonRepository repository;

    @Test
    void beforeCreateFailureDoesNotSavePerson() throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "firstName": "An",
                      "email": "blocked@example.com"
                    }
                    """))
            .andExpect(status().is5xxServerError());

        assertThat(repository.findByEmail("blocked@example.com"))
            .isEmpty();
    }
}
~~~

The status in the example should be adjusted to match your actual exception mapping. What matters is asserting that the entity was not saved because the POST was blocked before repository save.

For After listeners, when no outer transaction wraps the request, verify the possibility that data committed despite an error response:

~~~java
@Test
void afterCreateFailureMayLeaveCommittedPerson() throws Exception {
    mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": "An",
                  "email": "after-error@example.com"
                }
                """))
        .andExpect(status().is5xxServerError());

    assertThat(repository.findByEmail("after-error@example.com"))
        .isPresent();
}
~~~

This test only applies to a transaction setup where repository save commits before the After listener fails. If the application has an outer transaction wrapping event dispatch, the expectation may be rollback and tests should reflect that configuration.

**Avoid placing `@Transactional` on the test method when verifying the real transaction boundary of a request.** A test transaction may bind to the same thread and cause repository save to join the test transaction. The After listener then runs before the test transaction finishes; results may differ from production requests that have no outer transaction. If a test requires isolation, use a transaction template or execute the request against a separate server/thread and verify data after the request completes.

Tests should cover:

- Before listener throws: verify repository save did not create the entity.
- Repository save hits a constraint error: verify changes in the transaction are rolled back.
- After listener throws: verify the HTTP status and check whether the database may have kept the entity.
- Listener writes audit in a separate transaction: verify the audit can persist independently.
- Side effects moved to an outbox: verify entity and outbox record commit/roll back together.
- Request retry after error response: verify idempotency or duplicate-creation prevention.

## 12. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| POST returns 500, yet entity still exists | AfterCreate listener failed after repository save committed | Check the database; do not infer rollback from HTTP status |
| BeforeCreate failed, yet audit record exists | Listener wrote audit in an independent transaction before rejecting creation | Move audit into a shared transaction or clarify failure semantics |
| Exception caught and data still committed | Exception was swallowed or transaction not marked rollback-only | Rethrow the error or configure proper rollback rules |
| Checked exception did not roll back | Spring rolls back RuntimeException/Error by default | Use rollbackFor when a transaction must roll back on checked exceptions |
| Email/webhook still sent despite database rollback | External side effect did not participate in the database transaction | Use an outbox or after-commit workflow |
| Audit failed, yet entity was saved | Audit ran in a separate transaction after repository save | Use a service transaction wrapping both entity and audit if atomicity is needed |
| Test shows After listener rolls back, but production does not | Test method had a transaction wrapping the MockMvc request | Test without an outer transaction or use a separate server/thread |
| Subsequent listener did not run | Preceding listener threw in synchronous event multicaster | Handle errors intentionally and do not depend on implicit listener order |
| In-memory entity holds new values despite DB rollback | Java objects are not automatically restored to pre-transaction state | Reload entities; do not reuse persistence state after rollback |
| POST retry creates duplicate records | Error response after insert committed caused the client to retry | Use idempotency keys or unique business keys |

## 13. Checklist for handling rollbacks and listener failures

- Identify whether the event is Before or After and where it is published relative to the repository invocation.
- Check which transaction is active when the handler is called.
- Distinguish in-memory Java object mutations, database changes, and external side effects.
- Do not infer rollback solely from HTTP 4xx/5xx statuses.
- Verify whether exceptions pass through the transaction interceptor or are caught and swallowed.
- Use rollbackFor when checked exceptions must trigger rollback.
- Do not use After events as a default callback guaranteeing the transaction has committed.
- Do not put an audit requiring atomicity into a separate transaction after the save operation.
- Use a `@Transactional` service method to group database writes that must commit together.
- Use a transactional outbox for messages/webhooks requiring reliability.
- Make consumers and retry operations idempotent.
- Test both committed and uncommitted data; avoid test transactions that distort production boundaries.
- Map business exceptions to appropriate HTTP statuses and log with correlation IDs.

## Conclusion

Rollback depends on transaction boundaries, not merely on whether a listener throws an exception. Failures in Before events normally prevent that operation's repository save from being invoked. Failures inside the save transaction itself can roll back database changes belonging to that transaction. Failures in After events can cause the request to return an error while the entity is already committed, if the save transaction ended and no outer transaction wrapped it. Side effects such as emails, webhooks, or messages do not automatically roll back with the database. When entity and audit data must be atomic, orchestrate them in a single service transaction; when external events must be emitted reliably, use a transactional outbox and idempotent processing.

## References

- Spring Data REST – Events and repository event handlers: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Data JPA – Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Framework – Declarative transaction management and rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – Transaction-bound events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
