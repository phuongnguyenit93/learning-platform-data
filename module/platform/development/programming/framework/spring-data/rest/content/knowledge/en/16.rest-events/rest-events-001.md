# REST Exporter Event Lifecycle and Processing Extension Points in Spring Data REST

Spring Data REST automatically exposes Spring Data repositories as REST resources. When a client creates, updates, modifies an association, or deletes an entity through these endpoints, the REST exporter publishes corresponding events during processing. Applications can listen to those events to normalize data, validate business rules, record activities, or trigger additional processing.

Common extension points include:

- **Annotated event handler** with @RepositoryEventHandler and @HandleBefore... / @HandleAfter... annotations for domain-specific handling.
- **AbstractRepositoryEventListener** to receive centralized lifecycle callbacks and dispatch by entity type manually.
- **ValidatingRepositoryEventListener** to attach Spring Validators at specific points in the request.

These events belong to the Spring Data REST exporter processing flow. They are not general persistence callbacks and do not automatically run whenever any service or batch job calls a repository directly.

## 1. Event Lifecycle Overview

When a client sends a request to a repository resource, Spring Data REST resolves the repository, loads or instantiates the entity, binds the request data, and publishes the appropriate events around the repository operation.

High-level flow:

~~~text
HTTP request
    |
    v
Spring Data REST exporter
    |
    v
Resolve repository and entity
    |
    v
Bind request data
    |
    v
Before event / validation
    |
    v
Repository operation
    |
    v
After event
    |
    v
HTTP response and HAL representation
~~~

The specific events depend on the operation:

- POST to a collection resource creates a new entity and goes through the Create group.
- PUT or PATCH to an item resource saves changes and goes through the Save group.
- Adding or replacing an association goes through the Link Save group.
- Removing an association has Link Delete callbacks in supported API versions.
- DELETE on an item resource goes through the Delete group.

Before callbacks run prior to the corresponding repository operation. After callbacks run after that operation. The word After does not mean the database transaction has committed or that the HTTP response has been sent successfully.

## 2. REST Exporter Events

The core entity lifecycle events include:

| Event | Timing | Target | Common Purpose |
|---|---|---|---|
| BeforeCreateEvent | Before the first save of a new entity | New entity | Normalize data, assign default values |
| AfterCreateEvent | After the new entity is saved | Newly created entity | Record creation activity, trigger follow-up processing |
| BeforeSaveEvent | Before saving an entity | Entity about to be saved | Validate or normalize updated data |
| AfterSaveEvent | After the entity is saved | Saved entity | Record changes, produce synchronization info |
| BeforeLinkSaveEvent | Before saving an association | Parent entity and linked entity | Validate relationship before linking |
| AfterLinkSaveEvent | After saving an association | Parent entity and linked entity | Record recently changed association |
| BeforeDeleteEvent | Before deleting an entity | Entity about to be deleted | Check deletion conditions |
| AfterDeleteEvent | After deleting an entity | Deleted entity | Record deletion, notify other systems |

The Spring Data REST API also has callbacks and annotations for link deletion, such as onBeforeLinkDelete, onAfterLinkDelete, @HandleBeforeLinkDelete, and @HandleAfterLinkDelete in supported versions. Check the Javadoc matching your application's exact dependency version before using these hooks.

## 3. Distinguishing Create, Save, Link, and Delete

### Create: creating a new entity

When a client POSTs to a collection resource, the REST exporter creates a domain object and saves it via the repository.

~~~http
POST /people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

BeforeCreate is suitable for normalizing data or assigning server-managed properties before the first save. AfterCreate is suitable for recording that a new entity has been created.

### Save: saving an existing entity

When a client updates an item resource using PUT or PATCH, the REST exporter processes the existing entity and saves the changes.

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

BeforeSave can validate data or recalculate derived properties before saving. AfterSave can record changes after the repository has performed the save operation.

Create and Save should not be treated as a single event. If logic depends on whether an entity is newly created or an existing entity is updated, place it in the proper callback.

