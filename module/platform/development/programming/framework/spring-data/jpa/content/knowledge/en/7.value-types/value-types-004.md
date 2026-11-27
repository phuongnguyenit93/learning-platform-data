# Collections of Basic Types and Value Objects with @ElementCollection

In JPA, not all data attached to an entity needs to become a separate entity. If an attribute is a collection of simple values or value objects with no independent identifier, it can be mapped using @ElementCollection. This approach fits tags, aliases, phone numbers, saved addresses, labels, configurations, or values belonging exclusively to an owning entity.

This lesson focuses on two kinds of elements: **basic types** (String, enum, numbers, dates/times, and supported or converted types) and **@Embeddable value objects**. The examples use Jakarta Persistence with Spring Boot 3 / Spring Framework 6 or later, so imports use jakarta.persistence.*. Older Spring Boot 2 projects typically use javax.persistence.*; do not mix the two namespaces in the same application.

## 1. What Problem Does @ElementCollection Solve?

Suppose a user profile has multiple tags. A tag is simply a string attached to that profile; it has no ID, is not shared as an independent object, and has no lifecycle of its own. Creating a Tag entity just to store each string adds unnecessary identity, repositories, and relationships to the model.

@ElementCollection allows JPA to store a collection of:

- Basic types supported by JPA, such as String, Integer, BigDecimal, LocalDate, Boolean, or enum.
- Value object types annotated with @Embeddable.

Elements are stored in a separate **collection table**. Each row of this table links to the owning entity's primary key through a foreign key. JPA manages the collection rows alongside the persistence lifecycle of the owning entity.

An element collection has no separate identity. An element is a value belonging to the owning entity, not an independent entity. Therefore, @Id cannot be declared on an element, there is no separate repository for elements, and entity relationships like @OneToMany cannot be used in place of value collection semantics.

Example model:

~~~text
user_profile
------------
id
display_name

user_profile_tags
-----------------
user_profile_id   -> user_profile.id
tag

user_profile_contacts
---------------------
user_profile_id   -> user_profile.id
position
kind
value
~~~

The user_profile_tags table stores tag strings. The user_profile_contacts table stores the fields of a ContactMethod object. Both tables depend on the user_profile row.

## 2. Distinguishing Basic Types, Value Objects, and Entities

These three concepts have distinct boundaries:

| Type | Characteristics | Common mapping |
|---|---|---|
| Basic type | Single value such as String, number, date, enum | @ElementCollection |
| Value object | Groups multiple attributes into one concept, no independent identity | @Embeddable combined with @ElementCollection |
| Entity | Has stable identifier, lifecycle, and can be referenced independently | @Entity with @OneToMany, @ManyToOne, or appropriate relationship |

Examples:

- List of article keywords: Strings, suitable for an element collection.
- List of shipping addresses stored privately in a profile and not referenced independently: can be a collection of @Embeddable Address.
- Items in an order that need an ID, processing status, price at purchase time, and independent querying: usually an OrderLine entity, not an element collection.
- Categories shared by multiple products with their own lifecycle: should be a Category entity and an entity relationship.

The key decision is not the number of fields, but **whether that value has an independent business identity and lifecycle**. An object with many fields can still be a value object; conversely, an object with only two fields may still need to become an entity if managed independently.

## 3. Mapping a Collection of Basic Types

### 3.1. Collection of Strings

For example, a profile storing multiple tags:

~~~java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "user_profile")
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "user_profile_tags",
        joinColumns = @JoinColumn(name = "user_profile_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uk_user_profile_tag",
            columnNames = {"user_profile_id", "tag"}
        )
    )
    @Column(name = "tag", nullable = false, length = 60)
    private Set<String> tags = new LinkedHashSet<>();

    protected UserProfile() {
    }

    public UserProfile(String displayName) {
        this.displayName = displayName;
    }

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Tag must not be blank");
        }
        tags.add(tag.trim());
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }

    public Set<String> getTags() {
        return Set.copyOf(tags);
    }

    public Long getId() {
        return id;
    }
}
~~~

Annotation meanings:

- @ElementCollection marks the property as a collection of values, not a relationship to an entity.
- fetch = FetchType.LAZY tells the provider to defer loading the collection until needed. LAZY is the default for ElementCollection; it is a fetch hint in JPA, so always observe the actual SQL produced by the provider.
- @CollectionTable specifies the table storing the collection and the join columns pointing back to the owning entity.
- joinColumns declares the foreign key user_profile_id referencing the primary key of user_profile.
- @Column describes the column storing each element value.
- Set is appropriate when values do not need ordering and must not repeat in the Java model. LinkedHashSet preserves insertion order in Java memory, but if order needs to persist across database reads, it must be mapped explicitly.
- uniqueConstraints creates a uniqueness constraint on the owner and tag pair in the database. This protects uniqueness when multiple threads or applications write data.

The JPA provider generates SQL schemas according to configuration and dialect. When using migrations such as Flyway or Liquibase, create tables and constraints through migrations rather than relying on automatic schema generation in production.

### 3.2. Collection of Enums

Enums can also be elements of an element collection. Prefer EnumType.STRING to store readable enum names and avoid errors when enum constant order changes:

~~~java
public enum Permission {
    READ,
    WRITE,
    APPROVE
}
~~~

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_permissions",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@Enumerated(EnumType.STRING)
@Column(name = "permission", nullable = false, length = 30)
private Set<Permission> permissions = new HashSet<>();
~~~

EnumType.ORDINAL stores the ordinal number of the enum constant. If constants are added, removed, or reordered, old data can be misinterpreted. Only use ordinal when there is a clear reason and enum ordering is strictly controlled.

### 3.3. Collections of Numbers, Dates, and Other Basic Types

Other supported basic types can be used similarly:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_price_points",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "price", precision = 12, scale = 2, nullable = false)
private List<BigDecimal> historicalPrices = new ArrayList<>();
~~~

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_reminder_dates",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@Column(name = "reminder_date", nullable = false)
private Set<LocalDate> reminderDates = new HashSet<>();
~~~

Choose Java types and column types that match the data semantics. For monetary values, prefer BigDecimal over float/double. For dates/times, choose LocalDate, LocalDateTime, Instant, or OffsetDateTime according to business timezone rules and database capabilities.

If a custom type is not mapped directly by the provider, an appropriate AttributeConverter can be used. A converter must convert consistently between the Java type and the database type; do not store a complex object as a JSON string if the application needs to query individual fields in SQL without a clear strategy.

## 4. Mapping a Map of Basic Types

An element collection can also be a Map. For example, a profile storing key-value settings:

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_settings",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@MapKeyColumn(name = "setting_key", length = 80)
@Column(name = "setting_value", length = 300)
private Map<String, String> settings = new HashMap<>();
~~~

In this example:

- @MapKeyColumn specifies the column storing the Map key.
- @Column on the collection property specifies the column storing the value.
- Each row of the collection table contains the owner ID, setting key, and setting value.
- Keys must be unique within an owner's Map. If database-level protection is needed, add a unique constraint on the user_profile_id and setting_key pair.

A Map is suitable for small dictionary-style data, such as configuration name-value pairs. If keys or values need identity, relationships, complex validation, or independent business queries, consider a separate entity.

## 5. Value Objects with @Embeddable

When an element has multiple attributes, instead of storing each attribute in separate collections, group them into an @Embeddable class. For example, a profile has multiple contact methods:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class ContactMethod {

    @Column(name = "kind", nullable = false, length = 20)
    private String kind;

    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactMethod() {
    }

    public ContactMethod(String kind, String value) {
        if (kind == null || kind.isBlank()) {
            throw new IllegalArgumentException("Kind is required");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Value is required");
        }
        this.kind = kind;
        this.value = value;
    }

    public String getKind() {
        return kind;
    }

    public String getValue() {
        return value;
    }
}
~~~

@Embeddable marks the class as embeddable in an entity or usable as an element in an element collection. The class does not declare @Id because it has no independent identity. A no-argument constructor with protected visibility is a common JPA-compatible pattern; fields are mapped according to the entity/embeddable access strategy.

