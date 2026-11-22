# Record Patterns with Generic Records in Java

A **generic record** is a `record` with type parameters, such as `Box<T>` or `Pair<K, V>`. A **record pattern** lets you check whether an object is an instance of a matching record type while deconstructing its components into variables that can be used immediately. When combining both features, Java preserves compile-time type checking while inferring component types based on the record's generic type.

This lesson focuses on **how to write record patterns for generic records**, type argument inference, nested record patterns, handling data of unknown types, and limitations caused by **type erasure**. The examples run on **Java 21 or later**; record patterns were finalized in Java 21 via JEP 440, so no preview flag is required.

## 1. What Roles Do Generic Records and Record Patterns Play?

Declaring generic records:

```java
record Box<T>(T value) {}
record Pair<K, V>(K key, V value) {}
```

- `Box<T>` has one component, `value`, whose type is determined by the type parameter `T`.
- `Pair<K, V>` has two components, `key` and `value`, using `K` and `V` respectively.
- In `Box<String>`, the type of the `value` component is `String` at the source-code level. In `Pair<String, Integer>`, the type of `key` is `String` and the type of `value` is `Integer`.
- A record is still a class with a concrete type; its components are accessed through accessors such as `value()` and `key()`. A record pattern provides a way to extract those values without calling accessors directly in each branch.

Example without a record pattern:

```java
// Assume 'box' is already declared as Box<String>.
if (box != null) {
    String text = box.value();
    System.out.println(text);
}
```

Equivalent component extraction using a record pattern:

```java
// Assume 'box' is already declared as Box<String>.
if (box instanceof Box(var text)) {
    System.out.println(text);
}
```

In `Box(var text)`, `Box` is the record type and `var text` is a component pattern. It declares the variable `text` from the `value` component. Because this is a pattern-matching check, the `if` branch does not execute when `box == null`.

## 2. Writing Explicit Type Arguments in a Record Pattern

When the expression being matched already has type `Box<String>`, you can write it out explicitly:

```java
// 'box' has static type Box<String>.
if (box instanceof Box<String>(String text)) {
    System.out.println(text.toUpperCase());
}
```

In `Box<String>(String text)`:

1. `Box<String>` specifies the generic record with type argument `String`.
2. `String text` is the component pattern, checking the component value against type `String` and binding the variable `text`.
3. After a match, the compiler knows `text` has type `String`, so calling `toUpperCase()` is valid.

Generic record instantiation syntax is **different** from record pattern syntax: `new Box<>("Java")` creates an object, whereas `Box<String>(String text)` checks and deconstructs an existing object.

Note on `null` components: a component pattern of the form `String text` does not match a `null` value. If you want to accept `null` as well, you can use `var text` and then handle the `text == null` case yourself.

## 3. Type Argument Inference: `Box(var text)`

Java 21 allows the compiler to **infer the type arguments of a generic record pattern** from the static type of the expression being matched.

```java
// Illustrative snippet; 'box' has type Box<String>.
if (box instanceof Box(var text)) {
    // The compiler infers text as String.
    System.out.println(text.toUpperCase());
}
```

Here, `Box(var text)` is equivalent in effect to `Box<String>(String text)` in this context. There is no need to repeat `<String>` in the pattern; the compiler already knows the type from `Box<String>`.

The same applies to `Pair<K, V>`:

```java
// 'pair' has type Pair<String, Integer>.
if (pair instanceof Pair(var key, var count)) {
    String label = key;   // Valid: key is inferred as String.
    Integer total = count; // Valid: count is inferred as Integer.
    System.out.println(label + ": " + total);
}
```

However, **`var` does not by itself verify that a value is `String` or `Integer`** if the input only has type `Object`. `var` takes the type that the compiler infers from context. The less generic information the input expression's type has, the more general the inferred component type will be; you cannot call `String`-specific methods if the compiler only knows the variable is `Object`.

## 4. Nested Record Patterns with Generic Records

A generic record can contain another generic record:

```java
record Box<T>(T value) {}
record Envelope<T>(String label, Box<T> box) {}
```

Given an `Envelope<String>`, the compiler knows that the `box` component has type `Box<String>`. We can deconstruct two levels using:

```java
// 'envelope' has type Envelope<String>.
if (envelope instanceof Envelope(var label, Box(var message))) {
    // The compiler infers label as String and message as String.
    System.out.println(label + ": " + message.toUpperCase());
}
```

Reading from outside in:

- `Envelope(var label, ...)` extracts the `label` component.
- `Box(var message)` checks whether the `box` component is a matching `Box` instance and extracts `value`.
- Because the static type of the input is `Envelope<String>`, two levels of inference lead to `message` having type `String`.
- If `envelope` is `null`, or `envelope.box()` is `null`, the entire nested record pattern fails to match. An existing `Box` whose `value == null` can still match `Box(var message)`, in which case `message == null` and must be checked before calling methods on it.

