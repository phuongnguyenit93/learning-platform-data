# Extracting `customer` and `amount` in a Single Record Pattern (Java 21+)

## 1. Problem: extracting two pieces of data from a record in the same check

Suppose an order-processing application has orders, each with a **customer** (`customer`) and an **amount** (`amount`). If the data arrives at a method as a broad `Object` type, the traditional approach usually consists of a type check, a cast, and calling accessors:

~~~java
record Customer(String id, String name) {}
record Purchase(Customer customer, java.math.BigDecimal amount) {}

static String manual(Object input) {
    if (input instanceof Purchase) {
        Purchase purchase = (Purchase) input;
        Customer customer = purchase.customer();
        java.math.BigDecimal amount = purchase.amount();
        return customer.name() + ": " + amount.toPlainString();
    }
    return "Không phải Purchase";
}
~~~

Java 21 provides a more concise way: a **record pattern** can both check the outer type and extract **multiple record components in a single pattern**.

~~~java
static String withPattern(Object input) {
    if (input instanceof Purchase(var customer, var amount)) {
        return customer.name() + ": " + amount.toPlainString();
    }
    return "Không phải Purchase";
}
~~~

Here, `Purchase(var customer, var amount)` is **one record pattern**, not two separate `instanceof` checks and not a constructor call. The two variables `customer` and `amount` are bound according to the **order** of the two components in the record declaration.

**Goal of this article:** understand the mechanism of simultaneously extracting `customer` and `amount`, go a step further with a **nested record pattern** to get customer details, use `when` to filter the amount, handle `null` in the right places, and verify with a runnable example.

Record patterns were standardized in **Java 21 (JEP 440)**; pattern matching for `switch` was standardized in the same version (JEP 441). With JDK 21+, the features in this article **do not require `--enable-preview`**.

> The short examples in each section are illustrative snippets. A standalone, compilable, and runnable program is in section 8.

## 2. Record components define the exact two positions

Consider:

~~~java
record Customer(String id, String name) {}
record Purchase(Customer customer, BigDecimal amount) {}
~~~

(In an actual file, import `java.math.BigDecimal`.)

The `Purchase` declaration has **exactly two components**:

| Position | Component name | Static type | Extracted value |
| --- | --- | --- | --- |
| 1 | `customer` | `Customer` | Customer object |
| 2 | `amount` | `BigDecimal` | Transaction amount |

A valid pattern:

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    // customer has type Customer
    // amount has type BigDecimal
}
~~~

There is no rule requiring variable names to match the record component names. This example is also valid:

~~~java
if (input instanceof Purchase(var buyer, var total)) {
    System.out.println(buyer.name() + ": " + total);
}
~~~

In essence, the compiler matches **position 1 with `Customer`, position 2 with `BigDecimal`**, and then infers the variable types from the declaration.

**Important warning:** if two components have the same type, mixing up names and positions may still compile but have the wrong meaning. With `record Transfer(String from, String to) {}`, the pattern `Transfer(var destination, var source)` is type-valid but assigns names opposite to their actual meaning. Review by **component order**, not by intuition from variable names.

## 3. `var` in a record pattern is static type inference

`var` in `Purchase(var customer, var amount)` is **not** dynamic typing. It is a *variable pattern* whose type the compiler can infer based on the corresponding component:

- `customer`: static type `Customer`.
- `amount`: static type `BigDecimal`.

Explicit type patterns can be declared:

~~~java
if (input instanceof Purchase(Customer customer, BigDecimal amount)) {
    System.out.println(customer.id() + " / " + amount.toPlainString());
}
~~~

For components referencing their exact static types, this has a meaning close to `Purchase(var customer, var amount)`. `var` is concise when the types are already obvious; explicit types are useful if a review needs to clearly see the data contract.

When using the variables inside the `if` body, the compiler already knows the pattern succeeded, so there is no need for:

~~~java
// Redundant cast after record pattern:
// Customer customer = (Customer) purchase.customer();
~~~

