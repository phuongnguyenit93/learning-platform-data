# BeforeLinkSaveEvent and AfterLinkSaveEvent When Modifying Associations

Spring Data REST provides repository events so applications can hook into the REST resource processing lifecycle. When a client modifies an association between two entities, two key events are BeforeLinkSaveEvent and AfterLinkSaveEvent.

BeforeLinkSaveEvent is published before a link to a related entity is saved on the parent resource. AfterLinkSaveEvent is published after that link has been saved on the parent. With these two extension points, an application can validate business rules before changing relationships and run follow-up processing after the linking operation.

## 1. Modifying an Association Differs from Saving an Entity

Suppose a purchase order has many products. PurchaseOrder is the parent entity, and Product is the linked entity:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @ManyToMany
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

The purchase order repository is exposed:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

When reading order 42, the HAL representation can provide an association link:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "items": {
      "href": "http://localhost:8080/api/orders/42/items"
    }
  }
}
~~~

A client can use the association resource to add an existing product to the order:

~~~http
POST /api/orders/42/items
Content-Type: text/uri-list

http://localhost:8080/api/products/7
~~~

This operation modifies the relationship between PurchaseOrder and Product. It differs from POST /api/products, which creates a new Product in the repository collection.

Because this is a link-save operation, Spring Data REST can publish BeforeLinkSaveEvent and AfterLinkSaveEvent. These events let the application handle relationship rules without putting all logic into a controller.

## 2. What Is BeforeLinkSaveEvent?

BeforeLinkSaveEvent is published before a linked object is saved on the parent in the repository. The event carries two objects:

- **Parent:** the entity that owns the association, passed as the event source.
- **Linked object:** the entity being linked to the parent, accessible via getLinked().

In the order example, the parent is PurchaseOrder 42 and the linked object is Product 7.

This is the appropriate time to check rules that must hold before the relationship changes:

- The order must be in a status that allows adding products.
- The product must be active.
- The product must belong to the right warehouse or tenant.
- The user must have permission to modify the product list.
- Quantities or link limits must satisfy business rules.

If a rule is violated, the handler can reject the operation with a business exception. The application should map the exception to an appropriate HTTP status using its error-handling mechanism, such as 409 Conflict or 422 Unprocessable Entity.

BeforeLinkSaveEvent is not a new Product creation event. It focuses on linking an already resolved entity to a parent resource.

## 3. What Is AfterLinkSaveEvent?

AfterLinkSaveEvent is published after the linked object has been saved on the parent in the repository.

In our example, once Product 7 is linked to PurchaseOrder 42, the application can use this event to:

- Log or audit the addition of the product.
- Update necessary aggregate metrics.
- Send information to another component.
- Record association change history.
- Trigger a follow-up business workflow.

AfterLinkSaveEvent also carries the parent and linked object. Determining the two objects works the same way as in BeforeLinkSaveEvent.

Do not use AfterLinkSaveEvent to reject an invalid link, because by that point the link save operation has already taken place. Conditions that can block the operation should be checked in BeforeLinkSaveEvent or in a business service before updating.

It is also important to distinguish AfterLinkSaveEvent from AfterSaveEvent:

| Event | Objects of Interest | Timing |
|---|---|---|
| BeforeLinkSaveEvent | Parent and linked object | Before saving the link. |
| AfterLinkSaveEvent | Parent and linked object | After saving the link on the parent. |
| BeforeSaveEvent | Entity being saved | Before saving the entity. |
| AfterSaveEvent | Entity being saved | After the entity save operation. |

If a client only modifies an association, link-save events identify the exact operation taking place instead of having to infer it from a general save event.

## 4. Creating an Annotated Event Handler

The common way to handle repository events is to create a Spring bean annotated with @RepositoryEventHandler. Methods annotated with @HandleBeforeLinkSave and @HandleAfterLinkSave receive the corresponding events.

Example:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterLinkSave;
import org.springframework.data.rest.core.annotation.HandleBeforeLinkSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderLinkEventHandler {

    @HandleBeforeLinkSave
    public void beforeLinkSave(
            PurchaseOrder order,
            Product product) {

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new OrderLinkNotAllowedException(
                "Only orders in DRAFT status can add products"
            );
        }

        if (!product.isActive()) {
            throw new OrderLinkNotAllowedException(
                "Cannot add an inactive product"
            );
        }
    }

    @HandleAfterLinkSave
    public void afterLinkSave(
            PurchaseOrder order,
            Product product) {

        // Record that the product was linked to the order.
    }
}
~~~

