# Default Methods and Wrappers for Nullable Properties

## Objectives

Spring Data JPA supports interface projections to return a focused view of an entity instead of always loading the entire entity. A projection can declare **default methods** to compute display properties from other getters, and can use **nullable wrappers** like `Optional<T>` for properties that may be null.

These two capabilities solve different needs:

- Default methods compute derived values in Java based on the properties already declared on the projection.
- Nullable wrappers safely represent cases where a source property has no value.

For example, the `PersonSummary` projection has `getFirstName()`, `getLastName()`, and `getNickname()`. The default method `getFullName()` concatenates the first and last names; the getter `Optional<String> getNickname()` represents a nullable nickname; `getDisplayName()` chooses the nickname if present, or falls back to the full name.

## 1. How Do Interface Projections Work?

A projection is a return type describing the properties the caller needs to read. With an interface projection, Spring Data creates a proxy implementing the interface and populates values from the entity/query result.

An entity may contain many attributes:

```java
@Entity
public class Person {
    @Id
    private Long id;
    private String firstName;
    private String lastName;
    private String nickname;
    private String email;
    private String address;
}
```

However, a list screen only needs the full name and nickname. You can define a projection:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();
    Optional<String> getNickname();
}
```

Spring Data can create projections from a query method:

```java
List<PersonSummary> findByLastName(String lastName);
```

The caller receives `PersonSummary` without depending on the full `Person` entity. Projections fit when the read layer only needs a specific set of attributes, such as lists, search tables, or response views.

### Closed Projections

A projection is considered closed when its accessors correspond to properties of the target entity. Spring Data knows the required properties and can optimize the query to fetch only the needed data.

In the example, `firstName`, `lastName`, and `nickname` are properties of `Person`. The default methods introduced in the next section only invoke these accessors, preserving a closed projection design.

A projection does not always mean a SQL statement selecting only three columns in every scenario. Custom queries, nested projections, providers, and mappings can affect the final SQL. Enable SQL logging to verify when optimizing performance.

## 2. Default Methods in Projections

Java interfaces allow declaring methods with a body using the `default` keyword. Spring Data projections can use these methods to compute values from other accessors in the same interface.

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

`getFullName()` does not require a `fullName` column in the database. When the caller invokes this method, the default method body executes in Java and retrieves data via `getFirstName()` and `getLastName()`.

### Design Rules for Default Methods

- Only call accessors declared on the projection to read the values needed for computation.
- Keep logic brief, deterministic, and easy to test, such as concatenating names, formatting labels, or choosing fallback values.
- Do not assume the projection proxy can directly access private fields of the entity.
- Do not place database queries, write operations, or infrastructure-dependent logic inside default methods.
- If a formula is too complex or requires external services, move the logic to a service/mapper or use an appropriate DTO.

Inside a default method, `this` is the projection proxy. When calling `getFirstName()`, the call is handled by the proxy and returns the property value fetched by the query.

### Default Methods Do Not Create Columns or SQL Expressions

`getFullName()` is computed in Java after the projection has data. It does not create a `full_name` column, nor is it equivalent to a JPQL `concat(...)` running in the database.

If you need to sort or filter by a computed expression in the database, write an appropriate JPQL/SQL projection, use a query expression, or store a derived property according to your data design. You cannot reference a default method name as if it were a persistent entity property in a derived query.

## 3. Combining Default Methods with Optional

Suppose `nickname` can be null. The projection can declare a getter returning `Optional<String>`:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();
    Optional<String> getNickname();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }

    default String getDisplayName() {
        return getNickname()
                .filter(value -> !value.isBlank())
                .orElseGet(this::getFullName);
    }
}
```

When the source property `nickname` is null, Spring Data returns `Optional.empty()`. When the property has a value, the getter returns an `Optional` containing that value. The default method `getDisplayName()` can handle both cases without explicit null checks.

Example:

| firstName | lastName | nickname in database | getNickname() | getDisplayName() |
| --- | --- | --- | --- | --- |
| An | Nguyen | An | `Optional[An]` | An |
| Binh | Nguyen | `NULL` | `Optional.empty()` | Binh Nguyen |
| Cuong | Nguyen | Cún | `Optional[Cún]` | Cún |

