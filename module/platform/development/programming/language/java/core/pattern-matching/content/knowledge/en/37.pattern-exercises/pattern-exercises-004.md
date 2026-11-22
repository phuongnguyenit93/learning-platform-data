# Writing Nested Record Patterns in Java 21

## 1. Comprehensive Practice: Multi-Layer Order Request Data

In Java, a record can contain another record. When processing data from an API, command handler, message queue, or domain model, we often encounter structures such as:

```text
Request (sealed interface)
├── CancelOrder(id)
└── PlaceOrder(order)
    └── Order(customer, destination, payment, count)
        ├── Customer(name, contact)
        │   └── Contact(email)
        ├── Destination(city, district)
        └── Payment (sealed interface)
            ├── Card(last4)
            └── Cash()
```

We want to write a **`classify(Request)`** function that handles:
- Null request → `NO_REQUEST`.
- Order cancellation with a blank ID → `INVALID_CANCEL`; valid ID → `CANCEL:<id>`.
- Placing an order where `order == null` → `MISSING_ORDER`.
- Order missing customer, destination, payment, or `count <= 0` → `INVALID_ORDER`.
- Card payment, quantity at least 10, and email present → `BULK_CARD`.
- Standard card payment → `CARD`.
- Cash payment → `CASH`.
- Deeper missing record such as `Customer.contact == null` → `INCOMPLETE_DETAILS`.

Previously, code often used a chain of `instanceof` checks, casts, and accessors with multiple null-check branches. Java 21's **nested record patterns** allow writing the shape of the data to be checked directly inside the pattern:

```java
// An illustrative case; the full types are declared later.
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count)) ->
    "CARD:" + name + ":" + city + ":" + count;
```

Reading from the outside in: this is a `PlaceOrder` containing an `Order`; `Order` contains a `Customer` with `Contact`, a `Destination`, a `Card`, and a count. If the record patterns match, Java binds the component variables to their exact types without manual casting.

**This lesson guides you from simple patterns to multi-level nested patterns, then covers comprehensive testing, null/guard handling, compiler errors, and practical limitations.**

Versions:
- `record` became standard in Java 16.
- `sealed class`/`sealed interface` became standard in Java 17.
- **Record patterns (JEP 440)** and **pattern matching for `switch` (JEP 441)** became standard in **Java 21**, without needing `--enable-preview`.

The main example uses `javac --release 21` and a single Java SE file.

## 2. Distinguishing Type Patterns, Record Patterns, and Nested Record Patterns

### Type pattern

```java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` checks that the object has a matching type and binds the `text` variable. When `null` is the operand of `instanceof`, the result is always false.

### Record pattern

Given a record:

```java
record Destination(String city, String district) {}
```

We can match directly:

```java
if (value instanceof Destination(String city, String district)) {
    System.out.println(city + "/" + district);
}
```

`Destination(String city, String district)` is a **record pattern**, not a constructor call. It checks the outer record and its component patterns. When it succeeds, `city`/`district` are bound variables.

### Nested record pattern

```java
record Contact(String email) {}
record Customer(String name, Contact contact) {}
```

When used as:

```java
if (value instanceof Customer(String name, Contact(String email))) {
    System.out.println(name + ":" + email);
}
```

Java must match `Customer` and then match the `Contact` record in the `contact` component. If the `contact` component is null, the nested `Contact(...)` record pattern **does not match**. This is a normal non-match, not a `MatchException`.

The difference: a **type pattern** checks the type and binds; a **record pattern** checks the record and continues matching its components; a **nested record pattern** uses one record pattern as a component pattern of another record.

## 3. Record Declarations Determine Deconstruction Syntax

The model used in the program:

```java
sealed interface Request permits PlaceOrder, CancelOrder {}

record PlaceOrder(Order order) implements Request {}
record CancelOrder(String id) implements Request {}

record Order(Customer customer, Destination destination,
             Payment payment, int count) {}
record Customer(String name, Contact contact) {}
record Contact(String email) {}
record Destination(String city, String district) {}

sealed interface Payment permits Card, Cash {}
record Card(String last4) implements Payment {}
record Cash() implements Payment {}
```

