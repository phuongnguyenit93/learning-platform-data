# Why Doesn't `<T extends Number>` Provide Arithmetic Operators on `T`?

A common misconception when learning Java Generics is: if you declare `<T extends Number>`, variables of type `T` should surely support arithmetic operators `+`, `-`, `*`, and `/` like integers or floating-point numbers. **That is not true in Java.**

`Number` is an **abstract class** representing numeric types as objects. The bound `T extends Number` tells the compiler that a value of type `T` has `Number`'s methods, such as `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`. However, this bound **does not turn `T` into a primitive type**, does not define addition for every subclass, and does not create custom operators. Therefore, the expression `a + b` with two variables typed as `T extends Number` **does not compile**.

This lesson distinguishes generic type checking from Java's arithmetic operator mechanism, explains why unboxing does not automatically apply to `T`, shows intentional value conversions, and presents API design options when you genuinely need to add, subtract, or compare numbers of multiple types.

## 1. Reading the Meaning of `<T extends Number>` Correctly

Consider the generic method:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

This is an **illustrative method** placed inside a Java class. You can call it with `Integer`, `Long`, `Double`, `BigDecimal`, `BigInteger`, or another valid subclass of `Number`. The reason the compiler accepts `value.doubleValue()` is that `Number` exposes that method.

However, the signature:

```java
static <T extends Number> T add(T a, T b) {
    // return a + b; // COMPILE ERROR
    throw new UnsupportedOperationException();
}
```

is different. The line `return a + b` is commented out because Java's arithmetic addition operator has no way to apply generally to two **references of type `T`**. The `throw` part only provides a valid method body to illustrate the signature; it is **not** an implementation of addition.

Distinguish clearly:

| Concept | Does `<T extends Number>` guarantee it? | Why? |
|---|---|---|
| `T` is a reference type satisfying `Number` | Yes | This is the **upper bound** of the type parameter. |
| `value.doubleValue()` can be called | Yes | The method is declared on `Number`. |
| `value.intValue()` can be called | Yes | This is a method of `Number`. |
| `a + b` with `T a, T b` | **No** | There is no general arithmetic operator on `Number` objects. |
| `a.compareTo(b)` can be called | **No** from this bound alone | `Number` does not implement `Comparable<Number>`. |
| The result of addition automatically has type `T` | **No** | There is no contract producing a new `T` value. |
| Every conversion to `double` is exact | **No** | Conversion can round or lose information. |

**An upper bound constrains which members can be used and the type relationship**, not a promise that all subclasses support the same operator with the same rules.

## 2. Which Types Does Java Define Arithmetic Operators For?

Integer and floating-point arithmetic operators such as `+`, `-`, `*`, and `/` primarily operate on **primitive numeric types** (`byte`, `short`, `char`, `int`, `long`, `float`, `double`) after *binary numeric promotion* rules. Java also supports **unboxing** from the corresponding standard wrapper classes when the operator context requires it.

Example inside a method:

```java
int a = 4;
long b = 5L;
System.out.println(a + b); // 9, result has type long

Integer x = 4;
Integer y = 5;
System.out.println(x + y); // 9: Integer auto-unboxes to int
```

In the second example, the compiler **knows exactly** that `x` and `y` have type `Integer`, the standard wrapper for `int`. Therefore it applies unboxing and integer addition.

Conversely:

```java
Number first = Integer.valueOf(4);
Number second = Integer.valueOf(5);

// System.out.println(first + second); // INVALID: Number + Number
```

Even though both runtime objects are `Integer`, the **static type** of both variables is `Number`. Java does not define unboxing from the general `Number` type. The compiler does not inspect the runtime class of each operand and pick an operator at runtime.

The same happens with a type parameter `T` bounded by `Number`: although `T` is narrower than or equal to `Number` per the bound, the compiler still does not know a unified addition operation for every valid `T`.

### Easily confused cases

