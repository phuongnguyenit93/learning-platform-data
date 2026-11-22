# Primitive variants for `int`, `long`, `double`, and `boolean` in `java.util.function`

## 1. Context: why does Java have specialized functional interfaces?

General interfaces such as `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`, `UnaryOperator<T>`, and `BinaryOperator<T>` operate on **reference types**. Java generics do not accept primitive types as type arguments: `Function<int,int>` is invalid. If you use `Function<Integer,Integer>`, `int` values may have to be converted between `int` and the `Integer` wrapper (*boxing/unboxing*).

To directly express operations on integers, floating-point numbers, and boolean conditions, the JDK provides specialized functional interfaces in **`java.util.function`**:

- `Int...`: takes/returns `int` in specialized positions.
- `Long...`: takes/returns `long`.
- `Double...`: takes/returns `double`.
- `...ToIntFunction`, `...ToLongFunction`, `...ToDoubleFunction`: converts the result to the corresponding primitive.
- `BooleanSupplier`: directly supplies a `boolean` with no input.

These variants keep **type contracts** explicit, help avoid unnecessary boxing/unboxing in specialized parts, and align with `IntStream`, `LongStream`, and `DoubleStream`. However, they **do not automatically guarantee faster performance in every scenario**: computation cost, I/O, object allocation, element count, and JVM optimizations still determine actual results.

> **Important boundary:** there is no standard `BooleanFunction`, `BooleanConsumer`, `BooleanPredicate`, or `BooleanStream` family in Java 17. `boolean` is directly supported in the **return** of `Predicate` and primitive predicates, plus `BooleanSupplier` for the zero-argument case. Cases taking boolean as an input typically use `Boolean` with generic interfaces, or define a small custom functional interface when avoiding boxing is genuinely necessary.

## 2. Overview of interfaces by purpose

| Need | For `int` | For `long` | For `double` |
| --- | --- | --- | --- |
| One primitive → same primitive | `IntUnaryOperator`: `applyAsInt(int)` | `LongUnaryOperator`: `applyAsLong(long)` | `DoubleUnaryOperator`: `applyAsDouble(double)` |
| Two same-type primitives → one same-type result | `IntBinaryOperator`: `applyAsInt(int,int)` | `LongBinaryOperator`: `applyAsLong(long,long)` | `DoubleBinaryOperator`: `applyAsDouble(double,double)` |
| Primitive → `boolean` | `IntPredicate`: `test(int)` | `LongPredicate`: `test(long)` | `DoublePredicate`: `test(double)` |
| Primitive → no return value | `IntConsumer`: `accept(int)` | `LongConsumer`: `accept(long)` | `DoubleConsumer`: `accept(double)` |
| No input → primitive | `IntSupplier`: `getAsInt()` | `LongSupplier`: `getAsLong()` | `DoubleSupplier`: `getAsDouble()` |
| Primitive → reference type `R` | `IntFunction<R>`: `apply(int)` | `LongFunction<R>`: `apply(long)` | `DoubleFunction<R>`: `apply(double)` |

Two additional families bridge **reference types** and **primitive types**:

| Type | Core functional signature | Example |
| --- | --- | --- |
| `ToIntFunction<T>` | `int applyAsInt(T)` | String → length |
| `ToLongFunction<T>` | `long applyAsLong(T)` | Order → processing milliseconds |
| `ToDoubleFunction<T>` | `double applyAsDouble(T)` | Measurement object → weight |
| `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` | Two objects → integer index |
| `ToLongBiFunction<T,U>` | `long applyAsLong(T,U)` | Two objects → `long` result |
| `ToDoubleBiFunction<T,U>` | `double applyAsDouble(T,U)` | Two objects → `double` result |

**Do not mix up the primitive position:**

```java
IntFunction<String> label = score -> "score=" + score;
// int -> String; call label.apply(80)

ToIntFunction<String> length = String::length;
// String -> int; call length.applyAsInt("Java")
```

`IntFunction<R>` specializes the **input**, whereas `ToIntFunction<T>` specializes the **output**. The same applies to `LongFunction`/`ToLongFunction` and `DoubleFunction`/`ToDoubleFunction`. The snippet above requires importing `java.util.function.IntFunction` and `java.util.function.ToIntFunction`, placed in a method or `jshell`.

