# Designing Immutable Entities and Java Records

In **Spring Data Relational JDBC**, an entity is a Java model representing the state of an aggregate stored in a relational database. A common design approach is to use a mutable class with setters so the framework or business code directly modifies individual fields. However, that approach can allow state to be modified in many places, making business rules harder to enforce and making it difficult to understand what state an object is in.

An **immutable entity** restricts direct state modification after an object is created. When business logic needs to transition to a new state, the application creates a new object representing the next state and saves it via the repository. **Java records** provide concise syntax for declaring objects whose data components are fixed after initialization, making them well suited for value objects and certain entity models.

To apply them properly in Spring Data JDBC, you must understand three aspects simultaneously:

- Entity semantics: identity persists across state transitions.
- Record semantics: reference-level data immutability and default equality based on all components.
- Persistence mechanism: Spring Data JDBC instantiates objects from read data, saves aggregates when calling repositories, and can receive IDs/versions managed by the database or framework.

## 1. Mutable Entities and Immutable Entities

A mutable entity typically allows fields to be modified after initialization:

~~~java
public class MutableProduct {
    private Long id;
    private String name;
    private long price;

    public void setName(String name) {
        this.name = name;
    }

    public void setPrice(long price) {
        this.price = price;
    }
}
~~~

This illustrative snippet may be convenient for data binding, yet any code holding a reference to the object with access to setters can modify it. If a rule requires price to be positive, checking inside one setter does not guarantee every update path preserves the invariant if another setter exists or fields are accessed directly.

Immutable entities typically have these characteristics:

- State is established when the object is created.
- Fields are declared `final` or as record components.
- No public setters are exposed.
- Input values are validated in constructors/factories.
- Business behavior produces a new object representing the next state.

~~~java
public record ProductState(String name, long price) {
    public ProductState {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Product name must not be blank");
        }
        if (price < 0) {
            throw new IllegalArgumentException("Price must not be negative");
        }
    }

    public ProductState changePrice(long newPrice) {
        return new ProductState(name, newPrice);
    }
}
~~~

Once `ProductState` is created, `name` or `price` cannot be reassigned. The `changePrice` method returns a new object. The old object still represents the prior state.

### 1.1. Immutability Does Not Mean an Entity Cannot Change in Business Terms

An order can transition from `DRAFT` to `CONFIRMED`. If the entity is implemented as immutable, the two states can be represented by two Java objects:

~~~text
PurchaseOrder(id=42, status=DRAFT)
          |
          | confirm()
          v
PurchaseOrder(id=42, status=CONFIRMED)

The before and after objects are two distinct instances.
Both represent the business entity with identity id=42.
~~~

Here is the distinction to make:

- **Identity** answers "which entity is this?"
- **State** answers "what data does the entity currently hold?"
- **Immutability** governs whether an already-created Java object can have its state modified directly.

An entity can still go through many states over time. Immutability simply ensures each object represents a single well-defined state.

### 1.2. Benefits of Immutable Entities

**Easier to reason about:** after receiving an object, code can trust that its state will not change unexpectedly through another component holding the same reference.

**Invariant control:** constructors/factories and business methods serve as clear points to verify valid data.

**Safe reference sharing:** reduces the risk of one execution thread modifying data while another thread is reading it.

**Easier testing:** you can verify inputs and resulting objects without setting up and repeatedly checking mutations on the same instance.

**State history representation:** old objects can be kept as snapshots within a processing flow, log, or before/after comparison if business logic requires it.

### 1.3. Trade-Offs

Immutability is not free. When changing state, the application must create a new object; if an object contains large collections, copying can cost memory and time. For entities with database-generated IDs/versions, the persistence framework also needs a way to create a new instance carrying values returned by storage.

Therefore, the goal is not to make every object immutable at all costs. Choose a modeling style that keeps invariants clear, mapping straightforward, and costs appropriate.

## 2. What Is a Java Record?

Java records were introduced in Java 14 as a preview and became a standard feature in **Java 16**. A record is a class form designed for data with explicitly declared components. The compiler automatically generates:

- `private final` fields corresponding to the record components.
- A primary constructor (canonical constructor).
- Accessors sharing the component names, e.g., `name()` instead of `getName()`.
- `equals()`, `hashCode()`, and `toString()` based on the components, unless overridden.

Example:

~~~java
public record Money(long minorUnits, String currency) {
}
~~~

