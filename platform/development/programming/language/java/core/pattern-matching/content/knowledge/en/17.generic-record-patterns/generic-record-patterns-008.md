# Generic record patterns: Compiler inference and cases requiring explicit types

## 1. Goal and Java Context

When a record has type parameters, for example `record Box<T>(T value) {}`, a **record pattern** allows both testing the record and deconstructing its components. **Compiler inference** is the mechanism by which the compiler infers the type arguments of a record pattern and the types of pattern variables from the **static type of the matched expression** and the component declarations. We do not always have to repeat `Box<String>` and `String`.

```java
record Box<T>(T value) {}

static void print(Box<String> box) {
    if (box instanceof Box(var text)) {
        // The compiler knows text has type String.
        System.out.println(text.toUpperCase());
    }
}
```

Here, `Box(var text)` is inferred to be type-equivalent to `Box<String>(String text)` in a context where the `box` parameter has type `Box<String>`. There is no constructor call in the pattern. `var` performs **static type** inference, not dynamic type inference.

**Version:** Records (including generic records) have been standard since Java 16. Record patterns (JEP 440) have been standard since **Java 21**; this syntax cannot be used with Java 17, and with JDK 21+ `--enable-preview` is not required.

## 2. Two Layers of Inference: Type Arguments and Component Variables

Consider the declarations:

```java
record Box<T>(T value) {}
record Pair<A, B>(A first, B second) {}
```

In `Box(var x)`, two distinct things happen:

1. **Inferring the type argument `T` of the record pattern `Box<T>`** when `Box` omits `<...>`. The type of the target expression at the match site (compile-time target) provides the constraint for `T`.
2. **Inferring the type of the variable `x`** from the type of the `value` component once the record pattern's type arguments have been determined. If `T` is `String`, `x` has type `String`; if `T` is inferred as `Object`, `x` only has type `Object`.

This mechanism applies to `instanceof`, `switch` cases, and nested record patterns. In `Pair(var a, var b)`, `A` and `B` can be inferred independently from the type of the `Pair` being matched.

Comparing contexts:

| Static type of input value | Record pattern | Type safely usable for variable |
| --- | --- | --- |
| `Box<String>` | `Box(var x)` | `String` |
| `Box<? extends Number>` | `Box(var x)` | `x` can be used as `Number` |
| `Pair<String, Integer>` | `Pair(var a, var b)` | `a`: `String`, `b`: `Integer` |
| `Box<Box<String>>` | `Box(Box(var s))` | `s`: `String` |
| `Object` holding a `Box<String>` at runtime | `Box(var x)` | Only guarantees `Object`, does not infer `String` |

**Key point:** The compiler looks at the **static type at the match site**. It does not guess the type argument from the actual runtime contents inside the object. For example, declaring `Object unknown = new Box<>("hello");` does not cause `Box(var x)` to infer `x` as `String`. You must add a pattern that checks the component type if you want to handle strings safely.

## 3. Complete Runnable Example: Inferred, Explicit, Wildcard, Nested, and Switch

Save the code as **`GenericRecordInferenceDemo.java`**:

```java
public class GenericRecordInferenceDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}

    static void run() {
        Box<String> textBox = new Box<>("Java");

        // 1. Compiler infers Box<String> and text: String.
        if (textBox instanceof Box(var text)) {
            String typed = text; // No cast needed.
            System.out.println("Inferred: " + typed.toUpperCase());
        }

        // 2. Explicitly write the type argument and component type.
        if (textBox instanceof Box<String>(String text)) {
            System.out.println("Explicit: " + text.length());
        }

        // 3. Wildcard with upper bound.
        Box<? extends Number> numberBox = new Box<>(42);
        if (numberBox instanceof Box(var number)) {
            Number numeric = number;
            System.out.println("Bounded: " + numeric.intValue());
        }

        // 4. Nested generic record pattern: inference across two Box layers.
        Box<Box<String>> nested = new Box<>(new Box<>("inside"));
        if (nested instanceof Box(Box(var innerText))) {
            String typed = innerText;
            System.out.println("Nested: " + typed);
        }

        // 5. Two type parameters inferred independently.
        Pair<String, Integer> pair = new Pair<>("ok", 3);
        if (pair instanceof Pair(var left, var right)) {
            String label = left;
            Integer count = right;
            System.out.println("Pair: " + label + "/" + count);
        }

        // 6. When the expression only has type Object, var does not automatically become String.
        Object unknown = new Box<>("dynamic");
        if (unknown instanceof Box(var value)) {
            Object general = value;
            System.out.println("General: " + general);
        }

        // 7. Explicit component type checks at runtime.
        if (unknown instanceof Box(String actualString)) {
            System.out.println("Checked: " + actualString.toUpperCase());
        }

        // 8. Record patterns in switch also perform type inference.
        Object mixed = new Box<>(7);
        String kind = switch (mixed) {
            case Box(String s) -> "text=" + s;
            case Box(Integer n) -> "integer=" + n;
            case Box(var any) -> "other=" + any;
            case null -> "null";
            default -> "not-box";
        };
        System.out.println("Switch: " + kind);
    }

    public static void main(String[] args) {
        run();
    }
}
```

