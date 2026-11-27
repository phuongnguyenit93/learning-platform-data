# Conditional find, count, exists, and delete in Spring Data JDBC

## 1. What Are Derived Queries?

Spring Data JDBC lets you define queries using **repository method names**. The framework parses the method name, identifies properties and condition operators, and generates an SQL statement matching the entity's mapping and the database dialect.

Instead of writing SQL manually for every simple condition:

~~~java
@Query("SELECT * FROM customers WHERE customer_code = :code")
Optional<Customer> findByCode(String code);
~~~

you can declare:

~~~java
Optional<Customer> findByCustomerCode(String customerCode);
~~~

Spring Data recognizes `findBy` as a read query and `CustomerCode` as the property to compare. This is a **derived query**.

This lesson focuses on four method groups:

- **`find...By`**: finds and returns matching entities or projections.
- **`count...By`**: counts matching rows.
- **`exists...By`**: checks whether any matching row exists.
- **`delete...By` / `remove...By`**: deletes matching rows.

Derived queries work well for common, readable conditions with minimal custom SQL. When queries involve joins, complex projections, database-specific expressions, or specialized tuning, `@Query` and explicit SQL are usually a better fit.

## 2. Method Name Structure

A derived query method name typically has the form:

~~~text
<Subject><By><Predicate><OrderBy>
~~~

Example:

~~~java
List<Customer> findByStatusAndCityOrderByDisplayNameAsc(
        CustomerStatus status,
        String city
);
~~~

It breaks down into:

- `find`: query operation type for retrieving data.
- `By`: starts the condition section.
- `StatusAndCity`: two properties joined by `And`.
- `OrderByDisplayNameAsc`: sorts ascending by the `displayName` property.

Method name parts must match **Java properties on the entity**, not necessarily SQL column names. Example:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String customerCode;

    @Column("display_name")
    private String displayName;

    private String city;

    private CustomerStatus status;
}
~~~

The method `findByCustomerCode(...)` references the `customerCode` property; the `@Column("customer_code")` metadata lets Spring Data JDBC map it to the physical `customer_code` column.

Do not write `findByCustomer_code(...)` just because the schema uses snake_case. The parser works against the Java property model.

## 3. findBy: Finding Entities by Condition

### 3.1. Finding a single entity by business key

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String customerCode);
}
~~~

Usage:

~~~java
Customer customer = customerRepository
        .findByCustomerCode("CUST-001")
        .orElseThrow(() -> new IllegalArgumentException(
                "Customer not found"
        ));
~~~

`Optional<Customer>` clearly expresses both outcomes: a result is present or absent. If the property is not guaranteed unique, a method returning a single entity can fail when multiple rows match. When business rules require exactly one customer per code, enforce a unique constraint on the business key column in the database.

`Optional` does not guarantee data uniqueness by itself; it only represents the possibility of an absent result.

### 3.2. Finding multiple entities

~~~java
List<Customer> findByCity(String city);

List<Customer> findAllByStatus(CustomerStatus status);
~~~

`findBy...` and `findAllBy...` can both be used to read a result set. With a collection return type, no matching rows normally yields an empty collection, which is convenient for iteration:

~~~java
List<Customer> customers = customerRepository.findByCity("Da Nang");

if (customers.isEmpty()) {
    // No customers in this city.
}
~~~

Choose the return type based on business cardinality:

| Return type | Representation |
|---|---|
| `Optional<Customer>` | Zero or one result |
| `Customer` | One result per contract; missing-result handling depends on query/API type |
| `List<Customer>` | Multiple results; empty if none found |
| `Iterable<Customer>` | General iterable result set |

For a method expected to return at most one result, use `Optional<T>` when absence is a normal case. Do not use `Optional<T>` as a substitute for a unique constraint.

### 3.3. Limiting result counts with First and Top

You can cap the row count using `First` or `Top`:

~~~java
Optional<Customer> findFirstByCityOrderByDisplayNameAsc(String city);

List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
        CustomerStatus status
);
~~~

`First`/`Top` is useful when you only need a few results in a deterministic order. When picking a "latest" record, always specify `OrderBy` to avoid relying on whatever order the database happens to return.