**A record pattern must have the exact same number of nested patterns as record components**, in the exact declaration order.

For example, `Order` has four components:

| Position | Component | Type | Corresponding pattern |
| --- | --- | --- | --- |
| 1 | `customer` | `Customer` | `Customer(...)` or `var customer` |
| 2 | `destination` | `Destination` | `Destination(...)` or `var destination` |
| 3 | `payment` | `Payment` | `Card(...)`, `Cash()`, or `var payment` |
| 4 | `count` | `int` | `int count` or `var count` |

A valid pattern:

```java
Order(var customer, var destination, var payment, int count)
```

A more specific pattern:

```java
Order(Customer(var name, var contact),
      Destination(var city, var district),
      Card(var last4), int count)
```

The second pattern **only accepts an Order whose Payment is a Card**, because `Card(...)` is a record pattern for a subtype of `Payment`.

You cannot reorder components to make them "easier to remember": `Order(int count, Customer(...), ...)` will not match the declaration. You cannot write `Order(Customer customer)` to omit the other three components. If you do not need deep deconstruction, use `var` at each position you do not need to deconstruct.

**`Cash()` is valid:** The `Cash` record has zero components; the empty parentheses in the pattern mean the number of nested patterns is 0, not a constructor call.

## 4. Writing Nested Patterns Step by Step

Do not start with a six-level pattern if you only need one field. Expand as needed:

### Step 1 — Check the outer type

```java
if (request instanceof PlaceOrder place) {
    Order order = place.order();
    System.out.println(order);
}
```

`order` can be null. The benefit is simple, easy-to-debug code; the downside is having to access accessors and check structure with extra code.

### Step 2 — Deconstruct Order

```java
if (request instanceof PlaceOrder(Order(
        var customer, var destination, var payment, int count))) {
    System.out.println(count);
}
```

At this point `PlaceOrder.order()` must be a non-null `Order`. Reference variables created by `var` may contain null.

### Step 3 — Deconstruct Customer and Destination

```java
if (request instanceof PlaceOrder(Order(
        Customer(String name, var contact),
        Destination(String city, String district),
        var payment, int count))) {
    System.out.println(name + "@" + city + ":" + count);
}
```

The two new nested record patterns require both `customer` and `destination` to be non-null records of their respective types. However, `contact` is not yet `Contact(...)` — it is bound via `var`.

### Step 4 — Go deeper to Contact and Card

```java
if (request instanceof PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))) {
    System.out.println(name + ":" + city + ":" + count);
}
```

Now the matcher requires `Customer`, `Contact`, `Destination`, and `Card`. `Cash()` cannot match `Card(...)`; `customer.contact() == null` also causes the nested `Contact(...)` not to match.

**Keep nesting just deep enough.** If the problem only uses `count`, there is no good design reason to deconstruct `Contact.email` and `Card.last4`. A shorter pattern keeps code clear and less coupled to record structure.

## 5. One Pattern, Multiple Branches: `when` Guards

Suppose a card-paid order with `count >= 10` and a non-null email is a bulk order:

```java
// A case in a switch expression on Request.
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))
        when count >= 10 && email != null ->
    "BULK_CARD:" + city + ":" + last4 + ":" + count;
```

The **pattern** describes the structure, and the **guard** describes the additional condition. The guard is only evaluated after the associated pattern has matched:
- Guard true → the bulk case is selected.
- Guard false → other cases continue to be considered.
- Guard throws an exception → case selection completes abruptly; the exception is not treated as false.

Next is the unguarded Card case:

```java
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count)) ->
    "CARD:" + name + ":" + city + ":" + count;
```

A guarded case must appear **before** a case with the same record pattern without a guard. If the order is reversed, the general case will **dominate** the guarded case behind it.