Use JDK 21 or later:

```bash
javac --release 21 GenericRecordInferenceDemo.java
java GenericRecordInferenceDemo
```

Stdout:

```text
Inferred: JAVA
Explicit: 4
Bounded: 42
Nested: inside
Pair: ok/3
General: dynamic
Checked: DYNAMIC
Switch: integer=7
```

In part 6, the variable `value` is treated as `Object`, even though the actual runtime value is a string. Part 7 switches to **component checking**: `Box(String actualString)` only matches if the object is a `Box` record whose corresponding component matches type `String`; therefore calling `toUpperCase()` is safe in that branch. In `switch`, the `Box(var any)` branch is placed **after** the specific branches to avoid dominating them. `case null` handles a null selector, while `default` handles objects that are not a `Box`.

## 4. When to Rely on Inference

### Sources with Clear Generic Types

With `Box<String>`, writing it concisely:

```java
if (textBox instanceof Box(var s)) {
    String text = s;
}
```

is usually clear enough and avoids repeating information the compiler already knows. `String text = s` compiles because `s` is `String`. When a record has multiple type arguments, `Pair(var first, var second)` offers the same benefit.

### Nested Generic Types

With `Box<Box<String>>`, two pattern levels can still be inferred:

```java
if (nested instanceof Box(Box(var s))) {
    String text = s;
}
```

The compiler combines the `Box<T>` component declaration with the static type of `nested` to infer the inner component. There is no need to write the verbose `Box<Box<String>>(Box<String>(String s))` in a context that already has complete type information.

### Wildcards and Upper Bounds

With `Box<? extends Number>`, you can only rely on operations that are safe for the upper bound:

```java
if (numberBox instanceof Box(var number)) {
    Number n = number;
    System.out.println(n.doubleValue());
}
```

Do not assume `number` is an `Integer` just because the current data uses `new Box<>(42)`. Another version of the program might supply a `Double` or another subtype of `Number`. If the API requires `Integer`-specific behavior, you must perform a narrower check.

### Data Without Generic Information in Its Static Type

When an object is passed through an `Object` parameter, a wide-typed collection, or an API returning `Box<?>`, inference cannot recover `String` just from the fact that the object was *actually* created with `new Box<>("text")`. Keep the generic type in the method signature if possible; if runtime branching is needed, check the component type with an explicit pattern.

## 5. When Explicit Types Are Needed

**"Explicit types" involves two different decisions:** the record's type argument (`Box<String>`) and the component's pattern (`String s`). They do not have the same effect.

### Case A — Explicit to Clarify a Known Type Contract

If the input variable definitely has type `Box<String>`, both forms below are valid and yield the same variable type:

```java
if (textBox instanceof Box(var s)) {
    System.out.println(s.length());
}

if (textBox instanceof Box<String>(String s)) {
    System.out.println(s.length());
}
```

The explicit form is useful when reading code without tracing back to the input variable's type, or when documentation is explaining the relationship between the type argument and the component. It does **not** add a runtime check that the generic argument is actually `String`: ordinary generic type arguments are subject to **type erasure**.

### Case B — Needing a Runtime Component Type Check

When the parameter is `Object`:

```java
static void process(Object input) {
    if (input instanceof Box(String s)) {
        System.out.println(s.toUpperCase());
    }
}
```

`Box(String s)` provides an explicit runtime condition: the branch is entered only if the record component matches `String`. By contrast, `Box(var s)` in an `Object` context only allows treating `s` as `Object`.

Similarly, you can use `Box(Integer n)`, `Box(java.util.List<?> list)`, or a nested record pattern with an explicit structure. These check the **actual runtime type of the component**; they do not prove the entire generic type argument of `Box` at runtime.

### Case C — Explicit Type Arguments Cannot Force the Compiler to Trust an Erased Generic Type

The following snippet is a **compile-error example**, not runnable code:

```java
record Box<T>(T value) {}

static void invalid(Object source) {
    // ERROR: Object cannot be safely cast to Box<String>
    // with a check that does not require an unchecked conversion.
    if (source instanceof Box<String>(var s)) {
        System.out.println(s);
    }
}
```

Putting `<String>` in the record pattern does not replace a runtime generic type check. `source` could hold a `Box<Integer>`; the JVM does not retain enough type argument information to distinguish the two `Box` instances via `instanceof`. Java therefore rejects a generic pattern that requires an **unchecked conversion**. The same error occurs with a raw `Box` variable if you try to match it as `Box<String>(...)`.

If `source` has static type `Box<String>`, the pattern `Box<String>(var s)` is valid; if it is only `Object` or raw `Box`, you usually must use `Box(var s)` or check the component (`Box(String s)`) instead of attaching an unverifiable type argument.

