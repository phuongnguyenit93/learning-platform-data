# Unboxing null in Java Arithmetic or Conditional Operators

## 1. The Problem: An Integer Variable Can Hold null, While int Cannot

In Java, primitive types such as `int`, `long`, `double`, `float`, `short`, `byte`, and `boolean` always hold a primitive value when validly used. Meanwhile, the corresponding wrapper classes (`Integer`, `Long`, `Double`, `Float`, `Short`, `Byte`, `Boolean`, `Character`) are **reference types**, so variables can hold `null`.

Java supports automatic conversions:

- **Boxing**: from primitive to wrapper, e.g., `int → Integer`.
- **Unboxing**: from wrapper to primitive, e.g., `Integer → int`.

For a non-null wrapper, unboxing is convenient. For a wrapper that is `null`, converting to a primitive throws a **`NullPointerException` at runtime**.

~~~java
Integer count = null;

// Error occurs at the assignment because Java needs to unbox count to int:
// int total = count; // NullPointerException

Integer safeToStore = count; // Valid: only copies the null reference.
~~~

Some bugs are harder to spot because the program **does not explicitly write** `intValue()`, `longValue()`, or `booleanValue()`. Arithmetic operators, comparisons, and especially the conditional operator `?:` can implicitly require a primitive. This lesson explains exactly where unboxing happens and how to avoid the error without arbitrarily altering the business meaning of `null`.

## 2. Unboxing Is Equivalent to Calling a Primitive Accessor Method

Example:

~~~java
Integer number = Integer.valueOf(12);
int a = number;                  // Auto-unboxing
int b = number.intValue();       // Equivalent in value
System.out.println(a == b);      // true
~~~

If `number` is `null`, calling `number.intValue()` cannot succeed. Similarly:

| Wrapper | Target Primitive | Corresponding Primitive Accessor Method |
|---|---|---|
| `Integer` | `int` | `intValue()` |
| `Long` | `long` | `longValue()` |
| `Double` | `double` | `doubleValue()` |
| `Float` | `float` | `floatValue()` |
| `Short` | `short` | `shortValue()` |
| `Byte` | `byte` | `byteValue()` |
| `Boolean` | `boolean` | `booleanValue()` |
| `Character` | `char` | `charValue()` |

In many cases Java accepts both wrappers and primitives in an expression, yet the compiler inserts unboxing logic wherever the required type is primitive. Thus, **successful compilation does not prove that `null` data will run safely**.

~~~java
Integer quantity = null;

// The statements below compile, but throw NPE at runtime:
// int result = quantity + 1;
// boolean positive = quantity > 0;
// int maximum = Math.max(quantity, 0);
~~~

`NullPointerException` is a runtime issue, not a Java rule forcing the compiler to reject potentially `null` wrapper variables.

## 3. Arithmetic Operations That Easily Trigger Unboxing

When an operand is a wrapper but an operator requires a primitive, Java attempts to unbox. Common cases:

| Expression with `Integer n = null` | Why Does NPE Occur? |
|---|---|
| `int x = n;` | Assigning to `int` requires `n.intValue()` |
| `int x = n + 1;` | Arithmetic `+` requires the numeric value of `n` |
| `int x = n * 2;` | Arithmetic `*` requires unboxing |
| `boolean b = n > 0;` | `>` is a numeric comparison operator needing `int` |
| `boolean b = n == 0;` | Wrapper compared against numeric primitive requires numeric comparison rules |
| `n++;` | Reads primitive value, increments, then boxes/assigns back |
| `n += 2;` | Compound assignment still reads and computes from the old value |
| `int x = Math.max(n, 0);` | Method `Math.max(int, int)` requires `int` parameters |
| `int x = Math.abs(n);` | Integer overload requires `int` |

For example, the increment operator does not make a wrapper mutable. `Integer` remains immutable; `n++` behaves as reading the old value, performing primitive addition, and assigning a new wrapper. If the old value is `null`, the unboxing step fails before any result exists.

