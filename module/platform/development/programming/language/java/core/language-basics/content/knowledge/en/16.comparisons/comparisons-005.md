# NaN and Counterintuitive Comparison Results — Java 17+

`NaN` (*Not a Number*) is a special value of Java's floating-point types `float` and `double`, not `null` or an exception. Undefined operations can produce NaN:

~~~java
double nan = 0.0 / 0.0;
double alsoNan = Math.sqrt(-1.0);
~~~

**Counterintuitive point:** under primitive floating-point comparisons, NaN **is not equal to itself**. If at least one operand is NaN, then `==`, `<`, `<=`, `>`, and `>=` all return **false**, while `!=` returns **true**.

~~~java
double x = Double.NaN;
System.out.println(x == x);    // false.
System.out.println(x != x);    // true.
System.out.println(x < 10.0);  // false.
System.out.println(x >= 10.0); // false.
~~~

Because of this, **`!(x > 10)` is not always equivalent to `x <= 10`**. When `x` is NaN, the first expression is true while the second is false.

## 1. NaN Comparison Rules Table

Suppose `double x = Double.NaN`:

| Expression | Result | Explanation |
| --- | --- | --- |
| `x == x` | false | NaN is not equal to itself under `==` |
| `x != x` | true | Inequality rule with NaN |
| `x < 5.0` | false | Ordering relation is undefined |
| `x <= 5.0` | false | Cannot be inferred from "not greater than" |
| `x > 5.0` | false | Ordering relation is undefined |
| `x >= 5.0` | false | Ordering relation is undefined |
| `5.0 < x` | false | Same when NaN is the right-hand operand |
| `!(x > 5.0)` | true | Negating a comparison that returned false |
| `Double.isNaN(x)` | true | Purpose-built NaN check |

The corresponding rules also apply to `float`. **Do not use `x == Double.NaN` to test for NaN**; use `Double.isNaN(x)` or `Float.isNaN(x)`.

## 2. Self-Contained Java 17+ Demo Run via CLI

Create a UTF-8 file named **`NaNComparisonDemo.java`**:

~~~java
import java.util.TreeSet;

public class NaNComparisonDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;

        System.out.println("== primitive ==");
        System.out.println("nanIsNaN=" + Double.isNaN(nan));
        System.out.println("nanEqSelf=" + (nan == nan));
        System.out.println("nanNeSelf=" + (nan != nan));
        System.out.println("nanLess=" + (nan < 5.0));
        System.out.println("nanLessEqual=" + (nan <= 5.0));
        System.out.println("nanGreater=" + (nan > 5.0));
        System.out.println("nanGreaterEqual=" + (nan >= 5.0));
        System.out.println("reverseLess=" + (5.0 < nan));
        System.out.println("notGreater=" + (!(nan > 5.0)));
        System.out.println("lessOrEqual=" + (nan <= 5.0));

        System.out.println("== detecting ==");
        System.out.println("sqrtNaN="
                + Double.isNaN(Math.sqrt(-1.0)));
        System.out.println("infinityMinusInfinityNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        - Double.POSITIVE_INFINITY));
        System.out.println("nanPlusOne="
                + Double.isNaN(nan + 1.0));
        System.out.println("parsedNaN="
                + Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("nanFinite=" + Double.isFinite(nan));
        System.out.println("fiveFinite=" + Double.isFinite(5.0));
        System.out.println("infinityFinite="
                + Double.isFinite(Double.POSITIVE_INFINITY));
        System.out.println("mathMinNaN="
                + Double.isNaN(Math.min(nan, 3.0)));

        System.out.println("== wrapper and ordering ==");
        Double first = Double.valueOf(Double.NaN);
        Double second = Double.valueOf(Double.NaN);
        System.out.println("wrapperEquals=" + first.equals(second));
        System.out.println("compareNaNs=" + Double.compare(nan, nan));
        System.out.println("nanAfterInfinity="
                + (Double.compare(nan, Double.POSITIVE_INFINITY) > 0));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zerosPrimitiveEqual="
                + (positiveZero == negativeZero));
        System.out.println("zerosWrapperEqual="
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("compareZeros="
                + Double.compare(positiveZero, negativeZero));
        System.out.println("reciprocalNegZero="
                + (1.0 / negativeZero));

        TreeSet<Double> sorted = new TreeSet<>();
        sorted.add(Double.NaN);
        sorted.add(Double.NaN);
        sorted.add(Double.POSITIVE_INFINITY);
        sorted.add(Double.NEGATIVE_INFINITY);
        sorted.add(positiveZero);
        sorted.add(negativeZero);
        System.out.println("sorted=" + sorted);
        System.out.println("sortedSize=" + sorted.size());

        System.out.println("== float and precision ==");
        float fn = Float.NaN;
        System.out.println("floatEqualsSelf=" + (fn == fn));
        System.out.println("floatIsNaN=" + Float.isNaN(fn));

        double sum = 0.1 + 0.2;
        System.out.println("decimalSum=" + sum);
        System.out.println("decimalExactlyEqual=" + (sum == 0.3));

        boolean validScore = Double.isFinite(nan)
                && nan >= 0.0 && nan <= 100.0;
        System.out.println("nanValidScore=" + validScore);
    }
}
~~~

