# Removing First or Last Occurrences and Reverse Iteration

## 1. The Problem: Duplicate Values at Different Positions

In a double-ended queue (`Deque`), the same value can appear multiple times. Suppose a list of task codes is ordered from front to back as follows:

```text
first / head                             last / tail
     A       B       A       C       A       D
```

A request to "remove A" still leaves a decision unanswered: should it remove the A closest to the front, the A closest to the back, or every A? If the program needs to inspect tasks starting from the back, it must reverse the reading direction without necessarily being allowed to pull them out of the deque.

This lesson focuses on three tools:

- `removeFirstOccurrence(value)`: removes the single matching occurrence closest to the front.
- `removeLastOccurrence(value)`: removes the single matching occurrence closest to the back.
- `descendingIterator()`: iterates from back to front, optionally combined with removing the element just visited when the iterator supports that operation.

The goal is to know how to pick the right element by **value and current position**, how to read in reverse while preserving the data, and how to remove elements during iteration without violating the iterator's rules.

The examples use APIs available in Java 17. `ArrayDeque` is the primary implementation class; one separate example uses `LinkedList` to explain the `null` case. No Spring Boot, external libraries, or server environment are required.

## 2. What Do "First", "Last", and "Occurrence" Mean?

### 2.1. First and Last Are Positions in the Deque at Call Time

The convention in this lesson is to write a deque in the `first → last` direction, corresponding to the order of a standard iterator. Given:

```text
[A, B, A, C, A, D]
```

the first element is the A on the left; the last element is D on the right. The "first A" is the first matching A encountered when moving from left to right. The "last A" is the last matching A in that same order, which is also the first A encountered when moving from right to left.

We can temporarily label the three A's to track them:

```text
[A₁, B, A₂, C, A₃, D]
```

The subscripts here are merely visual labels for position; all three elements still hold the value `"A"`. Removing the first occurrence removes A₁; removing the last occurrence removes A₃.

Do not infer that "first" means created earliest or "last" means created latest. If the program inserts a new element using `addFirst`, the new element sits ahead of older elements. Any relationship with time holds only if the application's insertion pattern preserves it.

### 2.2. Searching by Value Differs from Removing at an End

Given `[A, B, A, C, A, D]`:

| Call | Return Value | Deque After Call |
| --- | --- | --- |
| `removeLastOccurrence("A")` | `true` | `[A, B, A, C, D]` |
| `removeLast()` | `"D"` | `[A, B, A, C, A]` |
| `removeFirstOccurrence("C")` | `true` | `[A, B, A, A, D]` |

Each row above starts from its own fresh copy of the initial data. The occurrence methods search by value, so they can remove an element from the middle of the deque. `removeLast()` takes no target value; it removes whichever element is currently at the end.

Do not "search manually" for the last A by calling `pollLast()` repeatedly and discarding other values. That approach also removes D, C, or other non-target elements from the deque, mutating far more than intended.

## 3. The Two Occurrence-Removal Methods

Abbreviated signatures:

```java
boolean removeFirstOccurrence(Object target);
boolean removeLastOccurrence(Object target);
```

Both methods return whether an element was removed:

| Situation | Result | Data Change |
| --- | --- | --- |
| One or more matching elements exist | `true` | Removes exactly one matching element from the chosen side |
| No matching element exists | `false` | Unchanged |
| Empty deque, searching for a valid value | `false` | Remains empty |
| Only one element and it matches | `true` | Becomes empty |

This is removal by value. `false` does not mean the deque is empty: the deque may contain many other elements and simply lack the target. Conversely, `true` does not mean every copy was removed.

After a removal, the remaining elements preserve their relative order. For example, removing the middle A from `[B, A, C]` yields `[B, C]`; B does not move behind C.

