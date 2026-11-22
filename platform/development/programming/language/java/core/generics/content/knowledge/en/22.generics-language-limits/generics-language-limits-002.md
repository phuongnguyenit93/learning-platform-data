# Disallowing Primitives as Type Arguments in Java Generics

## 1. Core rule and common issue

In Java Generics, **a *type argument* must be an appropriate reference type, not a *primitive type***. Therefore, these declarations are **invalid**:

```java
// INTENTIONALLY DOES NOT COMPILE – illustrates invalid cases:
List<int> numbers;
Set<boolean> flags;
Map<int, double> prices;
Optional<long> count;
```

`int`, `boolean`, `double`, and `long` are primitive types. They cannot appear directly inside `<...>` as a type argument of a generic class or interface.

Instead, Java provides **wrapper classes** such as `Integer`, `Boolean`, `Double`, and `Long`:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

class ValidDeclarations {
    List<Integer> numbers;
    Set<Boolean> flags;
    Map<Integer, Double> prices;
    Optional<Long> count;
}
```

This snippet is a valid class illustrating declarations; it has no `main`.

Keep three points in mind immediately:

1. **`List<int>` is invalid**, **`List<Integer>` is valid**: `Integer` is a class, not the primitive `int`.
2. **Autoboxing/unboxing** lets you write code with `Integer` similarly to `int`, but these are real conversions with consequences for `null`, equality comparison, and performance.
3. **Not everything containing `int` is forbidden in generics**: `int[]` is a **reference array type**, so `List<int[]>` is completely valid.

This lesson does more than ask you to memorize wrapper names: it helps you choose the right storage representation and understand subtle bugs that can arise when using Generics with numeric data.

## 2. Primitive types and their corresponding wrapper classes

Java has eight primitive types. Each primitive has a wrapper class in `java.lang`:

| Primitive | Wrapper | Example as a type argument |
|---|---|---|
| `byte` | `Byte` | `List<Byte>` |
| `short` | `Short` | `List<Short>` |
| `int` | `Integer` | `List<Integer>` |
| `long` | `Long` | `List<Long>` |
| `float` | `Float` | `List<Float>` |
| `double` | `Double` | `List<Double>` |
| `char` | `Character` | `List<Character>` |
| `boolean` | `Boolean` | `List<Boolean>` |

These wrappers are **reference classes** and can serve as type arguments:

```java
java.util.List<Integer> ids = new java.util.ArrayList<>();
java.util.List<Character> letters = new java.util.ArrayList<>();
java.util.List<Boolean> enabled = new java.util.ArrayList<>();
```

Whereas the following forms are invalid:

```java
// INTENTIONALLY DOES NOT COMPILE:
java.util.List<int> ids;
java.util.List<char> letters;
java.util.List<boolean> enabled;
```

The two type groups serve different roles:

- Primitives store and operate on values with primitive semantics.
- Wrappers are reference objects (or `null`) that have methods, participate in class/interface inheritance, and are valid type arguments.

Wrappers do not make `int` a subclass of `Object`. `Integer` is the class that extends `Number` and indirectly `Object`.

## 3. Why does the language impose this limit?

Standard Java Generics relies on **type erasure** to maintain a single class/bytecode model shared across multiple type arguments. An `ArrayList<String>` and an `ArrayList<Integer>` use the same generic class at runtime, rather than the JVM generating a specialized class for each type argument.

Given:

```java
class Box<T> {
    T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

If type variable `T` has no explicit bound, the erasure of `T` is `Object`. Bytecode representing fields and methods can operate through the `Object` reference type, and the compiler inserts the necessary casts where specific types are used.

The primitive `int` **is not a reference type** and cannot be used as an instance of `Object` without converting to a wrapper. Consequently, a generic API designed around reference type variables does not allow passing `int` directly for `T`.

In other words, you cannot assume that:

```java
Box<int> counter; // INTENTIONALLY INVALID.
```

would produce a `Box` storing a primitive `int` as efficiently as an `int` field. Standard Java Generics **does not *specialize*** the `Box` class for primitives using that syntax.

Instead:

```java
Box<Integer> counter = new Box<>(10);
```

is accepted by the compiler: `10` is converted to `Integer` where the context requires a wrapper.

**This limitation applies at the *type argument* position.** It does not forbid using primitives as ordinary method parameters, fields of non-generic classes, return types, or elements of primitive arrays.

## 4. Contrast: primitives in methods are valid, primitives in `<...>` are invalid

These two situations are easily confused:

```java
class Arithmetic {
    int doubleIt(int value) {
        return value * 2;
    }

    java.util.List<Integer> asList(int value) {
        return java.util.List.of(value);
    }
}
```

The class above is valid:

- `doubleIt` takes and returns `int` directly, with no type argument involved.
- `asList` takes `int` but returns `List<Integer>`. The generic method `List.of` infers the wrapper `Integer` in the appropriate context and boxing happens when passing the element.

By contrast:

```java
// INTENTIONALLY DOES NOT COMPILE:
class Broken<T extends int> { }
```

`T extends int` is invalid because `int` is not a reference type usable as a bound. If you need to restrict to numeric wrappers, you can write `<T extends Number>`:

```java
class NumericBox<T extends Number> {
    T value;
}
```

Then `NumericBox<Integer>` and `NumericBox<Double>` are valid; `NumericBox<int>` remains invalid.

## 5. Runnable Java 17 example: `List<Integer>` instead of `List<int>`

Create the file **`WrapperListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WrapperListDemo {
    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();

        scores.add(8);
        scores.add(9);
        scores.add(10);

        int total = 0;

        for (int score : scores) {
            total += score;
        }

        System.out.println(scores);
        System.out.println(total);
        System.out.println(scores.get(0) + 2);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac WrapperListDemo.java
java WrapperListDemo
```

Stdout:

```text
[8, 9, 10]
27
10
```

Explanation:

1. `scores` is declared as `List<Integer>`, **not** `List<int>`.
2. `scores.add(8)` works via **boxing**: an `int` value is converted to an `Integer` wrapper where needed.
3. The `for (int score : scores)` loop reads each `Integer` and **unboxes** it into `int`.
4. `total` is an `int`, so additions use standard integer arithmetic.
5. `scores.get(0) + 2` requires a numeric value; `Integer` can be unboxed to evaluate to `10`.

This code is generically type-checked at compile time. If you try `scores.add("text")`, the compiler rejects it because `String` is incompatible with `Integer`.

## 6. How do autoboxing and unboxing work?

**Boxing conversion** converts a primitive value into its corresponding wrapper type in contexts permitted by Java.

**Unboxing conversion** converts a wrapper into its corresponding primitive value.

For example:

```java
Integer boxed = 42; // Boxing from int to Integer.
int primitive = boxed; // Unboxing from Integer to int.
```

You can view an illustrative near-equivalent representation:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed.intValue();
```

The compiler may emit the corresponding helper calls and optimize them based on context. The snippet above illustrates the semantics, **not a guarantee of the exact bytecode instructions across all JDK/JIT versions**.

### Program to observe conversions

Create **`BoxingConversionDemo.java`**:

```java
public class BoxingConversionDemo {
    public static void main(String[] args) {
        int original = 21;

        Integer boxed = original;
        int restored = boxed;

        Double pi = 3.5;
        double doubled = pi * 2;

        Boolean enabled = true;
        boolean active = enabled;

        System.out.println(boxed);
        System.out.println(restored);
        System.out.println(doubled);
        System.out.println(active);
    }
}
```

Commands:

```bash
javac BoxingConversionDemo.java
java BoxingConversionDemo
```

Stdout:

```text
21
21
7.0
true
```

With `Double pi = 3.5`, the compiler selects the `Double` wrapper from the `double` literal. When computing `pi * 2`, the operation requires a primitive numeric value, so unboxing occurs; the result type is `double`.

These conversions make generic APIs convenient, but they are **not semantically free**: wrappers can be `null`, have reference identity, and may have different storage costs than primitives.

## 7. `null` is a special hazard during unboxing

A primitive `int` cannot hold `null`. `Integer` is a reference type, so it can be `null`.

For example:

```java
Integer count = null;
// int total = count; // Can throw NullPointerException.
```

This is not a compiler error; assigning to `int` compiles cleanly and then fails at runtime if `count == null`.

Create the file **`UnboxingNullDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class UnboxingNullDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        values.add(10);
        values.add(null);

