# Requirements for Constructors, Entity Classes, and Proxyability

## 1. Why Do Entities Have Special Rules?

An entity is a Java object managed by JPA and mapped to data in a database. When reading data, the JPA provider must create an instance, populate state from columns, and track changes in the persistence context. When the application uses lazy loading, the provider may also replace or wrap the entity with an intermediate object to defer loading related data.

Therefore, a class used as an entity has requirements that differ from a DTO or an ordinary business class. A no-argument constructor allows the provider to create the object before populating data. The class and its methods must be designed so that the provider can access state, override methods, or generate proxies when needed.

In Spring Data JPA, repositories do not directly decide how entities are instantiated. Spring Data JPA calls JPA APIs; Hibernate or the active JPA provider is responsible for creating instances, managing the persistence context, and performing proxying or bytecode enhancement.

This lesson focuses on three closely related requirements:
- The no-argument constructor and how JPA creates entities.
- The structure, modifiers, and attribute access modes of an entity class.
- Proxyability to support lazy loading.

## 2. Basic Requirements for an Entity Class

Under the portable Jakarta Persistence contract, an entity class must follow key rules:

1. It must be a top-level class or a suitable static nested class. A non-static inner class requires an enclosing class instance and is not suitable for independent instantiation by the provider.
2. It must have a no-argument constructor with public or protected visibility.
3. The class must not be declared final.
4. Methods and persistent instance variables must not be declared final.
5. It must be annotated with @Entity and follow JPA mapping rules.
6. It may be an abstract class if the inheritance model requires it; the provider will instantiate the appropriate concrete entity.

