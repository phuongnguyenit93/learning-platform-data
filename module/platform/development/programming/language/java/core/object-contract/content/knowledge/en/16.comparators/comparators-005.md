# `Comparator.reversed()` and Where to Apply It in a Comparison Chain

## 1. The Core Rule

`Comparator<T>` describes the comparison order of objects of type `T`. In Java, **`reversed()` returns a new comparator that reverses the order of the comparator on which it is called**. This is especially important when combining multiple criteria with `thenComparing(...)` or `thenComparingInt(...)`.

For example, sorting employees by:

1. `department`, ascending.
2. Within the same department, `age`, ascending.

You can write:

~~~java
Comparator<Employee> byDepartment =
        Comparator.comparing(Employee::department);
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> base = byDepartment.thenComparing(byAge);
~~~

This is an **illustrative snippet**, assuming class or record `Employee` has two accessors `department()` and `age()`. `thenComparing` uses the next criterion **only when the preceding comparator returns `0`**. This is left-to-right comparison (*lexicographic ordering*).

An easy point of confusion is that `reversed()` **reverses the entire comparator built up to the call site**, rather than defaulting to reversing only the criterion immediately adjacent to it. Think of it in terms of parentheses:

~~~text
(c1.thenComparing(c2)).reversed()
    -> reverses the order of the entire chain c1 then c2

c1.reversed().thenComparing(c2)
    -> reverses c1; if tied on c1, c2 keeps its original direction

c1.thenComparing(c2.reversed())
    -> keeps c1; if tied on c1, reverses only c2
~~~

**The method call order determines the scope of reversal.** `reversed()` does not mutate the original data, does not sort any list by itself, and does not change how `equals()` behaves on objects.

## 2. Understanding the Sign of `compare(a, b)`

By the `Comparator.compare(a, b)` contract:

- Returns a **negative number**: `a` comes before `b`.
- Returns **`0`**: the two objects are equivalent under the current comparator; only then does `thenComparing` need to check the next criterion.
- Returns a **positive number**: `a` comes after `b`.

If `c` is an ascending comparator and `r = c.reversed()`, in terms of ordering `r.compare(a, b)` flips the comparison sign relative to `c.compare(a, b)`. You can picture this as swapping the two arguments when comparing. **Do not reverse manually using subtraction or by negating the raw integer return value of `compare`**: the smallest `int` value (`Integer.MIN_VALUE`) can overflow when negated, and the contract relies only on the sign of the result.

With first criterion `c1` and second `c2`, the combined comparator logically works as follows:

~~~java
// Algorithmic illustration, assuming Comparator<T> c1 and c2 exist.
int result = c1.compare(a, b);
if (result != 0) {
    return result;
}
return c2.compare(a, b);
~~~

`thenComparing` does not "blend" scores together. The first criterion has **higher priority**: only when tied under the preceding criterion do we proceed to the next criterion.

## 3. Four Ways to Place `reversed()`, Four Different Orders

Suppose each object has three components:

- `name`: label to observe output.
- `group`: one of two values `A` or `B`.
- `score`: `10` or `20`.

We want to sort by `group` first, then by `score`.

| How the comparator is built | Group | Score within the same group | Meaning |
| --- | --- | --- | --- |
| `byGroup.thenComparing(byScore)` | A → B | 10 → 20 | Both ascending |
| `byGroup.thenComparing(byScore).reversed()` | B → A | 20 → 10 | Reverses the **entire chain** built so far |
| `byGroup.reversed().thenComparing(byScore)` | B → A | 10 → 20 | Reverses **group** before attaching score |
| `byGroup.thenComparing(byScore.reversed())` | A → B | 20 → 10 | Reverses only **score** as the secondary criterion |

Note: `byGroup.reversed().thenComparing(byScore)` is a new comparator built in the order *group descending, score ascending*. If you call `.reversed()` **after this whole chain**, you reverse both criteria currently present, turning it into *group ascending, score descending*.

A handy mathematical notation to remember:

~~~text
(c1 + c2).reversed()  ≈  c1.reversed() + c2.reversed()
c1.reversed() + c2    =  c1 descending, then c2 in its original direction
c1 + c2.reversed()    =  c1 in its original direction, then c2 descending
~~~

The `+` sign here merely denotes chaining comparators with `thenComparing`, **not Java addition**. The `≈` sign expresses **equivalence in comparison order**, not claiming that the two comparator objects share the same reference or internal implementation structure.