## 3. Transformations between primitive types

When converting from one primitive to **another primitive**, Java provides six interfaces:

| Conversion | Interface | Method |
| --- | --- | --- |
| `int → long` | `IntToLongFunction` | `long applyAsLong(int)` |
| `int → double` | `IntToDoubleFunction` | `double applyAsDouble(int)` |
| `long → int` | `LongToIntFunction` | `int applyAsInt(long)` |
| `long → double` | `LongToDoubleFunction` | `double applyAsDouble(long)` |
| `double → int` | `DoubleToIntFunction` | `int applyAsInt(double)` |
| `double → long` | `DoubleToLongFunction` | `long applyAsLong(double)` |

Example:

```java
IntToLongFunction secondsToNanos = s -> s * 1_000_000_000L;
LongToDoubleFunction toBillions = n -> n / 1_000_000_000.0;
LongToIntFunction checkedLongToInt = Math::toIntExact;
DoubleToLongFunction metersToMillimeters = m -> Math.round(m * 1000);

System.out.println(secondsToNanos.applyAsLong(3)); // 3000000000
System.out.println(toBillions.applyAsDouble(2_500_000_000L)); // 2.5
System.out.println(checkedLongToInt.applyAsInt(42L)); // 42
System.out.println(metersToMillimeters.applyAsLong(1.25)); // 1250
```

This snippet is placed inside a method with `import java.util.function.*`. Type conversions are **explicit business rules**, not automatically safe for all values:

- `long → int` can exceed the `int` range. `(int) longValue` can lose bits; `Math.toIntExact` throws `ArithmeticException` if out of range.
- `int/long → double` can lose precision for large integers because `double` has finite precision (53-bit significand).
- `double → int/long` requires choosing a **rounding rule**. Casting and `Math.round` are not equivalent. `Math.round(double)` returns `long`, not `int`.
- When converting units, check multiplication overflow: use the literal `1_000_000_000L` so the `int → long` multiplication in the example is performed in `long` arithmetic.

## 4. Specializations with `boolean`

In Java, `boolean` has two logical values: `true`/`false`. Do not use `0`/`1` as booleans, and there is no `BooleanStream` in JDK 17.

### `BooleanSupplier`: a boolean source with no input

```java
import java.util.function.BooleanSupplier;

BooleanSupplier featureEnabled = () -> true;
boolean enabled = featureEnabled.getAsBoolean(); // true
```

`getAsBoolean()` fits when you need to defer reading a **zero-parameter condition**; for example, asking a provider whether a feature is enabled. If the lambda reads mutable configuration state, results across calls may differ; `BooleanSupplier` does not guarantee purity or thread safety.

### `Predicate` and primitive predicates returning boolean

```java
IntPredicate atLeast70 = value -> value >= 70;
LongPredicate positiveId = id -> id > 0L;
DoublePredicate finite = Double::isFinite;

System.out.println(atLeast70.test(85));         // true
System.out.println(positiveId.test(-1L));       // false
System.out.println(finite.test(Double.NaN));    // false
```

`IntPredicate`, `LongPredicate`, and `DoublePredicate` have default methods `and`, `or`, and `negate` to compose conditions. `and` and `or` **short-circuit**: if the result is already determined, the subsequent predicate does not need to run. Do not rely on side effects inside a predicate to guarantee a piece of code executes.

```java
IntPredicate between0And100 =
        ((IntPredicate) n -> n >= 0).and(n -> n <= 100);

System.out.println(between0And100.test(80));  // true
System.out.println(between0And100.test(120)); // false
```

### What if boolean is the **input**?

The JDK does not provide `BooleanFunction<R>` or `BooleanConsumer` in `java.util.function`. You can use the `Boolean` wrapper:

```java
Function<Boolean, String> stateLabel =
        value -> Boolean.TRUE.equals(value) ? "ON" : "OFF";

System.out.println(stateLabel.apply(Boolean.TRUE));  // ON
System.out.println(stateLabel.apply(Boolean.FALSE)); // OFF
System.out.println(stateLabel.apply(null));          // OFF
```

This is an intentional choice: `Boolean.TRUE.equals(value)` handles `null` under the convention "if not TRUE, then OFF". If `null` should be treated as an error, validate the input and throw an exception rather than silently picking OFF. For many boolean values, you can process `Stream<Boolean>`, but understand it is a **stream of wrapper objects**, unlike the three primitive streams `IntStream`, `LongStream`, and `DoubleStream`.

