# Does `null` match a type pattern?

**Topic:** Java Core Pattern Matching → Null and type compatibility  
**Version milestone:** Java 17+ for `instanceof` type patterns; Java 21+ for pattern matching in `switch` and record patterns.

## 1. Exact answer

**When using `instanceof` with a type pattern, `null` always evaluates to `false`.** For example, if `Object value = null`, the expression `value instanceof String text` does not match, the variable `text` is not bound to a value, and the corresponding `if` branch does not execute.

However, this should not be overgeneralized into “`null` never matches any type pattern” across all of Java 21: **a type pattern nested directly inside a record pattern can be *null-matching*** if that pattern is *unconditional* for the type of the record component. In that case, the nested pattern variable can receive the value `null`. This is a specific case defined in the Java Language Specification §14.30.1–14.30.2.

| Scenario | Is `null` considered a match? | Key takeaway |
| --- | --- | --- |
| `value instanceof String s` with `value == null` | **No** | Evaluates to `false`, does not initialize `s` |
| `value instanceof Object o` semantically with `value == null` | **No** | `instanceof` does not treat `null` as an instance; some redundant type patterns are also rejected at compile time |
| `switch (value)` with `case String s`, `value == null` | **No** | Handle a `null` selector explicitly with `case null` when needed |
| `record Box(String value)` matched by `Box(String s)` with **non-null Box** but component `value == null` | **Yes, for the nested pattern `String s`** | The variable `s` is bound to `null`; check before calling methods |

Two distinct cases must be separated clearly: whether **the top-level value being tested** is `null`, and whether **a component inside a record** is `null`.

## 2. Why is `null instanceof T` `false`?

`null` represents the absence of a reference to any object; it is not a `String`, `Integer`, or `Object` instance with a concrete runtime type. The `instanceof` operator checks whether **the current reference value** is an instance of the target type. Because there is no object when the reference is `null`, the result is `false`.

For example, the following statements are valid on Java 17+:

```java
Object value = null;

System.out.println(value instanceof String);     // false
System.out.println(value instanceof String text); // false
System.out.println(value instanceof Object);     // false
```

Note: the example uses a variable with static type `Object` so that the type pattern `String text` is a meaningful check. For an expression whose static type is already `String`, writing `expr instanceof String s` may be rejected by Java because the pattern check is redundant under the rules of `instanceof` type patterns; do not confuse this compile-time error with the runtime result of checking `null`.

**The declared type and the actual value are two different things.** For example, `String name = null;` is a valid declaration, but no `String` object is referenced until `name` is assigned an actual string.

## 3. Impact on `if`, `else`, and flow scoping

A common practical pattern:

```java
static String explain(Object value) {
    if (value instanceof String text) {
        return "String dài " + text.length();
    }
    if (value == null) {
        return "Không có giá trị";
    }
    return "Không phải String";
}
```

- For `"Java"`, `instanceof` matches and `text.length()` returns `4`.
- For `null`, the `String text` branch is skipped and the `value == null` branch executes.
- For `42` (boxed into `Integer`), it matches neither `String` nor `null`.

Conditions with `&&` leverage *short-circuit* evaluation: `text` is only read after the pattern has matched.

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

If `value == null`, the left-hand side is `false`, so `text.isBlank()` is not called and no `NullPointerException` occurs from this operation.

With negation, the `instanceof` result is inverted, but it **does not create a new object**:

```java
if (!(value instanceof String text)) {
    // Reached here when value is null or not a String.
    return "Không phải String";
}
// After the guard return, text is guaranteed to have matched:
return text.toUpperCase();
```

The final snippet is illustrative code inside a method returning `String`; to run a standalone example, see the complete program in Section 6. Do not call `text.toUpperCase()` inside the negated branch itself: that is the path where the pattern did not match.

## 4. Handling `null` with pattern matching in `switch` (Java 21+)

Pattern matching for `switch` became a standard feature in Java 21. With a `null` selector, a top-level type pattern such as `case String s` **does not accept `null`**. Instead, `case null` handles this value:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

`case null` is a **case label for the null value**, not a type pattern. It allows you to express the `null`-handling branch explicitly.

**Be careful with `default`:** in a Java 21 `switch`, if the selector is `null` and there is no `case null` (or combined label `case null, default`), the `switch` typically throws `NullPointerException` before entering any normal branch. Simply adding `default` does not mean `null` will be handled there. For example, `switch (value) { case String s -> ...; default -> ...; }` does not automatically route `null` to `default`.

