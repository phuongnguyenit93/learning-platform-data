# Duplicate Element Criteria When Comparison Returns 0

## 1. In TreeSet, Comparison Determines Both Order and Duplicates

When using a sorted set such as `TreeSet`, we often focus on the question "which element comes first?". However, that same comparison also answers another critical question: **does the set treat two values as the same element?**

The rule to remember:

```text
compare(a, b) == 0
    → a and b are equivalent according to the set's ordering
    → TreeSet does not keep them as two separate elements
```

If natural ordering is used, the comparison is `a.compareTo(b)`. If the set is created with a `Comparator`, the comparison is `comparator.compare(a, b)`.

For example, a comparator that only checks string length treats `"An"` and `"Bo"` as equivalent because both are two characters long. A `TreeSet` using that comparator keeps only one representative, even though:

```java
"An".equals("Bo") // false
```

Therefore, choosing a `Comparator` for a set is not just choosing how elements are displayed. It directly affects the element count as well as the results of adding, searching, and removing elements.

The `TreeSet` documentation explains that elements are compared using `compareTo` or a `Comparator`; two values whose comparison result is `0` are treated by the set as equal according to its ordering. [TreeSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 2. Three Types of Comparison Results

A valid comparison returns an integer whose sign carries meaning:

| Result of compare(a, b) | Meaning in the chosen ordering |
| --- | --- |
| Less than 0 | a comes before b |
| Equal to 0 | a and b are equivalent according to the comparison criteria |
| Greater than 0 | a comes after b |

Do not assume the method may only return `-1`, `0`, or `1`. For any `Comparator`, the negative/positive sign is what determines before-and-after ordering.

A result of `0` also does not mean:

- The two variables point to the same object.
- The two objects have all the same fields.
- The `equals` method is guaranteed to return `true`.
- There is not enough information to compare, so the set will fall back to checking `equals`.

It means the comparator has concluded that the two values are equivalent under that ordering. For `TreeSet`, this conclusion is enough to treat the element as already present.

If the goal is "same priority, yet still keep them separate", returning `0` after comparing only priority may be missing a tie-breaking criterion for a set. [Comparator.compare](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T))

## 3. Natural Ordering and Comparator: Which Rule Is Used?

### 3.1. No Comparator Passed: Uses Comparable

```java
Set<Integer> numbers = new TreeSet<>();
```

Integers are sorted according to the natural ordering provided by `Integer`. Elements must be mutually comparable according to that rule.

For common value types like `Integer`, two integers that are equal according to `equals` also produce a comparison result of `0`. However, such alignment is not something every class implementing `Comparable` is required to provide; `BigDecimal` is a case to distinguish later.

If `tree.comparator()` returns `null`, it means the set uses natural ordering, not that the set has no ordering rule.

### 3.2. Comparator Passed: Uses the Provided Rule

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
Set<String> names = new TreeSet<>(byLength);
```

The rule in use looks only at length:

```text
compare("An", "Bo") = 0
compare("An", "Linh") < 0
compare("Linh", "Chi") > 0
```

There is no default step saying "if lengths are equal, compare alphabetically" in the expression above. If you want that step, you must design it explicitly, such as with `thenComparing`.

Element objects do not necessarily have to implement `Comparable` themselves when a suitable `Comparator` is provided for them. However, all elements must still fall within the domain that the comparator can handle. [Ways to Define Ordering in SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html)

## 4. Mechanism That Causes an Element to Be Treated as a Duplicate

You can visualize finding a position in the tree with this conceptual flow:

```text
value to find or add
    ↓
compare against a stored entry
    ├─ negative result: continue toward the preceding side
    ├─ positive result: continue toward the following side
    └─ result 0: an equivalent element has been found
```

This diagram does not describe the tree's shape or all implementation details. It shows why a result of `0` means stopping the search for a distinct new value.

### 4.1. add Returns false When an Equivalent Element Exists

With the length-based comparator:

```text
initial: []

add("An") → true
set: [An]

