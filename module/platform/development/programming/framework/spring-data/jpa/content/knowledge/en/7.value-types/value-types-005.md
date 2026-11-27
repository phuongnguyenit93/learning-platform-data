# Configuring Collection Tables with @CollectionTable

## 1. Problem: Storing a Collection of Values Belonging to an Entity

An entity typically has simple attributes like a name, status, or creation date. In business domains, however, an entity can also own multiple values of the same kind: a list of phone numbers, product labels, employee skills, delivery addresses, or custom attribute pairs.

If each value has no independent identifier and lifecycle, creating a separate entity for every value can add unnecessary complexity to the model. Jakarta Persistence provides @ElementCollection to map collections of basic types or embeddable types. Collection elements are stored in a separate table called a collection table. The @CollectionTable annotation specifies that table and how it links back to the owning entity.

For example, a Customer has multiple tags. The customer table stores customer details; the customer_tag table stores the tags and a foreign key pointing back to customer. Each tag is a value belonging to Customer, not an independent entity.

This lesson explains:
- When to use @ElementCollection and @CollectionTable.
- How to configure table names, join columns, and constraints.
- How to map collections of basics, enums, embeddables, and maps.
- How to manage ordering, querying, data loading, and testing.
- When to switch to @OneToMany instead of a collection table.

## 2. Distinguishing Entity Collections from Element Collections

Before configuring the table, determine whether elements are entities or merely values.

### 2.1. Element collection

Use @ElementCollection when elements:
- Have no separate JPA identifier.
- Are not queried or managed as independent entities.
- Have a lifecycle tied to the owning entity.
- Are basic types or embeddable types.

Examples:
- A Customer has a set of String tags.
- A User has a set of enum roles.
- A Product has multiple key/value attribute pairs.
- A Person has a list of ContactAddress objects annotated with @Embeddable.

Elements are stored in a collection table. Each row typically contains the foreign key to the owning entity and columns representing the element value.

### 2.2. One-to-many

Use @OneToMany when elements are entities with their own identity and lifecycle. For example, Order has OrderLines; each line item may have an ID, status, relationships, or be referenced by other business processes.

Do not choose @ElementCollection merely to avoid declaring an entity. If an element needs to be loaded, updated, authorized, or referenced independently, consider a separate entity.

| Criterion | @ElementCollection | @OneToMany |
|---|---|---|
| Element type | Basic or embeddable | Entity |
| Separate identifier | No entity identity | Has its own @Id |
| Lifecycle | Tied to owning entity | Can be independent depending on model |
| Separate repository | No | Can have one |
| Storage table | Collection table | Child entity table |
| Entity relationship | Not an entity relationship | Has an entity relationship |
| Typical use cases | Tags, roles, value objects, secondary attributes | OrderLine, InvoiceItem, Comment |

A value object can contain multiple fields and still be an embeddable. Having multiple fields does not automatically turn it into an entity; the deciding factor is business identity and lifecycle.

## 3. Roles of @ElementCollection and @CollectionTable

These two annotations typically go together:

- @ElementCollection declares the attribute as a collection of basic or embeddable values.
- @CollectionTable describes the table storing the collection and the columns joining that table to the owning entity.

Minimal example:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tag",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag", nullable = false, length = 80)
    private Set<String> tags = new LinkedHashSet<>();

    protected Customer() {
    }

    public Customer(Set<String> tags) {
        this.tags.addAll(tags);
    }

    public Long getId() {
        return id;
    }

    public Set<String> getTags() {
        return Collections.unmodifiableSet(tags);
    }

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Tag is required");
        }
        tags.add(tag);
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }
}
```

In the example:
- Customer is the entity owning the collection.
- tags is an element collection of type Set<String>.
- customer_tag is the collection table.
- customer_id is the join column pointing to customer's primary key.
- tag is the column holding the String value.

@CollectionTable does not declare the element type by itself. The collection type and value storage are determined by @ElementCollection together with @Column or the embeddable mapping.

If @CollectionTable is omitted, the provider can apply default naming rules per the specification. In real applications, explicitly declaring the table name and join column usually makes schemas more readable, stable, and easier to manage with migrations.

## 4. Configuring @CollectionTable Attributes

### 4.1. name

name specifies the collection table name:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

The table name should reflect both the owning entity and the collection's meaning. For example, customer_tag is clearer than a generic name like values.

### 4.2. joinColumns

joinColumns declares the foreign key column or columns linking the collection table to the owning entity's table.

```java
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(
        name = "customer_id",
        referencedColumnName = "id"
    )
)
```

Where:
- name is the column name in the collection table.
- referencedColumnName is the column name in the referenced table; if omitted, the provider defaults to referencing the corresponding primary key of the owning entity.
- nullable, foreignKey, and other @JoinColumn attributes can control DDL details when the provider generates schemas.

If the owning entity uses a composite primary key, declare join columns corresponding to the key components. The count and order of columns must match the referenced key.

### 4.3. schema and catalog

You can specify schema or catalog when the collection table resides in a specific database namespace:

```java
@CollectionTable(
    name = "customer_tag",
    schema = "app_data",
    joinColumns = @JoinColumn(name = "customer_id")
)
```

Schema naming should remain consistent with database configuration and migrations. Do not let annotations, the connection's default schema, and migration scripts use different names.

### 4.4. uniqueConstraints and indexes

@CollectionTable supports declaring uniqueConstraints and indexes. For example, if the same customer cannot have two identical tags, the database can enforce uniqueness on the customer_id and tag pair:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id"),
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tag",
        columnNames = {"customer_id", "tag"}
    ),
    indexes = @Index(
        name = "idx_customer_tag_tag",
        columnList = "tag"
    )
)
@Column(name = "tag", nullable = false, length = 80)
private Set<String> tags = new LinkedHashSet<>();
```

