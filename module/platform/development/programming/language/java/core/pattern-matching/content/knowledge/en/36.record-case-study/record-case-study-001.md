# Designing Nested Records for Order Data in Java 21

## 1. The Problem: Orders Have Nested Structure

An order rarely consists of only `id` and `total`. It usually involves a customer, contact information, a fulfillment method, a shipping address, and multiple product lines. A flat model quickly becomes hard to understand:

```java
// Sketch: many nullable and interdependent fields.
record OrderData(
    String orderId,
    String customerId,
    String email,
    String city,
    String street,
    String pickupStore,
    String[] skus,
    int[] quantities,
    long[] unitPrices
) {}
```

Problems with this design:
- `city`/`street` can be null for pickup, but must not be null for delivery; who enforces this?
- The three arrays `skus`, `quantities`, and `unitPrices` must always have the same length; elements at the same index must correspond to one line.
- Mutable arrays allow changing the record's state through references, even though the record component is final.
- An order may have `customerId` without `email`; the contract for missing data is unclear.
- Changing a small rule easily leads to validation scattered across the application.

**Nested records** help turn data relationships into **named structures with their own invariants**. Instead of three arrays, use `List<OrderLine>`. Instead of three address fields, use `Address` inside `Delivery`. Instead of interpreting null as "if there is an address then deliver, otherwise pick up", use `Delivery` or `Pickup` variants.

A model with clearer intent:

```text
Order
├── id: OrderId
├── customer: Customer
│   ├── id: CustomerId
│   └── contact: Contact
│       └── email: String
├── fulfillment: Fulfillment (sealed interface)
│   ├── Delivery
│   │   └── address: Address
│   │       ├── city: String
│   │       └── street: String
│   └── Pickup
│       └── storeCode: String
└── lines: List<OrderLine>
    └── OrderLine
        ├── sku: String
        ├── quantity: int
        └── unitPriceVnd: long
```

This is **composition**: a record containing components of other record types. You do not need to put all records in the same file or declare records as nested classes in Java syntax; "nested record" in this article mainly refers to **nested data structures** and **nested record patterns**. Records can be top-level types or static nested record declarations depending on how you package them.

This article focuses on meaningful domain design, constructor validation, immutability where needed, `switch` and nested record patterns in **Java 21**, as well as the limitations of using records for aggregates with complex identity or lifecycle.

## 2. Distinguishing Three Meanings of "Nested"

When speaking of "nested records", it is important to distinguish:

1. **A record component containing another record:** `record Customer(CustomerId id, Contact contact)`. This is composition of value types.
2. **Declaring a record inside a class/interface:** `class Demo { record Point(int x, int y) {} }`. A member record is **implicitly static** and does not hold a reference to an instance of the enclosing class.
3. **Nested record pattern:** `Customer(CustomerId(var id), Contact(var email))`. This is the syntax used in `instanceof`/`switch` to test and deconstruct multiple levels.

These three concepts are related but not identical. A system can place records in separate files and still match nested patterns. Conversely, declaring multiple records in the same file does not automatically create a composition relationship if their components do not reference one another.

**First rule:** start from **the business data relationships**, then choose where to declare the types and what deconstruction syntax to use. Do not build a very deep record tree just because Java supports nested record patterns.

### Java Version

- Record classes have been a standard feature since **Java 16**.
- Type patterns in `instanceof` have also been standard since Java 16.
- **Record patterns** and **pattern matching for `switch`** became complete and standard in **Java 21** (JEP 440, JEP 441).
- The full examples below require **JDK 21 or newer**, compiled with `javac --release 21`, **without needing `--enable-preview`**.

## 3. Choosing Aggregate Boundaries: What Data Does Order Own?

In an order model, just because something is "related" does not mean the entire object should be embedded into `Order`. Distinguish:

| Component | Example | Should it be stored directly in the Order snapshot? |
| --- | --- | --- |
| Order identifier | `OrderId` | Yes, it identifies the order in the use case |
| Finalized order lines | `List<OrderLine>` | Usually yes, because the total depends on the finalized contents |
| Unit price at order time | `unitPriceVnd` | Usually yes in the snapshot, independent of current catalog prices |
| Customer ID | `CustomerId` | Yes, links to the customer |
| Order contact email | `Contact` | Yes if the business needs a snapshot at order time; mind personal data |
| Full live customer profile | `CustomerEntity` in DB | Not by default: may only hold the ID or snapshot needed fields |
| Confirmed delivery address | `Delivery(Address)` | Yes when delivery requires a specific address |
| Multi-step shipping history | Tracking events, shipment lifecycle | Usually should have its own model/lifecycle |

**An Order snapshot is not necessarily a JPA entity.** A record has value equality across all components. If a domain entity has identity and state that changes over time, using `record Order(...)` can fit an **immutable snapshot** or a domain DTO, but it does not automatically solve transactions, versioning, optimistic locking, lazy loading, and ORM mapping.

For example, two Orders with the same `OrderId` but different `lines` will **not be equal under default `record.equals`**, because equality compares all components. If the business treats them as **the same entity** by ID, express that distinction at the entity/repository layer; do not assume a record has identity equality by default.

