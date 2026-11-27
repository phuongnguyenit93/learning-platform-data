# Mutable Entities, Immutable Entities, and Java Records

Spring Data R2DBC can map several styles of Java entities. An entity can be **mutable** (state can change after creation), **immutable** (unchangeable after creation), or a **Java record** (a data class with final components and an auto-generated constructor).

Spring Data does not require entities to have a no-arg constructor and setters for every property. When reading data, the framework uses metadata to pick a constructor and construct the object; then, if needed, it populates any remaining properties. When writing data, Spring Data returns an entity reflecting the saved state. This is especially important with immutable entities because a newly generated ID or version can be placed on a new instance rather than mutating the original instance.

## 1. Entities in Spring Data R2DBC

An entity is a Java type representing data persisted in a relational database. Entity mapping is typically described using Spring Data Relational annotations:

- @Table specifies the table.
- @Id marks the identifier property.
- @Column specifies the column name.
- @Version marks the version property for optimistic locking.
- @Transient excludes a property from persistent mapping.
- @Embedded and @MappedCollection describe certain value object or aggregate collection structures.

Simple example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Annotations only describe the mapping. Spring Data R2DBC also needs to know how to instantiate a Customer when reading a Row and how to access or update properties when saving.

An entity is usually designed around an aggregate root. Objects belonging to the same aggregate can be saved according to Spring Data's relational mapping rules. Whether choosing mutable or immutable, the aggregate model and table/column rules still need to be clear.

## 2. Mutable Entities: Objects Whose State Can Change

A mutable entity allows modifying properties after initialization, typically via setters or business methods. This is the familiar JavaBean style.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Version
    private Long version;

    protected Customer() {
        // For framework entity instantiation.
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }
}
~~~

When reading a row, Spring Data can instantiate the object and populate property values through the appropriate access mechanism. If an entity has a no-arg constructor and setters, the framework can generally use this pattern.

### 2.1. Advantages of Mutable Entities

- Easy to adopt for JavaBean developers.
- Can construct the object first and populate data step by step.
- Easy to integrate with libraries or frameworks that require setters.
- Can mutate entity state across a multi-step business workflow.
- Can be convenient when updating individual properties in memory.

### 2.2. Limitations to Keep in Mind

- An object can exist in an incomplete state between setter calls.
- Multiple places can modify the same instance, making it hard to trace where changes originate.
- Public setters can allow modifying properties that the business logic expects to remain invariant.
- Sharing a mutable entity across multiple threads or reactive branches can introduce concurrent-access bugs.

R2DBC uses a reactive model, but that does not make Java objects automatically safe when mutated concurrently across threads. Never mistake non-blocking I/O for entity thread-safety.

If you choose mutable entities, restrict setters to the necessary scope, keep mutations inside controlled services/aggregates, and avoid sharing an instance being mutated across concurrent operations.

## 3. Immutable Entities: State Fixed at Creation

An immutable entity does not permit modifying state after creation. Properties are typically final with no public setters; business changes are expressed by returning a new instance.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public final class Customer {

    @Id
    private final Long id;

    private final String fullName;

    @Version
    private final Long version;

    @PersistenceCreator
    public Customer(Long id, String fullName, Long version) {
        this.id = id;
        this.fullName = fullName;
        this.version = version;
    }

    public static Customer newCustomer(String fullName) {
        return new Customer(null, fullName, null);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Long getVersion() {
        return version;
    }

    public Customer withId(Long id) {
        return new Customer(id, this.fullName, this.version);
    }

    public Customer withVersion(Long version) {
        return new Customer(this.id, this.fullName, version);
    }

    public Customer rename(String newFullName) {
        return new Customer(this.id, newFullName, this.version);
    }
}
~~~

In this example, properties are final and there are no setters. The rename method creates a new Customer with the new name. The withId and withVersion methods also return new instances when the framework needs to apply an identifier or version value.

Spring Data can use the selected constructor to instantiate the entity. When multiple constructors exist, @PersistenceCreator designates which constructor to use for persistence. When there is a single matching constructor, the framework can usually pick it automatically.

### 3.1. Advantages of Immutable Entities

- State cannot change silently after the object is created.
- Easier to reason about when reading code because an instance has fixed data.
- Reduces the risk of one place mutating a property while another place reads the same instance.
- Fits value objects and immutability-first domain models.
- Convenient for testing because inputs and outputs can be compared cleanly.

### 3.2. Trade-off: Updates Create New Instances

With mutable entities, a setter mutates the object in place. With immutable entities, update methods must create a new object:

~~~java
Customer renamed = customer.rename("Tran An");
~~~

This approach allocates additional instances, yet usually makes state transitions more transparent. In most business applications, creating a small object is not a strong enough reason to give up immutability; however, measure if dealing with very high object volumes or heavy data structures.

## 4. Java Records: A More Concise Immutable Entity

A Java record is a data-carrier class declaration. The compiler automatically generates a canonical constructor, component accessors, equals, hashCode, and toString. Components are final and records have no setters.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    @Version Long version
) {}
~~~

