# Relationship Between Target, Pattern, and Pattern Variable in Java

In **pattern matching with `instanceof`** (stable and available on Java 17), three concepts are linked together in a chain: the **target** is the value being tested; the **pattern** describes the condition for that value to match; and the **pattern variable** receives the matched value under a specific static type. Understanding this relationship accurately helps avoid repetitive casting and use variables safely according to control flow.

## 1. Reading an Expression Correctly

```java
Object target = "Java";
if (target instanceof String text) {
    System.out.println(text.length());
}
```

| Component | In the Example | Role |
| --- | --- | --- |
| Target (object/expression being tested) | `target`, on the left of `instanceof` | Provides the value at runtime; here the value is a reference to the string `"Java"`. |
| Pattern | `String text`, on the right of `instanceof` | This is a **type pattern**: it requires the value to have a type compatible with `String`, while declaring the variable name that will be bound upon matching. |
| Pattern variable | `text` | Bound to the value only when the pattern matches; within the valid usage scope, the compiler knows `text` has type `String`. |

Specifically, `String` is the **type of the pattern**, and `text` is the **pattern variable name**; the entire pair `String text` is the pattern. `instanceof` is the operator performing the test, not part of the variable name. The name `target` is just a variable name in the example, not a Java keyword; the left-hand side can be any expression returning a reference.

When the condition is true, `text.length()` is valid because `text` has static type `String`. The result is `4`. There is no need to write `(String) target`.

## 2. Mechanism: From Target to Binding

With `target instanceof String text`, you can trace it step by step:

1. **Evaluate the target** to obtain its value. If the left-hand side is a method call, that expression is evaluated once for this test.
2. **Test the type pattern** against the value at runtime. With `String text`, the value must be non-`null` and an object compatible with the type `String`.
3. **Binding on match**: Java binds the reference to that object to the pattern variable `text`, under the static type `String`. The true branch executes and can access `text`.
4. **No binding on mismatch**: the `instanceof` result is `false`; no valid `text` value exists for the false branch to use.

The relationship can be summarized as:

```text
target (expression -> runtime value)
    |
    v
instanceof + pattern (e.g., String text)
    |-- match --> true  --> bind text --> use text where a match is guaranteed
    |
    +-- no match --> false --> do not bind text
```

**A pattern variable does not create a new object and does not copy the object.** Immediately after matching, `target` and `text` refer to the same object; they differ only in the static type the compiler allows you to use. If you later reassign `text`, the two variables may no longer point to the same object.

## 3. Static Type of Target, Pattern Type, and Runtime Type

Three things must be distinguished:

- **Static type of the target**: the type the compiler knows from the declaration or expression. In `Object target = "Java"`, the static type of `target` is `Object`.
- **Runtime type of the value**: the actual class of the object, which in the example is `String`.
- **Type of the pattern variable**: the type written in the pattern; `String text` gives `text` the static type `String` after matching.

The pattern type does not have to be identical to the runtime class. For example:

```java
Object target = new StringBuilder("Java");
if (target instanceof CharSequence sequence) {
    System.out.println(sequence.length());               // 4
    System.out.println(sequence.getClass().getSimpleName()); // StringBuilder
}
```

`StringBuilder` implements the `CharSequence` interface, so the pattern `CharSequence sequence` matches. The variable `sequence` has static type `CharSequence`; calling `length()` is valid because this method belongs to the interface. It still points to the actual `StringBuilder` object. Conversely, you cannot call a `StringBuilder`-specific method through `sequence` if `CharSequence` does not declare that method.

The compiler also checks **type compatibility** before the program runs. For example, `Object target` can hold a `String`, so testing with `String text` is valid. If `target` is already declared as `String`, writing `target instanceof String text` may be rejected because the type pattern test is trivially true for any non-`null` value of that static type; use the existing variable directly, and check for `null` separately if needed. Pattern matching should not be used for a meaningless type check.

When `target == null`, every type pattern here **does not match**: `null instanceof String text` is `false`, without throwing a `NullPointerException` just from the `instanceof` operator. Pattern matching checks the **type**, not string content like `equals`.

## 4. Runnable Example: All Three Roles in One Program

Save as `MatchingRolesDemo.java`:

```java
public class MatchingRolesDemo {
    static void describe(Object target) {
        if (target instanceof String text) {
            System.out.println("type=String; value=" + text);
            System.out.println("length=" + text.length());
            System.out.println("sameReference=" + (target == text));
        } else {
            System.out.println("no match: " + target);
        }
    }

    public static void main(String[] args) {
        describe("Java");
        describe(42);
        describe(null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac MatchingRolesDemo.java
java MatchingRolesDemo
```

Exact output:

```text
type=String; value=Java
length=4
sameReference=true
no match: 42
no match: null
```

First call: `target` points to a `String`; the pattern `String text` matches, so `text` is bound and `length()` can be called. Comparing `target == text` returns `true` because right at binding, both references point to the same object. Second call: `target` is an `Integer`, which does not match `String`. Third call: `target` is `null`, which also does not match. In the latter two calls, only the `else` branch runs.

## 5. Pattern Variable Scope Depends on Control Flow

