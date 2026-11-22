# Array Constructor References with `Type[]::new` in Java

**`Type[]::new`** is the *array constructor reference* syntax. It lets you pass "how to create an array of a length supplied later" as a function, instead of writing the lambda `size -> new Type[size]` at every usage site.

Typical example:

~~~java
String[] names = java.util.stream.Stream.of("An", "Bình", "Chi")
        .toArray(String[]::new);
~~~

Here, `String[]::new` specifies **the array type to create**; the `Stream.toArray` API allocates the required size and places the stream's elements into the resulting array. The return type is `String[]`, not `Object[]`.

## 1. Syntax and target functional type

An array constructor reference must be used where Java knows the *target type* is a functional interface with a matching signature. The most common target type is `IntFunction<T[]>` in the `java.util.function` package.

~~~java
import java.util.function.IntFunction;

IntFunction<String[]> newStrings = String[]::new;
// Equivalent in effect to:
IntFunction<String[]> same = length -> new String[length];
~~~

**The two snippets above are illustrative inside a method; they are not a standalone Java file.**

The abstract signature of `IntFunction<R>` is `R apply(int value)`. For `IntFunction<String[]>`, the signature after substituting the type argument is:

~~~java
String[] apply(int length);
~~~

Therefore:

- `Type` is the element type used to declare the array (for example `String`, `Integer`, `Order`, `int`).
- `[]::new` is a **reference to the array creation operation**, not creating an array at declaration time.
- When `factory.apply(n)` is called, the corresponding operation creates a `new Type[n]` array.
- The value `n` is the **length**, not an element. This reference does not copy data into the array by itself.
- The new array contains default values: `null` for reference elements, `0` for `int`, `false` for `boolean`, etc.

This syntax also applies to primitive element arrays, such as `int[]::new`, when the target type is `IntFunction<int[]>`. However, some general APIs, like `Stream<T>.toArray(IntFunction<A[]>)`, require the array element type to be a reference type `A`; creating `int[]` with `IntFunction<int[]>` does not turn a `Stream<Integer>` into an `IntStream`.

## 2. Standalone runnable example: creating arrays of a given length

Create the file `ArrayConstructorReferenceDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;

public class ArrayConstructorReferenceDemo {
    public static void main(String[] args) {
        IntFunction<String[]> strings = String[]::new;
        String[] slots = strings.apply(3);
        slots[1] = "Bình";

        IntFunction<int[]> integers = int[]::new;
        int[] scores = integers.apply(2);

        String[] empty = strings.apply(0);

        System.out.println("slots=" + Arrays.toString(slots));
        System.out.println("scores=" + Arrays.toString(scores));
        System.out.println("empty length=" + empty.length);
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac --release 17 ArrayConstructorReferenceDemo.java
java ArrayConstructorReferenceDemo
~~~

Output:

~~~text
slots=[null, Bình, null]
scores=[0, 0]
empty length=0
~~~

Key point: `String[]::new` is not a constructor for a single `String`. If you want to create a `String` object, that is a different syntax, such as `String::new` with a compatible functional interface. `String[]::new` always creates an **array of Strings**.

## 3. Primary application: `Stream.toArray(Type[]::new)`

The `Stream<T>` API has two overloads worth distinguishing:

| Call | Result | When to use |
| --- | --- | --- |
| `stream.toArray()` | `Object[]` | When you genuinely want an `Object[]` array. |
| `stream.toArray(String[]::new)` | `String[]` | When you want a typed array and elements are compatible with `String`. |
| `stream.toArray(Integer[]::new)` | `Integer[]` | When the data matches `Integer` elements. |

Complete example, file `StreamArrayDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamArrayDemo {
    public static void main(String[] args) {
        String[] result = Stream.of("An", "Bình", "Chi")
                .filter(s -> s.length() >= 2)
                .map(s -> s + "!")
                .toArray(String[]::new);

        Object[] generic = Stream.of("A", "B").toArray();
        String[] fromList = List.of("Đà Nẵng", "Hà Nội")
                .toArray(String[]::new);

        System.out.println(Arrays.toString(result));
        System.out.println(generic.getClass().getTypeName());
        System.out.println(Arrays.toString(fromList));
    }
}
~~~

~~~bash
javac --release 17 StreamArrayDemo.java
java StreamArrayDemo
~~~

Output:

~~~text
[An!, Bình!, Chi!]
java.lang.Object[]
[Đà Nẵng, Hà Nội]
~~~

`Stream.toArray(IntFunction<A[]>)` supplies the array generator with an integer representing the required array size. This lets the library manage array allocation itself. For a stream with an *encounter order*, the `toArray` result preserves element order. Do not assume the generator is always called exactly once or that every stream implementation calls it at the same time; rely only on the API contract.

