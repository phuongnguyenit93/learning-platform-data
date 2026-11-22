# Combining Deconstruction with Conditions (Java 21+)

## 1. Lesson Objectives

**Deconstruction** in Java is the operation of **extracting the components of a `record` using a record pattern**. When combined with **Boolean conditions**, we can express the rule "the data must have this exact structure **and** the values inside must meet these criteria" without having to call each accessor one by one or cast types manually.

For example, given `record Point(int x, int y)`, we want to accept a point only when both coordinates are positive:

```java
if (value instanceof Point(var x, var y) && x > 0 && y > 0) {
    System.out.println("Điểm ở góc phần tư I");
}
```

Here, **`Point(var x, var y)` checks the structure and extracts the values**, while **`x > 0 && y > 0` checks the rule on the extracted values**. The two parts work together thanks to the short-circuit `&&` operator and pattern variable scoping rules.

Both **Record Patterns (JEP 440)** and **Pattern Matching for `switch` (JEP 441)** are stable features as of **Java 21**. The examples below use **JDK 21+** and do not require `--enable-preview`. Java 17 already supported `record`, but did not yet have the stable record pattern syntax shown in this lesson.

After this lesson, you will be able to distinguish:
- **Structural checks** using record patterns and **value checks** using conditional expressions.
- How to combine record patterns with `instanceof ... && ...` and `case ... when ...`.
- How to use deconstructed variables in conditions, guards, and branch bodies.
- Scenarios involving non-matching nested records, `null` components, false guards, `case` ordering, and fallback branches.
- When to use a guard versus validating data in a constructor or business method.

## 2. Two Steps: Deconstruct Structure First, Check Conditions After

Consider the declaration:

```java
record Point(int x, int y) {}
```

The record pattern:

```java
Point(var x, var y)
```

means:

1. The value being matched must be a non-null `Point` object.
2. The record has exactly two components as declared: `x` and `y`. The nested pattern `var x` receives the first component; `var y` receives the second component.
3. Java infers that both `x` and `y` have type `int`, because the record declaration has two `int` components.
4. Once the pattern **matches completely**, the variables can be used in conditions and handling branches as permitted by scoping rules.

Deconstruction **does not automatically validate** "the point must have positive coordinates", "the age must be at least 18", or "the code must not be blank". These conditions are added via Boolean expressions, typically `&&` in `if` or `when` in `switch`.

A conditional branch can be read in this order:

```text
Input value
     |
     v
Matches outer record type?
     | no
     +--------------------------> Other branch
     |
    yes
     v
Matches all component patterns?
     | no
     +--------------------------> Other branch
     |
    yes
     v
Bind extracted variables
     |
     v
Boolean condition/guard is true?
     | no
     +--------------------------> Other branch
     |
    yes
     v
Execute branch body
```

This is a **logical reading model**; you should not rely on it to guess JVM optimization details. A record pattern reads components via accessors; it does not create a new record, nor does it automatically make data immutable if a component references a mutable object.

## 3. Using `instanceof` with `&&`

### 3.1. Pattern Variables Are Usable on the Right Side of `&&`

```java
static boolean isPositivePoint(Object value) {
    return value instanceof Point(var x, var y)
        && x > 0
        && y > 0;
}
```

Assuming `Point` is already defined, Java processes this according to the following logic:

- If `value` is not a `Point`, the `instanceof` expression returns `false`; the clauses `x > 0` and `y > 0` **are not evaluated**.
- If `value` is a `Point`, the record pattern extracts `x` and `y`. The variables are then allowed to participate in the remainder of the `&&` expression.
- If `x <= 0`, the `&&` operator short-circuits; there is no need to check `y > 0`.
- Only when all conditions are true is the result `true`.

**Why does the compiler allow using `x` and `y` on the right side of `&&`?** Because the right-hand side is only executed when the left-hand side is true; the compiler has proof that the pattern matched, so both variables are definitely assigned.

### 3.2. Variable Scope in `if`

```java
if (value instanceof Point(var x, var y)
        && x > 0 && y > 0) {
    System.out.println("x=" + x + ", y=" + y);
}
```

`x` and `y` can be used inside the `if` body because the body only runs when the entire condition is true. They do not become local variables accessible on every line after the `if`.

You can add more conditions directly related to the data:

```java
record Employee(String name, int age) {}

// Illustrative snippet within a scope that has the variable value:
if (value instanceof Employee(var name, var age)
        && name != null
        && !name.isBlank()
        && age >= 18) {
    System.out.println(name + " đủ tuổi");
}
```

