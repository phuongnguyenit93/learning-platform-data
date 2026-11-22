# Multi-Key Sorting and Handling Null Keys in Java Stream

When data has multiple sorting criteria, a single key is often not enough. For example, an employee list might need **department ascending → age ascending → name ascending**; a score list might need **score descending → team ascending → ID ascending**. In practice, some fields are `null`. If you write a comparator without specifying how `null` should be placed, the `Stream.sorted()` pipeline can throw a `NullPointerException` or return results that violate business logic.

Java solves this problem by **chaining `Comparator`s in priority order** and placing `Comparator.nullsFirst()`/`nullsLast()` at the **right level**:

- `Comparator.comparing(...)`, `comparingInt(...)`, `comparingLong(...)`, `comparingDouble(...)`: define the primary criterion.
- `thenComparing(...)`, `thenComparingInt(...)`, ...: add subsequent criteria, used only when preceding criteria return equal results.
- `Comparator.nullsFirst(c)` or `nullsLast(c)`: handle **the object directly compared by `c`**. This can be either a *key value* or *the entire element* depending on where it is placed.
- `Comparator.reverseOrder()` and `reversed()`: reverse the order; they must be placed at the right level to preserve the desired `null` policy.

This lesson uses Java 17+ and emphasizes reading a comparator in the order **primary key → secondary key → null policy → sort direction**.

## 1. How `thenComparing` Determines Order

A `Comparator<T>` compares two elements and returns:

- A negative value if the first element comes before the second element;
- `0` if the two elements are equal **according to the comparator's criterion**, even if they are not necessarily `equals()`;
- A positive value if the first element comes after the second element.

With `comparatorA.thenComparing(comparatorB)`:

1. Try key A.
2. If A yields a non-zero result, keep that result and **do not call** comparator B.
3. Only when A returns `0`, proceed to compare key B.
4. Can be chained multiple times to create a third key, fourth key, and so on.

Example:

~~~java
Comparator<Employee> order =
        Comparator.comparing(Employee::department)
                  .thenComparingInt(Employee::age)
                  .thenComparing(Employee::name);
~~~

This is an **illustrative snippet**, assuming `Employee.department()` and `Employee.name()` return a non-null `String`, while `Employee.age()` returns `int`. `department` is the primary key, `age` is the secondary key, and `name` is the third key. Because subsequent keys are only evaluated when preceding keys are equal, **the order of `thenComparing` calls is the priority of the keys**.

`Comparator.comparingInt` takes a `ToIntFunction<T>` and uses proper `int` comparison, avoiding boxing just to represent a primitive key. For a nullable `Integer` field, **do not use `comparingInt` directly** if you want to preserve null as a distinct state, because the unboxing step to `int` can cause an error.

## 2. Distinguishing Three Types of Nulls to Handle

When sorting a `List<Employee>`, you may encounter the following levels:

| Null location | Example | Problem | How to handle |
| --- | --- | --- | --- |
| **Element** in the list | `null` instead of `Employee` | Method reference `Employee::department` cannot be called on a null element | Wrap the **entire element comparator** with `Comparator.nullsFirst(...)` or `nullsLast(...)`. |
| **Primary key** in the object | `employee.department() == null` | Natural comparator of `String` cannot compare null | Use `comparing(Employee::department, nullsLast(naturalOrder()))`. |
| **Secondary key** in the object | `employee.age() == null` (type `Integer`) | `comparingInt` has to unbox a `null Integer` | Use `thenComparing(Employee::age, nullsLast(naturalOrder()))`. |

Furthermore, the name field used as a tie-breaker can be null and needs its own policy. **A single `nullsLast` layer does not automatically protect every level.** For example:

~~~java
// Handles null Employee objects only, NOT null department keys:
Comparator<Employee> incomplete = Comparator.nullsLast(
        Comparator.comparing(Employee::department));
~~~

If `Employee` is present but `department` is null, the inner comparator can still throw a `NullPointerException`.

Conversely:

~~~java
// Handles null department, NOT null Employee elements:
Comparator<Employee> alsoIncomplete = Comparator.comparing(
        Employee::department,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

If a list element is null, the expression `Employee::department` still cannot run. The solution when **both levels are nullable** is to wrap the outermost comparator after building the inner keys.

## 3. Complete Example: Department, Age, Name, and Multi-Level Nulls

Define the business rules:

1. Department **ascending**, null department **after** departments with values;
2. Within the same department, `Integer` age **ascending**, null age **after** ages with values;
3. If both department and age are equal, name **ascending**;
4. If the `Employee` element itself is null, place it **last**.

Create the file `MultiKeyNullSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class MultiKeyNullSortDemo {
    record Employee(String name, String department, Integer age) {}

    public static void main(String[] args) {
        List<Employee> employees = new ArrayList<>(Arrays.asList(
                new Employee("An", "Sales", 28),
                new Employee("Bình", null, 22),
                new Employee("Chi", "HR", null),
                new Employee("Dũng", "HR", 22),
                new Employee("Em", "Sales", null),
                new Employee("Gia", null, null),
                null
        ));

        Comparator<Employee> nonNullEmployees =
                Comparator.comparing(
                        Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(
                        Employee::age,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(
                        Employee::name,
                        Comparator.nullsLast(Comparator.naturalOrder()));

        Comparator<Employee> order =
                Comparator.nullsLast(nonNullEmployees);

        List<Employee> sorted = employees.stream()
                .sorted(order)
                .toList();

        for (Employee employee : sorted) {
            if (employee == null) {
                System.out.println("<null employee>");
            } else {
                System.out.println(
                        employee.department() + " | "
                        + employee.age() + " | "
                        + employee.name());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 MultiKeyNullSortDemo.java
java MultiKeyNullSortDemo
~~~

Output:

~~~text
HR | 22 | Dũng
HR | null | Chi
Sales | 28 | An
Sales | null | Em
null | 22 | Bình
null | null | Gia
<null employee>
~~~

Reading the comparator from the inside out:

- `Comparator.comparing(Employee::department, ...)`: creates the `String` department key. The **key's** comparator is wrapped with `nullsLast`.
- `.thenComparing(Employee::age, ...)`: compares age only when two departments are equal; null `Integer` keys are placed last.
- `.thenComparing(Employee::name, ...)`: name is the third key, guarding against null names for extensible data.
- `Comparator.nullsLast(nonNullEmployees)`: covers **null elements themselves**. Getters are only called when both `Employee` instances are non-null.

`employees.stream().sorted(order)` **does not sort the original list in place**; `toList()` returns a result list that does not support modification operations. If you need to sort a modifiable list in place, call `employees.sort(order)` on the `ArrayList`.

Common pitfall: `List.of(...)` does not allow null elements. The example intentionally uses `Arrays.asList(...)` wrapped in `ArrayList`; that approach allows null values in the input data.

## 4. Designing Multiple Keys with Independent Ascending/Descending Directions

A common requirement is **highest score first**, then **team alphabetically**, then **ID ascending**. At the same time, score and team can be null and must be at the end of their respective groups.

You should not reverse an entire comparator that already has a null policy; instead, place the comparison direction directly **inside each key's comparator**.

Create the file `MixedDirectionSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class MixedDirectionSortDemo {
    record Entry(String label, Integer score, String team, int id) {}

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>(Arrays.asList(
                new Entry("A", 90, "red", 2),
                new Entry("B", 90, null, 1),
                new Entry("C", null, "blue", 3),
                new Entry("D", 100, "blue", 4),
                null,
                new Entry("E", 90, "red", 1)
        ));

        Comparator<Entry> nonNullEntries =
                Comparator.comparing(
                        Entry::score,
                        Comparator.nullsLast(Comparator.reverseOrder()))
                .thenComparing(
                        Entry::team,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparingInt(Entry::id);

        Comparator<Entry> order =
                Comparator.nullsLast(nonNullEntries);

        entries.stream()
                .sorted(order)
                .forEach(entry -> System.out.println(
                        entry == null ? "<null>" : entry.label()));
    }
}
~~~

~~~bash
javac --release 17 MixedDirectionSortDemo.java
java MixedDirectionSortDemo
~~~

Output:

~~~text
D
E
A
B
C
<null>
~~~

Output explanation:

- `D` has score 100, coming before scores of 90.
- `E` and `A` both have score 90 and team `red`; E's ID 1 comes before A's ID 2.
- `B` also has score 90, but its team is null, so it comes after team `red` with the same score.
- `C` has a null score and therefore comes after entries with scores.
- The `null` element comes last thanks to the outermost wrapping comparator.

Using `Comparator.reverseOrder()` **inside** `nullsLast(...)` only reverses non-null scores; nulls remain at the end. This is the correct implementation order when the specification is "descending, missing scores last".

## 5. The `reversed()` Trap: Reversing the Null Policy Too

Consider the expressions:

~~~java
// Assuming Entry::score returns Integer, and Entry is non-null.
Comparator<Entry> descNullLast = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.reverseOrder()));

