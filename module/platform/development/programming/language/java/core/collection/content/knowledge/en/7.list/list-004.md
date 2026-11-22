# indexOf, lastIndexOf, and Finding Non-Existent Elements

A list can contain multiple identical elements. When you need to know the position of a value, you not only ask "is it present or not" but also determine whether you want the **first occurrence**, the **last occurrence**, or **all positions**.

`List.indexOf` and `List.lastIndexOf` solve the first two questions:

- `indexOf(target)`: the position of the first occurrence of a matching element.
- `lastIndexOf(target)`: the position of the last occurrence of a matching element.
- No matching element found: returns `-1`.

A common pitfall is that `-1` still has type `int`, but **is not a valid index for accessing a list**.

This lesson uses Java 17. Three complete programs have been compiled with `--release 17` and run to verify stdout. Other shortened snippets illustrate operations inside a method, not standalone runnable files.

After this lesson, you will be able to:

- Correctly read the first and last indices in a list with duplicate elements.
- Handle `-1` before using the result with `get` or position-based operations.
- Explain the matching rule based on `equals`.
- Distinguish between finding `null`, finding strings, finding objects, and finding by property.
- Identify cases that require a traversal loop instead of repeating `indexOf`.

## 1. Position Model of List

Consider the list:

```text
Value:   Lan   Minh   Lan   An   Lan
Index:    0     1      2    3     4
```

Positions start at `0`. The list has `5` elements, so valid indices are `0..4`.

For the value `"Lan"`:

```text
indexOf("Lan")     = 0
lastIndexOf("Lan") = 4
```

For the value `"Minh"`:

```text
indexOf("Minh")     = 1
lastIndexOf("Minh") = 1
```

For the value `"Mai"`:

```text
indexOf("Mai")     = -1
lastIndexOf("Mai") = -1
```

### The Last Index Is Still Counted from the Beginning of the List

`lastIndexOf` returns a standard list index. It does not return the number of steps counted backward from the end.

In the example, the last `"Lan"` is at index `4`, so the result is `4`, not `0` just because the element is at the very end.

### The First and Last Values Do Not Reveal Every Position

Knowing that the first is `0` and the last is `4` does not tell you the positions in between. They could be `0, 2, 4`, or a different distribution.

You cannot take:

```text
lastIndex - firstIndex + 1
```

as the number of occurrences, because the span between the two positions may contain other elements.

## 2. Signatures and Semantics of the Two Methods

Signature form:

```java
int indexOf(Object target);
int lastIndexOf(Object target);
```

This describes the `List` signatures, not a standalone Java file.

Contractual meaning:

| Method | Result when found |
| --- | --- |
| `indexOf(target)` | Smallest index of a matching element |
| `lastIndexOf(target)` | Largest index of a matching element |

Both methods:

- Do not modify the list.
- Do not reorder the data.
- Do not remove duplicate elements.
- Do not require the list to be sorted.
- Return an index, not the element object itself.

For an argument accepted by the source, if there is no matching element, the result is `-1`. An empty list also has no matching position, so it returns `-1`.

### indexOf Differs from get

| Call | What does the argument mean? | Result |
| --- | --- | --- |
| `list.get(1)` | Index `1` | The element at that position |
| `list.indexOf(1)` on `List<Integer>` | The numeric value `1` to find | The first index containing a matching value, or `-1` |

An integer argument passed to `indexOf` is used as a value to search for, not an access index.

Because the signature accepts `Object`, the fact that a call compiles does not automatically prove that the argument complies with the contract of every implementation class. Keep the element type model consistent and check the source's policy regarding restricted values.

## 3. How Is a Matching Element Determined?

Semantically, a position matches when:

```java
Objects.equals(target, list.get(index))
```

expresses the equality relationship being searched for.

This snippet requires `java.util.Objects` if written in code. It describes the matching contract; it does not require every implementation class to use this exact expression and index-access algorithm.

### equals Differs from Reference Comparison

Two distinct objects in memory can be equal according to `equals`.

For example:

- Two strings with the same content can be considered equal even if they are not the same object.
- A record type with equal components provides value-based equality.
- A class that does not override `equals` retains the default meaning of `Object.equals`, which is based on object identity.

Therefore, if you search using a new object and always receive `-1`, check the type's `equals` contract before concluding that `indexOf` does not work.

### Does Not Automatically Use a Comparator or Natural Ordering

