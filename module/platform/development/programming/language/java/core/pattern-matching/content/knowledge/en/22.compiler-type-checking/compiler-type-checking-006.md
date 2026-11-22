# Impossible Patterns: Compiler and Type Checking in Java 21+

## 1. What Does “Impossible Pattern” Mean?

Pattern matching in Java uses a *pattern* to test whether a value has a matching shape or type and, when it matches, introduces **pattern variables**. With a type pattern, we write `value instanceof Integer number`; with a record pattern (Java 21+), we can deconstruct components: `value instanceof Point(int x, int y)`.

Not every pattern can possibly match the data type under consideration. In particular, we need to distinguish **three phenomena**:

1. **Statically inapplicable**: the compiler knows from the declared types that the value can never match the pattern. This is a **compile-time error**.
2. **Dominated in `switch`**: an earlier `case` branch already covers the cases that a later branch could accept. The later branch can never be selected and is rejected by the compiler. This is an error of **branch ordering/reachability**, not necessarily because the pattern's type is inherently impossible.
3. **Valid at compile time but does not match at runtime**: the static type still allows a matching value, and it is only the current **actual value** that does not match. Java reports no compile-time error; the `instanceof` expression evaluates to `false`.

There are also **business constraints** (for example, a value is always positive by application convention) that the compiler does not necessarily know about. Not every failing condition should be called an “impossible pattern” in the sense of Java's type checking.

This lesson uses **Java 21+** syntax, where type patterns with `instanceof` and `switch`, record patterns, and `sealed` hierarchies can all be used without enabling preview features.

## 2. How the Compiler Detects Incompatible Pattern Types

### 2.1. Two Unconvertible Class Types

~~~java
String known = "abc";

// INTENTIONALLY DOES NOT COMPILE:
if (known instanceof Integer number) {
    System.out.println(number);
}
~~~

The static type of `known` is `String`. `String` and `Integer` are two classes with no inheritance relationship that would allow a value of type `String` to be an `Integer`. Therefore, the compiler rejects the expression `instanceof Integer number` before the program is ever run.

This is **not** a valid match check that always returns `false`: the code itself cannot compile.

In contrast:

~~~java
Object unknown = "abc";
System.out.println(unknown instanceof Integer number); // false
~~~

This snippet **compiles and runs**. The static type `Object` can hold an `Integer`, even though the actual value currently stored is a `String`. The compiler only sees a statically valid conversion possibility; the mismatch is determined **at runtime**.

Comparison:

| Static type of expression | Pattern | Result |
| --- | --- | --- |
| `String` | `Integer n` | Compile-time error: incompatible types |
| `Object` | `Integer n` | Valid; matches or not depending on runtime value |
| `Number` | `Integer n` | Valid because `Integer` is a subtype of `Number` |
| `Object` with value `null` | `String s` | Valid at compile time; `instanceof` returns `false` |
| `Object` with value `"abc"` | `String s` | Valid, matches, and `s` receives `"abc"` |

The key takeaway: **the compiler does not need to run the code to reject a pattern whose static type is incompatible**. However, a pattern can be type-valid and still not match in actual data.

### 2.2. Do Not Confuse “Unnecessary” with “Impossible”

A pattern can be semantically redundant yet still valid. For example:

~~~java
String text = "hello";

if (text instanceof String sameText) {
    System.out.println(sameText.toUpperCase());
}
~~~

The snippet above is still valid: `text` could be `null` in the general case, so `instanceof` also checks that the value is non-`null`. Do not assume that the compiler will reject every pattern that “obviously will match”.

## 3. Record Patterns: Component-by-Component Compile-Time Checking

Record patterns let us deconstruct data:

~~~java
record Fixed(String value) {}
record Flexible(Object value) {}
~~~

When the compiler sees:

~~~java
Object input = new Fixed("abc");

// INTENTIONALLY DOES NOT COMPILE:
if (input instanceof Fixed(Integer number)) {
    System.out.println(number);
}
~~~

The type of the `value` component in `Fixed` is declared as `String`. The nested subpattern `Integer number` is incompatible with `String`, so the entire `Fixed(Integer number)` is rejected **at compile time**, even though the input expression has type `Object`.

Compare this with a record that has an `Object` component:

~~~java
Object first = new Flexible("abc");
Object second = new Flexible(42);

System.out.println(first instanceof Flexible(Integer n));  // false
System.out.println(second instanceof Flexible(Integer n)); // true
~~~

In `Flexible`, the compiler only knows the component is `Object`; the actual value might be an `Integer`, so the subpattern `Integer n` is valid. Java then checks the component at runtime.

**Rule to remember:** With record patterns, you must examine the **declared type of each component** after generic type inference (if any), not just the type of the input variable. An outer pattern that looks valid can still fail to compile because of an **impossible subpattern**.

