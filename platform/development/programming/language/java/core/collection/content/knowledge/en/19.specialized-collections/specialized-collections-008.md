# Enumeration and Converting to Iterator or List

## 1. When a Legacy API Returns an Object for Traversal

Some Java APIs return an `Enumeration<E>` instead of a `List` or `Iterator`. For example, `Vector.elements()` lets you retrieve a `Vector`'s elements one by one. When you need to pass that data into code that uses `Iterator` or process it as a list, you must first determine whether you are converting **how it is traversed** or **collecting the data into a new collection**.

`Enumeration` is an interface for sequentially retrieving elements one at a time. It is not a container that holds all data under the contract of a `List`, nor is it the `enum` keyword used to declare a set of constants.

The following three types have different meanings:

| Object | Role | What to Think About |
|---|---|---|
| `Enumeration<E>` | A sequential read pass over elements | What has not been retrieved yet? |
| `Iterator<E>` | Standard traversal interface in the Collections Framework | How to use `hasNext`/`next` and optional operations |
| `List<E>` | Collection holding elements by position | Storing data, accessing by index, creating new traversal passes |

Converting from `Enumeration` to `Iterator` via `asIterator()` adapts the interface for the remaining elements. Converting to `List` via `Collections.list(...)` consumes all remaining elements to create a new `ArrayList`. Neither automatically rewinds to elements that were already read.

The complete programs in this lesson use Java 17 or later. The manual adapter section at the end is also verified to compile with Java 8 to illustrate how to handle environments without `Enumeration.asIterator()`.

## 2. The Traversal Contract of Enumeration

### 2.1. Two Primary Methods

| Method | Return Type | Meaning |
|---|---|---|
| `hasMoreElements()` | `boolean` | Are there any more elements to retrieve? |
| `nextElement()` | `E` | Retrieves the next element and advances the traversal |

Calling `nextElement` repeatedly returns consecutive elements. Once exhausted, `nextElement` throws `NoSuchElementException`; it does not use `null` as an end-of-stream signal.

The illustrative snippet below is placed inside a method that already has an `elements` variable, and is not a standalone Java file:

```java
while (elements.hasMoreElements()) {
    String value = elements.nextElement();
    System.out.println(value);
}
```

Do not call `nextElement` just to check whether data remains, because each valid call consumes one element from the traversal. Also do not call `nextElement` twice in the same iteration if you only intend to process one element: the second call will read the next element.

### 2.2. An Advancing Read Position, Not a Self-Repeating Collection

Imagine a source containing A, B, C where the `Enumeration` has already returned A:

```text
Data source:         [A, B, C]
Already read:        A
Remaining:           B, C
Next read position:     ↑
```

`Enumeration` has no `reset`, `get(index)`, `size`, or `remove` method in its interface. If you need to traverse from the beginning again, you need a new traversal provided by the source, or you need to store the elements in a separate collection.

Exhausting an `Enumeration` does not mean removing the elements from the `Vector` or source collection. **Traversal cursor state** is distinct from **source data content**.

### 2.3. Ordering and Nulls Depend on the Data Source

`Enumeration` does not sort elements or remove duplicates on its own. It returns elements according to the contract of the API that provides it. For `Vector` in these examples, that is the element order of the `Vector`.

A `null` element can appear if the source allows it. Therefore, a loop condition like `nextElement() == null` is not generally valid: it both advances the traversal and can stop prematurely on a valid `null` element. Use `hasMoreElements` to check whether elements remain.

The [Enumeration — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html) documentation is the reference for these rules.

## 3. Program 1: A Basic Traversal Pass

Save the complete program to `EnumerationBasicsDemo.java`. `Vector` is used here to demonstrate an actual API that returns an `Enumeration`.

```java
import java.util.Arrays;
import java.util.Enumeration;
import java.util.NoSuchElementException;
import java.util.Vector;

public class EnumerationBasicsDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("alpha", "beta", "gamma"));
        Enumeration<String> elements = source.elements();
        int count = 0;
        while (elements.hasMoreElements()) {
            String value = elements.nextElement();
            System.out.println("value=" + value);
            count++;
        }
        System.out.println("count=" + count);
        System.out.println("hasMore=" + elements.hasMoreElements());
        System.out.println("sourceSize=" + source.size());
        try {
            elements.nextElement();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("exhaustedNext=NoSuchElementException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumerationBasicsDemo.java
java EnumerationBasicsDemo
```

