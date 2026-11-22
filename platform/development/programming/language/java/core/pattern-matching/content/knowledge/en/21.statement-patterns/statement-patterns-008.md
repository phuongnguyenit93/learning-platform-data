# Reducing Nesting with Guard Clauses When Using Patterns in Statements (Java 21)

## 1. The Problem to Solve

In Java, a data-processing method often has to pass through multiple conditions: whether the input has the right type, whether a nested record exists, whether important components are valid, and finally the main business logic. If you place every condition into multiple nested `if` layers, the actual processing gets pushed far to the right and error branches interleave with the happy path.

A **guard clause** is a check at or near the beginning of a block; when a condition **fails to meet the requirements**, you terminate the current execution path early using `return`, `throw`, or `continue` in a loop. Failure conditions are handled one by one, leaving the valid processing at a shallower indentation level.

With Java's **pattern matching**, guard clauses are especially useful because `instanceof` and `record pattern` both check types/structure and declare variables that can only be used when the pattern has matched. When a condition negates a pattern and the failure branch ends with `return`, Java knows that the continuing path **has already matched the pattern**, so the variables declared in the pattern can be used afterward.

This lesson applies to:
- Type patterns `obj instanceof String text` (standard since Java 16).
- Record patterns `obj instanceof Order(var customer, var quantity)` and nested record patterns (standard since Java 21, JEP 440).
- Pattern matching in `switch` statements and `when` (standard since Java 21, JEP 441).
- Guard clauses using `return`, `throw`, and `continue`, along with preserving pattern variable scope (*flow scoping*).

All complete programs in this lesson use **JDK 21 or later**, without needing `--enable-preview`.

## 2. Before and After: Reducing `if` Nesting Levels

Data definitions:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(Customer customer, int quantity) {}
```

A deeply nested approach (placed inside a method that takes `Object value` and returns `String`):

```java
if (value instanceof Order(Customer(var name, Address(var city)), var quantity)) {
    if (city != null && !city.isBlank()) {
        if (quantity > 0) {
            return "Ship " + quantity + " for " + name + " to " + city;
        }
        return "Invalid quantity";
    }
    return "Missing city";
}
return "Invalid order structure";
```

This code is correct, but the business logic sits inside three levels of `if`. When additional requirements such as quantity limits, permission checks, or remaining stock checks appear, the nesting depth continues to grow.

Written with guard clauses:

```java
if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
    return "Invalid order structure";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
if (quantity <= 0) {
    return "Invalid quantity";
}
return "Ship " + quantity + " for " + name + " to " + city;
```

Both versions preserve the **exact same result priority order**:

1. The input must match the `Order → Customer → Address` structure; if not, return `Invalid order structure`.
2. If the structure matches but `city` is missing or contains only whitespace, return `Missing city`.
3. If the city is valid but the quantity is non-positive, return `Invalid quantity`.
4. Only when all conditions are satisfied does the main logic build the shipping message.

The main benefit is that **the happy path runs straight down the method body**. This style makes it easy to add validation checks without forcing the core logic one level deeper.

## 3. Why Can Pattern Variables Be Used After `if (!(...))`?

This is a key point about **flow scoping**, not just a code-formatting trick.

Consider the simple type-pattern version:

```java
static int lengthOf(Object raw) {
    if (!(raw instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

`raw instanceof String text` attempts to match the type and binds the pattern variable `text` if successful. The `!` operator negates the condition. If the `if` condition is true, the method returns `-1` immediately. Therefore, **every execution path that can reach `text.length()`** is a path where `String text` has already matched.

The compiler applies the *definitely matched* rule (the pattern is guaranteed to have matched along the control flow), allowing `text` to be used in subsequent statements. With nested **record patterns**, the same principle applies to component variables:

```java
static String cityOf(Object input) {
    if (!(input instanceof Order(
            Customer(var name, Address(var city)), var quantity))) {
        return "No complete address";
    }
    return name + " / " + city + " / " + quantity;
}
```

At the end of the `if`, Java knows that `Order(...)`, `Customer(...)`, and `Address(...)` have matched. Thus `name` has type `String`, `city` has type `String`, and `quantity` has type `int`; they can all be used in the `return` statement.

Contrast this with a positive condition that does not terminate all paths:

```java
// DOES NOT COMPILE: text is not definitely assigned after if.
static int invalid(Object raw) {
    if (raw instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

In the invalid example, after the `if` finishes, the input might not be a `String`, so `text` is not guaranteed to be in scope. This can be fixed by returning immediately inside the matching branch or using a negated guard clause like `lengthOf`.

**Important condition:** The failing guard branch must **not be able to complete normally and fall through to the statements below**, for example by using `return` or `throw`. If you only log inside `if (!(...))` and continue, Java cannot treat the pattern variables as definitely assigned.

## 4. Pattern Failure and Data Validation Are Two Different Kinds of Guards

A nested record pattern checks structure, whereas subsequent guard clauses check **data/business rules**.

With `Order(Customer(var name, Address(var city)), var quantity)`:

- If the outer value is not an `Order`, the pattern does not match.
- If the `customer` component is `null`, `Customer(...)` does not match.
- If the `address` component is `null`, `Address(...)` does not match.
- If `Address` exists but its `city` component is `null`, `var city` can still receive `null`; a record pattern by itself does not guarantee a non-null `String`.
- If `quantity` is `0` or negative, the pattern still matches because the component has type `int`; that is a business rule violation that must be checked separately.

Therefore, guard clauses should progress from **shape/type**, through **component validity**, to **business rules**. For example:

```java
if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
    return "Invalid order structure";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
if (quantity <= 0) {
    return "Invalid quantity";
}
return "Ship " + quantity + " for " + name + " to " + city;
```

The condition `city == null || city.isBlank()` short-circuits: when `city == null`, the second operand does not run, avoiding calling `isBlank()` on `null`. In practice, you can also add `name == null || name.isBlank()` if the business contract requires a valid customer name. Do not assume that matching `var name` guarantees the name is non-null.

A guard containing a nested pattern can combine multiple structural checks at once. However, if the application needs to **distinguish between a missing customer error and a missing address error**, split them into multiple steps instead of letting every structural failure return the same message:

```java
// Illustrative example inside a method accepting Object value.
if (!(value instanceof Order(var customer, var quantity))) {
    return "Not an order";
}
if (customer == null) {
    return "Missing customer";
}
if (!(customer.address() instanceof Address(var city))) {
    return "Missing address";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
return "Ready";
```

Here `customer` is inferred as type `Customer`, so you can call `customer.address()` after the first guard and check for `null` separately. Splitting into steps may be longer than a single nested pattern, but it provides more specific errors.

## 5. Using `throw` When an Invalid Condition Violates an API Contract

Not every guard clause returns a default value. In object-construction methods or API handlers with strict contracts, invalid input may need to throw an exception:

```java
record PositiveCount(int value) {}

static int readCount(Object raw) {
    if (!(raw instanceof PositiveCount(var count))) {
        throw new IllegalArgumentException("Expected PositiveCount");
    }
    if (count <= 0) {
        throw new IllegalArgumentException("Count must be positive");
    }
    return count;
}
```

Both `return` and `throw` terminate the error path, so `count` can be used after the negated guard. Choose `return` for invalid outcomes that are **designed as part of normal control flow**, and `throw` for contract violations that the caller must handle.

Do not automatically throw exceptions inside data-filtering loops: if the goal is to skip non-matching records and keep going, `continue` usually expresses the intent better.

## 6. Guard Clauses in Loops: `continue` to Skip Non-Matching Data

When finding the first record that satisfies a condition in an array or collection, you can use `continue` after guards instead of multiple `if` layers:

```java
static String firstShippable(Object[] values) {
    for (Object value : values) {
        if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
            continue;
        }
        if (city == null || city.isBlank() || quantity <= 0) {
            continue;
        }
        return "Found " + name + ":" + quantity + "@" + city;
    }
    return "No shippable order";
}
```

How it works:

- The current element does not match the nested record pattern: `continue` moves to the next element.
- The value matches, but the city is blank or the quantity is invalid: skip it.
- The line `return "Found ..."` only executes when all guards have been passed. Java knows the pattern variables are assigned along that path.
- If the loop finishes without finding a suitable element, the method returns `No shippable order`.

Unlike guards that use `return`, here **an invalid element does not stop the entire search**. This is especially useful when processing events or collections containing multiple object types.

Consider extracting complex validation logic into a separate helper method if a loop accumulates too many guards, so the iteration method does not have to know every detail of the business structure.

## 7. Guard Clauses with `switch` Statements and `when`

In Java 21, a `switch` statement can contain pattern-matching cases. A `when` clause is evaluated **after the pattern matches**, acting as an additional filter on a `case` branch. Despite the similar name, a **`when` guard is not synonymous with a guard clause**:

- `when` is a **switch-branch guard**: it decides whether that branch is selected; if false, evaluation continues to other matching branches.
- A **guard clause** is a control-flow organization style: it checks an invalid condition and exits the current processing early with `return`/`throw`/`continue`.

A `switch` statement using `case` branches that return early:

```java
// Example inside a method returning String, with Order/Customer/Address already declared.
switch (value) {
    case null -> {
        return "No input";
    }
    case Order(Customer(var name, Address(var city)), var quantity)
            when city != null && !city.isBlank() && quantity > 0 -> {
        return "Accepted " + name + "@" + city;
    }
    case Order(var customer, var quantity) -> {
        return "Invalid order";
    }
    default -> {
        return "Not an order";
    }
}
```

Here each branch is a **statement block** containing the method's `return`; `yield` is not used. If you change this to `return switch (value) { ... };`, the `switch` becomes an **expression**, and multi-statement blocks would use `yield` to produce a value rather than `return` to "return a value from the switch".

Branch ordering must be accurate: the more specific `Order(...) when ...` branch must appear before the general `Order(...)` branch. Reversing the order can cause the specific branch to be dominated and trigger a compilation error. `case null` handles a `null` selector; `default` does not automatically cover `null`. Arrow branches `->` do not fall through.

When multiple sequential conditions apply to **one** record type, consecutive `if` guard clauses are often clearer than a `switch`. When you need to handle **multiple different data types**, a `switch` with type/record patterns can be more readable.

## 8. Complete Java 21 Example: Comparing Nesting and Guard Clauses

Create the file **`GuardClausePatternDemo.java`**:

```java
public class GuardClausePatternDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(Customer customer, int quantity) {}
    record Failure(String reason) {}

    static String nested(Object value) {
        if (value instanceof Order(Customer(var name, Address(var city)), var quantity)) {
            if (city != null && !city.isBlank()) {
                if (quantity > 0) {
                    return "Ship " + quantity + " for " + name + " to " + city;
                }
                return "Invalid quantity";
            }
            return "Missing city";
        }
        return "Invalid order structure";
    }

    static String guarded(Object value) {
        if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
            return "Invalid order structure";
        }
        if (city == null || city.isBlank()) return "Missing city";
        if (quantity <= 0) return "Invalid quantity";
        return "Ship " + quantity + " for " + name + " to " + city;
    }

    static String firstShippable(Object[] values) {
        for (Object value : values) {
            if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
                continue;
            }
            if (city == null || city.isBlank() || quantity <= 0) continue;
            return "Found " + name + ":" + quantity + "@" + city;
        }
        return "No shippable order";
    }

    static String message(Object value) {
        if (value == null) return "No input";
        if (value instanceof Failure(var reason)) return "Failure: " + reason;
        if (!(value instanceof Order(var customer, var quantity))) return "Unsupported";
        if (customer == null) return "Missing customer";
        return "Order quantity " + quantity;
    }

    static String switchStatement(Object value) {
        switch (value) {
            case null -> { return "No input"; }
            case Order(Customer(var name, Address(var city)), var quantity)
                    when city != null && !city.isBlank() && quantity > 0 -> {
                return "Accepted " + name + "@" + city;
            }
            case Order(var customer, var quantity) -> { return "Invalid order"; }
            default -> { return "Not an order"; }
        }
    }

    public static void main(String[] args) {
        Object ok = new Order(new Customer("Lan", new Address("Da Nang")), 2);
        Object badCity = new Order(new Customer("Lan", new Address(" ")), 2);
        Object badQty = new Order(new Customer("Minh", new Address("Hue")), 0);
        Object absent = new Order(new Customer("An", null), 3);

        System.out.println(nested(ok));
        System.out.println(guarded(ok));
        System.out.println(guarded(badCity));
        System.out.println(guarded(badQty));
        System.out.println(guarded(absent));
        System.out.println(guarded(null));
        System.out.println(firstShippable(new Object[]{null, badQty, ok}));
        System.out.println(firstShippable(new Object[]{badCity, absent}));
        System.out.println(message(new Failure("timeout")));
        System.out.println(message(new Order(null, 4)));
        System.out.println(switchStatement(ok));
        System.out.println(switchStatement(badCity));
        System.out.println(switchStatement(null));
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 GuardClausePatternDemo.java
java GuardClausePatternDemo
```

**Output:**

```text
Ship 2 for Lan to Da Nang
Ship 2 for Lan to Da Nang
Missing city
Invalid quantity
Invalid order structure
Invalid order structure
Found Lan:2@Da Nang
No shippable order
Failure: timeout
Missing customer
Accepted Lan@Da Nang
Invalid order
No input
```

Key takeaways from the output:

1. `nested(ok)` and `guarded(ok)` produce the same result, demonstrating that restructuring the control flow preserves the happy-path result.
2. `badCity` matches the record but `city.isBlank()` is true; the guard returns `Missing city`.
3. `badQty` has `quantity == 0`; the third guard returns `Invalid quantity`.
4. `absent` has `Customer.address() == null`; the nested `Address(...)` fails to match, so it returns `Invalid order structure`.
5. `guarded(null)` returns `Invalid order structure` without throwing an exception, because `null instanceof Order(...)` evaluates to false.
6. `firstShippable` skips the null element and the invalid-quantity order to find the valid element `ok`.
7. `message(new Failure("timeout"))` handles `Failure` first and exits early; `message(new Order(null, 4))` extracts the `Order` structure and catches the null customer in the next guard.
8. `switchStatement(ok)` uses `case Order(...) when ...` to produce the accepted result, while `switchStatement(badCity)` falls into the general `Order(...)` branch. `switchStatement(null)` enters `case null`.

The example demonstrates all three ways of exiting a branch early: `return` in a method, `continue` in a loop, and `return` in a `switch statement` branch. In production code, you do not need to keep both `nested` and `guarded`; they are placed side by side here only for comparison.

## 9. Common Pitfalls

| Mistake / Misconception | Why it is a problem | How to fix |
| --- | --- | --- |
| Writing `if (!(raw instanceof String text)) { log(); }` and then using `text` | The failure branch can finish normally and fall through; the compiler cannot guarantee the pattern matched. | Add `return`/`throw` in the guard, or use a direct matching branch. |
| Forgetting `!` in the guard | `if (raw instanceof Type t) return...` may exit immediately when the data has the right type, inverting the intent. | Express the condition as the **invalid** state and verify each branch's result. |
| Using `&&` instead of `||` in `city == null || city.isBlank()` | Writing `city == null && city.isBlank()` can dereference `null` in the second operand. | Use `||` to short-circuit with the right logic. |
| Assuming a nested record pattern means every component is non-null | `var city` can still be `null` even if `Address(...)` matches. | Check `city == null` before calling methods on it. |
| Overly deep patterns hiding which level failed | One large guard cannot tell you which specific level was missing. | Split guards per level if precise error messages are needed. |
| Using `continue` outside a loop | `continue` is only valid inside a loop. | Use `return` to exit the method or refactor the loop. |
| Using `return` in every guard without considering the workflow | When processing a list, one invalid record can abort the rest of the items. | Use `continue` when you need to skip an element and keep searching. |
| Confusing `when` with a guard clause | `when` only filters a `case` branch; it does not terminate the method by itself. | Use `return`/`throw`/`continue` to express early exit. |
| Placing a broad `case Order(...)` branch before a branch with `when` | The narrower branch can be dominated and fail to compile. | Put narrower branches first, broader branches after. |
| Treating `record pattern` code as a standard feature on JDK 17 | Record patterns were finalized in Java 21. | Use JDK 21+ for these examples. |
| Adding too many guards, repeating checks, or changing error priority | Paths can become hard to read, and results when multiple conditions fail simultaneously may change. | Group by check type, choose an intentional error order, and extract helper methods when needed. |

Do not force a guard clause onto every `if`. For a small condition where both the true and false branches carry equal weight, `if/else` can be clearer. The goal is to make the normal flow easy to recognize and verify, not to reduce brace depth at all costs.

## 10. Practice Exercise

Given two records:

```java
record Profile(String username, String email) {}
record Registration(Profile profile, int age) {}
```

**Requirements:** Write a method `static String validate(Object input)` in this order:
1. Only accept a `Registration` with a non-null `Profile`; otherwise return `Invalid structure`.
2. If `username` is null or blank after trimming whitespace, return `Missing username`.
3. If `age < 18`, return `Underage`.
4. If `email` is null or does not contain `@`, return `Invalid email`.
5. If valid, return `Registered: <username>`.

**Solution with guard clauses (Java 21):**

```java
static String validate(Object input) {
    if (!(input instanceof Registration(
            Profile(var username, var email), var age))) {
        return "Invalid structure";
    }
    if (username == null || username.isBlank()) {
        return "Missing username";
    }
    if (age < 18) {
        return "Underage";
    }
    if (email == null || !email.contains("@")) {
        return "Invalid email";
    }
    return "Registered: " + username;
}
```

All variables `username`, `email`, and `age` are in scope after the first guard because non-matching inputs have already exited the method. Subsequent conditions check each constraint and exit early on failure. Every valid path reaches `return "Registered: " + username;` at the end.

Try it yourself:

- `validate(new Registration(new Profile("Mai", "mai@example.com"), 20))` → `Registered: Mai`.
- `validate(new Registration(null, 20))` → `Invalid structure`.
- `validate(new Registration(new Profile(" ", "mai@example.com"), 20))` → `Missing username`.
- `validate(new Registration(new Profile("Mai", "mai@example.com"), 16))` → `Underage`.
- `validate(new Registration(new Profile("Mai", "invalid"), 20))` → `Invalid email`.

The solution snippet is an illustrative method using the two records declared right above it; a complete runnable file with `main` is in section 8.

An extension: if you want a separate message when `Registration.profile == null`, match `Registration(var profile, var age)` first, then check `profile == null` in another guard. Only deconstruct `Profile(...)` after confirming it exists.

## 11. Safe Refactoring Checklist

When converting deeply nested code to guard clauses:

1. List the **preconditions** and error priority order before changing structure. Keep the same result/exception for each kind of input.
2. Put invalid conditions into short `if` statements and exit early. With patterns, this is typically `if (!(obj instanceof Type(var x))) return ...;`.
3. Confirm that pattern variables remain in scope after the guard along the matched path, especially when combining `!`, `&&`, and `||`.
4. Distinguish between a `null` nested record (where deconstruction fails to match the pattern) and a `null` component bound via `var` (which may require an explicit check).
5. Choose the right exit mechanism: `return` for a method, `throw` for contract violations, and `continue` for non-matching elements in a loop.
6. For multiple distinct types, consider a `switch statement` with pattern cases; distinguish `when` from a guard clause.
7. Test the happy path, `null`, wrong types, missing nested records, boundary values (0, negative, blank strings), and multiple simultaneous failures.

**Remember:** combining **pattern matching** with **guard clauses** moves type/structure checks to the top, letting you write the core business logic along a single clear path. In Java 21, after `if (!(obj instanceof Pattern(...))) return ...;`, the compiler allows pattern variables to be used afterward because they are definitely matched on every continuing path.

**References:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching with instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html), [Java Language Specification — Scope for Pattern Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2).
