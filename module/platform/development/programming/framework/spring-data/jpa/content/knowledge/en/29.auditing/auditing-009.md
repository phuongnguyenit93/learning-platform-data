# Distinguishing Last Modifier Information from Per-Version History

In Spring Data JPA applications, two requirements are often confused:

1. **Knowing who created and who last modified a record:** storing metadata such as creator, creation timestamp, last modifier, and last modification timestamp directly on the entity table.
2. **Knowing how data changed over time:** storing previous and subsequent versions of an entity so you can inspect its state at a point in time or a specific revision.

Spring Data JPA Auditing solves the first requirement. Hibernate Envers is a common choice to solve the second requirement by storing revision history. The two mechanisms can be used together, but they do not replace each other.

This article explains how each approach works, how to configure the actor performing an operation, querying history, the impact of bulk updates/deletes, testing approaches, and criteria for selecting a solution based on business requirements.

**Example prerequisites:** code snippets use Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence, and Hibernate. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a suitable schema. Examples retrieve the user from Spring Security; if the application does not use Spring Security, replace the principal lookup with your application's trusted identity source. These are parts of a Spring Boot application, not standalone programs runnable with javac alone.

## 1. Two Different Requirements

Suppose a **products** table has a product:

| id | name | price | created_by | created_at | last_modified_by | last_modified_at |
|---:|---|---:|---|---|---|---|
| 42 | Keyboard | 800000 | linh | 2026-10-01 | minh | 2026-11-09 |

The created_by and last_modified_by columns answer:

- Who created the product?
- Who last modified it?
- When was the product created and last modified?

However, they cannot answer:

- Before November 9, what was the product's price?
- Who changed the price from 750000 to 800000?
- How many times did the product name change?
- What was the product's state at the third revision?

When Minh edits the product, last_modified_by and last_modified_at are updated. The previous modifier's value is overwritten. If history is needed, there must be a place to store past versions.

| Capability | Spring Data Auditing | Revision History |
|---|---|---|
| Creator | Can store | Can store in revision metadata |
| Creation time | Yes | Yes |
| Last modifier | Yes | Can determine from latest revision if actor is stored |
| Last modification time | Yes | Can determine from latest revision |
| View old values | No | Yes |
| View entity state at an earlier revision | No | Yes |
| Track multiple changes | No | Yes |
| Storage footprint | Low | Higher, proportional to revision count |

Do not call the four created/modified columns a version history system. They only describe the current metadata of a row.

## 2. Spring Data JPA Auditing Stores Current Metadata

Spring Data Auditing provides four commonly used annotations:

- **@CreatedBy**: creator of the entity.
- **@CreatedDate**: creation timestamp of the entity.
- **@LastModifiedBy**: last modifier of the entity.
- **@LastModifiedDate**: last modification timestamp of the entity.

Values are updated through a JPA entity lifecycle listener. They are stored in the entity's row and do not automatically create a separate history table.

### Creating a Shared Auditable Base Class

You can place audit fields in a mapped superclass:

