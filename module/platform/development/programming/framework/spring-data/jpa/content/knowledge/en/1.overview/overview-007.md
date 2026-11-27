# Essential Java, SQL, and Spring Prerequisites Before Getting Started

This lesson helps you identify the foundational skills needed before learning Spring Data JPA. Spring Data JPA makes working with relational data more convenient, but to understand repositories, entities, queries, and transactions, you need a solid grasp of three layers of knowledge: Java to model data and write applications, SQL to understand relational databases, and Spring to understand how application components are created and coordinated.

You do not need to master every advanced feature before starting. Focus on the core concepts, learn to read examples, and be able to write a small program on your own.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of Java, SQL, Spring, JPA, Hibernate, and Spring Data JPA in an application.
- Read and write Java classes representing data, using interfaces, generics, collections, exceptions, and basic modern Java features.
- Design simple tables, declare primary keys and foreign keys, and write queries with JOINs, filtering, sorting, and aggregation.
- Understand IoC, Dependency Injection, beans, Spring Boot configuration, and transaction boundaries.
- Recognize the problems JPA solves, while understanding why SQL and transaction knowledge are still necessary.

## 2. The Big Picture: Which Layers Does Data Pass Through?

In a Spring Data JPA application, the processing flow typically looks like:

~~~text
Controller
    ↓
Service
    ↓
Spring Data Repository
    ↓
JPA EntityManager
    ↓
JPA Provider (usually Hibernate)
    ↓
JDBC Driver
    ↓
Relational Database
~~~

Each component has its own responsibility:

- **Java** is the language used to write business logic and model data.
- **Spring Framework** manages objects, dependencies, configuration, and shared services like transactions.
- **JPA** is the Java specification defining how to map Java objects to relational data and manage entity lifecycles.
- **Hibernate** is a popular JPA provider that implements the JPA specification and translates entity operations into SQL.
- **Spring Data JPA** provides the repository layer, reducing data access code and supporting query generation from method names or query declarations.
- **JDBC** is the foundational API for Java to communicate with a database through a driver.
- **Database** stores actual data and executes SQL, constraints, and transactions.

Therefore, Spring Data JPA is not a database and does not replace SQL. When a query is slow or returns wrong data, you still need to understand the executed SQL, table structure, and how the database processes the query.

## 3. Essential Java Foundations

### 3.1. Data Types, Variables, and Null Values

You need to distinguish primitive types from reference types:

- Primitive types like **int**, **long**, and **boolean** store values directly and cannot hold **null**.
- Wrapper types like **Integer**, **Long**, and **Boolean** are objects and can hold **null**.
- **String** is an immutable reference type.
- **BigDecimal** suits monetary calculations or decimal numbers needing exactness; avoid **double** for currency due to binary representation inaccuracies.

The difference between **long** and **Long** is especially important when mapping data. A column may not have a value yet or a new entity may not yet have an assigned ID, so wrapper types are usually more suitable for nullable properties.

### 3.2. Classes, Objects, and Object-Oriented Programming

You need to understand:

- **Class** describes structure and behavior; **object** is a specific instance of a class.
- **Constructor** initializes an object.
- **Encapsulation** protects internal state through access modifiers and methods.
- **Interface** describes a contract; a class can implement one or more interfaces.
- **Inheritance** models an inheritance relationship; **composition** combines objects to build behavior. In business design, composition often reduces rigid coupling.
- **Access modifiers** such as public, protected, private, and package scope determine where members can be accessed.

When working with JPA, you will encounter classes representing entities, repository interfaces, and services. Without understanding classes, objects, constructors, and interfaces, reading these components will be very difficult.

### 3.3. Collections and `equals`/`hashCode` Rules

Know the purpose of common collections:

- **List** preserves order and allows duplicate elements.
- **Set** represents a collection without duplicates according to equality rules.
- **Map** stores key-value pairs; keys must have stable equality and hash rules when used in a map.

You should know when to use each type and understand the contract of **equals()** and **hashCode()**. Two objects considered equal by `equals` must have the same `hashCode`. This rule affects `Set`, `Map`, and how relationships between entities are managed.

For JPA entities, implementing `equals`/`hashCode` requires care because an ID may not exist yet when a new object is created. Do not mechanically copy equality implementations from DTOs or ordinary classes onto entities.

### 3.4. Generics and Interfaces

Generics allow reusing data types while keeping compile-time type checking. For example, **List<Customer>** indicates a list containing `Customer`; **JpaRepository<Customer, Long>** indicates a repository managing the `Customer` entity with an ID type of `Long`.

