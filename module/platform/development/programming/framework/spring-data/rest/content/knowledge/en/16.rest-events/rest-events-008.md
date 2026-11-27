# Registering Handlers as Spring Beans and Domain Type Scoping

## Objectives

Spring Data REST publishes repository lifecycle events when clients create, save, delete resources, or modify associations through repository REST endpoints. Applications can listen to these events using a handler class registered as a Spring bean.

Two things need to be clear:

- **Bean registration:** so Spring Data REST finds the handler in the ApplicationContext.
- **Domain type scoping:** using `@RepositoryEventHandler(Person.class)` to specify the domain type the handler serves.

Methods in the handler are marked with annotations such as `@HandleBeforeCreate`, `@HandleAfterCreate`, `@HandleBeforeSave`, or `@HandleAfterSave`. This ensures logic runs at the exact moment in the resource lifecycle without writing separate controllers for each CRUD operation.

## 1. What Is a Repository Event Handler?

A repository event handler is a Spring bean that receives events published by Spring Data REST while processing repository resources.

For example, when a client sends:

~~~http
POST /api/people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

Spring Data REST identifies the collection resource, converts the request body into a Person object, and publishes the appropriate events during creation/saving. A handler registered for the pre-create event can normalize or supplement data; a post-create handler can perform post-processing work.

A handler is not a REST controller:

- It does not declare URLs with `@RequestMapping`.
- It does not directly receive `HttpServletRequest` like a controller.
- It is invoked when Spring Data REST publishes the corresponding event.
- It can use dependencies injected by Spring such as services, clocks, or publishers.

## 2. Registering a Handler as a Spring Bean

Spring Data REST can only discover a handler if that object resides in the Spring ApplicationContext and is marked as a repository event handler.

The common approach is to use `@Component` alongside `@RepositoryEventHandler`:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;

@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // Event handler methods go here.
}
~~~

- `@Component` registers the class as a Spring bean through component scanning.
- `@RepositoryEventHandler` marks the bean as containing methods that handle repository events.
- Spring Data REST locates handler beans in the ApplicationContext and wires methods with the corresponding lifecycle annotations.

The package containing the class must fall within the application's component scan scope. If the class is not scanned, annotations on the class alone are not enough to create a bean.

### Registering with @Bean

If you do not use `@Component`, you can declare the bean explicitly in configuration:

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler(
            PersonService personService) {
        return new PersonEventHandler(personService);
    }
}
~~~

The class still needs to be annotated with `@RepositoryEventHandler` so Spring Data REST recognizes its role. Choose a single bean registration approach; avoid creating multiple instances of the same handler unintentionally.

## 3. Scoping Handlers by Domain Type

An application can export multiple repositories, such as Person, Department, and Order. If a handler only processes Person, specify the domain type on `@RepositoryEventHandler`:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void handlePersonCreate(Person person) {
        // Logic specific to Person.
    }
}
~~~

`Person.class` is the domain type the handler is registered to receive events for. This helps Spring Data REST route events to the right handler, preventing a class from processing the wrong entity type by mistake.

Without explicit type scoping, a handler may be registered more broadly than intended. For applications with multiple aggregates, create separate handlers per domain type or per group of types sharing the same responsibility.

### Domain type scope is not authorization

`@RepositoryEventHandler(Person.class)` only restricts the type of domain object the handler receives. It does not:

- Grant users permission to edit Person.
- Restrict which fields are writable.
- Hide data in responses.
- Replace Spring Security or resource ownership checks.

Authorization must still be configured separately at the security and application/domain service layers.

## 4. Binding Methods to Lifecycle Events

Lifecycle annotations are placed on the handler's methods:

| Annotation | Timing | Example Purpose |
|---|---|---|
| `@HandleBeforeCreate` | Before creating a new resource | Assign default values, normalize input data |
| `@HandleAfterCreate` | After creating a resource | Record post-creation activity |
| `@HandleBeforeSave` | Before saving a resource | Normalize or check state before saving |
| `@HandleAfterSave` | After saving a resource | Emit post-processing signals |
| `@HandleBeforeDelete` | Before deleting a resource | Check conditions before deletion |
| `@HandleAfterDelete` | After deleting a resource | Record or notify after deletion |
| `@HandleBeforeLinkSave` | Before saving association changes | Validate link changes |
| `@HandleAfterLinkSave` | After saving association changes | Post-process link changes |

These annotations correspond to events published by Spring Data REST. Choose the event based on when the logic needs to run; do not use post-operation events if you need to mutate the object before saving.

## 5. Complete Handler Example for Person

The example below normalizes data before creation and update:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.util.StringUtils;

@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    private final PersonService personService;

    public PersonEventHandler(PersonService personService) {
        this.personService = personService;
    }

    @HandleBeforeCreate
    public void handleBeforeCreate(Person person) {
        normalize(person);
        personService.applyCreationDefaults(person);
    }

    @HandleBeforeSave
    public void handleBeforeSave(Person person) {
        normalize(person);
    }

    private void normalize(Person person) {
        if (StringUtils.hasText(person.getFirstName())) {
            person.setFirstName(person.getFirstName().trim());
        }

        if (StringUtils.hasText(person.getLastName())) {
            person.setLastName(person.getLastName().trim());
        }
    }
}
~~~

In this example:

- `@Component` creates the bean.
- `@RepositoryEventHandler(Person.class)` scopes the handler to Person.
- `@HandleBeforeCreate` runs before the create operation.
- `@HandleBeforeSave` runs before the save operation.
- Constructor injection provides PersonService from Spring.
- Normalization logic is extracted into a helper method to avoid duplication.

Handler methods receive the domain object matching the event. Keep method parameters specifically typed, such as Person, to avoid unnecessary casts.

If the same normalization rule is used across multiple entry points (REST, batch, or message consumer), place the core rule in the domain/service and invoke it from the handler. Do not let important business behavior exist only inside a REST callback.

## 6. Distinguishing Before and After

The main difference is when the event is published:

- **Before:** the repository operation has not completed yet. The handler can normalize or modify the object before Spring Data REST proceeds.
- **After:** the corresponding operation has been executed. The handler is suitable for post-processing based on the outcome that just occurred.

Example:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAuditHandler {

    private final AuditService auditService;

    public PersonAuditHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditService.recordCreated(person.getId());
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        auditService.recordSaved(person.getId());
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        auditService.recordDeleted(person.getId());
    }
}
~~~

This example illustrates where to call an audit service. Identify transaction boundaries and system consistency requirements before performing external side effects.

If you need to send emails, call HTTP services, or publish messages to other systems, consider a transactional outbox or an appropriate delivery-guarantee mechanism. Do not assume an external side effect inside a handler is automatically exactly-once or always synchronized with the database transaction.

## 7. Class-Level Type Scoping and Method Parameter Types

The two parts complement each other:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // Handle Person before creation.
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Handle Person after saving.
    }
}
~~~

- The class-level annotation scopes the domain type the handler registers for.
- The method parameter type indicates the object the method handles.
- The lifecycle annotation specifies which event invokes the method.

Keep these three consistent. If a handler is scoped to Person yet a method declares an incompatible domain type, the method may not be invoked as expected or the handler configuration becomes confusing.

If you need to handle Department, you can create a separate `DepartmentEventHandler`:

~~~java
@Component
@RepositoryEventHandler(Department.class)
public class DepartmentEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Department department) {
        department.setName(department.getName().trim());
    }
}
~~~

Splitting handlers by domain type keeps responsibilities bounded and makes dependencies easier to manage.

## 8. How Do Handlers Differ from ValidatingRepositoryEventListener?

Spring Data REST provides both repository event handlers and a validating repository event listener, but they serve different purposes:

| Mechanism | Primary Purpose | Declaration |
|---|---|---|
| Repository event handler | Run custom logic on lifecycle events | Spring bean with `@RepositoryEventHandler` and `@Handle...` |
| ValidatingRepositoryEventListener | Run Spring Validators and record validation errors | Register validators per event in `RepositoryRestConfigurer` |

Example:

- Normalizing names before saving can live in a handler or domain/service.
- Checking invalid data using `Errors` fits a Spring Validator.
- Deciding whether a user may modify Person belongs to authorization.
- Business rules that must always be protected should live in the application/domain service, not solely in a REST handler.

Do not use a repository event handler as an implicit validation mechanism when the goal is returning standardized field errors. Choose the abstraction matching the responsibility.

## 9. When Are Handlers Invoked?

Handlers are invoked when Spring Data REST publishes repository events while processing repository REST resources. Examples of typically related requests:

| HTTP Request | Typically Related Events |
|---|---|
| `POST /api/people` | BeforeCreate / AfterCreate and lifecycle-related save events |
| `PUT /api/people/42` | BeforeSave / AfterSave |
| `PATCH /api/people/42` | BeforeSave / AfterSave |
| `DELETE /api/people/42` | BeforeDelete / AfterDelete |
| Modifying associations | BeforeLinkSave / AfterLinkSave or corresponding link events |

The exact sequence and published events depend on the operation type, resource type, and Spring Data REST version. When you need to rely on a specific event order, verify it with integration tests on your running version.

A call to `repository.save(...)` from a service or batch job should not be assumed by default to pass through the same Spring Data REST event pipeline. If logic must run for every data write, invoke shared service/domain logic at all entry points or use an appropriate persistence event mechanism.

## 10. Common Reasons Handlers Do Not Run

If a request goes through Spring Data REST yet the handler is not invoked, check:

1. Is the handler actually a Spring bean?
2. Is the package containing the handler covered by component scanning?
3. Does the class have `@RepositoryEventHandler`?
4. Does the domain type in `@RepositoryEventHandler(Person.class)` match the exported entity?
5. Does the method have the right lifecycle annotation, such as `@HandleBeforeCreate`?
6. Does the method parameter have the matching domain type?
7. Does the method have visibility/signature compatible with the Spring Data REST version's API?
8. Does the request actually go through a Spring Data REST repository resource?
9. Are multiple handler beans listening to the same event and causing confusion?
10. Is the handler registered twice via both `@Component` and `@Bean`?

To debug, set a breakpoint in the constructor to confirm the bean is created and in the handler method to confirm the event is dispatched. Log event names, domain types, and entity IDs; avoid logging sensitive data.

## 11. Testing Handlers

Handler logic can be tested directly with unit tests:

~~~java
@Test
void trimsPersonNamesBeforeCreate() {
    PersonEventHandler handler =
            new PersonEventHandler(personService);

    Person person = new Person();
    person.setFirstName(" An ");
    person.setLastName(" Nguyen ");

    handler.handleBeforeCreate(person);

    assertThat(person.getFirstName()).isEqualTo("An");
    assertThat(person.getLastName()).isEqualTo("Nguyen");
}
~~~

Unit tests verify method logic. To verify that Spring Data REST publishes events and discovers the bean, you need an integration test that starts the application context and calls the repository REST endpoint:

~~~java
mockMvc.perform(
        post("/api/people")
            .contentType("application/json")
            .accept("application/hal+json")
            .content("""
                {
                  "firstName": " An ",
                  "lastName": " Nguyen "
                }
                """)
    )
    .andExpect(status().isCreated());
~~~

After the request, inspect the persisted data or returned representation to confirm the handler actually ran. Tests should use repository/database test fixtures appropriate for the application.

## 12. Takeaways

- A handler must be a Spring bean for Spring Data REST to detect it.
- `@Component` is the common way to register beans via component scanning; `@Bean` can also be used.
- `@RepositoryEventHandler(Person.class)` scopes the handler to the Person domain type.
- `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleAfterSave`, `@HandleBeforeDelete`, and related annotations select lifecycle events.
- Method parameter types should match the domain object the handler processes.
- Before events fit logic that must run prior to the operation; After events fit post-processing.
- Domain type scoping is not authorization and does not restrict request fields.
- Event handlers serve the Spring Data REST lifecycle; do not assume every repository call from anywhere passes through this pipeline.
- External side effects outside the transaction need clear retry/idempotency and consistency design.

## References

- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST API — RepositoryEventHandler](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST API — HandleBeforeCreate](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/annotation/HandleBeforeCreate.html)
- [Spring Framework — Bean definition and component scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
