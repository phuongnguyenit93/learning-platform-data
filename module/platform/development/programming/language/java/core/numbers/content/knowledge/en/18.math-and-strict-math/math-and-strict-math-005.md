# asin, acos, atan, and atan2 in Java — Math and StrictMath

## 1. What Will You Learn?

When you know the **sin, cos, tan** of an angle, how do you find that angle back? When you know the coordinates `(x, y)` of a point, how do you find its bearing/azimuth angle without **confusing quadrants**?

Java provides four important inverse trigonometric functions:

- `Math.asin(x)`: **arc sine**, finds an angle whose sine equals `x`.
- `Math.acos(x)`: **arc cosine**, finds an angle whose cosine equals `x`.
- `Math.atan(x)`: **arc tangent**, finds an angle whose tangent equals `x`.
- `Math.atan2(y, x)`: finds the angle from the `+x` axis to the vector `(x, y)`, taking into account the **signs of both coordinates** to determine the quadrant.

All four have corresponding versions on `StrictMath`. This lesson belongs to **Java Core — Numbers / Math and StrictMath**, using Java 17 or newer.

After completing this lesson, you should be able to:

1. State the exact **valid inputs, output value range, and radian unit** of each function.
2. Understand why inverse operations do not recover every original angle: the functions return a **principal value**.
3. Distinguish `atan(y / x)` from `atan2(y, x)`, remembering that **parameter y comes before x**.
4. Convert radians ↔ degrees using `Math.toRadians` and `Math.toDegrees`.
5. Handle `NaN`, ±Infinity, and **signed zero** per the API contract; understand angles on the ±π boundary.
6. Compare the accuracy bounds of `Math` with the result reproducibility requirements of `StrictMath`.
7. Write geometry code, validate input domains, and build tests for all four quadrants.

Prerequisites: `double` type, IEEE 754 floating-point numbers, Cartesian coordinates, sin/cos/tan, and the meaning of `Math.PI`.

## 2. Inverse Trigonometry Does Not Mean Inverting the Function Over the Entire Real Line

On a circle, many different angles share the same sine or cosine value. For instance:

```text
sin(π / 6) = 1 / 2
sin(5π / 6) = 1 / 2
sin(π / 6 + 2π) = 1 / 2
```

There is no way to **uniquely** select the original angle solely from the `sin` value. Therefore, each inverse trigonometric function picks a **principal value range**.

| Java Function | Meaning | Typical Input Domain | Principal Result Range (radians) |
| --- | --- | --- | --- |
| `asin(v)` | Angle with sin = `v` | `−1 ≤ v ≤ 1` | `[−π/2, +π/2]` |
| `acos(v)` | Angle with cos = `v` | `−1 ≤ v ≤ 1` | `[0, π]` |
| `atan(v)` | Angle with tan = `v` | All finite reals; ±∞ also handled | `[−π/2, +π/2]`, asymptotic at both ends |
| `atan2(y,x)` | Angle of vector `(x,y)` from `+x` axis | Two real coordinates, with IEEE 754 rules for special values | `[−π, +π]` |

**The returned unit is always radians**, not degrees, and **the return type is primitive `double`**. Java provides `Math.asin(double)`, `Math.acos(double)`, `Math.atan(double)`, and `Math.atan2(double,double)`. Passing `float` or `int` into these methods widens to `double`; there is no separate `asin(float)` overload returning `float` in Java 17's `Math`.

Note the endpoints of `atan` for finite arguments: it does not reach exact ±π/2 mathematically for any finite value, though in floating-point representation the result can round to the `double` pattern closest to π/2. When the argument is ±Infinity, Java returns the value closest to ±π/2 per the API contract.

## 3. Converting Degrees and Radians Before Calculating

A full circle has `360° = 2π` radians. Formulas:

```text
radian = degree × π / 180
degree = radian × 180 / π
```

Java provides two standard helpers:

```java
double radians = Math.toRadians(30.0);
double degrees = Math.toDegrees(Math.PI / 6);
```

They return `double`, and conversions can involve **rounding error**; do not claim every magnitude round-trips back and forth with bit-level exactness.

Example:

```java
System.out.println(Math.toDegrees(Math.asin(0.5))); // 30.000000000000004 may appear
```

In the programs below, `printf(Locale.US, "%.1f%n", ...)` is used to **intentionally display one decimal place**, avoiding misunderstanding a printed number near 30 as an incorrect result.

**Common trap:** `Math.asin(0.5)` is approximately `0.5235987756` **radians**, not `30.0` degrees. `Math.asin(30)` is not computing "asin of 30°"; that is an **out-of-domain** argument for asin.

## 4. Math.asin: Arc Sine, Choosing an Angle in [−π/2, π/2]

Mathematical notation `arcsin(v)` or `sin⁻¹(v)` describes **an angle whose sine equals v**. This is the inverse sine function, **not** the value `1/sin(v)`.

For `v` in `[−1,1]`, `Math.asin(v)` yields the principal angle in `[−π/2,π/2]`:

| v | Principal Angle (radians) | Angle in Degrees |
| ---: | --- | ---: |
| −1 | −π/2 | −90° |
| −0.5 | −π/6 | −30° |
| 0 | 0 | 0° |
| 0.5 | π/6 | 30° |
| 1 | π/2 | 90° |

Example:

```java
double angle = Math.asin(0.5);
System.out.printf(java.util.Locale.US, "%.1f%n",
        Math.toDegrees(angle)); // 30.0
```

**Important point:** `Math.asin(Math.sin(theta))` does not always equal `theta`. If `theta` is in quadrant II, `sin(theta)` can match a quadrant I angle, and `asin` will return a result in `[−90°,90°]`. For example, `sin(150°)≈0.5`; `asin(0.5)` returns `30°` rather than `150°`.

### 4.1. Out-of-Domain Inputs and NaN

If `|v| > 1` or `v` is NaN, `Math.asin(v)` returns **NaN**, without throwing `IllegalArgumentException` simply because the numerical domain is invalid.

```java
System.out.println(Double.isNaN(Math.asin(1.01))); // true
System.out.println(Double.isNaN(Math.asin(Double.NaN))); // true
```

`Math.asin(Double.POSITIVE_INFINITY)` and `Math.asin(Double.NEGATIVE_INFINITY)` also return NaN because their magnitude exceeds 1.

If an input should be a ratio in `[−1,1]` but rounding produced `1.0000000000000002`, you may need an error-handling policy. **Do not blindly clamp every input to [−1,1]**: clamping can mask corrupt data like `5.0`; if business logic permits clamping within a defined tolerance, check how far the value is outside the domain before clamping.

### 4.2. Signed Zero

`Math.asin(+0.0)` returns `+0.0`; `Math.asin(-0.0)` returns `-0.0`. Both compare equal under the primitive `==` operator, but have different sign bits. If you need to test the sign of zero, use `Double.doubleToRawLongBits` rather than just `==`.

## 5. Math.acos: Arc Cosine, Choosing an Angle in [0, π]

`Math.acos(v)` returns the principal angle in `[0,π]` with `cos(angle) = v`:

| v | Principal Angle (radians) | Degrees |
| ---: | --- | ---: |
| 1 | 0 | 0° |
| 0.5 | π/3 | 60° |
| 0 | π/2 | 90° |
| −0.5 | 2π/3 | 120° |
| −1 | π | 180° |

Example:

```java
double angle = Math.acos(0.5);
System.out.printf(java.util.Locale.US, "%.1f%n",
        Math.toDegrees(angle)); // 60.0
```

**Input domain is [−1,1]**, just like `asin`; if out of domain or NaN, the result is NaN. `Math.acos(1.0)` returns **+0.0** per the API contract. For `Math.acos(-1.0)`, the result is the `double` value closest to π.

Useful mathematical property:

```text
acos(v) + asin(v) ≈ π/2  (v ∈ [−1,1])
```

The `≈` symbol indicates it may deviate slightly due to floating-point rounding. Do not test that the sum equals exact `Math.PI/2` for all inputs.

### 5.1. Why Does acos Not Replace atan2 for Finding Direction?

`acos(x/r)` only returns an angle in `[0,π]`, giving no indication of whether the `y` coordinate lies **above or below** the x-axis. Knowing only the cosine, `+60°` and `−60°` share the same cosine. From a vector `(x,y)`, the direct way to know both sign and quadrant is `atan2(y,x)`.

## 6. Math.atan: Arc Tangent of a Ratio

`Math.atan(v)` is the principal angle whose tangent is `v`; the value range lies near `(−π/2,π/2)` for finite arguments. Unlike `asin`/`acos`, `atan` **does not restrict input to [−1,1]**.

Some landmarks:

| v | Radian Result | Degrees |
| --- | --- | --- |
| −∞ | near −π/2 | −90° |
| −1 | −π/4 | −45° |
| −0.0 | −0.0 | −0.0° |
| 0.0 | 0.0 | 0.0° |
| 1 | π/4 | 45° |
| +∞ | near +π/2 | +90° |

Example:

```java
System.out.println(Math.atan(1.0)); 
// 0.7853981633974483 on tested JDK

System.out.println(Math.atan(Double.POSITIVE_INFINITY));
// 1.5707963267948966 on tested JDK
```

`Math.atan(Double.NaN)` returns NaN. `Math.atan(-0.0)` preserves negative zero.

### 6.1. Losing Quadrant Information When Inverting Tangent

Because `tan(theta + π) = tan(theta)`, `atan` cannot recover which quadrant theta belongs to. Moreover, when using the ratio `y/x`, you lose the individual signs of `x`/`y`, especially if `x=0`.

For example, both vectors `(1,1)` and `(−1,−1)` have ratio `y/x = 1`, so:

```java
Math.atan(1.0 / 1.0);      // near +45°
Math.atan(-1.0 / -1.0);    // near +45° (not -135°)
```

Yet the direction angle from the +x axis of vector `(−1,−1)` is `−135°` by `atan2` convention. That is why you do not rely solely on `atan(y/x)` for general vector angles.

## 7. Math.atan2(y, x): Knowing the Quadrant from Both Coordinates

The method:

```java
double theta = Math.atan2(y, x);
```

