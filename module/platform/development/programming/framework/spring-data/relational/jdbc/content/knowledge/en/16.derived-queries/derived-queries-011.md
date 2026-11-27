# Detecting Property or Method Name Errors at Startup

In **Spring Data Relational JDBC**, Spring Data typically generates queries from repository method names when a method does not declare explicit SQL. At application startup, the framework parses method names, looks up the corresponding properties on the domain type, and builds queries. A small typo such as `findByFristName(...)` instead of `findByFirstName(...)` can prevent the repository from initializing and cause application startup to fail.

It is important to distinguish three error categories:

- **Unparseable method name:** the subject, predicate, or keyword violates query derivation syntax.
- **Nonexistent property path:** the method has valid syntax, but references a property missing from the entity.
- **Incorrect SQL/schema or parameter types:** the method is created, but the query fails at execution time.

The first two categories normally surface when Spring creates the repository bean; the last category may only appear when the method is called. This lesson focuses on identifying and fixing method-name and property-path errors before the application runs.

## 1. How Does Spring Data Parse Repository Method Names?

Example repository:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCity(String status, String city);
}
```

For methods without `@Query`, Spring Data can parse the name to identify:

1. **Subject** — query type or result limit, such as `find`, `read`, `get`, `count`, `exists`, `delete`, `Top`, `First`.
2. **Predicate** — conditions after `By`, such as `Email`, `StatusAndCity`.
3. **Property path** — domain property name referenced by each condition.
4. **Operator/keyword** — comparison, logical connector, or sorting, such as `And`, `Or`, `Between`, `GreaterThan`, `OrderBy`.

```text
findTop10ByStatusAndCreatedAtAfterOrderByCreatedAtDesc
│    │    │    │      │            │
│    │    │    │      │            └─ sort: CreatedAt DESC
│    │    │    │      └─ operator: After
│    │    │    └─ property: createdAt
│    │    └─ property: status
│    └─ predicate starts after By
└─ subject: find, limit 10 results
```

The example illustrates how to read a method name. Exact supported keywords depend on the Spring Data module and version; not every Spring Data JPA keyword automatically exists in Spring Data JDBC.

Spring Data Commons uses a query method parser (including `PartTree`) and mapping metadata to interpret method names. When the repository is created, the framework needs to know which entity is queried and which property paths are used to generate SQL.

## 2. Property Name Error: `No property ... found for type ...`

This is the most common error when writing derived queries. Suppose an entity has a `firstName` property:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    private String email;
    private String status;
}
```

Correct method:

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByFirstName(String firstName);
}
```

Misspelled method:

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByFristName(String firstName);
}
```

When Spring creates the repository, it can fail with an error like:

```text
BeanCreationException
  └─ QueryCreationException
       └─ PropertyReferenceException:
            No property 'fristName' found for type 'Customer'
```

The core message is `No property 'fristName' found for type 'Customer'`. `BeanCreationException` is usually just the Spring container wrapper; the root cause sits in `PropertyReferenceException`.

### How to fix

1. Open the entity named in the message (`Customer`).
2. Locate the actual Java property name (`firstName`).
3. Fix the segment after `By` to `FirstName`.
4. Double-check capitalization and property boundaries.
5. Restart the context or run a repository context initialization test.

Do not change the method name to match the SQL column name if the Java property keeps a different name.

## 3. `@Column` Changes the SQL Column Name, Not the Derived Query Property Name

This is a frequent source of confusion:

```java
@Column("first_name")
private String firstName;
```

There are two names at two layers:

| Layer | Name |
|---|---|
| Java domain property | `firstName` |
| SQL column | `first_name` |

Derived queries reference the **Java property**:

```java
findByFirstName(String firstName); // Correct
```

Do not write:

```java
findByFirst_name(String firstName); // Wrong: this is not a Java property
```

If you use `@Query`, the SQL statement instead uses **table/column names**:

```java
@Query("SELECT * FROM customer WHERE first_name = :name")
List<Customer> findCustomersByFirstName(@Param("name") String name);
```

Here, the method name is primarily a Java API name; the actual SQL comes from the annotation. Keep derived queries and annotated queries clearly separated.

## 4. Valid Method Syntax with an Incorrect Property Path

A method can have valid subject and keywords while still referencing a nonexistent property:

```java
List<Customer> findByStatusAndCreatedOnAfter(String status, Instant time);
```

If the entity only has `createdAt` and not `createdOn`, Spring Data cannot resolve the property path. Match the entire predicate against the entity:

```java
private String status;
private Instant createdAt;
```

Correct method:

```java
List<Customer> findByStatusAndCreatedAtAfter(String status, Instant time);
```

Common mistakes:

| Method | Possible issue | How to fix |
|---|---|---|
| `findByFirst_Name(...)` | Entity has `firstName`, not `first` or `name` along the path the parser expects | `findByFirstName(...)` |
| `findByCustomerName(...)` | Entity only has `customer` or `name`, no `customerName` property | Use the exact property path or an explicit query |
| `findByCreated(...)` | Entity has `createdAt`, not `created` | `findByCreatedAt(...)` |
| `findByIsActive(...)` | JavaBeans property may be recognized as `active` if the getter is `isActive()` | Check property metadata; usually use `findByActive(...)` |
| `findByEamil(...)` | Transposed letters in `email` | `findByEmail(...)` |

Method names must reflect the **properties Spring Data sees through mapping metadata**, not just field names a developer recalls from memory. With Lombok, records, or custom getters, check how properties are exposed and how constructor mapping behaves.

## 5. Nested Property Paths and Underscores as Delimiters

Some domain models contain nested objects, such as an address embedded in a customer:

```java
public class Address {
    private String city;
    private String postalCode;
}

@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL)
    private Address address;
}
```

When querying nested properties, Spring Data Commons splits property paths using camel case. An underscore `_` can be used to explicitly mark path boundaries when names are ambiguous:

```java
List<Customer> findByAddress_City(String city);
```

`Address_City` explicitly states the path `address.city`. Whether SQL can be generated for a nested path also depends on mapping style and Spring Data JDBC query support in your version; do not assume every object reference automatically produces an ORM-style JOIN. For cross-table queries or complex relationships, use `@Query` or a custom repository query and inspect the SQL.

### Ambiguous property names

Suppose an entity has both `addressZip` and an `address.zipCode` object. A method name like `findByAddressZipCode(...)` can cause the parser to split along the longest matching property, resolving a different path than intended. An underscore `_` makes the boundary explicit:

```java
findByAddress_ZipCode(String zipCode);
```

Prefer unambiguous property names and use `_` only when disambiguation is necessary. Avoid using underscores arbitrarily if they make Java method names harder to read.

## 6. Keywords and Operators in Method Names

Common keywords in derived queries:

| Category | Example | Meaning |
|---|---|---|
| Equality | `findByStatus`, `findByStatusIs` | `status = ?` |
| Inequality | `findByStatusNot` | Not equal to value |
| Logical combination | `findByStatusAndCity`, `findByStatusOrCity` | `AND`, `OR` |
| Comparison | `findByAgeGreaterThan`, `findByAgeLessThanEqual` | Numeric/date comparison |
| Range | `findByCreatedAtBetween` | Within range |
| Null | `findByEmailIsNull`, `findByEmailIsNotNull` | Null check |
| String | `findByNameLike`, `findByNameStartingWith`, `findByNameContaining` | Pattern matching |
| Value set | `findByStatusIn`, `findByStatusNotIn` | `IN` / `NOT IN` |
| Boolean | `findByActiveTrue`, `findByActiveFalse` | Boolean value |
| Sorting | `findByStatusOrderByCreatedAtDesc` | Adds `ORDER BY` |
| Limiting | `findTop10ByStatus`, `findFirstByEmail` | Limits result count |

Example:

```java
List<Customer> findTop20ByStatusOrderByCreatedAtDesc(String status);

List<Customer> findByAgeGreaterThanEqualAndActiveTrue(int age);

List<Customer> findByEmailIsNotNullAndStatusIn(Collection<String> statuses);
```

If a keyword is unsupported or misplaced, an error can appear as an unparseable method or a query creation failure. Check the keyword list in the documentation for **your exact Spring Data Relational JDBC version**; do not apply JPA or MongoDB keywords blindly to JDBC.

## 7. Distinguishing Property Errors from Reserved Repository Methods

Certain methods such as `findById`, `existsById`, and `deleteById` are inherited from `CrudRepository`. They are **reserved methods** and target the property annotated with `@Id`, not necessarily a Java property named `id`.

Example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long customerKey;

    private String id; // business identifier, not @Id
}
```

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findById(Long value);       // looks up by @Id customerKey
    Optional<Customer> findCustomerById(String id); // derived query by property id
}
```

The `Customer` token in `findCustomerById` is a descriptive subject part; the `Id` predicate references the Java `id` property. If the method were named simply `findById`, it would match the reserved method and be interpreted as looking up by the entity identifier. This is an important exception when an entity has a business property named `id` while its primary key has a different name.

