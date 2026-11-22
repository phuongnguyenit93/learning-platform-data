# Limitations When Building Your Own `Number` Subclass in Java

## 1. Why Is `extends Number` Not Enough to Have a Complete Numeric Type?

In Java, `java.lang.Number` is an **abstract class** generically representing objects capable of supplying values in several primitive forms. Familiar classes such as `Integer`, `Long`, `Float`, `Double`, `BigInteger`, and `BigDecimal` all belong to the `Number` family.

You can build your own class:

```java
final class CustomNumber extends Number {
    @Override public int intValue() { return 0; }
    @Override public long longValue() { return 0L; }
    @Override public float floatValue() { return 0.0f; }
    @Override public double doubleValue() { return 0.0; }
}
```

This class **compiles**, yet only satisfies the minimal contract: it provides four ways to convert to primitives. It does not yet have addition, multiplication, value comparison rules, range validation, precision, units of measure, or the invariants a real numeric type needs.

Therefore, **extending `Number` does not turn your class into a primitive or a wrapper with full arithmetic syntax**. In Java, there is no operator overloading mechanism for `+`, `-`, `*`, `/` on custom `Number` objects.

This lesson focuses on **limitations and design responsibilities when building a custom `Number` subclass**, how to satisfy the API properly, what data loss can occur, and when to choose a different design.

## 2. The Minimal Contract of `Number`

`Number` is an abstract class implementing `java.io.Serializable`. The four **abstract** methods a concrete subclass must implement are:

| Method | Return type | Responsibility |
|---|---|---|
| `intValue()` | `int` | Represent value as a 32-bit integer |
| `longValue()` | `long` | Represent value as a 64-bit integer |
| `floatValue()` | `float` | Represent value as a 32-bit binary floating-point number |
| `doubleValue()` | `double` | Represent value as a 64-bit binary floating-point number |

Additionally, `Number` already provides two concrete methods:

- `byteValue()`: essentially converts `(byte) intValue()`.
- `shortValue()`: essentially converts `(short) intValue()`.

That means you **are not forced to override** `byteValue()` or `shortValue()` to create a non-abstract subclass. However, their defaults can drop bits per integer narrowing rules. If your data model needs different handling, design an explicit API and test thoroughly.

Example:

```java
Number n = Integer.valueOf(258);
System.out.println(n.intValue());   // 258
System.out.println(n.byteValue());  // 2
```

Converting 258 to `byte` keeps only the low 8 bits, giving 2. **Having a `byteValue()` method does not prove the value fits in the `byte` range.**

### What `Number` does not promise

`Number` provides no shared contract for:

- Value range, precision, or units.
- Integer vs. decimal; finite vs. allowing NaN/Infinity.
- Addition, subtraction, multiplication, or division between two `Number` objects.
- Result type after an operation.
- Natural comparison ordering or value-based equality rules.
- **Exact** conversions to primitives.
- Thread safety or immutability of subclasses.

A subclass can add those capabilities, yet **they are contracts designed by the subclass itself**, not something that appears automatically from extending `Number`.

## 3. Extending `Number` Does Not Create Arithmetic Operators

Consider:

```java
Number a = Integer.valueOf(7);
Number b = Long.valueOf(5);

// Number c = a + b; // COMPILE ERROR
int c = a.intValue() + b.intValue(); // 12, yet can lose data
```

The first line is commented out because `a + b` **is invalid**. The `+` operator on numbers requires operands convertible under the language's arithmetic rules. An object whose static type is `Number` **is not automatically unboxed by Java into an arbitrary primitive numeric type**.

To compute, call appropriate conversion methods or use the API specific to the actual type:

```java
BigDecimal price = new BigDecimal("12.50");
BigDecimal fee = new BigDecimal("2.25");
BigDecimal total = price.add(fee); // 14.75
```

This is an **illustrative snippet**, which must be placed in a scope importing `java.math.BigDecimal`. Methods such as `add`, `subtract`, and `multiply` are **APIs of `BigDecimal`**, not of `Number`.

**Do not write a universal addition function taking two `Number`s and calling `doubleValue()` by default to "solve every numeric type."** That approach can lose precision from `BigInteger`/`BigDecimal` and turn huge values into Infinity.

## 4. Do Not Confuse `Number` with Auto-Unboxed Wrappers

Java supports **unboxing conversions** for primitive wrappers such as `Integer → int` and `Double → double`:

```java
Integer x = 7;
int y = x;        // valid: unboxes Integer -> int
int sum = x + 5;  // valid: unboxes then adds
```

