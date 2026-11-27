# Dividing Constraints Among Java Types, Domain Model, Application, and Database

A business rule can be checked in multiple places in a system, yet each layer has distinct responsibilities and enforcement capabilities. Java types represent data in the right shape; the domain model protects business semantics and valid entity states; the application layer orchestrates a use case across multiple objects and services; and the database protects integrity across every write path, including concurrent processes.

If you push every check into the UI or service layer, another write path can bypass the rule. If you push every condition into the database, the domain model becomes hard to express and business behavior becomes hard to test. If you duplicate the same condition across multiple layers without establishing an authoritative source, those layers can gradually interpret the rule differently.

In **data modeling**, designing invariants goes hand in hand with designing software boundaries. The question is not only “which condition must hold true?” but also “which layer understands that condition, which layer can enforce it reliably, and which layer serves as the final safeguard?”. This lesson uses a sales system to divide responsibilities across Java types, the domain model, the application layer, and the database.

## 1. Four layers, four kinds of responsibility

A Java system typically has the following processing layers:

1. **Java types and input structures** describe data shape, basic value domains, and how external data is converted.
2. **The domain model** represents business concepts, behavior, and valid states of an entity or aggregate.
3. **The application layer** executes use cases, coordinating multiple aggregates, transactions, authorization, and integration ports.
4. **The database** protects storage integrity through keys, constraints, transactions, and concurrency mechanisms.

~~~mermaid
flowchart TD
    A[HTTP, message, import] --> B[Java types and input validation]
    B --> C[Application use case]
    C --> D[Domain model]
    D --> C
    C --> E[Transaction and repository]
    E --> F[Database constraints]
    F --> E
    E --> C
    C --> G[Response or event]
~~~

The diagram illustrates a common flow, not a mandatory sequence for every architecture. A message consumer or batch import can enter the same application use case without passing through HTTP. The database can also be accessed by migrations, admin tools, or other services, so database constraints serve as a shared safeguard.

### 1.1. Principles for dividing responsibility

- Place a rule in the layer with enough semantics to express it.
- Place safeguards where they can protect all write paths.
- Validate early to return clear errors, without mistaking early validation for the final guarantee.
- Do not let outer layers mutate domain state by assigning fields directly.
- Use transactions and constraints for invariants that concurrent operations can break.
- Repeat checks only when each check serves a distinct purpose, such as input validation, domain protection, and storage protection.

A condition can appear in multiple layers without being wasteful duplication. For instance, the API checks that quantity is positive to return early feedback; the domain object refuses to create a line item with an invalid quantity; and a database CHECK protects data if another write path exists. Three safeguards serve three distinct boundaries. What must be avoided is each place defining a different rule.

## 2. Java types: representing shape and basic value domains

Java types eliminate certain invalid states right in code. Using `LocalDate` for calendar dates, `Instant` or `OffsetDateTime` for timestamps, `BigDecimal` for exact decimals, and `enum` for a finite value set is clearer than using `String` or `double` for everything.

### 2.1. Using types that match data semantics

| Meaning | Typically suitable Java type | Things to watch |
|---|---|---|
| Integer count | int, long | Check bounds and sign |
| Monetary amount, unit price | BigDecimal | Do not use float or double |
| Calendar date | LocalDate | Do not attach a timezone if it is just a date |
| Absolute point in time | Instant | Format in timezone at presentation layer |
| Point in time with offset | OffsetDateTime | Distinguish offset from time zone region |
| Finite status set | enum | A Java enum does not replace a DB constraint |
| Identifier | UUID or dedicated wrapper type | Do not pass raw Strings everywhere |

Data types help the compiler catch certain mistakes, but do not enforce every rule by themselves. An `int` can still be zero or negative. A `BigDecimal` can still hold a negative value, excessive scale, or out-of-range values. An `enum` can still be incompatible with legacy database values after an application upgrade.

### 2.2. Creating dedicated types instead of primitive obsession

