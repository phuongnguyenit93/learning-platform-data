# Conditional operator `?:` and special numeric rules in Java

## 1. What does `?:` do, and why do numeric types sometimes surprise you?

Java's ternary conditional operator has the syntax:

~~~java
condition ? valueIfTrue : valueIfFalse
~~~

This is **illustrative syntax**, not a standalone Java program. `condition` must have type `boolean` or `Boolean` (unboxed to `boolean`). When the condition is `true`, Java evaluates the second operand; when `false`, Java evaluates the third operand. **Only the chosen branch is evaluated at runtime**.

Example:

~~~java
int stock = 12;
int remaining = stock > 0 ? stock : 0;
~~~

The result `remaining` is `12`. With numeric data, learners often assume "Java takes the type of the branch that actually runs." That is **incorrect**: **the type of the entire `?:` expression is determined at compile time from the types of *both branches***, including the branch not chosen at runtime.

In particular, `?:` has **exceptions compared to ordinary binary numeric promotion**. The expression `byte b = 10; byte x = flag ? b : 20;` can be valid even though one branch is an `int` literal, because `20` is an `int` constant expression within the `byte` range. However, replacing `20` with an ordinary `int` variable can make the result type `int`, which cannot be directly assigned to `byte`.

To use `?:` correctly with Java numbers, distinguish:

1. **Which branch runs?** Exactly one branch is chosen based on the `boolean`.
2. **What is the type of the whole expression?** The compiler decides according to the rules of `?:`.
3. **Does the chosen branch's value need conversion?** There may be numeric promotion, unboxing, or another conversion depending on the expression category.
4. **Is the result safe?** Converting to `float`/`double` can lose precision; unboxing `null` can throw `NullPointerException`.

## 2. Classification of three kinds of conditional expressions

The Java Language Specification, section `15.25`, distinguishes three forms:

| Form | Example | Notable typing rule |
|---|---|---|
| **Boolean conditional expression** | `flag ? true : false` | Type `boolean` or `Boolean` depending on the two branches |
| **Numeric conditional expression** | `flag ? 1 : 2L` | Follows special rules for numeric types; e.g., yields `long` |
| **Reference conditional expression** | `flag ? "yes" : "no"` | Can be a *poly expression* influenced by target type context |

This lesson focuses on **numeric conditional expressions**, i.e., when the second and third operands are primitive numeric types or their corresponding wrapper classes and are classified as numeric expressions under the specification. Branches such as `String` and `null` can lead to a **reference conditional expression** with its own rules, so do not mechanically apply the numeric table here.

For a numeric conditional expression, Java determines the type based on **both branch operands**. It is a *standalone expression*: its type **does not change just because the variable on the left has a desired type**. For example, if the two branches make the result type `int`, writing `byte result = ...` does not force the result to become `byte`.

### Runtime evaluation diagram

~~~text
                 condition
                     |
                 boolean?
                  /     \
              true      false
               |          |
        eval branch 2   eval branch 3
               \          /
             convert chosen value
                       |
                value of ?: expr
~~~

This diagram describes the **runtime order**; the result type has already been determined by the compiler **before** runtime. If the condition is a `Boolean` object holding `null`, unboxing the condition throws `NullPointerException` before either branch is selected.

## 3. Special typing rules for numeric expressions

According to the specification, when both branches are numeric expressions, check in order:

1. **Both branches have the same type:** the result type is that same type. For example, `flag ? 1 : 2` is `int`; `flag ? 1L : 2L` is `long`; `flag ? someByte : otherByte` is `byte`.
2. **One branch has primitive type `T` and the other has the exact wrapper class for `T`:** the result type is primitive `T`; for instance, `byte` with `Byte` yields `byte`. The wrapper branch may have to be unboxed.
3. **One branch is `byte` or `Byte`, and the other is `short` or `Short`:** the result type is **`short`** (even if a wrapper is used in one or both branches).
4. **One branch is `byte`, `short`, or `char`, and the other is an `int` *constant expression* representable in that smaller type:** the result has **that corresponding smaller type**. For example, `byte` with `int` constant `100` yields `byte`.
5. **Similarly, with wrapper `Byte`, `Short`, `Character` and an `int` constant fitting the underlying primitive range:** the result is the **unboxed primitive**, e.g., `Byte` with `int` constant `100` yields `byte`.
6. **If none of the above apply:** perform general **numeric promotion** to a common type; for example, `char` with `short` becomes `int`, `int` with `long` becomes `long`, `long` with `float` becomes `float`, and `float` with `double` becomes `double`.

The fourth and fifth items are two easily overlooked exceptions. Having an `int` branch does not always make the result `int`; however, **the constant must have type `int`, be a constant expression, and fit within the narrow type's range**.

Example table (assuming `flag` is `boolean` and variables have the stated types):

| Two branches of `?:` | Type of whole expression | Why |
|---|---|---|
| `byte / byte` | `byte` | Same type |
| `short / short` | `short` | Same type |
| `byte / short` | `short` | `byte`–`short` exception |
| `byte / 100` | `byte` | `100` is an `int` constant within `byte` range |
| `byte / 200` | `int` | `200` is not within `byte` range |
| `char / 65` | `char` | `int` constant `65` is within `char` range |
| `char / -1` | `int` | `-1` is not within `char` range |
| `char / short` | `int` | Numeric promotion |
| `short / intVariable` | `int` | Ordinary `int` variable, not a constant expression |
| `int / long` | `long` | Numeric promotion |
| `long / float` | `float` | Numeric promotion; may lose precision |
| `float / double` | `double` | Numeric promotion |

In the first column, the `/` symbol **only separates the types of the two branches**, and does not denote division. The common type is a **compile-time** rule, independent of whether `flag` ends up true or false.

## 4. The `byte`–`short` exception: result has type `short`

Binary arithmetic expressions like `byteValue + shortValue` are normally promoted to `int`. Yet `flag ? byteValue : shortValue` is a **special** case whose result type is `short`:

~~~java
boolean flag = true;
byte small = 10;
short medium = 20;

short chosen = flag ? small : medium; // valid
// byte invalid = flag ? small : medium; // compile error: result is short
~~~

This illustrative snippet can be placed in `main`. If `flag` is `true`, the `byte` value `10` is widened to `short`; if `false`, the `short` value `20` is chosen. **The overall type remains `short` in both cases**.

The corresponding wrapper classes are also subject to this rule: `Byte` with `short` or `Short` with `byte` can produce an expression of type `short` and require unboxing on the chosen branch.

Note the difference when **adding**:

~~~java
byte small = 10;
short medium = 20;
int sum = small + medium;  // int, because addition promotes
short selection = true ? small : medium; // short
~~~

Same two operand types, yet **two different operators have different typing rule sets**.

## 5. `int` constants fitting small type ranges: `byte`, `short`, `char`

Suppose `byte small = 10;`:

~~~java
boolean flag = true;
byte small = 10;

byte a = flag ? small : 20;      // byte: 20 is in [-128, 127]
int b = flag ? small : 200;      // int: 200 is outside byte range
// byte invalid = flag ? small : 200; // error: whole expression is int
~~~

Even though the chosen branch might be `small` with value `10`, the compiler still examines **both branches**. Changing `flag` to a fixed `true` does not turn an `int`-typed expression into `byte` under `?:` rules; the expression type must be inferred before checking assignment to the target variable.

The same applies to `short` and `char`:

~~~java
short count = 123;
char letter = 'A';

short s = true ? count : 30_000;   // short: 30000 fits in range
char c = true ? letter : 65;       // char: 65 fits in range
int x = true ? letter : -1;        // int: -1 does not fit in char
int y = true ? count : 40_000;     // int: 40000 is outside short range
~~~

