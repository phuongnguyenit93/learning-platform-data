# Using Only Reference Types in Java Generics: Primitives, Wrapper Types, and Autoboxing

In Java, **type arguments passed to generics must be reference types**. Therefore, `List<Integer>` is valid whereas `List<int>` is invalid. Java provides **wrapper classes** such as `Integer` and `Double`, along with **autoboxing/unboxing**, to work conveniently with numbers, booleans, and characters when APIs require reference types.

This seemingly simple rule directly affects generic class and method syntax, `List`/`Map` operations, `NullPointerException` bugs, value comparisons, as well as memory overhead and performance.

## 1. Distinguishing Primitives from Reference Types

Java has eight *primitive types*: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, and `double`. A primitive variable holds a value of that type directly, such as `int count = 10;` or `boolean active = true;`. Primitives are not objects and have no instance methods.

**Reference types** include classes, interfaces, arrays, and other Java reference types; a reference variable can point to an object/array or hold `null`. For example, `String`, `Integer`, `List<String>`, and `int[]` are all reference types, even though the elements of `int[]` are primitives.

Common mapping table:

| Primitive | Wrapper class | Example value |
|---|---|---|
| `boolean` | `Boolean` | `Boolean flag = true;` |
| `byte` | `Byte` | `Byte size = (byte) 7;` |
| `short` | `Short` | `Short code = (short) 12;` |
| `char` | `Character` | `Character letter = 'A';` |
| `int` | `Integer` | `Integer count = 42;` |
| `long` | `Long` | `Long total = 42L;` |
| `float` | `Float` | `Float rate = 1.5f;` |
| `double` | `Double` | `Double amount = 1.5;` |

Wrapper classes reside in `java.lang` and are imported automatically. They are **immutable** objects: arithmetic operations do not mutate the value inside an existing `Integer` object. Both primitives and wrappers are useful; choose the right one for the API contract and data requirements.

`void` is not a value-holding primitive to store in collections; `Void` is a special reference class occasionally used as a type parameter to indicate the absence of a value result in APIs like `Callable<Void>`. Do not think of `Void` as a “numeric wrapper” or a way to store a `void` value.

## 2. Why Is `List<int>` Invalid While `List<Integer>` Is Valid?

Generic classes and generic interfaces use parameterized types, such as `List<E>`, `Map<K, V>`, and `Box<T>`. In Java 17, **type arguments must be reference types** (or valid wildcards where permitted); primitive type names like `int` and `double` cannot be written inside `<...>` as type arguments.

Examples that **do not compile**, isolated to help recognize errors:

```java
List<int> numbers;            // Incorrect: int is not a reference type
Map<String, double> prices;   // Incorrect: double is not a reference type
Box<boolean> enabled;         // Incorrect: boolean is not a reference type
```

**Valid** versions:

```java
List<Integer> numbers;
Map<String, Double> prices;
Box<Boolean> enabled;
```

The snippets above are **declaration illustrations**, not standalone runnable programs: they require importing `List` and `Map` and defining an appropriate `Box<T>` class.

Similarly, a generic method:

```java
static <T> T identity(T value) {
    return value;
}
```

can be called as `identity(123)`, which does not mean `T` becomes the primitive `int`. The compiler applies **boxing** to represent the argument as `Integer`, then infers and type-checks according to rules for reference types. `Integer result = identity(123);` is valid; assigning the result to an `int` can trigger **unboxing**.

**Type erasure:** most Java type parameters are erased at compile time: an unbounded parameter `T` typically erases to `Object`, and a bounded parameter erases to its bound. Because `Object` and bounds are reference types, wrappers allow passing primitives across the boundaries of general-purpose generic APIs. Do not think of `List<Integer>` as a `List<int>` secretly optimized into a primitive array; it remains a list of `Integer` references.

## 3. Boxing, Autoboxing, and Unboxing: What Are They Exactly?

**Boxing** converts a primitive value into an instance of the corresponding wrapper type. **Autoboxing** is boxing automatically inserted by the compiler in Java-supported contexts. Conversely, **unboxing** extracts the primitive value from a wrapper; the compiler can also insert automatic unboxing.

```java
int primitive = 42;

Integer boxedExplicitly = Integer.valueOf(primitive); // Explicit boxing
Integer boxedAutomatically = primitive;               // Autoboxing

int unboxedExplicitly = boxedExplicitly.intValue();   // Explicit unboxing
int unboxedAutomatically = boxedAutomatically;         // Auto-unboxing
```

