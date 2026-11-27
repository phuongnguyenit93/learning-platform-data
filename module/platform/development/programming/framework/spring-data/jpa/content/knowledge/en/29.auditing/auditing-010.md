# Spring Data Envers, RevisionRepository, and the Hibernate Envers Requirement

Spring Data Envers connects Hibernate Envers' history-querying capabilities with the Spring Data JPA repository model. Hibernate Envers records versions of entities marked for auditing; Spring Data Envers provides RevisionRepository to read those revisions using familiar methods such as finding the latest revision, finding state at a specific revision, and paginating history.

Three components play distinct roles:

- **Hibernate Envers** is the engine that records changes and manages history tables.
- **Spring Data Envers** integrates Envers into Spring Data JPA's repository infrastructure.
- **RevisionRepository** is the Spring Data interface provided for applications to query entity history.

Merely adding RevisionRepository to an interface is not enough. The project needs Hibernate Envers on the classpath, repositories must be backed by the Envers repository infrastructure, and the entity must be annotated with @Audited. This lesson walks through dependencies, configuration, audit table models, recording revisions, querying with RevisionRepository/AuditReader, relationships, revision metadata, transactions, performance, and testing.

## 1. How Does Spring Data Auditing Differ from Hibernate Envers?

Spring Data JPA has two capabilities that are frequently confused:

**Spring Data Auditing** records metadata about creation and the most recent update on the current record. Common annotations:

- @CreatedBy: creator of the entity.
- @CreatedDate: creation timestamp.
- @LastModifiedBy: last modifier.
- @LastModifiedDate: last modification timestamp.

Example entity holding only current information:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;
}
~~~

After multiple updates, createdAt remains the creation time and lastModifiedAt is the most recent update time. This mechanism does not retain earlier values of name.

**Hibernate Envers** stores historical versions of an entity. If name changes from An to Binh and then Chi, Envers can store the states by revision so the application can inspect data at each point in time.

| Criterion | Spring Data Auditing | Hibernate Envers |
|---|---|---|
| Goal | Who created/modified and when | History of data versions |
| Data | Current metadata on the entity table | Historical records in audit tables |
| View old values | Not provided automatically | Queryable by revision |
| Integration | @EnableJpaAuditing and auditing listener | @Audited, Hibernate Envers |
| History querying | Not its primary purpose | AuditReader or RevisionRepository |

The two mechanisms can be used together. For example, an application can keep createdBy/lastModifiedBy on the current entity and use Envers to look up all previous changes.

## 2. Hibernate Envers Is the Foundational Requirement

Envers is a module of Hibernate ORM. It is not an independent feature of every JPA provider. Spring Data Envers relies on Envers to write and read history.

With Maven, add the Spring Data Envers dependency:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-envers</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
implementation("org.springframework.data:spring-data-envers")
~~~

If the project uses Spring Boot or the Spring Data BOM, let dependency management resolve compatible versions. Do not arbitrarily pick mismatched Spring Data Envers and Hibernate Envers versions separately.

Spring Data Envers declares Hibernate Envers as a transitive dependency. Therefore, adding spring-data-envers usually brings hibernate-envers onto the runtime classpath. You can inspect the dependency tree to verify:

~~~bash
mvn dependency:tree
~~~

Or with Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

If the project explicitly excludes transitive dependencies or manages libraries under its own policy, ensure the hibernate-envers artifact is present and its version is compatible with the running hibernate-core. Avoid mixing a Hibernate Envers version from a different release line than Hibernate ORM, as this can cause class or API errors at startup.

Spring Data Envers is always used alongside Spring Data JPA. Adding Spring Data Envers to an application that does not use Hibernate ORM will not provide equivalent revision functionality.

## 3. Configuring Envers Repositories

In a Spring Boot application using auto-configuration, when Spring Data Envers is on the classpath, Spring Boot can configure JPA repositories to support Envers queries. The repository still needs to extend RevisionRepository.

If configuring Spring Data repositories manually, use @EnableEnversRepositories:

~~~java
@Configuration
@EnableEnversRepositories(
    basePackages = "com.example.people.repository"
)
@EnableTransactionManagement
public class PersistenceConfiguration {
}
~~~

The @EnableEnversRepositories annotation provides the appropriate repository factory bean for Envers. With manual configuration, this is the dedicated way to create repositories with revision support.