Stdout:

```text
value=alpha
value=beta
value=gamma
count=3
hasMore=false
sourceSize=3
exhaustedNext=NoSuchElementException
```

### 3.1. Reading to the End Does Not Empty the Source

Three iterations retrieve `alpha`, `beta`, `gamma`. `count` is `3` and `hasMore` afterward is `false`, yet `sourceSize` remains `3`. No removal operation was called.

Calling `nextElement` after exhaustion throws `NoSuchElementException`, as specified by the contract. Never write logic that expects it to return a special sentinel value at the end.

If you need to read the same `Vector` again, you can call `source.elements()` to obtain a fresh `Enumeration` of the source data at that time. Assigning another variable to point to the old `Enumeration` does not rewind its read position.

## 4. How Do Enumeration and Iterator Differ?

| Enumeration | Iterator | Notes |
|---|---|---|
| `hasMoreElements()` | `hasNext()` | Checks whether elements remain |
| `nextElement()` | `next()` | Retrieves and advances to the next element |
| No `remove` | `remove()` is an optional operation | Not every `Iterator` supports removal |
| Has `asIterator()` since Java 9 | Has `forEachRemaining()` since Java 8 | Helps bridge APIs using different interfaces |

Neither `Enumeration` nor `Iterator` automatically becomes an `Iterable`. Converting to `Iterator` lets you use `hasNext`/`next` or `forEachRemaining`, but that does not make an `Iterator` variable directly usable in enhanced `for-each` loops that require an `Iterable`.

When designing a new API that needs to expose traversal, you should generally choose the appropriate Collections Framework interfaces rather than creating an unnecessary `Enumeration` API. When receiving an `Enumeration` from an existing API, you can adapt it at the boundary where it is used.

## 5. Converting to Iterator with asIterator

### 5.1. Traversing the Remaining Elements Without Copying Everything

On Java 9 and later, call `elements.asIterator()` to obtain an `Iterator` that traverses the remaining elements covered by the `Enumeration`. Java 17 supports this method.

The default implementation delegates `hasNext` to `hasMoreElements` and `next` to `nextElement`. It does not eagerly read all data into a new `List`. If `A` was already retrieved beforehand, the `Iterator` continues from `B`.

### 5.2. Do Not Interleave Calls on the Original Enumeration After Adapting

The API specifies that traversal behavior is unspecified if methods continue to be called on the `Enumeration` after calling `asIterator`. Therefore, after creating the adapter, calling code must continue through the `Iterator` and must not interleave `elements.nextElement()` or directly inspect the original `Enumeration`.

Do not treat the `Enumeration` and the resulting `Iterator` as two independent cursors. Also do not create multiple adapters from the same `Enumeration` assuming each adapter can read its own copy of the data from the beginning.

In the next program, there is one read from the `Enumeration` before `asIterator`; after adaptation, all traversal operations go through the `Iterator`. Inspecting the contents of the source `Vector` is not a call back into the `Enumeration`.

### 5.3. The Resulting Iterator Does Not Automatically Support Removal

The default implementation of `asIterator` returns an `Iterator` whose `remove` method throws `UnsupportedOperationException`. `Enumeration` does not provide a removal operation for the adapter to forward to.

This remains true for the default adapter even when the underlying data source is a mutable `Vector`. Modifiability of the source collection does not mean every traversal wrapper around it supports removal.

`Iterator.remove` is generally an optional operation. To remove elements during traversal, you need an `Iterator` whose source API genuinely supports that operation, and you must follow the `next`/`remove` lifecycle rules. Do not force removal support into an adapter by guessing how to mutate the backing collection.

## 6. Program 2: Adapting the Remaining Elements

Save to `EnumerationIteratorDemo.java`:

```java
import java.util.Arrays;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.NoSuchElementException;
import java.util.Vector;

public class EnumerationIteratorDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("A", "B", "C"));
        Enumeration<String> elements = source.elements();
        System.out.println("beforeAdapt=" + elements.nextElement());
        Iterator<String> iterator = elements.asIterator();
        System.out.println("iteratorHasNext=" + iterator.hasNext());
        System.out.println("iteratorNext=" + iterator.next());
        try {
            iterator.remove();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("remove=UnsupportedOperationException");
        }
        iterator.forEachRemaining(value -> System.out.println("remaining=" + value));
        System.out.println("iteratorHasNextAfter=" + iterator.hasNext());
        System.out.println("sourceAfterTraversal=" + source);
        try {
            iterator.next();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("exhaustedIteratorNext=NoSuchElementException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumerationIteratorDemo.java
java EnumerationIteratorDemo
```

Stdout:

```text
beforeAdapt=A
iteratorHasNext=true
iteratorNext=B
remove=UnsupportedOperationException
remaining=C
iteratorHasNextAfter=false
sourceAfterTraversal=[A, B, C]
exhaustedIteratorNext=NoSuchElementException
```

### 6.1. A Was Already Read Before Adaptation

`beforeAdapt=A` comes from `nextElement` called before `asIterator`. The `Iterator` starts at `B`, so `iteratorNext` prints `B`, and then `forEachRemaining` processes `C`. `A` is not replayed.

`hasNext` after traversal is `false`. Calling `next` on the exhausted `Iterator` also throws `NoSuchElementException`. `source` remains `[A, B, C]` because traversal does not remove elements.

### 6.2. The remove Method Is Rejected

The `remove` call is placed right after a valid `next`, yet it still throws `UnsupportedOperationException` because the default adapter does not support removal. This differs from the case where an `Iterator` supports `remove` but the caller violates its lifecycle rules.

`forEachRemaining` is simply a more convenient way to process the remaining elements than a `while` loop. It does not create a backing store and does not provide the ability to re-traverse afterward.

## 7. Converting to List with Collections.list

### 7.1. Collecting All Remaining Elements into a New ArrayList

`Collections.list(elements)` returns an `ArrayList<E>` containing the elements that the `Enumeration` still yields, in the exact order they are retrieved. The method must traverse the source to the end to build the list.

Illustrative snippet inside a method that already has an `Enumeration<String>`:

```java
ArrayList<String> items = Collections.list(elements);
```

You can declare the result type as `List<String>` if you only need the `List` interface. The actual object type returned by the API is still `ArrayList`.

The resulting list does not include elements that were already read earlier. Given a source of `A, B, C` where `A` has already been retrieved, `list` collects only `B, C`. If the `Enumeration` is already exhausted, the result is an empty `ArrayList`.

The contract at [Collections.list — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html) guarantees element ordering matching the `Enumeration`. It does not sort alphabetically, deduplicate, or go back to the source to read a fresh pass.

### 7.2. Enumeration State Is Consumed; Source Data Is Not Removed

`Collections.list` must invoke traversal operations to collect elements. Therefore, the `Enumeration` reaches its end once the method completes normally on a finite source.

That is not equivalent to removing elements from the source collection. If the `Enumeration` reads from a `Vector`, the `Vector`'s elements remain intact; only the traversal pass has been consumed.

Calling `list` twice in a row on the same `Enumeration` does not produce two identical copies: the first call collects the remaining elements, and the second call typically returns an empty list because the traversal is exhausted. If multiple places need the collected data, keep the resulting `List` and create `Iterator` instances from that `List` as needed.

### 7.3. The Result Is Structurally Modifiable, but Elements Are Not Deep-Copied

The new `ArrayList` supports `add`, `remove`, or `set` according to its contract. Structural changes or replacing element references in the new list do not automatically modify the source `Vector`.

However, the method copies element references; it does not deep-clone each object. If an element is a mutable `StringBuilder`, both `source` and the new list can observe mutations made to that same object.

Keep these three questions separate:

1. Is the containing list a new structure? Yes.
2. Are the elements inside deep-cloned? No.
3. Does collecting into a list reset the `Enumeration` to the beginning? No.