### Nested Patterns and Matchability

~~~java
record Item(String name) {}
record Parcel(Item item) {}

Object input = new Parcel(new Item("book"));

if (input instanceof Parcel(Item(String name))) {
    System.out.println(name); // book
}
~~~

This is an **illustrative snippet**, assuming the record declarations are in an appropriate scope. Each level of the pattern must be checked for type compatibility and matchability. If a component is declared as `String` and the subpattern asks for `Integer`, the compiler catches the error at that level. If the types allow a match but the actual data does not fit, the pattern fails at runtime.

## 4. Sealed Hierarchies Restrict Which Types Can Appear

Suppose we have a closed hierarchy:

~~~java
sealed interface Signal permits TextSignal, CodeSignal {}

record TextSignal(String text) implements Signal {}
record CodeSignal(int code) implements Signal {}
~~~

Both `TextSignal` and `CodeSignal` implement `Signal`. They are the types declared in the `permits` clause of this hierarchy. Because `String` is not a permitted type belonging to the `Signal` hierarchy, the following snippet is rejected by the compiler:

~~~java
Signal signal = new TextSignal("ok");

// INTENTIONALLY DOES NOT COMPILE:
if (signal instanceof String s) {
    System.out.println(s);
}
~~~

This error stems from an **incompatible type relationship**, not because `signal` happens to hold a `TextSignal` at runtime. From the static type `Signal` and the constraints of the hierarchy, the compiler can conclude that a `String` is not a valid `Signal`.

A `sealed` hierarchy also helps `switch` check exhaustiveness:

~~~java
static String label(Signal value) {
    return switch (value) {
        case TextSignal t -> "text:" + t.text();
        case CodeSignal c -> "code:" + c.code();
        case null -> "null";
    };
}
~~~

This is an **illustrative method** inside a class that declares `Signal` and the two records above. The two pattern branches cover every permitted implementing type in this hierarchy; `case null` handles a `null` selector. No `default` branch is needed for other subtypes in this declared version of the hierarchy.

If you later extend `permits` with a new subtype, re-check the `switch`: the compiler may require adding a branch to handle it so that the expression remains exhaustive.

**Important limitation:** the compiler checks **the types allowed by the language and declarations**. It does not automatically prove business assumptions such as “the system will never emit this kind of signal” if that constraint is not expressed in the type system.

## 5. `switch`: Dominated Branches Never Get a Chance to Run

Another error often mislabeled as an “impossible pattern” is a branch placed **after a more general pattern**.

~~~java
Object value = 42;

// INTENTIONALLY DOES NOT COMPILE: case Integer is dominated by case Number.
String description = switch (value) {
    case Number n -> "number";
    case Integer i -> "integer";
    default -> "other";
};
~~~

Here `Integer` is completely valid as a value of `Object`. However, any `Integer` is also a `Number`; the preceding `case Number n` branch will accept it first. Thus `case Integer i` can never be selected, and the compiler reports a **dominated case label**.

The fix is to order branches from **specific to general**:

~~~java
Object value = 42;

String description = switch (value) {
    case Integer i -> "integer";
    case Number n -> "number";
    default -> "other";
};

System.out.println(description); // integer
~~~

Do not confuse the three situations:

- **`String known instanceof Integer i`**: the pattern is rejected due to **static type incompatibility**.
- **`Object value` with `case Number` then `case Integer`**: the `Integer` branch is **dominated** because of ordering.
- **`Object value = "abc"` with `instanceof Integer i`**: the pattern is **valid**, but does not match the current value.

If a `case` has a `when` guard, dominance also depends on branch selection rules and the corresponding guard. Do not assume that overlapping types always trigger a compiler error; verify the specific case with the compiler.

## 6. `null`: “Cannot Match” Depends on Where the Pattern Appears

With a top-level type pattern in `instanceof`:

~~~java
String value = null;
System.out.println(value instanceof String text); // false
~~~

