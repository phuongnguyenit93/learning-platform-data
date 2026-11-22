# Result Type of Conditional Expressions and Possible Conversions — Java 17+

## 1. The `?:` Operator Does More Than Pick One of Two Values

A conditional expression (commonly called the ternary operator) has the syntax:

~~~java
condition ? whenTrue : whenFalse
~~~

Java **evaluates `condition` first**, then **evaluates only the selected branch**. At the same time, the compiler determines **the type of the entire expression** according to Java's rules: that type does not necessarily match the type of the value in the branch that executes.

~~~java
boolean chooseFirst = true;
double value = chooseFirst ? 10 : 2.5;

System.out.println(value); // 10.0
~~~

The `10` branch is an `int` literal, and the `2.5` branch is a `double` literal. Because this is a **numeric conditional expression**, Java infers the result type `double` and converts 10 to `10.0`. The fact that the `2.5` branch **does not execute** does not prevent its type from affecting the overall type.

**Distinguish three questions:**

1. **Which branch executes?** Depends on the boolean result of `condition`.
2. **What is the expression type?** Governed by compile-time typing rules; requires examining both branches and sometimes the target context.
3. **Are there any conversions?** May include numeric promotion, special narrowing, boxing/unboxing, or reference conversion.

## 2. Three Categories of Conditional Expressions

Java classifies `?:` based on the types of its two branches:

| Category | Branches 2 and 3 | Example | Characteristics |
|---|---|---|---|
| **Boolean conditional** | Matching `boolean`/`Boolean` | `flag ? true : false` | Logical result; may unbox wrappers |
| **Numeric conditional** | Two numeric types or compatible numeric wrappers | `flag ? 1 : 2L` | Has numeric type selection and conversion rules |
| **Reference conditional** | Suitable reference/null cases | `flag ? "OK" : null` | Can undergo **target typing** in assignment/call contexts |

Java 17 defines detailed rules for specific pairs of types; **you cannot always say "the `?:` operator picks the larger type"**. For `byte`/`short` and `int` constants, there is an important exception. For reference types, the target context can also determine whether the expression is valid.

~~~mermaid
flowchart TD
    A["condition ? expr1 : expr2"] --> B{"Are both branches boolean/Boolean?"}
    B -- "Yes" --> C["Boolean conditional expression"]
    B -- "No" --> D{"Are both branches compatible numeric types?"}
    D -- "Yes" --> E["Numeric conditional expression"]
    D -- "No" --> F["Reference conditional expression"]
    C --> G["Check branch selection and possible unboxing"]
    E --> H["Check numeric promotion/special narrowing"]
    F --> I["Check reference types and target typing"]
~~~

**The first operand (condition)** must have type `boolean` or an unboxable `Boolean`. Java does not treat a non-zero number as true:

~~~java
// int number = 1;
// int result = number ? 10 : 20; // COMPILE ERROR: condition is not boolean
~~~

## 3. Only the Selected Branch Is Evaluated

~~~java
static int trace(String label, int value) {
    System.out.println("evaluated " + label);
    return value;
}
~~~

If:

~~~java
boolean flag = true;
int selected = flag
        ? trace("true", 7)
        : trace("false", 9);

System.out.println(selected);
~~~

**Expected stdout:**

~~~text
evaluated true
7
~~~

The false branch **does not run**: no method call, no side effect, and no exception from that branch.

However, the compiler still **type-checks both branches**. A branch that never runs for the sample data still cannot contain an invalidly typed expression:

~~~java
// int wrong = true ? 10 : "text";
// Cannot assign this reference conditional to int under Java typing rules.
~~~

**Note:** skipping a branch at runtime is not the same as excluding a branch from compile-time type checking.

## 4. Common Numeric Types: `int`, `long`, `float`, `double`

With two common numeric branches:

~~~java
boolean flag = true;

var first = flag ? 10 : 20;    // int
var second = flag ? 10 : 20L;  // long
var third = flag ? 10 : 2.5;   // double
var fourth = flag ? 10 : 2.5f; // float
~~~

