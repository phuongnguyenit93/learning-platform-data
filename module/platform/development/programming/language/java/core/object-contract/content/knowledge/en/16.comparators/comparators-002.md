# Sign Contract, Transitivity, and Groups with Comparison Result 0

## 1. A Comparator Defines an Ordering Relation, Not Just a Sorting Formula

`java.util.Comparator<T>` represents a rule for comparing two values of the same type `T`. Its central method is:

```java
int compare(T a, T b);
```

This is an **illustrative signature from the interface**, not a standalone runnable program. When calling `compare(a, b)`, the meaning of the result's **sign** is:

| Return value | Meaning |
| --- | --- |
| Less than `0` | `a` comes before `b`. |
| Equal to `0` | `a` and `b` belong to **the same equivalence group according to the comparator**. |
| Greater than `0` | `a` comes after `b`. |

The exact number does not matter: `-7` and `-1` both represent "less than"; `42` and `1` both represent "greater than". Therefore, check `compare(a,b) < 0`, `== 0`, `> 0`, or use `Integer.signum(...)` when comparing signs. Do not attach rank, distance, or business magnitude directly to the absolute value of the result.

A **valid** `Comparator` must produce a consistent relation over the entire domain of objects allowed for comparison. If it only appears right on a few pairs while violating the sign contract or transitivity, `List.sort`, `Collections.sort`, `Arrays.sort`, `TreeSet`, and `TreeMap` may behave contrary to what you expect. Some sorting algorithms may detect violations and throw `IllegalArgumentException: Comparison method violates its general contract!`; you must not rely on the error always being detected or always occurring.

## 2. Sign Contract: Reversing Argument Order Must Flip the Sign

For valid objects `x` and `y`, Comparator requires:

```text
sgn(compare(x, y)) == -sgn(compare(y, x))
```

Where `sgn(n)` is the sign of `n`: `-1`, `0`, or `1`. In other words:

- If `compare(x, y) < 0`, then `compare(y, x) > 0`.
- If `compare(x, y) > 0`, then `compare(y, x) < 0`.
- If `compare(x, y) == 0`, then `compare(y, x) == 0`.

This is a rule of **sign symmetry**; it does not require the two integer results to have opposite magnitudes. For example, `compare(x,y) == -10` and `compare(y,x) == 5` still satisfy the sign condition, although it is usually easier to understand if a comparator returns `-1`, `0`, `1`. This condition also has a corollary: if a call in one direction throws an exception for a pair, the reverse direction must not arbitrarily return a meaningful sign as if the pair were valid.

Standard implementation when comparing an integer field:

```java
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

*This snippet assumes the `Task` type has a `priority()` accessor returning `int` and is placed where a variable can be declared; the complete program is in section 6.*

`Comparator.comparingInt` uses standard integer comparison rules; when two values are equal, the result is `0`, and when they differ, the result carries the corresponding sign.

### Why not write subtraction mechanically?

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

This way of writing is **unsafe** across the entire `int` range because subtraction can cause integer overflow. For example:

```java
int a = Integer.MIN_VALUE;
int b = 1;

System.out.println(a - b);             // 2147483647: integer overflow
System.out.println(Integer.compare(a, b)); // -1: correct order
```

Use `Integer.compare(a,b)`, `Long.compare(...)`, or factories such as `comparingInt`, `comparingLong`, `comparingDouble`. Similarly, do not invert a comparator by arbitrarily doing `-compare(a,b)`: if the result is `Integer.MIN_VALUE`, the sign of the negation can still be wrong due to overflow. `comparator.reversed()` or swapping the argument order appropriately expresses the intent more clearly.

## 3. Transitivity: No Ordering Cycles Allowed

The Comparator contract requires:

```text
compare(x, y) > 0 and compare(y, z) > 0
    => compare(x, z) > 0
