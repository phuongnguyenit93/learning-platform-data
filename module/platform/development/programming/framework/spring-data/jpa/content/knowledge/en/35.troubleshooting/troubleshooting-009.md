# IncorrectResultSizeDataAccessException and Non-Unique Data

## 1. What Does This Error Mean?

`IncorrectResultSizeDataAccessException` is a Spring DAO exception indicating that a query operation received a different number of results than the caller or API expected. A common case in Spring Data JPA is a repository method declared to return a single Entity or `Optional<Entity>`, while the actual query matches multiple rows.

For example, business logic assumes email is unique:

```java
Optional<Customer> findByEmail(String email);
```

If the database contains two customers with the same email, Spring Data cannot arbitrarily pick one record to return as a single result. Depending on the execution path/provider, the error may surface as `IncorrectResultSizeDataAccessException`, translated from a JPA cardinality error.

Key takeaway: **a singular return type expresses an expectation about result count, but does not itself enforce uniqueness in the database**. If uniqueness is a business rule, protect it in the database and control both legacy data and new write paths.

## 2. Distinguishing Related Exceptions

| Exception | Common meaning |
| --- | --- |
| `IncorrectResultSizeDataAccessException` | Spring DAO received a different number of results than expected |
| `EmptyResultDataAccessException` | A single result was expected but no row matched; this is a subclass of `IncorrectResultSizeDataAccessException` |
| `jakarta.persistence.NonUniqueResultException` | A JPA query expected a single result but got multiple results |
| `DataIntegrityViolationException` | A write operation violated a data constraint, such as unique or foreign key |

Do not confuse a read query returning multiple rows with a write failing on a duplicate unique key. The former is read result cardinality; the latter is the database rejecting a write due to a constraint violation.

Spring can translate persistence provider exceptions into the `DataAccessException` hierarchy. The exact exception observed depends on the called API, Spring Data/JPA provider, and error location. When diagnosing, inspect both the root exception (`cause`) and the executed SQL.

## 3. Return Types Determine Expected Cardinality

Spring Data repositories support various return types with different semantics:

| Return type | Meaning |
| --- | --- |
| `Optional<Customer>` | Zero or one result; multiple results cause an error |
| `Customer` | A single result; when absent, typically returns null per query method semantics; multiple results cause an error |
| `List<Customer>` / `Collection<Customer>` | Zero, one, or many results allowed |
| `Page<Customer>` / `Slice<Customer>` | Paginated result set |
| `boolean` from `existsBy...` | Only checks whether at least one result exists |
| `long` from `countBy...` | Number of matching results |

Example:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByEmail(String email);

    boolean existsByEmail(String email);

    long countByEmail(String email);
}
```

Choose the return type based on business rules. If emails are allowed to repeat, use `List<Customer>` or an appropriate collection type. If emails must be unique, keep `Optional<Customer>` and enforce a unique constraint in the database.

`Optional` only represents the zero-result case. It does not mean "pick the first result" and does not automatically handle multiple duplicate rows.

## 4. Repository Methods Prone to This Error

### Derived Query Returning a Single Entity

```java
Optional<Customer> findByExternalId(String externalId);
```

This method assumes `externalId` identifies at most one Customer. If multiple rows share the same external ID, the query cannot satisfy the return type.

### JPQL @Query Returning a Single Result

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findOneByEmail(@Param("email") String email);
```

JPQL does not automatically ensure `email` is unique. If data has two matching rows, the cardinality error still happens.

### findOne with Example or Specification

`QueryByExampleExecutor.findOne(example)` and `JpaSpecificationExecutor.findOne(specification)` also require at most one result. If the probe/specification predicate matches multiple Entities, you cannot use `findOne` to arbitrarily pick one row; use `findAll` or ensure the predicate is unique.

### Querydsl findOne

`QuerydslPredicateExecutor.findOne(predicate)` also expresses a singular query. If the predicate matches multiple Entities, Spring Data reports a result-size error instead of silently picking one row.

## 5. First/Top Differs from Guaranteed Uniqueness

If business logic truly wants one result according to an ordering, Spring Data provides `First` or `Top` derived queries:

```java
Optional<Customer> findFirstByEmailOrderByCreatedAtDescIdDesc(String email);
```

This method limits results and selects the latest record by `createdAt`, using `id` as a tie-breaker. It does not prove email is unique; other matching records still exist.

Only use `First`/`Top` when business rules define an explicit selection rule, such as the newest version or highest-priority record. Always specify a deterministic `OrderBy`; without ordering, "the first record" can be non-deterministic.

Do not use `findFirstBy...` to mask duplicate data when the true rule requires uniqueness. Doing so lets data corruption persist and another request may receive a different record.

## 6. Common Causes