Do not enable two overlapping repository configurations for the same package unintentionally. In an application already using Spring Boot auto-configuration, inspect the existing configuration first rather than adding manual annotations mechanically.

Core JPA components still need to be functional:

- DataSource connecting to the database.
- EntityManagerFactory managing the persistence unit.
- PlatformTransactionManager managing transactions.
- Entities scanned and properly mapped.
- Hibernate Envers present on the runtime classpath.

In Spring Boot, most of these beans are auto-configured from starters and datasource properties.

## 4. Marking Entities with @Audited

Envers only records history for entities with auditing enabled. The common approach is placing @Audited on the class:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.hibernate.envers.Audited;

@Entity
@Audited
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

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

@Audited is a Hibernate Envers annotation from the org.hibernate.envers package. It is not a Spring Data JPA annotation.

When an entity is persisted, updated, or deleted through Hibernate within a transaction, Envers writes the corresponding revision information. If an entity is not marked for auditing, RevisionRepository cannot generate history for it automatically.

@Audited can be placed at the class level to audit persistent properties by default, or at the property level for selective auditing. With selective configuration, verify the exact annotations and default rules for your Envers version.

## 5. What Is a Revision?

A revision is a historical milestone managed by Envers. In the default configuration, the revision number is an incrementing number shared across audited changes.

Example:

| Revision | Person ID | name | email | Change Type |
|---:|---:|---|---|---|
| 1 | 10 | An | an@example.com | Create |
| 4 | 10 | Binh | an@example.com | Modify |
| 7 | 10 | Binh | binh@example.com | Modify |
| 9 | 10 | — | — | Delete |

Revision numbers for a single entity may be non-contiguous because revisions span more than one entity. Intermediate revisions may be created by changes to other entities.

A single transaction that modifies multiple audited entities can group those changes under the same revision. Envers does not create a separate revision for every save call within the same transaction.

A revision number is neither the entity's ID nor the @Version field used for optimistic locking.

## 6. Audit Table Structure

For a Person entity with a current table PERSON, Envers by default creates an audit table typically suffixed with _AUD, such as PERSON_AUD. The default revision table is typically REVINFO.

Simple model:

~~~text
PERSON
  id
  name
  email

PERSON_AUD
  id
  REV
  REVTYPE
  name
  email

REVINFO
  REV
  REVTSTMP
~~~

Meaning:

- PERSON stores the current state.
- PERSON_AUD stores the historical state of audited properties.
- REV is the revision number linking to the revision table.
- REVTYPE represents the change type.
- REVINFO stores the revision number and timestamp of the revision.

The audit primary key typically combines the entity ID and revision number, since an entity can have many versions across revisions but only one audit row per revision.

In the default configuration, revision types represent additions, modifications, and deletions. Hibernate Envers defines the RevisionType enum with values ADD, MOD, and DEL. Spring Data maps revision info to RevisionMetadata.RevisionType with values INSERT, UPDATE, DELETE, or UNKNOWN.

For deletions, Envers by default may store only the ID, revision, and delete type in the audit row; data properties may be null. If you need to retain full data at deletion time, check Envers' store_data_at_delete configuration and the associated storage cost.

## 7. Revision Number Is Not @Version

Both mechanisms can hold incrementing numbers, yet they solve two different problems.

~~~java
@Entity
@Audited
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    private String owner;

    @Version
    private Long version;
}
~~~

@Version belongs to JPA optimistic locking. It helps detect conflicting updates when multiple transactions modify the same entity concurrently.

An Envers revision number identifies a historical milestone. A single revision can contain changes across multiple entities in the same transaction.

| Property | @Version | Envers Revision |
|---|---|---|
| Scope | One entity instance | Transaction revision with audited changes |
| Purpose | Detect concurrent overwrites | Inspect historical changes |
| Provides old snapshots | No | Yes |
| Used for | Optimistic locking | Audit/history queries |

Both can be used together on the same entity. Do not use revision numbers as a substitute for optimistic locking or vice versa.

## 8. Declaring RevisionRepository

RevisionRepository belongs to Spring Data Commons and is supported by Spring Data Envers once the repository infrastructure is configured.

Repository declaration:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.history.RevisionRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long>,
                RevisionRepository<Person, Long, Integer> {
}
~~~

