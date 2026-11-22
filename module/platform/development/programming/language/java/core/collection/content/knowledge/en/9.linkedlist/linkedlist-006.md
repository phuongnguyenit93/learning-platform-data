# LinkedList: Double-Ended Operations and Null Policy

`LinkedList` is both a `List` and an implementation of `Deque` — a double-ended queue. You can add, inspect, or retrieve/remove elements at the head and tail without looking up nodes by index.

The key choices to make explicitly are **which end**, **whether to remove the element**, and **whether to return a special value or throw an exception when empty**. With `LinkedList`, there is an additional error-prone factor: the structure allows storing `null`, while many methods also use `null` to signal the absence of an element.

This article uses Java 17-compatible APIs to explain the method groups, FIFO/LIFO usage patterns, and how to design a `null` policy so data is never confused with an empty state.

## 1. The Two Ends of a Linked List

You can visualize a list containing A, B, and C as follows:

~~~text
first / head                       last / tail
     |                                  |
     v                                  v
    [A] <------------> [B] <----------> [C]
~~~

- **Head (`first`/`head`):** the end holding element A in the diagram.
- **Tail (`last`/`tail`):** the end holding element C.
- `addFirst` inserts before A; `addLast` inserts after C.
- Retrieving from the head or tail does not require traversing intermediate nodes.

In a doubly linked list implementation, the structure maintains references to both the first node and the last node. Reading an end or updating an end requires only a constant number of link operations.

This differs from `get(i)` in the middle: a middle index still requires searching for the node. Do not use the cost of double-ended operations to infer that every operation on `LinkedList` is O(1).

### 1.1. Deque Describes Usage, LinkedList Is an Implementation

An illustrative method body snippet:

~~~java
Deque<String> work = new LinkedList<>();
work.addLast("A");
work.addFirst("urgent");
~~~

The variable is declared as `Deque` to express that the program cares about the two ends. The actual object is still a `LinkedList`; the ability to store `null`, the memory layout, and synchronization requirements come from this implementation.

According to [LinkedList Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), the structure permits all elements, including `null`. According to [Deque Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), methods are organized into pairs with different failure-reporting behaviors.

### 1.2. An Empty List Differs from a List Containing Null

The two states below are different:

~~~text
empty:
size = 0
no element nodes

containing one null element:
size = 1
first/last -> [item = null]
~~~

A node holding a `null` element is still a real node and still counts toward the size. Only the absence of head/tail nodes represents an empty list; a `null` value inside an element does not make the list empty by itself.

This is the foundation for understanding the seemingly similar results of `peek`, `poll`, `getFirst`, and `removeFirst`.

## 2. Inspecting vs. Retrieving/Removing: Choosing the Right Method Group

There are two independent decisions:

1. Only inspect the element, or retrieve and remove it from the structure?
2. When no element is present, throw an exception or return `null`?

### 2.1. Methods at the Head

| Purpose | Throws Exception if Empty | Returns Null if Empty | Removes Element? |
|---|---|---|---|
| Inspect head | `getFirst()` | `peekFirst()` | No |
| Retrieve head | `removeFirst()` | `pollFirst()` | Yes, if a head node exists |

The exception-throwing group throws `NoSuchElementException` when the list is empty. The `null`-returning group does not throw an exception due to emptiness.

How to choose based on the program contract:

- If having no element is a normal situation, the `peek`/`poll` group is usually convenient.
- If at that point the program requires an element to definitely exist, the `get`/`remove` group helps surface contract violations.
- When `null` elements are allowed, looking only at the result of the `peek`/`poll` group is insufficient to distinguish an empty state.

### 2.2. Methods at the Tail

| Purpose | Throws Exception if Empty | Returns Null if Empty | Removes Element? |
|---|---|---|---|
| Inspect tail | `getLast()` | `peekLast()` | No |
| Retrieve tail | `removeLast()` | `pollLast()` | Yes, if a tail node exists |

The two ends are symmetrical in semantics. When reading code, the `First` or `Last` suffix indicates which end is affected; the verb indicates whether removal occurs and how emptiness is reported.

