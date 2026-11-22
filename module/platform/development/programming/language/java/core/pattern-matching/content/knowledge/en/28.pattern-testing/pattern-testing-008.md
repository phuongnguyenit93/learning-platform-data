# Testing Nested Record Patterns in Java 21

## 1. Lesson Objectives

A **nested record pattern** is a record pattern that contains one or more other record patterns in its component list, allowing you to inspect a multi-level data structure and bind values located deep inside. For example, an `Order` containing a `Customer`, and `Customer` containing an `Address`:

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}
record Order(String number, Customer buyer, List<String> items) {}
```

A pattern can traverse through three levels:

```java
case Order(var number,
           Customer(String customerId, Address(String city, String zip)),
           var items) -> ...
```

This snippet illustrates a label in a `switch`, assuming `java.util.List` has been imported and the records above are defined. The testing concern is not just "does the object have the right type?". You must test: **whether the outer pattern matches, whether nested records match, what values bound variables receive, what rules govern `null` components, whether guards execute, how branch ordering works, and whether accessors produce side effects or exceptions**.

After this lesson, you will be able to:

1. Build a **positive/negative, boundary, and null test matrix** for nested record patterns.
2. Distinguish **top-level type patterns**, **nested type patterns**, **nested record patterns**, and Java 21's *null-matching* mechanism.
3. Test patterns in `instanceof` and `switch` with `when` guards, branch priority, dominance, and exhaustiveness.
4. Verify **bound values**, **evaluation order**, **accessor invocation counts**, and `MatchException`.
5. Write tests that **run automatically with only JDK 21**, using assertions that do not depend on `-ea`.
6. Know how to use a unit test framework, table-driven tests, property-based tests, and negative compiler tests when a project needs them.

**Java level:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) are standard features in **Java 21**. No preview features are used, and `--enable-preview` is not required. Type patterns with `instanceof` have been standard since Java 16 (JEP 394).

## 2. Understanding Exactly What Is Being Tested

A nested record pattern has two important kinds of components:

- **Record pattern**, for example `Address(String city, String zip)`: the value must be a non-`null` `Address` record, and then Java proceeds to match each component.
- **Type pattern**, for example `String city`: binds the value to the variable `city` upon matching; when positioned **directly as a component of a record pattern**, the `null`-matching rule can differ from a top-level type pattern.

Consider the pattern:

```java
input instanceof Order(
        var number,
        Customer(String customerId, Address(String city, String zip)),
        var items)
```

Java checks the outer `Order` object, then deconstructs its components. The `buyer` component must match the **record pattern `Customer(...)`**; next, `address` must match the **record pattern `Address(...)`**. If `buyer` or `address` is `null`, the corresponding record pattern does not match.

**Special rule in Java 21:** a type pattern nested directly inside a record component can be **null-matching** if it is *unconditional* for the declared type of that component. Because `Address.city` is declared as `String`, the pattern `String city` is unconditional for type `String`, and can bind **`null`**. Therefore, **`Address(String city, String zip)` does not automatically guarantee that `city` or `zip` is non-`null`**.

This is not an inference from syntax: the Java Language Specification SE 21 §14.30.1/§14.30.2 defines *null-matching* type patterns. The practical tests below will demonstrate this.

### Two Easily Confused Statements

- `null instanceof String s` is `false`: at the **top level**, a type pattern does not match `null`.
- `new Address(null, "10000")` can match `Address(String city, String zip)`: `String city` is **directly inside a record pattern** for a component declared with type `String`, so it binds `city == null`.

Conversely, if the component is declared with type `Object`, the pattern `String s` is **not unconditional** for `Object`, so `record Narrow(Object payload) {}` with `Narrow(String s)` **does not match `Narrow(null)`**. Both cases must be tested; do not label all nested `String` patterns as always rejecting or always accepting `null`.

## 3. Designing Tests by Structural Level

Domain data example:

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}
record Order(String number, Customer buyer, List<String> items) {}
```

For an input of type `Object`, categorize the test groups:

| Test group | Sample input | What to verify |
| --- | --- | --- |
| **Full match** | `Order("O1", Customer("C1", Address("Hanoi","10000")), List.of("book"))` | Binds the right ID, city, zip; guard passes; ready branch |
| **Outer record wrong type** | `"hello"` | Does not match `Order(...)`; fallback branch |
| **Null selector** | `null` | Does not match record pattern; handled by `case null` |
| **Null buyer** | `Order("O", null, items)` | Nested `Customer(...)` does not match |
| **Null address** | `Order("O", Customer("C",null), items)` | Nested `Address(...)` does not match |
| **Null ID component** | `Customer(null, Address(...))` | `String id` can bind null; guard must check |
| **Null city component** | `Address(null,"10000")` | `String city` can bind null; do not dereference immediately |
| **Null zip component** | `Address("Hue",null)` | Guard must block null before `matches(...)` |
| **Blank string** | `city = " "` | Pattern still matches; business guard rejects |
| **Malformed zip** | `zip = "bad"` | Pattern matches, guard is false |
| **Empty items** | `List.of()` | Pattern matches; guard is false if items are required |
| **Null items** | `items = null` | `var items` binds null; guard must block |
| **Null order number** | `number = null` | `var number` binds null; guard must block |
| **Multiple simultaneous errors** | `id=null` and `address=null` | Branch selected by pattern order; no NPE |
| **Abnormal accessor** | Accessor increments a counter or throws an exception | Measure side effects and exception type |

The matrix above does not replace business requirements; for a real API, add subtype/generic combinations, other validations, mutable collections, and concurrent behavior if they are relevant.

**Tip:** Each test should have a name expressing a hypothesis: `nullAddressFallsBack`, `nullCityIsBoundThenRejectedByGuard`, or `guardIsNotCalledIfNestedRecordFails`. Names like `test1` reduce diagnostic value when a test turns red.

## 4. Null-Matching: Cases That Must Be Tested Thoroughly

### 4.1. Record patterns do not match a null selector or nested record

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}

Object absent = null;
boolean top = absent instanceof Customer(var id, var address);
// top == false

Object missingAddress = new Customer("C1", null);
boolean nested = missingAddress instanceof Customer(
        var id, Address(var city, var zip));
// nested == false: Address record pattern does not match null
```

The two snippets are shown inside valid methods or blocks; the `id` variables in the two different expressions must be placed in non-conflicting scopes if combined into a single file. The conclusion is that **a record pattern does not match `null`**, both at the top level and when nested inside another record.

### 4.2. Type patterns inside components can bind null

```java
record Address(String city, String zip) {}

Object value = new Address(null, "10000");
if (value instanceof Address(String city, String zip)) {
    System.out.println(city == null); // true in Java 21
}
```

Reason: the `city` component has declared type `String`; `String city` is an unconditional type pattern for that type, so in a component position it is *null-matching*. **Do not write `city.isBlank()` before checking `city != null`**.

Compare with a component of type `Object`:

```java
record Narrow(Object payload) {}

boolean a = new Narrow(null) instanceof Narrow(String text);    // false
boolean b = new Narrow("hello") instanceof Narrow(String text); // true
boolean c = new Narrow(42) instanceof Narrow(String text);      // false
```

Here `String text` is **not unconditional** for `Object`, so `null` does not match and an `Integer` does not match either. When copying these lines into the same scope, rename the pattern variables or separate them into independent statements/methods according to scoping rules.

### 4.3. `var` does not automatically check for non-null

```java
record Customer(String name, Address address) {}

if (obj instanceof Customer(var name, var address)) {
    // name and address can be null.
    // Check for null before dereferencing.
}
```

With a `var` variable, the compiler infers the type from the component. If the component is a reference type, a `null` value can still be bound. A pattern is not a business validator.

**Minimum null checklist:** `null` at the selector; `null` at each intermediate record level; `null` at each reference component; `null` inside collections if the domain allows it; one case with a component declared as `String` and nested `String s`, and one case declared as `Object` with nested `String s`.

## 5. Pattern Success Differs from Guard Success

Consider a classification method named after the order domain:

```java
static boolean valid(
        String number, String id, String city,
        String zip, List<String> items) {
    return number != null && !number.isBlank()
            && id != null && !id.isBlank()
            && city != null && !city.isBlank()
            && zip != null && zip.matches("[0-9]{5}")
            && items != null && !items.isEmpty();
}
```

This is a **business predicate**, not the record pattern itself. It validates the bound data and prevents `NullPointerException` via short-circuit `&&`.

```java
static String classify(Object input) {
    return switch (input) {
        case Order(var number,
                   Customer(String id, Address(String city, String zip)),
                   var items)
                when valid(number, id, city, zip, items) ->
                "ready:" + id + ":" + city + ":" + items.size();

        case Order(var number,
                   Customer(String id, Address(String city, String zip)),
                   var items) ->
                "invalid-fields";

        case Order(var number, Customer(var id, var address), var items) ->
                "missing-address";

        case Order(var number, var buyer, var items) ->
                "missing-customer";

        case null -> "null-order";
        default -> "not-order";
    };
}
```

This snippet runs when the records and `java.util.List` above are declared. The branches are ordered from **narrow to wide**:

1. Matches all three records `Order → Customer → Address`, and then the guard `valid(...)` must be true → `ready`.
2. Matches the same record chain but the previous guard failed → `invalid-fields`.
3. Still has `Customer`, but `Address(...)` does not match, such as a null address → `missing-address`. The status names here are this example's classification scheme; if a real system has other address types, distinguish them specifically.
4. Has `Order` but `Customer(...)` does not match, such as a null buyer → `missing-customer`.
5. `null` and non-`Order` objects have their own fallbacks.

**Testing point:** `id=null`, `city=null`, or `zip=null` can still match **the first record branch**, after which `valid(...)` returns `false` and execution falls through to the `invalid-fields` branch. However, `address=null` does not match the nested `Address(...)`, so it falls through to `missing-address`.

If you change fallback labels, replace `String id` with `var id`, or reorder cases, re-verify the matrix; that can be a behavioral change.

## 6. Measuring Whether Guards Are Evaluated at the Right Time

A guard only runs **after the pattern of its own case has matched**. To test this ordering, you can add a counter in the test fixture:

```java
static int validationCalls;

