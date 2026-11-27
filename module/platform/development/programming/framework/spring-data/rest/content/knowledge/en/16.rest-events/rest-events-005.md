# BeforeDeleteEvent and AfterDeleteEvent When Deleting Resources in Spring Data REST

## Objectives

Spring Data REST publishes repository events while processing REST requests. When a client deletes an item resource, two key events are:

- **BeforeDeleteEvent**: published before the entity is deleted from the repository.
- **AfterDeleteEvent**: published after the repository entity deletion operation completes.

These two events allow an application to add logic around the DELETE operation, such as validating deletion conditions, recording audits, refreshing caches, or notifying another component.

It is necessary to distinguish three milestones: before invoking the delete operation, after the repository executes the delete operation, and after the database transaction commits. The name AfterDeleteEvent only states that the repository operation has finished; it does not automatically guarantee that the transaction has committed.

## 1. Flow of Deleting an Item Resource

Suppose the Order repository is exported at /api/orders. A client sends:

~~~http
DELETE /api/orders/42
~~~

For deleting an entity through the REST exporter, the high-level flow is:

~~~text
HTTP DELETE /api/orders/42
        |
        v
Spring Data REST finds Order entity with id = 42
        |
        v
BeforeDeleteEvent
        |
        v
Repository executes delete(entity)
        |
        v
AfterDeleteEvent
        |
        v
Complete request processing / transaction commit
~~~

Spring Data REST publishes BeforeDeleteEvent before the entity is deleted from the repository and AfterDeleteEvent after the delete operation. These events are custom Spring application events published by the REST exporter.

If the entity is not found, the operation may end with a not-found response and there is no entity to run the deletion event sequence above. Exact status codes and response bodies should be tested against the exporter configuration and version in use.

Example item endpoint:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Clients do not need to call a custom service or controller to trigger events. When a request goes through the Spring Data REST repository exporter, the framework publishes the corresponding events while processing the entity.

## 2. Meaning of BeforeDeleteEvent

BeforeDeleteEvent represents the entity about to be deleted. This is the right moment for tasks that need to inspect the entity state before the repository removes it:

- Checking business conditions, such as disallowing deletion of a paid order.
- Checking status or dependent relationships before deleting.
- Recording audit details about the deletion request.
- Preparing data needed for a controlled deletion workflow.
- Rejecting the operation with an exception if conditions are not satisfied.

Example, disallowing deletion of a paid Order:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    @HandleBeforeDelete
    public void handleBeforeDelete(Order order) {
        if (order.getStatus() == OrderStatus.PAID) {
            throw new OrderDeletionNotAllowedException(
                    "Cannot delete a paid order");
        }
    }
}
~~~

Meaning of the annotations:

- `@RepositoryEventHandler(Order.class)`: registers the class as an event handler and scopes the domain type to handle to Order.
- `@HandleBeforeDelete`: marks the method receiving the event before deletion.
- The first parameter of the method is the entity being processed.

If an exception is thrown, the deletion operation is interrupted at the handler before the repository performs delete. Define a business exception and map it to an appropriate HTTP status, such as 409 Conflict, using the application's exception handler. Never let a business error be returned as a meaningless 500 error to the client.

BeforeDeleteEvent is suitable for guarding pre-deletion conditions, but core business rules should live in the service/domain layer if multiple paths can delete the entity.

## 3. Meaning of AfterDeleteEvent

AfterDeleteEvent represents the entity for which the repository delete operation has just finished processing. This is the right moment for post-processing actions such as:

- Recording the deletion event in an audit log.
- Evicting or marking stale an entry in a cache.
- Updating a search index.
- Updating metrics or statistics.
- Notifying an internal component that the entity was requested to be deleted from the repository.

Example:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final OrderAuditService auditService;

    public OrderDeleteEventHandler(OrderAuditService auditService) {
        this.auditService = auditService;
    }

    @HandleAfterDelete
    public void handleAfterDelete(Order order) {
        auditService.recordDeletion(
                order.getId(),
                order.getOrderNumber());
    }
}
~~~

The AfterDelete method receives the deleted entity. If you need to store details after deletion, extract the necessary values from the entity inside the handler or copy them into a small event object. Do not assume that after deletion, every lazy association on the entity can still be accessed safely.

**AfterDeleteEvent does not mean AFTER_COMMIT.** The repository may have finished the delete call while the transaction wrapping the request has not yet committed. If the transaction later rolls back, the database change may not exist even though the AfterDelete handler already ran.

## 4. Registering an Annotated Event Handler