takes **the y coordinate first, and the x coordinate second**. This is a fixed convention in Java (also appearing in many math libraries), easily reversed because we are used to writing points as `(x,y)`.

For a vector `(x,y)` away from the origin, the principal angle generally lies in `[−π,+π]`:

```text
                          y+
                           ^
                 QII       |       QI
                  +135°    |    +45°
                           |
          x− --------------+--------------> x+
                           |
                  −135°    |    −45°
                 QIII      |       QIV
                           v
                          y−
```

Four quadrant examples, printed in degrees to one decimal place:

| Coordinates (x,y) | Correct Call | Angle |
| --- | --- | ---: |
| (1,1) | `atan2(1,1)` | +45° |
| (−1,1) | `atan2(1,−1)` | +135° |
| (−1,−1) | `atan2(−1,−1)` | −135° |
| (1,−1) | `atan2(−1,1)` | −45° |

`Math.atan2` handles the quadrant even when `x` is negative. Using only `Math.atan(y/x)` collapses angles into ±90° and lacks the information to distinguish QI from QIII, or QII from QIV.

### 7.1. Do Not Replace atan2 with atan(y/x) When x = 0

`x = 0` causes the expression `y/x` to produce ±Infinity or NaN under IEEE 754 (or throw `ArithmeticException` if the division is integer). With `atan2`, both coordinates are passed directly and follow specific rules:

```java
System.out.println(Math.atan2(1.0, 0.0));
// 1.5707963267948966 ~ +90°

System.out.println(Math.atan2(-1.0, 0.0));
// -1.5707963267948966 ~ -90°
```

When `x` and `y` are extremely large or small, dividing `y/x` separately can also overflow/underflow and lose ratio information; `atan2` is the standard API for handling coordinate pairs without needing an intermediate ratio.

### 7.2. Interpreting Angles Geometrically

In a standard mathematical coordinate system, `+x` points right and `+y` points up; positive angles rotate **counter-clockwise**. However, in many screen coordinate systems, `y` increases **downward**. Then a pixel vector `(dx,dy)` passed into `atan2(dy,dx)` has positive angles pointing downward, which users often perceive as rotating clockwise.

**Identify the axis system before interpreting angle sign.** If you want to convert screen coordinates with y-downward to mathematical coordinates with y-upward, one approach when no other axis transforms exist is `Math.atan2(-dy, dx)`.

### 7.3. Principal Angle Limits and Angle Normalization

`atan2` returns a principal angle `[−π,+π]`, rather than automatically returning values in `[0,2π)`. If you need an angle from 0° up to less than 360°, the usual rule is adding `2π` for negative values:

```java
double angle = Math.atan2(y, x);
if (angle < 0.0) {
    angle += 2.0 * Math.PI;
}
```

This is a **code snippet** for ordinary finite angles. If `angle` equals `-0.0`, the condition `angle < 0.0` is false; if business rules require normalizing the sign bit of zero, add the rule `angle == 0.0 ? 0.0 : angle`. If `angle` is `NaN`, the comparison `angle < 0.0` is false and NaN remains, requiring separate input validation.

Due to rounding at the ±π/2π boundary, additional normalization near `2π` may be needed if the output **must strictly be less than 2π**. Do not use an unguarded `2π`-subtraction loop with NaN/Infinity; clearly define the data domain and normalization conditions.

## 8. Decision Table: Which Function Fits?

| Need | Approach |
| --- | --- |
| Know `sin(theta)` and need a principal angle | `asin(s)`, validate `s ∈ [−1,1]` |
| Know `cos(theta)` and need an angle from 0 to π | `acos(c)`, validate `c ∈ [−1,1]` |
| Know only `tan(theta)` and only need a principal angle | `atan(t)` |
| Know point/vector `(x,y)` and need direction/quadrant | **`atan2(y,x)`** |
| Need the result in degrees | `Math.toDegrees(angleRadians)` |
| Need to pass degree input to sin/cos/tan | `Math.toRadians(degrees)` first |
| Need computations with bit-reproducible trig library requirements | Check `StrictMath` and specific JDK contracts |

Distinguish **getting the angle from coordinates** from **getting the vector length**. If you need the radius `r = √(x²+y²)`, the appropriate API is `Math.hypot(x,y)`; get the angle using `atan2(y,x)`. `atan2` itself returns only the angle, not the vector magnitude.

## 9. Complete Java Program A — Four Basic Functions

Create file **`InverseTrigBasics.java`**:

```java
import java.util.Locale;

public class InverseTrigBasics {
    public static void main(String[] args) {
        System.out.printf(Locale.US, "asin(0.5) = %.1f deg%n",
                Math.toDegrees(Math.asin(0.5)));
        System.out.printf(Locale.US, "acos(0.5) = %.1f deg%n",
                Math.toDegrees(Math.acos(0.5)));
        System.out.printf(Locale.US, "atan(1)   = %.1f deg%n",
                Math.toDegrees(Math.atan(1.0)));
        System.out.printf(Locale.US, "atan2(1,1) = %.1f deg%n",
                Math.toDegrees(Math.atan2(1.0, 1.0)));

        System.out.println(Double.isNaN(Math.asin(1.01)));
        System.out.println(Double.isNaN(Math.acos(-1.01)));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 InverseTrigBasics.java
java InverseTrigBasics
```

