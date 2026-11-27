# Providing the Actor with AuditorAware

In Spring Data JDBC, auditing helps record who created or updated an aggregate. The **@CreatedBy** and **@LastModifiedBy** annotations mark the properties holding the actor; **AuditorAware<T>** provides the current actor value to the auditing infrastructure.

AuditorAware is the bridge between the identity authenticated by the application and auditing metadata. It does not authenticate users itself, does not create accounts, and does not guess identities. The application is responsible for resolving the actor from Spring Security, a service account, or a background task context.

This lesson explains how to configure AuditorAware for Spring Data JDBC, integrate with Spring Security, choose an actor identifier, and understand the limitations when writing data via direct SQL.

## 1. What Is AuditorAware?

AuditorAware<T> belongs to the org.springframework.data.domain package. The interface provides a single method:

~~~java
public interface AuditorAware<T> {
    Optional<T> getCurrentAuditor();
}
~~~

T is the data type representing the actor. For example:

- AuditorAware<String> when storing a username or string user code.
- AuditorAware<UUID> when storing a UUID user ID.
- AuditorAware<Long> when the system uses a long integer ID.
- AuditorAware<User> if the model and mapping actually persist a suitable User object.

The method returns Optional<T> because not every operation has a logged-in user. A scheduled task, migration, batch import, or system process may not have an Authentication attached to a request.

Spring Data auditing calls AuditorAware when it needs to populate annotated auditor fields. The interface simply supplies the identity that the application has resolved at save time.

## 2. Distinguishing Auditor Fields from Time Fields

Auditing typically records two groups of information:

| Group | Annotation | Meaning |
|---|---|---|
| Actor | @CreatedBy | Actor who created the aggregate |
| Actor | @LastModifiedBy | Actor who performed the most recent update |
| Time | @CreatedDate | Timestamp when the aggregate was created |
| Time | @LastModifiedDate | Timestamp of the most recent update |

AuditorAware only provides actor values for @CreatedBy and @LastModifiedBy. It does not provide time. Spring Data auditing uses DateTimeProvider or the default clock to populate date/time fields.

Example aggregate root entity:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        @CreatedBy String createdBy,
        @LastModifiedBy String lastModifiedBy,
        @CreatedDate Instant createdAt,
        @LastModifiedDate Instant lastModifiedAt
) {}
~~~

When saving a new aggregate, auditing can populate the creating actor and creation time. When saving an existing aggregate, auditing updates the last-modifying actor and modification time according to the auditing configuration.

## 3. Enabling Auditing for Spring Data JDBC

Spring Data JDBC provides the @EnableJdbcAuditing annotation to register the auditing infrastructure.

Configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {
}
~~~

The auditorAwareRef attribute explicitly names the AuditorAware bean that auditing will use. The name auditorProvider must match the declared bean name.

If the application has only one matching AuditorAware bean, Spring Data can auto-detect that bean depending on the configuration mechanism of the version in use. Declaring auditorAwareRef explicitly is often easier to read when the application has multiple auditor sources or multiple persistence configurations.

@EnableJdbcAuditing activates Spring Data JDBC's auditing mechanism. Simply placing @CreatedBy on an entity without enabling auditing is not enough for values to be populated automatically.

## 4. Providing a Simple AuditorAware

If the application has not yet integrated Spring Security or only needs a fixed actor for a specific task, you can declare a bean:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Every operation handled by auditing in this configuration will receive the actor system. This approach is helpful for examples or applications with a single system actor, but is unsuitable when distinguishing among multiple real users is required.

Do not hard-code a fixed username across the entire application if audit logs are used for accountability tracing. The auditor value should reflect the true identity source of the operation.

## 5. Retrieving the Current Auditor from Spring Security

In web applications using Spring Security, the authenticated user is typically represented by an Authentication in SecurityContextHolder. AuditorAware can read the Authentication at the moment auditing needs the value.

Example using the principal name:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
                        SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> !name.isBlank());
    }
}
~~~

Processing steps:

1. Retrieve the current Authentication from SecurityContextHolder.
2. If there is no Authentication, the Optional is empty.
3. Only accept an authenticated Authentication.
4. Exclude AnonymousAuthenticationToken because an anonymous user is not a logged-in actor.
5. Obtain the identifier name via Authentication.getName().
6. Filter out blank names before returning the auditor.

