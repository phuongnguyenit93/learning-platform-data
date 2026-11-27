# Retrieving Identity from the Reactive Security Context

In Spring Data Relational R2DBC, auditing can automatically record the creator and modifier of an entity through `@CreatedBy` and `@LastModifiedBy`. For Spring WebFlux and reactive Spring Security applications, the current identity must be retrieved from `ReactiveSecurityContextHolder`, because the security context is propagated via the subscription's Reactor Context rather than relying on `ThreadLocal` as in the traditional imperative model.

Spring Data provides `ReactiveAuditorAware<T>` to return the current auditor as a `Mono<T>`. When auditing processes an entity, this implementation reads `Authentication` from the reactive security context, identifies the appropriate principal, and emits the identifier to store. If there is no security context or the request is unauthenticated, the publisher can complete empty; the application must clearly decide whether audit fields may remain empty or whether a system identity must be used in background workflows.

## 1. Auditing and actor identity

Auditing records metadata about an entity's lifecycle. Commonly used annotations include:

| Annotation | Meaning |
|---|---|
| `@CreatedBy` | Person or actor that created the entity |
| `@LastModifiedBy` | Person or actor that most recently modified the entity |
| `@CreatedDate` | Timestamp when the entity was created |
| `@LastModifiedDate` | Timestamp when the entity was most recently modified |

Example of a customer record with audit fields:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

When an entity is created or updated via Spring Data auditing, the framework obtains the auditor from `ReactiveAuditorAware` and assigns it to the corresponding fields. Timestamps are provided through auditing's date-time provider.

Entity auditing does not automatically create an immutable history of every change. `@CreatedBy` and `@LastModifiedBy` only store the creator and most recent modifier on the current record. If you need to store every single change, old/new values, reasons, and actors for each event, design a separate audit log or event history.

## 2. Why must ReactiveSecurityContextHolder be used?

In reactive Spring Security, the `SecurityContext` is stored in the Reactor Context attached to the subscription. A single request may execute across multiple threads when the pipeline switches schedulers; therefore you cannot rely on a `ThreadLocal` always holding the right user.

The appropriate API to retrieve the security context in a reactive pipeline is:

```java
ReactiveSecurityContextHolder.getContext()
```

This API returns `Mono<SecurityContext>`. When a subscription is executing in a context populated by Spring Security, the publisher can emit the corresponding `SecurityContext`. If no context is present, the publisher normally completes empty.

Do not use this imperative approach in reactive code:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
```

Standard `SecurityContextHolder` relies on an imperative/ThreadLocal storage strategy. In WebFlux, code can run on different threads and reading the correct context is not guaranteed. `ReactiveSecurityContextHolder` is designed to read the context per subscription.

### 2.1. Reactor Context is not ThreadLocal

Reactor Context is attached to the subscriber and propagated across reactive operators. For example:

```text
WebFlux Security WebFilter
          |
          v
Creates SecurityContext in Reactor Context
          |
          v
Controller returns Mono / Flux
          |
          v
Service and Repository compose publishers
          |
          v
ReactiveAuditorAware reads context
          |
          v