### Snapshotting Customer Information

In the example, `Customer(CustomerId, Contact)` represents the customer information **used in the order**. It does not automatically sync with the customer account later. If the customer updates their email, whether order history should keep the email at order time or use the current email is a **business decision**.

Names like `CustomerSnapshot` or `OrderContact` may be clearer than `Customer` in a real system. The standalone runnable example uses short names to focus on nested composition, but semantics should be documented clearly.

## 4. Choosing Types for Each Kind of Information

Named data types help push invariants to the right place:

```java
record OrderId(String value) {}
record CustomerId(String value) {}
record Contact(String email) {}
record Address(String city, String street) {}
record OrderLine(String sku, int quantity, long unitPriceVnd) {}
```

Why not use `String` for every ID? With two records `OrderId` and `CustomerId`, the compiler helps prevent accidentally passing a customer ID where an order ID is expected, while each ID type can also have its own validation or normalization.

Why is `OrderLine` a record instead of three parallel lists? Each line binds **SKU, quantity, and unit price** together in a single object. Adding a line modifies one `List<OrderLine>`, rather than coordinating three structures by index.

Why does `Address` have its own type? When an address has multiple fields, contracts for city/street, country, postal code, normalization, and validation can be managed in one place. For multi-country systems, address rules need to be more flexible than two demo fields; do not treat `city/street` as a global address schema.

### Which Money Type to Use?

The example uses `long unitPriceVnd`, meaning **whole Vietnamese dong** per unit of product. This model fits when dealing only with whole VND without fractional units. For multi-currency or different precisions, use a value type such as `Money(currency, minorUnits)` with a clear policy, rather than a vague `long`.

Do not use `double` for money if the business requires exact arithmetic in the smallest unit. Use `Math.multiplyExact` and `Math.addExact` to avoid silent overflow with `long` in the example.

## 5. Invariants: Records Do Not Automatically Forbid Null or Invalid Data

Declaring:

```java
record Address(String city, String street) {}
```

**does not automatically reject** `new Address(null, "")`. A record generates final components and structural methods, but it does not know business rules. Use a **compact canonical constructor** when data must always be valid:

```java
record Address(String city, String street) {
    Address {
        city = requireText(city, "city");
        street = requireText(street, "street");
    }
}

static String requireText(String value, String name) {
    java.util.Objects.requireNonNull(value, name);
    String normalized = value.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(name + " is blank");
    }
    return normalized;
}
```

Here `requireText` is an illustrative helper that needs to be placed in an enclosing class with appropriate visibility. A compact constructor lets you reassign parameters `city` and `street`, and the compiler assigns their final values to the component fields upon normal completion; do not write `this.city = city` in the body of a compact constructor.

**Useful invariants:**

- `OrderId.value` and `CustomerId.value`: non-null, non-blank, stripped of leading/trailing whitespace.
- `Contact.email`: non-null, non-blank in the example; **not yet an RFC-compliant email validator**.
- `Address.city/street`: non-null, non-blank.
- `OrderLine.sku`: non-null, non-blank; `quantity > 0`; `unitPriceVnd >= 0`.
- `Delivery.address`: non-null.
- `Pickup.storeCode`: non-null, non-blank.
- `Order.id/customer/fulfillment/lines`: non-null; `lines` non-empty, no null elements.

Do not confuse **"eligible to construct the object"** with **"payment approved"**. A structurally valid `Order` snapshot may still need inventory, limit, promotion, authorization, idempotency, and transaction checks at another business layer.

### Null Contracts and Exceptions

`Objects.requireNonNull(value, "field")` typically throws `NullPointerException` when the argument is null. `IllegalArgumentException` is appropriate for a present value that is out of domain (blank string, quantity 0). There is no single rule forcing every domain to use those exact two exceptions; publish and maintain a consistent API contract for your application.

## 6. Representing Delivery and Pickup with Sealed Variants

A common modeling mistake:

```java
record Order(
    String id,
    Address shippingAddress,
    String pickupStoreCode
) {}
```

If `shippingAddress == null`, does that mean pickup or a missing address? If both are non-null, is the order delivery or pickup? If both are null, is it valid? Such ambiguous states increase guards and processing bugs.

Replace it with:

```java
sealed interface Fulfillment permits Delivery, Pickup {}

record Delivery(Address address) implements Fulfillment {
    Delivery {
        java.util.Objects.requireNonNull(address, "address");
    }
}

record Pickup(String storeCode) implements Fulfillment {
    Pickup {
        storeCode = requireText(storeCode, "storeCode");
    }
}
```

Now the contract is crystal clear:
- A valid `Delivery` **must have an Address**.
- A valid `Pickup` **must have a storeCode**.
- `Order.fulfillment` must be one of the permitted variants, non-null.

Using `switch` over the sealed hierarchy:

```java
static String fulfillmentLabel(Fulfillment value) {
    java.util.Objects.requireNonNull(value, "value");
    return switch (value) {
        case Delivery delivery ->
            "Giao tới " + delivery.address().street()
                + ", " + delivery.address().city();
        case Pickup pickup ->
            "Nhận tại " + pickup.storeCode();
    };
}
```

