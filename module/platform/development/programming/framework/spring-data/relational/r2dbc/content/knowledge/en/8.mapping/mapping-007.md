# Mapping Immutable Properties and Updating Entity Copies

Spring Data R2DBC can map data into entities that have no setters and do not allow property modification after initialization. With immutable data types, Spring Data creates objects via an appropriate constructor or factory method, then uses a copying mechanism when assigning values generated during persistence. For business updates, the application constructs a new instance containing the desired state and passes that instance to the Repository.

This approach fits Java records, classes with `final` fields, and Kotlin data classes. It makes entity state predictable, reduces unintended mutations, and clarifies the difference between the current object and its next version. To use it effectively, you need to understand constructor mapping, `@PersistenceCreator`, wither methods, `@Id`, `@Version`, and the value returned by `save`.

## 1. Immutable Objects in the Persistence Model

An *immutable object* is an object whose observable state cannot be changed after creation. Instead of offering setters like `setDisplayName(...)`, it accepts initial values through a constructor and holds them in fields that cannot be reassigned.

Mutable class example:

```java
public class Customer {
    private Long id;
    private String email;
    private String displayName;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Once created, the object above can be modified by any component holding a reference and calling the setter. An immutable entity represents the same data via a constructor:

```java
public record Customer(
        Long id,
        String email,
        String displayName
) {
}
```

A record provides no setters. To get a different display name, the program creates a new `Customer` while retaining the ID and email.

### 1.1. Why Use Immutable Entities?

- **Explicit state:** after initialization, each property's value cannot be silently changed elsewhere.
- **Easier reasoning:** each instance represents a specific state; an update operation produces the next state.
- **Fewer side effects:** multiple components can read the same instance without worrying that another component will mutate its internals.
- **Supports value-oriented design:** states can be compared, passed around, and tested without tracking a sequence of setter calls.
- **Fits constructor mapping:** Spring Data can construct objects directly from values read from a database row.

Immutability does not automatically guarantee valid data. Constructors, factories, or the business layer must still validate required conditions. Furthermore, an object holding a reference to a mutable collection can still be altered indirectly; entity immutability should also consider nested objects.

### 1.2. Java Object Immutability vs. Database Updates

An immutable entity does not mean the database row cannot be updated. The database can still execute `UPDATE`; the application simply represents the before and after states with two distinct objects.

```text
Old Customer                    New Customer
id = 12                         id = 12
email = a@example.com           email = a@example.com
displayName = "An"              displayName = "Anh An"
version = 3                     version = 3 (before save)
       |                               |
       | create copy with new name     |
       +------------------------------>
                                       |
                                       v
                                Repository.save(...)
                                       |
                                       v
                              Database UPDATE
                                       |
                                       v
                                Saved Customer
                                version = 4
```

The old instance is not mutated in place. The result returned by the save operation can be a new instance containing an incremented version or database-generated values.

## 2. How Spring Data Maps Immutable Entities

Spring Data Relational uses entity metadata to read columns from a result row and convert them into Java properties. For mutable entities, the framework can create the object and populate properties through an appropriate access mechanism. For immutable entities, the framework needs to know which constructor or factory method creates the object from the read values.

General process:

1. The R2DBC driver returns the columns of the database row.
2. Spring Data R2DBC reads the entity's mapping metadata, including table name, columns, and property types.
3. Column values are converted to the corresponding Java types.
4. Spring Data selects the persistence constructor or factory method.
5. Values are passed to parameters based on property names and mapping metadata.
6. The entity instance is created and returned via `Mono` or `Flux`.

Table example:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    version BIGINT
);
```

