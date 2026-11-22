# Looking Up JLS and Javadoc for Numeric APIs in Java: Finding the Right Rule, Version, and Method

## 1. Why Read the Original Specifications?

When encountering a puzzling result such as `Integer.MAX_VALUE + 1` becoming negative, `-7 / 3` producing `-2`, `2.0` differing from `2.00` in `BigDecimal.equals()`, or `Double.MIN_VALUE` being **positive**, the most reliable approach is to trace the **official specification documents** rather than guessing or relying solely on observing one machine.

Java has two essential documentation sources with **distinct purposes**:

1. **JLS – Java Language Specification:** defines the semantics of the **Java language**: primitive types, operators `+`/`-`/`*`/`/`/`%`, promotion, casting, boxing/unboxing, evaluation order, comparisons, literals, and expression runtime rules.
2. **Javadoc – Java SE API documentation:** defines **library classes, constants, constructors, and methods**: `Math.addExact`, `Integer.parseInt`, `Double.isNaN`, `BigDecimal.divide`, `BigInteger.mod`, `RoundingMode.HALF_EVEN`, etc.

A single question often requires both. For instance, to explain why `Integer.MAX_VALUE + 1` does not throw an error automatically, check the **JLS** on integer arithmetic; to learn what exception `Math.addExact` throws instead, check the **Javadoc of `Math`**.

This lesson is a **lookup and cross-referencing guide**, not an exhaustive list of all numeric APIs. After studying it, you can determine "Does this belong to the JLS or Javadoc?", pick the right Java version, locate the exact section/method, read the contract, and build a Java 17+ program to reproduce the result.

## 2. Map of Official Documentation Sources

| Need to Answer | Primary Source | Example Question |
|---|---|---|
| Semantics of `+`, `/`, `%`, `==` operators | JLS, typically Chapter 15 | Why is `-7 % 3` equal to `-1`? |
| Primitive ranges and floating-point rules | JLS Chapter 4 | How many bits does `int` have? Does `double` have signed zero? |
| Type conversions, boxing, unboxing, numeric promotion | JLS Chapter 5 | What type does `int + long` have? When is a null `Integer` unboxed? |
| Types and behavior of `Math.floorDiv`, `addExact` | Javadoc `java.lang.Math` | What does the method return, and what exceptions? |
| `MIN_VALUE`, `MAX_VALUE` constants and parsing | Javadoc `Integer`, `Long`, `Double` | What actually is `Double.MIN_VALUE`? |
| Exact decimals and value comparison | Javadoc `java.math.BigDecimal` | Where does `equals` differ from `compareTo`? |
| Arbitrary-size integers, remainder | Javadoc `java.math.BigInteger` | Does `mod` accept a negative modulus? |
| Rounding and precision | Javadoc `RoundingMode`, `MathContext` | How does `HALF_EVEN` handle exact midpoints? |
| Random numbers for simulation or tokens | Javadoc `Random`, `SecureRandom` | Is the algorithm suitable for security? |
| Bytecode/JVM runtime, VM-level representation | JVM Specification (JVMS), when truly needed | Bytecode instructions, verifier, execution engine |

**The JLS is not Javadoc**, and Javadoc is not the rulebook of a language operator itself. `BigDecimal.add` is a **method call** described in Javadoc; `int + int` is an **expression** governed by the JLS. Do not cite `BigDecimal` to explain default primitive addition, or vice versa.

### Entry Points for Java 17 (Matching Examples in This Lesson)

