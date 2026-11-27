# Default Synchronicity, Execution Order, and Exceptions in Listeners

Spring Data REST publishes repository events when the REST exporter handles entity operations. Listeners allow validating or normalizing data before saving, reacting after creation/update/deletion, or handling link changes between resources.

Three things to understand clearly when designing listeners are: listeners run synchronously by default, Before and After events appear around the repository operation in order, and exceptions can directly affect the HTTP request. These are Spring Data REST events; they should not be confused with JPA lifecycle callbacks such as @PrePersist or @PostUpdate.

## 1. Eight Spring Data REST Repository Events

The REST exporter publishes eight event types while working with entities:

| Stage | Pre-operation Event | Post-operation Event | Purpose |
|---|---|---|---|
| Create entity | BeforeCreateEvent | AfterCreateEvent | Handle when creating a new resource |
| Save entity | BeforeSaveEvent | AfterSaveEvent | Handle when saving/updating a resource |
| Save link | BeforeLinkSaveEvent | AfterLinkSaveEvent | Handle when updating an association link |
| Delete entity | BeforeDeleteEvent | AfterDeleteEvent | Handle when deleting a resource |

Practical meaning:

- BeforeCreateEvent: published before the REST exporter saves a new entity.
- AfterCreateEvent: published after the entity creation operation.
- BeforeSaveEvent: published before an entity is saved.
- AfterSaveEvent: published after the entity save operation.
- BeforeLinkSaveEvent: published before an association link is saved/updated.
- AfterLinkSaveEvent: published after the association link save operation.
- BeforeDeleteEvent: published before the entity deletion operation.
- AfterDeleteEvent: published after the entity deletion operation.

These events are tied to the Spring Data REST processing flow. If the application calls a repository directly from a service or writes data through another path, do not assume Spring Data REST repository events will also be published. If you need to capture all changes regardless of the caller, design events/domain services or a persistence mechanism matching that scope.

## 2. Registering Listeners with @RepositoryEventHandler

The common approach is to create a Spring bean and annotate the class with @RepositoryEventHandler. Methods are marked with annotations corresponding to the stage you want to handle.

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // Validate or normalize data before creation.
        person.setDisplayName(person.getDisplayName().trim());
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        // Check business rules before saving.
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // React after the save operation.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // Record or process after the delete operation.
    }
}
~~~

Declaration rules:

- The bean must be managed by Spring, e.g. via @Component, or declared using @Bean in configuration.
- @RepositoryEventHandler(Person.class) scopes the handler to the Person domain type.
- The first parameter type of a handler method determines the domain type it receives.
- @HandleBeforeCreate, @HandleAfterCreate, @HandleBeforeSave, @HandleAfterSave, @HandleBeforeLinkSave, @HandleAfterLinkSave, @HandleBeforeDelete, and @HandleAfterDelete correspond to the eight events above.
- Place logic in the right stage: validation/normalization before the operation; sending notifications or recording outcomes after the operation.

You can omit the domain type parameter on @RepositoryEventHandler if you want the handler to process multiple entity types, in which case declare methods with the right domain types and avoid matching the wrong resource type.

## 3. Using AbstractRepositoryEventListener

Another approach is extending AbstractRepositoryEventListener and overriding the needed hooks:

~~~java
@Component
public class AuditRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        // Process before saving.
    }

    @Override
    protected void onAfterSave(Object entity) {
        // Process after saving.
    }

    @Override
    protected void onBeforeDelete(Object entity) {
        // Process before deleting.
    }

    @Override
    protected void onAfterDelete(Object entity) {
        // Process after deleting.
    }
}
~~~

This approach is convenient when you want to consolidate multiple events into a shared listener. However, entity types usually need to be checked in code because the listener may receive multiple domain types. For entity-specific logic, @RepositoryEventHandler is usually easier to read and more type-safe.

You do not need to implement all eight hooks if business logic only cares about a few lifecycle points.

## 4. Synchronicity Is the Default Behavior

Spring Data REST events are Spring application events. Under default configuration, Spring publishes events and invokes listeners synchronously on the publishing thread.

That means:

1. An HTTP request enters the REST exporter.
2. The REST exporter publishes the event.
3. The listener runs on the current processing thread.
4. The publisher waits for the listener to finish.
5. Processing continues and returns a response after synchronous listeners have completed.

For example, if a request updating Person triggers three synchronous listeners and each takes 100 ms, the request processing time includes the time of all three listeners plus the rest of the request work. This is just an illustrative example; actual latency depends on workload and how the listeners are implemented.

Consequences of synchronous processing:

- Listeners can read or mutate the entity at the moment the event is published.
- Exceptions from listeners can propagate back to the event publisher.
- Long-running tasks like calling external services, sending emails, or generating reports increase request latency.
- A slow listener can make active requests wait.
- There is no automatic queue, retry, or durable delivery simply from registering a repository event listener.

When an event is published inside an active transaction, a synchronous listener can run within the publisher's transaction context. However, check the actual transaction boundaries of the repository operation and listener; do not infer that every event lies within the same transaction solely from the name Before or After.

