# findById, findAll, and findAllById

In Spring Data JDBC, repositories provide basic CRUD methods to read aggregates from the database. The three most commonly used methods for retrieval by identifier are **`findById`**, **`findAll`**, and **`findAllById`**. They look simple, yet differ in return type, scope of data read, how missing IDs are handled, and scalability as data volume grows.

This lesson explains these three methods in Spring Data Commons' repository contract and how Spring Data JDBC executes them on relational aggregates. Examples use a `CustomerRepository` to illustrate fetching one customer, all customers, and a subset of customers by a list of IDs.

## 1. CRUD repositories and the role of the three methods

Spring Data Commons defines shared repository contracts. `CrudRepository<T, ID>` provides basic CRUD operations with:

- `T`: the domain object / aggregate root type managed by the repository.
- `ID`: the identifier type of the root.

The three read methods to master:

```java
Optional<T> findById(ID id);

Iterable<T> findAll();

Iterable<T> findAllById(Iterable<ID> ids);
```

In Spring Data JDBC, repositories are declared per aggregate root. Spring Data JDBC provides implementations to read those aggregates from the database and map them into domain objects.

Example:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

You do not need to write implementations for these three basic CRUD methods. When the application has Spring Data JDBC and a valid datasource configuration, Spring Data creates the appropriate repository proxy.

### 1.1. CrudRepository and ListCrudRepository

Spring Data Commons offers two commonly used contracts:

| Interface | Return type of multi-element read methods |
| --- | --- |
| `CrudRepository<T, ID>` | `Iterable<T>` |
| `ListCrudRepository<T, ID>` | `List<T>` |

If you want to receive `List` directly, you can declare:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

`ListCrudRepository` extends the CRUD contract and provides `List` return types for methods returning multiple entities. `findById` still returns `Optional<T>` because the result is at most one entity.

Choosing `CrudRepository` or `ListCrudRepository` does not change the business meaning of the query; it primarily affects the data type received by calling code.

## 2. findById(ID id): finding one aggregate by identifier

`findById` retrieves a single entity by ID:

```java
Optional<Customer> findById(Long id);
```

The result is `Optional<Customer>` because a matching row may or may not exist in the database.

Example:

```java
Optional<Customer> result = customerRepository.findById(42L);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.name());
}
```

Or using the pattern commonly seen in services:

```java
Customer customer = customerRepository.findById(customerId)
    .orElseThrow(() ->
        new CustomerNotFoundException(customerId)
    );
```

### 2.1. Why return Optional?

There are two valid outcomes:

- ID exists: Optional contains the entity.
- ID does not exist: empty Optional (`Optional.empty()`).

The method does not return `null` to represent not found. That forces callers to explicitly handle missing data instead of accidentally dereferencing a null value.

Example:

```java
Optional<Customer> result = customerRepository.findById(999L);

assert result.isEmpty();
```

If the application needs to return HTTP 404, the service can turn an empty Optional into a business exception or appropriate result. The repository does not decide HTTP status codes.

### 2.2. Invalid IDs

The ID parameter must not be `null`. Passing a null ID violates the contract and leads to `IllegalArgumentException`.

```java
customerRepository.findById(null); // Invalid
```

Validate input data at the appropriate boundary. If the ID comes from a URL or request, convert and validate it before calling the repository.

### 2.3. How does findById read an aggregate root?

Suppose `Customer` is an aggregate root with contact addresses belonging to the same aggregate:

```java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @MappedCollection(idColumn = "customer_id")
    private Set<ContactAddress> addresses = new HashSet<>();
}
```

When calling `findById`, the goal is to reconstruct the `Customer` aggregate according to its declared mapping. Spring Data JDBC is not a JPA ORM with lazy-loading proxies; the JDBC model reads aggregate data according to its mapping mechanism. Do not assume child collections are lazily loaded on getter calls like JPA's `FetchType.LAZY`.

Therefore, aggregate size affects the cost of a single read. If a root owns substantial child data, retrieving one root can require more read operations than a simple SELECT on the root table.

### 2.4. Conceptual SQL example

