# Comparing Primitive Fields and Reference Fields When Implementing `equals`

When manually implementing `equals(Object)` for a Java class, the core part is **comparing the fields that determine whether two objects have the same value according to the problem domain**. How you compare them depends on the field's type:

- For **primitive types** such as `int`, `long`, `boolean`, you usually use `==` to compare values directly. `float` and `double` require a clear decision on how to handle `NaN` and the sign of zero.
- For **reference types** such as `String`, custom classes, lists, or arrays, `==` checks whether two references point to the same object; to compare **value/content**, you must use the comparison appropriate for that type.
- `equals` of a class containing multiple fields usually combines the comparisons above, while also having to implement a consistent `hashCode`.

For example, two independent `UserProfile` objects with the same `age = 20` and `displayName = "Lan"` can be considered equal. Comparing `age` with `==` is right because it is an `int`; comparing `displayName` with `==` can be wrong because it is a `String`, and two strings with identical content can still be two different objects.

## 1. Primitive Fields: Value Comparison

Java primitive types include `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`. Their values reside directly in the field; there is no reference to a separate object for that primitive value.

| Field type | How to compare when implementing `equals` | What to know |
| --- | --- | --- |
| `byte`, `short`, `int`, `long` | `a == b` | Compares numeric values; there is no concept of two instances of an `int`. |
| `char` | `a == b` | Compares `char` values (UTF-16 code units), not normalized text comparison. |
| `boolean` | `a == b` | Equal when both are `true` or both are `false`. |
| `float` | Usually `Float.compare(a, b) == 0` | Distinguishes `+0.0f` from `-0.0f`; treats `NaN` values as equal under `Float`'s rules. |
| `double` | Usually `Double.compare(a, b) == 0` | Has the same special rules for `double`; easy to keep in sync with `Double.hashCode`. |

For `float`/`double`, **`==` is not syntactically wrong**, but its semantics differ from `Float.compare`/`Double.compare`:

~~~java
System.out.println(0.0 == -0.0);                         // true
System.out.println(Double.compare(0.0, -0.0) == 0);      // false
System.out.println(Double.NaN == Double.NaN);           // false
System.out.println(Double.compare(Double.NaN, Double.NaN) == 0); // true
~~~

If the class is designed following `Double`'s comparison semantics, use `Double.compare` in `equals` and `Double.hashCode` (or `Objects.hash` which boxes `double`) in `hashCode`. This is especially reasonable if you want `equals` to be consistent with `Double.equals`.

**Do not use an arbitrary `Math.abs(a - b) < epsilon` as a general `equals` definition:** the “difference smaller than threshold” relation is generally not transitive. For instance, when the threshold is `0.1`, `0.00` is close to `0.06`, `0.06` is close to `0.12`, but `0.00` is not close to `0.12`. This violates the `equals` contract. Use tolerance in a separate floating-point checking method when appropriate, rather than automatically applying it to `Object.equals`.

## 2. Reference Fields: Understanding the `equals` of the Field Type

A field of type `String`, `Integer`, `Address`, or `List<String>` holds a **reference** (or `null`). Inside `equals`:

- `a == b` is `true` if they share the same reference or both are `null`. It does not inspect the contents of two different objects.
- `a.equals(b)` calls the `equals` method of the left-hand object, but throws `NullPointerException` if `a == null`.
- `Objects.equals(a, b)` returns `true` when both are `null`, returns `false` when exactly one side is `null`, and when both are non-`null` calls `a.equals(b)`. This is a convenient, `null`-safe choice for most reference fields that have appropriate `equals` semantics.

Direct example:

~~~java
String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);                   // false
System.out.println(first.equals(second));              // true
System.out.println(java.util.Objects.equals(first, second)); // true
System.out.println(java.util.Objects.equals(null, null));     // true
System.out.println(java.util.Objects.equals(first, null));    // false
~~~

The two `new String(...)` statements in the example intentionally create two independent string objects to make the difference clear. In normal programs, there is no need to create `new String` from a literal just for comparison.

**`Objects.equals` does not automatically create a “deep comparison”.** It merely delegates to the field type's `equals`. If that type inherits `Object.equals` without overriding it, the result still reflects identity. For example, an `Address` class that does not override `equals` can cause two addresses containing identical fields to be treated as different.

### Choosing the Right Comparison for Each Reference Type

