# `readOnly` as an Optimization Hint and Data Protection Limitations

In Spring Data JPA, the `readOnly` attribute of `@Transactional` expresses that a transaction is primarily used for reading data. Spring can pass this information to the transaction manager, JDBC driver, or JPA provider to optimize processing. However, `readOnly = true` is a **transaction-layer hint**, not a universal guarantee that every write statement will be blocked.

When designing transactions, distinguish three things: declaring read-only intent in the application, optimizations that the framework/provider may perform, and mechanisms that actually prevent writes at the database level. These three are related but not equivalent.

## 1. What does `readOnly` mean?

You can declare a read-only method as follows:

~~~java
@Transactional(readOnly = true)
public List<Book> findBooks(String author) {
    return bookRepository.findByAuthor(author);
}
~~~

`readOnly` is an attribute of Spring's transaction definition. Its default value is `false`. When set to `true`, the application signals that this transaction does not intend to modify data.

The transaction manager can use that information to prepare the transaction appropriately. Depending on configuration and platform, it may set the read-only flag on the JDBC connection or pass the transaction attribute down to the JPA provider. Some database management systems can enforce a read-only transaction when they receive the corresponding setting. Some drivers or providers treat it only as an optimization hint, or do not fully support it.

Therefore, do not interpret the code snippet above as a universal SQL command like "allow SELECT only." An annotation does not create database-level permissions and does not replace privilege control on the connection account.

## 2. How can Spring Data JPA optimize read-only transactions?

### 2.1. At the Spring and transaction manager layer

Spring stores the `readOnly` attribute in the transaction definition. When starting a transaction, the transaction manager can apply this attribute if both it and the underlying platform support it.

With JDBC, a transaction manager may call `Connection.setReadOnly(true)`. Per JDBC, this is a hint to the driver; the level of support and whether the database rejects write statements depend on the driver and database management system. Other transaction managers or configurations may handle this attribute differently.

### 2.2. At the JPA provider layer

With Hibernate and appropriate Spring integration configuration, read-only transactions are typically optimized by switching the flush mode to `MANUAL`. Hibernate then does not automatically flush the persistence context at ordinary auto-flush points. Hibernate integration may also mark entities loaded within the transaction as read-only to reduce dirty-checking work.

These optimizations can reduce overhead when reading many entities or traversing a large object graph. Exact benefits depend on the Hibernate version, transaction manager configuration, and how the application accesses data.

JPA is a specification, while Hibernate, EclipseLink, and other providers have their own internal mechanisms. Do not assume every provider sets the same flush mode or behaves identically simply because a method is marked `readOnly = true`.

### 2.3. At the database layer

Databases may support read-only transactions at the SQL or session level. If an application needs to guarantee an account can only read, appropriate database permissions must be configured—for example, using an account granted only `SELECT` privileges, or a connection/replica configured solely for read queries.

Simply placing an annotation in Java code is not enough to provide that guarantee. To know whether a write operation will be rejected, inspect the actual configuration of the transaction manager, driver, and running database system.

## 3. Where to place transaction boundaries?

Usually, the service layer is the appropriate place to declare transaction boundaries. A service method can call multiple repositories inside the same transaction, allowing all read operations to share one persistence context.

Spring Data JPA already configures transactions for CRUD methods inherited from the default `SimpleJpaRepository` implementation: read operations are marked read-only, while write operations have their own transaction configuration. However, custom query methods declared by the application generally do not automatically receive default transaction configuration. You can declare `@Transactional` on the query method or—often easier to manage—on the service calling the repository.

Do not scatter annotations indiscriminately across every repository method. Identify which business operation constitutes a unit of work, then place the transaction boundary where that operation is coordinated.

## 4. Example: separating read and write operations

The example below assumes the project already has a `Book` entity with `getId()`, `getTitle()`, and `setTitle(...)` methods, along with Spring Data JPA configuration. Code snippets use Java 17 or higher.

Repository declaring an author query:

~~~java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByAuthor(String author);
}
~~~

DTO returned to the caller:

~~~java
public record BookSummary(Long id, String title) {}
~~~

Service clearly separating read and update methods:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public List<BookSummary> findByAuthor(String author) {
        return books.findByAuthor(author)
                .stream()
                .map(book -> new BookSummary(book.getId(), book.getTitle()))
                .toList();
    }

    @Transactional
    public void renameBook(Long id, String newTitle) {
        Book book = books.findById(id).orElseThrow();
        book.setTitle(newTitle);
    }
}
~~~

In `findByAuthor`, the transaction is marked read-only because the method only queries and maps data to DTOs. Mapping to DTOs inside the transaction boundary also avoids relying on lazy-loaded associations after the transaction ends.

In `renameBook`, `@Transactional` does not set `readOnly = true`, so the transaction uses the default read/write mode. The entity retrieved from the repository is managed by the persistence context. When the method completes and the transaction commits, the JPA provider can use dirty checking to detect changes and write them to the database; therefore, the example does not need to call `save(book)` again.

If a business operation both reads and updates, use a read/write transaction for the entire operation. Do not mark a transaction read-only merely because most statements inside it are queries.

## 5. What does `readOnly = true` guarantee and not guarantee?