- [JLS Java SE 17 – Home](https://docs.oracle.com/javase/specs/jls/se17/html/index.html).
- [JLS Chapter 4 – Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).
- [JLS Chapter 5 – Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).
- [JLS Chapter 15 – Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).
- [Java SE 17 API documentation – Module `java.base`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html).
- [Javadoc `java.lang.Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html).
- [Javadoc `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Documentation URLs are **versioned**: `se17` in the JLS and `/javase/17/docs/api/` in Javadoc. When a project runs Java 17, start with Java 17. If the project runs another version, switch to the **JLS/Javadoc of that same version**, because newer APIs might not exist yet or behaviors/contracts may have documented changes.

## 3. Standard Lookup Workflow: From Expression to Citation

A recommended 7-step workflow applicable during code review and debugging:

1. **Rewrite the question concretely.** Example: "In Java 17, given `int a = -7;`, why does `a / 3` return `-2` instead of `-3`?"
2. **Classify the expression.** Language operator or method call? Primitive, wrapper, or `BigDecimal`? Could unboxing/promotion occur?
3. **Lock down the JDK version.** Run `java -version` and `javac -version`; if the build uses `--release 17` or a toolchain config, match that exact level when checking APIs.
4. **Open the exact JLS or Javadoc section.** For the division operator, go to JLS §15.17.2; for `Math.floorDiv`, find the method in `Math` Javadoc.
5. **Read all edge conditions and notes completely.** Pay attention to negative signs, zero, overflow, rounding, parameter types, `null`, exceptions, and provider/implementation limits if any.
6. **Create a minimal reproduction.** A small Java class with fixed inputs printing types/values or catching named exceptions; avoid external dependencies.
7. **Record the conclusion with source and version.** State clearly: "The JLS defines ...; the API method per Javadoc ...; running Java 17 produces ...".

Practical note template:

```text
Question   : Why is -7 / 3 = -2?
Types      : int / int -> int
Source     : JLS SE 17 §15.17.2 (Integer Division Operator /)
Conclusion : Integer division rounds the quotient toward 0
Verify     : javac --release 17, java; printing (-7 / 3) gives -2
Other API  : Math.floorDiv(-7,3) = -3, check Javadoc Math.floorDiv
```

This is a **lookup note template**, not a shell command. The key point is citing the **specific section**, rather than just linking to an overly broad home page.

## 4. Where to Read the JLS for Numbers?

### 4.1. Chapter 4: Primitives and Value Ranges

[JLS §4.2 – Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2) explains primitive types. Useful landmarks:

| JLS 17 Section | What to Look Up |
|---|---|
| [§4.2.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1) | Integral types and ranges of `byte`, `short`, `int`, `long`, `char` |
| [§4.2.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.2) | Integer operations, integer overflow |
| [§4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) | Floating-point types and values `float`, `double` |
| [§4.2.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.4) | Floating-point operations and arithmetic rules |

**Example question:** "Is `Double.MIN_VALUE` the smallest negative number?" First look up `Double.MIN_VALUE` Javadoc to understand the **specific** constant; use JLS §4.2.3–4.2.4 to understand floating-point ranges, subnormals, signed zero, and `Infinity`. Note that `Double.MIN_VALUE` is the **smallest nonzero positive** representable value, not the smallest finite negative number.

### 4.2. Chapter 5: Expression Types and Conversions

[JLS Chapter 5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html) is especially helpful when seeing unexpected results after casting or boxing:

| Section | Typical Question |
|---|---|
| [§5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2) | Is converting `int` to `long` exact? Can `long` to `double` lose digits? |
| [§5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3) | Which part is lost when casting `long` to `int`? |
| [§5.1.7 Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) | When `int` converts to `Integer`, is a new object created? |
| [§5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8) | What will `Integer n = null; n + 1` do? |
| [§5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6) | In `int + double`, how are operands promoted? |

**Subtlety:** converting to a wider type does not necessarily preserve **every bit with full numerical exactness**. `long` → `double` is a *widening primitive conversion*, yet it can lose precision for large integers; if debugging a `long` value near `2^53`, consult JLS §5.1.2 instead of assuming "widening is always lossless."

### 4.3. Chapter 15: Operators and Expression Semantics

Commonly used sections:

- [§15.17 – Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): `*`, `/`, `%`; specifically [§15.17.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2) for division and [§15.17.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3) for remainder.
- [§15.18 – Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): addition/subtraction (and `+` string concatenation); [§15.18.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.2) for numeric addition/subtraction.
- [§15.21 – Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): equality comparison, including numeric equality and reference equality.
- [§15.7 – Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): evaluation order of expression parts.
- [§15.26 – Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): assignment and compound assignment such as `+=`.

Easily confused example: `byte b = 1; b += 1;` is valid, whereas `b = b + 1;` fails to compile without a cast, because numeric promotion and compound assignment rules are not completely identical to simple assignment. Check **JLS §5.6** and **§15.26.2** rather than reading only `Byte`'s Javadoc.

## 5. How to Read Javadoc for Numeric APIs?

A typical Javadoc page contains: **Class/Interface/Enum**, top-level class description, field/constructor/method summaries, and **method detail**. To verify behavior, do not read only the one-line summary; scroll to the exact **overload** and check:

- **Signature:** `static`/instance, parameter types, return type, overloads taking `int`, `long`, `double`, `BigDecimal`, or `MathContext`.
- **Parameters/Returns:** meaning of `bound`, negative values, open/closed bounds, result ordering/scale.
- **Throws:** possible exceptions such as `ArithmeticException`, `NumberFormatException`, `NullPointerException`.
- **Since:** which Java version introduced the API; crucial if code must run on Java 17.
- **API Note / Implementation Requirements / Implementation Note:** read when present, while distinguishing API contracts from implementation details.
- **See Also:** related APIs and alternatives.
- **Class description:** sometimes critical rules (such as `BigDecimal.equals` differing from `compareTo`) are stated at the top of the class rather than repeated on every method.

Do not infer the behavior of all overloads from the method name alone. For instance, `BigDecimal.divide(BigDecimal)`, `divide(BigDecimal, int, RoundingMode)`, and `divide(BigDecimal, MathContext)` have **different precision/rounding contracts**.

### Quick Navigation Table

| Class / Enum | Java 17 Javadoc Link | What to Look Up |
|---|---|---|
| `java.lang.Integer` | [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html) | `MIN_VALUE`, `MAX_VALUE`, `parseInt`, `valueOf`, `compare`, `compareUnsigned` |
| `java.lang.Long` | [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html) | `parseLong`, `valueOf`, `compareUnsigned`, 64-bit bounds |
| `java.lang.Double` | [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) | `MIN_VALUE`, `MIN_NORMAL`, `isNaN`, `isFinite`, `compare`, `equals` |
| `java.lang.Float` | [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) | Constants, parsing, floating-point comparison |
| `java.lang.Math` | [Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) | `abs`, `floor`, `ceil`, `round`, `floorDiv`, `floorMod`, `addExact`, `nextUp`, `ulp` |
| `java.lang.StrictMath` | [StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html) | Precision/reproducibility contracts of math functions |
| `java.math.BigInteger` | [BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html) | `add`, `divide`, `remainder`, `mod`, `intValueExact` |
| `java.math.BigDecimal` | [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) | `scale`, `precision`, `equals`, `compareTo`, `divide`, `setScale` |
| `java.math.MathContext` | [MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html) | Result precision and rounding mode |
| `java.math.RoundingMode` | [RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) | `HALF_EVEN`, `HALF_UP`, `CEILING`, `FLOOR`, `UNNECESSARY` |
| `java.util.Random` | [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html) | Seed, `nextInt(bound)`, random simulation |
| `java.security.SecureRandom` | [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) | Unpredictable data generation for security purposes |

**Quick find:** open the class Javadoc and use in-page search (`Ctrl+F`) for `methodName` or `fieldName`, then pick the right overload under **Method Details**; or use the Java SE API Search box. When a method has multiple overloads, record the full parameter types in your notes (e.g., `divide(BigDecimal, int, RoundingMode)`).

## 6. Case 1: Why Does Negative Integer Division Differ from `Math.floorDiv`?

**Question:** Are `-7 / 3` and `Math.floorDiv(-7, 3)` the same?

Look up in two steps:

1. **JLS §15.17.2** specifies that the integer division operator `/` rounds the quotient toward **0** (*truncation toward zero*). Therefore `-7 / 3 = -2`.
2. **Javadoc `Math.floorDiv`** defines division toward **negative infinity**; therefore `Math.floorDiv(-7, 3) = -3`.

The signed primitive remainder `%` is tied to truncation-toward-0 division: `-7 % 3 = -1`. `Math.floorMod(-7,3)` corresponds to `floorDiv`, yielding `2`. Sources: JLS §15.17.3 and Javadoc `Math.floorMod`.

**File `NumericJlsDemo.java` – Java 17+:**

```java
public class NumericJlsDemo {
    public static void main(String[] args) {
        System.out.println("intDivision=" + (-7 / 3));
        System.out.println("intRemainder=" + (-7 % 3));
        System.out.println("floorDivision=" + Math.floorDiv(-7, 3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));

        int max = Integer.MAX_VALUE;
        System.out.println("overflow=" + (max + 1));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=ArithmeticException");
        }

        System.out.println("widenedDivision=" + (7.0 / 2));
        System.out.println("integerDivision=" + (7 / 2));
    }
}
```

Commands:

```bash
javac --release 17 NumericJlsDemo.java
java NumericJlsDemo
```

Stdout:

```text
intDivision=-2
intRemainder=-1
floorDivision=-3
floorMod=2
overflow=-2147483648
addExact=ArithmeticException
widenedDivision=3.5
integerDivision=3
```

In this example, `7.0 / 2` performs floating-point division after numeric promotion, whereas `7 / 2` is integer division. The expression `max + 1` is `int` addition and overflows without throwing an exception. `Math.addExact(max,1)` **is a separate API method** whose contract throws `ArithmeticException` on overflow. That is why both JLS and Javadoc must be read together.

## 7. Case 2: Where Does `BigDecimal.equals` Differ from `compareTo`?

**Question:** Why does `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` return `false`, while `compareTo` returns `0`?

This is **library behavior**, not directly the primitive `==` rule. Check the `BigDecimal` class Javadoc and both methods:

- `equals(Object)`: requires both value **and representation/scale** to match.
- `compareTo(BigDecimal)`: compares order by numerical value, and can return 0 for two numbers with different scales.
- `scale()`, `precision()`: explain representation details.
- `setScale(int,RoundingMode)`: adjusts scale, possibly requiring rounding.
- `divide`: each overload specifies a different exactness/rounding policy.

**File `NumericBigDecimalDocsDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NumericBigDecimalDocsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + a.compareTo(b));
        System.out.println("scaleA=" + a.scale());
        System.out.println("scaleB=" + b.scale());
        System.out.println("precisionB=" + b.precision());

        BigDecimal half = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("halfEven=" + half);

        try {
            System.out.println(BigDecimal.ONE.divide(new BigDecimal("3")));
        } catch (ArithmeticException ex) {
            System.out.println("exactDivision=ArithmeticException");
        }

        BigDecimal approx = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println("roundedDivision=" + approx);
    }
}
```

```bash
javac --release 17 NumericBigDecimalDocsDemo.java
java NumericBigDecimalDocsDemo
```

```text
equals=false
compareTo=0
scaleA=1
scaleB=2
precisionB=3
halfEven=2.34
exactDivision=ArithmeticException
roundedDivision=0.33
```

**Read carefully:** `BigDecimal.ONE.divide(new BigDecimal("3"))` cannot produce an exact finite decimal quotient, so it throws `ArithmeticException`; the overload with scale `2` and `HALF_UP` returns `0.33`. Confusing the overloads can lead to applying the wrong rounding or wrongly concluding that `BigDecimal.divide` "always fails when dividing by 3."

Another common misconception: `new BigDecimal(0.1)` and `new BigDecimal("0.1")` are **not identical** in decimal value, because the `double` argument already carries binary representation error. This is explained in the constructor description of `BigDecimal` Javadoc; read **constructor details**, not just the class name.

## 8. Case 3: Widening Does Not Always Mean Keeping Full Precision

**Question:** Can a `long` be converted to a `double` without losing digits?

Check **JLS §5.1.2**: `long` → `double` is a permitted widening primitive conversion, yet **it can lose precision** because `double` has a finite number of significant bits.

An example chosen near the `2^53` threshold:

**File `NumericConversionDocsDemo.java`:**

```java
public class NumericConversionDocsDemo {
    public static void main(String[] args) {
        long original = 9_007_199_254_740_993L;
        double converted = original;

        System.out.println("original=" + original);
        System.out.println("convertedBack=" + (long) converted);
        System.out.println("sameAfterRoundTrip="
                + (original == (long) converted));

        Integer maybe = null;
        try {
            System.out.println(maybe + 1);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
```

```bash
javac --release 17 NumericConversionDocsDemo.java
java NumericConversionDocsDemo
```

```text
original=9007199254740993
convertedBack=9007199254740992
sameAfterRoundTrip=false
unboxing=NullPointerException
```

Check **JLS §5.1.7–§5.1.8** to understand boxing/unboxing. `maybe + 1` requires unboxing `Integer` to `int`; because `maybe == null`, it throws `NullPointerException`. `Integer` Javadoc explains the wrapper type and its methods; conversion rules inside the **`+` expression** belong to the JLS.

The example also reminds us that a conversion valid under the type system may **fail data requirements** if business logic demands keeping every digit exact.

## 9. Case 4: `Double.MIN_VALUE`, `NaN`, and Signed Zero

**Question:** Why is `Double.MIN_VALUE` positive and `Double.NaN == Double.NaN` false?

Look up both together:

1. Javadoc `Double.MIN_VALUE` defines it as the **smallest nonzero positive `double` value**; `Double.MIN_NORMAL` is the smallest positive normal value.
2. JLS §4.2.3–§4.2.4 describe `float`/`double` values, including signed zero, infinities, and NaN.
3. JLS §15.21.1 specifies numeric equality: `NaN == NaN` evaluates to false, while `0.0 == -0.0` evaluates to true.
4. Javadoc `Double.equals` and `Double.compare` describe the separate rules when **both values are wrappers**: NaN and signed zero are handled differently from primitive `==`.

**File `NumericFloatingDocsDemo.java`:**

```java
public class NumericFloatingDocsDemo {
    public static void main(String[] args) {
        System.out.println("minPositive=" + Double.MIN_VALUE);
        System.out.println("nextUpZero=" + Math.nextUp(0.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));
        System.out.println("nanPrimitive="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapper="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitive=" + (0.0 == -0.0));
        System.out.println("zeroWrapper="
                + Double.valueOf(0.0)
                        .equals(Double.valueOf(-0.0)));
    }
}
```

```bash
javac --release 17 NumericFloatingDocsDemo.java
java NumericFloatingDocsDemo
```

```text
minPositive=4.9E-324
nextUpZero=4.9E-324
nextUpOne=1.0000000000000002
nanPrimitive=false
nanWrapper=true
zeroPrimitive=true
zeroWrapper=false
```

When you need to test whether a value is NaN or finite, read the contracts of `Double.isNaN` and `Double.isFinite`. Do not use `x == Double.NaN` to detect NaN. When considering "the next representable value", `Math.nextUp`, `nextDown`, and `ulp` are defined in `Math` Javadoc, rather than adding `x + 0.0000001` across all magnitudes.

## 10. Choosing the Right Version and Avoiding "Correct but Unusable" Information

A blog post might introduce a method valid in Java 21 while the project uses Java 17. In that case, the code will fail to compile, even if the idea is valid.

**Version checklist:**

- Check runtime: `java -version`.
- Check compiler: `javac -version`.
- Check project configuration (Maven `maven.compiler.release`, Gradle toolchain, or `--release`) when present.
- Look up Javadoc for the exact target **Java SE release**, not blindly the "latest" page.
- Check the **Since** tag on classes and methods; methods added in a newer release may not exist in an older one.
- Use `javac --release 17 Demo.java` to verify **language and public API** against target Java 17 when compiling with a JDK supporting this flag. Afterward, still test on the target runtime.

For example, **do not assume** a method name read in Java 21 Javadoc also exists in Java 17. If Java 17 lacks the corresponding API, use a Java 17-compatible alternative or submit a justified request to upgrade Java.

### Javadoc Differs from Implementation Detail

A method's Javadoc may state "returns..." and "throws...": that is part of the API contract. A sentence saying "implementation may use ..." or a property dependent on provider/OS may merely be an implementation detail. Keep the boundary clear:

- **Contract:** clients are permitted to rely on it.
- **Implementation note:** useful information for optimization/diagnostics, not necessarily guaranteed across every platform.
- **JLS:** standardized language rules for compliant compilers/Java implementations.

For example, `Math` and `StrictMath` document accuracy and reproducibility of math functions. Read the class overview and individual method docs before claiming "`Math.sin` always returns the exact same bit-pattern on every platform."

## 11. Search Tips and Citing Sources

When it is unclear where an issue lives, search using standard English documentation terms:

| Issue | Search Keywords | Priority Page |
|---|---|---|
| `int` overflow | `integer overflow JLS 4.2.2` | JLS §4.2.2 or §15.18.2 |
| Negative division | `integer division rounds toward zero JLS 15.17.2` | JLS §15.17.2 |
| Numeric casting | `widening narrowing primitive conversion JLS 5.1` | JLS §5.1.2/§5.1.3 |
| Boxing cache / null unboxing | `JLS 5.1.7 5.1.8` | JLS §5.1.7–§5.1.8 |
| Wrapper `==` | `reference equality JLS 15.21` | JLS §15.21 |
| `Math.abs` of MIN_VALUE | `Math abs Integer.MIN_VALUE Java 17` | Javadoc `Math.abs(int)` |
| `BigDecimal.equals` | `BigDecimal equals compareTo scale Javadoc` | Javadoc `BigDecimal` |
| `BigDecimal.divide` | `BigDecimal divide ArithmeticException non terminating` | Javadoc exact `divide` overload |
| Rounding policy | `RoundingMode HALF_EVEN table` | Javadoc `RoundingMode` |
| `Double.MIN_VALUE` | `Double MIN_VALUE MIN_NORMAL Java 17` | Javadoc `Double` |

If using external search engines, restrict results to official domains such as `docs.oracle.com`, then verify the version. Discussion sites, blogs, and forums are helpful for examples, but for **language/API contracts**, base your conclusions on the original JLS/Javadoc. For an issue involving interaction across multiple APIs, cite two or more sources instead of forcing everything into one link.

**Good citation:** "Java SE 17 JLS §15.17.2 (integer division) specifies integer division toward 0; Javadoc `Math.floorDiv(int,int)` defines floor division."  
**Insufficient citation:** "Read online that Java divides negative numbers oddly."

## 12. Common Lookup Mistakes

1. **Looking up Javadoc for operators:** `int + int`, `/`, `%`, `==` belong to the JLS; the `Integer` class does not directly replace the semantics of every operator.
2. **Looking up the JLS for library overloads:** `BigDecimal.divide` and `Math.floorDiv` have method contracts described in Javadoc; the JLS only defines method invocation and related language rules.
3. **Ignoring operand types:** `7 / 2` and `7.0 / 2` differ due to numeric promotion; wrappers also involve unboxing.
4. **Ignoring negative signs/zero:** `-7 / 3`, `-7 % 3`, `Math.floorDiv`, `Double.NaN`, and `+0.0`/`-0.0` are often the tests distinguishing right from wrong.
5. **Reading only the method summary:** missing overloads, `Throws`, `Since`, or warnings inside method details.
6. **Confusing `MIN_VALUE`:** `Integer.MIN_VALUE` is the negative bound, whereas `Double.MIN_VALUE` is the smallest nonzero **positive** number.
7. **Using Javadoc from a newer version:** code will not compile on an older target even if the "latest" page documents a valid API.
8. **Inferring from a single run:** a result can depend on implementation/provider; running a program is verification, not a substitute for the specification.
9. **Seeing the word "exact" and ignoring the target type:** `Math.addExact`, `BigDecimal.divide`, and `BigInteger.intValueExact` each have specific exactness semantics and exceptions depending on the method; read the exact signature.
10. **Ignoring precision/scale:** the same mathematical value can differ under `BigDecimal.equals`; looking at `toString` without checking `scale()` causes misunderstandings.
11. **Forgetting that JLS/Javadoc are authoritative English specifications:** when translating terms like `truncation`, `floor`, `ceiling`, `round toward zero`, and `narrowing`, keep the original terminology alongside to minimize ambiguity.
12. **Treating FAQs/previews/screenshots as final authority:** prefer versioned specification pages with exact section and method links.

## 13. Lookup Exercises with Answers

1. **Question:** Is `-7 / 3` floor division? Where do you look it up?  
   **Answer:** No, primitive `int` `/` truncates the quotient toward 0, giving `-2`; see **JLS §15.17.2**. For floor division `-3`, see `Math.floorDiv` in **Javadoc `Math`**.

2. **Question:** Does `Math.addExact(Integer.MAX_VALUE,1)` differ from `Integer.MAX_VALUE+1`?  
   **Answer:** Yes. The primitive operator overflows per the JLS; `Math.addExact` throws `ArithmeticException` per the method Javadoc. The `+` result is `Integer.MIN_VALUE`.

3. **Question:** Is `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` being `false` due to the JLS or Javadoc?  
   **Answer:** Primarily the contract of `BigDecimal.equals` in **Javadoc `BigDecimal`**; compare numerical values with `compareTo() == 0`.

4. **Question:** Why is `Double.MIN_VALUE > 0`?  
   **Answer:** The constant `MIN_VALUE` is defined by **Javadoc `Double`** as the smallest nonzero positive value. JLS §4.2.3 describes the `double` value model.

5. **Question:** If `Integer x = null;`, what does `x + 1` do?  
   **Answer:** Throws `NullPointerException` upon unboxing; see **JLS §5.1.8** and §5.6. `x == null` is reference equality only, so it does not unbox.

6. **Question:** Where do you find `Math.nextUp(1.0)`?  
   **Answer:** Method detail of **Javadoc `Math`**. It returns the adjacent representable `double` above 1.0, printed as `1.0000000000000002`.

7. **Question:** Does `BigDecimal.ONE.divide(new BigDecimal("3"))` round automatically?  
   **Answer:** The exact-division overload throws `ArithmeticException` when the decimal quotient does not terminate; see **Javadoc `BigDecimal.divide(BigDecimal)`**. Choose an overload with scale and rounding mode when business rules allow rounding.

8. **Question:** Why does the same method call compile on a newer JDK yet fail on Java 17?  
   **Answer:** Check the **Since** tag and Javadoc version, and use `javac --release 17` to verify public APIs against the target; the method may not yet be supported on Java 17.

9. **Question:** If you want to find why `byte b = 1; b += 1;` differs from `b = b + 1;`, where do you read?  
   **Answer:** **JLS §5.6** on numeric promotion and **§15.26.2** on compound assignment. Not only `Byte` Javadoc.

10. **Question:** When writing an arithmetic bug report, how should you cite evidence?  
    **Answer:** State the Java version, operand types, exact expression, method overload (if any), expected/actual results, minimal reproduction code, and links to the relevant JLS section or Javadoc method.

## 14. Quick Pre-Conclusion Lookup Checklist

- [ ] Record exact target Java version and compile/run commands.
- [ ] Identify whether it is a **language operator**, **type conversion**, or **library method**.
- [ ] Check JLS §4, §5, §15 if involving primitives, operators, promotion, casting, or boxing/unboxing.
- [ ] Check **the exact class, exact overload, and exact Java release** in Javadoc if involving APIs.
- [ ] Read `Returns`, `Throws`, `Since`, and warnings in class/method details.
- [ ] Check boundaries: MIN/MAX, negative numbers, zero, NaN/Infinity, scale, rounding.
- [ ] Write a small program with deterministic output and cross-check against the spec.
- [ ] Distinguish what is **guaranteed** from implementation/provider details.
- [ ] Save links to the exact section or method in knowledge notes, tests, or reviews.

## 15. Summary

For Java Core – numbers, remember one principle: **the JLS explains how Java evaluates expressions; Javadoc explains what public numeric libraries guarantee.** When verifying a behavior:

1. Determine the **types and Java version**.
2. Find the **exact JLS section** for operators/conversions, or the **exact Javadoc method** for APIs.
3. Read **edge cases, exceptions, rounding, and overloads**.
4. Use a Java 17+ example to reproduce, while basing your conclusion on the **specification contract**.
5. Record official sources with section/method names so others can verify them independently.

Primary sources: [JLS SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html), [Java SE 17 Javadoc – `java.base`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
