# `BigDecimal.setScale()` and Returning a New Object

## 1. Lesson Goals

In Java, `BigDecimal` represents decimal numbers with arbitrary precision, commonly used for money, taxes, rates, and calculations requiring control over decimal digits. `setScale()` sets the **scale** of the resulting value; it **does not modify the original `BigDecimal` object** because this class is *immutable*. You must use the return value if you need the result with the updated scale.

```java
BigDecimal price = new BigDecimal("12.345");
price.setScale(2, RoundingMode.HALF_UP); // Result ignored!
System.out.println(price);              // 12.345

BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded); // 12.35
System.out.println(price);   // 12.345
```

Standalone illustrative snippets in this lesson assume `import java.math.BigDecimal;` and `import java.math.RoundingMode;`. A complete, compilable example is in Section 5.

## 2. How Does Scale Differ from Precision?

`BigDecimal` represents a value using an **unscaled value** (an integer) and a **scale** according to the formula:

```text
value = unscaledValue × 10^(-scale)
```

For example, `new BigDecimal("123.4500")` has `unscaledValue() = 1234500`, `scale() = 4`, and `precision() = 7`. Scale indicates the decimal point position; precision is the total number of significant digits in the representation. After `setScale(2)`, the result `123.45` has unscaled value `12345` and scale `2`, while the mathematical value stays the same.

`new BigDecimal("2.5")` has scale 1, whereas `new BigDecimal("2.500")` has scale 3. Same numeric value, different representation. `setScale(2)` requests **two positions after the decimal point**, not two significant digits; to limit significant digits, study `MathContext` and the operations that apply it.

Scale can also be negative: `new BigDecimal("1234").setScale(-2, RoundingMode.HALF_UP)` represents the value `1200` at scale -2 and may print `1.2E+3`. Negative scale corresponds to rounding to tens, hundreds, or larger powers.

## 3. Three Overloads and Rules for Changing Scale

| API | Meaning |
| --- | --- |
| `setScale(int newScale)` | Permits only **exact** scale changes; if any nonzero digit must be discarded, throws `ArithmeticException`. |
| `setScale(int newScale, RoundingMode roundingMode)` | Allows rounding when needed according to the chosen mode. |
| `setScale(int newScale, int roundingMode)` | Legacy overload taking an `int` constant, deprecated; use `RoundingMode`. |

**Increasing scale** appends trailing zeros without changing the arithmetic value:

```java
BigDecimal x = new BigDecimal("7.2");
System.out.println(x.setScale(3)); // 7.200
System.out.println(x);             // 7.2
```

**Decreasing scale** must examine the discarded part:

```java
new BigDecimal("7.2300").setScale(2);                    // 7.23, exact
new BigDecimal("7.235").setScale(2, RoundingMode.HALF_UP); // 7.24
new BigDecimal("7.235").setScale(2);                    // ArithmeticException
```

Saying “`setScale(2)` always rounds” is false: the one-argument overload has no default rounding mode. However, saying “decreasing scale always errors” is also false: reducing from `7.2300` to `7.23` loses no nonzero significant digits, so it remains exact.

If `RoundingMode.UNNECESSARY` is used, the method actively throws `ArithmeticException` whenever rounding is required. This approach is useful when validating that input data already has the right scale.

## 4. Understanding and Choosing `RoundingMode`

Example with positive number `2.345` to scale 2:

| Mode | Result | Rule |
| --- | --- | --- |
| `HALF_UP` | `2.35` | At exact midpoint between two levels, rounds away from 0. |
| `HALF_EVEN` | `2.34` | At midpoint, chooses an even last retained digit; `2.355` becomes `2.36`. |
| `DOWN` | `2.34` | Truncates discarded part, toward 0. |
| `UP` | `2.35` | When any nonzero part is discarded, rounds away from 0. |
| `CEILING` | `2.35` | Rounds toward positive infinity. |
| `FLOOR` | `2.34` | Rounds toward negative infinity. |
| `UNNECESSARY` | Exception | Does not allow loss of accuracy. |

Negative numbers show how `CEILING` and `FLOOR` differ from `UP` and `DOWN`:

```java
BigDecimal negative = new BigDecimal("-2.345");
System.out.println(negative.setScale(2, RoundingMode.CEILING)); // -2.34
System.out.println(negative.setScale(2, RoundingMode.FLOOR));   // -2.35
System.out.println(negative.setScale(2, RoundingMode.HALF_UP)); // -2.35
```

`HALF_EVEN` can reduce overall bias when many results fall halfway between two levels. However, business requirements, financial regulations, or currency rules are the basis for choosing a mode; no single `RoundingMode` is right for all systems.

## 5. Complete Java 17+ Program

Save to file `BigDecimalSetScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalSetScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("12.345");
        BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
        System.out.println("original = " + original);
        System.out.println("rounded = " + rounded);

        BigDecimal amount = new BigDecimal("2.5");
        BigDecimal expanded = amount.setScale(3);
        System.out.println("expanded = " + expanded);
        System.out.println("amount unchanged = " + amount);

        BigDecimal exact = new BigDecimal("12.340").setScale(2);
        System.out.println("exact = " + exact);

        BigDecimal tie = new BigDecimal("2.345");
        System.out.println("HALF_UP = " + tie.setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN = " + tie.setScale(2, RoundingMode.HALF_EVEN));

        BigDecimal sameScale = new BigDecimal("1.20");
        BigDecimal result = sameScale.setScale(2);
        System.out.println("same value = " + sameScale.equals(result));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac BigDecimalSetScaleDemo.java
java BigDecimalSetScaleDemo
```

Standard output:

```text
original = 12.345
rounded = 12.35
expanded = 2.500
amount unchanged = 2.5
exact = 12.34
HALF_UP = 2.35
HALF_EVEN = 2.34
same value = true
```

Explanation: `rounded` receives the rounded result, while `original` remains unchanged. `expanded` gains two zeros because scale increases from 1 to 3. `exact` only drops a zero, so no rounding mode is needed. `tie` illustrates the difference between two rounding policies at an exact midpoint. The `sameScale` case checks equality by value and scale, not reference difference.

## 6. Understanding “Returning a New Object” Correctly

Semantically, `setScale()` returns a `BigDecimal` with the requested new scale without **mutating the state of the original object**:

```java
BigDecimal a = new BigDecimal("10.555");
BigDecimal b = a.setScale(2, RoundingMode.HALF_UP);
// a: 10.555, scale = 3
// b: 10.56, scale = 2
```

However, do not infer that the JVM **always allocates a physically different instance**. When the scale already equals the requested scale, or due to reuse/caching, an implementation may return the same reference as before. Do not write checks like `a != a.setScale(a.scale())` expecting them to always be true. The API contract is **result value + immutability**, not a fresh reference identity on every call.

Distinguish the following usages:

- `amount.setScale(2, mode);`: the result is discarded; `amount` does not change.
- `amount = amount.setScale(2, mode);`: reassigns the local variable to the result reference; the original object still does not change.
- `return amount.setScale(2, mode);`: returns the normalized result to the caller.
- For a `final BigDecimal amount` variable, you can create `BigDecimal rounded = amount.setScale(...)`, though you cannot reassign `amount`.

Because `BigDecimal` objects are immutable, sharing the same object across threads is safe with respect to internal state. If multiple threads read and reassign **a shared variable/field** holding a `BigDecimal` reference, synchronization or an appropriate thread-safe data structure is still required; immutability does not automatically make multiple reference updates atomic.

## 7. Impact on `equals()`, `compareTo()`, and Collections

`setScale()` can change the result of `equals()` even when the arithmetic value stays the same:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = x.setScale(2); // 2.00