The three generic parameters mean:

1. Person: the entity whose history is read.
2. Long: the entity's ID type.
3. Integer: the revision number type.

With default Envers configuration, the revision number type is typically Integer or Long. N must be a comparable numeric type per the RevisionRepository contract.

RevisionRepository does not replace JpaRepository. In the example, JpaRepository still provides CRUD; RevisionRepository adds the history-reading API.

The Person entity must be annotated with @Audited. Otherwise, history methods have no corresponding audit records to return.

## 9. Core Methods of RevisionRepository

RevisionRepository provides the following operations:

| Method | Return Value | Purpose |
|---|---|---|
| findLastChangeRevision(id) | Optional<Revision<N,T>> | Latest revision of the entity |
| findRevision(id, revisionNumber) | Optional<Revision<N,T>> | Entity at a specific revision |
| findRevisions(id) | Revisions<N,T> | All revisions of the entity |
| findRevisions(id, pageable) | Page<Revision<N,T>> | Paginated history |

These methods require a non-null ID. For findRevision, the revision number must also be non-null.

When no matching history exists, Optional-returning methods can return Optional.empty(); Revisions can be an empty collection. Always handle cases where an entity has no revisions yet or the ID does not exist.

## 10. Reading Full History with findRevisions

Example service reading a Person's history:

~~~java
@Service
public class PersonHistoryService {

    private final PersonRepository repository;

    public PersonHistoryService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<PersonRevisionView> history(Long personId) {
        Revisions<Integer, Person> revisions =
            repository.findRevisions(personId);

        return revisions.getContent().stream()
            .map(revision -> {
                RevisionMetadata<Integer> metadata =
                    revision.getMetadata();

                return new PersonRevisionView(
                    metadata.getRevisionNumber().orElseThrow(),
                    metadata.getRevisionInstant().orElseThrow(),
                    metadata.getRevisionType().name(),
                    revision.getEntity().getName(),
                    revision.getEntity().getEmail()
                );
            })
            .toList();
    }
}
~~~

Returned DTO:

~~~java
public record PersonRevisionView(
    Integer revisionNumber,
    Instant changedAt,
    String changeType,
    String name,
    String email
) {
}
~~~

The example calls getContent() to obtain the list of revisions. Each Revision contains an entity snapshot and metadata. Metadata provides the revision number, timestamp, and change type.

If the project uses Java older than 16, replace toList() with Collectors.toList(). The Person, PersonRepository, and DTO classes should reside in appropriate packages with proper imports.

## 11. Reading the Latest Revision

Use findLastChangeRevision:

~~~java
Optional<Revision<Integer, Person>> latest =
    personRepository.findLastChangeRevision(personId);

if (latest.isPresent()) {
    Revision<Integer, Person> revision = latest.get();

    Integer number = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();

    Person snapshot = revision.getEntity();

    RevisionMetadata.RevisionType type =
        revision.getMetadata().getRevisionType();
}
~~~

This method returns the revision where the entity was most recently changed. The latest revision may be a DELETE revision if the entity was deleted.

Therefore, before rendering the snapshot as an active entity, check the revision type. A deleted record by default may not retain all audited properties.

Do not use findLastChangeRevision to look up the current entity instead of findById. The two methods serve different goals: one reads history, the other reads the current table.

## 12. Finding State at a Specific Revision

Use findRevision:

~~~java
Optional<Revision<Integer, Person>> result =
    personRepository.findRevision(personId, revisionNumber);

if (result.isPresent()) {
    Revision<Integer, Person> revision = result.get();
    Person historicalState = revision.getEntity();

    Integer actualRevision = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();
}
~~~

This method returns a Revision wrapper, not Person directly. The wrapper holds metadata and the entity snapshot at the requested revision.

If the revision number does not exist for that entity, the result can be empty. A revision number may exist in REVINFO due to changes to another entity without meaning Person has a snapshot at that revision.

When you need an entity's state at a historical milestone, use this API rather than loading the current entity and trying to manually revert fields.

## 13. Paginating History with Pageable

An entity can be modified thousands of times. You should not always load the entire history into memory.

RevisionRepository supports pagination:

~~~java
Page<Revision<Integer, Person>> page =
    personRepository.findRevisions(
        personId,
        PageRequest.of(0, 20, RevisionSort.desc())
    );
~~~

