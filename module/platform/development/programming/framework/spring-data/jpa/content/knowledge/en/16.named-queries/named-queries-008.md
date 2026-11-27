# Detecting Invalid Queries at Startup and at Runtime in Spring Data JPA

## 1. Why do query errors surface at two different times?

In Spring Data JPA, a repository method can be parsed and prepared when the application starts, yet the final SQL is usually sent to the database only when the method is called. As a result, query errors can appear in two phases:

- **At initialization (bootstrap/startup):** Spring Data parses method names, resolves entity properties, locates named queries, or builds JPQL query objects. Errors detectable from metadata and JPQL syntax typically surface in this phase.
- **At execution (runtime):** The JPA provider generates and sends SQL, while the database parses the statement, binds values, and accesses actual tables, columns, and functions. Errors depending on schema, database, data, permissions, or parameter values usually appear only when the query runs.

Distinguishing these two phases helps pinpoint where to investigate. If the application fails to create a repository bean, inspect query derivation, JPQL, and repository bootstrap. If the repository bean is created successfully but fails when invoked, check the generated SQL, schema, parameters, and database.

Not every error falls strictly into one bucket. The JPA provider, Spring Data JPA version, query type, and bootstrap mode can shift when certain checks run.

## 2. Lifecycle of a repository query

A repository method generally passes through these conceptual stages:

~~~text
Application starts
       |
       v
Spring creates repository bean
       |
       v
Parse method name or locate declared query
       |
       v
Create query object and run early-detectable checks
       |
       v
Application is ready to receive requests
       |
       v
Service calls repository method
       |
       v
JPA provider generates SQL and binds parameters
       |
       v
Database parses and executes SQL
       |
       v
Map results to entity / projection
~~~

These steps form a conceptual model. Some work—such as creating query objects, parsing JPQL, or validating metadata—can occur early; sending SQL and validating execution against the actual schema typically wait until the method is invoked.

Example repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where c.status = :status
    """)
    List<Customer> findByStatus(@Param("status") CustomerStatus status);
}
~~~

When Spring creates the repository, the framework can parse `findByEmail` and prepare the JPQL query for `findByStatus`. When the application calls `findByEmail`, the provider needs to fetch data from the database to return results.

## 3. Errors detectable at repository initialization

### 3.1. Derived query referencing an invalid property name

Spring Data parses method names to determine properties and query conditions. If a property name does not exist on the entity, query derivation can fail when the repository is created.

Example entity:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;
    private String fullName;
}
~~~

Incorrect repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmali(String email);
}
~~~

`Customer` has no `emali` property; the right name is `email`. Spring Data cannot build a query from an invalid property path. The error typically surfaces during repository initialization, with a root cause such as `PropertyReferenceException` or an outer wrapped query-creation exception.

Corrected:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Beyond direct property names, also verify nested property paths:

~~~java
List<Customer> findByAddress_City(String city);
~~~

The entity must have an `address` relationship or property, and its type must have a `city` property. Underscores can help disambiguate nested property path segments when property names might otherwise conflict.

### 3.2. JPQL @Query with invalid syntax or wrong entity/property names

JPQL uses entity names and Java properties, not raw SQL table or column names.

Incorrect example:

~~~java
@Query("select c from Customer c where c.emali = :email")
Optional<Customer> findByEmail(@Param("email") String email);
~~~

If the entity only has an `email` property, `c.emali` is invalid. For JPQL queries declared with `@Query`, Spring Data JPA and the JPA provider can usually ask the provider to create the query to validate syntax/metadata when the repository initializes. Thus, the error can cause the application to fail at startup before the method is ever called.

Corrected version:

~~~java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(@Param("email") String email);
~~~

Common JPQL mistakes:

- Misspelling the entity name in `FROM`.
- Using a database column name instead of the entity property name.
- Misspelling an alias or referencing an undeclared alias.
- Invalid `JOIN`, `ORDER BY`, `GROUP BY`, or expression syntax.
- Calling a function unsupported by the provider/database.
- Using a constructor expression with a wrong DTO name or parameter type order.
- Declaring an invalid count query for a paginated method.

Exact timing and exception types depend on the provider and how repositories initialize. Still, early syntax checking is a major advantage of static JPQL.

### 3.3. Missing or misdeclared named query

JPA allows declaring named queries on entities or in XML mappings. Example:

~~~java
@Entity
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = :email"
)
public class Customer {
    @Id
    private Long id;

    private String email;
}
~~~

Spring Data JPA can resolve named queries by entity and method naming convention, such as `Customer.findByEmail`. If the application is configured to use declared queries only and no matching named query exists, repository creation can fail.

If the named query exists but has invalid JPQL, the JPA provider may detect it when initializing the persistence unit or creating the query; exact timing depends on the provider.

When `@Query` is placed directly on a repository method, that declaration takes precedence for that method over a named query per Spring Data JPA's lookup rules.

### 3.4. Parameter name or method declaration errors

For example, a query uses `:status` while the method does not supply a matching parameter:

~~~java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(CustomerStatus state);
~~~

The method parameter is named `state`, whereas the JPQL named parameter is `status`. Declare parameters consistently with `@Param`:

~~~java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(
    @Param("status") CustomerStatus state
);
~~~

Some parameter mismatches can be caught when Spring Data parses the method or constructs the query; actual value binding and type checks happen when the method is called. Do not rely on application startup success to assume every parameter binding is right.

## 4. Errors that typically surface only at query execution

### 4.1. Native SQL with wrong table or column names

Native queries use database SQL:

~~~java
@Query(
    value = "select * from customer where emali = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(
    @Param("email") String email
);
~~~

Suppose table `customer` has column `email`, not `emali`. The JPQL parser cannot validate this native column name as an entity property. The database usually reports the error only when the SQL runs.

Corrected:

~~~java
@Query(
    value = "select * from customer where email = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(
    @Param("email") String email
);
~~~

Native SQL may undergo partial processing by the provider when the query is created, but full validation of syntax, table/column names, functions, operators, and permissions typically requires database execution. Early-checking capabilities depend on the provider, driver, and database.

### 4.2. Missing table or column in the connected schema

A JPQL query can be valid according to entity metadata, yet the actual schema is missing a required table or column. When the query runs, the database may return errors such as "table/relation not found" or "column not found".

Examples:

- The entity maps to the `customer` table.
- The application connects to the wrong database or schema.
- The migration creating the table has not been applied in that environment.
- A column was renamed while a native query was not updated.

Check the datasource URL, current database/schema, migration history, and table/column metadata on the exact failing environment.

### 4.3. Incompatible database functions or data types

A JPQL query might contain:

~~~java
@Query("""
    select function('date_trunc', 'day', o.createdAt)
    from PurchaseOrder o
