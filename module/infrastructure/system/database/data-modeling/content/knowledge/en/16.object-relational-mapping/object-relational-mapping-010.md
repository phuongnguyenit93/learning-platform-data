# Keeping the Domain Model Independent of ORM Details Within Reasonable Bounds

**ORM (Object–Relational Mapping)** maps objects in a program to tables, columns, and relationships in a relational database. Tools like JPA/Hibernate can reduce manual SQL boilerplate, manage object identity, and support transactions. However, letting ORM characteristics dictate the entire business model makes the codebase hard to test, hard to change, and sometimes **semantically wrong about the data**.

For example, an order may transition from **DRAFT** to **PLACED** only when it has at least one order line. That is a **domain invariant**, not a Hibernate rule. Conversely, **@Entity**, **fetch = LAZY**, **@JoinColumn**, **EntityManager**, or proxy mechanics are storage details. Separating these two sets of responsibilities is the foundation of **persistence ignorance**: the domain model does not need to understand persistence mechanics to express and enforce business behavior.

This lesson belongs to the **Object Mapping** chapter of the **DATABASE_DATA_MODELING** module. The goal is learning how to build boundaries between the domain model, relational model, and ORM **pragmatically**: separate where separation pays off, accept framework coupling where reasonable, and always verify the design with keys, foreign keys, constraints, joins, transactions, and real behavior.

## 1. What Does ORM Independence Actually Mean?

A domain model achieves appropriate independence when:

1. **Names and behavior come from the business domain**: Order, OrderLine, place(), cancel(), quantity, unitPriceAtOrder—not from lazy proxy mechanics or table names.
2. **Invariants live close to the object that owns them**: cannot place an empty order, cannot add a negative quantity, cannot modify a placed order per example rules.
3. **Domain unit tests require no database connection**: you can construct plain Java objects and test state transitions.
4. **Domain code does not call EntityManager or SQL**: data access belongs to a repository port, application service, or adapter.
5. **The relational schema is still designed rigorously**: keys, functional dependencies, history, referential constraints, indexes, and transactions are never treated as "ignorable details."

This does **not** mean the domain model can ignore that information must persist durably, that operations spanning multiple aggregates need transactions, or that reading thousands of rows has a cost. "Independence" means **limiting the spread of implementation details**, not denying data constraints and performance limits.

### 1.1. Classifying Responsibilities

| Responsibility | Appropriate Layer | Example |
| --- | --- | --- |
| Defining entities and domain rules | Domain | Cannot place an empty order; line quantity must be positive |
| Coordinating a use case | Application | Load order, call **place()**, save result, return response |
| Transaction boundaries | Application/infrastructure | An order placement operation must commit or roll back atomically |
| Object–row mapping | Persistence adapter | Map Order to **orders** and OrderLine to **order_lines** |
| Keys, foreign keys, CHECK, and indexes | Database schema | **PRIMARY KEY (order_id, line_no)**; **CHECK (quantity > 0)** |
| API response data shape | Presentation/read model | **OrderDetailsResponse** DTO, never returning ORM proxies directly |

Important rules can be protected **at multiple layers**. For example, **quantity > 0** is checked when constructing `OrderLine` for clear domain error messages, and also enforced by **CHECK** in the database to block other write paths. This is **defense in depth**, not harmful redundancy to strip away.

## 2. Why Can Using an ORM Entity Directly as the Domain Model Cause Problems?

A JPA class can easily balloon into an object carrying every responsibility:

~~~java
@Entity
class OrderEntity {
    @Id
    private UUID id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

This snippet only illustrates mapping and defines no domain invariants. If application services manipulate it via public setters, one place can set **status = PLACED** while **lines** is empty, while another calls **lines.clear()** on an already placed order. The database can end up persisting states that violate business rules.

Common risks:

- **Anemic domain model**: entities hold only getters/setters; business rules scatter across services and controllers.
- **ORM leak**: business logic must know when associations are lazily loaded, or whether a session is open or closed.
- **N+1 queries**: looping over collections causes a domain operation to accidentally emit many queries.
- **Mapping convenience overrides domain semantics**: modeling a one-to-many solely because it is easy to map, even though the true grain is a many-to-many with its own attributes.
- **ORM lifecycle dictates behavior**: stuffing all logic into callbacks like **@PrePersist** or relying on dirty checking for domain conditions to "just happen."
- **Hard to unit-test pure logic**: invoking a simple rule requires booting a Spring context, EntityManager, or database.

Nevertheless, **not every JPA entity with domain behavior is wrong**. For simple CRUD applications, mapping directly onto domain objects can avoid extra translation layers while still protecting invariants with domain methods rather than open setters. Splitting domain entities from persistence entities is a **cost–benefit decision**, not dogma.

## 3. Typical Boundaries: Domain, Use Cases, and Persistence Adapters

A structure following **Ports & Adapters**:

~~~mermaid
flowchart TD
    UI["HTTP API / CLI / Consumer"]
    APP["Application: PlaceOrder"]
    PORT["OrderRepository (port)"]
    DOM["Domain: Order, OrderLine, invariant"]
    ADAPTER["Persistence adapter: JpaOrderRepository"]
    ORM["JPA / Hibernate"]
    DB[("Relational Database")]
    UI --> APP
    APP --> DOM
    APP --> PORT
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> ORM
    ORM --> DB
~~~

**Source code dependency direction** should stay clear:

- Domain depends on standard Java libraries and domain concepts, **not** on JPA/Hibernate if pure domain is intended.
- Application depends on domain and **persistence ports** defined in domain terms.
- Persistence adapter depends on application/domain and the ORM framework.
- Web/API maps requests/responses to commands/DTOs without depending on ORM proxy state.

A port sanity check: an interface named **OrderRepository** that returns **Page<OrderJpaEntity>** or accepts **Specification<JpaEntity>** or **EntityManager** still leaks ORM details to callers. In a pure-JPA system, Spring Data APIs inside the adapter are acceptable, yet should not be mistaken for an ORM-independent abstraction.

## 4. Running Example: Placing an Order

Rules in this example:

1. An order is identified by **order_id** (UUID).
2. An order line is identified by **(order_id, line_no)**; `line_no` is unique only **within the order**.
3. An order in **DRAFT** status may have zero lines.
4. Lines can only be added while the order is **DRAFT**. Quantity must be positive; VND unit price at ordering time must be non-negative.
5. **place()** is permitted only when a DRAFT order has at least one line; it transitions the order to **PLACED**.
6. A PLACED order must not have lines arbitrarily added via this use case.
7. A line's unit price is a **transaction snapshot**, unaffected retroactively by changes to the product's current catalog price.

This is an **intentionally scoped** version: it does not model taxes, promotions, cancellations, returns, split shipments, or multi-stream concurrent ordering. Rules in this version must not be generalized as invariants for every sales system.

### 4.1. Relational Model — Independent of Whether an ORM Is Used

~~~sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'PLACED')),
    version BIGINT NOT NULL DEFAULT 0
        CHECK (version >= 0)
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Here:

- One **orders** row is one order; one **order_lines** row is one line of that order.
- **PRIMARY KEY (order_id, line_no)** protects line identity; do not replace `line_no` with `product_id` because the same product can appear on multiple lines.
- **version** is for **optimistic locking**, **not** a domain field representing business state.
- **CHECK** protects row-level conditions, yet **does not** automatically enforce "a PLACED order has at least one line" or "no lines added once PLACED." Those two rules must be guarded in write paths and transactions; if other writers exist, equivalent safeguards must exist at the data boundary.

The schema is the contract for durable data. An ORM is merely one implementation for reading and writing against that contract.

### 4.2. Value Object `OrderLine` in Plain Java

~~~java
package example.domain;

import java.util.Objects;
import java.util.UUID;

public record OrderLine(
        int lineNo,
        UUID productId,
        int quantity,
        long unitPriceVnd
) {
    public OrderLine {
        if (lineNo <= 0) {
            throw new IllegalArgumentException("lineNo must be positive");
        }
        Objects.requireNonNull(productId, "productId");
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("price cannot be negative");
        }
    }

    public long lineTotalVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}
~~~

`OrderLine` in this example is a **value object within the `Order` aggregate**: it has no lifecycle independent of the order, and **lineNo** positions the element inside one order. In another application, an order line might be a **child entity** with its own durable ID and behavior. Decide from business lifecycle, not just because JPA needs **@Id**.

Because VND is represented as an integer in this example, **long** avoids `double` decimal rounding errors, and **Math.multiplyExact** detects overflow. For multiple currencies, fractional amounts, taxes, or complex rounding, use a **Money value object** with explicit currency, precision, and rounding policies rather than inferring from Java primitives.

### 4.3. Aggregate `Order` Protecting State

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class Order {
    public enum Status { DRAFT, PLACED }

    private final UUID id;
    private final List<OrderLine> lines = new ArrayList<>();
    private Status status;

    public Order(UUID id) {
        this.id = Objects.requireNonNull(id);
        this.status = Status.DRAFT;
    }

    // Used when reconstituting an aggregate from persisted data.
    public static Order restore(
            UUID id, Status status, Collection<OrderLine> savedLines
    ) {
        Objects.requireNonNull(status);
        Objects.requireNonNull(savedLines);
        Order order = new Order(id);
        for (OrderLine line : savedLines) {
            if (order.lines.stream()
                    .anyMatch(x -> x.lineNo() == line.lineNo())) {
                throw new IllegalStateException("duplicate line number");
            }
            order.lines.add(Objects.requireNonNull(line));
        }
        if (status == Status.PLACED && order.lines.isEmpty()) {
            throw new IllegalStateException("placed order has no lines");
        }
        order.status = status;
        return order;
    }

    public UUID id() { return id; }
    public Status status() { return status; }
    public List<OrderLine> lines() { return List.copyOf(lines); }

    public void addLine(OrderLine line) {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("order already placed");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("duplicate line number");
        }
        lines.add(line);
    }

    public void place() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("order already placed");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("cannot place empty order");
        }
        status = Status.PLACED;
    }
}
~~~

Inside **Order** there is no **@Entity**, **EntityManager**, **@Transactional**, or SQL call. You can instantiate `Order` and invoke **addLine()/place()** directly in a unit test. Terms like "order already placed," "line number," and "duplicate line number" belong to the business domain; they do not change when switching from JPA to a JDBC adapter or another storage engine.

The **restore(...)** factory reconstructs the object from stored data and checks invariants **per the modeled domain version**. In production systems, establish a clear strategy for legacy data predating new rules, and avoid using reconstitution helpers to perform business state transitions that require workflow checks. Here, external collection mutation is blocked because **lines()** returns an immutable copy.

## 5. Repository Port: Speaking the Domain Language

A simple persistence port:

~~~java
package example.domain;

import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {
    Optional<Order> findById(UUID id);
    void save(Order order);
}
~~~

The application does not need to know whether `Order` is stored across two tables, mapped with **@OneToMany**, or queried via JDBC:

~~~java
package example.application;

import example.domain.Order;
import example.domain.OrderRepository;
import java.util.UUID;

public final class PlaceOrder {
    private final OrderRepository repository;

    public PlaceOrder(OrderRepository repository) {
        this.repository = repository;
    }

    public void execute(UUID orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("order not found"));
        order.place();
        repository.save(order);
    }
}
~~~

**PlaceOrder** orchestrates a use case; **Order.place()** decides whether the order can be placed. If the system needs credit checks, inventory checks, or policies involving other aggregates, the application service can call the corresponding service ports; never cram unrelated data into `Order` merely to avoid another repository call.