Yet for a variable with **static type `Number`**:

```java
Number x = Integer.valueOf(7);

// int y = x;       // COMPILE ERROR: Number does not auto-unbox to int
// int sum = x + 5; // COMPILE ERROR
int y = x.intValue(); // valid: calls Number API explicitly
```

Even though the runtime object is `Integer`, the compiler checks the variable's static type `Number`. There is no "dynamic unboxing" rule for arbitrary `Number` subclasses.

For a custom subclass such as `FixedCents extends Number`, Java also **does not automatically convert `FixedCents → long`**, even when the class defines `longValue()`. You must call the method explicitly.

This is a fundamental design limit: extending `Number` provides a **class-level value-conversion interface**, without extending Java's syntax or primitive type system.

## 5. Conversion Methods Can Lose Fractions, Overflow, or Lose Precision

`intValue()`, `longValue()`, `floatValue()`, and `doubleValue()` are not guaranteed-succeeding, guaranteed-exact conversions. They may return a rounded, narrowed, or lossy value.

### From decimal to integer

```java
Number amount = new BigDecimal("12.99");

System.out.println(amount.intValue());  // 12
System.out.println(amount.longValue()); // 12
```

The fractional part is discarded when converting to integer. For negative numbers, watch truncation-toward-0 rules in floating-to-integer conversions in many cases; `BigDecimal` specifically enforces conversion rules per its API contract.

### Exceeding the `int` range

```java
BigInteger big = new BigInteger("2147483648");

System.out.println(big.intValue()); // -2147483648
```

The value 2_147_483_648 does not fit in `int`; `BigInteger.intValue()` extracts the low bits, resulting in a different sign from the original number. When **exact** conversion is required, `BigInteger` provides `intValueExact()`: it throws `ArithmeticException` if out of range.

### Precision loss when converting to `double`

Binary64 has about 53 bits of significand precision. Two distinct large integers can convert to **the same `double` value**:

```java
BigInteger a = new BigInteger("9007199254740992");
BigInteger b = new BigInteger("9007199254740993");

System.out.println(a.equals(b)); // false
System.out.println(a.doubleValue() == b.doubleValue()); // true
```

Therefore, **do not use `doubleValue()` as a general value comparison key for all `Number`s**. If your class needs exact inspection, provide dedicated methods such as `toBigDecimal()` or `longValueExact()` when the model permits.

### Conversion policy for your subclass

When writing your own `Number`, decide and document clearly:

- For values with fractional parts, do `intValue()`/`longValue()` truncate, round, or reject?
- When a number exceeds `int` or `long` range, how is it handled?
- How much precision can `floatValue()`/`doubleValue()` lose?
- Are NaN/Infinity supported? For decimal currency, you normally **should not** admit those values into the business domain.
- Are there **exact conversion methods that fail loudly** alongside the `Number` methods?

Do not rely on conversion calls to hide units or cause unintended data loss.

## 6. Program Verifying the Limitations of `Number`

Create the file `NumberLimitsDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberLimitsDemo {
    public static void main(String[] args) {
        Number wrapperAsNumber = Integer.valueOf(7);
        System.out.println("manual extraction: "
                + (wrapperAsNumber.intValue() + 5));

        Number decimalAsNumber = new BigDecimal("12.99");
        System.out.println("decimal to int: "
                + decimalAsNumber.intValue());

        BigInteger tooLarge = new BigInteger("2147483648");
        System.out.println("overflowing intValue: "
                + tooLarge.intValue());

        try {
            System.out.println(tooLarge.intValueExact());
        } catch (ArithmeticException e) {
            System.out.println("intValueExact: out of range");
        }

        BigInteger a = new BigInteger("9007199254740992");
        BigInteger b = new BigInteger("9007199254740993");
        System.out.println("big integers equal: " + a.equals(b));
        System.out.println("converted doubles equal: "
                + (a.doubleValue() == b.doubleValue()));

        Number n = Integer.valueOf(258);
        System.out.println("inherited byte conversion: "
                + n.byteValue());
    }
}
```

Run with Java 17+:

```bash
javac NumberLimitsDemo.java
java NumberLimitsDemo
```

Output:

```text
manual extraction: 12
decimal to int: 12
overflowing intValue: -2147483648
intValueExact: out of range
big integers equal: false
converted doubles equal: true
inherited byte conversion: 2
```

The program demonstrates that `Number` is a **conversion API**, while range limits, precision, and error-reporting policies still depend on **the concrete numeric type**.