### Case D — Generics Inside Generics: Do Not Infer Collection Element Types

Suppose you receive an `Object` holding a `Box<List<String>>`. The pattern `Box(java.util.List<?> values)` can check that the component is a `List` and allow iterating over it as `List<?>`. However, `List<String>` cannot be guaranteed through an erased generic type alone. If you need string elements, check each element individually or preserve the `Box<List<String>>` type in the input signature from the start.

```java
static void inspectList(Object source) {
    if (source instanceof Box(java.util.List<?> items)) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
    }
}
```

This checks `List<?>` and each individual element. The code does not assume every element is a `String` just because one specific instance happens to contain strings.

## 6. Inference, Nulls, and Pattern Variable Scope

Type inference does **not** eliminate the responsibility of handling `null`:

- A `null` input value does not match `Box(...)`, because the outer record object must exist.
- A component inside the record can be `null`. `Box(var x)` uses an unconditional component pattern for the corresponding declared type, so it can still match a record with a `null` component and bind `x = null`.
- With `Object input` and `Box(String s)`, if the component is `null`, `String s` does not match, because `String` does not cover all values of type `Object`.
- When the static type of the component is already `String`, the sub-pattern `String s` can be *unconditional* for the component and match even a `null` component. Therefore, you should not assume that every `String s` in a record pattern excludes `null`; check the static type at the component position.

Example verifying the difference:

```java
Box<String> known = new Box<>(null);
Object unknown = new Box<String>(null);

// true: the String component type is already known from Box<String>.
System.out.println(known instanceof Box<String>(String s));

// false: the component at this position is evaluated from Object; String is a narrower type.
System.out.println(unknown instanceof Box(String s));

// true: var at the component covers the corresponding type, including null.
System.out.println(unknown instanceof Box(var s));
```

Pattern variables can only be used in places where the compiler proves the match succeeded: the `if` body when the condition is true, the corresponding `case` branch, and expressions following pattern-matching scoping rules. Do not use `s` outside that scope or try to assume a runtime type different from the static type assigned by the compiler.

## 7. Common Mistakes

1. **Treating `var` as a dynamic type.** `var` is compile-time type inference. `Object o = new Box<>("abc")` does not give `x` in `Box(var x)` the type `String`.
2. **Confusing type arguments with component patterns.** `Box<String>(var x)` relies on the safety of converting to `Box<String>`; `Box(String x)` can directly check a runtime `String` component from an `Object`.
3. **Using a parameterized record pattern in a context requiring an unchecked cast.** Java forbids, for example, `Object` or raw `Box` with `Box<String>(...)` because the type argument cannot be verified.
4. **Assuming generic inference checks collection elements.** `List<String>` is a static type parameter; to verify each element in untrusted data, check the elements themselves.
5. **Losing type information too early.** Returning `Object` instead of `Box<T>` or `Box<?>` unnecessarily leaves subsequent patterns with less information for inference.
6. **Forgetting the wildcard's upper bound.** With `Box<? extends Number>`, operations based on `Number` are safe; calling `Integer`-specific methods without checking is not guaranteed.
7. **Placing a general branch before specific branches.** In `switch`, `case Box(var any)` should come after `case Box(String s)` and `case Box(Integer n)` so it does not dominate the branches meant for classification.
8. **Confusing generic record patterns with diamond constructors.** `new Box<>("x")` is object creation with diamond inference; `Box(var x)` is matching and deconstructing an object, where inference is constrained by the pattern's target site.

## 8. Pattern Design Checklist

When choosing between inference and explicit types, check:

1. **What is the static type of the selector/expression?** If it is already `Box<String>` or `Box<Box<String>>`, start with `Box(var x)` / `Box(Box(var x))`.
2. **What type does the method need to process?** If it needs `String` but the compiler only knows `Object`, add a `String s` component pattern or an `instanceof String` check.
3. **Is there an unchecked conversion?** Do not add `<String>` to a generic record pattern on an object whose generic type has not been proven by the type system.
4. **Are there wildcards, nulls, or multiple `switch` branches?** Only rely on capabilities guaranteed by the static type, handle `null` at each level, and place specific branches before general ones.
5. **Can generic information be preserved from upstream APIs?** An explicit `Box<T>` signature usually makes downstream pattern code much safer and easier to read than manual casting.

**Conclusion:** With generic record patterns, the compiler typically infers both type arguments and component variables based on the **static type at the match site**. Leverage `var` when type information is sufficient; use explicit component patterns to narrow types at runtime, and only write explicit type arguments when the check remains valid without requiring an unchecked conversion.

### References

- Oracle Java 21 — Record Patterns (Generic Records, Type Inference, Nested Record Patterns): https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- JEP 440 — Record Patterns (final in JDK 21): https://openjdk.org/jeps/440
- Java Language Specification — Record Pattern Type Inference (`18.5.5): https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html