Record patterns can be used with `instanceof`, `switch` statements, and `switch` expressions. Regardless of how deeply nested the pattern is, the number of component patterns at each level must match the number of components declared in the record at that level.

## 5. When the Input Is `Object`: Wildcards and Component Checks

**Generics in Java use type erasure**: the type parameter `T` in `Box<T>` is not stored as a runtime type tag that can be directly checked per object at runtime. Therefore, for a variable whose static type is `Object`, you cannot simply write:

```java
// DOES NOT COMPILE — example of an unsafe conversion.
Object input = new Box<>("Hello");
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

Reason: checking `Box<String>` from an `Object` would require an **unchecked conversion**; the runtime cannot independently verify the `<String>` type argument of `Box`.

The safe approach is to match the record with the wildcard `<?>` and directly check the **component value**:

```java
// Valid snippet in Java 21+.
Object input = new Box<>("Hello");

if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

`Box<?>(String text)` checks that the object is a `Box` record and then checks whether the component value is a non-`null` `String`. This is **not proof** that the original object was declared with the exact type argument `Box<String>`. For example, a `Box<CharSequence>` holding a `String` object can also match this pattern.

If you want to read the component when its type is unknown:

```java
// Valid snippet in Java 21+.
if (input instanceof Box<?>(var value)) {
    System.out.println(value);
}
```

Here, you should not assume `value` is a `String`. You can check further with `value instanceof String s` or use a specific pattern branch.

Comparison table:

| Input expression (static type) | Pattern | Evaluation |
| --- | --- | --- |
| `Box<String>` | `Box<String>(String s)` | Valid; type argument is known at compile time |
| `Box<String>` | `Box(var s)` | Valid; infers `s` as `String` |
| `Pair<String, Integer>` | `Pair(var key, var n)` | Valid; infers `String` and `Integer` |
| `Object` | `Box<String>(var s)` | Invalid because it requires an unchecked conversion |
| `Object` | `Box<?>(String s)` | Valid; checks that the component value is `String` |
| `Object` | `Box<?>(var v)` | Valid; `v` is handled with the safe type inferred by the compiler |

## 6. Complete Runnable Example on Java 21+

Create the file **`GenericRecordPatternsDemo.java`**:

```java
public class GenericRecordPatternsDemo {
    record Box<T>(T value) {}
    record Pair<K, V>(K key, V value) {}
    record Envelope<T>(String label, Box<T> box) {}

    static String knownBox(Box<String> box) {
        if (box instanceof Box(var text)) {
            return text.toUpperCase();
        }
        return "null box";
    }

    static String nested(Envelope<String> envelope) {
        if (envelope instanceof Envelope(var label, Box(var message))) {
            return label + ": " + message.toUpperCase();
        }
        return "no nested box";
    }

    static String inspect(Object obj) {
        if (obj instanceof Box<?>(String text)) {
            return "String: " + text;
        }
        if (obj instanceof Box<?>(var value)) {
            return "Other: " + value;
        }
        return "Not a box";
    }

    static String pair(Pair<String, Integer> pair) {
        return switch (pair) {
            case Pair(var key, var number)
                    when number != null && number > 0 -> key + "=" + number;
            case Pair(var key, var number) ->
                    key + "=nonpositive (" + number + ")";
        };
    }

    public static void main(String[] args) {
        System.out.println(knownBox(new Box<>("java")));
        System.out.println(nested(
                new Envelope<>("email", new Box<>("hello"))));
        System.out.println(nested(
                new Envelope<>("sms", null)));
        System.out.println(inspect(new Box<>("hello")));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(inspect(new Box<>(null)));
        System.out.println(inspect("other"));
        System.out.println(pair(new Pair<>("tasks", 5)));
        System.out.println(pair(new Pair<>("tasks", 0)));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac GenericRecordPatternsDemo.java
java GenericRecordPatternsDemo
```

Output:

```text
JAVA
email: HELLO
no nested box
String: hello
Other: 42
Other: null
Not a box
tasks=5
tasks=nonpositive (0)
```

Explanation:

1. `knownBox` receives a `Box<String>`, so `Box(var text)` correctly infers `String`; `toUpperCase()` works.
2. `nested` deconstructs two generic records via `Envelope(var label, Box(var message))`. For `Envelope("sms", null)`, the `box` component does not match the `Box(...)` record pattern, so it returns `"no nested box"`.
3. `inspect` receives an `Object`: the `Box<?>(String text)` branch only matches a non-`null` `String` component. The next branch, `Box<?>(var value)`, matches both `Integer` and `null`. The string `"other"` is not a `Box`.
4. `pair` uses a record pattern in a `switch` expression. The variable `number` is inferred as `Integer`, and the guard `number != null` prevents an auto-unboxing `NullPointerException` when comparing with `0`. The second branch handles non-positive or `null` values.