RevisionSort is a specialized Sort for ordering by revision number without depending on the revision entity's property name. RevisionSort.desc() places newer revisions first; RevisionSort.asc() places older revisions first.

You can iterate over it:

~~~java
for (Revision<Integer, Person> revision : page.getContent()) {
    Integer number = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();

    Person snapshot = revision.getEntity();
}
~~~

API documentation notes that implementations are not required to support sorting by arbitrary properties when paginating revisions. Use RevisionSort when sorting by revision number and verify other sorting capabilities on your specific version.

## 14. Revision and RevisionMetadata

Spring Data represents a version as Revision<N,T>. A Revision contains:

- Entity snapshot.
- RevisionMetadata.
- Revision number.
- Revision timestamp if available.
- Revision type.

RevisionMetadata exposes these APIs:

~~~java
RevisionMetadata<Integer> metadata = revision.getMetadata();

Optional<Integer> number = metadata.getRevisionNumber();

Optional<Instant> instant = metadata.getRevisionInstant();

RevisionMetadata.RevisionType type = metadata.getRevisionType();
~~~

RevisionMetadata.RevisionType has the values:

- INSERT: entity was created.
- UPDATE: entity was modified.
- DELETE: entity was deleted.
- UNKNOWN: change type could not be determined.

Do not confuse this Spring Data enum with Hibernate's org.hibernate.envers.RevisionType. The two enums belong to different APIs and use different constant names.

RevisionMetadata's getDelegate() can provide the underlying native revision metadata object used by the store/provider. When using a custom revision entity and needing extra fields such as actor or requestId, you can access the delegate cast to your configured revision entity type. Encapsulate this conversion inside a service/mapper rather than letting controllers depend directly on Hibernate metadata.

## 15. Querying History Directly with AuditReader

RevisionRepository fits common lookups by entity ID. When complex history queries are needed, Hibernate Envers provides AuditReader.

~~~java
AuditReader reader =
    AuditReaderFactory.get(entityManager);

Person historicalPerson =
    reader.find(Person.class, personId, revisionNumber);
~~~

AuditReaderFactory obtains an AuditReader from the current EntityManager. find returns the entity's state at the requested revision number.

AuditReader also supports criteria-based revision queries. For example, you can query Person revisions, filter by ID, and sort by revision number using the Envers AuditQuery API:

~~~java
List<Object[]> changes = reader.createQuery()
    .forRevisionsOfEntity(Person.class, false, true)
    .add(AuditEntity.id().eq(personId))
    .addOrder(AuditEntity.revisionNumber().asc())
    .getResultList();
~~~

When selectEntitiesOnly is false, each result is typically an Object[] containing the entity snapshot, revision entity, and revision type. Cast according to your actual entity and revision mappings.

Use AuditReader when you need advanced querying features that RevisionRepository does not expose directly. Keep Hibernate-specific query logic at the service/repository boundary to avoid leaking Envers APIs throughout the application.

## 16. Customizing Audit Table Names

By default, Envers typically appends the _AUD suffix to the entity table name. You can change the audit table name per entity with @AuditTable:

~~~java
@Entity
@Audited
@AuditTable(value = "PERSON_HISTORY")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
~~~

Or configure prefix/suffix globally via Hibernate properties. Spring Boot example:

~~~properties
spring.jpa.properties.org.hibernate.envers.audit_table_suffix=_HISTORY
~~~

If renaming tables, database migrations must create the exact names and structures Envers expects.

In production environments, do not rely on Hibernate's automatic schema generation in place of migration management. Use Flyway, Liquibase, or your project's schema migration process to create audit tables, the revision table, keys, and corresponding indexes.

## 17. Excluding Specific Properties with @NotAudited

Some fields do not need history recorded, such as cached values or temporary data. Use @NotAudited:

~~~java
@Entity
@Audited
public class UserProfile {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @NotAudited
    private String temporaryAccessToken;
}
~~~

The temporaryAccessToken field is not written to the audit table. Other fields continue to be audited per mapping.

Do not exclude a field from auditing simply because it is sensitive without reviewing compliance requirements. Define your data policy: whether history should be stored, whether encryption or masking is needed, and whether limited retention applies.

Conversely, do not audit all data unconditionally. Audit tables can hold many copies of sensitive data and substantially increase database storage.

