# sin, cos, tan, and Converting Degrees to Radians in Java

## 1. The Most Important Issue: Java Takes Radians

The trigonometric functions **Math.sin(double)**, **Math.cos(double)**, and **Math.tan(double)** in Java always interpret their argument as **radians**, not degrees. If input data from a UI or geometry problem uses degrees, convert units **before calling the function**.

~~~java
double angleDegrees = 30.0;
double angleRadians = Math.toRadians(angleDegrees);
double value = Math.sin(angleRadians); // approximately 0.5
~~~

Conversely, **Math.sin(30.0)** computes the sine of **30 radians**: that is not sin(30°) as students commonly encounter in school.

This lesson clarifies angle units, trigonometric formulas, using Math and StrictMath, floating-point errors, handling angles near 90°, a runnable Java 17+ program, and common programming mistakes.

## 2. Degrees, Radians, and Conversion Formulas

- **Degrees**: a full circle is **360°**.
- **Radians**: angle size equals the ratio **arc length / radius**. A full circle is **2π rad**.
- **180° = π rad**; **90° = π/2 rad**.

Formulas:

\[
\text{radians}=\text{degrees}\times\frac{\pi}{180}
\]

\[
\text{degrees}=\text{radians}\times\frac{180}{\pi}
\]

Conversion table:

| Degrees | Radians (exact math) | Approximate |
| ---: | --- | ---: |
| 0° | 0 | 0 |
| 30° | π/6 | 0.523599 |
| 45° | π/4 | 0.785398 |
| 60° | π/3 | 1.047198 |
| 90° | π/2 | 1.570796 |
| 180° | π | 3.141593 |
| 270° | 3π/2 | 4.712389 |
| 360° | 2π | 6.283185 |

The constant **Math.PI** holds a **`double` value approximating π**, because π has infinite non-repeating digits. Consequently, unit conversion in Java may require rounding.

### Math.toRadians and Math.toDegrees

~~~java
double radians = Math.toRadians(180.0); // approximately π
double degrees = Math.toDegrees(Math.PI); // approximately 180
~~~

**Math.toRadians(double)** converts degrees → radians; **Math.toDegrees(double)** converts radians → degrees. Both take and return **double**, without enforcing that degrees must lie in the 0–360 range.

~~~java
double negative = Math.toRadians(-45.0); // approximately -π/4
double repeated = Math.toRadians(720.0); // approximately 4π
~~~

The value **−45°** can represent rotation in the opposite direction compared to +45°. **720°** is two full turns and can still be passed to sin/cos/tan. However, due to representation error, periodic results may not be **bit-for-bit** equal.

Nor should you assume converting to radians and back to degrees always returns the exact original double under the **==** operator. When verification is needed, compare within an error threshold suitable for the data and application.

## 3. Sin, Cos, Tan on the Unit Circle

In standard mathematical coordinates, angle θ is measured from the positive x-axis, counter-clockwise as the positive direction. A point on the unit circle has:

\[
x=\cos(\theta),\qquad y=\sin(\theta)
\]

**Cos** gives the horizontal component; **sin** gives the vertical component. When **cos(θ) is mathematically non-zero**:

\[
\tan(\theta)=\frac{\sin(\theta)}{\cos(\theta)}
\]

Properties:

- For finite real arguments, sin and cos lie in **[−1, 1]**.
- Tan can grow arbitrarily large in magnitude as it approaches an asymptote; there is no fixed absolute bound.
- **sin(−θ)=−sin(θ)**, **tan(−θ)=−tan(θ)**: odd functions.
- **cos(−θ)=cos(θ)**: even function.
- Sin and cos have period **2π**; tan has period **π** mathematically.

These identities hold exactly in mathematics; Java floating-point numbers may only approximate them due to rounding.

### Special Angles

| Angle (deg) | sin | cos | tan |
| ---: | --- | --- | --- |
| 0° | 0 | 1 | 0 |
| 30° | 1/2 | √3/2 | √3/3 |
| 45° | √2/2 | √2/2 | 1 |
| 60° | √3/2 | 1/2 | √3 |
| 90° | 1 | 0 | **Undefined** |
| 180° | 0 | −1 | 0 |
| 270° | −1 | 0 | **Undefined** |
| 360° | 0 | 1 | 0 |

