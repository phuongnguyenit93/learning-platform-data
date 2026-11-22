# Why Can You Not Directly Create `new T[]` in Java Generics?

In Java, you can **declare** an array variable or parameter of type `T[]` in a generic class or method, but you **cannot directly instantiate** it with `new T[n]`:

```java
// Illustrative snippet: lines marked with an error comment do not compile.
class Buffer<T> {
    private T[] data; // Valid: declaring a T[] reference

    Buffer(int capacity) {
        // data = new T[capacity]; // ERROR: generic array creation
    }
}
```

The root cause: **Java arrays store their element type (component type) at runtime and check types on write**, whereas **a generics type variable `T` does not have full type information at runtime (non-reifiable)**. When the compiler performs type erasure, `T` can represent many different concrete types, while `new T[n]` requires creating an array with a real, fixed, checkable component type.

There are several solutions depending on your goal:

- If you only need a collection of generic elements: **prefer `List<T>`**, such as `new ArrayList<T>()`.
- If you must return a **real array with the right runtime component type**: pass `Class<T>` to use `Array.newInstance`, or accept an *array factory* such as `IntFunction<T[]>`.
- If you work with APIs that convert a list into an array: pass a template array or generator, such as `toArray(new String[0])` or `toArray(String[]::new)`.
- Do not treat `(T[]) new Object[n]` as a universal safe solution: that cast **does not create a runtime `String[]` array when `T = String`**.

## 1. Java Arrays Differ from Generics in the Type Information Stored at Runtime

Consider:

```java
String[] names = new String[2];
Object[] objects = names;

objects[0] = "An"; // Valid
// objects[1] = 42; // Compiles, but throws ArrayStoreException at runtime
```

Both `names` and `objects` reference **the same runtime `String[]` array**. Even though the variable `objects` has static type `Object[]`, the JVM still knows that the actual array has component type `String`. Therefore, when writing an `Integer` into that array, the JVM can check and reject it with `ArrayStoreException`.

Contrast this with generics:

```java
// Illustrative snippet, inside a method or class with appropriate imports.
java.util.List<String> text = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

boolean sameClass = text.getClass() == numbers.getClass(); // true
```

Both collections share the same runtime class `ArrayList`; Java does not automatically generate `ArrayList<String>` and `ArrayList<Integer>` as separate classes. Generic type arguments are checked by the compiler in source code, but erased from ordinary descriptors at runtime.

Arrays have **covariance**: `String[]` can be assigned to `Object[]`, while writing the wrong type is checked at runtime. Generic `List<T>` is **invariant**: `List<String>` cannot be assigned directly to `List<Object>`. Java prefers protecting generics with compile-time type rules rather than a separate runtime component type for each `T`.

## 2. Type Variable `T` Is Non-Reifiable: The Root of the Prohibition

Under Java's rules for **reifiable types**, `String`, `Number`, raw `List`, `List<?>`, and arrays with reifiable component types can be fully represented as needed for runtime checks. However, a **type variable** like `T` or `E` is non-reifiable.

```java
class GenericSample<T> {
    T value;   // Valid
    T[] items; // Valid

    void example() {
        // T element = new T();    // Invalid
        // Class<?> kind = T.class; // Invalid
        // items = new T[10];      // Invalid
    }
}
```

The three operations `new T()`, `T.class`, and `new T[10]` involve different restrictions, yet all reflect that the compiler does not know a concrete runtime class sufficient to perform the requested operation.

For example, when using `GenericSample<String>`, a programmer may expect `items` to be `String[]`; when using `GenericSample<Integer>`, they may expect `Integer[]`. If an implementation silently assumed `Object[]` for every `T`, the array would **not have the runtime component type matching what the caller expects**.

### Type Erasure Rules Cannot Save `new T[]`

If `T` has no explicit upper bound, the erasure of `T` is `Object`. If it has `<T extends Number>`, the erasure is `Number`. Even so:

```java
class NumericBuffer<T extends Number> {
    T[] numbers;

    void allocate(int n) {
        // numbers = new T[n]; // Still an invalid generic array creation
    }
}
```