        System.out.println(values.size());
        System.out.println(values.get(0));

        try {
            int number = values.get(1);
            System.out.println(number);
        } catch (NullPointerException ex) {
            System.out.println("NullPointerException");
        }
    }
}
```

Compile/run:

```bash
javac UnboxingNullDemo.java
java UnboxingNullDemo
```

Stdout:

```text
2
10
NullPointerException
```

`ArrayList<Integer>` can contain `null`. When `values.get(1)` is used in an `int` position, the compiler inserts unboxing, and a `null` reference cannot be dereferenced to extract a primitive.

Not every collection permits `null`:

- `new ArrayList<Integer>()` allows `null`.
- `List.of(1, null)` throws `NullPointerException` immediately upon list creation.
- `List.copyOf` rejects `null` in the source.

**Good practice:** Decide explicitly whether `null` is a valid value in your data contract. If not, validate or use collections/factories that prohibit `null`. If so, handle `null` before unboxing.

## 8. Wrappers are not primitives: comparing with `==` vs `equals`

A notable difference is that `Integer` is a reference object.

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b));
```

This prints `true`, because both objects represent the same numeric value.

However, `a == b` when **both variables are wrapper references** checks **whether they are the same object**, not numeric equality. You should not rely on whether the JVM caches certain wrapper values to draw any universal conclusion.