~~~java
package com.example.audit;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class Auditable {

    @CreatedBy
    @Column(name = "created_by", updatable = false, length = 100)
    private String createdBy;

    @CreatedDate
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @LastModifiedBy
    @Column(name = "last_modified_by", length = 100)
    private String lastModifiedBy;

    @LastModifiedDate
    @Column(name = "last_modified_at")
    private Instant lastModifiedAt;

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

An entity extending this class:

~~~java
package com.example.catalog.domain;

import com.example.audit.Auditable;
import jakarta.persistence.*;

import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product extends Auditable {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public void rename(String newName) {
        this.name = newName;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

**@MappedSuperclass** allows entities to inherit audit field mappings without creating a separate table for Auditable. **@EntityListeners(AuditingEntityListener.class)** connects JPA lifecycle callbacks with Spring Data Auditing.

Using **updatable = false** on createdBy and createdAt prevents JPA from including these columns in regular UPDATE statements. This is ORM-mapping-level protection; database permissions and direct SQL statements still need to be managed separately.

## 3. Enabling Auditing and Providing AuditorAware

Spring Data needs to know the current actor to populate @CreatedBy and @LastModifiedBy. The **AuditorAware<T>** interface supplies that information.

Configuration:

~~~java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

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
~~~

**@EnableJpaAuditing** activates the auditing mechanism. The **auditorAwareRef** attribute specifies the bean used to obtain the actor.

In the example:

- Logged-in users are identified by authentication.getName().
- Anonymous requests are not mistakenly attributed to an authenticated user.
- When there is no actor, AuditorAware returns Optional.empty(); auditor fields can remain null depending on configuration and application requirements.

If the system has batch jobs or schedulers, define an actor for background operations, such as a service account identifier like **system:nightly-import**. Do not accept createdBy/lastModifiedBy directly from a request body because clients can spoof the actor.

If not using Spring Security, AuditorAware can retrieve the user ID from a request context, application context, or custom authentication mechanism. The data source must reflect the authenticated actor.

## 4. When Is Metadata Updated?

When an entity is first persisted:

- createdBy and createdAt are set.
- lastModifiedBy and lastModifiedAt can also be set on initial creation, since that is also the first modification.

When a managed entity is updated and JPA executes a lifecycle update:

- createdBy and createdAt are preserved.
- lastModifiedBy and lastModifiedAt are updated with the current actor and time.

Service example:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = repository.findById(id).orElseThrow();
        product.changePrice(newPrice);

        // Dirty checking will write changes on flush/commit.
        // AuditingEntityListener updates lastModified metadata.
    }
}
~~~

An entity loaded within a transaction is managed. Dirty checking detects changes and Hibernate issues an UPDATE on flush. Spring Data's entity listener updates the audit fields in the corresponding lifecycle callback.

If using **save()** on a repository, Spring Data still performs persist or merge depending on entity state. For an entity already managed in a transaction, calling save solely to trigger dirty checking is usually unnecessary.

**@Transactional(readOnly = true)** is not a write transaction. Do not use a read-only transaction for data-modifying operations and expect audit metadata to update like a normal write.

## 5. Why Is Auditing Not Per-Version History?

Suppose a product changes three times:

| Date | Actor | Price |
|---|---|---:|
| 10/01 | linh | 700000 |
| 10/05 | minh | 750000 |
| 11/09 | hoa | 800000 |

If using only Spring Data Auditing, the final products row might store:

~~~text
price = 800000
created_by = linh
created_at = 2026-10-01
last_modified_by = hoa
last_modified_at = 2026-11-09
~~~

Information about the prices 700000 and 750000 has been overwritten. The last_modified_by column also retains only the most recent actor. There is no way to reconstruct the full history from these four columns.

If requirements demand knowing what each revision changed, a dedicated history mechanism is needed, such as:

- Hibernate Envers.
- A custom-designed audit table.
- An event store or domain event log.
- Database-level CDC/auditing, depending on architecture.

## 6. Hibernate Envers Stores Revision History

**Hibernate Envers** is a Hibernate module for tracking entity change history. Envers creates revisions and corresponding audit tables for entities annotated with **@Audited**.

On the Product entity, you can add:

~~~java
import org.hibernate.envers.Audited;

@Entity
@Table(name = "products")
@Audited
public class Product extends Auditable {
    // id, name, price, and other fields
}
~~~

When an entity is created, updated, or deleted through an Envers-supported entity lifecycle, Envers writes revision data within the same database transaction.

With the typical default configuration:

- The **REVINFO** table stores revision information, such as the revision number and timestamp.
- The **products_AUD** table stores the audited state of Product across revisions.
- The **REV** column links the audit record to the revision.
- The **REVTYPE** column indicates the change type: ADD, MOD, or DEL.

Table names and structures are configurable. This is an entity-state history model, not automatic logging of arbitrary SQL operations.

### Dependency Configuration

With Spring Boot, add the Envers module compatible with the Hibernate version managed by Spring Boot:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
~~~

Normally, let Spring Boot dependency management pick a version aligned with the existing Hibernate ORM version. Do not upgrade Envers independently to a different version without verifying compatibility.

## 7. Marking Entities and Fields to Audit

You can annotate the entire entity:

~~~java
@Entity
@Audited
@Table(name = "products")
public class Product {
    // ...
}
~~~

Eligible persistent properties are then tracked in revision history.

If a field does not need history stored, use **@NotAudited**:

~~~java
@Audited
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @NotAudited
    private String temporaryDisplayHint;
}
~~~

Do not include sensitive data such as password hashes, tokens, secrets, or unnecessary information in audit history simply because the entity is annotated with @Audited. History can outlive current data and requires appropriate access control, retention, masking, and deletion policies.

For associations, determine whether the target entity is audited. Envers provides mapping options such as **RelationTargetAuditMode.NOT_AUDITED** when you want to store a link to a non-audited entity; design and test each relationship type individually.