Do not only check that authentication is non-null. An application may automatically create an anonymous authentication; without excluding it, auditing could record anonymousUser as if it were a real user.

Authentication.getName() typically returns the username, subject, or identifier name depending on the authentication mechanism. Verify that this value matches the application's audit column contract.

## 6. Storing a Stable ID or Username?

An important design choice is whether to store a display username or an immutable user ID.

| Auditor value | Advantages | Limitations |
|---|---|---|
| Username | Easy to read in logs, easy to look up manually | Can be renamed or reused |
| Email | Easy to recognize in small systems | Can change and is usually personal data |
| User ID (UUID/Long) | Stable, suitable for linking to user tables | Requires a lookup to display the name |
| Service/client code | Distinguishes tasks performed by service accounts | Requires naming conventions and service identity lifecycle management |

If auditing serves long-term traceability, prefer a stable, unique ID. You can store both the actor ID and a display name snapshot if business requirements demand reading history without looking up current user info.

Example entity storing UUID:

~~~java
@CreatedBy
private UUID createdBy;
~~~

Then the bean must declare the same generic type:

~~~java
@Bean
AuditorAware<UUID> auditorProvider() {
    return () -> currentUserId();
}
~~~

Do not declare AuditorAware<String> and expect Spring to automatically convert a username into a UUID or Long. The auditor's generic type must be compatible with the property type annotated with @CreatedBy/@LastModifiedBy and the corresponding mapping converters.

## 7. Extracting User ID from a Custom Principal

In real applications, Authentication often contains a custom principal holding a user ID. For example:

~~~java
public record AppPrincipal(
        UUID userId,
        String username
) {}
~~~

AuditorAware can extract the ID:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentUserAuditorAware implements AuditorAware<UUID> {

    @Override
    public Optional<UUID> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        Object principal = authentication.getPrincipal();

        if (principal instanceof AppPrincipal appPrincipal) {
            return Optional.of(appPrincipal.userId());
        }

        return Optional.empty();
    }
}
~~~

Register the bean:

~~~java
@Bean
AuditorAware<UUID> auditorProvider() {
    return new CurrentUserAuditorAware();
}
~~~

This avoids depending on a username that might change. If the application supports multiple principal types (UserDetails, JWT, service account), handle each type explicitly. Do not call toString() on an arbitrary principal and store the result as an actor ID; toString() is not a stable identification contract.

## 8. DDL and Data Types Must Match the Auditor

For an entity using a String auditor:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    created_by VARCHAR(120),
    last_modified_by VARCHAR(120),
    created_at TIMESTAMP,
    last_modified_at TIMESTAMP
);
~~~

Audit columns must have names and types compatible with the entity mapping. If using UUID, the physical column must have type UUID or a compatible type according to the database/driver and configured converters.

Example:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_by UUID,
    last_modified_by UUID
);
~~~

UUID and timestamp type syntax varies across databases. Adjust the DDL to match your actual DBMS and naming strategy.

### Should NOT NULL Be Set on Auditor Columns?

Only set NOT NULL if every data-creation path has a valid auditor. If there are migrations, imports, schedulers, or system operations without an attached user, AuditorAware may return Optional.empty(). In that case, a NOT NULL column can cause INSERTs to fail.

There are three common design approaches:

- Allow null when the actor is genuinely unknown.
- Supply a clear system actor for background tasks.
- Require every create/update use case to have an actor and reject the operation if none is present.

Do not automatically assign system for every Optional.empty() case if doing so masks a bug where SecurityContext was lost. Distinguish genuine system actors from requests that ought to have an authenticated user.

## 9. What Does Optional.empty() Mean?

AuditorAware returns Optional<T> instead of T to represent the case where no actor is found.

Example:

~~~java
@Override
public Optional<String> getCurrentAuditor() {
    return Optional.empty();
}
~~~

When the auditor has no value, the auditing infrastructure has no actor to assign to @CreatedBy or @LastModifiedBy properties. It does not invent a username, does not query a users table, and does not guess an actor from the thread.

Data behavior also depends on the current entity and schema:

- On initial insert, the auditor property may remain null if no other value is set.
- If the database column is NOT NULL, the INSERT may fail.
- On update, if there is no new auditor, the existing value may be retained depending on the auditing/property-access mechanism.
- Date/time fields can still be updated independently of the auditor if date auditing is enabled.

If business rules require a mandatory actor, validate this explicitly in the application service or configure the actor source so operations without an actor are rejected with an appropriate message.

## 10. Background Tasks and Service Accounts

Not every save originates from an HTTP request. Common cases include:

- Scheduled tasks running via @Scheduled.
- Data batch imports.
- Message listeners processing messages from a broker.
- Jobs syncing data from external systems.
- Migrations or administrative tasks.
- Service-to-service requests.

These flows may not have a SecurityContext. Resolve the actor based on the triggering source:

| Operation Type | Suggested Auditor |
|---|---|
| Logged-in user acting via web/API | User ID or principal ID |
| Scheduler | Service account with a stable name such as service:daily-reconciliation |
| Batch import | Job/import batch ID or service account |
| Message consumer | Service identity or authenticated actor from message metadata |
| Migration | Dedicated migration actor, or leave unassigned if schema allows |
| Administrative task | Authenticated administrator's ID |

Do not use a single generic value for all background jobs if you need to know exactly which job modified the data.

### Do Not Rely on the Request's SecurityContext for Async Tasks

SecurityContextHolder typically stores context per thread. When offloading work to an executor, scheduler, or message listener, the original request's context may not propagate automatically.

If you need to preserve the request's actor during asynchronous execution, propagate the identity intentionally using an appropriate security context propagation mechanism or include the authenticated actor ID in the command/message. Do not assume a new thread will see the HTTP thread's Authentication.

## 11. Providing an Auditor for System Tasks Explicitly

A system principal can be used for categorized jobs. For example, the bean below is an option if the application truly runs a dedicated background task without users:

~~~java
@Bean
AuditorAware<String> batchAuditorProvider() {
    return () -> Optional.of("service:customer-import");
}
~~~

If the same application both serves user requests and runs background jobs, do not replace the global AuditorAware with a fixed value. Instead, use an actor source scoped to the application context or separate jobs into services/configurations with clear conventions.

One option is to place the system actor into a managed context scoped to the job:

~~~java
public final class AuditActorContext {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    private AuditActorContext() {}

    public static void set(String actor) {
        ACTOR.set(actor);
    }

    public static Optional<String> currentActor() {
        return Optional.ofNullable(ACTOR.get());
    }

    public static void clear() {
        ACTOR.remove();
    }
}
~~~

AuditorAware can check the explicitly set actor first before falling back to SecurityContext:

~~~java
@Bean
AuditorAware<String> auditorProvider() {
    return () -> AuditActorContext.currentActor()
            .or(() -> currentAuthenticatedUsername());
}
~~~

When running a job:

~~~java
try {
    AuditActorContext.set("service:nightly-import");
    importService.run();
} finally {
    AuditActorContext.clear();
}
~~~

This pattern illustrates a thread-bound synchronous context. ThreadLocal must always be cleared in a finally block because thread pools reuse threads. If a task runs asynchronously, the context must be propagated explicitly across the executor/message; ThreadLocal does not automatically cross thread boundaries.

In simple applications, a better approach may be passing the actor ID into the command or service method. There is no need to build a ThreadLocal if an explicit parameter already satisfies the requirement.

## 12. Combining @CreatedBy and @LastModifiedBy

An entity can declare both properties:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @CreatedBy String createdBy,
        @LastModifiedBy String lastModifiedBy
) {}
~~~

Meaning:

- createdBy records the actor at creation time.
- lastModifiedBy records the actor of the most recent change.
- On creation, default auditing configuration typically updates modified fields right at creation time; the modifyOnCreate attribute can adjust this behavior.
- When updating an existing aggregate, createdBy retains its initial value while lastModifiedBy is updated to the current auditor.

Do not reassign createdBy on every update. That is record-creation history and must be preserved.

If the application needs to know both the creator and prior editors, these two current fields only retain the creator and last modifier. To keep a full history, a separate audit table or event log is needed; full history cannot be inferred from @CreatedBy and @LastModifiedBy.

## 13. AuditorAware and DateTimeProvider