In particular, for `Integer` values in a small range, Java's boxing/caching rules and implementation make some `==` checks accidentally return `true`; outside that range, identity behavior should not be treated as a contract. Use `.equals(...)` or compare primitives after handling `null`.

File **`WrapperEqualityDemo.java`**:

```java
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer first = 1000;
        Integer second = 1000;

        System.out.println(first.equals(second));
        System.out.println(Objects.equals(first, second));
        System.out.println(first.intValue() == second.intValue());

        Integer absent = null;
        System.out.println(Objects.equals(absent, null));
    }
}
```

Compile/run:

```bash
javac WrapperEqualityDemo.java
java WrapperEqualityDemo
```

Stdout:

```text
true
true
true
true
```

The example intentionally **does not print `first == second`** to avoid encouraging reliance on wrapper identity. When you care about value equality, use `.equals` or `Objects.equals` when `null` is possible; when you care about primitive values and know they are non-null, unbox and compare primitives.

You should also avoid mixing nullable `Integer` values into expressions with `int` literals without considering unboxing. For example, `Integer x = null; boolean zero = (x == 0);` can throw `NullPointerException`.

## 9. Type inference with primitives: the compiler usually chooses wrappers

A generic method declares a type parameter `T`:

```java
static <T> T identity(T value) {
    return value;
}
```

When calling:

```java
Integer result = identity(123);
```

the compiler does not infer `T = int` as an invalid primitive type argument. In an appropriate context, it applies boxing and infers a reference type—here `Integer`.

Create the file **`GenericInferencePrimitiveDemo.java`**:

```java
import java.util.List;

public class GenericInferencePrimitiveDemo {

    static <T> T identity(T value) {
        return value;
    }

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    public static void main(String[] args) {
        Integer boxed = identity(7);
        int primitive = identity(7);

        List<Integer> numbers = singleton(9);

        System.out.println(boxed);
        System.out.println(primitive);
        System.out.println(numbers);

        System.out.println(numbers.get(0) + 1);
    }
}
```

Commands:

```bash
javac GenericInferencePrimitiveDemo.java
java GenericInferencePrimitiveDemo
```

Stdout:

```text
7
7
[9]
10
```

Explanation:

1. The generic method `<T> T identity(T value)` requires `T` to belong to the reference type system.
2. The literal `7` is an `int`, boxed to satisfy generic inference.
3. The result can be assigned to `Integer`; if assigned to `int`, unboxing provides the primitive value.
4. `singleton(9)` infers `T = Integer`, producing `List<Integer>`.

**The compiler never secretly creates `List<int>` under the hood.** Type arguments are always represented within the reference type system.

## 10. `List.of`, `Arrays.asList`, and the primitive array trap

When converting multiple integers into a `List<Integer>`, be careful if the source is an `int[]`.

Consider:

```java
int[] raw = {1, 2, 3};

var fromArray = java.util.Arrays.asList(raw);
```

`Arrays.asList` is a generic varargs method expecting **objects** as elements. `int[]` is a single array object; the primitive values **inside** the array are not automatically boxed into individual `Integer` elements when passing the whole `int[]` to varargs.

The result of `Arrays.asList(raw)` is a `List<int[]>` with **one element**—the `raw` array object itself—rather than a `List<Integer>` with three elements.

Create the file **`PrimitiveArrayListTrapDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveArrayListTrapDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};

        List<int[]> nested = Arrays.asList(raw);
        List<Integer> boxed = IntStream.of(raw)
                .boxed()
                .toList();

        System.out.println(nested.size());
        System.out.println(nested.get(0).length);
        System.out.println(boxed);
        System.out.println(boxed.size());
    }
}
```