| Both branches | Expression type | Value when `flag == true` |
|---|---|---|
| `10` and `20` | `int` | `10` |
| `10` and `20L` | `long` | `10L` |
| `10` and `2.5f` | `float` | `10.0f` |
| `10` and `2.5` | `double` | `10.0` |

For these type pairs, appropriate numeric conversion makes both branches compatible with the result type.

**Do not infer the expression type from the receiving variable's type:** the example below has two distinct steps:

~~~java
double d = flag ? 1 : 2;
~~~

`flag ? 1 : 2` itself is a numeric expression of type **`int`**; the assignment afterward widens the value to `double`. By contrast, `flag ? 1 : 2.0` has type **`double` directly at the conditional expression**.

## 5. Special Exception: `byte`/`short` and In-Range `int` Constants

Java has a special rule when one branch is `byte`, `short`, or the corresponding wrapper, and the other branch is a **constant `int` representable in the smaller type**.

~~~java
boolean flag = true;
byte small = 10;

var within = flag ? small : 100;  // byte
var outside = flag ? small : 1000; // int
~~~

- `100` is a **constant `int`** within the `byte` range (-128..127), so the expression type of `within` is `byte`.
- `1000` is outside the `byte` range, so the `outside` expression uses type `int`.

Checking via overloading:

~~~java
static String kind(byte value) { return "byte"; }
static String kind(int value) { return "int"; }

System.out.println(kind(flag ? small : 100));  // byte
System.out.println(kind(flag ? small : 1000)); // int
~~~

**Do not confuse literals with variables:** even when an `int` variable currently holds 100, a normal `flag ? small : intVariable` expression has type `int`, because a variable's value does not become a *constant expression* merely by holding 100.

~~~java
int intVariable = 100;
System.out.println(kind(flag ? small : intVariable)); // int
~~~

This detail proves that type selection is a **compile-time rule**, independent of the branch value chosen at runtime.

## 6. Converting Large Integers to Floating-Point Can Lose Precision

~~~java
long exact = 9_007_199_254_740_993L; // 2^53 + 1
boolean flag = true;

double result = flag ? exact : 0.5;
System.out.println(result); // 9.007199254740992E15
~~~

The entire conditional expression here has type `double`. When the `long` branch is selected, `exact` must be converted to `double`; the integer **2^53 + 1** is not exactly representable in binary64, so it is rounded to **2^53**.

**Consequence:** even though the `0.5` branch does not run, its `double` type still causes conversion of the large integer in the true branch. If an exact ID/`long` must be preserved, do not mix it with floating-point numbers just to write a single `?:` expression.

### Type conversion does not fix an operation already performed inside a branch

~~~java
boolean flag = true;
double quotient = flag ? (3 / 2) : 2.5;

System.out.println(quotient); // 1.0
~~~

`3 / 2` **already performed integer division**, returning 1, before being converted to the `double` type of the whole expression. It **does not become 1.5** just because the other branch is `double`.

If you need the fractional part, convert **before dividing**:

~~~java
double quotient = flag ? (3.0 / 2) : 2.5;
System.out.println(quotient); // 1.5
~~~

## 7. Numeric Wrappers: Unboxing Can Occur

Important example with `Integer` and `int`:

~~~java
Integer boxed = 7;
int primitive = 9;
boolean flag = true;

int selected = flag ? boxed : primitive;
System.out.println(selected); // 7
~~~

In this pair of types, the numeric conditional expression produces type `int`; when the `boxed` branch is chosen, Java **unboxes `Integer`** to obtain the primitive value.

If the wrapper is null:

~~~java
Integer missing = null;
// int result = true ? missing : 9;
// At runtime: NullPointerException from unboxing missing.
~~~

One crucial point: **only the selected branch is evaluated and undergoes the required runtime conversion**. In the following example, the null wrapper branch is not chosen, so no error occurs:

~~~java
Integer missing = null;
int safe = true ? 9 : missing;
System.out.println(safe); // 9
~~~

Do not assume a null branch will always throw NPE just because the compiler knows that branch might require unboxing. It must actually be selected and used at runtime.

## 8. Two Different Numeric Wrappers Can Also Yield a Primitive Type

~~~java
Integer whole = 7;
Double fraction = 2.5;
boolean flag = true;

Number chosen = flag ? whole : fraction;
System.out.println(chosen); // 7.0
~~~

With `Integer` and `Double`, this is a **numeric conditional**: Java applies unboxing and numeric promotion rules to get type `double`. When assigned to `Number`, the result can be **boxed into a `Double`**. Do not assume that picking `whole` guarantees the resulting object is an `Integer`.

If you need to preserve each branch's specific object type, design the **reference types** and conversion explicitly rather than relying on `?:` inference. In some cases, splitting into an `if/else` assigning to `Number` is easier to test.

This is one reason not to write `?:` expressions mixing multiple wrapper types when object-type semantics matter.

## 9. Boolean Conditional Expressions and Nullable `Boolean`

~~~java
boolean flag = true;
boolean selected = flag ? true : false;
System.out.println(selected); // true
~~~

An expression with two `boolean` branches has type `boolean`; if combined with `Boolean`, unboxing may occur.

~~~java
Boolean boxed = null;
boolean flag = true;

// boolean result = flag ? boxed : false;
// If the boxed branch is chosen, it throws NullPointerException.
~~~

Additionally, **the condition itself** can also be `Boolean`:

~~~java
Boolean condition = null;
// int value = condition ? 1 : 2;
// NullPointerException when unboxing condition to choose a branch.
~~~

**Error distinction:**
- Null condition → fails when **determining the branch**.
- Null wrapper branch → fails when **the selected branch needs unboxing**.
- Unselected branch → is not evaluated and does not itself throw NPE.

If `Boolean` data is nullable, define a clear `null` policy—for example, using `Boolean.TRUE.equals(condition)` when only true is accepted.

## 10. Reference Expressions and Target Typing

Not every `?:` uses numeric promotion. When both branches belong to the reference category, Java can use a **target type** in an assignment or argument-passing context.

~~~java
boolean flag = true;

String label = flag ? "ready" : null;
System.out.println(label); // ready
~~~

A clearer example with generics:

~~~java
java.util.List<String> names = flag
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();

names.add("Java");
System.out.println(names.get(0)); // Java
~~~

Both reference branches are checked against the **target type `List<String>`**; the `new ...<>()` expressions also receive the appropriate type context. Java does not need a numeric "type promotion" here.

With branches of different reference types:

~~~java
Object result = flag ? "ready" : Integer.valueOf(7);
System.out.println(result.getClass().getSimpleName()); // String
~~~

This is a **reference conditional expression** with target type `Object`. Only the selected branch creates a runtime value, but both branches must be convertible in the target context.

**Be careful with `var`:** when initializing a variable with `var x = flag ? expr1 : expr2;`, there is no pre-declared variable type acting as a target type for subexpressions like in the `List<String>` example above. The compiler must determine the type in a standalone context; with differing reference branches, it may infer a common supertype or a complex intersection type. When an API type needs to be exact and readable, **declare the target type explicitly**.

## 11. `null` Does Not Mean Every `?:` Expression Is Nullable

With references:

~~~java
String text = true ? null : "backup";
System.out.println(text == null); // true
~~~

The true branch is null; the result type can still fit `String` via the reference context.

However, with a numeric conditional mixing a primitive and a wrapper:

~~~java
Integer nullable = null;
// int result = true ? nullable : 5;
~~~

This case requires unboxing `nullable`, so it is **not the same** as a reference conditional returning null normally. Do not conclude "one branch is null so the operator will return null without error" before identifying the **conditional expression category**.

**API contract:** if null is a valid state, explicitly design a reference/Optional output; if null is unacceptable, validate before using.

## 12. Precedence, Associativity, and Nested Conditions

The `?:` operator is **right-associative**:

~~~java
int score = 75;
String grade = score >= 90 ? "A"
        : score >= 70 ? "B"
        : "C";

System.out.println(grade); // B
~~~

Grouped as:

~~~java
String grade = score >= 90
        ? "A"
        : (score >= 70 ? "B" : "C");
~~~

If a deeply nested expression has mixed branch types, both **type selection** and **branch selection order** become hard to follow. Prefer `if/else if/else` when there are multiple conditions, error checks, or lengthy business logic.

Parentheses clarify grouping, **but do not automatically make incompatible branch type pairs compatible**, nor do they alter numeric promotion rules.

## 13. When to Use `if/else` Instead of `?:`?

Use `?:` when both branches are **two short values with predictable types**:

~~~java
String status = active ? "ON" : "OFF";
int timeout = strict ? 100 : 300;
~~~

Consider `if/else` when:
- A branch has side effects, calls multiple methods, or can throw errors.
- Both branches contain different numeric/wrapper types needing deliberate conversion.
- Null handling, overflow, precision loss, or rounding policies are needed.
- Nested `?:` branches become hard to review.

Example making conversion explicit:

~~~java
Number selected;
if (flag) {
    selected = whole;    // Preserves the Integer reference value
} else {
    selected = fraction; // Preserves the Double reference value
}
~~~

This differs in **preserved object type** from the numeric conditional `flag ? whole : fraction` in certain situations. The right choice depends on the desired contract.

## 14. Common Mistakes Table

| Misconception | Reality in Java | How to handle |
|---|---|---|
| `?:` always has the type of the running branch | Type is determined by compile-time rules | Consider both branches and target type |
| `true ? 10 : 2.5` has type int | It has type `double` | Account for numeric promotion properly |
| `double d = flag ? 1 : 2;` makes `?:` double | The inner numeric conditional is int; widening happens on assignment | Separate expression type from receiving variable type |
| `byte b; flag ? b : 100` must be int | Constant int 100 fits in byte → result is byte | Know the constant-expression exception |
| `flag ? b : intVar` is byte when intVar holds 100 | A plain intVar is not a compile-time constant | Type is normally int |
| `long` branch always stays exact when paired with double | Widening long→double can round | Keep matching integer types if precision matters |
| `flag ? (3/2) : 2.5` yields 1.5 | Integer division 3/2 already produced 1 | Use 3.0/2 beforehand |
| Null wrapper is always safe because another branch exists | Selected branch may unbox null | Guard null or design a reference output |
| Unselected branch still runs for type conversion | Only the selected branch is evaluated at runtime | Separate compile-time typing from runtime evaluation |
| Null `Boolean` used as condition means false | Unboxing null throws NPE | Use an explicit null policy |
| `Integer`/`Double` preserves whichever wrapper is picked | Numeric conditional can unbox/promote and re-box | If object identity matters, use reference if/else |
| `var` always infers types like an explicit target | No pre-declared target type like `List<String>` exists | Declare the type when it matters |
| Deeply nested `?:` is always easier than if/else | Hard to reason about types and branch order | Split into if/else or a clearly named method |

## 15. Complete Java 17 Program

