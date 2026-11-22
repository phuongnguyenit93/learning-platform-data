# Matching Order Structure with Record Patterns in Java 21

## 1. The Problem: Inspecting Order Structure to Decide Processing

An e-commerce order may consist of multiple layers of data: customer information, product line, delivery method, address, and payment status. When classifying an order, the program does not just ask "is this an `Order`?"—it also has to examine **the structure of the components inside `Order`**.

For example, an order that is paid, belongs to a VIP customer, and has home delivery in Vietnam requires a different processing flow from a store pickup order. An order awaiting payment must not be routed to the delivery flow yet. If the customer, product, or address is missing, or if the total amount overflows the numeric type, the order must be rejected before routing.

**Record patterns** in Java 21 allow expressing that structure directly in a `case` label:

```java
// An illustrative branch in a switch on Order:
case Order(
        var id,
        Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)),
        var status)
        when status == Status.PAID
                && vip
                && "VN".equalsIgnoreCase(country) ->
        "VIP_HOME_VN";
```

How to read it from the outside in:

1. The selector must be an `Order`.
2. The second component must be a `Customer` to extract `customerId` and `vip`.
3. The third component must be a `Line` to extract `sku`, `quantity`, and `price`.
4. The fourth component must be a `Home` containing an `Address` to extract `city` and `country`.
5. The last component is `status`.
6. **Only after the patterns match**, the `when` guard checks that the order is paid, the customer is VIP, and the country is VN.

Strength: the order type, nested structure, and routing conditions appear **right inside a single case label**, without needing multiple `instanceof` checks and manual casts. Point of caution: **record patterns do not replace validation, null contracts, or pricing rules**.

**Version milestones:** `record` has been a standard feature since Java 16 (JEP 395); `sealed` has been standard since Java 17 (JEP 409). **Record patterns** (JEP 440) and **pattern matching for `switch`** (JEP 441) became standard in **Java 21**. This article uses JDK 21+, **without requiring `--enable-preview`**.

## 2. Defining the Domain Contract Before Matching

The case study uses the following data records:

| Type | Record components | Role |
| --- | --- | --- |
| `Customer` | `id: String`, `vip: boolean` | Ordering customer and VIP flag |
| `Line` | `sku: String`, `quantity: int`, `unitPriceCents: long` | **A single** product line of the order |
| `Address` | `city: String`, `country: String` | Delivery address |
| `Home` | `address: Address` | Home delivery |
| `Pickup` | `storeId: String` | Store pickup |
| `Delivery` | `sealed interface` | Common type of `Home` and `Pickup` |
| `Status` | `NEW`, `PAID`, `CANCELLED` | Payment/processing status of the order |
| `Order` | `id`, `customer`, `line`, `delivery`, `status` | Aggregates the structure of the order |

An `Order` in this article has only **one `Line`**. This is an assumption to illustrate nested record patterns, **not the definition of every sales system**. Multi-line orders will need `List<Line>` or another aggregate; record patterns on `List` do not automatically destructure individual elements.

To clearly demonstrate error paths, the example's record constructors **do not validate all invariants yet**. They can be created with null components or invalid quantities; a `valid(Order)` function is responsible for checking before routing. In a stricter domain design, validation can be done in the canonical constructor/factory, with a separate DTO used to represent untrusted input.

### Selected Business Rules

An order is considered data-valid when:

- `Order.id`, `Customer.id`, and `Line.sku` are non-null, non-blank strings.
- Both `Customer` and `Line` exist (are non-null).
- `quantity > 0`; `unitPriceCents >= 0`. A price of 0 is valid, for example for promotional/free gifts; this is defined by the demo contract.
- `quantity * unitPriceCents` **does not overflow `long`**.
- `delivery` and `status` are non-null.
- For `Home`, `Address` exists, and `city`/`country` are non-null and non-blank.
- For `Pickup`, `storeId` is non-null and non-blank.

Once the data is valid, the classification order is:

| Priority | Condition | Result |
| --- | --- | --- |
| 1 | Selector `Order` is null | `MISSING_ORDER` |
| 2 | Invalid component or monetary amount | `INVALID_ORDER` |
| 3 | `status == CANCELLED` | `CANCELLED` |
| 4 | `status == NEW` | `WAITING_PAYMENT` |
| 5 | `PAID` + `Home` + VIP customer + `country = VN` | `VIP_HOME_VN` |
| 6 | Remaining `PAID` + `Home` | `HOME_DELIVERY` |
| 7 | `PAID` + `Pickup` | `PICKUP` |
| 8 | Valid but undefined status/variant | **Report design error**, do not assume paid |

**Why place validation before status?** With this contract, an `Order` missing `Line` is still `INVALID_ORDER`, even if `status=CANCELLED`. Another domain might allow cancelling an incomplete draft. In that case, you must **intentionally change the policy order and update the tests**, rather than just swapping cases to make it "look nicer".

