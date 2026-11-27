# Defining JPQL with @NamedQuery and @NamedQueries

## Objectives

`@NamedQuery` and `@NamedQueries` allow declaring fixed-name JPQL queries in entity metadata. Instead of writing JPQL strings at every call site, the application defines the query once and invokes it by name. Spring Data JPA can also automatically look up a named query corresponding to a method name in a Repository.

- `@NamedQuery`: declares a single named JPQL query.
- `@NamedQueries`: groups multiple `@NamedQuery` declarations on the same entity.
- `EntityManager.createNamedQuery(...)`: executes a named query directly with JPA.
- Spring Data JPA: automatically binds a named query to a repository method by naming convention.

This approach is useful when a query is stable, reused across multiple places, or when you need to separate query definitions from calling code. A named query is static JPQL: parameters can vary per invocation, while the query structure is predefined.

## 1. What is a named query?

A named query is a query given a unique name within a persistence unit. The name is used to reference the query when executing it. With `@NamedQuery`, the `query` string is JPQL, so it uses entity names and Java properties rather than SQL table/column names.

For example, an entity `Book` has properties `title` and `category`:

```java
@Entity
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
public class Book {
    // entity fields
}
```

In the declaration above:

- `name` is the identifier name of the named query.
- `query` is the JPQL parsed by the provider according to the entity mapping.
- `Book` is the entity name.
- `b` is the alias.
- `b.title` is the Java property.
- `:title` is a named parameter that will be bound to a value at runtime.

`@NamedQuery` is placed at the class level, typically on the entity that the query targets. It is metadata of the persistence unit, not an annotation placed on a Repository method.

## 2. @NamedQuery and @NamedQueries

### Declaring a single query with @NamedQuery

If an entity only needs one named query, use `@NamedQuery` directly:

```java
@Entity
@Table(name = "books")
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;
}
```

### Grouping multiple queries with @NamedQueries

When an entity has multiple named queries, use `@NamedQueries` as a container:

```java
@Entity
@Table(name = "books")
@NamedQueries({
    @NamedQuery(
        name = "Book.findByTitle",
        query = "select b from Book b where b.title = :title"
    ),
    @NamedQuery(
        name = "Book.findByCategory",
        query = "select b from Book b "
              + "where b.category = :category order by b.title asc"
    ),
    @NamedQuery(
        name = "Book.countByCategory",
        query = "select count(b) from Book b where b.category = :category"
    )
})
public class Book {
    // entity fields
}
```

`@NamedQueries` does not create a different kind of query; it simply allows declaring multiple `@NamedQuery` annotations in the same location. Each query still has its own name and its own JPQL body.

### Naming queries

You should name queries following a recognizable convention:

- Start with the entity name, for example `Book`.
- Use a dot to separate the entity and the purpose, for example `Book.findByTitle`.
- Use a name that describes the condition or result, for example `Book.findPublishedByCategory`.
- Ensure the name does not collide with any other named query in the same persistence unit.

A query name is distinct from a Java method name. If you want Spring Data to automatically look up a named query for a method, you must follow the binding convention presented in a later section.

## 3. JPQL inside NamedQuery

JPQL queries entities and persistent attributes:

```jpql
select b
from Book b
where b.category = :category
order by b.title asc
```

Do not write the table name `books` or the schema column name `category` if they differ from the entity/property. For example, the database column might be `book_category`, yet JPQL still uses `b.category` if the Java property is named `category`.

A named query can return entities, scalar values, or DTO projections:

```jpql
select b from Book b where b.title = :title
```

```jpql
select count(b) from Book b where b.category = :category
```

```jpql
select new com.example.BookSummary(b.id, b.title)
from Book b
where b.category = :category
```

With a DTO constructor expression, the DTO class must have a constructor matching the order and data types of the selected expressions.

### Parameters in JPQL

Named parameters use a colon:

```jpql
select b from Book b where b.title = :title
```

Positional parameters use a sequence number:

```jpql
select b from Book b where b.title = ?1
```

Choose one parameter style consistently within a query. Do not concatenate input strings to build JPQL:

```java
// Unsafe and prone to syntax errors
String jpql = "select b from Book b where b.title = '" + title + "'";
```

Bind parameters instead so the provider handles values and data types:

```java
query.setParameter("title", title);
```

Parameters are used for values, not to substitute entity names, property names, operators, or sort directions. If the query structure needs to change, use a different query, Criteria API, Specification, or a whitelisted query-building mechanism.

## 4. Executing a named query with EntityManager

JPA provides `createNamedQuery` to retrieve a query by name:

```java
List<Book> books = entityManager
        .createNamedQuery("Book.findByTitle", Book.class)
        .setParameter("title", "Spring Data JPA")
        .getResultList();
```

The `Book.class` argument creates a typed query, enabling compile-time type checking for the result. `getResultList()` returns an empty list if no matching rows exist.

For count queries:

```java
Long total = entityManager
        .createNamedQuery("Book.countByCategory", Long.class)
        .setParameter("category", "BOOK")
        .getSingleResult();
```

`count` always returns a numeric value, even when no rows match; in that case the result is `0`. For queries returning a single entity, `getSingleResult()` can throw `NoResultException` if there is no result or `NonUniqueResultException` if there is more than one result. Choose an API and return type suited to the query's cardinality.

### Using untyped queries

You can use the overload without passing a result class:

```java
Query query = entityManager.createNamedQuery("Book.findByTitle");
query.setParameter("title", "Spring Data JPA");
List<?> results = query.getResultList();
```

A typed query is usually easier to read and more type-safe when the result type is already known.

## 5. Spring Data JPA automatic NamedQuery lookup by Repository method name

Spring Data JPA can bind a repository method to a named query without calling `EntityManager` directly. The naming convention is:

```text
<EntitySimpleName>.<repositoryMethodName>
```

Example:

```java
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
```

Repository:

```java
public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(@Param("title") String title);
}
```

When Spring Data processes `findByTitle`, it looks for the named query `Book.findByTitle`. If found, the declared query is used. If there is no matching named query, Spring Data may fall back to deriving a query from the method name according to the configured query lookup strategy.

Therefore, if the method is `findByCategory`, the named query needs to be named `Book.findByCategory`. A query with a different name—even with similar content—will not be automatically matched to the method.

### Using @Param to explicitly bind parameter names

In repository methods, you should specify `@Param` explicitly to match the JPQL parameter name:

```java
List<Book> findByCategory(@Param("category") String category);
```

JPQL uses `:category`, so `@Param("category")` specifies which Java argument is bound to that parameter. This prevents the code from depending on whether parameter name metadata is preserved during compilation.

### Named queries and @Query

If a repository method has `@Query`, that declaration takes precedence over a named query with the same name. For example:

```java
@Query("select b from Book b where b.title = :title")
List<Book> findByTitle(@Param("title") String title);
```

The method above uses the content of `@Query`. If you want to use `@NamedQuery`, do not place `@Query` on the same method.

## 6. Named queries can be used for SELECT, UPDATE, and DELETE

`@NamedQuery` accepts any JPQL query string, not just SELECT. JPQL also supports bulk UPDATE and DELETE:

```java
@NamedQuery(
    name = "Book.renameCategory",
    query = "update Book b set b.category = :target "
          + "where b.category = :source"
)
```

Execute a bulk update using `executeUpdate()` within a transaction:

```java
int updated = entityManager
        .createNamedQuery("Book.renameCategory")
        .setParameter("source", "OLD")
        .setParameter("target", "BOOK")
        .executeUpdate();
```

Bulk UPDATE/DELETE statements run directly against the database and do not synchronize individual entities currently managed in the persistence context. Entities loaded earlier may retain stale state. After a bulk operation, consider calling `entityManager.clear()` or refreshing entities that need further use; only clear when you understand the impact on unflushed changes.

Bulk operations require an appropriate transaction. In Spring, place `@Transactional` on the service method; do not execute data modifications inside a `readOnly = true` read-only flow.

## 7. Named queries, native queries, and dynamic queries

These three approaches serve different purposes:

| Approach | Language | When appropriate |
| --- | --- | --- |
| `@NamedQuery` / `@NamedQueries` | JPQL | Stable queries that are named and reused. |
| `@NamedNativeQuery` | Database SQL | Need database-specific SQL features, CTEs, window functions, or schema-specific syntax. |
| `@Query` / Criteria / Specification | JPQL or query-building API | Queries tied to a repository method or with structure varying by conditions. |

`@NamedQuery` is not native SQL. If a query needs SQL table/column names and database-specific syntax, consider `@NamedNativeQuery` or an appropriate native query.

A named query has fixed content; parameter values can change, but you cannot bind a column name or `ORDER BY` direction as a parameter. For dynamic sorting or complex optional filters, consider `Sort`, Specification, or the Criteria API instead of trying to concatenate JPQL strings.

## 8. Lifecycle and validation of NamedQuery

A named query is persistence unit metadata. The JPA provider typically parses and validates JPQL when initializing `EntityManagerFactory`; a query with an invalid entity name, property, parameter, or syntax can cause the application to fail immediately at startup.

The advantage of early detection is that query errors are less likely to surface only when a rare business branch is invoked. However, the completeness of validation and the exact time of detection still depend on the provider.

Rules to follow:

- Each named query has a unique name within the persistence unit.
- Entity and property names in JPQL must match the mapping.
- Parameter names in JPQL must match `setParameter` or `@Param`.
- The result type must match the repository return type or result class.
- Queries should include `ORDER BY` if the business logic requires deterministic ordering.
- Avoid overly broad queries or fetching unnecessary associations.

## 9. Runnable example with Java 17+, Spring Boot, and H2

This example declares multiple named queries on the `Book` entity and invokes them through a Spring Data repository. The project uses Spring Boot 3.4.5, Java 17, and an H2 in-memory database.

### Project structure

```text
named-query-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/namedquery/
        │   ├── NamedQueryApplication.java
        │   ├── Book.java
        │   └── BookRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

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
    <artifactId>named-query-demo</artifactId>
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

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:namedqueries;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Book.java`

```java
package com.example.namedquery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedQueries;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
@NamedQueries({
    @NamedQuery(
        name = "Book.findByTitle",
        query = "select b from Book b where b.title = :title"
    ),
    @NamedQuery(
        name = "Book.findByCategory",
        query = "select b from Book b "
              + "where b.category = :category order by b.title asc"
    ),
    @NamedQuery(
        name = "Book.countByCategory",
        query = "select count(b) from Book b where b.category = :category"
    ),
    @NamedQuery(
        name = "Book.findPublished",
        query = "select b from Book b where b.published = true order by b.title asc"
    )
})
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private boolean published;

    protected Book() {
    }

    public Book(String title, String category, boolean published) {
        this.title = title;
        this.category = category;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }
}
```

### `BookRepository.java`

```java
package com.example.namedquery;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(@Param("title") String title);

    List<Book> findByCategory(@Param("category") String category);

    long countByCategory(@Param("category") String category);

    List<Book> findPublished();
}
```

Spring Data looks for queries named `Book.findByTitle`, `Book.findByCategory`, `Book.countByCategory`, and `Book.findPublished`. Because they are already declared in `@NamedQueries`, the repository uses the corresponding JPQL instead of deriving queries from method names.

### `NamedQueryApplication.java`

