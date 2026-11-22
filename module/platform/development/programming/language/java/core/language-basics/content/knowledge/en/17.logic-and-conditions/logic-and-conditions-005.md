# Distinguishing `&&` from `&` and `||` from `|` — Java 17+

## 1. Key Concept to Master

In Java, `&&` and `||` are **short-circuit logical operators**. `&` and `|` can also operate on `boolean`, but they are **non-short-circuiting**: the right-hand side is still evaluated even when the logical result is already determined. When used on integer types, `&` and `|` instead have **bitwise** meaning, not conditional logic.

~~~java
boolean a = false;
boolean b = true;

System.out.println(a && b); // false
System.out.println(a & b);  // false
System.out.println(b || a); // true
System.out.println(b | a);  // true
~~~

The four results above are **identical in logical value**. The critical difference lies not in the truth table, but in **whether the right-hand side is evaluated**. The right-hand side can call a method, mutate state, consume resources, or throw an exception.

**Lesson goal:** know how to choose the right operator, explain execution order, guard `null`/array accesses, recognize side effects, understand bitwise operations on integer types, and avoid bugs from parentheses/precedence.

## 2. Quick Comparison Table

| Operator | Typical valid operands | When is the right side skipped? | Meaning |
|---|---|---|---|
| `&&` | `boolean` / `Boolean` via unboxing | When left side is `false` | Short-circuit AND |
| `&` | `boolean` or integers | **Never** skipped via short-circuiting | Non-short-circuit boolean AND or bitwise AND |
| `||` | `boolean` / `Boolean` via unboxing | When left side is `true` | Short-circuit OR |
| `|` | `boolean` or integers | **Never** skipped via short-circuiting | Non-short-circuit boolean OR or bitwise OR |

**In this lesson, "non-short-circuiting" means** when the operation is reached in normal execution flow, Java evaluates both operands in left-to-right order. If evaluating the left side throws an exception, execution still stops; no rule forces the right side to run after an exception.

`&&` and `||` **do not apply to two integer operands**:

~~~java
int x = 6, y = 3;
int bits = x & y; // Valid
// int invalid = x && y; // Compile error: operands are not boolean
~~~

Java does not treat integer 0 as `false` and non-zero integers as `true` as in some other languages.

## 3. Short-Circuit Rule of `&&`

`left && right` works as follows:

1. Evaluate `left`.
2. If `left` is `false`, **return `false` immediately**; do not evaluate `right`.
3. If `left` is `true`, evaluate `right` and take that boolean result.

Example:

~~~java
int denominator = 0;
boolean safe = (denominator != 0) && (10 / denominator > 2);

System.out.println(safe); // false
~~~

Because `denominator != 0` is false, Java **does not execute** `10 / denominator`; there is no `ArithmeticException`.

### Changing to `&` behaves completely differently

~~~java
int denominator = 0;
// boolean unsafe = (denominator != 0) & (10 / denominator > 2);
// If run: ArithmeticException (integer division by zero).
~~~

With `&` on booleans, the right side **must be evaluated** once the left side completes normally, even when the left side is false. Do not treat `&` as shorthand for `&&`.

## 4. Short-Circuit Rule of `||`

`left || right` works as follows:

1. Evaluate `left`.
2. If `left` is `true`, **return `true` immediately**; do not evaluate `right`.
3. If `left` is `false`, evaluate `right` and take that boolean result.

~~~java
int denominator = 0;
boolean invalidOrLarge = (denominator == 0)
        || (10 / denominator > 2);

System.out.println(invalidOrLarge); // true
~~~

The left side is true, so Java **skips the division**.

If changed to `|`:

~~~java
// boolean unsafe = (denominator == 0) | (10 / denominator > 2);
// If run: ArithmeticException.
~~~

**Memory tip:** `&&` stops on false; `||` stops on true. Boolean `&` and `|` do not have this right-side skipping mechanism.

~~~mermaid
flowchart TD
    A["Evaluate left side of &&"] --> B{"Is left true?"}
    B -- "No" --> C["Return false; skip right"]
    B -- "Yes" --> D["Evaluate right"]
    E["Evaluate left side of ||"] --> F{"Is left true?"}
    F -- "Yes" --> G["Return true; skip right"]
    F -- "No" --> H["Evaluate right"]
    I["& or | on boolean"] --> J["Evaluate left then right"]
    J --> K["Compute AND/OR from both results"]
~~~

## 5. `&` and `|` on Booleans Share the Same Truth Table

If **both operands are pure booleans**, with no side effects and no thrown errors, `&&` and `&` produce the same value; likewise for `||` and `|`.