### 7.4. Nulls and Duplicates Are Preserved

If the `Enumeration` returns `B, B, C`, the list has two positions holding `B`. If the source returns a valid `null` element, the resulting `ArrayList` preserves `null` at the corresponding index. Converting to `List` does not apply any null-filtering or deduplication policy.

You must distinguish a `null` element from the `Enumeration` variable itself being `null`. A valid `Enumeration` can yield `null`; passing a `null` `Enumeration` reference is not a way to request an empty list.

## 8. Program 3: Remaining Elements, Shallow Copy, and Nulls

Save the complete program to `EnumerationListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Vector;

public class EnumerationListDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("A", "B", "B", "C"));
        Enumeration<String> elements = source.elements();
        System.out.println("consumedBeforeCopy=" + elements.nextElement());
        ArrayList<String> remaining = Collections.list(elements);
        System.out.println("remainingCopy=" + remaining);
        System.out.println("sourceHasMore=" + elements.hasMoreElements());
        remaining.set(0, "B2");
        remaining.add("D");
        System.out.println("modifiedCopy=" + remaining);
        System.out.println("unchangedSource=" + source);
        System.out.println("freshFullCopy=" + Collections.list(source.elements()));
        System.out.println("copyOfExhausted=" + Collections.list(elements));

        Vector<String> nullable = new Vector<>(Arrays.asList("x", null, "y"));
        ArrayList<String> nullCopy = Collections.list(nullable.elements());
        System.out.println("nullCopy=" + nullCopy);
        System.out.println("nullCopySize=" + nullCopy.size());

        Vector<StringBuilder> builders = new Vector<>();
        builders.add(new StringBuilder("shared"));
        ArrayList<StringBuilder> shallow = Collections.list(builders.elements());
        shallow.get(0).append("!");
        System.out.println("mutableSourceValue=" + builders.get(0));
        System.out.println("sameElementReference=" + (builders.get(0) == shallow.get(0)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumerationListDemo.java
java EnumerationListDemo
```

Stdout:

```text
consumedBeforeCopy=A
remainingCopy=[B, B, C]
sourceHasMore=false
modifiedCopy=[B2, B, C, D]
unchangedSource=[A, B, B, C]
freshFullCopy=[A, B, B, C]
copyOfExhausted=[]
nullCopy=[x, null, y]
nullCopySize=3
mutableSourceValue=shared!
sameElementReference=true
```

### 8.1. Only B, B, C Are Collected into the First Copy

`consumedBeforeCopy=A` retrieves `A` before the `list` call. Therefore `remainingCopy=[B, B, C]`, preserving both occurrences of `B`. `sourceHasMore=false` confirms that the `Enumeration` has been completely traversed.

Changing the first element of `remaining` to `B2` and adding `D` produces `[B2, B, C, D]`. The source `Vector` remains `[A, B, B, C]`; no deletions or `set` calls are propagated back to it.

### 8.2. A Fresh Traversal Differs from Reusing an Exhausted One

`Collections.list(source.elements())` receives a new `Enumeration` from the `Vector` holding the data, so `freshFullCopy` contains all of `A, B, B, C`. `Collections.list(elements)` on the already-exhausted `Enumeration` yields `copyOfExhausted=[]`.

The difference lies in the object providing the traversal, not in renaming the result variable. If the source changes before a new `Enumeration` is created, the new traversal reads the source data according to its contract at that moment; it is not automatically a historical snapshot of the previous pass.

### 8.3. A null Element Does Not Terminate Reading

`nullCopy=[x, null, y]` and size `3` show that a `null` in the middle does not cause collection to stop before `y`. This is why `hasMoreElements` is used as the condition for remaining data.

### 8.4. A New Structure Still Shares a Mutable Object

The final section creates a `Vector` containing a `StringBuilder` with content `shared`. `Collections.list` creates a new `ArrayList`, but the first element is still the exact same `StringBuilder`. Appending an exclamation mark through the list causes the source to see `shared!`.

