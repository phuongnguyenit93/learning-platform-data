# Rules for Declaring Pattern Variables in Java

## 1. What Is a Pattern Variable and Where Is It Declared?

A **pattern variable** is a local variable **declared inside a pattern**. When the input value matches that pattern, Java creates and assigns a value to the variable according to the pattern's rules. If it does not match, the variable does not have a valid value to use. This declaration is tied to the matching operation, not a regular local variable declaration with an `=` sign.

A familiar example from Java 16:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

In `String text`:

- `String` is the **tested type** as well as the declared type of the variable;
- `text` is the **pattern variable name**;
- `value instanceof String text` checks whether `value` matches the `String` type;
- if it matches, the variable `text` is assigned the exact checked reference value and can be used in positions where the compiler confirms the pattern has matched.

Difference from traditional code:

```java
if (value instanceof String) {
    String text = (String) value; // Even after checking, you still have to cast.
}
```

Pattern variables help reduce manual casting, but they **do not automatically convert one data type to another** and do not become a `field` of a class.

### Main Declaration Positions by Version

| Pattern Usage Position | Declaration Example | Official Java Version |
| --- | --- | --- |
| `instanceof` type pattern | `value instanceof String text` | Java 16+ |
| `switch` type pattern | `case String text -> ...` | Java 21+ |
| `switch` type pattern with guard | `case String text when text.isBlank() -> ...` | Java 21+ |
| Record pattern | `value instanceof Point(int x, int y)` | Java 21+ |
| Record pattern using type inference | `value instanceof Point(var x, var y)` | Java 21+ |

**Choosing a JDK:** The `instanceof` examples in this article can be compiled with Java 17; the type `switch` and record pattern examples use Java 21 or later. These finalized features do not require `--enable-preview`. Within the same project, always check which version `javac` is targeting.

## 2. Syntax of a Type Pattern and Required Components

For a top-level type pattern, the pattern typically has the form:

```text
[final] ReferenceType variableName
```

When placed after `instanceof`:

```java
if (input instanceof String text) {
    // text is a String when the branch executes.
}
```

And in `switch` on Java 21:

```java
switch (input) {
    case String text -> System.out.println(text.length());
    default -> System.out.println("Other");
}
```

The two snippets above are **illustrative code fragments**, assuming the variable `input` has already been declared in a method. Specific rules:

1. **Must have a valid type and variable name.** For example, `String text`, `Number number`, `java.util.List<?> items`. The name must be a valid Java identifier and must not conflict with a local variable already in scope.
2. **Top-level type patterns use reference types.** In Java 17/21, `input instanceof int n` is invalid: `int` is a primitive type and is not valid for a type pattern in this position. To check a boxed value, use `input instanceof Integer n`.
3. **Do not write an initializer in the pattern.** Write `instanceof String text`; do **not** write `instanceof String text = "abc"`. Java assigns the variable when the pattern matches.
4. **One type pattern declares one variable name.** Do not write a comma-separated list of types/variables like a regular local declaration. If you need to extract multiple components of a `record`, use a record pattern with the exact number of components.
5. **Do not use `var` for a top-level type pattern** of `instanceof` or `case` in Java 21: `input instanceof var text` is invalid. `var` only serves for type inference in an appropriate **component type pattern** inside a record pattern.
6. **Variable names do not include array syntax after the identifier.** If an array type is needed, write the type in the type position (`String[] texts`) when valid; do not write `String texts[]` in a type pattern.
7. **Only use types compatible with the check.** The compiler rejects combinations that cannot match or `instanceof` checks against a pattern that is already guaranteed to be true statically. For example, a variable with static type `String` checked with `instanceof String text` will report an error because the pattern no longer checks anything useful.
8. **Generics must be type-safe.** With `Object input`, you can use `input instanceof java.util.List<?> items`; however, `input instanceof java.util.List<String> items` is invalid in this case because type arguments cannot be fully checked at runtime.

Note: the constraints of a **top-level type pattern** must not be mechanically applied to a **type pattern that is a component of a record pattern**. Primitive component types and `var` can be valid inside a record pattern, as shown in Section 6.

