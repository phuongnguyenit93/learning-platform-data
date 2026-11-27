# Immutable Objects, Constructors, and Java Records by Supported Version

Spring Data Elasticsearch does not merely read JSON and assign each field into an empty object. When converting an Elasticsearch document into a Java entity, Spring Data must determine which class to instantiate, which constructor to invoke, and where each property's value is passed.

For entities with setters, this process is fairly direct: instantiate the object and populate the properties. For immutable entities, fields are typically `final` with no setters; Spring Data must instantiate the object using a constructor supplied with sufficient data. Java records work in a similar direction: components are declared once and initialized via the canonical constructor.

This lesson explains how Spring Data Elasticsearch instantiates entities, how constructors are selected, how to design immutable classes, how to use records, and what to verify by Java/Spring Data version.

## 1. From Elasticsearch Document to Java Object

Elasticsearch stores documents as JSON data in an index. When searching or reading a document, the response may contain:

- `_source`: the document data.
- `_id`: the document ID managed by Elasticsearch.
- `_index`: the index containing the document.
- `_version` or sequence metadata depending on the API and configuration.
- `_score`, sort values, highlights, and other search metadata.

Spring Data Elasticsearch receives the response and uses mapping metadata to convert data into a Java entity. For example, a document with `_source` like:

~~~json
{
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "available": true
}
~~~

The corresponding entity might be:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private double price;

    private boolean available;

    // constructors, getters, setters
}
~~~

When calling the repository:

~~~java
Optional<Product> product = productRepository.findById("p-100");
~~~

Spring Data reads the document, converts each value to the appropriate Java type, instantiates `Product`, and returns the object to the application. `@Id` binds the `id` property to the document ID; this property does not necessarily appear inside `_source`.

Object instantiation is part of object mapping. It involves `ElasticsearchConverter`, persistent entity metadata, constructor metadata, and property accessors. Thus, constructor design directly impacts whether Spring Data can read an entity.

## 2. Mutable Entities and Immutable Entities

A mutable entity allows state changes after creation. Typically, the class has a no-arg constructor, assignable fields, and setters provided:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private String email;
    private String displayName;

    public Customer() {
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Spring Data can instantiate `Customer` with the empty constructor and populate properties through property accessors. This is straightforward, though the object can exist in an incomplete state between creation and field population.

An immutable entity does not allow state changes after initialization. Properties are typically `final`, have no setters, and are passed through a constructor:

~~~java
@Document(indexName = "customers")
public final class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Spring Data can instantiate the entity using this constructor and pass the corresponding values. Once the constructor finishes, the object has complete state for the passed properties.

### Benefits of Immutable Entities

- **Stable state:** the object cannot be modified unexpectedly after creation.
- **Easier reasoning:** when reading an entity, you can trust its values will not be altered by other code via setters.
- **Safer sharing:** multiple components can read the same object with less concern about concurrent state mutation.
- **Validation at creation time:** the constructor can enforce required invariants and reject invalid objects.
- **Good fit for domain models:** values considered fixed after creation can be represented with `final` fields.

In return, immutable entities must be designed to align with the object mapping mechanism. If the constructor does not receive all needed properties, Spring Data may not be able to restore complete state. Properties generated by Elasticsearch, such as the ID, also need intentional handling.

## 3. How Does Spring Data Select a Constructor?

Spring Data uses metadata to determine the appropriate constructor or factory method when creating a persistent entity. Conventions let the framework choose automatically in simple cases; annotations are used to clarify intent when multiple options exist.

Common design cases:

| Class Structure | How It Is Handled |
|---|---|
| Only one constructor | Spring Data can use that constructor to instantiate the entity |
| Multiple constructors | Mark the intended constructor with `@PersistenceCreator` |
| Empty constructor and other constructors | Explicitly identify the right constructor; do not rely on declaration order |
| Java record | Uses the record's canonical constructor |
| Marked static factory method | Spring Data can use the factory method per object mapping rules |

Detailed rules may depend on the Spring Data version. When a class has multiple constructors, the clearest approach is to mark the persistence constructor with the annotation.

### Using `@PersistenceCreator`

`@PersistenceCreator` belongs to Spring Data Commons:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

@Document(indexName = "customers")
public class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Customer(String email, String displayName) {
        this(null, email, displayName);
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

The class has a full constructor for restoring the entity and a shorter constructor for creating new objects in business logic. The annotation specifies the constructor Spring Data must use when reading data.

If the class has only one suitable constructor, the annotation may not be necessary. However, when adding business constructors, factories, or overloads in the future, the annotation prevents constructor selection from changing unexpectedly.

### Constructor Parameters Must Map to Properties

Spring Data needs to know which constructor parameter corresponds to which property. Parameter names are typically used to bind to property names in the entity.

For regular Java classes, enable the compiler option that preserves parameter names:

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

If parameter names are not retained in bytecode, the framework may fail to infer the corresponding properties in some cases. When that happens, entity creation can fail or pick an incorrect mapping.

Constructor parameter names should match Java property names. If the field name in Elasticsearch differs from the Java property name, use mapping annotations to describe the stored field name; do not rename constructor parameters just to mimic JSON names if the Java property retains a different name.

### Constructors and Data Validation

A constructor is a natural place to enforce object invariants:

~~~java
public Customer(String id, String email, String displayName) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException("email is required");
    }

    this.id = id;
    this.email = email;
    this.displayName = displayName;
}
~~~

