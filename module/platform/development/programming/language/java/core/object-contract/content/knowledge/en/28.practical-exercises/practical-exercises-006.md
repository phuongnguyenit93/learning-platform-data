# Practice: Comparing HashSet and TreeSet with BigDecimal or a Single-Key Comparator

## 1. Objective of the Practice

Both `HashSet` and `TreeSet` implement the `Set` interface: neither stores two elements considered duplicates according to **each implementation's uniqueness rules**. However, they can yield different results when data has multiple ways of defining "equal."

After this lesson, you should be able to:

- Explain why `HashSet<BigDecimal>` and `TreeSet<BigDecimal>` can hold **different element counts** given the same input data.
- Predict `add()`, `contains()`, and element count from `equals()/hashCode()` or `compareTo()/Comparator`.
- Practice with a `Comparator` comparing only **one key** of an object: two objects differing in other attributes can still be treated as a single element by `TreeSet`.
- Distinguish **identity by full object value** from **identity by business key**; choose a consistent strategy for real-world problems.
- Avoid bugs caused by inconsistency between ordering and `equals()`, by mutating keys inside a set, and by assuming ordering in `HashSet`.

This exercise belongs to **Java core – object-contract**, emphasizing the `equals`/`hashCode` contract and its relationship with comparison ordering. No database, framework, or external library is required.

## 2. The Core Difference: Where Is "Duplicate" Decided?

| Property | `HashSet<E>` | `TreeSet<E>` |
| --- | --- | --- |
| Underlying structure | Hash-based `HashMap` | Ordered tree structure backed by `TreeMap` |
| How duplicates are determined | `equals()`, with matching `hashCode()` to locate slots | `compareTo() == 0` or `Comparator.compare(a, b) == 0` |
| Iteration order | No ordering guaranteed | By natural ordering or comparator |
| Typical find/add/remove cost | Average O(1) with good hashing; worst case can be higher | O(log n) |
| Allows `null` | Can store one `null` | Natural ordering rejects `null`; comparator depends on definition |
| Key constraint | Two objects with `equals()==true` must have equal `hashCode()` | Ordering comparison should be consistent with `equals()` to fully obey the `Set` contract |

**`HashSet`:** conceptually, a new element first uses `hashCode()` to locate the appropriate slot; if another element exists that is equal per `equals()`, `add()` does not insert a new unique element into the set. Do not think "same hash alone means duplicate": **a hash collision does not mean equals**.

**`TreeSet`:** insertion, lookup, and removal rely on comparison. A result of **0** means "equivalent for the ordered set" even when the two objects' `equals()` returns `false`. A comparator operating on a single key can collapse many distinct objects into the same equivalence class.

In any example: if `compare(a,b) == 0` while `!a.equals(b)`, `TreeSet` keeps only one of the two, whereas `HashSet` keeps both (assuming their hashCode/equals obey the contract).

### What does the boolean return value of `add()` mean?

`set.add(element)` returns `true` if the set changed by adding the new element, or `false` if the element is already considered present. With `TreeSet`, `false` may mean "**an element with the same comparison key is already present**," not "an identical object matching all attributes is already present."

`TreeSet` does not automatically overwrite the old object with the new object when the comparator returns 0. Under sequential additions, the retained element is the one from the earlier successful insertion, unless you explicitly remove/replace it.

## 3. BigDecimal: Arithmetic Equality Differs from equals() Equality

`BigDecimal` both implements `Comparable<BigDecimal>` and defines its own `equals()` and `hashCode()`. For `BigDecimal`, the **scale** (number of decimal digits represented) is a significant factor.

The following two numbers have equal arithmetic values:

~~~java
BigDecimal a = new BigDecimal("2.0");  // unscaled=20, scale=1
BigDecimal b = new BigDecimal("2.00"); // unscaled=200, scale=2
~~~

However:

- `a.equals(b)` is **false** because both value and scale must match under `BigDecimal.equals()` rules.
- `a.compareTo(b)` is **0** because `BigDecimal`'s natural ordering compares **numerical value**; two representations of the same numerical value are equivalent.
- `HashSet` treats the two objects as **distinct** according to `equals()`.
- `TreeSet` uses `BigDecimal`'s natural ordering and treats both objects as **the same element in comparison order**.

This is a documented exception in Java's API docs: `BigDecimal`'s natural ordering is **inconsistent with equals**. There is no bug in Java or in either set; the issue is simply two different definitions of uniqueness.

## 4. Runnable Java 17 Program: Comparing Both Scenarios

