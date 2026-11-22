# Debugging Nested Record Patterns in Java 21+

## 1. The problem: why does a nested record pattern fail to match?

A **nested record pattern** is a pattern that contains one or more nested record patterns, allowing type checking and data extraction across multiple record layers. For example:

```java
// Assume Invoice, Customer, and Address are appropriately declared records.
if (value instanceof Invoice(
        var code,
        Customer(var name, Address(var city, var street)))) {
    System.out.println(code + ":" + name + ":" + city);
}
```

The expression above is evaluated from the outside in:

1. `value` must be a non-`null` `Invoice`.
2. The `customer` component of `Invoice` must be a non-`null` `Customer`.
3. The `address` component of `Customer` must be a non-`null` `Address`.
4. When all layers match, `code`, `name`, `city`, and `street` are bound to the pattern variables in the record's declaration order.

**Debugging difficulty:** a `false` result from the entire `instanceof` expression does not tell you which layer failed. If you add `&&` conditions or a `when` guard, you can also run into the situation where **the record pattern matched, but the business condition outside the pattern evaluated to `false`**. You need to separate these two causes.

Record patterns became a standard feature in **Java 21** (JEP 440) and can be used in `instanceof` and `switch`. Pattern matching for `switch` also became standard in Java 21 (JEP 441). The runnable example in this article requires **JDK 21+** and does not need `--enable-preview`.

## 2. Illustrative model and the matching "tree"

Use three records:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record Invoice(String code, Customer customer) {}
```

These are illustrative declarations; the full runnable program is in section 6.

Given the data:

```java
Object value = new Invoice(
        "I-1",
        new Customer("Ana", new Address("Ha Noi", "Main")));
```

The tree to match is:

```text
value
└── Invoice
    ├── code: String              -> var code
    └── customer: Customer        -> Customer(...)
        ├── name: String          -> var name
        └── address: Address      -> Address(...)
            ├── city: String      -> var city
            └── street: String    -> var street
