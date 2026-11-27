# Single-Result Query Returns Multiple Rows or No Results

In **Spring Data Relational JDBC**, a repository method can return a single entity, an `Optional<T>`, or a collection. The return type expresses how many results the application expects. If a query declared to return a single entity finds multiple rows in the database, Spring Data does not arbitrarily pick one row: the operation typically fails with `IncorrectResultSizeDataAccessException`. If no rows are found, the outcome depends on the return type: `Optional` becomes empty, collections become empty, and a bare single entity type may return `null`.

This issue commonly occurs when querying by email, order number, phone number, or a business key whose data is no longer unique in practice. It can also appear when a join produces multiple rows for a single entity. To handle it properly, clarify whether the query genuinely means "at most one row", "pick one best matching row", or "return all matching rows".

## 1. Three Query Cardinality Cases

A query can yield three outcomes:

| Matching rows | Meaning | Expected outcome |
| ---: | --- | --- |
| 0 | No matching data | Empty, null, or empty collection depending on return type |
| 1 | Exactly one row | Corresponding entity/value |
| 2 or more | Multiple matching rows | Collection if the query is designed for multiple; error if declared for a single result |

Example of finding an order by number:

```sql
SELECT id, order_number, customer_id, status
FROM purchase_order
WHERE order_number = 'PO-2026-001';
```

If order_number is a unique key, the query should return 0 or 1 row. If the database holds two rows with the same order_number due to a missing unique constraint or dirty legacy data, a method returning a single entity no longer satisfies its cardinality assumption.

Before choosing a return type, answer these business questions:

- Can the record be absent?
- If present, is there at most one record by data invariant?
- If multiple valid records exist, does the application need all of them or only the newest/oldest one?
- If multiple records appear unexpectedly, is that a data defect to surface or a valid scenario to handle?

## 2. Single Return Type: Entity or Value

A query method can return a single entity:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    PurchaseOrder findByOrderNumber(String orderNumber);
}
```

With this style of query method:

- If exactly one row matches, the repository returns the entity.
- If no rows match, the result may be `null`.
- If multiple rows match, Spring Data throws a result-size error rather than picking an arbitrary row.

Because absence is possible, callers must check for null before dereferencing:

```java
PurchaseOrder order =
        repository.findByOrderNumber("PO-2026-001");

if (order == null) {
    throw new OrderNotFoundException("Order does not exist");
}

order.confirm();
```

If the domain treats "not found" as a normal outcome, `Optional<PurchaseOrder>` usually communicates intent more clearly.

Do not use a bare entity return type simply because the application assumes the data "must exist". Queries can still find nothing due to bad IDs, deleted rows, tenant filters, soft-delete conditions, or changing data state.

## 3. Optional: No Rows Yields Optional.empty()

`Optional<T>` is a strong fit for queries where an entity might not be found:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
```

Usage:

```java
Optional<PurchaseOrder> result =
        repository.findByOrderNumber("PO-2026-001");

if (result.isEmpty()) {
    // Handle the not-found case.
}

PurchaseOrder order = result.orElseThrow(
        () -> new OrderNotFoundException("Order does not exist")
);
```

On Spring Data repositories, methods such as `CrudRepository.findById(id)` also return `Optional<T>`:

```java
Optional<PurchaseOrder> result = repository.findById(123L);
```

If the ID does not exist, the result is `Optional.empty()`. Callers can decide whether to return HTTP 404, skip the operation, or apply a default value depending on the use case.

### 3.1. Optional does not limit rows in SQL

Important detail: `Optional<T>` means at most one entity is expected. It does not automatically inject `LIMIT 1` into SQL, nor does it pick the first row.

If the query:

```sql
SELECT id, email, display_name
FROM customer
WHERE email = 'alex@example.com';
```

returns two rows, the method:

```java
Optional<Customer> findByEmail(String email);
```

does not return one of the two results. Spring Data throws `IncorrectResultSizeDataAccessException` because the query violated the single-result expectation.

Do not use Optional as a way to hide duplicate data. If email must be unique, enforce that invariant in the database with a unique constraint/index.

## 4. Collection: No Rows Yields an Empty Collection