When you must express a `boolean → boolean` contract without boxing, you can define your own:

```java
@FunctionalInterface
interface BooleanOperator {
    boolean apply(boolean value);
}
```

This is an **application-defined interface**, not a JDK interface. For simple cases, using `boolean` directly is usually clearer than designing a custom abstraction.

## 5. Complete Java 17 program: filtering, transforming, and aggregating with primitives

Create the file **`PrimitiveFunctionsDemo.java`** and copy the entire program below. The example uses only the JDK and runs on Java 17 or later.

```java
import java.util.Arrays;
import java.util.function.*;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveFunctionsDemo {
    public static void main(String[] args) {
        // int: filter passing scores, bonus capped at 100.
        IntPredicate passing = score -> score >= 70;
        IntUnaryOperator bonus = score -> Math.min(100, score + 5);
        int[] scores = IntStream.of(42, 70, 85, 100)
                .filter(passing)
                .map(bonus)
                .toArray();
        System.out.println("Int result: " + Arrays.toString(scores));

        IntToLongFunction secondsToNanos =
                seconds -> seconds * 1_000_000_000L;
        System.out.println("Int to long: "
                + secondsToNanos.applyAsLong(3));

        ToIntFunction<String> textLength = String::length;
        IntFunction<String> scoreLabel = n -> "S-" + n;
        System.out.println("ToIntFunction: "
                + textLength.applyAsInt("Java"));
        System.out.println("IntFunction: " + scoreLabel.apply(75));

        // Demonstrate execution order of andThen/compose.
        IntUnaryOperator doubleIt = x -> x * 2;
        IntUnaryOperator plusThree = x -> x + 3;
        System.out.println("andThen: "
                + doubleIt.andThen(plusThree).applyAsInt(4));
        System.out.println("compose: "
                + doubleIt.compose(plusThree).applyAsInt(4));

        IntBinaryOperator add = Integer::sum;
        System.out.println("Int reduce: "
                + IntStream.rangeClosed(1, 4).reduce(0, add));

        // long: sum result can exceed int limits.
        LongPredicate large = n -> n >= 2_000_000_000L;
        LongUnaryOperator addHundred = n -> n + 100L;
        long longTotal = LongStream.of(
                        1_500_000_000L,
                        2_000_000_000L,
                        3_000_000_000L
                )
                .filter(large)
                .map(addHundred)
                .sum();
        System.out.println("Long result: " + longTotal);

        LongToDoubleFunction toBillions =
                n -> n / 1_000_000_000.0;
        LongToIntFunction checkedLongToInt = Math::toIntExact;
        System.out.println("Long to double: "
                + toBillions.applyAsDouble(2_500_000_000L));
        System.out.println("Long to int: "
                + checkedLongToInt.applyAsInt(42L));

        // double: handle measured quantities that may have fractional parts.
        DoublePredicate atLeastTwo = n -> n >= 2.0;
        DoubleUnaryOperator twice = n -> n * 2.0;
        double total = DoubleStream.of(1.5, 2.0, 3.5)
                .filter(atLeastTwo)
                .map(twice)
                .sum();
        System.out.println("Double result: " + total);

        DoubleToIntFunction nearestInt =
                n -> (int) Math.round(n);
        DoubleToLongFunction metersToMillimeters =
                meters -> Math.round(meters * 1000);
        System.out.println("Double to int: "
                + nearestInt.applyAsInt(2.6));
        System.out.println("Double to long: "
                + metersToMillimeters.applyAsLong(1.25));

        // boolean: condition source and predicate result.
        BooleanSupplier featureEnabled = () -> true;
        System.out.println("BooleanSupplier: "
                + featureEnabled.getAsBoolean());
        System.out.println("IntPredicate: " + passing.test(69));

        Function<Boolean, String> stateLabel =
                flag -> Boolean.TRUE.equals(flag) ? "ON" : "OFF";
        System.out.println("Boxed boolean: "
                + stateLabel.apply(Boolean.TRUE));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 PrimitiveFunctionsDemo.java
java PrimitiveFunctionsDemo
```

**Exact stdout**:

```text
Int result: [75, 90, 100]
Int to long: 3000000000
ToIntFunction: 4
IntFunction: S-75
andThen: 11
compose: 14
Int reduce: 10
Long result: 5000000200
Long to double: 2.5
Long to int: 42
Double result: 11.0
Double to int: 3
Double to long: 1250
BooleanSupplier: true
IntPredicate: false
Boxed boolean: ON
```

Verify the output:

- Initial `IntStream` is `42, 70, 85, 100`. Filtering `>=70` leaves `70, 85, 100`; adding 5 and capping at 100 yields `75, 90, 100`.
- `doubleIt.andThen(plusThree)` on 4 is `4 × 2 + 3 = 11`; `doubleIt.compose(plusThree)` is `(4 + 3) × 2 = 14`.
- `rangeClosed(1,4)` yields `1 + 2 + 3 + 4 = 10`.
- For `long`, `1_500_000_000` is filtered out. The remaining two become `2_000_000_100 + 3_000_000_100 = 5_000_000_200`, exceeding `Integer.MAX_VALUE` yet fitting within `long`.
- For `double`, `1.5` is filtered out, leaving `2.0` and `3.5`; after doubling, `4.0` and `7.0` sum to `11.0`. These sample numbers are exactly representable in binary, so the result is deterministic.
- `Math.round(2.6)` is `3L`, cast to `int` gives `3`; `Math.round(1.25 × 1000)` is `1250L`.

## 6. How do `IntStream`, `LongStream`, and `DoubleStream` relate to these interfaces?

Common methods on the three primitive streams:

| Pipeline operation | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| Filter | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Same-type transform | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Transform to object | `mapToObj(IntFunction<R>)` | `mapToObj(LongFunction<R>)` | `mapToObj(DoubleFunction<R>)` |
| Transform to another primitive | `mapToLong(IntToLongFunction)`, `mapToDouble(IntToDoubleFunction)` | `mapToInt(LongToIntFunction)`, `mapToDouble(LongToDoubleFunction)` | `mapToInt(DoubleToIntFunction)`, `mapToLong(DoubleToLongFunction)` |
| Traverse with action | `forEach(IntConsumer)` | `forEach(LongConsumer)` | `forEach(DoubleConsumer)` |
| Reduce two values | `reduce(IntBinaryOperator)` | `reduce(LongBinaryOperator)` | `reduce(DoubleBinaryOperator)` |
| Sum | `sum()` | `sum()` | `sum()` |

Example of `IntStream.mapToObj` vs. `map`:

```java
IntFunction<String> label = n -> "N=" + n;
List<String> labels = IntStream.of(1, 2, 3)
        .mapToObj(label)
        .toList();
// labels = ["N=1", "N=2", "N=3"]
```

`IntStream.map(IntUnaryOperator)` returns **`IntStream`**; `IntStream.mapToObj(IntFunction<R>)` returns **`Stream<R>`**. Choose the method based on the *output type*, not just the logical name of the function. The snippet is placed inside a class/method with imports `java.util.List`, `java.util.function.IntFunction`, and `java.util.stream.IntStream`.

### From `Stream<T>` to a primitive stream

Data often starts as a list of objects. Use `mapToInt`/`mapToLong`/`mapToDouble` to turn an object field into a primitive stream and then aggregate:

```java
record Product(String code, int quantity, long unitPriceInDong) {}

List<Product> items = List.of(
        new Product("BOOK", 2, 120000L),
        new Product("PEN", 3, 10000L)
);

ToLongFunction<Product> lineAmount =
        p -> p.unitPriceInDong() * p.quantity();

long total = items.stream().mapToLong(lineAmount).sum();
// total = 270000L
```

A `record` declared inside a block can be used as a **local record** in Java 17 methods; the snippet needs imports `List` and `ToLongFunction`. `unitPriceInDong()` is `long`, so multiplication uses `long` arithmetic. **`long` overflow is still possible** for large values; check bounds or use `Math.multiplyExact`/`Math.addExact` when overflow detection is needed. For money with decimal fractions, taxes, or rounding rules, use `BigDecimal` or the smallest currency unit per the business contract.

## 7. Boxing and unboxing: benefits and limitations

Compare two ways to write doubling:

```java
Function<Integer, Integer> boxedDouble = n -> n * 2;
IntUnaryOperator primitiveDouble = n -> n * 2;

int a = boxedDouble.apply(7);
int b = primitiveDouble.applyAsInt(7);
// a == 14, b == 14
```

With `Function<Integer,Integer>`, the boundary contract is **`Integer → Integer`**. When performing arithmetic `n * 2`, Java must extract the primitive value from `Integer` (*unboxing*); when returning the result as `Integer`, boxing may be required. With `IntUnaryOperator`, the contract is `int → int`. The compiler/JIT may optimize allocations in specific cases, so do not claim that every call to `Function<Integer,Integer>` definitely allocates a new object.

**Unboxing `null`** is a source of errors:

```java
Function<Integer, Integer> boxedDouble = n -> n * 2;
// boxedDouble.apply(null); // NullPointerException when unboxing n
```

Conversely, primitives `int`/`long`/`double`/`boolean` cannot represent `null`. If business data allows a "missing value" state, establish an explicit convention; you can use wrappers or `OptionalInt`, `OptionalLong`, `OptionalDouble` depending on semantics. `OptionalInt`/`OptionalLong`/`OptionalDouble` are **optional containers for primitives**, not functional interfaces.

### Should you always choose primitives?

No. For a few elements or APIs that mainly exchange objects, `Function<Integer,Integer>` can be simpler and integrate well. Choose primitive interfaces when:

1. The data's meaning is genuinely a non-nullable primitive.
2. The called API matches, such as `IntStream.map` or `Stream.mapToInt`.
3. You want to avoid boxing/unboxing on a hot path with many elements.
4. You have verified behavior, precision, and suitable primitive conversions.

If you must start with `Stream<Integer>` because the input is boxed data, you can use `mapToInt(Integer::intValue)` to unlock primitive operations; however, **if an element is `null`, unboxing will throw `NullPointerException`**.

## 8. `int` and `long`: representation limits, addition, and conversions

`int` is a 32-bit signed integer; `long` is a 64-bit signed integer. There is no automatic overflow check for ordinary addition or multiplication. For example:

```java
IntUnaryOperator addOne = n -> n + 1;
System.out.println(addOne.applyAsInt(Integer.MAX_VALUE));
// -2147483648 (int overflow in two's complement arithmetic)
```

When overflow is a business error, use `Math.addExact`, `Math.multiplyExact`, and `Math.toIntExact`:

```java
IntBinaryOperator checkedAdd = Math::addExact;
LongToIntFunction checkedNarrowing = Math::toIntExact;

System.out.println(checkedAdd.applyAsInt(20, 22)); // 42
System.out.println(checkedNarrowing.applyAsInt(42L)); // 42

// checkedAdd.applyAsInt(Integer.MAX_VALUE, 1)
// -> ArithmeticException: integer overflow
// checkedNarrowing.applyAsInt(3_000_000_000L)
// -> ArithmeticException: integer overflow
```

Lines that throw exceptions are commented out so they do not disrupt the program. With `LongBinaryOperator checkedLongAdd = Math::addExact`, the compiler picks the overload taking two `long`s based on the target type, detecting `long` overflow. The fact that `LongStream.sum()` returns `long` does not mean it automatically detects all overflows; if the sum can exceed `long` range, another calculation or representation is needed.

### `int`, `long`, and easily confused method names

Method names are consistent with the **return type**:

- `IntSupplier.getAsInt()`, `LongSupplier.getAsLong()`, `DoubleSupplier.getAsDouble()`.
- `IntUnaryOperator.applyAsInt(int)`, `LongUnaryOperator.applyAsLong(long)`, `DoubleUnaryOperator.applyAsDouble(double)`.
- `IntFunction<R>.apply(int)` returns **`R`**, not necessarily `int`.
- `ToIntFunction<T>.applyAsInt(T)`, `ToLongFunction<T>.applyAsLong(T)`, `ToDoubleFunction<T>.applyAsDouble(T)`.

That is why `IntFunction<String> fn = n -> "N=" + n; fn.apply(3)` is right; `fn.applyAsInt(3)` does not exist.

## 9. `double`: precision, NaN, Infinity, and aggregation

`double` is an IEEE 754 binary floating-point number. It suits many engineering measurements, data analyses, and problems that tolerate floating-point arithmetic error. However, not every decimal number is represented exactly:

```java
DoubleBinaryOperator add = Double::sum;
double result = add.applyAsDouble(0.1, 0.2);
System.out.println(result); // 0.30000000000000004
```

Therefore, do not compare floating-point results with `==` when "approximately equal" is meant; use an error tolerance appropriate to the unit and data range. For **decimal currency** that must be calculated exactly by business rules, prefer `BigDecimal` or representing the smallest currency unit as an integer, along with proper scale/rounding handling.

### Handling special values

`DoublePredicate` is useful for filtering out non-finite values:

```java
DoublePredicate finite = Double::isFinite;
double[] clean = java.util.stream.DoubleStream
        .of(2.5, Double.NaN, Double.POSITIVE_INFINITY, 3.5)
        .filter(finite)
        .toArray();
// clean = [2.5, 3.5]
```

- `Double.NaN` (Not a Number) is not equal to itself under `==`.
- `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` represent infinity.
- `Double.isFinite` returns `false` for NaN and infinity values.
- `DoubleStream.sum()` can be affected by order and rounding error; floating-point addition is not strictly associative in all cases. A sum in a parallel stream may differ slightly from a sequential stream, even for the same business operation.
- `Math.round(double)` has special rules for NaN and out-of-range values. Validate input data if converting to integers is a critical step.

An example of an input-boundary rule:

```java
DoublePredicate accepted =
        Double::isFinite;
DoubleUnaryOperator convertMetersToCentimeters = m -> m * 100.0;

double[] centimeters = DoubleStream.of(1.5, Double.NaN, 2.25)
        .filter(accepted)
        .map(convertMetersToCentimeters)
        .toArray();
// centimeters = [150.0, 225.0]
```

## 10. Multi-parameter or object-combining interfaces

Sometimes a function must accept an object **and** a primitive. The JDK provides these additional interfaces:

| Interface | Signature | When useful |
| --- | --- | --- |
| `ObjIntConsumer<T>` | `void accept(T,int)` | Passing an `int` index/quantity into an object |
| `ObjLongConsumer<T>` | `void accept(T,long)` | Accepting an object and a `long` timestamp/quantity |
| `ObjDoubleConsumer<T>` | `void accept(T,double)` | Accepting an object and a `double` measurement |
| `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` | Combining two objects into an `int` |
| `ToLongBiFunction<T,U>` | `long applyAsLong(T,U)` | Combining two objects into a `long` |
| `ToDoubleBiFunction<T,U>` | `double applyAsDouble(T,U)` | Combining two objects into a `double` |

Example of `ObjIntConsumer`:

```java
ObjIntConsumer<StringBuilder> appendNumber =
        (builder, number) -> builder.append(number);

StringBuilder builder = new StringBuilder("Order-");
appendNumber.accept(builder, 7);
System.out.println(builder); // Order-7
```

This snippet intentionally has a **local side effect** on `builder`. In practice, do not let multiple threads concurrently call `appendNumber` on the same unprotected `StringBuilder`. A functional interface with primitives in its signature **does not mean the lambda is pure, thread-safe, or allocation-free**.

## 11. Common mistakes when learning primitive interfaces

**Mistake 1 — Writing a primitive type as a generic type argument.** `Function<int,long>` does not compile. Use `IntToLongFunction` or `Function<Integer,Long>` depending on the API.

**Mistake 2 — Confusing `IntFunction` with `ToIntFunction`.** The first takes `int` and returns `R`; the second takes `T` and returns `int`. Calling the wrong `apply`/`applyAsInt` causes a compile error.

**Mistake 3 — Believing every primitive has the exact same full set of interfaces.** `boolean` has no standard `BooleanUnaryOperator`, `BooleanFunction`, or `BooleanStream` in Java 17's `java.util.function`/`java.util.stream`. Use `BooleanSupplier`, predicates, the `Boolean` wrapper, or an application-specific interface as needed.

**Mistake 4 — Equating primitives with overflow-free or error-free arithmetic.** `IntStream.sum` can overflow `int`, `LongStream.sum` can overflow `long`, and `DoubleStream.sum` has floating-point error. Choosing a data type does not replace range checks.