Outside of `if`, pattern variables are subject to **flow scoping** rules. You cannot use `customer` or `amount` on every line just because you wrote them in the condition.

Correct example:

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    System.out.println(customer.id()); // Available in the matching branch.
}
// Do not assume customer/amount are still in scope here.
~~~

Scope errors or duplicate variable names in a pattern can prevent the code from compiling. Name variables clearly and use them within the region guaranteed by the compiler to have matched.

## 4. From a two-component pattern to a nested record pattern

Suppose you need to get the **customer name** and **amount**, not just the `Customer` object. There are two ways.

### Approach A — extract `customer` then call the accessor

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    String name = customer.name();
    System.out.println(name + ": " + amount.toPlainString());
}
~~~

This approach is clear when the customer is guaranteed to be non-null by data invariant. If `customer == null`, `customer.name()` causes an NPE.

### Approach B — also deconstruct the inner `Customer` record

~~~java
if (input instanceof Purchase(
        Customer(var customerId, var customerName),
        var amount)) {

    System.out.println(customerName + " (" + customerId
            + "): " + amount.toPlainString());
}
~~~

The entire `Purchase(Customer(var customerId, var customerName), var amount)` is still **an outer record pattern** containing a **nested record pattern**:

~~~text
Purchase
├── component 1: customer (Customer)
│   ├── component 1: customerId
│   └── component 2: customerName
└── component 2: amount (BigDecimal)
~~~

Matching process:

1. The input must match the record type `Purchase`.
2. The first component must match the record `Customer`.
3. The compiler/VM extracts `id` and `name` of `Customer` and binds the two pattern variables.
4. The second component of `Purchase` is bound to `amount`.
5. Only when the entire pattern matches does the `if` body or case run.

**Note:** a nested record pattern does not call the `new Customer(...)` constructor, does not create a new Customer object, and does not assert that the customer's name/id has been validated. It only deconstructs the existing value.

## 5. `null`: differences between the outer record, customer, and amount

This is the most important point to check when extracting `customer` and `amount` in one pattern.

### 5.1. Selector is `null`

~~~java
Object value = null;

boolean ok = value instanceof Purchase(var customer, var amount);
System.out.println(ok); // false
~~~

With `instanceof`, a record pattern **does not match null**; the expression returns `false` without throwing an NPE from the type check.

However, `switch (value)` has a different rule: when the selector is `null` and there is **no `case null`**, switching on a reference selector throws `NullPointerException` (even if `default` is present).

### 5.2. `customer == null` in the outer record

Suppose the data comes from a record that is allowed to contain a null component:

~~~java
Purchase purchase = new Purchase(null, new BigDecimal("100"));
~~~

Direct pattern:

~~~java
if (purchase instanceof Purchase(var customer, var amount)) {
    System.out.println(customer == null); // true
}
~~~

`var customer` is an unconditional component pattern for the component type `Customer`, so it can **bind null**. Therefore the branch executes, but you must not blindly call `customer.name()`.

Nested pattern:

~~~java
if (purchase instanceof Purchase(Customer(var id, var name), var amount)) {
    // Does not run: nested record Customer(...) does not match null.
}
~~~

The outer `Purchase` pattern is valid, but **the entire nested pattern does not match** because the customer component is null. These two cases must be clearly distinguished during code review.

### 5.3. `amount == null` in the outer record

~~~java
Purchase purchase = new Purchase(
        new Customer("C-7", "An"), null);
~~~

The direct pattern `Purchase(var customer, var amount)` can match and bind `amount == null`. The nested pattern `Purchase(Customer(var id,var name),var amount)` can also match because Customer exists; `var amount` itself does not block null.

Therefore:

~~~java
// UNSAFE if amount can be null:
// amount.signum() > 0

// SAFE:
amount != null && amount.signum() > 0
~~~

**Conclusion:** a record pattern gives you **static type** and **structure**, not a guarantee that all reference components are non-null. Null conditions need a clear contract at the constructor, boundary, or handling branch.

