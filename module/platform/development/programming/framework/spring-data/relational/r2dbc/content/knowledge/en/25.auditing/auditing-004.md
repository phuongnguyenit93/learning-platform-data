# Providing the Current User with ReactiveAuditorAware

Spring Data Relational R2DBC can automatically record who created or updated an entity through auditing. Annotations such as **@CreatedBy** and **@LastModifiedBy** mark properties that store who performed the operation. To let Spring know who the current user is in a reactive application, provide a bean implementing **ReactiveAuditorAware<T>**.

In a Spring WebFlux application combined with Spring Security, the authenticated identity is propagated through the **Reactor Context**. Therefore, ReactiveAuditorAware must read the security context reactively and return a **Mono<T>**. You should not retrieve the user with the imperative **SecurityContextHolder** or block the thread with **block()**, because those approaches are incompatible with the reactive lifecycle.

This lesson explains how to connect ReactiveAuditorAware with Spring Security, choose an identifier type, configure auditing for R2DBC, handle unauthenticated requests and background tasks, write tests, and recognize cases where automatic auditing is not applied.

## 1. Auditing needs to know who is performing the operation

Auditing stores information about when and by whom data was created or modified. An entity can have the following fields:

- Creator: **createdBy**.
- Creation time: **createdDate**.
- Most recent modifier: **lastModifiedBy**.
- Most recent modification time: **lastModifiedDate**.

Example order table:

~~~text
purchase_order
+----+-------------+---------------------+-----------------+---------------------+
| id | order_no    | created_at          | created_by      | last_modified_by   |
+----+-------------+---------------------+-----------------+---------------------+
| 10 | ORD-001     | 2026-10-01 09:00:00 | 42              | 42                  |
| 11 | ORD-002     | 2026-10-02 10:30:00 | 57              | 81                  |
+----+-------------+---------------------+-----------------+---------------------+
~~~

Time fields show when an operation happened. Auditor fields show which account performed the operation.

Spring Data provides annotations to mark auditing properties:

| Annotation | Meaning |
|---|---|
| **@CreatedBy** | Auditor of entity creation |
| **@CreatedDate** | Timestamp of entity creation |
| **@LastModifiedBy** | Auditor of the most recent modification |
| **@LastModifiedDate** | Timestamp of the most recent modification |

These annotations only describe metadata. For them to be processed, the application must enable auditing and provide appropriate time/user sources. With R2DBC, the reactive user source is declared via **ReactiveAuditorAware<T>**.

## 2. What is ReactiveAuditorAware?

**ReactiveAuditorAware<T>** is a Spring Data interface in the **org.springframework.data.domain** package. It provides the current auditor reactively:

~~~java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

The generic type **T** is the auditor's identifier type. For example:

- **Long** if the system stores numeric user IDs.
- **UUID** if user IDs are UUIDs.
- **String** if the system uses usernames or account codes.

The **getCurrentAuditor()** method returns **Mono<T>** because the current user is resolved within the reactive execution context. The publisher can emit an auditor or complete empty if no auditor exists.

ReactiveAuditorAware does not authenticate users itself, does not create a security context, and does not query a user database by default. It simply reads an identity already present in the context or from a reactive source explicitly configured by the application.

Overall flow:

~~~text
HTTP request
    |
    v
Spring Security WebFlux authentication
    |
    v
Authentication in Reactor Context
    |
    v
ReactiveAuditorAware.getCurrentAuditor()
    |
    v
Mono<AuditorId>
    |
    v
Spring Data auditing callback
    |
    +---- @CreatedBy
    |
    +---- @LastModifiedBy
    |
    v
R2DBC INSERT / UPDATE
~~~

## 3. Enabling auditing for Spring Data R2DBC

Declare **@EnableR2dbcAuditing** in configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
~~~

The **auditorAwareRef** attribute points to the bean name providing the auditor. That bean must implement **ReactiveAuditorAware<T>**.

If auditorAwareRef is omitted, Spring may locate an appropriate ReactiveAuditorAware bean according to the configuration mechanism of the version in use. Naming it explicitly avoids ambiguity when the application has multiple auditor sources or multiple persistence configurations.

