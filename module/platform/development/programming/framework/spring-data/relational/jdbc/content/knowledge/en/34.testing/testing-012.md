# Testing Callbacks, Auditing, and Direct SQL Writes

Spring Data JDBC offers several extension points in the persistence lifecycle. Entity callbacks can populate or modify data before/after saving; auditing automatically populates actor and timestamp metadata; and repository queries or direct SQL can mutate the database through a different execution path.

A test that merely checks a row was written to the database does not prove these behaviors work properly. You must verify separately:

1. Which callbacks are invoked, at what moment, and for which aggregates.
2. Whether auditing metadata is populated/updated with the right actor and timestamp.
3. Whether repository saves trigger the lifecycle while `@Modifying`, `JdbcTemplate`, or `JdbcClient` bypass it.
4. Whether transactions roll back related changes if a write step fails.

This lesson covers the Spring Data JDBC callback pipeline, writing tests with `@DataJdbcTest`, fixing `AuditorAware` and `DateTimeProvider`, verifying auditing by reloading data from the database, and confirming the boundaries of direct SQL.

## 1. Distinguishing Callbacks, Events, and Auditing

Three related concepts serve different purposes.

| Mechanism | Purpose | Example |
|---|---|---|
| Entity callback | Synchronous intervention in entity lifecycle | Assign a default value before save |
| Lifecycle event | Notify listeners that a persistence phase occurred | Log when an aggregate is saved |
| Auditing | Populate actor and timestamp metadata | `@CreatedBy`, `@LastModifiedDate` |

Entity callbacks can return a modified entity and are invoked synchronously in sequence. Lifecycle events typically notify listeners; if `ApplicationEventMulticaster` is configured with a `TaskExecutor`, event handling can happen asynchronously.

Spring Data JDBC auditing integrates via entity callbacks. Therefore, when testing auditing, exercise the repository/template path that actually executes callbacks.

## 2. Callback Pipeline When Spring Data JDBC Saves an Aggregate

A single aggregate save follows this general sequence:

~~~text
repository.save(aggregate)
          |
          v
Determine whether aggregate is new or existing
          |
          v
BeforeConvertCallback / BeforeConvertEvent
          |
          v
Create AggregateChange and DbActions
          |
          v
BeforeSaveCallback / BeforeSaveEvent
          |
          v
Execute SQL on database
          |
          v
AfterSaveCallback / AfterSaveEvent
          |
          v
Return saved aggregate
~~~

Key callbacks:

| Callback | Timing | When to Use |
|---|---|---|
| `BeforeConvertCallback` | Before aggregate is converted into database changes | Normalize data or assign application IDs |
| `BeforeSaveCallback` | After `AggregateChange` is created, before SQL runs | Inspect or adjust the change plan |
| `AfterSaveCallback` | After save SQL executes | Observe persistence outcome |
| `AfterConvertCallback` | After aggregate is materialized from `ResultSet` | Enrich data after reading |
| `BeforeDeleteCallback` | Before deleting aggregate | Validate or record deletion intent |
| `AfterDeleteCallback` | After aggregate is deleted | Observe deletion outcome |

### 2.1. Choosing the Right Callback Timing

If you need to modify persistent properties before the framework generates SQL, use `BeforeConvertCallback`.

`BeforeSaveCallback` runs after Spring Data JDBC has already created `AggregateChange`. Modifying a persistent aggregate property at this point may no longer be reflected in the generated `DbAction`s. This callback suits operating on `MutableAggregateChange`, not as a general place to mutate arbitrary fields before mapping.

If you only want to observe results after saving, use `AfterSaveCallback`.

### 2.2. Callbacks Are Bound to the Aggregate Root

Spring Data JDBC emits lifecycle callbacks/events for the aggregate root. If you need to process child entities, normally handle them through the aggregate root or a listener receiving the aggregate containing its children.

Do not write tests assuming each `OrderLine` in a collection receives its own separate `AfterSaveCallback` as if it were an independent entity.

## 3. Writing a Testable Callback

Example callback assigning a reference code before the aggregate is converted into database changes:

~~~java
public class OrderReferenceCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder order) {
        if (order.getReference() == null) {
            order.setReference("ORD-" + order.getIdempotencyKey());
        }

