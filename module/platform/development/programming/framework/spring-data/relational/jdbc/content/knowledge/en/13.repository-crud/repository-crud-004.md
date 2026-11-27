# save and saveAll: Return Values and Operation Scope in Spring Data JDBC

## 1. Role of save and saveAll

In Spring Data JDBC, repositories provide CRUD operations to persist aggregates to the database. Two commonly used methods are:

- **§save(entity)§:** saves a single entity/aggregate root and returns the saved entity.
- **§saveAll(entities)§:** saves multiple entities/aggregate roots and returns a collection of the saved entities.

Example:

~~~java
Book saved = bookRepository.save(book);

Iterable<Book> savedBooks = bookRepository.saveAll(books);
~~~

The key point is that **the return value may differ from the input object**. During saving, Spring Data JDBC may obtain a database-generated ID, update a version, run lifecycle callbacks, or create a new instance if the entity is immutable. Therefore, use the returned result for subsequent processing.

Beyond the return value, you need to understand **transaction scope**: a single repository call may execute in a transaction by default configuration; multiple repository calls in one business operation require a service-level transaction boundary if they must succeed or roll back together.

## 2. save(entity): saving one aggregate and receiving the result

In §CrudRepository§, the method signature is:

~~~java
<S extends T> S save(S entity);
~~~

The method takes an entity and returns an entity of the same concrete type §S§. In Spring Data JDBC, a repository typically represents an aggregate root; when saving the root, components belonging to the aggregate are also processed according to the aggregate mapping.

Example:

~~~java
Book input = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(input);

System.out.println(saved.getId());
~~~

If the database generates the ID, §saved§ contains the new ID. Do not assume §input.getId()§ is always mutated or always equals the returned ID, especially with immutable entities.

### 2.1. Why must the returned object be used?

There are three common reasons:

1. **Generated ID:** the database generates the primary key after INSERT; the framework populates that value into the saved result.
2. **Optimistic locking:** if the entity uses §@Version§, the version may be incremented on write.
3. **Immutable object:** a record or immutable class cannot modify its fields; the framework returns a new instance carrying the updated ID/version.

Example with a record:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
        @Id Long id,
        String title,
        BigDecimal price
) {}
~~~

Saving a new instance:

~~~java
Book input = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(input);

System.out.println("Input ID: " + input.id());
System.out.println("Saved ID: " + saved.id());
~~~

With a record, §input§ cannot be mutated in place. §saved§ is the result that must be used for subsequent operations:

~~~java
Long bookId = saved.id();
Book loaded = bookRepository.findById(bookId).orElseThrow();
~~~

**Practical rule:** always assign the result of §save§ to a variable and pass that result through subsequent steps. Do not rely on the framework mutating the input object.

## 3. How does save decide between INSERT and UPDATE?

§save§ does not simply mean “always INSERT” or “always UPDATE”. Spring Data determines whether the entity is new and chooses the corresponding persistence operation.

With the common default state-detection strategy:

- If the entity has a §@Version§ property, version state is checked first; a null version (for reference types) usually indicates a new entity.
- If there is no version property, the identifier is used to detect a new entity; a null identifier usually indicates a new entity.
- If the entity implements §Persistable§, the §isNew()§ method can supply custom logic.

Overview table:

| State | Typical Handling |
|---|---|
| New entity, null ID | INSERT |
| Existing entity, non-null ID | UPDATE |
| Entity with null version | Usually detected as new |
| Entity with pre-assigned ID before saving | May be detected as existing unless another strategy is configured |

Details of new-entity detection depend on the ID/version type and the mechanism the entity uses. When using application-assigned IDs, explicitly design how Spring Data knows whether an object is new or existing; do not expect §save§ to always try UPDATE and automatically fall back to INSERT if no row is found.

### 3.1. INSERT example

New entity:

~~~java
Book book = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(book);
~~~

Conceptual SQL:

~~~sql
INSERT INTO books (title, price)
VALUES (?, ?);
~~~

The database generates the ID according to the schema, and Spring Data JDBC retrieves that value according to the dialect/driver.

### 3.2. UPDATE example

Read an existing entity, modify data, and save:

~~~java
Book existing = bookRepository.findById(bookId)
        .orElseThrow();

Book changed = new Book(
        existing.id(),
        "Spring Data JDBC - Updated",
        existing.price()
);