Auditing assigns createdBy / lastModifiedBy
```

Switching threads with `publishOn` or `subscribeOn` does not by itself lose the Reactor Context when using Reactor operators properly. However, creating independent subscriptions via `subscribe()` or switching to an imperative API that does not preserve context can lose the request context. Therefore, compose publishers end-to-end instead of manually subscribing inside repositories/services.

## 3. What is ReactiveAuditorAware?

Spring Data Commons provides the `ReactiveAuditorAware<T>` interface to determine the current auditor in a reactive model. Its main method returns `Mono<T>`:

```java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
```

The type `T` must match the data type of fields annotated with `@CreatedBy` and `@LastModifiedBy`. For example:

- `ReactiveAuditorAware<String>` if storing a username or subject.
- `ReactiveAuditorAware<Long>` if storing an internal user key.
- `ReactiveAuditorAware<UUID>` if the system uses UUIDs as actor identifiers.

Unlike synchronous `AuditorAware<T>`, which returns `Optional<T>`, `ReactiveAuditorAware<T>` returns `Mono<T>` so identity resolution can participate in the reactive pipeline.

## 4. Retrieving username from Authentication

In common cases, `Authentication.getName()` provides the principal's identifier name. An auditor can be implemented as follows:

```java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("auditorProvider")
public class SecurityAuditorAware implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank());
    }
}
```

Processing steps:

1. `getContext()` retrieves `Mono<SecurityContext>` from the Reactor Context.
2. `map(SecurityContext::getAuthentication)` retrieves the `Authentication` object.
3. `filter(Authentication::isAuthenticated)` keeps only authenticated authentications.
4. Excludes `AnonymousAuthenticationToken`, because an anonymous authentication may report `isAuthenticated() == true` without representing a logged-in user.
5. `map(Authentication::getName)` extracts the principal's identifier.
6. Filters out blank names to avoid storing useless values.

If there is no context, the authentication is unauthenticated, or it is anonymous, the publisher completes empty. The auditor never arbitrarily assigns a fake user.

### 4.1. Why exclude AnonymousAuthenticationToken?

In some Spring Security configurations, an unauthenticated request can still have an `Authentication` representing an anonymous user. This token represents an anonymous principal and may be marked authenticated under Spring Security's internal semantics.

Checking only `isAuthenticated()` is therefore insufficient. If an anonymous principal's name is stored in `createdBy`, audit data may record a technical value like `anonymousUser` instead of a real actor. Exclude anonymous tokens or apply a dedicated actor rule according to business requirements.

### 4.2. Do not use principal.toString() as an identifier

Do not do:

```java
.map(authentication -> authentication.getPrincipal().toString())
```

`toString()` may contain much more information than an identifier, depends on the principal implementation, and risks putting personal data or authentication details into an audit column. Use `Authentication.getName()` or extract an explicit ID property from a defined principal.

## 5. Storing internal user ID instead of username

Usernames can change over time. If the system has a stable internal user key, storing the user ID is usually more convenient for linking data and handling renames.

Suppose the application uses a custom principal:

```java
public record AppPrincipal(Long userId, String username) {
}
```

A custom `Authentication` can set `AppPrincipal` as its principal. The auditor extracts `userId`:

```java
@Component("auditorProvider")
public class UserIdAuditorAware implements ReactiveAuditorAware<Long> {

    @Override
    public Mono<Long> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .filter(AppPrincipal.class::isInstance)
            .cast(AppPrincipal.class)
            .map(AppPrincipal::userId);
    }
}
```

If the principal is not `AppPrincipal`, the publisher completes empty. This is safer than an unchecked cast that throws `ClassCastException` on a different authentication type.

The entity then uses the matching type:

```java
@CreatedBy
private Long createdBy;

@LastModifiedBy
private Long lastModifiedBy;
```

The database schema must have compatible column types. If there is a foreign key to the user table, consider a user deletion/anonymization policy so historical data is not lost.

## 6. Supporting different Authentication types

Spring Security has many principal types depending on the login mechanism. Never assume `getPrincipal()` always returns `UserDetails`.

| Authentication mechanism | Common principal shape | Usable identifier |
|---|---|---|
| Form login / username-password | `UserDetails` or custom principal | Username or internal user ID |
| HTTP Basic | Principal per authentication provider config | `Authentication.getName()` or ID from principal |
| OAuth2 Login | `OAuth2User` | `getName()` or mapped subject/provider ID |
| Resource Server JWT | `Jwt` inside `JwtAuthenticationToken` | `sub` claim or mapped user ID |
| Opaque token | `OAuth2AuthenticatedPrincipal` | Name or validated identity claim |
| Custom authentication | Application-defined principal type | Application's stable ID property |

With `Authentication.getName()`, many standard authentication types already provide an appropriate name. However, systems needing a stable identifier across multiple providers can map the principal to an internal ID right at the authentication layer.

### 6.1. JWT and subject

With a JWT Resource Server, `JwtAuthenticationToken` typically provides a name based on the `sub` claim. A String auditor example can use:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .filter(Authentication::isAuthenticated)
    .filter(authentication ->
        !(authentication instanceof AnonymousAuthenticationToken))
    .map(Authentication::getName);
```

