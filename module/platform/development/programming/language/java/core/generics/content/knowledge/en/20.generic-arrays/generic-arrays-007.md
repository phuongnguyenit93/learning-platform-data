# Creating Generic Arrays Using `IntFunction<T[]>` or `Class<T>` Information in Java

## Learning Objectives

Java allows a generic method to work with elements of type `T`, yet does not allow directly writing `new T[n]`. This is not a mere syntax limitation: the JVM needs to know **the actual element type of the array at runtime** to check write operations, whereas generic `T` undergoes *type erasure* and usually has no dedicated class token.

There are two common ways to create the exact right array type while keeping the API generic:

1. **Accept `IntFunction<T[]>`** — the caller supplies an array-creation function such as `String[]::new`. This approach is the natural choice since the Java API already uses `Collection.toArray(IntFunction<T[]>)` or when the caller knows how to allocate the desired array type.
2. **Accept `Class<T>`** — the caller supplies `String.class` or `Integer.class`, and the method uses `java.lang.reflect.Array.newInstance(componentType, n)` to create an array with the right runtime component type.

After this lesson, you will:

- Be able to explain why `new T[n]` and `new List<String>[n]` are rejected by the compiler.
- Write, call, and test two `<T> T[]` array-creation APIs using a factory and a class token.
- Understand the differences among **runtime component type**, **compile-time type inference**, and **generic metadata**.
- Use `Collection.toArray(IntFunction<T[]>)`, `Collection.toArray(T[])`, and `Array.newInstance` for their intended purposes.
- Avoid mistakes such as casting `Object[]` to `String[]`, referencing nonexistent `List<String>.class`, or overlooking risks when the caller supplies an unsuitable factory.

## 1. Foundational Condition: `new T[n]` Is Forbidden

```java
static <T> T[] wrong(int length) {
    // return new T[length]; // generic array creation
    return null; // Only helps the snippet compile for illustration.
}
```

The type variable `T` has no concrete runtime component class; the erasure of `T` (typically `Object`) does not mean the caller expects `Object[]`. The JVM needs the real component type to check `array[i] = value`; `Object[]` is not `String[]`, even when currently holding only strings.

This lesson focuses on **two ways to create the right runtime component type**: accepting an `IntFunction<T[]>` provided by the caller, or accepting `Class<T>` and using `Array.newInstance`. Erasure, array covariance, and generic array creation have been demonstrated separately; what matters here is the factory/token contract and how to verify the allocation result.

## 2. Comparing the Two Main Strategies

| Criterion | `IntFunction<T[]>` | `Class<T>` combined with `Array.newInstance` |
| --- | --- | --- |
| Information provided by caller | A function taking length and returning an array, e.g., `String[]::new`. | An element type token, e.g., `String.class`. |
| How allocation occurs | Calls `factory.apply(n)`. | Calls `Array.newInstance(componentType, n)`. |
| Knows real component type at runtime? | Yes, from the array created by the factory. | Yes, from `Class<T>` passed to reflection. |
| Needs an unchecked cast inside the helper? | No, when simply calling the factory and receiving `T[]`. | Requires casting reflection's `Object` return to `T[]`; should be isolated in one place. |
| Best suited for | Caller-side lambda/constructor reference APIs, collection utilities. | Reflection, frameworks, APIs already passing `Class<T>`, creating arrays when only an element type token is available. |
| Supports arrays of `List<String>` as a reifiable component? | Cannot create `new List<String>[n]` directly; can only use arrays whose runtime component is `List`. | `List<String>.class` does not exist; `List.class` does not retain the `String` argument. |
| Main risks | Factory returns `null`, unexpected length, or an array with an incompatible runtime component. | Wrong token passed, missing null check, primitive types, and unchecked casts outside a safe scope. |

**Principle:** Choose a point where **actual type information is explicitly supplied by the caller**. Do not create `Object[]` and expect the compiler/JVM to turn it into an array of `T` via a generic cast.

## 3. Approach 1: `IntFunction<T[]>` and Constructor References

`java.util.function.IntFunction<R>` is a functional interface with the method:

```java
R apply(int value);
```

With `IntFunction<T[]>`, `R` is specialized to `T[]`: the function takes an integer and returns a suitable array.

Example:

```java
java.util.function.IntFunction<String[]> maker = String[]::new;
String[] result = maker.apply(3);
result[0] = "An";
```

