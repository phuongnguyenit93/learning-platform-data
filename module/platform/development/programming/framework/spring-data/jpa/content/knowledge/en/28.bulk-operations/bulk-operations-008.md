# Configuring `batch_size`, `order_inserts`, and `order_updates` in Hibernate

When a business workflow needs to save or update many entities, calling a repository in a loop can generate a large number of SQL transmissions to the database. Hibernate supports **JDBC batching** to group multiple executions of statements of the same shape into a single JDBC batch. The three settings `hibernate.jdbc.batch_size`, `hibernate.order_inserts`, and `hibernate.order_updates` control batch size and sort operations to increase grouping opportunities.

These settings affect how Hibernate sends SQL statements over JDBC. They do not automatically turn multiple JPA operations into a single bulk SQL statement, do not replace transactions, and do not guarantee better performance across every workload. You must configure, observe, and measure on the application's actual JDBC driver and database management system.

## 1. What is JDBC batching?

Without batching enabled, a loop saving 100 entities can cause Hibernate to execute many separate `INSERT` statements. When batching is enabled, Hibernate can prepare `PreparedStatement` objects of the same shape, add parameter sets to the batch, and call `executeBatch()` in groups.

For example, with a batch size of 50, Hibernate can send up to 50 executions of one statement shape in a single JDBC batch. If there are 120 operations of the same shape and all qualify for grouping, batches of 50, 50, and 20 may form. This is an illustrative example; actual batches depend on statement count, SQL structure, flush timing, ID generation strategy, driver, and provider.

A JDBC batch typically remains multiple executions of the same prepared statement sent in a group. Some drivers can rewrite a batch into a more optimal SQL form, though that depends on the driver and dedicated configuration. Do not assume a batch always becomes a single multi-row `INSERT` statement.

### How does batching differ from bulk operations?

- **JDBC batching:** groups multiple executions of statements with the same SQL structure into a batch. Hibernate still manages each entity and persistence context state.
- **JPQL bulk update/delete:** executes a single statement updating or deleting many records directly. This approach typically bypasses per-entity dirty checking and lifecycle callbacks and can leave the persistence context out of sync with newly updated data.
- **Application-layer batch processing:** splits a large dataset into chunks to bound memory and transaction duration. This approach can be combined with JDBC batching.

These three approaches solve different problems. This article focuses on Hibernate JDBC batching.

## 2. The three main configuration properties

### 2.1. `hibernate.jdbc.batch_size`

This property sets the maximum number of JDBC executions Hibernate groups into a single batch. A value of `0` or leaving it unconfigured usually means JDBC batching is disabled. Set a positive integer to enable batching.

Example:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
~~~

With a value of `50`, Hibernate can group up to 50 operations of the same SQL shape into one batch. This value is the limit per batch, not the maximum number of entities in a transaction. One transaction can emit multiple batches.

A larger size can reduce round-trips between the application and the database, yet it can also increase batch memory usage, packet size, and execution duration per batch. There is no single optimal value for all systems. You can start testing around 25 or 50, then measure with real data and driver behavior.

### 2.2. `hibernate.order_inserts`

When a transaction saves multiple entity types interleaved, the persist order can produce an SQL sequence that constantly switches between tables. Because batching generally only groups statements with identical structures, interleaving can shrink batch sizes.

Enable `hibernate.order_inserts` so Hibernate sorts insert operations in a way that keeps inserts of the same entity type closer together. Consequently, Hibernate has more opportunity to group them into the same batch.

~~~properties
spring.jpa.properties.hibernate.order_inserts=true
~~~

For instance, the application persists `Book`, `Author`, `Book`, `Author` in sequence. With insert ordering enabled, Hibernate can group inserts for the same entity type rather than strictly keeping the Java persist call order. Actual SQL ordering is managed by Hibernate and may differ from the operation order in Java code.

### 2.3. `hibernate.order_updates`

Enable `hibernate.order_updates` so Hibernate sorts update operations, typically by entity type and primary key, to increase the likelihood of batching updates of the same shape. Sorting in a consistent order can also reduce deadlock likelihood in certain scenarios where concurrent transactions update the same records.

~~~properties
spring.jpa.properties.hibernate.order_updates=true
~~~