```

Thanks to sign symmetry, the equivalent statement for the "less than" direction is:

```text
x < y and y < z  =>  x < z
```

For example, priorities `1 < 2 < 3` must yield `1 < 3`. If a comparator concludes `A < B`, `B < C`, yet `C < A`, we have a cycle that cannot be arranged into a consistent order. A "rock–paper–scissors" comparator defining A beats B, B beats C, C beats A might be useful for a game, but it is **unsuitable as a sorting rule**.

Transitivity must hold for **every triple** of valid values, not just three common cases. For multi-criteria comparators, compare fields sequentially in a fixed priority order, and only fall back to the next criterion when the previous criterion ties. `thenComparing(...)` helps express this rule.

Example of a comparator built from components that already have valid orderings:

```java
Comparator<Task> ordering = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::team)
        .thenComparing(Task::code);
```

*This is an illustrative snippet inside a class/method that has the `Task` type. `team()` and `code()` return non-`null` `String`.*

The order is: lower priority comes first; if priorities are equal, compare team name; if both are equal, compare task code. With `String` using natural order, such a set of criteria is usually much easier to analyze and verify for transitivity than a chain of `if` statements returning arbitrary signs.

## 4. `compare == 0` Forms Order-Equivalence Groups

An often-overlooked point: `compare(x,y) == 0` **does not necessarily mean `x.equals(y)`**.

For example, a comparator considering only `priority`:

```java
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

The following tasks can all have priority `2`:

```text
Task(team="alpha", priority=2, code="A")
Task(team="alpha", priority=2, code="B")
Task(team="beta",  priority=2, code="C")
```

They differ in `team` or `code`, so they may not be equal according to `equals()`, yet the comparator returns `0` for every pair in the priority-`2` group. This is a decision to **intentionally ignore criteria outside the ordering**, causing the comparator to view the whole group as a single shared rank.

Define the relation `x ~ y` when `compare(x,y) == 0`. For a valid comparator, this relation must be an **equivalence relation**:

1. **Reflexive:** `compare(x,x) == 0`.
2. **Symmetric:** if `compare(x,y) == 0`, then `compare(y,x) == 0`.
3. **Transitive:** if `compare(x,y) == 0` and `compare(y,z) == 0`, then `compare(x,z) == 0`.

Furthermore, two elements that lie in the **same 0-group** must have the same ordering relation with **every third element**:

```text
compare(x, y) == 0
    => sgn(compare(x, z)) == sgn(compare(y, z))
       for every valid z
```

For example, if `x` and `y` are in the same priority-2 group and `z` has priority 5, then both must come before `z`. You must not have `x < z` while `y > z`, because an equivalence group would then contradict itself.

This condition is sometimes called **consistency of groups with compare equal to 0**; it is stronger than merely saying "the comparator just needs sign symmetry." A custom comparison can return `0` for a special pair and still violate the rule when encountering a third element.

### Example of a logically broken 0-group

Suppose on integers we specially declare `1` and `3` "equal" (compare returns 0), while all remaining pairs use natural numeric order. When compared against `2`:

- `compare(1,3) == 0`.
- `compare(1,2) < 0` because `1 < 2`.
- `compare(3,2) > 0` because `3 > 2`.

`1` and `3` were declared to be in the same group, yet they sit on opposite sides of `2`. That is a contract-breaking comparator; it cannot be fixed by merely changing the sorting algorithm. To group by a different rule, you must **define an order over the groups** so that all members of the same group have the same sign result against every other group.

## 5. Relationship of `Comparator` with `equals()`

Java distinguishes two relations:

- `x.equals(y)`: logical equality defined by type `x`.
- `comparator.compare(x,y) == 0`: order equivalence provided by a specific comparator.

A comparator is considered **consistent with equals** when, for every pair in the comparison domain, `compare(x,y) == 0` if and only if `x.equals(y)`. This property is **strongly recommended** if the comparator is used in a sorted set/sorted map with `Set`/`Map` key semantics; not every comparator is required to distinguish objects according to `equals()`.

Intentional divergence examples:

```java
String a = "Java";
String b = "JAVA";

System.out.println(a.equals(b));                  // false
System.out.println(
        String.CASE_INSENSITIVE_ORDER.compare(a, b)); // 0
```