        return order;
    }
}
~~~

The callback can be registered as a bean:

~~~java
@Configuration
class OrderCallbackConfiguration {

    @Bean
    OrderReferenceCallback orderReferenceCallback() {
        return new OrderReferenceCallback();
    }
}
~~~

In real applications, callbacks should do short, deterministic, easily testable work. Avoid making HTTP calls or sending messages directly inside a callback. If a callback runs inside a transaction and throws an exception, the save can roll back; external side effects do not automatically roll back with it.

### 3.1. Ordering Multiple Callbacks

If multiple callbacks of the same type exist for one domain type, default ordering is not guaranteed. You can specify order using `@Order` or implementing `Ordered`.

~~~java
@Component
@Order(100)
class NormalizeOrderCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder order) {
        order.normalizeReference();
        return order;
    }
}
~~~

Callbacks execute sequentially; the result of an earlier callback is passed to the next. When ordering matters to business rules, test that ordering explicitly rather than relying on bean initialization order.

## 4. Testing Callbacks with @DataJdbcTest

With Spring Boot, `@DataJdbcTest` is the test slice for Spring Data JDBC. It auto-configures repositories, `JdbcTemplate`, and typically uses an embedded database if present on the classpath. Tests run inside a transaction that rolls back by default on completion.

Example:

~~~java
@DataJdbcTest
@Import(OrderCallbackConfiguration.class)
class PurchaseOrderCallbackTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void appliesReferenceCallbackBeforeInsert() {
        PurchaseOrder order = PurchaseOrder.draft("key-101");

        PurchaseOrder saved = repository.save(order);

        assertThat(saved.getReference()).isEqualTo("ORD-key-101");
    }
}
~~~

Test slices do not scan all components like `@SpringBootTest`. Custom callbacks/configurations typically need to be brought in via `@Import`.

If a callback is a `@Component` in production yet the test slice does not load it, the test will not run the callback. In that case the bug is in the test configuration, not necessarily in the callback implementation.

### 4.1. Checking Both the Object and the Database

A callback can return a modified object. To confirm the value was truly written, reload the aggregate or query directly with `JdbcTemplate`:

~~~java
@Test
void persistsCallbackValue() {
    PurchaseOrder order = repository.save(
            PurchaseOrder.draft("key-102")
    );

    String reference = jdbcTemplate.queryForObject(
            "SELECT reference FROM purchase_orders WHERE id = ?",
            String.class,
            order.getId()
    );

    assertThat(reference).isEqualTo("ORD-key-102");
}
~~~

Reloading from the database prevents tests from passing merely by checking an in-memory object without proving SQL wrote the value properly.

## 5. Testing Auditing with Fixed Actor and Time

Auditing usually depends on two data sources:

- `AuditorAware<T>` provides the current actor.
- `DateTimeProvider` provides the creation/modification timestamp.

If tests rely on a real `SecurityContext` or the system clock, results become environment-dependent. Replace both sources with controllable providers in tests.

Example entity:

~~~java
@Table("audit_orders")
public class AuditOrder {

    @Id
    private Long id;

    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("modified_by")
    private String modifiedBy;

    @LastModifiedDate
    @Column("modified_at")
    private Instant modifiedAt;

    public static AuditOrder draft() {
        AuditOrder order = new AuditOrder();
        order.status = "DRAFT";
        return order;
    }

    public void confirm() {
        this.status = "CONFIRMED";
    }

    public Long getId() {
        return id;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getModifiedBy() {
        return modifiedBy;
    }

    public Instant getModifiedAt() {
        return modifiedAt;
    }
}
~~~

Auditing configuration for tests:

~~~java
@TestConfiguration
@EnableJdbcAuditing(
        auditorAwareRef = "testAuditorAware",
        dateTimeProviderRef = "testDateTimeProvider"
)
class AuditTestConfiguration {

    @Bean
    MutableAuditValues mutableAuditValues() {
        return new MutableAuditValues();
    }

    @Bean
    AuditorAware<String> testAuditorAware(MutableAuditValues values) {
        return () -> Optional.of(values.actor());
    }