Requires **JDK 17 or later**. Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NaNComparisonDemo.java
java NaNComparisonDemo
~~~

**Exact expected stdout** of `java NaNComparisonDemo` (excluding JDK version output):

~~~text
== primitive ==
nanIsNaN=true
nanEqSelf=false
nanNeSelf=true
nanLess=false
nanLessEqual=false
nanGreater=false
nanGreaterEqual=false
reverseLess=false
notGreater=true
lessOrEqual=false
== detecting ==
sqrtNaN=true
infinityMinusInfinityNaN=true
nanPlusOne=true
parsedNaN=true
nanFinite=false
fiveFinite=true
infinityFinite=false
mathMinNaN=true
== wrapper and ordering ==
wrapperEquals=true
compareNaNs=0
nanAfterInfinity=true
zerosPrimitiveEqual=true
zerosWrapperEqual=false
compareZeros=1
reciprocalNegZero=-Infinity
sorted=[-Infinity, -0.0, 0.0, Infinity, NaN]
sortedSize=5
== float and precision ==
floatEqualsSelf=false
floatIsNaN=true
decimalSum=0.30000000000000004
decimalExactlyEqual=false
nanValidScore=false
~~~

## 3. Negating a Relation Does Not Automatically Produce the Opposite Relation

For two ordinary finite numbers, developers often treat `!(a > b)` as equivalent to `a <= b`. With NaN, however:

~~~java
double a = Double.NaN;
double b = 5.0;
boolean negated = !(a > b); // true.
boolean opposite = a <= b; // false.
~~~

The table below shows transformations that **must not be applied blindly** when NaN is possible:

| Negated expression | Assumed equivalent alternative | Result when `a` is NaN |
| --- | --- | --- |
| `!(a > b)` | `a <= b` | true vs. false |
| `!(a >= b)` | `a < b` | true vs. false |
| `!(a < b)` | `a >= b` | true vs. false |
| `!(a <= b)` | `a > b` | true vs. false |
| `!(a == b)` | `a != b` | Both true |

Only the last row always preserves a direct negation relationship between `==` and `!=`. The ordering operator pairs cease to be opposite negations when NaN is present.

In particular, the condition `!(score > 100)` accepts NaN values, so **do not use it alone to validate scores**. If only finite numbers in the interval [0, 100] are allowed:

~~~java
static boolean validScore(double score) {
    return Double.isFinite(score)
            && score >= 0.0
            && score <= 100.0;
}
~~~

`Double.isFinite` rejects NaN as well as ±Infinity. The `&&` operator short-circuits, so if the finiteness check is false, the remaining conditions are not evaluated.

## 4. Primitive `==`, Wrapper `equals`, and `Double.compare` Differ

~~~java
double nan = Double.NaN;

System.out.println(nan == nan); // false.
System.out.println(Double.valueOf(nan)
        .equals(Double.valueOf(nan))); // true.
System.out.println(Double.compare(nan, nan)); // 0.
~~~

| Mechanism | Two NaNs | `+0.0` and `-0.0` |
| --- | --- | --- |
| Primitive `double ==` | Not equal | Equal |
| `Double.equals` | Equal | Not equal |
| `Double.compare` | Returns 0 | Distinguished, `compare(+0.0, -0.0) > 0` |

`Double.compare(a, b)` establishes a total ordering suitable for sorting: NaN **comes after every other `double` value**, including `Infinity`; two NaNs are considered equivalent in that ordering. This is a rule of the **comparison method** and does not alter the behavior of primitive relational operators:

~~~java
Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0 // true.
Double.NaN > Double.POSITIVE_INFINITY // false.
~~~

Note: `==` between **two `Double` objects** is reference comparison. To compare wrapper values, use `equals` or `compare` per their contract; to use primitive operators, unbox and check for null when necessary.

## 5. Why Does `TreeSet<Double>` Place NaN at the End?

`TreeSet<Double>` uses the natural ordering of `Double.compareTo`. For example:

~~~java
TreeSet<Double> set = new TreeSet<>();
set.add(Double.NaN);
set.add(-0.0);
set.add(+0.0);
set.add(Double.POSITIVE_INFINITY);
set.add(Double.NEGATIVE_INFINITY);
~~~