## 3. Record and Sealed Interface Model

Declare the nested types inside a Java class:

```java
record Customer(String id, boolean vip) {}
record Line(String sku, int quantity, long unitPriceCents) {}
record Address(String city, String country) {}

sealed interface Delivery permits Home, Pickup {}

record Home(Address address) implements Delivery {}
record Pickup(String storeId) implements Delivery {}

enum Status {
    NEW, PAID, CANCELLED
}

record Order(
        String id,
        Customer customer,
        Line line,
        Delivery delivery,
        Status status) {}
```

These components each have their own role:

- **Record** is a type of data carrier: the compiler generates the canonical constructor, component accessors (`order.customer()`, `line.quantity()`, ...), `equals`, `hashCode`, and `toString` according to record rules.
- **Sealed interface** restricts the direct implementations of `Delivery` in this case to `Home` and `Pickup`. The compiler has additional information to check `switch` exhaustiveness.
- **Enum** defines a named set of statuses. However, the compiler **does not automatically prove** that guards like `status == PAID` and `status == NEW` cover every enum value — guards are runtime conditions.
- Record fields are final in terms of **reference/value**, which does not automatically guarantee deep immutability of all referenced data. The nested types in the demo only contain `String`, primitives, and other records, so there are no mutable `List`s/arrays.

You do not necessarily have to use an `Order` record if you only want to pass scattered individual fields. But when those components always describe an entity together, a record creates a **clear schema** for matching and testing.

## 4. Understanding Record Patterns Through Three Extraction Levels

### 4.1. Type Pattern: Extracting Only the Object

```java
// Illustrates a case in switch (order):
case Order o -> o.line().quantity();
```

This approach only confirms that the selector has type `Order` and binds the object `o`. You still have to call accessors to dig into the structure. It is suitable when the logic is complex or you need to pass the entire `Order` to a service.

### 4.2. Shallow Record Pattern: Extracting Components Directly

```java
case Order(var id, var customer, var line, var delivery, var status) ->
        id;
```

The components of `Order` are bound by **declaration order**, not by the field names rewritten in the pattern. The types of `customer`, `line`, and `delivery` are inferred by the compiler with `var`. `var` here is **not a wildcard that discards data**: it is a pattern declaring a named variable.

This form is readable when you want to extract multiple top-level components without deep destructuring.

### 4.3. Nested Record Pattern: Going Deeper into the Data Tree

```java
case Order(
        var id,
        Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long unitPriceCents),
        Home(Address(var city, var country)),
        var status) ->
        sku + ":" + quantity;
```

This pattern directly extracts `Customer` → `vip`, `Line` → `quantity`, and `Home` → `Address` → `country`. It requires Java 21 when used as a **record pattern**, not just because the model is declared as a `record`.

**Avoid positional confusion:** `Order` declares `id, customer, line, delivery, status`; therefore, the pattern must have five corresponding components. A pattern missing a component or having an incompatible type may be rejected by the compiler. If `customer` and `line` are swapped, the author must update the pattern to match the schema—you cannot rely on variable names for the compiler to "look up fields by name".

### 4.4. When Not to Nest Too Deeply

A case containing many record layers plus a long guard can be harder to review than a named helper:

```java
// A form of separating dispatch when business logic grows:
case Order order -> classifyValidatedOrder(order);
```

`classifyValidatedOrder` in the snippet above is an **illustrative** helper name, not a built-in Java method. If domain conditions are long, keep the `switch` dispatching by type and move secondary decisions into a helper. However, when the structure is concise—such as Order/Customer/Line/Home/Address in one case—nested patterns make the **structural contract** very clear.

## 5. Nulls at Each Level of the Order Structure

In nested data, at least four levels must be distinguished:

1. **`order == null`**: the selector is null, which can be handled with `case null`.
2. **`order.customer() == null`**: the selector is still an `Order`, but the nested pattern `Customer(...)` does not match.
3. **`order.delivery() instanceof Home` but `Home.address() == null`**: the nested `Address(...)` does not match, even though `Home` exists.
4. **`new Address(null, "VN")`**: the `Address` record exists, and the `city` component is null. `Address(var city,var country)` can still bind null to `city`; validation/guards decide whether to accept it.

Example:

```java
// This snippet illustrates the difference in shape:
var missingCustomer = new Order(
        "o-1", null, new Line("book", 1, 500),
        new Pickup("store1"), Status.PAID);

var missingAddress = new Order(
        "o-2", new Customer("c1", true),
        new Line("book", 1, 500),
        new Home(null), Status.PAID);
```

You **cannot** simply add `case null` to catch these two situations, because `Order` itself is non-null. If you place **only** nested record patterns without a fallback branch, a `switch` that the compiler considers type-exhaustive can still fail at runtime when a nested record component is null (in some structures, it can throw `MatchException`).