The configuration example above only enables auditing. You still need to declare the **auditorProvider** bean so Spring knows the current user's ID.

## 4. Retrieving the current user from Spring Security WebFlux

In reactive Spring Security, **ReactiveSecurityContextHolder** reads the **SecurityContext** from the Reactor Context. We can obtain the Authentication, then extract the principal and convert it into the auditor ID.

Suppose the application has a custom principal:

~~~java
public record AppUserPrincipal(
        Long id,
        String username) {
}
~~~

ReactiveAuditorAware bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration
public class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                        instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .ofType(AppUserPrincipal.class)
                .map(AppUserPrincipal::id);
    }
}
~~~

Processing steps:

1. **ReactiveSecurityContextHolder.getContext()** obtains the SecurityContext from the current reactive context.
2. **map(SecurityContext::getAuthentication)** extracts the Authentication object.
3. **filter(...)** keeps only authenticated tokens and excludes anonymous tokens.
4. **map(Authentication::getPrincipal)** extracts the principal.
5. **ofType(AppUserPrincipal.class)** accepts only principals of the type expected by the application.
6. **map(AppUserPrincipal::id)** transforms the principal into the auditor ID.

The result is a **Mono<Long>**. If there is no SecurityContext, authentication is unauthenticated, the principal is anonymous, or the principal is not AppUserPrincipal, the publisher completes empty.

### 4.1. Why exclude AnonymousAuthenticationToken?

In Spring Security, an anonymous authentication can have **isAuthenticated() == true**. Therefore, checking only:

~~~java
.filter(Authentication::isAuthenticated)
~~~

is not enough to confirm this is a logged-in user. An anonymous token can pass this condition.

You can explicitly exclude **AnonymousAuthenticationToken**, as in the example above. Another option is accepting only principals of an application-defined type via **ofType(AppUserPrincipal.class)**. Using both conditions makes the contract clearer.

Do not cast the principal to a specific type without checking. The principal could be the string **anonymousUser**, a **UserDetails**, a **Jwt**, or a custom class provided by the application.

## 5. Auditor type must match the entity field type

If the bean returns **Mono<Long>**, the **@CreatedBy** and **@LastModifiedBy** fields should accept Long or a type with explicitly configured conversion.

Example entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @CreatedBy
    @Column("created_by")
    private Long createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private Long lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;
}
~~~

With this entity, the auditor ID is **Long**. If the principal provides a UUID, you can change the bean to **ReactiveAuditorAware<UUID>** and the auditor fields to UUID, while ensuring the database schema uses a matching type.

Do not store a username in a field designed for a numeric user ID. Likewise, do not rely on implicit conversion between incompatible types.

### 5.1. Store a stable ID rather than a display name

Usernames, emails, or display names can change. A stable internal ID is usually better suited for createdBy/lastModifiedBy fields.

If you need to display the creator's name in a UI, you can join or query the user table by ID. Auditing history will retain the exact identity even if the user changes their username.

For systems required to preserve history after an account is deleted, decide how to retain the auditor ID: soft delete, storing a display-name snapshot, or using a historical identity table. A direct foreign key to the user table may block user deletion or prevent retaining history as designed.

## 6. Complete configuration for date/time auditing

Auditing can automatically populate both user and timestamp. A complete configuration:

~~~java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorProvider",
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                        instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .ofType(AppUserPrincipal.class)
                .map(AppUserPrincipal::id);
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }
}
~~~

This configuration uses **Clock** to generate the current instant and provides it via **DateTimeProvider**. In tests, Clock can be replaced with a fixed clock to verify timestamps deterministically.

**modifyOnCreate = true** requests that modified fields be populated when an entity is first created. Both created and last modified time/auditor can then be set on the initial insert. If business logic only wants modified fields populated after the first update, consider configuring false and verifying behavior with the Spring Data version in use.

If you do not need to customize the time source, you can omit **dateTimeProviderRef** and let auditing use the default provider.

Imports for the example:

~~~java
import java.time.Clock;
import java.util.Optional;

