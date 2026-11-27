# Writing Listeners with ApplicationListener and AbstractRepositoryEventListener

Spring Data REST publishes repository events while processing exported resources. Applications can listen to these events to normalize entities, record changes, or trigger auxiliary work. Two common implementation approaches are using Spring's `ApplicationListener<E>` for a specific event and extending `AbstractRepositoryEventListener<T>` to receive multiple types of repository events through callbacks.

Both approaches participate in the Spring application event mechanism. The main difference lies in how events are selected and how code is organized: `ApplicationListener` receives the event class declared in its generic type; `AbstractRepositoryEventListener` dispatches repository events to hooks such as `onBeforeSave` and `onAfterSave`.

## 1. Spring Data REST Repository Events

Spring Data REST publishes events around CRUD and association operations. Commonly used events include:

| Event | Timing |
|---|---|
| `BeforeCreateEvent` | Before creating a new entity |
| `AfterCreateEvent` | After the entity creation operation |
| `BeforeSaveEvent` | Before saving an entity |
| `AfterSaveEvent` | After repository save returns |
| `BeforeLinkSaveEvent` | Before saving an association |
| `AfterLinkSaveEvent` | After saving an association |
| `BeforeLinkDeleteEvent` | Before deleting an association |
| `AfterLinkDeleteEvent` | After deleting an association |
| `BeforeDeleteEvent` | Before deleting an entity |
| `AfterDeleteEvent` | After the entity deletion operation |

For example, when a client updates an item resource using PUT or PATCH, the flow normally publishes `BeforeSaveEvent` before the save operation and `AfterSaveEvent` after repository save returns. POST creating a new entity goes through Create events; operations on associations have their own Link events.

These events are hooks into the Spring Data REST flow. A custom controller calling a repository directly does not automatically publish the same Spring Data REST repository events. If the same behavior is needed across multiple write paths, place shared business logic in the service/domain layer and call that service from the appropriate entry points.

## 2. First Approach: Implementing ApplicationListener

`ApplicationListener<E>` is Spring's interface for receiving a single application event type. When declaring the generic type as `BeforeSaveEvent`, the listener is registered to receive events before saving an entity.

Example listener handling only `Person`:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.event.BeforeSaveEvent;

