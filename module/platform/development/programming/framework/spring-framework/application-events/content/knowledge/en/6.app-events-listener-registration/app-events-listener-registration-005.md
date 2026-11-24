# Parent and Child Context Listeners in Spring

Spring allows an application to have multiple ApplicationContexts organized in a parent–child relationship. Each context manages its own beans and listeners. When an event is published in a child context, Spring dispatches the event in the child context first, then forwards the same event to the parent context. This forwarding direction only travels upward through the context tree: an event emitted in the parent does not automatically travel down to the child, and an event from one child is not sent to another sibling.

Properly understanding these two distinct parts — **bean scope** and **event propagation path** — helps avoid missed listeners, duplicate processing, or running startup logic multiple times.

## 1. What are parent and child ApplicationContexts?

An ApplicationContext can set another context as its parent using setParent(...). The child context can look up beans provided by the parent. The parent cannot look up beans declared only in the child.

For example, a classic Spring MVC application may organize contexts as follows:

- **Root context (parent):** services, repositories, datasources, and shared components.
- **DispatcherServlet context (child):** controllers, handler mappings, view resolvers, and servlet-specific web configuration.

The child can use services in the parent. The parent does not depend on controllers that exist only in the child.

This relationship forms a context tree. An application can have multiple children pointing to one parent, or multiple parent–child levels. Each ApplicationContext still has its own lifecycle, BeanFactory, and ApplicationEventMulticaster.

## 2. Event propagation rules between contexts

When an event is published, Spring follows these rules:

1. The context where publishEvent() is called sends the event to listeners registered in that context itself.
2. If the context has a parent, Spring calls publishEvent() on the parent with the same event.
3. The parent dispatches the event to the parent's listeners, and continues forwarding up to higher-level parents if any.
4. The process stops at the root context because that context has no parent.

    Root context
    [Root listeners]
           ^
           | event from child propagates upward
      +----+----+
      |         |
    Child A  Child B
    [A listeners] [B listeners]

A publish: A listeners -> Root listeners
B publish: B listeners -> Root listeners
Root publish: Root listeners

Key consequences to remember:

| Event origin | Listeners that can receive it |
|---|---|
| Child A | Child A listeners, then parent and ancestor listeners |
| Child B | Child B listeners, then parent and ancestor listeners |
| Parent | Parent and ancestor listeners; does not travel down to children |
| Root | Only listeners in Root |

There is no horizontal path between two children. If Child A emits an event, Child B does not receive that event merely because both share a parent. The parent can receive events from both children and perform shared processing.

The forwarded event is the exact same object. Spring does not create a copy or a new wrapper just to forward an event to the parent. Therefore, listeners should not mutate event state after publishing; multiple contexts may observe the same object.

## 3. Each context has its own multicaster and listener set

ApplicationEventMulticaster is the component that dispatches events for an ApplicationContext. A listener registered in a given context is managed by that context's multicaster.

This means:

- Listeners registered in the child are called when the child receives an event.
- Listeners registered in the parent are called when the parent receives an event, including when the event originated in the child and was forwarded upward.
- A parent listener does not automatically become a local listener of the child.
- A child listener does not automatically become a listener of the parent.

Bean visibility and event routing are two different mechanisms. A child can inject a service bean from the parent, but that does not mean listeners declared in the parent are additionally registered in the child's multicaster. When the child publishes an event, the parent receives the event due to upward forwarding.

Both listeners implementing ApplicationListener and methods using @EventListener follow the registration scope of the context that owns them. @EventListener is converted by Spring into a listener adapter inside the context where the bean containing that method is instantiated.

## 4. Example: event from child is received by parent

The Java example below creates two AnnotationConfigApplicationContexts. The parent is refreshed first; the child sets its parent and then refreshes. Each context registers a listener for the same event type.

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ParentChildEventsDemo {

    public static void main(String[] args) {
        try (var parent = new AnnotationConfigApplicationContext()) {
            parent.setId("parent");

            parent.addApplicationListener(
                (ApplicationListener<NoticeEvent>) event ->
                    System.out.println(
                        "parent listener: " + event.getMessage()
                    )
            );

            parent.refresh();

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setId("child");
                child.setParent(parent);

                child.addApplicationListener(
                    (ApplicationListener<NoticeEvent>) event ->
                        System.out.println(
                            "child listener: " + event.getMessage()
                        )
                );

                child.refresh();

                child.publishEvent(
                    new NoticeEvent(child, "from child")
                );

                parent.publishEvent(
                    new NoticeEvent(parent, "from parent")
                );
            }
        }
    }

    static final class NoticeEvent extends ApplicationEvent {
        private final String message;

        NoticeEvent(Object source, String message) {
            super(source);
            this.message = message;
        }

        String getMessage() {
            return message;
        }
    }
}
~~~