If you do not want to use `case null`, check `value == null` before the `switch`. Avoid using `case Object obj` as a way to implicitly cover `null`: a `null` selector still follows the `switch` null-handling rules.

## 5. Important Java 21 exception: type patterns nested in records

The Java 21 specification defines a **null-matching type pattern** when a type pattern appears **directly** in the component list of a record pattern, and that type pattern is *unconditional* for the declared type of the corresponding component. When this condition holds, a `null` component **matches the nested type pattern** and the pattern variable is initialized to `null`.

Consider two records:

```java
record TextBox(String value) {}
record WideBox(Object value) {}
```

For `TextBox`, the component has declared type `String`. The pattern `String text` is unconditional for `String`, so:

```java
new TextBox(null) instanceof TextBox(String text) // true on Java 21+
```

Here, the **`TextBox` object is not null**. Only its `value` component is `null`. When the record pattern matches, `text == null` is `true`. Calling `text.length()` without checking will throw `NullPointerException`.

For `WideBox`, the component has declared type `Object`. The pattern `String text` is **not** unconditional for `Object`, so:

```java
new WideBox(null) instanceof WideBox(String text) // false on Java 21+
```

The difference lies in **the declared type of the record component**. The specification uses the unconditionality of the type pattern to determine whether `null` is accepted inside a record pattern; seeing the syntax `String text` does not mean it has the same behavior in every position.

Do not confuse this with a record pattern receiving a `null` selector:

```java
Object value = null;
boolean result = value instanceof TextBox(String text); // false
```

**A top-level record pattern does not match a `null` reference.** The special case only applies to *the type pattern of a component inside an existing record instance*.

## 6. Standalone runnable example comparing all three scenarios

Create the file **`NullTypePatternDemo.java`**, using JDK 21 or later:

```java
public class NullTypePatternDemo {
    record TextBox(String value) {}
    record WideBox(Object value) {}

    static String byInstanceof(Object value) {
        if (value instanceof String text) {
            return "STRING:" + text.length();
        }
        return value == null ? "NULL" : "OTHER";
    }

    static String bySwitch(Object value) {
        return switch (value) {
            case null -> "SWITCH_NULL";
            case String text -> "SWITCH_STRING:" + text;
            default -> "SWITCH_OTHER";
        };
    }

    static String byRecord(Object value) {
        return switch (value) {
            case null -> "RECORD_INPUT_NULL";
            case TextBox(String text) ->
                    text == null ? "TEXTBOX_NULL" : "TEXTBOX:" + text;
            case WideBox(String text) -> "WIDEBOX_STRING:" + text;
            case WideBox(var other) -> "WIDEBOX_OTHER:" + other;
            default -> "RECORD_OTHER";
        };
    }

    public static void main(String[] args) {
        Object missing = null;
        System.out.println(missing instanceof String);
        System.out.println(missing instanceof String text);
        System.out.println(missing instanceof Object);

        System.out.println(byInstanceof(null));
        System.out.println(byInstanceof("Java"));
        System.out.println(byInstanceof(42));

        System.out.println(bySwitch(null));
        System.out.println(bySwitch("ok"));
        System.out.println(bySwitch(42));

        System.out.println(byRecord(new TextBox(null)));
        System.out.println(byRecord(new TextBox("ok")));
        System.out.println(byRecord(new WideBox(null)));
        System.out.println(byRecord(new WideBox("ok")));
        System.out.println(byRecord(null));

        System.out.println(new TextBox(null) instanceof TextBox(String s));
        System.out.println(new WideBox(null) instanceof WideBox(String s));
    }
}
```

Compile and run:

```bash
javac --release 21 NullTypePatternDemo.java
java NullTypePatternDemo
```

Expected output:

```text
false
false
false
NULL
STRING:4
OTHER
SWITCH_NULL
SWITCH_STRING:ok
SWITCH_OTHER
TEXTBOX_NULL
TEXTBOX:ok
WIDEBOX_OTHER:null
WIDEBOX_STRING:ok
RECORD_INPUT_NULL
true
false
```

**Breakdown of easily confused lines:**