add("Bo") → false
set: [An]
```

`"Bo"` is not added as a second element. There is no operation that merges the two strings into a new value, nor does it automatically replace `"An"` with `"Bo"`.

A stored element acts as the representative for its equivalence group under the comparator. In the insertion sequence above, `"An"` was kept first; adding `"Bo"` to a set that already holds that representative leaves the set unchanged.

Insertion order can affect which representative is kept in a group whose objects are not equal according to `equals`. This is a consequence you must understand when using a comparator that is coarser than the object's value semantics.

### 4.2. contains Uses the Same Equivalence Semantics

If the set currently holds only `"An"`, then:

```java
names.contains("Tu"); // true with a length-only Comparator
```

That does not mean the set stores the exact string `"Tu"`. It means the set has an element equivalent to `"Tu"` under the current comparison rule.

`contains` is not a method for retrieving the stored representative for the caller. Its result is a `boolean` value.

### 4.3. remove Can Delete a Representative Not Equal to the Argument by equals

Still in the state containing `"An"`:

```java
names.remove("Tu"); // true with a length-only Comparator
```

removes the element representing the two-character string group, which is `"An"` in this example.

If a developer only thinks "removing a string only deletes that exact string according to String.equals", this operation can be surprising. You need to read the set's identity rule before reasoning about the outcome.

### 4.4. hashCode Does Not Arbitrate Further After compare == 0

`TreeSet` does not use hash codes to separate two values that the comparator has already deemed equivalent.

Changing an element's `hashCode` does not cause `TreeSet` to keep two objects separate when the comparison still returns `0`. Lookup and deduplication here are based on ordering, unlike the lookup mechanism in a hash-based set.

This does not mean you can ignore the `equals`/`hashCode` contract of the object type. It simply means hash codes are not a fallback criterion in a tree set's lookup path.

## 5. Complete Program: Strings of Equal Length Are Merged

Save the entire code in **ComparisonZeroDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ComparisonZeroDemo {
    public static void main(String[] args) {
        Comparator<String> byLength = Comparator.comparingInt(String::length);
        TreeSet<String> names = new TreeSet<>(byLength);

        System.out.println("An equals Bo: " + "An".equals("Bo"));
        System.out.println("compare An/Bo: " + byLength.compare("An", "Bo"));
        System.out.println("add An: " + names.add("An"));
        System.out.println("add Bo: " + names.add("Bo"));
        names.add("Linh");
        names.add("Chi");
        System.out.println("by length: " + names);
        System.out.println("size: " + names.size());
        System.out.println("contains Tu: " + names.contains("Tu"));
        System.out.println("remove Tu: " + names.remove("Tu"));
        System.out.println("after removal: " + names);

        Comparator<String> byLengthThenText =
                byLength.thenComparing(Comparator.naturalOrder());
        TreeSet<String> precise = new TreeSet<>(byLengthThenText);
        precise.addAll(List.of("An", "Bo", "Linh", "Chi", "An"));
        System.out.println("length then text: " + precise);
        System.out.println("precise size: " + precise.size());
        System.out.println("precise contains Tu: " + precise.contains("Tu"));

        List<String> sequence =
                new ArrayList<>(List.of("An", "Bo", "Linh", "Chi"));
        sequence.sort(byLength);
        System.out.println("list sorted by length: " + sequence);

        Set<String> coarse = new TreeSet<>(byLength);
        coarse.add("An");
        Set<String> ordinary = new HashSet<>(Set.of("Bo"));
        System.out.println("coarse.equals(ordinary): " + coarse.equals(ordinary));
        System.out.println("ordinary.equals(coarse): " + ordinary.equals(coarse));
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 ComparisonZeroDemo.java
java ComparisonZeroDemo
```

Stdout:

```text
An equals Bo: false
compare An/Bo: 0
add An: true
add Bo: false
by length: [An, Chi, Linh]
size: 3
contains Tu: true
remove Tu: true
after removal: [Chi, Linh]
length then text: [An, Bo, Chi, Linh]
precise size: 4
precise contains Tu: false
list sorted by length: [An, Bo, Chi, Linh]
coarse.equals(ordinary): true
ordinary.equals(coarse): false
```

How to read the output:

1. `"An"` is not equal to `"Bo"` by `String.equals`, yet comparing by length yields `0`.
2. Adding `"Bo"` returns `false`, so the two-character group has only the representative `"An"`.
3. `"Chi"` has length three and `"Linh"` has length four, so the sequence is `[An, Chi, Linh]`.
4. Looking up `"Tu"` returns `true`, even though the string stored in the length-two group is `"An"`.
5. Removing with `"Tu"` deletes the representative `"An"`.
6. Adding a text criterion after length allows the `precise` set to keep `"An"` and `"Bo"` separate.
7. Sorting a `List` by length does not remove elements of the same length.
8. The last two lines intentionally demonstrate the consequence when a tree set uses a rule inconsistent with `equals`: set-level equality can lose symmetry. The next section explains why this should not be treated as normal usage of the `Set` contract.