A `null` value does not match a direct `instanceof` check. However, **record patterns have a different nuance**: an **unconditional component pattern** (a pattern that covers all values of the component's static type) can match a `null` component. Therefore, you must not say that **every type pattern nested inside a record rejects `null`**.

Compare the two records:

~~~java
record Strict(String value) {}
record Broad(Object value) {}

Object a = new Strict(null);
Object b = new Broad(null);

System.out.println(a instanceof Strict(String text)); // true
System.out.println(b instanceof Broad(String text));  // false
~~~

In `Strict(String text)`, the component already has static type `String`; `String text` is an unconditional pattern for that component and can accept `null`. With `Broad(Object value)`, the pattern `String text` must **check the type of the component's value** at runtime; a `null` component does not match that conditional pattern.

This is a common pitfall that leads to `NullPointerException` when developers make the wrong assumption:

~~~java
Object input = new Strict(null);

// MAY THROW NPE if the text != null check is omitted.
if (input instanceof Strict(String text) && !text.isBlank()) {
    System.out.println("valid");
}
~~~

The safe approach:

~~~java
if (input instanceof Strict(String text)
        && text != null
        && !text.isBlank()) {
    System.out.println("valid");
}
~~~

**Conclusion on `null`:** distinguish between the outermost `instanceof` check, a component pattern inside a record, and the static type of the component itself. Check for `null` where you need to invoke methods, rather than relying on an inaccurate blanket rule.

## 7. Generic Type Erasure Is a Different Constraint, Not an Impossible Pattern

With generic types, a pattern syntax may be rejected **because type arguments cannot be safely checked at runtime**, even though the actual object type could exist.

~~~java
Object input = java.util.List.of("a", "b");

// INTENTIONALLY DOES NOT COMPILE from an Object variable:
// Runtime cannot safely check the full List<String>.
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
~~~

How to check the list shape at runtime:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
~~~

`List<?>` checks that the value is a `List`; it does **not** prove that every element has type `String`. If you need to ensure the element type, check each element while iterating.

This case should be noted as a **limitation of generic/reifiability checking**, not a conclusion that no `List<String>` can ever appear. Distinguishing the cause of the error helps you choose the right fix instead of using unsafe casts to silence compiler messages.

## 8. Complete Java 21 Program: Testing the Distinction Between Compile-Time and Runtime

Save all of the following code to a file named **`ImpossiblePatternDemo.java`**. The code uses a `sealed` hierarchy, type patterns, record patterns, and `switch`. The snippets that **intentionally do not compile** from earlier sections are **not included** in this program.

~~~java
public class ImpossiblePatternDemo {
    sealed interface Signal permits TextSignal, CodeSignal {}
    record TextSignal(String text) implements Signal {}
    record CodeSignal(int code) implements Signal {}
    record Case(String name, Object input, String expected) {}

    static String inspect(Object value) {
        if (value instanceof TextSignal(String text)
                && text != null && !text.isBlank()) {
            return "valid:" + text;
        }
        if (value instanceof CodeSignal(int code)) {
            return "code:" + code;
        }
        return value == null ? "null" : "other";
    }

    static String label(Signal value) {
        return switch (value) {
            case TextSignal t -> "text:" + t.text();
            case CodeSignal c -> "code:" + c.code();
            case null -> "null";
        };
    }

    static void check(String name, String got, String expected) {
        if (!expected.equals(got)) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + got);
        }
        System.out.println("PASS " + name + " -> " + got);
    }

    public static void main(String[] args) {
        Case[] cases = {
            new Case("text-ok", new TextSignal("ok"), "valid:ok"),
            new Case("text-blank", new TextSignal("   "), "other"),
            new Case("text-null", new TextSignal(null), "other"),
            new Case("code-record", new CodeSignal(7), "code:7"),
            new Case("plain-integer", 7, "other"),
            new Case("plain-string", "ok", "other"),
            new Case("input-null", null, "null")
        };

        for (Case test : cases) {
            check(test.name(), inspect(test.input()), test.expected());
        }

        check("sealed-text-null",
                label(new TextSignal(null)), "text:null");
        check("sealed-code", label(new CodeSignal(8)), "code:8");
        check("sealed-null", label(null), "null");

        Object uncertain = "hello";
        System.out.println(
                "Object-to-Integer=" + (uncertain instanceof Integer n));

        Object nestedNull = new TextSignal(null);
        if (nestedNull instanceof TextSignal(String text)) {
            System.out.println("nested-null-matched=" + (text == null));
        }

        System.out.println("ALL PASSED: 10");
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 ImpossiblePatternDemo.java
java ImpossiblePatternDemo
~~~

**Expected output:**

~~~text
PASS text-ok -> valid:ok
PASS text-blank -> other
PASS text-null -> other
PASS code-record -> code:7
PASS plain-integer -> other
PASS plain-string -> other
PASS input-null -> null
PASS sealed-text-null -> text:null
PASS sealed-code -> code:8
PASS sealed-null -> null
Object-to-Integer=false
nested-null-matched=true
ALL PASSED: 10
~~~

### What the Test Proves

1. `TextSignal("ok")` with the pattern `TextSignal(String text)` and a valid guard is classified as `"valid:ok"`.
2. `TextSignal(null)` is not accepted as valid text data because of the **guard `text != null`**, **not** because the component pattern `String text` itself is guaranteed to fail.
3. `CodeSignal(7)` matches the record pattern `CodeSignal(int code)`.
4. A direct integer `7` and string `"ok"` do not match either record pattern, even though `inspect`'s parameter has static type `Object`, making the check valid.
5. `label` covers both permitted subtypes of `Signal` and handles a `null` selector; a `text == null` component is still a valid `TextSignal` for the type pattern `case TextSignal t`.
6. `Object-to-Integer=false` verifies a pattern that is **statically possible** but does not match the runtime value.
7. `nested-null-matched=true` tests the case where an **unconditional** component pattern inside a record is allowed to match `null`.

The `check` method throws `AssertionError` if any expectation fails. Therefore, the line `ALL PASSED: 10` appears only after all ten runtime checks pass. The additional checks for `Object` and `null` are printed afterward to emphasize the difference from compile-time errors.

## 9. How to Test Cases That the Compiler Must Reject

A runtime test suite **cannot** directly verify that an intentionally invalid program is rejected by the compiler. Create **separate** small files for *negative compile tests* instead of putting that code into the runnable program in Section 8.

For example, `ImpossibleType.java`:

~~~java
public class ImpossibleType {
    public static void main(String[] args) {
        String text = "abc";
        if (text instanceof Integer number) {
            System.out.println(number);
        }
    }
}
~~~

Run:

~~~bash
javac --release 21 ImpossibleType.java
~~~

**Expected:** `javac` reports a compile-time error because `String` cannot be converted to `Integer`; compilation fails. There is no stdout from a running Java program in this example.

You can test the other three error examples in the same way:

- **Incompatible record component:** `Fixed(String value)` but using `Fixed(Integer n)`.
- **Type excluded by hierarchy:** a value with static type `Signal` but requiring the pattern `String s`.
- **Dominated `switch` branch:** `case Number n` appearing before `case Integer i`.

Inspect the **cause in the error message**, not just a non-zero exit code: a syntax error from a missing bracket does not prove that the compiler detected an impossible pattern.

If using a build system, negative compile cases should be run via a dedicated harness that marks “compilation failed as expected” as **PASS**; do not mix them into the application's main Java sources.

## 10. Diagnostic Checklist When the Compiler Reports a Pattern Error

When encountering a type error or unreachable branch, go through these steps in order:

1. **Identify the static type of the selector/expression.** Is it `String`, `Object`, an interface, a generic record, or a `sealed` type?
2. **Check convertibility between the static type and the pattern type.** Two incompatible `final` classes usually have no valid match path. An `Object` variable is broader and may require a runtime check.
3. **If it is a record pattern, inspect each component.** Is the declared component type compatible with the subpattern? For generic records, how are the type arguments inferred?
4. **If it is a `switch`, read the branches from top to bottom.** Does a broader branch dominate a more specific branch below it? Do you need to reorder them or split out a `when` guard?
5. **If generics are involved, distinguish an uncheckable type argument from a genuinely impossible type.** `List<String>` cannot be checked in general via `instanceof` from `Object` due to type erasure; `List<?>` only checks the list type.
6. **Test `null` both at the outer level and inside components.** Do not assume an unconditional record component pattern always rejects `null`.
7. **Write runtime tests for valid paths**, and negative compile tests for cases the compiler must reject. One type of test cannot substitute for the other.

## 11. Common Misconceptions to Avoid

**Misconception 1 — the compiler knows every runtime value.** Java does not infer that an `Object` holds `"abc"` forever just because it is currently assigned a string. `instanceof Integer` from static type `Object` is a valid expression and simply returns `false` if the value does not match.

**Misconception 2 — every non-matching pattern is a compile-time error.** A different value type, missing data, a failing guard, or `null` can cause a valid pattern not to match at runtime. A compile-time error occurs when type rules or branch ordering forbid writing the pattern that way.

**Misconception 3 — a dominated `case` means the target type is impossible.** `Integer` can certainly appear; the mistake is that `Number` placed earlier already accepts all `Integer` values. Reordering from specific to general usually resolves it.

**Misconception 4 — record patterns always reject every `null` component.** An unconditional component pattern can accept `null`; you must check for `null` before operating on the bound reference variable.

**Misconception 5 — casting to “bypass” the compiler is the right solution.** Casting through `Object` or a raw type may make the code compile, but it increases the risk of `ClassCastException` and sacrifices type safety. Fix the type design and choose a pattern that matches the data.

**Misconception 6 — the compiler enforces business rules for you.** Conditions like “quantity is always positive” or “this state never pairs with that data type” must be modeled with types, validation, or business tests if you want corresponding guarantees.

**Remember:** A pattern that is truly “impossible” by **static typing** is generally rejected by Java at compile time. A **dominated** `case` is rejected because it can never be selected after a broader branch. A valid pattern that **does not match at runtime** simply reflects the current value. Clearly distinguishing these three phenomena — and being careful with `null` in record components — is the foundation for writing safe, maintainable pattern matching in Java 21+.