The two cases are **exhaustive** for every non-null instance of `Fulfillment` in the current hierarchy. No `default` is needed. When adding a permitted `LockerDelivery`, if no case covers it yet, the compiler will require updating the `switch expression`.

**Do not assume `default` always catches a null selector** in an enhanced switch. The example above rejects null with `requireNonNull` before switching. If the contract differs, `case null` can be used with an appropriate typed result.

## 7. Designing OrderLine: Data That Belongs Together and Controlled Formulas

An order line needs the product identifier, quantity, and unit price at the time the order is created:

```java
record OrderLine(String sku, int quantity, long unitPriceVnd) {
    OrderLine {
        sku = requireText(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                "unitPriceVnd must be non-negative");
        }
    }

    long lineTotalVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }
}
```

**Why allow a unit price of 0?** The demo allows free promotional items. If the domain has no free items, a positive price can be required. Do not change the policy without reviewing business requirements.

**Why not also store `lineTotal` as a component?** Because `lineTotal = unitPrice × quantity` can be derived from the other components. If both were stored, you would have to enforce the invariant "lineTotal is always accurate" whenever creating a snapshot. For a short, pure formula, a `lineTotalVnd()` method on the record is acceptable.

**Overflow:** `Math.multiplyExact(long, int)` widens `int` to `long` and performs long multiplication; if it exceeds the `long` range, it throws `ArithmeticException` instead of wrapping. In Java, calling `Math.multiplyExact(unitPriceVnd, quantity)` selects the `multiplyExact(long, long)` overload because the `int` argument is widened to `long`. Do not assume every monetary addition is safe just because `long` is used.

For multiple lines:

```java
long total = 0;
for (OrderLine line : order.lines()) {
    total = Math.addExact(total, line.lineTotalVnd());
}
```

This is illustrative code inside a method that has `order`. The formula guards against overflow, but it does **not** automatically apply taxes, discounts, shipping fees, exchange rates, or rounding. Those must have their own contracts and calculation steps.

## 8. Protecting the Order Line List with Defensive Copying

A record component is final, but the `List` it points to can be mutable:

```java
record UnsafeOrder(java.util.List<OrderLine> lines) {}
```

If a caller passes an `ArrayList` and later calls `add/remove`, an already-created `UnsafeOrder` still "changes" in terms of observable value. Use a structurally immutable snapshot:

```java
record Order(
    OrderId id,
    Customer customer,
    Fulfillment fulfillment,
    java.util.List<OrderLine> lines
) {
    Order {
        java.util.Objects.requireNonNull(id, "id");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(fulfillment, "fulfillment");
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("lines is empty");
        }
    }
}
```

`List.copyOf`:
- Returns an unmodifiable list; callers cannot `add`, `remove`, or `clear` through the accessor.
- Disallows null elements.
- Creates a snapshot independent of structural changes to the mutable input list.
- May reuse an already-unmodifiable instance; it does not promise to always allocate a new list.

**Shallow vs. deep immutability:** In the example, elements are `OrderLine` records containing only `String` and primitives, so their components are stable; subrecords such as `CustomerId`, `Contact`, and `Address` also hold `String`, making the entire demo tree a value-stable snapshot. If `OrderLine` were changed to a record containing `Map<String, MutablePrice>`, `List.copyOf` on `Order` would **not** make those inner objects deeply immutable.

### Line Order and Equality Semantics

`List.equals` compares both elements and order. Two orders with the same SKUs and quantities in different line orders may have different `record.equals` results. If order matters for invoice printing, this makes sense. If the business considers order irrelevant, you must decide on normalization/sorting or another data structure, rather than just noting "order does not matter" without implementing it.

### Should Duplicate SKUs in One Order Be Forbidden?

The demo does **not** automatically forbid two lines with the same SKU; a system might allow them due to promotions, batches, or different customizations. If the business requires each SKU to appear on at most one line, add a tested invariant in the constructor/factory or normalize the list before creating `Order`.

## 9. Nested Record Patterns: Reading from Outside In

Java 21 allows matching multi-level structures:

```java
// Types in the full program are declared in section 11.
if (value instanceof Order(
        OrderId(var orderId),
        Customer(
            CustomerId(var customerId),
            Contact(var email)),
        Delivery(
            Address(var city, var street)),
        var lines)) {

    System.out.println(orderId + ": " + customerId);
}
```

This is an **illustrative snippet in a method receiving a `value` variable of type `Object`**. The corresponding match tree:

```text
Order
├── OrderId(var orderId)              -> String orderId
├── Customer
│   ├── CustomerId(var customerId)    -> String customerId
│   └── Contact(var email)            -> String email
├── Delivery
│   └── Address
│       ├── var city                  -> String city
│       └── var street                -> String street
└── var lines                         -> List<OrderLine> lines
```

**Semantics:**
1. The input must be a non-null `Order`.
2. `id` must match a non-null `OrderId`, and `value` is bound to `orderId`.
3. `customer` must match a non-null `Customer`; its inner components must further match `CustomerId` and `Contact`.
4. `fulfillment` must match the `Delivery` variant. A `Pickup` does not enter this branch even though it is a valid `Fulfillment`.
5. `Delivery.address` must match a non-null `Address`; `city` and `street` components are bound.
6. `lines` is captured with `var`, whose type `List<OrderLine>` is inferred from the record declaration.
7. If any nested record pattern fails, **the entire pattern fails to match**.

