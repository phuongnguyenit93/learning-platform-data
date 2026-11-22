# What is a Pattern in the Java Language Specification (JLS)?

**Scope:** Java SE 21 (JDK 21), where *type patterns*, *record patterns*, and pattern matching in `instanceof`/`switch` are all stable features. This article explains `pattern` according to the Java Language Specification, not regular expressions (`java.util.regex.Pattern`) or software design patterns (*design patterns*).

## 1. Definition according to JLS `14.30

In the Java Language Specification, a **pattern** describes a **test that can be performed on a value**. The value to be tested is provided by the expression or statement containing the pattern. A pattern can declare **zero, one, or more local variables**, called *pattern variables*.

**Pattern matching** is the process of testing a value against a pattern at runtime:

1. There is an input value, such as a reference whose static type is `Object`.
2. Java checks whether that value satisfies the structure and type conditions of the pattern.
3. If it **matches**, Java initializes the pattern variables declared in the pattern; the program can use them at locations where the compiler proves that the match succeeded.
4. If it **does not match**, those variables are not initialized and cannot be used as if the pattern had succeeded.

Example:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Here `String text` is a **type pattern**; `value` is the value being tested; `text` is the pattern variable. The entire `value instanceof String text` is an expression that evaluates to a `boolean` result. `String text` itself is not a standalone `boolean` expression.

Compared to the old way of writing:

```java
Object value = "Java";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Patterns combine type checking with variable declaration/initialization, eliminating repetitive casts while preserving runtime type checking.

## 2. Forms of patterns in Java 21 (`14.30.1)

According to the Java SE 21 JLS, `Pattern` has two basic forms: **`TypePattern`** and **`RecordPattern`**. A simplified grammar for recognition (not replacing the full grammar productions in the JLS):

```text
Pattern       ::= TypePattern | RecordPattern
TypePattern   ::= declaration of a single local variable, without an initializer
RecordPattern ::= ReferenceType "(" [Pattern ("," Pattern)*] ")"
```

### 2.1. Type pattern: testing a type and binding a variable

For example, `String s`, `CharSequence seq`, or `Number n` tests whether the object is compatible with the specified type; when it matches, the corresponding variable is initialized with the tested value.

```java
Object input = 42;
if (input instanceof Integer number) {
    System.out.println(number + 1); // 43
}
```

Important syntactic limitations in **Java 21**:

- A top-level type pattern must use a **reference type** and must name a variable, such as `String s`. `obj instanceof var s` and `obj instanceof int n` are not valid in the stable Java 21 grammar.
- A type pattern declares exactly **one** variable, with no initializer assignment or array brackets placed after the variable name. For example, `String s = "x"` is not a valid pattern.
- Inside a record pattern's component list, `var` can be used for Java to infer the component type, or a specific type can be declared (including `int` for an `int` component). `var` cannot be used arbitrarily as a top-level type pattern.
- Generic type checks are subject to type compatibility rules and *type erasure*: `List<?> list` can be used in appropriate cases, whereas `List<String> list` is not a type that can be fully checked by `instanceof` at runtime.

### 2.2. Record pattern: testing a record and deconstructing components

A record pattern combines testing whether a value belongs to the corresponding `record` class with **recursively matching** each component of the record (*deconstruction*).

```java
record Point(int x, int y) {}

Object value = new Point(3, 4);
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

In `Point(int x, int y)`:

- `Point(...)` is a record pattern; the value must be an appropriate `Point`.
- `int x` and `int y` are nested type patterns inside, corresponding to the two record components.
- `x` and `y` are only available for use when the **entire** record pattern matches.

Patterns can be nested deeply:

```java
record NamedPoint(String name, Point point) {}

Object item = new NamedPoint("A", new Point(2, 5));
if (item instanceof NamedPoint(String name, Point(int x, int y))) {
    System.out.println(name + ": " + x + ", " + y); // A: 2, 5
}
```

Rules to remember:

- The type before `(...)` must be a **record class type**, not an arbitrary Java class with record-like getters.
- The number of component patterns must **match** the number of declared components of the record and in the exact order; `Point(int x)` is a compile-time error if `Point` has two components.
- `record Empty() {}` can be matched with `Empty()` without declaring any variables. A record pattern does not directly declare variables; the inner component patterns declare the variables.
- Duplicate pattern variable names cannot be declared in the same record pattern, for example `Point(int x, int x)`.
- `Point(var x, var y)` is valid and infers `x` and `y` as `int`. This is `var` appearing directly inside a record pattern.

## 3. Where do patterns appear?

### 3.1. In the `instanceof` operator (`15.20.2)

`instanceof` takes a pattern as its right-hand operand. The check returns `true` or `false`; when true, the pattern variables can be used within their valid scope:

```java
static int textLength(Object obj) {
    if (obj instanceof String s) {
        return s.length();
    }
    return -1;
}
```