**Mistake 5 — Forgetting `null` in wrappers.** `Stream<Integer>.mapToInt(Integer::intValue)` requires unboxing and can fail if it encounters `null`. Primitive streams have no `null` elements; when values can be absent, choose an explicit policy for representing missing data.

**Mistake 6 — Using a side-effecting lambda to accumulate in a parallel stream.** `IntStream.parallel().forEach(n -> shared[0] += n)` has a data race if multiple threads write to the same array element. Prefer `sum`, `reduce`, or an appropriate collector; if shared state is truly needed, use synchronization and clear ownership.

**Mistake 7 — Composing `andThen`/`compose` in the wrong order.** `IntUnaryOperator`, `LongUnaryOperator`, and `DoubleUnaryOperator` have `andThen` and `compose` just like `UnaryOperator<T>`; results differ when two operations do not commute.

**Mistake 8 — Skipping input conditions.** `DoublePredicate` can receive NaN/Infinity; `LongToIntFunction` can lose data when narrowing; `IntToLongFunction` can still overflow `long` after many operations. Separate validation from the main transformation or make validation explicit.

**Mistake 9 — Assuming primitive streams are always faster than `Stream<Integer>` in every situation.** Primitive interfaces reduce boxing at their respective steps, but pipelines with object sources, I/O, or multi-stage transformations still have other costs. Measure with an appropriate benchmark before drawing performance conclusions.

**Mistake 10 — Using `double` for money without rounding rules.** If the problem requires exact monetary representation, primitive interfaces may not suit the *entire* monetary pipeline; use `BigDecimal` and generic functional interfaces when needed.

## 12. Exercises with reference results

1. Create an `IntPredicate` checking even numbers and an `IntUnaryOperator` squaring them. Apply to `IntStream.rangeClosed(1,6)`: filtering gives `2,4,6`, transforming gives `4,16,36`; the sum must be `56`.
2. Write an `IntToLongFunction` converting seconds to nanoseconds, test `3`, and explain why the literal `1_000_000_000L` matters for large multiplications.
3. With `LongStream.of(1_500_000_000L, 2_000_000_000L, 3_000_000_000L)`, filter numbers from 2 billion up and add 100 to each. The exact sum is `5000000200`. Why is `int` unsuitable?
4. Create a `DoublePredicate` rejecting `NaN`/infinity and a `DoubleUnaryOperator` multiplying by 100. Apply to `DoubleStream.of(1.5, Double.NaN, 2.25)` and compare the result with `[150.0, 225.0]`.
5. Write a `ToIntFunction<String>` returning string length and an `IntFunction<String>` turning length into `"length=" + n`. From `Stream.of("Java", "API")`, use `mapToInt` then `mapToObj` to get `["length=4", "length=3"]`.
6. Explain the difference between `BooleanSupplier` and `IntPredicate`: which takes an input? Which is suitable for `IntStream.filter`? State why there is no `BooleanStream` in Java 17.
7. Demonstrate that `andThen` differs from `compose` with "multiply by 2" and "add 3" when the input is `4`: `11` and `14`, respectively.
8. Try `Math.toIntExact(3_000_000_000L)` to observe `ArithmeticException`. Then use `LongToIntFunction` to express a checked conversion.
9. Determine when to use `Function<Integer,Integer>`, when to use `IntUnaryOperator`, and when to use `ToIntFunction<T>`. Evaluate input/output types, null requirements, and the API accepting the mapper.

## 13. Application checklist

When choosing a primitive functional interface, answer in order:

1. **What is the input?** A primitive `int`, `long`, floating-point `double`, an object, two inputs, or no input?
2. **What is the output?** `boolean`, a primitive of the same type, a different primitive, an object, or no return value?
3. **Which mapper type does the API expect?** `map`, `mapToObj`, `mapToInt`, `filter`, `forEach`, and `reduce` have different parameter types.
4. **Can null, overflow, NaN, or Infinity occur?** Choose a concrete data contract and error handling.
5. **Are there side effects or shared mutable state?** Keep the pipeline easy to reason about, especially when using parallel streams.
6. **Is boxing optimization actually needed?** Start with a clear API and benchmark when data is large enough.

Choosing the right interface lets the program express **the transformation's meaning directly in its types**, reduces unnecessary conversions, and connects naturally with the Java Stream API. Still, correctness comes from business rules, numeric bounds, missing-data handling, and controlling side effects.
