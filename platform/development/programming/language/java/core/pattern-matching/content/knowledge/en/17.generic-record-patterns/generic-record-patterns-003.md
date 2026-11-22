# Generic record patterns: pattern type arguments and target types in Java 21

## 1. Purpose and context

A **generic record pattern** is a record pattern used with a `record` that has a type parameter, for example `record Box<T>(T value) {}`. When matching the pattern, Java both checks the record structure and allows accessing components through nested sub-patterns. The key question is: **where are the component type and the pattern variable type determined from?**

Two concepts must be distinguished:

- **Pattern type argument**: the type argument written after the record name in the pattern, such as the `<String>` part of `Box<String>(var text)`. It can be written explicitly or inferred by the compiler using `Box(var text)`.
- **Target type (the target type of pattern matching)**: the static type that the compiler knows about the value being matched against the pattern, such as `Box<String>`, `Box<? extends CharSequence>`, or `Object`. With nested record patterns, the type of the **corresponding component in the outer record** serves as the type context used to infer the inner pattern.

Record patterns were standardized in **Java 21 (JEP 440)** and can be used with `instanceof` or pattern matching in `switch`. The examples in this lesson compile with Java 21+ without enabling preview features.

> Core takeaway: generic type arguments are inferred primarily from **the type already known at compile time**. Java cannot inspect the `T` of an arbitrary `Box<T>` at runtime to prove the object is a `Box<String>`, because generic information is largely removed (type erasure).

## 2. Explicit type arguments vs. inference from the target type

Given the definition:

```java
record Box<T>(T value) {}

Box<String> box = new Box<>("java");
```

The following two forms have equivalent meaning in a context where `box` has static type `Box<String>`:

```java
// Explicitly specify the type argument of the record pattern:
if (box instanceof Box<String>(var text)) {
    System.out.println(text.toUpperCase());
}

// Let the compiler infer from the target type Box<String>:
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase());
}
```

Both print `JAVA`. In the first form, `<String>` is the **pattern type argument** and `var text` receives the type `String`. In the second form, `Box(var text)` is inferred from the `Box<String>` context, so the compiler also knows `text` has type `String`. Therefore, calling `text.toUpperCase()` is valid without casting.

You can write `Box<String>(String text)` to explicitly specify both the type argument and the component's type pattern. However, those two positions serve different roles: `Box<String>` refers to **the record type checked according to the type system rules**, whereas `String text` checks/binds **the inner component**. When the component is already guaranteed to be `String` by the target type, using `var` is usually concise and easy to maintain.

The syntax `new Box<>("java")` uses the diamond `<>` to infer type arguments when **creating an object**. Conversely, `Box(var text)` is the syntax for **matching and deconstructing a record**. Both involve type inference, but they are two distinct mechanisms used in different contexts.

## 3. How the target type changes what the compiler can know

Consider two expressions with the same runtime object:

```java
Box<String> typed = new Box<>("hello");
Object unknown = typed;
```

With `typed instanceof Box(var x)`, the context already knows `Box<String>` and `x` has type `String`. With `unknown instanceof Box(var x)`, the expression on the left only has static type `Object`. The compiler can check at runtime that `unknown` is a `Box` and extract the component; however, it **cannot infer `String` solely from an erased generic type argument**. The variable `x` in this case is treated as `Object`, so `x.toUpperCase()` does not compile.

To distinguish the **actual runtime type of the component** when the input is `Object`, use a type pattern for the component:

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(String text)) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

`Box(String text)` checks that the object is a `Box` **and** its component is a `String`. If the inner value is an `Integer`, the pattern does not match. This is a valid runtime check on the component, unlike asking to check the generic parameter `Box<String>` at runtime.

**The following snippet does not compile:**