Starting in Java 21, `instanceof` can also test a record pattern, such as `obj instanceof Point(int x, int y)`. An object whose static type is `Object` can still be deconstructed into components that are type-checked at runtime.

### 3.2. In `case` labels of `switch` (`14.11)

`switch` can select a branch using patterns instead of only constants:

```java
static String kind(Object obj) {
    return switch (obj) {
        case null      -> "null";
        case String s  -> "chuỗi: " + s;
        case Integer n -> "số nguyên: " + n;
        default        -> "kiểu khác";
    };
}
```

In the example, `String s` and `Integer n` are patterns; `null` and `default` are other forms of `case` labels/branches, **not** patterns according to `14.30`. The `case null` branch handles `null` explicitly; if there is no appropriate branch handling `null`, a `switch` on a `null` reference normally throws a `NullPointerException`, even when `default` is present.

A `case` label can add a **`when`** guard condition (*guard*):

```java
static String lengthGroup(Object obj) {
    return switch (obj) {
        case String s when s.length() > 5 -> "chuỗi dài";
        case String s                     -> "chuỗi ngắn";
        default                           -> "không phải chuỗi";
    };
}
```

Java only evaluates `when` after the corresponding pattern has matched, so `s` is initialized when the guard condition runs. If `when` evaluates to `false`, selection continues checking the remaining branches. **`when` is a guard attached to a `case` label, not a third kind of pattern.**

## 4. Matching mechanism and variable initialization (`14.30.2)

### For type patterns

A non-`null` reference matches `String s` if the value can be cast to `String` according to the JLS testing rules; in that case `s` receives that value. If it cannot be cast, the match fails.

### For record patterns

To match `NamedPoint(String name, Point(int x, int y))`, Java semantically:

1. Checks whether the input value is compatible with the `NamedPoint` record type.
2. Retrieves the record components via **accessor methods** (for example, `name()`, `point()`).
3. Matches each component value against the corresponding pattern; if a nested record is encountered, continues matching recursively.
4. Only considers the pattern variables initialized for use by the expression/branch if **all** component matches succeed.

Pattern matching is not a field-access operation using arbitrary getter syntax. If a record accessor throws an exception when invoked during deconstruction, the Java 21 JLS specifies that the matching process completes abruptly with a `MatchException` carrying that exception as its cause. This is distinct from a normal **non-match** result.

### `null` rules to read carefully

- `null instanceof String` is `false`; a top-level type pattern `String s` does not match `null`.
- A record pattern such as `Point(int x, int y)` does not match when the **record value itself** is `null`.
- **Subtle exception:** A *directly nested type pattern* inside a record pattern can be *null-matching* if it is an **unconditional** pattern for the type of the record component. For example:

```java
record Box(String value) {}

Object box = new Box(null);
if (box instanceof Box(var content)) {
    System.out.println(content == null); // true
}
```

`Box(var content)` matches because the outer `Box` reference is not `null`; `var content` corresponds to the `String` component and can receive the `null` value itself. Therefore, one should not assume that **every** component of a record pattern must be non-`null`.

## 5. Flow-scoped variables (`6.3)

The JLS uses a mechanism commonly called **flow scoping**: the scope of a pattern variable depends on the branches where the compiler determines the pattern has matched.

**Valid — `&&` only evaluates the right-hand side if the left-hand side is true:**

```java
static boolean isLongText(Object obj) {
    return obj instanceof String s && s.length() > 5;
}
```

**Valid — early return on the non-matching branch:**

```java
static void printText(Object obj) {
    if (!(obj instanceof String s)) {
        return;
    }
    System.out.println(s.toUpperCase());
}
```

**Invalid — `||` may evaluate the right-hand side when the pattern on the left-hand side fails:**

```java
// DOES NOT COMPILE:
// if (obj instanceof String s || s.isEmpty()) {
//     System.out.println(s);
// }
```

Encountering a `String s` declaration does not mean `s` is in scope for the entire method. The compiler checks whether the variable is definitely initialized along each control-flow path. In a `switch`, a pattern variable exists only within the corresponding region of its `case` label, guard, and matching branch.

## 6. Properties the JLS uses to check patterns (`14.30.3)

| Term | Learning meaning | Example / impact |
| --- | --- | --- |
| **Applicable at type** | The pattern must be valid for the static type of the tested value according to conversion rules and record structure. | `Object obj` can be tested with `String s`; `Integer` and `String` are unrelated final types, so `Integer i; i instanceof String s` is invalid. |
| **Unconditional for type** | For a given input type, the pattern is guaranteed to match every value of that type according to JLS rules. | `Object o` is an unconditional type pattern for type `String`; this property is also related to null-matching in record components. |
| **Dominates** | An earlier pattern covers the cases that a later pattern is meant to handle; `case` ordering can make the later branch unreachable. | Placing `case CharSequence cs` before `case String s` causes a compile error because the later branch is dominated. |
| **Exhaustive switch** | The branches must cover all cases that the `switch` is required to handle, especially in a `switch` expression and an enhanced `switch` statement. | You can use `default` or fully partition a `sealed` type with appropriate patterns. |

