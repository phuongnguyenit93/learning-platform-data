# Ordering Cases by Specificity in Java Pattern Matching

## 1. Why Does Case Order Determine Whether a Program Is Correct?

When writing a `switch` with pattern matching in Java 21, multiple `case` labels can match **a single value**. For example, the string `"Java"` is simultaneously a `String`, a `CharSequence`, and an `Object`. The integer `Integer 8` is simultaneously an `Integer`, a `Number`, and an `Object`.

If labels are used in an improper order:

~~~java
switch (value) {
    case Number n -> System.out.println("Number");
    case Integer i -> System.out.println("Integer"); // dominance ERROR
    default -> System.out.println("Other");
}
~~~

the compiler rejects it because every `Integer` has already been matched by the preceding `case Number n`. The `Integer` label can never be selected. This phenomenon where a preceding label subsumes a following label is called **dominance**.

The focus of this lesson is **ordering cases from specific to general** so that the program both compiles and expresses the intended business logic. With Java 21, you can remember:

> **Specific constants → patterns with specific guards → unguarded patterns in type hierarchy order from subtype to supertype → catch-all fallback.** Handle `null` explicitly when needed.

This is a **readability and organization rule**, not an automatic algorithm that ranks the "specificity" of every Java expression. In particular, the compiler cannot always prove the subsumption of two dynamic guards; code may **compile yet take an unintended branch at runtime**.

After this lesson, you will be able to:

- Distinguish **runtime case-matching order** from **compile-time dominance checking**.
- Correctly order subtypes before broad supertypes/interfaces, constant labels before type patterns, and `when`-guarded labels before general labels.
- Understand why `case Number n when n > 0` does not automatically cause a following `case Integer i` to be dominated.
- Recognize cases where a dynamic guard "captures" the value of a following constant label even though the compiler allows it.
- Order record patterns, sealed hierarchies, and handle `null` and `default`.
- Write and test Java 21 code to prevent ordering errors and logic bugs.

**Version:** pattern matching for `switch` and record patterns have been stable since **Java 21**. All complete programs in this lesson use `javac --release 21` and do not require enabling preview features.

## 2. Two Separate Questions: Matching Order and Dominance

### 2.1. Matching Order: How Does Java Test Labels?

Java selects the matching case according to switch block rules; pattern labels are tested in order of appearance. For a guarded label:

~~~java
case String s when s.length() > 4 -> "LONG";
~~~

Java evaluates `s.length() > 4` **only after** the selector value matches `String s`. If the guard returns `false`, Java can try the next matching label. Once an arrow rule `->` is selected, there is no fall-through to other rules.

A sensible example:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "TEXT";
~~~

A blank string is handled by the first label; remaining strings are handled by the second label.

### 2.2. Dominance: The Compiler Rejects Unreachable Labels

A subsequent `case` label is **dominated** if, according to Java's dominance rules, a preceding label already subsumes its cases. In that situation, the compiler reports an error, typically with the message:

~~~text
error: this case label is dominated by a preceding case label
~~~

For example, `case CharSequence cs` before `case String s` is invalid because every `String` implements the `CharSequence` interface.

Dominance is a **language rule checked at compile time**; it is not the result of running a few test values. Conversely, there are complex guard condition domains where the compiler cannot prove subsumption. Valid code can still take a broad branch before a specific branch that follows it.

### 2.3. "Specificity" Is a Coding Strategy, Not Automatic Prioritization

Java **does not automatically sort cases from subtype to supertype** for you. The author sets the order of the labels. If business logic requires "positive integers first, remaining integers next, floating-point numbers after that," you must place the cases in that exact order.

Do not assume Java will automatically pick the "most specific" case intuitively. A preceding `case Number n` will still block `case Integer i`, resulting in a dominance error, rather than Java prioritizing `Integer` on its own.

## 3. A Practical Ordering Formula

When labels may overlap, apply this reference order:

1. **Constant values needing special handling:** `case 1`, `case "OK"`, enum constants, when appropriate for the selector type.
2. **Patterns with specific guards:** `case String s when s.isBlank()`, `case Integer n when n > 0`.
3. **Unguarded specific subtype/record patterns:** `case Integer n`, `case String s`, `case Circle(int radius)`.
4. **Broader supertype/interface patterns:** `case Number n`, `case CharSequence cs`, `case Shape s`.
5. **Catch-all fallback:** `case Object o` or `default` when valid and needed.