When you need to query a business property named `id`, insert a subject descriptor so the signature does not collide with the reserved method—such as `findCustomerById(...)`—and make sure the parameter type matches that property.

## 8. When Do Errors Appear at Startup?

By default, Spring Data creates repository proxies and builds query methods when the repository is initialized. If query derivation cannot find a property, bean creation can fail before the application is ready to accept requests.

A stack trace typically has several nested wrappers:

```text
ApplicationContextException / BeanCreationException
  -> Error creating bean with name 'customerRepository'
     -> QueryCreationException
        -> PropertyReferenceException
           -> No property 'fristName' found for type 'Customer'
```

Read the **deepest meaningful exception**, usually `PropertyReferenceException` or the specific query-creation cause, rather than stopping at `ApplicationContext failed to start`.

### Bootstrap modes can change when errors are detected

Spring Data repositories support different bootstrap modes (eager/default, lazy, or deferred). If repositories are initialized lazily or deferred, errors may not surface during initial startup and only appear when the bean or query is first initialized or invoked.

Therefore, "the application started" does not prove every derived query is valid if the project uses lazy or deferred bootstrap. A test that actively loads the repository context helps catch errors earlier.

## 9. Distinguishing Query Creation Errors from SQL Execution Errors

Not every repository error comes from property names. The table below helps pinpoint the failing phase:

| Phase | Example error | What to check |
|---|---|---|
| Method name parsing | `PropertyReferenceException` | Missing property, invalid nested path |
| Query creation | `QueryCreationException` | Invalid keyword, method signature, or query declaration |
| Parameter binding | Type or parameter count error | Incompatible Java type, mismatched named parameter |
| SQL execution | `BadSqlGrammarException`, `DataAccessException` | Column/table name, dialect, SQL syntax, schema |
| Result reading | Conversion/mapping exception | Column type, converter, nullability, or mapping constructor |
| Result cardinality | `IncorrectResultSizeDataAccessException` | Method expects single result but query returns multiple rows |

For example, the Java property `firstName` maps to the `first_name` column. If `findByFirstName(...)` parses successfully but the database reports `column first_name does not exist`, that is a schema/SQL execution error, not a method-name error.

Conversely, if `findByFristName(...)` reports `No property 'fristName' found`, the database has not even received an SQL statement; the query failed to build.

## 10. `@Query` When Method Names Cannot Express the Query

