# BigInteger, BigDecimal, and Other Number Classes in the JDK

Java has the primitive types `byte`, `short`, `int`, `long`, `float`, and `double` for storing numbers within finite ranges and precision. When those types do not meet requirements, the JDK provides **object classes representing numbers**: wrappers such as `Integer`/`Double`, arbitrary-magnitude integers `BigInteger`, arbitrary-precision decimals `BigDecimal`, along with counters for concurrent programming such as `AtomicInteger`, `AtomicLong`, and `LongAdder`.

Many of those classes extend the abstract class `java.lang.Number`, yet **being a `Number` does not mean they share the same value range, precision, immutability, equality rules, or way of performing operations**. You must choose a type based on data semantics and understand the limits of each API.

## 1. The Big Picture

| Group | Representative classes | Primary purpose | Things to watch out for |
| --- | --- | --- | --- |
| Primitives | `byte`, `short`, `int`, `long`, `float`, `double` | Direct arithmetic with operators | Fixed ranges; `float`/`double` have representation error |
| Numeric primitive wrappers | `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` | Representing numbers as objects, generics, collections, boxing | Immutable; conversions and comparisons require type awareness |
| Big integer | `java.math.BigInteger` | Exact integers beyond `long` | Immutable; practical limit is memory/CPU resources |
| Big decimal | `java.math.BigDecimal` | Exact decimals via decimal representation and rounding rules | Immutable; distinguish `scale`, `precision`, `equals`, and `compareTo` |
| Concurrent counters | `AtomicInteger`, `AtomicLong` | Updating integer values with atomic operations | Mutable state; not arbitrary-size integers |
| Concurrent accumulators | `LongAdder`, `DoubleAdder`, `LongAccumulator`, `DoubleAccumulator` | Sums/accumulators under high thread contention | Stateful; read values may not be an atomic snapshot |

These classes live in different packages: wrappers and `Number` are in `java.lang`, the two big-number classes are in `java.math`, and the atomic/adder/accumulator group is in `java.util.concurrent.atomic`.

## 2. What Is java.lang.Number?

`Number` is an **abstract class** representing objects capable of supplying their value as primitive numeric types. Its four key abstract methods are:

~~~java
public abstract int intValue();
public abstract long longValue();
public abstract float floatValue();
public abstract double doubleValue();
~~~

In addition, `Number` has `byteValue()` and `shortValue()` as concrete methods, essentially based on a narrowing conversion from `intValue()` unless a subclass provides its own implementation.

You can use a `Number` reference for many object types:

~~~java
Number count = Integer.valueOf(42);
Number pi = Double.valueOf(3.14);
Number huge = new java.math.BigInteger("12345678901234567890");
Number amount = new java.math.BigDecimal("19.95");
~~~

The `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()` methods support **value** conversion, but do not automatically guarantee exact conversion or preservation of the entire numeric range. For example, `new BigDecimal("1.99").intValue()` returns 1: the fractional part is discarded.

**Number does not provide general polymorphic arithmetic**. A `Number` variable has no `add(Number)` method on the base class, and Java does not allow applying the `+` operator directly between two `Number` references in a general arithmetic sense.

~~~java
Number a = Integer.valueOf(2);
Number b = Long.valueOf(3);
// Number result = a + b; // Error: no general addition operator for Number
~~~

You must decide on the concrete arithmetic (exact integer, floating-point, decimal, etc.) before computing. Do not automatically convert every `Number` to `double` for computation if the program must preserve digits.

### 2.1. Number is a reference type, not a primitive numeric type

You cannot write `Number x = 42.5 + 1.0` and expect `Number` to choose a polymorphic arithmetic system. The primitive expression is evaluated first using `double` and **boxed** into `Double` when assigned to `Number`.

~~~java
Number x = 42;      // int -> Integer (boxing) -> Number
Number y = 3.5;     // double -> Double (boxing) -> Number
System.out.println(x.getClass().getSimpleName()); // Integer
System.out.println(y.getClass().getSimpleName()); // Double
~~~

Java supports automatic boxing between primitives and their matching wrappers, yet **does not auto-box `int` into `BigInteger`** or `double` into `BigDecimal`. Those two classes require explicit factories/constructors.

### 2.2. Number does not imply immutability

`Integer`, `Long`, `BigInteger`, and `BigDecimal` are immutable: operations produce new result objects. However, `AtomicInteger`/`LongAdder` are also `Number`s and have mutable state.

