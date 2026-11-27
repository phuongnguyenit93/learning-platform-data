# Entity Type and Identifier Type in Repository Declarations

When declaring a Spring Data JPA Repository, the two most important generic types are the **Entity type** and the **Identifier (ID) type**. They tell Spring Data which entity the Repository manages and what Java data type it accepts when finding, checking, or deleting a record by primary key.

Common declaration:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

In this example, **Product** is the managed Entity type, and **Long** is the Java type of the primary key property in that Entity. Both types must match the actual JPA mapping.

## 1. Meaning of the Two Generic Parameters

JpaRepository has the general form:

~~~java
public interface JpaRepository<T, ID> {
}
~~~

- **T (Domain type / Entity type):** the entity class that the Repository operates on. Examples: Product, Customer, Order.
- **ID (ID type):** the Java type of the primary key mapped by @Id or the primary key class used with @EmbeddedId / @IdClass.

Example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

This declaration means the Repository manages Customer objects; operations by primary key accept a Long value.

Inherited methods use these two types. For example, in terms of API signatures:

~~~java
Optional<T> findById(ID id);
boolean existsById(ID id);
void deleteById(ID id);
<S extends T> S save(S entity);
~~~

With ProductRepository extends JpaRepository<Product, Long>, the corresponding methods can be called as follows:

~~~java
Optional<Product> product = productRepository.findById(10L);
boolean exists = productRepository.existsById(10L);
productRepository.deleteById(10L);

Product saved = productRepository.save(new Product("Keyboard"));
~~~

Thanks to the generic declaration, the compiler can check argument and result types while writing code. For instance, passing a string to findById on a Repository whose ID is Long will produce a compilation error.

## 2. The Entity Type Must Be a JPA-Managed Class

The first parameter must represent the Entity that the Repository needs to operate on. Typically, that class is annotated with @Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Corresponding Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

When Spring Data initializes the Repository, it needs to resolve Entity metadata from JPA. Therefore:

- Use the exact class annotated with @Entity, such as Product.
- Do not use a DTO, request object, or response object as the Entity type parameter.
- Do not use a class annotated only with @MappedSuperclass as the Repository's Entity type if that class is not declared as an independent Entity.
- If the Entity resides in a package not scanned by JPA, the application may fail to recognize the Entity even if the generic declaration looks correct.

A Repository can have methods returning DTOs or projections, but the Repository's root Entity type remains the JPA-managed Entity.

## 3. The ID Type Must Match the Primary Key Property

Consider an Entity with a primary key of type Long:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }
}
~~~

Appropriate declaration:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

If the property annotated with @Id is Integer, the Repository should declare ID as Integer. If it is String, the ID type is String.

| Mapping in Entity | ID Type in Repository | Example Value |
|---|---|---|
| @Id private Long id; | Long | 25L |
| @Id private Integer id; | Integer | 25 |
| @Id private String code; | String | "SKU-001" |
| @Id private UUID id; | UUID | A UUID object |
| @EmbeddedId private OrderKey id; | OrderKey | An OrderKey object |

The ID type is the **Java type of the primary key property**, not the column name and not the table name. For example, a SQL column of type BIGINT is typically mapped to Long; the Repository uses Long, not the string "BIGINT".

### Using Wrapper Types Instead of Primitive Types

Java does not allow primitive types as generic type arguments. Therefore, if the ID property is declared as long, the Repository parameter must still be Long:

~~~java
@Id
private long id;

// Generic must use wrapper:
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

In JPA Entities, prefer wrapper types such as Long, Integer, or UUID when appropriate. With auto-generated keys, a null value can indicate that the Entity does not yet have an ID. Primitive types like long always default to 0, so they cannot represent an unpopulated state in that way.

Commonly used example:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Avoid manually assigning an ID to an Entity that uses an auto-generation strategy unless the generation strategy and the Entity's new/existing state detection have been explicitly designed.

## 4. Example with a String Primary Key

Not every primary key is an auto-incrementing number. A unique business code can also be used as a primary key if the data model calls for it.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @Column(length = 30)
    private String code;

    @Column(nullable = false)
    private String name;

    protected Category() {
    }

    public Category(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() {
        return code;
    }
}
~~~