If multiple results are valid, declare a collection:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);
```

Outcomes:

- No orders: empty list.
- One order: single-element list.
- Multiple orders: list containing all matching rows.

Example:

```java
List<PurchaseOrder> orders =
        repository.findByCustomerId(customerId);

if (orders.isEmpty()) {
    // Customer has no orders yet.
}
```

There is no need to use null to represent an empty collection. Repository collection methods normally return empty collections, so code can call `isEmpty()` directly.

Depending on the use case, the collection return type can be `List<T>`, `Collection<T>`, or another suitable collection type. When iterating over large datasets, consider streaming/scrolling according to the capabilities and contracts of your Spring Data version; manage transactions and resource lifetimes properly.

## 5. Empty Query Results by Return Type

Common return types have distinct semantics when nothing matches:

| Return type | When no rows match | When multiple rows match |
| --- | --- | --- |
| Single entity, e.g., `PurchaseOrder` | `null` | `IncorrectResultSizeDataAccessException` |
| `Optional<PurchaseOrder>` | `Optional.empty()` | `IncorrectResultSizeDataAccessException` |
| `List<PurchaseOrder>` | Empty list | List containing all results |
| `Collection<PurchaseOrder>` | Empty collection | Collection containing all results |
| `Set<PurchaseOrder>` | Empty set | Results per Set and equality semantics |
| `Stream<PurchaseOrder>` | Empty stream | Stream of results; must close/manage resources per contract |

Do not confuse single-entity query methods with CRUD methods that have their own contracts. For instance:

- `findById(id)` returns `Optional<T>`.
- `findAll()` returns an iterable/collection of entities.
- `findAllById(ids)` returns only found entities; nonexistent IDs do not produce null placeholders in the result.

## 6. IncorrectResultSizeDataAccessException

When a query declared to return a single result actually returns multiple rows, Spring Data typically throws:

```java
org.springframework.dao.IncorrectResultSizeDataAccessException
```

This exception belongs to the Spring DAO exception hierarchy. It indicates that the actual number of results does not match what the operation expected.

Example:

```java
Optional<Customer> customer =
        customerRepository.findByEmail("alex@example.com");
```

If the data contains two customers with the same email, calling the repository fails immediately at the persistence layer. The service should not catch the exception and arbitrarily pick a row, as doing so hides a data integrity violation.

### 6.1. Why does this exception occur?

Common causes:

- A column assumed to be unique lacks a database unique constraint.
- Data imports/migrations created duplicate records.
- Query filters are incomplete—for example, filtering only by code instead of tenant ID and code.
- A one-to-many join causes the query to return multiple rows for one root entity.
- A custom query has a UNION or join producing duplicate rows.
- A query previously had unique data, but business rules later changed.

### 6.2. Do not catch the error just to pick a random row

Avoid doing this:

```java
try {
    return repository.findByEmail(email);
} catch (IncorrectResultSizeDataAccessException ex) {
    // Do not arbitrarily pick a customer to continue processing.
    return Optional.empty();
}
```

This code turns a data corruption error into "not found", potentially routing data or actions to the wrong user. If multiple rows violate an invariant, fail loudly, log sufficient safe context, and fix the data/schema.

If multiple rows are valid, change the query contract to a collection or a deterministically ordered "first/top" query.

## 7. Enforcing Uniqueness in the Database

If a value must be unique, the database should enforce that invariant. For example, unique login email:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email);
```

Or unique order number:

```sql
ALTER TABLE purchase_order
ADD CONSTRAINT uk_purchase_order_number UNIQUE (order_number);
```

Unique constraints help:

- Prevent two concurrent transactions from creating the same unique value.
- Preserve invariants across multiple application instances.
- Protect data when scripts, imports, or other apps write to the database.
- Back up the single-result assumption of repository query methods.

### 7.1. Checking and cleaning duplicate data before adding constraints

Before adding a unique constraint, find existing duplicates:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

For composite business keys:

```sql
SELECT tenant_id, external_code, COUNT(*) AS duplicate_count
FROM customer
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Before running the migration:

1. Define the rule determining which record to keep.
2. Merge or reassign referencing rows if foreign keys exist.
3. Delete or fix duplicate rows per approved policy.
4. Re-run the duplicate check query.
5. Create the unique constraint/index via migration.
6. Test insert behavior for duplicate values.

Do not automatically delete duplicates solely based on smaller/larger IDs unless the business has confirmed which record is authoritative.

### 7.2. Composite unique constraints

A value may be unique only within a tenant or parent scope. For example, external_code is unique per tenant:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_external_code
UNIQUE (tenant_id, external_code);
```

Repository queries must include every column in the business key:

```java
Optional<Customer> findByTenantIdAndExternalCode(
        Long tenantId,
        String externalCode
);
```

Filtering by externalCode while omitting tenantId can validly return multiple rows. In that case, the problem is not the repository; the query fails to express the full business key.

### 7.3. Uniqueness and NULL vary by database

Unique constraint semantics for NULL values differ across databases and may offer configurable options. PostgreSQL treats NULLs as distinct by default in standard unique constraints, allowing multiple rows with NULL in a unique column. PostgreSQL also offers `NULLS NOT DISTINCT` on supported versions.

If business rules require every row to have a unique value, you typically need `NOT NULL` alongside `UNIQUE`:

```sql
ALTER TABLE customer
ALTER COLUMN email SET NOT NULL;

ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email);
```

Verify your database's semantics before relying on a unique constraint to protect queries.

## 8. When Business Logic Needs Only One Row: First or Top

Sometimes multiple rows are valid, yet the use case only needs the newest or highest-priority record. In that situation, use an explicitly bounded query instead of an unbounded single-entity method.

Spring Data supports `First` and `Top` keywords in derived queries:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

This method expresses the intent to fetch at most one latest order for a customer. `IdDesc` acts as a tie-breaker so ordering remains deterministic when two orders share the same createdAt.

Variants:

```java
Optional<PurchaseOrder> findTopByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);

List<PurchaseOrder> findTop5ByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

With `First`/`Top`:

- No rows: Optional empty when the return type is Optional.
- One row: returns that row.
- Multiple rows: database/repository limits results to the specified count.

### 8.1. Always use deterministic ordering

Avoid:

```java
Optional<PurchaseOrder> findFirstByCustomerId(Long customerId);
```

Without `ORDER BY`, the database makes no guarantee about which row counts as "first". Results can shift after adding an index, vacuuming, changing query plans, or updating rows.

Prefer:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

Deterministic ordering requires enough columns to break ties among rows with equal sort keys. Appending the primary key as a tie-breaker is standard practice.

### 8.2. First/Top differs from enforcing uniqueness

If email must be unique, using FirstByEmail to dodge exceptions hides duplicate data. First/Top is appropriate when "select one row by priority order" is a genuine business requirement, such as the latest record or most recent event.

## 9. Limiting Results with SQL in @Query

For custom queries, you can use database-specific row-limiting syntax. PostgreSQL example:

```java
@Query("""
    SELECT id, customer_id, order_number, status, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """)
Optional<PurchaseOrder> findLatestOrder(
        @Param("customerId") Long customerId
);
```

The SQL has `LIMIT 1`, so it returns at most one row. However, `LIMIT 1` neither replaces a unique constraint nor determines which row to pick without an `ORDER BY`.

Non-deterministic example:

```sql
SELECT *
FROM purchase_order
WHERE customer_id = 42
LIMIT 1;
```

The database may return any matching row. If you need the latest one, sort explicitly:

```sql
SELECT *
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

Row-limiting SQL varies by dialect. PostgreSQL and MySQL typically use `LIMIT`; SQL Server uses `TOP` or `OFFSET/FETCH`; Oracle syntax depends on version. If the application requires portable SQL, consider First/Top derived queries or dialect-aware queries.

## 10. Joins Can Multiply Rows for a Single Entity

A subtle cause is a query joining a parent table with a child table. For example:

```sql
SELECT o.id, o.order_number, o.status
FROM purchase_order o
JOIN order_line l
  ON l.purchase_order_id = o.id
WHERE o.order_number = 'PO-2026-001';
```

If the order has three lines, the SQL returns three rows for the same root order. A repository method declared to return a single `PurchaseOrder` will fail with a multiple-results error, even though only one order exists in purchase_order.