Therefore, if an API accepts `Number`, do not assume the object's value stays unchanged between two `doubleValue()` calls. Concurrency and consistency guarantees must follow the contract of the concrete class.

## 3. BigInteger: Arbitrary-Magnitude Integers

`BigInteger` represents signed integers with arbitrary precision within practical memory/CPU and implementation limits. It fits when `long` (range -2^63 to 2^63-1) is not large enough: combinatorics, cryptography, huge integers, and algorithms requiring exact integer results.

Creating objects:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42L);
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger ten = BigInteger.TEN;
~~~

Use decimal strings to construct numbers beyond the `long` range. `BigInteger.valueOf(long)` is convenient for existing `long` values, though its input is still bounded by `long`. There is no `new BigInteger(long)` constructor.

### 3.1. Operations on BigInteger

Because it is an object, `BigInteger` does not support operators `+`, `-`, `*`, `/` like primitives. Use methods:

| Goal | Method |
| --- | --- |
| Addition, subtraction | `add(...)`, `subtract(...)` |
| Multiplication, integer division | `multiply(...)`, `divide(...)` |
| Remainder | `remainder(...)`; `mod(...)` for positive modulus |
| Exponentiation | `pow(int exponent)` (non-negative integer exponent) |
| GCD | `gcd(...)` |
| Bit shifting | `shiftLeft(n)`, `shiftRight(n)` |
| Modular exponentiation | `modPow(exponent, modulus)` |
| Comparison | `compareTo(...)`, `equals(...)` |

~~~java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = BigInteger.valueOf(3);
BigInteger sum = a.add(b);
BigInteger quotient = a.divide(b);
BigInteger remainder = a.remainder(b);
BigInteger square = b.pow(2);
~~~

This is an illustrative snippet that belongs inside a Java class with `import java.math.BigInteger`. With `divide`, the quotient is an **integer**, and the remainder is separated out. It does not produce fractions or decimals like `BigDecimal`. Dividing by zero throws `ArithmeticException`.

**Distinguish `remainder` and `mod`:** `remainder` takes its sign from integer division; `mod` requires a positive modulus and returns a non-negative result. Do not blindly substitute one for the other in algorithms handling negative numbers.

### 3.2. Immutability and discarded additions

~~~java
BigInteger n = BigInteger.TEN;
n.add(BigInteger.ONE);        // New result is discarded; n is still 10
n = n.add(BigInteger.ONE);    // n now points to an object equal to 11
~~~

The same mistake happens with `BigDecimal`. In the JDK, both are **immutable** objects, so calling `add` by itself does not mutate the existing object.

### 3.3. Converting to primitives can lose data

~~~java
BigInteger huge = BigInteger.ONE.shiftLeft(40); // 2^40
int truncated = huge.intValue();                // 0, only low 32 bits remain
// int exact = huge.intValueExact();            // throws ArithmeticException
~~~

Safer APIs when value preservation is required include `intValueExact()`, `longValueExact()`, `shortValueExact()`, and `byteValueExact()`. They throw `ArithmeticException` if the integer does not fit the target type.

Converting to `float` or `double` can round or turn into infinity for huge numbers. Therefore, if exact integers must be kept, do not store `BigInteger` results in `double` "for convenient further math."

## 4. BigDecimal: Exact Decimals via Unscaled Value and Scale

`BigDecimal` represents a decimal number as an **arbitrary-magnitude signed integer (unscaled value)** combined with a **scale**:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

- `new BigDecimal("12.34")` has `unscaledValue() = 1234` and `scale() = 2`.
- `new BigDecimal("2.00")` has `unscaledValue() = 200` and `scale() = 2`.
- `new BigDecimal("2.0")` has `unscaledValue() = 20` and `scale() = 1`.
- The two values `2.00` and `2.0` are numerically equal, yet have **different scale representations**.

`BigDecimal` lets you represent **the exact entered decimal value** and perform operations with controlled precision/rounding. "Arbitrary precision" does not mean every division yields a finite decimal result, or that every computation has infinite resources and needs no rounding policy.

### 4.1. Creating BigDecimal: prefer decimal strings

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");    // Exact decimal value 0.1
BigDecimal b = new BigDecimal("0.2");    // Exact decimal value 0.2
BigDecimal sum = a.add(b);               // Exact 0.3
BigDecimal c = BigDecimal.valueOf(0.1);  // Created from Double.toString(0.1): "0.1"
~~~

