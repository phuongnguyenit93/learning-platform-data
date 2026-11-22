# The ?: Operator Can Unbox Wrapper Branches in Java

> **Java core – numbers · Boxing and unboxing**  
> **Goal:** Understand why the conditional expression `condition ? expression1 : expression2` sometimes automatically converts `Integer`, `Long`, `Double`… into primitives; know when a `null` value throws `NullPointerException`, when an unselected branch is not evaluated, and how to design safe handling for optional values in Java 17+.

## 1. A single line of Java can throw NullPointerException without calling .intValue()

Consider the code:

```java
Integer boxed = null;
boolean chooseBoxed = true;

Integer result = chooseBoxed ? boxed : 0;
// NullPointerException at runtime!
```

At first glance, the receiving variable has type `Integer`, so it is easy to assume the `boxed` branch will remain `null`. Yet in this example, one branch is **`Integer`** and the other branch is **`int`** (the literal `0`). Under the typing rules for a **numeric conditional expression**, the `?:` operator can determine the result type to be **primitive `int`**.

When the condition is `true`, Java must **unbox** the `boxed` branch to `int` to produce the value of the `?:` expression. Since `boxed == null`, this operation throws `NullPointerException`. The boxing step to assign into the `Integer result` variable will **not happen**, because expression evaluation has already failed.

Same wrapper branch, but condition `false`:

```java
Integer boxed = null;
Integer result = false ? boxed : 0;
System.out.println(result); // 0
```

Here Java selects the primitive branch `0`, so it does not read `boxed`'s value and no error occurs.

**Core point:** the type of **the entire conditional expression** is determined **at compile time** based on Java's rules; at runtime, only the selected branch is evaluated. If the selected branch is a wrapper that must be converted to a primitive, **unboxing can occur right inside the `?:` operator**, before the final assignment step.

## 2. Review: boxing, unboxing, primitives, and wrappers

**Boxing** converts a primitive value into a wrapper object; **unboxing** retrieves the primitive value from a wrapper.

| Primitive | Wrapper | Unboxing example |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.byteValue()` |
| `short` | `Short` | `Short.shortValue()` |
| `int` | `Integer` | `Integer.intValue()` |
| `long` | `Long` | `Long.longValue()` |
| `float` | `Float` | `Float.floatValue()` |
| `double` | `Double` | `Double.doubleValue()` |
| `char` | `Character` | `Character.charValue()` |
| `boolean` | `Boolean` | `Boolean.booleanValue()` |

Example:

```java
int n = 7;
Integer boxed = n;            // boxing, close to Integer.valueOf(n)
int original = boxed;         // unboxing, close to boxed.intValue()

Integer nullable = null;
// int failed = nullable;     // compiles, yet throws NPE at runtime
```

Wrappers are **reference** types, so `Integer` can be `null`. Primitive `int` cannot hold `null`. Whenever a context requires converting a wrapper holding `null` to a primitive, Java throws `NullPointerException`.

In practice, unboxing can be hidden in:

- addition/subtraction/multiplication/division such as `boxed + 1`;
- comparing a wrapper with a primitive, e.g., `boxed == 5`;
- assigning a wrapper to a primitive, e.g., `int x = boxed;`;
- an `if (boxedBoolean)` condition if `boxedBoolean` has type `Boolean`;
- **the `?:` operator**, when type selection rules require a primitive.

This lesson focuses on the last case, especially expressions that appear to be “selecting an object”.

## 3. Fundamental rules of the ?: conditional operator

Syntax:

```java
condition ? whenTrue : whenFalse
```

Sequence:

1. Evaluate the `condition` expression.
2. If the condition is true, **only evaluate `whenTrue`**.
3. If the condition is false, **only evaluate `whenFalse`**.
4. Convert the selected branch's value to **the type required by the conditional operator**, if needed, and produce the expression result.

The two branches **do not both execute**. However, the compiler must determine the **common/result type of the expression** according to Java's grammar and type-system rules before the program runs.

An example without wrappers:

```java
int x = true ? 10 : 20;    // 10
int y = false ? 10 : 20;   // 20
```

The `?:` operator can also be nested; it groups from **right to left**:

```java
int result = a ? 1 : b ? 2 : 3;
// Grouping: a ? 1 : (b ? 2 : 3)
```

Here `a` and `b` are pre-existing `boolean` variables; this is an **illustrative syntax** example, not a complete program. When nesting multiple expressions, each `?:` operator has its own type selection rules, making subtle implicit conversions even easier to miss.

### A boolean condition can also unbox

Even the **condition** itself can cause an NPE:

```java
Boolean enabled = null;
// int status = enabled ? 1 : 0; // NPE when unboxing enabled to obtain boolean
```

This case is **distinct** from an error caused by a selected wrapper branch: the error occurs **before choosing a branch**. You need to recognize the exact unboxing site when reading stack traces or writing tests.

## 4. Why can Integer and int produce a primitive int result?

Consider:

```java
Integer nullable = null;
int fallback = 0;

