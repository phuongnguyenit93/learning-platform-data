# Optional, Empty Collections, and Missing-Result Conventions

In **Spring Data Relational JDBC**, a repository query may find one record, multiple records, or no records at all. A method's return type must express those possibilities clearly so business code can handle them cleanly, avoid returning `null` arbitrarily, and avoid confusing “no data found” with “the query failed.”

Three conventions to master:

- **`Optional<T>`** expresses a single result that may or may not exist.
- **Empty collection** expresses a multi-result query that currently has no matching elements.
- **Exception** expresses a query that could not complete or violated result expectations, such as a method expecting at most one record when multiple records actually exist.

These conventions appear across CRUD repositories, derived queries, custom SQL queries, and the service layer. Understanding them properly gives repository APIs clear contracts and helps applications handle missing-data cases according to business rules.

## 1. Three distinct result states

Suppose an application has a `customer` table and needs to look up a customer by email. A repository call can encounter these cases:

| Outcome | Meaning | Appropriate Representation |
| --- | --- | --- |
| Exactly one customer found | Query found a matching record | `Optional<Customer>` containing the Customer |
| No customer found | No row satisfies the condition | `Optional.empty()` |
| Database unreachable | Could not execute the query | Data access layer exception |
| Multiple customers in a single-result query | Result violates the “at most one” assumption | Result-size exception |

The critical point is that **not finding data is not a technical error**. For instance, looking up a customer by email may find nothing because the email is not yet registered. That is a normal outcome whose handling is decided by business logic.

Conversely, if the database loses its connection, the repository cannot determine whether the customer exists. Never turn a connection failure into `Optional.empty()`, because the application could mistakenly conclude the email is unregistered.

## 2. `Optional<T>` in Java

`java.util.Optional<T>` is a container that may hold a value of type `T` or hold no value at all.

~~~java
Optional<String> present = Optional.of("customer@example.com");
Optional<String> absent = Optional.empty();
~~~

You can visualize it as:

~~~text
Optional<Customer>
       |
       +--- has value ---------> Customer object
       |
       +--- no value ----------> Optional.empty()
~~~

`Optional` lets callers see immediately from the method signature that the result may be absent. Instead of having to remember an implicit convention like “returns null if not found,” the caller is guided to handle absence through Optional's API.

### 2.1. Creating Optional

| Method | Meaning |
| --- | --- |
| `Optional.of(value)` | Creates an Optional with a value; throws `NullPointerException` if value is null |
| `Optional.ofNullable(value)` | Creates an empty Optional if value is null, otherwise wraps value |
| `Optional.empty()` | Creates an empty Optional |

Example:

~~~java
Customer customer = findCustomerFromLegacyCode();

Optional<Customer> result = Optional.ofNullable(customer);
~~~

In new application code, avoid producing `null` only to wrap it later when you control the API from the start. Return `Optional.empty()` directly when a result does not exist.

### 2.2. Reading values safely

Commonly used methods:

~~~java
Optional<Customer> customer = repository.findById(customerId);

String label = customer
        .map(Customer::getName)
        .orElse("Unknown customer");
~~~

| Method | Behavior |
| --- | --- |
| `isPresent()` | Checks whether a value is present |
| `isEmpty()` | Checks whether no value is present (Java 11+) |
| `ifPresent(action)` | Runs action if a value is present |
| `ifPresentOrElse(action, emptyAction)` | Chooses an action for each of the two cases (Java 9+) |
| `map(mapper)` | Transforms the value if present; mapper result is wrapped in Optional |
| `flatMap(mapper)` | Transforms with a function already returning Optional, avoiding nested Optionals |
| `filter(predicate)` | Keeps the value if it matches the predicate |
| `orElse(defaultValue)` | Returns the contained value or a default value |
| `orElseGet(supplier)` | Returns the contained value or calls supplier to produce a default |
| `orElseThrow()` | Returns the value or throws `NoSuchElementException` |
| `orElseThrow(supplier)` | Returns the value or throws the exception created by supplier |
| `stream()` | Converts to a stream of 0 or 1 element (Java 9+) |

### 2.3. Distinguishing `orElse` and `orElseGet`

`orElse` takes an already evaluated value:

~~~java
Customer customer = repository.findById(id)
        .orElse(createGuestCustomer());
~~~

The expression `createGuestCustomer()` is evaluated before `orElse` is called, even when the Optional already contains a `Customer`.

`orElseGet` takes a supplier:

~~~java
Customer customer = repository.findById(id)
        .orElseGet(this::createGuestCustomer);
~~~

`createGuestCustomer` is only invoked when the Optional is empty. When creating the default is expensive, has side effects, or performs another query, `orElseGet` is usually the better choice.

### 2.4. Using `orElseThrow` when missing data is a business error

~~~java
Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId));
~~~

Here, the repository expresses possible absence; the service decides that the current use case strictly requires the customer. Throwing the exception is a business-layer decision, not because the repository treats every empty result as an error by default.

Avoid calling `get()` without checking:

~~~java
// Can throw NoSuchElementException if no value is present.
Customer customer = repository.findById(id).get();
~~~

If business rules require the data to exist, `orElseThrow` lets you specify the exact exception type and message. If absence is normal, use `map`, `ifPresent`, or explicit branching.

## 3. `CrudRepository.findById` returns Optional

Spring Data JDBC provides repositories based on `CrudRepository`:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Method:

~~~java
Optional<Customer> findById(Long id);
~~~

Contract:

- Row exists with matching ID: returns Optional containing the Customer.
- No row exists: returns `Optional.empty()`.
- Query fails: throws the appropriate data access exception.
- Passing null ID: invalid argument, not a way to ask for “a record with no ID.”

Example:

~~~java
Optional<Customer> result = customerRepository.findById(42L);

if (result.isPresent()) {
    Customer customer = result.orElseThrow();
    System.out.println(customer.getName());
} else {
    System.out.println("Customer not found");
}
~~~

It can be written more concisely:

~~~java
customerRepository.findById(42L)
        .ifPresent(customer -> sendWelcomeReminder(customer));
~~~

If a return value is required:

~~~java
Customer customer = customerRepository.findById(42L)
        .orElseThrow(() -> new CustomerNotFoundException(42L));
~~~

### 3.1. Not found vs null ID

`findById(null)` does not mean “find a row without a key.” Primary keys are non-null and the repository contract requires a valid ID. Passing null is an argument error and can result in `IllegalArgumentException`.

Similarly, `existsById(null)` is not a way to check whether an entity is unsaved. To distinguish new entities, use ID/version rules or domain factories.

### 3.2. `existsById` when you only need a yes/no check

When only a boolean is needed:

~~~java
boolean exists = customerRepository.existsById(customerId);
~~~

`existsById` fits when the caller does not need the `Customer` contents. If the `Customer` still must be loaded afterward, a single `findById` is usually sufficient and avoids two round-trips:

~~~java
// May issue two unnecessary queries:
if (repository.existsById(id)) {
    Customer customer = repository.findById(id).orElseThrow();
}
~~~

Between those two statements, database state can also change. When you need the object, call `findById` directly and handle the Optional.

## 4. Multi-record results: use collections, not Optional

A query may find zero, one, or multiple records. If business logic allows multiple results, the return type should be a collection:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
~~~

Contract of a collection query:

- Matches exist: collection contains the matching elements.
- No matches: empty collection.
- Never normally returns `null` instead of an empty collection.

Example:

~~~java
List<Customer> activeCustomers =
        customerRepository.findByStatus("ACTIVE");

if (activeCustomers.isEmpty()) {
    System.out.println("No active customers yet");
}
~~~

No need for:

~~~java
// Avoid designing collection methods to return null when no data exists.
List<Customer> customers = findCustomers();
if (customers == null) {
    // ...
}
~~~

An empty collection is a normal result that can be iterated, streamed, serialized, or chained with other operations without null-check branches.

### 4.1. When to use List, Set, or Iterable?

| Return Type | When Appropriate |
| --- | --- |
| `List<T>` | Caller needs a collection with query-defined order and List operations |
| `Set<T>` | Caller needs unique-set semantics and intentional deduplication |
| `Collection<T>` | Caller only needs a general group of elements |
| `Iterable<T>` | Spring Data's basic CRUD contract, e.g. `findAll()` |
| `Page<T>` / `Slice<T>` | Paginated queries when the repository/query supports that return type |

Do not convert results to `Set` merely to “deduplicate” if doing so hides data bugs or loses required ordering. Distinctness and sorting rules should be clearly defined in the query or business layer.

## 5. CRUD methods and empty-collection conventions

Basic CRUD methods have different return types:

| Method | Return Type | When No Records Exist |
| --- | --- | --- |
| `findById(id)` | `Optional<T>` | `Optional.empty()` |
| `findAll()` | `Iterable<T>` | Empty Iterable |
| `findAllById(ids)` | `Iterable<T>` | Empty Iterable if none found |
| `existsById(id)` | `boolean` | `false` |
| `count()` | `long` | `0` |
| `save(entity)` | `T` | Not a lookup query; returns saved entity per persistence mechanics |
| `deleteById(id)` | `void` | If ID is not found, deletion does nothing |

These conventions let callers know exactly how absence is represented without guessing around null.

### 5.1. `findAll()` does not return null

~~~java
Iterable<Customer> customers = customerRepository.findAll();

for (Customer customer : customers) {
    process(customer);
}
~~~

If the table has no rows, the loop runs zero times. There is no need to check `customers == null`.

If the caller needs a `List`:

~~~java
List<Customer> customers = StreamSupport
        .stream(customerRepository.findAll().spliterator(), false)
        .toList();
~~~

In Java 16+, `Stream.toList()` returns an unmodifiable list. If a mutable list is needed, collect via `Collectors.toCollection(ArrayList::new)`. Only convert when the caller genuinely needs a `List`; avoid unnecessary copies.

### 5.2. `findAllById` may return fewer items than input IDs

Suppose:

~~~java
List<Long> ids = List.of(10L, 20L, 30L, 40L);
Iterable<Customer> found = customerRepository.findAllById(ids);
~~~

If IDs 20 and 40 do not exist, the result contains only the customers found. Per the `CrudRepository` contract:

- Returned Iterable is non-null.
- Result may contain fewer elements than the input IDs.
- Returned element order is not guaranteed to match input ID order.

Do not assume:

~~~java
// Wrong assumption: second result always corresponds to ids.get(1).
Customer second = toList(found).get(1);
~~~

If mapping by ID is needed, build a `Map` from the result:

~~~java
Map<Long, Customer> byId = StreamSupport
        .stream(found.spliterator(), false)
        .collect(Collectors.toMap(Customer::getId, Function.identity()));
~~~

Then look up by ID:

~~~java
Customer customer10 = byId.get(10L);
Customer customer20 = byId.get(20L); // null if ID 20 does not exist
~~~

If missing IDs must be distinguished explicitly, use `containsKey`:

~~~java
if (!byId.containsKey(20L)) {
    // ID 20 is absent from the query result.
}
~~~

Or construct a `Map` with `Optional` values when internal APIs need to express absence explicitly. Avoid `null` where lookup methods returning `Optional` can be used.

### 5.3. If business rules require all IDs to exist

`findAllById` does not throw automatically when some IDs do not exist. The service must compare requested IDs against found IDs:

~~~java
Set<Long> requestedIds = new HashSet<>(ids);
Set<Long> foundIds = byId.keySet();

Set<Long> missingIds = new HashSet<>(requestedIds);
missingIds.removeAll(foundIds);

if (!missingIds.isEmpty()) {
    throw new CustomerNotFoundException(missingIds);
}
~~~

This example assumes input IDs have been checked as non-null and deduplication fits the business rule. If order or multiplicity of input IDs matters, keep the original list as well instead of using only a `Set`.

## 6. Should derived queries return Optional or a collection?

Spring Data JDBC lets you declare query methods based on property names:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);

    List<Customer> findByCity(String city);
}
~~~

Choose the return type based on business cardinality:

- `findByEmail`: if email is unique, at most one result, use `Optional<Customer>`.
- `findByStatus`: many customers can share a status, use `List`.
- `findByCity`: many customers can live in the same city, use `List` or an appropriate collection type.

### 6.1. Returning Optional does not mean the database enforces uniqueness

Suppose email is expected to be unique:

~~~java
Optional<Customer> findByEmail(String email);
~~~

This signature states the query returns at most one `Customer`. It does not automatically create a unique constraint on the `email` column.

If the database contains two rows with the same email, the actual query produces multiple results and the single-result method may throw `IncorrectResultSizeDataAccessException` (or the corresponding Spring ecosystem exception). Do not pick `Optional` merely because “there is usually only one result.”

Protect uniqueness assumptions in the schema:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_email UNIQUE (email);
~~~

Before adding a constraint to an existing table, clean up duplicate data and establish email normalization rules (casing, whitespace, collation) per business needs.

### 6.2. If the query can return multiple records

If the same email can be used across multiple tenants:

~~~java
List<Customer> findByEmail(String email);
~~~

Or query scoped to both:

~~~java
Optional<Customer> findByTenantIdAndEmail(
        Long tenantId,
        String email
);
~~~