```java
Object unknown = new Box<>("hello");

// ERROR: Object cannot be safely cast to Box<String>.
if (unknown instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

Even though the example creates `unknown` from a string, its **static type** is `Object`. Java does not allow the record pattern `Box<String>(...)` in a situation that requires an unchecked conversion. The problem cannot be solved by trying to force a generic type argument into the pattern.

Practical rule: when the data already has a precise type like `Box<String>`, you can write `Box<String>(...)` explicitly or let the compiler infer `Box(...)`; when the input is too general like `Object`, use `Box(var x)` and inspect the component afterward, or use `Box(String x)` if you specifically need a `String`.

## 4. Recursive inference from the outer record's target type

Generic records can be nested across multiple levels:

```java
record Box<T>(T value) {}
record Pair<A, B>(A first, B second) {}
record Envelope<T>(String tag, Box<Pair<String, T>> data) {}
```

Suppose a method receives `Envelope<Integer> env`:

```java
if (env instanceof Envelope(var tag, Box(Pair(var name, var count)))) {
    System.out.println(tag + ": " + name.toUpperCase() + " -> " + (count + 1));
}
```

The compiler infers step by step:

1. **Outer level:** from `env` having static type `Envelope<Integer>`, it knows `T = Integer`. The pattern `Envelope(...)` matches this record.
2. **Component `tag`:** `Envelope.tag` is `String`, so `var tag` has type `String`.
3. **Component `data`:** substituting `T` with `Integer`, it has type `Box<Pair<String, Integer>>`. That becomes the **target type** for the inner `Box(...)` pattern.
4. **Component `Box.value`:** has type `Pair<String, Integer>`. That in turn becomes the **target type** for `Pair(...)`.
5. **Final two components:** `name` has type `String`; `count` has type `Integer`. Therefore, calling `name.toUpperCase()` and computing `count + 1` are both valid. The `+ 1` operation performs unboxing on `Integer`, so if `count == null` it can throw a `NullPointerException` during evaluation; type inference does not replace null checks on components.

We can write the type arguments explicitly (when needing to clarify the type structure):

```java
if (env instanceof Envelope<Integer>(
        var tag,
        Box<Pair<String, Integer>>(
            Pair<String, Integer>(var name, var count)))) {
    System.out.println(name + ": " + count);
}
```

The explicit form is more verbose; when the target type is clear, the chain `Envelope(var tag, Box(Pair(var name, var count)))` is usually easier to read. The key point to remember is that the type argument of a **nested pattern** is not inferred arbitrarily from the runtime value, but from **the component type provided by the enclosing pattern**.

If the `data` component is `null`, the inner `Box(...)` does not match because there is no `Box` object to deconstruct. Similarly, if the inner `Pair` is `null`, `Pair(...)` does not match. However, a plain `var` component can accept `null`; you must distinguish between "a nested record is null" and "a component inside a record has the value null".

## 5. Wildcard target types and limits of inference

Consider this target type:

```java
Box<? extends CharSequence> box = new Box<>("hello");

if (box instanceof Box(var text)) {
    System.out.println(text.length()); // 5
}
```

`text` is used through the `CharSequence` interface — the upper bound of the wildcard `? extends CharSequence`. Calling `length()` is valid, but `text.toUpperCase()` is invalid because `CharSequence` does not declare that method. Even though the current object holds a `String`, the type system does not treat every `CharSequence` as a `String`.

To call an API that only exists on `String`, you must check further:

```java
if (box instanceof Box(var text) && text instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
}
```

Do not use `Box<String>(var s)` to replace the component check: the static type `Box<? extends CharSequence>` does not allow safely asserting that the exact type argument is `String`.

With `Box<?>`, the compiler cannot conclude on its own that the component is `String`; you can use `Box(String s)` to check the component at runtime. With `Box<Integer>`, `var n` has type `Integer`; with `Box<Number>`, `var n` has type `Number`. **Generic invariance**: `Box<Integer>` is not a subtype of `Box<Number>`, even though `Integer` is a subtype of `Number`.

## 6. Complete example: explicit, inferred, nested, wildcard, and switch

Create the file `GenericRecordPatternDemo.java`:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}
    record Envelope<T>(String tag, Box<Pair<String, T>> data) {}

    static String explicit(Box<String> box) {
        if (box instanceof Box<String>(var text)) return text.toUpperCase();
        return "no match";
    }

    static String inferred(Box<String> box) {
        if (box instanceof Box(var text)) return text.toUpperCase();
        return "no match";
    }

    static String fromObject(Object obj) {
        if (obj instanceof Box(var element)) {
            return element == null ? "Box(null)" : "Box(" + element.getClass().getSimpleName() + ")";
        }
        return "not a Box";
    }

    static int wildcard(Box<? extends CharSequence> box) {
        if (box instanceof Box(var text)) return text.length();
        return -1;
    }

    static String nested(Envelope<Integer> env) {
        if (env instanceof Envelope(var tag, Box(Pair(var name, var count)))) {
            return tag + ": " + name.toUpperCase() + " -> " + (count + 1);
        }
        return "incomplete";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case Box(var item) when item instanceof String s -> "string " + s;
            case Box(var item) -> "box " + (item == null ? "null" : item.getClass().getSimpleName());
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Box<String> textBox = new Box<>("java");
        Envelope<Integer> order = new Envelope<>("E1",
                new Box<>(new Pair<>("items", 4)));

        System.out.println(explicit(textBox));
        System.out.println(inferred(textBox));
        System.out.println(fromObject(new Box<>(123)));
        System.out.println(wildcard(new Box<>("hello")));
        System.out.println(nested(order));
        System.out.println(nested(new Envelope<>("E2", null)));
        System.out.println(classify(new Box<>("ok")));
        System.out.println(classify(new Box<>(27)));
        System.out.println(classify(new Box<>(null)));
        System.out.println(classify(null));
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Expected output:

```text
JAVA
JAVA
Box(Integer)
5
E1: ITEMS -> 5
incomplete
string ok
box Integer
box null
null
```

How to read the output:

- The two `JAVA` lines show that both the pattern with an explicit `<String>` type argument and the pattern inferred by the compiler obtain `String`.
- `Box(Integer)` shows that an input with static type `Object` can still match the `Box` record shape, without being assumed to be "String by default".
- `5` is the length of the string in `Box<? extends CharSequence>`; the type the code can use is the common `CharSequence` API.
- `E1: ITEMS -> 5` demonstrates inference across three generic record patterns and unboxing of the `Integer` component.
- `incomplete` occurs because `Envelope.data == null`: the nested `Box(...)` does not match.
- The two lines `string ok` and `box Integer` show that `switch` can distinguish the **actual runtime type of the component** using `when item instanceof String s` even when the selector is declared as `Object`.
- `box null` is a valid `Box` record whose component is `null`; the final `null` is the `switch` selector itself being `null`, caught by `case null`.

In `switch`, place the branch with `when` before the general `case Box(var item)` branch. Reversing the order would create a dominated branch and cause a compilation error due to dominance.

## 7. Common compilation errors and misconceptions

| Situation | Why it is wrong or easily confused | How to handle it |
| --- | --- | --- |
| `Object value` then `value instanceof Box<String>(var s)` | Cannot verify the generic argument `String` at runtime due to erasure; the cast requires an unchecked conversion. | Use `Box(String s)` to check the component, or preserve `Box<String>` in the input API. |
| `Box raw` then `raw instanceof Box<String>(var s)` | Raw types lose the required generic constraints. | Avoid raw types; pass `Box<String>` or use `Box(var s)` with an additional check. |
| `Box<Number>` with pattern `Box<Integer>(var n)` | Generic invariance; there is no safe cast from `Box<Number>` to `Box<Integer>`. | Check the actual runtime type of the component if needed, or change the generic contract upfront. |
| Assuming `Box(var s)` always infers `String` from `new Box<>("abc")` | Inference depends on the static target type at the **check site**, not by tracing back to the object creation expression. | Check the variable type, selector type, or component type where the pattern appears. |
| Assuming `Box(String s)` and `Box<String>(var s)` are identical | The first checks a `String` component at runtime; the second is only valid when the `String` type argument is statically safe. | Choose the syntax based on what you intend to check. |
| Assuming `var` creates dynamic typing | `var` still has a compiler-determined static type; you cannot arbitrarily call subtype methods. | Check or narrow the type before calling subtype-specific APIs. |
| Forgetting to check `null` on nested records or components | A nested record pattern does not match a `null` nested record; however, a `var` component can hold `null`. | Write a fallback/non-matching branch, and check nullable components before calling methods or unboxing. |
| Using Java 17 without standard support | Record patterns were only standardized starting in Java 21. | Use JDK 21+ for all examples. |

A separate error example **that must not be included in the runnable file**:

```java
record Box<T>(T value) {}