**The transaction boundary** must span **load → validate/mutate state → save**, rolling back on error. In Spring, **@Transactional** can sit on the application service or on an infrastructure wrapper/decorator invoking the use case. Putting a framework annotation on the application service is **a pragmatic trade-off**; if strict isolation is desired, put transaction management on the decorator so the use-case class remains plain Java. A repository port by itself **does not create a transaction**.

## 6. Persistence Adapter: JPA Handles Mapping, Not Order Placement Rules

When separating the domain from the ORM, we have two models with distinct goals:

- **Domain Order**: expresses behavior, state, values, and order invariants.
- **Persistence rows**: expresses how rows in **orders** and **order_lines** are identified, loaded, and updated by JPA.

Having two object representations holding corresponding data is an **intentional layering cost**. The goal is not eliminating all syntactic repetition, but preventing *lazy proxies*, no-arg constructors, and cascades from dictating domain behavior.

### 6.1. A JPA Entity Strictly for `orders` Rows

Illustrative JPA code using **Jakarta Persistence**:

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class OrderJpaRow {
    @Id
    @Column(name = "order_id", nullable = false)
    private UUID id;

    @Column(name = "status", nullable = false, length = 16)
    private String status;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected OrderJpaRow() {}  // JPA requires a no-arg constructor.

    public OrderJpaRow(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID id() { return id; }
    public String status() { return status; }

    public void updateStatus(String newStatus) {
        this.status = newStatus;
    }
}
~~~

In this example, there is no **@OneToMany** on **OrderJpaRow**. Lines are loaded with an explicit query to avoid forcing a proxied collection into the domain. That is **a design choice**, not a ban on **@OneToMany**: ORM relationships remain useful when lifecycles and fetch plans align.

**@Version** lets JPA detect certain concurrent updates modifying the **orders** row using an ORM-managed version counter. Technically, the version field here belongs to the **persistence row**; the domain does not have to expose **setVersion(...)** solely for the ORM.

### 6.2. Mapping the Composite Key of Order Lines

In SQL, the key of **order_lines** is **(order_id, line_no)**. The persistence adapter can map this key with **@EmbeddedId**:

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

@Embeddable
public class OrderLineKey implements Serializable {
    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    @Column(name = "line_no", nullable = false)
    private int lineNo;

    protected OrderLineKey() {}

    public OrderLineKey(UUID orderId, int lineNo) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNo = lineNo;
    }

    public UUID orderId() { return orderId; }
    public int lineNo() { return lineNo; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineKey that)) return false;
        return lineNo == that.lineNo &&
               Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
~~~

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "order_lines")
public class OrderLineJpaRow {
    @EmbeddedId
    private OrderLineKey id;

    @Column(name = "product_id", nullable = false)
    private UUID productId;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price_vnd", nullable = false)
    private long unitPriceVnd;

    protected OrderLineJpaRow() {}

    public OrderLineJpaRow(
            OrderLineKey id, UUID productId,
            int quantity, long unitPriceVnd
    ) {
        this.id = id;
        this.productId = productId;
        this.quantity = quantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public OrderLineKey id() { return id; }
    public UUID productId() { return productId; }
    public int quantity() { return quantity; }
    public long unitPriceVnd() { return unitPriceVnd; }
}
~~~

The composite key in persistence is a **mapping expression** of the same fact the domain knows: `lineNo` is unique only **within one Order**. The domain `OrderLine` above neither carries **@EmbeddedId**, implements **Serializable**, nor needs a no-arg constructor.

If the table chooses a surrogate **line_id** primary key with **UNIQUE(order_id, line_no)**, the persistence adapter can map differently. Yet the uniqueness rule for `lineNo` per order must still be protected; adding a surrogate key does not replace business constraints.

### 6.3. Mapper Reconstituting the Domain from Rows

The mapper bridges the two worlds:

~~~java
package example.persistence;

import example.domain.Order;
import example.domain.OrderLine;
import java.util.List;

public final class OrderMapper {
    public Order toDomain(
            OrderJpaRow header, List<OrderLineJpaRow> rows
    ) {
        List<OrderLine> lines = rows.stream()
                .map(row -> new OrderLine(
                        row.id().lineNo(),
                        row.productId(),
                        row.quantity(),
                        row.unitPriceVnd()
                ))
                .toList();

        return Order.restore(
                header.id(),
                Order.Status.valueOf(header.status()),
                lines
        );
    }
}
~~~

The mapper **does not** decide when **place()** is allowed. It reconstitutes data and can raise an error if stored data violates an invariant—such as a `PLACED` order with zero lines. Have a strategy for legacy/invalid data before tightening domain rules; never silently ignore discrepancies.

### 6.4. Adapter Loading the Full Aggregate Before Executing Behavior

A read method in the JPA adapter can issue two explicit queries:

~~~java
// Excerpt from JpaOrderRepository, inside an active transaction.
public Optional<Order> findById(UUID id) {
    OrderJpaRow header = em.find(OrderJpaRow.class, id);
    if (header == null) {
        return Optional.empty();
    }

    List<OrderLineJpaRow> rows = em.createQuery(
            "select l from OrderLineJpaRow l " +
            "where l.id.orderId = :orderId " +
            "order by l.id.lineNo",
            OrderLineJpaRow.class
    ).setParameter("orderId", id).getResultList();

    return Optional.of(mapper.toDomain(header, rows));
}
~~~

This is an **illustrative excerpt**: **em** is an adapter-managed EntityManager and **mapper** is OrderMapper. It is not a standalone runnable Java file.

The returned `Order` contains plain Java data, **no JPA proxies**. Hence when the use case calls **order.lines()** or **order.place()**, the behavior never triggers surprise SQL. It is the repository's responsibility to load everything the behavior needs before exiting the persistence boundary.

**Important:** when the application mutates an aggregate, **save(Order)** must synchronize **all affected state** (both header and lines), not merely update status in every case. You can implement this by diffing lines by **(order_id, line_no)** and inserting/updating/deleting changed rows, or using another controlled update strategy. Never write a method named **save** that silently drops line changes.

### 6.5. Which Parts Are ORM-Specific?

| Responsibility | Concrete Example | Should It Enter the Domain? |
| --- | --- | --- |
| JPA managed/detached states | Persistence context, merge, flush | No |
| Building domain objects from rows | Mapper, reconstitution checks | Not necessarily; keep in adapter |
| Placing an order requires lines | **Order.place()** | **Yes, it is domain behavior** |
| Line quantity is positive | **OrderLine** and DB **CHECK** | **Yes** in domain, **and also** in DB |
| Wiring child records to parent | @OneToMany, @MapsId, @EmbeddedId | No |
| Paginated order list search | Query object, projection, indexes | Primarily application/read adapter |
| Whether a product can be added to an order | Business policy and related data | Domain/application, not ORM callbacks |

Separating the two models **limits where changes land when mappings shift**. For instance, switching `order_lines` to a surrogate key does not force domain **OrderLine** to gain a **jpaLineId** field as long as the business identifier `lineNo` stays unchanged.

## 7. Transactions, Concurrency, and Persistence Lifecycles

ORM independence does not mean concurrency issues vanish automatically. Two users reading the same `DRAFT` order and adding lines simultaneously can cause **lost updates** or violate invariants without transaction control.

### 7.1. Place Transactions at the Use-Case Boundary

Example:

~~~text
HTTP POST /orders/{id}/place
    -> PlaceOrder.execute(id)
        -> repository.findById(id)
        -> order.place()
        -> repository.save(order)
    -> COMMIT
~~~

You need **one transaction wrapping** the entire load–validate–save cycle, rolling back on error. Putting separate transactions around **findById** and **save** fails to preserve consistency between the two steps.

In Spring, a pragmatic implementation may use a wrapper:

~~~java
package example.infrastructure;

import example.application.PlaceOrder;
import java.util.UUID;
import org.springframework.transaction.annotation.Transactional;

public final class TransactionalPlaceOrder {
    private final PlaceOrder useCase;

