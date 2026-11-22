# Float and Double in Java: NaN, +0.0, and -0.0

## 1. Why does this matter for object contracts?

Java has two primitive floating-point types, **float** (32-bit) and **double** (64-bit), along with two corresponding wrapper classes, **Float** and **Double**. Even when two values carry the same arithmetic meaning, **primitive comparison with ==** can differ from the wrapper class's **equals(Object)** method, especially for **NaN** and **signed zeros**.

- **NaN (Not a Number):** two NaN values compared with == on primitive floating-point numbers yield false, whereas the Float/Double wrapper classes consider NaNs equal under equals.
- **+0.0 and -0.0:** primitive floating-point numbers consider them equal under ==, whereas wrapper classes distinguish them in equals.
- The compare/compareTo methods of Float/Double are designed to be consistent with wrapper equals, rather than merely using the < or > operators on floating-point numbers.
- The hashCode methods of the wrapper classes follow the exact rules of equals, because HashSet/HashMap depend on the equals–hashCode contract.

Therefore, when writing equals and hashCode for an object with a float/double field, you must decide on the **desired equality relation** and handle both NaN and signed zero. The examples below use Java 17+.

## 2. NaN: special value and primitive floating-point operators

NaN denotes a result that is not a defined real number according to IEEE 754. For example:

~~~java
double a = 0.0d / 0.0d;
double b = Math.sqrt(-1.0d);
float c = 0.0f / 0.0f;
~~~

Those floating-point operations produce NaN; they do not throw ArithmeticException like integer division by 0. Built-in constants: **Double.NaN** and **Float.NaN**.

For a double value n = Double.NaN:

| Expression | Result |
| --- | --- |
| n == n | false |
| n != n | true |
| n < 1.0 | false |
| n > 1.0 | false |
| n <= 1.0 | false |
| n >= 1.0 | false |
| Double.isNaN(n) | true |

Any primitive ordering comparison involving NaN also returns false. This is why negated comparison expressions are not sufficient to infer ordering when data may contain NaN.

**Detecting NaN purposefully:**

~~~java
boolean isDoubleNaN = Double.isNaN(a);
boolean isFloatNaN = Float.isNaN(c);
~~~

You can use a != a to detect NaN for primitives, but Double.isNaN/Float.isNaN communicates intent more clearly. NaN is not infinity; use Double.isInfinite/Float.isInfinite when you need to identify Infinity or -Infinity.

## 3. Signed zero: +0.0 and -0.0

IEEE 754 has two representations of zero, differing in the sign bit:

- **+0.0**: sign bit 0.
- **-0.0**: sign bit 1.

For primitive floating-point operands, these two values are considered equal:

~~~java
System.out.println(+0.0d == -0.0d); // true
System.out.println(1.0d / +0.0d);    // Infinity
System.out.println(1.0d / -0.0d);    // -Infinity
~~~

They are equal under ==, yet division can produce infinities of opposite signs. This is why the sign representation is not a meaningless detail in every application.

You can inspect the bits using these APIs:

~~~java
Double.doubleToRawLongBits(+0.0d); // 0L
Double.doubleToRawLongBits(-0.0d); // Long.MIN_VALUE
Float.floatToRawIntBits(+0.0f);   // 0
Float.floatToRawIntBits(-0.0f);   // Integer.MIN_VALUE
~~~

These snippets illustrate expressions in a Java context; they are not a complete program class. The two methods with Raw preserve the representation bits as-is. The methods without Raw also preserve the signed zero difference, but normalize NaN bit patterns.

## 4. Float.equals() and Double.equals() have their own rules

The contract of the wrapper classes is:

- **Double.equals(Object)** is true only when the argument is also a Double and both values have the same bits according to **Double.doubleToLongBits**.
- **Float.equals(Object)** is true only when the argument is also a Float and both values have the same bits according to **Float.floatToIntBits**.

The two bit-conversion functions **normalize all NaN values** to a canonical NaN representation. Thus, NaNs with different payloads are still considered equal by equals. By contrast, +0.0 and -0.0 have different sign bits, so they are **not equal under wrapper equals**.

| Same-type number pair | == on primitives | Wrapper equals |
| --- | --- | --- |
| 1.5 and 1.5 | true | true |
| NaN and NaN | false | true |
| +0.0 and -0.0 | true | false |
| +0.0 and +0.0 | true | true |
| -0.0 and -0.0 | true | true |
| Infinity and Infinity | true | true |
| Infinity and -Infinity | false | false |

Example:

~~~java
double n1 = Double.NaN;
double n2 = 0.0d / 0.0d;
System.out.println(n1 == n2); // false
System.out.println(Double.valueOf(n1).equals(Double.valueOf(n2))); // true

