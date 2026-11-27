# Entities, Value Objects, and Aggregate Boundaries

In Domain-Driven Design (DDD), a domain model describes business concepts and rules using objects with clear responsibilities. The three foundational concepts are **Entity**, **Value Object**, and **Aggregate**. They help answer three different questions: how an object is identified, what defines its value, and which changes must be protected together.

With Spring Data REST, understanding these concepts is essential: the framework can export repositories as REST resources, but designing business boundaries and protecting invariants remains the responsibility of the domain model and the application.

## 1. The Big Picture

Imagine a sales system with orders, order lines, products, and currencies:

- An **order** has an identifier and a status that changes over time.
- An **order line** belongs to an order; its quantity or price can change while the order is still in draft status.
- A **monetary price** is defined by an amount and a currency unit. Two values with the same amount but different currencies are not the same value.
- An **order** must enforce rules such as not confirming an empty order, not adding lines after confirmation, and ensuring every line uses the same currency as the order.

The model can be represented as follows:

~~~text
PurchaseOrder (Aggregate Root / Entity)
|
+-- OrderLine (Internal Entity)
|   +-- productId (reference to Product aggregate)
|   +-- quantity
|   +-- unitPrice (Value Object: Money)
|
+-- status
+-- currencyCode
+-- version

Money (Value Object)
+-- amount
+-- currencyCode
~~~

In this example, `PurchaseOrder` is the aggregate root. `OrderLine` has its own identity within the scope of an order, but it is not an independent aggregate root. `Money` has no identity; it is defined entirely by its attributes.

## 2. Entity — An Object with Identity

An **Entity** is an object that we need to track throughout its lifecycle. Two entities can have the exact same data and still be two different objects if they have different identities.

For example:

- Two customers with the same name and address are still two different customers if their IDs differ.
- An order can change its status from `DRAFT` to `CONFIRMED`, yet remain the same order because its identity does not change.
- A product's name may change; the product ID continues to identify the product.

### 2.1. Identity Differs from Attributes

Consider the following two objects:

| Attribute | Order A | Order B |
|---|---|---|
| ID | 1001 | 1002 |
| Status | DRAFT | DRAFT |
| Currency | VND | VND |
| Total Amount | 500,000 | 500,000 |

The two orders have the same status and total amount, but they are not the same entity. They have different identities and may have different histories, owners, or access permissions.

In Java, an entity typically has an ID attribute:

~~~java
// Customer.java
package com.example.orders.domain;

import jakarta.persistence.*;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // Constructor required by JPA.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Customer name must not be blank");
        }
        this.name = newName;
    }
}
~~~

This is a JPA mapping example; the class needs to reside in a Spring Boot application with appropriate persistence and database configuration. An entity is not merely a row of data: it also has identity, state, and behaviors that perform valid state transitions.

### 2.2. Rules for Designing Entities

- Use an ID or a stable business key for identification; do not use a mutable name, address, or status as identity.
- Place state-changing operations in meaningful business methods such as `rename()`, `confirm()`, or `cancel()`.
- Validate input data and invariants right where state is changed.
- Do not expose setters for every attribute if arbitrary modification could put the object into an invalid state.
- Avoid generating `equals()` and `hashCode()` from all mutable fields of an entity. Doing so can cause the entity to disappear from a `HashSet` or become unfindable in a `HashMap` after a field changes.

With IDs generated on save, special care is needed when writing `equals()` and `hashCode()`: two new entities with a null ID must not accidentally be considered equal. You can use a truly immutable business key if the domain has one, or choose an ID-based comparison strategy that properly handles the unpersisted state. Do not mechanically apply Lombok's `@Data` to entities, as it typically generates equality and `toString()` based on multiple fields, easily causing issues with lazy associations or bidirectional cycles.

## 3. Value Object — An Object Defined by Its Value

A **Value Object** is an object without its own identity in the domain. Two instances are considered equal when all of their meaningful attributes are equal.

For example, the price `Money(100000, "VND")` is defined by the amount and the currency. We do not need a `moneyId` to recognize this value. Similarly, a shipping address can be a value object consisting of street, city, and postal code.

### 3.1. Characteristics of a Value Object

