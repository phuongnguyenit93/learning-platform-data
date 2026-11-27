# ORM, Transaction Boundaries, and Inspecting Actual SQL in PostgreSQL

## 1. Why Valid Java Code Does Not Guarantee Correct PostgreSQL Access

A Java service method may be just a few lines:

```java
@Transactional
public OrderDto placeOrder(CreateOrderCommand command) {
    Customer customer = customerRepository.findById(command.customerId())
        .orElseThrow();
    Order order = new Order(customer);
    orderRepository.save(order);
    return OrderDto.from(order);
}
```

Yet to evaluate correctness, you must know many things invisible in that method body:

- Does `findById` actually issue a `SELECT`, or read from the persistence context/cache?
- Does `save` send `INSERT` immediately or wait until `flush`?
- Does having `order.id` in Java mean the row has committed?
- Does `OrderDto.from(order)` touch a `LAZY` association and fire extra queries?
- Was `@Transactional` actually applied to this call through a Spring proxy?
- What isolation level is the connection running under?
- Does an `UPDATE` protect against *lost updates*?
- If an exception occurs after the `INSERT`, does the row roll back?
- If the system also sends an email, can that email roll back with the database?
- In PostgreSQL logs, do the actual SQL, bind types/values, and lock waits match the author's assumptions?

**ORM (Object–Relational Mapping) maps objects to relational data; it does not eliminate SQL, transaction boundaries, or PostgreSQL concurrency rules.**

This lesson builds a three-layer mental model:

```text
LAYER 1: Java / ORM
  Entity, repository, persistence context, lazy loading
             |
             v
LAYER 2: JDBC / transaction manager / connection pool
  PreparedStatement, bind parameters, commit, rollback
             |
             v
LAYER 3: PostgreSQL
  Actual SQL, locks, MVCC, constraints, WAL, query plans
```

A reliable application must understand **all three layers** and verify how they cross boundaries.

### Learning Objectives

After this lesson, you can:

1. Distinguish between ORM, JPA, Hibernate, Spring Data JPA, JDBC, and PostgreSQL.
2. Explain entity states, persistence context, dirty checking, and flushing.
3. Distinguish `save`, `flush`, `commit`, and when rows become visible to other transactions.
4. Identify transaction boundaries by service method and transaction manager rather than individual repository calls.
5. Spot cases where `@Transactional` silently fails due to proxies or self-invocation.
6. Understand `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and their practical trade-offs.
7. Apply PostgreSQL isolation levels, row locks, and optimistic locking for concurrent writers.
8. Design bounded retries for serialization failures and deadlocks.
9. Separate database transactions from cross-system workflows using the outbox pattern where appropriate.
10. Inspect actual SQL using Hibernate/JDBC logs, PostgreSQL logs, `pg_stat_activity`, `pg_stat_statements`, and `EXPLAIN`.
11. Diagnose N+1 queries, cartesian explosions from fetch joins, pagination issues, batching, and slow queries.
12. Choose among ORM, direct SQL, JDBC, native queries, or jOOQ based on complexity and domain needs.
13. Control connection pools, timeouts, idle-in-transaction sessions, and lock retention incidents.
14. Verify migrations, constraints, defaults, timezones, `jsonb`, and data type mappings.
15. Reason through an order workflow with concurrency and safe boundaries.

---

## 2. What ORM Is and What It Is Not

ORM bridges between:

| In Java | In PostgreSQL |
|---|---|
| Class `Customer` | Table `customers` |
| Field `id` | Column `customer_id` |
| `@ManyToOne` | Foreign key / reference |
| Object identity | Primary key and persistence context semantics |
| `BigDecimal` | `numeric` |
| `Instant` / `OffsetDateTime` | Commonly `timestamptz` depending on mapping |
| `LocalDate` | `date` |
| Entity lifecycle | SQL `SELECT`/`INSERT`/`UPDATE`/`DELETE` emitted as needed |
| Query method | Generated SQL query or framework retrieval plan |

ORM **does not**:

- Make every query fast.
- Prevent SQL injection if a developer concatenates strings into native SQL.
- Automatically turn multiple databases into a single ACID transaction.
- Guarantee every association loads in a single query.
- Replace PostgreSQL `CHECK`, `UNIQUE`, or foreign key constraints.
- Prevent race conditions without proper locking or versioning protocols.
- Verify query plans, indexes, or selectivity on production data distributions.
- Ensure local caches immediately reflect mutations committed by other processes.

### 2.1. JPA and Hibernate

- **Jakarta Persistence (JPA)**: Java persistence API specification and programming model.
- **Hibernate ORM**: a widely used JPA implementation with additional provider-specific features.
- **Spring Data JPA**: repository abstraction layered over JPA/Hibernate or another provider.
- **JDBC**: driver-level API for sending SQL and managing transactions/`ResultSet`s.
- **PostgreSQL JDBC Driver (pgjdbc)**: JDBC driver communicating with PostgreSQL.

For example, `JpaRepository.save` is a repository-layer API; the actual SQL emitted depends on entity state, Hibernate mappings, flush mode, ID generator strategy, and active transactions.

### 2.2. ORM and Direct SQL Can Coexist

You never have to choose between “100% ORM” and “100% raw SQL.”

One system can combine:

- ORM for straightforward CRUD and aggregate management.
- JPQL/Criteria for appropriate dynamic queries.
- Native SQL for `INSERT ... ON CONFLICT ... RETURNING`, `SKIP LOCKED`, or PostgreSQL-specific features.
- `JdbcTemplate`/JDBC for bulk batching and reporting.
- SQL migrations for schemas, indexes, and constraints.
- Outboxes + workers for reliable integration events.

Choose tools for **correctness, maintainability, and measured behavior**, not to avoid writing SQL at all costs.

## 3. A Single PostgreSQL Lab for the Entire Lesson

Use only in a practice database. Tables and IDs below are synthetic fixture data.

```sql
CREATE SCHEMA IF NOT EXISTS orm406;

CREATE TABLE orm406.customers (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orm406.products (
    product_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_code text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_on_hand integer NOT NULL CHECK (stock_on_hand >= 0),
    version bigint NOT NULL DEFAULT 0
);

CREATE TABLE orm406.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES orm406.customers(customer_id),
    external_request_id text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount numeric(14, 2) NOT NULL DEFAULT 0
        CHECK (total_amount >= 0),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orm406.order_items (
    order_item_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES orm406.orders(order_id) ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES orm406.products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    UNIQUE (order_id, product_id)
);

CREATE TABLE orm406.outbox_events (
    event_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
```

Sample data:

```sql
INSERT INTO orm406.customers(customer_id, full_name, email)
VALUES
    (1, 'An', 'an@example.invalid'),
    (2, 'Bình', 'binh@example.invalid');

INSERT INTO orm406.products(
    product_id, product_code, product_name,
    unit_price, stock_on_hand
)
VALUES
    (10, 'BOOK-001', 'SQL Book', 150000, 5),
    (11, 'KEY-002', 'Keyboard', 650000, 3),
    (12, 'MOU-003', 'Mouse', 200000, 0);
```

Because the fixture inserts explicit IDs into `GENERATED BY DEFAULT` identity columns, the underlying sequences have not necessarily advanced past them. To keep auto-generating IDs safely in the lab:

```sql
SELECT setval(
    pg_get_serial_sequence('orm406.customers', 'customer_id'),
    (SELECT max(customer_id) FROM orm406.customers),
    true
);

SELECT setval(
    pg_get_serial_sequence('orm406.products', 'product_id'),
    (SELECT max(product_id) FROM orm406.products),
    true
);
```

**Remember:** `setval` is a sequence operation that does not roll back under transaction semantics like row DML. This is fixture setup, not a production migration pattern.

### 3.1. Why Enforce Constraints in the Database?

ORM validation helps UIs and APIs, yet data can arrive via SQL scripts, ETL jobs, another service, pgAdmin, or migrations. PostgreSQL must enforce baseline invariants:

- Prices and totals cannot be negative.
- Order item quantities must be positive.
- Stock on hand cannot go negative.
- `email`, `product_code`, and `external_request_id` cannot duplicate.
- Orders reference only valid customers.

Applications should still surface friendly validation errors, but never strip database constraints relying purely on Java checks.

## 4. Minimal Entity Mapping in JPA

An illustrative Java mapping (imports omitted for brevity):

```java
@Entity
@Table(name = "products", schema = "orm406")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "product_id")
    private Long id;

    @Column(name = "product_code", nullable = false, unique = true)
    private String code;

    @Column(name = "product_name", nullable = false)
    private String name;

    @Column(name = "unit_price", precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "stock_on_hand", nullable = false)
    private Integer stockOnHand;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Product() { }
    // getters, methods enforcing invariants
}
```

### 4.1. Java Annotations Do Not Automatically Change Production DDL

`@Column(nullable = false)` describes the ORM mapping and only participates in DDL generation if auto-DDL is enabled. In production, manage schemas via reviewed migrations and verify constraints and indexes directly in the database.

### 4.2. What Problem Does `@Version` Solve?

`@Version` enables **optimistic locking** in Hibernate/JPA when updating managed entities:

```sql
-- Conceptual SQL illustration, not fixed verbatim
-- across all Hibernate versions:
UPDATE orm406.products
SET stock_on_hand = ?, version = ?
WHERE product_id = ?
  AND version = ?;
```

If the prior version no longer matches, the affected row count is 0 and the provider throws an optimistic locking failure.

**Limitation:** direct SQL updates bypassing the version protocol can still break expectations. Bulk JPQL `UPDATE` statements also do not follow managed-entity dirty checking; explicitly match and increment `version` or use an appropriate concurrency protocol.

### 4.3. `BigDecimal` for Money

`numeric(12,2)` pairs with `BigDecimal` rather than `double` when exact decimal precision is needed. You still must agree on:

- Currency and monetary unit.
- Rounding mode.
- Precision and scale.
- Tax and discount calculation rules.
- Overflow handling and reconciliation.

Never mistake using the right Java type for implementing complete financial rules.

## 5. Entity States and the Persistence Context

In JPA, an entity transitions among key states:

| State | Meaning |
|---|---|
| New / transient | Plain Java object not yet managed by a persistence context |
| Managed / persistent | Tracked by an `EntityManager` within a persistence context |
| Detached | Previously managed, no longer attached to any active context |
| Removed | Marked for deletion inside the context |

Lifecycle flow:

```text
new Product(...)
      |
      | persist()
      v
Managed entity <---- find() / query
      |
      | mutate field
      v
Dirty managed entity
      |
      | flush()
      v
SQL UPDATE/INSERT/DELETE sent to PostgreSQL
      |
      | commit()
      v
Transaction commits or rolls back depending on outcome
```

### 5.1. Managed Entities Do Not Need `save()` After Every Change

Inside a transaction:

```java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.rename(newName);
    // Calling entityManager.persist(product) again is usually unnecessary.
}
```

While the entity remains managed, Hibernate dirty checking detects mutated fields and emits SQL at flush time.

### 5.2. Detached Entities Are Not Tracked Automatically

An object loaded in a closed transaction becomes detached. Mutating its fields does not automatically trigger a DB `UPDATE`.

Calling `merge` or repository save on old objects requires understanding state copying and optimistic locking—never “save” a stale detached object assuming lost updates cannot occur.

### 5.3. Identity Inside the Persistence Context

Within one persistence context, JPA/Hibernate maintains one managed instance per database identity per provider rules. However, this cache is **scoped to the active context**, not a cluster-wide guarantee that no other transaction modified the row in the database.

## 6. `save()` Does Not Always Mean Immediate `INSERT`

Consider:

```java
@Transactional
public Long createOrder(Order order) {
    orderRepository.save(order);
    return order.getId();
}
```

Actual SQL timing depends on:

- Whether the entity is new or detached.
- Whether `persist` or `merge` is invoked.
- ID generator strategy (`IDENTITY`, `SEQUENCE`, `TABLE`, or assigned).
- Flush mode.
- Provider and version.
- Other operations in the same transaction.

### 6.1. `IDENTITY` May Require Early `INSERT`

When IDs come from a PostgreSQL identity column during `INSERT`, Hibernate typically executes `INSERT` early to obtain the generated ID. Even after `order.getId()` is populated, the transaction **still has not committed**.

### 6.2. `SEQUENCE` Can Allocate IDs Before `INSERT`

With a sequence:

```sql
SELECT nextval('some_sequence');
```

an ID can be allocated before any `INSERT` hits the table. Sequences have non-transactional semantics, so rolled-back inserts leave ID gaps.

### 6.3. Never Use an Assigned ID as Proof of Transaction Commit

An order holding `id = 123` in Java can still:

- Sit inside an uncommitted transaction.
- Be rolled back later.
- Trigger a constraint violation on another statement.
- Not even be flushed yet under certain mappings.

Only successful transaction commit and proper error handling confirm durable persistence.

## 7. `flush`, `commit`, and `rollback`: Three Distinct Concepts

| Action | Interpretation |
|---|---|
| `persist` / `save` | Registers entity persistence intent via the API |
| `flush` | Synchronizes persistence context changes as SQL inside the transaction |
| `commit` | Finalizes the transaction durably in PostgreSQL |
| `rollback` | Discards uncommitted transactional changes (aside from non-transactional effects like sequences) |
| `clear` | Detaches managed entities from the context; does not undo already-sent SQL |
| `refresh` | Reloads entity state from the DB per context/provider rules |

### 7.1. Illustrative Timeline

```text
Java method starts
   |
   +-- load Product (SELECT)
   +-- mutate name on managed entity
   +-- save(Order) / persist
   |
   +-- flush
   |     +-- INSERT/UPDATE sent to PostgreSQL
   |     +-- constraints may raise errors here or later
   |
   +-- further application code runs
   |
   +-- commit transaction
          |
          +-- success: data committed
          +-- failure: transaction unsuccessful