import org.springframework.data.auditing.DateTimeProvider;
~~~

## 7. Where does auditing happen in the entity save lifecycle?

Spring Data Relational uses entity callbacks to apply auditing while preparing an entity for persistence. When an entity is saved through a repository or Spring Data APIs that support callbacks, the auditing infrastructure can update fields before data is written.

Illustrative flow:

~~~text
repository.save(entity)
       |
       v
Determine whether entity is new or existing
       |
       v
Auditing entity callback
       |
       +---- get current auditor
       |
       +---- get current time
       |
       +---- assign Created/LastModified fields
       |
       v
Map entity to SQL parameters
       |
       v
R2DBC driver executes INSERT / UPDATE
~~~

In principle:

- When creating an entity, Spring populates **@CreatedBy** and **@CreatedDate**.
- When updating an entity, Spring preserves creation info and updates **@LastModifiedBy** and **@LastModifiedDate**.
- With **modifyOnCreate = true**, modified fields are also populated on creation.

Auditing is not a database trigger mechanism. It is Spring Data logic running inside Spring's persistence workflow.

### 7.1. Entities must be accurately detected as new or existing

Spring Data needs to determine whether an operation is an insert or an update. Detecting whether an entity is new typically relies on the ID and/or version field, or the **Persistable.isNew()** mechanism if the entity implements that interface.

If an entity's state is misidentified, Created fields may not be applied as intended. Verify the ID strategy, version, and entity lifecycle.

Do not pre-assign an ID before insert if your application's new/existing strategy relies on a null ID without configuring an appropriate detection mechanism.

## 8. No current user: what does Mono.empty() mean?

ReactiveAuditorAware can return **Mono.empty()**. This means that at the time of saving the entity, no auditor is provided.

The **@CreatedBy** or **@LastModifiedBy** fields then receive no new auditor value. Date fields can still be populated if date auditing is enabled.

Situations without an auditor can occur when:

- A request is unauthenticated or allowed anonymous access.
- A task runs on a schedule.
- A background message consumer lacks a security context.
- A migration or batch job runs outside a request.
- A test does not set up a SecurityContext.
- A publisher becomes detached from the reactive context containing Authentication.

This behavior must match the schema and auditing policy. If the created_by column is NOT NULL while the auditor can be empty, inserts will fail due to a constraint violation.

There are three common design approaches:

1. Allow null auditors if business logic accepts records without an associated user.
2. Provide an explicit system actor for background tasks permitted to use a system identity.
3. Reject the operation if business rules require a user and no valid auditor exists.

Do not automatically assign a default user whenever SecurityContext is missing. That can cause unauthenticated requests to be falsely attributed to a system account.

## 9. Providing a system auditor for background tasks

Scheduled tasks or message consumers usually lack a user Authentication. If records created by a job must have createdBy, explicitly define the system actor identity.

For example, reserve an ID for the system account:

~~~java
private static final Long SYSTEM_AUDITOR_ID = 1L;
~~~

A fallback can be used, but only once the application has established this is a system task's execution context. Do not use a global fallback for all requests missing authentication.

A cleaner approach is passing the auditor via Reactor Context for jobs:

~~~java
private static final String AUDITOR_ID_CONTEXT_KEY = "auditorId";

@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> Mono.deferContextual(context ->
            Mono.justOrEmpty(
                    context.<Long>getOrEmpty(AUDITOR_ID_CONTEXT_KEY)));
}
~~~

When running the job:

~~~java
Mono<Void> runImport(Long systemActorId) {
    return importService.importData()
            .then()
            .contextWrite(context ->
                    context.put(AUDITOR_ID_CONTEXT_KEY, systemActorId));
}
~~~

In this example, the auditor is placed into the context explicitly. The key and data type must be standardized across the application. Only authorized jobs should add the system actor to the context.

If using both Spring Security and a custom context, define precedence clearly. For example: prefer the authenticated user; if absent, only use the system actor when a flag or context marker confirms it is a background task. Do not use an arbitrary client-submitted context value as an auditor ID without permission checks.

