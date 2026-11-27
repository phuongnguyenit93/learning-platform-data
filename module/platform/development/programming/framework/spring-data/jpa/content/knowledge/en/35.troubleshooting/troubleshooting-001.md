# Classifying Configuration, Mapping, Query, and Data Errors in Spring Data JPA

## 1. Why Classify Errors?

When Spring Data JPA encounters an error, the stack trace often spans multiple layers: service, repository proxy, Spring ORM, JPA provider (usually Hibernate), JDBC driver, and database. The exception at the top of the stack trace may only be a wrapper; the real cause often lies deeper in **Caused by** or in the database's SQLState/vendor error code.

For example:

- An application failing to start due to a missing DataSource is a configuration/connection error.
- Hibernate failing to create EntityManagerFactory because two entities map to the same table name is a mapping error.
- A repository failing to create a query due to an incorrect property name is a query definition error.
- An INSERT failing due to a foreign key violation is a data/constraint error.
- An UPDATE failing to save because the entity was modified by another transaction is a concurrency error.

Accurate classification helps you check the right place. Changing configuration when the error is in the data only adds complexity; changing the query when the schema is wrong also fails to solve the root cause.

The four main groups in this lesson:

1. **Configuration and connection errors**: Spring context, datasource, transaction manager, dialect, migration, and permissions.
2. **Mapping errors**: entity, field, relationships, Java/SQL data types, and schema.
3. **Query errors**: derived query, JPQL, native SQL, parameters, projection, pagination, and execution.
4. **Data errors**: null, constraint, conversion, non-unique data, entity state, and concurrency.

Specific exceptions may vary by Spring Boot, Spring Data, Hibernate, JPA provider, and JDBC driver versions. Read the actual exception and cause chain instead of drawing conclusions from the class name alone.

## 2. General Diagnostic Process

When encountering an error, follow this order:

1. **Identify the timing**: did the error occur during context startup, repository creation, method invocation, flush, or transaction commit?
2. **Find the root exception**: read the entire Caused by chain, do not stop at the first DataAccessException or JpaSystemException.
3. **Retrieve the SQL statement and parameters**: identify which statement failed, which table/column is involved, and which parameter caused the error. Do not log sensitive data.
4. **Cross-check mapping and schema**: are the entity, migration, schema/table/column names, data types, and constraints synchronized?
5. **Minimal reproduction**: create a small test with the same DBMS, same migration, and same JDBC driver.
6. **Fix the root cause**: update the appropriate configuration, mapping, query, or data.
7. **Re-test**: verify both the success case, boundary data, and rollback if a transaction is involved.

### Reading the Stack Trace by Layer

| Commonly seen exception class | Initial meaning | Next step to trace |
|---|---|---|
| BeanCreationException | A bean could not be created | Deepest Caused by and the bean being initialized |
| UnsatisfiedDependencyException | Could not inject dependency | Missing bean/type/qualifier or error during creation |
| PersistenceException / JpaSystemException | JPA provider encountered an error | Hibernate cause, JDBC exception, and SQL |
| DataAccessException | Spring translated a data access error | Root exception, SQLState, and vendor code |
| QueryCreationException | Repository query could not be created | Property name, JPQL, named query, or parameters |
| DataIntegrityViolationException | Data violated a constraint | Constraint name, table/column, and involved values |
| TransactionSystemException | Error at transaction boundary | Flush/commit error and rollback exception |
| OptimisticLockingFailureException | Concurrent update is no longer valid | Version, updated row count, and competing transaction |

Spring typically translates persistence provider/JDBC exceptions into a unified exception hierarchy under the **org.springframework.dao** package. The outermost exception name is not necessarily the error name returned by the database.

## 3. Configuration and Connection Errors

### 3.1 Missing or Misconfigured DataSource

Common symptoms:

- No DataSource bean or JDBC URL not found.
- Unable to connect to the database: connection refused, timeout, authentication failed.
- Pool initializes successfully, but cannot obtain a connection when querying.
- Tests accidentally connect to a different database than expected.

Common causes:

- Missing JDBC driver on the classpath.
- Wrong host, port, database name, username, or password.
- Database is not running, or DNS/firewall/network blocks the connection.
- Spring profile is not activated or environment variables are not passed in.
- Driver and DBMS are incompatible.
- Pool exhaustion due to unreleased connections, long-running queries, or transactions holding connections too long.

Spring Boot configuration example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: app_user
    password: \${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  jpa:
    hibernate:
      ddl-auto: validate
```

This is an illustrative configuration for PostgreSQL; replace the URL, driver, and environment variable according to your actual DBMS. Never store real passwords in source control. When using HikariCP, check the pool initialization logs and connection timeout settings; do not immediately increase pool size before determining whether connections are being held by transactions or slow queries.

### 3.2 Missing Transaction Manager or EntityManagerFactory

Symptoms:

- NoSuchBeanDefinitionException for PlatformTransactionManager or EntityManagerFactory.
- Repository bean is not created.
- Application has multiple DataSources, but a repository uses the wrong transaction manager.
- Part of the operations do not participate in the expected transaction.

What to check:

- Whether the Spring Data JPA and JDBC driver dependencies have the correct scope.
- Whether the repository/entity packages are within the scan scope.
- Whether there are multiple datasource configurations and each repository group is bound to the right entityManagerFactoryRef/transactionManagerRef.
- Whether the transaction manager manages the right EntityManagerFactory.
- Whether a custom configuration accidentally disables necessary auto-configuration.

With a single simple datasource, Spring Boot usually auto-configures JpaTransactionManager. With multiple datasources, you must explicitly configure each EntityManagerFactory, transaction manager, and repository package. Do not use datasource A's transaction manager for datasource B's EntityManagerFactory.

### 3.3 Dialect, Schema, and Migration Errors

Symptoms:

- Hibernate cannot determine the dialect.
- Schema validation reports missing tables/columns or mismatched types.
- Repository initializes successfully, but the query fails because the procedure/table has not been created yet.
- Migration fails due to syntax incompatible with the DBMS.

How to resolve:

- Check the actual DBMS and JDBC metadata.
- Ensure the JDBC URL/driver is correct; Hibernate can usually infer the dialect from metadata.
- Only declare hibernate.dialect when truly necessary or when the environment cannot read metadata; choose a dialect compatible with the Hibernate version in use.
- Verify that Flyway/Liquibase runs against the right database/schema and in the right order.
- Use ddl-auto=validate to detect mapping/schema mismatches at startup; do not treat validate as a tool to create or modify the schema.
- Cross-check the deployed migration DDL, do not rely solely on entity annotations.

Common ddl-auto values:

| Value | Behavior | Usage |
|---|---|---|
| none | Does not manage the schema | Migrations take responsibility |
| validate | Validates mapping against the schema | Useful for migration-controlled environments |
| update | Hibernate attempts to update the schema | Avoid relying on this for production migrations |
| create | Creates the schema on startup | Primarily for experimental environments |
| create-drop | Creates the schema and drops it when context closes | Tests/demos with temporary data |

Do not use create or create-drop on a database with data that must be preserved. For applications with migrations, validate or none is typically chosen depending on the deployment workflow.

### 3.4 Permissions and Runtime Configuration

An application may connect successfully yet still fail to read/write because the user lacks privileges. Check SELECT, INSERT, UPDATE, DELETE, EXECUTE privileges, sequence permissions, and schema permissions according to the exact operations. Run tests using an account similar to the application's; do not run all tests as the database owner and assume production permissions are correct.

Settings such as default schema, search_path, case sensitivity, timezone, collation, and SQL mode also affect results. Verify them in both test and production environments when queries depend on these settings.

## 4. Entity and Schema Mapping Errors

### 4.1 Invalid Entity or Inconsistent Mapping

Symptoms:

- AnnotationException, MappingException, or errors creating SessionFactory/EntityManagerFactory.
- Hibernate cannot find an identifier.
- Two entities map to the same table/column in an invalid way.
- Fields are not mapped as expected or the entity cannot be instantiated.

Common causes:

- Entity lacks @Id or @EmbeddedId.
- Entity class does not meet JPA constructor/access requirements.
- Relationship references the wrong type or is missing the target entity.
- Mixing annotations between jakarta.persistence and javax.persistence.
- Using @Column with a column name that differs from the actual schema.
- Entity/mapped superclass inheritance is misconfigured.
- Java type is incompatible with the SQL type.

Basic mapping example:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer", schema = "app")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true, length = 180)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

This snippet illustrates Jakarta Persistence; a corresponding app.customer table must exist in the migration. An entity requires an identifier; the no-arg constructor can be protected. Attributes such as name, schema, nullable, unique, and length must match both design intent and the actual DDL.

### 4.2 Incorrect Table or Column Name

Symptoms:

- SQLGrammarException or BadSqlGrammarException.
- Database reports relation/table/column does not exist or invalid identifier.
- Only one query fails while other queries still succeed.

How to check:

1. Capture the SQL generated by Hibernate.
2. Cross-check table/column names against migrations in the exact schema.
3. Check whether the naming strategy converts camelCase to snake_case.
4. Check quoting/case sensitivity and reserved keywords.
5. Confirm the datasource is connecting to the right database.

For example, the entity uses @Column(name = "created_at") while the migration created createdAt. Hibernate will access the name per the mapping and the database may not find the column. Fix either the mapping or the migration under one consistent convention; do not arbitrarily rename columns if existing data must be preserved.

### 4.3 Relationships and Foreign Keys

Common errors:

- @ManyToOne or @OneToOne references the wrong join column.
- Bidirectional relationship has mappedBy pointing to a non-existent field name.
- @JoinColumn does not match the foreign key column name.
- Incorrect cascade causes unexpected persist/remove operations.
- Related object has not been saved or does not belong to the persistence context.

Example:

```java
@Entity
@Table(name = "orders", schema = "app")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }
}
```

The migration must create the customer_id column and a foreign key referencing customer's primary key. If saving PurchaseOrder with a Customer that does not yet exist, the database will reject it on insert/flush. If Customer already exists in the database but the Java object is transient/detached, load an appropriate reference within the transaction or configure cascade to match the domain lifecycle. Do not add CascadeType.ALL just to make an exception disappear; cascade can delete or persist unintended data.

### 4.4 Enums, Date/Time, Precision, and Data Types

Some mapping errors only appear when specific data is written or read:

- Enums stored as ordinal can change meaning when enum order changes.
- String enums may exceed column length.
- BigDecimal has inappropriate precision/scale.
- Instant/LocalDateTime/OffsetDateTime have different timezone rules.
- UUID, JSON, ARRAY, native enums, and vendor-specific types require support from the provider/dialect/driver.
- Java primitives cannot represent SQL NULL; reading NULL into int/long can cause conversion errors or wrong default values.

If enum values need to remain stable by name, use @Enumerated(EnumType.STRING) and migrate the column accordingly; you still need to manage enum renames since stored data will contain the old names. For currency, choose appropriate precision/scale and use BigDecimal instead of float/double. For date/time, clearly determine whether it represents an absolute instant or local time before selecting the Java and SQL types.

## 5. Query Definition and Execution Errors

### 5.1 Derived Query Cannot Find Property

Spring Data parses method names to generate queries based on entity properties. If a property name is wrong, the error can appear immediately during repository initialization, often as PropertyReferenceException or QueryCreationException.

Example entity with field email:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

If you write findByMailAddress when the entity has no mailAddress property, Spring Data cannot create the query. The method name must be based on the entity's Java property, not necessarily the SQL column name. For example, if the database column is email_address and the Java field is emailAddress, the derived query still uses findByEmailAddress.

With nested properties, method names can be ambiguous. Use the `_` separator to clarify the path, e.g., findByCustomer_Address_City if the actual model has those properties. Verify the exact Java property names and mapped associations.

### 5.2 JPQL Differs from SQL

JPQL queries entities and Java properties, not table/column names directly (except native queries). Example:

```java
@Query("""
    select c
    from Customer c
    where c.email = :email
    """)