This record can be used directly by Spring Data R2DBC as an entity. Spring Data uses the record's constructor to instantiate the object when reading data. No boilerplate getters, setters, or constructors are needed just to assign the three components.

When creating a new instance:

~~~java
Customer customer = new Customer(null, "Nguyen An", null);
~~~

The null values here indicate an unassigned ID and version in the example. Version initialization rules and ID generation also depend on configuration, ID type, and the database.

### 4.1. Records Do Not Automatically Make Everything Deeply Immutable

A record prevents reassigning component references after construction, but it does not automatically make referenced objects immutable.

Example:

~~~java
import java.util.List;

public record OrderDraft(List<String> items) {}
~~~

If the caller retains a reference to the List and mutates it, the contents seen by OrderDraft also change. To protect collection data, copy it or use an immutable collection:

~~~java
import java.util.List;

public record OrderDraft(List<String> items) {

    public OrderDraft {
        items = List.copyOf(items);
    }
}
~~~

This provides deep immutability at the copied collection level; elements inside still need consideration if they are themselves mutable.

### 4.2. When Records Are a Good Fit

Records fit well when:

- The entity has a relatively stable data structure.
- All properties are known at creation time.
- No setters are needed to mutate state.
- Constructor binding naturally reflects the data model.
- The project runs on a Java version supporting records (Java 16 or newer for standardized records).

Records do not fit well when a domain object needs a complex multi-step construction process, must extend a base class, or must work with a library that requires no-arg constructors and setters. In those cases, an immutable class or mutable JavaBean may fit better.

## 5. How Does Spring Data Instantiate Entities?

When a query returns a Row, Spring Data R2DBC converts the data into an entity instance. This process has two main phases:

1. **Object creation**: choose a constructor and instantiate the object from values matching constructor parameters.
2. **Property population**: populate any persistent properties not provided through the constructor, using property-access mechanisms supported by Spring Data.

~~~mermaid
flowchart TB
    A["Row and metadata"]
    B["RelationalMappingContext"]
    C["Select persistence constructor"]
    D["Read and convert parameters"]
    E["Create entity instance"]
    F["Populate remaining properties"]
    G["Complete entity"]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
~~~

### 5.1. Selecting a Constructor

Common rules:

- If the entity has a single suitable constructor, Spring Data can use it.
- If multiple constructors exist, the constructor annotated with @PersistenceCreator is preferred per mapping rules.
- For records, the canonical constructor is the natural constructor for instantiating the record.
- Constructor parameters must correspond to persistent properties and have discoverable names/types for data mapping.

