# reversed, reverseOrder, nullsFirst, and nullsLast

When sorting data, two things must be decided separately:

1. **By which rule and in which direction are actual values ordered?**
2. **If null values exist, does null come before or after those values?**

The `reversed`, `reverseOrder`, `nullsFirst`, and `nullsLast` methods help build comparators for these decisions. They create comparison rules; sorting only occurs when a rule is passed to an operation such as `List.sort`.

In this article, `reversed()` refers to the **Comparator** method. The examples use APIs compatible with Java 17 and later.

## 1. Identifying Each Tool

| Expression | Method Type | Function |
| --- | --- | --- |
| `c.reversed()` | Default method on an existing comparator | Reverses the entire order defined by `c` |
| `Comparator.reverseOrder()` | Static method | Creates a comparator in the reverse direction of natural ordering |
| `Comparator.nullsFirst(c)` | Static method | Places null before other values, using `c` for two non-null values |
| `Comparator.nullsLast(c)` | Static method | Places null after other values, using `c` for two non-null values |

Here, `c` is a `Comparator` object, not a list.

Two additional methods in the `Collections` class should also be distinguished:

- `Collections.reverseOrder(c)`: creates a comparator that reverses the rule of `c`.
- `Collections.reverse(list)`: reverses **the positions of existing elements** in a list.

These two operations cannot be substituted for one another arbitrarily.

## 2. reversed(): Reversing an Existing Rule

### 2.1. Reversing Which Rule?

Suppose an initial comparator orders strings by ascending length:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);

Comparator<String> lengthDescending = byLength.reversed();
```

These are illustrative declarations and require importing `java.util.Comparator`.

The new comparator puts longer strings first. It does not automatically change the rule to descending lexicographical order, because the original rule examines **length**.

If the original comparator orders by multiple criteria, reversing the comparator reverses that entire order.

### 2.2. Understanding by Comparison Direction, Not Result Magnitude

In terms of ordering relationships, a reversed comparator is equivalent to using the original comparator with its two arguments swapped:

```java
// Illustrating the meaning:
Comparator<String> reverse = (a, b) -> byLength.compare(b, a);
```

If `a` comes before `b` according to the original comparator, it comes after according to the reversed comparator. Objects of equal rank remain of equal rank.

Do not manually write:

```java
// Do not use as a pattern for reversing a comparator:
// Comparator<String> reverse = (a, b) -> -byLength.compare(a, b);
```

The comparator contract allows returning any appropriate negative or positive integer, not just -1 or 1. If the result is `Integer.MIN_VALUE`, negating that number remains negative due to `int` overflow.

`reversed()` expresses the right intent without requiring the caller to handle this case manually.

### 2.3. The Original Comparator and List Are Not Modified

The call:

```java
Comparator<String> reverse = byLength.reversed();
```

does not change `byLength` to descending order, nor does it automatically sort any list. Afterward, both comparators can still be used in two different places.

Reversing twice produces an ordering equivalent to the original rule. That is an observation about **comparison outcomes**, not a guarantee that the two expressions will return the same object reference.

See [Comparator.reversed API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#reversed()).

## 3. reverseOrder(): Reversing Natural Ordering

### 3.1. What Is Natural Ordering?

Natural ordering comes from the `Comparable` contract of a data type. For example, `Integer` has numeric order and `String` has string comparison order defined by that type.

```java
Comparator<Integer> descendingNumbers = Comparator.reverseOrder();
Comparator<String> descendingStrings = Comparator.reverseOrder();
```

These two comparators do not require an underlying user-supplied comparator.

`reverseOrder()` should not be understood as "reversing the order that a list currently has". It describes an order that can be applied to many lists.

### 3.2. Difference from Reversing a Custom Comparator

With the strings:

```text
z, aa, bbb
```

two requirements produce different results:

| Requirement | Result |
| --- | --- |
| Descending by String natural ordering | `[z, bbb, aa]` |
| Descending by length | `[bbb, aa, z]` |

Use `Comparator.reverseOrder()` for the first row. Use `Comparator.comparingInt(String::length).reversed()` for the second row.

If a domain type does not implement `Comparable`, you cannot simply use `Comparator.reverseOrder()` and expect Java to automatically know which property to reverse by. Create a comparator for the desired property first.

### 3.3. reverseOrder Does Not Automatically Support Null

`Comparator.reverseOrder()` has no null placement policy. If a comparison encounters a null argument, it throws `NullPointerException`.

To order non-null values in descending order while placing null at the end:

```java
Comparator<String> rule =
        Comparator.nullsLast(Comparator.reverseOrder());
