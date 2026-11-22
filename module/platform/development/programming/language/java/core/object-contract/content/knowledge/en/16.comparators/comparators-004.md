# `Comparator.thenComparing()`: Creating Multi-Key Orderings in Java

## 1. The Problem and Precedence Principles

When sorting a list of objects, a single field is often insufficient to determine position. For example, an HR system's requirement might be:

1. Sort **department ascending**.
2. Within the same department, sort **level descending**.
3. If levels tie, sort **name ascending**.
4. If still tied, sort **employee ID ascending** for a deterministic result.

This is **multi-key sorting**, or *lexicographic ordering*: evaluate the first key first; only when two values compare equal under the current comparator do you move on to the next key.

In Java, `Comparator<T>` expresses an ordering rule between two objects of type `T`. The result of `compare(a, b)` is:

- Negative: `a` comes before `b`.
- Zero: `a` and `b` are considered **equivalent under the sort order**.
- Positive: `a` comes after `b`.

The return value does **not** have to be `-1`, `0`, or `1`; only the negative/zero/positive sign matters. The relation "`compare(a, b) == 0`" does not automatically mean "`a.equals(b)`".

The `thenComparing()` method chains comparators according to that rule, keeping **key precedence** clear in code without needing nested `if` blocks.

## 2. How `thenComparing()` Works

`Comparator.comparing(keyExtractor)` creates a comparator based on a key with a *natural order* such as `String` or `LocalDate`. `thenComparing(nextComparator)` adds a fallback comparator used when the preceding comparator returns `0`.

Example:

```java
Comparator<Person> byLastThenFirst =
    Comparator.comparing(Person::lastName)
              .thenComparing(Person::firstName);
```

This is an illustrative snippet; assume a `Person` class with two getters `lastName()` and `firstName()` returning non-`null` `String` values, along with `import java.util.Comparator;`.

When comparing two people:

1. `lastName` differs -> use the surname key result immediately, **without examining** the first name.
2. `lastName` is considered equal by the comparator -> examine `firstName`.
3. Both keys are equivalent -> the comparison result is `0`.

Expressed algorithmically (only to understand the mechanism):

```java
// Equivalent logic in meaning, not code you are required to hand-write.
int primary = byLastName.compare(a, b);
if (primary != 0) {
    return primary;
}
return byFirstName.compare(a, b);
```

Chaining multiple keys produces a **new** comparator. `thenComparing()` does not mutate an existing comparator, so you must use the returned value when building a comparison chain.

### 2.1. Commonly used overloads

| Call | When to use | Example meaning |
| --- | --- | --- |
| `thenComparing(Comparator<? super T>)` | Already have a comparator for the whole object | After primary key, use descending level comparator |
| `thenComparing(Function<? super T, ? extends U>)` | Secondary key type supports natural order | After surname, compare first name |
| `thenComparing(Function, Comparator<? super U>)` | Secondary key needs a custom rule: `null`, case-insensitive, reversed | After team, compare name using `String.CASE_INSENSITIVE_ORDER` |
| `thenComparingInt(ToIntFunction<? super T>)` | `int` integer key | After name, compare `int` ID |
| `thenComparingLong(ToLongFunction<? super T>)` | `long` key | After status, compare epoch timestamp |
| `thenComparingDouble(ToDoubleFunction<? super T>)` | `double` key | After group, compare score |

The primitive convenience methods avoid unnecessary boxing. For the first key, there are also `Comparator.comparingInt`, `comparingLong`, and `comparingDouble`.

**Note:** `Comparator.comparing(Person::name)` assumes the key implements `Comparable` and has a suitable `null` policy. If the key can be `null`, use a comparator that explicitly handles null; never assume natural comparison accepts `null`.

## 3. Complete Java 17 Example: Four Keys, Two Sort Directions

Data definition:

- `department`: String, A -> Z.
- `level`: int, larger comes first.
- `name`: String, A -> Z.
- `employeeId`: int, smaller comes first.
- `salary`: long, extra information **not participating** in the chosen order.

A clear technique when a secondary key is descending is passing an **already-reversed secondary comparator** into `thenComparing`, rather than calling `reversed()` on the entire chain.

