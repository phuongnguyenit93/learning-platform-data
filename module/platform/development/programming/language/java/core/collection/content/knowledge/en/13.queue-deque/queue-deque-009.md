# Comparing ArrayDeque, LinkedList, and Stack

## 1. Comparing by Intended Role

The same sequence A, B, C can be managed as a first-in, first-out queue or a last-in, first-out stack. ArrayDeque, LinkedList, and Stack can all appear in code that processes such sequences, but they are not three completely interchangeable classes.

In single-threaded code that needs non-null queue or stack operations, `Deque<E>` with `ArrayDeque<E>` is usually the appropriate starting point. LinkedList also serves a List role and provides the ability to update through a traversal cursor whose position is already known. Stack is a legacy class extending Vector, commonly encountered in code that requires compatibility.

The decision should be based on operations and contracts:

| Aspect | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| Primary structure | Resizable circular array | Doubly linked list | Resizable array from Vector |
| Prominent role interfaces | Deque, Queue | List, Deque, Queue | List via Vector; dedicated Stack API |
| FIFO usage | Yes | Yes | Does not implement Queue/Deque |
| LIFO usage | Yes via push/pop | Yes via push/pop | Yes via Stack API |
| Indexed access | No get(index) API | Yes, requires traversing nodes | Yes via Vector |
| Null elements | Not accepted | Accepted | Accepted |
| Built-in synchronization | No | No | Underlying operations use Vector/Stack synchronization |
| Notable characteristics | Array resizing has periodic cost | Each element has a node and links | Legacy API, also exposes List/Vector operations |