`String[]::new` is an *array constructor reference*: when called with `3`, it creates `new String[3]`. It does not use `new T[3]`; the caller has already established `String` as the runtime component.

### 3.1. Array Allocation Helper

Placed inside a class:

```java
static <T> T[] allocateWithFactory(
        int length, java.util.function.IntFunction<T[]> factory) {
    if (length < 0) {
        throw new IllegalArgumentException("negative length");
    }
    T[] array = java.util.Objects.requireNonNull(
            factory.apply(length), "array");
    if (array.length != length) {
        throw new IllegalArgumentException("unexpected array length");
    }
    return array;
}
```

This is a standalone illustrative method; the complete runnable program in Section 7 includes this exact implementation.

Usage:

```java
String[] names = allocateWithFactory(3, String[]::new);
Integer[] scores = allocateWithFactory(2, Integer[]::new);
```

The compiler infers `T` from both the result type and the array constructor reference. There is no unchecked cast here: the factory returns `T[]` directly under its generic contract.

The condition `array.length == length` is a design choice of **this helper**, not a default requirement of every API accepting `IntFunction<T[]>`. It detects factories that fail to uphold the allocation contract expected by the helper. If different lengths should be allowed, adjust the contract and handling explicitly.

### 3.2. Why Is a Constructor Reference Better Than a Lambda in Simple Cases?

The following two expressions are equivalent in purpose:

```java
java.util.function.IntFunction<String[]> a = size -> new String[size];
java.util.function.IntFunction<String[]> b = String[]::new;
```

A constructor reference is usually concise, directly states the array type to allocate, and avoids repeating the parameter name. A lambda remains useful if you need size checks, logging, caching, or a custom allocation strategy.

**Do not confuse `String::new` with `String[]::new`**: the former is a constructor for a single `String` object; the latter is a constructor reference for a `String` array.

## 4. Approach 2: `Class<T>` and `Array.newInstance`

When the caller already has a `Class<T>` token, such as `String.class`, reflection can be used:

```java
java.lang.reflect.Array.newInstance(String.class, 3);
```

The method `Array.newInstance(Class<?> componentType, int length)` takes an element type and length and returns an array object with **the exact runtime component type specified by the token**. Its return type is declared as `Object`, because the reflection API also supports primitive arrays and multidimensional arrays.

To provide a generic API returning `T[]`, you can write:

```java
@SuppressWarnings("unchecked")
static <T> T[] allocateWithClass(Class<T> componentType, int length) {
    java.util.Objects.requireNonNull(componentType, "componentType");
    if (componentType.isPrimitive()) {
        throw new IllegalArgumentException("reference components only");
    }
    return (T[]) java.lang.reflect.Array.newInstance(componentType, length);
}
```

Example:

```java
String[] names = allocateWithClass(String.class, 4);
Number[] numbers = allocateWithClass(Number.class, 2);
Integer[] scores = allocateWithClass(Integer.class, 3);
```

In these cases, the created real arrays carry runtime component types `String`, `Number`, and `Integer` respectively. `@SuppressWarnings("unchecked")` is placed **right on the method** containing the cast, rather than spreading across the entire application. Safety rests on this reasoning: the `Class<T>` token specifies the component type that `Array.newInstance` uses to create the array; hence the result is an array of `T` for **reference component types**.

### 4.1. Why Must `isPrimitive()` Be Considered?

Reflection can create primitive arrays:

```java
int[] rawPrimitives =
        (int[]) java.lang.reflect.Array.newInstance(int.class, 2);
```

However, an `int[]` is **not** an `Integer[]` or `Object[]`. A generic array `T[]` in ordinary helpers is used as a reference array, so the wrapper above intentionally rejects `componentType.isPrimitive()` to keep the contract unambiguous.

A subtle detail: in Java expressions, `int.class` has a static type corresponding to `Class<Integer>`, yet the token object itself **describes primitive `int`**, not the `Integer` wrapper. Therefore:

- `Integer.class` creates component type `Integer`.
- `int.class` creates component type `int` when passed directly to `Array.newInstance`.
- Do not treat autoboxing as a mechanism that automatically converts `int[]` to `Integer[]`; autoboxing applies to value expressions, not transforming between those two array kinds.