static boolean valid(String number, String id, String city,
                     String zip, List<String> items) {
    validationCalls++;
    return number != null && !number.isBlank()
            && id != null && !id.isBlank()
            && city != null && !city.isBlank()
            && zip != null && zip.matches("[0-9]{5}")
            && items != null && !items.isEmpty();
}
```

When running the 12 inputs in the program at the end of the lesson, the guard is called **8 times**: the cases that have all three record levels `Order/Customer/Address`, even when a `String` component is null or invalid. The cases with `address=null`, `buyer=null`, `null` selector, or another object type **do not invoke that guard**.

**Do not conflate them:** A guard returning `false` is different from a pattern not matching, even though both can lead to a later branch. A counter helps verify that distinction. However, the counter here is for a **sequential test fixture**, not how production predicates should be designed: predicates should be pure and side-effect-free whenever possible.

### 6.1. Proving safe short-circuiting

With `instanceof` combined with a nested pattern:

```java
static boolean hasKnownCity(Object input) {
    return input instanceof Order(
            var number,
            Customer(String id, Address(String city, String zip)),
            var items)
            && city != null
            && !city.isBlank();
}
```

Only when `Order/Customer/Address` matches is `city != null` evaluated. If `city==null`, `&&` skips calling `isBlank()`. The method returns `false` instead of throwing an NPE.

Be careful with writing only `&& !city.isBlank()`: it is **unsafe** when nested `String city` is null-matching. Component-level null testing catches this bug.

## 7. Testing That Pattern Variables Bind the Right Data

A successful `instanceof`/`switch` call is not enough; tests must verify that data is bound in the right order and from the right source. For example:

```java
case Order(var number,
           Customer(String id, Address(String city, String zip)),
           var items)
        when valid(number, id, city, zip, items) ->
        "ready:" + id + ":" + city + ":" + items.size();
```

With the data `new Order("O1", new Customer("C1", new Address("Hanoi","10000")), List.of("book","pen"))`, the exact result is `"ready:C1:Hanoi:2"`.

Tests should distinguish components using **distinct values**, such as `number="O1"`, `id="C1"`, `city="Hanoi"`, `zip="10000"`. If all of them used `"test"`, swapping components might not cause the test to fail.

A simple checklist:

- Test component order matching the record declaration.
- Test extracting nested components across multiple levels.
- Test primitive values such as `int`, `boolean`, and negative/zero numbers when records contain them.
- Test `null` reference components.
- Test values with extra whitespace, Unicode, or unusual formatting when business logic handles them.
- Test empty/non-null/null collections, and their contents if guards inspect elements.

If a component is an array or mutable collection, the pattern **does not copy** the data. For code that observes or mutates collections, test aliasing and post-call state if required by the contract.

## 8. Testing Record Accessor Errors and Side Effects

Record patterns use **accessors** to retrieve component values. A default record has simple accessors, but a record author can declare explicit accessors—for example, counting invocations or throwing exceptions.

### 8.1. Testing whether accessors are called extra times

```java
record Metered(String value) {
    static int reads;
    @Override public String value() {
        reads++;
        return value;
    }
}
record Container(Metered payload) {}

static boolean typeOnly(Object input) {
    return input instanceof Container;
}

