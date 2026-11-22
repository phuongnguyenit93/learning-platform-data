# Testing Invalid Nested Structures in Nested Record Patterns (Java 21+)

## 1. Objective and Scope

A **nested record pattern** lets you test a value and deconstruct multiple `record` levels within the same pattern. When testing, you need to clearly distinguish between **patterns that are written incorrectly and therefore fail to compile** and **valid patterns where actual runtime data does not match**. These two cases have different detection mechanisms and different ways of writing tests.

Record patterns became a standard feature in **Java 21** (JEP 440). The examples use `instanceof` and run on JDK 21 or later without `--enable-preview`. Java 17 supports declaring `record` types, but does not yet support record patterns in `instanceof`.

Three-level model example:

```java
record Leaf(int id) {}
record Envelope(Leaf leaf, Object payload) {}
record Root(Envelope envelope) {}
```

Valid pattern:

```java
Object input = new Root(new Envelope(new Leaf(7), "data"));

if (input instanceof Root(Envelope(Leaf(var id), String text))) {
    System.out.println(id + " - " + text); // 7 - data
}
```

The structure matches from the outside in: `Root` has exactly **one** component (`Envelope`); `Envelope` has exactly **two** components (`Leaf` and `Object`); `Leaf` has exactly **one** component (`int`). The pattern `String text` narrows the `payload` component whose declared type is `Object`. The variables `id` and `text` are only in scope on the matched path.

## 2. Classification of Cases to Test

| Category | Example | Result to Verify |
| --- | --- | --- |
| **Structurally invalid pattern in source code** | Wrong component count, deconstructing a non-record class, type-incompatible subpattern, duplicate variable name | `javac` rejects the code and reports a compilation error |
| **Valid pattern, non-matching runtime data** | Wrong root object type, nested record is `null`, runtime value has wrong type | `instanceof` returns `false`; the body does not execute |
| **Valid pattern and matching data** | Correct types, valid record levels, all subpatterns match | `instanceof` returns `true`; pattern variables are assigned |
| **Exception thrown by accessor** | A custom record accessor throws an exception | Pattern matching may throw `MatchException`; must not be treated as `false` |

A properly constructed Java `record` always has the exact number of components declared in its header. Therefore, "data with missing/extra components" is **not** a situation that can be passed into a normal Java record at runtime. Missing/extra **subpatterns in source code** are errors caught by the compiler; `null` values or wide-typed data that do not match are separate runtime cases.

## 3. Runtime Testing with a Self-Contained Java Program

Create the file **`InvalidNestedPatternTests.java`**:

```java
public class InvalidNestedPatternTests {
    record Leaf(int id) {}
    record Envelope(Leaf leaf, Object payload) {}
    record Root(Envelope envelope) {}

    static void assertMatch(String name, boolean actual, boolean expected) {
        if (actual != expected) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual
            );
        }
        System.out.println(name + " => " + actual + " (OK)");
    }

    public static void main(String[] args) {
        Object valid = new Root(new Envelope(new Leaf(7), "data"));
        Object nullLeaf = new Root(new Envelope(null, "data"));
        Object nullEnvelope = new Root(null);
        Object wrongRoot = "not a Root";
        Object wrongPayload = new Root(new Envelope(new Leaf(7), 99));
        Object nullRoot = null;

        // All levels match, payload type matches, and condition id == 7 holds.
        assertMatch("valid",
            valid instanceof Root(Envelope(Leaf(var id), String text))
                && id == 7,
            true);

        // Leaf is null, so Leaf(var id) does not match.
        assertMatch("null-leaf",
            nullLeaf instanceof Root(Envelope(Leaf(var id), var payload)),
            false);

        // Envelope is null, so Envelope(...) does not match.
        assertMatch("null-envelope",
            nullEnvelope instanceof Root(Envelope(var leaf, var payload)),
            false);

        // The outermost value is not a Root.
        assertMatch("wrong-root",
            wrongRoot instanceof Root(Envelope(var leaf, var payload)),
            false);

        // payload is declared as Object; its runtime value is Integer, not String.
        assertMatch("wrong-payload",
            wrongPayload instanceof Root(Envelope(Leaf(var id), String text)),
            false);

        // The entire value being tested is null.
        assertMatch("null-root",
            nullRoot instanceof Root(Envelope(var leaf, var payload)),
            false);

        // var leaf accepts null: it does not require matching Leaf(...).
        assertMatch("var-null-leaf",
            nullLeaf instanceof Root(Envelope(var leaf, var payload)),
            true);

        System.out.println("7/7 tests passed");
    }
}
```

Compile and run:

```bash
javac --release 21 InvalidNestedPatternTests.java
java InvalidNestedPatternTests
```

**Exact stdout** when all 7 test cases pass:

```text
valid => true (OK)
null-leaf => false (OK)
null-envelope => false (OK)
wrong-root => false (OK)
wrong-payload => false (OK)
null-root => false (OK)
var-null-leaf => true (OK)
7/7 tests passed
```

If the actual value differs from the expected value, `assertMatch` throws an `AssertionError`, causing the run to fail instead of silently printing incorrect results. This program can be executed directly in CI with JDK 21+ without depending on any external test library.

### Why does the `var-null-leaf` case match?

You need to distinguish a **nested record pattern** `Leaf(var id)` from a **component pattern** `var leaf`:

- `Leaf(var id)` requires the component to actually be a non-`null` `Leaf`; `null` does not match a record pattern.
- `var leaf` binds the value of the `leaf` component using the static type inferred by the compiler; inside a record's component pattern list, this pattern can also accept `null`.
- `Root(Envelope(var leaf, var payload))` still fails if the **entire `Envelope`** is `null`, because at that level we are using the record pattern `Envelope(...)`.

Therefore, you should not write tests under the assumption that "whenever any component is `null`, every record pattern fails." Check which kind of pattern is being used to match that component.

### Why is `wrong-payload` a valid test case?

`Envelope.payload` is declared as `Object`, so it can hold a `String`, an `Integer`, or `null`. The pattern `String text` checks the actual runtime type; with an `Integer`, the entire nested pattern evaluates to `false`.

Conversely, if the component were declared as `String`, Java would not allow passing an `Integer` directly when constructing the record just to create "wrong-type data." To test varied data, model a wide-typed component at places where the domain genuinely allows multiple types.

## 4. Testing Invalid Patterns with Negative Compilation Tests

The following cases **must fail to compile**. These are **negative tests**, so a `javac` invocation returning a non-zero exit code is the expected result. Do not put these invalid snippets into the runtime program in Section 3, because the program will fail to compile.

Create a separate file **`BadNestedPatterns.java`** with one intentional error:

```java
public class BadNestedPatterns {
    record Leaf(int id) {}
    record Envelope(Leaf leaf, String tag) {}

    static boolean test(Object input) {
        // Invalid: Leaf has only one component, but the pattern requires two.
        return input instanceof Envelope(Leaf(var id, var extra), var tag);
    }
}
```

Verify:

```bash
javac --release 21 BadNestedPatterns.java
```

**Expected:** compilation fails because `Leaf` declares one component `id`, whereas `Leaf(var id, var extra)` has two subpatterns. The exact diagnostic message depends on the JDK version; the reliable test condition is that **`javac` rejects the code** and indicates a pattern arity error.

To test the next three errors, **replace only the expression on the right side of `instanceof`** in the `test` method of the file above, then re-run the compile command. Each variant must be tested **separately**, one error at a time:

| Invalid Pattern Expression | Reason the Compiler Must Reject It |
| --- | --- |
| `Envelope(Leaf(var id, var extra), var tag)` | `Leaf` has only 1 component, but the pattern has 2. |
| `Envelope(Leaf(var id), Leaf(var other))` | The `tag` component has type `String`, which is incompatible with the record pattern `Leaf(...)`. |
| `Envelope(Leaf(var id), String(var text))` | `String` is a regular class, not a `record`, so it cannot be deconstructed with `String(...)`. |
| `Envelope(Leaf(var same), var same)` | The pattern variable `same` is declared twice in the same nested record pattern. |

The `Envelope(...)` syntax must have exactly two subpatterns in component order. Similarly, for each inner record, you must also check the count and types of the components at that level.

A **fixed** version using the same two records `Leaf` and `Envelope` can be written as:

```java
static boolean test(Object input) {
    return input instanceof Envelope(Leaf(var id), var tag) && id >= 0;
}
```

This snippet is an **alternative illustrative method** inside the `BadNestedPatterns` class above. `id` is available on the right-hand side of `&&` because the right-hand side is only evaluated when the pattern on the left matches.

### How to Organize Negative Tests in a Project

1. Place each invalid code sample in a **separate** compilation test file, isolated from the runnable application's source directory.
2. Invoke `javac --release 21` for each sample and assert a **non-zero exit code**.
3. Match the compiler error category (arity, non-record, incompatible type, duplicate binding) rather than matching exact error message text, because diagnostic formatting may change across JDK releases.
4. Include at least one **positive control** that compiles successfully to ensure the JDK environment and compile command actually work; the program in Section 3 serves as a positive control.
5. If a negative test unexpectedly compiles, that test **FAILS** and you must review your language expectations; never interpret "javac reported no errors" as a PASS.

You can also add a case with mismatched nesting parentheses, such as a missing `)`, to test pure syntax errors. However, distinguish syntax errors from the four semantic pattern errors in the table above.

## 5. Cases That Should Not Be Equated with "Invalid Patterns"

### 5.1. `null` Is Non-Matching Data, Not a Compilation Error

`input instanceof Root(Envelope(Leaf(var id), var payload))` is a valid expression. If `input`, `envelope`, or `leaf` is `null` at a level requiring a record pattern, the match evaluates to `false`. Do not expect a `NullPointerException` merely because `instanceof` encounters `null`.

### 5.2. Pattern Variables Only Exist on the Matched Branch

The following is valid:

```java
if (input instanceof Root(Envelope(Leaf(var id), var payload))
        && id > 0) {
    System.out.println(id);
}
```

However, using `id` on the right-hand side of `||` as shown below is **invalid**, because the right-hand branch can be evaluated when the left pattern does not match:

```java
// Invalid example, for negative compilation testing only.
if (input instanceof Root(Envelope(Leaf(var id), var payload))
        || id > 0) {
    System.out.println("checking");
}
```

This is a **flow scoping** error, not a missing component in the record structure.

### 5.3. An Exception from an Accessor Is Not a `false` Result

A record pattern accesses components through the record's **accessor** methods. If a custom accessor throws an exception, pattern matching can throw `MatchException` with the accessor's exception as its cause, rather than simply returning `false`. Therefore, in systems with custom accessors, test the accessor failure path separately and do not swallow exceptions as "non-matching data."

### 5.4. Do Not Use Preview Syntax When Testing Standard Java 21 Syntax

To test the standard behavior of record patterns in Java 21, use `javac --release 21` and avoid syntax from other preview features. A test that unexpectedly compiles on a newer JDK may be due to language changes or preview flags; pin the Java release and toolchain version in CI.

## 6. Test Case Design Checklist

| Question | How to Verify |
| --- | --- |
| Right number of components at each level? | Negative compilation test for missing/extra subpatterns. |
| Is every level a `record` when using `Type(...)`? | Negative compilation test for a regular class such as `String(...)`. |
| Are subpattern types compatible with the components? | Negative compilation test for non-convertible types. |
| Are any pattern variables duplicated or used out of scope? | Negative compilation test. |
| Is a nested record or the root `null`? | Runtime test expecting `false` where that position uses a record pattern. |
| Does a wide-typed component hold an unexpected subtype? | Runtime test expecting `false` for a non-matching type pattern. |
| Is a `null` component captured with `var`? | Runtime test confirming it can still match. |
| Does the success branch extract the right values and `&&` condition? | Positive runtime test verifying variables and handling output. |
| Can an accessor throw an exception? | Separate `MatchException` test when custom accessors are used. |

## 7. Practice Exercises

Given:

```java
record Coordinate(int x, int y) {}
record Segment(Coordinate start, Coordinate end) {}
```

1. Write a valid pattern that extracts `start.x` and `end.y` from an `Object` containing a `Segment`.
2. Create a negative test with `Segment(Coordinate(var x), var end)`. At which level is it invalid?
3. Given `new Segment(null, new Coordinate(3, 4))`, predict the result when matching `start` with `Coordinate(...)`; then change the pattern for `start` to `var start` and explain the difference.

Reference solution:

```java
Object candidate = new Segment(
    new Coordinate(1, 2),
    new Coordinate(3, 4)
);
if (candidate instanceof Segment(
        Coordinate(var startX, var startY),
        Coordinate(var endX, var endY))) {
    System.out.println(startX + " -> " + endY); // 1 -> 4
}
```

In question 2, `Coordinate` has two components, so `Coordinate(var x)` has the wrong subpattern arity at **compile time**. In question 3, the record pattern for `start` does not match `null`, so the entire pattern fails; `var start` can accept `null` and allows the `end` part to continue matching.

**Official references:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html) and [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