- `Integer + Integer`: valid via unboxing.
- `Double + Integer`: valid via unboxing and numeric promotion.
- `Number + Number`: **invalid**.
- `T + T` in `<T extends Number>`: **invalid**.
- `BigDecimal + BigDecimal`: **invalid** because `BigDecimal` is an object class for which Java does not overload `+`; you must call `add`.
- `String + object`: valid as **string concatenation**, not numeric addition; do not use that phenomenon as evidence that `Number` supports operators.

There is no **user-defined operator overloading** mechanism for `+` on an arbitrary Java class.

## 3. Java 17 Example: Same Value, Different Static Type, Different Valid Operations

Save the program below as **`NumberBoundaryDemo.java`**:

```java
public class NumberBoundaryDemo {
    public static void main(String[] args) {
        Integer wrappedA = 4;
        Integer wrappedB = 5;
        System.out.println(wrappedA + wrappedB);

        Number first = wrappedA;
        Number second = wrappedB;

        // Cannot write: first + second
        System.out.println(first.intValue() + second.intValue());
        System.out.println(first.doubleValue() + second.doubleValue());

        Number decimal = Double.valueOf(2.9);
        System.out.println(decimal.intValue());
        System.out.println(decimal.doubleValue());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 NumberBoundaryDemo.java
java NumberBoundaryDemo
```

`stdout` output:

```text
9
9
9.0
2
2.9
```

Three points here are very noteworthy:

1. `wrappedA + wrappedB` compiles because both have static type `Integer`, enabling unboxing.
2. `first + second` will not compile because both have static type `Number`. Calling `intValue()` or `doubleValue()` before the operation is **a conversion chosen by the programmer**, completely different from adding `Number` directly.
3. `decimal.intValue()` returns `2`, not `2.9`. Converting to `int` drops the fractional part (for finite values in valid range); thus **type conversion can lose data**.

The program proves that a runtime object holding a number is not enough for the compiler to allow operators. **The static type and the operator's contract are the deciding factors.**

## 4. Why Can't Java Automatically Define Addition for Every `Number`?

`Number` is an abstraction for many kinds of numbers with different characteristics. Common subclasses include:

- `Byte`, `Short`, `Integer`, `Long`: wrappers for their corresponding primitive integers.
- `Float`, `Double`: binary floating-point real number representations.
- `BigInteger`: arbitrary-precision integers, with addition `add(BigInteger)`.
- `BigDecimal`: decimal numbers with controlled decimal precision, with `add(BigDecimal)`.
- Other subclasses that may be defined by libraries or applications, with their own semantics and limits.

If a method receives `Number a` and `Number b`, it would have to answer:

- If `a` is `Integer` while `b` is `Double`, should the result be `Integer`, `Double`, `BigDecimal`, or another type?
- If both are `Long` and the sum exceeds `long` bounds, should the API overflow, throw an error, or return `BigInteger`?
- If `a` is `BigDecimal("0.1")`, must addition preserve **decimal precision**?
- If `a` is a custom `Number` subclass, how do you construct an instance of the same class to preserve type `T`?
- If a `null` value is present, should the API reject it, skip it, or treat it as zero?

Java does not automatically pick one answer for all those cases. `Number` **does not declare `add(Number)`**, nor does it have an abstract method or operator guaranteeing "return a matching `T`".

Therefore, knowing only `T extends Number`, you know **how to convert the value to several primitive types**, not **how to perform arithmetic closed over `T`**.

## 5. Approach 1: Convert to an Explicit Target Primitive Type

If business requirements permit computing in `double`, you can write a utility:

```java
static <T extends Number> double sumAsDouble(
        java.util.List<T> numbers) {
    double total = 0.0;
    for (T number : numbers) {
        total += number.doubleValue();
    }
    return total;
}
```

This is an **illustrative method in a class**. It accepts a list of `T` objects and sums the values converted to `double`. The function **returns `double`, not `T`**. If you tried to return `T` from a `double` result, the compiler has no safe, general way to convert back for every subclass of `Number`.