## 18. Relationships to Non-Audited Entities

If an audited entity references another entity not annotated with @Audited, Envers needs to know how to handle that association.

One case is wanting only to store a reference to the target entity's current state:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@Audited(targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
private Department department;
~~~

With RelationTargetAuditMode.NOT_AUDITED, the source entity's history can reference the non-audited target entity in its current state.

This means that when viewing history, Department may reflect current data rather than a historical snapshot of Department at the old revision. Do not use this approach if the requirement is to reconstruct the entire relationship graph as it existed at that historical point in time.

If history for both sides of the relationship is required, mark the target entity as audited and configure the relationship using mappings supported by Envers.

## 19. Tracking Per-Property Modifications

Envers can store flags indicating which properties changed in a revision. Example:

~~~java
@Entity
@Audited(withModifiedFlag = true)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;
}
~~~

With modified flags, the audit table can include extra columns indicating whether the corresponding field changed in that revision. Default column names are usually generated from the property name and a configured suffix.

This information is useful when an audit screen needs to show "email changed" without comparing full before/after snapshots.

In return, the schema and audit data grow larger. Check modified-flag configuration and database migrations before enabling it on entities with many fields.

The Envers AuditQuery API supports querying by modified properties, such as AuditEntity.property("email").hasChanged(). This is a Hibernate Envers feature, not a built-in method on RevisionRepository.

## 20. Custom Revision Entity to Store the Modifier

The default revision stores the revision number and timestamp. An application may also need actor, tenant, request ID, or operation source.

Create a revision entity:

~~~java
@Entity
@Table(name = "REVINFO")
@RevisionEntity(CurrentUserRevisionListener.class)
public class AuditRevisionEntity {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    @Column(length = 120)
    private String actor;

    @Column(length = 80)
    private String requestId;

    public int getId() {
        return id;
    }

    public long getTimestamp() {
        return timestamp;
    }

    public String getActor() {
        return actor;
    }

    public void setActor(String actor) {
        this.actor = actor;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }
}
~~~

Two key annotations:

- @RevisionNumber marks the revision key.
- @RevisionTimestamp marks the revision timestamp.

@RevisionEntity links the revision entity with a RevisionListener to populate metadata when Envers creates a revision.

Example listener using Spring Security:

~~~java
public class CurrentUserRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevisionEntity revision =
            (AuditRevisionEntity) revisionEntity;

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            revision.setActor("system");
        } else {
            revision.setActor(authentication.getName());
        }
    }
}
~~~

This example requires Spring Security and its imports. If the application does not use Spring Security, replace it with the system's appropriate identity source.

RevisionListener is invoked when Envers creates a revision, not once per entity within the revision. Keep the listener simple; avoid database queries or network calls inside the callback. For async tasks, schedulers, or message consumers, propagate identity via an appropriate context; the HTTP request's SecurityContext is not automatically present on every thread.

## 21. Revision Metadata and Transaction Boundaries

Envers writes history in the same transaction as entity changes. When the transaction rolls back, the audit records in that transaction also roll back.

A single transaction may modify multiple audited entities, and all of them reference the same revision. Therefore:

- Two saves in the same transaction do not necessarily create two revisions.
- Two separately committed transactions can create two revisions.
- A read-only transaction does not create a new revision.
- A transaction that does not alter audited data will not create a revision merely because save was called.
- A revision number is a historical milestone, not a log for every line of code or every repository call.

Example:

~~~java
@Transactional
public void renamePerson(Long id) {
    Person person = repository.findById(id)
        .orElseThrow();

    person.setName("Binh");
    repository.save(person);

    person.setEmail("binh@example.com");
    repository.save(person);
}
~~~

Both save calls execute inside the same transaction. Envers typically records one revision for that transaction reflecting the final changed state of the entity, rather than creating two separate revisions for the two save calls.

If business rules require two distinct audit milestones, use two independent transactions with clearly designed boundaries. Do not split transactions solely to increment revision numbers if doing so breaks business atomicity.

## 22. Bulk Update/Delete and Direct SQL

Envers relies on Hibernate events/lifecycles when entities are managed and modified through the ORM.

Bulk JPQL operations or native SQL updating multiple rows directly usually bypass entity lifecycle events:

~~~java
@Modifying
@Query("""
    update Person p
    set p.name = :name
    where p.id = :id
    """)
