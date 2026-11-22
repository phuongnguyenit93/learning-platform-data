# Testing Patterns with Generic Records in Java 21+

## 1. Testing Objectives

When using **generic records** together with **record patterns**, we test more than just whether “the record has the right type.” We need to verify:

1. **Static types are inferred correctly** for `var` variables inside a record pattern.
2. **Nested patterns** match accurately at each level.
3. **`null` at the root record, child record, and component** behaves differently as expected.
4. **Generic type erasure** limits runtime type checking in specific ways.
5. **Guarded cases and fallback branches** execute in the right order and are not dominated.
6. **Intentionally invalid code must be rejected by the compiler**, not just testing cases that run successfully.

Starting in **Java 21**, record patterns are officially standardized (JEP 440) and can be used with `instanceof` and `switch`. Pattern matching for `switch` is also standard in Java 21 (JEP 441). The examples in this article run on **JDK 21 and later** without needing `--enable-preview`. `record` became official in Java 16, but **`record` supporting generics** does not mean every Java version with records supports **record patterns**.

This topic belongs to the **Testing** category: all explanations about generics and patterns are tied to test cases, outputs, failure modes, and verification strategies.

## 2. Sample Model: Generic Records and Types Used as Test Data

Three generic records:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, Box<T> payload) {}
```

With these, we can create:

```java
Pair<String, Integer> scores = new Pair<>("ada", 9);
Envelope<String> message = new Envelope<>("E1", new Box<>("java"));
Box<?> unknown = new Box<>(42);
```

**Static types** carry important information:

- `Pair<String, Integer>` tells the compiler that `left` has type `String` and `right` has type `Integer` when compiling the code.
- `Envelope<String>` tells the compiler that `payload` has type `Box<String>`, provided the objects obey the compiler-checked generic constraints.
- `Box<?>` only guarantees that it is a `Box` with an unknown type parameter. `value()` may return a `String`, `Integer`, `null`, or another reference value; it cannot be assumed to always be a `String`.

**Type erasure:** Java does not retain all generic type arguments in the runtime type of each object in a way that allows checking `Box<String>` vs. `Box<Integer>` with `instanceof` on an `Object`. The fact that a **record pattern can infer types from compile-time context** is not runtime proof that every object from untrusted data has the right generic type.

## 3. Testing Type Inference of Generic Record Patterns

Suppose a method parameter has the type:

```java
Pair<String, Integer> pair
```

We can write:

```java
return switch (pair) {
    case null -> "null-pair";
    case Pair(var name, var score) when name != null && score != null ->
            name.toUpperCase() + ":" + (score + 1);
    case Pair(var name, var score) -> "partial";
};
```

This is an **illustrative snippet inside a method returning `String`**. The complete program is in Section 7.

Key points to test:

- The pattern `Pair(var name, var score)` does not explicitly write `Pair<String, Integer>`; the compiler uses the **static type context of the selector** to infer the generic type arguments for the pattern.
- `name` is inferred as `String`, so calling `name.toUpperCase()` is valid.
- `score` is inferred as `Integer`, so adding `1` works via unboxing.
- The pattern does not automatically validate `null` for each component: `new Pair<>(null, 9)` can still match the record pattern, but the **`when` guard fails**, and the fallback branch returns `"partial"`.
- `case null` handles the **selector `pair == null`**; it does not mean rejecting all null components.
- The guarded branch must appear before the general `Pair(...)` branch, because placing the general branch first can cause the guarded branch after it to be *dominated*.

If you try calling `score.toUpperCase()`, the compiler reports an error because that variable is an `Integer`, not a `String`. This is a useful **negative compile test** to confirm type inference — see Section 9.

## 4. Testing Nested Record Patterns in Generic Records

Consider:

```java
Envelope<String> envelope =
        new Envelope<>("E1", new Box<>("java"));
```

Pattern:

```java
case Envelope(var id, Box(var content)) when content != null ->
        id + ":" + content.toUpperCase();
