# @RepositoryEventHandler and @HandleBefore*, @HandleAfter* Annotations

## 1. What Are Repository Events in Spring Data REST?

Spring Data REST exposes Spring Data repositories as HTTP resources. While processing requests to create, update, modify associations, or delete an entity, the REST exporter publishes corresponding application events.

Repository event handlers allow applications to run logic at those moments without rewriting the entire CRUD controller. For example:

- Normalizing data before an entity is created or saved.
- Recording audit information.
- Checking or adjusting state before an operation.
- Reacting after an entity is created, updated, or deleted.
- Tracking adding, changing, or removing links between resources.

This mechanism belongs to the **Spring Data REST exporter** lifecycle. It should not be treated as an interceptor that automatically runs whenever any service calls a repository. A direct call from a service or a custom MVC controller does not automatically publish these REST repository events.

There are two main approaches:

1. Write a POJO handler annotated with \`@RepositoryEventHandler\`, then bind methods to events using \`@HandleBefore...\` or \`@HandleAfter...\` annotations.
2. Listen to application events using \`ApplicationListener\` or extend \`AbstractRepositoryEventListener\` when more general dispatch control is needed.

For most per-domain-type handling, annotated handlers are concise and easy to read.

## 2. Events in the Resource Lifecycle

Spring Data REST has eight core events for entity operations:

| Event | Handler Annotation | Timing |
|---|---|---|
| BeforeCreateEvent | \`@HandleBeforeCreate\` | Before creating a new entity |
| AfterCreateEvent | \`@HandleAfterCreate\` | After a new entity is created |
| BeforeSaveEvent | \`@HandleBeforeSave\` | Before saving changes to an existing entity |
| AfterSaveEvent | \`@HandleAfterSave\` | After an entity is saved |
| BeforeLinkSaveEvent | \`@HandleBeforeLinkSave\` | Before saving link changes between resources |
| AfterLinkSaveEvent | \`@HandleAfterLinkSave\` | After saving link changes |
| BeforeDeleteEvent | \`@HandleBeforeDelete\` | Before deleting an entity |
| AfterDeleteEvent | \`@HandleAfterDelete\` | After deleting an entity |

Some current Spring Data REST versions also provide events for removing associations:

| Additional Event | Annotation | Meaning |
|---|---|---|
| BeforeLinkDeleteEvent | \`@HandleBeforeLinkDelete\` | Before removing a link from the parent entity |
| AfterLinkDeleteEvent | \`@HandleAfterLinkDelete\` | After removing a link |

The two link-delete events are not present in all older versions. Check the \`org.springframework.data.rest.core.annotation\` package and the API of the release train you are using before relying on them.

### Distinguishing create and save

- **Create** is used when the REST exporter creates a new entity, typically via POST to a collection resource.
- **Save** is used when the exporter saves changes to an existing entity, typically via PUT or PATCH on an item resource.
- **Link save/delete** applies to association resources or operations modifying links between entities.
- **Delete** applies to deleting an entity resource.

Do not infer every event that will run solely from the HTTP method. Verify the actual resource mapping and repository flow of the version in use, especially for associations and custom controllers.

## 3. Role of @RepositoryEventHandler

\`@RepositoryEventHandler\` marks a class as containing methods that handle repository events. Spring Data REST uses a BeanPostProcessor to locate beans with this annotation, scan methods carrying event annotations, and register them with the corresponding events.

A simple handler:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getDisplayName() != null) {
            person.setDisplayName(
                    person.getDisplayName().trim()
            );
        }
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setUpdatedAt(Instant.now());
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // Write logs or emit an internal signal after creation.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // React after the entity is deleted.
    }
}
~~~~

Points to remember:

- The class must be a Spring bean. You can use \`@Component\` or declare a bean with \`@Bean\` in configuration.
- The class must be annotated with \`@RepositoryEventHandler\`.
- Event-handling methods need the corresponding annotation.
- The domain type of the method's first parameter determines which entity type the handler receives.
- You can write multiple methods with the same annotation accepting different domain types.
- The handler is invoked only when the corresponding event is published by the REST exporter.

In current API versions, the domain type is inferred from the first parameter of the handler method. The class-level \`value\` attribute on \`@RepositoryEventHandler\` and type attributes on some handler annotations have been deprecated in newer APIs; prefer declaring parameters with concrete types and check the Javadoc for your project's version.

## 4. Registering Handlers in ApplicationContext

The common practice in Spring Boot is to place the handler in a component-scanned package:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // @HandleBefore... and @HandleAfter... methods
}
~~~~

If the class sits outside scanned packages, you can declare it manually:

~~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler() {
        return new PersonEventHandler();
    }
}
~~~~

Do not both annotate with \`@Component\` and create another \`@Bean\` for the same class. Choose one registration method to avoid creating two handler instances and unintentional duplicate event handling.

If the handler needs a service, repository, or clock, use constructor injection just like normal Spring beans:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    private final PersonPolicy personPolicy;
    private final Clock clock;

    public PersonEventHandler(
            PersonPolicy personPolicy,
            Clock clock) {
        this.personPolicy = personPolicy;
        this.clock = clock;
    }

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        personPolicy.prepareForCreation(person);
        person.setCreatedAt(Instant.now(clock));
    }
}
~~~~

Avoid instantiating dependencies with \`new\` inside handlers because that bypasses dependency injection, proxies, and related Spring configurations.

## 5. Domain Type Scope of a Handler

A single class can handle multiple domain types by declaring concrete types on each method:

~~~~java
@Component
@RepositoryEventHandler
public class AccountEventHandler {

    @HandleBeforeSave
    public void beforeSaveAccount(Account account) {
        // Handle Account.
    }

    @HandleBeforeSave
    public void beforeSaveProfile(Profile profile) {
        // Handle Profile.
    }
}
~~~~

The BeanPostProcessor determines the target domain type from the first parameter of each annotated method. Therefore, use concrete domain types instead of \`Object\` so the handler only receives matching events and the compiler can type-check the domain API.

Documentation for earlier versions often illustrated restricting types using \`@RepositoryEventHandler(Person.class)\` or passing the type into the method annotation. Newer APIs deprecate some of these type attributes and recommend inferring from method parameters. When upgrading Spring Data REST, check the exact Javadoc rather than copying old examples verbatim.

## 6. Using @HandleBefore* to Process Before Operations

Before annotations are invoked prior to the corresponding repository action. This is the appropriate time to normalize the entity, add simple metadata, or perform checks before continuing.

Example normalizing data before creation:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getEmail() != null) {
            person.setEmail(
                    person.getEmail().trim().toLowerCase(Locale.ROOT)
            );
        }

        if (person.getCreatedAt() == null) {
            person.setCreatedAt(Instant.now());
        }
    }
}
~~~~

Example updating an audit timestamp before saving:

~~~~java
@HandleBeforeSave
public void beforeSave(Person person) {
    person.setUpdatedAt(Instant.now());
}
~~~~

Example checking state before deletion:

~~~~java
@HandleBeforeDelete
public void beforeDelete(Person person) {
    if (person.isProtectedAccount()) {
        throw new IllegalStateException(
                "Cannot delete protected account"
        );
    }
}
~~~~

The final example illustrates stopping an operation with an exception. In real applications, use a custom business exception and map it to an appropriate HTTP response. If the check is a standard input constraint, Spring Data REST has a dedicated Validator mechanism; using a validator generally returns clearer field errors than throwing a generic exception.

Do not put heavy queries, network calls, or multi-step use cases into Before handlers. If logic requires coordinating multiple aggregates, access permissions, or complex transactions, move it to an application service and custom controller.

## 7. Using @HandleAfter* to React After Operations

After annotations are invoked after the REST exporter executes the corresponding operation. They are useful for logging, audit events, or emitting internal signals:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(PersonEventHandler.class);

    @HandleAfterCreate
    public void afterCreate(Person person) {
        log.info("Created person with id {}", person.getId());
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        log.info("Saved person with id {}", person.getId());
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        log.info("Deleted person with id {}", person.getId());
    }
}
~~~~

After events help decouple reactions from controllers, but the word "After" should not be taken as a guarantee that the database transaction has committed. Spring Data REST events are Spring application events and are published synchronously by default; where event publication sits relative to transaction commit depends on the application's transaction boundaries.

If you need to send emails, call external services, or publish messages that must reflect a committed change, use an appropriate post-commit mechanism such as \`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)\` with your own application event, or a transactional outbox. Do not let a fragile network call determine the success of a data-saving request.

## 8. Handling Association Changes

A resource can link to other resources through associations. For example, Person has many Roles or Orders. Spring Data REST exposes association resources and publishes dedicated events when links change.

Key handlers:

- \`@HandleBeforeLinkSave\`: before saving a link.
- \`@HandleAfterLinkSave\`: after saving a link.
- \`@HandleBeforeLinkDelete\`: before removing a link, if supported by the version.
- \`@HandleAfterLinkDelete\`: after removing a link, if supported by the version.

Example:

~~~~java
@Component
@RepositoryEventHandler
public class PersonAssociationEventHandler {

    @HandleBeforeLinkSave
    public void beforeLinkSave(Person person) {
        // Check or prepare data before the link is saved.
    }

    @HandleAfterLinkSave
    public void afterLinkSave(Person person) {
        // Record that the link changed.
    }

    @HandleBeforeLinkDelete
    public void beforeLinkDelete(Person person) {
        // Check before removing the association.
    }

    @HandleAfterLinkDelete
    public void afterLinkDelete(Person person) {
        // React after the association was removed.
    }
}
~~~~

The two link-delete annotations can only be used when present in the project's Spring Data REST version. Check the annotation package before adding methods to avoid compile errors on older release trains.

Link event handlers receive domain objects according to the annotation contract. If business logic needs to know the exact association or property that changed, check the specific event API for your version or use a custom controller/service with explicit association parameters; do not assume every handler method automatically receives the property name or related URI.

## 9. Corresponding Before/After Annotations

Commonly used annotations are grouped as follows:

| Group | Annotations |
|---|---|
| Create entity | \`@HandleBeforeCreate\`, \`@HandleAfterCreate\` |
| Save entity | \`@HandleBeforeSave\`, \`@HandleAfterSave\` |
| Save association | \`@HandleBeforeLinkSave\`, \`@HandleAfterLinkSave\` |
| Delete entity | \`@HandleBeforeDelete\`, \`@HandleAfterDelete\` |
| Delete association in supported versions | \`@HandleBeforeLinkDelete\`, \`@HandleAfterLinkDelete\` |

Annotation names map directly to event names. Each method should carry a single clear responsibility and avoid cramming the entire lifecycle into one method.

A class can contain multiple handler methods. If multiple beans register for the same event/domain type, multiple handlers may be invoked; execution order should not be used as a business coordination mechanism unless the application explicitly configures and controls that order.

## 10. Comparing Annotated Handlers and ApplicationListener

Spring Data REST also allows listening to events via standard Spring application event mechanisms.

| Approach | Characteristics | When Suitable |
|---|---|---|
| \`@RepositoryEventHandler\` + \`@Handle...\` | Declarative via annotations, methods accept concrete domain types | Clear entity- and lifecycle-event-specific handling |
| \`ApplicationListener<BeforeSaveEvent>\` | Listens to a specific Spring event type | Needs integration with the application event system |
| \`AbstractRepositoryEventListener<T>\` | Overrides hooks such as onBeforeSave or onAfterDelete | Wants to organize handlers via inheritance and lifecycle hooks |

Annotated handlers automatically infer the domain type from method parameters. With general listeners, the application may need to inspect the entity type manually if the listener receives Object or handles multiple domain types.

Conceptual example with an abstract listener:

~~~~java
@Component
public class PersonRepositoryListener
        extends AbstractRepositoryEventListener<Person> {

    @Override
    protected void onBeforeSave(Person person) {
        // Process before saving.
    }

    @Override
    protected void onAfterDelete(Person person) {
        // Process after deleting.
    }
}
~~~~

Verify the visibility and generic signatures of hooks against the API version in use. Do not register the same business rule in both an annotated handler and another listener unless double execution is intended.

## 11. Event Handlers Do Not Replace Validators or the Service Layer

Although Before handlers can check entities, not every check belongs in an event handler.

- **Bean Validation:** suited for nullability, length, format, and field constraints.
- **ValidatingRepositoryEventListener / Spring Validator:** suited for binding validators to the repository lifecycle and returning validation errors.
- **Domain/application service:** suited for rules depending on current state, user permissions, related data, or multi-step workflows.
- **Database constraints:** protect data integrity at write time.
- **Repository event handlers:** suited for logic tied to the REST exporter lifecycle such as lightweight normalization, auditing, or emitting signals.

Do not treat \`@HandleBeforeSave\` as the sole protector of an important business rule. Services or batch jobs calling repositories directly may not publish REST events, so business invariants should live in the domain/service or database depending on their nature.

## 12. Transactions, Synchronicity, and Side Effects

Spring Data REST events are Spring application events. By default, Spring application events are published synchronously on the same processing thread unless a listener actively switches to async or forwards across another thread/system boundary.

This leads to several considerations:

- Before handlers run on the request path; slow processing slows down the request.
- Synchronous After handlers can also increase response latency.
- Exceptions in handlers can affect request processing; how transactions roll back depends on where the event is published and transaction boundaries.
- Side effects outside the database do not automatically roll back when the database transaction rolls back.
- Retrying a request can duplicate side effects if the handler is not idempotent.

For notifications that must only be sent after commit, write an outbox record in the same transaction and have a separate worker send messages. If using \`@TransactionalEventListener\`, verify actual transactions and fallback configuration when no transaction exists.

Do not treat an event handler as a durable message broker. In-memory application events do not automatically guarantee delivery if the process stops.

## 13. Error Handling and Response Mapping

Before handlers can reject operations by throwing exceptions, but exceptions must be designed clearly:

- Use dedicated business exceptions to distinguish state, conflict, or permission errors.
- Use a Validator for field errors so clients receive field names and error codes.
- Use \`@RestControllerAdvice\` for custom MVC controllers.
- For Spring Data REST, inspect default exception handling and configure matching responses.
- Do not expose stack traces, SQL, tokens, or internal details in responses.

Status codes depend on the error type and exception mapping. Do not assume every exception thrown from a handler becomes HTTP 400; if unmapped, errors may become 500. Write integration tests to verify the exact response clients receive.

## 14. Testing Repository Event Handlers

Test through real HTTP requests because the goal is to verify that the REST exporter publishes events and that the handler is registered.

Example with MockMvc:

~~~~java
mockMvc.perform(post("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("""
            {
              "displayName": "  Alice  "
            }
            """))
    .andExpect(status().isCreated());
~~~~

After the request, verify that the entity was normalized or audit fields were populated according to the handler logic.

Cases to test:

1. POST triggers \`@HandleBeforeCreate\` and \`@HandleAfterCreate\`.
2. PUT/PATCH on an item triggers the appropriate save handlers.
3. DELETE on an item triggers BeforeDelete and AfterDelete.
4. Association operations trigger LinkSave; test link-delete only when supported by the version.
5. Handlers do not receive events for other domain types.
6. Handler beans are component-scanned or registered in ApplicationContext.
7. Exceptions in Before handlers block operations and responses are mapped properly.
8. After handlers do not cause duplicate side effects when requests are retried.
9. Direct repository call paths are not assumed to publish REST events.
10. Transactions and rollbacks are tested in appropriate integration tests.

You can use Mockito to unit test pure handler logic, but unit tests do not prove Spring Data REST publishes events or discovers the bean. At least one integration test is required to verify wiring.

## 15. Common Pitfalls

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Handler is not called | Class is not a Spring bean or lacks \`@RepositoryEventHandler\` | Check component scanning and ApplicationContext |
| Handler receives wrong domain type | Method parameter too general or legacy type config mismatch | Use a concrete entity type for the first parameter |
| BeforeCreate does not run on updates | Create and save are distinct events | Use the annotation matching the lifecycle |
| BeforeSave does not run on creation | Creation publishes BeforeCreate | Register both if logic applies to both create and update |
| Handler runs twice | Same logic registered in multiple handlers/listeners or duplicate beans | Check bean definitions and event registrations |
| Link-delete annotation fails to compile | Spring Data REST version lacks that annotation | Check Javadoc of the actual dependency |
| Exception returns 500 | Exception not mapped per API contract | Use a custom exception and integration tests |
| Calling repository from service does not trigger handler | REST events belong to the REST exporter lifecycle | Move invariants to service/domain or publish custom application events |
| Message sent before commit | Treating After events as if they were after-commit | Use transactional events/outbox |
| Handler slows down requests | Running queries or synchronous network calls | Keep handlers lightweight, offload side effects appropriately |

## 16. Conclusion

\`@RepositoryEventHandler\` marks a Spring bean containing methods that handle lifecycle events published by Spring Data REST. Annotations such as \`@HandleBeforeCreate\`, \`@HandleAfterCreate\`, \`@HandleBeforeSave\`, \`@HandleAfterSave\`, \`@HandleBeforeDelete\`, \`@HandleAfterDelete\`, and the corresponding link annotations hook logic into exact moments of resource processing.

Handlers must be registered in the ApplicationContext, declare clear domain types in method parameters, and only execute within the corresponding REST exporter flow. Use Before events for lightweight normalization or checks, After events for post-operation reactions, while business invariants, field validation, authorization, and post-commit side effects belong in their respective layers. Finally, verify the API for your version and use integration tests to confirm events are actually published and handled as expected.

## References

- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST — HandleBeforeSave API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/HandleBeforeSave.html)
- [Spring Data REST — HandleBeforeLinkDelete API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/HandleBeforeLinkDelete.html)
- [Spring Data REST — Repository event package](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-summary.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