The recommended approach for domain-specific logic is to create a Spring bean annotated with `@RepositoryEventHandler`, then mark methods with the corresponding annotations.

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final OrderPolicy orderPolicy;
    private final OrderAuditService auditService;

    public OrderDeleteEventHandler(
            OrderPolicy orderPolicy,
            OrderAuditService auditService) {
        this.orderPolicy = orderPolicy;
        this.auditService = auditService;
    }

    @HandleBeforeDelete
    public void beforeDelete(Order order) {
        orderPolicy.assertCanDelete(order);
    }

    @HandleAfterDelete
    public void afterDelete(Order order) {
        auditService.recordDeletion(order.getId());
    }
}
~~~

Key imports:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleAfterDelete;
import org.springframework.data.rest.core.annotation.HandleBeforeDelete;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
~~~

Spring Data REST uses a BeanPostProcessor to detect beans annotated with `@RepositoryEventHandler`, scan methods with event handler annotations, and wire them to the corresponding events.

There are two ways to register the bean:

1. Annotate the class with `@Component` or an equivalent stereotype so component scanning discovers it.
2. Declare the bean with `@Bean` in a configuration class loaded into the ApplicationContext.

Manual declaration example:

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    OrderDeleteEventHandler orderDeleteEventHandler(
            OrderPolicy orderPolicy,
            OrderAuditService auditService) {
        return new OrderDeleteEventHandler(orderPolicy, auditService);
    }
}
~~~

Do not simultaneously use `@Component` and declare an additional bean for the same class, as that can create two instances and cause the handler to run twice.

The type of the first parameter in a handler method determines the domain type the method is interested in. You can declare multiple handler methods for different domain types in one class; use `@RepositoryEventHandler(Order.class)` at the class level to restrict scope when needed.

## 5. Using AbstractRepositoryEventListener Instead of Annotations

Another option is to extend `AbstractRepositoryEventListener` and override callbacks:

~~~java
@Component
public class OrderRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeDelete(Object entity) {
        if (entity instanceof Order order) {
            // Check conditions before deleting Order.
        }
    }

    @Override
    protected void onAfterDelete(Object entity) {
        if (entity instanceof Order order) {
            // Process after Order delete operation.
        }
    }
}
~~~

This approach is useful when you want to centralize multiple types of repository events in a single listener. However, a general listener must check the entity type manually inside the callback. Annotated handlers are usually easier to read and more type-safe when logic applies to only a few domain types.

The corresponding delete callbacks are:

| Event | Callback |
| --- | --- |
| BeforeDeleteEvent | `onBeforeDelete(entity)` |
| AfterDeleteEvent | `onAfterDelete(entity)` |

Do not register both an annotated handler and an AbstractRepositoryEventListener to perform the same side effect unintentionally, because both mechanisms can receive the event.

## 6. Distinguishing Entity Deletion from Removing an Association Link

DELETE on an item resource and DELETE on an association resource are two different operations.

Example:

~~~http
DELETE /api/orders/42
~~~

This request deletes the Order entity with id 42 from the repository. This is the case for BeforeDeleteEvent and AfterDeleteEvent.

Meanwhile:

~~~http
DELETE /api/orders/42/customer
~~~

may only remove the link between Order and Customer. It does not automatically delete the Customer entity from the repository.

Spring Data REST has dedicated events for operations on association links, including:

- `BeforeLinkDeleteEvent`: before a link to a related entity is deleted from the parent.
- `AfterLinkDeleteEvent`: after the related link is deleted from the parent.

Link-delete events can be handled using `@HandleBeforeLinkDelete` and `@HandleAfterLinkDelete`, or the corresponding callbacks in `AbstractRepositoryEventListener`. With callbacks, the listener receives both the parent and the linked entity.

Illustrative example:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderLinkEventHandler {

    @HandleBeforeLinkDelete
    public void beforeCustomerUnlinked(Order order, Customer customer) {
        // Check removing Customer from Order.
    }

    @HandleAfterLinkDelete
    public void afterCustomerUnlinked(Order order, Customer customer) {
        // Record that the association was removed.
    }
}
~~~

Link event handler signatures take two parameters: the parent entity and the linked entity. This differs from BeforeDelete/AfterDelete, which process a single entity being deleted from the repository.

If the business requirement is to actually delete the Customer, the client must call the Customer item resource, and only that operation belongs to the entity delete lifecycle. Do not use link-removal events to act in place of entity deletion.

## 7. AfterDelete and Transaction Commit Timing

Spring application events are processed synchronously by default. That means when the REST exporter publishes an event, listeners typically run immediately on the request processing thread.

