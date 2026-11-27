# Callback Limitations with RowMapper or Custom Write SQL

## 1. Why don't callbacks always run?

Spring Data JDBC provides lifecycle callbacks and lifecycle events so applications can hook into specific points of an aggregate's lifecycle. For example, before saving you can normalize data or generate an ID; after saving you can record activity; after loading you can enrich the aggregate.

A common misconception is that every SQL operation in an application goes through Spring Data JDBC's persistence lifecycle. When an application:

- Uses a custom `RowMapper` or `ResultSetExtractor` on a query method.
- Uses `@Modifying` with `@Query` to update or delete data directly.
- Uses `JdbcTemplate` or `NamedParameterJdbcTemplate` to run SQL.

part or all of Spring Data JDBC's lifecycle pipeline may not be invoked. If the application relies on callbacks to update audit fields, normalize data, or detect saves, switching to custom mapping or SQL can make that behavior vanish.

It is important to distinguish three execution paths:

1. Repositories using Spring Data JDBC's default mapping.
2. Repository queries using a custom `RowMapper`/`ResultSetExtractor`.
3. Direct write SQL via `@Modifying` or Spring JDBC.

These three paths do not share the same callback behavior. This lesson explains the exact limitations, callbacks/events in the aggregate lifecycle, and how to keep business rules consistent when custom SQL is needed.

## 2. What are lifecycle callbacks and lifecycle events?

Spring Data JDBC has two related mechanisms with different goals:

| Mechanism | Purpose | Characteristics |
| --- | --- | --- |
| `EntityCallback` | Synchronously intervene in a step of persistence or mapping | Can receive and return a modified aggregate; suitable for immutable objects and auditing. |
| Lifecycle event | Notify that a stage in the aggregate lifecycle has occurred | Listeners react to events; events are not the primary mechanism for modifying aggregates. |

For example, `BeforeConvertCallback` can normalize an aggregate before Spring Data JDBC converts it into SQL operations. `BeforeSaveEvent` notifies that an aggregate is about to be saved. Callbacks are better when you need to modify an object; events are better when you need to notify other components.

Spring Data encourages using callbacks instead of events when modifying objects, since callbacks support immutable classes and execute in a deterministic pipeline order. Lifecycle events rely on `ApplicationEventMulticaster`; if the multicaster is configured with a `TaskExecutor`, listener execution timing may no longer be synchronous with the persistence step.

## 3. Callbacks and events in Spring Data JDBC

Spring Data JDBC emits lifecycle callbacks/events for the **aggregate root**. Callbacks do not run separately for each child object inside an aggregate. If you need to process child entity data, work through the aggregate root containing it.

### 3.1. Main callbacks

| Stage | Callback | Timing |
| --- | --- | --- |
| Before delete | `BeforeDeleteCallback` | Before rows belonging to the aggregate are deleted. |
| After delete | `AfterDeleteCallback` | After the aggregate has been deleted. |
| Before conversion for save | `BeforeConvertCallback` | After Spring decides insert or update, before creating the SQL plan. |
| Before executing save statements | `BeforeSaveCallback` | After the aggregate change plan is created, before SQL runs. |
| After save | `AfterSaveCallback` | After the SQL statements saving the aggregate have run. |
| After conversion on load | `AfterConvertCallback` | After the aggregate root is constructed from ResultSet and properties are populated. |

Key points in the save order:

1. Spring Data JDBC determines whether the aggregate is new or existing.
2. Invokes `BeforeConvertCallback`.
3. Builds `AggregateChange`, containing the `DbAction`s to execute and deciding which ID is sent to the database.
4. Invokes `BeforeSaveCallback`.
5. Executes the SQL statements.
6. Invokes `AfterSaveCallback`.

Therefore, if you want to generate an ID for a new aggregate yourself, use `BeforeConvertCallback`. By `BeforeSaveCallback`, the insert/update decision and ID plan have already been made; it is not the right place to generate a new ID.

When loading an aggregate, `AfterConvertCallback` runs after the aggregate root has been converted from database data.

### 3.2. Lifecycle events