Corresponding immutable entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @Version Long version
) {
}
```

Spring Data maps the `display_name` column to the `displayName` property. The record's constructor parameter name corresponds to the Java property name (`displayName`), while `@Column` specifies the column name in the database. Do not rename the constructor parameter to `display_name` just because the column name uses snake_case.

### 2.1. Constructor Mapping

The constructor used to materialize an entity must receive the values needed to create a valid instance. For a Java record, the canonical constructor is a natural choice because record components clearly define property names and types.

With an ordinary class, constructor mapping can also use a parameterized constructor. Parameter names must correspond to property names. Ensure the build preserves Java parameter-name metadata via the appropriate configuration—typically the `-parameters` compiler option; inspect the build configuration if Spring Data cannot resolve parameter names. Do not use SQL column names in place of Java property names.

Immutable class example:

```java
@Table("customers")
public final class Customer {

    @Id
    private final Long id;

    private final String email;

    @Column("display_name")
    private final String displayName;

    @Version
    private final Long version;

    public Customer(
            Long id,
            String email,
            String displayName,
            Long version) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
        this.version = version;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
    public Long getVersion() { return version; }
}
```

The `final` fields have no setters. The constructor accepts all values and initializes the entity's state once. Getters only expose read access to data.

### 2.2. Selecting a Constructor with @PersistenceCreator

A class may have multiple constructors for compatibility, creating new instances in application code, or serving other frameworks. Spring Data needs to know which constructor to use when reading data from the database. You can annotate the appropriate constructor with `@PersistenceCreator`.

```java
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public final class Customer {

    @Id
    private final Long id;
    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(Long id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Customer(String email, String displayName) {
        this(null, email, displayName);
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
}
```

The constructor taking `id`, `email`, and `displayName` is used to materialize the entity. The other convenience constructor serves creation of new instances from application code. When only one suitable constructor exists, the annotation may not be needed; use it when eliminating ambiguity over which constructor is chosen.

Spring Data also supports persistence factory methods where appropriate. If using a factory, ensure the method is annotated properly and returns the target entity type.

### 2.3. Constructor Parameters and Mapping Rules

Several rules should be followed:

- Constructor parameter names reflect property names in the entity.
- Parameter types are compatible with property types after conversion from the database.
- Parameters must suffice to construct a valid entity state.
- `@Column` maps a Java property to a database column; it does not replace the property name in the constructor.
- When multiple constructors exist, explicitly mark the persistence constructor rather than expecting the framework to guess by declaration order.
- Do not add constructor parameters merely to receive a column that does not belong to the entity; if aggregated data is needed, use a projection or a separate query result type.

If an entity has a field derived from other fields, consider excluding it from the persistence constructor or marking the non-stored property with `@Transient` if appropriate. For aggregated query data, projections usually express intent more clearly.

## 3. Records and Other Immutable Types

### 3.1. Java Records

Java records are a concise choice for entities whose data is primarily described by fixed components. The canonical constructor accepts all record components, getters share the component names, and there are no setters.

```java
@Table("products")
public record Product(
        @Id Long id,
        String sku,
        String name,
        BigDecimal price,
        @Version Long version
) {
}
```

Records eliminate boilerplate getters, constructors, and `equals`/`hashCode`. However, record-generated `equals`/`hashCode` compare all components; consider the domain semantics of entity equality. Records do not automatically provide database primary-key identity semantics.

### 3.2. Classes with Final Fields

Regular classes are useful when you need control over constructors, domain behavior, or compatibility with an existing project structure. You can keep all properties `final`, expose getters, and provide copy methods such as `withDisplayName(...)`.

An advantage is that update rules can be encapsulated inside the entity. For example, a rename method can validate the new name before returning the next instance. Do not add public setters just to satisfy the mapping mechanism when constructor mapping already meets your needs.

### 3.3. Kotlin Data Classes

In Kotlin, a `data class` with `val` properties is a common immutable representation. The Kotlin-generated `copy(...)` method lets you create a copy with selected properties changed while preserving the rest.

```kotlin
@Table("customers")
data class Customer(
    @Id val id: Long? = null,
    val email: String,
    @Column("display_name") val displayName: String,
    @Version val version: Long? = null
)
```

```kotlin
val renamed = customer.copy(displayName = "Anh An")
```

Kotlin support and default constructor handling depend on the versions of Spring Data, Kotlin, and compiler plugins in use. Use compatible versions and test actual materialization, especially with default parameters, nullable properties, or multiple constructors.

## 4. Updating Immutable Entities by Creating Copies

Because the entity has no setters, changing business data is represented by a new instance. You can create `with...` methods or behavior-named domain methods such as `rename(...)`.

### 4.1. Creating Wither Methods

A *wither* is a method that returns a new instance with one property changed while all other properties remain unchanged. The naming convention is typically `with` followed by the property name.

```java
@Table("customers")
public record Customer(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @Version Long version
) {
    public Customer withDisplayName(String newDisplayName) {
        return new Customer(id, email, newDisplayName, version);
    }

    public Customer withEmail(String newEmail) {
        return new Customer(id, newEmail, displayName, version);
    }

    public Customer withId(Long newId) {
        return new Customer(newId, email, displayName, version);
    }

    public Customer withVersion(Long newVersion) {
        return new Customer(id, email, displayName, newVersion);
    }
}
```

`withDisplayName` serves business updates. `withId` and `withVersion` illustrate how to create instances with new metadata values when needed. Spring Data can recognize withers by convention to change immutable properties during mapping steps; if no suitable wither exists, the framework can use the persistence constructor to create a new instance. With records, the canonical constructor is also a natural way to materialize a new state.

Do not write a wither that mutates a current field and returns `this`; that breaks immutability. A wither must instantiate a new object and preserve all properties not requested to change.

### 4.2. Behavior-Expressive Domain Methods

The name `withDisplayName` describes swapping a value. For business operations with rules, a behavioral name like `rename` can express intent more clearly:

```java
public Customer rename(String newDisplayName) {
    if (newDisplayName == null || newDisplayName.isBlank()) {
        throw new IllegalArgumentException("Display name is required");
    }

    return new Customer(id, email, newDisplayName.trim(), version);
}
```

The entity remains immutable because the method returns a new instance. Validation rules stay close to the data they protect. For rules depending on the database or multiple aggregates, the Service remains the proper coordinator; do not put repository queries inside entities.

### 4.3. Copy Constructors or Factory Methods

You do not need a separate wither for every property. You can use a factory or `copy` method accepting the values to be updated. Example:

```java
public Customer withProfile(String newEmail, String newDisplayName) {
    return new Customer(id, newEmail, newDisplayName, version);
}
```

With many properties, a combined copy method can avoid chained wither calls and reduce intermediate object creation. However, the method signature must remain readable and not let callers accidentally overwrite metadata like ID or version.

## 5. Generated IDs and Creating a New Instance

On insert, the database may generate the primary key. An immutable entity cannot receive the new ID by assigning to the current `id` field. Spring Data must construct another instance containing the newly received ID value.

For entities using `@Id`, you can provide a `withId(...)` wither to express creating a copy with the new ID. Spring Data can also use the persistence constructor to materialize a new instance with the generated ID value, depending on entity structure and the chosen mapping mechanism.

Insert operation example:

```java
Customer draft = new Customer(
        null,
        "an@example.com",
        "An Nguyen",
        null
);

return customerRepository.save(draft);
```

Do not assume `draft` will be updated in place. `save` returns a publisher emitting the saved entity; always use the entity emitted by that publisher:

```java
return customerRepository.save(draft)
        .map(saved -> {
            // saved may contain the database-generated ID.
            return saved;
        });
```

If you ignore the return value and keep using `draft`, code may still see `id == null` even though the record was created successfully.

With some application-assigned ID strategies, new-entity detection rules may differ. Spring Data relies on entity information, `@Id`, and `@Version` (if present) to determine new/existing state. Design a consistent ID strategy and do not use fake IDs to force the framework to insert.

## 6. Updating Copies Through a Repository in a Reactive Flow

An update operation typically consists of three steps: reading the current entity, creating a copy with the desired changes, and saving the copy. The steps are chained with Reactor so results and errors flow through the same pipeline.

### 6.1. Repository Example

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);
}
```

`findById` is inherited from `ReactiveCrudRepository`; the result is `Mono<Customer>` because the record may not be found or at most one record matches.

### 6.2. Service Creating a Copy and Saving

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> rename(Long id, String newDisplayName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)))
                .map(customer -> customer.rename(newDisplayName))
                .flatMap(repository::save);
    }
}
```

Meaning of each step:

1. `findById` reads the current state from the database.
2. `switchIfEmpty` turns a missing record into a business exception.
3. `map` calls `rename` and produces a new `Customer`. This step only transforms the object synchronously.
4. `flatMap` calls `save` because `save` returns another `Mono<Customer>`.
5. The final publisher emits the saved entity or an error if the operation fails.

Do not use `map(repository::save)` because that would yield `Mono<Mono<Customer>>`. Use `flatMap` to compose a publisher into the current pipeline.

### 6.3. Preserving Metadata When Creating a Copy

When creating a copy for an update operation, preserve the ID and version of the entity that was read. For example, `rename` keeps `id`, `email`, and `version`, changing only `displayName`. If you accidentally construct a new entity with `id == null`, the Repository may treat it as an insert. If you omit `version` or set the wrong version, a versioned update may be treated as a new state or rejected due to a conflict.

Therefore, create copies from the current entity rather than constructing a new object solely from client-submitted fields. Fields absent from the request must still be preserved.

## 7. Optimistic Locking and the @Version Property

`@Version` enables Spring Data Relational to verify whether an entity is being updated based on the latest version. This mechanism is valuable when concurrent requests may read the same row and then write changes simultaneously.

Entity example:

```java
@Table("customers")
public record Customer(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @Version Long version
) {
    public Customer rename(String value) {
        return new Customer(id, email, value, version);
    }
}
```

Suppose two requests both read a record with `version = 5`:

```text
Request A reads version 5      Request B reads version 5
          |                              |
          v                              v