    public TransactionalPlaceOrder(PlaceOrder useCase) {
        this.useCase = useCase;
    }

    @Transactional
    public void execute(UUID orderId) {
        useCase.execute(orderId);
    }
}
~~~

In a real app, the wrapper must be managed as a Spring bean and invoked **through the transaction proxy/interceptor**, not via self-invocation that bypasses proxying. This snippet shows responsibility placement rather than a full Spring setup.

This illustrates **source-dependency independence**: **PlaceOrder** does not import Spring, while the infrastructure layer decides how transactions open. For small projects, placing **@Transactional** directly on the application service can also be reasonable when simplicity outweighs strict framework isolation. A repository port by itself **does not create a transaction**.

### 7.2. Optimistic Locking with `@Version`

Suppose two transactions T1 and T2 both load order version **5**:

~~~text
T1 reads Order(version=5, status=DRAFT)
T2 reads Order(version=5, status=DRAFT)

T1 places the order (PLACED) and commits -> new version 6.
T2 also attempts to update based on version 5.
=> ORM detects version conflict and rejects one write.
~~~

**@Version** on **OrderJpaRow** is the standard persistence mechanism for preventing *lost updates* on the root row. The application must decide: return an error to the user, reload and retry **safely**, or ask the user to re-submit. Never auto-retry business flows (especially payments or external service calls) without designing **idempotency**.

**Important limitation:** if only **order_lines** are added/deleted/updated **without** modifying the **orders** row, **@Version** on the parent row may **not** increment automatically depending on mapping strategy and provider. To protect invariants across **the whole aggregate**, the adapter must ensure child edits participate in root version control—such as using optimistic force-increment locking or controlled root version updates. Never treat `@Version` on the parent as magic protection for every child row.

### 7.3. Transactions Do Not Replace All Constraints

A use case may call:

~~~java
order.addLine(new OrderLine(1, productId, 2, 300_000));
~~~

inside a valid transaction, yet if two concurrent flows both write **line_no = 1**, the DB **PRIMARY KEY (order_id, line_no)** constraint remains the final line of defense. Domain logic stops adding duplicate lines **within one loaded object**, while DB keys stop duplicates **across competing transactions**.

Conversely, relying solely on database duplicate-key errors yields poor user messages and rough UX. Combine **domain/application validation messages** with **final DB enforcement**.

### 7.4. Dirty Checking and `merge` Are Mechanics, Not Invariants

In JPA, a **managed** object can have changes detected and written on flush/commit. A **detached** object lacks that tracking. Calling **merge** on an object tree built from an unvalidated request risks overwriting fields, unintentionally adding/removing children, or bypassing edit permissions.

A safer pattern is usually:

1. Load the aggregate by ID inside a transaction.
2. Invoke **permitted domain methods** on the domain model.
3. Have the adapter apply **intended changes** to managed rows.
4. Flush and translate version/constraint errors into designed domain errors or conflicts.

Never treat **entityManager.merge(requestBody)** as the default way to implement a business mutation command.

## 8. Lazy Loading, N+1, and Reading Properly per Use Case

Bugs often appear when JPA entities leak to the API layer and associations get traversed anywhere:

~~~java
// Anti-pattern illustration:
List<OrderJpaEntity> orders = jpaRepository.findAll();
for (OrderJpaEntity order : orders) {
    // If lines are LAZY, this can trigger a separate query per order.
    System.out.println(order.getLines().size());
}
~~~

Loading N orders in one query and then triggering a query per `lines` collection can total **1 + N queries**. If the persistence context has closed, reading the association fails due to unavailable lazy loading.

This is a **fetch-plan** consequence, not a business requirement saying "an order has many lines." Never try to fix it by forcing every association in the domain to **EAGER**.

### 8.1. Choose Fetch Strategies by Purpose

| Purpose | Suitable Read Approach | What to Watch |
| --- | --- | --- |
| Placing **one** order needing all lines | Load root and lines in transaction; join fetch or second query | Ensure aggregate has full data to verify invariants |
| Listing 100 orders by date | DTO/projection selecting only id, date, status, and stored total | Avoid instantiating 100 full aggregates |
| Reporting sold product quantities | SQL aggregation or dedicated read model | Never load the whole object graph to sum in Java |
| Viewing one order's details | Query with an explicit fetch plan | Watch query count, pagination, and row multiplication |
| Batch-processing many orders | Batch fetch or key-group queries | Measure query count, memory, and batch size |

Example of a DTO query directly against the schema:

~~~sql
SELECT
    o.order_id,
    o.status,
    COUNT(ol.line_no) AS line_count,
    COALESCE(
        SUM(ol.quantity::numeric * ol.unit_price_vnd),
        0
    ) AS order_value_vnd
FROM orders AS o
LEFT JOIN order_lines AS ol ON ol.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
~~~

This is a **read model** for the UI; it does not need to pass through **Order.restore(...)**. Separating read and write paths lightly keeps the domain model focused on behavior and free from fetch-plan coupling.

### 8.2. Why Not Return JPA Entities Directly over HTTP?

Returning a JPA entity from a controller can:

- Trigger lazy loading during JSON serialization.
- Cause circular references **Order → Lines → Order** in bidirectional mappings.
- Expose technical columns (version, internal IDs) or unintended internal fields.
- Couple persistence mapping changes directly to the public API contract.
- Fail after the transaction closes or trigger hidden query bursts.

Map to a **response DTO** with explicit fields. A DTO is not a domain entity: it is tailored to a screen or API contract and does not need to carry business behavior.

### 8.3. Aggregate Boundaries Do Not Mean Fetching the Whole Graph

If **Order** has many lines and each line references **Product**, placing an order does not require loading **every Product attribute, inventory count, supplier, or review**. **ProductId** and rule-relevant snapshots suffice when `Product` belongs to another aggregate.

An aggregate should guard invariants maintainable within **one consistency boundary**. Never turn every SQL foreign key into an owning object reference cascading across dozens of entities. Aggregate design and foreign keys are related, yet **not identical**.

## 9. Value Objects, Identity, and ORM Rules to Isolate

### 9.1. Value Objects Are Not Simply Everything "Without a Table"

A **MoneyVnd**, **EmailAddress**, or **AddressSnapshot** can be a domain value object. They are compared by **value**, not by database row identity.

At the storage level:

- `MoneyVnd` can be a single **BIGINT** column.
- An `AddressSnapshot` can flatten into **street, city, postal_code** columns.
- A list of multiple addresses with independent lifecycles may need a child table or another aggregate.

JPA **@Embeddable** can map a value object directly if annotations on the value class are acceptable; alternatively, persistence rows hold flat columns and the mapper builds plain Java value objects. Choose based on isolation needs, avoiding forcing domain value objects to adopt unnecessary no-arg constructors and mutability purely for the ORM.

### 9.2. Entity Equality and `hashCode`

In the domain, two references pointing to the same **OrderId** generally represent the same business entity, even as other attributes evolve over time.

For JPA entities, **equals()/hashCode()** must be designed carefully:

- New objects whose ID is database-generated after **persist** can change identity mid-lifecycle.
- Hibernate proxies can complicate runtime class equality checks.
- Including mutable collections in **hashCode()** can break **HashSet** invariants if lines change while the entity is in the set.
- Auto-generated equals/hashCode/toString annotations over all fields can touch lazy associations, triggering queries or infinite loops.

Never apply one blanket `equals/hashCode` formula to all entities. Define true identity, ID allocation strategy, and lifecycle; if using a stable business key, specify its scope and mutability policy.

### 9.3. ID and Version Play Two Different Roles

**UUID order_id** is the order's identity and carries meaning in use-case calls. **@Version** is a storage mechanism for detecting write conflicts; it is neither an order number nor business state.

If IDs are DB-generated on insert, the application must clarify when an order receives identity and how pre-insert events/dependencies behave. If IDs are application-generated (like the UUID in our example), the domain has an identifier before persistence; this does not remove the need for DB uniqueness constraints.

### 9.4. Never Let Cascade and `orphanRemoval` Replace Lifecycle Definitions

For example, **Order** owns **OrderLine** in business terms; deleting a DRAFT line may be allowed, whereas deleting lines of a PLACED order may be forbidden.

**cascade = ALL** or **orphanRemoval = true** dictates what the ORM does to rows when collections change; **they do not decide whether the business permits that action**. When invoice history is required, hard cascade deletion may even be prohibited for auditing. Specify lifecycle rules first, then pick cascades and **ON DELETE** rules accordingly.

### 9.5. Never Hide Core Logic Inside ORM Callbacks

**@PrePersist**, **@PreUpdate**, and similar callbacks can populate minor technical fields, yet should never be the sole place enforcing major rules like:

- Placing an order only when it has lines.
- Locking prices under a promotion policy.
- Ensuring shipped quantity does not exceed ordered quantity.
- Publishing a payment event after commit.

Callbacks do not always have full business context; execution timing can be hard to predict across flushes, multi-entity edits, or non-ORM write paths. Such rules belong in the domain model, use cases, and matching database mechanisms inside explicit transactions.

## 10. When to Separate Domain and JPA Entities vs. When to Merge?

"Within reasonable bounds" means using **a level of separation proportional to complexity and change risk**, rather than chasing an absolute slogan.

### 10.1. Three Practical Options

| Option | Characteristics | Suitable When | Costs / Risks |
| --- | --- | --- | --- |
| **A. Single class as domain + JPA entity** | Class holds **@Entity**, mappings, and domain methods | Small CRUD, few rules, one stable store, development speed paramount | Domain depends on JPA; prone to proxy/mutability leaks if undisciplined |
| **B. Pure domain + persistence entity + mapper** | Two separate models; adapter translates bidirectionally | Complex rules, rich state machines, clear aggregates, pure unit tests needed, evolving storage | Extra mapper code, state syncing, more complex version and identity handling |
| **C. Contextual hybrid** | Core aggregates kept pure; simple CRUD/admin tables use JPA directly; read models use projections | Large systems with uneven complexity | Requires clear naming and boundary conventions to prevent confusion |

**Option C** is often the pragmatic sweet spot: workflows like **ordering, payments, and inventory allocation** have rich invariants worth a pure domain model, while **country_codes**, **system_settings**, or simple admin screens can use JPA entities/DTOs directly without creating three nearly identical class hierarchies.

### 10.2. Signals Favoring Separation

Lean toward a pure domain model when:

- An aggregate has rich behaviors (**place, cancel, reserve, settle, refund**) with strict state-transition rules.
- Multiple use cases must reuse the exact same invariants.
- Domain logic needs fast unit tests without booting an ORM or database.
- Persistence spans multiple tables, history models, versioning, or complex mappings while domain language stays relatively stable.
- Data is read from multiple sources or requires alternative write mechanisms like SQL plus event sourcing/dedicated read models.
- Changing physical storage structure should not force rewriting business methods.

Consider **not separating** if a table only performs simple CRUD, objects look identical across layers, and a mapper merely copies fields without creating a meaningful boundary.

### 10.3. If Using JPA Entities Directly, Still Guard Domain Boundaries

You do not need a second class just to have good behavior. Even when a class is a JPA entity, still:

- Restrict public setters; expose **place()**, **addLine(...)**, **changePrice(...)** instead of letting every service mutate state freely.
- Keep checkable invariants on the object near the data it owns.
- Never let controllers accept or return managed entities directly; use request/response DTOs.
- Define transactions at the application service layer.
- Only touch lazy associations within intentionally fetched scopes.
- Keep **EntityManager** out of pure calculation code.
- Enforce keys, unique constraints, checks, and foreign keys in the schema even if the domain validates them too.

This achieves **conceptual and behavioral independence**, even without strict type/import separation. For small systems, this level often delivers more value than an over-layered architecture.

### 10.4. A Useful Litmus Test Question

> If tomorrow we changed how **order_lines** is stored from a `@OneToMany` association to explicit JDBC queries, would **Order.place()** and **Order.addLine()** have to change?

- If **no**, domain boundaries are well preserved.
- If **yes** because business logic calls **getHibernateLazyInitializer()**, **entityManager.flush()**, or assumes collections are ORM-managed, ORM details have leaked into the domain.

You do not need to promise you will swap out Hibernate tomorrow. The real value of clean boundaries is **lower cost of change and better testability today**.

## 11. Three-Layer Testing: Domain, Persistence, and Use Cases

Separation of responsibilities only pays off when tests verify each layer does its own job.

### 11.1. Domain Unit Tests Without Spring or a DB

JUnit 5 example:

~~~java
package example.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void cannotPlaceEmptyOrder() {
        Order order = new Order(UUID.randomUUID());
        assertThrows(IllegalStateException.class, order::place);
    }