static boolean deconstruct(Object input) {
    return input instanceof Container(Metered(String value));
}
```

With `Container(new Metered("ok"))`:

- `typeOnly(...)` only checks the type; it **does not need to call** `Metered.value()`, so `reads` does not increment.
- `deconstruct(...)` reads the deeper component; `Metered.value()` is called, so `reads` increments to 1.
- With `Container(new Metered(null))`, nested `String value` is **still null-matching** because the component is declared `String`; `deconstruct(...)` returns `true` and the accessor runs one more time.

A test that only compares `boolean` results can miss accessor cost or side effects. When proving behavioral equivalence after refactoring, check invocation counts and exceptions.

### 8.2. Accessor throws an exception: testing the real exception type

```java
record Unstable(String value) {
    @Override public String value() {
        throw new IllegalStateException("accessor failure");
    }
}
record Wrapper(Unstable inner) {}
```

When matching `Wrapper(Unstable(String value))`, Java invokes the inner record's accessor. Per JLS Java 21 §14.30.2, an exception thrown by an accessor invocation during deconstruction is wrapped in **`MatchException`** with the original exception in `getCause()`.

```java
try {
    Object object = new Wrapper(new Unstable("x"));
    boolean matched = object instanceof Wrapper(Unstable(String value));
    throw new AssertionError("Unexpected result: " + matched);
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
    // IllegalStateException
}
```

This snippet is excerpted from a test context; `Unstable` and `Wrapper` are already declared. In this case, calling `Unstable.value()` throws `IllegalStateException`; pattern matching throws `MatchException` with that error as its cause. Do not assume a nested pattern always just returns `false` when an accessor fails.

**Tests must observe exceptions rather than swallowing them with a broad catch and returning `false`.** If a record structure retrieves values via I/O or mutable state, the risk also involves stability and consistency; with pure data structures, side effects are fewer, but understanding the semantics is still necessary.

## 9. Negative Compiler Tests: Errors Caught Before Runtime

Some cases cannot be tested with normal runtime unit tests because **Java refuses to compile them**. Separate negative compilation tests are needed, or you can rely on CI's `javac --release 21` step and inspect diagnostics.

### 9.1. Wide record branch dominates a narrow nested branch

```java
record Point(int x, int y) {}
record Holder(Point value) {}

// INTENTIONALLY WRONG in switch:
return switch (input) {
    case Holder(var p) -> "wide";
    case Holder(Point(var x, var y)) -> "narrow"; // dominated
    default -> "other";
};
```

`Holder(var p)` comes first and covers every non-null `Holder`, including those containing a valid `Point`. The nested case afterward can never be selected; the compiler reports `this case label is dominated by a preceding case label`.

**Fix:** place `Holder(Point(var x,var y))` before `Holder(var p)`.

### 9.2. Wrong number of components

```java
record Point(int x, int y) {}

// INTENTIONALLY WRONG:
boolean match = input instanceof Point(var x);
```

Record `Point` has **two** components, but the pattern has only one. Java 21 reports an error equivalent to `incorrect number of nested patterns`, because you cannot omit the second component by leaving out its position.

**Fix:** write `Point(var x, var y)`, or if you only need `x`, you must still include the second component pattern such as `Point(var x, var ignoredY)`. Do not confuse not using a component with not declaring its position.

### 9.3. Duplicate bound variable name

```java
// INTENTIONALLY WRONG:
boolean match = input instanceof Point(var x, var x);
```

Two component patterns both declare the variable `x` in the same record pattern. Java 21 reports an error equivalent to `illegal attempt to redefine an existing match binding`.

**Fix:** use distinct names, such as `Point(var x, var y)`.

### 9.4. Using a pattern variable when a match is not guaranteed

```java
// INTENTIONALLY WRONG: if the pattern does not match, city is not bound.
return input instanceof Order(var no,
        Customer(var id, Address(var city, var zip)),
        var items)
        || city.isBlank();
```

The right-hand side of `||` only executes when the match on the left-hand side is `false`; at that point `city` cannot be used. If you want to require a match and a non-blank city, use `&& city != null && !city.isBlank()`.

**Note:** The first three errors can be detected directly by `javac` on Java 21; this example illustrates the flow scoping rules of pattern variables (JLS §6.3) and must not be placed into a runnable source file.

## 10. Complete Java 21 Program for Testing

Create a file **`NestedRecordPatternTestDemo.java`** with the following contents. This code uses only the Java standard library, includes **12 table-driven classification tests**, guard/accessor measurements, three narrow type pattern cases, and an accessor exception test. If an expectation fails, the program throws `AssertionError`; `-ea` does not need to be enabled.

```java
import java.util.List;