This setting does not completely eliminate deadlocks and does not replace lock ordering design, short transactions, or retry strategies. It also incurs sorting overhead; measure its impact on real workloads.

## 3. Configuring in Spring Boot

For a Spring Boot application using Hibernate as the JPA provider, declare the properties in `application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Or use `application.yml`:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

Spring Boot forwards properties under `spring.jpa.properties` to Hibernate. If configuring Hibernate directly without Spring Boot, the corresponding property names are `hibernate.jdbc.batch_size`, `hibernate.order_inserts`, and `hibernate.order_updates`.

These properties are Hibernate-specific settings. If the application uses another JPA provider, do not assume that provider understands or applies them.

## 4. Example saving multiple entities in one transaction

Suppose the project has a `Book` entity and a Spring Data JPA repository. You can use `EntityManager` to save in batches and periodically release the persistence context:

~~~java
import java.util.List;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookImportService {
    private final EntityManager entityManager;

    public BookImportService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void importBooks(List<Book> books) {
        int flushInterval = 50;

        for (int i = 0; i < books.size(); i++) {
            entityManager.persist(books.get(i));

            if ((i + 1) % flushInterval == 0 || i + 1 == books.size()) {
                entityManager.flush();
                entityManager.clear();
            }
        }
    }
}
~~~

This example is a service snippet meant to be placed in a Spring Boot project with the `Book` entity, Jakarta Persistence, and the Hibernate configuration from the previous section; it is not a standalone Java program to run with `javac` alone.

How it works:

1. `persist()` places new entities into the persistence context. Hibernate tracks these entities and prepares insert operations.
2. Every 50 entities, `flush()` synchronizes pending changes to the database. With batching configured, Hibernate can send eligible inserts in batches.
3. `clear()` removes all managed entities from the persistence context, helping prevent memory from growing continuously during a large import.
4. The final condition handles the remainder when the entity count is not divisible by 50.

`flush()` is not synonymous with `commit()`. It sends pending changes to the database within the current transaction; the transaction can still roll back afterward. `clear()` detaches all managed entities in the persistence context. Therefore, only use this pattern when import work can be isolated and you do not need to continue operating on detached entities.

`flushInterval` in the example is set equal to `batch_size` for clarity. These two values have different purposes: `hibernate.jdbc.batch_size` limits operations in a single JDBC batch, whereas `flushInterval` decides when the application instructs Hibernate to flush and clear the persistence context. You can choose a different flush interval after measuring.

## 5. Important note on ID generation strategy

A common reason insert batching fails to work as expected is the `IDENTITY` primary key generation strategy.

With `GenerationType.IDENTITY`, Hibernate must execute the insert so the database generates the auto-increment ID and returns it. Because it needs the ID immediately upon insert, Hibernate usually cannot defer and group inserts via standard JDBC batching. Consequently, insert batching is disabled for entities using the identity identifier generator in Hibernate.

On databases supporting sequences, `GenerationType.SEQUENCE` is generally better suited for insert batching because Hibernate can obtain IDs before sending inserts. Example declaration:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;

@Entity
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "book_seq")
    @SequenceGenerator(
        name = "book_seq",
        sequenceName = "book_seq",
        allocationSize = 50
    )
    private Long id;

    // Entity properties and methods
}
~~~

This is an example entity configuration; adjust the sequence name and ID strategy according to your database. `allocationSize` relates to how the provider allocates IDs from the sequence; ensure the database sequence configuration is compatible with Hibernate. Do not switch from IDENTITY to SEQUENCE if the current database or architecture does not support it.

## 6. Batching update operations

Batch updates can work when Hibernate detects changes on managed entities and flushes them to the database. Example:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookPriceService {
    private final BookRepository bookRepository;

    public BookPriceService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void increasePrices(BigDecimal rate) {
        List<Book> books = bookRepository.findAll();

        for (Book book : books) {
            book.setPrice(book.getPrice().multiply(rate));
        }
    }
}
~~~

The snippet assumes `Book` has `getPrice()` and `setPrice(...)`. Entities loaded in the transaction are managed; on flush or commit, Hibernate uses dirty checking to identify entities needing updates. With appropriate `hibernate.jdbc.batch_size` and `hibernate.order_updates`, updates with the same SQL structure can be batched.

The `findAll()` example is only suitable for small datasets. If record counts are large, do not load all entities into memory at once. Use pagination or key-range queries, process in chunks, and control the persistence context with flush/clear.

`hibernate.order_updates=true` orders updates managed by Hibernate; it does not turn a JPQL bulk update into a batch update. If using `@Modifying` with JPQL `UPDATE`, the database executes a single separate bulk statement. After a bulk update, keep in mind the persistence context may still hold stale state; consider clearing or refreshing appropriately.

## 7. When does batching fall short?

- **Using IDENTITY for inserted entity IDs.** Hibernate usually has to insert immediately to retrieve the primary key, so it cannot JDBC-batch those inserts.
- **SQL statements do not share the same shape.** Statements updating different columns or belonging to different tables cannot always be combined into one batch. `order_inserts` and `order_updates` help group them, but do not turn different SQL statements into identical ones.
- **No appropriate transaction.** Batches must execute inside an appropriate transactional and flush context. Invoking each operation in overly short transactions can eliminate batching opportunities.
- **Inappropriate batch size.** Too small a batch may not reduce round-trips enough; too large a batch can increase memory and processing time. Benchmark it.
- **Driver or database limits.** Verify batching support, parameter limits, packet sizes, and driver batch-rewrite options.
- **Persistence context grows too large.** Saving hundreds of thousands of entities without chunked flush/clear can cause memory pressure even when JDBC batching is enabled.
- **Using a non-Hibernate provider.** Properties starting with `hibernate.` are not standard JPA options.

Additionally, ordering statements can change SQL execution order relative to the `persist()` call order or entity modifications in Java. If the system has triggers or logic depending on statement order, test the impact before enabling ordering.

## 8. How to verify batching is actually working

Do not conclude batching is active merely because you added three properties to a config file. Verify in an environment with the Hibernate, JDBC driver, and database matching production:

1. Confirm the application actually uses Hibernate and loads the properties from the right configuration profile.
2. Create a transaction saving more entities than the batch size, e.g., 120 entities with batch size 50.
3. Enable SQL logging or use a JDBC observation tool to inspect prepared statements and batch calls. Simply looking at SQL log lines does not reliably reveal the number of `executeBatch()` calls.
4. Use Hibernate statistics or JDBC/database monitoring tools to observe prepared statement counts, batch executions, duration, and round-trips if provided by the tool.
5. Compare execution time, throughput, and memory usage with batching off/on using the same data, database, and load conditions.
6. Test inserts and updates separately; if inserts are not batching, check the ID generation strategy first.

In Spring Boot, you can enable Hibernate statistics in test environments using:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Do not leave overly verbose logging or resource-intensive statistics enabled by default in production without evaluating their impact. Numbers in H2 or mock databases also do not substitute for measurements on the real database engine and driver.

## 9. Practical configuration workflow

1. Identify whether the workload is insert-heavy, update-heavy, or both; identify frequently written entities and tables.
2. Enable `hibernate.jdbc.batch_size` with a moderate starting value, such as 25 or 50.
3. Enable `hibernate.order_inserts=true` if the workload has inserts across multiple entity types or interleaved inserts.
4. Enable `hibernate.order_updates=true` if the workload has many updates and needs improved batching; also check impact on deadlocks and statement order.
5. Check ID generators, especially avoiding expecting insert batching with `IDENTITY`.
6. For large imports, set reasonable transactions and split into chunks for controlled persistence context flush/clear.
7. Re-measure with the target JDBC driver and database; tune batch size based on throughput, latency, memory, and database limits.

| Property | Role | What to check |
|---|---|---|
| `hibernate.jdbc.batch_size` | Max JDBC executions per batch | Driver support, batch size, round-trips |
| `hibernate.order_inserts` | Sorts inserts to group operations of the same type | Inserts sharing SQL structure, ID generator |
| `hibernate.order_updates` | Sorts updates to improve batching likelihood | Update volume, lock ordering, deadlocks, and sorting overhead |

When configured properly, JDBC batching helps Hibernate reduce the overhead of sending many individual SQL statements. Effectiveness depends on grouping statements of the same shape, ID generation strategy, transactions, persistence context, driver, and database. Treat these three properties as optimization tools requiring measurement, not automatic switches guaranteeing every bulk operation runs faster.