double pz = +0.0d;
double nz = -0.0d;
System.out.println(pz == nz); // true
System.out.println(Double.valueOf(pz).equals(Double.valueOf(nz))); // false
~~~

You also need to distinguish **== between two wrapper references**: if both operands are Double (or Float) objects, == compares **object identity**, not value. If one operand is primitive, Java can perform unboxing, and unboxing a null value throws NullPointerException. When reading an expression, always check the exact types of both sides.

**Float.equals cannot consider a Double equal**, and vice versa, even if the two objects have nearly identical printed representations. They are two classes of different types.

## 5. Ordering comparisons: compare and compareTo

**Double.compare(x, y)** and **Float.compare(x, y)** use a total order compatible with wrapper equals:

1. All NaNs of the same type are treated as equivalent when comparing: compare(NaN, NaN) equals 0.
2. NaN ranks greater than every numeric value, including +Infinity.
3. -0.0 ranks less than +0.0.
4. For ordinary numbers and infinities, natural numeric ordering is preserved.

Example:

~~~java
Double.compare(Double.NaN, Double.NaN);             // 0
Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // 1
Double.compare(-0.0d, +0.0d);                        // -1
Float.compare(-0.0f, +0.0f);                        // -1
~~~

The compare functions return a negative number, 0, or a positive number; for the pairs listed here, the specific Java results are 0, 1, -1, and -1, respectively. The wrapper classes' compareTo uses the same rules.

To sort Double/Float, prefer explicit comparators:

~~~java
// Illustrative declarations only; requires import java.util.Comparator.
Comparator<Double> doubleComparator = Double::compare;
Comparator<Float> floatComparator = Float::compare;
~~~

**Common mistake:**

~~~java
// Wrong: loses fractional part, fails with NaN and signed zero.
Comparator<Double> bad = (a, b) -> (int) (a - b);

// Also inconsistent with wrapper equals when NaN/signed zero are present.
Comparator<Double> bad2 = (a, b) -> a < b ? -1 : a > b ? 1 : 0;
~~~

The second comparator can return 0 even when one side is NaN and the other is a normal number, or return 0 for the two signed zeros. With **TreeSet** or **TreeMap**, the comparator decides whether two keys occupy the same logical slot via compare == 0, so a comparator that differs from equals rules can cause surprising behavior compared to HashSet/HashMap.

## 6. HashCode of Float and Double: mandatory compatibility

Two objects that are equal under equals must have the same hashCode. The methods **Double.hashCode(double)** and **Float.hashCode(float)** are designed to be compatible with the wrapper rules:

- All NaNs of the same type are normalized and therefore have the same hash.
- +0.0 and -0.0 have different sign bits and therefore have different hashes.
- Two unequal values are not required to have different hashes: hash collisions are still valid.

Some concrete results:

~~~java
Double.hashCode(+0.0d); // 0
Double.hashCode(-0.0d); // Integer.MIN_VALUE
Float.hashCode(+0.0f);  // 0
Float.hashCode(-0.0f);  // Integer.MIN_VALUE
~~~

This is consistent with Double.equals/Float.equals because the equals methods **distinguish** signed zeros.

Collection example:

~~~java
// Illustrative snippet assuming Set and HashSet are already imported.
Set<Double> values = new HashSet<>();
values.add(Double.NaN);
values.add(Double.NaN); // Duplicate under Double.equals.
values.add(+0.0d);
values.add(-0.0d);       // Distinct under Double.equals.
System.out.println(values.size()); // 3
~~~

The HashSet contains one NaN element and two zero elements of opposite signs. If replaced with HashSet<Float>, the same principle applies.

**Do not** use Double.doubleToRawLongBits or Float.floatToRawIntBits directly as the basis for hashing an object whose equals merges all NaNs; NaNs with different raw bits could produce different hashes even though equals is true. The doubleToLongBits/floatToIntBits functions normalize NaN and are appropriate when following wrapper rules.

## 7. Compilable/runnable Java 17+ program