| Field type | Commonly appropriate comparison in the containing class's `equals` |
| --- | --- |
| `String` | `Objects.equals(name, that.name)` to compare content accurately and handle `null`. |
| Custom value class | `Objects.equals(address, that.address)`, **after** `Address.equals` has been properly defined. |
| `Integer`, `Long`, `Boolean` (wrappers) | `Objects.equals(boxed, that.boxed)` or appropriate value check; avoid `==` between two wrappers because caching/boxing can make results confusing. |
| `List` | `Objects.equals(list, that.list)`, if list semantics compare elements in the same order. |
| `Set` | `Objects.equals(set, that.set)`, if you want to compare the set of elements, independent of iteration order. |
| `Map` | `Objects.equals(map, that.map)`, if you want to compare corresponding key-value mappings. |
| Enum | `status == that.status` is appropriate because each enum constant is a unique instance. |
| Primitive array, e.g., `int[]` | `Arrays.equals(a, b)` to compare element by element. |
| One-dimensional object array, e.g., `String[]` | `Arrays.equals(a, b)` to compare elements using `Objects.equals`. |
| Nested array, e.g., `int[][]` | `Arrays.deepEquals(a, b)` if you need to compare the contents of sub-arrays rather than the identity of each sub-array. |

Comparisons for `List`, `Set`, and `Map` are only correct when the **element/key/value contract** is also correct. If an element is a class that does not override `equals`, a collection whose contents “look the same” may still not be `equals`.

### Specifically for Arrays

Java arrays inherit `Object.equals` and **do not override `equals` to compare element by element**. Therefore:

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a == b);                       // false
System.out.println(a.equals(b));                  // false
System.out.println(java.util.Objects.equals(a,b)); // false
System.out.println(java.util.Arrays.equals(a,b));  // true
~~~

`Arrays.equals` handles both arrays being `null`; if two arrays have the same length and corresponding elements are equal, the result is `true`. For arrays containing arrays, `Arrays.equals` only compares the inner array elements by reference; `Arrays.deepEquals` can descend into sub-arrays. If you choose `Arrays.deepEquals`, the corresponding `hashCode` must usually use `Arrays.deepHashCode`. With one-dimensional `Arrays.equals`, use `Arrays.hashCode`.

Understand the limitation: `Arrays.deepEquals` is meant for ordinary array trees; an array with a circular reference back to itself is not a situation where deep traversal should be expected to work safely.

## 3. Java 17+ Example: Combining Multiple Field Types in `equals`

Suppose two study plans having the same `level`, `active`, `rating`, `title`, topic list, and progress checkpoints are considered to have the same value. The fields are data of a **value object**; this is not an entity identity comparison rule for every system.