This article uses **guard validation on a shallow `Order` record pattern before** the deeply nested patterns:

```java
case Order(var id, var customer, var line, var delivery, var status)
        when !valid(order) ->
        "INVALID_ORDER";
```

As a result, invalid data is not forced through the nested patterns of the delivery branches. In a real-world application, structured rejection right at the boundary/constructor is also a reasonable choice.

**Note:** `case null` at the Order level handles a null selector, while `valid` actively checks for null components. These are two different mechanisms and do not replace each other.

## 6. The `when` Guard and Precedence Rules

The two home delivery branches:

```java
case Order(
        var id, Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)), var status)
        when status == Status.PAID
                && vip
                && "VN".equalsIgnoreCase(country) ->
        "VIP_HOME_VN";

case Order(
        var id, Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)), var status)
        when status == Status.PAID ->
        "HOME_DELIVERY";
```

**Order matters:** the VIP-VN branch must come before the more general Home branch. When both guards are true, the first branch is selected. If the order is reversed, orders can fall into `HOME_DELIVERY` and bypass VIP priority handling.

- `when` is only evaluated once the record pattern has matched.
- `&&` short-circuits; `"VN".equalsIgnoreCase(country)` is null-safe even when `country` is null because it is called on a literal.
- Guards should be pure—no sending notifications, writing to databases, or mutating state. A guard may be tried and return false, causing the next case to be evaluated.
- Both branches check `status == PAID`. If status were only checked in the VIP branch, the general Home branch could accept a newly added enum status in the future and **deliver by mistake**.
- The final fallback branch of the example explicitly throws an error for a valid `Order` that **does not belong to any defined policy**, rather than automatically treating it as a paid order.

Do not mechanically apply "as few guards as possible". Each guard should reflect **a verifiable business constraint**.

## 7. Complete Java 21 Program: Classifying and Calculating Order Totals

The following example runs standalone, without needing any frameworks or external libraries. It contains:

- The `Order` type composed of nested records and sealed `Delivery`.
- Validation before classification.
- `switch` with **record patterns**, **nested record patterns**, **`when` guards**, and `case null`.
- Classification of unpaid, cancelled, VIP home delivery, standard delivery, and store pickup orders.
- Calculation checks using `Math.multiplyExact` to prevent `long` overflow.
- Value-based record comparison and an illustration of creating a copy when data needs to change.
- Assertion-based tests for **21 classification cases**, followed by checks for calculation, equality, immutability, and exceptions.

Create the file **`OrderRecordPatternDemo.java`**:

```java
public class OrderRecordPatternDemo {
    record Customer(String id, boolean vip) {}

    record Line(String sku, int quantity, long unitPriceCents) {}

    record Address(String city, String country) {}

    sealed interface Delivery permits Home, Pickup {}

    record Home(Address address) implements Delivery {}

    record Pickup(String storeId) implements Delivery {}

    enum Status { NEW, PAID, CANCELLED }

    record Order(
            String id,
            Customer customer,
            Line line,
            Delivery delivery,
            Status status) {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static boolean valid(Order order) {
        if (order == null || !hasText(order.id())) {
            return false;
        }

        Customer customer = order.customer();
        Line line = order.line();
        Delivery delivery = order.delivery();

        if (customer == null || !hasText(customer.id())) {
            return false;
        }

        if (line == null || !hasText(line.sku())
                || line.quantity() <= 0
                || line.unitPriceCents() < 0) {
            return false;
        }

        if (delivery == null || order.status() == null) {
            return false;
        }

        try {
            Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPriceCents());
        } catch (ArithmeticException ex) {
            return false;
        }

        return switch (delivery) {
            case Home(var address) ->
                    address != null
                            && hasText(address.city())
                            && hasText(address.country());

            case Pickup(var storeId) ->
                    hasText(storeId);
        };
    }

    static String route(Order order) {
        return switch (order) {
            case null ->
                    "MISSING_ORDER";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when !valid(order) ->
                    "INVALID_ORDER";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when status == Status.CANCELLED ->
                    "CANCELLED";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when status == Status.NEW ->
                    "WAITING_PAYMENT";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Home(Address(var city, var country)),
                    var status)
                    when status == Status.PAID
                            && vip
                            && "VN".equalsIgnoreCase(country) ->
                    "VIP_HOME_VN";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Home(Address(var city, var country)),
                    var status)
                    when status == Status.PAID ->
                    "HOME_DELIVERY";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Pickup(var storeId),
                    var status)
                    when status == Status.PAID ->
                    "PICKUP";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status) ->
                    throw new IllegalStateException(
                            "unexpected valid order");
        };
    }

    static long totalCents(Order order) {
        if (!valid(order)) {
            throw new IllegalArgumentException("invalid order");
        }

        return switch (order) {
            case Order(
                    var id,
                    var customer,
                    Line(var sku, int quantity, long price),
                    var delivery,
                    var status) ->
                    Math.multiplyExact((long) quantity, price);
        };
    }

    static void check(
            String label, Order order, String expected) {
        String actual = route(order);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected
                            + " got " + actual);
        }

        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        var customer = new Customer("c1", true);
        var standard = new Customer("c2", false);
        var line = new Line("book", 2, 1_250);

        var vn = new Home(new Address("Ha Noi", "VN"));
        var foreign = new Home(new Address("Paris", "FR"));

        Order paid = new Order(
                "o-1", customer, line, vn, Status.PAID);

        check("vip-vn", paid, "VIP_HOME_VN");

        check("standard-vn",
                new Order("o-2", standard, line, vn, Status.PAID),
                "HOME_DELIVERY");

        check("vip-foreign",
                new Order(
                        "o-3", customer, line, foreign, Status.PAID),
                "HOME_DELIVERY");

        check("pickup",
                new Order(
                        "o-4", customer, line,
                        new Pickup("store7"), Status.PAID),
                "PICKUP");

        check("waiting",
                new Order("o-5", customer, line, vn, Status.NEW),
                "WAITING_PAYMENT");

        check("cancelled",
                new Order(
                        "o-6", customer, line, vn, Status.CANCELLED),
                "CANCELLED");

        check("null-order", null, "MISSING_ORDER");

        check("null-customer",
                new Order("o-7", null, line, vn, Status.PAID),
                "INVALID_ORDER");

        check("blank-id",
                new Order(" ", customer, line, vn, Status.PAID),
                "INVALID_ORDER");

        check("null-line",
                new Order("o-8", customer, null, vn, Status.PAID),
                "INVALID_ORDER");

        check("zero-qty",
                new Order(
                        "o-9", customer,
                        new Line("book", 0, 50),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("negative-price",
                new Order(
                        "o-10", customer,
                        new Line("book", 2, -1),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("overflow",
                new Order(
                        "o-11", customer,
                        new Line("book", 2, Long.MAX_VALUE),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("null-address",
                new Order(
                        "o-12", customer, line,
                        new Home(null), Status.PAID),
                "INVALID_ORDER");

        check("null-city",
                new Order(
                        "o-13", customer, line,
                        new Home(new Address(null, "VN")),
                        Status.PAID),
                "INVALID_ORDER");

        check("blank-country",
                new Order(
                        "o-14", customer, line,
                        new Home(new Address("Hue", " ")),
                        Status.PAID),
                "INVALID_ORDER");

        check("blank-store",
                new Order(
                        "o-15", customer, line,
                        new Pickup(" "), Status.PAID),
                "INVALID_ORDER");

        check("null-delivery",
                new Order(
                        "o-16", customer, line, null, Status.PAID),
                "INVALID_ORDER");

        check("null-status",
                new Order(
                        "o-17", customer, line, vn, null),
                "INVALID_ORDER");

        check("blank-sku",
                new Order(
                        "o-18", customer,
                        new Line(" ", 1, 10),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("country-case",
                new Order(
                        "o-19", customer, line,
                        new Home(new Address("Hanoi", "vn")),
                        Status.PAID),
                "VIP_HOME_VN");

        System.out.println("total=" + totalCents(paid));

        System.out.println("records-equal="
                + paid.equals(
                        new Order(
                                "o-1",
                                new Customer("c1", true),
                                new Line("book", 2, 1_250),
                                new Home(
                                        new Address("Ha Noi", "VN")),
                                Status.PAID)));

        Order changed = new Order(
                paid.id(),
                paid.customer(),
                new Line("book", 3, 1_250),
                paid.delivery(),
                paid.status());

        System.out.println(
                "original-quantity=" + paid.line().quantity()
                        + " new-quantity="
                        + changed.line().quantity());

        try {
            totalCents(
                    new Order(
                            "bad", customer,
                            new Line("x", 0, 10),
                            vn, Status.PAID));
            throw new AssertionError("expected invalid order");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "invalid-total=IllegalArgumentException");
        }
    }
}
```

Compile/run with **JDK 21 or newer**:

```bash
javac --release 21 OrderRecordPatternDemo.java
java OrderRecordPatternDemo
```

**Exact stdout:**

```text
vip-vn => VIP_HOME_VN
standard-vn => HOME_DELIVERY
vip-foreign => HOME_DELIVERY
pickup => PICKUP
waiting => WAITING_PAYMENT
cancelled => CANCELLED
null-order => MISSING_ORDER
null-customer => INVALID_ORDER
blank-id => INVALID_ORDER
null-line => INVALID_ORDER
zero-qty => INVALID_ORDER
negative-price => INVALID_ORDER
overflow => INVALID_ORDER
null-address => INVALID_ORDER
null-city => INVALID_ORDER
blank-country => INVALID_ORDER
blank-store => INVALID_ORDER
null-delivery => INVALID_ORDER
null-status => INVALID_ORDER
blank-sku => INVALID_ORDER
country-case => VIP_HOME_VN
total=2500
records-equal=true
original-quantity=2 new-quantity=3
invalid-total=IllegalArgumentException
```