This is an illustrative snippet that must be placed inside a method or valid declaration scope. The two lines with `Integer.valueOf(...)` and `.intValue()` make the mechanism visible; in everyday code, autoboxing/unboxing keeps syntax concise.

Contexts where automatic conversion commonly occurs:

- **Assignment and argument passing:** `Integer x = 10;`, or passing `10` to a method expecting `Integer`, when context permits boxing.
- **Putting primitives into collections:** `List<Integer> values = new ArrayList<>(); values.add(10);` — the argument `10` is boxed into `Integer`.
- **Retrieving a wrapper to use as a primitive:** `int x = values.get(0);` — the `Integer` element is unboxed to `int`.
- **Arithmetic and numeric comparison operators:** `Integer x = 10; int y = x + 5;` normally requires unboxing `x` before addition.
- **Generic methods:** when calling `<T> T echo(T value)` with a primitive, boxing creates a wrapper value to fit into `T`.

**Autoboxing is not an arbitrary conversion between all wrappers.** For instance, to create a `Long` from an integer literal, write `Long n = 10L;` or `Long.valueOf(10L)`; do not assume `Integer` and `Long` are directly interchangeable just because `int` widens to `long`. `Integer i = 10; Long l = i;` is invalid.

Nor is there autoboxing from an arbitrary string to a number: `Integer.parseInt("42")` returns `int`, while `Integer.valueOf("42")` returns `Integer`. Converting digits in a string into a number is **parsing**, separate from boxing.

## 4. Standalone Runnable Java 17 Example: From Primitives to Generic Collections

Save the entire program as `PrimitiveGenericsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class PrimitiveGenericsDemo {
    static <T> T echo(T input) {
        return input;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(10); // int -> Integer (autoboxing)
        scores.add(20);

        int first = scores.get(0); // Integer -> int (unboxing)
        System.out.println("first: " + first);

        Integer echoed = echo(42);
        System.out.println("echo: " + echoed);

        int sum = scores.stream().mapToInt(Integer::intValue).sum();
        System.out.println("sum: " + sum);

        int[] raw = {2, 4, 6};
        List<int[]> batches = new ArrayList<>();
        batches.add(raw);
        System.out.println("array value: " + batches.get(0)[1]);

        List<int[]> oneArray = Arrays.asList(raw);
        System.out.println("asList size: " + oneArray.size());

        List<Integer> boxed = Arrays.stream(raw).boxed().toList();
        System.out.println("boxed stream: " + boxed);

        int primitiveSum = IntStream.of(raw).sum();
        System.out.println("primitive sum: " + primitiveSum);

        Integer a = Integer.valueOf(1000);
        Integer b = Integer.valueOf(1000);
        System.out.println("value equality: " + Objects.equals(a, b));

        Integer missing = null;
        System.out.println("missing is null: " + (missing == null));
        try {
            int unavailable = missing;
            System.out.println(unavailable);
        } catch (NullPointerException exception) {
            System.out.println("unboxing null: NullPointerException");
        }

        List<Integer> selected = new ArrayList<>(List.of(10, 20, 30));
        selected.remove(1); // remove(int index): removes 20
        selected.remove(Integer.valueOf(10)); // remove(Object): removes 10
        System.out.println("after remove: " + selected);
    }
}
```

Compile/run in the directory containing the file (JDK 17 or higher):

```bash
javac PrimitiveGenericsDemo.java
java PrimitiveGenericsDemo
```

Stdout in exact order:

```text
first: 10
echo: 42
sum: 30
array value: 4
asList size: 1
boxed stream: [2, 4, 6]
primitive sum: 12
value equality: true
missing is null: true
unboxing null: NullPointerException
after remove: [30]
```

Explanation of easily overlooked details:

1. `scores.add(10)` calls a method whose parameter type is `Integer`; the compiler inserts boxing. `int first = scores.get(0)` automatically unboxes the `Integer` result. The list still holds wrapper references and does not become an `int[]`.
2. `echo(42)` is a generic method `<T> T echo(T input)`; `42` is boxed into `Integer`, and the result can be kept as type `Integer`. `T` is not a primitive type.
3. `mapToInt(Integer::intValue)` turns the stream of `Integer`s into an `IntStream` to total with `sum()`, which returns `int`. Because every element is non-null, conversion is safe.
4. `int[]` **is a reference type**, even though its elements are `int`. Hence `List<int[]>` is valid, and `batches.get(0)[1]` reads the number `4` inside the array element.
5. `Arrays.asList(raw)` treats **one `int[]` array as a single element**, creating a `List<int[]>` of size `1`, not a `List<Integer>` of three numbers. This is a very common pitfall when passing a primitive array to a varargs generic API.
6. `Arrays.stream(raw).boxed().toList()` converts each `int` into `Integer` to build a `List<Integer>`. `Stream.toList()` in Java 17 returns a list that **does not support structural/content modification via mutating methods**; if modification is needed, wrap it in `new ArrayList<>(...)`.
7. `IntStream.of(raw)` sums directly over an `int` stream, avoiding allocating a list of wrappers just to add numbers.
8. `Objects.equals(a, b)` compares values safely with respect to `null`. Do not use `a == b` to check numeric equality when both operands are `Integer`.
9. `missing == null` checks for null safely; however, `int unavailable = missing;` attempts to unbox `null` and throws `NullPointerException`.
10. `List<Integer>.remove(1)` calls **`remove(int index)`**, whereas `remove(Integer.valueOf(10))` calls **`remove(Object value)`**. These two overloads mean different things, and autoboxing can trip up newcomers.

## 5. Primitive Arrays Are Reference Types: A Seemingly Contradictory Exception

The rule forbidding primitives as type arguments **does not mean anything containing primitives is forbidden**. Arrays themselves in Java are objects, so `int[]`, `double[]`, and `boolean[]` are all valid reference types when used as type arguments:

```java
List<int[]> chunks;
List<double[]> measurements;
Map<String, boolean[]> flags;
```

These are valid declarations when placed in context with `List` and `Map` imported. However, `List<int[]>` is a **list of integer arrays**, not a list of individual integers. For example, `chunks.get(0)` has type `int[]`, and `chunks.get(0)[0]` has type `int`.

Comparison of three structures:

| Structure | What does it hold? | Typical usage |
|---|---|---|
| `int[]` | Sequence of primitive `int` elements | Size known at creation, indexed access, numeric computation |
| `List<Integer>` | Sequence of references to `Integer` wrappers | Collection API, supports add/remove if the implementation allows it |
| `List<int[]>` | Sequence of `int[]` array objects | Multiple data batches of integer arrays |

When converting `int[]` to `List<Integer>`, use `Arrays.stream(array).boxed().toList()` for read-only needs, or `Arrays.stream(array).boxed().collect(java.util.stream.Collectors.toCollection(ArrayList::new))` when you need a list supporting add/remove. This conversion must box each element; you cannot cast directly via `(List<Integer>) array`.

Conversely, from `List<Integer>` you can build `int[]` with `list.stream().mapToInt(Integer::intValue).toArray()`, though **any null element will cause an error when unboxed to primitive**.

## 6. Null: An Important Difference Between Primitives and Wrappers

A primitive `int` cannot hold `null`; a wrapper `Integer` can hold `null`. This is both an advantage for expressing “no value yet” and a source of bugs if unboxed accidentally.

Illustrative example, to be placed inside a method:

```java
Integer quantity = null;

// int q = quantity;         // Compiles, but throws NPE at runtime
boolean absent = quantity == null; // Safe, true
boolean zero = java.util.Objects.equals(quantity, 0); // Safe, false
```

Expressions such as `quantity + 1`, `quantity < 5`, or `int q = quantity` require unboxing, so when `quantity == null` they can throw `NullPointerException`. Merely declaring a wrapper and holding `null` does not throw; the error happens when it is used in a way that demands a primitive value.

The `Map<String, Integer>` scenario often catches developers off guard:

```java
Map<String, Integer> counts = new java.util.HashMap<>();
// int count = counts.get("missing"); // get returns null -> auto-unboxing causes NPE
int count = counts.getOrDefault("missing", 0);
```

`getOrDefault` uses the default value if the key is absent; for the empty map example, `count = 0`. **Exception to remember:** if the map actually contains a mapping from that key to `null`, `getOrDefault` returns `null`, and assigning to `int` can still throw NPE. When null is a valid state, handle it explicitly:

```java
Integer maybeCount = counts.get("key");
int safeCount = maybeCount == null ? 0 : maybeCount;
```