### Distinguishing Variable Kinds

```java
String existing = "hello";               // Regular local variable.
Object candidate = existing;              // Regular local variable.
if (candidate instanceof String matched) {
    System.out.println(matched);          // Pattern variable.
}
```

`matched` is not a method parameter, not a field, and cannot be "brought outside" the `if` simply by referencing its name directly. The fact that these variables all have type `String` does not make their declaration rules and scope the same.

## 3. Valid Declarations Tied to When the Pattern Actually Matches

A **syntactic declaration** may appear inside a condition, but the **variable is brought into use** only at positions where the compiler confirms the pattern has *definitely matched*.

### When `instanceof` Returns `true`

```java
Object data = "hello";
if (data instanceof String text) {
    System.out.println(text.toUpperCase()); // Valid.
} else {
    System.out.println("Không khớp");       // Do not use text here.
}
// Cannot arbitrarily use text here.
```

A pattern variable is initialized only when the pattern matches. With `null`, **a type pattern in `instanceof` does not match**: `null instanceof String text` returns `false` and does not initialize `text`.

### When Chaining Conditions with `&&`

```java
if (data instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

The right-hand side of `&&` only runs when the left-hand side is true, so `text` is already bound. You cannot do the symmetric thing with `||` as follows:

```java
// INVALID: the right-hand side may run when the pattern has not matched.
if (data instanceof String text || text.isBlank()) {
    System.out.println(data);
}
```

This is an example that **intentionally does not compile**, because Java cannot guarantee `text` has been declared and initialized at the point `isBlank()` is called.

### When Negating and Returning Early

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // Valid: reaching here means it must have matched.
}
```

The snippet above is **a method** that needs to be placed inside a class. At the point after the `if`, all continuing execution paths must have passed through a successful `value instanceof String text`.

What to remember when declaring: **scope is based on control-flow analysis**, not just curly braces. Detailed analysis of `if`/`while`/`for` branches should be studied further in the lesson on flow scoping.

## 4. Naming Rules: Do Not Conflict with a Local Variable in Scope

Pattern variables follow the same naming rules as Java local variables; you cannot redeclare a local name that is currently in effect in a conflicting scope.

```java
Object data = "Java";
String text = "existing";
if (data instanceof String text) { // INVALID: text is already declared.
    System.out.println(text);
}
```

This is an example that **intentionally does not compile**. The fix is to use a different, meaningful name:

```java
Object data = "Java";
String text = "existing";
if (data instanceof String matchedText) {
    System.out.println(matchedText);
}
```

Some helpful naming guidelines:

- Name according to the role of the data: `text`, `number`, `request`, `point`. Avoid `a`, `b` when there are multiple patterns.
- In a `switch` with multiple cases, name variables according to the data type used in that specific branch; do not try to use a variable name from one case in another case.
- When using nested record patterns, name each component according to its actual meaning, avoiding duplicate names in conflicting scopes.
- Avoid giving a pattern variable the same name as an existing local variable in the method, even when the code has many branches and braces.

Do not "fix" a conflict by assigning or casting an existing variable and assuming it becomes a pattern variable. Decide clearly which construct declares that name, which scope uses it, and which pattern supplies the value.

## 5. `final`, Assignment, and Local Variable Behavior

Since Java 16, a pattern variable is **not `final` by default**. It is a local variable and can be reassigned within its valid scope:

```java
Object data = "  Java  ";
if (data instanceof String text) {
    text = text.strip();          // Valid: text is not final by default.
    System.out.println(text);     // Java
}
```

Reassigning `text` only changes the reference value of the local variable `text`; **it does not change the variable `data`**. For mutable objects, mutating the object's state and reassigning the reference are two different things.

If you want to prevent reassignment, Java allows declaring `final` directly in the type pattern:

```java
Object data = "Java";
if (data instanceof final String text) {
    System.out.println(text.length()); // Valid.
    // text = "Other";                 // INVALID if uncommented: text is final.
}
```

Without reassignment, an ordinary pattern variable can be **effectively final**, which is useful when used in lambdas and contexts that require the value to remain unchanged. A variable that is reassigned is no longer effectively final.

