# Pattern Names to Recognize in Java 21 Source Code

## 1. Goal: Read Source Code and Name the Syntax Accurately

When reading a Java snippet that uses **pattern matching**, you should be able to answer three questions:

1. **Which part is actually a pattern?** Not every place with `instanceof`, `case`, parentheses `()`, or the word `var` is a pattern.
2. **What is that pattern called?** Java 21 has two official kinds of patterns: **type pattern** and **record pattern**. Phrases like *nested pattern* or *guarded case label* describe how patterns are placed or combined—they do not automatically become a third kind of pattern.
3. **Which variables does it bind, and when are those variables in scope?** A name inside a pattern is a local variable declared when the pattern matches; that name does not have to match the field or component name of the data.

In this lesson, “pattern” refers to **Java language pattern matching** syntax, as distinct from *design patterns* (Strategy, Factory, Observer...) and the `java.util.regex.Pattern` class used for regular expressions.

First example:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

- `instanceof`: type-testing operator that can accept a pattern on its right-hand side.
- `String text`: **type pattern**; `String` is the type to test, and `text` is the **pattern variable**.
- `text.length()`: statement using the bound variable, **not** another pattern.

## 2. Glossary of Names You Will See When Reading Java 21

| Term | Recognition cue in code | Accurate meaning | Status in Java 21 |
| --- | --- | --- | --- |
| **Type pattern** | `String s`, `Number n` in `instanceof` or `case` | Tests a type and binds a named variable | Standard |
| **Record pattern** | `Point(int x, int y)`, `Box(var v)` in a pattern position | Tests a record and matches its components in order | Standard; JEP 440 |
| **Nested pattern** | `Segment(Point(var x, var y), Point(var a, var b))` | A pattern inside the component list of another record pattern | Standard way of combining patterns |
| **Inferred type pattern** (type pattern using `var`) | `Point(var x, var y)` | The variable's type is inferred from the record component | Standard when placed in a valid nested position |
| **Pattern variable** | `s` in `String s`, `x` in `int x` | Variable name declared/assigned when the pattern matches | Language concept; not a kind of pattern |
| **Pattern case label** | `case String s ->`, `case Point(var x, var y) ->` | A `switch` label that uses a pattern | Standard; JEP 441 |
| **Guarded case label** | `case String s when s.isBlank() ->` | Pattern `String s` paired with a `when` condition | Standard; the guard is not a separate kind of pattern |
| **Unnamed pattern** | `Point(var x, _)` | Ignores a component; declares no variable for `_` | **Preview** in Java 21; JEP 443 |
| **Unnamed pattern variable** | `case String _ ->` | A type pattern whose variable has no usable name | **Preview** in Java 21; JEP 443 |
| **Unconditional pattern** | JLS term; e.g., `case Object o` when the selector is `Object` | A property regarding type coverage, not new syntax | Pattern analysis concept |

**Official names in the Java SE 21 grammar:** `TypePattern` and `RecordPattern` are the two branches of `Pattern` in JLS §14.30.1. The other names in the table are very useful when reading code, writing documentation, or reviewing, but you must distinguish **kind of pattern**, **usage position**, **property**, and **preview feature**.

## 3. Recognizing a Type Pattern and a Pattern Variable

### 3.1. A Type Followed by a Variable Name

Look at the following snippets:

```java
value instanceof String name
value instanceof Number number
case CharSequence text -> ...
case Integer count when count > 0 -> ...
```

`String name`, `Number number`, `CharSequence text`, and `Integer count` are **type patterns**. In them, `name`, `number`, `text`, and `count` are **pattern variables**.

Quick way to recognize them: look for a **pattern position** (after `instanceof` or after `case`) and then identify “type + variable name”. Looking at `String name` in isolation is not enough, because the same token sequence can be a regular declaration elsewhere.

Compare:

```java
String name = "Java";               // Local variable declaration, not a pattern
void print(String name) { ... }     // Method parameter, not a pattern
if (obj instanceof String name) {}  // Type pattern
switch (obj) {
    case String name -> use(name);   // Type pattern in a case label
    default -> {}
}
```

