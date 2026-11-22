# Recommended Consistency Between `compareTo() == 0` and `equals()`

## 1. Understanding the two concepts of "equality" properly

In Java, an object can participate in **two independent comparison mechanisms**:

- **`equals(Object)`** returns a `boolean` to determine whether two objects are logically equal. This is the general `Object` contract; collections such as `HashSet` and `HashMap` use it alongside `hashCode()` to identify elements/keys.
- **`compareTo(T)`** returns a negative, 0, or positive `int` to define the natural ordering of objects implementing `Comparable<T>`. Ordered collections such as `TreeSet` and `TreeMap` use this comparison, or a provided `Comparator`.

The `Comparable` contract **strongly recommends** that natural ordering be consistent with `equals`, meaning:

```java
x.compareTo(y) == 0   // should be equivalent to
x.equals(y)           // true
```

This is an illustrative expression snippet, assuming `x` and `y` have the appropriate same type and are non-`null`.

Written precisely in logic:

```text
x.compareTo(y) == 0  ⇔  x.equals(y) == true
```

The `⇔` symbol means **both directions hold**:

1. If `compareTo` returns 0 then `equals` should return `true`.
2. If `equals` returns `true` then `compareTo` should return 0.

This speaks of **pairs of objects with comparable values**; it does not mean `compareTo` must return exactly `-1` or `1` when they differ. Any negative/positive value is valid.

**Key point:** This is a **recommendation**, not a mandatory condition for a class to implement `Comparable`. Some standard classes, notably `BigDecimal`, intentionally have a natural ordering **inconsistent** with `equals`; JavaDoc requires such cases to be clearly documented so users understand the consequences.

## 2. Why does Java recommend consistency?

Suppose a system defines two products with the same `sku` code as the same logical object. If `equals` uses `sku` yet `compareTo` compares only selling price, we can encounter two situations:

- Two products with different codes but the same price: `compareTo == 0` even though `equals == false`. A `TreeSet` may drop the second product as a duplicate, while `HashSet` keeps both.
- Two products with the same code but different prices: `equals == true` even though `compareTo != 0`. A `HashSet` treats them as duplicates, yet `TreeSet` may keep two elements that `equals` considers equal.

This discrepancy is especially confusing if the same objects are passed sequentially through APIs accepting `Set`, or when replacing `HashMap` with `TreeMap` to sort keys.

| Collection | Mechanism to identify equivalent elements/keys | Consequence when criteria differ |
| --- | --- | --- |
| `HashSet` | `equals(Object)` and `hashCode()` | Merges elements equal under `equals` |
| `HashMap` | `equals(Object)` and `hashCode()` of key | Updates value when encountering an equal key |
| `TreeSet` | `compareTo(T) == 0` or `Comparator.compare(...) == 0` | Treats elements with equal comparison order as one |
| `TreeMap` | `compareTo(T) == 0` or `Comparator.compare(...) == 0` | Treats keys comparing to 0 as one key |

`TreeSet` and `TreeMap` still operate according to **the supplied comparison order**, even when inconsistent with `equals`. However, they then do not fully satisfy the equality semantics normally described by the `Set`/`Map` interfaces. Calling APIs must clearly understand this rule.

Beyond correctness, consistency makes code more readable: "two duplicate keys" shares the same meaning whether data resides in a hash map, an ordered map, or is compared directly.

## 3. Bad example: compareTo checks only priority, equals checks the whole record

Create file `InconsistentComparisonDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class InconsistentComparisonDemo {
    record Event(String code, int priority)
            implements Comparable<Event> {

        @Override
        public int compareTo(Event other) {
            return Integer.compare(priority, other.priority);
        }
    }

    public static void main(String[] args) {
        Event a = new Event("E-1", 5);
        Event b = new Event("E-2", 5);

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);

        Set<Event> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<Event> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println(treeSet.size());
        System.out.println(treeSet.contains(b));
    }
}
```

Run with JDK 17 or newer:

```bash
javac InconsistentComparisonDemo.java
java InconsistentComparisonDemo
```

Output:

```text
false
true
2
1
true
```

Interpretation:

1. Record `Event` auto-generates `equals(Object)` using **both `code` and `priority`**. `a` and `b` have different codes, so `equals` is `false`.
2. `compareTo` compares only `priority`. Both events have priority 5, so `compareTo == 0`.
3. `HashSet` keeps **2 elements** according to record equality.
4. `TreeSet` keeps only **1 element**, because natural ordering considers the two events equal. `contains(b)` still returns `true` under the tree's criterion, even though object `b` was not added as a separate element.

`TreeSet.contains(b)` here does not prove `a.equals(b)`. It only proves the tree contains an element equivalent to `b` under the comparison currently in use.

**Design issue:** If business requirements state an event is distinguished by both code and priority, `compareTo` is missing a tie-breaking criterion (`code`). If the real goal is merging events of the same priority level, explicitly express that rule in the data structure or a `Comparator`, rather than assuming normal equality changed accordingly.