## 7. Design Example: Fixed Two-Decimal-Place Money Amount

Suppose a model represents a monetary amount in **integer cents**, and every addition must check for overflow. A custom `FixedCents` class can store a `long cents` field.

This is only a **fixed two-decimal-place learning model**, not sufficient for real-world monetary products. It **stores no currency**, has no currency conversion rules, and does not handle taxes or exchange-rate rounding.

Explicit conventions:

- The underlying `cents` value is **the smallest unit**, e.g., 1234 means 12.34 major currency units.
- `toBigDecimal()` returns the **exact** decimal value in major currency units.
- `intValue()` and `longValue()` return the **whole major units**, truncating the fractional part toward 0.
- `floatValue()` and `doubleValue()` return a **binary floating-point approximation** of the decimal value.
- Addition must call `plus`; you cannot use `+` between two `FixedCents`.
- `Math.addExact` is used to detect cent overflow.
- `equals`/`hashCode`/`compareTo` compare the same unit and `cents` value.

Defining these rules **is not provided by `Number`**. The developer must design and publish them.

## 8. A Compilable, Runnable, and Testable `Number` Subclass

Create the file `CustomNumberDemo.java` containing **two classes**: the `public` runner class and the static nested `FixedCents` class.

```java
import java.math.BigDecimal;

public class CustomNumberDemo {

    static final class FixedCents extends Number
            implements Comparable<FixedCents> {

        private static final long serialVersionUID = 1L;
        private final long cents;

        FixedCents(long cents) {
            this.cents = cents;
        }

        BigDecimal toBigDecimal() {
            return BigDecimal.valueOf(cents, 2);
        }

        FixedCents plus(FixedCents other) {
            return new FixedCents(Math.addExact(cents, other.cents));
        }

        @Override
        public int intValue() {
            return (int) longValue();
        }

        @Override
        public long longValue() {
            return cents / 100L; // truncate fractional part toward 0
        }

        @Override
        public float floatValue() {
            return toBigDecimal().floatValue();
        }

        @Override
        public double doubleValue() {
            return toBigDecimal().doubleValue();
        }

        @Override
        public int compareTo(FixedCents other) {
            return Long.compare(cents, other.cents);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof FixedCents that
                    && cents == that.cents;
        }

        @Override
        public int hashCode() {
            return Long.hashCode(cents);
        }

        @Override
        public String toString() {
            return toBigDecimal().toPlainString();
        }
    }

    public static void main(String[] args) {
        FixedCents price = new FixedCents(1234);
        FixedCents fee = new FixedCents(266);
        FixedCents total = price.plus(fee);

        Number generic = price;

        System.out.println("price: " + price);
        System.out.println("fee: " + fee);
        System.out.println("total: " + total);
        System.out.println("as long: " + generic.longValue());
        System.out.println("as double: " + generic.doubleValue());
        System.out.println("as byte: " + generic.byteValue());
        System.out.println("same cents: "
                + price.equals(new FixedCents(1234)));
        System.out.println("price > fee: "
                + (price.compareTo(fee) > 0));
    }
}
```

Compile and run:

```bash
javac CustomNumberDemo.java
java CustomNumberDemo
```

Output:

```text
price: 12.34
fee: 2.66
total: 15.00
as long: 12
as double: 12.34
as byte: 12
same cents: true
price > fee: true
```

### Why is this implementation only one **policy choice**?

Several decisions are encoded here, rather than being "the single standard meaning" of `Number`:

1. `longValue()` chooses to return **whole major units**, not cents. If another application expects `longValue()` to return 1234, the two systems will misinterpret each other. The API contract must document this clearly.
2. `intValue()` calls `(int) longValue()`. For major-unit counts exceeding `int` range, this cast **can lose bits**. Do not use it to inspect large monetary amounts.
3. `floatValue()` and `doubleValue()` are allowed to return **approximations** — decimal `12.34` need not have an exact binary representation.
4. `plus` uses `Math.addExact` to reject `long` overflow of cents. Yet the class still lacks subtraction, exchange-rate multiplication, currency constraints, or rounding handling.
5. `equals` and `hashCode` both rely on `cents`. This behavior must be **explicitly overridden**: extending `Number` does not automatically provide value equality.

Notably: `Number.byteValue()` on the example class inherits going through `intValue()`, and can then narrow further to `byte`. If `longValue()` returns a large or negative result, `byteValue()` can differ from the desired mathematical value.