Be especially careful to understand:

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinary = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
~~~

`new BigDecimal(0.1)` receives the **binary double value** of the literal 0.1 directly (which is not exactly equal to decimal 0.1), so it represents that binary value in a very long decimal form. `BigDecimal.valueOf(0.1)` uses the canonical string representation of `double` and converts it to `BigDecimal`, so in the example it yields the intended decimal `0.1`.

This does not mean `BigDecimal.valueOf(double)` recovers all original decimal information already lost when converting to `double`. **When the original input is a decimal number string, parse that string directly into BigDecimal** to avoid losing precision prior to conversion.

For integer data already in `long`, you can use `BigDecimal.valueOf(long)`; for `BigInteger`, use `new BigDecimal(bigInteger)`. There is no automatic conversion from primitives to `BigDecimal`.

### 4.2. Operations and rounding policies

Basic methods:

~~~java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);    // 59.85
BigDecimal discounted = total.subtract(new BigDecimal("1.50")); // 58.35
~~~

`add`, `subtract`, and `multiply` can produce exact decimal results for the represented operands if not further constrained by a `MathContext`. **Division** is trickier: many quotients do not have a finite decimal expansion, famously `1 / 3`.

~~~java
BigDecimal numerator = BigDecimal.ONE;
BigDecimal denominator = new BigDecimal("3");

// numerator.divide(denominator); // ArithmeticException: non-terminating quotient
BigDecimal ratio = numerator.divide(
        denominator, 2, java.math.RoundingMode.HALF_UP); // 0.33
~~~

When you need to specify the number of digits after the decimal point, use `divide(divisor, scale, roundingMode)` or `setScale(scale, roundingMode)`. When you want to limit **significant digits**, use `MathContext`:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(5, RoundingMode.HALF_EVEN);
BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), context);
// Value: 0.33333 (5 significant digits)
~~~

Carefully distinguish:

- **Scale:** number of decimal digits in the representation `unscaled × 10^-scale`; can be negative.
- **Precision:** number of significant decimal digits of the unscaled part (ignoring sign).
- **RoundingMode:** rule for handling discarded digits, e.g., `HALF_UP` or `HALF_EVEN`.
- **MathContext:** precision and rounding mode applied when executing operations taking a context.

For example, `new BigDecimal("123.45").setScale(1, RoundingMode.HALF_UP)` returns `123.5`. In financial applications, an agreed-upon scale of 2 and rounding mode must come from **business rules, currency, contract, or system policy**, rather than always defaulting arbitrarily.

### 4.3. equals differs from compareTo

This is the most important `BigDecimal` trap when placing values in collections:

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
~~~

`equals` requires both **numeric value and scale** to match; `compareTo` compares by **numeric value**, ignoring scale differences. Therefore:

- `HashSet<BigDecimal>` uses `equals`/`hashCode`, so it can contain both `2.0` and `2.00` as two distinct elements.
- `TreeSet<BigDecimal>`, using natural ordering via `compareTo`, treats them as the same key, so it keeps only one element.
- To check whether two `BigDecimal`s are **numerically** equal, use `a.compareTo(b) == 0`. To check identical representation (including scale), use `a.equals(b)`.
- `stripTrailingZeros()` can normalize trailing zeros, but may also produce a negative scale or switch string output to scientific notation, e.g., for integers with many trailing zeros. Do not normalize system-wide automatically if scale carries business meaning.

The differing behavior of the two collections stems from API contracts, not a Java bug.

### 4.4. Converting BigDecimal to integer types

~~~java
BigDecimal amount = new BigDecimal("1.99");
int truncated = amount.intValue();    // 1: discards fractional part
// int exact = amount.intValueExact(); // throws ArithmeticException
~~~

`intValue()` can discard the fractional part and/or lose high bits if the value is out of range. `intValueExact()` requires fitting in the `int` range **and having no non-zero fractional part**. `longValueExact()` and `toBigIntegerExact()` behave analogously when integer preservation is needed.

`toBigInteger()` does not round: it truncates the fractional part toward 0. If you must round and then take an integer, apply `setScale(0, roundingMode)` first and then perform the exact conversion as required.

### 4.5. Displaying BigDecimal

`toString()` may use scientific notation; `toPlainString()` does not use scientific notation; `toEngineeringString()` follows a different rule suited to engineering notation. These methods concern **display strings** and do not mutate the object.

Do not use display formatting or display rounding as proof that internal calculations were exact to that number of digits. When outputting payment data, rules for scale, rounding, and domain-appropriate formatting are also needed.

## 5. Other Number Classes in the JDK

### 5.1. Primitive wrappers: Byte, Short, Integer, Long, Float, Double

All six wrappers extend `Number`; they represent their corresponding primitive values as **immutable objects**. They are essential when using generics/collections or when an API requires reference types:

~~~java
java.util.List<Integer> ids = java.util.List.of(1, 2, 3);
Number first = ids.get(0);
long converted = first.longValue();
~~~

Wrappers provide factories like `Integer.valueOf(...)`, parsers like `Integer.parseInt(...)`, conversion methods, and MIN/MAX constants. They share the same arithmetic limitations as their underlying primitives:

- `Integer`/`Long` cannot replace `BigInteger` if integers exceed their range.
- `Float`/`Double` still have binary error, NaN, and infinity; being wrappers does not make operations exact decimals.
- Wrapper `equals` checks **object type**, e.g., `Integer.valueOf(1).equals(Long.valueOf(1L))` is `false` even though both are numerically 1.
- Boxing and unboxing are not always free, and unboxing a `null` reference causes `NullPointerException`.

For a `List<Number>` containing multiple subtypes, do not assume elements will compare equal via `equals` when they hold equal mathematical values.

### 5.2. AtomicInteger and AtomicLong

`java.util.concurrent.atomic.AtomicInteger` and `AtomicLong` extend `Number`, but have **mutable** state and atomic update methods such as `incrementAndGet()`, `getAndAdd(...)`, and `compareAndSet(...)`.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger requests = new AtomicInteger(7);
int updated = requests.incrementAndGet(); // 8
Number asNumber = requests;
int snapshot = asNumber.intValue();       // 8 at the moment of reading
~~~

They fit counters/state variables requiring concurrent updates within the `int` or `long` range, not "mutable BigIntegers." Incrementing can overflow just like primitive integers; it does not auto-expand into a big number.

### 5.3. LongAdder, DoubleAdder, and Accumulators

The `LongAdder`/`DoubleAdder` family is designed for efficient accumulation under high multi-threaded contention. `LongAccumulator` and `DoubleAccumulator` support accumulation using a specified combining function and identity value.

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder hits = new LongAdder();
hits.add(10);
hits.increment();

Number n = hits;
System.out.println(n.longValue()); // 11 in this single-threaded run
~~~

`LongAdder.sum()` obtains an observed value, yet **is not an atomic snapshot** while other threads are updating. It suits high-throughput statistics/counters and should not be treated as a direct substitute for transactions requiring exact simultaneous check-and-update semantics.

`DoubleAdder` accumulates binary floating-point numbers, so results still suffer rounding error and can depend on update order. It does not replace `BigDecimal` for exact decimal problems.

Both the atomic and adder families demonstrate a core truth: **extending Number does not imply an object is immutable or that reading it always reflects a fixed global state**.

## 6. Standalone Runnable Example in Java 17+

Create the file **NumberFamiliesDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class NumberFamiliesDemo {
    public static void main(String[] args) {
        Number boxed = Integer.valueOf(42);
        System.out.println("Number intValue: " + boxed.intValue());

        BigInteger large = new BigInteger("123456789012345678901234567890");
        System.out.println("BigInteger + 10: " + large.add(BigInteger.TEN));
        System.out.println("2^100 bits: " + BigInteger.ONE.shiftLeft(100).bitLength());
        System.out.println("2^40 intValue: " + BigInteger.ONE.shiftLeft(40).intValue());
        try {
            BigInteger.ONE.shiftLeft(40).intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger exact conversion: overflow");
        }

        BigDecimal decimalSum = new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal 0.1 + 0.2: " + decimalSum.toPlainString());
        System.out.println("from double exact? "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOf double: "
                + BigDecimal.valueOf(0.1).toPlainString());

        BigDecimal one = new BigDecimal("2.0");
        BigDecimal two = new BigDecimal("2.00");
        System.out.println("equals with scale: " + one.equals(two));
        System.out.println("compareTo with scale: " + one.compareTo(two));

        System.out.println("1 / 3 (scale 2): "
                + BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("1 / 3 (precision 5): "
                + BigDecimal.ONE.divide(new BigDecimal("3"),
                        new MathContext(5, RoundingMode.HALF_EVEN)));
        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 without rounding: non-terminating");
        }

        System.out.println("rounded scale: "
                + new BigDecimal("123.45").setScale(1, RoundingMode.HALF_UP));
        System.out.println("intValue truncates: " + new BigDecimal("1.99").intValue());
        try {
            new BigDecimal("1.99").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal exact conversion: fractional");
        }

        Set<BigDecimal> hash = new HashSet<>();
        Set<BigDecimal> sorted = new TreeSet<>();
        hash.add(one);
        hash.add(two);
        sorted.add(one);
        sorted.add(two);
        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + sorted.size());

        AtomicInteger counter = new AtomicInteger(7);
        System.out.println("AtomicInteger increment: " + counter.incrementAndGet());
        LongAdder adder = new LongAdder();
        adder.add(10);
        adder.increment();
        Number accumulator = adder;
        System.out.println("LongAdder as Number: " + accumulator.longValue());
    }
}
~~~