Do not manually read claims from an unverified JWT. The auditor must rely on an `Authentication` already validated by Spring Security, never taking `sub` from client-sent headers or payloads without signature, issuer, audience, and expiration validation.

If `sub` is an ID from an identity provider, decide whether it is sufficiently stable and unique within the application. You may need to map the `(issuer, subject)` pair to an internal user ID to avoid subject collisions across multiple issuers.

### 6.2. OAuth2 Login and multiple identity providers

Two providers can return the same username for two different people. Storing a bare username can make audit records ambiguous. Use an internal ID or a namespaced identifier such as provider/issuer plus subject.

Do not store access tokens, refresh tokens, ID tokens, or all `OAuth2User` attributes in an auditor field. Store only the chosen actor identifier.

## 7. Configuring R2DBC auditing

Once you have a `ReactiveAuditorAware` implementation, enable auditing for Spring Data R2DBC:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
```

`auditorAwareRef` points to the declared `ReactiveAuditorAware` bean. In the previous example, the bean is named `auditorProvider` via `@Component("auditorProvider")`.

If the application has only one matching auditor bean, the configuration can use the default auditor as supported by the Spring Data version. When multiple auditor providers exist, specify the bean name explicitly to prevent the framework from selecting the wrong one.

### 7.1. Enabling date auditing as well

`@EnableR2dbcAuditing` also enables populating creation and modification dates. Entities can declare:

```java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
```

The auditor provider and date-time provider are two separate sources:

- `ReactiveAuditorAware` provides who performed the action.
- DateTimeProvider provides when.

If you need a custom clock for testing or custom time rules, configure a date-time provider per the API of your Spring Data version. Do not derive timestamps from the principal or security context.

### 7.2. Auditing requires entities to be saved through Spring Data

Auditing is applied inside Spring Data lifecycle callbacks. If the application executes direct SQL in a way that bypasses entity auditing callbacks, entity annotations are not automatically applied to that SQL statement.

For example, `DatabaseClient` executing a direct `INSERT` must bind the audit columns the application wants to write:

```java
databaseClient.sql("""
        INSERT INTO customer(name, created_by, created_date)
        VALUES (:name, :createdBy, :createdDate)
        """)
    .bind("name", name)
    .bind("createdBy", auditorId)
    .bind("createdDate", Instant.now())
    .fetch()
    .rowsUpdated();
```

Do not assume `@CreatedBy` automatically supplies values for custom SQL. If an auditor is needed for direct SQL operations, obtain the identity through an appropriate service/provider and bind it explicitly, or use an entity persistence path with auditing callbacks.

## 8. Attaching the auditor to an entity on INSERT and UPDATE

A sample entity:

```java
@Table("document")
public class Document {