Example of a valid entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Customer() {
        // Constructor for JPA.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

The protected constructor satisfies JPA's requirement. The application still has a parameterized constructor to create new entities for business logic. There is no need to make the JPA constructor public just for repository usage.

Fields can be private. JPA does not require every attribute to have public getters/setters. Actual access depends on the chosen field access or property access strategy.

### 2.1. Top-level class and static nested class

Entities are typically declared as top-level classes:

```java
@Entity
public class Order {
    protected Order() {
    }
}
```

If an entity must be nested inside another class, the nested class must be static:

```java
public class PersistenceModel {

    @Entity
    public static class Customer {
        protected Customer() {
        }
    }
}
```

A non-static inner class holds an implicit reference to an instance of the enclosing class. Its constructor inherently requires that instance, whereas JPA must be able to create an entity without knowing a specific enclosing instance. Therefore, do not use a non-static inner class as an entity.

In typical projects, top-level classes are easier to read, easier to find, and less confusing.

### 2.2. An entity can be abstract, but must not be final

An abstract entity can serve as the root of a hierarchy:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue
    private Long id;

    protected Payment() {
    }
}
```

Concrete child entities inherit from it and are mapped by JPA according to the chosen inheritance strategy. Abstract prevents direct instantiation of the root class; it is not synonymous with final.

Conversely, a final class prevents Hibernate from generating a subclass proxy via standard inheritance mechanisms. It also violates the portable entity class requirement. Do not declare an entity as final if you want the application to follow the JPA contract and support standard lazy proxies.

## 3. No-Argument Constructor

### 3.1. Why does JPA need this constructor?

When querying the database, the provider needs to create an entity object. With field access, the general process is:

1. Create an instance via the no-argument constructor.
2. Populate column values into persistent fields.
3. Set up relationship state and internal management metadata.
4. Place the entity into the persistence context for tracking.

JPA does not require the provider to call an application's parameterized constructor to reconstruct the object. The provider needs a consistent way to instantiate objects without knowing which business constructor matches each row of data.

The no-argument constructor is therefore part of the persistence contract, not the primary constructor for application code to use.

### 3.2. Why should it be protected?

Protected visibility both satisfies JPA and prevents external code from arbitrarily creating an empty entity:

```java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Product name is required");
        }
        this.name = name;
    }
}
```

Application code creates new entities through the parameterized constructor. The provider can call the protected constructor when hydrating the entity. The no-argument constructor may also be public, but there is usually no benefit if the application does not need to create empty entities.

Do not declare the JPA constructor as private if you want to comply with the portable contract, because the specification requires public or protected.

### 3.3. Having a parameterized constructor still requires a no-argument constructor

Java only generates a default constructor automatically when a class declares no constructors at all. Once a parameterized constructor is declared, the compiler no longer creates an empty constructor.

Invalid example:

```java
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    public Product(String name) {
        this.name = name;
    }
}
```

This class only has a constructor taking name. When Hibernate needs to create an entity, it cannot find a suitable no-argument constructor. This can lead to entity instantiation failures or runtime query errors.

Fix:

```java
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }
}
```

### 3.4. The JPA constructor should do minimal work

The no-argument constructor should be simple and perform no business logic:

- Do not call repositories or services.
- Do not open transactions or database connections.
- Do not publish business events.
- Do not call overridable methods.
- Do not assume fields already have values from the database.
- Do not check invariants across all attributes because the provider has not hydrated them yet.

Do not place email-sending, invoice-creating, or business-audit logic inside an entity constructor. The provider may call the constructor when reading data, creating proxies, or in other internal situations. If the constructor causes side effects, a query could accidentally repeat a business action.

Business logic should be invoked explicitly from an application service or domain method after the entity has been created and holds the necessary state.

### 3.5. Field initializers and the JPA constructor

Java field initializers still execute when the object is created. Example:

```java
private boolean active = true;
private List<OrderLine> lines = new ArrayList<>();
```

When JPA hydrates an entity, the provider loads persistent state from the database. Initializer values should not be treated as defaults replacing the schema or database data.

Initializing collections to avoid null is often helpful, but the provider may replace the collection with its own wrapper to manage lazy loading and dirty checking. Do not keep a reference to the old collection and continue manipulating it after the provider has replaced it.

For persistent fields with business defaults, distinguish between:
- The default value when the application creates a new entity.
- The value stored in the database.
- The value the provider reloads when hydrating the entity.

These three can differ. If a database-level default is needed, define it in the schema or migration; a Java initializer does not create defaults for rows written by other applications.

## 4. Field Access and Property Access

JPA supports two primary ways to access persistent state.

### 4.1. Field access

When mapping annotations like @Id are placed on fields, JPA uses field access:

```java
@Entity
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String accountName;

    protected Account() {
    }

    public String getAccountName() {
        return accountName;
    }

    public void changeAccountName(String value) {
        this.accountName = value;
    }
}
```

The provider reads and writes persistent fields directly using the access mechanism permitted at runtime. Fields can be private; public setters are not required for every attribute.

Advantages of field access:
- Preserves encapsulation of the entity API.
- Avoids creating public setters solely for persistence.
- Getters can be designed for the domain without necessarily being persistence entry points.
- Avoids invoking setters with side effects during entity hydration.

This is the common approach in many Hibernate applications.

### 4.2. Property access

When mapping annotations are placed on getters, JPA uses property access:

```java
@Entity
public class Account {

    private Long id;
    private String accountName;

    protected Account() {
    }

    @Id
    @GeneratedValue
    public Long getId() {
        return id;
    }

    public String getAccountName() {
        return accountName;
    }