Save to **`MultiKeyComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class MultiKeyComparatorDemo {
    record Employee(String department, String name,
                    int level, long salary, int employeeId) {}

    public static void main(String[] args) {
        List<Employee> employees = new ArrayList<>(List.of(
            new Employee("Core", "An",   3, 100, 102),
            new Employee("Core", "Binh", 5, 125, 103),
            new Employee("Core", "An",   5, 130, 101),
            new Employee("Web",  "An",   4, 120, 104),
            new Employee("Core", "An",   5, 140, 105)
        ));

        Comparator<Employee> byDepartmentLevelNameId =
            Comparator.comparing(Employee::department)
                .thenComparing(
                    Comparator.comparingInt(Employee::level).reversed()
                )
                .thenComparing(Employee::name)
                .thenComparingInt(Employee::employeeId);

        employees.sort(byDepartmentLevelNameId);

        for (Employee employee : employees) {
            System.out.printf("%s | %d | %s | %d%n",
                employee.department(),
                employee.level(),
                employee.name(),
                employee.employeeId());
        }

        Employee original =
            new Employee("Core", "An", 5, 130, 101);
        Employee otherSalary =
            new Employee("Core", "An", 5, 999, 101);

        System.out.println("Comparator sees tie: "
            + (byDepartmentLevelNameId.compare(original, otherSalary) == 0));
        System.out.println("Record equals: " + original.equals(otherSalary));

        TreeSet<Employee> sortedSet =
            new TreeSet<>(byDepartmentLevelNameId);
        sortedSet.add(original);
        sortedSet.add(otherSalary);
        System.out.println("TreeSet size: " + sortedSet.size());
    }
}
```

Compile and run with **JDK 17+** in the directory containing the file:

```bash
javac MultiKeyComparatorDemo.java
java MultiKeyComparatorDemo
```

Exact result:

```text
Core | 5 | An | 101
Core | 5 | An | 105
Core | 5 | Binh | 103
Core | 3 | An | 102
Web | 4 | An | 104
Comparator sees tie: true
Record equals: false
TreeSet size: 1
```

**Order explanation:**

1. `Core` employees come before `Web` because `department` is ascending; `Web`'s level is never used to jump ahead across departments.
2. Within `Core`, level `5` comes before level `3` due to `comparingInt(Employee::level).reversed()`.
3. Within `Core` level `5`, the name `An` comes before `Binh`.
4. The two `An` employees in `Core` level `5` are distinguished by `employeeId`: `101` before `105`.
5. `salary` is excluded from the comparator. The two records `original` and `otherSalary` differ only in salary so the comparator returns `0`, yet `record.equals` compares **all components** and returns `false`.
6. `TreeSet` considers the two elements equivalent under the comparator, so it keeps only one element. The result `TreeSet size: 1` is a reminder that **the comparator also governs uniqueness in ordered sets**, not just display order.

In a requirement that only sorts a list, salary might not belong in the ordering rule. However, if the comparator is used as the key definition in `TreeSet` or `TreeMap`, omitting an important field can unintentionally merge objects that `equals()` treats as distinct.

## 4. Placing Ascending and Descending Keys in the Right Spot

### 4.1. Reversing the right **secondary key**

To make `department` ascending yet `level` descending:

```java
Comparator<Employee> order =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Comparator.comparingInt(Employee::level).reversed()
        );
```

This is an illustrative snippet using `Employee` from the complete program. The secondary comparator `comparingInt(...).reversed()` reverses only the `level` order within groups sharing the same department.

### 4.2. `reversed()` at the end reverses the **entire comparator**

Note the distinction:

```java
Comparator<Employee> allReversed =
    Comparator.comparing(Employee::department)
        .thenComparingInt(Employee::level)
        .reversed();
```

Here `reversed()` is called on the result of **the whole chain** `department` then `level`, so **both department and level** are reversed together. It does not reverse only the nearest field.

If the requirement is "department ascending, level descending," the syntax in 4.1 expresses it accurately. If the requirement is "both keys descending," `allReversed` is appropriate.

### 4.3. Changing chain order changes priority

These two expressions are not equivalent:

```java
Comparator<Employee> byDepartmentThenLevel =
    Comparator.comparing(Employee::department)
        .thenComparingInt(Employee::level);

Comparator<Employee> byLevelThenDepartment =
    Comparator.comparingInt(Employee::level)
        .thenComparing(Employee::department);
```

The key **appearing earlier** always has higher precedence. Swapping `thenComparing` positions is not a harmless code refactoring—it alters the business rule.

### 4.4. Adding a final key for a deterministic result

If using only `department`, `level`, and `name`, objects sharing all three keys will have `compare == 0`. `List.sort` and `Collections.sort` are specified by Java as **stable sorts**: elements considered equal by the comparator preserve their original relative order. However, if the input order comes from an API, database, or `HashSet` without a stable order, results may vary across data fetches.

Adding a stable, domain-unique final key such as `employeeId` (if truly unique within the sorted scope) makes the order deterministic. Do not invent criteria rejected by the business logic, and do not use `hashCode` or `identityHashCode` as a final key expecting uniqueness or stability across JVMs.

## 5. `null` Keys: First or Last Must Be Explicit

Extractors of `Comparator.comparing` can return `null`. If the key comparator does not handle null, comparisons typically throw `NullPointerException` upon encountering a null value.

To place `name == null` **after** non-null names:

```java
Comparator<Employee> byNameNullsLast =
    Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(Comparator.naturalOrder())
    );
```

To sort `department` ascending with null `name` last **within each department**:

```java
Comparator<Employee> byDepartmentThenName =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Employee::name,
            Comparator.nullsLast(Comparator.naturalOrder())
        );
```

This is an illustrative snippet using `Employee` whose `name()` returns a String. If `Employee` itself can be `null` (not just an inner field being null), you can wrap the **whole-object comparator** with `Comparator.nullsFirst(...)` or `nullsLast(...)`. Distinguish the two policies:

- `Comparator.comparing(Employee::name, nullsLast(...))` handles a **null name key**.
- `Comparator.nullsLast(byDepartmentThenName)` handles **a null Employee element itself**.

Where `nullsLast` is placed determines its scope. If you reverse a comparator that already uses `nullsLast` via `reversed()`, the null rule reverses too: `nullsLast(...).reversed()` moves nulls to the front. If you want names descending while keeping nulls last, write:

```java
Comparator<String> descendingWithNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());
```

Use this comparator for the **String key** via the `thenComparing(Employee::name, descendingWithNullLast)` overload.

Note: `Comparator.nullsFirst(null)` and `nullsLast(null)` still accept a `null` key comparator per the Java API and treat non-null values as equivalent; this is only useful when you genuinely want to ignore ordering among non-null values.

## 6. Comparing Strings Under the Right Policy

### 6.1. Case-sensitive or case-insensitive?

`String` sorts naturally in lexicographical order based on Unicode character codes (UTF-16 code units), which does not automatically match Vietnamese alphabetical order or case-insensitive requirements.

For technical codes or names requiring case-insensitive comparison, you can use:

```java
Comparator<Employee> byDepartmentThenNameIgnoreCase =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Employee::name,
            String.CASE_INSENSITIVE_ORDER
        );
```

However, `CASE_INSENSITIVE_ORDER` does not guarantee matching natural-language sorting rules in every locale. It can also return `0` for two strings that differ under `String.equals`. When sorting for display, add a case-sensitive secondary key or a stable ID if a specific total order is needed.

### 6.2. Vietnamese names and `Collator`

If the UI requires an order conforming to language rules, consider `java.text.Collator` and an appropriate `Locale`. An illustrative example:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

// Illustrative example using Employee from the sample program.
Collator vietnamese = Collator.getInstance(
    Locale.forLanguageTag("vi-VN")
);
Comparator<Employee> byVietnameseName =
    Comparator.comparing(Employee::name, vietnamese);