In the demo domain, constructors guard required references so a validly constructed `Order` has a non-null data tree by contract. However, the compiler **does not use** runtime rules inside a compact constructor to prove that every nested component is always present.

### `var` Is Not a Non-Null Check

If using an unvalidated input record:

```java
record RawOrder(String code, String email) {}

if (value instanceof RawOrder(var code, var email)) {
    // email can be null, even though its static type is String.
}
```

The outer record pattern requires `RawOrder` to be non-null, but `var email` can bind `null`. By contrast, `Contact(var email)` **does not match** when the entire `Contact` component is null. This is an important distinction when designing nested records and `when` guards.

### When Guards Are Evaluated

`case Order(...nested...) when someCondition -> ...` evaluates the guard **only after the entire nested pattern matches**. If `fulfillment` is `Pickup`, the `Delivery` branch's guard does not run. If the guard evaluates to false, `switch` considers other matching branches.

A value failing the pattern is **different** from a value matching the pattern whose guard returns false; when debugging, you need to know which case was actually selected and which fallback branch ran.

## 10. Do Not Nest Too Deeply in Every Case

Nested record patterns are powerful, but they can easily expose **too much detail at the dispatch point**.

For example, when processing only needs the Order ID and total:

```java
// No need to unpack Customer -> Contact -> Delivery -> Address
// if the task is only to compute the total.
long total = orderTotalVnd(order);
```

If you write deep patterns in every branch, a change such as adding `postalCode` to `Address` can force edits across many record patterns even though the total calculation has nothing to do with addresses.

Ways to reduce depth:

**A. Type patterns at the switch boundary**

```java
return switch (fulfillment) {
    case Delivery delivery -> handleDelivery(delivery);
    case Pickup pickup -> handlePickup(pickup);
};
```

This is an example inside a method with two handlers returning the same result type. The switch selects the right variant; each handler is responsible for the details.

**B. Record patterns only to the necessary depth**

```java
if (value instanceof Order(
        var id, var customer, Delivery(var address), var lines)) {
    // Only need to know it's Delivery and extract Address.
}
```

**C. Domain-named helpers**

```java
if (order.fulfillment() instanceof Delivery delivery
        && isServiceableAddress(delivery.address())) {
    // Named rule, independently testable.
}
```

`isServiceableAddress` is an illustrative helper; for policies requiring I/O, run them beforehand in an application service or separate the outcome explicitly rather than hiding a remote call inside a guard that may be evaluated multiple times.

**Principle:** pattern depth should reflect **the structure actually relevant to the decision**. If you need all fields to generate an invoice, nested patterns in an adapter can be valuable. If you only need the total amount, do not deconstruct the address.

## 11. Complete Java 21 Program: Nested Order Records

The following program is a **single standalone file** with no external dependencies. It builds value objects with constructors that enforce invariants, uses sealed fulfillment, copies the order line list, and demonstrates both `switch` type patterns and nested record patterns.