In Java, if you only call `Stream<String>.toArray()`, knowing the element type is `String` **does not** change the runtime type of the returned array: it is still `Object[]`. Do not cast `(String[]) stream.toArray()`; that cast can throw `ClassCastException` because the actual array type is not `String[]`.

## 4. Using with `Collection.toArray(IntFunction<T[]>)`

Since Java 11, the `Collection` interface has the overload `<T> T[] toArray(IntFunction<T[]> generator)`. Because `List` is a `Collection`, you can write:

~~~java
List<String> labels = List.of("đỏ", "xanh");
String[] colors = labels.toArray(String[]::new);
~~~

This is an **illustrative snippet** placed inside a method with `java.util.List` imported. Other ways for the same purpose are `labels.toArray(new String[0])` or `labels.toArray(new String[labels.size()])`.

There is a subtle difference from `Stream.toArray`: the default implementation of `Collection.toArray(IntFunction)` calls the generator with **0** and passes the resulting array to the `toArray(T[])` overload to collect elements. Therefore, **do not rely on the generator receiving `collection.size()`**. Implementations may override this; the contract to care about is that the resulting array has the right contents and type. This explains why `String[]::new` fits: it can create an array of any non-negative length.

Do not confuse these two overloads:

- `Stream.toArray(String[]::new)`: accumulates elements from **a stream pipeline**.
- `Collection.toArray(String[]::new)`: extracts elements from **an existing collection**.

Both provide a typed array and do not mutate the element objects. This creates a new array; if elements are mutable objects, the array and the collection/stream still point to **the same element objects** (it is not a deep copy).

## 5. Reusing with generic methods

A major benefit is not having to write `new T[size]` inside a generic method. Java does not allow creating a new array directly with an unreified type parameter:

~~~java
// Illustrative snippet that DOES NOT compile:
static <T> T[] broken(int size) {
    return new T[size]; // generic array creation
}
~~~