## 4. Correct design: same definition of "duplicate" in equals and compareTo

The example below models a unique product code `sku`. Display price is purely a descriptive attribute, **not determining identity**. Therefore, both `equals` and `compareTo` rely on `sku`.

Create file `ConsistentComparisonDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ConsistentComparisonDemo {
    static final class Product implements Comparable<Product> {
        private final String sku;
        private final int displayPrice;

        Product(String sku, int displayPrice) {
            this.sku = Objects.requireNonNull(sku);
            this.displayPrice = displayPrice;
        }

        @Override
        public int compareTo(Product other) {
            return sku.compareTo(other.sku);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Product other
                    && sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        Product a = new Product("A-01", 100);
        Product sameSku = new Product("A-01", 200);
        Product b = new Product("B-01", 100);

        System.out.println(a == sameSku);
        System.out.println(a.equals(sameSku));
        System.out.println(a.compareTo(sameSku) == 0);
        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) < 0);

        Set<Product> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(sameSku);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<Product> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(sameSku);
        treeSet.add(b);
        System.out.println(treeSet.size());

        Map<Product, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(sameSku, "updated");
        System.out.println(hashMap.size());
        System.out.println(hashMap.get(a));

        Map<Product, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(sameSku, "updated");
        System.out.println(treeMap.size());
        System.out.println(treeMap.get(a));
    }
}
```

Run:

```bash
javac ConsistentComparisonDemo.java
java ConsistentComparisonDemo
```

Stdout:

```text
false
true
true
false
true
2
2
1
updated
1
updated
```

Explanation:

- `a` and `sameSku` have different references (`== false`) yet share the same `sku`; hence `equals == true` and `compareTo == 0`.
- `a` and `b` have different codes; `equals == false`, while `compareTo` produces the proper lexicographical order of codes (`"A-01"` before `"B-01"`).
- Both `HashSet` and `TreeSet` contain exactly **2 logical products**.
- Both `HashMap` and `TreeMap` have only **1 logical key** after updating code `A-01`; `get(a)` returns `"updated"`.

Here `displayPrice` does not participate in equality or natural ordering, so two products with the same SKU yet different display prices still represent the same business object. **This is an intentional decision of the example**, not a rule that every `Product` type should ignore price.

`Product` is `final`, `sku` is `final`, and `String` is immutable; this helps maintain consistency while keys/elements reside in collections. For types with inheritance or mutable attributes, you must additionally check the equality contract across the entire hierarchy and the risk of key mutation.

## 5. Fixing the Event example with a tie-breaking criterion

For record `Event(String code, int priority)`, `equals` is generated based on **both components**. Natural ordering can be made consistent by comparing priority first and then using code to distinguish events with the same priority:

```java
@Override
public int compareTo(Event other) {
    int byPriority = Integer.compare(priority, other.priority);
    if (byPriority != 0) {
        return byPriority;
    }
    return code.compareTo(other.code);
}
```

This is **a snippet placed inside record `Event` from the previous example**, assuming `code` is not `null`. With valid strings, the comparison returns 0 only when **`priority` is equal and `code` is equal**, aligning with the auto-generated `equals`.

If an ordering is only a temporary need for a screen or report, there is no need to change the type's natural ordering. Instead, use a `Comparator` where the collection is created. Keep in mind that the comparator will govern duplicate key/element meaning for any `TreeSet`/`TreeMap` using it.

Example comparator comparing both criteria:

```java
Comparator<Event> byPriorityThenCode =
        Comparator.comparingInt(Event::priority)
                .thenComparing(Event::code);
```

This snippet is also **illustrative code**, requiring `import java.util.Comparator;` and record `Event` having accessors `priority()`, `code()`. If `code` can be `null`, you must define how `null` is handled (for instance `Comparator.nullsFirst`).

## 6. Three separate contracts must all hold

A class defining both equality and natural ordering should satisfy **three layers of commitments**:

### The equals(Object) contract

`equals` must be reflexive, symmetric, transitive, consistent when relevant data does not change, and `x.equals(null) == false` for non-`null` `x`.

### The hashCode() contract

If `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()` must be `true`. Keys in `HashMap` or elements in `HashSet` should keep data participating in equality **stable while stored**.

`compareTo` **does not replace** `hashCode`. Two objects with `compareTo == 0` yet `equals == false` do not mean they must share the same hash code. The hash rule stems from `equals`.

### The compareTo(T) contract

Natural comparison must produce a consistent order: results in opposite directions must have opposite signs, the greater-than relation must be transitive, and when `x.compareTo(y) == 0`, `x` and `y` must compare identically when placed before a third compatible object. In other words, the comparator must not create contradictory ordering.

**Consistency between compareTo and equals is an additional recommendation**, not a replacement for the intrinsic conditions of either method. A class can have a transitive `compareTo` yet still be inconsistent with `equals`, as in the `Event` example.

## 7. Intentional exception: BigDecimal

`BigDecimal` is a well-documented standard Java example: two numbers can be equal in numerical value yet differ in **scale**.

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
```

This is an illustrative snippet requiring `import java.math.BigDecimal;`. `compareTo` considers both numerically equal; `equals` additionally requires the same scale. Consequently `HashSet<BigDecimal>` can keep `2.0` and `2.00` as two elements, while `TreeSet<BigDecimal>` with natural ordering keeps only one.

That **does not make BigDecimal a broken Java type**: it intentionally expresses two different equality concepts. However, API users must clearly decide whether "duplicate" means equal numerical value or equal value and scale, especially before using them as map keys or set elements.

If business logic wants to merge all representations of the same decimal number, you can deliberately normalize with `stripTrailingZeros()` at both insertion and lookup; remember that this method can produce negative scale or scientific notation form. If business logic needs a fixed scale (e.g., two decimal places), you can call `setScale(2, roundingMode)` with an explicit rounding rule. Do not apply normalization arbitrarily when scale carries business meaning.

## 8. Common implementation mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `compareTo` checks one field while `equals` checks multiple fields | Elements distinct under `equals` may be merged by TreeSet | Add appropriate tie-breaking criteria or redefine equality per business logic |
| `compareTo` checks multiple fields while `equals` checks one field | TreeSet may hold two elements that `equals` considers equal | Unify the definition of duplicate |
| Using `return a - b;` to compare `int` | Overflow can flip order, breaking comparison rules | Use `Integer.compare(a, b)` |
| Assuming `compareTo` always returns `-1`, `0`, `1` | Faulty condition checks, such as `compareTo(x) == 1` | Check only negative / 0 / positive |
| Overriding `equals` while forgetting `hashCode` | HashSet/HashMap fails to recognize equal objects | Override both using the same components |
| Putting mutable keys into a collection then mutating compared fields | HashMap lookup or TreeSet/TreeMap ordering can break | Prefer immutable types; remove first, update, and re-insert when needed |
| Calling `compareTo(null)` expecting a comparison result with `null` | Standard `Comparable` does not treat `null` as a valid comparison value | Handle `null` separately or use a comparator with a null policy |
| Using a `Comparator` on a display column assuming TreeSet still distinguishes elements via `equals` | TreeSet merges whenever comparator returns 0 | Use tie-breaking criteria or a data structure allowing duplicate sort keys |

One practical rule: **natural ordering should represent a type's stable, long-term meaningful order**, whereas screen-driven sorting styles (by price, date, priority) should be expressed via separate comparators. Still, even a separate comparator must be examined carefully if used as the key-identification mechanism in a sorted set/map.

## 9. Design and testing checklist

1. **Write the equality definition first:** which two objects are genuinely one logical value? Choose fields participating in `equals` and `hashCode`.
2. **Choose natural ordering:** which criteria yield a complete, transitive, and stable order? Break ties thoroughly enough so `compareTo == 0` denotes exactly one logical value if consistency with `equals` is desired.
3. **Use proper comparison helpers:** `Integer.compare`, `Long.compare`, `String.compareTo`, `Comparator.comparing(...).thenComparing(...)` instead of subtraction prone to overflow.
4. **Test both directions:** for distinct objects `a`, `b`, verify `(a.compareTo(b) == 0) == a.equals(b)` and that `b.compareTo(a)` has the opposite sign when appropriate.
5. **Test three elements:** if `a < b` and `b < c` then `a < c`; values comparing to 0 do not alter the outcome when compared against a third element.
6. **Test real Sets/Maps:** place equal and distinct objects into `HashSet`/`TreeSet`, use as `HashMap`/`TreeMap` keys, compare sizes and `contains/get` results.
7. **Check null, inheritance, mutable state:** define comparison preconditions clearly and avoid mutating ordering-determining fields while the object resides in a sorted collection.
8. **If intentionally inconsistent, document clearly:** explain `compareTo` criteria, `equals` criteria, and the impact on sorted sets/maps; users must select the appropriate collection.

**Self-check:**

- If `a.compareTo(b) == 0` yet `a.equals(b) == false`, is natural ordering consistent with equals? **No.**
- If a `TreeSet` stores only one element while a `HashSet` stores two elements for the same pair of objects, what is the usual cause? **Two different definitions of "duplicate" between ordering comparison and equality.**
- Is consistency between `compareTo` and `equals` mandatory for every `Comparable` class? **No, yet strongly recommended; when inconsistent, it must be documented.**
- When using a `Comparator` to sort by score, if multiple people share the same score and all must be kept, what should you do? **Add a tie-breaking criterion or use an appropriate data structure, instead of using a TreeSet that compares only by score.**

**Remember:** You should define `compareTo(a, b) == 0` true precisely when `a.equals(b)` is `true`, so every collection shares a unified meaning of "same element/key". Intentional exceptions like `BigDecimal` are valid, yet their behavior must be understood and documented when using ordered data structures.