```

### 7.2. Flushing Does Not Make Rows Visible to Other Connections

Under standard PostgreSQL MVCC isolation, concurrent transactions cannot read uncommitted rows just because Hibernate flushed them.

### 7.3. Flushing Can Happen Before You Call `flush()`

Hibernate may auto-flush before executing queries to preserve consistency under its flush mode. Never assume SQL only leaves the app at the very end of `@Transactional`.

### 7.4. Commit Can Trigger Flush

When the transaction manager commits, the provider flushes pending changes. Do not forget that flush/constraint errors can surface at the commit boundary after your service method body already returned.

### 7.5. Rollback Cannot Unsend an Email

If a service flushes an `INSERT`, calls an external email API, and then the database transaction rolls back, the sent email does not roll back with PostgreSQL.

That spans a **cross-system transaction boundary** requiring an outbox or compensating workflow.

## 8. Where Is the `@Transactional` Boundary?

In Spring, the standard pattern places `@Transactional` at the **application/service layer**, encompassing a full use case needing atomicity:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final ProductRepository products;

    public OrderService(OrderRepository orders,
                        ProductRepository products) {
        this.orders = orders;
        this.products = products;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Product product = products.findById(command.productId())
            .orElseThrow();
        Order order = new Order(...);
        orders.save(order);
        return order.getId();
    }
}
```

**Intended semantics:** all DB operations of the use case share a transaction managed by the transaction manager over one bound connection/resource per configuration.

### 8.1. Not Every Repository Call Is a Separate Transaction

When a Spring transaction is active and repositories share the same transaction manager/resource, multiple repository calls participate in that single transaction.

### 8.2. Transaction Boundaries Do Not Come From Method Names

Without an active transaction, JDBC operations may run in autocommit or per-call mini-transactions depending on setup, breaking invariants when you assumed “create order + create items is atomic.”

### 8.3. A Boundary Can Span Multiple Layers

```text
Controller
    |
    v
OrderService.createOrder() [@Transactional proxy]
    |
    +--> CustomerRepository
    +--> ProductRepository
    +--> OrderRepository
    +--> OutboxRepository
    |
    v
commit / rollback
```

One unit of work can span multiple repositories. However, external HTTP calls do not join a PostgreSQL ACID transaction merely by sitting inside the same Java method.

## 9. Spring Proxies and Self-Invocation: A Common Silent Bug

Look closely:

```java
@Service
public class InvoiceService {
    public void submit() {
        saveWithinTransaction();
    }

    @Transactional
    public void saveWithinTransaction() {
        // database writes
    }
}
```

When `submit()` directly calls `this.saveWithinTransaction()` on the same object, standard Spring proxy-based transaction management **bypasses the proxy**. The `@Transactional` interceptor never runs as expected.

### 9.1. How to Fix It

- Place `@Transactional` on the public service entry method invoked through the proxy.
- Move the transactional unit into a separate Spring bean and call it via dependency injection.
- Or use `TransactionTemplate` for explicit programmatic transaction boundaries.

Example:

```java
@Service
public class InvoiceService {
    private final InvoiceWriter writer;

    public InvoiceService(InvoiceWriter writer) {
        this.writer = writer;
    }

    public void submit() {
        writer.saveWithinTransaction();
    }
}

@Service
public class InvoiceWriter {
    @Transactional
    public void saveWithinTransaction() {
        // transactional database writes
    }
}
```

### 9.2. Additional Cases to Check

- `private`/`final` methods or `final` classes depending on proxy type and framework config.
- Objects instantiated with `new` rather than managed by Spring.
- Calls from constructors or lifecycle hooks bypassing proxies.
- Work spawned onto another thread not inheriting transaction context automatically.
- `@Scheduled` or `@Async` boundaries starting fresh execution contexts.
- Binding the wrong transaction manager when multiple `DataSource`s exist.

**Verify real database transactions**, rather than trusting annotations visually.

## 10. What Are `@Transactional` Defaults?

Common Spring defaults (verify against your exact configuration and version):

| Attribute | Typical Default |
|---|---|
| `propagation` | `REQUIRED` |
| `isolation` | `DEFAULT`: follows datasource/database default |
| `readOnly` | `false` |
| `timeout` | Follows transaction manager / none explicitly set |
| Rollback | Rolls back by default on `RuntimeException` and `Error` |
| Checked exceptions | Does not roll back by default solely for being checked |

### 10.1. Do Not Assume Isolation Is Uniform Across Databases

PostgreSQL defaults to `READ COMMITTED`, yet `@Transactional(isolation = DEFAULT)` simply defers to the connection/database setting rather than Spring guaranteeing `READ COMMITTED` in every environment.

### 10.2. Checked Exceptions

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // DB writes ...
    // may throw IOException
}
```

Specify `rollbackFor` when business rules demand rollback on checked exceptions. Never assume all exceptions trigger rollback identically.

### 10.3. Catching an Exception Can Prevent Rollback

```java
@Transactional
public void process() {
    try {
        doDatabaseWrite();
        callSomethingThatFails();
    } catch (SomeBusinessException e) {
        log.warn("Handled", e);
        // method returns normally
    }
}
```

If an exception is caught without marking rollback-only, the transaction manager may commit prior changes depending on the error and resource state. Note that in PostgreSQL, an SQL error puts the DB transaction into an aborted state where normal SQL cannot proceed without rolling back.

**Decide intentionally:** which failures must roll back, which count as handled outcomes, and what state the database was left in.

## 11. Rollback-Only and `UnexpectedRollbackException`

An inner method joining a `REQUIRED` transaction may mark it rollback-only. An outer method catching that exception and returning normally hits an unpleasant surprise:

```text
Outer @Transactional
   |
   +-- Inner REQUIRED joins same transaction
   |       |
   |       +-- fails, marks rollback-only
   |
   +-- Outer catches error
   +-- Outer returns normally
   |
   v
Commit attempt
   |
   v
UnexpectedRollbackException / rollback
```

Never “swallow the error and return HTTP 200” once a shared transaction was marked rollback-only.

### 11.1. Inspecting Transaction State While Debugging

In Spring, you can observe:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

These indicate Spring-layer state; they do not replace checking the actual PostgreSQL connection/backend and commit outcome when diagnosing transaction manager behavior.

## 12. Transaction Propagation: `REQUIRED` and `REQUIRES_NEW`

### 12.1. `REQUIRED`

If an appropriate transaction is active, the inner method **joins the existing transaction**. Otherwise, a new transaction begins.

```java
@Transactional(propagation = Propagation.REQUIRED)
public void adjustStock() {
    // joins caller transaction if present
}
```

### 12.2. `REQUIRES_NEW`

The inner method opens an **independent transaction** while suspending the outer transaction per transaction manager rules.

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void persistAttemptLog() {
    // commits/rollbacks independently of outer transaction
}
```

**Warning:** while the outer transaction holds one connection, the inner transaction requires a second connection. If many threads hold outer connections simultaneously while waiting on the pool for inner connections, pool exhaustion or pool deadlocks can occur.

### 12.3. `REQUIRES_NEW` Does Not Solve “Atomic Order + Audit”

If business rules require the audit record to roll back whenever the order fails, writing the audit via `REQUIRES_NEW` is **wrong**: the audit can commit even if the order rolls back.

Only use `REQUIRES_NEW` when business requirements explicitly call for an independent transaction and accept that split-outcome behavior.

### 12.4. Do Not Expect New Propagation via Self-Invocation

Calling `this.inner()` on a method marked `@Transactional(REQUIRES_NEW)` inside the same class typically skips the proxy, so no new transaction is created.

## 13. `NESTED` and Savepoints: Not Equivalent to `REQUIRES_NEW`

`Propagation.NESTED` typically uses a database **savepoint** inside the existing transaction where supported by the transaction manager and driver.

Model:

```text
BEGIN outer transaction
   |
   +-- insert order
   |
   +-- SAVEPOINT before optional step
   |      +-- insert optional data
   |      +-- error
   |      +-- ROLLBACK TO SAVEPOINT
   |
   +-- continue outer transaction
   |
COMMIT outer transaction
```

Unlike `REQUIRES_NEW`:

- A `NESTED` savepoint does not commit independently.
- If the outer transaction rolls back, work kept past the savepoint also rolls back.
- Support depends on the transaction manager; do not assume `JpaTransactionManager` supports `NESTED` semantics across arbitrary JPA operations.

### 13.1. Illustrative SQL

```sql
BEGIN;

INSERT INTO orm406.orders(
    customer_id, external_request_id, total_amount
)
VALUES (1, 'LAB-NESTED-001', 0);

SAVEPOINT item_step;

-- Operation that may fail:
INSERT INTO orm406.order_items(
    order_id, product_id, quantity, unit_price
)
VALUES (999999, 10, 1, 150000);

-- If INSERT raises an FK violation:
ROLLBACK TO SAVEPOINT item_step;

COMMIT;
```

This is a **step-by-step lab**: run `ROLLBACK TO SAVEPOINT` only if the savepoint exists and the preceding error occurred; do not run it as an unconditional script expecting every statement to pass.

### 13.2. When a JPA Persistence Context Exists

Rolling back to a database savepoint does not automatically revert dirty Java entity fields inside an ORM persistence context. Mixing savepoints with JPA entities requires explicit `refresh`/`clear` strategies and verified provider/transaction manager support.

## 14. Does `@Transactional(readOnly = true)` Strictly Block DML?

In Spring, `readOnly = true` is primarily a **hint/optimization intent** passed to the transaction manager and ORM. Depending on config, it may disable automatic dirty-checking flushes, set the JDBC connection read-only flag, or influence transaction SQL.

Never treat it as an **authorization enforcement layer**:

```java
@Transactional(readOnly = true)
public ProductDto getProduct(Long id) {
    // Intended read-only
}
```

### 14.1. Verify What Is Actually Enforced

- Does the ORM skip flushing mutated entities?
- Is the JDBC connection flagged read-only?
- Is the PostgreSQL transaction actually `READ ONLY`?
- Can native SQL still perform writes?
- Does the DB role hold `INSERT`/`UPDATE`/`DELETE` privileges?

### 14.2. PostgreSQL Read-Only Transactions

To verify explicitly in SQL:

```sql
BEGIN READ ONLY;

SELECT count(*)
FROM orm406.products;

COMMIT;
```

Or inside an active transaction:

```sql
SHOW transaction_read_only;
```

A PostgreSQL `READ ONLY` transaction restricts writes per server semantics, yet it still does not substitute for proper `GRANT`/`REVOKE` SQL permissions across roles.

### 14.3. Do Not Rely on `readOnly` Instead of Consistency Design

Read-only queries still need consistent snapshots, bounded latency, proper indexes, and strict tenant isolation.

## 15. Connection Pools and Auto-Commit

Java apps typically borrow connections from HikariCP or an equivalent pool.

Each connection carries session state:

```text
autocommit
transaction isolation
read-only flag
search_path
role / session variables
timezone
statement_timeout
prepared statements
temporary tables
locks and transaction state
```

### 15.1. JDBC Auto-Commit