- **No separate identity:** no database ID is needed to distinguish individual instances.
- **Value-based equality:** all attributes that define the value are used in comparisons.
- **Should be immutable:** once created, its contents do not change. To obtain a different value, create a new instance.
- **Self-validating:** constructors or factory methods validate data upon creation.
- **Replaceable:** because it has no identity, one instance can be replaced with another having the same value without changing the domain meaning.

Value Objects help avoid passing disconnected primitive types. Instead of passing an unrelated `BigDecimal` and `String`, we pass a `Money` to ensure the amount is always paired with its currency unit.

### 3.2. Money Example in Java

~~~java
// Money.java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

@Embeddable
public class Money {

    @Column(name = "amount", precision = 19, scale = 2, nullable = false)
    private BigDecimal amount;

    @Column(name = "currency_code", length = 3, nullable = false)
    private String currencyCode;

    protected Money() {
        // JPA requires a no-arg constructor with public/protected visibility.
    }

    public Money(BigDecimal amount, String currencyCode) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Amount must be greater than or equal to 0");
        }
        if (currencyCode == null || currencyCode.isBlank()) {
            throw new IllegalArgumentException("Currency code is required");
        }

        String normalizedCode = currencyCode.toUpperCase(Locale.ROOT);
        Currency.getInstance(normalizedCode);

        this.amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        this.currencyCode = normalizedCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currencyCode.equals(other.currencyCode)) {
            throw new IllegalArgumentException("Cannot add two different currencies");
        }
        return new Money(amount.add(other.amount), currencyCode);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Money money)) {
            return false;
        }
        return amount.equals(money.amount)
            && currencyCode.equals(money.currencyCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currencyCode);
    }

    @Override
    public String toString() {
        return amount + " " + currencyCode;
    }
}
~~~

Notable points:

1. `@Embeddable` indicates that `Money` is persisted as part of the owning entity's state, without its own table and identity just because it is a value object.
2. There are no public setters. The application creates values through the constructor, which validates the amount and currency code.
3. `setScale(2, RoundingMode.UNNECESSARY)` requires data to have at most two significant decimal places; if rounding is needed, the domain should explicitly choose a rounding policy rather than letting the framework decide implicitly.
4. `plus()` only adds when the currencies match.
5. `equals()` and `hashCode()` are value-based. The constructor normalizes the scale of `BigDecimal` to avoid cases where `10.0` and `10.00` are treated as different solely because of scale.

Usage example:

~~~java
import java.math.BigDecimal;

Money price = new Money(new BigDecimal("125000.00"), "VND");
Money shipping = new Money(new BigDecimal("15000.00"), "VND");

Money total = price.plus(shipping);

System.out.println(total);
~~~

Output:

~~~text
140000.00 VND
~~~

This Java snippet illustrates how to use a Value Object; to run it, place it in a class with `main()` and configure the appropriate Jakarta Persistence dependency if JPA annotations are used. The `Money` calculation itself requires no database.

### 3.3. Mapping Value Objects with JPA

There are several ways to persist value objects:

- `@Embeddable` + `@Embedded`: the object's attributes are stored in the owning entity's table.
- `@ElementCollection`: stores a collection of basic values or embeddable values belonging to an entity; elements have no independent identity.
- `AttributeConverter`: converts a value object into a single column type, such as a status code or a simple value object into a string.

For example, `Money` embedded in `OrderLine`. Because the order line table may contain multiple price columns, we rename the columns using `@AttributeOverrides`:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "unit_price_amount", precision = 19, scale = 2)
    ),
    @AttributeOverride(
        name = "currencyCode",
        column = @Column(name = "unit_price_currency", length = 3)
    )
})
private Money unitPrice;
~~~

JPA field access is used in the example because mapping annotations are placed on fields. The provider can read/write persistent fields directly; therefore, the value object can keep an immutable API at the application layer while still having a no-arg constructor for persistence. For complex mappings, verify the requirements of your Jakarta Persistence version and provider.

## 4. Aggregate — The Consistency Boundary of the Domain

An **Aggregate** is a cluster of entities and value objects treated as a unit of business consistency. The **Aggregate Root** is the root entity, serving as the public entry point for external callers to request state changes inside the aggregate.