**Stdout** (US formatter with one fractional digit):

```text
asin(0.5) = 30.0 deg
acos(0.5) = 60.0 deg
atan(1)   = 45.0 deg
atan2(1,1) = 45.0 deg
true
true
```

Explanation: the argument `0.5` is valid for `asin` and `acos`; `atan(1)` yields π/4; `atan2(1,1)` is a 45° vector. The arguments `1.01` and `−1.01` exceed the domain of `asin`/`acos`, returning NaN, checked with `Double.isNaN`.

Do not assert that the internal value is always **30.0 radians** just because the formatter prints `30.0 deg`: the result was **converted from radians to degrees** and displayed with one decimal digit.

## 10. Complete Java Program B — Four Quadrants

Create **`Atan2Quadrants.java`**:

```java
import java.util.Locale;

public class Atan2Quadrants {
    private static void show(double x, double y) {
        double angleDegrees = Math.toDegrees(Math.atan2(y, x));
        System.out.printf(Locale.US,
                "(x=%4.1f, y=%4.1f) -> %6.1f deg%n",
                x, y, angleDegrees);
    }

    public static void main(String[] args) {
        show( 1.0,  1.0);
        show(-1.0,  1.0);
        show(-1.0, -1.0);
        show( 1.0, -1.0);
    }
}
```

Run:

```bash
javac --release 17 Atan2Quadrants.java
java Atan2Quadrants
```

**Stdout:**

```text
(x= 1.0, y= 1.0) ->   45.0 deg
(x=-1.0, y= 1.0) ->  135.0 deg
(x=-1.0, y=-1.0) -> -135.0 deg
(x= 1.0, y=-1.0) ->  -45.0 deg
```

Note the signature `show(x,y)` uses the familiar coordinate order, but internally calls `Math.atan2(y,x)`. This is clear naming to avoid passing parameters in the wrong order.

### 10.1. Why Does atan(y/x) Return the Wrong Quadrant for QIII?

With `x=-1`, `y=-1`:

```java
double byRatio = Math.toDegrees(Math.atan(y / x));
// around +45°, loses the quadrant

double byVector = Math.toDegrees(Math.atan2(y, x));
// around -135°, true vector direction
```

This is a **code snippet** requiring `x` and `y` to be declared before compiling. In real applications, prefer `atan2` when coordinates are available; do not try to patch it by manually adding π in `if` branches when the standard API handles it.

## 11. Signed Zero: Two Zero Patterns Can Lead to Two Different Angles

IEEE 754 has `+0.0` and `-0.0`. They are equal under primitive `==`, but have different sign bits. `asin` and `atan` preserve the zero sign of their argument; `atan2` uses the sign of zero to pick the side of the angle boundary.

Rule table for `atan2(y,x)` on coordinate axes:

| y | x | `Math.atan2(y,x)` |
| --- | --- | --- |
| `+0.0` | `+1.0` | `+0.0` |
| `-0.0` | `+1.0` | `-0.0` |
| `+0.0` | `-1.0` | nearest `+π` |
| `-0.0` | `-1.0` | nearest `-π` |
| `+1.0` | `+0.0` | nearest `+π/2` |
| `-1.0` | `+0.0` | nearest `-π/2` |

**Very important:** `Math.atan2(+0.0, -1.0)` and `Math.atan2(-0.0, -1.0)` return two angles of opposite signs, approximately +π and −π. They are the two sides of the **branch cut** along the negative x-axis.

### 11.1. atan2(0,0) Is Not Automatically NaN

Mathematically, the direction of the zero vector at the origin is undefined as a geometric angle. However, Java's `Math.atan2` still has **deterministic floating-point rules** for ±0 in both coordinates:

```java
System.out.println(Math.atan2(+0.0, +0.0)); // 0.0
System.out.println(Math.atan2(-0.0, +0.0)); // -0.0
System.out.println(Math.atan2(+0.0, -0.0)); // near +pi
System.out.println(Math.atan2(-0.0, -0.0)); // near -pi
```

**Do not equate "the API returns a value" with "the vector has a valid geometric direction".** If the application rejects the zero vector, validate upfront:

```java
if (x == 0.0 && y == 0.0) {
    throw new IllegalArgumentException("Zero vector has no direction");
}
double angle = Math.atan2(y, x);
```

This is an **illustrative code snippet**; place inside a method with `x`, `y` declared. The `== 0.0` condition matches both positive and negative zero. If inputs may contain NaN or Infinity, define an additional finiteness policy.

## 12. Infinity and NaN: Behavior of Each Method

`Math`/`StrictMath` handle special values according to Java's contract and do not need to be wrapped in `try/catch` for `ArithmeticException` in normal real-domain cases.