## 4. Standalone Runnable Java 17+ Program

Create the file **`ComparatorReversedDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;

public class ComparatorReversedDemo {
    record Row(String name, String group, int score) {}

    static void show(
            String label, List<Row> rows, Comparator<Row> comparator) {
        List<String> names = rows.stream()
                .sorted(comparator)
                .map(Row::name)
                .toList();
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(
                new Row("b20", "B", 20),
                new Row("a10", "A", 10),
                new Row("b10", "B", 10),
                new Row("a20", "A", 20));

        Comparator<Row> byGroup = Comparator.comparing(Row::group);
        Comparator<Row> byScore = Comparator.comparingInt(Row::score);

        Comparator<Row> allAsc =
                byGroup.thenComparing(byScore);

        Comparator<Row> allDesc =
                byGroup.thenComparing(byScore).reversed();

        Comparator<Row> groupDescScoreAsc =
                byGroup.reversed().thenComparing(byScore);

        Comparator<Row> groupAscScoreDesc =
                byGroup.thenComparing(byScore.reversed());

        show("group ASC, score ASC", rows, allAsc);
        show("all DESC", rows, allDesc);
        show("group DESC, score ASC", rows, groupDescScoreAsc);
        show("group ASC, score DESC", rows, groupAscScoreDesc);

        List<Row> ties = List.of(
                new Row("m1", "A", 10),
                new Row("m2", "A", 10),
                new Row("x", "B", 20));

        show("reverse with equal keys", ties, allDesc);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac ComparatorReversedDemo.java
java ComparatorReversedDemo
~~~

Deterministic output:

~~~text
group ASC, score ASC: [a10, a20, b10, b20]
all DESC: [b20, b10, a20, a10]
group DESC, score ASC: [b10, b20, a10, a20]
group ASC, score DESC: [a20, a10, b20, b10]
reverse with equal keys: [x, m1, m2]
~~~

**Line-by-line explanation:**

1. `allAsc` is the ascending chain by `group` then ascending by `score`: group `A` rows come before group `B`; within each group, score `10` comes before `20`.
2. `allDesc` calls `reversed()` **after `thenComparing` has attached both criteria**. Thus group `B` comes before `A`, and score `20` comes before `10` within each group.
3. `groupDescScoreAsc` calls `reversed()` when the comparator has only `byGroup`. Then `thenComparing(byScore)` attaches the score criterion **remaining ascending**.
4. `groupAscScoreDesc` reverses only the `byScore` comparator before passing it to `thenComparing`. Groups stay ascending while scores within a group are descending.
5. Both `m1` and `m2` have `group = A` and `score = 10`, so `allDesc.compare(m1, m2) == 0`. `Stream.sorted` preserves stability (*stable*) for ordered streams such as `List.stream()`, so the tied rows still appear in their original input order: `m1` before `m2`.

**Important lesson:** reversing a comparator **is not synonymous with reversing an already-sorted list**. If elements have equal comparison keys, a stable sort preserves their relative order; whereas a list-reversal call like `Collections.reverse(list)` flips the order of those tied elements as well.

## 5. Placing `reversed()` with Three Criteria

Suppose you need to sort by three keys in sequence: **department, salary, name**. From left to right, `thenComparing` is only consulted when all preceding criteria result in a tie.

### A. Reverse all chained criteria

~~~java
// Illustrative snippet in a context with an Employee class and accessors.
Comparator<Employee> allDescending =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name)
                .reversed();
~~~

The order is **department descending -> salary descending -> name descending**. `reversed()` is at the end, so it covers **all three keys**.

### B. Reverse the first criterion, keep subsequent criteria ascending

~~~java
Comparator<Employee> departmentDescThenOthersAsc =
        Comparator.comparing(Employee::department,
                             Comparator.reverseOrder())
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name);
~~~

Here only the `department` comparison is reversed right when creating the base comparator, and secondary criteria are attached unchanged. An expression with equivalent ordering is:

~~~java
Comparator<Employee> byDepartment =
        Comparator.comparing(Employee::department);

Comparator<Employee> departmentDescThenOthersAsc =
        byDepartment.reversed()
                .thenComparingInt(Employee::salary)
                .thenComparing(Employee::name);
~~~

These are **two alternative approaches**; do not place both variable declarations with the same name in the same scope.

### C. Reverse only the middle criterion

~~~java
Comparator<Employee> middleDescending =
        Comparator.comparing(Employee::department)
                .thenComparing(
                        Comparator.comparingInt(Employee::salary)
                                  .reversed())
                .thenComparing(Employee::name);
~~~

Order: **department ascending -> salary descending -> name ascending**.

If Java runs into type inference issues with a complex lambda or method reference in the inner comparator, extract a variable with an explicit type:

~~~java
Comparator<Employee> salaryDesc =
        Comparator.comparingInt(Employee::salary).reversed();

Comparator<Employee> middleDescending =
        Comparator.comparing(Employee::department)
                .thenComparing(salaryDesc)
                .thenComparing(Employee::name);
~~~

Each snippet is **illustrative**, assuming `Employee` has `department()` and `name()` returning `String`, `salary()` returning `int`, and `import java.util.Comparator` is present. Only the program in section 4 is a complete standalone runnable Java file.

### D. Reverse a prefix then append a new criterion

~~~java
Comparator<Employee> prefixDescNameAsc =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary)
                .reversed()
                .thenComparing(Employee::name);
~~~

Order: **department descending -> salary descending -> name ascending**. `reversed()` reverses *the two previously chained criteria*, while `thenComparing(Employee::name)` is added **after the reversal step**, so it remains ascending.

This is a critical difference from moving `reversed()` to the very end: when moved to the end, name becomes descending too.

## 6. Two Ways to Write "Reverse One Criterion"

When you want to reverse a specific key, two options are usually clearer than placing `reversed()` mid-way in a long chain:

**Approach 1: pass a key-specific comparator into `comparing` / `thenComparing`.**

~~~java
Comparator<Employee> byDepartmentDescThenNameAsc =
        Comparator.comparing(
                Employee::department, Comparator.reverseOrder())
                .thenComparing(Employee::name);
~~~

`Comparator.reverseOrder()` creates a comparator opposite to the **natural order** of the key's value type. For `String`, natural order is lexicographical by Unicode value; for `Integer`, it is ascending numeric order. Since `department` returns `String`, this reverses only the department key.

**Approach 2: create a sub-comparator and call `reversed()` directly on that sub-comparator.**

~~~java
Comparator<Employee> bySalaryDesc =
        Comparator.comparingInt(Employee::salary).reversed();

Comparator<Employee> byDepartmentAscSalaryDesc =
        Comparator.comparing(Employee::department)
                .thenComparing(bySalaryDesc);
~~~

This approach is particularly readable when the secondary key is a primitive number: `comparingInt` uses an `int` extractor, then `reversed()` reverses the resulting comparator.

**Note:** `Comparator.reverseOrder()` is a `static` method creating a comparator opposite to the natural order of the **key type itself**; `someComparator.reversed()` is an instance method of an existing comparator, reversing the order defined by **that comparator**, even when it consists of multiple keys or custom rules.

## 7. `reversed()` Does Not Break `thenComparing` Precedence

Consider:

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::salary);
~~~

If two employees are in different departments, the comparison result is already decided at `department`; their salaries are never used to "jump ahead" of the department order. Calling `cmp.reversed()` only reverses the grouping order and reverses how salary is ordered **within the same department**.

Similarly, if you write `cmp.reversed().thenComparing(Employee::name)`, the `name` criterion only activates when **both department and salary** fail to distinguish two employees. It neither replaces nor cuts ahead of those criteria.

Therefore, when a sort result differs from expectations, read the comparator chain as a **priority list of criteria**: "compare key 1; if tied, key 2; if still tied, key 3." Then determine precisely which criteria `reversed()` covered at the point it was called.

## 8. Cases to Watch Out For

### `null` keys and `nullsFirst`/`nullsLast` placement

When keys can be `null`, `Comparator.naturalOrder()` and `Comparator.reverseOrder()` do not allow `null` by themselves. You can use `Comparator.nullsFirst(...)` or `Comparator.nullsLast(...)` to define where `null` goes.

Example:

~~~java
// Illustrative snippet with String values.
Comparator<String> nullLastAsc =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> nullFirstDesc = nullLastAsc.reversed();

Comparator<String> nullLastDesc =
        Comparator.nullsLast(Comparator.reverseOrder());
~~~

- `nullLastAsc`: non-null strings ascending; `null` at the end.
- `nullFirstDesc`: reverses the **entire** `nullLastAsc`; non-null strings descending **and `null` moves to the front**.
- `nullLastDesc`: non-null strings descending, yet **`null` stays at the end**.

This further illustrates that `reversed()` reverses the order of the **entire current comparator**, including any `null` rule wrapped into the comparator before the reversal.

### `compare(...) == 0` and ordered collections

Two objects that differ under `equals()` can still have `comparator.compare(a, b) == 0` if all selected keys are equal. `TreeSet` and `TreeMap` rely on the comparator to determine whether two elements or keys are equivalent in the structure; thus they can treat two objects that are distinct under `equals()` as the same key if the comparator returns `0`.

If you want to keep objects distinct by an identifier key, append `thenComparing(Employee::id)` or a terminal criterion matching the data semantics. Note: adding the terminal criterion **before or after `reversed()`** continues to determine that criterion's direction.

### Comparators with invalid ordering

A comparator must obey the contract of sign symmetry, transitivity, and consistency. For instance, writing `return a.score() - b.score();` risks integer overflow, causing the sign not to reflect true numeric order. Use `Comparator.comparingInt(Employee::score)` or `Integer.compare(a.score(), b.score())`.

`reversed()` cannot fix an underlying comparator that already violates the contract. A broken comparator can cause sorting algorithms or ordered structures to behave unexpectedly.

### Case sensitivity and Locale

`Comparator.comparing(Employee::name)` uses `String`'s natural order, which does not automatically apply linguistic rules for personal names. If an order for a specific language is needed, choose a suitable key comparator (such as a properly configured `Collator`) before reversing if needed. Reversing a linguistic comparator applies to **the exact order that comparator produces**.

## 9. Quick Comparison of Common Expressions

| Expression | First criterion | Second criterion |
| --- | --- | --- |
| `c1.thenComparing(c2)` | c1 direction | c2 direction |
| `c1.thenComparing(c2).reversed()` | Reverse c1 | Reverse c2 |
| `c1.reversed().thenComparing(c2)` | Reverse c1 | c2 direction |
| `c1.thenComparing(c2.reversed())` | c1 direction | Reverse c2 |
| `c1.reversed().thenComparing(c2).reversed()` | c1 direction | Reverse c2 |

In the table, `c1` and `c2` are valid comparators for the **same element type**. "Direction" means the rule defined by each base comparator, not necessarily natural order. For example, in the last row: the first reversal affects `c1`, then `c2` is chained; the final reversal reverses the entire chain built so far, returning `c1` to its original direction while `c2` becomes reversed.

When chains get long, it is usually better to **name the sub-comparators** rather than chaining multiple `reversed()` calls in a row. Names like `byGroupDesc` and `byScoreAsc` make it easy to verify directly against business requirements.

## 10. Self-Check Exercises

**Exercise 1.** What is the result of the following chain by department and age keys?

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .reversed()
                .thenComparingInt(Employee::age);
~~~

**Answer:** Department **descending**, then age **ascending** within the same department.

**Exercise 2.** How do you write it if you want both department and age descending?

~~~java
Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparingInt(Employee::age)
                .reversed();
~~~

**Answer:** Place `reversed()` after chaining both criteria as above, or reverse each sub-comparator individually and then chain them.

**Exercise 3.** How do you make department ascending, age descending, and name ascending?

~~~java
Comparator<Employee> ageDesc =
        Comparator.comparingInt(Employee::age).reversed();

Comparator<Employee> cmp =
        Comparator.comparing(Employee::department)
                .thenComparing(ageDesc)
                .thenComparing(Employee::name);
~~~

**Answer:** Reverse the `ageDesc` comparator before attaching it as the second criterion; `department` and `name` remain in natural order.

**Exercise 4.** Is `cmp.reversed()` the same as `Collections.reverse(sortedList)`?

**Answer:** Not completely. Reversing the comparator and re-sorting produces the reverse order by the comparison keys, but objects considered equal by the comparator can preserve their relative order when using a stable sorting algorithm. `Collections.reverse` flips the positions of all elements, including tied elements.

**Exercise 5.** If `Comparator.nullsLast(Comparator.naturalOrder()).reversed()` is used, where is `null` placed?

**Answer:** `null` moves to the **front**, because `reversed()` also reverses the null policy wrapped inside the comparator.

**Takeaway:** `reversed()` affects the **entire comparator formed up to the call point**. To reverse all chained keys, call it at the end. To reverse a single key, reverse that key's sub-comparator before chaining or supply a reversed comparator in `comparing`/`thenComparing`. Always double-check precedence order when multiple criteria are involved.

## References

- [Java SE 17 — `Comparator` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — `Stream.sorted` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator))