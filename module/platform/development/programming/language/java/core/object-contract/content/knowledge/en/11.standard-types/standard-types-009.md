# Do not generalize one standard class's rules to all other classes

## 1. Principle

In Java, the **general contract** of `equals()`, `hashCode()`, and `compareTo()` does not mean every standard class defines value equality in the same way. Observing that `String.equals()` compares content and then applying that assumption to `StringBuilder`, arrays, `BigDecimal`, or temporal types easily leads to bugs.

| Operation / API | What can be guaranteed | What must be checked per type |
|---|---|---|
| `==` (references) | Same object or both `null` | Whether literals/caches reuse instances |
| `equals()` | Reflexive, symmetric, transitive, consistent, non-`null` | Which fields or aspects constitute equality |
| `hashCode()` | If equals is true, hashes must match | Hashing scheme, collisions, participating fields |
| `Comparable` | Negative/0/positive result indicates before/equal/after | Whether the class has a natural order, whether `0` aligns with equals |
| `Comparator` | Ordering defined by the caller | Distinct values may still compare as `0` |
| Collection | Strictly follows the specific API contract | Duplicate rules, `null`, ordering, factories |

**Matching hashes do not prove equality**; `compareTo() == 0` also does not automatically imply `equals() == true`. Even among standard types, each class may deliberately choose different criteria.

## 2. `String`, `StringBuilder`, and custom classes

`String.equals` compares character sequences; `StringBuilder` inherits `Object.equals` and therefore compares identity. A custom class that does not override `equals` behaves the same way.