| Event | Publish timing |
| --- | --- |
| `BeforeDeleteEvent` | Before the aggregate root is deleted. |
| `AfterDeleteEvent` | After the aggregate root is deleted. |
| `BeforeConvertEvent` | Before the aggregate root is converted into an SQL plan. |
| `BeforeSaveEvent` | Before the aggregate root is saved, after the insert/update decision. |
| `AfterSaveEvent` | After the aggregate root is saved. |
| `AfterConvertEvent` | After the aggregate root is created from ResultSet and properties are populated. |

The events above are not per-table or per-child-object events. Even if an aggregate has many child rows, events still represent the aggregate root lifecycle.

## 4. Callbacks work on the default repository path

When using a CRUD repository or standard aggregate persistence, Spring Data JDBC executes the aggregate mapping and persistence flow. This is the execution path callbacks/events are designed to join.

Example callback normalizing a customer's name before saving:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer) {
        return customer.withName(customer.name().trim());
    }
}
~~~

`Customer` in the example is an immutable record/class with a `withName` method. The callback returns the modified instance so Spring Data JDBC continues converting and saving it.

If using a mutable aggregate root, the callback can return the same instance after mutating properties. With immutable objects, return a new instance.

### 4.1. Callbacks do not replace domain behavior

Callbacks are appropriate for technical logic tied to persistence, such as:

- Normalizing a value before saving.
- Assigning an ID in `BeforeConvertCallback`.
- Updating auditing metadata.
- Populating consistent technical data whenever an aggregate is saved.

Rules such as "an order can only be cancelled while in draft status" or "no order lines can be added after the order is submitted" belong in the aggregate/domain model or application service. Do not hide core business logic in callbacks, because callbacks do not replace explicit domain contracts and behavior.

## 5. @Query with default mapping vs. custom mapping

Simply writing `@Query` does not disable callbacks. Spring Data JDBC uses the same default `RowMapper` for `@Query` results as for framework-generated queries. If the query uses default mapping and returns an aggregate managed by Spring Data JDBC, lifecycle mapping can continue to participate.

Example query using default mapping:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findByEmail(@Param("email") String email);
}
~~~

The SQL statement must return all columns required by the entity's constructor. Properties set via setters, withers, or field access may be optional if no matching column exists; when a column is missing, that property is left unset. For aggregates with one-to-one relationships, column names must follow Spring Data JDBC's relation prefix conventions. Entity collections/maps/lists may require separate queries generated by the framework.

If you only need custom SQL while still keeping Spring Data JDBC's default mapping, consider having the query return the aggregate in the exact format the default mapper expects.

## 6. Custom RowMapper or ResultSetExtractor disables callbacks and events

This is the most important limitation in this lesson.

Spring Data JDBC lets you specify a custom mapper in `@Query`, such as:

- `rowMapperClass`
- `rowMapperRef`
- `resultSetExtractorClass`
- `resultSetExtractorRef`

In addition, you can register `QueryMappingConfiguration` to select a `RowMapper` based on a query method's return type.

**When using a custom `RowMapper` via `QueryMappingConfiguration`, `@Query(rowMapperClass = ...)`, or a custom `ResultSetExtractor`, Spring Data JDBC disables Entity Callbacks and Lifecycle Events for mapping the results.** Custom mappers may emit events or call custom logic themselves if the application needs it.

Example:

~~~java
public final class CustomerSummaryRowMapper
        implements RowMapper<CustomerSummary> {

    @Override
    public CustomerSummary mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        );
    }
}
~~~

Using the mapper on a query:

~~~java
public interface CustomerReportRepository
        extends Repository<Customer, Long> {

    @Query(
        value = """
            SELECT id, display_name, email
            FROM customers
            WHERE active = true
            """,
        rowMapperClass = CustomerSummaryRowMapper.class
    )
    List<CustomerSummary> findActiveSummaries();
}
~~~

In this case, `CustomerSummaryRowMapper` constructs DTOs from the ResultSet itself. Spring Data JDBC does not run `AfterConvertCallback` or lifecycle events for results mapped by a custom mapper.