`sameElementReference=true` explains that result. A new list does not mean the entire object graph inside has been copied. If the data requires deep independence, copying must be designed according to the element type.

## 9. Choosing Iterator or List Based on Downstream Work

| Need | Approach | Key Impact |
|---|---|---|
| Process the remaining elements sequentially once | Traverse `Enumeration` directly or adapt to `Iterator` | Does not require retaining all elements |
| Pass into an API that accepts `Iterator` | `asIterator()` on Java 9+ | Adapts the remaining traversal |
| Need `size`, positional access, or multiple passes | `Collections.list(...)` | Collects all remaining elements into a new `ArrayList` |
| Need both data retention and an `Iterator` | Collect into a `List` first, then obtain `Iterator`s from the `List` | Provides stored data to create separate traversals |
| Legacy API requires `Enumeration` but input is a `Collection` | `Collections.enumeration(collection)` | Bridge in the reverse direction |

Do not collect a large `List` just to call `forEach` once if you have no need to retain the data. Conversely, do not pass the same `Enumeration` to multiple places expecting each to receive all data from the start.

When you need both storage and `Iterator`s, the illustrative snippet is:

```java
// Illustration: source is an Enumeration<String> that has not been adapted yet.
List<String> items = Collections.list(source);
Iterator<String> firstPass = items.iterator();
Iterator<String> secondPass = items.iterator();
```

The two `Iterator`s of the `ArrayList` maintain separate traversal positions over the same list. They do not come from calling `asIterator` twice on the original `Enumeration`. The list is still mutable, so its rules regarding modifying the source during traversal must still be respected.

### 9.1. Cost of Collecting Data

If `n` elements remain, `Collections.list` must retrieve `n` elements and allocate a structure to hold the corresponding references. Beyond the linear work of building the list, there is also the cost of the source itself supplying each element.

`Enumeration` does not expose `size` in its interface and may produce data through mechanisms specific to the source API. When the source is large, choose full collection only if the task requires it. With an unbounded source, an operation trying to collect everything cannot finish the way a finite list does.

An `Iterator` adapter does not eagerly load all `n` elements. It is suitable for element-by-element processing, though it does not turn the source into something rewindable.

### 9.2. Do Not Cast to Fake a Conversion

An `Enumeration` object does not automatically implement `Iterator` or `List` just because all of these types relate to traversal. Casting only checks/asserts an object's runtime type; it does not create an adapter and does not collect data. If the object does not implement the target interface, casting can throw `ClassCastException`.

Using `asIterator` or `Collections.list` explicitly expresses the intended operation and lets readers evaluate its effect on the remaining traversal.

## 10. Reverse Direction: Collection to Enumeration

When a legacy library requires an `Enumeration`, `Collections.enumeration(collection)` creates a bridge from an existing `Collection`. For example, a `List` storing names can be passed into a legacy API via a corresponding `Enumeration`.

This is an adapter choice at the boundary between two APIs. There is no need to change your entire program's data model back to `Vector` just to obtain an `Enumeration` return type.

The `enumeration` method does not contractually create a deep copy or freeze the source data. If you need an independent container before handing it off to other code, explicitly copy the collection first, and then create the `Enumeration` from that copy. Ordering and rules for modifying the source during traversal still depend on the actual collection/API.

For a `List`, traversal follows list order. The bridge does not sort, deduplicate, or filter `null`s. An existing `Iterator` is not a valid `Collection` argument: you must check whether the input API actually holds a backing collection or only a single-use traversal.

## 11. Manual Adapter When Java 8 Compatibility Is Required

### 11.1. Forwarding the Two Read Operations

`Enumeration.asIterator()` was added in Java 9. If code must compile for Java 8, you can create an `Iterator` that delegates `hasNext` to `hasMoreElements` and `next` to `nextElement`.

This adapter only wraps the read pass; it does not create a `List`. You must use a single consistent traversal path through the adapter after handing over control, avoiding other code concurrently consuming the original `Enumeration` and dropping elements unbeknownst to the reader.

The next program validates the source reference with `Objects.requireNonNull` as soon as the adapter is created. When the source is `null`, the error is caught at the conversion boundary. A valid but empty source remains a normal case.