With table:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL
);
```

A lookup by ID conceptually looks like:

```sql
SELECT id, name
FROM customers
WHERE id = ?;
```

This expresses the meaning of the query. Actual SQL may vary by dialect, mapping metadata, column names, and Spring Data JDBC's implementation.

## 3. findAll(): reading all aggregates

`findAll` retrieves every entity managed by the repository:

```java
Iterable<Customer> findAll();
```

If the repository extends `ListCrudRepository`, the return type is `List<Customer>`:

```java
List<Customer> customers = customerRepository.findAll();
```

Example:

```java
for (Customer customer : customerRepository.findAll()) {
    System.out.println(customer.name());
}
```

### 3.1. When there is no data

If there are no customers, `findAll` returns an empty collection (an empty `Iterable`/`List`), not `null`.

```java
List<Customer> customers = customerRepository.findAll();

if (customers.isEmpty()) {
    System.out.println("No customers yet");
}
```

### 3.2. findAll has no filter condition

`findAll` accepts no filter parameters and means reading every entity in the repository. In SQL terms, you can picture:

```sql
SELECT id, name
FROM customers;
```

Do not use this method on a table with millions of rows only to filter in Java afterward:

```java
List<Customer> all = customerRepository.findAll();

List<Customer> active = all.stream()
    .filter(Customer::active)
    .toList();
```

That approach pulls all data into the application, wasting memory and bandwidth when the database could filter far more efficiently.

If you only need active customers, use a query method or appropriate conditional query:

```java
List<Customer> findByActiveTrue();
```

This is a query method derived from its method name, distinct from the `findAll` CRUD method.

### 3.3. No ordering guarantee

`findAll` has no sort parameter, so callers must not assume results arrive ordered by ID, name, or creation time. Databases do not guarantee row order when a SQL statement lacks `ORDER BY`.

If a business operation requires ordering, use the appropriate sorting/query API or an explicit query:

```sql
SELECT id, name
FROM customers
ORDER BY name ASC, id ASC;
```

Using a secondary criterion like ID keeps results deterministic when multiple records share the same name.

### 3.4. Performance risks of findAll

A single `findAll` call can trigger substantial work:

- Reading every aggregate root.
- Mapping each row into a domain object.
- Reading child components belonging to each aggregate per the mapping.
- Holding many objects in application memory simultaneously.

If aggregates contain large collections, total materialized data can far exceed the root table's size. Consider data scale before calling `findAll` in web requests or scheduled jobs.

`findAll` fits small datasets or use cases that genuinely require every record. For large lists, consider pagination, sorting, conditional queries, or a dedicated read model.

## 4. findAllById(Iterable<ID> ids): reading a set of aggregates by ID

`findAllById` accepts an iterable of IDs and returns the found entities:

```java
Iterable<Customer> findAllById(Iterable<Long> ids);
```

With `ListCrudRepository`:

```java
List<Customer> findAllById(Iterable<Long> ids);
```

Example:

```java
List<Long> ids = List.of(10L, 20L, 30L);

List<Customer> customers =
    customerRepository.findAllById(ids);
```

This method is useful when the application already holds a list of identifiers and wants to load the corresponding aggregates without calling `findById` repeatedly for each ID.

### 4.1. Missing IDs are skipped

The `findAllById` contract specifies returning only the entities found. If one or more IDs do not exist, the corresponding entities simply do not appear in the result.

Example:

```java
List<Long> ids = List.of(10L, 20L, 999L);

List<Customer> found = customerRepository.findAllById(ids);
```

Suppose the database has IDs 10 and 20 but not 999; the result contains customers 10 and 20. The method does not produce placeholders or individual Optionals for missing IDs.

This differs from repeated calls:

```java
Optional<Customer> first = repository.findById(10L);
Optional<Customer> second = repository.findById(20L);
Optional<Customer> missing = repository.findById(999L);
```

If the business operation needs to know exactly which IDs are missing, the application must compare the requested ID set against returned IDs or run an additional check.

### 4.2. Result ordering is not guaranteed

This is very important: `findAllById` **does not guarantee that result ordering matches the input ID ordering**.

Example:

```java
List<Long> requestedIds = List.of(30L, 10L, 20L);
List<Customer> customers =
    repository.findAllById(requestedIds);
```

Never assume the first element in the result is definitely Customer with ID 30. Neither the database nor the repository implementation promises this ordering.

If input ordering must be preserved, reorder the results at the application layer by ID:

```java
Map<Long, Customer> byId = customers.stream()
    .collect(Collectors.toMap(
        Customer::id,
        Function.identity()
    ));