Mapping the collection:

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderColumn(name = "position")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

The fields of ContactMethod become columns in user_profile_contacts. There is no need to create a separate contact_method table just to store a value object belonging to the profile.

If you want column names different from the field names in the embeddable, use @AttributeOverride or @AttributeOverrides:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_saved_locations",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "label",
        column = @Column(name = "location_label", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "city_name", nullable = false)
    )
})
private List<SavedLocation> savedLocations = new ArrayList<>();
~~~

The name in @AttributeOverride is the Java attribute inside the embeddable. The column name is the column name to use in the collection table. If the embeddable has nested attributes, property paths can be used for overrides according to JPA mapping rules.

## 6. Element Ordering: @OrderColumn and @OrderBy

Collections can be Set, List, or Map, but you must distinguish ordering in Java from ordering stored in the database.

### 6.1. @OrderColumn stores position

If the business logic needs to preserve the exact order arranged by users, use @OrderColumn:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderColumn(name = "position")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

The database stores an additional position column. JPA uses this column to reconstruct the List order when loading the collection. When inserting or removing an element in the middle, the provider may need to update the positions of many subsequent rows.

Use @OrderColumn for business-meaningful ordering such as priority order, display order, or step order. Do not use it merely because the Java field is declared as a List.

### 6.2. @OrderBy sorts by attribute

@OrderBy requests sorting the collection by one or more attributes of the element:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderBy("kind ASC")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

With @OrderBy, order is evaluated by attribute when loading the collection. It does not store a drag-and-drop position index defined by the user.

Comparison:

| Annotation | How it works | When to use |
|---|---|---|
| @OrderColumn | Stores position in an ordering column | Preserve user-arranged ordering |
| @OrderBy | Sorts by attribute value | Always display sorted by name, date, or priority |

Do not place both annotations to solve the same ordering requirement. Choose one suitable model and inspect the SQL generated by the provider.

## 7. Collection Table and Foreign Keys

@CollectionTable maps the collection to a relational table. Common attributes:

- name: collection table name.
- schema and catalog: schema/catalog if needed.
- joinColumns: one or more foreign key columns referencing the owning entity.
- foreignKey: configures the foreign key name and characteristics.
- uniqueConstraints: uniqueness constraints on columns.
- indexes: indexes to support queries.

Example:

~~~java
@ElementCollection
@CollectionTable(
    name = "article_labels",
    joinColumns = @JoinColumn(
        name = "article_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_article_labels_article")
    ),
    indexes = {
        @Index(
            name = "ix_article_labels_article",
            columnList = "article_id"
        ),
        @Index(
            name = "ix_article_labels_label",
            columnList = "label"
        )
    }
)
@Column(name = "label", nullable = false, length = 80)
private Set<String> labels = new HashSet<>();
~~~

Conceptually, the schema looks like:

~~~sql
create table article_labels (
    article_id bigint not null,
    label varchar(80) not null,
    constraint fk_article_labels_article
        foreign key (article_id) references article(id)
);

create index ix_article_labels_article
    on article_labels(article_id);

create index ix_article_labels_label
    on article_labels(label);
~~~

This is illustrative DDL. Actual column types, constraint names, and syntax depend on the database, dialect, and migrations. For data requiring deduplication, add an appropriate unique constraint such as unique(article_id, label). For queries frequently filtering by owner ID and value, choose indexes based on actual workload.

If the owning entity has a composite primary key, joinColumns can consist of multiple JoinColumns corresponding to the key components. Column names and types must match the referenced key.

## 8. Managing Collections Through the Owning Entity in Spring Data JPA

Repositories still belong to the owning entity. Do not create a repository for String, ContactMethod, or value objects inside the collection.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserProfileRepository
        extends JpaRepository<UserProfile, Long> {
}
~~~

A service modifying the collection:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserProfileService {

    private final UserProfileRepository repository;

    public UserProfileService(UserProfileRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void addTag(Long id, String tag) {
        UserProfile profile = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "User profile not found"
            ));

        profile.addTag(tag);
        // profile is managed; dirty checking writes changes on flush/commit.
    }

    @Transactional
    public void addContact(Long id, ContactMethod contact) {
        UserProfile profile = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "User profile not found"
            ));

        profile.addContact(contact);
    }
}
~~~