In this example, an empty or whitespace-only nickname is also treated as having no nickname thanks to `filter`. If the business rules consider empty strings meaningful data, remove the filter condition.

### Ways to Handle Optional

```java
String nickname = summary.getNickname().orElse("No nickname set");

String displayName = summary.getNickname()
        .filter(value -> !value.isBlank())
        .orElseGet(summary::getFullName);

summary.getNickname().ifPresent(value -> log.info("Nickname: {}", value));
```

- `orElse(value)` returns a default value when the `Optional` is empty; the argument expression is evaluated before the call.
- `orElseGet(supplier)` invokes the supplier only when the `Optional` is empty.
- `map(function)` transforms the value if present.
- `ifPresent(action)` runs an action when a value is present.
- `orElseThrow()` or `orElseThrow(supplier)` is used when a missing value is an error.

Do not call `.get()` indiscriminately. If a value may be absent, handle it with `orElse`, `orElseGet`, `map`, `ifPresent`, or `orElseThrow` according to the business contract.

## 4. Supported Nullable Wrappers

Spring Data Commons supports several wrappers for getters in projections. If the underlying property is null, the getter returns an empty wrapper; if the property has a value, the getter returns a wrapper containing the value.

| Wrapper | Getter type |
| --- | --- |
| Java 8+ | `java.util.Optional<T>` |
| Guava | `com.google.common.base.Optional<T>` |
| Scala | `scala.Option<T>` |
| Vavr | `io.vavr.control.Option<T>` |

Java `Optional` is usually the simplest choice since it is built into the JDK. The remaining wrappers require their corresponding libraries on the classpath and support from your Spring Data version.

### Using Wrappers for Other Data Types

If a numeric property can be null, you can declare a projection getter using a boxed type inside `Optional`:

```java
Optional<Integer> getAge();
Optional<BigDecimal> getCreditLimit();
```

Do not use primitives like `int` to represent a value that may be absent: primitives do not have a null state. `OptionalInt`, `OptionalLong`, and `OptionalDouble` are not in the list of supported projection wrappers above; use `Optional<Integer>`, `Optional<Long>`, or `Optional<Double>` when a nullable wrapper is needed.

### Wrappers Belong Only on Projection Accessors

The entity can keep normal persistent attributes:

```java
@Column
private String nickname;
```

Only the projection declares:

```java
Optional<String> getNickname();
```

There is no need to change the entity field to `Optional<String>`. Here, the wrapper is the read contract of the projection; the entity property continues to be mapped by JPA according to the appropriate data type.

## 5. Distinguishing Property Optional vs. Query Optional

The following two cases have different meanings:

```java
Optional<PersonSummary> findByEmail(String email);
```

The repository return type states that **a `PersonSummary` might not be found** by email. `Optional.empty()` means the query found no matching row.

Meanwhile:

```java
public interface PersonSummary {
    Optional<String> getNickname();
}
```

The projection getter states that **a `Person` row was found, but its `nickname` property may be null**.

For example, you can receive a non-empty `Optional<PersonSummary>` while `summary.getNickname()` is `Optional.empty()`. That person exists; they simply do not have a nickname yet.

Do not use `Optional<List<PersonSummary>>` for multi-result queries. Repositories return `List<PersonSummary>` and use an empty list when no rows match; property-level `Optional` values can still appear inside each projection.

## 6. Default Methods vs. @Value and SpEL

Spring Data projections also allow using `@Value` to compute properties with SpEL:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

This is an open projection because the expression can access the target object. Spring Data cannot fully infer which attributes will be used inside the expression, so it may not optimize column selection like a closed projection.

Comparison:

| Criterion | Default method | `@Value` / SpEL |
| --- | --- | --- |
| Data source | Accessors of the projection itself | Target object, method arguments, or Spring beans via expression |
| Suitable logic | Simple calculations from declared getters | More complex expressions or bean calls |
| Projection type | Can keep the projection closed | Makes it an open projection |
| Refactoring safety | Java compiler checks method calls | SpEL strings must be verified at runtime |