Conceptually equivalent to a class with `private final` fields, a constructor, accessors, and basic equality/hash methods. Records reduce boilerplate while making clear that the type's identity is tied to its set of values.

### 2.1. Record Components and Accessors

With the declaration:

~~~java
public record CustomerName(String firstName, String lastName) {
}
~~~

Java generates accessors:

~~~java
CustomerName customer = new CustomerName("An", "Nguyen");

String first = customer.firstName();
String last = customer.lastName();
~~~

Not `getFirstName()` and `getLastName()` like traditional JavaBeans. Modern frameworks, including Spring Data, support constructor/property discovery for records, though when writing Java code directly you must call the accessors with the proper syntax.

### 2.2. Compact Constructors for Checking Invariants

A record can declare a compact constructor:

~~~java
public record Money(long minorUnits, String currency) {
    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Amount must not be negative");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
~~~

A compact constructor does not re-declare the parameter list. Component parameters can be validated or normalized; after the constructor body finishes, Java assigns them to the corresponding fields. This is the right place to guard value object invariants.

Note that checking three letters only validates code shape, not whether that code is a currency supported by the system. Real domain rules may require an allowed currency list or an enum type.

### 2.3. Records Do Not Allow Inheritance

Records are implicitly `final`. They cannot be extended by another class, though they can still implement interfaces:

~~~java
public interface Identified<ID> {
    ID id();
}

public record ProductId(Long value) {
}
~~~

You cannot write `class SpecialProduct extends ProductRecord` if `ProductRecord` is a record. Use composition or interfaces when behavior needs to be extended.

## 3. Shallow Immutability vs. Deep Immutability

Records prevent reassigning components, yet that alone does not make referenced objects immutable.

Example:

~~~java
public record OrderSnapshot(List<String> productCodes) {
}

List<String> codes = new ArrayList<>();
codes.add("BOOK-A");

OrderSnapshot snapshot = new OrderSnapshot(codes);
codes.add("PEN-B");

System.out.println(snapshot.productCodes()); // [BOOK-A, PEN-B]
~~~

The reference field inside the record is `final`, yet the original list can still be mutated. The record object is therefore not deeply immutable.

To protect collections, create an unmodifiable copy:

~~~java
public record OrderSnapshot(List<String> productCodes) {
    public OrderSnapshot {
        productCodes = List.copyOf(productCodes);
    }
}
~~~

`List.copyOf` creates an unmodifiable list that disallows null elements. This is a shallow copy: if an element is a mutable object, the internal state of that element can still change. For deep immutability, elements must also be immutable or copied according to appropriate rules.

Similarly, be careful with arrays, mutable `Date` objects, nested collections, and objects supplied by external libraries. `final` on a reference does not equate to immutability of the entire object graph.

## 4. When Are Java Records Appropriate?

Records are especially well suited for **value objects**:

- `Money`: monetary amount and currency code.
- `EmailAddress`: normalized email address.
- `DateRange`: start date and end date.
- `AddressSnapshot`: shipping address at the time of ordering.
- `SearchCriteria`: search criteria for a request.
- `ProductSummary`: summary data serving a query.

Records can also be used as entities in some models, since Spring Data JDBC supports mapping immutable objects and Java records. However, carefully consider default equality semantics.

| Criterion | Value Object | Entity |
| --- | --- | --- |
| What defines sameness | Property values | Stable identity |
| Two instances with all equal values | Usually considered equivalent | May still be two distinct entities |
| Change | Create a new value | Same identity with new state |
| Default record | Very suitable | Usable, though equality across all components may be unsuitable |

### 4.1. Default Record Equality May Not Fit Entities

Suppose:

~~~java
public record Product(Long id, String name, long price) {
}

Product a = new Product(10L, "Book", 100_000);
Product b = new Product(10L, "Book", 120_000);
~~~

`a.equals(b)` returns `false` because the prices differ. Yet under entity semantics, two objects with the same identity `id=10` may represent two state versions of the same product.

Another case:

~~~java
Product a = new Product(10L, "Book", 100_000);
Product b = new Product(11L, "Book", 100_000);
~~~

Two products have identical descriptive properties but different IDs; they are two distinct entities.

Therefore:

- For value objects, equality across all components is usually desirable.
- For entities, equality is usually based on stable identity per domain rules.
- Records auto-generate equality across all components; if using a record as an entity, verify whether those semantics fit your domain.

You can override `equals()` and `hashCode()` in a record, yet you must honor the equality/hash contract and handle new entities without IDs carefully. A regular class with a clear identity strategy can be easier to understand for complex entities.

### 4.2. Records Are Not DTOs in Every Case

Records are often great for DTOs, yet that does not mean every record is merely a DTO. A record can contain domain behavior, invariant checks, and methods creating new values. Conversely, a class with getters/setters can also be a DTO. Role depends on the type's responsibilities and semantics, not solely on the declaration keyword.

## 5. How Does Spring Data JDBC Support Immutable Objects?

Spring Data JDBC must transfer data between the database and Java objects. For mutable classes, the framework can instantiate the class and populate properties through mapping mechanisms. For immutable objects, the framework must construct the object via an appropriate constructor.

The read flow can be pictured as:

~~~text
SELECT ... FROM product
          |
          v
     ResultSet / Row
          |
          v
 Spring Data JDBC mapping
          |
          v
 constructor / canonical constructor
          |
          v
     Product instance
~~~

For Java records, the canonical constructor provides a natural object creation point. Spring Data can use record components and constructor parameter names to map read values.

The flow for saving a new aggregate can look like:

~~~text
Product(id=null, name="Book", ...)
          |
          v
 repository.save(product)
          |
          v
       INSERT SQL
          |
          v
 database generates ID
          |
          v
 Spring Data creates instance state with ID
          |
          v
      returned Product
~~~

With immutable entities, persistence-generated values such as ID or version cannot be assigned to final fields of the original instance. The framework must create an instance carrying the new values using supported object creation/copy mechanisms. Therefore, application code must use the **object returned by the repository** when the ID or version is needed after saving.

## 6. Mapping a Java Record as an Aggregate Root

Suppose table `product`:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_minor_units BIGINT NOT NULL,
    price_currency VARCHAR(3) NOT NULL
);
~~~

