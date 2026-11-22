# Comparing Runtime-Checked Arrays with Compile-Time-Checked Generics

## Learning Objectives

In Java, both **arrays** and **generics** help describe element types, yet the way they enforce type safety differs. Arrays retain their component type at runtime so the JVM can check write operations directly. Most generic type arguments are erased (*type erasure*), so the compiler checks generic operations at compile time; the JVM does not have a separate runtime class for `List<String>`.

After this lesson, you will be able to:

- Distinguish **runtime type checking of arrays** from **compile-time type checking of generics**.
- Explain why `String[]` can be assigned to `Object[]`, whereas `List<String>` cannot be assigned to `List<Object>`.
- Accurately predict two important errors: `ArrayStoreException` when writing an incompatible type into an array with a specific component type; `ClassCastException` when reading from a generic collection that has been type-polluted.
- Understand why Java forbids creating `new List<String>[10]` and `new T[10]`, yet allows `new List<?>[10]`.
- Choose solutions such as `List<T>`, an `IntFunction<T[]>` array factory, `Class<T>` combined with `Array.newInstance`, and safe varargs.
- Recognize **heap pollution**, raw types, and unchecked/varargs warnings when maintaining Java code.

The complete examples are designed for **Java 17+**. Only snippets explicitly labeled as a "complete program" need to be saved into their corresponding files to run standalone; other short snippets are used to explain a single rule or compile-time error.

## 1. Two Mechanisms That Look Similar but Differ Fundamentally

Let us start with two kinds of structures that hold strings:

```java
String[] names = new String[2];
java.util.List<String> labels = new java.util.ArrayList<>();
```

In Java source code, both suggest that elements must be `String`. However, the way Java enforces that promise differs:

| Question | `String[]` | `List<String>` |
| --- | --- | --- |
| Does the element type exist in the runtime class? | **Yes:** the component type is `String` | **No** separate runtime class `List<String>` |
| Primary place of checking | Compiler **and** the JVM when performing array writes | Primarily the compiler via generic type arguments |
| What if "bypassed" via a wider reference? | `Object[]` can point to `String[]`; the JVM still checks on write | Raw `List` can insert a wrong element with an unchecked warning |
| Characteristic error | `ArrayStoreException` on an invalid write | `ClassCastException` when an invalid value is cast to the expected type |
| Is it covariant? | Yes: `String[]` is a subtype of `Object[]` | No: `List<String>` is **not** a subtype of `List<Object>` |
| Direct creation | `new String[2]` is valid | `new ArrayList<String>()` or `new ArrayList<>()` is valid |

Key terms:

- **Reifiable type:** a type that can be fully represented at runtime according to the language rules. An array type with a reifiable component, such as `String[]`, has enough information to check writes.
- **Non-reifiable parameterized type:** a type such as `List<String>` containing generic arguments that have no corresponding runtime representation for the JVM to verify every `String` inside the list.
- **Type erasure:** the mechanism of compiling generic declarations and references into descriptors suitable for the JVM, while the compiler may insert casts where needed.

Note: `String[]` is also type-checked by the compiler at the source level; one should not claim that "arrays are *only* checked at runtime." The difference is that **arrays have an additional write-gate check in the JVM based on the actual component type**, even when an `Object[]` reference hides the element type in source code.

## 2. Arrays Have a Runtime Component Type

Consider the following illustration:

```java
String[] names = {"Lan", "Minh"};
Object[] asObjects = names; // Valid: arrays are covariant.
```

Both variables reference **the exact same array object**. Because the created object is `String[]`, its runtime class remains `String[].class` and its component type remains `String.class`, even though the variable `asObjects` has source type `Object[]`.

A valid call:

```java
asObjects[0] = "Hoa";
```

A call rejected by the JVM at write time:

```java
// Compiles because asObjects has source type Object[].
// At runtime with an actual String[] array object, the following line throws ArrayStoreException:
asObjects[0] = Integer.valueOf(42);
```

Because `Integer` cannot be stored in an array whose actual component type is `String`, the JVM throws **`ArrayStoreException`** right at the array assignment expression. The previous value at that index is not overwritten by the incompatible object.