Example immutable class with multiple constructors:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public class Product {

    @Id
    private final Long id;

    private final String name;

    private final String sku;

    public Product(String name, String sku) {
        this(null, name, sku);
    }

    @PersistenceCreator
    public Product(Long id, String name, String sku) {
        this.id = id;
        this.name = name;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getSku() {
        return sku;
    }
}
~~~

The constructor annotated with @PersistenceCreator tells Spring Data how to construct the entity from persistence data. The simpler constructor can still be used in business code to create new products.

With regular classes, ensure constructor parameter name metadata can be discovered and matched to properties. Compiler settings that retain parameter names (such as the Java compiler `-parameters` flag where needed) help the mapping resolve parameters accurately. Do not arbitrarily rename constructor parameters when they are relied upon for property mapping.

### 5.2. Property Population After Construction

After the constructor runs, Spring Data may need to populate properties not set via the constructor. For mutable entities, the framework can use setters or suitable property access.

For immutable entities, two mechanisms stand out:

- **Wither**: a method returning a new instance with one property changed, typically named following the `withProperty` convention.
- **Persistence constructor**: if no suitable wither exists, Spring Data can re-create the instance via the constructor with the new property value.

Wither example:

~~~java
public Customer withId(Long newId) {
    return new Customer(newId, this.fullName, this.version);
}
~~~

A wither does not mutate the current object. It returns another Customer. This lets the framework attach database-generated values while keeping the entity immutable.

If the constructor already receives all persistent properties, the framework may not need an additional property-population step.

### 5.3. Property Names and Column Names Are Distinct Concepts

Constructor parameter names typically map to Java property names, whereas SQL columns can be renamed via @Column or a NamingStrategy.

Example:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

The Java property is `fullName`; the database column name is `full_name`. The constructor component remains `fullName`. Do not rename the component to `full_name` just because the database uses snake_case column names.

## 6. Generated IDs and Immutable Entities

An important case is when the database generates the ID on insert.

For a new entity, the application typically creates an object without an ID:

~~~java
Customer customer = new Customer(null, "Nguyen An", null);
~~~

After insert, the database can return the generated ID. Spring Data must construct or update the returned entity state to hold that ID.

With immutable classes or records, the original instance cannot be mutated. Therefore, always use the **entity emitted by the save result**:

~~~java
Mono<Customer> savedCustomer =
    customerRepository.save(
        new Customer(null, "Nguyen An", null)
    );

return savedCustomer.flatMap(saved ->
    customerRepository.findById(saved.id())
);
~~~

Never discard the return value of `save` and keep using the original instance assuming the ID was written into it. For immutable entities, the original instance retains its initial state; the newly returned instance reflects the post-save state.

This is another reason to return publishers from repositories through services/controllers rather than calling `subscribe` arbitrarily in the business layer.

### 6.1. Mutable Entities Should Also Use the Return Value

Some mapping mechanisms can populate IDs on mutable entities, yet the safest and clearest practice is still to use the entity emitted by `save`. The repository API returns the saved entity so callers can proceed with the state Spring Data returned.

### 6.2. Application-Assigned IDs

If the ID is generated upfront by the application, the entity can carry an ID at creation time:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record CustomerWithUuid(
    @Id UUID id,
    String fullName,
    @Version Long version
) {}

CustomerWithUuid customer =
    new CustomerWithUuid(UUID.randomUUID(), "Nguyen An", null);
~~~

The ID type and new-entity detection must align with Spring Data mapping and configuration. With a non-null ID, repositories typically need to distinguish an update from an existing entity via new-state detection rules. If your project uses application-assigned IDs, understand new-entity detection—you may need `Persistable` or an appropriate strategy rather than assuming any non-null ID means the record already exists.

## 7. Versions and Optimistic Locking with Immutable Entities

Spring Data Relational supports optimistic locking via @Version. Versions detect when a record has been modified by another transaction since the entity was read.

Example:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    String fullName,
    @Version Long version
) {}
~~~

On update, Spring Data uses the current version in the update condition and updates to the new version per the framework mechanism. If no rows are updated because the version no longer matches, the operation can raise `OptimisticLockingFailureException`.

With records, the new version is also part of the returned instance. Therefore, after save/update, continue using the returned entity:

~~~java
Mono<Customer> updated =
    customerRepository.findById(customerId)
        .map(customer ->
            new Customer(
                customer.id(),
                "Tran An",
                customer.version()
            )
        )
        .flatMap(customerRepository::save);
~~~

The example above illustrates constructing a new record before saving. In a real application, place domain-changing operations in a clear method and handle missing records or optimistic locking failures.

Do not manually increment the version in the service if Spring Data is managing @Version. Let the persistence mechanism control version comparison and increments.

## 8. Comparing Mutable Classes, Immutable Classes, and Records

| Criterion | Mutable Class | Immutable Class | Java Record |
|---|---|---|---|
| State after creation | Can change | Unchanging; creates new instance | Components cannot be reassigned |
| Properties | Typically fields and setters | Typically final, no setters | Final components |
| Constructor | Can use no-arg or business constructors | Constructor taking required data | Compiler-generated canonical constructor |
| Spring Data object creation | Instantiates then populates properties or uses constructor | Constructor binding; can use withers/copy via constructor | Canonical constructor |
| Updating properties | Setters or business methods | Creates new instance | Creates new record |
| ID/version generated after insert | May reflect on mutable instance or returned instance | Returned instance holds new values | Returned record holds new values |
| Boilerplate | Many getters/setters | Potentially many constructors and withers | Minimal |
| Best suited when | Step-by-step state mutation is required | Domain favors immutability, controlled construction | Concise data types, natural constructor binding |

No single choice is universally right for every domain. Choose based on how the application manages state, integration requirements, and entity complexity.

## 9. Combining Entities with Repositories and Services

Reactive repositories work with mutable classes, immutable classes, and records alike when mappings are configured properly.

Repository example:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByFullName(String fullName);
}
~~~

A service can create a new entity, save it, and use the returned result:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(String fullName) {
        Customer customer = new Customer(null, fullName, null);
        return repository.save(customer);
    }
}
~~~