If every ID is a `long`, it is easy to accidentally pass `productId` into a `customerId` parameter. Wrapper types let the compiler distinguish them:

~~~java
public record CustomerId(long value) {
    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("customerId must be positive");
        }
    }
}

public record ProductId(long value) {
    public ProductId {
        if (value <= 0) {
            throw new IllegalArgumentException("productId must be positive");
        }
    }
}

public void loadCustomer(CustomerId customerId) {
    // Cannot pass ProductId into this parameter.
}
~~~

Wrapper types are also useful for contract codes, currency codes, serial numbers, or tenant IDs. However, do not create a separate class for every column if it carries no distinct meaning or rule. The goal is to clarify concepts that are easily confused.

### 2.3. Value objects for money

Money is not merely a `BigDecimal`. It has an amount and a currency. Adding USD and VND must be rejected or converted under an explicit exchange-rate rule.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }
}
~~~

This example allows `Money` to represent negative values because some domains require refunds or adjustment entries. The rule “payment amount must be positive” belongs to a `PaymentAmount`/`Payment` type or behavior, rather than being mechanically forced onto every monetary value.

In systems with historical currencies or custom rules, currency catalogs may need to be managed in the domain instead of relying solely on JDK `Currency`. Precision, scale, and rounding must also be specified per business rules; `Currency.getDefaultFractionDigits` does not solve every accounting rule automatically.

### 2.4. Value objects for measured quantities

A `Quantity` has a numeric value and a unit. Only two values with the same dimension can be added after conversion:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record Quantity(BigDecimal value, Unit unit) {
    public Quantity {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
    }

    public Quantity add(Quantity other, UnitConverter converter) {
        if (!unit.dimension().equals(other.unit().dimension())) {
            throw new IllegalArgumentException("Dimension mismatch");
        }
        BigDecimal converted = converter.convert(
            other.value(), other.unit(), unit
        );
        return new Quantity(value.add(converted), unit);
    }
}
~~~

The snippet assumes `UnitConverter` verifies dimensions and applies managed conversion rules. For temperature, conversions can involve offsets; for volume-to-mass, density and context are required. Never implement all conversions by multiplying by a single factor.

### 2.5. Limits of Java types

Java types only protect paths passing through compiled Java code. They do not protect:

- Data received from HTTP or messages before parsing.
- Data written directly via SQL clients or admin tools.
- Another service using an older schema.
- Multiple transactions updating the same value concurrently.
- Legacy data already stored in the database.

Therefore, Java types are the first layer for clarifying data semantics and reducing programming errors, not the sole safeguard for the entire system.

## 3. Domain model: protecting business semantics and behavior

The domain model understands business concepts. It knows that a confirmed order cannot have arbitrary lines added, that ordered quantities must be positive, or that a payment cannot be recorded against a cancelled order.

### 3.1. Entities and value objects have different responsibilities

An **Entity** has identity and a lifecycle. For example, `Order` has an `orderId` and a state that evolves over time.

A **Value object** is defined by its values and is usually immutable. Examples include `Money`, `Quantity`, `Address`, or `DateRange`.

Value objects bundle data and its rules into one cohesive concept. Entities control state changes through business-named methods rather than letting callers mutate fields arbitrarily.

### 3.2. Protecting invariants inside an aggregate

An aggregate is the consistency boundary for a group of objects modified as one business unit. The aggregate root controls operations that mutate internal state.

For example, `Order` can be the aggregate root and `OrderLine` an internal member. Line items may only be added through `Order` behavior:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id, CustomerId customerId) {
        this.id = id;
        this.customerId = customerId;
    }

    public void addLine(ProductId productId, Quantity quantity, Money unitPrice) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be changed");
        }
        if (quantity.value().signum() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice.isNegative()) {
            throw new IllegalArgumentException("Unit price cannot be negative");
        }
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        status = OrderStatus.CONFIRMED;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }
}
~~~