An aggregate is not simply a group of tables related by foreign keys. Aggregate boundaries are chosen based on which invariants must be protected together in a single business operation.

For example, with an order:

- An order cannot be confirmed if it has no order lines.
- Only draft orders can have lines added or removed.
- Each line's quantity must be greater than 0.
- The currency of each line's price must match the order's currency.
- An order line cannot be moved to another order by modifying an arbitrary attribute.

These rules involve the state of the order and its order lines. Therefore, `PurchaseOrder` is the aggregate root, and `OrderLine` resides inside the aggregate.

### 4.1. What Is the Aggregate Root Responsible For?

The aggregate root:

1. Provides business methods to mutate the aggregate.
2. Enforces invariants before changing state.
3. Controls the creation, addition, modification, or removal of internal entities.
4. Is the point through which external objects reference the aggregate.
5. Defines the transaction boundary for changes that must be consistent together.

External code should not fetch an `OrderLine` and directly modify its quantity or move it to another order. It should invoke `PurchaseOrder.addLine(...)` or a corresponding command on the root. That way, the root has full context to validate order status, currency, quantity, and related rules.

### 4.2. Referencing Other Aggregates by ID

If an order needs to reference a product, the product is usually a separate aggregate. The order can store `productId` instead of holding an object graph containing the entire Product entity.

Benefits:

- The Order aggregate does not need to load and lock the entire Product aggregate just to add an order line.
- The change boundaries of the two aggregates are clearer.
- Reduces the risk of cascading writes/deletes across aggregates.
- Product information can be queried through another service/repository when needed.

If the business requires storing the product name or price at the time of ordering, that snapshot can be stored in OrderLine. The snapshot is historical order data; it does not turn Product into part of the Order aggregate.

There is no absolute rule that every JPA relationship must be a scalar ID. What matters is understanding consistency boundaries: an object relationship or foreign key in the database does not by itself dictate the aggregate boundary.

## 5. A More Complete PurchaseOrder Aggregate Example

The example below uses a root entity `PurchaseOrder`, an internal entity `OrderLine`, and a value object `Money`. Each public class resides in its own file in the `com.example.orders.domain` package.

### 5.1. OrderLine — Internal Entity of the Aggregate

~~~java
// OrderLine.java
package com.example.orders.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "purchase_order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(name = "unit_price_amount", precision = 19, scale = 2, nullable = false)
        ),
        @AttributeOverride(
            name = "currencyCode",
            column = @Column(name = "unit_price_currency", length = 3, nullable = false)
        )
    })
    private Money unitPrice;

    protected OrderLine() {
        // JPA requires a no-arg constructor.
    }

    OrderLine(PurchaseOrder order, Long productId, int quantity, Money unitPrice) {
        this.order = Objects.requireNonNull(order, "order");
        this.productId = Objects.requireNonNull(productId, "productId");
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than 0");
        }
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");
    }

    public Long getId() {
        return id;
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    public Money getUnitPrice() {
        return unitPrice;
    }

    Money subtotal() {
        BigDecimal lineAmount = unitPrice.getAmount()
            .multiply(BigDecimal.valueOf(quantity));
        return new Money(lineAmount, unitPrice.getCurrencyCode());
    }
}
~~~

The `OrderLine` constructor has package visibility, so code outside the package cannot arbitrarily create order lines. In this example, only `PurchaseOrder` creates new order lines. This entity has a persistence ID, yet remains an internal component of the Order aggregate.

### 5.2. PurchaseOrder — Aggregate Root

