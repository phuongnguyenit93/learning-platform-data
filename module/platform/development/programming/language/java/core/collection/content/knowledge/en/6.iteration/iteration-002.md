# Iterator: hasNext, next, and forEachRemaining

`Iterator<E>` is an object that holds the state of **a single traversal pass** over elements of type `E`. It allows data-consuming code to retrieve elements one by one without needing to know whether the source is stored in an array, a linked list, a set, or generated in some other way.

Three core methods:

| Method | Question or Operation |
| --- | --- |
| `boolean hasNext()` | Are there any more elements to retrieve? |
| `E next()` | Retrieve the next element and advance the traversal state. |
| `void forEachRemaining(Consumer<? super E> action)` | Apply an action to the entire remaining portion of the traversal pass. |

An iterator is not a copy of the collection and does not automatically restart once exhausted. It is important to understand traversal state before choosing between a manual loop and `forEachRemaining`.

## 1. Iterable Provides a Traversal Pass, Iterator Holds Its State

Given a list:

~~~java
// Code snippet inside a method; requires importing java.util.List and java.util.Iterator.
List<String> values = List.of("A", "B", "C");
Iterator<String> iterator = values.iterator();
~~~

There are two objects with two distinct roles:

- `values` is the list that stores or provides data according to the `List` contract.
- `iterator` is the traversal cursor that keeps track of the next retrieval for this traversal pass.

`Iterable<E>` is the contract that provides `iterator()`. `Collection<E>`, `List<E>`, and `Set<E>` are examples of types that can be traversed in this way.

`Iterator<E>` belongs to the `java.util` package, not `java.lang`. Creating an iterator from a list does not automatically create a new list.

### Visualizing the Next Element Position

With the list A, B, C:

~~~text
Newly created:
next part -> A, B, C

After next() returns A:
passed: A
next part -> B, C

After next() returns B:
passed: A, B
next part -> C

After next() returns C:
passed: A, B, C
remaining part: empty
~~~

This is a mental model for reading code. Not every iterator class uses an internal index variable. For a linked list, the traversal structure may rely on nodes; for other sources, the state representation may be different still.

## 2. hasNext: Asks Whether Elements Remain, Does Not Retrieve Them

~~~java
Iterator<String> iterator = List.of("A", "B").iterator();

System.out.println(iterator.hasNext()); // true
System.out.println(iterator.hasNext()); // true
System.out.println(iterator.next());    // A
~~~

During a normal traversal of an unmodified source, calling `hasNext()` repeatedly does not skip A. The method asks whether `next()` can still return an element, rather than retrieving that element for the caller.

Do not call `hasNext()` expecting to receive the next element itself. The return value is `boolean`, not `E`.

### hasNext Is Not a Waiting Mechanism

For a regular collection iterator, `hasNext()` does not mean "wait until new data arrives." Nor does it create a synchronization guarantee that another thread cannot modify the source after the check.

Do not assume that every iterator has the same `hasNext()` cost. A computed or lazily read source might have to prepare data internally. The meaning to the caller is still asking whether an element remains, not a guarantee that every implementation merely reads a field with fixed cost.

### A Loop That Does Not Advance Does Not Terminate

~~~java
// Logically incorrect example: if the iterator currently has elements, the state never advances.
while (iterator.hasNext()) {
    System.out.println("still has data");
}
~~~

The condition does not consume data on its own. A traversal loop needs to call `next()` or an appropriate consuming operation to make progress.

## 3. next: Retrieves One Element and Advances One Step

Common pattern:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
}
~~~

Each iteration:

1. Checks whether an element remains.
2. Retrieves exactly one element.
3. Processes the retrieved value.

It is not mandatory to call `hasNext()` immediately before every `next()`. If the code has a solid guarantee that an element remains, it may call `next()` directly. However, the responsibility for handling the case where no data remains still rests with the caller.

When exhausted, `next()` throws `NoSuchElementException`; it does not return `null` as an end-of-iteration marker. The exception contracts and remaining details are described in the [Java SE 17 Iterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

### Do Not Confuse Retrieving an Element with Removing It from the Source

~~~java
List<String> values = List.of("A", "B");
Iterator<String> iterator = values.iterator();

String first = iterator.next();

System.out.println(first);  // A
System.out.println(values); // [A, B]
~~~

`next()` has passed A in the traversal pass, but it has not removed A from the list.

In this article, "consuming the traversal" refers to the iterator's state. It does not mean elements are removed one by one from the source collection.

### Calling next Twice Advances Two Steps

~~~java
// Common mistake when intending to process each element exactly once.
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    process(iterator.next());
}
~~~

`process` here is the name of an illustrative application method, not a built-in API. The snippet retrieves one element to print and then retrieves another element to process. It can skip elements relative to the original intent, and the second `next()` call may encounter the end of the data.

Retrieve once and reuse the variable:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
    process(value);
}
~~~

The snippets with `process` only illustrate structure inside a method, not standalone programs.

## 4. Null Can Be Data, Not an Exhaustion Signal

If the source permits `null` elements, an iterator can return `null` as a valid element:

~~~java
// Requires importing java.util.Arrays.
Iterator<String> iterator = Arrays.asList("X", null, "Y").iterator();

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
~~~

Stdout of this snippet:

~~~text
X
null
Y
~~~

Writing a condition like the following is wrong for a source that may contain `null`:

~~~java
// Do not use null as an Iterator termination signal.
while (iterator.next() != null) {
    // Does not properly express whether elements remain.
}
~~~

It may stop before Y, or throw an exception if it does not encounter `null` before running out of data. Use `hasNext()` to check for completion.

Further distinctions:

- `List.of(...)` does not accept `null` elements.
- `Arrays.asList(...)` can contain `null` elements.
- An iterator does not impose a universal `null` policy across all sources.

The issue lies in the data source and how the return value is used, not in Java using `null` to mark the end of an iterator.

## 5. forEachRemaining: Processes from the Current Position to the End

Example where one element has already been retrieved:

~~~java
Iterator<String> iterator = List.of("A", "B", "C", "D").iterator();

System.out.println(iterator.next()); // A
iterator.forEachRemaining(System.out::println);
~~~

Stdout:

~~~text
A
B
C
D
~~~

The line `A` comes from `next()`. `forEachRemaining` only processes B, C, and D.

If you want to inspect specifically the part processed by the callback:

~~~java
Iterator<String> remainderIterator = List.of("A", "B", "C", "D").iterator();
remainderIterator.next(); // Already retrieved A.
List<String> remaining = new ArrayList<>();
remainderIterator.forEachRemaining(remaining::add);
System.out.println(remaining); // [B, C, D]
~~~

The `remaining` list receives the unretrieved portion from **that iterator**. It does not re-fetch elements that the iterator has already passed.

### Idea Behind the Default Implementation

Its behavior can be understood in terms of a loop:

~~~java
while (iterator.hasNext()) {
    action.accept(iterator.next());
}
~~~

`action` is the passed-in action, not a newly returned result. A concrete implementation may override the method to execute in a way suited to its internal structure, so do not assume every iterator executes the exact same bytecode as the loop above.

What matters is preserving the semantics of processing the remaining elements and the traversal order guaranteed by the source.

### After Normal Completion

For a finite traversal pass over a stable source, when `forEachRemaining` completes normally:

- The remaining elements have been processed.
- `hasNext()` returns `false`.
- Calling `forEachRemaining` again with a valid action has no new elements to process.
- Calling `next()` on the exhausted traversal pass throws `NoSuchElementException`.

Do not use `forEachRemaining` if you only need to process a bounded portion or if the source may be infinite. It has no built-in business stopping condition beyond running out of data or throwing an exception.

## 6. Consumer: An Action on Elements, Not a Result-Returning Transformation

Signature:

~~~java
void forEachRemaining(Consumer<? super E> action)
~~~

This signature is shown for understanding; you do not redeclare the method in code that uses an iterator.

`Consumer` accepts a value to perform an action and returns no value from its `accept` method. For example:

~~~java
Iterator<String> iterator = List.of("A", "B").iterator();

iterator.forEachRemaining(value -> System.out.println(value));
~~~

An equivalent method reference in this context:

~~~java
iterator.forEachRemaining(System.out::println);
~~~

However, if the two snippets are called back-to-back on the **same iterator**, the second one does not automatically run again from the beginning. Equivalence refers to how the callback is written, not an ability to reuse already traversed data.

### Consumer of a Supertype

Because of `? super E`, an iterator of `String` can accept an action applicable to `Object`:

~~~java
// Requires importing java.util.function.Consumer.
Consumer<Object> print = value -> System.out.println(value);
Iterator<String> iterator = List.of("A", "B").iterator();

iterator.forEachRemaining(print);
~~~

The action can accept every `String` because a `String` is also an `Object`. The reverse direction is not safe: an action that only handles `String` cannot automatically accept every element from an `Iterator<Object>`.

### No Automatic Result List

`forEachRemaining` returns `void`. If you need to build a new list, you must provide a destination to collect into:

~~~java
List<String> result = new ArrayList<>();
iterator.forEachRemaining(value -> result.add(value.toLowerCase()));
~~~

This is a syntax example assuming non-`null` elements. When normalizing strings in a real application, choose the appropriate locale rules and handle missing data as required; not every lowercase conversion carries the same business meaning.

When you only need to accumulate or transform elements, a regular loop can also be clearer. There is no need to use a callback for every task.

## 7. Early Stopping: Loops Have break, Lambda return Does Not Stop Traversal

If you need to stop at B:

~~~java
Iterator<String> iterator = List.of("A", "B", "C", "D").iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    if (value.equals("B")) {
        break;
    }
    System.out.println(value);
}
~~~

A is printed. B was already retrieved before causing the loop to break, so the remaining elements of the iterator are C and D.

If `iterator.forEachRemaining(...)` is called afterward, it starts from C.

### Return Inside a Lambda Only Ends the Current Callback Invocation

~~~java
List<String> accepted = new ArrayList<>();

List.of("A", "B", "C", "D").iterator().forEachRemaining(value -> {
    if (value.equals("B")) {
        return;
    }
    accepted.add(value);
});

System.out.println(accepted); // [A, C, D]
~~~

`return` does not return from the enclosing method, does not terminate `forEachRemaining`, and does not act like a loop `break`. It only ends the callback execution for B. The callback is still invoked subsequently for C and D.

A `break` statement cannot jump from inside a lambda out to an enclosing loop.

You could make the callback throw an exception, but artificial exceptions should not be used as the default choice for normal stopping conditions. When early termination and continued management of traversal state are required, a manual loop expresses the intent more directly.

## 8. Exceptions in the Callback and Work Already Performed

Example where an action fails when encountering B:

~~~java
List<String> completed = new ArrayList<>();
Iterator<String> iterator = List.of("A", "B", "C").iterator();

try {
    iterator.forEachRemaining(value -> {
        if (value.equals("B")) {
            throw new IllegalStateException("stop at B");
        }
        completed.add(value);
    });
} catch (IllegalStateException exception) {
    System.out.println(exception.getMessage());
}

System.out.println(completed); // [A]
~~~

The exception thrown by the callback is propagated to the caller. The action already performed for A is not automatically rolled back. `forEachRemaining` does not create a transaction across the entire data set.

You should not subsequently guess whether the iterator is positioned before B, after B, or at C and continue processing based on that assumption. The general contract does not guarantee the subsequent behavior of an iterator after its callback throws an exception.

If the work requires retry:

- Clearly determine at the business layer which items have succeeded.
- Do not use the iterator's unguaranteed internal position as a checkpoint.
- Design idempotent processing or store identifiers/checkpoints as required.
- Recreate an appropriate read pass when the source allows it.

For small in-memory collection tasks, you can simply choose a manual loop and handle errors explicitly per element, rather than trying to continue using an iterator whose callback just failed.

### Action Must Not Be Null

~~~java
// Snippet illustrating an error on a new iterator.
List.of("A").iterator().forEachRemaining(null);
~~~

The call throws `NullPointerException`. Distinguish `action == null` from a source element being `null`: the former is a missing action, whereas the latter can be valid data if the source permits it.

## 9. Do Not Arbitrarily Modify the Source Inside the Callback to "Traverse and Mutate"

An action like the following does not have general safe semantics:

~~~java
// Example that should not be used with a standard List.
iterator.forEachRemaining(value -> values.remove(value));
~~~

Modifying a collection during traversal must follow the policy of the specific iterator and source. The general contract of `forEachRemaining` does not guarantee behavior if the callback mutates the collection, including calling mutating operations through the iterator, unless a specific implementation defines otherwise.

If the goal is to filter elements, consider an appropriate mechanism such as:

- An explicit iterator loop using `remove()` when the iterator actually supports it.
- `Collection.removeIf(...)` when the collection supports mutation and the condition fits.
- Creating a new result collection without mutating the source being traversed.