### 10.1. Use EXISTS when only checking for matching children

If the goal is to find an order with at least one line matching a specific SKU, use EXISTS:

```sql
SELECT o.id, o.order_number, o.status
FROM purchase_order o
WHERE o.order_number = 'PO-2026-001'
  AND EXISTS (
      SELECT 1
      FROM order_line l
      WHERE l.purchase_order_id = o.id
        AND l.sku = 'SKU-CHAIR'
  );
```

EXISTS checks for child existence without multiplying root rows by the number of matching children.

### 10.2. Use DISTINCT when semantics truly call for deduplication

You can write:

```sql
SELECT DISTINCT o.id, o.order_number, o.status
FROM purchase_order o
JOIN order_line l
  ON l.purchase_order_id = o.id
WHERE o.order_number = 'PO-2026-001';
```

However, DISTINCT only removes rows where all selected columns match. If the projection includes child columns, rows remain distinct. Do not use DISTINCT to paper over an incorrect join or corrupt data.

### 10.3. Spring Data JDBC does not deduplicate via a persistence context like an ORM

Spring Data JDBC does not maintain a JPA-style persistence context or identity map to merge joined rows into a single aggregate instance. Custom queries must return result sets matching the method's mapping contract. If a query needs an aggregate with children, design queries/repositories around Spring Data JDBC's model or split root and child queries appropriately.

## 11. Aggregate Queries and Scalar Results

Not every query returning a single scalar value shares entity-query semantics.