When the owning entity is managed within a transaction, collection changes are detected by the persistence context and synchronized on flush/commit. Calling repository.save(profile) after every modification to an already managed entity is not necessary. However, save may be used at creation boundaries or when working with detached objects per repository design; understand persist/merge and entity state before calling it.

If the collection is lazily initialized, adding or removing an element may cause the provider to load the current collection state to compute changes. Do not assume an add operation always generates just a single simple INSERT.

## 9. Querying Element Collections

JPQL can join through an owning entity's collection:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    left join fetch p.tags
    where p.id = :id
    """)
Optional<UserProfile> findByIdWithTags(@Param("id") Long id);
~~~

A fetch join loads the collection together with the entity in a single query. From there, the service can map the data to a DTO before the transaction ends.

EntityGraph can also be used:

~~~java
@EntityGraph(attributePaths = "tags")
@Query("select p from UserProfile p where p.id = :id")
Optional<UserProfile> findProfileWithTags(@Param("id") Long id);
~~~

For an embeddable collection, the collection can be fetched similarly:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    left join fetch p.contacts
    where p.id = :id
    """)
Optional<UserProfile> findByIdWithContacts(@Param("id") Long id);
~~~

Collection joins increase the number of result rows: an owning entity with multiple elements appears across multiple SQL rows. Therefore, use distinct to avoid duplicate entities in JPQL results when needed.

### 9.1. Finding owners by a collection value

