# replaceAll and sort on Lists

A list supports two very different kinds of modifications:

- **Element transformation:** normalizing strings, recalculating a value, or replacing an object with a new result.
- **Element sorting:** keeping the elements while reorganizing their positions according to a comparison rule.

`List.replaceAll` serves the first kind; `List.sort` serves the second. Both mutate the receiving list itself and return `void`.

This lesson uses Java 17 as its baseline. Four complete programs have been compiled with `--release 17` and run to verify stdout. The remaining short snippets illustrate expressions or operations inside a method, not standalone runnable files.

After this lesson, you will be able to:

- Use a UnaryOperator to transform each element.
- Choose natural ordering or a comparator when sorting.
- Explain sort stability.
- Distinguish element replacement capability from resizing capability.
- Predict the impact on shared references and handle transformation failures.

## 1. Distinguishing Value Transformation from Repositioning

Given the data:

```text
[3, 1, 2]
```

replacing each number with its negation produces:

```text
[-3, -1, -2]
```

Each position is replaced with a result calculated from the old element. No sorting step has occurred yet.

Sorting the new data in ascending order produces:

```text
[-3, -2, -1]
```

This is a separate step that determines the relative positions of the elements.

| Characteristic | replaceAll | sort |
| --- | --- | --- |
| Primary input | Function transforming a single element | Rule comparing two elements |
| Result at each position | May be replaced by a different value/object | Elements are reorganized in order |
| Element count in a valid successful operation | Preserved | Preserved |
| Automatically filters or deduplicates | No | No |
| Return value | `void` | `void` |
| Requires a modifiable list | Yes | Yes |
| Requires resizing support? | No | No |

These content guarantees assume that the supplied function performs only its intended role, without adding to or removing from the same list or causing side effects that violate usage conditions.

## 2. replaceAll and UnaryOperator

Signature:

```java
default void replaceAll(UnaryOperator<E> operator)
```

`UnaryOperator<E>` represents a function that accepts a value of type E and returns a result of the same type E. Its core operation can be understood as:

```text
E apply(E value)
```

This is the meaning of the functional interface, not a method you need to add to List yourself.

The [Java 17 UnaryOperator documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/UnaryOperator.html) describes it as an operation on a single operand that produces a result of the same type as its operand. With replaceAll, that result is used to replace the element.

For example:

```java
names.replaceAll(value -> value.strip());
```

or using a method reference:

```java
names.replaceAll(String::strip);
```

This snippet assumes `names` is a List<String> that supports element replacement and contains no null elements.

### The Function Result Must Be Returned

The transformation function must provide the replacement value. With a block body, an appropriate return statement is required:

```java
names.replaceAll(value -> {
    String cleaned = value.strip();
    return cleaned;
});
```

If you need to convert a List<String> into a List<Integer>, replaceAll on the string list is not the right tool: the result must keep the list's element type. When changing data types, create a new result list using an appropriate transformation.

### How replaceAll Differs from forEach

```java
names.forEach(value -> value.strip());
```

does not automatically store the stripped string back into the list. Calling the method on String returns a resulting string, but in this Consumer usage, the return value is ignored.

With replaceAll, the contract of the operation itself stores the function result into the element's position.

### Not a Fixed Old-Value Replacement Operation

Two APIs have similar names:

| API | Role |
| --- | --- |
| `list.replaceAll(operator)` | Applies a function to each element and stores the result |
| `Collections.replaceAll(list, oldValue, newValue)` | Replaces elements matching oldValue with newValue |

Do not confuse List's replaceAll with String's regular-expression replacement method. The receiving object and argument types determine which contract is in use.

## 3. sort and Comparator

Signature:

```java
default void sort(Comparator<? super E> comparator)
```

There are two main ways to use it:

```java
numbers.sort(null);
numbers.sort(Comparator.naturalOrder());
```

Both express sorting according to natural ordering when the elements satisfy comparability requirements.

