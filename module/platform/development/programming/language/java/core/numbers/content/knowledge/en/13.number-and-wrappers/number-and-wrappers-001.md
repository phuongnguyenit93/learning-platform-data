# `Number` as an Abstract Class and Value-Conversion Contract in Java

In Java, `java.lang.Number` is an **abstract class** serving as the common superclass for many numeric classes: `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `BigInteger`, `BigDecimal`, and several concurrent numeric classes such as `AtomicInteger` and `AtomicLong`. Its purpose is not to provide a "universal numeric type that can directly add, subtract, multiply, and divide," but to provide an **object-level interface for converting numeric values into several primitive types**.

```java
Number a = Integer.valueOf(42);
Number b = Long.valueOf(4_294_967_297L);
Number c = new java.math.BigDecimal("12.75");

System.out.println(a.intValue()); // 42
System.out.println(b.intValue()); // 1: no longer preserves the full long value.
System.out.println(c.intValue()); // 12: fractional part is discarded.
```

All three share the reference type `Number`, but **the conversion behavior depends on the concrete class of the object**. The `intValue()` method does not guarantee exactness: it may lose the fractional part, lose magnitude, drop significant bits, or return a result with a flipped sign.

**Lesson objectives:** understand the contract of the `Number` class, distinguish abstract methods from implemented methods, use polymorphism, recognize conversions that can lose information, and decide when to use each type's own *exact* conversion mechanism.

## 1. Position of `Number` in the Java Type System

Basic JDK declaration:

```java
public abstract class Number implements java.io.Serializable {
    // Methods for converting the value to primitive types.
}
```

`Number` belongs to `java.lang`, so it does not require an `import`. It is a **class**, not an interface; you cannot instantiate it with `new Number()` because the class is `abstract`.

```java
// Number n = new Number(); // Compile-time error: Number is abstract.

Number n1 = Integer.valueOf(10);
Number n2 = Double.valueOf(2.5);
Number n3 = new java.math.BigInteger("12345678901234567890");
```

Conceptual diagram:

```text
Object
  └── Number (abstract, Serializable)
       ├── Byte / Short / Integer / Long
       ├── Float / Double
       ├── BigInteger / BigDecimal
       ├── AtomicInteger / AtomicLong
       └── Other Number subclasses
```

Some of the classes above are **primitive wrappers**, while others are not wrappers:

| Category | Examples | Characteristics |
| --- | --- | --- |
| Integer wrappers | `Byte`, `Short`, `Integer`, `Long` | Immutable objects holding the corresponding primitive value |
| Floating-point wrappers | `Float`, `Double` | Immutable objects holding a binary32/binary64 value |
| Arbitrary-precision integer | `BigInteger` | Immutable, not bounded by fixed 32/64 bits (within memory/implementation limits) |
| Decimal number | `BigDecimal` | Immutable, value consists of an unscaled integer and `scale`; suitable for exact decimals |
| Numbers in concurrent contexts | `AtomicInteger`, `AtomicLong` | Value can be mutated via atomic operations; not immutable wrappers |

**Do not interpret `Number` as guaranteeing that every subclass is immutable or thread-safe.** Wrapper objects such as `Integer` are immutable; `AtomicInteger`, on the other hand, can be updated. Even though `Number` implements `Serializable`, decisions about persistent representation, interchange formats, comparison rules, and data safety remain the responsibility of the specific API/type.

## 2. The Six-Method Conversion Contract

According to the Java SE 17 API, `Number` declares six primary methods:

| Method | Return type | In `Number` | Guarantee |
| --- | --- | --- | --- |
| `intValue()` | `int` | **Abstract** | Returns the value after conversion to `int` according to the implementing class |
| `longValue()` | `long` | **Abstract** | Returns the value after conversion to `long` |
| `floatValue()` | `float` | **Abstract** | Returns the value after conversion to `float` |
| `doubleValue()` | `double` | **Abstract** | Returns the value after conversion to `double` |
| `byteValue()` | `byte` | **Has default implementation** | By default returns `(byte) intValue()` |
| `shortValue()` | `short` | **Has default implementation** | By default returns `(short) intValue()` |

The four abstract methods require **concrete subclasses to provide the corresponding value-returning behavior**, unless inherited from an intermediate superclass. The two methods `byteValue` and `shortValue` are **not abstract** in `Number`, and subclasses may override them if needed.

### Why are there no `charValue()` or `booleanValue()`?

Both `char` and `boolean` are Java primitives, but they are not among the six primitives for which `Number` provides conversions. `char` represents a UTF-16 code unit rather than a signed numeric type under the same contract; `boolean` is not a numeric type. Therefore, **there is no `Number.charValue()`, `Number.booleanValue()`, or `Number.stringValue()`**.

If you want a string, you can call `toString()` on the **concrete object**, though `Number` does not promise that all subclasses use the same display format or radix. To parse a string into a number, use dedicated parsers such as `Integer.parseInt`, `Double.parseDouble`, `new BigInteger(String)`, `new BigDecimal(String)`; **`Number` has no general static `parse` method**.

### Simplified code to understand the contract

```java
public abstract class Number implements java.io.Serializable {
    public abstract int intValue();
    public abstract long longValue();
    public abstract float floatValue();
    public abstract double doubleValue();