### Complete program

Save **`SumAsDoubleDemo.java`**:

```java
import java.util.List;

public class SumAsDoubleDemo {
    static <T extends Number> double sumAsDouble(List<T> values) {
        double total = 0.0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static double sumNumbers(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(1.5, 2.25);

        System.out.println(sumAsDouble(integers));
        System.out.println(sumAsDouble(decimals));
        System.out.println(sumNumbers(List.of(1, 2.5, 3L)));
    }
}
```

Run with Java 17:

```bash
javac -encoding UTF-8 SumAsDoubleDemo.java
java SumAsDoubleDemo
```

`stdout`:

```text
6.0
3.75
6.5
```

Analysis:

- In `sumAsDouble`, `<T extends Number>` gives list elements type `T` and allows calling `doubleValue()`.
- In `sumNumbers`, no **named** type parameter is needed, because the algorithm only reads elements as `Number` and returns `double`. `List<? extends Number>` suffices to accept `List<Integer>`, `List<Double>`, and other numeric lists.
- Both versions perform **arithmetic on `double`**, not direct addition on `T`.
- `List.of(1, 2.5, 3L)` is an unmodifiable list containing numeric objects, accepted by the `List<? extends Number>` parameter.

If a method does not need to preserve a type relationship between parameters or the return value, **a simple wildcard can be more readable than declaring `<T>`**. Only use a named type parameter when it genuinely expresses a relationship that must be preserved.

## 6. Warning: `doubleValue()` Is Not an Exact Conversion for Every Type

Even though `doubleValue()` is available on `Number`, it is **not a lossless conversion for all numbers**. `double` is an IEEE 754 binary floating-point type with roughly 53 bits of significand precision, and cannot exactly represent every large integer or every decimal fraction.

Example:

```java
long exact = 9_007_199_254_740_993L;
double converted = Long.valueOf(exact).doubleValue();

System.out.println(converted == 9_007_199_254_740_992.0);
```

This is a **snippet inside a method**; the result is `true` because two consecutive integers in that value range can round to the same `double` value. Thus converting from a large `long` to `double` can lose the last unit.

A standalone program to demonstrate:

Save the file **`PrecisionDemo.java`**:

```java
import java.math.BigDecimal;

public class PrecisionDemo {
    public static void main(String[] args) {
        Number large = 9_007_199_254_740_993L;
        double approximate = large.doubleValue();

        System.out.println(
                approximate == 9_007_199_254_740_992.0);
        System.out.println(new BigDecimal("0.1")
                .add(new BigDecimal("0.2")));
        System.out.println(0.1 + 0.2);
    }
}
```

Run:

```bash
javac -encoding UTF-8 PrecisionDemo.java
java PrecisionDemo
```

`stdout`:

```text
true
0.3
0.30000000000000004
```

**Choosing the calculation type** depends on business requirements:

- Measurement or simulation data tolerating approximation: `double` may fit.
- Currency or values requiring decimal precision: typically use `BigDecimal` with explicit scale/rounding policies.
- Very large integers requiring exactness: consider `BigInteger`.
- Fixed-width integers: `int`/`long` have limits; consider overflow checks with `Math.addExact` and related functions.

Do not put `doubleValue()` into every generic utility just to make `+` compile; you are **deciding a new arithmetic model**, not merely making "equivalent syntax".

## 7. Approach 2: Call the Concrete Numeric Class's Specific Operation

When the input type is known, prefer that type's dedicated arithmetic API instead of trying to write `T + T`. For example:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

// Illustrative snippet inside a method body:
BigDecimal money = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

BigInteger big = new BigInteger("99999999999999999999")
        .add(BigInteger.ONE);