Book updated = bookRepository.save(changed);
~~~

Conceptual SQL:

~~~sql
UPDATE books
SET title = ?, price = ?
WHERE id = ?;
~~~

Spring Data JDBC does not track every in-memory change on objects like JPA's dirty checking. Modifying a property does not automatically send an UPDATE; the appropriate save operation must be called.

## 4. saveAll(Iterable<S>): saving multiple entities

In §CrudRepository§, the method signature is:

~~~java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
~~~

The method takes an §Iterable§ and returns an §Iterable§ containing the saved entities. Example:

~~~java
List<Book> input = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000")),
        new Book(null, "Book C", new BigDecimal("150000"))
);

Iterable<Book> savedBooks = bookRepository.saveAll(input);
~~~

The returned result should not be ignored if the application needs the ID, version, or new instance of each entity:

~~~java
for (Book saved : savedBooks) {
    System.out.println(saved.id() + " - " + saved.title());
}
~~~

### 4.1. saveAll does not mean a single INSERT statement

The word “All” in the method name does not guarantee the database receives **a single SQL statement** to save all entities. In Spring Data JDBC, each aggregate may require one or more statements to save the root and its child components. Execution also depends on the implementation, dialect, and driver.

Distinguish between:

| Concept | Meaning |
|---|---|
| One §saveAll§ call | A single repository API invocation with multiple entities |
| One transaction | A commit/rollback boundary for operations within that scope |
| JDBC batch | A mechanism grouping multiple statements of the same form to send/execute in batches |
| One SQL statement | A single statement sent to the database |

§saveAll§ is an API for saving multiple entities, **not a guarantee of JDBC batching or a single statement**. If high-volume write optimization is needed, measure performance and choose an appropriate strategy, such as JDBC batching via §JdbcTemplate.batchUpdate§ when the data has a suitable SQL structure. That approach does not automatically perform Spring Data JDBC's aggregate mapping or lifecycle callbacks.

### 4.2. saveAll results and the input collection

§saveAll§ accepts §Iterable§ so callers are not forced to use §List§ specifically. With §CrudRepository§, the return type is §Iterable<S>§. Some versions/setups can use §ListCrudRepository§, where the corresponding methods return §List<S>§.

When writing code, rely on **the repository interface your application actually extends** and the return type shown by the IDE/compiler, rather than casting blindly:

~~~java
Iterable<Book> saved = bookRepository.saveAll(input);
~~~

If the API returns §Iterable§, it can be converted to a list when genuinely needed:

~~~java
List<Book> savedList = StreamSupport
        .stream(saved.spliterator(), false)
        .toList();
~~~

Converting to a list consumes the iterable to create a new collection. For large datasets, consider memory usage and avoid materializing the entire result if you only need to process elements one by one.

Do not assume the input collection will be mutated or contain new IDs after calling §saveAll§. Read the instances from **the returned result**.

## 5. Return values for entities with ID and version

### 5.1. Database-generated ID

Suppose the table is:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Entity:

~~~java
@Table("books")
public record Book(
        @Id Long id,
        String title,
        BigDecimal price
) {}
~~~

Saving multiple new entities:

~~~java
List<Book> inputs = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000"))
);

Iterable<Book> saved = bookRepository.saveAll(inputs);

for (Book book : saved) {
    // Use the ID populated in the saveAll result.
    log.info("Saved book id={}", book.id());
}
~~~

Each new entity must be persisted and receive the appropriate ID value. Ignoring the result may leave the application without IDs to link subsequent data or return to the caller.

### 5.2. Optimistic locking with @Version

A versioned entity:

~~~java
@Table("books")
public record Book(
        @Id Long id,
        @Version Long version,
        String title,
        BigDecimal price
) {}
~~~

Version enables Spring Data JDBC to detect updates based on the version the caller read. Upon successful save, the version may be incremented. If another transaction has updated the record in the meantime, saving with an outdated version may fail due to optimistic locking.

Example:

~~~java
Book loaded = bookRepository.findById(bookId).orElseThrow();

Book changed = new Book(
        loaded.id(),
        loaded.version(),
        "New title",
        loaded.price()
);

Book saved = bookRepository.save(changed);

// Use saved.version() for the new state.
~~~

With immutable objects, the returned result is where you obtain the new version. Continuing to use the old object with the old version may cause subsequent updates to be rejected as stale data.