`case null` does not belong to a normal subtype tree. Type patterns such as `String s` or `Object o` do not match `null`; you should handle `null` explicitly, usually placed at the top of the switch for readability. Do not mistake "putting null first" for a mandatory syntax requirement.

**Important caveat:** the order above is only a starting framework. For example, `String` is not a subtype of `Number`; these two cases do not subsume each other, so they can be ordered according to classification goals. When type relationships or guards cause branches to intersect, verify specifically with the compiler and runtime tests.

## 4. Subtype Before Supertype: The Most Important Rule

Consider these relationships:

~~~text
Object
├── Number
│   ├── Integer
│   ├── Long
│   └── Double
└── CharSequence (interface)
    ├── String
    └── StringBuilder
~~~

The diagram only describes the relevant inheritance/implementation relationships; `StringBuilder` is not a subclass of `String`, rather both implement `CharSequence`.

Two **incorrect** orderings:

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER"; // Dominated by Number
~~~

~~~java
case CharSequence cs -> "SEQUENCE";
case String s -> "STRING"; // Dominated by CharSequence
~~~

These are illustrative snippets **intentionally written not to compile**.

Correct orderings:

~~~java
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
~~~

~~~java
case String s -> "STRING";
case CharSequence cs -> "SEQUENCE";
~~~

With `value = Integer.valueOf(10)`, the `Integer` case is selected. With `value = Double.valueOf(2.5)`, `Integer` does not match and the `Number` case is selected.

**Specificity by type relationship** is different from class name length or declaration order in code. To analyze it, ask: "Will every object matching pattern B definitely match pattern A?" If A precedes B and always covers B, the order is usually wrong.

Interfaces and records also require attention: a class can implement multiple unrelated interfaces, so not every pair of interface labels causes dominance with each other. When there is no subsumption relationship, the order can still affect behavior for a class implementing **both** interfaces. That is a business decision that needs testing, not always a compile-time error.

## 5. Same Type: Specific Guards Before Unguarded Patterns

When multiple cases share `String s`, specific conditions must precede the general branch:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s when s.length() >= 5 -> "LONG";
case String s -> "OTHER_STRING";
~~~

- A whitespace-only string matches the `isBlank()` guard first.
- A non-blank string with at least 5 characters can match the `LONG` branch.
- Other strings fall through to the unguarded `case String s`.

Reversing them as follows is a **compile error**:

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK"; // Dominated
~~~

The unguarded label catches all `String` objects, so the guarded label after it can never be selected.

A subtle point is that two dynamic guards do not necessarily have an obvious subsumption relationship for the compiler to check. For example:

~~~java
case String s when s.length() >= 3 -> "AT_LEAST_THREE";
case String s when s.startsWith("A") -> "STARTS_A";
case String s -> "OTHER";
~~~

This is valid syntax in principle within a corresponding switch, yet the string `"Alice"` will enter the length case first, **not** the `startsWith("A")` case. If business logic wants to prioritize the `A` prefix, you must swap the order of the two guards. The right way to verify this is to write tests for values in the **intersection of both conditions**, not just values matching a single guard.

## 6. Combined Program: Specific Patterns First, General Patterns Later

Save as `SpecificityOrderDemo.java`:

~~~java
public class SpecificityOrderDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s;
            case String s -> "TEXT:" + s;
            case Integer n when n > 0 -> "POS_INT:" + n;
            case Integer n -> "INT:" + n;
            case Number n -> "NUMBER:" + n;
            case CharSequence cs -> "CHAR_SEQUENCE:" + cs.length();
            case Object o -> "OBJECT";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("Java!"));
        System.out.println(classify("Hi"));
        System.out.println(classify(8));
        System.out.println(classify(-2));
        System.out.println(classify(2.5));
        System.out.println(classify(new StringBuilder("abc")));
        System.out.println(classify(new Object()));
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 SpecificityOrderDemo.java
java SpecificityOrderDemo
~~~

