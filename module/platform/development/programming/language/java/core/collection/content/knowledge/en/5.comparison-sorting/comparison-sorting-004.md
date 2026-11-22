# thenComparing and Multi-Criteria Sorting

A single criterion is often not enough to present data according to business meaning. In a task list, we might want:

1. Higher priority comes first.
2. If priorities are equal, an earlier due date comes first.
3. If still tied, the task ID increases in ascending order so the result has a well-defined rule.

`Comparator.thenComparing(...)` combines criteria in that exact hierarchy. A subsequent criterion only resolves pairs of elements that all preceding criteria could not distinguish.

This article uses `Ticket` as an example. A larger `priority` number means higher priority; `due == null` means no due date has been set. These are business conventions chosen for the example, not meanings that Java automatically imposes on field names.

## 1. Why Are Secondary Criteria Needed?

Sample data:

| ID | Priority | Due Date |
| --- | --- | --- |
| T4 | 2 | 2026-05-10 |
| T2 | 3 | 2026-05-08 |
| T6 | 3 | None |
| T1 | 3 | 2026-05-08 |
| T3 | 2 | 2026-05-06 |
| T5 | 3 | 2026-05-12 |

Sorting by descending priority alone can place the entire priority `3` group before the priority `2` group. However, it does not specify how T1 and T5 within the same group should be ordered.

Adding the due date sorts each priority group by due date. Adding the ID further distinguishes T1 and T2, because these two tasks have the same priority and the same due date.

The result using all three criteria is:

~~~text
T1, T2, T5, T6, T3, T4
~~~

T3 has an earlier due date than T1 but still comes after the priority `3` group, because **priority is the primary criterion**. The due date is not allowed to reverse an outcome already decided by priority.

This is the difference between a hierarchy of criteria and a composite scoring method. `thenComparing` does not average, apply weights, or let a secondary criterion "compensate" for the primary criterion.

## 2. Mechanism: Using the First Non-Zero Result

Suppose:

~~~java
Comparator<Ticket> order =
        primary.thenComparing(secondary).thenComparing(tertiary);
~~~

When comparing two tasks `left` and `right`, you can think of it as:

~~~java
// Code illustrating the mechanism; the component comparators have already been declared.
int result = primary.compare(left, right);
if (result != 0) {
    return result;
}

result = secondary.compare(left, right);
if (result != 0) {
    return result;
}

return tertiary.compare(left, right);
~~~

This snippet with `return` is an illustrative body of a comparison operation, not a standalone program to be copied into `main`.

A negative result means `left` comes first, a positive result means `left` comes after, and `0` means the comparator has not distinguished the two elements.

"Equal" at the step that decides whether to use the next criterion means **`compare(left, right) == 0`**, not `left.equals(right)`.

For example, T1 and T2 are two different tasks, but a comparator that only checks priority returns `0`. Therefore, the due-date comparator is checked next, and then the ID comparator is checked when the due dates are also equal.