**Duplicate data already exists in the database.** Past imports, migrations, manual edits, or prior bugs may have created multiple rows with the same business key.

**Missing unique constraint.** The Java method returns `Optional`, while the schema only has a non-unique index or no uniqueness constraint.

**Unique constraint scoped improperly.** For example, email must be unique per tenant, yet the schema lacks a composite unique constraint `(tenant_id, email)` or the query omits the tenant filter.

**Case sensitivity and normalization differences.** `User@example.com` and `user@example.com` may be treated as equal or distinct depending on database collation and business rules. Whitespace, Unicode normalization, or phone number formatting can also produce multiple representations of the same value.

**JOIN queries multiplying rows.** Joining a root entity to multiple child rows can create multiple result rows for the same root. This can be query-shape duplication rather than two Entities with the same ID.

**Underspecified predicates.** Searching by name, status, or a non-unique attribute while declaring a singular return type.

**Concurrent inserts.** Two concurrent requests both check "email does not exist yet" and both insert. Both pre-checks can succeed if no unique constraint exists.

## 7. Distinguishing Duplicate Entities from Duplicate Rows Caused by JOIN

Before adding constraints or deleting data, determine whether multiple results represent different Entities or multiple SQL rows representing the same root.

Example query:

```java
@Query("""
    select c
    from Customer c
    join c.orders o
    where o.status = :status
    """)
List<Customer> findCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

A Customer with three orders of the same status can yield three joined rows for that same Customer. If the goal is distinct Customers, you can use:

```java
@Query("""
    select distinct c
    from Customer c
    join c.orders o
    where o.status = :status
    """)
List<Customer> findDistinctCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

If you only need to check whether matching orders exist, `EXISTS` typically avoids multiplying root rows:

```java
@Query("""
    select c
    from Customer c
    where exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
          and o.status = :status
    )
    """)
List<Customer> findCustomersHavingOrderStatus(
    @Param("status") OrderStatus status
);
```

`DISTINCT` resolves duplicated root results caused by joins. It does not fix two distinct Customers sharing the same email. Conversely, a unique email constraint does not resolve joining one Customer to multiple orders. Fix the actual cause.

For queries returning scalars, tuples, or DTOs, rows with identical values may still be separate results; `DISTINCT` only deduplicates identical projections according to query semantics.

## 8. Checking Duplicate Data with SQL

To find emails appearing more than once:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

To check by business key per tenant:

```sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
```

To inspect specific IDs and rows for investigation:

```sql
SELECT c.id, c.tenant_id, c.email, c.created_at
FROM customer c
JOIN (
    SELECT tenant_id, email
    FROM customer
    GROUP BY tenant_id, email
    HAVING COUNT(*) > 1
) d
  ON d.tenant_id = c.tenant_id
 AND d.email = c.email
ORDER BY c.tenant_id, c.email, c.created_at, c.id;
```

Adjust the query to match your schema and database null semantics. If the business key is nullable, clarify whether multiple NULLs are allowed; unique handling of NULL varies across databases. For case-insensitive matching, group by the normalized expression matching system rules, such as `LOWER(email)` if supported by the database and collation.

Do not delete duplicate rows immediately upon discovery. First identify the canonical record, referencing foreign keys, business history, and how to merge data. Deleting carelessly can break relationships or audit trails.

## 9. Protecting Uniqueness with Database Constraints

If email must be globally unique, declare the constraint in the schema:

```java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;
}
```

`@UniqueConstraint` describes the constraint for schema generation. In production using Flyway/Liquibase or another migration tool, create the actual unique constraint via migration; annotations do not alter an already-deployed schema when DDL auto is disabled.

If email only needs to be unique within a tenant:

```java
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {"tenant_id", "email"}
    )
)
```

This is a composite unique constraint. Both lookup queries and uniqueness checks must use the same `(tenant_id, email)` business key. Filtering only by email without tenant allows the repository method to legitimately return multiple customers from different tenants.

## 10. Normalizing Data Before Applying Uniqueness

Unique constraints compare according to database semantics. If business rules treat emails case-insensitively, normalize consistently before writing and querying:

```java
public static String normalizeEmail(String rawEmail) {
    return rawEmail == null
        ? null
        : rawEmail.trim().toLowerCase(Locale.ROOT);
}
```

The example above is an illustrative policy. Explicitly decide how to handle Unicode, domains, local-parts, whitespace, and internationalized emails per product rules; not every email should be transformed arbitrarily. One option is storing an additional normalized key column and placing the unique constraint on that column.

With databases supporting functional unique indexes or suitable collations, uniqueness rules can be enforced in the schema. Syntax is database-dependent; document migrations clearly and test on the exact production engine.

## 11. Pre-Insert Checks Do Not Replace Unique Constraints

A service may check first to return a friendly message:

```java
if (repository.existsByEmail(normalizedEmail)) {
    throw new EmailAlreadyRegisteredException(normalizedEmail);
}

repository.save(newCustomer);
```

However, this pre-check is for user experience, not concurrency safety. Two transactions can both receive `false` from `existsByEmail` and both insert. Only a database unique constraint serves as the final safeguard.

Catch constraint violations at an appropriate service boundary and translate them into a clear business outcome, such as HTTP 409 Conflict for a duplicate resource creation request. Identify the exact constraint; do not turn every `DataIntegrityViolationException` into a duplicate-email error, because that exception can also indicate foreign key, NOT NULL, or other constraint violations.

## 12. Handling Race Conditions and Exceptions on Write

A safe flow is typically:

1. Normalize the business key.
2. Optionally check `existsBy...` for early feedback.
3. Execute INSERT inside a transaction.
4. Let the unique constraint resolve concurrent races.
5. Catch/translate the exact constraint error after the transaction fails.

Illustrative service example:

```java
@Transactional
public Customer createCustomer(String rawEmail) {
    String email = normalizeEmail(rawEmail);

    if (repository.existsByEmail(email)) {
        throw new EmailAlreadyRegisteredException(email);
    }

    try {
        return repository.saveAndFlush(new Customer(email));
    } catch (DataIntegrityViolationException ex) {
        if (isEmailUniqueConstraintViolation(ex)) {
            throw new EmailAlreadyRegisteredException(email, ex);
        }
        throw ex;
    }
}
```

`isEmailUniqueConstraintViolation` is database/driver-dependent and should be implemented by checking the constraint name or appropriate SQLState/error code. Avoid parsing generic message strings when reliable error metadata can be inspected.

`saveAndFlush()` helps surface constraint violations right at this line instead of waiting for end-of-transaction flush. If the exception marks the transaction rollback-only, do not continue using that transaction as if the insert succeeded. Translating the error to HTTP should happen after the transaction has rolled back cleanly.

## 13. Choosing the Right Query When Data Is Non-Unique

If a business key is not unique, update the query/API to reflect true cardinality:

```java
List<Customer> findAllByLastName(String lastName);
```

If you only need to check existence:

```java
boolean existsByLastName(String lastName);
```

If you only need a count:

```java
long countByLastName(String lastName);
```

If you want the latest record according to a deterministic rule:

```java
Optional<Customer> findFirstByLastNameOrderByCreatedAtDescIdDesc(
    String lastName
);
```

Do not switch from `Optional` to `List` just to silence the exception if business rules still require a unique record. Fix the data or schema if the key must be unique.

## 14. Cleaning Up Existing Duplicate Data

When adding a unique constraint to a populated table, the migration will fail if duplicate keys exist. Follow a cleanup process first:

1. Run a GROUP BY/HAVING query to list duplicate business keys.
2. Determine the canonical record by business rules; do not mechanically pick the smallest ID.
3. Identify foreign keys, child tables, audit logs, and history needing merging/re-pointing.
4. Back up or create an audit archive table before modifying critical data.
5. Merge/update references inside a controlled transaction or migration.
6. Re-run the duplicate query to verify zero violations remain.
7. Create the unique constraint in a migration.
8. Deploy new code relying on the constraint and test concurrent inserts.

On large tables, creating indexes/constraints may lock tables or require online strategies depending on the database. Plan migrations around the production engine, table size, and uptime requirements.

## 15. Testing Result Size Errors

Integration tests should cover zero, one, and multiple matches:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void listQueryCanReturnMultipleCustomers() {
        repository.save(new Customer("same@example.com"));
        repository.save(new Customer("same@example.com"));

        assertEquals(2, repository.findAllByEmail("same@example.com").size());
    }

    @Test
    void singularQueryRejectsMultipleMatches() {
        repository.save(new Customer("duplicate@example.com"));
        repository.save(new Customer("duplicate@example.com"));

        assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> repository.findByEmail("duplicate@example.com")
        );
    }
}
```

The second test demonstrates duplicate data to verify the singular repository method; it only runs if the test schema has not yet applied a unique constraint on email. Once the constraint is added, separately test that the second insert is rejected by the database and translated by Spring to the expected exception type. You cannot both enable the unique constraint and expect inserting two duplicate rows to succeed in the same test.

In `@DataJpaTest`, call `flush()` to force INSERT/constraints to run and `clear()` when you need to reload through a fresh persistence context. Slice tests usually roll back transactions upon completion; flush does not mean commit.

## 16. Testing Unique Constraints and Concurrent Inserts

A unique constraint test should save the first record, flush, and then attempt to save a second record with the same key:

```java
@Test
void databaseRejectsDuplicateEmail() {
    repository.saveAndFlush(new Customer("unique@example.com"));

    assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(new Customer("unique@example.com"))
    );
}
```

This example depends on the schema having the unique constraint and the test configuration's exception translation. After a constraint error, the transaction may become rollback-only; let the test framework roll back the test instead of issuing more queries in the failed transaction.

To test a real race condition, two independent transactions/connections must concurrently insert the same business key. One transaction must win; the other must receive a unique violation. Concurrency tests require synchronization barriers and a real database or compatible engine, not two sequential calls inside a single transaction.

## 17. Handling at the REST API Layer

Do not return stack traces or SQL messages to clients. You can map a duplicate key business error to HTTP 409:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(EmailAlreadyRegisteredException.class)
    ResponseEntity<ProblemDetail> handleDuplicateEmail(
            EmailAlreadyRegisteredException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setTitle("Email already registered");
        problem.setDetail("An account with this email already exists.");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
```