```

The rule above has two layers: the outer layer handles null, and the inner layer handles actual strings.

See [Comparator.reverseOrder API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#reverseOrder()).

## 4. How Do nullsFirst and nullsLast Work?

Suppose `c` is a valid comparator for two non-null values:

| Two Arguments | `nullsFirst(c)` | `nullsLast(c)` |
| --- | --- | --- |
| Both null | Equal rank | Equal rank |
| First argument null, second non-null | First comes before | First comes after |
| First argument non-null, second null | First comes after | First comes before |
| Both non-null | Uses `c` | Uses `c` |

The outer wrapper handles cases involving null before the inner comparator is needed. It does not convert a null value into an empty string, the number 0, or a dummy object.

Two common declarations:

```java
Comparator<String> nullFirstAscending =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<String> nullLastAscending =
        Comparator.nullsLast(Comparator.naturalOrder());
```

`naturalOrder()` does not accept null on its own, but it can be placed inside a null-handling wrapper as shown above.

### 4.1. A Null Comparator Argument Has Its Own Meaning

The API allows:

```java
Comparator<String> onlyNullPlacement =
        Comparator.nullsFirst(null);
```

In this case:

- Null still comes before non-null values.
- **All non-null values are considered equal in rank.**
- There is no automatic step that applies natural ordering to the non-null portion.

Similarly, `Comparator.nullsLast(null)` only separates null to the end, while all non-null values share equal rank.

This is not shorthand for `nullsFirst(naturalOrder())`. If non-null values need to be distinguished, an appropriate comparator must be passed.

If a rule that only distinguishes null is used in a `TreeSet`, all non-null values belong to a single rank according to the comparator; you cannot expect the tree to retain every distinct string. With a list, elements of equal rank are still retained.

Details of the two wrappers are in the [nullsFirst API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)) and [nullsLast API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsLast(java.util.Comparator)).

## 5. The Position of reversed Determines the Position of Null

This is a point that must be read according to the structure of the expression.

### 5.1. Reversing the Entire Wrapper

```java
Comparator<String> original =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> reverseEverything = original.reversed();
```

The original rule orders:

```text
small value -> large value -> null
```

Reversing the whole rule gives:

```text
null -> large value -> small value
```

Null moves from the end to the beginning because it is also part of the reversed order.

### 5.2. Reversing Only Non-Null Values

```java
Comparator<String> descendingButNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Here, null remains at the end. The inner comparator specifies descending direction for non-null strings.

It can be read from the inside out:

1. Order actual values in descending direction.
2. Add the rule placing null at the end.

### 5.3. Quick Comparison Table

Let `c` be an ascending order for non-null values:

| Expression | Direction of Actual Values | Null Position |
| --- | --- | --- |
| `nullsFirst(c)` | Ascending | First |
| `nullsLast(c)` | Ascending | Last |
| `nullsFirst(c).reversed()` | Descending | Last |
| `nullsLast(c).reversed()` | Descending | First |
| `nullsFirst(c.reversed())` | Descending | First |
| `nullsLast(c.reversed())` | Descending | Last |

The table uses shorthand notation for the static methods of `Comparator`.

Two expressions with the same direction for the non-null portion do not necessarily share the same null policy. Therefore, both axes must be checked when reading a multi-layered comparator.

## 6. Complete Program: Reversing Direction and Placing Nulls