Derived queries suit simple property-based conditions. For JOINs, aggregations, subqueries, vendor-specific SQL, or complex projections, use `@Query`:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT c.*
        FROM customer c
        WHERE c.status = :status
          AND EXISTS (
              SELECT 1
              FROM purchase_order o
              WHERE o.customer_id = c.customer_key
          )
        """)
    List<Customer> findCustomersWithOrders(@Param("status") String status);
}
```

Inside `@Query` SQL, use database table and column names (`customer_key`, `customer_id`), not Java property names (`customerKey`) unless those happen to be the actual column names. The method name can reflect the use case; the SQL inside the annotation defines the query.

`@Query` is not a workaround for every property typo. If a query only needs `findByFirstName`, fixing the typo is much easier to maintain. Switch to explicit SQL only when the query genuinely needs structural control or performance tuning.

## 11. Step-by-Step Guide to Reading and Fixing Stack Traces

When the application fails to start because of a repository, follow this sequence:

1. **Identify the failing repository bean.** For example, `customerRepository`.
2. **Identify the method mentioned.** For example, `findByFristName`.
3. **Find the deepest exception.** If it is `PropertyReferenceException`, note the missing property and the domain type.
4. **Open the right domain type.** Check Java properties, getters, embedded types, and `@Id`.
5. **Break the method name into parts.** Subject, `By`, property path, operator, `And`/`Or`, `OrderBy`.
6. **Check `@Column`.** Make sure you did not confuse an SQL column name with a Java property name.
7. **Check reserved methods.** `findById` may point to `@Id` rather than a business `id` property.
8. **Verify keywords against your Spring Data JDBC version.** Do not apply keywords from another module.
9. **Run a repository context test.** Confirm the bean initializes cleanly before running the full application.
10. **If the query compiles/creates cleanly but fails at runtime, inspect SQL/schema/parameters.** Stop renaming the method when the fault lies in the database.

### Stack trace analysis example

Suppose the log contains:

```text
Caused by: org.springframework.data.mapping.PropertyReferenceException:
No property 'createdOn' found for type 'Customer'
```

Entity:

```java
private Instant createdAt;
```

Repository:

```java
List<Customer> findByCreatedOnAfter(Instant time);
```

Fix:

```java
List<Customer> findByCreatedAtAfter(Instant time);
```

There is no need to alter the schema, add converters, or touch the database; simply point the method to the property that actually exists.

## 12. Catching Query Method Errors Early in Tests

A `@DataJdbcTest` creates the repository slice and catches query derivation errors as Spring loads the context:

```java
@DataJdbcTest
class CustomerRepositoryContextTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void repositoryIsCreated() {
        assertThat(repository).isNotNull();
    }
}
```

This test does not even have to invoke the method to catch parsing errors when repositories are eagerly bootstrapped in the test context. If your project uses lazy or deferred repository bootstrap, invoke the method in the test or configure tests for eager repository initialization.

For property-path errors, no database rows are required to reproduce the failure; the query method can fail as soon as the repository is created. Still, `@DataJdbcTest` requires valid database and schema setup so query tests can run.

A runtime test verifying an actual derived query:

```java
@Test
void findsCustomerByFirstName() {
    jdbcTemplate.update(
            "INSERT INTO customer(id, first_name, email, status) VALUES (?, ?, ?, ?)",
            1L, "Lan", "lan@example.com", "ACTIVE"
    );

    List<Customer> customers = repository.findByFirstName("Lan");

    assertThat(customers).hasSize(1);
    assertThat(customers.get(0).getFirstName()).isEqualTo("Lan");
}
```

Adjust the SQL example to match your project's actual DDL and Java version. The goal is to verify both phases: the repository method builds cleanly and the SQL returns the right results.

## 13. Common Method and Property Name Errors

| Scenario | Message or symptom | Cause | How to resolve |
|---|---|---|---|
| Misspelled property | `No property 'fristName' found for type 'Customer'` | Typo in predicate | Fix to match the actual property name |
| SQL column name used in method | `No property 'first_name' found` | Confusing `@Column` with Java property | Use `findByFirstName` |
| Invalid nested path | `No property 'zip' found...` or invalid path | Parser split the path incorrectly | Check each segment; use `_` to disambiguate |
| Using `findById` for business ID | Queries by primary key `@Id` | Method matches reserved CRUD signature | Name it e.g. `findCustomerById` |
| Unsupported keyword | Query creation/parsing error | Used another module's keyword or wrong syntax | Check Spring Data JDBC docs for your exact version |
| Derived query builds but SQL fails | SQL grammar/schema exception | Wrong column/table name or dialect mismatch | Inspect DDL and executed SQL |
| Expecting single result but multiple rows exist | `IncorrectResultSizeDataAccessException` at runtime | Singular return type with non-unique data | Use `List`, or add a unique constraint / stricter filter |
| App starts but fails on first call | Lazy/deferred repository bootstrap | Query was not initialized at startup | Eagerly test repositories or call the method in tests |

## 14. Naming Conventions to Prevent Errors

- Keep method names in camelCase matching Java properties: `findByFirstName`, `findByCreatedAt`.
- Name domain properties consistently; avoid near-duplicate aliases such as `created`, `createdOn`, and `createdAt` if they mean the same thing.
- Use `_` only when needed to clarify nested property path boundaries.
- Use `And`/`Or` for clear predicate splits; for complex conditions, write `@Query` instead of an overly long method name.
- Use clear subjects (`find`, `exists`, `count`, `delete`) and verify keywords against the right module.
- Remember reserved methods from `CrudRepository`, especially `findById`, `existsById`, and `deleteById`.
- When renaming a Java property, update derived query methods accordingly; when changing only the SQL column name via `@Column`, derived methods normally do not need changes.
- Use context tests to catch query method errors before packaging or deploying.

**Key takeaway:** derived queries are built from method names and Java property paths. Whenever you see `PropertyReferenceException`, check the property name and path in the domain class first. `@Column` only adjusts the SQL column name, while methods like `findById` may be reserved identifier methods. If the repository initializes cleanly but the query fails at runtime, inspect the SQL, schema, parameters, and data types next.

## Official References

- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): how to declare derived queries, keywords, and `@Query`.
- [Spring Data Commons — Query Method Details](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): subjects, predicates, property expressions, nested paths, and reserved methods.
- [Spring Data Commons — Query Creation](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-methods.query-creation): query lookup and deriving queries from method names.
- [Spring Data Commons — `PropertyReferenceException` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PropertyReferenceException.html): nonexistent property path error.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping domain properties to relational columns.