~~~java
Integer attempts = Integer.valueOf(2);
attempts++; // Becomes an Integer holding 3, does not mutate the old Integer(2) object.
~~~

Arithmetic operations are evaluated according to Java's evaluation order and typing rules; whichever operand is actually evaluated and requires unboxing will fail if it is `null` at that spot. Never explain this NPE by saying "Java adds null as 0": Java **has no rule treating null as 0**.

### Distinguishing String Concatenation from Arithmetic Addition

The `+` sign is also used for string concatenation:

~~~java
Integer n = null;
System.out.println("n=" + n); // n=null

// int total = n + 1;          // NullPointerException
~~~

In string concatenation, Java converts a `null` reference to the string `"null"`; this is completely different from arithmetic `+`. Do not infer that because printing `n` succeeds, numeric addition with `n` is also safe.

## 4. The Conditional Operator ?: Triggers Unboxing Even When Assigned to Integer

The conditional operator has the syntax:

~~~java
condition ? expressionIfTrue : expressionIfFalse
~~~

Java **evaluates only one of the two result branches** depending on the condition. However, the type of the entire `?:` expression is determined at compile time from its operands and language rules. This creates a surprising case:

~~~java
Integer nullable = null;
boolean chooseFirst = true;

// Compiles, but throws NPE at runtime:
Integer result = chooseFirst ? nullable : 7;
~~~

Here one branch is `Integer` and the other is primitive `int`. Under the rules of a **numeric conditional expression**, the conditional expression itself has primitive `int` type in this case. If the `nullable` branch is selected, Java must unbox `nullable` to produce the `int` result. Because it is `null`, the program throws `NullPointerException`.

**Specifically:** having a target variable of type `Integer` **does not protect** the code above. Java first evaluates the `?:` expression (type `int`), and only then boxes the result to assign to `Integer`. The failure already occurred at the earlier unboxing step.

Similarly:

~~~java
Integer nullable = null;
boolean yes = true;

// ALSO throws NPE even though the target variable is Object:
Object value = yes ? nullable : 7;
~~~

You cannot use an `Object` target variable as a "shield" against unboxing already decided inside the conditional expression.

### 4.1. How to Avoid It: Keep Both Branches as Integer When Allowing null

~~~java
Integer nullable = null;
boolean yes = true;

// Both branches are Integer: the reference result can be null.
Integer result = yes ? nullable : Integer.valueOf(7);
System.out.println(result); // null
~~~

Understand this properly: this code **does not replace null with a default value**. It intentionally preserves `null` in the result if the corresponding branch is chosen. This fits when `null` means "no data" or "not yet determined".

Later, if you want a primitive, you still must check:

~~~java
int safeValue = result == null ? 0 : result;
~~~

This solution is only appropriate if the contract says `null` may be replaced by 0. If missing data is an error, report the error rather than silently defaulting.

### 4.2. Comparison Table of ?: Branches

Assume `Integer missing = null; boolean chooseFirst = true;`.

| Expression | Key Type / Effect | When the First Branch Is Selected |
|---|---|---|
| `chooseFirst ? missing : 7` | One `Integer` branch, one `int` branch → unboxed to become numeric | **NPE** |
| `chooseFirst ? missing : Integer.valueOf(7)` | Both branches `Integer` | Returns `null` reference, no NPE yet |
| `chooseFirst ? missing : "fallback"` | Two reference branches, not a numeric conditional | Returns `null`, no NPE yet |
| `chooseFirst ? null : Integer.valueOf(7)` | `null` branch and `Integer` reference | Can safely return `null` when receiver accepts a reference |
| `chooseFirst ? null : 7` assigned to `int` | `null` branch chosen, assignment requires unboxing nullable result | **NPE** |
| `chooseFirst ? missing : 7` assigned to `Object` | Numeric conditional still requires `int` before boxing | **NPE** |

Key distinction: distinguish between **an NPE occurring while evaluating the expression** and **an NPE occurring afterward when forcing a reference result into a primitive**. They may have different stack traces, yet both stem from needing a primitive when the reference value is `null`.