### 6.1. Registering RowMapper by return type

If multiple queries return the same type and need a shared mapper, you can register `QueryMappingConfiguration`:

~~~java
@Configuration
public class QueryMappingConfig {

    @Bean
    QueryMappingConfiguration queryMappingConfiguration() {
        return new DefaultQueryMappingConfiguration()
                .register(CustomerSummary.class,
                        new CustomerSummaryRowMapper());
    }
}
~~~

Spring Data JDBC resolves mappers by the method's return type. For `Optional<CustomerSummary>` or collections containing `CustomerSummary`, the framework unwraps the wrapper to determine the type to map. Registration order matters: more specific types should be registered before more general types.

When configuring a custom mapper this way, query methods returning the matching type and using that mapper will not run entity callbacks and lifecycle events for result mapping.

### 6.2. Using ResultSetExtractor has the same limitation

`ResultSetExtractor` allows processing the entire ResultSet, such as building a nested structure or aggregating multiple rows into one object. When specifying a custom extractor for a query method, Spring Data JDBC also disables entity callbacks and lifecycle events for that mapping.

This is intentional: the framework cannot assume a custom mapper/extractor constructed an aggregate along the exact lifecycle performed by default mapping. If the mapper manages object creation itself, it is also responsible for any extra steps the application needs.

## 7. JdbcTemplate RowMapper does not run Spring Data callbacks

Another case is using `JdbcTemplate` directly:

~~~java
List<Customer> customers = jdbcTemplate.query(
        "SELECT id, name, email FROM customers WHERE active = ?",
        (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("email")
        ),
        true
);
~~~

Even if `RowMapper` creates objects of the same `Customer` class as the aggregate root, this operation does not go through Spring Data JDBC's repository/aggregate mapping pipeline. Consequently, Spring Data JDBC does not automatically invoke:

- `AfterConvertCallback`.
- Lifecycle event `AfterConvertEvent`.
- Aggregate save or delete callbacks/events.
- Auditing mechanisms tied to aggregate persistence.

`JdbcTemplate` simply executes SQL and invokes the mapper supplied by the caller. It does not infer that the newly created object is an aggregate root requiring lifecycle callbacks.

If you only need to read data for reports or screens, map to a DTO/projection instead of constructing a fake aggregate just to reuse the domain class. If you need an aggregate with lifecycle behavior, use a repository or `JdbcAggregateTemplate` with default mapping.

## 8. Custom write SQL does not invoke callbacks or events

Data-modifying queries annotated with `@Modifying` execute directly against the database:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET display_name = :name
    WHERE id = :id
    """)
int updateDisplayName(
        @Param("id") Long id,
        @Param("name") String name
);
~~~

With modifying queries, Spring Data JDBC does not invoke lifecycle events or entity callbacks. This means:

- `BeforeSaveCallback` does not run.
- `AfterSaveCallback` does not run.
- `BeforeSaveEvent` and `AfterSaveEvent` are not published.
- Auditing callbacks do not automatically update `@LastModifiedDate` or `@LastModifiedBy` fields.

If the SQL statement does not update audit columns, those columns keep their old values. Having the method return `int` or `boolean` only reports the affected row count; it does not trigger callbacks.

The same applies when using `JdbcTemplate.update(...)` or `NamedParameterJdbcTemplate.update(...)`. SQL executes directly and bypasses the aggregate save pipeline.

### 8.1. Direct DELETE also lacks aggregate lifecycle like repository delete

If using custom SQL to delete rows, do not expect `BeforeDeleteCallback`, `AfterDeleteCallback`, `BeforeDeleteEvent`, or `AfterDeleteEvent` to be invoked automatically. Spring Data JDBC has no efficient way to deduce exactly which aggregates are affected by a custom SQL statement that may touch many rows.

If the business requires pre/post-delete processing for aggregates, use the aggregate delete path or invoke necessary logic in the application service. For bulk deletes, explicitly design how auditing, outbox, and related associations are handled.

## 9. Why can't Spring Data JDBC invoke callbacks automatically for bulk SQL?

Suppose a query updates thousands of customers:

~~~sql
UPDATE customers
SET active = false
WHERE last_seen < :cutoff;
~~~

To run callbacks like `BeforeSaveCallback<Customer>` for each customer, the framework would have to:

1. Find every affected aggregate.
2. Load each aggregate along with required child data.
3. Invoke callbacks for each aggregate.
4. Recompute changes and SQL statements.
5. Ensure results did not change between reading and updating.

This would be very expensive and defeats the purpose of bulk SQL. A bulk modification statement intentionally skips materializing individual aggregates. Therefore, Spring Data JDBC does not invoke callbacks/events for modifying queries.

If an operation must enforce per-aggregate domain behavior, load and process each aggregate via the repository. If it is a well-defined maintenance/bulk operation, place required rules into SQL, constraints, or service workflows.

## 10. Auditing when using custom write SQL

Spring Data JDBC auditing normally relies on entity callbacks. When using the aggregate persistence path, annotations such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` are updated per auditing configuration.

With `@Modifying` or direct JDBC, these values are not updated automatically. Three common ways to handle this exist.

### 10.1. Update audit fields directly in SQL

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET display_name = :name,
        last_modified_at = CURRENT_TIMESTAMP,
        last_modified_by = :actor
    WHERE id = :id
    """)