This is an illustrative example. In a complete model, `OrderLine` can enforce its own internal rules, `Order` can compute totals per tax/discount policies, and methods can record domain events or change metadata.

The key point is that external code cannot obtain a mutable list and append lines after the order has been confirmed. The domain model must retain control over state transitions.

### 3.3. Do not put every rule inside entities

The domain model should not run arbitrary database queries or call APIs from inside an entity. A rule may require data outside the aggregate:

- Is the customer still within their credit limit?
- Does the warehouse have enough stock across locations?
- Is the promo code active and within usage limits?
- Does a piece of equipment already have maintenance scheduled during the requested interval?

If an entity directly calls repositories or HTTP clients, domain logic becomes coupled to infrastructure and hard to test. Use a domain service or application service to fetch required data, then pass results or policies into domain behavior.

### 3.4. An aggregate does not mean one table

One aggregate can be persisted across multiple tables; one table can also hold data for multiple concepts depending on the model. Aggregate boundaries are chosen based on consistency rules and mutation behavior, not table counts.

For example, `Order` and `OrderLine` may form one aggregate because line items change only through the order. `Payment` may be a separate aggregate because it has its own lifecycle, callbacks, and reconciliation. One order has multiple payments; recording payments and updating order status should be coordinated through an appropriate use case and transaction.

### 3.5. State transitions must be explicit behaviors

An enum can restrict the set of states, while the domain model enforces valid transitions:

~~~java
public void markPaid() {
    if (status != OrderStatus.CONFIRMED) {
        throw new IllegalStateException(
            "Only confirmed orders can be paid"
        );
    }
    status = OrderStatus.PAID;
}
~~~

If the business allows partial payments, states may not be a simple jump from CONFIRMED to PAID. You must model collected amounts, remaining balances, and appropriate statuses. Never use a simplistic enum to hide a complex workflow.

## 4. Application layer: orchestrating use cases and transaction boundaries

The application layer receives a specific request and coordinates the domain model with repositories, transaction managers, authorization, and external services. It should not become a dumping ground of scattered `if` statements holding all business rules.

### 4.1. Validating input at the system boundary

DTOs received from HTTP or messages must be checked for shape and syntax before invoking a use case:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record AddOrderLineRequest(
    @NotNull Long productId,
    @NotNull @Positive Integer quantity
) {}
~~~

Bean Validation helps return early, consistent input errors when the framework actually triggers validation, such as via `@Valid`/`@Validated` or an explicitly invoked `Validator`. Simply placing annotations does not automatically validate every DTO instantiation. Annotations on DTOs also do not protect call paths bypassing controllers and do not replace domain validation. An application use case can be invoked from a REST controller, message consumer, batch job, or test.

### 4.2. Application services orchestrate behavior

An add-order-line use case can:

1. Verify the caller is authorized to modify the order.
2. Load the `Order` by ID.
3. Fetch product information and applicable price.
4. Construct typed value objects.
5. Invoke `Order`'s `addLine` behavior.
6. Persist the aggregate within a transaction.
7. Return the result or emit events after commit.

Example:

~~~java
public final class AddOrderLineUseCase {
    private final OrderRepository orders;
    private final ProductCatalog products;
    private final Authorization authorization;
    private final TransactionRunner transactions;

    public AddOrderLineUseCase(
        OrderRepository orders,
        ProductCatalog products,
        Authorization authorization,
        TransactionRunner transactions
    ) {
        this.orders = orders;
        this.products = products;
        this.authorization = authorization;
        this.transactions = transactions;
    }

    public void execute(
        UserId actor,
        OrderId orderId,
        ProductId productId,
        Quantity quantity
    ) {
        transactions.required(() -> {
            authorization.requireCanEditOrder(actor, orderId);
            Order order = orders.getRequired(orderId);
            Product product = products.getRequired(productId);

            order.addLine(product.id(), quantity, product.currentPrice());
            orders.save(order);
        });
    }
}
~~~