### Link Save: adding or replacing an association

Suppose Person has an association to Address. A client can assign an address through the association resource:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

BeforeLinkSave and AfterLinkSave receive both the parent entity and the linked entity. This allows the handler to check the specific relationship, such as whether an address is allowed to be assigned to this person.

### Link Delete: removing an association

When the API and Spring Data REST version support link-delete events, a handler can observe the relationship removal operation:

~~~http
DELETE /people/42/address
~~~

Removing an association does not mean deleting the Address entity. Link-delete callbacks help the application check or record the relationship that was just removed. Verify the actual association endpoint and callbacks exposed in the running version.

### Delete: deleting an entity

When a client DELETEs an item resource:

~~~http
DELETE /people/42
~~~

BeforeDelete is suitable for checking business conditions before deletion. AfterDelete is suitable for recording the operation after the repository has deleted the entity.

If you need to reject a deletion operation, perform the check in BeforeDelete, a Validator, or service/domain logic. AfterDelete occurs after the repository operation, so it is not the appropriate place to prevent deletion.

## 4. Annotated Handlers with @RepositoryEventHandler

This is the direct approach when logic is tied to a single domain type. Create a Spring bean, annotate it with @RepositoryEventHandler, and place event annotations on its methods.

~~~java
import java.time.Instant;

import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.HandleBeforeDelete;
import org.springframework.data.rest.core.annotation.HandleAfterDelete;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;

@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        person.setCreatedAt(Instant.now());
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // Record that Person was just created.
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setDisplayName(
            person.getFirstName() + " " + person.getLastName()
        );
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Record that Person was just saved.
    }

    @HandleBeforeDelete
    public void beforeDelete(Person person) {
        // Check business conditions before deleting.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // Record that Person was deleted.
    }
}
~~~

The methods receive Person directly, so they can access domain properties without casting from Object.

### Handling associations in annotated handlers

For link events, the first parameter is the parent entity and the second parameter is the linked entity:

~~~java
@HandleBeforeLinkSave
public void beforeAddressLink(Person person, Address address) {
    // Check whether the address is allowed to be linked to this person.
}

@HandleAfterLinkSave
public void afterAddressLink(Person person, Address address) {
    // Record the recently updated association.
}
~~~

If the version supports link-delete annotations:

~~~java
@HandleBeforeLinkDelete
public void beforeAddressUnlink(Person person, Address address) {
    // Check before removing the association.
}

@HandleAfterLinkDelete
public void afterAddressUnlink(Person person, Address address) {
    // Record that the association was removed.
}
~~~

Do not mix up the order of the two parameters: parent is the entity that owns the association, and linked entity is the object on the other side of the relationship.

## 5. How Spring Data REST Discovers Handlers

A handler must be a bean in the ApplicationContext. It can be registered via component scanning:

~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // Event methods
}
~~~

Or declared as a bean in configuration:

~~~java
@Configuration
public class RestEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler() {
        return new PersonEventHandler();
    }
}
~~~

Spring Data REST uses event handler configuration and bean post-processing to locate methods annotated with @Handle... on @RepositoryEventHandler beans.

The domain type is determined from the type of the method's first parameter. For link events, the first parameter is the parent and the second parameter is the linked entity. Declare concrete types so the handler only receives matching events.

If a class has multiple methods for multiple domain types, keep each method clearly focused on a single event type and domain. Avoid putting too much unrelated processing in one handler.

## 6. Using AbstractRepositoryEventListener

When you want to centralize multiple lifecycle callbacks in a general listener, you can extend AbstractRepositoryEventListener.

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;