With `String.CASE_INSENSITIVE_ORDER`, the two strings belong to the same case-insensitive sort group, but `String.equals()` still distinguishes uppercase/lowercase. This relation is **not consistent with equals**.

Notably with `BigDecimal`:

```java
BigDecimal one = new BigDecimal("1.0");
BigDecimal another = new BigDecimal("1.00");

System.out.println(one.compareTo(another)); // 0
System.out.println(one.equals(another));    // false
```

*This illustrative snippet needs `import java.math.BigDecimal;`.* `BigDecimal.compareTo` treats two numbers with the same numeric value as order-equivalent, whereas `equals` also checks `scale`. The natural-order comparator of `BigDecimal` is therefore not consistent with equals.

When objects serve as keys of a `TreeMap` or elements of a `TreeSet`, you need to know the exact intent: **do you want to merge by a single criterion**, or **do you want to distinguish all values that differ by equals**? Both goals are valid, but they produce different behaviors.

## 6. Runnable Java 17+ Example: Signs, Transitivity, 0-Groups, `TreeSet`, and `TreeMap`

Save the following program to `ComparatorContractDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorContractDemo {

    record Task(String team, int priority, String code) {}

    public static void main(String[] args) {
        Task a = new Task("alpha", 2, "A");
        Task b = new Task("alpha", 2, "B");
        Task c = new Task("beta", 4, "C");
        Task d = new Task("beta", 2, "D");
        Task e = new Task("beta", 6, "E");

        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);

        // Sign rules and sign symmetry.
        System.out.println(byPriority.compare(a, b));
        System.out.println(a.equals(b));
        System.out.println(Integer.signum(byPriority.compare(a, c)));
        System.out.println(Integer.signum(byPriority.compare(c, a)));

        // Transitivity: 2 < 4 < 6, so 2 < 6.
        boolean transitive =
                byPriority.compare(a, c) < 0
                && byPriority.compare(c, e) < 0
                && byPriority.compare(a, e) < 0;
        System.out.println(transitive);

        // TreeSet treats Tasks with the same priority as equivalent.
        Set<Task> grouped = new TreeSet<>(byPriority);
        grouped.add(a);
        grouped.add(b);
        grouped.add(c);
        grouped.add(d);
        grouped.add(e);
        System.out.println(grouped.size());
        System.out.println(grouped.contains(
                new Task("unknown", 2, "Z")));

        // TreeMap also determines key equivalence using the comparator.
        Map<Task, String> map = new TreeMap<>(byPriority);
        map.put(a, "first");
        map.put(b, "updated");
        System.out.println(map.size());
        System.out.println(map.get(a));

        // Add tie-breakers to distinguish all three record components.
        Comparator<Task> byAllFields = byPriority
                .thenComparing(Task::team)
                .thenComparing(Task::code);
        Set<Task> distinct = new TreeSet<>(byAllFields);
        distinct.add(a);
        distinct.add(b);
        distinct.add(c);
        distinct.add(d);
        distinct.add(e);
        System.out.println(distinct.size());
        System.out.println(Integer.signum(byAllFields.compare(a, b)));

        // Two examples where compare == 0 but equals() is false.
        String s1 = "Java";
        String s2 = "JAVA";
        System.out.println(s1.equals(s2));
        System.out.println(
                String.CASE_INSENSITIVE_ORDER.compare(s1, s2));

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println(x.compareTo(y));
        System.out.println(x.equals(y));
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac ComparatorContractDemo.java
java ComparatorContractDemo
```

Exact output:

```text
0
false
-1
1
true
3
true
1
updated
5
-1
false
0
0
false
```

Line-by-line explanation:

1. `byPriority.compare(a,b)` prints `0` because both have priority `2`, while `a.equals(b)` prints `false` because `Task` is a record with three components, in which `code` differs.
2. `Integer.signum(compare(a,c))` prints `-1`; reversing the order to `compare(c,a)` gives `1`. This is the symmetric sign relation.
3. The three comparisons on 2, 4, and 6 yield `true` for the transitivity check.
4. `TreeSet` with `byPriority` has three equivalence groups for priority levels `2`, `4`, `6`, so `size()` is `3`. `contains(new Task("unknown",2,"Z"))` is `true` even though the new record is not equal to `a`, `b`, or `d`, because the comparator treats equal priority as the same sort key.
5. `TreeMap` uses the comparator to identify keys: inserting `a` then `b` (same priority) creates only **one mapping**; the second call replaces the value with `updated`, so `size()` is `1`.
6. `byAllFields` adds `team` and `code` to split groups with the same `priority`. The five records in the example all differ across their three components, so the `TreeSet` has `5` elements; within the same priority and team, `"A"` comes before `"B"`, returning a negative sign.
7. The `String` and `BigDecimal` pairs illustrate `compare == 0` yet `equals() == false` for two different reasons: ignoring case sensitivity and ignoring scale differences.

## 7. Why Do `TreeSet` and `TreeMap` Treat `compare == 0` as the Same Element/Key?

`TreeSet` uses natural order (`Comparable`) or a supplied `Comparator` to determine an element's position and whether two elements are equivalent in the tree. `TreeMap` applies the same principle to keys. Consequently, for these structures:

```text
compare(a, b) == 0
    => TreeSet treats a and b as equivalent for storing/finding elements.
    => TreeMap treats a and b as the same key for storing/finding mappings.
```

**Practical consequence:** A `TreeSet` with a comparator examining only `priority` cannot retain multiple distinct `Task` instances of the same priority. It is a set of **priority levels** in the comparator's sense, not a set of all tasks distinguished by record equality.

If that is intentional—for example, needing only one representative per priority group—a single-field comparator makes sense. If you want to keep **every distinct task**, add tie-breakers sufficient to distinguish them.

For example:

```java
Comparator<Task> byPriorityThenTeamThenCode =
        Comparator.comparingInt(Task::priority)
                .thenComparing(Task::team)
                .thenComparing(Task::code);
```

*Illustrative snippet intended for the same `Task` record in section 6.*

With the three-component record in the example, `compare` returns 0 when all three components match, so it aligns with record `equals()`. But if `Task` were changed into an entity whose equality is **by ID only**, a comparator over three state fields might no longer align. You must compare ordering criteria against the class's true identity definition; blindly adding tie-breakers "just to be safe" without understanding equality can introduce a different kind of bug.

The Java documentation advises explicitly noting when a comparator's ordering is **inconsistent with equals**, because `SortedSet` and `SortedMap` are designed to obey the general `Set`/`Map` contracts that specify equality via `equals()`. A `TreeSet` using an inconsistent comparator still operates by the comparator's rules; however, its results may diverge from intuition and the general `Set` equality contract.

A further distinction: regular `HashSet`/`HashMap` use `equals()/hashCode()` and **do not use a Comparator** to merge keys. Thus, the same pair of elements can be stored as two entries by `HashSet` while a `TreeSet` with a comparator treats them as one.

## 8. Ways to Create Valid and Maintainable Comparators

Java provides a composition API to avoid writing ad-hoc comparison sign logic manually:

| API | Role |
| --- | --- |
| `Comparator.comparing(keyExtractor)` | Compare by a key that has a natural order. |
| `Comparator.comparingInt/Long/Double(...)` | Compare primitive keys using standard order and avoid dangerous subtraction. |
| `thenComparing(...)` | Apply a secondary criterion when the previous criterion returns `0`. |
| `reversed()` | Reverse the entire order of the comparator. |
| `Comparator.naturalOrder()` | Use the natural order of a type implementing `Comparable`. |
| `Comparator.reverseOrder()` | Use the reversed natural order. |
| `Comparator.nullsFirst(...)` and `nullsLast(...)` | Specify the placement of `null` if the data domain can contain nulls. |

For example, wanting **higher priority first**, followed by ascending code:

```java
Comparator<Task> order = Comparator
        .comparingInt(Task::priority)
        .reversed()
        .thenComparing(Task::code);
```

*Illustrative snippet applied to the `Task` record in section 6.* Note the placement of `reversed()`: calling it **before** `thenComparing` means only the priority criterion is reversed, while `code` remains ascending. If you write `Comparator.comparingInt(...).thenComparing(...).reversed()`, the **entire combined order** is reversed, including the secondary criterion.

When a field can be `null`, decide explicitly:

```java
Comparator<String> nullableNames =
        Comparator.nullsFirst(Comparator.naturalOrder());
```

This puts `null` before other strings and uses natural order for non-null strings. `Comparator.naturalOrder()` by itself does not accept comparing a `null` value. Do not invent arbitrary null rules that cause `compare(null,x)` to return the same sign as `compare(x,null)`.

Some factories creating object-key comparators require the key to be suitable for comparison. If a key extractor returns a nullable value without handling it, `NullPointerException` can occur during sorting; use a key comparator with an explicit null policy, or design the data not to contain nulls.

## 9. Ordering Stability Differs from Comparator Validity

"Stable sort" means that elements considered equal by the comparator (`compare == 0`) keep their **original relative order** after sorting. This **does not turn two elements into the same object**, nor does it make them `equals()` to each other.

For example, a list containing:

```text
Task A: priority=2
Task B: priority=1
Task C: priority=2
```

If stably sorted by `priority` ascending, the result is `B, A, C`: A and C remain next to each other in the priority-2 group in their initial order. `List.sort` in Java guarantees a stable sort. However, a **TreeSet** with the same comparator will keep only one representative element for the priority-2 group, because it is a comparison-ordered set structure rather than a list sort.

Stability of a sorting algorithm **cannot fix** a contract-violating comparator. A comparator whose results change based on the clock, random numbers, or mutable state during sorting can make results inconsistent even though the algorithm is guaranteed to be stable.

When applying a comparator to a long-lived sorted collection, data participating in comparisons should also remain stable while the object is an element/key; if a sort field changes after insertion into a `TreeSet`/`TreeMap`, the tree structure does not automatically re-sort to the new position, leading to confusing lookup bugs.

## 10. Common Comparator Mistakes

### 10.1. Returning 1 for every unequal pair

```java
// WRONG: if both a < b and b > a return 1, sign symmetry is violated.
Comparator<Integer> bad = (a, b) ->
        a.equals(b) ? 0 : 1;
```

If two values differ, comparing in both directions yields a positive sign. There is no consistent order.

### 10.2. Creating cycles

A rule like "0 before 1, 1 before 2, but 2 before 0" violates transitivity. A comparator meant for sorting must enforce a consistent ordering relation across all pairs and triples.

### 10.3. Making two values compare to 0 yet disagree against a third value

Group `x ~ y` cannot sit on opposite sides of `z`. If a comparator uses an exception rule for one pair without designing the entire equivalence class, it easily violates the sign condition for 0-groups.

### 10.4. Using integer subtraction

`(a,b) -> a.age() - b.age()` can fail across the `int` range due to overflow. Use `Integer.compare` or `Comparator.comparingInt`. For `long`, casting a difference to `int` is even more dangerous.

### 10.5. Confusing compare equal to 0 with equals returning true

`String.CASE_INSENSITIVE_ORDER` and `BigDecimal.compareTo` are examples where compare equal to 0 does not imply equals. In `TreeSet` or `TreeMap`, this changes how entries are merged.

### 10.6. Using insufficient or excessive tie-breakers

A comparator inspecting only `lastName` will merge multiple people sharing a surname in a `TreeSet`. Conversely, a comparator inspecting mutable state or timestamps outside identity can cause the same entity to be treated as different after an update. You must clearly define what a "0-group" means for the business domain and target collection.

### 10.7. Breaking the contract on null or special values