## 8. Querying Entity State at Earlier Revisions

Envers provides **AuditReader** to read history.

Service example:

~~~java
@Service
public class ProductHistoryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<Number> findRevisions(Long productId) {
        AuditReader reader =
            AuditReaderFactory.get(entityManager);

        return reader.getRevisions(Product.class, productId);
    }

    @Transactional(readOnly = true)
    public Product findAtRevision(Long productId, Number revision) {
        AuditReader reader =
            AuditReaderFactory.get(entityManager);

        return reader.find(Product.class, productId, revision);
    }
}
~~~

**getRevisions(Product.class, productId)** returns the revision numbers that contain history for that entity.

**find(Product.class, productId, revision)** returns the state of Product at the requested revision. The result is a historical state reconstructed from audit data; do not treat that object as a live entity to overwrite production data.

Usage example:

~~~java
List<Number> revisions = historyService.findRevisions(productId);

for (Number revision : revisions) {
    Product snapshot =
        historyService.findAtRevision(productId, revision);

    System.out.println(
        revision + " -> " + snapshot.getName()
            + ", price=" + snapshot.getPrice()
    );
}
~~~

This snippet illustrates how to call the API in an application with Envers and existing audit data. Actual values depend on the database's revision history.

If an entity has been deleted, Envers can still record a deletion revision; reading pre-deletion state and how DEL revisions are represented depend on the audit strategy and configuration. Test deletion scenarios specifically.

## 9. Storing the Actor and Additional Information in Revisions

By default, Envers stores a revision number and timestamp. If you need to know **who** created a revision, use a custom revision entity and **RevisionListener** to add an actor or relevant metadata.

Example custom revision entity structure:

~~~java
@Entity
@Table(name = "REVINFO")
@RevisionEntity(ActorRevisionListener.class)
public class ActorRevision extends DefaultRevisionEntity {

    @Column(name = "actor", length = 100)
    private String actor;

    public String getActor() {
        return actor;
    }

    public void setActor(String actor) {
        this.actor = actor;
    }
}
~~~

Listener:

~~~java
public class ActorRevisionListener implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        ActorRevision revision = (ActorRevision) revisionEntity;

        // Read the actor from a context safely managed by the application.
        revision.setActor(AuditActorContext.currentActor());
    }
}
~~~

**AuditActorContext** in the example is an application-built adapter providing the actor to the listener; it is not a built-in Hibernate class. Design this context to work properly across request threads, async execution, scheduled jobs, and message consumers. Do not assume RevisionListener can always receive a Spring bean via constructor injection.

You can add fields such as correlation ID or change source type if needed for investigations. Avoid storing entire request payloads or authentication secrets in revision metadata.

When combining Spring Data Auditing and Envers:

- createdBy/lastModifiedBy provide quick information directly on the current entity.
- The actor in revision metadata identifies who performed each revision.
- Envers stores entity state per revision so versions can be compared.

You do not always need both. Choose based on current-state and historical querying needs.

## 10. Bulk Update/Delete Can Bypass Both Mechanisms

An important limitation: JPQL bulk updates/deletes and native SQL DML execute directly against the database, bypassing the normal entity lifecycle.

Example:

~~~java
@Modifying
@Transactional
@Query("""
    update Product p
    set p.price = :price
    where p.id = :id
    """)
int updatePriceDirectly(
    @Param("id") Long id,
    @Param("price") BigDecimal price
);
~~~

This is a bulk JPQL update. It does not load each Product and perform a lifecycle update. Consequently:

- Spring Data's AuditingEntityListener is not invoked per entity.
- @LastModifiedBy and @LastModifiedDate are not updated automatically.
- Envers does not automatically create revisions for each entity affected by bulk DML.
- The persistence context may still hold stale objects after the database has changed.

If full audit history is required, use entity lifecycle updates or explicitly record audit records within the same transaction. With bulk DML, you can update audit columns directly in the statement, though that still does not create full revision history like Envers.

Example updating metadata directly:

~~~java
@Modifying
@Transactional
@Query("""
    update Product p
    set p.price = :price,
        p.lastModifiedBy = :actor,
        p.lastModifiedAt = :changedAt
    where p.id = :id
    """)
int updatePriceAndAudit(
    @Param("id") Long id,
    @Param("price") BigDecimal price,
    @Param("actor") String actor,
    @Param("changedAt") Instant changedAt
);
~~~