In raw JDBC, new connections typically default to `autoCommit = true` unless changed by a pool or framework.

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        // execute SQL statements on c
        c.commit();
    } catch (SQLException ex) {
        c.rollback();
        throw ex;
    }
}
```

A transaction manager such as Spring owns the lifecycle of its managed connections. Never call `commit()` manually on a connection controlled by a Spring transaction without understanding the consequences.

### 15.2. Pools Must Return Sessions in a Clean State

If one request runs:

```sql
SET search_path = tenant_a;
```

and returns the connection to the pool without resetting session state per policy, the next request inherits unintended session state.

The same applies to `SET ROLE`, timeouts, temporary tables, and custom GUCs.

### 15.3. Prefer `SET LOCAL` for Transaction-Scoped Settings

Inside a transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

-- Queries ...

COMMIT;
```

`SET LOCAL` limits changes to the current transaction, reducing state leakage across pooled requests. You still must manage transaction ownership, connection reuse, and other session-mutating statements carefully.

### 15.4. Tenant Context Alone Is Not Authentication

An RLS policy checking `current_setting('app.tenant_id')` works well in a properly designed architecture, yet if untrusted clients or roles can execute arbitrary `SET app.tenant_id`, that variable alone does not enforce authorization.

## 16. What Is the Cost of a Long Transaction?

Bad pattern:

```java
@Transactional
public void checkout(OrderCommand command) {
    loadAndUpdateDatabase();
    callPaymentGatewayOverHttp();
    waitForUserConfirmation();
    sendEmail();
    updateDatabaseAgain();
}
```

Holding a DB transaction open while waiting on network I/O or user input can:

- Pin a pooled connection.
- Hold row locks until commit/rollback.
- Amplify lock contention.
- Pin old snapshots, blocking vacuum and dead-tuple cleanup.
- Increase deadlock, timeout, and serialization failure rates.
- Cause pool exhaustion under load spikes.

### 16.1. Keep Boundaries Tight Around Database Invariants

Split the workflow:

```text
Transaction 1: create order + reservation/outbox
       |
       v
Commit
       |
       v
Call external service / async worker
       |
       v
Transaction 2: update status based on result
```

Now the system relies on an explicit state machine, idempotency, and failure compensation instead of trying to stretch one ACID transaction across an external payment gateway.

### 16.2. Do Not Split Transactions If It Breaks Atomicity

If a use case requires deducting inventory **and** creating the order to succeed or fail together, both DB writes belong in one proper transaction. Keeping transactions short never means breaking genuine atomic invariants apart.

## 17. PostgreSQL `READ COMMITTED` and Statement-Level Snapshots

PostgreSQL defaults to `READ COMMITTED`.

At this level, every SQL statement observes committed data as of a fresh snapshot taken when that statement starts. Two `SELECT`s inside the same transaction can see different values if another transaction commits in between.

Mental model:

```text
T1: BEGIN READ COMMITTED
T1: SELECT stock_on_hand FROM products WHERE id=10 -> 5

T2: BEGIN
T2: UPDATE products SET stock_on_hand=3 WHERE id=10
T2: COMMIT

T1: SELECT stock_on_hand FROM products WHERE id=10 -> 3
T1: COMMIT
```

### 17.1. Beware the ORM First-Level Cache

If T1 calls `entityManager.find(Product.class, 10)` twice inside the same persistence context, the second call can return **the same cached managed entity with the stale value**, issuing no second `SELECT`.

Thus raw PostgreSQL `SELECT` behavior differs from:

```java
Product p1 = entityManager.find(Product.class, 10L);
Product p2 = entityManager.find(Product.class, 10L);
```

SQL queries may see `3`, while an unrefreshed managed entity still holds `5`.

### 17.2. `@Transactional` Alone Does Not Give Repeatable Snapshots

A `READ COMMITTED` transaction offers no cross-statement repeatable snapshot guarantee. When business logic requires a consistent multi-read snapshot, select an appropriate isolation level and retry protocol.

## 18. `REPEATABLE READ` and `SERIALIZABLE`

PostgreSQL implements standard isolation levels, treating `READ UNCOMMITTED` effectively like `READ COMMITTED` rather than allowing dirty reads as some SQL dialects do.

| Isolation | Key Property | Boundary |
|---|---|---|
| `READ COMMITTED` | Statement-level snapshot | Non-repeatable reads can occur |
| `REPEATABLE READ` | Stable transaction snapshot per PostgreSQL rules | Concurrent update conflicts require retry; does not catch every serialization anomaly |
| `SERIALIZABLE` | Verifies concurrent transactions remain equivalent to some serial order | Can abort with `40001`; must retry the entire unit |
| `READ UNCOMMITTED` | Enforces `READ COMMITTED` semantics in PostgreSQL | Does not allow dirty reads |

### 18.1. `REPEATABLE READ` Demo

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT stock_on_hand
FROM orm406.products
WHERE product_id = 10;

-- Suppose another transaction commits an UPDATE here.

SELECT stock_on_hand
FROM orm406.products
WHERE product_id = 10;

COMMIT;
```

With the transaction snapshot pinned and no local modifications, both `SELECT`s observe the same row version from that snapshot.

### 18.2. `SERIALIZABLE` Does Not Mean Never Needing Retries

PostgreSQL tracks predicate conflicts and serialization anomalies; a transaction can fail with:

```text
SQLSTATE 40001: serialization_failure
```

The application must retry **the entire transaction logic** at a proper outer boundary—never retry a single statement inside an aborted transaction.

### 18.3. Retries Do Not Replace Idempotency or Side-Effect Isolation

A retried transaction executes its body multiple times. Any external side effects must be idempotent or moved outside via an outbox; otherwise emails or payment calls will repeat.

## 19. Lost Updates: Read–Modify–Write Is a Race Condition

Suppose stock = 5.

Two requests read stock and mutate Java objects concurrently:

```text
T1 reads stock=5
T2 reads stock=5

T1 writes stock=4
T2 writes stock=4

Final value: 4
Yet two 1-item purchases succeeded;
expected value: 3
```

Without proper locking, versioning, or atomic SQL predicates, one update silently overwrites the other.

### 19.1. `@Transactional` Alone Is Not Enough

Having both T1 and T2 wrapped in transactions does not protect against lost updates under default isolation and plain read-then-set logic.

### 19.2. Using `@Version`

Managed entities with `@Version` detect stale concurrent overwrites. The second transaction triggers an optimistic locking failure when its `WHERE version = ?` matches zero rows.

### 19.3. Audit Every `UPDATE` Path

If a background job executes:

```sql
UPDATE orm406.products
SET stock_on_hand = 100
WHERE product_id = 10;
```

without updating `version`, it breaks the ORM's optimistic locking assumptions. Enforce one consistent concurrency/version protocol across both JPA and direct SQL.

## 20. Atomic Inventory Updates in SQL

When decrementing stock conditionally, PostgreSQL can do it in one atomic statement:

```sql
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 2,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 2
RETURNING
    product_id,
    stock_on_hand,
    version;
```

Explanation:

- PostgreSQL checks the predicate against the current locked row under concurrent `UPDATE` semantics.
- If enough stock exists, it subtracts 2.
- If insufficient stock or missing product, it returns **0 rows**.
- On success, `RETURNING` emits the new stock level.
- `version` also increments consistently with the versioning protocol.

### 20.1. Why Is This Better Than Reading Stock and Writing an Absolute Value?

It eliminates the race window of “`SELECT` 5, compute 3 in Java, `UPDATE stock = 3`” without verifying current state.

### 20.2. `RETURNING` Does Not Mean the Transaction Committed

An `UPDATE` returning 1 row can still roll back afterward. The API should report “order placed” only after the entire transaction commits.

### 20.3. Beware Stale State When Mixing with ORM

If the persistence context already loaded `Product` before a native `UPDATE`, the managed entity still holds the old stock and version. Call `refresh`/`clear`, or avoid mixing native DML and dirty managed entities for the same row in one use case.

### 20.4. Remember to Reset Fixtures After Testing

This practice statement mutates product 10's stock. In the lab, if you want to restore the initial fixture state, reset explicitly:

```sql
UPDATE orm406.products
SET stock_on_hand = 5,
    version = version + 1
WHERE product_id = 10;
```

Never perform arbitrary manual resets like this in production, and never let application code rewind versions backward.

## 21. Pessimistic Locking: `SELECT ... FOR UPDATE`

Another strategy locks the row before mutating it:

```sql
BEGIN;

SELECT product_id, stock_on_hand
FROM orm406.products
WHERE product_id = 10
FOR UPDATE;

-- Within this transaction, evaluate rules and UPDATE.

UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1
WHERE product_id = 10
  AND stock_on_hand >= 1;

COMMIT;
```

### 21.1. How Long Are Locks Held?

Row locks persist under transaction semantics until commit or rollback of the holding transaction.

### 21.2. `@Lock(PESSIMISTIC_WRITE)` in JPA

Depending on provider, dialect, and query, JPA lock modes emit `FOR UPDATE` or equivalent locking clauses. Never guess from the annotation alone without checking the generated SQL.

### 21.3. Never Make Remote API Calls While Holding Row Locks

Holding locks across network I/O stalls concurrent orders for the same product, spikes timeouts, and raises deadlock risk.

### 21.4. `NOWAIT` and `SKIP LOCKED` Serve Different Purposes

- `NOWAIT`: refuses to wait; fails immediately if the row lock is busy.
- `SKIP LOCKED`: skips locked rows, suited for concurrent job queues.

Neither produces “a complete consistent snapshot for financial reporting.” `SKIP LOCKED` intentionally yields a partial view unsuitable for most reporting queries.

## 22. `SKIP LOCKED` for Worker Queues

Example worker claiming unpublished outbox events:

```sql
BEGIN;

SELECT event_id, payload
FROM orm406.outbox_events
WHERE published_at IS NULL
ORDER BY event_id
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Claim/mark events per design within the transaction.

COMMIT;
```

### 22.1. What Is Missing from This Snippet

This `SELECT` **is not a complete worker**:

- Workers need an explicit claim/lease/retry protocol.
- Never keep transactions open during multi-second or multi-minute broker calls.
- Consumers must be idempotent and deduplicate.
- Skipped locked rows must be revisited on subsequent polls.
- Crashed workers must recover via lease expiration if rows were claimed.

### 22.2. PostgreSQL Lock Semantics Do Not Equal Exactly-Once Delivery

Row locks stop two workers from claiming the exact same row simultaneously. They do not prevent a crash between broker delivery and marking `published_at`, so retries can still redeliver messages.

## 23. Deadlocks: Two Transactions Locking in Opposite Order

Suppose T1 does:

```text
Lock product 10
  -> lock product 11
```

While T2 does:

```text
Lock product 11
  -> lock product 10
```

Both wait on each other; PostgreSQL detects the deadlock and aborts one transaction:

```text
SQLSTATE 40P01: deadlock_detected
```

### 23.1. Reduce Deadlocks with Consistent Lock Ordering

When updating multiple products, acquire locks in a deterministic order (such as ascending `product_id`) to eliminate circular wait cycles.

### 23.2. `lock_timeout` Differs from Deadlocks

A query can fail on `lock_timeout` without forming a deadlock cycle. Distinguish SQLSTATEs, transaction state, and root causes accurately.

### 23.3. Retry at the Proper Boundary

Once PostgreSQL aborts a transaction, the app must roll back and open a fresh transaction covering the entire use case. Never rerun a single repository call on an aborted transaction.

## 24. Transaction Retries: Not Every Error Should Retry

Errors commonly eligible for **controlled retries**:

- `40001`: serialization failure.
- `40P01`: deadlock detected.

Conversely:

- `23505` unique violation usually signals a business or idempotency condition (duplicate `external_request_id`), not a reason to retry endlessly.
- `23503` foreign key violation usually signals invalid reference data.
- `23514` check violation usually signals invalid input.
- Timeouts may indicate lock/CPU/I/O overload; blind retries worsen load.
- Network errors during `COMMIT` leave outcomes **uncertain** for the client: use idempotency and reconciliation.

### 24.1. Retry Pseudocode

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return transactionTemplate.execute(status ->
            performDatabaseUnitOfWork(command)
        );
    } catch (DataAccessException ex) {
        if (!isRetryableTransactionFailure(ex)
                || attempt == maxAttempts) {
            throw ex;
        }
        backoffWithJitter(attempt);
    }
}
throw new IllegalStateException("unreachable");
```