public class NestedRecordPatternTestDemo {
    record Address(String city, String zip) {}
    record Customer(String id, Address address) {}
    record Order(String number, Customer buyer, List<String> items) {}
    record Container(Metered payload) {}
    record Metered(String value) {
        static int reads;
        @Override public String value() {
            reads++;
            return value;
        }
    }
    record Narrow(Object payload) {}
    record Unstable(String value) {
        @Override public String value() {
            throw new IllegalStateException("accessor failure");
        }
    }
    record Wrapper(Unstable inner) {}

    static int validationCalls;

    static boolean valid(String number, String id, String city,
                         String zip, List<String> items) {
        validationCalls++;
        return number != null && !number.isBlank()
                && id != null && !id.isBlank()
                && city != null && !city.isBlank()
                && zip != null && zip.matches("[0-9]{5}")
                && items != null && !items.isEmpty();
    }

    static String classify(Object input) {
        return switch (input) {
            case Order(var number,
                       Customer(String id, Address(String city, String zip)),
                       var items)
                    when valid(number, id, city, zip, items) ->
                    "ready:" + id + ":" + city + ":" + items.size();
            case Order(var number,
                       Customer(String id, Address(String city, String zip)),
                       var items) ->
                    "invalid-fields";
            case Order(var number, Customer(var id, var address), var items) ->
                    "missing-address";
            case Order(var number, var buyer, var items) ->
                    "missing-customer";
            case null -> "null-order";
            default -> "not-order";
        };
    }

    static boolean hasKnownCity(Object input) {
        return input instanceof Order(var number,
                Customer(String id, Address(String city, String zip)),
                var items) && city != null && !city.isBlank();
    }

    static boolean typeOnly(Object input) {
        return input instanceof Container;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Container(Metered(String value));
    }

    static boolean narrow(Object input) {
        return input instanceof Narrow(String text);
    }

    static void check(String name, Object input, String expected) {
        String actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println(name + " -> " + actual);
    }

