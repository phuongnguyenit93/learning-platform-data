# Pattern Kinds in Java 21

## 1. What Is Pattern Matching?

In Java, a **pattern** describes how to test whether a value matches a given structure or data type. When it matches, the pattern can declare and assign values to **pattern variables** for direct use in the handling branch. Pattern matching replaces many manual type checks, casts, and component accesses.

Example with a data type:

```java
Object value = "Java 21";

if (value instanceof String text) {
    System.out.println(text.length()); // 7
}
```

Here `String text` is a **type pattern**: Java checks whether `value` is a `String` and, if so, declares `text` of type `String`. There is no need to cast again with `(String) value`.

**Java language patterns are not regular expressions**: `String.matches(...)` matches character patterns; `String text` is a pattern for an object type.

## 2. What Kinds of Patterns Does Java 21 Have?

According to the **Java SE 21** Java Language Specification, the two official kinds of patterns are **type patterns** and **record patterns**. Usages such as nested patterns, guards in `switch`, or `null` checks should be distinguished from those two foundational syntactic kinds.

| Syntax / Technique | Short Example | Meaning | Status in Java 21 |
| --- | --- | --- | --- |
| **Type pattern** | `obj instanceof String s` | Checks the type and binds variable `s` | Standard; patterns for `instanceof` finalized since Java 16 |
| **Record pattern** | `obj instanceof Point(int x, int y)` | Checks the record and extracts its components | Standard in Java 21 (JEP 440) |
| **Nested pattern** | `Box(Point(var x, var y))` | Combines multiple patterns, deconstructing multiple levels | Composition of type/record patterns, standard |
| **Pattern in `switch`** | `case String s -> ...` | Selects a branch by pattern instead of only constants | Standard in Java 21 (JEP 441) |
| **`case` guard** | `case String s when s.isBlank() -> ...` | Adds a condition after the pattern matches | `switch` syntax, **not an independent pattern kind** |
| **Unnamed pattern `_`** | `Point(var x, _)` | Ignores an unused component | **Preview in Java 21** (JEP 443); requires enabling preview |
| **`case null`** | `case null -> ...` | Handles the `null` value explicitly | `switch` label, **not a pattern** |

Note: `var` inside `Point(var x, var y)` lets the compiler infer the types of the components; it does not create a separate kind of pattern. For **standard Java 21 code**, you only need JDK 21—no `--enable-preview` is required to use type patterns, record patterns, and pattern `switch`.

## 3. Type Pattern: Check the Type and Use the Checked Variable

### 3.1. Using with `instanceof`

The old approach required checking the type and then casting:

```java
if (obj instanceof String) {
    String s = (String) obj;
    System.out.println(s.length());
}
```

A type pattern performs both the check and the variable binding:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

The variable `s` is only in **scope where Java knows the pattern has matched** (flow scoping). The following example is valid:

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

The right-hand side of `&&` is evaluated only when the left-hand side is true, so `s` has been assigned. You cannot use `s` the same way on the right-hand side of `||`: when the left-hand side is false, `s` has not been assigned.

Example of scope after a negated check:

```java
static int textLength(Object obj) {
    if (!(obj instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

After the `return` branch, the remainder runs only when `obj instanceof String text` is true. This is one benefit of flow scoping.

### 3.2. Using Type Patterns in `switch`

When there are multiple types to branch on, `switch` is easier to read than a chain of `if / else if`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case Integer n -> "Số nguyên: " + n;
        case String s -> "Chuỗi dài " + s.length();
        default -> "Kiểu khác";
    };
}
```

Each variable `n`, `s` is used only in its corresponding branch. A `switch` expression must return a value for every possible case; `default` here covers other types. `case null` handles `null` explicitly.

## 4. Record Pattern: Check and Deconstruct a Record

A `record` defines data in terms of **record components**. A record pattern lets you extract the components directly during the check without calling each accessor manually.

Suppose:

```java
record Point(int x, int y) {}
```

Before Java 21, the common approach was:

```java
if (obj instanceof Point p) {
    int x = p.x();
    int y = p.y();
    System.out.println(x + ", " + y);
}
```