```

There are three layers of meaning:

1. `Envelope(...)` checks the root record type and extracts `id` and `payload`.
2. `Box(...)` requires `payload` to be a non-`null` `Box` record.
3. `var content` extracts the `value` component; thanks to the `Envelope<String>` context, the compiler infers the static type of `content` as `String`.

**Testing `null` at the exact layer:**

| Data | Matching layer | Expected result |
| --- | --- | --- |
| `Envelope("E1", Box("java"))` | Both `Envelope` and `Box` match; guard is true | `E1:JAVA` |
| `Envelope("E2", Box(null))` | Both records match, `content == null`; guard is false | `null-content` |
| `Envelope("E3", null)` | Outer record matches, `Box(...)` does not match | `missing-box` |
| `envelope == null` | Does not match outer record; uses `case null` | `null-envelope` |

An important distinction: `Box(var content)` **can match `new Box<>(null)`**, whereas a **nested record pattern** `Box(...)` **does not match** if the entire `payload == null`. A test containing only valid data will miss bugs in distinguishing these two cases.

In the complete code, the cases are ordered as: guarded nested record → unguarded nested record → general outer record. Only the final case covers the situation where `payload` is `null`.

## 5. Testing at Boundaries Receiving Object and Wildcard Types

If an API receives `Object input`, the compiler **cannot yet know** the concrete generic type argument of the object. To check a `Box` with an unknown type parameter:

```java
if (!(input instanceof Box<?> box)) {
    return "not-box";
}
Object content = box.value();
```

`Box<?>` is a checkable type in this context; what is verified is that **the object belongs to the `Box` record**, not that the element inside is guaranteed to have type `String`.

After retrieving `content` of type `Object`, check it with a pattern on the element itself:

```java
return switch (content) {
    case null -> "null-value";
    case String s -> "String:" + s;
    case Integer n -> "Integer:" + n;
    default -> "other:" + content.getClass().getSimpleName();
};
```

This is a **code snippet placed inside a method returning `String`**. The `case null` branch is necessary if you want to handle null content as valid data instead of letting `switch` throw an error. In the `default` branch, `content` is guaranteed to be non-null because `case null` has already handled it.

Additionally, Java 21 allows using a **record pattern with inferred type arguments** on an `Object`:

```java
if (input instanceof Pair(var left, var right)) {
    // Do not automatically assume left is String and right is Integer.
    System.out.println(left);
}
```

When the selector is `Object` without concrete generic type arguments, the two inner variables cannot be used as if the compiler had proved they are `String` and `Integer`. Check the element types explicitly or pass a model with concrete static types through internal APIs. The test suite separately compares both paths: typed `Pair<String,Integer>` and untyped `Object`.

## 6. Designing the Test Matrix Before Writing the Program

To verify **both types and behavior**, we need the following groups:

| Group | Case | Purpose |
| --- | --- | --- |
| Generic record typed | `Pair<String,Integer>("ada",9)` | Type inference, true guard, value-producing branch |
| Typed + null component | `Pair<String,Integer>(null,9)` | Record matches, but guard rejects component |
| Typed + null selector | `pair == null` | `case null` branch |
| Nested generic record | `Envelope<String>("E1", Box("java"))` | Infer `content` as String, multi-level deconstruction |
| Nested value null | `Envelope("E2", Box(null))` | Distinguish null value from null child record |
| Nested Box null | `Envelope("E3", null)` | Child record does not match, fallback to outer record |
| Nested selector null | `envelope == null` | Record pattern branches do not run |
| Wildcard String | `Box<?>` containing `"ok"` | Runtime element type check |
| Wildcard Integer | `Box<?>` containing `4` | Prove generics does not imply String |
| Wildcard null | `Box<?>` containing `null` | Handle null content |
| Not a Box | `input = "text"` | `not-box` branch |
| Pair from Object | `new Pair<>("x", 4)` | Record pattern on Object only checks structure, does not validate generic args |

Instead of only printing results, the program below uses a **custom assertion**: if actual differs from expected, it throws `AssertionError`. Therefore, the “passed” line only appears when all preceding cases pass.

## 7. Complete Program and How to Run It

Create a file named **`GenericRecordPatternTests.java`** with the following content:

```java
public class GenericRecordPatternTests {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, Box<T> payload) {}

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + " but got " + actual);
        }
        System.out.println(label + " => " + actual);
    }

    static String typed(Pair<String, Integer> pair) {
        return switch (pair) {
            case null -> "null-pair";
            case Pair(var name, var score) when name != null && score != null ->
                    name.toUpperCase() + ":" + (score + 1);
            case Pair(var name, var score) -> "partial";
        };
    }

    static String nested(Envelope<String> envelope) {
        return switch (envelope) {
            case null -> "null-envelope";
            case Envelope(var id, Box(var content)) when content != null ->
                    id + ":" + content.toUpperCase();
            case Envelope(var id, Box(var content)) -> "null-content";
            case Envelope(var id, var payload) -> "missing-box";
        };
    }

    static String wildcard(Object input) {
        if (!(input instanceof Box<?> box)) return "not-box";

        Object content = box.value();
        return switch (content) {
            case null -> "null-value";
            case String s -> "String:" + s;
            case Integer n -> "Integer:" + n;
            default -> "other:" + content.getClass().getSimpleName();
        };
    }

    static String destructureUnknown(Object input) {
        if (input instanceof Pair(var left, var right)) {
            String a = left == null
                    ? "null" : left.getClass().getSimpleName();
            String b = right == null
                    ? "null" : right.getClass().getSimpleName();
            return a + "/" + b;
        }
        return "not-pair";
    }

    public static void main(String[] args) {
        check("typed-ok", "ADA:10", typed(new Pair<>("ada", 9)));
        check("typed-null-component", "partial",
                typed(new Pair<>(null, 9)));
        check("typed-null-root", "null-pair", typed(null));

        check("nested-ok", "E1:JAVA",
                nested(new Envelope<>("E1", new Box<>("java"))));
        check("nested-null-value", "null-content",
                nested(new Envelope<>("E2", new Box<>(null))));
        check("nested-null-box", "missing-box",
                nested(new Envelope<>("E3", null)));
        check("nested-null-root", "null-envelope", nested(null));

        check("wild-string", "String:ok", wildcard(new Box<>("ok")));
        check("wild-int", "Integer:4", wildcard(new Box<>(4)));
        check("wild-null", "null-value", wildcard(new Box<>(null)));
        check("wild-wrong", "not-box", wildcard("text"));

        check("unknown-pair", "String/Integer",
                destructureUnknown(new Pair<>("x", 4)));

        System.out.println("12/12 passed");
    }
}
```

**Run with JDK 21+:**

```bash
javac --release 21 GenericRecordPatternTests.java
java GenericRecordPatternTests
```

**Exact stdout:**

```text
typed-ok => ADA:10
typed-null-component => partial
typed-null-root => null-pair
nested-ok => E1:JAVA
nested-null-value => null-content
nested-null-box => missing-box
nested-null-root => null-envelope
wild-string => String:ok
wild-int => Integer:4
wild-null => null-value
wild-wrong => not-box
unknown-pair => String/Integer
12/12 passed
```

The example was run in **JDK 24's JShell** and produced all 12 expected results along with the summary line. The syntax features used are standard features in Java 21; the `javac --release 21` command indicates the compilation target for learners.

**How to verify the tests are genuinely meaningful:** temporarily change `"ADA:10"` to `"ADA:11"` in expected, or change `score + 1` to `score + 2` in `typed`: the program must throw `AssertionError`. Do not rely solely on the program finishing without exceptions to claim that all patterns produced the right results.

## 8. Testing Compilation Error Cases (Negative Compilation)

Some mistakes **cannot** be verified by running the program, because the compiler must reject them beforehand. The snippets below are **intentionally wrong** and are not included in the program file in Section 7. If run in JShell or placed in a Java file with `Box` and `Pair` declared, they must be rejected.

### 8.1. Cannot Check `Box<String>` from Object

```java
// INTENTIONALLY WRONG: the generic type argument String cannot be checked at runtime this way.
static boolean bad(Object input) {
    return input instanceof Box<String> box;
}
```

With `Object` as the selector, `Box<String>` is not a reifiable type that permits checking in this way. The compiler reports that `Object` cannot be safely cast to `Box<String>`. **Fix:** use `Box<?>` to check the base record, then check `box.value()` with a separate type pattern if `String` is needed.

Do not overgeneralize that “no generic type can ever be used with `instanceof`.” For example, `Box<?>` is valid; and when the compiler has a narrower type context, the checks allowed by the language may differ. Here, the specific scenario being tested is **`Object` to `Box<String>`**.

### 8.2. Wrong Component Count in Record Pattern

```java
// INTENTIONALLY WRONG: Box declares only one component.
static boolean badArity(Object input) {
    return input instanceof Box(var first, var second);
}
```

`Box<T>` has **one** record component `value`, so the pattern must have exactly **one** subpattern. The compiler reports an incorrect number of nested patterns. A record pattern follows the **declared count, order, and types of components**, not the variable names chosen by the author.

### 8.3. Inferring Integer Disallows Calling String Methods

```java
// INTENTIONALLY WRONG: score is Integer, which does not have toUpperCase().
static String badInference(Pair<String, Integer> pair) {
    return switch (pair) {
        case null -> "none";
        case Pair(var name, var score) -> score.toUpperCase();
    };
}
```

The compiler rejects the `score.toUpperCase()` call. That is a sign that `var score` is **not an arbitrary Object** and not a `String`, but rather receives the type inferred from `Pair<String,Integer>`.

These three negative compile cases were tested in **JDK 24 JShell** and were all rejected as expected: respectively for unsafe generic check, wrong number of nested patterns, and method `toUpperCase()` not found on type Integer.

## 9. Beware of Type Erasure, Raw Types, and Untrusted Data

Because Java generics rely primarily on compile-time checks, code using **raw types**, unchecked casts, reflection, or external data sources can break assumptions about components.

Example illustrating the risk (placed in a method, not code for production use):

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static Pair<String, Integer> forgePair() {
    Pair raw = new Pair("ada", "not-an-integer");
    return (Pair<String, Integer>) raw;
}
```