### 11.2. Accepting a Producer-Only Source

Declaring `Enumeration<? extends T>` means the source may supply a subtype of `T`. `Enumeration` only yields data according to its interface; the adapter does not insert elements into the source.

Because `Integer` is a `Number`, the method in the example can produce an `Iterator<Number>` from an `Enumeration<Integer>`. The returned objects are still the original `Integer` instances. Generics do not clone elements or convert `Integer` into a different numeric type.

You do not need raw types or unchecked casts to write this bridge. If a legacy API returns a raw `Enumeration`, generics on the receiving side cannot automatically verify every object inside; you must check and handle actual runtime types according to that API's contract.

### 11.3. Omitting remove Uses Iterator's Default Implementation

The anonymous class only implements `hasNext` and `next`. It inherits `Iterator`'s default `remove` method, so calling `remove` throws `UnsupportedOperationException`. Do not write an empty `remove` method to fake success: calling code would mistakenly assume data was deleted.

If you truly need to remove elements from a collection, use a mechanism supported by that collection. A valid removal operation cannot be inferred from the `Enumeration` interface alone.

## 12. Program 4: Bridging, Generics, and Empty Sources

Save the complete program to `EnumerationCompatibilityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class EnumerationCompatibilityDemo {
    static <T> Iterator<T> adapt(Enumeration<? extends T> source) {
        Objects.requireNonNull(source, "source");
        return new Iterator<T>() {
            @Override
            public boolean hasNext() {
                return source.hasMoreElements();
            }

            @Override
            public T next() {
                return source.nextElement();
            }
        };
    }

    public static void main(String[] args) {
        List<String> modern = new ArrayList<>(Arrays.asList("red", "blue"));
        Enumeration<String> forLegacy = Collections.enumeration(modern);
        ArrayList<String> copyBack = Collections.list(forLegacy);
        modern.clear();
        System.out.println("copyBack=" + copyBack);
        System.out.println("modernSizeAfterClear=" + modern.size());

        Enumeration<Integer> integers =
                Collections.enumeration(Arrays.asList(10, 20));
        Iterator<Number> numbers = adapt(integers);
        System.out.println("number=" + numbers.next());
        try {
            numbers.remove();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("compatRemove=UnsupportedOperationException");
        }
        numbers.forEachRemaining(number -> System.out.println("number=" + number));
        System.out.println("hasNextAfter=" + numbers.hasNext());
        ArrayList<String> emptyCopy =
                Collections.list(Collections.<String>emptyEnumeration());
        emptyCopy.add("later");
        System.out.println("mutableEmptyCopy=" + emptyCopy);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumerationCompatibilityDemo.java
java EnumerationCompatibilityDemo
```

Stdout:

```text
copyBack=[red, blue]
modernSizeAfterClear=0
number=10
compatRemove=UnsupportedOperationException
number=20
hasNextAfter=false
mutableEmptyCopy=[later]
```

### 12.1. The Collected List Exists Independently of the Source Structure

`modern` starts as a `List` containing `red` and `blue`. `Collections.enumeration` creates a traversal so `Collections.list` can collect it into another `ArrayList`. After collection completes, clearing `modern` sets the source's size to `0`, yet `copyBack` still contains `red` and `blue`.

The example does not mutate the source while the `Enumeration` is still in use. It demonstrates the structural independence of the collected `List`, not that every `Enumeration` is a fixed snapshot of its source.

### 12.2. The Adapter Only Changes the Read Interface

`Enumeration<Integer>` provides two numbers, `10` and `20`. The `Iterator<Number>` returned by `adapt` retrieves `10` via `next`; `remove` is rejected; `forEachRemaining` continues with `20`. `hasNext` afterward is `false`.

The `remove` call is placed right after `next` and before `forEachRemaining` specifically to test the case where the adapter does not support removal. Do not use this example as a pattern for calling `remove` after `forEachRemaining` has run: the `Iterator` contract leaves `remove` behavior unspecified in that situation.

### 12.3. The Resulting Empty List Can Still Accept New Elements