static void invalid(Object obj) {
    // Does not compile: cannot safely check Box<String> from Object.
    if (obj instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

How to fix it when you need to be sure the component is a string:

```java
static void valid(Object obj) {
    if (obj instanceof Box(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

In cases where the API already receives `Box<String>`, you can use either `Box<String>(var text)` or `Box(var text)`. **The type context is part of what determines whether a pattern is valid.**

## 8. Practical applications and self-check exercise

Common real-world scenarios include generic result wrappers, events carrying payloads, and nested AST structures. Generic record patterns let you extract properly typed data with fewer manual accessor calls and casts. However, avoid nesting too many levels if doing so obscures nullable boundaries or business conditions.

**Exercise:** Given the following records:

```java
record Pair<L, R>(L left, R right) {}
record Box<T>(T value) {}
record Response<T>(int status, Box<Pair<String, T>> payload) {}
```

Fill in the types of `label` and `quantity` in this example, determine the target type of `Pair(...)`, and predict what happens when `payload == null`:

```java
static String display(Response<Long> response) {
    if (response instanceof Response(var status, Box(Pair(var label, var quantity)))) {
        return status + "/" + label + "/" + quantity;
    }
    return "missing payload";
}
```

**Answer:** `Response<Long>` has `T = Long`. The `payload` component has type `Box<Pair<String, Long>>`. Therefore, `Pair(...)` has target type `Pair<String, Long>`; `label` has type `String` and `quantity` has type `Long`. If `payload == null`, the `Box(...)` pattern does not match and the method returns `"missing payload"`. Conversely, if `payload` is a `Box` whose inner `Pair` is `null`, the `Pair(...)` pattern also does not match. If `Pair` exists but `quantity == null`, `var quantity` can still be bound to `null`; you must check for null before unboxing or calling methods.

## 9. Summary of the mechanism

A generic record pattern uses two sources of information: **explicit type arguments** when you write `Record<T>(...)`, or **inference based on the static type of the tested value** when you write `Record(...)`. In multi-level patterns, the component type of the parent record provides the target type for the child pattern, so generic constraints propagate naturally. Type erasure still limits what Java can verify at runtime; to check the content type in general-purpose data, use a component type pattern or an appropriate `instanceof` check.

**References:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns (Generic Records, Type Inference, Nested Record Patterns)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.30).