## 10. Reactive Context and why not to use SecurityContextHolder

In imperative applications, Spring Security typically provides SecurityContext via ThreadLocal, readable via **SecurityContextHolder.getContext()**.

In WebFlux, a single request may switch across multiple threads. ThreadLocal is not a reliable mechanism for carrying request state throughout an entire reactive pipeline. Reactive Spring Security stores the context in the Reactor Context and provides **ReactiveSecurityContextHolder** to read it.

Do not write:

~~~java
@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return Mono.just(((AppUserPrincipal)
                authentication.getPrincipal()).id());
    };
}
~~~

Problems with this approach:

- Reading ThreadLocal may fail to find a context on the current thread.
- An anonymous or empty context can cause ClassCastException or NullPointerException.
- Reading the principal happens synchronously and ignores the reactive context.
- It can easily attribute the wrong identity when requests switch threads or run on schedulers.

Use:

~~~java
ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
~~~

Reactor Context propagates with the subscription. Operators like **publishOn** or **subscribeOn** change the execution thread, which does not lose context the way ThreadLocal typically does. However, creating independent subscriptions or using libraries that do not preserve reactive context can cause the auditor to lose sight of the original security context.

## 11. Principals can be UserDetails, JWT, or custom types

Not every application uses **AppUserPrincipal**. Map the principal according to the actual authentication mechanism.

### 11.1. Principal implementing UserDetails

If a custom principal implements **UserDetails**, you can extract the specific type:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getPrincipal)
        .ofType(AppUserDetails.class)
        .map(AppUserDetails::getUserId);
~~~

Still exclude anonymous authentication if Security configuration permits anonymous access.

### 11.2. JWT resource server

With JWT, the principal is often a **Jwt** object. You can extract the subject or a claim containing the user ID:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication ->
                authentication.isAuthenticated()
                        && !(authentication
                                instanceof AnonymousAuthenticationToken))
        .map(Authentication::getPrincipal)
        .ofType(Jwt.class)
        .map(jwt -> jwt.getClaimAsString("user_id"))
        .filter(Objects::nonNull)
        .map(Long::valueOf);
~~~

This example assumes the **user_id** claim is always a numeric string. If the claim can hold a UUID or another type, convert accordingly and handle invalid values.

Do not assume **Authentication.getName()** is always a database ID. With JWT, getName may return the subject; with UserDetails, it usually returns the username. Define the principal contract and auditor data type clearly.

## 12. Distinguishing auditor from tenant and data owner

Auditor answers the question: **who performed the operation?**

Tenant answers the question: **which workspace/customer organization does the data belong to?**

Owner answers the question: **who owns the record in business terms?**

These three concepts may coincide in one use case, but they should not be merged into one.

For example:

- A support agent updates a customer's order.
- The auditor is the support agent's ID.
- The owner/customer is the customer's ID.
- The tenant is the organization the order belongs to.

If customer ID were used as the auditor in the case above, history would not reveal which staff member actually modified the data.

All three fields can be stored separately:

~~~java
@CreatedBy
@Column("created_by")
private Long createdBy;

@Column("customer_id")
private Long customerId;

@Column("tenant_id")
private Long tenantId;
~~~

Tenant and owner usually need to be obtained from separate context/authorization and must have access permissions verified. Do not trust a tenant ID or auditor ID merely because the client sent it in the request body.

## 13. Operations that do not automatically run auditing callbacks

Auditing annotations do not mean every data-modifying SQL statement automatically updates audit fields.

Persistence paths like **repository.save(...)** or Spring Data entity/template APIs can run entity callbacks as configured. However, direct SQL updates via **DatabaseClient**, R2DBC SPI, stored procedures, or bulk modifying queries do not necessarily create and save an entity through auditing callbacks.

Direct update example:

~~~java
databaseClient.sql("""
        UPDATE purchase_order
        SET status = :status
        WHERE id = :id
        """)
        .bind("status", status.name())
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
~~~

This statement does not automatically know the current auditor to set **last_modified_by**. If using direct queries, update audit fields in SQL:

~~~java
databaseClient.sql("""
        UPDATE purchase_order
        SET status = :status,
            last_modified_by = :auditorId,
            last_modified_at = :modifiedAt
        WHERE id = :id
        """)
        .bind("status", status.name())
        .bind("auditorId", auditorId)
        .bind("modifiedAt", modifiedAt)
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
~~~

Or use database triggers if the auditing policy must apply across all write paths, including other applications. When combining triggers and Spring auditing, avoid having two places write inconsistent values.

For bulk update/delete, do not assume entity callbacks are invoked per row. Check the API contract and update audit metadata explicitly if needed.

## 14. Time types and time sources

Date/time auditing fields can use Java types supported by Spring Data, such as **Instant**, **LocalDateTime**, or **OffsetDateTime**, depending on converters and the database.

Choose the type by semantics:

| Type | Meaning |
|---|---|
| **Instant** | An absolute point on the timeline |
| **OffsetDateTime** | Point in time with a UTC offset |
| **LocalDateTime** | Local date and time without timezone/offset |

For distributed systems, **Instant** is usually the clearest choice for created/modified timestamps. Database columns should be chosen with appropriate precision and timezone semantics.

Using UTC for timestamps reduces confusion when services run across multiple timezones. Do not use the client machine's clock as the auditing time; the server or database should be the controlled time source.

Custom **DateTimeProvider** and **Clock** help:

- Synchronize time sources across services.
- Test timestamps deterministically.
- Simulate past/future timestamps in tests.
- Avoid direct dependency on the system clock in entities/services.

## 15. Testing ReactiveAuditorAware independently

You can test the auditor bean using **StepVerifier** and placing Authentication into the Reactor Context.

Example:

~~~java
@Test
void returnsAuthenticatedUserId() {
    AppUserPrincipal principal =
            new AppUserPrincipal(42L, "an");

    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    principal,
                    "n/a",
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));

    StepVerifier.create(
            auditorProvider.getCurrentAuditor()
                    .contextWrite(
                            ReactiveSecurityContextHolder
                                    .withAuthentication(authentication)))
            .expectNext(42L)
            .verifyComplete();
}
~~~

This test verifies that the auditor reads the ID from the reactive security context.

### 15.1. Testing when no context exists

~~~java
@Test
void returnsEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(auditorProvider.getCurrentAuditor())
            .verifyComplete();
}
~~~

This is valid behavior if the application permits operations without a user or has a separate handling policy for that case.

### 15.2. Testing anonymous authentication

~~~java
@Test
void doesNotUseAnonymousUserAsAuditor() {
    Authentication anonymous =
            new AnonymousAuthenticationToken(
                    "key",
                    "anonymousUser",
                    List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

    StepVerifier.create(
            auditorProvider.getCurrentAuditor()
                    .contextWrite(
                            ReactiveSecurityContextHolder
                                    .withAuthentication(anonymous)))
            .verifyComplete();
}
~~~

This test ensures the auditor does not accept the string **anonymousUser** or a principal that does not represent an authenticated user.

## 16. Testing auditing when saving an entity

Testing the bean in isolation does not prove that entity callbacks and database mapping work together. You should write integration tests using a real repository and the target database/driver.

A scenario:

1. Create an Authentication for user ID 42.
2. Put the Authentication into the Reactor Context.
3. Call repository.save(new entity).
4. Read the saved entity.
5. Verify createdBy is 42.
6. Verify createdDate is populated.
7. Update the entity under user ID 57's context.
8. Verify createdBy remains 42 and lastModifiedBy is 57.
9. Verify lastModifiedDate is updated.

Publisher verification example:

~~~java
StepVerifier.create(
        orderRepository.save(newOrder)
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authenticationForUser42)))
        .assertNext(saved -> {
            assertThat(saved.getCreatedBy()).isEqualTo(42L);
            assertThat(saved.getCreatedDate()).isNotNull();
            assertThat(saved.getLastModifiedBy()).isEqualTo(42L);
        })
        .verifyComplete();
~~~

If using **modifyOnCreate = false**, adjust expectations for modified fields on insert. If auditor columns are nullable and the context has no Authentication, tests should verify that behavior matches the schema and policy.