```

`Collator` has configurable comparison strength and behavior depending on the Java environment's locale data. If completely fixed results across environments are required, specify the collation policy and data-source version; do not assume a list of accented names will sort identically in every configuration.

`Collator` objects are mutable and are not guaranteed thread-safe if the same instance is used concurrently while being modified. When sharing across threads is needed, use an appropriate strategy such as per-thread instances or controlled access, and never alter rules during sorting.

### 6.3. Normalized key values

If code uses `String.toLowerCase()` as a secondary key, specify the locale and null policy. For technical identifiers with case-insensitive rules, using `Locale.ROOT` where appropriate is clearer than relying on the host machine's default locale. Avoid producing different normalized representations across sorting, `equals`, hashing, and business lookups.

## 7. Numeric, Date/Time Keys, and Specialized Comparators

For integers, use `comparingInt` / `thenComparingInt`; for `long`, use `comparingLong` / `thenComparingLong`; for `double`, use `comparingDouble` / `thenComparingDouble`. Primitive overloads save boxing and avoid subtracting numbers manually to compare.

Illustrative snippet for an `Event` class with `LocalDateTime createdAt()` and `long sequence()`:

```java
Comparator<Event> newestFirstThenSequence =
    Comparator.comparing(Event::createdAt, Comparator.reverseOrder())
        .thenComparingLong(Event::sequence);
```

This snippet requires `java.util.Comparator` and the corresponding `Event` class; it is not a standalone compilable program. For date/time, choose the right representation type: `LocalDateTime` carries no time zone; `Instant` is more suitable when the goal is ordering absolute points in time.

**Avoid this error-prone pattern:**

```java
// DO NOT use for large ints: can overflow.
Comparator<Employee> risky =
    (left, right) -> left.employeeId() - right.employeeId();
```

If `left.employeeId() == Integer.MIN_VALUE` and `right.employeeId() == 1`, `int` subtraction overflows and can yield the wrong sign, causing the comparator to violate ordering. Use `Integer.compare(left.employeeId(), right.employeeId())` or `Comparator.comparingInt(Employee::employeeId)`.

For `double`, `Double.compare` and `comparingDouble` define total-order rules for NaN and signed zero matching the Java API; if the business domain wants to handle NaN or `-0.0` differently, state the policy explicitly and test it. Multi-key comparators do not establish that rule automatically.

## 8. `thenComparing()` and the `Comparator` Contract

Chaining multiple keys works like lexicographical comparison: the primary key decides first, and a secondary key is consulted only when the primary key returns `0`. Component comparators must define valid, stable ordering relations; chaining them does not fix a comparator that has cycles, depends on randomness, or reads data being mutated.

Two concepts to keep separate in applications:

- **Sort key:** the key chain `department -> level -> name -> employeeId` can return `compare(a,b)==0` when two objects tie on all those keys.
- **Data identity:** a record's `equals(a,b)` may also inspect another field like `salary`. In the example in section 3, two records differing in salary still compare equal to 0.

`List.sort` keeps both tied records. `TreeSet` and `TreeMap` treat a zero result as key equivalence, so you must decide **whether the final key needs to distinguish records according to `equals`**. If an entity's identity is solely its ID yet the comparator puts mutable display fields before ID, appending ID at the end still may not be consistent with `equals`. The lesson on equality relations explores both mismatch directions in depth.
## 9. Performance and Key Extraction Timing

Chained comparators can read multiple fields via getters. `thenComparing` only evaluates a secondary key **when the preceding key ties**, so field ordering can also affect the number of extractor calls, though business requirements should always take priority.

For expensive extractors—such as normalizing names, formatting dates, querying external sources, or heavy computation—the sorter may invoke them **multiple times**. A design worth considering is precomputing keys into an immutable object/record, then sorting by the precomputed keys. Avoid calling external APIs, mutating state, or causing side effects inside a comparator.

`List.sort` and `Collections.sort` do not call the comparator only once per element. The comparator must be **pure** in the sense that its result for any pair remains unchanged throughout the sort pass. Modifying fields used as keys concurrently with sorting can cause bugs or even violate the comparator contract.

`thenComparingInt`, `thenComparingLong`, and `thenComparingDouble` fit primitive keys well; not every lambda needs manual micro-optimization. On small datasets, a clear comparator expression usually matters more than a few minor allocations.

## 10. Common Mistakes

| Mistake | Possible outcome | Fix |
| --- | --- | --- |
| Putting `reversed()` at the end of the chain when intending to reverse only the last key | Reverses all chained keys | Reverse only that key's comparator and pass it into `thenComparing` |
| Changing the order of `thenComparing` calls | Alters business precedence | Write out the required key order in plain words first |
| Omitting a final distinguishing key | Many objects have `compare == 0`; `TreeSet` merges entries | Consider a domain-appropriate stable ID |
| Using `String.CASE_INSENSITIVE_ORDER` and assuming `compare == 0` equals `String.equals` | Two strings differing in case are treated as one in a sorted set | Separate display semantics from identity semantics |
| Forgetting a `null` policy | Throws `NullPointerException` during sort | Apply `nullsFirst/nullsLast` at the proper scope |
| Using subtraction `a.id() - b.id()` | Overflow flips signs or breaks contract | Use `comparingInt` or `Integer.compare` |
| Using a secondary comparator over mutable state | Inconsistent results across comparisons | Use stable keys during sorting and while stored in ordered collections |
| Using a comparator with side effects or randomness | Violates transitivity or consistency | Make the comparator a deterministic comparison |
| Assuming String natural order equals Vietnamese linguistic order | Inappropriate display order | Choose locale collation or application-specific rules |
| Assuming `thenComparing()` mutates the original comparator in place | Drops the secondary comparator because return value is discarded | Assign the chained result to a new comparator variable |

## 11. Self-Check Exercises

**Exercise 1.** Given an `Order` class with `status()` returning String and `priority()` returning int. Requirement: status ascending, and within the same status, higher priority first. How should the comparator be written?

**Answer (snippet):**

```java
Comparator<Order> order =
    Comparator.comparing(Order::status)
        .thenComparing(
            Comparator.comparingInt(Order::priority).reversed()
        );