The demo program was verified using **JDK 24 JShell** with Java 21 language level: 21 classification cases along with checks for total amount, equals, copying, and exceptions. The `status == PAID` guard was tested separately using an enum version with an added `REFUNDED` value: the new status is not routed as a paid order and instead enters the explicit error branch.

**Execution scope:** `route` only returns a classification code; it **does not ship goods, charge cards, call a database, or transition states**. This is an intentional decision so the example focuses on structural matching. In a real system, once the routing code is obtained, it can be handed off to the corresponding handlers/services with appropriate transactions and authorization.

## 8. Explaining the Matching Flow for Each Case Group

### 8.1. Null and Invalid Are Checked First

For `null`, the `case null` branch returns `MISSING_ORDER`; the record patterns are not attempted as if there were a valid Order.

For `new Order("o-7", null, line, vn, PAID)`, the branch:

```java
case Order(var id, var customer, var line, var delivery, var status)
        when !valid(order) -> "INVALID_ORDER";
```

matches **the outer Order**, then `valid` sees `customer == null` and returns false. There is no need to try the deeply nested `Customer(...)` when the data is already invalid. This is an easy-to-debug layering approach.

### 8.2. New and Cancelled Orders

After validation passes, two guards route these cases:

```java
case Order(var id, var c, var l, var d, var status)
        when status == Status.CANCELLED ->
        "CANCELLED";

case Order(var id, var c, var l, var d, var status)
        when status == Status.NEW ->
        "WAITING_PAYMENT";
```

These are **case label snippets**, not a standalone program. New orders are not yet considered eligible for delivery. Under the stated contract, a cancelled order that is missing data is also treated as `INVALID_ORDER` because validation comes first.

### 8.3. Home with Nested Address, Pickup with storeId

Home:

```java
Home(Address(var city, var country))
```

differs from Pickup:

```java
Pickup(var storeId)
```

At the fourth position of `Order`, the two record patterns are mutually exclusive by `Delivery` subtype. A valid Pickup order will never match Home; the order between Home and Pickup does not matter by type, but the order of **the two guarded Home cases** is critical.

With `new Home(null)`, the Home record exists, but the nested `Address(...)` does not match. Therefore, validation/fallback must ensure no case is unexpectedly skipped.

### 8.4. Checking Country with a Literal

`"VN".equalsIgnoreCase(country)` treats `"vn"` the same as `"VN"`; that is an **intentional contract of the demo**. In a real international system, country should usually be stored as a **standardized country code** (such as ISO 3166-1 alpha-2), distinguishing between display name and code, and validated against an allowlist; `equalsIgnoreCase` does not automatically validate the length or validity of every code.

At the same time, the VIP priority policy must be defined: if a VIP customer is in another country, the demo returns `HOME_DELIVERY`, not `VIP_HOME_VN`.

### 8.5. Why Is There a Final Throw Branch?

```java
case Order(var id, var customer, var line, var delivery, var status) ->
        throw new IllegalStateException("unexpected valid order");
```

`when` guards do not automatically prove coverage of all possible `Status` values. If `REFUNDED` is later added to the enum and the order is still valid, the three branches `PAID`, `NEW`, and `CANCELLED` do not cover the new status. The final throw branch signals that **domain logic needs to be updated**, instead of silently sending a refunded order into the delivery flow.

A production system may choose a result code such as `UNSUPPORTED_STATUS` or a sealed outcome instead of throwing, but it must be decided **by contract**, with tests/migrations for the new status.

## 9. Total Amount: Avoiding Arithmetic Errors When the Order Structure Is Valid

Data having the "right types" does not automatically mean multiplication is safe.

For a single product line:

\[
\text{totalCents} = \text{quantity}\times\text{unitPriceCents}
\]

The snippet:

```java
return switch (order) {
    case Order(
            var id,
            var customer,
            Line(var sku, int quantity, long price),
            var delivery,
            var status) ->
            Math.multiplyExact((long) quantity, price);
};
```

is used inside a method after `valid(order)` passes. `Math.multiplyExact` throws `ArithmeticException` when signed multiplication exceeds the range of `long`. In `valid`, this expected exception is caught and turned into **invalid input** before classification; in `totalCents`, `multiplyExact` is also used to preserve the safeguard.

**Examples:**

- `quantity=2`, `unitPriceCents=1250` → `total=2500`.
- `quantity=0` → invalid according to the demo rules.
- `unitPriceCents=-1` → invalid.
- `quantity=2` and `unitPriceCents=Long.MAX_VALUE` → multiplication overflows and must not wrap around to a negative number.