## 9. Why Must You Care About `equals`, `hashCode`, and `compareTo`?

`Number` does not guarantee that two distinct objects with "the same value" are equal under `equals`. Without overriding, a subclass inherits `Object`'s reference equality behavior.

Consider two objects:

```java
FixedCents first = new FixedCents(1234);
FixedCents second = new FixedCents(1234);
```

These two lines are an **illustration** inside a scope with access to `FixedCents`. If `FixedCents` does not implement `equals` itself, `first.equals(second)` can be false even though `cents` are equal.

When using structures like `HashSet` or `HashMap`, ensure:

- If `a.equals(b)` is true, then `a.hashCode() == b.hashCode()`.
- Values used in `equals` and `hashCode` must remain stable; **immutability** is a strong choice for value objects.
- `compareTo` (if implemented) should be consistent with the model's ordering semantics and, where possible, with `equals`.
- Do not arbitrarily compare values using `doubleValue()` across `Number`s lacking a shared range/precision.

For example, `new BigDecimal("2.0")` and `new BigDecimal("2.00")` have equal mathematical values per `compareTo`, yet `equals` is false due to different scales. This shows that even **standard-library `Number` subclasses have their own equality policies**.

### Do all numeric types need `Comparable<Number>`?

No. A meaningful comparison requires **the same data domain and same unit**. An object holding meters cannot meaningfully compare to an object holding money merely because both `extends Number`.

In the example, `Comparable<FixedCents>` is deliberate: compare only values of the same model. Do not define a universal ordering across all `Number`s because no unified rule exists for NaN, precision, scale, units, overflow, and custom numeric types.

## 10. Immutability, Serialization, and Thread Safety

`Number` implements `Serializable`, so subclasses tie into Java Serialization. However:

- Subclass fields must still satisfy serialization mechanics if serialization/deserialization is expected to succeed.
- An immutable class may need extra invariant guards during deserialization if its real implementation has complex logic.
- `serialVersionUID` is part of legacy serialization compatibility management; it **does not automatically make data safe or compatible** across all versions.
- If Java native serialization is not needed, do not default to object serialization as an external storage/interchange format merely because of extending `Number`.

The `FixedCents` example uses `private final long cents` and only creates new objects on computation. This **immutable value object** approach avoids mutating a key after inserting it into a hash collection.

However, extending `Number` **does not automatically make every subclass immutable or thread-safe**. For example, stateful numeric types such as `AtomicInteger` also extend `Number`, yet have different goals and update mechanisms.

A mutable subclass must pay special attention to synchronization, state visibility, and `equals`/`hashCode` contracts if shared across threads.

## 11. Limitations of Java's Type System and Syntax

### 11.1. A class can extend only one direct superclass

Java supports **single inheritance** for classes. If you write:

```java
class MyNumber extends Number {
    // ...
}
```

then `MyNumber` cannot simultaneously `extends` another superclass. You can implement multiple interfaces, such as `Comparable<MyNumber>`, yet cannot have two superclasses.

**Records** also cannot `extends Number` because every record directly extends `java.lang.Record`. A record fits better when you want a simple value object without needing a type relationship to `Number`.

If a model needs both another superclass and numeric operations, consider **composition** (holding `BigDecimal` or `BigInteger` as a field) and explicit APIs rather than forcing `extends Number`.

### 11.2. Java does not allow creating "new primitives"

A custom `Number`:

- Has no custom literal like `123usd`.
- Cannot directly use primitive arithmetic operators.
- Is not accepted by overloads requiring `int`/`double` without explicit conversion.
- Does not gain automatic unboxing merely by overriding `intValue()`.
- Cannot alter Java's fixed numeric promotion rules.

These are language limits, not a missing method override.

### 11.3. You cannot rely on `instanceof Number` to assume all numeric types are comparable

`instanceof Number` only checks reference type hierarchy. The object could be `BigDecimal`, `BigInteger`, `Integer`, or any custom numeric type with its own range/unit.

```java
static String describe(Number value) {
    if (value == null) {
        return "missing";
    }
    return value.getClass().getSimpleName()
            + " -> " + value.doubleValue();
}
```

This is an illustrative method that **does not preserve exact numeric values**. It suits intentional approximate logging, not safe financial normalization or large-integer comparison.

## 12. Designing **Exact** Conversions Alongside `Number` Methods

The four abstract methods serve **primitive value access**. If your numeric domain forbids data loss, provide supplementary APIs whose names express the policy:

```java
BigDecimal toBigDecimal()
long centsExact()
int intValueExact()
```

