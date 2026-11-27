# Auditing with @CreatedDate, @LastModifiedDate, @CreatedBy, and @LastModifiedBy

Spring Data Auditing automatically records creation timestamps, last-modified timestamps, and the actors behind entity save operations. The four commonly used annotations are **`@CreatedDate`**, **`@LastModifiedDate`**, **`@CreatedBy`**, and **`@LastModifiedBy`**.

When Spring Data REST persists entities through Spring Data JPA, auditing can be triggered during the JPA lifecycle. To make it work, the application needs auditing enabled, **`AuditingEntityListener`** registered on the entity, and an **`AuditorAware`** bean provided if you want to store who created or modified the entity.

Auditing helps answer questions like “when was the record created?”, “when was it last updated?”, and “who performed the action?”. It stores this metadata on the entity itself; auditing alone does not keep a history of every version or diffs of the data.

## 1. Roles of the four annotations

The auditing annotations live in package **`org.springframework.data.annotation`**:

~~~java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
~~~

| Annotation | Meaning | When updated |
|---|---|---|
| **`@CreatedDate`** | Time when the entity was created | On initial insert |
| **`@LastModifiedDate`** | Time when the entity was last modified | On creation and on update |
| **`@CreatedBy`** | Actor who created the entity | On initial insert |
| **`@LastModifiedBy`** | Actor who last modified the entity | On creation and on update |

By default, **`modifyOnCreate`** in Spring Data Auditing is **`true`**, so “last modified” metadata is also populated on initial creation. If you do not want this behavior, configure **`@EnableJpaAuditing(modifyOnCreate = false)`**.

The two date/time annotations can operate without knowing the current user. The two actor annotations (**`@CreatedBy`**, **`@LastModifiedBy`**) require an auditor source, typically an **`AuditorAware<T>`** bean.

## 2. Enabling JPA Auditing

With Spring Data JPA, enable auditing with **`@EnableJpaAuditing`** on a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

The **`@EnableJpaAuditing`** annotation registers Spring Data JPA's auditing infrastructure. If entities use **`@CreatedBy`** or **`@LastModifiedBy`**, specify an **`AuditorAware`** bean so Spring knows the current actor:

~~~java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

The example above always assigns **`system`** as the actor, which suits a simple background task. In real applications, obtain the username from the security context or another trustworthy identity source.

If you only need timestamps, you can enable **`@EnableJpaAuditing`** without configuring **`AuditorAware`**.

## 3. Obtaining the current user with AuditorAware

**`AuditorAware<T>`** returns the actor used for **`@CreatedBy`** and **`@LastModifiedBy`** fields. Type **`T`** must be compatible with the property type on the entity.

Example with Spring Security:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Bean
public AuditorAware<String> auditorProvider() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    };
}
~~~

In the example:

- Authenticated users are identified via **`authentication.getName()`**.
- Anonymous or unauthenticated contexts return **`Optional.empty()`**.
- Spring Data Auditing uses the returned value to populate actor fields.

If the system has batch jobs, schedulers, or message consumers, those flows may lack a SecurityContext. Decide explicitly on the system actor to record—such as **`system-job`**—or allow empty values if business rules permit. Do not record a default actor that obscures real users.

If the actor is a domain object, you can use **`AuditorAware<User>`** instead of **`AuditorAware<String>`**, provided the type matches the **`@CreatedBy`** and **`@LastModifiedBy`** properties.

## 4. Declaring audit fields on an entity

Example Person entity:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // getters and setters
}
~~~

Key points to note:

- **`@EntityListeners(AuditingEntityListener.class)`** registers the JPA listener to receive persistence callbacks.
- **`@CreatedDate`** and **`@LastModifiedDate`** are automatically populated with the current time supplied by auditing.
- **`@CreatedBy`** and **`@LastModifiedBy`** retrieve values from **`AuditorAware`**.
- **`@Column(updatable = false)`** on creation fields ensures JPA omits those columns from UPDATE statements after insert.

You can use **`Instant`** to store timestamps in UTC. Spring Data also supports other common temporal types such as **`LocalDateTime`**, **`OffsetDateTime`**, **`Date`**, or **`Calendar`**, depending on the version and mapping used. Choose one type consistently across the system.

If you use XML to register JPA entity listeners globally, you can configure **`AuditingEntityListener`** in **`orm.xml`** instead of repeating **`@EntityListeners`** on every entity.

## 5. When does Spring Data REST trigger auditing?

Spring Data REST persists entities through repositories. When a repository uses JPA, persist/update operations pass through the JPA lifecycle and the auditing listener updates the audit fields.

Typical flow:

| Spring Data REST request | Persistence operation | Auditing result |
|---|---|---|
| **`POST /people`** | Insert new entity | Sets created and last-modified metadata |
| **`PUT /people/{id}`** | Update existing entity | Preserves created metadata; updates last-modified metadata |
| **`PATCH /people/{id}`** | Partially update entity | Preserves created metadata; updates last-modified metadata |
| Repository **`save`** call from a service | Insert or update depending on entity state | JPA listener runs according to the corresponding lifecycle |

Auditing is not tied exclusively to HTTP requests. Saves performed through services or batch processes are also audited if they go through the configured persistence lifecycle.

If the application uses Spring Data REST with a non-JPA persistence store, use that store's auditing support; **`AuditingEntityListener`** is a JPA-specific listener.

## 6. Distinguishing auditing from transactions and event listeners

Auditing and transactions are related within the same data-saving flow but serve different purposes:

- **Transaction** defines the commit/rollback boundary of data operations.
- **Auditing** updates created/modified metadata on the entity during the persistence lifecycle.
- **Spring Data REST repository events** allow handling logic before or after repository operations, such as **`beforeCreate`** or **`afterSave`**.
- **Audit log/history** stores multiple events or versions for long-term traceability; the four auditing annotations do not provide this automatically.

If a transaction rolls back, metadata changes on the entity are not committed to the database either. However, an in-memory object may have already been populated by the listener prior to rollback; do not treat that object as proof that the transaction committed.

## 7. Keeping audit fields server-managed

Audit fields are normally controlled by the server. Clients should not be able to submit **`createdBy`**, **`createdDate`**, **`lastModifiedBy`**, or **`lastModifiedDate`** to forge history.

You can mark properties with **`@ReadOnlyProperty`** so Spring Data treats them as read-only during writes:

~~~java
import org.springframework.data.annotation.ReadOnlyProperty;

@CreatedDate
@ReadOnlyProperty
@Column(updatable = false)
private Instant createdDate;

@LastModifiedDate
@ReadOnlyProperty
private Instant lastModifiedDate;
~~~

Apply the same approach to the two actor fields if they are exposed in representations. Verify actual responses and write behavior for your Spring Data REST version.

If you do not want clients to see the metadata, exclude those fields from representations via projections or appropriate API configuration. Hiding fields from responses and preventing client writes are two separate requirements; enforce both according to your contract.

## 8. Customizing the auditing clock

By default, auditing gets the current time from **`DateTimeProvider`**. You can supply a custom bean to control the time source—for example, for testing or standardizing clocks:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;

@Bean
public Clock auditingClock() {
    return Clock.systemUTC();
}

@Bean
public DateTimeProvider dateTimeProvider(Clock auditingClock) {
    return () -> Optional.of(Instant.now(auditingClock));
}
~~~

Then reference the bean in configuration:

~~~java
@EnableJpaAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

Using a controllable clock makes timestamp tests deterministic and avoids direct dependence on the system clock. In production, store timestamps consistently—typically in UTC—and convert to display timezones in the UI layer.

If default behavior suffices, you do not need to declare a custom **`DateTimeProvider`**.

## 9. Verifying auditing with integration tests

Test both creation and update by saving the entity and forcing a flush so JPA executes lifecycle callbacks.

Example:

~~~java
@Test
void auditingFieldsAreSetOnCreateAndUpdate() {
    Person person = new Person();
    person.setName("An");

    Person created = personRepository.saveAndFlush(person);

    assertNotNull(created.getCreatedDate());
    assertNotNull(created.getLastModifiedDate());
    assertNotNull(created.getCreatedBy());
    assertNotNull(created.getLastModifiedBy());

    Instant originalCreatedDate = created.getCreatedDate();
    String originalCreatedBy = created.getCreatedBy();

    created.setName("An Nguyen");
    Person updated = personRepository.saveAndFlush(created);

    assertEquals(originalCreatedDate, updated.getCreatedDate());
    assertEquals(originalCreatedBy, updated.getCreatedBy());
    assertNotNull(updated.getLastModifiedDate());
    assertNotNull(updated.getLastModifiedBy());
}
~~~

To make actor tests deterministic, configure **`AuditorAware`** in tests to return a fixed actor such as **`test-user`**. For Spring Security-based tests, establish authentication before calling the repository.

You can also add HTTP integration tests for Spring Data REST:

1. Send a POST to create a Person via **`/people`**.
2. Read the response or GET the item back and verify created/modified fields are populated.
3. Send a PATCH or PUT changing the name.
4. GET the item back to verify created metadata stayed unchanged and modified metadata was updated.
5. Verify the actor reflects the request's authenticated user.

Do not check only the HTTP status. Reload the entity or query the database after the transaction completes to verify the data was actually persisted.

## 10. Common errors and resolutions

| Symptom | Possible cause | Resolution |
|---|---|---|
| Date fields remain null | **`@EnableJpaAuditing`** not enabled or listener not registered | Check configuration and **`@EntityListeners`** |
| CreatedDate is populated, but CreatedBy is null | Missing **`AuditorAware`** or actor source returns empty | Register an auditor provider and check the security context |
| LastModifiedDate does not change on update | Entity did not go through JPA update lifecycle or no dirty change occurred | Force flush in tests and inspect SQL/persistence state |
| Actor is always system | Auditor provider returns a hardcoded value | Retrieve the actor from authentication or an appropriate identity source |
| CreatedDate changes after update | Created field is unprotected or overwritten by application logic | Use **`updatable = false`**, read-only mapping, and disallow client writes |
| Timestamp timezone mismatch | Mixing temporal types or inconsistent timezone conversions | Prefer Instant/UTC and convert timezones on display |
| Audit fields not saved via REST | JPA listener not configured for the entity or repository does not use JPA | Check the persistence module and active listener |

## 11. Configuration checklist

- Spring Data JPA and an appropriate persistence provider are present.
- **`@EnableJpaAuditing`** is present in Spring configuration.
- Entities have **`@EntityListeners(AuditingEntityListener.class)`** or the listener is registered globally via XML.
- Audit fields use the proper annotations from **`org.springframework.data.annotation`**.
- **`AuditorAware<T>`** is configured when recording creator/modifier is required.
- The return type of **`AuditorAware`** is compatible with the actor field types.
- Security context or background actor sources are explicitly handled.
- Server-managed audit fields are protected against client tampering.
- Integration tests verify both insert and update after flush/commit.
- If full history is required, design a dedicated audit log or version history.

Official references:

- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