With a fixed Clock, you can assert exact timestamps instead of only checking not null.

## 17. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Not enabling **@EnableR2dbcAuditing** | Auditing annotations are not applied | Enable auditing in configuration |
| Not registering ReactiveAuditorAware bean or wrong bean ref | Spring cannot retrieve the auditor | Declare bean and check auditorAwareRef |
| Using **SecurityContextHolder** in WebFlux | Cannot reliably read context across threads | Use ReactiveSecurityContextHolder |
| Checking only **isAuthenticated()** | Anonymous tokens may be treated as authenticated | Exclude AnonymousAuthenticationToken and inspect principal |
| Casting principal to an unverified type | ClassCastException or errors with JWT/anonymous | Use ofType and map according to actual principal |
| Bean returns **Mono<UUID>** while field is Long | Incompatible auditor mapping | Align generic type and column type |
| No context while created_by column is NOT NULL | Insert fails due to constraint violation | Provide valid actor or design null/system actor policy |
| Assigning system user to every unauthenticated request | Audit records wrong actor | Only use system auditor in clearly defined execution contexts |
| Calling standalone subscribe() in a service | Reactive security context may be lost | Chain publishers within the same pipeline |
| Using auditor as tenant or owner | History and ownership are conflated | Store actor, tenant, and owner separately |
| Using DatabaseClient raw SQL expecting callbacks to run | lastModified fields are not updated | Set audit fields in SQL or use appropriate callbacks |
| Not checking entity new/existing detection | Created/modified fields applied incorrectly | Verify ID, version, and isNew strategy |
| Storing username instead of a stable ID | History affected when username changes | Prefer immutable user ID |
| Not testing anonymous/job contexts | Background tasks write null or wrong auditors | Test each execution context |

## 18. Workflow for implementing ReactiveAuditorAware

When integrating auditing with the current user, follow this sequence:

1. Identify the stable user identifier type the database will store.
2. Annotate entity fields with **@CreatedBy**, **@LastModifiedBy**, and needed time annotations.
3. Enable **@EnableR2dbcAuditing** and point to the auditor bean.
4. Implement **ReactiveAuditorAware<T>** with a generic type matching entity fields.
5. If using WebFlux/Spring Security, read Authentication with **ReactiveSecurityContextHolder**.
6. Exclude anonymous authentication and check principal type before extracting the ID.
7. Decide behavior when no auditor exists: allow null, conditional system actor, or reject operation.
8. Configure **DateTimeProvider** if time source control is needed.
9. Verify repository/entity callbacks actually run on the persistence path in use.
10. For raw SQL or bulk updates, update audit fields explicitly or use database triggers.
11. Test authenticated user, anonymous, no-context, system job, insert, and update.
12. Test on the actual R2DBC driver/database to verify schema and data types.

## 19. Key takeaways

- **ReactiveAuditorAware<T>** provides the current auditor via **Mono<T>**.
- **@EnableR2dbcAuditing** enables auditing and **auditorAwareRef** points to the user-provider bean.
- In WebFlux, read the user via **ReactiveSecurityContextHolder**, because SecurityContext is propagated through the Reactor Context.
- Do not use imperative **SecurityContextHolder** or **block()** in a reactive pipeline.
- Checking **isAuthenticated()** alone is insufficient because anonymous tokens can be marked authenticated.
- Verify the principal type before extracting a user ID; do not assume every Authentication has the same principal.
- ReactiveAuditorAware's generic type must match the type of **@CreatedBy** and **@LastModifiedBy**.
- **Mono.empty()** means no auditor exists; auditor fields may remain unassigned and the schema must allow it or the application must have another policy.
- Background tasks may need a system actor, but assign it only when the execution context is explicitly established.
- Auditor, tenant, and owner are three distinct concepts.
- Auditing callbacks operate on Spring Data-supported persistence paths; raw SQL, bulk queries, and direct SPI require separate audit metadata updates.
- Test both the auditor bean and repository integration, including creation, updates, anonymous requests, and jobs without a security context.