System.out.println(x.equals(y));    // false
System.out.println(x.compareTo(y)); // 0
System.out.println(x.scale());      // 1
System.out.println(y.scale());      // 2
```

`BigDecimal.equals()` checks both represented value and scale; `compareTo()` compares by mathematical numeric value. Therefore, for the question “are two numbers arithmetically equal?”, normally use `compareTo(...) == 0`. Meanwhile, `HashSet<BigDecimal>` and `HashMap<BigDecimal, ...>` keys use `equals()/hashCode()`: `2.0` and `2.00` can be two distinct keys. If business logic requires canonicalized keys, apply a consistent scale strategy **before storing/querying**.

`stripTrailingZeros()` also returns a `BigDecimal` and can alter scale; it does not replace `setScale(n, mode)` when a fixed number of decimal digits is required. Also remember that string display formatting (e.g., locale-specific currency) is a separate responsibility: do not infer a display contract solely from `BigDecimal.toString()`.

## 8. Practical Scenario: Rounding Monetary Amounts

Suppose business rules require rounding a payable amount to two decimal places using `HALF_UP`. The following standalone program shows how to write a function returning the result while keeping the input untouched:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyExample {
    static BigDecimal toTwoDecimals(BigDecimal amount) {
        return amount.setScale(2, RoundingMode.HALF_UP);
    }

    public static void main(String[] args) {
        BigDecimal raw = new BigDecimal("19.995");
        BigDecimal payable = toTwoDecimals(raw);
        System.out.println("raw = " + raw);
        System.out.println("payable = " + payable);
    }
}
```

Save as `MoneyExample.java`, run `javac MoneyExample.java` then `java MoneyExample`:

```text
raw = 19.995
payable = 20.00
```

The `toTwoDecimals` function normalizes data at the business boundary. You must decide **when to round**: per invoice line, after summing totals, before/after tax, etc. Rounding early at every step can cause the final total to differ from rounding once. Choosing scale 2 in this example is an assumed convention, not valid for every currency and regulation.

If you need to verify that an input value already has the right scale without allowing rounding:

```java
BigDecimal valid = new BigDecimal("10.00");
BigDecimal invalid = new BigDecimal("10.001");
System.out.println(valid.setScale(2, RoundingMode.UNNECESSARY)); // 10.00
// invalid.setScale(2, RoundingMode.UNNECESSARY) throws ArithmeticException.
```

## 9. Common Mistakes

1. **Not keeping the return value:** calling `x.setScale(2, mode)` and continuing to use `x`. Fix: assign to a result variable, reassign if allowed, or return it.
2. **Believing the one-argument overload always rounds:** `new BigDecimal("1.235").setScale(2)` throws `ArithmeticException`. If digits might be lost, choose a `RoundingMode` per business logic.
3. **Believing decreasing scale always errors:** `new BigDecimal("1.2300").setScale(2)` is valid because it is exact.
4. **Incorrectly initializing from `double`:** `new BigDecimal(0.1)` preserves the exact binary value of `double` (which does not equal exact decimal 0.1). Create using `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` where appropriate.
5. **Confusing scale and precision:** `setScale(2)` positions the decimal point rather than limiting to two significant digits; use `MathContext` when the problem requires precision.
6. **Wrong comparisons:** `==` checks reference; `equals()` also checks scale; `compareTo()` checks arithmetic value.
7. **Waiting until after division to call `setScale()`:** `BigDecimal.ONE.divide(new BigDecimal("3"))` can throw `ArithmeticException` due to a non-terminating fractional part; `setScale()` cannot rescue a division that already failed. Use the `divide(divisor, scale, roundingMode)` overload when dividing with rounding.
8. **Misunderstanding immutable methods:** `add()`, `subtract()`, `multiply()`, `divide()`, and `setScale()` all return values; use the result when needed.
9. **Arbitrarily rounding multiple times:** total results can change if intermediate rounding is performed. Write tests for boundaries like `1.005`, `-1.005`, `2.345`, and the chosen business rules.

## 10. Self-Check Questions

- Does `new BigDecimal("5.200").setScale(1)` error? **No**: returns `5.2` because only zeros are dropped.
- Does `new BigDecimal("5.201").setScale(1)` error? **Yes**: `ArithmeticException` because a nonzero significant digit must be dropped.
- After `BigDecimal x = new BigDecimal("1.234"); x.setScale(2, RoundingMode.DOWN);`, what is `x`'s value? Still **`1.234`**, because the result `1.23` was not kept.
- What does `new BigDecimal("8").setScale(2).toString()` return? **`"8.00"`**.
- Why is `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` false? Because the two objects have different scales, even though `compareTo()` returns 0.
- Why shouldn't you claim `setScale()` always creates a new instance? Because the API guarantees immutability and the result value, not that reference identity is always distinct.

**Key Takeaway:** `setScale()` returns a value with the requested scale; it does not modify the original `BigDecimal`. Choose an explicit rounding rule, always use the return value, and distinguish scale from mathematical value.