Repository:

~~~java
public interface CategoryRepository
        extends JpaRepository<Category, String> {
}
~~~

Usage:

~~~java
Optional<Category> category =
        categoryRepository.findById("ELEC");

boolean exists =
        categoryRepository.existsById("ELEC");
~~~

In this example, String is the ID type because the code property is annotated with @Id. You do not need to use Long just because other tables in the application use numeric keys.

If a business code might change in the future, consider using a stable surrogate key such as Long or UUID while placing a separate unique constraint on the business code. Primary keys should generally remain stable because they may be referenced by other tables.

## 5. Composite Primary Keys and the Repository ID Type

An Entity can have a primary key consisting of multiple properties—for example, an order line identified by both the order ID and the line number. In JPA, the two common mapping approaches are @EmbeddedId and @IdClass.

When using a composite primary key, the ID type in the Repository is **the class representing the entire composite key**, not the type of a single component.

### Approach 1: Using @EmbeddedId

Create a key class annotated with @Embeddable:

~~~java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineKey implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineKey that)) return false;
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity containing the @EmbeddedId property:

~~~java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineKey id;

    private String productName;

    protected OrderLine() {
    }

    public OrderLine(OrderLineKey id, String productName) {
        this.id = id;
        this.productName = productName;
    }

    public OrderLineKey getId() {
        return id;
    }
}
~~~

The Repository must declare the composite key class as its second parameter:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineKey> {
}
~~~

How to call it:

~~~java
OrderLineKey key = new OrderLineKey(100L, 2);

Optional<OrderLine> line =
        orderLineRepository.findById(key);

orderLineRepository.deleteById(key);
~~~

Here, T = OrderLine and ID = OrderLineKey. Do not declare JpaRepository<OrderLine, Long> because the Entity's primary key is the pair of orderId and lineNumber.

The primary key class needs to implement equals() and hashCode() based on all key components. This is critical for key comparison and consistent Entity management. Following the traditional JPA composite key model, the key class needs an appropriate no-arg constructor and must implement Serializable.

### Approach 2: Using @IdClass

With @IdClass, the key properties are declared directly on the Entity and the ID class only describes the structure of the key:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@IdClass(OrderLineId.class)
public class OrderLine {

    @Id
    private Long orderId;

    @Id
    private Integer lineNumber;

    private String productName;

    protected OrderLine() {
    }
}
~~~

Repository:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {
}
~~~

With @IdClass, the names and Java types of the fields in the key class must match the @Id properties on the Entity. The key class also needs equals(), hashCode(), serialization capability, and a no-arg constructor as required by the JPA model.

Do not declare the ID type as Long just because one component of the composite key has type Long. The Repository needs to accept the full key as OrderLineId.

## 6. How Do Entity and ID Types Affect Repository Methods?

Once declared:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Basic operations have consistent types:

~~~java
Optional<Product> findById(Long id);

boolean existsById(Long id);

void deleteById(Long id);

<S extends Product> S save(S entity);

List<Product> findAll();
~~~

You do not need to rewrite basic CRUD methods. Spring Data provides them based on the Entity type and ID type.

Query methods on other Entity properties also use the Entity type as their return type:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByName(String name);

    Optional<Product> findFirstByNameOrderByIdAsc(String name);

    boolean existsByName(String name);
}
~~~

Property names in derived query methods must correspond to the Entity's Java properties. For example, if the Entity has private String productName, the method can be findByProductName(...), even if the database column name is product_name.

Distinguish findById(...) inherited from Repository from derived query methods. findById is the standard method using the primary key declared in the ID generic. If you want to search by another business property, name the method after that property, such as findByCode(...) or findByEmail(...).

With pagination, the Entity type also determines the element type in the result:

~~~java
Page<Product> findByNameContaining(
        String keyword,
        Pageable pageable
);
~~~

The result is a Page<Product> because the Repository manages the Product Entity.

## 7. Can You Create a Generic Base Repository?