| `a` | `b` | `a && b` | `a & b` | `a || b` | `a | b` |
|---|---|---|---|---|---|
| false | false | false | false | false | false |
| false | true | false | false | true | true |
| true | false | false | false | true | true |
| true | true | true | true | true | true |

Why shouldn't you swap them carelessly?

~~~java
boolean result = false && doWork(); // doWork() is NOT called
boolean other = false & doWork();   // doWork() IS called
~~~

In real code, `doWork()` might update a counter, call an external API, or throw an exception. The two statements do not behave identically, even though both return false when the method runs normally.

**Default to short-circuiting** when writing ordinary conditions. Choose boolean `&`/`|` only when you **deliberately require both sides to be evaluated** and have accounted for side effects, cost, and exceptions.

## 6. Evaluation Order and Side Effects

Java evaluates the left side first; when the right side must be evaluated, it happens **after the left side**. You can observe this with a method that prints its label:

~~~java
static boolean trace(String label, boolean answer) {
    System.out.println("called " + label);
    return answer;
}
~~~

Illustration:

~~~java
boolean a = false && trace("skip-and", true);
boolean b = false & trace("eager-and", true);
boolean c = true || trace("skip-or", false);
boolean d = true | trace("eager-or", false);
~~~

Only two lines are printed:

~~~text
called eager-and
called eager-or
~~~

If the left side also has a side effect:

~~~java
boolean result = trace("left", true) & trace("right", false);
~~~

the order is:

~~~text
called left
called right
~~~

and then the boolean result of `&` is false. **Both sides are never evaluated in parallel simply because `&` or `|` is used**.

## 7. Guards for Nullable References

When writing `text != null && !text.isBlank()`, Java calls `isBlank()` only if `text` is non-null. The symmetric condition `text == null || text.isBlank()` is also safe: if the value is null, the right side of `||` does not run.

~~~java
String text = null;
boolean hasText = text != null && !text.isBlank();  // false
boolean missing = text == null || text.isBlank();    // true
~~~

Replacing `&&` with `&`, or `||` with `|`, still executes the call on null and can throw `NullPointerException`. With `Boolean enabled = null`, unboxing carries the same risk; `enabled != null && enabled` or `Boolean.TRUE.equals(enabled)` clearly expresses the policy for allowing true. The lesson **Using Short-Circuiting for Null Checks and Array Bounds** covers multi-level guards; here the focus is the **evaluation difference between the two operator pairs**.

## 8. Arrays: Guard Order Changes Behavior

A valid index must be non-negative and less than the array length; for nullable arrays, check the reference first:

~~~java
static boolean positiveAt(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length
            && array[index] > 0;
}
~~~

Writing `&` instead of `&&` lets Java evaluate `array.length` even when the array is null, or `array[index]` even when the index is out of bounds, throwing an exception. This example suffices to compare the operators; checking nullable elements, two-dimensional arrays, boundary cases, and choosing guard clauses are practiced in the dedicated lesson on **null and array bounds**.

## 9. When Do You Truly Want Both Sides Evaluated?

Sometimes two **independent** checks must both run even if the first check fails—for example, collecting all input validation errors:

~~~java
boolean hasName = validateName();
boolean hasEmail = validateEmail();
boolean allValid = hasName && hasEmail;
~~~

Both methods are called **once each**, and then `&&` simply combines the two precomputed boolean values. This approach usually **shows intent more clearly** than:

~~~java
boolean allValid = validateName() & validateEmail();
~~~

The second line may be valid if the API genuinely wants **both methods to run**, but it is less clear to readers accustomed to `&` as a bitwise operator. When running everything is important, splitting method calls into separate statements makes maintenance, testing, and logging easier.

**Caution:** If `validateName()` throws an exception, Java does not proceed to call `validateEmail()` in **either** pattern above without appropriate exception handling. "Non-short-circuiting" does not mean "always call both methods regardless of errors".

## 10. `&` and `|` Are Also Bitwise Operators on Integers

Unlike `&&`/`||`, the `&`/`|` operators also have bitwise meaning for `byte`, `short`, `char`, `int`, and `long` (after numeric promotion).

Example:

~~~java
int a = 0b1100; // 12
int b = 0b1010; // 10

System.out.println(a & b); // 8: 1000
System.out.println(a | b); // 14: 1110
~~~

Representation:

~~~text
  1100 (12)
& 1010 (10)
= 1000 (8)

  1100 (12)
| 1010 (10)
= 1110 (14)
~~~

- Bitwise AND `&`: the resulting bit is 1 **when both bits at the same position are 1**.
- Bitwise OR `|`: the resulting bit is 1 **when at least one bit at that position is 1**.