A list that has been sorted using a comparator still uses the element's equality contract when `indexOf` is called.

"Ranking equally in a sort operation" and "being equal according to `equals`" are two distinct relationships. Passing a comparator for a sort operation does not store that comparator as the list's new search policy.

### With String: Matches the Whole Element, Not a Substring

`String.equals` compares content case-sensitively. It does not automatically trim whitespace or normalize input.

For example:

| Call | Meaning |
| --- | --- |
| `List.of("Lan").indexOf("Lan")` | Finds an element equal to the string Lan |
| `List.of("Lan").indexOf("lan")` | Does not match under String's equals rule |
| `List.of("Lan").indexOf("an")` | Does not search for a substring within the element Lan |
| `"Lan".indexOf("an")` | String method that searches for a substring within a single string |

Identical method names do not mean the receiver object and the kind of search are the same.

If your problem requires case-insensitive search, substring search, or search by a specific property, use an explicit custom criterion.

## 4. Complete Program: First, Last, and All Positions

Create the file **`ListPositionLookupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;

public class ListPositionLookupDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "Lan", "An", "Lan");

        System.out.println("names = " + names);
        show(names, "Lan");
        show(names, "Minh");
        show(names, "Mai");
        show(names, "lan");

        List<Integer> positions = new ArrayList<>();
        ListIterator<String> cursor = names.listIterator();
        while (cursor.hasNext()) {
            int index = cursor.nextIndex();
            if (Objects.equals(cursor.next(), "Lan")) {
                positions.add(index);
            }
        }
        System.out.println("all Lan positions = " + positions);
    }

    private static void show(List<String> values, String target) {
        int first = values.indexOf(target);
        int last = values.lastIndexOf(target);
        System.out.println(target + ": first=" + first + ", last=" + last);

        if (first < 0) {
            System.out.println("  not found");
        } else {
            System.out.println("  get(first) = " + values.get(first));
        }
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ListPositionLookupDemo.java
java -Dfile.encoding=UTF-8 ListPositionLookupDemo
```

Verified stdout:

```text
names = [Lan, Minh, Lan, An, Lan]
Lan: first=0, last=4
  get(first) = Lan
Minh: first=1, last=1
  get(first) = Minh
Mai: first=-1, last=-1
  not found
lan: first=-1, last=-1
  not found
all Lan positions = [0, 2, 4]
```

### Reading the Results

- Lan appears at `0, 2, 4`; the two methods return `0` and `4` respectively.
- Minh only appears at `1`, so the first and last positions are the same.
- Mai does not exist, so both results are `-1`.
- The string `"lan"` differs from `"Lan"` according to `String.equals`, so it does not match.
- The `first < 0` branch handles the not-found case; only the other branch calls `get(first)`.
- Position `0` is recognized as a normal match.

### Why Include a Traversal Loop to Find All Positions?

The position list `[0, 2, 4]` is collected using a single `ListIterator` pass:

1. Read `nextIndex()` before retrieving the element.
2. `next()` returns the element at that index.
3. If it matches, record the index.

This is a separate traversal pass with an explicit criterion. `indexOf` and `lastIndexOf` do not return that set of positions on behalf of the program.

Using `Objects.equals` inside the loop allows the matching criterion to handle `null` references as well, when the source permits them.

## 5. Handling -1 Safely

An appropriate usage pattern:

```java
int found = values.indexOf(target);

if (found >= 0) {
    String value = values.get(found);
    System.out.println(value);
} else {
    System.out.println("Không tìm thấy");
}
```

This snippet assumes `values` is a list of strings, `target` is the value to find, and the list is not modified between operations.

### Mistake: Using the Result Directly

```java
String value = values.get(values.indexOf(target));
```

If not found, the program executes `get(-1)`, throwing an `IndexOutOfBoundsException`.

Not finding an element is a normal search outcome; turning it into an index access error is usually due to a missing handling branch in the application.

### Mistake: Checking Only Greater Than 0

```java
if (found > 0) {
    System.out.println("Đã tìm thấy");
}
```

This condition ignores the element at the very first position. A valid index can be `0`.

Two commonly used checks are:

```text
found >= 0
found != -1
```

The first directly expresses the non-negative index domain.

### Mistake: Checking Only Less Than size

For a non-empty list, `-1 < values.size()` is still true. Checking only the upper bound does not rule out the missing-value indicator.

If you are validating an arbitrary index for `List` access, both bounds are required:

```text
0 <= index < size
```