For a custom order:

```java
tickets.sort(Comparator.comparingInt(Ticket::priority));
```

These snippets require importing Comparator and the corresponding data types.

### sort(null) Does Not Mean Skipping the Sort

In this API, a null comparator is the signal to use natural ordering. That differs from:

```text
replaceAll(null)
```

because replaceAll has no transformation function to apply in that case.

### Understanding Comparator Signs

```text
compare(first, second) < 0  -> first comes before second
compare(first, second) = 0  -> equivalent according to the criterion
compare(first, second) > 0  -> first comes after second
```

A comparator must describe a valid and consistent ordering relation. Do not subtract two int/long fields and cast the result, because overflow or data loss can flip the sign. Factory methods such as comparingInt or comparingLong help express type-safe comparison criteria.

A comparator should also not mutate the list itself, change comparison keys while sorting, or depend on external state that changes arbitrarily.

### Stability

List.sort guarantees stability: elements considered equal by the comparator retain their previous relative order. Sorting requires the list to be modifiable, but does not require it to be resizable. These specifications are documented in [Java 17 List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Stability does not mean:

- The order of every element remains unchanged.
- Duplicate elements are removed.
- The data automatically gains a secondary criterion that you did not declare.

If a comparator examines only priority, two objects with the same priority are considered equivalent for sorting, even if they are not equals to each other.

## 4. Program: Transforming and Then Sorting

Create the file **`ListReplaceSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ListReplaceSortDemo {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("  beta ", "ALPHA", " beta"));

        names.replaceAll(value -> value.strip().toLowerCase(Locale.ROOT));
        System.out.println("normalized = " + names);
        names.sort(null);
        System.out.println("sorted = " + names);
        System.out.println("size = " + names.size());

        List<Integer> transformFirst = new ArrayList<>(List.of(3, 1, 2));
        transformFirst.replaceAll(value -> -value);
        transformFirst.sort(null);

        List<Integer> sortFirst = new ArrayList<>(List.of(3, 1, 2));
        sortFirst.sort(null);
        sortFirst.replaceAll(value -> -value);

        System.out.println("transform then sort = " + transformFirst);
        System.out.println("sort then transform = " + sortFirst);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ListReplaceSortDemo.java
java -Dfile.encoding=UTF-8 ListReplaceSortDemo
```

Verified stdout:

```text
normalized = [beta, alpha, beta]
sorted = [alpha, beta, beta]
size = 3
transform then sort = [-3, -2, -1]
sort then transform = [-1, -2, -3]
```

### String Group

1. strip removes leading and trailing whitespace according to the method's rules.
2. toLowerCase with Locale.ROOT applies a lowercase policy independent of the host machine's default locale.
3. replaceAll replaces each element with its normalized result.
4. sort(null) orders the new strings according to natural ordering.
5. Both occurrences of beta remain; the size is still 3.

Strings are immutable objects. The program does not mutate the contents of an existing String; it replaces the reference at each list position with the resulting string.

### Step Order Can Change the Result

With the numbers 3, 1, 2:

- Transforming to negations first and then sorting produces `[-3, -2, -1]`.
- Sorting first and then transforming to negations produces `[-1, -2, -3]`.

A transformation can alter greater-than/less-than relationships. Therefore, you must not swap the two steps simply because both "process all elements."

If the goal is ordering based on normalized data, normalize first and then sort by the normalized data or key.

## 5. Stable Sorting, Secondary Criteria, and Nulls

Suppose Ticket objects have an id and a priority. Initial list:

```text
T3(priority=2)
T1(priority=1)
T2(priority=2)
T4(priority=1)
```

Sorting by priority in ascending order places group 1 before group 2. Within each equal-priority group, the previous relative order is preserved:

```text
T1, T4, T3, T2
```

If id is added as a secondary criterion:

```text
T1, T4, T2, T3
```

then T2 comes before T3 because of the id criterion, not because stability magically produced that order.

### Complete Program

Create the file **`StableListSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class StableListSortDemo {
    public record Ticket(String id, int priority) {
    }

    public static void main(String[] args) {
        List<Ticket> tickets = new ArrayList<>(List.of(
                new Ticket("T3", 2),
                new Ticket("T1", 1),
                new Ticket("T2", 2),
                new Ticket("T4", 1)));

        tickets.sort(Comparator.comparingInt(Ticket::priority));
        System.out.println("priority only = " + ids(tickets));

        tickets.sort(Comparator.comparingInt(Ticket::priority)
                .thenComparing(Ticket::id));
        System.out.println("priority then id = " + ids(tickets));
        System.out.println("ticket count = " + tickets.size());

        List<Integer> nullable =
                new ArrayList<>(Arrays.asList(3, null, 1, null, 2));
        nullable.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("nulls last = " + nullable);
    }

    private static List<String> ids(List<Ticket> tickets) {
        return tickets.stream().map(Ticket::id).toList();
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 StableListSortDemo.java
java -Dfile.encoding=UTF-8 StableListSortDemo
```

Verified stdout:

```text
priority only = [T1, T4, T3, T2]
priority then id = [T1, T4, T2, T3]
ticket count = 4
nulls last = [1, 2, 3, null, null]
```

### Reading the Results

- By priority only: T1 stays before T4, and T3 stays before T2.
- With id as a secondary criterion: elements previously tied on priority are further compared by id.
- The Ticket count remains 4.
- The list of numbers containing nulls uses an explicit policy: non-null numbers in ascending order, with nulls at the end.

### A Null-Safe Comparator Differs from a Null Comparator

These two expressions mean different things:

```java
nullable.sort(null);
```

requests natural ordering, whereas:

```java
nullable.sort(Comparator.nullsLast(Comparator.naturalOrder()));
```

supplies a comparator with an explicit null-handling policy.

If the sorting algorithm encounters a null that the comparison rule does not support, an error can occur. Do not assume that any list containing null can be validly sorted with natural ordering.

### Reversing the Right Scope

If you want non-null numbers in descending order while keeping nulls at the end, an appropriate policy is:

```java
Comparator<Integer> order =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Reversing the entire nullsLast comparator after constructing it can also flip the position of nulls. Be explicit about which part of the ordering you are reversing.

## 6. Fixed-Size Lists Can Still Support Both Operations

You need to distinguish between:

- Cannot grow or shrink in size.
- Cannot replace elements.
- Cannot perform any modification at all.

A list with a fixed number of positions can still allow replacing the value at each position and reorganizing the order.

For example, Arrays.asList creates a fixed-size List backed by the source array. Element changes in the list and the array are reflected across the shared data. See [Java 17 Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### Practical Comparison Table

| Source | replaceAll/sort | Add/remove |
| --- | --- | --- |
| Standard ArrayList | Supported | Supported |
| Standard LinkedList | Supported | Supported |
| Arrays.asList | Can replace elements and sort | Cannot change size |
| List.of or List.copyOf | No modification allowed | No modification allowed |
| Collections.unmodifiableList | No modification allowed through this view | No modification allowed through this view |

The List interface does not mean every instance accepts every mutating operation. You need to know how a list was created and who shares its backing data.

### Complete Program

Create the file **`FixedSizeListOperationsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class FixedSizeListOperationsDemo {
    public static void main(String[] args) {
        String[] source = {" B ", "a", " C "};
        List<String> view = Arrays.asList(source);

        view.replaceAll(value -> value.strip().toLowerCase(Locale.ROOT));
        view.sort(null);

        System.out.println("view = " + view);
        System.out.println("source = " + Arrays.toString(source));

        try {
            view.add("d");
        } catch (UnsupportedOperationException exception) {
            System.out.println("fixed-size add = "
                    + exception.getClass().getSimpleName());
        }

        List<String> readOnly = List.of("b", "a");

        try {
            readOnly.replaceAll(value -> value);
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only replaceAll = "
                    + exception.getClass().getSimpleName());
        }

        try {
            readOnly.sort(null);
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only sort = "
                    + exception.getClass().getSimpleName());
        }

        List<String> copy = new ArrayList<>(readOnly);
        copy.sort(null);

        System.out.println("read-only original = " + readOnly);
        System.out.println("sorted copy = " + copy);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 FixedSizeListOperationsDemo.java
java -Dfile.encoding=UTF-8 FixedSizeListOperationsDemo
```

Verified stdout:

```text
view = [a, b, c]
source = [a, b, c]
fixed-size add = UnsupportedOperationException
read-only replaceAll = UnsupportedOperationException
read-only sort = UnsupportedOperationException
read-only original = [b, a]
sorted copy = [a, b]
```

### Verified Points

- The view from Arrays.asList is normalized and then sorted into a, b, c.
- The source array also becomes a, b, c because the backing data is shared.
- Adding d is rejected because it requires resizing.
- List.of rejects both replaceAll with an identity function and sort.
- Creating an ArrayList copy allows sorting without changing the elements of the original list.

Do not use an identity function or pre-sorted data to probe whether an unmodifiable list allows mutation. Mutating APIs may reject the call immediately even if you think the visible outcome would not change.

## 7. Both Methods Return void and Mutate the Receiving List

Typical usage:

```java
names.replaceAll(String::strip);
names.sort(Comparator.naturalOrder());
```

No new result list is returned for assignment or method chaining.

If two variables reference the same list:

```java
List<String> alias = names;
names.replaceAll(String::strip);
```

then alias also sees the replaced elements in that same list object.

### Preserving the Source List

Create a separate result list first:

```java
List<String> result = new ArrayList<>(source);
result.replaceAll(String::strip);
result.sort(Comparator.naturalOrder());
```

This snippet assumes the source contains no nulls and is read under appropriately stable conditions.

A structural copy does not automatically deep-copy the elements. With immutable String objects, replacing positions in result does not alter the String contents of source. With mutable objects, an operator that directly mutates properties of a shared object can still affect data referenced by source.

### replaceAll Can Return the Same Reference or a New Reference

A function may:

- Return the exact object it received.
- Return a new object of the same type.
- Return null if the list's policy and business rules allow it.

There is no rule that every replaceAll call creates new objects or mutates existing ones. That is decided by the transformation function; the API's responsibility is to use the returned value to replace the element.

## 8. When the Transformation Function Throws: Do Not Assume Automatic Rollback

The [Java 17 List.replaceAll documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)) states that runtime errors or exceptions thrown by the operator are relayed to the caller. This API is not specified as a transaction that automatically rolls back the entire list upon failure.

Consider the transformation:

```text
value -> 20 / value
```

With input:

```text
[2, 4, 0, 5]
```

the first two elements may already be replaced before division by 0 fails. The following program demonstrates this clearly on an ArrayList.

### Complete Program

Create the file **`PartialReplaceAllDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialReplaceAllDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(List.of(2, 4, 0, 5));
        List<Integer> alias = values;

        try {
            values.replaceAll(value -> 20 / value);
        } catch (ArithmeticException exception) {
            System.out.println("in-place failure = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("values after failure = " + values);
        System.out.println("alias after failure = " + alias);

        List<Integer> original = new ArrayList<>(List.of(2, 4, 0, 5));
        try {
            List<Integer> result = transformedCopy(original);
            System.out.println("result = " + result);
        } catch (ArithmeticException exception) {
            System.out.println("copy transform failure = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("original preserved = " + original);

        System.out.println("successful copy = "
                + transformedCopy(List.of(2, 4, 5)));
    }

    private static List<Integer> transformedCopy(List<Integer> source) {
        List<Integer> candidate = new ArrayList<>(source);
        candidate.replaceAll(value -> 20 / value);
        candidate.sort(null);
        return candidate;
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 PartialReplaceAllDemo.java
java -Dfile.encoding=UTF-8 PartialReplaceAllDemo
```

Verified stdout:

```text
in-place failure = ArithmeticException
values after failure = [10, 5, 0, 5]
alias after failure = [10, 5, 0, 5]
copy transform failure = ArithmeticException
original preserved = [2, 4, 0, 5]
successful copy = [4, 5, 10]
```

### In-Place Modification Run

- 2 is replaced with 10.
- 4 is replaced with 5.
- At 0, division throws ArithmeticException.
- The list in this example retains the state `[10, 5, 0, 5]`.
- The alias points to the same list and therefore sees the same partially modified state.

This state is verified for the class and operation used in the program. You must not use it to assume every other implementation class updates in the exact same way when an error occurs.

### Copy Modification Run

The transformedCopy method:

1. Creates a new ArrayList from the source.
2. Transforms the copy.
3. Sorts if the transformation step succeeds.
4. Returns the result only when the entire sequence of steps completes.

For input containing 0, the method does not return a result; the original list retains its data untouched. For the valid input 2, 4, 5, it returns `[4, 5, 10]`.

In this model, Integer objects are immutable and the operator has no side effects outside the calculation. Therefore, a failure on candidate does not alter the elements of the source.

### Limitations of the Copy Approach

- A shallow copy does not prevent a function from directly mutating a shared mutable object.
- It cannot undo sending notifications, writing files, or calling external services already performed by the operator.
- It does not automatically create an atomic snapshot if the source is concurrently modified without a coordination protocol.
- Publishing the result across multiple threads requires its own dedicated design.

Creating a copy is a way to control data ownership and when a result becomes visible, not a general-purpose transaction mechanism.

## 9. Nulls, Data Types, and Error Conditions

### Distinguishing Three Null Questions in replaceAll

| Case | Question to Resolve |
| --- | --- |
| The operator itself is null | There is no function to apply; the call is invalid |
| An input element is null | Does the function handle that input? |
| The function returns null | Do the backing list and business rules accept null elements? |

For example, String::strip does not handle a null String reference. If an application wants to preserve or replace missing data, it must choose an explicit policy.

An illustrative normalization:

```java
names.replaceAll(value -> value == null ? "" : value.strip());
```

This snippet chooses an empty string as the result for null; that is a business decision for the example, not default replaceAll behavior.

### Sorting Requires Elements Comparable Under the Active Rule

With natural ordering, elements must support mutually compatible comparisons. With a custom comparator, the comparator must handle the pairs of elements it receives.

Potential failure causes include:

- Objects or elements lacking compatible comparison types.
- Null values not handled by the comparison rule.
- A comparator violating the ordering contract.
- A comparator throwing an exception from its own logic.
- A list not supporting modification.
- The source being invalidly modified during the operation.

Do not rely on the state of a list after a failed sort as if it were guaranteed to roll back or guaranteed to modify only a prefix. The details depend on the concrete implementation class and the point at which the failure occurs.

### Do Not Modify the Same List Inside the Function

An operator or comparator that calls add, remove, sort, or replaceAll on the very list being processed can violate operating conditions.

If you need a complex workflow, separate calculating the results from applying the changes. Do not rely on modification-detection mechanisms as a valid control-flow technique.

## 10. Efficiency and Designing Supplied Functions

### With replaceAll

If each transformation has a constant cost and the traversal/replacement mechanism is well-suited, total work scales linearly with the number of elements.

An overly heavy function involving I/O or slow resource access can dominate the total cost, even though the outer operation looks like a single short call.

Prefer:

- Functions with clear meaning that do not depend on invocation count or side-effect ordering for correctness.
- Not mutating the source list itself.
- Validating required data beforehand when possible.
- Separating external processing from element transformation.

### With sort

Sorting may invoke the comparator many times across various pairs in an order you should not depend on. A comparator is not a "once per element" transformation function.

If a comparison key is very expensive to compute, consider preparing the keys or an appropriate intermediate data model before sorting. Avoid placing service calls or data mutations inside a comparator.

Do not infer from the List interface name that every implementation class sorts using the exact same algorithm or with the same cost. Stability is the contractual guarantee to rely on; implementation details must be evaluated per class.

### Sorting Does Not Maintain Order for Subsequent Additions

A sort call only orders the state present when the operation succeeds. If elements are later added or values that determine ordering are mutated, the list does not automatically remain ordered according to the previous comparator.

You must re-sort when ordered access is required, or choose a different data model suited to maintaining order continuously.

## 11. Common Pitfalls

### Thinking replaceAll Filters Elements

It replaces each element with a result; it does not remove elements. Returning null does not remove that position.

### Thinking sort Deduplicates

A list can still retain multiple elements that compare equal. Stability only governs their relative order.

### Assigning the Result of a void Method

Neither replaceAll nor sort returns a new List. Use two separate statements, or create a copy yourself when you need an independent result.

### Calling on List.of Because "It Only Reorders Without Adding or Removing"

Replacing and sorting are still list modifications. Unmodifiable lists reject them immediately.

### Assuming Arrays.asList Is Completely Immutable

It is fixed-size, not immutable; its elements can be replaced. The example showed that replaceAll and sort also reflect back into the source array.

### Implementing a Comparator Using Subtraction

Sign errors caused by overflow can break the ordering contract. Use type-appropriate comparison methods or comparator factory methods.

### Expecting Stability to Automatically Sort by a Secondary Criterion

If you need id or another attribute to break ties, you must declare that criterion. Stability preserves the previous order within an equivalent group.

### Calling sort Before Normalization and Assuming It Stays Correct

A transformation can change ordering relationships. Identify the key you want to sort by before choosing the order of steps.

### Catching an Exception and Assuming Data Is Intact

The ArrayList experiment showed that replaceAll may have already partially modified the list. When preserving the source matters, control copies and side effects from the start.

## 12. Practice

### Exercise 1: Predict the String Pipeline

Create an ArrayList from:

```text
[" Z ", "b", " A", "b "]
```

Normalize using strip and lowercase with Locale.ROOT, then sort in natural order.

Before running, predict:

- The contents after replaceAll.
- The contents after sort.
- The remaining element count.
- Whether either of the two b elements is removed.

### Exercise 2: Stability or Secondary Criterion?

Using Ticket from the program:

1. Sort by priority only.
2. Compare the order within each priority group.
3. Then add descending id as a secondary criterion.
4. Explain which part of the result comes from the comparator and which part comes from stability.

### Exercise 3: Change the Data Source

Run appropriate operations on:

- A copied ArrayList.
- A view from Arrays.asList.
- A List.of instance.

Record clearly which operations succeed, which are rejected, and which backing data changes through shared references.

### Exercise 4: Null Policy

Create a list that allows nulls and choose a policy:

- Keep nulls but place them at the end when sorting.
- Replace nulls with empty strings before sorting.
- Reject the entire dataset before starting any modification.

Describe the meaning of each policy. Do not treat the three choices as producing the same business outcome.

### Exercise 5: Mid-Operation Failure

Starting from PartialReplaceAllDemo:

1. Place 0 at the beginning, middle, and end in separate trials.
2. Observe the state of the ArrayList after the failure.
3. Repeat the experiment on a structural copy.
4. Explain why a copy of Integer elements behaves differently from a scenario where the operator mutates a property of a shared mutable object.
5. Identify the point at which it is safe to publish the result to callers.

The completion criterion is accurately distinguishing transformation from sorting, choosing appropriate functions, maintaining clear ownership over data mutations, and never assuming a source list has modification or rollback capabilities that its contract does not guarantee.