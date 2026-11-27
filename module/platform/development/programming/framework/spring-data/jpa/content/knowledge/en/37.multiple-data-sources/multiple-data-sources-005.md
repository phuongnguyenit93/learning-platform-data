# Atomicity Limitations When Updating Multiple Data Sources

A Spring Data JPA application can connect to multiple databases, each with its own `DataSource`, `EntityManagerFactory`, and transaction manager. Configuring multiple data sources helps separate business domains, data, or access loads. However, a local JPA transaction typically protects only operations on the data source managed by that specific transaction manager.

If a business operation updates two databases—for example, deducting inventory in a warehouse database and creating an order in a sales database—placing a single `@Transactional` annotation does not automatically guarantee that both changes commit or roll back together. This is a critical limitation on atomicity when working with multiple data sources.

## 1. A local transaction manages only a single resource

In a typical configuration, each `JpaTransactionManager` is bound to a single `EntityManagerFactory`. It manages transactions for the corresponding persistence context and database.

For example, suppose an application has two databases:

- `ordersDataSource`: stores orders.
- `inventoryDataSource`: stores stock quantities.

You can configure two separate repository sets, each using the appropriate EntityManager and transaction manager. When invoking a method:

```java
@Transactional("ordersTransactionManager")
public void createOrder() {
    // Operations through OrdersEntityManagerFactory
}
```

the selected transaction manager only manages transactions for the orders database. It does not automatically enlist operations going through `inventoryEntityManagerFactory` into the same transaction.

Similarly:

```java
@Transactional("inventoryTransactionManager")
public void reserveStock() {
    // Operations through InventoryEntityManagerFactory
}
```

This is another local transaction. Each transaction can commit or roll back independently.

**Key takeaway:** `@Transactional` defines a transaction boundary according to the chosen transaction manager. It does not mean every database connected to the application participates in that transaction.

## 2. Why can a business operation only half-succeed?

Suppose an order placement flow consists of two operations:

1. Write the order to the Orders database.
2. Deduct the product quantity in the Inventory database.

If the two operations run under two local transaction managers, the following sequence can occur:

```text
Orders DB:     BEGIN -> INSERT order -> COMMIT
Inventory DB:  BEGIN -> UPDATE stock -> ERROR -> ROLLBACK
```

The result is that the order exists, yet inventory was not deducted. If the order is reversed, the opposite situation can happen: inventory is reduced, yet the order is never created.

A service method may call two sub-services, each annotated with `@Transactional` for its own manager. That still does not create a distributed transaction. The first database's transaction can commit before the second transaction completes. If the second transaction fails, the first transaction does not automatically roll back.

Nor should `Propagation.REQUIRES_NEW` be mistaken for a way to merge multiple databases into one transaction. `REQUIRES_NEW` creates an independent transaction within the selected transaction manager; it provides no atomic commit mechanism across different managers.

## 3. Configuring multiple transaction managers explicitly

When there are multiple datasources, name each transaction manager clearly and specify the appropriate manager in services or repositories.

Example illustrating selecting a transaction manager per domain:

```java
@Service
public class OrderWriter {

    private final OrderRepository orderRepository;

    public OrderWriter(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional("ordersTransactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

```java
@Service
public class InventoryWriter {

    private final InventoryRepository inventoryRepository;