Compile/run:

```bash
javac PrimitiveArrayListTrapDemo.java
java PrimitiveArrayListTrapDemo
```

Stdout:

```text
1
3
[1, 2, 3]
3
```

Key takeaways:

- `int[]` is a **reference type**, because arrays are objects; hence `List<int[]>` is valid.
- `Arrays.asList(raw)` places the entire `int[]` object into the list.
- `IntStream.of(raw).boxed()` creates a stream of `Integer` wrappers from the `int` values.
- `.toList()` (Java 16+) creates an unmodifiable list via the standard API; you should not call `add` on the result.

If you need a mutable `ArrayList<Integer>`, use `collect(Collectors.toCollection(ArrayList::new))` after `.boxed()` or construct `new ArrayList<>(boxed)`.

## 11. When `List<int[]>` is the right design

The primitive-generic limitation does not forbid using **primitive arrays as reference elements**.

For example:

```java
java.util.List<int[]> rows = new java.util.ArrayList<>();
rows.add(new int[] {1, 2});
rows.add(new int[] {3, 4});
```

This list has two elements of type `int[]`, not four elements of type `Integer`. It fits when each element is a block of integers, such as a matrix row or a data sample.

Standalone example **`PrimitiveArrayElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PrimitiveArrayElementDemo {
    public static void main(String[] args) {
        List<int[]> rows = new ArrayList<>();

        rows.add(new int[] {1, 2});
        rows.add(new int[] {3, 4, 5});

        for (int[] row : rows) {
            int sum = 0;

            for (int value : row) {
                sum += value;
            }

            System.out.println(sum);
        }
    }
}
```

Commands:

```bash
javac PrimitiveArrayElementDemo.java
java PrimitiveArrayElementDemo
```

Stdout:

```text
3
12
```

Each `row` is an array object holding primitive `int` values. Because `int[]` is a reference type, it can fill the type argument of `List`. The `int` values inside remain inside primitive arrays, avoiding per-element boxing at the array storage layer.

Also remember that the list **does not deep-copy** added arrays. If the caller mutates `rows.get(0)[0]`, the array's contents change as well.

## 12. The limit across different generic types

It is not only `List` that forbids primitive type arguments.

All of the following declarations are invalid:

```java
// INTENTIONALLY INVALID:
java.util.Set<char> letters;
java.util.Map<int, String> namesById;
java.util.function.Supplier<double> supplier;
java.util.Optional<boolean> present;
```

The valid versions:

```java
java.util.Set<Character> letters;
java.util.Map<Integer, String> namesById;
java.util.function.Supplier<Double> supplier;
java.util.Optional<Boolean> present;
```

The same applies to user-defined classes:

```java
class Pair<A, B> {
    A left;
    B right;
}
```

You can use `Pair<Integer, Double>`, but not `Pair<int, double>`.

This is a **rule of the type-argument system**, not a rule specific to the Java Collections Framework.

In addition, a generic method declaration:

```java
static <T> T first(T a, T b) {
    return a;
}
```

cannot be invoked with a primitive type witness:

```java
// INTENTIONALLY INVALID:
Utils.<int>first(1, 2);
```

If an explicit type witness is needed, use a reference type such as `<Integer>`, provided the method is validly accessible in real code.

## 13. Numeric wrappers and the common `Number` type

Numeric wrappers such as `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double` all extend `Number`, so a list of `Number` elements can hold multiple wrapper types.

File **`NumberCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NumberCollectionDemo {

    static double total(List<? extends Number> values) {
        double result = 0.0;

        for (Number number : values) {
            result += number.doubleValue();
        }

        return result;
    }

    public static void main(String[] args) {
        List<Number> mixed = new ArrayList<>();

        mixed.add(2);
        mixed.add(3.5);
        mixed.add(4L);

        System.out.println(mixed);
        System.out.println(total(mixed));
        System.out.println(total(List.of(1, 2, 3)));
    }
}
```

Compile/run:

```bash
javac NumberCollectionDemo.java
java NumberCollectionDemo
```

Stdout:

```text
[2, 3.5, 4]
9.5
6.0
```

The literals `2`, `3.5`, and `4L` can be boxed into `Integer`, `Double`, and `Long`; all are compatible with `Number`.