List<Customer> ordered = requestedIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

This example preserves requested ID order and skips missing IDs. If missing IDs need to be distinguished, check for null values or construct explicit status results instead of filtering them out.

### 4.3. Null inputs

The IDs iterable must not be `null` and must not contain null IDs per the contract. Passing invalid input results in `IllegalArgumentException`.

```java
repository.findAllById(null); // Invalid

repository.findAllById(
    Arrays.asList(10L, null, 20L)
); // Invalid
```

An empty collection is valid input; the result is an empty collection.

### 4.4. Duplicate IDs in input

Do not rely on `findAllById` to preserve occurrence counts or positions of duplicate IDs in the input iterable. The contract does not guarantee ordering and is not an API that maps each input item one-to-one to a corresponding result entry.

If the business operation needs to handle each request item individually, normalize the ID list or build your own result-mapping logic against the original list. If you only need a unique set of aggregates, normalize with a `Set` before calling the repository.

### 4.5. Conceptual SQL

Conceptually, the query can be expressed as:

```sql
SELECT id, name
FROM customers
WHERE id IN (?, ?, ?);
```

This only illustrates the logic of filtering by an ID set. Do not rely on an exact single SQL statement or fixed number of round-trips: actual execution depends on the Spring Data JDBC version, dialect, ID set size, and driver/database limits.

## 5. Comparing the three methods

| Criterion | `findById` | `findAll` | `findAllById` |
| --- | --- | --- | --- |
| Input | One ID | None | Iterable of IDs |
| Scope | At most one aggregate | All aggregates in the repository | Aggregates whose IDs are in the input set |
| CrudRepository return type | `Optional<T>` | `Iterable<T>` | `Iterable<T>` |
| ListCrudRepository return type | `Optional<T>` | `List<T>` | `List<T>` |
| Non-existent ID | Empty Optional | Not applicable | Missing entity skipped |
| Ordering | Single element | Not guaranteed | Not guaranteed to match input |
| Null input | Null ID invalid | No parameters | Null iterable / null ID invalid |
| Data scale | One aggregate | Potentially very large | Depends on number of IDs passed |

### 5.1. Choosing a method by use case

- Need to load one order by ID: use `findById`.
- Need all data from a small dataset for an admin task: `findAll` can be used.
- Already have a list of IDs and need to load those aggregates: use `findAllById`.
- Need to filter, sort, or paginate a large dataset: use appropriate query/sorting/paging APIs instead of reading everything.

## 6. Complete domain and repository example

Suppose a customer management application has this schema:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL
);
```

Domain object:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String name,
    String email,
    boolean active
) {}
```

Repository:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

Service:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerQueryService {

    private final CustomerRepository customers;

    public CustomerQueryService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Optional<Customer> findOne(Long id) {
        return customers.findById(id);
    }

    @Transactional(readOnly = true)
    public List<Customer> findEveryCustomer() {
        return customers.findAll();
    }

    @Transactional(readOnly = true)
    public List<Customer> findSelected(List<Long> ids) {
        return customers.findAllById(ids);
    }
}
```

Here `@Transactional(readOnly = true)` indicates read-only use cases. Repository CRUD methods have Spring Data's default transaction configuration; service-level transactions are helpful when a use case coordinates multiple operations that need a shared transaction boundary.

The service returns `Optional<Customer>` for one ID, and `List<Customer>` for collection results because the repository extends `ListCrudRepository`. If using `CrudRepository`, the service would receive `Iterable<Customer>` and could convert to `List` only when genuinely needed.

## 7. Handling missing IDs and business requirements

`findAllById` skips non-existent IDs. This works well when callers only want the objects that exist, but not when a use case requires **every ID to exist**.

For example: a request to create a customer group requires linking exactly 3 customers. If only 2 are found, the application must report an error instead of silently proceeding with 2.

You can validate this:

```java
public List<Customer> requireAllCustomers(List<Long> requestedIds) {
    List<Customer> found = customers.findAllById(requestedIds);

    Set<Long> foundIds = found.stream()
        .map(Customer::id)
        .collect(Collectors.toSet());

    List<Long> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .distinct()
        .toList();

    if (!missingIds.isEmpty()) {
        throw new CustomerNotFoundException(missingIds);
    }

    return found;
}
```

This example assumes input IDs have already been validated as non-null. It does not depend on repository return ordering because it compares against an ID set.

If input contains duplicate IDs, `distinct()` prevents repeated IDs in the error list. If the business case needs duplicate counts preserved for detailed error reporting, omit `distinct()`.

Keep in mind that existence state can change between reading and the next operation if another transaction deletes data. Foreign keys, transaction isolation, and concurrency handling still need proper design.

## 8. findAllById is not a findAllBy... derived query method

The name `findAllById` is a built-in CRUD method on the repository contract. It takes an iterable of IDs and finds aggregates by identifier.

Meanwhile, methods like:

```java
List<Customer> findAllByActiveTrue();

