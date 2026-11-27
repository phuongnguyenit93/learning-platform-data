# Recording the Creator and Modifier with @CreatedBy, @LastModifiedBy, and AuditorAware

Spring Data JPA Auditing automatically stores information about who performs operations on an entity. The two annotations `@CreatedBy` and `@LastModifiedBy` record who created and who last modified a record. The `AuditorAware<T>` interface provides the current user's identity for Spring Data to populate these fields.

This mechanism gives the application basic accountability history without passing a username or user ID into every `save` call. The key parts are configuring auditing, attaching the listener to the entity, and providing an `AuditorAware` implementation suited to how the application identifies the current user.

## 1. What Do the Two Auditor Fields Mean?

- `@CreatedBy`: marks the property that stores the creator of the entity. The value is set when the entity is first created.
- `@LastModifiedBy`: marks the property that stores the last modifier. The value is updated when the entity is modified.

These two annotations belong to the `org.springframework.data.annotation` package. They describe auditing metadata for Spring Data; the annotations themselves do not automatically know who the currently logged-in user is.

For example, an article record might store:

| Time | createdBy | lastModifiedBy |
|---|---|---|
| First saved by alice | alice | alice |
| Later edited by bob | alice | bob |
| Later edited again by alice | alice | alice |

Under the default `@EnableJpaAuditing` configuration `modifyOnCreate = true`, the `@LastModifiedBy` field is also assigned on creation. If you set `modifyOnCreate = false`, auditing does not set modification metadata during initial creation.

The auditor is the identity performing the operation, not necessarily the owner of the record. For example, a support agent might edit a record created by a customer; in that case, `createdBy` remains the customer while `lastModifiedBy` becomes the support agent.

## 2. Declaring Auditing Fields on the Entity

Shared fields can be placed in a superclass annotated with `@MappedSuperclass`. Entities extending this class share the same mapping and listener.

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(name = "last_modified_by")
    private String lastModifiedBy;

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

Key points to understand:

- `@MappedSuperclass` allows child entities to inherit persistent properties from the superclass. The superclass is not mapped to its own table solely because of this annotation.
- `@EntityListeners(AuditingEntityListener.class)` registers the listener to receive JPA lifecycle events and invoke Spring Data Auditing.
- `updatable = false` on `createdBy` prevents the creator column from being included in regular SQL UPDATE statements. The value is still written on INSERT.
- `lastModifiedBy` can change during subsequent updates.

A concrete entity can extend the auditing class:

```java
package com.example.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Article extends AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
    }

    public void rename(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

If you do not use a shared superclass, you can place `@EntityListeners(AuditingEntityListener.class)`, `@CreatedBy`, and `@LastModifiedBy` directly on each entity. Using a superclass avoids repeating the mapping across many entities.

## 3. Enabling JPA Auditing

Spring Data requires auditing to be enabled in the application configuration. The example below names the auditor-providing bean `auditorAware`:

```java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {
}
```

`@EnableJpaAuditing` registers Spring Data JPA's auditing infrastructure. The `auditorAwareRef` attribute points to the bean implementing `AuditorAware`. This name must match the bean name in the configuration. If the application has only one `AuditorAware` bean, you can use the default configuration without specifying a reference; an explicit declaration improves readability when a project has multiple configurations.

Enabling `@EnableJpaAuditing` alone is not enough if the entity has not registered `AuditingEntityListener`. Conversely, the listener also requires the auditing infrastructure to be activated and able to resolve the current auditor.

## 4. How Does AuditorAware Retrieve the Current User?

`AuditorAware<T>` is the Spring Data interface used to obtain the current identity. Type `T` must be compatible with the type of the properties annotated with `@CreatedBy` and `@LastModifiedBy`.

If the application uses Spring Security and stores the username as a `String`, you can implement it as follows:

```java
package com.example.config;

import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorAware() {
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
}
```

The `getCurrentAuditor()` method returns `Optional<String>`:

1. Reads `Authentication` from `SecurityContextHolder`.
2. Checks whether the context contains an authentication.
3. Skips unauthenticated or anonymous cases.
4. Returns the principal name via `authentication.getName()` when authenticated.

The example uses `String` because `createdBy` and `lastModifiedBy` in `AuditedEntity` are also `String`. If you want to store a user ID, use a consistent type such as `AuditorAware<Long>` along with `Long` fields, and extract the ID from your application's custom principal.

If not using Spring Security, you can implement `AuditorAware` based on the system's own actor resolution mechanism. For background tasks, schedulers, or batch jobs without a login request, the application should provide a meaningful system identity such as `system` or `batch-job` rather than leaving history without an actor.

`Optional.empty()` means the provider does not supply an auditor for that operation. Auditor fields may remain unset; if business rules require a creator/modifier, you must clearly define how anonymous requests and background tasks are handled.

## 5. Using Auditing Through Repositories

Once configured, business code simply saves the entity via the repository. The application does not need to manually call setters to assign `createdBy` or `lastModifiedBy`.

```java
package com.example.repository;