The `Deque` contract defines matching via `Objects.equals(target, element)`; `remove(Object)` is equivalent to removing the first occurrence. See the [Java 17 Deque documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#removeFirstOccurrence(java.lang.Object)).

### 3.1. Choosing the Right Variant of remove

There are three meanings that are easy to confuse:

```java
// Illustrative snippet; deque is an already-created Deque<String>.
String head = deque.remove();                 // retrieves and removes the head element
boolean changed = deque.remove("A");           // removes the A closest to the head
boolean changedAtTail = deque.removeLastOccurrence("A");
```

The no-argument `remove()` returns an element and throws `NoSuchElementException` if empty. `remove("A")` with an argument returns `boolean`, can search into the middle of the deque, and returns `false` if A is not found.

With `Deque<Integer>`, `remove(1)` removes the `Integer` value 1 via `remove(Object)`, not the element at index 1. The `Deque` interface has no `remove(int index)` method.

If the variable is declared as `LinkedList<Integer>` or `List<Integer>`, the visible method set is different: it includes `remove(int)`. Therefore, you must read both the variable's declared type and the parameter list rather than reasoning from the runtime object alone. When the intent is value-based removal in a deque, `removeFirstOccurrence` or `removeLastOccurrence` makes that intent explicit.

### 3.2. One Call Handles Only One Occurrence

Given `[A, B, A]`, a single `removeFirstOccurrence("A")` produces `[B, A]`. If you need to remove all A's, that is a different requirement. You can iterate and remove conditionally; do not misread "occurrence" as "remove every equal element".

Calling an occurrence method in a loop until it returns `false` can remove all matches, but it has to search again on every call. The cost section at the end of this lesson explains why that can do excessive work on large datasets.

## 4. Matching: By Value, Not Necessarily the Same Object

### 4.1. Do Not Use == to Predict Object Removal

Two distinct objects can be equal according to `equals`. In the runnable program later in this lesson, these two values:

```java
Token stored = new Token(7);
Token probe = new Token(7);
```

do not share the same reference, yet they are equal because `Token` is `record Token(int id)`. Passing `probe` as the argument still removes `stored` from the deque.

This outcome depends on how equality is defined for the element type. A regular class does not automatically treat "same ID means equal" just because it has an `id` field. If a class has not defined an appropriate `equals` method, two separately created instances may fail to match even if they print identical fields.

For records with multiple components, default equality checks all components. `record Job(int id, String state)` does not automatically treat two `Job` instances with the same `id` but different `state` as equal. If the business requirement is "remove the last Job with id 7, regardless of state", use the condition `job.id() == 7` during reverse iteration.

### 4.2. An Object Parameter Type Does Not Make Similar Values Equal

Because the methods accept `Object`, some mismatched-type arguments still compile. For example:

```java
Deque<Integer> numbers = new ArrayDeque<>(List.of(10, 1, 20, 1));
boolean a = numbers.removeFirstOccurrence(1L); // Long, does not match Integer 1
boolean b = numbers.remove(1);                // Integer 1, removes first occurrence
```

`a` is `false`, `b` is `true`, leaving `[10, 20, 1]`. Writing the same numeric value is not enough: `Integer.equals(Long)` does not return `true`.

Similarly, searching for `"a"` does not match `"A"` by default. If you need case-insensitive matching or comparison on a single field, use an application-defined condition; do not stretch your expectations of occurrence methods into approximate matching.

### 4.3. hashCode Is Not Used to Pick an Occurrence in a Deque

This removal depends on element order and element equality. Do not assume searching a deque works like looking up a key in a hash table. Having the same `hashCode` does not mean two objects are equal, nor does it determine which copy gets removed.

An object with mutable fields can also change its `equals` result after being added. Decide which current values need to match, or use a stable identifier in your search condition. When the program must distinguish between two tasks with identical payloads submitted separately, give them a distinct submission ID rather than relying on payload equality alone.

## 5. Runnable Program: Removing First, Removing Last, and Value Equality

Save the code as **DequeOccurrenceDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;

public class DequeOccurrenceDemo {
    record Token(int id) {}

    private static Deque<String> sample() {
        return new ArrayDeque<>(List.of("A", "B", "A", "C", "A", "D"));
    }

    public static void main(String[] args) {
        Deque<String> first = sample();
        System.out.println("initial: " + first);
        System.out.println("first A: " + first.removeFirstOccurrence("A"));
        System.out.println("after first A: " + first);

        Deque<String> last = sample();
        System.out.println("last A: " + last.removeLastOccurrence("A"));
        System.out.println("after last A: " + last);
        System.out.println("missing Z: " + last.removeLastOccurrence("Z"));
        System.out.println("after missing Z: " + last);

        Deque<String> alias = sample();
        System.out.println("remove A: " + alias.remove("A"));
        System.out.println("after remove A: " + alias);
        System.out.println("removeLast endpoint: " + alias.removeLast());
        System.out.println("after removeLast: " + alias);

        Deque<String> one = new ArrayDeque<>(List.of("A"));
        System.out.println("single A: " + one.removeLastOccurrence("A"));
        System.out.println("single now: " + one);
        System.out.println("empty first A: " + one.removeFirstOccurrence("A"));

        Token stored = new Token(7);
        Token probe = new Token(7);
        Deque<Token> tokens = new ArrayDeque<>(List.of(stored, new Token(8)));
        System.out.println("same reference: " + (stored == probe));
        System.out.println("equal value: " + stored.equals(probe));
        System.out.println("remove equal token: " + tokens.removeFirstOccurrence(probe));
        System.out.println("tokens left: " + tokens);

        Deque<Integer> numbers = new ArrayDeque<>(List.of(10, 1, 20, 1));
        System.out.println("remove 1L: " + numbers.removeFirstOccurrence(1L));
        System.out.println("remove 1: " + numbers.remove(1));
        System.out.println("numbers left: " + numbers);

        Deque<String> nullable = new LinkedList<>(Arrays.asList(null, "A", null, "B"));
        System.out.println("remove last null: " + nullable.removeLastOccurrence(null));
        System.out.println("nullable left: " + nullable);
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 DequeOccurrenceDemo.java
java DequeOccurrenceDemo
```

Exact stdout:

```text
initial: [A, B, A, C, A, D]
first A: true
after first A: [B, A, C, A, D]
last A: true
after last A: [A, B, A, C, D]
missing Z: false
after missing Z: [A, B, A, C, D]
remove A: true
after remove A: [B, A, C, A, D]
removeLast endpoint: D
after removeLast: [B, A, C, A]
single A: true
single now: []
empty first A: false
same reference: false
equal value: true
remove equal token: true
tokens left: [Token[id=8]]
remove 1L: false
remove 1: true
numbers left: [10, 20, 1]
remove last null: true
nullable left: [null, A, B]
```

What to observe:

- Both `first` and `last` deques are initialized independently. This lets you directly compare the effect of removing the A near the head versus the A near the tail.
- In `last`, D remains at the end after removing the last A. The method found the A preceding D without removing D.
- Searching for Z finds nothing, returns `false`, and leaves the data unchanged.
- `remove("A")` picks the A closest to the head; afterwards, `removeLast()` removes D and returns D itself.
- Removing an element using a record instance with an equal value succeeds even though the two references differ.
- `LinkedList` in the final example can hold `null` and removes the last occurrence of `null`.

The programs in this lesson were compiled with `javac --release 17` and run on OpenJDK 24.0.2. The `--release 17` flag checks language/API usage targeting Java 17 and emits corresponding bytecode; it does not mean the runtime JVM itself became Java 17.

## 6. Tracing Results via State Transitions

A good way to check yourself is to separate three questions: where does the search start, which element matches first in the chosen direction, and what order do the remaining elements keep?

Standalone example:

```text
Initial:                     [X, A, B, A, C]
removeLastOccurrence("A"):   searches from the end: sees C, then sees A
Return value:                true
After call:                  [X, A, B, C]
```

Do not reverse the deque before searching. The search direction alone selects the right A. Likewise, do not use "largest element" to explain the last occurrence: "last" refers to position, not ascending or descending value order.

For a sequence of consecutive operations, each subsequent call must read the updated state:

| Step | Operation | Return | State After Step |
| --- | --- | --- | --- |
| 0 | Initialize | — | `[A, B, A, C, A]` |
| 1 | `removeFirstOccurrence("A")` | `true` | `[B, A, C, A]` |
| 2 | `removeLastOccurrence("A")` | `true` | `[B, A, C]` |
| 3 | `removeLastOccurrence("A")` | `true` | `[B, C]` |
| 4 | `removeFirstOccurrence("A")` | `false` | `[B, C]` |

At step 3, the sole remaining A is simultaneously the first and last occurrence. Step 4 returns `false`, yet the deque still has two elements.

## 7. Reverse Iteration with descendingIterator

### 7.1. Changing the Reading Direction While Preserving Storage Order

`iterator()` goes from `first` to `last`; `descendingIterator()` goes from `last` to `first`. See the [Deque iterator specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#descendingIterator()).

Given `[A, B, A, C]`:

```text
iterator():            A → B → A → C
descendingIterator():  C → A → B → A
deque after read-only: [A, B, A, C]
```

Here, "descending" means reverse order within the deque. It does not sort in descending order. A numeric deque `[3, 1, 4]` is read in reverse as `4, 1, 3`, not `4, 3, 1`.

### 7.2. Basic Loop

The following snippet assumes `deque` already exists and requires importing `java.util.Iterator`:

```java
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
}
```

`hasNext()` checks whether any unread elements remain in this traversal. `next()` returns the next element in the reverse direction and advances the iterator. By themselves, these two calls do not remove elements from the deque.

When no elements remain, `hasNext()` returns `false`; calling `next()` afterwards throws `NoSuchElementException`. This differs from `pollLast()`, which removes the last element and returns `null` when empty.

An exhausted iterator does not rewind to the start for another pass. To iterate from the end again, create a new `descendingIterator()`. Loops generally should not use `null` as a stop sentinel for `next()`: the iterator already provides `hasNext()`, and an implementation that allows `null` may return a legitimate `null` element.

### 7.3. Shorthand for Read-Only Traversal

You can write:

```java
// Illustrative snippet; deque has already been created.
deque.descendingIterator().forEachRemaining(System.out::println);
```

This action only prints the elements. If you need conditional removal and step-by-step control, use an explicit `while` loop with an iterator as shown in the next section.

`descendingIterator()` returns `Iterator<E>`, not `Iterable<E>`. Therefore, you cannot place its result directly on the right-hand side of an enhanced `for` loop:

```java
// Invalid example, does not compile:
for (String value : deque.descendingIterator()) {
    System.out.println(value);
}
```

An enhanced `for` loop directly over `deque` still uses the normal iterator and traverses from head to tail. Renaming the loop variable or the deque variable does not change the traversal direction.

## 8. Removing via Iterator: Removing Exactly the Element Just Read

### 8.1. Iterator.remove Takes No Value

When the iterator supports removal:

```java
// Illustrative snippet; deque is an already-created ArrayDeque<String>.
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("A".equals(value)) {
        iterator.remove();
        break;
    }
}
```

The traversal starts from the back. Upon encountering the first A in reverse order, `iterator.remove()` removes the exact A element just returned by `next()`. The `break` ensures only one element is removed.

Given `[A, B, A, C]`, the iterator reads C and then the A on the right. The result is `[A, B, C]`. When `remove()` is called, C is still the last element of the deque. Thus, "the element most recently returned by the iterator" does not mean "the last element of the deque".

If you only need equality against a single value, `removeLastOccurrence("A")` is shorter than this loop. An iterator is useful when you need richer conditions, need to collect information while reading, or need to select multiple elements.

### 8.2. Valid States for iterator.remove()

Per the [Java 17 Iterator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()), each successful `next()` call allows at most one `remove()` call; removal support is an optional capability of an iterator.

```text
Create iterator
    ↓
next() succeeds
    ↓
may call remove() once, or skip
    ↓
next() succeeds again
    ↓
may call remove() once again
```

For the `ArrayDeque` iterator in this lesson:

| Sequence of Operations | Outcome |
| --- | --- |
| Create iterator → `remove()` | `IllegalStateException` |
| `next()` succeeds → `remove()` | Removes the element just returned |
| `next()` succeeds → `remove()` → `remove()` | Second removal throws `IllegalStateException` |
| `next()` succeeds → `hasNext()` → `remove()` | `hasNext()` does not read a new element; still removes the element from the prior `next()` |
| Empty iterator → `next()` | `NoSuchElementException` |

Other implementations may not support `Iterator.remove()` and may throw `UnsupportedOperationException`. Do not generalize `ArrayDeque` iterator capabilities to every iterator in Java.

## 9. Runnable Program: Reverse Iteration and Removal During Iteration

Save as **DequeReverseDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class DequeReverseDemo {
    private static <E> List<E> reverseValues(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        Iterator<E> iterator = deque.descendingIterator();
        while (iterator.hasNext()) {
            result.add(iterator.next());
        }
        return result;
    }

    public static void main(String[] args) {
        Deque<String> deque = new ArrayDeque<>(List.of("A", "B", "A", "C"));
        System.out.println("forward: " + new ArrayList<>(deque));
        System.out.println("reverse: " + reverseValues(deque));
        System.out.println("after read: " + deque);

        Iterator<String> iterator = deque.descendingIterator();
        while (iterator.hasNext()) {
            String value = iterator.next();
            if ("A".equals(value)) {
                iterator.remove();
                break;
            }
        }
        System.out.println("after reverse remove one A: " + deque);
        System.out.println("reverse now: " + reverseValues(deque));

        Deque<Integer> numbers = new ArrayDeque<>(List.of(1, 2, 3, 4, 5, 6));
        Iterator<Integer> reverse = numbers.descendingIterator();
        while (reverse.hasNext()) {
            if (reverse.next() % 2 == 0) {
                reverse.remove();
            }
        }
        System.out.println("after reverse remove evens: " + numbers);

        Deque<String> empty = new ArrayDeque<>();
        Iterator<String> exhausted = empty.descendingIterator();
        System.out.println("empty hasNext: " + exhausted.hasNext());
        try {
            exhausted.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty next: " + ex.getClass().getSimpleName());
        }

        Iterator<String> state = deque.descendingIterator();
        try {
            state.remove();
        } catch (IllegalStateException ex) {
            System.out.println("remove before next: " + ex.getClass().getSimpleName());
        }
        System.out.println("next before remove: " + state.next());
        state.remove();
        try {
            state.remove();
        } catch (IllegalStateException ex) {
            System.out.println("remove twice: " + ex.getClass().getSimpleName());
        }
        System.out.println("after iterator state checks: " + deque);

        Deque<String> consumed = new ArrayDeque<>(List.of("A", "B", "C"));
        List<String> removed = new ArrayList<>();
        while (!consumed.isEmpty()) {
            removed.add(consumed.pollLast());
        }
        System.out.println("pollLast values: " + removed);
        System.out.println("after pollLast loop: " + consumed);
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 DequeReverseDemo.java
java DequeReverseDemo
```

Exact stdout:

```text
forward: [A, B, A, C]
reverse: [C, A, B, A]
after read: [A, B, A, C]
after reverse remove one A: [A, B, C]
reverse now: [C, B, A]
after reverse remove evens: [1, 3, 5]
empty hasNext: false
empty next: NoSuchElementException
remove before next: IllegalStateException
next before remove: C
remove twice: IllegalStateException
after iterator state checks: [A, B]
pollLast values: [C, B, A]
after pollLast loop: []
```

`reverseValues` builds a `List` so the reading direction's output can be easily printed and compared. It only calls `hasNext()` and `next()`, so the original deque remains intact. Creating a list is a choice for this example, not a requirement for reverse iteration.

The A-removal loop stops after the first match in reverse order. The even-number removal loop has no `break`, because the requirement is to remove all even numbers. Afterward, only the odd numbers `[1, 3, 5]` remain in their original order.

The iterator state check uses a fresh iterator on `[A, B, C]`: calling `remove()` too early throws an error; `next()` returns C; removing C succeeds; calling `remove()` again without a new `next()` throws an error. The final deque is `[A, B]`.

The `pollLast()` loop at the end serves as a contrast: it also produces `C, B, A`, but drains all elements. Two approaches can print the exact same order while leaving the data in completely different states.

## 10. Applying a Condition: Removing the Last Matching Element

### 10.1. When Whole-Object Equality Cannot Express the Requirement

Suppose a deque holds tasks. Each task has an ID and a status. You need to cancel the most recent (closest to tail) task in a waiting state, rather than removing an object equal to a full template object.

The following is a **utility method placed in an application class**, not a standalone program. It requires importing `Deque`, `Iterator`, and `java.util.function.Predicate`:

```java
static <E> boolean removeLastMatching(
        Deque<E> deque, Predicate<? super E> condition) {
    Iterator<E> iterator = deque.descendingIterator();
    while (iterator.hasNext()) {
        E value = iterator.next();
        if (condition.test(value)) {
            iterator.remove();
            return true;
        }
    }
    return false;
}
```

Usage with a deque of strings that contains no `null` elements:

```java
// Illustrative snippet inside a method:
Deque<String> jobs = new ArrayDeque<>(
        List.of("WAIT-1", "RUN-1", "WAIT-2", "DONE-1"));
boolean removed = removeLastMatching(jobs, s -> s.startsWith("WAIT-"));
// removed == true
// jobs now contains [WAIT-1, RUN-1, DONE-1]
```

The check order is DONE-1, then WAIT-2; upon seeing WAIT-2, it removes it and returns immediately. WAIT-1 remains. Removing the early return and continuing to remove would change the behavior to "remove all waiting tasks".

This method assumes the iterator supports removal, the deque is not modified elsewhere during iteration, and the predicate itself does not add or remove elements on the deque. With `ArrayDeque` used in this lesson, iterator removal is supported. The predicate may throw an exception; when handling business errors, you must decide explicitly whether to accept changes made prior to the error. The single-element removal method above only calls `remove()` after the predicate returns `true`.

### 10.2. Pick the Direction by Question, Pick the Removal Count by Stop Condition

| Requirement | Direction and Termination |
| --- | --- |
| Remove one element equal to target, closest to head | `removeFirstOccurrence(target)` |
| Remove one element equal to target, closest to tail | `removeLastOccurrence(target)` |
| Remove one element matching a condition, closest to head | `iterator()`, remove then stop |
| Remove one element matching a condition, closest to tail | `descendingIterator()`, remove then stop |
| Remove all elements matching a condition | Iterate and remove each match; do not stop after one |
| Read only from tail to head | `descendingIterator()`, do not call `remove()` |

The iterator's direction determines which element is encountered first. The stop condition determines whether one or multiple elements are removed. The occurrence methods can only decide based on equality; they do not accept a `Predicate`.

If you need to know the exact removed element rather than just a `boolean` flag, the iterator loop lets you hold onto `value` before removing it and then return or process it per your application's contract. Do not try to coerce the `boolean` result of `removeLastOccurrence` into an element type.

## 11. Three "Reverse Read" Operations with Different Side Effects

### 11.1. Iterate Only

Use `descendingIterator()` to log, check conditions, or find an element near the tail. If you only need to read, there is no need to make a copy and the deque's order is not modified.

### 11.2. Build a List in Reverse Order

The `reverseValues` helper in the program returns a new list. Adding or removing elements in that new list does not add or remove elements in the original deque.

However, it copies element references. If the elements are mutable objects, mutating an object through the new list is still observable through the deque. A "separate list" does not mean the objects inside are deep-copied.

The resulting list also does not track subsequent additions or removals on the deque after the helper returns. If you need a consistent snapshot in a multithreaded program, creating a separate list does not automatically make the read an atomic operation.

### 11.3. Drain Everything from the End

Calling `pollLast()` in a loop until empty is a destructive consumption. Use it only when the requirement allows draining the deque.

```java
// Illustrative snippet: deque is an ArrayDeque<String> owned by the current thread.
while (!deque.isEmpty()) {
    String value = deque.pollLast();
    System.out.println(value);
}
```

Given `[A, B, C]`, this prints C, B, A and leaves the deque empty. If this represents a queue of pending jobs, using this snippet just to "view from newest to oldest" would wipe out the entire queue.

Do not use this empty-check-then-poll loop as a synchronization guarantee across multiple threads. The single-threaded ownership note in the comment is part of the example's assumptions.

## 12. Modifying Data While Iterating

### 12.1. Use the Active Iterator to Remove

An easy mistake to make:

```java
// Incorrect example of modifying while an iterator is active:
Iterator<String> iterator = deque.descendingIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("A".equals(value)) {
        deque.removeLastOccurrence(value);
    }
}
```

There are two distinct issues here.

First, the removal goes through the deque rather than the iterator tracking the traversal. Do not continue relying on that iterator after such an external modification. With `ArrayDeque`, the fail-fast modification check usually throws `ConcurrentModificationException`, but it is not guaranteed to throw on every invalid modification.

Second, `removeLastOccurrence(value)` searches again by value. It does not directly express "remove the exact object the iterator just returned". When equal elements exist, re-searching logic and iterator-position logic can select different occurrences in other loop variants.

The right approach within this example's scope is `iterator.remove()`. Likewise, an enhanced `for` loop has an iterator underneath; calling `deque.remove(...)` inside the loop body does not avoid this problem.

### 12.2. Fail-Fast Exceptions Are Not a Synchronization Mechanism

`ArrayDeque` is not thread-safe for concurrent access without proper synchronization. Fail-fast behavior detects bugs on a best-effort basis; never use "presence or absence of `ConcurrentModificationException`" as proof that a multithreaded program is correct. This class supports `Iterator`'s optional operations, including removal. See the [Java 17 ArrayDeque documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

In a single-threaded application, a simple rule of thumb is: create the iterator, read/remove through that iterator, finish the traversal, and only then perform other modifications. If other tasks or threads can mutate the deque concurrently, choose an implementation and synchronization policy suited to your application design; do not infer their concurrency guarantees from `ArrayDeque` examples.

Do not expect a fixed stdout output for a program that deliberately mutates a deque outside an active iterator to observe an exception. Which step throws the exception is not a stable behavior to memorize.

## 13. null, Wrong Types, and Search Cost

### 13.1. null Support Depends on the Implementation

`ArrayDeque` does not allow inserting `null` elements. `LinkedList` permits `null`; the first runnable example showed removing the last `null` from `[null, A, null, B]` to leave `[null, A, B]`. See the [Java 17 LinkedList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

Do not generalize that every deque must behave identically when searching for or removing `null`. The interface contract allows implementation-specific exceptions for unsupported arguments. Similarly, an `Object` parameter does not mean every deque implementation silently returns `false` for all wrong-type arguments.

When applying a predicate to a deque that may contain `null`, handle it explicitly according to your business logic:

```java
// Illustrative predicate for a deque that may contain null:
value -> value != null && value.startsWith("WAIT-")
```

In the first program, `Arrays.asList(null, "A", null, "B")` was used to initialize the `LinkedList`. Replacing it with `List.of(null, ...)` fails immediately when creating the list, even before the deque is constructed. That is an error in the data-preparation step, not in the occurrence method.

### 13.2. Searching in the Middle Can Traverse Many Elements

With `ArrayDeque`, value-based removals like `removeFirstOccurrence` and `removeLastOccurrence` take linear time in the worst case, with no constant-time guarantee for finding an arbitrary value. Switching direction may hit the target sooner on specific data, but it does not eliminate the case where nearly the entire deque must be scanned.

Simply reading all `n` elements with an iterator requires `n` calls to `next()`. If you only process elements one by one without accumulating results, you do not need to allocate an extra `n`-element list. `reverseValues` allocates a list, so it uses extra memory proportional to the number of returned elements.

Do not assume "one pass with iterator removal is always O(n)". With `ArrayDeque`, removing from the middle via an iterator can require shifting elements. Multiple removals in a single pass can still push total work above linear time. The class documentation lists `iterator.remove()` among linear-time operations; see [ArrayDeque performance characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Calling occurrence methods repeatedly in a loop can also re-scan and shift elements repeatedly, leading to quadratic worst-case cost. If the requirement is to filter a large dataset, consider the appropriate filtering operation for the class in use or build a new result deque in the desired order. Do not swap data structures solely because of a small example; determine your search/removal frequency and measure on representative workloads when performance is an actual requirement.

## 14. Common Mistakes and Self-Diagnosis

| Symptom | Likely Cause | How to Fix Your Reasoning |
| --- | --- | --- |
| Removed D when intending to remove the A near the tail | Used `removeLast()` | Remove by value using `removeLastOccurrence("A")` |
| Another A still remains after the call | Thought occurrence removes all | One call removes at most one element |
| Two objects look alike but fail to match | `equals` rule does not match search criteria | Check the equality model; use a field-based condition when appropriate |
| Searching for 1 fails in an integer deque | Argument is `1L` or another type | Check both target type and element type |
| "Descending" traversal does not produce descending sorted order | Confused reverse order with sorting | Write down the current order and read right to left |
| Wanted to view in reverse, but the deque is empty afterward | Used `pollLast()` in a loop | Read non-destructively with `descendingIterator()` |
| Iterator removal fails immediately | Haven't called `next()` yet | Must successfully read an element first |
| Second consecutive removal fails | Each `next()` allows only one `remove()` | Remove at most once per element read |
| Modifying while iterating fails or gives unpredictable results | Mutated the deque outside the iterator | Use the active iterator or redesign the processing pass |
| Enhanced `for` with `descendingIterator` fails to compile | Result is `Iterator`, not `Iterable` | Use a `while (hasNext())` loop |

One way to verify on paper is to track four separate items: the deque order before the call, the current reading direction, the element most recently returned by the iterator, and the element actually removed. Do not look only at the final printed output, because different approaches can print the same values while mutating the data differently.

## 15. Self-Check Exercises with Solutions

### Exercise 1: A Sequence of Calls on Duplicate Data

Starting with `[A, B, A, C, A]`, execute consecutively:

```java
removeFirstOccurrence("A");
removeLastOccurrence("A");
removeLastOccurrence("Z");
```

What does each call return, and what is the final deque?

**Solution:** The first call returns `true`, leaving `[B, A, C, A]`; the second returns `true`, leaving `[B, A, C]`; the third returns `false`, leaving it unchanged. The final deque is `[B, A, C]`. Z not existing does not mean the deque is empty.

### Exercise 2: The Word "Last" Across Three Operations

The deque is `[A, B, A, C]`. A reverse iterator calls `next()` twice, then `remove()`. Which element is removed?

**Solution:** The two values read are C and then the A on the right. `remove()` removes the A just read; the deque becomes `[A, B, C]`. C remains at the end. Calling `deque.removeLast()` instead would remove C and is a different operation.

### Exercise 3: Reading in Reverse Is Not Sorting

A numeric deque is `[3, 1, 4]`. Iterate only with `descendingIterator()`, then print the deque. What are the two results?

**Solution:** The traversal yields `4, 1, 3`; the deque remains `[3, 1, 4]`. There is no comparison step to sort and no removal step.

### Exercise 4: Single Element and Iterator State

The deque is `[X]`. A reverse iterator calls `hasNext()`, `next()`, `remove()`, and then `hasNext()`. What happens? What if `remove()` is called one more time?

**Solution:** The first check is `true`; `next()` returns X; removal succeeds and leaves the deque empty; the next check is `false`. Calling `remove()` again without a new successful `next()` throws `IllegalStateException` with `ArrayDeque`'s iterator.

### Exercise 5: Removing by a Single Field

There are three records `Job(7, "WAIT")`, `Job(8, "WAIT")`, `Job(7, "DONE")` in that order. You need to remove the last Job with ID 7, regardless of status. Does passing a template `Job(7, "WAIT")` to `removeLastOccurrence` match the intent?

**Solution:** No. Record equality checks both ID and status, so that template matches the first Job and does not match the last Job. Iterating in reverse with the condition `job.id() == 7`, removing via the iterator, and stopping will select the last Job whose status is DONE. If the real requirement is "the last waiting Job with ID 7", the condition must include the status as well.

### Exercise 6: Choosing the Tool by Data Impact

You need to display log entries from most recent to oldest while keeping the log intact. Someone uses a `pollLast()` loop and stores the values in a list. The displayed output looks right; what bug remains?

**Solution:** The original log has been drained of all elements. Use a read-only reverse iterator or a helper that builds a reversed list like `reverseValues`. The UI displaying the right output does not prove the post-operation data state is correct.

## 16. Reference Documentation

- [Java 17 Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): reference for method names, iterator direction, return types, and occurrence semantics.
- [Java 17 Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): `next()`/`remove()` rules and optional removal capability.
- [Java 17 ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html): characteristics of the implementation used in the examples.
- [Java 17 LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html): reference for the example that accepts `null`.

When applying these tools, answer three questions clearly before writing code: are you selecting by value or by condition, do you prioritize the head or the tail, and do you want to read only or actually remove? Those three decisions determine the right tool and help predict the deque's state after the operation.