File **`CoursePlanEqualsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class CoursePlanEqualsDemo {

    static final class CoursePlan {
        private final int level;
        private final boolean active;
        private final double rating;
        private final String title;
        private final int[] checkpoints;
        private final List<String> topics;

        CoursePlan(int level, boolean active, double rating,
                   String title, int[] checkpoints, List<String> topics) {
            this.level = level;
            this.active = active;
            this.rating = rating;
            this.title = title; // Allows null; String is immutable.
            this.checkpoints = Arrays.copyOf(
                Objects.requireNonNull(checkpoints), checkpoints.length
            );
            this.topics = List.copyOf(Objects.requireNonNull(topics));
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CoursePlan that)) {
                return false;
            }
            return level == that.level
                && active == that.active
                && Double.compare(rating, that.rating) == 0
                && Objects.equals(title, that.title)
                && Arrays.equals(checkpoints, that.checkpoints)
                && Objects.equals(topics, that.topics);
        }

        @Override
        public int hashCode() {
            int result = Objects.hash(level, active, rating, title, topics);
            result = 31 * result + Arrays.hashCode(checkpoints);
            return result;
        }
    }

    public static void main(String[] args) {
        CoursePlan first = new CoursePlan(
            2, true, 4.5, new String("Objects"),
            new int[] {1, 3}, List.of("java", "junit")
        );
        CoursePlan second = new CoursePlan(
            2, true, 4.5, new String("Objects"),
            new int[] {1, 3}, List.of("java", "junit")
        );
        CoursePlan changed = new CoursePlan(
            2, true, 4.5, "Objects",
            new int[] {1, 4}, List.of("java", "junit")
        );

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first.equals(changed));
        System.out.println(first.equals(null));
        System.out.println(Objects.equals(null, null));

        Set<CoursePlan> plans = new HashSet<>();
        plans.add(first);
        plans.add(second);
        plans.add(changed);
        System.out.println(plans.size());

        System.out.println(
            Arrays.equals(new int[] {1, 3}, new int[] {1, 3})
        );
        System.out.println(Double.compare(+0.0, -0.0) == 0);
        System.out.println(Double.compare(Double.NaN, Double.NaN) == 0);
    }
}
~~~

Compile and run using JDK 17 or higher:

~~~bash
javac CoursePlanEqualsDemo.java
java CoursePlanEqualsDemo
~~~

Expected output:

~~~text
false
true
true
false
false
true
2
true
false
true
~~~

Checking each output:

1. `first == second` → `false` because two constructor calls create **two independent `CoursePlan` instances**.
2. `first.equals(second)` → `true`: primitive fields are equal; `String` has the same content; the two arrays are different instances but have identical elements; the two lists have elements in the same order.
3. The hashes of the two `CoursePlan` instances are equal because `hashCode` uses the same data as the basis that `equals` uses.
4. `first.equals(changed)` → `false` because `checkpoints` differs at the second element (`3` versus `4`).
5. `first.equals(null)` → `false` per the `equals` contract.
6. `Objects.equals(null, null)` → `true`.
7. `HashSet` has size `2`: `first` and `second` are treated as the same value; `changed` is a different value.
8. Two independent `int[]` arrays have the same elements, so `Arrays.equals` returns `true`.
9. `Double.compare(+0.0, -0.0) == 0` → `false`.
10. `Double.compare(Double.NaN, Double.NaN) == 0` → `true`.

In the constructor, `Arrays.copyOf` copies the array passed in by the caller so they cannot mutate the field's content through the original array reference. `List.copyOf` stores an unmodifiable list against element-modification operations on the list. Because the example list contains only immutable `String` elements, this design is suitable as a stable value object. `List.copyOf` does not allow `null` elements; that is a constraint chosen for the example, not a mandatory rule of `equals`.

Why does `hashCode` have two parts? `Objects.hash(...)` handles primitive fields via boxing and reference fields via their hash codes; however, **arrays need `Arrays.hashCode`** to hash the contents of each element. Combining via `31 * result + ...` ensures all components determining `equals` also contribute to the hash result.

## 4. Consistency Rules Between `equals` and `hashCode`

The `equals` contract requires reflexivity, symmetry, transitivity, consistency (when relevant data does not change), and `x.equals(null) == false` for `x != null`.

The `hashCode` contract requires:

> If `x.equals(y)` is `true`, then **`x.hashCode() == y.hashCode()` must be `true`**.

The converse is not required: two different values can have the same hash (collision).

In the example, `level`, `active`, `rating`, `title`, `checkpoints`, `topics` all affect `equals` and are all reflected in `hashCode`. Omitting `checkpoints` from the hash while still comparing it in `equals` **does not necessarily break** the “equal implies same hash” clause, though it can increase collisions. Conversely, hashing an extra field that does not participate in `equals` and differs between two objects considered equal will **violate the contract**.

To maintain stability, avoid modifying fields that participate in `equals`/`hashCode` while the object is a key in a `HashMap` or an element in a `HashSet`. If the hash changes after storage, lookup or removal operations can fail even though the reference is still inside the collection.

## 5. Common Mistakes and How to Fix Them

### Mistake 1: Using `==` for `String` or wrappers

~~~java
// Prone to error if content comparison is intended:
return age == that.age && name == that.name;

// Correct when name is String and may be null:
return age == that.age && Objects.equals(name, that.name);
~~~

`Integer` and other wrappers are also reference types. Some boxed values may be reused via caching; this does not make `==` a reliable value comparison for any two arbitrary wrappers. Use `Objects.equals` when comparing content and handling `null`.

### Mistake 2: Using `Objects.equals` on arrays expecting element comparison

~~~java
// Wrong goal: this still compares references of the two arrays.
Objects.equals(firstArray, secondArray);

// Correct for one-dimensional int[]:
Arrays.equals(firstArray, secondArray);
~~~

At the same time, use the corresponding `Arrays.hashCode` for one-dimensional arrays; for nested arrays use the pair `Arrays.deepEquals` / `Arrays.deepHashCode` when deep semantics are needed.

### Mistake 3: Calling `equals` on a nullable field

~~~java
// Risk of NullPointerException:
title.equals(that.title);

// Safe when one or both sides are null:
Objects.equals(title, that.title);
~~~

If the domain forbids `null`, you can also validate right in the constructor with `Objects.requireNonNull(title)` and then call `title.equals(that.title)`. Be consistent with the object's validity invariants.

### Mistake 4: Comparing too few or too many fields

If `equals` only compares `name` while two people with the same name are not necessarily the same person, the value definition may be wrong for the domain. Conversely, adding a transient descriptive field like `lastViewedAt` to `equals` of a value object that only cares about `id` can cause values that should be equal to be unnecessarily distinguished.

**Choose fields based on the meaning of the data type**, then make sure `hashCode` follows the same decision. Auto-generating methods in an IDE only prevents syntax errors; you must still review the field selection.

### Mistake 5: Ignoring subtypes and symmetry

For a class that can be inherited, having the superclass use `instanceof Parent` while the subclass compares an additional field can make `parent.equals(child)` differ from `child.equals(parent)`. A clear equality strategy must be designed. A simple choice for a **value object** is to use a `final` class, like `CoursePlan` above. If the class must remain open for inheritance, consider checking `getClass()` or another strategy, and test symmetry/transitivity; there is no single formula right for every inheritance model.

### Mistake 6: Misunderstanding `BigDecimal`, `String`, or collections

`BigDecimal("1.0")` and `BigDecimal("1.00")` may be numerically equivalent by `compareTo`, but `equals` returns `false` because it considers `scale` as well. Similarly, `String.equals` compares strings exactly, including uppercase/lowercase; if you want normalization before comparison, you must establish a clear rule and ensure that rule also applies consistently to the hash.

With collections, `Objects.equals` relies on the `equals` of the collection and its elements. `List` preserves order semantics; `Set` compares by elements regardless of iteration order; `Map` compares by key-value mappings. Do not automatically assume all collections are unordered sets of elements.

## 6. Process for Writing and Testing `equals`

1. **Define the meaning of “same value”.** Specify which fields participate in the comparison and whether it is a value object or an entity with its own identity.
2. **Check same reference:** `if (this == obj) return true;`.
3. **Check the input object:** `null` and incompatible types must yield `false`. For a `final` class, `instanceof YourClass that` is a clear way to write it in Java 17.
4. **Compare each field according to its type:** primitives usually `==`, `float/double` choose `Float.compare`/`Double.compare`, references use `Objects.equals` when appropriate, arrays use `Arrays.equals` or `Arrays.deepEquals`.
5. **Write the corresponding `hashCode`:** the same information that determines `equals` must produce the same hash; arrays specifically need `Arrays.hashCode` or `Arrays.deepHashCode`.
6. **Test essential cases:** same reference, two instances with the same data, one field changed, `null`, unrelated type, independent strings with the same content, independent arrays with the same elements, `NaN`/`±0.0` if `float/double` is present, and storing/looking up in `HashSet` or `HashMap`.
7. **Keep comparison state stable:** prefer immutable value objects; do not let arrays or collections change their content via unintended aliases.

A Java `record` automatically generates `equals` and `hashCode` based on its components, which is very convenient for many value objects. However, **a record containing an array does not automatically deep-compare array contents**; an array-typed component is still compared by reference semantics in the generated `equals`. Therefore, you still need to consider component types before choosing a record to represent a value.

## 7. Self-Check

1. A class has fields `int age` and `String name`. Why is `age == that.age` appropriate while `name == that.name` is insufficient to determine equal content?
2. Two independent `int[]` arrays contain `{1, 2, 3}`. Predict the results of `==`, `Objects.equals`, and `Arrays.equals`, then explain.
3. If two objects are equal according to `equals` but have different hashes, what can happen when putting them into a `HashSet`?
4. Why do `Double.compare(+0.0, -0.0)` and `+0.0 == -0.0` give different views of value?
5. If a `List<Address>` field is compared using `Objects.equals`, what `equals` semantics does the `Address` class need so that two independent address lists with the same data are considered equal?

**Key takeaway:** When implementing `equals`, compare **primitive values with a comparison suited to their type**, compare **reference fields through that object's `equals` semantics**, and handle **arrays separately with `Arrays` methods**. The same set of fields and comparison rules must be consistent with `hashCode`; that is the foundation for two independent objects with the same value to work properly in Java collections.