int updateDisplayName(
        @Param("id") Long id,
        @Param("name") String name,
        @Param("actor") String actor
);
~~~

SQL explicitly writes the audit columns to update. This is transparent and suitable for certain bulk operations. Ensure the actor value comes from an authenticated security/application context, never trusting arbitrary client-supplied values directly.

### 10.2. Use database defaults or triggers

If auditing rules apply across every write path, database defaults or triggers can protect data even when SQL originates from another application. However, triggers must be designed consistently with application-layer auditing so two places do not overwrite timestamps or actors inconsistently.

### 10.3. Use aggregate persistence when auditing callbacks are required

If the operation updates a single aggregate following domain behavior and needs auditing callbacks, load the aggregate, call domain behavior, and save via the repository or `JdbcAggregateTemplate`. Do not use modifying queries merely to save a few lines of code if doing so drops essential aggregate rules.

## 11. Preserving domain behavior with custom mappers or SQL

Callbacks are not the only logic that can be bypassed. When stepping outside aggregate persistence, the application must also consider:

- Are domain invariants checked?
- Are values normalized as before?
- Is `@Version`/optimistic locking enforced?
- Is audit metadata recorded?
- Are child entities synchronized properly?
- Do outbox events or audit rows need to be written?
- Are post-commit side effects needed?

Example SQL changing order status:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id;
~~~

This SQL does not call `order.cancel()` and does not check whether the order is in a cancellable state. If the rule only allows cancelling draft orders, the condition must be expressed in domain/application logic or in SQL:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status = 'DRAFT';
~~~

Then inspect the affected row count. For rich business logic, loading the aggregate, calling domain behavior, and saving is usually much clearer.

## 12. When events need to be emitted after direct SQL

If a `@Modifying` or `JdbcTemplate.update` statement modifies data and the application needs to notify other systems, do not expect Spring Data JDBC to emit `AfterSaveEvent` automatically.

You can orchestrate this explicitly in the application service:

~~~java
@Service
public class CustomerStatusService {

    private final CustomerRepository customers;
    private final OutboxRepository outbox;

    public CustomerStatusService(
            CustomerRepository customers,
            OutboxRepository outbox
    ) {
        this.customers = customers;
        this.outbox = outbox;
    }

    @Transactional
    public void deactivate(Long id) {
        int changed = customers.deactivateById(id);

        if (changed != 1) {
            throw new IllegalStateException("Customer was not deactivated");
        }

        outbox.save(OutboxMessage.customerDeactivated(id));
    }
}
~~~

In the example, `deactivateById` is a modifying query and `outbox.save` writes the message to emit in the same transaction. After commit, a separate publisher reads the outbox and sends the message. If the transaction rolls back, both the customer change and outbox row roll back.