If an API genuinely needs primitive arrays, provide an explicit API returning `Object` or a specific primitive array type, instead of forcing them into `<T> T[]`.

### 4.2. Checking the Component Type at Runtime

An array can report its own element type:

```java
String[] names = allocateWithClass(String.class, 2);
System.out.println(
        names.getClass().getComponentType().getSimpleName());
```

Output:

```text
String
```

This information comes from the real array object, not just from the `T` symbol in source code. That also explains why array store checks can reject objects of the wrong type immediately on write.

## 5. Most Common Case: `Collection.toArray`

If you already have a `Collection<T>` or `List<T>` and need to convert it to an array, **you usually do not need to write your own array-creation helper**: the Java Collections Framework already provides supporting APIs.

### 5.1. `toArray(T[] a)`

Example:

```java
java.util.List<String> values = java.util.List.of("A", "B");
String[] array = values.toArray(new String[0]);
```

`toArray(T[] a)` uses the runtime component of the passed array to create the result array whenever the input array lacks capacity. If `a` has enough space, the result may be `a` itself; when there is extra room, the slot immediately following the last element is set to `null` per the API contract.

You can pass an exact-sized array:

```java
String[] exact = values.toArray(new String[values.size()]);
```

Do not claim that passing an exact-length array is always faster than passing a zero-length array: cost and optimizations depend on the JDK, collection type, and measurement environment. Choose readability first and benchmark when performance truly matters.

### 5.2. `toArray(IntFunction<T[]> generator)`

Since Java 11, `Collection` has a convenient overload:

```java
String[] array = java.util.List.of("A", "B").toArray(String[]::new);
```

This form is concise, directly states the component type, and is usually the best option when you already have a `Collection`.

**An important point about the argument passed to the factory:** the default implementation of `Collection.toArray(IntFunction<T[]>)` invokes `generator.apply(0)` and passes the resulting array to `toArray(T[])`. Therefore, never write a generator assuming the parameter always equals `collection.size()`. In the verified program in Section 7, the factory genuinely receives `0`, yet the result still contains both elements.

The difference:

```java
// Custom helper: explicitly invokes the factory with the requested length.
T[] array = factory.apply(length);

// Collection.toArray(IntFunction): default implementation calls the generator with 0.
// The Collection then creates/populates the result array of the right size.
String[] names = List.of("A", "B").toArray(String[]::new);
```

The line using `T` at the top is a **description in a generic context**, not a standalone program. When designing a callback of type `IntFunction<T[]>`, read the contract of the **API invoking the callback**, rather than inferring the meaning of the integer solely from the interface name.

### 5.3. Copying from `Collection<? extends T>` into an Array of `T`

If the source is `Collection<Integer>` and the desired target is `Number[]`, a factory can be used:

```java
static <T> T[] copyToArray(
        java.util.Collection<? extends T> source,
        java.util.function.IntFunction<T[]> factory) {
    return source.toArray(factory.apply(0));
}
```

Caller:

```java
Number[] values = copyToArray(
        java.util.List.of(2, 5), Number[]::new);
```

The method creates an array with runtime component type `Number`, placing `Integer` elements into it validly since `Integer` is a subtype of `Number`. Widening to `Number[]` here is intentional; it differs from casting an `Object[]` to `String[]` without proof.

If the API does not need a custom helper, calling `Collection.toArray(Number[]::new)` directly serves the same purpose.

## 6. Using `Class<T>` to Copy a Collection

You can combine two steps: allocate the array via a class token and populate elements from the collection.

```java
static <T> T[] copyWithClass(
        java.util.Collection<? extends T> source,
        Class<T> componentType) {
    T[] target = allocateWithClass(componentType, source.size());
    return source.toArray(target);
}
```

This method belongs to the same class containing `allocateWithClass` in Section 4, and has a full runnable version in Section 7.

Example:

```java
Number[] result = copyWithClass(
        java.util.List.of(3, 4), Number.class);
```

When the source contains an element incompatible with the array's true component type, `Collection.toArray` can throw `ArrayStoreException`. In a program using only safe generics and passing matching tokens, the compiler normally prevents incompatible calls. Yet if data has been polluted by raw types, unchecked casts, or untrusted sources, the runtime array store check remains a line of defense.

**Distinguish carefully:** `Class<T>` describes a runtime component type usable as an array, not deeply nested generic arguments like `List<String>`. Calling `copyWithClass(..., List.class)` only describes an array of `List`s, without checking whether each `List` contains `String`.