Unique constraints help protect data directly at the database level, even with multiple application instances or writes bypassing the Java collection. Indexes should be chosen based on actual queries, not created merely because a column exists.

These declarations participate in the provider's schema generation process. If schemas are managed with Flyway or Liquibase, declare constraints and indexes in migrations to maintain a clear change history. Do not assume annotations automatically modify the production database when Hibernate is using ddl-auto=validate or none.

### 4.5. foreignKey

The foreignKey attribute allows configuring the foreign key constraint when the provider generates schemas. You can specify a constraint name or control DDL generation. In migration-managed systems, defining foreign keys in migrations is usually clearer and can be reviewed alongside other schema changes.

## 5. Collections of Basic Types

### 5.1. Set<String>

Set is suitable when values must not repeat and insertion order does not need to be persisted:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag", nullable = false, length = 80)
private Set<String> tags = new LinkedHashSet<>();
```

LinkedHashSet preserves iteration order in Java memory, but that does not automatically mean the database saves and restores the order. If order is data that must be preserved, configure a separate ordering mechanism.

Set prevents duplicates in the running Java collection. If uniqueness is a data invariant, add a unique constraint in the database to guard against concurrent writes or data written from other sources.

### 5.2. List and element ordering

If element order must be preserved, use @OrderColumn:

```java
@ElementCollection
@CollectionTable(
    name = "customer_phone",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderColumn(name = "position")
@Column(name = "phone_number", nullable = false)
private List<String> phoneNumbers = new ArrayList<>();
```

The provider stores each element's position in the position column. When read back, the collection is reconstructed in the saved order. Inserting or deleting in the middle of the list may require updating many positions; consider the cost if the list is large and changes frequently.

Distinction:
- @OrderColumn stores positional order in the database.
- @OrderBy sorts results on read based on a supported attribute or sorting expression; it does not store collection insertion order.

If no ordering mechanism is configured, do not assume the row order returned by the database is stable.

### 5.3. Collection of enums

Enums can be stored in a collection table:

```java
public enum UserRole {
    ADMIN,
    EDITOR,
    VIEWER
}
```

```java
@ElementCollection
@CollectionTable(
    name = "user_role",
    joinColumns = @JoinColumn(name = "user_id")
)
@Column(name = "role", nullable = false, length = 30)
@Enumerated(EnumType.STRING)
private Set<UserRole> roles = new HashSet<>();
```

Using EnumType.STRING is usually more readable and durable than ordinal. If storing ordinals, changing the enum declaration order can cause old data to be interpreted as different values. When renaming an enum stored as a string, perform a corresponding data migration.

## 6. Collections of Embeddable Types

When each element consists of multiple attributes, you can create a value object with @Embeddable:

```java
@Embeddable
public class AddressValue {

    @Column(name = "street_name", nullable = false, length = 150)
    private String street;

    @Column(name = "city_name", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected AddressValue() {
    }

    public AddressValue(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
```

Owning entity:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_address",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    private List<AddressValue> addresses = new ArrayList<>();

    protected Customer() {
    }

    public void addAddress(AddressValue address) {
        addresses.add(Objects.requireNonNull(address));
    }
}
```

Because AddressValue is an embeddable, it has no @Id of its own. The street_name, city_name, and postal_code columns are placed in customer_address alongside the customer_id foreign key.

### 6.1. Using AttributeOverride to rename columns

An embeddable can be reused across multiple places. If you want column names in the collection table to differ from the default names, use @AttributeOverrides:

```java
@ElementCollection
@CollectionTable(
    name = "customer_address",
    joinColumns = @JoinColumn(name = "customer_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "delivery_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "delivery_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "delivery_postal_code")
    )
})
private List<AddressValue> deliveryAddresses = new ArrayList<>();
```

name in @AttributeOverride is the Java attribute name of the embeddable, not the database column name. column.name is the column name to use in the collection table.

If collections contain multiple embeddables with similar structures, overrides help distinguish column semantics by context without creating new value object classes just to rename columns.

## 7. Mapping a Map

Map is useful when each element has a specific key, such as custom product attributes.

```java
@ElementCollection
@CollectionTable(
    name = "product_attribute",
    joinColumns = @JoinColumn(name = "product_id"),
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_attribute_key",
        columnNames = {"product_id", "attribute_key"}
    )
)
@MapKeyColumn(name = "attribute_key", length = 80)
@Column(name = "attribute_value", length = 500)
private Map<String, String> attributes = new HashMap<>();
```

Here:
- product_id links the collection row to Product.
- attribute_key stores the Map key.
- attribute_value stores the Map value.
- The unique constraint ensures a product does not have two rows with the same key.

For a Map with enum keys, @MapKeyEnumerated can be used. With entity keys, mappings have different rules and you must evaluate whether the model is still an element collection or has become an entity relationship.

When querying a Map in JPQL, functions such as KEY, VALUE, and ENTRY can be used depending on the goal. Example:

```java
@Query("""
    select p
    from Product p
    join p.attributes a
    where key(a) = :attributeKey
      and value(a) = :attributeValue
    """)
List<Product> findByAttribute(
    @Param("attributeKey") String attributeKey,
    @Param("attributeValue") String attributeValue
);
```

JPQL references Java attributes and entity names, not SQL table names or column names directly. If database-specific SQL queries are needed, native queries can be used while accepting dependency on the specific schema.

## 8. What Does the Collection Table Schema Look Like?

For Customer with a set of tags, an illustrative schema:

```sql
create table customer (
    id bigint generated by default as identity primary key,
    name varchar(150) not null
);

create table customer_tag (
    customer_id bigint not null,
    tag varchar(80) not null,
    constraint fk_customer_tag_customer
        foreign key (customer_id) references customer(id),
    constraint uk_customer_tag
        unique (customer_id, tag)
);
```

Example data:

| customer_id | tag |
|---:|---|
| 10 | vip |
| 10 | newsletter |
| 12 | wholesale |

Customer with id 10 owns two tags. Customer id 12 owns one tag. The collection table does not need a separate Java entity to represent each row.

Column names, data types, and constraints in DDL must match the mapping. The type of customer_id must be compatible with the primary key customer.id. If the owner's primary key is a UUID or composite key, the DDL and join columns must match accordingly.

For collection tables, foreign keys are very important. Without constraints, orphan rows pointing to nonexistent owners can appear when writes occur outside JPA. Appropriate unique constraints also help protect collection invariants.

## 9. Lifecycle, Updates, and Deleting Elements

An element collection belongs to its owning entity. Applications typically modify it through the collection on the entity:

```java
customer.addTag("vip");
customer.removeTag("newsletter");
```

When the owner is managed in a transaction, Hibernate tracks collection changes and synchronizes them on flush. The exact SQL mechanism depends on the mapping and provider; some modifications can result in deleting/inserting collection rows rather than a simple update statement.

Points to remember:
- There is no separate repository for String, enum, or embeddable elements.
- There is no separate @Id on each element of an element collection.
- Do not use orphanRemoval as with @OneToMany; element lifecycle is tied to the owner's collection.
- When the owner is deleted, the provider must handle collection table rows according to the mapping and constraints. Appropriate foreign keys and database policies can be used to protect integrity.
- If an element needs to be edited independently, audited independently, or referenced from other entities, consider converting it to an entity.

Avoid updating the collection table directly with JDBC while a persistence context still holds the old collection without synchronizing. If bulk SQL runs, consider flushing and clearing/refreshing to avoid in-memory state diverging from the database.

## 10. Fetching, Querying, and Performance

### 10.1. FetchType.LAZY

Element collections default to fetch type LAZY per the specification. The provider can defer loading the collection until the application accesses it.

Example:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Reading customer does not necessarily load all tags. However, if tags are accessed after the persistence context closes, Hibernate can throw LazyInitializationException.

### 10.2. Querying entities by collection elements

JPQL can join the collection:

```java
@Query("""
    select distinct c
    from Customer c
    join c.tags tag
    where tag = :tag
    """)
List<Customer> findCustomersWithTag(@Param("tag") String tag);
```

distinct prevents returning duplicate entities when the join produces multiple result rows for the same owner. For large collections, consider indexing the tag column or key pair suited to the query.

### 10.3. Avoiding N+1

If you load a list of Customers and sequentially access each person's tags, the provider may issue a separate query for each collection. This is an N+1 pattern.

Ways to handle it:
- Load the collection with an explicit fetch plan via EntityGraph or fetch join when appropriate.
- Use DTO projections for views that only need specific data.
- Use Hibernate batch fetching when the access pattern fits.
- Measure actual SQL and round trips instead of guessing.

Fetch joining a collection alongside pagination must be examined carefully because the join can multiply row counts. You can paginate the owner list first and then load collections for that set of IDs in a second query.

## 11. When Should ElementCollection Be Replaced by an Entity?

Element collections fit small values tightly bound to the owner's lifecycle. Switch to an entity when:
- Elements need their own IDs.
- Elements have their own state or business workflow.
- Elements are referenced by other entities.
- Per-element auditing, authorization, or change history is needed.
- Elements need to be queried and paginated as an independent dataset.
- Many relationships or complex metadata are attached to elements.

For example, OrderLine is usually an entity because a line item has quantity, unit price, discount, status, and can be processed individually. Conversely, a Customer's set of tags is usually an element collection because each tag is just a value attached to Customer.

Do not use ElementCollection for large datasets, independently changing records, or complex batch operations without weighing collection tracking costs and provider-generated SQL.

## 12. Testing @CollectionTable Mappings

A JPA test can verify that a collection is saved and reloaded:

```java
@DataJpaTest
class CustomerCollectionTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository repository;

    @Test
    void persistsAndLoadsTags() {
        Customer customer = new Customer(Set.of("vip", "newsletter"));
        entityManager.persist(customer);
        entityManager.flush();
        Long id = customer.getId();

        entityManager.clear();

        Customer loaded = repository.findById(id).orElseThrow();

        assertThat(loaded.getTags())
            .containsExactlyInAnyOrder("vip", "newsletter");
    }
}
```

The example assumes Customer has the constructor and getter shown earlier. flush() forces the provider to synchronize changes to the database; clear() removes the managed entity from the persistence context so the subsequent query does not merely return the instance already in memory. The test verifies data can be read back from the database.

Add tests according to domain requirements:
- Adding and removing an element.
- Two owners having independent collections.
- Unique constraint preventing duplicate keys/values if that is a rule.
- List preserving order when using @OrderColumn.
- Embeddables saved under the right column names after AttributeOverride.
- Maps restoring keys and values properly.
- Deleting the owner handles collection table rows properly.
- JPQL queries joining collections return correct owners without duplicates.

For production schemas, run integration tests against the same database type using Testcontainers to verify data types, constraints, and real SQL.

## 13. Checklist Before Finalizing the Mapping

- [ ] Elements are truly basic or embeddable values, needing no entity identity.
- [ ] Collection is annotated with @ElementCollection.
- [ ] @CollectionTable has an explicit table name and joinColumns.
- [ ] Join columns reference the correct owner primary key.
- [ ] Column names and data types match the schema/migrations.
- [ ] Unique constraints are declared if the domain requires uniqueness.
- [ ] Indexes are chosen based on real queries.
- [ ] Lists have @OrderColumn if positional ordering must be stored.
- [ ] Maps have @MapKeyColumn or an appropriate key mapping.
- [ ] Embeddables use AttributeOverride when column names need to change.
- [ ] Fetch plan is appropriate and collections are accessed within transactions.
- [ ] Avoid JDBC bulk updates leaving managed collections stale.
- [ ] Integration tests verify persist, reload, update, and delete.
- [ ] Use a separate entity if elements have an independent lifecycle or identifier.

## 14. Conclusion

@CollectionTable specifies the table storing a collection of basic or embeddable values declared with @ElementCollection. joinColumns links rows in this table to the owning entity; annotations such as @Column, @AttributeOverride, @MapKeyColumn, @OrderColumn, uniqueConstraints, and indexes describe the specific data structure.

Use element collections for values whose lifecycle is tied to the owner, and use entity relationships when elements need independent identification, querying, or management. Designing the collection table along with foreign keys, uniqueness, ordering, and indexes from the beginning keeps mappings clear, queries stable, and schemas maintainable.