    @Test
    void canPlaceDraftWithLineButCannotChangeAfterPlace() {
        Order order = new Order(UUID.randomUUID());
        OrderLine line = new OrderLine(
                1, UUID.randomUUID(), 2, 300_000
        );
        order.addLine(line);
        order.place();

        assertEquals(Order.Status.PLACED, order.status());
        assertThrows(
                IllegalStateException.class,
                () -> order.addLine(
                        new OrderLine(2, UUID.randomUUID(), 1, 100_000)
                )
        );
    }

    @Test
    void cannotDuplicateLineNumber() {
        Order order = new Order(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 10_000));

        assertThrows(
                IllegalArgumentException.class,
                () -> order.addLine(
                        new OrderLine(1, UUID.randomUUID(), 1, 20_000)
                )
        );
    }
}
~~~

These tests need no Hibernate, SQL, database container, or Spring context. Changing table names, fetch strategies, indexes, or ORM providers **should not break these tests**.

### 11.2. Persistence Integration Tests Need a Real Database

Pure unit tests **do not prove** mappings or DB constraints are right. For the persistence adapter, write integration tests verifying:

1. Create a DRAFT Order, add lines, and save; reading back restores exact ID, status, line count, and unit prices.
2. Save/read lines keyed by **(order_id, line_no)**; two lines with the same `lineNo` in one order must be rejected.
3. **CHECK(quantity > 0)** rejects negative values even on writes bypassing the domain.
4. Transitioning Order to PLACED flushes/commits and reads back accurately.
5. Two competing transactions updating the same order root trigger the designed **optimistic locking** behavior.
6. Adding/removing lines synchronizes properly in the persistence adapter; if invariants span the aggregate, root versioning protects child changes.
7. Measure SQL statement counts when loading multiple orders and verify projection queries to prevent N+1.