`findFirstByCity(...)` without `OrderBy` does not specify which row must be chosen when multiple rows match. Relational SQL makes no ordering guarantees without `ORDER BY`.

## 4. Common Condition Operators

Method names can use keywords to express comparison conditions. Available keywords and exact support depend on your Spring Data JDBC version; the forms below represent common patterns.

| Keyword | Meaning | Example |
|---|---|---|
| `And` | Combines two conditions with AND | `findByStatusAndCity(...)` |
| `Or` | Combines with OR | `findByStatusOrCity(...)` |
| `Between` | Within a range | `findByPriceBetween(...)` |
| `LessThan` | Less than | `findByPriceLessThan(...)` |
| `LessThanEqual` | Less than or equal to | `findByPriceLessThanEqual(...)` |
| `GreaterThan` | Greater than | `findByQuantityGreaterThan(...)` |
| `GreaterThanEqual` | Greater than or equal to | `findByPriceGreaterThanEqual(...)` |
| `Before` / `After` | Before/after for compatible date/time types | `findByCreatedAtAfter(...)` |
| `IsNull` | Null value | `findByEmailAddressIsNull()` |
| `IsNotNull` | Non-null value | `findByEmailAddressIsNotNull()` |
| `In` | Value in a set | `findByStatusIn(...)` |
| `NotIn` | Value not in a set | `findByStatusNotIn(...)` |
| `Like` | Matches SQL LIKE pattern | `findByDisplayNameLike(...)` |
| `Containing` | Contains substring | `findByDisplayNameContaining(...)` |
| `StartingWith` | Starts with string | `findByCustomerCodeStartingWith(...)` |
| `EndingWith` | Ends with string | `findByCustomerCodeEndingWith(...)` |
| `True` / `False` | Boolean value | `findByActiveTrue()` |
| `Not` | Negates equality | `findByStatusNot(...)` |
| `IgnoreCase` | Case-insensitive string comparison if supported | `findByEmailAddressIgnoreCase(...)` |

### 4.1. Combining conditions

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusOrCity(
        CustomerStatus status,
        String city
);
~~~

`And` requires both conditions to be true. `Or` requires at least one condition to be true.

With many conditions mixing `And` and `Or`, long method names can obscure the logical grouping. Verify the parser/SQL rules for your version and consider `@Query` when explicit parentheses are needed.

### 4.2. Range conditions

~~~java
List<Book> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
);
~~~

The `Between` condition typically includes both bounds, matching SQL `BETWEEN`. If business logic calls for a half-open interval (such as from the start date inclusive up to before the end date), use two explicit conditions:

~~~java
List<AuditEvent> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        Instant from,
        Instant until
);
~~~

This works well for time intervals `[from, until)`, avoiding duplicate records on the boundary between adjacent ranges.

### 4.3. String conditions

~~~java
List<Customer> findByDisplayNameContaining(String fragment);

List<Customer> findByCustomerCodeStartingWith(String prefix);

List<Customer> findByEmailAddressEndingWith(String suffix);
~~~

`Containing`, `StartingWith`, and `EndingWith` express familiar search patterns. Results depend on how the database implements `LIKE`, collation, and wildcard escaping rules.

If you need exact control over `%` or `_` in input, check how escaping works in your version and how the query is generated. Never concatenate user input into SQL.

### 4.4. Null conditions

~~~java
List<Customer> findByEmailAddressIsNull();

List<Customer> findByEmailAddressIsNotNull();
~~~

SQL uses `IS NULL`/`IS NOT NULL`, not `= NULL` comparisons. Using explicit method names makes the intent clear and prevents confusing null values with empty strings.

### 4.5. IN and NOT IN conditions

~~~java
List<Book> findByStatusIn(Collection<BookStatus> statuses);

List<Book> findByStatusNotIn(Collection<BookStatus> statuses);
~~~

This is convenient when the input is a set of values. Handle empty collections before calling the method: SQL `IN ()` does not have consistent syntax or semantics across databases, and behavior can vary by implementation.

Example:

~~~java
if (statuses.isEmpty()) {
    return List.of();
}
return bookRepository.findByStatusIn(statuses);
~~~