| Case | Result |
| --- | --- |
| `Math.asin(1.1)` | NaN (out of domain) |
| `Math.acos(-1.1)` | NaN (out of domain) |
| `Math.asin(Double.NaN)` | NaN |
| `Math.acos(Double.POSITIVE_INFINITY)` | NaN |
| `Math.atan(Double.NaN)` | NaN |
| `Math.atan(Double.POSITIVE_INFINITY)` | near +π/2 |
| `Math.atan(Double.NEGATIVE_INFINITY)` | near −π/2 |
| `Math.atan2(Double.NaN, 1.0)` | NaN |
| `Math.atan2(1.0, Double.NaN)` | NaN |
| `Math.atan2(1.0, +0.0)` | near +π/2 |
| `Math.atan2(-1.0, +0.0)` | near −π/2 |

When both coordinates are infinite, `atan2` has additional special rules that cannot be deduced simply from an infinity/infinity ratio (which is NaN):

| y | x | Angle |
| --- | --- | --- |
| +∞ | +∞ | +π/4 |
| +∞ | −∞ | +3π/4 |
| −∞ | +∞ | −π/4 |
| −∞ | −∞ | −3π/4 |

This is another example showing **`atan2(y,x)` is not merely a call to `atan(y/x)`**.

### 12.1. Why Not Compare NaN with ==?

`NaN == NaN` returns false under primitive floating-point equality, even when both unbox to `Double.NaN`. To detect invalid values:

```java
double result = Math.acos(1.1);

if (Double.isNaN(result)) {
    System.out.println("outside domain");
}
```

To also constrain infinities, use `Double.isFinite(result)` in Java 17. When receiving user input, report the appropriate cause: `acos(1.1)` is out of domain, whereas `atan2(Double.NaN,1)` has a coordinate that is not a valid number.

### 12.2. Zero Sign Can Be Lost in Other Steps

If you compute the ratio `y/x` before `atan2`, division or other operations may round, overflow, underflow, or alter the sign of zero. Thus, passing coordinates directly to `atan2` preserves more essential sign/angle information than computing `atan(y/x)` manually.

## 13. Complete Java Program C — Special Cases

Save **`InverseTrigEdges.java`**:

```java
public class InverseTrigEdges {
    public static void main(String[] args) {
        System.out.println(Double.isNaN(Math.asin(1.01)));
        System.out.println(Double.isNaN(Math.acos(-1.01)));

        System.out.println(Math.asin(-0.0));
        System.out.println(Math.atan(-0.0));
        System.out.println(Math.acos(1.0));

        System.out.println(Math.atan2(+0.0, -1.0));
        System.out.println(Math.atan2(-0.0, -1.0));
        System.out.println(Math.atan2(+0.0, +1.0));
        System.out.println(Math.atan2(-0.0, +1.0));

        System.out.println(Math.atan2(1.0, +0.0));
        System.out.println(Math.atan2(-1.0, +0.0));

        System.out.println(Math.atan2(+0.0, +0.0));
        System.out.println(Double.isNaN(
                Math.atan2(Double.NaN, 1.0)));
    }
}
```

Run:

```bash
javac --release 17 InverseTrigEdges.java
java InverseTrigEdges
```

**Stdout on tested JDK:**

```text
true
true
-0.0
-0.0
0.0
3.141592653589793
-3.141592653589793
0.0
-0.0
1.5707963267948966
-1.5707963267948966
0.0
true
```

Special milestones like ±0, ±π, ±π/2, and NaN are stated in the API contract. When using `Math` across different JDKs/platforms, **do not treat every decimal digit of non-special angles as a bit-for-bit guarantee**. `StrictMath` is more tightly specified for certain functions to increase result reproducibility across implementations.

## 14. Math vs. StrictMath: Overlapping Functionality, Different Reproducibility Guarantees

Java provides both:

```java
double a = Math.asin(0.5);
double b = StrictMath.asin(0.5);

double c = Math.acos(0.5);
double d = StrictMath.acos(0.5);

double e = Math.atan(1.0);
double f = StrictMath.atan(1.0);

double g = Math.atan2(1.0, -1.0);
double h = StrictMath.atan2(1.0, -1.0);
```

Both classes use **radians**, share the same mathematical meaning, and have the same return type `double`. The difference is not that `Math` is "wrong", but the **algorithmic result guarantee policy**.

### 14.1. Math: Sufficient Accuracy per Specification, Implementation Flexibility

Java SE 17 `Math.asin`/`acos`/`atan` specify accuracy within **1 ulp** of the exact mathematical result, with a **semi-monotonic** requirement. `Math.atan2` allows error within **2 ulp** and has a semi-monotonic requirement per the API contract.

`ulp` stands for "unit in the last place", roughly the spacing between representable floating-point values around a number. An error within 1–2 ulp is a meaningful constraint for binary64, **not** "a fixed error smaller than 0.000001 radians for all values" or "always correctly rounded".

Implementations of `Math` are permitted to use platform-specific algorithms or optimized instructions, as long as they satisfy the accuracy contract and special cases.

### 14.2. StrictMath: Aimed at Higher Reproducibility

According to Java SE 17 documentation, several `StrictMath` functions (including the trigonometric functions studied here) are bound to the **fdlibm 5.3** (Freely Distributable Math Library) algorithms described in the API, supporting **bit-for-bit consistent** results across compliant Java implementations.