`Iterator.remove()` is an optional operation. Not every iterator supports it, and calling it after `forEachRemaining` has no general guarantee as a way to remove the last processed element.

Iterators that detect modification may throw `ConcurrentModificationException`, but do not rely on that exception as a synchronization mechanism or as definitive proof that every invalid modification will be detected.

## 10. One Iterator Serves One Pass; Creating a New Iterator Does Not Copy Data

~~~java
List<String> values = List.of("A", "B");

Iterator<String> first = values.iterator();
Iterator<String> second = values.iterator();

System.out.println(first.next());  // A
System.out.println(first.next());  // B
System.out.println(second.next()); // A
~~~

These two iterators over the list maintain independent traversal states. `second` has not passed any elements even after `first` has reached the end.

However, both read from the same `values` source. They are not two independent copies of the elements or of the collection.

### Assigning Another Variable Does Not Create a New Iterator

~~~java
Iterator<String> first = values.iterator();
Iterator<String> alias = first;

System.out.println(first.next()); // A
System.out.println(alias.next()); // B
~~~

`alias` and `first` reference the same iterator. Calling `next` through one variable changes the state observed through the other.

If two independent passes are needed, create two iterators from a source that supports doing so. Do not assume every `Iterable` source provides an identical snapshot across multiple traversals; with the immutable `List.of` example here, the content across passes is deterministic.

### Pitfall of Recreating the Iterator Inside the Loop

~~~java
// Incorrect example if values is non-empty and unmodified.
while (values.iterator().hasNext()) {
    System.out.println(values.iterator().next());
}
~~~

Each check and call creates a brand-new iterator from the beginning. The loop fails to maintain progress and will print the first element endlessly.

Create the iterator once before the loop:

~~~java
Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
~~~

## 11. Relationship with Enhanced for-each and the Source's forEach

An enhanced for-each loop over an `Iterable` source expresses the corresponding traversal idea:

~~~java
for (String value : values) {
    System.out.println(value);
}
~~~

It can be read as roughly equivalent to:

~~~java
for (Iterator<String> iterator = values.iterator(); iterator.hasNext(); ) {
    String value = iterator.next();
    System.out.println(value);
}
~~~

This explanation applies to `Iterable` sources; enhanced for-each also supports arrays via a separate language mechanism. Arrays do not implement `Iterable` as a result. The rules are specified in [JLS 17, enhanced for statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2).

Differences in usage scope:

| Traversal Style | Starting Point in the List Example | Stopping Control |
| --- | --- | --- |
| For-each over `values` | A fresh traversal pass over the list | Supports `break` and `continue`. |
| `values.forEach(action)` | Processes the list according to the source contract | Callback; no `break` to exit the call. |
| `iterator.forEachRemaining(action)` | Current position of an existing iterator | Callback until exhausted or an exception occurs. |
| `while (iterator.hasNext())` | Current position of an existing iterator | Step-by-step control and early exit via `break`. |

If you have already called `iterator.next()` and then call `values.forEach(...)` on the source list, the source operation does not use the progress of that separate iterator. Conversely, calling `iterator.forEachRemaining(...)` uses its exact current progress.

Choose the style based on the level of control required. If you only need to traverse the entire source, enhanced for-each is usually concise. If you need to split a single pass into multiple stages, stop early, or pass the remainder to a method, an explicit iterator makes more sense.

## 12. Complete Program