However, older documents in Elasticsearch may omit fields or contain `null` values. If a new constructor adds strict validation, old documents that fail the condition may become unreadable.

When changing the constructor of an already stored entity, consider:

- Could the field be missing in old documents?
- Does the new field have a valid default value?
- Do primitives like `int` or `boolean` lose the distinction between a default value and missing data?
- Is a data migration needed before deploying the new version?

For potentially absent fields, wrappers like `Integer`, `Boolean`, or `Double` preserve `null` state so the application can decide how to handle it.

## 4. Property Population After the Constructor Runs

Constructors do not always receive every property. Spring Data may need to populate remaining properties after instantiating the object. This is done via the property accessor mechanism.

For mutable entities, the framework can use setters or field access per mapping metadata. For immutable entities, properties not initialized by the constructor require a mechanism that creates a new instance, such as a wither method.

A wither method accepts a new value and returns a new object:

~~~java
public Customer withDisplayName(String displayName) {
    return new Customer(id, email, displayName);
}
~~~

Because the method returns a new object, the class maintains immutability. Spring Data can use wither conventions when updating a property that cannot be mutated directly.

### Properties Generated by Elasticsearch

An important case is an ID generated when saving a document. The application can create an entity with `id = null`, send the entity to Elasticsearch, and receive the server-generated ID.

An immutable entity can provide a wither for the ID:

~~~java
@Document(indexName = "customers")
public final class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Customer withId(String id) {
        return new Customer(id, email, displayName);
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

After saving, use the object returned by the repository:

~~~java
Customer input = new Customer(null, "dev@example.com", "Developer");

Customer saved = customerRepository.save(input);

System.out.println(saved.getId());
~~~

Do not assume the input object is always mutated in place to receive the ID. For immutable entities, the returned instance may be a new instance containing the newly assigned ID.

### Do Not Omit Properties Outside the Constructor

If an entity has a persistent property that is not accepted by the constructor, Spring Data must find a way to populate that property after creating the instance. For mutable fields, this is usually simple. For `final` fields with no suitable setter or wither, the framework cannot update the state in the usual way.

Therefore, when designing immutable entities, include the persistent properties that need to be restored in the selected constructor. If a property can change over its lifecycle, consider a wither returning a new instance or adjust the data model.

## 5. What Is a Java Record?

A Java record is a class form intended for fixed-structure data. A record automatically provides:

- Components declared in the header.
- Corresponding fields and accessors with the same names as the components.
- A canonical constructor to initialize all components.
- `equals`, `hashCode`, and `toString` based on the components.

Example:

~~~java
public record CustomerRecord(
    String id,
    String email,
    String displayName
) {}
~~~

Records are immutable at the component level: component fields are `final` and cannot be reassigned after the constructor finishes. However, if a component references a mutable collection or object, the referenced object itself can still change. Records do not automatically create deeply immutable object graphs.

Records fit entities or documents with clear data structures that rarely need mutation after being read. They also reduce boilerplate for getters, constructors, `equals`, and `hashCode`.

### Using Records as Elasticsearch Entities

Spring Data Elasticsearch can map records when the Spring Data version in use supports record mapping:

~~~java
@Document(indexName = "orders")
public record Order(
    @Id String id,
    @Field(type = FieldType.Keyword) String orderNumber,
    @Field(type = FieldType.Double) Double total,
    boolean paid
) {}
~~~

When reading a document, Spring Data uses `Order`'s canonical constructor and passes values for the corresponding components. Mapping annotations on components describe how Spring Data binds the record to the index and fields.

The application can use a repository just like with regular entity classes:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

Example service:

~~~java
Order order = new Order(
    null,
    "ORD-2026-001",
    129.90,
    false
);

Order saved = orderRepository.save(order);
~~~

If Elasticsearch generates the ID, ensure the Spring Data version in use can assign IDs to record entities according to the project's mapping mechanism. You can provide a wither method returning a new record to represent updating the ID:

~~~java
public record Order(
    @Id String id,
    String orderNumber,
    Double total,
    boolean paid
) {
    public Order withId(String id) {
        return new Order(id, orderNumber, total, paid);
    }
}
~~~

Records do not allow modifying components directly, yet can still declare methods returning a new record with one component changed.

## 6. Canonical Constructors and Compact Constructors

Every record has a canonical constructor matching all components. If not declared explicitly, Java generates this constructor automatically.

You can write a compact constructor to validate or normalize data:

~~~java
public record ProductSnapshot(
    String sku,
    String name,
    Double price
) {
    public ProductSnapshot {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        if (price != null && price < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
    }
}
~~~

A compact constructor does not need to repeat the parameter list or field assignments. Java performs the component assignments after the compact constructor body completes.

Spring Data still instantiates the record through the canonical constructor. Therefore, validation in a compact constructor is also executed when data is read from Elasticsearch.

This has two sides:

- Valid data always passes through the same initialization rules.
- Older or incomplete documents can cause entity reads to throw exceptions.

Before adding new validation to a record representing already stored data, evaluate historical data and a migration plan.

## 7. Java and Spring Data Versions Supporting Records

Records are a Java language feature finalized in Java 16. Java 14 and 15 previously offered records as a preview feature; do not use preview features for ordinary applications without a specific reason.

However, the Java compiler supporting records does not mean every version of Spring Data can map records. Both conditions must be met simultaneously:

1. The project's JVM and compiler support Java records.
2. The Spring Data Commons/Spring Data Elasticsearch version in use supports record object mapping.

In modern Spring Boot projects using Java 17 or newer and the corresponding Spring Data version, records are a practical choice for immutable documents. For older projects, check the reference documentation and release notes of the exact release train. Do not merely upgrade the JDK and assume record mapping is already supported.

### Guidance Table by Environment

| Environment | Guidance |
|---|---|
| Java below 16 | Use regular classes; records are not a standard Java feature of this runtime |
| Java 16+ with older Spring Data | Confirm record mapping is supported before using |
| Spring Boot 3.x with Java 17+ | Records are usually suitable; keep Spring Data dependencies managed by the release train |
| Project overriding Spring Data/client | Check the actual dependency tree and version documentation before relying on record support |

Spring Boot manages a curated set of dependencies designed to work together. If you override Spring Data Elasticsearch or Spring Data Commons, verify the actual version of record mapping being loaded.

### If an Older Version Does Not Support Record Mapping Yet

You can use an immutable class with a constructor annotated with `@PersistenceCreator`:

~~~java
@Document(indexName = "orders")
public final class Order {

    @Id
    private final String id;

    private final String orderNumber;
    private final Double total;

    @PersistenceCreator
    public Order(String id, String orderNumber, Double total) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Double getTotal() {
        return total;
    }
}
~~~

This still provides constructor binding and immutable state without depending on record support.

## 8. Record, Immutable Class, and Mutable Class: Which to Choose?

No single entity style fits every scenario. Choose based on data lifecycle and Spring Data version capabilities.

| Criterion | Mutable Class | Immutable Class | Java Record |
|---|---|---|---|
| Modify properties after creation | Yes | No, create new instance | No, create new record |
| Empty constructor | Usually present | Not needed with constructor binding | Not present in the usual way |
| Boilerplate | More | Can have many getters/constructors | Minimal |
| Constructor mapping | Can be used | Primary mechanism | Canonical constructor |
| Generated ID | Can assign via setter/field | May need wither | May need wither returning new record |
| Validation at initialization | Possible | Natural in constructor | Can use compact constructor |
| Suits fixed-structure data | Yes | Yes | Very well suited |

### When to Choose a Mutable Class?

Choose a mutable class if the domain model needs to update many fields across its lifecycle, existing code relies on setters, or integration libraries require mutable objects. It is also an accessible choice for legacy projects.

### When to Choose an Immutable Class?

Choose an immutable class when you want strict state control, constructors that enforce invariants, and entities with rich business behavior. Immutable classes also fit when compatibility with older Java versions lacking records is required.

### When to Choose a Record?

Choose a record for documents that primarily represent data, have a stable structure, and require no mutation behavior. Records provide concise code, clear accessors, and component-based equality.

If an entity contains substantial domain behavior, needs class inheritance, needs special proxies, or has a complex mutation lifecycle, a regular class may be more suitable.

## 9. Common Issues When Mapping Constructors and Records

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cannot instantiate entity | No suitable constructor found | Check constructors and `@PersistenceCreator` |
| Constructor receives wrong or missing values | Parameter names could not be inferred | Check `-parameters` and property names |
| Immutable entity has null fields | Property not passed through constructor and no update mechanism | Add property to constructor or provide a wither |
| Record is not mapped | Spring Data release does not yet support record mapping | Check Spring Data version |
| Reading old document throws exception | New constructor/compact constructor requires a mandatory field missing in old data | Inspect historical data and migrations |
| ID is null after save | Immutable entity is not mutated the way the app expects | Check wither and use the object returned from `save` |
| Numeric value becomes 0 even when field is missing | Primitive type cannot distinguish null from default value | Consider wrapper types |
| Adding a constructor breaks mapping | Framework picks a different constructor or sees multiple candidates | Annotate the persistence constructor |

### Missing Constructor Parameter Names Error

If Spring Data cannot bind constructor parameters to properties, check the bytecode and compiler configuration. For Gradle, confirm `-parameters` is applied to the module containing the entities. For Maven, check `<parameters>` in the compiler plugin.

Also ensure parameter names match Java property names and the right constructor is selected.

### Record Error on Older Versions

If a record compiles cleanly yet Spring Data cannot instantiate the entity, identify the actual runtime versions of Spring Data Commons and Spring Data Elasticsearch. Check release notes to confirm record mapping support. If the version does not support it, use an immutable class with constructor binding or upgrade the entire dependency set along a compatible release train.

### ID Issue with Immutable Entities

When the ID is generated by Elasticsearch, the original input object may still retain `id = null`. Inspect the object returned from `save` and how Spring Data updates immutable properties. If needed, define a wither named according to convention that returns a new instance.

## 10. Complete Example: Repository with an Immutable Entity

The example below illustrates an immutable entity with an ID, explicitly mapped fields, and a wither for the ID:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public final class Product {

    @Id
    private final String id;

    @Field(type = FieldType.Keyword)
    private final String sku;

    @Field(type = FieldType.Text)
    private final String name;

    @Field(type = FieldType.Double)
    private final Double price;

    @PersistenceCreator
    public Product(
            String id,
            String sku,
            String name,
            Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Product withId(String id) {
        return new Product(id, sku, name, price);
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public Double getPrice() {
        return price;
    }
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(
            String sku,
            String name,
            Double price) {

        Product input = new Product(null, sku, name, price);

        // Use the returned instance because the ID may be generated by Elasticsearch.
        return repository.save(input);
    }

    public Optional<Product> find(String id) {
        return repository.findById(id);
    }
}
~~~

In this example:

1. `@Document` specifies the index.
2. `@Id` binds the Java ID to the document ID.
3. `@Field` describes data types in the index.
4. `@PersistenceCreator` identifies the constructor used to restore the entity.
5. `final` fields and absence of setters preserve immutability.
6. `withId` provides a way to create a new instance when the ID needs to be updated.
7. The service returns the result of `save` so the caller receives the saved entity.

The example demonstrates the constructor binding pattern. When applying it, verify the Spring Data Elasticsearch version and how ID generation is configured in your project.

## 11. Notes on Using Lombok and Code Generation

Lombok can reduce boilerplate, but it also affects the constructors that Spring Data sees.

For example, combining `@NoArgsConstructor`, `@AllArgsConstructor`, and `@RequiredArgsConstructor` can generate multiple constructors. Without explicitly identifying the persistence constructor, Spring Data may not choose the constructor the developer intended.

Some guidelines:

- Inspect the actual constructors generated by Lombok.
- Mark the persistence constructor with `@PersistenceCreator` when multiple constructors exist.
- Ensure constructor parameters have names matching the properties.
- Do not add setters to immutable fields merely to avoid constructor handling if the domain needs to preserve immutability.
- If using a builder, remember that a builder does not automatically replace Spring Data's constructor mapping mechanism.

You can use a builder to construct entities in business code, but Spring Data still needs a constructor or factory method that object mapping can recognize.

## 12. Performance of Constructor-Based Mapping

Spring Data uses metadata and object/property accessor mechanisms to reduce reflection overhead in supported cases. However, optimization capability depends on class structure, visibility, runtime, and framework version.

For mapping to work efficiently:

- Use clear constructors without heavy logic or network calls.
- Keep entities as top-level or static nested classes.
- Avoid `private` constructors if the framework requires access without a suitable mechanism.
- Enable preserving parameter names when compiling regular Java classes.
- Use constructor binding for immutable entities to avoid multiple property assignment steps.
- Avoid expensive validation per hit if data can be validated at a more appropriate layer.

Do not alter domain design solely based on a performance assumption. If mapping is a bottleneck, measure timings and profile before optimizing.

## 13. Entity Mapping Verification Checklist

When an immutable entity or record fails to read, check in order:

1. Verify the Java runtime and compiler versions.
2. Verify the actual runtime versions of Spring Data Elasticsearch/Spring Data Commons.
3. Check that the entity has `@Document` and properties have appropriate mapping annotations.
4. Check the selected constructor; if multiple constructors exist, use `@PersistenceCreator`.
5. Check constructor parameter names and the `-parameters` compiler option.
6. Ensure every persistent property needing restoration is accepted by the constructor or has an appropriate property population mechanism.
7. For records, confirm the canonical constructor and that record mapping is supported.
8. Inspect the actual document, especially missing fields or differing data types.
9. Check how the ID is assigned and whether the caller uses the instance returned by `save`.

When distinguishing a mapping error from a query error, try reading a document with a known simple structure. If Elasticsearch returns a hit yet fails to construct the entity, focus on constructors, property metadata, and the converter rather than changing Query DSL.

## 14. Design Principles

Mutable entities, immutable classes, and records all have a place in Spring Data Elasticsearch. What matters is selecting the option that fits the data lifecycle and framework version.

- Use constructor binding to create immutable entities with complete state.
- Use `@PersistenceCreator` to designate the constructor when multiple options exist.
- Keep constructor parameter names matching Java properties.
- Use `-parameters` for regular Java classes so Spring Data can discover parameter names.
- Use a wither when an immutable property needs to be updated via a new instance, especially for generated IDs.
- Use canonical constructors and component mapping when your Spring Data version supports Java records.
- Inspect historical data before adding mandatory validation to constructors.
- Keep dependencies within a compatible release train rather than relying solely on code compiling.

By understanding how Spring Data chooses constructors and restores properties, you can design immutable entities or records that remain compatible with reading, saving, and searching documents in Elasticsearch.