With `List<? extends Number>`, the `total` method only needs to **read** elements as `Number`, so it can accept `List<Integer>`, `List<Double>`, or `List<Number>`. This applies PECS (*Producer Extends*) to wrapper numbers.

**Do not mistake `List<Integer>` for a subtype of `List<Number>`.** Java Generics is invariant by default:

```java
List<Integer> integers = List.of(1, 2);
// List<Number> numbers = integers; // INTENTIONALLY INVALID.
List<? extends Number> readable = integers; // Valid.
```

The variable `readable` can read `Number` values, yet you cannot arbitrarily add a `Double` to a list that might actually be a `List<Integer>`.

## 14. Conversion trap: not every conversion occurs in a single boxing step

Some developers expect a generic wrapper to automatically support all numeric widenings just like primitives.

For example, `Long` and `Integer` are **two distinct wrapper classes**:

```java
java.util.List<Long> ids = new java.util.ArrayList<>();
ids.add(1L); // Valid.

// ids.add(1); // Invalid: int does not autobox to Long.
```

In `ids.add(1)`, the compiler does not automatically perform the chain "`int` -> `long` -> `Long`" merely because the target is `Long`; Java does not provide arbitrary widening-then-boxing combinations as an implicit conversion at this call site.

Fix with:

```java
ids.add(1L);
ids.add(Long.valueOf(1));
```

For a method expecting `Number`, boxing an `int` to `Integer` followed by reference widening to `Number` is permitted:

```java
java.util.List<Number> numbers = new java.util.ArrayList<>();
numbers.add(1); // Integer is a Number.
```

When encountering compiler errors with wrappers, distinguish **primitive widening**, **boxing**, **reference widening**, and the conversion combinations actually allowed by the JLS. Never assume every syntax that looks like a numeric conversion is valid.

## 15. Do wrappers affect performance and memory?

When storing millions of numeric values:

- `int[]` stores primitive `int` values inside a single array object.
- `List<Integer>` stores **references** to wrapper objects through an appropriate implementation—typically `ArrayList`, whose internal array holds references.
- Boxing may allocate wrapper objects or reuse cached objects depending on rules and implementation; you should not guess exact allocation counts from a single code snippet.
- Unboxing can add conversion work, and if the data contains `null`, it will trigger `NullPointerException`.
- In large computational loops, memory/cache/GC/boxing overhead can matter significantly; however, JIT optimizations can make actual behavior workload-dependent.

Therefore `List<Integer>` is not necessarily the best choice for storing huge quantities of primitive `int` values when memory density or raw throughput is the goal. Yet it is often the right choice when you need standard Collections APIs: dynamic resizing, `contains`, `Map`, interoperability with generic code, and so forth.

**Do not conclude "List is always slow"** solely because boxing exists. To optimize a numeric hot path, use a reliable benchmark such as JMH on a representative workload.

## 16. When processing primitives in bulk, use `IntStream`, `LongStream`, `DoubleStream`

The Java Stream API includes **primitive-specialized** variants:

- `IntStream` processes `int`.
- `LongStream` processes `long`.
- `DoubleStream` processes `double`.

They enable many numeric operations without representing data as `Stream<Integer>` or `List<Integer>` at every step.

Create the file **`PrimitiveStreamDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveStreamDemo {
    public static void main(String[] args) {
        int total = IntStream.rangeClosed(1, 4).sum();
        double average = IntStream.of(2, 4, 6)
                .average()
                .orElse(0.0);

        List<Integer> boxed =
                IntStream.of(3, 5, 7)
                        .boxed()
                        .toList();

        System.out.println(total);
        System.out.println(average);
        System.out.println(boxed);
    }
}
```

Compile/run:

```bash
javac PrimitiveStreamDemo.java
java PrimitiveStreamDemo
```

Stdout:

```text
10
4.0
[3, 5, 7]
```

`IntStream.sum()` returns `int`, while `average()` returns `OptionalDouble` because an average may be absent when the stream is empty.

`.boxed()` converts the primitive `int` stream into a `Stream<Integer>`; `.toList()` produces a list of wrappers that is unmodifiable via the standard API in Java 17. If you need to keep processing primitives, keep using the primitive stream until you truly need to transition to an object API.

**There is no `Stream<int>`.** The valid syntax is `IntStream`, or `Stream<Integer>` when you want to work with wrappers.

## 17. Primitive-specialized Optional and functional interfaces

The type-argument restriction also explains why Java provides many primitive-specialized APIs.