Create a file named exactly **`ConditionalExpressionTypeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public final class ConditionalExpressionTypeDemo {
    private ConditionalExpressionTypeDemo() {}

    static String kind(byte value) { return "byte"; }
    static String kind(int value) { return "int"; }
    static String kind(long value) { return "long"; }
    static String kind(float value) { return "float"; }
    static String kind(double value) { return "double"; }

    static int trace(String label, int value) {
        System.out.println("evaluated " + label);
        return value;
    }

    public static void main(String[] args) {
        boolean choose = true;

        System.out.println("numeric int="
                + kind(choose ? 10 : 20));
        System.out.println("numeric long="
                + kind(choose ? 10 : 20L));
        System.out.println("numeric float="
                + kind(choose ? 10 : 2.5f));
        System.out.println("numeric double="
                + kind(choose ? 10 : 2.5));

        byte small = 10;
        int regularInt = 100;
        System.out.println("byte constant="
                + kind(choose ? small : 100));
        System.out.println("byte too large="
                + kind(choose ? small : 1000));
        System.out.println("byte int variable="
                + kind(choose ? small : regularInt));

        double widenedTarget = choose ? 1 : 2;
        System.out.println("widened assignment=" + widenedTarget);

        long exact = 9_007_199_254_740_993L;
        double rounded = choose ? exact : 0.5;
        System.out.println("long promoted to double=" + rounded);

        double lateDivision = choose ? (3 / 2) : 2.5;
        double earlyDivision = choose ? (3.0 / 2) : 2.5;
        System.out.println("integer division then widen=" + lateDivision);
        System.out.println("floating division=" + earlyDivision);

        int selected = choose
                ? trace("true", 7)
                : trace("false", 9);
        System.out.println("selected=" + selected);

        Integer boxed = 7;
        int primitive = 9;
        System.out.println("int unboxed=" + (choose ? boxed : primitive));

        Integer missing = null;
        int safe = choose ? 9 : missing;
        System.out.println("unselected null=" + safe);
        try {
            int broken = choose ? missing : 9;
            System.out.println(broken);
        } catch (NullPointerException ex) {
            System.out.println("selected null=NullPointerException");
        }

        Integer whole = 7;
        Double fraction = 2.5;
        Number numericWrapper = choose ? whole : fraction;
        System.out.println("wrapper value=" + numericWrapper);
        System.out.println("wrapper class="
                + numericWrapper.getClass().getSimpleName());

        Number referenceWrapper;
        if (choose) {
            referenceWrapper = whole;
        } else {
            referenceWrapper = fraction;
        }
        System.out.println("reference class="
                + referenceWrapper.getClass().getSimpleName());

        Boolean boxedCondition = null;
        try {
            int number = boxedCondition ? 1 : 2;
            System.out.println(number);
        } catch (NullPointerException ex) {
            System.out.println("null condition=NullPointerException");
        }

        String text = choose ? "ready" : null;
        System.out.println("reference string=" + text);
        String nullable = choose ? null : "fallback";
        System.out.println("reference null=" + (nullable == null));

        Object objectValue = choose ? "ready" : Integer.valueOf(7);
        System.out.println("target object class="
                + objectValue.getClass().getSimpleName());

        List<String> list = choose
                ? new ArrayList<>()
                : new LinkedList<>();
        list.add("Java");
        System.out.println("target typed list=" + list.get(0));

        int score = 75;
        String grade = score >= 90 ? "A"
                : score >= 70 ? "B"
                : "C";
        System.out.println("nested condition=" + grade);
    }
}
~~~

**Bash (Linux/macOS)** — terminal in the directory containing the file, JDK 17+ required:

~~~bash
javac --release 17 -encoding UTF-8 ConditionalExpressionTypeDemo.java
java -cp . ConditionalExpressionTypeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ConditionalExpressionTypeDemo.java
java -cp . ConditionalExpressionTypeDemo
~~~

No Maven, Gradle, or external libraries needed.

### Exact expected stdout

~~~text
numeric int=int
numeric long=long
numeric float=float
numeric double=double
byte constant=byte
byte too large=int
byte int variable=int
widened assignment=1.0
long promoted to double=9.007199254740992E15
integer division then widen=1.0
floating division=1.5
evaluated true
selected=7
int unboxed=7
unselected null=9
selected null=NullPointerException
wrapper value=7.0
wrapper class=Double
reference class=Integer
null condition=NullPointerException
reference string=ready
reference null=true
target object class=String
target typed list=Java
nested condition=B
~~~

**Key points of the stdout explained:**

1. The four `numeric ...` lines confirm that numeric conditional expressions get a common type decided by Java.
2. `byte constant=byte`, `byte too large=int`: in-range `int` constants have a special rule; a regular `int` variable does not qualify.
3. `widened assignment=1.0`: the inner `?:` has type int; widening happens at assignment to the double variable.
4. `long promoted to double`: a large `long` gets rounded when paired into an expression of type `double`.
5. `integer division then widen=1.0`: outer conversion does not turn integer division into floating-point division.
6. No `evaluated false`: Java executes only the true branch.
7. `selected null` throws NPE due to unboxing the selected branch; `unselected null=9` produces no error.
8. `wrapper class=Double` vs. `reference class=Integer`: numeric conditional differs from directly assigning each wrapper to `Number`.
9. `null condition` throws NPE when evaluating the `Boolean` condition.
10. `target typed list=Java` demonstrates reference expressions can use target type `List<String>`; `nested condition=B` is due to `?:` right-associativity.

## 16. Exercises with Answers

### Exercise A — determining expression type

~~~java
boolean flag = true;
var result = flag ? 3 : 4L;
System.out.println(result);
~~~

**Answer:** `result` has type **`long`**, stdout is `3`. `var` does not make the expression dynamically typed at runtime.

### Exercise B — `int` constant with `byte`

~~~java
byte b = 5;
System.out.println(kind(true ? b : 100));
System.out.println(kind(true ? b : 200));
~~~

**Answer:**

~~~text
byte
int
~~~

The `kind` overload is defined in the full program. 100 is within the byte range, while 200 is not.

### Exercise C — unboxing a null branch

~~~java
Integer missing = null;
int value = true ? 1 : missing;
System.out.println(value);
~~~

**Answer:** `1`, no NPE because the `missing` branch is not selected. If `true` is changed to `false`, the null `Integer` branch is chosen and requires unboxing → `NullPointerException`.

### Exercise D — integer division or floating-point division?

~~~java
boolean flag = true;
double result = flag ? (7 / 2) : 2.5;
System.out.println(result);
~~~

**Answer:** `3.0`. `7 / 2` occurs inside the branch with integer types, truncating the fractional part before converting to double.

### Exercise E — preserving object or numeric value?

~~~java
Integer a = 7;
Double b = 2.5;
Number result = true ? a : b;
System.out.println(result.getClass().getSimpleName());
~~~

**Answer:** `Double`. The numeric conditional performs unboxing/numeric promotion and then re-boxes when assigning to Number, rather than preserving the Integer wrapper just because the true branch chose a.

### Exercise F — target typing with references

~~~java
java.util.List<String> names = true
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();
names.add("JDK 17");
System.out.println(names.get(0));
~~~

**Answer:** `JDK 17`. The reference expression receives target type `List<String>`, allowing both branches to be checked in that context.

## 17. Checklist and Conclusion

- [ ] Understand the syntax `condition ? whenTrue : whenFalse`.
- [ ] Know that only **the selected branch** is evaluated at runtime.
- [ ] Understand that the compiler inspects both branches for type checking.
- [ ] Distinguish boolean, numeric, and reference conditional expressions.
- [ ] Know numeric promotion when mixing `int`, `long`, `float`, `double`.
- [ ] Know the special rule for `byte`/`short` with in-range `int` constants.
- [ ] Distinguish the type of `?:` from conversion on assignment to a variable.
- [ ] Understand `long → double` can lose precision; outer conversion does not fix already-evaluated integer division.
- [ ] Recognize unboxing and NPE on a selected wrapper branch.
- [ ] Know a null `Boolean` used as a condition can throw NPE.
- [ ] Understand reference conditionals can undergo target typing, and `var` does not replace explicit type declarations when API clarity matters.
- [ ] Understand right-associativity of `?:` and avoid overly deep nesting.
- [ ] Compile `ConditionalExpressionTypeDemo.java` on Java 17+ and verify the exact stdout.

**Conclusion:** The ternary operator `?:` in Java 17+ does not simply "return the exact type of whichever branch runs". Its type is decided **at compile time**, sometimes relying on a **target type**, while runtime evaluates only **the selected branch**. Numeric promotion, special narrowing, and boxing/unboxing can yield unintuitive results or runtime errors. Use `?:` for short value selections with clear matching types; when mixing multiple types or when conversion policies matter, prefer `if/else` and explicit conversions.