@Component
public class RepositoryLifecycleListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeCreate(Object entity) {
        if (entity instanceof Person person) {
            // Prepare Person before creation.
        }
    }

    @Override
    protected void onAfterSave(Object entity) {
        if (entity instanceof Person person) {
            // Process after Person is saved.
        }
    }

    @Override
    protected void onBeforeDelete(Object entity) {
        if (entity instanceof Person person) {
            // Check before deleting Person.
        }
    }

    @Override
    protected void onBeforeLinkSave(Object parent, Object linked) {
        if (parent instanceof Person person
                && linked instanceof Address address) {
            // Check Person - Address association.
        }
    }

    @Override
    protected void onAfterLinkDelete(Object parent, Object linked) {
        if (parent instanceof Person person
                && linked instanceof Address address) {
            // Record that the association was removed.
        }
    }
}
~~~

A general listener receives Object and checks the type manually. For entity events, the callback receives the entity. For link events, the callback receives the parent and linked object.

This approach fits when you need to centralize callbacks across multiple domain types. If the logic belongs to only one specific domain, an annotated handler is usually easier to read and has clearer parameter types.

## 7. Choosing a Handler or a Listener

| Criterion | @RepositoryEventHandler | AbstractRepositoryEventListener |
|---|---|---|
| Parameter types | Can declare a specific domain type | Usually receives Object or a general type |
| Domain filtering | Based on method parameter type | Checked manually inside the callback |
| Organization | Separate methods per event and entity | Single class centralizing multiple callbacks |
| Best suited for | Domain-specific logic | General listener across multiple domains |

Do not implement both approaches simultaneously for the same business rule. If the same logic is registered in both places, it can run twice and produce duplicate side effects.

## 8. Validation with ValidatingRepositoryEventListener

When the goal is to validate data and reject the request if invalid, use a Spring Validator bound to the event.

Example validator for Person on creation:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreatePersonValidator")
public class PersonCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getEmail() == null
                || person.getEmail().isBlank()) {
            errors.rejectValue(
                "email",
                "email.required",
                "Email is required"
            );
        }
    }
}
~~~

The bean name following the convention beforeCreatePersonValidator binds the validator to the beforeCreate event of Person. You can use corresponding event names such as beforeSave or beforeDelete if validation is needed at those stages.

You can also register a validator manually via RepositoryRestConfigurer:

~~~java
@Configuration
public class RestRepositoryConfiguration
        implements RepositoryRestConfigurer {

    private final PersonCreateValidator validator;

    public RestRepositoryConfiguration(
            PersonCreateValidator validator) {
        this.validator = validator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", validator);
    }
}
~~~

ValidatingRepositoryEventListener connects the validator to the event. When validation detects errors, the request can be rejected before the repository operation and return errors according to the application's validation handling mechanism.

Use a Validator for data validation rules. Use an event handler for domain processing or side effects. Both mechanisms can be combined if each has a distinct responsibility.

## 9. Choosing the Right Extension Point

Not all logic belongs in a REST event handler.

| Need | Appropriate Extension Point |
|---|---|
| Normalize data when REST creates an entity | BeforeCreate handler |
| Validate data when REST updates | Validator or BeforeSave handler |
| Record operations after REST create/update/delete | After event handler |
| Validate or record association changes | Link event handler |
| Business logic that must run from REST, batch, and service | Service or domain layer |
| Audit created/modified date and user | Spring Data auditing |
| Customize GET representation | Projection, serializer, or custom controller |
| Endpoint with custom request/response | Custom controller or custom repository implementation |

REST events are only published by the REST exporter in the REST flow. If a business rule must be enforced regardless of whether the entity is modified via REST, service, batch job, or message consumer, place the core rule in the service/domain layer.

JPA lifecycle callbacks such as @PrePersist, @PostPersist, @PreUpdate, and @PreRemove belong to the persistence provider. They are distinct from Spring Data REST events and have their own trigger scope. Spring Data auditing is also a separate mechanism for recording metadata such as created date and modified date.

## 10. Transactions and Side Effects

Spring application events are processed synchronously by default if the application does not configure an event multicaster or an asynchronous forwarding mechanism. Therefore:

- Long-running handlers can extend HTTP response latency.
- Exceptions in handlers can affect the request depending on where the event is published and the transaction boundary.
- An After event indicates that the corresponding repository operation has run; it does not automatically guarantee that the database transaction has committed.
- Sending emails or calling external services directly in a callback can produce side effects even if the database transaction later rolls back.

For side effects that must execute after data has committed, consider TransactionalEventListener at the AFTER_COMMIT phase or a transactional outbox. Inspect the actual transaction boundary before choosing a mechanism.

For messages or tasks that may be retried, design consumers and side effects to be idempotent. Do not treat an After callback as an exactly-once guarantee.

## 11. Limitations to Keep in Mind

- REST events do not run automatically when Java code calls a repository directly.
- The main lifecycle events do not provide a general read callback for every GET.
- After does not mean after commit.
- Link events have two targets: parent and linked entity.
- Handlers do not replace Spring Security or authorization in the service layer.
- Before events or Validators are suitable for rejecting operations; After events run after the repository operation.
- The ordering of multiple handlers should not be assumed unless explicitly configured by the application.
- If multiple handlers modify the same entity, define clear responsibilities and avoid overwriting each other.
- Link-delete callback APIs may vary by Spring Data REST version; check your actual dependency and Javadoc.

## 12. Testing the Event Lifecycle

You should test through HTTP integration tests to verify that the REST exporter publishes the right events and that handlers are registered.

Cases to test:

1. POST a Person and verify BeforeCreate/AfterCreate are called.
2. PUT or PATCH a Person and verify BeforeSave/AfterSave are called.
3. Link an Address to a Person and verify LinkSave receives the correct parent and linked entity.
4. Unlink an association and verify LinkDelete callbacks if supported by the version in use.
5. DELETE a Person and verify BeforeDelete/AfterDelete.
6. Submit invalid data and verify the Validator rejects it before saving.
7. Call the repository directly from a service and verify core business logic still runs without depending on REST events.
8. Verify transaction rollback when a callback throws an exception.
9. Verify external side effects are not sent before commit if the business rule requires after-commit.
10. Verify handlers do not run twice due to duplicate registration.

You can use Mockito to verify that a service is called from a handler. Integration tests with a database help verify entity and association state after the request. If there is asynchronous processing, also test the recorded message and how the consumer handles retries.

## 13. Implementation Workflow

1. Identify the REST operation to extend: create, save, link save/delete, or delete.
2. Choose Before or After based on when processing is needed.
3. Choose an annotated handler for domain-type-specific logic or AbstractRepositoryEventListener for general callbacks.
4. Register the handler in the ApplicationContext via component scanning or bean configuration.
5. Use a Validator bound to the event if the goal is data validation.
6. Place shared business rules in the service/domain layer.
7. Determine the transaction boundary before calling external systems or publishing messages.
8. Use after-commit or an outbox if side effects must be tied to a database commit.
9. Write HTTP integration tests for each event and verify the data after the operation.

## 14. Key Takeaways

- Spring Data REST publishes events around create, save, link, and delete operations in the REST exporter.
- The eight core entity lifecycle events are Before/After Create, Before/After Save, Before/After Link Save, and Before/After Delete.
- Versions that support link deletion add Before/After Link Delete callbacks and annotations.
- @RepositoryEventHandler with @Handle... is the way to declare handlers by domain type; for link events, the two parameters are the parent and linked entity, respectively.
- AbstractRepositoryEventListener provides general callbacks and fits when handling multiple domain types in a single listener.
- ValidatingRepositoryEventListener lets you bind Spring Validators to events by bean name or manual registration.
- REST events do not replace service/domain logic, JPA lifecycle callbacks, or Spring Data auditing.
- Events run synchronously by default; an After callback does not automatically guarantee that the transaction has committed.
- Test over HTTP to confirm handlers are triggered properly and data is saved as expected.

## References

- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — AbstractRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AbstractRepositoryEventListener.html)
- [Spring Data REST — RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — ValidatingRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/ValidatingRepositoryEventListener.html)