The interfaces and `TransactionRunner` in the example are application-defined abstractions. Transaction implementation may use Spring, Jakarta Transactions, or another framework's mechanism. What matters is that commit/rollback boundaries encompass the changes that must be atomic.

### 4.3. Rules across multiple aggregates

Suppose a use case must confirm an order and reserve inventory. `Order` and `Inventory` may be two separate aggregates. The application service coordinates:

- Load the order.
- Compute demand per product.
- Reserve inventory.
- Transition the order to confirmed.
- Save changes within a transaction or suitable consistency workflow.

If all data lives in the same database and requires atomic commit, a transaction can cover the updates. If inventory lives in another service, you cannot assume an ACID transaction across HTTP. Instead, use a multi-step workflow such as reservations, confirmations, timeouts, and compensation.

### 4.4. Authorization is not a data invariant

The rule “this user is allowed to edit this order” is an access policy, typically enforced in the application layer or a policy service. Foreign keys cannot fully express permissions by user, role, tenant, and context.

However, the database still needs to protect data boundaries such as `tenant_id` or `owner_id` if the model requires it. In multi-tenant systems, composite foreign keys, row-level security, or equivalent mechanisms can be used depending on the DBMS. Never rely solely on assuming the client won't send another tenant's ID.

### 4.5. Idempotency spans both use case and persistence

A request may be resent due to timeouts or webhook retries. The application layer defines the semantics of an idempotency key and the response to return; the database uses `UNIQUE` to guarantee two requests with the same key are never created concurrently.

This exemplifies a rule with dual responsibilities: the application knows whether two requests carry the same meaning; the database protects uniqueness under concurrent writes.

## 5. Database: the final integrity safeguard

The database is the right place to enforce conditions that must hold regardless of whether data is written from a REST API, batch job, message consumer, SQL script, or another service.

### 5.1. Using constraints for declarative rules

Common constraints:

- PRIMARY KEY: identifies rows.
- UNIQUE: enforces uniqueness.
- FOREIGN KEY: enforces referential relationships.
- NOT NULL: requires a value.
- CHECK: validates row-level conditions.

Example:

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Constraints protect data even if a piece of Java code forgets to check. Yet the constraints above only enforce what is declared. They do not automatically ensure a confirmed order has line items or that totals match the lines.

### 5.2. Do not use database constraints to replace domain behavior

`CHECK status IN (...)` only verifies that status belongs to the allowed set. It cannot fully express that an order may only transition from `confirmed` to `paid` once a valid payment exists, or must not transition from `cancelled` to `fulfilled`.

The domain model understands those transitions. The application layer orchestrates payment and status changes within a transaction. The database can store transition history, foreign keys, and supporting constraints. Each layer plays its own role.

### 5.3. Protecting uniqueness under concurrency

A `SELECT` check before `INSERT` is not enough to protect uniqueness:

~~~sql
-- Two transactions can both see that the order number does not exist yet.
SELECT 1
FROM orders
WHERE order_number = :order_number;

INSERT INTO orders (customer_id, order_number, status)
VALUES (:customer_id, :order_number, 'draft');
~~~

If two transactions run concurrently, both can pass the `SELECT`. The `UNIQUE` constraint is the final safeguard. The application must catch unique-violation errors and translate them into an appropriate business outcome, such as reporting that the order number is already in use.

### 5.4. Transactions and atomic updates

When a business operation comprises multiple changes that must succeed or fail together, use a transaction. For instance, creating a payment and updating `amount_paid` must commit together. If only one succeeds, balances become inaccurate.

For inventory, a conditional update can enforce limits in a single statement:

~~~sql
UPDATE inventory_balances
SET reserved = reserved + :requested_quantity
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand - reserved >= :requested_quantity;
~~~

The application checks the affected row count. If zero, stock is insufficient or the balance row is missing. Creating the reservation detail must occur inside the same transaction.