1. The first three `false` lines prove that `missing == null` is not an instance of `String` or `Object`; using a type pattern in `instanceof` does not make `null` match either.
2. `byInstanceof(null)` returns `NULL` because the `instanceof` condition fails; `"Java"` returns `STRING:4`.
3. `bySwitch(null)` enters `case null` and returns `SWITCH_NULL`, not `case String text` or `default`.
4. `byRecord(new TextBox(null))` matches `TextBox(String text)`; the variable `text` is actually `null`, so it returns `TEXTBOX_NULL`.
5. `byRecord(new WideBox(null))` does **not** match `WideBox(String text)` but matches `WideBox(var other)`, where `other` receives `null`; string concatenation prints `WIDEBOX_OTHER:null`.
6. `byRecord(null)` handles the `null` selector via `case null`; it cannot match `TextBox(...)` or `WideBox(...)`.
7. The last two lines (`true`, `false`) directly test the null-matching exception of nested type patterns in records: component type `String` versus `Object`.

The program uses features finalized in Java 21, **without needing `--enable-preview`**.

## 7. Decision table when handling potentially `null` data

| Input | Check form | Result or branch |
| --- | --- | --- |
| `Object x = null` | `x instanceof String s` | `false` |
| `Object x = "Hi"` | `x instanceof String s` | `true`, `s = "Hi"` |
| `Object x = 5` | `x instanceof String s` | `false` |
| `Object x = null` | `x == null` | `true` |
| `Object x = null` | `switch (x)` with `case null` | Enters `case null` |
| `Object x = null` | `switch (x)` with only `case String s` and `default` | Throws `NullPointerException` |
| `new TextBox(null)` | `instanceof TextBox(String s)` | `true`; `s == null` |
| `new WideBox(null)` | `instanceof WideBox(String s)` | `false` |

**Design tip:** if `null` is a valid business input, model it as an explicit branch and write tests for it. With nested record patterns, consider the nullability of each component, even when the outer record is non-null.

## 8. Common misconceptions and errors

- **“The variable's type is `String`, so `null` must match `String`.”** False: a variable's static type does not change the fact that its runtime value is `null`. `instanceof` inspects the actual object.
- **“`instanceof` throws `NullPointerException` when the variable is null.”** False: `instanceof` itself on a `null` reference returns `false`. An exception can only come from calling a method on `null` in another step.
- **“Entering the `else` branch means the value is null.”** False: it could be a non-matching type, such as `Integer` instead of `String`; if you need to distinguish them, check `value == null`.
- **“A pattern variable can be used even when it didn't match.”** False: with `instanceof`, a pattern variable is only in scope where control flow proves a match; it cannot be used in the failure branch.
- **“`switch`'s `default` automatically catches `null`.”** False in the Java 21 scenario described; use `case null` or a prior `null` check.
- **“No `String s` pattern ever accepts `null`.”** Inaccurate when referring to a type pattern nested directly in a record pattern that is unconditional for the corresponding record component.
- **“If a record contains null, the record itself is null.”** False: `new TextBox(null)` is a valid record object with a null component; only a top-level `null` causes the record pattern not to match.
- **“If a record pattern matches, every component is guaranteed to be non-null.”** False: a null-matching nested type pattern can bind the variable to `null`, so appropriate checks must be applied before calling methods.

## 9. Practice exercises

1. Given `Object x = null;`, predict the results of `x instanceof String`, `x instanceof Integer i`, `x instanceof Object`, and `x == null`, then verify them.
2. Write a method that accepts `Object` and returns three distinct results for `null`, `String`, and other types; use `instanceof String s` in an `if` to print the length safely.
3. Create a Java 21 `switch` with `case null`, `case String s`, and `default`. Try removing `case null` when passing `null` and observe the exception; then restore the safe branch.
4. Define `record TextBox(String value)` and `record WideBox(Object value)`. Given a `null` component, explain why `TextBox(String s)` can match while `WideBox(String s)` does not.
5. Given `new TextBox(null)`, write a record pattern branch that safely handles the variable `s` before calling `s.length()`; add a test to ensure it does not throw `NullPointerException`.

**Passing criteria:** distinguish a top-level null reference from a null component inside a record, accurately predict `instanceof` results, understand the role of `case null`, and explain the *null-matching* condition of nested type patterns in Java 21.

**Standard references:**

- [JLS Java SE 21 — `instanceof` operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2).
- [JLS Java SE 21 — kinds of patterns and null-matching (§14.30.1)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1).
- [JLS Java SE 21 — pattern matching (§14.30.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2).
- [JLS Java SE 21 — label selection in `switch` (§14.11.1.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2).