With the default multicaster running listeners synchronously, the output is:

~~~text
child listener: from child
parent listener: from child
parent listener: from parent
~~~

Explanation:

- The first publish is called on the child. The child listener runs first; then the child forwards the event to the parent so the parent listener also runs.
- The second publish is called on the parent. The parent listener runs, while the child listener is not called because the parent does not propagate events downward.
- No listener in any other context is called outside this path.

This is a standalone example of event routing. It requires no component scan configuration; listeners are registered directly before refresh to make clear which context owns each listener.

## 5. Context lifecycle events are also forwarded to the parent

Events such as ContextRefreshedEvent, ContextStartedEvent, ContextStoppedEvent, and ContextClosedEvent extend ApplicationContextEvent. They carry the ApplicationContext that emitted the event.

When a child refreshes or closes, the corresponding event is published by the child and forwarded to the parent. Consequently, a listener in the root context can receive ContextRefreshedEvent from both the root itself and child contexts.

For example, in a system with one root context and two DispatcherServlet contexts, a listener in the root can receive multiple ContextRefreshedEvents:

- One event when the root context refreshes.
- One event when the first servlet's child context refreshes.
- One event when the second servlet's child context refreshes.

Do not assume every ContextRefreshedEvent means the entire application has just finished starting up. This event describes a specific ApplicationContext completing refresh. In a context tree, each context may refresh at a different time.

Similarly, when a child closes, the parent can receive the child's ContextClosedEvent. That does not mean the parent has closed as well. Inspect the context inside the event before taking lifecycle-dependent actions.

## 6. Identifying which context emitted the event

### With ApplicationContextEvent

Lifecycle events provide getApplicationContext(). A listener can compare the context in the event with the context to which the bean belongs.

Example of a listener that only wants to run when the root context finishes refreshing:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class RootRefreshListener {

    private final ApplicationContext ownContext;

    RootRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }

        System.out.println("Root context refreshed");
    }
}
~~~

If the listener bean is created in the root context, the ApplicationContext injected into the bean is the root context. When the parent receives an event from a child, the identity comparison does not match and the listener ignores that event.

You can compare context IDs instead of object identity when correlating via logs or configuration. However, context IDs must be set explicitly and uniquely in the context tree; do not assume every context has a useful or unique ID if the application does not configure them.

### With custom events

A custom event extending ApplicationEvent does not automatically have getApplicationContext(). ApplicationEvent only provides getSource(), and source can be a service or publisher bean. Do not assume source is always a context.

If a listener needs to know where an event originated, include that information in the event contract. You can pass a context ID, tenant ID, or an appropriate origin identifier:

~~~java
import org.springframework.context.ApplicationEvent;

public final class DataImportedEvent extends ApplicationEvent {
    private final String contextId;
    private final int importedRows;

    public DataImportedEvent(
            Object source,
            String contextId,
            int importedRows) {
        super(source);
        this.contextId = contextId;
        this.importedRows = importedRows;
    }

    public String getContextId() {
        return contextId;
    }

    public int getImportedRows() {
        return importedRows;
    }
}
~~~

Another option is to intentionally use ApplicationContext as the source when the event genuinely describes context activity. Whichever approach you choose, document the meaning of source clearly in the contract; do not rely on an implicit convention that listeners cannot safely depend on.

## 7. Avoiding duplicate processing when listeners exist in both parent and child

A common situation is having the same listener class component-scanned in both the root context and a child context. When the child emits an event:

1. The child's listener handles the event in the child multicaster.
2. The event is forwarded to the parent.
3. The listener of the same class in the parent handles the event again.

If both listeners send emails, write data, or update the same resource, side effects can happen twice.

How to prevent this:

- **Separate component scan scopes:** the root context only scans packages containing services, repositories, and shared components; the child scans controller packages and its web configuration.
- **Place listeners in an intentional context:** if handling is shared across all children, register the listener in the parent; if it belongs only to a specific servlet, register it in the child.
- **Filter by origin:** for lifecycle events, check getApplicationContext(); for custom events, use a context ID or defined metadata.
- **Design idempotent handlers:** if the same event can be observed from multiple places or replayed, repeated handling must not produce incorrect side effects. You can use an event ID and deduplication lock when business logic requires it.

Do not rely solely on bean names to guess which context a listener runs in. Check where the bean is actually instantiated and which context owns the multicaster that dispatched it.

## 8. Listener ordering and asynchronous processing

