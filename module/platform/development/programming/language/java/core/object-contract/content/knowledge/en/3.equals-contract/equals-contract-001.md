# `equals()` Defines an Equivalence Relation on Non-`null` References

## 1. Purpose and Scope

In Java, `Object.equals(Object)` is the method by which an object answers the question: "Is this object considered equal to the other object according to the rules of the data type?". The default implementation in `Object` considers two references equal only when they point to **the same object**. A class with value semantics typically overrides `equals` so that two different objects are still equal when their corresponding meaningful properties are equal.

Consider the set `D` of **non-`null`** Java object references. Define the relation `~` on `D`:

- `x ~ y` if and only if `x.equals(y)` returns `true`.
- For `~` to truly be an **equivalence relation**, `equals` must be **reflexive, symmetric, and transitive**.
- The `Object.equals` contract also requires **consistency** provided the relevant state does not change, and that `x.equals(null)` is always `false` for `x != null`.

Note the distinction: the axioms of an *equivalence relation* apply to the **non-`null`** elements in `D`; the two requirements "consistent" and "non-null" are additions of the **`equals` method contract**, not two mathematical axioms of an equivalence relation.

## 2. The Five Conditions of the `equals` Contract

For non-`null` references `x`, `y`, and `z`:

| Condition | Expression / Statement | Meaning |
| --- | --- | --- |
| **Reflexive** | `x.equals(x) == true` | An object is always equal to itself. |
| **Symmetric** | `x.equals(y)` and `y.equals(x)` must give the same result | The order of the two objects must not determine the equality result. |
| **Transitive** | If `x.equals(y)` and `y.equals(z)` then `x.equals(z)` | Three objects cannot form an "equal, equal, yet not equal" chain. |
| **Consistent** | Multiple calls for the same pair of objects must give the same result, if the information used by `equals` does not change | The result must not depend randomly on the invocation, time, or extraneous state outside the equality definition. |
| **Non-null** | `x.equals(null) == false` | A reference to a real object is not equal to `null`. |

### Reflexive

`x.equals(x)` must be true even when `x` is a newly created object or belongs to a class with complex comparison logic. A common implementation technique is to check `this == other` first; however, this is only an optimization technique and does not replace designing the entire equality relation.

### Symmetric

If `a.equals(b)` is `true`, then `b.equals(a)` must also be `true`. Bugs often appear when a class accepts comparisons with another type that does not have a corresponding rule, or when a subclass changes the comparison criteria of its superclass.

Example of a **flawed design**: a `FlexibleText` class allows `equals` to accept a `String` with different letter casing. If `FlexibleText("java").equals("JAVA")` returns `true`, `"JAVA".equals(FlexibleText("java"))` still returns `false` because `String.equals` only accepts `String`. The two directions are not symmetric. The solution is to define the same type domain for both sides or use a separate comparison API (for example `equalsIgnoreCase`) if a different rule is desired.

### Transitive

Suppose a design compares two integers as equal when their distance is at most 1. Then `1 ~ 2` is true, `2 ~ 3` is true, yet `1 ~ 3` is false. This "nearly equal" rule is **unsuitable for implementing `equals`**. It can be a business check with a dedicated name such as `isNearTo`, but it cannot replace a transitive equality relation.

### Consistent and `null`

`equals` needs to rely on data that defines object semantics. If that data does not change, the result must not change on its own across calls. When the data used for comparison **actually changes**, the `equals` result is allowed to change; this is still risky when the object has already been used as a key in a hash structure.

`x.equals(null)` must return `false`. Conversely, `null.equals(x)` **cannot be invoked** and will throw a `NullPointerException`. Distinguish between those two expressions rather than phrasing it loosely as "`null` can compare itself".

## 3. Distinguishing `==`, `equals`, and `Objects.equals`

- For **object references**, `a == b` checks **reference identity**: whether both point to the same object (or both are `null`).
- `a.equals(b)` applies the **equality rule defined by `a`'s class**; it requires `a` to be non-`null`. If the class does not override `Object.equals`, the default behavior is identity comparison like `==`.
- `Objects.equals(a, b)` performs a `null`-safe check: if both are `null`, it returns `true`; if only one side is `null`, `false`; if `a` is non-`null`, it delegates to `a.equals(b)`.

`Objects.equals(null, null) == true` does not contradict `x.equals(null) == false`: the former expression is a utility comparing two potentially `null` references, while the latter is the contract of the method on **an actual object**.

Different methods or value domains may define different notions of equality. When discussing the contract in this lesson, always examine the result of **`equals(Object)`**, without substituting `==` or a similarly named method.

## 4. A Contract-Compliant Java 17+ Example

Design `Coordinate` as an **immutable value class** with two integer components `x` and `y`. Two coordinates are equal when both `x` and `y` are equal. Declaring it `final` makes it clear that the class has no subclasses adding comparison state.