AuditorAware provides the actor; DateTimeProvider provides the current time. The two abstractions are independent but are commonly configured together with the auditing infrastructure.

Example custom DateTimeProvider using Clock:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.context.annotation.Bean;

@Bean
Clock auditClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditClock) {
    return () -> Optional.<TemporalAccessor>of(auditClock.instant());
}
~~~

This bean can be referenced in the auditing configuration:

~~~java
@EnableJdbcAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

Configuring Clock makes time-based testing deterministic and avoids scattering direct system clock calls across the codebase. If no customization is needed, auditing can use the default time provider.

AuditorAware should not return timestamps and DateTimeProvider should not return usernames. Keeping these two responsibilities separate makes entity metadata easier to understand and test independently.

## 14. AuditorAware Does Not Run Automatically for Direct SQL

Spring Data JDBC auditing is integrated into the aggregate persistence lifecycle. When repository.save(...) or JdbcAggregateTemplate saves an aggregate, auditing callbacks can populate @CreatedBy, @LastModifiedBy, and date/time fields.

A direct SQL statement:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET name = :name
    WHERE id = :id
    """)
int updateName(Long id, String name);
~~~

does not automatically execute aggregate auditing callbacks for each updated row. AuditorAware is not invoked merely because that UPDATE statement runs.

If using @Query DML or JdbcTemplate to update a table with audit columns, the SQL must update those columns explicitly or the use case must coordinate auditing separately:

~~~sql
UPDATE customers
SET name = :name,
    last_modified_by = :actor,
    last_modified_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

The actor value must be obtained from an appropriate authenticated source and bound as a parameter. Do not concatenate the actor string into SQL.

If uniform auditing across multiple write paths is needed, choose a clear strategy: prefer repository/template for normal aggregates; for direct SQL, use a shared helper to obtain the actor/timestamp and update audit columns, or route the operation through a service responsible for auditing.

## 15. AuditorAware and the Aggregate Root

Spring Data JDBC organizes persistence around the aggregate root. Auditing metadata is processed on the aggregate root during Spring Data JDBC's save path.

If the root contains a collection of children via @MappedCollection, do not assume a separate AuditorAware invocation occurs for each child entity as if it were an independent save. Child audit fields must be designed around the actual mapping and lifecycle the application uses.

If children need to record their own creator/modifier, verify the mapping/lifecycle support of the Spring Data Relational version in use and consider modeling a child with an independent lifecycle as a separate aggregate when appropriate for the domain. Do not split an aggregate solely to work around an annotation.

## 16. Testing AuditorAware

At least three cases should be tested:

1. Valid actor present: the auditor returns the correct ID/username.
2. No Authentication or anonymous: the auditor returns Optional.empty() or the chosen fallback actor by convention.
3. Background job: the auditor returns the right service identity if the job must record a system actor.

Unit tests for an implementation reading SecurityContext can set up a mock Authentication:

~~~java
@Test
void returnsAuthenticatedUsername() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    "lan",
                    "n/a",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

    SecurityContextHolder.getContext().setAuthentication(authentication);

    try {
        assertEquals(
                Optional.of("lan"),
                auditorAware.getCurrentAuditor()
        );
    } finally {
        SecurityContextHolder.clearContext();
    }
}
~~~

Actual tests need the corresponding JUnit, assertion, and Spring Security imports. Always clear SecurityContext after the test to prevent state from leaking into other tests.

### Integration Test with Repository

To verify that auditing is actually enabled, save an aggregate via a repository in a Spring context:

~~~java
@Test
void recordsCreatedAndModifiedAuditors() {
    setAuthenticatedUser("lan");

    Customer saved = customerRepository.save(
            new Customer(null, "Lan", null, null)
    );

    assertEquals("lan", saved.createdBy());
    assertEquals("lan", saved.lastModifiedBy());

    setAuthenticatedUser("minh");

    Customer changed = new Customer(
            saved.id(),
            "Lan Nguyen",
            saved.createdBy(),
            saved.lastModifiedBy()
    );

    Customer updated = customerRepository.save(changed);

    assertEquals("lan", updated.createdBy());
    assertEquals("minh", updated.lastModifiedBy());
}
~~~

This illustrates the testing idea; the constructor and properties of Customer must match the actual entity. When using an immutable record, use the instance returned from save to obtain the populated audit values.

Integration tests should also inspect data read back from the database if the goal is to verify mapping and persistence, not just the returned object.

## 17. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| createdBy is always null | @EnableJdbcAuditing not enabled or no AuditorAware bean | Check auditing configuration and bean reference |
| lastModifiedBy does not change | Update bypasses aggregate save lifecycle or auditor is empty | Check write path and SecurityContext |
| Save fails with NOT NULL on auditor column | AuditorAware returns Optional.empty() while schema requires a value | Choose an intentional fallback or allow null |
| Audit records anonymousUser | AnonymousAuthenticationToken not excluded | Filter out anonymous authentication |
| Username stored when user ID is needed | AuditorAware returns the wrong identifier | Use a custom principal and AuditorAware<UUID/Long> |
| Cannot map auditor type | Generic type mismatches property or converter | Align Java type, SQL type, and converters |
| Background job records null actor | Job has no SecurityContext | Use a service identity or pass actor explicitly |
| Async task loses actor | SecurityContext/ThreadLocal not propagated to new thread | Use context propagation or pass actor in message/command |
| Direct UPDATE does not change lastModifiedBy | @Query DML does not invoke auditing callbacks | Update audit columns in SQL or coordinate separately |
| createdBy changed unintentionally | Update logic reassigns created field | Preserve original value |
| Tests affect each other | SecurityContext not cleared | Clear context in finally/tearDown |
| Audit stores personal email unintentionally | Email chosen as long-term identifier | Consider stable IDs and data-retention policies |

## 18. Process for Setting Up AuditorAware

When adding auditing to a Spring Data JDBC application:

1. Determine the actor type to store: username, UUID, Long, or service identity.
2. Declare audit properties with @CreatedBy and @LastModifiedBy.
3. Create database columns with compatible names, types, and nullability.
4. Enable @EnableJdbcAuditing and reference the proper AuditorAware bean.
5. Read the actor from the authenticated source at the moment the callback is invoked.
6. Exclude anonymous or invalid principals.
7. Clearly define whether Optional.empty() is accepted or must be replaced by a system actor.
8. Handle schedulers, batches, message consumers, and async tasks.
9. Ensure direct SQL has its own rules for updating audit columns.
10. Write unit tests for AuditorAware and integration tests via the repository.

~~~mermaid
flowchart TD
    A["Aggregate is saved"] --> B["Spring Data JDBC auditing"]
    B --> C["AuditorAware.getCurrentAuditor"]
    C --> D{"Valid actor?"}
    D -->|Yes| E["Return Optional.of(actor)"]
    D -->|No| F["Return Optional.empty or defined fallback"]
    E --> G["Assign CreatedBy / LastModifiedBy"]
    F --> G
    G --> H["Mapping and SQL persistence"]
    H --> I["Database"]
~~~

## 19. Key Principles to Remember

- AuditorAware<T> returns Optional<T> representing the current actor.
- @CreatedBy and @LastModifiedBy use the auditor provider; @CreatedDate and @LastModifiedDate use the date/time provider.
- Enable auditing for Spring Data JDBC with @EnableJdbcAuditing.
- The generic type of AuditorAware must be compatible with the audit property types.
- SecurityContextHolder may lack an Authentication; handle null, unauthenticated, and anonymous cases.
- Prefer a stable identifier such as a user ID if auditing serves long-term traceability.
- Optional.empty() does not invent an actor; explicitly specify whether the schema allows null.
- Background jobs and async tasks need a service identity or explicit actor propagation.
- AuditorAware and auditing callbacks do not run automatically for direct SQL or @Query DML.
- @CreatedBy retains the creator; @LastModifiedBy changes with the most recent modification.
- After-save or auditing callbacks are not a mechanism for publishing post-commit side effects.
- Test both the AuditorAware implementation and actual persistence through a repository.

AuditorAware is the bridge between the identity authenticated by the application and Spring Data JDBC's auditing metadata. Choose a stable identifier, handle missing users explicitly, distinguish requests from system tasks, and enforce the same rules across every data write path. When properly configured, @CreatedBy and @LastModifiedBy record actors consistently without application services having to assign these fields in every use case.

## References

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [AuditorAware API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [EnableJdbcAuditing API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html)