If there are **multiple product lines**, you must sum across lines with `Math.addExact` and handle rules for taxes, discounts, currency, rounding, refunds, and quantities appropriately. Do not use `double` for real money when exact values in the smallest currency unit are required. The demo uses `long cents` with an assumed single currency unit; by itself, it is **not a safe payment system**.

### Boundary Between Validation and Pricing

The `valid` function checks `Math.multiplyExact` to reject orders whose total overflows. `totalCents` recomputes the total on a validated `Order`. Since this is a small, pure-data example, the cost is negligible; for multi-line orders and large data, you can switch to a `ValidatedOrder`/`PricingResult` type to **validate once** and pass along the computed values. Avoid storing duplicate totals alongside source data without a mechanism to keep them consistent.

## 10. Record Equality and Creating a Copy When Modifying an Order

Two `Order` instances with all corresponding record components equal will be `equals` by **value semantics**:

```java
var first = new Order(
        "o-1", new Customer("c1", true),
        new Line("book", 2, 1250),
        new Home(new Address("Ha Noi", "VN")),
        Status.PAID);

var second = new Order(
        "o-1", new Customer("c1", true),
        new Line("book", 2, 1250),
        new Home(new Address("Ha Noi", "VN")),
        Status.PAID);

System.out.println(first.equals(second)); // true
```

`record` generates the canonical constructor and accessors, but **does not generate withers** or setters such as `withLine(...)`. When you need to change the quantity, create a new Order with a new Line:

```java
Order changed = new Order(
        first.id(),
        first.customer(),
        new Line("book", 3, 1250),
        first.delivery(),
        first.status());
```

The `first` Order is not mutated. This is easy to test and fits systems that process immutable data.

**However:** a record only guarantees that component fields are final, **not deep immutability** when a component is an array/list or mutable object. In the current model, the nested types are records and strings/enums/primitives, which is safer, but if `Line` is later replaced by `List<Line>`, you will need `List.copyOf`/defensive copying and appropriate constructor/accessor design.

**Value equality differs from order identity:** The domain may consider two versions of an Order with the same `id` to be the same entity despite different statuses or totals. `record.equals`, on the other hand, compares **all components**. If you need entity identity and a complex lifecycle, separate the `OrderSnapshot` record (value) from `OrderEntity` (identity, persistence, version), rather than forcing `record.equals` to represent every business identity relationship.

## 11. When Adding Multiple Line Items, How Do Nested Record Patterns Change?

A real-world Order might use:

```java
// Illustrative schema for another version:
record MultiLineOrder(
        String id,
        Customer customer,
        java.util.List<Line> lines,
        Delivery delivery,
        Status status) {}
```

A `record pattern` can extract `lines` as a single component:

```java
case MultiLineOrder(var id, var customer, var lines, var delivery, var status)
        -> ...;
```

However, Java 21 syntax **does not automatically destructure `List`** like sequence patterns in some other languages. Do not write `case MultiLineOrder(..., List(Line(...), Line(...)),...)` as if Java 21 had list patterns.

Solution approach:

1. Use a record pattern to extract `List<Line> lines`.
2. Validate non-null, size, each Line, quantity, and price.
3. Iterate over the list using `for`/streams with `Math.multiplyExact` and `Math.addExact`.
4. If you need to pattern-match individual elements, use `switch(line)` or `instanceof` inside the loop.
5. Do not simply pass a mutable list variable into a record and assume it has become immutable.

**Type erasure:** A `List<String>` pattern from an `Object` cannot prove that all elements are Strings using only a runtime generic pattern. For `List<Line>`, you must rely on type boundaries/validation or inspect each element when data is untrusted.

## 12. Four Ways to Use Patterns in an Order Application

### 12.1. `instanceof` Pattern for a Simple Branch

```java
if (order.delivery() instanceof Pickup pickup) {
    System.out.println(pickup.storeId());
}
```

This is a good choice when only one branch is needed. Pattern matching for `instanceof` has been final since Java 16. If `order` can be null, you must guard `order` before calling the accessor.

### 12.2. Type Pattern in Switch

```java
return switch (delivery) {
    case Home home -> "HOME";
    case Pickup pickup -> "PICKUP";
};
```

This illustrative snippet assumes `delivery` is a non-null `Delivery`. With a sealed hierarchy having two subtypes, the compiler checks exhaustiveness. A null selector requires a separate policy if the data can be null.

### 12.3. Record Pattern in Switch

```java
return switch (delivery) {
    case Home(Address(var city, var country)) ->
            "HOME:" + country;
    case Pickup(var storeId) ->
            "STORE:" + storeId;
    case Home(var address) ->
            "HOME_WITHOUT_ADDRESS";
    case null ->
            "MISSING_DELIVERY";
};
```