int updateName(
    @Param("id") Long id,
    @Param("name") String name
);
~~~

A bulk update like the one above does not automatically generate Envers history per entity the way loading an entity, mutating fields, and flushing via Hibernate does.

Similarly, SQL executed directly via JDBC, external scripts, or other systems updating tables does not automatically trigger Envers.

If business rules strictly require auditing bulk changes, design a separate strategy:

- Load and update entities through the ORM if the volume is manageable.
- Emit a dedicated audit event for the bulk operation.
- Use database-level auditing/CDC when all changes must be tracked regardless of source.
- Document clearly which scope is tracked by Envers and which scope is handled by another mechanism.

Do not claim Envers is a complete record of every database change if the application still has write paths outside Hibernate.

## 23. Deleting Entities and Historical Data

When an entity is deleted through Hibernate, Envers writes a revision of type DELETE. The current table no longer holds the entity, while the audit table can still retain the historical marker.

You can query deletion revisions with RevisionRepository and check RevisionMetadata.RevisionType.DELETE.

With default settings, a deletion revision's snapshot may contain only the identifier instead of all fields. If you need to store the final field values before deletion, consider Envers' store_data_at_delete setting and inspect the audit schema.

Do not delete audit rows just because the current entity has been deleted. Retaining history is usually the primary purpose of Envers. If data must be purged due to retention or privacy policies, establish a proper audit deletion workflow and evaluate legal/business impact.

## 24. Envers Is Not Event Sourcing

Envers records entity state by revision for historical queries. It does not automatically turn changes into business-meaningful domain events.

For example, Envers can show that Account balance changed from 100 to 80. However, it does not explain by itself whether that action was an invoice payment, a refund, or a manual adjustment.

| Envers | Event Sourcing |
|---|---|
| Stores entity snapshots/versions | Stores business events |
| Focuses on data state history | Focuses on the sequence of events producing state |
| Can query entity at a revision | Replays events to rebuild state |
| Does not inherently explain business intent | Events typically carry business names and payload data |
| Suits ORM history auditing | Suits systems treating events as the primary source of truth |

If the requirement is to see who edited which field and what the before/after values were, Envers can fit well. If you need to know the exact business action that occurred and replay an event stream, design domain events/event sourcing separately.

## 25. Performance and Audit Storage Footprint

Every revision generates additional data writes. Entities with many fields or frequent updates can produce large audit tables.

Consider:

- How many entities are annotated with @Audited.
- How many fields are audited.
- Update frequency.
- Frequently changing collections/associations.
- Modified flags.
- Indexes on ID and revision number.
- Whether history queries are paginated or load everything.
- Retention and backup policies.

Audit tables typically need indexes supporting queries by entity ID and revision. The default schema includes a composite key, yet actual workloads may require additional indexes.

Do not add indexes arbitrarily. Use execution plans and measure common history queries.

RevisionRepository.findRevisions(id) can return the entire history. For frequently updated entities, prefer findRevisions(id, pageable).

## 26. Security and Sensitive Data

Audit tables are long-lived data. When a sensitive field is audited, its previous values can remain in the audit table even after the current value has been changed or deleted.

Action items:

- Identify which fields need auditing.
- Use @NotAudited for fields that do not require history.
- Do not audit plaintext passwords, access tokens, or secrets.
- Restrict read permissions for audit history.
- Record actor and request context if traceability is required.
- Protect backups and replicas containing audit data.
- Define retention, masking, or deletion processes per data policies.
- Do not expose entire revision entities directly in APIs if they contain internal metadata.

Audit history is often more sensitive than current data because it contains many historical versions.

## 27. Testing Envers and Revision Commits

A test should verify that at least two transactions created two revisions. Note that @DataJpaTest normally runs tests in a transaction and rolls back at the end. Saving and updating in the same transaction will not prove two independent revisions.

Example using TestTransaction to commit between stages:

~~~java
@DataJpaTest
class PersonRevisionRepositoryTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void storesSeparateRevisionsForSeparateTransactions() {
        Person person = repository.saveAndFlush(
            new Person("An", "an@example.com")
        );

        Long id = person.getId();

        TestTransaction.flagForCommit();
        TestTransaction.end();

        TestTransaction.start();