Java refers to this combination as lexicographic order over comparators. The API description and overloads can be found in the [Java SE 17 Comparator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Do Not Add Comparison Results Together

The following combination does not properly express a hierarchy:

~~~java
// Conceptually flawed example; do not use.
int result = primary.compare(left, right)
        + secondary.compare(left, right);
~~~

A positive result from one criterion can be canceled out by a negative result from another. Moreover, a comparator only specifies the meaning of the sign; the magnitude of the result is not a business weight.

Also, do not write subtraction between two numeric keys and assume it is always a valid comparator. Numeric overflow can flip the sign. Factories like `comparingInt` or the `Integer.compare` method are more appropriate for `int` keys.

## 3. Creating a Multi-Criteria Comparator

Given the data type:

~~~java
// Illustrative type declaration; requires importing java.time.LocalDate.
record Ticket(String id, int priority, LocalDate due) {}
~~~

We create a comparator for a date that may be missing:

~~~java
Comparator<LocalDate> dateOrder =
        Comparator.nullsLast(Comparator.naturalOrder());
~~~

Then we chain the rules:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

Read in order:

- `comparingInt(Ticket::priority).reversed()`: priority in descending order.
- `thenComparing(Ticket::due, dateOrder)`: within the same priority level, date in ascending order; missing dates come last within the group.
- `thenComparing(Ticket::id)`: if both criteria above are tied, ID follows the natural ordering of `String`.

Ascending ID in this article is understood in terms of string comparison. With IDs like `T2` and `T10`, string order does not match the numeric order of the number inside. If business rules require numeric ordering of the ID, an appropriate comparison key must be designed.

### A Comparator Is Data Describing a Rule

Creating `order` does not sort the data yet. You need to pass it to an operation that uses it:

~~~java
// tickets is an existing source; ArrayList creates a modifiable list.
List<Ticket> sorted = new ArrayList<>(tickets);
sorted.sort(order);
~~~

`sort` reorders the elements inside the list on which it is called. A comparator does not decide on its own whether to mutate the source or create a copy; that is the choice of the code using it.

If you call `sort` directly on an unmodifiable list such as the result of `List.of(...)`, the operation may fail with `UnsupportedOperationException`. Use a modifiable copy when the goal is to preserve the original source or when the source does not allow reordering.

## 4. Three Forms of thenComparing to Distinguish

| Form | Input | When to Use |
| --- | --- | --- |
| `thenComparing(other)` | Comparator for the same element type | You already have a complete comparison rule to reuse as the next criterion. |
| `thenComparing(keyExtractor)` | Function extracting a key with natural ordering | Keys like `String` or `LocalDate` do not need a custom rule. |
| `thenComparing(keyExtractor, keyComparator)` | Function extracting a key and a comparator for that key | You want to control `null`, comparison direction, or a custom rule for the key. |

### Chaining an Existing Comparator

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority).reversed();

Comparator<Ticket> byDue =
        Comparator.comparing(Ticket::due, dateOrder);

Comparator<Ticket> order =
        byPriority.thenComparing(byDue).thenComparing(Ticket::id);
~~~

`byDue` compares two `Ticket` instances. Therefore, it fits the overload that accepts a comparator for the element type.

### Chaining a Key Extractor Function

~~~java
Comparator<Ticket> order =
        byPriority.thenComparing(Ticket::id);
~~~

`Ticket::id` is not a comparator: it takes a task and returns a `String` key. This overload extracts two keys and then uses their natural ordering.

### Chaining a Key with a Custom Rule

~~~java
Comparator<Ticket> order =
        byPriority.thenComparing(
                Ticket::id,
                String.CASE_INSENSITIVE_ORDER
        );
~~~

In this example, the second parameter is a comparator of `String`, not a comparator of `Ticket`.

Do not confuse the two levels:

~~~text
Comparator<Ticket>
    compares Ticket with Ticket

Comparator<String>
    compares two id keys extracted from Ticket
~~~

If the key type does not implement `Comparable`, the overload accepting only a key extractor function is not sufficient to select a natural ordering. In that case, you must pass a comparator for the key or map to a key that has a well-defined ordering rule.

## 5. Variants for Primitive Keys

For numeric keys, there are specialized methods:

- `thenComparingInt(...)`: key extractor function returns `int`.
- `thenComparingLong(...)`: key extractor function returns `long`.
- `thenComparingDouble(...)`: key extractor function returns `double`.

An additional example for another data type:

~~~java
// Illustrates declarations within a class; requires importing java.util.Comparator.
record Shipment(
        String destination,
        int priority,
        long weightInGrams,
        double distance
) {}

Comparator<Shipment> order =
        Comparator.comparing(Shipment::destination)
                .thenComparingInt(Shipment::priority)
                .thenComparingLong(Shipment::weightInGrams)
                .thenComparingDouble(Shipment::distance);
~~~

The hierarchy is destination, then priority, then weight, then distance. All criteria in the example above use ascending order for each key.

The primitive variants make the key type explicit and avoid boxing keys into `Integer`, `Long`, or `Double` along the corresponding comparison path. Do not cast a `long` value to `int` just to use `thenComparingInt`: doing so can lose information and change the result.

Choose the data type and define the ordering first. If `distance` allows `NaN`, infinity, or values invalid for the business domain, you must define a data policy for them; the fact that the API accepts `double` does not automatically resolve business meaning.

## 6. Controlling Ascending and Descending Order for Each Criterion

### Reversing Only the Primary Criterion

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