    public byte byteValue() {
        return (byte) intValue();
    }

    public short shortValue() {
        return (short) intValue();
    }
}
```

This is an **API illustration**, not code to rewrite to replace `java.lang.Number` built into the JDK. Annotations, source attributions, and actual implementation details may differ; what matters is having four abstract methods and two methods with default implementations.

## 3. Polymorphism: Declared Type is `Number`, Runtime Type Decides Behavior

`Number` lets an API accept multiple numeric types under a single reference type:

```java
static void showAsDouble(Number number) {
    System.out.println(number.doubleValue());
}
```

If you pass an `Integer`, a `Long`, or a `BigDecimal`, Java calls the `doubleValue()` method **implemented by the actual object** (dynamic dispatch). That is polymorphism; not all numbers are "automatically turned" into `double` the moment they are assigned to a `Number` variable.

```java
Number n = Long.valueOf(9_007_199_254_740_993L);
System.out.println(n.longValue());   // 9007199254740993
System.out.println(n.doubleValue()); // 9.007199254740992E15 (loses 1 unit).
```

`n` still references the `Long` object holding the exact integer value. **Only the return value of `doubleValue()`** can lose precision. Assigning a `Long` to a `Number` variable does not by itself narrow the value.

### `Number` has no general arithmetic operators

```java
Number x = Integer.valueOf(3);
Number y = Double.valueOf(2.5);