Decisions for empty sets must match business rules. For an empty `IN`, usually no records match; for an empty `NOT IN`, it may mean no statuses are excluded. Handling this in the service keeps semantics clear.

## 5. countBy: Counting Matching Rows

`countBy...` returns the number of records matching the predicate. Example:

~~~java
long countByStatus(CustomerStatus status);

long countByCityAndStatus(String city, CustomerStatus status);

long countByCreatedAtBetween(Instant from, Instant until);
~~~

Usage:

~~~java
long activeCustomers =
        customerRepository.countByStatus(CustomerStatus.ACTIVE);

if (activeCustomers == 0) {
    // No active customers yet.
}
~~~

Prefer `long` for counts because total row counts can exceed the range of `int`. `countBy` counts rows matching the query's conditions; if the query involves custom joins or projections, verify the exact semantics of what constitutes a row.

### 5.1. countBy vs. findBy(...).size()

Compare:

~~~java
List<Customer> customers =
        customerRepository.findByStatus(CustomerStatus.ACTIVE);

long count = customers.size();
~~~

with:

~~~java
long count =
        customerRepository.countByStatus(CustomerStatus.ACTIVE);
~~~

The first approach loads all entities into the application just to count them. The second asks the database to count the results, typically reducing transferred data and object allocations.

When you only need a count, prefer `countBy` instead of loading an entire collection. Keep in mind that count query cost still depends on indexes, predicates, the database engine, and the query plan; not every `COUNT` runs in constant time.

## 6. existsBy: Checking Whether Records Exist

`existsBy...` returns a boolean, suitable when business logic only needs to know whether at least one matching record exists:

~~~java
boolean existsByCustomerCode(String customerCode);

boolean existsByEmailAddressAndStatus(
        String emailAddress,
        CustomerStatus status
);
~~~

Example pre-creation check:

~~~java
if (customerRepository.existsByCustomerCode(code)) {
    throw new CustomerCodeAlreadyUsedException(code);
}
~~~

`existsBy` states the intent better than calling `findBy...` and checking `Optional.isPresent()`, because the application does not need the entire entity.

However, checking existence before inserting **does not replace a unique constraint**. Two concurrent requests can both receive `false` and both attempt to insert. The database must enforce uniqueness with a constraint, and the application must still handle duplicate-key errors on write.

### 6.1. existsBy is not a concurrency lock

Possible flow:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: existsByCustomerCode("C001")
    B->>DB: existsByCustomerCode("C001")
    DB-->>A: false
    DB-->>B: false
    A->>DB: INSERT C001
    B->>DB: INSERT C001
    DB-->>A: Success
    DB-->>B: Unique constraint violation
~~~

Therefore, `existsBy` is helpful for early validation and clearer error messages. It does not reserve the value, does not lock the business key, and does not guarantee the subsequent insert will succeed.

## 7. deleteBy and removeBy: Conditional Deletion

Spring Data supports derived delete methods named by condition:

~~~java
void deleteByStatus(CustomerStatus status);

void removeByCreatedAtBefore(Instant cutoff);
~~~

Example deleting expired records:

~~~java
customerRepository.deleteByStatus(CustomerStatus.EXPIRED);
~~~

`deleteBy` and `removeBy` express deleting rows that match the condition. `By` begins the predicate; keywords like `And`, `Before`, and `In` can describe the condition.

### 7.1. Choosing the return type for delete

Depending on the repository method type and Spring Data version, a delete method may return nothing or return the count of affected rows when supported. Count form example:

~~~java
long deleteByStatus(CustomerStatus status);
~~~

Verify which return types your Spring Data JDBC version and repository interface support. If you do not need the count, use `void` to signal a command. If you need an exact count of deleted rows, check the contract and verify against your target database rather than assuming every delete method returns a count identically.

For important data, do not execute broad deletes solely based on an untested predicate. You can run `countBy...` or `find...` beforehand to verify scope, while still designing transactions and deletion policies carefully.

### 7.2. Deleting by ID vs. deleting by condition

These two operations have different semantics:

~~~java
customerRepository.deleteById(id);
customerRepository.deleteByCustomerCode(code);
~~~