The lines above are **separate illustrative syntax fragments**, not a complete program to copy and compile as a single block; `use` and `obj` would need to be defined if placed in a program.

### 3.2. `instanceof Type` and `instanceof Type variable` Are Not the Same

```java
obj instanceof String    // Traditional type test
obj instanceof String s  // Type pattern, also declares variable s
```

Both use `instanceof`, but the first form does not declare a pattern variable. The second form lets you use `s` in branches where Java knows the match succeeded.

### 3.3. Flow Scoping: A Variable Name Exists Only Where It Has Matched

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

The right-hand side of `&&` is evaluated only when `obj instanceof String s` is `true`, so `s` is already assigned. Conversely, you cannot arbitrarily use `s` after `||` because the left-hand side might not have matched. Java calls this control-flow-based scoping rule **flow scoping**.

Another valid example:

```java
static int lengthOrMinusOne(Object obj) {
    if (!(obj instanceof String s)) {
        return -1;
    }
    return s.length();
}
```

After the `return -1` branch, Java knows `s` is bound. A pattern variable **does not automatically become a field** of the class or a property of the object.

## 4. Recognizing a Record Pattern by Parentheses Containing Sub-Patterns

Consider these data declarations:

```java
record Point(int x, int y) {}
record Marker(Point point, String label) {}
```

In a pattern position, the following expression is a **record pattern**:

```java
obj instanceof Point(int a, int b)
```

Syntax breakdown:

- `Point`: name of the **record type** to match.
- `(int a, int b)`: list of two **component patterns**; both `int a` and `int b` are type patterns inside the record pattern.
- `a` and `b`: two new pattern variables. They are **not** the record component names declared in `record Point(int x, int y)`.
- The number of elements inside the parentheses must equal the number of components of the record and be in the same order.

Therefore, `Point(int a, int b)` should not be read as “calling the `Point` constructor”, but rather as “deconstructing a `Point` into two values”.

### 4.1. Three Similar-Looking Lines with Different Meanings

```java
record Point(int x, int y) {}         // Record type declaration
Point p = new Point(1, 2);           // Object instantiation
if (obj instanceof Point(int a, int b)) { // Record pattern
    System.out.println(a + b);
}
```

The `()` in a `record` declaration, a `new` call, and a record pattern play different roles; **syntactic context** is what tells you which one is a pattern.

Also, `obj instanceof Point p` is a **type pattern** because `Point` is followed by a variable name. `obj instanceof Point(var x, var y)` is a **record pattern** because `Point` is followed by a list of sub-patterns.

### 4.2. `var` Inside a Record Pattern

```java
if (obj instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
```

From `record Point(int x, int y)`, the compiler knows `a` and `b` are `int`. When you see `var a` or `var b` **inside a record pattern**, call it a **type pattern with an inferred type**.

Do not assume that `obj instanceof var anything` is also valid: a **top-level type pattern** of `instanceof` in Java 21 must explicitly specify a reference type, not `var`.

### 4.3. A Record Pattern Does Not Have to Create Variables

```java
record Done() {}

static boolean completed(Object obj) {
    return obj instanceof Done();
}
```

`Done()` is a record pattern with an empty component list; it tests a record that has no components. Not every pattern has to produce a pattern variable. In particular, a record pattern **by itself** does not declare a variable representing the entire record; variables come from the sub-patterns.

## 5. Recognizing Nested Patterns and Each Variable Name