`isRetryableTransactionFailure` must inspect the causal SQLSTATE or driver/Spring exception hierarchy accurately. `backoffWithJitter` is a placeholder requiring real implementation, not a built-in helper.

### 24.2. Retries Must Wrap Fresh Transactions

Never place a retry loop **inside** an already active `@Transactional` method; retries will execute against an aborted or rollback-only transaction.

### 24.3. Never Repeat External Non-DB Side Effects

If the transaction body calls payment APIs or sends emails before commit, retries duplicate them. Separate external side effects or use idempotency keys/outboxes.

## 25. Idempotency: Guarding Against Client Retries and Timeouts

An HTTP client may resend “create order” after timing out even though the first transaction committed.

We defined:

```sql
external_request_id text NOT NULL UNIQUE
```

on `orm406.orders`.

This provides the foundation to detect previously processed requests.

### 25.1. `INSERT ... ON CONFLICT` in PostgreSQL

```sql
INSERT INTO orm406.orders(
    customer_id,
    external_request_id,
    status,
    total_amount
)
VALUES (
    1,
    'REQUEST-XYZ-001',
    'NEW',
    150000
)
ON CONFLICT (external_request_id)
DO NOTHING
RETURNING order_id;
```

If newly inserted, `RETURNING` emits `order_id`. If conflicted and skipped, it returns **0 rows**.

### 25.2. Zero Rows Does Not Prove Payload Equivalence

A caller might reuse a request ID with a different payload. On conflict, load the stored order and verify payload, ownership, and status per your idempotency protocol. Never blindly return “success” when the payload differs.

### 25.3. Unique Constraints Are the Concurrency Defense Line

Two concurrent requests sharing `external_request_id` must never rely on:

```text
SELECT to check existence
  -> if absent, INSERT
```

because both can see “absent” simultaneously. Database `UNIQUE` constraints and `ON CONFLICT` resolve races far more safely than unlocked app pre-checks.

## 26. One Transaction for Order + Item + Outbox

Goals:

1. Deduct stock if sufficient.
2. Create order and order item.
3. Insert outbox event.
4. Commit or roll back all together.

Illustrative SQL transaction flow:

```sql
BEGIN;

-- 1) Reserve 1 item; succeeds only if stock suffices:
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 1
RETURNING product_id, unit_price, stock_on_hand;

-- 2) ONLY when step 1 returns exactly one row:
INSERT INTO orm406.orders(
    customer_id, external_request_id, total_amount
)
VALUES (1, 'ORDER-406-A', 150000)
RETURNING order_id;

-- 3) Use the returned order_id, e.g. 100:
-- INSERT INTO orm406.order_items(
--     order_id, product_id, quantity, unit_price
-- ) VALUES (100, 10, 1, 150000);

-- 4) Write outbox record for the real order_id:
-- INSERT INTO orm406.outbox_events(
--     aggregate_type, aggregate_id, event_type, payload
-- ) VALUES ('order', 100, 'OrderCreated',
--          '{"product_id": 10, "quantity": 1}'::jsonb);

-- COMMIT ONLY after all appropriate steps succeed:
-- COMMIT;
-- During demo/when not persisting: ROLLBACK;
```

This is a **step-by-step scenario, not an automated end-to-end script**. `order_id = 100` is strictly a placeholder never to be hard-coded in production; applications use the ID returned by `RETURNING` and handle zero-row/error cases.

### 26.1. Common Mistake: Updating Stock Zero Rows Yet Still Creating the Order

If the stock `UPDATE` affects 0 rows, treat it as “out of stock / product missing” per business policy; never proceed to insert a valid order.

### 26.2. Never Commit Before Writing the Outbox

If the order commits and a separate transaction writing the outbox fails, the downstream event vanishes. Persisting order + outbox inside one transaction guarantees durable linkage.

### 26.3. Outboxes Do Not Guarantee Exactly-Once Delivery

An outbox publisher may retry after network errors when talking to a broker. Consumers must process events idempotently.

### 26.4. Ensure ORM and JDBC Share One Transaction Unit

If ORM persists the order/item while `JdbcTemplate` updates stock/outbox, they must share the same transaction manager and connection. Separate `DataSource`s or nested independent transactions will not join the same atomic unit.

## 27. Is `@TransactionalEventListener(AFTER_COMMIT)` Durable Enough?

Spring offers post-commit event listeners:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // e.g. notify an in-memory listener
}
```

While this decouples post-commit hooks from pre-commit work, it **does not guarantee durable delivery**:

- The JVM process can crash after DB commit and before the callback finishes.
- The listener or downstream broker can fail.
- In-memory events have no persistent retry store.
- Accessing DB resources inside `AFTER_COMMIT` carries special transaction semantics; new writes need an explicit new transaction.
- An in-process callback is not a durable message queue.

For critical events that must never be dropped, outboxes, CDC, or durable queues are usually required beyond an `AFTER_COMMIT` listener.

## 28. The N+1 Query Problem: One Initial `SELECT` Triggering N Follow-Up `SELECT`s

Suppose we load 100 orders and read customer names in a loop:

```java
List<Order> orders = orderRepository.findAll();
for (Order o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

If `customer` is lazy and unfetched initially, the ORM can emit:

```sql
SELECT ... FROM orm406.orders;             -- 1 query

SELECT ... FROM orm406.customers WHERE customer_id = ?;
SELECT ... FROM orm406.customers WHERE customer_id = ?;
-- ... continuing for each uninitialized association
```

### 28.1. N+1 Is Not Always Literally N+1 Queries

First/second-level caches, shared customers across multiple orders, fetch plans, and provider batching can raise or lower the exact query count. The key symptom is round trips scaling linearly with rows or associations.

### 28.2. Why Is It Slow?

Even fast primary-key `SELECT`s add massive cumulative latency, network round trips, connection occupation, and CPU when repeated 100 or 1,000 times.

### 28.3. Context-Dependent Fixes

- DTO projections selecting only needed columns.
- Targeted `JOIN FETCH` where cardinality stays safe.
- `@EntityGraph`.
- Provider batch fetching or subselect fetching.
- Direct SQL queries for reporting endpoints.
- Controlled caching when consistency semantics allow.

Never “fix N+1” by switching every relationship globally to `EAGER`; that triggers bloated fetches and secondary N+1 cascades elsewhere.

## 29. DTO Projections: Avoiding Full Entity Graph Loads

Example SQL for an order list view:

```sql
SELECT
    o.order_id,
    o.external_request_id,
    o.status,
    o.total_amount,
    c.full_name AS customer_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

One clean query returning exact columns needed.

Conceptual JPQL projection:

```java
@Query("""
    select new com.example.api.OrderRow(
        o.id, o.externalRequestId, o.status,
        o.totalAmount, c.fullName
    )
    from Order o join o.customer c
    order by o.createdAt desc, o.id desc
    """)
List<OrderRow> findRows(Pageable pageable);
```

This snippet assumes the DTO and mapping exist; it is not a standalone compilable file.

### 29.1. Projections Do Not Automatically Prevent All N+1s

If a DTO constructor or post-query mapper navigates lazy collections, extra queries still fire. Measure SQL counts **through response serialization**, not merely up to the repository return.

### 29.2. Never Return JPA Entities Directly as API JSON

Serializing entities triggers unintended lazy loads, exposes internal fields, and risks cyclic recursion. Dedicated DTOs keep API contracts clean and predictable.

## 30. `JOIN FETCH` Is Not Free

Fetching a to-many collection:

```java
@Query("select o from Order o join fetch o.items")
List<Order> findWithItems();
```

multiplies SQL result rows by item counts:

```text
order 1 × 4 items -> 4 SQL rows
order 2 × 8 items -> 8 SQL rows
```

### 30.1. Cartesian Explosion

Fetching multiple collections simultaneously (e.g., `items` and `discounts`) creates a cross-product:

```text
1 order × 20 items × 10 discounts = 200 rows
```

Even though Hibernate deduplicates parent `Order` instances in Java, PostgreSQL still builds and transfers the inflated result set.

### 30.2. Pagination with Collection Fetch Joins

Combining `LIMIT`/`OFFSET` with one-to-many fetch joins often causes incorrect pagination, provider warnings, or full in-memory pagination depending on provider, version, and settings.

A common two-phase pattern:

1. Page over `order_id`s with a deterministic `ORDER BY`.
2. Fetch full orders/items filtered `WHERE order_id IN (...)`.

Or use dedicated projections/aggregations.

### 30.3. Place `WHERE` and `JOIN` Conditions Accurately

`INNER JOIN` drops parent rows lacking optional children. With `LEFT JOIN`, putting predicates in `WHERE` versus `ON` changes null-row retention; verify the actual SQL emitted.

## 31. `LazyInitializationException` and Open Session in View

An entity holds lazy relationships after the service transaction ended:

```java
Order order = service.loadOrder(id); // transaction ends
return order.getItems().size();      // lazy collection not loaded
```

Depending on configuration, accessing it throws `LazyInitializationException`.

### 31.1. The Fix Is Not Making Everything Eager

Fetch everything needed for the response inside a dedicated service query/transaction and map to a DTO before returning:

```java
@Transactional(readOnly = true)
public OrderDetailDto getDetail(Long id) {
    Order o = repository.findWithRequiredAssociations(id)
        .orElseThrow();
    return mapper.toDetailDto(o);
}
```

### 31.2. Open Session in View (OSIV)

OSIV keeps the persistence context open through HTTP response rendering, allowing lazy loading outside the service boundary.

Drawbacks:

- Queries emitted during JSON serialization are hard to spot.
- Encourages N+1 queries outside business transactions.
- Connection, autocommit, and transaction retention behave subtly.
- Couples API contracts directly to entity graphs.

Many API teams disable OSIV and rely on explicit DTOs and fetch plans. Check your Spring Boot version/defaults rather than guessing whether OSIV is enabled.

## 32. Batch `INSERT`/`UPDATE` and Hibernate

Batching cuts round trips on bulk writes, subject to mappings and ID generators.

Illustrative Hibernate configuration (property names vary by version):

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

### 32.1. `IDENTITY` Can Limit Insert Batching

When Hibernate needs database-generated IDs immediately upon each `IDENTITY` insert, JDBC insert batching often cannot operate the way it does with sequence generators. Never enable `batch_size` and assume batching works without inspecting SQL/JDBC logs.

### 32.2. `SEQUENCE` and Allocation Size

Sequence generators support preallocation/pooled optimizers to cut `nextval` round trips. Ensure DB sequence `INCREMENT BY`, ORM `allocationSize`, migrations, and concurrency semantics all align cleanly.

### 32.3. Batching Does Not Define Transactions

Statements can be batched inside one transaction or across multiple transactions; batching optimizes wire dispatch, **not atomicity**.

### 32.4. Manage the Persistence Context During Huge Bulk Inserts

Persisting hundreds of thousands of entities bloats the persistence context. Periodically calling `flush()` and `clear()` keeps heap bounded—remembering `flush()` sends SQL **without committing**, and `clear()` detaches tracked entities.

## 33. Bulk JPQL `UPDATE`/`DELETE` and Cache Consistency

A bulk JPQL update:

```java
@Modifying
@Query("""
    update Product p
    set p.stockOnHand = p.stockOnHand + :delta
    where p.id = :id
    """)
int adjust(@Param("id") Long id, @Param("delta") int delta);
```

behaves differently from mutating a loaded managed entity.

### 33.1. Bulk DML Does Not Sync Already-Loaded Managed Entities

If `Product` 10 is already in the persistence context, the bulk DB update mutates PostgreSQL while the in-memory managed entity keeps old values.

Spring Data JPA options can flush before and clear after modifying queries, with trade-offs for other pending entities in that context.

### 33.2. Version Columns May Not Auto-Increment

Bulk JPQL updates do not automatically enforce `@Version` optimistic locking checks. Write explicit `AND p.version = :v` and `p.version = p.version + 1` logic when optimistic locking is required.

### 33.3. Always Check Affected Row Counts

`UPDATE ... WHERE id = ? AND version = ?` returning 0 rows signals concurrent modification or missing data; never assume success silently.

## 34. Query Pagination: `OFFSET` and Keyset

ORM `Pageable` typically generates `LIMIT`/`OFFSET` or equivalent syntax:

```sql
SELECT
    order_id,
    created_at,
    status
FROM orm406.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
```

With large `OFFSET`s, PostgreSQL walks and discards thousands of rows before emitting 20.

### 34.1. Keyset Pagination

With order `created_at DESC, order_id DESC`, fetch subsequent pages relative to the last seen key:

```sql
SELECT order_id, created_at, status
FROM orm406.orders
WHERE (created_at, order_id)
      < ($1::timestamptz, $2::bigint)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

This prepared query pattern passes the cursor tuple from the final row of the previous page.

### 34.2. Why Is a Tie-Breaker Needed?

`created_at` values can collide. Pairing with unique `order_id` yields a strict total ordering that avoids skipping or duplicating rows on tied timestamps.

### 34.3. Account for Concurrent Mutations Under Keyset Pagination

When rows are inserted or updated between page requests, feed consistency depends on your cursor and product semantics; keyset pagination does not freeze a global snapshot across separate HTTP requests.

### 34.4. ORM `Page<T>` May Run a `COUNT` Query

Returning `Page<Order>` typically triggers a total-count `SELECT COUNT(...)` query alongside the page query unless optimized away or replaced by `Slice<T>`. Measure actual SQL to see whether an expensive `COUNT` runs.

## 35. Count Queries, Not Repository Method Calls

One repository call might:

- Emit zero SQL due to the persistence context cache.
- Emit one `SELECT`.
- Trigger extra lazy or batch-fetch `SELECT`s.
- Emit `COUNT` + `SELECT` for pagination.
- Trigger `INSERT`/`UPDATE` via auto-flush.
- Emit extra mapping/inheritance `SELECT`s depending on provider.
- Emit cascading writes across child collections.

Conversely, calling several repository methods for the same managed entity may issue no extra `SELECT`s.

### 35.1. How to Measure

Count total SQL statements and query categories across an entire request/transaction end-to-end, including response serialization if OSIV is active.

### 35.2. Do Not Measure Only Service-Method Elapsed Time

A 500 ms request might be 50 ms SQL + 450 ms HTTP, or 400 ms lock wait + 100 ms Java. Trace end-to-end across layers.

## 36. Hibernate SQL Logs: Helpful, Yet Incomplete Truth

Example Hibernate 6 logger configuration (differs slightly in Hibernate 5 or other providers):

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Produces output like:

```text
Hibernate:
    select p.product_id, p.stock_on_hand, p.version
    from orm406.products p
    where p.product_id=?
```

And with bind logging enabled:

```text
binding parameter (1:BIGINT) <- [10]
```

### 36.1. Why SQL Text Alone Is Not Enough

A `?` placeholder can represent:

- `bigint`.
- `text`.
- `date`/`timestamp`.
- `numeric`.
- JSON/`bytea`.

Bind types affect casts, operator overload resolution, index usability, and query plans. Inspect parameter types and values in safe environments **without exposing PII or secrets**.

### 36.2. Bind Parameter Logging Can Leak Sensitive Data

Tracing bind values in production logs passwords, tokens, emails, and IDs. Restrict bind logging carefully with redaction/retention rules, or use synthetic test data in non-production environments.

### 36.3. ORM SQL Logs Do Not Prove DB Commit

Seeing `INSERT` in Hibernate logs only proves SQL was built/sent at that moment. The transaction may still roll back or fail at commit.

## 37. PostgreSQL Logs and Actual Queries

PostgreSQL supports logging controls such as:

```conf
# Conceptual example; never enable broadly in production without assessing risk:
log_min_duration_statement = '250ms'
log_lock_waits = on
deadlock_timeout = '1s'
```

Many setups configure `log_line_prefix` with application name, transaction ID, and session ID to correlate logs.

### 37.1. `log_min_duration_statement`

Captures statements exceeding the duration threshold, keeping in mind:

- Extended query protocol / prepared statement details log differently from simple queries.
- Logs can capture sensitive parameter literals.
- Fast N+1 queries individually under 250 ms will not appear.
- Logged statement duration includes lock wait time.

### 37.2. `application_name`

Tagging connections with:

```text
application_name=checkout-api
```

identifies query origins inside PostgreSQL. In multi-instance deployments, pair with distributed request tracing rather than relying solely on static `application_name`.

### 37.3. Never Enable `log_statement = 'all'` Unconditionally

Logging every statement incurs heavy I/O overhead, explodes log storage, and exposes data. Apply selective observability policies and strict log access control.

## 38. `pg_stat_activity`: Who Is Running What?

PostgreSQL exposes active backend state via `pg_stat_activity`:

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    left(query, 300) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

### 38.1. Key States to Watch

- `active`: backend currently executing a query.
- `idle`: awaiting next command.
- `idle in transaction`: open transaction sitting idle between commands.
- `idle in transaction (aborted)`: transaction failed and awaits rollback/end.

### 38.2. Why Is `idle in transaction` Dangerous?

Long open transactions hold locks and snapshots, stall MVCC vacuum cleanup, and tie up pooled connections.

### 38.3. Query Text Is Not Omni-Visible

Permissions, config limits, and query truncation restrict visibility. `pg_stat_activity` shows a **live point-in-time snapshot**, not a historical log of past requests.

## 39. `pg_locks`: Observing Lock Contention

Overview query:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, granted, locktype;
```

### 39.1. Not Every Lock Is a Problem

PostgreSQL takes locks routinely for normal operations. Seeing locks does not imply a deadlock or problem.

### 39.2. Finding Blocking Sessions

Use:

```sql
SELECT
    a.pid,
    a.application_name,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 200) AS query_excerpt
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.pid;
```

`pg_blocking_pids` identifies blocking backends accurately under PostgreSQL lock semantics.

### 39.3. Do Not Rashly Terminate Backends

`pg_terminate_backend` rolls back the active transaction and disrupts client sessions. Identify the source, business impact, and authorization before intervening.

## 40. `pg_stat_statements`: Query Families and Trends

The `pg_stat_statements` extension aggregates execution metrics by normalized query representation per config and version.

Enable in authorized environments (typically requires `shared_preload_libraries` and server restart):

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Reference query:

```sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    left(query, 300) AS query_excerpt
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 40.1. Key Metrics