This code snippet is illustrative, not a standalone runnable class.

### Constant expressions differ from `int` variables

A **non-`final` `int` variable** is not considered a compile-time constant, even if at runtime it is always 20:

~~~java
byte small = 10;
int normal = 20;
final int constant = 20;

byte first = true ? small : constant; // byte
int second = true ? small : normal;   // int
// byte invalid = true ? small : normal; // error if assigned to byte
~~~

In the example, `constant` is a **constant variable** because it has primitive type `int`, is `final`, and is initialized with a constant expression. A `final int` variable assigned from a runtime result, such as a method call, **does not automatically become a constant variable**.

You can write constant expressions like `10 + 10` or `(1 << 5)` when they satisfy *constant expression* rules. However, if the expression has type `long`, such as `20L`, the "`int` constant" exception **does not apply**; `byte` with `20L` yields `long` via numeric promotion.

## 6. How to verify the **compile-time type**, rather than just looking at printed values

If you print `System.out.println(flag ? small : 20)`, you only see the number `10` or `20`, without knowing whether the expression has type `byte` or `int`. You can use **overloading** to observe the compiler's choice.

Create the file `ConditionalNumericTypeDemo.java`:

~~~java
public class ConditionalNumericTypeDemo {
    static String kind(byte value) { return "byte"; }
    static String kind(short value) { return "short"; }
    static String kind(int value) { return "int"; }
    static String kind(long value) { return "long"; }
    static String kind(float value) { return "float"; }
    static String kind(double value) { return "double"; }