This only updates current metadata. It does not create old/new snapshots in Envers. If history is required, design a dedicated revision/audit-writing operation or avoid bulk DML for that use case.

After bulk DML, consider flushing before and clearing the persistence context after the query to prevent managed entities from becoming stale. The **flushAutomatically** and **clearAutomatically** options on @Modifying can help, though clearing detaches entities in the current persistence context.

## 11. @Version Is Neither Auditing Nor Revision History

Another annotation often confused with auditing is JPA's **@Version**:

~~~java
@Version
private Long version;
~~~

@Version supports optimistic locking. It helps detect transactions updating stale data, typically by including the current version in the UPDATE predicate.

Suppose two users load Product at version 4:

1. User A updates first; version increments to 5.
2. User B still holds version 4.
3. When B updates, the version condition no longer matches and the provider raises an optimistic locking conflict.

@Version does not store the contents of previous versions. It only manages the current version number to detect concurrent updates.

| Mechanism | Primary Purpose |
|---|---|
| @CreatedBy / @LastModifiedBy | Who created and who last modified |
| @CreatedDate / @LastModifiedDate | When created and when last modified |
| Hibernate Envers | Entity state history across revisions |
| @Version | Detecting concurrent updates via a version counter |

An entity can use @Version, Spring Data Auditing, and Envers together if business requirements call for all three capabilities.

## 12. Revision History Is Not the Same as a Domain Event Log

Envers stores entity state per revision. That is useful for answering "What value did Product have at revision 7?".

However, it does not fully answer business questions on its own:

- Why did the user change the price?
- Which order led to the product change?
- Which notifications did the system send?
- In what sequence did a business action occur?
- Should an event be published to another system?

This is the difference between state history and domain events:

- **State history** stores entity snapshots/states across revisions.
- **Domain events** express business-meaningful occurrences, such as ProductPriceChanged with old price, new price, actor, reason, and correlation ID.
- **Transactional outbox** stores events to publish within the same database transaction so a worker can dispatch them after commit.

If you need business investigations, system integration, or action sequence reconstruction, consider domain events/outbox instead of treating Envers as a complete event store.

## 13. Choosing a Strategy Based on Requirements

| Requirement | Appropriate Solution |
|---|---|
| Only need to display the last modifier | Spring Data Auditing |
| Need createdAt/createdBy and modifiedAt/modifiedBy | Spring Data Auditing |
| Need to view entity state at older revisions | Hibernate Envers |
| Need actor per revision | Envers with custom revision entity/listener |
| Need to publish events after transaction commit | Transactional event/outbox |
| Need to detect concurrent updates by two users | @Version optimistic locking |
| Need to audit bulk SQL or non-JPA changes | Database auditing/CDC or explicit audit writes |

If the application only needs four audit columns, Envers can add unnecessary storage and complexity. If requirements call for per-edit history, four audit columns are insufficient.

## 14. Testing Spring Data Auditing

An integration test should verify that creation metadata is preserved and modification metadata is updated.

Example test configuration providing a fixed actor:

~~~java
@TestConfiguration
@EnableJpaAuditing
class AuditTestConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("test-user");
    }
}
~~~

Test:

~~~java
@DataJpaTest
@Import(AuditTestConfiguration.class)
class ProductAuditingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void recordsCreatedAndModifiedMetadata() {
        Product product =
            new Product("Keyboard", new BigDecimal("800000"));

        entityManager.persistAndFlush(product);

        assertThat(product.getCreatedBy()).isEqualTo("test-user");
        assertThat(product.getCreatedAt()).isNotNull();
        assertThat(product.getLastModifiedBy()).isEqualTo("test-user");
        assertThat(product.getLastModifiedAt()).isNotNull();

        Instant originalCreatedAt = product.getCreatedAt();

        product.changePrice(new BigDecimal("850000"));
        entityManager.flush();

        assertThat(product.getCreatedAt()).isEqualTo(originalCreatedAt);
        assertThat(product.getLastModifiedBy()).isEqualTo("test-user");
        assertThat(product.getLastModifiedAt()).isNotNull();
    }
}
~~~

The test assumes the Product entity and auditing listener are configured as in previous sections. If the application already enables auditing in its main configuration, do not enable a conflicting configuration in tests; import or override AuditorAware according to your actual test context.

To test changing actors, use a test AuditorAware that can return different actors between two flushes. To test exact timestamps, configure a DateTimeProvider using a fixed Clock instead of comparing timestamps based on test execution speed.