For example, `COUNT(*)` with no matching rows still returns one row containing 0:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE customer_id = 42;
```

Thus the method:

```java
long countByCustomerId(Long customerId);
```

returns 0 when the customer has no orders. This is not a "no result row" case.

Conversely, aggregate functions such as `SUM` or `AVG` can return NULL when there are no input rows (depending on the expression/query). If you need a default value, use `COALESCE`:

```sql
SELECT COALESCE(SUM(quantity), 0)
FROM order_line
WHERE purchase_order_id = 999;
```

With `GROUP BY` queries, there may be zero groups and therefore zero result rows. Distinguish a NULL/0 aggregate value from a query returning no rows at all.

## 12. Empty Scalar Queries and Java Primitives

If a custom query returns a scalar such as a count, name, or total, the return type must accurately reflect the possibility of no result.

Example:

```java
@Query("""
    SELECT MAX(created_at)
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
Instant findLatestCreatedAt(@Param("customerId") Long customerId);
```

MAX over an empty set can return SQL NULL. Java reference types can represent null; primitive types like `long` or `int` cannot. When a value may be absent, consider an appropriate wrapper or Optional:

```java
@Query("""
    SELECT MAX(created_at)
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
Optional<Instant> findLatestCreatedAt(
        @Param("customerId") Long customerId
);
```

Verify scalar mapping capabilities for your Spring Data JDBC version. For aggregate queries that always return one row such as COUNT, primitive types fit if the database always yields a non-null value.

## 13. Diagnosing Unexpected Multi-Row Queries

When encountering `IncorrectResultSizeDataAccessException`, do not immediately change the return type to List. First diagnose the cause:

1. Record the repository method and actual SQL query.
2. Confirm whether filter predicates include the full business key.
3. Run the query directly to count matching rows.
4. Check whether a join multiplies root rows.
5. Check for duplicate data on supposedly unique keys.
6. Check whether tenant, soft-delete, or status filters were omitted.
7. Decide whether multiple rows represent a data bug or a valid use case.
8. Fix the query, add a unique constraint, or change the return type accordingly.

Diagnostic queries:

```sql
SELECT order_number, COUNT(*) AS row_count
FROM purchase_order
GROUP BY order_number
HAVING COUNT(*) > 1;
```

For tenant-aware keys:

```sql
SELECT tenant_id, external_code, COUNT(*) AS row_count
FROM customer
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

If the repository query includes extra status/tenant predicates, reproduce those exact predicates to pinpoint the offending rows.

## 14. Testing 0, 1, and Multiple Results

Tests should cover all three cardinalities. Example repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByRegion(String region);

    Optional<Customer> findFirstByRegionOrderByCreatedAtDescIdDesc(
            String region
    );
}
```

### 14.1. Zero results

```java
@Test
void returnsEmptyWhenEmailDoesNotExist() {
    assertThat(repository.findByEmail("missing@example.com"))
            .isEmpty();
}
```

### 14.2. One result

```java
@Test
void returnsCustomerWhenEmailMatchesOneRow() {
    repository.save(new Customer(null, "alex@example.com", "NORTH"));

    Optional<Customer> result =
            repository.findByEmail("alex@example.com");

    assertThat(result).isPresent();
    assertThat(result.orElseThrow().email())
            .isEqualTo("alex@example.com");
}
```

### 14.3. Multiple results with a single return type

If the test schema has no unique constraint on email, you can insert two duplicate rows to confirm the repository throws:

```java
@Test
void throwsWhenSingleResultQueryMatchesMultipleRows() {
    repository.save(new Customer(null, "duplicate@example.com", "NORTH"));
    repository.save(new Customer(null, "duplicate@example.com", "SOUTH"));

    assertThatThrownBy(() ->
            repository.findByEmail("duplicate@example.com")
    ).isInstanceOf(IncorrectResultSizeDataAccessException.class);
}
```

This test requires a schema fixture permitting duplicates. If production has the proper unique constraint, duplicate inserts will fail directly in the database and uniqueness tests should verify that constraint separately. You can use another query without a unique invariant to test result-size exceptions.

### 14.4. Multiple valid results with a collection

```java
@Test
void returnsAllCustomersInRegion() {
    repository.save(new Customer(null, "a@example.com", "NORTH"));
    repository.save(new Customer(null, "b@example.com", "NORTH"));

    assertThat(repository.findAllByRegion("NORTH"))
            .hasSize(2);
}
```

### 14.5. Selecting one row by ordering

```java
@Test
void returnsLatestCustomerForRegion() {
    repository.save(new Customer(
            null, "older@example.com", "NORTH", T0));
    repository.save(new Customer(
            null, "newer@example.com", "NORTH", T1));

    Optional<Customer> result =
            repository.findFirstByRegionOrderByCreatedAtDescIdDesc(
                    "NORTH");

    assertThat(result.orElseThrow().email())
            .isEqualTo("newer@example.com");
}
```

Tests should use distinct timestamps or verify the tie-breaker ID to prove deterministic ordering.

## 15. Database Constraints and Race Conditions

An unsafe pattern is pre-checking before inserting:

```java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email));
}
```

Two concurrent transactions can both check and see that the email does not exist, then both insert. This is a race condition:

```text
Transaction A                 Transaction B
      │                             │
      ├── exists(email)? false      │
      │                             ├── exists(email)? false
      ├── insert(email)             │
      │                             ├── insert(email)
      ▼                             ▼
   Duplicate if no unique constraint exists