    public InventoryWriter(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional("inventoryTransactionManager")
    public void reserve(Long productId, int quantity) {
        Inventory item = inventoryRepository.findById(productId)
                .orElseThrow();

        item.reserve(quantity);
    }
}
```

The names `ordersTransactionManager` and `inventoryTransactionManager` must match the actual beans in the application configuration. Each repository must also be bound to the right `EntityManagerFactory` and transaction manager for its datasource, typically via separate `@EnableJpaRepositories` configurations.

The example above illustrates two independent transaction boundaries. If an orchestrating service calls both writers, that orchestrating service cannot make the two local transactions atomic merely by adding `@Transactional` to itself.

When configuring multiple data sources, avoid relying on a default transaction manager if a method could operate across multiple domains. Explicitly specifying the manager helps readers identify which database is protected by that transaction.

## 4. Option 1: Use JTA/XA when atomic commit is truly required

If the business strictly requires two databases to commit or roll back together, consider a distributed transaction using JTA combined with XA.

A JTA transaction manager acts as the coordinator of a global transaction. Participating resources must support XA and be enlisted into the global transaction. With JPA, the configuration must use JTA-compatible resources/EntityManagerFactories and transaction integration. Simply having two datasources or two separate JpaTransactionManagers is not enough.

### How two-phase commit works

Two-phase commit (2PC) has two main phases:

1. **Prepare:** the coordinator asks each resource participant to prepare to commit. Each database verifies its ability to complete and writes the prepared state according to the XA protocol.
2. **Commit or roll back:** if all participants prepare successfully, the coordinator instructs all of them to commit. If any participant fails to prepare, the coordinator instructs a rollback per the protocol outcome.

Conceptual diagram:

```text
Application
    |
    v
JTA Transaction Manager (Coordinator)
    |
    +---- prepare ----> Orders DB (XA)
    |
    +---- prepare ----> Inventory DB (XA)
    |
    +---- commit -----> Orders DB
    |
    +---- commit -----> Inventory DB
```

When using JTA, the application typically declares transactions using the configured global transaction manager:

```java
@Transactional
public void placeOrder(Order order, Long productId, int quantity) {
    orderRepository.save(order);
    inventoryRepository.reserve(productId, quantity);
}
```

This code only acts as a global transaction when both repositories genuinely participate in the same JTA transaction. If they still use two local `JpaTransactionManager` beans, this annotation does not produce 2PC.

### Conditions and trade-offs of XA

- The database and JDBC driver must support XA for the resources used.
- Connection pools and datasources must be configured for XA; regular JDBC datasources do not automatically become XA resources.
- The application requires a JTA coordinator, resource enlistment configuration, and recovery mechanisms after process or node failures.
- Global transactions add extra network round-trips and prepare/commit steps, increasing latency.
- Resources may hold locks or prepared states while waiting for the coordinator to finish, affecting throughput and availability.
- When the coordinator or network fails, recovering transactions requires durable logs and proper recovery procedures. Certain rare situations can produce heuristic outcomes requiring operational intervention.

XA is appropriate when cross-database atomicity is mandatory, all systems support XA, and the organization accepts the operational overhead. Do not choose XA merely because an application has multiple datasources.

## 5. Option 2: Transactional Outbox and eventual consistency

In many systems, databases do not need to commit at the exact same instant. What matters is that the change in the primary data source and the intent to synchronize to another source are never lost. Transactional outbox is a popular option.

Suppose Orders DB is the primary source of truth when placing an order. Within the same local transaction, the application:

1. Saves the order in `PENDING` state.
2. Inserts a record into the `outbox_event` table describing the stock reservation request.
3. Commits both the order and the outbox event together.

A background publisher reads unsent events and forwards them to a message broker or a worker handling Inventory DB. The worker updates stock in a local transaction on Inventory DB and records the processed event. Once stock reservation succeeds, a response event can be sent back to update the order to `CONFIRMED`. If stock is insufficient, the order can transition to `REJECTED`.

Example flow:

```text
Orders DB transaction
    |
    +-- INSERT order (PENDING)
    |
    +-- INSERT outbox event (ReserveStock)
    |
    +-- COMMIT
             |
             v
       Outbox publisher
             |
             v
        Message broker
             |
             v
Inventory DB transaction
    |
    +-- Reserve stock
    |
    +-- Record processed event
    |
    +-- COMMIT
             |
             v
       Reservation result
             |
             v
Orders DB: CONFIRMED / REJECTED
```

Outbox eliminates the dangerous gap between committing Orders data and persisting the intent to publish a message: if the Orders transaction rolls back, the outbox row rolls back too; if it commits successfully, the event remains durable for the publisher to resend after a crash.

This is eventual consistency. For a brief window, Orders DB may be in `PENDING` while Inventory DB has not yet processed the request. The application must model intermediate states and only report business completion after receiving the appropriate outcome.

## 6. Designing idempotent consumers and handling duplicate deliveries

Transactional outbox does not guarantee the broker receives a message exactly once. For example, the publisher may send a message successfully, but the process crashes before marking the outbox row as sent. Upon restart, the publisher may send that message again.

Therefore, consumers must be idempotent. A common technique is assigning a unique `eventId` and storing processed IDs in the same transaction as the business change in the destination database.

Example processed-events table:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Consumer flow:

1. Receive message and extract `eventId`.
2. Begin a transaction in the destination database.
3. Attempt to insert `eventId` into `processed_event`.
4. If the ID already exists, treat it as a duplicate message and do not apply the change again.
5. If the ID is new, perform the business update in the same transaction.
6. Commit before acknowledging the message to the broker.

The primary key constraint lets the database handle concurrency when two consumers receive the same event simultaneously. If recording the processed marker and updating stock occurred in two separate transactions, the system could still mark an event complete while the stock update failed, or vice versa.

Idempotent consumers safely handle message redeliveries. This does not magically create system-wide exactly-once delivery; the practical goal is at-least-once delivery combined with effectively-once processing by event ID.

## 7. Using Saga and compensating actions for multi-step workflows

A business process spanning multiple steps across multiple databases or services is often modeled as a Saga. Each step is a local transaction. If a later step fails, the workflow runs compensating actions to bring the system back to an acceptable business state.

Order placement example:

| Step | Local Transaction | Compensation When Needed |
|---|---|---|
| 1 | Create order in PENDING state | Cancel order |
| 2 | Reserve stock in inventory | Release reserved quantity |
| 3 | Charge payment | Issue refund |
| 4 | Confirm order | Transition to manual-intervention state if unable to complete |

Compensation is not necessarily a physical rollback. If a payment has already been submitted to an external payment gateway, that event cannot be erased from history; the system must issue a new refund transaction.

A Saga needs to persist workflow state, step identifiers, outcomes, retry counts, and error details so it can resume after a process restart. Steps must be idempotent because messages or commands can be redelivered. Timeouts, bounded retries, dead-letter queues or manual intervention queues, and reconciliation mechanisms are needed for cases that cannot self-recover.

Saga fits when the business accepts intermediate states and must coordinate long-running multi-step flows. It does not provide instantaneous atomic rollback like a local database transaction.

## 8. Choosing a strategy based on business requirements

| Requirement | Suitable Strategy |
|---|---|
| An operation updates only one database | Local transaction with JpaTransactionManager |
| Two databases must commit/roll back together and both support XA | JTA/XA two-phase commit |
| Need to sync to another database, intermediate states acceptable | Transactional outbox and idempotent consumer |
| Multi-step workflow needing compensation when a later step fails | Saga |
| Data is replicated or aggregated periodically, latency acceptable | Sync job, CDC, or appropriate reconciliation process |

Before choosing, answer these questions:

- Which database is the primary source of truth for each piece of data?
- Are intermediate states acceptable to the business?
- If one database succeeds and the other fails, what must happen?
- Can messages be redelivered, and are consumers idempotent?
- Is simultaneous commit mandatory, or is converging to the right state sufficient?
- Does the system support XA, and can operations handle recovery?

If two databases belong to two independent business domains, it is usually best to let each domain own its local transactions and communicate via events/commands. Only use distributed transactions when true atomicity is genuinely required and fully supported.

## 9. Common mistakes

- **Assuming one `@Transactional` covers every datasource:** the annotation uses only the selected transaction manager. Identify the actual manager and resources of each repository.
- **Calling two services with two transaction managers and expecting joint rollback:** two local transactions commit independently. Choose XA or design outbox/Saga as required.
- **Using `REQUIRES_NEW` to create a cross-database transaction:** this propagation only creates a new transaction for the current manager; it does not coordinate multiple resources.
- **Publishing a message before the source transaction commits:** consumers might process a change that the source database subsequently rolls back. Write to outbox in the same transaction and publish after commit.
- **Marking outbox as sent before broker acknowledgement:** events can be lost if the publisher crashes. Design delivery state and retries carefully.
- **Not guarding against duplicate processing:** publishers or brokers can redeliver. Use event IDs, unique constraints, and idempotent consumers.
- **Treating compensation as rollback:** compensation is a new business operation that can itself fail and require retries or manual intervention.
- **Using XA without recovery:** a coordinator can leave transactions in a prepared state during outages. Configure durable logs and test recovery procedures.

## 10. Key takeaways

A Spring Data JPA local transaction typically manages only one `EntityManagerFactory` and datasource. Multiple `@Transactional` annotations with different managers do not automatically create cross-database atomicity. If simultaneous commit is strictly required, use JTA/XA with supporting resources and complete recovery configuration. If eventual consistency is acceptable, transactional outbox, idempotent consumers, and Saga typically coordinate multiple data sources in a more scalable and operable manner.