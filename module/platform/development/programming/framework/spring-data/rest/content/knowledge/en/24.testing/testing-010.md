# Testing Validation, Events, and Rollback on Processing Failure

## Goal

Spring Data REST exports Spring Data repositories as HTTP resources. When testing a write flow, verify three layers of behavior simultaneously:

1. **Validation:** invalid data is rejected before being persisted.
2. **Lifecycle events:** hooks corresponding to create, update, link, or delete operations are published and handled properly.
3. **Transaction rollback:** if a business operation involving multiple writes fails midway, all changes belonging to the same transaction must be rolled back.

You should have both tests through Spring Data REST HTTP endpoints and transaction tests at the service layer. Calling repositories directly only tests the persistence layer; it does not pass through the full validation and event pipeline of the REST exporter.

The examples below use Java, JUnit Jupiter, Spring Boot, Spring Data REST, and Spring Data JPA. Use dependency versions managed by your project's Spring Boot BOM; package names for some test annotations may differ across Spring Boot generations.

## 1. Preparing Endpoints and Domain Model

Suppose the application has a **Person** entity with **id**, **name**, **email** fields, constructors, and corresponding getters:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String email;

    protected Person() {
    }

    public Person(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

The repository is exported by Spring Data REST as the **/people** endpoint:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    boolean existsByEmail(String email);
}
~~~

Actual URLs also depend on **spring.data.rest.base-path**, repository configuration, and access permissions. In this example, **POST /people** creates a new **Person**, while **PUT** or **PATCH /people/{id}** updates the resource.

## 2. Testing Validation

Spring Data REST supports registering **org.springframework.validation.Validator** in two ways:

- Name the bean by the convention **<event><DomainType>Validator**. For example, **beforeCreatePersonValidator** runs at the **beforeCreate** hook for domain type **Person**.
- Register manually via **RepositoryRestConfigurer.configureValidatingRepositoryEventListener(...)** and **ValidatingRepositoryEventListener.addValidator(...)**.

Bean naming convention is usually the most concise. Example validator requiring email not to be blank:

~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (!StringUtils.hasText(person.getEmail())) {
            errors.rejectValue(
                "email",
                "email.required",
                "Email is required"
            );
        }
    }
}
~~~

Key imports:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;
~~~

For updates, register a validator at the **beforeSave** hook, such as bean **beforeSavePersonValidator**. Creation and updates are two distinct lifecycle points; do not assume a **beforeCreate** validator runs automatically on **PUT** or **PATCH**. To reuse logic, extract validation into a shared class and register it at both hooks.

You can register manually instead of using the bean naming convention:

~~~java
@Configuration
public class RestValidationConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeSave", new PersonValidator());
    }
}
~~~

Avoid registering the same validator using both mechanisms unless you intentionally want it to run twice.

When a validator adds errors to **Errors**, Spring Data REST throws **RepositoryConstraintViolationException**. This is Spring Data REST's dedicated validation exception, extending **DataIntegrityViolationException**; REST exception handling translates the error into an HTTP response for the client. With default configuration, tests typically assert a **400 Bad Request** response. If the application has custom **@ControllerAdvice**, verify status and error structure against the actual API contract.

Example endpoint call:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "email": ""
}
~~~

Outcome to verify: the request is rejected, the response is a client error (typically **400**), and no **Person** record with the submitted email exists in the repository.

## 3. Testing Lifecycle Events

Spring Data REST publishes eight events while processing entities:

| Operation | Before save/delete | After save/delete |
|---|---|---|
| Create entity | **BeforeCreateEvent** | **AfterCreateEvent** |
| Save existing entity | **BeforeSaveEvent** | **AfterSaveEvent** |
| Save link | **BeforeLinkSaveEvent** | **AfterLinkSaveEvent** |
| Delete entity | **BeforeDeleteEvent** | **AfterDeleteEvent** |

There are two ways to handle events:

- Extend **AbstractRepositoryEventListener** and override callbacks such as **onBeforeSave** or **onAfterDelete**. This receives multiple domain object types; the listener must inspect the entity type itself.
- Use **@RepositoryEventHandler** with annotations such as **@HandleBeforeSave**, **@HandleAfterSave**. The type of the method's first parameter determines the domain type, giving the handler strong typing.

Example handler for **Person**:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeSave
    public void beforeSave(Person person) {
        if (!StringUtils.hasText(person.getName())) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Log or perform lightweight internal post-processing after repository save.
    }
}
~~~

Handler annotations belong to package **org.springframework.data.rest.core.annotation**. Handlers must be Spring beans: annotate with **@Component** so component scan picks them up, or declare them via **@Bean**. **@RepositoryEventHandler(Person.class)** restricts the handler to **Person**; if the class argument is omitted, the first parameter type on each method still determines the domain type.

Spring Data REST events are Spring application events and are published synchronously by default. That means synchronous listeners execute on the event-publishing thread. However, **AfterSaveEvent** only indicates the repository performed the save operation; do not treat the event name as proof that the transaction has committed. Also remember that REST lifecycle events belong to the Spring Data REST pipeline: calling repositories directly in a unit test is not equivalent to sending requests through the REST exporter.

### Binding side effects to transactions

If you need to send notifications or run side effects only after the transaction commits successfully, use a dedicated domain/business event and **@TransactionalEventListener**:

~~~java
@Component
public class PersonCreatedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PersonCreated event) {
        // Send notification after the transaction has committed.
    }
}
~~~

**@TransactionalEventListener** runs at **AFTER_COMMIT** by default. You can choose **BEFORE_COMMIT**, **AFTER_ROLLBACK**, or **AFTER_COMPLETION**. If no transaction is active, the listener is not called by default; only enable **fallbackExecution = true** when you genuinely want to handle that case too. An **AFTER_COMMIT** listener cannot force an already-committed transaction back into rollback. For side effects requiring durable delivery guarantees, consider a transactional outbox instead of relying on a network call inside the callback.

## 4. Testing Rollback When Business Processing Fails

By default, Spring transactions mark for rollback when a transactional method throws a **RuntimeException** or **Error**. Checked exceptions do not trigger rollback automatically under default rules. You can explicitly declare checked exceptions that should roll back:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performBusinessOperation() throws BusinessRuleException {
    // Data write operations.
    throw new BusinessRuleException("Business rule failed");
}
~~~

Example service writing to two repositories and then intentionally throwing a runtime exception:

~~~java
@Service
public class PersonWorkflowService {

    private final PersonRepository people;
    private final AuditRepository audits;

    public PersonWorkflowService(
            PersonRepository people,
            AuditRepository audits) {
        this.people = people;
        this.audits = audits;
    }

    @Transactional
    public void createAndFail(String email) {
        people.save(new Person("Lan", email));
        audits.save(new AuditEntry(email, "CREATED"));

        // Simulate failure occurring after write statements.
        throw new IllegalStateException("Simulated workflow failure");
    }
}
~~~

**AuditEntry** is an audit entity with **email** and **action** fields; its corresponding repository can be declared as:

~~~java
public interface AuditRepository extends JpaRepository<AuditEntry, Long> {

    boolean existsByEmail(String email);
}
~~~

When **createAndFail** terminates with an exception, both writes only roll back if they participate in the same transaction manager and same transaction. Tests should invoke the service through an injected Spring bean so the transaction proxy is actually applied. Do not call a transactional method from another method on the same object and expect the proxy to intercept that internal call.

Example independent rollback test:

~~~java
@SpringBootTest
class PersonWorkflowRollbackTest {

    @Autowired
    private PersonWorkflowService workflow;

    @Autowired
    private PersonRepository people;

    @Autowired
    private AuditRepository audits;