Save with the exact name **FloatingEqualityDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double nanA = Double.NaN;
        double nanB = 0.0d / 0.0d;
        double positiveZero = +0.0d;
        double negativeZero = -0.0d;

        System.out.println("double NaN == NaN: " + (nanA == nanB));
        System.out.println("Double.equals NaN: "
                + Double.valueOf(nanA).equals(Double.valueOf(nanB)));
        System.out.println("Double.compare NaN: "
                + Double.compare(nanA, nanB));
        System.out.println("Double.isNaN: " + Double.isNaN(nanA));
        System.out.println("NaN hashes equal: "
                + (Double.hashCode(nanA) == Double.hashCode(nanB)));

        System.out.println("double +0 == -0: "
                + (positiveZero == negativeZero));
        System.out.println("Double.equals zeros: "
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("Double.compare(-0,+0): "
                + Double.compare(negativeZero, positiveZero));
        System.out.println("Zero hashes differ: "
                + (Double.hashCode(positiveZero)
                        != Double.hashCode(negativeZero)));

        Set<Double> doubles = new HashSet<>();
        doubles.add(nanA);
        doubles.add(nanB);
        doubles.add(positiveZero);
        doubles.add(negativeZero);
        System.out.println("HashSet<Double> size: " + doubles.size());

        System.out.println("Arrays.equals double NaNs: "
                + Arrays.equals(new double[] {nanA},
                        new double[] {nanB}));
        System.out.println("Arrays.equals double zeros: "
                + Arrays.equals(new double[] {positiveZero},
                        new double[] {negativeZero}));

        float floatNanA = Float.NaN;
        float floatNanB = 0.0f / 0.0f;
        float floatPositiveZero = +0.0f;
        float floatNegativeZero = -0.0f;

        System.out.println("float NaN == NaN: "
                + (floatNanA == floatNanB));
        System.out.println("Float.equals NaN: "
                + Float.valueOf(floatNanA)
                        .equals(Float.valueOf(floatNanB)));
        System.out.println("Float.compare NaN: "
                + Float.compare(floatNanA, floatNanB));
        System.out.println("float +0 == -0: "
                + (floatPositiveZero == floatNegativeZero));
        System.out.println("Float.equals zeros: "
                + Float.valueOf(floatPositiveZero)
                        .equals(Float.valueOf(floatNegativeZero)));
        System.out.println("Float.compare(-0,+0): "
                + Float.compare(floatNegativeZero, floatPositiveZero));
        System.out.println("Float zero hashes differ: "
                + (Float.hashCode(floatPositiveZero)
                        != Float.hashCode(floatNegativeZero)));
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac -encoding UTF-8 FloatingEqualityDemo.java
java FloatingEqualityDemo
~~~

**Exact expected stdout:**

~~~text
double NaN == NaN: false
Double.equals NaN: true
Double.compare NaN: 0
Double.isNaN: true
NaN hashes equal: true
double +0 == -0: true
Double.equals zeros: false
Double.compare(-0,+0): -1
Zero hashes differ: true
HashSet<Double> size: 3
Arrays.equals double NaNs: true
Arrays.equals double zeros: false
float NaN == NaN: false
Float.equals NaN: true
Float.compare NaN: 0
float +0 == -0: true
Float.equals zeros: false
Float.compare(-0,+0): -1
Float zero hashes differ: true
~~~

Explanation:

1. Two NaNs are not equal under primitive ==, but are equal under wrapper equals, have compare equal to 0, and have the same hash.
2. Two signed zeros are equal under ==, but differ under wrapper equals, compare, and hash.
3. HashSet<Double> holds only one NaN (regardless of how it was created) and two zeros of opposite signs.
4. **Arrays.equals(double[], double[])** and the float[] overload use element comparison rules matching the normalized bits: NaNs are equivalent to each other, and the two signed zeros are distinct. You cannot assume that every floating-point array comparison applies primitive ==.

This program is a standalone example; the short code blocks in earlier sections only illustrate how the API works.

## 8. Writing equals/hashCode for a class with a double or float field

If the **Sample** class has a double value field and wants an equality relation like Double.equals, use this pair:

~~~java
// Placed inside class Sample, assuming a final class with a double value field.
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Sample other)) {
        return false;
    }
    return Double.compare(value, other.value) == 0;
}

@Override
public int hashCode() {
    return Double.hashCode(value);
}
~~~

This is an excerpt inside a class, not a standalone runnable program. For float, use **Float.compare** and **Float.hashCode** respectively. Same-reference, null, and object-type checks remain important; in inheritance hierarchies with subclassing, you also need to handle symmetry/transitivity when extending equals.

**Why not use == in equals and Double.hashCode in hashCode?** If equals checks primitive value == other.value, two objects containing +0.0 and -0.0 will be equal yet receive different hashCodes. That violates the requirement that **equals true implies equal hashes**.

With NaN, == is always false, so a naive implementation missing the same-reference check can even cause an object containing NaN **not to equal itself**, violating reflexivity of equals.

### 8.1. When business logic wants to merge +0.0 and -0.0

Not every value class is required to keep Double.equals's signed-zero policy. If the problem treats +0.0 and -0.0 as the same value, normalize **before both comparison and hashing**:

~~~java
// Illustrative methods inside a final Measurement class
// with an immutable double value field.
private static double normalizeZero(double x) {
    return x == 0.0d ? 0.0d : x;
}

@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Measurement other)) {
        return false;
    }
    return Double.doubleToLongBits(normalizeZero(value))
            == Double.doubleToLongBits(normalizeZero(other.value));
}

@Override
public int hashCode() {
    return Double.hashCode(normalizeZero(value));
}
~~~

This custom rule merges the two signed zeros while still treating all NaNs as equal. Normalizing in **both methods** preserves the hash contract. If you need to sort these Measurement objects, the comparator must also use the same rule if you want compare == 0 to be equivalent to equals.

If you use a **record** with a float/double component, Java generates equals/hashCode following the rule that distinguishes signed zeros and treats NaNs as equivalent. When custom equality is needed, never change only equals and forget hashCode.

### 8.2. Avoid using approximate comparison as equals

A formula like the absolute value of the difference being less than epsilon is often useful to check *near-equality* in calculations. However, if used directly as Object.equals, it can violate **transitivity**: a is close to b, b is close to c, yet a is not close to c. Approximate checks also need to handle NaN/infinity and overflow appropriately.

Create a separate method such as **approximatelyEqual(a, b, tolerance)** for tolerance needs, or define quantization into value buckets with a proper equality relation and hash if you genuinely need the objects as hash keys.

## 9. Choosing the right API for the need

| Need | Appropriate tool |
| --- | --- |
| Check whether a value is NaN | Double.isNaN / Float.isNaN |
| Primitive check using IEEE operators | ==, !=, <, > with float/double |
| Compare wrapper objects | Double.equals / Float.equals |
| Ordering compatible with wrapper equals | Double.compare / Float.compare |
| Hashing compatible with wrappers | Double.hashCode / Float.hashCode |
| Compare float[]/double[] arrays | Arrays.equals |
| Hash arrays by elements | Arrays.hashCode |
| Distinguish zero sign bits | doubleToRawLongBits / floatToRawIntBits |
| Merge signed zeros per business rules | Normalize consistently in equals, hashCode, and comparator |
| Check floating-point numbers within a tolerance | Separate method, do not arbitrarily replace Object.equals |

## 10. Misconceptions to avoid

**"Two NaNs are different values in every context."** Incorrect: primitive == returns false, but wrapper equals returns true for any NaNs of the same type and compare returns 0.

**"+0.0 and -0.0 are equal so two Doubles must be equals."** Incorrect: primitive == returns true, while Double.equals distinguishes the sign to provide an object rule stable with hashing and ordering.

**"If Double.compare(x, y) == 0 then x == y on primitives."** Incorrect for NaN. A pair with compare == 0 corresponds to the wrapper equals relation of the same type.

**"If unequal under equals, hashCode must differ."** Incorrect: collisions are allowed. However, two values equal under equals must have the same hash.

**"Hashing raw bits directly will always work."** Incorrect if equals merges NaNs with different payloads or merges signed zeros. Always use a hashing scheme consistent with the chosen equality relation.

**"Skipping the same-reference check does no harm because there are only numeric fields."** Dangerous if equals uses == with NaN, breaking reflexivity.

**"Using an arbitrary Comparator does not affect collections."** Incorrect for TreeSet/TreeMap: compare == 0 determines key identity in an ordered set/map, which can sometimes differ from equals.

## 11. Testing checklist

When testing a class containing float/double, check all of these scenarios:

1. **Self-comparison:** x.equals(x) is always true, even when x contains NaN.
2. **Two objects with NaN:** result matches the documented rule; true if using wrapper semantics.
3. **Two signed zeros:** result matches the documented rule; wrapper semantics distinguish them, custom normalized semantics merge them.
4. **Hashing:** every pair where equals is true must have equal hashCodes.
5. **Ordering comparison:** if a comparator/Comparable exists, check whether compare == 0 reflects the same equality relation as designed.
6. **Collections:** insert NaN and both signed zeros into HashSet/TreeSet and verify the element count matches the comparison rules.
7. **State stability:** equals/hashCode must not return random results when comparison state has not changed.
8. **Type distinction:** Float.equals(Double) is always false; do not infer equality from identical printed strings.
9. **Normal numbers, infinities, null:** verify cases without NaN or signed zero still obey the contract.
10. **Immutability:** avoid mutating fields used in equals/hashCode after using the object as a HashMap/HashSet key.

**Remember:** for primitive floating-point numbers, NaN does not equal NaN and +0.0 equals -0.0 under ==; for Float/Double wrappers, **NaN equals NaN while the two signed zeros differ**. Design equals, hashCode, and comparator under the same rule so collections and comparisons behave consistently.