This is an **illustrative expression snippet** inside a method with a `delivery` variable of type `Delivery`. The `Home(var address)` branch handles a Home containing a null Address, placed after the more specific Home record pattern. In real code, you can validate city/country instead of returning a raw string.

### 12.4. `when` Guard to Express Routing Policies

If there is a short business condition, a guarded record pattern can be very readable:

```java
case Order(var id, var c, var l, Home(var address), var status)
        when status == Status.PAID ->
        "PAID_HOME";
```

If the condition is long and involves multiple related rules, create a helper such as `eligibleForVipShipping(order)` rather than putting service calls with side effects into the guard. Weigh the trade-off between nesting depth and the number of jumps to other methods.

## 13. Distinguishing Record Pattern Correctness from Business Validation

A record pattern **does not automatically** verify that:

- `id` is an existing order ID in the database.
- `Customer` is actually authenticated or authorized to act.
- `unitPriceCents` matches the current price table.
- `status == PAID` has been confirmed by the payment gateway.
- The address is real or within the service area.
- `Home` and `Pickup` meet specific shipping/fee conditions.
- Fields created from JSON/DTOs have passed schema versioning.

Those checks require proper validation, authorization, inventory, and payment layers. `route` in the demo only **reads data** and returns a processing group; it must not be treated as actual authorization to ship.

A dangerous mistake is putting database update operations inside `when`:

```java
// Illustrative anti-pattern, DO NOT use:
// case Order o when chargeCard(o) -> "PAID";
```

If `chargeCard(o)` causes a side effect and then returns `false`, the switch may evaluate a subsequent branch while the card has already been charged. A guard should be a **pure predicate** on verified data. Side effects must live in the selected handler, protected by transactions/idempotency/authorization as needed.

## 14. Testing Record Patterns: Covering Structure, Guards, and Nulls

From the sample program, a test matrix can be built:

| Group | Input to test | Result |
| --- | --- | --- |
| Selector | `null` | `MISSING_ORDER` |
| Customer structure | `Customer=null`, `Customer.id` blank | `INVALID_ORDER` |
| Product structure | `Line=null`, `sku` blank, `quantity=0` | `INVALID_ORDER` |
| Numeric values | `price < 0`, multiplication overflows `long` | `INVALID_ORDER` |
| Home delivery | `Home(null)`, `Address.city=null`, `country` blank | `INVALID_ORDER` |
| Store pickup | `Pickup(" ")` | `INVALID_ORDER` |
| Status | `status=null` | `INVALID_ORDER` |
| Unpaid | `Status.NEW` on a valid Order | `WAITING_PAYMENT` |
| Cancelled | `Status.CANCELLED` on a valid Order | `CANCELLED` |
| VIP delivery | `Customer.vip=true`, `country=VN`, `status=PAID` | `VIP_HOME_VN` |
| Standard delivery | Standard customer in VN or VIP in another country | `HOME_DELIVERY` |
| Pickup | `Pickup("store7")` + `PAID` | `PICKUP` |
| Case-insensitive | `country="vn"` | `VIP_HOME_VN` |
| Equality | Two Orders with equivalent components | `equals == true` |
| Copying | Order replacing Line with a new record | Old Order unchanged |

A **property-based test** can generate combinations of `Status` × `Delivery` × `Customer.vip` × `country` × `quantity`, paying attention to boundary values. Useful properties include:

- **Totality over the defined domain:** for a valid `Order` in the three existing statuses, `route` returns exactly one valid code.
- **No delivery routing before payment:** `NEW` or `CANCELLED` must not return `HOME_DELIVERY`, `VIP_HOME_VN`, or `PICKUP`.
- **No bypassing validation:** an Order missing any required component must not enter a delivery handler.
- **Metamorphic:** changing `id` from one valid string to another valid string does not change the routing group when all other conditions remain the same.
- **Arithmetic:** the total amount must be a safe multiplication, with no overflow/wrap-around.

If refactoring from `if instanceof/cast` to `switch`, compare results against an independent oracle written from the business table, but do not compare outputs alone if side effects, exceptions, or database writes are involved.

### Why Must Testing Go Deeper Than the Two Home and Pickup Branches?

The compiler knows `Delivery` is sealed, but it does not know whether the contents of `Address` are valid or null. The compiler also does not verify that all status values have been covered by the right guards. Therefore, **compilation success is different from business completeness**. Tests must exercise null values at **every level** and boolean conditions around boundaries.

## 15. Common Pitfalls