`reversed()` appears immediately after the priority comparator, before chaining the date and ID. Therefore, it reverses only the priority direction.

### Reversing the Entire Chain

~~~java
Comparator<Ticket> different =
        Comparator.comparingInt(Ticket::priority)
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id)
                .reversed();
~~~

At the point `reversed()` is called, the chain already includes all three criteria. The result reverses priority, due date, and ID. The "missing date comes last" relation is also reversed into "missing date comes first" within the corresponding group.

You cannot move `reversed()` from the middle to the end and assume it preserves the same meaning.

### Descending Order for a Secondary Criterion

Suppose that for tasks with the same priority, a later due date comes first, while missing dates still come last:

~~~java
Comparator<LocalDate> dueDescendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());

Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dueDescendingNullLast)
                .thenComparing(Ticket::id);
~~~

Another way to reverse an existing element comparator is to pass it into the overload that accepts a comparator:

~~~java
// Example showing reversal scope only: reverses the entire existing byDue rule.
Comparator<Ticket> byPriorityThenReversedDue =
        byPriority.thenComparing(byDue.reversed());
~~~

If `byDue` already wraps `nullsLast` for the date, `byDue.reversed()` will also reverse the position of `null`. If you want `null` to always stay at the end, create a key rule like `dueDescendingNullLast` in the previous example.

## 7. Null: Policies at Each Criterion and at the Element Level

If only the due date can be missing, handle it in the date key comparator:

~~~java
Comparator<LocalDate> dateOrder =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

If the list can also contain `Ticket == null` elements, wrap the complete comparator on the outside:

~~~java
Comparator<Ticket> nullTicketsLast =
        Comparator.nullsLast(order);
~~~

These two layers address two different situations:

- The outer comparator checks the `Ticket` element itself.
- The date comparator handles the `due` value of an existing `Ticket`.

If `id` can also be `null`, you must add a rule at the ID criterion. Handling `null` for `due` does not automatically handle `null` for all other keys.

### No Exception on One Dataset Does Not Prove a Comparator Is Safe

Because a secondary criterion is only used when preceding criteria tie, a `null` key might not be read during a given comparison.

For example, two tasks with different priorities can be distinguished immediately; the date comparator does not need to run. However, as soon as data with the same priority is added, date comparisons may occur and expose an unhandled `null` error.

Do not rely on the incidental comparison order of a sorting algorithm to hide invalid data. Clearly define which keys are allowed to be missing, at which level, and where they should be placed.

## 8. thenComparing Returns a New Comparator

The method call does not mutate the existing comparator variable:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority).reversed();

order.thenComparing(Ticket::id); // Ignores the newly returned comparator.
~~~

After this code runs, the `order` variable still contains only the priority rule. To use the chained rule:

~~~java
order = order.thenComparing(Ticket::id);
~~~

Or build it as a single complete expression from the start:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::id);
~~~

This makes it convenient to reuse partial rules:

~~~java
Comparator<Ticket> base =
        Comparator.comparingInt(Ticket::priority).reversed();

Comparator<Ticket> forDashboard =
        base.thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);

Comparator<Ticket> forCodeLookup =
        base.thenComparing(Ticket::id);
~~~

Creating a new chain does not cause secondary criteria to appear on `base`. However, comparators can still share references to external objects captured by lambdas; do not mistake this for meaning that all data they read is immutable.

## 9. Chaining vs. Multi-Pass Sorting

The most natural way to express the requirement priority → due date → ID is to build one comparator and call `sort` once:

~~~java
sorted.sort(order);
~~~

A common misconception:

~~~java
sorted.sort(byPriority);
sorted.sort(byDueThenId);
~~~

The second sort reorders **the entire list** by due date and ID. It does not automatically mean "only sort the tied groups from the first pass".

With the data in this article, T3 has priority `2` but the earliest due date, so it will be moved to the front if the entire list is sorted by due date in the final step. The result violates the requirement that priority is the primary criterion.

### Multi-Pass Sorting Works When You Understand Stability

`List.sort` is a stable sort: elements considered equal by the comparator preserve their relative order from before that sort pass.

If you truly need multi-pass sorting, you can sort by the secondary criterion first and then perform a stable sort by the primary criterion:

~~~java
sorted.sort(byDueThenId);
sorted.sort(byPriority);
~~~

The final sort forms the priority groups. Within each group, it preserves the due date and ID ordering established in the previous pass.

This is a conditional technique, not a universal rule that works with every sorting algorithm:

- Passes must be applied from the least important criterion to the most important criterion.
- The sorting operation used must be stable to preserve secondary ordering within tied groups.
- The data and comparison rules must not change between passes.

A `thenComparing` chain is generally easier to read and less prone to hierarchy mistakes, while not requiring the reader to reason backward across multiple list mutations.

## 10. Stable Sorting Is Different from a Fully Determined Order

Sorting only by priority and due date:

~~~java
Comparator<Ticket> priorityThenDue =
        byPriority.thenComparing(Ticket::due, dateOrder);
~~~

T1 and T2 are still tied. If the input places T2 before T1, a stable `List.sort` keeps T2 before T1. If the input source reverses the two records, the result within the tied group can reverse accordingly.

Stability does not invent a missing criterion. If you want the result to be determined by the data itself rather than depending on input order, you need to choose an appropriate tie-breaking rule, such as a unique ID in the example:

~~~java
Comparator<Ticket> fullOrder =
        priorityThenDue.thenComparing(Ticket::id);
~~~

This is valuable for:

- Tests that require reproducible results.
- Exporting reports over the same dataset.
- Pagination that requires a clear order among records tied on the primary criterion.

However, adding an ID at the end of the chain does not automatically solve every pagination problem. Data can change between requests, and an ID might only be unique within a certain scope. A system must define uniqueness scope, data consistency, and how cursors or snapshots are created.

Do not add `identityHashCode`, random numbers, or the current time just to avoid `compare == 0`. Those values do not express a durable business order.

## 11. Elements Equal by Comparator and TreeSet

If a comparator only checks priority, T1 and T2 can produce `0` even though they are two different tasks.

- With a list, sorting does not remove elements just because they tie.
- With a `TreeSet`, the comparison relation also determines whether two elements occupy the same position in the set.
- With a `TreeMap`, the comparator participates in deciding whether two keys are equivalent.

Therefore, a comparator designed for a "group by priority" view may not be suitable as the comparator for a set intended to hold all tasks.

Adding the ID can help distinguish tasks if the ID is truly their unique identifier. However, the requirement of being "consistent with `equals`" must be verified against the actual `equals` definition.

In the `Ticket(id, priority, due)` record used in this article, `equals` checks all three components. The full comparator chain also checks all three components according to their respective rules. If you change the data definition, allow duplicate IDs, or add a case-insensitive rule, you must revisit the equivalence relation rather than simply keeping the old comparator chain.

## 12. Cost and Consistency of Criteria

A subsequent criterion is only called when the preceding chain returns `0`. This characteristic can reduce the number of times secondary keys are computed.

However, you should not reorder criteria just to reduce cost if doing so violates business requirements. Moving a unique ID to the front would mean the priority and due-date criteria are almost never used to decide the order between records with different IDs.

Optimize within the bounds of preserving the intended meaning:

- Use `thenComparingInt/Long/Double` variants for matching primitive keys.
- Avoid network calls or database queries inside key extractor functions.
- Consider precomputing expensive keys for a single processing pass.
- Do not let keys mutate while sorting is in progress.
- Do not rely on a fixed number of comparator calls made by an algorithm.

A comparator must produce consistent results throughout its use: swapping two objects must flip the sign; the ordering relation must be transitive; elements that compare equal must share the same sign relation when compared against a third element.

Chaining valid comparators is a way to express clear rules. It cannot fix a component comparator that already violates the contract or reads randomly changing data.

## 13. Complete Program