    @Id
    private Long id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

On creation:

```java
Mono<Document> createDocument(String title) {
    return documentRepository.save(new Document(title));
}
```

Auditing can set `createdBy`, `lastModifiedBy`, `createdDate`, and `lastModifiedDate` according to the `modifyOnCreate` setting and date provider.

On update:

```java
Mono<Document> renameDocument(Long id, String newTitle) {
    return documentRepository.findById(id)
        .switchIfEmpty(Mono.error(new DocumentNotFoundException(id)))
        .flatMap(document -> {
            document.setTitle(newTitle);
            return documentRepository.save(document);
        });
}
```

Auditing can update `lastModifiedBy` and `lastModifiedDate` from the auditor/time providers at save time. `createdBy` and `createdDate` are normally preserved once the entity has been created.

### 8.1. `modifyOnCreate`

In auditing configuration, `modifyOnCreate` determines whether modified fields are assigned when an entity is newly created. When enabled, `@LastModifiedBy` and `@LastModifiedDate` may share the same values as the created fields on the initial write. This behavior can be helpful so modified fields are always populated, though you should choose according to schema and business conventions.

Explicit configuration example:

```java
@EnableR2dbcAuditing(
    auditorAwareRef = "auditorProvider",
    modifyOnCreate = true
)
```

If you want `lastModifiedBy` to have a value only after the first update, consider configuring `modifyOnCreate = false` and testing on your framework version.

## 9. When there is no SecurityContext

Not every R2DBC operation originates from a logged-in HTTP request. Common cases include:

- Scheduled jobs.
- Batch imports/exports.
- Message consumers.
- Migrations or administrative tasks.
- Integration tests that do not set up a security context.
- Anonymous requests or public flows permitted to write data.

In these cases, `ReactiveSecurityContextHolder.getContext()` may complete empty. `ReactiveAuditorAware` may also return `Mono.empty()`, leaving auditor fields unassigned by the provider. The schema and business rules must decide whether those fields are nullable.

Do not automatically assign `anonymousUser` or `system` for every empty case without distinguishing the cause. Doing so could misattribute unauthenticated user actions to system jobs.

### 9.1. System identity for background jobs

If a job needs a system actor, set the system identity explicitly inside an application-controlled workflow. One approach is using a dedicated Reactor Context key for the system auditor:

```java
public final class AuditActorContext {
    public static final String AUDIT_ACTOR_KEY = "audit.actor";

    private AuditActorContext() {
    }
}
```

The auditor can prioritize an actor attached by an internal workflow before reading the Spring Security context:

```java
@Component("auditorProvider")
public class ContextAwareAuditor implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.deferContextual(contextView -> {
            if (contextView.hasKey(AuditActorContext.AUDIT_ACTOR_KEY)) {
                return Mono.just(contextView.get(
                    AuditActorContext.AUDIT_ACTOR_KEY));
            }

            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
        });
    }
}
```

An internal job can attach the actor when building the pipeline:

```java
public Mono<Void> runNightlyImport() {
    return importService.importData()
        .then()
        .contextWrite(context -> context.put(
            AuditActorContext.AUDIT_ACTOR_KEY,
            "system:nightly-import"
        ));
}
```

This context key must be controlled by internal code. Never let HTTP clients send arbitrary values to claim to be `system` or another actor. Clearly define which jobs are allowed to use system actors, and ensure actor names are stable and traceable.

A simpler alternative is a separate auditor provider for background workers or a `ReactiveAuditorAware` with a fixed fallback. Only use a fallback when the application guarantees that flow can never be an unauthenticated user request.

### 9.2. Public endpoints with write permissions

If a public endpoint allows creating data without logging in, decide how to represent the actor:

- `createdBy = null` if the schema and business logic allow an unspecified user.
- A technical actor such as `anonymous:public-api` if the write source must be distinguished.
- An identity from a validated API key/client credential if the endpoint uses machine-to-machine authentication.

Do not treat `anonymousUser` as a real user. If you need to audit which client called the API, store the client/application identity separately and distinguish it from end-user identity.

## 10. Context propagation through the Reactor pipeline

The reactive security context is read accurately only when the auditing operation executes within a subscription carrying that context. Keep publishers inside the same pipeline:

```java
@Transactional
public Mono<Document> createDocument(Document document) {
    return documentRepository.save(document)
        .flatMap(saved -> auditEventRepository.save(
            AuditEvent.documentCreated(saved.getId())
        ).thenReturn(saved));
}
```

When WebFlux Security has populated the context for the request and publishers are composed normally, auditing callbacks can read the corresponding principal.

Actions that can lose or alter context:

- Calling `subscribe()` manually to create an independent subscription.
- Switching to imperative callbacks that do not preserve the Reactor Context.
- Calling a blocking API or custom thread pool without an appropriate context propagation mechanism.
- Spawning background work detached from the request while expecting it to still carry the original request identity.

Reactor's `publishOn` and `subscribeOn` normally preserve the Reactor Context across the pipeline, though that does not mean every custom `ThreadLocal` or MDC is automatically propagated. If you need logging context propagation, configure Micrometer Context Propagation/Tracing for your Spring/Reactor version or read metadata from the Reactor Context in the right place.

### 10.1. Do not carry user identity into deferred jobs unknowingly

A request may enqueue work that gets processed minutes later. If that job keeps the request's principal without an explicit policy, auditing may mislead readers into thinking the user directly executed the background operation.

Decide the job's actor explicitly:

- User who initiated the request: store `requestedBy` on the job record.
- Worker performing the modification: `lastModifiedBy` can be the system/worker actor.
- Both needed: store `requestedBy` and `processedBy` separately, or record separate audit events.

Do not rely on Reactor Context accidentally remaining present to carry identity into a queued or retried task at a later time.

## 11. User identity, tenant, and system actor

In multi-tenant systems, storing only a username may not be enough to identify the context. Additional fields may be needed:

```java
@CreatedBy
private Long createdBy;

private Long createdTenantId;

private String createdActorType;
```

`@CreatedBy` only supplies the auditor per configuration. Tenant ID and actor type may need to be obtained from another context provider or combined into a custom auditor type.

Record auditor example:

```java
public record AuditActor(Long userId, Long tenantId, String actorType) {
}
```

```java
ReactiveAuditorAware<AuditActor> auditorAware = () ->
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .filter(authentication ->
            !(authentication instanceof AnonymousAuthenticationToken))
        .map(authentication -> (AppPrincipal) authentication.getPrincipal())
        .map(principal -> new AuditActor(
            principal.userId(),
            principal.tenantId(),
            "USER"
        ));
```

This example requires the custom principal to have the exact expected type. In a real system, avoid direct casts if multiple Authentication types exist; use type checks and an appropriate fallback policy.

Auditing does not replace authorization. `@CreatedBy` records the actor, but does not verify whether that user has permission to create or modify an entity within the tenant. Authorization must be enforced separately in the security/service layer, and tenant scope must be checked in queries.

## 12. Protecting data in principals and auditor fields

A principal may contain many attributes such as username, email, display name, tenant, roles, or claims. Select only the minimal identifier needed for storage.

Do not store the following data in auditor fields:

- Passwords or password hashes.
- Access tokens, refresh tokens, ID tokens, or raw JWTs.
- Session cookies or API keys.
- Serialized full `UserDetails`, `Jwt`, or OAuth2 attributes.
- Personal information unnecessary for auditing purposes.

Usually you should store an internal user ID or stable subject. If the audit UI needs to display the user's name, join to the user table or directory service on read rather than copying the full profile into every entity.

If a user can be deleted or anonymized, choose an appropriate strategy: retain the reference ID, switch to a tombstone actor, or store a permitted minimal snapshot. Do not use cascade delete in ways that erase audit trails when legal/business requirements mandate retaining history.

## 13. Auditing and custom SQL

Auditing annotations are applied via Spring Data lifecycle callbacks when entities are inserted/updated through an auditing-enabled persistence path. When using `DatabaseClient` or raw R2DBC SPI, SQL statements do not automatically execute entity callbacks.

Example:

```java
databaseClient.sql("""
        UPDATE document
        SET title = :title,
            last_modified_by = :actor,
            last_modified_date = :modifiedAt
        WHERE id = :id
        """)
    .bind("title", title)
    .bind("actor", actor)
    .bind("modifiedAt", clock.instant())
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Here the application obtains the actor and timestamp itself and binds them into SQL. If custom SQL is used in multiple places, consolidate actor retrieval into a shared abstraction so each repository does not read the security context differently.

Another option is performing entity updates through a repository/template so auditing callbacks are triggered, if the operation and mapping suit the use case.

## 14. Testing ReactiveAuditorAware

Auditor tests should verify scenarios with a security context, anonymous authentication, and no context.

### 14.1. Authenticated principal

Unit test example using `ReactiveSecurityContextHolder.withAuthentication`:

```java
@Test
void returnsAuthenticatedUserName() {
    Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice",
            "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

    StepVerifier.create(
            auditorAware.getCurrentAuditor()
                .contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(authentication))
        )
        .expectNext("alice")
        .verifyComplete();
}
```

The tested publisher is subscribed via `StepVerifier`; `contextWrite` supplies the security context for that subscription. This lets you test ReactiveAuditorAware independently of the HTTP filter chain.

### 14.2. No context

```java
@Test
void completesEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(auditorAware.getCurrentAuditor())
        .verifyComplete();
}
```

This test confirms the provider does not fabricate a username when no context exists.

### 14.3. Anonymous authentication

```java
@Test
void ignoresAnonymousAuthentication() {
    Authentication anonymous =
        new AnonymousAuthenticationToken(
            "key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );

    StepVerifier.create(
            auditorAware.getCurrentAuditor()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(anonymous))
        )
        .verifyComplete();
}
```

This test ensures `isAuthenticated()` does not cause an anonymous principal to be mistakenly recorded as an authenticated user.

### 14.4. Integration testing auditing on R2DBC

Unit testing the provider alone does not prove Spring Data assigns the fields to the entity. You need integration tests with the appropriate database/driver:

1. Set up `ReactiveAuditorAware` and enable `@EnableR2dbcAuditing`.
2. Build a publisher saving an entity inside a security context with an actor.
3. Subscribe and wait for save completion.
4. Read the entity back from the database.
5. Verify `createdBy`, `lastModifiedBy`, and date fields have expected values.
6. Update the entity with a different actor and verify created fields remain unchanged while modified fields update per configuration.
7. Repeat with empty context, anonymous authentication, and background actor.

Test composition example:

```java
Mono<Document> saveAsAlice = documentRepository.save(document)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(aliceAuth));

