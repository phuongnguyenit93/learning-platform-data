# Testing Generic Record Patterns (Java 21+)

## 1. What Are We Testing?

A **generic record pattern** is a record pattern applied to a parameterized `record` type, such as `Box<T>` or `Pair<L, R>`. When a record pattern matches, Java deconstructs the record components and declares pattern variables. For generic records, the types of these variables also depend on the **static type of the expression being tested** and the types of the component patterns.

~~~java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> pair = new Pair<>("item", 3);
if (pair instanceof Pair(var name, var quantity)) {
    String upper = name.toUpperCase(); // name is inferred as String
    int twice = quantity * 2;         // quantity is inferred as Integer
}
~~~

This is an **illustrative snippet**, assuming the two records are declared in an appropriate scope. Record pattern syntax was standardized in **Java 21**; `--enable-preview` is not required on JDK 21+.

A good test suite must distinguish between two things:

1. **Compile-time checks**: Does Java infer types correctly from the generic record and accept/reject unsafe uses of pattern variables?
2. **Runtime checks**: Does the pattern match the right record type, the right component value types, the right nested structure, and `null` cases?

You cannot see a single `instanceof` check return `true` and conclude that Java has verified all generic type arguments at runtime. Because of **type erasure**, you need dedicated test cases for component values.

## 2. Data Model and Type Expectations

Use the following three records as sample data:

~~~java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, Box<T> payload) {}
~~~

Three representative patterns:

~~~java
// Source with static type Pair<String, Integer>:
Pair<String, Integer> a = new Pair<>("item", 3);
if (a instanceof Pair(var text, var number)) {
    String label = text.toUpperCase();
    int doubled = number * 2;
}

// Source with static type Envelope<Integer>, nested record:
Envelope<Integer> b = new Envelope<>("unit", new Box<>(7));
if (b instanceof Envelope(var id, Box(var count))) {
    Integer value = count; // inferred as Integer across two record levels
}

// Source with static type Object only:
Object c = new Pair<>("tag", 4);
if (c instanceof Pair(String tag, Integer count)) {
    System.out.println(tag + ":" + count);
}
~~~

In the first two cases, the static type of the expression allows Java to infer the type arguments of the record pattern and the `var` variables inside. In the third case, we **cannot assume** that `Object` carries specific generic type arguments; the component patterns `String tag` and `Integer count` are used to **check each actual component value**.

For example:

~~~java
Object unknown = new Box<>("hello");
if (unknown instanceof Box(var value)) {
    // value has static type Object; further checking is needed before treating it as String.
    if (value instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
~~~

Do not interpret `var` as "the actual runtime type is automatically detected and always accessible as String". With `unknown` having static type `Object`, the generic information `Box<String>` from the initialization expression does not automatically turn `value` into a variable with static type `String` at the point of use.

## 3. Required Test Matrix

| Category | Value or Scenario | Expectation |
| --- | --- | --- |
| Static type inference | `Pair<String, Integer>` with `Pair(var, var)` | First variable is used as `String`, second as `Integer`; compiles successfully. |
| Nested generic record | `Envelope<Integer>(..., Box<Integer>)` | Pattern `Envelope(var, Box(var))` matches and the innermost variable is inferred as `Integer`. |
| Matching runtime component types | `Object` holding `Pair("tag", 4)` | `Pair(String, Integer)` matches. |
| Wrong component order/types | `Object` holding `Pair(4, "tag")` | `Pair(String, Integer)` does not match. |
| Wrong record type | `Object` holding `Box("tag")` | Pattern `Pair(...)` does not match. |
| Outermost value is `null` | `null instanceof Pair(...)` | Does not match. |
| Nested record is `null` | `Envelope("unit", null)` | Pattern `Envelope(var, Box(...))` does not match. |
| Record component contains `null` | `Box<String>(null)` | `Box(var value)` can match with `value == null`; `Box(String text)` does not match. |
| Wrong type inside nested pattern | `Envelope("unit", Box("seven"))` | Nested pattern `Box(Integer n)` does not match. |
| `switch` guard | Positive `Integer`, `0`, and other types | Enters the right `case`, including the fallback branch. |
| Consistency | Deconstructing known `Pair` instances | Pattern variable values equal the values returned by the `left()`, `right()` accessors. |

This matrix includes **positive cases** (must match), **negative cases** (must be rejected), **`null` boundaries**, and **type contract checks**. Testing only a single `Pair("a", 1)` success case is not enough to protect the program from data type or component order changes.

## 4. Complete Java Test Suite Without External Libraries

Create the file **`GenericRecordPatternTest.java`** with all of the following code. The test suite uses an always-active `check` method that throws `AssertionError` when a result is wrong. This approach does not depend on the `-ea` flag of the `java` command.

~~~java
public class GenericRecordPatternTest {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, Box<T> payload) {}

    private static int passed = 0;

    private static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    private static void typeInference() {
        Pair<String, Integer> pair = new Pair<>("item", 3);

        if (pair instanceof Pair(var item, var quantity)) {
            String upper = item.toUpperCase();
            int doubled = quantity * 2;
            check(upper.equals("ITEM") && doubled == 6,
                    "inferred types");
        } else {
            throw new AssertionError("typed pair pattern did not match");
        }

        Envelope<Integer> envelope =
                new Envelope<>("unit", new Box<>(7));

        if (envelope instanceof Envelope(var id, Box(var count))) {
            Integer typedCount = count;
            check(id.equals("unit") && typedCount == 7,
                    "nested inference");
        } else {
            throw new AssertionError("nested pattern did not match");
        }
    }

    private static void runtimeMatching() {
        Object correct = new Pair<>("tag", 4);
        check(correct instanceof Pair(String tag, Integer amount)
                        && tag.equals("tag") && amount == 4,
                "runtime component types");

        Object swapped = new Pair<>(4, "tag");
        check(!(swapped instanceof Pair(String tag, Integer amount)),
                "swapped components rejected");

        Object other = new Box<>("tag");
        check(!(other instanceof Pair(String tag, Integer amount)),
                "wrong record type rejected");

        Object nullTop = null;
        check(!(nullTop instanceof Pair(var first, var second)),
                "null input rejected");

        Object nullInner = new Envelope<Integer>("unit", null);
        check(!(nullInner instanceof Envelope(var id, Box(var value))),
                "null nested record rejected");

        Object nullValue = new Box<String>(null);
        check(nullValue instanceof Box(var value) && value == null,
                "null component accepted by var");
        check(!(nullValue instanceof Box(String text)),
                "null component rejected by type pattern");

        Object wrongInner = new Envelope<>(
                "unit", new Box<>("seven"));
        check(!(wrongInner instanceof Envelope(var id, Box(Integer n))),
                "wrong nested component rejected");
    }

    private static String classify(Object input) {
        return switch (input) {
            case Envelope(var id, Box(Integer n))
                    when n > 0 -> id + ":positive:" + n;
            case Envelope(var id, Box(Integer n)) ->
                    id + ":nonpositive:" + n;
            case Envelope(var id, Box(var rest)) ->
                    id + ":other";
            case null -> "null";
            default -> "unknown";
        };
    }

    private static void switchCases() {
        check(classify(new Envelope<>("e", new Box<>(7)))
                        .equals("e:positive:7"),
                "guard true");
        check(classify(new Envelope<>("e", new Box<>(0)))
                        .equals("e:nonpositive:0"),
                "guard false");
        check(classify(new Envelope<>("e", new Box<>("text")))
                        .equals("e:other"),
                "different nested type");
        check(classify(new Envelope<>(
                "e", new Box<>((Object) null))).equals("e:other"),
                "null nested value");
        check(classify(new Envelope<Integer>("e", null))
                        .equals("unknown"),
                "null nested record switch");
        check(classify(null).equals("null"),
                "null switch input");
    }

    private static void accessorConsistency() {
        for (int i = 0; i < 3; i++) {
            Pair<String, Integer> pair = new Pair<>("item-" + i, i);

            if (pair instanceof Pair(var name, var number)) {
                check(name.equals(pair.left())
                                && number.equals(pair.right()),
                        "accessors " + i);
            } else {
                throw new AssertionError("unexpected failure");
            }
        }
    }

    public static void main(String[] args) {
        typeInference();
        runtimeMatching();
        switchCases();
        accessorConsistency();
        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile and run on JDK 21 or later:

~~~bash
javac --release 21 GenericRecordPatternTest.java
java GenericRecordPatternTest
~~~

Output when all tests pass:

~~~text
PASS inferred types
PASS nested inference
PASS runtime component types
PASS swapped components rejected
PASS wrong record type rejected
PASS null input rejected
PASS null nested record rejected
PASS null component accepted by var
PASS null component rejected by type pattern
PASS wrong nested component rejected
PASS guard true
PASS guard false
PASS different nested type
PASS null nested value
PASS null nested record switch
PASS null switch input
PASS accessors 0
PASS accessors 1
PASS accessors 2
ALL PASSED: 19
~~~

If a condition fails, `check` throws an `AssertionError` with the test case name; the program does not print `ALL PASSED: 19`. This mechanism makes failures clearly visible and causes the Java process to exit with an error on an unhandled assertion.

### How to Read the Output

- **`inferred types`**: `item.toUpperCase()` and `quantity * 2` compile because the `var` variables carry the types inferred from `Pair<String, Integer>`.
- **`nested inference`**: starting from `Envelope<Integer>` through the `Box<T>` component, the nested pattern infers `count` as `Integer`.
- **`runtime component types`**: an expression with static type `Object` can still check component values using `String` and `Integer` patterns.
- **`swapped components rejected`**: the type and position of each component matter; having `String` and `Integer` in swapped positions does not match.
- **`null` tests**: must distinguish between a `null` outermost object, a `null` nested record itself, and a `null` value inside a record.
- **`guard true/false`**: the pattern `Box(Integer n)` binds `n` for use in `when n > 0`; if the guard is false, `switch` can select the next `Integer` branch.
- **`accessors 0..2`**: components are deconstructed in the exact order and with the exact values as the record accessors, across three different data sets.

## 5. Negative Compile-Time Tests

You should not rely solely on runtime tests. Certain generic record pattern mistakes must be caught by the **compiler**. The snippets below are **intentionally invalid**, meant only as standalone compilation test examples; do not put them into the runnable test file in Section 4.

### Mistake A: directly checking unsafe generic type arguments on `Object`

~~~java
Object obj = new Pair<>("tag", 4);

// DOES NOT COMPILE: Object cannot be safely checked as
// Pair<String, Integer> with generic type arguments at runtime.
if (obj instanceof Pair<String, Integer>(var text, var count)) {
    System.out.println(text);
}
~~~

Because of *type erasure*, this `instanceof Pair<String, Integer>(...)` form is unsafe when the source object is only known as `Object`. Instead, use component patterns with concrete types:

~~~java
if (obj instanceof Pair(String text, Integer count)) {
    System.out.println(text + ":" + count);
}
~~~

The latter checks that **each component's value** actually matches `String` and `Integer`. It does not generally validate the generic type arguments of the object that was created, especially with data that was unsafely cast elsewhere.

### Mistake B: assuming `var` on an `Object` source produces static type `String`

~~~java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var value)) {
    // String text = value; // DOES NOT COMPILE: value has type Object
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
~~~

The runnable part of the snippet includes an additional `String` type check. If you uncomment the direct assignment line, it becomes a **negative compile-time test case** that must be rejected.

You should maintain both positive and negative compilation tests when upgrading JDK versions or refactoring record signatures. You can verify with `javac --release 21` and check for a **non-zero exit code** on the intentionally invalid example file. Do not treat a compilation error in a negative example as a failure of the standalone positive test suite in Section 4.

## 6. Using `switch` with Generic Record Patterns

The pattern `Envelope(var id, Box(Integer n))` in the test suite has three properties that need dedicated testing:

1. `id` is extracted from the `String id` component of `Envelope<T>`; `n` is extracted from the value of the nested `Box<T>`, if that value matches `Integer`.
2. After the pattern matches, `when n > 0` decides whether to take the positive-number branch. The number `0` is still a valid `Integer`, but it does not pass the guard; the next `Integer` branch receives it.
3. The pattern `Envelope(var id, Box(var rest))` is a more general branch, so it is placed **after** the specific `Integer` branches. It matches `Box<String>("text")` and `Box<Object>(null)`; conversely, `Envelope("e", null)` does not match the `Box(...)` pattern and falls through to `default`.

In particular, `case null` in the example handles **the case where the object passed into `switch` itself is `null`**. It is not a substitute for testing an existing record that contains a `null` component.

When adding test cases, you should cover positive numbers, `0`, other types, `null` inside a component, a `null` nested record, and a `null` selector. Testing only the `when`-true branch will miss branch-ordering bugs or exhaustiveness conditions.

## 7. Integrating Tests into a JUnit 5 Project

In a project configured with **JUnit Jupiter**, you can convert the `check` method to JUnit assertions, place the tests in `src/test/java`, and use `@Test`. The example below is an **illustrative snippet**, assuming `Pair` and `Envelope` are available in the test class scope:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GenericPatternJUnitTest {
    record Pair<L, R>(L left, R right) {}

    @Test
    void typedComponentsMatch() {
        Object input = new Pair<>("tag", 4);
        assertTrue(input instanceof Pair(String text, Integer amount)
                && text.equals("tag") && amount == 4);
    }

    @Test
    void wrongComponentOrderDoesNotMatch() {
        Object input = new Pair<>(4, "tag");
        assertFalse(input instanceof Pair(String text, Integer amount));
    }

    @Test
    void nullSelectorDoesNotMatch() {
        Object input = null;
        assertFalse(input instanceof Pair(var left, var right));
    }
}
~~~

JUnit code requires the `org.junit.jupiter` dependency and the project's JUnit 5 test runner; it will **not** compile with plain JDK `javac` alone without the library. Tests with similar data can be grouped into parameterized tests (`@ParameterizedTest`), but keep test case names meaningful and include full negative paths.

In larger projects, you should place record classification logic into a method with a clear output and test the **output result**, alongside a few direct `instanceof` checks. That way, the tests protect application behavior rather than merely repeating Java syntax.

## 8. Common Testing Mistakes and How to Avoid Them

**Testing only a single successful match.** You should also include wrong record types, wrong component positions, wrong component types in nested records, and `null` cases.

**Assuming `Pair<String, Integer>` is recognized intact at runtime.** Generic type arguments are not preserved in a way that can be generally checked with `instanceof`. For `Object`-typed inputs, use concrete component patterns and test the actual value types.

**Confusing `var` with dynamic typing.** `var` is inferred from the static type Java knows at the pattern site. Compilation tests should check both cases where the source has a full generic type and cases where the source only has type `Object`.

**Using `assert` but forgetting to enable assertions.** Java's `assert` statement may not execute unless run with `java -ea`. The test suite in Section 4 uses `throw new AssertionError` to detect failures consistently; JUnit also actively runs its own assertions.

**Forgetting to distinguish between forms of `null`.** A `Box<String>(null)` is still a record instance and `Box(var value)` can match; however, `Box(String text)` does not match a `null` component. An `Envelope` with `payload == null` does not match `Envelope(var id, Box(...))`.

**Placing a general pattern before a specific pattern in `switch`.** The pattern `Envelope(var, Box(var))` can dominate and shadow a subsequent `Envelope(var, Box(Integer))` branch. Keep the order from specific to general and test both true and false guards.

**Not checking the Java version.** `javac --release 21` helps verify that the code only uses features compatible with Java 21; this generic record pattern example does not require enabling preview features in Java 21.

## 9. Regression Testing Checklist

When modifying a `record` type, adding a component, or changing generic types:

1. Recompile the test suite targeting Java 21 or the project's minimum version.
2. Run positive tests to confirm type inference from `Pair<String, Integer>` and nested generic records still works.
3. Run negative runtime tests for component order, mismatched value types, and `null` at every level.
4. Check `switch` branches, especially `case` ordering and `when` guards.
5. Compare pattern variable values against accessors to catch misaligned deconstruction.
6. Keep negative compilation examples **separate from** the runnable test suite; an intentional error must be scored as *expected* when the compiler rejects it.

**Conclusion:** Testing generic record patterns requires combining **compile-time type inference**, **runtime structure and component type checks**, **`null` handling**, **`switch` branches**, and **consistency with accessors**. This approach properly verifies the contract of pattern matching on generic records, avoiding the misconception that type erasure allows validating all generic type arguments at runtime.