Examples:

| Goal | Generic reference API | Primitive-specialized API |
|---|---|---|
| Possibly absent integer value | `Optional<Integer>` | `OptionalInt` |
| Possibly absent double value | `Optional<Double>` | `OptionalDouble` |
| Possibly absent long value | `Optional<Long>` | `OptionalLong` |
| Parameterless function returning `int` | `Supplier<Integer>` | `IntSupplier` |
| Function taking `int` | `Consumer<Integer>` | `IntConsumer` |
| Predicate taking `int` | `Predicate<Integer>` | `IntPredicate` |
| Mapping `int` to `int` | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Function taking `int`, returning object `R` | `Function<Integer,R>` | `IntFunction<R>` |
| Function taking object `T`, returning `int` | `Function<T,Integer>` | `ToIntFunction<T>` |

Specialized types express primitives directly in the API signature and can avoid boxing/unboxing in certain operations.

File **`PrimitiveFunctionalDemo.java`**:

```java
import java.util.OptionalInt;
import java.util.function.IntPredicate;
import java.util.function.IntUnaryOperator;

public class PrimitiveFunctionalDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = n -> n * 2;
        IntPredicate positive = n -> n > 0;

        OptionalInt result = OptionalInt.of(twice.applyAsInt(6));

        System.out.println(result.getAsInt());
        System.out.println(positive.test(10));
        System.out.println(positive.test(-1));
    }
}
```

Compile/run:

```bash
javac PrimitiveFunctionalDemo.java
java PrimitiveFunctionalDemo
```

Stdout:

```text
12
true
false
```

`IntUnaryOperator` and `IntPredicate` accept and return primitive `int` by signature; they are **not** generic interfaces parameterized with `<int>`.

`OptionalInt` needs no type argument; it is already specialized for `int`. When absence is needed, `OptionalInt.empty()` represents it without using `null` as an `int` value.

## 18. When should you choose `Integer[]`, `int[]`, and `List<Integer>`?

All three are valid, but their semantics differ.

| Type | Elements | Size | Element-level `null` | Main contract |
|---|---|---|---|---|
| `int[]` | Primitive `int` | Fixed | Impossible | Primitive array, runtime knows component type `int` |
| `Integer[]` | Reference `Integer` | Fixed | Allowed | Reference wrapper array |
| `List<Integer>` | Reference `Integer` | Depends on implementation | Depends on implementation | Generic collection, rich utilities |
| `List<int[]>` | Reference to `int[]` object | Depends on implementation | Depends on implementation | Each element is a primitive array |
| `IntStream` | Stream of `int` values | Does not directly model mutable slots | No null elements | Integer processing pipeline |

**Need fixed slots and direct primitive storage?** `int[]` is usually the natural choice.

**Need Collection utilities, dynamic sizing, keys/values, or generic interoperability?** `List<Integer>` or wrapper containers fit well.

**Need grouped sequences of primitives?** `List<int[]>` may be right, though you must account for mutating inner arrays.

**Need a computation pipeline?** `IntStream` lets you describe numeric operations without converting all values into wrappers.

`Integer[]` differs from `int[]` in runtime component type, nullability semantics, and where boxing/unboxing occurs.

## 19. Data processing example: choosing a primitive array or a generic list

File **`PrimitiveVsWrapperStorageDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveVsWrapperStorageDemo {

    static int sumArray(int[] values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    static int sumList(List<Integer> values) {
        int sum = 0;
        for (Integer value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] primitive = {4, 5, 6};
        List<Integer> wrappers =
                new ArrayList<>(List.of(4, 5, 6));

        System.out.println(Arrays.toString(primitive));
        System.out.println(wrappers);
        System.out.println(sumArray(primitive));
        System.out.println(sumList(wrappers));

        wrappers.add(7);
        System.out.println(wrappers.size());
    }
}
```

Commands:

```bash
javac PrimitiveVsWrapperStorageDemo.java
java PrimitiveVsWrapperStorageDemo
```

Stdout:

```text
[4, 5, 6]
[4, 5, 6]
15
15
4
```

This example is not meant to measure speed. It only shows that:

- `sumArray` reads primitives directly.
- `sumList` unboxes `Integer` on every addition and needs a clear policy for `null`.
- `ArrayList` can grow dynamically, whereas an `int[]` array's length is fixed upon creation.