Create the file **`NestedOrderRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NestedOrderRecordDemo {

    static String required(String text, String field) {
        Objects.requireNonNull(text, field);
        String normalized = text.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " is blank");
        }
        return normalized;
    }

    record OrderId(String value) {
        OrderId {
            value = required(value, "orderId");
        }
    }

    record CustomerId(String value) {
        CustomerId {
            value = required(value, "customerId");
        }
    }

    // Demo only checks that email has content;
    // does not claim to validate email addresses per RFC.
    record Contact(String email) {
        Contact {
            email = required(email, "email");
        }
    }

    // Customer here is a contact snapshot used in the order.
    record Customer(CustomerId id, Contact contact) {
        Customer {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(contact, "contact");
        }
    }

    record Address(String city, String street) {
        Address {
            city = required(city, "city");
            street = required(street, "street");
        }
    }

    sealed interface Fulfillment permits Delivery, Pickup {}

    record Delivery(Address address) implements Fulfillment {
        Delivery {
            Objects.requireNonNull(address, "address");
        }
    }

    record Pickup(String storeCode) implements Fulfillment {
        Pickup {
            storeCode = required(storeCode, "storeCode");
        }
    }

    record OrderLine(String sku, int quantity, long unitPriceVnd) {
        OrderLine {
            sku = required(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "quantity must be positive");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                    "unitPriceVnd must be non-negative");
            }
        }

        long lineTotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    // Order is an immutable snapshot, not a JPA entity.
    record Order(OrderId id, Customer customer,
                 Fulfillment fulfillment, List<OrderLine> lines) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(customer, "customer");
            Objects.requireNonNull(fulfillment, "fulfillment");
            lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("lines is empty");
            }
        }
    }

    static long totalVnd(Order order) {
        Objects.requireNonNull(order, "order");
        long total = 0L;
        for (OrderLine line : order.lines()) {
            total = Math.addExact(total, line.lineTotalVnd());
        }
        return total;
    }

    // Exhaustive switch thanks to sealed Fulfillment.
    static String fulfillmentLabel(Fulfillment fulfillment) {
        Objects.requireNonNull(fulfillment, "fulfillment");
        return switch (fulfillment) {
            case Delivery delivery ->
                "Giao tới " + delivery.address().street()
                    + ", " + delivery.address().city();
            case Pickup pickup ->
                "Nhận tại " + pickup.storeCode();
        };
    }

    // Multi-level deconstruction when an adapter needs the full structure.
    static String inspect(Object value) {
        if (value instanceof Order(
                OrderId(var orderId),
                Customer(
                    CustomerId(var customerId),
                    Contact(var email)),
                Delivery(
                    Address(var city, var street)),
                var lines)) {

            return "Đơn " + orderId
                + " | khách " + customerId
                + " | " + email
                + " | giao " + street + ", " + city
                + " | " + lines.size() + " dòng";
        }

        if (value instanceof Order(
                OrderId(var orderId),
                var customer,
                Pickup(var storeCode),
                var lines)) {

            return "Đơn " + orderId
                + " | nhận " + storeCode
                + " | " + lines.size() + " dòng";
        }

        return switch (value) {
            case null -> "Không có dữ liệu";
            case Order order ->
                "Đơn chưa khớp cấu trúc: " + order.id().value();
            default -> "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Customer customer = new Customer(
            new CustomerId(" C-7 "),
            new Contact(" buyer@example.com "));

        List<OrderLine> sourceLines = new ArrayList<>();
        sourceLines.add(
            new OrderLine(" BOOK-1 ", 2, 120_000));
        sourceLines.add(
            new OrderLine("PEN-1", 3, 10_000));

        Order deliveryOrder = new Order(
            new OrderId(" OD-42 "),
            customer,
            new Delivery(new Address(" Hà Nội ", " Nguyễn Trãi ")),
            sourceLines);

        // Mutate the source list after creation:
        // the snapshot inside Order does not change.
        sourceLines.add(
            new OrderLine("EXTRA", 1, 999));

        System.out.println(
            "Mã đơn: " + deliveryOrder.id().value());
        System.out.println(
            "Khách: " + deliveryOrder.customer().id().value());
        System.out.println(
            "Số dòng đã chốt: " + deliveryOrder.lines().size());
        System.out.println(
            "Tổng VND: " + totalVnd(deliveryOrder));
        System.out.println(
            "Fulfillment: "
                + fulfillmentLabel(deliveryOrder.fulfillment()));
        System.out.println(inspect(deliveryOrder));

        Order pickupOrder = new Order(
            new OrderId("OD-43"),
            customer,
            new Pickup(" Q1 "),
            List.of(new OrderLine("PEN-1", 1, 10_000)));

        System.out.println(
            "Pickup: " + fulfillmentLabel(pickupOrder.fulfillment()));
        System.out.println(inspect(pickupOrder));

        try {
            deliveryOrder.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Danh sách bất biến");
        }

        try {
            new Delivery(null);
        } catch (NullPointerException ex) {
            System.out.println("Thiếu địa chỉ bị từ chối");
        }

        try {
            new OrderLine(" ", 1, 1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("SKU rỗng bị từ chối");
        }

        System.out.println(inspect(null));
    }
}
```

