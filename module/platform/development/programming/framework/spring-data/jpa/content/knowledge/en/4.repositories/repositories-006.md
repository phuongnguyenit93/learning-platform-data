# Selecting Methods with `@RepositoryDefinition` and Base Interfaces

## Objectives

Spring Data JPA allows a Repository to expose only the data operations that a given part of the application actually needs. Instead of always extending `JpaRepository` and automatically inheriting the entire CRUD API, we can select a smaller set of methods in two ways:

- Use `@RepositoryDefinition(domainClass = ..., idClass = ...)` on a concrete Repository interface.
- Create a minimal base interface extending `Repository<T, ID>`, declare only the methods you want to use, and have concrete Repositories extend that interface.

Both approaches let you control the API at the Java type level. A base interface also enables reusing the same set of methods across multiple entities. This article explains how Spring Data detects these interfaces, how `@NoRepositoryBean` works, how to combine query methods, and how to choose the right design.

## 1. A Repository Is an Abstraction, Not Mandatory Full CRUD

A Spring Data Repository is an interface describing how the application accesses data. Spring Data scans the interface, creates a proxy, and dispatches methods to the corresponding JPA implementation. With Spring Data JPA, the default implementation is typically `SimpleJpaRepository`.

Common foundational interfaces:

| Interface | Role |
| --- | --- |
| `Repository<T, ID>` | Minimal marker interface for Spring Data to recognize the repository and entity/ID types. |
| `CrudRepository<T, ID>` | Standard group of CRUD operations such as saving, finding, counting, and deleting. |
| `ListCrudRepository<T, ID>` | CRUD variant returning `List` for collection-returning methods. |
| `PagingAndSortingRepository<T, ID>` | Provides pagination and sorting operations. |
| `JpaRepository<T, ID>` | Extended API for JPA, including batch operations, flush, and other JPA capabilities. |

`JpaRepository` is very convenient when a component needs full data management capabilities. However, if a module only needs to read data, extending `JpaRepository` makes the module's API broader than required. Callers see `save`, `delete`, and `flush` methods even though the business logic only needs queries.

Spring Data lets you define an interface extending only the `Repository` marker and declare the exact method signatures to expose. Signatures matching foundational operations are routed to the repository base implementation; new query methods are parsed by name or annotation.

## 2. Selecting Methods Directly with `Repository<T, ID>`

`Repository<T, ID>` carries only information about the domain type and primary key type. It does not expose full CRUD automatically. We can copy the signatures of the methods we need from CRUD interfaces into our own interface.

Example exposing read-only capabilities:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    Optional<Customer> findById(Long id);

    List<Customer> findAll();

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

This interface exposes three methods: find by ID, list all, and case-insensitive find by email. It does not declare `save`, `deleteById`, or `flush`, so code using the bean through the `CustomerReadRepository` type cannot invoke those methods directly.

`findById` is a foundational method recognized by Spring Data by signature and forwarded to the repository implementation. `findAll` is also a foundational method. `findByEmailIgnoreCase` is a derived query: Spring Data parses the method name, resolves the `email` property, and generates the corresponding JPA query.

### If a Write Operation Is Also Needed

Add only the signatures truly required. For example, an interface with read and save capabilities but no delete:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface CustomerWriteRepository
        extends Repository<Customer, Long> {

    <S extends Customer> S save(S entity);

    Optional<Customer> findById(Long id);

    List<Customer> findAll();
}
```

The generic signature `<S extends Customer> S save(S entity)` preserves the concrete entity type when calling `save`, matching the signature in CRUD repositories. There is no need to declare `delete` if the module is not supposed to perform deletions through this interface.

Narrowing an interface is an API design technique that reduces accidental misuse at compile time. It is not a database security boundary: code can still write data through another bean, `EntityManager`, JDBC, or a different Repository if granted access.

## 3. Using a Base Interface to Reuse a Set of Methods

When multiple entities require the same set of operations, avoid repeating signatures in every Repository. Create a generic interface as a base:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}
```