That does not mean:

- `StrictMath` results represent mathematical real numbers with **infinite precision**.
- Every `StrictMath` function uses the exact same fdlibm mechanism or same rounding policy in every case.
- `Math.asin(x)` **must always differ** from `StrictMath.asin(x)`: on many JDKs they may yield the exact same bits.
- Using `StrictMath` makes `==` comparisons of calculated results unconditionally stable across all other arithmetic (`+`, `-`, `*`, `/`): intermediate operations still undergo rounding.

**Guidance for choosing:** for ordinary applications needing math functions with JDK-guaranteed accuracy, `Math` is the straightforward choice. When a system requires trigonometric results that match **bit-for-bit across implementations** for the same inputs (regression testing, regulated deterministic simulations), consider `StrictMath` and the target version's documentation.

### 14.3. strictfp Does Not Replace StrictMath

In Java 17, floating-point expression semantics are always evaluated strictly per the JLS, and the `strictfp` modifier has become unnecessary for forcing strict evaluation of primitive operations. However, that **does not turn** `Math` into `StrictMath`'s fdlibm functions. The question of **library algorithms computing asin/acos/atan/atan2** is distinct from **precision of primitive operations**.

## 15. Complete Java Program D — Same API in Math and StrictMath

Create file **`MathVersusStrictMath.java`**:

```java
import java.util.Locale;

public class MathVersusStrictMath {
    static void show(String name, double math, double strict) {
        System.out.printf(Locale.US,
                "%s -> Math: %.6f, StrictMath: %.6f%n",
                name, math, strict);
    }

    public static void main(String[] args) {
        show("asin", Math.asin(0.5), StrictMath.asin(0.5));
        show("acos", Math.acos(0.5), StrictMath.acos(0.5));
        show("atan", Math.atan(1.0), StrictMath.atan(1.0));
        show("atan2", Math.atan2(1.0, -1.0),
                StrictMath.atan2(1.0, -1.0));
    }
}
```

Run:

```bash
javac --release 17 MathVersusStrictMath.java
java MathVersusStrictMath
```

**Stdout (formatted to 6 decimal places):**

```text
asin -> Math: 0.523599, StrictMath: 0.523599
acos -> Math: 1.047198, StrictMath: 1.047198
atan -> Math: 0.785398, StrictMath: 0.785398
atan2 -> Math: 2.356194, StrictMath: 2.356194
```

**How to interpret:** showing identical decimal digits after formatting **does not prove** the two results are identical in every bit or for all inputs. To evaluate true reproducibility, compare raw bits via `Double.doubleToRawLongBits` over a representative input set and multiple supported JDKs/architectures. Do not write a test forcing `Math` and `StrictMath` to always be bit-equal when the contract does not require it.

## 16. Application: Direction of Motion, Coordinates, and Vectors

Suppose an object moves from `(x1,y1)` to `(x2,y2)` on a Cartesian coordinate system. The displacement vector is:

```text
dx = x2 - x1
dy = y2 - y1
theta = atan2(dy, dx)
```

Example of motion from `(1,2)` to `(−2,5)`:

```java
double x1 = 1.0;
double y1 = 2.0;
double x2 = -2.0;
double y2 = 5.0;

double dx = x2 - x1; // -3
double dy = y2 - y1; // +3

double heading = Math.atan2(dy, dx); // QII
System.out.printf(java.util.Locale.US,
        "%.1f degrees%n", Math.toDegrees(heading));
// 135.0 degrees
```

This snippet **illustrates a method** (or a block inside `main`), not a standalone Java file. The angle +135° is right because dx is negative and dy is positive.

### 16.1. Vector Length ≠ Angle

`Math.hypot(dx,dy)` gives the vector magnitude. It avoids certain intermediate overflow/underflow risks compared to manually computing `Math.sqrt(dx*dx + dy*dy)`.

```java
double length = Math.hypot(dx, dy);
double angle = Math.atan2(dy, dx);
```

The two results are **length** and **angle**, respectively. If the vector is zero, length is 0 but direction is typically undefined in geometry problems, even though Java's `atan2` still returns a value based on signed-zero inputs.

### 16.2. Normalizing If the Domain Wants [0,360)

`Math.toDegrees(Math.atan2(dy,dx))` returns approximately `[−180,180]`. If you want a heading from 0 to less than 360 degrees:

```java
double angleDeg = Math.toDegrees(Math.atan2(dy, dx));
if (angleDeg < 0.0) {
    angleDeg += 360.0;
}
```

This works for finite inputs in ordinary scenarios. For signed zero and the −180/+180 boundary points, exact conventions should be documented and tested. If the screen coordinate system uses y increasing downward, angle direction must also be adjusted before displaying.

## 17. Common Mistakes When Using Inverse Trig