~~~java
// PurchaseOrder.java
package com.example.orders.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    public enum Status {
        DRAFT,
        CONFIRMED,
        CANCELLED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status;

    @Column(name = "currency_code", nullable = false, length = 3)
    private String currencyCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    public PurchaseOrder(String currencyCode) {
        this.currencyCode = new Money(
            BigDecimal.ZERO,
            currencyCode
        ).getCurrencyCode();
        this.status = Status.DRAFT;
    }

    public void addLine(Long productId, int quantity, Money unitPrice) {
        ensureDraft();

        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than 0");
        }
        if (!currencyCode.equals(unitPrice.getCurrencyCode())) {
            throw new IllegalArgumentException(
                "Line item currency must match order currency"
            );
        }
        if (lines.stream().anyMatch(line -> line.getProductId().equals(productId))) {
            throw new IllegalArgumentException(
                "Product is already in the order; use a separate update operation"
            );
        }

        lines.add(new OrderLine(this, productId, quantity, unitPrice));
    }

    public void removeLine(Long productId) {
        ensureDraft();
        boolean removed = lines.removeIf(
            line -> line.getProductId().equals(productId)
        );
        if (!removed) {
            throw new IllegalArgumentException("Product not found in order");
        }
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = Status.CONFIRMED;
    }

    public Money total() {
        Money result = new Money(BigDecimal.ZERO, currencyCode);
        for (OrderLine line : lines) {
            result = result.plus(line.subtotal());
        }
        return result;
    }

    private void ensureDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be modified"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public Status getStatus() {
        return status;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

Key decisions in the example:

- No public setters for `status`, `currencyCode`, or `lines`.
- `addLine()` validates order status, quantity, currency, and duplicate products before creating the internal entity.
- `confirm()` enforces the aggregate-wide invariant.
- `orphanRemoval = true` instructs the persistence provider to delete an order line when it is removed from the collection and changes are flushed.
- `cascade = CascadeType.ALL` propagates persistence operations from the root to the order lines owned by the root. Cascading is a persistence mechanism; by itself it does not replace domain rules.
- `@Version` declares optimistic locking for the root entity. The version mechanism helps detect conflicting concurrent updates on the versioned entity. If the root's version must also protect changes to child collections, verify the lock scope and persistence provider behavior for your specific mapping; a force-increment strategy or explicit version update may be needed.

### 5.3. Placing the Repository at the Aggregate Root

~~~java
// PurchaseOrderRepository.java
package com.example.orders.domain;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Following DDD design, this repository is the access gateway for the Order aggregate. There is no need to create a public REST repository for `OrderLine` just to manipulate lines inside an order. Those operations should go through `PurchaseOrder`.

If queries by productId, status, or creation date are needed, query methods can be added to the root repository; read-only queries do not necessarily alter aggregate boundaries. Separate consideration is needed if a query returns internal entities or allows direct updates to them.

## 6. Aggregate Boundaries and Spring Data REST

Spring Data REST **exports Spring Data repositories as REST resources**. For example, `PurchaseOrderRepository` can produce the collection resource `/orders` and item resource `/orders/{id}`. By default, responses use HAL and associations of the domain type can be represented by links. Paths can be changed via `@RepositoryRestResource`.

Common requests:

~~~http
GET /orders
GET /orders/1001
~~~

Clients can discover links from the application's root URL. HAL representations typically include `_links`, and collections may use `_embedded` along with pagination metadata.

### 6.1. Spring Data REST Does Not Automatically Create Aggregate Boundaries

This is the most important point to remember:

- DDD defines aggregate boundaries based on business invariants and consistency.
- JPA defines entity mappings, associations, cascades, ownership, and persistence lifecycle.
- Spring Data REST defines which repositories are exported and which HTTP resources are created from those repositories.

These three layers are related, but they are not synonymous. Simply creating `PurchaseOrderRepository` does not automatically guarantee that every write path goes through `addLine()` or `confirm()`. A REST request is handled by the framework through exposed repository methods; for example, collection `POST` and item `PUT/PATCH` may call `save()`. They do not automatically invoke custom domain methods just because those methods exist on the entity.

If clients can send payloads to change state in ways that bypass invariants, the model risks being broken even when the domain code has proper validation methods.

### 6.2. How to Preserve Boundaries When Exposing APIs

1. **Only export repositories for aggregate roots.** Avoid creating public repositories for internal entities unless there is a genuine need.
2. **Review repository detection.** By default, Spring Data REST may export public repositories; you can use `@RepositoryRestResource(exported = false)` or configure the detection strategy to control which repositories are exposed.
3. **Control write methods.** `@RestResource(exported = false)` can hide repository methods from HTTP. Exposure configuration can also restrict HTTP methods. If you want read APIs via Spring Data REST while write commands must go through a service, disable the corresponding write methods.
4. **Place commands in application services/controllers.** Operations such as adding order lines, confirming an order, or cancelling an order should invoke domain methods on the root within a transaction.
5. **Protect with authorization.** Do not treat hiding a repository or link as a replacement for Spring Security. Permissions for reading collections, reading items, writing, deleting, and executing commands must be explicitly designed.
6. **Check association resources.** Spring Data REST can expose sub-resources for associations. Association operations such as linking the URI of an existing resource are not custom business commands; verify whether they conform to aggregate invariants.