The condition `name != null` must come **before** `!name.isBlank()` to avoid a `NullPointerException`. When `name` is null, `&&` stops immediately and does not invoke a method on null.

### 3.3. Do Not Arbitrarily Replace `&&` with `||`

An **intentionally invalid example that does not compile**:

```java
// WRONG: if the left side is false, x is not bound yet.
if (value instanceof Point(var x, var y) || x > 0) {
    System.out.println("...");
}
```

The right-hand side of `||` is evaluated when the left-hand side is **false**. At that point, the pattern may not have matched, so `x` cannot be used as in the example.

If you want to check "not a point **or** a point with positive x", you can write clear separate branches:

```java
if (!(value instanceof Point(var x, var y))) {
    System.out.println("Không phải Point");
} else if (x > 0) {
    System.out.println("Point có x dương");
}
```

In `else if`, the compiler knows that the `instanceof` matched because the previous negated branch was not taken. This illustrates **flow scoping**: the scope of a pattern variable depends on control-flow paths that guarantee the pattern succeeded.

## 4. Using `switch` with `when` After a Record Pattern

For multiple classification conditions, writing a `switch` is often clearer than an `if/else if` chain.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có điểm";

        case Point(var x, var y) when x == 0 && y == 0 ->
            "Gốc tọa độ";

        case Point(var x, var y) when x > 0 && y > 0 ->
            "Góc phần tư I";

        case Point(var x, var y) ->
            "Điểm khác";

        default -> "Không phải Point";
    };
}
```

This snippet is an **illustrative method**, assuming `Point` is already declared in the same valid scope.

How to read `case Point(var x, var y) when x > 0 && y > 0`:

1. The `switch` selector must match the record pattern `Point(var x, var y)`.
2. If it matches, `x` and `y` become variables available to the guard.
3. Java evaluates `x > 0 && y > 0`.
4. Only when the guard is true is the part after `->` executed.
5. If the guard is false, the next branch is considered; therefore, the unguarded `case Point(var x, var y)` at the end handles the remaining points.

**`when` is only used in `switch` pattern `case` labels**, not after `instanceof` in an `if`. The corresponding constructs are:

| Purpose | Syntax |
| --- | --- |
| A condition in `if` | `value instanceof Point(var x, var y) && x > 0` |
| Selecting a branch in `switch` | `case Point(var x, var y) when x > 0 -> ...` |
| Matching all remaining `Point`s | `case Point(var x, var y) -> ...` |

A guard must have type `boolean` (or an expression usable as a valid Boolean condition). It can call methods on extracted variables; prefer readable conditions without side effects.

## 5. Nested Deconstruction Followed by Business Conditions

Record patterns can be **nested** to both validate the input structure and extract data located deep across multiple records.

Given the data:

```java
record Customer(String name, int age) {}
record Address(String city, String postalCode) {}
record Order(String code, Customer customer, Address address, long amount) {}
```

The full pattern:

```java
Order(
    var code,
    Customer(var name, var age),
    Address(var city, var postalCode),
    var amount
)
```

Explanation from outside to inside:

- `Order(...)`: the selector must be a non-null `Order`.
- `var code`: extracts the order code as a `String`.
- `Customer(var name, var age)`: the second component must be a non-null `Customer`; extracts `String name` and `int age`.
- `Address(var city, var postalCode)`: the third component must be a non-null `Address`; extracts the two corresponding strings.
- `var amount`: extracts `long amount`.

Only after **all record levels match** do we use a guard to check business conditions:

```java
case Order(
        var code,
        Customer(var name, var age),
        Address(var city, var postalCode),
        var amount)
        when age >= 18
            && name != null && !name.isBlank()
            && city != null && !city.isBlank()
            && postalCode != null && !postalCode.isBlank()
            && amount >= 1_000_000L ->
    "Đơn hàng ưu tiên: " + code;
```

Note: **`Customer(...)` and `Address(...)` require the corresponding record component to be non-null**; conversely, `var name`, `var city`, and `var postalCode` are unconditional patterns for the component type, so they can receive a `null` value directly. Therefore, these strings still need null checks before calling `isBlank()`.

When reading a long guard, group it by meaning: (1) age, (2) name, (3) address, (4) order amount. If the business rule is too complex, name the condition with a pure function so readers can understand it quickly.

## 6. Complete Program: `instanceof`, `when`, and Nested Deconstruction

Create the file **`ConditionDeconstructionDemo.java`** with the following content:

```java
public class ConditionDeconstructionDemo {
    record Point(int x, int y) {}
    record Customer(String name, int age) {}
    record Address(String city, String postalCode) {}
    record Order(String code, Customer customer,
                 Address address, long amount) {}