Knowing the `Number` bound does not allow the compiler to assert that the user wants a `Number[]` instead of `Integer[]` or `Double[]`. `T` remains a non-reifiable type variable and does not automatically become a concrete runtime class.

## 3. Why Is `new Object[n]` Cast with `(T[])` Not Equivalent to `new T[n]`?

A common trick is:

```java
// Example that compiles, but is unsafe for an API returning T[].
@SuppressWarnings("unchecked")
static <T> T[] unsafeArray(int size) {
    return (T[]) new Object[size];
}
```

Distinguish two facts:

1. `new Object[size]` **always creates a runtime `Object[]` array**, regardless of the type argument `T` inferred at the call site.
2. The cast `(T[])` inside the generic method may only be checked against the **erasure of `T[]`**, so an `Object[]` array can temporarily pass through the cast here. That does not change the runtime component type into `String` or `Integer`.

Example:

```java
// Illustrative snippet calling the declared unsafeArray method:
try {
    String[] data = unsafeArray(3);
    System.out.println(data.length);
} catch (ClassCastException exception) {
    System.out.println("ClassCastException");
}
```

The caller expects `String[]`; because the actual object is still `Object[]`, the corresponding runtime cast can throw `ClassCastException` **right at the result assignment**. This example proves that casting a reference does not transform the created array object.

**Do not confuse `ClassCastException` with `ArrayStoreException`:** the first occurs when an object cannot be treated as the target type of a cast; the second occurs when attempting to store an incompatible element into an array with a defined runtime component type.

### When Can `Object[]` Be Used as Internal Storage?

When implementing a generic data structure, you can keep `Object[]` **internally** and control read/write operations, instead of exposing it as a `T[]` array with an exact runtime type:

```java
// Class snippet that compiles standalone when placed in an appropriate file.
class ObjectBackedBuffer<T> {
    private final Object[] values;
    private int count;

    ObjectBackedBuffer(int capacity) {
        values = new Object[capacity];
    }

    void add(T value) {
        values[count++] = value; // Needs a capacity check in production code
    }

    @SuppressWarnings("unchecked")
    T get(int index) {
        return (T) values[index];
    }
}
```

Here, reading as `T` relies on the invariant that **only `T` values enter through the type-checked API**, with no raw or unchecked path breaking that constraint. `get` can return the value with a cast tied to the erasure of `T`; at the call site, the compiler can also insert a cast to the concrete type.

This is an internal generic storage pattern, **not a way to create a true `T[]`**. If an API must return an array to the caller, you should not hand out `Object[]` directly via a fake cast posing as `T[]`.

## 4. How to Create an Array with the Right Runtime Type Using `Class<T>` and Reflection

When the caller can supply the runtime class of the component, `Array.newInstance` is the standard approach:

```java
import java.lang.reflect.Array;

static <T> T[] createArray(Class<T> elementType, int size) {
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(elementType, size);
    return result;
}
```

Usage example:

```java
String[] names = createArray(String.class, 3);
Integer[] scores = createArray(Integer.class, 2);
```

Unlike `new Object[n]`, `Array.newInstance(String.class, n)` creates a **real runtime `String[]` array**. The reflective signature returns `Object` and requires a cast, yet the cast is justifiable because the `Class<T>` object itself was used to select the component type when creating the array.

Keep in mind:

- `Class<T>` describes a concrete runtime class, such as `String.class` or `Integer.class`; there is no `List<String>.class` in Java.
- `Array.newInstance` takes a `Class<?>` for the component and a size; `size < 0` throws an array size error such as `NegativeArraySizeException`.
- The generic `createArray` example suits a **reference type `T`** such as `String` or `Integer`. Passing a primitive token like `int.class` through another API can produce `int[]`, which is incompatible with the concept of a reference-typed parameterized generic array `T[]`.
- If you need an array for a nested parameterized type such as `List<String>`, the `List.class` token only selects raw `List` as the runtime component, **and cannot create a separate `List<String>` runtime component type**.

Thus, `Class<T>` solves the need for "the exact runtime class of the element," rather than turning all of Java generics into reified generics.

## 5. Java 17+ Program Comparing Array Creation Approaches

Save the following code verbatim into **`GenericArrayDemo.java`**:

```java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.List;

public class GenericArrayDemo {
    static <T> T[] createArray(Class<T> elementType, int size) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(elementType, size);
        return result;
    }

    static <T> T[] unsafeArray(int size) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) new Object[size];
        return result;
    }

    public static void main(String[] args) {
        String[] names = createArray(String.class, 2);
        names[0] = "An";
        names[1] = "Binh";

        System.out.println("String array: " + Arrays.toString(names));
        System.out.println("Runtime array: "
                + names.getClass().getTypeName());

        Integer[] scores = createArray(Integer.class, 2);
        scores[0] = 10;
        System.out.println("Integer array: "
                + Arrays.toString(scores));

        try {
            String[] wrong = unsafeArray(2);
            System.out.println(wrong.length);
        } catch (ClassCastException exception) {
            System.out.println("Unsafe Object[] cast: ClassCastException");
        }

        Object[] asObjects = names;
        try {
            asObjects[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("Wrong array store: ArrayStoreException");
        }

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(42);

        System.out.println("Wildcard arrays: "
                + Arrays.toString(groups));
        System.out.println("Wildcard component: "
                + groups.getClass().getComponentType().getTypeName());
    }
}
```

Compile and run on JDK 17 or higher:

```bash
javac -encoding UTF-8 -Xlint:unchecked GenericArrayDemo.java
java GenericArrayDemo
```

Standard output:

```text
String array: [An, Binh]
Runtime array: java.lang.String[]
Integer array: [10, null]
Unsafe Object[] cast: ClassCastException
Wrong array store: ArrayStoreException
Wildcard arrays: [[Java], [42]]
Wildcard component: java.util.List
```

Meaning:

1. `createArray(String.class, 2)` creates a runtime `String[]` object matching the caller's variable type.
2. `createArray(Integer.class, 2)` creates `Integer[]`, with the second value defaulting to `null` since it is a new reference array.
3. `unsafeArray(2)` only creates `Object[]`. When the caller expects `String[]`, the cast at the call site throws `ClassCastException`.
4. The same `String[]` can be viewed through `Object[]`, yet the JVM blocks writing an `Integer` with `ArrayStoreException`.
5. `new List<?>[2]` is valid because the component type `List<?>` is **reifiable**; the array has runtime component class `java.util.List` and does not retain `String` or `Integer` for each sub-list.

Intentionally invalid lines such as `new T[n]` appear only in commented snippets, **not** as executable code in this program.

## 6. Why Is `new List<?>[n]` Allowed While `new List<String>[n]` Is Forbidden?

Java's array creation rule requires the **component type** in `new ElementType[n]` to be reifiable.

```java
// Valid:
java.util.List<?>[] unknownLists = new java.util.List<?>[3];

// Does not compile:
// java.util.List<String>[] names = new java.util.List<String>[3];
```

Although both `List<?>` and `List<String>` use the runtime interface `List`, these two types express different constraints:

- `List<?>` does not say that the elements of the sub-lists have a specific type. The runtime only needs to check that each value placed into the array is a `List`.
- `List<String>` constrains the element type to `String`, which the runtime `List` cannot directly verify for each object. Allowing `List<String>[]` creation would therefore create an illusion that the JVM will block any attempt to insert a wrongly typed list.

Counterexample simulating what would happen if a `List<String>[]` existed via an unsafe operation:

```java
// Intentionally unsafe snippet, for explanation only.
java.util.List<?>[] rawArray = new java.util.List<?>[1];
Object[] objects = rawArray;
objects[0] = java.util.List.of(42); // Allowed at runtime: this is a List

// No guarantee that every element in the List is a String.
```

The `List<Integer>` object here is still a valid `List` with respect to the array's runtime component type. There is no generic element type check comparable to `String[]` rejecting a direct `Integer` write.

**Remember:** `List<?>[]` is not `List<Object>[]`; the wildcard holds elements of an unknown type, whereas `List<Object>` is a concrete parameterized type and is not automatically inferred from `List<String>`.

## 7. Why Is Declaring `T[]` Valid While Instantiating with `new T[n]` Is Not?

Distinguish between:

```java
class Holder<T> {
    private T[] values; // Valid

    Holder(T[] values) { // Valid
        this.values = values;
    }

    T[] getValues() { // Valid
        return values;
    }
}
```

This code **does not create a new array**. It merely receives an existing `T[]` reference. For instance, the caller creates `String[]` externally and passes it in:

```java
Holder<String> h = new Holder<>(new String[] { "An", "Binh" });
String[] data = h.getValues();
```

At runtime, the original array object is genuinely `String[]`, so returning it from the generic method matches the caller's `String[]` reference.

By contrast, `new T[n]` forces the compiler to **choose a runtime component type itself**, without having a concrete type token to choose from. That is what is forbidden.

A generic class that needs an array can accept the array via its constructor, or accept `Class<T>` / a factory to allocate an array of the right type itself.

### Designing a Class That Accepts `Class<T>`

```java
// Java 17+ illustrative snippet; requires importing java.lang.reflect.Array.
class TypedBuffer<T> {
    private final T[] data;

    @SuppressWarnings("unchecked")
    TypedBuffer(Class<T> elementType, int size) {
        data = (T[]) java.lang.reflect.Array.newInstance(elementType, size);
    }

    void set(int index, T value) {
        data[index] = value;
    }

    T[] toArray() {
        return data.clone();
    }
}
```

Caller:

```java
TypedBuffer<String> buffer = new TypedBuffer<>(String.class, 2);
buffer.set(0, "An");
String[] copy = buffer.toArray();
```

Here, `toArray()` returns a clone with the same runtime component type as the original array, namely `String[]`. `clone()` performs a **shallow copy**: for mutable elements, the element objects themselves are not automatically cloned.

The `set` method in the example uses a Java array for storage: in a real library, you should add index checks, capacity checks, and other domain constraints.

## 8. Using `IntFunction<T[]>` to Let the Caller Choose Array Creation

Another approach is to ask the caller to supply an **array factory**:

```java
// Snippet inside an appropriate class/method:
static <T> T[] allocate(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}
```

At the call site:

```java
String[] names = allocate(2, String[]::new);
Integer[] numbers = allocate(3, Integer[]::new);
```

The method reference expression `String[]::new` places array creation where the component type `String` is already known. The generic method receives the factory and invokes it; it **does not have to write `new T[n]` itself**.

This approach is useful when writing generic APIs that avoid reflection, or when a collection/processing pipeline accepts a generator capable of producing an array of the right type.

Note that the caller is responsible for providing a compatible factory; if raw/unchecked casts are used to pass the wrong factory, type-safety risks can still arise.

## 9. Converting a Collection to an Array: Avoiding Creating `T[]` Yourself

Many Java APIs already provide mechanisms for the caller to determine the runtime component type.

Example:

```java
java.util.List<String> list = java.util.List.of("An", "Binh");

String[] first = list.toArray(new String[0]);
String[] second = list.toArray(String[]::new);
```

Both produce a `String[]` result. The `String[0]` array acts as a template conveying the component type; the API can allocate an appropriately sized array according to the `toArray(T[])` contract. With `toArray(IntFunction<T[]>)`, the generator `String[]::new` creates an array with the right runtime component type.

If you simply call `list.toArray()` **with no arguments**, the return type is `Object[]`, which cannot be assumed to be `String[]`:

```java
Object[] values = list.toArray(); // Valid
// String[] wrong = (String[]) list.toArray(); // May throw ClassCastException
```

This approach clarifies responsibilities: the generic library handles the elements, while the caller supplies type information to construct the proper runtime array.

## 10. Why Is `List<T>` Often Simpler Than `T[]`?

If the goal is simply to store a number of elements of type `T`, use a standard generic collection:

```java
import java.util.ArrayList;
import java.util.List;

class DynamicBuffer<T> {
    private final List<T> elements = new ArrayList<>();

    void add(T value) {
        elements.add(value);
    }

    T get(int index) {
        return elements.get(index);
    }
}
```

When using `DynamicBuffer<String>`, the compiler checks `add(String)` in source code, and no runtime `String[]` array needs to be constructed. `ArrayList` can manage its internal storage with an array structure suited to its implementation, while the public API keeps type `List<T>`.

This is usually the better choice because:

- It does not require `Class<T>` or a factory just to store elements.
- It resizes easily; arrays have a fixed length.
- `List<T>` methods provide add/remove/access operations checked at the source level via generics.
- It reduces the need to cast `Object[]` to `T[]` to return results to callers.

Choose `T[]` when you need to interoperate with array-based APIs, leverage array structure, or have a specific requirement for a runtime component type. You should not default to arrays just because you are used to `new int[n]` in non-generic algorithms.

### Primitive Arrays Are a Separate Case

`int[]` and `double[]` are runtime arrays with explicit primitive components. Standard Java generics do not support `List<int>` or `T = int` as ordinary generic type arguments; collections require `List<Integer>` with boxing/unboxing. When `int[]` is needed for representation efficiency, design for it explicitly rather than expecting `new T[]` in generics to create a primitive array automatically.

## 11. Generic Varargs: `T...` Allowed Yet `new T[]` Forbidden?

Java allows declaring generic varargs methods:

```java
@SafeVarargs
static <T> int count(T... values) {
    return values.length;
}
```

When invoking varargs, the compiler constructs an array for the arguments at the call site. When the element type is **non-reifiable**, the compiler may create the array based on erasure and emit an **unchecked/generic array creation warning**, because the runtime component type cannot fully represent the type argument.

Therefore, **allowing `T...` in a declaration does not mean you can write `new T[10]` inside the method body**. Varargs is a method invocation syntax with its own compilation rules, and it also carries heap pollution risks if code exposes or writes wrongly typed data into the varargs array.

`@SafeVarargs` is a promise by the method author that the body **performs no unsafe operations** on the varargs array. The annotation is allowed on constructors and eligible methods—such as `static`, `final`, or `private` depending on the Java version. It does **not** make `T` reifiable, nor is it a tool to silence warnings when code still corrupts data.

An example eligible for `@SafeVarargs` is one that merely counts elements as above; for methods that store the array into a shared field, expose it externally, or write wrong types through an alias, evaluate very carefully before promising `@SafeVarargs`.

## 12. Array Covariance and Heap Pollution: Why This Safeguard Matters

Suppose Java allowed creating arrays with non-reifiable generic component types and people mistakenly assumed it would block invalidly typed data:

```java
// Snippet illustrating operations on List<?>[] which is itself valid.
java.util.List<?>[] lists = new java.util.List<?>[1];
Object[] objects = lists;
objects[0] = java.util.List.of(42); // Valid: still a List
```

The runtime array only checks whether the written element is a `List`; it cannot check whether each list holds `Integer` or `String`.

If other code, via an unchecked cast or raw type, assumes this array is `List<String>[]`, a list element containing `Integer` could later be read under the assumption of `String`, leading to a cast failure. The state where a variable declared with a parameterized generic type does not match its actual data is called **heap pollution**.

This is why Java strictly separates arrays and generics:

- Arrays have **runtime component type** checks and covariance.
- Generics are checked primarily at **compile time**, use erasure, and are generally invariant.
- An array whose component type is a non-reifiable generic type would create a boundary where type safety is hard to uphold.

Consequently, expressions like `new List<String>[n]` and `new T[n]` are forbidden, whereas declaring references to such array types can still be valid in appropriate contexts.

## 13. Common Mistakes and How to Fix Them

**Mistake 1 — "`T` is replaced with `String` at the call site, so `new T[n]` should work."** False. Ordinary Java Generics type arguments do not generate class specializations for each type binding. The compiler does not have a single runtime component class for this expression.

**Mistake 2 — "Using `(T[]) new Object[n]` produces a real `T[]` array."** False. The actual object remains `Object[]`; a caller expecting `String[]` can encounter `ClassCastException`.

**Mistake 3 — "`T extends Number` allows `new T[n]`."** False. `T` remains non-reifiable even though its erasure may be `Number`.

**Mistake 4 — "If you cannot create `T[]`, you cannot declare a `T[]` field either."** False. Declaring, accepting, and returning `T[]` references is allowed; what is restricted is an array creation expression with a non-reifiable component type.

**Mistake 5 — "`new List<?>[n]` is also forbidden because it has `<...>`."** False. `List<?>` is reifiable, so creating an array with this component type is permitted. `List<String>`, however, is non-reifiable.