It is **array covariance** that creates a situation where the compiler cannot decide at the source level: writing an `Object` fits the `Object[]` variable, yet the object's runtime component type may be narrower. Java allows this array subtyping relationship for historical reasons; the runtime store check compensates for that lack of strictness.

Conversely, with a variable declared directly as `String[]`:

```java
String[] direct = new String[1];
// direct[0] = 42; // Compile-time error.
```

The compiler already sees that the argument has the wrong type, so there is no need to wait for the JVM's store check in this case.

## 3. Generics Do Not Keep a Specialized Runtime `List<String>`

Consider:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();
```

If you directly instantiate the two `ArrayList`s above, `strings.getClass() == numbers.getClass()` is `true`: the same runtime class `ArrayList`. The type arguments `String` and `Integer` are important information for the compiler in source code, but they do not create two corresponding runtime classes.

With a typed variable, Java rejects an invalid addition:

```java
strings.add("Java"); // Valid.
// strings.add(42); // Compile-time error: Integer is not compatible with String.
```

What happens when a raw reference is used?

```java
java.util.List raw = strings;
raw.add(42); // Compiler emits an unchecked warning.
```

The call can execute and place an `Integer` into the very list that `strings` points to. Because `ArrayList` does not have a runtime component type `String` to check inside `add(Object)`, it does not throw `ArrayStoreException` on its own like an array.

The error typically occurs when typed code reads the data:

```java
String value = strings.get(1); // May throw ClassCastException.
```

In source code, the compiler treats `List<String>.get(...)` as returning `String`. However, the bytecode of `List.get(int)` returns `Object` after erasure; the compiler can insert **`checkcast java/lang/String`** at the use site. If the actual value is `Integer`, the cast fails and throws `ClassCastException`.

That is an example of **heap pollution**: the data state inside a collection object does not match the parameterized type that the code trusts. Java generics protect well when typed APIs are used properly; raw types and unchecked operations can break that guarantee.

## 4. Program A — Comparing Both Kinds of Errors in a Single Run

Create the file **`ArraysGenericsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class ArraysGenericsDemo {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh"};
        Object[] asObjects = names; // covariance
        System.out.println("array component: "
                + asObjects.getClass().getComponentType().getSimpleName());
        System.out.println("same array: " + (asObjects == names));

        try {
            asObjects[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("array write: "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("array[0]: " + names[0]);

        List<String> strings = new ArrayList<>(List.of("Java"));
        List<Integer> numbers = new ArrayList<>(List.of(7));
        System.out.println("same list class: "
                + (strings.getClass() == numbers.getClass()));
        // List<Object> objects = strings; // Compile-time error: invariant

        List raw = strings; // intentionally unsafe
        raw.add(42);        // unchecked
        System.out.println("list contents: " + strings);

        try {
            String second = strings.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("generic read: "
                    + ex.getClass().getSimpleName());
        }

        List<?>[] wildcardArray = new List<?>[1];
        wildcardArray[0] = List.of("safe", 5);
        System.out.println("wildcard read: " + wildcardArray[0].get(0));
    }
}
```

Compile and run:

```bash
javac -Xlint:all ArraysGenericsDemo.java
java ArraysGenericsDemo
```

**Verified stdout:**

```text
array component: String
same array: true
array write: ArrayStoreException
array[0]: Lan
same list class: true
list contents: [Java, 42]
generic read: ClassCastException
wildcard read: safe
```

The command `javac -Xlint:all` emitted `[rawtypes]` warnings for `List raw` and `[unchecked]` for `raw.add(42)`. These are **compiler diagnostics**, not part of the stdout of `java ArraysGenericsDemo`.

Line-by-line explanation:

1. `array component: String`: the component type can be accessed via `getClass().getComponentType()`, proving that the runtime knows this is a `String[]` array.
2. `same array: true`: the assignment `Object[] asObjects = names` does **not** create a copy; every write affects the same object.
3. `array write: ArrayStoreException`: the JVM rejects the invalid value before storing it; therefore, `array[0]` remains `Lan`.
4. `same list class: true`: two `ArrayList` instances with different generic arguments share one runtime class.
5. `list contents: [Java, 42]`: the raw type bypassed the compile-time guard of `List<String>`, while the `ArrayList` object itself does not distinguish generic arguments.
6. `generic read: ClassCastException`: the error surfaces when the actual value is used as a `String`.
7. `wildcard read: safe`: an array of `List<?>` is allowed to be created directly; a later section explains why.

**Interim conclusion:** An invalid write into an array is rejected immediately at runtime. In the generic example broken via a raw type, the invalid addition succeeded and the error was detected late at read time.

## 5. Why Are Arrays Covariant While Generics Are Typically Invariant?

**Array covariance**:

```java
String[] strings = new String[2];
Object[] objects = strings; // Valid.
```

If `S` is a reference subtype of `T`, then `S[]` is also a subtype of `T[]` under Java's array covariance rule. This relationship allows a wider reference to view a narrower array, but forces the JVM to perform runtime store checks.

**Generic invariance**:

```java
List<String> strings = new ArrayList<>();
// List<Object> objects = strings; // Invalid.
```

`String` is a subtype of `Object`, yet `List<String>` is **not** a subtype of `List<Object>`. If Java allowed that assignment, a call like `objects.add(42)` would corrupt the list of strings without a corresponding runtime generic component type to block it immediately.

If you want to read lists of different element types, use a wildcard:

```java
List<?> unknown = strings;
Object first = unknown.isEmpty() ? null : unknown.get(0);
// unknown.add("new"); // Does not compile: element type is unknown.
```

`List<?>` is still a parameterized type with a constraint; **it is not a raw type**. Because the element type is unknown, the compiler prevents adding any non-`null` value through the wildcard reference.

For a concrete API, wildcards can express data flow direction:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) {
        total += n.doubleValue();
    }
    return total;
}
```

This snippet is an illustrative method that should be placed in a class importing `java.util.List`. It accepts `List<Integer>` or `List<Double>` to read `Number` values, while disallowing arbitrarily adding a `Number` because the actual element type may be narrower.

Do not conclude that "generics cannot be polymorphic." **Invariance** describes the relationship between parameterizations `List<S>` and `List<T>`; wildcards `? extends`/`? super` allow expressing flexible and safe relationships when needed.

## 6. Reification and Restrictions on Creating Generic Arrays

An array creation expression `new ComponentType[n]` requires a **reifiable component type**, meaning the appropriate type information must be representable at runtime so the JVM can check writes. `String`, raw `List`, and parameterized `List<?>` (where all type arguments are unbounded wildcards `?`) meet this requirement; `List<String>`, `List<? extends Number>`, and a type variable `T` do not.

```java
String[] words = new String[3];            // Valid.
List<?>[] lists = new List<?>[3];          // Valid.
// List<String>[] bad = new List<String>[3]; // Generic array creation error.
// T[] bad = new T[3];                       // Error when T is a type variable.
```

An element of `List<?>[]` can be a `List<String>` or a `List<Integer>`: the runtime component type is only `List`, not a `List<String>` that can be verified per element. Directly allowing `new List<String>[n]` would create a type promise that the array store check cannot uphold when a user writes through an `Object[]` alias. **Do not confuse** `List<?>[]` with `List<Object>[]`, and do not use unchecked casts to simulate an array of string lists.

Reifiable type rules, arrays holding parameterized lists, and heap pollution are analyzed with separate runnable examples in the lessons on `new List<String>[]` and `List<?>[]`.

## 7. Declaring `T[]` Is Not Allocating `new T[n]`

```java
class Holder<T> {
    private final T[] elements;
    Holder(T[] elements) { this.elements = elements; }
    T first() { return elements[0]; }
}
```

`Holder<String>` can **receive** `new String[]{"A"}` from the caller, and then read `first()` as `String`. Inside `Holder<T>`, however, you cannot write `new T[n]`: `T` is a type variable and has no runtime component class to create the right array for every parameterization. Even with `T extends Number`, a `Number[]` array is not automatically an `Integer[]`.

Do not fix this with `(T[]) new Object[n]`: the actual array still has runtime class `Object[]`, so a caller expecting `String[]` can hit `ClassCastException`. To create an array with the right component type, accept a factory or a trustworthy `Class<T>`; the next program illustrates both approaches, and the dedicated lesson on `new T[]` explains the bytecode/erasure limits.

## 8. Program B — Safely Creating a Typed Array via Factory or `Class<T>`

Create the file **`TypedArrayDemo.java`**:

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.IntFunction;

public final class TypedArrayDemo {
    static <T> T[] withFactory(IntFunction<T[]> factory, int n) {
        T[] result = factory.apply(n);
        return result;
    }

    static <T> T[] withClass(Class<T> elementType, int n) {
        Objects.requireNonNull(elementType);
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(elementType, n);
        return result;
    }

    @SafeVarargs
    static <T> List<T> concat(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        String[] words = withFactory(String[]::new, 2);
        words[0] = "A";
        words[1] = "B";
        System.out.println("factory: " + Arrays.toString(words));

        Integer[] ids = withClass(Integer.class, 2);
        ids[0] = 10;
        System.out.println("reflection component: "
                + ids.getClass().getComponentType().getSimpleName());

        try {
            Object[] view = ids;
            view[1] = "wrong";
        } catch (ArrayStoreException ex) {
            System.out.println("reflection store: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("concat: "
                + concat(List.of("x"), List.of("y")));
    }
}
```

Compile and run:

```bash
javac -Xlint:all TypedArrayDemo.java
java TypedArrayDemo
```

**Verified stdout:**

```text
factory: [A, B]
reflection component: Integer
reflection store: ArrayStoreException
concat: [x, y]
```

### Approach 1 — `IntFunction<T[]>` Factory

`String[]::new` is an **array constructor reference**: when given length `2`, it creates an actual `String[2]`, not an `Object[2]` carrying a generic label. The `withFactory` method simply asks the factory to create the exact array type provided by the caller.

Advantage: it avoids manual casts from `Object[]` and clearly expresses the responsibility for creating the array. For APIs used across many types `T`, an appropriate factory is often the cleanest way to keep code generic while preserving the runtime component type.

### Approach 2 — `Class<T>` with `Array.newInstance`

`Integer.class` is passed explicitly, so reflection has enough information to allocate an array object with component type `Integer`. The result is genuinely `Integer[]`, as proven by the line:

```text
reflection component: Integer
```

In `withClass`, the `(T[])` cast is placed within a small scope annotated with `@SuppressWarnings("unchecked")`. Because of erasure, the compiler cannot generically verify the cast from `Object` returned by `Array.newInstance`; however, in this example, passing a properly typed **`Class<T>`** without letting other callers arbitrarily swap the token provides justification that the array is allocated with the matching component type.

`Class<T>` is a runtime token for a concrete class and does not recover nested types such as `List<String>` from `List.class`. Avoid using an uncontracted raw `Class` and claiming that `List<String>[]` will be fully checked.

### Properly Typed Arrays Still Enforce Runtime Store Checks

Whether created via a factory or reflection, the actual `Integer[]` object still carries the `Integer` component type. Writing a `String` through a wider `Object[]` variable is immediately rejected with `ArrayStoreException`. This confirms that the allocation preserves the **actual array type**, not merely a generic annotation in source code.

## 9. Generic Method `T[]` in Bytecode: An Advanced Detail

You can inspect the signatures of the compiled `TypedArrayDemo` yourself:

```bash
javap -p -s TypedArrayDemo
```

Verified descriptor excerpt:

```text
static <T> T[] withFactory(java.util.function.IntFunction<T[]>, int);
  descriptor: (Ljava/util/function/IntFunction;I)[Ljava/lang/Object;

static <T> T[] withClass(java.lang.Class<T>, int);
  descriptor: (Ljava/lang/Class;I)[Ljava/lang/Object;
```

`[Ljava/lang/Object;` is the descriptor for **`Object[]`**, which is the erased type of `T[]` when `T` is unbounded. This **does not contradict** `withFactory(String[]::new, 2)` returning an actual `String[]` object: the erased return descriptor of a method and the runtime class of the returned object are two different aspects.

The compiler can insert `checkcast [Ljava/lang/String;` at a call site that assigns the result to `String[]`. Because the factory/token creates the right component type, that cast succeeds in the valid program of the example.

If you replace the factory with code that always creates `Object[]` and casts it to `T[]`, the source code may look similar, yet the runtime class of the result is no longer guaranteed to match, putting the caller's cast at risk of failing.

## 10. Program C — Why Unchecked Casts with Generic Arrays Are Dangerous

The following experiment intentionally creates heap pollution that `ArrayStoreException` **cannot prevent**, because the array's runtime component type is only `List`.

Create the file **`UnsafeGenericArrayDemo.java`**:

```java
import java.util.List;

public final class UnsafeGenericArrayDemo {
    public static void main(String[] args) {
        List<?>[] backing = new List<?>[1];

        @SuppressWarnings("unchecked")
        List<String>[] strings = (List<String>[]) backing;

        Object[] objects = strings;
        objects[0] = List.of(123);

        System.out.println("array component: "
                + objects.getClass().getComponentType().getSimpleName());

        try {
            String value = strings[0].get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("polluted read: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac -Xlint:all UnsafeGenericArrayDemo.java
java UnsafeGenericArrayDemo
```

**Verified stdout:**

```text
array component: List
polluted read: ClassCastException
```

Analysis steps:

1. `new List<?>[1]` is valid because `List<?>` is reifiable; the actual array has component type `List`.
2. The cast `(List<String>[]) backing` is **unchecked** at the source level. It does not verify that every list inside contains only `String`s. The suppression in the example only highlights where evidence is missing; **it does not make the cast safe**.
3. The `Object[] objects` variable still references the same array; `objects[0] = List.of(123)` is allowed by the JVM because the inserted object is a `List`, matching the array's runtime component type.
4. `strings[0].get(0)` is treated by the compiler as returning `String`, yet the actual value is `Integer`; `ClassCastException` occurs on read/cast.

**Takeaway:** Arrays check the **object type stored in each array slot** (here `List`), not the **erased generic arguments** of that object (`String` vs `Integer`). Therefore, even though arrays have a runtime store check, it cannot rescue generic promises fabricated by an unchecked cast.

Do not use this experimental snippet as a data structure design in production. If you need multiple groups of `List<String>`, a more natural choice is `List<List<String>>` with typed operations.

## 11. Generic Varargs Also Use Arrays at Runtime

`List<T>... groups` is a varargs parameter whose backing array has a generic component type that is usually **non-reifiable**. The caller or compiler may have to use an erased array and emit an unchecked warning; if a method stores a `List<Integer>` into an array that a caller treats as `List<String>[]`, reading a `String` later can cause `ClassCastException`.

On Java 17, `@SafeVarargs` is permitted on constructors and eligible methods (`static`, `final`, and `private` instance methods). This annotation does **not** make `List<T>` reifiable and does not add runtime validation automatically: the author is responsible for not storing invalid components and not letting the varargs array escape to places where it could be mutated unchecked.

```java
@SafeVarargs
static <T> List<T> concat(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

The `concat` example only reads the lists, does not modify or expose the varargs array, and returns a new collection; therefore, there is sound justification for the annotation. If an API only needs to iterate over elements, accepting `Collection<? extends T>` is often simpler. This is a **complementary intersection** of arrays and generics, not a workaround to legitimize `new T[n]` or `new List<String>[n]`.

## 12. Runtime Class and Type Observability

Several distinct questions are often conflated:

| Question | How to observe | Result |
| --- | --- | --- |
| What is the actual component type of a `String[]` array? | `array.getClass().getComponentType()` | `String.class` |
| Do two `ArrayList`s with different type arguments have the same runtime class? | `list1.getClass() == list2.getClass()` | Yes, if both are instantiated directly from the same `ArrayList` class in the same class-loading context |
| What is the actual type of an object inside `List<String>`? | `list.get(i).getClass()` when the element is non-`null` | The actual class of the **value**, not confirmation of the generic argument for every element |
| Does the JVM know `ArrayList<String>` as a separate subclass? | `list.getClass()` | There is no separate runtime class for that parameterization |
| What does `List<?>[]` check on write? | Runtime array store | The element must be a compatible `List`, without checking the inner type arguments |

Reflection can read **generic metadata on declarations** of a class, field, or method (for example `Field.getGenericType()`). That is different from the runtime being able to check all `String` arguments inside a specific `ArrayList<String>` instance when `add(Object)` is called. Do not infer element types solely from a collection's `getClass()`.

Another detail: `int[]` is a primitive array. `int[]` is **not a subtype of `Object[]`**, even though `int[]` itself is an `Object` and has its own runtime class. Array covariance such as `String[] -> Object[]` applies to **arrays of reference types** with a matching subtype relationship.

## 13. When to Use Arrays vs. Generic Collections

Arrays and generic collections have different trade-offs; neither choice should be treated as absolute.

**Arrays are appropriate when:**

- Elements are indexed and the length is usually known or fixed.
- You need to interface with APIs requiring arrays, especially legacy APIs or low-level interfaces.
- You need primitive arrays such as `int[]` or `double[]` to avoid boxing elements.
- You have a concrete component type and want to leverage runtime store checks.

**Generic collections are appropriate when:**

- The number of elements changes as the program runs.
- You need flexible `add`, `remove`, traversal, and transformation operations.
- You want to model nested containers like `List<List<String>>` without creating unsafe generic arrays.
- You want to use wildcards to express producer/consumer type relationships.

An API can combine both. For example, a method that accepts `Collection<? extends T>` and returns `T[]` can request an array factory or a type token. What matters is that **the runtime component type of the returned array matches the promised type**.

Avoid passing raw collections through multiple application layers and casting them back to generic types at the end. If you must interact with legacy APIs, validate the data at the boundary and convert to typed forms as early as possible.

## 14. Common Misconceptions to Eliminate

**Misconception 1 — "Arrays are only type-checked at runtime."**

Arrays are also checked by the compiler for declarations like `String[]`. The difference is that the JVM knows the runtime component type and performs an additional store check, which is required because of covariance.

**Misconception 2 — "Generics are unsafe because of type erasure."**

In programs that use typed APIs properly, the compiler prevents incompatible writes. The delayed failure in the example occurred because the code **deliberately** used raw types/unchecked casts and violated the contract.

**Misconception 3 — "`List<String>` is a subtype of `List<Object>` because `String extends Object`."**

Java generics are invariant by default. If an API needs to read multiple kinds of lists, use `List<?>` or an appropriate wildcard.

**Misconception 4 — "Using `new Object[n]` and casting creates a real `T[]`."**

The actual array remains `Object[]`; a cast at the caller expecting `String[]` can fail. Use `IntFunction<T[]>` or `Class<T>` to create the true runtime component type when needed.

**Misconception 5 — "`new List<?>[n]` is illegal just like `new List<String>[n]`."**

`List<?>` is a reifiable case with an unbounded wildcard, so it can serve as the component type of a newly created array. `List<String>` does not satisfy that condition.

**Misconception 6 — "`ArrayStoreException` guarantees every list in the array has the right type arguments."**

The runtime array checks whether the object in each slot is a `List`. It cannot distinguish `List<Integer>` from `List<String>` at runtime via array store checks alone.

**Misconception 7 — "Every `ClassCastException` in generics happens right at `add`."**

Wrong types can be added via a raw reference. The error typically occurs when typed code reads an element and the compiler-inserted cast executes to use it as a `String`.

**Misconception 8 — "`@SafeVarargs` fixes heap pollution automatically."**

The annotation does not change bytecode to add a runtime component type to generics. It is an assertion about the safety of how varargs are used and must be verified by reasoning and testing.

## 15. Additional Practice and Answers

### Exercise 1 — Predicting When the Error Occurs

```java
String[] data = {"A"};
Object[] ref = data;
ref[0] = 9;
```

**Answer:** the code compiles, but the JVM throws `ArrayStoreException` at the line `ref[0] = 9`. `Integer` does not belong in `String[]`; the original element is preserved.

### Exercise 2 — Why Is the Generic Assignment Invalid?

```java
List<String> a = new ArrayList<>();
// List<Object> b = a;
```

**Answer:** `List<String>` and `List<Object>` are invariant. Allowing it would create a path to write a non-`String` `Object` into a list of strings, whereas the runtime does not retain the generic argument to block it like `String[]` does.

### Exercise 3 — Two Different Errors

After `List raw = typedList`, the code calls `raw.add(100)`, and then `String s = typedList.get(0)`. Where can errors appear?

**Answer:** the compiler emits an unchecked warning at the raw `add` call. If the element read is actually an `Integer`, using it as a `String` causes `ClassCastException`. A raw `ArrayList` does not guarantee throwing `ArrayStoreException` when adding a value.

### Exercise 4 — Checking Generic Array Creation

Among the following expressions, which ones are valid?

```java
new String[3];
new List<?>[3];
// new List<String>[3];
// new T[3]; // T is a type variable.
```

**Answer:** the first two expressions are valid; the latter two cannot be used directly to create arrays in Java source code.

### Exercise 5 — Analyzing a Cast

Why is `(T[]) new Object[n]` not equivalent to `String[]::new` when `T = String`?

**Answer:** the first creates an actual `Object[]` array and applies an unchecked cast, whereas the second directly creates a `String[]`. The runtime component types differ; `String[]` requires an actual array with a compatible component type, and `Object[]` does not meet that requirement.

### Exercise 6 — API Design

You need a method to create an array of an arbitrary element type. Provide two signature options:

```java
static <T> T[] create(java.util.function.IntFunction<T[]> factory, int size)
static <T> T[] create(Class<T> type, int size)
```

**Guided answer:** the factory variant calls `factory.apply(size)` (for example `String[]::new`); the token variant uses `Array.newInstance(type, size)` and a carefully scoped cast. Verify the component type of the returned array yourself using reflection.

### Exercise 7 — Why Can a `List<?>[]` Array Still Hold a List of Numbers?

```java
List<?>[] groups = new List<?>[1];
groups[0] = List.of(1, 2);
```

**Answer:** the runtime array requires elements to be `List`, and the wildcard does not promise a specific element type. Values retrieved from it are viewed as `Object` unless further checked.

### Exercise 8 — Varargs Annotation

Can a generic varargs method add `List<Integer>` instances into a varargs array that the caller treats as `List<String>[]`, and still keep `@SafeVarargs`?

**Answer:** it should not; that operation causes heap pollution and breaks the safety promise implied by the annotation. Only use `@SafeVarargs` for an implementation that genuinely performs no unsafe operations on the varargs array.

## 16. Self-Assessment Checklist

You can consider this lesson complete when you can explain:

1. Reference-type arrays have **covariance**, the compiler still checks types, and the JVM checks stores against the runtime component type.
2. `List<String>` is **invariant**, and generic arguments do not create a separate `ArrayList<String>` runtime class.
3. `ArrayStoreException` differs from `ClassCastException` in both where it is detected and the conditions that trigger it.
4. `new List<String>[n]` and `new T[n]` are illegal, while `new List<?>[n]` is legal.
5. `T[]` can serve as a return/field/parameter type; however, allocating the right runtime array requires knowing how to construct the component type.
6. An array factory or `Class<T>` helps create an array of the true runtime type instead of relying on an unchecked cast from `Object[]`.
7. Generic varargs require caution regarding heap pollution, and `@SafeVarargs` is a commitment from the author.
8. A collection's `getClass()` must not be treated as proof of the list's type arguments.

## Conclusion

**Java arrays retain their runtime component type and check write operations**, so a `String[]` viewed through `Object[]` still rejects an `Integer` with `ArrayStoreException`. **Generics check types primarily at compile time and undergo type erasure**, so `List<String>` has no equivalent runtime "store fence"; raw types or unchecked casts can cause heap pollution, followed by `ClassCastException` on read. That very difference explains why Java keeps arrays covariant while keeping generics invariant, and why creating arrays of non-reifiable generic types is restricted. When you truly need `T[]`, use a factory or a trustworthy type token; for flexible generic structures, prefer collections and wildcards that express the contract accurately.