This method uses a raw type and an unchecked cast, so it can produce a reference whose **declared type is `Pair<String,Integer>` while the actual component is not an `Integer`**. When subsequent code retrieves or uses `score` as an `Integer`, a cast/runtime error can occur. Do not treat record pattern matching as a complete validator of generic type arguments.

A defensive strategy at data boundaries:

- Accept `Object`/`Box<?>` and check runtime types for each component if the source is untrusted.
- Convert into validated DTOs/domain objects with proper generic types before calling internal logic.
- Avoid raw types whenever possible; treat compiler warnings about unchecked conversions as signals to fix.
- When using `List<?>` or `Box<?>`, do not cast all elements to `String` just because one sample element has that type.

**Not every kind of generic bug needs a runtime test.** Type errors obvious at compile time should have **negative compile tests**; type errors caused by external input or raw casts need **runtime validation tests** at the boundary.

## 10. Common Bugs Missed in Test Suites

| Bug | Test that catches it |
| --- | --- |
| Testing only `Pair("ada",9)` without null components | `typed-null-component` shows the pattern still matches, but the guard fails |
| Conflating `Box(null)` with `payload == null` | `nested-null-value` and `nested-null-box` produce different results |
| Forgetting root null | `typed-null-root` and `nested-null-root` |
| Calling `content.toUpperCase()` when selector is `Object` | Negative compile or requiring a runtime check first |
| Believing `Box<String>` can be verified from `Object` via `instanceof` | Negative compile test `bad(Object input)` |
| Mistaking `var score` for String | Negative compile test `badInference` |
| Wrong number of subpatterns | Negative compile test `badArity` |
| Placing a general case before a `when` case | Compiler may reject due to dominance, or guard logic becomes meaningless |
| Using `Box<?>` and casting all content to `String` | Test `String`, `Integer`, `null`; component validation |
| Checking output only by eye | `check` helper compares expected/actual automatically and throws `AssertionError` |