// Number sum = x + y; // Does not compile: + is not defined for Number.
double approximate = x.doubleValue() + y.doubleValue(); // 5.5.
```

In Java, the `+` operator applies to primitive numbers or string concatenation; it **is not overloaded by the `Number` class**. Two objects both being `Number` does not tell Java whether to use big integers, decimals, or binary floating-point for addition.

If you **deliberately** convert both to `double`, binary64 addition may be reasonable for approximate measurements. But that is an **algorithmic decision**, not an abstract addition that preserves exactness across all `Number` subclasses.

## 4. The Contract Is "Convert Value," Not "Preserve All Information"

The Java API states clearly: the detailed semantics of `intValue`, `longValue`, `floatValue`, `doubleValue`, etc. are decided by the **concrete implementation**. Conversions generally mirror widening/narrowing primitive conversions, so they may:

1. **Lose the fractional part:** `3.75` converted to `int` becomes `3`.
2. **Lose magnitude:** a `long` outside the `int` range converted to `int` keeps the low-order bit pattern per integer narrowing rules.
3. **Change sign:** a large positive integer can become a negative `int`.
4. **Lose precision:** a `long` beyond the contiguous integer precision of `double` gets rounded.
5. **Lose finiteness:** a very large `BigDecimal` converted to `double` can become `Infinity`.
6. **Depend on state if the subclass is mutable:** `AtomicInteger.intValue()` reads a value at the time of the call.

`Number` **does not promise** to throw an exception if a value cannot be represented exactly in the target type. If business logic requires "no information loss," use the **exact** methods of the appropriate numeric type or perform explicit range/rounding checks.

### Example: `long` narrowing to `int`

```java
Number n = Long.valueOf(4_294_967_297L);
System.out.println(n.longValue()); // 4294967297
System.out.println(n.intValue());  // 1
```

The original value equals `2^32 + 1`. When converted to a 32-bit `int`, the high bits are discarded and the low 32 bits represent 1. **There is no `ArithmeticException`** on this `intValue()` call.

Similarly:

```java
Number n = new java.math.BigInteger("2147483648");
System.out.println(n.intValue()); // -2147483648
```

The value `2^31` is outside the signed `int` range; the low 32 bits have the sign bit set to 1, so the result becomes `Integer.MIN_VALUE`. The data no longer has the original sign and magnitude.

### Example: `double` to `int`

```java
System.out.println(Double.valueOf(3.75).intValue()); // 3
System.out.println(Double.valueOf(-3.75).intValue()); // -3
System.out.println(Double.valueOf(Double.NaN).intValue()); // 0
System.out.println(Double.valueOf(Double.POSITIVE_INFINITY).intValue()); // 2147483647
```

Java's floating-point-to-integer primitive conversion rules include truncating the fractional part toward 0, converting NaN to 0, and clamping to the maximum/minimum value of the integer type in out-of-range cases. **Do not** interpret a 0 returned from NaN as an actual measurement of 0. If external data can contain NaN/Infinity, validate with `Double.isFinite` before converting.

## 5. Why `byteValue()` and `shortValue()` Easily Cause Surprises

By default, `Number.byteValue()` is equivalent to calling `intValue()` and then casting to `byte`; `shortValue()` is analogous:

```java
byte small = (byte) 258; // 2.
short shortResult = (short) 65537; // 1.
```

A subclass only needs to implement the four abstract methods, and can inherit these two behaviors. Therefore, even if a subclass stores data in a `long`, calling `byteValue()` by default goes through `intValue()`. Subclasses may override them if their contract requires different behavior.

**Conclusion:** the name `byteValue()` does not mean "check that the value fits in the byte range"; it only asks for a `byte` result. If you want to detect data loss, look at `byteValueExact()` on `BigInteger` or `BigDecimal`, rather than trusting `Number.byteValue()` by default.

## 6. Implementing Your Own `Number` Subclass

When you have a custom numeric type that needs to participate in APIs accepting `Number`, you can create a subclass and implement the four abstract methods:

```java
static final class CounterNumber extends Number {
    private final long value;

    CounterNumber(long value) {
        this.value = value;
    }

