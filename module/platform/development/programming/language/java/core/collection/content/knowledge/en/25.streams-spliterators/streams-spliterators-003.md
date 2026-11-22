# Spliterator: tryAdvance, forEachRemaining, and trySplit

## 1. A Traverser That Can Split Its Remaining Work

When reading a list, we may want to take elements one by one, process all remaining elements quickly, or hand off an unprocessed portion to another traverser. `Spliterator<T>` provides three corresponding operations:

| Method | Primary Role | Return Value |
| --- | --- | --- |
| `tryAdvance(action)` | Performs the action on one remaining element, if one exists | `boolean` |
| `forEachRemaining(action)` | Performs the action on the remaining elements of this traverser | `void` |
| `trySplit()` | Attempts to split off an untraversed portion into another Spliterator | New Spliterator or `null` |

A Spliterator is an object for **traversing and partitioning elements of a source**. The source may be a Collection, an array, or another kind of source; the Spliterator itself is not a list holding a copy of all the data. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

Picture an ordered stack of files:

~~~text
[A, B, C, D, E, F]
~~~

A Spliterator is managing the reading of this stack. Reading `A` leaves `B..F` unread. Afterward, a portion of `B..F` can be split off for another traverser. The already-processed file `A` does not reappear in the split portion.

In this article, “remaining” always means the portion that **the Spliterator under discussion is still responsible for traversing**, not the entire source Collection. After a split, the two Spliterators are responsible for two different portions.

The learning goal is to track that state accurately: which part has passed through the action, which part has been transferred to the new traverser, which part still belongs to the old traverser, and when elements are genuinely exhausted.

## 2. Compared to Iterator: Changing How Elements Are Requested and Adding Splitting

An `Iterator` is typically used with the `hasNext` and `next` pair:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    consume(value);
}
~~~