Save as **MultiCriteriaSortDemo.java**. The program uses APIs available in Java 17; `Ticket` is a record so the example data cannot have its keys mutated during comparison.

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class MultiCriteriaSortDemo {
    record Ticket(String id, int priority, LocalDate due) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("T4", 2, LocalDate.of(2026, 5, 10)),
                new Ticket("T2", 3, LocalDate.of(2026, 5, 8)),
                new Ticket("T6", 3, null),
                new Ticket("T1", 3, LocalDate.of(2026, 5, 8)),
                new Ticket("T3", 2, LocalDate.of(2026, 5, 6)),
                new Ticket("T5", 3, LocalDate.of(2026, 5, 12))
        );

        Comparator<LocalDate> dateOrder =
                Comparator.nullsLast(Comparator.naturalOrder());

        Comparator<Ticket> byPriorityDescending =
                Comparator.comparingInt(Ticket::priority).reversed();

        Comparator<Ticket> byDueThenId =
                Comparator.comparing(Ticket::due, dateOrder)
                        .thenComparing(Ticket::id);

        Comparator<Ticket> priorityThenDue =
                byPriorityDescending.thenComparing(Ticket::due, dateOrder);

        Comparator<Ticket> fullOrder =
                priorityThenDue.thenComparing(Ticket::id);

        Comparator<Ticket> wholeOrderReversed =
                Comparator.comparingInt(Ticket::priority)
                        .thenComparing(Ticket::due, dateOrder)
                        .thenComparing(Ticket::id)
                        .reversed();

        printSorted("Priority only", tickets, byPriorityDescending);
        printSorted("Priority then due", tickets, priorityThenDue);
        printSorted("Full order", tickets, fullOrder);
        printSorted("Whole chain reversed", tickets, wholeOrderReversed);

        List<Ticket> wrongPassOrder = new ArrayList<>(tickets);
        wrongPassOrder.sort(byPriorityDescending);
        wrongPassOrder.sort(byDueThenId);
        System.out.println("Primary sort then secondary sort = "
                + ids(wrongPassOrder));

        List<Ticket> correctPassOrder = new ArrayList<>(tickets);
        correctPassOrder.sort(byDueThenId);
        correctPassOrder.sort(byPriorityDescending);
        System.out.println("Secondary sort then primary stable sort = "
                + ids(correctPassOrder));

        Ticket t1 = tickets.get(3);
        Ticket t2 = tickets.get(1);
        Ticket t4 = tickets.get(0);

        System.out.println("Primary compare T1,T2 = "
                + byPriorityDescending.compare(t1, t2));
        System.out.println("Full compare T1,T2 sign = "
                + Integer.signum(fullOrder.compare(t1, t2)));

        int[] secondaryReads = {0};
        Comparator<Ticket> probe =
                byPriorityDescending.thenComparing(ticket -> {
                    secondaryReads[0]++;
                    return ticket.id();
                });

        probe.compare(t2, t4);
        System.out.println("Secondary reads when primary differs = "
                + secondaryReads[0]);

        secondaryReads[0] = 0;
        probe.compare(t2, t1);
        System.out.println("Secondary reads when primary ties = "
                + secondaryReads[0]);

        System.out.println("Original = " + ids(tickets));
    }

    private static void printSorted(
            String label,
            List<Ticket> source,
            Comparator<? super Ticket> order
    ) {
        List<Ticket> copy = new ArrayList<>(source);
        copy.sort(order);
        System.out.println(label + " = " + ids(copy));
    }

    private static List<String> ids(List<Ticket> tickets) {
        List<String> result = new ArrayList<>();
        for (Ticket ticket : tickets) {
            result.add(ticket.id());
        }
        return result;
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 MultiCriteriaSortDemo.java
java MultiCriteriaSortDemo
~~~

Stdout:

~~~text
Priority only = [T2, T6, T1, T5, T4, T3]
Priority then due = [T2, T1, T5, T6, T3, T4]
Full order = [T1, T2, T5, T6, T3, T4]
Whole chain reversed = [T6, T5, T2, T1, T4, T3]
Primary sort then secondary sort = [T3, T1, T2, T4, T5, T6]
Secondary sort then primary stable sort = [T1, T2, T5, T6, T3, T4]
Primary compare T1,T2 = 0
Full compare T1,T2 sign = -1
Secondary reads when primary differs = 0
Secondary reads when primary ties = 2
Original = [T4, T2, T6, T1, T3, T5]
~~~

### Reading Each Group of Results

**Priority only**

The priority `3` group appears before the priority `2` group. Within each group, there is no due-date or ID rule yet, so `List.sort` preserves the initial relative order: T2, T6, T1, T5 in group `3`.

**Priority then due**

T2 and T1 share the due date `2026-05-08`, so T2 remains before T1. T5 comes later because it has a later due date; T6 has no due date, so it stands at the end of the priority `3` group.

**Full order**

The ID is checked to resolve the pair T1 and T2. T1 comes before T2 because IDs are compared in ascending order. Relationships already decided by priority or due date remain unchanged.

**Whole chain reversed**

The ascending chain by priority, due date, and ID is reversed at the end. The priority `3` group comes first, but dates within the group go in reverse order; T6 with a `null` date is even moved to the front. The result is not the desired complete rule.

**Two sort call orders**

Sorting by primary and then secondary moves T3 to the front because the final pass prioritizes due date. Sorting by secondary and then performing a stable sort by primary yields the same sequence of IDs as the full comparator chain.

**Comparing T1 and T2**

The priority comparator returns `0`. The full comparator returns a negative sign because ultimately ID T1 comes before ID T2. The program prints the sign using `Integer.signum`, rather than assuming every comparator returns only `-1, 0, 1`.

**Counting secondary key extractions**

When two tasks differ in priority, the secondary ID key is not read: the count is `0`. When they have the same priority, the ID extractor reads the key for both objects: the count is `2`.

This counter is merely an observation tool for two isolated `compare` calls in the example. Do not write business logic that depends on how many times a comparator is called by a sorting algorithm, and do not add side effects such as mutating data inside key extractor functions.

**Source data**

All sort operations in the program work on copies. Therefore, the `Original` line preserves the initial sequence of IDs. Creating a new comparator and sorting a copy are two separate mechanisms that together help the example observe results clearly without mutating the source data.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking secondary criteria when `equals` returns true | Confuses object equality with a tie on a criterion | Use the `compare == 0` result in the combination mechanism. |
| Adding comparator results together | Loses the hierarchy and signs can cancel out | Use the first non-zero result or `thenComparing`. |
| Swapping the order of two criteria to "optimize" | Changes the business requirement | Keep the hierarchy and optimize how keys are computed instead. |
| Ignoring the return value of `thenComparing` | The old comparator does not include the new criterion | Assign the result or chain within a single expression. |
| Placing `reversed` at the end when only intending to reverse the first criterion | Reverses due date, ID, and `null` ordering as well | Reverse only the intended component comparator. |
| Sorting by primary then secondary and expecting only tied groups to change | The final pass reorders the entire list | Use a single comparator chain, or properly apply stable multi-pass sorting. |
| Assuming stable sort creates a unique order | Tied groups still depend on input order | Add a meaningful tie-breaking criterion when needed. |
| Not handling `null` keys because a small dataset has not failed yet | The error only appears when that criterion is actually reached | Test each tie level and define a policy for missing data. |
| Using a comparator that only checks part of the data for a `TreeSet` | Tied elements can be merged as duplicates | Check the uniqueness definition and consistency with `equals`. |
| Using mutating attributes or random numbers as keys | The comparison relation becomes inconsistent | Use keys that remain stable throughout the sorting pass. |

## 15. Self-Check and Practice

1. State in words the hierarchy of `byA.thenComparing(byB).thenComparing(byC)`. When is `byC` called?
2. Create two tasks with different priorities but dates ordered in the opposite direction. Prove that priority still decides the outcome.
3. Create two tasks with the same priority and different dates, then two tasks with the same priority and same date but different IDs. Test the two tie levels separately.
4. Modify the comparator to: priority descending, due date descending with missing dates last, and ID ascending.
5. Add data containing a `Ticket == null` element. Place that element at the beginning while still keeping missing dates at the end within each valid task group.
6. Reverse the input order of T1 and T2. Compare the results with and without the ID criterion.
7. Ignore the return value of `thenComparing` in a test snippet. Write a test case to detect that the secondary criterion was not applied.
8. Pass a comparator that only checks priority into a `TreeSet`. Observe the number of elements, explain why the result differs from a sorted list, and then choose an appropriate data structure or comparator for your data retention requirements.

When evaluating a comparator chain, explicitly write down each criterion, its ascending or descending direction, its missing-value policy, and what a tie means. Then test pairs that differ at only one level at a time to confirm the chain expresses the exact intended hierarchy.