`Collections.emptyEnumeration` provides an empty `Enumeration`. `Collections.list` on it returns a mutable empty `ArrayList`. Adding `later` to the list yields `[later]`; this operation does not put data into the `Enumeration`.

An empty source, a `null` source, and an exhausted source are three distinct cases to separate. Both cases with a valid `Enumeration` can produce an empty `List`; a `null` reference must be handled as an input error or according to an explicit program policy.

This program was compiled and run at the Java 17 API level as shown in the commands above. The same source code also compiled successfully with `--release 8`; it does not use `asIterator`.

## 13. When Source Data Changes During Traversal

### 13.1. Enumeration Has No General Fail-Fast Guarantee

Do not assume every `Enumeration` will throw `ConcurrentModificationException` if the source changes. The `Enumeration` interface does not mandate a modification-detection policy across all implementations.

Specifically, [Vector — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html) states that the `Enumeration` returned by `Vector` is not fail-fast. If the `Vector` is structurally modified after the `Enumeration` is created, the results of the enumeration are undefined under that contract.

Therefore, do not take a single run that happens to print a few elements as proof that adding/removing on a `Vector` while reading an `Enumeration` is safe. All complete programs above keep the source structure stable during each active traversal.

### 13.2. Wrapping as Iterator Adds No Concurrency Guarantees

`asIterator` does not transform the source's policy into a thread-safe one. An `Iterator` created from an `Enumeration` also does not gain modification-detection mechanisms like those provided by another collection's native `Iterator`.

Similarly, `Collections.list` only collects data via read operations. If you need a consistent snapshot when multiple places can modify the source, you must coordinate reads and writes according to the source's synchronization contract. Calling a conversion method does not replace that coordination.

The fact that `Vector` synchronizes individual operations does not mean the sequence of checking for remaining elements and retrieving the next element becomes an atomic transaction. Do not use `Vector`'s presence as an excuse to skip concurrent access design.

### 13.3. A List Copy Is Not an Immutability Guarantee

Once collected under valid source conditions, the new `List` has its own backing structure. It is still a mutable `ArrayList` and may still share mutable element objects.

If the requirement is "re-read the same set of references multiple times," a `List` copy is usually appropriate. If the requirement is "every object's state must remain unchanged," you also need an immutable design or per-element copying; `Collections.list` does not solve that requirement.

## 14. Common Pitfalls

| Misconception or Practice | Problem | How to Handle |
|---|---|---|
| Treating `Enumeration` like a data store with `size`/`index` | The interface only provides a sequential read pass | Collect into a `List` if positional operations are needed |
| Using `null` as an end marker | `null` can be a valid element | Check `hasMoreElements` |
| Calling `nextElement` twice in one loop for one element | Two calls consume two elements | Retrieve once, store in a variable, then use it |
| Expecting `asIterator` to replay already-read elements | The adapter continues from the remaining elements | Create a fresh pass from the source or save data earlier |
| Using the original `Enumeration` directly after `asIterator` | The API leaves traversal behavior undefined for that usage | Continue traversing through the `Iterator` |
| Casting `Enumeration` to `List` | Casting does not collect data | Use `Collections.list` |
| Calling `Collections.list` twice on the same exhausted pass | The second call has no old data left to re-read | Keep the first `List` or request a fresh pass |
| Assuming the default adapter supports `remove` because the source is mutable | `Enumeration` has no removal operation to forward | Use a removal API that is genuinely supported |
| Treating the new `ArrayList` as a deep copy | Elements may still share the same references | Design copying per element type if needed |
| Expecting converting to `Iterator` to detect all source mutations | The wrapper adds no such contract | Follow the source's concurrency/modification policy |
| Choosing full collection without considering source size | Retains references to all remaining elements | Choose sequential traversal if only one pass is needed |
| Calling `asIterator` in code that must compile on Java 8 | The method was introduced in Java 9 | Use a compatible adapter or raise the Java target |

## 15. Self-Check