**Mistake 6 — "Reflection is unsafe because it always returns `Object[]`."** False. `Array.newInstance(String.class, n)` genuinely creates `String[]`; the reflective method's generic return type is `Object`, but the array's runtime class matches the component type token.

**Mistake 7 — "`List<T>` is an array in disguise, so it also needs `new T[n]`."** False. Generic collections expose a generic API; their internal storage mechanism does not force the public API to return a runtime `T[]` array.

**Mistake 8 — "`@SuppressWarnings("unchecked")` makes casting `Object[]` to `T[]` safe."** False. The annotation only hides the compiler warning; it does not alter the runtime component class.

**Mistake 9 — "`@SafeVarargs` allows creating any generic array without risk."** False. It denotes a commitment to safe operations on the varargs parameter; it does not turn a non-reifiable type into a reifiable one.

**Mistake 10 — "If casting `Object[]` to `String[]` fails, then all array casts are wrong."** False. Casting to an array type that matches the object's runtime component type is normal; the issue lies in what type the underlying array object was actually created with.

## 14. Self-Check Exercises

**Question 1.** In `class Box<T>`, is `T[] array;` valid?

Yes. Declaring a reference variable to a `T[]` array does not require creating a new array.

**Question 2.** Why is `array = new T[10];` invalid?

Because `T` is a non-reifiable type variable, whereas an array creation expression requires a representable and checkable runtime component type.

**Question 3.** What is the runtime class of `String[] result = createArray(String.class, 5)`?

It is `String[]`, because `Array.newInstance` creates the array directly from `String.class`.

**Question 4.** Is `<T> T[] f() { return (T[]) new Object[3]; }` guaranteed to be safe when the caller needs `String[]`?

No. The runtime array is still `Object[]`, and the cast at the caller can throw `ClassCastException`.

**Question 5.** How do `new List<?>[2]` and `new List<String>[2]` differ?

The first is valid because `List<?>` is reifiable; the second is forbidden because `List<String>` is non-reifiable.

**Question 6.** When should `List<T>` be preferred?

When you primarily need a collection of generic elements, do not need a runtime array with a specific component type, and want to avoid array casts that are hard to prove safe.

**Question 7.** What error does `String[] data = {"A"}; Object[] objects = data; objects[0] = 42;` cause?

`ArrayStoreException`, because the actual array has component type `String`. This differs from the `ClassCastException` that can occur when trying to treat an `Object[]` as `String[]`.

**Question 8.** Is `List<String> names = List.of("A"); String[] values = names.toArray(String[]::new);` valid?

Yes. The caller provides the generator `String[]::new`, enabling the API to create a runtime array with the right component type.

## 15. Summary by Design Decision

| Requirement | Recommended Approach | What to Avoid |
| --- | --- | --- |
| Store multiple generic values with flexible add/remove | `List<T>` / `ArrayList<T>` | Creating `T[]` unnecessarily |
| Fixed-length internal storage | `Object[]` inside an encapsulated data structure upholding invariants | Exposing `Object[]` under a runtime `T[]` promise |
| Return an array with the exact element class | `Class<T>` + `Array.newInstance` | `(T[]) new Object[n]` when the caller may expect `String[]` |
| Caller already knows the element type | `IntFunction<T[]>`, e.g., `String[]::new` | Assuming the compiler recovers `T` at runtime |
| Convert `List<String>` to an array | `toArray(new String[0])` or `toArray(String[]::new)` | Casting `Object[]` returned by `toArray()` to `String[]` |
| Need lists of multiple unknown types | `List<?>` or `List<?>[]` when an array is genuinely needed | Trusting `List<?>[]` to verify the contents of every `List<String>` |

**Conclusion:** Java forbids direct `new T[]` not because generics cannot be placed into arrays, but because **the type variable `T` is non-reifiable while arrays must know their component type at runtime**. An `Object[]` cast to `T[]` does not magically become `String[]` or `Integer[]`, risking runtime errors. When you need a properly typed array, pass `Class<T>` or an array factory; when you only need a generic storage structure, `List<T>` is usually simpler and less risky.