One counterintuitive point: `new Contact(null)` is still a non-null `Contact` record, and `Contact(String email)` can bind `email == null` at the component position of type `String`. This is the **unconditional type pattern** rule in Java 21; it does not mean `null instanceof String` returns true. Therefore, the guard must check for null before calling `email.isBlank()`.

## 6. Null at Four Levels: Why Distinguish Them?

| Situation | Example | Result |
| --- | --- | --- |
| `instanceof` selector is null | `null instanceof Customer(...)` | False |
| `switch` selector is null and has a `case null` | `case null -> ...` | `case null` |
| `Order` component is null, using `var` | `PlaceOrder(var order)` | Binds `order=null`, outer pattern can match |
| `Order` component is null, using nested `Order(...)` | `PlaceOrder(Order(...))` | Nested record pattern does not match |
| `Contact` record exists, `email` is null | `Contact(String email)` | Component type pattern can bind null |
| `Customer` record exists, `contact` is null | `Customer(String n, Contact(...))` | Nested `Contact(...)` does not match |

This is why the demo has three handling layers:

```java
case null -> "NO_REQUEST";

case PlaceOrder(var order) when order == null ->
    "MISSING_ORDER";

case PlaceOrder(Order(
        var customer, var destination, var payment, int count))
        when customer == null || destination == null ||
             payment == null || count <= 0 ->
    "INVALID_ORDER";
```

The `PlaceOrder(Order(...))` pattern only runs when `order` is actually an `Order` record. Using `var` in the components lets the guard inspect null fields without requiring a specific nested record to match.

Toward the end of the switch, a case:

```java
case PlaceOrder(var order) -> "INCOMPLETE_DETAILS";
```

is kept **after the specialized cases** to catch remaining missing nested data, such as `Customer.contact == null`. If placed earlier, the subsequent Card/Cash cases would be dominated.

**Domain design:** A real production system should normally reject invalid data in constructors or at boundaries. In this exercise, the records intentionally do not validate immediately so we can observe each pattern outcome. Having a fallback should not be taken as a reason to allow storing objects that violate invariants.

## 7. Complete Java 21 Program and 13 Test Cases

Create the file **`NestedRecordPatternsWorkshop.java`** with the following content. The code uses only Java SE and has been run with `--release 21`:

```java
import java.util.Objects;

public class NestedRecordPatternsWorkshop {
    sealed interface Request permits PlaceOrder, CancelOrder {}
    record PlaceOrder(Order order) implements Request {}
    record CancelOrder(String id) implements Request {}

    record Order(Customer customer, Destination destination,
                 Payment payment, int count) {}
    record Customer(String name, Contact contact) {}
    record Contact(String email) {}
    record Destination(String city, String district) {}
    sealed interface Payment permits Card, Cash {}
    record Card(String last4) implements Payment {}
    record Cash() implements Payment {}

    static String classify(Request request) {
        return switch (request) {
            case null -> "NO_REQUEST";

            case CancelOrder(String id)
                    when id == null || id.isBlank() ->
                "INVALID_CANCEL";

            case CancelOrder(String id) ->
                "CANCEL:" + id;

            case PlaceOrder(var order) when order == null ->
                "MISSING_ORDER";

            case PlaceOrder(Order(
                    var customer, var destination,
                    var payment, int count))
                    when customer == null || destination == null ||
                         payment == null || count <= 0 ->
                "INVALID_ORDER";

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Card(String last4), int count))
                    when count >= 10 && email != null ->
                "BULK_CARD:" + city + ":" + last4 + ":" + count;

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Card(String last4), int count)) ->
                "CARD:" + name + ":" + city + ":" + count;

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Cash(), int count)) ->
                "CASH:" + name + ":" + district + ":" + count;

            case PlaceOrder(var order) ->
                "INCOMPLETE_DETAILS";
        };
    }

    static void assertCase(
            String label, Request request, String expected) {
        String actual = classify(request);
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                label + ": expected=" + expected +
                ", actual=" + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    record Traced(String value) {
        static int reads;

        @Override
        public String value() {
            reads++;
            return value;
        }
    }

    record Envelope(Traced traced) {}

    record Broken(String value) {
        @Override
        public String value() {
            throw new IllegalStateException("accessor failure");
        }
    }

    record BrokenEnvelope(Broken broken) {}

    public static void main(String[] args) {
        Customer lan =
            new Customer("Lan", new Contact("lan@example.test"));
        Destination danang =
            new Destination("Da Nang", "Hai Chau");
        Customer mai =
            new Customer("Mai", new Contact("mai@example.test"));

        assertCase("S01", null, "NO_REQUEST");
        assertCase("S02", new CancelOrder("A1"), "CANCEL:A1");
        assertCase("S03", new CancelOrder(" "), "INVALID_CANCEL");

        assertCase("S04", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 2)),
            "CARD:Lan:Da Nang:2");

        assertCase("S05", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 12)),
            "BULK_CARD:Da Nang:1234:12");

        assertCase("S06", new PlaceOrder(new Order(
            new Customer("Lan", new Contact(null)),
            danang, new Card("1234"), 12)),
            "CARD:Lan:Da Nang:12");

        assertCase("S07", new PlaceOrder(new Order(
            mai, new Destination("Ha Noi", "Ba Dinh"),
            new Cash(), 3)),
            "CASH:Mai:Ba Dinh:3");

        assertCase("S08", new PlaceOrder(null),
            "MISSING_ORDER");

        assertCase("S09", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 0)),
            "INVALID_ORDER");

        assertCase("S10", new PlaceOrder(new Order(
            lan, danang, null, 2)),
            "INVALID_ORDER");

        assertCase("S11", new PlaceOrder(new Order(
            null, danang, new Cash(), 2)),
            "INVALID_ORDER");

        assertCase("S12", new PlaceOrder(new Order(
            lan, null, new Cash(), 2)),
            "INVALID_ORDER");

        assertCase("S13", new PlaceOrder(new Order(
            new Customer("Lan", null), danang, new Cash(), 2)),
            "INCOMPLETE_DETAILS");

        Object complete = new Envelope(new Traced("OK"));
        if (!(complete instanceof
                Envelope(Traced(String value)) &&
                value.equals("OK"))) {
            throw new AssertionError("nested matching failed");
        }
        System.out.println("ACCESSOR_READS=" + Traced.reads);

        Object missingNested = new Envelope(null);
        boolean nestedMatch =
            missingNested instanceof
                Envelope(Traced(String missingValue));
        System.out.println("NULL_NESTED_MATCH=" + nestedMatch);

        try {
            Object broken =
                new BrokenEnvelope(new Broken("x"));
            boolean ignored = broken instanceof
                BrokenEnvelope(Broken(String brokenValue));
            throw new AssertionError(
                "Expected MatchException, got " + ignored);
        } catch (MatchException ex) {
            System.out.println("ACCESSOR_ERROR=" +
                ex.getClass().getSimpleName() + ":" +
                ex.getCause().getClass().getSimpleName());
        }

        System.out.println("TESTS=13");
    }
}
```

Compile and run on **JDK 21 or later**:

```bash
javac --release 21 NestedRecordPatternsWorkshop.java
java NestedRecordPatternsWorkshop
```

**Exact stdout:**

```text
S01 -> NO_REQUEST
S02 -> CANCEL:A1
S03 -> INVALID_CANCEL
S04 -> CARD:Lan:Da Nang:2
S05 -> BULK_CARD:Da Nang:1234:12
S06 -> CARD:Lan:Da Nang:12
S07 -> CASH:Mai:Ba Dinh:3
S08 -> MISSING_ORDER
S09 -> INVALID_ORDER
S10 -> INVALID_ORDER
S11 -> INVALID_ORDER
S12 -> INVALID_ORDER
S13 -> INCOMPLETE_DETAILS
ACCESSOR_READS=1
NULL_NESTED_MATCH=false
ACCESSOR_ERROR=MatchException:IllegalStateException
TESTS=13
```