@Component
public class PersonBeforeSaveListener
        implements ApplicationListener<BeforeSaveEvent> {

    @Override
    public void onApplicationEvent(BeforeSaveEvent event) {
        Object source = event.getSource();

        if (!(source instanceof Person)) {
            return;
        }

        Person person = (Person) source;
        person.setDisplayName(
            person.getDisplayName().trim()
        );
    }
}
```

Notable points:

- The generic type `BeforeSaveEvent` defines which event type the listener is interested in.
- `event.getSource()` returns the entity object attached to the event; the return value must be type-checked before casting.
- A `BeforeSaveEvent` can relate to multiple exported domain types. Checking `instanceof` ensures the listener applies only to the entity it is responsible for.
- The `onApplicationEvent` method is where handling for that event lives.

To receive `AfterSaveEvent`, create a separate listener with the corresponding generic type:

```java
@Component
public class PersonAfterSaveListener
        implements ApplicationListener<AfterSaveEvent> {

    @Override
    public void onApplicationEvent(AfterSaveEvent event) {
        Object source = event.getSource();

        if (!(source instanceof Person)) {
            return;
        }

        Person person = (Person) source;
        // Record details after repository save returns.
    }
}
```

A single class cannot simultaneously implement both `ApplicationListener<BeforeSaveEvent>` and `ApplicationListener<AfterSaveEvent>` as two distinct generic interfaces because Java type erasure gives both signatures the same erasure. Splitting into two concrete beans is usually clearer. If you want a single point receiving multiple events, you can listen to a common event supertype and branch using `instanceof`, while keeping the event scope narrow and handling each type explicitly.

## 3. Second Approach: Extending AbstractRepositoryEventListener

`AbstractRepositoryEventListener<T>` is an abstract class that already implements `ApplicationListener<RepositoryEvent>`. It receives repository events and dispatches them by event type to protected callbacks. Instead of writing a long `onApplicationEvent` with multiple branches, the application only overrides the hooks it needs.

Example:

```java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class PersonRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        if (!(entity instanceof Person)) {
            return;
        }

        Person person = (Person) entity;
        person.setDisplayName(
            person.getDisplayName().trim()
        );
    }

    @Override
    protected void onAfterSave(Object entity) {
        if (!(entity instanceof Person)) {
            return;
        }

        Person person = (Person) entity;
        // Record or publish an application event after save.
    }
}
```

In this example, the listener uses `Object` and checks the entity type explicitly. This approach is safe when the listener needs to observe multiple domain types or wants full control over entity filtering. If you use a specific generic type such as `AbstractRepositoryEventListener<Person>`, verify the type-filtering behavior of the Spring Data REST version you are running; do not rely on compile-time generics as an authorization or validation mechanism.

Available callbacks include:

| Callback | Dispatched Event |
|---|---|
| `onBeforeCreate(T entity)` | `BeforeCreateEvent` |
| `onAfterCreate(T entity)` | `AfterCreateEvent` |
| `onBeforeSave(T entity)` | `BeforeSaveEvent` |
| `onAfterSave(T entity)` | `AfterSaveEvent` |
| `onBeforeLinkSave(T parent, Object linked)` | `BeforeLinkSaveEvent` |
| `onAfterLinkSave(T parent, Object linked)` | `AfterLinkSaveEvent` |
| `onBeforeLinkDelete(T parent, Object linked)` | `BeforeLinkDeleteEvent` |
| `onAfterLinkDelete(T parent, Object linked)` | `AfterLinkDeleteEvent` |
| `onBeforeDelete(T entity)` | `BeforeDeleteEvent` |
| `onAfterDelete(T entity)` | `AfterDeleteEvent` |

For association hooks, `parent` is the parent entity and `linked` is the linked object. This parameter pair is useful when recording what was attached to or removed from a relationship.

There is no need to override every callback. Only implement the events the application actually needs to handle; the remaining hooks can be left with their default implementations.

## 4. Comparing the Two Approaches

| Criterion | ApplicationListener | AbstractRepositoryEventListener |
|---|---|---|
| Registration | Implement `ApplicationListener<EventType>` | Extend the abstract listener class |
| Event scope | Usually focused on one event type per listener | Multiple repository events via callbacks |
| Handling entry point | `onApplicationEvent(event)` | `onBeforeSave`, `onAfterSave`, and other hooks |
| Event branching | Written manually if listening to a general event type | Superclass dispatches by event type |
| Entity filtering | Check source manually when needed | Uses generic type and/or explicit entity check depending on version/implementation |
| Best suited when | Caring about one specific event or needing direct event API control | Consolidating multiple CRUD/association callbacks into one listener |

Use `ApplicationListener` when handling a single distinct event and you want the code to show the exact event type right in the class declaration. Use `AbstractRepositoryEventListener` when you need one listener with multiple lifecycle hooks and want to avoid dispatching each event manually.

Both are Spring beans. Add `@Component` or register the bean via configuration so Spring manages the listener. If the bean is not in the application context or its package is not component-scanned, events will not reach the listener.

## 5. Filtering for the Right Domain Type

A Spring Data REST application typically exports multiple repositories. Therefore, a listener receiving events must process only the right entity types.

With `ApplicationListener<BeforeSaveEvent>`, the event's source should be checked before casting:

```java
if (!(event.getSource() instanceof Person)) {
    return;
}

