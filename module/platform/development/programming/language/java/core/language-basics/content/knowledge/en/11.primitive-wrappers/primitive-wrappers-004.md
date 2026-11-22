# Distinguishing Wrapper Reference Comparison from Value Comparison — Java 17+

In Java, **wrapper classes** such as `Integer`, `Long`, `Double`, `Float`, `Boolean`, `Character`, `Byte`, and `Short` are **reference types** that wrap primitive values. Therefore, the following two questions are **not the same**:

1. **Do two variables point to the same object?** Use `==` when both operands are genuinely being compared as references.
2. **Do two objects have equal values according to the wrapper class's rules?** Use `equals()` or `Objects.equals()`, depending on whether `null` can occur.

~~~java
Integer a = Integer.valueOf(100);
Integer b = Integer.valueOf(100);

System.out.println(a == b);      // true when the value 100 is cached.
System.out.println(a.equals(b)); // true because the values are equal.
~~~

**Key point:** the result `a == b` being `true` is **not because `==` compared the numeric values**. It is a consequence of both references pointing to the same shared wrapper obtained through the caching mechanism.

## 1. Table Distinguishing Comparison Operations

| Expression | Primary Meaning | Null-Safe? |
| --- | --- | --- |
| `wrapperA == wrapperB` | Compares **reference identity** when both are wrapper references of the same type | Yes, if only comparing references |
| `wrapperA.equals(wrapperB)` | Compares **wrapper values** according to the `equals` implementation | No if `wrapperA == null` |
| `Objects.equals(wrapperA, wrapperB)` | Checks equality, handling `null` on either side | Yes |
| `intA == intB` | Compares primitive `int` values | Primitives cannot hold `null` |
| `wrapperA == intB` | The wrapper can be **unboxed**, then primitive values are compared | Unsafe if wrapper is `null` |
| `Integer.compare(a, b)` | Compares order of two `int`s, returning negative/0/positive | `a` and `b` are primitives |
| `wrapperA.compareTo(wrapperB)` | Compares order of two compatible wrappers | Can throw NPE when null is involved |

Java selects rules based on **operand types**, not because one side "looks like a number". In particular, `Integer == Integer` (two wrappers) and `Integer == int` (one wrapper, one primitive) can lead to **two different kinds of comparisons**.

## 2. Runnable Java 17+ Example

Save as a UTF-8 file **`WrapperEqualityDemo.java`**:

~~~java
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(100);
        Integer smallB = Integer.valueOf(100);
        Integer alias = smallA;

        System.out.println("smallSameReference=" + (smallA == smallB));
        System.out.println("aliasSameReference=" + (alias == smallA));
        System.out.println("smallValueEqual=" + smallA.equals(smallB));

        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);
        System.out.println("largeValueEqual=" + largeA.equals(largeB));
        System.out.println("largeObjectsEqual="
                + Objects.equals(largeA, largeB));

        Integer integer42 = Integer.valueOf(42);
        Long long42 = Long.valueOf(42L);
        System.out.println("crossWrapperEquals="
                + integer42.equals(long42));
        System.out.println("compareOrder="
                + Integer.valueOf(5).compareTo(Integer.valueOf(9)));

        int primitive100 = 100;
        System.out.println("wrapperVsPrimitive="
                + (smallA == primitive100));
        System.out.println("equalsBoxedArgument="
                + smallA.equals(100));

        Integer missing = null;
        Integer alsoMissing = null;
        System.out.println("bothNullReferences="
                + (missing == alsoMissing));
        System.out.println("nullVsWrapper=" + (missing == smallA));
        System.out.println("bothNullObjects="
                + Objects.equals(missing, alsoMissing));
        System.out.println("mixedObjects="
                + Objects.equals(missing, smallA));
        System.out.println("knownEqualsNull=" + smallA.equals(missing));
        System.out.println("guardedCompare="
                + (missing != null && missing.intValue() == 100));

        try {
            System.out.println("dangerousCompare="
                    + (missing == primitive100));
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }

        try {
            System.out.println("dangerousEquals="
                    + missing.equals(smallA));
        } catch (NullPointerException ex) {
            System.out.println("equalsNull=NullPointerException");
        }

        System.out.println("nanPrimitive="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapper="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("signedZeroPrimitive=" + (0.0d == -0.0d));
        System.out.println("signedZeroWrapper="
                + Double.valueOf(0.0d)
                        .equals(Double.valueOf(-0.0d)));
        System.out.println("signedZeroCompare="
                + Double.compare(0.0d, -0.0d));

        System.out.println("booleanWrapper="
                + Boolean.TRUE.equals(Boolean.valueOf(true)));
        System.out.println("numericDifferentWrappers="
                + Double.valueOf(1.0).equals(Integer.valueOf(1)));
    }
}
~~~