Example application service for the order confirmation command:

~~~java
// OrderCommandService.java
package com.example.orders.application;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.domain.PurchaseOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public void confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        order.confirm();
        // The entity is managed in the transaction; JPA dirty checking
        // will persist changes when the transaction commits.
    }
}
~~~

A controller can expose the command with a business-meaningful endpoint:

~~~java
// OrderCommandController.java
package com.example.orders.api;

import com.example.orders.application.OrderCommandService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderCommandController {

    private final OrderCommandService service;

    public OrderCommandController(OrderCommandService service) {
        this.service = service;
    }

    @PostMapping("/{orderId}/confirm")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void confirm(@PathVariable Long orderId) {
        service.confirm(orderId);
    }
}
~~~

To avoid two write paths with conflicting rules, explicitly decide which route is the primary write path. If the command controller must protect invariants, do not leave public repository write endpoints open for clients to modify the same data while bypassing the command. You can disable repository write methods with `@RestResource(exported = false)` or choose not to export that repository and provide a dedicated API.

## 7. Transactions and Consistency Between Aggregates

An aggregate is designed so that its invariants are upheld within a single transaction. When adding an order line, changing status, and computing totals, the required changes for an order must be persisted together.

Do not lump every related entity into one giant aggregate just to share a single transaction. For example, Product, Customer, Inventory, and PurchaseOrder can be separate aggregates because they have different lifecycles, rules, and rates of change.

When a use case affects multiple aggregates:

- Reference other aggregates by ID.
- Keep transactions short and focused on a single aggregate whenever possible.
- If synchronization across multiple aggregates is required, consider domain events, application events, the outbox pattern, or workflows/sagas depending on requirements.
- Accept eventual consistency where the business allows it; do not use eventual consistency for invariants that must hold immediately.
- Use idempotency for commands that may be retried, especially when clients retry due to timeouts.

Not every multi-aggregate operation requires a saga. If they share the same database and an invariant genuinely requires an atomic transaction, a transaction across multiple repositories can be appropriate. However, that choice should be deliberate because it couples the aggregates more tightly.

### 7.1. Optimistic Locking

If multiple users can update the same order concurrently, `@Version` helps the persistence provider detect conflicts when the version in the database has changed relative to the version being updated by the transaction.

When an optimistic lock failure occurs, the application should return an appropriate conflict error, asking the client to reload the latest state and reconsider the operation. Do not automatically overwrite newer data with stale state.

Optimistic locking protects concurrent updates according to the mapping/version scope applied by the provider. Test scenarios where two transactions concurrently modify the root and a child collection; do not assume every relationship change automatically increments the root's version across all mappings.

## 8. When to Use Entity, Value Object, and Aggregate?

| Scenario | Suitable Model | Reason |
|---|---|---|
| Customer has an ID, history, and can change name | Entity | Needs to track the same customer over time |
| Price consisting of amount and currency | Value Object | Value is defined by all its attributes |
| Shipping address that only has meaning within an order | Value Object | No independent identity needed |
| Order line that lives only inside an order and obeys order rules | Internal entity of aggregate | May have a local ID, but lifecycle is controlled by the root |
| Order with confirmation rules and line management | Aggregate with PurchaseOrder root | Multiple states must be protected together |
| Product with its own lifecycle and pricing/inventory rules | Separate aggregate | Order should not directly control Product state |

A helpful question when classifying is: **if two instances have the exact same attributes, does the domain need to distinguish them?** If yes, it is usually an Entity. If no and only value comparison is needed, it is usually a Value Object. If multiple entities/value objects must change together to maintain invariants, consider grouping them into an Aggregate.

## 9. Common Design Pitfalls

