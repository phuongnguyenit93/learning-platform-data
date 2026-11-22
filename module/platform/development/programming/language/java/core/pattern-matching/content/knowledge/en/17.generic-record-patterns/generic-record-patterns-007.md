# Avoiding raw record patterns

## 1. Why should raw types be avoided when using generic records?

Suppose we declare a record with a type parameter:

```java
record Box<T>(T value) {}
```

`Box<String>` has a `value` component represented as `String` at compile time; `Box<Integer>` has the corresponding component represented as `Integer`. Generics help the compiler catch type-mismatch errors before the program runs.

An older style is to omit type arguments on a variable or at instantiation:

```java
Box raw = new Box("hello"); // raw type: the compiler may warn
```

The variable `raw` has a **raw type** (`Box` instead of `Box<T>`, `Box<String>`, or `Box<?>`). Omitting type information weakens static type checking and can lead to an *unchecked conversion*. In new code, you should avoid declaring variables or APIs with raw types whenever a parameterized type can be used.

However, there is a very common point of confusion in **Java 21**: writing a record pattern `Box(var value)` without `<T>` **does not necessarily create a raw match**. For record patterns of generic records, Java has a **type argument inference** mechanism based on the type of the value being matched. Therefore, it is important to distinguish clearly:

- `Box raw`: declaring a variable with a raw type, losing type information on the variable side.
- `Box(var value)`: record pattern syntax that omits explicit type arguments so the compiler **infers the types** in contexts where inference is possible.
- `Box<?> box`: using a wildcard to state explicitly that we have a `Box` whose type argument `T` is **unknown**; this is how to represent unknown type information without using a raw type.
- `Box<String>(var value)`: a record pattern with an explicit `String` type argument; valid only when the type check conforms to Java's safe casting rules.

This lesson focuses on preserving type information, choosing the right way to write patterns, and avoiding a false sense of safety when data passes through `Object` or a raw type.

## 2. When the input has a clear generic type: let Java infer it

With a method accepting `Box<String>`:

```java
static void printUpper(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Java 21 infers the record pattern `Box(var text)` to correspond to `Box<String>(var text)` in this context. The variable `text` has static type `String`, so calling `text.toUpperCase()` is valid without casting.

We can also write the type argument explicitly if we want to emphasize the data contract:

```java
static void printUpperExplicit(Box<String> box) {
    if (box instanceof Box<String>(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Both approaches express the intent of extracting a `String` from `Box<String>`. Omitting `<String>` in the pattern is **contextual type inference**, not evidence that Java bypasses type safety.

With a record that has two type parameters:

```java
record Pair<K, V>(K key, V value) {}

static void printCount(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var key, var count)) {
        System.out.println(key + ": " + (count + 1));
    }
}
```

The compiler infers `key` as `String` and `count` as `Integer`. The expression `count + 1` uses unboxing from `Integer` to `int`. Note: if `count` is `null`, this unboxing will throw a `NullPointerException`; type inference does not mean a reference value is always non-`null`.

## 3. Do not confuse checking a record with checking type arguments at runtime

Java uses **type erasure** for generics. Therefore, from an `Object` variable, we cannot safely check that an object is a `Box<String>` merely by inspecting the record's type argument at runtime.

An example to avoid:

```java
static void bad(Box raw) {
    // DOES NOT COMPILE:
    // Cannot check Box<String> this way
    // when the input is a raw Box and requires an unchecked conversion.
    if (raw instanceof Box<String>(var text)) {
        System.out.println(text.length());
    }
}
```

This is **intentionally erroneous code for illustration, not a runnable example**. Java does not allow this parameterized record pattern check when it requires an unchecked conversion from raw `Box` to `Box<String>`.

Nor should you write:

```java
Object input = new Box<>("hello");

// Cannot guarantee the type argument with a parameterized instanceof:
// if (input instanceof Box<String> box) { ... } // compile error
```

In situations where the input is `Object`, the safe approach is to match the record, extract the component, and then check the **actual type of the component** if you need to use type-specific APIs:

```java
static void inspect(Object input) {
    if (input instanceof Box(var item)) {
        if (item instanceof String text) {
            System.out.println(text.length());
        } else {
            System.out.println("Không phải chuỗi: " + item);
        }
    }
}
```

Here, `Box(var item)` is inferred from context, but it **does not prove** that the record has type argument `String` at runtime. With an input of static type `Object`, you must not assume `item` is a `String`. Checking `item instanceof String text` is what allows you to use `String`-specific operations in the matched branch.

Key practical takeaway: **preserve generic types at API boundaries when the type is known**, for example accepting `Box<String>` instead of `Object` or raw `Box`. If the data is genuinely heterogeneous, represent that uncertainty with `Box<?>` or check the component before using it.

## 4. When T is unknown: use Box<?> instead of raw Box

When a method needs to accept a `Box` with any type argument, write:

```java
static void processUnknown(Box<?> box) {
    if (box instanceof Box(var item)) {
        System.out.println("Giá trị: " + item);
    }
}
```

`Box<?>` allows passing `Box<String>`, `Box<Integer>`, and other `Box<X>` types. It still makes clear that the `T` information is unknown, so the compiler does not let you assume that `item` is definitely a `String` or an `Integer`.

For instance, if you need to process an integer:

```java
static void processInteger(Box<?> box) {
    if (box instanceof Box(var item)
            && item instanceof Integer number) {
        System.out.println(number + 1);
    }
}
```

Checking `Integer` on the **component** makes the condition explicit. Do not replace it with a blind cast `(Integer) item` when you do not know for sure where the data came from.

Another note: `Box<?>` and `Box<Object>` are **not equivalent**. A `Box<String>` can be referenced as `Box<?>`, but it cannot be automatically assigned to `Box<Object>` because Java generics are *invariant*. Therefore, a wildcard is usually more appropriate when the requirement is "accept a Box of an unknown type".

## 5. Nested generic record patterns can still be inferred

Suppose a `Box` holds another `Box<String>`:

```java
static void nested(Box<Box<String>> outer) {
    if (outer instanceof Box(Box(var text))) {
        System.out.println(text.toUpperCase());
    }
}
```

In the context of `Box<Box<String>>`, Java can infer the outer pattern and the inner pattern along the component chain, so that `text` has type `String`. There is no need to introduce raw types just because records are nested across multiple levels.

Even so, if you receive an `Object` without reliable generic type information, you should not assume a nested pattern will prove type arguments that were erased at runtime. When unsure about the structure or component values, use patterns at an appropriate level to check the actual types before calling type-specific methods.

Record patterns also **do not make null values disappear**. A `null` record value itself does not match a record pattern; a component holding a `null` reference still needs to be accounted for before calling methods or performing unboxing.

## 6. Complete runnable Java 21 program

Create the file **`AvoidRawRecordPatternDemo.java`**:

```java
public class AvoidRawRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<K, V>(K key, V value) {}

    static void printKnown(Box<String> box) {
        if (box instanceof Box(var text)) {
            System.out.println("Known: " + text.toUpperCase());
        }
    }

    static void printAny(Object input) {
        if (input instanceof Box(var item)) {
            if (item instanceof String text) {
                System.out.println("String: " + text);
            } else {
                System.out.println("Other: " + item);
            }
        } else {
            System.out.println("Not a Box");
        }
    }

    static void printWildcard(Box<?> box) {
        if (box instanceof Box(var item)) {
            if (item instanceof Integer number) {
                System.out.println("Integer: " + (number + 1));
            } else {
                System.out.println("Wildcard: " + item);
            }
        }
    }

    static void printPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var key, var count)) {
            System.out.println("Pair: " + key + "=" + (count + 1));
        }
    }

    static void printNested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            System.out.println("Nested: " + text.length());
        }
    }

    public static void main(String[] args) {
        printKnown(new Box<>("java"));
        printAny(new Box<>("hello"));
        printAny(new Box<>(42));
        printAny("nothing");
        printWildcard(new Box<>(41));
        printPair(new Pair<>("items", 4));
        printNested(new Box<>(new Box<>("abcd")));
    }
}
```

Using **JDK 21 or later**, compile and run with:

```bash
javac AvoidRawRecordPatternDemo.java
java AvoidRawRecordPatternDemo
```

Standard output:

```text
Known: JAVA
String: hello
Other: 42
Not a Box
Integer: 42
Pair: items=5
Nested: 4
```

Meaning:

- `printKnown` accepts `Box<String>`, so `Box(var text)` can infer `text` as `String`.
- `printAny` accepts `Object`. It confirms the object is a `Box`, and only then checks whether the component is a `String`; `Box<Integer>` enters the `Other` branch.
- `printWildcard` accepts `Box<?>`, checks the component with `instanceof Integer`, and increments the integer value by one.
- `printPair` leverages `Pair<String, Integer>` information to infer two distinct component types.
- `printNested` leverages the `Box<Box<String>>` type to infer through two record levels and extract the inner `String`.

The methods in this program do not use raw types and do not require unchecked casts. The illustrated branches must be understood according to the **static type of the parameter at the call site**.

## 7. Common mistakes and how to fix them

| Way of writing / thinking | Problem | Better approach |
| --- | --- | --- |
| `Box raw = new Box("x");` | Omits the variable's type argument; prone to raw/unchecked warnings and loses static guarantees. | `Box<String> box = new Box<>("x");` |
| "`Box(var x)` is always raw" | Java 21 has type argument inference for generic record patterns. | Check the static type of the expression being matched. |
| `Box<String> box = raw;` | Assigning from a raw type can produce an unchecked conversion. | Pass parameterized types throughout the API and avoid creating raw types. |
| Inferring `Box<String>` from `Object` because `Box(var x)` matched | Erasure does not guarantee generic type arguments from a runtime object. | Check `x instanceof String s` when you need to use `String`. |
| Using `Box<Object>` to accept any `Box<X>` | Generics are invariant; `Box<String>` is not a subtype of `Box<Object>`. | Use `Box<?>` when the type argument is unknown. |
| Calling `text.length()` when `text` may be `null` | Type inference is static type checking, not null checking. | Check for `null` according to the data contract. |
| Using record patterns in Java 17 without appropriate preview configuration | Record patterns were finalized in Java 21. | Compile this lesson's examples with JDK 21 or later. |

## 8. Self-check

Given:

```java
record Result<T>(T data) {}

Result<String> known = new Result<>("ok");
Result<?> unknown = new Result<>(42);
```

- With `known instanceof Result(var data)`, the compiler has enough context to infer `data` as `String`.
- With `unknown instanceof Result(var data)`, the specific type argument is unknown. You cannot assume `data` has type `Integer` just because the example value is `42`; check the component if you need to handle it as an integer.
- A `Result<String>` type test on an `Object`/raw input cannot be treated as a way to check generic type arguments at runtime; respect the limits of erasure and checked conversions.

**Remember:** To avoid raw record patterns in the spirit of type-safe generics, prioritize **keeping parameterized types on variables and APIs**, use `Box<?>` when the element type is unknown, and take advantage of **record pattern type argument inference in Java 21** when context is available. The syntax `Box(var value)` does not by itself prove generic type arguments at runtime, nor is it by default an unsafe raw operation.