This is an illustrative snippet where `iterator` and `consume` are provided by the application. `hasNext` asks whether an element remains; `next` returns the element and advances the state. [Java SE 17 — Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

With Spliterator, `tryAdvance` combines attempting to retrieve an element with passing it to a `Consumer`:

~~~java
boolean moved = spliterator.tryAdvance(value -> consume(value));
~~~

If an element is available, the action is invoked with that element and the method returns `true`. If not, no element is passed to the action and the method returns `false`.

Spliterator also has `trySplit` to partition the untraversed portion. However, the ability to split does not mean multiple threads must be used. All three methods can be used in a sequential program for learning or for building custom algorithms.

Spliterator also has no `remove` method like Iterator’s optional operation. You should not try to use `tryAdvance` to replace a valid removal mechanism of the underlying source structure.

## 3. tryAdvance: One Successful Call Processes One Element

Signature:

~~~java
boolean tryAdvance(Consumer<? super T> action)
~~~

With an ordered source `A, B, C`, normal calls in sequence mean:

| Call | Element passed to action | Result |
| --- | --- | --- |
| Call 1 | `A` | `true` |
| Call 2 | `B` | `true` |
| Call 3 | `C` | `true` |
| Call 4 | None | `false` |

The call that processes the last element still returns `true`. It does not answer the question “is there another element after this call?”; it answers the question “did this call have an element on which to perform the action?”.

Illustrative example inside a method:

~~~java
List<String> data = new ArrayList<>(List.of("A", "B", "C"));
Spliterator<String> cursor = data.spliterator();
List<String> visited = new ArrayList<>();

boolean first = cursor.tryAdvance(visited::add);
~~~

After the call, `first` is `true` and `visited` is `[A]`. The source `data` is still `[A, B, C]`. Traversal state has advanced, rather than `A` being removed from the list.

The short snippets in this article require appropriate imports; the complete program later includes all imports and run commands.

### 3.1. The Boolean Is Not a Business-Check Result

`action` has type `Consumer` and does not return a filtering decision. If the action checks a condition itself and then does nothing, `tryAdvance` can still return `true` because it retrieved an element.

Illustrative example:

~~~java
boolean moved = cursor.tryAdvance(value -> {
    if (value.startsWith("Z")) {
        System.out.println(value);
    }
});
~~~

Nothing being printed does not prove that `moved` is `false`. The retrieved element may simply not have satisfied the `startsWith` condition.

Likewise, `visited::add` can be adapted as a Consumer even though `List.add` returns a boolean. That boolean does not become the return value of `tryAdvance`.

### 3.2. Taking Elements One by One When Pacing Control Is Needed

`tryAdvance` is useful when the caller needs to stop mid-way, process a bounded count, or coordinate with an external condition. There is no need to drain the entire source in a single call.

If the sole purpose is to process everything remaining, using `forEachRemaining` usually expresses intent more clearly than a loop calling `tryAdvance` with an empty body.

Once a Spliterator has exhausted its work, `tryAdvance` with a valid action returns `false` and does not invoke the action. This speaks only for that traverser; a portion already split off to another Spliterator may still be unread.

## 4. forEachRemaining: Process the Untraversed Portion Without Restarting the Source

Signature:

~~~java
void forEachRemaining(Consumer<? super T> action)
~~~

If `tryAdvance` has already been used to process `A` and `B` in the source `A..F`, a subsequent `forEachRemaining` call processes only `C, D, E, F`.

Example:

~~~java
Spliterator<String> cursor = data.spliterator();
List<String> visited = new ArrayList<>();

cursor.tryAdvance(visited::add);
cursor.tryAdvance(visited::add);
cursor.forEachRemaining(visited::add);
~~~

With `data` as `[A, B, C, D, E, F]`, `visited` ends up as `[A, B, C, D, E, F]`, not `[A, B, A, B, C, D, E, F]`.

The method returns `void`, so there is no boolean result indicating how many elements were processed. If a computed result is needed, the action or surrounding algorithm must collect it appropriately.

By contract, `forEachRemaining` performs the action sequentially in the current thread until all elements are processed or the action throws an exception. If the `ORDERED` characteristic is present, actions occur in the encounter order of that portion of the source. The default implementation repeatedly calls `tryAdvance`, but a concrete implementation may optimize the traversal loop. [Java SE 17 — Spliterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#forEachRemaining(java.util.function.Consumer)).

Two practical consequences:

- Calling `forEachRemaining` again after everything has been processed does not re-traverse the data.
- `forEachRemaining` on a split portion does not automatically process the portion belonging to the other traverser.

The method name says “all remaining” in the sense of all remaining elements of **the target object**, not all elements that ever existed in the source.

## 5. trySplit: Transfer Part of the Traversal Responsibility to a New Traverser

Signature:

~~~java
Spliterator<T> trySplit()
~~~

If a split is possible, the method returns a Spliterator managing a portion of the untraversed elements. After the call, that portion no longer belongs to the scope of the old Spliterator. If it cannot split yet or chooses not to split further, it returns `null`.

What to picture is **partitioning**, not duplicating:

~~~text
before:
cursor -> [A, B, C, D, E, F]

after one split in the example:
prefix -> [A, B, C]
cursor -> [D, E, F]
~~~

The two portions must be disjoint at the level of the elements partitioned by the source. This is not a requirement that **values** be distinct: a source `[X, X, Y]` has two positions holding `X`, and both need to be processed exactly once.

`trySplit` does not accept a Consumer, so it does not itself execute the business action you will pass to `tryAdvance` or `forEachRemaining`. However, you should not infer that it is always a free operation with no allocation or no reading from the underlying structure. An implementation may need to prepare or batch elements to form a split.

### 5.1. For ORDERED Sources, the Returned Portion Is a Prefix

If the Spliterator reports `ORDERED`, the returned portion must be a strict prefix of the untraversed elements. The old Spliterator retains the remainder. This constraint enables algorithms to recombine results in the correct order. [Java SE 17 — Spliterator.trySplit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#trySplit()).

With an ordered source `A..F` and a three-and-three split, to reconstruct the source order you traverse `prefix` first, then `cursor`. If you traverse the trailing part first, each traverser can still respect order within its own portion, but the combined list becomes `[D, E, F, A, B, C]`.

If the source does not have `ORDERED`, do not impose prefix semantics on it according to an unguaranteed business order. Being splittable into parts does not by itself create a sorted order.

### 5.2. The Split Ratio Does Not Have to Be Two Halves

Balanced splitting is often beneficial for parallel processing, but the contract does not require every source to split exactly `50/50`. Tree structures, iterator-based sources, or sources whose size is difficult to determine may use different strategies.

The exact `[B, C]` and `[D, E, F]` results in this article’s program are observations of a specific `ArrayList` source after `A` was already read. Do not treat those numbers as a fixed answer for every Collection type.

## 6. Combining All Three Methods in One Example

Source:

~~~text
[A, B, C, D, E, F]
~~~

First:

~~~java
Spliterator<String> cursor = data.spliterator();
List<String> first = new ArrayList<>();
cursor.tryAdvance(first::add);
~~~

State at this point:

~~~text
processed:  [A]
cursor:     [B, C, D, E, F]
~~~

Next:

~~~java
Spliterator<String> prefix = cursor.trySplit();
~~~

In the `ArrayList` case that was run:

~~~text
processed:  [A]
prefix:     [B, C]
cursor:     [D, E, F]
~~~

Finally:

~~~java
prefix.forEachRemaining(prefixValues::add);
cursor.forEachRemaining(remainingValues::add);
~~~

The two output lists are `[B, C]` and `[D, E, F]`. Combining the processed part, the prefix, and the remaining part yields `A..F` exactly once.

Three points to verify:

1. `A` is not included in the split because it has already passed through the action.
2. Traversing `cursor` does not automatically pull in `prefix`.
3. The source list is not deleted from or sliced into two new lists merely because traversal responsibility was split.

In general code, you must check `prefix != null` before using it. The complete program uses a known source to demonstrate a successful split and includes a guard checking the example’s assumption.

## 7. trySplit Returning null Does Not Mean Data Is Exhausted

A traverser over a single-element array cannot split any further:

~~~java
Spliterator<String> one = Arrays.spliterator(new String[] {"solo"});
Spliterator<String> part = one.trySplit();
~~~

In this example, `part` is `null`. Yet `one.tryAdvance(...)` still processes `solo` and returns `true`.

Two questions must be kept separate:

| Question | Appropriate Check |
| --- | --- |
| Can another portion be split off to hand over? | Call `trySplit` and check whether the result is null |
| Is there an element to process in this call? | Call `tryAdvance` with a valid action |
| Want to process all current remaining work? | Call `forEachRemaining` |

Do not write an algorithm that only processes when `trySplit` is non-`null` and discards the `null` branch. That branch is usually the very work that needs to be traversed directly.

`trySplit` can refuse due to an empty source, structural constraints, execution efficiency, or because traversal has already started in a way that prevents the implementation from splitting further. Therefore, even a source with many remaining elements does not guarantee every Spliterator can always split.

For a finite source, repeated splitting attempts must eventually reach the case where it can no longer split according to the contract. Even so, a practical algorithm should still use an appropriate stopping threshold rather than splitting down to the smallest unit just because it can.

## 8. Recursive In-Order Traversal: Split When Possible, Process When Not

The following helper is for sources with a suitable order:

~~~java
static <T> void drainInOrder(Spliterator<T> source, List<T> output) {
    Spliterator<T> prefix = source.trySplit();
    if (prefix == null) {
        source.forEachRemaining(output::add);
    } else {
        drainInOrder(prefix, output);
        drainInOrder(source, output);
    }
}
~~~

This is a method placed inside a class and requires importing `Spliterator` and `List`. The complete program uses this helper with small `ArrayList` instances.

Flow of reasoning:

1. Try splitting off a leading portion.
2. If there is no split portion, process the current work directly.
3. If there is, process the prefix first.
4. Then process the remaining part of the original object.

Calling the helper as above is still completely sequential. No line of code creates threads or submits tasks to an executor.

The helper serves to illustrate the order-preservation principle. A system processing large data needs to consider recursion depth, number of splits, allocation cost, and size thresholds. Do not treat splitting down to `null` as an optimal performance policy for every source.

For a source without a defined order, the name `drainInOrder` can only mean the order chosen by the algorithm, and cannot promise to restore an original order that the source does not guarantee.

## 9. estimateSize Is Supporting Information, Not a Replacement for Element Checks

`estimateSize()` reports an estimate of the number of elements the traverser may still yield. When unknown, too expensive to compute, or the source is infinite, the value may be `Long.MAX_VALUE`.

`SIZED` and `SUBSIZED` place additional constraints on size, but with conditions related to whether traversal or splitting has already occurred. Never assume every Spliterator always returns an exact count after every operation.

`ArrayList.spliterator()` reports `ORDERED`, `SIZED`, and `SUBSIZED`, and has a late-binding and best-effort concurrent modification detection policy. [Java SE 17 — ArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#spliterator()).

In the article’s test case, after processing `A` and splitting:

~~~text
prefix.estimateSize() = 2
cursor.estimateSize() = 3
~~~

The two values match `[B, C]` and `[D, E, F]` for the implementation that was run. That is useful diagnostic information, not a reason to replace every traversal loop with a loop driven by the estimate.

Avoid the reasoning pattern “estimate greater than zero means elements definitely remain; estimate equal to zero means definitely exhausted” when writing code that accepts an arbitrary Spliterator without checking its characteristic contract and state. `tryAdvance` directly attempts one step; `forEachRemaining` directly requests draining the remainder.

This article uses only the characteristics needed to understand the three operations. Characteristic bits are commitments for algorithms to leverage properly, not arbitrary decorative labels.

## 10. Splitting Work Does Not Automatically Create Thread Safety

One thread can call `trySplit` and pass the returned Spliterator to another thread. This provides the basis for parts of a source to be processed independently.

However, two threads must not concurrently call `tryAdvance` or `trySplit` on **the same Spliterator object** and assume it is safe. The Spliterator contract does not require an object to be safe for that kind of concurrent access.

The appropriate responsibility model is:

~~~text
initial traverser
      |
      | split before handing off
      +--> part 1 --> one worker processes
      |
      +--> part 2 --> another worker processes
~~~

Beyond Spliterator ownership, the processing action must also be suitable. Two different source parts calling `sharedArrayList.add` from two threads can still fail because the shared result collector is not thread-safe.

If global order must be preserved, you must also design how results are combined according to split order. Each part having `ORDERED` does not make completion times across multiple threads line up in order automatically.

This article’s program intentionally traverses everything in one thread, collecting into separate lists or in recursive order. The verified outputs are not evidence of a multithreaded algorithm.

## 11. Null Actions, Exceptions, and Source Modification

### 11.1. A null action Is an Invalid Argument

Both `tryAdvance` and `forEachRemaining` require a valid action. Passing `null` throws `NullPointerException`; do not use it as a way to ask “is data left?” without wanting to process it.

You can use a no-op action if you genuinely want to consume one step while discarding the value:

~~~java
boolean skipped = cursor.tryAdvance(value -> { });
~~~

If it returns `true`, that element has passed through the traversal state and is no longer in the untraversed portion. This is a consuming action, not a non-mutating lookahead operation.

### 11.2. Exceptions From action Propagate Outward

If the action throws an exception on element `B`, the ongoing traversal call stops and the exception is propagated to the caller. Side effects already performed on `A` or on `B` before throwing are not automatically rolled back.

The contract also states that subsequent behavior of the Spliterator is unspecified when the action throws an exception. Therefore, do not write a general algorithm relying on the assumption “catch the error and call again, and it will definitely resume at the element right after B”.

In the demonstration program, the traverser that encountered the error is discarded and not queried or reused further. The `seen-before-failure` list only shows the side effects observed before the error in that example.

### 11.3. Source Modification During Traversal Should Not Be Handled by Guesswork

For mutable sources, you must know the Spliterator’s source-binding and concurrent-modification policies. `ArrayList` has a late-binding and fail-fast Spliterator, though modification detection is only best-effort.

Changes after the traverser has bound to the source can invalidate traversal. Logging with `estimateSize` or calling `trySplit` can also involve the binding point; `tryAdvance` is not the only call that matters.

Do not rely on `ConcurrentModificationException` to prove there was no invalid access. `forEachRemaining` may optimize by checking for modification after a batch rather than after every element. Keep the source stable during demonstrations and choose an appropriate coordination policy if the application needs concurrent updates.

## 12. Primitive Specializations and Bridging to Stream

### 12.1. Spliterator.OfInt Uses an Action Accepting int

With an integer array:

~~~java
Spliterator.OfInt numbers = Arrays.spliterator(new int[] {2, 4, 6});
int[] total = {0};

numbers.tryAdvance((int value) -> total[0] += value);
numbers.forEachRemaining((int value) -> total[0] += value);
~~~

The first call adds `2`, the second call adds `4` and `6`, and the final total is `12`. The lambda specifies the `int` type to select the primitive action overload.

The `OfInt`, `OfLong`, and `OfDouble` specializations have overloads for primitive types. Using the matching primitive action avoids having the traversal mechanism box every value into an object just to pass it to a generic Consumer.

`total` here is a single-cell accumulator used in a sequential example. Do not carry this shared-array update pattern directly into multithreaded code and treat it as an atomic addition.

### 12.2. Stream Can Take Over Remaining Untraversed Work

`StreamSupport.stream(spliterator, false)` creates a sequential Stream from the given Spliterator. It does not require going back to the start of the source. [Java SE 17 — StreamSupport.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html#stream(java.util.Spliterator,boolean)).

If `tryAdvance` has already skipped `A`, a Stream receiving that traverser sees only `B, C, D, E, F`. Wrapping it in a Stream does not reset the traversal state.

Once you hand the traverser to the pipeline, let the pipeline manage that traversal pass. Do not interleave manual calls on the same Spliterator while the Stream is using it. If you need a fresh pass from the start, create a new traverser from the source according to the source’s contract.

## 13. Complete Demonstration Program

Save the following code as **SpliteratorOperationsDemo.java**. The program uses Java 17+, the standard library, and creates no extra threads.

`rejects` verifies the expected exception type. The action failure case only inspects the recorded list and then discards the failed traverser. The recursive helper is used only for the small, ordered sources in the example.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class SpliteratorOperationsDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static <T> void drainInOrder(Spliterator<T> source, List<T> output) {
        Spliterator<T> prefix = source.trySplit();
        if (prefix == null) {
            source.forEachRemaining(output::add);
        } else {
            drainInOrder(prefix, output);
            drainInOrder(source, output);
        }
    }

    public static void main(String[] args) {
        List<String> data = new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));

        Spliterator<String> cursor = data.spliterator();
        List<String> first = new ArrayList<>();
        System.out.println("advance=" + cursor.tryAdvance(first::add));
        System.out.println("first=" + first);
        Spliterator<String> prefix = cursor.trySplit();
        if (prefix == null) {
            throw new AssertionError("Expected ArrayList split");
        }
        System.out.println("split-size=" + prefix.estimateSize());
        System.out.println("remaining-size=" + cursor.estimateSize());
        List<String> prefixValues = new ArrayList<>();
        List<String> remainingValues = new ArrayList<>();
        prefix.forEachRemaining(prefixValues::add);
        cursor.forEachRemaining(remainingValues::add);
        System.out.println("prefix=" + prefixValues);
        System.out.println("remaining=" + remainingValues);
        System.out.println("source=" + data);
        System.out.println("advance-after-end=" + cursor.tryAdvance(first::add));
        System.out.println("first-still=" + first);

        Spliterator<String> mixed = data.spliterator();
        List<String> visited = new ArrayList<>();
        mixed.tryAdvance(visited::add);
        mixed.tryAdvance(visited::add);
        System.out.println("before-bulk=" + visited);
        mixed.forEachRemaining(visited::add);
        System.out.println("after-bulk=" + visited);
        mixed.forEachRemaining(value -> visited.add("unexpected"));
        System.out.println("after-empty-bulk=" + visited);

        Spliterator<String> singleton = Arrays.spliterator(new String[] {"solo"});
        System.out.println("singleton-split-null=" + (singleton.trySplit() == null));
        List<String> soloValues = new ArrayList<>();
        System.out.println("singleton-advance=" + singleton.tryAdvance(soloValues::add));
        System.out.println("singleton-values=" + soloValues);

        List<String> rebuilt = new ArrayList<>();
        drainInOrder(data.spliterator(), rebuilt);
        System.out.println("recursive=" + rebuilt);
        List<String> duplicateValues = new ArrayList<>();
        drainInOrder(new ArrayList<>(List.of("X", "X", "Y")).spliterator(), duplicateValues);
        System.out.println("duplicates=" + duplicateValues);

        Spliterator<String> empty = List.<String>of().spliterator();
        System.out.println("empty-split-null=" + (empty.trySplit() == null));
        System.out.println("empty-advance=" + empty.tryAdvance(value -> {
            throw new AssertionError("No value expected");
        }));

        rejects("null-advance-action", NullPointerException.class,
                () -> data.spliterator().tryAdvance((Consumer<String>) null));
        rejects("null-bulk-action", NullPointerException.class,
                () -> data.spliterator().forEachRemaining((Consumer<String>) null));

        Spliterator<String> failing = data.spliterator();
        List<String> beforeFailure = new ArrayList<>();
        rejects("action-failure", IllegalArgumentException.class,
                () -> failing.forEachRemaining(value -> {
                    beforeFailure.add(value);
                    if (value.equals("B")) {
                        throw new IllegalArgumentException("stop");
                    }
                }));
        System.out.println("seen-before-failure=" + beforeFailure);

        Spliterator.OfInt primitive = Arrays.spliterator(new int[] {2, 4, 6});
        int[] total = {0};
        primitive.tryAdvance((int value) -> total[0] += value);
        System.out.println("primitive-first-total=" + total[0]);
        primitive.forEachRemaining((int value) -> total[0] += value);
        System.out.println("primitive-full-total=" + total[0]);

        Spliterator<String> forStream = data.spliterator();
        forStream.tryAdvance(value -> { });
        List<String> streamRemainder = StreamSupport.stream(forStream, false).toList();
        System.out.println("stream-remainder=" + streamRemainder);
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 SpliteratorOperationsDemo.java
java SpliteratorOperationsDemo
~~~

Exact stdout:

~~~text
advance=true
first=[A]
split-size=2
remaining-size=3
prefix=[B, C]
remaining=[D, E, F]
source=[A, B, C, D, E, F]
advance-after-end=false
first-still=[A]
before-bulk=[A, B]
after-bulk=[A, B, C, D, E, F]
after-empty-bulk=[A, B, C, D, E, F]
singleton-split-null=true
singleton-advance=true
singleton-values=[solo]
recursive=[A, B, C, D, E, F]
duplicates=[X, X, Y]
empty-split-null=true
empty-advance=false
null-advance-action -> NullPointerException
null-bulk-action -> NullPointerException
action-failure -> IllegalArgumentException
seen-before-failure=[A, B]
primitive-first-total=2
primitive-full-total=12
stream-remainder=[B, C, D, E, F]
~~~

The code compiled with `--release 17` and ran on JDK 24.0.2. The compiler flag checks Java 17 language/API level; the run output was verified on the stated JVM, not on a Java 17 JVM run.

Reading the output:

- `advance` and `first` show that one step processed `A`.
- `split-size`, `prefix`, and `remaining` show the split of `B..F` for the `ArrayList` used.
- `source` is unchanged because traversal does not delete from or slice the source Collection.
- `advance-after-end` returns false and `first-still` gains no new elements.
- The `before-bulk` and `after-bulk` lines show that `forEachRemaining` continues from the existing state.
- `singleton-split-null` together with `singleton-advance` proves that not being splittable does not mean elements are exhausted.
- `recursive` preserves order, while `duplicates` preserves both positions holding `X`.
- The `empty` lines do not invoke the action on a non-existent element.
- The `null` cases check the action parameter; `action-failure` checks an exception thrown by the action itself.
- The `primitive` lines demonstrate the `int`-accepting overload.
- `stream-remainder` confirms that the Stream receives only the untraversed portion of the Spliterator.

## 14. Practice With Answers

### Exercise 1 — Meaning of true on the Last Element

A Spliterator has exactly one element left. What does a successful `tryAdvance(action)` call return? What does the next call with a valid action return?

**Answer:** The call processing the last element returns `true` because an element was passed to the action. The next call returns `false` because no elements remained when that call began. The boolean is not a promise that another element still remains after the processed one.

### Exercise 2 — Where Does forEachRemaining Start?

A source `A, B, C, D` has already been processed twice with `tryAdvance`. What will calling `forEachRemaining` process? Does it delete data from the source?

**Answer:** It processes `C` and `D`, in order if the source has `ORDERED`. `A` and `B` do not appear again. Advancing the traversal state does not itself remove elements from the source Collection.

### Exercise 3 — null From trySplit

A traverser returns `null` when `trySplit` is called. Can you conclude that all elements have been processed?

**Answer:** No. `null` only indicates that the call could not split off a new portion. The source may have one element left, may not support splitting, or may refuse for efficiency reasons. Continue processing the current portion with the appropriate traversal operation.

### Exercise 4 — Avoiding Lost Work After a Split

For an `ORDERED` source with `A, B, C, D` remaining, a split returns a prefix `A, B` and the old traverser retains `C, D`. If you only traverse the old traverser, what is missing? How do you combine them in the right order?

**Answer:** The `A, B` portion belonging to `prefix` is missing. Traverse and collect results from both portions; when source order is needed, combine the `prefix` results before the old traverser’s results. The old traverser no longer includes the portion handed off.

### Exercise 5 — Are Equal Values Duplicate Work?

The source is `[X, X, Y]`. After splitting and traversing, the result still contains two `X`s. Did `trySplit` duplicate data?

**Answer:** No. Two different positions can hold equal values. Partitioning must preserve source elements by range, not deduplicate equal values. You should compare against the original occurrence counts rather than inferring duplication from `equals` on values.

### Exercise 6 — Calling Again After action Throws

`forEachRemaining` ran the action on `A`, and on `B` the action threw an exception. Can you write general code that catches the error and continues the traverser assuming it will start at `C`?

**Answer:** No. Subsequent behavior of a Spliterator after an exception from the action is unspecified under the general contract. Side effects before the error are also not rolled back automatically. Design a dedicated error-handling strategy or recreate an appropriate traversal pass instead of assuming a resume position.

### Exercise 7 — Splitting and Using Multiple Threads

After `trySplit`, can two threads operate concurrently on one of the two Spliterator objects to “speed it up further”? Is sharing a single output `ArrayList` automatically safe?

**Answer:** There is no safety guarantee when multiple threads operate concurrently on the same Spliterator. Ownership of each traverser must be assigned to one worker at a time. The result collector must also be designed appropriately; splitting the source does not make a shared `ArrayList` thread-safe.

### Exercise 8 — Does Wrapping in a Stream Rewind to the Start?

A Spliterator of `[A, B, C]` has already processed `A`. Then you create `StreamSupport.stream(s, false)` and collect a list. Does the Stream get `A` back?

**Answer:** No, it receives the untraversed state of `s`, so it sees only `B, C` in this example. To read from the beginning again, you need a new traverser from a suitable source, not merely a Stream wrapper around an already-advanced traverser.

## 15. How to Track the Three Operations Properly

Before each call, identify which portion of work currently belongs to which Spliterator. `tryAdvance` passes one element to an action; `forEachRemaining` drains that traverser’s remaining work; `trySplit` transfers part of the untraversed responsibility to another traverser or reports that it cannot split.

When order matters, check whether the source has `ORDERED` and keep the prefix-before-remainder rule. When multiple threads are involved, separate traverser ownership and design the result destination as well. When encountering an action error or a modified source, return to the source contract instead of guessing the cursor position.

Keeping the model of processed portion, handed-off portion, and remaining portion lets you use Spliterator correctly without confusing splitting with copying data, without discarding the `null` branch of `trySplit`, and without accidentally re-reading or dropping work.