We can model price as a record value object:

~~~java
public record Money(long minorUnits, String currency) {
    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Amount must not be negative");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
~~~

Root record:

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        @Version Long version,
        String sku,
        String name,
        @Embedded(prefix = "price_") Money price
) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Product name must not be blank");
        }
        Objects.requireNonNull(price, "price");
    }

    public static Product create(String sku, String name, Money price) {
        return new Product(null, null, sku, name, price);
    }

    public Product rename(String newName) {
        return new Product(id, version, sku, newName, price);
    }

    public Product changePrice(Money newPrice) {
        return new Product(id, version, sku, name, newPrice);
    }
}
~~~

The example uses `@Embedded(prefix = "price_")` to map the two components of `Money` to columns `price_minor_units` and `price_currency` following Spring Data Relational's snake_case naming rule. If the application uses another naming strategy, column names must be configured accordingly.

Points to note:

- `@Table("product")` specifies the table.
- `@Id` designates the key property.
- `@Version` marks the version used for optimistic locking.
- `@Embedded` maps the value object into the same row.
- `id` and `version` use wrapper types to represent the pre-persistence unpopulated state as `null`.
- The compact constructor validates invariants immediately when creating an instance.
- `rename` and `changePrice` return new instances while keeping the current snapshot's ID/version.

This is an example modeling a record aggregate root; schema identity and mapping details must match your project's database and Spring Data JDBC version. For components whose names collide with SQL keywords or use special types, explicit column name annotations may be required.

### 6.1. Repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, Long> {
}
~~~

Spring Data JDBC provides the repository implementation at runtime based on mapping metadata. The application does not need to write boilerplate implementations for basic CRUD operations.

### 6.2. Creating and Saving a Record

~~~java
Product draft = Product.create(
        "BOOK-021",
        "Spring Data JDBC",
        new Money(185_000, "VND")
);

Product saved = productRepository.save(draft);

System.out.println(draft.id()); // null: original instance was not mutated
System.out.println(saved.id()); // ID returned by persistence layer
~~~

The critical part is keeping the result of `save`:

~~~java
Product saved = productRepository.save(draft);
Long productId = saved.id();
~~~

Do not continue using `draft.id()` assuming it will be updated. With immutable entities, the original instance still represents the state prior to saving.

### 6.3. Reading and Changing State

~~~java
Product current = productRepository.findById(productId)
        .orElseThrow();

Product renamed = current.rename("Spring Data Relational JDBC");
Product savedAgain = productRepository.save(renamed);
~~~

`rename` creates a new record with the same read ID and version. The repository executes the save; the returned result is the instance to use for subsequent operations, especially when version is updated.