The program below has two parts:

1. Add `BigDecimal("2.0")` and `BigDecimal("2.00")` to both `HashSet` and `TreeSet`.
2. Add two `Product` instances with the same `sku` but different `name`; test a `TreeSet` comparing only `sku` and a comparator with `name` as a secondary key.

Save the **entire** program into **SetComparisonDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class SetComparisonDemo {

    record Product(String sku, String name) { }

    public static void main(String[] args) {
        compareBigDecimals();
        compareProducts();
    }

    private static void compareBigDecimals() {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        Set<BigDecimal> hash = new HashSet<>();
        Set<BigDecimal> tree = new TreeSet<>();

        System.out.println("=== BigDecimal ===");
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b): " + a.compareTo(b));

        System.out.println("HashSet add(a): " + hash.add(a));
        System.out.println("HashSet add(b): " + hash.add(b));
        System.out.println("TreeSet add(a): " + tree.add(a));
        System.out.println("TreeSet add(b): " + tree.add(b));

        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + tree.size());
        System.out.println("TreeSet values: " + tree);
    }

    private static void compareProducts() {
        Product a = new Product("SKU-1", "Notebook");
        Product b = new Product("SKU-1", "Notebook Pro");

        Set<Product> hash = new HashSet<>();
        Set<Product> treeBySku =
                new TreeSet<>(Comparator.comparing(Product::sku));
        Set<Product> treeBySkuAndName = new TreeSet<>(
                Comparator.comparing(Product::sku)
                        .thenComparing(Product::name));

        System.out.println("=== Product ===");
        System.out.println("a.equals(b): " + a.equals(b));

        hash.add(a);
        hash.add(b);
        System.out.println("HashSet size: " + hash.size());

        System.out.println("TreeSet by SKU add(a): " + treeBySku.add(a));
        System.out.println("TreeSet by SKU add(b): " + treeBySku.add(b));
        System.out.println("TreeSet by SKU size: " + treeBySku.size());
        System.out.println("TreeSet by SKU first: "
                + ((TreeSet<Product>) treeBySku).first());
        System.out.println("TreeSet by SKU contains(b): "
                + treeBySku.contains(b));

        treeBySkuAndName.add(a);
        treeBySkuAndName.add(b);
        System.out.println("TreeSet by SKU+name size: "
                + treeBySkuAndName.size());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 SetComparisonDemo.java
java SetComparisonDemo
~~~

Expected output (avoiding printing `HashSet` directly because its iteration order is not guaranteed):

~~~text
=== BigDecimal ===
a.equals(b): false
a.compareTo(b): 0
HashSet add(a): true
HashSet add(b): true
TreeSet add(a): true
TreeSet add(b): false
HashSet size: 2
TreeSet size: 1
TreeSet values: [2.0]
=== Product ===
a.equals(b): false
HashSet size: 2
TreeSet by SKU add(a): true
TreeSet by SKU add(b): false
TreeSet by SKU size: 1
TreeSet by SKU first: Product[sku=SKU-1, name=Notebook]
TreeSet by SKU contains(b): true
TreeSet by SKU+name size: 2
~~~

### Interpreting the `BigDecimal` Results

- `HashSet add(b): true`: the two numbers differ in scale, so they are not equal under `BigDecimal.equals()`. `HashSet` grows to 2 elements.
- `TreeSet add(b): false`: `b.compareTo(a) == 0`; the tree already holds an equivalent element under natural ordering.
- `TreeSet values: [2.0]`: the set retains the first object (`a`) that was successfully added. If you reverse the insertion order to `b` then `a`, the representative element displays `2.00`.
- Do not use this size difference to claim one set is "right" and the other is "wrong." You must check whether business requirements treat scale as significant.

### Interpreting the `Product` Results

`record Product(String sku, String name)` automatically generates `equals()` and `hashCode()` examining **both components**. Since `name` differs, `a.equals(b) == false`, so `HashSet` keeps both.

Comparator `Comparator.comparing(Product::sku)` looks only at `sku`. Two products with the same SKU have `compare(a,b) == 0` despite different names. Consequently, the SKU-based `TreeSet` retains only the record added first; `contains(b)` returns **true** even though object `b` was never stored as an element in the tree. `contains()` asks whether there is **an element in the same comparison equivalence class**.

When adding `thenComparing(Product::name)`, name becomes the secondary key; two products sharing an SKU with different names sort into two distinct positions, so the size is 2.

**Scope note:** The SKU+name comparator matches `equals()` because this record has only two non-null `String` fields and both string fields use natural ordering consistent with equals. If the record gains another field participating in the equals contract, a comparator using only SKU+name **is no longer guaranteed** to be consistent with equals.

## 5. Deliberate Practice: Predict Before Running

### Exercise 1 — Multiple representations of the same number

Given:

~~~java
BigDecimal x = new BigDecimal("10.0");
BigDecimal y = new BigDecimal("10.00");
BigDecimal z = new BigDecimal("9.0");
~~~

If `x, y, z` are added sequentially into two empty sets:

| Check | `HashSet<BigDecimal>` | `TreeSet<BigDecimal>` |
| --- | --- | --- |
| Add `x` | `true` | `true` |
| Add `y` | `true` | `false` |
| Add `z` | `true` | `true` |
| Size | 3 | 2 |
| Iteration order | No guarantee | Ascending by numerical value |

**Why?** `x.equals(y) == false` yet `x.compareTo(y) == 0`; meanwhile `z` has a smaller numerical value and differs from both under every criterion above.

### Exercise 2 — Comparator inspecting only a single key

Consider these records:

~~~java
record Employee(String departmentId, String fullName) { }

Employee first = new Employee("D01", "An");
Employee second = new Employee("D01", "Binh");

Set<Employee> staff = new TreeSet<>(
        Comparator.comparing(Employee::departmentId));
~~~

If `first` is added and then `second`:

- `staff.size()` is **1**, because the comparator checks only `departmentId`.
- The remaining element has the name **An**, because `first` was added first.
- `staff.contains(second)` returns **true** per the comparator, even though `second` is not stored as the representative object.

**Question:** If the requirement is "no two employees in the same department," is this sufficient?

In terms of the key set, the comparator enforces deduplication by department ID. However, in terms of **business modeling**, keeping only one employee per department can drop data and misrepresent the relationship between departments and employees. Consider `Map<String, Employee>` if there is genuinely only one representative per department code, or `Map<String, List<Employee>>` if each department has multiple people. A comparator cannot by itself decide whether dropping data is valid policy.

## 6. Choosing Equivalence Criteria Based on Business Purpose

Before choosing `HashSet`, `TreeSet`, or `Map`, define the **unit of uniqueness**.

### Case A — Distinguish decimal representations as well

For example, an input validation system wants to distinguish a user entering `2.0` from `2.00` to preserve display precision or scale per data rules. `HashSet<BigDecimal>` fits better if you want to directly reflect `BigDecimal.equals`; remember it "fits" here because **the definition of identity includes scale**.

### Case B — Identical numerical values must be treated as duplicates

If `2.0` and `2.00` must represent the same value:

- `TreeSet<BigDecimal>` with natural ordering deduplicates based on `compareTo() == 0` while also sorting numerically.
- If a hash structure is needed, you can **normalize** values before insertion, such as `value.stripTrailingZeros()` (with a consistently applied normalization policy). After normalization, `2.0` and `2.00` become `equals() == true`.

Illustrative snippet inside a Java method with `import java.math.BigDecimal`, `import java.util.Set`, and `import java.util.HashSet`:

~~~java
Set<BigDecimal> canonical = new HashSet<>();
canonical.add(new BigDecimal("2.0").stripTrailingZeros());
canonical.add(new BigDecimal("2.00").stripTrailingZeros());
System.out.println(canonical.size()); // 1
~~~

Be careful: `stripTrailingZeros()` can turn the scale **negative** and alter how a number displays, such as a large integer with trailing zeros. If output formatting is a business requirement, do not rely solely on `toString()` of the normalized value; separate numerical value from display formatting.

### Case C — Currency with fixed scale

If monetary data must always have exactly two decimal places, you can define a policy converting to scale 2:

~~~java
BigDecimal amount = new BigDecimal("2.0")
        .setScale(2, java.math.RoundingMode.UNNECESSARY);
System.out.println(amount.toPlainString()); // 2.00
~~~

Using `RoundingMode.UNNECESSARY` throws `ArithmeticException` if rounding would be required to reach the target scale. In real applications, rounding policies must be specified by currency type, business rules, and data source. **Never silently round** just to make keys match.

### Case D — Unique solely by business code

If records have `id` or `sku` as the unique key, `TreeSet<>(Comparator.comparing(Entity::id))` can guarantee one representative per key while sorting ascending by key. However, this relation may be **inconsistent with `Entity.equals()`**.

A `Map<Key, Value>` usually expresses "each key has one value" more clearly. For example:

~~~java
Map<String, String> latestNameBySku = new java.util.HashMap<>();
latestNameBySku.put("SKU-1", "Notebook");
latestNameBySku.put("SKU-1", "Notebook Pro");
System.out.println(latestNameBySku.get("SKU-1")); // Notebook Pro
~~~

Inside a Java method, this snippet requires `import java.util.Map`; `put` intentionally chooses the policy of overwriting the earlier value with the later one. If you do **not** want overwriting, use `putIfAbsent` or handle conflicts explicitly.

## 7. What Does "Comparator Consistent with equals" Mean?

An ordering is called **consistent with equals** when for all valid `a, b`, the condition `compare(a,b) == 0` is equivalent to `a.equals(b) == true`.

In this lesson there are two examples that **do not** satisfy this:

- `BigDecimal("2.0")` and `BigDecimal("2.00")`: `compareTo == 0` yet `equals == false`.
- Two `Product` instances with the same SKU and different names: the SKU comparator returns 0 yet record equals returns false.

According to the `SortedSet`/`Set` contract, a sorted set's ordering should be consistent with equals if you want the sorted set to **fully** obey the general `Set` contract. `TreeSet` still behaves deterministically when the comparator is inconsistent; however, certain set equality checks, `contains`, or flows combining `HashSet` and `TreeSet` can surprise users. Do not assume the two sets are interchangeable everywhere just because both are `Set`.

Do not try to modify `BigDecimal.equals()` (it is an immutable library type). If a different comparison policy is needed, apply a normalization strategy, a wrapper/domain value object, or an appropriate collection.

### Comparator with a secondary key to avoid unintended data loss

When you want all records retained if they differ in meaningful fields, add a secondary key with `thenComparing()`:

~~~java
Comparator<Product> bySkuThenName =
        Comparator.comparing(Product::sku)
                .thenComparing(Product::name);
~~~

This snippet uses `Product` defined in the main program and `import java.util.Comparator`.

However, avoid adding secondary keys mechanically just to "stop duplicates": if policy requires **one product per SKU**, adding `name` as a secondary key changes the business rule and may no longer satisfy requirements.

## 8. Impact of equals/hashCode on HashSet

Objects placed into a `HashSet` must obey the contract:

1. `equals` is reflexive, symmetric, transitive, and consistent while attributes used in comparison do not change.
2. If `a.equals(b)` is `true`, `a.hashCode() == b.hashCode()` must hold.
3. Two **unequal** objects can still share a hash code; `HashSet` falls back on `equals()` as needed.
4. When overriding `equals()`, you almost always need to override `hashCode()` to maintain the contract.

Records automatically generate `equals()/hashCode()` from their components, so the `Product` example already has a contract consistent on both `sku` **and** `name`. Nevertheless, a record can contain mutable components; do not automatically assume every record is deeply immutable.

If you want `Product`'s identity to depend solely on SKU across **all** structures, design a class/value object whose `equals/hashCode` matches that policy, rather than only swapping a `Comparator` at one `TreeSet` usage site.

## 9. Avoid Mutating Keys While Elements Are Inside a Set

This is a dangerous bug for both implementations, especially when objects have mutable fields:

- With `HashSet`, mutating a field participating in `hashCode()/equals()` can make the object fall into a mismatched bucket during lookup, causing `contains()/remove()` to fail to behave as expected.
- With `TreeSet`, mutating a field used by the comparator for ordering can corrupt the tree's ordering invariant; lookups or insertions can yield confusing results.
- Modifying fields that do not affect equality/comparator may remain safe for uniqueness and ordering, though business invariants and concurrency must still be considered.

**Principle:** use immutable keys for elements in a set; if a key must change, **remove before mutating, then re-add** in a controlled flow, or use a more suitable data model. Never silently mutate a key via an external reference while the element remains inside the collection.

## 10. Other Differences and Limitations to Observe

### Ordering and performance

`HashSet` makes no guarantee on iteration order, even if running a program multiple times appears to yield a stable order. Never write tests asserting a specific printed string order directly from a `HashSet`.

`TreeSet` provides ordered operations from `NavigableSet` such as `first()`, `last()`, `lower()`, `floor()`, `ceiling()`, and `higher()`. These rely on the comparator or natural ordering; if the comparator checks only SKU, all nearest-element queries also operate by SKU.

`HashSet` typically has average O(1) basic operations with good hash distribution; `TreeSet` is O(log n). Having uniqueness match requirements and key stability matters more than picking a structure on speed alone.

### Comparator and null

`TreeSet` with natural ordering normally rejects `null`. A custom comparator can handle null via `Comparator.nullsFirst(...)` or `nullsLast(...)` per policy; however, nullable data must still be controlled to avoid an undefined comparator. `HashSet` can hold exactly one `null` value.

### ClassCastException and non-transitive comparisons

If an object does not implement `Comparable` and you construct `new TreeSet<>()` without passing a comparator, adding an element can throw `ClassCastException`. Similarly, a comparator that rejects the supplied type also triggers comparison errors.

A comparator must define a valid, consistent total ordering—especially reflexivity, antisymmetry of sign, and transitivity per the `Comparator` contract. A non-transitive comparator can cause sorted structures to behave unexpectedly. Avoid comparators like `return a.someInt - b.someInt;` because of integer overflow risk; prefer `Comparator.comparingInt(...)` or `Integer.compare(...)`.

### BigDecimal and double values

To input exact decimal values from strings, use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` as appropriate; be careful with `new BigDecimal(0.1)` because converting directly from `double`'s binary representation can produce a long decimal value unlike what the author expected. That is a numeric representation issue, **distinct** from equals/compareTo and scale, yet it easily makes exercises harder to interpret if wrong inputs are used.

## 11. Troubleshooting Table for Practical Exercises

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `HashSet<BigDecimal>` has 2, `TreeSet<BigDecimal>` has 1 | `equals` checks scale, `compareTo` checks numerical value | Choose the duplicate definition explicitly and apply consistently |
| `TreeSet<Product>` drops elements with different names | Comparator checks only SKU | To keep both, add a secondary key; to deduplicate by SKU, state the policy clearly |
| `tree.contains(b) == true` even though object `b` is not stored | Another element is considered equivalent by the comparator | Interpret `contains` by comparison equivalence class, not object identity |
| Asserting printed `HashSet` output fails intermittently | No iteration order guarantee | Assert only size/membership or explicitly sort before printing |
| `HashSet` cannot find an object after changing its ID | Field used in equals/hashCode was mutated | Immutable keys or controlled remove-mutate-add |
| `TreeSet` lookups fail after changing sort key | Tree does not re-sort itself after mutation | Avoid mutating keys while objects are in the set |
| `TreeSet` throws `ClassCastException` | Missing natural ordering/appropriate comparator | Supply a properly typed Comparator |
| Normalizing `BigDecimal` changes display | `stripTrailingZeros` can alter scale | Separate value policy from display formatting |

## 12. Checklist for Reviewing a Set Problem

When deduplicating elements, answer in exact order:

1. **What does "duplicate" mean?** Identical across all fields, identical ID, identical numerical value, or identical decimal representation?
2. **What is the equals/hashCode contract?** Which two elements are considered equal as objects?
3. **What does Comparator or compareTo inspect?** When does comparison return 0?
4. **Are the two rules consistent?** If not, can the application tolerate differences in `add()`/`contains()`/combined collections?
5. **Is sorted order needed?** If not, `HashSet` may be simpler; if yes, `TreeSet` is an option, provided the comparator is finalized.
6. **Is the key immutable while inside the Set?** If not, redesign how updates occur.
7. **Do you need one representative per key or all records?** For one value per key, `Map<K,V>` usually expresses intent more clearly.

### Self-check answers

- Does `HashSet` use `BigDecimal`'s `compareTo()` to decide duplicates? **No**.
- Does `TreeSet` always call `equals()` to decide duplicates? **No**; it relies on comparison.
- Does `BigDecimal("2.0").compareTo(BigDecimal("2.00")) == 0` imply `equals() == true`? **No**.
- If a comparator checks only `sku`, does adding two records with the same SKU and different names keep both? **No**; the second element added is treated as a duplicate.
- If a secondary key `name` is added, is it always consistent with `equals()`? **Only when** the compared fields sufficiently cover the `equals` contract and each component's comparator is consistent with equals.

**Knowledge takeaway:** `HashSet` and `TreeSet` differ in **the contract defining uniqueness**, not only in ordering or performance. With `BigDecimal` or a single-key comparator, decide upfront whether "equal" means by representation, by numerical value, or by business key. Once that policy is clear, `add()`, `contains()`, sizes, and data retention become predictable.

## Official References

- [Java SE 21 — HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html)
- [Java SE 21 — TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html)
- [Java SE 21 — SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [Java SE 21 — Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)