A nested pattern appears when a pattern stands inside the component list of **another record pattern**. For example:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static String describe(Object obj) {
    if (obj instanceof Segment(
            Point(var startX, var startY),
            Point(var endX, var endY))) {
        return startX + "," + startY + " -> " + endX + "," + endY;
    }
    return "not a segment";
}
```

Reading from outside in:

1. `Segment(...)` is the **outer record pattern**.
2. The two `Point(...)` are **nested record patterns**.
3. `var startX`, `var startY`, `var endX`, `var endY` are **inferred type patterns**, declared directly in the `Point` component positions.
4. `startX`, `startY`, `endX`, `endY` are four **pattern variables** usable when the entire match succeeds.

With `new Segment(new Point(1, 2), new Point(7, 8))`, the method returns `"1,2 -> 7,8"`.

You can mix explicit type patterns and `var` in the same record pattern:

```java
obj instanceof Marker(Point(int x, int y), String color)
obj instanceof Marker(Point(var x, var y), var color)
```

Both have an outer `Marker(...)` **record pattern**, an inner `Point(...)` **record pattern**, and **type patterns** at the component positions. `String color` or `var color` binds the value of the `label` component, even though the variable is named `color`.

**Distinguishing a common mistake:** when the `point` component of a `Marker` is `null`, the nested record pattern `Point(...)` **does not match**. A nested type pattern may have its own `null`-matching rules when it is **unconditional** for the component type; do not generalize that all sub-patterns handle `null` the same way. When logic requires non-`null` data, ensure it via checks or data constraints.

## 6. Recognizing Patterns in `switch` and `when` Conditions

Example:

```java
static String classify(Object obj) {
    return switch (obj) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> "string";
        case Integer n when n > 0 -> "positive integer";
        case Integer n -> "other integer";
        default -> "other type";
    };
}
```

Name each branch accurately:

- `case String s`: **pattern case label** containing the **type pattern** `String s`.
- `case String s when s.isBlank()`: **guarded case label**; the pattern is still `String s`, and `s.isBlank()` is the **guard** condition.
- `case Integer n`: **type pattern**, pattern variable named `n`.
- `case null`: **null case label**, **not** a kind of pattern.
- `default`: **default label**, **not** a pattern.

The `when` guard is evaluated only after the pattern has matched. `when` in `switch` does not replace `&&` after `instanceof`:

```java
if (obj instanceof String s && s.length() > 3) { /* ... */ }
```

### 6.1. Branch Order and Dominance

In `switch`, a broader branch can prevent a narrower branch from ever running:

```java
// Code illustrating a compile-time error:
switch (obj) {
    case CharSequence sequence -> System.out.println(sequence.length());
    case String text -> System.out.println(text); // Dominated by the branch above
    default -> {}
}
```

`String` implements `CharSequence`. Therefore `case String text` after `case CharSequence sequence` is **dominated**. Order specific branches before general branches.

With guards, you typically place specific constant branches first, `when` branches next, and unguarded branches last so special cases take priority. Avoid assuming the compiler can reason about every `when` condition; arbitrary conditions can be complex and must not be relied upon as a substitute for explicit branch ordering.

### 6.2. Exhaustiveness: Understanding Which Labels Cover Which Values

With a `switch` expression, the branches must be exhaustive enough to return a result for all valid cases. When the selector has a `sealed` type, you can list the permitted subtypes:

```java
sealed interface Event permits Started, Stopped {}
record Started(long id) implements Event {}
record Stopped(String reason) implements Event {}

static String describeEvent(Event event) {
    return switch (event) {
        case Started(var id) -> "start " + id;
        case Stopped(var reason) -> "stop " + reason;
    };
}
```

This is an **illustrative snippet** placing the declarations in the same appropriate compilation unit. Both branches contain **record patterns**, each deconstructing one subtype. For the `Event` type, the compiler sees that all permitted subtypes are handled; if `null` is possible, add a `case null` branch or check beforehand. Remember that `default` by itself does not guarantee catching `null`.

## 7. Distinguishing Things That Look Like Patterns From Actual Patterns

| Code snippet encountered | Exact name | Is it a pattern? |
| --- | --- | --- |
| `obj instanceof String` | `instanceof` type test | **No** |
| `obj instanceof String s` | `instanceof` using a **type pattern** | **Yes**: `String s` |
| `case Point p ->` | `case` containing a **type pattern** | **Yes**: `Point p` |
| `case Point(var x, var y) ->` | `case` containing a **record pattern** | **Yes** |
| `record Point(int x, int y) {}` | Record and component declaration | **No** |
| `new Point(3, 5)` | Object creation via constructor | **No** |
| `Point p = new Point(3, 5)` | Variable declaration and object creation | **No** |
| `case 100 ->` | `switch` constant case label | **No** |
| `case RED ->` | `enum` constant case label | **No** |
| `case null ->` | Label for `null` | **No** |
| `default ->` | Default label | **No** |
| `String pattern = ".*";` | Regular variable named `pattern` | **No** |
| `Pattern.compile(".*")` | Regular expression API | **No** |
| `case String s when s.isEmpty() ->` | Type pattern + guard | **Yes**: `String s`; **No**: `when` |

**There is no general “constant pattern” as an independent kind of pattern in the Java 21 grammar.** `case` constants are **constant case labels**, and `case null` is a special case label. There is also no standard Java 21 syntax to deconstruct a list/array using a list pattern as in some other languages.

## 8. Names Appearing in Old or New Preview Examples

When reading blog posts or code from Java 17–21 preview releases, check the version.

### 8.1. Unnamed Pattern `_` in Java 21: Preview

```java
record Point(int x, int y) {}