For an index just returned by `indexOf` on an unmodified list, the `found >= 0` branch already relies on the return contract to know that it lies within the upper bound.

### Mistake: Converting -1 to 0 for a "Default Value"

Forcing a missing result to the first position does not make the target element appear. It causes the program to fetch a different element while appearing to run normally.

If fallback behavior is needed, write that branch explicitly: display a message, return an empty result according to the API contract, or handle it according to business requirements. Do not use a fake index to mask absence.

## 6. Null Is an Element, Distinct from Not Found

For a list that permits `null`:

```text
[null, A, null, B]
```

you can have:

```text
indexOf(null)     = 0
lastIndexOf(null) = 2
```

`-1` indicates that no matching position exists. It does not mean the same thing as "the element at the found position is null".

Distinguish between:

| Scenario | Position lookup result |
| --- | --- |
| A null element exists at the beginning | Index `0` |
| A null element exists at another position | The corresponding non-negative index |
| No matching element exists | `-1`, if the argument is accepted by the source |

### The Source May Restrict null

Not every `List` allows `null` elements or accepts `null` queries under the same policy. For example, lists that disallow `null` may reject such a query with a `NullPointerException`.

Do not assume that calling `indexOf(null)` on every `List` is guaranteed to return only an index or `-1`. Verify the source contract.

In the following program, the chosen source is an `ArrayList` created from an input containing `null` elements so that the scenario is well-defined.

## 7. Complete Program: Missing, Empty, and Null

Create the file **`MissingAndNullDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MissingAndNullDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList(null, "A", null, "B"));

        System.out.println("values = " + values);
        System.out.println("first null = " + values.indexOf(null));
        System.out.println("last null = " + values.lastIndexOf(null));

        int found = values.indexOf("Z");
        System.out.println("Z position = " + found);

        if (found >= 0) {
            System.out.println("Z value = " + values.get(found));
        } else {
            System.out.println("Z is absent");
        }

        try {
            values.get(found);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(-1) = "
                    + exception.getClass().getSimpleName());
        }

        List<String> empty = List.of();
        System.out.println("empty first A = " + empty.indexOf("A"));
        System.out.println("empty last A = " + empty.lastIndexOf("A"));

        List<Integer> numbers = List.of(10, 20, 10);
        System.out.println("numbers.get(1) = " + numbers.get(1));
        System.out.println("numbers.indexOf(1) = " + numbers.indexOf(1));
        System.out.println("numbers.lastIndexOf(10) = " + numbers.lastIndexOf(10));
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 MissingAndNullDemo.java
java -Dfile.encoding=UTF-8 MissingAndNullDemo
```

Verified stdout:

```text
values = [null, A, null, B]
first null = 0
last null = 2
Z position = -1
Z is absent
get(-1) = IndexOutOfBoundsException
empty first A = -1
empty last A = -1
numbers.get(1) = 20
numbers.indexOf(1) = -1
numbers.lastIndexOf(10) = 2
```

### Verified Cases

1. `null` has specific first and last positions.
2. Z does not exist, so it receives `-1`.
3. The index-checking branch handles the absence of Z without calling `get`.
4. The `get(found)` call outside the safe branch is intentionally placed in the experiment to show that `get(-1)` throws an exception.
5. An empty list returns `-1` when searching for A.
6. `numbers.get(1)` returns the element `20`.
7. `numbers.indexOf(1)` searches for the value `1`, which is absent, so it returns `-1`.
8. `lastIndexOf(10)` returns the last position of the value `10`, which is `2`.

The exception-catching block in the program is used to illustrate a known misuse. In normal search-handling code, check the result before accessing rather than using an exception as the "not found" branch.

## 8. Finding an Object Is Not Automatically Finding by a Single Property

Suppose a product consists of:

```text
code
name
```

We might have two different problems:

- Find a `Product` that is equal according to `equals`.
- Find a product with the same `code`, regardless of `name`.

`indexOf` only directly solves the first problem according to `Product`'s contract. It does not know whether the `code` property has any special business meaning unless you have designed it that way.

In the program, `Product` is a record. The equality provided by the record examines both the `code` and `name` components.

### Complete Program