## 6. Extracting `customer` and `amount` with `switch`, combined with `when`

For multiple conditions on `amount`, a Java 21 `switch` expression helps express the classification rules:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case null -> "Không có đơn";

        case Purchase(Customer(var id, var name), var amount)
                when amount != null && amount.signum() > 0 ->
            name + " thanh toán " + amount.toPlainString();

        case Purchase(Customer(var id, var name), var amount)
                when amount != null && amount.signum() == 0 ->
            name + " có số tiền bằng 0";

        case Purchase(Customer(var id, var name), var amount) ->
            name + " có số tiền null hoặc âm";

        case Purchase(var customer, var amount) ->
            "Thiếu khách hàng";

        default -> "Không phải Purchase";
    };
}
~~~

Read in **order**:

1. `case null` handles a null selector (if null is an allowed input).
2. The `Purchase(Customer(...), var amount)` branch with the first guard is only selected when Customer is present **and** amount is non-null and positive.
3. The branch with the second guard is only selected when Customer is present **and** amount is non-null and equal to 0.
4. The unguarded nested branch catches the remaining Purchases that have Customer present; here amount is **negative or null**.
5. The general `Purchase(var customer, var amount)` branch comes last in the Purchase group to handle a null Customer.
6. `default` is for types not belonging to Purchase; it does **not** replace `case null`.

Why place specific branches before general branches? If `case Purchase(var customer, var amount)` were placed at the top, it would already match every (non-null) Purchase before the specialized patterns, causing the compiler to report a **dominated case label** for the subsequent branches.

### Guards only run after the pattern matches

`amount != null && amount.signum() > 0` has **short-circuiting**: `signum()` only runs after checking that amount is non-null. If the Customer component is null, the nested Customer pattern does not match, so the corresponding guard is not evaluated.

Do not put I/O, database writes, or mutations into a guard just to select a case. Simple, side-effect-free guards are generally easier to review and test.

## 7. `BigDecimal`: reading amounts properly, without relying on `==`

Monetary data usually uses `BigDecimal` instead of `double` to avoid binary representation inaccuracies in decimal calculations. In Java:

~~~java
BigDecimal amount = new BigDecimal("125000.00");
int sign = amount.signum();
~~~

`signum()` returns:

- `1` if positive.
- `0` if equal to 0.
- `-1` if negative.

To compare numerical values:

~~~java
BigDecimal left = new BigDecimal("10.0");
BigDecimal right = new BigDecimal("10.00");

System.out.println(left.compareTo(right) == 0); // true
System.out.println(left.equals(right));          // false
~~~

`compareTo` compares **numerical value** (without requiring the same scale), whereas `BigDecimal`'s `equals` also considers **scale**. `==` on two BigDecimal objects is a reference comparison, not an amount comparison.

**Do not create a BigDecimal from a `double` literal when an exact decimal value is needed:**

~~~java
// Recommended:
new BigDecimal("0.10");

// Be careful with:
new BigDecimal(0.10); // May carry binary representation inaccuracy.
~~~

In a real application, amount also needs policies for **currency, scale, rounding, range, and sign**. This demo treats amount as a nominal monetary figure and does not handle multiple currencies or tax calculations. When summing/valuing by currency, consider a value object such as `Money(BigDecimal amount, Currency currency)` and explicit rounding rules.

Notably: a record containing `BigDecimal` has an `equals()` based on the component's `BigDecimal.equals()`. Two records that are numerically equal but have different scales may not be equal according to `record.equals()`. Do not use value equality as proof that two transactions represent the same business request.

## 8. Complete, runnable Java 21+ program

The following code intentionally **allows Customer or amount to be null in `Order`** to illustrate how record patterns match and how fallback branches handle missing input data. This is an **input/test data** model, **not** a recommendation to store business Orders with broken invariants. `Customer` has a compact constructor that validates id/name; `Order` only validates orderId. Section 10 presents how to tighten invariants in a domain model.