Exact output:

~~~text
NULL
BLANK
LONG_TEXT:Java!
TEXT:Hi
POS_INT:8
INT:-2
NUMBER:2.5
CHAR_SEQUENCE:3
OBJECT
~~~

Tracing the case order:

| Value | Selected Case | Reason |
| --- | --- | --- |
| `null` | `case null` | Type patterns do not match null |
| `"   "` | `String s when s.isBlank()` | Special condition placed first in the String group |
| `"Java!"` | `String s when s.length() >= 5` | Blank guard is false, length guard is true |
| `"Hi"` | `String s` | Both String guards are false |
| `8` | `Integer n when n > 0` | Positive Integer branch precedes general Integer |
| `-2` | `Integer n` | Positive-number guard is false |
| `2.5` | `Number n` | This is a Double, not an Integer |
| `new StringBuilder("abc")` | `CharSequence cs` | Not a String, but implements CharSequence |
| `new Object()` | `Object o` | Does not match any preceding labels |

Two points to distinguish:

- `case Number n` is broader than `case Integer n`, so it must appear **after** the Integer cases if you want separate handling.
- `case CharSequence cs` is broader than `case String s`, so it must appear after the String cases. The relative order between `Number` and `CharSequence` in this example does not cause dominance because the two branches have no direct subsumption relationship.

**Exhaustiveness:** `case Object o` is a pattern covering all **non-null Object** values of the selector; `case null` handles the null value. Therefore, the example does not need an extra `default`. Do not add a redundant `default` label after a general `Object o` pattern if the compiler determines it already covers all remaining cases.

## 7. Specific Constants Before Guarded Patterns: Both Compile Errors and Logic Errors

### 7.1. A General Pattern Can Dominate a Constant

Suppose the selector is `String`:

~~~java
case String s -> "ANY_STRING";
case "OK" -> "EXACT"; // dominance ERROR
~~~

The unguarded `case String s` label already matches every non-null string, including `"OK"`. Thus, the following `case "OK"` is dominated.

Correct form:

~~~java
case "OK" -> "EXACT";
case String s -> "ANY_STRING";
~~~

### 7.2. Dynamic Guards Do Not Necessarily Dominate a Constant Under Compiler Rules

Unlike an unguarded label, a label like:

~~~java
case Integer i when i > 0 -> "POSITIVE";
~~~

has a dynamic condition expression `i > 0`. Most dynamic guards **are not treated as unconditional dominance** over a following constant label. Therefore, the snippet:

~~~java
case Integer i when i > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer i -> "OTHER";
~~~

can **compile**, yet for the value `1`, the first guard is already true and the `case 1` label **is not selected**. This is a **logic error in ordering**, not a dominance error caught by the compiler.

A safe rule of thumb from Oracle's documentation: **specific constants first, guarded patterns next, unguarded patterns last**. If your business priority is genuinely different, express it intentionally and test it explicitly.

### 7.3. Verification Program

Save as `ConstantGuardOrderDemo.java`:

~~~java
public class ConstantGuardOrderDemo {
    static String good(Integer value) {
        return switch (value) {
            case 1 -> "ONE";
            case -1 -> "MINUS_ONE";
            case Integer i when i > 0 -> "POSITIVE";
            case Integer i -> "OTHER_INTEGER";
            case null -> "NULL";
        };
    }