The baseline characteristics are referenced against the Java 17 documentation for [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [Stack](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html), and [Vector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html).

This article explains why those differences matter, rather than choosing a class based solely on slogans like “arrays are fast” or “linked lists have O(1) insertion/removal.”

## 2. What Trade-offs Does the Storage Structure Create?

### 2.1. ArrayDeque: References in a Circular Array

Model:

```text
backing array:
[ C | D | . | . | A | B ]
                  ^
                logical head

logical sequence: A, B, C, D
```

The head and tail positions wrap around the array boundaries. Adding or removing at the front does not require shifting all remaining elements back to slot 0.

If space runs out, the structure grows the array and reorganizes the references. Therefore, some insertions take significantly more work than ordinary ones.

The reference slots being in an array does not mean the element objects themselves are all placed contiguously in memory. Objects can exist independently; the array holds references to them.

### 2.2. LinkedList: Each Element in a Doubly Linked Node

Model:

```text
first
  |
  v
[prev | A | next] <-> [prev | B | next] <-> [prev | C | next]
                                                   ^
                                                   |
                                                  last
```

By maintaining both ends, adding or removing first/last does not require searching from the beginning through the entire list. However, to retrieve an element at an arbitrary index, links must be followed from the closer end.

Each element also has a node containing link information. That creates allocation and memory overhead beyond the reference to the data. You should not state a fixed byte count for all JVMs without specifying the configuration and measurement method.

### 2.3. Stack: LIFO Behavior Built on Vector

Stack extends Vector. The top of the stack is placed at the end of Vector's sequence:

```text
index:       0    1    2
data:        A    B    C
             ^         ^
           bottom     top
```

Push adds at the end; pop removes at the end. The standard iterator traverses in index order from 0 upward, so it goes from bottom to top.

Due to inheritance, Stack also has List/Vector methods such as indexed `get` or inserting into the middle. Those capabilities are unnecessary for a pure stack interface and can make usage intent less clear.

The [Java 17 Stack documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html) recommends using Deque and its implementations for a more complete and consistent set of LIFO operations in new code.

## 3. Complexity Must Be Tied to the Exact Operation

Let n be the current number of elements. The following table describes common operations assuming value comparison has constant cost:

| Operation | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| Add/remove for LIFO | Add O(1) amortized; remove head O(1) | O(1) at head, with node allocation/removal | Push O(1) amortized; pop end O(1), with synchronization mechanism |
| Add end, remove head for FIFO | O(1) amortized for head/tail operations | O(1) for links at both ends | No Queue API; simulating with remove(0) shifts the sequence |
| Peek head or top | O(1) | O(1) | O(1), via Stack API |
| get(i) | Not supported by index | O(n) in the general case | O(1) via Vector |
| Search or remove by value | O(n) in the general case | O(n) to find position | O(n) in the general case |
| Insert in middle with only index | No indexed insert API | Must find position, general case O(n) | Shifts subsequent elements, O(n) |
| Update at a positioned ListIterator | No ListIterator | Local link changes can be O(1) | No similar advantage due to array backing |
| Full traversal | O(n) | O(n) | O(n) |

The numbers do not mean the three structures have the same actual runtime when both list O(1). Node allocation, array copying, reference chasing, and synchronization all have different costs.

### 3.1. Amortized Differs from Per-Call

With a resizable array, most insertions only write into existing space. Occasionally, it must allocate and move many references.

Amortized O(1) means the total cost can be distributed over a sequence of operations; a single insertion that happens right when the array grows can still cost O(n).

If requirements have strict latency bounds, looking only at the amortized bound is not enough. You need to evaluate scale, usage history, and allocation behavior in a real environment.

### 3.2. LinkedList Does Not Have “Free Middle Removal”

If you already have a ListIterator standing at the position to update, changing adjacent links can be cheap.

However, if the input is only index 5000 or a value to search for, LinkedList must traverse to that position first. The search cost does not disappear just because the node linking/unlinking step is O(1).

In particular, looping by index:

```java
// Snippet prone to excessive traversal on LinkedList.
for (int i = 0; i < list.size(); i++) {
    use(list.get(i));
}
```

can create quadratic total work on LinkedList. An iterator or for-each loop fits linked storage much better. This is an illustrative snippet, not a standalone program.

### 3.3. Memory and Locality

ArrayDeque and Vector hold references in an array, whereas LinkedList must traverse through nodes. This affects read locality and allocation volume.

Conversely, an array can retain excess capacity after a load spike and must handle capacity growth. LinkedList has per-element node overhead.

You cannot infer a fixed speedup ratio from a complexity table. If performance is an actual requirement, measure with a representative scenario, checking both allocation volume and latency, not just a small loop.

## 4. Program 1: The Same Role Can Produce the Same Output

Save the file `ThreeCollectionsRolesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.Queue;
import java.util.Stack;

public class ThreeCollectionsRolesDemo {
    static List<String> drainQueue(Queue<String> queue) {
        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.remove());
        }
        return result;
    }

    static List<String> drainDequeStack(Deque<String> stack) {
        List<String> result = new ArrayList<>();
        while (!stack.isEmpty()) {
            result.add(stack.pop());
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C");

        Queue<String> arrayQueue = new ArrayDeque<>(input);
        Queue<String> linkedQueue = new LinkedList<>(input);
        System.out.println("ArrayDeque FIFO = " + drainQueue(arrayQueue));
        System.out.println("LinkedList FIFO = " + drainQueue(linkedQueue));

        Deque<String> arrayStack = new ArrayDeque<>();
        Deque<String> linkedStack = new LinkedList<>();
        Stack<String> legacyStack = new Stack<>();
        for (String item : input) {
            arrayStack.push(item);
            linkedStack.push(item);
            legacyStack.push(item);
        }

        System.out.println("ArrayDeque iteration = " + arrayStack);
        System.out.println("LinkedList iteration = " + linkedStack);
        System.out.println("Stack iteration = " + legacyStack);
        System.out.println("ArrayDeque LIFO = " + drainDequeStack(arrayStack));
        System.out.println("LinkedList LIFO = " + drainDequeStack(linkedStack));

        List<String> legacyOutput = new ArrayList<>();
        while (!legacyStack.empty()) {
            legacyOutput.add(legacyStack.pop());
        }
        System.out.println("Stack LIFO = " + legacyOutput);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ThreeCollectionsRolesDemo.java
java ThreeCollectionsRolesDemo
```

Output of the verification run:

```text
ArrayDeque FIFO = [A, B, C]
LinkedList FIFO = [A, B, C]
ArrayDeque iteration = [C, B, A]
LinkedList iteration = [C, B, A]
Stack iteration = [A, B, C]
ArrayDeque LIFO = [C, B, A]
LinkedList LIFO = [C, B, A]
Stack LIFO = [C, B, A]
```

The programs in this article use language features and APIs available in Java 17 and later, compiled with `--release 17` and verified using Azul OpenJDK 24.0.2.

### 4.1. ArrayDeque and LinkedList Both Perform FIFO via Queue

Both objects are created from the same sequence A, B, C. When processed with `Queue.remove`, both yield A, B, C.

That shows an interface can be chosen to express a role. It does not mean null handling, memory, or costs for other operations are identical.

The loops in the program are single-threaded code, so checking for emptiness and then calling `remove` has no interleaved updates. Do not automatically carry that assumption over to multithreaded code.

### 4.2. All Three Can Produce the Same Pop Order

After pushing A, B, C, all three retrieve C, B, A when using the appropriate LIFO API.

However, the initial iteration order differs:

```text
ArrayDeque using push: [C, B, A]  -> top at first
LinkedList using push: [C, B, A]  -> top at first
Stack:                 [A, B, C]  -> top at end of Vector
```

The same pop order does not mean the same iterator order. This is an important difference when displaying history, serializing a sequence, or copying into another collection.

### 4.3. This Program Is Not a Benchmark

The printed lines only verify ordering contracts. No timing is measured, so the output cannot be used to conclude which class is faster.

Even if a clock were added to a small example, results would still be affected by JVM warmup, optimizations, allocation, and printing work. Evaluating performance requires designing a dedicated benchmark.

## 5. Empty and Null APIs: Same Name Does Not Guarantee Same Behavior

### 5.1. Peek on Deque Differs from Peek on Legacy Stack

| Call when empty | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| `peek()` | null | null | EmptyStackException |
| `pop()` | NoSuchElementException | NoSuchElementException | EmptyStackException |
| Peek expecting a Deque-style exception | `getFirst()` | `getFirst()` | Dedicated Stack.peek API |
| Remove expecting null Queue/Deque-style | `poll()` or `pollFirst()` | `poll()` or `pollFirst()` | No Queue poll method |

Therefore, changing a declaration from Stack to Deque while keeping the same `peek`/`pop` names can still alter the empty-handling branch or the exception type being caught.

If the exception is part of a public method's contract, you must decide whether to preserve compatibility with a wrapper or explicitly update the contract.

### 5.2. Null Breaks the Simple Meaning of poll/peek

ArrayDeque forbids null elements. When `poll` returns null, there is no ambiguity with a real null member.

LinkedList accepts null. If the first element is null, `poll` can return null while having just removed a real element and with the list still containing other data.

Stack can also hold null. `peek` returns null when the top is a real null member, whereas `peek` on an empty Stack throws an exception. Do not use “peek is not null” to check whether a Stack has elements.

Accepting null in a collection does not mean null is a good data model for every queue. If you want patterns that poll until null, you should establish non-null member data.

### 5.3. Push Has Different Return Types

- `Stack.push(e)` returns `e`.
- `Deque.push(e)` returns `void`.

Legacy code using expressions like assigning the result of `push` or passing it as an argument cannot switch classes merely by changing the type name.

If you need to keep the pushed value, store the element in a variable and then push, rather than relying on a return value that does not exist in Deque.

## 6. Program 2: Comparing Empty and Null Handling

Save the file `EmptyAndNullComparisonDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedList;
import java.util.Stack;

public class EmptyAndNullComparisonDemo {
    static void reportFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected a runtime exception");
        } catch (RuntimeException ex) {
            System.out.println(label + " = " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> array = new ArrayDeque<>();
        LinkedList<String> linked = new LinkedList<>();
        Stack<String> legacy = new Stack<>();

        System.out.println("empty ArrayDeque peek = " + array.peek());
        System.out.println("empty LinkedList peek = " + linked.peek());
        reportFailure("empty Stack peek", legacy::peek);
        reportFailure("empty ArrayDeque pop", array::pop);
        reportFailure("empty LinkedList pop", linked::pop);
        reportFailure("empty Stack pop", legacy::pop);
        reportFailure("ArrayDeque offer null", () -> array.offerLast(null));

        linked.offerLast(null);
        linked.offerLast("X");
        System.out.println("LinkedList size with null = " + linked.size());
        System.out.println("LinkedList empty with null = " + linked.isEmpty());
        System.out.println("LinkedList peek null member = " + linked.peek());
        System.out.println("LinkedList poll null member = " + linked.poll());
        System.out.println("LinkedList remaining = " + linked);

        System.out.println("Stack push null result = " + legacy.push(null));
        System.out.println("Stack empty with null = " + legacy.empty());
        System.out.println("Stack peek null member = " + legacy.peek());
        System.out.println("Stack pop null member = " + legacy.pop());
        System.out.println("Stack empty after pop = " + legacy.empty());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 EmptyAndNullComparisonDemo.java
java EmptyAndNullComparisonDemo
```

Output of the verification run:

```text
empty ArrayDeque peek = null
empty LinkedList peek = null
empty Stack peek = EmptyStackException
empty ArrayDeque pop = NoSuchElementException
empty LinkedList pop = NoSuchElementException
empty Stack pop = EmptyStackException
ArrayDeque offer null = NullPointerException
LinkedList size with null = 2
LinkedList empty with null = false
LinkedList peek null member = null
LinkedList poll null member = null
LinkedList remaining = [X]
Stack push null result = null
Stack empty with null = false
Stack peek null member = null
Stack pop null member = null
Stack empty after pop = true
```

The `reportFailure` method causes the example to stop with `AssertionError` if an operation does not throw an exception as expected. The exception class names in the output are actual observed results from running the code, not predicted labels.

### 6.1. ArrayDeque Can Still Throw on offer

`offer` may use a boolean for certain failures such as lack of space in a bounded-capacity implementation, but it does not turn every invalid input into `false`.

`ArrayDeque.offerLast(null)` throws `NullPointerException`. Thus, data validity policies must be checked separately from empty or full policies.

### 6.2. LinkedList Still Has X After poll Returns null

The list has two elements: `null` then `X`. Calling `poll` removes the first member `null` and returns `null`; the list still has `X`.

The pattern:

```java
// Not general if the queue can contain null elements.
String next;
while ((next = queue.poll()) != null) {
    process(next);
}
```

can stop before draining all data if used with a LinkedList containing `null`. This snippet illustrates a flawed assumption, not a standalone program.

In single-threaded code that allows null, you can separate the emptiness check from the retrieved value and handle null intentionally. With multiple threads, the check-then-remove sequence also has its own coordination requirements.

### 6.3. Stack Holds null Without Being Empty

After pushing `null`, `empty` returns `false`; `peek` and `pop` return `null` as real data. Only after `pop` does `empty` return `true`.

This reminds us that replacing Stack or a LinkedList containing nulls with ArrayDeque requires a data decision, not just editing imports and constructors.

Do not silently filter out nulls if each occurrence has business meaning. You may need to reject the input, change the representation type, or choose an appropriate structure.

## 7. When Is LinkedList's List Capability Valuable?

ArrayDeque primarily serves two-ended operations. LinkedList also implements List and ListIterator, allowing a traversal cursor to move through the sequence and update at a known position.

For example, a process scanning points along a route sequentially, occasionally inserting a point right before the next position or removing the point just read. If the cursor is already there, modifying local links does not require re-finding the position by index.

Keep the two steps separate:

```text
navigate to the position to update
    +
update at the known position
```

The second step can be O(1) with linked nodes; the first step still has navigation cost.

Do not choose LinkedList merely because you heard “O(1) middle insertion” if every application operation starts from a random index and has to traverse from the front or back.

### 7.1. You Cannot Replace List with Deque Just to Swap Implementations

If a method uses `List.get(i)`, `ListIterator.add`, or indexed operations, ArrayDeque does not satisfy the same interface.

In that case, the design decision is not simply replacing `new LinkedList<>()` with `new ArrayDeque<>()`. You need to see whether the algorithm truly needs List capabilities or can be re-expressed using two-ended operations.

Conversely, if the code only uses `offer`/`poll` or `push`/`pop`, declaring it with Queue/Deque expresses the role clearly and allows choosing a more suitable implementation.

### 7.2. Node Allocation and Known Position

LinkedList must allocate a node on insertion. O(1) in terms of the number of links to change does not mean allocation, garbage collection, or memory access work is free.

Therefore, the benefit of ListIterator should be evaluated within the specific algorithm: the frequency of local updates, traversal pattern, and actual data, rather than looking at one operation in isolation.

## 8. Program 3: Cursor Position and Local Updates

Save the file `LinkedListCursorComparisonDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorComparisonDemo {
    public static void main(String[] args) {
        LinkedList<String> route = new LinkedList<>(List.of("A", "C", "D"));
        ListIterator<String> cursor = route.listIterator(1);

        System.out.println("initial route = " + route);
        cursor.add("B");
        System.out.println("after cursor add B = " + route);
        System.out.println("cursor next = " + cursor.next());
        cursor.remove();
        System.out.println("after cursor remove = " + route);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.set("B2");
        System.out.println("after cursor set = " + route);
        System.out.println("indexed get 1 = " + route.get(1));

        route.addFirst("START");
        route.addLast("END");
        System.out.println("with both ends = " + route);
        System.out.println("remove first = " + route.removeFirst());
        System.out.println("remove last = " + route.removeLast());
        System.out.println("final route = " + route);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 LinkedListCursorComparisonDemo.java
java LinkedListCursorComparisonDemo
```

Output of the verification run:

```text
initial route = [A, C, D]
after cursor add B = [A, B, C, D]
cursor next = C
after cursor remove = [A, B, D]
cursor previous = B
after cursor set = [A, B2, D]
indexed get 1 = B2
with both ends = [START, A, B2, D, END]
remove first = START
remove last = END
final route = [A, B2, D]
```

### 8.1. Positioning Cost Lies in Creating or Moving the Cursor

`listIterator(1)` locates the position before element C. With small data, this cost is unnoticeable; with large data in the middle of the sequence, remember that positioning still has a cost.

Afterward, `cursor.add` inserts B at the cursor position. `cursor.next` reads C; `cursor.remove` removes the exact element just read. There is no separate call to search for C again by value.

The program does not measure time and does not by itself prove a performance ratio. It helps demonstrate what the condition “already at the position” means in the API.

### 8.2. Iterators Have State Rules

`ListIterator.remove` applies to the element most recently returned by `next` or `previous`. It is not “remove an arbitrary element” without regard to traversal state.

`set` replaces the value of the element just read; `add` inserts at the cursor position. When building an update algorithm, you must uphold the contracts of those operations.

After the program modifies both ends directly through `route`, it does not reuse the old `cursor`. You should not continue using an iterator after structural modifications through another path and assume its state remains valid.

### 8.3. The Same LinkedList Has Two API Roles

`route` also has `addFirst`/`addLast`/`removeFirst`/`removeLast`, so it can be used like a Deque at both ends.

This shows flexibility, but it does not mean an application should arbitrarily mix mid-sequence access with a stack that requires the invariant of changing only at the top. Choosing the right interface and ownership remains important.

## 9. How Far Does Stack's Synchronization Protect?

Stack extends Vector, a class that has synchronization mechanisms for its underlying operations. That differs from ArrayDeque and LinkedList, which do not synchronize themselves.

However, you must distinguish a single operation from a sequence of operations.

Suppose a stack currently has exactly one element:

```text
Thread 1: calls empty() -> false
Thread 2: calls pop()   -> removes the last element
Thread 1: calls pop()   -> EmptyStackException
```

Each individual call can still execute the class's synchronization mechanism properly. The flawed assumption lies in the gap between Thread 1's two calls: the state has changed.

### 9.1. “Having synchronized” Does Not Make Every Workflow Atomic

Sequences such as check-then-remove, iterate-then-update, or multi-step copies require a coordination boundary appropriate for the entire requirement.

In legacy code where Stack must be kept, you may need to synchronize the entire related sequence under the same mechanism that all participants obey. In new designs, review the processing model and the concurrency APIs needed.

Do not use Stack just because it has synchronization and assume requirements for waiting on data, capacity bounds, failure handling, or multi-party coordination are already met.

### 9.2. Iterators Are Not Concurrency-Safe Snapshots

The iterators of the classes in this article do not automatically provide a stable snapshot across concurrent modifications. Fail-fast behavior can help detect modifications, but it does not guarantee that a shared-data algorithm is correct.

Do not use “no `ConcurrentModificationException` seen in a few runs” as proof of multithreaded safety.

Similarly, a Stack having synchronized methods does not mean a `for-each` loop over it automatically holds a lock covering the entire loop.

### 9.3. Choose the Concurrency Role Before Choosing the Class

If data belongs to a single thread, do not choose Stack just to get a synchronization mechanism the algorithm does not need.

If data is shared, identify which operations must be atomic, whether waiting on empty/full is needed, and the bounding policy. Only then is comparing these three classes part of the decision; it is not the whole design.

Do not remove synchronization from a system just because ArrayDeque is usually suitable for single-threaded FIFO/LIFO. Usage conditions are part of the choice.

## 10. What to Check When Migrating Stack Code to Deque?

A new LIFO declaration is typically:

```java
// Snippet; requires importing java.util.Deque and ArrayDeque.
Deque<String> history = new ArrayDeque<>();
```

`push` adds at `first`; `pop` removes `first`. However, legacy Stack code may depend on more than those two operations.

| What legacy code may depend on | What to review |
|---|---|
| `pop` on empty throws `EmptyStackException` | `Deque.pop` throws `NoSuchElementException` |
| `peek` on empty throws an exception | `Deque.peek` returns `null`; `getFirst` throws a Deque-style exception |
| `Stack.push` returns the element | `Deque.push` returns `void` |
| `Stack.empty` | `Deque` uses `isEmpty` |
| `Stack.search` returns depth from the top | `Deque` has no direct equivalent `search` API |
| Iterator goes from bottom to top | `Deque` using `push` iterates from top down |
| `null` elements are valid | `ArrayDeque` rejects `null` |
| Inherited Vector/List operations | `ArrayDeque` has no indexed access/insertion |
| Synchronization behavior | `ArrayDeque` does not provide it automatically |
| List-style `equals` | `ArrayDeque` does not compare sequence contents with `equals` like List |

You should not convert a public type used by many callers with a simple text replacement. First identify which behaviors belong to the actual contract.

### 10.1. Copying the Iterator Sequence Does Not Guarantee the Same Stack Top

A Stack with A, B, C pushed iterates as A, B, C. The `ArrayDeque` constructor taking a collection preserves the source's iterator order, so the new sequence is A, B, C from `first` to `last`.

If `Deque.pop` is used afterward, the first value removed is A, whereas legacy `Stack.pop` would remove C.

Therefore:

```java
// Snippet: does not preserve the same top if Deque.push/pop are used afterward.
Deque<String> copy = new ArrayDeque<>(legacyStack);
```

can copy the traversal order accurately while getting the intended stack semantics wrong.

### 10.2. Keeping the Top-at-First Convention

With a single-threaded, non-null source that is not modified during copying, you can iterate from bottom to top and `push` each element onto the new Deque.

Each new element becomes `first`, so the final top is the exact element at the top of the legacy Stack.

If the source contains nulls, decide how to handle them beforehand; do not let a half-completed conversion be treated as successful. If the source is shared across multiple threads, capture the data under an appropriate consistent boundary.

### 10.3. Another Option Is Top at Last

You can keep the A, B, C iterator order in the new Deque while using `addLast`/`removeLast`/`getLast` as the stack operations.

That approach is also valid if all code consistently uses the same end. However, you must not copy under the top-at-last convention and then call `push`/`pop`, which place the top at `first`.

The choice should be expressed in a wrapper interface or usage rules, avoiding situations where each part of the code guesses.

## 11. Program 4: Preserving Which Element Will Be Popped Next

Save the file `StackToDequeMigrationDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Stack;

public class StackToDequeMigrationDemo {
    public static void main(String[] args) {
        Stack<String> legacy = new Stack<>();
        legacy.push("A");
        legacy.push("B");
        legacy.push("C");

        Deque<String> iteratorOrderCopy = new ArrayDeque<>(legacy);
        Deque<String> topPreservingCopy = new ArrayDeque<>();
        for (String item : legacy) {
            topPreservingCopy.push(item);
        }

        System.out.println("legacy bottom to top = " + legacy);
        System.out.println("legacy top = " + legacy.peek());
        System.out.println("legacy search B = " + legacy.search("B"));
        System.out.println("constructor copy first = "
                + iteratorOrderCopy.peekFirst());
        System.out.println("top-preserving copy = " + topPreservingCopy);
        System.out.println("top-preserving peek = " + topPreservingCopy.peek());

        List<String> output = new ArrayList<>();
        while (!topPreservingCopy.isEmpty()) {
            output.add(topPreservingCopy.pop());
        }
        System.out.println("migrated pop order = " + output);
        System.out.println("legacy remains = " + legacy);
        System.out.println("legacy top remains = " + legacy.peek());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 StackToDequeMigrationDemo.java
java StackToDequeMigrationDemo
```

Output of the verification run:

```text
legacy bottom to top = [A, B, C]
legacy top = C
legacy search B = 2
constructor copy first = A
top-preserving copy = [C, B, A]
top-preserving peek = C
migrated pop order = [C, B, A]
legacy remains = [A, B, C]
legacy top remains = C
```

### 11.1. Constructor Copy and Top-Preserving Copy Differ

The constructor copy has `first` as A because it follows Stack's iterator. The top-preserving version uses `push` during iteration, so `first` is C.

The resulting `migrated pop order` is C, B, A, matching the LIFO semantics that needed to be preserved.

The original Stack remains A, B, C and its top remains C. The program created a separate container rather than consuming the legacy Stack.

### 11.2. Search Is Not contains

`Stack.search(B)` returns 2, meaning B is at the second position from the top according to Stack's 1-based convention. `Deque.contains(B)` only returns a boolean and does not replace that depth meaning.

If the application genuinely needs the position from the top, you must redefine how it is expressed and its search cost. Do not replace `search` with `contains` just to make the code compile.

### 11.3. Copying the Container Does Not Deep-Copy the Data

The example uses immutable `String`s, making container separation easy to observe. With mutable objects, both containers can still hold references to the same objects.

Changing the storage class does not automatically resolve ownership and lifecycle of individual elements.

## 12. Choosing a Class for a Specific Requirement

### 12.1. Only Single-Threaded FIFO or LIFO Needed

You can start with:

```java
// Snippet expressing roles.
Queue<Job> queue = new ArrayDeque<>();
Deque<Change> history = new ArrayDeque<>();
```

`Job` and `Change` are business types in the surrounding program. ArrayDeque fits when data is non-null and operations are primarily at the two ends.

There is no need to choose LinkedList just because of the phrase “queues usually use linked lists” if the code does not leverage List capabilities or an update cursor.

### 12.2. List Needed Along with Changes at an Existing Cursor

LinkedList can be valuable when the algorithm already traverses sequentially with `ListIterator` and needs local insertions/removals around that position.

However, you must account for node allocation, link traversal, and how the position is reached. If access is mostly random by index, LinkedList usually does not benefit from its structure.

Needing a List does not automatically force choosing LinkedList; it is a sign that the problem needs a broader comparison across List operations rather than only a queue/stack comparison.

### 12.3. Integrating with Code Requiring Stack

If legacy APIs specifically require `Stack` or rely on its inherited methods, exceptions, or synchronization, maintaining compatibility can be a practical constraint.

Isolate that constraint at a clear boundary and verify semantics before migrating. Recommending Deque for new LIFO code does not mean every piece of legacy Stack code must be changed immediately in an unrelated edit.

### 12.4. Null Support Needed

First ask what `null` represents and whether it needs to be kept as a real element.

LinkedList or Stack can accept `null`, but doing so changes how `peek`/`poll` are read and how loop termination patterns work. If missing data can be represented by a clearer type while keeping elements non-null, using Queue/Deque is usually easier to understand.

Do not pick a collection just to avoid a `NullPointerException` without deciding on the data semantics first.

## 13. Memory, Latency, and Reading Measurements Carefully

The three classes have different trade-offs, not an absolute ranking for all workloads.

- ArrayDeque has a backing array and array growth steps; it does not have a separate linked node per element.
- LinkedList has a node and links per element; two-ended operations do not have to grow a shared array.
- Stack is based on Vector, with reserve capacity and synchronization costs tied to usage.

After a load spike, an array may still retain a large capacity even after the element count drops. That must be separated from the fact that the element references themselves have been removed.

A conclusion about memory should state clearly whether it measures reserve slots, node objects, allocation volume, or total business data. Do not look only at `size` and assume the classes use the same memory.

### 13.1. Same O(1) Does Not Mean Same Latency

Allocation, garbage collection, reference chasing, available memory regions, and synchronization locks can create real-world differences.

On the other hand, the JVM can optimize different usage patterns differently. Do not predict a fixed speed ratio from the number of `synchronized` keywords or from an array diagram.

If measurement is needed, use the exact operation mix of the application: interleaved additions/removals, representative queue depth or length, allocation load, and degree of sharing across threads.

### 13.2. Do Not Benchmark Operations with Different Meanings

Comparing `ArrayDeque.removeFirst` with `LinkedList.remove(Object)` compares two different requirements: one removes the front, while the other also has to search for a value.

Similarly, comparing `Stack.pop` with `Deque.peek` does not tell you the cost of two stack implementations, because `peek` does not remove data.

A measurement is only useful when the contracts, data, and amount of work performed correspond to one another.

## 14. Common Comparison and Migration Mistakes

| Claim or practice | What is missed | How to fix |
|---|---|---|
| LinkedList is always better because insertion/removal is O(1) | May have to find the position and allocate a node | Account for the full path to the update |
| ArrayDeque is always fastest in all situations | No absolute guarantee for every workload | Choose by contract, then measure when needed |
| Using Stack for FIFO because it has add/remove | Inherited API is not Queue; removing from front of array can shift the sequence | Use an appropriate Queue role |
| Stack is synchronized so every operation sequence is safe | Separate check and update can be interleaved | Establish the required atomic boundary |
| LinkedList accepts null so polling until null always drains everything | Null could be a real first member | Forbid null or handle existence separately |
| Replacing Stack with Deque while keeping `catch EmptyStackException` | The empty exception has changed | Review the contract and handling branch |
| Copying Stack via constructor then popping from first | Stack iterator goes from bottom up | Preserve the proper top convention |
| Using Deque's `push` return value like Stack | `Deque.push` returns `void` | Store the value in a variable before pushing |
| Replacing LinkedList with ArrayDeque while still needing `get(i)` | ArrayDeque is not a List | Review the interface and algorithm |
| Using `equals` to compare two ArrayDeques like Lists | ArrayDeque does not have sequence-based `equals` | Compare observed sequences appropriately |
| Comparing only `size` after running | Ignores exact order and occurrence counts | Compare the full output |
| Picking a class from a few-millisecond microbenchmark | Scenario and JVM warmup can dominate | Use a representative, methodical benchmark |

When reading advice on choosing a collection, look for the accompanying conditions: single-threaded or multithreaded, whether data can be null, whether indexing is needed or only two ends, and whether positioning cost has been accounted for.

## 15. Checklist Before Replacing a Class in Existing Code

A short but decisive checklist:

1. State the expected removal order clearly: FIFO or LIFO.
2. Test with at least three distinct elements and interleaved add/remove steps.
3. Test empty handling with the exact method types and exceptions.
4. Test null data against the existing contract.
5. Test iterator order if used for display or copying.
6. Check any specific List/Vector/Stack methods that calling code is using.
7. Check reference sharing, synchronization, and entire update sequences.
8. Check `equals` behavior if the new class has different semantics.

Tests should protect application requirements, not just verify the new class name or an implementation detail.

If you need to compare data order, collect the removed elements into a `List` as in the programs in this article. Two classes with the same set of elements but different order can still produce different business behavior.

Do not use a `Set` to verify a stack/queue replacement: a `Set` can hide ordering and duplicate counts.

## 16. Practice Exercises

### Exercise 1: Single-Threaded Job Queue

Only appending at the end and removing from the front are needed, nulls are not accepted, and indexed access is not needed. Among the three classes, which one should be considered first?

**Suggested answer:** `ArrayDeque` through the `Queue` or `Deque` interface is the appropriate choice to start with. You still need to consider scale, bounds, and actual requirements.

### Exercise 2: Middle Removal in LinkedList

A method takes index `i` and calls `remove(i)`. Can you conclude it is O(1) just because LinkedList uses links?

**Suggested answer:** No. It must traverse to position `i`; the general cost is still O(n). Local updates at an already-positioned cursor are a different case.

### Exercise 3: Same Pop, Different Iterator

Push A, B, C onto a Stack and onto an ArrayDeque. Both pop C first. Do their iterators have the same order?

**Suggested answer:** No. Stack iterates A, B, C in Vector order; ArrayDeque using `push` iterates C, B, A from `first` to `last`.

### Exercise 4: Changing peek

Legacy code catches `EmptyStackException` around `Stack.peek`. If changed to `Deque.peek`, what happens in the empty case?

**Suggested answer:** `Deque.peek` returns `null`. You must review the handling branch or choose a method/adapter that preserves the desired contract.

### Exercise 5: Stack with One Element

Two threads both run a non-empty check followed by `pop`. Does per-method synchronization guarantee both `pop` calls succeed?

**Suggested answer:** No. One thread can remove the element between the other thread's two calls. The check-then-pop sequence needs an appropriate mechanism for the entire requirement.

### Exercise 6: Migrating Data Containing null

A LinkedList is holding `null` as a real element. Can it be replaced with ArrayDeque without revisiting the data decision?

**Suggested answer:** No. ArrayDeque forbids `null`; you must decide whether to reject it, represent it differently, or keep a structure with a matching contract.

### Exercise 7: Stack Constructor Copy

A Stack currently has A at the bottom and C at the top. Create an ArrayDeque using the constructor taking the Stack, then call `pop`.

Which value can be retrieved and why?

**Suggested answer:** A, because the constructor preserves the iterator order A, B, C and `Deque.pop` removes `first`. To preserve top C, you must transfer elements according to an explicit top convention.

### Exercise 8: Choosing Stack Because It Has get(i)

Stack has O(1) `get(i)`, so is it the default choice for any random-access list?

**Suggested answer:** No. Inherited capabilities do not change the purpose of a structure. When the need is a List, compare List implementations by real operations rather than picking Stack just because a method is available.

A sound choice must preserve ordering semantics, valid data rules, and coordination boundaries. ArrayDeque, LinkedList, and Stack should only be compared after those requirements have been clearly stated.