    @Test
    void rollsBackAllWritesWhenWorkflowFails() {
        String email = "rollback-" + UUID.randomUUID() + "@example.test";

        assertThatThrownBy(() -> workflow.createAndFail(email))
            .isInstanceOf(IllegalStateException.class);

        assertThat(people.existsByEmail(email)).isFalse();
        assertThat(audits.existsByEmail(email)).isFalse();
    }
}
~~~

Do not place **@Transactional** on this rollback test. Once the service transaction terminates via exception, subsequent assertion queries run and inspect the rolled-back state. Use unique emails so repeated test runs do not interfere with each other.

### Transaction boundaries with Spring Data REST

Validation in **beforeCreate** or **beforeSave** is suitable for rejecting data before the repository saves. For multi-step business logic, such as saving **Person**, saving an audit record, and updating another aggregate, wrap the entire operation sequence in one **@Transactional** service method and let exceptions propagate out of that method.

If a REST lifecycle handler only calls a transactional service after the repository has already saved, the new transaction may start too late to encompass the initial save. To guarantee atomicity of the entire request, design a custom controller/workflow invoking the service as the transaction boundary, or explicitly verify an outer transaction encompasses the full sequence. Do not infer rollback solely from the fact that the handler is invoked synchronously.

Common reasons rollback fails to occur:

- The exception is a checked exception without matching **rollbackFor**.
- Code catches the exception and does not rethrow it, making the transaction interceptor see normal method completion.
- The transactional call is a self-invocation bypassing the proxy.
- Part of the operations uses a different transaction manager or resource.
- Work runs asynchronously or inside an **AFTER_COMMIT** listener, i.e., after the transaction being tested.

## 5. Testing HTTP and Events with MockMvc

**MockMvc** executes full Spring MVC processing using mock requests/responses without starting an HTTP server. It is the right choice for testing Spring Data REST endpoints within the same application context.

Spring TestContext's **@RecordApplicationEvents** (available since Spring Framework 5.3.3) records application events published during each test method. You can accept **ApplicationEvents** as a test parameter and count events by type.

Example of two tests: invalid request rejected and valid request publishing creation events:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
@Transactional
class PersonRestIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private PersonRepository people;

    @Test
    void rejectsInvalidEmail() throws Exception {
        String email = "invalid-" + UUID.randomUUID() + "@example.test";

        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Lan",
                      "email": ""
                    }
                    """))
            .andExpect(status().isBadRequest());

        assertThat(people.existsByEmail(email)).isFalse();
    }

    @Test
    void publishesCreateEvents(ApplicationEvents events) throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Lan",
                      "email": "lan@example.test"
                    }
                    """))
            .andExpect(status().isCreated());

        assertThat(events.stream(BeforeCreateEvent.class).count()).isEqualTo(1);
        assertThat(events.stream(AfterCreateEvent.class).count()).isEqualTo(1);
    }
}
~~~

In the example above, **@Transactional** on the test class rolls back each test method's data after the test ends; MockMvc requests run in a mock environment. If using **@SpringBootTest(webEnvironment = RANDOM_PORT)** or **DEFINED_PORT**, the HTTP client and server run on different threads with separate transactions. The test's transaction then does not roll back transactions executed on the server. Clean up data via fixtures/test databases or verify results through an independent transaction.

When testing updates, pre-create a **Person**, send **PUT** or **PATCH** to **/people/{id}**, then verify **BeforeSaveEvent**/**AfterSaveEvent** and final values. When testing deletes, verify the **BeforeDeleteEvent**/**AfterDeleteEvent** pair and confirm the record no longer exists. Do not check only event counts: inspect the exact domain object and post-request data state.

## 6. Recommended Testing Matrix