There are **13 classification cases** S01–S13, plus observations for accessor reads, nested null, and `MatchException`. The `assertCase` method throws `AssertionError` on mismatch, so the `-ea` flag is not required.

**Note:** The strings, emails, and last four card digits in the demo are all dummy data. In production code, do not automatically log entire records; payment information, tokens, and personal data must be handled according to security policies.

## 8. Detailed Explanation of Results

| Test | Key input | Output | Meaning |
| --- | --- | --- | --- |
| S01 | Null Request | `NO_REQUEST` | `case null` |
| S02 | CancelOrder ID `A1` | `CANCEL:A1` | Invalid guard false, normal Cancel case |
| S03 | CancelOrder blank ID | `INVALID_CANCEL` | `isBlank()` true |
| S04 | Card, count 2, non-null email | `CARD` | Bulk guard false |
| S05 | Card, count 12, non-null email | `BULK_CARD` | Bulk guard true |
| S06 | Card, count 12, `Contact.email` null | `CARD` | `Contact` record still matches, bulk guard false |
| S07 | Cash, count 3 | `CASH` | Nested `Cash()` matches |
| S08 | `PlaceOrder.order` null | `MISSING_ORDER` | `var order` binds null |
| S09 | `Order.count` 0 | `INVALID_ORDER` | Guard `count <= 0` |
| S10 | `Order.payment` null | `INVALID_ORDER` | Guard catches null `Payment` |
| S11 | `Order.customer` null | `INVALID_ORDER` | Guard catches null `Customer` |
| S12 | `Order.destination` null | `INVALID_ORDER` | Guard catches null `Destination` |
| S13 | `Customer.contact` null | `INCOMPLETE_DETAILS` | Nested `Contact` does not match, fallback |

### Analyzing S06

`new Customer("Lan", new Contact(null))` has a non-null `Contact` record. `Contact(String email)` matches the record; the `email` component can be bound to null because it is an unconditional type pattern at a `String`-typed component. `count >= 10` is true, but `email != null` is false. Therefore, the `BULK_CARD` case is skipped and the unguarded `CARD` case is selected.

If business logic requires `email` to be non-null, add validation or an `INVALID_EMAIL` case. This is a **domain contract** decision, not something automatically guaranteed by a nested record pattern.

### Analyzing S13

`new Customer("Lan", null)` causes the nested `Contact(String email)` not to match. Since both the Card and Cash patterns require `Customer(..., Contact(...))`, neither applies. The final `PlaceOrder(var order)` case receives this request and returns `INCOMPLETE_DETAILS`.

**Do not confuse this:** A nested pattern not matching is a normal outcome. It does not throw `MatchException` just because a record component is null.

### Why are there two sealed hierarchies?

`Request` consists of `PlaceOrder` and `CancelOrder`, while `Payment` consists of `Card` and `Cash`. The compiler can verify that the root `switch` is exhaustive when a general `CancelOrder` case and a `PlaceOrder` fallback cover all `Request` subtypes. However, the compiler **does not prove that every `Payment` type is handled properly by business logic** if there is a broad `PlaceOrder` fallback.

If you add `Voucher` to `Payment` and forget to add a dedicated case, the fallback can still allow the root `switch` to compile, while returning `INCOMPLETE_DETAILS` for vouchers. Therefore, you need separate tests for each nested subtype rather than relying solely on root exhaustiveness.

## 9. Variable Scope and Flow Scoping

Pattern variables bound in a branch can be used in that branch's body and in the appropriate guard. For example:

```java
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))
        when count >= 10 && email != null ->
    "BULK_CARD:" + city + ":" + last4 + ":" + count;
```

`name`, `email`, `city`, `district`, `last4`, and `count` all have definite types, but **do not automatically become variables outside the `switch`**.

In `instanceof`:

```java
if (obj instanceof Customer(String name, Contact(String email))
        && email != null) {
    System.out.println(name + ":" + email.toLowerCase());
}
```

The right-hand side of `&&` can use `email` because Java only evaluates it when the pattern on the left has matched. However, using the variable outside the region guaranteed to match will be rejected by the compiler.

Intentionally wrong example:

```java
record Point(int x, int y) {}

static void check(Object obj) {
    if (obj instanceof Point(int x, int y)) {
        System.out.println(x);
    }
    System.out.println(x); // cannot find symbol
}
```

`javac` was tested with this case and reports the missing variable `x` on the line outside `if`. With complex conditional expressions, do not confuse pattern variable scope with ordinary local variable scope; the compiler applies **flow scoping** rules.

### Avoiding variable name collisions

In a method with multiple `instanceof` checks, pattern variables can have scopes that extend across certain control-flow paths. Reusing the name `value` repeatedly can cause the compiler to report that the variable is already defined. In the demo, the names `missingValue` and `brokenValue` differ from `value` to avoid conflicts.

## 10. Testing Record Accessors and MatchException

When deconstructing a record, Java calls its accessor methods to obtain the components. If a custom accessor has side effects, nested record patterns have observable behavior.

### Accessors are called when a nested pattern needs to read data

```java
record Traced(String value) {
    static int reads;

    @Override
    public String value() {
        reads++;
        return value;
    }
}
record Envelope(Traced traced) {}
```

With:

```java
Object complete = new Envelope(new Traced("OK"));
boolean match = complete instanceof Envelope(Traced(String text));
```

`Traced.value()` is called to match `Traced(String text)`. In the full program, the output is:

```text
ACCESSOR_READS=1
```

**Do not infer nanosecond timing from call counts:** The JIT can inline accessors; different patterns may require different steps. Avoid accessors with side effects, especially with deeply nested cases.

### A null nested record does not match

```java
Object missingNested = new Envelope(null);
boolean result =
    missingNested instanceof Envelope(Traced(String text));
```

The result is false. The outer `Envelope` exists, but the `traced` component is null, so the nested `Traced(...)` record cannot match.

### Accessor throws an exception

```java
record Broken(String value) {
    @Override
    public String value() {
        throw new IllegalStateException("accessor failure");
    }
}
record BrokenEnvelope(Broken broken) {}
```

When matching:

```java
Object broken = new BrokenEnvelope(new Broken("x"));
boolean ignored =
    broken instanceof BrokenEnvelope(Broken(String text));
```

The `IllegalStateException` thrown in the accessor is wrapped by Java 21 into a `MatchException`, with `getCause()` returning the original exception. The demo catches the error and prints:

```text
ACCESSOR_ERROR=MatchException:IllegalStateException
```

**Four outcomes to distinguish:**
- Pattern does not match due to wrong subtype → false or next case.
- Nested record does not match due to null → false or next case.
- Accessor throws an exception during deconstruction → `MatchException` with the original cause.
- Guard or body throws an exception → the exception propagates along the corresponding evaluation path rather than turning into a non-match.

Therefore, do not catch every `MatchException` and return `INCOMPLETE_DETAILS` as if it were merely missing data. Doing so can hide a real accessor bug.

## 11. Generic Record Patterns and Type Inference

Java 21 allows combining nested patterns with generic records:

```java
record Box<T>(T value) {}
record Parcel(Box<String> tracking, int pieces) {}

static String inspect(Object obj) {
    if (obj instanceof Parcel(Box(var code), int pieces)) {
        return "PARCEL:" + code + ":" + pieces;
    }
    return "NO_MATCH";
}
```

`var code` is inferred from the component of `Box<String>`; in this context it has type `String`. No manual cast is needed in the body.

Three tested cases:

```java
System.out.println(inspect(new Parcel(new Box<>("ZX"), 2)));
System.out.println(inspect(new Parcel(new Box<>(null), 0)));
System.out.println(inspect(new Parcel(null, 3)));
```