Create the file **`ObjectPositionLookupDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class ObjectPositionLookupDemo {
    public record Product(String code, String name) {
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P1", "Pen"),
                new Product("P2", "Book"),
                new Product("P1", "Pen"));

        Product sameValue = new Product("P1", "Pen");
        Product sameCodeOnly = new Product("P1", "Pencil");

        System.out.println("same reference = " + (products.get(0) == sameValue));
        System.out.println("same value = " + products.get(0).equals(sameValue));
        System.out.println("sameValue first = " + products.indexOf(sameValue));
        System.out.println("sameValue last = " + products.lastIndexOf(sameValue));
        System.out.println("sameCodeOnly indexOf = " + products.indexOf(sameCodeOnly));
        System.out.println("find P1 by code = " + firstIndexByCode(products, "P1"));
        System.out.println("find P9 by code = " + firstIndexByCode(products, "P9"));
    }

    private static int firstIndexByCode(List<Product> products, String code) {
        for (int index = 0; index < products.size(); index++) {
            if (Objects.equals(products.get(index).code(), code)) {
                return index;
            }
        }
        return -1;
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 ObjectPositionLookupDemo.java
java -Dfile.encoding=UTF-8 ObjectPositionLookupDemo
```

Verified stdout:

```text
same reference = false
same value = true
sameValue first = 0
sameValue last = 2
sameCodeOnly indexOf = -1
find P1 by code = 0
find P9 by code = -1
```

### Why Can a New Object Still Be Found?

`sameValue` does not share the same reference as the first element, but both `code` and `name` are identical. Under the record's equality, they are equal, so `indexOf` finds it at `0`.

Because there is also an equal `Product` at the end, `lastIndexOf` returns `2`.

### Why Might an Object with the Same Code Still Not Be Found?

`sameCodeOnly` has code P1 but name Pencil, which differs from the name Pen in the source data. Under the equality of the record in use, it does not match.

The `firstIndexByCode` method describes a different criterion:

```text
Product code equals the target code
```

Consequently, searching for P1 by code returns `0`, while searching for P9 returns `-1`.

The illustrative method assumes the `Product` elements are non-null. Using `Objects.equals` for `code` safely compares potentially null code values, but does not protect against calling `code()` on a null `Product` element.

### Should You Modify equals So indexOf Searches by Code?

Only do so if "two `Product` instances are equal when they share the same code" is the true domain contract for that type across the entire system. `equals` affects many other places, not just a single search call.

If only the current screen or task needs to search by a single property, write a dedicated search criterion. Do not alter the equality definition of the entire type just to save one loop.

## 9. A Found Index Is Tied to the List's State

The result is a position in the list at the moment of the search, not a stable identifier for the element.

Illustrative snippet:

```java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

int found = values.indexOf("B"); // found = 1
values.add(0, "X");

// values is now [X, A, B, C].
// values.get(found) now returns A, not B.
```

Inserting at the beginning shifted the position of B.

Operations that can invalidate the previous meaning of a saved index include:

- Inserting or removing elements before that position.
- Reordering or sorting the list.
- Replacing the element at the found position.
- Mutating the data on which the `equals` rule depends.

Therefore:

- Use the index immediately within a scope where the list state remains stable.
- If you must store a long-lived reference to an item, use an appropriate identifier instead of an index.
- If multiple parties modify the list, searching and then accessing requires proper coordination.
- Even a collection with thread-safe methods does not automatically make the sequence "find index, then use index" atomic.

In the complete examples of this lesson, no concurrent modifications occur between searching and accessing, so that condition is clearly established.

## 10. Cost and When to Use a Single Traversal Pass

In common lists such as `ArrayList` and `LinkedList`, searching by value may require inspecting many elements. The worst case typically grows linearly with the number of elements.

The two methods can also stop at different points:

- When a matching element lies near the beginning, `indexOf` can find it early.
- When it lies near the end, `lastIndexOf` can find it early.
- When it does not exist, the search must confirm that no matching position exists across the entire search range.

Do not rely on small examples to assume that value-based lookup always has constant cost.

### Avoid contains Followed by indexOf When You Only Need the Position

A common unnecessary pattern:

```java
if (values.contains(target)) {
    int found = values.indexOf(target);
    System.out.println(found);
}
```

If the goal is already to obtain the index, calling `indexOf` once and checking against `-1` is usually sufficient. The two calls above can trigger two separate search passes, and if the source changes between them, the two results might not even reflect the same state.

Conversely, if you only need a yes/no answer, `contains` expresses that intent directly.

### When You Need All Positions

Use a single traversal loop and collect the matching indices, as shown in the first program.