1. **Turning every table into an independent entity with a public repository.** This can expose persistence structure and allow data modifications that bypass the aggregate root.
2. **Giving Value Objects unnecessary IDs.** If an object has no independent lifecycle, an ID only complicates the model.
3. **Mutable Value Objects.** A shared instance being mutated can silently affect multiple places. Prefer immutability and create a new instance when the value changes.
4. **Entity equality based on all fields.** When mutable fields change, hash-based collections can break; lazy relationships can also trigger unintended queries.
5. **Aggregates that are too large.** A simple operation must load and lock too many objects, increasing contention and lengthening transactions.
6. **Aggregates that are too small.** An invariant that must be immediately consistent gets split across multiple roots, forcing the application to coordinate multiple transactions.
7. **Letting controllers or serializers mutate arbitrary fields.** Public setters do not replace business methods.
8. **Confusing cascade with aggregate boundaries.** Cascade only describes persistence behavior; it does not define which object is allowed to mutate another.
9. **Assuming Spring Data REST automatically invokes services.** The repository exporter invokes exposed repository methods. Custom domain methods do not automatically become HTTP command endpoints.
10. **Hiding links without enforcing access control.** Clients can call URLs directly; real server-side authorization is required.

## 10. Testing the Domain Model

Test invariants without a database first, then test mappings and APIs at the integration layer.

### Unit Tests for Value Objects

- Same amount and same currency are equal.
- Different currencies are not equal.
- Cannot add two different currencies.
- Negative values or invalid currency codes are rejected.
- Scale and rounding rules are explicitly tested.

### Unit Tests for Aggregate Roots

- Cannot confirm an empty order.
- Cannot add order lines after confirmation.
- Cannot add zero or negative quantities.
- Cannot add a price with a currency different from the order.
- Cannot add the same product twice if the domain specifies one line per product.
- Removing an order line from a draft order updates the total amount correctly.

### Integration Tests

- `@Embedded` persists `Money` into the expected columns.
- `cascade` and `orphanRemoval` work according to the mapping.
- Only authorized repositories appear in the HAL root.
- Disabled HTTP methods actually return `405 Method Not Allowed`.
- Command controllers invoke domain methods and transactions roll back if an invariant fails.
- Security blocks unauthorized users.
- Two concurrent update transactions are handled according to optimistic locking.

## 11. Practical Design Workflow

When starting a new module, you can follow this sequence:

1. List business concepts and identify which objects require identity.
2. Find groups of data defined entirely by their values; model them as Value Objects.
3. Write down the invariants that must always hold after an operation.
4. Group entities/value objects that must change together to protect invariants.
5. Choose the Aggregate Root and expose only valid business methods on the root.
6. Design repositories for aggregate roots and decide which repositories Spring Data REST should export.
7. Choose the write path: CRUD repositories fit simple invariants, while command services/controllers fit operations requiring explicit workflows and business rules.
8. Write unit tests for invariants first, then integration tests for JPA mappings, transactions, REST representations, and security.

## 12. Conclusion

- **Entity** answers the question "is this the same object over time?" using identity.
- **Value Object** answers the question "do two values have the same meaning?" using attributes and value equality.
- **Aggregate** answers the question "which changes must be protected together?" using consistency boundaries and an aggregate root.
- **Spring Data REST** exports repositories as REST resources. It helps build APIs quickly, but it does not design aggregates, enforce every invariant automatically, or turn domain methods into command endpoints by itself.

When the domain model is clear, repositories, JPA mappings, and REST APIs can be organized around the same business boundaries. That makes the API easier to understand, reduces unintended write paths, and gives critical rules a single place of responsibility.

## 13. References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): how repositories are exported as collection, item, association, and query resources; how HTTP methods map to repository methods.
- [Spring Data REST — Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): repository detection strategies and how to hide repository methods from HTTP.
- [Jakarta Persistence — Embeddable](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/persistence/embeddable): how to declare types stored as part of an owning entity's state.
- [Jakarta Persistence — Entity](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/persistence/Entity.html): entity identity and mapping requirements.
- [Jakarta Persistence — Version](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Version.html): optimistic locking and valid types for version fields.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.pdf): description of embeddables, entity state, and persistence mappings.