Integer value = choose ? nullable : fallback;
```

This is a **numeric conditional expression** because both branches have numeric-related types. With the branch pair `Integer` and `int`, the type of the conditional expression is `int`. If `nullable` is chosen, it must be **unboxed**.

Interpreting the meaning of that line step by step:

```text
condition ? Integer : int
          └── expression type per rules: int

When condition == true:
1. Retrieve nullable (Integer).
2. Convert Integer -> int (unboxing).
3. If nullable == null: throw NullPointerException.
4. If successful, the int result can be boxed when
   assigned to the Integer value variable.

When condition == false:
1. Retrieve fallback (int).
2. Result has type int.
3. Box if the assignment target has type Integer.
```

In an expression with `Integer` and `long`, Java may also need to widen the number to `long`:

```java
Integer maybe = null;
// long value = true ? maybe : 0L; // NPE: Integer branch needs unboxing then widening
```

**Do not** infer an overly simplistic general rule like “whenever there is one wrapper and one primitive, the result is always the primitive sharing the wrapper's name”. The type-selection tables for `?:` have special cases for constant expressions of type `int`, `byte`/`short`/`char`, and other numeric types. You must determine the **actual type pair** of the two branches and any nested expressions, rather than guessing from the target variable's type.

Nevertheless, the foundational `Integer ? int` example causing unboxing is enough to illustrate the risk.

## 5. The receiving variable's type does not necessarily prevent unboxing

Compare:

```java
Integer boxed = null;
boolean c = true;

// Both can throw NPE when selecting boxed:
 // int primitiveResult = c ? boxed : 0;
 // Integer wrapperResult = c ? boxed : 0;
```

Because in both expressions, the `boxed` branch and the `0` literal already determine the numeric conditional's type to be `int`. Declaring the receiving variable as `Integer` **does not automatically turn the `0` branch into `Integer` before the operator finishes evaluating**.

Similarly, when assigning to `Object`:

```java
Integer boxed = null;
// Object objectResult = true ? boxed : 0; // can still NPE
```

This context does not guarantee preserving the `boxed` reference. The conditional expression is still typed by its two branches; the `int` value is only boxed into an object **after** evaluating successfully.

To avoid misreasoning, inspect expressions **from the inside out**: branch types → type of `?:` → type of assignment. Do not work backward by looking at the target variable and assuming all intermediate conversions match it.

## 6. Both branches are Integer: an important difference

Now replace the primitive literal `0` with an `Integer` wrapper:

```java
Integer nullable = null;
Integer zeroBox = Integer.valueOf(0);

Integer chosen = true ? nullable : zeroBox;
System.out.println(chosen == null); // true
```

When **both branches have the same `Integer` type**, the expression's type selection rules keep the result type as `Integer`. If the `nullable` branch is selected, the result is the `null` reference; there is no reason to unbox at this operator.

Another readable way to write it:

```java
Integer chosen = true
        ? nullable
        : Integer.valueOf(0); // same Integer type as the other branch
```

At this point `null` can be preserved in the receiving `Integer` variable. However, if the chosen value is converted to a **primitive afterward**, an NPE will still happen:

```java
Integer nullable = null;
Integer other = Integer.valueOf(0);