In this example, `Customer` can be the record declared earlier. The service does not have to change how it calls the repository just because the entity is a record. The difference lies in how the framework instantiates and updates instances during mapping.

If you need the newly generated ID, extract it from the emitted entity:

~~~java
public Mono<Long> registerAndGetId(String fullName) {
    return repository.save(new Customer(null, fullName, null))
        .map(Customer::id);
}
~~~

Do not call `block()` inside a reactive service just to obtain synchronous results. Let the publisher compose with the upstream pipeline.

## 10. Choosing an Entity Style for Each Scenario

### Use Mutable Entities When

- Domain or integration frameworks require setters.
- The entity genuinely needs a step-by-step initialization workflow.
- The application uses the JavaBean model and wants compatibility.
- Clear rules control where state mutation is allowed.

### Use Immutable Classes When

- You want strict control over constructors and initialization rules.
- The entity carries more business logic than a simple data carrier.
- Clearly named withers or factory methods are needed.
- You want immutability while retaining inheritance or standard class features.

### Use Records When

- The entity has a clear, relatively stable data structure.
- Constructor binding matches entity creation naturally.
- Setters or class inheritance are unnecessary.
- You want to minimize boilerplate for getters, equals, hashCode, and toString.
- The project uses a Java version supporting records.

For all three styles, verify mappings for special properties, constructor parameters, IDs/versions, and collections. Records will not fix schema mismatches on their own, and mutable classes will not resolve driver or conversion issues either.

## 11. Common Mistakes

### 11.1. Failing to Find a Matching Constructor

Possible causes include multiple constructors without a designated one, parameter names not matching properties, or a constructor inaccessible to the mapping mechanism.

How to fix:

- Annotate the persistence constructor with @PersistenceCreator when multiple constructors exist.
- Ensure constructor parameters match persistent properties.
- Verify parameter names are preserved during compilation.
- With records, use meaningful component names and avoid arbitrary renaming.

### 11.2. Records or Immutable Entities Missing IDs After Insert

Usually caused by code continuing to use the original instance instead of the entity emitted by `save`.

How to fix: keep and consume the result publisher from the repository/template. Read the ID from the saved instance.

### 11.3. Using Setters for Final Fields

Final fields cannot be updated like ordinary mutable properties. If an immutable entity needs to receive values generated during persistence, provide an appropriate constructor or convention-based wither.

### 11.4. Constructor Parameters with Mismatched Names

For example, if the property is `fullName` yet the constructor parameter is `name`, Spring Data may fail to resolve which data to pass without corresponding mapping support.

How to fix: keep parameter names matching properties or structure constructors cleanly, and verify constructor metadata.

### 11.5. Using Records with Mutable Collections

Records do not make Lists, Maps, or nested objects immutable. To guard state, copy collections in the constructor and use immutable elements where appropriate.

### 11.6. Expecting Entities to Be Automatically Thread-Safe in Reactive Execution

Reactive only describes how signals and I/O are handled. It does not prevent two processing branches from mutating the same mutable object simultaneously. Avoid sharing mutable entities under modification across concurrent subscribers or requests.

## 12. Practical Design Principles

- Pick a clear entity creation style: mutable JavaBean, immutable constructor binding, or record.
- Use @PersistenceCreator when an entity has multiple constructors and you must designate the persistence constructor.
- Ensure constructor parameters map accurately to properties.
- Use @Table, @Column, @Id, and @Version to describe mapping; do not confuse Java property names with SQL column names.
- For immutable entities, use withers or the persistence constructor to create new instances when updating properties.
- For records, remember component immutability is shallow; protect mutable collections and nested objects yourself.
- Always use the entity emitted by `save`, especially when the database generates IDs or Spring Data updates versions.
- Do not manually increment @Version if Spring Data is managing optimistic locking.
- Avoid sharing mutable entities across concurrent execution paths.
- Keep reactive flows end-to-end across services and controllers; do not block arbitrarily to extract entities.

## 13. Remembering the Mapping Flow

When reading data, Spring Data R2DBC uses entity metadata to select a constructor, convert values from the Row, and create an instance. For mutable entities, the framework can populate remaining properties via setters or property access. For immutable classes, the framework can use withers or create a new instance through the persistence constructor. For records, the canonical constructor is the natural instantiation mechanism.

When writing data, the repository or template executes the operation and emits the resulting entity. If an ID or version is generated or updated during persistence, the newly returned instance is the state source to use going forward. Understanding this distinction helps choose the right entity style and avoid bugs when working with Spring Data R2DBC.