Compile and run from the directory containing the file, using **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 NestedOrderRecordDemo.java
java NestedOrderRecordDemo
```

**Expected output:**

```text
Mã đơn: OD-42
Khách: C-7
Số dòng đã chốt: 2
Tổng VND: 270000
Fulfillment: Giao tới Nguyễn Trãi, Hà Nội
Đơn OD-42 | khách C-7 | buyer@example.com | giao Nguyễn Trãi, Hà Nội | 2 dòng
Pickup: Nhận tại Q1
Đơn OD-43 | nhận Q1 | 1 dòng
Danh sách bất biến
Thiếu địa chỉ bị từ chối
SKU rỗng bị từ chối
Không có dữ liệu
```

### 11.1. Verifying Each Result

- `OrderId(" OD-42 ")` is stripped to `"OD-42"`; `CustomerId(" C-7 ")` becomes `"C-7"`.
- Line BOOK-1: `2 × 120000 = 240000` VND. Line PEN-1: `3 × 10000 = 30000` VND. Total is `270000` VND.
- Adding `EXTRA` to `sourceLines` **after** creating `Order` does not increase `deliveryOrder.lines().size()`; the snapshot has 2 lines.
- `Delivery(Address)` returns the delivery description to the stripped address `Nguyễn Trãi, Hà Nội`.
- The nested record pattern in `inspect` matches `Order -> Customer -> CustomerId/Contact -> Delivery -> Address` and binds the variables used in the summary line.
- The pickup order has `Fulfillment` as `Pickup`, so it does **not** match the pattern containing `Delivery(...)`; the second pattern selects the `Pickup` variant.
- `List.copyOf` causes `deliveryOrder.lines().clear()` to throw `UnsupportedOperationException`.
- `new Delivery(null)` throws `NullPointerException`; `new OrderLine(" ", ...)` throws `IllegalArgumentException` due to a blank SKU.
- `inspect(null)` does not match the nested patterns; the `case null` branch of the fallback switch returns `Không có dữ liệu`.

**There is no real payment/transaction** in the demo. The calculations are order data examples without taxes, shipping fees, discounts, payment status, or inventory management.

### 11.2. Why Is the Code Runnable Yet the Model Intentionally Minimal?

The way `Customer` and `Address` are structured is a demo domain choice, not a universal schema for all commerce systems. A real model also includes country/postal code, price at order time, promotion source, currency, VAT, order status, and lifecycle. This article focuses on **nested composition and pattern matching**, avoiding mixing in unrelated rules.

### 11.3. Why Is the Nested Pattern in `inspect` and Not in `totalVnd`?

`inspect` needs to read the ID, customer, and destination to build a structured summary. In that case, direct nested deconstruction is useful. By contrast, `totalVnd` only needs `lines` and prices, so it uses a simple loop. This is a criterion for **not overusing nested patterns**.

## 12. Techniques for Writing Safe `switch` Statements with Nested Records

A `switch` on `Fulfillment` is easier to prove exhaustive:

```java
return switch (fulfillment) {
    case Delivery delivery -> describeDelivery(delivery);
    case Pickup pickup -> describePickup(pickup);
};
```

The handlers are illustrative and must return compatible result types. When `Delivery` guarantees a non-null `Address` via its constructor, the handler can choose whatever level of deconstruction it needs.

If you `switch` directly on `Object` with multiple nested record patterns, consider the case where a pattern **fails to match** due to a different variant or a nullable component; include a broader domain branch and `default` for completely unrelated types, depending on the contract.

Example:

```java
// Illustrative: label assigned from a switch expression taking Object.
String label = switch (value) {
    case null -> "null";
    case Delivery(Address(var city, var street)) ->
        "Giao: " + street + ", " + city;
    case Delivery delivery ->
        "Delivery có cấu trúc địa chỉ không khớp";
    case Pickup(var storeCode) ->
        "Pickup: " + storeCode;
    default -> "Khác";
};
```

In the demo system, `Delivery`'s constructor rejects null, so `case Delivery delivery` rarely occurs for instances created under the contract. However, in terms of **pattern semantics**, `Delivery(Address(...))` is the case with a matching nested component; the compiler does not use constructor validation to eliminate fallback branches.

### Specific Before General Ordering

Writing:

```java
case Delivery(Address(var city, var street)) -> "Giao";
case Delivery delivery -> "Delivery khác";
```

is intentional: the specific structural branch comes before the branch accepting any `Delivery`. Reversing the order causes the nested branch to be **dominated** by `Delivery delivery`, which the compiler flags as unreachable.

### Guards and Null Policies

```java
case Delivery(Address(var city, var street))
        when city != null && !city.isBlank() ->
    "Có thành phố";
```

The guard is evaluated only when both `Delivery` and `Address` match non-null records. `var city` could receive null if `Address` was created via an unvalidated path; the guard uses safe short-circuiting. `case null` for the **selector** is separate from null components inside the tree.

### Record Patterns Do Not Invoke Arbitrary Calculations for You

`OrderLine(var sku, var quantity, var price)` only reads components; it **does not automatically call** `lineTotalVnd()`. When classifying by line total, you must explicitly compute it in a helper/guard or place the result in an evaluated object. Do not treat deconstruction as automatically executing validation or calculation.

## 13. What Happens When the Order Model Changes?

A record's component header is part of its **public API**. Changing:

```java
record Address(String city, String street) {}
```

to:

```java
record Address(String city, String street, String postalCode) {}
```

affects:
- The canonical constructor;
- Accessors, reflection, and some serialization tools;
- Record patterns like `Address(var city, var street)` because the component count must match;
- Default `equals`/`hashCode`;
- DTO/schema/API contracts if exposed publicly.

If `Order` embeds the entire `Address` and many use cases deconstruct it deeply, a small change to `Address` ripples across many files. That is why you should **not use nested patterns everywhere**.

Strategies:
1. Keep the domain model clear and version it when public schemas need to change.
2. Use type-pattern handlers/helpers when a use case does not need every component.
3. Isolate the mapping boundary from external data to domain value objects.
4. Do not change structure and business rules at the same time if they can be verified separately.
5. Maintain contract tests for old/new snapshots and all critical deserialization paths.

There is no automatic mechanism guaranteeing source compatibility for every consumer just because a record is immutable. Records are often convenient internally, but require care when a public API already has external callers.

## 14. Serialization and the Raw Data Boundary

A JSON input from an external system may contain nulls, wrong types, missing lines, or negative numbers. Do not assume deserializing into a record always invokes the right validation path across all libraries/configurations without verifying it.

A clear pipeline:

```text
HTTP / JSON / Message
         |
         v
RawOrderRequest (nullable DTO)
         |
         v
Parser + validator
         |
         v
OrderId, CustomerSnapshot, Fulfillment, OrderLine
         |
         v
Order snapshot (invariants protected)
         |
         v