```

An application may pre-check for friendlier feedback, but a database unique constraint is the final safeguard. When two transactions race, one insert succeeds and the other receives a duplicate key/unique violation error.

Handle that error in the service and translate it into an appropriate business error, such as EmailAlreadyRegisteredException. Do not rely on pre-checks to guarantee uniqueness.

## 16. Transactions and Data Changing Between Reads

A query may return one row initially while data changes afterward. For example, a service reads a customer by email and performs another step. If another transaction modifies the email or creates a duplicate in a schema lacking a unique constraint, a subsequent read may yield different results.

If uniqueness is an invariant, enforce it with a database constraint. If a sequence of reads and writes requires consistency, design appropriate transaction isolation and locking. Switching the return type to Optional does not fix race conditions or enforce uniqueness.

For "fetch latest record" queries, use stable sort keys and transaction semantics suited to the use case. If new data arrives continuously, two calls to the same query may validly return different rows.

## 17. Common Pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| IncorrectResultSizeDataAccessException | Single-result method matches multiple rows | Check duplicates, predicates, joins, and invariants |
| Optional empty even though caller expects data | Insufficient query filter or data is deleted/hidden | Check SQL, tenant/status/soft-delete filters, and fixtures |
| NullPointerException after query | Bare single-entity method returned null on no rows | Use Optional or check for null |
| Still getting multi-row error despite using Optional | Optional neither adds LIMIT nor deduplicates | Add unique constraint, switch to collection, or use First/Top appropriately |
| findFirst returns different rows across runs | Missing ORDER BY or non-unique sort key | Add deterministic ordering and a tie-breaker |
| Join query returns multiple rows per root | One-to-many join multiplies result rows | Use EXISTS, query root separately, or use a suitable projection |
| Duplicates appear only under concurrency | Pre-check cannot prevent race conditions | Add unique constraint and handle unique violations |
| COUNT returns 0 yet code treats it as no result row | COUNT aggregate still returns one row | Handle 0 as a valid result |
| SUM returns null on empty set | SQL aggregate has no input values | Use Optional/wrapper or COALESCE |
| Unique constraint allows multiple NULLs | Database NULL semantics | Combine NOT NULL or appropriate unique options |

## 18. Return Type Selection Workflow

When declaring a repository query, follow this decision flow:

1. Can the query validly return multiple rows?
   - Yes: use List/Collection/Stream as appropriate.
   - No: continue.
2. Is "not found" a normal outcome?
   - Yes: prefer Optional.
   - No: use Optional and convert empty into a business error in the service, or use another explicit contract.
3. Is uniqueness enforced by the database?
   - Yes: verify the unique constraint/index matches the query predicate.
   - No: if it must be unique, add a migration and clean up duplicate data.
4. Are multiple rows valid while only one prioritized row is needed?
   - Yes: use First/Top or row-limited SQL with a deterministic ORDER BY.
   - No: return a collection or fix the query/invariant.
5. Does the query contain a join that duplicates root rows?
   - Yes: adjust the query/projection or use EXISTS/DISTINCT where semantically sound.
6. Write tests covering 0, 1, and multiple rows to verify the contract.

## 19. Practice Exercises

**Exercise 1 — Optional with no results.** Write findByEmail returning Optional<Customer>. Query a nonexistent email and confirm Optional.empty().

**Exercise 2 — Bare single entity returning null.** Create a finder returning Customer directly. Observe the not-found case and handle null; then switch to Optional.

**Exercise 3 — Multiple rows for Optional.** Insert two rows with the same email in a test schema without a unique constraint. Call the Optional finder and confirm IncorrectResultSizeDataAccessException.

**Exercise 4 — Collection.** Change the finder to List<Customer>, create two rows in the same region, and confirm both are returned; when none match, an empty list is returned.

**Exercise 5 — First/Top.** Write findFirstByCustomerIdOrderByCreatedAtDescIdDesc. Create multiple orders and verify the latest record is selected deterministically.

**Exercise 6 — Unique constraint.** Detect duplicate rows, clean them via migration, and add a unique constraint. Test duplicate inserts and translate the database error into a business exception.

**Exercise 7 — Composite key.** Create a unique constraint on tenant_id and external_code. Write a repository method using both columns; compare it with a method filtering only external_code.

**Exercise 8 — Join multiplying rows.** Write a query joining purchase_order and order_line. Create an order with multiple lines, observe the result row count, and fix using EXISTS or an appropriate query.

**Exercise 9 — Scalar aggregates.** Compare COUNT(*) and SUM() on an empty set. Test COALESCE and wrapper/Optional return types.

**Exercise 10 — Race condition.** Run two concurrent transactions registering the same email. Confirm the unique constraint allows only one transaction to succeed.

**Exercise 11 — Cardinality testing.** Write tests for 0, 1, and multiple results on a repository. Use the target database if behavior depends on unique/NULL semantics.

### References

- [Spring Data Commons — Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html): semantics of single entities, Optional, collections, and result types.
- [Spring Data JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository queries, mapping, and persistence in Spring Data JDBC.
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html): exception abstraction and data access error handling.
- [Spring Framework — DataAccessUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html): utilities for handling single and multiple results.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): unique, primary key, foreign key, NOT NULL, and NULL semantics.
- [MySQL — InnoDB Constraints](https://dev.mysql.com/doc/refman/8.4/en/constraints.html): constraints and uniqueness enforcement in MySQL.
