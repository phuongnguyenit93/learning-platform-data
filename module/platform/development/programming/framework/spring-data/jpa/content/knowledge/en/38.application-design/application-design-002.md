# Designing Aggregates and Consistent Update Boundaries

## Objectives

In Domain-Driven Design (DDD), an aggregate is a cluster of domain objects managed as a single unit of consistency. An aggregate has an **aggregate root** that serves as the external entry point. The root enforces business rules (invariants) that must always hold true when a transaction completes.

With Spring Data JPA, how you partition aggregates directly affects entity mappings, cascades, repositories, transactions, concurrency locking, and how multiple services coordinate. If an aggregate is too large, updates become heavy and prone to contention. If the boundary is too small, a single business rule can be split across multiple transactions and become hard to protect.

After this lesson, you will be able to:

- Distinguish between an entity, an aggregate, and an aggregate root.
- Identify aggregate boundaries from business consistency rules.
- Design JPA relationships so the root controls child entity lifecycles.
- Align repositories and transactions with aggregate boundaries.
- Distinguish intra-aggregate updates from coordination across multiple aggregates.
- Use optimistic locking and database constraints to protect concurrent updates.
- Choose between local transactions, the outbox pattern, or Sagas for business processes spanning multiple boundaries.
- Test invariants, mappings, and concurrent behavior.

## 1. What Is an Aggregate?

An **entity** has an identity and its own lifecycle. A **value object** is defined by its attributes, is usually immutable, and has no independent identity in the domain model.

An **aggregate** is a consistency boundary enclosing one or more entities and value objects. The aggregate root is the only entity that external code is allowed to use to request state changes to the aggregate.

For example, an order might consist of:

- PurchaseOrder: the root, with an order code and status.
- OrderLine: order line items, belonging to the order's lifecycle.
- Money or shipping address: value objects stored with the aggregate.

Rules such as "a confirmed order cannot have lines added" or "the total amount must equal the sum of line subtotals" are the responsibility of PurchaseOrder. External code should not modify OrderLine directly or manually assign the total amount in a way that bypasses the root's rules.

An aggregate is not simply every table connected by foreign keys. It is a **consistent update boundary**: which pieces of data must be checked and modified together to protect a business rule?

## 2. Identifying Boundaries from Invariants

Start by listing the rules that must hold true at the moment a transaction commits.

For example, with orders:

- An order must have at least one line before confirmation.
- The quantity of each line must be greater than 0.
- A confirmed order must not have its contents modified.
- The total amount must match the order lines.
- An inventory reservation must not exceed the remaining available quantity.

The first rules can belong to the same Order aggregate because they must be checked together when modifying an order. The inventory rule can belong to a separate InventoryItem aggregate because inventory is updated concurrently by many orders and has its own lifecycle.

Some helpful design questions:

1. Which attributes must change atomically so a rule always holds?
2. Who has authority to decide state transitions for an object?
3. Does a child object have independent meaning outside the root?
4. Are two pieces of data frequently updated by different requests?
5. Can an intermediate state and eventual consistency after a short time be tolerated?
6. If the whole group of data must be locked or loaded, is that scope too large?

Do not lump every entity with a JPA relationship into a single aggregate. An oversized aggregate increases the number of rows loaded, lock hold times, and the risk of two users colliding when editing unrelated parts.

Conversely, do not split a rule requiring atomicity across multiple aggregates just because they reside in two different tables. Boundaries should follow business logic and consistency requirements, not table counts.

## 3. The Aggregate Root Protects State