### 4.3. When Condition Is false, the null Branch Does Not Necessarily Fail

~~~java
Integer missing = null;
boolean chooseFirst = false;

int value = chooseFirst ? missing : 7; // 7, no NPE
~~~

Because the condition is false, the `missing` branch is not evaluated. Nevertheless, this expression is **unsafe across all inputs**: flipping the condition to true triggers NPE. This is why production bugs sometimes appear only along a rare branch.

## 5. Null Boolean Right in the Condition

It is not just the result branches; **the condition of `if`, `while`, `for`, and `?:` requires a primitive boolean**. When passing a `Boolean`, Java unboxes it:

~~~java
Boolean approved = null;

// The following expressions compile but can throw NullPointerException:
// if (approved) { ... }
// String label = approved ? "yes" : "no";
// while (approved) { ... }
~~~

The logical operators `&&` and `||` also require boolean values on operands that are actually evaluated:

~~~java
Boolean enabled = null;

// boolean wrong = enabled && true; // NPE
boolean safe = enabled != null && enabled; // false
~~~

In the safe expression, `&&` evaluates left to right and **short-circuits**: when `enabled != null` is false, Java skips evaluating `enabled` on the right and thus never unboxes it.

An even clearer idiom when treating `null` as false:

~~~java
Boolean enabled = null;
boolean enabledOnlyIfTrue = Boolean.TRUE.equals(enabled); // false
~~~

`Boolean.TRUE.equals(enabled)` does not invoke a method on a potentially null object; the receiver is the non-null constant `Boolean.TRUE`. It returns false for both `Boolean.FALSE` and `null`.

**Be careful with three-state logic:** if `null` means "unanswered", distinct from false ("declined"), do not collapse both into false without a business requirement. You can check explicitly:

~~~java
if (enabled == null) {
    // Missing data or undetermined state.
} else if (enabled) {
    // true
} else {
    // false
}
~~~

Here the `enabled` condition is only evaluated after the wrapper is known to be non-null.

### Difference Between && and &

`&&` short-circuits; `&` on booleans always evaluates both sides:

~~~java
Boolean enabled = null;

boolean safe = enabled != null && enabled; // false
// boolean unsafe = enabled != null & enabled; // NPE: right-hand side still runs.
~~~

The same rule holds for `||` (short-circuit) and `|` (non-short-circuit) when used on booleans. This is a common bug caused by mistyping a single logical operator character.

## 6. Comparing with ==, equals, and < When Wrappers Are Involved

Not every `==` operator involving a wrapper forces unboxing. The static types of **both operands** determine reference comparison vs. numeric comparison.

~~~java
Integer a = null;
Integer b = Integer.valueOf(7);

System.out.println(a == b);      // false: two Integer references
System.out.println(a == null);   // true: reference check
System.out.println(java.util.Objects.equals(a, b)); // false

// boolean numerical = a == 7; // NPE: Integer compared with primitive int
// boolean less = a < 7;       // NPE: < requires numeric value
~~~

Using `==` on two `Integer`s performs **reference identity comparison**, not numeric value comparison. This can cause another kind of bug even when neither is null:

~~~java
Integer x = new Integer(1000); // Example illustrating legacy API; constructor is deprecated.
Integer y = new Integer(1000);

// x == y can be false even with equal values; do not use == to compare wrapper values.
~~~

In new code, never construct wrappers via constructors. Use `Integer.valueOf(...)` or autoboxing and **`Objects.equals(x, y)`** for nullable value comparisons, or after a null check use `x.intValue() == y.intValue()` if primitives are truly needed.

Value comparison when null can have its own meaning. For example:

~~~java
Integer score = null;
boolean isZero = java.util.Objects.equals(score, 0); // false, no NPE
~~~

`Objects.equals` is null-safe but **does not** treat null as 0; it considers one null side and one non-null side unequal.

Meanwhile, `score.equals(0)` still throws NPE if `score == null`, because the method receiver is null:

~~~java
// score.equals(0); // NullPointerException
boolean zero = Integer.valueOf(0).equals(score); // false
~~~

When comparing `Integer` with `Long`, `Objects.equals` checks the object type as well, so `Integer.valueOf(5)` does not equal `Long.valueOf(5L)` under `equals`. If business logic wants to compare values across numeric types, convert **explicitly with null checks**; never assume all numeric wrappers are equivalent just because they share the same numeric value.

## 7. Complete Java 17+ Program: Reproducing NPE and Safe Alternatives

Create `NullUnboxingDemo.java`. The program catches `NullPointerException` around each example so the entire program runs to completion while keeping output deterministic and easy to inspect:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullUnboxingDemo {
    private static void check(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException ex) {
            System.out.println(name + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        Integer missing = null;
        Boolean unknown = null;
        boolean chooseFirst = true;

        check("arithmetic", () -> {
            int value = missing + 1;
            System.out.println(value);
        });

        check("mixed-ternary", () -> {
            Integer value = chooseFirst ? missing : 7;
            System.out.println(value);
        });

        Integer kept = chooseFirst
                ? missing
                : Integer.valueOf(7);
        System.out.println("both-boxed: " + kept);

        check("Object-target", () -> {
            Object result = chooseFirst ? missing : 7;
            System.out.println(result);
        });

        Object reference = chooseFirst ? missing : "fallback";
        System.out.println("reference-ternary: " + reference);

        check("condition", () -> {
            String answer = unknown ? "yes" : "no";
            System.out.println(answer);
        });

        check("compare-with-int", () -> {
            boolean equalsZero = missing == 0;
            System.out.println(equalsZero);
        });

        System.out.println("Objects.equals: "
                + Objects.equals(missing, 0));
        System.out.println("safe-Boolean: "
                + Boolean.TRUE.equals(unknown));

        int fallback = missing == null ? 0 : missing;
        System.out.println("checked-fallback: " + fallback);

        int optionalFallback = Optional.ofNullable(missing).orElse(0);
        System.out.println("optional-fallback: " + optionalFallback);
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac NullUnboxingDemo.java
java NullUnboxingDemo
~~~

Stdout output:

~~~text
arithmetic: NullPointerException
mixed-ternary: NullPointerException
both-boxed: null
Object-target: NullPointerException
reference-ternary: null
condition: NullPointerException
compare-with-int: NullPointerException
Objects.equals: false
safe-Boolean: false
checked-fallback: 0
optional-fallback: 0
~~~

Reading the output group by group:

- `arithmetic`: Java needs an `int` to perform addition.
- `mixed-ternary` and `Object-target`: the conditional expression has `Integer`/`int` branches, so it unboxes before returning, regardless of whether the target variable is `Integer` or `Object`.
- `both-boxed`: both branches are `Integer`, so the result can be a null reference.
- `reference-ternary`: `Integer` and `String` branches form a reference conditional expression; the `missing` branch can return null without unboxing.
- `condition`: a null `Boolean` is unboxed when selecting the branch.
- `compare-with-int`: comparing a wrapper against a primitive requires numeric value processing.
- `Objects.equals` and `Boolean.TRUE.equals`: avoid unboxing nullable objects; results are false.
- `checked-fallback` and `optional-fallback`: intentional default of 0, no NPE.

**Do not depend on the exact wording of NPE detail messages** in tests: "helpful NullPointerExceptions" in different JDK builds may generate varying messages depending on compilation options. The program prints fixed exception labels to clarify the phenomenon rather than `ex.getMessage()`.

## 8. Fix Patterns: Choose Based on the Meaning of null

Unboxing bugs should not be "fixed" by blindly turning every null into 0. Decide the business meaning of null first.

### 8.1. Null Means a Default Value

~~~java
Integer quantity = null;
int value = quantity != null ? quantity : 0;
~~~

The `?:` operator in this example still has primitive `int` type, but **it only selects the nullable branch when `quantity` is already known to be non-null**. Unboxing is therefore safe.

It can be written more concisely:

~~~java
int value = quantity == null ? 0 : quantity;
~~~

Or when input is modeled as nullable:

~~~java
int value = java.util.Optional.ofNullable(quantity).orElse(0);
~~~

`Optional.ofNullable` accepts null and produces an empty `Optional`; `orElse(0)` returns a non-null `Integer`, which Java then safely unboxes to `int`. This pattern is unnecessary for every computation path; a direct null check is usually clearer and lighter.

### 8.2. Null Is Invalid Data and Must Be Rejected

~~~java
import java.util.Objects;

Integer amount = null;

// When called and amount is null, fails early with an intentional message:
int required = Objects.requireNonNull(amount, "amount must not be null");
~~~

`requireNonNull` throws `NullPointerException` with the specified message when null. If the application expects a different exception type, check and throw `IllegalArgumentException` or a domain-specific exception at the data boundary.

The important thing is **detecting null early**, rather than letting an exception surface deep inside an addition or a complex `?:` expression where the origin is hard to trace.

### 8.3. Null Is a Meaningful State and Must Be Preserved

~~~java
Integer measured = null;

Integer selected = measured == null
        ? null
        : Integer.valueOf(measured + 1);

// selected is null; not forced to 0.
~~~

If an API returns a nullable `Integer`, preserve its ability to return null instead of forcing it to `int`. When a final result can only be a number or absent, an `OptionalInt` can also express absence explicitly:

~~~java
java.util.OptionalInt maybeValue = measured == null
        ? java.util.OptionalInt.empty()
        : java.util.OptionalInt.of(measured);
~~~

`OptionalInt` does not hold null internally, yet callers must handle the absent state via `isPresent()`, `orElse(...)`, `orElseThrow()`, etc. Do not treat `OptionalInt.empty()` as 0 unless business rules state so.

### 8.4. Three-State Boolean

~~~java
Boolean answer = null;

if (answer == null) {
    System.out.println("unknown");
} else if (answer) {
    System.out.println("yes");
} else {
    System.out.println("no");
}
~~~

Only after checking for non-null is `answer` unboxed in `else if`. If business rules allow treating null as false, `Boolean.TRUE.equals(answer)` is a concise idiom. If business rules distinguish unanswered from declined, use three branches as shown.

## 9. Watch Data Boundaries: List, Map, Stream, and Optional

Null unboxing does not only appear in single-line expressions. It also frequently occurs when data is fed into APIs expecting primitives.

### 9.1. List<Integer> and Stream

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, null, 3);

// NullPointerException when the terminal operation actually reaches the null element:
// int sum = values.stream().mapToInt(Integer::intValue).sum();

int safeSum = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
~~~

`mapToInt(Integer::intValue)` requires unboxing each wrapper and executes when the pipeline runs (because Stream intermediate operations are lazy). Explicitly decide whether null means "skip", "treat as 0", or "input error"; `filter(Objects::nonNull)` is only appropriate when skipping null elements is valid.

Note that `List.of(1, null, 3)` itself forbids nulls and throws `NullPointerException` upon list creation; the example uses `Arrays.asList` to depict a collection that actually holds null.

### 9.2. Map.get or getOrDefault

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> counts = new HashMap<>();
counts.put("A", null);

// int value = counts.get("A"); // NPE due to unboxing null.
~~~

`Map.getOrDefault(key, defaultValue)` **is not always a null-substitution safeguard**: if the key exists and is mapped to null, it can still return null (with `HashMap`). For example:

~~~java
// Map<String, Integer> counts as above.
// int value = counts.getOrDefault("A", 0); // can still throw NPE.
~~~

If the application permits `null` as a meaningful value, handle it explicitly:

~~~java
Integer count = counts.get("A");
int value = count == null ? 0 : count;
~~~

If you need to distinguish "missing key" from "key mapped to null", use `containsKey` alongside `get` or redesign the data structure accordingly.

### 9.3. Optional Does Not Automatically Guarantee Safe Unboxing

~~~java
import java.util.Optional;

Optional<Integer> maybe = Optional.empty();

// int value = maybe.orElse(null); // NPE if attempting to assign null to int.
int safeValue = maybe.orElse(0);
~~~

`Optional<Integer>` models the possible absence of a wrapper. However, `orElse(null)` can still return null; if unboxed afterward, the error still occurs. Choose `OptionalInt` when an API needs to directly represent "an `int` value or its absence" without wrappers at every step.

## 10. Complex Conditional Cases and Evaluation Order

Multi-branch expressions easily hide a deeply buried unboxing step:

~~~java
Integer discount = null;
boolean vip = true;
boolean promotion = false;

// Example requiring type and null checks before writing complex code:
// int applied = vip ? discount : (promotion ? 5 : 0);
~~~

If `vip` is true, the `discount` branch is chosen; because the numeric expression requires a primitive, null gets unboxed. Even if the other branch does not run, that does not make the expression safe.

Instead, make the policy explicit:

~~~java
Integer discount = null;
boolean vip = true;
boolean promotion = false;

int applied;
if (vip) {
    if (discount == null) {
        throw new IllegalStateException("VIP discount is missing");
    }
    applied = discount;
} else {
    applied = promotion ? 5 : 0;
}
~~~

When business conditions are complex, an `if/else` block with explicit null checks is usually easier to understand and review than nested `?:` expressions, especially when branches mix wrapper and primitive types.

### Short-Circuit Operators Help Avoid Unnecessary Unboxing

~~~java
Integer age = null;

boolean adult = age != null && age >= 18; // false, no NPE
boolean missingOrAdult = age == null || age >= 18; // true, no NPE
~~~

In the first example, the right-hand side `age >= 18` only runs when `age != null`. In the second, the right-hand side only runs when `age == null` is false. This guard pattern is safe thanks to short-circuit evaluation; mistyping `&&` as `&` or `||` as `|` removes that protection.

## 11. Code Review Rules to Detect Null Unboxing

When reviewing Java code with nullable wrappers, trace the **static type** of every operand, not just the declared type of the destination variable.

A short checklist:

1. **Nullable sources:** entity/DTO fields, `Map.get` results, missing parsed input, nullable database columns, methods returning nullable wrappers.
2. **Primitive targets:** assigning `Integer → int`, passing into `method(int)`, returning from a method declared `int`.
3. **Operators requiring primitives:** `+`, `-`, `*`, `/`, comparisons `<`/`>`, increment/decrement operators, and compound assignments.
4. **Logical conditions:** `if(Boolean)`, `while(Boolean)`, `Boolean && ...`, `Boolean ? ... : ...`.
5. **The `?:` operator:** when mixing numeric wrappers and numeric primitives, check the type of **the entire expression**. Assigning the result to `Integer`/`Object` does not necessarily prevent unboxing.
6. **Conversion APIs:** `Integer::intValue`, `mapToInt`, `Collectors.summingInt`, `Math.max`, and overloads requiring primitives.
7. **Test both branches:** true/false conditions and null/non-null values; rare bugs often hide on branches skipped by simple tests.

### Testing with Minimal Cases

To verify a risky expression, write tests covering all meaningful combinations:

| Condition | Wrapper Value | What to Verify |
|---|---|---|
| true | non-null | First branch result is correct |
| true | null | Is NPE thrown or is null preserved per contract? |
| false | non-null | Second branch and result type |
| false | null | Is the null branch genuinely skipped? |
| `Boolean` null as condition | any | Does NPE occur in the condition before branch selection? |

Do not test only the "happy path" with `Integer.valueOf(5)`. Actually run tests with `null` and assert the expected exception type or default result.

## 12. Common Mistakes and Replacements

| Buggy Pattern / Misconception | Issue | How to Handle |
|---|---|---|
| `Integer n = flag ? nullable : 0;` cannot NPE because result is Integer | `Integer`/`int` branches can unbox `nullable` | Check null or use two wrapper branches if preserving null |
| `Object o = flag ? nullable : 0;` safely preserves null | Expression type is decided before assigning to Object | Determine `?:` type, fix branch types |
| `Boolean b = null; if (b) ...` | Condition requires `boolean` | `Boolean.TRUE.equals(b)` or three-state check |
| `n == 0` is safe if n is Integer | Comparing against primitive unboxes null | `Objects.equals(n, 0)` or null check |
| `n.equals(0)` is null-safe | Calling method on null causes NPE | `Objects.equals(n, 0)` |
| `n++` cannot NPE because it only increments a wrapper | Incrementing requires unboxing old value | Initialize value, check null |
| `mapToInt(Integer::intValue)` skips null automatically | Pipeline unboxes each element when consumed | Filter or fail explicitly per contract |
| `map.getOrDefault(k, 0)` is always non-null | A map key mapped to null can still return null | Read into wrapper, check null |
| `Optional.ofNullable(n).orElse(null)` is safe | Can return null and then get unboxed | Choose non-null default or keep Optional |
| Replace every null with 0 | Loses meaning of "missing" or "undefined" | Establish explicit null handling policy |
| Use `==` to compare values of two Integers | Two wrappers may compare references | `Objects.equals` for null-safe value comparison |
| Test only with condition false | Fails to exercise the path where null branch is chosen | Test true/false with both null and non-null |

## 13. Self-Check Exercises

**Question 1.** What happens?

~~~java
Integer n = null;
int r = n + 10;
~~~

**Answer:** `NullPointerException` when Java unboxes `n` to perform `int` addition.

**Question 2.** Why can this code throw NPE even though the target variable is `Integer`?

~~~java
Integer n = null;
boolean flag = true;
Integer r = flag ? n : 5;
~~~

**Answer:** the two branches have types `Integer` and `int`; the numeric conditional expression has type `int`, so branch `n` is unboxed when chosen. With `flag` true and `n` null, NPE occurs before boxing the result back to `Integer`.

**Question 3.** What if `5` is changed to `Integer.valueOf(5)` in Question 2?

**Answer:** Both branches have type `Integer`, so the result can be a `null` reference and assigning to `Integer` does not throw NPE. NPE can still occur if the result is unboxed later.

**Question 4.** What does `Boolean approved = null; boolean ok = approved != null && approved;` return?

**Answer:** `false`, no NPE. The right-hand side does not execute because `approved != null` is false.

**Question 5.** Given `Integer a = null; Integer b = 2;`, how do `a == b` and `a == 2` differ?

**Answer:** `a == b` compares wrapper references, returns false, and requires no unboxing. `a == 2` compares against primitive `int`, unboxes `a`, and throws NPE. When comparing values, use `Objects.equals(a, b)` instead of wrapper reference identity.

**Question 6.** Why does `String s = "n=" + nullableInteger;` run when `nullableInteger` is null?

**Answer:** The `+` operator with a string performs string concatenation from references, producing `"n=null"`; this is not arithmetic addition requiring unboxing.

**Question 7.** A DTO contains `Integer quantity` which can be null. An API requires an `int` result. What should you do?

**Answer:** Determine what null means: default 0, invalid data, or missing information that must propagate to the caller. Then check for null before unboxing or change the data model/return type. Do not default to 0 unless business logic specifies it.

**Question 8.** Does `Optional<Integer>` guarantee that `int x = optional.orElse(null);` runs safely?

**Answer:** No. If the `Optional` is empty, `orElse(null)` returns null and assigning to `int` attempts to unbox null, causing NPE.

---

**Remember:** `null` is valid for wrappers but cannot become a primitive through unboxing. Arithmetic operators, comparisons, `Boolean` conditions, APIs accepting primitives, and `?:` expressions mixing wrappers and primitives can all trigger hidden unboxing. **Check expression types before assignment**, validate null at boundaries, and choose a business-appropriate null handling policy instead of assuming null equals 0.
