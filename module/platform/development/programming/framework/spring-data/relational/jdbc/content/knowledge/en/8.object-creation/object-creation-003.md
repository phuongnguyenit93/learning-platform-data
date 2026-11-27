# Constructor Parameter Names and the `-parameters` Compiler Option

Spring Data JDBC must recreate Java objects from data read from the database. When a repository reads a table row, the framework retrieves the column values, converts them to appropriate Java types, and instantiates the aggregate or its component objects. For immutable entities, the constructor is usually where those values are received.

To pass the right value to the right property, Spring Data needs to know the **constructor parameter names**. Java source code may declare:

~~~java
public Customer(Long id, String firstName, String email) {
    // ...
}
~~~

yet parameter names may no longer be present in bytecode if the code was compiled without the `-parameters` option enabled. In that case, the framework might only see generic names such as `arg0`, `arg1`, `arg2`, preventing constructor parameters from matching persistent properties as expected.

This lesson explains the role of parameter names, how to enable `-parameters`, how to use `@ConstructorProperties` and `@PersistenceCreator`, and how to troubleshoot object instantiation errors in Spring Data Relational JDBC.

## 1. Why Does Spring Data JDBC Need Parameter Names?

Spring Data JDBC maps data according to **entity metadata**. Metadata describes Java property names, SQL column names, data types, identifiers, and object creation strategies. When materializing a row, the framework must determine which value goes into which constructor parameter.

Example table:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    email VARCHAR(320) NOT NULL
);
~~~

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private final Long id;

    @Column("first_name")
    private final String firstName;

    private final String email;

    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getEmail() { return email; }
}
~~~

When reading a row, the framework needs to instantiate the equivalent of:

~~~java
new Customer(10L, "Lan", "lan@example.test");
~~~

Spring Data must know:

- The `id` column value goes to the `id` property.
- The `first_name` column value is mapped to the Java property `firstName`, then passed to the `firstName` constructor parameter.
- The `email` column value goes to the `email` parameter.

The key point is that **constructor parameter names are matched against Java property names**, not automatically against physical column names in the database. In the example, parameter name `firstName` is still correct even though the SQL column is named `first_name`, because `@Column("first_name")` declares the relationship between those two names.

~~~mermaid
flowchart TD
    A["SQL row<br/>id, first_name, email"] --> B["Mapping metadata"]
    B --> C["Java properties<br/>id, firstName, email"]
    C --> D["Constructor parameter names"]
    D --> E["new Customer(id, firstName, email)"]
    E --> F["Aggregate instantiated"]
~~~

If parameter names cannot be determined or do not match the properties to populate, Spring Data may not find a way to supply values to the constructor. That is why compiling with parameter names preserved is a vital part of object mapping.

## 2. Parameter Names in Java Source vs. Bytecode

In Java source code, parameter names are always visible:

~~~java
public Customer(Long id, String firstName, String email) {
    // Names id, firstName, email are present in source.
}
~~~

However, Java bytecode does not necessarily store these names as reflection-accessible metadata. If compiled without `-parameters`, reflection calls may return names like `arg0`, `arg1`, and `arg2`; the `Parameter.isNamePresent()` method returns `false`.

Inspection example:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorParameterInspector {
    public static void main(String[] args) {
        for (Constructor<?> constructor
                : Customer.class.getDeclaredConstructors()) {
            System.out.println(constructor);

            for (Parameter parameter : constructor.getParameters()) {
                System.out.printf(
                    "name=%s, namePresent=%s, type=%s%n",
                    parameter.getName(),
                    parameter.isNamePresent(),
                    parameter.getType().getName()
                );
            }
        }
    }
}
~~~

When compiled with parameter names preserved, output may show:

~~~text
name=id, namePresent=true, type=java.lang.Long
name=firstName, namePresent=true, type=java.lang.String
name=email, namePresent=true, type=java.lang.String
~~~

When names are not preserved, output typically looks like:

~~~text
name=arg0, namePresent=false, type=java.lang.Long
name=arg1, namePresent=false, type=java.lang.String
name=arg2, namePresent=false, type=java.lang.String
~~~

The name `arg0` does not tell whether it represents property `id`, `customerId`, or `accountId`. Data types alone are also insufficient for reliable inference: a constructor may take multiple parameters of the same type `String` or `Long`.

**Do not rely on parameter order to guess properties.** When there are multiple parameters of the same type, guessing by position easily assigns the wrong data without failing immediately.

## 3. What Does `-parameters` Do?

`-parameters` is a **Java compiler** option. It instructs the compiler to record parameter name metadata in `.class` files so reflection and frameworks can read the names declared in source code.

Example:

~~~bash
javac -parameters Customer.java
~~~

This is a **compile-time** option, not a JVM runtime flag. The following commands are not equivalent:

~~~bash
java -parameters com.example.CustomerApplication
~~~

~~~bash
java -Dparameters=true com.example.CustomerApplication
~~~

`-g` or enabling debug symbols does not replace `-parameters` either. Debug information and parameter name metadata serve different purposes. Do not assume local variable names in debug tables can substitute for constructor parameter metadata needed by Spring Data.

### Important Condition

The option must be applied when compiling **the class containing the entity constructor**. If the entity resides in a JAR library already compiled without parameter names, enabling `-parameters` in the consuming application cannot recover names lost in that library's bytecode. You must recompile the module/library owning the entity or use explicit metadata such as `@ConstructorProperties`.

## 4. Enabling `-parameters` with Gradle

In a project using Gradle Groovy DSL, configure `JavaCompile` tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Place the configuration in the build script of the module containing the entities, or in a shared build convention if all Java modules need parameter name metadata.

If using Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

If the project manages compiler options in convention plugins, place the option in the exact location responsible for configuring Java compilation. Avoid scattering it across multiple build files where one module gets `-parameters` and another does not.

### Applying by Module Scope

Suppose the layout is:

~~~text
java-learning/
├── module/
│   └── shop/
│       ├── build.gradle
│       └── src/main/java/
│           └── com/example/shop/Customer.java
└── build.gradle
~~~

If only `shop` owns entities requiring constructor mapping, you can configure it in `module/shop/build.gradle`. If the repository has a shared convention for Java modules, configuring it in the convention plugin is more consistent.

One thing to verify is which module produces the entity JAR. For example, module `domain-model` compiles `Customer.class`, while module `shop-app` only depends on that JAR. The option must be present in **`domain-model`**, not just in `shop-app`.

### Recompiling After Changes

After adding the option, make sure Gradle recompiles the relevant classes. If you inspect a stale artifact in the build directory or an old JAR, reflection results may still lack parameter names.

You can run the appropriate compile task in your development environment:

~~~bash
./gradlew :shop:clean :shop:compileJava
~~~

The project path depends on the actual Gradle structure. In multi-module projects, use the exact project path of the module containing the entity.

## 5. Enabling `-parameters` with Maven

With Maven, configure the Java compiler plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

If the project uses properties to manage the Java version, keep the existing source/release configuration and add `parameters` to the plugin. This example only enables saving parameter names; it does not replace selecting the right JDK, release, or annotation processor configuration.

For projects consuming an internal library, ensure the Maven module that produces the entity itself is compiled with this configuration.

## 6. `-parameters` and `@ConstructorProperties`

There are two common ways for Spring Data to learn constructor parameter names:

- Save parameter names into bytecode using the `-parameters` compiler option.
- Declare names explicitly on the constructor with the `java.beans.ConstructorProperties` annotation.

Example:

~~~java
import java.beans.ConstructorProperties;

public class Customer {
    private final Long id;
    private final String firstName;
    private final String email;

    @ConstructorProperties({"id", "firstName", "email"})
    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }
}
~~~

The string array in `@ConstructorProperties` must have the same length and order as the constructor parameter list. Each string is the **Java property name** represented by the corresponding parameter.

| Constructor Parameter | Annotation Value at Same Position |
| --- | --- |
| First parameter `Long id` | `"id"` |
| Second parameter `String firstName` | `"firstName"` |
| Third parameter `String email` | `"email"` |

If the annotation order is swapped:

~~~java
@ConstructorProperties({"email", "firstName", "id"})
public Customer(Long id, String firstName, String email) {
    // ...
}
~~~

the metadata is misdeclared: the first parameter of type `Long` is claimed to be property `email`. This is a mapping bug, not a way to reorder SQL columns.

### When to Use Which?

| Situation | Appropriate Choice |
| --- | --- |
| Gradle/Maven application under your control | Enable `-parameters` in the module compiling entities |
| Library needing explicit constructor metadata | Can use `@ConstructorProperties` on the constructor |
| Cannot change dependency compilation flags | Use annotation metadata if you can edit and recompile the class; otherwise consider another suitable persistence constructor |
| Multiple modules needing the same convention | Configure compiler option in a shared convention/build plugin |
| Java record | Uses canonical constructor and record component names; still verify build/metadata per environment |

These two approaches both support parameter name discovery. You do not need to declare both merely to repeat the same information if the compiler already preserves names properly. If both are used, ensure metadata remains consistent.

## 7. Which Constructor Does `@PersistenceCreator` Select?

An entity may have multiple constructors: a full constructor for persistence, convenience constructors for business logic, a no-arg constructor, or constructors for testing. Spring Data needs to know which constructor to use to restore the entity.

Spring Data's `@PersistenceCreator` annotation marks the constructor or factory method used for persistence when explicit selection is needed.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private final Long id;
    private final String firstName;
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }

    public Customer(String firstName, String email) {
        this(null, firstName, email);
    }
}
~~~

The three-parameter constructor is chosen for persistence; the two-parameter constructor can serve business use cases for creating a new customer.

**`@PersistenceCreator` does not replace `-parameters`.** It answers *which constructor to use*, whereas parameter names of that constructor still must be discovered through appropriate metadata such as `-parameters` or `@ConstructorProperties`.

### General Constructor Selection Rules

Spring Data has object creation rules based on constructor count, annotated constructors, and class kind. Generally:

- If there is only one suitable constructor, the framework can use that constructor.
- If there are multiple constructors, mark the persistence constructor with `@PersistenceCreator` to avoid ambiguous selection.
- If using a static factory method for persistence, annotate the appropriate factory method.
- For a Java record, the canonical constructor is the natural constructor to create the record from its components.

When a class has multiple constructors including a no-arg constructor, do not assume the full constructor will always be selected. Define the persistence constructor explicitly according to the rules of the Spring Data version in use.

## 8. Parameter Names Must Match Java Property Names, Not Column Names

This is an easy point of confusion when combining `@Column` with constructor mapping.

~~~java
@Table("customers")
public class Customer {
    @Id
    private final Long id;

    @Column("first_name")
    private final String givenName;

    private final String email;

    public Customer(Long id, String givenName, String email) {
        this.id = id;
        this.givenName = givenName;
        this.email = email;
    }
}
~~~

Mapping table:

| Layer | Name |
| --- | --- |
| Database column | `first_name` |
| Annotation | `@Column("first_name")` |
| Java property | `givenName` |
| Constructor parameter | `givenName` |

This is a consistent mapping. The framework uses column metadata to read `first_name` into property `givenName`, then uses the corresponding property name to locate the value for constructor parameter `givenName`.

If the constructor is written as:

~~~java
public Customer(Long id, String firstName, String email) {
    this.id = id;
    this.givenName = firstName;
    this.email = email;
}
~~~

then parameter `firstName` no longer shares the same name as property `givenName`. Simply renaming the variable inside the constructor body does not let Spring Data infer that `firstName` represents `givenName`. Rename the parameter to `givenName`, or provide appropriate explicit constructor metadata.

**Do not name parameters after SQL columns** if the Java property name differs. For example, parameter `first_name` is not a substitute for `givenName`; underscores in column names are already handled by mapping metadata.

## 9. Immutable Entities and Constructor Mapping

Spring Data JDBC supports immutable entity models. Properties can be `final`, requiring no public setters; the framework instantiates objects via constructors and can use property population mechanisms when needed.

Example:

~~~java
@Table("products")
public class Product {
    @Id
    private final Long id;

    @Column("product_name")
    private final String name;

    private final int quantity;

    @PersistenceCreator
    public Product(Long id, String name, int quantity) {
        this.id = id;
        this.name = name;
        this.quantity = quantity;
    }

    public Product(String name, int quantity) {
        this(null, name, quantity);
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public int getQuantity() { return quantity; }
}
~~~

With the full persistence constructor, the framework can pass values read from the database immediately upon object creation. The two-parameter business constructor allows the application to create a new product without knowing the database-generated ID.

A clear constructor brings benefits:

- Object state is fully established at creation time.
- No public setters are needed purely for persistence.
- Business invariants can be validated inside the constructor.
- Fields of the same type are not accidentally swapped by positional instantiation scattered across multiple places.

However, constructor mapping only succeeds if Spring Data can determine the persistence constructor, parameter names, and type conversions for each value.

## 10. Java Records and Component Names

A Java record represents data using record components:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    @Column("first_name") String firstName,
    String email
) {}
~~~

The compiler generates a canonical constructor whose parameters correspond to the record components. Component names are part of record metadata, so Spring Data can use the canonical constructor to materialize the record.

Component names are still Java property names:

- `firstName` is the component/property name.
- `first_name` is the column name specified by `@Column`.

There is no need to write a constructor duplicating the canonical constructor if no custom logic is needed. If additional constructors are defined, pay attention to constructor selection rules and keep mapping unambiguous.

Projects using Java records must be compiled with a JDK supporting records (Java 16 or later). In a Java 21 codebase, this feature is built in. `-parameters` remains a good compiler option for regular Java constructors; do not generalize record metadata behavior to all Java classes.

## 11. Type Conversion and Parameter Names Are Two Separate Concerns

Correct parameter names do not guarantee a value can be converted to the Java type. For example, a SQL `created_at` column has a timestamp type, whereas the constructor accepts `Instant`:

~~~java
public Customer(Long id, String firstName, Instant createdAt) {
    this.id = id;
    this.firstName = firstName;
    this.createdAt = createdAt;
}
~~~

Spring Data JDBC uses the conversion infrastructure to convert JDBC values to the corresponding property/constructor types. There are two distinct categories of errors:

| Category | Example | Resolution |
| --- | --- | --- |
| Name cannot be determined | Parameter only shows `arg2`, or name does not match property | Enable `-parameters`, use `@ConstructorProperties`, fix parameter name |
| Type cannot be converted | Database returns `Timestamp`, constructor expects type without converter | Use a supported type or register an appropriate converter |
| No suitable constructor found | Multiple constructors without designating persistence constructor | Use `@PersistenceCreator` following the rules |
| Missing required value | Constructor requires property absent from mapping result | Check schema, projection, and query mapping |
| Value violates invariant | Constructor rejects invalid data | Reconcile data/schema and business rules |

Do not try to fix a type conversion error by renaming a parameter, or fix a parameter name error by adding a converter. Classify the root cause accurately.

## 12. Constructor Mapping with Repositories and Custom Queries

A CRUD repository can restore an aggregate from a table:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

When calling:

~~~java
Customer customer = customerRepository.findById(10L).orElseThrow();
~~~

Spring Data JDBC reads the data and uses object mapping metadata to create `Customer`.

With custom queries, results still must be mapped to the target Java type:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, first_name, email
        FROM customers
        WHERE email = :email
        """)
    Customer findByEmail(String email);
}
~~~

This example assumes the query returns the columns needed to construct `Customer`. If the query returns only a subset of columns while the persistence constructor requires multiple mandatory properties, the framework may fail to create a complete entity. Design a dedicated projection/DTO for reduced results, or return complete data matching the mapping.

For custom queries, two things must be correct simultaneously:

1. SQL must return column names and values compatible with the mapping.
2. The target type must have a constructor that Spring Data can select and supply with sufficient parameters.

A SQL query that executes successfully against the database does not guarantee it can materialize into every Java class.

## 13. How to Verify Compiled Parameter Names

### 13.1. Inspecting via Reflection

Use `Parameter.isNamePresent()` as shown in Section 2. This directly checks the metadata the application will see at runtime.

You can add a small test:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import org.junit.jupiter.api.Test;

class CustomerConstructorMetadataTest {

    @Test
    void constructorParameterNamesArePresent() {
        Constructor<?> constructor =
            Customer.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            assertTrue(
                parameter.isNamePresent(),
                () -> "Missing parameter name for " + parameter
            );
        }
    }
}
~~~

This snippet is suitable only if the class has one constructor or the test explicitly selects the persistence constructor. If there are multiple constructors, look up the constructor by signature instead of taking the first element of the reflection array, because the order returned by `getDeclaredConstructors()` is not a persistence selection contract.

### 13.2. Inspecting Bytecode with `javap`

The JDK provides the `javap` tool to inspect class metadata:

~~~bash
javap -v -p path/to/Customer.class
~~~

Look for the `MethodParameters` section of the constructor. When compiled with `-parameters`, this section displays parameter names such as `id`, `firstName`, `email`. Having debug info without `MethodParameters` does not prove reflection can read parameter names.

### 13.3. Checking the Actual Running Artifact

Sometimes the build changed, yet the application is still running an older JAR. Identify which directory or JAR the class is loaded from, inspect the bytecode of that exact artifact, and re-run the application after building the module owning the entity.

If the entity comes from an internal dependency, inspect the dependency JAR rather than only checking the application's `build/classes` directory.

## 14. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Constructor parameters only named `arg0`, `arg1` | Class compiled without `-parameters` and no fallback metadata | Enable compiler option in module building entity or use `@ConstructorProperties` |
| Spring Data cannot instantiate entity | No suitable constructor found or parameter names do not match properties | Review constructors, property names, and `@PersistenceCreator` |
| Class has business and persistence constructors, wrong one chosen | Multiple constructors without marking persistence constructor | Use `@PersistenceCreator` on the intended constructor |
| Parameter names match yet data is assigned wrongly | Order/names in `@ConstructorProperties` wrong or inconsistent property mapping | Match each parameter against its Java property |
| Enabled `-parameters` yet still failing | Enabled in application module instead of entity module, or using stale JAR | Inspect actual class/JAR via reflection or `javap` |
| Constructor receives no column value | Custom query missing column or column name mismatch with mapping | Return all columns, use `@Column` properly, or use an appropriate projection |
| Value cannot be converted | JDBC type incompatible with parameter type | Use supported type or register a converter |
| Field refactored but constructor parameter not renamed | Constructor parameter still has old name | Rename parameter or provide appropriate mapping metadata |
| Java records work while regular classes fail | Record components have dedicated metadata; regular classes lack parameter metadata | Enable `-parameters` for regular classes |

### Practical Investigation Checklist

When encountering a materialization error, follow this sequence:

1. Identify the specific entity class and the constructor Spring Data expects to use.
2. Check the names of the entity's persistent properties.
3. Inspect constructor reflection: `getParameters()`, `getName()`, `isNamePresent()`.
4. Check `-parameters` on the compile task of the module producing the class or check `@ConstructorProperties`.
5. Check `@PersistenceCreator` if there are multiple constructors.
6. Compare parameter names with **Java property names**, then check `@Column` linking properties to SQL columns.
7. Check whether the query returns all needed columns and converters handle the data types.
8. Verify the running class is the newly compiled artifact.

Do not change multiple settings simultaneously before determining which metadata is missing. Reflection provides fast evidence to distinguish compiler metadata errors from other mapping errors.

## 15. Recommended Implementation Conventions

For Java projects using Spring Data JDBC:

- Enable `-parameters` in shared Java compilation configuration or in every module compiling entities.
- Use a clear persistence constructor for immutable entities.
- Use `@PersistenceCreator` when a class has multiple constructors and a specific constructor must be selected.
- Use `@ConstructorProperties` when parameter names need explicit declaration or compiler options cannot be controlled in certain environments.
- Keep constructor parameter names matching Java property names, even when SQL column names are customized with `@Column`.
- Use records when the model suits immutable data and a canonical constructor.
- Verify built artifacts, especially for entities located in separate modules or internal libraries.
- Do not confuse `-parameters` with `-g`, JVM system properties, annotation processors, or Hibernate configuration.

A minimal build convention example:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

This configuration ensures Java constructors compiled within that task's scope retain parameter names. It does not replace declaring proper schemas, mapping annotations, constructor selection, or converters.

## 16. Practice Exercises

### Exercise 1 — Observe Bytecode

Create class:

~~~java
public class Account {
    private final Long id;
    private final String accountNumber;

    public Account(Long id, String accountNumber) {
        this.id = id;
        this.accountNumber = accountNumber;
    }
}
~~~

Compile once without `-parameters`, and once with `-parameters`. Use reflection to compare `Parameter.getName()` and `isNamePresent()`. Explain why the same source code produces different runtime metadata.

### Exercise 2 — Constructor Mapping with Column Name Differing from Property Name

Create table `customers` with column `first_name`, then declare an entity with property `givenName` and constructor parameter `givenName`. Use `@Column("first_name")` to map it. Try changing the parameter to `firstName` while keeping property `givenName`, observe the error, and explain why.

### Exercise 3 — Two Constructors

Create an entity with a full constructor taking `id`, `name`, `email` and a business constructor taking `name`, `email`. Mark the persistence constructor with `@PersistenceCreator`. Verify parameter names of the persistence constructor are preserved in bytecode.

### Exercise 4 — Try `@ConstructorProperties`

Disable `-parameters` for a learning entity module and add `@ConstructorProperties` with the correct property names. Inspect metadata via reflection and test reading the entity through a repository. Then intentionally swap the annotation order to observe the difference.

### Exercise 5 — Verify Module Dependency

Place the entity in a module producing a separate JAR, and keep the Spring Data JDBC application in another module. Enable `-parameters` only in the application module and inspect the entity constructor inside the JAR. Then enable it in the module owning the entity, rebuild the JAR, and compare.

### Exercise 6 — Distinguish Name Errors from Type Errors

Create a constructor with parameter `Instant createdAt` mapped to a timestamp column. Test two cases: parameter name mismatching the property; parameter name matching, yet the data type needing a converter. Explain why the two errors require different fixes.

## 17. Official References

- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): how Spring Data creates objects, selects constructors/factories, and maps parameters to properties.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): constructor rules, immutable objects, metadata, and persistence annotations.
- [Spring Data Commons — `@PersistenceCreator` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/PersistenceCreator.html): marks the constructor or factory method used to create persistent objects.
- [Java `ConstructorProperties` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/ConstructorProperties.html): declares property names corresponding to constructor parameters.
- [Java Compiler — `javac` options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-parameters` option to store parameter name metadata.
- [Gradle JavaCompile](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): configuring compiler arguments in Java compile tasks.

Constructor parameter names are part of the object mapping contract: Spring Data needs to match parameters to Java properties to restore entities from SQL rows. Enabling `-parameters` preserves names in bytecode; `@ConstructorProperties` declares names explicitly; `@PersistenceCreator` chooses which constructor to use. When these three pieces are configured accurately and consistently with property mapping, Spring Data JDBC can create immutable entities cleanly and reliably.