High-level sequence:

~~~text
Repository delete
       |
       v
AfterDeleteEvent is published
       |
       v
Synchronous listener runs
       |
       v
Transaction completes / commits or rolls back
~~~

Therefore, the name AfterDelete only indicates that the repository operation has finished. It is not proof that the transaction has committed successfully.

If a listener sends emails, makes HTTP calls to another system, or deletes external data directly inside AfterDelete, the following scenario can happen:

1. The listener executes the external side effect successfully.
2. The database transaction subsequently rolls back.
3. The database still keeps the entity, yet the external system received a deletion notification.

This is why irreversible side effects should not be placed directly inside an AfterDelete handler.

### Using TransactionalEventListener for post-commit actions

You can publish a dedicated application event from the AfterDelete handler, then handle it after the transaction commits:

~~~java
public record OrderDeletedEvent(
        Long orderId,
        String orderNumber) {
}
~~~

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderDeleteEventHandler {

    private final ApplicationEventPublisher publisher;

    public OrderDeleteEventHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @HandleAfterDelete
    public void afterDelete(Order order) {
        publisher.publishEvent(new OrderDeletedEvent(
                order.getId(),
                order.getOrderNumber()));
    }
}
~~~

Listener that only runs after commit:

~~~java
@Component
public class OrderDeletionNotificationListener {

    private final SearchIndexService searchIndexService;

    public OrderDeletionNotificationListener(
            SearchIndexService searchIndexService) {
        this.searchIndexService = searchIndexService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderDeleted(OrderDeletedEvent event) {
        searchIndexService.removeOrder(event.orderId());
    }
}
~~~

Key imports for transaction events:

~~~java
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;
~~~

`@TransactionalEventListener` binds to an active transaction by default. If the event is published outside a transaction, the listener does not run unless `fallbackExecution = true` is enabled. Clarify the request's transaction boundary and test the no-transaction case.

If you need to guarantee that messages are not lost between the database and a message broker, consider a **transactional outbox**: write an outbox record in the same transaction that deletes the entity, and after commit have a worker read the outbox and send the message. An outbox handles retries, crashes, and consistency better than calling external systems directly from an event handler.

## 8. BeforeDelete Does Not Replace Authorization and Service Rules

BeforeDeleteEvent can check business conditions, but it is not the sole security boundary.

For example, disallowing deletion of a paid Order is a domain rule. If the same Order can be deleted from a REST API, scheduled job, message consumer, or internal service, the rule must be shared in the service/domain layer.

Responsibility layers should be distinguished:

- **Spring Security / authorization:** does the caller have permission to delete this resource?
- **Service/domain policy:** does the current state allow deletion?
- **BeforeDeleteEvent:** adds integration logic for the path through the Spring Data REST exporter.
- **Database constraints:** protects data integrity at the storage level.

Do not check permissions solely by inspecting an entity field in a handler. Authorization usually depends on the current user, tenant, ownership, and policy; use Spring Security and an appropriate authorization service.

## 9. Scope of Event Publishing

BeforeDeleteEvent and AfterDeleteEvent are events of the **Spring Data REST exporter**. They are published when operations go through Spring Data REST's repository REST pipeline.

Do not assume that every call to `repository.delete(...)` in the application publishes these events. For instance, a service calling a repository directly, a scheduled task, or a batch job does not automatically pass through the REST exporter.

If logic must run for all deletion paths:

- Place shared business rules and required side effects in a shared service/domain layer.
- Use JPA lifecycle callbacks such as `@PreRemove` or `@PostRemove` for needs tied to JPA entity operations, after understanding their limitations.
- Note that bulk JPQL/native deletes can bypass entity lifecycle callbacks because the database deletes via a bulk statement instead of loading each entity.

Spring Data REST event handlers should be viewed as REST API integration hooks, not an application-wide event bus replacing every lifecycle mechanism.

## 10. Cascade Delete and Related Data

If Order has a `@OneToMany(cascade = CascadeType.REMOVE)` or `orphanRemoval = true` relationship, deleting an Order can cascade to deleting OrderLines. However, do not assume the REST exporter will publish a separate BeforeDelete/AfterDelete pair for every entity deleted via JPA cascade.

The exporter handles the entity sent to the repository delete call. Cascade operations at the ORM layer have their own lifecycle; if each child needs auditing, design the logic in the appropriate service/domain or JPA lifecycle and test with a real database.

In addition, foreign key constraints can cause deletion to fail if dependent entities remain. BeforeDeleteEvent can check ahead of time to return a clear business error, while database constraints remain the final line of defense against invalid referential data.

## 11. Testing BeforeDeleteEvent and AfterDeleteEvent

Test at least three behaviors:

1. A valid DELETE request triggers before and after handlers, and the entity is no longer in the repository afterward.
2. When a BeforeDelete handler rejects the entity by policy, the repository does not delete the entity.
3. The AfterDelete handler only performs the intended side effects and handles transaction boundaries properly.

Example testing HTTP DELETE:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderDeleteResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void deletesOrderThroughRestExporter() throws Exception {
        Order order = orderRepository.save(new Order("PO-42"));

        mockMvc.perform(delete("/api/orders/{id}", order.getId()))
            .andExpect(status().isNoContent());

        assertThat(orderRepository.findById(order.getId())).isEmpty();
    }
}
~~~