Create copy A                  Create copy B
          |                              |
          v                              v
Save succeeds: version 6       Save with stale version 5
          |                              |
          v                              v
          +--------------------> Conflict detected
                                  Optimistic locking failure
```

When A updates successfully, the version in the database increments. B still holds the old version, so B's update no longer matches the current version and can fail with an optimistic locking error. The application must decide whether to return a conflict error to the client, re-read data for user resolution, or retry when business rules permit.

### 7.1. Do Not Manually Increment Version in Copy Methods

The `rename` method should keep the version that was read. Spring Data manages version checking and incrementing during the save operation. Do not manually increment version inside `rename` or mappers; doing so can break optimistic locking checks.

### 7.2. Use the Entity Returned After Save

With immutable entities, `save` can return a new instance with the incremented version. Pass the returned instance to subsequent steps:

```java
return repository.save(updated)
        .flatMap(saved -> auditRepository.recordCustomerChange(saved)
                .thenReturn(saved));
```

If the audit step must share a transaction with the update operation, wrap both operations in a reactive transaction. The example above only illustrates using the saved entity; transactions must be configured separately per business requirements.

### 7.3. Handling Conflicts

Not every conflict should be retried automatically. If two users edit the same display name, retrying could overwrite the earlier user's intent. For additive data or safely repeatable operations, retrying after re-reading state may be appropriate. This is a business decision.

APIs can represent conflicts via HTTP `409 Conflict` or use `ETag`/`If-Match` if the contract supports conditional updates. Whichever approach is chosen, never return a fake success response when a save was rejected due to a stale version.

## 8. Considerations When Working with Collections and Nested Objects

A record can hold references to a `List`, `Map`, or other objects. Making the reference property `final` does not automatically make the collection inside immutable.

Example:

```java
public record ShoppingCart(Long id, List<CartLine> lines) {
}
```

Callers can still mutate the original list after passing it to the record. You can create an unmodifiable copy in the constructor:

```java
public record ShoppingCart(Long id, List<CartLine> lines) {
    public ShoppingCart {
        lines = List.copyOf(lines);
    }
}
```

`List.copyOf` produces a collection that cannot be modified through the returned reference. This is shallow immutability: if `CartLine` itself is mutable, its elements can still be altered. When deep immutability is needed, elements should also be immutable types or protected appropriately.

When updating a collection, create a new list and a new entity:

```java
List<CartLine> newLines = new ArrayList<>(cart.lines());
newLines.add(newLine);