    public void setAccountName(String accountName) {
        this.accountName = accountName;
    }
}
```

With property access, the provider uses getters to read and setters to write state. Persistent accessors must obey JPA access rules; setters should not contain complex side effects because the provider may call them during hydration.

Property access is useful when you need to customize how a persistent value is retrieved or assigned, but accessors must remain simple, deterministic, and independent of setter call order.

### 4.3. Do not mix annotations arbitrarily

By default, the placement of the @Id annotation determines the access type of the entity hierarchy. If @Id is on a field, mapping annotations are typically placed on fields; if it is on a getter, they are typically placed on getters.

Mixing mapping annotations between fields and getters without explicit declaration can cause the provider to misinterpret mappings or report errors. When you genuinely need to choose an access type, you can use @Access:

```java
@Entity
@Access(AccessType.FIELD)
public class Account {
    // Persistent mappings placed on fields.
}
```

You can select property access at the class level or on a specific attribute following Jakarta Persistence rules. Only use mixed access when there is a clear reason and it has been tested; a consistent convention is usually easier to maintain.

## 5. Why Do Proxies Require an Inheritable Entity?

### 5.1. What is a proxy?

A proxy is an intermediate object representing an entity or an entity relationship. The provider can return a proxy instead of loading the entire state immediately. The proxy holds the required identifier and knows how to ask the provider to load data when the application accesses needed attributes.

With Hibernate, a common type of proxy is a subclass dynamically generated from the entity class. The proxy overrides overridable methods to intercept calls, check whether the entity is initialized, and load state when necessary.

Example relationship:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

When loading a PurchaseOrder, the provider may not yet load the full Customer. The customer field may hold a proxy. When code accesses customer.getName(), the proxy asks the database to load the data if it is not yet initialized and the persistence context is still active.

### 5.2. Why does a final class block subclass proxies?

A subclass proxy needs to create a child class of the entity class. Java does not allow extending a final class. If an entity is final, a subclass-based proxy mechanism cannot create the child class.

Unsuitable example:

```java
@Entity
public final class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

The portable fix is to remove final:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

Not only the class, persistent methods should also not be final. If a getter is final, the subclass proxy cannot override that getter to intercept calls and trigger lazy initialization. Likewise, persistent instance variables must not be declared final under the portable entity contract.

### 5.3. How do final methods and final fields affect behavior?

With property access, getters/setters are the path to persistent state. If a getter is final, the proxy cannot override it to intercept access. This can prevent lazy loading from working as expected or make it non-portable across providers.

With field access, the provider can access fields directly according to the mapping. However, the specification still requires persistent instance variables to be non-final. Final fields also make it difficult for the provider to hydrate and update state via standard mechanisms.

Safe rules:
- Entity classes are not final.
- Persistent methods are not final.
- Persistent instance fields are not final.
- The JPA constructor is public/protected and no-argument.

Helper methods unrelated to persistent state can be designed as needed, but they should not turn the entity into final or prevent proxy-required accessors from being overridden.

## 6. Lazy Loading and the Persistence Context

Proxies are only part of lazy loading. For a proxy to load data, the provider still needs access to an active persistence context and an appropriate transaction.

A common scenario:

1. A service opens a transaction.
2. A repository loads a PurchaseOrder.
3. The customer relationship is marked lazy.
4. The service accesses order.getCustomer().getName().
5. Hibernate initializes the proxy with an additional query.
6. The transaction ends; the entity and proxy may become detached.

If the application keeps the proxy and then accesses an unloaded attribute after the persistence context closes, Hibernate may throw LazyInitializationException.

Good design is to identify the data needed for a use case and load it within the transaction:
- Use fetch join when the query needs that relationship.
- Use @EntityGraph when you want to declare a fetch plan.
- Use DTO projections when only a specific set of columns is needed.
- Convert required data into a DTO before returning a response outside the transaction.

Do not turn on eager loading for all relationships just to avoid lazy exceptions. Eager loading can pull in large amounts of unnecessary data and increase query count or complexity.

### 6.1. Lazy is a hint in certain relationships

In JPA, @ManyToOne and @OneToOne default to EAGER; if you want to defer them, you must declare fetch = FetchType.LAZY. The specification treats LAZY as a hint to the provider, so verify behavior with the active provider and configuration.

Collection relationships like @OneToMany and @ManyToMany default to LAZY. Hibernate commonly uses a persistent collection wrapper to track initialization and modifications to the collection.

Example:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Declaring LAZY does not mean the data will never be loaded; it defers loading until the use case needs it and the provider is able to execute that load.

### 6.2. Proxies and identifiers

Providers can often know a proxy's identifier without loading the entire entity. Thus, calling the ID getter sometimes does not trigger a query; detailed behavior depends on the mapping and provider.

Do not write business logic assuming that every getter will avoid triggering SQL. Observe actual SQL, especially when serializing entities or calling toString(), equals(), and hashCode().

## 7. Bytecode Enhancement and Limitations of Subclass Proxies