### 5.3. When saveAll contains both new and existing entities

An iterable may contain entities in mixed states. Spring Data determines each entity's state from its metadata; new elements may follow INSERT while existing elements may follow UPDATE.

Do not assume every element in §saveAll§ is an INSERT. Nor assume having an ID guarantees a matching row exists in the database; the new-entity detection strategy and actual database state must stay consistent.

## 6. saveAll and transaction scope

This is critical when a business operation must write multiple entities as a single unit.

Spring Data repository CRUD methods are typically configured with transactions by default. Calling a repository method through its proxy applies the repository's transaction configuration if a matching transaction manager is configured.

Example:

~~~java
bookRepository.saveAll(books);
~~~

With default CRUD repository configuration, a §saveAll§ call generally runs inside the repository method's transaction. If a write operation within that scope throws a runtime exception and it propagates out, the transaction can roll back according to the active transaction policy.

However, when a business operation consists of multiple separate repository calls, place the transaction on the service to clearly define the entire business scope:

~~~java
@Service
public class CatalogService {

    private final BookRepository books;
    private final AuthorRepository authors;

    public CatalogService(
            BookRepository books,
            AuthorRepository authors
    ) {
        this.books = books;
        this.authors = authors;
    }

    @Transactional
    public void createAuthorAndBooks(
            Author author,
            List<Book> newBooks
    ) {
        Author savedAuthor = authors.save(author);

        List<Book> booksWithAuthor = newBooks.stream()
                .map(book -> book.withAuthorId(savedAuthor.id()))
                .toList();

        books.saveAll(booksWithAuthor);
    }
}
~~~

In this example, §@Transactional§ on the service expresses that creating the author and saving the list of books form one business operation. If the repositories share the appropriate transaction manager/DataSource, the calls participate in the same transaction.

### 6.1. Two separate save calls are not automatically one shared transaction

Example:

~~~java
bookRepository.save(bookA);
bookRepository.save(bookB);
~~~

Without an enclosing transaction at the service layer, each repository call may run in its own transaction under default configuration. If the first succeeds and the second fails, the first may already have committed.

If two records must succeed or fail together:

~~~java
@Transactional
public void savePair(Book bookA, Book bookB) {
    bookRepository.save(bookA);
    bookRepository.save(bookB);
}
~~~

Or use §saveAll§ if they are aggregates of the same repository and the business operation fits:

~~~java
@Transactional
public Iterable<Book> saveBooks(List<Book> books) {
    return bookRepository.saveAll(books);
}
~~~

Service transactions also allow combining different operations within the same use case, rather than just a single repository method.

### 6.2. Is saveAll always atomic?

Do not answer solely from the method name. Atomicity depends on:

- Whether the repository method runs inside a transaction.
- Whether the transaction manager is properly configured and manages the same DataSource.
- Whether the database/table engine supports transactions.
- Whether the error triggers rollback under the active policy.
- Whether the application catches and swallows exceptions inside the transaction.

In a typical Spring Data JDBC setup on a transactional database, CRUD repository methods usually have a transaction boundary. Even so, if atomicity is a business requirement, explicitly declare §@Transactional§ on the service and test mid-operation failure cases.

By default, Spring transactions roll back on §RuntimeException§ and §Error§; checked exceptions generally do not trigger automatic rollback unless §rollbackFor§ is configured appropriately. If code catches an exception and continues, the transaction may still commit or be marked rollback-only depending on the error and transaction manager. Do not hide persistence errors.

### 6.3. Self-invocation and proxies

In the default proxy configuration, §@Transactional§ applies only when calls pass through the Spring proxy. A method in the same object calling another annotated method on itself normally bypasses the proxy:

~~~java
public void importBooks(List<Book> books) {
    this.saveAllInTransaction(books); // self-invocation
}

@Transactional
public void saveAllInTransaction(List<Book> books) {
    bookRepository.saveAll(books);
}
~~~

In this example, the annotation on §saveAllInTransaction§ may fail to start a transaction as expected when called via §this§. Place the transaction on a public method invoked from another bean or extract the use case into an appropriate service bean.

## 7. saveAll does not replace large batch processing

For a few entities or a moderately sized set of aggregates, §saveAll§ is a convenient API. However, when importing hundreds of thousands or millions of rows, evaluate:

- Actual number of SQL statements generated.
- Number of aggregates and number of children per aggregate.
- Memory consumed to hold inputs and results.
- Transaction duration and lock duration.
- Database/driver parameter limits.
- Retry capability and failed-record handling.
- Requirements for lifecycle callbacks and aggregate mapping.

### 7.1. Chunking

Example of processing in groups to bound memory and work per batch:

~~~java
@Transactional
public void importBooks(List<Book> input) {
    int chunkSize = 500;

    for (int start = 0; start < input.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, input.size());
        List<Book> chunk = input.subList(start, end);

        Iterable<Book> savedChunk = bookRepository.saveAll(chunk);

        for (Book saved : savedChunk) {
            // Process ID/version from this chunk's results.
        }
    }
}
~~~

In the example above, the entire method still runs inside **one transaction** because the annotation wraps the method. Chunking only divides processing groups in code; it does not automatically create separate transactions per chunk.

If you want per-chunk commits, you must design a different transaction boundary (such as a separate method with appropriate propagation or explicit orchestration). That changes semantics: earlier chunks may already be committed even if a later chunk fails.

### 7.2. JDBC batching when raw write performance is needed

If the data consists of flat rows and does not require Spring Data JDBC's aggregate mapping/lifecycle, consider:

~~~java
jdbcTemplate.batchUpdate(
        "INSERT INTO audit_events (event_type, message) VALUES (?, ?)",
        events,
        500,
        (ps, event) -> {
            ps.setString(1, event.type());
            ps.setString(2, event.message());
        }
);
~~~

§batchUpdate§ is a more explicit JDBC batch mechanism for plain SQL. However:

- It does not automatically invoke repository lifecycle callbacks.
- It does not perform aggregate mapping.
- It does not execute entity new-state detection rules.
- It does not automatically populate IDs/versions onto entities like a repository.
- You must manage transactions and error handling yourself.

Choose the tool based on requirements: use repositories for aggregate persistence; raw bulk SQL can use JDBC batching.

## 8. save and saveAll with aggregates containing children

In Spring Data JDBC, a repository saves the aggregate root and all components belonging to the aggregate. Example:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        LocalDate orderedOn,
        @MappedCollection(idColumn = "order_id", keyColumn = "line_number")
        List<OrderLine> lines
) {}
~~~

Calling:

~~~java
PurchaseOrder savedOrder = orderRepository.save(order);
~~~

or:

~~~java
Iterable<PurchaseOrder> savedOrders =
        orderRepository.saveAll(orders);
~~~

means saving the passed aggregate roots including child data according to the mapping. It does not write only a single row into the root table.

One aggregate may require multiple SQL statements:

1. INSERT/UPDATE on the root table.
2. Write child data in related tables.
3. Maintain foreign keys and collection keys per the mapping.
4. Perform child delete/replace operations needed when updating the aggregate.

Therefore, §saveAll§ with 100 aggregates can emit far more than 100 statements. Do not infer performance solely from the iterable's element count.

### 8.1. Return value for immutable aggregates

If the root is a record or immutable class, the §save§ result may contain the root ID and updated values. Keep the saved aggregate result if you need to use the root ID or lifecycle-generated data.

Example:

~~~java
PurchaseOrder saved = orderRepository.save(inputOrder);
Long orderId = saved.id();
~~~

Do not continue using §inputOrder§ to read the ID if it was created with a null ID.

### 8.2. Do not use saveAll to bypass aggregate boundaries

If multiple child objects belong to the same root, they should be modeled inside the aggregate according to domain design and saved through the root. If objects are genuinely independent aggregates with their own repository, §saveAll§ can save a collection of those roots.

An iterable of child objects does not automatically turn them into aggregate roots. Identify which aggregate type the repository manages and what entity type §saveAll§ accepts.

## 9. Example service returning saved results

A service can return the list of saved entities so the caller can use the new IDs:

~~~java
@Service
public class BookImportService {

    private final BookRepository books;

    public BookImportService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public List<Book> importBooks(List<Book> input) {
        Iterable<Book> saved = books.saveAll(input);

        List<Book> result = new ArrayList<>();
        saved.forEach(result::add);

        return result;
    }
}
~~~

Caller:

~~~java
List<Book> savedBooks = bookImportService.importBooks(input);