`deleteById` targets the entity's identifier. `deleteByCustomerCode` targets a business property. If the business key is not unique, the second call can delete multiple rows.

If the requirement is to delete exactly one customer by code, enforce uniqueness with a unique constraint. Do not rely on an assumption that codes "are normally unique."

### 7.3. Conditional deletion and aggregates

In Spring Data JDBC, an aggregate root can own child rows in other tables. When deleting an aggregate, foreign key integrity and child lifecycle rules must be preserved.

Do not assume every derived delete method has the exact same semantics as loading each aggregate and calling `repository.delete(entity)`. If an aggregate has children, callbacks, auditing, or dependent deletion rules, verify the method's behavior in your version and against your actual database. For operations requiring explicit lifecycle handling, you can find matching aggregates and delete them explicitly via the repository, or design schema cascades deliberately.

Watch out for foreign keys: if child tables are not deleted per the aggregate strategy or lack an appropriate cascade, deleting the root may be rejected by the database. Do not enable cascades blindly; choose the policy based on data ownership.

## 8. Combining find, count, exists, and delete in a Repository

Repository example:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String customerCode);

    List<Customer> findByStatusAndCity(
            CustomerStatus status,
            String city
    );

    List<Customer> findTop10ByStatusOrderByCreatedAtDesc(
            CustomerStatus status
    );

    long countByStatus(CustomerStatus status);

    boolean existsByEmailAddress(String emailAddress);

    void deleteByStatusAndCreatedAtBefore(
            CustomerStatus status,
            Instant cutoff
    );
}
~~~

A service can combine these operations:

~~~java
@Service
public class CustomerMaintenanceService {

    private final CustomerRepository customers;

    public CustomerMaintenanceService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public long removeExpiredCustomers(Instant cutoff) {
        long before = customers.countByStatusAndCreatedAtBefore(
                CustomerStatus.EXPIRED,
                cutoff
        );

        customers.deleteByStatusAndCreatedAtBefore(
                CustomerStatus.EXPIRED,
                cutoff
        );

        return before;
    }
}
~~~

In this example, the count is read before deleting and returned. Note that `count` and `delete` are two separate queries. If data changes concurrently, the count before deletion and the actual number of deleted rows may differ unless transaction isolation and locking are designed to provide a consistent snapshot.

If the repository delete method supports returning a row count in your version's contract, using that return value directly avoids a separate count query. Verify the exact semantics and supported return types.

## 9. Derived Queries Use Java Properties, Not Column Names

Entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String customerCode;

    @Column("email_address")
    private String emailAddress;

    @Column("created_at")
    private Instant createdAt;
}
~~~

Repository methods:

~~~java
Optional<Customer> findByCustomerCode(String code);

boolean existsByEmailAddress(String email);

long countByCreatedAtAfter(Instant timestamp);
~~~

The parser references the properties `customerCode`, `emailAddress`, and `createdAt`. Mapping metadata handles the physical column names `customer_code`, `email_address`, and `created_at`.

If you write `findByEmail_Address`, the parser does not treat it as an SQL column name; underscores in method names can be used to delimit property paths under parser rules, not to write physical column names.

For nested properties or embedded objects, property path naming and support depend on Spring Data JDBC's mapping and query derivation capabilities. Verify the specific mapping; do not assume you can freely query across arbitrary aggregate relationships as in an ORM.

## 10. Derived Queries vs. @Query: When to Switch to Explicit SQL?

Derived queries work well when method names remain readable and conditions map directly to properties. Example:

~~~java
List<Book> findByPriceGreaterThanEqualAndStatus(
        BigDecimal minPrice,
        BookStatus status
);
~~~

When methods become long or require database-specific SQL features, `@Query` can be clearer:

~~~java
@Query("""
    SELECT id, title, price, status
    FROM books
    WHERE status = :status
      AND price >= :minPrice
    ORDER BY price DESC, id
    """)
List<Book> findAvailableBooks(
        BookStatus status,
        BigDecimal minPrice
);
~~~