    @Bean
    DateTimeProvider testDateTimeProvider(MutableAuditValues values) {
        return () -> Optional.of(values.now());
    }
}
~~~

Controllable provider:

~~~java
public class MutableAuditValues {

    private final AtomicReference<String> actor =
            new AtomicReference<>("user-101");

    private final AtomicReference<Instant> now =
            new AtomicReference<>(
                    Instant.parse("2026-11-13T08:00:00Z")
            );

    public String actor() {
        return actor.get();
    }

    public Instant now() {
        return now.get();
    }

    public void setActor(String value) {
        actor.set(value);
    }

    public void setNow(Instant value) {
        now.set(value);
    }
}
~~~

In the test, import configurations explicitly:

~~~java
@DataJdbcTest
@Import({AuditTestConfiguration.class, CallbackTestConfiguration.class})
class AuditOrderRepositoryTest {

    @Autowired
    AuditOrderRepository repository;

    @Autowired
    MutableAuditValues auditValues;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    CountingAfterSaveCallback countingCallback;

    @Test
    void recordsCreatorAndLastModifier() {
        AuditOrder order = AuditOrder.draft();

        AuditOrder created = repository.save(order);

        assertThat(created.getCreatedBy()).isEqualTo("user-101");
        assertThat(created.getModifiedBy()).isEqualTo("user-101");
        assertThat(created.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));

        auditValues.setActor("user-202");
        auditValues.setNow(Instant.parse("2026-11-13T09:30:00Z"));

        AuditOrder loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.confirm();
        repository.save(loaded);

        AuditOrder reloaded = repository.findById(created.getId())
                .orElseThrow();

        assertThat(reloaded.getCreatedBy()).isEqualTo("user-101");
        assertThat(reloaded.getModifiedBy()).isEqualTo("user-202");
        assertThat(reloaded.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
        assertThat(reloaded.getModifiedAt())
                .isEqualTo(Instant.parse("2026-11-13T09:30:00Z"));
    }
}
~~~

The example assumes the test schema contains the matching columns and the repository is configured in the test slice.

### 5.1. Why Must the Entity Be Reloaded?

Do not only assert on the object passed to `save`. Auditing callbacks can return a new instance populated with metadata. Assert on the returned object and/or reload from the database to prove the values were persisted.

### 5.2. Checking modifyOnCreate

`@EnableJdbcAuditing` has a `modifyOnCreate` attribute. By default, entities can be marked modified right at creation time.

If business rules require `modifiedBy`/`modifiedAt` to be populated only after the first modification, configure `modifyOnCreate = false` and write a test verifying that behavior. Do not let tests rely on defaults without explicitly capturing the application's policy.

## 6. Counting Callback Invocations to Verify Lifecycle Execution

A callback that counts invocations helps test whether a save path passes through the lifecycle:

~~~java
public class CountingAfterSaveCallback
        implements AfterSaveCallback<AuditOrder> {

    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public AuditOrder onAfterSave(AuditOrder aggregate) {
        calls.incrementAndGet();
        return aggregate;
    }

    public int calls() {
        return calls.get();
    }
}
~~~

Register the callback in tests:

~~~java
@TestConfiguration
class CallbackTestConfiguration {