Instead, **the caller supplies a factory for the concrete array type**. File `GenericArrayFactoryDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;
import java.util.stream.Stream;

public class GenericArrayFactoryDemo {
    static <T> T[] collectToArray(
            Stream<T> source, IntFunction<T[]> arrayFactory) {
        return source.toArray(arrayFactory);
    }

    public static void main(String[] args) {
        String[] words = collectToArray(
                Stream.of("Java", "Lambda"), String[]::new);

        Integer[] numbers = collectToArray(
                Stream.of(1, 2, 3), Integer[]::new);

        System.out.println(Arrays.toString(words));
        System.out.println(Arrays.toString(numbers));
    }
}
~~~

~~~bash
javac --release 17 GenericArrayFactoryDemo.java
java GenericArrayFactoryDemo
~~~

Output:

~~~text
[Java, Lambda]
[1, 2, 3]
~~~

The caller specifies `String[]::new` or `Integer[]::new`, letting the library know the exact runtime array type. The element type `T` in the generic signature is still subject to *type erasure*; it is the concrete factory that creates an array object with a real component type.

This is also why you cannot write `T[]::new` inside an arbitrary generic method; instead, pass `IntFunction<T[]>` from a site where the concrete type is known. Avoid using `(T[]) new Object[size]` to "work around" the error: that cast does not turn `Object[]` into `String[]` at runtime and easily causes `ClassCastException` at the usage site.

## 6. Multidimensional arrays: `Type[][]::new`

The reference `String[][]::new` adapts to `IntFunction<String[][]>`, creating the outer array (an array holding references to `String[]` arrays). It is equivalent in meaning to `length -> new String[length][]`, **not automatically creating all the inner rows**.

File `MatrixFactoryDemo.java`:

~~~java
import java.util.Arrays;
import java.util.function.IntFunction;

public class MatrixFactoryDemo {
    public static void main(String[] args) {
        IntFunction<String[][]> outerFactory = String[][]::new;
        String[][] rows = outerFactory.apply(2);

        System.out.println("rows=" + rows.length);
        System.out.println("first row null=" + (rows[0] == null));

        rows[0] = new String[] {"A", "B"};
        rows[1] = new String[] {"C"};

        System.out.println(Arrays.deepToString(rows));
    }
}
~~~

~~~bash
javac --release 17 MatrixFactoryDemo.java
java MatrixFactoryDemo
~~~

Output:

~~~text
rows=2
first row null=true
[[A, B], [C]]
~~~

If you need a true rectangular array, you can create it with `new String[rows][columns]` inside a suitable lambda or factory method. The `String[][]::new` syntax only accepts **one length** from an `IntFunction`-like interface; it does not represent a factory needing both dimensions.

Some valid target type examples:

| Reference | Matching functional interface | Result of `apply(4)` |
| --- | --- | --- |
| `String[]::new` | `IntFunction<String[]>` | `new String[4]` |
| `int[]::new` | `IntFunction<int[]>` | `new int[4]` |
| `Person[]::new` | `IntFunction<Person[]>` | `new Person[4]`, requires `Person` type. |
| `String[][]::new` | `IntFunction<String[][]>` | `new String[4][]`; four rows initially `null`. |

## 7. Target types and common compile errors

### Missing target type

Method/constructor references are *poly expressions*. The following expressions are **invalid** because they lack a functional interface as a target type:

~~~java
// Does not compile:
var factory = String[]::new;
Object factory2 = String[]::new;
~~~

You must write explicitly:

~~~java
java.util.function.IntFunction<String[]> factory = String[]::new;
~~~

Or use a context that already has an expected parameter type, such as `stream.toArray(String[]::new)`.

### Choosing the wrong functional interface

`Supplier<String[]>` has the signature `() -> String[]` (taking no length), so it does not match `String[]::new`, which requires an `int`. If you want an array always of length 10, use a lambda that supplies the size explicitly:

~~~java
java.util.function.Supplier<String[]> fixed = () -> new String[10];
~~~

Meanwhile, `IntFunction<String[]>` represents a caller-determined size, suitable for many dynamic array-creation APIs.

### Confusing primitive arrays with wrapper arrays

`int[]` is different from `Integer[]`:

- `int[]::new` creates an array of primitive `int`s.
- `Integer[]::new` creates an array of `Integer` object references.
- `IntStream.range(1, 4).toArray()` returns `int[]`; this is the dedicated API for primitive streams.
- `Stream<Integer>.toArray(Integer[]::new)` returns `Integer[]`; you cannot use `int[]::new` to satisfy the `IntFunction<A[]>` parameter of that overload.

For streams of primitive numbers, prefer `IntStream`, `LongStream`, `DoubleStream` and their dedicated `toArray()` APIs when appropriate, avoiding unnecessary boxing.

### Wrong element type at runtime

Java checks element types when storing into an array at runtime. The following example **intentionally causes an error**:

~~~java
// Illustrative snippet inside a method, after importing Stream.
java.util.stream.Stream<Object> mixed =
        java.util.stream.Stream.of("hợp lệ", 42);

// May compile, but 42 cannot be stored into String[]:
// String[] wrong = mixed.toArray(String[]::new);
// Running the line above will throw ArrayStoreException.
~~~

The generic type `A` of the `Stream.toArray(IntFunction<A[]>)` overload is inferred from the generator, and is not necessarily constrained by the compiler so that every actual value in the stream is assignable to `A`. Do not use a generator of a narrower type than the data that can flow through the pipeline.

### Invalid size

The expression `String[]::new` itself is valid; when executing `factory.apply(-1)`, the corresponding array creation throws `NegativeArraySizeException`. A size that is too large can throw `OutOfMemoryError` or an array length limit error depending on the JVM. Do not create arrays from untrusted sizes without enforcing business and memory limits.

## 8. When to use it, and what to remember

**Use `Type[]::new`** when an API needs a size-accepting callback to create a properly typed array, especially `Stream.toArray`, `Collection.toArray`, or generic helpers with an `IntFunction<T[]>` parameter. It is concise, strongly typed, and delegates size determination to the calling API.

**Use `size -> new Type[size]`** when you need extra logic before/after array creation, such as validating the size or creating an array with special conditions. In pipelines, prefer a side-effect-free generator; do not depend on how many times or in what order it is called.

**Do not create arrays just for syntactic convenience.** If you still need to add/remove elements frequently, a `List` may be more suitable; convert to an array only at API boundaries that require an array. Arrays have fixed length; creating a new one allocates memory proportional to the element count, and copying references into an array does not mean a deep copy.

Checklist when reading or writing `Type[]::new`:

1. Does the target functional interface have **exactly one `int` size parameter** and return a matching array type?
2. Is the required runtime type `String[]`, `Integer[]`, `int[]`, or a multidimensional array?
3. When does the API invoke the generator, and what guarantees exist on the size or call count?
4. Can every element actually be stored in the array's component type?
5. For generic methods, have you let the caller pass a concrete factory instead of trying `new T[n]`?
6. If using multidimensional arrays, have you allocated the necessary inner arrays?

**Technical conclusion:** `Type[]::new` is the constructor-reference version of `size -> new Type[size]` in a suitable functional interface context. It is especially useful for converting `Stream<T>` or `Collection<T>` into an array of the **correct runtime type**, while avoiding invalid generic array creation and unsafe `Object[]` casts.