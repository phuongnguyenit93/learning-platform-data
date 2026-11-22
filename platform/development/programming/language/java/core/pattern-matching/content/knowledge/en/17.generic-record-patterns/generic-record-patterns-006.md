# Limitations Due to Type Erasure in Generic Record Patterns (Java 21+)

## 1. The Problem to Understand

Java allows records to carry type parameters (*generic records*) and allows record components to be destructured using *record patterns*:

~~~java
record Box<T>(T value) {}

Box<String> box = new Box<>("Java");
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

In this example, the compiler knows `box` has type `Box<String>`, so it infers the variable `text` as `String`. However, one must not conclude that the pattern match verified the `String` type argument at runtime.

**Core boundary:** *Type erasure* removes most information about generic type arguments at compile time. A record pattern can use static type information to infer variables and check pattern validity, but at runtime it **cannot verify on its own** whether a `Box<?>` object was actually created as a `Box<String>` or a `Box<Integer>`.

The content below applies to **Java 21 and later** (record patterns were standardized in JEP 440). The runnable program examples use JDK 21+ and do not require `--enable-preview`.

## 2. How Does Type Erasure Affect Generic Records?

Consider the declaration:

~~~java
record Box<T>(T value) {}
~~~

In source code, two variables have different static types:

~~~java
Box<String> names = new Box<>("hello");
Box<Integer> numbers = new Box<>(42);
~~~

The type parameter `T` helps the compiler enforce assignments and the return type of the accessor. However, according to Java's *type erasure* rules:

- Both `Box<String>` and `Box<Integer>` have the exact same runtime class type: `Box`. They do not become two different runtime classes.
- `T` has no explicit bound in `Box<T>`, so upon erasure, positions using `T` are represented by `Object` in the corresponding bytecode signature. If `T extends Number`, the erasure of `T` is based on its leftmost bound, which is `Number`.
- The compiler may insert casts where needed when using the accessor result in a specific context. That does not replace verifying the generic argument at runtime.
- `names.getClass() == numbers.getClass()` is `true`. Calling `getClass()` on an instance does not tell you whether it is a `Box<String>` or a `Box<Integer>`.

The record pattern `Box(var item)` can still check that the object has class `Box` and extract the `value` component. However, it has no runtime check equivalent to "this record's `T` must be `String`".

**Two kinds of checks to distinguish:**

1. **Checking the record class**: is the object an instance of the `Box` class? Record pattern matching can perform this.
2. **Checking the generic type argument**: is this instance truly a `Box<String>` rather than a `Box<Integer>`? Because of erasure, that cannot be fully verified from the object alone at runtime.

You can check the **actual component value** with `instanceof String`, but that result only proves the value itself is a `String`; it does not prove that every aspect of the generic type parameter was preserved.

## 3. When the Static Type Is Known: Allowed Patterns and Inferred Variables

Suppose a method parameter is `Box<String>`:

~~~java
static void printTyped(Box<String> box) {
    if (box instanceof Box<String>(String value)) {
        System.out.println(value.toUpperCase());
    }

    if (box instanceof Box(var value)) {
        System.out.println(value.length());
    }
}
~~~

Both patterns are valid:

- `Box<String>(String value)` explicitly specifies the type argument of the record pattern and the type pattern of the component.
- `Box(var value)` allows both the generic type argument of the record pattern and the type of the variable `value` to be inferred from the input context `Box<String>`.
- In both approaches, `value` is treated as `String` inside the `if` body; calling `toUpperCase()` or `length()` is checked at compile time.

This is **static type inference**, not a runtime check that the object stores a `String` type argument. Java accepts the destructuring as safe on the basis that the program has upheld the `Box<String>` contract.

Similarly, with multiple type parameters:

~~~java
record Pair<A, B>(A first, B second) {}

static void readPair(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var name, var count)) {
        String upper = name.toUpperCase();
        int next = count + 1;
        System.out.println(upper + ": " + next);
    }
}
~~~

The compiler infers `name` as `String` and `count` as `Integer`, then performs unboxing when evaluating `count + 1`. If `count` is `null`, unboxing can throw a `NullPointerException`; matching a record pattern does not automatically guarantee that reference components are non-`null`.