```

### Exercise 2. Why does `compare(a, b) == 0` not imply `a.equals(b)`?

Because the comparator inspects only the chosen set of keys; `equals` may inspect a different set of fields. For instance, a record with a different salary still yields 0 if the comparator only checks department, level, name, and employeeId. In `TreeSet`, this also affects the number of stored elements.

### Exercise 3. Which key does `Comparator.comparing(Employee::department).thenComparingInt(Employee::level).reversed()` reverse?

It reverses **the entire chain department then level**, because `reversed()` is called on the combined comparator. If you only want `level` descending, reverse `Comparator.comparingInt(Employee::level)` inside `thenComparing(...)`.

### Exercise 4. If name can be `null` and nulls must come last while remaining names sort descending, what should be used?

```java
Comparator<Employee> byName =
    Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(Comparator.reverseOrder())
    );
```

With the comparator for the **name key** above, nulls appear after other names; non-null names are sorted descending.

### Exercise 5. A `TreeSet` uses a comparator based solely on `age`. What happens to two objects of age `20` with different IDs?

Both have `compare == 0`, so `TreeSet` considers them equivalent and keeps only one element. To store both, the comparator needs a suitable tie-breaking key such as ID.

### Exercise 6. How does `thenComparingInt` differ practically from `thenComparing(Person::age)`?

`thenComparingInt` takes a primitive `int`, matching a getter returning `int` and avoiding boxing to `Integer` during comparison. With nullable `Integer` getters, you cannot directly use a primitive extractor while preserving `null` semantics; you need a wrapper comparator with a null policy.

### Exercise 7. A list is sorted by `team`, and then sorted again by `name`. Is that always the same as multi-key sorting with `thenComparing`?

No. Because `List.sort` is stable, if you first sort by the **secondary key `name`** and then sort by the **primary key `team`**, the result can match `team -> name` when comparators are valid and data does not change. However, if you sort by the primary key first and the secondary key second, the secondary key becomes the main priority. Using `thenComparing` directly is clearer and avoids depending on the order of multiple sort passes.

---

**Takeaway:** `Comparator.comparing(...)` defines the **highest-priority key**; each `thenComparing(...)` adds a **fallback key** used only when preceding keys tie. Explicitly choose ascending/descending per key, the `null` policy, and string comparison rules. When using a comparator with `TreeSet`/`TreeMap`, pay close attention to `compare == 0` because it determines whether two keys are treated as duplicates.