Save the entire following program in the file `EqualsContractDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class EqualsContractDemo {
    static final class Coordinate {
        private final int x;
        private final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Coordinate that)) {
                return false;
            }
            return x == that.x && y == that.y;
        }

        @Override
        public int hashCode() {
            return 31 * x + y;
        }
    }

    public static void main(String[] args) {
        Coordinate a = new Coordinate(2, 5);
        Coordinate b = new Coordinate(2, 5);
        Coordinate c = new Coordinate(2, 5);
        Coordinate different = new Coordinate(2, 6);

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("reflexive: " + a.equals(a));
        System.out.println("symmetric: " + (a.equals(b) == b.equals(a)));
        System.out.println("transitive: "
                + (!a.equals(b) || !b.equals(c) || a.equals(c)));
        System.out.println("null: " + a.equals(null));
        System.out.println("different: " + a.equals(different));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));

        Set<Coordinate> coordinates = new HashSet<>();
        coordinates.add(a);
        System.out.println("set contains b: " + coordinates.contains(b));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 EqualsContractDemo.java
java EqualsContractDemo
```

Expected output:

```text
a == b: false
a.equals(b): true
reflexive: true
symmetric: true
transitive: true
null: false
different: false
same hash: true
set contains b: true
```

Step-by-step explanation:

1. `a` and `b` are created with two separate `new` expressions, so `a == b` is `false`; they have the same pair of coordinates, so `a.equals(b)` is `true`.
2. The `this == other` check quickly handles the self-comparison case and ensures reflexivity; the `instanceof Coordinate that` pattern (pattern matching available in Java 17) returns `false` when `other` is `null` or of a different type.
3. Comparing two `int` fields with `==` is appropriate because here they are **primitive values**. The equality definition does not depend on object addresses.
4. The "transitive" expression in the program checks one specific triple: if both premises are true, the conclusion must be true. A single example returning `true` **does not prove** all inputs satisfy the contract; systematic tests are still needed.
5. `HashSet.contains(b)` succeeds even though only `a` was added, because `a` and `b` are considered the same value and their hash codes are compatible.

## 5. The Contract Between `equals` and `hashCode`

When overriding `equals`, you must almost always override `hashCode` at the same time. The contract specifies:

- If `a.equals(b)` is `true`, it is **mandatory** that `a.hashCode() == b.hashCode()`.
- If `a.equals(b)` is `false`, the hash codes **may be the same or different**; hash collisions are valid.
- Within a single execution, repeated calls to `hashCode` on the same object must be consistent when the data used in `equals` does not change.

The coordinate example uses `31 * x + y`. This is a simple way to combine two `int` fields; Java integer overflow is well-defined and does not by itself violate the contract. Note that two different coordinates **can** produce the same hash, which does not make them equal. You may choose `Objects.hash(x, y)` when preferring a general-purpose approach, accepting a small extra cost.

`HashMap` and `HashSet` typically locate candidates in a bucket by `hashCode` and then use `equals` to decide equality. Violating the "equal ⇒ same hash" direction can cause `contains`, `get`, or duplicate-key detection to behave incorrectly. Even if `equals` is correct, modifying data that affects a key's hash **after inserting it** into a hash structure can prevent lookups from finding it. Therefore, prefer **immutable** keys.

## 6. Choosing Fields and Type Domains to Compare

A good implementation first answers two questions: **what defines value identity** and **which types are allowed to be considered equal**?

For example, a book entry has an `isbn` field and a display description `displayTitle`: if the domain identifies books by ISBN, two objects with the same ISBN can still be equal even if their display titles differ. Conversely, a `(x, y)` coordinate must use both components. Choose criteria consistent with the meaning of the data rather than automatically including every field in the comparison.

### Inheritance and the Symmetry/Transitivity Problem

If `Point` compares `x, y`, while `ColorPoint extends Point` wants to also compare `color`, it is very easy to get two contradictory results: `Point.equals(ColorPoint)` accepts because the coordinates match, whereas `ColorPoint.equals(Point)` rejects because there is no color. Trying to allow all directions can instead break transitivity between two differently colored points and a colorless point.

Options depending on semantics:

- Use a `final` value class when the design does not need inheritance: the simplest way to keep a stable `equals` rule.
- Use `getClass() == other.getClass()` when you want **equality only within the exact same runtime class**, applied consistently across the class hierarchy; this intentionally does not consider superclass and subclass instances equal.
- If equality across classes in an inheritance relationship is genuinely required, a common rule must be designed for all sides and all properties must be verified. Do not mechanically swap `instanceof` for `getClass`.

In the example, `Coordinate` is `final`, so the `instanceof Coordinate` pattern is both concise and clearly defines the set of objects that can be equal.

### Cases Requiring Attention