    @Bean
    CountingAfterSaveCallback countingAfterSaveCallback() {
        return new CountingAfterSaveCallback();
    }
}
~~~

Tests can verify:

- One repository save triggers one callback for the aggregate root.
- A second repository save increments the counter again.
- Loading an aggregate does not invoke `AfterSaveCallback`.
- A direct SQL update does not increment the counter.

When `saveAll` saves multiple aggregates, callbacks are invoked for each saved aggregate root. Do not assume callbacks run individually per child row.

## 7. Lifecycle Events and Callbacks Are Not Identical

Spring Data JDBC also publishes events such as `BeforeSaveEvent` and `AfterSaveEvent`.

| Criterion | Entity Callback | Lifecycle Event |
|---|---|---|
| Primary purpose | Mutate or govern entity inside lifecycle | Notify listeners of an occurrence |
| Return value | Can return a modified entity | Listeners do not replace the entity in the persistence pipeline |
| Ordering | Controllable via `@Order`/`Ordered` | Depends on `ApplicationEventMulticaster` |
| Async | Callbacks run synchronously in pipeline | Can be async if multicaster has a `TaskExecutor` |
| Auditing | Integrated by Spring Data JDBC via callbacks | Not the primary auditing mechanism |

If logic must run before SQL is generated, prefer the appropriate callback. If you only need to send notifications or update a read model after an event, listeners/events may fit better.

Do not use asynchronous event listeners as a substitute for metadata updates that belong inside the same transaction as the aggregate.

## 8. Callbacks Apply Only to Spring Data JDBC Persistence Paths

This is crucial to test explicitly when a project writes data through multiple paths.

The following write paths are not equivalent:

~~~text
repository.save(aggregate)
       |
       v
Spring Data JDBC lifecycle
       |
       +-- BeforeConvert
       +-- BeforeSave
       +-- SQL
       +-- AfterSave
       +-- Auditing callback

@Modifying @Query / JdbcTemplate / JdbcClient
       |
       v
Direct SQL
       |
       +-- Executes the written SQL statement directly
       +-- Does not invoke aggregate lifecycle callbacks
       +-- Does not populate auditing metadata
       +-- Does not automatically apply aggregate @Version
~~~

Spring Data JDBC documentation states clearly that save/delete callbacks and events are not invoked for derived query methods or annotated queries, because the framework has no efficient way to determine which aggregates are affected.

SQL executed via `JdbcTemplate`, `NamedParameterJdbcTemplate`, or `JdbcClient` likewise bypasses the repository/template lifecycle.

## 9. Testing That @Modifying Queries Do Not Trigger Callbacks

Repository:

~~~java
public interface AuditOrderRepository
        extends CrudRepository<AuditOrder, Long> {

    @Modifying
    @Query("""
        UPDATE audit_orders
        SET status = :status
        WHERE id = :id
        """)
    int updateStatusDirectly(
            @Param("id") Long id,
            @Param("status") String status
    );
}
~~~

Test:

~~~java
@Test
void modifyingQueryDoesNotInvokeSaveCallbackOrAuditing() {
    AuditOrder created = repository.save(AuditOrder.draft());
    int callbackCountBefore = countingCallback.calls();

    auditValues.setActor("user-999");
    auditValues.setNow(Instant.parse("2026-11-13T10:00:00Z"));

    int changed = repository.updateStatusDirectly(
            created.getId(),
            "CANCELLED"
    );

    assertThat(changed).isEqualTo(1);
    assertThat(countingCallback.calls()).isEqualTo(callbackCountBefore);

    AuditOrder reloaded = repository.findById(created.getId())
            .orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("CANCELLED");

    // Direct SQL does not automatically update auditing metadata.
    assertThat(reloaded.getModifiedBy()).isEqualTo("user-101");
    assertThat(reloaded.getModifiedAt())
            .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
}
~~~

This test proves two things:

1. The `UPDATE` statement changed the data.
2. Repository callbacks/auditing did not run automatically for the annotated query.

If direct queries are designed to mutate aggregates, the application must explicitly decide how to update `modified_by`, `modified_at`, `version`, and related side effects.

## 10. Testing Direct Writes via JdbcTemplate

The same principle applies to `JdbcTemplate`:

~~~java
@Test
void jdbcTemplateUpdateBypassesAggregateCallbacks() {
    AuditOrder created = repository.save(AuditOrder.draft());
    int callbackCountBefore = countingCallback.calls();

    jdbcTemplate.update(
            """
            UPDATE audit_orders
            SET status = ?
            WHERE id = ?
            """,
            "CANCELLED",
            created.getId()
    );

    assertThat(countingCallback.calls()).isEqualTo(callbackCountBefore);

    AuditOrder reloaded = repository.findById(created.getId())
            .orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("CANCELLED");
}
~~~

When both the repository and `JdbcTemplate` share the same DataSource and transaction manager in `@DataJdbcTest`, they participate in the same test transaction. Tests roll back by default on completion.

If production uses multiple DataSources or transaction managers, tests must configure the exact DataSource each adapter actually uses.

## 11. When Direct SQL Must Update Auditing Metadata

There are two common approaches:

- Include metadata directly in the SQL statement.
- Use database triggers following consistent conventions.

Example updating metadata directly:

~~~java
int changed = jdbcTemplate.update(
        """
        UPDATE audit_orders
        SET status = ?,
            modified_by = ?,
            modified_at = ?
        WHERE id = ?
        """,
        "CANCELLED",
        actorId,
        clock.instant(),
        orderId
);
~~~

If the aggregate has a version, the SQL statement should check and increment the version:

~~~sql
UPDATE audit_orders
SET status = :status,
    modified_by = :actor,
    modified_at = :modifiedAt,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Tests must verify:

- Affected row count is accurate.
- Metadata updated with the right actor/time.
- Version incremented per policy.
- Requests with stale versions cannot overwrite newer changes.
- Dependent steps roll back together if any step fails.

Do not only assert that the SQL statement affected one row. Reload the data and assert every metadata/version column.

## 12. Testing Auditing for Background Jobs

`AuditorAware` commonly obtains the actor from `SecurityContext`. Background jobs, schedulers, or message consumers may lack an end-user `SecurityContext`.

Tests should verify the actor policy for each flow:

| Flow | Expected Test Actor |
|---|---|
| Authenticated HTTP request | User ID |
| Scheduled job | Service actor, e.g., `system:archive-job` |
| Partner import | Integration identity |
| Migration | Migration identity |
| No actor present | `Optional.empty`, `NULL`, or error per policy |

Do not let tests run solely with a single fixed user and assume background jobs will magically have that actor in production.

For async tasks, security contexts do not necessarily propagate to other threads automatically. Pass actor context explicitly or configure context propagation and test it.

## 13. Testing Transactions and Rollback

Callbacks, repository saves, auditing metadata, and direct SQL can all participate in the same transaction when sharing the same DataSource and transaction manager.

A transaction test can verify:

~~~text
@Transactional test/use case
        |
        +-- repository.save(order)
        |       |
        |       +-- callbacks
        |       +-- auditing metadata
        |
        +-- jdbcTemplate.update(...)
        |
        +-- exception thrown
                |
                v
             ROLLBACK
                |
                +-- root unchanged
                +-- direct SQL has no lasting effect
                +-- audit row in same transaction does not exist
~~~

Example:

~~~java
@Transactional
public void saveAndUpdateThenFail(Long orderId) {
    AuditOrder order = repository.findById(orderId)
            .orElseThrow();

    order.confirm();
    repository.save(order);

    jdbcTemplate.update(
            "UPDATE audit_orders SET status = ? WHERE id = ?",
            "ARCHIVED",
            orderId
    );

    throw new IllegalStateException("Force rollback");
}
~~~

In integration tests, invoke the method via the Spring proxy so the transaction interceptor runs. After rollback completes, open a new transaction/read to verify database state.

Note: if the test method itself is already wrapped in a transaction by `@DataJdbcTest`, understand propagation and transaction completion when testing independent commit/rollback outcomes. Never use a single read inside an unfinished transaction to conclude data rolled back in the database.

## 14. Limitations of H2 and When a Real Database Is Needed

`@DataJdbcTest` commonly uses an embedded database for speed. It suits testing basic mapping, callbacks, and auditing.

However, H2 can differ from the production database in:

- SQL dialect.
- Generated keys and sequences.
- Timestamp/timezone conversions.
- JSON/array/custom types.
- Constraints and locking.
- Batch update counts.
- Triggers.
- DDL and migration behavior.

If the application relies on PostgreSQL-, MySQL-, or SQL Server-specific behavior, add integration tests running on the real engine, typically via Testcontainers or a dedicated test database.

Example configuration to keep the configured test datasource instead of replacing it:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlAuditIntegrationTest {
    // Tests use the PostgreSQL datasource configured for testing.
}
~~~

Testing on a real database is especially important when verifying direct SQL, batch updates, triggers, generated keys, or locking.

## 15. Testing Callback Order and Event Timing

When multiple callbacks process the same aggregate, use `@Order` or `Ordered` to define order.

Example:

~~~java
@Component
@Order(100)
class NormalizeCallback implements BeforeConvertCallback<AuditOrder> {