| Mistake | What Happens | Right Way |
| --- | --- | --- |
| Assuming `asin(0.5)` returns `30` | Result is in **radians** | Use `toDegrees` when degrees are needed |
| Calling `asin(30)` meaning 30° | 30 is outside [−1,1] → NaN | Distinguish sine value from angle |
| Using `acos(1.0001)` expecting 0 | Argument exceeds domain → NaN | Validate input; clamp only per error policy |
| Using `atan(y/x)` to find the quadrant | Loses individual signs of x,y | Use `atan2(y,x)` |
| Calling `atan2(x,y)` | Swapped parameters by mistake | Method is **atan2(y,x)** |
| Treating `atan2(0,0)` as a valid vector direction | API returns a number per signed zero, but geometrically direction is not unique | Check for zero vector if needed |
| Ignoring negative zero | Can flip ±π at the branch cut | Preserve signed zero or normalize intentionally |
| Comparing NaN using `== Double.NaN` | Always false | `Double.isNaN` |
| Assigning `Math.atan(1.0)` directly to `float` | Return type is `double`, requires cast and can lose precision | Use `double` unless specifically required otherwise |
| Assuming `asin(sin(t))==t` is always true | Sine is periodic, asin only returns principal value | Check domain and uniqueness conditions |
| Claiming "Math is always faster than StrictMath" | Performance depends on JDK/hardware | Benchmark in real environment |
| Treating `StrictMath` as infinitely accurate | Still `double` with rounding | Understand fdlibm and precision |
| Comparing angle results with `==` against displayed decimals | Representation/rounding error | Pick tolerance based on units and problem accuracy |

A subtle trap is **re-inverting sine and cosine computed from an angle**: `Math.atan2(Math.sin(theta), Math.cos(theta))` returns a **normalized principal version of theta**, not necessarily the original theta if theta was outside `[−π,π]`. Floating-point errors can also appear near boundaries and at multiples of π.

## 18. Designing Proper Tests for Floating-Point Math

**Do not test every value with a context-free fixed epsilon.** If the application allows an angular error of 0.01 degrees, convert the values under test to degrees or convert the tolerance to radians, and also define how comparisons work at the ±180° boundary.

Tests should cover:

1. Standard values: `asin(0.5)` ≈ 30°, `acos(0.5)` ≈ 60°, `atan(1)` ≈ 45°.
2. Both domain boundaries: `asin(−1)`, `asin(1)`, `acos(−1)`, `acos(1)`.
3. Out of domain: `asin(1.01)`, `acos(−1.01)` → NaN.
4. All four quadrants: `atan2(±1, ±1)`.
5. Coordinate axes: `atan2(±0.0, ±1.0)` and `atan2(±1.0, ±0.0)`.
6. Origin: define zero-vector handling policy.
7. Special values: ±Infinity, NaN.
8. Very large/very small coordinates: do not manually divide `y/x` or square uncontrollably.
9. ±π boundary: observe the branch cut and angle normalization conventions.
10. Comparing `Math` and `StrictMath` based on actual reproducibility requirements, not rounded strings.

### 18.1. Angular Distance Must Wrap Around the Circle When Needed

Two angles `179.9°` and `−179.9°` are **0.2° apart along the shortest arc**, not nearly 359.8° as ordinary decimal subtraction suggests. When comparing **directions on a circle**, define an angle-difference calculation normalized modulo 360°/2π.

A useful formula for the principal angular distance in radians is:

```java
static double angleDistance(double a, double b) {
    return Math.abs(Math.atan2(
            Math.sin(a - b), Math.cos(a - b)));
}
```

This is a **method snippet** that must be placed inside a class; it works well for ordinary finite angles, though `a-b` with huge numbers/Infinity can overflow or produce NaN, and the result is still subject to rounding. If the system handles very large or special angles, normalize angles carefully beforehand and validate `Double.isFinite`.

## 19. Self-Practice Exercises with Answers

### Exercise 1 — Reading Function Semantics Correctly

Approximately how many radians and how many degrees does `Math.asin(0.5)` return?

**Answer:** approximately `0.5235987756` radians, equivalent to `30°`. Use `Math.toDegrees` if a degree result is wanted.

### Exercise 2 — Angles of acos

How many degrees do `Math.acos(0.5)` and `Math.acos(-1.0)` correspond to?

**Answer:** `60°` and `180°`. `acos` returns the principal angle in `[0°,180°]`.

### Exercise 3 — Angle of atan

How many degrees does `Math.atan(1.0)` correspond to?

**Answer:** `45°`, i.e., approximately π/4 radians.

### Exercise 4 — Out-of-Domain Values

Do `Math.asin(2.0)` and `Math.acos(-2.0)` throw exceptions or return something else?

**Answer:** they return `NaN`; check using `Double.isNaN`. There is no real angle whose sine or cosine equals ±2.

### Exercise 5 — Four Quadrants

For coordinates `(x,y) = (−1,1)` and `(−1,−1)`, how do you call `atan2` and what are the resulting angles?

**Answer:** `Math.atan2(1,-1)` ≈ +135°; `Math.atan2(-1,-1)` ≈ −135°. `y` is the first parameter.

### Exercise 6 — Why Not Use atan(y/x)?

For vector `(−1,−1)`, `atan(y/x)` can return around `+45°`, whereas `atan2(y,x)` returns `−135°`. Why?

**Answer:** division loses the individual signs of the two coordinates: `(−1)/(−1) = +1`, the same ratio as vector `(1,1)`. `atan2` still sees negative x and negative y and picks QIII.