Compile and run:

~~~bash
javac NumberFamiliesDemo.java
java NumberFamiliesDemo
~~~

Exact output:

~~~text
Number intValue: 42
BigInteger + 10: 123456789012345678901234567900
2^100 bits: 101
2^40 intValue: 0
BigInteger exact conversion: overflow
decimal 0.1 + 0.2: 0.3
from double exact? false
valueOf double: 0.1
equals with scale: false
compareTo with scale: 0
1 / 3 (scale 2): 0.33
1 / 3 (precision 5): 0.33333
1 / 3 without rounding: non-terminating
rounded scale: 123.5
intValue truncates: 1
BigDecimal exact conversion: fractional
HashSet size: 2
TreeSet size: 1
AtomicInteger increment: 8
LongAdder as Number: 11
~~~

The program simultaneously demonstrates three key differences to remember: `BigInteger` holds large integers while `intValue()` does not preserve the whole number; `BigDecimal` keeps decimal values and distinguishes scale in `equals`; and `AtomicInteger`/`LongAdder` are **stateful** `Number` classes serving updates/counters rather than arbitrary-precision arithmetic.

## 7. Which Type Should You Choose for the Problem?

| Need | Usually suitable choice | Why |
| --- | --- | --- |
| Counting, indices, integers within a defined range | `int` or `long` | Fast, simple syntax; overflow must be controlled |
| Huge/exact integers | `BigInteger` | Arbitrary-magnitude integers; has exact conversion checks |
| Exact decimal values per input/specification | `BigDecimal` | Has scale and rounding mode model |
| Approximate scientific/engineering computations | `double` (or `float` when required) | Fast and IEEE 754 compliant when error is managed |
| Passing numbers into a generic read-only API | `Number` or targeted generics | Abstraction, though conversions must be specified |
| Counters shared across threads | `AtomicInteger`/`AtomicLong` | Atomic updates |
| High-contention statistical counters | `LongAdder` | Can reduce contention, accepting snapshot semantics |

If a system handles money, `BigDecimal` **does not by itself guarantee correct monetary business logic**: you still need to define units, scale, currency, rounding rules, when rounding occurs, tax/fee rules, and serialization format. In some designs, storing monetary amounts as **integers in the smallest unit** (such as cents) using `long`/`BigInteger` may fit better.

If exact fractional arithmetic such as `1/3` is needed, finite `BigDecimal` cannot store an infinite decimal result exactly in a finite value either. You must choose rounding, or use a **rational fraction** model with `BigInteger` numerator and denominator (custom-built or via an appropriate library), depending on requirements.

## 8. Common Mistakes and How to Avoid Them

**Mistake 1 — Using `new BigDecimal(double)` for decimal currency amounts.**  
A `double` value has already undergone binary conversion and may not represent the original data accurately. When the input is a decimal string, construct directly from the string; when starting from a `double`, understand the limits of `BigDecimal.valueOf(double)`.

**Mistake 2 — Assuming `Number.doubleValue()` always preserves the number.**  
Multi-digit `BigInteger`s can lose precision when converted to `double`; `BigDecimal` converted to `double` can also round or overflow. Do not use `doubleValue()` as a general conversion layer when exact results are needed.

**Mistake 3 — Forgetting that BigInteger/BigDecimal are immutable.**  
`amount.add(extra)` does not change `amount`; you must write `amount = amount.add(extra)` or store the resulting object separately.