## 5. Processing Order of Before and After

The order at the repository operation level is clear: the Before event is published prior to the corresponding operation, and the After event is published after that operation.

~~~text
Create resource:
BeforeCreateEvent
        |
        v
Execute create/save operation
        |
        v
AfterCreateEvent

Update/save resource:
BeforeSaveEvent
        |
        v
Execute save operation
        |
        v
AfterSaveEvent

Update association link:
BeforeLinkSaveEvent
        |
        v
Execute link save operation
        |
        v
AfterLinkSaveEvent

Delete resource:
BeforeDeleteEvent
        |
        v
Execute delete operation
        |
        v
AfterDeleteEvent
~~~

Important notes:

- Before events are the right place to validate, enrich data, or normalize the entity before the repository performs the operation.
- After events are suitable for recording results or initiating follow-up reactions.
- AfterCreateEvent or AfterSaveEvent indicates that the corresponding repository operation was executed in the REST exporter flow. Do not automatically interpret this as a guarantee that the database transaction has durably committed.
- If a request fails at one stage, do not assume subsequent events will still be published.
- Spring Data REST publishes events for association link save operations; do not assume every relationship change publishes a dedicated event pair for every remove operation.

The order Before → repository operation → After is the event lifecycle order. It does not dictate the exact SQL order issued by the ORM to the database, nor the commit order of every related transaction.

## 6. Ordering Among Multiple Listeners for the Same Event

A single event can be received by multiple listeners. Do not let a second listener implicitly depend on the first listener having mutated the entity or written auxiliary data unless execution order is explicitly defined.

For listeners registered directly via Spring ApplicationListener or @EventListener mechanisms, Spring supports ordering listeners using Ordered or the @Order annotation. Lower order values have higher priority than higher values.

~~~java
@Component
public class PersonAuditListener {

    @EventListener
    @Order(10)
    public void onPersonSaved(AfterSaveEvent event) {
        // Listener ordered ahead of listeners with larger order values.
    }
}
~~~

Note: the example above illustrates Spring @EventListener receiving an application event. @RepositoryEventHandler is Spring Data REST's own handler mechanism; do not assume every @EventListener method-ordering rule applies identically to @HandleBeforeSave or @HandleAfterSave methods. Verify the behavior of the version in use if handler ordering is a strict requirement.

If business logic requires a deterministic sequence, you can:

- Group dependent steps into a single service invoked from one coordinating handler.
- Place operations needing ordering in the same method/service call.
- Use dedicated application events and explicitly ordered listeners when steps must be separated.
- Write integration tests recording actual order instead of relying on bean or method declaration order.

Avoid creating implicit dependency chains between multiple independent listeners. That makes changing configuration, adding listeners, or upgrading Spring harder to predict.

## 7. Exceptions in Synchronous Listeners

In default mode, listeners run directly on the event-publishing thread. If a listener throws a runtime exception and there is no custom exception handling, the exception can propagate back to the publisher and fail the REST request.

### Exceptions in Before events

Example listener rejecting data before saving:

~~~java
@HandleBeforeSave
public void validate(Person person) {
    if (person.getEmail() == null || person.getEmail().isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }
}
~~~

Because the save operation has not occurred yet at the time of BeforeSaveEvent, the exception normally prevents the REST flow from proceeding to the save operation. This is a suitable place for validation that decides whether the request may continue.

However, if the listener already performed its own side effect before throwing the exception, that side effect is not automatically undone just because saving the entity was blocked.

### Exceptions in After events

~~~java
@HandleAfterSave
public void afterSave(Person person) {
    // Example: calling another system to send a notification.
    notificationService.notifyPersonUpdated(person);
}
~~~

If the listener throws an exception here, the repository operation has already been invoked. The request may receive an error even though the data was saved. Whether the database rolls back depends on transaction boundaries, propagation, and actual commit timing.

Do not use exceptions in AfterSaveEvent as a business rollback mechanism. If you need to ensure side effects only happen after commit, design appropriate transaction events or publish domain events inside application-controlled transactions. For reliable delivery between the database and external systems, consider Transactional Outbox instead of calling HTTP/email directly from a listener.

### Impact on subsequent listeners

When a synchronous listener throws an unhandled exception, dispatching may stop at that listener; subsequent listeners should not be assumed to have run. If you need to isolate errors from a non-critical step, catch and handle errors intentionally, log thoroughly, and define retry or recovery strategies.

Never catch all Exceptions and silently ignore them. Doing so can turn validation errors, data errors, or business errors into false success responses.

## 8. Moving Listeners to Asynchronous Processing

Spring supports @Async for listeners registered through @EventListener. With async processing, work is handed off to another thread and the publisher does not wait for the listener to finish.

~~~java
@Component
public class PersonNotificationListener {

    @Async
    @EventListener
    public void onPersonSaved(AfterSaveEvent event) {
        // Process notification on another thread.
    }
}
~~~

For @Async to work, the application must enable async processing, such as with @EnableAsync, and provide a suitable executor.

Key differences compared to synchronous listeners:

| Characteristic | Synchronous Default | Asynchronous |
|---|---|---|
| Execution thread | Event-publishing thread | Thread managed by executor |
| Publisher waits for listener | Yes | No |
| Request latency | Includes listener time | Does not wait for async processing |
| Exceptions propagate to publisher | Can propagate back | Does not propagate to caller |
| Completion order across tasks | Follows synchronous dispatch order | Can differ from event publish order |
| Retry/durable delivery | Not built-in | Not built-in |

With async listeners, exceptions do not propagate back to the caller. Configure proper error handling, such as AsyncUncaughtExceptionHandler for void async methods, along with logging, metrics, and retry state when business logic requires it.

Do not assume ThreadLocal, security context, transaction context, or MDC logging context are propagated to the other thread. If the listener needs contextual data, pass it explicitly or configure an appropriate context propagation mechanism.

The example above illustrates Spring @EventListener receiving a Spring Data REST event. Do not infer that merely adding @Async to a @HandleAfterSave method will make Spring automatically apply the same mechanism. Use the listener mechanism supported by the framework.

If a task must run after the transaction commits, @TransactionalEventListener with the AFTER_COMMIT phase can be appropriate when the event is published inside an active transaction. If there is no transaction, a transactional listener is not invoked by default unless fallbackExecution is configured. For delivery guarantees even when the process crashes unexpectedly, a durable storage mechanism such as Outbox is required.

## 9. Designing Safe Listeners

A good listener should be short, clearly scoped, and not introduce extra risk to the main request.

**Place validation in Before events**

- Check conditions the API must enforce.
- Normalize data before saving.
- Throw meaningful exceptions when the request is invalid.
- Avoid slow external service calls if validation can be performed using local data.

**Place reactions in After events**

- Record appropriate audits or metrics.
- Trigger a follow-up domain event.
- If sending emails or calling external APIs, decide explicitly whether failure is allowed to fail the request.
- If execution must wait for commit, use transaction-aware design rather than relying on the name After.

**Keep listeners testable**

- Do not rely on accidental ordering between beans.
- Use dedicated services for reusable business logic.
- Ensure side effects are idempotent if retries are possible.
- Do not put heavy or unbounded work on the synchronous path.
- Log enough details to trace entities and events, while avoiding sensitive data.

## 10. Testing Ordering and Exceptions

Integration tests should go through real Spring Data REST endpoints to confirm events are published properly in the HTTP flow.

Cases to test:

1. POST creation: BeforeCreate runs before save and AfterCreate runs after the operation.
2. PUT/PATCH update: BeforeSave runs before save and AfterSave runs after the operation.
3. Deleting a resource: BeforeDelete and AfterDelete are published in order.
4. Updating an association: BeforeLinkSave and AfterLinkSave are published when the endpoint performs the corresponding link operation.
5. Before listener throws an exception: the request fails and the repository operation is not performed.
6. After listener throws an exception: verify the response and database state according to actual transaction boundaries.
7. Multiple listeners receive the event: verify ordering if the application relies on order.
8. Async listener: verify the request does not wait for async work and errors are recorded by the async error handler.
9. Calling repository directly from a service: confirm explicitly whether that flow publishes Spring Data REST events.

Do not assert only HTTP status. For exception scenarios, re-read the database to verify whether data was persisted or rolled back. For async listeners, use synchronization utilities in tests such as latches or Awaitility instead of fixed sleeps.

## 11. Common Misconceptions

| Misconception | Reality |
|---|---|
| AfterSave means the transaction has committed | The event marks the stage after the repository operation; commit depends on transaction boundaries |
| Every repository operation publishes Spring Data REST events | Events are tied to the REST exporter; other call paths need their own mechanisms |
| Listeners run in the background by default | Spring application events run synchronously by default |
| Registering multiple listeners runs them in parallel automatically | Synchronous dispatch waits for listeners; async must be configured explicitly |
| An exception in AfterSave automatically rolls back data | Cannot conclude without knowing whether the transaction has already committed |
| Bean declaration order determines listener order | Requires explicit ordering mechanisms and testing |
| Catching and ignoring exceptions is always safe | Can mask errors and produce false success responses |
| Async listeners include retries and guaranteed delivery automatically | @Async only switches threads; it does not provide a durable queue or automatic retries |

## 12. Pre-Implementation Checklist

- [ ] Identify the REST operation to listen to: create, save, link save, or delete.
- [ ] Choose Before or After matching the exact business timing.
- [ ] Register the handler as a Spring bean.
- [ ] Restrict domain types to avoid handling unintended entities.
- [ ] Keep synchronous listeners short and time-bounded.
- [ ] Decide whether exceptions are allowed to fail the request.
- [ ] Inspect transaction boundaries before relying on rollbacks or After events.
- [ ] If multiple listeners depend on one another, define explicit ordering.
- [ ] If running async, configure executor, error handler, and error observability.
- [ ] If post-commit processing or durable delivery is needed, use transaction-aware events or Outbox.
- [ ] Test both HTTP responses and database state after a listener throws an exception.

## References

- Spring Data REST Reference — Events: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Framework Reference — Application Events and Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html