### Exercise 7 — Signed Zero on the Negative x-Axis

What angles are `atan2(+0.0,-1.0)` and `atan2(-0.0,-1.0)`?

**Answer:** near +π and −π. The sign of zero determines the side of the branch cut.

### Exercise 8 — Zero Vector

Does `Math.atan2(0.0,0.0)` return NaN? Should it be treated as a valid geometric direction?

**Answer:** in Java, it returns `+0.0` for two positive zeros. However, the vector (0,0) has no defined direction, so the application should check separately if a non-zero vector is required.

### Exercise 9 — Infinity

What angles do `Math.atan(Double.POSITIVE_INFINITY)` and `Math.atan(Double.NEGATIVE_INFINITY)` approach?

**Answer:** near +π/2 and −π/2; per Java's contract, it returns the double values closest to those two landmarks.

### Exercise 10 — Two Infinite Coordinates

What angle is `Math.atan2(Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY)` close to?

**Answer:** +3π/4 = 135°. `atan(y/x)` cannot substitute because `Infinity / -Infinity` is NaN.

### Exercise 11 — Math vs. StrictMath

Can we assert `Math.atan2(y,x) == StrictMath.atan2(y,x)` for **all** values? Why or why not?

**Answer:** no, we should not assert that. `Math` permits flexible implementations within accuracy limits; `StrictMath` has fdlibm algorithm constraints to support bit-level reproducibility for certain methods.

### Exercise 12 — Radians/Degrees

Write a Java expression to get the angle in degrees of vector `(x,y)`.

**Answer:** `Math.toDegrees(Math.atan2(y,x))`. If you want the angle in [0,360), add normalization as required and check signed zero/boundary constraints.

### Exercise 13 — Principal Angle

Why does `asin(sin(150°))` not give 150°?

**Answer:** `sin(150°)=sin(30°)`; meanwhile, `asin` only returns angles in [−90°,90°], so the principal result is near 30°; 150° must also be converted to radians before calling sin.

### Exercise 14 — Screen Coordinates

On a screen, y increases downward. When dragging the mouse right and down, does `atan2(dy,dx)` return a positive or negative angle? What should you do if you want positive angles counter-clockwise as in math?

**Answer:** if dx>0 and dy>0, `atan2(dy,dx)` returns a positive angle in quadrant I of the passed numeric coordinate system; on screen, it looks like down-right. To use a y-upward convention, use `atan2(-dy,dx)` if no other coordinate transform is applied.

### Exercise 15 — Accuracy Checking

If an application needs to compare angles near +180° and −180°, why can `Math.abs(a-b)` misjudge "closeness"?

**Answer:** angle intervals around a circle are periodic. The two directions ±179.9° only differ by 0.2° along the short arc; normalize the angular difference modulo 360° or 2π per the application's contract.

## 20. Checklist and References

- [ ] I remember that `asin` and `acos` accept arguments in [−1,1], while `atan` accepts real numbers outside that range.
- [ ] I know the principal result range of each function and the **radian** unit.
- [ ] I understand `asin(sin(theta))`, `acos(cos(theta))`, `atan(tan(theta))` do not always recover the original theta.
- [ ] I always write `atan2(y,x)` when given coordinates, **without swapping parameters**.
- [ ] I do not use `atan(y/x)` instead of `atan2` when distinguishing quadrants and handling x=0.
- [ ] I validate inputs to `asin`/`acos` rather than silently hiding bad data.
- [ ] I know `asin`/`atan` preserve signed zero; `atan2` has rules for ±0 on the axes.
- [ ] I know `atan2(0,0)` has an IEEE 754 output, but a zero vector may be considered invalid by business logic.
- [ ] I check `Double.isNaN`/`Double.isFinite` on inputs and outputs as appropriate.
- [ ] I distinguish the 1 ulp/2 ulp accuracy requirements of `Math` from the fdlibm constraints of `StrictMath`.
- [ ] I can write a dx/dy vector example and convert the result to degrees.
- [ ] I test all four quadrants, coordinate axes, ±π, signed zero, NaN, and infinity.
- [ ] I understand angular problems on a **circle** differ from comparing two real numbers on a straight line.
- [ ] I have run the Java 17+ programs and verified stdout.

**Official Java SE 17 Documentation:**

- [Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `asin`, `acos`, `atan`, `atan2`, `toDegrees`, `toRadians`, ulp specifications, and special cases.
- [StrictMath API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): corresponding functions, fdlibm rules, and reproducibility.
- [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `NaN`, ±Infinity, signed zero, `doubleToRawLongBits`.
- [JLS 17 `4.2.3 Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): Java floating-point numbers.
- [JLS 17 `15.4 Floating-Point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): precision, rounding, and expression semantics in Java 17.

**Conclusion:** `asin`, `acos`, and `atan` find a **principal angle** from a trigonometric value, while `atan2(y,x)` finds the **vector direction based on both coordinates**. In Java geometry code, prefer `atan2` when x/y are available, remember radians, account for signed zero/NaN, and choose `Math` or `StrictMath` based on actual accuracy and reproducibility requirements.