""")
List<Object> findOrderDays();
~~~

If the database lacks the `date_trunc` function, an extension is not installed, or argument types mismatch, the error can appear when the database executes the SQL. Some providers may catch unsupported functions or types early, but you should not assume all database functions are fully validated at startup.

Similarly, native queries using JSON operators, full-text search, geospatial functions, or vendor-specific types may only run on a specific database/dialect.

### 4.4. Parameter binding and runtime data errors

A query can be created successfully yet fail at runtime due to:

- Missing value for a named parameter.
- A Java value incompatible with the column or expression type.
- Values exceeding column precision/scale or length.
- Passing enums in a way that mismatches the mapping.
- Input values causing a database function to receive invalid data.
- Returned results failing to map to the entity or projection.

Some parameter type errors can be detected from metadata; errors tied to actual runtime values are typically discovered only during binding or execution.

### 4.5. Permission, connection, and constraint errors

Even a valid query can fail due to environmental issues:

- The database is unavailable or the connection pool is exhausted.
- The application account lacks `SELECT`/`EXECUTE` privileges.
- A function or extension lacks execute permission.
- Query timeout or lock timeout.
- Data violates constraints during modifying queries or side-effecting stored functions.
- The transaction has already been marked rollback-only.

These are environmental or execution errors, not necessarily JPQL syntax bugs.

## 5. Comparing detection timing by query type

| Query type | Checkable at initialization | Requires execution to verify |
|---|---|---|
| Derived query, e.g. `findByEmail` | Method name parsing, property paths, and query kind | SQL, schema, data, permissions, and results |
| JPQL `@Query` | JPQL parsing, entity/attribute, aliases, and many syntax errors | Exact SQL, function/database behavior, bind values, and results |
| JPA `@NamedQuery` | Provider typically checks when persistence unit or query initializes | Database-specific behavior, schema, and data |
| Native `@Query` | Method metadata, parameter metadata, or partial query handling per provider | Usually requires database execution to verify SQL, column/table names, functions, and dialect |
| Stored procedure/function | Method declaration and partial metadata checks | Actual procedure/function, permissions, parameters, and result types |
| Dynamically built Criteria API | Java code checked at compile time; some structures when building Criteria query | Final query, bind values, and SQL on the database |

This table describes general tendencies. It is not a guarantee that every error for a query type always appears at the exact same moment across all versions.

## 6. How repository bootstrap mode affects initialization timing

Spring Data JPA supports repository bootstrap modes. The mode determines whether repositories initialize eagerly or lazily, thereby shifting when initialization errors are observed.

| Mode | General behavior | When do repository initialization errors surface? |
|---|---|---|
| DEFAULT | Initializes repositories eagerly by default | During application startup |
| DEFERRED | Defers part of initialization until after application context refresh, completing before ready | Near the end of startup, before ready state |
| LAZY | Initializes repositories when the bean is first requested | When the repository is first accessed |

With Spring Boot, configure via:

~~~properties
spring.data.jpa.repositories.bootstrap-mode=default
~~~

Or use `deferred` or `lazy` when architectural needs warrant it.

Notes:

- `LAZY` does not fix broken queries; it only delays when errors can appear.
- If a repository is only accessed once a request arrives, the error may surface on the first request.
- `DEFERRED` postpones work while still finishing repository initialization before the application is considered ready.
- For production applications, eager/`default` bootstrap usually catches configuration errors early before serving traffic.

Do not enable lazy bootstrap just to hide a broken query or make startup appear successful.

## 7. QueryLookupStrategy and query resolution

Spring Data JPA has strategies for resolving queries for repository methods:

- CREATE: creates queries from method names.
- USE_DECLARED_QUERY: requires a predeclared query, such as `@Query` or a matching named query.
- CREATE_IF_NOT_FOUND: looks for a declared query first; derives from the method name if absent.

`CREATE_IF_NOT_FOUND` is the common default option. For example, Spring Data may look up a named query by convention before parsing the method as a derived query.

The lookup strategy answers **where the query comes from**; it does not guarantee the database will execute the query successfully. A declared JPQL query may parse cleanly yet still encounter schema or data errors at runtime.

When debugging, identify what the method is using:

1. `@Query` on the repository method?
2. Named query on the entity or in XML?
3. Derived query from the method name?
4. Native SQL or JPQL?

If you are unsure which query was selected, inspect the method declaration, named queries, and relevant Spring Data/JPA provider logs.

## 8. Reading stack traces to identify the error phase

### 8.1. Errors when creating the ApplicationContext

If the application fails to start and the stack trace contains classes like:

- BeanCreationException
- UnsatisfiedDependencyException
- QueryCreationException
- PropertyReferenceException
- Hibernate query parse/semantic exceptions

follow the deepest `Caused by` chain. Outer exceptions usually only state that a repository bean or service bean could not be created; the real root cause is typically an invalid property path, JPQL error, or named query error.

Example error pattern:

~~~text
Error creating bean with name 'customerRepository'
...
QueryCreationException
...
No property 'emali' found for type 'Customer'
~~~

Resolution: inspect the method name, entity properties, `@Query`, named queries, and parameters before checking runtime SQL.

### 8.2. Errors after calling a repository method

If the application starts successfully and errors occur only when a service calls the repository, stack traces may include:

- `DataAccessException` or a Spring-translated subclass.
- `InvalidDataAccessResourceUsageException`.
- `BadSqlGrammarException` for certain JDBC/translation paths.
- `SQLGrammarException`, `JDBCException`, or equivalent Hibernate exceptions.
- Driver-specific exceptions, such as PostgreSQL or SQL Server SQL errors.

Inspect the SQL statement and the underlying database error message. Do not adjust annotations blindly based solely on the outer exception class; identify which table, column, function, type, permission, or value the database rejected.

### 8.3. Not every startup error is a query error

A repository can fail to initialize due to a misconfigured datasource, entity scan, transaction manager, dialect, or entity mapping. Read the root cause before concluding a query method is at fault.

## 9. Enabling logging to observe SQL and bind parameters

In development, enable Hibernate logging to view SQL sent to the database:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

With Hibernate 6, bind parameter logging can be enabled via:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

With Hibernate 5, the bind parameter logger typically uses category:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Logger names depend on the Hibernate version. Only enable bind parameter logging when diagnosing issues; parameter values can contain emails, tokens, personal information, or sensitive business data. Do not leave `TRACE` bind parameter logging enabled in production long-term without log-protection controls.

`spring.jpa.show-sql=true` can be used for simple SQL observation, though logger configuration is generally better for controlling log levels and integrating with application logs.

When reading SQL:

1. Verify the SQL targets the expected tables and columns.
2. Check aliases and `JOIN`s.
3. Check placeholders and bound values.
4. Compare Java data types against database column types.
5. Run the SQL directly against the target database/schema to reproduce.
6. Inspect the execution plan if the query succeeds but runs slowly.

## 10. Schema validation does not replace query validation

A common setting is:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

`validate` instructs Hibernate to verify portions of entity-to-schema compatibility at startup. It helps catch mismatched table or column mappings.

However, schema validation does not mean Hibernate test-ran every repository method. It does not guarantee:

- Every native query has valid syntax.
- Every column name in native SQL exists.
- Every database function or stored procedure exists.
- Every runtime parameter and value is valid.
- Every query has required permissions and acceptable performance.

Therefore, combine mapping/schema validation with integration tests that actually execute critical queries.

## 11. Testing to catch errors before deployment

### 11.1. Verifying repository bootstrap in tests

`@DataJpaTest` sets up a JPA slice test, typically configuring entities and repositories to verify the persistence layer:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void repositoryContextStarts() {
        assertThat(repository).isNotNull();
    }
}
~~~

This test helps catch repository-creation, derived-query, or JPQL errors checkable at bootstrap. However, it does not verify that every method runs cleanly if those methods are never called.

### 11.2. Invoking each query with representative data

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer customer = new Customer("an@example.com");
        repository.saveAndFlush(customer);

        Optional<Customer> result =
            repository.findByEmail("an@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
            .isEqualTo("an@example.com");
    }
}
~~~

This is a structural example; constructors and getters must match your actual entity. Calling methods in tests forces queries through both the provider and database, catching errors that only surface at runtime.

Write dedicated tests for:

- Derived queries with property paths.
- JPQL `@Query` and named queries.
- Native queries and database functions.
- Named parameters, enums, and date/time types.
- `JOIN`, `DISTINCT`, `GROUP BY`, and count queries.
- Pagination and sorting.
- Empty results, `NULL`s, and boundary data.

### 11.3. Using the right database in integration tests

H2 can be helpful for fast tests, but it does not completely replace production databases. A native query using PostgreSQL `jsonb`, `unaccent`, `date_trunc`, or vendor operators may not run on H2.

If production runs PostgreSQL, MySQL, or SQL Server, consider Testcontainers to run the real database engine in integration tests. This surfaces dialect, function, schema, and data-type issues close to production conditions.

### 11.4. Testing all critical query methods

A successful `ApplicationContext` startup only proves that initialized components passed startup checks. It does not prove every repository method works properly.

A solid testing checklist:

1. Initialize the persistence context and repositories.
2. Create schemas via migrations matching the target environment.
3. Invoke every critical query method.
4. Assert content, counts, and result types.
5. Test `NULL` parameters and boundary values.
6. Test count queries when using `Page`.
7. Run tests on a database with the target dialect.
8. Inspect slow queries with execution plans when needed.

## 12. Troubleshooting workflow by failure phase

When encountering an error, follow these steps in order:

1. **Determine the phase:** did the application fail during startup or after a repository method was called?
2. **Find the root cause:** read the deepest `Caused by` entries in the stack trace.
3. **Identify the query type:** derived, JPQL, named query, native SQL, stored procedure, or Criteria.
4. **If startup failed:** check property names, entity names, JPQL, named queries, parameters, and repository bootstrap.
5. **If runtime failed:** inspect SQL, bind parameters, database/schema, functions, permissions, data types, transactions, and input data.
6. **Reproduce with an integration test:** execute the query against the matching database and schema.
7. **Fix at the right layer:** query derivation/JPQL, mapping, migration, native SQL, or database configuration.
8. **Re-run tests:** confirm both repository bootstrap and method execution succeed.

Do not change `ddl-auto`, switch to lazy bootstrap, or disable validation simply to get the application past startup. Those changes merely postpone errors until requests arrive and complicate diagnosis.

## 13. Key takeaways

- Derived queries are typically parsed when Spring Data creates repositories; misspelled property names usually cause startup failures.
- JPQL `@Query` declarations are typically validated for syntax/metadata by the provider when repository queries initialize.
- Named queries may be validated by the provider when the persistence unit or query initializes; exact timing depends on the provider.
- Native SQL usually requires database execution to fully validate table/column names, syntax, and functions; early checks vary by provider.
- Schema, permission, connection, parameter-type, and data errors typically surface at runtime.
- `DEFAULT`, `DEFERRED`, and `LAZY` change when repositories initialize; they do not fix invalid queries.
- `ddl-auto=validate` checks part of the mapping/schema, not every repository method.
- Startup tests and query-executing integration tests are complementary layers of verification.
- Use the real database in Testcontainers or an equivalent environment when queries depend on dialect.
- Read the root exception and actual SQL before changing configuration.

Catching errors early requires combining repository-bootstrap checks with integration tests that execute real queries. Startup checks catch method-name, property, and JPQL errors; running against the real database catches SQL, schema, function, parameter, and data issues that metadata alone cannot verify.