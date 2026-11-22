# Deque and Add, Inspect, and Remove Operations at Both Ends

## 1. Two-Ended Model: first and last

`Deque<E>` is a double-ended queue. It allows adding, inspecting, and retrieving/removing elements at both ends of a sequence.

In this lesson, we always draw it as:

```text
first / head                         last / tail
front end       [A] [B] [C]           back end
```

With that state:

- Adding at the front end places the new element before `A`.
- Adding at the back end places the new element after `C`.
- Inspecting the front end returns `A` while keeping it in the deque.
- Retrieving/removing at the back end returns `C` and removes it from the deque.

`first` and `last` are positions in the current sequence; they do not mean smallest/largest value or oldest/newest in every usage. The choice of which end to add to and which end to remove from defines the processing policy.

`Deque` also does not provide index-based access like `List`. `getFirst()` is not a shorthand for `get(0)` supported by the `Deque` interface; it is a dedicated method for inspecting the front end. [Java 17 Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

One way to create an instance for single-threaded practice:

```java
Deque<String> values = new ArrayDeque<>();
```

The examples use Java 17-compatible APIs and do not store `null` elements.

## 2. Twelve Methods, Viewed by Three Tasks and Two Ends

Each task at each end has two ways to report certain situations where the operation cannot be performed:

| Task | Front end: exception form | Front end: special-value form | Back end: exception form | Back end: special-value form |
| --- | --- | --- | --- | --- |
| Add | `addFirst(e)` | `offerFirst(e)` | `addLast(e)` | `offerLast(e)` |
| Retrieve and remove | `removeFirst()` | `pollFirst()` | `removeLast()` | `pollLast()` |
| Inspect, without removing | `getFirst()` | `peekFirst()` | `getLast()` | `peekLast()` |

Read the method names in two steps:

1. The verb part indicates whether it adds, inspects, or retrieves/removes.
2. `First` or `Last` indicates which end receives the operation.

Then choose how you want to handle empty or full conditions:

| Situation | Exception form | Special-value form |
| --- | --- | --- |
| Cannot add due to capacity limit | `IllegalStateException` from addFirst/addLast | `false` from offerFirst/offerLast |
| Inspect when empty | `NoSuchElementException` from getFirst/getLast | `null` from peekFirst/peekLast |
| Retrieve/remove when empty | `NoSuchElementException` from removeFirst/removeLast | `null` from pollFirst/pollLast |

The pairs do not select different elements when the operation succeeds. They differ in how they report the corresponding failure condition.

"Special-value form" does not mean all errors are swallowed into `false` or `null`. An invalid element can still throw an exception according to the implementation's contract. [Deque Method Summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 3. Adding at Both Ends: addFirst/addLast and offerFirst/offerLast

### 3.1. Effect on Order

Suppose the deque currently contains `[B, C]`:

```text
addFirst("A") → [A, B, C]
addLast("D")  → [A, B, C, D]
```

The new element is placed at the exact specified end. A `Deque` does not automatically sort elements alphabetically or by value.

With `offerFirst` and `offerLast`, the order on a successful insertion is the same:

```java
// Illustrative snippet.
boolean firstAdded = values.offerFirst("A");
boolean lastAdded = values.offerLast("D");
```

If successful, each operation increases the size by `1` and returns `true`.

### 3.2. addFirst/addLast Return void, Not boolean

Signatures:

```java
void addFirst(E value);
void addLast(E value);

boolean offerFirst(E value);
boolean offerLast(E value);
```

These are signature descriptions, not a standalone program.

Because `addFirst` and `addLast` return `void`, do not write:

```java
// Wrong return type, does not compile:
boolean changed = values.addFirst("A");
```

Success of an `addFirst` call is indicated by the call completing normally and the element being added. If you want a flag to handle lack of space as an expected condition, use the corresponding `offer` method.

### 3.3. Whether a Deque Can Be Full Depends on the Implementation

`Deque` supports both capacity-bounded implementations and implementations without such a fixed maximum.

`ArrayDeque` uses a resizable array. The argument in `new ArrayDeque<>(2)` does not set a maximum limit of two elements.

In contrast, a `LinkedBlockingDeque<>(2)` has a bounded capacity of two elements. When it is full, the single-argument `offerFirst` or `offerLast` returns `false`, while `addFirst` or `addLast` throws `IllegalStateException`.

Do not infer "when full" behavior from the interface name without knowing the actual runtime implementation. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

### 3.4. Adding Duplicate Elements Still Adds Them

A deque is not a deduplicating set. With the implementations in this lesson, adding `"A"` twice creates two elements that can be retrieved twice.

`offerFirst("A")` does not mean "add if A is not already present." A `false` return value when full does not mean "A was a duplicate and was rejected."

## 4. Inspecting Both Ends: get and peek Do Not Remove Data

With `[A, B, C]`:

```text
getFirst()  → A
peekFirst() → A

getLast()   → C
peekLast()  → C

deque after inspections: [A, B, C]
size is still 3
```

The difference only appears when the deque is empty:

- `getFirst()`, `getLast()`: throw `NoSuchElementException`.
- `peekFirst()`, `peekLast()`: return `null`.

When the deque contains only `[B]`, both the front end and the back end refer to the same element `B`. There are not two copies. Retrieving/removing the single element from either end makes the entire deque empty.

Inspection methods return a reference to the element; they do not automatically create a deep copy of it. "Without removing" describes the deque operation; it does not make a mutable element object immutable.

If you want to continuously process subsequent elements, calling only `peekFirst` in a loop is not enough: without another mutating operation, it keeps looking at the same front element.

## 5. Retrieving and Removing at Both Ends: remove and poll

### 5.1. Removing from an End Returns the Element at That End

Starting from `[A, B, C]`:

```text
removeFirst() → returns A; remaining [B, C]
pollLast()    → returns C; remaining [B]
removeLast()  → returns B; remaining []
```

On a successful operation, `removeFirst/removeLast/pollFirst/pollLast`:

- Return the retrieved element itself.
- Remove that element from the deque.
- Decrease the size by `1`.

They do not return a `boolean` indicating whether the collection changed, unlike some value-based removal operations.

### 5.2. Choosing How to Handle Empty State

When being empty is a normal part of the processing flow, you can use `poll`:

```java
// Illustrative snippet: values does not contain null elements.
String item = values.pollFirst();
if (item == null) {
    System.out.println("Chưa có phần tử để xử lý");
} else {
    System.out.println("Đã lấy: " + item);
}
```

If the algorithm has a precondition guaranteeing an element must exist and emptiness should be detected via an exception, a `remove` method can express that requirement.

Do not repeatedly catch exceptions as a default way to check whether a deque has elements when the API already provides the appropriate `poll` form.

### 5.3. Be Careful When Unboxing the Return Value

With an empty `Deque<Integer>`:

```java
// May throw NullPointerException due to unboxing null:
int item = numbers.pollFirst();
```

`pollFirst` returns an `Integer` that is `null`; the error occurs when converting it to `int`. To handle the empty state, store the result in an `Integer` and check it before unboxing.

Do not confuse this error with the `NoSuchElementException` that `removeFirst` explicitly throws when empty.

## 6. Complete Program: Tracking Operations at Both Ends

Save the full code in **DequeEndsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEndsDemo {
    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();
        values.addLast("B");
        values.addFirst("A");
        System.out.println("offerLast C: " + values.offerLast("C"));
        System.out.println("initial: " + values);

        System.out.println("getFirst: " + values.getFirst());
        System.out.println("getLast: " + values.getLast());
        System.out.println("peekFirst: " + values.peekFirst());
        System.out.println("peekLast: " + values.peekLast());
        System.out.println("after inspections: " + values);
        System.out.println("size: " + values.size());

        System.out.println("removeFirst: " + values.removeFirst());
        System.out.println("after removeFirst: " + values);
        System.out.println("pollLast: " + values.pollLast());
        System.out.println("one element: " + values);
        System.out.println("one-element first: " + values.peekFirst());
        System.out.println("one-element last: " + values.peekLast());
        System.out.println("removeLast: " + values.removeLast());
        System.out.println("empty: " + values.isEmpty());

        System.out.println("empty peekFirst: " + values.peekFirst());
        System.out.println("empty peekLast: " + values.peekLast());
        System.out.println("empty pollFirst: " + values.pollFirst());
        System.out.println("empty pollLast: " + values.pollLast());
        try {
            values.getFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("empty getFirst: NoSuchElementException");
        }
        try {
            values.removeLast();
        } catch (NoSuchElementException ex) {
            System.out.println("empty removeLast: NoSuchElementException");
        }
        try {
            values.offerFirst(null);
        } catch (NullPointerException ex) {
            System.out.println("null offerFirst: NullPointerException");
        }
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 DequeEndsDemo.java
java DequeEndsDemo
```

Stdout:

```text
offerLast C: true
initial: [A, B, C]
getFirst: A
getLast: C
peekFirst: A
peekLast: C
after inspections: [A, B, C]
size: 3
removeFirst: A
after removeFirst: [B, C]
pollLast: C
one element: [B]
one-element first: B
one-element last: B
removeLast: B
empty: true
empty peekFirst: null
empty peekLast: null
empty pollFirst: null
empty pollLast: null
empty getFirst: NoSuchElementException
empty removeLast: NoSuchElementException
null offerFirst: NullPointerException
```

How to read the output:

1. `addLast("B")` followed by `addFirst("A")` clearly establishes each element's position.
2. `offerLast("C")` succeeds and appends `C` at the end.
3. The `get` and `peek` calls do not alter the sequence or its size.
4. Removing from the front retrieves `A`; removing from the back retrieves `C`.
5. When only `B` remains, inspecting either end returns `B`.
6. When empty, the `peek/poll` methods return `null`; the corresponding `get/remove` methods throw `NoSuchElementException`.
7. `ArrayDeque` rejects `null` with an exception even when using `offerFirst`. The `offer` name does not make an invalid element valid.

In the printed deque lines, the front end is on the left and the back end is on the right.

## 7. Using Deque as a Queue: Add at Back, Remove from Front

`Deque` extends `Queue`. The inherited queue methods do not pick ends arbitrarily; they have a clear mapping:

| Queue method on Deque | Corresponding end and operation |
| --- | --- |
| `add(e)` | Add at back like addLast |
| `offer(e)` | Add at back like offerLast |
| `remove()` | Retrieve/remove at front like removeFirst |
| `poll()` | Retrieve/remove at front like pollFirst |
| `element()` | Inspect front like getFirst |
| `peek()` | Inspect front like peekFirst |

Note the signature difference: `add(e)` returns `boolean`, whereas `addLast(e)` returns `void`. The table describes the end and operation semantics, not that every signature is identical.

Typical FIFO usage:

```java
Deque<String> pending = new ArrayDeque<>();
pending.offerLast("A");
pending.offerLast("B");
pending.offerLast("C");

String first = pending.pollFirst(); // A
```

If all callers using the same deque follow the add-at-back / remove-at-front convention, the element inserted first is retrieved first.

You cannot add at both ends arbitrarily and still assume the sequence reflects a single FIFO history. A consistent usage convention is required. [Deque: Queue Mapping](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 8. Using Deque as a Stack: Add and Remove at the Same End

Stack usage example:

```java
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
stack.push("C");

String top = stack.pop(); // C
```

Methods on `Deque`:

| Method | Equivalent | When empty or out of space |
| --- | --- | --- |
| `push(e)` | `addFirst(e)` | May throw IllegalStateException if it cannot add due to capacity |
| `pop()` | `removeFirst()` | NoSuchElementException if empty |
| `peek()` | `peekFirst()` | null if empty |

After three `push` calls, the sequence viewed from the front is `[C, B, A]`. `pop` retrieves `C`, the most recently pushed element.

In both FIFO and stack usage, `Deque`'s `peek()` inspects the front end. It does not automatically switch to inspecting the back end just because the variable is named `stack`.

If you want stack semantics but want to handle emptiness with `null`, you can use `pollFirst` instead of `pop` as needed. Choose the empty-handling behavior explicitly rather than relying on variable naming.

The `Deque` documentation recommends using this interface for stack usage instead of the legacy `Stack` class. [Deque: LIFO Usage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 9. Complete Program: Method Mapping and Bounded Deque

Save the code in **DequePoliciesAndCapacityDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.LinkedBlockingDeque;

public class DequePoliciesAndCapacityDemo {
    public static void main(String[] args) {
        Deque<Integer> fifo = new ArrayDeque<>();
        fifo.offer(10);
        fifo.add(20);
        fifo.offerLast(30);
        System.out.println("queue aliases: " + fifo);
        System.out.println("queue peek: " + fifo.peek());
        System.out.println("queue element: " + fifo.element());
        System.out.println("queue poll: " + fifo.poll());
        System.out.println("queue remove: " + fifo.remove());
        System.out.println("queue remaining: " + fifo);

        Deque<String> stack = new ArrayDeque<>();
        stack.push("A");
        stack.push("B");
        stack.push("C");
        System.out.println("stack, first on left: " + stack);
        System.out.println("stack peek: " + stack.peek());
        System.out.println("stack pop: " + stack.pop());
        System.out.println("stack remaining: " + stack);

        Deque<String> bounded = new LinkedBlockingDeque<>(2);
        System.out.println("bounded offerLast A: " + bounded.offerLast("A"));
        System.out.println("bounded offerFirst B: " + bounded.offerFirst("B"));
        System.out.println("bounded full: " + bounded);
        System.out.println("full offerFirst X: " + bounded.offerFirst("X"));
        System.out.println("full offerLast Y: " + bounded.offerLast("Y"));
        try {
            bounded.addFirst("X");
        } catch (IllegalStateException ex) {
            System.out.println("full addFirst: IllegalStateException");
        }
        try {
            bounded.addLast("Y");
        } catch (IllegalStateException ex) {
            System.out.println("full addLast: IllegalStateException");
        }
        System.out.println("bounded after failures: " + bounded);
        System.out.println("bounded pollFirst: " + bounded.pollFirst());
        System.out.println("offerLast C after removal: " + bounded.offerLast("C"));
        System.out.println("bounded final: " + bounded);

        Deque<String> growing = new ArrayDeque<>(2);
        growing.addLast("A");
        growing.addLast("B");
        growing.addLast("C");
        System.out.println("ArrayDeque with initial hint 2: " + growing);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DequePoliciesAndCapacityDemo.java
java DequePoliciesAndCapacityDemo
```

Stdout:

```text
queue aliases: [10, 20, 30]
queue peek: 10
queue element: 10
queue poll: 10
queue remove: 20
queue remaining: [30]
stack, first on left: [C, B, A]
stack peek: C
stack pop: C
stack remaining: [B, A]
bounded offerLast A: true
bounded offerFirst B: true
bounded full: [B, A]
full offerFirst X: false
full offerLast Y: false
full addFirst: IllegalStateException
full addLast: IllegalStateException
bounded after failures: [B, A]
bounded pollFirst: B
offerLast C after removal: true
bounded final: [A, C]
ArrayDeque with initial hint 2: [A, B, C]
```

How to read each section:

1. `offer`, `add`, and `offerLast` all place elements at the back in the queue section.
2. `peek` and `element` inspect the front; `poll` and `remove()` retrieve from the front.
3. `push` adds at the front, so the stack displays as `[C, B, A]`.
4. `LinkedBlockingDeque<>(2)` is full after two successful additions.
5. Neither end accepts another element via `offer` when full, returning `false`.
6. Both `add` forms throw `IllegalStateException` in the full state.
7. The failed additions do not insert `X` or `Y` into the sequence.
8. After removing `B`, adding `C` at the back succeeds.
9. `new ArrayDeque<>(2)` still accepts three elements, proving that the argument is not a two-element maximum limit.

In the example, `LinkedBlockingDeque` is used in a single thread solely to demonstrate capacity exhaustion. The single-argument `offerFirst(e)` and `offerLast(e)` methods still attempt to insert immediately and do not wait for space just because the class name contains `Blocking`.

`BlockingDeque` has its own blocking or timed methods, such as `putFirst`, `putLast`, `takeFirst`, `takeLast`, and their corresponding overloads. Those are additional capabilities and do not change the meaning of the twelve basic methods. [BlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Both standalone programs in this lesson were compiled with `--release 17` and executed to verify the exact stdout. This option checks the language/API level and produces Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 10. Distinguishing End Removal from Value Search and Removal

Similar-looking names can express different operations:

| Call | Meaning |
| --- | --- |
| `removeFirst()` | Retrieve/remove the element currently at the front end |
| `removeLast()` | Retrieve/remove the element currently at the back end |
| `removeFirstOccurrence(x)` | Search for the first occurrence of value x from front to back and remove it |
| `removeLastOccurrence(x)` | Search for the last occurrence of value x and remove it |
| `remove(x)` with argument | On Deque, removes the first occurrence of x |
| `remove()` without arguments | Retrieve/remove the front end |

Examples on separate copies of the structure all starting from `[A, B, A, C]`:

```text
removeFirst()              → returns A; remaining [B, A, C]
removeFirstOccurrence("B") → returns true; remaining [A, A, C]
removeLastOccurrence("A")  → returns true; remaining [A, B, C]
```

The `Occurrence` methods are not restricted to removing only at the front or back end; they search for a value in the sequence. Their return values and performance characteristics can also differ from end-removal operations.

With `Deque<Integer>`, `remove(1)` removes the queried value `1`, not the element at position 1. This interface has no index-based access or removal like `List`. [Deque: Occurrence Operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 11. Iterating, Inspecting, and Draining Are Three Different Tasks

### 11.1. Iterating Does Not Remove Elements

A standard `for-each` loop over a deque iterates from the front end to the back end:

```java
// Illustrative snippet.
for (String value : values) {
    System.out.println(value);
}
```

If you want to iterate in reverse order, `descendingIterator()` provides an iterator from back to front. It does not reverse the stored sequence and does not remove elements.

### 11.2. To Drain All Elements, Use a Retrieve/Remove Operation

With a `null`-free `ArrayDeque<String>`, processing elements one by one from the front:

```java
String value;
while ((value = values.pollFirst()) != null) {
    System.out.println("Đã lấy: " + value);
}
```

This empties the deque once all elements are processed in a single-threaded context with no other producer adding data. Changing it to `pollLast` retrieves from the back end instead.

Merely replacing `pollFirst` with `peekFirst` without another removal operation can cause the loop to encounter the same element endlessly.

### 11.3. Do Not Mutate Structure Arbitrarily Through Other Means During for-each

With implementations such as `ArrayDeque`, iterating with an iterator while directly calling end-addition or end-removal methods can violate iteration rules. The fail-fast mechanism may detect this and throw `ConcurrentModificationException`, but you should not use the presence or absence of an exception as proof of correctness.

If the goal is to consume the sequence, a `poll` loop usually expresses the intent more clearly. If the goal is to remove elements while iterating, use the mechanism supported by the iterator and follow its contract. [ArrayDeque: Iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

## 12. Choosing the Right Usage Pattern and Implementation

A few practical scenarios:

| Requirement | Operation choice |
| --- | --- |
| Add a new task to the back of a waiting list | offerLast or addLast depending on full-capacity policy |
| Insert an element at the front per application rules | offerFirst or addFirst |
| Inspect the next task without removing it | peekFirst or getFirst |
| Retrieve the next task from the front | pollFirst or removeFirst |
| Retrieve the most recent element placed at the back | pollLast or removeLast |
| Use as a stack with top at the front | push, pop, peek, or appropriate First forms |

For single-threaded and typical deque usage, `ArrayDeque` provides both-end operations in amortized constant time for most related operations, as described by the class documentation. That does not mean every method of every `Deque`, such as searching for a value inside, is O(1).

If you need bounded capacity or cross-thread waiting, you must choose the corresponding implementation and methods. `ArrayDeque` is not synchronized for concurrent modification by multiple threads. Conversely, using a concurrent implementation does not turn a sequence of separate calls into an atomic algorithmic operation.

For example, "peek then poll" is two separate calls, not a single command that both checks and claims ownership of an element. Choosing a direct retrieval operation and handling its result usually describes the intended work more clearly.

Do not infer from data being in a deque that it is sorted, deduplicated, or prioritized automatically. Those properties require a separate model or rule.

## 13. Common Mistakes

| Misconception or code pattern | Problem | Fix |
| --- | --- | --- |
| Confusing First/Last with smallest/largest | They are end positions, not value ordering | Draw the sequence with first on the left and last on the right |
| Assigning addFirst to a boolean | The method returns void | Use offerFirst if a flag is needed |
| Calling get and expecting the element to disappear | get only inspects | Use remove or poll to retrieve/remove |
| Using peek in a loop without removing | May inspect the same element forever | Use poll when consuming |
| Thinking poll and remove target different ends | Same corresponding end; different empty handling | Separate end selection from error-reporting choice |
| Thinking offer never throws an exception | Invalid elements can still cause errors | Distinguish lack of space from data-domain violations |
| Thinking ArrayDeque(2) holds at most two elements | Confusing initial capacity hint with maximum limit | Read the implementation contract |
| Calling peek() to inspect the back end | Deque's peek inspects the front end | Use peekLast |
| Thinking push adds at the back | push corresponds to addFirst | Identify where the stack top is |
| Confusing removeFirst with removeFirstOccurrence | One removes the front end, the other searches by value | Read the full name and signature |
| Assigning Integer poll to int when it may be empty | Auto-unboxing null | Check Integer first |
| Using null as data while also using null as empty marker | Results become ambiguous, and some classes reject null | Keep the element domain non-null when appropriate |

To self-check a line of code, answer three questions: which end is being acted upon, does it modify the sequence, and when it cannot be performed will you get an exception or a special value?

## 14. Self-Practice and Verification

### Exercise 1: Trace the Sequence After Each Operation

Start with an empty deque:

```java
values.addLast("B");
values.addFirst("A");
values.offerLast("C");
values.offerFirst("X");
values.peekLast();
values.pollFirst();
values.removeLast();
```

Verification:

| Step | Return value to note | Sequence after step |
| --- | --- | --- |
| addLast B | void | `[B]` |
| addFirst A | void | `[A, B]` |
| offerLast C | true | `[A, B, C]` |
| offerFirst X | true | `[X, A, B, C]` |
| peekLast | C | `[X, A, B, C]` |
| pollFirst | X | `[A, B, C]` |
| removeLast | C | `[A, B]` |

### Exercise 2: Single Element and Empty

The deque contains only `[7]`. Predict the results:

```text
peekFirst() → 7
peekLast()  → 7
pollLast()  → 7; deque is empty
pollFirst() → null
getLast()   → NoSuchElementException
```

Explain why inspecting both ends does not mean there are two `7` elements.

### Exercise 3: Choose by Scenario

1. Want to try adding at the front and handle full capacity with a boolean branch: `offerFirst`.
2. Want to inspect the back end where emptiness is a normal state: `peekLast`.
3. Want to retrieve from the front where emptiness is an error to detect via exception: `removeFirst`.
4. Want to retrieve from the back and receive a marker for no result when empty: `pollLast`.

### Exercise 4: Distinguish FIFO and Stack

Insert A, B, C at the back and retrieve from the front: A, B, C.

Insert A, B, C with push and retrieve with pop: C, B, A.

The same `ArrayDeque` type can serve both usages. The chosen ends determine the policy.

### Exercise 5: Capacity Limit

A `LinkedBlockingDeque<String>` with capacity 2 currently contains `[A, B]`.

- `offerLast("C")`: false, sequence unchanged.
- `addFirst("C")`: IllegalStateException, C is not added to the sequence.
- `pollLast()`: returns B, remaining `[A]`.
- `offerFirst("C")`: true, becomes `[C, A]`.

Do not switch to a blocking/waiting method if the requirement is only to attempt immediate insertion and handle the result.

## 15. Reference Documentation

- [Java 17 Deque — both-end operations and Queue/stack mappings](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)
- [Java 17 ArrayDeque — growable capacity, null handling, and iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)
- [Java 17 LinkedBlockingDeque — capacity bounds and both-end methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)
- [Java 17 BlockingDeque — distinguishing immediate attempts from waiting operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)