Save as **`CustomerAmountPatternDemo.java`**:

~~~java
import java.math.BigDecimal;

public class CustomerAmountPatternDemo {
    record Customer(String id, String name) {
        public Customer {
            id = required(id, "id");
            name = required(name, "name");
        }
    }

    record Order(String orderId, Customer customer,
                 BigDecimal amount) {
        public Order {
            orderId = required(orderId, "orderId");
        }
    }

    static String required(String text, String field) {
        if (text == null || text.isBlank())
            throw new IllegalArgumentException(
                    field + " không được trống");
        return text.strip();
    }

    static String direct(Object input) {
        if (input instanceof Order(var id, var customer, var amount)) {
            return "Direct " + id + ": customer=" +
                    (customer == null ? "null" : customer.id()) +
                    ", amount=" +
                    (amount == null ? "null" : amount.toPlainString());
        }
        return "Direct: không phải Order";
    }

    static String nested(Object input) {
        if (input instanceof Order(
                var id,
                Customer(var customerId, var name),
                var amount)) {

            return "Nested " + id + ": "
                    + name + " (" + customerId + "), amount="
                    + (amount == null ? "null" : amount.toPlainString());
        }
        return "Nested: không khớp";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL_SELECTOR";

            case Order(var id, Customer(var cid, var name), var amount)
                    when amount != null && amount.signum() > 0 ->
                "POSITIVE " + id + ": " + name + " / "
                        + amount.toPlainString();

            case Order(var id, Customer(var cid, var name), var amount)
                    when amount != null && amount.signum() == 0 ->
                "ZERO " + id + ": " + name;

            case Order(var id, Customer(var cid, var name), var amount) ->
                "BAD_AMOUNT " + id + ": "
                        + (amount == null
                                ? "null" : amount.toPlainString());

            case Order(var id, var customer, var amount) ->
                "MISSING_CUSTOMER " + id;

            default -> "OTHER_TYPE";
        };
    }

    public static void main(String[] args) {
        Customer an = new Customer(" C-7 ", " An ");
        Order paid = new Order(
                " O-1 ", an, new BigDecimal("125000.00"));

        System.out.println(direct(paid));
        System.out.println(nested(paid));
        System.out.println(classify(paid));

        System.out.println(classify(
                new Order("O-2", an, BigDecimal.ZERO)));
        System.out.println(classify(
                new Order("O-3", an, new BigDecimal("-100"))));
        System.out.println(classify(
                new Order("O-4", an, null)));
        System.out.println(classify(
                new Order("O-5", null, BigDecimal.TEN)));
        System.out.println(nested(
                new Order("O-5", null, BigDecimal.TEN)));

        System.out.println(classify(null));
        System.out.println(classify("unknown"));

        System.out.println(
                new BigDecimal("10.0")
                        .compareTo(new BigDecimal("10.00")) == 0);
        System.out.println(
                new BigDecimal("10.0")
                        .equals(new BigDecimal("10.00")));

        try {
            new Customer("  ", "An");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "VALIDATION " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 -encoding UTF-8 CustomerAmountPatternDemo.java
java CustomerAmountPatternDemo
~~~

**Exact output:**

~~~text
Direct O-1: customer=C-7, amount=125000.00
Nested O-1: An (C-7), amount=125000.00
POSITIVE O-1: An / 125000.00
ZERO O-2: An
BAD_AMOUNT O-3: -100
BAD_AMOUNT O-4: null
MISSING_CUSTOMER O-5
Nested: không khớp
NULL_SELECTOR
OTHER_TYPE
true
false
VALIDATION id không được trống
~~~

### Reading the results by execution path

- **`Direct O-1`**: one record pattern `Order(var id, var customer, var amount)` binds both customer and amount. `Order` has three components, so all three positions are required.
- **`Nested O-1`**: nested `Customer(var customerId, var name)` also extracts id/name within the pattern itself, while `var amount` extracts the Order's BigDecimal.
- **`POSITIVE`**: Customer present, positive amount, guard is true.
- **`ZERO`**: Customer present, amount equals 0, first guard is false and second is true.
- **`BAD_AMOUNT O-3/O-4`**: amount is negative or null; nested Customer still matches and the guards do not select the positive/zero branches.
- **`MISSING_CUSTOMER`**: Customer component is null, nested Customer does not match; the general Order branch still matches.
- **`Nested: không khớp`**: the same object with a null Customer makes `instanceof` with the nested record pattern return `false`.
- **`NULL_SELECTOR`**: thanks to `case null`, no NPE is thrown when the selector is null.
- **`OTHER_TYPE`**: input is a String, not an Order.
- **`true/false`**: BigDecimal `compareTo` and `equals` give different results when scales differ.
- **`VALIDATION`**: Customer's compact constructor rejects an empty id.

There is no I/O other than `System.out.println`; the program uses no database, HTTP, or frameworks so learners can focus on pattern structure and conditions.

## 9. When to choose `if instanceof`, and when to choose `switch`?

### Choose `if instanceof` when you only need to extract once

~~~java
if (input instanceof Order(var id, var customer, var amount)) {
    // Both customer and amount are ready in the branch.
}
~~~

This is short and clear for a single processing path. You can add conditions after the match:

~~~java
if (input instanceof Order(var id, var customer, var amount)
        && customer != null && amount != null
        && amount.signum() > 0) {
    System.out.println(customer.name() + " / "
            + amount.toPlainString());
}
~~~

The short-circuit `&&` operator ensures `customer.name()` and `amount.signum()` are only called after checking for valid values. Note that a null selector makes `instanceof` false without throwing an NPE from this check.

### Choose `switch` when you need to classify multiple situations

~~~java
return switch (value) {
    case null -> "NULL";
    case Order(var id, Customer(var cid, var name), var amount)
            when amount != null && amount.signum() > 0 ->
        "Khách " + name + " đã có amount dương";
    case Order(var id, var customer, var amount) ->
        "Đơn không đủ điều kiện";
    default -> "Kiểu khác";
};
~~~

`switch` makes the **order and scope** of branches clear; it is especially useful with nested record patterns or sealed hierarchies with many subtypes. However, there is no need to force a simple `instanceof` condition into a long switch just to use a Java 21 feature.

**Limitation of the example:** do not infer performance from syntactic form. HotSpot can optimize both, and choosing a dispatch style should prioritize correctness/maintainability; benchmarks are only needed when there is a specific performance requirement.

## 10. If the domain forbids missing `customer`/`amount`, validate in the constructor

In the section 8 example, `Order` intentionally allows the two reference components to be null to test the branches. If a **valid domain Order** must have a customer and a positive amount, the type design should protect invariants at creation time:

~~~java
record StrictOrder(String orderId,
                   Customer customer,
                   BigDecimal amount) {
    public StrictOrder {
        orderId = required(orderId, "orderId");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0)
            throw new IllegalArgumentException(
                    "amount phải dương");
    }
}
~~~

If an amount equal to 0 is valid in the domain, change the condition to `amount.signum() < 0`. The goal is not to forbid every null value at all costs, but to **place the rule in the right data layer**.

Two common ways to organize this:

1. **Input DTO that may be missing data** (for example raw JSON): intentionally accept nullable fields, validate/convert at the boundary, and return structured errors.
2. **Validated domain record/value object**: the constructor guarantees invariants such as non-null and positive amount; downstream processing can rely on this contract.

If `amount` comes from an external system, you should also check currency, digit limits, scale, rounding mode, and the risk of exceeding business limits. A valid Java `BigDecimal` **does not** by itself guarantee that it is an allowed monetary amount.

**Do not do this:** silently convert null to `BigDecimal.ZERO` if the domain treats "missing amount" differently from "zero amount". Assigning a default loses information about missing data.

## 11. Common compile-time errors when extracting two components

### 11.1. Wrong number of component patterns

~~~java
record Purchase(Customer customer, BigDecimal amount) {}

// INTENTIONALLY WRONG: Purchase has two components but only one pattern is provided.
// if (value instanceof Purchase(var customer)) { ... }
~~~

The error message usually falls under `incorrect number of nested patterns`. You must provide **two positions**:

~~~java
if (value instanceof Purchase(var customer, var amount)) {
    // ...
}
~~~

In the complete example, `Order` has **three** components (`orderId`, `customer`, `amount`), so there must be three component patterns: `Order(var id, var customer, var amount)`. You cannot directly extract only the last two positions by omitting the first component:

~~~java
// INTENTIONALLY WRONG if Order has 3 components:
// Order(var customer, var amount)
~~~

If `orderId` is not needed, you must still place a pattern for that position, for example `Order(var ignoredId, var customer, var amount)`.

### 11.2. Mixing up the types of the two components

~~~java
// INTENTIONALLY WRONG: customer is declared as type Customer, not String.
// if (value instanceof Purchase(String customer, BigDecimal amount)) { ... }
~~~

A record pattern must be compatible with the **static type of each component**; you cannot expect the compiler to automatically convert `Customer` to `String` just because the object has a name property.

Fix with `Purchase(Customer customer, BigDecimal amount)`, `Purchase(var customer, var amount)`, or the nested pattern `Purchase(Customer(var id, var name), var amount)`.

### 11.3. Using a record pattern with a regular class

~~~java
class PlainPurchase {
    PlainPurchase(Customer customer, BigDecimal amount) {}
}

// INTENTIONALLY WRONG: PlainPurchase is not a record.
// if (value instanceof PlainPurchase(var customer, var amount)) { ... }
~~~

In Java 21, **a record pattern is not a general-purpose constructor pattern**. A class having a constructor with two parameters is not enough for `PlainPurchase(...)` to be a valid record pattern. Use a type pattern `PlainPurchase p` and accessors, or choose a record when it fits the data model.

### 11.4. Confusing `when` with `instanceof` syntax

`when` is a guard in a **pattern switch case**. In an `if`, chain conditions with `&&`:

~~~java
// CORRECT with instanceof:
if (input instanceof Purchase(var customer, var amount)
        && amount != null && amount.signum() > 0) {
    // ...
}
~~~

Do not write `input instanceof Purchase(...) when amount.signum() > 0` as in a case label.

### 11.5. General case shadowing a specialized case

~~~java
// INTENTIONALLY WRONG ORDER, may be reported as a dominated case:
// case Order(var id, var customer, var amount) -> "OTHER_ORDER";
// case Order(var id, Customer(var cid, var name), var amount)
//         when amount != null -> "HAS_CUSTOMER";
~~~

The general `case Order(...)` already matches every valid non-null Order, so specialized nested/guarded cases must be placed **first**, with the fallback case last.

### 11.6. `default` alone does not handle a null selector

~~~java
// Runtime NPE if selector is null, even with default:
// return switch (value) {
//     case Purchase(var customer, var amount) -> "Purchase";
//     default -> "Other";
// };
~~~

Add `case null` if null is valid, or explicitly reject null at the boundary. Do not equate "compile-time exhaustive switch" with "runtime null-safe".

## 12. Test matrix for the customer + amount problem

To verify that a pattern extracts **the exact two pieces of data** and handles all important cases:

| Input | Expected | What it proves |
| --- | --- | --- |
| Purchase(valid Customer, positive amount) | Matches, extracts customer and amount | Correct two component positions |
| Purchase(valid Customer, 0 amount) | Matches, takes zero branch | Positive guard false, zero true |
| Purchase(valid Customer, negative amount) | Matches, handles invalid amount | False guards not missed |
| Purchase(valid Customer, null amount) | `var amount` receives null, does not wrongly call `signum()` | Null component differs from null selector |
| Purchase(null, positive amount) | Direct pattern matches; nested Customer does not match | Difference between `var` and nested record pattern |
| `null` input | `instanceof` false or `case null` | Null selector is explicitly handled |
| String input | Does not match Purchase | Proper type checking |
| Empty Customer id/name | Constructor rejects if domain requires | Data invariant |
| BigDecimal `10.0` and `10.00` | `compareTo == 0`, `equals == false` | Does not confuse numeric comparison with scale |

When code uses a guard like `amount != null && amount.signum() > 0`, tests need cases for null, positive, zero, and negative amounts. Do not just test that **the case ran at least once** while skipping the other conditional paths.

For real monetary orders, add tests for currency, precision/scale, rounding, large numbers, amount limits, and data from serializers. The record pattern structure can be right while the monetary business rules are still wrong.

## 13. JUnit 5 example: asserting the extraction instead of just printing to console

If you put the section 8 program into a project with JUnit 5, you can verify the results with assertions. This is a **test snippet using the nested types inside `CustomerAmountPatternDemo`**, not a standalone runnable file without the JUnit dependency:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class CustomerAmountPatternDemoTest {
    @Test
    void extractsCustomerAndAmountTogether() {
        var customer =
                new CustomerAmountPatternDemo.Customer("C-7", "An");
        var order = new CustomerAmountPatternDemo.Order(
                "O-1", customer, new BigDecimal("125000.00"));

        assertEquals(
                "Direct O-1: customer=C-7, amount=125000.00",
                CustomerAmountPatternDemo.direct(order));
        assertEquals(
                "Nested O-1: An (C-7), amount=125000.00",
                CustomerAmountPatternDemo.nested(order));
    }

    @Test
    void differentiatesMissingCustomerFromNullAmount() {
        var customer =
                new CustomerAmountPatternDemo.Customer("C-7", "An");

        assertEquals("BAD_AMOUNT O-4: null",
                CustomerAmountPatternDemo.classify(
                    new CustomerAmountPatternDemo.Order(
                        "O-4", customer, null)));

        assertEquals("MISSING_CUSTOMER O-5",
                CustomerAmountPatternDemo.classify(
                    new CustomerAmountPatternDemo.Order(
                        "O-5", null, BigDecimal.TEN)));
    }

    @Test
    void rejectsInvalidCustomer() {
        assertThrows(IllegalArgumentException.class,
                () -> new CustomerAmountPatternDemo.Customer(
                        " ", "An"));
    }
}
~~~

With the nested `Customer` and `Order` types declared without the `private` modifier in the example, a test in the same package can reference them as shown above. A real project should have a clear package and properly versioned Maven/Gradle/JUnit configuration.

**Testing takeaway:** the extracted `customer` and `amount` results are concrete data being asserted, not just checking that a `case` branch was invoked. The tests also separate two different reasons leading to a fallback: **null customer** and **null amount**.

## 14. Code review checklist for a multi-component record pattern

- [ ] The record declares the right components **in the right order**.
- [ ] A single pattern contains **the full number of positions**: `Purchase(var customer, var amount)` has two; `Order(var id, var customer, var amount)` has three.
- [ ] `var` is understood as an inferred static type, not as making data automatically non-null.
- [ ] For nested `Customer(...)`, has the case of a null Customer component been considered?
- [ ] If a null amount is allowed, are all calls to `amount.signum()`, `compareTo()`, `toPlainString()` guarded on the corresponding path?
- [ ] When using `switch`, do specific guarded cases come before general cases to avoid dominance?
- [ ] Does a null selector have a `case null` policy or an explicit null-rejection contract?
- [ ] Is `BigDecimal` initialized/compared for the intended purpose; is `==` avoided for numeric value comparison?
- [ ] Does the domain order have invariants that should be checked upon creation? Are nullable DTOs being mixed up with valid domain records?
- [ ] Do tests verify the actual values of **customer and amount**, true/false guards, and null cases?
- [ ] If the record schema changes, do other record patterns need their component arity updated?

This is a review checklist focused on **program correctness and data contracts**, not a standard forcing all code into multi-level nested patterns.

## 15. Practice exercises

**Exercise 1 — Extract two components.** Create `record Invoice(Customer customer, BigDecimal amount) {}`. Write a single `if instanceof` that extracts both `customer` and `amount`, printing `customer.id()` and amount when both are non-null.

**Exercise 2 — Nested customer.** Given `record Customer(String id, String name) {}`, replace `Invoice(var customer, var amount)` with a pattern that directly extracts `name` and `amount`. If Customer is null, does the pattern match?

**Exercise 3 — Order.** Why does `record Invoice(Customer customer, BigDecimal amount)` not allow using `Invoice(var amount, var customer)` to swap the value order, even though the variable names are valid?

**Exercise 4 — Guard.** Write a `switch` with branches for: null selector, positive amount, non-positive/missing amount, and other types. What must the guard check before calling `signum()`?

**Exercise 5 — BigDecimal.** The two objects `new BigDecimal("5.0")` and `new BigDecimal("5.00")` differ under `equals` but are equal under `compareTo`. Why is that a situation to consider if the `Invoice` record uses `equals()` for business logic?

**Exercise 6 — Tighten invariants.** Design a compact constructor for a domain record `Invoice` to reject a null customer, null amount, and negative amount. Keep amount = 0 valid. Why does a DTO receiving external JSON still need schema error handling before or when creating the domain record?

### Suggested answers

~~~java
// Exercise 1:
if (value instanceof Invoice(var customer, var amount)
        && customer != null && amount != null) {
    System.out.println(customer.id() + " / "
            + amount.toPlainString());
}

// Exercise 2:
if (value instanceof Invoice(
        Customer(var id, var name), var amount)) {
    System.out.println(name + " / " + amount);
}

// Exercise 6, constructor sketch for record Invoice:
record Invoice(Customer customer, BigDecimal amount) {
    public Invoice {
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0)
            throw new IllegalArgumentException("amount phải >= 0");
    }
}
~~~

