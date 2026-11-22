# `Comparator.equals()` Differs from `compare() == 0` for Two Elements

## 1. Two Calls with Different Meanings

In Java, `Comparator<T>` represents **a rule for comparing and ordering objects of type `T`**. This interface declares the core method `int compare(T a, T b)` and has the `boolean equals(Object obj)` method inherited from `Object`; a comparator class **may** override `equals` to define when two **comparators** are equivalent.

The crucial point is that **the objects being compared are different**:

- `comparator.compare(a, b) == 0`: asks **whether two elements `a` and `b` tie in the order defined by the comparator**. The result does not directly state that `a.equals(b)` is `true`.
- `comparator.equals(otherComparator)`: asks **whether the current comparator object equals another comparator object**. This is an `equals(Object)` call on the comparator itself, not an equality check between two data elements.

Brief example:

~~~java
Comparator<String> comparator = String.CASE_INSENSITIVE_ORDER;
boolean samePosition = comparator.compare("Java", "JAVA") == 0;
boolean sameValue = "Java".equals("JAVA");
~~~

`samePosition` is `true` because the comparator is case-insensitive; `sameValue` is `false` because `String.equals` is case-sensitive. Meanwhile, `comparator.equals(anotherComparator)` is a question about **two sorting strategies**.

**Do not conflate these expressions**:

| Expression | Subjects compared | Meaning |
| --- | --- | --- |
| `a == b` | Two element references | Whether they are the exact same object |
| `a.equals(b)` | Two elements | Whether they are equal under the element's `equals` contract |
| `c.compare(a, b) == 0` | Two elements via comparator `c` | Whether they are equivalent in the **order defined by `c`** |
| `c.equals(d)` | Two comparators `c` and `d` | Whether the comparators consider themselves equal comparators |

## 2. Negative, Zero, and Positive Values of `compare(a, b)`

`compare(a,b)` returns a negative number if `a` comes before `b`, a positive number if `a` comes after `b`, and `0` if the two elements belong to the same equivalence group under the **chosen rule**. Returning exact `-1` or `1` is not required, nor does a comparison result of 0 mean `a.equals(b)` must be `true`.

~~~text
a ~ b  ⇔  comparator.compare(a, b) == 0
~~~

For example, a comparator by length returns `0` for `"cat"` and `"dog"`, even though `String.equals` returns `false`. The contract still requires flipping sign when swapping arguments, transitivity, and a consistent relation with every third element; the mathematical details are in the lesson on the sign contract and 0-groups.

The special point to remember in **this lesson** is that `comparatorA.equals(comparatorB)` does not use `compare(a,b)` at all to check equality of **two elements**. It asks whether two *comparator objects* are equal; its exact meaning is analyzed in the next section.
## 3. Runnable Example: Order Equivalence Differs from `String` Equality

Create the file `ComparatorZeroDemo.java`:

~~~java
import java.util.Comparator;