**Test ordering should be intentional:** first verify one valid case to rule out model/syntax errors; then add null at each layer; finally test wildcards, generic erasure, and compile negatives. If a schema change breaks a test, the failure message should identify the exact case name so the right layer can be fixed.

## 11. Testing Strategy for Real Codebases

- **Unit tests for pattern logic:** each case/rule has clear input and expected output. No framework dependency is strictly required; however, the `check` helper can be replaced with JUnit assertions when a project already uses JUnit.
- **Boundary data tests:** generate records with contractually nullable components, empty collections, blank strings, and boundary values; distinguish invalid domain data from pattern non-matches.
- **Tests with wide-typed sources:** accept `Object`, wildcards, or JSON-parsed data; do not assume generic parameters. Keep untrusted data at the boundary.
- **Negative compile tests:** place invalid snippets in a separate test target to assert the compiler rejects them; do not mix them into sources that must build cleanly.
- **Tests during model refactoring:** if you reorder or add record components, retest patterns according to component order. With sealed hierarchies and exhaustive `switch`, the compiler helps catch some missing branches, but it does not replace business logic tests.
- **Runtime/version:** use JDK 21+ for record pattern code; declare the corresponding toolchain/`--release`. JDK 24 JShell confirms the example behavior, while projects should run CI on their actual target JDK.