**Mistake 4 — Calling `BigDecimal.divide` without a rounding policy for 1/3.**  
Exact division without a terminating decimal expansion throws `ArithmeticException`. Choose scale/precision and rounding per specification.

**Mistake 5 — Using `BigDecimal.equals` to check numerical equality.**  
`new BigDecimal("2.0")` and `new BigDecimal("2.00")` have `equals=false`, even though `compareTo=0`. Choose your desired equality definition before using them as keys.

**Mistake 6 — Mistaking all Numbers for immutable.**  
`AtomicInteger`, `AtomicLong`, and `LongAdder` are mutable objects; `intValue()` or `longValue()` reflects state when read according to each class's contract.

**Mistake 7 — Converting BigInteger/BigDecimal to int using unchecked `intValue()`.**  
This can lose fractional parts or high bits. Use `...Exact()` methods when value preservation is required, handling `ArithmeticException` properly.

**Mistake 8 — Assuming BigDecimal has no limits.**  
`BigDecimal` does not grant infinite resources and can be constrained by scale range and compute resources; infinite decimal divisions require rounding. Choosing it does not replace algorithm design and input validation.

**Mistake 9 — Comparing wrappers with `==` by object identity.**  
When both sides are references, `==` checks **reference identity**, except when unboxing triggers a primitive operator. Use `equals` or appropriate comparison APIs, while remembering `equals` may also not match across different `Number` types.

## 9. Self-Check Exercises

**Question 1.** Is `Number n = new BigInteger("999999999999999999999");` valid, and is `n.intValue()` guaranteed to return the full number?  
**Answer:** Valid because `BigInteger` extends `Number`. `intValue()` does not preserve large numbers; cast back to `BigInteger` safely or keep a specific-typed reference, then use `intValueExact()` if converting to `int`.

**Question 2.** Why does `new BigDecimal("0.1").add(new BigDecimal("0.2"))` give exact 0.3, while `0.1 + 0.2` can differ from 0.3?  
**Answer:** `BigDecimal` created from strings stores exact decimals 0.1 and 0.2; `BigDecimal` addition is exact in this case. `double` stores binary approximations of 0.1 and 0.2, producing `0.30000000000000004`.

**Question 3.** What does `new BigDecimal("1").divide(new BigDecimal("3"))` produce?  
**Answer:** Throws `ArithmeticException` because the quotient 1/3 has no finite decimal representation. Provide `scale`/`RoundingMode` or a `MathContext`.

**Question 4.** Why does `HashSet<BigDecimal>` contain both 2.0 and 2.00, while `TreeSet<BigDecimal>` usually holds only one?  
**Answer:** `HashSet` uses `equals`/`hashCode`, which consider scale; `TreeSet` uses `compareTo` by numeric value, treating these two values as equal when comparing.

**Question 5.** Is `Number` suitable as a common interface for all exact numeric additions?  
**Answer:** No. `Number` only specifies conversions to primitives and does not define `add(Number)` or an arithmetic system. You need specific interfaces/domain types and conversion rules when building an arithmetic library.

**Question 6.** Are `AtomicInteger` and `LongAdder` more efficient multithreaded versions of `BigInteger`?  
**Answer:** No. They serve updates/accumulation on fixed-range values, with stateful behavior and specific concurrency contracts. `BigInteger` is an immutable arbitrary-magnitude integer.

**Question 7.** Should you use `BigDecimal.intValue()` or `intValueExact()` when reading an integer age from a decimal value?  
**Answer:** `intValueExact()` if age must be an integer and within `int` range; this method rejects values with fractional parts or out-of-range values instead of silently losing information.

## 10. Key Takeaways

- `Number` is an **abstract class for converting numeric values** to primitives, not a universal arithmetic operation for all numeric kinds.
- `BigInteger` serves **exact large integers**; operations are methods returning new objects; guard conversions with `...Exact()`.
- `BigDecimal` serves **controlled decimals**; construct from strings when preserving original input, manage `scale`/`precision`/`RoundingMode`, and distinguish `equals` from `compareTo`.
- Primitive wrappers have fixed ranges and are immutable; `AtomicInteger`/`AtomicLong`/`LongAdder` are also `Number`s, yet are stateful and built for concurrency.
- Choose numeric types based on **magnitude, precision, immutability, concurrency needs, rounding rules, and performance**, not merely on whether a class extends `Number`.