- **Java arrays:** two separate arrays with the same elements are still not equal under `array1.equals(array2)` (inherited reference comparison). Use `Arrays.equals` for one-dimensional arrays, or `Arrays.deepEquals` for nested arrays requiring deep comparison.
- **`BigDecimal`:** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false` because `equals` also considers scale; whereas `compareTo` may return `0`. Different ordering and `equals` rules can lead to differences between `TreeSet` and `HashSet`.
- **Floating-point numbers:** `double` has `NaN`, `-0.0`, and `+0.0`; avoid directly choosing an "epsilon tolerance" criterion for `equals` because it easily violates transitivity. When representing floating-point values under a consistent contract, consider `Double.compare` / `Double.hashCode` or a normalization rule appropriate for the data domain.
- **`record`:** Java automatically generates `equals` and `hashCode` based on the record's components. This is a useful starting point for value modeling, but components referencing mutable objects still need consideration regarding effective immutability.

## 7. Two Counterexamples to Spot Design Flaws

### Broken Symmetry: Comparing Across Different Types

The following **abbreviated illustration, not a standalone Java program** assumes class `FlexibleText` has a `String value` field:

```java
@Override
public boolean equals(Object other) {
    if (other instanceof FlexibleText text) {
        return value.equalsIgnoreCase(text.value);
    }
    if (other instanceof String text) {
        return value.equalsIgnoreCase(text); // WRONG: String.equals does not accept FlexibleText
    }
    return false;
}
```

With `FlexibleText("java")` and `"JAVA"`, calling from the `FlexibleText` side may return true while the reverse direction returns false. Do not use this rule as `equals`. If you want case-insensitive string checks, expose a separate business method or normalize the data before creating a value type with a unified comparison domain.

### Broken Transitivity: "Nearly Equal"

Suppose `NearbyNumber.equals` returns `true` when the absolute difference between two values is at most `1`. When the values are `1`, `2`, and `3`:

```text
1 ~ 2: true
2 ~ 3: true
1 ~ 3: false
```

Both premises are true yet the conclusion is false, so the relation is not transitive. Testing only a single pair may miss the bug; you need to test a **triple**. If the application needs a "nearby" notion, write a method like `withinDistance(other, tolerance)` and do not declare it as `equals`.

## 8. How to Test the Contract

For your value class, prepare at least three objects with the same value created independently (`a, b, c`), an object with a different value (`d`), an object of a different type, and `null`. Verify:

1. `a.equals(a)` is true; likewise for other valid objects.
2. `a.equals(b) == b.equals(a)`; test both equal and unequal pairs, including different types.
3. If `a.equals(b) && b.equals(c)` then `a.equals(c)`; test multiple triples, especially when inheritance or rounding is involved.
4. Calling on the same pair repeatedly while relevant fields are unchanged yields the same result.
5. `a.equals(null)` is false; different-type checks return `false` without invalid casts.
6. For every equal pair, hash codes must be equal; also test real usage in `HashSet` and `HashMap`.
7. If the class allows state mutation, clearly identify which fields affect `equals`/`hashCode` and avoid using objects with changing hashes as keys.

The check statements in `main` above are behavioral observation examples, not complete verification. For libraries or critical domain models, write property-based unit tests across varied inputs, especially testing superclass/subclass pairs and boundary values where applicable.

## 9. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing `equals(Coordinate other)` instead of `equals(Object other)` | This is an **overload**, not an override of `Object.equals`; collections calling `equals(Object)` keep the old behavior. | Use `@Override public boolean equals(Object other)`; the annotation helps the compiler catch an incorrect signature. |
| Comparing reference fields with `==` when value comparison is needed | Two objects with identical content may be treated as different. | Use `Objects.equals(field1, field2)` or `field.equals(...)` when guaranteed non-`null`. |
| Forgetting to check `null`/type before casting | Can throw `NullPointerException` or `ClassCastException` during comparison. | Check `this == other` and `instanceof` (or class check) before reading the other object's fields. |
| Overriding `equals` without overriding `hashCode` accordingly | Hash structures may mishandle two equal keys. | Use the same set of significant fields for both methods. |
| Adding equality conditions only in a subclass | Can break symmetry/transitivity when compared against the superclass. | Choose a clear type domain and inheritance policy; prefer a `final` value class when appropriate. |
| Using an approximation threshold as `equals` | Can break transitivity. | Separate the "nearly equal" operation into its own method. |
| Using mutable key fields in `hashCode` | Lookups in `HashMap`/`HashSet` may fail after modification. | Use immutable keys or do not mutate comparison fields while stored in a hash structure. |

## 10. Key Takeaways

A valid `equals(Object)` on non-`null` objects must form an **equivalence relation**: reflexive, symmetric, and transitive. The Java contract also requires consistency when comparison data does not change and `x.equals(null) == false`. When defining value-based equality, ensure `hashCode` is compatible. The most important part of implementing it is defining **the right equality semantics and type domain**, then testing with both pairs and triples of objects rather than a single example with an expected result.