1. **How does `Enumeration` differ from `enum`?** `Enumeration` is an interface for sequentially traversing elements; `enum` is a language mechanism for declaring a constant set type.
2. **A source has `A, B, C`, and `nextElement` was called to retrieve `A`. What does `Collections.list` receive?** `B, C` in that order, assuming the source stays stable and the traversal has those exact two elements remaining.
3. **Does collecting into a `List` empty the source `Vector`?** No. It consumes the traversal pass, not the source data.
4. **After `asIterator`, should you continue calling `hasMoreElements` on the original `Enumeration`?** No. The `Enumeration` API leaves traversal results undefined if you continue calling methods directly on the `Enumeration` after adapting it.
5. **Does `asIterator` provide two independent passes if you keep both variables?** There is no such guarantee. Use the `Iterator` to continue the remaining elements; if you need separate passes, collect into a `List` and obtain `Iterator`s from the `List`.
6. **What type of object does `Collections.list` create?** A new `ArrayList`, which can be assigned to a `List` variable; elements are held by reference rather than deep-copied.
7. **Does a source yielding `x, null, y` cause collection to stop at `null`?** No. When `null` is a valid element, all three positions are placed into the `ArrayList`.
8. **Why can the manual adapter return `Iterator<Number>` from `Enumeration<Integer>`?** The source only needs to supply objects that are `Number`s; `Integer` satisfies that relationship. A broader reference type does not change the underlying object's runtime type.
9. **Can you rely on `ConcurrentModificationException` to detect all `Vector` mutations while reading an `Enumeration`?** No. `Vector`'s `Enumeration` is not fail-fast; structural modification under conditions the API warns against can yield undefined results.
10. **Can Java 8 call `Enumeration.asIterator`?** No. `asIterator` was added in Java 9; you can use a manual adapter when Java 8 compatibility is required.

## 16. Practice Exercises

### 16.1. Preserving Order and Duplicates of Remaining Elements

Create a `Vector<Integer>` containing `4, 4, 8`; retrieve the first element using `nextElement`, then collect the remaining elements using `Collections.list`.

Results to verify: the read element is `4`, the resulting `List` is `[4, 8]`, and the source `Vector` is still `[4, 4, 8]`. Changing the first element of the resulting `List` to `40` only makes the `List` `[40, 8]` without modifying the source `Vector`.

Then collect again from the exact same old `Enumeration`. The result should be empty. Explain why a fresh `Enumeration` from the `Vector` can still read all elements.

### 16.2. Choosing a Single Read Path After Adaptation

Create a `Vector<String>` containing `X, Y, Z`; read `X` via `Enumeration`, then call `asIterator`. Use only the `Iterator` for the remaining elements.

Results to verify: the `Iterator` reads `Y` and `Z`, and `hasNext` is `false` afterward. Do not add direct calls to the `Enumeration` after creating the adapter. Explain why "holding two variables" does not mean "having two independent passes."

### 16.3. Choosing a Conversion Based on Caller Requirements

One method receives an `Enumeration<String>` and only needs to print each name once. Another method needs to inspect the name at index `0` and traverse the data twice.

For the first method, you can traverse directly or adapt to an `Iterator` without collecting everything into a `List`. For the second method, collect into a `List` once from the remaining elements, check for emptiness before accessing index `0`, and then perform the traversal passes on that `List`.

Clearly state the condition that the source still has the expected data. If the `Enumeration` was already partially read beforehand, converting to a `List` does not recover the elements already consumed from the traversal.

## 17. References and Verification Scope

- [Enumeration — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html): `hasMoreElements`, `nextElement`, `asIterator`, the Java 9 milestone, and usage constraints on `Enumeration` after adaptation.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `list` returning `ArrayList`, element collection order, `enumeration`, and `emptyEnumeration`.
- [Iterator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): traversal methods, optional `remove`, `forEachRemaining`, and related behavioral limits.
- [Vector — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html): the `Enumeration` source in the examples and warnings when the source is structurally modified.

The four complete programs were compiled with `javac` using `--release 17` and run on JDK 24.0.2, producing the exact stdout recorded in this lesson. The manual adapter program also compiled successfully with `--release 8`. Snippets marked as illustrative must be placed in a context with the corresponding variables and imports already defined; they are not presented as standalone runnable files.