    @Override
    public int intValue() {
        return (int) value;
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
}
```

This is a **nested class inside another class**, illustrating data stored in `long`. The complete program is in section 11.

- `longValue()` preserves the stored value.
- `intValue()` can overflow according to `long -> int` cast rules.
- `floatValue()` and `doubleValue()` can round large integers.
- `byteValue()` and `shortValue()` are inherited from `Number`, going through `intValue()`.

```java
System.out.println(new CounterNumber(258L).byteValue()); // 2
```

**Design note:** extending `Number` does not automatically create parsing, formatting, addition, comparison, or meaningful equality contracts. If a class represents money, fractions, units of measurement, or custom immutable numbers, you must design those operations independently, and consider whether extending `Number` is genuinely needed. That is an architectural choice, not a mandatory requirement for every class that "has a numeric value."

## 7. `Exact` Methods Belong to Subclasses, Not `Number`

`Number` has no shared `intValueExact()` or `longValueExact()`. However, the big-number classes provide APIs that check for information loss.

| Type | Method | Guarantee / reaction |
| --- | --- | --- |
| `BigInteger` | `intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()` | Throws `ArithmeticException` if the integer value exceeds the target type's range |
| `BigDecimal` | `intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()` | Throws `ArithmeticException` if there is a non-zero fractional part **or** it does not fit in the target range |
| `BigDecimal` | `toBigIntegerExact()` | Throws `ArithmeticException` if there is a non-zero fractional part |
| `long` to `int` | `Math.toIntExact(long)` | Throws `ArithmeticException` if `long` does not fit in `int` |

### `BigDecimal`: `intValue` and `intValueExact` are two policies

```java
java.math.BigDecimal value =
        new java.math.BigDecimal("12.75");

System.out.println(value.intValue()); // 12
// value.intValueExact(); // ArithmeticException: discards non-zero fractional part.
```

`intValue()` on `BigDecimal` discards the fractional part and, when the integer part exceeds the `int` range, may retain only the low 32 bits. `intValueExact()` requires the value to **be an integer** and **fit in `int`**. For example, `new BigDecimal("12.00").intValueExact()` returns 12, because its mathematical fractional part is 0.

### `BigInteger`: only needs bounds checking

```java
java.math.BigInteger tooLarge =
        new java.math.BigInteger("2147483648");

System.out.println(tooLarge.intValue()); // -2147483648
// tooLarge.intValueExact(); // ArithmeticException: exceeds Integer.MAX_VALUE.
```

`BigInteger` always represents an integer, so there is no fractional part to discard; the exact APIs primarily check the **target type's range**.

### `long` to `int` when working with primitives

```java
long count = 4_294_967_297L;
// int unsafe = (int) count;       // 1, loses high bits.
// int safe = Math.toIntExact(count); // ArithmeticException.
```

These exact APIs **are not methods on `Number`**. When a variable only has declared type `Number`, the compiler does not know whether `intValueExact` exists on every subtype. You must design the input contract, check the concrete type, or choose an API with more specific types.

## 8. Handling a `Number` of Unknown Class Without Silent Data Loss

A way you *should not* use when you want to preserve exact decimals:

```java
static java.math.BigDecimal badConversion(Number n) {
    return new java.math.BigDecimal(n.doubleValue());
}
```

This function converts every numeric type to `double` first: a large `BigInteger` can lose digits and an exact `BigDecimal` can be rounded; `new BigDecimal(double)` will describe the **exact binary approximation** passed in, rather than recovering the original data. In addition, `Double.NaN` and infinities cannot construct a `BigDecimal` this way.

An example with a **clear contract** accepting only appropriate decimal and integer types:

```java
static java.math.BigDecimal toExactDecimal(Number n) {
    if (n == null) {
        throw new IllegalArgumentException("number is required");
    }
    if (n instanceof java.math.BigDecimal bd) {
        return bd;
    }
    if (n instanceof java.math.BigInteger bi) {
        return new java.math.BigDecimal(bi);
    }
    if (n instanceof Byte || n instanceof Short
            || n instanceof Integer || n instanceof Long) {
        return java.math.BigDecimal.valueOf(n.longValue());
    }
    throw new IllegalArgumentException(
            "Unsupported numeric source: " + n.getClass().getName());
}
```

This is a Java 17+ illustrative method (using `instanceof` pattern matching). It **deliberately rejects** `Float`, `Double`, `AtomicInteger`, and any unfamiliar subtype to avoid the false inference that `Number.doubleValue()` guarantees exact decimals.

If an application wants to accept finite `double` values, it can define an explicit rule such as `BigDecimal.valueOf(d)`, while understanding that **the `double` value was already rounded beforehand** and distinguishing it from `new BigDecimal(d)`. For approximate measurement data, a policy permitting rounding may be reasonable; for exact decimal protocols, accepting only explicit types as above is safer.

**Design takeaway:** do not expect a `Number` method to automatically choose the right precision for every system. The more exactness must be preserved, the more **specific** parameter and return types should be.

## 9. `Number` Differs from Autoboxing, Unboxing, and Generic Arithmetic

### Boxing does not turn `Number` into a primitive

```java
Number a = 42;      // int -> Integer (boxing) -> Number (upcast).
Number b = 1.25;    // double -> Double (boxing) -> Number.
int x = a.intValue();

// int y = a; // Does not compile: cannot directly unbox an arbitrary Number.
```

Java supports **unboxing** from language-specified wrappers such as `Integer`, `Double`, and `Long`, not an unboxing rule from **any `Number` subtype**. Calling `intValue()` is a method call, not an automatic conversion of all `Number` instances to primitives under the same operation.

When a variable has type `Integer`, an expression like `Integer boxed = 3; int v = boxed;` can use implicit unboxing. If `boxed` is `null`, unboxing throws `NullPointerException`. Likewise, `Number n = null; n.intValue()` causes an NPE because a method is invoked on a null reference.

### Generic `T extends Number` does not provide the `+` operator

```java
static double sumAsDouble(
        java.util.List<? extends Number> numbers) {
    double result = 0.0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
```

This method can work with `List<Integer>`, `List<Long>`, `List<BigDecimal>`, etc., but the result **is a binary64 approximate sum**, guaranteeing neither exact decimals nor freedom from overflow. `List<? extends Number>` only expresses a type constraint; it does not make Java allow `n1 + n2` on `Number` objects.

For libraries handling money, large-integer totals, or rational fractions, it is usually better to accept `List<BigDecimal>`, `List<BigInteger>`, or a dedicated value type with a clear contract. Do not use generic `Number` and coerce everything to `double` if requirements forbid data loss.

## 10. Equality, Ordering, and Mutability Are Not Standardized by `Number`

Two objects with the same mathematical value do not necessarily compare equal when calling `equals`:

```java
System.out.println(
        Integer.valueOf(1).equals(Long.valueOf(1L))); // false.

System.out.println(
        new java.math.BigDecimal("1.0")
            .equals(new java.math.BigDecimal("1.00"))); // false.
```

`Integer.equals` requires an object of the same type `Integer` with the same value; `Long.equals` has the corresponding type rule. For `BigDecimal`, `equals` also considers **scale**, so 1.0 differs from 1.00; whereas `compareTo` shows their mathematical values are equal:

```java
java.math.BigDecimal x = new java.math.BigDecimal("1.0");
java.math.BigDecimal y = new java.math.BigDecimal("1.00");
System.out.println(x.compareTo(y) == 0); // true.
```

`Number` **does not establish a universal `equals`/`hashCode`/`compareTo` rule across all subtypes**. You should not create `new HashSet<Number>()` expecting it to merge `Integer(1)`, `Long(1L)`, and `BigDecimal("1.0")` into a single element.

Some `Number` types are also **mutable**:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger(3);
Number snapshotSource = counter;
counter.incrementAndGet();
System.out.println(snapshotSource.intValue()); // 4.
```

`snapshotSource` references **the same `AtomicInteger` object** whose value changed, not a snapshot of `3`. If you need an immutable snapshot value, read a primitive at an intentional point in time (`int snapshot = counter.intValue()`) and store it separately. `AtomicInteger.intValue` returns the value observed at the time of the call; if multiple threads update it, consecutive calls need not return the same number.

## 11. Standalone Java 17+ Program

Create the file `NumberContractDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class NumberContractDemo {
    static class CounterNumber extends Number {
        private final long value;

        CounterNumber(long value) {
            this.value = value;
        }

        @Override public int intValue() {
            return (int) value;
        }
        @Override public long longValue() {
            return value;
        }
        @Override public float floatValue() {
            return value;
        }
        @Override public double doubleValue() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<Number> list = List.of(
                Integer.valueOf(42),
                Long.valueOf(4_294_967_297L),
                Double.valueOf(3.75),
                new BigDecimal("42.50"),
                new BigInteger("4294967296"),
                new AtomicInteger(7));

        for (Number n : list) {
            System.out.println(n.getClass().getSimpleName()
                    + ": int=" + n.intValue()
                    + ", long=" + n.longValue());
        }

        System.out.println("Default byteValue: "
                + new CounterNumber(258L).byteValue());

        System.out.println("Decimal intValue: "
                + new BigDecimal("12.75").intValue());
        try {
            new BigDecimal("12.75").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("Decimal intValueExact: rejected");
        }

        System.out.println("BigInteger intValue: "
                + new BigInteger("2147483648").intValue());
        try {
            new BigInteger("2147483648").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger intValueExact: rejected");
        }

        System.out.println("NaN intValue: "
                + Double.valueOf(Double.NaN).intValue());
        System.out.println("Infinity intValue: "
                + Double.valueOf(Double.POSITIVE_INFINITY).intValue());

        System.out.println("Cross-wrapper equals: "
                + Integer.valueOf(1).equals(Long.valueOf(1L)));
        System.out.println("Decimal equals by scale: "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("Decimal compareTo numerically: "
                + (new BigDecimal("1.0")
                    .compareTo(new BigDecimal("1.00")) == 0));
    }
}
```

Compile and run:

```bash
javac --release 17 NumberContractDemo.java
java NumberContractDemo
```

Stdout output:

```text
Integer: int=42, long=42
Long: int=1, long=4294967297
Double: int=3, long=3
BigDecimal: int=42, long=42
BigInteger: int=0, long=4294967296
AtomicInteger: int=7, long=7
Default byteValue: 2
Decimal intValue: 12
Decimal intValueExact: rejected
BigInteger intValue: -2147483648
BigInteger intValueExact: rejected
NaN intValue: 0
Infinity intValue: 2147483647
Cross-wrapper equals: false
Decimal equals by scale: false
Decimal compareTo numerically: true
```

The program verifies four main points: the same `Number` reference type can hold many numeric types; converting to `int`/`long` can lose values; `byteValue/shortValue` have defaults; *exact* conversions and `equals` equality are **contracts of the specific type**, not of every `Number`.

## 12. How to Choose Types and Design APIs

| Need | Usually suitable choice | Reason |
| --- | --- | --- |
| Display approximate statistics from multiple numeric classes, error tolerated | `Number` then **deliberate** `doubleValue()` | Easy polymorphic API; must check finiteness/precision |
| API requiring an integer within `int` range | `int`/`Integer` with input validation, or `intValueExact` on supporting types | Do not trust `Number.intValue` to detect overflow |
| Integers not bounded by 64 bits | `BigInteger` | Avoids bit loss from `longValue/intValue` |
| Finance or exact decimal arithmetic | `BigDecimal` | Preserves decimal representation and controls rounding |
| Storing only 32/64-bit primitives with clear performance/memory needs | `int`/`long`/`double` | Avoids unnecessary boxing in hot loops |
| Numeric value mutable across threads | `AtomicInteger`/`AtomicLong` if concurrency fits | Provides atomic API; reading `Number` only takes a single value |
| Heterogeneous list for presentation/logging | `List<Number>` | Shared reference type; do not infer arithmetic/equality |
| Addition/subtraction across types that **must** stay exact | Design a custom numeric type or choose an appropriate canonical type | `Number` does not describe algebraic operations or rounding rules |

### What should an API contract specify?

If you define a method taking `Number`, answer:

1. Are **all** `Number` subtypes allowed, or only `Integer`/`Long`/`BigDecimal`?
2. Are NaN, infinity, negative numbers, or fractional parts accepted?
3. Can precision loss, truncation, sign change, or overflow occur?
4. Can the value change between two reads from a mutable `Number`?
5. What type does the return value have; how are input errors and overflow reported?
6. If converting to `double`, what error tolerance and magnitude range are acceptable?
7. Is a cross-type `equals`/`compareTo` rule needed, or is each subtype handled separately?

In public APIs, **accepting `Number` for flexibility** must be paired with **documentation on precision and conversion**. If business rules allow only one valid numeric type, accepting that exact type is usually simpler and safer.

## 13. Common Mistakes

| Misconception | What happens | How to handle |
| --- | --- | --- |
| Thinking `Number` is an interface | It is an **abstract class** with implemented methods | Use `extends Number` when creating a subtype |
| Trying to instantiate `new Number()` | Compile-time error | Instantiate a concrete subclass |
| Thinking implementing `intValue()` is enough | `longValue`, `floatValue`, `doubleValue` remain abstract | Implement all four unless inherited from a superclass |
| Trusting `n.intValue()` to always check range | `Long(4294967297)` returns 1 | Use checked/exact conversion when required |
| Trusting `n.doubleValue()` to preserve every integer | `2^53+1` is not preserved exactly in binary64 | Keep `long`/`BigInteger` if needed |
| Trusting `n.byteValue()` to automatically throw above 127 | Default casts from `intValue` | Use an appropriate exact API |
| Thinking `Number` supports `x + y` | The `+` operator is not defined for two `Number`s | Choose explicit numeric types/math strategy |
| Using `new BigDecimal(n.doubleValue())` to "preserve" data | Data is already lost before constructing `BigDecimal` | Accept types supporting exactness and convert directly |
| Treating every `Number` as an immutable wrapper | `AtomicInteger` is mutable | Pay attention to mutability and snapshots |
| Thinking `Number` standardizes `equals` and `compareTo` | Each subtype has its own contract | Avoid undesigned cross-type equality/hashing |
| Thinking `Number n = 2` turns the integer into `double` | The value is boxed to `Integer` | Distinguish boxing, upcasting, and conversion |
| Calling `n.intValue()` on `null` | `NullPointerException` | Check for null at the boundary |
| Using `Number` for exact money but summing via `doubleValue` | Decimal precision can be lost | Use `BigDecimal` and a rounding policy |
| Passing `Number` through serialization without a defined schema | Concrete type/precision can become ambiguous across systems | Specify numeric type, format, scale, and conversion policy in the protocol |

## 14. Self-Check

1. Is `Number` a class, an interface, or an abstract class? Why can you not use `new Number()`?
2. What are the four abstract methods of `Number`? Which two methods have default implementations, and how do those defaults work?
3. Why does `Number n = Long.valueOf(4_294_967_297L); n.intValue()` return 1 instead of throwing an exception?
4. What does `intValue()` return on `BigDecimal("12.75")`? How does `intValueExact()` behave?
5. Why can `BigInteger("2147483648").intValue()` be **negative** even though the original number is positive?
6. Given `Number n = Integer.valueOf(3)`, can you write `int x = n;`? Why is `int x = n.intValue();` valid?
7. Why does `List<? extends Number>` not make `+` between two elements valid?
8. Why does converting a large `BigInteger` via `doubleValue()` and then creating a `BigDecimal` not preserve all digits?
9. When can an `AtomicInteger` typed as `Number` return two different results from consecutive `intValue()` calls?
10. Why is `Integer.valueOf(1).equals(Long.valueOf(1L))` false? Are `BigDecimal("1.0")` and `BigDecimal("1.00")` equal under `equals` and `compareTo`?
11. If an API only accepts integers that fit in `int`, what contract should replace unchecked `Number.intValue()`?
12. For a new unit-of-measurement type, does `extends Number` automatically provide arithmetic operators or comparators?

## 15. Official Documentation

- [`java.lang.Number` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): describes the abstract class, four abstract methods, two defaulted methods, and warnings about information loss during conversion.
- [`java.math.BigDecimal` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): type-conversion contract and `intValueExact`, `longValueExact`, `toBigIntegerExact`.
- [`java.math.BigInteger` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): large integers, `intValueExact`/`longValueExact`, and low-bit truncation conversions.
- [Java Language Specification `5.1.2 and `5.1.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): widening/narrowing primitive conversions.
- [`java.util.concurrent.atomic.AtomicInteger` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomically updated integer class that extends `Number`.

**Conclusion:** `Number` is an **abstract superclass for numeric objects capable of converting to six primitives**. It provides conversion polymorphism, and **does not guarantee** general arithmetic, precision, cross-type equality, or immutability. `intValue`/`longValue`/`floatValue`/`doubleValue` can lose information; `byteValue`/`shortValue` default to going through `intValue`. When numeric range, fractional parts, or precision must be guaranteed, choose **specific types and checked/exact conversions** instead of treating every `Number` as a completely interchangeable numeric value.