If using property-based testing, you can generate valid `Pair<String,Integer>` data under defined constraints and check output invariants. However, testing type erasure still requires intentionally mistyped cases from boundaries/raw conversions; standard statically typed generators may not produce those cases.

## 12. Practice Exercise

Given:

```java
record Result<T>(String code, T data) {}
record Page<T>(java.util.List<T> items) {}
```

Requirements:

1. Write `describe(Result<Page<String>> result)` using nested record patterns to extract `code` and `items`. If `result == null`, return `"missing-result"`.
2. If `data == null`, return `"missing-page"`. If `Page.items == null`, return `"missing-items"`.
3. If the list is non-null, return `code + ":" + items.size()`.
4. Write tests for an empty list, a two-element list, null at all three levels, and a null `code` (decide the display rule before writing the test).
5. Write a negative compile test that attempts to check `Result<Page<String>>` directly with `instanceof` from an `Object` variable, then explain why a wildcard and runtime content validation must be used instead.

**Hint for the switch branches** (placed in a method returning `String` with parameter `Result<Page<String>> result`):

```java
return switch (result) {
    case null -> "missing-result";
    case Result(var code, Page(var items)) when items != null ->
            code + ":" + items.size();
    case Result(var code, Page(var items)) -> "missing-items";
    case Result(var code, var page) -> "missing-page";
};
```

This is illustrative code for the records above, not a standalone file. The pattern order distinguishes a **null component value** from a **null child record**. Do not try to force `List<String>` into a runtime pattern purely from its generic type argument; if you need to check individual elements, iterate and use a separate type pattern.

## 13. Key Takeaways

**Generic record patterns check record shape and infer types from static context; they do not recover type arguments erased at runtime.** Tests must cover typed contexts, Object/wildcards, different null levels, guard/case ordering, and compiler-rejected code. The test suite above has **12 runtime cases with expected output** and **3 negative compile cases**, clearly demonstrating both the limits and capabilities of pattern matching in Java 21.

Official documentation:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 Language Guide — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS 21 `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