Save as **IteratorMethodsDemo.java**. The `Countdown` class illustrates a custom iterator backed by a counter state rather than a collection pre-populated with all elements.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorMethodsDemo {
    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D");
        Iterator<String> iterator = letters.iterator();

        System.out.println("hasNext first = " + iterator.hasNext());
        System.out.println("hasNext again = " + iterator.hasNext());
        System.out.println("next = " + iterator.next());

        List<String> remaining = new ArrayList<>();
        iterator.forEachRemaining(remaining::add);
        System.out.println("Remaining = " + remaining);
        System.out.println("hasNext after drain = " + iterator.hasNext());

        List<String> secondDrain = new ArrayList<>();
        iterator.forEachRemaining(secondDrain::add);
        System.out.println("Second drain = " + secondDrain);

        try {
            iterator.next();
        } catch (NoSuchElementException exception) {
            System.out.println("next when exhausted = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<String> fresh = letters.iterator();
        System.out.println("Fresh iterator next = " + fresh.next());
        System.out.println("Original iterator still exhausted = "
                + !iterator.hasNext());

        Iterator<String> withNull = Arrays.asList("X", null, "Y").iterator();
        List<String> nullData = new ArrayList<>();
        while (withNull.hasNext()) {
            nullData.add(withNull.next());
        }
        System.out.println("Null is data = " + nullData);

        Iterator<String> partial = letters.iterator();
        while (partial.hasNext()) {
            String value = partial.next();
            if (value.equals("B")) {
                break;
            }
        }
        List<String> afterBreak = new ArrayList<>();
        partial.forEachRemaining(afterBreak::add);
        System.out.println("Remaining after break at B = " + afterBreak);

        List<String> accepted = new ArrayList<>();
        letters.iterator().forEachRemaining(value -> {
            if (value.equals("B")) {
                return;
            }
            accepted.add(value);
        });
        System.out.println("Lambda return skips B only = " + accepted);

        List<String> beforeFailure = new ArrayList<>();
        Iterator<String> failing = letters.iterator();
        try {
            failing.forEachRemaining(value -> {
                if (value.equals("B")) {
                    throw new IllegalStateException("stop at B");
                }
                beforeFailure.add(value);
            });
        } catch (IllegalStateException exception) {
            System.out.println("Consumer error = " + exception.getMessage());
        }
        System.out.println("Completed actions before error = " + beforeFailure);
        // Do not use the failing iterator again.

        try {
            letters.iterator().forEachRemaining(null);
        } catch (NullPointerException exception) {
            System.out.println("Null action = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<Integer> countdown = new Countdown(3);
        System.out.println("Countdown next = " + countdown.next());
        List<Integer> tail = new ArrayList<>();
        countdown.forEachRemaining(tail::add);
        System.out.println("Countdown remaining = " + tail);
        System.out.println("Countdown exhausted = " + !countdown.hasNext());
        System.out.println("Source unchanged = " + letters);
    }

    private static final class Countdown implements Iterator<Integer> {
        private int remaining;

        private Countdown(int start) {
            if (start < 0) {
                throw new IllegalArgumentException("start must be non-negative");
            }
            remaining = start;
        }

        @Override
        public boolean hasNext() {
            return remaining > 0;
        }

        @Override
        public Integer next() {
            if (!hasNext()) {
                throw new NoSuchElementException();
            }
            return remaining--;
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 IteratorMethodsDemo.java
java IteratorMethodsDemo
~~~

Stdout:

~~~text
hasNext first = true
hasNext again = true
next = A
Remaining = [B, C, D]
hasNext after drain = false
Second drain = []
next when exhausted = NoSuchElementException
Fresh iterator next = A
Original iterator still exhausted = true
Null is data = [X, null, Y]
Remaining after break at B = [C, D]
Lambda return skips B only = [A, C, D]
Consumer error = stop at B
Completed actions before error = [A]
Null action = NullPointerException
Countdown next = 3
Countdown remaining = [2, 1]
Countdown exhausted = true
Source unchanged = [A, B, C, D]
~~~

### Explanation of Each Result Group

**Two hasNext Calls**

Both return `true`, and `next` still retrieves A. Asking whether data remains does not advance past A.

**Remaining and Second drain**

A was retrieved earlier, so `forEachRemaining` collects B, C, and D. The subsequent drain produces an empty result list because the iterator is already exhausted.

**next When Exhausted**

The program catches `NoSuchElementException` and prints the exception name. Do not use this exception as a routine control-flow mechanism in place of `hasNext`.

**Fresh iterator**

A new iterator from the list starts at A, while the old iterator remains exhausted. Two separate traversal states do not copy or mutate the source list.

**Null is data**

The iterator traverses X, `null`, and Y. Because the loop condition checks `hasNext`, it does not mistakenly stop at the `null` element.

**Break and lambda return**

The loop retrieves B and then breaks, leaving C and D. The lambda only skips adding B, while still adding A, C, and D when their respective callback invocations run.

**Failing Callback**

The action for A completed before the error occurred at B. The program does not reuse the `failing` iterator, avoiding reliance on subsequent behavior not guaranteed by the general contract.

**Countdown**

`next()` retrieves `3`, and then `forEachRemaining` receives `2, 1`. The class only implements `hasNext` and `next`, relying on the default method for the remainder. When no values remain, `next` checks and throws the proper exception rather than returning a dummy value.

**Source unchanged**

Calls that retrieve or traverse elements do not remove the contents of the list. Auxiliary lists are used to collect results, while the source remains A, B, C, D.

## 13. Implementing a Custom Iterator: Minimum Responsibilities

A custom iterator implementation needs a clear state model:

- What the next element is.
- When traversal is exhausted.
- How `hasNext` determines whether elements remain.
- How `next` transitions state and behaves when exhausted.
- Whether the source allows modification during traversal.

The `Countdown` example accepts a non-negative starting number. The `remaining` state both indicates the next value and determines exhaustion when it reaches `0`. The number `0` is not an element in the domain of this sample iterator.

You do not need to override `forEachRemaining` just to make it usable. If you override it for optimization, you must still honor its related contracts, including rejecting a `null` action and preserving order if the iterator guarantees one.

The `Iterator` interface does not provide `reset()`, `previous()`, `size()`, or `close()`. Needs such as backward traversal, knowing the element count, or managing resources require consulting the specific contract and class. For instance, `ListIterator` adds capabilities suited to lists, but not every iterator is a `ListIterator`.

In particular, do not assume that merely holding an `Iterator` fully manages the lifecycle of external resources such as files or connections. Resource contracts must be handled at the level of the API that created the source.

## 14. Testing and Common Mistakes

Basic test cases:

1. Empty source: `hasNext` is `false`; a valid callback is never invoked; `next` throws an exception.
2. Single element: multiple `hasNext` calls before `next` do not lose the element.
3. Multiple elements: retrieving a few elements and then calling `forEachRemaining` processes only the remainder in the guaranteed order.
4. `null` element when permitted by the source: not confused with completion.
5. `null` action: rejected with an exception.
6. Callback throws an error: the error is propagated to the caller; do not write tests that force resuming from an unguaranteed position.
7. Two separate iterators versus two variables pointing to the same iterator: distinguish independent state from shared state.

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling only `hasNext` in a loop | State never advances; potential infinite loop | Retrieve elements with `next` at the right place. |
| Calling `next` twice for a single processing step | Skips elements or hits exhaustion unexpectedly | Store the value in a variable and reuse it. |
| Using `null` as an end marker | Stops prematurely on sources containing `null` | Use `hasNext`. |
| Thinking `next` removes elements from the collection | Confuses traversal state with source data | Distinguish retrieving via an iterator from mutating the source. |
| Thinking `forEachRemaining` restarts from the beginning | Misses already consumed elements or expects wrong results | Account for the current position of that specific iterator. |
| Using `return` inside a lambda to stop the whole pass | Subsequent elements are still processed | Use an explicit loop when `break` is needed. |
| Recreating the iterator each time in the loop condition or body | Fails to maintain progress | Create one iterator per traversal pass. |
| Modifying the collection inside the callback without checking the contract | May cause unguaranteed behavior or exceptions | Choose a mutation mechanism appropriate for the source. |
| Continuing an iterator after a callback exception based on a guessed position | May duplicate, skip, or misprocess data | Design error handling and checkpointing at the appropriate layer. |

## 15. Practice

1. Given a source A, B, C, D, E, call `next` twice and then collect `forEachRemaining` into a new list. Predict and verify the remaining elements.
2. Write a loop that processes at most two elements while preserving the iterator so a later code section can process the remainder.
3. Create a source containing `null` at the beginning, middle, and end. Demonstrate that a loop based on `hasNext` still traverses the exact number of elements.
4. Compare two independent iterators against two variables pointing to the same iterator using interleaved `next` calls.
5. Run a callback that executes `return` on a specific condition and demonstrate that it only skips the current action.
6. Write an iterator that counts upward across a finite range, testing an empty range and calling `next` after exhaustion. Use the default `forEachRemaining` as well.
7. Given the requirement "stop at the element matching a condition," determine whether the matching element has already been consumed from the traversal pass and write a corresponding test for the remainder.

A traversal pass has a progressively advancing state. `hasNext` checks, `next` retrieves one step, and `forEachRemaining` processes the remainder. Keeping these three roles distinct makes early termination, variable reuse, and multi-stage processing much easier to reason about.