Comparator<Entry> descButNullFirst = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.naturalOrder()))
        .reversed();
~~~

The first expression is **score descending with nulls last**. The second expression builds "score ascending, nulls last" first, and then calls `reversed()` on the **entire comparator**, resulting in "score descending, nulls first".

If you already have:

~~~java
Comparator<Entry> order = Comparator.nullsLast(
        Comparator.comparingInt(Entry::id));
~~~

then `order.reversed()` not only changes ID from ascending to descending, it **also moves null Entry elements to the front**. To keep nulls last while reversing the ID, reverse the inner comparator first:

~~~java
Comparator<Entry> descIdNullLast = Comparator.nullsLast(
        Comparator.comparingInt(Entry::id).reversed());
~~~

The snippets in this section are **method-scoped illustrations** using an existing `Entry` class. General rule: **reverse the criterion that needs reversing first, and apply the null policy at the layer where it should be preserved afterward**.

## 6. Placing `nullsLast` at the End of a Multi-Key Chain

A subtle mistake is adding `thenComparing` **after** already wrapping the whole element with `nullsLast`:

~~~java
// Dangerous if the input contains two null elements:
Comparator<Employee> unsafe =
        Comparator.nullsLast(
                Comparator.comparing(Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder())))
                  .thenComparing(Employee::name);
~~~

When **both Employees are null**, `nullsLast` considers them equal and returns `0`. The outer `thenComparing(Employee::name)` then proceeds to call the getter on null, causing a `NullPointerException`.

A safer structure:

~~~java
Comparator<Employee> safe = Comparator.nullsLast(
        Comparator.comparing(
                        Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                  .thenComparing(
                        Employee::name,
                        Comparator.nullsLast(Comparator.naturalOrder())));
~~~

Now the null layer for the **Employee object** is outside the entire chain, handling null elements before calling any getter. If name is non-nullable and the data is guaranteed non-null, the secondary key comparator can be written as `thenComparing(Employee::name)` for conciseness.

## 7. `comparingInt`, `comparingLong`, and Nullable Keys

When the key is actually a primitive `int`, use:

~~~java
Comparator<Entry> byId = Comparator.comparingInt(Entry::id);
~~~

When the key is a nullable `Integer`, the following approach is **unsafe**:

~~~java
// Illustrates the risk; do not run this code when score == null.
Comparator<Entry> unsafeScore =
        Comparator.comparingInt(e -> e.score());
// e.score() returns Integer; Java auto-unboxes to int and may throw NPE.
~~~

Replace with:

~~~java
Comparator<Entry> safeScore = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

`Comparator.comparingLong` and `comparingDouble` also use the corresponding primitive extractors; if a getter returns a nullable `Long`/`Double`, you need a null policy via `comparing` for wrapper types or an explicit replacement rule.

You can convert null to a sentinel number to keep using `comparingInt`, but only when the business logic **truly defines null as equivalent to that value**:

~~~java
Comparator<Entry> fallback = Comparator.comparingInt(
        e -> e.score() == null ? -1 : e.score());
~~~

If an actual score can be -1, the two cases "missing score" and "score -1" become the same key. Use `nullsLast` for `Integer` when they need to be clearly distinguished.

Do not write numeric comparators like `(a, b) -> a.id() - b.id()`: subtraction can overflow `int`, breaking the comparator contract. `comparingInt` uses proper integer comparison instead of relying on subtraction.

## 8. Data Types at Each Step in a Stream Pipeline

With `Stream<Employee>`, the `sorted(comparator)` operation **does not change the element type**:

~~~text
List<Employee>
  .stream()                             → Stream<Employee>
  .filter(Objects::nonNull)              → Stream<Employee>
  .sorted(Comparator<Employee>)          → Stream<Employee>
  .map(Employee::name)                   → Stream<String>
  .toList()                              → List<String>
~~~

Sorting should be performed on the type containing **all required keys**. For example, if you map `Employee` to the `String` name before sorting, `Stream<String>` no longer has access to department and age for multi-key comparison.

If the requirement is to remove null elements instead of placing them first/last, you can proactively filter them out:

~~~java
// Assuming employees is List<Employee> and comparator is for non-null Employee.
List<Employee> valid = employees.stream()
        .filter(java.util.Objects::nonNull)
        .sorted(nonNullEmployees)
        .toList();
~~~

This **changes the result set** (removing nulls), which is different from sorting while keeping all elements. Do not use `filter(Objects::nonNull)` merely to hide the lack of a business policy.

## 9. Stability and Equal Keys

`List.sort` is a **stable** sort: if the comparator returns `0`, the original relative order of those elements is preserved. `Stream.sorted` also guarantees stability for an **ordered stream**; for an unordered stream, there is no such guarantee.

For example, two `Employee` instances with the same department and age will be compared by name if `thenComparing(Employee::name)` is present. If their names are also equal, the comparator returns `0`; with an ordered stream, they retain their initial encounter order.

This has two practical implications:

1. If you want pagination or report output to have a **fully deterministic** order even when business keys collide, add a stable tie-breaker key (such as a unique `id`) at the end of the chain.
2. `Comparator.compare(a, b) == 0` does not mean `a.equals(b)`. In `TreeSet`/`TreeMap`, elements/keys are considered duplicates according to the comparator if it returns `0`, so lacking a distinguishing key can cause data to be merged in those structures.

With streams from a `HashSet` or sources without a defined encounter order, do not rely on stability to infer order among elements with equal keys. Provide a complete tie-breaker key if reproducible output is needed.

## 10. Cost and Execution Behavior of `sorted`

`Stream.sorted()` is a **stateful** intermediate operation. To sort an entire finite set by multiple keys, the system generally needs to hold enough data to determine the order; you should not assume it can emit results one by one starting from the first element like a pure `filter`. Creating a comparator is cheap, but sorting typically has a cost that grows with input size (commonly around `O(n log n)` comparisons, depending on the algorithm and data).

**Key extractor functions can be called multiple times**, so you should avoid:

- database/network queries inside `Comparator.comparing(x -> expensiveLookup(x))`;
- mutating state in a getter or `thenComparing`;
- depending on a clock or continuously changing information when the comparator is called;
- executing logic with side effects such as writing files, sending notifications, or modifying the objects being sorted.

If a key is expensive or mutable, compute a **snapshot key** before sorting, then compare on the stable value. For large datasets, measure actual cost; avoid recomputing the same key multiple times during comparisons. Optimizations must preserve all null rules and key ordering.

A stream pipeline like:

~~~java
// Illustrates the processing structure; source is Stream<Employee>.
source.sorted(order).limit(10).toList();
~~~

usually still has to examine a large enough range of data to find the **10 smallest elements** according to the comparator; placing `limit(10)` after `sorted` does not mean sorting only the first 10 elements of the source. You should not use `sorted` on an infinite source and expect `limit` to always produce a finite result.

## 11. String Keys and Locale-Based Ordering

`Comparator.naturalOrder()` for `String` uses natural ordering based on `String.compareTo`. This is ordering by UTF-16 character values, **not necessarily Vietnamese dictionary order** or a natural order suitable for human readers.

If the application needs language-specific ordering, use a localized comparison strategy, such as `Collator` from `java.text` with the appropriate locale. Because `Collator` has mutable configuration, set up and manage instances carefully, especially with parallel sorting. If you need to handle null `String` keys, wrap that language comparator with `nullsFirst`/`nullsLast` just like a natural comparator.

Structural illustration example:

~~~java
// Inside a method where type Employee and related types are imported.
java.text.Collator collator =
        java.text.Collator.getInstance(java.util.Locale.forLanguageTag("vi-VN"));

Comparator<Employee> byVietnameseName = Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(collator));
~~~

Examples using `naturalOrder()` in this lesson only specify **Java natural order**, and do not assert cultural/locale-based name sorting rules.