## 15. Testing Envers History

With Envers, integration tests should:

1. Persist Product initially and flush.
2. Change the price in a subsequent transaction and flush/commit.
3. Retrieve the revision list using AuditReader.
4. Read Product at each revision.
5. Verify old and new prices match expectations.
6. Also test deletion revisions if the use case requires storing deletion history.

Example history-reading snippet in a test:

~~~java
@Test
@Transactional
void storesProductRevisions() {
    AuditReader reader =
        AuditReaderFactory.get(entityManager);

    List<Number> revisions =
        reader.getRevisions(Product.class, productId);

    assertThat(revisions).hasSizeGreaterThanOrEqualTo(2);

    Product firstVersion =
        reader.find(Product.class, productId, revisions.get(0));

    Product latestVersion =
        reader.find(
            Product.class,
            productId,
            revisions.get(revisions.size() - 1)
        );

    assertThat(firstVersion.getPrice())
        .isEqualByComparingTo("800000");

    assertThat(latestVersion.getPrice())
        .isEqualByComparingTo("850000");
}
~~~

This snippet assumes Product already has at least two committed revisions and Envers is configured. In real tests, create the entity and commit/flush across appropriate transaction boundaries; Envers revisions are typically written when the transaction completes successfully. If all changes occur in a single transaction, they may belong to the same revision rather than creating separate revisions.

Do not check only the revision count. Verify snapshot values, actor metadata, revision types, deletions, and rollback behavior according to application requirements.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| createdBy/lastModifiedBy always null | Auditing not enabled or AuditorAware returns empty | Check @EnableJpaAuditing, entity listener, and actor context |
| Timestamps not updated | Missing @CreatedDate/@LastModifiedDate or listener | Check mapping and lifecycle |
| lastModifiedBy spoofed | Actor taken directly from request body | Obtain principal from a trusted security context |
| No old price history | Only using LastModified columns | Enable Envers or design audit history |
| Envers creates no revisions | Entity not @Audited or operation uses bulk DML | Check mapping and use entity lifecycle |
| Bulk update does not change audit metadata | Bulk JPQL bypasses entity listener | Update metadata explicitly or use entity updates |
| _AUD table not found | Envers not added / schema not created | Check dependencies, DDL, and migrations |
| History lacks actor | Default revision metadata has no user | Create a custom revision entity/listener |
| Audit table grows very fast | Recording too many revisions or unnecessary fields | Define audit scope and retention policies |
| Confusing @Version with history | Version only supports optimistic locking | Use Envers or an event/audit store for history |
| Audit history contains sensitive data | @Audited placed on entire entity without reviewing fields | Use @NotAudited and data protection policies |

## 17. Audit Design Checklist

- [ ] Determine whether only the last modifier is needed or per-version history is required.
- [ ] Use @CreatedBy/@CreatedDate/@LastModifiedBy/@LastModifiedDate for current metadata.
- [ ] Enable @EnableJpaAuditing and provide AuditorAware.
- [ ] Obtain the actor from an authenticated identity; do not trust client-submitted data.
- [ ] Define actors for batch jobs, schedulers, and message consumers.
- [ ] Use @Audited and Hibernate Envers when revision history is needed.
- [ ] Use a custom revision entity if actor or correlation metadata is needed per revision.
- [ ] Exclude sensitive/unnecessary data from audit history.
- [ ] Understand that bulk JPQL/native DML does not trigger standard entity auditing/Envers lifecycles.
- [ ] Use @Version for optimistic locking, not as a replacement for history.
- [ ] Use domain events/outbox if business intent or reliable event publishing is needed.
- [ ] Design read permissions, retention, migrations, and audit table capacity.
- [ ] Test create, update, delete, rollback, bulk DML, and actor attribution.

## 18. Conclusion

**Spring Data JPA Auditing** stores metadata of the current state: who created it, when it was created, who last modified it, and when it was last modified. Those modified values are overwritten on the next update; this mechanism does not retain prior values.

**Hibernate Envers** stores revision history so entity states can be queried at earlier versions. If an actor is needed per revision, you can add a custom revision entity and listener. Both mechanisms depend on the entity lifecycle and do not automatically track bulk JPQL/native DML.

Choose based on the questions the system must answer: current metadata uses Spring Data Auditing; state history uses Envers; business event history uses domain events/outbox; concurrent update detection uses @Version. These mechanisms can be combined when each solves a distinct requirement.