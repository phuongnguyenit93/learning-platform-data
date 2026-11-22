# Boxing Costs and Why Java Generics Do Not Automatically Specialize Code for Primitives

## Learning Objectives

In Java, `List<Integer>` is valid whereas `List<int>` is invalid. This has direct consequences for memory, allocation, and performance: when a primitive value like `int` enters a generic structure requiring a **reference**, Java must generally **box** it into an `Integer` wrapper object; when used again in arithmetic, Java typically **unboxes** it back to `int`.

This lesson explains **both sides** of the issue:

1. **Language and JVM:** Why Java 17 generics work primarily with reference types, why erasure uses `Object`/upper bounds instead of a dedicated `int` version, and why the compiler does not automatically generate a separate version of a generic algorithm for each primitive.
2. **Cost and testing:** When boxing/unboxing happens semantically, `NullPointerException` and identity risks, memory/GC overhead that can arise, when `int[]` / `IntStream` / primitive functional interfaces are needed, and how to measure performance without inventing numbers.

After this lesson, you will be able to:

- Distinguish primitive `int` from reference `Integer`; distinguish boxing, unboxing, widening, and generic erasure.
- Write positive/negative compilation tests for `List<Integer>`, `List<int>`, `Box<int>`, arithmetic on `T extends Number`, `new T[]`, and `T.class`.
- Prove with `javap -s` that fields/methods of `Box<T>` after erasure do not become primitive fields/methods for `T=Integer`.
- Read a loop `for (int n : List<Integer>)` and spot where unboxing occurs.
- Know why data containing `null` can throw `NullPointerException` at the unboxing point.
- Understand that numeric value and **object identity** are two different concepts for wrappers.
- Compare `int[]`, `List<Integer>`, `IntStream`, `Stream<Integer>`, `IntUnaryOperator`, `OptionalInt`, and API design alternatives.
- Distinguish potential boxing overhead from verified measurements; avoid claiming "every boxing definitely allocates an object" or "`IntStream` is always faster."

The complete runnable programs use **JDK 17 or later**. The code has been verified with `javac --release 17 -Xlint:all -Werror`, and stdout results are recorded exactly from the verified runs. Snippets that intentionally fail to compile are marked clearly; do not place them in the same source set as valid programs.

## 1. Primitives and Wrappers: Two Different Data Types

Java has eight primitive types:

| Primitive | Wrapper reference |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

`int` is a Java primitive value type; `Integer` is a **class**, an object reference that can point to a wrapper instance or `null`. Wrappers provide APIs such as `intValue()`, `parseInt(...)`, `compare(...)`, and many others.

Notice the difference:

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(42);
```

- The `primitive` variable holds a primitive `int` value under Java semantics.
- The `wrapper` variable is a reference to an `Integer` object; that reference can be `null`.
- `Integer` represents an integer value, yet **is not synonymous** with having declared type `int`.
- `Integer` is a subtype of `Number` and `Object`. Primitive `int` is **not** a subtype of `Object` or `Number`.

An assignment expression:

```java
Integer x = 42;
int y = x;
```

is accepted by the compiler due to conversion rules (boxing and unboxing), **not** because `int` and `Integer` are the same generic type or in an inheritance relationship.

## 2. What Is Boxing?

**Boxing conversion** turns a primitive value into a value of its corresponding wrapper type. Example:

```java
int value = 42;
Integer boxed = value; // Autoboxing.
```

Semantically, this can be understood roughly as:

```java
Integer boxed = Integer.valueOf(value);
```

The compiler typically inserts the appropriate wrapper factory call in bytecode, such as `Integer.valueOf(int)`. This is a common semantic/bytecode explanation, not a guarantee that every boxing operation always allocates a fresh object.

Wrapper factories can **cache** or reuse objects according to implementation and specification rules. The JIT optimizer can also eliminate boxed objects that do not need to be materialized on the heap when observable program semantics are preserved.

**Therefore:** an accurate assessment is "boxing *can potentially* cause allocations and increase memory/GC pressure," not "every autoboxing definitely creates a new heap object."

### Common Places Where Boxing Happens

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10);                // int -> Integer.
Integer result = 5 + 7;         // int expression -> Integer.
Object asObject = 12;           // int -> Integer -> Object.
Integer viaFactory = Integer.valueOf(13);
```

The snippet above requires imports `java.util.List` and `java.util.ArrayList`, placed inside a valid method. `List<Integer>` requires reference elements, so `numbers.add(10)` must convert the primitive argument into a compatible wrapper.

Writing `numbers.add(Integer.valueOf(10))` makes boxing explicit. It does **not** make elements in the list primitive: the element type remains `Integer`.

## 3. What Is Unboxing?

**Unboxing conversion** extracts a primitive value from a wrapper. Example:

```java
Integer boxed = 42;
int number = boxed; // Unboxing.
```

A simple way to view it is:

```java
int number = boxed.intValue();
```

Primitive arithmetic typically triggers unboxing:

```java
Integer a = 3;
Integer b = 4;
int sum = a + b;
```

Here both wrappers are used as `int` in the `+` operation. If you want to express a generic operation supporting any `Number`, you cannot assume `+` is automatically defined on generic type variables.

### Null Unboxing: A Frequently Overlooked Runtime Error

```java
Integer missing = null;
int value = missing; // Throws NullPointerException at runtime.
```