import com.example.domain.Article;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository
        extends JpaRepository<Article, Long> {
}
```

Example usage flow:

```java
Article article = new Article("Spring Data JPA");
articleRepository.save(article);

// Another user modifies the entity in a subsequent transaction.
article.rename("Spring Data JPA Auditing");
articleRepository.save(article);
```

When the entity is persisted, the listener invokes the auditing handler to set creation metadata. When the entity is updated, the listener updates modification metadata. Actual writing happens according to the JPA lifecycle, typically at flush or transaction commit time; do not assume values are already synchronized in the database before the persistence context flushes.

Expected outcome if the initial save is performed by `alice` and the subsequent edit by `bob`:

- After creation: `createdBy = "alice"`, `lastModifiedBy = "alice"`.
- After modification: `createdBy = "alice"`, `lastModifiedBy = "bob"`.

The values are stored in the database alongside the entity, so they can be read back via the repository after the transaction completes.

## 6. Relationship Between User Auditing and Timestamp Auditing

Spring Data JPA also provides `@CreatedDate` and `@LastModifiedDate` to store creation and update timestamps. They can be used alongside the two auditor annotations:

```java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
```

Date/time fields typically use `Instant`, `LocalDateTime`, or another temporal type supported by Spring Data. When both the actor and the timestamp are needed, the entity can store four pieces of information:

| Field | Meaning |
|---|---|
| `createdBy` | Who created the record |
| `createdDate` | When the record was created |
| `lastModifiedBy` | Who last modified the record |
| `lastModifiedDate` | When the record was last modified |

The two user annotations do not automatically create timestamps. If dates and times are needed, you must declare the corresponding date fields as well. Spring Data uses the auditing handler to set them within the same lifecycle process.

## 7. Notes on Async, Batch, and Operations Outside JPA

Auditing relies on the auditor information the application provides at the moment the listener processes the entity. Several scenarios require dedicated design:

- **Async execution:** `SecurityContextHolder` is typically bound to the request-handling thread. When offloading work to another thread, the context may no longer be present. You need to propagate or set the identity safely for async tasks.
- **Scheduled jobs and batch:** there is no logged-in user as in a normal request. Use a clearly named system auditor to distinguish automated changes from user changes.
- **Anonymous requests:** if `AuditorAware` returns `Optional.empty()`, the system has no auditor to record. Decide whether the field is nullable or needs a system actor assigned.
- **Bulk JPQL UPDATE/DELETE:** bulk queries act directly on the database and bypass per-entity lifecycle callbacks. Therefore, `AuditingEntityListener` does not automatically update `lastModifiedBy` for bulk-updated rows. If auditing is needed in such operations, include the auditor value in the statement or use a separate recording process.
- **Native SQL or writes outside JPA:** the JPA listener does not run when data is updated directly via SQL, another tool, or another service. If every write path must be audited, ensure all writers follow the same convention or move part of the responsibility down to the database.

Application auditing is useful for knowing the actor within JPA flows. It does not replace an immutable security audit log when a system requires tamper-evident records, before/after change tracking, or full history.

## 8. Common Errors and How to Verify

- **Missing `@EnableJpaAuditing`:** the auditing infrastructure is not registered. Enable the annotation in Spring configuration.
- **Missing `@EntityListeners(AuditingEntityListener.class)`:** the entity does not receive auditing callbacks. Register the listener on the entity or shared `@MappedSuperclass`.
- **No `AuditorAware` bean:** Spring cannot obtain an auditor when configuration requires the bean. Create the bean and ensure its name matches `auditorAwareRef`.
- **Wrong generic type:** `AuditorAware<Long>` is incompatible with an auditor field of type `String`. Align the return type and property type.
- **Always receiving empty values:** check SecurityContext, authentication status, anonymous tokens, and context propagation across threads.
- **Creator changed on update:** check column mapping and do not manually reassign `createdBy`. You can set `updatable = false` to prevent updating this column in SQL UPDATE statements.
- **Bulk update does not change modifier:** this is expected behavior because bulk updates bypass the entity listener. Update the auditor explicitly or use normal entity operations if lifecycle callbacks are required.

To verify, create an entity while logged in as user A, flush, and reload to check both auditor fields. Then modify the entity as user B in another transaction, flush, and reload again. The result should keep `createdBy` as A and update `lastModifiedBy` to B. Add a test for anonymous requests or batch jobs to confirm the policy when no request user is present.

## 9. Key Takeaways

`@CreatedBy` and `@LastModifiedBy` mark the fields that store the actors creating and modifying an entity. `AuditingEntityListener` connects the JPA lifecycle to the auditing handler, `@EnableJpaAuditing` enables the infrastructure, and `AuditorAware<T>` supplies the current identity. When implementing, align the auditor data type, handle anonymous and background tasks explicitly, and remember that bulk updates and write paths outside JPA do not automatically trigger the auditing listener.