By default, SimpleApplicationEventMulticaster invokes listeners synchronously on the event-publishing thread. When the child publishes an event, child dispatch completes before the forwarding call to the parent begins. Therefore, in the synchronous example, the output shows the child listener before the parent listener.

You can use @Order or Ordered to order listeners within the same multicaster. However:

- @Order only orders within the listener list of a single multicaster.
- It does not establish a global order across all parent and child listeners.
- If the multicaster is configured with an async executor, the order in which listeners start or complete is no longer guaranteed by dispatch order alone.
- Do not use event propagation to coordinate a mandatory chain of tasks with result dependencies.

If an operation requires the parent to finish before the child or needs a result from a listener to proceed, use a service/interface or an explicit orchestration workflow. Event propagation is suited for notification and reaction, not as an RPC mechanism between contexts.

## 9. Transactions and the same event forwarded to the parent

The parent receives the same event object that the child published. Forwarding the event to the parent does not automatically create a new transaction, does not copy a transaction context, and does not turn the event into a durable message.

With synchronous listeners running on the same thread, a listener in the parent can be invoked while the child's publishing flow is still active. If an event is emitted inside a transaction, a synchronous listener may run before the transaction ends. Consider @TransactionalEventListener when the reaction needs to be tied to a transaction phase, such as AFTER_COMMIT.

If a listener uses @Async or the multicaster runs on a separate executor, the publishing thread's transaction context is not automatically transferred to the handling thread. Transactions and error handling for async listeners must be designed separately.

Forwarding events from child to parent also provides no retries or delivery guarantees if the process stops. If work must be processed even after a failure, use an outbox/message broker or an appropriate durable storage mechanism instead of relying solely on the ApplicationContext hierarchy.

## 10. How to verify parent-child event routing

A small test can confirm the event propagation direction and prevent misunderstandings:

1. Create a parent context and register a listener for NoticeEvent.
2. Refresh the parent before creating or refreshing the child.
3. Set the parent via child.setParent(parent), then register a separate listener on the child.
4. Publish NoticeEvent from the child; verify both the child listener and parent listener receive it.
5. Publish NoticeEvent from the parent; verify only the parent listener receives it.
6. If there are Child A and Child B, publish from A; verify B does not receive it.
7. Trigger ContextRefreshedEvent via an actual refresh; check whether the listener in the parent filters by the source context properly.
8. If a listener is scanned in both contexts, verify that duplicate processing can occur and adjust the registration scope.

In large applications, logs should record context ID, event type, and event ID. This helps distinguish events emitted from root, a servlet context, or another child, especially when multiple contexts refresh close together.

## 11. Common mistakes

**Assuming parent listeners are automatically registered in the child.** Parent beans can be looked up by the child, but listeners still belong to the parent's multicaster. The child receives the parent's event only when the parent itself publishes; the event direction does not go down to the child.

**Assuming child events are only handled in the child.** Spring forwards events up to the parent. If a shared listener exists in both contexts, it may run twice.

**Assuming siblings receive each other's events.** Child A does not publish directly to Child B. Events only travel from A up to the parent; the parent does not re-emit them back down to B.

**Using ContextRefreshedEvent as the sole application-ready signal.** Each context can refresh independently. If you need the point when a Spring Boot application is ready, consider ApplicationReadyEvent and clearly identify which context or application lifecycle you care about.

**Relying on event.getSource() to obtain ApplicationContext.** A custom event's source can be a publisher bean. Only ApplicationContextEvent provides getApplicationContext() by contract; custom events need their own origin metadata if required.

**Relying on @Order for ordering across parent–child.** @Order applies within a single multicaster. If global ordering across contexts is needed, create a single coordination point.

**Using mutable events or modifying payload inside a listener.** Parent and child can receive the same object. Mutating state inside a listener can cause a listener in a later context to see modified data. Prefer immutable events and read-only payloads.

## 12. Rules to remember

- Child publishes: child listeners first, then parent and ancestors.
- Parent publishes: parent and ancestors; does not go down to children.
- Two siblings do not receive each other's events merely by sharing a parent.
- Each context has its own multicaster and listener set.
- Bean visibility from parent to child does not mean listeners are registered in both contexts.
- Lifecycle events carry the originating ApplicationContext; custom events need their own metadata convention.
- If a listener appears in both parent and child, check for duplicate processing risk.
- Listeners are synchronous by default; async changes completion timing and error handling.

**Key takeaway:** events travel up the ApplicationContext tree. A child can notify its parent; a parent does not broadcast events down to children. Place listeners in the right context, filter by source context when needed, and design handlers to tolerate receiving events from multiple children.

## References

- [AbstractApplicationContext — Spring Framework source](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
- [ApplicationContext — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContext.html)
- [ApplicationContextEvent — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [ApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)