At **90°** and **270°**, tan is **mathematically undefined**. Do not write that tan at these two angles equals Infinity: Java has no exact representation of π/2 in double, and tan may return a very large finite value when evaluated near the asymptote.

## 4. Math.sin: Computing the y-Component and Height

~~~java
double sine = Math.sin(Math.toRadians(30.0)); // approximately 0.5
~~~

Sin is positive in quadrants I and II, negative in quadrants III and IV. At 0° and 180°, sin is 0 mathematically; however, **Math.sin(Math.PI)** is not guaranteed to be exact 0.0, because Math.PI only approximates π.

Example of a vector of magnitude 10 at angle 30° with the x-axis:

~~~java
double length = 10.0;
double radians = Math.toRadians(30.0);
double y = length * Math.sin(radians); // approximately 5.0
~~~

The input to sin must be radians; real-world coordinate systems may have a y-axis direction different from mathematical convention, so check before applying to UI or graphics.

## 5. Math.cos: Computing the x-Component

~~~java
double cosine = Math.cos(Math.toRadians(60.0)); // approximately 0.5
~~~

Cos is positive in quadrants I and IV, negative in quadrants II and III. At 90° and 270°, cos is 0 mathematically. However:

~~~java
double rightAngle = Math.toRadians(90.0);
boolean exactlyZero = Math.cos(rightAngle) == 0.0; // false on typical JDKs
~~~

The value of Math.cos(rightAngle) is typically near **6.123 × 10^−17**; this is not a geometry bug. It is a tiny error due to unit conversion and double arithmetic.

Example of the x-component of a vector of length 10 at 60°:

~~~java
double x = 10.0 * Math.cos(Math.toRadians(60.0));
// x is approximately 5.0
~~~

## 6. Math.tan: Computing Slope and Avoiding Poles

~~~java
double tangent = Math.tan(Math.toRadians(45.0)); // approximately 1.0
~~~

Mathematically, tan=sin/cos when cos is non-zero. Tan is often used to derive the ratio of two sides or the slope at a non-vertical angle.

**Why does tan(90°) not necessarily become Infinity in Java?**

~~~java
double nearHalfPi = Math.toRadians(90.0);
double c = Math.cos(nearHalfPi);
double t = Math.tan(nearHalfPi);
System.out.println(c == 0.0);        // false
System.out.println(Double.isFinite(t)); // true
~~~

Math.toRadians(90.0) is a double **close to π/2**. Because cos is not exactly 0, Math.tan returns a very large finite value at this approximate angle. Even though the machine returns a number, **the slope at a vertical angle is undefined** in the mathematical model.

For an application that cannot accept angles too close to tan's asymptote, you can define a validation policy:

~~~java
double radians = Math.toRadians(inputDegrees);
if (Math.abs(Math.cos(radians)) < 1.0e-12) {
    throw new IllegalArgumentException("Angle too close to a tan pole");
}
double slope = Math.tan(radians);
~~~

The snippet above sits inside a method with a declared **inputDegrees** variable. **1e−12 is not the right threshold for every problem**: this is just an example of input domain requirements; choose the criterion based on sensitivity and allowable error. Checking cosine non-zero with the **!=** operator can still accept unrealistically huge slopes.

**Math.tan(x)** may not match **Math.sin(x)/Math.cos(x)** bit-for-bit, because the algorithms and rounding steps differ. When you need tan, call Math.tan directly; if you need vector components, compute sin/cos along each axis.

## 7. Trigonometry in Applications: Vectors and Coordinates

A vector of length **r** and angle **θ** counter-clockwise from the positive x-axis has:

\[
x=r\cos(\theta),\qquad y=r\sin(\theta)
\]

With **r=10, θ=30°**:

~~~java
double magnitude = 10.0;
double angleDegrees = 30.0;
double angleRadians = Math.toRadians(angleDegrees);
double x = magnitude * Math.cos(angleRadians); // approximately 8.660254
double y = magnitude * Math.sin(angleRadians); // approximately 5.0
~~~

These formulas appear in graphics, robotics, simulations, physics, forces, velocities, and geometry. However, computer screens typically have **y increasing downward**, differing from the mathematical coordinate system. A graphics program may need to negate the y-component or change the angle measurement convention. Do not apply mechanically without identifying the coordinate system.