Optional<Customer> findCustomer(@Param("email") String email);
```

Here Customer is the entity name and email is the entity property. Writing SELECT * FROM customer in JPQL will cause a syntax error; if you want to use SQL against tables, declare nativeQuery = true:

```java
@Query(
    value = "SELECT * FROM app.customer WHERE email = :email",
    nativeQuery = true
)
Optional<Customer> findCustomerNative(@Param("email") String email);
```

Native queries depend on the DBMS, schema/column names, and result mapping. When using pagination, the count query (countQuery) may need to be declared separately, especially for complex queries with joins, group by, or CTEs.

### 5.3 Wrong Parameters, Return Type, or Result Count

Symptoms:

- Named parameter not bound or parameter not found.
- Parameter type is incompatible with the property type.
- Query returns multiple rows while the method declares a single entity/Optional.
- Projection does not match aliases or constructor.
- No result or NonUniqueResultException.

Example:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(@Param("email") String email);
```

The name :email must match @Param("email"). If the repository uses positional parameters, the parameter order must be exact. Avoid mixing named and positional parameters in the same query unless necessary.

Optional<Customer> expresses an expectation of at most one result. If email is not unique in the database, the query may return multiple rows and trigger a non-unique result error. Only a database unique constraint protects data against concurrent writes; using Optional alone does not enforce uniqueness.