List<Customer> findAllByNameContainingIgnoreCase(String keyword);

List<Customer> findAllByEmailIn(Collection<String> emails);
```

are **query methods** whose names Spring Data parses to generate queries against domain model properties.

The difference:

| Method | Origin | Meaning |
| --- | --- | --- |
| `findAll()` | CRUD contract | Read all aggregates. |
| `findAllById(ids)` | CRUD contract | Read aggregates by a set of IDs. |
| `findAllByActiveTrue()` | Query method | Filter by property `active`. |
| `findAllByNameContainingIgnoreCase(name)` | Query method | Filter using supported naming/property rules. |

You do not need to declare a custom `findAllById` method to use query derivation; that method is already part of the contract.

## 9. When data is large: pagination, sorting, and specialized queries

`findAll` has no pagination parameters. If a table holds a lot of data, do not load everything just to display one UI page.

Several approaches:

- Use repository contracts/APIs for pagination and sorting supported by the module, with `Pageable`/`Sort` when appropriate.
- Use conditional queries to narrow the dataset in the database.
- Use projections/DTOs for read models that only need specific columns.
- Use custom repositories or `NamedParameterJdbcOperations` when JOIN/aggregate queries require SQL control.
- For batch processing, split ID sets or data into reasonably sized batches.

Example of a status query method:

```java
List<Customer> findByActiveTrue();
```

This is better than calling `findAll()` and filtering `active` in Java when only active customers are needed.

If pagination is needed, pay attention to the Spring Data version and contract used. In Spring Data 3.x, `PagingAndSortingRepository` is a separate abstraction; when both CRUD and paging are needed, repositories typically extend both interfaces or use a module-supported specialized repository type.

### 9.1. findAllById with very large ID sets

If an input contains tens or hundreds of thousands of IDs, passing all of them in a single call can hit database/driver parameter limits, increase memory usage, and produce inefficient queries.

You can split into batches:

```java
List<Customer> result = new ArrayList<>();

for (List<Long> batch : partition(ids, 500)) {
    result.addAll(repository.findAllById(batch));
}
```

`partition` is a helper splitting a list into smaller chunks; the example merely illustrates batch organization and is not a standard Java API. Batch size should be chosen based on the database, driver, column count, and actual workload.

If input ordering must be preserved, combining batch results still does not guarantee ordering within each batch. Reorder by ID after loading.

## 10. findAll and aggregates with many child entities

In Spring Data JDBC, repositories manage aggregate roots rather than standalone tables. If a root has a child collection mapped with `@MappedCollection`, reading the root also involves mapping components belonging to the aggregate.

Example:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
```

`findById(orderId)` reads one `PurchaseOrder` aggregate along with its components. `findAll()` reads all `PurchaseOrder` instances and their corresponding aggregate data. Thus, if there are many orders and each order has many order lines, the actual cost can be far greater than reading just the `purchase_orders` table.

If a screen only needs order numbers and totals, consider a projection or aggregate query instead of loading all `OrderLine` items into domain objects.

### 10.1. Do not use findAllById to query arbitrary relationships

If you want all `Book` instances belonging to an `Author` and only have the author ID, `BookRepository`'s `findAllById` does not fit because it filters by **Book's ID**, not Author's ID.

You need a query method or query by reference:

```java
List<Book> findByAuthor(AggregateReference<Author, Long> author);
```

or a custom query on the `author_id` column depending on domain declaration and query derivation support. Exact semantics must match mapping/properties and the Spring Data JDBC version in use.

## 11. Testing the three methods

A Spring Data JDBC test slice can verify the core behaviors:

```java
@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void findsOneById() {
        Customer saved = customers.save(
            new Customer(null, "Lan", "lan@example.test", true)
        );

        Optional<Customer> found =
            customers.findById(saved.id());

        assertThat(found).contains(saved);
    }

    @Test
    void returnsEmptyWhenIdDoesNotExist() {
        assertThat(customers.findById(999L)).isEmpty();
    }

    @Test
    void findsAllCustomers() {
        customers.save(new Customer(null, "Lan", "lan@example.test", true));
        customers.save(new Customer(null, "Minh", "minh@example.test", false));

        assertThat(customers.findAll()).hasSize(2);
    }

    @Test
    void findsOnlyExistingIds() {
        Customer first = customers.save(
            new Customer(null, "Lan", "lan@example.test", true)
        );
        Customer second = customers.save(
            new Customer(null, "Minh", "minh@example.test", false)
        );

        List<Customer> found = customers.findAllById(
            List.of(first.id(), 999L, second.id())
        );

        assertThat(found)
            .extracting(Customer::id)
            .containsExactlyInAnyOrder(first.id(), second.id());
    }
}
```

This illustrative test needs an appropriate schema and test datasource. If `@DataJdbcTest` replaces the datasource with an embedded database by default, configure the desired database explicitly when using Testcontainers or a dedicated test database.

The assertions intentionally do not check ordering of `findAll` and `findAllById`. If a test relies on incidental ordering, it may fail on a different database or execution plan even when the result satisfies the contract.

### 11.1. Testing invalid inputs

You can add contract tests:

- `findById(null)` must be rejected.
- `findAllById(null)` must be rejected.
- `findAllById` with a null element must be rejected.
- `findAllById(emptyList())` returns an empty result.
- Missing IDs do not cause the entire call to fail; missing IDs are skipped.

There is no need to write tests for every internal SQL detail. Focus on the contract the application relies on.

## 12. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| NullPointerException after calling `findById` | Caller assumed Optional always has a value or passed a null ID. | Check Optional and validate IDs. |
| Expected repository to throw when entity not found | `findById` returns an empty Optional. | Convert empty to a business error in the service when needed. |
| `findAll` makes request slow or runs out of memory | Reading entire table and materializing many aggregates. | Use filters, pagination, projections, or batches. |
| `findAll` result order changes | No ORDER BY in the contract. | Sort explicitly using Sort/query. |
| `findAllById` result misses some elements | Non-existent IDs are skipped. | Compare requested ID set with results if all must exist. |
| `findAllById` result does not match input order | Contract does not guarantee order. | Reorder by the original ID list. |
| Using `findAllById` to filter by foreign key | Method filters by ID of the repository's own entity. | Use a query method or custom query on the reference property. |
| Loading unwanted child aggregates | Repository reads aggregate root with full mapping. | Design dedicated read queries/projections. |
| Passing a very large ID set fails the query | Database/driver parameter or resource limits. | Split into batches or use a specialized query. |

## 13. Practical rules for choosing the API

Before calling a method, clarify what data needs to be read:

1. **One aggregate by ID:** use `findById` and handle the Optional.
2. **All aggregates in a small set:** use `findAll` if you truly need every record.
3. **A set of aggregates with known IDs:** use `findAllById`, without relying on return ordering.
4. **Large datasets or needing filtering/sorting:** use query methods, sorting/pagination, or custom queries.
5. **Need every ID to exist:** check for missing IDs after `findAllById`.
6. **Need data from another aggregate:** fetch via its own repository or a combined read query; do not confuse foreign keys with aggregate children.
7. **Need to preserve input ordering:** reorder results by the original ID list.
8. **Need only a few columns or aggregated data:** use an appropriate projection/DTO instead of materializing full aggregates.

> **`findById` returns an Optional for at most one aggregate; `findAll` reads all aggregates in the repository; `findAllById` reads aggregates whose IDs are in the input set and skips non-existent IDs.** Both multi-result methods do not guarantee ordering. For large datasets, use conditional queries, pagination, or appropriate read models instead of loading full aggregates.

### References

- [Spring Data Commons — Repository Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): repository abstraction and CRUD contracts.
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html): contracts for `findById`, `findAll`, and `findAllById`.
- [Spring Data Commons — ListCrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/ListCrudRepository.html): CRUD variant returning List.
- [Spring Data JDBC — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories and aggregate persistence in Spring Data JDBC.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods and custom queries.