```text
PARCEL:ZX:2
PARCEL:null:0
NO_MATCH
```

The second result shows that when `Box` exists but its `value` component is null, it can still be bound via `var`. The third result shows that the nested `Box(...)` does not match because the `Box` object itself is null.

**Do not confuse this with generic reification:** Java still uses type erasure for generic type arguments. The fact that the compiler infers a component's type through a pattern does not mean every type argument is fully checked at runtime like a reified type. Follow Java's type-checking rules and do not use unchecked casts to force a pattern to be valid.

## 12. Three Reproduced Compiler Errors

### 12.1. Incorrect number of nested patterns

Record:

```java
record Point(int x, int y) {}
```

Incorrect pattern:

```java
// INTENTIONALLY WRONG:
boolean matches = obj instanceof Point(int x);
```

Java 21 `javac` reports:

```text
incorrect number of nested patterns
required: int,int
found: int
```

**Fix:** Use `Point(int x, int y)` or `Point(var x, var y)`. A record pattern must have two component patterns as declared.

### 12.2. Dominated case

Given `record Pair(int a, int b) {}`:

```java
// INTENTIONALLY WRONG order:
case Pair(int a, int b) -> "any";
case Pair(int a, int b) when a > 0 -> "positive";
```

The compiler reports an error equivalent to:

```text
this case label is dominated by a preceding case label
```

The preceding unguarded case already covers all `Pair` values. **Fix:** Place the guarded `a > 0` case before the unguarded case.

### 12.3. Pattern variable out of scope