If business logic allows multiple results, return List<Customer>, Slice<Customer>, or Page<Customer> as appropriate. If only one result is allowed, enforce data constraints and handle the no-result case explicitly.

### 5.4 SQL Execution Errors

A query may be created successfully yet fail at runtime because:

- Table/column name is wrong or permissions are missing.
- SQL is incompatible with the dialect/DBMS.
- Parameter has an incompatible data type.
- Data exceeds precision/length or violates a constraint.
- Function, procedure, or extension does not exist.
- Query timeout, deadlock, or lock timeout.

Read the SQLState and vendor code in SQLException. SQLState usually helps identify the standard error category, while the vendor code and message point more specifically to the database issue. Do not handle errors by catching a generic Exception and ignoring it; translate errors at the appropriate boundary into meaningful business exceptions.

## 6. Data and Constraint Errors

### 6.1 NOT NULL, UNIQUE, FOREIGN KEY, and CHECK

| Constraint | Manifestation | How to check |
|---|---|---|
| NOT NULL | Cannot write a null value | Check field, validation, and column |
| UNIQUE | Duplicate unique value | Check existing data and race conditions |
| FOREIGN KEY | Child record references a non-existent parent record | Check write order, keys, and cascade |
| CHECK | Value does not satisfy the condition | Check business rules and DDL |
| LENGTH/precision | String/number exceeds column limit | Check length, precision, scale, and rounding |

Spring may translate constraint errors into DataIntegrityViolationException or DuplicateKeyException depending on the driver and context. This exception alone does not tell you the full business rule violated; inspect the constraint name, SQLState, and vendor message.

Do not rely solely on a SELECT check followed by INSERT to prevent duplicates. Two concurrent requests can still both see that the record does not exist and both insert. The database unique constraint is the final barrier; catch the violation and convert it into an appropriate business message.

### 6.2 Nulls and Application-Layer Validation

Bean Validation can be used for early feedback:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Entity
public class Contact {

    @Id
    private Long id;