`T` is the entity type and `ID` is the primary key type. Each concrete Repository supplies these two types when extending it:

```java
import java.util.Optional;

public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

Another Repository can reuse the same interface:

```java
public interface ProductRepository
        extends ReadOnlyRepository<Product, Long> {

    List<Product> findByActiveTrue();
}
```

As a result, `CustomerRepository` and `ProductRepository` both expose `findById` and `findAll`, while each interface keeps its own domain-specific query methods.

### Why Is `@NoRepositoryBean` Required?

`ReadOnlyRepository<T, ID>` is an intermediate interface. It does not yet specify a concrete entity because `T` and `ID` remain generic type parameters. We do not want Spring Data to instantiate a Repository bean directly from this interface.

`@NoRepositoryBean` tells the Repository scanning mechanism that the interface is solely a base for concrete interfaces to extend, not a standalone repository instance. Child interfaces such as `CustomerRepository` are still scanned and turned into beans normally.

Without the annotation, Spring Data may try to create a repository for the intermediate interface and fail to resolve a suitable domain type or ID type. Placing `@NoRepositoryBean` on non-concrete base repository interfaces is an essential convention.

### Extending Base Interfaces in a Controlled Manner

To add a shared method, add its signature to the base interface. For example:

```java
@NoRepositoryBean
public interface ReadWriteRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();

    <S extends T> S save(S entity);
}
```

Every Repository extending `ReadWriteRepository` will expose `save`. If only a subset of entities should be writable, create a separate interface branch for that group rather than putting `save` into a base interface shared across every entity.

Avoid packing a large set of CRUD methods into a base interface just to save a few lines. The goal is to express the exact capabilities that child Repositories need to share.

## 4. Using `@RepositoryDefinition` on a Concrete Repository

`@RepositoryDefinition` is an alternative to extending `Repository<T, ID>`. The annotation explicitly declares the repository's entity and ID types:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(domainClass = Customer.class, idClass = Long.class)
public interface CustomerQueryRepository {

    Optional<Customer> findById(Long id);

    List<Customer> findAll();

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

Spring Data recognizes the interface annotated with `@RepositoryDefinition`, creates a proxy for it, and handles its methods via the Repository infrastructure. Foundational methods such as `findById` and `findAll` are routed to the base implementation; `findByEmailIgnoreCase` is handled as a derived query.

Key differences:

| Definition Style | How Domain and ID Are Specified | Best When |
| --- | --- | --- |
| `extends Repository<Customer, Long>` | Declared in generic type arguments. | You want the interface to explicitly show Repository inheritance. |
| `@RepositoryDefinition(domainClass = Customer.class, idClass = Long.class)` | Declared via annotation attributes. | You want an interface that does not extend the `Repository` marker. |
| Generic base interface with `@NoRepositoryBean` | Base interface keeps `T`, `ID`; child interface supplies concrete types. | Multiple Repositories need to share a selected set of methods. |

Usually you only need to pick one style per Repository. There is no need to combine `@RepositoryDefinition` and `extends Repository` on the same interface. When multiple Repositories share the same structure, a generic base interface usually reduces duplication better.

## 5. How Spring Data Distinguishes Foundational Methods from Query Methods

The repository proxy must decide how each method will be executed.

### Foundational Methods

Signatures such as `findById(ID id)`, `findAll()`, or `save(S entity)` match operations already provided by the repository base implementation. When we selectively copy those signatures into a subinterface of `Repository`, Spring Data can still forward calls to the store module's default implementation.

`findById` is a reserved Repository method for looking up by the entity identifier. If an entity happens to have another property named `id` that is not the primary key, give the query method a clearer name, such as `findCustomerById(...)`, to avoid colliding with the foundational method.

### Derived Query Methods

Methods such as `findByEmailIgnoreCase`, `findByStatusAndCreatedAtAfter`, or `existsByEmail` are parsed from their names:

- `findBy`: starts a read query.
- `Email`: the entity's `email` property.
- `IgnoreCase`: case-insensitive string comparison.
- `And`, `Or`, `After`, `Before`, `Containing`, `In`, `Between`: operators and combinators supported by Spring Data.

Example:

```java
public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByNameContainingIgnoreCase(String keyword);
}
```

Spring Data checks properties on the entity, not SQL column names. If the Java property is `email` while the column is mapped via `@Column(name = "email_address")`, the method still uses `findByEmail...`.

### Queries Declared with `@Query`

For complex queries or overly long method names, you can declare JPQL:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> lookupByEmail(@Param("email") String email);
```