If only in-process notifications are needed, the application service can publish an application event explicitly. For messages that must survive a process crash after commit, a transactional outbox is usually more reliable than publishing in-memory events alone.

## 13. When to use callbacks, RowMapper, or direct SQL?

| Need | Suitable approach |
| --- | --- |
| Normalizing an aggregate before saving | `BeforeConvertCallback` |
| Generating an ID for a new aggregate | `BeforeConvertCallback` |
| Modifying an aggregate before SQL runs | `BeforeSaveCallback`, understanding `AggregateChange` is already created |
| Reacting after an aggregate is saved | `AfterSaveCallback` or appropriate lifecycle event |
| Modifying an aggregate after loading via default mapping | `AfterConvertCallback` |
| Notifying listeners about lifecycle stages | Lifecycle event |
| Returning DTOs/projections for reports | Custom `RowMapper` or `ResultSetExtractor` |
| Optimizing specialized query mapping | Custom `RowMapper`/`QueryMappingConfiguration`, handling required logic explicitly |
| Bulk updating by condition | `@Modifying` or `JdbcTemplate`, updating audits/invariants explicitly |
| Executing business logic on one aggregate | Repository or `JdbcAggregateTemplate` |

Do not pick a custom RowMapper merely to rename a couple of columns if default mapping already meets your needs. Custom mapping can disable callbacks/events, so weigh that impact before using it.

## 14. Testing callback boundaries

Both the aggregate persistence path and custom paths should be tested to avoid relying on false assumptions.

### 14.1. Testing callbacks on repository save

Create an observable callback:

~~~java
@Component
public class CustomerSaveCallback
        implements BeforeConvertCallback<Customer> {

    private final CustomerCallbackProbe probe;

    public CustomerSaveCallback(CustomerCallbackProbe probe) {
        this.probe = probe;
    }

    @Override
    public Customer onBeforeConvert(Customer customer) {
        probe.record(customer.id());
        return customer;
    }
}
~~~

In an integration test, call `repository.save(customer)` and verify the probe was invoked.

### 14.2. Testing custom RowMapper

Declare a query method using `rowMapperClass` or `QueryMappingConfiguration`. Call the method and verify the DTO results are correct while the callback probe is not invoked for that mapping.

### 14.3. Testing modifying queries

Call a method with `@Modifying @Query`, then verify:

- Database rows are updated.
- Save callbacks/events are not invoked.
- Audit fields change only if updated by the SQL statement or handled by database triggers.
- The row count reflects affected rows.

### 14.4. Testing transactions and outbox

If custom write SQL must emit events, test:

1. Updating data and writing outbox in the same transaction.
2. Intentionally failing the outbox write step.
3. Verifying the business data change also rolls back.
4. Running successfully and verifying the publisher only processes committed messages.

Use a database integration setup matching production when testing specialized SQL, triggers, or transaction semantics.

## 15. Common mistakes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `AfterConvertCallback` does not run after query | Query uses a custom `RowMapper` or `ResultSetExtractor` | Use default mapping if callbacks are needed, or call required logic explicitly in the mapper/service. |
| Callback runs on `findById` yet not on custom query | Two different mapping paths | Check `rowMapperClass`, `rowMapperRef`, `QueryMappingConfiguration`, and `ResultSetExtractor`. |
| `@LastModifiedDate` does not change after bulk update | `@Modifying` executes SQL directly without calling auditing callbacks | Update audit fields in SQL, use triggers, or switch to aggregate save. |
| `AfterSaveEvent` is not published after `@Modifying` | Modifying queries do not invoke lifecycle events/callbacks | Emit application events/outbox explicitly if the use case requires it. |
| RowMapper builds an aggregate yet callbacks still do not run | Creating objects with a JDBC mapper bypasses the aggregate mapping pipeline | Use repository/`JdbcAggregateTemplate` or run required logic explicitly. |
| Child entity receives no separate callback | Lifecycle callbacks/events are emitted only for the aggregate root | Process children via the containing aggregate root's callbacks/listeners. |
| Event listener handles events at the wrong time | Event multicaster may run asynchronously | Use EntityCallback for synchronous modifications; use transaction-aware events/outbox for time-sensitive side effects. |
| Direct SQL violates invariants | SQL path bypasses domain behavior | Put conditions in domain/service/SQL constraints or use aggregate persistence. |
| Bulk update ignores version | Custom SQL does not automatically apply optimistic locking | Include expected version in the condition and increment version in the same statement if needed. |