Test against the **actual target DBMS** or an equivalent environment. An in-memory database from a different engine may handle UUIDs, SQL dialects, foreign keys, locking, and transactions differently from PostgreSQL. Which database runner is used for integration tests is an implementation choice; **this lesson itself does not claim to have executed tests**.

### 11.3. Testing Use Cases and Transactions

For **PlaceOrder**, a fake repository can verify orchestration:

- Repository cannot find order → throws appropriate error, does not save.
- DRAFT order with no lines → domain rejects, nothing committed.
- Order with lines → calls `place()` and saves `PLACED` state.

However, testing rollbacks, version conflicts, and concurrent writers requires real transactions and persistence. Fake repositories **do not** accurately simulate isolation, dirty checking, or database locks.

### 11.4. Contract Tests at the API Boundary

Ensure the API:

- Never returns raw JPA proxies or unintended version fields.
- Returns meaningful business errors when placing an empty order or re-placing an already placed order.
- Rejects payloads attempting to tamper with internal properties via **mass assignment**.
- Reflects committed state; never reports success before the write transaction commits.

## 12. Publishing Domain Events and Integrating External Systems

A **PLACED** order may need to send notifications, reserve inventory, or emit messages to shipping. Never write:

~~~java
// Anti-pattern: performing external side effects inside Order.place().
emailClient.sendOrderPlaced(...);
~~~