`List.indexOf` does not have a `fromIndex` starting-offset parameter like some `String` search methods. If you repeatedly search across sublists, you must manually manage index offsets and may end up performing multiple scans.

A single indexed iterator pass makes the scope clear and avoids redundantly scanning the same data.

### When Searching by Property

A loop with an explicit condition is usually suitable for a standalone task.

If the system frequently looks up data by a key, reconsider the storage model: you may need an accompanying index or `Map`. However, keep requirements around duplicate elements, ordering, and data synchronization clear; do not blindly replace a `List` with a `Map` assuming every semantic detail remains identical.

### Be Careful with get(index) Loops on LinkedList

The search-by-code method in the example emphasizes how to determine a position on a small dataset. If you apply an index-by-index `get(index)` algorithm to a large linked list, re-traversing nodes for every `get` can cause the total cost to grow unacceptably.

When writing a general traversal across various `List` types, a `ListIterator` or sequential traversal mechanism avoids assuming fast random access. That is a matter of choosing an algorithm suited to the data structure; it does not change the contract of returning `-1` or the found index.

## 11. Common Mistakes

### Confusing -1 with the Last Element

In Java's `List`, `-1` is not syntax for accessing the last element. It is the sentinel value indicating "not found" for the two methods covered here.

### Ignoring Position 0

Using `found > 0` as the match condition treats data at the start of the list as missing. Check for the non-negative domain instead.

### Assuming lastIndexOf Counts from the End

The returned index still uses the zero-based indexing system from the start of the list. The last element of a list of size `n` has index `n - 1`.

### Assuming indexOf Searches Substrings or Ignores Case Automatically

With `List<String>`, the lookup compares whole elements using `String.equals`. If you want a different criterion, you must express it explicitly.

### Assuming Identical Codes Automatically Mean equals

The meaning of equality depends on the element type. A record with multiple components does not automatically treat a single component as its unique key.

### Calling get Before Checking for -1

Reversing this order causes an index access exception when the target object does not exist. Not finding an element is a branch that must be anticipated up front.

### Using a null Element to Conclude Not Found

Finding a position that currently holds `null` is still a successful match. Use the index result to determine presence, rather than only looking at the value returned by `get`.

### Saving an Index Across Multiple Modifications

An index is not a stable identifier. If the list is modified or reordered, you must re-evaluate how any previously saved position is used.

### Taking the First-to-Last Span as the Duplicate Count

That span may contain other values in between. To count occurrences or collect every position, traverse the list with the appropriate criterion.

## 12. Practice

### Exercise 1: Predict Positions

Given:

```text
[red, blue, red, green, red]
```

Without running code first, fill in:

| Target value | indexOf | lastIndexOf |
| --- | --- | --- |
| red | ? | ? |
| blue | ? | ? |
| yellow | ? | ? |
| RED | ? | ? |

Explain the matching rule used and why the number of occurrences of `red` does not equal the span from the first index to the last index.

### Exercise 2: Fix the Not-Found Branch

Code snippet:

```java
int found = names.indexOf(target);
System.out.println(names.get(found));
```

Add handling logic so that:

1. An element at position `0` is still recognized as found.
2. A non-existent target does not cause a `get` error.
3. `-1` is not converted into a fake position.
4. The list is not searched twice when only a single position result is needed.

### Exercise 3: Distinguish null from Absence

Create an `ArrayList` from:

```text
[A, null, B, null]
```

Predict:

- The first position of `null`.
- The last position of `null`.
- The result of searching for `C`.
- The condition used to distinguish finding `null` from not finding an element.

The two `null` positions should be `1` and `3` respectively; searching for `C` returns `-1`.

### Exercise 4: Search by Value vs. Search by Property

Starting from `ObjectPositionLookupDemo`:

1. Add a `Product` with code `P1` but a different `name`.
2. Search for an object matching both `code` and `name`.
3. Find the first match by `code`.
4. Write a traversal pass to collect all positions matching by `code`.
5. Explain why the two criteria can produce different sets of positions.

### Exercise 5: Inspect Stale Indices

Find the position of `B` in `[A, B, C]`, then separately test each operation:

- Insert `X` at the beginning.
- Remove `A`.
- Replace `B` with `Y` at the known position.

Track the value of the index variable and the content at that position. State when the index still represents the original element and when you need to search again or use a different form of identification.

The completion criteria are accurately identifying the matching relationship, selecting the right first/last index, explicitly handling absence, and only using position results while the list remains in a compatible state.
