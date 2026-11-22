# Avoiding Deeply Nested Conditions When Composing Patterns (Java 21+)

## 1. The problem: deeper nesting makes conditions harder to follow

In a Java program, a processing step often has to check several things in sequence: whether the object has the right type, whether nested data exists, whether properties are valid, and whether the business state allows processing. If each check sits inside a new `if` block, the code turns into multiple layers:

~~~java
if (input instanceof Order order) {
    if (order.buyer() != null) {
        if (order.buyer().verified()) {
            // ... other conditions ...
        }
    }
}
~~~

This style is not semantically wrong. The problem is that **the main flow is pushed to the right**, you have to keep track of many surrounding conditions at the processing line, failure paths are harder to spot, and `null` checks are easy to miss when the data structure changes.

**Pattern matching** checks the type and extracts the value in the same expression; **record patterns** also deconstruct the components of a `record`. Combining them properly with **guard clauses** (early returns), `&&`, helper methods, and `switch` can reduce the number of nested blocks while preserving the exact behavior.

The goal is not necessarily **the fewest lines**: good organization should clearly show which conditions are mandatory, which are business rules, and what happens when there is no match.

This lesson uses **Java 21+**, the version in which record patterns and pattern matching in `switch` are officially supported.

## 2. A running example

Suppose the system only approves an order when:

1. The input is actually an `Order`.
2. The `Order` has a buyer `User`.
3. The buyer is verified (`verified == true`).
4. The buyer's name is not `null` and does not consist only of whitespace.
5. The total amount `total >= 100`.
6. The order status is `"PAID"`.

Two simple records:

~~~java
record User(String name, boolean verified) {}
record Order(User buyer, int total, String status) {}
~~~

The input has static type `Object` because it can come from multiple sources. If any condition fails, the approval decision must be `false`. When returning a status label, the convention is: `"APPROVED"` if all conditions are met, `"REJECTED"` if it is an `Order` that does not meet the conditions, and `"INVALID"` if the input is `null` or not an `Order`.

### Deeply nested style

~~~java
static boolean nested(Object input) {
    if (input instanceof Order order) {
        if (order.buyer() != null) {
            if (order.buyer().verified()) {
                if (order.buyer().name() != null) {
                    if (!order.buyer().name().isBlank()) {
                        if (order.total() >= 100) {
                            if ("PAID".equals(order.status())) {
                                return true;
                            }
                        }
                    }
                }
            }
        }
    }
    return false;
}
~~~

This is **an illustrative method**; place it in a class that has the `User` and `Order` declarations above. It solves the problem correctly, but six levels of conditions force the reader to dig deep to reach the result. Calls to `order.buyer()` and `order.buyer().name()` are also repeated.

We can improve this step by step instead of compressing everything into a single cryptic expression.

## 3. Approach 1: record pattern + guard clause

~~~java
static boolean flattened(Object input) {
    if (!(input instanceof Order(
            User(var name, var verified),
            var total, var status))) {
        return false;
    }

    return verified
            && name != null
            && !name.isBlank()
            && total >= 100
            && "PAID".equals(status);
}
~~~

### Why are multiple layers of `if` unnecessary?

- `Order(...)` checks that the input object is an `Order` and deconstructs its three components `buyer`, `total`, and `status`.
- `User(var name, var verified)` is a **nested record pattern**: the `buyer` component must be a non-`null` `User` for the pattern to match, and it then introduces the variables `name` and `verified`.
- If the record pattern does not match, the negated branch `if (!(...))` returns `false` immediately. Every execution path that continues past the `if` has matched the pattern.
- Thanks to **flow scoping**, the pattern variables `name`, `verified`, `total`, and `status` remain in scope in the `return` statement after the guard clause.
- The business rules now form a flat conditional expression that can be read from top to bottom.

You must distinguish between **a nested record value** and **an inner component value**: `buyer == null` causes `User(...)` not to match. However, if `buyer` exists and `name == null`, the pattern `var name` still receives `null`; we must check `name != null` before `name.isBlank()`.

Writing `"PAID".equals(status)` is safe when `status == null`. Writing `status.equals("PAID")` can throw a `NullPointerException` if `status` is not checked first.

Guard clauses are especially useful when the "cannot process" branch is short and the remaining flow is the main logic. You can replace `return` with `throw` when invalid input is an error that should be reported, but doing so **changes behavior**; you should not apply it just to have fewer `if` layers.

## 4. Approach 2: combining a pattern and `&&` in a single expression

If you need a concise boolean result, you can take advantage of short-circuit evaluation:

~~~java
static boolean combined(Object input) {
    return input instanceof Order(
            User(var name, var verified),
            var total, var status)
            && verified
            && name != null
            && !name.isBlank()
            && total >= 100
            && "PAID".equals(status);
}
~~~

Java evaluates `&&` from **left to right**. When the pattern at the beginning does not match, the rest is not evaluated; the pattern variables are never used on the invalid path. When the pattern matches, `verified`, `name`, `total`, and `status` are in scope for the subsequent operands.

Condition order matters:

~~~java
name != null && !name.isBlank()  // Safe
~~~

differs from:

~~~java
!name.isBlank() && name != null  // May throw NullPointerException
~~~

Additional notes:

- You cannot mechanically replace `&&` with `||`. If the left-hand `instanceof` is false, the right-hand side of `||` could run when the pattern variables are not in scope.
- `&&` fits short conditions with a single processing path. If the expression grows too long to inspect each rule easily, use a guard clause or extract a method.
- Do not mix up **data shape checks** with **business rules**: the record pattern confirms the structure; `verified`, the `total` threshold, and `status` are business conditions checked afterward.

## 5. Approach 3: extracting business rules into a clearly named method

Sometimes the main issue is not the number of `if` levels, but a single expression having too many conditions. Let's extract the buyer check:

~~~java
static boolean validBuyer(User buyer) {
    return buyer != null
            && buyer.verified()
            && buyer.name() != null
            && !buyer.name().isBlank();
}

static boolean helper(Object input) {
    if (!(input instanceof Order order)) {
        return false;
    }

    return validBuyer(order.buyer())
            && order.total() >= 100
            && "PAID".equals(order.status());
}
~~~

Here `instanceof Order order` is a **type pattern**: it checks the type and declares the `order` variable. The `validBuyer` method groups conditions that belong to the same responsibility; `helper` clearly expresses the order-level conditions.

This approach works well when the "valid buyer" rule is used in multiple places or needs to be tested independently. Avoid creating a separate method for every tiny comparison if splitting forces the reader to jump through many methods just to understand the main flow.

Quick comparison:

| Approach | Strength | Use when |
| --- | --- | --- |
| Deeply nested `if` | Each level has its own processing site | Branches genuinely perform different actions, not just true/false checks |
| Record pattern + guard clause | Rejects invalid input early, main body has shallow indentation | Further processing is needed after the pattern matches |
| Record pattern + `&&` | Concise boolean condition, short-circuit evaluation | Only a true/false result is needed with a few readable conditions |
| `validBuyer` method + type pattern | Named, reusable business rule | Rules are long, repeated, or need separate testing |

No single approach is always better: the goal is to make the conditions clear **according to their relationships** while preserving semantics.

## 6. Approach 4: using `switch` with `when` for multiple outcomes

When classifying into multiple outcomes, a nested `if/else if` chain also becomes hard to read. A `switch` with patterns and `when` can express each case cleanly:

~~~java
static String classify(Object input) {
    return switch (input) {
        case Order(User(var name, var verified), var total, var status)
                when verified && name != null && !name.isBlank()
                        && total >= 100 && "PAID".equals(status)
                -> "APPROVED";

        case Order(var buyer, var total, var status) -> "REJECTED";
        case null -> "INVALID";
        default -> "INVALID";
    };
}
~~~

In the first branch, the record pattern deconstructs `User` and `Order`; the **`when` guard** is only evaluated if the pattern matches. The pattern variables are in scope in the `when` condition and in the result expression of that branch.

The `case Order(var buyer, var total, var status)` branch is broader: any unapproved `Order` returns `"REJECTED"`, including an order with `buyer == null`. This distinction matters because the first approval branch contains the nested `User(...)` pattern and will **not** match if the buyer is `null`.

`case null` handles a `null` input object itself; `default` handles objects that are not `Order`. Place the specific branch with `when` **before** the broader `Order(...)` branch to avoid dominating specific cases.

`switch` is useful when you need to **classify** into multiple outcomes. If you only need a boolean, a `return` with `&&` is usually simpler. If each condition needs to return a detailed reason, a sequence of guard clauses with clear messages can be easier to maintain than a `switch` with many long guards.

## 7. Complete Java 21 program: verifying equivalent implementations

Save the following complete program to **`PatternDepthDemo.java`**. It compares all five approaches (nested conditions, guard clause, `&&`, helper method, and `switch` classification) across eleven cases, including ineligible cases and `null` values.

~~~java
public class PatternDepthDemo {
    record User(String name, boolean verified) {}
    record Order(User buyer, int total, String status) {}
    record Sample(String label, Object value, String expected) {}

    static boolean nested(Object input) {
        if (input instanceof Order order) {
            if (order.buyer() != null) {
                if (order.buyer().verified()) {
                    if (order.buyer().name() != null) {
                        if (!order.buyer().name().isBlank()) {
                            if (order.total() >= 100) {
                                if ("PAID".equals(order.status())) {
                                    return true;
                                }
                            }
                        }
                    }
                }
            }
        }
        return false;
    }