// The ?: operator returns a potentially null Integer, yet assigning to int requires unboxing.
// int number = true ? nullable : other; // NPE on unboxing for assignment
```

The question to answer is not merely “does `?:` unbox?”, but also **whether subsequent steps using the result require unboxing**.

### Same wrapper type but with a null value in one branch

```java
Integer a = null;
Integer b = 7;
Integer selectedA = true ? a : b;  // null
Integer selectedB = false ? a : b; // 7
```

Both lines are safe **at the branch-selection and `Integer`-assignment steps**. Accessing `selectedA.intValue()` or adding `selectedA + 1` afterward is what triggers an NPE.

**Warning:** `Integer` is a numeric wrapper type; just because both branches look like objects does not mean every case mixing different numeric types preserves references. The cases above are safe because **both branches share the exact same `Integer` type** and the target is also `Integer`.

## 7. The true/false condition decides whether unboxing happens at runtime

An expression can **have an implicit conversion in its typing rules** yet not throw an error on every execution.

```java
Integer maybe = null;

int a = false ? maybe : 10; // 10; the maybe branch is not evaluated

// int b = true ? maybe : 10; // NPE; selects the maybe branch
```

The mechanism of **evaluating only the selected branch** is crucial: Java does not run both expressions and then pick a value. If the unselected branch calls a side-effecting function, throws an exception, or contains a null wrapper, it is never evaluated.

Example:

```java
static Integer loadNullable() {
    System.out.println("called");
    return null;
}

// Does not print "called", no NPE:
int safe = false ? loadNullable() : 100;

// Prints "called" then NPE:
// int failed = true ? loadNullable() : 100;
```

This is illustrative code; the `loadNullable` method must be placed inside a class, and the other statements in a method with appropriate context.

At the same time, the compiler still **type-checks both branches**. An unselected branch does not mean you are allowed to write syntactically or type-wise invalid code there.

## 8. Boolean wrapper is a special case

With a nullable `Boolean` wrapper, there are at least **two spots** to watch out for.

### 8.1. Unboxing to use as the condition

```java
Boolean condition = null;

// String text = condition ? "yes" : "no"; // NPE when evaluating condition
```

The condition part must have a `boolean` value (or an unboxed `Boolean`). If `condition` is `null`, no branch can be chosen.

If the business meaning is that **only `Boolean.TRUE` counts as true**, you can write:

```java
Boolean condition = null;
String text = Boolean.TRUE.equals(condition) ? "yes" : "no";
System.out.println(text); // no
```

This is an **explicitly chosen business rule**, not a natural definition for `null`. A system with three-state logic `true`/`false`/`unknown` may need to preserve the unknown state rather than silently turning it into false.

### 8.2. One Boolean branch, one boolean branch

```java
Boolean nullable = null;
// boolean selected = true ? nullable : false; // NPE when nullable is selected
```

Like numeric wrappers, when mixing `Boolean` with primitive `boolean`, type conversion can require unboxing the wrapper branch.

If you want to keep a nullable `Boolean` result:

```java
Boolean nullable = null;
Boolean fallback = Boolean.FALSE;
Boolean selected = true ? nullable : fallback;
System.out.println(selected == null); // true
```

Do not use a potentially null wrapper in `if`/`while` conditions or `&&`, `||` operators without explicit rules; unboxing null will throw an NPE when that operand's turn to evaluate arrives.

## 9. Examples with Long, Double, and other numeric wrappers

The risk does not happen only with `Integer`. For example:

```java
Long nullableLong = null;
// long x = true ? nullableLong : 0L; // NPE

Double nullableDouble = null;
// double y = true ? nullableDouble : 0.0; // NPE

Float nullableFloat = null;
// float z = true ? nullableFloat : 0.0f; // NPE
```

In these examples, the respective branches mix a wrapper with a primitive of the same numeric kind, leading to a primitive result and unboxing if the null branch is chosen.

With two wrappers of the same type, a null reference can be returned:

```java
Long a = null;
Long b = Long.valueOf(0L);
Long x = true ? a : b;
System.out.println(x == null); // true
```

### Mixing numeric wrappers of different types

For example, `Integer` and `Double` are different wrapper types:

```java
Integer count = Integer.valueOf(2);
Double ratio = Double.valueOf(1.5);