Pattern variables follow **flow scoping** rules: the variable can only be used where the compiler can prove that the pattern has matched. It is not simply scoped to the entire block containing the `instanceof` expression.

**In the true branch:**

```java
if (target instanceof String text) {
    System.out.println(text.toUpperCase()); // Valid: String has matched
} else {
    // Cannot use text: pattern is not guaranteed to have matched
}
```

**With `&&`:** the right-hand side runs only when the left-hand side is true, so the variable is already bound.

```java
if (target instanceof String text && text.length() >= 4) {
    System.out.println(text);
}
```

**With `||`:** the right-hand side runs only when the left-hand side is false, so you cannot rely on a pattern on the left-hand side to use the variable on the right-hand side. The following intentionally **does not compile**:

```java
// Invalid: when evaluating the right-hand side, the pattern String text has not matched.
if (target instanceof String text || text.isBlank()) {
    System.out.println("...");
}
```

**After an early exit branch:** if the non-matching branch terminates the method with `return` or cannot continue, subsequent statements can use the pattern variable.

```java
static int lengthOrMinusOne(Object target) {
    if (!(target instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid: all paths reaching here have matched
}
```

In the ordinary case below, the last statement **does not compile**, because after the `if` there is still a path where the pattern did not match:

```java
// Suppose target is Object.
if (target instanceof String text) {
    System.out.println(text);
}
// System.out.println(text); // Invalid: could have taken the non-matching branch.
```

The `!` operator reverses the condition, but does not lose the binding semantics: Java analyzes which paths are guaranteed to have `text`.

## 6. Runnable Example: Compound Conditions and Guard Clauses

Save as `FlowScopeDemo.java`:

```java
public class FlowScopeDemo {
    static void check(Object target) {
        if (target instanceof String text && text.length() >= 4) {
            System.out.println("Long string: " + text);
        } else {
            System.out.println("Not a long string");
        }
    }

    static String label(Object target) {
        if (!(target instanceof String text)) {
            return "Not String";
        }
        return "String(" + text.length() + ")";
    }

    public static void main(String[] args) {
        check("Java");
        check("Go");
        check(null);
        System.out.println(label("Hello"));
        System.out.println(label(123));
    }
}
```

```bash
javac FlowScopeDemo.java
java FlowScopeDemo
```

```text
Long string: Java
Not a long string
Not a long string
String(5)
Not String
```

The `&&` condition only reads `text.length()` when `target` is actually a `String`. In `label`, all non-matching values `return` immediately; therefore, the last line only receives matched values.

## 7. Comparison with Traditional `instanceof` and Casting

The old way:

```java
if (target instanceof String) {
    String text = (String) target;
    System.out.println(text.length());
}
```

With a type pattern:

```java
if (target instanceof String text) {
    System.out.println(text.length());
}
```

Both express the intent to work only with strings. A type pattern combines the type check and naming a variable that already has the appropriate type; it eliminates writing a manual cast inside the checked branch, reducing the chance of casting to the wrong type or using the wrong variable. This is a runtime type check with binding, **not** a mechanism for automatically destructuring an object's properties.

## 8. Common Misconceptions to Avoid

1. **Thinking `target` and the pattern variable are two different objects.** After matching, they refer to the same original object. The `pattern variable` is simply a new name with the static type specified by the pattern.
2. **Thinking the pattern variable exists even if the check fails.** Binding occurs only on a match; use the variable in the true branch, on the right-hand side of `&&`, or after an early exit path that proves a match.
3. **Confusing the pattern with the variable name.** In `target instanceof String text`, the full pattern is `String text`; `text` is only the variable introduced by the pattern.
4. **Assuming `instanceof` checks content.** Both `"Java"` and `"Go"` match the type pattern `String text`; to compare content, use methods like `equals` or `isBlank` after matching.
5. **Writing a type pattern with generic type arguments that cannot be checked at runtime.** For example, with `Object target`, `target instanceof java.util.List<String> items` is invalid because Java cannot determine `String` in the type argument at runtime. You can check `target instanceof java.util.List<?> items`, then inspect individual elements when needed.
6. **Assuming a pattern variable is `final` by default.** In Java 17, a pattern variable can be reassigned within its valid scope, for example `text = text.strip();`. This reassignment changes the value of `text`, not `target` itself; if the variable is captured by a lambda, the `final` or *effectively final* rules still apply just like with any other local variable.
7. **Assuming patterns work across all Java versions with the same syntax.** Type patterns for `instanceof` were stabilized by Java 17; other pattern syntaxes, such as patterns in `switch`, have their own support milestones. Both programs in this lesson use syntax that runs on Java 17+.

## 9. How to Self-Check When Reading Code

When encountering `expression instanceof Type variable`, answer these questions in order: **(1)** what value does `expression` produce and what is its static type; **(2)** is the runtime value non-`null` and compatible with `Type`; **(3)** if it matches, what reference is `variable` bound to and what is its static type; **(4)** at the line where you want to use `variable`, do all paths reaching it guarantee that the pattern has matched?

These four questions directly connect **target → pattern → pattern variable → flow scoping**, forming the foundation for reading and writing pattern matching clearly in Java.