You should be able to read interface declarations, type parameters, return types, and generic types. This is foundational for understanding Spring Data JPA repositories.

### 3.5. Exceptions and Error Handling

Distinguish:

- **Checked exceptions** must be declared or handled according to Java rules.
- **Unchecked exceptions** extend `RuntimeException` and are not required to be declared in method signatures.
- **try/catch/finally** handles errors where sufficient context exists.
- Do not catch every exception and ignore it; errors should be handled, translated, or propagated intentionally.

In data applications, errors can arise from constraint violations, connection failures, invalid queries, or rolled-back transactions. Understanding exceptions helps you pinpoint which layer failed.

### 3.6. Annotations, Reflection, and Lambdas

Java frameworks use annotations as metadata. For example, **@Service**, **@Repository**, **@Transactional**, and JPA annotations describe the role or behavior of classes, methods, and fields. You do not need to write reflection code yourself at the start, but you should understand that annotations are metadata and frameworks can read that metadata at runtime.

In addition, know lambda syntax, functional interfaces, the Stream API, and `Optional`:

- Lambdas pass behavior as expressions.
- Streams help transform and aggregate in-memory data.
- `Optional` represents a result that may not exist and appears frequently in repository APIs.

Streams process collections already in memory; they do not automatically become SQL queries. For large datasets, filtering and pagination in the database are usually much more efficient than loading everything into memory and filtering with a Stream.