Save as **ComparatorDirectionDemo.java**. The `sorted` function always creates a new `ArrayList` copy so that each run uses the same input.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class ComparatorDirectionDemo {
    private static List<String> sorted(
            List<String> source, Comparator<String> comparator) {
        List<String> result = new ArrayList<>(source);
        result.sort(comparator);
        return result;
    }

    public static void main(String[] args) {
        List<String> words = List.of("z", "aa", "bbb");
        Comparator<String> byLength =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        System.out.println("Natural descending: "
                + sorted(words, Comparator.reverseOrder()));
        System.out.println("Length descending: "
                + sorted(words, byLength.reversed()));
        System.out.println("Collections reverse comparator: "
                + sorted(words, Collections.reverseOrder(byLength)));

        List<String> nullable =
                Arrays.asList("z", null, "aa", "bbb", null);
        Comparator<String> natural = Comparator.naturalOrder();
        Comparator<String> nullLastAscending =
                Comparator.nullsLast(natural);

        System.out.println("Null first ascending: "
                + sorted(nullable, Comparator.nullsFirst(natural)));
        System.out.println("Null last ascending: "
                + sorted(nullable, nullLastAscending));
        System.out.println("Reverse whole rule: "
                + sorted(nullable, nullLastAscending.reversed()));
        System.out.println("Null last descending: "
                + sorted(nullable, Comparator.nullsLast(
                        Comparator.reverseOrder())));

        Comparator<String> onlyNullPlacement =
                Comparator.nullsFirst(null);
        System.out.println("Only null placement: "
                + sorted(nullable, onlyNullPlacement));
        System.out.println("Non-null tie: "
                + onlyNullPlacement.compare("z", "aa"));
        System.out.println("Source unchanged: " + nullable);

        List<String> positional = new ArrayList<>(List.of("b", "a", "c"));
        Collections.reverse(positional);
        System.out.println("Reverse positions: " + positional);
        System.out.println("Sort descending: "
                + sorted(List.of("b", "a", "c"), Comparator.reverseOrder()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparatorDirectionDemo.java
java ComparatorDirectionDemo
```

Stdout:

```text
Natural descending: [z, bbb, aa]
Length descending: [bbb, aa, z]
Collections reverse comparator: [bbb, aa, z]
Null first ascending: [null, null, aa, bbb, z]
Null last ascending: [aa, bbb, z, null, null]
Reverse whole rule: [null, null, z, bbb, aa]
Null last descending: [z, bbb, aa, null, null]
Only null placement: [null, null, z, aa, bbb]
Non-null tie: 0
Source unchanged: [z, null, aa, bbb, null]
Reverse positions: [c, a, b]
Sort descending: [c, b, a]
```

### Comparing the Results

**The first three lines** distinguish natural ordering from length ordering. `Collections.reverseOrder(byLength)` produces the same reversed rule as `byLength.reversed()`.

**The four lines on null** demonstrate that the placement of the `reversed()` call has an effect:

- Reversing the entire `nullLastAscending` moves null to the beginning.
- Wrapping descending order with `nullsLast` keeps null at the end.

**`Only null placement`** preserves the relative order `z, aa, bbb` of the non-null portion. This is the consequence of two things happening together: the comparator treats them as equal in rank and `List.sort` is a stable sort. It is not a hidden ascending sort inside `nullsFirst(null)`. The stability guarantee is described in the [List.sort API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

**`Source unchanged`** confirms that the example sorts copies; the source list is not modified. If `source.sort(comparator)` were called directly on a list that supports mutation, that list itself would be reordered.

**The last two lines** show that reversing positions and sorting in descending order are two different tasks:

- Reversing `[b, a, c]` by position produces `[c, a, b]`.
- Sorting the strings by descending natural order produces `[c, b, a]`.

## 7. Reversing One Criterion or Reversing the Entire Criterion Chain?

Suppose the data type is:

```java
record Result(String code, int score) {}
```

The requirement is descending score, and when scores are equal, ascending code.

The right way to structure and read it:

```java
Comparator<Result> scoreDescendingCodeAscending =
        Comparator.comparingInt(Result::score)
                .reversed()
                .thenComparing(Result::code);
```

`reversed()` only affects the score comparator at the point where it is called. After that, the ascending code criterion is chained onto it.

Another expression:

```java
Comparator<Result> scoreAndCodeDescending =
        Comparator.comparingInt(Result::score)
                .thenComparing(Result::code)
                .reversed();
```

reverses both criteria: descending score, and also descending code when scores are tied.

The priority order is still score first and then code; the change lies in the comparison direction of each component.

If null handling is needed, you must determine which criterion may be null. Placing a single `nullsLast` wrapper at the end of the entire chain does not mean every inner field is automatically protected.

## 8. Element Null Differs from Property Null

Consider:

```java
record Task(String code, Integer priority) {}
```

There can be three separate cases:

1. The `Task` reference is null.
2. The `Task` exists, but `priority` is null.
3. The `Task` exists, but `code` is null.

### 8.1. Wrapping Only the Element Is Not Enough

The following illustration does not protect against a null property:

```java
Comparator<Task> incomplete = Comparator.nullsLast(
        Comparator.comparing(Task::priority));
```

The outer layer handles a null `Task`. When both tasks are non-null, the inner comparator extracts `priority`. If priority is null, the natural ordering used for that property can still throw `NullPointerException`.

Similarly, `comparingInt(task -> task.priority())` must convert `Integer` to `int`. A null priority causes an error during unboxing, before any integer comparison can take place.

### 8.2. Handling Null at the Right Data Layer

Specific requirements:

- Non-null priority in descending order.
- Null priority placed after actual priorities.
- When priorities are equal, code in ascending order and null code at the end of the tied group.
- A null task placed at the very end of the entire list.

Build layer by layer:

```java
Comparator<Task> priorityDescending = Comparator.comparing(
        Task::priority,
        Comparator.nullsLast(Comparator.reverseOrder()));

Comparator<Task> codeAscending = Comparator.comparing(
        Task::code,
        Comparator.nullsLast(Comparator.naturalOrder()));

Comparator<Task> complete = Comparator.nullsLast(
        priorityDescending.thenComparing(codeAscending));
```

The inner `nullsLast` calls handle **properties**; the outer `nullsLast` handles **Task objects**.

When two priorities are both null, the priority comparator returns 0, so the code criterion is still evaluated. If business policy does not want further distinction within that group, a different rule must be intentionally specified.

## 9. Complete Program with Multiple Null Layers

Save as **NullableTaskSortDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullableTaskSortDemo {
    record Task(String code, Integer priority) {}

    private static String describe(Task task) {
        if (task == null) {
            return "<null task>";
        }
        return String.valueOf(task.code()) + ":" + task.priority();
    }

    private static List<String> sorted(
            List<Task> source, Comparator<Task> comparator) {
        List<Task> copy = new ArrayList<>(source);
        copy.sort(comparator);
        return copy.stream().map(NullableTaskSortDemo::describe).toList();
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
                new Task("B", 2),
                new Task("A", 2),
                new Task("C", null),
                null,
                new Task(null, 2),
                new Task("D", 1));

        Comparator<Task> priorityDescending = Comparator.comparing(
                Task::priority,
                Comparator.nullsLast(Comparator.reverseOrder()));

        Comparator<Task> codeAscending = Comparator.comparing(
                Task::code,
                Comparator.nullsLast(Comparator.naturalOrder()));

        Comparator<Task> rule = Comparator.nullsLast(
                priorityDescending.thenComparing(codeAscending));

        System.out.println("Selected rule: " + sorted(tasks, rule));
        System.out.println("Reverse whole rule: "
                + sorted(tasks, rule.reversed()));
        System.out.println("Original size: " + tasks.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NullableTaskSortDemo.java
java NullableTaskSortDemo
```

Stdout:

```text
Selected rule: [A:2, B:2, null:2, D:1, C:null, <null task>]
Reverse whole rule: [<null task>, C:null, D:1, null:2, B:2, A:2]
Original size: 6
```

### Reading the Data Groups

With `rule`:

1. Priority 2 comes before priority 1.
2. Within the priority 2 group, code `A` then `B`, followed by null code.
3. Task `C` with null priority comes after tasks with actual priorities.
4. The null task reference is at the very end.

The string `null:2` in the output represents **an existing task, null code, priority 2**. The notation `<null task>` represents **no task object**. The program prints them differently so the two states are not confused.

When calling `rule.reversed()`, the entire order is reversed: the null task moves to the beginning, null priority moves up, and the actual value criteria and code order also flip direction. This is no longer the original requirement of "descending priority, ascending code, nulls last".

To reverse only the priority direction while keeping the other policies intact, rebuild the priority comparator component at the corresponding layer and recombine them.

## 10. reverseOrder in the Collections Class

In addition to `Comparator.reverseOrder()`, Java has two familiar methods in `Collections`:

| Expression | Meaning |
| --- | --- |
| `Collections.reverseOrder()` | Reversed natural ordering |
| `Collections.reverseOrder(c)` | Reverses the ordering defined by comparator `c` |

For a non-null `c`, the second call fulfills the same ordering intent as `c.reversed()`. If `c` already supports null, reversing it also reverses the relationship between null and other values.

There is a special case for the overload taking a comparator: **`Collections.reverseOrder(null)` uses reversed natural ordering**. That differs from the meaning of a null comparator in `Comparator.nullsFirst(null)`.

See the contracts for [no-arg Collections.reverseOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverseOrder()) and [Collections.reverseOrder taking a comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverseOrder(java.util.Comparator)).

### Null Values in the API Do Not All Mean the Same Thing

| Where Null Is Passed | Meaning |
| --- | --- |
| An element in the data | A value requiring an acceptance or rejection policy |
| `Comparator.nullsFirst(null)` | Null first; all non-null values share equal rank |
| `Comparator.nullsLast(null)` | Null last; all non-null values share equal rank |
| `Collections.reverseOrder(null)` | Uses reversed natural ordering |
| `list.sort(null)` | Uses natural ordering; does not automatically become a sort that supports null elements |

When a comparator variable `c` has a null value, calling `c.reversed()` invokes a method on a null reference and causes a `NullPointerException`. Do not assume the special case of `Collections.reverseOrder(null)` applies to every identically named or related method.

## 11. Reversed Comparator vs. List Reversal Operation

`Collections.reverse(list)` changes the existing positional order:

```text
last element -> ... -> first element
```

It does not need to know whether the elements are numbers, strings, or tasks, does not evaluate criteria, and does not determine ascending or descending order on its own. Because it does not compare elements, the positional reversal operation does not need a comparator to handle null.

For example, if the original sequence is already sorted in ascending order according to a comparator, reversing the sequence can produce descending order under that relation. However, if there are elements of equal rank, reversing positions also reverses their relative order. A stable sort using a reversed comparator preserves the relative order of equal-rank elements. The two operations may both achieve a valid order while differing in the placement of tied elements.

Therefore, choose the operation according to the goal:

- To reverse the current sequence: `Collections.reverse`.
- To establish order according to a descending rule: pass an appropriate comparator to a sorting operation.

Details on list modification are in the [Collections.reverse API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)).

## 12. Common Pitfalls

| Symptom or Coding Pattern | Cause | Solution |
| --- | --- | --- |
| Using `reverseOrder()` does not order by length | Reversed natural ordering instead of the custom rule | Use `byLength.reversed()` |
| Null moves to the beginning after reversing | Reversed the entire `nullsLast` wrapper | Wrap the descending comparator with `nullsLast` if null must stay last |
| Task is non-null, yet a null error still occurs | An extracted null property is unprotected | Pass a null-safe comparator at the property level |
| Null priority causes an error when using `comparingInt` | Unboxing a null `Integer` to `int` | Use boxed comparison with a null policy |
| All non-null values keep their original order instead of ascending | Passed a null comparator to `nullsFirst/nullsLast` | Pass an actual comparator for those values |
| Secondary criterion also becomes descending | Called `reversed()` after chaining criteria | Reverse individual criteria at the right position |
| Initializing test data containing null with `List.of` fails | This factory does not accept null elements | Use a null-supporting structure for the example, such as `ArrayList` |
| Calling sort on an unmodifiable list fails | Sorting requires mutating the list order | Create an `ArrayList` when sorting a copy is needed |
| Manually negating the compare result | Can overflow on a valid negative result | Use `reversed()` or swap the argument order |
| Using `Collections.reverse` as a descending sort | Only reverses positions, does not sort by value | Call sort with a descending comparator |

Null wrappers and reversal operations do not make an incorrect comparator valid. The underlying comparator still needs a valid sign contract, transitivity, and consistency appropriate for the data.

## 13. How to Design and Verify a Rule

Before writing a chained expression, describe the requirement in full sentences:

> Priority descending; missing priority placed last. When priority is tied, code ascending; missing code placed last within the group. Null task placed last overall.

Then build layer by layer and test the cases:

1. Two different actual values.
2. Two actual values sharing the primary criterion.
3. One null and one non-null, in both argument directions.
4. Two nulls.
5. Property null vs. whole-element null.
6. Tied primary criterion with different secondary criterion.
7. Reversing an individual criterion vs. reversing the entire comparator.
8. Is the source list allowed to be mutated, or must it remain unchanged?

Do not conclude that a comparator supports null merely because testing on an empty or single-element list produces no error: the algorithm may not have invoked the relevant comparison yet.

To verify a null policy directly, you can call `compare(null, value)`, `compare(value, null)`, and `compare(null, null)` on a comparator designed to accept those cases, then verify the signs against the requirements.

## 14. Self-Check Exercises

1. With the strings `z, aa, bbb`, explain why `reverseOrder()` and a reversed length comparator produce different results.
2. Predict the null position of `nullsFirst(c).reversed()` and `nullsFirst(c.reversed())`.
3. Fix a rule that currently orders both score and code descending so that only score is descending while code remains ascending.
4. In the Task example, change priority from descending to ascending while still keeping nulls last in all three relevant positions.
5. Explain why `Comparator.nullsLast(null)` is not equivalent to `Comparator.nullsLast(Comparator.naturalOrder())`.
6. Create two elements of equal rank with different codes, then compare positional reversal against stable sorting with a reversed comparator.

The key takeaway is the scope of effect for each layer: **reversing an existing rule, selecting reversed natural ordering, placing null on one side, and performing an operation on a list** are distinct decisions that can be combined to match exact requirements.