1. **Confusing record patterns with record declarations:** having `record Order(...)` since Java 16 does not mean `case Order(...)` was final in Java 16; record patterns became final in Java 21.
2. **Wrong order of components in the pattern:** the compiler uses canonical component order, not variable-name lookup.
3. **Assuming `var x` ignores any value:** it is a binding pattern with an inferred type; the author can use it in the guard/branch body.
4. **Assuming nested `Address(...)` matches `Address=null`:** it does not; validation or fallback is needed at the right level.
5. **Forgetting `case null` for the Order selector:** this can throw `NullPointerException`; `default` should not be treated as a null fallback.
6. **Placing the general Home branch before the VIP Home branch:** hides the priority policy or causes the later case to be dominated.
7. **Not checking `Status.PAID` in all delivery branches:** a new status could accidentally be routed as paid.
8. **Assuming a sealed hierarchy automatically checks all guards:** **type** exhaustiveness does not prove all business cases are covered.
9. **Checking only the Line type without checking quantity/price:** record patterns do not automatically enforce business validation.
10. **Multiplying quantity × price with `*` and ignoring overflow:** can produce a wrong negative number.
11. **Mixing cents with different currency units:** a clear currency/precision model is needed.
12. **Using a record with a mutable `List` and assuming deep immutability:** risks data changing after validation.
13. **Putting database I/O inside `when`:** the guard may run without the branch being selected, causing unintended side effects.
14. **Allowing a cancelled `Order` with missing data without changing the policy:** in this article, validation takes precedence over CANCELLED; different requirements must be reflected in design/tests.
15. **Adding `default -> "OK"` to an exhaustive switch just to silence errors:** can hide unhandled new subtypes or statuses.
16. **Using `equals` as a substitute for entity identity:** record value equality may differ from "same order id" in the domain.
17. **Assuming `record` automatically solves JSON deserialization/schema issues:** mapping and backward compatibility belong to a different layer.
18. **Hiding too many rules in a single case label:** deep nesting + long guards can be less readable than a clearly named helper.
19. **Catching every `RuntimeException` and treating it as an invalid order:** can mask programming bugs, infrastructure errors, or unexpected `MatchException`s.
20. **Mixing order classification with transaction execution:** `route` is not sufficient proof to ship goods or process payment.

## 16. Extension Exercises

**Exercise 1 — Multi-line orders:** change `Line line` to `List<Line> lines`; write per-line validation and use `Math.addExact` for the total amount. Add tests for empty/null lists and lines with invalid values.

**Exercise 2 — Adding the `REFUNDED` status:** update the enum and rerun the classification logic. Define a dedicated branch returning `REFUNDED` or a clear business code, without letting it fall into Home/Pickup. Prove it with a test input that was previously paid but is now refunded.

**Exercise 3 — Store pickup:** add pickup time-slot information and validate the date/time. Consider a new record `Pickup(String storeId, LocalDateTime slot)` and its impact on existing patterns destructuring Pickup.

**Exercise 4 — Unserviceable address:** add an `isServiceable(Address)` rule as a pure predicate; distinguish invalid data errors from valid addresses outside the supported area.

**Exercise 5 — Separating DTO and domain types:** create `OrderRequest` for raw unvalidated input and `ValidatedOrder` for validated data. Compare the clarity of the switch when the domain type guarantees non-null components.

## 17. Code Review Checklist

- [ ] Does the `Order` record have the right components, order, and types according to the defined schema?
- [ ] Do child records (`Customer`, `Line`, `Home`/`Pickup`, `Address`) have clear immutability/validation?
- [ ] Do nested record patterns genuinely help express business structure rather than making the case label overly deep?
- [ ] Does `when` properly check `PAID`, VIP, and address/country without calling side-effecting methods?
- [ ] Is the order of VIP Home before general Home preserved?
- [ ] Are null selectors and null components at every level handled properly?
- [ ] Is there a plan to add branches to sealed `Delivery` and enum `Status` when the domain expands?
- [ ] Are `Math.multiplyExact`/`Math.addExact` used where overflow protection is needed?
- [ ] Does record value equality match expectations, or is entity identity by `orderId` needed?
- [ ] Are there tests for invalid structure, nulls, boundaries, new statuses, large order totals, and no side effects?
- [ ] If multiple Lines are added, are mutable collections and multi-line totals handled?
- [ ] If implementing a real API, are transactions, auth, pricing, logistics, and the error model placed in the appropriate layers?

**Conclusion:** Java 21 record patterns make it possible to "read" the **Order → Customer/Line/Delivery → Address** structure right inside the case label, making many classification branches intuitive and cast-free. Proper design requires combining **a clear record schema, validation before nested matching, pure `when` guards, intentional case ordering, arithmetic checks, and tests for every null level**. Pattern matching is a tool for expressing decisions; the order contract and business safety must still be defined by the program.

### References

- OpenJDK JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- OpenJDK JEP 395 — Records (Java 16): https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes (Java 17): https://openjdk.org/jeps/409
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.30 Patterns` and `14.11 Switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- Oracle Java 21 API — Math.multiplyExact: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)