JPQL uses entity names and Java properties. If you need SQL using table and column names, use `nativeQuery = true`. Both query forms can still be declared in a selective Repository or a subinterface of a base interface.

## 6. Configuring Repository Scanning

In Spring Boot, Repositories are usually scanned automatically based on the `@SpringBootApplication` class's package. Place the main class in the root package so child interfaces and entities in subpackages are easily discovered.

If you need to specify packages explicitly, you can use `@EnableJpaRepositories`:

```java
@SpringBootApplication
@EnableJpaRepositories(basePackages = "com.example.repository")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

When configuring multiple persistence units or multiple databases, point to the right `entityManagerFactoryRef` and `transactionManagerRef`. `@NoRepositoryBean` only excludes intermediate interfaces from bean creation; it does not replace package scan configuration.

## 7. Runnable Example with Java 17+, Spring Boot, and H2

This example creates a read-only base interface. Data is created using `EntityManager` in a separate Service; the Repository exposes only `findById`, `findAll`, and an email lookup query.

### Project Structure

```text
selective-repository/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/selective/
        │   ├── SelectiveRepositoryApplication.java
        │   ├── Customer.java
        │   ├── ReadOnlyRepository.java
        │   ├── CustomerRepository.java
        │   ├── CustomerWriter.java
        │   └── CustomerReader.java
        └── resources/
            └── application.properties
```

### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>selective-repository</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/resources/application.properties

```properties
spring.datasource.url=jdbc:h2:mem:selective;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` is suitable for an ephemeral H2 database in an example. Production projects should manage schemas using Flyway or Liquibase and choose a `ddl-auto` setting appropriate for the environment.

### Customer.java

```java
package com.example.selective;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 180)
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
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

    @Override
    public String toString() {
        return "Customer{id=" + id + ", name=" + name + ", email=" + email + "}";
    }
}
```

### ReadOnlyRepository.java

```java
package com.example.selective;

import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadOnlyRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);

    List<T> findAll();
}
```

### CustomerRepository.java

```java
package com.example.selective;

import java.util.Optional;

public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

### CustomerWriter.java

```java
package com.example.selective;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerWriter {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void create(String name, String email) {
        entityManager.persist(new Customer(name, email));
    }
}
```

### CustomerReader.java

```java
package com.example.selective;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReader {
    private final CustomerRepository repository;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer findByEmail(String email) {
        return repository.findByEmailIgnoreCase(email).orElseThrow();
    }

    @Transactional(readOnly = true)
    public int countAll() {
        List<Customer> customers = repository.findAll();
        return customers.size();
    }
}
```

Application-declared query methods do not receive default transaction configuration in every situation. Placing `@Transactional(readOnly = true)` in the Service makes the transaction boundary of read operations explicit. Operations within the same Service method can share the same transaction.

### SelectiveRepositoryApplication.java

```java
package com.example.selective;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SelectiveRepositoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SelectiveRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerWriter writer, CustomerReader reader) {
        return args -> {
            writer.create("An", "an@example.com");

            Customer found = reader.findByEmail("AN@example.com");
            System.out.println("Found: " + found);
            System.out.println("Total customers: " + reader.countAll());
        };
    }
}
```

### Running the Program

```bash
mvn spring-boot:run
```

With a fresh H2 database, the application output looks like:

```text
Found: Customer{id=1, name=An, email=an@example.com}
Total customers: 1
```