Important principle when designing APIs: name variables **angleDegrees** or **angleRadians**; when interacting across multiple libraries, document axis rules, positive direction, and angle units at the boundary.


## 8. How Do Math and StrictMath Differ?

Java has **java.lang.Math** and **java.lang.StrictMath**, both providing **sin**, **cos**, **tan**, **toRadians**, and **toDegrees**.

- **Math** can be optimized by the JVM using different implementations, as long as it meets API specification guarantees. For some operations, result bits may differ slightly between platforms.
- **StrictMath** is designed for reproducible behavior of core math functions per specified algorithms, suitable when result consistency across Java implementations is required.
- **Both take angles in radians** for sin/cos/tan.
- StrictMath **does not make π an exact representable number** and does not guarantee all trigonometric identities hold bit-for-bit.

Example:

~~~java
double rad = Math.toRadians(30.0);
double fast = Math.sin(rad);
double reproducible = StrictMath.sin(rad);
// Both are approximately 0.5; do not assume they always share the same bit pattern.
~~~

Java 17 documentation for **Math.sin/cos/tan** specifies accuracy within **1 ulp** of the exact mathematical result and **semi-monotonicity**. This does not mean Math.cos(π/2) must be exact 0, because the π/2 passed in is already approximated.

In most Java Core applications, **Math** is appropriate. Choose **StrictMath** when product requirements have specific constraints on bit-level reproducibility of specified functions.

## 9. Floating-Point Error and Approximate Comparison

Double has finite precision. Expressions with clean mathematical results like 0, 0.5, or 1 do not always produce those exact bit patterns due to unit conversion, approximations, or argument reduction.

Example:

~~~java
boolean equal = Math.sin(Math.toRadians(180.0)) == 0.0;
// false on typical JDKs, even though sin(180°)=0 mathematically
~~~

When testing over a bounded value range, an **absolute error** comparison helper is useful:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    return Double.isFinite(a) && Double.isFinite(b)
            && tolerance >= 0.0
            && Math.abs(a - b) <= tolerance;
}
~~~

This is a method placed inside a class. Example:

~~~java
boolean valid = nearlyEqual(
        Math.sin(Math.toRadians(30.0)), 0.5, 1.0e-12);
~~~

**1e−12 is only an illustrative choice** for simple trigonometric calculations in a domain near [−1, 1]. Do not blindly reuse this threshold for every system. For quantities with units, define business limits; for data of varying magnitudes, relative error or ULP may be appropriate depending on the contract.

Rounding every small result to 0 can hide important numerical information. If an application wants to flag special angles like 90° or 180°, define angle-handling rules and approximation thresholds at the business level, rather than hardcoding them into Math.

## 10. Standalone Compilable and Runnable Java 17+ Program

Save the program as **TrigAngleDemo.java**:

~~~java
import java.util.Locale;

public class TrigAngleDemo {
    static boolean nearlyEqual(double a, double b, double tolerance) {
        return Double.isFinite(a) && Double.isFinite(b)
                && tolerance >= 0.0
                && Math.abs(a - b) <= tolerance;
    }

    static void show(double degrees) {
        double radians = Math.toRadians(degrees);
        System.out.printf(Locale.US,
                "%5.0f deg -> rad=%8.5f, sin=% .6f, cos=% .6f, tan=% .6f%n",
                degrees, radians, Math.sin(radians),
                Math.cos(radians), Math.tan(radians));
    }

    public static void main(String[] args) {
        show(0.0);
        show(30.0);
        show(45.0);
        show(60.0);
        show(-45.0);

        double rightAngle = Math.toRadians(90.0);
        double halfTurn = Math.toRadians(180.0);

        System.out.println("cos(90) == 0: "
                + (Math.cos(rightAngle) == 0.0));
        System.out.printf(Locale.US, "cos(90) approx: %.3e%n",
                Math.cos(rightAngle));
        System.out.println("tan(90) is finite: "
                + Double.isFinite(Math.tan(rightAngle)));
        System.out.println("sin(180) == 0: "
                + (Math.sin(halfTurn) == 0.0));

        System.out.println("sin(30) near 0.5: "
                + nearlyEqual(Math.sin(Math.toRadians(30.0)),
                        0.5, 1.0e-12));
        System.out.println("StrictMath.sin(30) near 0.5: "
                + nearlyEqual(
                        StrictMath.sin(StrictMath.toRadians(30.0)),
                        0.5, 1.0e-12));

        System.out.printf(Locale.US, "roundtrip: %.10f deg%n",
                Math.toDegrees(Math.toRadians(123.0)));
        System.out.println("sin(infinity) is NaN: "
                + Double.isNaN(Math.sin(Double.POSITIVE_INFINITY)));
        System.out.println("sin(-0.0) keeps negative zero: "
                + (Double.doubleToRawLongBits(Math.sin(-0.0))
                        == Double.doubleToRawLongBits(-0.0)));
    }
}
~~~