    static String legalButSurprising(Integer value) {
        return switch (value) {
            case Integer i when i > 0 -> "POSITIVE";
            case 1 -> "ONE";
            case Integer i -> "OTHER_INTEGER";
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println("good(1)=" + good(1));
        System.out.println("good(2)=" + good(2));
        System.out.println("good(-1)=" + good(-1));
        System.out.println("good(0)=" + good(0));
        System.out.println("good(null)=" + good(null));
        System.out.println("surprising(1)=" + legalButSurprising(1));
    }
}
~~~

~~~bash
javac --release 21 ConstantGuardOrderDemo.java
java ConstantGuardOrderDemo
~~~

Output:

~~~text
good(1)=ONE
good(2)=POSITIVE
good(-1)=MINUS_ONE
good(0)=OTHER_INTEGER
good(null)=NULL
surprising(1)=POSITIVE
~~~

The `good` method prioritizes the two constant values `1` and `-1` before the positive-number guard, and then handles other integers. The `legalButSurprising` method shows that the `case 1` label can be bypassed **at runtime**, even though the compiler reports no dominance.

**Exception to remember:** a guard that is the constant expression `true` is treated by the Java 21 JLS as **unguarded** for dominance rules. If you write `case Integer i when true` before `case 1`, the compiler reports dominance; this is not a normal dynamic guard. A guard that is the constant expression `false` is not accepted in a case label.

## 8. A Broad Guard on a Supertype Does Not Necessarily Dominate a Subtype Pattern

An interesting example:

~~~java
case Number n when n.intValue() > 0 -> "POSITIVE";
case Integer i -> "OTHER_INTEGER";
case Number n -> "OTHER_NUMBER";
~~~

The first label uses the broad `Number`, but it has a dynamic guard. If the guard is false, execution can reach the `Integer` label even though the value is still an `Integer` object. Therefore, Java **does not automatically** reject this ordering via dominance as it would with an unguarded `case Number n`.

Complete program `GuardDoesNotDominateDemo.java`:

~~~java
public class GuardDoesNotDominateDemo {
    static String classify(Number value) {
        return switch (value) {
            case Number n when n.intValue() > 0 -> "POSITIVE";
            case Integer n -> "OTHER_INTEGER";
            case Number n -> "OTHER_NUMBER";
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(3));
        System.out.println(classify(0));
        System.out.println(classify(-2.5));
        System.out.println(classify(7L));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardDoesNotDominateDemo.java
java GuardDoesNotDominateDemo
~~~

Output:

~~~text
POSITIVE
OTHER_INTEGER
OTHER_NUMBER
POSITIVE
NULL
~~~

For `3`, the guarded `Number` label is selected even though an `Integer` case follows it. For `0`, the guard is false and execution reaches `case Integer n`. This is **valid under Java's rules**, but it can be surprising.

If the program's goal is to classify **Integer before other Numbers** regardless of whether the value is positive or negative, prioritize the Integer case, or place a separate guard on `Integer`. Do not expect the compiler to infer your business intent from guard expressions.

Some guards may throw exceptions or have side effects; changing case order can change how many times a guard is evaluated. When refactoring order, test both the **result values** and **side effects** if guards are not pure.

## 9. Record Patterns and Ordering from Specific Conditions to General

Record patterns allow deconstructing components directly in a case:

~~~java
case Rectangle(int w, int h) when w == h -> "SQUARE";
case Rectangle(int w, int h) -> "RECTANGLE";
~~~

Both labels accept the same `Rectangle` type; the `w == h` guard is a specific condition, so it precedes the unguarded record pattern.

If reversed:

~~~java
case Rectangle(int w, int h) -> "RECTANGLE";
case Rectangle(int w, int h) when w == h -> "SQUARE"; // ERROR
~~~

the compiler rejects the second label because it is dominated by the preceding record pattern.

### Record + Sealed Hierarchy Program

Save `RecordSpecificityDemo.java`:

~~~java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}

public class RecordSpecificityDemo {
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle(int r) when r == 0 -> "POINT";
            case Circle(int r) when r > 0 -> "CIRCLE:" + r;
            case Circle(int r) -> "INVALID_CIRCLE:" + r;
            case Rectangle(int w, int h) when w == h -> "SQUARE:" + w;
            case Rectangle(int w, int h) -> "RECTANGLE:" + w + "x" + h;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(0)));
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Circle(-1)));
        System.out.println(describe(new Rectangle(4, 4)));
        System.out.println(describe(new Rectangle(4, 5)));
    }
}
~~~

~~~bash
javac --release 21 RecordSpecificityDemo.java
java RecordSpecificityDemo
~~~

Exact output:

~~~text
POINT
CIRCLE:3
INVALID_CIRCLE:-1
SQUARE:4
RECTANGLE:4x5
~~~

Explanation:

- `Circle(0)` goes to the record pattern with guard `r == 0`.
- `Circle(3)` goes to the `r > 0` guard.
- `Circle(-1)` fails both guards but still matches the unguarded `Circle(int r)`.
- `Rectangle(4,4)` matches the `w == h` guard and is classified as a square.
- `Rectangle(4,5)` goes to the general Rectangle case.

`Shape` is a sealed interface with two permitted implementations, and the unguarded `Circle`/`Rectangle` branches cover them. Thus, the switch expression is **exhaustive** without needing `default`. This does not prevent `describe(null)` from throwing `NullPointerException` because there is no `case null`.

If you add `case Shape s` before the `Circle` and `Rectangle` record patterns, it will dominate those subtypes and prevent separate handling. With sealed types, specific subtype branches are typically ordered before a general interface/parent branch if one exists.

## 10. Ordering Constant Labels, Interfaces, Object, null, and default

### 10.1. Constants Before Broad Type Patterns

For a `String` selector, if values like `"OK"` or `"ERROR"` need priority, place the constant cases before `case String s`. For an `Integer` selector, if `0` or `1` have special meaning, place the constant labels before the corresponding broad pattern. If you use guards instead, explicitly decide the order between guards and constants.

### 10.2. Interfaces Do Not Necessarily Subsume One Another

`String` is a subtype of `CharSequence`; therefore `CharSequence` before `String` causes dominance. However, if two interfaces `Readable` and `AutoCloseable` have no parent–child relationship, a class can implement both. In that case, the order of the two interface cases can determine how that object is handled, even though the compiler has no direct subtype relationship to treat one pattern as dominating the other.

For unrelated interfaces, place the higher-priority business condition first and add tests for objects that implement both interfaces simultaneously.

### 10.3. The Very Broad Object Pattern

For an `Object` selector:

~~~java
case String s -> "STRING";
case Number n -> "NUMBER";
case Object o -> "OTHER_OBJECT";
~~~

`case Object o` at the end is a general pattern for all remaining **non-null** objects. If you move `case Object o` before the String/Number cases, the compiler reports dominance. Within a switch block that already has such a general pattern, avoid adding duplicate catch-all labels that cause compiler errors.

### 10.4. null Is a Special Case

`null` is not a subtype in the type pattern dispatch model. Java 21 allows:

~~~java
case null -> "NULL";
case String s -> "STRING";
default -> "OTHER";
~~~

**This is a snippet inside an appropriate switch**, not a standalone program. `case null` should be written explicitly when you want to accept null. A standalone `default` does not necessarily handle null: in a Java 21 pattern switch, switching on null typically throws `NullPointerException` if there is no matching null label.

You do not need to force `case null` to the top because of dominance; placing it at the top is simply a choice to make code easier to read.

### 10.5. default Is Not a Tool to Fix All Ordering Errors

`default` helps cover other data types, but **cannot fix** a specific label being dominated by a preceding broad label. For example, having `case Number n` before `case Integer i` and then adding `default` at the end still results in the Integer label being rejected by the compiler.

When fixing a dominance error, you must **reorder or change the conditions/patterns** that make the labels overlap, not merely add a fallback branch.

## 11. Compiler-Confirmed List of Dominance Errors

The snippets below **intentionally do not compile** with `javac --release 21`. Each snippet assumes it is placed in a switch with an appropriate selector and result type.

**Error 1 — Number dominates Integer**

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
~~~

Every Integer is a Number, so the following `Integer` is dominated.

**Error 2 — CharSequence dominates String**

~~~java
case CharSequence cs -> "CHAR_SEQUENCE";
case String s -> "STRING";
~~~

Every String implements CharSequence, so the following `String` is dominated.

**Error 3 — General String pattern precedes guard**

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK";
~~~

The general case already accepts every String, so the guarded case can never be selected.

**Error 4 — General String pattern precedes constant**

~~~java
case String s -> "ANY_STRING";
case "OK" -> "EXACT";
~~~

The constant `"OK"` is always a String and is already caught by the preceding pattern.

**Error 5 — General record pattern precedes guarded record pattern**

~~~java
case Metric(int n) -> "METRIC";
case Metric(int n) when n > 0 -> "POSITIVE";
~~~

Assuming `record Metric(int value) {}`; the first case already accepts all Metric instances. The following label is dominated.