public class ComparatorZeroDemo {
    public static void main(String[] args) {
        Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;

        String a = new String("Java");
        String b = new String("JAVA");
        String c = "Spring";

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("compare(a,b)==0: " + (ignoreCase.compare(a, b) == 0));
        System.out.println("compare(a,c)<0: " + (ignoreCase.compare(a, c) < 0));
        System.out.println("compare(c,a)>0: " + (ignoreCase.compare(c, a) > 0));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 ComparatorZeroDemo.java
java ComparatorZeroDemo
~~~

Stdout:

~~~text
a == b: false
a.equals(b): false
compare(a,b)==0: true
compare(a,c)<0: true
compare(c,a)>0: true
~~~

Analysis:

1. `new String("Java")` and `new String("JAVA")` create two separate String objects.
2. `String.equals` is case-sensitive and therefore returns `false`.
3. `String.CASE_INSENSITIVE_ORDER` ignores case differences when comparing, so `compare(a,b)` returns `0`.
4. For `"Java"` and `"Spring"`, case-insensitive order still places `Java` before `Spring`.

The results above demonstrate that **equivalence in a comparator does not imply equality under an element's `equals`**.

## 4. What Does `Comparator.equals(Object)` Actually Compare?

`Comparator.equals(Object)` carries the contract of `Object.equals` (reflexive, symmetric, transitive, consistent, and never equal to `null`). The `Comparator` documentation further states a special meaning if a comparator **explicitly defines** equality: two comparators considered equal must impose **the same ordering**, meaning the signs of corresponding `compare` results are identical for every pair of elements in the comparison domain.

There are two important cases:

**Case 1: the comparator does not override `equals`.** The inherited `Object.equals` method usually returns `true` only when comparing **the exact same comparator instance**. Two distinct instances implementing the exact same comparison algorithm can still return `false` from `equals`. That is valid: a comparator is not required to compare equal based on "having the same algorithm code."

**Case 2: the comparator class explicitly overrides `equals`.** A class may treat two comparators as equal if they hold the same configuration and are guaranteed to produce the same ordering rule. If `equals` is overridden, `hashCode` must be overridden correspondingly per the object contract. An `equals` result of `true` must suffice to guarantee they impose the same order; conversely, **two comparators with identical comparison behavior are not required to return `true` from `equals`**.

You cannot merely test a few pairs of data and declare two comparators equivalent for all values. The ordering contract is a requirement over **the entire domain of values they support**.

### Runnable example: two comparators with the same algorithm yet not `equals`

Create the file `ComparatorIdentityDemo.java`:

~~~java
import java.util.Comparator;

public class ComparatorIdentityDemo {
    static final class ByLength implements Comparator<String> {
        @Override
        public int compare(String a, String b) {
            return Integer.compare(a.length(), b.length());
        }
        // Does not override equals(Object): inherits Object.equals.
    }

    public static void main(String[] args) {
        ByLength first = new ByLength();
        ByLength second = new ByLength();

        System.out.println("same comparator object: " + (first == second));
        System.out.println("comparators equal: " + first.equals(second));
        System.out.println("first compares: " + first.compare("dog", "cat"));
        System.out.println("second compares: " + second.compare("dog", "cat"));
        System.out.println("element objects equal: " + "dog".equals("cat"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorIdentityDemo.java
java ComparatorIdentityDemo
~~~

Stdout:

~~~text
same comparator object: false
comparators equal: false
first compares: 0
second compares: 0
element objects equal: false
~~~

The two `ByLength` instances are separate comparator objects, so `first.equals(second)` is `false`. Both see `"dog"` and `"cat"` as having the same length, so `compare(...)` returns `0`. That **does not allow concluding** that `first.equals(second)` must be `true`; it also shows that `compare == 0` has no direct link to `String.equals`.

## 5. Example Overriding `Comparator.equals` Based on Ordering Configuration

When an application has a well-defined comparator kind with configuration parameters determining the order, you can define `equals/hashCode` for **the comparator object**.

Create the file `ConfiguredComparatorDemo.java`:

~~~java
import java.util.Comparator;

public class ConfiguredComparatorDemo {
    static final class ByRemainder implements Comparator<Integer> {
        private final int divisor;

        ByRemainder(int divisor) {
            if (divisor <= 0) {
                throw new IllegalArgumentException("divisor must be positive");
            }
            this.divisor = divisor;
        }

        @Override
        public int compare(Integer a, Integer b) {
            return Integer.compare(
                    Math.floorMod(a, divisor),
                    Math.floorMod(b, divisor)
            );
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ByRemainder other)) return false;
            return divisor == other.divisor;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(divisor);
        }
    }

    public static void main(String[] args) {
        ByRemainder by10a = new ByRemainder(10);
        ByRemainder by10b = new ByRemainder(10);
        ByRemainder by5 = new ByRemainder(5);

        System.out.println("same instance: " + (by10a == by10b));
        System.out.println("same comparator configuration: "
                + by10a.equals(by10b));
        System.out.println("matching comparator hashes: "
                + (by10a.hashCode() == by10b.hashCode()));
        System.out.println("different configuration: " + by10a.equals(by5));
        System.out.println("12 versus 22: " + by10a.compare(12, 22));
        System.out.println("12.equals(22): " + Integer.valueOf(12).equals(22));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConfiguredComparatorDemo.java
java ConfiguredComparatorDemo
~~~

Stdout:

~~~text
same instance: false
same comparator configuration: true
matching comparator hashes: true
different configuration: false
12 versus 22: 0
12.equals(22): false
~~~

In this example, two comparators with the same `divisor` always apply the exact same formula so `equals` can return `true`, and `hashCode` is based on that same field. Yet the two numbers `12` and `22` remain **two unequal Integers**, even though both have remainder 2 modulo 10 and the comparator returns 0.

`ByRemainder` intentionally inspects only the remainder and is therefore **inconsistent with `Integer.equals`**. This is a group/remainder ordering, not natural integer order. Do not apply this kind of comparator to a `TreeSet<Integer>` if you want the set to hold **every distinct integer**.

Note that `compare` in the example requires non-`null` `Integer` arguments (unboxing into `Math.floorMod` can throw `NullPointerException` if passed null). If null support is needed, wrap the comparator with `Comparator.nullsFirst` or `Comparator.nullsLast` with an appropriate policy.

## 6. "Consistent with equals" Is a Property of the Ordering Relation

An ordering defined by a `Comparator` is said to be **consistent with the elements' `equals`** when, for all `a`, `b` in the comparison domain:

~~~text
comparator.compare(a, b) == 0  ⇔  a.equals(b)
~~~

This is a relation between **`compare` and the elements' `equals`**, completely separate from `comparator.equals(otherComparator)`.

Examples:

- `Comparator.naturalOrder()` on `Integer` has a `compare(a,b)==0` relation matching `Integer.equals`.
- `String.CASE_INSENSITIVE_ORDER` is **not** consistent with `String.equals` because `"Java"` and `"JAVA"` have equal ordering yet `equals` is `false`.
- `Comparator.comparingInt(String::length)` is not consistent with `String.equals` because two distinct strings can still have the same length.
- A comparator checking only `Person.id` is consistent with `Person.equals` only if Person's `equals` also defines equality strictly by `id` across the entire object domain.

A comparator inconsistent with `equals` is not always a bug. It fits **grouping sorts, case-insensitive comparison, or bucketing values with the same key**. Yet when used in collections that determine uniqueness via order comparison, the difference has major consequences.

### Separating equality relations from sort precedence

If you want to sort by length yet **not** treat two equal-length strings as a single unique value, you can add a secondary criterion:

~~~java
Comparator<String> byLengthThenNatural =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
~~~

This snippet is an **illustrative fragment in a context that already has `import java.util.Comparator;`**, not a standalone program file. `thenComparing` applies the second comparison only when the length criterion returns 0. For two different strings `"dog"` and `"cat"`, the secondary criterion distinguishes them. On String, this combined comparison is consistent with `String.equals`: returning 0 only when string contents match (over the non-null domain). For other element types, choose a secondary criterion that genuinely distinguishes objects that `equals` treats as different.

## 7. Consequences for `TreeSet`

`TreeSet` is a sorted set. When constructed with a comparator, it uses order comparison results to decide element placement and **duplication**: if `compare(a,b)==0`, the set treats them as the same element in the tree structure.

Create the file `TreeSetComparatorDemo.java`:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetComparatorDemo {
    public static void main(String[] args) {
        Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;

        Set<String> tree = new TreeSet<>(ignoreCase);
        System.out.println("tree first add: " + tree.add("Java"));
        System.out.println("tree second add: " + tree.add("JAVA"));
        System.out.println("tree size: " + tree.size());
        System.out.println("tree contains java: " + tree.contains("java"));
        System.out.println("tree first element: " + tree.iterator().next());

        Set<String> hash = new HashSet<>();
        hash.add("Java");
        hash.add("JAVA");
        System.out.println("hash size: " + hash.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 TreeSetComparatorDemo.java
java TreeSetComparatorDemo
~~~

Stdout:

~~~text
tree first add: true
tree second add: false
tree size: 1
tree contains java: true
tree first element: Java
hash size: 2
~~~

Explanation:

1. `TreeSet` inserts `"Java"` into the set.
2. When adding `"JAVA"`, the case-insensitive comparator returns 0 against `"Java"`, so `TreeSet` treats it as already present and `add` returns `false`.
3. The set still holds the first element `"Java"`; `contains("java")` returns `true` according to the comparator.
4. `HashSet` uses `String`'s `hashCode` and `equals`; the two strings differ in letter case, so both are stored.

**Key design point:** Sorted set classes operate faithfully according to the **comparator's rules**, but to fully satisfy the `Set` contract regarding element equality, the ordering must be **consistent with `equals`**. When a comparator is inconsistent, the sorted set's behavior remains well-defined by tree structure yet diverges from typical `Set` intuition and can violate the general `Set` contract for `equals`-based sets.

Using `TreeSet` with an inconsistent comparator makes sense when you **genuinely want to merge elements belonging to the same order class**. If you want to sort by one field while keeping all distinct objects, add a consistent tie-breaking criterion.

## 8. Similar Consequences for `TreeMap`

`TreeMap` uses a comparator to order **keys** and decide when two keys are treated as equivalent. If the comparator returns 0, a `put` operation for a new key can **overwrite the value** of an existing entry, even though `key1.equals(key2)` is `false`.

Create the file `TreeMapComparatorDemo.java`:

~~~java
import java.util.Map;
import java.util.TreeMap;

public class TreeMapComparatorDemo {
    public static void main(String[] args) {
        Map<String, String> map =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        System.out.println("first put: " + map.put("Java", "first"));
        System.out.println("second put: " + map.put("JAVA", "second"));
        System.out.println("size: " + map.size());
        System.out.println("lookup java: " + map.get("java"));
        System.out.println("original key kept: " + map.keySet().iterator().next());
        System.out.println("key equals: " + "Java".equals("JAVA"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 TreeMapComparatorDemo.java
java TreeMapComparatorDemo
~~~

Stdout:

~~~text
first put: null
second put: first
size: 1
lookup java: second
original key kept: Java
key equals: false
~~~

The `put("JAVA", "second")` call finds a key order-equivalent to `"Java"`, so it updates the **value** of that entry instead of inserting a new entry. The original key stored in the tree remains `"Java"` in the example. Consequently:

- `TreeMap` has one entry instead of two.
- `get("java")` retrieves the new value `"second"`.
- `String.equals("Java","JAVA")` is still `false`.

Like `TreeSet`, `TreeMap` obeys the supplied comparator; to fully adhere to the general `Map` contract based on key `equals`, the comparator must be consistent with `equals`.

## 9. What Happens with `sort`, `min/max`, or `binarySearch`?

In **sorting** (`List.sort`, `Arrays.sort`, `Collections.sort`), the comparator determines order only. Two elements for which `compare` returns 0 can still be two separate objects and both remain present in the list after sorting. Sorting does not merge elements.

For instance, a list containing `"Java"` and `"JAVA"` after `sort(String.CASE_INSENSITIVE_ORDER)` still has **two elements**. Sorting stability is documented for specific APIs—for example, `List.sort` guarantees not to reorder elements that the comparator considers equal.

Similarly:

- `Collections.min/max` with a comparator picks an extremum **under the comparator's order**; an extreme element does not necessarily equal another element in the same order class under `equals`.
- `Collections.binarySearch(list, key, comparator)` can match an element where `compare(found,key)==0`, without needing `found.equals(key)`; the list must already be sorted by a matching comparator. If multiple order-equivalent matches exist, no specific index is guaranteed.

### Runnable example: a list does not merge elements

Create the file `SortKeepsElementsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortKeepsElementsDemo {
    public static void main(String[] args) {
        Comparator<String> byLength =
                Comparator.comparingInt(String::length);

        List<String> words = new ArrayList<>(
                List.of("dog", "a", "cat")
        );
        words.sort(byLength);

        System.out.println("sorted: " + words);
        System.out.println("size: " + words.size());
        System.out.println("dog vs cat: " + byLength.compare("dog", "cat"));
        System.out.println("dog equals cat: " + "dog".equals("cat"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SortKeepsElementsDemo.java
java SortKeepsElementsDemo
~~~

Stdout:

~~~text
sorted: [a, dog, cat]
size: 3
dog vs cat: 0
dog equals cat: false
~~~

Both equal-length strings are retained. `List.sort` is **sorting**, whereas `TreeSet` applies order equivalence to element **uniqueness**.

## 10. How to Build a Comparator Matching Business Intent

### When you need to group elements by a key

If the business domain treats case-insensitive names as the same key, `String.CASE_INSENSITIVE_ORDER` with `TreeMap` or `TreeSet` may fit. Document clearly that uniqueness is by **normalized key** or **comparator-defined equivalence class**; do not confuse this with `String.equals`.

If you want precise control over normalization, consider converting data into a dedicated key type whose `equals/hashCode` reflect that relation, such as a wrapper holding a consistently normalized name. With natural and multilingual text, Unicode normalization/comparison, locale, and casing rules must be explicitly designed; never assume every string comparison shares the same contract.

### When you need to preserve every distinct element

The comparator should have a **tie-breaker** to distinguish elements that differ under `equals`. For String:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
~~~

For custom classes, if `equals` is based on `id`, you can append `id` comparison as a tie-breaker (provided `id` carries suitable semantics). However, **do not use `System.identityHashCode` as a sole tie-breaker** to guarantee distinguishing every object: hashes can collide. Nor can you blindly tack on arbitrary secondary criteria and assume the comparator is consistent with every `equals` definition.

### When you want to check whether two comparators are equal

Use `comparatorA.equals(comparatorB)` when the target is **genuinely the comparator objects**; a `false` result may simply mean they are two different instances. In many applications, there is no need to test equality of two comparators: simply choose one comparator and reuse it.

If building a **configurable comparator class** and wanting to use it as a cache/configuration key, you can implement `equals` and `hashCode` based on the parameters that define the ordering. This is a design choice **independent** of the `compare(a,b)==0` rule on data elements.

## 11. Common Confusions

| Confusion | Reality |
| --- | --- |
| `c.equals(d)` is equivalent to `c.compare(a,b)==0`. | Both sides have **different comparison subjects**: comparator vs comparator, element vs element. |
| `compare(a,b)==0` implies `a.equals(b)` is always `true`. | Only true when the comparator is **consistent with equals** over the relevant element domain. |
| Two comparators using the same algorithm always have `c.equals(d) == true`. | Not necessarily: `equals` may be inherited from `Object` and check instance identity. |
| `c.equals(d)==false` means there exists a pair of elements ordered differently by the two comparators. | False: `equals` returning false **does not prove** the two comparators produce different orderings. |
| A comparator must return exact `-1`, `0`, `1`. | The contract only specifies negative/0/positive signs. |
| `TreeSet` checks duplicates using `a.equals(b)`. | With a supplied comparator, the tree uses `compare(a,b)==0` to determine order equivalence. |
| `TreeMap.put` with two keys having different `equals` always creates two entries. | There can be only one entry if the comparator considers them equivalent (`compare==0`). |
| `sort` drops elements with `compare==0`. | Sorting does not merge elements; the list keeps its count. |
| Adding a hash-based tie-breaker always yields a valid total order. | Hashes can collide; a secondary criterion aligned with object semantics is needed. |
| `Comparator.equals` must be overridden in every comparator. | Not required; inheriting `Object.equals` is valid. |

## 12. Design Review Checklist

When writing or using a `Comparator<T>`:

1. Identify the **sorting rule** of `compare(a,b)` and which fields participate.
2. Ask explicitly: should two elements for which `compare` returns 0 be treated as **the same key**, or merely the same priority/group?
3. Cross-check against `a.equals(b)`: is the comparator **consistent with equals** over its usage domain?
4. If using `TreeSet`/`TreeMap`, carefully verify the case `compare(a,b)==0` yet `a.equals(b)==false` to avoid accidentally merging elements or overwriting values.
5. If only sorting a List, do not assume two elements with `compare==0` will be removed or merged.
6. With multiple criteria, use `Comparator.comparing(...).thenComparing(...)` and select tie-breakers matching intended semantics.
7. Ensure the comparator obeys sign rules, transitivity, and consistency of equivalent elements; avoid writing `return a - b` for `int` since overflow can yield wrong results, and use `Integer.compare(a,b)`.
8. If a comparator has state or configuration that changes while used by a `TreeSet`/`TreeMap`, the tree's ordering can become invalid; keep comparison configuration **stable** throughout its usage lifecycle.
9. Evaluate `comparatorA.equals(comparatorB)` only when genuinely comparing **two comparators**. If overriding this method yourself, ensure a `true` result implies the same ordering and preserve the contract with `hashCode()`.

**Takeaway:** `Comparator.equals(Object)` answers whether **two comparator objects** are considered equal; `Comparator.compare(a,b)==0` answers whether **two elements** are equivalent under an ordering rule. The latter coincides with `a.equals(b)` only when the comparator is consistent with equals. Distinguishing these relations helps avoid subtle bugs with `TreeSet`, `TreeMap`, and defining data uniqueness.