| Scenario | Trigger | What to assert |
|---|---|---|
| Valid creation | **POST /people** with valid email | HTTP **201**; record exists; **BeforeCreateEvent** and **AfterCreateEvent** present |
| Invalid creation | **POST /people** missing email | HTTP client error, typically **400**; no record saved |
| Valid update | **PUT** or **PATCH /people/{id}** | Data updated accurately; **BeforeSaveEvent** and **AfterSaveEvent** present |
| Invalid update | **PUT** or **PATCH** with invalid data | Request rejected; previous data intact |
| Save association link | Send association update request | **BeforeLinkSaveEvent**/**AfterLinkSaveEvent** pair present |
| Delete | **DELETE /people/{id}** | Delete event pair present; entity deleted |
| Runtime exception mid-workflow | Service writes multiple repositories then throws exception | All changes in the same transaction disappear |
| Checked exception | Service throws checked exception | Rolls back when **rollbackFor** or global exception rollback rules apply |
| Post-commit listener | Commit or roll back transaction containing event | **AFTER_COMMIT** only executes after successful commit |

## 7. Common Troubleshooting

| Symptom | Causes to check | How to resolve |
|---|---|---|
| Validator does not run on POST | Wrong bean name, bean not scanned, **supports()** returns **false** | Check spelling of **beforeCreatePersonValidator**, component scan, and **Person** type |
| Validator runs on POST but not on PUT/PATCH | Only registered for **beforeCreate** hook | Also register validator for **beforeSave** |
| REST returns error yet data persists | Error occurred after transaction committed, or exception was caught and swallowed | Identify transaction boundary; let exception escape the transaction to roll back |
| Event handler is not invoked | Handler is not a Spring bean, wrong annotation, or wrong parameter type | Register **@Component**/**@Bean**, check **@RepositoryEventHandler** and first parameter |
| Calling repository in unit test shows no REST events | Call path bypasses Spring Data REST exporter | Use MockMvc against endpoint to test REST lifecycle events |
| Runtime exception thrown yet data persists | Writes outside transaction, self-invocation, different transaction manager, or swallowed exception | Call service via proxy, check manager/resources and exception path |
| Checked exception does not roll back | Default rules do not roll back checked exceptions | Use **@Transactional(rollbackFor = ...)** or configure all-exception rollback if appropriate |
| Rollback test still sees data on server | Test uses **RANDOM_PORT**/**DEFINED_PORT**; request runs on separate thread/transaction | Clean up data explicitly or verify via independent transaction on server |
| **AFTER_COMMIT** listener does not run | No active transaction when event is published | Publish event inside transaction; only enable **fallbackExecution** if outside-tx execution is acceptable |

## 8. Pre-Completion Checklist

- [ ] Validators support the right domain type and are registered for the right events (**beforeCreate**, **beforeSave**).
- [ ] Invalid requests return client error statuses and persist no data.
- [ ] Valid requests create/update/delete entities accurately.
- [ ] Tests record the right Spring Data REST lifecycle events for each operation.
- [ ] Handlers are Spring beans and only process intended domain types.
- [ ] Multi-step business operations have clear transaction boundaries.
- [ ] Runtime exceptions escape transactions; checked exceptions have rollback rules if needed.
- [ ] Rollback tests inspect data after the transaction completes, ideally from a test method without an enclosing transaction.
- [ ] Side effects running only after commit are attached to **@TransactionalEventListener** or an appropriate outbox mechanism.
- [ ] HTTP tests use MockMvc or test server matching the objective; never confuse test transaction rollback with server transactions.

## 9. Official Documentation

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): registering validators by bean name or **RepositoryRestConfigurer**.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html): list of lifecycle events, **AbstractRepositoryEventListener**, and **@RepositoryEventHandler**.
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): exception thrown when a Spring **Validator** reports errors.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules for runtime and checked exceptions, **rollbackFor**, and **noRollbackFor**.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): **BEFORE_COMMIT**, **AFTER_COMMIT**, **AFTER_ROLLBACK**, and **AFTER_COMPLETION** phases.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC via mock requests/responses.
- [Spring Framework — Application Events in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): **@RecordApplicationEvents** and **ApplicationEvents** API.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): **@SpringBootTest**, mock web environment, and transaction notes when using a server port.