A practical application is checking a flag:

~~~java
int flags = 0b1100;
boolean hasRead = (flags & 0b0100) != 0;
System.out.println(hasRead); // true
~~~

**Parentheses are necessary to express intent:** `(flags & 0b0100) != 0` performs the bitwise AND first and then compares against 0. Using `&&` directly between two integers causes a compile error.

## 11. Operator Precedence and Parentheses

Operators have **different precedence levels**. For the groups being studied, from highest to lowest:

| Operator group | Examples | Notes |
|---|---|---|
| Equality comparison | `==`, `!=` | Higher precedence than bitwise AND/OR |
| Bitwise/boolean AND | `&` | Higher precedence than `^` and `|` |
| Bitwise/boolean XOR | `^` | Between `&` and `|` |
| Bitwise/boolean OR | `|` | Higher precedence than `&&` |
| Short-circuit AND | `&&` | Higher precedence than `||` |
| Short-circuit OR | `||` | Lower than `&&` |

Example:

~~~java
boolean a = true;
boolean b = false;
boolean c = false;

System.out.println(a || b && c);   // true: a || (b && c)
System.out.println((a || b) && c); // false
~~~

**Place parentheses according to business requirements** when mixing `&&` and `||`, or `&`/`|` with numeric comparisons. Parentheses do not turn `&` into a short-circuit operator and do not eliminate side effects.

Note the `!` (negation) operator applied to booleans: `!(a && b)` is logically equivalent to `!a || !b`. However, when operands have side effects, **evaluation order and call counts must be preserved** when refactoring.

## 12. Compound Assignments `&=` and `|=` Are Also Non-Short-Circuiting

On `boolean` variables:

~~~java
boolean good = false;
good &= expensiveCheck(); // expensiveCheck() still runs

boolean ready = true;
ready |= expensiveCheck(); // expensiveCheck() still runs
~~~

`&=`/`|=` are **compound assignments** corresponding to `&`/`|`, not `&&`/`||`.

Java **does not have** `&&=` or `||=` operators.

If the goal is to keep short-circuiting while updating the variable:

~~~java
good = good && expensiveCheck();
ready = ready || expensiveCheck();
~~~

However, this is a **semantic change** if the original code needed `expensiveCheck()` to run even when the value of `good`/`ready` already determined the result. Refactor only after confirming that.

## 13. Separating State Updates from Guards

Short-circuit operators do not fix bugs when a guard **mutates the very index being checked**. With `index = 1` and `values.length = 2`, `index++ < values.length` evaluates to true and then increments `index` to 2, causing the subsequent `values[index]` read to go out of bounds.

~~~java
int[] values = {10, 20};
int index = 1;
boolean valid = index >= 0 && index < values.length;
if (valid) {
    int current = values[index];
    index++; // Separate the mutation from the guard condition.
}
~~~

Guards also do not provide atomicity against modifications from other threads; when sharing data, use proper synchronization or snapshotting. The comparison focus here is **evaluation order and count**, not just the truth table.

## 14. Complete, Standalone Java 17 Program

Save the file as **`ShortCircuitVsEagerDemo.java`**:

~~~java
public final class ShortCircuitVsEagerDemo {
    private ShortCircuitVsEagerDemo() {}

    static boolean trace(String label, boolean answer) {
        System.out.println("called " + label);
        return answer;
    }

    static boolean positiveAt(int[] array, int index) {
        return array != null
                && index >= 0
                && index < array.length
                && array[index] > 0;
    }