### 2.3. Inspecting Does Not Change the Element Count

With `[A, B, C]`:

~~~text
getFirst()  -> A, list remains [A, B, C]
peekLast()  -> C, list remains [A, B, C]

removeFirst() -> A, list becomes [B, C]
pollLast()    -> C, list becomes [B]
~~~

If an algorithm needs to check the head element multiple times before deciding to process it, `peekFirst` or `getFirst` is more appropriate than removing it and re-inserting it manually. Once processing is complete and the item must leave the queue, calling only `peek` will not advance the state.

### 2.4. An Exception on Empty Is Not an Exception on a Null Element

If the head of the list is a `null` element and the list is not empty:

- `getFirst()` returns `null` without throwing `NoSuchElementException`.
- `removeFirst()` returns `null` and removes that node.
- `peekFirst()` returns `null` and keeps the node intact.
- `pollFirst()` returns `null` and removes that node.

The same applies at the tail.

Therefore, do not refer to the exception-throwing group as "the group that always returns a non-null element." This group distinguishes **having no node** via an exception; it does not alter the data policy of `LinkedList`.

## 3. Adding to Both Ends: add and offer Differ in Contract

| Target End | Add Method | Return Type | Offer Method | Return Type |
|---|---|---|---|---|
| Head | `addFirst(e)` | `void` | `offerFirst(e)` | `boolean` |
| Tail | `addLast(e)` | `void` | `offerLast(e)` | `boolean` |

In the general `Deque` contract, for a capacity-restricted structure:

- The `add` group can report failure to insert due to full capacity by throwing `IllegalStateException`.
- The `offer` group can return `false` when no space is available.

That is why both forms exist. `offer` does not mean "ignore all errors and never throw an exception." An implementation that forbids `null` can still throw `NullPointerException` on `offer(null)`.

### 3.1. With LinkedList, offer Normally Returns true Upon Completion

`LinkedList` does not have a configuration parameter limiting the number of elements like a bounded queue. Its `offer`, `offerFirst`, and `offerLast` methods return `true` after a successful insertion.

Do not use `false` as an expected mechanism to detect when a linked list is "full." Memory is still finite; allocation can fail. `offer` does not turn resource exhaustion into a load-throttling system or a guarantee of infinite storage.

If requirements demand load bounding, you need a design with capacity limits and appropriate signaling/waiting semantics. Changing `add` to `offer` on the same `LinkedList` does not create that bound by itself.

### 3.2. Null Is Accepted by LinkedList at Both Ends

A `LinkedList<String>` can accept `addFirst(null)`, `addLast(null)`, `offerFirst(null)`, and `offerLast(null)`. This inserts a `null` element, not a "do nothing" command.

After a successful insertion, the size increases even when the inserted value is `null`.

However, passing a `null` source collection reference—such as to the collection-accepting constructor—is different from passing a collection containing a `null` element. "Permits null elements" does not mean every API parameter is allowed to be `null`.

### 3.3. Offer and Poll Do Not Wait for Data

The methods covered here are immediate operations on the current state. Calling `pollFirst()` on an empty `LinkedList` returns `null`; it does not block waiting for another thread to add an element.

If the problem involves coordinating threads with blocking waits, timeouts, or bounded capacity, an appropriate concurrent contract is required. Do not interpret the type names `Queue` or `Deque` as a promise of automatic blocking or waiting.

## 4. Using the Same Structure as FIFO or LIFO

### 4.1. FIFO Queue: In at the Tail, Out from the Head

FIFO means "first-in, first-out." With `LinkedList`, the common usage pattern is:

~~~java
Queue<String> queue = new LinkedList<>();
queue.offer("first");
queue.offer("second");
String next = queue.poll(); // "first"
~~~

The snippet above illustrates a method body. The short `Queue` method names map to the head/tail operations of `Deque` as follows:

| Short Name | Meaning on LinkedList |
|---|---|
| `add(e)` | Appends to tail; returns `true` on success |
| `offer(e)` | Equivalent in insertion direction to `offerLast(e)` |
| `remove()` | Retrieves/removes head; throws exception if empty |
| `poll()` | Retrieves/removes head; returns `null` if empty |
| `element()` | Inspects head; throws exception if empty |
| `peek()` | Inspects head; returns `null` if empty |

FIFO behavior here comes from inserting at the tail and removing from the head in this implementation. Do not infer from the `Queue` interface that every Java queue implementation uses the same ordering rule; other implementations order elements differently. See [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

When only queue semantics are needed, declaring the variable as `Queue` helps prevent accidentally calling operations on the opposite end. If both ends are needed, use `Deque` to express the full requirement.

### 4.2. LIFO Stack: In at the Head, Out from the Head

LIFO means "last-in, first-out." The stack method names in `Deque` are:

| Name | Equivalent |
|---|---|
| `push(e)` | `addFirst(e)` |
| `pop()` | `removeFirst()` |
| `peek()` | `peekFirst()` |

Pushing `one` and then `two` produces a head-to-tail order of `[two, one]`; `pop()` retrieves `two` first.

Do not mix `push` with `pollLast` and still call it the same LIFO discipline. Calling a variable a "stack" does not prevent code from retrieving from the other end.

### 4.3. remove() Differs from remove(value) and remove(index)

A concrete `LinkedList` object has multiple overloaded methods with the name `remove`:

- `remove()`: retrieves and removes the head.
- `remove(int index)`: locates and removes the element at the specified index.
- `remove(Object value)`: searches for and removes the first matching occurrence.

On a variable of type `Deque<Integer>`, `remove(1)` resolves to `remove(Object)` via autoboxing because `Deque` does not declare `remove(int)`. On a variable of type `LinkedList<Integer>`, `remove(1)` resolves to removing the element at index 1.

Therefore, when intending to operate on an endpoint, using explicit names like `removeFirst`, `pollFirst`, or `removeLast` prevents ambiguity. Removing by value or by an interior index may also require traversal and does not share the same cost model as head/tail removal.

## 5. The Core Problem with Null: One Result with Two Meanings

### 5.1. State Table at the Head

| State Before Call | peekFirst | getFirst | pollFirst | removeFirst |
|---|---|---|---|---|
| Empty | `null`, unchanged | `NoSuchElementException` | `null`, unchanged | `NoSuchElementException` |
| Head is non-null X | X, unchanged | X, unchanged | X, removes head node | X, removes head node |
| Head is actual null | `null`, unchanged | `null`, unchanged | `null`, removes head node | `null`, removes head node |

The table for the tail is symmetrical when replacing `First` with `Last`.

From this table:

~~~text
deque is empty     -> peekFirst() returns null
peekFirst()==null  -> NOT SUFFICIENT to conclude the deque is empty
~~~

A valid implication in one direction does not make the converse automatically true.

### 5.2. A Null Return from Poll May Have Modified the List

Suppose the list is currently `[null, job]`:

~~~text
pollFirst() -> null
list afterward -> [job]
~~~

If the list is empty:

~~~text
pollFirst() -> null
list afterward -> []
~~~

The return values are identical, yet one call removed an actual element while the other removed nothing.

Consequently, after receiving `null`, you must not assume that the operation left the state unchanged. This is a particularly dangerous bug when a program skips or retries work that it assumes never happened.

### 5.3. Loops Using Null as a Termination Sentinel Can Stop Prematurely

The following pattern is valid only if the data is guaranteed never to contain `null`:

~~~java
String item;
while ((item = deque.pollFirst()) != null) {
    process(item);
}
~~~

With `[A, null, B]`:

1. A is retrieved and processed.
2. The `null` element is retrieved, and its node is removed.
3. The loop condition evaluates to false, so the loop terminates.
4. B remains unprocessed in the deque.

The code does not merely skip processing `null`; it also stops before reaching subsequent elements. The full example below demonstrates this outcome: `processed=[A], remaining=[B]`.

### 5.4. Optional.ofNullable Does Not Recover Lost Information

Wrapping the result with:

~~~java
Optional<String> item = Optional.ofNullable(deque.pollFirst());
~~~

cannot distinguish between "no element was present" and "a `null` element was removed." Both become `Optional.empty`.

This is the defined behavior of [Optional.ofNullable Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#ofNullable(T)). To distinguish the two states, you must preserve separate presence information; you cannot reconstruct it solely from the `null` value returned by `poll`.

### 5.5. Unboxing Can Throw an Exception After the Node Has Already Been Removed

With `Deque<Integer>`:

~~~java
int value = deque.removeFirst();
~~~

If there is a `null` element at the head, `removeFirst` removes the node and returns `null`; then unboxing `Integer` to `int` throws `NullPointerException`.

An unboxing failure does not mean the deque remained unchanged. You must distinguish the completed method call from the subsequent conversion of its return value.

If the data genuinely permits `null`, assign the result to the wrapper type `Integer` and handle the `null` policy explicitly before converting to a primitive value.

## 6. Choosing a Clear Null Policy

### 6.1. If Null Is Not Valid Data: Reject It at the Boundary

In many work queues, there is no business reason for a work item itself to be `null`. Rejecting `null` early gives `poll`/`peek` an unambiguous emptiness signal.

A helper can call `Objects.requireNonNull` before inserting. However, a helper only guards calls that pass through it. If other code retains a direct reference to the mutable deque and calls `addFirst(null)`, the policy is bypassed.

To enforce the invariant across the application, you must control ownership and every data entry path: head insertion, tail insertion, bulk insertion, or mutation through other exposed interfaces. The domain class's API documentation should state clearly that work items must not be `null`.

When you simply need a deque that forbids `null`, consider `ArrayDeque`. This structure prohibits `null` elements; attempting to insert `null` is rejected with `NullPointerException`, as documented in [ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Switching implementations still requires verifying other requirements: the APIs used, memory characteristics, and access patterns. Sharing the `Deque` interface does not guarantee that legacy data containing `null` will be accepted when migrating to another implementation.

### 6.2. If Null Is Valid Data: Check Emptiness Independently of the Value

In a single-threaded scope, where no concurrent modification occurs between checking and removing, you can write:

~~~java
while (!deque.isEmpty()) {
    String item = deque.removeFirst();
    processIncludingNull(item);
}
~~~

Emptiness is checked via `isEmpty`; the removed value may be `null` and is still passed into business processing.

This is an illustrative pattern where `processIncludingNull` is defined by the application. The function name emphasizes that you cannot merely change the loop condition and assume all downstream processing code supports `null`.

Do not treat the "check-then-remove" pattern as an atomic operation when other threads modify the structure concurrently. In multi-threaded contexts, proper coordination must cover the entire sequence of actions.

### 6.3. If You Need a Distinguishable Return Value: Use an Explicit Presence Flag

For example, a result carrying two fields:

~~~text
present = true,  value = null  -> an element was retrieved, and its value is null
present = false, value = null  -> no element was available to retrieve
~~~

The program below uses a `Removal<E>` record to illustrate this. The helper method checks `isEmpty` and then calls `removeFirst`, explicitly scoped to situations without concurrent modification.

This is a result representation, not a complete concurrent queue class. When used outside the example, both the result creation contract and the structure's access rules must be designed accordingly.

### 6.4. An Optional Field Inside an Element Differs from a Null Element

A task might exist while lacking an optional note. You can represent this as a non-null task object whose note field has its own optionality policy, rather than using `null` itself as the queue element.

Similarly, if you need an end-of-stream marker, batch separator, or special message type, an explicit domain type representing those message kinds is typically easier to verify than an unnamed `null`. Using `null` as a sentinel convention always risks colliding with methods that treat `null` as an empty state.

The `Deque` interface specification explicitly discourages inserting `null` even in implementations that permit it, precisely because of return-value ambiguity. What a class permits and what policy an application should adopt are two separate decisions.

## 7. Complete Program: Both Ends, FIFO/LIFO, and Null States

This example runs in a single thread. It tests operations at both ends, behavior when empty, actual `null` elements, premature loop termination, and two ways to represent missing data.

### 7.1. Source Code

Save as `LinkedListEndsNullDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.Queue;

public class LinkedListEndsNullDemo {
    record Removal<E>(boolean present, E value) {}

    // Use only when no concurrent modification occurs between check and remove.
    static <E> Removal<E> removeNullableFirst(Deque<E> deque) {
        if (deque.isEmpty()) {
            return new Removal<>(false, null);
        }
        return new Removal<>(true, deque.removeFirst());
    }

    static void enqueueNonNull(Deque<String> deque, String value) {
        deque.addLast(Objects.requireNonNull(value, "value"));
    }

    static void showEmptyFailure(String name, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("expected NoSuchElementException");
        } catch (NoSuchElementException exception) {
            System.out.println(name + ": NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        Deque<String> ends = new LinkedList<>();
        ends.addLast("B");
        ends.addFirst("A");
        boolean tailAccepted = ends.offerLast("C");
        boolean headAccepted = ends.offerFirst("Z");
        System.out.printf("offers: head=%s, tail=%s, values=%s%n",
                headAccepted, tailAccepted, ends);
        System.out.printf("get ends: first=%s, last=%s, size=%d%n",
                ends.getFirst(), ends.getLast(), ends.size());
        System.out.printf("peek ends: first=%s, last=%s, size=%d%n",
                ends.peekFirst(), ends.peekLast(), ends.size());
        System.out.println("removeFirst: " + ends.removeFirst());
        System.out.println("pollLast: " + ends.pollLast());
        System.out.println("remaining: " + ends);

        Queue<String> queue = new LinkedList<>();
        queue.offer("one");
        queue.offer("two");
        System.out.println("FIFO poll: " + queue.poll());
        System.out.println("FIFO element: " + queue.element());
        System.out.println("FIFO remove: " + queue.remove());

        Deque<Integer> dequeView = new LinkedList<>(List.of(1, 2, 3));
        LinkedList<Integer> listView = new LinkedList<>(List.of(1, 2, 3));
        boolean removedValue = dequeView.remove(1);
        int removedIndex = listView.remove(1);
        System.out.printf("remove(1) as Deque: returned=%s, values=%s%n",
                removedValue, dequeView);
        System.out.printf("remove(1) as LinkedList: returned=%d, values=%s%n",
                removedIndex, listView);

        Deque<String> stack = new LinkedList<>();
        stack.push("one");
        stack.push("two");
        System.out.println("stack values: " + stack);
        System.out.println("LIFO pop: " + stack.pop());
        System.out.println("LIFO peek: " + stack.peek());

        Deque<String> empty = new LinkedList<>();
        System.out.printf("empty peek: first=%s, last=%s%n",
                empty.peekFirst(), empty.peekLast());
        System.out.printf("empty poll: first=%s, last=%s%n",
                empty.pollFirst(), empty.pollLast());
        showEmptyFailure("empty getFirst", () -> empty.getFirst());
        showEmptyFailure("empty getLast", () -> empty.getLast());
        showEmptyFailure("empty removeFirst", () -> empty.removeFirst());
        showEmptyFailure("empty removeLast", () -> empty.removeLast());

        Deque<String> nullable = new LinkedList<>();
        System.out.println("offerFirst(null): " + nullable.offerFirst(null));
        nullable.addLast("job");
        System.out.printf("null head: size=%d, peek=%s, get=%s%n",
                nullable.size(), nullable.peekFirst(), nullable.getFirst());
        String removedNull = nullable.pollFirst();
        System.out.printf("poll stored null: value=%s, remaining=%s%n",
                removedNull, nullable);
        System.out.println("poll job: " + nullable.pollFirst());
        System.out.println("poll empty: " + nullable.pollFirst());

        Deque<String> tailNull = new LinkedList<>();
        tailNull.addLast("job");
        tailNull.addLast(null);
        System.out.printf("null tail: peek=%s, get=%s, size=%d%n",
                tailNull.peekLast(), tailNull.getLast(), tailNull.size());
        String removedTailNull = tailNull.removeLast();
        System.out.printf("remove stored tail null: value=%s, remaining=%s%n",
                removedTailNull, tailNull);

        Deque<String> risky = new LinkedList<>();
        risky.addLast("A");
        risky.addLast(null);
        risky.addLast("B");
        List<String> processed = new ArrayList<>();
        String item;
        while ((item = risky.pollFirst()) != null) {
            processed.add(item);
        }
        System.out.printf("sentinel loop: processed=%s, remaining=%s%n",
                processed, risky);

        Deque<String> complete = new LinkedList<>();
        complete.addLast("A");
        complete.addLast(null);
        complete.addLast("B");
        List<String> all = new ArrayList<>();
        while (!complete.isEmpty()) {
            all.add(complete.removeFirst());
        }
        System.out.printf("explicit-empty loop: processed=%s, remaining=%s%n",
                all, complete);

        Deque<String> results = new LinkedList<>();
        results.addLast(null);
        System.out.println("explicit result 1: " + removeNullableFirst(results));
        System.out.println("explicit result 2: " + removeNullableFirst(results));
        results.addLast(null);
        Optional<String> optional = Optional.ofNullable(results.pollFirst());
        System.out.printf("Optional after stored null: %s, remaining=%s%n",
                optional, results);

        Deque<String> guarded = new LinkedList<>();
        enqueueNonNull(guarded, "job");
        try {
            enqueueNonNull(guarded, null);
        } catch (NullPointerException exception) {
            System.out.println("guard rejects null: remaining=" + guarded);
        }
        Deque<String> array = new ArrayDeque<>();
        try {
            array.addLast(null);
        } catch (NullPointerException exception) {
            System.out.println("ArrayDeque null: NullPointerException");
        }

        Deque<Integer> numbers = new LinkedList<>();
        numbers.addLast(null);
        try {
            int value = numbers.removeFirst();
            System.out.println(value);
        } catch (NullPointerException exception) {
            System.out.println("unboxing removed null: NullPointerException, size="
                    + numbers.size());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 LinkedListEndsNullDemo.java
java LinkedListEndsNullDemo
~~~

### 7.2. Standard Output

~~~text
offers: head=true, tail=true, values=[Z, A, B, C]
get ends: first=Z, last=C, size=4
peek ends: first=Z, last=C, size=4
removeFirst: Z
pollLast: C
remaining: [A, B]
FIFO poll: one
FIFO element: two
FIFO remove: two
remove(1) as Deque: returned=true, values=[2, 3]
remove(1) as LinkedList: returned=2, values=[1, 3]
stack values: [two, one]
LIFO pop: two
LIFO peek: one
empty peek: first=null, last=null
empty poll: first=null, last=null
empty getFirst: NoSuchElementException
empty getLast: NoSuchElementException
empty removeFirst: NoSuchElementException
empty removeLast: NoSuchElementException
offerFirst(null): true
null head: size=2, peek=null, get=null
poll stored null: value=null, remaining=[job]
poll job: job
poll empty: null
null tail: peek=null, get=null, size=2
remove stored tail null: value=null, remaining=[job]
sentinel loop: processed=[A], remaining=[B]
explicit-empty loop: processed=[A, null, B], remaining=[]
explicit result 1: Removal[present=true, value=null]
explicit result 2: Removal[present=false, value=null]
Optional after stored null: Optional.empty, remaining=[]
guard rejects null: remaining=[job]
ArrayDeque null: NullPointerException
unboxing removed null: NullPointerException, size=0
~~~

### 7.3. Reading the Key Points in the Output

After the head and tail insertions, the deque is `[Z, A, B, C]`. Both the `get` and `peek` groups keep `size = 4`. `removeFirst` removes Z, `pollLast` removes C, leaving `[A, B]`.

The FIFO sequence retrieves `one` before `two`, whereas the stack that pushed `one` and then `two` retrieves `two` first. This difference comes from which ends are selected, not from using two different storage classes.

The two `remove(1)` lines show how the static reference type affects compile-time overload resolution: through `Deque`, the value `1` is removed and a `boolean` is returned; through `LinkedList`, the element `2` at index `1` is removed and returned.

On an empty deque, `peek`/`poll` return `null` while `get`/`remove` throw `NoSuchElementException`. The program prints only the exception type so it does not depend on JDK-specific detail messages.

The line `null head: size=2` proves that the inspected value is `null` while the list still contains elements. The subsequent `poll stored null` call returns `null` but removes the head node, leaving `[job]`.

At the tail, `getLast` also returns `null` when the last node holds `null`. `removeLast` retrieves and removes that node normally; no `NoSuchElementException` is thrown because the list is not empty.

The two loops produce different results:

- The sentinel pattern stops upon polling `null`, leaving B unprocessed.
- The explicit `isEmpty` check decoupled from the element value processes all of A, `null`, and B under the single-threaded conditions of the example.

The two result records preserve the distinction between "a `null` element was present" and "no element was present." Passing the result of `poll` into `Optional.ofNullable` loses that distinction.

The input-validating helper rejects `null` before insertion, so the guarded list still contains only `job`. `ArrayDeque` rejects `null` elements by itself. Finally, the unboxing failure occurs when `size` has already dropped to 0, confirming that the retrieval/removal call completed before using the return value failed.

In the printed output lines, `null` comes from a null reference inserted directly by the code, not the string literal `"null"`. Looking solely at the formatted string representation of an arbitrary collection cannot always distinguish between the two.

## 8. Costs and Usage Boundaries

### 8.1. O(1) at Both Ends Is Link Manipulation Work

With `LinkedList`, inspecting the head/tail and linking/unlinking a node at the head/tail require a constant number of structural updates. There is no traversal to an interior node and no shifting of an array segment.

The [OpenJDK 17 LinkedList source code (build jdk-17+35)](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedList.java) shows the use of `first`/`last` references and pointer updates when nodes are linked or unlinked.

This complexity bound does not guarantee identical latency on every insertion: a new node must still be allocated, subject to memory locality and garbage collection effects. Nor does it prove that `LinkedList` is always faster than an array-backed deque across real-world workloads.

If an algorithm only inserts and removes $n$ elements at the ends, the link management work totals $O(n)$. If it also searches for a value in the middle of the list before each step, the search cost must be added.

### 8.2. Null Does Not Change Asymptotic Cost, But Changes Interpretation

Storing `null` still creates an element entry and a node. Removing it from the head requires no extra search just because the value is `null`.

The central issue with a `null` policy here is data semantics and control-flow correctness, not a speed factor. Optimizing a fast operation is useless if the program terminates early and drops work.

### 8.3. Not Automatically Thread-Safe

A standard `LinkedList` instance is not synchronized. The sequence `isEmpty` followed by `removeFirst` consists of two separate actions; another thread can mutate the structure between them if there is no coordination.

Locking individual calls in isolation or inspecting a `null` return value after a removal is not guaranteed to satisfy the contract of an entire workflow. Access ownership, synchronization, or concurrent data structures must be designed for the specific requirements.

The examples intentionally run in a single thread to clarify API semantics. Do not treat them as proof that multi-threaded queue usage is safe without synchronization.

### 8.4. Type Names Help Restrict Unnecessary Calls

If only FIFO behavior is needed, accept or return `Queue<E>`. If both ends are needed, `Deque<E>` expresses that intent. If indexed list access is also required, evaluate that traversal cost separately rather than treating every API on `LinkedList` as equivalent.

Regardless of the declared interface type, document the `null` policy clearly in your application contract. A `Deque<E>` variable does not state by itself whether its data permits `null`; `LinkedList` and `ArrayDeque` already differ in this regard.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `Deque` always forbids `null` | The interface does not require every implementation to forbid `null`; `LinkedList` permits it |
| Because `LinkedList` allows `null`, you should use `null` as an empty marker | `poll`/`peek` already use `null` as an empty signal; the application needs a clear policy |
| If `peekFirst` returns `null`, the deque is definitely empty | The head element itself might be `null` |
| If `pollFirst` returns `null`, nothing was removed | It may have just retrieved and removed an actual `null` element |
| `getFirst` always returns a non-null value | It throws an exception when no node exists, but still returns `null` if the head node holds `null` |
| `removeFirst` throws `NullPointerException` when the element is `null` | `LinkedList` itself returns `null`; any `NullPointerException` happens in downstream code (such as unboxing) |
| Wrapping `poll` in `Optional` solves every state ambiguity | `ofNullable` collapses both data `null` and empty-signal `null` into `Optional.empty` |
| `offer` never throws an exception | It does not convert every invalid input or allocation failure into `false` |
| `offer` returning `false` is how `LinkedList` reports out-of-memory | `LinkedList` has no bounded-capacity mechanism like that |
| `poll` waits until an element arrives | It checks the current state and returns immediately |
| Calling `push` then `pollLast` follows the same stack pattern | The two operations act on opposite ends; check the resulting order |
| `remove()`, `remove(value)`, and `remove(index)` all remove the head | These are distinct method contracts |
| `isEmpty` followed by `remove` is atomic | Only safe when proper coordination covers the entire sequence |
| Every `LinkedList` operation is O(1) because both ends are O(1) | Searching the middle by index or value still incurs traversal cost |

## 10. Self-Check Exercises

### Exercise 1: Reading Without Removing

A deque currently holds `[A, B]`. After calling `peekFirst()` and `getLast()`, what is the remaining size? What are the two returned values?

**Explanation:** There are still 2 elements; the results are A and B respectively. Both methods only inspect.

### Exercise 2: Removing from Both Ends

Starting from `[A, B, C]`, call `pollLast()` followed by `removeFirst()`. What remains?

**Explanation:** C is removed first, then A is removed, leaving `[B]`. The suffix determines which end is affected, regardless of whether the method throws an exception or returns a signal when empty.

### Exercise 3: A Single Null Element

A deque contains exactly one `null` element. What do `getFirst()`, `isEmpty()`, and `size()` return?

**Explanation:** `getFirst` returns `null`, `isEmpty` is `false`, and `size` is 1. Inspecting the head does not remove the node. If `removeFirst` is called next, it returns `null` and leaves the deque empty.

### Exercise 4: Stopping on a Sentinel

With `[A, null, B, C]`, which values does the loop `while ((x = pollFirst()) != null)` process, and what is left behind?

**Explanation:** Only A is processed; the `null` element is removed when evaluating the loop condition, the loop terminates, and `[B, C]` remain unprocessed.

### Exercise 5: Stack Ordering

Call `push("A")`, `push("B")`, `push("C")`, and then `pop()`. What value is returned?

**Explanation:** C, because both `push` and `pop` operate at the head; the last item inserted is removed first. Afterward, the head-to-tail sequence is `[B, A]`.

### Exercise 6: Switching Implementations

A variable of type `Deque<String>` currently holds a `LinkedList` and its data includes `null`. Does simply changing the constructor to `ArrayDeque` preserve all behavior?

**Explanation:** No. `ArrayDeque` does not permit inserting `null`. You must review the data policy and every element insertion path, not just keep the interface name unchanged.

### Exercise 7: Presence-Aware Result

Why does `Removal(true, null)` differ from `Removal(false, null)`, whereas `Optional.ofNullable(pollFirst())` cannot distinguish between those two cases?

**Explanation:** The record stores a separate boolean flag indicating whether an element was present. The `Optional` is constructed solely from the returned value; when that value is `null`, both origins are represented as having no value.

Using both ends of `LinkedList` effectively requires choosing the right **end**, **structural effect**, and **emptiness-reporting mechanism**. Once the `null` policy is explicitly decided, the method pairs become consistent and the processing flow avoids mistaking a valid element for the end of data.