Key points to understand in this example:

- @Component registers the handler in the Spring ApplicationContext.
- @RepositoryEventHandler(PurchaseOrder.class) scopes the handler to events of the PurchaseOrder domain type.
- @HandleBeforeLinkSave marks the method that runs before saving the link.
- @HandleAfterLinkSave marks the method that runs after saving the link.
- The first parameter is the parent entity; the second parameter is the linked object.
- The first parameter's type helps Spring Data REST determine the domain type the method cares about.

If the application uses multiple domain types, you can create a separate handler per parent to keep logic clear and avoid handling associations by mistake.

## 5. Registering Handlers in Spring

A handler must be a Spring-managed bean so Spring Data REST can discover event-handling methods.

There are two common approaches.

**Using @Component**

~~~java
@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderLinkEventHandler {
    // Event handler methods.
}
~~~

This works when the handler's package falls under the Spring Boot application's component scan scope.

**Declaring with @Bean**

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PurchaseOrderLinkEventHandler purchaseOrderLinkEventHandler() {
        return new PurchaseOrderLinkEventHandler();
    }
}
~~~

Only one bean registration mechanism is needed. Do not declare the same handler via both component scanning and an extra @Bean simultaneously, as that can create two instances and cause logic to execute twice.

Spring Data REST's BeanPostProcessor inspects beans annotated with @RepositoryEventHandler, finds methods with event handler annotations, and wires them to the corresponding repository events.

## 6. Handling Events with AbstractRepositoryEventListener

Apart from annotated handlers, you can extend AbstractRepositoryEventListener to override callbacks.

Example:

~~~java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderRepositoryEventListener
        extends AbstractRepositoryEventListener<PurchaseOrder> {

    @Override
    protected void onBeforeLinkSave(
            PurchaseOrder parent,
            Object linked) {

        if (parent.getStatus() != OrderStatus.DRAFT) {
            throw new OrderLinkNotAllowedException(
                "Order does not allow modifying products"
            );
        }
    }

    @Override
    protected void onAfterLinkSave(
            PurchaseOrder parent,
            Object linked) {

        // Process after the link is saved.
    }
}
~~~

The two key callbacks are:

- onBeforeLinkSave(parent, linked): runs before the link is saved.
- onAfterLinkSave(parent, linked): runs after the link is saved.

Unlike an annotated handler that can declare its second parameter as Product, AbstractRepositoryEventListener callbacks receive linked as Object. If you need to handle multiple linked object types, check the type before casting.

Example:

~~~java
if (linked instanceof Product product) {
    // Handle Product.
}
~~~

Extending the listener is useful when you want to centralize multiple callbacks in one class. Annotated handlers are usually easier to read when you want to declare both the domain type and linked type explicitly on each method.

Pick one implementation approach per processing flow to avoid registering duplicate logic.

## 7. Distinguishing Link Save Events from Regular Create/Save Events

Spring Data REST has events for the entity lifecycle and events dedicated to associations.

Example:

| HTTP Operation | Events of Interest |
|---|---|
| POST /api/products | BeforeCreateEvent and AfterCreateEvent. |
| PUT or PATCH /api/products/7 | BeforeSaveEvent and AfterSaveEvent. |
| POST to an order's association resource | BeforeLinkSaveEvent and AfterLinkSaveEvent. |
| Modifying parent entity via repository item resource | BeforeSaveEvent and AfterSaveEvent. |

The table above describes typical flows. Actual events depend on the request, exposed associations, and how Spring Data REST handles the repository.

For instance, when a client creates a new Product, a beforeCreate handler is appropriate for validating Product data before saving. When a client adds an existing Product to a PurchaseOrder, a beforeLinkSave handler is appropriate for checking the linking rules between the two entities.

Do not place all Product validation rules into beforeLinkSave if those rules must also apply when a Product is created via the repository collection. In that case, use beforeCreate or beforeSave for entity rules and beforeLinkSave for association-specific rules.

## 8. Controlling Transactions and Side Effects

Spring application events are processed synchronously by default. Therefore, handlers typically run on the request thread when Spring Data REST publishes the event.

This has several consequences:

- Logic in handlers can slow down the request.
- Exceptions from pre-save processing can prevent the operation from proceeding.
- Errors raised in post-save processing can affect the request outcome depending on transaction and exception handling.
- AfterLinkSaveEvent indicates the link save operation occurred, but should not automatically be assumed to mean the database transaction has committed.

For lightweight tasks like internal auditing, a post-save handler can be an appropriate starting point. For sending emails, calling other HTTP services, or publishing messages to external systems, consider post-commit mechanisms such as @TransactionalEventListener with TransactionPhase.AFTER_COMMIT when the event is published inside an appropriate transaction, or use a transactional outbox.

Example post-commit listener:

~~~java
@Component
public class OrderLinkCommittedListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterLinkCommit(AfterLinkSaveEvent event) {
        PurchaseOrder order =
            (PurchaseOrder) event.getSource();

        Object linked = event.getLinked();

        // Publish notification after the transaction commits.
    }
}
~~~

This approach requires the event to be published within an active transaction. If there is no transaction, the listener does not run by default; configure fallbackExecution only when that is genuinely the desired behavior.

If you need to guarantee that messages are not lost between committing data and sending the message, a transactional outbox is usually better suited than calling external systems directly from a callback.

## 9. Things to Keep in Mind When Validating Associations

When writing logic for BeforeLinkSaveEvent and AfterLinkSaveEvent, identify both sides of the relationship accurately:

- Parent is the entity owning the association being changed.
- Linked object is the entity being referenced or added to the association.
- For bidirectional JPA relationships, understand the owning side and mappedBy.
- If the same parent has multiple association types, check the exact linked type and business property.
- Do not assume every entity modification publishes link-save events; only link-saving operations through the corresponding Spring Data REST flow trigger these events.

For example, if PurchaseOrder has both items and approver, the two link types may require different rules. The handler can check order status and linked object type, or split logic by domain type and business service.

Do not use event handlers to replace access control checks. Whether a user is allowed to modify an order should be checked using Spring Security or service authorization. Handlers can enforce domain consistency rules, while ensuring other write paths outside Spring Data REST apply the same rules.

## 10. Practice and Verification Workflow

Suppose order 42 is in DRAFT status and needs product 7 added:

1. GET /api/orders/42 to confirm the parent resource exists and obtain the association link.
2. GET /api/products/7 to confirm the product exists.
3. Send POST to the association href with Content-Type text/uri-list and the product URI in the body.
4. Set a breakpoint in beforeLinkSave to verify parent and linked object are passed correctly.
5. Test the case where the order is not in DRAFT status; the handler must reject the operation.
6. With a valid product and DRAFT order, verify beforeLinkSave is called before the link is saved.
7. Verify afterLinkSave is called after the association is saved on the parent.
8. GET /api/orders/42 or the association resource again to verify the link state.
9. Check transactions and logs if the post-save handler performs side effects.

You can test by trying to add an inactive product or changing the order status to CONFIRMED. These cases confirm that pre-save rules are enforced properly.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Handler is not called | Bean is not registered or method lacks annotation. | Check component scanning, @Bean, and handler annotations. |
| Handler receives wrong domain type | First parameter is not the parent entity used by the event. | Put parent as the first parameter and check @RepositoryEventHandler. |
| Casting linked object fails | Association links to multiple different domain types. | Use the exact type for the association or check instanceof. |
| BeforeLinkSave does not run on entity creation | Handling create events instead of association events. | Use BeforeCreate/BeforeSave for entities and BeforeLinkSave for relationships. |
| Exception returned as 500 | Business exception not mapped to an appropriate HTTP status. | Use an exception handler to return an appropriate status and error body. |
| Message sent before transaction commit | Treating AfterLinkSaveEvent as an after-commit event. | Use AFTER_COMMIT or a transactional outbox for external tasks. |
| Relationship not persisted as expected | JPA mapping or owning side not updated properly. | Check owning side, mappedBy, and transactions. |

BeforeLinkSaveEvent is the checkpoint before an association is saved; AfterLinkSaveEvent is the processing point after the link is saved on the parent. Register handlers for the right domain type, accept parent and linked object in the right order, and place business validation before the operation and side effects at the appropriate timing. That way, the application can control relationship changes in Spring Data REST while keeping logic clearly organized around the association lifecycle.

## References

- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [BeforeLinkSaveEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/BeforeLinkSaveEvent.html)
- [AfterLinkSaveEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AfterLinkSaveEvent.html)
- [LinkedEntityEvent API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/LinkedEntityEvent.html)