The assignment **compiles**: the type checker sees an `Integer` that can be unboxed. At runtime, however, the reference is `null`, so extracting the primitive value fails.

The same error happens in `for (int n : listOfInteger)`, `Integer` arithmetic, or `mapToInt(Integer::intValue)` when actual data contains `null`. This is a **runtime test case**, not a pattern the compiler rejects.

## 4. Why Is `List<int>` Rejected?

A generic class in Java 17 takes **reference types** as type arguments. `int` is a primitive and therefore invalid.

**Must compile:**

```java
import java.util.List;

class ValidListOfWrappers {
    List<Integer> numbers = List.of(1, 2, 3);
}
```

**Must be rejected:**

```java
import java.util.List;

class InvalidPrimitiveTypeArgument {
    List<int> numbers;
}
```

Run the negative fixture separately:

```bash
javac --release 17 InvalidPrimitiveTypeArgument.java
```

In verification, the compiler returned a non-zero exit code with a diagnostic stating `int` is not a reference type argument. There is no valid program to run from this fixture.

The same applies to:

```java
class Box<T> {}
class InvalidPrimitiveGenericUse {
    Box<int> value; // Compile-time error.
}
```

The Java compiler does **not** automatically reinterpret `Box<int>` as `Box<Integer>` merely because autoboxing exists on expressions/method invocations. Use `Box<Integer>`, or if the API requires efficient primitive numeric data, write/introduce a dedicated primitive abstraction.

## 5. Generics Are Compiled Using Type Erasure

Consider a generic holder:

```java
static final class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

With an unbounded `T`, standard erasure uses `Object` at the corresponding sites. In the JVM class file:

- Field `T value` has descriptor `Ljava/lang/Object;`.
- Constructor `Box(T)` has descriptor `(Ljava/lang/Object;)V`.
- Method `T get()` has descriptor `()Ljava/lang/Object;`.

The compiler still records generic `Signature` metadata where appropriate so tools understand the `Box<T>` declaration. Yet the JVM-level method descriptor does not become `()I` just because a caller uses `Box<Integer>`.

Example:

```java
Box<Integer> box = new Box<>(42);
Integer result = box.get();
```

`42` is boxed to be passed to the constructor taking a reference after erasure. When the caller retrieves `Integer`, the compiler inserts an appropriate type cast per the generic contract; if the caller then uses `int`, unboxing follows.

**Two distinct steps:**

1. **Erasure** lets a single generic implementation serve multiple reference type arguments.
2. **Boxing/unboxing** lets a primitive cross a boundary expecting a wrapper reference.

Do not merge them into one concept. Type erasure does not mean the compiler automatically generates specialized machine code versions for `int` and `long`.

## 6. Why Isn't There a Separate `Box<int>` Automatically?

In Java 17:

- Type arguments of generic classes/methods exclude primitive types.
- Positions using an unbounded `T` at the JVM level rely on `Object`; with explicit bounds, erasure relies on the appropriate first bound.
- A generic implementation is typically **shared** across `Box<String>` and `Box<Integer>`, rather than having a compiler-generated Java bytecode class `Box$int`.
- Boxing allows primitive values to participate in APIs accepting only wrapper/reference types, creating a **semantic conversion** rather than generating a specialized generic class.

If you want fields and methods to use **primitive descriptor `I`**, you need code actually carrying that primitive type, such as:

```java
static final class IntBox {
    private final int value;
    IntBox(int value) { this.value = value; }
    int get() { return value; }
}
```

`Box<Integer>` and `IntBox` can express the same API idea while **differing in representation and bytecode signatures**. The latter stores an `int` field and returns `int`; the former must obey the generic erasure/reference semantics of `Box<T>`.

This is not saying "generics are always bad": for algorithms primarily handling references, generics avoid manual casts and maintain strong type safety. Boxing becomes worth evaluating when processing **large volumes of primitive numbers** on hot paths.

## 7. Program A — Observing Boxing, Unboxing, and Erasure

Create the file **`BoxingMechanicsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingMechanicsDemo {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static final class IntBox {
        private final int value;
        IntBox(int value) { this.value = value; }
        int get() { return value; }
    }

    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;
        int unboxed = boxed;
        System.out.println("boxed type: "
                + boxed.getClass().getSimpleName());
        System.out.println("unboxed: " + unboxed);

        List<Integer> values = new ArrayList<>();
        for (int i = 1; i <= 3; i++) values.add(i);
        int sum = 0;
        for (int value : values) sum += value;
        System.out.println("generic list: " + values);
        System.out.println("generic sum: " + sum);

        Box<Integer> generic = new Box<>(42);
        IntBox specialized = new IntBox(42);
        System.out.println("generic holder: " + generic.get());
        System.out.println("primitive holder: " + specialized.get());

        Integer cachedA = 127;
        Integer cachedB = 127;
        System.out.println("small boxed identity: "
                + (cachedA == cachedB));
        System.out.println("numeric comparison: "
                + Integer.valueOf(1000)
                         .equals(Integer.valueOf(1000)));

        Integer missing = null;
        try {
            int impossible = missing;
            System.out.println(impossible);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Commands:

```bash
javac --release 17 -Xlint:all -Werror BoxingMechanicsDemo.java
java BoxingMechanicsDemo
```

**Verified stdout:**

```text
boxed type: Integer
unboxed: 42
generic list: [1, 2, 3]
generic sum: 6
generic holder: 42
primitive holder: 42
small boxed identity: true
numeric comparison: true
null unboxing: NullPointerException
```

The program compiled cleanly under `-Xlint:all -Werror`.

### Accurate Interpretation

- `Integer boxed = primitive`: primitive → wrapper conversion.
- `int unboxed = boxed`: wrapper → primitive conversion.
- `values.add(i)`: an `int` is added to `List<Integer>`, so boxing happens semantically.
- `for (int value : values)`: when iterating `List<Integer>`, each element reference is unboxed to assign to `int`.
- `Box<Integer>` does not turn field `T` into `int`. It is a generic reference container.
- Manually written `IntBox` uses a primitive field and primitive getter; compared to `Box<Integer>`, it differs in representation.
- `cachedA == cachedB` for the constant `127` yields `true` under small boxed integer caching rules; **never** use `==` to compare wrapper values in general.
- `Integer.valueOf(1000).equals(Integer.valueOf(1000))` compares **values**, without requiring the two references to be the same object.
- Unboxing `missing` throws `NullPointerException` at runtime.

Do not read the output above as a benchmark. It verifies **behavior and type/runtime risks**, without measuring allocations or nanoseconds.

## 8. Verifying with `javap`: Reference vs. Primitive Descriptors

After compiling the file above, inspect the two nested classes:

```bash
javap -p -s 'BoxingMechanicsDemo$Box'
javap -p -s 'BoxingMechanicsDemo$IntBox'
```

In Windows PowerShell or Bash, single quotes around names containing `$` prevent the shell from misinterpreting what follows `$`.

**Verified abbreviated output:**

```text
final class BoxingMechanicsDemo$Box<T> {
  private final T value;
    descriptor: Ljava/lang/Object;
  BoxingMechanicsDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V
  T get();
    descriptor: ()Ljava/lang/Object;
}

final class BoxingMechanicsDemo$IntBox {
  private final int value;
    descriptor: I
  BoxingMechanicsDemo$IntBox(int);
    descriptor: (I)V
  int get();
    descriptor: ()I
}
```

Observations:

| Location | Unbounded `Box<T>` | Manually Specialized `IntBox` |
| --- | --- | --- |
| Field | `Ljava/lang/Object;` | `I` |
| Constructor | `(Ljava/lang/Object;)V` | `(I)V` |
| Getter | `()Ljava/lang/Object;` | `()I` |

**This is evidence of the JVM code form emitted**, not a measurement of JIT optimization or actual memory usage in a benchmark. The JVM can optimize aggressively in specific contexts, yet the Java compiler still does not turn `Box<Integer>` into a generic instantiation class with a primitive field.

To inspect call sites containing boxing/unboxing, use:

```bash
javap -p -c BoxingMechanicsDemo
```

Look for methods like `Integer.valueOf`, `Integer.intValue`, and operations on the generic/primitive classes. Bytecode easily confirms **which conversions are represented**, whereas seeing whether the JIT eliminates an allocation requires other tools.

## 9. How Many Objects Are Allocated During Boxing?

This question **cannot be answered with a single universal constant**.

For:

```java
Integer a = 42;
Integer b = 42;
```

wrapper instances can be **reused** under caching rules. In Java, small boxed integer values in at least the range `-128..127` have specified identity guarantees in boxing contexts; `Integer.valueOf` also caches at least this range.

For:

```java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);
```

do not write a test **requiring `x != y`** to prove allocation. Implementations may expand the cache or the JVM may optimize. And even when two references differ, you still cannot deduce the exact time cost of the entire program.

Beyond caching, the compiler/JIT can reduce or eliminate wrapper allocations when objects do not escape and nothing observes object identity. Conversely, storing millions of boxed values in a collection can force many wrapper objects to be retained.

**Accurate conclusion:** boxing has *potential* overhead in CPU, memory footprint, object indirection, and garbage collection; actual overhead depends on data, environment, and runtime optimizations. Only conclude allocation counts or latency through proper profiling or benchmarking.

## 10. Memory Cost of `List<Integer>` vs. `int[]`

Consider two structures holding N numbers:

```java
int[] primitiveNumbers = {1, 2, 3, 4};
List<Integer> wrappedNumbers = List.of(1, 2, 3, 4);
```

Conceptually:

- `int[]` has a single array object containing contiguous primitive `int` elements in array storage.
- `List<Integer>` requires a collection implementation and **element references** pointing to `Integer` wrapper values (or reused objects). The exact backing structure depends on the implementation; do not assume every `List` uses `ArrayList`.
- Each `Integer` wrapper is an object reference value, carrying an object header/alignment/indirection if materialized.
- Reference counts and object allocations affect locality/cache behavior, garbage collector pressure, and managed bytes.

Therefore, for large numeric datasets and repeated processing, a primitive array is **typically** the lower-overhead representation.

However, **do not assign a fixed byte count per `Integer` across all JVMs**. It depends on JDK, 32/64-bit architecture, compressed references, object layout, alignment, collections, caching, and escape analysis.

### A Conceptual Estimation Model

When N is very large:

```text
int[]:
  array header + N × int element size (in primitive representation)

Reference-backed List<Integer>:
  collection/backing structure
  + N × element reference size
  + wrapper objects that actually need to exist
  + corresponding metadata/overhead
```

This model is not a direct measurement. **Do not** treat it as a promise that "`List<Integer>` always uses X times the RAM of `int[]`." When choosing a structure, profile realistically, measure retained heap bytes/GC if needed, and consider the APIs used by the rest of the program.

## 11. Cannot Use the `+` Operator on Arbitrary `T extends Number`

Someone might try writing:

```java
class InvalidGenericArithmetic<T extends Number> {
    T add(T left, T right) {
        return left + right; // Compile-time error.
    }
}
```

This file **intentionally fails to compile**:

```bash
javac --release 17 InvalidGenericArithmetic.java
```

The verified result is a non-zero exit code and diagnostic `bad operand types for binary operator '+'`.

**Why?**

- Generic `T extends Number` only guarantees that `T` has members inherited from `Number` (such as `doubleValue()`).
- It does not define a static `+` operator across every subtype `T` and does not guarantee the sum has the same return type `T`.
- `Integer`, `Double`, `BigDecimal`, and `BigInteger` have different arithmetic semantics: overflow, precision, rounding, scale, division, etc.
- Java Generics do not synthesize a `T + T` addition merely from knowing the `Number` upper bound.

You can write:

```java
static double sumAsDouble(List<? extends Number> source) {
    double sum = 0;
    for (Number n : source) sum += n.doubleValue();
    return sum;
}
```

Yet this is **not** a generic exact-number adder preserving subtype `T`. Converting numbers to `double` can lose precision for large integers or high-precision numeric types. If exact `BigDecimal` arithmetic is required, choose the right API and rounding rules instead of relying casually on `doubleValue()`.

## 12. Avoiding Boxing on Hot Paths with Primitive Arrays

If a workload is primarily arithmetic on `int` numbers and needs no polymorphic collections, `int[]` is the natural choice:

```java
int[] values = {1, 2, 3, 4};
int total = 0;
for (int value : values) {
    total += value;
}
```

There are no `int -> Integer -> int` conversions from a generic collection when accessing `values`. Elements are primitive values.

### What Else Must Be Checked?

- `int` arithmetic can still **overflow**. Use `long` accumulation or `Math.addExact` if overflow must be detected rather than wrapping around.
- Arrays have fixed size, and their API is often less convenient than collections for insertion/deletion/structural transformation.
- An array is still a runtime object with a header; "primitive array" does not mean zero allocations altogether.
- If it must be converted to `List<Integer>` for another API, boxing may reappear at the boundary.
- Testing correctness and overflow is just as important as testing performance.

No single data structure is "best" for every use case. Choose primitive arrays when they clearly express the **uniform numeric bulk data** the API actually needs.

## 13. Primitive Streams: `IntStream` Differs from `Stream<Integer>`

The standard library provides specialized streams:

- `IntStream` for `int`.
- `LongStream` for `long`.
- `DoubleStream` for `double`.

With primitive streams, operations like `map(IntUnaryOperator)`, `sum()`, `average()`, `max()`, and `forEach(IntConsumer)` are defined on primitive values, **without requiring each element to pass through an `Integer` in the stream API**.

Compare:

```java
int[] numbers = {1, 2, 3, 4};
int a = java.util.Arrays.stream(numbers).sum();
int b = java.util.stream.IntStream.of(numbers).sum();
```

Both process a sequence of `int` and return an `int` sum. By contrast:

```java
List<Integer> boxed = List.of(1, 2, 3, 4);
int total = boxed.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

`boxed.stream()` is a `Stream<Integer>`. Converting to `IntStream` via `mapToInt` extracts primitive values from wrapper elements. If the collection contains `null`, the method reference fails on unboxing/dereferencing that element.

### Converting from a Primitive Stream to a Generic Stream

```java
List<Integer> list = java.util.stream.IntStream
        .rangeClosed(1, 4)
        .boxed()
        .toList();
```

`boxed()` requires producing a **`Stream<Integer>`** at the API level. Moving from a primitive path to a reference path can forfeit boxing avoidance; actual time/allocations must be measured on the workload.

Steps like `boxed()` / `mapToObj(...)` / collecting into `List<Integer>` are important **representation-transition boundaries** when analyzing performance.

## 14. Primitive Functional Interfaces: Do Not Use Generic `Function<Integer,Integer>` When You Only Need `int -> int`

A `Function<Integer,Integer>` represents a transformation accepting/returning **reference wrapper types**. When inputs/outputs are naturally primitive, the library offers corresponding interfaces:

| Need | Generic Wrapper API | Primitive Specialization |
| --- | --- | --- |
| Function `int -> int` | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Accept an `int` | `Consumer<Integer>` | `IntConsumer` |
| Test `int -> boolean` | `Predicate<Integer>` | `IntPredicate` |
| Produce an `int` | `Supplier<Integer>` | `IntSupplier` |
| Read an optionally absent number | `Optional<Integer>` | `OptionalInt` |
| Iterate `int` numbers | `Stream<Integer>` | `IntStream` |

Note: these are **explicitly written/defined specialized interfaces and classes in the library**, not the compiler auto-generating `Function<int,int>`.

Example:

```java
java.util.function.IntUnaryOperator doubleIt = x -> x * 2;
int value = doubleIt.applyAsInt(7); // 14
```

`IntUnaryOperator.applyAsInt` uses `int` in its signature. Compared to `Function<Integer,Integer>.apply`, this interface requires no wrapper types in its parameter/return contract.

**However:** lambda allocation, virtual dispatch, inlining, and JIT optimizations affect overall performance. A "primitive interface" avoids wrapper representations at the API boundary, rather than guaranteeing every call is faster in every benchmark.

## 15. Program B — Comparing Primitive Paths and Conversions

Create the file **`PrimitiveAlternativesDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalInt;
import java.util.function.IntUnaryOperator;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PrimitiveAlternativesDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3, 4};
        System.out.println("array sum: "
                + Arrays.stream(source).sum());
        System.out.println("int stream sum: "
                + IntStream.of(source).sum());
        System.out.println("squares sum: "
                + IntStream.of(source)
                           .map(x -> x * x).sum());

        List<Integer> boxed =
                IntStream.of(source).boxed().toList();
        System.out.println("boxed list: " + boxed);
        System.out.println("list sum: "
                + boxed.stream()
                       .mapToInt(Integer::intValue).sum());

        IntUnaryOperator doubleIt = x -> x * 2;
        System.out.println("primitive function: "
                + doubleIt.applyAsInt(7));

        OptionalInt maximum = IntStream.of(source).max();
        OptionalInt absent = IntStream.empty().max();
        System.out.println("max: " + maximum.orElseThrow());
        System.out.println("empty max present: "
                + absent.isPresent());

        try {
            Stream.of(1, null, 3)
                  .mapToInt(Integer::intValue).sum();
        } catch (NullPointerException ex) {
            System.out.println("null stream unboxing: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Commands:

```bash
javac --release 17 -Xlint:all -Werror PrimitiveAlternativesDemo.java
java PrimitiveAlternativesDemo
```

**Verified stdout:**

```text
array sum: 10
int stream sum: 10
squares sum: 30
boxed list: [1, 2, 3, 4]
list sum: 10
primitive function: 14
max: 4
empty max present: false
null stream unboxing: NullPointerException
```

When processing `int[]` and `IntStream`, many operators work directly with `int`. Calling `boxed()` turns the result API into `Stream<Integer>`, and `toList()` produces `List<Integer>`. `mapToInt` switches back to the primitive path.

### How Does `OptionalInt` Differ from `Optional<Integer>`?

`OptionalInt` is a specialized container for **an optionally absent `int` value**, avoiding requiring an `Integer` wrapper in the value-holding API. `IntStream.max()` returns `OptionalInt` because the stream might be empty. Calling `orElseThrow()` on a non-empty stream retrieves the `int`; on an empty stream it throws `NoSuchElementException`.

Do not turn `OptionalInt` into a general replacement for all `Optional<T>`. It is designed for primitive `int` with its own API and does not hold arbitrary reference types.

## 16. Boxing Conversions Can Be Hidden by Syntax

Java has autoboxing/unboxing for readability, yet each conversion point is still worth watching during debugging:

```java
Integer objectNumber = 5;  // Boxing.
int plain = objectNumber;   // Unboxing.

List<Integer> values = new ArrayList<>();
values.add(plain);          // Boxing to store as Integer.

int accumulator = 0;
for (int value : values) {  // Unboxing each element.
    accumulator += value;
}
```

Not every `+` operator unboxes in every context. For instance, string concatenation has text conversion rules, and overload resolution can pick a different method. To know the exact conversion, check the **static types** of operands, the expression context, and the compiler-generated bytecode.

However, do not optimize a snippet merely because you see `Integer.valueOf` in bytecode. The JIT can inline or eliminate much of the cost; measure on a real workload to identify actual hot spots.

## 17. Primitive Arrays vs. `List<Integer>`: Different Semantics Too, Not Just Performance

Replacing a `List<Integer>` with `int[]` also changes the contract:

| Property | `int[]` | `List<Integer>` |
| --- | --- | --- |
| Elements | `int` | `Integer` references |
| Can contain null? | No | Depending on implementation, yes |
| Size | Fixed | Depending on implementation/API |
| Generic collection APIs | Does not directly implement `List` | Yes |
| Indexed access | `a[i]` | `list.get(i)` |
| Runtime element type | Primitive component type `int` | Runtime generic argument is erased |
| Boxing when storing `int` values | None due to element representation | Converts to wrapper at the API |
| Specialized stream API | `Arrays.stream(a)` → `IntStream` | `list.stream()` → `Stream<Integer>` |
| Large numeric datasets | Usually lower representation overhead | Can incur wrapper/reference overhead |

If business logic needs **null** to represent "no number present," `int[]` cannot represent that state on its own. You would need an extra bitset/sentinel/schema or a reference representation. Do not switch to primitives just to cut allocations and lose data semantics.

If an API needs arbitrary insertions/removals and integrates with many collection utilities, `List<Integer>` can be far more convenient; paying conversion/wrapper costs is sometimes an acceptable trade-off.

## 18. Bridge Methods from Erasure Are Not Primitive Specialization

When a subclass overrides a generic method specialized with a **reference type**:

```java
class Parent<T> {
    T echo(T value) { return value; }
}
class StringChild extends Parent<String> {
    @Override String echo(String value) { return "v=" + value; }
}
```

`javac` can generate a bridge so calls targeting the erased descriptor `echo(Object):Object` dispatch to the `echo(String):String` implementation. A bridge's job is preserving overriding after erasure—it **does not** emit a `Parent<int>` class and does not eliminate boxing from `Parent<Integer>`.

## 19. Comparing Bridges with True Primitive APIs

Two key descriptors on the compiled `StringChild` class are:

```text
echo:(Ljava/lang/String;)Ljava/lang/String;   // Implementation
echo:(Ljava/lang/Object;)Ljava/lang/Object;   // Bridge
```

Meanwhile, a functional interface **explicitly declared for primitives** genuinely has a descriptor using `I`:

```java
java.util.function.IntUnaryOperator twice = x -> x * 2;
int result = twice.applyAsInt(7); // 14, method accepts/returns primitive int
```

`IntUnaryOperator.applyAsInt(int)` has descriptor `(I)I`, whereas `Function<Integer,Integer>.apply` uses the reference-erased descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`. The difference comes from an **explicitly designed primitive API**, not from the compiler automatically specializing a generic instantiation. The class-file/bridge comparison lesson in this chapter provides a complete Java 17 program, `javap -s/-v`, and Reflection to locate `ACC_BRIDGE` and `ACC_SYNTHETIC`; here we simply distinguish bridges from boxing.

## 20. Code Samples That Must Be Rejected by the Compiler

Alongside positive programs, test each rule with **a standalone negative fixture**. The five files below were tested with `javac --release 17`: all returned a non-zero exit code and produced a compiler error for the exact stated rule.

### 20.1. Cannot Use a Primitive Type Argument

File `InvalidPrimitiveTypeArgument.java`:

```java
import java.util.List;

class InvalidPrimitiveTypeArgument {
    List<int> values;
}
```

Expected: **REJECTED** with a diagnostic stating a reference type is required but `int` was found.

### 20.2. Cannot Automatically Create Generic Specialization for Primitives

File `InvalidPrimitiveGenericBox.java`:

```java
class InvalidPrimitiveGenericBox<T> {}

class InvalidPrimitiveGenericUse {
    InvalidPrimitiveGenericBox<int> value;
}
```

Expected: **REJECTED**. Use `InvalidPrimitiveGenericBox<Integer>` or a dedicated primitive-specialized class if that is the desired contract.

### 20.3. Cannot Assume `+` Operator on `T extends Number`

File `InvalidGenericArithmetic.java`:

```java
class InvalidGenericArithmetic<T extends Number> {
    T add(T left, T right) {
        return left + right;
    }
}
```

Expected: **REJECTED** because the `+` operator does not apply directly to two expressions of type `T`.

### 20.4. Cannot Create an Array from an Arbitrary Type Variable

File `InvalidGenericArray.java`:

```java
class InvalidGenericArray<T> {
    T[] newItems(int size) {
        return new T[size];
    }
}
```

Expected: **REJECTED** due to generic array creation. Use an appropriate structure/library or pass an array factory/token per contract, rather than creating `T[]` directly when the element type is non-reifiable.

### 20.5. Cannot Take `T.class` from a Type Variable

File `InvalidTypeLiteral.java`:

```java
class InvalidTypeLiteral<T> {
    Class<?> token() {
        return T.class;
    }
}
```

Expected: **REJECTED** with an error equivalent to `cannot select from a type variable`. Pass a `Class<T>` token or appropriate type descriptor when runtime type information is genuinely needed.

### Running a Negative Sample in Bash

```bash
if javac --release 17 InvalidPrimitiveTypeArgument.java; then
    echo "FAIL: invalid code unexpectedly compiled"
    exit 1
else
    echo "PASS: invalid code rejected"
fi
```

In PowerShell 5.1:

```powershell
javac --release 17 InvalidPrimitiveTypeArgument.java
if ($LASTEXITCODE -eq 0) {
    throw "Invalid source unexpectedly compiled"
}
Write-Output "PASS: invalid source rejected"
```

Never invoke `java` on a fixture that the compiler rejected. If stale class files exist in the directory, avoid accidentally running an old build. A negative compilation test succeeds at the **compiler exit status and diagnostic level**, not via runtime stdout.

## 21. Can `T extends Number` Be Used to Avoid Boxing?

No. A bound such as:

```java
static <T extends Number> double sum(
        java.util.List<T> values) {
    double result = 0;
    for (T value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

still accepts **reference type arguments** in Java 17. If a caller passes `List<Integer>`, elements remain `Integer` references; the bound only grants access to members like `doubleValue()`.

In bytecode, erasure of `T extends Number` uses the bound `Number` at the corresponding positions rather than becoming primitive `int`. Moreover:

- `doubleValue()` does not guarantee exact arithmetic across all subtypes.
- `List<Double>` can contain `null` if the implementation allows it; calling `doubleValue()` on null throws `NullPointerException`.
- If exact numeric type `BigDecimal` must be preserved, use operators/APIs built for `BigDecimal` rather than generic bound `Number`.

Bounds provide **supertype method capabilities**, not specialized operators or primitive memory layouts.

## 22. Boxing in Map Keys, `Optional`, and Callbacks

Boxing does not happen only in `List`:

```java
java.util.Map<Integer, String> names =
        new java.util.HashMap<>();
names.put(7, "seven"); // int is boxed into an Integer key.

java.util.Optional<Integer> boxedOption =
        java.util.Optional.of(5);
java.util.OptionalInt primitiveOption =
        java.util.OptionalInt.of(5);
```

With `Map<Integer,V>`, the key is an `Integer` reference. Do not assume `HashMap` has primitive-specialized storage merely because the call site passes an `int` literal.

When accessing numeric data at large scale, primitive-specialized collections from external libraries can provide suitable representations, though you must evaluate their APIs, licenses, thread safety, null/sentinel semantics, and benchmarks. No external library is required just to learn generics.

When code handles only small counts, `List<Integer>` and `Map<Integer,V>` are often plenty good enough, keeping APIs simpler and easier to maintain than primitive-specific abstractions.

## 23. Solving Cost Through API Design, Not Just Editing One Line of Code

Before optimizing, trace the **data path**:

```text
Primitive source int[]
        |
        v
   IntStream / int operators  --- primitive path --->
        |
        | boxed(), mapToObj(Integer::valueOf),
        | add to List<Integer>, map key Integer...
        v
   Stream<Integer> / List<Integer> / generic APIs
        |
        | mapToInt(Integer::intValue),
        | iterator/for(int x : boxedList)...
        v
   int operations again
```

Boundary crossings between the two representations can involve boxing/unboxing. A good solution avoids **repeatedly** converting back and forth in code processing large data volumes.

For example: if the input is `int[]` and the output only needs a sum, return an appropriate primitive `int` or `long` instead of building an unnecessary intermediate `List<Integer>`.

If the rest of the application requires `List<Integer>`, boxing once at a clear boundary is sometimes entirely reasonable. Do not build an entire specialized framework just to avoid a handful of wrapper values that cause no measurable issue.

## 24. What Makes a Benchmark Trustworthy?

**There is no universal "boxing is X times slower" figure across all JDKs.** A serious benchmark must distinguish:

1. **Allocation rate:** How many objects actually materialize/escape, not just how many `Integer.valueOf` calls appear in bytecode?
2. **Throughput/latency:** Total time of a representative workload, not a single overly short loop.
3. **GC pressure:** Collection counts and pause times under realistic load.
4. **Retained heap memory:** Does boxed data kept in collections consume additional memory?
5. **JIT effects:** Inlining, escape analysis, scalar replacement, vectorization, and warmup can alter results.
6. **Data characteristics:** Input size, value ranges (affecting caching), null counts, and data distribution.
7. **Comparability:** Both variants must compute the **exact same result** with identical semantics for overflow, precision, and null handling.

### Tooling Recommendations

Use a profiler on real workloads; when a JVM microbenchmark is needed, prefer **JMH** with warmup, multiple forks, iterations, and proper result consumption so the JIT does not eliminate dead work. When measuring object layout/heap, use appropriate inspection tools rather than guessing from a fixed object-header byte count.

Do not use a single-shot `System.nanoTime()` program as convincing proof that boxing always costs a specific number of nanoseconds.

### A Reasonable Benchmark Design Pattern

Compare three paths with the same data size and the same math:

- A `for` loop over `int[]`.
- A `for` loop over a `List<Integer>` constructed **before the timed section**, if measuring only read access/unboxing.
- `IntStream` over `int[]` and `Stream<Integer>.mapToInt` over the list, if measuring stream pipeline overhead.

If you also want to measure **the cost of building a boxed collection**, construct the list inside the timed workload; **do not** compare that against an already-constructed `int[]` and pretend the two benchmarks are equivalent. Separate **data construction** cost from **data processing** cost.

Benchmark outputs must be verified identical before publishing results.

## 25. Optimization Attempts That Can Backfire

- **Turning every `List` into an array:** can lose null semantics, flexibility, APIs, and data ownership while adding conversion costs at other boundaries.
- **Replacing every stream with a loop:** loops can be faster in some workloads yet streams can be clearer, and the JVM optimizes differently; do not conclude without data.
- **Believing boxed values always allocate new objects:** caching, JIT optimization, and reuse make this false.
- **Believing boxed values have zero overhead because the JIT optimizes:** when references escape and must be retained, overhead can still be substantial.
- **Using `==` to check `Integer` equality:** object identity depends on caching/reuse and is not value comparison. Use `equals` or intentional unboxing.
- **Unboxing potentially null values without checking:** can throw `NullPointerException` in summation loops or `mapToInt`.
- **Using `doubleValue()` to sum every `Number`:** can lose precision/semantics.
- **Using `Integer` instead of `int` in every hot loop just to stay generic:** API type safety can remain at boundaries while core numeric paths use primitives.
- **Using primitive arrays when data requires heterogeneous types:** breaks the business contract and forces awkward compensating logic.

The goal of optimization is preserving **correctness + semantics** while reducing a verified cost, not merely making code look "less generic."

## 26. Practice Exercises with Answers

### Exercise 1 — Primitive Type Argument

Can you declare `List<int>` on Java 17? If not, what is the standard collection usage?

**Answer:** No. Generic type arguments require reference types; use `List<Integer>`. If you want a primitive representation, consider `int[]`, `IntStream`, or a specialized primitive structure.

### Exercise 2 — Where Is Boxing?

```java
List<Integer> list = new java.util.ArrayList<>();
int x = 5;
list.add(x);
```

**Answer:** `x` is primitive `int`; `List<Integer>.add` accepts `Integer`, so a boxing conversion occurs.

### Exercise 3 — Where Is Unboxing?

```java
int sum = 0;
for (int n : list) sum += n;
```

Given `list: List<Integer>`, **Answer:** each `Integer` element must be unboxed to `int` to assign to `n`. A `null` value can throw `NullPointerException`.

### Exercise 4 — Does a Bound Make `+` Work?

```java
<T extends Number> T add(T a, T b) {
    return a + b;
}
```

**Answer:** Does not compile. `Number` does not declare a `+` operator returning `T`. You need a concrete math API or an explicit conversion/strategy with chosen semantics.

### Exercise 5 — Wrapper Identity

`Integer a=127, b=127;` and `Integer x=1000, y=1000;`: should `==` be used as numeric equality checking?

**Answer:** No. `==` on two references is an identity test; small numbers are cached, yet you must never depend on identity for arbitrary values. Use `a.equals(b)` or explicit primitive comparisons.

### Exercise 6 — `OptionalInt`

When computing `IntStream.empty().max()`, what does the method return?

**Answer:** An empty `OptionalInt`; `isPresent()` is `false`. It does not create a null `Integer` to represent a missing value.

### Exercise 7 — Erasure Descriptors

Why does `Box<T>.get()` have `()Ljava/lang/Object;` while `IntBox.get()` has `()I`?

**Answer:** Unbounded `T` erases to `Object` in generic bytecode; `IntBox` is explicitly declared using primitive `int`, so its descriptor returns `int`.

### Exercise 8 — Is `Box<Integer>` Automatically Specialized?

**Answer:** No, not in the sense of turning all generic code into `Box<int>` on Java 17. `Box<Integer>` uses the shared generic class representation, with wrapper/conversions when crossing primitive boundaries.

### Exercise 9 — Comparing Two Benchmarks

Benchmark A constructs `List<Integer>` inside the timed section while Benchmark B reads a pre-built `int[]`. Can we say the runtime cost of the two element types was compared fairly?

**Answer:** Not yet. A includes structure-creation cost while B does not. Equivalent workloads must be defined, separating creation from processing.

### Exercise 10 — Runtime Null

Is `Stream.of(1,null,3).mapToInt(Integer::intValue).sum()` rejected by the compiler?

**Answer:** No, the code compiles. However, when the pipeline processes `null`, calling `intValue` throws `NullPointerException` at runtime.

### Exercise 11 — Bridge Methods

Is an `echo(Object):Object` bridge from overriding `echo(String):String` a sign that the compiler generated a primitive-specialized version?

**Answer:** No. Bridges preserve polymorphic dispatch after generic erasure; they are not directly related to `int`-specialization.

### Exercise 12 — Choosing Representation by Goal

A job processes millions of integers solely to compute a `long` sum. Which design is worth considering first?

**Answer:** Use `int[]`/a primitive loop or `IntStream` over a primitive source, accumulating into `long` to avoid `int` overflow. Measure the actual workload before asserting which is faster.

## 27. Design and Testing Checklist

- [ ] Know which variables are `int` and which are `Integer`; do not treat wrappers as primitives.
- [ ] Never use primitive `int` as a Java 17 generic type argument.
- [ ] Spot conversions when adding primitives to `List<Integer>` and reading them back as `int`.
- [ ] Have an explicit null policy before unboxing wrappers or calling `Integer::intValue`.
- [ ] Never use `==` on wrappers for general numeric equality checks.
- [ ] Distinguish generic erasure `Object`/bounds from primitive descriptors `I`, `J`, `D`.
- [ ] Do not expect `T extends Number` to automatically provide `+` or specialized primitive operators.
- [ ] Test negative source fixtures with the compiler and never run them as runtime programs.
- [ ] When numeric hot paths need optimization, consider `int[]`/`IntStream`/`IntUnaryOperator`/`OptionalInt`.
- [ ] Avoid introducing boxing/`boxed()` into large pipelines when only primitive output is needed.
- [ ] Preserve null semantics, overflow behavior, precision, and data ownership when changing representations.
- [ ] Do not claim every boxing always allocates or that the JIT eliminates all boxing.
- [ ] Measure allocation, GC, retained heap, and throughput on a realistic workload/JDK.
- [ ] Do not call a single `System.nanoTime()` measurement a trustworthy benchmark.
- [ ] When in doubt, use `javap -p -s/-c` to inspect descriptors and conversions before concluding.

## Conclusion

On Java 17, **generics do not automatically generate primitive specializations**. `List<Integer>` and `Box<Integer>` remain reference-generic APIs, whereas `List<int>`/`Box<int>` are rejected by the compiler. When primitive values cross wrapper APIs, boxing/unboxing can occur; null unboxing is a runtime hazard, and wrappers/references can increase memory, CPU, and GC costs in large workloads.

Instead of declaring generics "slow," choose the **representation that fits the role**: generics for type-safe object APIs, primitive arrays/streams/functions when processing raw numeric data, and conversions only at genuinely necessary boundaries. Inspect erasure with `javap`, run positive/negative compilation checks, and measure real performance with a profiler/JMH before optimizing. That avoids both **type bugs** and ungrounded performance claims.