This handles the business error translated by the service from the right unique constraint. `IncorrectResultSizeDataAccessException` typically indicates a query or data violated the code's cardinality expectation; do not automatically turn it into 404 or return an arbitrary record. Log it with safe context, investigate the query and data, and return an appropriate server error if it is an internal data integrity failure.

Do not include emails, SQL, table names, or sensitive data in error responses unnecessarily.

## 18. Diagnostic Workflow When Encountering the Error

1. Read the stack trace and identify which repository method/API requested a single result.
2. Record the JPQL/SQL query, bound parameters, and return type.
3. Run an equivalent query to determine whether there are multiple distinct Entities or duplicate rows from a JOIN.
4. If it is a JOIN fan-out, consider `DISTINCT` or EXISTS; check projections and counts.
5. If it is a duplicate business key, run GROUP BY/HAVING matching the tenant scope and normalization rules.
6. Verify existing unique constraints in the database rather than relying solely on Entity annotations.
7. Check all write paths: APIs, batch jobs, imports, native SQL, and other services.
8. If there is a race condition, add a database unique constraint and handle constraint errors.
9. Write integration tests for cardinality and constraints; test concurrency when needed.

## 19. Common Mistakes and Resolutions

**`Optional<T>` still throws when two rows exist.** Optional only represents zero-or-one; enforce a unique key or switch to a collection if multiple results are valid.

**Switching to `findFirstBy...` makes the error disappear while duplicates remain.** Only keep this if there is an explicit selection rule and deterministic sort; if the key must be unique, fix the data and schema.

**Added `@Column(unique = true)` yet production still gets duplicates.** Check whether migrations actually created the constraint; annotations do not alter production schemas automatically.

**`DISTINCT` does not fix duplicate emails.** DISTINCT deduplicates query results; only a unique constraint protects the business key.

**Unique constraint still allows multiple duplicate NULL values.** Check the database's NULL semantics and determine whether the column needs NOT NULL or a partial/filtered unique index.

**Exists pre-check still allows duplicates under concurrent requests.** That is a race condition; a database constraint must be the final safeguard.

**`DataIntegrityViolationException` gets converted into duplicate email even though the real error is a foreign key.** Only translate when the specific constraint is identified; rethrow other errors.

**Query returns multiple results due to a collection join.** Check cardinality and use `distinct`/EXISTS appropriately; do not delete Entity data.

**Test fails to reproduce the error because data was not flushed.** Use `saveAndFlush()` or `entityManager.flush()` to force SQL/constraints to execute.

## 20. Prevention Checklist

- Only use singular return types when the query truly has at most cardinality one.
- Use `List`/`Page` if multiple results are valid; use `exists`/`count` if only checking or counting.
- Use `First`/`Top` only when business rules define a selection policy and deterministic ORDER BY.
- Distinguish duplicate Entities from duplicate rows caused by JOINs.
- Protect business keys with real unique constraints in the database.
- For per-tenant uniqueness, create composite unique constraints and always filter by tenant.
- Normalize keys under the same policy across writes, lookups, and constraints.
- Clean up existing duplicate data before adding constraints.
- Do not rely on exists pre-checks to prevent concurrent inserts.
- Translate only the exact unique constraint into a business error; do not swallow other integrity errors.
- Use flush/clear in integration tests when verifying the database rather than the first-level cache.
- Test zero/one/multiple results, JOIN fan-out, unique violations, and concurrent writes.

`IncorrectResultSizeDataAccessException` reports that the actual result count did not match a singular query's expectation. Determine whether the error comes from duplicate data or a JOIN multiplying rows, pick the return type matching true cardinality, and protect business keys with database constraints. `Optional`, pre-checks, and `First` cannot substitute for uniqueness when uniqueness is a business requirement.