double result = true ? count : ratio;
System.out.println(result); // 2.0
```

In this numeric conditional example, Java uses numeric conversion rules to yield a `double` result; selecting `count` requires unboxing `Integer` and widening to `double`. If `count` is `null`, the selected branch will throw an NPE.

**Do not rely on “both branches are objects so no unboxing occurs”.** With numeric conditional expressions, numeric typing rules can demand primitive values even when each branch starts as a wrapper.

## 10. Re-autoboxing at the final step can hide an earlier unboxing step

Consider the chain of steps:

```java
Integer maybe = Integer.valueOf(5);
Integer answer = true ? maybe : 0;
System.out.println(answer); // 5
```

In this case:

1. `maybe` has type `Integer`;
2. the other branch is `int 0`;
3. the conditional expression has type `int`;
4. when `maybe` is selected, Java unboxes it to 5;
5. assigning to `Integer answer` can box 5 back.

When `maybe` is non-null, the program still runs and readers might not notice that **unboxing → boxing** took place. Only when a `null` value appears does the NPE surface.

Therefore test suites that only use non-null wrappers are **not enough** to prove a value-selecting expression is null-safe. You must test both the null branch and the corresponding true/false conditions.

## 11. How to fix: clearly define the null contract before choosing values

There is no single “fix” for every problem. You must decide on one of three requirements:

1. **Preserve `null`** to signify “no value”.
2. **Use a fallback** such as 0 or 1 when the wrapper is null.
3. **Reject null** with an exception bearing a clear message.

### 11.1. When preserving null

Use two branches of the same wrapper type and a wrapper target:

```java
Integer nullable = null;
Integer fallbackBoxed = Integer.valueOf(0);

Integer result = true ? nullable : fallbackBoxed;
System.out.println(result == null); // true
```

Or write `if/else` to make it explicit:

```java
Integer result;
if (true) {
    result = nullable;
} else {
    result = fallbackBoxed;
}
```

The `if (true)` snippet only illustrates control flow; in a real program, replace it with a business condition. **Do not unbox `result` later if null remains valid.**

### 11.2. When falling back on wrapper null

If a non-null primitive integer is required:

```java
Integer maybe = null;
int count = maybe != null ? maybe.intValue() : 0;
System.out.println(count); // 0
```

Here **the condition checks the wrapper value itself**; when `maybe == null`, the branch calling `intValue()` is not evaluated. This makes it very clear that `null` turns into `0` per the chosen rule.

If there is also a business condition `choose`:

```java
Integer maybe = null;
boolean choose = true;
int result = choose && maybe != null ? maybe.intValue() : 0;
```

Verify whether “not chosen” and “chosen but has no value” truly map to the same 0. If the two states mean different things, do not collapse them with a single fallback.

You can also use `Objects.requireNonNullElse` when you need a wrapper with a **non-null** fallback, while still remembering it is a convention-based null replacement, not something Java automatically applies to `?:`:

```java
import java.util.Objects;

Integer maybe = null;
Integer result = Objects.requireNonNullElse(
        maybe, Integer.valueOf(0));
System.out.println(result); // 0
```

### 11.3. When rejecting null

```java
import java.util.Objects;

Integer maybe = null;
// int x = Objects.requireNonNull(maybe, "Missing count"); // throws NPE with clear message
```

Or proactively throw `IllegalArgumentException` at the API boundary if null is invalid input data. Do not mask bugs by wrapping a large expression in a `NullPointerException` catch block and silently substituting 0: that easily swallows unrelated programming errors.

## 12. When to write if/else instead of ?:

The `?:` operator fits when both branches are short, readable, and have clear result types. When multiple wrapper types, nullability, or complex conditional logic are involved, `if/else` usually makes **the unboxing step** much more visible:

```java
static Integer chooseNullable(boolean choose, Integer input) {
    if (choose) {
        return input;     // may return null
    }
    return Integer.valueOf(0);
}