Person person = (Person) event.getSource();
```

With `AbstractRepositoryEventListener`, you can choose a concrete generic type if the listener is responsible for a single domain type and the framework version supports resolving that type. If the listener uses `Object` to accept multiple entity types, always check the type inside the callback before accessing fields.

Do not use repository names or URLs to infer object types at runtime when the event already provides the source entity. Direct type checking is clearer and less coupled to endpoint structure.

Type filtering is also not permission checking. The listener only decides which entities to apply logic to; authentication and authorization must still be handled in Spring Security or the appropriate business layer.

## 6. When to Choose Listeners Over @RepositoryEventHandler?

Spring Data REST also supports declaring handlers with `@RepositoryEventHandler` and annotations such as `@HandleBeforeSave` and `@HandleAfterSave`. This uses a POJO with annotated handler methods and allows binding domain types via annotations so the framework filters handlers by entity type.

The three approaches can be selected by need:

- `ApplicationListener`: suitable when you need to receive a Spring event class directly.
- `AbstractRepositoryEventListener`: suitable when you want to override a group of lifecycle callbacks in the same class.
- `@RepositoryEventHandler`: suitable when you want to declare annotated handler methods and filter by domain type.

Do not register multiple mechanisms to perform the same side effect for the same event unless you control their joint invocation. For example, if an email is sent from both `ApplicationListener` and `@HandleAfterSave`, a single update could send two emails.

## 7. Execution Order, Transactions, and Side Effects

Spring application events are normally processed synchronously on the publishing thread under default configuration. Applications can customize the event multicaster or listener execution; if asynchronous processing is configured, ordering and transaction context may differ. Do not rely on execution order between multiple listeners unless explicitly configured and tested.

`AfterSaveEvent` means repository save has returned; it does not automatically prove an outer transaction has committed. If tasks must run only after commit, use a transaction-aware listener such as `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` when the event is published inside an appropriate transaction, or design a transactional outbox for high-reliability messaging.

Some guidelines:

1. Keep callbacks short and avoid calling long-running network services on the request thread.
2. Do not send emails, process payments, or publish irreversible messages before understanding the transaction boundary.
3. Design side effects to tolerate retries or duplicate events.
4. Use an outbox and consumer deduplication when durable message delivery is required.
5. If a listener throws an exception, response and rollback behavior depend on where the event was published, transaction boundaries, and exception policies; test against your actual configuration.

A listener is a lifecycle extension point, not an automatic background queue. If a task takes significant time, publish an appropriate event/application command and hand off processing to an async or messaging mechanism with error management.

## 8. Testing Listeners

Unit tests calling callbacks directly only verify logic inside the method. They do not prove that Spring registered the bean or that Spring Data REST publishes events during real requests.

Include integration tests through real endpoints or an appropriate test context:

- PUT/PATCH an entity: verify before-save and after-save are called properly.
- POST a new entity: verify Create events, not confused with Save events.
- Modify an association: verify LinkSave or LinkDelete callbacks.
- Trigger events with another entity type: verify the listener ignores it when out of scope.
- Before-save listener rejects or throws an exception: verify the request does not complete as a successful write.
- After-save publishes an application event: verify transaction behavior and side effects.
- If async or multiple listeners are configured: verify ordering, errors, and transaction context under that configuration.

You can use spy/mock beans to verify that callbacks were invoked, but you should also inspect final repository state to ensure the listener not only ran but produced the expected result.

## 9. Implementation Checklist

1. Identify the specific event to handle: create, save, link save/delete, or delete.
2. Use `ApplicationListener<EventType>` if you only need to receive one event class directly.
3. Use `AbstractRepositoryEventListener<T>` if you want to override multiple repository lifecycle callbacks.
4. Register the listener as a Spring bean in the application context.
5. Check the source entity before casting and restrict processing to the right domain type.
6. Do not register multiple listeners performing the same side effect unintentionally.
7. Distinguish repository save completion from transaction commit.
8. Use an after-commit listener or outbox when external work must run after commit.
9. Test listeners through real Spring Data REST requests, including other entity types and handler errors.

`ApplicationListener` allows handling a single Spring event type directly; `AbstractRepositoryEventListener` provides built-in callbacks for multiple repository lifecycle events. Choosing the right fit for the number of events to track, filtering entities explicitly, and controlling transactions/side effects makes listeners in Spring Data REST easier to maintain and reason about.