ShoppingCart updatedCart = new ShoppingCart(cart.id(), newLines);
```

For aggregates persisted by Spring Data Relational with `@MappedCollection`, define aggregate-owned collections clearly and follow mapping rules. Replacing a collection may cause Spring Data to rewrite dependent elements; understand the emitted SQL and test against the target database. Do not use immutable collections as a substitute for aggregate or transaction design.

## 9. Constructors, Withers, and Callbacks in the Mapping Lifecycle

Spring Data provides extension points in the entity lifecycle such as entity callbacks. With immutable entities, a callback must return the instance to be used going forward instead of mutating the object in place. For example, a before-convert callback can normalize a property and return a new copy.

Do not put all business rules into callbacks. Callbacks are suitable for infrastructure handling or consistent mapping rules, such as normalizing metadata. Behaviors like approving orders, checking limits, or deciding update permissions still belong in Services/domain logic so they can be invoked and tested explicitly.

When custom conversion between database types and Java types is needed, register converters using Spring Data R2DBC's mechanism instead of casting manually in constructors. Constructors should receive values already converted to the entity's property types.

## 10. Testing Immutable Entities and Copy Updates

Tests should cover reading/mapping from the database, inserts with generated IDs, and updates with versions. Unit testing copy methods ensures unrelated properties are preserved; integration tests verify that Spring Data can actually materialize and persist the immutable entity type.

### 10.1. Unit Testing Copy Methods

```java
Customer current = new Customer(
        12L,
        "an@example.com",
        "An",
        5L
);