For simple calculations like concatenating names or falling back from `Optional`, default methods are usually easier to read and safer to refactor. Use SpEL when access to `target` or beans is genuinely required.

## 7. Using Default Methods with Repository Projections

A repository method can return an interface projection directly:

```java
public interface PersonRepository extends JpaRepository<Person, Long> {
    List<PersonSummary> findByLastNameOrderByFirstNameAscIdAsc(String lastName);
}
```

Spring Data creates a projection for each row. The caller uses raw getters, nullable wrappers, and default methods as a unified view object:

```java
for (PersonSummary person : repository.findByLastNameOrderByFirstNameAscIdAsc("Nguyen")) {
    System.out.println(person.getDisplayName());
}
```

A query method can return `Optional<PersonSummary>` if the condition guarantees at most one row, or `List<PersonSummary>` if multiple people may match. This is query cardinality, independent of whether a getter inside the projection returns `Optional`.

### Projections from @Query

Interface projections can also be used with `@Query`, as long as the query returns aliases/properties matching the accessors:

```java
@Query("select p from Person p where p.lastName = :lastName")
List<PersonSummary> searchByLastName(@Param("lastName") String lastName);
```

With interface projections, Spring Data maps returned attributes to accessors by property name. For native queries or custom alias selections, specify matching aliases and test against the real database.

## 8. Limitations and Design Considerations

1. **Default methods should rely only on projection accessors.** Do not assume direct access to the entity or private fields.
2. **Values computed by default methods are produced in Java.** Do not use them as JPQL properties to filter or sort in the database.
3. **Use wrappers for nullable properties.** If the backing value is null, the wrapper returns empty and the caller must handle it.
4. **Do not confuse query `Optional` with property `Optional`.** One represents a row that may not exist; the other represents a property in a row that may be null.
5. **Keep entity fields as normal persistent types.** Apply wrappers at the projection boundary instead of changing JPA fields to `Optional`.
6. **Do not use `Optional` for collection projections.** An empty `List` already indicates no elements.
7. **Do not use primitives for nullable attributes.** Choose appropriate boxed types or nullable wrappers.
8. **SpEL can turn a projection into an open projection.** Use default methods if you only need to combine accessors.
9. **Avoid complex business logic in projections.** Put rules that depend on state, repositories, or other services in the service/domain layer.
10. **Inspect actual queries.** Projections can reduce read data, but nested associations and custom queries can still introduce joins or load extra columns.

## 9. Runnable Example with Java 17+, Spring Boot, and H2

This example saves three people with the last name `Nguyen`: one whose nickname equals their first name, one without a nickname, and one with a distinct nickname. The repository returns an interface projection; default methods compute the full name and display name, while `Optional<String>` represents the nullable nickname.

### Project Structure

```text
projection-default-method/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/projection/
        │   ├── ProjectionApplication.java
        │   ├── Person.java
        │   ├── PersonSummary.java
        │   └── PersonRepository.java
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
    <artifactId>projection-default-method</artifactId>
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
spring.datasource.url=jdbc:h2:mem:projectiondb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Person.java`

```java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String firstName;

    @Column(nullable = false, length = 80)
    private String lastName;

    @Column(length = 80)
    private String nickname;

    protected Person() {
    }

    public Person(String firstName, String lastName, String nickname) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.nickname = nickname;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getNickname() {
        return nickname;
    }
}
```

### `PersonSummary.java`

```java
package com.example.projection;

import java.util.Optional;

public interface PersonSummary {
    String getFirstName();

    String getLastName();

    Optional<String> getNickname();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }

    default String getDisplayName() {
        return getNickname()
                .filter(value -> !value.isBlank())
                .orElseGet(this::getFullName);
    }
}
```

### `PersonRepository.java`

```java
package com.example.projection;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository extends JpaRepository<Person, Long> {
    List<PersonSummary> findByLastNameOrderByFirstNameAscIdAsc(String lastName);
}
```

### `ProjectionApplication.java`