**Design rule:** Usually you should keep a pattern variable at its initial value for readability. When you need to transform data (normalize, trim strings, compute a new value), consider creating a new variable name such as `normalizedText`. Just because reassignment is allowed does not mean you should always do it.

## 6. Declarations in `switch` and Record Patterns on Java 21

### Pattern Variable in a `case`

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "blank";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

This is an illustrative method requiring **Java 21+**. `text` in the case with `when` is bound before the `text.isBlank()` condition is evaluated. Each pattern's variable is only usable where permitted in its **corresponding case/guard**, not as a shared variable across cases. `case null` handles `null` and does not declare a pattern variable. Do not place a general case that dominates specific cases after it.

When `when` is false, the guarded `String` pattern is not selected; the next `String` case can match and declare the variable for that branch.

### Declaring One or More Variables from a Record Pattern

With a record:

```java
record Point(int x, int y) {}
```

Inside a method, with `Object data`:

```java
if (data instanceof Point(int x, int y)) {
    System.out.println(x + ", " + y);
}
```

Here `int x` and `int y` are **component type patterns** located **inside** `Point(...)`. `Point(...)` is a record pattern; it checks the record type and matches each component in declaration order. Java 21 also allows inferring component types:

```java
if (data instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

In this example, `x` and `y` are inferred as `int` because the record has two `int` components. **This does not make `input instanceof var something` valid** at the top level.

Record patterns can be nested when a component contains another record:

```java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

// Inside a method, with Object data:
if (data instanceof Line(Point(int x1, int y1), Point(int x2, int y2))) {
    System.out.println(x1 + "," + y1 + " -> " + x2 + "," + y2);
}
```

This snippet illustrates the syntax and needs to be placed in an appropriate class/method. If combined with the previous `Point` example, **declare `Point` only once**.

**Note on `null`:** A top-level type pattern in `instanceof` does not match `null`. In Java 21, some **component type patterns** of a record can match `null` when they are unconditional with respect to the component type, so you should not generalize that every pattern variable is always non-`null`. The record pattern itself still does not match a `null` record value.

## 7. Complete Java 17 Example: Declaration, Checking, and Scope

Create a file `PatternVariableRules17.java` with the **entire** following content:

```java
public class PatternVariableRules17 {

    static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "String(" + text.length() + "): " + text;
        }

        if (input instanceof Integer number) {
            return "Integer: " + number;
        }

        return "Unsupported";
    }

    static int lengthOrZero(Object value) {
        if (!(value instanceof String text)) {
            return 0;
        }
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(21));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(lengthOrZero("abc"));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 --release 17 PatternVariableRules17.java
java PatternVariableRules17
```

Exact output:

```text
String(4): Java
Integer: 21
Unsupported
Unsupported
3
```

**Explanation:** `text` only exists where `String` has been checked; `number` is only bound to the `Integer` branch; `null` values and whitespace-only strings both fall through to `Unsupported`. In `lengthOrZero`, when the input is not a `String`, the method exits early; if execution continues, `text` is guaranteed to have a suitable value.

On-the-spot check: adding `System.out.println(text);` after the `if` chain in `describe` will cause a compilation error because the pattern variable is not guaranteed in that scope. **Do not treat this modified snippet as a valid complete program.**

## 8. Complete Java 21 Example: Declarations in `switch` and Record Patterns

Create `PatternVariableRules21.java`:

```java
public class PatternVariableRules21 {

    record Pair(int left, int right) {}