    static boolean flattened(Object input) {
        if (!(input instanceof Order(
                User(var name, var verified),
                var total, var status))) {
            return false;
        }
        return verified && name != null && !name.isBlank()
                && total >= 100 && "PAID".equals(status);
    }

    static boolean combined(Object input) {
        return input instanceof Order(
                User(var name, var verified),
                var total, var status)
                && verified && name != null && !name.isBlank()
                && total >= 100 && "PAID".equals(status);
    }

    static boolean validBuyer(User buyer) {
        return buyer != null && buyer.verified()
                && buyer.name() != null && !buyer.name().isBlank();
    }

    static boolean helper(Object input) {
        if (!(input instanceof Order order)) {
            return false;
        }
        return validBuyer(order.buyer()) && order.total() >= 100
                && "PAID".equals(order.status());
    }

    static String classify(Object input) {
        return switch (input) {
            case Order(User(var name, var verified), var total, var status)
                    when verified && name != null && !name.isBlank()
                            && total >= 100 && "PAID".equals(status)
                    -> "APPROVED";
            case Order(var buyer, var total, var status) -> "REJECTED";
            case null -> "INVALID";
            default -> "INVALID";
        };
    }

    public static void main(String[] args) {
        Sample[] samples = {
            new Sample("eligible",
                    new Order(new User("Lan", true), 150, "PAID"),
                    "APPROVED"),
            new Sample("boundary-100",
                    new Order(new User("Lan", true), 100, "PAID"),
                    "APPROVED"),
            new Sample("unverified",
                    new Order(new User("Lan", false), 150, "PAID"),
                    "REJECTED"),
            new Sample("low-total",
                    new Order(new User("Lan", true), 99, "PAID"),
                    "REJECTED"),
            new Sample("wrong-status",
                    new Order(new User("Lan", true), 150, "PENDING"),
                    "REJECTED"),
            new Sample("null-status",
                    new Order(new User("Lan", true), 150, null),
                    "REJECTED"),
            new Sample("null-buyer",
                    new Order(null, 150, "PAID"),
                    "REJECTED"),
            new Sample("null-name",
                    new Order(new User(null, true), 150, "PAID"),
                    "REJECTED"),
            new Sample("blank-name",
                    new Order(new User("  ", true), 150, "PAID"),
                    "REJECTED"),
            new Sample("null-input", null, "INVALID"),
            new Sample("other-type", "not-an-order", "INVALID")
        };

        int passed = 0;
        for (Sample s : samples) {
            boolean expectedEligible = s.expected().equals("APPROVED");
            boolean same = nested(s.value()) == expectedEligible
                    && flattened(s.value()) == expectedEligible
                    && combined(s.value()) == expectedEligible
                    && helper(s.value()) == expectedEligible
                    && classify(s.value()).equals(s.expected());
            if (!same) {
                throw new AssertionError("Mismatch at " + s.label());
            }
            passed++;
            System.out.println(s.label() + " -> " + classify(s.value()));
        }
        System.out.println("PASS " + passed + "/" + samples.length);
    }
}
~~~

Run with **JDK 21 or later**:

~~~bash
javac --release 21 PatternDepthDemo.java
java PatternDepthDemo
~~~

Expected output:

~~~text
eligible -> APPROVED
boundary-100 -> APPROVED
unverified -> REJECTED
low-total -> REJECTED
wrong-status -> REJECTED
null-status -> REJECTED
null-buyer -> REJECTED
null-name -> REJECTED
blank-name -> REJECTED
null-input -> INVALID
other-type -> INVALID
PASS 11/11
~~~

The `main` method checks each case against a **predetermined expectation**. It also verifies that all four boolean implementations agree with one another and that `classify` returns the right label. If any implementation differs from the expected result, the program throws an `AssertionError` before printing `PASS 11/11`.

One point to keep in mind: equivalence checks must include **failure cases**, not just valid inputs. For example, moving from `if (order.buyer() != null)` to a nested record pattern is safe because `User(...)` does not match `null`; however, if you drop the `name != null` check, the subsequent `name.isBlank()` call can fail.

## 8. Why condition order, `null`, and variable scope matter

### 8.1. Short-circuit operators keep later steps safe

~~~java
name != null && !name.isBlank()
~~~

is valid because Java only calls `isBlank()` when `name != null`. In long expressions, place conditions **required for safe access** before conditions that use the value.

### 8.2. Pattern variables are flow-scoped

~~~java
if (!(input instanceof Order(User(var name, var verified),
                             var total, var status))) {
    return false;
}

