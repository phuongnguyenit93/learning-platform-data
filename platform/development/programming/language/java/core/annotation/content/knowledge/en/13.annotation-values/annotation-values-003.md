# `hashCode()` Semantics and Comparing Annotation Array Elements in Java

## 1. Why Do Annotations Need Their Own Comparison Rules?

An annotation in Java is not just text starting with `@`. When retained until runtime, an annotation usage can be returned by Reflection as an object implementing `java.lang.annotation.Annotation`. This object has `equals(Object)`, `hashCode()`, `toString()`, and `annotationType()`.

Consider the annotation type:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Endpoint {
    String path();
    int[] ports() default {80, 443};
}
~~~

And two annotated classes:

~~~java
@Endpoint(path = "/status")
class StatusA {
}

@Endpoint(path = "/status", ports = {80, 443})
class StatusB {
}
~~~

The two usages are written differently: one **omits** `ports` to take the default, while the other **explicitly specifies** the same value. In terms of annotation semantics, they have **the same annotation type and the same effective value for each element**. Therefore, the annotation objects returned at runtime must be `equals()` to each other and have the same `hashCode()`.

Conversely, `ports = {443, 80}` is a **different** array value from `ports = {80, 443}`, because element order is meaningful in array comparison.

This article clarifies three questions:

1. How Java defines two **equal annotations**.
2. Why **arrays** in annotations must be compared by content rather than using `==` or `Object.equals()`.
3. How Java computes an annotation's `hashCode()`, especially for arrays, default elements, and nested annotations.

These rules are the **public contract of `java.lang.annotation.Annotation`**, not merely an implementation habit of a specific JDK version.

## 2. The `Annotation.equals(Object)` Contract

According to Java SE 17, two annotation objects `a` and `b` are equal when they **represent the same annotation type** and **every pair of corresponding elements has equal values** according to the rules for that element's type.

For example:

~~~java
@interface Access {
    String role() default "reader";
    int[] levels() default {1, 2};
}
~~~

If we have:

~~~java
@Access
class One {
}

@Access(role = "reader", levels = {1, 2})
class Two {
}

@Access(role = "reader", levels = {2, 1})
class Three {
}
~~~

Then, in terms of annotation values:

- `One` and `Two` are equal: both have `role` equal to `"reader"`, and both have `levels` with the two elements `1, 2`.
- `One` and `Three` are not equal: `levels` has a different order.
- Having the annotation on two **different classes** does not by itself make the annotation values different. The target holding the metadata is not part of an annotation's `equals()`.
- The order in which **name = value pairs** of an annotation are written at the use site does not change the comparison; the order **inside an array** does.

### 2.1. Comparison Depends on the Element Type

| Annotation element type | Value `equals` rule |
| --- | --- |
| Primitive types except `float`, `double` | Compare with `==` on primitive values |
| `float` | Uses `Float.valueOf(x).equals(Float.valueOf(y))` semantics |
| `double` | Uses `Double.valueOf(x).equals(Double.valueOf(y))` semantics |
| `String`, `Class`, enum | Uses `x.equals(y)` |
| Nested annotation | Uses `x.equals(y)` **recursively over the inner annotation elements** |
| One-dimensional array of a valid type | Uses the matching `java.util.Arrays.equals(x, y)` overload |

Java allows annotation elements to have primitive types, `String`, `Class`, enum, another annotation, or a **one-dimensional array** of a permitted type. You cannot declare `List<String>`, `Object`, or `int[][]` as an annotation element type.

### 2.2. Notable Exceptions for `float` and `double`

For `float` or `double` elements, the annotation contract uses the comparison of the corresponding wrapper, **not simply the `==` operator**:

- `NaN` is considered equal to `NaN` under `Float.equals`/`Double.equals`, unlike `NaN == NaN` on primitive floating-point values.
- `+0.0` and `-0.0` are considered **different** under wrapper equality, even though the `+0.0 == -0.0` operator returns `true`.

This ensures that the annotation `equals()` rule is consistent with `hashCode()` for these types. In `float[]` and `double[]` arrays, `Arrays.equals` also has the corresponding semantics for NaN and signed zero.

## 3. Why Do `==` and `array.equals()` Not Compare Array Contents?

In Java, arrays are objects. Two independently created arrays can contain the same elements without sharing the same reference:

~~~java
int[] x = {80, 443};
int[] y = {80, 443};

System.out.println(x == y);             // false
System.out.println(x.equals(y));         // false
System.out.println(java.util.Arrays.equals(x, y)); // true
~~~

This is a **fragment that can be placed inside a method**, not a complete Java file. `x == y` compares reference identity; `int[].equals` inherits `Object.equals` and also does not compare individual elements. Only `Arrays.equals(int[], int[])` checks the length and each value at the corresponding position.

Therefore, **annotations with array elements cannot be compared using the array's `Object.equals`**. Two annotations with independent `ports = {80, 443}` must still be considered equal if their other elements match as well.

Overloads to know:

~~~java
Arrays.equals(int[] a, int[] b)
Arrays.equals(boolean[] a, boolean[] b)
Arrays.equals(double[] a, double[] b)
Arrays.equals(Object[] a, Object[] b)
~~~

The other primitive forms (`byte[]`, `short[]`, `char[]`, `long[]`, `float[]`) also have corresponding overloads. `String[]`, `Class<?>[]`, enum[], or annotation[] arrays use the reference-array overload, comparing contents via each element's `equals`.

**Order matters:** `{80, 443}` is not equal to `{443, 80}`. Even if an application treats two sets of ports as the same set, Java's rule for annotation arrays still compares them as **ordered sequences**, not as sets.

**Do not use `Arrays.deepEquals` as a substitute for the standard rule.** Annotations do not allow declaring elements as multidimensional nested arrays. For valid one-dimensional array types, `Arrays.equals` is the official contract. If an element is an array of annotations, each nested annotation applies `equals` recursively on its own; there is no need to create a two-dimensional array.

## 4. The Annotation `hashCode()` Formula

`Annotation.hashCode()` has a **formula specified in the Java API**, rather than arbitrarily taking a hash code based on object identity.

For each annotation element with name `name` and effective value `value`, its hash contribution is:

```text
memberHash = (127 * name.hashCode()) ^ valueHash
```

Where `^` is the **bitwise XOR** operator on `int` integers, not exponentiation.

The final hash code of the annotation is the **sum of contributions from all elements**, including elements populated from `default` values:

```text
annotationHash =
    sum over all annotation elements:
        (127 * memberName.hashCode()) ^ memberValueHash
```

Multiplication, XOR, and addition are performed with 32-bit `int` integers according to Java semantics (if overflow occurs, the low 32 bits are kept). There is no notion of a "unique positive hash code"; `hashCode()` can be negative and collisions can occur.

### 4.1. How Is `memberValueHash` Computed?

| Element value kind | Hash code used |
| --- | --- |
| Primitive type `v` | `WrapperType.valueOf(v).hashCode()` |
| `String`, `Class`, enum | `v.hashCode()` |
| Nested annotation | `v.hashCode()`, computed recursively for the nested annotation |
| Primitive array | `Arrays.hashCode(v)` using the matching overload |
| Valid reference array | `Arrays.hashCode(v)` for `Object[]` |

Two special rules to emphasize:

- Defaults are also included: if `int[] ports() default {80, 443};` is not passed at the use site, the hash code still adds the contribution of `ports` with the array `{80, 443}`.
- Array elements must use **`Arrays.hashCode` by content**, not `int[].hashCode()` or `String[].hashCode()` from `Object`.

This corresponds to the `Arrays.equals` rule: arrays that are equal by content will have the same hash code, so equal annotations also have the same hash code.

### 4.2. Both Directions of the `equals/hashCode` Contract

True:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

**The converse does not follow:**

```text
a.hashCode() == b.hashCode()  DOES NOT prove a.equals(b)
```

Because the number of `int` hash codes is finite while the number of annotations and values can be vast, unequal objects can still share the same hash code. Hash codes serve lookup structures such as `HashMap`/`HashSet`, **not unique identifiers, tamper-resistant checksums, or cryptographic hash functions**.

## 5. Complete Java 17 Example: Array Comparison, Defaults, and Manual Hash Calculation