These two map examples are illustrative snippets requiring `Map` imported and placement inside a method. API design should clearly specify **what null means**: missing record, unassigned, or invalid data. Do not automatically treat `0` and `null` as equivalent in every business domain.

## 7. Comparing Wrappers: `==`, `equals()`, and Unboxing

With primitives, `int a = 5; int b = 5; a == b` compares **numeric values**. With two variables of wrapper reference type `Integer`, `a == b` is usually a **reference comparison**, not a numeric equality check.

Java caches certain common boxed values (for example, `Integer.valueOf` must reuse instances for a specified small range); implementations may cache additional values. Thus testing `Integer a = 127; Integer b = 127; a == b` can yield `true` yet does not prove `==` works for comparing all numbers. **Do not rely on wrapper object identity to compare contents.**

Prefer:

- `Objects.equals(a, b)` if wrapper variables might be null and value comparison is needed.
- `a.equals(b)` if `a` is guaranteed non-null.
- `a.intValue() == b.intValue()` if primitive comparison is needed and both are guaranteed non-null.

**Caution:** in an expression mixing a wrapper and a primitive, such as `Integer a = 5; boolean same = a == 5;`, conversion rules unbox `a` to compare primitive values. The behavior of `==` depends on **the types of both operands**, so there is no universal rule that “`==` on Integer always compares addresses”. If `a` is null, this unboxing expression throws NPE.

Wrappers are immutable. For example, `Integer count = 1; count++;` compiles to logic roughly equivalent to “unbox, add 1, then box/reassign”; incrementing does not modify the old `Integer` object.

## 8. Autoboxing Has Costs: Choose Data Structures According to Need

Wrappers are useful because `List<E>`, `Map<K, V>`, and standard generic APIs operate on reference types; in return, a numeric collection typically needs **references to wrapper objects**, along with boxing/unboxing in many operations. This can cost memory, allocations, and CPU, especially in large loops or hot data paths. The JVM has optimizations such as caching and escape analysis, so **you cannot conclude every boxing operation always allocates a new object**, nor deduce exact cost from syntax alone.

Choose the tool based on the situation:

| Need | Choice | Meaning |
|---|---|---|
| Integrating `List`, `Map`, or standard generic APIs | `Integer`, `Long`, `Double`, etc. | Follows reference-type type arguments |
| Storing a fixed-size sequence of integers and indexing | `int[]` | Primitive element storage, no per-element wrapper needed |
| Computing numeric sequences from arrays/numeric sources | `IntStream`, `LongStream`, `DoubleStream` | Stream APIs specialized for primitives |
| An optional single numeric value | `OptionalInt`, `OptionalLong`, `OptionalDouble` when suitable | Represents optional values without `Optional<Integer>` |
| Needing an add/remove list or broad collection API | `ArrayList<Integer>` or a matching collection | Flexible, though uses wrappers |
| Passing multiple numeric arrays in batches | `List<int[]>` | Each list element is a primitive array |

`IntStream` and `OptionalInt` are **specialized APIs** and do not make `List<int>` valid syntax. For example, `IntStream.range(1, 5).sum()` computes `1 + 2 + 3 + 4 = 10` using a primitive stream. If you eventually need `List<Integer>`, call `.boxed()` to switch to a wrapper stream.

Some generic signatures have bounded type parameters:

```java
static <N extends Number> double twice(N value) {
    return value.doubleValue() * 2;
}
```

This is an illustrative method to be placed inside a class. `twice(3)` is valid because `3` is boxed to `Integer`, which is a subtype of `Number`; `twice(2.5)` uses `Double`. The `Number` bound **does not allow substituting primitive `int` for `N`**; it only accepts appropriate reference types.

In performance-critical computation, benchmark with real data and JVM conditions before optimizing. Do not replace every `List<Integer>` with arrays if the design requires collection features.

## 9. Common Mistakes and How to Fix Them

**Mistake 1 — Passing a primitive directly as a type argument.**

```java
List<int> values;       // Invalid type parameter syntax
List<Integer> values;   // Valid (shown as an alternative, do not declare twice in the same scope)
```

Fix: use wrapper `Integer`, or consider `int[]`/`IntStream` for pure numeric operations. Similarly, `Map<String, boolean>` must be changed to `Map<String, Boolean>`.