If a `null` element appears in `wrappers`, `sumList` can throw `NullPointerException`. That semantic difference matters more than the fact that both examples print `15` for valid data.

## 20. Do not confuse wrappers with the runtime `Class` of a primitive

`Integer.class` is the class token for the `Integer` wrapper reference type. The primitive type `int` has a valid class literal `int.class`, yet that **does not** make `int` a reference type usable with Generics.

A class token can represent a primitive type for reflection purposes, while generic type arguments remain constrained to reference types.

For example:

```java
System.out.println(int.class.isPrimitive());
System.out.println(Integer.class.isPrimitive());
```

Inside a Java method, these two lines print, respectively:

```text
true
false
```

**Key point:** Having a runtime/reflection `Class` object representing a primitive does not make `List<int>` valid syntax.

When writing an API requiring a runtime class token:

```java
static <T> T checkedCast(Object value, Class<T> type) {
    return type.cast(value);
}
```

`T` is still a reference generic type variable. `Class<T>` is not a mechanism that allows declaring `T = int` with a primitive type argument. If an API needs to handle `int` directly, use a primitive-specific signature or the `Integer` wrapper by design.

## 21. Common mistakes

**Mistake 1 — "`List<int>` is shorter to write than `List<Integer>`."** Invalid syntax. A type argument must be an appropriate reference type.

**Mistake 2 — "`int` extends `Number`."** False. `Integer` is a subclass of `Number`; the primitive `int` is not a class.

**Mistake 3 — "`List<Integer>` stores `int` directly like `int[]`."** No. Generic collections operate on wrappers at the API layer, whereas primitive arrays have component type `int`.

**Mistake 4 — "Boxing and unboxing are completely free."** That cannot be assumed. There can be object/conversion costs depending on code and runtime optimizations.

**Mistake 5 — "`Integer` cannot be `null` because it represents an `int`."** False. A wrapper is a reference type and can be `null`.

**Mistake 6 — "You can safely use `==` to compare the values of two `Integer`s."** When both operands are references, `==` tests identity, not numeric equality. Use `.equals` or compare primitives after checking for null.

**Mistake 7 — "`List<Integer>` is a `List<Number>` because `Integer` is a `Number`."** False. Java Generics is invariant; use an appropriate wildcard when an API only reads the supertype.

**Mistake 8 — "`Arrays.asList(int[])` returns a list of `Integer`s."** False. `int[]` is treated as a single reference element, typically producing a one-element `List<int[]>`.

**Mistake 9 — "`List<int[]>` is also forbidden because it contains `int`."** False. `int[]` is an **array reference type**, valid as a type argument.

**Mistake 10 — "`List<Long>` automatically accepts literal `1` because any number converts."** No. An `int` does not automatically convert through arbitrary widening-plus-boxing chains to `Long`; use `1L` when you want a `Long`.

**Mistake 11 — "`Optional<int>` is valid because `Optional` is for possibly absent values."** False. Use specialized `OptionalInt` or `Optional<Integer>`.

**Mistake 12 — "`Stream<int>` avoids boxing."** Invalid. Use `IntStream`, not a parameterized `Stream<int>`.

**Mistake 13 — "Type erasure means the compiler cannot check wrappers."** False. `List<Integer>` has strong compile-time type checking; the separate restriction is that primitive type arguments are unsupported.

**Mistake 14 — "Primitives cannot be used anywhere inside a generic class."** False. A generic class can still declare `int count`, take a `double rate` parameter, or use `int[]`; what is restricted is using primitives as *type arguments* or invalid type-variable bounds.

## 22. Self-check exercises with answers

**Question 1.** Which of the following declarations are valid?

```java
List<int> a;          // A
List<Integer> b;      // B
List<int[]> c;        // C
```

**Answer:** B and C are valid. A is invalid. The example requires importing `java.util.List` and placing it in a class/method.

**Question 2.** What conversions does `Integer x = 5; int y = x;` perform?

**Answer:** Boxing `int` to `Integer` in the first assignment and unboxing `Integer` to `int` in the second.

**Question 3.** At which stage does `Integer x = null; int y = x;` fail?

**Answer:** It compiles, but throws `NullPointerException` when unboxing at runtime.

**Question 4.** Is `List<Integer>` automatically assignable to `List<Number>`?

**Answer:** No; Java Generics is invariant. If only reading numbers, you can use `List<? extends Number>`.

**Question 5.** What is `Arrays.asList(new int[] {1,2,3}).size()`?