In a real program, if `knownBox` or `nested` receives a component whose value is `null`, calling `toUpperCase()` can throw a `NullPointerException`. Extracting a component with a record pattern does not automatically guarantee that the component is non-`null`.

## 7. Important Limitations: Type Erasure, `null`, Primitives, and `switch` Exhaustiveness

### Type erasure still applies

`Box<String>` and `Box<Integer>` share the same raw class `Box` at runtime. Therefore:

- You cannot use a record pattern to distinguish the **generic type arguments** `String` and `Integer` via an unchecked test from `Object`.
- You can check the **component value** at runtime, such as `Box<?>(String s)` or `Box<?>(Integer n)`.
- If `T` is an interface or superclass type, the component value may be an instance of a subtype; a pattern on a subtype can match without proving what generic type argument was used when the record was created.
- Avoid using the raw type `Box` to bypass type checking; raw types lose generic guarantees and can trigger unchecked warnings. Prefer `Box<?>` when the type is unknown.

### `null` has two distinct positions

- `null` as the **record object itself**: no record pattern `Box(...)` will match.
- `null` as a **component value**: `Box<?>(var value)` still matches if the `Box` object exists, with `value` equal to `null`. Meanwhile, `Box<?>(String s)` does not match a `null` component because it does not satisfy the `String` type pattern.

In particular, a `switch` with a `null` selector requires a `case null` branch if you want to handle it without throwing an exception. A `switch` expression must also satisfy the compiler's exhaustiveness check; nested record patterns might not cover a `null` record component and thus may require an additional branch or `default`.

### `T` must be a reference type

A generic type argument must be a reference type: write `Box<Integer>` instead of `Box<int>`. The record itself can still declare non-generic primitive components, for example:

```java
record Labeled<T>(T label, int score) {}

// Snippet: 'item' has type Labeled<String>.
if (item instanceof Labeled(var name, var score)) {
    System.out.println(name + ": " + score); // name: String; score: int.
}
```

## 8. Common Mistakes When Writing Generic Record Patterns

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Writing `Box<String>(var x)` when the input has type `Object` | Compile error due to unchecked conversion | Use `Box<?>(String x)` to check the component, or preserve the type information earlier |
| Assuming `Box(var x)` always infers `x` as `String` | Incorrect if the input lacks generic type information | Check the static type of the input; use an explicit type pattern when needed |
| Thinking `Box<?>(String x)` proves `T` is `String` | Confuses a runtime value check with a compile-time generic type | It only asserts that the current component value is a `String` |
| Calling `x.toUpperCase()` after `Box(var x)` without handling `null` | May throw `NullPointerException` | Check `x != null` or use an appropriate component type |
| Writing `Pair(var key)` for a two-component record | Component pattern count mismatch | Write all components: `Pair(var key, var value)` |
| Using `Box<int>` | Java generics do not accept primitive types | Use `Box<Integer>` |
| Overusing raw types and unchecked casts | Loses type safety and can cause errors later | Use explicit type arguments or wildcards intentionally |

## 9. Self-Check Exercises

Given two records:

```java
record Result<T>(String status, T payload) {}
record Batch<T>(Result<T> first, Result<T> second) {}
```

**Exercise 1.** Given `Result<Integer> r`, extract `status` and `payload` without repeating `<Integer>` in the pattern. What types does the compiler infer?

**Answer:** `if (r instanceof Result(var status, var payload)) { ... }`. The variable `status` has type `String`, and `payload` has type `Integer`.

**Exercise 2.** Given `Batch<String> batch`, extract the contents of `first.payload` using a nested record pattern.

**Answer:**

```java
// Illustrative snippet; 'batch' has type Batch<String>.
if (batch instanceof Batch(Result(var status, var payload), var second)) {
    System.out.println(status + ": " + payload);
}
```

`payload` is inferred as `String`. If `batch` or `first` is `null`, the nested pattern does not match. `second` has type `Result<String>` (and may be `null`).

**Exercise 3.** From `Object input`, can you write `input instanceof Result<String>(var status, var value)` to check whether `payload` is a `String`?

**Answer:** No; that is a generic type argument check requiring an unchecked conversion. Use `Result<?>(var status, String value)` to check whether the `payload` component value is a non-`null` `String`.

## 10. Key Takeaways

- Generic record patterns combine **record deconstruction** with **generic type information**. For example, `Box(var value)` can infer the component type from `Box<String>`.
- You can write type arguments explicitly (`Box<String>(String text)`) or omit them so the compiler infers them (`Box(var text)`).
- When the input only has type `Object`, use a wildcard and check the component, such as `Box<?>(String text)`; do not test `Box<String>` directly with an unchecked pattern.
- Nested patterns such as `Envelope(var label, Box(var message))` still infer types across multiple levels and still follow `null`-matching rules.
- Record patterns were finalized in **Java 21** (JEP 440); pattern matching for `switch` was also finalized in Java 21 (JEP 441).

Official documentation: [Oracle — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