```

**Key point:** `var city` does not reject `null` on its own. If `Address` exists but its `city` component is `null`, the pattern can still **match** and bind `city` to `null`. By contrast, if the `Address` object itself is `null`, the nested pattern `Address(...)` **does not match**.

Therefore, debugging a nested record pattern requires distinguishing between:

- **Structural non-match:** wrong type at the root record, or a nested record required by the pattern is `null`.
- **Structural match, but guard failed:** a component is `null`/blank, a number is out of range, or a business condition returns `false`.
- **Exception:** a custom record accessor throws an exception during deconstruction, which is not a normal `false` result.
- **Compilation error:** wrong number of nested patterns, incompatible types, or using a pattern variable outside its valid scope.

## 3. Debug from the outside in instead of guessing from `false`

Suppose the business requirement is: an invoice must have a code, a customer, an address, and non-null/non-blank customer name and city name. `street` is allowed to be null in this example.

We use the expression:

```java
if (value instanceof Invoice(var code,
        Customer(var name, Address(var city, var street)))
        && code != null && !code.isBlank()
        && name != null && !name.isBlank()
        && city != null && !city.isBlank()) {
    // Process valid invoice.
}
```

### Step A — Check the root record

```java
if (!(value instanceof Invoice invoice)) {
    System.out.println("not an Invoice");
}
```

If `value == null` or the actual value is a `String`, the outer layer has already failed to match. There is no need to speculate about the inner components.

`instanceof` on `null` returns `false` and the test itself does not throw `NullPointerException`.

### Step B — Check each nested record

```java
if (value instanceof Invoice invoice) {
    Customer customer = invoice.customer();
    if (customer == null) {
        System.out.println("customer is null");
    } else {
        Address address = customer.address();
        if (address == null) {
            System.out.println("address is null");
        }
    }
}
```

This is a **temporary technique using accessors and type patterns** to locate the failing layer. Once the bug is identified, you can switch back to the more concise record pattern expression. Avoid sprinkling `System.out.println` everywhere and forgetting to remove it in production code.

### Step C — Check business conditions

If all nested records are non-`null`, check `code`, `name`, and `city` individually. For example, `new Address(null, "Main")` still matches `Address(var city, var street)`; it is the guard `city != null` that rejects it.

The `&&` operator evaluates with **short-circuiting** from left to right. Thus `!city.isBlank()` only runs after `city != null` is true. Reversing the condition to `!city.isBlank() && city != null` can cause a `NullPointerException` when `city == null`.

### Step D — Compare against the exact same input

Save a single input and run **both approaches**: the real pattern expression and the layer-by-layer diagnostic function. Do not construct a new input between the two checks, especially if the data is mutable or a custom accessor has side effects.

## 4. A diagnostic function with specific failure reasons

A pattern expression returning a boolean has no "failure reason code". You can use a step-by-step function to report the **first reason in the chosen check order**:

```java
static String diagnose(Object value) {
    if (value == null) return "root-null";
    if (!(value instanceof Invoice invoice)) return "wrong-root";

    Customer customer = invoice.customer();
    if (customer == null) return "customer-null";

    Address address = customer.address();
    if (address == null) return "address-null";

    String code = invoice.code();
    if (code == null || code.isBlank()) return "invalid-code";

    String name = customer.name();
    if (name == null || name.isBlank()) return "invalid-name";

    String city = address.city();
    if (city == null) return "city-null";
    if (city.isBlank()) return "city-blank";
    return "ok";
}
```

This snippet is an illustrative method placed inside a class that contains the records mentioned earlier. The function uses the record's **default accessors**, which are not customized in the complete program.

**Why check `customer` and `address` before `code` and `name`?** That is the diagnostic priority order chosen by the example to distinguish structural errors before content errors. An invoice with multiple simultaneous errors will report the **first error**, not the full list. For business validation that must report all errors, build a separate error collector instead of treating this function as a general-purpose validator.

## 5. Test matrix: testing `null` at each layer

| Input data | Nested record pattern structurally matches? | Guard satisfied? | Diagnostic reason |
| --- | --- | --- | --- |
| `Invoice("I-1", Customer("Ana", Address("Ha Noi", "Main")))` | Yes | Yes | `ok` |
| `Invoice("I-2", Customer("Binh", Address("Hue", null)))` | Yes; `var street` receives null | Yes | `ok` |
| `Invoice("I-3", null)` | No; missing `Customer(...)` | Not evaluated | `customer-null` |
| `Invoice("I-4", Customer("Chi", null))` | No; missing `Address(...)` | Not evaluated | `address-null` |
| `Invoice("I-5", Customer("Dung", Address(null, "Main")))` | Yes; `var city` receives null | No | `city-null` |
| `Invoice("I-6", Customer("Em", Address(" ", "Main")))` | Yes | No | `city-blank` |
| `Invoice(" ", Customer(...))` | Yes | No | `invalid-code` |
| `Invoice("I-8", Customer("", Address(...)))` | Yes | No | `invalid-name` |
| String `"not an invoice"` | No; wrong root type | Not evaluated | `wrong-root` |
| `value == null` | No | Not evaluated | `root-null` |

**Terminology note:** In the runnable method in section 6, the result `"NO_MATCH"` means **the entire `instanceof pattern && guards` expression is false**. It does not prove that the record pattern itself failed: `city-null`, `city-blank`, `invalid-code`, and `invalid-name` all pass structural matching and then fail at the guard.

## 6. Complete Java program: test with assertions and exact output

Create the file **`NestedRecordPatternDebugDemo.java`**:

```java
public class NestedRecordPatternDebugDemo {
    record Address(String city, String street) {}
    record Customer(String name, Address address) {}
    record Invoice(String code, Customer customer) {}

    static String extract(Object value) {
        if (value instanceof Invoice(var code,
                Customer(var name, Address(var city, var street)))
                && code != null && !code.isBlank()
                && name != null && !name.isBlank()
                && city != null && !city.isBlank()) {
            return "MATCH:" + code + ":" + name + ":"
                    + city.toUpperCase(java.util.Locale.ROOT);
        }
        return "NO_MATCH";
    }

    static String diagnose(Object value) {
        if (value == null) return "root-null";
        if (!(value instanceof Invoice invoice)) return "wrong-root";

        Customer customer = invoice.customer();
        if (customer == null) return "customer-null";

        Address address = customer.address();
        if (address == null) return "address-null";

        String code = invoice.code();
        if (code == null || code.isBlank()) return "invalid-code";

        String name = customer.name();
        if (name == null || name.isBlank()) return "invalid-name";

        String city = address.city();
        if (city == null) return "city-null";
        if (city.isBlank()) return "city-blank";
        return "ok";
    }

    static void verify(String label, Object value,
                       String expectedExtract, String expectedReason) {
        String actualExtract = extract(value);
        String actualReason = diagnose(value);
        if (!expectedExtract.equals(actualExtract)
                || !expectedReason.equals(actualReason)) {
            throw new AssertionError(label + " actual="
                    + actualExtract + "/" + actualReason);
        }
        System.out.println(label + " -> " + actualExtract
                + " [" + actualReason + "]");
    }