- Exercise 2: nested `Customer(...)` **does not match** when the Customer component is null; use a fallback case or validation if needed.
- Exercise 3: patterns match **by position**, not by swapping based on variable names. Renaming only changes the label of the received value; with different types, subsequent usage can cause a compile-time error.
- Exercise 4: `amount != null && amount.signum() > 0`; if the null check is missing, the guard can throw an NPE.
- Exercise 5: `record.equals` relies on the component's `BigDecimal.equals`, so `equals` must not be used as a numeric monetary comparison policy without normalizing scale/contract.
- Exercise 6: a DTO may contain missing/malformed data; converting to a domain record requires intentional validation and clear error reporting.

## 16. Summary

To **extract `customer` and `amount` in a single pattern** in Java 21:

1. Declare the record according to the data structure: `record Purchase(Customer customer, BigDecimal amount) {}`.
2. Use one record pattern: `input instanceof Purchase(var customer, var amount)`.
3. If you need information inside Customer, use nesting: `Purchase(Customer(var id, var name), var amount)`.
4. When there are multiple rules on amount, combine `case` and `when`, but always check for null before calling methods on `amount`.
5. Distinguish between a `null` selector, a `null` customer component, and a `null` amount component: they have different matching behavior.
6. Use `BigDecimal.compareTo`/`signum` to compare numeric values; do not confuse them with `equals` which checks scale.
7. Place appropriate invariants in constructors/domain boundaries, while record patterns are only responsible for **checking structure and extracting values**, not replacing business validation.

### References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record deconstruction, nested component patterns, and type inference (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `switch`, `when` guards, case ordering, and null semantics.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): examples and applicable syntax.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): rules for type/record patterns and matching.
- [Java SE 21 API — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `compareTo`, `equals`, `signum`, and scale.