Hibernate can use bytecode enhancement to add behavior to entity classes, such as lazy attribute loading, dirty tracking, or state management capabilities without relying solely on subclass proxies.

This can expand how Hibernate handles lazy loading and reduce some limitations of traditional proxies. However:
- Bytecode enhancement is a provider-specific mechanism and does not alter the portable Jakarta Persistence requirements.
- Build/plugin configuration must actually run enhancement on the required classes.
- Behavior must be tested with the exact Hibernate version and production configuration.
- Do not assume enhancement turns every final entity into a portable entity or makes every final accessor safe.

When designing entities for ordinary Spring Data JPA applications, keep entities inheritable and persistent accessors overridable. Only rely on enhancement when the project has configured, verified, and intentionally accepted the Hibernate dependency.

## 8. Common Design Mistakes

### 8.1. Declaring only a parameterized constructor

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;

    public Customer(String name) {
        this.name = name;
    }
}
```

Error: no no-argument constructor. The provider cannot instantiate the entity under the JPA contract.

Fix by adding a protected constructor:

```java
protected Customer() {
}

public Customer(String name) {
    this.name = name;
}
```

### 8.2. Declaring an entity final

```java
@Entity
public final class Customer {
    protected Customer() {
    }
}
```

Error: does not satisfy portable requirements and prevents Hibernate subclass proxies. Fix by removing final from the entity class.

### 8.3. Marking a persistent getter as final

If a getter used for property access is declared final, a subclass proxy cannot override it. Keep persistent accessors non-final.

### 8.4. Using a record as an Entity

A Java record is final, has a canonical constructor matching its components, and lacks a no-argument constructor in the traditional entity model. Records are well suited as DTOs, request/response objects, or projections, but are not an appropriate choice for standard JPA entities.

Example DTO record:

```java
public record CustomerSummary(Long id, String name) {
}
```

You can use records in constructor projections or DTO mappings, while entities remain mutable classes managed by JPA.

### 8.5. Using Lombok @Data on an entity

@Data generates getters, setters, equals, hashCode, and toString based on fields. For entities, this easily causes problems:
- toString() may access lazy relationships and trigger queries.
- equals()/hashCode() may traverse associations, causing loops or unintended data loading.
- Bidirectional relationships can cause infinite recursion.
- Mutable fields can cause hashCode to change after an entity has been placed in a HashSet/HashMap.

Use Lombok annotations selectively, such as @Getter and @Setter where appropriate, and design equals/hashCode according to domain rules. A no-argument constructor must still be declared or generated with appropriate visibility:

```java
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@Getter
@Entity
public class Customer {
    // ...
}
```

Lombok only generates code at compile time; inspect the generated result, especially when using @Builder, @AllArgsConstructor, or @Value. @Value typically makes the class and fields final, so it is unsuitable for standard JPA entities.

### 8.6. JPA constructor with side effects

If the no-argument constructor sends events, writes business logs, creates auxiliary data, or calls services, those actions may occur every time the provider creates an instance to hydrate or proxy. Keep this constructor minimal and move side effects to a service or appropriate lifecycle callback.

### 8.7. Using equals/hashCode based on all fields

Entities often have bidirectional relationships and lazy fields. If equals() or hashCode() traverses all fields, merely comparing two entities can:
- Trigger lazy loading.
- Create cycles through bidirectional relationships.
- Read more data than necessary.
- Change hashCode after mutable fields change.

If an immutable and unique natural key exists, you can use it as the basis for comparison. If using a generated ID, design carefully for pre-persist and post-persist states; the ID may be null before the entity is saved. No single implementation fits every domain.

## 9. Notes for Kotlin and Languages with Final Classes by Default

Kotlin classes and methods are final by default. When using Kotlin with JPA, you need to configure compiler plugins to open appropriate classes/methods and generate no-argument constructors for entities.

Two common plugins:
- kotlin-jpa (no-arg plugin) helps generate no-argument constructors for JPA annotations.
- all-open can open classes annotated with configured annotations, such as @Entity, so proxying works.

Specific configuration depends on the Kotlin and Gradle plugin versions. Verify that plugins apply to the right modules and JPA annotations used by the project. Do not just add runtime dependencies and assume the compiler generated the right code.

With Java, this is simpler because classes are not final by default; just avoid declaring final and provide a no-argument constructor with the right visibility.

## 10. Verifying Entity Instantiation and Proxyability

### 10.1. Verifying with an integration test

A test can verify that an entity is persisted, reloaded, and a lazy relationship is initialized inside a transaction. Illustrative example:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void loadsLazyCustomerInsideTransaction() {
        Customer customer = new Customer("Lan");
        entityManager.persist(customer);

        PurchaseOrder order = new PurchaseOrder(customer);
        entityManager.persist(order);
        entityManager.flush();
        entityManager.clear();

        PurchaseOrder loaded = repository.findById(order.getId())
            .orElseThrow();

        assertThat(loaded.getCustomer().getName()).isEqualTo("Lan");
    }
}
```