In PowerShell (Windows) or Bash (Linux/macOS), run from the directory containing the file using **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WrapperEqualityDemo.java
java WrapperEqualityDemo
~~~

**Exact expected output of `java WrapperEqualityDemo`:**

~~~text
smallSameReference=true
aliasSameReference=true
smallValueEqual=true
largeValueEqual=true
largeObjectsEqual=true
crossWrapperEquals=false
compareOrder=-1
wrapperVsPrimitive=true
equalsBoxedArgument=true
bothNullReferences=true
nullVsWrapper=false
bothNullObjects=true
mixedObjects=false
knownEqualsNull=false
guardedCompare=false
unboxNull=NullPointerException
equalsNull=NullPointerException
nanPrimitive=false
nanWrapper=true
signedZeroPrimitive=true
signedZeroWrapper=false
signedZeroCompare=1
booleanWrapper=true
numericDifferentWrappers=false
~~~

The `java -version` and `javac -version` commands have JDK-dependent output and are not part of the expected output block above.

## 3. Caching Is Only One Reason `==` Can Appear Correct

`Integer.valueOf(int)` is guaranteed to reuse objects for integers from **−128 to 127**:

~~~java
Integer a = Integer.valueOf(100);
Integer b = Integer.valueOf(100);
System.out.println(a == b); // true, because it is the same cached object.
~~~

For values outside the guaranteed range, such as `1_000`, you should not state a fixed output for `Integer.valueOf(1000) == Integer.valueOf(1000)`; the JVM may cache more broadly. `equals` is the stable contract for value comparison. The next lesson separately explains the cache ranges of `Byte`, `Short`, `Long`, `Character`, `Boolean`, and what is **not guaranteed** regarding object identity.


## 4. When One Side Is a Primitive, `==` Can Trigger Unboxing

~~~java
Integer wrapper = Integer.valueOf(100);
int number = 100;
System.out.println(wrapper == number); // true.
~~~

With `Integer == int`, Java can **unbox** the wrapper to `int` and apply primitive numeric comparison. Therefore, the result reflects the numeric value **only after unboxing**.

If the wrapper is `null`:

~~~java
Integer maybe = null;
int number = 100;

// boolean same = maybe == number;
// Runtime: NullPointerException when unboxing maybe.
~~~

Conversely, the following comparison **does not unbox** merely because `null` is encountered if both operands have the same reference type:

~~~java
Integer a = null;
Integer b = Integer.valueOf(100);

System.out.println(a == b); // false, no NPE.
~~~

**Rule to remember:** always check the **static types of both operands** before explaining `==`, and avoid comparison expressions that unbox a potentially null wrapper.

## 5. What Does Wrapper `equals()` Compare?

For `Integer`, the `equals` method returns `true` when the argument is an **`Integer`** containing the same `int` value:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
Long c = Long.valueOf(42L);

System.out.println(a.equals(b)); // true.
System.out.println(a.equals(c)); // false.
~~~

`Integer(42)` and `Long(42)` carry corresponding **mathematical values** but are **not the same wrapper type**. Neither class's `equals` automatically converts `Long` to `Integer`.

For `Double`/`Float`, there are also two special points:

| Data Pair | Primitive `==` Comparison | Wrapper `equals` |
| --- | --- | --- |
| `Double.NaN` and `Double.NaN` | `false` | `true` |
| `+0.0d` and `-0.0d` | `true` | `false` |

`Double.equals` uses the bit rules of `Double.doubleToLongBits`: NaN representations are canonicalized when checking equality, while the sign of zero is distinguished. `Float.equals` behaves similarly. Therefore, **do not arbitrarily replace** primitive floating-point comparisons with `equals` if the problem specification requires the IEEE 754 rules of the `==` operator.

If you want ordering comparisons, `Integer.compare`, `Long.compare`, `Double.compare`, or `compareTo` have different semantics from checking reference equality. `Double.compare(+0.0, -0.0)` returns a **positive** result, as shown in the example.