List<Long> ids = savedBooks.stream()
        .map(Book::id)
        .toList();
~~~

This example materializes the result as a §List§ because the caller needs to stream it to extract IDs. If the repository interface already returns §List§, you can return it directly. For very large datasets, consider streaming/chunked processing to avoid holding the entire result in memory.

## 10. Common errors with save and saveAll

| Symptom | Common Cause | Resolution |
|---|---|---|
| ID remains null after save | Reading ID from immutable input object or generated keys not configured/supported | Use the returned object; check identity, dialect, and driver |
| Entity with ID triggers UPDATE instead of INSERT | New-entity detection treats assigned ID as an existing entity | Design §isNew()§/§Persistable§ or version appropriately |
| saveAll is slow despite being one call | Each aggregate/child may require multiple SQLs; JDBC batching is not guaranteed | Measure SQL, chunk, or choose JDBC batch for plain SQL |
| Some entities are not saved | Constraint, conversion, mapping, or transaction error | Inspect the root exception and check schema/data |
| Saving two entities keeps only one | Two save calls have separate transactions or unexpected transaction boundary | Put §@Transactional§ on the service |
| Error on last element leaves earlier data committed | No shared transaction, exception caught, or non-transactional database | Check transaction manager, rollback policy, and database |
| Version reuses stale value | Caller ignores returned object or reuses a stale entity | Continue using the version from the new result |
| saveAll returns Iterable but code casts to List | Relying on return type from wrong repository interface | Use §Iterable§ or materialize explicitly |
| Input collection lacks IDs after saveAll | Expecting framework to mutate every input element | Iterate over the returned result for IDs/versions |
| Aggregate children rewritten unexpectedly | Misunderstanding aggregate lifecycle during root save | Review mapping and aggregate boundary design |

## 11. Practice exercises

### Exercise 1 — Using the save result

Create a new §Book§ with a null ID, call §save§, then print the ID of both the input object and the returned object. Try with both a mutable class and a Java record. Explain why code should use the returned object.

### Exercise 2 — saveAll and generated IDs

Create a list of three new §Book§ instances, call §saveAll§, iterate over the result, and collect their IDs. Verify the number of returned entities and the database state.

### Exercise 3 — Mixing INSERT and UPDATE

Create one new entity and one existing entity, pass both into §saveAll§. Observe newness status and SQL operations. Also test an entity with a pre-assigned ID that does not yet have a row in the database.

### Exercise 4 — Version

Add §@Version§ to an entity. Read an entity, update it through the repository, then attempt to save an older instance carrying the previous version. Observe the optimistic locking failure and use the version from the new result.

### Exercise 5 — Transactions with saveAll

Create a list where one element violates a unique constraint. Call §saveAll§ inside a service annotated with §@Transactional§, let the exception propagate, and verify whether earlier elements roll back. Repeat without a service transaction and compare with separate §save§ calls.

### Exercise 6 — Distinguishing batching from saveAll

Save many records via §saveAll§ with SQL logging enabled to observe statement counts. Write a §JdbcTemplate.batchUpdate§ example for a simple log table and compare mapping/lifecycle capabilities.

### Exercise 7 — Saving aggregates

Create multiple §PurchaseOrder§ instances, each with §OrderLine§ items. Call §saveAll§ on the root repository. Inspect both root and child tables, then update an aggregate and observe how child rows are synchronized.

## 12. Key takeaways

- §save(entity)§ returns the saved entity; §saveAll(iterable)§ returns the collection of saved entities. Always use the returned result when you need generated IDs, versions, or new immutable instances.
- §save§ chooses INSERT or UPDATE based on new-entity detection, not simply from the method name.
- §saveAll§ does not inherently mean a single SQL statement or JDBC batch; a single aggregate can require multiple statements.
- CRUD repository methods have default transaction semantics when invoked via the repository proxy with a proper transaction manager. Put §@Transactional§ on the service when multiple operations must succeed or roll back together.
- Two separate §save§ calls do not automatically form one shared business transaction without an enclosing transaction.
- With §@Version§, continue using the version from the returned object to avoid saving with stale state.
- When saving an aggregate, the repository manages the root and child components per the mapping; SQL count can exceed the number of roots.
- For plain bulk SQL, JDBC batching may be more suitable, though it does not replace Spring Data JDBC's aggregate mapping and lifecycle.