if (obj instanceof Point(var x, _)) {
    System.out.println(x);
}
```

The `_` is an **unnamed pattern** in the second component position: it matches and discards that component without introducing a usable variable name. This syntax is a **preview** feature in Java 21 (JEP 443), so it does not compile by default in standard Java 21 mode.

Meanwhile, `case String _ ->` is called a **type pattern with an unnamed pattern variable**, which is also a preview feature; it differs from `_` standing alone in a component list. You cannot use `_` as a named variable afterward.

Save **`PreviewNames.java`** to run the complete preview example:

```java
public class PreviewNames {
    record Point(int x, int y) {}
    record Tagged(Point point, String label) {}

    static String firstX(Object obj) {
        return switch (obj) {
            case Tagged(Point(var x, _), _) -> "x = " + x;
            default -> "not tagged";
        };
    }

    public static void main(String[] args) {
        System.out.println(firstX(
                new Tagged(new Point(5, 9), "demo")));
    }
}
```

Use **JDK 21** and enable preview at both compile time and runtime:

```bash
javac --enable-preview --release 21 PreviewNames.java
java --enable-preview PreviewNames
```

Output:

```text
x = 5
```

If the project does not enable preview, use a regular variable name without using it: `Point(var x, var ignoredY)`. Unnamed patterns/variables only became a standard feature in Java 22 (JEP 456); that status does not apply retroactively to Java 21.

### 8.2. Parenthesized Patterns Were Removed From Java 21

Older preview examples may write `case (String s) ->` and call it a *parenthesized pattern*. **Java 21 removed parenthesized pattern syntax.** Write `case String s ->` in current Java 21 code. Similarly, older preview syntaxes using `case String s && condition` were replaced with `case String s when condition`.

### 8.3. “Deconstruction” Is a Term, Not Instantiation

You may encounter the terms *record deconstruction* or *deconstruction pattern* when reading documentation about records. In Java 21, map that to a **record pattern** deconstructing components. The form `Point(var x, var y)` is only a pattern in an allowed position; when creating an object, the syntax is `new Point(...)`.

## 9. A Java 21 Program to Practice Recognition

The **`PatternReader.java`** file below uses standard Java 21, **no preview required**:

```java
public class PatternReader {
    record Point(int x, int y) {}
    record Marker(Point point, String label) {}