For `@Query` statements that modify data, Spring Data JDBC generally requires `@Modifying` to mark a modifying query:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :newStatus
    WHERE status = :oldStatus
    """)
int updateCustomerStatus(
        CustomerStatus oldStatus,
        CustomerStatus newStatus
);
~~~

Explicit SQL is appropriate when you need:

- Joins or database-specific expressions.
- CTEs, window functions, or complex aggregations.
- Custom aliases or projections.
- Conditions with complex parenthesized groupings.
- Multi-column updates in a single statement.
- Exact control over the SQL sent to the database.

In exchange, the author must ensure the SQL matches the schema, dialect, parameter types, and result mapping. Use named parameters to bind **data values**; never concatenate input directly into the SQL string.

## 11. Return Types and Handling Empty Results

Choosing an appropriate return type makes caller handling explicit:

| Intent | Example method | Common return type |
|---|---|---|
| Look up by code that may not exist | `findByCustomerCode(...)` | `Optional<Customer>` |
| Find multiple rows | `findByStatus(...)` | `List<Customer>` |
| Count matching rows | `countByStatus(...)` | `long` |
| Check existence | `existsByCustomerCode(...)` | `boolean` |
| Delete by condition, no result needed | `deleteByStatus(...)` | `void` |
| Delete and obtain count when supported | `deleteByStatus(...)` | Appropriate numeric type per contract |

For `Optional<T>`, multiple matching rows do not mean "pick any one row"; that violates the single-result assumption and can raise a result-size exception. If business logic requires uniqueness, the database needs a unique constraint.

For collection return types, no matching rows normally returns an empty collection. For counts, no matching rows returns zero. For exists, the result is false.

## 12. Parameter Safety and SQL Injection

Derived queries bind values through Spring Data's query mechanism. With `@Query`, use named parameters:

~~~java
@Query("""
    SELECT id, customer_code, display_name
    FROM customers
    WHERE customer_code = :code
    """)
Optional<Customer> findByCode(String code);
~~~

Do not concatenate input into SQL:

~~~java
// Unsafe:
String sql = "SELECT * FROM customers WHERE customer_code = '" + code + "'";
~~~

Prepared parameters protect **values**; they cannot substitute for table names, column names, or SQL keywords. If a user is allowed to choose a sort column, map the selection from an application-controlled allowlist.

Derived query method names are fixed at compile time and never accept raw SQL fragments from a request, so there is no string concatenation into method names.

## 13. Performance and Indexes for Query Conditions

Derived queries do not automatically guarantee fast execution. The database still evaluates predicates, sorts, and counts according to schema, indexes, and query plans.

Example method:

~~~java
Optional<Customer> findByCustomerCode(String customerCode);
~~~

If `customer_code` is a unique business key, add a unique constraint:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_customer_code UNIQUE (customer_code);
~~~

This constraint both protects data integrity and typically creates an index supporting lookups. For a query like:

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);
~~~

consider a composite index `(status, city)` after reviewing workload and query plans. Do not index every property indiscriminately; indexes increase INSERT/UPDATE/DELETE overhead and storage consumption.

For `countBy`, the database may still need to scan many index entries or rows depending on the condition. For `existsBy`, the database may stop once it finds a single match, though the actual SQL and query plan depend on the implementation and database. Measure instead of assuming every exists query has the same cost.

`deleteBy` can also be expensive if the predicate lacks an index or deletes many rows. Deleting rows also updates indexes, checks foreign keys, and writes transaction logs.

## 14. Additional Considerations for Conditions and Data

### 14.1. Case sensitivity and collation

`findByEmailAddressIgnoreCase(...)` can express case-insensitive comparisons when supported by the property type and database. However, exact rules depend on dialect, collation, and how Spring Data generates SQL.

If emails or usernames must be unique case-insensitively, ensure the unique constraint uses the same normalization rule. An `IgnoreCase` derived query does not automatically create a matching unique constraint.

### 14.2. Wildcards in LIKE

`Containing`, `StartingWith`, and `EndingWith` are normally translated into LIKE patterns. `%` and `_` act as SQL wildcards. If input may contain these characters, check how escaping works in your framework/driver or choose `@Query` with an explicit escaping strategy.

### 14.3. Dates, times, and time zones

For temporal properties, choose matching Java and SQL types. For example, `Instant` represents a point on the timeline; `LocalDate` represents a calendar date without time. When using `Before`, `After`, or `Between`, standardize time zones and timestamp storage to avoid boundary discrepancies.

### 14.4. Broad deletes

A method like `deleteByStatus(status)` can affect many rows. Before running it on critical data, verify the predicate, transaction boundaries, and deletion policy. You can use a count or preview query to estimate scope, though concurrent writes can still occur between preview and deletion.

## 15. Common Mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| Method name fails to parse | Wrong keyword or property name | Verify Java property and derived query syntax |
| `findByCustomer_code` fails | Physical column name used instead of property name | Use `findByCustomerCode` |
| `Optional` encounters multiple rows | Non-unique property when method assumes single result | Use a collection or add a unique constraint |
| `countBy` loads many entities | Using `findBy(...).size()` instead of a count query | Use `countBy...` |
| `existsBy` treated as guaranteeing uniqueness | Confusing a pre-check with a constraint | Add a unique constraint and handle duplicates |
| `IN` with an empty collection causes SQL error | SQL `IN ()` is not portable | Handle empty collections in the service layer |
| `IgnoreCase` behaves differently across databases | Different collations/dialects | Inspect the SQL and comparison rules |
| `deleteBy` deletes too many rows | Predicate too broad or missing tenant filter | Add scoping conditions and verify beforehand |
| Deleting root violates foreign key | Child/reference not handled per aggregate/schema | Check mapping, cascades, and aggregate boundaries |
| Derived query too long, hard to read | Too many conditions and OR branches | Use `@Query` or a custom repository |
| Query returns entity missing properties | Custom SELECT omits columns needed for mapping | Select all required columns or use a projection |
| Pre-delete count and actual deleted rows mismatch | Concurrent writes between two queries | Design transaction isolation/locks or use delete count if supported |

## 16. Practice Exercises

### Exercise 1 — findBy

Create `CustomerRepository` with `findByCustomerCode`, `findByStatusAndCity`, and `findTop5ByStatusOrderByCreatedAtDesc`. Insert sample data and test empty results, single results, and multiple results.

### Exercise 2 — countBy

Write `countByStatus` and `countByCreatedAtAfter`. Compare with `findByStatus(...).size()` in terms of loaded objects and execution time.

### Exercise 3 — existsBy

Write `existsByCustomerCode`. Send two concurrent requests registering the same code. Add a unique constraint and observe why one request must still handle duplicate errors even though both pre-checks may return false.

### Exercise 4 — deleteBy

Write `deleteByStatusAndCreatedAtBefore`. Prepare data with different statuses and verify that the predicate deletes only the intended subset. If the method returns a count in your version, compare the count against actual data.

### Exercise 5 — IN condition

Write `findByStatusIn`. Test multi-element, single-element, and empty collections. Implement empty-collection handling in the service layer to match business semantics.

### Exercise 6 — Converting a derived query to @Query

Take a method with several conditions and convert it to `@Query`. Compare readability, SQL control, and schema coupling.

### Exercise 7 — Indexes and query plans

Create `findByStatusAndCity` and measure query plans before and after adding an appropriate index. Also measure write cost with the index present to understand read/write trade-offs.

## 17. Key Takeaways

- Derived queries are generated from **repository method names**, predicates, and Java properties on the entity.
- `find...By` retrieves entities; use `Optional` for zero/one result and a collection for multiple results.
- `count...By` counts matching records; `exists...By` checks whether matching records exist; `delete...By`/`remove...By` deletes by condition.
- Java property names and physical column names can differ; `@Column` and naming strategies handle the mapping.
- Keywords like `And`, `Or`, `Between`, `In`, `IsNull`, `Containing`, `StartingWith`, and `OrderBy` express common conditions.
- `existsBy` does not replace a unique constraint; pre-insert checks still have race conditions.
- Conditional deletes require tight predicates, transactions, and a clear understanding of aggregate and foreign key relationships.
- When a method becomes too long or needs complex SQL, use `@Query` and `@Modifying` appropriately.
- Performance depends on indexes, collation, query plans, row counts, and index/constraint maintenance overhead; measure against the target database.