## 6. Consistency with equals Must Be Evaluated in Both Directions

An ordering is **consistent with equals** when, within the domain in use:

```text
compare(a, b) == 0
    if and only if
a.equals(b) == true
```

Both directions are required:

| Situation | Consequence in TreeSet | Issue with the general Set contract |
| --- | --- | --- |
| `equals` is false but compare returns 0 | Two objects with different values are treated as one element | May reject a value that an ordinary Set treats as distinct |
| `equals` is true but compare is non-zero | The set may keep both objects | May retain two elements that are equal according to equals |
| Both identity checks align | Sorted set and value equality agree | Conducive to obeying the Set contract |

The `Comparator` documentation does not forbid every comparator that is inconsistent with `equals`. A comparator may be valid for sorting a list yet unsuitable as the identity criterion for a set intended to obey the full general contract.

The `TreeSet` documentation also explicitly states: if the ordering is inconsistent with `equals`, the set still operates according to its comparison rules, but it fails to obey the general `Set` contract. [Comparator: consistent with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html), [TreeSet: Set contract conditions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### Why Can equals Between Two Sets Differ by Call Direction?

In the first program:

- `coarse` is a tree set containing only `"An"`, using length for identity.
- `ordinary` is a hash set containing only `"Bo"`, using string equality.

When the tree set checks `"Bo"`, it finds that the length-two group is already present. When the hash set checks `"An"`, it does not find a string equal to `"An"`.

Therefore:

```text
coarse.equals(ordinary) → true
ordinary.equals(coarse) → false
```

This is not a desirable equality rule. It is proof that the two sets are using two incompatible notions of membership.

Do not "fix" this by always calling `equals` from whichever side gives the result you want, or by combining both directions with an OR operator. You need to fix the identity design, or choose a separate data structure and comparison suited to a different purpose.

## 7. Adding a Secondary Criterion: What Does thenComparing Do?

### 7.1. A Secondary Criterion Only Runs When the Preceding One Returns 0

If you want to sort strings by length while still keeping distinct strings of the same length:

```java
Comparator<String> order =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
```

The rule is:

1. Compare lengths.
2. If the lengths differ, the result is already determined.
3. If the lengths are equal, compare the string contents using natural ordering.

For `String`, the subsequent text criterion distinguishes unequal contents, so `"An"` and `"Bo"` no longer have an overall comparison result of `0`.

`thenComparing` does not automatically know your business identifier fields. The designer must choose a secondary criterion that matches the intended semantics.

### 7.2. For Multi-Field Objects, You Must Also Match the equals Rule

Example using a record:

```java
private record Task(String id, int priority) {
}
```

This record defines equality based on both `id` and `priority`. An ordering that compares priority and then id aligns with those two components:

```java
Comparator<Task> order = Comparator.comparingInt(Task::priority)
        .thenComparing(Task::id);
```

Assuming `id` is a valid string per the input contract, two objects have a comparison result of `0` when they have the same priority and the same id, matching record equality in the example.

If you compare only `priority`, two tasks with different ids but the same priority are merged. If the goal is to keep all tasks with the same priority, that criterion is insufficient for a set.

### 7.3. Appending an ID Is Not a Cure-All for Every Model

Suppose another class defines `equals` solely by `id`, whereas the comparator looks at priority and then `id`. Two objects with the same `id` but different priorities can produce:

```text
equals → true
compare → non-zero
```

In that case, the comparator is still inconsistent with `equals`, even with `thenComparing(id)`.

Therefore, do not apply a mantra like "just append id and you're done." Write down clearly:

- Which data defines a value?
- When are two objects considered duplicates?
- Which data participates in the ordering?
- Does compare returning 0 correspond exactly to equals?

If you only need to keep uniqueness by id and then display by priority, you can separate managing uniqueness by id from creating a sorted list for display. Do not force a `TreeSet` to carry one identity rule while pretending to carry another.

## 8. Sorting a List Differs from Deduplicating in a TreeSet

The exact same length-based comparator has two different roles:

| Where it is used | When two strings have the same length |
| --- | --- |
| `List.sort(byLength)` | Sorts them in order, keeping all elements in the list |
| `new TreeSet<>(byLength)` then adding | Keeps only one representative for the group where compare returns 0 |

A list can contain multiple elements that compare equal under the sorting criterion. There is no automatic deduplication rule just from calling `sort`.

If the requirement is simply "display all tasks by score/priority", a sorted list may fit the semantics better. If the requirement is truly a set of distinct values that also needs ordering, you must design a complete distinguishing criterion for the set.

Switching from a list to a tree set is not a neutral way to sort: it can reduce the number of elements. Before changing the data structure, check the condition under which compare returns `0`.

## 9. BigDecimal: Natural Ordering Can Also Differ from equals

It is not only custom `Comparator` implementations that exhibit this difference. `BigDecimal` is the classic example highlighted in the `Comparable` documentation:

```java
BigDecimal first = new BigDecimal("4.0");
BigDecimal second = new BigDecimal("4.00");
```

The two objects represent the same numerical value according to `compareTo`, but they have different scales:

```text
first.compareTo(second) → 0
first.equals(second)    → false

first.scale()  → 1
second.scale() → 2
```

`BigDecimal.equals` considers both value and scale; `compareTo` compares numerical value without distinguishing those two scales. This is why a `HashSet<BigDecimal>` can hold both values while a `TreeSet<BigDecimal>` using natural ordering keeps only one representative. [Comparable: the BigDecimal case](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html), [BigDecimal.compareTo and equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

There are at least two different requirements:

- If the intended meaning is the same numerical value, these two representations may need to be managed as the same value under a clearly defined model.
- If you need to preserve the distinction that `BigDecimal.equals` sees, you cannot rely solely on natural numerical comparison to distinguish them in a tree set.

An example of the second choice is comparing numerical value first, then comparing scale:

```java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
```

When numerical values are equal but scales differ, the secondary criterion distinguishes them. For `BigDecimal`, equal numerical value and equal scale correspond to the equality condition used by `equals`.

This is a data-semantics choice, not an arbitrary tweak to make the set larger. If your domain considers scale meaningful, do not silently discard that information just to make a particular set type convenient to use.

## 10. Complete Program: record, Secondary Criteria, and BigDecimal

Save the code in **SortedSetIdentityDemo.java**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class SortedSetIdentityDemo {
    private record Task(String id, int priority) {
    }

    private static String taskOrder(Set<Task> tasks) {
        StringBuilder result = new StringBuilder("[");
        String separator = "";
        for (Task task : tasks) {
            result.append(separator).append(task.id())
                    .append(":").append(task.priority());
            separator = ", ";
        }
        return result.append("]").toString();
    }

    public static void main(String[] args) {
        Comparator<Task> order = Comparator.comparingInt(Task::priority)
                .thenComparing(Task::id);
        Set<Task> tasks = new TreeSet<>(order);
        tasks.add(new Task("t-3", 2));
        tasks.add(new Task("t-2", 1));
        tasks.add(new Task("t-1", 1));
        System.out.println("tasks: " + taskOrder(tasks));
        System.out.println("duplicate task: " + tasks.add(new Task("t-2", 1)));
        System.out.println("contains same fields: "
                + tasks.contains(new Task("t-2", 1)));
        System.out.println("contains changed priority: "
                + tasks.contains(new Task("t-2", 9)));

        BigDecimal first = new BigDecimal("4.0");
        BigDecimal second = new BigDecimal("4.00");
        System.out.println("decimal equals: " + first.equals(second));
        System.out.println("decimal compareTo: " + first.compareTo(second));

        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(first);
        hashed.add(second);
        System.out.println("HashSet decimals: " + hashed.size());

        TreeSet<BigDecimal> numeric = new TreeSet<>();
        System.out.println("TreeSet add first: " + numeric.add(first));
        System.out.println("TreeSet add second: " + numeric.add(second));
        System.out.println("TreeSet decimals: " + numeric.size());
        System.out.println("stored scale: " + numeric.first().scale());
        System.out.println("contains 4.000: "
                + numeric.contains(new BigDecimal("4.000")));
        System.out.println("remove second: " + numeric.remove(second));
        System.out.println("numeric empty: " + numeric.isEmpty());

        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        Set<BigDecimal> scaleAware = new TreeSet<>(valueThenScale);
        scaleAware.add(first);
        scaleAware.add(second);
        System.out.println("scale-aware size: " + scaleAware.size());
        System.out.println("scale-aware order: " + scaleAware);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SortedSetIdentityDemo.java
java SortedSetIdentityDemo
```

Stdout:

```text
tasks: [t-1:1, t-2:1, t-3:2]
duplicate task: false
contains same fields: true
contains changed priority: false
decimal equals: false
decimal compareTo: 0
HashSet decimals: 2
TreeSet add first: true
TreeSet add second: false
TreeSet decimals: 1
stored scale: 1
contains 4.000: true
remove second: true
numeric empty: true
scale-aware size: 2
scale-aware order: [4.0, 4.00]
```

How to read the output:

1. The two tasks with the same priority `1` are both kept because ids `t-1` and `t-2` distinguish them in the secondary criterion.
2. Adding a record with both fields matching an existing record returns `false`.
3. The same id with priority `9` does not equal the record with priority `1` in this record model.
4. `4.0` and `4.00` are not equal by `BigDecimal.equals`; the hash set retains two elements.
5. The natural-order tree set keeps only one element. The stored representative's scale is `1`, because `first` was added first and adding `second` did not replace it.
6. Querying with `4.000` still finds the representative with the same numerical value.
7. Removing with `second` deletes that representative, leaving the natural-order tree set empty.
8. The value-then-scale comparator retains both `4.0` and `4.00`.

Both standalone programs were compiled with `--release 17` and executed to verify the exact stdout. This option checks language/API level and produces Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 11. A Comparator Must Be Valid Before Discussing Duplicate Criteria

A comparator that is inconsistent with `equals` is not necessarily wrong in terms of ordering rules. The length comparator is one example: it can be valid for sorting while being too coarse for identity in a string set that uses `String.equals`.

That must be distinguished from a comparator that violates the `Comparator` contract itself.

### 11.1. Properties to Verify

For values in the comparison domain:

- Comparing a value with itself must return `0`.
- Swapping the two arguments must invert the sign of the result.
- The before-and-after relation must be transitive.
- If `x` and `y` compare as `0`, then when comparing them against any `z`, the signs of the results must match.

The last property ensures that values treated as equivalent have a consistent before-and-after relationship with all remaining groups. Otherwise, the tree structure has no reliable ordering for lookup. [Comparator.compare Contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T))

### 11.2. Do Not Return a Non-Zero Number Just to Force Keeping All Elements

Writing "if scores are equal, just return `1`" is not a valid tie-breaking criterion. It can cause:

```text
compare(a, b) > 0
compare(b, a) > 0
```

or even `compare(a, a) > 0`. That is a contradiction in the comparator, not a way to turn a set into a list that keeps every element.

If you want to keep distinct values, add a criterion that genuinely distinguishes them. If you want to keep even completely equal values, reconsider using `Set`.

### 11.3. Do Not Use int Subtraction as a General Comparison Technique

An expression like `left.priority - right.priority` can overflow the `int` range, causing the result's sign to be wrong for large/small boundary values.

Use `Integer.compare` or `Comparator.comparingInt` to express integer comparisons. Add secondary criteria using the corresponding methods instead of hand-rolling calculations that are hard to verify.

Do not use randomness, the current time, or a configuration that mutates between calls to break ties. An ordering that changes while the set holds data leaves lookups without a stable foundation.

## 12. Data Domain and Stability of Comparison Keys

### 12.1. Fields Used for Comparison Must Remain Stable While in the Set

If a set orders tasks by priority, and the program then mutates the priority of an object already inside the set, its old structural position may no longer match the current ordering rule.

Do not rely on still holding an object reference to assume `contains` or `remove` will find it like a stable key. Prefer immutable values or explicitly design a workflow that removes the old value and adds the new one.

Even when objects are immutable, a comparator that reads from an external configuration table can change ordering if that table is modified. Keep both the identity data and the comparison rules stable for as long as the set is in use.

### 12.2. null and Incomparable Types Are Different Requirements

Returning `0` from compare is the result of a valid comparison. It is not a substitute code for an incomparable-input error.

A `TreeSet` using natural ordering does not allow `null` elements. A `Comparator` can support `null` if designed to do so, for example with `Comparator.nullsFirst`.

The `Comparator.comparingInt(String::length)` comparator in the example does not handle `null` on its own: calling `length` requires a valid string. The input contract must be explicit.

Similarly, all elements must be comparable under the same rule. An overly broad declared type does not suddenly give incompatible values a shared natural ordering. [TreeSet: Comparison Requirements and Exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 12.3. Comparison Cost Also Affects Operations

`TreeSet` has an O(log n) model for basic operations. However, each step also performs a comparison; a comparator that traverses many fields or large amounts of data carries its own cost.

Do not add expensive secondary criteria without understanding their purpose, but do not omit required identity criteria just to make the comparison shorter. Correctness of element retention comes first.

## 13. Common Mistakes and How to Self-Check

| Symptom or coding pattern | Possible cause | How to check |
| --- | --- | --- |
| Adding many objects results in a smaller size than expected | Comparator returns 0 for distinct business values | Print or inspect the specific pair of comparison keys |
| contains returns true for an object never added | An order-equivalent representative is present | Distinguish the stored object from the compare-equals-0 group |
| remove deletes a representative different from the argument by equals | Comparison rule is coarser than equals | Review the set's identity criteria |
| Changing hashCode still loses elements on add | TreeSet does not use hash codes to separate compare == 0 | Fix the comparator or the data model |
| Adding thenComparing(id) and assuming everything is consistent | The class's equals may use a different rule | Check the if-and-only-if condition in both directions |
| Returning 1 on equal scores to force insertion | Violates the ordering contract | Use a valid secondary criterion or choose a List |
| Using integer subtraction for comparison | Can overflow and produce the wrong sign | Use compare/comparingInt |
| Sorting a List keeps all elements, switching to TreeSet loses some | A set also deduplicates based on compare | Choose the data structure based on retention requirements |
| HashSet keeps two BigDecimals, TreeSet keeps only one | BigDecimal's equals and natural order differ on scale | Decide whether scale is part of the value semantics to preserve |
| Two-way equals between sets differs | The sets use incompatible identity rules | Fix the design; do not pick whichever call direction gives the desired result |

A concrete diagnostic technique is to take two objects that you believe should be kept separate and check both:

```java
a.equals(b);
comparator.compare(a, b);
```

If using natural ordering, check `a.compareTo(b)` instead of the comparator call. Then evaluate whether the result matches the identity requirement or only the display requirement.

## 14. Self-Practice and Verification

### Exercise 1: Representative of a Length-Equal Group

Create a string tree set using a length-only comparator. Add in sequence:

```text
"aa", "bb", "c", "ddd", "ee"
```

Predict:

1. The return values of the five `add` calls.
2. The contents and size of the set.
3. `contains("ff")`.
4. After `remove("xx")`, which elements remain?

Verify:

```text
add results: true, false, true, true, false
set: [c, aa, ddd]
size: 3
contains("ff"): true
remove("xx"): true
after removal: [c, ddd]
```

You should be able to explain why `"ff"` and `"xx"` do not need to match `"aa"` in content to belong to the same comparison group.

### Exercise 2: Keeping Strings of the Same Length

Add a text criterion after length, then insert the same data as in Exercise 1.

The result is:

```text
[c, aa, bb, ee, ddd]
```

The two-character strings are kept separate and ordered within their group alphabetically.

### Exercise 3: Checking a Class's Rules

A class defines `equals` solely by `id`. Its comparator compares by `priority`, then `id`.

Given two objects with the same `id` but different `priority`, evaluate:

- Does `equals` return `true`?
- Does the comparator return `0`?
- Is the comparator consistent with `equals` on this pair?

Verify: equal by equals; different by comparator; inconsistent. Appending id at the end does not resolve the semantic mismatch introduced by priority.

### Exercise 4: Choosing Semantics for BigDecimal

Given two values created from `"5.0"` and `"5.00"`:

- A tree set using natural ordering keeps one representative.
- A hash set using `BigDecimal`'s equality keeps two elements.
- A tree set comparing value then scale can keep two elements under scale-aware semantics.

Do not pick one of the three simply based on whether the size is larger or smaller. You must determine whether the two representations need to be kept separate in your data model.

## 15. Reference Documentation

- [TreeSet Java 17 — ordering and element identity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [SortedSet — relationship between ordering and the Set contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html)
- [Comparator — compare, thenComparing, and consistency with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Comparable — natural ordering and the BigDecimal case](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [BigDecimal — compareTo, equals, and scale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