The Java 17+ example below demonstrates collections, Streams, `Optional`, and `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

public class JavaPrerequisiteDemo {
    record Customer(Long id, String name) {}

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer(1L, "An"),
            new Customer(2L, "Binh")
        );

        Optional<Customer> result = customers.stream()
            .filter(customer -> customer.name().equals("An"))
            .findFirst();

        BigDecimal total = List.of(
            new BigDecimal("12.50"),
            new BigDecimal("3.25")
        ).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(result.map(Customer::name).orElse("Not found"));
        System.out.println(total);
    }
}
~~~

Save the code as **JavaPrerequisiteDemo.java**, then run:

~~~bash
javac JavaPrerequisiteDemo.java
java JavaPrerequisiteDemo
~~~

Output:

~~~text
An
15.75
~~~

**record** fits value-only data types such as DTOs or value objects. JPA entities usually require classes with mutable state and their own lifecycle; do not assume any record can replace an entity.

### 3.7. Dates, Times, and Appropriate Data Types

Know the types in **java.time**:

- **LocalDate** represents a date without a time zone.
- **LocalDateTime** represents a date and time without a time zone.
- **Instant** represents an exact point on the timeline, usually suitable when storing absolute timestamps.
- **OffsetDateTime** carries a time-zone offset.

Choose types according to business meaning and standardize time-zone storage and conversion. Avoid `Date` or `Calendar` in new code unless needed for compatibility.

### 3.8. Build Tools and Testing

Know how to read **build.gradle** or **pom.xml**, understand dependencies, versions, and how to run the application. You should also know how to run tests with Gradle or Maven, read compilation errors, and read stack traces.

You do not need advanced build configuration before learning JPA, but you must understand that Spring Boot, Spring Data JPA, Hibernate, and the JDBC driver are dependencies working together.

## 4. SQL and Relational Databases

### 4.1. Tables, Rows, Columns, and Data Types

Relational databases store data in tables. A row represents a record; a column represents an attribute. Each column has a data type and may have constraints.

For example, an e-commerce system may have **customers** and **orders** tables. One customer can have many orders; each order belongs to one customer.

You should know common types like `INTEGER`, `BIGINT`, `VARCHAR`, `DATE`, `TIMESTAMP`, `BOOLEAN`, and `DECIMAL`. Exact type names and behavior may vary across PostgreSQL, MySQL, SQL Server, and other databases.

### 4.2. Primary Keys, Foreign Keys, and Constraints

- **PRIMARY KEY** uniquely identifies each row and cannot be null.
- **FOREIGN KEY** ensures a referenced value exists in the related table.
- **UNIQUE** prevents duplicate values within the constraint scope.
- **NOT NULL** requires a value to be present.
- **CHECK** restricts values according to a condition.
- **DEFAULT** supplies a default value when an insert omits that column.

Database constraints protect data integrity even when data arrives from multiple applications or concurrent streams. Do not rely solely on UI or Java validation.

### 4.3. Categories of SQL Statements

You should distinguish these statement groups:

- **DDL** defines structure, such as `CREATE TABLE` and `ALTER TABLE`.
- **DML** modifies data, such as `INSERT`, `UPDATE`, and `DELETE`.
- **DQL** commonly refers to querying data with `SELECT`.
- **DCL** manages access privileges, such as `GRANT` and `REVOKE`.
- **TCL** controls transactions, such as `COMMIT` and `ROLLBACK`.

Before studying repositories, make sure you can write `SELECT` queries with `WHERE`, `ORDER BY`, `LIMIT`, or the pagination syntax of your database engine.

### 4.4. JOINs and Relationships Between Tables

JOINs are essential because business data is usually split across multiple tables.

- **INNER JOIN** returns only rows matching on both sides.
- **LEFT JOIN** keeps all rows from the left table and fills `NULL` for the right side when no match exists.
- **RIGHT JOIN** keeps all rows from the right table; in practice, it can be rewritten by swapping table order and using `LEFT JOIN`.
- **CROSS JOIN** produces the Cartesian product of two row sets.

Example of creating tables and querying customers along with their orders:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total DECIMAL(12, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

SELECT
    c.id,
    c.name,
    o.id AS order_id,
    o.total
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = 1
ORDER BY o.created_at DESC;
~~~

Being able to read this query helps you understand entity relationships and why a repository query might need a JOIN to fetch related data.

### 4.5. NULL, Filtering, and Aggregation

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. Consequently, comparing a value to `NULL` with `=` does not work like ordinary comparisons. Use **IS NULL** or **IS NOT NULL**.

Know these functions and clauses:

- **COUNT**, **SUM**, **AVG**, **MIN**, **MAX** for aggregation.
- **GROUP BY** to group records.
- **HAVING** to filter after grouping.
- **DISTINCT** to remove duplicate results.
- **IN**, **BETWEEN**, **LIKE**, **EXISTS** to express conditions.

Distinguish `WHERE` from `HAVING`: `WHERE` filters rows before grouping; `HAVING` filters groups after `GROUP BY`.

### 4.6. Normalization and Relationship Design

Normalization reduces data duplication and prevents anomalies on insert, update, or delete. At a basic level, you should know:

- Each table should represent one entity type or one meaningful relationship.
- Do not store comma-separated lists of values in a single column just to avoid creating a relationship table.
- Use foreign keys to express relationships.
- One-to-one, one-to-many, and many-to-many relationships require appropriate table designs.
- For many-to-many relationships, a join table containing foreign keys to both related tables is usually needed.

Proper relational design makes entity mapping and JPA queries much easier to understand.

### 4.7. Indexes and Query Performance

Indexes help the database find data faster in many cases, though they also consume storage and increase write cost. Do not index every column.

You should understand:

- Indexes are generally helpful on columns frequently used in lookups, JOINs, or sorting.
- Column order in a composite index matters.
- A query may not use an index if expressions, data types, or conditions prevent it.
- An execution plan shows how the database intends to execute a query.

When a query is slow, examine the SQL, row counts, indexes, and execution plan instead of merely adding caches or throwing hardware at it.

### 4.8. Transactions and ACID

A transaction groups multiple data operations into a single unit of work. The four ACID properties are:

- **Atomicity**: either all operations succeed, or the transaction is canceled via rollback.
- **Consistency**: a transaction moves data from one valid state to another based on constraints and business rules.
- **Isolation**: concurrent transactions are isolated according to the chosen isolation level.
- **Durability**: committed data is stored permanently according to the database's guarantees.

You should know commit, rollback, and concurrency anomalies such as dirty reads, non-repeatable reads, phantom reads, and lost updates. Each database engine may support different isolation levels and locking behaviors.

### 4.9. Safe SQL

Do not concatenate user input strings directly into SQL queries. Use parameter binding or prepared statements to separate data from query structure. This is a fundamental rule for preventing SQL injection.

## 5. Spring Framework and Spring Boot

### 5.1. IoC and Dependency Injection

**Inversion of Control (IoC)** means the application hands over object creation and management to a container. **Dependency Injection (DI)** is how the container supplies dependencies to the objects that need them.

Instead of a service instantiating a repository with **new**, Spring creates beans and injects dependencies. This reduces coupling and makes substituting dependencies during testing easier.

Constructor injection is usually the clearest option because dependencies are visible directly in the constructor and can be declared `final`:

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

The example assumes `CustomerRepository` is a bean Spring can provide. You do not need to instantiate it yourself with `new`.

### 5.2. Beans and Common Annotations

- **@Component** marks a class to be managed by Spring as a bean.
- **@Service** denotes a business-layer role.
- **@Repository** denotes a data-access role and enables translation of certain persistence-related exceptions.
- **@Controller** and **@RestController** are used in the web layer.
- **@Configuration** and **@Bean** explicitly declare configuration and beans.
- **@Autowired** can be used to inject dependencies; when a class has a single constructor, Spring can use that constructor automatically without the annotation.

Annotations alone do not make every class a bean. The class must fall within component scan scope or be declared via configuration.

### 5.3. Spring Boot, Auto-Configuration, and Configuration

Spring Boot provides application bootstrapping, auto-configuration, and externalized configuration. You should understand:

- The main startup class typically has **@SpringBootApplication**.
- Component scanning locates beans within configured packages.
- Auto-configuration creates default setups based on dependencies and conditions.
- **application.properties** or **application.yml** holds configuration values.
- Profiles such as **dev**, **test**, and **prod** allow switching settings per environment.
- Database connection details like URL, username, and password should be managed via environment configuration or proper secrets, never hard-coded in source code.

Spring Boot reduces manual setup, but when connection errors or missing beans occur, you still need to understand component scanning, dependencies, and configuration.

### 5.4. Layering Controller, Service, and Repository

A simple application typically separates responsibilities as follows:

- **Controller** receives requests, validates communication-level input, and returns responses.
- **Service** enforces business rules, coordinates multiple repositories, and defines transaction boundaries.
- **Repository** performs data access operations.
- **Entity** models persistent state stored in the database.
- **DTO** represents data exchanged across APIs or between layers when needed.

Do not place all business logic in controllers or expose entities as default API responses. Clear separation of responsibilities makes testing and change easier.

### 5.5. Transactions in Spring

You need to know that **@Transactional** marks a transaction boundary. In a Spring Data JPA application, this annotation is typically placed on service methods representing a business operation whose multiple data steps must succeed or roll back together.

Key points to understand before diving deeper:

- Transactions are typically managed via a Spring proxy.
- Self-invocation between methods within the same object may bypass the proxy, so annotations on internally called methods do not always apply as expected.
- Under common defaults, transactions roll back on unchecked exceptions and `Error`; checked exceptions do not automatically trigger rollback unless explicitly configured.
- Transactions should remain short; avoid keeping a transaction open while calling external services or waiting on users.
- Distinguish application-level transaction boundaries from database-level transaction execution.

You do not need to memorize every propagation and isolation option from day one. First understand why a business operation needs to commit or roll back as one unit.

### 5.6. Testing Spring Applications

Know the difference between unit tests and integration tests:

- Unit tests verify a class's logic with dependencies mocked when appropriate.
- Integration tests verify multiple components working together, such as the Spring context, repositories, and database.
- Repository tests should verify queries and mappings against a compatible database.
- Service tests should verify business rules and outcomes when errors occur.

Testing catches mapping, transaction, and query mistakes that compilation alone cannot detect.

## 6. JPA Concepts to Picture First

You do not yet need to know every JPA API detail, but you should understand these terms so later lessons feel cohesive:

- **ORM (Object-Relational Mapping)** maps Java objects to relational tables and relationships.
- **Entity** is a JPA-managed object mapped to stored data.
- **EntityManager** is JPA's central API for managing entities.
- **Persistence Context** tracks managed entities within a unit of work.
- **Dirty Checking** detects changes on managed entities to emit update statements upon synchronization.
- **Flush** synchronizes changes in the persistence context to the database; flush is not synonymous with committing a transaction.
- **Lazy Loading** defers loading related data until accessed; accessing outside an active persistence context can cause errors.
- **N+1 Query** is a situation where one list query is followed by many individual queries to fetch related data.
- **Cascade** specifies that certain entity operations propagate to related entities; choose carefully to avoid unintended data modifications.

These concepts will be studied in depth in the JPA section. At the preparation stage, simply grasp their purpose and the problems they solve.

## 7. Recommended Study Order

If your current knowledge is uneven, study in this order:

1. **Core Java and OOP**: classes, objects, interfaces, collections, generics, exceptions, annotations, and lambdas.
2. **Basic SQL**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `JOIN`, constraints, transactions, and indexes conceptually.
3. **Spring Core**: IoC, DI, beans, component scanning, and configuration.
4. **Spring Boot**: application startup, dependencies, application configuration, and profiles.
5. **JPA Foundations**: entities, mappings, persistence context, `EntityManager`, and relationships.
6. **Spring Data JPA**: repositories, derived queries, JPQL, native queries, pagination, and sorting.
7. **Advanced Practice**: transactions, fetch strategies, N+1, locking, auditing, and query optimization.

Do not wait until every advanced topic is complete before starting JPA. Once you understand Java OOP, basic SQL, and Spring DI, you can start learning JPA while strengthening weaker areas in parallel.

## 8. Preparation Practice Exercise

Try a small exercise on customer and order management:

**Java Part**

- Create a `Customer` class with ID, email, and name.
- Create an `Order` class with ID, total amount, and creation timestamp.
- Use appropriate types for money and date/time.
- Create a simple service accepting a repository via constructor.
- Write unit tests for email or total validation rules.

**SQL Part**

- Create `customers` and `orders` tables.
- Declare primary keys, foreign keys, `UNIQUE`, and `NOT NULL`.
- Insert at least two customers and three orders.
- Write a query fetching orders with customer names using `JOIN`.
- Write a query calculating total order amount per customer using `GROUP BY`.

**Spring Part**

- Create a small Spring Boot application.
- Declare a service and inject dependencies via constructor.
- Read configuration from `application.properties` or `application.yml`.
- Write an integration test verifying the Spring context starts.

Once you understand each part independently, connect them using Spring Data JPA. You will then see what code the repository replaces, what SQL is generated for each operation, and how transactions protect business operations.

## 9. Self-Assessment Checklist

You are ready to begin learning Spring Data JPA when you can answer most items below:

- [ ] I can explain classes, objects, interfaces, and constructors.
- [ ] I can distinguish `List`, `Set`, and `Map`.
- [ ] I understand generics, `equals`/`hashCode`, exceptions, and `Optional` at a basic level.
- [ ] I know to choose `BigDecimal` for money and appropriate `java.time` types for dates and times.
- [ ] I can write `SELECT` statements with `WHERE`, `ORDER BY`, and `JOIN`.
- [ ] I understand primary keys, foreign keys, `UNIQUE`, `NOT NULL`, and one-to-many relationships.
- [ ] I can explain transactions, commit, rollback, and ACID.
- [ ] I understand IoC, Dependency Injection, and beans in Spring.
- [ ] I can distinguish the responsibilities of Controller, Service, and Repository.
- [ ] I understand what `@Transactional` is used for at the business layer.

If a few items are missing, note them down and fill the gaps as you study. If you are not yet comfortable with JOINs, foreign keys, or DI, take time to review them first because they appear continuously in JPA examples.

## 10. Common Misconceptions

1. **Spring Data JPA, JPA, and Hibernate are the same thing**: false. JPA is the specification, Hibernate is a popular implementation, and Spring Data JPA provides the repository abstraction and JPA integration.
2. **Using repositories means no SQL is needed**: false. Repositories reduce data access code, but SQL still governs how the database reads and writes data.
3. **Entities are identical to DTOs**: do not assume this. Entities have persistence lifecycles and relationships; DTOs serve data exchange.
4. **Every operation is automatically inside a transaction**: false. You must understand transaction boundaries, how proxies work, and where to put `@Transactional`.
5. **Using Streams to filter large datasets is always good**: false. When filtering, sorting, and pagination can happen in the database, let the database do it.
6. **Lazy loading always makes an application faster**: false. Accessing relationships inside a loop with lazy loading can trigger N+1 queries.
7. **Having a foreign key in Java is enough**: false. Database constraints are what protect data across all writers to the database.

## 11. Review Questions

**1. Why do you need to understand SQL when using Spring Data JPA?**

Because Spring Data JPA still generates and executes queries on the database. SQL helps you understand JOINs, filtering, pagination, constraints, and query performance.

**2. Why do you need to understand interfaces and generics?**

Repositories are typically declared as interfaces parameterized by the entity and ID type. Understanding both concepts lets you read APIs like `JpaRepository<Customer, Long>`.

**3. What problem do IoC and DI solve?**

They shift the responsibility of creating and supplying dependencies to the container, reducing coupling between classes and making testing easier.

**4. Is flush the same as commit?**

No. Flush synchronizes changes from the persistence context to the database; commit finishes the transaction successfully. A single transaction can flush multiple times before committing.

**5. Do you need to learn Hibernate before Spring Data JPA?**

You do not need deep Hibernate knowledge beforehand. Master Java, SQL, and Spring DI, then learn JPA and gradually understand how providers like Hibernate execute operations.

Once you have completed these foundations, you are ready to start working with entities, repositories, and queries in Spring Data JPA.