## 16. Process for choosing an execution path

Before replacing default mapping or using custom write SQL, answer:

1. **Is the result an aggregate or a DTO?** If only a projection is needed, a custom RowMapper is usually suitable.
2. **Are lifecycle callbacks needed on load?** If yes, avoid custom RowMapper/ResultSetExtractor or run the equivalent logic yourself.
3. **Are callbacks needed on save/delete?** Custom write SQL does not invoke save/delete callbacks/events.
4. **Is auditing required?** Clarify who updates `created_at`, `last_modified_at`, actor, and related fields.
5. **Are invariants or versions involved?** Direct SQL must protect them explicitly.
6. **Are post-commit side effects required?** Consider application events or a transactional outbox.
7. **Are child entities affected?** Remember callbacks/events are emitted for the aggregate root.
8. **Has each execution path been tested?** Test default repository paths, custom mapping, and direct DML separately.

## 17. Practice exercises

**Exercise 1 — Default callbacks.** Create `BeforeConvertCallback<Customer>` to normalize names. Save a customer via the repository and confirm the value is normalized before writing.

**Exercise 2 — Default mapping with @Query.** Write a `@Query` returning `Customer` with default mapping. Ensure the SELECT returns all columns required by the constructor and observe post-convert callbacks.

**Exercise 3 — Custom RowMapper.** Create `CustomerSummaryRowMapper`, attach it via `rowMapperClass`, invoke the query, and verify Spring Data JDBC callbacks/lifecycle events are not invoked for custom mapping.

**Exercise 4 — QueryMappingConfiguration.** Register a mapper for a return type. Test a query method using that type and observe differences from default mapping.

**Exercise 5 — Modifying query.** Write a `@Modifying @Query` updating a customer. Verify `AfterSaveCallback` does not run and update audit columns manually in SQL.

**Exercise 6 — JdbcTemplate.** Use `JdbcTemplate` to construct objects via RowMapper. Compare with `repository.findById` and explain why the same Java class does not mean the same lifecycle.

**Exercise 7 — Outbox.** Perform a bulk update and write an outbox row in the same transaction. Make the outbox insert fail and verify the bulk update rolls back.

**Exercise 8 — Aggregate root and children.** Create an aggregate with a child collection. Observe that callbacks receive the aggregate root and design child handling without expecting per-element callbacks.

## 18. Key takeaways

Spring Data JDBC invokes lifecycle callbacks/events on the default aggregate persistence and mapping path. Callbacks/events are emitted for the aggregate root, not individual child objects. `BeforeConvertCallback` fits preparing aggregates and generating IDs; `BeforeSaveCallback` runs after the `AggregateChange` plan is built; `AfterSaveCallback` and `AfterConvertCallback` correspond to post-save and post-load steps.

A `@Query` using default mapping does not automatically disable callbacks. However, a custom `RowMapper` via `QueryMappingConfiguration` or `rowMapperClass`, as well as a custom `ResultSetExtractor`, disables Entity Callbacks and Lifecycle Events for result mapping. `@Modifying` queries execute SQL directly and therefore do not invoke callbacks/events; `JdbcTemplate` likewise sits outside the aggregate lifecycle pipeline.

When using custom mapping or SQL, handle auditing, invariants, versioning, audit logs, and outbox explicitly if your use case requires them. Use callbacks for synchronous technical logic in the aggregate lifecycle, use events for notifications, and use application services to coordinate business logic. Test each execution path separately to ensure behavior does not silently disappear when changing data access strategies.

### References

- [Spring Data Relational – Lifecycle Events and Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational – Query Methods, Custom RowMapper and Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational – BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html)
- [Spring Data Relational – BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [Spring Data Relational – AfterConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/AfterConvertCallback.html)