    static String inspect(Object obj) {
        if (obj instanceof Marker(Point(var x, var y), String name)) {
            return "marker " + name + " at " + x + "," + y;
        }

        return switch (obj) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text(" + text.length() + ")";
            case Integer number when number > 0 -> "positive " + number;
            case Integer number -> "integer " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
            new Marker(new Point(2, 5), "A"),
            " ", "hi", 7, -2, null, 3.14
        };
        for (Object value : samples) {
            System.out.println(inspect(value));
        }
    }
}
```

Compile with JDK 21 or a newer JDK supporting Java 21 as the target, then run:

```bash
javac --release 21 PatternReader.java
java PatternReader
```

Stdout:

```text
marker A at 2,5
blank
text(2)
positive 7
integer -2
null
other
```

**Annotate the code directly to memorize the pattern names:**

- `Marker(Point(var x, var y), String name)` → **outer record pattern** `Marker`, **nested record pattern** `Point`, three **sub-type patterns** `var x`, `var y`, `String name`; they declare the variables `x`, `y`, `name`.
- `case String text when text.isBlank()` → **type pattern** `String text` inside a **guarded case label**.
- `case String text`, `case Integer number` → other **type patterns**; the variable names exist only within the branch or region allowed by flow scoping.
- `case null` and `default` → special labels, with no pattern variables.
- `record Point(...)`, `record Marker(...)` → type declarations; `new Marker(new Point(...), "A")` → data creation; **not** patterns.

## 10. Source-Reading Exercises and Answers

**Exercise 1.** In the following lines, pinpoint the exact part that is a pattern and name it:

```java
Object data = "abc";
boolean a = data instanceof String;
boolean b = data instanceof String value;
```

**Answer:** The line declaring `a` only performs a type test and uses no pattern; line `b` has the **type pattern** `String value`; the pattern variable name is `value`, not `data`. Using `value` outside the scope where Java knows the pattern matched is an error.

**Exercise 2.** In the following snippet, how many record patterns and how many type patterns are there?

```java
record Pair(int first, int second) {}
record Packet(Pair pair, String tag) {}

// Expression fragment inside a valid check branch:
obj instanceof Packet(Pair(var left, var right), String label)
```

**Answer:** Two **record patterns**: `Packet(...)` and `Pair(...)`. Three **type patterns**: `var left`, `var right`, `String label`. `left`, `right`, `label` are three pattern variables. The declarations `record Pair(...)` and `record Packet(...)` do not count as patterns.

**Exercise 3.** Is `case Integer n when n < 0 ->` a “when pattern” or a “negative number pattern”?

**Answer:** No. `Integer n` is a **type pattern**; `when n < 0` is a **guard**; the whole branch is called a **guarded case label**. In Java 21 there is no separate kind of pattern named “negative number pattern”.

**Exercise 4.** Why do the following two expressions have different version statuses?

```java
obj instanceof Point(var x, var y)
obj instanceof Point(var x, _)
```

**Answer:** The first line uses a **record pattern** with two **inferred type patterns**, which is standard in Java 21. The second line has an **unnamed pattern** `_`, which is a **Java 21 preview** feature and therefore requires `--enable-preview`. Both must be placed in a context with an appropriate `Point` declaration.

## 11. Checklist When Reviewing Java Code That Uses Patterns

1. **Identify the position:** after `instanceof`, in `case`, or inside the component list of a record pattern?
2. **Identify the core:** “type + variable” is a **type pattern**; “record name + list of sub-patterns” is a **record pattern**.
3. **Break down nested patterns:** count every record pattern and type pattern accurately, going from outside in.
4. **Separate variable names:** a pattern variable name can differ from the record component name; check its scope according to control flow.
5. **Separate labels and guards:** `case` is the position where a pattern is placed; `when` is a condition; `case null`, `default`, and `case` constants are not patterns.
6. **Check `switch` ordering:** specific branches before general branches to avoid dominance; check whether the branches are exhaustive.
7. **Check the version:** record patterns and pattern `switch` are standard in Java 21; `_` for unnamed patterns/variables is still preview; parenthesized patterns were removed.
8. **Read the context accurately:** `record Point(...)` declares data, `new Point(...)` instantiates, and only `Point(...)` in a pattern position is a record pattern.

## 12. Official References

- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): definition and grammar of `TypePattern`, `RecordPattern`, and pattern variable scope.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): guards, dominance, and `case` label kinds.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns as a standard feature in Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern `switch` as a standard feature in Java 21.
- [Oracle Java 21 — Unnamed Patterns and Variables](https://docs.oracle.com/en/java/javase/21/language/unnamed-variables-and-patterns.html) and [JEP 443](https://openjdk.org/jeps/443): distinguishing unnamed patterns from unnamed pattern variables, and preview requirements.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): standard/preview status and syntax changes across releases.