Commands to use with JDK 17+:

~~~bash
javac --release 17 TrigAngleDemo.java
java TrigAngleDemo
~~~

Stdout on a verified JDK (preserve leading spaces from printf):

~~~text
    0 deg -> rad= 0.00000, sin= 0.000000, cos= 1.000000, tan= 0.000000
   30 deg -> rad= 0.52360, sin= 0.500000, cos= 0.866025, tan= 0.577350
   45 deg -> rad= 0.78540, sin= 0.707107, cos= 0.707107, tan= 1.000000
   60 deg -> rad= 1.04720, sin= 0.866025, cos= 0.500000, tan= 1.732051
  -45 deg -> rad=-0.78540, sin=-0.707107, cos= 0.707107, tan=-1.000000
cos(90) == 0: false
cos(90) approx: 6.123e-17
tan(90) is finite: true
sin(180) == 0: false
sin(30) near 0.5: true
StrictMath.sin(30) near 0.5: true
roundtrip: 123.0000000000 deg
sin(infinity) is NaN: true
sin(-0.0) keeps negative zero: true
~~~

### Output Line Explanations

- **0°, 30°, 45°, 60°, −45°** are passed through Math.toRadians before computing. Six-decimal-place numbers are only formatted strings, not the full precision of the double results.
- **sin(30°) ≈ 0.5**, **cos(60°) ≈ 0.5**, tan(45°) approximates 1 per mathematical formulas.
- **cos(90) == 0** and **sin(180) == 0** are false because both the radian input and the results are approximated in type double.
- **tan(90) is finite** being true does not mean tan at a right angle is mathematically defined.
- **roundtrip: 123.0000000000 deg** is rounded to 10 displayed decimal places; it is not a guarantee that every double angle round-trips exactly.
- **sin(infinity) is NaN** and the sign bit of **sin(−0.0)** illustrate special floating-point cases.

## 11. NaN, Infinity, and Signed Zero

Java's sin/cos/tan functions have special behaviors:

| double argument | sin | cos | tan |
| --- | --- | --- | --- |
| NaN | NaN | NaN | NaN |
| +Infinity or −Infinity | NaN | NaN | NaN |
| +0.0 | +0.0 | 1.0 | +0.0 |
| −0.0 | −0.0 | 1.0 | −0.0 |

The two values **+0.0 and −0.0** are equal under the == operator but differ in sign bit. If you need to check for negative zero:

~~~java
boolean negativeZeroRetained =
        Double.doubleToRawLongBits(Math.sin(-0.0))
                == Double.doubleToRawLongBits(-0.0); // true
~~~

If data represents a **real physical angle**, you should usually check for finite input:

~~~java
if (!Double.isFinite(angleDegrees)) {
    throw new IllegalArgumentException("Angle must be finite");
}
double radians = Math.toRadians(angleDegrees);
~~~

This snippet sits inside a method with a declared angleDegrees variable. Do not compare a value to Double.NaN using ==, because NaN does not equal itself. Use **Double.isNaN** to check.

## 12. Negative Angles, Multiple Turns, and Very Large Angles

Mathematically, sin and cos have period 2π, and tan has period π. Thus 30° and 390° give the same ideal sin/cos values. However, in floating-point arithmetic, multiplication and range reduction can introduce rounding.

If you need an angle normalized in degrees within **[0,360)** for ordinary finite data:

~~~java
double normalized = ((angleDegrees % 360.0) + 360.0) % 360.0;
~~~

This illustrative formula is not an absolutely exact argument-reduction method for **arbitrarily huge doubles**. When angles accumulate over too many turns, the fractional part of the angle can be lost due to double resolution. Good design keeps angles within a moderate finite range from the start when workflows allow.