This is an illustrative example; constructors and mappings of Customer and PurchaseOrder must exist in the corresponding test model. clear() detaches saved entities from the persistence context, forcing the subsequent load to read from the database again. Accessing getName() checks the lazy loading path inside the test transaction.

### 10.2. Checking loaded state with PersistenceUnitUtil

JPA provides PersistenceUnitUtil to check loaded state:

```java
PersistenceUnitUtil util =
    entityManagerFactory.getPersistenceUnitUtil();

boolean loaded = util.isLoaded(order, "customer");
```

This is a standard JPA API, more useful than checking specific Hibernate proxy class names. Do not write tests that depend on dynamically generated class names because proxy names and mechanisms can change across provider versions.

Hibernate also provides its own API like Hibernate.isInitialized(...), but that is a provider-specific dependency. Use it when a test intentionally checks Hibernate behavior, whereas portability tests should prefer JPA APIs.

### 10.3. What to observe

When testing proxies and lazy loading, check:
- Entities persist and reload normally.
- Unaccessed lazy relationships remain unloaded if the provider and mapping truly support it.
- Accessing lazy attributes inside a transaction works.
- Uninitialized proxies are not accessed after the persistence context closes.
- Generated SQL count is reasonable, with no unexpected N+1 queries.
- Entities still work with the right constructors, field/property access, and modifiers.

Do not only check whether getClass() is a proxy class. A provider may use subclass proxies, bytecode enhancement, or another mechanism.

## 11. Entity Class Design Checklist

Before finalizing an entity, check:

- [ ] The class is annotated with @Entity.
- [ ] The class is a top-level or static nested class.
- [ ] The class is not declared final.
- [ ] A public or protected no-argument constructor is present.
- [ ] The JPA no-argument constructor contains no business logic or side effects.
- [ ] Parameterized constructors/factory methods can be added for application code.
- [ ] Persistent instance fields are not final.
- [ ] Persistent methods/accessors are not final.
- [ ] Field/property access type is consistent and explicit.
- [ ] Mapping annotations are placed in the correct location for the access type.
- [ ] Lazy relationships are loaded within transactions and appropriate fetch plans.
- [ ] equals, hashCode, and toString do not accidentally traverse lazy associations.
- [ ] Lombok does not generate final classes/fields or unsuitable constructors.
- [ ] Kotlin no-arg/all-open plugins are configured if using Kotlin.
- [ ] Integration tests confirm persist, load, and lazy access.

## 12. Conclusion

JPA needs a no-argument constructor so the provider can create entities before populating state from the database. That constructor must be public or protected and should be kept minimal. Entity classes must be inheritable under the portable contract; the class, persistent methods, and persistent fields should not be final.

These rules are especially important for Hibernate subclass proxies, the mechanism commonly used to defer loading related entities. Lazy loading also depends on the persistence context and transactions, so data should be loaded within proper use-case boundaries and verified with integration tests.

Good entity design clearly separates the constructor intended for persistence from how the application creates new objects, keeps the access strategy consistent, avoids side effects in constructors, and prevents proxies from being blocked by modifiers or generated code.