static int choosePrimitive(boolean choose, Integer input) {
    if (choose) {
        if (input == null) {
            throw new IllegalArgumentException("Missing input");
        }
        return input.intValue();
    }
    return 0;
}
```

These two methods have **different contracts**:

- `chooseNullable` can return `null`, which the caller must handle.
- `choosePrimitive` always returns `int` or throws an explicit exception if the needed number is absent.

Compare with a misleading method:

```java
static Integer subtle(boolean choose, Integer input) {
    return choose ? input : 0;
}
```

Even though the signature returns `Integer`, the `input` branch can still be unboxed by the numeric conditional expression. **The method's return type does not automatically fix how `?:` inside determines its type.**

A good API design should explicitly state: are parameters/return values allowed to be null, and is any fallback applied?

## 13. Do not cast arbitrarily to dodge NullPointerException

You might encounter the trick “cast to Object so Java does not unbox”:

```java
Integer nullable = null;
Object selected = true ? (Object) nullable : 0;
System.out.println(selected == null); // true
```

Because one branch has type `Object`, this expression falls under **reference conditional expression** and can retain a null reference. Yet that is **not a default solution** for variables needing type `Integer` or `int`, because returning `Object` weakens type safety and may require casts later.

Similarly, changing all branches to another reference type without understanding conditional typing rules can hide a bug here only to move it elsewhere. Prefer:

- matching wrapper types when you genuinely want to preserve null;
- explicit null checks when primitives are needed;
- `if/else` when multiple processing steps or good error messages are required.

### Be careful with Optional

`Optional<Integer>` represents the presence or absence of an integer:

```java
import java.util.Optional;

Integer maybe = null;
int count = Optional.ofNullable(maybe).orElse(0);
System.out.println(count); // 0
```

This is an option for **certain API boundaries**, unnecessary for every simple addition. `Optional` does not “cure” every null bug either: you still need to intentionally choose a fallback, throw an error, or handle the absent case.

## 14. Standalone runnable Java 17+ demo

Create file **`ConditionalUnboxingDemo.java`**:

```java
import java.util.Objects;

public class ConditionalUnboxingDemo {
    private static Integer chooseNullable(boolean choose, Integer value) {
        return choose ? value : Integer.valueOf(0);
    }

    private static Integer subtle(boolean choose, Integer value) {
        return choose ? value : 0;
    }

    private static void runCase(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException ex) {
            System.out.println(name + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        Integer missing = null;

        runCase("selected Integer+int", () -> {
            Integer result = true ? missing : 0;
            System.out.println(result);
        });

        Integer notSelected = false ? missing : 0;
        System.out.println("unselected null = " + notSelected);

        Integer keptNull = true
                ? missing
                : Integer.valueOf(0);
        System.out.println("two Integer branches null = "
                + (keptNull == null));

        Integer fromMethod = chooseNullable(true, missing);
        System.out.println("nullable method null = "
                + (fromMethod == null));

        runCase("method returning Integer", () -> {
            System.out.println(subtle(true, missing));
        });

        runCase("assignment to int", () -> {
            Integer left = null;
            Integer right = Integer.valueOf(0);
            int number = true ? left : right;
            System.out.println(number);
        });

        int safe = missing != null ? missing.intValue() : 0;
        System.out.println("explicit fallback = " + safe);

        Integer fallback = Objects.requireNonNullElse(
                missing, Integer.valueOf(0));
        System.out.println("Objects fallback = " + fallback);

        runCase("Boolean condition", () -> {
            Boolean enabled = null;
            int status = enabled ? 1 : 0;
            System.out.println(status);
        });

        runCase("Long+long", () -> {
            Long amount = null;
            long total = true ? amount : 0L;
            System.out.println(total);
        });

        Integer a = Integer.valueOf(2);
        Double b = Double.valueOf(1.5);
        double mixed = true ? a : b;
        System.out.println("mixed numeric = " + mixed);

        Object keptObject = true ? (Object) missing : 0;
        System.out.println("Object branch null = "
                + (keptObject == null));
    }
}
```

Run from the directory containing the file:

```bash
javac ConditionalUnboxingDemo.java
java ConditionalUnboxingDemo
```

**Expected output on Java 17+:**

```text
selected Integer+int: NullPointerException
unselected null = 0
two Integer branches null = true
nullable method null = true
method returning Integer: NullPointerException
assignment to int: NullPointerException
explicit fallback = 0
Objects fallback = 0
Boolean condition: NullPointerException
Long+long: NullPointerException
mixed numeric = 2.0
Object branch null = true
```

**Explanation:**

1. `true ? missing : 0` produces numeric conditional type `int`, so `missing` must be unboxed and throws NPE.
2. `false ? missing : 0` does not evaluate the null branch; result is 0.
3. Two `Integer` branches produce a reference value, thus null can be preserved; yet assigning the result to `int` still requires unboxing.
4. A method returning `Integer` does not automatically prevent unboxing if the expression inside mixes `Integer` and `int`.
5. Checking `missing != null` and `Objects.requireNonNullElse` are two explicit ways to define a fallback of 0.
6. A null `Boolean` in the condition and a selected null `Long` in a numeric conditional can both throw NPE.
7. Mixing `Integer` and `Double` produces a numeric result handled via numeric type conversion; selecting branch `Integer 2` yields `double 2.0`.
8. Casting a branch to `Object` illustrates a reference conditional expression that can preserve null, though type safety must be weighed.

## 15. Comparison table of common scenarios

In this table, `n` is the variable `Integer n = null;`; `zero` is `Integer zero = Integer.valueOf(0);`.

| Expression / situation | Core type or conversion | At runtime |
| --- | --- | --- |
| `Integer x = true ? n : 0;` | `Integer` + `int` → `int` result then boxed on assignment | **NPE** |
| `Integer x = false ? n : 0;` | Selects primitive `int` branch | `x = 0` |
| `int x = true ? n : 0;` | Selects `n` then unboxes | **NPE** |
| `Object x = true ? n : 0;` | Numeric operator before boxing to Object | **NPE** |
| `Integer x = true ? n : zero;` | Both branches are `Integer` | `x = null` |
| `int x = true ? n : zero;` | Operator keeps `Integer`, yet assignment is to primitive | **NPE on assignment** |
| `Integer x = n != null ? n : zero;` | Has null check and selected branches are both `Integer` | `x = 0` |
| `int x = n != null ? n.intValue() : 0;` | Unboxes only in the checked branch | `x = 0` |
| `boolean x = ((Boolean) null) ? true : false;` | Condition must unbox Boolean | **NPE before branch selection** |
| `Object x = true ? (Object)n : 0;` | One branch cast to Object → reference conditional | `x = null` |

**Precision about timing:** even though all are NPEs, they can happen at **the condition**, at **the selected branch** inside `?:`, or at **the conversion step after the operator returns a value**. Fixing the bug should start by identifying that exact step.

## 16. Misconceptions that easily lead to bugs

| Misconception | Accurate explanation |
| --- | --- |
| “Receiving variable type `Integer` means no unboxing.” | The type of `?:` can be `int` before boxing into the receiving variable. |
| “A `null` branch never causes NPE because null is a reference.” | If the selected wrapper branch needs unboxing, null causes NPE. |
| “The `?:` operator always evaluates both branches.” | Only one branch is evaluated; the unselected branch causes no runtime side effects. |
| “When both branches are wrappers, it always returns a wrapper.” | With the **same wrapper type**, the reference can be preserved; different numeric wrapper types can undergo numeric promotion. |
| “Changing `0` to `Integer.valueOf(0)` always eliminates all NPEs.” | It only prevents unboxing at `?:` when both branches are Integer; if the target is `int`, an NPE can still occur. |
| “`Objects.equals(n, 0)` is the same as `n == 0` when n is null.” | `Objects.equals` is null-safe, whereas `n == 0` can unbox null. |
| “Casting to Object makes any type safe.” | It may preserve null at selection, yet loses type safety and still risks errors on later casts/unboxing. |
| “A null Boolean is automatically treated as false.” | No; using it as a condition requires unboxing and can throw NPE. |
| “If code runs with non-null values, ?: is safe.” | You must test both the null wrapper branch and the opposite branch. |
| “The compiler picks branch types based on known true/false values.” | Type-checking determines types from both operands per language rules, regardless of which branch executes at runtime. |
| “Just catching NPE at the end is enough.” | NPEs can reflect other bugs; check null and specify contracts where data is used. |

## 17. Self-check exercises and solutions

**Exercise 1.** With `Integer n = null;`, evaluate `Integer r = true ? n : 0;`. Why does it not simply receive null?  
**Answer:** The two branches `Integer` and `int` create a numeric conditional of type `int`. Selecting `n` requires unboxing null, throwing `NullPointerException` before the result can be boxed for assignment.

**Exercise 2.** Does `Integer r = false ? n : 0;` (with `n=null`) throw NPE?  
**Answer:** No. Java only evaluates the `0` branch because the condition is false; after boxing, the result is `Integer 0`.

**Exercise 3.** Does `Integer z = Integer.valueOf(0); Integer r = true ? n : z;` throw NPE when `n=null`?  
**Answer:** Not at the selection/assignment step: both branches are `Integer`, the expression returns a `null` reference, and `r=null`. However, using `int x=r;` afterward will throw NPE.

**Exercise 4.** Why does `int x = true ? n : z;` still throw NPE even though both branches are Integer?  
**Answer:** The `?:` operator can return `Integer null`, yet assigning to `int` forces unboxing the null reference.

**Exercise 5.** With `Boolean b=null;`, at which step does `int x=b ? 1:0;` fail?  
**Answer:** During unboxing of **condition** `b` to obtain a primitive `boolean`, before selecting either numeric branch.

**Exercise 6.** Fix `int r = choose ? nullable : 0;` per the requirement: null is treated as 0.  
**Answer:** `int r = choose && nullable != null ? nullable.intValue() : 0;`, where `choose` is boolean and `nullable` has type `Integer`. The condition checks null before calling `intValue()`.

**Exercise 7.** Fix the same expression per the requirement: when choose=true and nullable=null, **must return null**.  
**Answer:** The result must be `Integer` and both branches must be wrappers: `Integer r = choose ? nullable : Integer.valueOf(0);`. The caller remains responsible for handling null.

**Exercise 8.** Does `Object o = true ? nullable : 0;` always avoid NPE?  
**Answer:** No. The numeric conditional's type is determined from the `Integer`/`int` branches first, which can unbox null. Assigning to `Object` does not undo the step that already happened.

**Exercise 9.** If the unselected branch contains `Integer null` or a method that throws an error, does it run?  
**Answer:** No. The operator only evaluates the one selected branch; however, both branches must still be syntactically and type-wise valid at compile time.

**Exercise 10.** During a PR review, you see `return condition ? boxed : 0;` in a method returning `Integer`. What should you check?  
**Answer:** Check whether `boxed` can be null, because `?:` can have type `int` and unbox before boxing the return value. If null is allowed, use `Integer.valueOf(0)` for the other branch or write `if/else` to preserve the wrapper type; if null is invalid, validate and report a clear error.

## 18. Checklist when using ?: with wrappers

1. Check the type of **condition**: `boolean` or potentially null `Boolean`?
2. Check the type of **each branch**, not just the receiving variable: primitive, same wrapper type, or different numeric wrapper types?
3. Determine the result type **of `?:` itself** per Java rules; do not assume an `Integer` assignment target means the prior expression result is a wrapper.
4. Ask if a wrapper branch can be `null`; if selected, does it require unboxing?
5. Ask if **the consumer of the result** will unbox afterward, even if `?:` preserves a reference?
6. If null must be preserved, use **two branches of the same wrapper type** and a wrapper target, and document the nullability contract.
7. If a primitive is mandatory, **check for null beforehand** or reject the data with an intentional exception.
8. If a fallback is needed, document it as a **business rule**; 0 does not automatically equate to “no value”.
9. Write tests covering **condition true/false**, null/non-null wrapper branches, boxed values, and nested ternaries.
10. When an expression is complex or invites type confusion, **use `if/else`** to clarify intent.

**Key takeaway:** `?:` evaluates only **one branch**, yet its result type is chosen at compile time by Java's rules. If that type demands a **primitive**, a selected wrapper branch can be **automatically unboxed** and throw `NullPointerException` when holding `null`—even when the receiving variable or final return type is a wrapper. To write safe code, check for null and clarify the types of both the **`?:` expression** and where its result is consumed.