    @NotBlank
    @Email
    @Size(max = 180)
    @Column(nullable = false, length = 180)
    private String email;
}
```

Validation annotations check data at the application layer when validation is enabled; @Column describes the mapping/schema for JPA. The two mechanisms do not replace each other. If a batch job or native SQL writes directly to the database, Bean Validation on the entity may not run; database constraints remain necessary.

### 6.3 Type and Conversion Violations

Conversion errors can happen when:

- An SQL column contains a string that cannot be converted to the Java type.
- Legacy data does not conform to the current format.
- A native query returns a numeric/date type different from the expected projection type.
- An enum in the database has a value that no longer exists in Java.
- JSON/UUID/vendor types need an appropriate converter or Hibernate type.

The solution is to inspect the actual values, column metadata, JDBC type, and converter. Do not force types with a Java cast without verifying the data is valid. For legacy data, consider cleanup migrations and testing old values before tightening mappings.

## 7. Entity State and Transaction Errors Often Mistaken for Data Errors

### 7.1 Transient, Managed, and Detached

JPA distinguishes entity states:

- **Transient**: new object, not yet managed by a persistence context.
- **Managed**: entity currently managed by an EntityManager; changes can be flushed.
- **Detached**: entity that was previously managed but is no longer attached to a persistence context.
- **Removed**: entity marked for deletion and will be deleted upon flush.

Errors such as detached entity passed to persist, object references an unsaved transient instance, or entity not found stem from the entity/relationship lifecycle. Determine which state the object is in, whether the transaction is still open, and whether persist/merge/reference operations are appropriate.

Example:

```java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                    "Customer not found: " + id));

    customer.rename(newName);
    // Entity is managed; dirty checking writes changes on flush/commit.
}
```

Inside a transaction, an entity fetched from a repository is usually managed by the current persistence context. You do not need to call save() again just for dirty checking to detect changes; however, calling save() may be useful for repository/API intent or detached entities.

### 7.2 LazyInitializationException

This error typically occurs when accessing a LAZY relationship after the persistence context has closed. How to handle it:

- Load required data within the transaction using fetch join or EntityGraph.
- Use DTO projections to fetch only the data to be returned.
- Keep data access within appropriate service transaction boundaries.
- Avoid enabling EAGER globally to mask the symptom; this can create N+1 queries or load excessive data.

Fetch join example:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithCustomer(@Param("id") Long id);
```

Not every relationship should be fetch joined in every query. For collections, pagination may have limitations or produce duplicate results; choose EntityGraph, batch fetching, or DTO queries as needed.

### 7.3 Optimistic Locking and Concurrent Updates

When two transactions read and modify the same entity concurrently, @Version helps detect that one transaction wrote first. The other transaction may encounter OptimisticLockException or Spring's OptimisticLockingFailureException.

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;

    public void decrease(int amount) {
        if (amount <= 0 || amount > quantity) {
            throw new IllegalArgumentException("Invalid amount");
        }
        quantity -= amount;
    }
}
```

The version is managed by the JPA provider; do not manually increment version in business code. When optimistic locking fails, re-read the latest state and decide whether to retry or return a conflict to the user. Retries must be bounded and only re-run safe/idempotent business logic.

### 7.4 Flush and Commit Errors

Some errors do not appear at save() because JPA may defer SQL until flush or commit. Therefore, tests should use saveAndFlush() or EntityManager.flush() when you want errors to surface immediately in tests.

A transaction can fail at the end of a method due to a constraint, deadlock, or optimistic lock. If an exception occurs on commit, read the root cause and transaction boundary; do not assume a repository method succeeded just because it did not throw immediately on the save() line.

## 8. Quick Classification Table by Symptom

| Symptom | Priority group to check | Starting point |
|---|---|---|
| App fails to start, missing bean | Configuration | Dependencies, component scan, bean definitions |
| Connection refused/authentication failed | Connection | URL, DB availability, credentials, network |
| Cannot create EntityManagerFactory | Mapping/configuration | Entity metadata, dialect, JDBC metadata, schema |
| Table/column does not exist | Mapping/schema | Migration, schema name, naming strategy |
| PropertyReferenceException | Query | Java property name in repository method |
| JPQL syntax/validation error | Query | Entity name, property, alias, parameter |
| SQLGrammarException | Query/schema | Generated SQL, dialect, table/column, and permissions |
| DataIntegrityViolationException | Data | Constraint name, values, relationships |
| ConversionFailedException | Mapping/data | Java type, JDBC type, converter |
| LazyInitializationException | Persistence context | Transaction boundary and fetch plan |
| OptimisticLockingFailureException | Concurrency | @Version, competing transactions |
| TransactionSystemException | Transaction/flush | Cause of flush/commit and rollback |

This table is only an initial guide. An SQLGrammarException could be due to an unapplied migration (deployment configuration), wrong mapping, or wrong query; always cross-check the SQL statement and the actual schema.

## 9. Enabling Controlled Logging to Find the Cause

In development or test environments, you can enable SQL and bind parameter logging:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.orm.jpa: DEBUG
    org.springframework.transaction: TRACE
```