    public static void main(String[] args) {
        check("valid", new Order("O1", new Customer("C1",
                new Address("Hanoi", "10000")), List.of("book", "pen")),
                "ready:C1:Hanoi:2");
        check("blank-city", new Order("O2", new Customer("C2",
                new Address(" ", "10000")), List.of("book")), "invalid-fields");
        check("bad-zip", new Order("O3", new Customer("C3",
                new Address("Hue", "bad")), List.of("book")), "invalid-fields");
        check("empty-items", new Order("O4", new Customer("C4",
                new Address("Hue", "50000")), List.of()), "invalid-fields");
        check("null-number", new Order(null, new Customer("C5",
                new Address("Hue", "50000")), List.of("book")), "invalid-fields");
        check("null-id", new Order("O6", new Customer(null,
                new Address("Hue", "50000")), List.of("book")), "invalid-fields");
        check("null-city", new Order("O7", new Customer("C7",
                new Address(null, "50000")), List.of("book")), "invalid-fields");
        check("null-zip", new Order("O8", new Customer("C8",
                new Address("Hue", null)), List.of("book")), "invalid-fields");
        check("null-address", new Order("O9", new Customer("C9", null),
                List.of("book")), "missing-address");
        check("null-buyer", new Order("O10", null,
                List.of("book")), "missing-customer");
        check("null-selector", null, "null-order");
        check("other-type", "hello", "not-order");

        System.out.println("validation calls=" + validationCalls);
        Object known = new Order("O11", new Customer("C11",
                new Address("Hue", "50000")), List.of("book"));
        System.out.println("has city=" + hasKnownCity(known));
        System.out.println("null nested city=" +
                hasKnownCity(new Order("O12", new Customer("C12",
                        new Address(null, "50000")), List.of("book"))));

        Container good = new Container(new Metered("ok"));
        System.out.println("type only=" + typeOnly(good)
                + ", reads=" + Metered.reads);
        System.out.println("nested=" + deconstruct(good)
                + ", reads=" + Metered.reads);
        Container withNull = new Container(new Metered(null));
        System.out.println("nested null=" + deconstruct(withNull)
                + ", reads=" + Metered.reads);
        System.out.println("narrow null=" + narrow(new Narrow(null)));
        System.out.println("narrow text=" + narrow(new Narrow("hello")));
        System.out.println("narrow integer=" + narrow(new Narrow(42)));

        try {
            Object object = new Wrapper(new Unstable("x"));
            boolean matched =
                    object instanceof Wrapper(Unstable(String value));
            throw new AssertionError("Unexpected result: " + matched);
        } catch (MatchException ex) {
            System.out.println("accessor error="
                    + ex.getClass().getSimpleName()
                    + ", cause=" + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("TESTS PASSED");
    }
}
```

**Compile and run:** requires JDK 21 or later; in the directory containing the source:

```bash
javac --release 21 NestedRecordPatternTestDemo.java
java NestedRecordPatternTestDemo
```

**Actual output (stdout):**

```text
valid -> ready:C1:Hanoi:2
blank-city -> invalid-fields
bad-zip -> invalid-fields
empty-items -> invalid-fields
null-number -> invalid-fields
null-id -> invalid-fields
null-city -> invalid-fields
null-zip -> invalid-fields
null-address -> missing-address
null-buyer -> missing-customer
null-selector -> null-order
other-type -> not-order
validation calls=8
has city=true
null nested city=false
type only=true, reads=0
nested=true, reads=1
nested null=true, reads=2
narrow null=false
narrow text=true
narrow integer=false
accessor error=MatchException, cause=IllegalStateException
TESTS PASSED
```

### 10.1. Reading the core results

- **The first 12 cases** use `check(...)`: if expected and actual differ, the program throws `AssertionError`. Thus, the line `TESTS PASSED` only appears when every check in the program completes normally.
- `null-id`, `null-city`, and `null-zip` all result in `invalid-fields`, **not** `missing-address`. This confirms that nested `String` type patterns can be null-matching for components of type `String`.
- `null-address` and `null-buyer` enter other branches because **nested record patterns do not match null**.
- `validation calls=8`: the guard is executed for objects that have all record levels, even when a `String` component is null; it is not executed when a nested record fails.
- `has city=true` and `null nested city=false` show that checking `city != null && !city.isBlank()` is necessary.
- `type only=true, reads=0` differs from `nested=true, reads=1`: deconstruction invokes the accessor rather than only checking the runtime type.
- `nested null=true, reads=2` is another demonstration of a null-matching type pattern nested in a record.
- `Narrow(null)` does not match `Narrow(String text)` because the component has declared type `Object`, whereas `Narrow("hello")` matches and `Narrow(42)` does not.
- `MatchException` wraps the `IllegalStateException` from the accessor; the error does not silently turn into `false`.
- Finally, `TESTS PASSED` proves **the checked expectations**, not that every input outside the test domain is guaranteed to be correct.

### 10.2. Why use `throw new AssertionError(...)`?

In Java, an `assert condition;` statement only runs when assertions are enabled, typically via the `java -ea ...` flag. In the demo, checking expected/actual with a condition and throwing `AssertionError` directly ensures it **always runs** whether or not the JVM has `-ea`. If a project uses JUnit, use `assertEquals(...)`, `assertThrows(...)`, and the appropriate test runner instead of printing logs manually.

## 11. Integrating with JUnit and Test Data Tables

When a project already uses JUnit Jupiter (JUnit 5), you can convert the test method into a parameterized test. The following snippet is an **illustration that depends on JUnit and the records/`classify` method defined in production code**, not a standalone JDK program.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.Arguments;
import java.util.List;
import java.util.stream.Stream;

class OrderPatternTest {
    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(
                new Order("O1",
                    new Customer("C1", new Address("Hanoi", "10000")),
                    List.of("book")),
                "ready:C1:Hanoi:1"),
            Arguments.of(
                new Order("O2",
                    new Customer("C2", new Address(null, "10000")),
                    List.of("book")),
                "invalid-fields"),
            Arguments.of(
                new Order("O3", new Customer("C3", null), List.of("book")),
                "missing-address"),
            Arguments.of(null, "null-order")
        );
    }

    @ParameterizedTest
    @MethodSource("cases")
    void classifiesNestedRecords(Object input, String expected) {
        assertEquals(expected, classify(input));
    }
}
```

**Usage notes:** You must declare the `Order`, `Customer`, and `Address` classes and access `classify` accordingly, and configure the project's `junit-jupiter-params` dependency/test runner. If the records are declared nested inside a production class, use qualified names or valid imports. In a separate test class, `classify` must be called through its enclosing class unless a valid static import is used.

**Pros:** A single `cases` set separates inputs from expectations; adding a null or boundary case only requires adding one line. **Cons:** If you only test return values, you still need separate tests for exceptions and side effects.

### 11.1. Testing accessor exceptions with JUnit

In a project using JUnit, you can verify the wrapped exception:

```java
MatchException ex = assertThrows(MatchException.class, () -> {
    Object object = new Wrapper(new Unstable("x"));
    boolean matched =
            object instanceof Wrapper(Unstable(String value));
});
assertInstanceOf(IllegalStateException.class, ex.getCause());
```

This is an **illustrative code snippet**, assuming static imports for `assertThrows`, `assertInstanceOf`, and records matching the full example. Do not use a broad `RuntimeException` catch and treat every failure as passing; you must verify **the exact exception type and cause** per the contract.

## 12. Property-Based and Metamorphic Testing

With multiple levels of records, manual test tables can easily miss combinations. You can increase confidence using **property-based testing** or invariants defined from the domain.

Some meaningful invariants:

- If `buyer == null` and the selector is still an `Order`, the example's result must be `"missing-customer"`, regardless of `number` or `items`.
- If `buyer != null` but `address == null`, the result is `"missing-address"`.
- If all record levels are present and `city == null`, `valid(...)` must return `false` without throwing an NPE.
- If a complete `Order` is ready, changing `zip` from five digits to `"bad"` must make it no longer ready.
- If only `items` changes from a non-empty list to an empty list, the example's business guard changes from true to false.
- With `Narrow(Object payload)`, `null` does not match nested `String text`, whereas a non-null `String` does match.

If using a generator, fix the random seed when reproducing a failure, shrink the failing input to a concrete case, and add that regression case to the suite. Do not generate purely random data and only check "no exception thrown"—pattern matching can take the wrong branch without throwing an error.

### 12.1. Metamorphic tests help identify the impact of a change

For example, starting from a `ready` order:
1. Change `city` to a whitespace-only string → expected `invalid-fields`.
2. Change `address` to `null` → expected `missing-address`.
3. Change `buyer` to `null` → expected `missing-customer`.
4. Change the selector to `null` → expected `null-order`.

These transformations test **the difference between a guard failing and a nested pattern failing**; this is often where bugs hide when refactoring from `if/instanceof/cast` to nested record patterns.

## 13. Coverage, Mutation Testing, and Regression Control

**Branch coverage** in `switch` is useful, but insufficient if each branch is only tested with one simple case. A solid nested record pattern test suite needs:

1. **Outer pattern success/failure:** valid `Order`, different type, `null` selector.
2. **Each record level:** `buyer=null` and `address=null`.
3. **Each reference component:** non-null, null, blank/empty when meaningful.
4. **Guards:** true/false; confirm guards are not called when the pattern has not matched.
5. **Case ordering:** narrow nested before general record; if swapped, the compiler must catch dominance or tests must catch wrong branch selection.
6. **Accessors:** with/without side effects, throwing exceptions, and read counts if required by the contract.
7. **Regression:** run the same input suite on old and refactored code, comparing results and key exceptions.
8. **Compile checks:** `javac --release 21` on real source and separate negative samples when needed for tooling/training.

**Mutation testing** can help uncover weak tests—for instance, changing `zip.matches(...)` to always true in a test mutant, removing `city != null`, or swapping two branches. A useful test suite should catch at least the mutations that violate defined business rules. Do not apply mutations to production source or real data without isolation and a review process.

### When should you benchmark?

Record deconstruction calls accessors and generates nested matching logic, but you **should not assume** it is always slower than legacy casting by a fixed ratio. If the code is on a hot path, use JMH or an appropriate benchmark, measure in a representative environment, and avoid drawing conclusions from a single run. Prioritize correctness, null semantics, and exceptions before optimizing.

## 14. Review Checklist for Nested Record Pattern Tests

- [ ] Clearly specify JDK 21+ for record/switch patterns and compile with the right `--release`.
- [ ] Include tests for *outer selector null* and *wrong type*.
- [ ] Include tests for each **nested record being null**, not just a String component being null.
- [ ] Include tests for null-matching of **type patterns unconditional for the component type**; do not assume `String city` rejects all `null`s.
- [ ] Include tests for nested type patterns that are **not unconditional** (e.g., `Object payload` with `String s`).
- [ ] Guards have null checks before dereferencing; both true and false guard cases are executed.
- [ ] Include tests that detect guards being called when patterns do not match, or test with a counter when needed.
- [ ] Include tests for case ordering between narrow nested patterns and wide record patterns, with no dominated branches.
- [ ] Each bound component is verified with a distinct value, avoiding variable swaps that still pass tests.
- [ ] Include tests with `null`, empty, and non-empty collections if the record contains a list.
- [ ] Include tests for accessor side effects and `MatchException` if the record type overrides accessors.
- [ ] Do not treat `AssertionError` or test failures as normal pattern fallback branches.
- [ ] Tests run in CI on the target Java version and do not mix **intentionally invalid** examples into runnable source.
- [ ] Expected results are derived from the contract, not adjusted just to "make tests green".

**Completion criteria:** Have a positive, negative, and boundary test set reflecting the record structure; accurately understand null semantics; test guards and bound variables; verify accessor errors; build and run examples; and ensure syntax, dominance, and arity violations are caught by the compiler. When all cases PASS, conclude only within the scope of the tested inputs and contract.

## 15. Common Mistakes

### Mistake 1: Assuming `String s` in any nested record never matches null

This mistake can lead to NPEs. If the type pattern is **unconditional** for the component's declared type, Java 21 allows it to be **null-matching**. Test `Address(null, "10000")` and `Narrow(null)` to see the two different outcomes.

### Mistake 2: Testing `null` only at the outer selector

`Order(null, Customer(...), items)`, `Order("O", null, items)`, `Customer("C", null)`, and `Address(null, "10000")` have different meanings. Missing a null level can miss a non-matching branch or an exception.

### Mistake 3: Confusing a non-matching pattern with a false guard

An order with `address=null` does not match the nested `Address(...)`; an order with `city=" "` matches the structure but fails the guard. Tests must expect different branches.

### Mistake 4: Using `assert` without enabling assertions

When the JVM runs without `-ea`, `assert condition;` statements usually do not execute. Use a test framework or explicit checks throwing `AssertionError` for pure JDK demos.

### Mistake 5: Assuming all record accessors are pure

Accessors can be overridden, cause side effects, or throw exceptions. Deconstruction tests must consider the possibility of `MatchException` and the difference from type-only checks.

### Mistake 6: Placing a wide case before a narrow nested case

`case Order(var number, var buyer, var items)` before `case Order(...Customer(...))` shadows the nested case behind it. The Java 21 compiler performs **dominance** analysis; reorder so specific comes before general.

### Mistake 7: Checking only output while ignoring bindings and side effects

Two implementations might both return `"ready"` while reading accessors a different number of times, changing guard order, or using the wrong component in logs. Use distinct data and check important state/exceptions.

### Mistake 8: Setting test expectations by intuition about null instead of the JLS

When a test case unexpectedly throws an NPE, analyze whether the nested type pattern matches `null`. Do not "fix" the test by letting the NPE pass if the business rule intends to reject null data safely. Apply explicit null checks.

## 16. Self-Check Questions

**1.** How does a nested record pattern differ from a type pattern?  
*Answer:* A record pattern requires a non-null record object of the matching type and then matches its components; a type pattern binds a value by type and can be null-matching in a component position if it is unconditional for the declared type.

**2.** What is `new Customer("C1", null) instanceof Customer(var id, Address(var city, var zip))`?  
*Answer:* `false`, because `Address(...)` is a record pattern and does not match a `null` component.

**3.** Can `new Address(null, "10000") instanceof Address(String city, String zip)` return true?  
*Answer:* Yes, in Java 21. `String city` is an unconditional component type pattern for a component declared as `String`, so it can bind null.

**4.** Why is `new Narrow(null) instanceof Narrow(String text)` false if `record Narrow(Object payload) {}`?  
*Answer:* `String text` is not unconditional for the component type `Object`, so it is not null-matching in that position.

**5.** Why must we test `city != null && !city.isBlank()`?  
*Answer:* The pattern can bind `city==null`; short-circuiting ensures `isBlank()` is not called on null.

**6.** Is the guard `when valid(...)` called when `address==null` and the pattern requires `Address(...)`?  
*Answer:* No, because the nested record pattern fails before the guard is evaluated.

**7.** When a record accessor throws `IllegalStateException` during deconstruction, what can happen?  
*Answer:* Pattern matching throws `MatchException` with the accessor exception as its cause; it does not silently return false.

**8.** Why is `case Holder(var p)` before `case Holder(Point(var x,var y))` rejected by the compiler?  
*Answer:* The wide pattern covers all match cases of the narrow nested pattern that follows it: dominance.

**9.** Should a `"TESTS PASSED"` result from a 12-case suite be taken as proof that the entire API is correct?  
*Answer:* No. It only proves the tested cases. You must add boundaries and contracts from the real system.

**10.** Do unit test frameworks replace negative compilation tests?  
*Answer:* No. Errors such as wrong arity, duplicate bindings, and dominated cases occur before runtime; you need a compile-time gate and separate error samples.

## Official References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 JLS §14.30.1 — Kinds of Patterns and null-matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1)
- [Java SE 21 JLS §14.30.2 — Pattern Matching, accessor exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [Java SE 21 JLS §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