With a record pattern in Java 21:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + ", " + y);
}
```

**Reading the syntax:** `Point(int x, int y)` requires the value to be a `Point` and matches the two components `x` and `y` in order, while declaring two local variables `x` and `y`.

Rules to remember:

- The pattern must refer to a **record type**; this syntax cannot be used to automatically deconstruct a regular class.
- The number of subpatterns must **equal the number of record components**, and their order must match the record declaration order.
- The components must be type-compatible with the subpatterns. `var` can help avoid repeating type names when the type is clear.
- A record pattern **does not invoke the constructor** or create a copy of the record; it checks the value and accesses its components for matching.
- You cannot write `Point(int x)` if `Point` has two components, and you cannot use `...` to skip remaining components.

### 4.1. `var` in Record Patterns

```java
if (obj instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

The compiler infers both `x` and `y` as `int` from the `Point` declaration. Similarly, with `record Pair<T>(T first, T second) {}`, type information of the value at the pattern site can help Java infer type arguments and component types.

`var` in a record component does not mean you can write `obj instanceof var x` to match any value.

## 5. Nested Pattern: Combining Record Patterns Across Multiple Levels

A nested pattern is a **way of nesting patterns**, not an independent third kind of pattern in Java 21.

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static String endpoints(Object obj) {
    if (obj instanceof Segment(
            Point(var x1, var y1),
            Point(var x2, var y2))) {
        return "(" + x1 + "," + y1 + ") -> (" + x2 + "," + y2 + ")";
    }
    return "Không phải đoạn thẳng hợp lệ";
}
```

Level-by-level explanation:

1. `Segment(...)` checks the outer object and deconstructs `start` and `end`.
2. The two `Point(...)` patterns further check the inner `Point` components.
3. `var x1`, `var y1`, `var x2`, `var y2` directly bind the four coordinates.
4. Only when the **entire** pattern matches is the `if` branch executed.

For example, `new Segment(new Point(1, 2), new Point(4, 6))` produces the string `(1,2) -> (4,6)`.

For a component that needs further deconstruction, a `null` value at that level causes the nested record pattern not to match. Do not assume a record-typed component is always non-`null`. Validate input data if the model allows `null`.

## 6. Pattern `switch`, `when` Guards, and Branch Ordering

Java 21 allows a `case` branch to contain a type pattern or record pattern. You can add a **guard** with `when` for finer filtering:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "Chuỗi trống/trắng";
        case String s -> "Chuỗi thường";
        case Integer n when n > 0 -> "Số nguyên dương";
        case Integer n -> "Số nguyên không dương";
        default -> "Loại khác";
    };
}
```

Matching flow for a guarded branch:

1. Evaluate the `switch` selector expression.
2. Test the `case` branch's pattern.
3. If the pattern matches, evaluate the condition after `when`; if true, execute that branch.
4. If either the pattern or the guard does not match, proceed to the next branches.

**Order matters.** More specific branches should come before more general ones. For example:

```java
// Wrong: CharSequence already covers every String.
switch (value) {
    case CharSequence cs -> System.out.println(cs.length());
    case String s -> System.out.println(s); // Compile error: dominated case
    default -> {}
}
```

The compiler detects that `case String s` can never be selected because every `String` is a `CharSequence`, and the preceding more general branch already covers it. This is the **dominance** rule.

A `when` guard is not standalone syntax after `instanceof`. With `instanceof`, use logical operators:

```java
if (value instanceof String s && s.length() > 5) {
    System.out.println(s);
}
```

In `switch`, `case null` handles `null`. Without a matching `case null` branch, a pattern `switch` receiving `null` typically throws a `NullPointerException` before reaching `default`. Do not treat `default` as a replacement for `case null`.

### 6.1. Exhaustiveness with `sealed` Types

When branching over a `sealed` hierarchy, the compiler knows all permitted subtypes:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String message) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Success(var value) -> "OK: " + value;
        case Failure(var message) -> "ERR: " + message;
    };
}
```

This is an **illustrative snippet** that must be placed in a valid Java compilation unit along with its accompanying declarations. Both types listed in `permits` are handled, so the `switch` expression does not need a `default` for non-`null` values. If you add a new permitted subtype, the compiler forces you to revisit exhaustiveness. `null` still needs to be handled if it can occur.

For pattern `switch` statements (enhanced `switch`), Java 21 also requires exhaustiveness; `switch` expressions have always had to be exhaustive. This helps catch missing branches at compile time.

## 7. Complete Java 21 Example Without Preview

Save all the code below into **`PatternKindsDemo.java`**:

```java
public class PatternKindsDemo {
    record Point(int x, int y) {}
    record ColoredPoint(Point point, String color) {}

    static String inspect(Object value) {
        if (value instanceof String s) {
            return "String length = " + s.length();
        }
        if (value instanceof ColoredPoint(
                Point(int x, int y), String color)) {
            return "Point = (" + x + ", " + y + "), color = " + color;
        }
        return "Other";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank string";
            case String s -> "text";
            case Integer n when n > 0 -> "positive integer";
            case Integer n -> "other integer";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect("Java"));
        System.out.println(inspect(
                new ColoredPoint(new Point(2, 3), "red")));
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("ok"));
        System.out.println(classify(7));
        System.out.println(classify(-2));
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 PatternKindsDemo.java
java PatternKindsDemo
```

Expected output:

```text
String length = 4
Point = (2, 3), color = red
null
blank string
text
positive integer
other integer
```

In a single program, the example combines four techniques: **type pattern** with `String`, **record pattern** with `ColoredPoint`, **nested pattern** with `Point`, and a `when` **guard** in a pattern `switch`. All are standard features of Java 21.

## 8. Unnamed Pattern `_`: A Separate Preview Feature in Java 21

JEP 443 allows using an underscore `_` to **ignore a record component** that the program does not need. This is a **preview feature in Java 21**, unlike standard record patterns.

Example: extract the `x` coordinate while ignoring `y` and the label. Save into **`PreviewPatternDemo.java`**:

```java
public class PreviewPatternDemo {
    record Point(int x, int y) {}
    record LabeledPoint(Point point, String label) {}