Customer renamed = current.rename("Anh An");

assertThat(renamed).isNotSameAs(current);
assertThat(renamed.id()).isEqualTo(current.id());
assertThat(renamed.email()).isEqualTo(current.email());
assertThat(renamed.displayName()).isEqualTo("Anh An");
assertThat(renamed.version()).isEqualTo(current.version());
assertThat(current.displayName()).isEqualTo("An");
```

This test verifies that a new instance is created, ID/email/version are retained, and the old instance remains unchanged.

### 10.2. Testing the Reactive Flow

With Reactor Test, you can verify that the Service returns the new entity after saving:

```java
Customer current = new Customer(12L, "an@example.com", "An", 5L);
Customer updated = new Customer(12L, "an@example.com", "Anh An", 6L);

when(repository.findById(12L)).thenReturn(Mono.just(current));
when(repository.save(any(Customer.class))).thenReturn(Mono.just(updated));

StepVerifier.create(service.rename(12L, "Anh An"))
        .expectNext(updated)
        .verifyComplete();

verify(repository).save(argThat(customer ->
        customer.id().equals(12L)
                && customer.displayName().equals("Anh An")
                && customer.version().equals(5L)));
```

The example assumes the Service retains the old version when creating the copy and the Repository returns the saved instance with the new version. In real tests, declare full mocks, matchers, and exceptions per your project's layers.

### 10.3. Integration Testing with R2DBC

Integration tests should verify:

- Immutable entities are read and materialized accurately from database rows.
- `@Column` maps column names that differ from Java properties.
- Insert returns an instance containing the generated ID.
- Update returns an instance containing the new version when using `@Version`.
- Two concurrent updates based on the same version trigger the expected conflict.
- The constructor annotated with `@PersistenceCreator` is chosen when the entity has multiple constructors.
- Collection mapping works properly if the entity uses `@MappedCollection`.

Do not rely solely on mocking the Repository to conclude that constructor mapping works. Materialization, generated IDs, SQL, and optimistic locking must be tested against an appropriate database and driver.

## 11. Common Errors and How to Resolve Them

### Cannot Find a Suitable Constructor

Verify that the constructor accepts all required properties, parameter names match property names, and parameter-name metadata is retained in the build. If multiple constructors exist, mark the persistence constructor with `@PersistenceCreator`.

### Confusing Constructor Parameter Names with Column Names

Java parameter names must match entity properties. `@Column("display_name")` maps the `displayName` property to the `display_name` column; the constructor still accepts a parameter named `displayName`.

### Wither Mutates the Current Object

A wither must instantiate a new instance. If a method mutates a field and returns `this`, the entity is no longer immutable and can cause side effects wherever references are held.

### Ignoring the Return Value of save

With immutable entities, `save` does not update the input object in place. Always continue from the entity emitted by the `save` publisher, especially when needing generated IDs or new versions.

### Creating an Update Copy That Drops ID or Version

If the copy omits the ID, the operation may be detected as an insert. If the version does not reflect the state just read, optimistic locking may misbehave or reject the update. Create copies from the current entity and change only the business properties that need updating.

### Incrementing Version Manually Before save

Let Spring Data manage the version. The copy uses the version that was read to check for conflicts; the framework increments the version when the update succeeds.

### Using `map` to Call a Method Returning a Publisher

`map` creates a nested publisher if the mapping function returns `Mono` or `Flux`. Use `flatMap` to compose publishers into the pipeline.

### Collections Inside an Entity Remain Mutable

A `final List<T>` field only fixes the reference, not the list's contents. Use unmodifiable copies and immutable elements when deeper control is needed.

## 12. Workflow for Applying to an Immutable Entity

When designing a new entity or converting a mutable entity to immutable, follow these steps:

1. Identify tables, columns, primary keys, data types, and constraints in the schema.
2. Create a record or class with a constructor representing the full state to be mapped.
3. Declare `@Table`, `@Id`, `@Column`, and `@Version` where appropriate.
4. If there are multiple constructors, mark the persistence constructor with `@PersistenceCreator`.
5. Ensure constructor parameter names match Java property names and the build preserves required metadata.
6. Create withers or domain methods returning new instances for necessary update operations.
7. Retain ID and version when creating copies for updates.
8. Combine `find`, copy, and `save` with `map`/`flatMap` in the reactive pipeline.
9. Use the entity returned by `save` in subsequent steps.
10. Test constructor mapping, generated IDs, versions, and update conflicts against a real database.

## 13. Review Checklist

- [ ] Immutable entities have no setters that mutate state after initialization.
- [ ] Spring Data can instantiate entities via a persistence constructor or factory method.
- [ ] Java records suit data models with fixed components.
- [ ] `@PersistenceCreator` is used when a constructor/factory for entity materialization needs to be designated explicitly.
- [ ] Constructor parameter names match Java property names; `@Column` only maps database column names.
- [ ] Withers create new instances and preserve unchanged properties.
- [ ] On insert, the entity emitted by `save` is used to obtain the generated ID.
- [ ] On update, the copy retains the ID and version that were read.
- [ ] `@Version` is managed by Spring Data; version is not manually incremented in copy methods.
- [ ] `flatMap` is used when chaining operations returning `Mono`/`Flux`.
- [ ] Nested collections and objects are also evaluated for immutability.
- [ ] Integration tests confirm mapping, generated IDs, and optimistic locking on a compatible database.

Mapping immutable properties via constructors or factory methods enables Spring Data R2DBC to create entities from relational data without setters. When business logic needs to change state, the application intentionally creates a copy and saves it through the Repository. Retaining the proper ID and version and using the return value from `save` keeps the immutable model consistent with the reactive persistence lifecycle.