```

`BigDecimal.add(...)` and `BigInteger.add(...)` are methods defined by concrete classes. They are **not** declared by `Number`, so an expression typed as `T extends Number` cannot call `a.add(b)` without another bound that actually supplies a matching method contract.

A complete Java 17 example:

Save **`ConcreteArithmeticDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class ConcreteArithmeticDemo {
    public static void main(String[] args) {
        BigDecimal money = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        BigInteger huge = new BigInteger("99999999999999999999")
                .add(BigInteger.ONE);

        int safe = Math.addExact(20, 22);
        System.out.println(money);
        System.out.println(huge);
        System.out.println(safe);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConcreteArithmeticDemo.java
java ConcreteArithmeticDemo
```

`stdout`:

```text
0.3
100000000000000000000
42
```

Note creating `BigDecimal` from a **decimal string** like `"0.1"` to specify the exact desired value; writing `new BigDecimal(0.1)` usually carries the binary approximation of the `double` literal. `BigDecimal.valueOf(0.1)` behaves more appropriately in many situations, though when financial values originate from decimal text, the string constructor expresses intent most clearly.

## 8. Approach 3: Pass the Addition Operation from Outside via `BinaryOperator<T>`

If you genuinely want a general algorithm that **returns the exact type `T`**, the algorithm must be supplied with a way to add two `T` values into one `T` value. In Java, this capability can be represented by a **strategy** or a `BinaryOperator<T>` function.

Signature:

```java
static <T extends Number> T sum(
        java.util.List<T> values,
        T zero,
        java.util.function.BinaryOperator<T> add) {
    T result = zero;
    for (T value : values) {
        result = add.apply(result, value);
    }
    return result;
}
```

This is an **illustrative method**, which must be placed in a class. The algorithm does not write `result + value`. It calls `add.apply(result, value)` and lets the caller decide the arithmetic matching `T`.

### Complete program: the same algorithm for `Integer` and `BigDecimal`

Save **`NumericStrategyDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.function.BinaryOperator;

public class NumericStrategyDemo {
    static <T extends Number> T sum(
            List<T> values,
            T zero,
            BinaryOperator<T> addition) {
        T result = zero;
        for (T value : values) {
            result = addition.apply(result, value);
        }
        return result;
    }

    public static void main(String[] args) {
        Integer integerTotal = sum(
                List.of(1, 2, 3),
                0,
                Integer::sum);

        BigDecimal decimalTotal = sum(
                List.of(
                    new BigDecimal("0.1"),
                    new BigDecimal("0.2")
                ),
                BigDecimal.ZERO,
                BigDecimal::add);

        System.out.println(integerTotal);
        System.out.println(decimalTotal);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 NumericStrategyDemo.java
java NumericStrategyDemo
```

`stdout`:

```text
6
0.3
```

In the first call, `T` is inferred as `Integer` and the caller passes `Integer::sum`. In the second call, `T` is inferred as `BigDecimal` and addition is passed via `BigDecimal::add`.

**Why does this approach work?** Java does not need to know how to add an arbitrary `T`; it only needs to ensure the `BinaryOperator<T>` function accepts two `T` values and returns a `T` value. The caller supplies the concrete type's addition definition.

Several design notes:

- `zero` must be an initial value compatible with the chosen addition; the compiler checks **types**, not that it is a mathematical identity element.
- `Integer::sum` uses `int` addition, so **overflow is still possible**. If overflow detection is required, you can use `Math::addExact` in an `Integer` context.
- `addition` can be written incorrectly by the user, throw exceptions, or have side effects. Business validation is still needed.
- If the list contains `null`, an operator such as `Integer::sum` can throw `NullPointerException` upon unboxing.
- The `T extends Number` bound is syntactically unnecessary if the utility only calls `addition.apply` without using `Number` members. You can choose plain `<T>` if you want the algorithm to apply to types with other combining operations, such as string concatenation.

**Key point:** `BinaryOperator<T>` is a solution that provides an **operation contract** from outside. It does not make Java "natively support the `+` operator on `T`".

## 9. Approach 4: Design an Interface Providing Addition

If your application owns custom or domain numeric classes, you can define an interface representing the ability to add. The generic bound will rely on **the contract that actually has the addition method**, not on `Number`.

Example of an integer quantity type:

```java
interface Addable<T> {
    T add(T other);
}
```

This is a generic interface; a domain class `Quantity` can implement it and define `add`. If you want to use all `Number` methods **and** addition capability, declare a dual-bounded type:

```java
static <T extends Number & Addable<T>> T add(T a, T b) {
    return a.add(b);
}
```

This is an **illustrative method**, which must be placed in a class. `Number` is a class bound so it comes first; `Addable<T>` is an interface bound following `&`. Here the compiler accepts `a.add(b)` **because the `Addable<T>` interface declares the `add` method**, not because `Number` provides addition.

### Runnable example with `Quantity extends Number`

Save **`AddableNumberDemo.java`**:

```java
public class AddableNumberDemo {
    interface Addable<T> {
        T add(T other);
    }

    static final class Quantity extends Number
            implements Addable<Quantity> {
        private final int value;

        Quantity(int value) {
            this.value = value;
        }

        @Override
        public Quantity add(Quantity other) {
            return new Quantity(Math.addExact(value, other.value));
        }

        @Override
        public int intValue() {
            return value;
        }

        @Override
        public long longValue() {
            return value;
        }

        @Override
        public float floatValue() {
            return value;
        }

        @Override
        public double doubleValue() {
            return value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    static <T extends Number & Addable<T>> T plus(T a, T b) {
        return a.add(b);
    }

    public static void main(String[] args) {
        Quantity a = new Quantity(20);
        Quantity b = new Quantity(22);
        System.out.println(plus(a, b));
    }
}
```

Run:

```bash
javac -encoding UTF-8 AddableNumberDemo.java
java AddableNumberDemo
```

`stdout`:

```text
42
```

Why does `plus(a,b)` compile? `Quantity` **extends `Number` and implements `Addable<Quantity>`**, so it satisfies both bounds simultaneously. `Math.addExact` makes `Quantity.add` throw `ArithmeticException` instead of silently overflowing when adding two out-of-range `int`s.

Do not try to force JDK classes like `Integer` or `BigDecimal` into a self-defined `Addable<T>` interface: they do not naturally implement this interface, and you cannot modify their source code. For built-in numeric classes, **passing a `BinaryOperator<T>`** as in the previous section is usually more convenient.

## 10. Comparison Operators Also Need Separate Consideration

`T extends Number` is not enough to call `compareTo`:

```java
static <T extends Number> boolean greater(T a, T b) {
    // return a.compareTo(b) > 0; // Invalid: Number does not declare compareTo
    return a.doubleValue() > b.doubleValue();
}
```

The method above is **illustrative code with a valid body**, yet it compares after converting to `double`, so precision can be lost. It is not equivalent to exact comparison for every `Number` kind.

If you need natural ordering defined by the object, add a `Comparable` bound:

```java
static <T extends Number & Comparable<? super T>> T maximum(
        T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

This snippet is a method placed in a class. The compiler allows `compareTo` because `Comparable<? super T>` supplies the comparison contract; `Number` still only provides numeric conversion capabilities.

A complete Java 17 program:

Save **`NumberComparableDemo.java`**:

```java
public class NumberComparableDemo {
    static <T extends Number & Comparable<? super T>>
    T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        System.out.println(maximum(5, 9));
        System.out.println(maximum(2.5, 1.25));
    }
}
```

Run:

```bash
javac -encoding UTF-8 NumberComparableDemo.java
java NumberComparableDemo
```

`stdout`:

```text
9
2.5
```

The syntax `<T extends Number & Comparable<? super T>>` belongs to **multiple bounds**. If there is a class bound, it must come first; interfaces follow.

Another point: wrappers like `Integer` and `Double` have `compareTo`, yet do not automatically permit cross-comparison via a shared `Comparable<Number>`. Do not assume `maximum(5, 2.5)` has a valid `T` merely because both are numbers.

## 11. Integer Overflow: A "Valid" Addition Can Still Be Wrong for Business Logic

Even when the type is fixed as `Integer`, the `+` operator or `Integer.sum` uses standard `int` addition. Java does not automatically throw an error when `int` overflows in ordinary addition.

Create **`OverflowDemo.java`**:

```java
public class OverflowDemo {
    public static void main(String[] args) {
        int ordinary = Integer.MAX_VALUE + 1;
        System.out.println(ordinary);

        try {
            int checked = Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println(checked);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 OverflowDemo.java
java OverflowDemo
```

`stdout`:

```text
-2147483648
overflow detected
```

The general problem is not merely making addition compile, but **defining an arithmetic policy**: accept overflow, reject overflow, or use a type with a larger value range. `T extends Number` does not solve this policy.

For decimal numbers, you must also distinguish binary rounding errors of `double` from `BigDecimal`'s scale/rounding rules. For instance, `BigDecimal.divide` can throw `ArithmeticException` on non-terminating decimal quotients if an appropriate rounding mode is not specified.

## 12. When Is `<T extends Number>` Not Needed?

A generic bound is useful only if it expresses a type relationship the API needs to check. For example:

```java
static double sum(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

This is an **illustrative method** requiring `import java.util.List` and placement inside a class. If there is no type relationship to preserve between input, output, or multiple parameters, `List<? extends Number>` is clear enough: the list serves as a source supplying `Number` values, while the algorithm converts to `double`.

Conversely, to **preserve type `T` from input to result**:

```java
static <T extends Number> T reduce(
        List<T> values,
        T zero,
        java.util.function.BinaryOperator<T> op) {
    T result = zero;
    for (T value : values) {
        result = op.apply(result, value);
    }
    return result;
}
```

Here type parameter `T` matters because it links the element type, initial value, operator, and result. However, the `extends Number` bound may still be unnecessary if the operation only uses `op.apply`. If you want the function to handle any values with a combining operation generally, the signature `<T> T reduce(...)` is even more flexible.

Selection guidelines:

- **Only need to read numbers to convert to primitive:** accepting `Number` or `? extends Number` suffices.
- **Need a concrete `double` or `long` result:** declare the result type explicitly; document precision and overflow.
- **Need to preserve `T`:** pass an operation such as `BinaryOperator<T>`, or constrain with an interface carrying the actual operation.
- **Need exact decimal numbers:** choose `BigDecimal` as the input/output contract and use its API instead of over-generalizing.
- **Need comparison:** require `Comparable<? super T>` or accept a suitable `Comparator<? super T>`.

## 13. Common Compile or Design Errors

| Wrong code or flawed reasoning | Actual issue | How to handle |
|---|---|---|
| `static <T extends Number> T add(T a,T b) { return a+b; }` | The `+` operator does not work on `T`. | Pick a concrete numeric type, or pass the addition operation. |
| `Number a=1, b=2; a+b` | `Number` is not auto-unboxed by Java. | Convert explicitly and accept the chosen arithmetic rules. |
| `T total = 0;` | Primitive literal `0` does not automatically have an arbitrary type `T`. | Accept `T zero` from the caller or an appropriate factory. |
| `return (T) Double.valueOf(a.doubleValue()+b.doubleValue());` | Unsafe cast; the result is not necessarily of the requested type `T`. | Return `double` or use a passed-in operator returning `T`. |
| `a.add(b)` with `T extends Number` | `Number` does not declare `add`. | Use concrete `BigDecimal` or a bound with `Addable<T>`. |
| `a.compareTo(b)` with `T extends Number` | `Number` does not declare `compareTo`. | Add bound `Comparable<? super T>` or accept a `Comparator`. |
| Calling `doubleValue()` and assuming no data changes | Precision loss on large numbers or fractional parts. | Check requirements; use `BigDecimal`/`BigInteger` when appropriate. |
| Using `Integer::sum` and thinking it cannot overflow | `int` addition can overflow. | `Math::addExact`, a wider type, or an appropriate overflow policy. |
| Writing a generic currency adder that converts via `double` | Can corrupt monetary values. | Design an API accepting/returning `BigDecimal` with clear scale and rounding rules. |
| Using the `+` operator on `BigDecimal` | Java does not overload arithmetic operators for classes. | `a.add(b)`. |
| Assuming the compiler picks `+` based on runtime class | Java checks operators via static types and unboxing/numeric promotion rules. | Design explicit arithmetic signatures at compile time. |

Error examples are used to **recognize errors**, not as Java code to run as-is.

## 14. Process for Designing a Generic Numeric Utility

When you need to write a function handling multiple numeric kinds, determine step by step:

1. **What are the input numeric types?** Only `Integer` and `Long`, or also `BigDecimal`, `BigInteger`, `Double`, and other `Number` subclasses?
2. **What type must the result have?** `double`, `BigDecimal`, or preserving type `T`? This is the most important API decision.
3. **How much precision loss is acceptable?** Money calculations, very large counts, and approximate measurements should not share the same policy.
4. **Can the arithmetic overflow?** If using `int`/`long`, consider `Math.addExact` or switching types per business requirements.
5. **Where does the operation come from?** If using `T extends Number`, only `Number`'s conversion methods exist. To add and return `T`, an additional operator/strategy is needed.
6. **Is a type parameter `T` needed to preserve a type relationship?** If only reading and converting to `double`, wildcard `? extends Number` may be simpler.
7. **How are `null` values, empty lists, and exceptions handled?** Runtime conditions must be specified separately.
8. **Should compiler warnings be checked?** Avoid raw types, unchecked casts, or roundabout casts meant to mask the `T + T` error.
9. **Test boundary data**: negative numbers, very large numbers, decimals, empty lists, overflow, and disallowed values.

## 15. Self-Check

**Question 1.** Why does `Integer a=1, b=2; a+b` compile while `Number a=1, b=2; a+b` does not compile, even though both runtime objects might be `Integer`?

**Question 2.** With `<T extends Number>`, which conversion methods does the compiler guarantee? Does it guarantee `add(T)` or `compareTo(T)`?

**Question 3.** If you write `double total = a.doubleValue() + b.doubleValue()`, what has changed about the result contract? Why can that cause bugs when handling money or large integers?

**Question 4.** How can you write a function that adds two `T`s and returns exact `T` without unchecked casts, when classes like `Integer` and `BigDecimal` do not share a common `add`?

**Question 5.** Distinguish `<T extends Number>` from `<T extends Number & Addable<T>>` when writing `a.add(b)`.

**Question 6.** What does `<T extends Number & Comparable<? super T>>` enable that `<T extends Number>` cannot?

**Answer hints:** (1) `Integer` is a wrapper class unboxed by Java, whereas `Number` is not among types with direct unboxing conversion. (2) Methods such as `intValue()` and `doubleValue()`; `Number` does not declare `add` or `compareTo`. (3) The operation switches to `double`, does not return `T`, and can lose precision. (4) Pass `BinaryOperator<T>`, or use an application-defined arithmetic interface. (5) The second bound adds the `Addable<T>` contract containing `add`. (6) The `Comparable` bound guarantees valid `compareTo` calls for natural-order comparison.

**Key takeaway:** **`<T extends Number>` does not mean `T` has arithmetic operators.** Java only permits calling members guaranteed by bounds, while operators `+`, `-`, `*`, and `/` depend on primitive numeric types and specific unboxing rules. To handle multiple numeric types, **explicitly choose the result type and precision policy**, or **supply an operation contract** via an interface or strategy like `BinaryOperator<T>`. Avoid unchecked casts to simulate generic addition that Java Generics do not actually guarantee.