    static String xOf(Object obj) {
        return switch (obj) {
            case LabeledPoint(Point(int x, _), _) -> "x = " + x;
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                xOf(new LabeledPoint(new Point(3, 9), "red")));
    }
}
```

Compile and run with **JDK 21**, enabling preview in **both steps**:

```bash
javac --enable-preview --release 21 PreviewPatternDemo.java
java --enable-preview PreviewPatternDemo
```

Output:

```text
x = 3
```

Distinguish easily confused syntaxes:

- `Point(var x, var y)`: both `x` and `y` have names to reference; works without preview.
- `Point(var x, _)`: binds only `x`; `_` is an **unnamed pattern** in a component position, requiring preview on JDK 21.
- `case String _ -> ...`: unnamed pattern variable, also part of the preview feature on JDK 21.
- `case _ -> ...` or `obj instanceof _`: **not** valid free-standing wildcard patterns in Java 21.
- Unnamed **variables** in variable declarations, `catch`, or lambdas are also covered by JEP 443, but that is a different usage of `_` from unnamed patterns inside records.

When you do not want to depend on preview, write `Point(var x, var ignoredY)` and simply leave `ignoredY` unused. `_` and unnamed variables/patterns became standard features in **Java 22 (JEP 456)**; do not apply Java 22's status retroactively to Java 21.

## 9. Common Mistakes and How to Fix Them

| Situation | Why It Is Wrong or Error-Prone | How to Handle |
| --- | --- | --- |
| `obj instanceof String s` then using `s` on a path where the pattern may not match | A pattern variable is in scope only when definitely assigned | Use `s` in the true branch, after a `return` guard, or on the valid right-hand side of `&&` |
| Placing `case Object o` / `case CharSequence cs` before a specific pattern | The specific branch can be **dominated** | Place specific patterns before general ones |
| Writing `case String s when ...` and assuming `when` works with `instanceof` | `when` is a guard for a `switch` pattern branch | Use `&&` after `instanceof` |
| Omitting `case null` and expecting `default` to handle `null` | `switch` can throw `NullPointerException` | Add `case null` or check for `null` beforehand |
| Using `Point(var x)` when the record has two components | The number of pattern components does not match the record | Specify all positions, such as `Point(var x, var y)` |
| Using a record pattern on a regular class | This deconstruction syntax applies only to `record`s | Use a type pattern and call getters/accessors normally |
| Using `_` on JDK 21 without enabling preview | Unnamed patterns are not standard in Java 21 | Enable `--enable-preview` or use a named variable |
| Writing `instanceof int n` to match a boxed integer | Java 21 does not have free-standing primitive type patterns like that | Use `instanceof Integer n`; for an `int` record component, you can use `Point(int x, int y)` |
| Treating a record pattern as matching individual fields out of order | It deconstructs according to **declared components** | Match the exact order and type of each component |

## 10. Choosing the Right Pattern for the Problem

If you only need to know an object's type and use a checked variable, use a **type pattern**. If the data is modeled with a `record` and you need its components, use a **record pattern**. If the data has nested `record`s, nest **record patterns** to express the structure directly. If multiple types must route to different action branches, use a **pattern `switch`**; add `when` when a branch needs an extra condition. Only use the **unnamed pattern `_`** if your Java 21 project allows preview features and you genuinely need to ignore a component.

**Quick self-check:**

1. What kind is `String s` in `case String s`? → **Type pattern**, placed in a `switch` branch.
2. What is `Point(int x, int y)`? → **Record pattern**, extracting two components.
3. What is `Segment(Point(var x1, var y1), Point(var x2, var y2))`? → **Nested record pattern** (a record pattern containing record patterns).
4. Is `when x > 0` a separate pattern? → **No**; it is a guard on a `switch` pattern branch.
5. Does `Point(var x, _)` run by default on JDK 21? → **No**; it requires `--enable-preview`.

## 11. Standard Reference Documentation

- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): definition and classification of type/record patterns.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns as a standard feature in Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern labels, guards, dominance, exhaustiveness, and `null`.
- [JEP 443 — Unnamed Patterns and Variables (Preview)](https://openjdk.org/jeps/443): `_` syntax under preview mode in Java 21.
- [Oracle Java SE 21 — Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): official feature status table for Java 21.