    // A Boolean condition: only inspect coordinates when the pattern succeeds.
    static boolean isInQuadrantI(Object value) {
        return value instanceof Point(var x, var y)
            && x > 0
            && y > 0;
    }

    // Multiple result groups: pattern -> guard -> branch.
    static String classifyPoint(Object value) {
        return switch (value) {
            case null -> "Không có điểm";
            case Point(var x, var y) when x == 0 && y == 0 ->
                "Gốc tọa độ";
            case Point(var x, var y) when x > 0 && y > 0 ->
                "Góc phần tư I";
            case Point(var x, var y) ->
                "Điểm khác (" + x + ", " + y + ")";
            default -> "Không phải Point";
        };
    }

    static String routeOrder(Object value) {
        return switch (value) {
            case null -> "Không có đơn hàng";

            // Complete structure and meets priority conditions.
            case Order(
                    var code,
                    Customer(var name, var age),
                    Address(var city, var postalCode),
                    var amount)
                    when age >= 18
                        && name != null && !name.isBlank()
                        && city != null && !city.isBlank()
                        && postalCode != null
                        && !postalCode.isBlank()
                        && amount >= 1_000_000L ->
                "Ưu tiên: " + code + " - " + name + " - " + city;

            // Complete Customer info, but age is under 18.
            case Order(
                    var code,
                    Customer(var name, var age),
                    var address,
                    var amount)
                    when age < 18 ->
                "Cần xác minh tuổi: " + code;

            // Do not drill into missing components; receive them with var.
            case Order(var code, var customer, var address, var amount)
                    when customer == null || address == null ->
                "Thiếu hồ sơ hoặc địa chỉ: " + code;

            // All remaining Orders are handled here.
            case Order(var code, var customer, var address, var amount) ->
                "Thông thường: " + code;

            default -> "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        System.out.println(isInQuadrantI(new Point(2, 3)));
        System.out.println(isInQuadrantI(new Point(-1, 3)));

        System.out.println(classifyPoint(new Point(0, 0)));
        System.out.println(classifyPoint(new Point(2, 3)));
        System.out.println(classifyPoint(new Point(-1, 3)));
        System.out.println(classifyPoint("abc"));

        System.out.println(routeOrder(new Order(
            "DH-01",
            new Customer("An", 22),
            new Address("Hà Nội", "10000"),
            1_200_000L)));

        System.out.println(routeOrder(new Order(
            "DH-02",
            new Customer("Bình", 16),
            new Address("Huế", "53000"),
            1_500_000L)));

        System.out.println(routeOrder(new Order(
            "DH-03",
            null,
            new Address("Đà Nẵng", "50000"),
            2_000_000L)));

        System.out.println(routeOrder(new Order(
            "DH-04",
            new Customer("", 27),
            new Address("TP.HCM", "70000"),
            1_200_000L)));

        System.out.println(routeOrder(null));
    }
}
```

Compile in the directory containing the file using **JDK 21 or newer**:

```bash
javac --release 21 -encoding UTF-8 ConditionDeconstructionDemo.java
java ConditionDeconstructionDemo
```

Output:

```text
true
false
Gốc tọa độ
Góc phần tư I
Điểm khác (-1, 3)
Không phải Point
Ưu tiên: DH-01 - An - Hà Nội
Cần xác minh tuổi: DH-02
Thiếu hồ sơ hoặc địa chỉ: DH-03
Thông thường: DH-04
Không có đơn hàng
```

### Why Does Each Order Enter the Right Branch?

- **DH-01:** `Order` has non-null `Customer` and `Address`; `age = 22`, name/city/postalCode are non-blank, and `amount = 1_200_000L`. The nested pattern and all guard conditions are true, so it enters the **Ưu tiên** (Priority) branch.
- **DH-02:** complete structure, but `age = 16` makes the priority guard false. The second branch's guard `age < 18` is true, so it enters **Cần xác minh tuổi** (Age verification required).
- **DH-03:** `customer == null` causes the `Customer(...)` pattern of the first and second branches **not to match**. The third branch only uses `var customer` so it accepts null; the guard `customer == null || address == null` is true and prints **Thiếu hồ sơ hoặc địa chỉ** (Missing profile or address).
- **DH-04:** complete structure, but `name` is an empty string, making `!name.isBlank()` false. Age is not under 18 and no record components are missing, so it enters the general `Order(...)` branch **Thông thường** (Standard).
- `routeOrder(null)`: handled directly at `case null`. Do not expect `default` to catch null in pattern-matching `switch`.

The example is written to expose **the precedence order of rules**, not to suggest that orders with an empty name should always be accepted in a real system. In real software, profile validity requires a unified validation rule.

## 7. A Failed Guard Differs from a Non-Matching Pattern

This is the most important distinction when combining deconstruction with conditions.

| Case | Record pattern | Guard | Result |
| --- | --- | --- | --- |
| Input is not an `Order` | Does not match at outer level | Not evaluated | Check other branches |
| `Order.customer() == null` with `Customer(...)` pattern | Does not match at `Customer` level | Not evaluated | Check shallower or other branches |
| `Customer.name() == null` with `Customer(var name, var age)` | Can still match; `name` receives null | `name != null` check returns false | Check other branches |
| `age = 16` with full nested pattern | Matches | `age >= 18` returns false | Check other branches |
| `age = 22`, valid name, amount meets threshold | Matches | True | Execute priority branch |

**A nested record pattern only succeeds when every record pattern at every level succeeds.** The guard condition is evaluated after the entire pattern matches. A false guard means "the data matches the shape, but does not satisfy this branch's rule".

With a Boolean chain:

```java
when name != null && !name.isBlank() && age >= 18
```

if `name == null`, the remaining parts are not evaluated. With `||`, the order also short-circuits, but the logic is different:

```java
when customer == null || address == null
```

Only **one** of the two components needs to be missing for the guard to be true. The `||` in this guard is valid because both `customer` and `address` are already bound by `var` in the pattern to the left of `when`. Do not confuse this with using `||` **after an `instanceof`**, where the pattern variable might not exist.

## 8. Branch Ordering, Dominance, and Exhaustiveness

When multiple `case`s can match the same record, top-to-bottom order determines which branch is chosen. Prefer placing **specific and guarded** branches first, and the **general** branch last.

An **intentionally invalid example that does not compile**:

```java
// Illustrates a dominance error.
return switch (value) {
    case Point(var x, var y) -> "Mọi điểm";
    case Point(var x, var y) when x > 0 -> "Điểm có x dương";
    default -> "Khác";
};
```

The unguarded `Point(var x, var y)` branch before it already matches every non-null `Point`; the subsequent branch is therefore dominated (shadowed). Swap their order:

```java
return switch (value) {
    case Point(var x, var y) when x > 0 -> "Điểm có x dương";
    case Point(var x, var y) -> "Mọi điểm còn lại";
    default -> "Khác";
};
```

The snippet above is a **supplemental example inside a method with `value` and a `Point` declaration**, not a standalone file; if `value` can be null, a `case null` policy is still needed at runtime.

**Do not treat guards as covering the entire type.** For example:

```java
// WRONG: switch expression is not exhaustive for all Object values.
return switch (value) {
    case Point(var x, var y) when x > 0 -> "x dương";
};
```

A selector of type `Object` can receive a `String`, a `Point` with `x <= 0`, etc. Subsequent branches or `default` are needed so the expression produces a result on every required path. If using a `sealed` hierarchy, the compiler can check exhaustiveness across all declared subtypes; arbitrary guards generally cannot replace a general branch covering each type.

With a `switch` expression, a branch with multiple statements can use a block and `yield`:

```java
case Point(var x, var y) when x > 0 -> {
    String text = "x dương: " + x;
    yield text;
}
```

The variables `x` and `y` can be used in the guard and branch body, but are no longer in scope in another `case` or outside the `switch`.

## 9. Distinguishing Data Filtering from Data Validation

**Patterns + guards are suitable for choosing how to handle data** based on its current structure and values. **Constructors or business classes are suitable for blocking invalid objects at creation time**.

Example of a record with an invariant on customer name:

```java
record ValidCustomer(String name, int age) {
    ValidCustomer {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be nonnegative");
        }
    }
}
```

This is a **syntactically standalone record declaration**, which can be placed in an appropriate Java class/compilation unit. When the constructor already blocks null/blank names and negative ages, code in other branches can rely on that invariant. Even so, guards remain useful for **contextual rules** such as "the customer must be at least 18 years old to perform this action".

Some practical notes:

- If a condition is complex, extract it into a clearly named method, such as `isEligibleCustomer(name, age)`, instead of putting a dozen hard-to-read comparisons inside `when`.
- Avoid conditions with side effects in guards. `switch` may evaluate guards of multiple branches; behavior should be predictable.
- Record patterns invoke accessors to retrieve components. A customized record accessor can behave unusually or throw an exception. Do not use guards as a way to "catch" arbitrary accessor errors.
- Avoid very deep patterns if you only need one component. You can stop at `var address` and call a helper method, making the condition structure clearer.
- `var` in a record pattern **is inferred from the declared component type**; it does not turn an `int` into an `Object` or automatically cast an incompatible reference value.
- Just because Java allows a pattern to match a structure does not mean the whole object is always valid for business logic. Choose a fallback branch that fits your system's policy.

## 10. Common Mistakes and Fixes

| Mistake | Why it happens | How to fix |
| --- | --- | --- |
| Writing `case Point(var x, var y) && x > 0` | `case` does not use `if`-style Boolean chaining | Write `case Point(var x, var y) when x > 0 -> ...`. |
| Writing `value instanceof Point(var x, var y) when x > 0` | `when` is for `switch` `case` labels | Use `instanceof ... && x > 0`. |
| Using an extracted variable on the right of `||` after `instanceof` | The pattern might fail so the variable may not be bound | Use `&&` when checking conditions after a successful pattern; split branches for other logic. |
| Calling `name.isBlank()` when `name` may be null | `var name` on a reference component can receive null | Write `name != null && !name.isBlank()`. |
| Confusing `Customer(...)` with `var customer` | A nested record pattern requires a non-null `Customer`, whereas `var` can receive a null component | Choose the appropriate nesting depth and add a branch to handle missing data. |
| Guard is skipped | A record pattern level failed to match earlier | Check the outer record type, each component, and nested records before looking at the guard. |
| Specific case is unreachable | A general branch placed earlier causes dominance | Order conditional branches before general branches. |
| `switch` expression is not exhaustive | Only guarded cases exist or other input types are missing | Add remaining cases, `default`, or cover the `sealed` type set. |
| `switch` throws `NullPointerException` on null selector | No appropriate `case null` branch | Add `case null` when null handling is required by policy. |
| Java reports syntax error on record pattern/`when` | Using a JDK older than Java 21 or an older source flag | Check `javac -version` and use JDK 21+ with `--release 21`. |
| Assuming guards validate data for the entire application | A guard only applies at the evaluated branch | Enforce important invariants in constructors or a validation layer. |

## 11. Exercises with Suggested Answers

**Exercise 1 — Condition after extraction.** Given `record Rectangle(int width, int height) {}`, write an expression that returns `true` if the input is a `Rectangle` with two positive sides. Hint:

```java
static boolean isValidRectangle(Object value) {
    return value instanceof Rectangle(var width, var height)
        && width > 0
        && height > 0;
}
```

**Exercise 2 — Two guards both match.** Given `Point(2, 3)`, if the first branch checks `x > 0` and the next branch checks `y > 0`, which branch runs? Answer: **the first branch**, provided it appears first and its pattern matches; `switch` selects the first branch whose condition is satisfied.

**Exercise 3 — Null nested component.** Given `Order("A", null, address, 2_000_000L)`, is the guard of `Order(var code, Customer(...), Address(...), var amount) when ...` evaluated? Answer: **no**, because the `Customer(...)` record pattern already failed to match; a shallower branch such as `Order(var code, var customer, var address, var amount)` is needed to handle this case.

**Exercise 4 — Safe condition with strings.** Rewrite a guard that accepts a customer whose name is non-blank, non-null, and at least 18 years old. Hint: `name != null && !name.isBlank() && age >= 18`.

**Exercise 5 — Branch design.** Add a branch for `amount < 0` to report invalid data. Place this branch **before** the general `Order(...)` branch and consider its priority relative to the underage-customer branch. That is a **business rule** decision, distinct from record pattern matching capability.

## 12. Key Takeaways and Official Documentation

- **Deconstruction** checks the type/record and extracts components.
- `instanceof Record(...) && condition` evaluates a combined condition with short-circuiting.
- `case Record(...) when condition -> ...` selects a `switch` branch when both the record matches and the guard is satisfied.
- **Nested record patterns** require each record at the corresponding level to match and be non-null; **`var` on a component** can receive null if the pattern is unconditional.
- **A false guard differs from a failed pattern**: both cause the branch not to be selected, but at two different steps.
- Keep conditional branches before general branches; handle `null` and exhaustiveness intentionally.

Official references:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Patterns, `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
