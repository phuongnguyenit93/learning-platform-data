# Choosing a List When You Need Indexed Access or Duplicate Elements

Choosing a collection starts with the **meaning of the data group**, not a familiar class name.

If the data represents a sequence with positions that need to be accessed, or if every occurrence of the same value must be retained, `List<E>` is an option worth considering. However, those two needs must also be weighed against requirements for ordering, lookup, modification, and element processing.

This lesson uses Java 17. Three complete programs have been compiled with `--release 17` and executed to verify their stdout. Other shortened code snippets illustrate operations within a method, not standalone executable files.

After this lesson, you will be able to:

- Identify which requirements genuinely need list positions.
- Distinguish a unique value from multiple occurrences of that value.
- Explain when a Set, Map, or queue models the problem better.
- Choose a List implementation class based on the primary operations.
- Avoid using indices as stable data identifiers.

## 1. A List Represents a Positioned Sequence of Elements

Consider:

```text
Value:   P1   P2   P1   P3
Index:    0    1    2    3
```

We might ask:

- What is the element at the third position?
- Before which position should an element be inserted?
- Which occurrences of P1 exist in the sequence?
- If two elements are swapped, does the resulting sequence still carry the same meaning?

A List provides a contract for index-based positional access and control. Common implementations such as ArrayList allow equal elements to appear multiple times. This is the sequence model described in [Java 17 List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Three properties must be distinguished:

1. **Ordered:** elements have relative positions within the sequence.
2. **Indexed:** positional operations such as get or set can be called.
3. **Sorted:** data currently follows a comparison rule such as ascending order.

A List has a positional ordering model, but it does not automatically sort values. The list `[P1, P2, P1, P3]` has a clear order, even though equal codes are not grouped together.

### Order Is Not Just Append Order

When calling add at the end, positions usually follow insertion order. However, a program can also:

- Insert in the middle.
- Remove a position.
- Swap elements.
- Re-sort.
- Replace data at a position.

Therefore, it is better to say that a List maintains the **current positional sequence**, rather than assuming it permanently preserves the original insertion history.

## 2. When Is Indexed Access a Genuine Requirement?

Common situations where it fits well:

| Scenario | Why does position matter? |
| --- | --- |
| Music playlist | A song has a specific playback position; the same song can be played again |
| Steps in a workflow | Previous/next steps and reordering operations carry meaning |
| Result rows in a defined order | The consumer needs to access or display items by position |
| Lines in a document | Inserting, replacing, and retrieving lines by position are real operations |
| A sequence of observations or scans | The order of occurrence must be preserved |

An illustrative access operation:

```java
String third = scans.get(2);
```

Indices start at 0. The third element in everyday counting resides at index 2.

### Not Every Question Involving a Number Is an Index

"Find the record with code 1002" is different from "get the element at position 1002".

- A record code is an identifying attribute.
- An index is the current position within a list.
- An index can change when elements are added, removed, or sorted.
- Valid codes are not necessarily contiguous or zero-based.

If the primary requirement is lookup by code, a Map is usually the model to consider. A List can still be used to present order, but an index should not be treated as a business identifier.

### If You Only Iterate Sequentially, You Might Not Need a List

A method that only prints or processes elements one by one might only need an appropriate Iterable or Collection. Requiring a List specifically just to write a get(index) loop can couple the API to an unnecessary capability.

Choose a List when sequence order or positional capability is part of the contract that must be provided, not simply because it was the first data structure you learned.

## 3. "Keeping Duplicates" Means Keeping Occurrences

Suppose a scanner records:

```text
P1, P2, P1, P3
```

There are four scans, even though there are only three distinct codes.

The following two requirements are different:

- **Store scan history:** P1 appears twice, and both positions carry meaning.
- **Store a catalog of seen codes:** each code only needs to appear once.

A List fits the first model. A Set may fit the second model, provided the uniqueness relationship is properly defined.

### Value Duplication Does Not Require the Same Reference

A list may contain:

- Two distinct objects that are equal according to equals.
- The exact same reference added at multiple positions.

The size of a list counts the elements at its positions; it does not count the number of distinct Java objects existing in memory.

Keeping duplicates also does not mean automatically copying objects. If you add the same mutable object twice, both positions may reference that exact same object.

### Sharing an Attribute Does Not Necessarily Mean Equal Elements

Two records with the same product code but different scan IDs, timestamps, or other data might not be equal according to equals.

Therefore, before choosing "no duplicates", answer:

- Unique by the entire object value?
- Unique by a specific code?
- Or must each occurrence be kept separately even if it shares the same code?

A collection name cannot decide that business relationship for you.

## 4. Program Preserving Occurrences and Accessing Positions

Create the file **`ChoosingListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class ChoosingListDemo {
    public static void main(String[] args) {
        String repeated = "P1";
        List<String> scans =
                new ArrayList<>(List.of(repeated, "P2", repeated, "P3"));

        System.out.println("scans = " + scans);
        System.out.println("occurrence count = " + scans.size());
        System.out.println("at index 2 = " + scans.get(2));
        System.out.println("same reference at 0 and 2 = "
                + (scans.get(0) == scans.get(2)));

        Set<String> uniqueCodes = new LinkedHashSet<>(scans);
        System.out.println("unique codes = " + uniqueCodes);
        System.out.println("unique count = " + uniqueCodes.size());

        boolean removed = scans.remove("P1");
        System.out.println("one P1 removed = " + removed);
        System.out.println("remaining scans = " + scans);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ChoosingListDemo.java
java -Dfile.encoding=UTF-8 ChoosingListDemo
```

Verified stdout:

```text
scans = [P1, P2, P1, P3]
occurrence count = 4
at index 2 = P1
same reference at 0 and 2 = true
unique codes = [P1, P2, P3]
unique count = 3
one P1 removed = true
remaining scans = [P2, P1, P3]
```

### Reading the Results

- The list has 4 elements because it retains both occurrences of P1.
- get(2) returns P1 at its second occurrence.
- Positions 0 and 2 hold the same reference in this example because the program deliberately reuses the variable repeated.
- LinkedHashSet keeps the three unique codes and presents them in first-seen order.
- remove("P1") on the list removes only the first occurrence, so the remaining P1 is still kept.

If the problem requires knowing every scan, converting directly to a Set loses part of the information.

### Being Ordered Does Not Guarantee It Can Replace a List

The LinkedHashSet in the example has a well-defined iteration order, but it does not provide the get(index) operation of a List and does not keep both occurrences of P1.

This shows that "being ordered" is not the sole criterion for two structures to be interchangeable.

### Converting Back Does Not Recover Lost Information

Creating a new ArrayList from uniqueCodes yields a sequence of three codes, but it lacks the data needed to know that P1 occurred twice or where it was located in the original sequence.

Copying into a List only changes the representation structure of the currently available data; it does not restore occurrences that were already discarded.

## 5. Keeping Only Counts vs. Keeping the Whole Sequence

If you only need to know:

```text
A appears 2 times
B appears 1 time
```

a frequency table by value can accurately model the need without storing each occurrence as a separate position.

However, the two sequences:

```text
[A, B, A]
[A, A, B]
```

have the same frequency table but different orders.

### Complete Program

Create the file **`SequenceVsCountsDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class SequenceVsCountsDemo {
    public static void main(String[] args) {
        List<String> first = List.of("A", "B", "A");
        List<String> second = List.of("A", "A", "B");

        Map<String, Integer> firstCounts = count(first);
        Map<String, Integer> secondCounts = count(second);

        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same list values = " + first.equals(second));
        System.out.println("first counts = " + firstCounts);
        System.out.println("second counts = " + secondCounts);
        System.out.println("same counts = " + firstCounts.equals(secondCounts));

        Map<String, List<Integer>> positions = new LinkedHashMap<>();
        for (int index = 0; index < first.size(); index++) {
            positions.computeIfAbsent(
                    first.get(index), key -> new java.util.ArrayList<>()).add(index);
        }
        System.out.println("first positions by value = " + positions);
    }

    private static Map<String, Integer> count(List<String> values) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String value : values) {
            counts.merge(value, 1, Integer::sum);
        }
        return counts;
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 SequenceVsCountsDemo.java
java -Dfile.encoding=UTF-8 SequenceVsCountsDemo
```

Verified stdout:

```text
first = [A, B, A]
second = [A, A, B]
same list values = false
first counts = {A=2, B=1}
second counts = {A=2, B=1}
same counts = true
first positions by value = {A=[0, 2], B=[1]}
```

### Comparing the Models

**List:**

- Keeps elements at their exact positions.
- Two sequences with different orders are not equal according to List.equals in the example.

**Map<String, Integer> counting occurrences:**

- Keeps each value along with its occurrence count.
- Both count tables are equal, even though the original sequences differ.
- Counts alone are insufficient to reconstruct the position of each occurrence.

**Map<String, List<Integer>> keeping positions:**

- Groups by value.
- Each group holds a list of indices.
- For example, A has positions 0 and 2, while B has position 1.

This composite structure demonstrates that List and Map can participate together in a single model. Choosing a data structure is not always about completely eliminating one in favor of another.

In this small example, both counts and indices fit within the int range. For data at other scales, you must choose appropriate numeric types and arithmetic policies for the frequency table.

### Keeping Duplicates Is Not Enough to Conclude You Must Use a List

If you only process tasks from the head of a queue, an appropriate Queue or Deque can still hold multiple equal tasks without needing a positional access contract.

The right question is: **do you need a positional sequence to access or modify elements, or do you only need a rule for retrieving the next element?**

## 6. Comparing with Other Structures

| Primary Requirement | Model to Consider | Points to Verify |
| --- | --- | --- |
| Positioned sequence of elements preserving each occurrence | List | Access cost and mutability |
| Set of unique values | Set | Uniqueness relationship and ordering policy |
| Value lookup by key | Map | Whether keys are unique; what updating a duplicate key means |
| Receiving/processing elements under a queueing policy | Queue or Deque | Head/tail operations and processing order |
| Only the count of each value is needed | Map of value → count | Whether losing ordering information is acceptable |
| Multiple values per key | Map of key → List of values | Intra-group order vs. global order |
| Fixed number of positions, especially with primitive data | Array | Size, data type, and required operations |

### A Map Can Contain Duplicate Values

A Map enforces how keys are handled according to its contract; that does not mean the values associated with every key must be distinct.

If you use a song ID as a key and put the same ID multiple times, a single-value Map does not automatically store multiple plays under the same key. To hold multiple occurrences under one key, you must choose a collection-typed value or a different model.

### Grouping by Key Can Lose Global Interleaving

A `Map<EventType, List<Event>>` can preserve order within each group, but those per-group lists alone may not be enough to know how different event types interleaved across the global sequence.

If global order matters, you need to keep the original sequence or store explicit position/timestamp information. The earlier example program storing indices for each group is one way to make positional information explicit.

### A Set Is Not Always the Right Way to "Clean Up" Data

If each occurrence represents a real event, discarding equal elements can delete valid information.

Conversely, if repetition is a data error, the fact that a List can hold duplicates does not mean the system should silently accept them. Business constraints should be validated explicitly rather than expecting a data structure to decide on its own.

## 7. An Index Is Not a Stable Identifier

Suppose a workflow list has a Review step at index 1. When a Prepare step is inserted at the beginning, Review shifts to index 2.

If the program saved the number 1 to represent Review, that number now points to a different step.

### Complete Program

Create the file **`PositionIsNotIdDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class PositionIsNotIdDemo {
    public record Step(String id, String text) {
    }

    public static void main(String[] args) {
        Step review = new Step("S20", "Review");
        List<Step> steps = new ArrayList<>(List.of(
                new Step("S10", "Start"),
                review,
                new Step("S30", "Finish")));

        int savedIndex = 1;
        String savedId = steps.get(savedIndex).id();

        steps.add(0, new Step("S05", "Prepare"));

        Map<String, Step> byId = new LinkedHashMap<>();
        for (Step step : steps) {
            byId.put(step.id(), step);
        }

        System.out.println("current ids = "
                + steps.stream().map(Step::id).toList());
        System.out.println("saved index now points to = "
                + steps.get(savedIndex).id());
        System.out.println("review current index = " + steps.indexOf(review));
        System.out.println("saved id = " + savedId);
        System.out.println("lookup by saved id = " + byId.get(savedId).text());
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 PositionIsNotIdDemo.java
java -Dfile.encoding=UTF-8 PositionIsNotIdDemo
```

Verified stdout:

```text
current ids = [S05, S10, S20, S30]
saved index now points to = S10
review current index = 2
saved id = S20
lookup by saved id = Review
```

### How to Read This

- savedIndex is still 1, but the list structure changed, so that position now holds S10.
- Review is still the step with id S20.
- indexOf(review) in the new state returns 2.
- The byId Map is built from the current list and queried using the saved id, so it retrieves Review accurately.

This example assumes each Step id is unique. If the input allows duplicate ids, you must define how to handle them rather than letting put silently overwrite an existing value.

The Map in the program is an index built **after the insertion**. It does not automatically stay synchronized with future changes to the List. If a system maintains both a List and a Map simultaneously, you must design an update mechanism to keep them consistent.

### When Position Is Still the Right Data

An index is completely appropriate when the actual operation is:

- "Replace the element in the third row of the current state."
- "Insert before the step currently located at this position."
- "Retrieve the element by a position managed by a list controller."

The mistake is using a position as a substitute for identity across multiple mutations without rules to maintain state consistency.

## 8. Choosing an Implementation Class Once You Choose List

The indexed contract does not mean every List accesses indices equally fast.

### ArrayList When Positional Access Is a Dominant Operation

ArrayList uses a resizable array model. get and set take time that does not grow with the number of elements under the standard cost model; appending to the end has amortized constant cost. Inserting or removing in the middle typically requires shifting data. See [Java 17 ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Therefore, for a list that needs indexed reads, iteration, and appending at the end, ArrayList is usually a sensible starting point to evaluate.

That is not a promise that it is optimal for every workload or every size. You must still consider capacity, mutation frequency, elements, and runtime conditions.

### LinkedList Has Indices but Must Traverse to the Position

LinkedList organizes doubly linked nodes; indexed operations must traverse from the beginning or the end to reach the target position. The [Java 17 LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) documentation explicitly describes traversing from whichever end is closer.

Consequences:

- Having a get(index) method does not imply constant-time random access.
- If you have already traversed to a position using a ListIterator, inserting or removing there can operate directly on the known links.
- If every insertion must first locate its position by index from the head or tail, you must include the traversal cost of finding that position.

Do not choose LinkedList simply because a requirement says "many insertions and removals". You need to know where those insertions and removals happen, whether a cursor is already positioned there, and how other read operations occur.

### Orientation Table

| Usage Pattern | What to Prioritize |
| --- | --- |
| Frequent get/set by index | Positional access capability of the class |
| Primarily sequential traversal | Iterator or enhanced for; avoid repeatedly looking up each index unnecessarily |
| Mid-list insert/remove via an existing cursor | Modification cost at that position |
| Primarily operations at both ends | Consider the Deque contract as well, not just List |
| Read-heavy with special concurrency requirements | Choose a dedicated concurrency policy rather than inferring one from List |

If performance is a practical requirement, measure against representative data samples and operation sequences. Asymptotic complexity helps rule out flawed assumptions, but it does not replace all real-world runtime conditions.

## 9. Mutability Is a Separate Decision

A List can be right in terms of ordering and duplicate elements yet not support the modification operation you are about to perform.

For example:

```java
List<String> fixedData = List.of("A", "B", "A");
List<String> editable = new ArrayList<>(fixedData);
```

Both keep three occurrences in that order. The difference is:

- fixedData does not allow adding, removing, or replacing elements.
- editable is a mutable structural copy that can be modified through the operations supported by ArrayList.

The ability to keep duplicates does not depend on whether the list is modifiable.

### Null Support Cannot Be Inferred from the Name List

Some Lists allow null, while some List creation sources reject it. Decide clearly how missing data is represented and verify the contract of the source.

Do not use "List allows duplicates" to infer that it also allows every value or every operation.

### Mutable Elements Require Their Own Policy

An unmodifiable list structure does not automatically make its elements immutable. Conversely, a modifiable list does not require its elements to be mutable objects.

When the same reference appears multiple times, mutating that object can become visible across multiple positions. If you want each occurrence to have independent state, create distinct occurrence records or copy objects according to an appropriate policy.

## 10. Designing APIs from the Required Contract

Before exposing a List for another component to use, clarify:

- What meaning the order carries.
- Whether equal elements are allowed to appear multiple times.
- Whether the recipient is allowed to add, remove, or modify elements.
- Whether the result is a copy, a shared view, or a live object.
- Within what state scope an index remains valid.
- Whether multiple parties may access and modify it concurrently.

### Request Only the Capabilities Actually Needed

If a method needs to retrieve a specific position, a List parameter makes sense:

```java
static String valueAt(List<String> values, int index) {
    return values.get(index);
}
```

This is an illustrative method declaration; it relies on List for index bounds checking and does not define any extra missing-data policy of its own.

If a method only reads elements sequentially, Iterable may be a narrower, sufficient contract. If a method requires "each value appears only once", consider a Set or explicit validation rather than letting a List parameter create false expectations.

### Returning a List Publishes Ordering Semantics

If an API returns a List, callers may rely on its positional sequence. Determine whether that order is stable across calls and where it originates.

A list created from an unordered source does not automatically gain a meaningful business order just because the return type is List. It has a concrete order in that specific creation instance, but its meaning and repeatability must be intentionally designed.

### Shared Data Needs Clear Ownership

Allowing multiple parties to mutate the same List causes indices and ordering to change outside expected boundaries.

Depending on the problem, you can:

- Keep mutation ownership within a single component.
- Return a structural copy.
- Return an unmodifiable view or collection.
- Use an appropriate coordination mechanism or concurrent data structure.

Do not assume a standard ArrayList is safe when multiple threads modify it concurrently. Likewise, do not assume that individually synchronized methods automatically make an entire multi-step indexed operation sequence atomic.

## 11. Short Decision Workflow

### Step 1: Define What One Element Is

A product code, a scan event, and an event log line are three different units.

If "one element" has not been clearly defined, duplication and counting rules can easily go wrong.

### Step 2: Identify the Information That Must Be Preserved

Ask:

- Do you need full sequence order?
- Do you need to preserve every individual occurrence?
- Do you need index-based access or modification?
- Or do you only need unique membership, counts, or key-based lookup?

### Step 3: Choose the Contract

Choose List, Set, Map, Queue/Deque, or a composite structure based on the answers above.

Do not force every requirement into a List simply because it can hold data.

### Step 4: Choose the Concrete Implementation

Verify:

- Cost of primary operations.
- Mutability.
- Null policy.
- Sharing relationship with the data source.
- Concurrency requirements.

### Step 5: Verify with Data That Exposes Differences

A useful test dataset should include:

- Elements at the beginning.
- Duplicate elements.
- Sequences with identical counts but different orders.
- Insertions or removals before an actively used position.
- Queries by identifier versus queries by position.

The programs in this lesson use these exact scenarios to make the semantics clear, rather than testing only a duplicate-free, unmodified list.

## 12. Common Mistakes

### Choosing a List Simply Because "There Are Multiple Objects"

Every collection manages groups of data according to different models. You need to identify position, duplication, keys, and processing patterns.

### Choosing a Set to Remove Duplicates Without Knowing What Duplicates Mean

Two scans with the same code can still be two real events. Discarding them can destroy valid data.

### Choosing a List Because It "Keeps Duplicates" When Only Counts Are Needed

If individual positions or individual records are unnecessary, a frequency table can express the requirement more clearly. Conversely, counts cannot reconstruct the sequence.

### Assuming Preserving Order Means Always Sorted in Ascending Order

A List preserves the positional order the program currently holds. Sorting is a separate operation or policy.

### Assuming Every List Performs get Equally Fast

LinkedList has get(index) but must traverse to locate the position. Check the implementation class and traversal algorithm.

### Using an Index as a Long-Lived Key

Insertions, removals, and sorting can all shift positions. Use a dedicated identifier when an item must be recognized across state changes.

### Thinking Adding an Object Twice Creates Two Object Copies

A List holds two references at two positions; they can point to the exact same object. If each occurrence needs independent state, model that explicitly.

### Using a List and a Map in Parallel Without an Update Strategy

Two separate structures do not automatically stay consistent. The program needs a single place responsible for adding, removing, and replacing data across both.

### Assuming a List Must Be Modifiable

An unmodifiable List still has positions and can still contain duplicates. Choose a creation source that matches the operations you need to perform.

## 13. Practice

### Exercise 1: Keep Scan Occurrences or Keep Codes?

A device records:

```text
X, Y, X, X, Z
```

Design separate solutions for three requirements:

1. Display the complete history in order.
2. Display the codes that have appeared, each code once.
3. Display the occurrence count of each code.

State which data structure to use and what information is preserved or lost in each choice.

### Exercise 2: Two Sequences with the Same Counts

Create two sequences that have the same frequency table but different orders. Demonstrate that:

- List.equals does not treat them as the same sequence.
- Their frequency tables can be equal.
- The original order cannot be deduced from counts alone.

### Exercise 3: Modeling Playback Occurrences

A playlist allows the same song to appear multiple times.

Determine:

- Whether an element represents a song or a playback entry.
- Which fields are needed if each occurrence requires its own independent state.
- How a song ID differs from a playback position.
- What information is lost if you convert the playlist into a Set by song ID.

### Exercise 4: Choosing a Class by Operation Pattern

Compare the following scenarios:

- Frequent reads of elements at arbitrary positions.
- Traversing from start to finish without needing indices.
- Already holding a ListIterator in the middle and needing insertions/removals around it.
- Primarily adding and removing at both ends.

Explain in terms of locating positions and updating the underlying structure, not just saying "this class is faster".

### Exercise 5: Indices and Identifiers

Extend PositionIsNotIdDemo:

1. Save an initial id and an initial index.
2. Insert or remove an element before that position.
3. Re-sort the list by text.
4. Compare the element at the old index against the step matching the saved id.
5. If maintaining both a Map and a List, describe how to keep them consistent after each operation.

The completion criteria are choosing a data structure that matches the true data unit, preserving sufficient information about positions or occurrences, and clearly separating current positional order from a stable identifier.