Key observation: `CustomerRepository` does not extend `CrudRepository` or `JpaRepository`, yet Spring Data still creates a proxy. `findById` and `findAll` are handled by the repository base implementation; `findByEmailIgnoreCase` is parsed into a query. The application can call the three exposed methods, while `save` and `delete` do not exist on the `CustomerRepository` type.

## 8. When to Use `@RepositoryDefinition` vs. a Base Interface?

| Need | Suitable Choice |
| --- | --- |
| A single Repository needs to expose a few methods | `@RepositoryDefinition` or extend `Repository<T, ID>` directly and declare signatures. |
| Multiple Repositories need the same minimal set of operations | Generic base interface annotated with `@NoRepositoryBean`. |
| Multiple Repositories have different access levels, e.g., read-only vs. read/write | Create separate base interface branches like `ReadOnlyRepository` and `ReadWriteRepository`. |
| Custom behavior needs to be added to some Repositories | Use repository fragments with a corresponding interface and implementation. |
| The shared base implementation for multiple Repositories needs to change | Configure a custom repository base class, e.g., a class extending `SimpleJpaRepository`. |

`@RepositoryDefinition` and base interfaces decide which APIs are exposed. Repository fragments and custom base classes address implementing custom behavior; they solve different problems.

### Distinguishing Custom Base Interfaces from Custom Base Classes

- **Custom base interface:** declares method signatures and capabilities callers can invoke. `@NoRepositoryBean` prevents intermediate generic interfaces from being turned into standalone beans.
- **Repository fragment:** adds a dedicated group of behaviors by composing a custom interface and implementation into the target Repositories.
- **Custom base class:** replaces or extends the base implementation class, typically extending `SimpleJpaRepository` and registered via the `repositoryBaseClass` configuration.

You do not need to create a custom base class just to hide `save` or `delete`; selective interfaces already solve the exposed API part.

## 9. Version and Design Notes

1. **Pagination and CRUD:** starting from Spring Data 3.x, `PagingAndSortingRepository` no longer extends `CrudRepository`. If both groups of methods are needed, explicitly extend both interfaces appropriate for your version.
2. **List return types:** `List<T> findAll()` works well with JPA and `SimpleJpaRepository`. If building an abstraction shared across multiple Spring Data stores, consider `Iterable<T>` for compatibility with basic CRUD signatures.
3. **Generic ID must be accurate:** if an entity uses `Long` as its primary key, declare `Repository<Customer, Long>`; do not mistakenly use a type like `String`.
4. **Property names are Java names:** derived queries rely on entity properties, not directly on database column names.
5. **Foundational methods have reserved names:** `findById` always has lookup-by-identifier semantics. If you want to query another property with the same name, use a distinct method name.
6. **Do not forget `@NoRepositoryBean`:** apply it to generic base interfaces that are not concrete repositories.
7. **Do not overuse base interfaces:** put only genuinely shared operations in them. An oversized base interface forces unnecessary APIs onto every child Repository.
8. **A narrow API does not replace authorization:** control data access permissions in services, authorization, and database permissions when needed; omitting `delete` only prevents calls through that interface type.
9. **Transactions at the right layer:** place transactions per business unit in Services; do not assume every declared query method automatically gets a transaction.

## 10. Checklist When Creating a Selective Repository

- Identify the entity type and ID type.
- List the exact methods to expose: read, save, delete, pagination, or custom queries.
- If there is only one Repository, consider `@RepositoryDefinition` or `Repository<T, ID>` directly.
- If multiple Repositories share an API, create a generic base interface and annotate it with `@NoRepositoryBean`.
- Place derived queries or `@Query` on concrete interfaces according to domain needs.
- Place transactions in Services for read/write use cases requiring clear boundaries.
- Check package scanning and ensure Spring creates beans for concrete interfaces.
- Compile and run the application to confirm every method signature is implemented properly by Spring Data.

Core takeaway: **`Repository<T, ID>` is the minimal marker; `@RepositoryDefinition` declares domain/ID via annotation; a generic base interface with `@NoRepositoryBean` enables reusing a selected set of methods.** Expose only the capabilities a module needs, and add custom behavior via fragments or a base class only when truly necessary.