Create a single file **`AnnotationHashDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RoutePolicy {
    String route();
    int[] ports() default {80, 443};
    String[] tags() default {"public", "stable"};
    double ratio() default 1.0;
}

@RoutePolicy(route = "/v1")
class FirstRoute {
}

@RoutePolicy(
        ratio = 1.0,
        tags = {"public", "stable"},
        ports = {80, 443},
        route = "/v1")
class SameRoute {
}

@RoutePolicy(route = "/v1", ports = {443, 80})
class ReorderedRoute {
}

public class AnnotationHashDemo {
    public static void main(String[] args) {
        RoutePolicy first =
                FirstRoute.class.getAnnotation(RoutePolicy.class);
        RoutePolicy same =
                SameRoute.class.getAnnotation(RoutePolicy.class);
        RoutePolicy reordered =
                ReorderedRoute.class.getAnnotation(RoutePolicy.class);

        System.out.println("First equals Same: "
                + first.equals(same));
        System.out.println("Same equals First: "
                + same.equals(first));
        System.out.println("First equals Reordered: "
                + first.equals(reordered));
        System.out.println("Equal hashes for equal annotations: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("Matches specified hash formula: "
                + (first.hashCode() == calculateHash(first)));

        int[] x = {80, 443};
        int[] y = {80, 443};
        int[] reversed = {443, 80};

        System.out.println("Array reference equality: " + (x == y));
        System.out.println("Array content equality: "
                + Arrays.equals(x, y));
        System.out.println("Reversed array equality: "
                + Arrays.equals(x, reversed));
        System.out.println("Array content hash equality: "
                + (Arrays.hashCode(x) == Arrays.hashCode(y)));

        Set<RoutePolicy> unique = new HashSet<>();
        unique.add(first);
        unique.add(same);
        unique.add(reordered);
        System.out.println("Unique annotation values: "
                + unique.size());
    }

    private static int calculateHash(RoutePolicy policy) {
        return ((127 * "route".hashCode())
                       ^ policy.route().hashCode())
             + ((127 * "ports".hashCode())
                       ^ Arrays.hashCode(policy.ports()))
             + ((127 * "tags".hashCode())
                       ^ Arrays.hashCode(policy.tags()))
             + ((127 * "ratio".hashCode())
                       ^ Double.valueOf(policy.ratio()).hashCode());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 AnnotationHashDemo.java
java AnnotationHashDemo
~~~

**Expected stdout, independent of reflection traversal order:**

~~~text
First equals Same: true
Same equals First: true
First equals Reordered: false
Equal hashes for equal annotations: true
Matches specified hash formula: true
Array reference equality: false
Array content equality: true
Reversed array equality: false
Array content hash equality: true
Unique annotation values: 2
~~~

### 5.1. Analyzing the Output

**`FirstRoute` and `SameRoute` are equal.** In `FirstRoute`, `ports`, `tags`, and `ratio` take their defaults; `SameRoute` explicitly specifies those exact values. The effective values are identical, even though the order in which `ratio`, `tags`, `ports`, and `route` are written in source differs from their declaration order in the annotation type.

**`ReorderedRoute` differs.** The array `ports = {443, 80}` differs in order from `{80, 443}`, so `equals()` returns `false`, even though both have the same two port numbers.

**The formula check returns `true`.** `calculateHash` sums the exact contributions of the four elements, using `Arrays.hashCode` for the two arrays and `Double.valueOf(...).hashCode()` for `ratio`. The order of addition does not change the `int` result.

**The `HashSet` size is `2`.** `first` and `same` are two equivalent annotation values, so there is only one logical value in the set; `reordered` is not equivalent, so there is one more value. This is why the `equals/hashCode` contract is especially important when annotations are used as keys or elements of hash-based data structures.

**Specific hash numbers are not printed.** The program verifies the correctness of the formula and the equality of hash codes instead of forcing learners to memorize an `int` number. For `Class`, enum, or other element types, the specific hash value may depend on the object/runtime; what Java guarantees is **the comparison contract and the calculation rules per value kind**, not hashes used as persistent identifiers across runs.

### 5.2. Why Can `Arrays.hashCode` Be Used in `calculateHash`?

Because the annotation element `ports()` returns `int[]`, and `tags()` returns `String[]`. The `Arrays.hashCode(int[])` and `Arrays.hashCode(Object[])` overloads hash **the contents of each array**, respectively. Calling:

~~~java
policy.ports().hashCode()
~~~

would obtain the hash of the array object itself, which does not conform to the annotation array element hash rule.

In the manual calculation, pay attention to the parentheses:

~~~java
(127 * "ports".hashCode()) ^ Arrays.hashCode(policy.ports())
~~~

Each contribution is obtained by **XORing the two sides**, and then the contributions of the elements are **summed**. The `^` symbol is not exponentiation and does not replace summing across all elements.

## 6. What Can Annotation Array Elements Contain?

Java restricts annotation elements to valid types: primitives, `String`, `Class`, enums, annotations, or a **one-dimensional array** of any of the above. Accordingly, the following comparisons apply:

| Element | Corresponding comparison | Corresponding hash |
| --- | --- | --- |
| `int[] levels()` | `Arrays.equals(int[], int[])` | `Arrays.hashCode(int[])` |
| `boolean[] flags()` | `Arrays.equals(boolean[], boolean[])` | `Arrays.hashCode(boolean[])` |
| `double[] weights()` | `Arrays.equals(double[], double[])` | `Arrays.hashCode(double[])` |
| `String[] names()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Class<?>[] types()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Mode[] modes()` | `Arrays.equals(Object[], Object[])` | `Arrays.hashCode(Object[])` |
| `Nested[] nested()` | `Arrays.equals(Object[], Object[])`, calling `equals` on each nested annotation | `Arrays.hashCode(Object[])`, calling `hashCode` on each nested annotation |

In the last two rows, `Mode` is an illustrative enum and `Nested` is an illustrative annotation type. Remember that `String[]`, enum[], and annotation[] are all **reference arrays**; Java does not have a separate `Arrays.hashCode(String[])` overload and instead uses the `Object[]` version.

### Nested Annotations Are Compared Recursively

Example definition fragment:

~~~java
@interface Nested {
    String code() default "ok";
}

@interface Outer {
    Nested nested() default @Nested;
    Nested[] checks() default {@Nested(code = "a"), @Nested(code = "b")};
}
~~~

These are two annotation types, not a standalone program with `main`.

If two `Outer` objects have `Nested` instances with the same `code()`, the comparison `Outer.equals(...)` relies on `Nested.equals(...)`. The `checks` element is an array of annotations, so Java uses `Arrays.equals` in order and calls `equals` on each annotation at the corresponding position. Similarly, `Outer`'s `hashCode` uses the recursive hash code of the nested annotations.

`Arrays.deepEquals` is not needed to support `Nested[]`: nested annotations have their own content-based `equals`, and `Nested[][]` is **not a valid annotation element type**.

## 7. Default Values Directly Affect `equals/hashCode`

An easily overlooked point: **every element is considered**, even if the programmer does not write it at the use site.

~~~java
@interface Policy {
    String name() default "standard";
    int[] levels() default {1, 2};
}
~~~

Two usages:

~~~java
@Policy
class A {
}

@Policy(name = "standard", levels = {1, 2})
class B {
}
~~~

They have the same effective values. When read at runtime, `Policy.name()` on both is `"standard"`, and `Policy.levels()` on both is `{1, 2}`. Therefore `equals()` holds and `hashCode()` includes the contributions of both `name` and `levels`.

It is **not** the case that because the `@Policy` source omits `levels`, the `hashCode()` formula skips that element. An annotation's hash must be consistent with the actual values the annotation represents.

### What If a Library Changes a Default Value?

Suppose an older version defines `int[] levels() default {1, 2};`, and a newer version changes it to `default {1, 3};`. Annotation use sites that **omit `levels`** can receive a different effective value when the code is run or decoded with the new annotation definition.

Because `equals()` and `hashCode()` depend on element values, changing a default can **alter comparison behavior and lookups in hash collections**, even if client source code does not change. Changing a default should not be treated as merely a documentation fix or a cosmetic API change.

Conversely, if a use site has **explicitly written** `levels = {1, 2}`, changing the default value of the annotation type does not automatically change the value explicitly written at that site.

## 8. Special Cases for `float`, `double`, and Arrays

The `equals/hashCode` rules must remain consistent even with special floating-point values.

~~~java
double positiveZero = 0.0d;
double negativeZero = -0.0d;

System.out.println(positiveZero == negativeZero);
System.out.println(Double.valueOf(positiveZero)
                         .equals(Double.valueOf(negativeZero)));
~~~

**Output:**

~~~text
true
false
~~~

This is a fragment runnable inside a method. For an annotation element of type `double`, the equality contract uses wrapper `Double.equals`, so `+0.0d` and `-0.0d` are **not** considered equal. A `double[]` array also uses `Arrays.equals(double[], double[])`, which distinguishes those two cases.

For `NaN`, `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` returns `true`, whereas `Double.NaN == Double.NaN` returns `false`. This rule helps an annotation's `equals()` preserve reflexivity and remain consistent with `Double`'s hash.

**Do not write** a generic comparator that only uses `==` on numeric elements; that approach is wrong for `float`/`double` in these special cases. It is best to use `annotation.equals(other)` directly, unless you are genuinely building tooling that needs to replicate the exact Java contract.

## 9. Why Should You Not Use `==` on Annotation Objects?

Applying `==` to two annotation objects checks **whether they share the same object reference**. It does not check whether they represent the same metadata.

~~~java
RoutePolicy a = FirstRoute.class.getAnnotation(RoutePolicy.class);
RoutePolicy b = SameRoute.class.getAnnotation(RoutePolicy.class);

System.out.println(a.equals(b)); // true
~~~

The fragment above uses the classes declared in the full example in Section 5. The two classes are different, yet the two annotation values are equivalent. Do not replace `a.equals(b)` with `a == b` to draw conclusions about the **meaning** of annotations.

Runtimes/JDKs may use proxy objects or implementation-specific objects to represent annotations. Therefore, `getClass()` on an annotation object is not a reliable way to determine the annotation type; the right method is `annotation.annotationType()`.

You should also not rely on `System.identityHashCode(annotation)` to compare annotation values. It serves object identity, which differs from `Annotation.hashCode()` defined in terms of the elements.

## 10. Can You Modify an Array Returned by an Annotation to Change `equals/hashCode`?

No. Annotations are metadata defined at compile time/written into the class file or generated by tooling according to the corresponding contract; **modifying a Java array returned by an element method is not a mechanism for updating the annotation attached in source code**.

Example illustrating the idea to avoid:

~~~java
RoutePolicy policy =
        FirstRoute.class.getAnnotation(RoutePolicy.class);

int[] copy = policy.ports();
copy[0] = 999; // Does NOT mean FirstRoute's metadata was modified
~~~

This fragment requires the definitions in Section 5. Typical runtime implementations protect an annotation's array values from external modification (for example, by returning a copy), and application logic **must not rely** on the ability to mutate the internal data of an annotation object.

If you need to create a mutable configuration, transfer the annotation data into an **independent** DTO/config object. When using arrays as keys in data structures, also be mindful: Java arrays themselves do not have content-based `equals/hashCode`, so you cannot use `int[]` directly as a content key in a `HashMap` and expect independent arrays with the same elements to be equal. You can use an appropriate immutable wrapper or canonical representation when designing the key.

## 11. Using Annotations in `HashMap` and `HashSet`

With the `equals/hashCode` contract, annotation objects can be used as keys in a `HashMap` or elements in a `HashSet`:

~~~java
Set<RoutePolicy> unique = new HashSet<>();
unique.add(first);
unique.add(same);
unique.add(reordered);
~~~

In the full example in Section 5, `first` and `same` have equivalent metadata and thus occupy only **one** logical entry; `reordered` is a different value, so the set has two entries.

However, business semantics should be considered:

- If you want to distinguish **which annotated class it originated from**, the annotation object is **not sufficient** as a key: the same annotation can appear on multiple classes.
- If you want to distinguish annotation configurations by **value**, using the annotation object with `equals/hashCode` is appropriate.
- If you want to compare array elements as an **unordered set**, the standard annotation contract does not meet that requirement. You must convert to a separate key with canonicalization/sorting rules, **without changing the Java semantics of `Annotation.equals`**.
- Do not store `hashCode` results as persistent identifiers in databases, files, or network protocols. A hash is a lookup aid, not a globally immutable identifier.

## 12. Common Pitfalls

**Pitfall 1 — using `==` to compare two annotation objects.** `==` checks object identity, not metadata. Use `equals()`.

**Pitfall 2 — using `int[].equals(...)` or `String[].equals(...)` to compare array elements.** Arrays do not override `Object.equals`; use `Arrays.equals` with the matching overload.

**Pitfall 3 — using `array.hashCode()` in the annotation hash formula.** Incorrect for array elements. You must use `Arrays.hashCode` by content.

**Pitfall 4 — omitting defaulted elements when computing the hash code.** Incorrect. Default values are part of the effective value and contribute to the hash like every other element.

**Pitfall 5 — assuming arrays with the same elements in different order are equal.** Incorrect. `Arrays.equals` compares position by position.

**Pitfall 6 — assuming `a.hashCode() == b.hashCode()` proves `a.equals(b)`.** Incorrect. Hash collisions can occur.

**Pitfall 7 — assuming `+0.0` and `-0.0` are equal in `float/double` elements because `==` returns `true`.** Incorrect. Annotation equality uses wrapper equality.

**Pitfall 8 — using `Arrays.deepEquals` because an array contains annotations.** Unnecessary; annotation elements can only be one-dimensional arrays, and nested annotations already have content-based `equals`.

**Pitfall 9 — printing `annotation.toString()` and comparing strings to conclude two annotations are equal.** You should not do this. `toString` formatting is implementation-dependent; `equals` is the official contract.

**Pitfall 10 — implementing `Annotation` yourself and writing `equals/hashCode` based on `Object` or using only a few elements.** If you build your own implementation, you must comply with the full contract of the `Annotation` interface, including all elements, arrays, defaults, and floating-point cases; omissions will break `HashSet`/`HashMap`.

## 13. Self-Check Exercises

**Exercise 1.** Two usages:

~~~java
@Endpoint(path = "/a")
class A1 {
}

@Endpoint(path = "/a", ports = {80, 443})
class A2 {
}
~~~

Suppose `Endpoint.ports()` has `default {80, 443}`. Are the two `Endpoint` objects read from the two classes equal?  
**Answer:** Yes. `ports` receives the same effective value, even when one site uses the default.

**Exercise 2.** If `ports` on the second class is changed to `{443, 80}`, what does `equals()` return?  
**Answer:** `false`, because the arrays are in different order. Do not assert with certainty that the two hash codes differ: two unequal values can still share the same hash.

**Exercise 3.** What is the formula for the contribution of the `int[] ports()` element?  
**Answer:** `(127 * "ports".hashCode()) ^ Arrays.hashCode(portsValue)`. Then add this contribution to the remaining elements.

**Exercise 4.** Does `new int[]{1, 2}.equals(new int[]{1, 2})` return `true`?  
**Answer:** No. The two arrays are different objects, and an array's `Object.equals` does not compare contents. Only `Arrays.equals(new int[]{1, 2}, new int[]{1, 2})` returns `true`.

**Exercise 5.** An annotation has an element `Nested[] checks()`. Do you need to use `Arrays.deepEquals`?  
**Answer:** No. Use `Arrays.equals(Nested[], Nested[])`, calling `equals()` on each `Nested` in turn; nested annotation comparison is performed recursively by element.

**Exercise 6.** Why are `+0.0d` and `-0.0d` two different values under `Annotation.equals` when they appear in a `double` element?  
**Answer:** The contract uses `Double.valueOf(x).equals(Double.valueOf(y))`, which distinguishes signed zero; primitive `==` is not used.

**Exercise 7.** If `A.equals(B)` is true, is `A.hashCode() == B.hashCode()` definitely true? What about the converse?  
**Answer:** The first direction is definitely true; the converse is not true due to hash collisions.

**Hands-on exercise:** Run `AnnotationHashDemo.java`. Then change `SameRoute` to `@RoutePolicy(route = "/v1", tags = {"stable", "public"})` and run it again. Predict `First equals Same`, `Equal hashes for equal annotations`, and `Unique annotation values`. Finally, revert `SameRoute` and try changing the `ratio` element on one site to `-0.0`, then check the difference compared with `ratio = 0.0`. Use `equals` to confirm semantics rather than guessing based on hashes.

## 14. Official References

- [Java SE 17 — `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): complete contract of `equals` and `hashCode` formula.
- [Java SE 17 — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `equals` and `hashCode` overloads for primitive and reference arrays.
- [JLS Java SE 17 §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): annotation type structure, valid element types, and defaults.
- [Java SE 17 — `java.lang.Object`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): general rules for `equals` and `hashCode` on objects.

In summary, treat each annotation as **a structured value**: same annotation type and **equal values for all elements** means they are equal. For arrays, **`Arrays.equals` and `Arrays.hashCode`** are the key pair of rules; the overall hash formula sums the **`(127 * name.hashCode()) ^ valueHash`** contribution of **all elements, including defaults**.