An example that **does not compile** due to dominance:

```java
// switch (obj) {
//     case CharSequence cs -> System.out.println(cs);
//     case String s -> System.out.println(s); // Dominated by the previous case
//     default -> {}
// }
```

Place specific cases (`String`) before general cases (`CharSequence`), and only use `default` when needed. Guards can help split conditions, but a guard should not be thought of as a separate pattern.

With a `sealed interface` or `sealed class`, the compiler can sometimes prove that a `switch` expression covers all permitted subtypes without needing `default`. That is a property of the set of `case` labels and the selector type, not that every pattern automatically matches every value.

## 7. Complete program using type patterns, record patterns, and guards

Save the content below to a file named `PatternJlsDemo.java`. The program requires **JDK 21 or later** and does not require enabling preview features:

```java
public class PatternJlsDemo {
    record Point(int x, int y) {}

    record NamedPoint(String name, Point point) {}

    static String describe(Object value) {
        // Type pattern and flow scoping via &&
        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi: " + text;
        }

        return switch (value) {
            case null -> "null";

            // Nested record pattern with guard
            case NamedPoint(String name, Point(int x, int y))
                    when x == y -> name + ": đường chéo";

            // Nested record pattern without guard
            case NamedPoint(String name, Point(int x, int y)) ->
                    name + ": (" + x + ", " + y + ")";

            case String ignored -> "Chuỗi trống";
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new NamedPoint("A", new Point(2, 3))));
        System.out.println(describe(new NamedPoint("B", new Point(4, 4))));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 21 -encoding UTF-8 PatternJlsDemo.java
java PatternJlsDemo
```

Expected output:

```text
Chuỗi: Java
A: (2, 3)
B: đường chéo
null
Khác
```

Step-by-step explanation:

1. `"Java"` matches `String text` and is not blank, so it returns immediately.
2. `NamedPoint("A", Point(2, 3))` matches the record, but the guard `x == y` is false, so execution proceeds to the next record pattern.
3. `NamedPoint("B", Point(4, 4))` matches the record and the guard is true, so it returns the diagonal branch.
4. `null` is caught by `case null` before record patterns are considered.
5. `42` does not match the `NamedPoint` or `String` patterns, so it falls into `default`.

In this example, each use of `String name`, `int x`, or `int y` declares a new pattern variable belonging to the corresponding branch. Java verifies the match condition before allowing those variables to be read.

## 8. Common mistakes and how to self-check

1. **Confusing patterns with regex or design patterns.** `java.util.regex.Pattern` matches strings against regular expressions; `14.30` describes a construct of the Java language itself for matching values.
2. **Calling the entire expression a pattern.** In `obj instanceof String s`, only `String s` is the pattern; `instanceof` is the operator that uses the pattern.
3. **Using a variable when a match is not guaranteed.** Check scope along the paths of `if`, `&&`, `||`, `!`, `return`, and `switch` branches.
4. **Assuming record patterns can deconstruct any class.** They require a record type, the exact number of components, and valid sub-patterns.
5. **Assuming `null` always behaves the same way.** Top-level type patterns and record patterns themselves do not match `null`; certain type patterns in record component positions can match `null` under the *unconditional* rule.
6. **Writing overly broad `case` labels first.** A broader pattern can *dominate* a more specific pattern placed later, causing a compile-time error.
7. **Using version-mismatched syntax.** Pattern matching for `instanceof` has been a stable feature since **Java 16**; record patterns and pattern matching for `switch` have been stable since **Java 21**. Standalone parenthesized pattern syntax like `case (String s)` is no longer a pattern in JLS 21; the `_` token for unnamed patterns is not part of the stable Java 21 syntax set. Documentation about preview features in other versions may differ from the examples here.
8. **Confusing `when` with a pattern.** `when` adds a condition after the pattern match, while variable binding is determined by the type/record pattern.

When encountering a pattern-matching expression, identify in order: **what value is being tested**, **what kind of pattern it is**, **whether the static type allows the test**, **what the runtime matching condition is**, **which variables are initialized on success**, and **where those variables remain in scope as control flow continues**.

## 9. Official specification references

- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): definitions, pattern kinds, matching mechanism, applicability/unconditional/dominance.
- [JLS Java SE 21 `15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): rules for the `instanceof` operator.
- [JLS Java SE 21 `14.11 — switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): `case` labels, guards, `null`, and exhaustiveness.
- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow-scoped pattern variables.
- [Oracle Java SE 21 Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): stability status and history of pattern-matching features.