### 5.5. Locks and isolation levels

When an invariant depends on multiple rows, choose how to protect against competing transactions:

- `SELECT FOR UPDATE` to lock rows representing a resource or aggregate.
- Conditional `UPDATE` to check and mutate atomically.
- Optimistic locking with a version column to detect conflicts.
- `SERIALIZABLE` when serial-equivalent outcomes are required and retries can be handled.
- Specialized constraints such as exclusion constraints when supported by the DBMS.

Isolation levels and locking behavior differ across DBMSs. Test under realistic workloads and handle deadlocks or serialization failures. Placing logic in Java cannot on its own prevent two transactions from reading the same stale value and overwriting each other.

### 5.6. The database does not understand all business semantics

The database can enforce `quantity > 0`, yet does not inherently know whether a product may be sold by kilogram or only by unit. It can store valid `status` values, yet does not know which users are permitted to trigger transitions. It can enforce foreign keys, yet does not inherently know customer-specific promotional pricing rules.

Rules with rich semantics should be expressed in the domain/application layers, while the database protects structural conditions and integrity rules it can enforce reliably.

## 6. Responsibility allocation matrix

| Rule type | Java types / DTO | Domain model | Application layer | Database |
|---|---|---|---|---|
| Properly shaped input data | Parsing, Bean Validation, specific types | Receives valid value objects | Handles input error responses | Column types and NOT NULL |
| Preventing ID mix-ups | Wrapper types | Uses typed IDs | Mapping and authorization | PK/FK |
| Positive quantity | `@Positive` on DTO where appropriate | `Quantity`/`OrderLine` rejects invalid values | Returns use-case error | CHECK |
| Order must have lines on confirm | Insufficient to enforce | `confirm()` checks lines | Calls `confirm` in transaction | Triggers/procedures or controlled workflow if all write paths need protection |
| Only valid state transitions | Enum represents state set | State-transition methods | Selects proper use case and transaction | CHECK values, store history; constraints do not replace state machines |
| Total payments <= amount due | Typed `Money`/`PaymentAmount` | Checks within order context | Coordinates payment recording | Locks/atomic updates/transactions |
| Inventory not over-reserved | Typed `Quantity` and `Unit` | Reservation rules in domain | Coordinates order and inventory | Conditional UPDATE, locks, CHECK |
| User authorized to act | Not primary responsibility | May supply domain policies | Authorization/policy | RLS or tenant boundary where appropriate |
| Unique idempotency key | Key type and request hash | May model logical operation | Identifies equivalent requests and responses | UNIQUE |

This matrix is an allocation guide, not a rigid law. Boundaries depend on architecture, DBMS, deployment model, and consistency requirements. When a rule appears in multiple layers, document which boundary each check protects.

## 7. End-to-end example: confirming an order

Suppose a customer creates an order with multiple lines. Upon confirmation, the system must guarantee:

- The order is in `draft` status.
- There is at least one line item.
- Each line's quantity is positive.
- Products are still eligible for sale.
- Prices and currency are finalized.
- Inventory is sufficient to reserve.
- Order total is computed by the same rules.
- Order number is unique.

### 7.1. At the Java boundary

The DTO verifies `productId` is present and `quantity` is positive. Parsers convert date strings or currency codes into typed objects. Malformed data is rejected before executing the use case.

### 7.2. In the domain model

`Order.confirm()` checks current status, the line-item list, and internal rules. `OrderLine` holds `Quantity` and `Money` rather than raw primitive numbers. The domain model prevents modifying lines after confirmation if policy forbids it.

### 7.3. In the application layer

`ConfirmOrderUseCase` verifies caller authorization, loads `Order`, retrieves pricing policies, and coordinates with `InventoryService` to reserve stock. It defines transaction boundaries, handles idempotency, and decides how to respond when inventory is insufficient.

### 7.4. In the database