Also distinguish periodicity from domain: a negative angle can carry rotational direction information, so do not blindly call **Math.abs** before computing sin.

## 13. Recovering the Angle with Math.atan2

When you have coordinates **(x,y)** and want to derive the angle, use **Math.atan2(y, x)** to get the angle in radians, then **Math.toDegrees** if you want degrees:

~~~java
double x = Math.sqrt(3.0);
double y = 1.0;
double radians = Math.atan2(y, x);
double degrees = Math.toDegrees(radians); // approximately 30.0
~~~

**The argument order of atan2 is (y, x)**, which is very easy to confuse with coordinates usually written as (x,y). Unlike atan(y/x), atan2 distinguishes quadrants and has rules for coordinate axes and signed zero. The atan2 function is useful when going the reverse direction from a vector to an angle.

This is supplementary related knowledge: the main purpose of this lesson remains converting **degrees to radians before using sin/cos/tan**.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling Math.sin(30) when 30 is in degrees | Computes sine of 30 radians | Math.sin(Math.toRadians(30)) |
| Forgetting to divide by 180 when using Math.PI | Wrong angle unit | Use Math.toRadians |
| Assuming Math.PI represents π exactly | == comparisons at π, π/2 fail | Policy-based approximate comparison |
| Expecting tan at 90° to always equal Infinity | Java may return a very large finite number | Handle asymptotes/angle domains |
| Using tan to represent a vertical line | Mathematical slope is undefined | Handle vertical vectors/lines separately |
| Comparing Math.cos(Math.PI/2) == 0 | May be false due to rounding | Use an appropriate check |
| Using a fixed epsilon for all angles | May be too large or too small | Choose threshold per requirements |
| Taking Math.abs of a negative angle | Loses rotation direction, wrong sin/tan | Preserve sign per contract |
| Thinking StrictMath takes degrees | Also takes radians | Convert units beforehand |
| Dividing sin/cos instead of tan expecting identical bits | Algorithms/rounding differ | Call Math.tan when tan is needed |
| Failing to check NaN/infinity | Causes NaN propagation | Check Double.isFinite if needed |
| Treating y-downward as y-upward | Vector rotates incorrectly geometrically | Identify the coordinate system |
| Adding huge turn counts then reducing modulo arbitrarily | Double resolution may lose phase | Keep angles in a moderate range |

## 15. Exercises and Answers

**Exercise 1.** How do you write the expression to compute sin 60° in Java?

*Answer:* **Math.sin(Math.toRadians(60.0))**, approximately **0.8660254**.

**Exercise 2.** How many radians is 45°? What is tan(45°) mathematically?

*Answer:* **π/4 rad** and **1**. Java's computed value is an approximation.

**Exercise 3.** Is Math.cos(Math.toRadians(90.0)) always 0.0?

*Answer:* No. Math.PI and double calculations introduce rounding error, so it typically produces around **6.123e−17**.

**Exercise 4.** Why should tan(90°) not be used to compute the slope of a vertical line?

*Answer:* Tan at 90° is mathematically undefined; Math.tan called with a double angle near π/2 can return a very large finite value that is extremely sensitive.

**Exercise 5.** Given a vector of length 10 at angle 30°, what are the approximate x and y components?

*Answer:* **x≈8.660254**, **y≈5** taking the positive x-axis as 0° and counter-clockwise as positive.

**Exercise 6.** If the input is already in radians, should you call Math.toRadians again?

*Answer:* No. Pass the radian angle directly to Math.sin/cos/tan.

**Exercise 7.** What does Math.sin(Double.POSITIVE_INFINITY) return?

*Answer:* **NaN**, checked using **Double.isNaN**.

**Exercise 8.** When should StrictMath.sin be chosen?

*Answer:* When reproducibility per the StrictMath specification across implementations is required; both Math and StrictMath still take radians.

**Exercise 9.** Why might converting degrees to radians and back to degrees not match exactly with ==?

*Answer:* π and double results have finite precision, so conversions may involve rounding.

## 16. Official References

- [Math Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): sin, cos, tan, PI, toRadians, toDegrees, accuracy of functions.
- [StrictMath Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): reproducibility of mathematical functions.
- [Double Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): NaN, Infinity, isFinite, and raw bits.
- [Java Language Specification 17 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): double representation, signed zero, NaN, and infinity.