// Valid: the non-matching path has already terminated.
System.out.println(name);
~~~

This is an **illustrative snippet** inside a method that has the appropriate `User` and `Order` types; it is not a standalone program. If you remove `return false` and still use `name` after the `if`, Java no longer guarantees that the pattern variable has been bound.

The right-hand side of `&&` can also use pattern variables because it only runs after the left-hand side matches. Conversely, an expression like the following is **invalid**:

~~~java
// INTENTIONALLY WRONG: on the right-hand side of ||, the pattern on the left may not have matched.
if (input instanceof Order(User(var name, var verified),
                           var total, var status)
        || verified) {
    // ...
}
~~~

This example only illustrates the scoping error and is not part of the compilable file in section 7.

### 8.3. Nested record patterns do not automatically eliminate all `null` values

| Data | Pattern `Order(User(...), ...)` | Reason |
| --- | --- | --- |
| `input == null` | Does not match | `instanceof` with `null` is `false`. |
| `new Order(null, 150, "PAID")` | Does not match | The `buyer` component does not match the `User(...)` record pattern. |
| `new Order(new User(null, true), 150, "PAID")` | Matches the pattern, but is not approved | `var name` can receive `null`; the business condition rejects this value. |
| `new Order(new User("Lan", true), 150, null)` | Matches the pattern, but is not approved | `var status` receives `null`, and `"PAID".equals(status)` returns `false`. |
| Object other than `Order` | Does not match | The outermost type check fails. |

The key takeaway: **patterns define the data structure**, while conditions after the pattern must check rules that the structure does not guarantee, such as a non-blank name or payment status.

## 9. Common mistakes when simplifying conditions

**Mistake 1 — cramming everything onto one ultra-long line.** Fewer `if` layers do not automatically mean better readability. Put conditions on separate lines, name rules clearly, or extract helper methods when needed.

**Mistake 2 — changing behavior while refactoring.** The old code might return `false` for invalid input, whereas the new code throws an exception or treats `null` as valid. Before changing anything, write down the edge cases and test for identical outputs.

**Mistake 3 — dropping `null` checks after using record patterns.** A nested record pattern eliminates `null` at the position where a record must match; it **does not guarantee** that every reference-typed component inside is non-`null`, especially with `var`.

**Mistake 4 — assuming `&&` and `||` are interchangeable.** Short-circuit evaluation and pattern variable scoping behave differently. Always verify which exact path will evaluate the subsequent expression.

**Mistake 5 — using `switch` for a simple boolean condition.** If there is only a single true/false rule, `instanceof` with `&&` or a guard clause is easier to understand. `switch` shines when there are genuinely multiple object types or multiple outcomes to distinguish.

**Mistake 6 — overusing deeply nested record patterns.** Forms like `Envelope(Document(Owner(Address(...))))` can express structure, but become hard to read when combined with many guards. Deconstruct one or two levels at a time, move rules into named methods, and keep the structure clear.

**Mistake 7 — placing a general branch before a specific branch in `switch`.** With a general pattern like `case Order(...)`, subsequent `Order` cases can be dominated; put specific guarded branches before fallback branches.

**Mistake 8 — losing rejection reason details.** A flat boolean expression is great for eligibility checks, but if the product needs to display "unverified" or "unpaid", use steps that return specific reasons. Do not sacrifice business information just to save a few blocks.

## 10. Refactoring workflow and practice

When you encounter a deeply nested `if` chain, follow this sequence:

1. **Write down the input/output contract**: which conditions must hold, which fields can be `null`, and what happens when there is no match?
2. **Identify structural checks**: `instanceof` and chained accessors on records can be combined into a type pattern or record pattern.
3. **Move failure paths out early** with guard clauses when they require no special handling.
4. **Combine independent conditions with `&&`**, preserving `null`-safe ordering and valid pattern variable scope.
5. **Extract long business rules** into clearly named methods instead of forcing all logic into a single expression.
6. **Use `switch` when there are multiple cases/outcomes**, placing specific branches before general ones.
7. **Compare behavior before and after** on valid cases, wrong types, missing data, boundary values, mismatched states, and `null`.

Exercise: try changing `total >= 100` to `total >= 200` while keeping the original 11 test cases. The `eligible` case with total 150 and `boundary-100` with total 100 should no longer pass; update the expectations or add separate tests for the 200 threshold. Then try adding a `"REFUNDED"` status and verify that all four boolean methods and `switch` reject it.

**Remember:** To avoid deeply nested conditions when composing patterns, use pattern matching to check **data shape**, guard clauses for early exits, `&&` to combine rules in a safe order, helper methods to name business logic, and `switch` for distinct outcomes. Most importantly, **reduce reading complexity while preserving exact behavior on both valid and invalid cases**.