    public static void main(String[] args) {
        boolean leftFalse = false;
        boolean rightTrue = true;

        System.out.println("AND short=" + (leftFalse && rightTrue));
        System.out.println("AND eager=" + (leftFalse & rightTrue));
        System.out.println("OR short=" + (rightTrue || leftFalse));
        System.out.println("OR eager=" + (rightTrue | leftFalse));

        boolean skipAnd = false && trace("skip-and", true);
        System.out.println("skip &&=" + skipAnd);

        boolean eagerAnd = false & trace("eager-and", true);
        System.out.println("eager &=" + eagerAnd);

        boolean skipOr = true || trace("skip-or", false);
        System.out.println("skip ||=" + skipOr);

        boolean eagerOr = true | trace("eager-or", false);
        System.out.println("eager |=" + eagerOr);

        boolean both = trace("left", true)
                & trace("right", false);
        System.out.println("both evaluated=" + both);

        int zero = 0;
        boolean safeAnd = zero != 0 && 10 / zero > 2;
        boolean safeOr = zero == 0 || 10 / zero > 2;
        System.out.println("safe division &&=" + safeAnd);
        System.out.println("safe division ||=" + safeOr);

        try {
            boolean invalid = zero != 0 & 10 / zero > 2;
            System.out.println(invalid);
        } catch (ArithmeticException ex) {
            System.out.println("eager division=ArithmeticException");
        }

        String text = null;
        System.out.println("safe null &&="
                + (text != null && !text.isBlank()));
        System.out.println("safe null ||="
                + (text == null || text.isBlank()));
        try {
            boolean invalid = text != null & !text.isBlank();
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("eager null=NullPointerException");
        }

        Boolean boxed = null;
        System.out.println("nullable Boolean="
                + (boxed != null && boxed));
        System.out.println("boxed skipped &&=" + (false && boxed));
        System.out.println("boxed skipped ||=" + (true || boxed));
        try {
            boolean invalid = false & boxed;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("eager unboxing=NullPointerException");
        }

        int[] scores = {7, 0};
        System.out.println("array[0]=" + positiveAt(scores, 0));
        System.out.println("array end=" + positiveAt(scores, 2));
        System.out.println("array null=" + positiveAt(null, 0));

        try {
            boolean invalid = scores != null & scores[99] > 0;
            System.out.println(invalid);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("eager array=ArrayIndexOutOfBoundsException");
        }

        int first = 0b1100;
        int second = 0b1010;
        System.out.println("bitwise &=" + (first & second));
        System.out.println("bitwise |=" + (first | second));
        System.out.println("flag present="
                + ((first & 0b0100) != 0));

        boolean a = true, b = false, c = false;
        System.out.println("precedence default=" + (a || b && c));
        System.out.println("precedence grouped=" + ((a || b) && c));

        boolean compoundAnd = false;
        compoundAnd &= trace("compound-and", true);
        System.out.println("compound &=" + compoundAnd);

        boolean compoundOr = true;
        compoundOr |= trace("compound-or", false);
        System.out.println("compound |=" + compoundOr);
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file. No Maven, Gradle, or external libraries needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ShortCircuitVsEagerDemo.java
java -cp . ShortCircuitVsEagerDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShortCircuitVsEagerDemo.java
java -cp . ShortCircuitVsEagerDemo
~~~

**Exact expected stdout:**

~~~text
AND short=false
AND eager=false
OR short=true
OR eager=true
skip &&=false
called eager-and
eager &=false
skip ||=true
called eager-or
eager |=true
called left
called right
both evaluated=false
safe division &&=false
safe division ||=true
eager division=ArithmeticException
safe null &&=false
safe null ||=true
eager null=NullPointerException
nullable Boolean=false
boxed skipped &&=false
boxed skipped ||=true
eager unboxing=NullPointerException
array[0]=true
array end=false
array null=false
eager array=ArrayIndexOutOfBoundsException
bitwise &=8
bitwise |=14
flag present=true
precedence default=true
precedence grouped=false
called compound-and
compound &=false
called compound-or
compound |=true
~~~

### Verifying the Meaning of the Output

1. The first four lines confirm `&&`/`&` and `||`/`|` share the **same truth table** on pure booleans.
2. Neither `called skip-and` nor `called skip-or` appears: the right side of `&&`/`||` was skipped.
3. `called eager-and` and `called eager-or` appear: boolean `&`/`|` still evaluate the right side.
4. `called left` precedes `called right`: both operands of `&` are evaluated left to right.
5. Integer-division and null guards avoid exceptions; with eager boolean operators, the exceptions occur as printed.
6. A null `Boolean` wrapper is skipped by short-circuiting, but causes NPE if forced to unbox.
7. The array is accessed safely thanks to all three checks; `&` with an out-of-bounds index throws an exception.
8. `0b1100 & 0b1010 = 8`; `0b1100 | 0b1010 = 14`; these are **bitwise**, not boolean short-circuit operations.
9. The two precedence lines differ because parentheses alter logical grouping.
10. Compound `&=`/`|=` still call the method on the right side, even when the variable's value already determines the result.

## 15. Common Mistakes and How to Handle Them

| Mistake / misconception | Why is it wrong? | How to handle |
|---|---|---|
| Boolean `&&` and `&` are identical in all cases | `&` evaluates the right side too | Use `&&` when short-circuiting is needed |
| Boolean `||` and `|` are identical in all cases | `|` evaluates the right side too | Use `||` when short-circuiting is needed |
| `obj != null & obj.ready()` | Calls method on null | `obj != null && obj.ready()` |
| `array == null | array.length == 0` | May read length of null | `array == null || array.length == 0` |
| `i < array.length && array[i] > 0` | Missing `i >= 0` check | Add negative-index guard |
| Using `&` to force both validations to run without considering exceptions | Left-side exception still aborts the whole expression | Call each validation with proper error handling |
| Thinking `&`/`|` evaluate both sides concurrently | Java evaluates sequentially from left to right | Do not assume parallelism |
| `int result = a && b;` | `&&` does not operate on int | Use `a & b` if bitwise is intended |
| `flags & MASK != 0` without parentheses | Easy to misread precedence; can cause type error | `(flags & MASK) != 0` |
| Treating `a || b && c` as `(a || b) && c` | `&&` has higher precedence than `||` | Use parentheses per intent |
| `Boolean flag = null; false & flag` | Right side is unboxed even though left side is false | Use `false && flag` if skipping is truly wanted |
| `flag &= check()` is short-circuiting | `&=` does not short-circuit | `flag = flag && check()` when appropriate |
| Putting `index++` inside guard condition | Index changes before subsequent read | Move update to a separate statement |
| Believing short-circuiting provides thread safety | Guards do not synchronize state across threads | Apply synchronization/ownership policies |

## 16. Exercises with Answers

### Exercise A — null guard

~~~java
String text = null;
boolean result = text != null && text.length() > 0;
System.out.println(result);
~~~

**Answer:** `false`, does not throw NPE. If `&&` is changed to `&`, the right side still runs and can throw NPE.

### Exercise B — short-circuit OR

~~~java
int divisor = 0;
boolean invalid = divisor == 0 || 10 / divisor > 2;
System.out.println(invalid);
~~~

**Answer:** `true`; the division does not run. With `|`, the division is evaluated and throws `ArithmeticException`.

### Exercise C — side effect

~~~java
int[] calls = {0};
boolean result = false & (++calls[0] > 0);
System.out.println(result);
System.out.println(calls[0]);
~~~

**Answer:**

~~~text
false
1
~~~

Even though the left side is false, `&` still increments the counter. If replaced with `&&`, the result is false and the counter stays 0.

### Exercise D — bitwise

~~~java
int a = 0b0101;
int b = 0b0011;
System.out.println(a & b);
System.out.println(a | b);
~~~

**Answer:**

~~~text
1
7
~~~

These are operations on **bits**, not `&&`/`||` logic.

### Exercise E — compound assignment

~~~java
int[] calls = {0};
boolean ready = true;
ready |= (++calls[0] > 0);
System.out.println(ready);
System.out.println(calls[0]);
~~~

**Answer:**

~~~text
true
1
~~~

`|=` still evaluates the right side. If you only want to increment when `ready` is false, you could consider `ready = ready || (++calls[0] > 0);`, while ensuring the change in side effect matches requirements.

### Exercise F — choosing how to validate both fields

Requirement: run both `validateName()` and `validateEmail()` to collect error messages from each method. What should be written?

**A readable answer:**

~~~java
boolean nameValid = validateName();
boolean emailValid = validateEmail();
boolean valid = nameValid && emailValid;
~~~

Both independent calls run during normal execution; the final expression only combines the booleans. If each validator can throw an exception, handle exceptions according to the contract to ensure all errors are still collected.

## 17. Checklist and Conclusion

- [ ] Know that `&&` skips the right side when the left is false, while `||` skips the right side when the left is true.
- [ ] Know that boolean `&`/`|` **always evaluate the right side when the operation executes normally**.
- [ ] Distinguish matching **truth-table results** from differing **side effects/exceptions/costs**.
- [ ] Know that Java evaluates left before right, never running both in parallel automatically.
- [ ] Use `&&` for null guards, index guards, and potentially failing operations.
- [ ] Use `||` for exclusion conditions: null or invalid values.
- [ ] Avoid using boolean `&`/`|` in place of short-circuit operators inside guards.
- [ ] Remember `&`/`|` are also bitwise on integer types.
- [ ] Use parentheses when combining bitwise ops with comparisons and when mixing `&&`/`||`.
- [ ] Know `&=`/`|=` do not short-circuit; Java has no `&&=`/`||=`.
- [ ] Do not use side effects like `index++` to mutate state between a guard and an access.
- [ ] Understand short-circuiting does not replace exception handling or multithreaded synchronization.
- [ ] Run `ShortCircuitVsEagerDemo.java` with Java 17+ and verify each stdout line.

**Conclusion:** `&&` and `||` are the default choice for **guarded logical conditions**, because Java guarantees skipping the right side once the result is determined. `&` and `|` on booleans have the same truth table but **evaluate both sides**, which can alter side effects and exceptions; on integers, they are **bitwise operators**. Choose operators based on **evaluation semantics**, not just true/false output.