```java
package com.example.namedquery;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NamedQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Book("JPA Basics", "BOOK", true),
                    new Book("Spring Data JPA", "BOOK", true),
                    new Book("Hibernate Guide", "BOOK", false),
                    new Book("Java Fundamentals", "COURSE", true)
            ));
            repository.flush();

            System.out.println("Find by title: "
                    + titles(repository.findByTitle("Spring Data JPA")));
            System.out.println("Find BOOK category: "
                    + titles(repository.findByCategory("BOOK")));
            System.out.println("Count BOOK: " + repository.countByCategory("BOOK"));
            System.out.println("Published: " + titles(repository.findPublished()));
        };
    }

    private static String titles(List<Book> books) {
        return books.stream()
                .map(Book::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Running the application

```bash
mvn spring-boot:run
```

Output printed by the application:

```text
Find by title: Spring Data JPA
Find BOOK category: Hibernate Guide, JPA Basics, Spring Data JPA
Count BOOK: 3
Published: JPA Basics, Java Fundamentals, Spring Data JPA
```

Results are sorted according to the JPQL `ORDER BY` declared in the named query. The `Book.findPublished` query demonstrates that the repository method `findPublished()` can use a named query even when the method name does not fully describe the JPQL predicate.

### Calling the same named query directly via EntityManager

If you need to use the JPA API instead of a repository method, you can invoke the exact same named query:

```java
List<Book> books = entityManager
        .createNamedQuery("Book.findByCategory", Book.class)
        .setParameter("category", "BOOK")
        .getResultList();
```

This is the same JPQL definition on the entity; there is no need to duplicate the query string in the Service.

## 10. When should NamedQuery be used?

A named query is appropriate when:

- A stable query is called from multiple locations.
- You want JPQL defined centrally alongside entity metadata.
- You want Spring Data repositories to automatically resolve queries by method naming convention.
- You want early detection of JPQL errors when the persistence unit initializes.
- You want to reuse queries without repeating JPQL strings across multiple services.

You do not need to convert every query into a named query. For one-off queries, highly dynamic queries, or logic depending on many runtime conditions, `@Query`, Specification, or the Criteria API may be easier to maintain.

## 11. Common pitfalls

1. **Wrong named query name:** repository method `findByTitle` requires the conventional name `Book.findByTitle`; a query with a different name will not bind automatically.
2. **Confusing entity name with table name:** JPQL uses entity names, not SQL table names.
3. **Confusing property with column:** use `b.category` if the Java property is named `category`, even if the database column has a different name.
4. **Wrong parameter name:** `:title` must match `setParameter("title", ...)` or `@Param("title")`.
5. **Adding @Query and expecting the named query to run:** `@Query` on a repository method takes precedence.
6. **Duplicate query names in the persistence unit:** namespace names by entity and purpose.
7. **Using getSingleResult for multi-row queries:** choose `getResultList`, `Optional`, or limit results appropriately.
8. **Putting native SQL in @NamedQuery:** `@NamedQuery` is for JPQL; native SQL requires `@NamedNativeQuery`.
9. **Changing JPQL without checking results:** run integration tests to verify parameters, return types, ordering, and join semantics.
10. **Bulk updates leaving stale entities in the persistence context:** intentionally clear or refresh after `executeUpdate()`.

## 12. Testing NamedQuery

You should have integration tests that initialize the persistence context and a test database to verify:

- Query names are registered and the provider accepts the JPQL.
- Named parameters are bound correctly.
- Results have the expected type and count.
- `ORDER BY` produces deterministic ordering.
- Count queries return the correct `Long`.
- Repository methods actually resolve the named query by convention.
- Empty results and boundary data are handled properly.

Test against the same database type as production when queries depend on dialect, functions, collation, or native features. H2 is useful for examples and fast tests, but does not fully replace integration tests with the target database.

## 13. Best practices

- Use `@NamedQuery` for a single JPQL query and `@NamedQueries` when multiple queries are needed on an entity.
- Name queries following `EntityName.methodName` when you want Spring Data to bind repository methods automatically.
- Use named parameters and `@Param` for explicit binding.
- Use `EntityManager.createNamedQuery` when calling directly from JPA.
- Keep JPQL queries using Java entities/properties; use `@NamedNativeQuery` for raw SQL.
- Do not declare `@Query` on a method if the goal is for the named query to be selected.
- Choose typed queries and return types that match the expected results.
- Verify queries at startup and through integration tests with representative data.

Key takeaway: **`@NamedQuery` gives a name to a JPQL query; `@NamedQueries` groups multiple queries on an entity. EntityManager invokes queries by name, while Spring Data JPA can automatically look up queries using the `EntityName.repositoryMethodName` pattern. Parameters are bound at runtime, but the JPQL structure remains predefined.**