Spring Data JDBC does not use a persistence context/dirty checking like JPA. Creating a new object does not automatically emit SQL. The application must call `save` on the repository or execute SQL through an appropriate JDBC API for changes to be persisted.

## 7. Versions and Optimistic Locking with Immutable Entities

When multiple requests concurrently read and update an entity, relying solely on immutable Java objects is not enough to prevent data overwrites. Two requests can both read version 4 and then construct two new objects from the same snapshot.

`@Version` helps detect updates based on an outdated version:

~~~text
Database: Product #10, version=4, price=100

Request A reads version 4       Request B reads version 4
        |                             |
        v                             v
 A creates object price=120    B creates object price=130
        |                             |
        v                             v
 A saves with version 4        B saves with version 4
        |
        v
 A succeeds, version increments
        |
        +-----------------------------+
                                      v
                         B no longer matches current version
                                      |
                                      v
                           Optimistic locking failure
~~~

If a save operation uses a stale version, Spring Data JDBC can throw an optimistic locking failure instead of silently overwriting another request's changes.

When using records:

- Version is a component of the record.
- When creating a new object for a business state change, keep the current version.
- After a successful save, use the returned object to receive the new version.
- When a conflict occurs, reload the latest state and re-evaluate business rules before retrying.

Do not manually increment version inside `rename` or `changePrice`. Version is synchronization metadata owned by the persistence layer; manual increments can corrupt the update condition.

## 8. Designing Immutable Entities with Regular Classes

Java records are concise, yet entities with complex identity, custom equality, or multiple instantiation paths may be better served by regular classes.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public final class PurchaseOrder {

    @Id
    private final Long id;

    @Version
    private final Long version;

    private final String orderNumber;
    private final String status;

    @PersistenceCreator
    public PurchaseOrder(
            Long id,
            Long version,
            String orderNumber,
            String status
    ) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Invalid order number");
        }
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Invalid status");
        }
        this.id = id;
        this.version = version;
        this.orderNumber = orderNumber;
        this.status = status;
    }

    public static PurchaseOrder draft(String orderNumber) {
        return new PurchaseOrder(null, null, orderNumber, "DRAFT");
    }

    public PurchaseOrder confirm() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Can only confirm draft orders");
        }
        return new PurchaseOrder(id, version, orderNumber, "CONFIRMED");
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }
}
~~~

`@PersistenceCreator` marks the constructor Spring Data uses to restore the object when choosing among multiple constructors/factories. The constructor accepts persistent properties; it does not ask callers to supply unmapped temporary values.

### 8.1. Wither/Copy Methods

An immutable class can expose methods to create a copy with one property changed:

~~~java
public PurchaseOrder withId(Long generatedId) {
    return new PurchaseOrder(
            generatedId, version, orderNumber, status
    );
}

public PurchaseOrder withVersion(Long newVersion) {
    return new PurchaseOrder(
            id, newVersion, orderNumber, status
    );
}
~~~

These are examples of a *wither*: returning a new instance with one changed value without mutating the current instance. Spring Data's object mapping mechanism can use supported creation/copy mechanisms to apply values supplied by the persistence layer to immutable entities. For records, the canonical constructor and component metadata are the natural creation path; for classes, constructors or withers may be used depending on structure.

Do not write application code assuming the framework will always call a specific method named `withId`. Follow the object mapping rules of the Spring Data version in use and always use the repository's returned result.

## 9. Java Records for Value Objects in Aggregates

A well-suited use case is using records for embedded values:

~~~java
public record ShippingAddress(
        String recipient,
        String street,
        String city,
        String postalCode
) {
    public ShippingAddress {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Recipient is required");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street address is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
    }
}
~~~

Two addresses with identical content can be treated as equivalent by value equality. When an order's shipping address changes prior to confirmation, the aggregate root can be recreated with a new `ShippingAddress`.

In Spring Data JDBC, `@Embedded` can be used to map the value object's components to columns of the same row:

~~~java
@Embedded(prefix = "shipping_")
ShippingAddress shippingAddress
~~~

Actual column names are generated according to the prefix and naming strategy, e.g., `shipping_recipient`, `shipping_street`, and `shipping_city`. If multiple objects of the same type exist in one row, prefixes avoid column name collisions.

### 9.1. Records Nested Inside Records

They can be composed:

~~~java
public record OrderHeader(
        String orderNumber,
        ShippingAddress shippingAddress
) {
}
~~~