if pure, independently testable domain logic is the goal. Instead:

- The domain expresses an **OrderPlaced(orderId)** event as an outcome of behavior, or records events on the aggregate via a clear protocol.
- The application coordinates committing and dispatching messages per integration policy.
- The persistence adapter persists data and can write an **outbox event in the same transaction** if the system must prevent database commits without emitted messages.
- A background worker/publisher later dispatches outbox events; consumers must handle idempotency and duplicate/replayed deliveries per system guarantees.

**Note:** calling a message broker after **order.place()** but before commit does not guarantee distributed consistency; if the commit fails, external systems may already receive an event for an order that never reached the expected state. **Transactional outbox** is a commonly considered pattern, not an automatic consequence of using an ORM or domain events.

## 13. The Data Schema Remains an Independent Model to Evaluate

Never let an ORM auto-generate DDL and assume it is a sound data model. A proper schema must answer:

- **Table grain:** does each row represent an entity, line, event, or point-in-time snapshot?
- **Candidate keys:** does a technical ID accidentally drop business uniqueness constraints?
- **Functional dependencies:** is the same current name or fact duplicated across multiple tables?
- **History:** how are locked prices, shipping addresses, and status transitions retained?
- **Relationships and lifecycles:** one-to-many, many-to-many, cascades, soft deletes, archived data?
- **Consistency:** which multi-row invariants require transactions or constraints?
- **Performance:** indexes, query shapes, pagination, aggregations, generated SQL counts?

For **order_lines** in our example, **product_id** is currently just a UUID because the example omitted a products catalog table. When a canonical **products(product_id)** table exists, consider **FOREIGN KEY (product_id) REFERENCES products(product_id)**; if products can be deleted or discontinued after an order is placed, define referential policies and retain proper historical snapshots. Never use the absence of a JPA association as an excuse to skip data integrity.

**Schema migrations** must be version-controlled and governed by a deployment workflow (using an appropriate SQL migration tool). Auto-syncing schemas from annotations at startup can be handy during early development, yet production requires controlling data migrations, deployment ordering, and rollback plans tailored to the project.

A sound principle: **the domain defines behavior; the schema defines durable truth and enforceable constraints; the ORM connects the two**. Neither side replaces the other's core job.

## 14. Practice Exercises

### Exercise 1 — Classifying Domain vs. Infrastructure Code

Given these responsibilities:

1. **Forbid** transitioning a DRAFT order to PLACED when it has zero lines.
2. Load order lines using a JPQL query parameterized by `orderId`.
3. Validate that `quantity` is greater than 0 when constructing a line.
4. Choose **@EmbeddedId** vs. **@IdClass** to map the line key.
5. Convert an Order into a DTO returned to the UI.
6. Increment version when an aggregate child changes to prevent concurrent overwrites.
7. Compute committed order total from line quantities and unit prices.
8. Create an index for queries searching lines by `productId`.

**Task:** identify primary ownership—domain, application/API, persistence adapter, or database schema. If a rule needs multi-layer protection, explain why.

<details>
<summary>Suggested Solution for Exercise 1</summary>

| # | Primary Owner | Notes |
| --- | --- | --- |
| 1 | **Domain** | `Order.place()` protects state transitions |
| 2 | **Persistence adapter** | JPQL is a query implementation detail |
| 3 | **Domain + database** | `OrderLine` constructor and SQL `CHECK` both protect |
| 4 | **Persistence adapter** | Mapping style difference is not order behavior |
| 5 | **API/application** | DTO belongs to the transport contract, not the aggregate |
| 6 | **Persistence adapter / transaction** | Root version must guard the full aggregate when needed |
| 7 | **Domain** or query projection depending on purpose | Domain computes for behavior rules; reporting reads can use SQL |
| 8 | **Database schema** | Indexes depend on workload and query plans |

</details>

### Exercise 2 — Spotting Where ORM Details Leaked into the Domain

Consider this illustrative snippet:

~~~java
public void placeOrder(OrderJpaEntity order) {
    Hibernate.initialize(order.getLines());
    if (order.getLines().size() == 0) {
        throw new IllegalStateException("empty order");
    }
    order.setStatus("PLACED");
    entityManager.flush();
}
~~~

**Tasks:**

1. Point out at least three signs that business logic depends on the ORM.
2. Rewrite the flow at the responsibility level (full Java code not required).
3. If the system is very small and keeps using JPA entities directly, suggest a lower-effort improvement than splitting into two full object hierarchies.

<details>
<summary>Suggested Solution for Exercise 2</summary>

- **OrderJpaEntity** enters the use case directly; **Hibernate.initialize(...)** is an infrastructure call; **setStatus("PLACED")** bypasses invariant-checking domain methods; **entityManager.flush()** couples the use case to ORM write mechanics and lifecycle.
- Alternative flow: application receives **orderId** → repository loads full **Order** → **order.place()** enforces invariants → repository saves changes → transaction commits.
- For a small project, you can keep the JPA entity while adding **place()** onto the entity, restricting status setters, and managing fetch plans/transactions in the service; this keeps behavior encapsulated and removes Hibernate utilities from business logic without splitting domain/persistence into two classes yet.

</details>

### Exercise 3 — Line Keys, Price Snapshots, and Aggregate Boundaries

A sales system specifies three rules:

- A product can appear twice on the same order at two different locked prices.
- Active catalog products can change name and price.
- Placed orders must keep locked line prices; catalog edits must never alter past invoices.

**Tasks:**