```java
package com.example.projection;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ProjectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProjectionApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PersonRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Person("An", "Nguyen", "An"),
                    new Person("Binh", "Nguyen", null),
                    new Person("Cuong", "Nguyen", "Cún")
            ));
            repository.flush();

            List<PersonSummary> people =
                    repository.findByLastNameOrderByFirstNameAscIdAsc("Nguyen");

            for (PersonSummary person : people) {
                String nickname = person.getNickname().orElse("(none)");
                System.out.println(person.getFullName()
                        + " | nickname=" + nickname
                        + " | display=" + person.getDisplayName());
            }
        };
    }
}
```

### Running the Application

```bash
mvn spring-boot:run
```

Stdout:

```text
An Nguyen | nickname=An | display=An
Binh Nguyen | nickname=(none) | display=Binh Nguyen
Cuong Nguyen | nickname=Cún | display=Cún
```

Result explanation:

- `An` has a nickname, so `getDisplayName()` returns the nickname.
- `Binh` has a null nickname, so `getNickname()` is `Optional.empty()`; the default method falls back to `getFullName()`.
- `Cuong` has the nickname `Cún`, so the display name uses that value.

Default methods execute on the projection proxy and call back into the accessors. No `fullName` or `displayName` columns are needed in the `people` table.

## 10. Testing Projections and Nullable Wrappers

Integration tests should use a test database to confirm that Spring Data actually builds the projection and converts nulls into empty wrappers:

```java
@DataJpaTest
class PersonRepositoryTest {
    @Autowired
    private PersonRepository repository;

    @Test
    void wrapsNullPropertyAndRunsDefaultMethods() {
        repository.saveAndFlush(new Person("Binh", "Nguyen", null));

        PersonSummary result = repository
                .findByLastNameOrderByFirstNameAscIdAsc("Nguyen")
                .get(0);

        assertThat(result.getNickname()).isEmpty();
        assertThat(result.getFullName()).isEqualTo("Binh Nguyen");
        assertThat(result.getDisplayName()).isEqualTo("Binh Nguyen");
    }
}
```

This is the test body to place in the project's test sources with the corresponding imports and assertions; `spring-boot-starter-test` must be in the test dependencies. Additional tests should cover non-null nicknames, empty strings, whitespace-only strings, and queries with no matching people.

## 11. Common Pitfalls

1. **Returning null from an `Optional` getter:** nullable wrappers provided by Spring Data return `Optional.empty()` when the property is null; callers do not need to check whether the `Optional` itself is null.
2. **Confusing "query not found" with "nullable property":** a repository `Optional<PersonSummary>` being empty means no row exists; `getNickname()` being empty means the row exists but `nickname` is null.
3. **Declaring `Optional` on an entity field:** keep persistent fields as normal Java types like `String`; declare wrappers on projection getters.
4. **Using a default method that calls a field without an accessor:** default methods should call the projection proxy's getters.
5. **Using default methods for overly complex logic:** move that logic to a service/mapper or DTO.
6. **Using `@Value` when simply combining getters:** SpEL turns the projection into an open projection and can reduce column-selection optimization.
7. **Using primitives for nullable attributes:** choose boxed types or nullable wrappers.
8. **Declaring `Optional<List<T>>`:** use `List` and handle an empty list.
9. **Assuming default methods can be used in `WHERE`/`ORDER BY`:** these methods run in Java, not as persistent properties or JPQL expressions.
10. **Failing to test with real nulls:** add integration tests with SQL `NULL` values to verify wrappers and default methods.

## 12. Best Practices

- Use closed interface projections when only a subset of entity attributes is needed.
- Use default methods for simple derived values computed from projection accessors.
- Use `Optional<T>` or a Spring Data-supported nullable wrapper for properties that can be null.
- Keep entity fields as normal persistent types; wrappers are contracts at the projection boundary.
- Distinguish between query-level `Optional` and property-level `Optional`.
- Use `@Value`/SpEL only when target objects or beans are needed, and account for open projection effects.
- Place complex business logic in the service/domain layer.
- Test null, non-null, and empty-string cases; verify SQL when optimizing projections.

Key takeaway: **Default methods compute derived values in Java from the projection's accessors; nullable wrappers such as `Optional<T>` represent source properties that can be null. Together, these two mechanisms keep projections concise, null-safe, and clear about the boundary between queried data and display values.**