**Answer:** `1`, because an `int[]` array is treated as a single element object of the generic varargs call.

**Question 6.** How can you obtain a `List<Integer>` from an `int[]` on Java 17?

**Answer:** `Arrays.stream(source).boxed().toList()` or `IntStream.of(source).boxed().toList()`.

**Question 7.** Is `List<Long> ids = new ArrayList<>(); ids.add(1);` valid?

**Answer:** No. The literal `1` has type `int`; use `1L` or `Long.valueOf(1)`.

**Question 8.** How does `List<int[]>` store each value?

**Answer:** Each **List element** is an `int[]` array object, and the `int` values reside inside each of those arrays.

**Question 9.** When summing a large set of integers, why consider `int[]` or `IntStream`?

**Answer:** Because they support direct primitive operations and can avoid part of the boxing/unboxing cost. Always benchmark realistically before drawing performance conclusions.

**Question 10.** Why does `Integer.class` or `int.class` not make `List<int>` valid?

**Answer:** Reflection class tokens do not alter the language's type-argument rules; `int` remains a primitive type.

**Question 11.** What options exist for an optional primitive `int` value?

**Answer:** `OptionalInt` for a primitive-specialized API or `Optional<Integer>` when a generic wrapper API is needed.

**Question 12.** Should two wrappers be compared with `==` when business logic requires numeric equality?

**Answer:** No. Use `Objects.equals(a,b)` to handle nullable references or check for null and then compare primitives.

## 23. API design checklist for primitives

When designing a generic class or method, check:

1. **Is a type argument a primitive?** If so, replace it with a wrapper or pick a primitive-specialized API.
2. **Do you need a dynamically sized collection?** `List<Integer>`, `Set<Long>`, `Map<Integer,Double>` may fit well.
3. **Do you need dense primitive storage or heavy numeric arithmetic?** Consider `int[]`, `double[]`, `IntStream`, `DoubleStream`.
4. **Can `null` appear?** If wrappers are nullable, design the policy before unboxing.
5. **Are wrappers being compared with `==`?** If the intent is value equality, change to `.equals` or `Objects.equals`.
6. **Are you converting `int[]` to `List<Integer>`?** Do not mistakenly use `Arrays.asList(int[])`; box each element.
7. **Are you assuming `List<Integer>` is a `List<Number>`?** Use appropriate variance/wildcards.
8. **Do you need to represent absence without wrapper `null`?** Use `OptionalInt` or a suitable primitive return contract.
9. **Are you using a primitive type witness like `<int>`?** Change to a wrapper type or let the compiler box/infer validly.
10. **Do you need compatibility with an external API?** If the API accepts a primitive array, do not force a generic collection merely because you are practicing Generics.

Clear design is usually better than hiding boxing and casts behind complex abstractions. Every choice should follow the data's semantics and the API shape you need to support.

## 24. Summary and authoritative references

**Java Generics does not allow primitive types such as `int`, `double`, or `boolean` as type arguments.** To use generic APIs, choose the corresponding wrapper class: `Integer`, `Double`, `Boolean`, and so on. Java provides autoboxing/unboxing to bridge primitives and wrappers in everyday code, yet these conversions carry consequences for `null`, equality, and potentially performance.

Do not confuse a **primitive type** with an **array of primitives**: `int` is not a reference type, whereas `int[]` is a reference array object, making `List<int[]>` valid. For large numbers of primitive values, consider `int[]`, `IntStream`, `OptionalInt`, or primitive-specialized functional interfaces instead of forcing everything into `List<Integer>`.

Choose the structure suited to the problem:

- Use `List<Integer>` for Collection APIs when generic reference elements are needed.
- Use `int[]` when fixed-length primitive storage is needed.
- Use `IntStream` when a numeric operation pipeline is beneficial.
- Use `OptionalInt` when a possibly absent `int` value is needed.
- Use wrapper/reference generics when a general-purpose, compile-time type-safe API is required.

Authoritative references:

- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type argument rules.
- [Java Language Specification §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types versus primitive types.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure of type variables and parameterized types.
- [Java Language Specification §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7): converting primitives to wrappers.
- [Java Language Specification §5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): converting wrappers to primitives and the `null` case.
- [Java SE 17 `java.lang.Integer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): the `Integer` wrapper and related APIs.
- [Java SE 17 `java.util.stream.IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): stream specialized for primitive `int`.
- [Java SE 17 `java.util.OptionalInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html): optional for primitive `int`.