What matters is Spring Data JDBC mapping metadata, not only Java syntax. For embedded value objects, define columns via `@Embedded` and the corresponding schema. For child entity collections, use aggregate collection mapping mechanisms such as `@MappedCollection`; do not confuse embedded objects with separate child tables.

## 10. Records Containing Collections in Aggregates

An aggregate root sometimes contains a list of members. Records can still declare collection-typed components, yet the collection must be guarded so callers cannot mutate its contents after creation:

~~~java
public record OrderDraft(
        String orderNumber,
        List<String> productCodes
) {
    public OrderDraft {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Invalid order number");
        }
        productCodes = List.copyOf(productCodes);
    }

    public OrderDraft addProduct(String productCode) {
        List<String> updated = new ArrayList<>(productCodes);
        updated.add(Objects.requireNonNull(productCode));
        return new OrderDraft(orderNumber, updated);
    }
}
~~~

The `addProduct` method creates a new list and returns a new record. The old object remains unchanged.

If this is a collection persisted in Spring Data JDBC, map it properly in the aggregate schema. For example, a child entity collection can use `@MappedCollection` with a foreign key pointing back to the root and a key column when order must be preserved. Record components can be used for child objects if constructor mapping and schema are compatible.

Do not use `List.copyOf` as a substitute for mapping annotations: copying the collection is a Java immutability decision; `@MappedCollection` is metadata describing storage relationships. The two solve different problems.

With large aggregates, copying an entire collection on every change can be expensive. Weigh aggregate size, update frequency, and consistency requirements. If a collection has an independent lifecycle, that may be a sign to reconsider the aggregate boundary.

## 11. Constructor Binding and Property Names

Spring Data JDBC restores immutable objects via constructors. For mapping to work:

- The constructor must accept the values needed to build a valid object.
- Parameter names must be discoverable to link with corresponding properties.
- Mapping annotations must be placed on the proper components/properties.
- The constructor must maintain invariants without requiring unpersisted data.

Records have a canonical constructor matching record components, making the link between component names and parameters explicit. For regular classes with multiple constructors, use `@PersistenceCreator` to designate the appropriate persistence constructor.

For regular Java classes, constructor parameter names may rely on compilation metadata. The `-parameters` flag is commonly used to preserve parameter names in bytecode. Check your project's build configuration when Spring Data cannot resolve parameters.

### 11.1. Do Not Put Unpersisted Data into the Persistence Constructor

Suppose an entity has a display value computed only per request:

~~~java
@Transient
private final String displayLabel;
~~~

If the persistence constructor requires `displayLabel` as a mandatory parameter, Spring Data JDBC has no corresponding column from which to pull a value. Instead:

- Compute the value via a method from persisted properties.
- Attach the value after materialization if the class permits controlled transient state.
- Separate a view model/DTO if the data is purely for presentation.

Records have a canonical constructor tied to all components, so adding `@Transient` components to a persistence record requires careful thought. Generally, keep persistence records focused on genuinely mapped data and build separate view DTOs.

## 12. Transactions and Saving Immutable Entities

A service method can load an aggregate, produce a new state, and save it within a transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product rename(Long id, String newName) {
        Product current = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found"
                ));

        Product renamed = current.rename(newName);
        return repository.save(renamed);
    }
}
~~~

This is a clean coordination pattern:

1. The repository reads the current state.
2. The domain method validates the request and creates the next object.
3. The repository saves the new object.
4. The service returns the saved object.

With Spring Data JDBC, calling `save` is an explicit persistence operation. There is no JPA-style automatic dirty checking merely because an object was read in a transaction and a field changed.

Transactions ensure database operations within scope are committed or rolled back together. However, do not hold transactions open while calling external APIs, waiting on users, or doing slow work unrelated to the database, as connections and locks may be held too long.

## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Records are always entities." | A record is just a data class form; entity vs. value object role depends on the domain. |
| "Records are deeply immutable." | Components cannot be reassigned, yet referenced objects can still be mutable. |
| "Immutable entities cannot change state." | A new instance with the same identity and next state can be created. |
| "Record equality is always right for entities." | Default equality compares all components; entities usually need identity semantics. |
| "Calling setters or creating a new record saves automatically." | Spring Data JDBC requires calling a repository or issuing corresponding SQL. |
| "The original object receives the ID after save." | For immutable objects, use the instance returned by the repository. |
| "You can increment version manually in domain methods." | Version is persistence metadata; do not modify it manually without clear rules. |
| "`@Version` replaces transactions." | Optimistic locking detects conflicts; transactions manage commit/rollback boundaries. |
| "Using records reduces SQL query count." | Java type choice does not determine how many SQL queries aggregate mapping generates. |
| "A nested record is always stored in a separate table." | Value objects can be embedded in the same row; collections/child entities require explicit relationship declarations. |
| "`final` guarantees no invalid data." | Invariants must be checked in constructors, factories, domain behavior, and appropriate database constraints. |