The bind parameter logger name depends on the Hibernate version. Check the documentation for the version you are using. Do not enable TRACE bind parameter logging broadly in production without evaluating the risk of exposing data, tokens, emails, personal information, or business secrets.

You can enable SQL formatting in Hibernate configuration when you need more readable logs. Avoid logging more SQL and parameters than necessary, as it increases overhead, log volume, and data exposure risk.

When logging exceptions, capture the full cause chain, SQLState, vendor error code, and correlation/request id. Do not log only ex.getMessage() if it loses the root cause. Also never return stack traces or internal SQL statements to the client; return an API error with an appropriate code and message while keeping technical details in controlled logs.

## 10. Diagnostic Examples from Error to Fix

### Scenario A: Repository Fails to Initialize

Message: No property 'mailAddress' found for type 'Customer'.

- **Group**: query definition.
- **Cause**: derived query method references a non-existent Java property.
- **Check**: the entity has field email; the method is using findByMailAddress.
- **Fix**: change to findByEmail or add the appropriate property according to the domain and mapping.
- **Test**: initialize the repository context and invoke the method with matching and non-matching data.

### Scenario B: Query Runs but Reports Missing Column

Message: column c.created_at does not exist.

- **Group**: mapping/schema or query.
- **Possible causes**: entity/JPQL/native SQL uses created_at, but the migration has not created the column, the actual column name differs, or the app connects to the wrong schema.
- **Check**: SQL logs, table metadata, migration history, and the connected schema.
- **Fix**: align @Column(name=...), JPQL/native SQL, and migrations to a standard name.
- **Test**: initialize an empty test database with migrations and run the query.

### Scenario C: Insert Fails with Duplicate Email

Message: DataIntegrityViolationException, unique constraint violation.

- **Group**: data/constraint.
- **Cause**: the email already exists or two requests inserted concurrently.
- **Check**: constraint name, existing data, competing transactions.
- **Fix**: keep the unique constraint; catch the error at the service boundary and translate it into a business error “email is already in use”.
- **Test**: test sequential duplicates and concurrent duplicates if the risk is high.

### Scenario D: LazyInitializationException When Returning JSON

Message: could not initialize proxy - no Session.

- **Group**: persistence context/fetch plan.
- **Cause**: controller/serializer accesses a LAZY relationship after the service transaction has ended.
- **Fix**: service loads required data and returns a DTO; selectively use fetch join/EntityGraph.
- **Test**: call the service, close the persistence context, then serialize the DTO and verify no unexpected queries are issued.

## 11. Checklist-Based Troubleshooting Workflow

- [ ] Record the timing of the error: startup, repository creation, method call, flush, or commit.
- [ ] Read the outermost exception and the entire Caused by chain.
- [ ] Identify the DBMS, version, JDBC driver, and active profile.
- [ ] Capture the generated SQL and SQLState/vendor error code when available.
- [ ] Cross-check entity mapping against the actual migration/schema.
- [ ] Check query methods, JPQL/native SQL, parameter names, and return types.
- [ ] Check input data, nullability, length, precision, and constraints.
- [ ] Check persistence context, fetch plan, and transaction boundaries.
- [ ] Reproduce with an isolated test on the exact DBMS when the error is database-dependent.
- [ ] Add a regression test for the root cause just fixed.

Do not modify multiple groups at once without evidence. Keeping a minimal reproducer helps confirm which change actually resolves the error.

## 12. Key Takeaways

- **Configuration/connection**: check beans, profiles, DataSource, drivers, transaction managers, schemas, and permissions.
- **Mapping**: check @Entity, @Id, @Column, relationships, Java/SQL types, and migrations.
- **Query**: distinguish derived queries, JPQL, and native SQL; cross-check Java properties, entity names, parameters, and results.
- **Data**: check nulls, constraints, conversions, duplicate data, entity state, and concurrency.
- Read the cause chain, SQL, and vendor error code before making fixes.
- Flush/commit may be when the error actually surfaces; save() returning does not prove the transaction committed.
- Regression tests on the right DBMS help prevent errors that only appear upon deployment.

## 13. References

- [Spring Data JPA — Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Hibernate ORM — User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