StepVerifier.create(saveAsAlice)
    .assertNext(saved -> assertEquals("alice", saved.getCreatedBy()))
    .verifyComplete();
```

This is an illustrative example. Getter names and entity construction depend on your actual model. In integration tests, read back from the database to verify values were persisted, rather than checking only the in-memory object.

## 15. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Using imperative `SecurityContextHolder` in WebFlux | May fail to retrieve the right principal when threads change | Use `ReactiveSecurityContextHolder` |
| Using synchronous `AuditorAware` instead of `ReactiveAuditorAware` | Fails to leverage reactive context properly | Implement `ReactiveAuditorAware<T>` |
| Checking only `isAuthenticated()` | Anonymous tokens can be treated as authenticated | Exclude `AnonymousAuthenticationToken` or define a separate actor rule |
| Using `principal.toString()` | May store extraneous or sensitive data | Use `Authentication.getName()` or an explicit ID |
| Casting principal to one type without checking | `ClassCastException` with OAuth2/JWT or other custom auth | Check types and handle supported principal kinds |
| Storing mutable usernames when long-term identity is needed | Audit records become hard to link after username changes | Store a stable user ID/subject |
| Not enabling `@EnableR2dbcAuditing` | Auditing annotations are ignored | Enable configuration and declare the auditor provider |
| Bean name mismatch in `auditorAwareRef` | Provider not found or wrong bean selected | Specify the bean name explicitly |
| Calling `subscribe()` manually in a service | Loses Reactor Context and transaction propagation | Compose publishers and return to the caller |
| Using `DatabaseClient` expecting annotations to assign the auditor | Custom SQL bypasses entity auditing callbacks | Bind actor/date explicitly or use an entity persistence path |
| Assigning `system` for every empty context | May falsely log anonymous requests as system jobs | Distinguish requests, anonymous access, and background actors |
| Carrying request principal into deferred jobs | Audit shows the wrong executing actor | Store requestedBy and processedBy separately when needed |
| Storing tokens or the entire principal | Leaks sensitive data into audit tables | Store only the minimal identifier |
| Assuming auditing checks access permissions | Records the actor while still allowing unauthorized edits | Enforce authorization separately |
| Not testing with a real security context | Fails to catch context propagation or callback bugs | Test the provider and R2DBC integration |

## 16. Workflow for implementing auditing with the reactive security context

When implementing creator/updater identity tracking, follow this sequence:

1. **Choose an identifier:** username, identity-provider subject, or internal user ID; prefer a stable identifier.
2. **Choose the auditor type:** `String`, `Long`, `UUID`, or a domain type matching the entity.
3. **Implement ReactiveAuditorAware:** read `ReactiveSecurityContextHolder`, verify authentication, and exclude anonymous.
4. **Configure auditing:** enable `@EnableR2dbcAuditing` and point `auditorAwareRef` to the proper bean.
5. **Annotate the entity:** apply `@CreatedBy`, `@LastModifiedBy`, and required date annotations.
6. **Define empty-context rules:** specify behavior for public requests, scheduled jobs, workers, and tests.
7. **Design system actors:** use an internal context or separate provider; never apply a blind fallback.
8. **Preserve reactive context:** compose publishers end-to-end and never manually subscribe in repositories/services.
9. **Handle custom SQL:** bind audit fields explicitly when operations bypass auditing callbacks.
10. **Protect identifiers:** never store tokens, passwords, or entire principals.
11. **Test:** verify authenticated, anonymous, no-context, background actor, INSERT, and UPDATE against a real database.

## 17. Key principles to remember

- Spring Data R2DBC uses `ReactiveAuditorAware<T>` to obtain the current actor reactively.
- The reactive security context lives in the Reactor Context; use `ReactiveSecurityContextHolder.getContext()` instead of imperative `SecurityContextHolder`.
- `getCurrentAuditor()` returns `Mono<T>` and can complete empty when no suitable principal exists.
- Check `Authentication.isAuthenticated()` and exclude `AnonymousAuthenticationToken`.
- `Authentication.getName()` fits many authentication mechanisms; internal user IDs are generally more stable than usernames.
- Do not assume every principal is a `UserDetails`; OAuth2, JWT, and custom authentication can use different types.
- Enable `@EnableR2dbcAuditing` and configure `auditorAwareRef` accurately.
- Use `@CreatedBy`/`@LastModifiedBy` for actors and date annotations for timestamps.
- Auditing callbacks apply through Spring Data entity persistence; custom SQL needs explicit audit field bindings.
- Do not assign `system` for every missing-context case; distinguish anonymous requests from background jobs.
- For background jobs, track the requester and executing actor separately if needed.
- Never store passwords, tokens, or entire principals in auditor fields.
- Auditing does not replace authorization and does not automatically create an immutable history of every change.
- Test context propagation and field assignment on the actual database/driver.

Retrieving identity from the reactive security context ensures `createdBy` and `lastModifiedBy` fields accurately reflect the actor of the subscription executing the R2DBC operation. `ReactiveAuditorAware` connects Spring Data auditing with `ReactiveSecurityContextHolder`, while Reactor Context preserves identity across the pipeline without relying on a fixed thread. By choosing stable identifiers, excluding anonymous principals, explicitly handling empty contexts, and separating system actors from end users, auditing data stays consistent and meaningful across both WebFlux requests and background workflows.