Business use case / pattern matching / persistence
```

At the boundary, you can collect errors for multiple fields at once instead of throwing only on the first exception. In domain constructors, fail-fast protects invariants when constructing each value object. The two layers serve different purposes and can work together.

### Optional Fields and Variants

Not every component of an order is required. For example, a customer note may be absent. Several designs exist:
- Nullable `String note`, with clear Javadoc stating "null means no note";
- `Optional<String>` in the return type of a note-lookup API when appropriate for the toolchain;
- Sealed variants if "unconfirmed", "not provided by customer", and "hidden by policy" are **distinct business states**.

Do not introduce a whole chain of new records just for a simple nullable field. Model depth should be proportional to domain meaning.

### Records and JPA ORM

Many ORMs manage entities that require identity, lazy loading, mutable lifecycles, or proxies. Records are not automatically suited to replace every JPA entity in traditional entity mapping. A practical option is:
- Persistence entities shaped to ORM requirements;
- Immutable domain snapshots/DTOs using records;
- Explicit mapping between the two forms.

Do not call a nested `Order` record a "transaction-safe aggregate root" just because it holds all state; transactions and concurrency belong to layers with dedicated responsibilities.

## 15. Immutability and Concurrency

Record component fields are final, but components can reference mutable objects. The demo model has:
- `String`: immutable;
- `long`/`int`: primitives;
- Nested records containing only those values or references to nested records;
- `List.copyOf`: protects the collection structure of `Order`.

Therefore, the demo tree **exposes no mutable components** and is relatively safe to share as a snapshot. However, do not infer that **all records** have deep immutability or that every system using records is thread-safe.

If you store:
```java
record Attachment(byte[] data) {}
```

then the array can be mutated after creation and via the accessor. Default `record.equals` on arrays also uses reference equality, not byte-content equality. To get content-based value semantics, clone on input/output, implement appropriate equality/hash, or choose another immutable type.

If you have `List<MutableProduct>`, an unmodifiable list can still contain `MutableProduct` instances mutated through another reference. **Snapshot integrity requires examining the entire object graph**, not just the root record.

### Updating an Order by Creating a New Snapshot

An `Order` record has no setters. To add a line after creation, you can:
1. Create a new `ArrayList` from `order.lines()`;
2. Add the new `OrderLine`;
3. Create `new Order(order.id(), order.customer(), order.fulfillment(), newLines)`.

That produces a **new snapshot**, which may share the same `OrderId` but differ in record equality. If multiple users can edit the same `Order`, use versioning/optimistic locking or synchronization at the storage layer; immutable snapshots do not prevent lost updates on their own.

## 16. Unit Tests for Nested Order Records

**Testing constructor invariants:**

| Case | Expected |
| --- | --- |
| `new OrderId(null)` | Throws NPE |
| `new CustomerId("   ")` | Throws IllegalArgumentException |
| `new Delivery(null)` | Throws NPE |
| `new Pickup(" ")` | Throws IllegalArgumentException |
| `new OrderLine("SKU", 0, 100)` | Throws IllegalArgumentException |
| `new OrderLine("SKU", 1, -1)` | Throws IllegalArgumentException |
| `new Order(..., List.of())` | Throws IllegalArgumentException |
| `new Order(..., null)` | Throws NPE |
| `new Order(..., listMutable)`, then mutate source list | Snapshot unchanged |

**Testing pattern matching:**

- `Delivery` with a valid `Address` matches the nested branch and extracts `city`/`street` in component order.
- `Pickup` does not match the nested `Delivery` branch; it matches the `Pickup` branch.
- `inspect(null)` returns `Không có dữ liệu`.
- An `Object` that is not an `Order` returns `Không phải đơn hàng`.
- If a Raw DTO allows a null `Contact`, nested `Contact(...)` does not match, and that branch's guard does not run.

**Testing calculations:**

- Two lines `2×120000` and `3×10000` must yield `270000`.
- A line with price 0 is accepted per the demo contract.
- A very large `unitPriceVnd` multiplied by a large quantity must throw `ArithmeticException`; it must not silently overflow.
- Multiple lines whose sum exceeds `long` range also throw `ArithmeticException` via `Math.addExact`.

**Testing API evolution:** adding a `postalCode` component to `Address` requires updating constructors, record patterns, serialization mapping, and docs/tests. This case highlights the coupling of nested deconstruction.

### Testing Equality Is Not Testing Identity

You can create two `Order` instances with identical component structures to verify `equals` returns true. However, changing a line or `Contact` changes default equality. If a repository considers `Order` instances equal when they share the same ID, **that is a separate entity identity rule**; do not blindly rely on `record.equals` as the default.

## 17. Common Pitfalls

| Pitfall | Consequence | Solution |
| --- | --- | --- |
| Stuffing the entire order into a flat record with many nullable fields | Creates nonsensical state combinations | Split into ID, Contact, Address, Fulfillment, OrderLine |
| Nesting records for everything without domain meaning | Deep model and rigid API | Only create value types with clear invariants or roles |
| Assuming records validate null/blank automatically | Invalid domain objects can be constructed | Compact constructor/factory with validation |
| Using `shippingAddress == null` to infer pickup | Cannot distinguish missing data from another method | Sealed Fulfillment variants |
| Using three parallel lists for SKU/qty/price | Misaligned indices, wrong line totals | `List<OrderLine>` |
| Passing a mutable `List` directly into a record | Snapshot mutates after creation | `List.copyOf` in the constructor |
| Thinking `List.copyOf` guarantees deep immutability | Mutable elements can still change | Immutable elements/deep copy |
| Using `double` for exact money | Rounding errors | Long minor units/Money with contract |
| Forgetting arithmetic overflow for money | Sums or products wrap silently | `Math.addExact`/`multiplyExact` |
| Nested patterns inspecting unnecessary levels | Coupling to extra nulls/structure | Use type patterns or minimal deconstruction |
| Assuming `var component` is always non-null | NPE when calling methods | Define null contracts, use safe guards |
| Placing a broad case before a specific nested case | Nested case is dominated | Place specific cases first |
| Thinking a guard runs when the nested pattern fails | Wrong branch handles null | Separate structural match and guard |
| Using `default -> 0` to handle new fulfillment types | Masks missing business logic | Sealed exhaustive switch, review new subtypes |
| Equating an `Order` record with a mutable JPA aggregate | Broken identity/lifecycle/transactions | Separate snapshot and entity/use case |
| Not documenting record component order | Deconstruction mixes up same-type fields | Clear naming, Javadoc, tests |
| Logging full `Order.toString()` in production | Leaks email, address, unit prices | Minimal logging, policy-based masking |

## 18. Practice Exercises

**Exercise 1 — Design from a flat model.** Refactor `OrderData` from section 1 into `OrderId`, `CustomerId`, `Address`, `OrderLine`, and `Order` records. State the invariants belonging to each record, not just the field list.

**Exercise 2 — Add an optional note.** Add `note` to the `Order` snapshot. Specify whether null is valid, whether blank is meaningful, and whether to normalize with `strip()`. Write the corresponding Javadoc/constructor.

**Exercise 3 — New fulfillment variant.** Add `record LockerPickup(String lockerCode) implements Fulfillment`, update `permits` and `fulfillmentLabel`. Observe the compiler reporting a missing case in the `switch expression` before adding it. Add validation for `lockerCode`.

**Exercise 4 — Nested pattern.** Given `Order(OrderId(var id), Customer(CustomerId(var cid), Contact(var email)), Delivery(Address(var city, var street)), var lines)`, identify which variables are bound, their static types, and what happens for a `Pickup`.

**Exercise 5 — Deconstruct only when needed.** Write `totalVnd(Order)` without deep nested patterns. Explain why the calculation should not depend on `Contact` or `Address` if it only needs `OrderLine`.

**Exercise 6 — Snapshot.** Run the program in section 11, adding elements to `sourceLines` before and after creating `Order`. Observe when the finalized line count is 2 vs. 3, and why `List.copyOf` is needed.

**Exercise 7 — Overflow.** Create `OrderLine("X", 3, Long.MAX_VALUE)`; what happens when calling `lineTotalVnd()`? Why should you not use `long total = price * quantity` and assume every result is valid?

**Exercise 8 — Order identity.** Create two `Order` instances with the same `OrderId` but different `Contact` emails. What does default `equals` return? Does that mean the two snapshots represent two different orders by identity in a repository?

**Exercise 9 — API evolution.** Add `postalCode` to `Address`. Count the constructors, nested patterns, tests, and mappers that must be updated; propose ways to reduce the number of places coupled to component order.

**Exercise 10 — Multi-currency pricing design.** Replace `unitPriceVnd` with a `Money` record containing `currency` and `minorUnits`. When summing multiple `OrderLine`s, what condition must be checked to avoid adding different currencies?

**Exercise 11 — Order status.** Add `Draft`, `Confirmed`, and `Cancelled` statuses. Analyze whether to use an enum, sealed variants, or an entity workflow instead of putting a status into a record without guarding transitions.

**Exercise 12 — Personal data.** If `Order.toString()` can contain email/address, design a logging strategy that avoids leaking data in production while still tracking valid transaction IDs.

## 19. Summary

**Designing nested records for orders** means turning domain structure into **named value objects with clear invariants**, not merely grouping fields into a record tree.

Key takeaways:

1. Separate `OrderId`, `CustomerId`, `Contact`, `Address`, `OrderLine`, and `Fulfillment` variants when each type has its own meaning.
2. Enforce **non-null, non-blank, quantity, price, and list structure** in constructors; records do not validate automatically.
3. Use `List.copyOf` to snapshot order lines and understand the limits of **shallow immutability**.
4. Use sealed `Delivery`/`Pickup` instead of relying on ambiguous pairs of nullable fields.
5. Use nested record patterns when you **genuinely need to read multiple levels**; type patterns or helpers are better suited for narrow processing.
6. Distinguish **pattern failure** from **guard false**; `var` can bind null; specific cases go before broad ones.
7. For money, control units, overflow, and price-capture timing.
8. Distinguish an **Order snapshot with record equality** from **aggregate/entity identity and lifecycle** in storage systems.
9. Treat record header changes as API changes that can affect constructors, record patterns, equality, and mapping.

### References

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 21 — `Math.multiplyExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long))