A simple order example:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    protected PurchaseOrder() {
    }

    public void addLine(
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {

        ensureDraft();

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Unit price must be non-negative");
        }

        OrderLine line = new OrderLine(
            this, productId, productName, unitPrice, quantity);

        lines.add(line);
        recalculateTotal();
    }

    public void removeLine(Long lineId) {
        ensureDraft();

        boolean removed = lines.removeIf(
            line -> line.hasId(lineId));

        if (!removed) {
            throw new IllegalArgumentException("Order line not found");
        }

        recalculateTotal();
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An order must contain at least one line");
        }

        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be changed");
        }
    }

    private void recalculateTotal() {
        totalAmount = lines.stream()
            .map(OrderLine::subtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Status enum:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Child entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(name = "product_name", nullable = false)
    private String productName;

    @Column(name = "unit_price", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    OrderLine(
            PurchaseOrder order,
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {
        this.order = order;
        this.productId = productId;
        this.productName = productName;
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    boolean hasId(Long lineId) {
        return id != null && id.equals(lineId);
    }
}
~~~

This example illustrates several key points:

- PurchaseOrder is the root; business code calls addLine, removeLine, and confirm.
- OrderLine has a non-public constructor to restrict arbitrary creation of child entities from outside the package.
- OrderLine holds a reference to the root and has the order_id foreign key.
- The root recalculates totalAmount when the line list changes. The total amount field also changes the root's state, allowing the root's version to participate in update control in this example.
- getLines() returns an unmodifiable copy that cannot be used to mutate the internal collection directly.

This is an illustrative model; a production project needs appropriate equals/hashCode implementations, handling for new lines without an ID yet, currency rules, scale/rounding, and its own business states. Do not use BigDecimal with double arithmetic for monetary calculations.

## 4. JPA Relationships Must Reflect Ownership

In the mapping above, OrderLine.order is the owning side of the relationship because it holds the order_id foreign key. PurchaseOrder.lines declares mappedBy = "order", making it the inverse side.

When adding a line, the root creates an OrderLine with a reference to `this` and adds it to the collection. Both sides of the relationship are thus synchronized in memory.

If you only add the line to the inverse collection without setting OrderLine.order, Hibernate may not write the foreign key as intended, or the database may reject it because order_id is null. A helper method on the root helps avoid forgetting to update the owning side.

**CascadeType.ALL** fits here because OrderLine belongs to the lifecycle of PurchaseOrder. Persisting the root can persist new lines; removing the root can remove dependent lines. **orphanRemoval = true** means that when a line is removed from the managed collection, that line can be deleted on flush.

Do not apply cascade remove from Order to Product just because OrderLine stores productId. Product belongs to a different aggregate and has an independent lifecycle. Similarly, do not use orphanRemoval for relationships where the child entity needs to exist independently or be shared.

## 5. Reference Other Aggregates by ID

Normally, one aggregate should reference another aggregate by identifier rather than holding an entire JPA object graph.

For example, OrderLine stores productId and a snapshot of productName/unitPrice at the time the order is placed. Order does not need to load the entire Product aggregate every time an order is read. A product's price may change later, while the order still needs to preserve the locked-in price.

Several benefits:

- Reduces object graph size and unnecessary joins.
- Prevents accidentally modifying another aggregate through a cascade relationship.
- Reduces coupling between modules and services.
- Clarifies which aggregate owns the update rules.

When current Product information is needed, the application can query the Product repository or a separate read model. If business logic requires checking price or inventory at order placement time, define the validation step clearly and decide how to handle data changing between read and write.

Not every JPA ManyToOne relationship represents a cross-aggregate reference. Within an aggregate, child entities can use direct object relationships. Between two aggregates, ID references usually make consistency boundaries clearer.

## 6. Repositories Usually Sit at the Aggregate Root

A repository provides a way to load and save an aggregate. Typically, create a repository for the root:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

The application service loads the root and invokes domain behavior:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orderRepository;

    public OrderApplicationService(
            PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void addLine(
            Long orderId,
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {

        PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        order.addLine(productId, productName, unitPrice, quantity);
    }

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        order.confirm();
    }
}
~~~

An entity loaded inside a transaction is managed. When the root changes, JPA dirty checking detects the changes and flushes when needed; it is not strictly necessary to call save() again just to update a managed entity.

There is no need to create an OrderLineRepository for routine add, edit, or delete line operations if OrderLine is managed solely through PurchaseOrder. If reporting queries or standalone line lookups are needed, a dedicated query/projection can be created, but the write path should still go through the root to protect invariants.

A repository should not become a place holding all business rules. It loads and saves aggregates; the root executes domain behavior; the application service orchestrates use cases and transactions.

## 7. Transaction Boundaries and a Single Aggregate

A transaction typically wraps a single use case in the application service:

1. Open the transaction.
2. Load the aggregate root.
3. Invoke domain behavior to validate and mutate state.
4. Flush/commit.
5. On error, roll back the transaction.

Rules that must hold true as soon as the transaction ends should be enforced in the root and/or database constraints. Do not return the root outside the transaction for a controller or background thread to mutate directly.

Technically, a local transaction can update multiple aggregate roots within the same database. However, if a use case frequently needs to load and modify multiple roots simultaneously, re-examine the boundaries: a rule may be placed in the wrong aggregate, or the process should become multi-step with eventual consistency.

Do not turn "one aggregate per transaction" into an inflexible law for every system. Use it as a design default to reduce coupling and contention; if business rules genuinely require an atomic update across multiple roots in the same database, document the rationale and test for conflicts.

## 8. Multiple Aggregates and Eventual Consistency

Suppose placing an order must reserve inventory. Order and InventoryItem can be two separate aggregates:

- Order manages order lines, total amount, and order status.
- InventoryItem manages available sellable quantity and reservations.
- Order does not directly modify quantity inside InventoryItem through an object graph.

There are two options depending on requirements:

**Atomic update in one database:** if both aggregates reside in the same database and business requirements demand they succeed or fail together, a local transaction can load and update both roots. This approach introduces coupling and contention between the two aggregates, so update frequency and lock scope must be evaluated.

**Multi-step process:** create Order in PENDING status, send a stock reservation request, and once Inventory confirms, transition Order to CONFIRMED. If reservation fails, transition Order to REJECTED or CANCELLED. Intermediate states are represented explicitly and the process achieves eventual consistency.

If two aggregates live in two different services/databases, `@Transactional` on a single service cannot atomically commit both local transactions. Use an outbox to publish events reliably and a Saga to coordinate forward/compensating steps when business logic requires it.

## 9. Invariants and Database Constraints

The root should validate business rules before changing state. Database constraints provide the last line of defense when there are multiple concurrent requests or different write paths.

For example:

- NOT NULL protects required fields.
- UNIQUE protects unique reference codes.
- FOREIGN KEY protects referential relationships.
- CHECK can enforce positive quantities or values within a valid range, depending on the database.

Not every invariant can be expressed by a CHECK constraint. Rules like "a confirmed order cannot have its lines modified" require state logic and appropriate update controls. Rules spanning multiple rows may require transactions, locks, or a different data model.

If you only check inventory by reading quantity in Java and then writing the new value, two transactions can read the same stale quantity simultaneously. Use optimistic/pessimistic locking or a conditional UPDATE so the check and modification are protected at the database level.

## 10. Optimistic Locking for the Aggregate Root

`@Version` can be placed on the root to detect two transactions modifying the same aggregate from the same version:

~~~java
@Version
private long version;
~~~

When the root is updated, the JPA provider typically issues an UPDATE with a condition on the old version and increments the version. If another transaction has committed first, the remaining update fails to match the version and raises an optimistic locking failure.

In the PurchaseOrder example, the add/remove line methods recalculate totalAmount, so the root's state also changes. In models where only a child entity changes and the root is not dirty, verify the version behavior of the provider and mapping. If the aggregate's invariants depend on every change in child entities, ensure those changes also increment the root's version or use an appropriate locking mechanism, such as optimistic force increment.

Error handling at the application boundary:

- Report the conflict to the caller or return HTTP 409.
- If a retry is appropriate, open a new transaction, reload the root, and recompute the behavior from the fresh state.
- Do not continue using stale entities in a transaction that has rolled back or been marked rollback-only.
- Do not retry external side effects without idempotency.

Optimistic locking is suitable when write conflicts are relatively infrequent. If contention is high, consider pessimistic locking on the root, keeping transactions short and handling timeouts/deadlocks.

## 11. Bulk Updates Can Break Aggregate Boundaries

JPQL bulk updates and native SQL update the database directly, bypassing domain behavior calls on the root. They can also bypass dirty checking, entity callbacks, and persistence context synchronization.

For example, updating the status of multiple orders directly could bypass the rule allowing transitions only from DRAFT to CANCELLED. If bulk updates are used, you must explicitly design the status conditions, versioning, auditing, events, and cache synchronization; do not assume root invariants will run automatically.

Bulk updates are appropriate for maintenance tasks or batch operations with clear rules when the designer deliberately reproduces the necessary guarantees. For normal business flows, loading the root and invoking domain behavior is safer.

## 12. Separating Command Models and Read Models

Aggregates are designed to protect updates, not necessarily as the optimal structure for every read query.

An order list screen might need customerName, totalAmount, status, and line count. Loading the entire aggregate with all relationships for every row can trigger N+1 queries and fetch excessive data.

A projection can be used instead:

~~~java
public interface OrderListView {
    Long getId();
    OrderStatus getStatus();
    BigDecimal getTotalAmount();
}
~~~

Or a dedicated DTO query with appropriate JPQL/native SQL. A read model can aggregate across multiple aggregates, but it should not be used to update domain state directly. Commands go through the aggregate root; queries can be optimized for reading needs.

If caching is used for read models, post-commit invalidation or event/outbox publishing is needed to keep read data up to date. Changing a single aggregate can affect multiple projections or cache keys.

## 13. Domain Events and Outbox at Aggregate Boundaries

After a business state change, the root or application service can emit a domain event, such as OrderConfirmed. The event describes what happened; other services can react to reserve stock, create a shipment, or send a notification.

If you merely publish an event directly after calling the repository, the process could crash between the database commit and publishing. To avoid losing events, write an outbox record in the same transaction as the aggregate change:

1. Load the Order root and call confirm().
2. Save the Order changes and the outbox event in the same local transaction.
3. Commit.
4. A worker publishes events from the outbox.
5. Consumers process events idempotently and record processed event IDs.

If the worker publishes successfully but crashes before marking the event as published, the message may be redelivered. Consumers should use eventId with a unique constraint/inbox to avoid applying the same business effect multiple times.

The outbox does not make multiple aggregates or multiple services commit atomically. It guarantees that the request to publish an event is stored durably alongside the source change, and then delivers the event under at-least-once semantics.

## 14. Testing Aggregates and Update Boundaries

Both domain behavior and persistence mappings should be tested.

**Unit tests for the root** without a database:

- Disallow adding lines once the order is confirmed.
- Reject zero or negative quantities.
- Reject confirming an empty order.
- Total amount updates accurately when adding or removing lines.
- Disallow removing a line that does not belong to the order.

**Repository/integration tests** using `@DataJpaTest`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void rootPersistsAndRemovesItsLines() {
        PurchaseOrder order = new PurchaseOrder();
        order.addLine(
            10L, "Keyboard", new BigDecimal("25.00"), 2);

        PurchaseOrder saved = orderRepository.save(order);
        entityManager.flush();
        Long orderId = saved.getId();

        entityManager.clear();

        PurchaseOrder loaded =
            orderRepository.findById(orderId).orElseThrow();

        assertThat(loaded.getLines()).hasSize(1);
        assertThat(loaded.getTotalAmount())
            .isEqualByComparingTo("50.00");
    }
}
~~~

This example focuses on cascade persist, the owning side, reloading after clear, and the total amount. To test orphanRemoval, load the root, remove a line through the root method, flush/clear, and verify the line is no longer in the database.

Other important tests:

- Database constraints reject invalid data.
- Two concurrent transactions update the same root; one transaction receives an optimistic locking conflict.
- Modifying a child entity through the root updates the root's version as designed.
- Projection queries do not load the entire aggregate.
- Conditional bulk updates do not violate invariants.
- Outbox events exist only when the business transaction commits.
- Consumers handle duplicate events safely.

Use Testcontainers or the same database engine as production to test locking, isolation, constraints, and dialect-dependent native queries. H2 can be suitable for fast tests, but it cannot substitute for every behavior of the deployed database.

## 15. Common Design Mistakes

1. **Aggregate too large:** loads too many entities, holds locks for too long, and causes conflicts between unrelated changes.
2. **Allowing direct child entity modification:** bypasses invariants that the root must protect.
3. **Creating repositories for every child entity:** makes it easy for external code to update children without going through the root.
4. **Cascade ALL to another aggregate:** accidentally extends or deletes the lifecycle of an independent object.
5. **Using JPA relationships for every reference:** creates huge object graphs and unnecessary coupling; consider ID references between aggregates.
6. **Treating `@Transactional` as multi-service consistency:** local transactions only protect resources managed by the transaction manager.
7. **Checking version only on the child:** may fail to protect root-level invariants if the root is not marked dirty or locked appropriately.
8. **Using bulk updates for business commands:** bypasses domain behavior, callbacks, and some concurrency mechanisms.
9. **Using aggregates as read models for every screen:** easily causes N+1 queries and loads superfluous data.
10. **Publishing events unreliably:** database commits, yet the message is lost if the process crashes before publishing.

## 16. Practical Design Workflow

When adding a new use case, you can follow this order:

1. Clearly write down the invariants that must hold true when the transaction finishes.
2. Identify which entity owns and protects each invariant.
3. Choose the root and limit which entities/value objects live inside the aggregate.
4. Design domain methods so all changes go through the root.
5. Map JPA according to true lifecycles: owning side, cascade, and orphanRemoval only when appropriate.
6. Create a repository for the root and place transactions in the application service.
7. Define concurrency rules: `@Version`, locks, or conditional UPDATEs.
8. For processes spanning multiple aggregates/services, choose local transactions, outbox, or Sagas and model intermediate states.
9. Separate read models from command models when query needs diverge from the aggregate structure.
10. Write unit tests for invariants and integration tests for mappings, transactions, and concurrency.

A good aggregate keeps rules that must remain consistent together inside a manageable update boundary. Spring Data JPA provides entity lifecycle management, transactions, and locking to implement that boundary; DDD helps decide which data belongs under the same root and when coordination via events or compensation is required.