You can join to find profiles that have a specific tag:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    join p.tags tag
    where tag = :tag
    """)
List<UserProfile> findProfilesWithTag(@Param("tag") String tag);
~~~

Elements can be queried directly via a join in JPQL, yet the element is still not a root entity with an independent identity. Its queries and lifecycle still belong to the owning entity's context.

### 9.2. Collection fetch and pagination

Be careful when combining a collection fetch join with Pageable. An owning entity with many elements produces multiple SQL rows, causing database pagination to no longer correspond simply to entity counts. Some providers may log warnings or perform pagination in memory.

Safer approaches:

1. Paginate the list of IDs or owning entities first.
2. Query the collection for the retrieved set of IDs.
3. Use DTOs/projections if the screen only needs a subset of data.
4. Use provider batch fetching if appropriate.

Do not fetch join multiple large collections simultaneously without understanding result row counts and provider limitations.

## 10. Lifecycle and Element Updates

An element collection belongs to its owning entity:

- When adding an element to a managed collection, JPA synchronizes the corresponding collection row on flush.
- When removing an element, JPA synchronizes removing the value from the collection table.
- When modifying an attribute of a managed embeddable in the collection, the provider must synchronize the collection state according to the mapping.
- When deleting the owning entity via normal entity operations, its collection rows are handled according to the owning relationship and JPA/provider mapping.
- There is no cascade attribute like entity relationships, because elements are not independent entities.
- Do not use orphanRemoval on ElementCollection; the orphan removal concept belongs to entity relationships such as OneToMany/OneToOne.

Exact SQL details for updating collections depend on the provider and how the collection is modified. Providers may perform collection-wide DELETE/INSERT operations or per-element optimizations. If a collection is large, frequently has small partial updates, or requires per-element auditing, a child entity model may be more suitable.

A bulk JPQL update/delete operates directly on the database and bypasses lifecycle/dirty checking of managed entities. After a bulk operation, the persistence context may hold stale state; consider clearing/refreshing and handling collection tables/foreign keys according to the actual schema.

## 11. Validation and Data Integrity

Collection tables should be designed like any other relational table:

- Column lengths appropriate for the data.
- NOT NULL for required values.
- UNIQUE when an owner cannot repeat a value.
- Foreign keys pointing to the owner.
- Indexes for querying by owner or by value.
- String normalization rules if comparisons are case-insensitive.
- Numeric/date types matching the value domain.

Validation in Java provides early, friendly error reporting, but it does not replace database constraints. When multiple application instances or concurrent requests exist, database constraints are the final line of defense protecting integrity.

For embeddable collections, validation annotations can be placed on fields inside the embeddable and cascade validation triggered from the owning entity via Bean Validation. Example:

~~~java
@Embeddable
public class ContactMethod {

    @NotBlank
    @Column(name = "kind", nullable = false, length = 20)
    private String kind;

    @NotBlank
    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactMethod() {
    }
}
~~~

~~~java
@ElementCollection
@Valid
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
private List<ContactMethod> contacts = new ArrayList<>();
~~~

An appropriate Bean Validation dependency is required, such as Spring Boot's validation starter. @Valid triggers validation down into each element. Database constraints still need to be declared in migrations or mappings.

## 12. Performance and Design Limitations

### 12.1. Small and infrequently changing collections

ElementCollection works well when the collection is small, privately owned by a single owner, and usually read alongside that entity. Examples include tag lists, preferred languages, configuration pairs, or small value objects.

### 12.2. Large or frequently queried collections

If an entity has tens of thousands of elements, loading the entire collection can consume significant memory and time. ElementCollection is typically treated as a unit owned by the owner; repository APIs do not provide a separate repository for elements.

If you need searching, pagination, updating, locking, or auditing of individual elements independently, consider turning them into entities.

### 12.3. N+1 queries

If you load a list of owners and then access the lazy collection of each owner, a separate query may be issued per owner. This is a form of N+1.

Ways to handle it:
- Use fetch joins when retrieving a single owner or a suitably small set.
- Use EntityGraph for use cases that need the collection.
- Use projections/DTOs when only specific data is needed.
- Use provider batch fetching if supported and verified.
- Measure actual SQL rather than merely counting repository calls.

### 12.4. Multiple collections and Cartesian multiplication

Fetch joining multiple collections in a single query can multiply result rows. For example, an owner with 5 tags and 4 contacts can produce 20 SQL rows for the same owner. With Hibernate, simultaneously fetching multiple bag collections can also trigger MultipleBagFetchException depending on the mapping. This is provider-specific behavior, not a general JPA rule.

Splitting queries, using DTOs, or using batch fetching is usually easier to control.

### 12.5. Transactions and lazy loading

Accessing a lazy collection after the persistence context closes can trigger LazyInitializationException in Hibernate. Loading necessary data inside a service transaction and returning DTOs is a clear design approach.

Do not enable Open EntityManager in View merely to hide lazy loading errors without understanding queries triggered at the web layer. OSIV can cause queries to run during response serialization and make N+1 issues harder to detect.

## 13. Comparing @ElementCollection with @OneToMany

| Criterion | @ElementCollection | @OneToMany |
|---|---|---|
| Element | Basic or @Embeddable | Entity |
| Separate identity | No | Yes |
| @Id on element | No | Yes on child entity |
| Separate repository | No | Can have one |
| Lifecycle | Tied to owner | Can be managed independently depending on relationship/cascade |
| Cascade | No entity cascade declared | Cascade can be configured |
| orphanRemoval | Not applicable | Applicable in suitable relationships |
| Independent querying | Usually joined from owner | Child entity can be queried directly |
| Suitable model | Values owned exclusively by owner | Child objects with their own identity/behavior/lifecycle |

For example, a simple list of phone numbers that are just values belonging to a profile can use ElementCollection. If each phone number has verification status, verification timestamp, change history, ownership, or is directly referenced by other parts of the system, consider a PhoneNumber entity and @OneToMany.

## 14. Testing with Spring Data JPA

A repository test can verify saving and loading a collection:

~~~java
@DataJpaTest
class UserProfileRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private UserProfileRepository repository;

    @Test
    void persistsBasicAndEmbeddableCollections() {
        UserProfile profile = new UserProfile("Ada");
        profile.addTag("java");
        profile.addContact(new ContactMethod("EMAIL", "ada@example.test"));

        entityManager.persist(profile);
        entityManager.flush();
        entityManager.clear();

        UserProfile loaded = repository.findByIdWithTags(profile.getId())
            .orElseThrow();

        assertThat(loaded.getTags()).contains("java");
    }
}
~~~

This is an illustrative test requiring Spring Boot test imports and dependencies. If you want to verify the embeddable collection, the query must fetch contacts or run inside an open transaction before asserting. Tests should flush and clear to ensure data is genuinely written to and read back from the database, rather than checking an object still in the persistence context.

You should also test:
- Owner with no elements.
- Adding, removing, and updating elements.
- Unique constraint when adding duplicate values.
- Deleting the owner and confirming collection rows are handled.
- Lazy loading and fetch plans for each use case.
- Concurrent updates if the collection has special consistency requirements.
- Migrations on a database close to production, not just H2.

## 15. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Mapping cannot be created | Using @ElementCollection for an entity | Switch to @OneToMany/@ManyToMany or an appropriate entity mapping |
| Unmanaged entity error | Using @Entity instead of @Embeddable for a value object in a collection | Use @Embeddable for elements without identity |
| Wrong table/column names | Relying on default naming that does not match schema | Explicitly declare @CollectionTable, @JoinColumn, and @Column |
| Duplicate key on insert | Inappropriate unique constraint design or duplicate data | Define uniqueness rules, normalize data, and handle constraints |
| List order changes after loading | Not storing order when business logic requires a fixed order | Use @OrderColumn or @OrderBy for the right purpose |
| LazyInitializationException | Reading collection outside persistence context | Fetch inside a transaction and map to a DTO |
| N+1 queries | Accessing lazy collection in a loop | Fetch join, EntityGraph, batch fetch, or projection |
| Slow/incorrect paginated query | Fetch joining collection with Pageable | Paginate owners first, then load collections by ID |
| Collection table grows too large | Using a value collection for data with an independent lifecycle | Convert elements to entities and design dedicated queries |
| Many SQL statements when editing one element | Provider synchronizes collection using its own strategy | Measure SQL; use a child entity if individual rows are updated frequently |

## 16. Selection Rules and Checklist

Choose @ElementCollection when all or most of the following hold:

- Elements are basic types or embeddables.
- Elements do not need their own primary key and identity.
- Elements are not referenced independently by other entities.
- Element lifecycles are tied to the owner.
- The collection has a reasonable size and is usually manipulated with the owner.
- Independent querying, pagination, or updating of individual elements is not a primary requirement.

Choose a child entity when one or more of these needs apply:

- Elements need their own IDs.
- Elements are referenced by multiple entities.
- Elements have their own state, lifecycle, or business behavior.
- Per-element repositories, pagination, locking, or auditing are needed.
- The collection is very large or individual rows are updated frequently.

Checklist before adopting the mapping in an application:

- [ ] Determine whether elements are basic, embeddable, or entities.
- [ ] Clearly identify the owner and collection table.
- [ ] Explicitly declare table name, join column, and column names.
- [ ] Choose Set/List/Map according to business semantics.
- [ ] Use @OrderColumn if user-arranged ordering must be stored.
- [ ] Use @OrderBy if sorting by an attribute is sufficient.
- [ ] Add appropriate unique constraints, foreign keys, and indexes.
- [ ] Verify LAZY loading and fetch plans within transactions.
- [ ] Avoid fetch joining collections during pagination without evaluation.
- [ ] Use DTOs for responses instead of letting the web layer arbitrarily trigger lazy collections.
- [ ] Evaluate collection size and update frequency.
- [ ] Write flush/clear tests to verify data is actually persisted.
- [ ] Use migrations to manage production schemas.

## 17. Conclusion

@ElementCollection is the right choice for mapping collections of values belonging to an owning entity. For basic types, JPA stores values directly in the collection table. For value objects, @Embeddable groups multiple attributes into a meaningful domain element. Both lack separate identity and have lifecycles tied to the owner.

Use @ElementCollection for small, owner-dependent data that does not require independent manipulation. When an element needs its own identity, lifecycle, repository, queries, or updates, model it as an entity and use an entity relationship. Designing this boundary properly keeps mappings simple, queries predictable, and avoids turning a value collection into an unnecessarily complex entity model.