**Mistake 2 — Thinking `List<Integer>` directly holds raw `int` slots.** The list stores references of type `Integer`; boxing/unboxing is inserted at compile time where required. Syntactic convenience does not erase the runtime difference.

**Mistake 3 — Unboxing `null` without checking.** `Integer count = null; int n = count;` compiles yet throws `NullPointerException` at runtime. Check for null or design APIs to avoid unwanted null values.

**Mistake 4 — Using `==` to compare two wrappers.** This can yield results dependent on caching and object identity. Use `Objects.equals(left, right)` for null-safe comparison or `.equals()` when the object is definitely non-null.

**Mistake 5 — Mistaking `Arrays.asList(intArray)` for a list of numbers.** With `int[] array = {1, 2, 3};`, `Arrays.asList(array)` creates **one element of type `int[]`**, not three `Integer`s. Use `Arrays.stream(array).boxed().toList()` when you want a wrapper for each value.

**Mistake 6 — Mistaking `List<Integer>.remove(1)` for removing the number `1`.** Passing primitive `int` selects `remove(int index)`; to remove the value `1`, call `remove(Integer.valueOf(1))` (the `remove(Object)` overload). Watch out for out-of-bounds indices.

**Mistake 7 — Assuming a wrapper collection accepts any compatible numeric type.** `List<Integer>` is not `List<Long>`, and `Integer` does not automatically convert to `Long` via boxing. If multiple numeric types are needed, choose an API for `Number` or an appropriate generic bound; if type conversion is needed, perform it intentionally.

**Mistake 8 — Forgetting that `Stream.toList()` is unmodifiable.** The list returned by `Arrays.stream(raw).boxed().toList()` does not allow `add`, `remove`, or `set`. If modification is required, construct `new ArrayList<>(result)` or use a collector creating an `ArrayList`.

**Mistake 9 — Using `Optional<Integer>` for every numeric operation even when generic APIs are unnecessary.** Where an optional single number is needed, `OptionalInt` can express intent better and avoid wrapping elements in `Integer`. However, `OptionalInt` does not replace every place expecting `Optional<T>` or `List<T>`: each type has a distinct API.

**Mistake 10 — Assuming `int[]` is forbidden in generics because its elements are primitives.** An array itself is a reference type, so `List<int[]>` is valid. However, it is a list of *arrays*, not a list of *numbers*.

## 10. Self-Check Questions with Answers

1. **Why is `List<int>` invalid?** Because `int` is a primitive, whereas type arguments in Java 17 generic APIs must be reference types. Use `List<Integer>` when a collection is needed.
2. **Does `Integer x = 7;` require `new Integer(7)`?** No. The compiler inserts appropriate boxing; in modern Java code, prefer the simple syntax or `Integer.valueOf`, and avoid deprecated wrapper constructors.
3. **In `List<Integer> list = new ArrayList<>(); list.add(5);`, what conversion happens?** The value `5` is autoboxed to `Integer` to call `add`.
4. **What happens in `int number = list.get(0);`?** The `Integer` result is unboxed to `int`. If the element is `null`, there is a risk of NPE.
5. **Is `List<int[]>` valid?** Yes. `int[]` is a reference type pointing to an array, even though individual elements inside the array are primitives.
6. **How many elements does `Arrays.asList(new int[]{1, 2})` have?** One: the sole element is the `int[]` object; it does not auto-box each array element.
7. **What is needed to turn `int[]` into `List<Integer>`?** `Arrays.stream(array).boxed().toList()` is the concise Java 17 approach. If the list must be modifiable, create `new ArrayList<>(...)`.
8. **Does `Integer maybe = null; boolean b = maybe == null;` fail?** No; comparing with `null` here does not unbox. However, `maybe == 0` can throw NPE because it requires unboxing.
9. **Why should `Integer a = 1000; Integer b = 1000; a == b` not be used to check value equality?** The two wrappers may be two distinct references. Use `Objects.equals(a, b)`.
10. **When processing large amounts of numeric data, are there alternatives to `List<Integer>`?** Yes: `int[]`, `IntStream`, or suitable specialized structures; benchmark real performance before deciding.

Remember: **primitives supply basic numeric/boolean values; wrappers bring those values into the world of objects and generic APIs; autoboxing/unboxing bridges the two worlds yet can introduce null errors and overhead.** Whenever you see `List<Integer>`, remember it is a generic over a **reference type**, even though calling code often writes literals concisely like primitives.