        Person current = repository.findById(id).orElseThrow();
        current.setName("Binh");
        repository.saveAndFlush(current);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        TestTransaction.start();

        Revisions<Integer, Person> revisions =
            repository.findRevisions(id);

        assertEquals(2, revisions.getContent().size());

        Person latest = repository.findLastChangeRevision(id)
            .orElseThrow()
            .getEntity();

        assertEquals("Binh", latest.getName());
    }
}
~~~

The example requires importing TestTransaction, DataJpaTest, and assertions from the test framework in use. The test assumes the repository is configured for Envers, the Person entity has constructors and setters as in earlier examples, and the audit schema has been created.

The first transaction creates Person and commits. The second transaction renames it and commits. The third transaction reads revision history. The final test transaction can roll back when the test finishes.

Other important tests:

1. Persisting an audited entity creates an INSERT revision.
2. Updating an entity creates an UPDATE revision.
3. Deleting an entity creates a DELETE revision.
4. Rollback leaves no committed audit rows.
5. Two entities modified in the same transaction share the same revision number.
6. @NotAudited produces no historical data for excluded fields.
7. Relationships to non-audited entities behave according to the chosen targetAuditMode.
8. RevisionRepository paginates and sorts properly.
9. Custom RevisionListener stores the expected actor.
10. Bulk updates are not mistakenly assumed to be audited by Envers.

## 28. Common Pitfalls and Troubleshooting

**1. Repository lacks history methods or startup throws factory error**

Check that spring-data-envers is on the classpath, the repository extends RevisionRepository, and the repository infrastructure uses the Envers factory. With Spring Boot, check auto-configuration; with manual setup, use @EnableEnversRepositories.

**2. Entity has no revisions**

Check that the entity has @Audited, changes are actually flushed/committed, and operations go through Hibernate ORM.

**3. Hibernate Envers classes not found**

Check the dependency tree and ensure hibernate-envers is present with a version compatible with hibernate-core.

**4. Wrong revision number generic type**

Check the third type parameter of RevisionRepository. With default Envers, this is typically Integer or Long.

**5. History does not grow after multiple saves**

Check whether the saves ran inside the same transaction. One transaction may create only one revision for audited changes.

**6. Bulk update creates no audit rows**

Bulk JPQL/native SQL bypasses entity lifecycle events. Use ORM updates or a dedicated auditing mechanism.

**7. Relationship to non-audited entity causes mapping error**

Mark the target entity @Audited if relationship history is needed, or configure RelationTargetAuditMode.NOT_AUDITED if referencing the target's current state is acceptable.

**8. Delete revision lacks fields**

Check store_data_at_delete. By default, DELETE revisions may store only the ID and metadata.

**9. Tests show no revisions**

Check whether the test transaction rolled back and whether changes were committed. Use TestTransaction or design separate test transactions.

**10. Audit tables are not created in production**

Check schema migrations. Do not assume Hibernate creates audit tables automatically when production uses ddl-auto=validate or none.

**11. Audit table grows too fast**

Review @Audited scope, @NotAudited fields, write frequency, modified flags, retention, and indexes.

**12. Confusing Envers with @Version or Spring Data Auditing**

@Version handles optimistic locking; Spring Data Auditing records creation/modification metadata; Envers stores entity history. Pick the mechanism matching the requirement.

## 29. Spring Data Envers Implementation Workflow

1. Confirm the application uses Spring Data JPA and Hibernate ORM.
2. Add spring-data-envers with a BOM-managed version.
3. Verify hibernate-envers is included on the runtime classpath.
4. Annotate entities requiring history with @Audited.
5. Identify fields/associations to exclude from auditing.
6. Configure @EnableEnversRepositories if not relying on suitable auto-configuration.
7. Extend RevisionRepository alongside JpaRepository.
8. Choose an appropriate Integer or Long revision number type.
9. Create audit table and revision table schemas via migrations.
10. Determine additional metadata such as actor or request ID if needed.
11. Keep transaction boundaries aligned with business semantics.
12. Decide whether bulk/native SQL requires a separate auditing mechanism.
13. Create a service reading history via RevisionRepository.
14. Use AuditReader when advanced Envers queries are needed.
15. Paginate history and restrict access permissions.
16. Test INSERT, UPDATE, DELETE, rollback, relationships, and custom revision metadata.
17. Monitor storage growth, query plans, and retention policies.