These are **suggested signatures**, not a standalone program. For instance:

- `toBigDecimal()` preserves fractional digits in decimal form when the internal structure permits.
- `centsExact()` returns the raw cents and states the unit right in the method name.
- `intValueExact()` returns `int` only if the mathematical value has no fractional part and fits in `int` range; otherwise it throws a controlled exception.

A simple implementation for `FixedCents` above could use:

```java
int intValueExact() {
    return toBigDecimal().intValueExact();
}
```

This method must live **inside `FixedCents`**. It requires the major-unit amount to be an exact integer: 12.00 is accepted, 12.34 is rejected. If the real need is returning cents as `int`, use a different API like `Math.toIntExact(cents)`, likewise with an explicit unit name.

Similarly, when receiving an arbitrary `Number` from an API, you cannot guarantee recovering original decimal values from `doubleValue()`. If exact decimals are required, require `BigDecimal` input or a dedicated interface supplying decimals at the design boundary.

## 13. When Should You Use Composition Instead of `extends Number`?

A domain value class such as `Money`, `Percentage`, `Temperature`, or `Distance` typically needs:

- Units and constraints attached to the value.
- Meaningful and forbidden operations (e.g., money + money of the same currency, never money + meters).
- Dedicated rounding/validation rules.
- Controlled comparison, conversion, and serialization.

A `Money` object **does not necessarily need to extend `Number`**. Using composition with `BigDecimal` and `Currency` often expresses the model more clearly:

```java
import java.math.BigDecimal;
import java.util.Currency;

record Money(BigDecimal amount, Currency currency) {
    Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException("missing money data");
        }
    }

    Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
```

This is an **illustrative record declaration**, with no `main` method. It demonstrates preserving the model through **units and dedicated APIs**; it does not yet handle scale, currency minor units, rounding, or full financial implementation requirements.

### Why can composition be safer?

If `Money extends Number`, a framework might arbitrarily call `doubleValue()` and accidentally drop precision, currency, or scale. A record/class that does not extend `Number` **forces callers to invoke explicit unit-aware conversions or operations**.

Only `extends Number` when you genuinely must support a polymorphic API accepting `Number` and you **can define consistent, understandable, well-documented conversions to the four primitives**. Without that compatibility requirement, composition usually leaves fewer implicit behaviors.

## 14. Generics, Collections, and Limitations of `Number`

Java generics support:

```java
java.util.List<Number> numbers = java.util.List.of(
        Integer.valueOf(1),
        Long.valueOf(2L),
        new BigDecimal("3.5"));
```

Such a list can hold different numeric classes, yet Java **does not automatically have an exact universal sum** for `List<Number>`. Iterating elements and summing `doubleValue()` chooses a **binary64 approximation** policy.

```java
double sum = 0.0;
for (Number n : numbers) {
    sum += n.doubleValue();
}
```

This is an **illustrative snippet**; it may suit approximate measurement data, yet does not preserve exact decimals for every `Number`.

If an API only accepts small, stable integers, restrict it to a concrete type like `List<Integer>`; if exact decimals are required, use `List<BigDecimal>` or a suitable domain abstraction. **Tighter input typing often improves correctness more than accepting any `Number`.**

### Generic bounds do not create operators

```java
static <T extends Number> double approximate(T value) {
    return value.doubleValue();
}
```

The generic method above is valid, yet you still **cannot write `value + value`** expecting the operator to treat it as a number. A `T extends Number` bound only guarantees access to `Number` APIs; it adds no primitive arithmetic, precision, or cross-`T` operations.

## 15. Common Misconceptions and How to Avoid Them

| Misconception | Reality | How to handle |
|---|---|---|
| `extends Number` lets you write `a + b` | Java does not allow operator overloading for custom numeric classes | Provide `add/plus` or domain APIs |
| You must override all 6 conversion methods | Only 4 are abstract; `byteValue/shortValue` have defaults | Override extra ones when an appropriate contract exists |
| `Number n` auto-unboxes like `Integer` | Static type `Number` has no general primitive unboxing | Call `intValue()`/concrete APIs |
| `intValue()` is always exact | It can lose fractions or bits when out of range | Use `...Exact()` methods where available |
| `doubleValue()` suffices to compare any numbers | Large integers/decimals can lose precision | Compare by original type and data domain |
| Extending `Number` auto-defines value `equals` | No; default behavior comes from `Object` | Design consistent `equals/hashCode` |
| `Number` has a natural ordering | Does not require `Comparable` | Implement `Comparable<T>` when meaningful |
| `Number` guarantees immutability | No | Design `final` classes/fields or manage concurrency |
| `Number` checks overflow automatically | No | Use `Math.*Exact` or validation APIs |
| `Number` preserves units of measure | No shared unit field | Make APIs and types unit-explicit |
| Any `Number` serializes safely over a network | `Serializable` is not equivalent to a safe interchange format | Use defined data formats and schema control |
| A `record` can `extends Number` | Records already extend `Record` | Use composition for value records |
| `List<Number>` has a standard exact `sum` | No single addition/exactness model exists | Choose appropriate algorithms, types, and rules |