    public static void main(String[] args) {
        verify("valid", new Invoice("I-1",
                new Customer("Ana", new Address("Ha Noi", "Main"))),
                "MATCH:I-1:Ana:HA NOI", "ok");

        verify("street-null", new Invoice("I-2",
                new Customer("Binh", new Address("Hue", null))),
                "MATCH:I-2:Binh:HUE", "ok");

        verify("customer-null", new Invoice("I-3", null),
                "NO_MATCH", "customer-null");

        verify("address-null", new Invoice("I-4",
                new Customer("Chi", null)),
                "NO_MATCH", "address-null");

        verify("city-null", new Invoice("I-5",
                new Customer("Dung", new Address(null, "Main"))),
                "NO_MATCH", "city-null");

        verify("city-blank", new Invoice("I-6",
                new Customer("Em", new Address(" ", "Main"))),
                "NO_MATCH", "city-blank");

        verify("invalid-code", new Invoice(" ",
                new Customer("Giau", new Address("Da Nang", "Main"))),
                "NO_MATCH", "invalid-code");

        verify("invalid-name", new Invoice("I-8",
                new Customer("", new Address("Da Nang", "Main"))),
                "NO_MATCH", "invalid-name");

        verify("wrong-root", "not an invoice",
                "NO_MATCH", "wrong-root");

        verify("root-null", null,
                "NO_MATCH", "root-null");

        System.out.println("10/10 tests passed");
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 NestedRecordPatternDebugDemo.java
java NestedRecordPatternDebugDemo
```

**Exact stdout:**

```text
valid -> MATCH:I-1:Ana:HA NOI [ok]
street-null -> MATCH:I-2:Binh:HUE [ok]
customer-null -> NO_MATCH [customer-null]
address-null -> NO_MATCH [address-null]
city-null -> NO_MATCH [city-null]
city-blank -> NO_MATCH [city-blank]
invalid-code -> NO_MATCH [invalid-code]
invalid-name -> NO_MATCH [invalid-name]
wrong-root -> NO_MATCH [wrong-root]
root-null -> NO_MATCH [root-null]
10/10 tests passed
```

The program was run using JDK 24's JShell with the logic and 10 input cases above; `Locale.ROOT` is used in the demo so uppercasing does not depend on the system locale. Both `extract` and `diagnose` return the expected results across all cases; if an expected value differs from actual, `verify` throws `AssertionError` instead of printing "passed".

### Why is each test case valuable?

- `valid` verifies the standard path through all three record layers.
- `street-null` demonstrates that a component captured with `var` can be null without breaking the record pattern, if business rules allow it.
- `customer-null` and `address-null` isolate the two deconstruction layers that cannot match a null nested record.
- `city-null` and `city-blank` prove that **pattern match** does not mean **guard passed**.
- `invalid-code` and `invalid-name` check the order and business conditions after deconstruction succeeds.
- `wrong-root` and `root-null` distinguish a wrong source type from a null selector.

Because `Invoice`, `Customer`, and `Address` are records without validating constructors in this demo program, we can **intentionally** create null/blank data for testing. In a real domain model, consider enforcing invariants in constructors/factories so invalid objects cannot be created in the first place; invalid-data errors are then tested at the **object creation boundary**.

## 7. Debugging in `switch`: a case not running may not be a pattern failure

Pattern matching for `switch` is often used alongside record patterns:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "root-null";
        case Invoice(var code,
                Customer(var name, Address(var city, var street)))
                when code != null && !code.isBlank()
                        && name != null && !name.isBlank()
                        && city != null && !city.isBlank() ->
                "valid:" + code;

        case Invoice(var code,
                Customer(var name, Address(var city, var street))) ->
                "guard-failed";

        case Invoice(var code, Customer(var name, var address)) ->
                "address-null";

        case Invoice(var code, var customer) ->
                "customer-null";

        default -> "wrong-root";
    };
}
```

This is an **illustrative method** meant to be placed in a class with the three declared records; it is not a standalone Java file. It separates the cause groups:

1. `case null` handles a null selector.
2. The branch with `when` returns `valid` when both structure and guard succeed.
3. The branch with the same structure but no guard catches cases where the record was deconstructed but the guard failed.
4. The `Invoice(..., Customer(..., var address))` branch catches cases where `Address(...)` did not match (in this model, `address == null`).
5. The `Invoice(var code, var customer)` branch catches the remaining `customer == null` case.
6. `default` handles values that are not `Invoice`.

**Case ordering matters.** Placing the general pattern `Invoice(var code, var customer)` before the nested patterns will shadow the more specific branches below it. The compiler may report a *dominated case*. Place guarded specific cases before unguarded cases of the same structure.

**Note when debugging `when` branches:** a guard is only evaluated **after the pattern matches**. You cannot conclude that a null component caused the pattern to fail just because a guarded branch did not execute.

## 8. Compile-time errors in nested record patterns vs. runtime non-match

Some errors must be fixed **before running tests**, because the compiler blocks them immediately.

### 8.1. Incorrect number of components

`Customer` declares two components: `name` and `address`. The following snippet is **intentionally wrong**:

```java
// Wrong: Customer has two components, but only one nested pattern is provided.
static boolean badArity(Object value) {
    return value instanceof Invoice(var code, Customer(var name));
}
```

Expected result: the compiler reports an incorrect number of nested patterns. The count, **order**, and types of nested patterns must match the declared record components. This snippet is not included in the runnable file in section 6.

### 8.2. Using a pattern variable out of scope

```java
// Wrong: city does not exist on paths where instanceof fails.
static void badScope(Object value) {
    if (value instanceof Invoice(var code,
            Customer(var name, Address(var city, var street)))) {
        System.out.println(city);
    }
    System.out.println(city); // Compile error.
}
```

Java uses **flow scoping**: a pattern variable can only be used where the compiler can prove the pattern has matched. The variable `city` is valid inside the `if` true branch and on the right-hand side of `&&` when the pattern is on the left-hand side; it is not valid after the `if` block in this example.

**Verified with JDK 24:** a `badArity` variant is rejected by the compiler with `incorrect number of nested patterns`; the `badScope` variant is rejected because `city` is not in scope at the usage site. These are **negative compilation tests**, not `false` results from `instanceof`.

### 8.3. Component types and variable names

`var` is inferred from the static type of the component. `var city` here is `String`, and `var` does not turn Java into a dynamic language. If you replace `city.toUpperCase()` with an operation that only exists on another type, the compiler will report a type error.

Pattern variable names can differ from component names, but the **pattern order** still follows the record declaration. Swapping `name` and `address`, or nesting record patterns at the wrong level, causes a compile error when types are incompatible; for components of the same type, getting the order wrong can even compile while introducing a logic bug. Use clear names and review the original record declaration.

## 9. Accessor throwing an exception: do not confuse with "pattern non-match"

Record patterns perform deconstruction through the record's accessors. If a **custom** accessor throws an exception during matching, the outcome is no longer a simple `false`.

Separate **illustrative example for JShell or a suitable class**:

```java
record AccessorBomb(String data) {
    @Override
    public String data() {
        throw new IllegalStateException("bomb");
    }
}

Object bomb = new AccessorBomb("x");

try {
    System.out.println(bomb instanceof AccessorBomb(var x));
} catch (MatchException e) {
    System.out.println("accessor-exception -> "
            + e.getClass().getSimpleName() + ":"
            + e.getCause().getClass().getSimpleName());
}
```

**Output of the example above (JDK 24):**

```text
accessor-exception -> MatchException:IllegalStateException
```

`MatchException` is Java's exception when a deconstruction operation fails during pattern matching. **Do not treat it as a normal non-match** or silently return `false` in all situations.

When debugging an exception thrown mid-match, inspect the **stack trace**, the original exception type, and `getCause()`. Check whether the accessor performs computation, reads mutable state, or throws exceptions. In most simple data models, keep record accessors clean with minimal side effects and enforce invariants in appropriate constructors/factories.

## 10. Practical debugging workflow with an IDE and logging

1. **Save a reproducible input.** Record the root type, all three record layers, and key values. Do not rely on a description like "the invoice was null" without knowing which layer is null.
2. **Set a breakpoint at `if`/`switch`.** Inspect the selector before matching. For `value instanceof Invoice(...)`, if the selector is null or the wrong type, inspecting deeper makes no sense.
3. **Temporarily write a diagnostic function like `diagnose`.** Stop at each `return "..."` to pinpoint the first failing layer. This is usually more reliable than guessing which nested condition returned `false`.
4. **Trace guards separately.** A skipped `case ... when ...` branch could be due to a pattern non-match or a failing `when`. Place an unguarded pattern case after the guarded case or log conditions using the extracted variables.
5. **Compare against a small test suite.** Include at least root null, wrong type, each nested record null, null component, blank component, and a valid path.
6. **Check case order and dominance.** In `switch`, a general case can shadow a specific case; the compiler catches many of these errors.
7. **Isolate runtime exceptions.** If you see `MatchException`, inspect the accessor cause; if you see `NullPointerException`, check whether a method was called on a null component inside a guard or body.
8. **Reduce to a minimum reproducible example.** Keep just the few records, the matching method, and the failing data; re-test on the project's exact JDK/toolchain.
9. **Run regression tests after fixing.** A passing happy-path test does not prove that null layers and guards are handled correctly.

You can use `javac --release 21 -g NestedRecordPatternDebugDemo.java` when you need to compile with debug information. In an IDE, set breakpoints in `diagnose` and in the result branches; the compiler may lower record patterns into internal operations, so there may not be a clear per-subpattern breakpoint inside a single long expression.

**Safe logging:** Do not print entire objects in production applications if they contain personal information, tokens, or sensitive data. Prefer logging only the input type, failing branch, approved correlation IDs, and the minimal information needed to reproduce the bug.

## 11. Common debugging "pitfalls"

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `instanceof Invoice(...)` is `false` | Wrong selector type, null selector, or a null nested record | Check the outer layer, then each accessor |
| Nested pattern looks right, but `if` still doesn't run | `&&` guard failed | Separate pattern-only from guard; test `city == null`/`city.isBlank()` |
| `Address(null, "Main")` is assumed to be "record didn't match" | Confusing a null component with a null nested record | Test an unguarded pattern: `Address(var city, var street)` can still match |
| `street == null` yet match still succeeds | `var street` allows null and business rules permit it | Confirm the component's nullability rules |
| Specific `case` is unreachable | An earlier general case shadows it | Reorder guarded/specific cases before general ones |
| Compiler reports `incorrect number of nested patterns` | Record pattern is missing or has extra components | Cross-check the `record` declaration |
| Compiler reports cannot find variable `city` | Pattern variable is outside flow scope | Only use it in matched branches/paths |
| `MatchException` occurs | An accessor threw an exception during deconstruction | Inspect cause/stack trace and check custom accessors |
| `NullPointerException` in guard | Calling `isBlank()` before null check or using the wrong operator | Use `city != null && !city.isBlank()` |
| Only "happy path" tests are green | Missing per-layer null cases | Add a test matrix and named assertions as in sections 5–6 |

## 12. Practice exercise

Given:

```java
record Coordinates(Double lat, Double lon) {}
record Place(String label, Coordinates coordinates) {}
record Trip(String tripId, Place destination) {}
```

You need to verify that an `Object input` is a valid `Trip`, with non-null `destination`, `coordinates`, `lat`, and `lon`, and within range:

- Latitude between -90 and 90.
- Longitude between -180 and 180.
- `label` non-null and non-blank.

**Requirements:**

1. Write `instanceof Trip(var tripId, Place(var label, Coordinates(var lat, var lon)))` and guards to validate the values. Place null checks **before** numeric comparisons to avoid unboxing `null`.
2. Write `diagnoseTrip(Object input)` using accessors to distinguish: root null, wrong type, missing destination, missing coordinates, missing lat/lon, out-of-range coordinates, and blank label.
3. Build a test matrix for each case and compare the pattern result with the layer-by-layer diagnosis.
4. Consider adding tests for `Double.NaN` and infinity: an improperly negated range check can let `NaN` slip through; use `Double.isFinite(...)` when the domain requires finite coordinates.
5. Try placing a general `case Trip(...)` before a `when` case, observe compiler/dominance behavior, then fix the order.

**Hint expression** (inside a method with parameter `Object input`):

```java
boolean valid = input instanceof Trip(
        var tripId,
        Place(var label, Coordinates(var lat, var lon)))
        && label != null && !label.isBlank()
        && lat != null && lon != null
        && Double.isFinite(lat) && Double.isFinite(lon)
        && lat >= -90 && lat <= 90
        && lon >= -180 && lon <= 180;
```

This is an **illustrative code snippet** using the exercise's three records, not a standalone Java class. Note: the pattern matches `Coordinates(null, ...)` because `var lat` can be null, so the guard must reject it before unboxing.

## 13. Key takeaways and references

When debugging nested record patterns, **verify the matching layer first, check guards second, and separate exceptions from compilation errors**. Use clearly named models, a layer-by-layer diagnostic function, tests with expected/actual checks, and null cases at every level. Do not infer from a single `false` result that the deepest record pattern failed.

Official documentation:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java 21 API — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