The element order is:

~~~text
[-Infinity, -0.0, 0.0, Infinity, NaN]
~~~

- `-Infinity` comes before finite numbers.
- `-0.0` and `+0.0` are **two distinct elements** according to the comparator.
- `Infinity` comes before NaN.
- Adding NaN again does not create a second NaN element because `Double.compare` treats NaNs as equivalent.

This does not contradict `NaN == NaN` being false: the container uses a **comparator**, while expressions use primitive value operators.

## 6. Signed Zeros `+0.0` and `-0.0`

~~~java
double plus = 0.0;
double minus = -0.0;

System.out.println(plus == minus);       // true.
System.out.println(Double.compare(plus, minus)); // 1.
System.out.println(1.0 / minus);         // -Infinity.
~~~

Primitive `==` treats both zero values as equal, yet the sign is preserved in the floating-point representation and affects operations such as reciprocals. `Double.equals` and `Double.compare` distinguish them.

Therefore, also avoid using primitive `<` and `>` to infer the sign bit of zero: `-0.0 < +0.0` is false, while `-0.0 <= +0.0` is true.

## 7. NaN Differs from Infinity and Binary Rounding Error

| Phenomenon | Example | How to check or handle |
| --- | --- | --- |
| NaN | `0.0 / 0.0`, `Math.sqrt(-1.0)` | `Double.isNaN` |
| ±Infinity | `1.0 / 0.0`, `-1.0 / 0.0` | `Double.isInfinite` |
| Finite number | `5.0`, `-0.0` | `Double.isFinite` |
| Rounding error | `0.1 + 0.2` | Analyze `double` precision |

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);         // 0.30000000000000004.
System.out.println(sum == 0.3);  // false.
~~~

`sum` is a **finite** number, not NaN. The discrepancy comes from **binary** floating-point representation, not NaN comparison rules. If exact decimal arithmetic is required (such as currency), consider `BigDecimal` created from strings along with scale/rounding rules; for measured quantities, use a domain-appropriate tolerance rule.

## 8. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`x == Double.NaN` detects NaN." | Always false in primitive comparison; use `Double.isNaN(x)` |
| "If it is not less than, it must be greater than or equal." | False for NaN |
| "`NaN != NaN` should be false because it has the same name." | Primitive `!=` returns true |
| "`Double.compare(NaN, NaN)` returns non-zero." | Returns 0 |
| "`Double.equals` always behaves like `double ==`." | They differ for NaN and ±0.0 |
| "`0.0` and `-0.0` behave identically in every API." | Comparators, wrappers, and reciprocals distinguish them |
| "`Double.parseDouble("NaN")` throws an exception." | It parses into NaN |
| "`Double.isFinite` confirms exact decimal representation." | It only confirms the value is neither NaN nor Infinity |

## 9. Exercises and Answers

1. What are `Double.NaN == Double.NaN` and `Double.NaN != Double.NaN`?  
   *Answer:* `false` and `true`.
2. Given `double x = Double.NaN`, what are the four relations `x < 1`, `x <= 1`, `x > 1`, `x >= 1`?  
   *Answer:* All false.
3. What do `!(x > 1)` and `x <= 1` evaluate to when `x` is NaN?  
   *Answer:* true and false.
4. What is `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))`?  
   *Answer:* true.
5. What is `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0`?  
   *Answer:* true, according to `Double.compare` ordering.
6. What are `0.0 == -0.0` and wrapper `equals` for the two zeros?  
   *Answer:* true and false.
7. Is `Double.isNaN(0.1 + 0.2)` true?  
   *Answer:* false; the result is the finite approximation `0.30000000000000004`.
8. How do you check that `score` is in [0, 100] while rejecting both NaN and Infinity?  
   *Answer:* `Double.isFinite(score) && score >= 0 && score <= 100`.

## Checklist

- [ ] NaN belongs to `float`/`double`, not null or an exception.
- [ ] For NaN, `==`/`<`/`<=`/`>`/`>=` return false and `!=` returns true.
- [ ] Use `Double.isNaN` or `Float.isNaN`, never compare against the NaN constant.
- [ ] `!(a > b)` is not equivalent to `a <= b` when NaN is present.
- [ ] Distinguish primitive `==`, wrapper `Double.equals`, and `Double.compare`.
- [ ] `Double.compare` orders NaN after Infinity and distinguishes signed zeros.
- [ ] Use `Double.isFinite` when only finite values are accepted.
- [ ] Do not confuse finite binary precision error with NaN.

**Conclusion:** NaN makes many floating-point comparison results in Java **counterintuitive**. Writing correct conditions requires understanding **primitive operator rules**, distinguishing them from **wrappers and comparators**, and explicitly validating which special values the business logic allows.