Code:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x);
}
System.out.println(x); // INTENTIONALLY WRONG
```

The compiler reports:

```text
cannot find symbol
symbol: variable x
```

**Fix:** Use `x` within the region where Java proves the pattern matched, or transfer the value to a variable declared in the appropriate scope.

### Two other errors to avoid

**Wrong component type:** `Order` declares its third component as `Payment`, so you cannot substitute a nested record pattern for an unrelated type such as `Destination(...)` and expect a runtime cast. The compiler enforces type checking at every level.

**Wrong Java release:** A file using record patterns and `when` clauses must be compiled with a supporting release, for example:

```bash
javac --release 21 NestedRecordPatternsWorkshop.java
```

`javac --release 17` does not accept these Java 21-only features. Enabling `--enable-preview` on Java 17 is not a way to turn features finalized in Java 21 into code that runs on Java 17.

## 13. When Should You Use Deeply Nested Patterns?

**Appropriate when:**
- Data is modeled with multi-level immutable records.
- The consumer genuinely needs to read multiple deep components at once.
- You need to classify DTOs, messages, commands, or sealed algebraic data types.
- You want the compiler to enforce types, scope, dominance, and exhaustiveness at an appropriate level.
- You have specific tests for input shapes and nulls.

**Do not overuse when:**
- You only use one simple component but deconstruct the entire record tree.
- The nested hierarchy changes frequently, forcing dozens of consumers to update.
- Accessors have side effects, I/O, or unpredictable exceptions.
- Guards contain large business rules duplicated across multiple adapters.
- Domain behavior belongs on the type or in a domain service to avoid duplicating logic.

A shallower alternative when only `count` is needed:

```java
if (request instanceof PlaceOrder(Order(
        var customer, var destination, var payment, int count))) {
    System.out.println(count);
}
```

This pattern is clearer than deconstructing every detail of `Customer`, `Contact`, `Destination`, and `Payment` just to read `count`.

### If a record must always be valid

You can enforce invariants directly in the compact constructor:

```java
// ALTERNATIVE Order definition for production design;
// do not declare alongside the Order from the complete program.
record Order(Customer customer, Destination destination,
             Payment payment, int count) {
    Order {
        Objects.requireNonNull(customer, "customer");
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(payment, "payment");
        if (count <= 0) {
            throw new IllegalArgumentException("invalid count");
        }
    }
}
```

Now cases handling `new Order(null, ...)` are no longer needed if the object cannot be validly constructed that way. However, deeper nested components such as `Customer.contact` also need invariants if non-null is to be guaranteed. A successful pattern match does not by itself prove all domain invariants.

## 14. Testing and Refactoring Checklist

When writing nested record patterns, verify:

1. Does each record pattern have the exact **component count, order, and types** matching its declaration?
2. Which records can be null at the selector or component level?
3. Which positions only need `var`, and which must match a specific nested record?
4. Do `when` guards check for null before dereferencing?
5. Is any unguarded/general case dominating a more specific case?
6. Are pattern variables within Java's flow scope?
7. Are all subtypes of the sealed root covered by the `switch`?
8. Do **nested** subtypes such as `Payment` have their own tests?
9. Is any fallback silently masking the addition of a new subtype?
10. Can accessors throw exceptions or have side effects? Are they necessary?
11. If a record's structure changed, have all relevant consumers been rebuilt and tested?
12. Have you tested wrong-type input, null outer record, null component, null nested record, and guard false/true?
13. Have you verified stdout rather than relying only on the code compiling?
14. Do outputs/logs contain any sensitive data?
15. Can the pattern be written more concisely while remaining clear?

A good test suite should cover **matches**, **non-matches**, **guards**, and **abrupt completion**, not just the happy path with complete data.

## 15. Self-Practice Exercises

**Exercise 1 — Add a payment type:** Add `record Voucher(String code) implements Payment` and update `permits`. Add a `VOUCHER` branch to `classify`, and test with a valid code and a null code. Observe that the `PlaceOrder` fallback can still allow the root `switch` to compile before adding the `Voucher` case.

**Exercise 2 — Blank email:** Add a case returning `INVALID_EMAIL` if `Contact.email` is null or blank. Test null, `""`, `"   "`, and a normal email. Do not call `email.isBlank()` before the null check.

**Exercise 3 — Shorten the pattern:** Write a method `int count(Request request)` that only uses `count` from `Order`, without deconstructing `Contact` or `Payment`. Consider how to handle `PlaceOrder(null)` and `CancelOrder`.

**Exercise 4 — Out of scope:** Move a pattern variable outside an `if`, observe the `javac` error, and fix it by keeping the code in scope or assigning the value to a result type.

**Exercise 5 — Throwing accessor:** Change `Broken.value()` to throw `IllegalArgumentException`. Inspect `MatchException.getCause()` and distinguish that error from a null nested non-match.

**Exercise 6 — Generics:** Create `record Box<T>(T value)` and `record ParcelInt(Box<Integer> value)`. Use nested `Box(var number)`, and test a null `Box` and a null `value`.

**Exercise 7 — Null matrix:** Build an expected-results table for null selector, null `PlaceOrder.order`, null `Order.customer`, null `Customer.contact`, null `Contact.email`, null `Destination`, null `Payment`, and `count` 0. Update the classifying method/tests to match your own contract.

**Exercise 8 — Domain refactor:** If a bulk discount calculation is used by multiple consumers, design a domain method/service holding the single rule, and use nested patterns in adapters/mapping where needed. Explain why the same formula should not be copied across multiple `switch` statements.

## 16. Conclusion

**Nested record patterns** help Java 21 describe and deconstruct record data by its exact shape during matching. Combining `sealed`, `switch`, `when`, and `var` lets you write specific branches whose types, scope, and dominance can be checked by the compiler.

Key takeaways:
- **Right structure:** component count and order must match the declaration.
- **Right null handling:** null selector, null nested record, and null component are handled differently.
- **Right order:** guarded/specific cases go before broad fallbacks.
- **Right scope:** pattern variables are only usable where the compiler proves they are bound.
- **Right business logic:** an exhaustive `switch` does not replace tests for each nested subtype and boundary value.

Start with shallow patterns, increase depth as needed, keep accessors and guards predictable, and always test matching, non-matching, and exception-throwing cases.

## References

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.20.2 instanceof`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21 API — MatchException: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