## 7. Complete Java 17 Program

**File `GenericArrayFactoriesDemo.java`:**

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntFunction;

public class GenericArrayFactoriesDemo {
    static <T> T[] allocateWithFactory(int length, IntFunction<T[]> factory) {
        if (length < 0) throw new IllegalArgumentException("negative length");
        T[] array = Objects.requireNonNull(factory.apply(length), "array");
        if (array.length != length) {
            throw new IllegalArgumentException("unexpected array length");
        }
        return array;
    }

    @SuppressWarnings("unchecked")
    static <T> T[] allocateWithClass(Class<T> componentType, int length) {
        Objects.requireNonNull(componentType, "componentType");
        if (componentType.isPrimitive()) {
            throw new IllegalArgumentException("reference components only");
        }
        return (T[]) Array.newInstance(componentType, length);
    }

    static <T> T[] copyToArray(
            Collection<? extends T> source, IntFunction<T[]> factory) {
        return source.toArray(factory.apply(0));
    }

    static <T> T[] copyWithClass(
            Collection<? extends T> source, Class<T> componentType) {
        T[] target = allocateWithClass(componentType, source.size());
        return source.toArray(target);
    }

    static <T> List<T> newList() {
        return new ArrayList<>();
    }

    public static void main(String[] args) {
        String[] slots = allocateWithFactory(3, String[]::new);
        slots[0] = "A";
        System.out.println("factory=" + Arrays.toString(slots));
        System.out.println("factoryComponent="
                + slots.getClass().getComponentType().getSimpleName());

        Integer[] scores = allocateWithClass(Integer.class, 2);
        scores[0] = 7;
        System.out.println("class=" + Arrays.toString(scores));
        System.out.println("classComponent="
                + scores.getClass().getComponentType().getSimpleName());

        Number[] wider = copyToArray(List.of(2, 5), Number[]::new);
        System.out.println("copiedNumbers=" + Arrays.toString(wider));

        String[] names = List.of("An", "Binh").toArray(String[]::new);
        System.out.println("library=" + Arrays.toString(names));

        AtomicInteger requestedLength = new AtomicInteger(-1);
        String[] viaCollection = List.of("X", "Y").toArray(length -> {
            requestedLength.set(length);
            return new String[length];
        });
        System.out.println("collectionResult=" + Arrays.toString(viaCollection));
        System.out.println("generatorRequested=" + requestedLength.get());

        Number[] fromClass = copyWithClass(List.of(3, 4), Number.class);
        System.out.println("copyClass=" + Arrays.toString(fromClass));

        try {
            String[] words = allocateWithFactory(2, String[]::new);
            Object[] alias = words;
            alias[0] = 99;
        } catch (ArrayStoreException error) {
            System.out.println("storeCheck=" + error.getClass().getSimpleName());
        }

        try {
            allocateWithClass(int.class, 2);
        } catch (IllegalArgumentException error) {
            System.out.println("primitiveGuard=" + error.getMessage());
        }

        List<?>[] lists = new List<?>[2];
        lists[0] = List.of("one");
        lists[1] = List.of(10);
        System.out.println("wildcardArray=" + lists[0] + "|" + lists[1]);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 -Xlint:all GenericArrayFactoriesDemo.java
java GenericArrayFactoriesDemo
```

**Verified stdout:**

```text
factory=[A, null, null]
factoryComponent=String
class=[7, null]
classComponent=Integer
copiedNumbers=[2, 5]
library=[An, Binh]
collectionResult=[X, Y]
generatorRequested=0
copyClass=[3, 4]
storeCheck=ArrayStoreException
primitiveGuard=reference components only
wildcardArray=[one]|[10]
```

The program compiled with `--release 17 -Xlint:all` and ran successfully in testing. Important details:

- `slots` is genuinely `String[]` with three slots; unassigned slots default to `null`.
- `scores` is genuinely `Integer[]` created via reflection, not `int[]`.
- `copyToArray` uses a `Number[]` factory to accept `Integer` elements via subtyping.
- `Collection.toArray(String[]::new)` directly returns `String[]`.
- In the tested `List.of(...).toArray(generator)` implementation, the generator was invoked with `0`; the `Collection` still produced a result of the right length afterward.
- `alias[0] = 99` proves the `String[]` array is still checked by the JVM against its true component type at runtime.
- The `Class<T>`-based helper rejects primitive tokens per its designed contract.
- `List<?>[]` is valid, yet carries no commitment that all inner `List`s share the same generic argument.

## 8. Related Compile-Time Errors to Recognize

**File `InvalidArrayCreation.java` — intentionally fails compilation:**

```java
import java.util.List;

class InvalidArrayCreation {
    static <T> T[] make(int length) {
        return new T[length];
    }

    List<String>[] lists = new List<String>[2];
}
```

Command:

```bash
javac --release 17 InvalidArrayCreation.java
```

The compiler rejects both expressions with the core error:

```text
error: generic array creation
```

The two cases have related roots yet differ:

1. `new T[length]`: `T` is a type variable, with no independent runtime class to create an array.
2. `new List<String>[2]`: element type `List<String>` is not *reifiable*, because the JVM has no runtime component distinguishing the `String` generic parameter.

Meanwhile:

```java
String[] strings = new String[2];    // Valid.
List<?>[] lists = new List<?>[2];    // Valid.
List[] rawLists = new List[2];       // Valid, yet uses a raw type.
```

This snippet illustrates declarations in a scope importing `List`. `List<?>` is reifiable under Java's rules because every argument is an unbounded wildcard. However, `List<?>[]` has runtime component `List`, and **cannot** check the element type parameter inside each `List`.

### Can `List<String>.class` Help?

No. The expression:

```java
// Invalid:
// Class<List<String>> token = List<String>.class;
```

does not exist in Java's class literal syntax. `List.class` can create an array of `List` at the raw runtime level, yet cannot turn it into an array with a reifiable `List<String>` component type.

If the problem needs to store **multiple `List<String>`s**, you can usually use `List<List<String>>` to avoid generic array creation. If you must work with arrays required by a legacy API, use a controlled solution that validates data and isolates unchecked casts; you cannot ask the JVM to deeply check generic arguments via `List.class` alone.

## 9. Why Is Casting `Object[]` to `T[]` a Trap?

A short-looking yet dangerous approach:

```java
// DO NOT USE:
@SuppressWarnings("unchecked")
static <T> T[] wrongArray(int length) {
    return (T[]) new Object[length];
}
```

Casting to `T[]` in generic source code does not change **the kind of array allocated**. The object remains `Object[]`. If the caller writes:

```java
// Using wrongArray above:
String[] names = wrongArray(2);
```

the result can throw `ClassCastException` on the caller side when `Object[]` must be converted to `String[]`. This is not a matter of "the JVM forgot generics so any array works": the runtime knows very well that `Object[]` differs from `String[]`.

Comparison of two cases:

```text
new Object[2] -> runtime type: Object[]
new String[2] -> runtime type: String[]

Putting a (T[]) cast in front of Object[] does not turn Object[] into String[].
String[]::new and Array.newInstance(String.class, 2) genuinely create String[].
```

Furthermore, `ArrayStoreException` is a different kind of error: it occurs when you **write an element of the wrong type into a reference array** that already has a true component type. `ClassCastException` can occur when you **cast an array reference** or return value to an incompatible type.

### Factories Also Need Clear Contracts

`IntFunction<T[]>` relies on the caller providing a properly typed factory. If a caller deliberately uses raw types or unchecked casts to pass a factory returning an unsuitable array, the system can fail with a type error at some point. A generic signature cannot automatically inspect every case that intentionally bypasses type safety.

Therefore:

- Use explicit array constructor references, such as `String[]::new`.
- Avoid factories like `length -> (T[]) new Object[length]`.
- Specify clearly whether `null` or differing lengths are accepted; the `allocateWithFactory` helper above checks both.
- Minimize `@SuppressWarnings`; use it only when justified by safety reasoning at a narrow point, such as reflection with an exact `Class<T>`.

## 10. Factories Do Not Make Generics Reifiable

Arrays created with `String[]::new` or `Array.newInstance(String.class,n)` have `String` as their true component type; yet `List<String>` still has no runtime class specialization. `List.class` only represents raw `List`, and `List<String>.class` is invalid.

```java
Object[] names = new String[2];
try {
    names[0] = 12;
} catch (ArrayStoreException expected) {
    System.out.println("Rejected by runtime String[] component type");
}
```

Reference arrays remain covariant, whereas `List<String>` cannot be assigned to `List<Object>`. When reading from `Collection<Integer>` to create `Number[]`, use `Collection<? extends Number>` and the `Number[]::new` factory. Avoid the unchecked cast `(T[]) new Object[n]`: a factory or token supplies **runtime component proof** that a mere cast lacks.

This is the boundary of both allocation methods, not a promise to verify nested generic arguments or untrusted input data.

## 11. Difference Between `Class<T>` and `Class<T[]>`

Sometimes an API takes an **element-type token**:

```java
Class<String> component = String.class;
```

In that case, `Array.newInstance(component, length)` is the natural way to create the array.

Another API might take a **complete array-type token**:

```java
Class<String[]> arrayType = String[].class;
System.out.println(arrayType.getComponentType().getSimpleName());
```

Output:

```text
String
```

`Class<T[]>` describes the entire array type `T[]`, whereas `Class<T>` describes the element type. Never pass `String[].class` as if it were `Class<String>`: the two tokens have different meanings.

Additionally, `Class<T>` does not fully represent deeply parameterized types like `List<String>`. If a library needs to store a `List<String>` description for deserialization or generic reflection, it may need `java.lang.reflect.Type`/`ParameterizedType`/a type reference, **not** just `Class<T>`. Yet `Type` is a type descriptor; you cannot pass an arbitrary `ParameterizedType` to `Array.newInstance(Class, length)` to conjure a nonexistent runtime component.

## 12. Length, Empty Arrays, and Edge Cases

### 12.1. Zero Length

Both `String[]::new` with `n = 0` and `Array.newInstance(String.class, 0)` create a `String` array of length 0. An empty array still retains its `String` runtime component type; it does not "lose its type" for having zero elements.

`Collection.toArray(String[]::new)` can call the generator with length 0 as a signal to create an array of the right type; when the collection has more elements, the overload is responsible for supplying an appropriately sized result array.

### 12.2. Negative Length

`new String[-1]` and `Array.newInstance(String.class, -1)` throw `NegativeArraySizeException` under array allocation behavior. The `allocateWithFactory` helper in the example **intentionally checks and throws `IllegalArgumentException`** to demonstrate a custom input contract; do not infer that as the default behavior of every constructor reference.

### 12.3. Factory Returning `null`

`IntFunction<T[]>` is a functional interface, so its return type technically permits returning `null`. If you intend to use the array immediately, check and fail near the factory boundary. `Objects.requireNonNull(factory.apply(length))` throws `NullPointerException` with an appropriate message, rather than letting an error surface later in processing code.

### 12.4. Factory Returning the Wrong Size

In a custom helper, you can require `array.length == length`. However, `Collection.toArray` has its own rules for the passed array: if it is too small, it can allocate a new array of the right type; if it has enough room, it populates the provided array per contract.

Therefore, do not add a check claiming "the factory must always return `collection.size()`" when working with `Collection.toArray(IntFunction)`, because the default implementation may intentionally invoke the factory with `0`.

### 12.5. Primitive Arrays

`int[]` and `double[]` are primitive arrays, distinct from `Integer[]` and `Double[]`. `Class<T>`/`T[]` in reference-based generic helpers do not automatically support creating or returning primitive arrays in the usual way. If a primitive array is needed, use specific APIs (`new int[n]`, `IntStream.toArray()`, etc.) or reflection with an explicit return-type contract.

## 13. Which Approach Should You Choose in Real Scenarios?

| Scenario | Suitable Choice | Reason |
| --- | --- | --- |
| Converting `List<String>` to `String[]` | `list.toArray(String[]::new)` | Standard library, concise, explicit component type. |
| Writing a generic array-allocation helper where the caller knows the array type | `IntFunction<T[]>`, caller passes `TConcrete[]::new` | No unchecked cast needed inside the helper. |
| Writing a framework that already has `Class<T>` | `Array.newInstance(Class<T>, n)` | The token provides the runtime component type. |
| Copying `List<Integer>` into `Number[]` | `toArray(Number[]::new)` or a matching factory | Safely accepts subtype relationships. |
| Needing to create `int[]` | Direct primitive allocation / primitive APIs | `int[]` is not `Integer[]`. |
| Wanting an array of `List<String>` | Consider `List<List<String>>`; if an array is needed, runtime component can only be `List` | There is no `List<String>.class`. |
| Data from legacy/untrusted APIs | Validate elements before storing in typed structures | Factories do not deeply check nested generics. |
| Do not genuinely need an array | Keep `List<T>` | Avoids generic array creation limits and casts. |

Crucially, **do not force generic APIs to return arrays if consumers can use `List`**. Arrays fit when a library mandates them, when a runtime component type is needed, or for array-specific operations. When only a dynamically sized collection is needed, `List<T>` usually expresses the domain more clearly.

## 14. Exercises and Answers

### Exercise 1. Write a helper that allocates a `String` array without casts.

**Answer:**

```java
static <T> T[] make(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}

// Called inside main/method:
String[] names = make(4, String[]::new);
```

Ensure the caller supplies a suitable factory. The version with input and length validation is shown in Section 3.

### Exercise 2. What is the difference between `String[]::new` and `String.class`?

**Answer:** `String[]::new` is a function that takes a size and creates `String[]`; `String.class` is a class token describing the `String` element type, which must be passed to an API such as `Array.newInstance` to create the array.

### Exercise 3. Why is `new T[5]` invalid?

**Answer:** The type variable `T` does not provide a concrete runtime component type for the new array; Java rejects generic array creation. Use a factory or `Class<T>` provided by the caller.

### Exercise 4. Given `List<Integer>`, can you create `Number[]`?

**Answer:** Yes. The caller can write `Number[] result = integers.toArray(Number[]::new)` or use a helper accepting `Collection<? extends Number>` and a `Number[]` factory. `Integer` elements can be stored into a `Number[]` array.

### Exercise 5. Does `Collection.toArray(IntFunction)` always call the factory with `collection.size()`?

**Answer:** No. The default implementation uses `generator.apply(0)` and then delegates array handling to `toArray(T[])`. Follow the contract of the API invoking the factory; do not assume the argument equals `size`.

### Exercise 6. Why is `(T[]) new Object[5]` unsafe?

**Answer:** The underlying array object remains `Object[]`. When the caller expects an array with a component type like `String[]`, the runtime can throw `ClassCastException`. Casting does not change the array kind.

### Exercise 7. Can `List<String>.class` be passed to `Array.newInstance`?

**Answer:** No, because `List<String>.class` is not a valid class literal. `List.class` only represents the runtime `List` type after erasure, with no deep verification of the `String` argument.

### Exercise 8. Does a helper rejecting `int.class` when taking `Class<T>` contradict Java reflection supporting `int[]`?

**Answer:** No. Reflection supports creating primitive arrays when invoked directly with `int.class`. The example's helper returning `T[]` deliberately restricts itself to reference component types to avoid confusion with primitive arrays.

### Exercise 9. A factory returns `String[4]` when the helper requested length `2`. Is this a Java generics error or a contract error?

**Answer:** Not necessarily a type error; both are still `String[]`. However, if the helper promises an array of exact length `n`, it must check and report a contract error, as `allocateWithFactory` does.

### Exercise 10. If a `List` contains wrong-typed elements due to a raw operation, does converting it with `toArray(String[]::new)` automatically fix the data?

**Answer:** No. When copying elements into the `String` array, the runtime can detect incompatible elements and throw `ArrayStoreException`. You must fix the source of heap pollution or validate/convert elements according to domain rules.

## 15. Summary

- You cannot write `new T[n]` because a generic type variable does not supply a runtime component type for the array.
- `IntFunction<T[]>` lets the caller provide a factory such as `String[]::new`, avoiding unchecked casts inside the helper.
- `Class<T>` combined with `Array.newInstance` works when the caller holds an element-type token; isolate the cast and handle primitive tokens according to the API contract.
- `Collection.toArray(String[]::new)` is usually the most concise way to convert a collection into an array. Note that the generator may receive `0` under the default implementation, not necessarily `size()`.
- Runtime array types are genuinely preserved: `String[]` differs from `Object[]`, and the JVM enforces array store checks.
- A class token or factory for the `List` container type does not reify the `String` argument nested inside `List<String>`.
- When an array is not genuinely required, `List<T>` usually keeps APIs simpler and avoids generic array creation restrictions.

**Practical rule:** Delegate array creation to where concrete type information exists (an array factory or class token), so the created array has **the exact right runtime component type** instead of relying on unverifiable casts.