## 30. Self-Assessment Checklist

- [ ] I can distinguish Spring Data Auditing from Hibernate Envers.
- [ ] I understand Envers is a module of Hibernate ORM.
- [ ] I know how to add the spring-data-envers dependency.
- [ ] I know hibernate-envers is brought into runtime and must be compatible with Hibernate ORM.
- [ ] I know when to use @EnableEnversRepositories.
- [ ] I know how to annotate entities with org.hibernate.envers.Audited.
- [ ] I understand audit table and revision table structures.
- [ ] I can distinguish revision numbers from entity IDs and @Version.
- [ ] I know how to declare RevisionRepository<T, ID, N>.
- [ ] I know how to use findLastChangeRevision, findRevision, and findRevisions.
- [ ] I know how to paginate history with Pageable and RevisionSort.
- [ ] I know how to read RevisionMetadata and RevisionType.
- [ ] I know how to use AuditReader for advanced queries.
- [ ] I know how to configure @AuditTable and @NotAudited.
- [ ] I understand targetAuditMode for relationships to non-audited entities.
- [ ] I know how to create a custom revision entity and RevisionListener.
- [ ] I understand a single transaction can group multiple changes into one revision.
- [ ] I know bulk JPQL/native SQL is not automatically audited by Envers.
- [ ] I know how to test commit/rollback and revision history.
- [ ] I have a security, retention, and storage policy for auditing.

## 31. Review Questions

**1. Is Spring Data Envers an audit engine?**

No. Hibernate Envers is the engine recording history; Spring Data Envers integrates revision queries into Spring Data JPA repositories.

**2. Why is the hibernate-envers dependency needed?**

Because Spring Data Envers relies on Hibernate Envers to create audit records and query history. The spring-data-envers dependency usually brings hibernate-envers onto the runtime classpath transitively.

**3. What does @Audited do?**

It marks an entity or property to be tracked and stored in history by Hibernate Envers.

**4. Does RevisionRepository replace JpaRepository?**

No. RevisionRepository provides the history API; if CRUD is needed, a repository typically extends both JpaRepository and RevisionRepository.

**5. What do the three generic parameters of RevisionRepository mean?**

Entity type, ID type, and revision number type.

**6. Does findRevision return the entity directly?**

No. It returns Optional<Revision<N,T>>, where Revision contains the entity snapshot and metadata.

**7. How many revisions does a single transaction modifying three audited entities create?**

Typically one revision for that transaction, shared by all audited changes within the transaction.

**8. Does @Version replace revision numbers?**

No. @Version supports optimistic locking for a single entity; a revision number identifies an Envers historical milestone.

**9. Why do bulk updates not create Envers history?**

Bulk JPQL/native SQL updates data directly and bypasses the entity lifecycle events Envers uses to record audits.

**10. When should you use AuditReader instead of RevisionRepository?**

When you need advanced history queries across multiple criteria, revision dates, changed properties, or Hibernate Envers-specific capabilities not exposed directly by the repository API.

**11. Does a DELETE revision preserve all fields by default?**

Not necessarily. By default it may retain only the ID and metadata; the store_data_at_delete setting controls whether data is stored at deletion time.

**12. Why is TestTransaction needed in some Envers tests?**

@DataJpaTest usually rolls back test transactions. To verify revisions across independent transactions, you need to commit earlier transactions and then read history in another transaction.

Spring Data Envers lets applications query entity history via a repository API, while revision-recording capabilities come from Hibernate Envers. When dependencies, @Audited, repository factories, and transaction boundaries are configured properly, applications can inspect entity states by revision, track change types, and extend metadata to store the actor. Clearly define audit scope, data write paths, and security policies before treating audit history as a complete traceability source.

## References

- [Spring Data JPA — Spring Data Envers Introduction](https://docs.spring.io/spring-data/jpa/reference/envers/introduction.html)
- [Spring Data JPA — Envers Configuration](https://docs.spring.io/spring-data/jpa/reference/envers/configuration.html)
- [Spring Data Commons — RevisionRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/history/RevisionRepository.html)
- [Spring Data Commons — RevisionMetadata API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/history/RevisionMetadata.html)
- [Spring Data Commons — RevisionSort API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/history/RevisionSort.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [Hibernate ORM — Envers documentation](https://hibernate.org/orm/envers/)