Example testing a policy that rejects deletion:

~~~java
@Test
void doesNotDeletePaidOrder() throws Exception {
    Order order = orderRepository.save(
            new Order("PO-PAID", OrderStatus.PAID));

    mockMvc.perform(delete("/api/orders/{id}", order.getId()))
        .andExpect(status().isConflict());

    assertThat(orderRepository.findById(order.getId())).isPresent();
}
~~~

The second example assumes the application maps `OrderDeletionNotAllowedException` to HTTP 409. An appropriate exception handler must be configured; the event handler annotation itself does not dictate status codes for all exceptions.

To test AfterCommit:

- Send DELETE within a real transaction.
- Verify the custom event only triggers the listener after commit.
- Test rollback to confirm post-commit side effects do not execute.
- Test the case where the event is published without a transaction if the application has such a path.

Do not only assert that the listener method was called. Verify database state, the HTTP response, and the final side effect.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Handler does not run | Bean is not component-scanned or not declared in ApplicationContext | Check @Component/@Bean and package scanning |
| Handler runs for unexpected domain types | Handler is not scoped to a domain type | Use @RepositoryEventHandler(Order.class) or specifically typed parameter |
| BeforeDelete runs but entity still exists | Handler threw an exception or repository delete failed | Check exceptions, transactions, and constraints |
| AfterDelete runs but entity remains in database | Transaction subsequently rolled back | Use a transaction-aware listener for post-commit side effects |
| Message sent before commit and database rolled back | External side effect executed synchronously in AfterDelete | Publish a separate event and use AFTER_COMMIT or an outbox |
| Association DELETE does not run BeforeDelete | Request only unlinks an association, not deleting an entity | Use the appropriate link-delete event |
| Deleting entity via service does not publish event | Request does not go through Spring Data REST exporter | Move shared logic to the service/domain layer |
| Handler is invoked twice | Same class registered multiple ways or multiple handlers handle the side effect | Check component scanning and bean declarations |
| Cascaded children lack separate audit | ORM cascade is not individual REST delete requests | Use appropriate domain/JPA lifecycle and test cascade |
| Unexpected HTTP status | Exception from handler is not mapped | Use an exception handler and test the response |

## 13. Choosing the Right Event for Each Need

| Need | Appropriate Mechanism |
| --- | --- |
| Block Order deletion before repository delete | `@HandleBeforeDelete` |
| Record that handler passed through REST exporter delete | `@HandleAfterDelete` |
| Act on entities before/after removing an association | `@HandleBeforeLinkDelete` / `@HandleAfterLinkDelete` |
| Execute side effects only after transaction commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Guarantee durable message publishing after database commit | Transactional outbox |
| Enforce policy across REST, jobs, and services | Shared service/domain layer |
| Track JPA entity lifecycle | `@PreRemove` / `@PostRemove` subject to JPA limitations |

## References

- [Spring Data REST 5.1.2 — Events](https://docs.spring.io/spring-data/rest/reference/events.html): eight repository events, writing ApplicationListener and annotated handlers, bean registration, and synchronous event handling defaults.
- [Spring Data REST 5.1.2 API — BeforeDeleteEvent](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/BeforeDeleteEvent.html): event published before an entity is deleted from the repository.
- [Spring Data REST 5.1.2 API — AfterDeleteEvent](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AfterDeleteEvent.html): event published after an entity is deleted from the repository.
- [Spring Data REST 5.1.2 API — AbstractRepositoryEventListener](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AbstractRepositoryEventListener.html): onBeforeDelete and onAfterDelete callbacks.
- [Spring Data REST 5.1.2 API — Event package hierarchy](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-tree.html): events related to entity deletion and association link deletion.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): using @TransactionalEventListener and transaction phases such as AFTER_COMMIT.