## 16. Self-Check Exercises

**Question 1.** To create a concrete class that `extends Number`, which four methods must you override?  
**Answer:** `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`.

**Question 2.** Is it mandatory to override `byteValue()` and `shortValue()`?  
**Answer:** No. `Number` already implements them based on `intValue()`, though conversion can lose information.

**Question 3.** Given `Number n = Integer.valueOf(10);`, can you write `int x = n;`?  
**Answer:** No. The variable has static type `Number`; you need `int x = n.intValue();` or an API typed concretely.

**Question 4.** Can `FixedCents extends Number` use `price + fee` automatically?  
**Answer:** No. You must define and call a method like `price.plus(fee)` or another API.

**Question 5.** What does `new BigInteger("2147483648").intValue()` equal?  
**Answer:** -2_147_483_648 due to dropping high bits under `BigInteger`'s narrowing rules. To reject out-of-range values, use `intValueExact()`.

**Question 6.** Why can two `BigInteger`s differing by 1 appear equal after `doubleValue()`?  
**Answer:** Because binary64 has limited significand precision; large values can round to the same `double`.

**Question 7.** If two `FixedCents` objects share the same `cents`, which methods are needed for `HashSet` to treat them as equal?  
**Answer:** Consistently implemented `equals` and `hashCode`.

**Question 8.** Should `longValue()` on a money type return cents or major units?  
**Answer:** There is no universal answer. Define an explicit policy; ideally provide unit-named APIs like `centsExact()` to avoid ambiguity.

**Question 9.** If a class wants to order numbers of the same type, is `Number` enough?  
**Answer:** No. You can implement `Comparable<MyNumber>` or dedicated comparison methods.

**Question 10.** Why might `Money` be better as a record/class holding `BigDecimal` rather than `extends Number`?  
**Answer:** Because it must protect units, currency conversion rules, and domain arithmetic; extending `Number` can encourage lossy primitive conversions.

**Question 11.** Can `class MyNumber extends Number` also `extends BaseEntity`?  
**Answer:** No, Java supports only single direct class inheritance. You can implement additional interfaces or use composition.

**Question 12.** Does `T extends Number` allow `a + b` with two variables of type `T`?  
**Answer:** No. The generic bound only guarantees `Number`'s methods, not an addition operator.

## 17. Checklist Before Deciding to Build a Custom `Number` Subclass

1. **Reason for inheriting:** does a framework/API genuinely require type `Number`? If not, is composition clearer?
2. **Data model:** integer, decimal, ratio, measurement, or value with units? What is the allowed range?
3. **Four required methods:** what will each method return on fractions, out-of-range values, or precision loss?
4. **Exact APIs:** do you need `toBigDecimal()`, `longValueExact()`, `centsExact()`, or methods that fail rather than dropping bits?
5. **Operations:** how are addition, subtraction, multiplication, division, rounding, division by zero, and overflow handled?
6. **Comparisons:** which fields/units do `equals/hashCode` and `compareTo` inspect? Are they compatible with collections?
7. **Object mutability:** immutable or mutable? If mutable, how are synchronization and hash-key stability guaranteed?
8. **System boundaries:** serialization, database persistence, JSON, logging? Is there an explicit representation beyond primitives?
9. **Testing:** cover negative values, zero, extremes, fractional parts, out-of-range inputs, conversion failures, and invariants.
10. **Contract documentation:** do callers know exactly how to interpret `intValue/longValue/floatValue/doubleValue` results?

**Conclusion:** `Number` is a **foundation class for obtaining primitive representations of a numeric value**, not a complete mathematical interface. To build a safe subclass, you must design the data domain, operations, loss checks, comparisons, and conversion rules yourself. For types with units or critical business precision, **composition and explicit APIs** are usually the easier choice to keep correct.

Official API docs: [Java SE 17 — Number](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html), [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).