**Error 6 — Object at the top**

~~~java
case Object o -> "OBJECT";
case String s -> "STRING";
~~~

`Object` already accepts every non-null String, so the String label can never be selected.

**Error 7 — Constant true guard is treated as unguarded**

~~~java
case Integer i when true -> "ALL";
case 1 -> "ONE";
~~~

In Java 21, `when true` is a constant true guard, so the label is treated as unguarded for dominance. The following `1` case is dominated.

Typical `javac` error in these cases:

~~~text
error: this case label is dominated by a preceding case label
~~~

**Do not "fix" this by deleting the specific case** if business requirements need to keep it. Reorder from specific constants/guards to broader patterns. If two conditions genuinely overlap, rewrite them so each branch's data domain is clear and tested.

## 12. Distinguishing Dominance, Duplicate Labels, and Exhaustiveness

These are three different kinds of rules:

| Concept | Question the Compiler Must Guarantee | Example |
| --- | --- | --- |
| **Dominance** | Is any label subsumed by a preceding label? | `case Number` before `case Integer` |
| **Duplicate case constants** | Are there two case constants with the same value? | Two `case 1` labels |
| **Exhaustiveness** | Does the switch cover all possible input values? | Switch expression on `Object` with only String/Integer and no fallback |

A well-ordered switch can still be **non-exhaustive** if it omits a data type. Conversely, a switch with `default` can still **suffer from dominance** if a broad case shadows a specific case before reaching default.

For a switch expression on `Object`, you usually need a `default` or an appropriate total type pattern to cover the remaining types. For sealed types, the compiler can prove coverage via all permitted subtypes, as in the `Shape` example.

`case null` must be decided separately according to the input contract; a switch expression can be exhaustive by the compiler's check yet still throw an exception on null if there is no matching null branch.

## 13. When Using Colon-Style Switch Statements

The case-selection semantics are the same, but there are two body forms to distinguish:

~~~java
// Switch statement using arrow rules
switch (value) {
    case String s -> System.out.println("STRING:" + s);
    case Number n -> System.out.println("NUMBER:" + n);
    default -> System.out.println("OTHER");
}
~~~

~~~java
// Switch statement using colon statement groups
switch (value) {
    case String s:
        System.out.println("STRING:" + s);
        break;
    case Number n:
        System.out.println("NUMBER:" + n);
        break;
    default:
        System.out.println("OTHER");
}
~~~

These are **illustrative** snippets placed inside a method with `Object value`. Label dominance rules still must be followed in both forms.

Operational difference: the `case ... ->` form has no fall-through; the `case ...:` form can fall through if control flow is not stopped with `break`, `return`, or `throw`. With pattern variables, Java also forbids falling **into** a case that declares a pattern variable if the variable might be uninitialized.

Therefore, when focusing on **label specificity**, the arrow form is usually easier to review. If you must use colons, check both **case order** and **fall-through flow**; merely ordering subtypes before supertypes is not enough to guarantee the entire switch is safe.

## 14. Checklist for Ordering and Reviewing Pattern Switches

When encountering a switch with many cases, check yourself:

1. **What is the static type of the selector?** `Object`, `Number`, an interface, a record, or a sealed hierarchy?
2. **Are there subtype–supertype relationships?** `Integer` before `Number`, `String` before `CharSequence` if they need to be distinguished.
3. **Are there constant labels that need priority?** `case 1` or `case "OK"` should precede broad guarded/unguarded type patterns.
4. **Are guards on the same type ordered sensibly?** Specific conditions before unguarded cases of the same type.
5. **Can an earlier guard capture data meant for a later constant case?** The compiler will not necessarily report an error; test overlapping values.
6. **Is `case Object o`, an overly broad parent pattern, or `default` at the end?** Do not let broad patterns shadow specific cases.
7. **Are record patterns and sealed hierarchy subtypes ordered properly?** Specific guards before general record patterns.
8. **Are any labels duplicated or dominated?** Run the compiler and read the exact error rather than patching with a haphazard default.
9. **Is the switch exhaustive?** On `Object`, a fallback is usually needed; on a sealed hierarchy, all subtypes can be covered.
10. **Is `null` handled as intended?** Use `case null` if you want to handle it as a result.
11. **If using `case ...:`, is there any unintended fall-through?** Avoid falling into a label that declares a pattern variable.
12. **Are there tests for values matching multiple branches?** Testing the intersection often catches ordering bugs that the compiler does not detect.