## 14. Choosing a Record or a Class for a Spring Data JDBC Model?

| Situation | Suggestion | Reason |
| --- | --- | --- |
| Small value object defined entirely by components | Java record | Value-based equality and clear constructor. |
| Request/response DTO or projection | Java record | Low boilerplate, suitable for data transfer. |
| Entity with custom identity and equality | Immutable class or class encapsulating mutation | Easy to control identity-based `equals`/`hashCode`. |
| Entity with simple state transitions where all-component equality is acceptable | Can use a record | Must verify semantics and ID/version mapping. |
| Aggregate with multiple collections and complex mutation rules | Consider root class with encapsulated collections or record with copy methods | Choose based on invariant enforcement and copy overhead. |
| Derived data used only for display | Computed getter or DTO record | Avoids storing redundant state inside entities. |

There is no rule that every entity must be mutable or every entity must be a record. A practical model may combine:

- Aggregate roots as immutable classes due to custom identity semantics.
- Value objects as records.
- Projections/DTOs as records.
- Certain child entities encapsulated and modified only through the root.

## 15. Business Flow Example: Changing Product Price

Suppose the requirement is to change a product's price and persist the change. Model using a record:

~~~java
public record Product(
        @Id Long id,
        @Version Long version,
        String sku,
        Money price
) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        Objects.requireNonNull(price);
    }

    public Product changePrice(Money newPrice) {
        return new Product(id, version, sku, newPrice);
    }
}
~~~

Service:

~~~java
@Transactional
public Product changePrice(Long id, Money requestedPrice) {
    Product current = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Not found"));

    Product updated = current.changePrice(requestedPrice);
    return repository.save(updated);
}
~~~

State flow:

~~~text
Database row (id=25, version=7, price=100_000)
                    |
                    | findById(25)
                    v
Product #25 v7 price=100_000
                    |
                    | changePrice(120_000)
                    v
Product #25 v7 price=120_000
                    |
                    | repository.save(...)
                    v
Database row (id=25, version=8, price=120_000)
                    |
                    | returned value
                    v
Product #25 v8 price=120_000
~~~

The pre-change object still holds `price=100_000` and `version=7`. The new object before saving holds the same version read from the database. After saving succeeds, use the returned result with the new version. If another request already updated version 7 beforehand, the save operation can fail due to optimistic locking; the service or error-handling layer must decide the appropriate response.

## 16. Design Checklist Before Putting an Immutable Entity into a Repository

When designing an immutable aggregate or entity, ask yourself:

1. **Identity:** which property identifies the entity across state changes? Is default record equality appropriate?
2. **Constructor:** can Spring Data JDBC instantiate the object from mapped columns? Are any unpersisted parameters marked mandatory?
3. **Invariants:** do constructors/factories and domain methods reject invalid states?
4. **Nested objects:** are value objects and collections truly deeply immutable or protected by defensive copies?
5. **Generated values:** how are IDs/versions received from the persistence layer? Does code retain the instance returned by `save`?
6. **Concurrency:** does the aggregate use `@Version` when concurrent updates must be detected?
7. **Aggregate mapping:** are embedded objects and child collections mapped properly to the Spring Data JDBC schema?
8. **Persistence lifecycle:** does the application explicitly call `save` after producing a new state?
9. **Performance:** is the cost of copying collections and saving the aggregate proportional to its size and update frequency?
10. **API boundary:** is the entity used directly as request/response, exposing persistence state externally? If so, would a dedicated DTO be cleaner?

## Key Takeaways

Immutable entities ensure each object represents a clear state; Java records provide concise declarations and value-based equality, making them especially well suited for value objects. For entities with identity, evaluate default record equality and persistence-managed ID/version lifecycles.

In Spring Data JDBC, immutable objects are restored via constructors and changes are persisted only when the application calls a repository or executes corresponding SQL. When saving new entities or versioned entities, always use the object returned by the repository. Protect collections with defensive copies, enforce invariants in the domain model, and use transactions alongside optimistic locking when business rules require concurrency control.