## 4. When Only Object or a Raw Type Is Available: Checked Cast Limitations

A record pattern can carry explicit generic type arguments **only when** the type of the input expression can be converted to the record pattern's type via a **checked cast conversion** (without requiring an *unchecked conversion*).

The following example **does not compile**:

~~~java
record Box<T>(T value) {}

// DOES NOT compile — shown only to illustrate the limitation.
static void invalid(Object input) {
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
~~~

Because `input` only has the static type `Object`, the runtime can determine whether it is a `Box`, but cannot check whether the object is a `Box<String>`. Converting `Object` to `Box<String>` would require checking a generic argument that has been erased, so `instanceof Box<String>(...)` is rejected at compile time.

Similarly, code using a **raw `Box`** also does not compile:

~~~java
// DOES NOT compile — raw Box loses the type parameter.
static void invalidRaw(Box input) {
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
~~~

Do not interpret the error message as if Java saw an `Integer` inside the `Box`. This is a **compile-time** error caused by an unverifiable cast, without needing to run the program or inspect the data inside.

**Subtle point:** Not every use of `Box<String>(...)` is forbidden. It is valid when **the static type of the input** already provides sufficient basis to check the type conversion (such as the `Box<String>` input in Section 3). The governing rule is the *checked cast* requirement, not an absolute ban on generic record patterns.

## 5. Safe Approach for Untyped Data: `Box<?>` and Component Checks

When receiving an `Object` from an API or an external source, you can use the wildcard `?` to check the record class without assuming a generic type argument:

~~~java
static String inspect(Object input) {
    if (input instanceof Box<?>(var content)) {
        if (content instanceof String text) {
            return "String: " + text;
        }
        return "Giá trị khác";
    }
    return "Không phải Box";
}
~~~

The pattern `Box<?>(var content)` is valid for `Object` because `Box<?>` is a type that can be safely checked in this context; `content` is not inferred as `String`. For an unbounded `Box<T>`, `content` can be handled as `Object`. The `content instanceof String text` branch is what performs the **actual runtime check** on the component value's type.

A shorter form:

~~~java
if (input instanceof Box(var content)) {
    // When input only has type Object, do not assume content is String.
    System.out.println(content);
}
~~~

In this case, the record pattern's type can be inferred, but the input lacks sufficient information for `content` to have the static type `String`. Therefore, `content.toUpperCase()` will not compile without an appropriate check/narrowing step.

**Regarding `null`:** a record pattern never matches a `null` reference itself. However, if the `Box` object exists while its `value` component is `null`, the component pattern `var content` can still bind `content == null`. Therefore, you should check for `null` before invoking methods on the component value.

## 6. Nested Generic Record Patterns: Types Propagate, Not Verified at Runtime

Type inference still works across multiple levels when the static type has been properly declared:

~~~java
static void nested(Box<Box<String>> outer) {
    if (outer instanceof Box(Box(var text))) {
        System.out.println(text.toUpperCase());
    }
}
~~~

In this example:

1. The parameter `outer` already has the static type `Box<Box<String>>`.
2. The outer pattern `Box(...)` infers the `value` component to have type `Box<String>`.
3. The inner pattern `Box(var text)` infers `text` to have type `String`.
4. When both record patterns match, `text.toUpperCase()` can be called.

If the inner record component is `null`, the nested `Box(...)` pattern does not match and the `if` branch does not execute. If the `text` component is `null`, the `var text` pattern can still match, but `toUpperCase()` will fail if not checked beforehand.

**The limitation remains intact:** The fact that the compiler knows the type `Box<Box<String>>` does not mean the JVM checked two levels of generics via runtime reflection. If data has been mixed due to raw types or unchecked casts (*heap pollution*), static type assumptions can be violated and cause runtime errors.

## 7. Distinguishing the Generic Argument from the Value Type Inside the Record

The following two cases are often confused:

**Case A — knowing that the current component is a String.**

~~~java
Object unknown = new Box<>("hello");
if (unknown instanceof Box<?>(var item) && item instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
}
~~~

Here `item instanceof String s` directly checks the object held in the component. It is valid even when we do not know the record's generic type parameter.

**Case B — wanting to check that a record is Box<List<String>>.**

~~~java
record Container<T>(T value) {}
Object unknown = new Container<>(java.util.List.of("a", "b"));
~~~

A pattern such as `Container<java.util.List<String>>(var list)` applied directly to `Object` cannot verify `List<String>` at runtime, because the type arguments of both `Container` and `List` have been erased. The safe approach is to check `Container<?>`, then check whether the component is a `List<?>`, and then check each element if the data is required to contain only strings:

~~~java
if (unknown instanceof Container<?>(var value)
        && value instanceof java.util.List<?> list) {
    boolean allStrings = list.stream()
            .allMatch(item -> item instanceof String);
    System.out.println(allStrings); // true
}
~~~

`allStrings` checks the elements **currently present** in the list. It does not turn the list into a `List<String>` at the static type level, does not prove its generic instantiation history, and does not prevent other data from being added later if the structure is still mutable. For an empty list, `allMatch` returns `true` by "all elements satisfy" logic, even though there are no elements to demonstrate the type.

## 8. Complete Runnable Example for Java 21+

Save the following code to **`GenericRecordErasureDemo.java`**:

~~~java
public class GenericRecordErasureDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}

    static String fromTyped(Box<String> box) {
        if (box instanceof Box<String>(var text)) {
            return text.toUpperCase();
        }
        return "Không khớp";
    }

    static String fromUnknown(Object input) {
        if (input instanceof Box<?>(var content)) {
            if (content instanceof String text) {
                return "String: " + text;
            }
            return "Khác: " +
                    (content == null ? "null" : content.getClass().getSimpleName());
        }
        return "Không phải Box";
    }

    static String fromNested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            return "Nested: " + text;
        }
        return "Nested không khớp";
    }

    static String fromPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var name, var count)) {
            return name.toUpperCase() + ": " + (count + 1);
        }
        return "Pair không khớp";
    }

    public static void main(String[] args) {
        System.out.println(fromTyped(new Box<>("java")));
        System.out.println(fromUnknown(new Box<>("hello")));
        System.out.println(fromUnknown(new Box<>(42)));
        System.out.println(fromUnknown(new Box<>(null)));
        System.out.println(fromUnknown("other"));
        System.out.println(fromNested(new Box<>(new Box<>("ok"))));
        System.out.println(fromNested(new Box<>(null)));
        System.out.println(fromPair(new Pair<>("task", 4)));
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac --release 21 GenericRecordErasureDemo.java
java GenericRecordErasureDemo
~~~

Exact output:

~~~text
JAVA
String: hello
Khác: Integer
Khác: null
Không phải Box
Nested: ok
Nested không khớp
TASK: 5
~~~

Explanation:

- `fromTyped`: the static type `Box<String>` allows `Box<String>(var text)`, and the variable `text` has type `String`.
- `fromUnknown`: uses `Box<?>` to match safely, then separately checks `content instanceof String`; `Integer` values, `null`, and non-`Box` inputs are handled separately.
- `fromNested`: infers `String` across two nested record patterns; the inner pattern does not match when the inner record is `null`.
- `fromPair`: simultaneously infers `String` and `Integer` from `Pair<String, Integer>`, allowing appropriate operations to be used.

The same record pattern syntax can be used in `switch`. The rules for *checked casts*, type erasure, and generic type inference still apply; `switch` does not add any ability to recognize erased type arguments.

## 9. Heap Pollution and Limits of Compiler Guarantees

**Heap pollution** occurs when a variable of a parameterized type refers to data that does not actually match that type, typically due to raw types, unchecked casts, or APIs that do not adhere to generics.

The example below is only for risk analysis; **do not run it together with the complete example**:

~~~java
record Box<T>(T value) {}

@SuppressWarnings({"rawtypes", "unchecked"})
static Box<String> unsafeBox() {
    Box raw = new Box(123);
    return raw; // Unchecked conversion: suppressing warnings does not make the data safe.
}
~~~

If the result of `unsafeBox()` is passed into a method expecting `Box<String>` and a record pattern with an inferred `String` variable is used, the program can fail when it needs to treat the `Integer` as a `String`. Matching the `Box` class with a record pattern cannot repair a broken generic contract.

In real-world applications:

- Avoid raw types and unchecked casts at data boundaries.
- Use `Box<?>`/component patterns when the input type is untrusted, combined with runtime checks on individual values.
- If an element type needs to be validated at runtime, you can pass a `Class<T>` as a *type token* for types that can be checked with `Class.isInstance`. However, `Class<List<String>>` does not exist as a class token capable of verifying element type arguments; for nested generics, per-level/per-element validation rules are needed.
- For collections that must maintain a type contract, prefer generic APIs and data validated at insertion time rather than hoping patterns will catch every discrepancy later.

## 10. Decision Table: Which Patterns Are Valid?

In these examples, the record is declared as `record Box<T>(T value) {}`.

| Static type of the expression | Pattern | Compilation result and limitations |
| --- | --- | --- |
| `Box<String>` | `Box<String>(var text)` | Valid; `text` has static type `String`. |
| `Box<String>` | `Box(var text)` | Valid; `text` is inferred as `String`. |
| `Box<?>` | `Box(var item)` | Valid; does not infer `item` as `String` from the wildcard alone. |
| `Object` | `Box<?>(var item)` | Valid; checks the record class and binds the component, without verifying a specific generic argument. |
| `Object` | `Box(var item)` | Valid; lacks sufficient context to directly call `String`-specific methods on `item`. |
| `Object` | `Box<String>(var text)` | **Compile error**: requires an unchecked conversion. |
| Raw `Box` | `Box<String>(var text)` | **Compile error**: loses the basis for checking `String`. |
| `Box<Box<String>>` | `Box(Box(var text))` | Valid; infers `text` as `String` through nested record patterns. |

## 11. Common Misconceptions

**"I wrote `Box<String>(...)`, so Java will verify the `String` type argument at runtime."** Incorrect. This pattern is valid when the checked cast rule permits it based on the static type. Type erasure still applies.

**"Using `var` makes every component have type `Object`."** Incorrect. If the input has type `Box<String>`, `Box(var s)` infers `s` as `String`; if the input is only `Object`, the inferred type is correspondingly less specific.

**"`Box<?>` lets me cast any value to `String`."** Incorrect. The wildcard lets you work safely with an unknown type, but you still need `instanceof String` or explicit validation before using `String` APIs.

**"Nested record patterns verify the entire generic tree at runtime."** Incorrect. They help destructure and infer static information across multiple record layers. Erased generic arguments still cannot be fully verified from an arbitrary object.

**"Suppressing unchecked warnings fixes the bug."** Incorrect. `@SuppressWarnings("unchecked")` only affects compiler warnings; mistyped data can still cause runtime errors.

**"`instanceof List<?>` proves this is a `List<String>`."** Incorrect. It verifies that the object is a `List`, but does not know the generic type of its elements. Checking each element only confirms the state of the observed data.

## 12. Self-Check Questions

1. Why can `Object source` not use `source instanceof Box<String>(var text)`, whereas `source instanceof Box<?>(var text)` is allowed?
2. When the input is `Box<String>`, why does `Box(var text)` infer `text` as `String` yet still not check `String` as a runtime type argument?
3. With `Box<Box<String>>`, what happens if the inner `Box<String>` component is `null`? What if the inner record exists, but its `String` value is `null`?
4. Why does checking every element of a `List<?>` not equate to fully verifying that an object has type `List<String>` at runtime?
5. What should you do when receiving an object of unknown type from an external API and wanting to process a string component safely?

**Suggested answers:** (1) `Box<String>` from `Object` requires an unchecked cast, whereas `Box<?>` can be checked; (2) the static type lets the compiler infer it, while erasure does not store the instance's type argument; (3) the inner pattern does not match if the inner record is `null`, whereas `var text` can bind `null` if the inner record exists; (4) observing elements cannot recover an erased generic type parameter; (5) check `Box<?>` and then `instanceof String` on the component, handling `null` and other data types.

## References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns and generic type inference in Java 21.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): `Box<String>` examples, unchecked conversion errors, `var`, and nested record patterns.
- [JLS 21, `4.6 — Type Erasure`](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-4.html#jls-4.6): generic type erasure rules.
- [JLS 21, `18.5.5 — Record Pattern Type Inference`](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-18.html#jls-18.5.5): inferring generic type arguments in record patterns.