In the second case, the schema should have a unique constraint on `(tenant_id, email)` if that is the business rule.

## 7. Optional in the service layer

The repository returns `Optional` to represent data state. The service decides whether missing data is acceptable.

### 7.1. Not found is normal

For example, checking whether a customer is already registered:

~~~java
public boolean isRegistered(String email) {
    return customerRepository.findByEmail(email).isPresent();
}
~~~

If only a boolean is needed, declare an appropriate query or `exists` method so you do not materialize the entire entity.

### 7.2. Not found is a use-case error

~~~java
public CustomerDetail getCustomerDetail(Long id) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return CustomerDetail.from(customer);
}
~~~

A domain exception can be mapped by a controller or exception handler to HTTP 404. The repository does not need to know HTTP and should not throw exceptions tied to the web protocol.

### 7.3. Create when absent

~~~java
public Customer registerIfAbsent(String email, String name) {
    return customerRepository.findByEmail(email)
            .orElseGet(() -> customerRepository.save(
                    Customer.create(email, name)
            ));
}
~~~

This is a short example of check-then-create. Under concurrency, two requests can still both observe an empty Optional and both attempt to insert. A unique constraint must guard the email; the service needs to catch and translate constraint violations or use a database-appropriate upsert strategy.

### 7.4. Transforming values with map and flatMap

When only one property is needed:

~~~java
Optional<String> email = customerRepository.findById(id)
        .map(Customer::getEmail);
~~~

When the next function also returns Optional:

~~~java
Optional<Address> address = customerRepository.findById(id)
        .flatMap(Customer::getPrimaryAddress);
~~~

Suppose `getPrimaryAddress()` returns `Optional<Address>`. Using `flatMap` keeps the result as `Optional<Address>` instead of `Optional<Optional<Address>>`.

### 7.5. Additional condition filtering

~~~java
Optional<Customer> activeCustomer = customerRepository.findById(id)
        .filter(Customer::isActive);
~~~

An empty result here can have two causes: the ID does not exist, or the customer exists but is inactive. If business logic needs to distinguish those two cases, do not collapse them into one Optional; handle them step by step:

~~~java
Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new CustomerNotFoundException(id));

if (!customer.isActive()) {
    throw new CustomerInactiveException(id);
}
~~~

## 8. Optional does not replace every return type

`Optional` is helpful for potentially absent single results, but should not be used as a universal container for every situation.

### 8.1. Do not wrap collections in Optional

Avoid:

~~~java
Optional<List<Customer>> findByStatus(String status);
~~~

When there are no customers, should it return `Optional.empty()` or `Optional.of(List.of())`? Those two states normally carry no distinct meaning. An empty collection already expresses “no elements,” so use:

~~~java
List<Customer> findByStatus(String status);
~~~

### 8.2. Do not use Optional to hide technical failures

Avoid catching all exceptions and returning empty:

~~~java
public Optional<Customer> findCustomer(Long id) {
    try {
        return repository.findById(id);
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

This code turns database outages, mapping errors, SQL syntax issues, and unrelated failures into “not found.” Callers cannot distinguish them and may take wrong actions.

Only convert an error into another business outcome when there is an explicit rule and you catch only the specific exception type intended.

### 8.3. Do not use Optional as a persistent entity field

Avoid declaring:

~~~java
class Customer {
    private Optional<String> middleName;
}
~~~

Optional was designed primarily for return types, letting callers see possible absence. For Spring Data JDBC entities, use the actual value type nullable according to mapping, or model it more explicitly with value objects / nullable semantics. Do not ask the framework to persist an Optional wrapper as a plain column when mapping does not support it as intended.

If a property can be absent, express it on service/repository APIs using Optional when returning a single result; inside the entity, use property types aligned with mapping and database nullability rules.

### 8.4. Do not use Optional as a default parameter type

Avoid APIs like:

~~~java
void updateCustomer(Long id, Optional<String> newName);
~~~

Callers can still pass null instead of Optional, adding another layer of absence. Typically, use overloads, command objects, or clear conventions for patch/update. Optional fits best when a **method returns** a potentially absent value.

## 9. Spring Data nullability conventions

A clear repository contract should distinguish:

- Non-null return values.
- Potentially absent single values expressed with Optional.
- Non-null returned collections; zero items means an empty collection.
- Required parameters must be non-null.

Spring Data supports nullability annotations to document and check null contracts, such as `@NonNullApi` at the package level and `@Nullable` on specific elements where null is genuinely allowed.

Conceptual example:

~~~java
@NonNullApi
package com.example.customer;

import org.springframework.lang.NonNullApi;
~~~

In a package with `@NonNullApi`, parameters and return values are treated as non-null by default unless annotated with `@Nullable`. For repository methods returning `Optional<T>`, the Optional itself is non-null; absence lives inside the container.

When designing APIs, avoid mixing three representations for the same situation:

~~~text
null
Optional.empty()
empty collection
~~~

Each has distinct semantics:

- `null`: lack of a clear contract or an explicitly declared nullable value.
- `Optional.empty()`: a single result does not exist.
- Empty collection: zero elements in a result set.

### 9.1. Database NULL differs from no row

A row can exist while one of its columns holds SQL `NULL`. That differs from a query returning zero rows.

Example:

~~~sql
SELECT id, middle_name
FROM customer
WHERE id = 42;
~~~

Two cases:

1. No customer with ID 42: no result row, repository `findById` returns an empty Optional.
2. Customer ID 42 exists with `middle_name IS NULL`: row exists; the entity is constructed with `middleName` holding no value per mapping.

Do not use the entity's Optional to represent a null value inside a column. Those are two different levels.

## 10. Custom SQL queries and empty results

With `@Query` or `JdbcClient`, return conventions still must match row cardinality.

Example customer lookup query:

~~~java
@Query("SELECT * FROM customer WHERE email = :email")
Optional<Customer> findByEmail(String email);
~~~

If no row matches, the result is an empty Optional. If the query returns multiple rows while the method asks for a single result, Spring Data may throw a result-size error.

For multi-row queries:

~~~java
@Query("SELECT * FROM customer WHERE status = :status")
List<Customer> findAllByStatus(String status);
~~~

If no rows match, an empty `List` is returned.

### 10.1. `COUNT` returns one row with value 0

A common point of confusion:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status = 'UNKNOWN';
~~~

A standard `COUNT(*)` aggregate query still returns **one row** with value `0` when no records match. It does not return zero rows.

Therefore, when mapping a count query to a numeric type, the result is `0`, not an empty Optional merely because the table had no matching rows.

### 10.2. `SUM` and `AVG` can return SQL NULL

Unlike COUNT, some aggregate functions such as `SUM` or `AVG` can return SQL NULL when there are no matching inputs (unless the query uses `COALESCE`). Example:

~~~sql
SELECT SUM(amount)
FROM payment
WHERE order_id = ?;
~~~

If there are no payments, the result may be one row containing SQL NULL. If business logic wants the sum to be 0:

~~~sql
SELECT COALESCE(SUM(amount), 0)
FROM payment
WHERE order_id = ?;
~~~

Distinguish between:

- No result rows.
- One row with a SQL NULL column.
- One row with numeric value 0.

These three situations carry different meanings and require matching mapping and return types.

## 11. Single-result queries when data might contain duplicates

Suppose:

~~~java
Optional<Customer> findByEmail(String email);
~~~

This method implies the query returns at most one result. If duplicate data exists, the framework should not arbitrarily pick the first row because that masks a uniqueness violation.

Enforce the rule in the database:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_email UNIQUE (email);
~~~

If uniqueness is scoped per tenant:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_tenant_email
    UNIQUE (tenant_id, email);
~~~

Once the unique constraint is protected, `Optional` accurately represents the two states: either one customer exists or no customer exists.

If business rules genuinely allow multiple rows, change the return type to a collection or explicitly design a bounded/ordered query. Never pretend data is unique just by choosing `Optional`.

## 12. Combining Optional with HTTP/APIs

Repositories should not know HTTP status codes. Services can turn Optional into domain exceptions, and controller advice maps exceptions to HTTP responses.

~~~java
@GetMapping("/customers/{id}")
public CustomerResponse getCustomer(@PathVariable Long id) {
    return customerService.getById(id);
}
~~~

Service:

~~~java
public CustomerResponse getById(Long id) {
    Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return CustomerResponse.from(customer);
}
~~~

Exception handler:

~~~java
@ExceptionHandler(CustomerNotFoundException.class)
ResponseEntity<ProblemDetail> handleNotFound(
        CustomerNotFoundException exception
) {
    ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    problem.setDetail(exception.getMessage());
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
}
~~~

These classes are simplified to focus on data flow. In a real application, include imports, constructor injection, and exception handlers according to project structure.

Flow:

~~~text
HTTP request
    |
    v
Controller
    |
    v
Service
    |
    v
Repository.findById()
    |
    +--- Optional has value ---> build response
    |
    +--- Optional empty -------> throw domain exception
                                      |
                                      v
                              Exception handler
                                      |
                                      v
                                  HTTP 404
~~~

When a list-search endpoint finds no matches, it typically returns HTTP 200 with an empty array rather than 404, because the collection resource itself still exists even though it currently has no matching items. Exact API decisions depend on product contracts.

## 13. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning null when a single entity is not found | Callers have to guess nullability | Return `Optional<T>` |
| Returning Optional for multi-row queries | Cannot fully express the result set | Return List/Collection/Iterable |
| Returning null for an empty collection | Forces unnecessary null branches | Return an empty collection |
| Calling `get()` without checking | Can throw confusing NoSuchElementException | Use `orElseThrow` or handle absence |
| Using `orElse(expensiveCall())` | Computes default even when a value is present | Use `orElseGet` |
| Catching all exceptions and returning Optional.empty | Masks database, mapping, and coding errors | Handle only expected error types |
| Choosing Optional assuming data is unique | Duplicate rows cause runtime failures | Unique constraint + single-result method |
| Using `Optional<List<T>>` | Two redundant layers of “empty” | Return an empty List |
| Using Optional as an entity field | Complicates mapping and null modeling | Use proper property types; Optional is primarily for returns |
| Assuming findAllById preserves input order | Mismatches IDs and entities | Build a Map by ID or sort explicitly |
| Calling existsById then findById | Extra round-trip and race window | Call findById directly if you need the entity |
| Confusing SQL NULL with no row | Misinterprets data | Distinguish nullable columns from row absence |

## 14. Practice scenarios

### Scenario A — Looking up an account by ID

A use case displays customer details by ID. If the ID does not exist, return 404.

**Approach:** the repository returns `Optional<Customer>`; the service uses `orElseThrow` to throw `CustomerNotFoundException`; the web layer maps the exception to 404.

### Scenario B — Finding orders by customer

A customer may have no orders yet or many orders.

**Approach:** the method returns `List<PurchaseOrder>`. When there are no orders yet, return an empty list. Do not use `Optional<List<PurchaseOrder>>`.

### Scenario C — Loading multiple selected IDs

A request contains 10 customer IDs; the database only has 8 rows.

**Approach:** `findAllById` returns the found rows. If the business rule allows missing items, process the result set. If all 10 are mandatory, compare requested IDs against found IDs and return a clear error.

### Scenario D — Looking up a unique email

Method `findByEmail` returns Optional, yet the database might hold duplicate emails from legacy data.

**Approach:** clean up legacy data, define normalization rules, and add a unique constraint. If duplicates are valid per tenant, include tenant in both the query predicate and constraint.

### Scenario E — Not found or database down?

An endpoint reports “no customer found” while the database connection is down.

**Problem:** code caught exceptions too broadly and converted them into an empty Optional.

**Approach:** let infrastructure exceptions be handled by system error policy; reserve empty Optional strictly for a successful query with no matching rows.

## 15. Workflow for choosing repository return types

When declaring a query method, determine:

1. **How many rows can the query return?** Zero rows, at most one row, or multiple rows?
2. **Is zero rows a normal case?** If a single result can be absent, use Optional.
3. **What about zero items in a multi-result query?** Use an empty collection.
4. **Where is uniqueness enforced?** If the method assumes one row, the database needs a matching unique constraint.
5. **How are technical errors handled?** Never turn data-access errors into absence.
6. **What behavior does the service need when absent?** Return an absent result, supply a default, skip, or throw a domain exception.
7. **Must SQL NULL be distinguished from no row?** Choose projections and data types accordingly.
8. **Can multi-ID queries have missing items or reordered outputs?** Do not rely on input order if the contract does not guarantee it.

## Key takeaways

In Spring Data JDBC, `Optional<T>` is the explicit contract for a single result that may not exist; an empty collection is the natural contract for a multi-result query finding no elements; exceptions are for query failures or cardinality-assumption violations. `findById` returns Optional, `findAll` and `findAllById` return potentially empty collections, while `existsById` and `count` return boolean/counts.

Let the repository express data state, the service decide business meaning, and the database enforce structural assumptions such as uniqueness. Keeping those three responsibilities clear eliminates guessing about nulls, avoids masking infrastructure failures, and handles both present and absent data cleanly.