`PRIMARY KEY`/`UNIQUE` protects identity, `FOREIGN KEY` protects references, and `CHECK` protects per-row quantities and prices. A transaction updates stock and writes reservations. Conditional `UPDATE` or locks prevent two concurrent requests from reserving the same inventory.

### 7.5. What if one layer skips a rule?

If a controller omits `@Positive`, the domain still rejects invalid `Quantity`. If a batch job bypasses the domain model and executes SQL directly, `CHECK` still blocks negative quantities. If two application requests reserve concurrently, database serialization protects stock levels. If the database lacks proper constraints or transactions, Java-side checks remain vulnerable to race conditions.

This is why layered responsibilities and final safeguards are needed. No single layer can fully substitute for all the others.

## 8. Avoiding two extremes: harmful duplication and missing safeguards

### 8.1. When should you check in multiple layers?

Intentional multi-layer checking makes sense when:

- DTOs need clear error messages before entering the domain.
- The domain must protect state regardless of who calls its methods.
- The database must protect data across all write paths.
- The application must verify conditions spanning multiple aggregates or services.

For instance, `quantity > 0` can be checked in the DTO, `Quantity` value object, and `CHECK` constraint. These three layers need not be three independent definitions; the domain rule defines canonical semantics, while DTOs and the DB act as safeguards at their boundaries.

### 8.2. When is duplicate checking harmful?

Duplicate checking becomes harmful when:

- Each layer uses a different threshold.
- One place allows scale 3 while another only allows scale 2.
- Domain and database disagree on valid states.
- Rules are copy-pasted across multiple places without tests or documentation.
- A business change updates only one layer.

Define canonical rules in domain terms and test conversion adapters. When schemas impose specific limits, synchronize them with domain value ranges.

### 8.3. When should a rule NOT live in the database?

Not every policy belongs in a `CHECK` or trigger:

- Rules depending on user permissions or roles.
- Rules requiring calls to external providers.
- Rules changing frequently by campaign or configuration.
- Rules with rich semantics needing explanation in business language.

The database can still store configuration, referential keys, or structural guardrails. However, deciding whether a request meets business eligibility usually belongs in the application/domain layers.

### 8.4. When should you NOT rely solely on the domain model?

If multiple applications, jobs, or admin tools write to the same database, a domain model inside one service cannot fully protect the data. If an invariant must hold even under two competing transactions, you must use constraints, transactions, locks, or appropriate concurrency mechanisms.

## 9. Mapping between domain and database

The domain model does not have to mirror table layouts. A domain object may contain value objects like `Money`, `Quantity`, or `DateRange`, while the database persists them across multiple columns or related tables.

For example, `Money` can map to `amount` and `currency_code`. `Quantity` can map to `measured_value` and `unit_code`. The domain model preserves meaningful objects, while the physical schema chooses suitable storage structures.

### 9.1. Keeping persistence types from leaking into the domain

The domain should not directly depend on:

- ORM entity annotations if the architecture separates domain from persistence.
- Lazy-loading proxies.
- Specific SQL exceptions or transaction APIs.
- Database-specific JSON types or row mappings.

Mappers or repository adapters can handle translation. In a small application, using JPA entities directly as domain objects can be pragmatic, provided you understand that ORM lifecycles, lazy loading, and managed state will influence domain behavior.

### 9.2. Checking legacy data on read

Database records may have been created by older application versions or before new constraints were added. When hydrating domain objects, handle data that is no longer valid:

- Reject loading and report a data error.
- Quarantine the record for remediation.
- Run migrations/backfills before enabling the new rule.
- Build compatibility adapters during transition periods.

Never silently construct a domain object in an invalid state and let failures surface later in unrelated, hard-to-trace behavior.

### 9.3. Handling constraint errors

Database constraint violations can still occur even after prior application checks, especially under concurrent writes. The application layer should map technical errors into meaningful use-case errors:

- Unique violation: code is already in use.
- Foreign key violation: referenced entity no longer exists or is invalid.
- Check violation: value violates the data domain.
- Deadlock/serialization failure: operation requires retry or conflict response.

Do not catch every `SQLException` and return a generic “system error” when the error category and safe handling can be identified. At the same time, never expose raw SQL details or internal table names to end users.

## 10. Testing by responsibility boundary

Each layer requires its own appropriate test strategy:

| Layer | Primary tests | Examples |
|---|---|---|
| Java types / DTO | Unit and validation tests | Invalid IDs, negative quantity, missing request fields |
| Domain model | Behavior and invariant unit tests | Cannot confirm empty order, cannot edit finalized order |
| Application | Use-case tests with fake repos/services or integration tests | Authorization, orchestration order, transactions, and idempotency |
| Database | Integration tests against real or compatible DBMS | CHECK, UNIQUE, FK, transactions, and rollbacks |
| Concurrency | Concurrency tests | Two requests claiming the last inventory unit simultaneously |
| Migration | Tests on realistic data copies | Backfills, adding constraints, and version compatibility |

### 10.1. Domain unit tests

~~~java
@Test
void cannotConfirmAnEmptyOrder() {
    Order order = new Order(
        new OrderId(1L),
        new CustomerId(10L)
    );

    assertThrows(
        IllegalStateException.class,
        order::confirm
    );
}
~~~

This test verifies domain behavior independently of the database. It does not prove the database has `CHECK` or `UNIQUE` constraints; that belongs to a separate test suite.

### 10.2. Constraint integration tests

Try inserting violating data directly into the database:

- `quantity = 0`.
- duplicate `order_number`.
- non-existent `customer_id`.
- `discount_amount` greater than line subtotal.

If the writes succeed, the constraints are missing or misconfigured. These tests matter because other write paths can bypass the domain model.

### 10.3. Concurrency tests

Seed inventory with 1 unit, then run two independent transactions simultaneously requesting to reserve 1 unit. A valid result allows only one request to succeed, keeps `reserved <= on_hand`, and leaves no orphaned reservation details.

Tests must execute genuinely concurrently, not merely sequentially twice. Use the actual DBMS and isolation level planned for production, since concurrency behavior varies across products.

### 10.4. Mapping contract tests

When domain `Money` is persisted as `amount` and `currency_code`, mapping tests should verify:

- Decimal values are not converted to floating-point numbers.
- Currency codes are preserved intact.
- Scale and rounding follow rules.
- Reading back reconstructs a valid `Money`.
- Legacy data is not misinterpreted under a different unit or currency.

## 11. Evolving rules across layers

Business rules evolve. For example, a system initially supports only a single full payment and later supports multiple installment payments. That change affects:

- DTOs and API contracts.
- Value objects or domain behavior.
- Use cases and transaction flows.
- Payment schemas, unique constraints, and `amount_paid` aggregates.
- Legacy data migrations.
- Reporting and reconciliation.

Roll out changes step by step:

1. Confirm the new definition and valid states.
2. Update the domain model and behavior tests.
3. Design compatible schemas and migrations.
4. Update application use cases, transactions, and error handling.
5. Deploy backward-compatible support for older versions if needed.
6. Backfill and reconcile data.
7. Remove old structures only when no consumers remain.

Do not alter a `CHECK` in the database while leaving the domain rejecting the new state. Likewise, do not expand a Java enum before the database and all consumers are ready to read the new value.

### 11.1. Expand–migrate–contract

When changing a schema shared by multiple running application versions:

- **Expand:** add new columns/tables/constraints in a backward-compatible way.
- **Migrate:** migrate data and update applications in phases.
- **Switch:** shift read/write traffic to the new structure.
- **Contract:** drop old structures after all consumers have migrated.

This strategy reduces risk when domain, application, and database cannot be deployed simultaneously.

## 12. Common responsibility-allocation mistakes