| Scenario | Correct understanding |
|---|---|
| Marking a read method with `@Transactional(readOnly = true)` | Expresses read-only intent and lets supporting components apply optimizations. |
| Calling `save()` or a write operation inside a read-only transaction | The annotation does not guarantee the operation will always be blocked. Behavior depends on the transaction manager, provider, driver, and database. |
| Modifying a managed entity | The provider may skip auto-flushing or reduce dirty checking in read-only mode; do not rely on this as a data protection mechanism. |
| Wanting to forbid an application account from updating data | Permissions must be configured in the database or via an equivalent access-control mechanism. |
| Wanting to optimize read queries | Use read-only transactions when appropriate, then measure on your application's actual provider and database. |

A misleading example is:

~~~java
@Transactional(readOnly = true)
public void renameBook(Long id, String newTitle) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.setTitle(newTitle);
}
~~~

This declares the wrong intent because the method modifies data. With Hibernate, read-only flush mode may prevent changes from being auto-flushed like a standard read/write transaction. However, you cannot conclude that all write operations across all configurations will be rejected. A direct JDBC statement, native query, explicit flush, or provider-specific behavior may produce a different outcome.

If a method needs to update data, declare a read/write transaction:

~~~java
@Transactional
public void renameBook(Long id, String newTitle) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.setTitle(newTitle);
}
~~~

## 6. Nested transactions and propagation

The attributes of an active transaction affect methods joining that transaction.

With default `REQUIRED` propagation, if a method is called when a transaction already exists, that method generally joins the existing transaction. For example, an outer service opens a read-only transaction and calls an update service with default `@Transactional`. The inner transaction typically joins the existing read-only transaction; the annotation on the inner method does not turn the current transaction into a read/write transaction.

~~~java
@Service
public class ReportService {
    private final BookService bookService;

    public ReportService(BookService bookService) {
        this.bookService = bookService;
    }

    @Transactional(readOnly = true)
    public void buildReportAndUpdateBook(Long id) {
        // Calls an update method with default REQUIRED propagation.
        // The inner method may join this read-only transaction.
        bookService.renameBook(id, "New Title");
    }
}
~~~

The example above demonstrates a design to avoid: a flow declared read-only invoking a write operation. Separate read and write flows or place appropriate transaction boundaries on the coordinating service.

By default, Spring does not strictly validate every read-only difference when a method joins an existing transaction. You can enable `validateExistingTransaction` on the transaction manager to catch certain incompatible joining transaction configurations; how to enable it depends on the transaction manager type.

`REQUIRES_NEW` propagation can create an independent transaction rather than joining the existing one. Use it only when the business logic genuinely needs separate commit/rollback boundaries. Do not use it as a casual workaround for misplacing `readOnly`, as it alters transaction semantics and connection resource usage.

### Note on Spring proxies

In default proxy mode, Spring applies `@Transactional` when calls go through the proxy. One method in the same object directly calling another method via `this.someMethod()` generally does not go through the proxy, so annotations on the called method may not apply as expected.

Place transaction boundaries on methods called through Spring beans, or organize services so calls pass through the proxy. When troubleshooting transaction bugs, inspect the call path rather than only looking at annotations in source code.

## 7. Common mistakes

- **Treating read-only as an authorization mechanism.** The annotation does not replace `SELECT`/`INSERT`/`UPDATE`/`DELETE` privileges on the database account.
- **Marking an entire service read-only despite having write methods.** If using class-level annotations, redeclare read/write mode on update methods and ensure calls actually go through the proxy.
- **Assuming an inner annotation always overrides an outer transaction.** With `REQUIRED`, the inner method typically joins the existing transaction.
- **Assuming every JPA provider behaves like Hibernate.** Flush mode and dirty-checking optimizations are provider- and configuration-dependent details.
- **Relying on not seeing data updated in one run to conclude it is protected.** Changes may simply not have flushed, may have rolled back, or may be affected by other configuration. To protect data, verify privileges and behavior at the database layer.
- **Placing scattered transactions on repositories while ignoring business operations.** When multiple repository calls need a consistent boundary, the service is usually a more appropriate place to manage transactions.

## 8. How to verify in a project

When applying read-only transactions, verify against your actual running configuration:

1. Identify the actual transaction manager used by the application, such as `JpaTransactionManager` or `DataSourceTransactionManager`.
2. Identify the JPA provider and its version. With Hibernate, verify flush mode and dirty-checking behavior in read-only transactions for the exact version in use.
3. Enable SQL and transaction logging in test environments to observe when statements are emitted. Logs help understand behavior, but do not by themselves prove the database blocks all writes.
4. Write integration tests using the application's actual database management system if you need to verify behavior when writing inside a read-only transaction.
5. If true write prohibition is required, test using a read-only privileged account or database-level read-only configuration. Tests must confirm write statements are rejected by that protection mechanism itself.

Do not rely solely on tests with mocked repositories to draw conclusions about flush behavior, dirty checking, or write permissions. These behaviors depend on the transaction manager, JPA provider, JDBC driver, and real database.

## 9. Rules for choosing transaction mode

- Use `@Transactional(readOnly = true)` for service methods that only query, aggregate, or transform read data.
- Use default `@Transactional` for operations that modify entities, invoke writes, or require both reads and writes within the same transaction.
- Place business-level transaction boundaries at the service layer so related repository operations share one transaction.
- Use database permissions, read-only accounts, or database-tier read-only configurations when writes must be strictly impossible.

Treat `readOnly` as a signal helping Spring and the JPA provider optimize read transactions. Data protection must still be designed and verified at the layer capable of enforcing access rights.