    @Override
    public AuditOrder onBeforeConvert(AuditOrder order) {
        order.normalizeStatus();
        return order;
    }
}
~~~

~~~java
@Component
@Order(200)
class ValidateCallback implements BeforeConvertCallback<AuditOrder> {

    @Override
    public AuditOrder onBeforeConvert(AuditOrder order) {
        order.validate();
        return order;
    }
}
~~~

Tests can record invocation order in a list or probe bean, then assert:

~~~text
normalize -> validate -> convert -> before-save -> SQL -> after-save
~~~

This reflects the general ordering of pipeline hooks, not a guarantee that every asynchronous event listener completes in that exact order.

If using event listeners with a `TaskExecutor`, do not assert order using an unsynchronized shared list. Events may run on other threads.

## 16. Common Testing Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Asserting only the object after save | Does not prove data persisted | Reload from database |
| Test slice omits `@Import` for callback config | Callbacks are never registered | Use `@Import` |
| Relying on system clock | Tests depend on execution timestamp | Fix `DateTimeProvider` |
| Not controlling actor | Tests receive `NULL` or environment actor | Supply test `AuditorAware` |
| Expecting callbacks on `@Modifying` | Tests assume wrong lifecycle | Test direct query behavior separately |
| Expecting callbacks on `JdbcTemplate` | Direct SQL skips entity lifecycle | Update metadata in SQL or use repositories |
| Testing callbacks per child entity | Callbacks bind to the aggregate root | Test via the root |
| Using `ApplicationEvent` instead of synchronous callbacks | Events can be async and unordered | Use `EntityCallback` for lifecycle mutations |
| Using H2 only for database-specific SQL | Misses dialect/driver differences | Add integration tests with target database |
| Testing rollback inside an unfinished transaction | Reads do not reflect post-rollback state | Finish transaction then read in a new transaction |
| Not testing background actors | Jobs lack identity metadata | Test service actors and async contexts |

## 17. Recommended Test Matrix

| Write Path | Callbacks | Auditing | SQL | Transaction |
|---|---|---|---|---|
| `repository.save` | Yes | Yes if enabled | Framework-generated | Per Spring transaction |
| `JdbcAggregateTemplate.insert/update` | Yes | Yes if enabled | Framework-generated | Per Spring transaction |
| `repository.saveAll` | Yes per aggregate root | Yes if enabled | Framework batch-aware | Per Spring transaction |
| `@Modifying @Query` | Save/delete callbacks skipped | Not auto-updated | Declared SQL | Per repository/caller transaction |
| Derived modifying query | Save/delete callbacks skipped | Not auto-updated | Framework-generated SQL | Per repository/caller transaction |
| `JdbcTemplate.update` | No | No | Direct SQL | If sharing datasource/manager |
| `NamedParameterJdbcTemplate.batchUpdate` | No | No | Direct JDBC batch | If sharing datasource/manager |
| `JdbcClient.update` | No | No | Direct SQL | If sharing datasource/manager |

This matrix helps identify which tests are needed for each write path present in the application.

## 18. Workflow for Writing Callback, Auditing, and Direct SQL Tests

**Step 1 — Pick a representative aggregate.** Use an aggregate that has the metadata and callbacks under test.

**Step 2 — Configure the test slice.** Use `@DataJdbcTest` and explicitly import auditing/callback configurations.

**Step 3 — Fix actor and clock.** Create controllable `AuditorAware` and `DateTimeProvider` beans.

**Step 4 — Test callbacks.** Use a callback probe to verify the right callbacks run in the right order.

**Step 5 — Test auditing.** Save new, change actor/time, save again, then reload from database to confirm created fields stay unchanged and modified fields update.

**Step 6 — Test direct queries.** Call `@Modifying` or `JdbcTemplate` and confirm callbacks/auditing do not run automatically.

**Step 7 — Test explicit SQL metadata updates.** If direct SQL is designed to write audit fields/versions, verify those columns update properly.

**Step 8 — Test rollback.** Fail a later step and confirm all operations in the transaction roll back.

**Step 9 — Test on a real database.** Run supplementary tests against the production dialect/driver when custom SQL is involved.

~~~text
@DataJdbcTest + imported test configuration
                  |
                  v
       Fixed AuditorAware + DateTimeProvider
                  |
                  v
             repository.save
                  |
                  +---- callback probe
                  |
                  +---- auditing columns
                  |
                  v
             Read back from DB
                  |
                  v
        Direct @Modifying / JDBC SQL
                  |
                  +---- assert no lifecycle callback
                  +---- assert no automatic auditing
                  |
                  v
         Test explicit metadata update
                  |
                  v
        Test transaction rollback
                  |
                  v
       Repeat on production database
~~~

## 19. Self-Reflection Exercises

**Scenario A — Callback did not run**

A test invokes `@Modifying @Query` to update status. `AfterSaveCallback` was not called. Is this a framework bug?

**Hint:** No. Derived/annotated query methods do not pass through the aggregate save lifecycle, so save/delete callbacks and corresponding events are not invoked.

**Scenario B — `createdBy` is always `NULL`**

Repository save succeeds, yet `createdBy` has no value. What should be checked?

**Hint:** Check `@EnableJdbcAuditing`, the generic type of `AuditorAware`, whether the bean is imported into the test context, and whether the provider returns an actor.

**Scenario C — `modifiedAt` did not change in test**

Two saves happened at the same instant under a fixed clock. Can we conclude auditing is broken?

**Hint:** No. Use a controllable `DateTimeProvider` and explicitly advance the timestamp between saves.

**Scenario D — Direct SQL updated status**

`JdbcTemplate.update` changed status successfully, yet `modifiedBy` kept its old value. Why?

**Hint:** Direct SQL does not invoke auditing callbacks. Update metadata in SQL or route the mutation through a repository/template.

**Scenario E — Slow event listener**

An `AfterSaveEvent` listener runs on a separate executor. The test checks a list immediately after `repository.save`, yet the event is not in the list yet. Why?

**Hint:** Events can be handled asynchronously. If synchronous entity mutation is required, use a callback; when testing async events, synchronize waiting explicitly using test primitives.

**Scenario F — H2 test passes, PostgreSQL fails**

A direct SQL update works in H2 yet fails on PostgreSQL. What needs to be added?

**Hint:** Integration tests on real PostgreSQL or Testcontainers to verify dialect, types, locking, and driver behavior.

## 20. Key Takeaways

| Component | Role |
|---|---|
| `BeforeConvertCallback` | Modify entity before generating database changes |
| `BeforeSaveCallback` | Intervene after `AggregateChange` is created |
| `AfterSaveCallback` | Process after the aggregate is saved |
| `AfterConvertCallback` | Process after the aggregate is materialized |
| `BeforeDeleteCallback` / `AfterDeleteCallback` | Hooks before/after deleting aggregate |
| Lifecycle events | Notify about persistence phases |
| `@EnableJdbcAuditing` | Enable auditing for Spring Data JDBC |
| `AuditorAware` | Supply actor for metadata |
| `DateTimeProvider` | Supply controllable timestamps |
| `@DataJdbcTest` | Test slice for Spring Data JDBC |
| `@Import` | Bring callback/auditing test configuration into context |
| `@Modifying` | Direct SQL write via repository; skips save/delete callbacks |
| `JdbcTemplate` / `JdbcClient` | Direct SQL; bypasses aggregate lifecycle |
| Integration test on real DB | Verifies dialect, driver, transactions, and real SQL |

**To properly test callbacks and auditing, verify both the lifecycle execution and the data persisted in the database.** Repository/template saves run through callbacks and auditing; derived/annotated modifying queries and direct JDBC bypass the save/delete lifecycle. Use fixed actors and clocks for deterministic tests, test direct SQL as a distinct write path, and confirm transaction rollbacks on an appropriate datasource and driver.

## References

- [Spring Data Relational — Lifecycle Events and EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): callback pipeline, lifecycle events, aggregate root scope, and limits of derived/annotated query methods.
- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): `@EnableJdbcAuditing`, actor providers, and auditing metadata.
- [Spring Data Relational — BeforeConvertCallback Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html): callback timing and signature.
- [Spring Data Relational — BeforeSaveCallback Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html): `AggregateChange` already created before callback runs.
- [Spring Data Commons — Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): registration, ordering, and synchronous callback semantics.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataJdbcTest`, auto-configuration, and default transaction rollback.