**Validating only in controllers.** Batch jobs or message consumers can bypass controllers. Protect domain behavior and database constraints according to scope.

**Putting all business logic in services.** Conditions scatter across `if` statements and get missed when new entry points appear. Move entity-centric behavior into the domain model.

**Entities exposing setters for every field.** Any caller can construct an invalid state. Encapsulate state and expose validated business methods.

**Using database constraints for all domain rules.** The database cannot fully express policies, permissions, and domain behaviors. Use constraints for structural integrity it can reliably enforce.

**Believing domain validation prevents race conditions.** Two domain instances can read the same stale state concurrently. Transactions, locks, optimistic concurrency, or database constraints are required.

**Duplicating validation without a canonical definition.** DTO allowing 0, domain requiring positive, and database allowing negative creates unpredictable failures. Synchronize value domains and tests across layers.

**Swallowing constraint errors.** Catching and ignoring exceptions can let a use case report success even though nothing was persisted. Transactions must roll back and errors must be mapped clearly.

**Letting the ORM decide for the domain.** Persistence callbacks or lifecycle hooks should not be the sole home of critical business rules if the domain can be invoked outside the ORM.

**Skipping direct-write tests.** A system tested only through REST APIs can miss imports, migrations, jobs, and SQL scripts.

## 13. Process for allocating an invariant

When receiving a new rule, follow these steps:

1. **Write the business definition:** what condition must hold, in which states, and with what exceptions?
2. **Determine data scope:** a single value, an entity, one aggregate, multiple aggregates, or multiple tables?
3. **Choose Java representation:** primitive, enum, ID wrapper, or value object?
4. **Choose where semantics live:** entity behavior, value object, domain service, or policy?
5. **Define the use case:** who calls it, what permissions are needed, and which repositories/services participate?
6. **Define database safeguards:** PK, UNIQUE, FK, CHECK, transactions, locks, or specialized constraints?
7. **Analyze concurrency:** can two requests pass checks at the same time?
8. **Define errors and recovery:** business error, retry, rollback, or compensation?
9. **Test every boundary:** unit, use-case, integration, concurrency, and migration tests.
10. **Document:** canonical rule, enforcement layers, source of truth, and owner.

## 14. Design review checklist

- [ ] Java types accurately express data semantics and prevent ID mix-ups.
- [ ] DTOs validate input syntax and shape at the system boundary.
- [ ] Value objects protect value domains and internal value rules.
- [ ] Entities/aggregates only allow state changes through valid business behaviors.
- [ ] The domain model has no direct dependencies on HTTP, SQL, or external services.
- [ ] The application layer coordinates authorization, use cases, transactions, and integrations.
- [ ] The database enforces PK, UNIQUE, FK, NOT NULL, and CHECK for appropriate rules.
- [ ] Cross-row invariants have appropriate locking, transactions, or isolation levels.
- [ ] All write paths (APIs, jobs, imports, webhooks) obey required safeguards.
- [ ] Constraint errors are mapped into appropriate use-case errors.
- [ ] Domain unit tests, database integration tests, and concurrency tests exist.
- [ ] Domain-to-schema mappings preserve values, units, precision, and history.
- [ ] Migrations coordinate changes across Java, domain, application, and database.
- [ ] Documentation records enforcement locations and owners for each critical invariant.

## Conclusion

Java types, the domain model, the application layer, and the database work together to protect data quality, each performing distinct jobs. Java types clarify data semantics and prevent basic mix-ups. The domain model protects behavior and valid states of entities or aggregates. The application layer orchestrates use cases, authorization, multiple aggregates, and transactions. The database protects integrity across every write path and handles contention with constraints and concurrency controls.

Determine an invariant's scope before choosing enforcement layers. Validate early for fast feedback, keep business rules in the domain, coordinate in the application layer, and place data guardrails in the database whenever possible. When all layers share one canonical definition, are tested at their boundaries, and evolve together, the system stays both understandable and reliable.