1. Why is **(order_id, product_id)** not necessarily a candidate key?
2. Should **unit_price_vnd_at_order** live on Product or OrderLine?
3. Does the `Order` domain object need to pull the entire `Product` object into every line?
4. When using JPA, what goes wrong if **OrderLine.unitPrice** is mapped to read directly from **Product.currentPrice** on every query?

<details>
<summary>Suggested Solution for Exercise 3</summary>

The appropriate key per rules is **(order_id, line_no)**; the same `productId` appearing multiple times causes no key collision. **unit_price_vnd_at_order** is a historical fact of the line, so it belongs on **OrderLine**, never recomputed from the current price list. The domain only needs **ProductId** and the price snapshot, unless a specific behavior genuinely requires extra verified attributes from `Product`.

If line price is read from **Product.currentPrice**, historical invoices will change whenever the catalog price updates. That is a **temporal semantics bug**, unfixable by **FetchType.EAGER** or swapping ORM annotations.

</details>

### Exercise 4 — Deciding the Layering Depth

Consider two subsystems:

**Subsystem A:** a catalog of country codes and display names, only added/edited/deleted via an admin page, with no notable business rules.

**Subsystem B:** order placement transactions involving inventory reservation, reservation expiration, split shipments, refunds, and concurrent multi-user edits.

**Task:** recommend A/B/C from Section 10's decision table for each subsystem, explain benefits and costs, and name three important integration tests for B.

**Solution Guide:** A can usually use **JPA entities + DTOs** directly without adding a domain layer that merely copies fields. B fits an **independent domain aggregate**, repository port, and persistence adapter; invariants, transactions, and concurrency must be explicit. Key integration tests: rejecting invalid state transitions, enforcing keys/versioning under two concurrent write transactions, and preserving historical data and integrity during inventory allocation or shipment.

### Exercise 5 — Intentional Denormalization Does Not Alter Domain Meaning

To speed up a list screen, the team adds **order_summary_read_model(order_id, status, line_count, total_vnd)** updated from source tables.

**Questions:** should this new table become an independent aggregate with a **place()** method? If read-model updates lag by a few seconds, how should the API express that? Which data remains the source of truth?

**Hint:** the read model is a projection optimizing reads; it does not become the authority for placing orders. **Order** and canonical transaction tables continue protecting invariants. If the read model updates asynchronously, the UI must account for staleness and never rely on potentially stale read-model values for sensitive write decisions without re-validating against the canonical source.

## 15. Pragmatic Design Checklist

| Question Before Finalizing | Reliable Indicator |
| --- | --- |
| Can the domain express behavior **without the ORM**? | Methods like **place()**, **addLine()** enforce clear invariants |
| Does the repository port speak domain terms? | Uses `Order`, `OrderId`, meaningful commands/queries; never exposes `EntityManager` |
| Are we creating two models just to copy fields? | Mapper cost weighed against real testing and change needs |
| Does ORM mapping reflect true grain? | `Order`, `OrderLine`, composite keys, and FKs match rules |
| Are historical values recomputed from live catalogs? | Snapshots belong to transactions, independent of `Product.currentPrice` |
| Do write use cases have wide-enough transactions? | Load/check/write live inside one consistency boundary |
| Does version protect child edits? | Write conflicts tested across the whole aggregate, not just the root row |
| Do associations trigger N+1 or lazy exceptions? | Fetch plans and query-count tests in place |
| Does the API return JPA entities/proxies? | Clear DTOs/projections defined |
| Are domain rules enforced in the DB where appropriate? | PK, FK, UNIQUE, CHECK, transactions, and advanced constraints as needed |
| Are there both pure unit tests and ORM integration tests? | Behavior testing cleanly separated from mapping/transaction testing |
| Is the schema versioned? | Migrations, upgrade plans, and data reconciliation procedures exist |

## 16. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "A domain without annotations is guaranteed ORM-independent." | If domain methods still rely on an open session, proxies, or `EntityManager`, coupling **still exists in behavior**. |
| "Every `@Entity` class is bad design." | For simple CRUD, a JPA entity with controlled behavior can be a sensible solution. |
| "Splitting domain and JPA entities eliminates persistence problems." | Mappers, transactions, versioning, locking, fetch plans, and schemas still require careful design. |
| "`@OneToMany` defines a domain aggregate." | SQL/ORM relationships do not dictate aggregate lifecycles or invariant boundaries. |
| "`@Version` on the root protects all children." | Verify how root version updates when collections/children are written. |
| "`LAZY` is always better than `EAGER`" or vice versa. | Fetch strategies depend on each use case and must be measured by query counts. |
| "Having a transaction prevents overwrites." | Isolation levels, optimistic/pessimistic locking, and DB constraints still matter. |
| "Mappers are redundant boilerplate so delete them." | Mappers are valuable when they isolate persistence churn from domain behavior. |
| "SQL normalization and object models should share the same shape." | Aggregate objects and normalized tables serve different goals; mappings bridge the two. |
| "If the ORM generated the schema, the schema is right." | Data design still requires grain, keys, FDs, FKs, history, migrations, and verification. |

## 17. Key Takeaways

**Keeping the domain model independent of ORM details within reasonable bounds** means putting **business terminology, behavior, and invariants** where they belong, while confining details like **@Entity**, **@EmbeddedId**, fetch plans, proxies, **EntityManager**, dirty checking, and transaction implementations to appropriate technical boundaries.

When business logic is complex, **pure domain → repository port → JPA adapter → database** lets you evolve mappings and test rules with minimal mutual interference. When the domain is simple CRUD, **combining JPA entities with domain behavior** can cut design overhead as long as you keep controlled setters, DTOs, clear transactions, and database constraints.

Framework independence must **never** come at the cost of data ambiguity: `Order` and `OrderLine` must have clear grain and keys, line prices must be transaction snapshots, aggregates need concurrency protection, and reads need fetch plans. Measure success by **clarity, testability, cost of change, performance, and data correctness**—not by counting Java classes or demanding zero annotations everywhere.