## 15. Self-Check Exercises and Answers

### Exercise 1 — Fix Type Order

Given:

~~~java
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
case Double d -> "DOUBLE";
~~~

Reorder to handle Integer and Double separately first, then accept remaining Numbers.

**Answer:**

~~~java
case Integer i -> "INTEGER";
case Double d -> "DOUBLE";
case Number n -> "NUMBER";
~~~

The cases must be inside a switch with an appropriate selector and remaining covering branches if needed.

### Exercise 2 — Constant and Guard

Given a selector of type `Integer`:

~~~java
case Integer n when n > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer n -> "OTHER";
~~~

Will the compiler necessarily report dominance for this snippet? Which branch does `value = 1` take?

**Answer:** The guard `n > 0` is dynamic, so the snippet can compile. For `1`, the first guard is true, so it returns `POSITIVE`, not `ONE`. To treat `1` specially, place `case 1` before the guard.

### Exercise 3 — Specific Guard First

Order the following:

~~~java
case String s -> "TEXT";
case String s when s.isBlank() -> "BLANK";
case String s when s.length() > 10 -> "VERY_LONG";
~~~

so that it compiles and classifies blank strings first, long strings second, and other strings last.

**Answer:**

~~~java
case String s when s.isBlank() -> "BLANK";
case String s when s.length() > 10 -> "VERY_LONG";
case String s -> "TEXT";
~~~

A blank string longer than 10 characters is still prioritized as `BLANK` because the first guard comes first.

### Exercise 4 — Record Pattern

With `record Point(int x, int y) {}`, you want to distinguish the origin, points on the diagonal, and other points. Order the labels:

**Reference answer:**

~~~java
case Point(int x, int y) when x == 0 && y == 0 -> "ORIGIN";
case Point(int x, int y) when x == y -> "DIAGONAL";
case Point(int x, int y) -> "OTHER_POINT";
~~~

The origin also satisfies `x == y`, so it must precede the diagonal guard if you want a separate label for it.

### Exercise 5 — Interfaces

Why is `case CharSequence cs` before `case String s` dominance, whereas `case Number n` and `case CharSequence cs` can coexist in either order in `switch (Object value)`?

**Answer:** Every `String` is a `CharSequence`, so the preceding broad case subsumes the subtype case. `Number` and `CharSequence` have no direct subtype relationship for one pattern to automatically subsume the other; in basic examples both are valid and serve different groups of objects.

### Exercise 6 — Exhaustiveness and null

A switch expression on an `Object` selector has `String`, `Integer`, and `Number` cases. Is it exhaustive yet? Is adding `case null` enough?

**Answer:** No. Objects such as `new Object()` or `StringBuilder` still do not match the labels. A catch-all fallback like `default` or an appropriate `Object o` pattern is needed; handling null is a separate concern. Adding `case null` **does not** by itself cover all other types.

### Exercise 7 — Compiler Diagnostics

If `javac` reports `this case label is dominated by a preceding case label`, should you delete `default` or add `break` to fix it?

**Answer:** Usually no. Dominance concerns the matching capability of **case labels** in order; identify how the preceding label subsumes the following label, then reorder or redesign the pattern/guard. `break` only relates to control flow in colon-style switch statements.

## 16. Conclusion and References

A readable pattern switch should be organized **from specific cases to general ones**. Prioritize specific constants, guarded patterns according to business needs, then unguarded type/record patterns following subtype–supertype relationships, and finally a broad fallback. `null` needs to be decided explicitly.

The most important distinction: **the compiler catches dominance errors according to deterministic rules; the compiler does not guarantee that every dynamic guard order matches business intent**. Therefore, beyond compiling successfully, test values that can match **multiple labels**.

Official documentation:

- Java SE 21 JLS `14.11.1 — Switch Blocks, dominance and guarded case labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Java SE 21 JLS `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements, Pattern Label Dominance section: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