In projects with many Entities, you can create a base interface to reuse common declarations:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {
}
~~~

Then, each concrete Repository provides its Entity and ID types:

~~~java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}

public interface CategoryRepository
        extends BaseRepository<Category, String> {
}
~~~

@NoRepositoryBean tells Spring Data that this base interface is a structure meant for inheritance, not a concrete Repository for which a bean should be created directly. Each child Repository must specify concrete Entity and ID types.

Avoid using raw types like JpaRepository or overly broad declarations like JpaRepository<Object, Object> to bypass generic errors. That approach loses type safety, makes Repository configuration confusing, and easily leads to runtime errors.

## 8. Common Declaration Mistakes

### Using the Wrong ID Type

Entity:

~~~java
@Entity
public class Product {

    @Id
    private Long id;
}
~~~

Incorrect declaration:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, String> {
}
~~~

Correct declaration:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

The ID type must follow the Java type of the @Id property. If they do not match, calls to methods such as findById, existsById, and deleteById may fail type checking at compile time or fail when integrating with JPA metadata.

### Using a Database Column Type Instead of a Java Type

Do not write JpaRepository<Product, "BIGINT">. Generics require a Java type such as Long, not a SQL type name as a string.

### Using a Primitive Type in Generics

You cannot write JpaRepository<Product, long> because Java generics do not accept primitives. Use Long.

### Mistakenly Using a DTO as the Entity Type

A DTO not managed by JPA cannot replace an Entity in JpaRepository. Declare the Repository with the Entity, then use projections or DTOs in query methods when needed.

### Forgetting to Declare an ID in the Entity

An Entity needs a primary key recognized by JPA via @Id or a valid composite key structure. Without a primary key, Hibernate cannot manage the Entity under the standard JPA model.

### Declaring the Generic ID as Only Part of a Composite Key

For Entities using @EmbeddedId or @IdClass, use the composite key class as the second parameter. Do not use the type of an individual field within the key.

### Redeclaring findById with a Different Type

Do not declare your own findById(String id) method in a Repository whose generic ID is Long to query by a business column. Use a property-based query name such as findByCode(String code). Keep findById(Long id) for the primary key.

## 9. How to Verify Before Declaring a Repository

When creating a Repository for a new Entity, you can check step by step:

1. Identify the Entity class annotated with @Entity.
2. Locate the @Id property or the @EmbeddedId / @IdClass structure.
3. Check the Java type of the primary key: Long, Integer, String, UUID, or a composite key class.
4. Declare JpaRepository<EntityType, IdType> using those exact two types.
5. Verify that calls to findById, save, deleteById, and property-based queries have matching argument and return types.
6. Start the application and confirm Spring Data recognizes the Repository, Entity, and primary key.

Quick checklist table:

| Question | What to Confirm |
|---|---|
| Which Entity does the Repository manage? | The concrete @Entity class |
| Does the Entity use a single or composite key? | @Id, @EmbeddedId, or @IdClass |
| What is the ID type? | Java type of the key or composite key class |
| What is the first generic argument? | The Entity class itself |
| What is the second generic argument? | The ID type itself |
| What name do queries by other properties use? | The Entity's Java property name |

## 10. Notes on Jakarta Persistence Versions

The examples in this article use the jakarta.persistence namespace, matching Spring Boot 3 and later along with the corresponding Jakarta EE ecosystem. Spring Boot 2 projects typically use the older javax.persistence namespace. Do not mix both namespaces in the same Entity model; use the dependency version aligned with your project.

Certain specific features, such as UUID auto-generation strategies, depend on the Jakarta Persistence version and JPA provider. If you use a specialized ID type, check support in your running Hibernate version and database rather than only changing generics on the Repository.

## 11. Conclusion

In the declaration JpaRepository<T, ID>, T is the JPA-managed Entity class and ID is the Java type of the primary key. For single-column keys, the generic ID must match the @Id property type; for composite keys, the generic ID is the key class used in @EmbeddedId or @IdClass. When both types are declared accurately, Spring Data can provide CRUD methods with clear type safety, making Repository code safer and easier to maintain.