    public static void main(String[] args) {
        boolean flag = true;
        byte small = 10;
        short medium = 20;
        char letter = 'A';
        int normal = 20;
        final int constant = 20;

        System.out.println("byteShort=" + kind(flag ? small : medium));
        System.out.println("byteIntConst=" + kind(flag ? small : 20));
        System.out.println("byteFinalConst=" + kind(flag ? small : constant));
        System.out.println("byteIntVariable=" + kind(flag ? small : normal));
        System.out.println("byteIntOutside=" + kind(flag ? small : 200));
        System.out.println("charShort=" + kind(flag ? letter : medium));
        System.out.println("intLong=" + kind(flag ? 1 : 2L));
        System.out.println("intDouble=" + kind(flag ? 1 : 2.5));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac ConditionalNumericTypeDemo.java
java ConditionalNumericTypeDemo
~~~

Output:

~~~text
byteShort=short
byteIntConst=byte
byteFinalConst=byte
byteIntVariable=int
byteIntOutside=int
charShort=int
intLong=long
intDouble=double
~~~

This shows the **static type of the `?:` result** chosen by Java at the `kind` call site. Notably, even though `flag` is `true` and the `small` branch has value 10, the `byteIntOutside` line still calls the `kind(int)` overload because the unchosen branch is constant `200`, which exceeds the `byte` range.

Similarly, in Java 10+, you can use `var result = flag ? small : medium;`. `var` infers the **static type of the right-hand expression** as `short`; `var` does not dynamically keep the type of the runtime branch.

## 7. Wrappers `Byte`, `Short`, `Character`, and unboxing

Java provides wrapper classes for primitives: `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, and `Double`. With numeric `?:`, **boxing/unboxing can occur** to bring both branches to the result type.

### Combining a matching primitive and wrapper pair

Example:

~~~java
Byte wrapper = Byte.valueOf((byte) 10);
byte primitive = 20;
byte chosen = true ? wrapper : primitive; // byte: wrapper is unboxed
~~~

The resulting expression has type **`byte`**, not `Byte`. If `wrapper` is `null` and the wrapper branch is selected, unboxing throws `NullPointerException`.

### Combining a wrapper with an in-range `int` constant

~~~java
Byte boxed = Byte.valueOf((byte) 5);
int chosen = true ? boxed : 7; // expression has type byte, widened on int assignment
~~~

Here, the constant `7` is an `int` within the `byte` range, so the `?:` result is **primitive `byte`**; only upon assigning to `int` is there an additional widening step from `byte` to `int`.

Conversely, `true ? boxed : 200` has type `int` because `200` is not within `byte` range, and may also require unboxing the `boxed` branch.

### Two wrappers of the same type

Given `Byte first = ...; Byte second = ...;`, `flag ? first : second` has type **`Byte`** according to the rule for two branches of the same type. The result can be `null` without throwing an error, as long as no unboxing step occurs. This is an important difference from having one `Byte` branch and one primitive `byte` branch.

### Standalone Java 17+ example: `null` error occurs only when the branch needing unboxing is selected

Create the file `ConditionalWrapperDemo.java`:

~~~java
public class ConditionalWrapperDemo {
    public static void main(String[] args) {
        Byte missing = null;

        System.out.println("unselected=" + (false ? missing : 7));

        try {
            int value = true ? missing : 7;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("selectedNull=NPE");
        }

        Byte other = Byte.valueOf((byte) 9);
        Byte sameType = true ? missing : other;
        System.out.println("sameTypeKeepsNull=" + (sameType == null));

        Boolean condition = null;
        try {
            int value = condition ? 1 : 2;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("nullCondition=NPE");
        }
    }
}
~~~

~~~bash
javac ConditionalWrapperDemo.java
java ConditionalWrapperDemo
~~~

Output:

~~~text
unselected=7
selectedNull=NPE
sameTypeKeepsNull=true
nullCondition=NPE
~~~

Explanation:

1. `false ? missing : 7` selects `7` and does not evaluate `missing` as the chosen operand to unbox; hence it causes no error.
2. `true ? missing : 7` selects `missing`: the numeric expression type is `byte`, requiring unboxing of the `null` object, causing `NullPointerException`.
3. Both branches are `Byte` of the same type, so the expression result stays a `Byte` reference, which can hold `null`.
4. `condition` has type `Boolean` and holds `null`; the error occurs when unboxing the **condition**, before branch selection.

If you need to clearly express a policy for optional values, check `null` first or switch to an `if` statement. Do not treat `?:` as a mechanism that automatically provides a safe default when `null` wrappers are present.

## 8. General numeric promotion when no exception applies

If none of the special cases match, both branches are brought to a common numeric type. Core rules:

- If `double` is present, the result normally becomes `double`.
- If there is no `double` but `float` is present, the result normally becomes `float`.
- If neither is present but `long` is present, the result normally becomes `long`.
- Remaining small combinations (`byte`, `short`, `char`, `int`) normally become `int`, **except for the special cases in the earlier section**.

Example:

~~~java
boolean flag = true;
char letter = 'A';
short small = 12;

int result = flag ? letter : small;   // int: char/short
long count = flag ? 12 : 30L;        // long: int/long
double ratio = flag ? 1.25f : 2.0;  // double: float/double
~~~

This is an illustrative snippet. Note that the common type can lead to **loss of precision**:

~~~java
long huge = 9_007_199_254_740_993L; // 2^53 + 1
double number = true ? huge : 0.0; // long is converted to double
~~~

`double` cannot represent every 64-bit integer exactly. In this example, the value `huge` is larger than `double`'s last consecutive exact integer, and converting to `double` can round it to `9007199254740992.0`. Only use floating-point types when rounding tolerance fits the problem.

### Numeric promotion is not addition

`flag ? a : b` **selects one branch**, unlike `a + b` which performs addition. Even though both can use numeric promotion mechanisms, **they do not evaluate both branches to add them together**, and `?:` has special rules for `byte`/`short`/`char` with `int` constants that addition does not have.

## 9. Only the selected branch runs: side effects and exceptions

Create the file `ConditionalEvaluationDemo.java`:

~~~java
public class ConditionalEvaluationDemo {
    private static int calls;

    private static int selected() {
        calls++;
        return 42;
    }

    private static int notSelected() {
        calls += 100;
        throw new IllegalStateException("should not execute");
    }

    public static void main(String[] args) {
        int answer = true ? selected() : notSelected();

        System.out.println("answer=" + answer);
        System.out.println("calls=" + calls);

        int second = false ? notSelected() : 7;
        System.out.println("second=" + second);
        System.out.println("callsAfter=" + calls);
    }
}
~~~

~~~bash
javac ConditionalEvaluationDemo.java
java ConditionalEvaluationDemo
~~~

Output:

~~~text
answer=42
calls=1
second=7
callsAfter=1
~~~

Reason: `notSelected()` **does not run** in either `?:` expression because the condition does not choose that branch. Yet the compiler still checks the **types** and syntax of both branches. Avoid putting critical side effects in a branch that might not be chosen. If both branches involve multiple complex statements, `if/else` is usually easier to read and control.

Also distinguish this from `Math.max(a, b)`: in a method call, Java evaluates both argument expressions before invoking the method, whereas `?:` evaluates only the selected branch expression.

## 10. Combining multiple `?:`, precedence, and readability

The conditional operator is **right-associative**:

~~~java
int level = 2;
int score = level == 1 ? 10 : level == 2 ? 20 : 30;
~~~

This is illustrative code; it is parsed as:

~~~java
int score = level == 1 ? 10 : (level == 2 ? 20 : 30);
~~~

The result is `20`. If there are multiple nested numeric conditions and branches, pay attention to the types of nested `?:` expressions, because a subexpression's type can affect the outer expression's type. Use parentheses and intermediate named variables in hard-to-read cases.

### Precedence traps when combining operators

Some expressions are easy to misread when parentheses are omitted:

~~~java
int a = 5;
int b = 3;
int selected = a > b ? a : b;    // 5
int result = (a > b ? a : b) + 1; // 6
~~~

This is illustrative. Parentheses in `result` make clear that addition applies to the **entire selected result**.

Do not chain too many `?:` operators for a business rule with multiple nested conditions. Using `if/else` or well-named helper methods is usually easier to read and test.

## 11. Comparison with arithmetic expressions and `if/else` statements

| Situation | `?:` | `if/else` or other operations |
|---|---|---|
| Choosing concisely between two numeric values | Suitable, e.g., `flag ? a : b` | `if/else` also works but is longer |
| Two branches have different types | Need to understand `?:` typing rules | Can assign separately after range checks |
| Branch has multiple steps or side effects | Easily becomes hard to read | `if/else` shows control flow clearly |
| Need to handle nullable wrappers | Can throw during unboxing | Explicit `null` checks and clear data contract |
| Need to avoid precision loss | Must determine expression type beforehand | Use exact types / checked conversions |
| Need maximum/minimum value | `a > b ? a : b` | `Math.max(a, b)` is convenient for numbers, though argument expressions are evaluated under method call mechanics |

### Do not confuse the type of `?:` with the assignment target type

For example, both branches are `int` expressions, even though the selected value falls in the `byte` range:

~~~java
int left = 10;
int right = 20;
// byte value = true ? left : right; // does not compile
int value = true ? left : right;    // valid
~~~

Even though at runtime the result is 10, the type of `?:` is still `int`. If you want to narrow to `byte`, check bounds and cast intentionally, or declare the branches as `byte` appropriately when the data model truly represents 8-bit integers.

Another case: `flag ? (byte) 10 : 20` has type `byte` because one branch is `byte` and the other is an in-range `int` constant `20`. This is the exception in rule `15.25.2`, not type inference from the variable on the left.

## 12. Common mistakes

| Claim | Accurate understanding |
|---|---|
| "`?:` always performs binary numeric promotion like `+`." | There are exceptions such as `byte` with `short` yielding `short`, or `byte` with an in-range `int` constant yielding `byte`. |
| "`flag` is true so the compiler only checks the second branch's type." | The compiler still checks the types of both branches, even though the other branch does not run. |
| "`byte` with any `int` becomes `byte` if the `byte` branch is selected." | The exception applies only when the `int` branch is a **constant expression** whose value fits in range. |
| "`final int` is always a compile-time constant." | Only when the variable is a *constant variable* initialized with a valid constant expression. |
| "`byte` with `short` becomes `int` because `+` does so." | Specifically for numeric `?:`, the result is `short`. |
| "Two `Byte` branches produce `byte`." | If both have type `Byte`, the expression has type `Byte`; mixing with a primitive behaves differently. |
| "The non-running branch is still unboxed." | The unselected branch is not evaluated at runtime, though a `Boolean` condition must be unboxed first and the selected branch may need unboxing. |
| "`null` is safe because Java automatically picks the other branch." | The condition determines the branch; if a `null` wrapper requiring unboxing is selected, `NullPointerException` occurs. |
| "The result type is chosen from the variable on the left." | Numeric conditional is a standalone expression; its type is determined from the branches. |
| "`long` with `float` loses no data because both have many bits." | Converting `long` to `float` can round / lose precision. |

## 13. Process for reading a numeric `?:` expression

When encountering `condition ? x : y`:

1. Verify `condition` has type `boolean` or `Boolean`; for `Boolean`, note the `null` case.
2. Determine the **static types** of `x` and `y`, not just the values they currently hold.
3. Check whether they have the same type or a matching primitive-wrapper pair.
4. Check for the `byte`/`Byte` with `short`/`Short` exception.
5. Check whether one branch is `byte`/`short`/`char` (or its wrapper) and the other is an **in-range `int` constant**.
6. Otherwise, apply numeric promotion to determine the common type.
7. Verify the conversion from the chosen branch to the result type: could there be numeric precision loss or `null` unboxing?
8. Finally, check whether that expression type is assignable to the target variable; if not, choose a wide enough target type or check/cast explicitly.

### Self-check exercises

Assume:

~~~java
boolean flag = true;
byte b = 5;
short s = 300;
char c = 'A';
int ordinary = 5;
final int fixed = 5;
Byte boxed = Byte.valueOf((byte) 5);
~~~

This is a shared initialization snippet for the questions, not a complete class.

1. What is the type of `flag ? b : s`?
2. What is the type of `flag ? b : 5`?
3. What is the type of `flag ? b : ordinary`, even though `ordinary` is currently 5?
4. What is the type of `flag ? b : fixed`?
5. What is the type of `flag ? c : s`?
6. Is the type of `flag ? boxed : 5` `Byte`, `byte`, or `int`?
7. What is the type of `flag ? b : 500`?
8. If `Byte missing = null;`, what exception can `true ? missing : 5` throw?
9. Write the result type of `flag ? 5L : 2.5f`. Is every `long` value guaranteed to convert to that type accurately?
10. If `flag` is set to `true`, does the expression `flag ? b : someMethod()` invoke `someMethod()`? Does the compiler still check the type of the `someMethod()` call?

**Answer hints:** (1) `short`. (2) `byte`. (3) `int`. (4) `byte` because `fixed` is a constant variable. (5) `int`. (6) `byte`. (7) `int`. (8) `NullPointerException` when unboxing the selected wrapper. (9) `float`; converting `long` to `float` can lose precision. (10) Not invoked at runtime; the compiler still checks both branches' types.

## 14. Specification source and takeaway

The rules above are described in the **Java Language Specification**, section **15.25 — Conditional Operator `? :`**, specifically **15.25.2 — Numeric Conditional Expressions**:  
[Java Language Specification §15.25](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25)

**Takeaway:** `?:` **evaluates only one branch at runtime**, yet **the type of the entire expression is inferred from both branches at compile time**. For numeric types, remember the `byte`/`short` exception, in-range `int` constants for narrow types, wrappers, and unboxing; those exceptions explain why the type of `?:` is not always the type of addition on the same operands.