- Call count.
- Total execution time.
- Mean execution time.
- Rows returned/affected.
- Buffer reads/hits and related metrics depending on version and view settings.

### 40.2. Normalization Has Limits

Query normalization groups matching query shapes, yet should not be treated as a 100% privacy redaction guarantee. Query text can still leak schema/literal hints, and separate logs/bind traces carry their own exposure risks.

### 40.3. `pg_stat_statements` Does Not Replace Per-Request Tracing

It aggregates per query family rather than telling you “HTTP request 123 ran 17 SQL statements, 5 of them during JSON serialization.” Pair database views with application tracing.

## 41. `EXPLAIN` and `EXPLAIN (ANALYZE, BUFFERS)`

To inspect the estimated plan for ORM-generated SQL:

```sql
EXPLAIN (VERBOSE, COSTS ON)
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
ORDER BY o.created_at DESC
LIMIT 50;
```

To measure actual execution for read queries in an appropriate environment:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
ORDER BY o.created_at DESC
LIMIT 50;
```

### 41.1. `EXPLAIN` Is Not `EXPLAIN ANALYZE`

- `EXPLAIN` shows the planner's estimated plan without executing the query.
- `EXPLAIN ANALYZE` **actually executes the query** to measure real times and row counts.

With `UPDATE`/`DELETE`/`INSERT`, `EXPLAIN ANALYZE` **executes real DML mutations**. Only run DML under controlled rollback transactions when strictly needed and understood, or use staging environments.

### 41.2. Compare Estimated vs. Actual Rows

A plan node showing:

```text
rows=100 (estimated)
actual rows=100000
```

points to stale statistics, correlated columns, or poor selectivity estimates that often mislead join strategies.

### 41.3. `BUFFERS`

Shared/local/temp buffer statistics distinguish cache hits, disk I/O, and temp spills, interpreted alongside CPU, lock waits, and overall load. A plan fast on a tiny table may collapse at 30 million rows.

### 41.4. Test the Exact Query and Bind Types

Never analyze a “roughly similar” SQL query with different predicates, casts, joins, or ordering. Extract the exact query emitted by the app with realistic parameter types and run `EXPLAIN` against representative data distributions.

## 42. Prepared Statements and Plan Caching

JDBC typically uses `PreparedStatement`:

```java
String sql = """
    SELECT product_id, stock_on_hand
    FROM orm406.products
    WHERE product_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, productId);
    try (ResultSet rs = ps.executeQuery()) {
        // consume result set
    }
}
```

### 42.1. Parameter Binding Mitigates SQL Injection

Never build SQL like:

```java
String sql = "SELECT * FROM products WHERE code = '" + userInput + "'";
```

due to injection risk and fragile type quoting.

### 42.2. A Java `PreparedStatement` Is Not Automatically a Named Server Statement

Depending on settings and thresholds, pgJDBC uses the extended query protocol, client/server preparation thresholds, and plan caches. Calling `prepareStatement` once in Java does not guarantee a permanent named prepared statement inside PostgreSQL.

### 42.3. Generic vs. Custom Plans

PostgreSQL dynamically selects between custom plans and cached generic plans for prepared statements. Under skewed data distributions, one generic plan may not perform well for every parameter value.

Investigate using:

- `EXPLAIN` across representative parameter values.
- `pg_prepared_statements` for the active session where applicable.
- Latency distributions across parameter buckets.
- PostgreSQL docs on plan caching and `plan_cache_mode`.

Never force generic or custom mode blindly without measuring first.

## 43. Translating Hibernate SQL Logs into `EXPLAIN`

A practical workflow:

1. Attach request/trace IDs in application logs.
2. Enable controlled SQL logging in test/staging or safe sampling.
3. Capture generated SQL and exact **bind parameter types**.
4. Reproduce real parameter mappings, including nullable casts.
5. Reconstruct a representative query in `psql`/client without logging secrets.
6. Run `EXPLAIN`, then `EXPLAIN (ANALYZE, BUFFERS)` safely on representative test data.
7. Inspect indexes, row estimates vs. actuals, sorts, joins, buffers, and wait times.
8. Cross-check against `pg_stat_statements` and application traces.
9. Fix fetch plan, projections, indexes, query shape, or transaction length.
10. Re-verify end-to-end request and DB metrics.

### 43.1. Do Not Just Replace `?` with Plain Strings in an Editor

When Hibernate binds `OffsetDateTime`, `BigDecimal`, `UUID`, `jsonb`, or `bytea`, pasting raw text literals with wrong types can trigger different operators or query plans.

### 43.2. Mind Timezones

When mapping Java `Instant`/`OffsetDateTime` to `timestamptz`, preserve explicit UTC offsets in test queries rather than converting to timezone-less local strings.

### 43.3. Never Strip `LIMIT`/`OFFSET` or `DISTINCT`

Clauses like `DISTINCT`, `ORDER BY`, `LIMIT`/`OFFSET`, `JOIN FETCH`, and `COUNT` queries are frequently where costs hide.

## 44. `auto_explain` and Queries Inside Functions

Some PostgreSQL deployments configure the `auto_explain` extension to log execution plans of slow statements automatically, optionally inspecting nested SQL inside functions.

Trade-offs:

- Requires specific privileges and configuration.
- Adds measurable overhead if set broadly, especially with `log_analyze`.
- Logged plans may expose object names, query text, or sensitive parameters.
- Often restricted on managed PostgreSQL services.

**Never enable broad `auto_explain` logging in production without strict duration limits and log protection.**

## 45. Indexes Must Come from Actual SQL

Suppose the application frequently executes:

```sql
SELECT
    order_id,
    customer_id,
    status,
    created_at
FROM orm406.orders
WHERE customer_id = 1
  AND status = 'NEW'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Consider indexing:

```sql
CREATE INDEX idx_orm406_orders_customer_status_created
ON orm406.orders(
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
```

### 45.1. Do Not Create Indexes Simply Because Entity Fields Exist

Having a Java field does not merit an independent column index. Design indexes around actual filter predicates, joins, sort orders, selectivity, write amplification, and query workload.

### 45.2. Indexes Carry Write Costs

Every `INSERT`, `UPDATE`, and `DELETE` maintains affected indexes, adding WAL, CPU, and disk I/O. Never throw dozens of speculative indexes at a slow `SELECT`.

### 45.3. `UNIQUE` Constraints Protect Integrity and Accelerate Lookups

`external_request_id UNIQUE` is not merely a fast lookup index; it enforces duplicate protection under concurrency. ORM annotations are metadata; the database constraint actually enforces uniqueness.

## 46. N+1 and SQL Statistics: An Observed Example

Suppose an endpoint returns 100 orders:

```text
HTTP GET /orders
  Repository.findAll()             -> 1 SELECT
  Map each order.customer.name     -> 37 SELECT
  Map each order.items             -> 100 SELECT
  Serializer loads product names   -> 80 SELECT
------------------------------------------------
  Total SQL                         218 SELECT
```

These numbers are **illustrative** (not lab benchmarks) to show why inspecting one repository method hides the full query explosion.

### 46.1. Setting Query-Count Assertions in Tests

An integration test can assert:

```text
fetch 20 order summary rows
  -> no more than a small expected number of SQL statements
```

Tune exact bounds to your fetch strategy rather than rigidly demanding “every endpoint runs 1 query.” Measure latency, payload size, and domain requirements.

### 46.2. Where to Count SQL Statements

- Hibernate SQL logs and statistics.
- Test statement-counting listeners.
- DataSource proxy utilities where applicable.
- PostgreSQL query logs and `pg_stat_statements`.
- Distributed tracing DB spans.

Pick instrumentation that never leaks PII or secrets.

## 47. ORM Caches: Caching Is Not Transaction Isolation

Caching layers can include:

1. Persistence context first-level cache.
2. Hibernate second-level cache (if enabled).
3. Query cache (if configured).
4. Application caches such as Redis.
5. Database buffer cache.

### 47.1. First-Level Cache and Entity Identity Repeatability

`EntityManager` returning the same managed instance without firing another `SELECT` reflects persistence context identity semantics—not proof that PostgreSQL is running `REPEATABLE READ`.

### 47.2. Second-Level Cache Invalidation Risks

If another service or native SQL job modifies a table without coordinated cache invalidation, the app may serve stale state.

### 47.3. Does Query Caching Suit Write-Heavy Tables?

Often not: frequent invalidations, churn, and tenant scoping can cost more than they save. Measure hit ratios, staleness risk, and write patterns.

### 47.4. Caches Never Prevent Lost Updates

Reading stale cached stock values makes lost updates worse if code writes absolute quantities back without versioning or atomic predicates.

## 48. Timezone, `numeric`, and `jsonb` Mapping

### 48.1. `timestamp` vs. `timestamptz`

- `timestamp without time zone`: calendar date-time carrying no instant timezone interpretation.
- `timestamptz`: stores an absolute instant in time, formatted according to session timezone.

Never map `LocalDateTime` pretending it represents a timezone-aware `Instant` without strict timezone contracts.

### 48.2. `date`

`date` pairs cleanly with `LocalDate` for calendar dates like birth dates or delivery dates without time-of-day.

### 48.3. `numeric`

Map `numeric(14,2)` to `BigDecimal` for financial values to eliminate binary floating-point rounding errors.

### 48.4. `jsonb`

ORM providers support JSON mappings, while PostgreSQL `jsonb` carries distinct semantics:

- JSON objects and arrays.
- GIN indexing, containment operators, and jsonpath queries.
- JSON `null` differs from SQL `NULL`.
- Applications must govern schema evolution and validation.

Avoid stuffing the entire domain model into one `jsonb` column merely to skip relational migrations.

### 48.5. Nullability

Bean Validation `@NotNull` in Java and `NOT NULL` in PostgreSQL are separate validation layers. Keep them aligned while ensuring database constraints really exist.

## 49. RLS and Tenant Boundaries with ORM

ORM repository filters can inject tenant predicates, yet cannot guarantee airtight isolation if:

- Native SQL bypasses ORM filters.
- Background jobs or admin queries omit filters.
- Lazy associations or entity graphs traverse unfiltered paths.
- SQL injection runs under an over-privileged role.
- Database views/functions execute under different role privileges.

### 49.1. Defense in Depth

```text
Authentication
  -> trusted tenant identity
  -> service authorization
  -> ORM filter / query scoping
  -> PostgreSQL RLS where appropriate
  -> GRANT / role separation
  -> audit / monitoring
```

### 49.2. RLS Does Not Protect Tenants If Roles Bypass It

`SUPERUSER`, `BYPASSRLS`, and certain table-owner contexts bypass RLS. Never run application workloads as a `SUPERUSER`.

### 49.3. Session Tenant Context and Connection Pools

When relying on custom GUCs/roles for RLS, ensure:

- Tenant context derives solely from verified authentication state.
- Users cannot overwrite it via unrestricted SQL.
- Context is set properly for the transaction scope (`SET LOCAL`).
- State resets cleanly when connections return to the pool.
- Automated tests run under the actual unprivileged application DB role.

### 49.4. Schema-per-Tenant Carries Different Trade-Offs

Schema-per-tenant and database-per-tenant trade off isolation against migrations, pool sizing, `search_path`, privileges, backups, and monitoring. Multi-tenancy flags in an ORM do not prove database isolation is sound.

## 50. Migration & Schema Validation: Never Let Hibernate Auto-Alter Production

In development you may see:

```properties
spring.jpa.hibernate.ddl-auto=update
```

Convenient in local labs, this poses severe risks if used to mutate production schemas unattended.

### 50.1. Architectural Recommendations

- Use versioned migrations (Flyway, Liquibase, or reviewed SQL scripts).
- Run DDL at controlled deployment boundaries with migration privileges.
- Deny broad `CREATE`/`ALTER` rights to the runtime application role in production.
- Validate ORM mappings against the migrated schema.
- Test migrations on real PostgreSQL versions and representative data sizes.
- Plan locking, concurrent index builds, and rollouts for large tables.

### 50.2. `@Column(unique = true)` Does Not Create a Production Migration

Seeing `@Column(unique = true)` in Java does not prove PostgreSQL actually has the unique constraint. Always inspect catalogs and DDL directly.

### 50.3. Enum Mapping

Mapping Java enums to `text` vs. PostgreSQL `ENUM` types involves migration trade-offs around adding values, renaming, backward compatibility, and `CHECK` constraints. Evaluate existing rows before altering enum mappings.

### 50.4. Sequence Allocation Mismatch

Mismatched ORM generator `allocationSize` and database sequence `INCREMENT BY` produce negative or colliding IDs depending on provider. Check sequence DDL carefully when switching between `IDENTITY` and `SEQUENCE`.

## 51. Pool Sizing: More Connections Is Not Always Faster

A connection pool exposes key parameters:

```text
maxPoolSize
minIdle
connectionTimeout
idleTimeout
maxLifetime
validationQuery / connectionTestQuery (where applicable)
leakDetectionThreshold (diagnostic)
```

Exact property names depend on pool implementation.

### 51.1. Oversized Pools Overload PostgreSQL

Hundreds of active connections increase context switching, backend memory, and lock/CPU contention. If a database peaks around 20 active cores/queries, opening 200 concurrent connections will not make it 10× faster.

### 51.2. Pool Starvation from Long Transactions

One endpoint holding connections across slow HTTP calls causes hundreds of fast requests to stall waiting for pool checkout even when SQL queries take milliseconds.

### 51.3. `REQUIRES_NEW` Multiplies Connection Demand

Because an outer transaction holds one connection while an inner `REQUIRES_NEW` requests another, tight pools can deadlock waiting on themselves under concurrency. Factor propagation patterns into pool budgets.

### 51.4. Inspect Directly

Combine pool metrics (`active`/`idle`/`pending`), `pg_stat_activity`, DB CPU/locks, and distributed traces. Never just bump `maximumPoolSize` blindly on timeouts.

## 52. `statement_timeout`, `lock_timeout`, and Idle Transaction Timeouts

PostgreSQL supports session/transaction limits:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

SELECT *
FROM orm406.products
WHERE product_id = 10;

COMMIT;
```

### 52.1. `statement_timeout`

Bounds individual statement execution under PostgreSQL rules. It is not synonymous with an HTTP request deadline or JPA transaction timeout in every configuration.

### 52.2. `lock_timeout`

Limits time spent waiting on lock acquisition before canceling the query. Setting it overly tight can cause legitimate busy operations to fail frequently.

### 52.3. `idle_in_transaction_session_timeout`

Protects against abandoned open transactions, yet terminating the session surfaces errors the application must handle. Use it as a guardrail alongside clean transaction boundaries—never as a substitute.

### 52.4. Timeout Layering

Coordinate budgets top-to-bottom:

```text
HTTP timeout
    |
    +-- service-level deadline
    |
    +-- connection acquisition timeout
    |
    +-- transaction timeout
    |
    +-- statement_timeout
    |
    +-- lock_timeout
```

If an HTTP layer times out while the DB keeps executing, wasted work or ambiguous client states follow. Pair layered timeouts with cancellation propagation and idempotency.

## 53. Failure Scenario: SQL Succeeds, Response Fails

Timeline:

```text
T1: Service builds order.
T2: Hibernate flush -> INSERT succeeds.
T3: PostgreSQL COMMIT succeeds.
T4: Network drops between app and client.
T5: Client never receives order_id.
T6: Client retries identical request.
```

If request 2 creates another order, duplicate business state occurs.

### 53.1. How to Handle

- Require client idempotency keys.
- Enforce a PostgreSQL `UNIQUE` constraint on that key.
- On collision, verify matching payload, ownership, and status.
- Return the committed result safely on valid retries.
- Never infer DB rollback merely because the client missed HTTP 200.

### 53.2. Never Treat HTTP Exceptions as Proof of DB Rollback

Response serialization or network errors happen **after commit**. Once the transaction closed and committed, a Java rollback cannot undo it.

## 54. Another Failure Scenario: Flush Ran, Then Everything Rolled Back

Timeline:

```text
T1: BEGIN.
T2: INSERT order -> received by PostgreSQL.
T3: INSERT order_item -> received by PostgreSQL.
T4: INSERT outbox -> hits constraint violation.
T5: Transaction rolls back.
T6: Queries from other transactions see neither order nor item.
```

### 54.1. Why Not Log Business “Order Created” Too Early?

Emitting business-success metrics or events before commit makes observability diverge from durable reality.

### 54.2. Diagnostic Logs vs. Outbox Events

- Diagnostic logs record attempts, SQL execution, and rollbacks.
- Outbox events persist business facts atomically so consumers see only committed events.

Never use application text logs as a durable event bus.

## 55. Transaction Boundaries and API Composition

An endpoint orchestrating multiple services:

```java
@PostMapping("/checkout")
public OrderResponse checkout(@RequestBody CheckoutRequest req) {
    Customer c = customerService.load(req.customerId());
    Order o = orderService.create(req, c);
    inventoryService.decrement(req.items());
    paymentService.charge(req.paymentToken());
    return ...;
}
```

If each method starts its own separate transaction, this HTTP request **does not execute inside one atomic database transaction**.

### 55.1. Orchestrate DB Units in One Application Service

When database invariants require atomicity, wrap related DB steps in one transactional service method. Handle external payments in a separate step or saga/outbox workflow.

### 55.2. Transaction Boundaries Do Not Automatically Cross Threads

`@Async` or thread-pool workers do not inherit Spring's `ThreadLocal` transaction context automatically; they open independent connections/transactions.

### 55.3. Multiple `DataSource`s

Using two databases inside one `@Transactional` method bound to one `DataSource` transaction manager does not produce a distributed ACID transaction. Cross-DB consistency requires explicit patterns (sagas, outboxes, or XA/JTA with known caveats).

### 55.4. `TransactionTemplate` for Complex Boundaries

When splitting I/O out of DB transactions or adding retries, `TransactionTemplate` makes exact transaction boundaries explicit and launches fresh transactions cleanly per attempt.

## 56. Inspecting Generated Queries: An End-to-End Workflow

Suppose `GET /customers/1/orders` is slow:

**Step 1:** Measure endpoint p95/p99 latency and capture a correlation ID.

**Step 2:** Count SQL statements and DB span time in application tracing.

**Step 3:** Check for N+1 queries caused by entity mapping or response serialization.

**Step 4:** Capture generated SQL and bind types (using test data; avoid logging secrets).

**Step 5:** Locate expensive query families in `pg_stat_statements`.

**Step 6:** Inspect lock waits and idle-in-transaction sessions in `pg_stat_activity` and `pg_locks`.

**Step 7:** Run `EXPLAIN (ANALYZE, BUFFERS)` safely on slow `SELECT`s with representative data.

**Step 8:** Improve fetch plans, projections, indexes, query shape, pagination, or transaction length.

**Step 9:** Re-run under load and verify correctness, row counts, and lock behavior.

**Step 10:** Deploy with monitoring and rollback readiness.

### 56.1. Never Add Indexes Before Seeing the Actual SQL

A slow endpoint could stem from:

- 101 tiny queries instead of 1 slow query.
- Lock waits.
- JDBC pool checkout waits.
- Slow JSON serialization.
- External API calls.
- JVM GC pauses.
- A query missing an index.

Each root cause calls for a different fix.

## 57. Integration Test Pattern for Transaction Rollback

A solid integration test should:

1. Execute a multi-step DB use case.
2. Inject a failure at the final step (e.g., unique constraint violation).
3. Verify the method throws and triggers rollback.
4. Query from a separate transaction/connection to verify no order, item, or outbox row exists.
5. Verify sequence ID gaps are not misread as committed rows.
6. Verify no external side effect fired prior to commit.

Pseudo-code:

```java
@Test
void orderAndOutboxRollbackTogether() {
    assertThrows(
        SomeExpectedException.class,
        () -> orderService.createWithInjectedOutboxFailure(command)
    );

    // Inspect via a clean transaction/EntityManager:
    assertThat(orderRepository.findByExternalRequestId(key))
        .isEmpty();
    assertThat(outboxRepository.findByBusinessKey(key))
        .isEmpty();
}
```

### 57.1. `@Transactional` Test Methods Can Create False Confidence

Wrapping an integration test itself in `@Transactional` with auto-rollback may bypass the real commit boundary of production services. When testing **commit-time failures** or `REQUIRES_NEW`, manage test transactions explicitly without wrapping the outer test method.

### 57.2. Test Against Real PostgreSQL for PostgreSQL-Specific Behavior

H2/in-memory databases diverge from PostgreSQL on:

- Isolation and locking behavior.
- `ON CONFLICT`.
- `RETURNING`.
- `jsonb`.
- Partial and expression indexes.
- Sequences and identity columns.
- SQLSTATE codes.
- Row-level security (RLS).

Run integration tests against real PostgreSQL containers/instances whenever validating those behaviors.

## 58. Common Mistakes Using ORM and Transactions

### Mistake 1 — Treating `save()` as `commit()`

`save()` may only attach an entity or emit an early `INSERT`; neither confirms transaction commit.

### Mistake 2 — Treating `flush()` as `commit()`

Flushing syncs SQL inside the active transaction; rollback can still undo everything.

### Mistake 3 — Putting `@Transactional` on a Self-Invoked Method

Standard Spring proxies do not intercept `this.inner()` calls.

### Mistake 4 — Treating `@Transactional(readOnly = true)` as `SELECT`-Only Security

It never replaces database `GRANT`s and RLS.

### Mistake 5 — Catching an Exception and Assuming Spring Always Rolls Back

Swallowing exceptions without rethrowing or flagging rollback-only may cause commit attempts, while SQL errors abort PostgreSQL transactions.

### Mistake 6 — Retrying a Serialization Error Inside the Same Aborted Transaction

Roll back and open a fresh transaction.

### Mistake 7 — Blindly Retrying Every SQLSTATE

Unique, FK, and check violations do not resolve via blind retries.

### Mistake 8 — Sending Emails/Payments Inside a DB Transaction Expecting Rollback

External calls do not participate in PostgreSQL ACID transactions.

### Mistake 9 — Using `REQUIRES_NEW` for Audit Logs That Must Roll Back with Orders

Independent commits persist audit entries even when the order rolls back.

### Mistake 10 — Assuming `NESTED` Commits Independently

Savepoints live inside the outer transaction and roll back with it.

### Mistake 11 — Reading Stock and Writing `stock - 1` Without Locking or Versioning

Concurrent reads cause lost updates.

### Mistake 12 — Using `@Version` in ORM While Native SQL Skips Incrementing Version

Breaks optimistic locking assumptions.

### Mistake 13 — Running Bulk JPQL `UPDATE` and Expecting Managed Entities to Auto-Refresh

Persistence context instances stay stale unless cleared or refreshed.

### Mistake 14 — Triggering N+1 via Lazy Associations

A single repository call fans out into many queries during mapping or serialization.

### Mistake 15 — Switching Every Association to `EAGER` to Cure N+1

Bloats payloads, causes join explosions, and triggers cascading queries elsewhere.

### Mistake 16 — Combining Multi-Collection `JOIN FETCH` with `Pageable`

Causes cartesian explosions, inaccurate limits, or in-memory pagination.

### Mistake 17 — Setting `batch_size` with `IDENTITY` Without Checking SQL Logs

Batching may silently stay inactive due to ID fetching rules.

### Mistake 18 — Assuming `@Column(unique = true)` Means Production Has the Constraint

Always inspect migrations and PostgreSQL schema directly.

### Mistake 19 — Holding Transactions Open Across HTTP Calls

Pins pooled connections, locks, and snapshots, driving contention.

### Mistake 20 — Leaving OSIV Enabled Without Tracing Serialization Queries

Fires unmonitored SQL outside service boundaries.

### Mistake 21 — Returning Entities Directly as API JSON

Exposes internal fields, triggers lazy queries, and risks recursion loops.

### Mistake 22 — Reading Hibernate SQL Logs Without Checking Bind Types

Parameter types affect casts, operator matching, and index plans.

### Mistake 23 — Enabling Detailed SQL/Bind Logging Broadly in Production

Exposes PII/secrets and floods storage.

### Mistake 24 — Running `EXPLAIN ANALYZE UPDATE` on Live Data

`ANALYZE` **executes the statement** and mutates data.

### Mistake 25 — Treating `pg_stat_statements` as Per-HTTP-Request Tracing

It aggregates by query family, lacking per-request context.

### Mistake 26 — Confusing the First-Level Cache with Transaction Isolation

Persistence context identity differs from PostgreSQL MVCC snapshots.

### Mistake 27 — Paginating Solely by `ORDER BY created_at`

Tied timestamps yield unstable ordering.

### Mistake 28 — Using Huge `OFFSET` Without Checking Query Plans

Scans and discards massive row counts before returning a page.

### Mistake 29 — Raising Pool Size to Fix Any Latency Spike

Worsens DB contention without curing locks or N+1 queries.

### Mistake 30 — Failing to Reset Connection/Session State in Pools

Leaks `search_path`, tenant variables, roles, and timeouts across requests.

### Mistake 31 — Running Application Connections as `SUPERUSER`

Bypasses RLS/permissions and expands security blast radius.

### Mistake 32 — Assuming `UPDATE ... RETURNING` 1 Row Means Committed

It only reflects statement execution inside an active uncommitted transaction.

### Mistake 33 — Retrying Order Creation HTTP Calls Without Idempotency Keys

Produces duplicate orders if the original response drops post-commit.

### Mistake 34 — Ignoring Affected Row Counts on Optimistic/Conditional `UPDATE`s

Zero affected rows signals a version conflict or unmet business condition.

### Mistake 35 — Letting Hibernate Auto-Update Production Schemas

Risks destructive DDL, downtime, and migration drift.

### Mistake 36 — Testing Plans on 3 Rows and Assuming They Scale to 30 Million

Cardinality and planner choices shift dramatically on real data volumes.

## 59. Practice Exercises with Answers

Exercises build on schema `orm406` and Java/Spring patterns. For DML statements, run inside a separate lab transaction and roll back/reset as needed.

### Exercise 1. Does ORM eliminate SQL?

**Answer:** no. ORM translates object operations into SQL and persistence calls.

### Exercise 2. How do JPA and Hibernate differ?

**Answer:** JPA is the Java persistence specification; Hibernate is a popular implementation/provider offering extra features.

### Exercise 3. If a managed entity mutates a field, must you call `save()` every time?

**Answer:** not necessarily; dirty checking emits SQL automatically at flush inside a transaction.

### Exercise 4. If `save(order)` returns an ID, has the transaction committed?

**Answer:** cannot assume so. IDs can be generated before or during `INSERT`; commit is a separate boundary.

### Exercise 5. If you `flush()` and then `rollback()`, does the inserted row remain?

**Answer:** uncommitted row DML rolls back, though non-transactional side effects like consumed sequence numbers persist.

### Exercise 6. When can auto-flush happen?

**Answer:** before certain queries, before commit, or on explicit `flush()`, depending on flush mode and provider.

### Exercise 7. Why can `this.innerTransactional()` fail to start a transaction?

**Answer:** self-invocation bypasses standard Spring AOP proxy interception.

### Exercise 8. Does `@Transactional` roll back checked exceptions by default?

**Answer:** not merely because an exception is checked; configure `rollbackFor` or custom rollback policies.

### Exercise 9. Inner `REQUIRED` fails and marks rollback-only; outer catches it and returns normally. What happens?

**Answer:** the transaction rolls back and the outer boundary throws `UnexpectedRollbackException` upon commit.

### Exercise 10. Does `REQUIRES_NEW` commit independently of the outer transaction?

**Answer:** yes, per transaction manager rules; rolling back the outer transaction does not undo a committed inner one.

### Exercise 11. Why does `REQUIRES_NEW` pressure the connection pool?

**Answer:** the outer transaction retains one connection while the inner requires a second connection simultaneously.

### Exercise 12. Are `NESTED` and `REQUIRES_NEW` equivalent?

**Answer:** no; `NESTED` relies on savepoints inside the same outer transaction where supported rather than independent commits.

### Exercise 13. Does `readOnly = true` replace `GRANT` permissions?

**Answer:** no. It does not alter SQL authorization rules.

### Exercise 14. What does JDBC `autoCommit = true` mean?

**Answer:** each statement generally auto-commits upon completion unless managed/overridden by a framework or pool.

### Exercise 15. What happens if an app sets `search_path` per tenant without resetting pooled connections?

**Answer:** subsequent requests can inherit prior session state, causing errors or cross-tenant data exposure. Use transaction-scoped state and proper pool hygiene.

### Exercise 16. Can two `SELECT`s under `READ COMMITTED` return different values?

**Answer:** yes, if another transaction commits in between and the query actually executes rather than hitting an unrefreshed entity cache.

### Exercise 17. Does `REPEATABLE READ` mean transactions never fail?

**Answer:** no; concurrent update conflicts can still raise serialization errors requiring retries.

### Exercise 18. What does `SQLSTATE 40001` indicate?

**Answer:** serialization failure; typically retry the full transaction under a bounded policy.

### Exercise 19. What does `SQLSTATE 40P01` indicate?

**Answer:** deadlock detected; one transaction aborted and needs rollback and controlled retry.

### Exercise 20. With `stock = 5`, two concurrent buyers each purchase 1 item under lost-update read-modify-write. What happens?

**Answer:** if both write absolute `stock = 4` from stale reads, inventory ends up wrong (`4` instead of expected `3`).

### Exercise 21. Write an atomic `UPDATE` to decrement 1 item of stock

```sql
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 1
RETURNING stock_on_hand;
```

**Answer:** returns 1 row on success, or 0 rows if stock is insufficient or the product does not exist.

### Exercise 22. Does `UPDATE ... RETURNING` emitting 1 row mean the commit succeeded?

**Answer:** no; the transaction can still roll back afterward.

### Exercise 23. Does `@Version` protect native SQL updates that ignore version checks?

**Answer:** not automatically. Include native SQL in the same locking/versioning protocol when needed.

### Exercise 24. When is `FOR UPDATE` suitable?

**Answer:** when a transaction must lock specific rows across a short read–evaluate–modify sequence; keep transactions brief.

### Exercise 25. Is `SKIP LOCKED` suitable for accurate revenue reporting?

**Answer:** usually no; it skips locked rows and produces an incomplete view. It fits worker queues instead.

### Exercise 26. Why is retrying a transaction that calls a payment gateway inside its body dangerous?

**Answer:** external payment charges can execute repeatedly on transaction retries.

### Exercise 27. How does `external_request_id UNIQUE` help?

**Answer:** prevents duplicate order creation across client retries, paired with payload/ownership validation on conflict.

### Exercise 28. What does `ON CONFLICT DO NOTHING RETURNING` return on conflict?

**Answer:** 0 rows for the skipped insert.

### Exercise 29. Across how many transactions should order and outbox writes commit when atomicity is needed?

**Answer:** one shared PostgreSQL transaction whenever possible.

### Exercise 30. Does an `AFTER_COMMIT` listener guarantee durable event delivery?

**Answer:** no; a process crash between commit and callback drops the event. Outboxes/CDC solve durability.

### Exercise 31. What is N+1?

**Answer:** one list query triggering N follow-up queries while iterating associations, adding severe round-trip overhead.

### Exercise 32. Does marking every relationship `EAGER` always cure N+1?

**Answer:** no; it causes oversized joins, over-fetching, and unexpected follow-up queries.

### Exercise 33. What risks arise from fetch-joining 2 collections?

**Answer:** cartesian explosions, provider multi-bag/collection restrictions, and broken pagination.

### Exercise 34. When are DTO projections ideal?

**Answer:** when queries only need display/API columns, avoiding loading full entity graphs.

### Exercise 35. At what phase can OSIV emit SQL?

**Answer:** during HTTP rendering or JSON serialization after the service method returned, depending on config/provider.

### Exercise 36. Does Hibernate `jdbc.batch_size = 50` guarantee batched inserts with `IDENTITY`?

**Answer:** no; ID generation strategies and provider rules can disable insert batching.

### Exercise 37. Does bulk JPQL `UPDATE` automatically refresh managed entities?

**Answer:** not by default; persistence context state can become stale and version handling must be explicit.

### Exercise 38. Why can `Page<T>` execute two queries?

**Answer:** one query fetches page rows while a `COUNT` query computes total elements and pages.

### Exercise 39. What does keyset pagination require?

**Answer:** a strict deterministic ordering and cursor from the last seen key, e.g. `(created_at, order_id)`.

### Exercise 40. How do you prevent SQL injection in JDBC?

**Answer:** use `PreparedStatement` with bind parameters; never concatenate untrusted input into SQL strings.

### Exercise 41. What is the risk of enabling Hibernate bind `TRACE` logging in production?

**Answer:** leaking PII/credentials and generating excessive log volume.

### Exercise 42. What does `pg_stat_activity` show?

**Answer:** live backend state, active/last query, wait events, and transaction age, subject to privileges and point-in-time snapshot limits.

### Exercise 43. What harm can `idle in transaction` cause?

**Answer:** holds locks, snapshots, and pool connections open, raising contention and blocking vacuum cleanup.

### Exercise 44. Does `pg_stat_statements` identify a specific HTTP request?

**Answer:** not by itself; it aggregates query families and must be paired with application tracing.

### Exercise 45. Is `EXPLAIN ANALYZE UPDATE` safe to run casually in production?

**Answer:** it actually executes the `UPDATE`; run only in test environments or tightly controlled rollback scopes understanding all side effects.

### Exercise 46. When an SQL log shows `?` placeholders, what else do you need for plan analysis?

**Answer:** bind types, representative parameter values, session context, `search_path`, and the exact SQL text.

### Exercise 47. Which index suits queries filtering customer + status ordered by `created_at`?

**Answer:** a composite index leading with `(customer_id, status, created_at DESC, order_id DESC)` is often effective; verify with `EXPLAIN` on representative data.

### Exercise 48. Does a larger connection pool always improve speed?

**Answer:** no; oversized pools amplify DB contention. Monitor active/pending counts, locks, and DB capacity.

### Exercise 49. Email sent after `flush()` before `commit()`, then the transaction rolls back—does the email roll back?

**Answer:** no. Use transactional outboxes and idempotent workflows.

### Exercise 50. Is testing on H2 sufficient to verify `ON CONFLICT` or `SKIP LOCKED`?

**Answer:** no; run tests against real PostgreSQL whenever relying on PostgreSQL-specific behavior.

## 60. Pre-Deployment Checklist for ORM Use Cases

| Question | What Must Be Clear |
|---|---|
| Which steps form an atomic DB unit? | Transaction boundary |
| Is `@Transactional` actually intercepted? | Proxies / self-invocation / threads |
| Does transaction manager match `DataSource`? | Multi-`DataSource` correctness |
| Is external I/O inside a transaction? | Lock duration / side effects |
| Can the service throw checked exceptions? | `rollbackFor` policy |
| Do caught exceptions break rollback intent? | Rollback-only / commit behavior |
| Are `REQUIRES_NEW` / `NESTED` used? | Independent commits / savepoints |
| Are rows updated concurrently? | `@Version` / locks / atomic SQL |
| Do `40001`/`40P01` need retries? | Fresh transactions / bounded backoff |
| Can clients retry requests? | Unique idempotency keys |
| Is there an outbox for critical events? | Atomic DB writes, async delivery |
| Are entity states & dirty checking understood? | Managed vs. detached |
| Are `flush` and `commit` kept distinct? | Accurate success signaling |
| Is native DML mixed with managed entities? | Stale persistence context |
| Do bulk JPQL updates handle `version`? | Optimistic locking |
| Do serializers touch lazy relations? | N+1 / OSIV |
| Do fetch joins bloat result sets? | Cartesian explosion |
| Does pagination use stable `ORDER BY`? | Tie-breakers / keyset |
| Does `Page<T>` run costly `COUNT` queries? | Query counts |
| Is JDBC batching actually active? | ID strategy / SQL logs |
| Do ORM mappings match actual DDL? | Constraints / indexes / types |
| Are money and timestamps mapped accurately? | `BigDecimal` / `timestamptz` |
| Is all SQL parameterized safely? | `PreparedStatement` |
| Could SQL logs expose PII or keys? | Redaction / sampling |
| Can you observe the real emitted SQL? | Hibernate logs / JDBC |
| Can you spot DB waits and locks? | `pg_stat_activity` / `pg_locks` |
| Are top query families tracked? | `pg_stat_statements` |
| Was `EXPLAIN` run on representative data? | Plans, actual rows, buffers |
| Are pool waits, network, and serialization measured? | End-to-end tracing |
| Does pooled connection/session state reset? | Pool hygiene, `search_path`, roles |
| Does the app role enforce least privilege? | `GRANT`/RLS, never `SUPERUSER` |
| Do transactions carry sensible timeouts? | Statement / lock / deadlines |
| Are idle-in-transaction sessions monitored? | Pool / DB metrics |
| Are migrations versioned and reviewed? | Flyway / Liquibase / DDL |
| Do integration tests use real PostgreSQL? | Isolation / locking / SQLSTATE |
| Are commit-time failures and retries tested? | Proper rollback / idempotency |

## 61. Quick Reference Table

| Scenario | Related Mechanism | What to Verify |
|---|---|---|
| Saving a new entity | `persist` / `save` | When `INSERT` runs / ID allocation |
| Mutating a managed field | Dirty checking | SQL `UPDATE` at flush |
| Forcing SQL before commit | `flush` | Still uncommitted |
| Atomicity across repositories | `@Transactional` | Proxy + matching manager |
| Inner method joins caller txn | `REQUIRED` | Joins existing transaction |
| Inner method needs isolated commit | `REQUIRES_NEW` | Pool capacity and split consistency |
| Partial rollback inside txn | `NESTED` / savepoint | Manager/provider support |
| Preventing lost updates | `@Version` or atomic `UPDATE` | Keep native DML aligned |
| Locking a row | `FOR UPDATE` | Keep transactions short |
| Worker job queue | `SKIP LOCKED` | Leases / retries / idempotency |
| Serialization failure | SQLSTATE `40001` | Retry full transaction |
| Deadlock | SQLSTATE `40P01` | Lock ordering / retries |
| Client retry | Unique request ID | Payload consistency |
| Durable post-commit events | Outbox + worker/CDC | Consumer idempotency |
| N+1 queries | DTO / fetch plan / batch fetch | Total SQL count and latency |
| Fetch-joining multiple collections | Two-phase load / projection | Row blowup / pagination |
| Bulk updates | Native SQL / JPQL | Context and version sync |
| ORM-generated SQL | Hibernate SQL logger | Bind types / sensitive logs |
| What backends are doing | `pg_stat_activity` | Wait events / transaction age |
| Who holds locks | `pg_locks`, `pg_blocking_pids` | Blocker sessions |
| Slow query families | `pg_stat_statements` | Calls / time / rows |
| Query plan | `EXPLAIN` | Estimates / indexes |
| Actual execution plan | `EXPLAIN (ANALYZE, BUFFERS)` | Executes statement |
| Schema management | SQL migrations | DDL matches mappings |
| Data integrity | DB constraints | Never annotations alone |
| Tenant isolation | Roles + RLS | Trusted context / pool hygiene |
| Query timeouts | statement/lock timeouts | Coordinated deadlines |

## 62. References and Further Reading

**PostgreSQL:**

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, table locks, deadlocks.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — `ON CONFLICT`, `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — conditional updates, row counts, `RETURNING`.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html) and [ROLLBACK TO SAVEPOINT](https://www.postgresql.org/docs/current/sql-rollback-to.html).
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW) — backends, wait events, transaction age.
- [pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html) — lock monitoring.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query statistics.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — estimated and actual execution plans.
- [Runtime Config: Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) — statement/lock/idle transaction timeouts.
- [Prepared Statements](https://www.postgresql.org/docs/current/sql-prepare.html) — generic and custom plans.
- [DDL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — PK/FK/UNIQUE/CHECK.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS and privileges.
- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html) — `timestamp` vs. `timestamptz`.
- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) — `json`/`jsonb`.

**Java and Frameworks** (read documentation matching your deployed versions):

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — managed entities, persistence context, flush, queries.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — identifiers, fetch plans, batching, versioning.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — proxies, propagation, rollback, transaction managers.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repositories, projections, modifying queries.
- [PostgreSQL JDBC Driver](https://jdbc.postgresql.org/documentation/) — JDBC connections, prepared statements, PostgreSQL types.
- Connection pool documentation such as HikariCP matching your exact version and configuration.

Java snippets in this lesson are **conceptual illustrations**, not a standalone compiled project. SQL blocks are **theoretical lab exercises** not executed live while authoring this text. When implementing in production, test thoroughly against your exact driver, provider, framework, PostgreSQL version, and workload.

## 63. Summary

Keep the full stack clearly in mind:

```text
HTTP request
    |
    v
Spring service + @Transactional
    |
    +--> ORM persistence context
    |        |
    |        +--> entities/relations
    |        +--> dirty checking
    |        +--> flush
    |
    +--> JDBC/connection manager
    |        |
    |        +--> SQL / bind parameters
    |        +--> BEGIN/COMMIT/ROLLBACK
    |
    v
PostgreSQL
    |
    +--> MVCC/isolation
    +--> locks/concurrency
    +--> constraints/indexes
    +--> query planner/executor
    +--> WAL/commit
    |
    v
Durable result
```

Core principles:

1. **ORM does not eliminate SQL.** Inspect actual queries and PostgreSQL plans when tuning or verifying correctness.
2. **`save`, `flush`, and `commit` differ.** Having an ID or sending `INSERT` does not prove a transaction committed.
3. **`@Transactional` boundaries depend on proxies and transaction managers.** Self-invocation or spawning threads may silently miss expected transactions.
4. **Propagation modes have distinct semantics.** `REQUIRED` shares, `REQUIRES_NEW` isolates, and `NESTED` typically uses savepoints where supported.
5. **`READ COMMITTED` does not automatically stop lost updates.** Use `@Version`, atomic SQL predicates, or proper locks/protocols.
6. **Retries for serialization/deadlocks require fresh transactions.** Never blindly retry all errors or external side effects.
7. **One HTTP request does not equal one DB transaction.** Design boundaries carefully across multiple repositories, services, and external calls.
8. **Use unique constraints and idempotency keys** to protect against client retries and lost post-commit responses.
9. **Outboxes commit orders and event records atomically**, while external delivery still requires retries and consumer deduplication.
10. **N+1, fetch-join blowups, pagination, and batching must all be verified by observing real SQL.** Never guess from annotations.
11. **Observe both sides:** app SQL/traces alongside PostgreSQL `pg_stat_activity`, `pg_locks`, `pg_stat_statements`, and `EXPLAIN`.
12. **Lock and pool waits can dominate query plans.** Monitor transaction age, timeouts, and pool metrics.
13. **Schemas and constraints live in the database as the source of truth.** Use versioned migrations instead of letting entity annotations auto-alter production.
14. **SQL security still relies on `GRANT`, RLS, and parameter binding.** ORM never substitutes for tenant authorization or makes concatenated native SQL safe.
15. **Run integration tests against real PostgreSQL for PostgreSQL-specific behavior**, especially isolation, locking, `ON CONFLICT`, `RETURNING`, and SQLSTATEs.

### One Sentence to Remember

> **ORM helps build applications around object models; PostgreSQL still decides whether data is written accurately, isolated accurately, locked accurately, and committed durably.** Transaction boundaries must be designed deliberately, and actual SQL must be **observed and verified** rather than guessed from Java annotations.