## 12. Verifying Output and Testing Comparators

A multi-key comparator should be tested against at least the following cases:

| Scenario | What to verify |
| --- | --- |
| Two different primary keys | Primary key takes proper precedence; secondary key does not override it. |
| Same primary key, different secondary keys | `thenComparing` handles the direction properly. |
| Multiple equal keys | Final key breaks the tie, or stability holds when the comparator returns `0`. |
| Null / non-null primary key | Null is placed first or last as specified. |
| Null / non-null secondary key | Null in secondary fields does not cause unboxing or NPE. |
| Null / non-null element | Outermost comparator wraps properly. |
| Two elements both null | Secondary key getters are not called on null. |
| Negative scores, 0, extreme numbers | No overflowing subtraction is used; sentinels are handled validly. |
| `reversed()` and multiple sort directions | Only the intended criterion changes; nulls stay in their proper positions. |
| Equal-key data from an unordered source | A tie-breaker key is present if deterministic order is required. |

A comparator needs a consistent ordering: antisymmetry, transitivity, and comparison results must be based on stable data. An "arbitrary" comparator that returns different results for the same two objects can cause `sort` to fail, even throwing `IllegalArgumentException` with a message that the comparator violates its general contract. Do not handle errors by catching exceptions and unconditionally returning `0`: fix the ordering relation instead.

One manual verification method is writing the expected key sequence alongside a sample set, for example:

~~~text
Requirement: department ASC NULLS LAST
        → age ASC NULLS LAST
        → name ASC NULLS LAST
        → Employee NULLS LAST

HR / 22 / Dũng
HR / null / Chi
Sales / 28 / An
Sales / null / Em
null / 22 / Bình
null / null / Gia
<null employee>
~~~

This is why the empty department key comes **after** Sales even though Bình's age is 22. A secondary key must never override the priority of a primary key.

## 13. Common Mistakes

1. **Using `comparingInt` with a nullable `Integer` field:** auto-unboxing can throw an NPE; use `comparing` with a null-safe key comparator.
2. **Wrapping `nullsLast` at the outermost layer and thinking all null getters are safe:** the outer layer only handles null elements, not nullable keys.
3. **Placing `thenComparing` after the null-element wrapper:** when both elements are null, secondary key getters can still be called.
4. **Calling `reversed()` on a null-wrapped comparator:** the nulls-first/last policy gets unintentionally reversed.
5. **Reordering `thenComparing` arbitrarily:** an earlier key always has higher priority than a later key.
6. **Sorting after `map` loses the keys:** a `Stream<String>` no longer has enough data to compare by the original object's age and department.
7. **Omitting a tie-breaker key when stable results across sources are needed:** unordered sources and data with many colliding keys can cause non-deterministic ordering.
8. **Confusing `Stream.sorted` with in-place sorting:** it returns a new stream in the pipeline; `List.sort` on a mutable list is what mutates the list.
9. **Treating `String.compareTo` order as Vietnamese order:** if localization is required, use an appropriate comparator.
10. **Using key extractors with side effects or frequently changing data:** this can violate the comparator contract and create hard-to-reproduce bugs.

## 14. Practical Rules

To write a comparator for multiple keys with nulls, follow this order:

1. Clearly write down the **key order** per the specification (primary key first, then secondary keys).
2. For **each key**, determine whether its type is primitive or reference and whether it can be null.
3. Separately define **ASC/DESC direction** and **NULLS FIRST/LAST** for each key.
4. Use `comparing` for nullable reference keys and `comparingInt/Long/Double` for appropriate primitive keys.
5. Chain all keys with `thenComparing`, including a tie-breaker key if needed.
6. If **the element itself** can be null, wrap the complete comparator with `nullsFirst`/`nullsLast` at the very end.
7. Test with data containing equal keys, nulls at various levels, and boundary values; verify that the printed order matches the requirements.

**Remember:** with multiple keys, `thenComparing` determines **priority**; the comparator inside `comparing(..., keyComparator)` determines **the order and null policy of each key**; and the `nullsFirst/nullsLast` layer wrapping the entire comparator determines **the position of null elements**. Placing each layer correctly makes `Stream.sorted()` clear, safe, and easy to test.