## 6. `null`: How to Compare Safely

**`equals` can throw an NPE when the receiver object is null:**

~~~java
Integer a = null;
Integer b = 10;

// a.equals(b); // NullPointerException.
System.out.println(Objects.equals(a, b)); // false.
~~~

`Objects.equals(a, b)` checks safely when one or both variables may be null; two null values are considered equal. However, whether **"both values missing" should be treated as equivalent in business logic** is a separate application decision.

| Requirement | How to Write It | Notes |
| --- | --- | --- |
| Wrappers known non-null, same type | `a.equals(b)` | Compares wrapper values |
| Two wrappers that may be null | `Objects.equals(a, b)` | Null-safe, uses `equals` for objects |
| One wrapper against a fixed value | `Integer.valueOf(10).equals(a)` | Receiver object is guaranteed non-null |
| Comparing a primitive and a nullable wrapper | `a != null && a.intValue() == 10` | Null check before unboxing |
| Ascending/descending ordering | `Integer.compare(x, y)` | Uses primitives; handle null first if source is a wrapper |
| Checking same object | `a == b` | Only when identity is genuinely the goal |

**Do not use `Objects.equals` as a cross-type numeric comparison:** `Objects.equals(Integer.valueOf(1), Long.valueOf(1))` is `false` because the two wrappers have different classes.

## 7. Autoboxing, Caching, and Reassignment

~~~java
Integer a = 7;
Integer b = a;

a = a + 1;
System.out.println(a); // 8.
System.out.println(b); // 7.
~~~

`a + 1` unboxes `Integer` to `int`, adds to get 8, then boxes the result to reassign `a`. Wrappers are immutable: this assignment **does not modify** the object referenced by `b`.

Caching is a possible optimization for immutable objects; the existence of a cache does not turn `Integer` into a primitive. Do not try to guess how many objects are allocated solely from boxing syntax without empirical verification and unless it is central to the problem.

## 8. Self-Check Exercises

1. **Two `Integer` wrappers:** `Integer a = 100, b = 100; a == b` returns what?  
   *Answer:* `true` with autoboxing of the constant 100 in the guaranteed cache range; however, do not use `==` as a general value comparison.
2. **Large wrappers:** `Integer a = Integer.valueOf(1000); Integer b = Integer.valueOf(1000); a.equals(b)` returns what?  
   *Answer:* `true`. Do not assume a fixed result for `a == b`.
3. **Different types:** `Integer.valueOf(42).equals(Long.valueOf(42L))` returns what?  
   *Answer:* `false` because the argument is not an `Integer`.
4. **Unboxing:** `Integer x = null; boolean same = (x == 10);` — what happens?  
   *Answer:* Throws `NullPointerException` when unboxing `x`.
5. **Null-safe:** What are `Objects.equals(null, null)` and `Objects.equals(null, Integer.valueOf(1))`?  
   *Answer:* `true` and `false`, respectively.
6. **NaN:** Why is `Double.NaN == Double.NaN` false, while `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` is true?  
   *Answer:* Primitive `==` follows floating-point NaN rules; wrapper `equals` applies equality rules on the NaN-canonicalized bit representation.
7. **Signed zero:** What is `Double.valueOf(0.0).equals(Double.valueOf(-0.0))`?  
   *Answer:* `false`; the wrapper distinguishes the sign of zero, even though `0.0 == -0.0` is `true`.

## Checklist

- [ ] Distinguish **reference identity** from **wrapper value equality**.
- [ ] For two wrappers of the same type, `==` checks the object; `equals` checks the wrapper value.
- [ ] Do not rely on `Integer` caching to predict the result of `==` for all numbers.
- [ ] When comparing a wrapper to a primitive, check the risk of **unboxing null**.
- [ ] Use `Objects.equals` when two wrappers may be null.
- [ ] Do not treat `Integer` and `Long` with equal numeric values as `equals`.
- [ ] Remember the differences of `Double`/`Float` regarding `NaN` and `+0.0`/`-0.0`.
- [ ] Choose `compare`/`compareTo` when ordering is needed instead of equality.

**Conclusion:** To check for **the same object**, use `==` between references and understand caching. To check for **the same wrapper value**, use `equals` or `Objects.equals` (when null is possible). When one side is primitive, always check **unboxing** before assuming `==` is safe.