    static String explain(Object value) {
        return switch (value) {
            case null -> "null";
            case Pair(int left, int right) ->
                    "Pair: " + left + " + " + right + " = " + (left + right);
            case String text when text.isBlank() -> "blank";
            case String text -> "Text: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(explain(new Pair(2, 3)));
        System.out.println(explain(" "));
        System.out.println(explain("Java"));
        System.out.println(explain(7));
        System.out.println(explain(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 PatternVariableRules21.java
java PatternVariableRules21
```

Exact output:

```text
Pair: 2 + 3 = 5
blank
Text: Java
Integer: 7
null
```

**Explanation:** `Pair(int left, int right)` declares two component variables in a record pattern; the `String text` and `Integer number` cases declare variables using type patterns; `when` can access `text` because the type pattern has matched. `case null` has no variable and must be handled separately. Moving the general `case String text` before `case String text when ...` can create a dominated case, which is rejected at compile time.

## 9. Common Declaration Errors and How to Fix Them

| Case | Why It Is Wrong or Misleading | How to Handle It |
| --- | --- | --- |
| `input instanceof int n` | Java 17/21 top-level type patterns require a reference type | `input instanceof Integer n` |
| `input instanceof var x` | `var` is invalid for a top-level type pattern | Use an explicit type, e.g., `String x` |
| `input instanceof String s = "x"` | Patterns do not have initializers like local declarations | Remove `= "x"`; use the bound value |
| Local variable `text` already exists and `String text` is declared in the same conflicting scope | Duplicate declaration name | Choose another name, e.g., `matchedText` |
| `input instanceof java.util.List<String> xs` | Generic type arguments cannot be fully checked at runtime | Use `java.util.List<?> xs` then check elements appropriately |
| Using a pattern variable after an `else`/`\|\|` branch without guaranteed match | No proof that the variable has been initialized | Only use in definitely matched branches/positions |
| Using `case String s` with `--release 17` | Pattern `switch` is finalized in Java 21 | Upgrade target to 21 or use `instanceof` |
| Assuming `text` is `final` by default | Since Java 16, pattern variables are not `final` by default | Write `final String text` if you want to forbid reassignment |
| Equating top-level rules with record components | `Point(var x, var y)` has its own syntax | Distinguish record patterns from top-level type patterns |
| Assuming `null` never produces a reference-typed pattern variable | Top-level `instanceof` does not match `null`; nested components have exceptions | Handle `null` appropriately for the matching context |

Do not use newer Java exceptions or unenabled preview syntax to "fix" examples intentionally targeting Java 17/21.

## 10. Exercises to Verify Your Understanding of Declaration Rules

1. **Identify:** In `if (obj instanceof String name)`, point out the declaration position, the variable's type, the condition that causes the variable to be assigned, and where it can definitely be used.
2. **Fix syntax:** Convert `obj instanceof int i`, `obj instanceof var x`, and `obj instanceof String s = "a"` into valid type pattern declarations for the corresponding data scenarios.
3. **Rename:** In a method that already has a local variable `String name`, handle `Object input` with a type pattern without redeclaring `name`.
4. **Scope:** Predict which snippets compile: `obj instanceof String s && s.length() > 0`; `obj instanceof String s || s.isEmpty()`; `if (!(obj instanceof String s)) return;` followed by using `s` afterward.
5. **Variable immutability:** Give an example of reassigning a pattern variable, then use `final` so the compiler rejects that same assignment. Explain why the source variable is not reassigned.
6. **Record pattern (Java 21):** Define `record Range(int min, int max)` and write both `Range(int min, int max)` and `Range(var min, var max)`; indicate the actual types of the two variables.
7. **Check version:** Compile the Java 17 program with `--release 17` and the Java 21 program with `--release 21`. Try changing only `--release 17` for the Java 21 program to understand language version errors.

**Self-assessment criteria:** You know how to write valid type patterns, distinguish the declared name/type/bound value, know why `var` or primitive types cannot be used directly at the top level, know how to avoid name collisions, know the minimum safe scope, and can read component variable declarations in record patterns.

## 11. Official References

- [Java Language Specification, Java SE 21 `14.30 — Patterns`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern syntax, record patterns, matching rules, and pattern variable initialization.
- [Java Language Specification, Java SE 21 `6.3 — Scope of a Declaration`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): pattern variable scope in `instanceof`, conditional operators, and `switch`.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): Java 16, supports variable declarations in `instanceof` and removes the default `final` rule.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): Java 21, type patterns in `case`, guards, and `null` handling.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): Java 21, component variable declarations and nested record patterns.

When writing real code, check both `java -version` and `javac -version`, then use `--release` matching your project's compilation target.