~~~java
String a = new String("Java");
String b = new String("Java");
StringBuilder x = new StringBuilder("Java");
StringBuilder y = new StringBuilder("Java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
System.out.println(x.equals(y)); // false
~~~

This is an illustrative snippet placed inside `main`. The difference comes from the **class contract**, not from both storing text. `String.equals` is case-sensitive; `"Java".equalsIgnoreCase("JAVA")` returns `true`, whereas `"Java".equals("JAVA")` returns `false`. `String.CASE_INSENSITIVE_ORDER` can even merge these strings inside a `TreeSet`. Do not use `==` for content comparison based on observations about string interning.

## 3. `BigDecimal` and numeric wrappers

~~~java
BigDecimal n1 = new BigDecimal("2.0");
BigDecimal n2 = new BigDecimal("2.00");
System.out.println(n1.equals(n2));       // false
System.out.println(n1.compareTo(n2) == 0); // true
~~~

Requires `java.math.BigDecimal`. `BigDecimal.equals` considers **scale** (1 versus 2), while `compareTo` considers numeric value. Therefore, `HashSet<BigDecimal>` can retain both, whereas `TreeSet<BigDecimal>` with natural order keeps only one. `String.compareTo == 0` is consistent with `String.equals`, yet **you must not extrapolate that rule to BigDecimal**.

Similarly, `Integer.valueOf(10).equals(Long.valueOf(10L))` returns `false`, despite both representing 10, because `Integer.equals` requires the exact wrapper type. For `Double`, `Double.NaN == Double.NaN` is `false` for primitives, yet two `Double`s holding `NaN` are equal via `Double.equals`. `Double.equals(-0.0, +0.0)` is not the API syntax; calling `equals` on the two wrappers returns `false`, whereas `-0.0 == +0.0` on primitives is `true`.

Do not infer object `equals` from arithmetic comparisons. When modeling monetary data, decide whether scale matters or only numeric quantity, then apply one consistent criterion across keys and collections.

## 4. Arrays, records, and collections

Java arrays do not override `Object.equals` by default: two `int[]` instances with identical elements are still unequal via `array.equals`. Use `Arrays.equals` to compare elements of one-dimensional arrays, and `Arrays.deepEquals` when deep comparison of `Object[]` with nested elements is needed.

A `record` generates `equals`/`hashCode` from its components, yet **an array component still compares by identity**; a record does not turn array components into deep equality.

Different collections behave differently:

- `List.equals` examines elements **in order**; an `ArrayList` can equal `List.of` with the same sequence of elements.
- `Set.equals` examines **same elements**, independent of iteration order; a `HashSet` can equal a `LinkedHashSet` with the same element set.
- `HashSet` uses `equals/hashCode` to detect duplicate elements; `TreeSet` uses `compareTo` or a comparator returning `0` to detect duplicate keys.
- `HashSet.add` with a duplicate element returns `false`, whereas the `Set.of` factory with duplicate elements **throws `IllegalArgumentException`**. `List.of` allows duplicate elements. `HashSet` can hold one `null`; the `Set.of` factory rejects `null`.

For example, a comparator based solely on length treats `"hi"` and `"ok"` as equivalent in a `TreeSet`, even though `String.equals` between them returns `false`. To retain both, use a comparator with a tie-breaker or a different collection.

## 5. Date-time: same instant, different equality

`OffsetDateTime.parse("2026-01-01T10:00:00+07:00")` and `OffsetDateTime.parse("2026-01-01T03:00:00Z")` represent the same instant on the timeline.

`isEqual()` between them is `true`; `equals()` is `false`, because `equals` checks the full representation including offset. If business logic asks **same instant**, use `isEqual` or compare `Instant`. If it asks **same OffsetDateTime value**, use `equals`. Do not use the contract of `LocalDate` or `Instant` to guess the behavior of `OffsetDateTime`/`ZonedDateTime`.

## 6. Runnable Java 17 program

Save as **`StandardContractsDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class StandardContractsDemo {
    record Box(int[] values) {}

    public static void main(String[] args) {
        String s1 = new String("Java");
        String s2 = new String("Java");
        System.out.println("String identity: " + (s1 == s2));
        System.out.println("String equals: " + s1.equals(s2));
        System.out.println("Builder equals: "
                + new StringBuilder("Java")
                .equals(new StringBuilder("Java")));

        System.out.println("Integer vs Long: "
                + Integer.valueOf(10).equals(Long.valueOf(10L)));
        System.out.println("Primitive NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("Wrapper NaN: "
                + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("Decimal equals: " + a.equals(b));
        System.out.println("Decimal compare zero: "
                + (a.compareTo(b) == 0));
        System.out.println("HashSet decimals: "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("TreeSet decimals: "
                + new TreeSet<>(List.of(a, b)).size());

        int[] x = {1, 2};
        int[] y = {1, 2};
        System.out.println("Array equals: " + x.equals(y));
        System.out.println("Arrays.equals: " + Arrays.equals(x, y));
        System.out.println("Record array equals: "
                + new Box(x).equals(new Box(y)));

        List<String> listA = List.of("a", "b");
        List<String> listB = new ArrayList<>(List.of("a", "b"));
        Set<String> setA = new HashSet<>(List.of("a", "b"));
        Set<String> setB = new LinkedHashSet<>(List.of("b", "a"));
        System.out.println("List across classes: "
                + listA.equals(listB));
        System.out.println("Set across classes: "
                + setA.equals(setB));

        TreeSet<String> byLength = new TreeSet<>(
                Comparator.comparingInt(String::length));
        byLength.add("hi");
        byLength.add("ok");
        System.out.println("TreeSet length only: " + byLength.size());

        System.out.println("String hash collision: "
                + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("Collision equals: "
                + "Aa".equals("BB"));

        OffsetDateTime hcm = OffsetDateTime.parse(
                "2026-01-01T10:00:00+07:00");
        OffsetDateTime utc = OffsetDateTime.parse(
                "2026-01-01T03:00:00Z");
        System.out.println("Date same instant: " + hcm.isEqual(utc));
        System.out.println("Date equals: " + hcm.equals(utc));

        try {
            Set.of("x", "x");
        } catch (IllegalArgumentException expected) {
            System.out.println("Set.of duplicate: rejected");
        }
    }
}
~~~

Run with JDK 17:

~~~bash
javac StandardContractsDemo.java
java StandardContractsDemo
~~~

Output:

~~~text
String identity: false
String equals: true
Builder equals: false
Integer vs Long: false
Primitive NaN: false
Wrapper NaN: true
Decimal equals: false
Decimal compare zero: true
HashSet decimals: 2
TreeSet decimals: 1
Array equals: false
Arrays.equals: true
Record array equals: false
List across classes: true
Set across classes: true
TreeSet length only: 1
String hash collision: true
Collision equals: false
Date same instant: true
Date equals: false
Set.of duplicate: rejected
~~~

The output only uses booleans/sizes; it does not rely on `HashSet`'s unguaranteed iteration order. `"Aa"` and `"BB"` are a real hash collision yet the two strings are not equal; a collision does **not** turn two logical elements into one.

## 7. How to apply and verify

When encountering a new standard class, **read the Javadoc of that exact class** instead of copying rules from a familiar one:

1. Determine whether `equals` uses identity, value, runtime type, ID, or specific fields; check `null`.
2. Verify `hashCode` uses the same data that determines equality. If an object already serves as a hash collection key, avoid mutating fields participating in equality/hash.
3. Check whether the class implements `Comparable` and whether `compareTo == 0` is consistent with `equals`. If passing a comparator, consider tie-breaking criteria.
4. Check collections/factories: `HashSet`, `TreeSet`, `List.of`, and `Set.of` have different contracts for duplicates, `null`, and ordering.
5. Test pairs of distinct instances with equal data; two numeric types; `BigDecimal` with different scales; nested arrays; `NaN`; same instant with different offsets; matching hashes with unequal values.
6. Pick the relation matching **business requirements**: comparing numbers regardless of scale may need `compareTo`; comparing instants needs `isEqual`/`Instant`; comparing array contents needs `Arrays.equals`.

## 8. Common mistakes

| Wrong assumption | Consequence | How to fix |
|---|---|---|
| Having the same fields makes objects automatically equal | Classes not overriding `equals` still use identity | Check the class contract, define a value object if needed |
| All text types behave like `String` | `StringBuilder.equals` still uses identity | Use the appropriate content comparison |
| Equal numbers mean wrappers are always equals | `Integer` differs from `Long`, BigDecimal checks scale | Choose types and comparison policies explicitly |
| `compareTo == 0` means `equals` | False for BigDecimal/custom comparators | Check the comparator's semantics |
| Equal hashes mean equal objects | Collisions are mistaken for duplicates | Check equality; never conclude from hashes |
| Records automatically deep-compare arrays | Two arrays with identical contents still have different identity | Redesign the component or override properly |
| All sets deduplicate the same way | Comparators or factories change the outcome | Read the specific API |
| Same instant means date-time `equals` | Different offsets can produce `equals false` | Compare instants when that is the goal |

## 9. Self-check questions

**1.** Two `StringBuilder("A")` instances have identical content yet `equals false`: does that contradict `String.equals`?  
**Answer:** No. The two classes have different contracts.

**2.** Why does `HashSet<BigDecimal>` keep both `2.0` and `2.00`, while `TreeSet<BigDecimal>` keeps only one?  
**Answer:** `equals` considers scale; `compareTo` considers numeric quantity.

**3.** Two arrays have identical elements yet `array.equals` is false; what should you use?  
**Answer:** `Arrays.equals` or `Arrays.deepEquals` appropriate for the structure.

**4.** Does a `TreeSet` comparator considering only length keep both `"hi"` and `"ok"`?  
**Answer:** No; the comparator returns `0`.

**5.** Is it valid for `OffsetDateTime.isEqual` to be true while `equals` is false?  
**Answer:** Yes; same instant, different offset representation.

**Remember:** General `Object` invariants are the foundation, while **the exact meaning of equality, hashing, ordering, and collection behavior must be verified for each class/API**.