Comparing `double` with `a < b ? -1 : a > b ? 1 : 0` treats multiple `NaN` cases as equivalent to other values, leading to bizarre logic. `Double.compare` has well-defined rules for `NaN` and negative zero (`-0.0`); using `Comparator.comparingDouble` is generally safer than custom comparison via relational operators. If the domain wants special values treated as equivalent in a custom way, define a normalization rule first and verify the entire contract.

## 11. Checking the Comparator Contract with Representative Datasets

Given comparator `cmp` and a meaningful set of values, you can check the relations using assertions or unit tests:

```java
// Illustrative check placed inside a test method, with cmp and
// List<Task> samples already set up.
for (Task x : samples) {
    for (Task y : samples) {
        int xy = Integer.signum(cmp.compare(x, y));
        int yx = Integer.signum(cmp.compare(y, x));
        if (xy != -yx) {
            throw new AssertionError("Sign symmetry violation");
        }
        for (Task z : samples) {
            int yz = Integer.signum(cmp.compare(y, z));
            int xz = Integer.signum(cmp.compare(x, z));
            if (xy > 0 && yz > 0 && xz <= 0) {
                throw new AssertionError("Transitivity violation");
            }
            if (xy == 0 && xz != yz) {
                throw new AssertionError("Inconsistent compare==0 group");
            }
        }
    }
}
```

*This is a **non-standalone** snippet; `Task`, `samples`, and `cmp` are required to run it. The triple nested loop has `O(n³)` cost, suitable only for small sample sets in tests.* It verifies sign symmetry, transitivity in the greater-than direction, and consistency against a third element for the supplied samples.

A useful test suite should include: values equal by comparator yet not `equals()`, elements near group boundaries, reversed orders, `Integer.MIN_VALUE/MAX_VALUE` if comparing numbers, data containing `null` if permitted, strings differing in letter case, and `TreeSet`/`TreeMap` keys after insertion. Testing on samples is not a mathematical proof over the entire input domain, so constructing comparators from standard ordering components remains essential.

## 12. Self-Check

**Question 1.** Does a comparator returning `-20` for `compare(a,b)` and `5` for `compare(b,a)` violate the sign rule?  
**Answer:** No; the signs are negative and positive respectively. Matching magnitudes are not required.

**Question 2.** If `compare(a,b)==0`, `compare(a,c)<0`, yet `compare(b,c)>0`, is the comparator valid?  
**Answer:** No. Two elements in the same 0-group must have the same sign relation with every `c`.

**Question 3.** Can you use a Comparator that only compares `priority` with `List.sort` when you want to keep tasks of the same priority in their input order?  
**Answer:** Yes, with `List.sort` being stable. They remain separate elements in the list; this is not a merge operation.

**Question 4.** For a `TreeSet<Task>` using a priority-only comparator, if you add two tasks with different codes but the same priority, does `size()` increase twice?  
**Answer:** No. The comparator returns 0, so `TreeSet` treats them as equivalent.

**Question 5.** Is `Comparator` required to satisfy `compare(x,y)==0` if and only if `x.equals(y)`?  
**Answer:** Not required for every purpose, but consistency with equals is very important to consider when used in a sorted set/map.

**Question 6.** Is `a - b` always a correct comparator implementation for `int`?  
**Answer:** No, because of overflow. Use `Integer.compare(a,b)` or a comparator factory.

**Question 7.** Why can a comparator with a cycle `A < B < C < A` not be used safely for sorting?  
**Answer:** It violates transitivity, so there is no consistent total order for the sorting algorithm to maintain.

**Question 8.** When adding `thenComparing` after the first criterion, how do the `compare == 0` groups change?  
**Answer:** A group under the first criterion can be split into smaller subgroups according to the next criterion. Pairs that remain equal across all new criteria continue to have `compare == 0`.

**Key takeaway:** A valid comparator obeys **sign symmetry, transitivity, and consistency of groups with `compare == 0`**. A result of 0 describes **equivalence under the sorting rule**, not automatically `equals()`; this consequence is especially important when using a comparator as the key policy of `TreeSet` and `TreeMap`.